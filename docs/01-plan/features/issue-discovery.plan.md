# Plan: Issue Discovery Agent

> **Feature**: issue-discovery
> **Created**: 2026-04-01
> **Status**: Draft
> **Level**: Dynamic

---

## Executive Summary

| 항목 | 내용 |
|------|------|
| **Feature** | 뉴스 + SNS 기반 이슈 디스커버리 에이전트 |
| **Created** | 2026-04-01 |
| **Estimated Duration** | 구현 완료 상태, 안정화/개선 단계 |

### Value Delivered

| 관점 | 내용 |
|------|------|
| **Problem** | 기존 n8n 워크플로우가 RSS 뉴스만 수집하여 2030 타겟의 SNS 트렌드를 놓치고 있음 |
| **Solution** | Python 기반 에이전트로 전환 + Instagram 캡션 크롤링 추가로 뉴스+SNS 교차 분석 |
| **Function UX Effect** | 매일 09:00 KST 자동 실행, Google Sheets + Discord로 Top 10 이슈 큐레이션 제공 |
| **Core Value** | 정보시스템 관점에서 한국 사회 변화를 읽는 고품질 이슈 디스커버리 자동화 |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | n8n RSS-only 워크플로우의 SNS 트렌드 사각지대 해소 |
| **WHO** | 2030세대 타겟, HCI/정보시스템 관점 큐레이터 |
| **RISK** | Instagram 크롤링 불안정성 (DOM 변경, 로그인 차단), API 비용 |
| **SUCCESS** | 매일 안정적으로 Top 10 이슈 생성, Discord+Sheets 정상 출력, 에러 시 알림 |
| **SCOPE** | RSS 수집 + Instagram 시드계정 크롤링 + GPT-4o 3단계 필터링 + Sheets/Discord 출력 |

---

## 1. Background & Problem

### 1.1 현재 상황
- n8n 워크플로우로 RSS 뉴스만 수집하여 이슈 추천 운영 중
- 2030세대가 소비하는 SNS(Instagram) 트렌드가 반영되지 않아 토픽 품질이 제한적
- n8n의 유지보수 한계 (커스텀 로직 추가 어려움)

### 1.2 해결 목표
- Python 코드 기반으로 전환하여 유연한 확장 가능
- Instagram 시드 계정 크롤링을 추가하여 SNS 시그널 반영
- GPT-4o 기반 3단계 필터링으로 토픽 선정 품질 향상
- 에러 발생 시 Discord 알림으로 운영 안정성 확보

---

## 2. Requirements

### 2.1 Functional Requirements

| ID | 요구사항 | 우선순위 |
|----|---------|---------|
| FR-01 | RSS 5개 카테고리(8개 매체)에서 최근 24시간 뉴스 수집 | Must |
| FR-02 | Instagram 시드 계정(3~5개)에서 최근 게시물 캡션 수집 (Playwright) | Must |
| FR-03 | 제목 유사도 기반 뉴스 중복 제거 (60% threshold) | Must |
| FR-04 | GPT-4o 3단계 필터링: SNS필터(계정당 7→3) → Top30 → Top10 | Must |
| FR-05 | Google Sheets (`perspective_DB` > `topic Recommender`)에 결과 저장 | Must |
| FR-06 | Discord 웹훅으로 Top 10 이슈 전송 | Must |
| FR-07 | GitHub Actions 매일 00:00 UTC (09:00 KST) 자동 실행 | Must |
| FR-08 | 에러 발생 시 Discord에 에러 알림 전송 | Should |
| FR-09 | Instagram 로그인 실패 시 graceful degradation (뉴스만으로 진행) | Should |

### 2.2 Non-Functional Requirements

| ID | 요구사항 | 기준 |
|----|---------|------|
| NFR-01 | 전체 파이프라인 실행 시간 | < 10분 (GitHub Actions 환경) |
| NFR-02 | 월간 운영 비용 | $1~5 이하 |
| NFR-03 | Secrets 관리 | GitHub Secrets로 안전하게 관리 |
| NFR-04 | Instagram 크롤링 안정성 | 쿠키+계정 로그인 기반, 실패 시 skip |

---

## 3. Scope

