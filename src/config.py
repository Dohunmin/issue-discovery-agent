import os
from dotenv import load_dotenv

load_dotenv()

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Google Sheets
GOOGLE_SHEETS_CREDS = os.getenv("GOOGLE_SHEETS_CREDS", "")
SPREADSHEET_NAME = "Perspective_DB"
WORKSHEET_NAME = "Topic Recommender"
SOURCE_STATS_WORKSHEET = "Source Stats"

# Discord
# Discord 웹훅 (쉼표로 여러 개 지정 가능)
DISCORD_WEBHOOK_URLS = [
    url.strip()
    for url in os.getenv("DISCORD_WEBHOOK_URL", "").split(",")
    if url.strip()
]

# Instagram
INSTAGRAM_SEED_ACCOUNTS = [
    acct.strip()
    for acct in os.getenv("INSTAGRAM_SEED_ACCOUNTS", "").split(",")
    if acct.strip()
]
INSTAGRAM_COOKIES = os.getenv("INSTAGRAM_COOKIES", "")
INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME", "")
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD", "")

# ─────────────────────────────────────────────
# RSS Feeds
#
# 관점: "정보시스템이 한국 사회구조·제도·일상을 어떻게 바꾸는가"
#
# 카테고리 설계:
#   ai_society  — AI·자동화가 노동·제도·조직에 미치는 영향
#   culture     — 2030 문화·라이프스타일·소비 트렌드
#   generation  — 2030이 체감하는 디지털 전환 (채용·주거·소비·교육)
#   media_info  — 정보 흐름, 미디어 생태계, 알고리즘과 여론
#   buzz        — 실시간 화제·바이럴·밈 (구글뉴스 기반)
#
# 소스 선정 기준:
#   - 한국 매체 중심
#   - RSS 피드가 공개된 매체
#   - AI 기술 뉴스뿐만 아니라 2030 생활밀착 이슈도 폭넓게 커버
# ─────────────────────────────────────────────
RSS_FEEDS = {

    # AI·디지털이 일상을 바꾸는 이슈 (산업지 톤 축소 — 블로터만 유지)
    "ai_society": [
        "https://www.bloter.net/feed",                      # 블로터 — IT 심층 분석
    ],

    # 2030 문화·라이프스타일·소비 트렌드
    "culture": [
        "https://www.hani.co.kr/rss/culture/",              # 한겨레 문화 — 문화·사회 분석
        "https://www.khan.co.kr/rss/rssdata/culture_news.xml",  # 경향 문화 — 트렌드·문화현상
        "https://www.mk.co.kr/rss/50400001/",               # 매경 라이프 — 소비·라이프스타일
        "https://uppity.co.kr/feed/",                        # 어피티 — 2030 경제·소비 트렌드
    ],

    # 2030이 직접 체감하는 디지털 전환 이슈
    "generation": [
        "https://www.hankyung.com/feed/it",                 # 한경 IT — 스타트업·채용
        "https://www.hani.co.kr/rss/science/",              # 한겨레 과학 — 기술과 사회 접점
        "https://www.khan.co.kr/rss/rssdata/it_news.xml",   # 경향 IT — 기술 사회적 맥락
    ],

    # 미디어 생태계·정보 흐름 (산업지 톤 축소 — 슬로우뉴스만 유지)
    "media_info": [
        "https://slownews.kr/feed",                         # 슬로우뉴스 — 미디어 비평
    ],

    # 실시간 화제·바이럴·밈 (구글뉴스 — 쿼리 세분화, 비중 확대)
    "buzz": [
        "https://news.google.com/rss/search?q=화제+OR+논란+OR+밈+OR+챌린지+OR+바이럴&hl=ko&gl=KR&ceid=KR:ko",
        "https://news.google.com/rss/search?q=청년+취업+OR+부동산+OR+전세사기+OR+소비+트렌드&hl=ko&gl=KR&ceid=KR:ko",
        "https://news.google.com/rss/search?q=틱톡+OR+인스타+OR+유튜브+OR+숏폼+OR+챌린지+화제&hl=ko&gl=KR&ceid=KR:ko",
        "https://news.google.com/rss/search?q=Z세대+OR+잘파세대+OR+MZ+화제&hl=ko&gl=KR&ceid=KR:ko",
        "https://news.google.com/rss/search?q=요즘+유행+OR+신조어+OR+핫플+OR+오픈런&hl=ko&gl=KR&ceid=KR:ko",
        "https://news.google.com/rss/search?q=데이팅앱+OR+연애+OR+결혼+트렌드&hl=ko&gl=KR&ceid=KR:ko",
        "https://news.google.com/rss/search?q=K콘텐츠+OR+한드+OR+예능+화제&hl=ko&gl=KR&ceid=KR:ko",
    ],

}

