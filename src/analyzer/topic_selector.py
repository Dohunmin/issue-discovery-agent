import json
from urllib.parse import urlparse
from openai import OpenAI
from src.config import OPENAI_API_KEY, SNS_FILTER_PROMPT, STAGE1_PROMPT, STAGE2_ENRICH_PROMPT
from src.analyzer.preference import load_preference_vector, score_candidates, BAD_HARD_FILTER_THRESHOLD
from src.logger import log

RUBRIC_WEIGHT = 0.5      # 5차원 채점 가중치 50%
PREFERENCE_WEIGHT = 0.5  # 취향 벡터 가중치 50%
STAGE1_TARGET_COUNT = 30
STAGE2_MIN_CANDIDATES = 15
LOG_PREVIEW_CHARS = 60
MAX_RUBRIC_TOTAL = 15

STAGE1_SCORING_INSTRUCTION = """
IMPORTANT STAGE 1 SCORING RULE:
- Score every selected candidate with the same 5D rubric used later:
  1) 체감도, 2) 소재력, 3) 확산성, 4) 구체성, 5) 시의성.
- Each dimension must be an integer from 1 to 3.
- scores.total must be the sum of the five dimensions, from 5 to 15.
- Select exactly the best Top 30 by scores.total first, using editorial judgment only as a tie-breaker.
- Every article object must include:
  "scores": {"체감도": N, "소재력": N, "확산성": N, "구체성": N, "시의성": N, "total": N}
"""


def select_topics(
    rss_articles: list[dict],
    instagram_posts_by_account: dict[str, list[dict]],
    youtube_videos: list[dict] | None = None,
    community_posts: list[dict] | None = None,
) -> list[dict]:
    """다중 소스 AI 선정 + 취향 벡터:
    - SNS 필터: 인스타 계정당 2~3개 선택
    - Stage 1: 뉴스 + YouTube + 커뮤니티 → Top 50
    - 취향 벡터: 전체 후보에 preference_score 부여
    - Stage 2A: 취향 반영 Top 10
    - Stage 2B: 모델 자체 Top 3 (비교용)
    """
    client = OpenAI(api_key=OPENAI_API_KEY)
    youtube_videos = youtube_videos or []
    community_posts = community_posts or []

    # SNS 필터: 계정당 AI가 2~3개씩 선택
    log("[SNS 필터] 계정별 게시물 분석 중...")
    filtered_sns = _filter_instagram(client, instagram_posts_by_account)
    log(f"[SNS 필터] 총 {len(filtered_sns)}개 게시물 선정 완료")
    for s in filtered_sns:
        log(f"  > @{s.get('account','')}: {_preview_text(s.get('caption', ''))}")

    # Stage 1: 뉴스 + YouTube + Instagram + 커뮤니티 통합 후보에서 Top 50 선별
    log(f"[Stage 1] 뉴스 + YouTube + Instagram 통합 후보에서 Top {STAGE1_TARGET_COUNT} 선별 중...")
    top30_articles = _stage1_filter(
        client, rss_articles, youtube_videos, community_posts, filtered_sns
    )
    reserve_candidates = _build_reserve_candidates(
        rss_articles, youtube_videos, filtered_sns, top30_articles
    )
    log(f"[Stage 1] {len(top30_articles)}개 선별 완료")
    for i, a in enumerate(top30_articles, 1):
        title = a.get("title", a.get("canonical_title", ""))
        scores = a.get("scores") if isinstance(a.get("scores"), dict) else {}
        log(
            f"  {i}. [{a.get('category','')}] "
            f"5D={scores.get('total', '')} {_preview_text(title, 70)}"
        )

    # 취향 벡터 로드 + 후보에 점수 부여
    log("[Preference] 취향 벡터 로드 중...")
    pref_data = load_preference_vector(client)
    if pref_data:
        top30_articles = score_candidates(
            client, pref_data, top30_articles, text_key="title",
            label=f"뉴스+유튜브+커뮤니티 Top {STAGE1_TARGET_COUNT}",
        )
        if reserve_candidates:
            reserve_candidates = score_candidates(
                client, pref_data, reserve_candidates, text_key="title",
                label="Stage 2 예비 후보",
            )

    # 취향 하드 필터: bad 유사도가 임계값 이상인 후보 제거
    if pref_data:
        before_news = len(top30_articles)
        top30_articles = [
            a for a in top30_articles
            if a.get("bad_similarity", 0) < BAD_HARD_FILTER_THRESHOLD
        ]
        reserve_candidates = [
            a for a in reserve_candidates
            if a.get("bad_similarity", 0) < BAD_HARD_FILTER_THRESHOLD
        ]
        removed_news = before_news - len(top30_articles)
        if removed_news:
            log(f"[Preference] 하드 필터: 통합 Top{STAGE1_TARGET_COUNT} 후보 {removed_news}개 제거 (bad 유사도 ≥ {BAD_HARD_FILTER_THRESHOLD})")

    top30_articles = _ensure_min_stage2_candidates(
        top30_articles, reserve_candidates, min_count=STAGE2_MIN_CANDIDATES
    )

    # Stage 2A: 취향 반영 Top 10
    log("[Stage 2A] 취향 반영 → Top 10 선정 중...")
    _prepare_stage2_scoring(top30_articles, [])
    _attach_candidate_source_details(
        top30_articles, rss_articles, instagram_posts_by_account, youtube_videos, filtered_sns
    )
    log(f"[Stage 2A] scoring rule: 5D rubric {int(RUBRIC_WEIGHT*100)}% + preference vector {int(PREFERENCE_WEIGHT*100)}%")
    topics = _stage2_select(client, top30_articles, [])
    log(f"[Stage 2A] {len(topics)}개 이슈 최종 선정 완료")
    for t in topics:
        t["selection_type"] = "preference"
        title = t.get("original_title", t.get("canonical_title", ""))
        scores = t.get("scores") if isinstance(t.get("scores"), dict) else {}
        log(f"  #{t.get('rank','')} {t.get('candidate_id', '')} {_preview_text(title, 70)}")
        log(
            "     score: "
            f"5D_total={scores.get('total', '')} "
            f"rubric={t.get('rubric_norm', '')} "
            f"pref={t.get('preference_norm', '')} "
            f"final={t.get('final_score', '')}"
        )
        if scores:
            log(f"     5D: {json.dumps(scores, ensure_ascii=False)}")
        log(f"     why_now: {_preview_text(t.get('why_now', ''), 90)}")

    # 소스 역매핑: 제목 기반으로 원본 소스 정보 추가
    _enrich_source_detail(
        topics, rss_articles, instagram_posts_by_account, youtube_videos,
        top30_articles=top30_articles, filtered_sns=filtered_sns,
    )

    return topics


