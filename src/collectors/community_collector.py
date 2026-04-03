"""한국 커뮤니티 실시간 인기글 수집기.

DC인사이드 실시간 베스트 (남초) + 네이트판 실시간 인기 (여초)를 수집한다.
requests + BeautifulSoup으로 제목+추천수만 파싱 (Playwright 불필요).
"""

import random
import time
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
    """DC인사이드 실베 + 네이트판 인기글을 수집한다."""
    posts = []

    dc_posts = _collect_dcinside()
    posts.extend(dc_posts)

    time.sleep(2)

    pann_posts = _collect_natepann()
    posts.extend(pann_posts)

    log(f"[Community] 총 {len(posts)}개 수집 (DC {len(dc_posts)} + 네이트판 {len(pann_posts)})")
    return posts


def _collect_dcinside() -> list[dict]:
    """DC인사이드 실시간 베스트 제목+추천수를 수집한다."""
    url = "https://m.dcinside.com/board/dcbest"
    posts = []

    try:
        resp = requests.get(url, headers=_get_headers(), timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # 모바일 페이지의 게시글 목록 파싱
        items = soup.select("ul.gall-detail-lst li")
        if not items:
            items = soup.select("div.gall-detail-lnktb")

        for item in items[:20]:
            title_el = item.select_one("span.subjectin, a.lt")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            # 추천수 추출
            recommend = 0
            rec_el = item.select_one("span.ginfo .lkc, span.rt")
            if rec_el:
                try:
                    recommend = int(rec_el.get_text(strip=True).replace(",", ""))
                except ValueError:
                    pass

            posts.append({
                "title": title,
                "recommend": recommend,
                "source": "dcinside_realtime_best",
                "category": "community_male",
            })

        log(f"[DC실베] {len(posts)}개 수집")

    except Exception as e:
        log(f"[DC실베] 수집 실패: {e}")

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
