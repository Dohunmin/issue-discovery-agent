import json
from openai import OpenAI
from src.config import OPENAI_API_KEY, SNS_FILTER_PROMPT, STAGE1_PROMPT, STAGE2_PROMPT
from src.analyzer.preference import load_preference_vector, score_candidates
from src.logger import log


def select_topics(
    rss_articles: list[dict],
    instagram_posts_by_account: dict[str, list[dict]],
    youtube_videos: list[dict] | None = None,
    community_posts: list[dict] | None = None,
) -> list[dict]:
    """다중 소스 AI 선정 + 취향 벡터:
    - SNS 필터: 인스타 계정당 2~3개 선택
    - Stage 1: 뉴스 + YouTube + 커뮤니티 → Top 30
    - 취향 벡터: 전체 후보에 preference_score 부여
    - Stage 2A: 취향 반영 Top 10
    - Stage 2B: 모델 자체 Top 3 (비교용)
    """
    client = OpenAI(api_key=OPENAI_API_KEY)
    youtube_videos = youtube_videos or []
    community_posts = community_posts or []

    # SNS 필터: 계정당 AI가 2~3개씩 선택
    log("[SNS 필터] 계정별 게시물 분석 중...")
    filtered_sns = _filter_instagram(client, instagram_posts_by_account)
    log(f"[SNS 필터] 총 {len(filtered_sns)}개 게시물 선정 완료")
    for s in filtered_sns:
        log(f"  > @{s.get('account','')}: {s.get('caption','')[:80]}")

    # Stage 1: 뉴스 + YouTube + 커뮤니티에서 Top 30 선별
    log("[Stage 1] 뉴스 + YouTube + 커뮤니티에서 Top 30 선별 중...")
    top30_articles = _stage1_filter(client, rss_articles, youtube_videos, community_posts)
    log(f"[Stage 1] {len(top30_articles)}개 선별 완료")
    for i, a in enumerate(top30_articles, 1):
        title = a.get("title", a.get("canonical_title", ""))
        log(f"  {i}. [{a.get('category','')}] {title[:70]}")

    # 취향 벡터 로드 + 후보에 점수 부여
    log("[Preference] 취향 벡터 로드 중...")
    pref_data = load_preference_vector(client)
    if pref_data:
        top30_articles = score_candidates(
            client, pref_data, top30_articles, text_key="title",
            label="뉴스+유튜브+커뮤니티 Top 30",
        )
        filtered_sns = score_candidates(
            client, pref_data, filtered_sns, text_key="caption",
            label="인스타 SNS",
        )

    # Stage 2A: 취향 반영 Top 10
    log("[Stage 2A] 취향 반영 → Top 10 선정 중...")
    topics = _stage2_select(client, top30_articles, filtered_sns)
    log(f"[Stage 2A] {len(topics)}개 이슈 최종 선정 완료")
    for t in topics:
        t["selection_type"] = "preference"
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


def _stage1_filter(
    client: OpenAI,
    articles: list[dict],
    youtube_videos: list[dict] | None = None,
    community_posts: list[dict] | None = None,
) -> list[dict]:
    """1단계: 뉴스 + YouTube + 커뮤니티에서 Top 30을 선별한다."""
    rss_text = _build_stage1_text(articles, youtube_videos or [], community_posts or [])

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
            items = result.get("articles", [])
        elif isinstance(result, list):
            items = result
        else:
            items = []

        # 후처리: 제목 중복 제거 + 30개 강제
        seen_titles = set()
        deduped = []
        for item in items:
            title = item.get("title", "").strip()
            if title and title not in seen_titles:
                seen_titles.add(title)
                deduped.append(item)

        # GPT가 30개 미만을 반환하면, 입력 소스에서 보충
        if len(deduped) < 30:
            shortage = 30 - len(deduped)
            # YouTube → 뉴스 순으로 보충
            backfill_sources = (youtube_videos or []) + articles
            for src in backfill_sources:
                if len(deduped) >= 30:
                    break
                title = src.get("title", "").strip()
                if title and title not in seen_titles:
                    seen_titles.add(title)
                    deduped.append({
                        "title": title,
                        "description": src.get("description", ""),
                        "category": src.get("category", ""),
                        "source_ref": src.get("source", ""),
                        "reason": "자동 보충",
                    })
            log(f"[Stage 1] GPT가 {30 - shortage}개만 반환 → {shortage}개 자동 보충하여 {len(deduped)}개")

        return deduped[:30]
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

        # 후처리: 제목 중복 제거 + 10개 보충 + 카테고리 다양성
        topics = _dedup_topics(topics)

        # 중복 제거로 10개 미만이 되면 Stage 1 후보에서 보충
        if len(topics) < 10:
            selected_titles = {t.get("original_title", t.get("canonical_title", "")).strip() for t in topics}
            backfill_pool = top30_articles + filtered_sns
            for item in backfill_pool:
                if len(topics) >= 10:
                    break
                title = item.get("title", item.get("caption", "")).strip()
                if title and title not in selected_titles:
                    selected_titles.add(title)
                    topics.append({
                        "original_title": title,
                        "why_now": "Stage 1에서 선별된 후보",
                        "issue_hook": "",
                        "source_ref": item.get("source_ref", item.get("source", "")),
                    })
            log(f"[Stage 2] 중복 제거 후 보충 → {len(topics)}개")

        topics = _enforce_diversity(topics)
        return topics
    except json.JSONDecodeError:
        log(f"[Stage 2] JSON 파싱 실패: {raw[:200]}")
        return []