def _filter_instagram(
    client: OpenAI,
    posts_by_account: dict[str, list[dict]],
) -> list[dict]:
    """각 계정의 게시물 7개를 AI가 분석하여 3개씩 선택한다."""
    selected_posts = []

    AD_KEYWORDS = ["#광고", "#ad", "#협찬", "#sponsored", "#제공"]

    for account, posts in posts_by_account.items():
        if not posts:
            continue

        # 광고 게시물 사전 제거 (코드 레벨 강제)
        clean_posts = []
        for p in posts:
            caption = p.get("caption", "")
            caption_lower = caption.lower()
            if any(kw in caption_lower for kw in AD_KEYWORDS):
                log(f"  @{account}: 광고 제거 - {_preview_text(caption, 50)}")
                continue
            clean_posts.append(p)
        posts = clean_posts

        if not posts:
            log(f"  @{account}: 광고 제거 후 남은 게시물 없음")
            continue

        # 캡션 목록 구성
        captions_text = f"계정: @{account}\n\n"
        for i, post in enumerate(posts):
            caption = post.get("caption", "(캡션 없음)")
            captions_text += f"[{i}] {caption[:400]}\n\n"

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SNS_FILTER_PROMPT},
                {"role": "user", "content": captions_text},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content
        try:
            result = json.loads(raw)
            indices = result.get("selected", [])
            for idx in indices:
                if 0 <= idx < len(posts):
                    selected_posts.append(posts[idx])
            log(f"  @{account}: {len(posts)}개 중 인덱스 {indices} 선택")
        except (json.JSONDecodeError, TypeError):
            # 파싱 실패 시 캡션이 있는 것 중 앞 3개 폴백
            fallback = [p for p in posts if p.get("caption")][:3]
            selected_posts.extend(fallback)
            log(f"  @{account}: AI 필터 실패, 폴백 {len(fallback)}개 선택")

    return selected_posts


def _preview_text(text: object, limit: int = LOG_PREVIEW_CHARS) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip() + "..."


