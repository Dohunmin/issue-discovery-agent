"""Google Trends 한국 실시간 인기 검색어 수집기.

뉴스 교차 태깅 전용 — Stage 1 소스로 직접 경쟁하지 않고,
수집된 뉴스 기사에 [TRENDING] 태그를 부여하는 데 사용한다.
"""

import feedparser
from src.config import GOOGLE_TRENDS_RSS
from src.logger import log


def collect_trend_keywords() -> list[str]:
    """Google Trends 한국 실시간 인기 검색어 목록을 반환한다."""
    if not GOOGLE_TRENDS_RSS:
        return []

    try:
        feed = feedparser.parse(GOOGLE_TRENDS_RSS)
        keywords = []
        for entry in feed.entries:
            title = entry.get("title", "").strip()
            if title:
                keywords.append(title)

        log(f"[Trends] 한국 인기 검색어 {len(keywords)}개 수집")
        for kw in keywords[:10]:
            log(f"  > {kw}")
        return keywords

    except Exception as e:
        log(f"[Trends] 수집 실패: {e}")
        return []


def tag_trending_articles(
    articles: list[dict],
    trend_keywords: list[str],
) -> list[dict]:
    """트렌딩 키워드가 포함된 뉴스 기사에 trending=True 태그를 부여한다."""
    if not trend_keywords:
        return articles

    # 키워드를 단어 단위로 분리하여 부분 매칭 (예: "테슬라 yl" → "테슬라"도 매칭)
    keyword_words = set()
    for kw in trend_keywords:
        for word in kw.lower().split():
            if len(word) >= 2:  # 2글자 이상만
                keyword_words.add(word)

    tagged_count = 0

    for article in articles:
        title = article.get("title", "").lower()
        desc = article.get("description", "").lower()
        text = f"{title} {desc}"

        matched = [w for w in keyword_words if w in text]
        if matched:
            article["trending"] = True
            article["trend_keywords"] = matched
            tagged_count += 1

    log(f"[Trends] {tagged_count}건 뉴스에 [TRENDING] 태그 부여")
    return articles
