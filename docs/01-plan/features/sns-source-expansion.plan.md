# Plan: SNS 소스 확장 (sns-source-expansion)

**Phase**: Plan
**Created**: 2026-04-03
**Status**: Draft

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 인스타 3계정 의존으로 콘텐츠 반복, 실시간 트렌드 미포착, 이슈 다양성 부족 |
| **Solution** | YouTube 트렌딩 + DC인사이드 실베 + 네이트판 실시간 인기 추가, Google Trends는 뉴스 태깅용 |
| **Function UX Effect** | Discord에 전달되는 Top 10 이슈가 "오늘 실제로 화제인 것"과 일치하고, 매일 새로운 이슈가 등장 |
| **Core Value** | 운영자가 결과를 보고 "이건 맞아"라고 느끼는 비율을 높임 |

## Context Anchor

| 축 | 내용 |
|----|------|
| **WHY** | 인스타 3계정만으로는 하루가 지나도 같은 게시물이 반복되고, 뉴스 RSS만으로는 실시간 바이럴/밈을 포착하지 못함 |
| **WHO** | 한국 2030세대 이슈에 관심 있는 운영자 (1인) |
| **RISK** | 스크래핑 소스(DC, 네이트판)의 봇 차단/구조 변경, GitHub Actions CI 타임아웃, AI 프롬프트 토큰 초과 |
| **SUCCESS** | 매일 Top 10 중 70%+ 이상이 "오늘 화제"와 일치, 전일 대비 80%+ 이슈가 갱신 |
| **SCOPE** | YouTube + DC실베 + 네이트판 수집기 추가, Google Trends RSS 태깅, 인스타는 계정 추가만으로 확장 가능하도록 유지 |

---

## 1. 현재 상태 (As-Is)

### 데이터 소스
| 소스 | 수량 | 실시간성 | 문제 |
|------|------|---------|------|
| RSS 뉴스 | 14개 피드, 5개 카테고리 | 중간 (24h 윈도우) | 언론 보도 후에만 포착 |
| Instagram | 3개 계정, 계정당 5개 게시물 | 낮음 | 업로드 안 하면 동일 게시물 반복 |

### 파이프라인
```
RSS (24h) + Instagram (최근 5개)
  → 중복 제거
  → SNS 필터 (계정당 2~3개)
  → Stage 1: 뉴스 Top 30 (GPT)
  → 취향 점수 부여 (임베딩)
  → Stage 2: 최종 Top 10 (GPT)
  → Google Sheets + Discord
```

### 핵심 문제
1. 인스타 계정이 하루에 안 올리면 어제와 같은 게시물 반복
2. 밈/챌린지/바이럴이 뉴스화되기 전에 포착 불가
3. "지금 뜨고 있는" 정량적 신호 없음 (시의성을 AI 프롬프트에만 의존)

---

## 2. 목표 상태 (To-Be)

### 데이터 소스
| 소스 | 수량 | 실시간성 | 역할 |
|------|------|---------|------|
| RSS 뉴스 | 14개 피드 (기존) | 중간 | 언론 보도 기반 이슈 |
| Instagram | 10개 계정 (확대) | 낮음→중간 | 2030 SNS 큐레이션 |
| **Google Trends RSS** | 1개 피드 (신규) | **높음** | 실시간 검색 트렌드 |
| **YouTube 트렌딩** | API 1회 호출 (신규) | **중간** | 밈/챌린지/논란 영상 |
| **DC인사이드 실베** | 스크래핑 (신규) | **높음** | 커뮤니티 여론, 밈 원산지 |
| **X 트렌딩** | trends24 스크래핑 (선택) | **매우 높음** | 실시간 바이럴/논란 |

### 파이프라인 변경
```
RSS + Instagram + Google Trends + YouTube + DC실베 + (X 트렌딩)
  → 소스별 중복 제거
  → 교차 태깅: 여러 소스에서 동시 출현 시 [TRENDING] 태그
  → SNS 필터 (인스타만)
  → Stage 1: 전체 → Top 30 (모든 소스 포함)
  → 취향 점수 부여
  → Stage 2A: 취향 반영 Top 10
  → Stage 2B: 모델 자체 Top 3 (비교용)
  → Google Sheets + Discord
```

---

## 3. 구현 단계 (Phase별 우선순위)

### Phase 1: 즉시 (코드 변경 최소)

#### 3-1. Google Trends RSS 추가
- **작업**: `config.py`의 `RSS_FEEDS`에 URL 1줄 추가
- **URL**: `https://trends.google.com/trending/rss?geo=KR`
- **카테고리**: `realtime_trend`
- **난이도**: 매우 낮음 (config 수정만)
- **효과**: 실시간 검색 트렌드가 Stage 1 입력에 자동 포함
- **추가 의존성**: 없음 (feedparser 이미 사용 중)

#### 3-2. 인스타 계정 확대 (3 → 10개)
- **작업**: `INSTAGRAM_SEED_ACCOUNTS` 환경변수에 계정 추가
- **추가 계정 유형**:
  - 뉴스/큐레이션: newneek, uppitykr, dotface_official 등 (매일 포스팅)
  - 밈/바이럴: 밈 아카이브 계정
  - 2030 라이프스타일: careet.official 등
