"""YouTube 한국 트렌딩 수집기.

YouTube Data API v3로 한국 인기 급상승 영상을 수집한다.
Music 카테고리는 제외하고, 제목/설명/태그/조회수를 반환한다.
"""

from src.config import YOUTUBE_API_KEY
from src.logger import log

# Music(10) 카테고리 제외 — 트렌딩의 40~60%가 음악이라 노이즈
EXCLUDE_CATEGORIES = {"10"}


def collect_youtube_trending() -> list[dict]:
    """한국 YouTube 트렌딩 영상을 수집한다."""
    if not YOUTUBE_API_KEY:
        log("[YouTube] API 키 없음 — 건너뜀")
        return []

    try:
        from googleapiclient.discovery import build

        youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

        response = youtube.videos().list(
            part="snippet,statistics",
            chart="mostPopular",
            regionCode="KR",
            maxResults=50,
        ).execute()

        videos = []
        for item in response.get("items", []):
            snippet = item["snippet"]
            stats = item.get("statistics", {})
            category_id = snippet.get("categoryId", "")

            if category_id in EXCLUDE_CATEGORIES:
                continue

            videos.append({
                "title": snippet.get("title", ""),
                "description": snippet.get("description", "")[:300],
                "tags": snippet.get("tags", [])[:10],
                "channel": snippet.get("channelTitle", ""),
                "category_id": category_id,
                "view_count": int(stats.get("viewCount", 0)),
                "published_at": snippet.get("publishedAt", ""),
                "url": f"https://www.youtube.com/watch?v={item['id']}",
                "source": "youtube_trending",
                "category": "youtube",
            })

        log(f"[YouTube] 트렌딩 {len(videos)}개 수집 (Music 제외)")
        return videos

    except Exception as e:
        log(f"[YouTube] 수집 실패: {e}")
        return []
