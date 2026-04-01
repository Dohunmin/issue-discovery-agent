import asyncio
import json
from playwright.async_api import async_playwright
from src.config import INSTAGRAM_SEED_ACCOUNTS, INSTAGRAM_COOKIES


async def collect_instagram() -> list[dict]:
    """인스타그램 시드 계정의 최근 게시물 캡션을 수집한다."""
    posts = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )

        # 쿠키가 있으면 세션 주입
        if INSTAGRAM_COOKIES:
            try:
                cookies = json.loads(INSTAGRAM_COOKIES)
                await context.add_cookies(cookies)
            except json.JSONDecodeError:
                print("[Instagram] 쿠키 파싱 실패, 비로그인 모드로 진행")

        page = await context.new_page()

        for account in INSTAGRAM_SEED_ACCOUNTS:
            account_posts = await _scrape_account(page, account)
            posts.extend(account_posts)

        await browser.close()

    print(f"[Instagram] 총 {len(posts)}개 게시물 수집 완료")
    return posts


async def _scrape_account(page, account: str) -> list[dict]:
    """개별 계정의 최근 게시물을 수집한다."""
    posts = []
    url = f"https://www.instagram.com/{account}/"

    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)

        # 게시물 링크 수집 (최근 6개)
        post_links = await page.eval_on_selector_all(
            'a[href*="/p/"]',
            "els => els.slice(0, 6).map(el => el.href)"
        )

        for link in post_links:
            try:
                await page.goto(link, wait_until="networkidle", timeout=20000)
                await page.wait_for_timeout(1500)

                # 캡션 추출
                caption = ""
                caption_el = await page.query_selector('h1[dir="auto"]')
                if caption_el:
                    caption = await caption_el.inner_text()

                if not caption:
                    # 대체 셀렉터
                    caption_el = await page.query_selector(
                        'div[class*="Caption"] span'
                    )
                    if caption_el:
                        caption = await caption_el.inner_text()

                if caption:
                    # 해시태그 추출
                    hashtags = [
                        word for word in caption.split()
                        if word.startswith("#")
                    ]
                    posts.append({
                        "caption": caption,
                        "account": account,
                        "hashtags": hashtags,
                        "url": link,
                        "likes": 0,
                        "comments": 0,
                        "posted_at": "",
                    })
            except Exception as e:
                print(f"[Instagram] 게시물 수집 실패 ({link}): {e}")

    except Exception as e:
        print(f"[Instagram] {account} 접근 실패: {e}")

    return posts


def collect_instagram_sync() -> list[dict]:
    """동기 래퍼."""
    return asyncio.run(collect_instagram())