def _stage1_filter(
    client: OpenAI,
    articles: list[dict],
    youtube_videos: list[dict] | None = None,
    community_posts: list[dict] | None = None,
    sns_posts: list[dict] | None = None,
) -> list[dict]:
    """1단계: 뉴스 + YouTube + 커뮤니티에서 Top 50을 선별한다."""
    rss_text = STAGE1_SCORING_INSTRUCTION + "\n\n" + _build_stage1_text(
        articles, youtube_videos or [], community_posts or [], sns_posts or []
    )

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": STAGE1_PROMPT},
            {"role": "user", "content": rss_text},
        ],
        temperature=0.5,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content
    try:
        result = json.loads(raw)
        if isinstance(result, dict):
            items = result.get("articles", [])
        elif isinstance(result, list):
            items = result
        else:
            items = []

        # 후처리: 제목 중복 제거 + 목표 개수 강제
        seen_titles = set()
        deduped = []
        for item in items:
            title = item.get("title", "").strip()
            if title and title not in seen_titles:
                seen_titles.add(title)
                _normalize_stage1_scores(item)
                deduped.append(item)

        # GPT가 목표 개수 미만을 반환하면, 입력 소스에서 보충
        if len(deduped) < STAGE1_TARGET_COUNT:
            shortage = STAGE1_TARGET_COUNT - len(deduped)
            # YouTube → 뉴스 순으로 보충
            backfill_sources = (
                _stage1_backfill_items(youtube_videos or [], "유튜브")
                + _stage1_backfill_items(sns_posts or [], "SNS")
                + _stage1_backfill_items(articles, "뉴스")
            )
            for src in backfill_sources:
                if len(deduped) >= STAGE1_TARGET_COUNT:
                    break
                title = src.get("title", "").strip()
                if title and title not in seen_titles:
                    seen_titles.add(title)
                    _normalize_stage1_scores(src, fallback=True)
                    deduped.append(src)
            log(f"[Stage 1] GPT가 {STAGE1_TARGET_COUNT - shortage}개만 반환 → {shortage}개 자동 보충하여 {len(deduped)}개")

        sorted_items = sorted(
            deduped,
            key=lambda item: item.get("scores", {}).get("total", 0),
            reverse=True,
        )
        # 동일 이슈 중복 제한 (story당 최대 2개)
        sorted_items = _dedup_stage1_stories(sorted_items, max_per_story=1)
        return sorted_items[:STAGE1_TARGET_COUNT]
    except json.JSONDecodeError:
        log(f"[Stage 1] JSON 파싱 실패: {raw[:200]}")
        return []


def _stage1_backfill_items(items: list[dict], category: str) -> list[dict]:
    backfill = []
    for i, item in enumerate(items, 1):
        title = item.get("title") or item.get("caption", "")[:120]
        if not title:
            continue
        prefix = "SNS" if category == "SNS" else ("유튜브" if category == "유튜브" else "뉴스")
        backfill.append({
            "title": title,
            "description": item.get("description", item.get("caption", "")),
            "category": item.get("category", category),
            "source_ref": item.get("source_ref", item.get("source", f"{prefix}#{i}")),
            "reason": "자동 보충",
        })
    return backfill


_STORY_STOPWORDS = frozenset({
    "논란", "여파", "문제", "이후", "최근", "결국", "이다", "하다",
    "그", "한", "된", "및", "등", "속", "중", "위해", "위한", "통해",
    "것", "수", "더", "안", "못", "적", "때", "말", "관련", "위기",
    "상황", "우려", "주목", "화제", "이번", "지금", "오늘", "어제",
})


def _dedup_stage1_stories(candidates: list[dict], max_per_story: int = 2) -> list[dict]:
    """핵심 키워드 2개 이상 겹치는 기사를 같은 story로 묶어 story당 최대 N개만 유지.

    candidates는 이미 score 내림차순 정렬되어 있어야 한다 (높은 점수 우선 보존).
    """
    import re

    def _keywords(title: str) -> frozenset:
        tokens = re.findall(r"[가-힣]{2,}|[A-Za-z]{3,}", title)
        return frozenset(t for t in tokens if t not in _STORY_STOPWORDS)

    # (대표 키워드셋, 현재 count)
    buckets: list[tuple[frozenset, int]] = []
    result: list[dict] = []

    for item in candidates:
        kws = _keywords(item.get("title", ""))
        if not kws:
            result.append(item)
            continue

        matched = -1
        for i, (bkws, _) in enumerate(buckets):
            if len(kws & bkws) >= 2:
                matched = i
                break

        if matched == -1:
            buckets.append((kws, 1))
            result.append(item)
        elif buckets[matched][1] < max_per_story:
            buckets[matched] = (buckets[matched][0], buckets[matched][1] + 1)
            result.append(item)

    removed = len(candidates) - len(result)
    if removed:
        log(f"[Stage 1] 이슈 클러스터링: 동일 이슈 중복 {removed}개 제거 (story당 최대 {max_per_story}개)")
    return result


