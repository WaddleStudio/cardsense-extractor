from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List

from extractor import ingest
from extractor.html_utils import collect_links, collapse_text, html_to_lines
from extractor.page_extractors import SectionedPageConfig, extract_sectioned_page
from extractor.promotion_rules import (
    build_conditions,
    build_summary,
    classify_recommendation_scope,
    clean_offer_text,
    dedupe_promotions,
    extract_cap,
    extract_date_range,
    extract_frequency_limit,
    extract_min_amount,
    extract_reward,
    infer_category,
    infer_channel,
    normalize_promotion_title,
)


CARD_LIST_URL = "https://www.taishinbank.com.tw/TSB/personal/credit/intro/overview/index.html"
BASE_URL = "https://www.taishinbank.com.tw"
BANK_CODE = "TAISHIN"
BANK_NAME = "台新銀行"

CATEGORY_SIGNALS = {
    "OVERSEAS": [("日本", 4), ("韓國", 4), ("海外", 4), ("外幣", 3), ("航空", 3), ("旅遊", 3), ("旅行", 3), ("飯店", 3), ("住宿", 3), ("機場", 2), ("日圓", 2), ("韓圓", 2), ("國泰航空", 4), ("里數", 3), ("亞洲萬里通", 4)],
    "ONLINE": [("Booking", 3), ("Agoda", 3), ("Hotels.com", 3), ("Expedia", 3), ("Klook", 3), ("KKday", 3), ("PChome", 4), ("蝦皮", 4), ("網購", 4), ("LINE Pay", 3), ("Uber Eats", 3), ("網頁", 2), ("網站", 2), ("平台", 1), ("APP", 1), ("街口", 3), ("台新Pay", 3)],
    "DINING": [("餐飲", 4), ("餐廳", 3), ("咖啡", 2), ("壽司", 2), ("美饌", 3)],
    "TRANSPORT": [("交通", 4), ("乘車", 4), ("高鐵", 4), ("台鐵", 4), ("捷運", 4), ("北捷", 4), ("巴士", 3), ("TAXI", 4), ("機場接送", 4), ("大眾交通", 4), ("加油", 2), ("中油", 2)],
    "SHOPPING": [("百貨", 3), ("新光三越", 5), ("購物", 3), ("免稅", 2), ("商圈", 2), ("OUTLET", 2), ("全聯", 5), ("昇恆昌", 4), ("免稅店", 4)],
    "GROCERY": [("家樂福", 5), ("全聯", 5), ("超市", 4), ("量販", 3)],
    "ENTERTAINMENT": [("影城", 4), ("電影", 4), ("串流", 4), ("購票", 2), ("演唱會", 4), ("威秀", 4), ("新光影城", 5), ("國賓影城", 5), ("friDay", 4), ("影音", 3)],
}

CHANNEL_SIGNALS = {
    "ONLINE": [("APP", 3), ("網站", 3), ("網頁", 3), ("網購", 4), ("Booking", 4), ("Agoda", 4), ("Hotels.com", 4), ("Expedia", 4), ("Klook", 4), ("KKday", 4), ("PChome", 4), ("蝦皮", 4), ("LINE Pay", 3), ("台新Pay", 3), ("電子支付", 3), ("乘車碼", 2), ("Richart", 2), ("街口", 3)],
    "OFFLINE": [("實體門市", 4), ("實體店面", 4), ("實體商店", 4), ("店面", 3), ("門市", 3), ("店家", 3), ("商圈", 3), ("商店", 2), ("百貨", 2), ("餐廳", 2), ("加油站", 3), ("直營站", 3), ("搭乘", 2), ("掃碼付", 2), ("TWQR", 2), ("臨櫃", 2), ("實體卡", 3), ("實體", 1)],
    "ALL": [("一般消費", 4), ("國內外一般消費", 5), ("不限通路", 4), ("國內外", 2)],
}

SUMMARY_NOISE_TOKENS = ("活動詳情", "注意事項", "立即登錄", "了解更多", "專屬網頁", "詳情請參閱", "活動請詳", "官網辦法")
GENERIC_TITLE_TOKENS = {"【活動一】", "【活動二】", "【活動三】", "活動一", "活動二", "活動三", "優惠", "回饋", "滿額活動"}

