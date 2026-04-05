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

    # GPT가 반환하는 rank가 뒤죽박죽일 수 있으므로, 순서대로 1~N 강제 부여
    for i, topic in enumerate(topics, 1):
        topic["rank"] = i

    chunks = [topics[i:i + 5] for i in range(0, len(topics), 5)]

    for idx, chunk in enumerate(chunks):
        if idx == 0:
            header = f"**Daily Issue Discovery** ({today})\n"
        else:
            header = ""

        parts = [header] if header else []
        for topic in chunk:
            rank = topic["rank"]
            title = topic.get("original_title", topic.get("canonical_title", "제목 없음"))
            why_now = topic.get("why_now", "")
            issue_hook = topic.get("issue_hook", "")

            parts.append(
                f"**{rank}. {title}**\n"
                f"> **why_now:** {why_now}\n"
                f"> **issue_hook:** {issue_hook}\n"
            )

        _send_message("\n".join(parts), f"파트 {idx + 1}/{len(chunks)}")


def _send_message(content: str, label: str) -> None:
    """Discord 웹훅으로 메시지를 전송한다."""
    response = requests.post(
        DISCORD_WEBHOOK_URL,
        json={"content": content},
        timeout=10,
    )

    if response.status_code == 204:
        log(f"[Discord] {label} 전송 완료")
    else:
        log(f"[Discord] {label} 전송 실패: {response.status_code} {response.text}")
