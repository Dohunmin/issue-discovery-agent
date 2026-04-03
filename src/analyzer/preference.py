"""임베딩 기반 취향 벡터 모듈.

Google Sheets에서 "good" 평가된 토픽 + 수기 예시를 읽어
취향 벡터를 생성하고, 새 후보 토픽의 취향 점수를 계산한다.
"""

import json
import base64
import hashlib
from pathlib import Path
import numpy as np
from openai import OpenAI
from google.oauth2.service_account import Credentials
import gspread
from src.config import OPENAI_API_KEY, GOOGLE_SHEETS_CREDS, SPREADSHEET_NAME
from src.logger import log

CACHE_PATH = Path(__file__).parent.parent.parent / ".cache" / "preference_vector.json"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
EMBEDDING_MODEL = "text-embedding-3-small"


def _get_sheets_client():
    """Google Sheets 클라이언트를 반환한다."""
    try:
        creds_json = json.loads(base64.b64decode(GOOGLE_SHEETS_CREDS))
    except Exception:
        creds_json = json.loads(GOOGLE_SHEETS_CREDS)
    credentials = Credentials.from_service_account_info(creds_json, scopes=SCOPES)
    return gspread.authorize(credentials)


def _get_embedding(client: OpenAI, text: str) -> list[float]:
    """텍스트의 임베딩 벡터를 반환한다."""
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
    )
    return response.data[0].embedding


def _get_embeddings_batch(client: OpenAI, texts: list[str]) -> list[list[float]]:
    """여러 텍스트의 임베딩을 한번에 가져온다."""
    if not texts:
        return []
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
    )
    return [item.embedding for item in response.data]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """두 벡터의 코사인 유사도를 계산한다."""
    a_np = np.array(a)
    b_np = np.array(b)
    dot = np.dot(a_np, b_np)
    norm = np.linalg.norm(a_np) * np.linalg.norm(b_np)
    if norm == 0:
        return 0.0
    return float(dot / norm)


MULTI_CENTROID_THRESHOLD = 15  # 이 개수 이상이면 클러스터링 활성화
MULTI_CENTROID_K = 3


def load_preference_vector(client: OpenAI) -> dict | None:
    """Sheets에서 good 토픽 + 수기 예시를 읽어 취향 벡터를 생성한다.

    Returns:
        {"mode": "single", "vector": [...]} 또는
        {"mode": "multi", "centroids": [[...], ...]} 또는
        데이터 부족 시 None
    """
    if not GOOGLE_SHEETS_CREDS:
        log("[Preference] GOOGLE_SHEETS_CREDS 미설정, 취향 벡터 건너뜀")
        return None

    gc = _get_sheets_client()
    sh = gc.open(SPREADSHEET_NAME)

    good_texts = []

    # 1) Topic Recommender에서 rating="good"인 토픽 수집
    try:
        ws = sh.worksheet("Topic Recommender")
        rows = ws.get_all_values()
        if rows:
            header = rows[0]
            rating_idx = header.index("rating") if "rating" in header else -1
            title_idx = header.index("canonical_title") if "canonical_title" in header else 2

            if rating_idx >= 0:
                for row in rows[1:]:
                    if len(row) > rating_idx and row[rating_idx].strip() == "0":
                        title = row[title_idx] if len(row) > title_idx else ""
                        if title:
                            good_texts.append(title)
    except Exception as e:
        log(f"[Preference] Topic Recommender 읽기 실패: {e}")

    # 2) good_examples 시트에서 수기 예시 수집 (title + why_good 결합)
    example_texts = []
    try:
        ex_ws = sh.worksheet("good_examples")
        ex_rows = ex_ws.get_all_values()
        for row in ex_rows[1:]:  # 헤더 스킵
            if row and row[0].strip():
                title = row[0].strip()
                why_good = row[1].strip() if len(row) > 1 and row[1].strip() else ""
                # title + why_good 결합으로 더 풍부한 임베딩 생성
                combined = f"{title} — {why_good}" if why_good else title
                example_texts.append(combined)
    except Exception as e:
        log(f"[Preference] good_examples 읽기 실패: {e}")

    all_texts = good_texts + example_texts
    if len(all_texts) < 3:
        log(f"[Preference] good 데이터 {len(all_texts)}개 — 최소 3개 필요, 건너뜀")
        return None

    log(f"[Preference] good 데이터 로드: Topic Recommender {len(good_texts)}개 + good_examples {len(example_texts)}개")

    # 캐시 확인: good 텍스트가 변하지 않았으면 이전 결과 재사용
    cache_key = hashlib.sha256("|".join(sorted(all_texts)).encode()).hexdigest()
    if CACHE_PATH.exists():
        try:
            cached = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            if cached.get("key") == cache_key:
                mode = cached.get("mode", "single")
                log(f"[Preference] 캐시된 취향 벡터 사용 (mode={mode}, API 호출 생략)")
                return cached
        except Exception:
            pass

    # 3) 임베딩 생성 + 가중 평균/클러스터링
    #    good_examples는 직접 작성한 취향이므로 가중치 2배
    EXAMPLE_WEIGHT = 2.0
    recommender_embeddings = _get_embeddings_batch(client, good_texts) if good_texts else []
    example_embeddings = _get_embeddings_batch(client, example_texts) if example_texts else []

    all_embeddings = recommender_embeddings + example_embeddings
    weights = [1.0] * len(recommender_embeddings) + [EXAMPLE_WEIGHT] * len(example_embeddings)

    if not all_embeddings:
        log("[Preference] 임베딩 생성 실패, 취향 벡터 건너뜀")
        return None

    embeddings_np = np.array(all_embeddings)

    # Multi-centroid: good 데이터가 충분하면 k-means 클러스터링
    if len(all_embeddings) >= MULTI_CENTROID_THRESHOLD:
        result = _build_multi_centroid(embeddings_np, weights)
    else:
        result = _build_single_vector(embeddings_np, weights)

    # 캐시 저장
    result["key"] = cache_key
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(result), encoding="utf-8")

    log(f"[Preference] 취향 벡터 생성 완료 (mode={result['mode']}, 캐시 저장)")
    return result


