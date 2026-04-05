from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List

from extractor import ingest
from extractor.benefit_plans import apply_plan_subcategory_hint, infer_plan_id
from extractor.html_utils import collect_links, collapse_text, html_to_lines
from extractor.normalize import clean_card_name, infer_eligibility_type
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
    infer_subcategory,
    normalize_promotion_title,
    SUBCATEGORY_SIGNALS,
)


CARD_LIST_URL = "https://www.esunbank.com/zh-tw/personal/credit-card/intro"
BANK_CODE = "ESUN"
BANK_NAME = "玉山銀行"

CATEGORY_SIGNALS = {
    "OVERSEAS": [("日本", 4), ("韓國", 4), ("海外", 4), ("外幣", 3), ("航空", 3), ("旅遊", 3), ("旅行", 3), ("飯店", 3), ("住宿", 3), ("機場", 2), ("日圓", 2), ("韓圓", 2)],
    "ONLINE": [("Booking", 3), ("Agoda", 3), ("Hotels.com", 3), ("Expedia", 3), ("Klook", 3), ("KKday", 3), ("PChome", 4), ("蝦皮", 4), ("網購", 4), ("LINE Pay", 3), ("Uber Eats", 3), ("網頁", 2), ("網站", 2), ("平台", 1), ("APP", 1)],
    "DINING": [("餐飲", 4), ("餐廳", 3), ("咖啡", 2), ("壽司", 2), ("爭鮮", 3), ("星巴克", 2), ("熟成紅茶", 2)],
    "TRANSPORT": [("交通", 4), ("乘車", 4), ("高鐵", 4), ("台鐵", 4), ("捷運", 4), ("巴士", 3), ("TAXI", 4), ("機場接送", 4), ("大眾交通", 4), ("Suica", 4), ("加油", 2), ("中油", 2)],
    "SHOPPING": [("百貨", 3), ("新光三越", 5), ("購物", 3), ("購物園區", 4), ("免稅", 2), ("商圈", 2), ("OUTLET", 2)],
    "GROCERY": [("家樂福", 5), ("全聯", 5), ("超市", 4), ("量販", 3)],
    "ENTERTAINMENT": [("影城", 4), ("電影", 4), ("串流", 4), ("購票", 2), ("演唱會", 4), ("轉播", 2), ("健身房", 2), ("學習平台", 2)],
}

CHANNEL_SIGNALS = {
    "ONLINE": [("APP", 3), ("網站", 3), ("網頁", 3), ("網購", 4), ("Booking", 4), ("Agoda", 4), ("Hotels.com", 4), ("Expedia", 4), ("Klook", 4), ("KKday", 4), ("PChome", 4), ("蝦皮", 4), ("LINE Pay", 3), ("玉山Wallet", 3), ("電子支付", 3), ("乘車碼", 2)],
    "OFFLINE": [("實體門市", 4), ("實體店面", 4), ("實體商店", 4), ("店面", 3), ("門市", 3), ("店家", 3), ("商圈", 3), ("商店", 2), ("百貨", 2), ("餐廳", 2), ("加油站", 3), ("直營站", 3), ("搭乘", 2), ("掃碼付", 2), ("TWQR", 2)],
    "ALL": [("一般消費", 4), ("國內外一般消費", 5), ("不限通路", 4), ("國內外", 2)],
}

SUMMARY_NOISE_TOKENS = ("活動詳情", "注意事項", "立即登錄", "了解更多", "專屬網頁", "詳情請參閱")
GENERIC_TITLE_TOKENS = {"【活動一】", "【活動二】", "【活動三】", "活動一", "活動二", "活動三", "優惠", "回饋", "滿額活動"}

