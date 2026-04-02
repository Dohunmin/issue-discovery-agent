"""이슈 디스커버리 에이전트 - 엔트리포인트"""

from src.collectors.rss_collector import collect_rss
from src.collectors.instagram_collector import collect_instagram_sync
from src.analyzer.dedup import deduplicate_articles
from src.analyzer.topic_selector import select_topics
from src.outputs.sheets_writer import write_to_sheets
from src.outputs.discord_sender import send_to_discord
from src.logger import init_logger


def main():
    logger = init_logger()
    logger.log("=== 이슈 디스커버리 에이전트 시작 ===\n")

    # 1. 데이터 수집
    logger.log("[1/5] 데이터 수집 중...")
    rss_articles = collect_rss()
    instagram_posts_by_account = collect_instagram_sync()

    if not rss_articles and not instagram_posts_by_account:
        logger.log("수집된 데이터가 없습니다. 종료합니다.")
        logger.close()
        return

    # 2. 뉴스 중복 제거
    logger.log("\n[2/5] 뉴스 중복 제거 중...")
    rss_articles = deduplicate_articles(rss_articles)

    # 3. 3단계 AI 이슈 선정 (SNS 필터 → 뉴스 Top30 → 최종 Top10)
    logger.log("\n[3/5] AI 이슈 선정 중 (3단계)...")
    topics = select_topics(rss_articles, instagram_posts_by_account)

    if not topics:
        logger.log("선정된 이슈가 없습니다. 종료합니다.")
        logger.close()
        return

    # 4. Google Sheets 저장
    logger.log("\n[4/5] Google Sheets 저장 중...")
    write_to_sheets(topics)

    # 5. Discord 전송
    logger.log("\n[5/5] Discord 전송 중...")
    send_to_discord(topics)

    logger.log("\n=== 이슈 디스커버리 에이전트 완료 ===")
    logger.close()


if __name__ == "__main__":
    main()
