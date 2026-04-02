import json
from openai import OpenAI
from src.config import OPENAI_API_KEY, SNS_FILTER_PROMPT, STAGE1_PROMPT, STAGE2_PROMPT
from src.logger import log


def select_topics(
    rss_articles: list[dict],
    instagram_posts_by_account: dict[str, list[dict]],
) -> list[dict]:
    """3단계 AI 선정:
    - SNS 필터: 계정당 7개 → AI가 3개 선택 = 9개
    - Stage 1: 뉴스 전체 → Top 30
    - Stage 2: 뉴스 30 + SNS 9 = ~39건 → Top 10
    """
    client = OpenAI(api_key=OPENAI_API_KEY)

    # SNS 필터: 계정당 AI가 3개씩 선택
    log("[SNS 필터] 계정별 게시물 분석 중...")
    filtered_sns = _filter_instagram(client, instagram_posts_by_account)
    log(f"[SNS 필터] 총 {len(filtered_sns)}개 게시물 선정 완료")
    for s in filtered_sns:
        log(f"  > @{s.get('account','')}: {s.get('caption','')[:80]}")

    # Stage 1: 뉴스에서 Top 30 선별
    log("[Stage 1] 뉴스에서 Top 30 선별 중...")
    top30_articles = _stage1_filter(client, rss_articles)
    log(f"[Stage 1] {len(top30_articles)}개 기사 선별 완료")
    for i, a in enumerate(top30_articles, 1):
        title = a.get("title", a.get("canonical_title", ""))
        log(f"  {i}. [{a.get('category','')}] {title[:70]}")

    # Stage 2: 뉴스 30 + SNS 9 → 최종 Top 10
    log("[Stage 2] 뉴스 + SNS 합산 -> Top 10 선정 중...")
    topics = _stage2_select(client, top30_articles, filtered_sns)
    log(f"[Stage 2] {len(topics)}개 이슈 최종 선정 완료")
    for t in topics:
        log(f"  #{t.get('rank','')} {t.get('original_title', t.get('canonical_title',''))[:70]}")
        log(f"     why_now: {t.get('why_now','')[:80]}")

    return topics


def _filter_instagram(
    client: OpenAI,
    posts_by_account: dict[str, list[dict]],
) -> list[dict]:
    """각 계정의 게시물 7개를 AI가 분석하여 3개씩 선택한다."""
    selected_posts = []

    AD_KEYWORDS = ["#광고", "#ad", "#협찬", "#sponsored", "#제공"]

    for account, posts in posts_by_account.items():
        if not posts:
            continue

        # 광고 게시물 사전 제거 (코드 레벨 강제)
        clean_posts = []
        for p in posts:
            caption = p.get("caption", "")
            caption_lower = caption.lower()
            if any(kw in caption_lower for kw in AD_KEYWORDS):
                log(f"  @{account}: 광고 제거 - {caption[:50]}...")
                continue
            clean_posts.append(p)
        posts = clean_posts

        if not posts:
            log(f"  @{account}: 광고 제거 후 남은 게시물 없음")
            continue

        # 캡션 목록 구성
        captions_text = f"계정: @{account}\n\n"
        for i, post in enumerate(posts):
            caption = post.get("caption", "(캡션 없음)")
            captions_text += f"[{i}] {caption[:400]}\n\n"

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SNS_FILTER_PROMPT},
                {"role": "user", "content": captions_text},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content
        try:
            result = json.loads(raw)
            indices = result.get("selected", [])
            for idx in indices:
                if 0 <= idx < len(posts):
                    selected_posts.append(posts[idx])
            log(f"  @{account}: {len(posts)}개 중 인덱스 {indices} 선택")
        except (json.JSONDecodeError, TypeError):
            # 파싱 실패 시 캡션이 있는 것 중 앞 3개 폴백
            fallback = [p for p in posts if p.get("caption")][:3]
            selected_posts.extend(fallback)
            log(f"  @{account}: AI 필터 실패, 폴백 {len(fallback)}개 선택")

    return selected_posts