def _dedup_topics(topics: list[dict]) -> list[dict]:
    """제목 기반 중복 제거. GPT가 같은 이슈를 다른 rank로 반환하는 경우 방지."""
    seen = set()
    deduped = []
    for t in topics:
        title = t.get("original_title", t.get("canonical_title", "")).strip()
        if not title or title in seen:
            continue
        seen.add(title)
        deduped.append(t)
    return deduped


def _enforce_diversity(topics: list[dict], max_per_category: int = 3) -> list[dict]:
    """동일 카테고리 최대 N개로 제한하는 후처리.

    source_ref 기반으로 뉴스/SNS 비율을 조절한다.
    토픽 수와 무관하게 항상 다양성 체크를 실행한다.
    """
    if not topics:
        return topics

    category_count: dict[str, int] = {}
    filtered = []
    overflow = []

    for t in topics:
        ref = t.get("source_ref", "")
        cat = ref.split("#")[0] if "#" in ref else "unknown"
        count = category_count.get(cat, 0)

        if count < max_per_category:
            filtered.append(t)
            category_count[cat] = count + 1
        else:
            overflow.append(t)

    # 원래 개수까지 채우기
    target = min(len(topics), 10)
    while len(filtered) < target and overflow:
        filtered.append(overflow.pop(0))

    return filtered[:target]


def _build_rss_text(articles: list[dict]) -> str:
    """1단계용: 전체 RSS 기사 목록 텍스트."""
    lines = [f"총 {len(articles)}개 뉴스 기사:\n"]
    for i, art in enumerate(articles, 1):
        lines.append(
            f"{i}. [{art.get('category', '')}] {art.get('title', '')} | "
            f"{art.get('description', '')[:200]}"
        )
    return "\n".join(lines)


def _build_stage1_text(
    articles: list[dict],
    youtube_videos: list[dict],
    community_posts: list[dict],
) -> str:
    """1단계용: YouTube + 커뮤니티를 앞에, 뉴스를 뒤에 배치.

    GPT positional bias 대응: 중요 소스(유튜브/커뮤니티)를 앞에 놓고,
    뉴스는 제목만 전달하여 토큰을 절약한다.
    """
    lines = []

    # 1) YouTube — 맨 앞 배치 (GPT가 확실히 인식하도록)
    if youtube_videos:
        lines.append(f"=== YouTube 이슈/트렌드 채널 ({len(youtube_videos)}건) ===")
        lines.append("2030 이슈를 다루는 채널의 최근 영상. 이 중 이슈성 있는 것을 반드시 선정하세요.")
        for i, vid in enumerate(youtube_videos, 1):
            views = vid.get("view_count", 0)
            view_str = f"{views:,}" if views else ""
            lines.append(
                f"유튜브#{i}. {vid.get('title', '')} | "
                f"{vid.get('channel', '')} | 조회수 {view_str}"
            )

    # 2) 뉴스 — 제목만 (description 생략하여 토큰 절약)
    lines.append(f"\n=== 뉴스 기사 ({len(articles)}건) ===")
    for i, art in enumerate(articles, 1):
        trending_tag = " [TRENDING]" if art.get("trending") else ""
        lines.append(
            f"뉴스#{i}. [{art.get('category', '')}]{trending_tag} {art.get('title', '')}"
        )

    return "\n".join(lines)


def _build_combined_text(
    top30_articles: list[dict],
    filtered_sns: list[dict],
) -> str:
    """2단계용: Top30 뉴스 + AI 선별된 SNS 합산 텍스트 (취향 점수 포함)."""
    has_pref = any("preference_label" in a for a in top30_articles)

    lines = [f"=== 1차 선별된 뉴스 ({len(top30_articles)}건) ==="]
    if has_pref:
        lines.append("(운영자 취향: 운영자의 과거 선호도 기반 등급. '매우 높음'인 주제를 우선 선정하세요)")
    for i, art in enumerate(top30_articles, 1):
        title = art.get("title", art.get("canonical_title", ""))
        desc = art.get("description", "")
        reason = art.get("reason", "")
        category = art.get("category", "")
        label = art.get("preference_label", "")
        pref_tag = f" [운영자취향:{label}]" if label else ""
        lines.append(f"{i}. [{category}]{pref_tag} {title} | {desc[:200]}")
        if reason:
            lines.append(f"   -> 선정 이유: {reason}")

    lines.append(f"\n=== AI 선별된 인스타그램 SNS ({len(filtered_sns)}건) ===")
    if has_pref:
        lines.append("(운영자 취향: 운영자의 과거 선호도 기반 등급. '매우 높음'인 주제를 우선 선정하세요)")
    for i, post in enumerate(filtered_sns, 1):
        label = post.get("preference_label", "")
        pref_tag = f" [운영자취향:{label}]" if label else ""
        lines.append(
            f"{i}. @{post.get('account', '')}:{pref_tag} {post.get('caption', '')[:300]} "
            f"{' '.join(post.get('hashtags', []))}"
        )

    return "\n".join(lines)
