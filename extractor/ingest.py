import os
import re
import ssl
import time
from html import unescape
from typing import List
from urllib.error import URLError
from urllib.request import Request, urlopen

import requests
import urllib3
from dotenv import load_dotenv

# ctbcbank.com has a cert missing the Subject Key Identifier extension; suppress
# the InsecureRequestWarning emitted when cert_reqs='CERT_NONE' is in use.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


DEFAULT_REAL_SOURCE_URLS = [
    "https://www.esunbank.com/zh-tw/personal/credit-card",
    "https://www.cathay-cube.com.tw/cathaybk/personal/product/credit-card/cards",
]


def get_raw_promotions(source: str = "mock") -> List[str]:
    """Return mock raw promotion text until real bank ingestion is implemented."""
    if source != "mock":
        return []

    return [
        """
        Bank: CTBC
        Bank Name: 中國信託
        Card Code: CTBC_DEMO_ONLINE
        Card Name: 中國信託 示例網購卡
        Promotion: 春季線上訂票回饋
        Category: ONLINE
        Cashback Type: PERCENT
        Cashback Value: 3.0
        Min Amount: 500
        Max Cashback: 300
        Frequency Limit: MONTHLY
        Requires Registration: true
        Valid From: 2026-03-01
        Valid Until: 2026-06-30
        Conditions: 需登錄活動; LOCATION_ONLY:TAIPEI; trip.com 線上訂票適用
        Excluded Conditions: LOCATION:KAOHSIUNG
        Source URL: https://example.com/promotions/ctbc-online-spring
        Apply URL: https://example.com/cards/ctbc-demo-online
        Annual Fee: 1800
        Status: ACTIVE
        """,
        """
        Bank: CATHAY
        Bank Name: 國泰世華
        Card Code: CATHAY_DEMO_LIFESTYLE
        Card Name: 國泰世華 示例生活卡
        Promotion: 海外平台旅遊刷卡回饋
        Category: OVERSEAS
        Cashback Type: PERCENT
        Cashback Value: 2.5
        Min Amount: 1
        Max Cashback: 500
        Frequency Limit: MONTHLY
        Requires Registration: false
        Valid From: 2026-01-01
        Valid Until: 2026-08-31
        Conditions: 海外一般消費適用; 以外幣結帳回饋優先
        Excluded Conditions:
        Source URL: https://example.com/promotions/cathay-overseas
        Apply URL: https://example.com/cards/cathay-demo-lifestyle
        Annual Fee: 1800
        Status: ACTIVE
        """,
        """
        Mega Sale! 50% off everything!
        Come visit us today.
        """,
    ]


def get_real_source_urls() -> List[str]:
    return list(DEFAULT_REAL_SOURCE_URLS)


def fetch_real_page(url: str, timeout: int = 20) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except URLError as error:
        if isinstance(error.reason, ssl.SSLCertVerificationError):
            insecure_context = ssl._create_unverified_context()
            with urlopen(request, timeout=timeout, context=insecure_context) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace")
        raise


def fetch_with_playwright(url: str, timeout: int = 60) -> str:
    """Fetch a JS-challenge-protected page using a local Playwright Chromium browser.

    Required once after adding playwright:
        uv add playwright
        uv run playwright install chromium

    Unlike Cloudflare Browser Rendering, this uses a real browser on the local
    machine's IP, which passes bot-protection systems (PerimeterX, Akamai Bot
    Manager) that block data-centre IPs.  ctbcbank.com falls into this category.
    """
    import asyncio

    async def _fetch() -> str:
        from playwright.async_api import async_playwright
        try:
            from playwright_stealth import stealth_async  # type: ignore[import-untyped]
            _has_stealth = True
        except ImportError:
            _has_stealth = False

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            ctx = await browser.new_context(
                locale="zh-TW",
                extra_http_headers={"Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8"},
                ignore_https_errors=True,
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/135.0.0.0 Safari/537.36"
                ),
            )
            page = await ctx.new_page()
            if _has_stealth:
                await stealth_async(page)
            await page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
            content = await _get_stable_page_content(page)
            await browser.close()
            return content

    return asyncio.run(_fetch())


async def _get_stable_page_content(page, attempts: int = 4, settle_ms: int = 800) -> str:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            await page.wait_for_timeout(settle_ms)
            await page.wait_for_load_state("domcontentloaded", timeout=5000)
            return await page.content()
        except Exception as error:
            last_error = error
            # Some CTBC pages redirect again after networkidle; give them a brief
            # chance to settle before retrying the DOM snapshot.
            if attempt == attempts - 1:
                break
            await page.wait_for_timeout(settle_ms * (attempt + 1))
    if last_error is not None:
        raise last_error
    raise RuntimeError("Unable to capture stable page content")


def fetch_with_cloudscraper(url: str, timeout: int = 30) -> str:
    """Alias kept for backwards compatibility — delegates to fetch_with_playwright."""
    return fetch_with_playwright(url, timeout=timeout)


def fetch_rendered_page(url: str, timeout: int = 90) -> str:
    """Fetch fully rendered HTML via Cloudflare Browser Rendering API.

    Requires CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN in .env or environment.
    """
    load_dotenv()
    account_id = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    api_token = os.environ["CLOUDFLARE_API_TOKEN"]

    api_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/browser-rendering/content"
    for attempt in range(3):
        response = requests.post(
            api_url,
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            },
            json={
                "url": url,
                "gotoOptions": {"waitUntil": "networkidle0", "timeout": 60000},
            },
            timeout=timeout,
        )
        if response.status_code == 429 and attempt < 2:
            wait = 10 * (attempt + 1)
            time.sleep(wait)
            continue
        response.raise_for_status()
        return response.json()["result"]


def extract_page_summary(html: str) -> str:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    title = unescape(title_match.group(1)).strip() if title_match else ""

    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    snippet = text[:500]

    if title:
        return f"TITLE: {title}\nSNIPPET: {snippet}"
    return f"SNIPPET: {snippet}"
