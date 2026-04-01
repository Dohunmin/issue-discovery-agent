# 뉴스 + SNS 기반 이슈 디스커버리 에이전트

## Context
기존 n8n 워크플로우가 RSS 뉴스만으로 이슈를 수집하고 있어 2030 타겟의 SNS 트렌드를 놓치는 문제가 있음.
n8n을 걷어내고 Python 코드 기반으로 전환하면서, 인스타그램 크롤링을 추가해 토픽 품질을 높이려는 프로젝트.

## 기술 스택
- **언어**: Python 3.11+
- **AI**: OpenAI GPT-4o (또는 그 이상 모델)
- **인스타 크롤링**: Playwright (headless browser)
- **RSS 파싱**: feedparser
- **DB**: Google Sheets (gspread + google-auth)
- **알림**: Discord Webhook
- **배포**: GitHub Actions (cron: 매일 09:00 KST = 00:00 UTC)
- **스케줄링**: GitHub Actions scheduled workflow

## 프로젝트 구조
```
issue-discovery-agent/
├── .github/
│   └── workflows/
│       └── daily-run.yml          # GitHub Actions cron workflow
├── src/
│   ├── __init__.py
│   ├── main.py                    # 엔트리포인트 (오케스트레이터)
│   ├── collectors/
│   │   ├── __init__.py
│   │   ├── rss_collector.py       # RSS 뉴스 수집
│   │   └── instagram_collector.py # 인스타그램 크롤링
│   ├── analyzer/
│   │   ├── __init__.py
│   │   └── topic_selector.py      # Gemini 기반 이슈 선정
│   ├── outputs/
│   │   ├── __init__.py
│   │   ├── sheets_writer.py       # Google Sheets 저장
│   │   └── discord_sender.py      # Discord 웹훅 전송
│   └── config.py                  # 설정 (RSS URL, 계정, 프롬프트 등)
├── requirements.txt
└── README.md
```

## 파이프라인 흐름

```
[매일 00:00 UTC / 09:00 KST]
        │
        ▼
┌─────────────────────────────────────┐
│  1. 데이터 수집 (병렬)               │
│  ├─ RSS Collector: 5개 카테고리 피드  │
│  └─ Instagram Collector:            │
│     ├─ 시드 계정 3~5개 최근 게시물    │
│     └─ 트렌딩 해시태그 탐색          │
└─────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────┐
│  2. 데이터 정규화                    │
│  - 제목, 본문, 소스, 타임스탬프 통일  │
│  - 중복 제거 (유사도 기반)           │
└─────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────┐
│  3. AI 이슈 선정 (Gemini 2.0 Flash) │
│  - HCI 연결성 평가                   │
│  - 시의성 판단                       │
│  - 2030 흥미도 스코어링              │
│  - Top 5 선별 + why_now, issue_hook │
└─────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────┐
│  4. 출력 (병렬)                      │
│  ├─ Google Sheets 저장               │
│  │   (perspective_DB > topic         │
│  │    Recommender 시트)              │
│  └─ Discord Webhook 전송            │
└─────────────────────────────────────┘
```

## 모듈별 상세 설계

### 1. RSS Collector (`rss_collector.py`)
- feedparser로 5개 카테고리 RSS 피드 파싱
- 최근 24시간 내 기사만 필터링
- 출력: `[{title, description, source, url, published_at, category}]`

### 2. Instagram Collector (`instagram_collector.py`)
- **Playwright headless Chrome** 사용
- **시드 계정 수집**: 사용자가 지정한 **3개 계정** 프로필 방문 → 최근 게시물의 캡션 수집 (좋아요/댓글 수는 참조 지표로만 활용)
- **해시태그 탐색**: AI가 현재 시점에 탐색할 만한 해시태그 3~5개 제안 → 해당 해시태그 페이지의 인기 게시물 수집
- 핵심은 캡션 텍스트에서 **시의적 이슈를 판단**하는 것 (단순 인기 지표 X)
- 로그인 없이 공개 프로필/해시태그만 접근 (로그인 필요시 쿠키 기반)
- 출력: `[{caption, likes(참조), comments(참조), account, hashtags, posted_at}]`
- **주의**: 인스타 로그인 없이 접근 가능한 범위가 제한적 → 필요시 세션 쿠키를 GitHub Secrets에 저장

