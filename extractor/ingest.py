import os
import re
import ssl
import time
from html import unescape
from typing import List
from urllib.error import URLError
from urllib.request import Request, urlopen

import requests
from dotenv import load_dotenv


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
