"""제목 유사도 기반 중복 제거 모듈"""

from difflib import SequenceMatcher
from src.logger import log

SIMILARITY_THRESHOLD = 0.6


def deduplicate_articles(articles: list[dict]) -> list[dict]:
    """제목 유사도 기반으로 중복 기사를 제거한다.

    같은 사건을 다룬 기사들을 하나로 묶고,
    그 중 설명이 가장 긴 기사를 대표로 남긴다.
    """
    if not articles:
        return []

    groups: list[list[dict]] = []

    for article in articles:
        title = article.get("title", "")
        matched = False

        for group in groups:
            representative = group[0]
            rep_title = representative.get("title", "")
            similarity = SequenceMatcher(None, title.lower(), rep_title.lower()).ratio()

            if similarity >= SIMILARITY_THRESHOLD:
                group.append(article)
                matched = True
                break

        if not matched:
            groups.append([article])

    # 각 그룹에서 설명이 가장 긴 기사를 대표로 선택
    deduplicated = []
    for group in groups:
        representative = max(group, key=lambda a: len(a.get("description", "")))
        representative["duplicate_count"] = len(group)
        deduplicated.append(representative)

    removed = len(articles) - len(deduplicated)
    log(f"[Dedup] {len(articles)}개 -> {len(deduplicated)}개 (중복 {removed}개 제거)")
    return deduplicated