### 3. Topic Selector (`topic_selector.py`)
- OpenAI GPT-4o API 호출
- 프롬프트 구조:
  ```
  당신은 HCI 전공 대학원생 관점의 이슈 큐레이터입니다.

  아래 수집된 뉴스와 SNS 데이터를 분석하여 Top 5 이슈를 선정하세요.

  선정 기준:
  1. HCI(Human-Computer Interaction)와의 연결성
  2. 시의성 (지금 왜 중요한지)
  3. 2030세대의 흥미도

  각 이슈에 대해:
  - rank (1~5)
  - topic_id (topic_XX 형식)
  - canonical_title (헤드라인)
  - why_now (2~3문장)
  - issue_hook (2~3문장, HCI 관점 분석 포인트 포함)

  JSON 형식으로 출력하세요.
  ```
- 출력: 기존 Google Sheets 스키마와 동일한 구조

### 4. Sheets Writer (`sheets_writer.py`)
- gspread + google-auth (서비스 계정)
- `perspective_DB` 스프레드시트의 `topic Recommender` 시트에 append
- 컬럼: `rank, topic_id, canonical_title, why_now, issue_hook`
- 날짜별 구분을 위해 `date` 컬럼 추가 고려

### 5. Discord Sender (`discord_sender.py`)
- Discord Webhook URL로 POST
- 기존 포맷 유지:
  ```
  **{canonical_title}**

  **why_now:** {why_now}
  **issue_hook:** {issue_hook}
  ```
- 5개 토픽을 하나의 메시지 or embed로 전송

### 6. GitHub Actions Workflow (`daily-run.yml`)
```yaml
name: Daily Issue Discovery
on:
  schedule:
    - cron: '0 0 * * *'  # 00:00 UTC = 09:00 KST
  workflow_dispatch: # 수동 실행 가능

jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          playwright install chromium
      - name: Run agent
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          GOOGLE_SHEETS_CREDS: ${{ secrets.GOOGLE_SHEETS_CREDS }}
          DISCORD_WEBHOOK_URL: ${{ secrets.DISCORD_WEBHOOK_URL }}
          INSTAGRAM_SEED_ACCOUNTS: ${{ secrets.INSTAGRAM_SEED_ACCOUNTS }}
        run: python -m src.main
```

## 필요한 Secrets (GitHub)
- `OPENAI_API_KEY`: OpenAI API 키
- `GOOGLE_SHEETS_CREDS`: 서비스 계정 JSON (base64 인코딩)
- `DISCORD_WEBHOOK_URL`: 디스코드 채널 웹훅 URL
- `INSTAGRAM_SEED_ACCOUNTS`: 시드 계정 목록 (쉼표 구분)
- `INSTAGRAM_COOKIES` (선택): 인스타 로그인 세션 쿠키

## 비용 예상
- **OpenAI GPT-4o**: 입력 $2.50/1M, 출력 $10/1M 토큰. 일 1회 호출 기준 월 ~$1~3
- **GitHub Actions**: 무료 티어 월 2000분, 일 1회 실행 ~5분 = 월 150분
- **총 예상 비용: 월 $1 ~ $5 이하**

## 구현 순서
1. `config.py` - RSS URL, 시드 계정, 프롬프트 등 설정
2. `rss_collector.py` - RSS 수집 모듈
3. `instagram_collector.py` - 인스타 크롤링 모듈 (Playwright)
4. `topic_selector.py` - Gemini 기반 이슈 선정
5. `sheets_writer.py` - Google Sheets 저장
6. `discord_sender.py` - Discord 전송
7. `main.py` - 오케스트레이터
8. `daily-run.yml` - GitHub Actions 워크플로우
9. 테스트 및 디버깅

## 검증 방법
1. 로컬에서 `python -m src.main` 실행하여 전체 파이프라인 동작 확인
2. Google Sheets에 데이터가 올바른 형식으로 저장되는지 확인
3. Discord에 메시지가 기존 포맷과 동일하게 오는지 확인
4. GitHub Actions에서 수동 트리거(workflow_dispatch)로 실행 확인
5. 인스타그램 크롤링이 GitHub Actions 환경에서 정상 동작하는지 확인
