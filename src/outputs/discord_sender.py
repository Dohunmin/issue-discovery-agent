import requests
from src.config import DISCORD_WEBHOOK_URL
from src.logger import log


def send_to_discord(topics: list[dict], model_picks: list[dict] | None = None) -> None:
    """선정된 이슈를 Discord 웹훅으로 전송한다.

    Args:
        topics: 취향 반영 Top 10
        model_picks: 모델 자체 판단 Top 3 (비교용)
    """
    if not DISCORD_WEBHOOK_URL:
        log("[Discord] DISCORD_WEBHOOK_URL이 설정되지 않아 건너뜀")
        return

    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 취향 반영 Top 10 (5개씩 분할)
    chunks = [topics[i:i + 5] for i in range(0, len(topics), 5)]

    for idx, chunk in enumerate(chunks):
        if idx == 0:
            header = f"**Daily Issue Discovery** ({today})\n"
            header += "━━━ 취향 반영 Top 10 ━━━\n"
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

        _send_message("\n".join(parts), f"취향 파트 {idx + 1}/{len(chunks)}")

    # 모델 자체 판단 Top 3 (별도 메시지)
    if model_picks:
        parts = ["━━━ 모델 자체 판단 Top 3 (비교용) ━━━\n"]
        for topic in model_picks:
            rank = topic.get("rank", "?")
            title = topic.get("original_title", topic.get("canonical_title", "제목 없음"))
            why_now = topic.get("why_now", "")

            parts.append(
                f"**{rank}. {title}**\n"
                f"> {why_now}\n"
            )

        _send_message("\n".join(parts), "모델 자체 판단")


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