def _normalize_stage1_scores(item: dict, fallback: bool = False) -> None:
    scores = item.get("scores") if isinstance(item.get("scores"), dict) else {}
    normalized = {}
    for key in ("체감도", "소재력", "확산성", "구체성", "시의성"):
        value = scores.get(key)
        if not isinstance(value, (int, float)):
            value = 2 if fallback else 1
        normalized[key] = max(1, min(int(value), 3))
    normalized["total"] = sum(normalized.values())
    item["scores"] = normalized
    item["rubric_norm"] = round(normalized["total"] / MAX_RUBRIC_TOTAL, 4)


def _build_reserve_candidates(
    articles: list[dict],
    youtube_videos: list[dict],
    sns_posts: list[dict],
    selected: list[dict],
) -> list[dict]:
    selected_titles = {
        _normalize_match_text(item.get("title", item.get("canonical_title", "")))
        for item in selected
        if item.get("title") or item.get("canonical_title")
    }
    reserves = (
        _stage1_backfill_items(youtube_videos or [], "유튜브")
        + _stage1_backfill_items(sns_posts or [], "SNS")
        + _stage1_backfill_items(articles or [], "뉴스")
    )

    deduped = []
    seen = set(selected_titles)
    for item in reserves:
        title = item.get("title", "").strip()
        norm_title = _normalize_match_text(title)
        if not norm_title or norm_title in seen:
            continue
        seen.add(norm_title)
        _normalize_stage1_scores(item, fallback=True)
        deduped.append(item)
    return deduped


def _ensure_min_stage2_candidates(
    primary: list[dict],
    reserves: list[dict],
    min_count: int = STAGE2_MIN_CANDIDATES,
) -> list[dict]:
    if len(primary) >= min_count:
        return primary

    selected_titles = {
        _normalize_match_text(item.get("title", item.get("canonical_title", "")))
        for item in primary
    }
    sorted_reserves = sorted(
        reserves,
        key=lambda item: item.get("preference_score", 0),
        reverse=True,
    )

    added = 0
    for item in sorted_reserves:
        if len(primary) >= min_count:
            break
        norm_title = _normalize_match_text(item.get("title", ""))
        if not norm_title or norm_title in selected_titles:
            continue
        selected_titles.add(norm_title)
        primary.append(item)
        added += 1

    if added:
        log(f"[Stage 2] 후보 부족: bad 필터 통과 예비 후보 {added}개 보충 → {len(primary)}개")
    elif len(primary) < 10:
        log(f"[Stage 2] WARNING: bad 필터 통과 후보가 {len(primary)}개뿐이라 Top10을 채울 수 없습니다")

    return primary


def _stage2_select(
    client: OpenAI,
    top30_articles: list[dict],
    filtered_sns: list[dict],
) -> list[dict]:
    """2단계: 5차원 50% + 취향벡터 50% → 코드가 Top 10 선정 → LLM 보강."""
    all_candidates = top30_articles + filtered_sns

    # reserve 후보 보충 후 story 중복 재차 제거
    all_candidates = _dedup_stage1_stories(all_candidates, max_per_story=1)

    # 1. final_score 계산 (코드 기반, LLM 없음)
    for c in all_candidates:
        scores = c.get("scores") if isinstance(c.get("scores"), dict) else {}
        total = scores.get("total", 5)
        rubric_norm = max(0.0, min(float(total) / MAX_RUBRIC_TOTAL, 1.0))
        pref_norm = c.get("preference_norm", 0.5)
        if not isinstance(pref_norm, (int, float)):
            pref_norm = 0.5
        c["rubric_norm"] = round(rubric_norm, 4)
        c["final_score"] = round(
            RUBRIC_WEIGHT * rubric_norm + PREFERENCE_WEIGHT * float(pref_norm), 4
        )

    # 2. 정렬 → 중복 제거 → 다양성 → Top 10 (코드 기반 선정)
    ranked = sorted(all_candidates, key=lambda c: c.get("final_score", 0), reverse=True)
    ranked = _dedup_by_title(ranked)
    ranked = _enforce_diversity(ranked)
    top10 = ranked[:10]

    log(f"[Stage 2] Combined score 기반 Top 10 (5D×{int(RUBRIC_WEIGHT*100)}% + 취향×{int(PREFERENCE_WEIGHT*100)}%):")
    for i, c in enumerate(top10, 1):
        title = c.get("title", c.get("caption", ""))[:60]
        log(
            f"  #{i} final={c['final_score']:.3f}"
            f" (rubric={c['rubric_norm']:.2f} pref={c.get('preference_norm', 0):.2f})"
            f" | {title}"
        )

    # 3. LLM으로 why_now / issue_hook 생성 (선정 결과는 변경하지 않음)
    log("[Stage 2] why_now / issue_hook 생성 중...")
    return _enrich_top10(client, top10)


