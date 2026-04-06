"""CTBC (中國信託) credit card extractor.

Uses local Playwright (playwright-stealth) to bypass CTBC's F5 BIG-IP ASM
bot-protection layer.  Cloudflare Browser Rendering and plain HTTP are both
blocked by CTBC; only a real browser on a residential IP passes.

Prerequisites (one-time):
    uv add playwright playwright-stealth
    uv run playwright install chromium

Card listing URL and link patterns verified against ctbcbank.com as of 2026-Q1.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Sequence

from extractor import ingest
from extractor.html_utils import collect_links, collapse_text, html_to_lines
from extractor.normalize import infer_eligibility_type
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
    append_inferred_subcategory_conditions,
    append_inferred_payment_method_conditions,
    append_catalog_review_conditions,
    append_bank_wide_promotion_condition,
    canonicalize_subcategory,
    sanitize_payment_conditions,
    SUBCATEGORY_SIGNALS,
)


CARD_LIST_URL = "https://www.ctbcbank.com/twrbo/zh_tw/cc_index/cc_product/cc_introduction_index.html"
CARD_LIST_JSON_URL = "https://www.ctbcbank.com/content/twrbo/setting/creditcards.cardlist.json"
BASE_URL = "https://www.ctbcbank.com"
# AEM content path prefix used in hrefs on the rendered page
_CONTENT_BASE = "https://www.ctbcbank.com/content/twrbo/zh_tw/cc_index/cc_product/cc_introduction_index"
BANK_CODE = "CTBC"
BANK_NAME = "中國信託銀行"

CATEGORY_SIGNALS = {
    "OVERSEAS": [
        ("日本", 4), ("韓國", 4), ("海外", 4), ("外幣", 3), ("航空", 3),
        ("旅遊", 3), ("旅行", 3), ("飯店", 3), ("住宿", 3), ("機場", 2),
        ("日圓", 2), ("里數", 3), ("亞洲萬里通", 4), ("國際", 2),
        ("Marriott", 4), ("萬豪", 4), ("希爾頓", 4), ("洲際", 4),
    ],
    "ONLINE": [
        ("LINE Pay", 4), ("Booking", 3), ("Agoda", 3), ("Hotels.com", 3),
        ("Klook", 3), ("KKday", 3), ("PChome", 4), ("蝦皮", 4), ("網購", 4),
        ("Uber Eats", 3), ("foodpanda", 3), ("momo", 4), ("網頁", 2),
        ("網站", 2), ("平台", 1), ("APP", 1), ("線上購物", 4), ("網路消費", 4),
        ("CTBC Pay", 3), ("街口", 3),
    ],
    "DINING": [
        ("餐飲", 4), ("餐廳", 3), ("咖啡", 2), ("壽司", 2), ("米其林", 5),
        ("Michelin", 5), ("Costa", 3), ("Starbucks", 3), ("星巴克", 3),
        ("饗樂", 3), ("美饌", 3),
    ],
    "TRANSPORT": [
        ("交通", 4), ("乘車", 4), ("高鐵", 4), ("台鐵", 4), ("臺鐵", 4),
        ("捷運", 4), ("北捷", 4), ("巴士", 3), ("TAXI", 4), ("機場接送", 4),
        ("大眾交通", 4), ("加油", 3), ("中油", 2), ("自助加油", 4),
    ],
    "SHOPPING": [
        ("百貨", 3), ("新光三越", 5), ("購物", 3), ("免稅", 2), ("商圈", 2),
        ("OUTLET", 2), ("家樂福", 5), ("Costco", 5), ("好市多", 5),
        ("昇恆昌", 4), ("免稅店", 4),
    ],
    "GROCERY": [
        ("家樂福", 5), ("全聯", 5), ("超市", 4), ("量販", 3),
        ("全家", 4), ("7-ELEVEN", 4), ("FamilyMart", 4),
    ],
    "ENTERTAINMENT": [
        ("影城", 4), ("電影", 4), ("串流", 4), ("購票", 2),
        ("演唱會", 4), ("威秀", 4), ("Netflix", 4), ("Disney+", 4),
    ],
}

CHANNEL_SIGNALS = {
    "ONLINE": [
        ("APP", 3), ("網站", 3), ("網頁", 3), ("網購", 4),
        ("LINE Pay", 4), ("CTBC Pay", 4), ("街口", 3),
        ("Booking", 4), ("Agoda", 4), ("Hotels.com", 4), ("Expedia", 4),
        ("Klook", 4), ("KKday", 4), ("PChome", 4), ("蝦皮", 4),
        ("電子支付", 3), ("momo購物網", 4), ("線上購物", 4),
        ("Apple Pay", 3), ("Google Pay", 3), ("Samsung Pay", 3),
    ],
    "OFFLINE": [
        ("實體門市", 4), ("實體店面", 4), ("實體商店", 4), ("店面", 3),
        ("門市", 3), ("店家", 3), ("商圈", 3), ("商店", 2), ("百貨", 2),
        ("餐廳", 2), ("加油站", 3), ("直營站", 3), ("搭乘", 2),
        ("實體卡", 3), ("實體", 1), ("店內消費", 4), ("Costco店內", 5),
    ],
    "ALL": [
        ("一般消費", 4), ("國內外一般消費", 5), ("不限通路", 4), ("國內外", 2),
        ("店外一般消費", 3),
    ],
}

SUMMARY_NOISE_TOKENS = (
    "活動詳情", "注意事項", "立即登錄", "了解更多", "專屬網頁",
    "詳情請參閱", "活動請詳", "官網辦法", "立即擁有", "立即申辦",
)
GENERIC_TITLE_TOKENS = {
    "【活動一】", "【活動二】", "【活動三】",
    "活動一", "活動二", "活動三",
    "優惠", "回饋", "滿額活動",
}

PAGE_CONFIG = SectionedPageConfig(
    section_headings=frozenset({
        "卡片特色",
        "最新活動",
        "專屬優惠",
        "優惠活動",
        "優惠訊息",
        "精選優惠",
        "卡片介紹",
        "申請資格",
        "年費說明",
        "重要公告",
        "Additional Links",
    }),
    active_sections=frozenset({
        "卡片特色",
        "最新活動",
        "專屬優惠",
        "優惠活動",
        "優惠訊息",
        "精選優惠",
        "卡片介紹",
    }),
    subsection_skip=frozenset({
        "卡片特色",
        "最新活動",
        "專屬優惠",
        "優惠活動",
        "優惠訊息",
        "精選優惠",
        "卡片介紹",
        "申請資格",
        "年費說明",
        "重要公告",
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
    }),
    ignored_subsection_prefixes=("活動期間", "本活動", "活動回饋", "1.", "2.", "3.", "【"),
    offer_body_min_length=30,
    annual_fee_signal_tokens=("首年免年費", "年費", "正卡"),
    application_requirement_tokens=("年滿18歲", "年滿15歲", "財力證明", "申辦", "所需文件"),
    ignored_offer_title_tokens=(
        "立即申辦", "立即擁有", "道路救援", "旅遊平安保險", "旅遊平安險", "旅行平安保險",
        "飛行優先禮遇", "貴賓室", "停車", "機場接送",
    ),
)

ONLINE_PRIORITY_TOKENS = (
    "行動支付", "網路消費", "APP", "LINE Pay", "CTBC Pay",
    "電子支付", "平台", "網頁", "網站", "街口",
    "Apple Pay", "Google Pay", "Samsung Pay", "線上購物", "網購",
)
OFFLINE_PRIORITY_TOKENS = (
    "實體商店", "門市", "店面", "機場接送", "搭乘",
    "餐廳", "百貨", "飯店", "臨櫃", "實體卡", "店內消費", "自助加油",
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


_SKIP_SLUGS = frozenset({
    "Card_Notice", "card-compare", "index", "cc_introduction_index",
})


def list_ctbc_cards() -> List[CardRecord]:
    import json

    raw = ingest.fetch_real_page(CARD_LIST_JSON_URL)
    data = json.loads(raw)

    cards: List[CardRecord] = []
    seen: set[str] = set()

    for item in data.get("creditCards", []):
        intro_link = item.get("introLink", "")
        if not intro_link:
            continue

        slug_match = re.search(
            r"/cc_introduction_index/([A-Za-z0-9_-]+)\.html$", intro_link
        )
        if not slug_match:
            continue
        slug = slug_match.group(1)
        if slug in _SKIP_SLUGS:
            continue

        detail_url = f"{BASE_URL}{intro_link}"
        if detail_url in seen:
            continue
        seen.add(detail_url)

        card_name = item.get("cardName") or slug

        fee_html = item.get("annualFee") or ""
        fee_text = re.sub(r"<[^>]+>", " ", fee_html).strip()
        annual_fee_summary = re.sub(r"\s+", " ", fee_text).strip() or None

        apply_link = item.get("applyLink") or ""
        apply_url = f"{BASE_URL}{apply_link}" if apply_link else None

        cards.append(
            CardRecord(
                card_code=_build_card_code(slug),
                card_name=card_name,
                detail_url=detail_url,
                apply_url=apply_url,
                annual_fee_summary=annual_fee_summary,
                application_requirements=[],
                sections=[],
            )
        )

    return cards


def extract_card_promotions(card: CardRecord) -> tuple[CardRecord, List[Dict[str, object]]]:
    html = ingest.fetch_with_playwright(card.detail_url)
    links = collect_links(html, card.detail_url)
    lines = html_to_lines(html)
    extracted = extract_sectioned_page(lines, links, PAGE_CONFIG)

    slug = card.card_code.removeprefix("CTBC_").lower()
    # Prefer card.card_name (from JSON API, already correct); fall back to detail page extraction
    resolved_card_name = _clean_ctbc_card_name(card.card_name or extracted.card_name, slug)

    enriched_card = CardRecord(
        card_code=card.card_code,
        card_name=resolved_card_name,
        detail_url=card.detail_url,
        apply_url=card.apply_url or extracted.apply_url,
        annual_fee_summary=card.annual_fee_summary or extracted.annual_fee_summary,
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
        recommendation_scope = classify_recommendation_scope(clean_title, clean_body, category)
        conditions = build_conditions(clean_body, enriched_card.application_requirements, requires_registration)
        conditions = append_inferred_subcategory_conditions(clean_title, clean_body, category, subcategory, conditions)
        conditions = append_inferred_payment_method_conditions(category, subcategory, conditions, clean_title, clean_body)
        conditions = sanitize_payment_conditions(clean_title, clean_body, conditions)
        conditions = append_bank_wide_promotion_condition(
            clean_title,
            clean_body,
            recommendation_scope,
            conditions,
            requires_registration=requires_registration,
            subcategory=subcategory,
        )
        conditions = append_catalog_review_conditions(
            clean_title,
            clean_body,
            recommendation_scope,
            conditions,
            requires_registration=requires_registration,
        )
        subcategory = canonicalize_subcategory(category, subcategory, conditions)
        category, subcategory, channel, recommendation_scope, conditions = _refine_ctbc_promotion(
            card_code=enriched_card.card_code,
            title=clean_title,
            body=clean_body,
            category=category,
            subcategory=subcategory,
            channel=_infer_channel(clean_title, clean_body),
            recommendation_scope=recommendation_scope,
            requires_registration=requires_registration,
            conditions=conditions,
        )

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
                "channel": channel,
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
                "sourceUrl": card.detail_url,
                "summary": summary,
                "status": "ACTIVE",
            }
        )

    return enriched_card, _dedupe_promotions(promotions)


def _build_card_code(slug: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", slug).strip("_").upper()
    return f"CTBC_{normalized}"


def _clean_ctbc_card_name(name: str, slug: str = "") -> str:
    """Strip CTBC-specific suffixes (e.g. '－中國信託銀行', '中國信託' prefix) from card names."""
    # Remove trailing bank name suffixes
    cleaned = re.sub(r"\s*[-－]\s*中國信託(?:銀行|商業銀行)?\s*$", "", name).strip()
    # Remove leading bank name prefix if present
    cleaned = re.sub(r"^中國信託(?:銀行|商業銀行)?\s*[-－]?\s*", "", cleaned).strip()
    if not cleaned or cleaned in ("信用卡", "中國信託"):
        import logging
        logging.warning(
            "CTBC: card name resolved to generic value after cleaning; slug=%r — "
            "check whether the page omits the name or the parser missed it.",
            slug or "(no slug)",
        )
        return slug or name
    return cleaned


def _normalize_promotion_title(card_name: str, raw_title: str, raw_body: str) -> str:
    return normalize_promotion_title(
        card_name,
        raw_title,
        raw_body,
        generic_title_tokens=GENERIC_TITLE_TOKENS | {"立即申辦", "立即擁有", "加碼贈", "新戶首刷禮", "基本回饋", "一般消費回饋"},
        summary_noise_tokens=SUMMARY_NOISE_TOKENS,
        bank_suffixes=(BANK_NAME, "中國信託商業銀行", "中國信託"),
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


def _extract_reward(title: str, text: str) -> Dict[str, object] | None:
    # Filter out condition-threshold percentages before extraction.
    _threshold_pct = r"(?:團費|消費金額|消費額|金額|費用)\s*\d+(?:\.\d+)?%\s*以上"
    # Also filter "80%團費" (percentage before keyword) — a payment-threshold, not reward.
    _pct_before_keyword = r"\d+(?:\.\d+)?%\s*(?:團費|交通工具費用|旅遊團費|機票)"
    # Filter "100%折抵" — a redemption ratio, not a cashback rate.
    _redemption_ratio = r"\d+(?:\.\d+)?%\s*折抵"
    # Filter exchange-rate descriptions like "1A金=NT1元" — currency definition, not reward.
    _exchange_rate = r"\d+\s*A金\s*=\s*NT\$?\s*[\d,]+\s*元"
    _filter = re.compile(f"{_threshold_pct}|{_pct_before_keyword}|{_redemption_ratio}|{_exchange_rate}")
    filtered_text = _filter.sub("", text)
    filtered_title = _filter.sub("", title)
    return extract_reward(filtered_title, filtered_text)


def _infer_category(title: str, body: str) -> str:
    return infer_category(title, body, CATEGORY_SIGNALS, overseas_category="OVERSEAS")


def _infer_channel(title: str, body: str) -> str:
    text = f"{title} {body}"
    if any(token in text for token in ONLINE_PRIORITY_TOKENS) and not any(token in text for token in OFFLINE_PRIORITY_TOKENS):
        return "ONLINE"
    if any(token in text for token in OFFLINE_PRIORITY_TOKENS) and not any(token in text for token in ONLINE_PRIORITY_TOKENS):
        return "OFFLINE"
    return infer_channel(title, body, CHANNEL_SIGNALS)


def _refine_ctbc_promotion(
    *,
    card_code: str,
    title: str,
    body: str,
    category: str,
    subcategory: str,
    channel: str,
    recommendation_scope: str,
    requires_registration: bool,
    conditions: Sequence[Dict[str, str]],
) -> tuple[str, str, str, str, List[Dict[str, str]]]:
    text = collapse_text(f"{title} {body}")
    refined_conditions = [dict(condition) for condition in conditions]

    if "指定網購平台最高5%回饋" in text and "蝦皮購物" in text and "momo購物網" in text:
        category = "ONLINE"
        subcategory = "ECOMMERCE"
        channel = "ONLINE"
        refined_conditions = _replace_payment_conditions(
            refined_conditions,
            [
                {"type": "PAYMENT_PLATFORM", "value": "APPLE_PAY", "label": "Apple Pay"},
                {"type": "PAYMENT_PLATFORM", "value": "GOOGLE_PAY", "label": "Google Pay"},
                {"type": "PAYMENT_PLATFORM", "value": "SAMSUNG_PAY", "label": "Samsung Pay"},
            ],
        )
        refined_conditions = _merge_conditions(
            refined_conditions,
            [
                {"type": "ECOMMERCE_PLATFORM", "value": "SHOPEE", "label": "蝦皮購物"},
                {"type": "ECOMMERCE_PLATFORM", "value": "MOMO", "label": "momo"},
                {"type": "ECOMMERCE_PLATFORM", "value": "COUPANG", "label": "Coupang"},
                {"type": "ECOMMERCE_PLATFORM", "value": "TAOBAO", "label": "淘寶"},
            ],
        )

    if "店內消費最高3%" in text and "成功綁定支付" in text:
        category = "SHOPPING"
        subcategory = "DEPARTMENT"
        channel = "OFFLINE"
        refined_conditions = _replace_payment_conditions(
            refined_conditions,
            [
                {"type": "PAYMENT_PLATFORM", "value": "APPLE_PAY", "label": "Apple Pay"},
                {"type": "PAYMENT_PLATFORM", "value": "GOOGLE_PAY", "label": "Google Pay"},
                {"type": "PAYMENT_PLATFORM", "value": "LINE_PAY", "label": "LINE Pay"},
                {"type": "PAYMENT_PLATFORM", "value": "HAPPY_GO_PAY", "label": "HAPPY GO Pay"},
            ],
        )
        refined_conditions = _merge_conditions(
            refined_conditions,
            [{"type": "RETAIL_CHAIN", "value": "SOGO", "label": "SOGO"}],
        )

    if "Hami Pay掃碼支付" in text and "始符合回饋資格" in text:
        refined_conditions = _merge_conditions(
            refined_conditions,
            [{"type": "PAYMENT_PLATFORM", "value": "HAMI_PAY", "label": "Hami Pay"}],
        )

    if "遠東SOGO百貨即享券專區" in text and "核卡後 30天內" in text:
        refined_conditions = _replace_payment_conditions(refined_conditions, [])

    if requires_registration and recommendation_scope == "RECOMMENDABLE" and _is_registration_heavy_catalog_offer(text):
        recommendation_scope = "CATALOG_ONLY"

    # One more pass after CTBC-specific reshaping so persisted payment rows stay narrow.
    refined_conditions = sanitize_payment_conditions(title, body, refined_conditions)
    return category, subcategory, channel, recommendation_scope, refined_conditions


def _is_registration_heavy_catalog_offer(text: str) -> bool:
    if "需登錄" not in text and "完成登錄" not in text:
        return False
    return any(
        token in text
        for token in (
            "每月限量",
            "每戶加碼上限",
            "每戶每月回饋上限",
            "每人限回饋一次",
            "限量",
            "限回饋",
            "刷卡金回饋",
        )
    )


def _replace_payment_conditions(
    conditions: Sequence[Dict[str, str]],
    replacements: Sequence[Dict[str, str]],
) -> List[Dict[str, str]]:
    kept = [
        dict(condition)
        for condition in conditions
        if str(condition.get("type", "")).upper() not in {"PAYMENT_PLATFORM", "PAYMENT_METHOD"}
    ]
    return _merge_conditions(kept, replacements)


def _merge_conditions(
    conditions: Sequence[Dict[str, str]],
    additions: Sequence[Dict[str, str]],
) -> List[Dict[str, str]]:
    merged: List[Dict[str, str]] = [dict(condition) for condition in conditions]
    seen = {
        (str(condition.get("type", "")).upper(), str(condition.get("value", "")).upper())
        for condition in merged
    }
    for condition in additions:
        key = (str(condition.get("type", "")).upper(), str(condition.get("value", "")).upper())
        if key in seen:
            continue
        merged.append(dict(condition))
        seen.add(key)
    return merged