# Google Trends 한국 — Stage 1 소스가 아니라, 뉴스 교차 태깅 전용
GOOGLE_TRENDS_RSS = "https://trends.google.com/trending/rss?geo=KR"

# YouTube — 인스타처럼 시드 채널 기반 수집
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
YOUTUBE_SEED_CHANNELS = [
    ch.strip()
    for ch in os.getenv("YOUTUBE_SEED_CHANNELS", "").split(",")
    if ch.strip()
]


# ─────────────────────────────────────────────
# AI 프롬프트
# ─────────────────────────────────────────────

# SNS 필터: 계정당 7개 → 3개 선별
SNS_FILTER_PROMPT = """당신은 2030세대 트렌드 분석가입니다.

아래는 인스타그램 계정 하나에서 수집한 최근 게시물 캡션입니다.
이 중에서 2030세대 이슈/트렌드로서 가치가 높은 게시물 3개를 선정하세요.

선정 기준:
1. 특정 사건·현상·논란을 다루고 있는가 (예: "가짜 배민 앱 논란", "쉬었음 청년 밈")
2. "무엇이 화제인가"를 하나의 키워드나 문장으로 특정할 수 있는가
3. 캡션에 분석할 만한 구체적 맥락이 있는가

제외 대상 (절대 선택하지 마세요):
- #광고, #ad, #협찬, #sponsored 태그가 있는 게시물
- 특정 브랜드·서비스를 홍보하는 광고성 게시물 (제품 리뷰, 할인 코드, 이벤트 안내 등)
- 단순 제품 소개·사용 후기
- "요즘 트렌드 모음", "이번 주 뉴스 정리" 같은 포괄적 큐레이션 (구체적 이슈 하나로 특정 불가)

광고를 제외하고 3개를 채울 수 없으면, 가능한 만큼만 선택하세요.

JSON 형식으로 출력하세요:
{"selected": [0, 2, 5]}

숫자는 아래 게시물 목록의 인덱스(0부터)입니다.
"""

# 1단계: 전체 뉴스·YouTube → 5차원 채점 → Top 30 선별
STAGE1_PROMPT = """당신은 한국 2030세대의 삶에 영향을 미치는 이슈를 채점하는 필터입니다.
"기술 산업 뉴스"가 아니라 "기술·플랫폼·문화가 일상을 바꾸는 순간"에 주목합니다.

아래 후보들을 5차원으로 채점하고, 총점 상위 30개를 선정하여 반환하세요.

채점 기준 (각 1~3점, 합계 최대 15점):
| 차원    | 1점              | 2점          | 3점                    |
|---------|-----------------|-------------|------------------------|
| 체감도  | 2030 관련 약함  | 간접 관련   | 직접 체감              |
| 소재력  | 관심 낮음       | 알면 좋음   | 안 알면 뒤처짐         |
| 확산성  | 확산 안됨       | 일부 공유   | 밈/짤/챌린지 가능      |
| 구체성  | 포괄적 트렌드   | 특정 현상   | 특정 사건+날짜         |
| 시의성  | 상시 주제       | 이번 주     | 오늘~어제              |

소스별 특징:
- 뉴스: 언론 보도 기반. [TRENDING] 태그가 붙은 기사는 Google Trends 인기 검색어와 매칭된 기사
- YouTube 채널: 2030 이슈/트렌드를 다루는 채널의 최근 영상 (최소 3개 이상 반드시 포함)

제외 대상 (점수 부여 금지, 선정 금지):
- 정치/외교 뉴스 (IT정책은 포함 가능)
- 단순 연예/가십
- 특정 기업의 제품 출시·MOU·파트너십 보도
- 해외 빅테크 동향 (구글/MS/오픈AI 신제품, 분기 실적)
- B2B 기업 간 기술 협약·클라우드 계약
- 양자컴퓨팅·반도체 공정 등 일반인이 체감하지 못하는 기술 이슈
- 학술 논문·컨퍼런스 발표 소식
- 기업 주가·실적 단신

중요:
- title은 원문 제목을 **절대 수정하지 말고 그대로** 사용하세요
- source_ref는 원래 소스 번호 그대로 (예: "뉴스#3", "유튜브#5")
- total은 반드시 다섯 점수의 합계
- **정확히 30개 반환**

JSON 형식으로 출력하세요:
{"articles": [{"title": "원문 그대로", "description": "한 줄 요약", "category": "buzz", "source_ref": "뉴스#1", "scores": {"체감도": 2, "소재력": 3, "확산성": 2, "구체성": 3, "시의성": 2, "total": 12}}]}
"""