def _dedup_by_title(candidates: list[dict]) -> list[dict]:
    """title / caption 기준으로 중복 제거."""
    seen: set[str] = set()
    deduped = []
    for c in candidates:
        title = (c.get("title") or c.get("caption") or "").strip()
        norm = _normalize_match_text(title)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        deduped.append(c)
    return deduped


def _enrich_top10(client: OpenAI, top10: list[dict]) -> list[dict]:
    """선정된 Top 10에 original_title / why_now / issue_hook 생성."""
    items_text = ""
    for i, c in enumerate(top10, 1):
        title = (c.get("title") or c.get("caption") or "")[:200]
        src = c.get("source_ref") or c.get("stage2_id", "")
        scores = c.get("scores") if isinstance(c.get("scores"), dict) else {}
        items_text += (
            f"[{i}] {title}\n"
            f"출처: {src} | 5D총점: {scores.get('total', 'N/A')}/15"
            f" | final_score: {c.get('final_score', 0):.3f}\n\n"
        )

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": STAGE2_ENRICH_PROMPT},
            {"role": "user", "content": items_text},
        ],
        temperature=0.7,
        response_format={"type": "json_object"},
    )

    enrichment: dict[int, dict] = {}
    try:
        result = json.loads(response.choices[0].message.content)
        for e in result.get("topics", []):
            idx = e.get("index")
            if isinstance(idx, int):
                enrichment[idx] = e
    except Exception as exc:
        log(f"[Stage 2] 보강 파싱 실패: {exc}")

    topics = []
    for i, c in enumerate(top10, 1):
        e = enrichment.get(i, {})
        default_title = (c.get("title") or c.get("caption") or "")
        topics.append({
            "rank": i,
            "topic_id": f"topic_{i:02d}",
            "original_title": e.get("original_title") or default_title,
            "why_now": e.get("why_now", ""),
            "issue_hook": e.get("issue_hook", ""),
            "source_ref": e.get("source_ref") or c.get("source_ref") or c.get("stage2_id", ""),
            "scores": c.get("scores", {}),
            "rubric_norm": c.get("rubric_norm", 0),
            "preference_norm": c.get("preference_norm", 0),
            "final_score": c.get("final_score", 0),
            "preference_score": c.get("preference_score"),
            "preference_label": c.get("preference_label", ""),
            "candidate_id": c.get("stage2_id", ""),
            # 소스 역매핑용 원본 필드 보존
            "title": c.get("title", ""),
            "caption": c.get("caption", ""),
            "account": c.get("account", ""),
        })
    return topics





def _prepare_stage2_scoring(
    top30_articles: list[dict],
    filtered_sns: list[dict],
) -> None:
    candidates = top30_articles + filtered_sns
    scores = [
        c.get("preference_score")
        for c in candidates
        if isinstance(c.get("preference_score"), (int, float))
    ]
    min_score = min(scores) if scores else 0.0
    max_score = max(scores) if scores else 0.0
    span = max_score - min_score

    for i, art in enumerate(top30_articles, 1):
        art["stage2_id"] = f"N{i}"
        art["preference_norm"] = _normalize_preference(
            art.get("preference_score"), min_score, span
        )

    for i, post in enumerate(filtered_sns, 1):
        post["stage2_id"] = f"S{i}"
        post["preference_norm"] = _normalize_preference(
            post.get("preference_score"), min_score, span
        )


def _normalize_preference(score: object, min_score: float, span: float) -> float:
    if not isinstance(score, (int, float)):
        return 0.5
    if span <= 0:
        return 0.5
    return round((float(score) - min_score) / span, 4)