def _build_single_vector(embeddings_np: np.ndarray, weights: list[float]) -> dict:
    """가중 평균으로 단일 취향 벡터를 생성한다."""
    weights_np = np.array(weights).reshape(-1, 1)
    avg_vector = (embeddings_np * weights_np).sum(axis=0) / sum(weights)
    return {"mode": "single", "vector": avg_vector.tolist()}


def _build_multi_centroid(embeddings_np: np.ndarray, weights: list[float]) -> dict:
    """k-means 클러스터링으로 다중 취향 중심벡터를 생성한다.

    가중치를 반영하기 위해, 가중치가 높은 임베딩을 복제하여 클러스터링한다.
    """
    from sklearn.cluster import KMeans

    # 가중치 반영: weight를 정수배로 반올림하여 복제
    expanded = []
    for emb, w in zip(embeddings_np, weights):
        for _ in range(round(w)):
            expanded.append(emb)
    expanded_np = np.array(expanded)

    k = min(MULTI_CENTROID_K, len(expanded_np) // 5)
    if k < 2:
        return _build_single_vector(embeddings_np, weights)

    kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
    kmeans.fit(expanded_np)

    centroids = kmeans.cluster_centers_.tolist()
    log(f"[Preference] Multi-centroid: {k}개 클러스터 생성 (데이터 {len(embeddings_np)}개)")
    return {"mode": "multi", "centroids": centroids}


def score_candidates(
    client: OpenAI,
    preference_data: dict,
    candidates: list[dict],
    text_key: str = "title",
) -> list[dict]:
    """후보 토픽에 취향 점수(preference_score)를 추가한다.

    Args:
        client: OpenAI 클라이언트
        preference_data: load_preference_vector의 반환값 (single/multi mode)
        candidates: 후보 토픽 리스트
        text_key: 텍스트를 가져올 키 (title, canonical_title 등)

    Returns:
        preference_score가 추가된 후보 리스트
    """
    texts = []
    for c in candidates:
        primary = c.get(text_key, c.get("title", c.get("canonical_title", "")))
        if not primary:
            texts.append("")
            continue
        # 뉴스 후보: description, reason을 결합하여 풍부한 임베딩 생성
        # SNS 후보: caption 자체가 이미 충분히 풍부하므로 그대로 사용
        parts = [primary]
        desc = c.get("description", "")
        if desc:
            parts.append(desc[:200])
        reason = c.get("reason", "")
        if reason:
            parts.append(reason)
        texts.append(" | ".join(parts))

    embeddings = _get_embeddings_batch(client, texts)

    mode = preference_data.get("mode", "single")
    for i, c in enumerate(candidates):
        if mode == "multi":
            # max-sim: 어느 클러스터라도 맞으면 높은 점수
            centroids = preference_data["centroids"]
            score = max(_cosine_similarity(cent, embeddings[i]) for cent in centroids)
        else:
            score = _cosine_similarity(preference_data["vector"], embeddings[i])
        c["preference_score"] = round(score, 4)

    # 점수 로그
    scored = sorted(candidates, key=lambda x: x.get("preference_score", 0), reverse=True)
    log("[Preference] 취향 점수 상위 5개:")
    for c in scored[:5]:
        text = c.get(text_key, c.get("title", c.get("canonical_title", "")))
        log(f"  {c['preference_score']:.3f} | {text[:60]}")

    # 상대적 라벨 부여 (LLM이 raw 숫자보다 라벨을 더 잘 활용)
    _assign_preference_labels(candidates)

    return candidates


def _assign_preference_labels(candidates: list[dict]) -> None:
    """preference_score를 상대적 등급 라벨로 변환한다."""
    scores = sorted(
        [c["preference_score"] for c in candidates if "preference_score" in c],
        reverse=True,
    )
    if not scores:
        return

    for c in candidates:
        score = c.get("preference_score")
        if score is None:
            c["preference_label"] = ""
            continue
        rank = scores.index(score)
        percentile = 1.0 - (rank / len(scores))
        if percentile >= 0.7:
            c["preference_label"] = "매우 높음"
        elif percentile >= 0.4:
            c["preference_label"] = "보통"
        else:
            c["preference_label"] = "낮음"
