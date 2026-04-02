"""Instagram 수동 로그인 -> 쿠키 저장 스크립트.

headed 브라우저를 열어 사용자가 직접 로그인하면,
로그인 상태를 자동 감지하고 쿠키를 저장합니다.
"""

import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

COOKIES_FILE = Path(__file__).parent.parent / ".instagram_cookies.json"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()
        await page.goto("https://www.instagram.com/accounts/login/")

        print("=" * 50)
        print("Browser opened. Please log in to Instagram.")
        print("Waiting for login (auto-detect)...")
        print("=" * 50)

        # 로그인 완료를 자동 감지 (최대 3분 대기)
        for i in range(90):
            await page.wait_for_timeout(2000)
            logged_in = (
                await page.query_selector('svg[aria-label="Home"]')
                or await page.query_selector('svg[aria-label="홈"]')
                or await page.query_selector('a[href="/direct/inbox/"]')
            )
            if logged_in:
                print("Login detected!")
                break
            if (i + 1) % 10 == 0:
                print(f"  Still waiting... ({(i+1)*2}s)")
        else:
            print("Timeout (3min). Saving cookies anyway.")

        # 쿠키 저장
        cookies = await context.cookies()
        COOKIES_FILE.write_text(
            json.dumps(cookies, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Cookies saved: {COOKIES_FILE}")
        print(f"Cookie count: {len(cookies)}")
        print("Done! Browser closing in 3 seconds...")
        await page.wait_for_timeout(3000)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