def _attach_candidate_source_details(
    candidates: list[dict],
    rss_articles: list[dict],
    instagram_posts_by_account: dict[str, list[dict]],
    youtube_videos: list[dict],
    filtered_sns: list[dict],
) -> None:
    news_index_map = {
        i + 1: {
            "type": "rss",
            "name": _extract_rss_domain(art),
            "category": art.get("category", ""),
        }
        for i, art in enumerate(rss_articles)
    }
    yt_index_map = {
        i + 1: {
            "type": "youtube",
            "name": vid.get("channel", "unknown"),
            "channel_id": vid.get("channel_id", ""),
        }
        for i, vid in enumerate(youtube_videos or [])
    }
    sns_index_map = {
        i + 1: {
            "type": "instagram",
            "name": post.get("account", "unknown"),
        }
        for i, post in enumerate(filtered_sns or [])
    }

    title_to_source: dict[str, dict] = {}
    for art in rss_articles:
        title = art.get("title", "").strip()
        if title:
            title_to_source[title] = {
                "type": "rss",
                "name": _extract_rss_domain(art),
                "category": art.get("category", ""),
            }
    for vid in youtube_videos or []:
        title = vid.get("title", "").strip()
        if title:
            title_to_source[title] = {
                "type": "youtube",
                "name": vid.get("channel", "unknown"),
                "channel_id": vid.get("channel_id", ""),
            }
    for account, posts in instagram_posts_by_account.items():
        for post in posts:
            caption = post.get("caption", "").strip()
            if caption:
                title_to_source[caption] = {
                    "type": "instagram",
                    "name": account,
                }

    for item in candidates:
        if item.get("source_detail"):
            continue
        source_info = _parse_source_ref(
            item.get("source_ref", ""), news_index_map, yt_index_map, sns_index_map
        )
        if source_info:
            item["source_detail"] = source_info
            continue
        title = item.get("title", item.get("caption", "")).strip()
        matched = _try_match(title, title_to_source)
        if matched:
            item["source_detail"] = matched




def _build_candidate_lookup(
    top30_articles: list[dict],
    filtered_sns: list[dict],
) -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    for item in top30_articles + filtered_sns:
        for key in (
            item.get("stage2_id"),
            item.get("candidate_id"),
            item.get("source_ref"),
            item.get("title"),
            item.get("caption"),
        ):
            if key:
                lookup[str(key).strip()] = item
    return lookup


def _find_candidate_for_topic(topic: dict, lookup: dict[str, dict]) -> dict | None:
    for key in (
        topic.get("candidate_id"),
        topic.get("source_ref"),
        topic.get("original_title"),
        topic.get("canonical_title"),
    ):
        if key and str(key).strip() in lookup:
            return lookup[str(key).strip()]

    title = topic.get("original_title", topic.get("canonical_title", ""))
    norm_title = _normalize_match_text(title)
    if not norm_title:
        return None

    for candidate_key, candidate in lookup.items():
        norm_key = _normalize_match_text(candidate_key)
        if len(norm_key) < 12:
            continue
        if norm_key in norm_title or norm_title in norm_key:
            return candidate
    return None


def _normalize_match_text(value: object) -> str:
    if not value:
        return ""
    text = str(value)
    for token in ("[.txt]", "|", " ", "\t", "\n"):
        text = text.replace(token, "")
    return text.strip()




def _enforce_diversity(topics: list[dict], max_per_category: int = 3) -> list[dict]:
    """동일 카테고리 최대 N개로 제한하는 후처리.

    source_ref 기반으로 뉴스/SNS 비율을 조절한다.
    토픽 수와 무관하게 항상 다양성 체크를 실행한다.
    """
    if not topics:
        return topics

    category_count: dict[str, int] = {}
    filtered = []
    overflow = []

    for t in topics:
        ref = t.get("source_ref", "")
        cat = ref.split("#")[0] if "#" in ref else "unknown"
        count = category_count.get(cat, 0)

        if count < max_per_category:
            filtered.append(t)
            category_count[cat] = count + 1
        else:
            overflow.append(t)

    # 원래 개수까지 채우기
    target = min(len(topics), 10)
    while len(filtered) < target and overflow:
        filtered.append(overflow.pop(0))

    return filtered[:target]


def _build_rss_text(articles: list[dict]) -> str:
    """1단계용: 전체 RSS 기사 목록 텍스트."""
    lines = [f"총 {len(articles)}개 뉴스 기사:\n"]
    for i, art in enumerate(articles, 1):
        lines.append(
            f"{i}. [{art.get('category', '')}] {art.get('title', '')} | "
            f"{art.get('description', '')[:200]}"
        )
    return "\n".join(lines)


