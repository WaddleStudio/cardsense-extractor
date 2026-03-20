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


CARD_LIST_URL = "https://www.cathaybk.com.tw/cathaybk/personal/product/credit-card/cards/"
BANK_CODE = "CATHAY"
BANK_NAME = "國泰世華"

CATEGORY_SIGNALS = {
    "OVERSEAS": [("海外", 4), ("外幣", 3), ("旅遊", 3), ("航空", 3), ("住宿", 3), ("日本", 2)],
    "ONLINE": [("網購", 4), ("APP", 2), ("LINE Pay", 3), ("行動支付", 4), ("平台", 2)],
    "DINING": [("餐飲", 4), ("餐廳", 3), ("咖啡", 2)],
    "TRANSPORT": [("高鐵", 4), ("台鐵", 4), ("捷運", 4), ("交通", 3), ("加油", 2)],
    "SHOPPING": [("百貨", 3), ("購物", 3), ("商場", 2)],
    "GROCERY": [("超市", 4), ("量販", 3), ("全聯", 3), ("家樂福", 3)],
    "ENTERTAINMENT": [("電影", 3), ("影城", 3), ("串流", 3)],
}

CHANNEL_SIGNALS = {
    "ONLINE": [("APP", 3), ("網站", 3), ("網路", 3), ("網購", 4), ("LINE Pay", 3), ("行動支付", 4)],
    "OFFLINE": [("門市", 3), ("實體", 4), ("店面", 3), ("百貨", 2), ("餐廳", 2)],
    "ALL": [("一般消費", 4), ("國內外一般消費", 5), ("不限通路", 4)],
}

SUMMARY_NOISE_TOKENS = ("活動詳情", "注意事項", "立即登錄", "了解更多", "詳情請參閱")
GENERIC_TITLE_TOKENS = {"優惠", "回饋", "活動", "加碼"}

PAGE_CONFIG = SectionedPageConfig(
    section_headings=frozenset({"卡片權益", "卡片特色", "優惠活動", "專屬禮遇", "注意事項"}),
    active_sections=frozenset({"卡片權益", "卡片特色", "優惠活動", "專屬禮遇"}),
    subsection_skip=frozenset({"注意事項", "活動詳情", "立即申辦", "了解更多"}),
    title_prefixes=("CUBE", "國泰", "亞洲萬里通", "Costco", "蝦皮"),
    annual_fee_signal_tokens=("首年免年費", "年費"),
    application_requirement_tokens=("年滿18歲", "財力證明", "正卡", "附卡"),
    ignored_offer_title_tokens=("立即申辦", "注意事項"),
)


@dataclass
class CardRecord:
    card_code: str
    card_name: str
    detail_url: str
    apply_url: str | None
    annual_fee_summary: str | None
    application_requirements: List[str]
    sections: List[str]


def list_cathay_cards() -> List[CardRecord]:
    html = ingest.fetch_real_page(CARD_LIST_URL)
    links = collect_links(html, CARD_LIST_URL)

    seen: set[str] = set()
    cards: List[CardRecord] = []
    for link in links:
        href = link["href"]
        if "/credit-card/cards/" not in href:
            continue
        if href in seen:
            continue
        seen.add(href)

        card_name = _extract_card_name_from_link_text(link["text"])
        if not card_name:
            continue

        cards.append(
            CardRecord(
                card_code=_build_card_code(href),
                card_name=card_name,
                detail_url=href,
                apply_url=None,
                annual_fee_summary=None,
                application_requirements=[],
                sections=[],
            )
        )

    return cards


def extract_card_promotions(card: CardRecord) -> tuple[CardRecord, List[Dict[str, object]]]:
    html = ingest.fetch_real_page(card.detail_url)
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
        clean_title = normalize_promotion_title(
            enriched_card.card_name,
            block.title,
            block.body,
            generic_title_tokens=GENERIC_TITLE_TOKENS,
            summary_noise_tokens=SUMMARY_NOISE_TOKENS,
            bank_suffixes=(BANK_NAME, "國泰世華銀行"),
        )
        reward = extract_reward(clean_title, block.body)
        if reward is None:
            continue

        valid_from, valid_until = extract_date_range(block.body)
        if not valid_from or not valid_until:
            continue

        requires_registration = "登錄" in block.body
        category = infer_category(clean_title, block.body, CATEGORY_SIGNALS, overseas_category="OVERSEAS")
        recommendation_scope = classify_recommendation_scope(clean_title, block.body, category)
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
                "channel": infer_channel(clean_title, block.body, CHANNEL_SIGNALS),
                "cashbackType": reward["type"],
                "cashbackValue": reward["value"],
                "minAmount": extract_min_amount(block.body),
                "maxCashback": extract_cap(block.body),
                "frequencyLimit": extract_frequency_limit(block.body),
                "requiresRegistration": requires_registration,
                "recommendationScope": recommendation_scope,
                "validFrom": valid_from,
                "validUntil": valid_until,
                "conditions": build_conditions(block.body, enriched_card.application_requirements, requires_registration),
                "excludedConditions": [],
                "sourceUrl": enriched_card.detail_url,
                "summary": build_summary(
                    clean_title,
                    block.body,
                    valid_from,
                    valid_until,
                    extract_min_amount(block.body),
                    extract_cap(block.body),
                    requires_registration,
                    summary_noise_tokens=SUMMARY_NOISE_TOKENS,
                ),
                "status": "ACTIVE",
            }
        )

    return enriched_card, dedupe_promotions(promotions)


def _extract_card_name_from_link_text(text: str) -> str:
    cleaned = collapse_text(text)
    if not cleaned:
        return ""
    for splitter in ["卡", "信用卡", "御璽卡", "世界卡"]:
        if splitter in cleaned:
            head = cleaned.split(splitter, 1)[0].strip()
            if head:
                return f"{head}{splitter}"[:30]
    return cleaned[:30].strip()


def _build_card_code(url: str) -> str:
    slug = url.rstrip("/").split("/")[-1]
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", slug).strip("_").upper()
    return f"CATHAY_{normalized}"


def _extract_annual_fee_amount(summary: str | None) -> int:
    if not summary:
        return 0
    match = re.search(r"年費\s*([\d,]+)元", summary)
    if match:
        return int(match.group(1).replace(",", ""))
    return 0