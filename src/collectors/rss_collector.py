import feedparser
from datetime import datetime, timedelta, timezone
from src.config import RSS_FEEDS
from src.logger import log


def collect_rss() -> list[dict]:
    """RSS 피드에서 최근 24시간 내 기사를 수집한다."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    articles = []
    seen_urls: set[str] = set()

    for category, urls in RSS_FEEDS.items():
        for url in urls:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries:
                    published = _parse_date(entry)
                    if published and published < cutoff:
                        continue

                    # URL 기반 중복 제거 (같은 기사가 다른 카테고리에 있을 때)
                    article_url = entry.get("link", "")
                    if article_url in seen_urls:
                        continue
                    seen_urls.add(article_url)

                    articles.append({
                        "title": entry.get("title", ""),
                        "description": entry.get("summary", ""),
                        "source": feed.feed.get("title", url),
                        "url": article_url,
                        "published_at": published.isoformat() if published else "",
                        "category": category,
                    })
            except Exception as e:
                log(f"[RSS] {url} 수집 실패: {e}")

    log(f"[RSS] 총 {len(articles)}개 기사 수집 완료 (URL 중복 제거 적용)")
    return articles


def _parse_date(entry) -> datetime | None:
    """feedparser 엔트리에서 날짜를 파싱한다."""
    for field in ("published_parsed", "updated_parsed"):
        parsed = entry.get(field)
        if parsed:
            from time import mktime
            return datetime.fromtimestamp(mktime(parsed), tz=timezone.utc)
    return None
