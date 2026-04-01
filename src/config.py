import os
from dotenv import load_dotenv

load_dotenv()

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Google Sheets
GOOGLE_SHEETS_CREDS = os.getenv("GOOGLE_SHEETS_CREDS", "")
SPREADSHEET_NAME = "perspective_DB"
WORKSHEET_NAME = "topic Recommender"

# Discord
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# Instagram
INSTAGRAM_SEED_ACCOUNTS = [
    acct.strip()
    for acct in os.getenv("INSTAGRAM_SEED_ACCOUNTS", "").split(",")
    if acct.strip()
]
INSTAGRAM_COOKIES = os.getenv("INSTAGRAM_COOKIES", "")

# RSS Feeds (5개 카테고리)
RSS_FEEDS = {
    "tech": [
        "https://feeds.feedburner.com/TechCrunch/",
        "https://www.theverge.com/rss/index.xml",
    ],
    "design": [
        "https://feeds.feedburner.com/fastcodesign/feed",
    ],
    "science": [
        "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml",
    ],
    "culture": [
        "https://rss.nytimes.com/services/xml/rss/nyt/Arts.xml",
    ],
    "korea": [
        "https://www.hankyung.com/feed/it",
        "https://rss.etnews.com/Section901.xml",
    ],
}

# AI 프롬프트 — 1단계: 뉴스에서 Top 30 선별
STAGE1_PROMPT = """당신은 2030세대 트렌드에 정통한 뉴스 필터입니다.

아래 뉴스 목록에서 2030세대가 관심 가질 만한 기사 Top 30을 선별하세요.

선정 기준:
1. 2030세대가 실제로 흥미를 느끼고 공유할 만한 주제인가
2. 시의성 — 지금 이 시점에 왜 주목해야 하는가
3. 기술·디자인·사용자 경험과 자연스럽게 연결될 수 있는 소재인가

제외 대상:
- 정치/외교 뉴스
- 단순 연예/가십
- 지나치게 일반적인 라이프스타일 기사 (ex. "봄맞이 다이어트 팁")

각 기사에 대해 원본 정보를 유지하되, 선정 이유를 한 줄로 추가하세요.

JSON 형식으로 출력하세요:
{"articles": [{"title": "...", "description": "...", "category": "...", "reason": "선정 이유 한 줄"}]}
"""

# AI 프롬프트 — 2단계: 뉴스 + SNS 합산 → Top 10 최종 선정
STAGE2_PROMPT = """당신은 2030세대 트렌드에 정통한 이슈 큐레이터입니다.

아래는 1차 선별된 뉴스 30건과 SNS 콘텐츠 20건입니다.
이 중에서 최종 Top 10 이슈를 선정하세요.

선정 기준 (우선순위 순):
1. 2030세대가 실제로 흥미를 느끼고 공유할 만한 주제인가
2. 시의성 — 지금 이 시점에 왜 주목해야 하는가
3. 기술·디자인·사용자 경험과 자연스럽게 연결되는 소재인가
4. 뉴스와 SNS에서 동시에 언급되는 주제는 가산점

제외 대상:
- 정치/외교 뉴스
- 단순 연예/가십
- 지나치게 일반적인 라이프스타일 기사

좋은 토픽 예시: AI 서비스 변화, 새로운 앱/플랫폼 트렌드, Z세대 소비 행태, 디지털 문화 현상, UX 논쟁, 크리에이터 이코노미 등

각 이슈에 대해:
- rank (1~10)
- topic_id (topic_XX 형식)
- canonical_title (헤드라인)
- why_now (2~3문장, 지금 왜 중요한지)
- issue_hook (2~3문장, 이 주제를 기술·디자인·사용자 경험 관점에서 어떻게 풀어볼 수 있는지)

JSON 형식으로 출력하세요:
{"topics": [{"rank": 1, "topic_id": "topic_01", "canonical_title": "...", "why_now": "...", "issue_hook": "..."}]}
"""
