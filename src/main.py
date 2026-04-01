"""이슈 디스커버리 에이전트 - 엔트리포인트"""

from src.collectors.rss_collector import collect_rss
from src.collectors.instagram_collector import collect_instagram_sync
from src.analyzer.dedup import deduplicate_articles
from src.analyzer.topic_selector import select_topics
from src.outputs.sheets_writer import write_to_sheets
from src.outputs.discord_sender import send_to_discord


def main():
    print("=== 이슈 디스커버리 에이전트 시작 ===\n")

    # 1. 데이터 수집
    print("[1/5] 데이터 수집 중...")
    rss_articles = collect_rss()
    instagram_posts = collect_instagram_sync()

    if not rss_articles and not instagram_posts:
        print("수집된 데이터가 없습니다. 종료합니다.")
        return

    # 2. 뉴스 중복 제거
    print("\n[2/5] 뉴스 중복 제거 중...")
    rss_articles = deduplicate_articles(rss_articles)

    # 3. 2단계 AI 이슈 선정
    print("\n[3/5] AI 이슈 선정 중 (2단계)...")
    topics = select_topics(rss_articles, instagram_posts)

    if not topics:
        print("선정된 이슈가 없습니다. 종료합니다.")
        return

    # 4. Google Sheets 저장
    print("\n[4/5] Google Sheets 저장 중...")
    write_to_sheets(topics)

    # 5. Discord 전송
    print("\n[5/5] Discord 전송 중...")
    send_to_discord(topics)

    print("\n=== 이슈 디스커버리 에이전트 완료 ===")


if __name__ == "__main__":
    main()