### 3.1 In Scope
- RSS 뉴스 수집 (feedparser, 5개 카테고리)
- Instagram 시드 계정 캡션 크롤링 (Playwright headless)
- GPT-4o 기반 3단계 AI 필터링
- Google Sheets 저장 (gspread)
- Discord 웹훅 전송 (일반 + 에러 알림)
- GitHub Actions cron 스케줄링
- Instagram 쿠키/계정 기반 로그인

### 3.2 Out of Scope
- ~~해시태그 탐색 기능~~ (향후 확장 가능)
- SNS 게시물 중복 제거 (뉴스만 적용)
- 다른 SNS 플랫폼 (X/Twitter, TikTok 등)
- 웹 UI / 대시보드
- 단위 테스트 / E2E 테스트

---

## 4. Architecture Overview

```
[GitHub Actions Cron 09:00 KST]
        │
        ▼
┌─────────────────────────────────┐
│  main.py (Orchestrator)         │
│                                 │
│  Step 1: Data Collection        │
│  ├─ rss_collector.py            │
│  └─ instagram_collector.py      │
│                                 │
│  Step 2: Deduplication          │
│  └─ dedup.py                    │
│                                 │
│  Step 3: AI Topic Selection     │
│  └─ topic_selector.py (GPT-4o) │
│    ├─ SNS Filter (7→3/account)  │
│    ├─ Stage 1 (News → Top 30)  │
│    └─ Stage 2 (News+SNS → Top10)│
│                                 │
│  Step 4: Google Sheets Write    │
│  └─ sheets_writer.py            │
│                                 │
│  Step 5: Discord Notification   │
│  └─ discord_sender.py           │
│    ├─ 일반: Top 10 이슈 전송    │
│    └─ 에러: 에러 알림 전송      │
└─────────────────────────────────┘
```

---

## 5. Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Language | Python 3.11+ | 메인 런타임 |
| AI/LLM | OpenAI GPT-4o | 3단계 이슈 필터링 |
| Web Scraping | Playwright | Instagram headless 크롤링 |
| RSS Parsing | feedparser | RSS 피드 수집 |
| Storage | Google Sheets (gspread + google-auth) | 결과 저장 |
| Notification | Discord Webhook (requests) | 이슈 전송 + 에러 알림 |
| Environment | python-dotenv | 로컬 환경 변수 |
| CI/CD | GitHub Actions | cron 스케줄링 |

---

## 6. Data Flow

### 6.1 Input Sources

**RSS Feeds (5 categories)**:
| 카테고리 | 소스 | 관점 |
|----------|------|------|
| ai_society | AI타임스, 블로터, 테크M | AI·자동화가 노동·제도를 바꾸는 이슈 |
| platform | 블로터, ZDNet, 전자신문 | 플랫폼 권력, 데이터 주권, 규제 |
| generation | 한경IT, 매일경제, 구글뉴스 | 2030 체감 디지털 전환 |
| deeptech | 전자신문, ZDNet, AI타임스 | 반도체·클라우드·보안 인프라 |
| media_info | 슬로우뉴스, 블로터, 테크M | 알고리즘·미디어 생태계 |

**Instagram**: 시드 계정 3~5개, 계정당 최근 7개 게시물 → AI로 3개 선별

### 6.2 Output Schema

```json
{
  "rank": 1,
  "topic_id": "topic_01",
  "original_title": "원문 제목",
  "source_ref": "뉴스#1",
  "why_now": "지금 왜 중요한지 2~3문장",
  "issue_hook": "정보시스템 관점 분석 포인트 2~3문장"
}
```

---

## 7. Module Design

### 7.1 `config.py` — 설정
- 환경 변수 로딩 (API 키, 자격증명)
- RSS 피드 URL 매핑 (5개 카테고리)
- AI 프롬프트 (SNS_FILTER, STAGE1, STAGE2)
- Instagram 시드 계정 설정

### 7.2 `collectors/rss_collector.py` — RSS 수집
- feedparser로 5개 카테고리 RSS 파싱
- 최근 24시간 기사만 필터링
- Output: `[{title, description, source, url, published_at, category}]`

### 7.3 `collectors/instagram_collector.py` — Instagram 크롤링
- Playwright headless Chrome
- 쿠키 기반 세션 유지 또는 계정 로그인
- 시드 계정별 최근 게시물 캡션 수집
- 로그인 실패 시 graceful degradation
- Output: `{account: [{caption, likes, comments, hashtags, posted_at}]}`