PAGE_CONFIG = SectionedPageConfig(
    section_headings=frozenset(
        {
            "卡片特色",
            "優惠活動",
            "優惠訊息",
            "申請條件",
            "年費公告",
            "重要公告",
            "社群總覽",
            "用卡貼心功能",
            "Additional Links",
        }
    ),
    active_sections=frozenset({"卡片特色", "優惠活動", "優惠訊息"}),
    subsection_skip=frozenset(
        {
            "卡片特色",
            "優惠活動",
            "優惠訊息",
            "申請條件",
            "年費公告",
            "重要公告",
            "社群總覽",
            "用卡貼心功能",
            "Additional Links",
            "注意事項",
            "活動詳情",
            "立即登錄",
            "了解更多",
            "專屬網頁",
            "申辦",
            "申請",
            "申請資格",
            "年費收費標準",
            "服務介紹",
            "限時活動",
            "新戶",
            "舊戶",
            "新戶首刷禮",
            "加碼贈",
        }
    ),
    ignored_subsection_prefixes=("活動期間", "本活動", "活動回饋", "1.", "2.", "3.", "【"),
    offer_body_min_length=30,
    annual_fee_signal_tokens=("首年免年費", "年費"),
    application_requirement_tokens=("年滿18歲", "年滿15歲", "財力證明", "申辦", "所需文件"),
    ignored_offer_title_tokens=("立即申辦", "道路救援", "旅遊平安保險", "旅遊平安險", "飛行優先禮遇", "用卡貼心功能", "卡號速取"),
)

ONLINE_PRIORITY_TOKENS = ("行動支付", "網路消費", "APP", "LINE Pay", "台新Pay", "電子支付", "平台", "網頁", "網站", "Richart", "街口")
OFFLINE_PRIORITY_TOKENS = ("實體商店", "門市", "店面", "機場接送", "搭乘", "餐廳", "百貨", "飯店", "臨櫃", "實體卡")


@dataclass
class CardRecord:
    card_code: str
    card_name: str
    detail_url: str
    apply_url: str | None
    annual_fee_summary: str | None
    application_requirements: List[str]
    sections: List[str]


def list_taishin_cards() -> List[CardRecord]:
    html = ingest.fetch_rendered_page(CARD_LIST_URL)

    seen: set[str] = set()
    cards: List[CardRecord] = []

    # Use regex to find card links with itemprop="name"
    pattern = re.compile(
        r'<a[^>]*href="(/TSB/personal/credit/intro/overview/(?:cg\d+/card\d+)[^"]*)"[^>]*>.*?'
        r'<p[^>]*itemprop="name"[^>]*>([^<]+)</p>',
        re.DOTALL,
    )
    for match in pattern.finditer(html):
        path = match.group(1)
        card_name = collapse_text(match.group(2))

        if not card_name:
            continue

        detail_url = f"{BASE_URL}{path}"
        if detail_url in seen:
            continue
        seen.add(detail_url)

        cards.append(
            CardRecord(
                card_code=_build_card_code(path),
                card_name=card_name,
                detail_url=detail_url,
                apply_url=None,
                annual_fee_summary=None,
                application_requirements=[],
                sections=[],
            )
        )

    return cards


