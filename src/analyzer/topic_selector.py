import json
from openai import OpenAI
from src.config import OPENAI_API_KEY, STAGE1_PROMPT, STAGE2_PROMPT


def select_topics(
    rss_articles: list[dict],
    instagram_posts: list[dict],
) -> list[dict]:
    """2단계 AI 선정: 뉴스 Top30 → 뉴스+SNS Top10."""
    client = OpenAI(api_key=OPENAI_API_KEY)

    # Stage 1: 뉴스에서 Top 30 선별
    print("[Stage 1] 뉴스에서 Top 30 선별 중...")
    top30_articles = _stage1_filter(client, rss_articles)
    print(f"[Stage 1] {len(top30_articles)}개 기사 선별 완료")

    # Stage 2: Top 30 뉴스 + SNS 20개 → 최종 Top 10
    print("[Stage 2] 뉴스 + SNS 합산 → Top 10 선정 중...")
    topics = _stage2_select(client, top30_articles, instagram_posts)
    print(f"[Stage 2] {len(topics)}개 이슈 최종 선정 완료")

    return topics


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
        print(f"[Stage 1] JSON 파싱 실패: {raw[:200]}")
        return []


def _stage2_select(
    client: OpenAI,
    top30_articles: list[dict],
    instagram_posts: list[dict],
) -> list[dict]:
    """2단계: 뉴스 Top30 + SNS → 최종 Top 10 선정."""
    combined_text = _build_combined_text(top30_articles, instagram_posts)

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
            return result
        if isinstance(result, dict):
            return result.get("topics", result.get("issues", []))
        return []
    except json.JSONDecodeError:
        print(f"[Stage 2] JSON 파싱 실패: {raw[:200]}")
        return []


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
    instagram_posts: list[dict],
) -> str:
    """2단계용: Top30 뉴스 + SNS 데이터 합산 텍스트."""
    lines = [f"=== 1차 선별된 뉴스 ({len(top30_articles)}건) ==="]
    for i, art in enumerate(top30_articles, 1):
        title = art.get("title", art.get("canonical_title", ""))
        desc = art.get("description", "")
        reason = art.get("reason", "")
        category = art.get("category", "")
        lines.append(f"{i}. [{category}] {title} | {desc[:200]}")
        if reason:
            lines.append(f"   → 선정 이유: {reason}")

    lines.append(f"\n=== 인스타그램 SNS ({len(instagram_posts[:20])}건) ===")
    for i, post in enumerate(instagram_posts[:20], 1):
        lines.append(
            f"{i}. @{post.get('account', '')}: {post.get('caption', '')[:300]} "
            f"{' '.join(post.get('hashtags', []))}"
        )

    return "\n".join(lines)