- **POSTS_TO_SCAN**: 5 → 3으로 축소 (계정 수 증가에 따른 시간 절약)
- **추가 작업**: URL 기반 인스타 중복 게시물 제거 로직

### Phase 2: 단기 (1~2일)

#### 3-3. YouTube 트렌딩 수집기
- **신규 파일**: `src/collectors/youtube_collector.py`
- **API**: YouTube Data API v3 `videos.list(chart=mostPopular, regionCode=KR)`
- **비용**: 무료 (일일 쿼터 10,000 유닛 중 3유닛 소모)
- **필터**: Music(10) 카테고리 제외
- **반환 데이터**: 제목, 설명, 태그, 조회수, 채널명
- **환경변수**: `YOUTUBE_API_KEY` (Google Cloud Console에서 발급)
- **의존성**: `google-api-python-client` (requirements.txt 추가)

#### 3-4. DC인사이드 실시간 베스트 수집기
- **신규 파일**: `src/collectors/community_collector.py`
- **방식**: `requests` + `BeautifulSoup`으로 실베 제목+추천수 파싱
- **수집 범위**: 제목 + 추천수만 (본문 수집 X → 부하/리스크 최소화)
- **봇 대응**: User-Agent 랜덤화, 요청 간격 5초+
- **의존성**: `beautifulsoup4` (requirements.txt 추가)
- **주의**: Playwright 불필요 (requests만으로 접근 가능)

### Phase 3: 선택 (예산/안정성 확보 후)

#### 3-5. X(트위터) 트렌딩
- **방안 A (무료)**: trends24.in/korea 스크래핑 (Playwright 재활용)
- **방안 B (무료, 유지보수 필요)**: twikit 라이브러리
- **방안 C ($200/월)**: 공식 API Basic (검색만, 트렌딩 불가)
- **권장**: 방안 A → 안정화 후 방안 C로 전환 검토

---

## 4. 파이프라인 통합 설계

### 4-1. main.py 변경
```python
# 현재
rss_articles = collect_rss()
instagram_posts = collect_instagram_sync()

# 변경
rss_articles = collect_rss()            # Google Trends RSS 자동 포함
instagram_posts = collect_instagram_sync()
youtube_videos = collect_youtube_trending()  # 신규
community_posts = collect_community()        # 신규 (DC실베)
```

### 4-2. select_topics() 확장
- YouTube + DC실베 데이터를 Stage 1 입력에 새 카테고리로 추가
- 교차 출현 감지: 같은 키워드가 뉴스+트렌드+커뮤니티에 동시 출현 시 `[TRENDING]` 태그
- STAGE1_PROMPT / STAGE2_PROMPT에 새 소스 유형 설명 추가

### 4-3. 프롬프트 수정 포인트
- Stage 1: YouTube/커뮤니티 카테고리 설명 추가
- Stage 2: "[TRENDING] 태그는 여러 소스에서 동시 출현한 이슈 → 동일 점수 시 우선 선정"

---

## 5. 환경변수 및 시크릿

| 변수 | Phase | 필수 여부 | 설명 |
|------|-------|----------|------|
| `INSTAGRAM_SEED_ACCOUNTS` | 1 | 기존 확장 | 10개 계정으로 확대 |
| `YOUTUBE_API_KEY` | 2 | 선택 | Google Cloud API 키 |
| `X_USERNAME` / `X_PASSWORD` | 3 | 선택 | twikit 사용 시 |

---

## 6. 리스크 및 대응

| 리스크 | 영향 | 대응 |
|--------|------|------|
| Instagram 봇 차단 (계정 10개) | 수집 실패 | graceful degradation: 인스타 실패 시 다른 소스만으로 진행 |
| DC인사이드 HTML 구조 변경 | 파싱 실패 | 셀렉터 기반 파싱 + 실패 시 빈 리스트 반환 |
| YouTube API 쿼터 초과 | 수집 불가 | 일일 3유닛이므로 사실상 불가. 모니터링만 |
| GitHub Actions 실행 시간 초과 | 전체 실패 | 소스별 타임아웃 설정, 실패한 소스 스킵 |
| AI 프롬프트 토큰 초과 | Stage 2 실패 | 입력 텍스트 총량 제한 (소스별 상한선) |
| trends24 구조 변경 | X 트렌딩 실패 | Phase 3 선택사항이므로 영향 최소 |

---

## 7. 성공 기준

| 기준 | 측정 방법 | 목표 |
|------|----------|------|
| 이슈 갱신율 | 전일 Top 10 대비 신규 이슈 비율 | 80%+ |
| 운영자 만족도 | Sheets rating "good" 비율 | 70%+ |
| 실시간 화제 포착 | Google Trends 키워드와 Top 10 교집합 | 3개+ |
| 소스 다양성 | Top 10 내 2개 이상 소스 유형 포함 | 상시 |
| CI 실행 안정성 | 연속 성공 실행 비율 | 95%+ |

---

## 8. 일정 (예상)

| 단계 | 작업 | 소요 |
|------|------|------|
| Phase 1 | Google Trends RSS + 인스타 확대 + 중복 제거 | 반나절 |
| Phase 2 | YouTube 수집기 + DC실베 수집기 + 파이프라인 통합 | 1~2일 |
| Phase 3 | X 트렌딩 (선택) | 1일 |
| 튜닝 | 프롬프트 조정, 결과 모니터링, 취향 벡터 보강 | 지속 |