def _build_stage1_text(
    articles: list[dict],
    youtube_videos: list[dict],
    community_posts: list[dict],
    sns_posts: list[dict],
) -> str:
    """1단계용: YouTube + 커뮤니티를 앞에, 뉴스를 뒤에 배치.

    GPT positional bias 대응: 중요 소스(유튜브/커뮤니티)를 앞에 놓고,
    뉴스는 제목만 전달하여 토큰을 절약한다.
    """
    lines = []

    # 1) YouTube — 맨 앞 배치 (GPT가 확실히 인식하도록)
    if youtube_videos:
        lines.append(f"=== YouTube 이슈/트렌드 채널 ({len(youtube_videos)}건) ===")
        lines.append("2030 이슈를 다루는 채널의 최근 영상. 이 중 이슈성 있는 것을 반드시 선정하세요.")
        for i, vid in enumerate(youtube_videos, 1):
            views = vid.get("view_count", 0)
            view_str = f"{views:,}" if views else ""
            lines.append(
                f"유튜브#{i}. {vid.get('title', '')} | "
                f"{vid.get('channel', '')} | 조회수 {view_str}"
            )

    # 2) 뉴스 — 제목만 (description 생략하여 토큰 절약)
    if sns_posts:
        lines.append(f"\n=== Instagram/SNS 후보 ({len(sns_posts)}건) ===")
        lines.append("뉴스, YouTube와 같은 후보풀에서 공정하게 평가하세요. 광고성 게시물은 이미 제거되었습니다.")
        for i, post in enumerate(sns_posts, 1):
            caption = _preview_text(post.get("caption", ""), 500)
            lines.append(f"SNS#{i}. @{post.get('account', '')}: {caption}")

    if community_posts:
        lines.append(f"\n=== 커뮤니티 인기글 ({len(community_posts)}건) ===")
        for i, post in enumerate(community_posts, 1):
            title = post.get("title", post.get("caption", ""))
            lines.append(f"커뮤니티#{i}. {title}")

    lines.append(f"\n=== 뉴스 기사 ({len(articles)}건) ===")
    for i, art in enumerate(articles, 1):
        trending_tag = " [TRENDING]" if art.get("trending") else ""
        lines.append(
            f"뉴스#{i}. [{art.get('category', '')}]{trending_tag} {art.get('title', '')}"
        )

    return "\n".join(lines)




def _enrich_source_detail(
    topics: list[dict],
    rss_articles: list[dict],
    instagram_posts_by_account: dict[str, list[dict]],
    youtube_videos: list[dict] | None = None,
    top30_articles: list[dict] | None = None,
    filtered_sns: list[dict] | None = None,
) -> None:
    """제목 매칭으로 Top 10 결과에 source_detail을 추가한다.

    매칭 체인: 최종 제목 → top30/filtered_sns 제목 → 원본 소스
    GPT가 제목을 변형해도 중간 단계(top30)를 거치면 역추적 가능.
    """
    youtube_videos = youtube_videos or []
    top30_articles = top30_articles or []
    filtered_sns = filtered_sns or []

    # ── 1층: 원본 소스 테이블 (제목 → 소스 정보) ──
    title_to_source: dict[str, dict] = {}

    for art in rss_articles:
        title = art.get("title", "").strip()
        if title:
            title_to_source[title] = {
                "type": "rss",
                "name": _extract_rss_domain(art),
                "category": art.get("category", ""),
            }

    for vid in youtube_videos:
        title = vid.get("title", "").strip()
        if title:
            title_to_source[title] = {
                "type": "youtube",
                "name": vid.get("channel", "unknown"),
                "channel_id": vid.get("channel_id", ""),
            }

    caption_to_source: dict[str, dict] = {}
    for account, posts in instagram_posts_by_account.items():
        for post in posts:
            caption = post.get("caption", "").strip()
            if caption:
                caption_to_source[caption[:100]] = {
                    "type": "instagram",
                    "name": account,
                }

    # ── 2층: Stage 1 source_ref 번호 → 원본 역매핑 ──
    # Stage 1 입력 텍스트에서 "뉴스#N" → rss_articles[N-1], "유튜브#N" → youtube_videos[N-1]
    news_index_map: dict[int, dict] = {}
    for i, art in enumerate(rss_articles):
        source_name = _extract_rss_domain(art)
        news_index_map[i + 1] = {
            "type": "rss",
            "name": source_name,
            "category": art.get("category", ""),
        }
    yt_index_map: dict[int, dict] = {}
    for i, vid in enumerate(youtube_videos):
        yt_index_map[i + 1] = {
            "type": "youtube",
            "name": vid.get("channel", "unknown"),
            "channel_id": vid.get("channel_id", ""),
        }
    sns_index_map: dict[int, dict] = {}
    for i, post in enumerate(filtered_sns):
        sns_index_map[i + 1] = {
            "type": "instagram",
            "name": post.get("account", "unknown"),
        }

    # ── 3층: top30 제목 → 원본 역추적 ──
    # top30 항목의 source_ref("뉴스#3")를 파싱하여 원본 소스에 매핑
    top30_title_to_source: dict[str, dict] = {}
    for item in top30_articles:
        t30_title = item.get("title", item.get("canonical_title", "")).strip()
        if not t30_title:
            continue

        # top30의 source_ref로 원본 역추적
        ref = item.get("source_ref", "")
        source_info = _parse_source_ref(ref, news_index_map, yt_index_map, sns_index_map)
        if source_info:
            top30_title_to_source[t30_title] = source_info
        elif t30_title in title_to_source:
            top30_title_to_source[t30_title] = title_to_source[t30_title]

    # ── 4층: filtered_sns 제목 → Instagram 계정 ──
    sns_title_to_source: dict[str, dict] = {}
    for post in filtered_sns:
        caption = post.get("caption", "").strip()
        account = post.get("account", "")
        if caption and account:
            sns_title_to_source[caption[:100]] = {
                "type": "instagram",
                "name": account,
            }

    # ── 매칭 실행 ──
    candidate_lookup = _build_candidate_lookup(top30_articles, filtered_sns)
    for topic in topics:
        title = topic.get("original_title", topic.get("canonical_title", "")).strip()

        # 0차: Stage 2 이전에 고정한 candidate_id로 직접 매핑
        candidate = _find_candidate_for_topic(topic, candidate_lookup)
        if candidate and candidate.get("source_detail"):
            topic["candidate_id"] = topic.get("candidate_id") or candidate.get("stage2_id", "")
            topic["source_ref"] = topic.get("source_ref") or candidate.get("source_ref", "")
            topic["source_detail"] = candidate["source_detail"]
            continue

        # 1차: 원본 소스 정확 매칭
        if title in title_to_source:
            topic["source_detail"] = title_to_source[title]
            continue

        # 2차: top30 제목 매칭 (GPT Stage 1이 변형한 제목)
        matched = _try_match(title, top30_title_to_source)
        if matched:
            topic["source_detail"] = matched
            continue

        # 3차: 원본 소스 부분 매칭
        matched = _try_match(title, title_to_source)
        if matched:
            topic["source_detail"] = matched
            continue

        # 4차: Instagram 캡션 매칭
        matched = _try_match(title, sns_title_to_source)
        if matched:
            topic["source_detail"] = matched
            continue
        matched = _try_match(title, caption_to_source)
        if matched:
            topic["source_detail"] = matched
            continue

        # 5차: GPT가 반환한 source_ref 직접 파싱
        ref = topic.get("source_ref", "")
        source_info = _parse_source_ref(ref, news_index_map, yt_index_map, sns_index_map)
        if source_info:
            topic["source_detail"] = source_info
            continue

        topic["source_detail"] = {"type": "unknown", "name": "unknown"}
        log(f"  [Source] WARNING: 역매핑 실패 — {title[:60]}")

    # 매핑 결과 로그
    for t in topics:
        detail = t.get("source_detail", {})
        log(f"  [Source] {detail.get('type', '?')}:{detail.get('name', '?')} <- {t.get('original_title', '')[:50]}")


