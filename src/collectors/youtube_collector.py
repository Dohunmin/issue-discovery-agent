"""YouTube 시드 채널 수집기.

인스타와 동일한 구조: 특정 채널의 최근 영상 중 7일 이내 업로드된 것만 수집.
YOUTUBE_SEED_CHANNELS 환경변수에 채널 ID를 쉼표로 추가하면 자동 인식.
"""

from datetime import datetime, timedelta, timezone
from src.config import YOUTUBE_API_KEY, YOUTUBE_SEED_CHANNELS
from src.logger import log

MAX_FETCH_PER_CHANNEL = 10  # 최근 10개를 가져와서 날짜 필터링
DAYS_WINDOW = 7  # 7일 이내 영상만


def collect_youtube_channels() -> list[dict]:
    """시드 채널의 최근 7일 이내 영상을 수집한다."""
    if not YOUTUBE_API_KEY:
        log("[YouTube] API 키 없음 — 건너뜀")
        return []

    if not YOUTUBE_SEED_CHANNELS:
        log("[YouTube] 시드 채널 없음 — 건너뜀")
        return []

    try:
        from googleapiclient.discovery import build

        youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS_WINDOW)
        all_videos = []

        for channel_id in YOUTUBE_SEED_CHANNELS:
            videos = _fetch_channel_videos(youtube, channel_id, cutoff)
            all_videos.extend(videos)

        log(f"[YouTube] 총 {len(all_videos)}개 영상 수집 ({len(YOUTUBE_SEED_CHANNELS)}개 채널, {DAYS_WINDOW}일 이내)")
        return all_videos

    except Exception as e:
        log(f"[YouTube] 수집 실패: {e}")
        return []


def _fetch_channel_videos(youtube, channel_id: str, cutoff: datetime) -> list[dict]:
    """채널의 최근 영상 중 cutoff 이후 업로드된 것만 가져온다."""
    videos = []

    try:
        # 1) 채널의 uploads 플레이리스트 ID 조회
        ch_response = youtube.channels().list(
            part="snippet,contentDetails",
            id=channel_id,
        ).execute()

        items = ch_response.get("items", [])
        if not items:
            log(f"  [YouTube] 채널 {channel_id} 찾을 수 없음")
            return []

        channel_name = items[0]["snippet"]["title"]
        uploads_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

        # 2) 최근 영상 목록 (최대 10개 가져와서 날짜 필터)
        pl_response = youtube.playlistItems().list(
            part="snippet",
            playlistId=uploads_id,
            maxResults=MAX_FETCH_PER_CHANNEL,
        ).execute()

        video_ids = []
        for item in pl_response.get("items", []):
            vid = item["snippet"]["resourceId"].get("videoId", "")
            if vid:
                video_ids.append(vid)

        if not video_ids:
            return []

        # 3) 영상 상세 정보 (조회수 + 날짜 확인)
        v_response = youtube.videos().list(
            part="snippet,statistics",
            id=",".join(video_ids),
        ).execute()

        for item in v_response.get("items", []):
            snippet = item["snippet"]
            stats = item.get("statistics", {})

            # 날짜 필터: 7일 이내만
            published_str = snippet.get("publishedAt", "")
            if published_str:
                published = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                if published < cutoff:
                    continue

            videos.append({
                "title": snippet.get("title", ""),
                "description": snippet.get("description", "")[:300],
                "channel": channel_name,
                "channel_id": channel_id,
                "view_count": int(stats.get("viewCount", 0)),
                "published_at": published_str,
                "url": f"https://www.youtube.com/watch?v={item['id']}",
                "source": "youtube_channel",
                "category": "youtube",
            })

        log(f"  [YouTube] @{channel_name}: {len(videos)}개 영상 (7일 이내)")
        for v in videos:
            date = v["published_at"][:10]
            views = v["view_count"]
            log(f"    [{date}] {v['title'][:60]} | 조회수 {views:,}")

    except Exception as e:
        log(f"  [YouTube] 채널 {channel_id} 수집 실패: {e}")

    return videos