### 7.4 `analyzer/dedup.py` — 중복 제거
- 뉴스 제목 유사도 비교 (60% threshold)
- 중복 기사 제거 후 유니크 기사 반환

### 7.5 `analyzer/topic_selector.py` — AI 이슈 선정
- **SNS Filter**: 계정당 7개 → 3개 선별 (GPT-4o)
- **Stage 1**: 전체 뉴스 → Top 30 선별 (GPT-4o)
- **Stage 2**: Top 30 뉴스 + 선별된 SNS → Top 10 최종 선정 (GPT-4o)
- Output: `[{rank, topic_id, original_title, source_ref, why_now, issue_hook}]`

### 7.6 `outputs/sheets_writer.py` — Google Sheets 저장
- gspread + 서비스 계정 인증
- `perspective_DB` > `topic Recommender` 시트에 append
- 날짜 포함 기록

### 7.7 `outputs/discord_sender.py` — Discord 전송
- 일반: Top 10 이슈 포맷팅 후 웹훅 전송
- **에러 알림**: 파이프라인 에러 발생 시 Discord에 에러 메시지 전송

---

## 8. Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|-----------|------------|
| Instagram DOM 변경으로 크롤링 실패 | High | Medium | 다중 CSS selector 폴백, 실패 시 뉴스만으로 진행 |
| Instagram 로그인 차단 (2FA/CAPTCHA) | High | Medium | 쿠키 기반 세션 유지, 실패 시 skip |
| OpenAI API 오류/한도 초과 | High | Low | 에러 핸들링 + Discord 에러 알림 |
| RSS 피드 URL 변경/중단 | Medium | Low | 다수 소스로 분산, 실패 시 해당 카테고리 skip |
| GitHub Actions 환경에서 Playwright 이슈 | Medium | Low | chromium 설치 스크립트 포함 |

---

## 9. Success Criteria

| ID | 기준 | 측정 방법 |
|----|------|----------|
| SC-01 | 매일 자동으로 Top 10 이슈가 생성된다 | GitHub Actions 실행 로그 확인 |
| SC-02 | Google Sheets에 올바른 형식으로 저장된다 | 시트 데이터 검증 |
| SC-03 | Discord에 포맷된 이슈 메시지가 전송된다 | Discord 채널 확인 |
| SC-04 | Instagram 크롤링 실패 시에도 뉴스만으로 정상 동작한다 | 인스타 차단 상태에서 실행 테스트 |
| SC-05 | 에러 발생 시 Discord에 알림이 간다 | 의도적 에러 발생 후 알림 확인 |
| SC-06 | 전체 실행 시간이 10분 이내이다 | GitHub Actions 실행 시간 확인 |

---

## 10. Implementation Status

> 이 프로젝트는 이미 기능 구현이 완료된 상태입니다.

### 구현 완료
- [x] `config.py` — RSS URL, 시드 계정, 프롬프트 설정
- [x] `collectors/rss_collector.py` — RSS 수집
- [x] `collectors/instagram_collector.py` — Instagram 크롤링
- [x] `analyzer/dedup.py` — 뉴스 중복 제거
- [x] `analyzer/topic_selector.py` — 3단계 AI 필터링
- [x] `outputs/sheets_writer.py` — Google Sheets 저장
- [x] `outputs/discord_sender.py` — Discord 전송
- [x] `main.py` — 파이프라인 오케스트레이터
- [x] `.github/workflows/daily-run.yml` — GitHub Actions 워크플로우

### 미구현 (이번 Plan 확인 사항)
- [ ] Discord 에러 알림 (FR-08) — **구현 필요**
- [ ] 에러 시 graceful degradation 강화 (FR-09)

---

## 11. Implementation Guide

### Module Map

| Module | Files | Dependencies | Complexity |
|--------|-------|-------------|-----------|
| module-1: 에러 알림 | `discord_sender.py`, `main.py` | requests | Low |
| module-2: 안정성 강화 | `instagram_collector.py`, `main.py` | playwright | Medium |

### Recommended Session Plan

| Session | Scope | Est. Changes |
|---------|-------|-------------|
| Session 1 | module-1: Discord 에러 알림 추가 | ~30 lines |
| Session 2 | module-2: Instagram graceful degradation 강화 | ~20 lines |