def _try_match(title: str, source_map: dict[str, dict]) -> dict | None:
    """제목을 source_map에서 부분 매칭으로 찾는다."""
    # 1차: 부분 문자열 매칭
    for src_title, src_info in source_map.items():
        if src_title in title or title in src_title:
            return src_info

    # 2차: 공백/특수문자 정규화 후 매칭 (GPT가 띄어쓰기를 바꾸는 경우)
    import re
    norm_title = re.sub(r"\s+", "", title)
    for src_title, src_info in source_map.items():
        norm_src = re.sub(r"\s+", "", src_title)
        if norm_src in norm_title or norm_title in norm_src:
            return src_info
        # 앞 30자만 비교 (GPT가 뒤에 부제를 추가하는 경우)
        if len(norm_title) >= 15 and len(norm_src) >= 15:
            if norm_title[:30] in norm_src or norm_src[:30] in norm_title:
                return src_info

    return None


def _parse_source_ref(ref: str, news_map: dict, yt_map: dict, sns_map: dict | None = None) -> dict | None:
    """GPT가 반환한 source_ref 문자열을 파싱하여 원본 소스를 찾는다.

    예: "뉴스#3" → news_map[3], "유튜브#2" → yt_map[2]
    """
    if not ref:
        return None
    import re
    m = re.match(r"(뉴스|유튜브|SNS)#(\d+)", ref)
    if not m:
        return None
    src_type, idx_str = m.group(1), int(m.group(2))
    if src_type == "뉴스":
        return news_map.get(idx_str)
    elif src_type == "유튜브":
        return yt_map.get(idx_str)
    elif src_type == "SNS" and sns_map:
        return sns_map.get(idx_str)
    return None


def _extract_rss_domain(article: dict) -> str:
    """RSS 기사에서 소스 도메인을 추출한다."""
    url = article.get("url", "")
    if url:
        domain = urlparse(url).netloc.replace("www.", "")
        if domain:
            return domain
    source = article.get("source", "")
    if source:
        return source
    return "unknown_rss"