def _stage1_filter(client: OpenAI, articles: list[dict]) -> list[dict]:
    """1단계: 전체 뉴스에서 Top 30을 선별한다."""
    rss_text = _build_rss_text(articles)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": STAGE1_PROMPT},
            {"role": "user", "content": rss_text},
        ],
        temperature=0.5,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content
    try:
        result = json.loads(raw)
        if isinstance(result, dict):
            return result.get("articles", [])
        return result if isinstance(result, list) else []
    except json.JSONDecodeError:
        log(f"[Stage 1] JSON 파싱 실패: {raw[:200]}")
        return []


def _stage2_select(
    client: OpenAI,
    top30_articles: list[dict],
    filtered_sns: list[dict],
) -> list[dict]:
    """2단계: 뉴스 Top30 + SNS 9개 → 최종 Top 10 선정."""
    combined_text = _build_combined_text(top30_articles, filtered_sns)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": STAGE2_PROMPT},
            {"role": "user", "content": combined_text},
        ],
        temperature=0.7,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content
    try:
        result = json.loads(raw)
        if isinstance(result, list):
            topics = result
        elif isinstance(result, dict):
            topics = result.get("topics", result.get("issues", []))
        else:
            topics = []

        # 카테고리 다양성 후처리: 동일 source_ref 유형(뉴스/SNS) 최대 비율 제한
        topics = _enforce_diversity(topics)
        return topics
    except json.JSONDecodeError:
        log(f"[Stage 2] JSON 파싱 실패: {raw[:200]}")
        return []


def _enforce_diversity(topics: list[dict]) -> list[dict]:
    """동일 카테고리 최대 3개로 제한하는 후처리."""
    if len(topics) <= 10:
        return topics

    category_count: dict[str, int] = {}
    filtered = []
    overflow = []

    for t in topics:
        # source_ref에서 카테고리 추정 (뉴스#N → 뉴스, SNS#N → SNS)
        ref = t.get("source_ref", "")
        cat = ref.split("#")[0] if "#" in ref else "unknown"
        count = category_count.get(cat, 0)

        if count < 3:
            filtered.append(t)
            category_count[cat] = count + 1
        else:
            overflow.append(t)

    # 10개 채우기
    while len(filtered) < 10 and overflow:
        filtered.append(overflow.pop(0))

    return filtered[:10]


def _build_rss_text(articles: list[dict]) -> str:
    """1단계용: 전체 RSS 기사 목록 텍스트."""
    lines = [f"총 {len(articles)}개 뉴스 기사:\n"]
    for i, art in enumerate(articles, 1):
        lines.append(
            f"{i}. [{art.get('category', '')}] {art.get('title', '')} | "
            f"{art.get('description', '')[:200]}"
        )
    return "\n".join(lines)


def _build_combined_text(
    top30_articles: list[dict],
    filtered_sns: list[dict],
) -> str:
    """2단계용: Top30 뉴스 + AI 선별된 SNS 합산 텍스트."""
    lines = [f"=== 1차 선별된 뉴스 ({len(top30_articles)}건) ==="]
    for i, art in enumerate(top30_articles, 1):
        title = art.get("title", art.get("canonical_title", ""))
        desc = art.get("description", "")
        reason = art.get("reason", "")
        category = art.get("category", "")
        lines.append(f"{i}. [{category}] {title} | {desc[:200]}")
        if reason:
            lines.append(f"   -> 선정 이유: {reason}")

    lines.append(f"\n=== AI 선별된 인스타그램 SNS ({len(filtered_sns)}건) ===")
    for i, post in enumerate(filtered_sns, 1):
        lines.append(
            f"{i}. @{post.get('account', '')}: {post.get('caption', '')[:300]} "
            f"{' '.join(post.get('hashtags', []))}"
        )

    return "\n".join(lines)
