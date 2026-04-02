import asyncio
import json
import random
from pathlib import Path
from playwright.async_api import async_playwright, BrowserContext
from src.config import (
    INSTAGRAM_SEED_ACCOUNTS,
    INSTAGRAM_USERNAME,
    INSTAGRAM_PASSWORD,
)
from src.logger import log

POSTS_TO_SCAN = 5
COOKIES_FILE = Path(__file__).parent.parent.parent / ".instagram_cookies.json"


async def _human_delay(min_s: float = 1.5, max_s: float = 4.0) -> None:
    """사람처럼 랜덤한 딜레이를 준다."""
    await asyncio.sleep(random.uniform(min_s, max_s))


async def _scroll_page(page) -> None:
    """페이지를 살짝 스크롤한다 (사람 행동 모방)."""
    await page.evaluate("window.scrollBy(0, Math.random() * 300 + 200)")
    await _human_delay(0.5, 1.5)


async def collect_instagram() -> dict[str, list[dict]]:
    """인스타그램 시드 계정의 최근 게시물 캡션을 수집한다."""
    all_posts: dict[str, list[dict]] = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
            locale="ko-KR",
            timezone_id="Asia/Seoul",
        )

        # 로그인 처리
        logged_in = await _ensure_login(context)
        if not logged_in:
            log("[Instagram] 로그인 실패 - 비로그인 모드로 진행")

        page = await context.new_page()

        # 홈 먼저 방문 (사람 패턴)
        await page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=20000)
        await _human_delay(2.0, 4.0)

        for i, account in enumerate(INSTAGRAM_SEED_ACCOUNTS):
            if i > 0:
                # 계정 간 쉬어가기
                await _human_delay(3.0, 6.0)
            account_posts = await _scrape_account(page, account)
            all_posts[account] = account_posts
            captions_count = sum(1 for p in account_posts if p.get("caption"))
            log(f"[Instagram] @{account}: {len(account_posts)}개 수집 (캡션 {captions_count}개)")
            for p in account_posts:
                cap = p.get("caption", "")
                if cap:
                    log(f"  > {cap[:80]}")

        await browser.close()

    total = sum(len(posts) for posts in all_posts.values())
    log(f"[Instagram] 총 {total}개 게시물 수집 완료 (AI 필터링 전)")
    return all_posts


async def _ensure_login(context: BrowserContext) -> bool:
    """쿠키 -> 로그인 순서로 인스타 로그인을 시도한다."""

    if COOKIES_FILE.exists():
        try:
            cookies = json.loads(COOKIES_FILE.read_text(encoding="utf-8"))
            await context.add_cookies(cookies)
            log("[Instagram] 저장된 쿠키 로드 완료")

            page = await context.new_page()
            await page.goto("https://www.instagram.com/", timeout=20000)
            await _human_delay(2.0, 4.0)

            if await _is_logged_in(page):
                log("[Instagram] 쿠키 로그인 성공")
                await page.close()
                return True
            else:
                log("[Instagram] 쿠키 만료됨, 재로그인 시도")
                await page.close()
        except Exception as e:
            log(f"[Instagram] 쿠키 로드 실패: {e}")

    if not INSTAGRAM_USERNAME or not INSTAGRAM_PASSWORD:
        log("[Instagram] 로그인 정보 없음")
        return False

    return await _login_with_credentials(context)


async def _login_with_credentials(context: BrowserContext) -> bool:
    """아이디/비번으로 로그인하고 쿠키를 저장한다."""
    page = await context.new_page()

    try:
        await page.goto("https://www.instagram.com/accounts/login/", timeout=20000)
        await _human_delay(2.0, 4.0)

        await page.fill('input[name="username"]', INSTAGRAM_USERNAME)
        await _human_delay(0.5, 1.0)
        await page.fill('input[name="password"]', INSTAGRAM_PASSWORD)
        await _human_delay(0.5, 1.5)
        await page.click('button[type="submit"]')

        await _human_delay(4.0, 6.0)

        for text in ("나중에 하기", "Not Now"):
            try:
                btn = page.get_by_text(text)
                if await btn.is_visible(timeout=3000):
                    await btn.click()
                    await _human_delay(1.0, 2.0)
            except Exception:
                pass

        if await _is_logged_in(page):
            cookies = await context.cookies()
            COOKIES_FILE.write_text(
                json.dumps(cookies, ensure_ascii=False),
                encoding="utf-8",
            )
            log("[Instagram] 로그인 성공, 쿠키 저장 완료")
            await page.close()
            return True
        else:
            log("[Instagram] 로그인 실패 (2FA 또는 CAPTCHA 필요할 수 있음)")
            await page.close()
            return False

    except Exception as e:
        log(f"[Instagram] 로그인 중 오류: {e}")
        await page.close()
        return False


async def _is_logged_in(page) -> bool:
    """현재 페이지가 로그인 상태인지 확인한다."""
    try:
        logged_in = await page.query_selector('svg[aria-label="Home"]') or \
                    await page.query_selector('svg[aria-label="홈"]') or \
                    await page.query_selector('a[href="/direct/inbox/"]')
        return logged_in is not None
    except Exception:
        return False


async def _scrape_account(page, account: str) -> list[dict]:
    """개별 계정의 최근 게시물 캡션을 수집한다."""
    posts = []
    url = f"https://www.instagram.com/{account}/"

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await _human_delay(2.0, 4.0)
        await _scroll_page(page)

        # 게시물 링크가 로드될 때까지 대기
        for _ in range(3):
            post_links = await page.eval_on_selector_all(
                'a[href*="/p/"]',
                f"els => els.slice(0, {POSTS_TO_SCAN}).map(el => el.href)"
            )
            if post_links:
                break
            await _human_delay(1.5, 3.0)
            await _scroll_page(page)

        for i, link in enumerate(post_links):
            try:
                await _human_delay(1.5, 3.5)
                await page.goto(link, wait_until="domcontentloaded", timeout=20000)
                await _human_delay(2.0, 4.0)

                caption = await _extract_caption(page)
                hashtags = [
                    word for word in caption.split() if word.startswith("#")
                ] if caption else []

                posts.append({
                    "index": i,
                    "caption": caption,
                    "account": account,
                    "hashtags": hashtags,
                    "url": link,
                    "posted_at": "",
                })
            except Exception as e:
                log(f"[Instagram] 게시물 수집 실패 ({link}): {e}")

    except Exception as e:
        log(f"[Instagram] @{account} 접근 실패: {e}")

    return posts


async def _extract_caption(page) -> str:
    """게시물 페이지에서 캡션 텍스트를 추출한다."""
    # 1) meta og:description에서 캡션 추출 (가장 안정적)
    meta = await page.query_selector('meta[property="og:description"]')
    if meta:
        content = await meta.get_attribute("content") or ""
        if ':"' in content or ': "' in content:
            sep = ': "' if ': "' in content else ':"'
            caption = content.split(sep, 1)[-1]
            if caption.endswith('".'):
                caption = caption[:-2]
            elif caption.endswith('"'):
                caption = caption[:-1]
            if len(caption.strip()) > 10:
                return caption.strip()

    # 2) 기존 selector 폴백
    selectors = [
        'h1[dir="auto"]',
        'div[class*="Caption"] span',
        'article span[dir="auto"]',
    ]
    for selector in selectors:
        el = await page.query_selector(selector)
        if el:
            text = await el.inner_text()
            if text and len(text.strip()) > 10:
                return text.strip()
    return ""


def collect_instagram_sync() -> dict[str, list[dict]]:
    """동기 래퍼."""
    return asyncio.run(collect_instagram())