# 2단계-A: SNS 후보 5차원 채점
STAGE2_SNS_SCORE_PROMPT = """아래 인스타그램 게시물들을 5차원으로 채점하세요.

채점 기준 (각 1~3점, 합계 최대 15점):
| 차원    | 1점              | 2점          | 3점                    |
|---------|-----------------|-------------|------------------------|
| 체감도  | 2030 관련 약함  | 간접 관련   | 직접 체감              |
| 소재력  | 관심 낮음       | 알면 좋음   | 안 알면 뒤처짐         |
| 확산성  | 확산 안됨       | 일부 공유   | 밈/짤/챌린지 가능      |
| 구체성  | 포괄적 트렌드   | 특정 현상   | 특정 사건+날짜         |
| 시의성  | 상시 주제       | 이번 주     | 오늘~어제              |

index는 입력 게시물의 번호(0부터)입니다. 모든 게시물에 점수를 매기세요.
total은 반드시 다섯 점수의 합계입니다.

JSON 형식으로 출력하세요:
{"scores": [{"index": 0, "scores": {"체감도": 2, "소재력": 3, "확산성": 2, "구체성": 2, "시의성": 2, "total": 11}}]}
"""

# 2단계-B: Top 10 내용 보강 (선정 결과는 코드에서 결정, LLM은 보강만 담당)
STAGE2_ENRICH_PROMPT = """아래는 [5차원 채점 50% + 취향 벡터 50%] 결합 점수로 이미 선정된 Top 10 이슈입니다.
선정 결과는 변경하지 마세요. 각 이슈에 대한 설명만 작성하세요.

각 이슈에 대해:
- original_title
  - 뉴스·YouTube 출처: 원문 제목을 **절대 수정하지 말고 그대로** 사용
  - SNS 출처: 캡션이 다루는 이슈/사건을 **검색 가능한 키워드 문장**으로 작성
- source_ref: 입력에 표시된 출처 번호 그대로 (예: "뉴스#3", "SNS#2")
- why_now: 지금 왜 한국에서 중요한지 2~3문장
- issue_hook: 디지털 문화·플랫폼·사회 변화 관점에서 어떻게 풀어볼 수 있는지 2~3문장

JSON 형식으로 출력하세요:
{"topics": [{"index": 1, "original_title": "...", "source_ref": "뉴스#1", "why_now": "...", "issue_hook": "..."}]}
"""

# 하위 호환: 기존 STAGE2_PROMPT 참조를 위한 별칭 (미사용)
STAGE2_PROMPT = STAGE2_ENRICH_PROMPT

# 모델 자체 판단 Top 3 (취향 정보 없이 순수 프롬프트 기준)
MODEL_PICKS_PROMPT = """당신은 한국 2030세대가 오늘 카톡/인스타에서 이야기할 주제를 선정하는 큐레이터입니다.

아래는 1차 선별된 뉴스와 SNS 콘텐츠입니다.
이 중에서 당신이 가장 자신 있게 추천하는 Top 3 이슈를 선정하세요.

선정 기준:
1. 카톡 단톡방 테스트: 2030 직장인이 점심시간에 공유할 만한 주제인가?
2. 밈화 가능성: 짤/패러디/챌린지로 퍼질 수 있는 요소가 있는가?
3. 체감 변화: 나의 소비·취업·주거·여가에 직접 영향을 주는가?
4. 논쟁성: 찬반이 갈리거나 "이게 맞아?" 반응이 나오는가?
5. 구체성: 하나의 구체적 사건·현상으로 특정 가능한가?

제외 대상:
- 정치/외교 뉴스, 단순 연예/가십
- 기업 제품 출시·MOU·파트너십 보도
- 해외 빅테크 동향, B2B 뉴스
- 포괄적 트렌드 모음

각 이슈에 대해:
- rank (1~3)
- original_title: 원문 제목 그대로 (SNS는 검색 가능한 키워드 문장)
- source_ref: 원문 출처 번호
- why_now (1~2문장)

JSON 형식으로 출력하세요:
{"topics": [{"rank": 1, "original_title": "...", "source_ref": "뉴스#1", "why_now": "..."}]}
"""
