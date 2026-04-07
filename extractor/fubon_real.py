from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List

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
    expand_general_reward_promotions,
    sanitize_payment_conditions,
    append_inferred_cobranded_conditions,
    append_inferred_date_conditions,
    SUBCATEGORY_SIGNALS,
)


CARD_LIST_URL = "https://www.fubon.com/banking/personal/credit_card/all_card/all_card.htm"
BASE_URL = "https://www.fubon.com"
BANK_CODE = "FUBON"
BANK_NAME = "富邦銀行"

CATEGORY_SIGNALS = {
    "OVERSEAS": [("日本", 4), ("韓國", 4), ("海外", 4), ("外幣", 3), ("航空", 3), ("旅遊", 3), ("旅行", 3), ("飯店", 3), ("住宿", 3), ("機場", 2), ("日圓", 2), ("韓圓", 2), ("里數", 3), ("泰國", 4), ("海外商戶", 4), ("Suica", 3), ("PASMO", 3), ("ICOCA", 3)],
    "ONLINE": [("Booking", 3), ("Agoda", 3), ("Hotels.com", 3), ("Expedia", 3), ("Klook", 3), ("KKday", 3), ("PChome", 4), ("蝦皮", 4), ("網購", 4), ("LINE Pay", 3), ("Uber Eats", 3), ("momo", 4), ("網頁", 2), ("網站", 2), ("平台", 1), ("APP", 1), ("線上購物", 4), ("網路消費", 4)],
    "DINING": [("餐飲", 4), ("餐廳", 3), ("咖啡", 2), ("壽司", 2), ("美饌", 3), ("饗樂", 3)],
    "TRANSPORT": [("交通", 4), ("乘車", 4), ("高鐵", 4), ("台鐵", 4), ("臺鐵", 4), ("捷運", 4), ("北捷", 4), ("巴士", 3), ("TAXI", 4), ("機場接送", 4), ("大眾交通", 4), ("加油", 3), ("中油", 2), ("自助加油", 4)],
    "SHOPPING": [("百貨", 3), ("新光三越", 5), ("購物", 3), ("免稅", 2), ("商圈", 2), ("OUTLET", 2), ("Costco", 5), ("好市多", 5), ("昇恆昌", 4), ("免稅店", 4), ("店內消費", 3), ("店外消費", 2)],
    "GROCERY": [("家樂福", 5), ("全聯", 5), ("超市", 4), ("量販", 3)],
    "ENTERTAINMENT": [("影城", 4), ("電影", 4), ("串流", 4), ("購票", 2), ("演唱會", 4), ("威秀", 4)],
}

CHANNEL_SIGNALS = {
    "ONLINE": [("APP", 3), ("網站", 3), ("網頁", 3), ("網購", 4), ("Booking", 4), ("Agoda", 4), ("Hotels.com", 4), ("Expedia", 4), ("Klook", 4), ("KKday", 4), ("PChome", 4), ("蝦皮", 4), ("LINE Pay", 3), ("電子支付", 3), ("momo購物網", 4), ("線上購物", 4), ("Apple Pay", 3), ("Google Pay", 3), ("Samsung Pay", 3)],
    "OFFLINE": [("實體門市", 4), ("實體店面", 4), ("實體商店", 4), ("店面", 3), ("門市", 3), ("店家", 3), ("商圈", 3), ("商店", 2), ("百貨", 2), ("餐廳", 2), ("加油站", 3), ("直營站", 3), ("搭乘", 2), ("實體卡", 3), ("實體", 1), ("Costco店內", 5), ("店內消費", 4)],
    "ALL": [("一般消費", 4), ("國內外一般消費", 5), ("不限通路", 4), ("國內外", 2), ("店外一般消費", 3)],
}