PAGE_CONFIG = SectionedPageConfig(
    section_headings=frozenset(
        {
            "卡片介紹",
            "卡片特色",
            "專屬優惠",
            "Pi拍錢包加碼",
            "卡友禮遇服務",
            "卡片須知",
            "行動支付新體驗",
            "玉山Wallet 卡友必備APP",
            "常見問題",
            "聯繫客服",
            "Additional Links",
        }
    ),
    active_sections=frozenset({"卡片特色", "專屬優惠", "Pi拍錢包加碼", "卡友禮遇服務"}),
    subsection_skip=frozenset(
        {
            "卡片介紹",
            "卡片特色",
            "專屬優惠",
            "Pi拍錢包加碼",
            "卡友禮遇服務",
            "卡片須知",
            "行動支付新體驗",
            "玉山Wallet 卡友必備APP",
            "常見問題",
            "聯繫客服",
            "Additional Links",
            "注意事項",
            "活動詳情",
            "立即登錄",
            "了解更多",
            "專屬網頁",
            "申辦",
            "申請",
        }
    ),
    title_prefixes=("玉山",),
    annual_fee_signal_tokens=("首年免年費", "年費"),
    application_requirement_tokens=("年滿18歲", "年滿15歲", "財力證明", "申辦雙幣卡須", "臺外幣帳戶", "同一持卡人"),
    ignored_offer_title_tokens=("立即申辦", "道路救援", "旅遊保障", "白金會員禮遇", "專屬禮遇"),
)

ONLINE_PRIORITY_TOKENS = ("行動支付", "網路消費", "APP", "LINE Pay", "玉山Wallet", "電子支付", "平台", "網頁", "網站")
OFFLINE_PRIORITY_TOKENS = ("實體商店", "門市", "店面", "購物園區", "機場接送", "搭乘", "餐廳", "百貨", "飯店")


@dataclass
class CardRecord:
    card_code: str
    card_name: str
    detail_url: str
    apply_url: str | None
    annual_fee_summary: str | None
    application_requirements: List[str]
    sections: List[str]


def list_esun_cards() -> List[CardRecord]:
    html = ingest.fetch_real_page(CARD_LIST_URL)
    links = collect_links(html, CARD_LIST_URL)

    seen: set[str] = set()
    cards: List[CardRecord] = []
    for link in links:
        href = link["href"]
        if "/personal/credit-card/intro/" not in href:
            continue
        if "#" in href:
            href = href.split("#", 1)[0]
        if href in seen:
            continue
        seen.add(href)

        text = link["text"]
        if not text:
            continue
        card_name = clean_card_name(_extract_card_name_from_link_text(text))
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
        card_name=clean_card_name(extracted.card_name or card.card_name),
        detail_url=card.detail_url,
        apply_url=extracted.apply_url,
        annual_fee_summary=extracted.annual_fee_summary,
        application_requirements=extracted.application_requirements,
        sections=extracted.sections,
    )

    promotions: List[Dict[str, object]] = []
    eligibility_type = infer_eligibility_type(enriched_card.card_name)
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
        subcategory = infer_subcategory(clean_title, clean_body, category, SUBCATEGORY_SIGNALS)
        plan_id = infer_plan_id(enriched_card.card_code, category, title=clean_title, subcategory=subcategory)
        category, subcategory = apply_plan_subcategory_hint(plan_id, category, subcategory)
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
                "subcategory": subcategory,
                "channel": _infer_channel(clean_title, clean_body),
                "cashbackType": reward["type"],
                "cashbackValue": reward["value"],
                "minAmount": min_amount,
                "maxCashback": max_cashback,
                "frequencyLimit": frequency_limit,
                "requiresRegistration": requires_registration,
                "recommendationScope": recommendation_scope,
                "eligibilityType": eligibility_type,
                "validFrom": valid_from,
                "validUntil": valid_until,
                "conditions": conditions,
                "excludedConditions": [],
                "sourceUrl": enriched_card.detail_url,
                "summary": summary,
                "status": "ACTIVE",
                "planId": plan_id,
            }
        )

    return enriched_card, _dedupe_promotions(promotions)


def _extract_card_name_from_link_text(text: str) -> str:
    cleaned = collapse_text(text)
    if not cleaned:
        return ""
    if "了解更多" in cleaned:
        cleaned = cleaned.split("了解更多", 1)[0].strip()
    for splitter in ["  ", "最高", "國內", "日本", "不限", "公司戶"]:
        if splitter in cleaned:
            candidate = cleaned.split(splitter, 1)[0].strip()
            if 2 <= len(candidate) <= 30:
                return candidate
    return cleaned[:30].strip()




def _build_card_code(url: str) -> str:
    slug = url.rstrip("/").split("/")[-1]
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", slug).strip("_").upper()
    return f"ESUN_{normalized}"


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
    match = re.search(r"正卡\s*([\d,]+)元", summary)
    if match:
        return int(match.group(1).replace(",", ""))
    match = re.search(r"年費\s*([\d,]+)元", summary)
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
