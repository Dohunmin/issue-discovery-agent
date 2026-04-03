"""한국 커뮤니티 실시간 인기글 수집기.

네이트판 실시간 인기 (여초) — requests + BeautifulSoup
"""

import random
import requests
from bs4 import BeautifulSoup
from src.logger import log

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

REQUEST_TIMEOUT = 15


def _get_headers() -> dict:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "ko-KR,ko;q=0.9",
    }


def collect_community() -> list[dict]:
    """네이트판 인기글을 수집한다."""
    posts = _collect_natepann()
    log(f"[Community] 총 {len(posts)}개 수집 (네이트판 {len(posts)})")
    return posts


def _collect_natepann() -> list[dict]:
    """네이트판 실시간 인기글 제목+공감수를 수집한다."""
    url = "https://pann.nate.com/talk/ranking/d"
    posts = []

    try:
        resp = requests.get(url, headers=_get_headers(), timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # 인기글 목록 파싱
        items = soup.select("div.rankingList ul li, ul.post_wrap li, div.list_area dl")

        for item in items[:20]:
            title_el = item.select_one("a.tit, dt a, a.rankSubject")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            # 공감수 추출
            sympathy = 0
            sym_el = item.select_one("span.sympathy em, span.count em, span.likecnt")
            if sym_el:
                try:
                    sympathy = int(sym_el.get_text(strip=True).replace(",", ""))
                except ValueError:
                    pass

            posts.append({
                "title": title,
                "recommend": sympathy,
                "source": "natepann_hot",
                "category": "community_female",
            })

        log(f"[네이트판] {len(posts)}개 수집")

    except Exception as e:
        log(f"[네이트판] 수집 실패: {e}")

    return posts