SUMMARY_NOISE_TOKENS = ("活動詳情", "注意事項", "立即登錄", "了解更多", "專屬網頁", "詳情請參閱", "活動請詳", "官網辦法", "立即擁有", "立即申辦")
GENERIC_TITLE_TOKENS = {"【活動一】", "【活動二】", "【活動三】", "活動一", "活動二", "活動三", "優惠", "回饋", "滿額活動"}

PAGE_CONFIG = SectionedPageConfig(
    section_headings=frozenset(
        {
            "產品特色",
            "精選優惠",
            "卡片特色",
            "優惠活動",
            "優惠訊息",
            "旅遊",
            "more饗樂",
            "more權益",
            "限時好禮",
            "產品權益",
            "服務申請",
            "資格／年費",
            "資格/年費",
            "申請資格",
            "年費標準",
            "申辦",
            "Additional Links",
        }
    ),
    active_sections=frozenset({"產品特色", "精選優惠", "卡片特色", "優惠活動", "優惠訊息", "旅遊", "more饗樂", "more權益", "限時好禮", "產品權益"}),
    subsection_skip=frozenset(
        {
            "產品特色",
            "精選優惠",
            "卡片特色",
            "優惠活動",
            "優惠訊息",
            "旅遊",
            "more饗樂",
            "more權益",
            "限時好禮",
            "產品權益",
            "服務申請",
            "資格／年費",
            "資格/年費",
            "申請資格",
            "年費標準",
            "申辦",
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
    annual_fee_signal_tokens=("首年免年費", "年費", "正卡"),
    application_requirement_tokens=("年滿18歲", "年滿15歲", "財力證明", "申辦", "所需文件"),
    ignored_offer_title_tokens=("立即申辦", "立即擁有", "道路救援", "旅遊平安保險", "旅遊平安險", "飛行優先禮遇", "權益手冊下載", "與我聯絡", "服務申請", "機場接送", "貴賓室", "停車", "機場外圍停車", "行李箱", "禮遇"),
)

ONLINE_PRIORITY_TOKENS = ("行動支付", "網路消費", "APP", "LINE Pay", "電子支付", "平台", "網頁", "網站", "Apple Pay", "Google Pay", "Samsung Pay", "線上購物", "網購")
OFFLINE_PRIORITY_TOKENS = ("實體商店", "門市", "店面", "機場接送", "搭乘", "餐廳", "百貨", "飯店", "臨櫃", "實體卡", "店內消費", "自助加油")


@dataclass
class CardRecord:
    card_code: str
    card_name: str
    detail_url: str
    apply_url: str | None
    annual_fee_summary: str | None
    application_requirements: List[str]
    sections: List[str]


def list_fubon_cards() -> List[CardRecord]:
    html = ingest.fetch_with_playwright(CARD_LIST_URL)

    seen: set[str] = set()
    cards: List[CardRecord] = []

    # Each card sits inside a card-list-box with:
    #   <img alt="CARD NAME" ...>
    #   <p class="card-title">CARD NAME</p>
    #   <a href="/banking/personal/credit_card/all_card/{slug}/{slug}.htm" class="more-btn">了解更多</a>
    # We extract the card name from card-title (preferred) or img alt, paired with the more-btn link.
    pattern = re.compile(
        r'<div class="card-list-box"[^>]*>.*?'
        r'<img\s+alt="([^"]*?)"[^>]*>.*?'
        r'(?:<p class="card-title">([^<]*?)</p>.*?)?'
        r'<a[^>]*href="(/banking/personal/credit_card/all_card/([^/"]+)/\4\.htm)"[^>]*class="more-btn"[^>]*>',
        re.DOTALL,
    )
    for match in pattern.finditer(html):
        img_alt = match.group(1).strip()
        card_title = (match.group(2) or "").strip()
        path = match.group(3)
        slug = match.group(4)

        detail_url = f"{BASE_URL}{path}"
        if detail_url in seen:
            continue
        seen.add(detail_url)

        raw_name = card_title or img_alt
        card_name = _clean_fubon_card_name(raw_name, slug)
        if not card_name or len(card_name) > 40:
            card_name = slug

        cards.append(
            CardRecord(
                card_code=_build_card_code(slug),
                card_name=card_name,
                detail_url=detail_url,
                apply_url=None,
                annual_fee_summary=None,
                application_requirements=[],
                sections=[],
            )
        )

    # Fallback: broader regex if the card-list-box pattern didn't match
    if not cards:
        fallback_pattern = re.compile(
            r'href="(/banking/personal/credit_card/all_card/([a-zA-Z0-9_]+)/[^"]*\.htm)"',
        )
        for match in fallback_pattern.finditer(html):
            path = match.group(1)
            slug = match.group(2)
            detail_url = f"{BASE_URL}{path}"
            if detail_url in seen or slug in ("all_card",):
                continue
            seen.add(detail_url)
            cards.append(
                CardRecord(
                    card_code=_build_card_code(slug),
                    card_name=slug,
                    detail_url=detail_url,
                    apply_url=None,
                    annual_fee_summary=None,
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

    slug = card.card_code.removeprefix("FUBON_").lower()
    # Prefer the list-page card name (already cleaned); fall back to detail-page extraction
    if card.card_name and card.card_name != slug:
        resolved_card_name = card.card_name
    else:
        resolved_card_name = _clean_fubon_card_name(extracted.card_name or card.card_name, slug)

    enriched_card = CardRecord(
        card_code=card.card_code,
        card_name=resolved_card_name,
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
        recommendation_scope = classify_recommendation_scope(clean_title, clean_body, category)
        conditions = build_conditions(clean_body, enriched_card.application_requirements, requires_registration)
        conditions = append_inferred_subcategory_conditions(clean_title, clean_body, category, subcategory, conditions)
        conditions = append_inferred_payment_method_conditions(category, subcategory, conditions, clean_title, clean_body)
        conditions = sanitize_payment_conditions(clean_title, clean_body, conditions)
        conditions = append_inferred_cobranded_conditions(clean_title, clean_body, conditions)
        conditions = append_inferred_date_conditions(clean_title, clean_body, conditions)
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
        channel = _infer_channel(clean_title, clean_body)
        category, subcategory, channel, recommendation_scope, conditions = _apply_card_specific_overrides(
            enriched_card.card_code,
            clean_title,
            clean_body,
            category,
            subcategory,
            channel,
            recommendation_scope,
            conditions,
        )

        base_promotion = {
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

        promotions.extend(expand_general_reward_promotions(base_promotion, clean_title, clean_body))

    # Card-specific feature extractors
    feature_builders: dict[str, object] = {
        "FUBON_INSURANCE": _extract_insurance_feature_promotions,
        "FUBON_LIFESTYLE": _extract_lifestyle_feature_promotions,
        "FUBON_OPENPOSSIBLE": _extract_openpossible_feature_promotions,
    }
    builder = feature_builders.get(enriched_card.card_code)
    if builder:
        for feature_promo in builder(enriched_card, eligibility_type):
            body = feature_promo.pop("_body", "")
            promotions.extend(expand_general_reward_promotions(feature_promo, feature_promo.get("title", ""), body))

    return enriched_card, _dedupe_promotions(promotions)


def _build_manual_promotion(
    card: CardRecord,
    *,
    title: str,
    body: str,
    category: str,
    subcategory: str,
    channel: str,
    recommendation_scope: str,
    reward: dict[str, object],
    valid_from: str,
    valid_until: str,
    eligibility_type: str,
    conditions: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    return {
        "title": f"{card.card_name} {title}",
        "cardCode": card.card_code,
        "cardName": card.card_name,
        "cardStatus": "ACTIVE",
        "annualFee": _extract_annual_fee_amount(card.annual_fee_summary),
        "applyUrl": card.apply_url,
        "bankCode": BANK_CODE,
        "bankName": BANK_NAME,
        "category": category,
        "subcategory": subcategory,
        "channel": channel,
        "cashbackType": reward["type"],
        "cashbackValue": reward["value"],
        "minAmount": 0,
        "maxCashback": None,
        "frequencyLimit": "NONE",
        "requiresRegistration": False,
        "recommendationScope": recommendation_scope,
        "eligibilityType": eligibility_type,
        "validFrom": valid_from,
        "validUntil": valid_until,
        "conditions": conditions or [],
        "excludedConditions": [],
        "sourceUrl": card.detail_url,
        "summary": f"{card.card_name} {title}；期間 {valid_from}~{valid_until}",
        "status": "ACTIVE",
        "_body": body,
    }


def _extract_insurance_feature_promotions(card: CardRecord, eligibility_type: str) -> list[dict[str, object]]:
    """富邦鑽保卡: 一般消費0.7%現金回饋無上限 + 保費0.5%回饋."""
    promotions: list[dict[str, object]] = []
    promotions.append(_build_manual_promotion(
        card,
        title="一般消費0.7%現金回饋無上限",
        body="持富邦鑽保卡刷卡消費，所有新增一般消費(不含保費)均享0.7%現金回饋，回饋無上限。",
        category="OTHER", subcategory="GENERAL", channel="ALL",
        recommendation_scope="RECOMMENDABLE",
        reward={"type": "PERCENT", "value": 0.7},
        valid_from="2026-01-01", valid_until="2026-06-30",
        eligibility_type=eligibility_type,
    ))
    promotions.append(_build_manual_promotion(
        card,
        title="保費0.5%現金回饋無上限",
        body="以富邦鑽保卡刷保費，享0.5%現金回饋，回饋無上限。",
        category="OTHER", subcategory="GENERAL", channel="ALL",
        recommendation_scope="RECOMMENDABLE",
        reward={"type": "PERCENT", "value": 0.5},
        valid_from="2026-01-01", valid_until="2026-06-30",
        eligibility_type=eligibility_type,
        conditions=[{"type": "TEXT", "value": "限保費消費", "label": "限保費消費"}],
    ))
    return promotions


def _extract_lifestyle_feature_promotions(card: CardRecord, eligibility_type: str) -> list[dict[str, object]]:
    """富邦富利生活系列卡: 8大生活消費紅利5倍."""
    promotions: list[dict[str, object]] = []
    promotions.append(_build_manual_promotion(
        card,
        title="8大生活消費紅利5倍回饋",
        body="持富邦富利生活系列卡於8大通路消費，享5倍紅利回饋（含原本1倍，即NT$20=5點），回饋無上限。當期帳單消費需達NT$3,000以上始可累積紅利。",
        category="OTHER", subcategory="GENERAL", channel="ALL",
        recommendation_scope="RECOMMENDABLE",
        reward={"type": "POINTS", "value": 0.25},
        valid_from="2026-01-01", valid_until="2026-12-31",
        eligibility_type=eligibility_type,
        conditions=[
            {"type": "TEXT", "value": "當期帳單需達NT$3,000以上", "label": "當期帳單需達NT$3,000以上"},
        ],
    ))
    return promotions


def _extract_openpossible_feature_promotions(card: CardRecord, eligibility_type: str) -> list[dict[str, object]]:
    """台灣大哥大Open Possible聯名卡: myfone基本回饋."""
    promotions: list[dict[str, object]] = []
    promotions.append(_build_manual_promotion(
        card,
        title="myfone購物最高5%回饋",
        body="持Open Possible聯名卡於myfone購物消費，享最高5%回饋。",
        category="ONLINE", subcategory="ECOMMERCE", channel="ONLINE",
        recommendation_scope="RECOMMENDABLE",
        reward={"type": "PERCENT", "value": 5.0},
        valid_from="2026-01-01", valid_until="2026-12-31",
        eligibility_type=eligibility_type,
        conditions=[{"type": "ECOMMERCE_PLATFORM", "value": "MYFONE", "label": "myfone購物"}],
    ))
    return promotions


def _build_card_code(slug: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", slug).strip("_").upper()
    return f"FUBON_{normalized}"


def _clean_fubon_card_name(name: str, slug: str = "") -> str:
    """Strip Fubon-specific prefixes/suffixes and fall back to slug for generic names.

    Patterns removed:
    - "信用卡-" / "信用卡－" prefix  (e.g. "信用卡-J&Co聯名卡" → "J&Co聯名卡")
    - "－台北富邦銀行" / "-台北富邦銀行" suffix (e.g. "Premier卡－台北富邦銀行" → "Premier卡")

    If the cleaned name is empty or still just "信用卡" (i.e. no real name was present),
    this returns the slug string and logs a warning so the caller can investigate whether
    the page genuinely omits a card name or the parser needs adjustment.
    """
    cleaned = re.sub(r"^信用卡\s*[-－]\s*", "", name).strip()
    cleaned = re.sub(r"\s*[-－]\s*台北富邦銀行\s*$", "", cleaned).strip()
    if not cleaned or cleaned == "信用卡":
        import logging
        logging.warning(
            "FUBON: card name resolved to generic ('信用卡') for slug=%r — "
            "check whether the listing page omits the name or the parser missed it.",
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
        bank_suffixes=(BANK_NAME, "台北富邦銀行", "富邦"),
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
    # Patterns like "團費80%以上" or "消費金額80%以上" are spending conditions, not rewards.
    filtered_text = re.sub(r"(?:團費|消費金額|消費額|金額|費用)\s*\d+(?:\.\d+)?%\s*以上", "", text)
    filtered_title = re.sub(r"(?:團費|消費金額|消費額|金額|費用)\s*\d+(?:\.\d+)?%\s*以上", "", title)
    reward = extract_reward(filtered_title, filtered_text)
    if reward and reward.get("value", 0) > 0:
        return reward
    fixed_match = re.search(r"(?:回饋|上限)\s*([\d,]+)\s*元刷卡金", filtered_text)
    if fixed_match:
        return {"type": "FIXED", "value": float(fixed_match.group(1).replace(",", ""))}
    return extract_reward("", filtered_text)


def _infer_category(title: str, body: str) -> str:
    return infer_category(title, body, CATEGORY_SIGNALS, overseas_category="OVERSEAS")


def _infer_channel(title: str, body: str) -> str:
    text = f"{title} {body}"
    if any(token in text for token in ONLINE_PRIORITY_TOKENS) and not any(token in text for token in OFFLINE_PRIORITY_TOKENS):
        return "ONLINE"
    if any(token in text for token in OFFLINE_PRIORITY_TOKENS) and not any(token in text for token in ONLINE_PRIORITY_TOKENS):
        return "OFFLINE"
    return infer_channel(title, body, CHANNEL_SIGNALS)


def _apply_card_specific_overrides(
    card_code: str,
    title: str,
    body: str,
    category: str,
    subcategory: str,
    channel: str,
    recommendation_scope: str,
    conditions: List[Dict[str, str]],
) -> tuple[str, str, str, str, List[Dict[str, str]]]:
    text = f"{title} {body}"
    merged_conditions = [dict(condition) for condition in conditions]

    if _should_drop_exclusion_only_payment_conditions(title, body):
        merged_conditions = _drop_condition_types(merged_conditions, {"PAYMENT_METHOD", "PAYMENT_PLATFORM"})

    if "高鐵除外" in text and category == "TRANSPORT" and subcategory == "PUBLIC_TRANSIT":
        merged_conditions = _drop_condition_types(merged_conditions, {"MERCHANT"})

    if any(token in text for token in ("即享券適用範圍", "即享券適用通路")) and any(
        token in text for token in ("推薦", "新戶", "專屬連結")
    ):
        merged_conditions = _drop_condition_types(
            merged_conditions,
            {"MERCHANT", "RETAIL_CHAIN", "ECOMMERCE_PLATFORM"},
        )
        return ("OTHER", "GENERAL", "ALL", recommendation_scope, merged_conditions)

    if any(token in text for token in ("刷卡賺紅利", "紅利點數", "一般消費享", "保費享", "紅利變現金折抵")) and any(
        token in text for token in ("一般消費定義", "數位通路消費定義限制", "不包含指定網路平台交易")
    ):
        return ("OTHER", "GENERAL", "ALL", recommendation_scope, merged_conditions)

    if card_code == "FUBON_MOMO":
        if "指定跨境線上" in title:
            merged_conditions = [
                condition
                for condition in merged_conditions
                if not (
                    str(condition.get("type", "")).upper() == "ECOMMERCE_PLATFORM"
                    and str(condition.get("value", "")).upper() == "MOMO"
                )
            ]
            return (category, "GENERAL", "ONLINE", recommendation_scope, merged_conditions)

        if "店外滿額" in title and "店內最高" in title:
            merged_conditions = _drop_condition_types(merged_conditions, {"PAYMENT_METHOD", "PAYMENT_PLATFORM"})
            return ("ONLINE", "GENERAL", "ALL", "CATALOG_ONLY", merged_conditions)

    if card_code == "FUBON_OMIYAGE":
        if any(token in text for token in ("日本三大交通卡", "Suica", "PASMO", "ICOCA")) and "Apple Pay" in text:
            merged_conditions = _merge_conditions(
                _drop_condition_types(merged_conditions, {"PAYMENT_METHOD", "PAYMENT_PLATFORM", "MERCHANT"}),
                [
                    {"type": "PAYMENT_PLATFORM", "value": "APPLE_PAY", "label": "Apple Pay"},
                    {"type": "MERCHANT", "value": "SUICA", "label": "Suica"},
                    {"type": "MERCHANT", "value": "PASMO", "label": "PASMO"},
                    {"type": "MERCHANT", "value": "ICOCA", "label": "ICOCA"},
                ],
            )
            return ("TRANSPORT", "PUBLIC_TRANSIT", "ONLINE", recommendation_scope, merged_conditions)

        if "活動餐廳：" in text or "指定餐廳" in title:
            merged_conditions = _drop_condition_types(merged_conditions, {"PAYMENT_METHOD", "PAYMENT_PLATFORM"})
            return ("DINING", "GENERAL", "OFFLINE", "CATALOG_ONLY", merged_conditions)

    return category, subcategory, channel, recommendation_scope, merged_conditions


def _should_drop_exclusion_only_payment_conditions(title: str, body: str) -> bool:
    text = f"{title} {body}"
    exclusion_tokens = (
        "一般消費定義",
        "數位通路消費定義限制",
        "不包含指定網路平台交易",
        "便利商店消費",
        "第三方支付平台",
        "視同店外一般消費",
        "不計入活動門檻",
        "不列入活動資格",
    )
    positive_tokens = (
        "日本三大交通卡",
        "Apple Pay綁定J卡",
        "綁定國際行動支付",
        "使用Apple Pay",
        "使用 LINE Pay",
        "限以Apple Pay",
        "限以 LINE Pay",
    )
    return any(token in text for token in exclusion_tokens) and not any(token in text for token in positive_tokens)


def _drop_condition_types(
    conditions: List[Dict[str, str]],
    condition_types: set[str],
) -> List[Dict[str, str]]:
    return [
        dict(condition)
        for condition in conditions
        if str(condition.get("type", "")).upper() not in condition_types
    ]


def _merge_conditions(
    base_conditions: List[Dict[str, str]],
    extra_conditions: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    merged = [dict(condition) for condition in base_conditions]
    seen = {
        (str(condition.get("type", "")).upper(), str(condition.get("value", "")).upper())
        for condition in merged
    }
    for condition in extra_conditions:
        key = (str(condition.get("type", "")).upper(), str(condition.get("value", "")).upper())
        if key in seen:
            continue
        merged.append(dict(condition))
        seen.add(key)
    return merged
