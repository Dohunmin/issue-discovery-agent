import requests
from src.config import DISCORD_WEBHOOK_URL


def send_to_discord(topics: list[dict]) -> None:
    """선정된 이슈를 Discord 웹훅으로 전송한다."""
    if not DISCORD_WEBHOOK_URL:
        print("[Discord] DISCORD_WEBHOOK_URL이 설정되지 않아 건너뜀")
        return

    message = _format_message(topics)

    response = requests.post(
        DISCORD_WEBHOOK_URL,
        json={"content": message},
        timeout=10,
    )

    if response.status_code == 204:
        print("[Discord] 전송 완료")
    else:
        print(f"[Discord] 전송 실패: {response.status_code} {response.text}")


def _format_message(topics: list[dict]) -> str:
    """디스코드 메시지 포맷으로 변환한다."""
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    parts = [f"📌 **Daily Issue Discovery** ({today})\n"]

    for topic in topics:
        rank = topic.get("rank", "?")
        title = topic.get("canonical_title", "제목 없음")
        why_now = topic.get("why_now", "")
        issue_hook = topic.get("issue_hook", "")

        parts.append(
            f"**{rank}. {title}**\n"
            f"**why_now:** {why_now}\n"
            f"**issue_hook:** {issue_hook}\n"
        )

    return "\n".join(parts)