def extract_card_promotions(card: CardRecord) -> tuple[CardRecord, List[Dict[str, object]]]:
    html = ingest.fetch_rendered_page(card.detail_url)
    links = collect_links(html, card.detail_url)
    lines = html_to_lines(html)
    extracted = extract_sectioned_page(lines, links, PAGE_CONFIG)

    enriched_card = CardRecord(
        card_code=card.card_code,
        card_name=extracted.card_name or card.card_name,
        detail_url=card.detail_url,
        apply_url=extracted.apply_url,
        annual_fee_summary=extracted.annual_fee_summary,
        application_requirements=extracted.application_requirements,
        sections=extracted.sections,
    )

    promotions: List[Dict[str, object]] = []
    for block in extracted.offer_blocks:
        clean_title = _normalize_promotion_title(enriched_card.card_name, block.title, block.body)
        clean_body = clean_offer_text(block.body)

        reward = _extract_reward(clean_title, clean_body)
        if reward is None:
            continue

        valid_from, valid_until = extract_date_range(clean_body)
        if not valid_from or not valid_until:
            continue

        min_amount = extract_min_amount(clean_body)
        max_cashback = extract_cap(clean_body)
        requires_registration = "登錄" in clean_body
        frequency_limit = extract_frequency_limit(clean_body)
        summary = build_summary(
            clean_title,
            clean_body,
            valid_from,
            valid_until,
            min_amount,
            max_cashback,
            requires_registration,
            summary_noise_tokens=SUMMARY_NOISE_TOKENS,
        )
        category = _infer_category(clean_title, clean_body)
        recommendation_scope = classify_recommendation_scope(clean_title, clean_body, category)
        conditions = build_conditions(clean_body, enriched_card.application_requirements, requires_registration)

        promotions.append(
            {
                "title": f"{enriched_card.card_name} {clean_title}",
                "cardCode": enriched_card.card_code,
                "cardName": enriched_card.card_name,
                "cardStatus": "ACTIVE",
                "annualFee": _extract_annual_fee_amount(enriched_card.annual_fee_summary),
                "applyUrl": enriched_card.apply_url,
                "bankCode": BANK_CODE,
                "bankName": BANK_NAME,
                "category": category,
                "channel": _infer_channel(clean_title, clean_body),
                "cashbackType": reward["type"],
                "cashbackValue": reward["value"],
                "minAmount": min_amount,
                "maxCashback": max_cashback,
                "frequencyLimit": frequency_limit,
                "requiresRegistration": requires_registration,
                "recommendationScope": recommendation_scope,
                "validFrom": valid_from,
                "validUntil": valid_until,
                "conditions": conditions,
                "excludedConditions": [],
                "sourceUrl": enriched_card.detail_url,
                "summary": summary,
                "status": "ACTIVE",
            }
        )

    return enriched_card, _dedupe_promotions(promotions)


def _build_card_code(path: str) -> str:
    # Extract cg and card parts from path like /TSB/personal/credit/intro/overview/cg003/card001/
    match = re.search(r"(cg\d+)/(card\d+)", path, re.IGNORECASE)
    if match:
        cg = match.group(1).upper()
        card = match.group(2).upper()
        return f"TAISHIN_{cg}_{card}"
    slug = path.rstrip("/").split("/")[-1]
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", slug).strip("_").upper()
    return f"TAISHIN_{normalized}"


def _normalize_promotion_title(card_name: str, raw_title: str, raw_body: str) -> str:
    return normalize_promotion_title(
        card_name,
        raw_title,
        raw_body,
        generic_title_tokens=GENERIC_TITLE_TOKENS | {"立即申辦", "加碼贈", "新戶首刷禮", "基本回饋", "一般消費回饋"},
        summary_noise_tokens=SUMMARY_NOISE_TOKENS,
        bank_suffixes=(BANK_NAME,),
    )


def _dedupe_promotions(promotions: List[Dict[str, object]]) -> List[Dict[str, object]]:
    return dedupe_promotions(promotions)


def _extract_annual_fee_amount(summary: str | None) -> int:
    if not summary:
        return 0
    match = re.search(r"正卡\s*(?:NT\$?)?\s*([\d,]+)\s*元?", summary)
    if match:
        return int(match.group(1).replace(",", ""))
    match = re.search(r"年費\s*(?:NT\$?)?\s*([\d,]+)\s*元?", summary)
    if match:
        return int(match.group(1).replace(",", ""))
    match = re.search(r"NT\$?\s*([\d,]+)", summary)
    if match:
        return int(match.group(1).replace(",", ""))
    return 0


_extract_reward = extract_reward


def _infer_category(title: str, body: str) -> str:
    return infer_category(title, body, CATEGORY_SIGNALS, overseas_category="OVERSEAS")


def _infer_channel(title: str, body: str) -> str:
    text = f"{title} {body}"
    if any(token in text for token in ONLINE_PRIORITY_TOKENS) and not any(token in text for token in OFFLINE_PRIORITY_TOKENS):
        return "ONLINE"
    if any(token in text for token in OFFLINE_PRIORITY_TOKENS) and not any(token in text for token in ONLINE_PRIORITY_TOKENS):
        return "OFFLINE"
    return infer_channel(title, body, CHANNEL_SIGNALS)
