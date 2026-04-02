import requests
from src.config import DISCORD_WEBHOOK_URL
from src.logger import log


def send_to_discord(topics: list[dict]) -> None:
    """선정된 이슈를 Discord 웹훅으로 5개씩 분할 전송한다."""
    if not DISCORD_WEBHOOK_URL:
        log("[Discord] DISCORD_WEBHOOK_URL이 설정되지 않아 건너뜀")
        return

    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 5개씩 분할
    chunks = [topics[i:i + 5] for i in range(0, len(topics), 5)]

    for idx, chunk in enumerate(chunks):
        if idx == 0:
            header = f"**Daily Issue Discovery** ({today})\n"
        else:
            header = ""

        parts = [header] if header else []
        for topic in chunk:
            rank = topic.get("rank", "?")
            title = topic.get("original_title", topic.get("canonical_title", "제목 없음"))
            why_now = topic.get("why_now", "")
            issue_hook = topic.get("issue_hook", "")

            parts.append(
                f"**{rank}. {title}**\n"
                f"> **why_now:** {why_now}\n"
                f"> **issue_hook:** {issue_hook}\n"
            )

        message = "\n".join(parts)

        response = requests.post(
            DISCORD_WEBHOOK_URL,
            json={"content": message},
            timeout=10,
        )

        if response.status_code == 204:
            log(f"[Discord] 파트 {idx + 1}/{len(chunks)} 전송 완료")
        else:
            log(f"[Discord] 파트 {idx + 1} 전송 실패: {response.status_code} {response.text}")
