from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence

from extractor import ingest
from extractor.benefit_plans import apply_plan_subcategory_hint, infer_plan_id
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
    is_registration_heavy_catalog_offer,
    sanitize_payment_conditions,
    append_inferred_cobranded_conditions,
    append_inferred_date_conditions,
    SUBCATEGORY_SIGNALS,
)

RICHART_EXCLUDED_ACTIVITY_TOKENS = (
    "保費",
    "保險",
    "分期",
    "優惠利率",
    "抽獎",
    "首刷禮",
    "首筆",
    "核卡",
    "新戶禮",
    "滿額禮",
    "行李箱",
)
RICHART_CATALOG_ONLY_TOKENS = (
    "領券",
    "登錄",
    "優惠碼",
    "折扣碼",
    "限量",
    "新戶",
    "抽獎",
    "保費",
    "保險",
    "分期",
    "首刷禮",
)


CARD_LIST_URL = "https://www.taishinbank.com.tw/TSB/personal/credit/intro/overview/index.html"
BASE_URL = "https://www.taishinbank.com.tw"
BANK_CODE = "TAISHIN"
PROMOTION_HOST_TOKENS = ("mkp.taishinbank.com.tw", "mkpcard.taishinbank.com.tw")
PROMOTION_PATH_TOKENS = ("/tscccms/promotion/detail/", "/TsCms/marketing/expose/")
RICHART_GUIDE_URLS = (
    "https://www.taishinbank.com.tw/TSB/personal/credit/discount/life/",
    "https://www.taishinbank.com.tw/TSB/personal/digital/E-Payment/Electronic-Payment/introduction/",
)
RICHART_KEYWORDS = (
    "Richart",
    "台新Richart卡",
    "Pay著刷",
    "天天刷",
    "大筆刷",
    "好饗刷",
    "數趣刷",
    "玩旅刷",
    "假日刷",
)
REGISTRATION_TOKENS = ("登錄", "領券", "領取", "切換")
RICHART_PLAN_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("Pay著刷",), "TAISHIN_RICHART_PAY"),
    (("天天刷",), "TAISHIN_RICHART_DAILY"),
    (("大筆刷",), "TAISHIN_RICHART_BIG"),
    (("好饗刷",), "TAISHIN_RICHART_DINING"),
    (("數趣刷",), "TAISHIN_RICHART_DIGITAL"),
    (("玩旅刷",), "TAISHIN_RICHART_TRAVEL"),
    (("假日刷",), "TAISHIN_RICHART_WEEKEND"),
    (("Hotels.com", "Agoda", "Booking", "Klook", "KKday", "Trip.com", "AsiaYo", "AIRSIM", "旅遊", "訂房"), "TAISHIN_RICHART_TRAVEL"),
    (("LINE Pay", "台新Pay", "街口", "電子支付", "行動支付"), "TAISHIN_RICHART_PAY"),
    (("超商量販", "高鐵", "臺鐵", "台鐵", "量販"), "TAISHIN_RICHART_DAILY"),
    (("滿額", "分期"), "TAISHIN_RICHART_BIG"),
    (("餐飲", "餐廳", "美食"), "TAISHIN_RICHART_DINING"),
    (("影音", "串流", "Netflix", "Spotify", "Disney+", "friDay"), "TAISHIN_RICHART_DIGITAL"),
    (("週末", "周末", "假日"), "TAISHIN_RICHART_WEEKEND"),
)
RICHART_PLAN_CONDITIONS: dict[tuple[str, str], tuple[dict[str, str], ...]] = {
    ("TAISHIN_RICHART_PAY", "MOBILE_PAY"): (
        {"type": "PAYMENT_PLATFORM", "value": "LINE_PAY", "label": "LINE Pay"},
        {"type": "PAYMENT_PLATFORM", "value": "JKOPAY", "label": "JKOPay"},
        {"type": "PAYMENT_PLATFORM", "value": "APPLE_PAY", "label": "Apple Pay"},
        {"type": "PAYMENT_PLATFORM", "value": "GOOGLE_PAY", "label": "Google Pay"},
    ),
    ("TAISHIN_RICHART_DAILY", "SUPERMARKET"): (
        {"type": "RETAIL_CHAIN", "value": "PXMART", "label": "PX Mart"},
        {"type": "RETAIL_CHAIN", "value": "CARREFOUR", "label": "Carrefour"},
        {"type": "RETAIL_CHAIN", "value": "RT_MART", "label": "RT-Mart"},
    ),
    ("TAISHIN_RICHART_BIG", "DEPARTMENT"): (
        {"type": "RETAIL_CHAIN", "value": "SHIN_KONG_MITSUKOSHI", "label": "Shin Kong Mitsukoshi"},
        {"type": "RETAIL_CHAIN", "value": "SOGO", "label": "SOGO"},
        {"type": "RETAIL_CHAIN", "value": "FAR_EAST_DEPARTMENT_STORE", "label": "Far Eastern"},
    ),
    ("TAISHIN_RICHART_DIGITAL", "STREAMING"): (
        {"type": "MERCHANT", "value": "NETFLIX", "label": "Netflix"},
        {"type": "MERCHANT", "value": "SPOTIFY", "label": "Spotify"},
        {"type": "MERCHANT", "value": "DISNEY_PLUS", "label": "Disney+"},
        {"type": "MERCHANT", "value": "FRIDAY_VIDEO", "label": "friDay Video"},
    ),
    ("TAISHIN_RICHART_TRAVEL", "TRAVEL_PLATFORM"): (
        {"type": "MERCHANT", "value": "AGODA", "label": "Agoda"},
        {"type": "MERCHANT", "value": "BOOKING", "label": "Booking.com"},
        {"type": "MERCHANT", "value": "HOTELS_COM", "label": "Hotels.com"},
        {"type": "MERCHANT", "value": "TRIP_COM", "label": "Trip.com"},
        {"type": "MERCHANT", "value": "KLOOK", "label": "Klook"},
        {"type": "MERCHANT", "value": "KKDAY", "label": "KKday"},
        {"type": "MERCHANT", "value": "ASIAYO", "label": "AsiaYo"},
    ),
}
RICHART_TIERED_PLAN_IDS = {
    "TAISHIN_RICHART_PAY",
    "TAISHIN_RICHART_DAILY",
    "TAISHIN_RICHART_BIG",
    "TAISHIN_RICHART_DINING",
    "TAISHIN_RICHART_DIGITAL",
    "TAISHIN_RICHART_TRAVEL",
    "TAISHIN_RICHART_WEEKEND",
}
RICHART_TIER_SENSITIVE_RATES = {1.3, 2.0, 2.3, 3.3, 3.8}
MARKETING_NOISE_TOKENS = (
    "處理中",
    "敬請稍候",
    "行動選單",
    "關閉視窗",
    "信用卡刷卡優惠",
    "旅遊及海外購物",
    "台新銀行提醒您",
    "不是台新銀行的網頁",
)
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

# Known card mapping: CG path fragment → (semantic card_code, canonical card_name)
KNOWN_CARDS: dict[str, tuple[str, str]] = {
    "cg047/card001": ("TAISHIN_RICHART", "台新Richart卡"),
    "cg010/card001": ("TAISHIN_PX_MART", "大全聯信用卡"),
    "cg038/card001": ("TAISHIN_JKOPAY", "街口聯名卡"),
    "cg009/card001": ("TAISHIN_EVERRICH", "昇恆昌御璽/白金/普卡"),
    "cg008/card001": ("TAISHIN_SHIN_KONG", "新光三越御璽/鈦金/白金卡"),
    "cg003/card001": ("TAISHIN_CATHAY_PACIFIC", "國泰航空翱翔鈦金卡/鈦金卡"),
    "cg019/card001": ("TAISHIN_FRIDAY", "遠傳friDay聯名卡"),
    "cg042/card001": ("TAISHIN_GOGORO", "Gogoro Rewards 聯名卡"),
    "cg039/card001": ("TAISHIN_DUAL_CURRENCY", "台新雙幣卡"),
    "cg013/card0001": ("TAISHIN_ROSE", "玫瑰卡"),
    "cg012/card0001": ("TAISHIN_SUN", "太陽卡"),
    "cg045/card001": ("TAISHIN_INFINITE", "卓富無限卡"),
    "cg023/card002": ("TAISHIN_TSANN_KUEN", "燦坤聯名卡"),
    "cg014/card0001": ("TAISHIN_SHIN_KONG_WORLD", "新光三越無限/世界卡"),
}


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
    html = ingest.fetch_with_playwright(CARD_LIST_URL)

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
                card_name=_resolve_card_name(path, card_name),
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

    enriched_card = CardRecord(
        card_code=card.card_code,
        card_name=_resolve_card_name(card.detail_url, card.card_name),
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
        plan_id = _resolve_richart_plan_id(enriched_card.card_code, category, clean_title, clean_body)
        conditions = build_conditions(clean_body, enriched_card.application_requirements, requires_registration)
        conditions = append_inferred_subcategory_conditions(clean_title, clean_body, category, subcategory, conditions)
        conditions = append_inferred_payment_method_conditions(category, subcategory, conditions, clean_title, clean_body)
        category, subcategory = apply_plan_subcategory_hint(
            plan_id,
            category,
            subcategory,
            title=clean_title,
            body=clean_body,
        )
        conditions = _append_richart_plan_conditions(plan_id, subcategory, conditions)
        conditions = _append_richart_tier_conditions(plan_id, reward["value"], conditions)
        conditions = sanitize_payment_conditions(clean_title, clean_body, conditions)
        conditions = append_inferred_cobranded_conditions(clean_title, clean_body, conditions)
        conditions = append_inferred_date_conditions(clean_title, clean_body, conditions)
        conditions = append_bank_wide_promotion_condition(
            clean_title,
            clean_body,
            recommendation_scope,
            conditions,
            requires_registration=requires_registration,
            plan_id=plan_id,
            subcategory=subcategory,
        )
        conditions = append_catalog_review_conditions(
            clean_title,
            clean_body,
            recommendation_scope,
            conditions,
            requires_registration=requires_registration,
            plan_id=plan_id,
        )
        subcategory = canonicalize_subcategory(category, subcategory, conditions)

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

        promotions.extend(expand_general_reward_promotions(base_promotion, clean_title, clean_body))

    promotions.extend(_extract_card_feature_promotions(enriched_card, lines))

    if enriched_card.card_code == "TAISHIN_RICHART":
        promotions.extend(_extract_richart_bonus_promotions(enriched_card, links))

    promotions = _postprocess_taishin_promotions(enriched_card, promotions)
    return enriched_card, _dedupe_promotions(promotions)


def _build_card_code(path: str) -> str:
    # Check known card mapping first
    match = re.search(r"(cg\d+/card\d+)", path, re.IGNORECASE)
    if match:
        key = match.group(1).lower()
        known = KNOWN_CARDS.get(key)
        if known:
            return known[0]
        cg, card = key.split("/")
        return f"TAISHIN_{cg.upper()}_{card.upper()}"
    slug = path.rstrip("/").split("/")[-1]
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", slug).strip("_").upper()
    return f"TAISHIN_{normalized}"


def _resolve_card_name(path: str, parsed_name: str) -> str:
    """Return canonical card name from KNOWN_CARDS, falling back to parsed_name."""
    match = re.search(r"(cg\d+/card\d+)", path, re.IGNORECASE)
    if match:
        known = KNOWN_CARDS.get(match.group(1).lower())
        if known:
            return known[1]
    return parsed_name


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


def _extract_card_feature_promotions(card: CardRecord, lines: Sequence[str]) -> List[Dict[str, object]]:
    builders = {
        "TAISHIN_JKOPAY": _extract_jkopay_feature_promotions,
        "TAISHIN_PX_MART": _extract_px_mart_feature_promotions,
        "TAISHIN_FRIDAY": _extract_friday_feature_promotions,
        "TAISHIN_GOGORO": _extract_gogoro_feature_promotions,
        "TAISHIN_DUAL_CURRENCY": _extract_dual_currency_feature_promotions,
        "TAISHIN_INFINITE": _extract_infinite_feature_promotions,
        "TAISHIN_SHIN_KONG": _extract_shin_kong_feature_promotions,
        "TAISHIN_SHIN_KONG_WORLD": _extract_shin_kong_world_feature_promotions,
        "TAISHIN_TSANN_KUEN": _extract_tsann_kuen_feature_promotions,
    }
    builder = builders.get(card.card_code)
    if builder is None:
        return []
    return builder(card, lines)


def _postprocess_taishin_promotions(card: CardRecord, promotions: List[Dict[str, object]]) -> List[Dict[str, object]]:
    normalized: List[Dict[str, object]] = []
    for promo in promotions:
        title = str(promo.get("title", ""))
        summary = str(promo.get("summary", ""))
        combined = f"{title} {summary}"

        if card.card_code == "TAISHIN_FRIDAY" and "電信費最高3%" in combined and "活動已結束" in combined:
            continue

        if _is_installment_offer(combined):
            promo["recommendationScope"] = "CATALOG_ONLY"
            promo["category"] = "OTHER"
            promo["subcategory"] = "GENERAL"
            promo["channel"] = "ALL"

        if card.card_code in {"TAISHIN_ROSE", "TAISHIN_SUN"} and (
            "指定套餐方案" in combined or "自由選方案" in combined
        ):
            promo["recommendationScope"] = "CATALOG_ONLY"
            promo["category"] = "OTHER"
            promo["subcategory"] = "GENERAL"
            promo["channel"] = "ALL"

        if card.card_code == "TAISHIN_DUAL_CURRENCY" and "輪子：5.5cm" in combined:
            continue

        normalized.append(promo)

    return normalized


def _is_installment_offer(text: str) -> bool:
    return all(token in text for token in ("分期", "優惠利率")) or "卡片分期" in text or "單筆分期" in text


def _extract_jkopay_feature_promotions(card: CardRecord, lines: Sequence[str]) -> List[Dict[str, object]]:
    promotions: List[Dict[str, object]] = []
    selected_body = _collect_line_window(
        lines,
        "街口豬富卡2026年權益 : 精選通路最高3.5%街口幣",
        stop_tokens=("【活動已結束】旅遊/娛樂/交通/百貨/藥妝/外送/餐飲最高3.5%",),
    )
    if selected_body:
        promotions.append(
            _build_manual_promotion(
                card,
                title="精選通路最高3.5%街口幣",
                body=selected_body,
                category="OTHER",
                subcategory="GENERAL",
                channel="ALL",
                recommendation_scope="CATALOG_ONLY",
                valid_from="2026-01-01",
                valid_until="2026-12-31",
            )
        )

    billpay_body = _collect_line_window(
        lines,
        "【街口APP繳費 最高 2.15 %】",
        stop_tokens=("【一般消費享 1 %街口幣 無上限】",),
    )
    if billpay_body:
        promotions.append(
            _build_manual_promotion(
                card,
                title="街口APP繳費最高2.15%",
                body=billpay_body,
                category="OTHER",
                subcategory="GENERAL",
                channel="ONLINE",
                recommendation_scope="CATALOG_ONLY",
                valid_from="2026-01-01",
                valid_until="2026-12-31",
                extra_conditions=[
                    {"type": "PAYMENT_PLATFORM", "value": "JKOPAY", "label": "街口支付"},
                    {"type": "PAYMENT_METHOD", "value": "MOBILE_PAY", "label": "行動支付"},
                ],
            )
        )

    general_body = _collect_line_window(
        lines,
        "【一般消費享 1 %街口幣 無上限】",
        stop_tokens=("(1)精選通路最高3.5%優惠說明如下，其中精選加碼合計每月上限10,000元街口幣",),
    )
    if general_body:
        promotions.append(
            _build_manual_promotion(
                card,
                title="一般消費1%街口幣無上限",
                body=general_body,
                category="OTHER",
                subcategory="GENERAL",
                channel="ALL",
                recommendation_scope="RECOMMENDABLE",
                valid_from="2026-01-01",
                valid_until="2026-12-31",
            )
        )

    return promotions


def _extract_px_mart_feature_promotions(card: CardRecord, lines: Sequence[str]) -> List[Dict[str, object]]:
    promotions: List[Dict[str, object]] = []

    # Base reward: 其他一般消費0.3%福利點
    promotions.append(
        _build_manual_promotion(
            card,
            title="其他一般消費0.3%福利點",
            body="大全聯信用卡其他一般消費(不含全支付、大全聯、全聯福利中心消費)每消費100元給3點福利點(最高0.3%)。無需登錄，店外全支付消費及其他一般消費合計每期最高回饋福利點15,000點。適用期間2026/4/1-2026/6/30。",
            category="OTHER",
            subcategory="GENERAL",
            channel="ALL",
            recommendation_scope="RECOMMENDABLE",
            reward={"type": "PERCENT", "value": 0.3},
            valid_from="2026-04-01",
            valid_until="2026-06-30",
        )
    )

    feature_body = _collect_line_window(
        lines,
        "大全聯JCB卡最高8.5% 福利點限時送",
        stop_tokens=("卡片分期享 0.88%限時優利",),
    )
    if feature_body:
        promotions.append(
            _build_manual_promotion(
                card,
                title="大全聯店內消費最高1.2%",
                body=feature_body,
                category="GROCERY",
                subcategory="SUPERMARKET",
                channel="OFFLINE",
                recommendation_scope="RECOMMENDABLE",
                extra_conditions=[
                    {"type": "RETAIL_CHAIN", "value": "PXMART", "label": "大全聯"},
                ],
                valid_from="2026-04-01",
                valid_until="2026-06-30",
            )
        )
        promotions.append(
            _build_manual_promotion(
                card,
                title="全支付店外消費最高1.5%",
                body=feature_body,
                category="OTHER",
                subcategory="GENERAL",
                channel="ALL",
                recommendation_scope="RECOMMENDABLE",
                extra_conditions=[
                    {"type": "PAYMENT_PLATFORM", "value": "全支付", "label": "全支付"},
                    {"type": "PAYMENT_METHOD", "value": "MOBILE_PAY", "label": "行動支付"},
                ],
                valid_from="2026-04-01",
                valid_until="2026-06-30",
            )
        )

    return promotions


def _extract_friday_feature_promotions(card: CardRecord, lines: Sequence[str]) -> List[Dict[str, object]]:
    promotions: List[Dict[str, object]] = []

    # Base reward: 一般消費1%遠傳幣無上限
    promotions.append(
        _build_manual_promotion(
            card,
            title="一般消費1%遠傳幣無上限",
            body="一般消費基本回饋1%遠傳幣，回饋無上限。活動期間2025/1/1~2026/5/31結帳帳單。",
            category="OTHER",
            subcategory="GENERAL",
            channel="ALL",
            recommendation_scope="RECOMMENDABLE",
            reward={"type": "PERCENT", "value": 1.0},
            valid_from="2025-01-01",
            valid_until="2026-05-31",
        )
    )

    telecom_body = _collect_line_window(
        lines,
        "電信帳單代扣繳最高3%、指定通路會員日最高8%",
        stop_tokens=("八大專屬訂房網，享最高14%優惠",),
    )
    if telecom_body:
        promotions.append(
            _build_manual_promotion(
                card,
                title="遠傳電信帳單代扣繳最高3%",
                body=telecom_body,
                category="OTHER",
                subcategory="GENERAL",
                channel="ALL",
                recommendation_scope="RECOMMENDABLE",
            )
        )

    dining_body = _collect_line_window(
        lines,
        "餐飲多一盤、享最高15%優惠",
        stop_tokens=("申請條件",),
    )
    if dining_body:
        promotions.append(
            _build_manual_promotion(
                card,
                title="餐飲多一盤最高15%優惠",
                body=dining_body,
                category="DINING",
                subcategory="RESTAURANT",
                channel="OFFLINE",
                recommendation_scope="CATALOG_ONLY",
                extra_conditions=[
                    {"type": "MERCHANT", "value": "WOWPRIME", "label": "王品集團"},
                    {"type": "MERCHANT", "value": "TOFU_RESTAURANTS", "label": "豆府餐飲集團"},
                    {"type": "MERCHANT", "value": "VOLTERRA_GROUP", "label": "瓦城泰統集團"},
                    {"type": "MERCHANT", "value": "SABOTEN", "label": "勝博殿"},
                    {"type": "MERCHANT", "value": "COLD_STONE", "label": "COLD STONE"},
                ],
            )
        )

    return promotions


def _extract_gogoro_feature_promotions(card: CardRecord, lines: Sequence[str]) -> List[Dict[str, object]]:
    promotions: List[Dict[str, object]] = []

    # Base reward: 一般消費0.3%無上限
    promotions.append(
        _build_manual_promotion(
            card,
            title="一般消費0.3% Gogoro Smart Points無上限",
            body="持台新Gogoro Rewards聯名卡一般消費享0.3% Gogoro Smart Points回饋無上限。活動期間2026/1/1~2026/12/31。",
            category="OTHER",
            subcategory="GENERAL",
            channel="ALL",
            recommendation_scope="RECOMMENDABLE",
            reward={"type": "PERCENT", "value": 0.3},
            valid_from="2026-01-01",
            valid_until="2026-12-31",
        )
    )

    # Gogoro Rewards夥伴商家加碼（7-ELEVEN、全家、高鐵、Uber、Uber Eats、foodpanda、Klook、KKday）
    promotions.append(
        _build_manual_promotion(
            card,
            title="Gogoro Rewards夥伴商家最高4%",
            body="於Gogoro Rewards商家夥伴(7-ELEVEN、全家便利商店、高鐵、Uber、Uber Eats、foodpanda、Klook、KKday)使用聯名卡消費，享最高4%回饋。含一般消費0.3%無上限+指定任務加碼3.7%，加碼單筆上限100點，每月上限500點。活動期間2026/2/1~2026/6/30。",
            category="OTHER",
            subcategory="GENERAL",
            channel="ALL",
            recommendation_scope="CATALOG_ONLY",
            reward={"type": "PERCENT", "value": 4.0},
            valid_from="2026-02-01",
            valid_until="2026-06-30",
            extra_conditions=[
                {"type": "MERCHANT", "value": "7_ELEVEN", "label": "7-ELEVEN"},
                {"type": "MERCHANT", "value": "FAMILY_MART", "label": "全家便利商店"},
                {"type": "MERCHANT", "value": "THSR", "label": "高鐵"},
                {"type": "MERCHANT", "value": "UBER", "label": "Uber"},
                {"type": "MERCHANT", "value": "UBER_EATS", "label": "Uber Eats"},
                {"type": "MERCHANT", "value": "FOODPANDA", "label": "foodpanda"},
                {"type": "MERCHANT", "value": "KLOOK", "label": "Klook"},
                {"type": "MERCHANT", "value": "KKDAY", "label": "KKday"},
            ],
        )
    )

    battery_body = _collect_line_window(
        lines,
        "1. 電池資費最高享 4% 回饋無上限",
        stop_tokens=("保了再上| Gogoro門市維修保養及配件、Gogoro 網路商店回饋",),
    )
    if battery_body:
        promotions.append(
            _build_manual_promotion(
                card,
                title="電池資費最高4%回饋無上限",
                body=battery_body,
                category="OTHER",
                subcategory="GENERAL",
                channel="ALL",
                recommendation_scope="CATALOG_ONLY",
                extra_conditions=[
                    {"type": "MERCHANT", "value": "GOGORO", "label": "Gogoro"},
                ],
            )
        )

    maintenance_body = _collect_line_window(
        lines,
        "保了再上｜Gogoro門市維修保養及配件優惠",
        stop_tokens=("注意事項｜Gogoro門市維修保養及配件、Gogoro 網路商店回饋",),
    )
    if maintenance_body:
        promotions.append(
            _build_manual_promotion(
                card,
                title="Gogoro門市維修保養及配件最高4%",
                body=maintenance_body,
                category="OTHER",
                subcategory="GENERAL",
                channel="ALL",
                recommendation_scope="CATALOG_ONLY",
                extra_conditions=[
                    {"type": "MERCHANT", "value": "GOGORO", "label": "Gogoro"},
                ],
            )
        )

    warranty_body = _collect_line_window(
        lines,
        "加購延長保固享 40% 無上限",
        stop_tokens=("注意事項｜Gogoro門市維修保養及配件、Gogoro 網路商店回饋",),
    )
    if warranty_body:
        promotions.append(
            _build_manual_promotion(
                card,
                title="加購延長保固40%回饋無上限",
                body=warranty_body,
                category="OTHER",
                subcategory="GENERAL",
                channel="ALL",
                recommendation_scope="CATALOG_ONLY",
                extra_conditions=[
                    {"type": "MERCHANT", "value": "GOGORO", "label": "Gogoro"},
                ],
                valid_from="2026-02-01",
                valid_until="2026-06-30",
            )
        )

    return promotions


def _extract_dual_currency_feature_promotions(card: CardRecord, lines: Sequence[str]) -> List[Dict[str, object]]:
    return []


def _extract_infinite_feature_promotions(card: CardRecord, lines: Sequence[str]) -> List[Dict[str, object]]:
    """卓富無限卡：現金回饋無上限（from MKP page: 2026/1/1-2027/1/31）。"""
    return [
        _build_manual_promotion(
            card,
            title="一般消費現金回饋無上限",
            body="卓富無限卡一般消費享現金回饋無上限。適用期間2026/1/1-2027/1/31結帳帳單。",
            category="OTHER",
            subcategory="GENERAL",
            channel="ALL",
            recommendation_scope="RECOMMENDABLE",
            reward={"type": "PERCENT", "value": 0.3},
            valid_from="2026-01-01",
            valid_until="2027-01-31",
        ),
    ]


def _extract_shin_kong_feature_promotions(card: CardRecord, lines: Sequence[str]) -> List[Dict[str, object]]:
    """新光三越御璽/鈦金/白金卡：一般消費0.3%無上限 + 週五~日店內最高1%。"""
    return [
        _build_manual_promotion(
            card,
            title="一般消費0.3%台新Point回饋無上限",
            body="新光三越聯名卡一般消費享0.3%台新Point(信用卡)回饋無上限。2026/1/1~2026/12/31結帳帳單。",
            category="OTHER",
            subcategory="GENERAL",
            channel="ALL",
            recommendation_scope="RECOMMENDABLE",
            reward={"type": "PERCENT", "value": 0.3},
            valid_from="2026-01-01",
            valid_until="2026-12-31",
        ),
        _build_manual_promotion(
            card,
            title="週五~日新光三越店內消費最高1%",
            body="週五~日於新光三越百貨店內消費，筆筆享最高1%台新Point(信用卡)回饋。御璽/鈦金卡一般消費0.3%無上限+店內加碼0.7%(每月上限1,000點)。2026/1/1~2026/12/31結帳帳單。",
            category="SHOPPING",
            subcategory="DEPARTMENT",
            channel="OFFLINE",
            recommendation_scope="RECOMMENDABLE",
            reward={"type": "PERCENT", "value": 1.0},
            valid_from="2026-01-01",
            valid_until="2026-12-31",
            extra_conditions=[
                {"type": "RETAIL_CHAIN", "value": "SHIN_KONG_MITSUKOSHI", "label": "新光三越"},
            ],
        ),
    ]


def _extract_shin_kong_world_feature_promotions(card: CardRecord, lines: Sequence[str]) -> List[Dict[str, object]]:
    """新光三越無限/世界卡：一般消費0.3%無上限 + 週五~日店內最高1.2%。"""
    return [
        _build_manual_promotion(
            card,
            title="一般消費0.3%台新Point回饋無上限",
            body="新光三越聯名卡一般消費享0.3%台新Point(信用卡)回饋無上限。2026/1/1~2026/12/31結帳帳單。",
            category="OTHER",
            subcategory="GENERAL",
            channel="ALL",
            recommendation_scope="RECOMMENDABLE",
            reward={"type": "PERCENT", "value": 0.3},
            valid_from="2026-01-01",
            valid_until="2026-12-31",
        ),
        _build_manual_promotion(
            card,
            title="週五~日新光三越店內消費最高1.2%",
            body="週五~日於新光三越百貨店內消費，筆筆享最高1.2%台新Point(信用卡)回饋。一般消費0.3%無上限+店內加碼0.9%(每月上限10,000點)。2026/1/1~2026/12/31結帳帳單。",
            category="SHOPPING",
            subcategory="DEPARTMENT",
            channel="OFFLINE",
            recommendation_scope="RECOMMENDABLE",
            reward={"type": "PERCENT", "value": 1.2},
            valid_from="2026-01-01",
            valid_until="2026-12-31",
            extra_conditions=[
                {"type": "RETAIL_CHAIN", "value": "SHIN_KONG_MITSUKOSHI", "label": "新光三越"},
            ],
        ),
    ]


def _extract_tsann_kuen_feature_promotions(card: CardRecord, lines: Sequence[str]) -> List[Dict[str, object]]:
    """燦坤聯名卡：一般消費0.3%無上限 + 燦坤店內平日1%/週末2%。"""
    return [
        _build_manual_promotion(
            card,
            title="一般消費0.3%燦坤K幣回饋無上限",
            body="燦坤聯名卡一般消費享0.3%燦坤K幣回饋無上限。2026/1/1~2026/12/31。",
            category="OTHER",
            subcategory="GENERAL",
            channel="ALL",
            recommendation_scope="RECOMMENDABLE",
            reward={"type": "PERCENT", "value": 0.3},
            valid_from="2026-01-01",
            valid_until="2026-12-31",
        ),
        _build_manual_promotion(
            card,
            title="燦坤店內消費平日1%/週末最高2%",
            body="持燦坤聯名卡於燦坤店內消費，平日(週一~五)享1%燦坤K幣回饋無上限，週末(週六~日)享2%燦坤K幣回饋無上限。2026/1/1~2026/12/31。",
            category="SHOPPING",
            subcategory="ELECTRONICS",
            channel="OFFLINE",
            recommendation_scope="RECOMMENDABLE",
            reward={"type": "PERCENT", "value": 2.0},
            valid_from="2026-01-01",
            valid_until="2026-12-31",
            extra_conditions=[
                {"type": "RETAIL_CHAIN", "value": "TSANN_KUEN", "label": "燦坤"},
            ],
        ),
    ]


def _collect_line_window(
    lines: Sequence[str],
    start_token: str,
    *,
    stop_tokens: Sequence[str],
    max_lines: int = 48,
) -> str:
    start_index = next((index for index, line in enumerate(lines) if start_token in line), None)
    if start_index is None:
        return ""

    collected: List[str] = []
    for line in lines[start_index:start_index + max_lines]:
        if collected and any(token in line for token in stop_tokens):
            break
        if not line.strip():
            continue
        collected.append(line.strip())
    return clean_offer_text(" ".join(collected))


def _build_manual_promotion(
    card: CardRecord,
    *,
    title: str,
    body: str,
    category: str,
    subcategory: str,
    channel: str,
    recommendation_scope: str,
    extra_conditions: Sequence[Dict[str, str]] = (),
    valid_from: str | None = None,
    valid_until: str | None = None,
    reward: Dict[str, object] | None = None,
) -> Dict[str, object]:
    resolved_reward = reward or _extract_reward(title, body)
    if resolved_reward is None:
        resolved_reward = {"type": "FIXED", "value": 0}

    parsed_valid_from, parsed_valid_until = extract_date_range(body)
    valid_from = valid_from or parsed_valid_from or "2026-01-01"
    valid_until = valid_until or parsed_valid_until or "2026-12-31"
    min_amount = extract_min_amount(body)
    max_cashback = extract_cap(body)
    requires_registration = any(token in body for token in REGISTRATION_TOKENS)
    frequency_limit = extract_frequency_limit(body)
    conditions = build_conditions(body, card.application_requirements, requires_registration)
    conditions.extend(dict(condition) for condition in extra_conditions)
    conditions = sanitize_payment_conditions(title, body, conditions)
    summary = build_summary(
        title,
        body,
        valid_from,
        valid_until,
        min_amount,
        max_cashback,
        requires_registration,
        summary_noise_tokens=SUMMARY_NOISE_TOKENS,
    )

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
        "cashbackType": resolved_reward["type"],
        "cashbackValue": resolved_reward["value"],
        "minAmount": min_amount,
        "maxCashback": max_cashback,
        "frequencyLimit": frequency_limit,
        "requiresRegistration": requires_registration,
        "recommendationScope": recommendation_scope,
        "eligibilityType": infer_eligibility_type(card.card_name),
        "validFrom": valid_from,
        "validUntil": valid_until,
        "conditions": conditions,
        "excludedConditions": [],
        "sourceUrl": card.detail_url,
        "summary": summary,
        "status": "ACTIVE",
        "planId": None,
    }


def _extract_richart_bonus_promotions(card: CardRecord, detail_links: Iterable[Dict[str, str]]) -> List[Dict[str, object]]:
    pending_urls = list(dict.fromkeys([
        *_extract_promotion_urls(detail_links),
        *RICHART_GUIDE_URLS,
    ]))
    promotions: List[Dict[str, object]] = []
    visited: set[str] = set()

    while pending_urls:
        url = pending_urls.pop(0)
        if url in visited:
            continue
        visited.add(url)

        html = ingest.fetch_with_playwright(url)
        links = collect_links(html, url)

        if _is_richart_guide_url(url):
            for promo_url in _extract_promotion_urls(links):
                if promo_url not in visited:
                    pending_urls.append(promo_url)
            continue

        promotion = _extract_marketing_promotion(card, html, url)
        if promotion is not None:
            promotions.extend(
                expand_general_reward_promotions(
                    promotion,
                    str(promotion.get("title", "") or ""),
                    str(promotion.get("summary", "") or ""),
                )
            )

    return promotions


def _extract_promotion_urls(links: Iterable[Dict[str, str]]) -> List[str]:
    urls: List[str] = []
    for link in links:
        href = link.get("href", "")
        if any(host in href for host in PROMOTION_HOST_TOKENS) and any(path in href for path in PROMOTION_PATH_TOKENS):
            urls.append(href)
    return urls


def _is_richart_guide_url(url: str) -> bool:
    return (
        "/TSB/personal/credit/discount/life/" in url
        or "/TSB/personal/digital/E-Payment/Electronic-Payment/introduction/" in url
    )


def _extract_marketing_promotion(card: CardRecord, html: str, source_url: str) -> Dict[str, object] | None:
    lines = html_to_lines(html)
    page_text = clean_offer_text(" ".join(lines))
    if not any(keyword in page_text for keyword in RICHART_KEYWORDS):
        return None

    focused_text = _build_marketing_focus_text(lines) or page_text
    title = _select_marketing_title(lines, focused_text)
    if _should_skip_richart_marketing(title, focused_text):
        return None

    plan_id = _resolve_richart_plan_id(card.card_code, _infer_category(title, focused_text), title, focused_text)
    if plan_id is None:
        return None

    reward = _extract_reward(title, focused_text)
    if reward is None:
        return None

    valid_from, valid_until = extract_date_range(focused_text)
    if not valid_from or not valid_until:
        return None

    min_amount = extract_min_amount(focused_text)
    max_cashback = extract_cap(focused_text)
    requires_registration = any(token in focused_text for token in REGISTRATION_TOKENS)
    frequency_limit = extract_frequency_limit(focused_text)
    category = _infer_category(title, focused_text)
    subcategory = infer_subcategory(title, focused_text, category, SUBCATEGORY_SIGNALS)
    category, subcategory = apply_plan_subcategory_hint(
        plan_id,
        category,
        subcategory,
        title=title,
        body=focused_text,
    )
    recommendation_scope = _resolve_richart_marketing_scope(title, focused_text, category, requires_registration, plan_id=plan_id)
    conditions = build_conditions(focused_text, card.application_requirements, requires_registration)
    conditions = append_inferred_subcategory_conditions(title, focused_text, category, subcategory, conditions)
    conditions = append_inferred_payment_method_conditions(category, subcategory, conditions, title, focused_text)
    conditions = _append_richart_plan_conditions(plan_id, subcategory, conditions)
    conditions = _append_richart_tier_conditions(plan_id, reward["value"], conditions)
    conditions = sanitize_payment_conditions(title, focused_text, conditions)
    conditions = append_inferred_cobranded_conditions(title, focused_text, conditions)
    conditions = append_inferred_date_conditions(title, focused_text, conditions)
    conditions = append_bank_wide_promotion_condition(
        title,
        focused_text,
        recommendation_scope,
        conditions,
        requires_registration=requires_registration,
        plan_id=plan_id,
        subcategory=subcategory,
    )
    conditions = append_catalog_review_conditions(
        title,
        focused_text,
        recommendation_scope,
        conditions,
        requires_registration=requires_registration,
        plan_id=plan_id,
    )
    subcategory = canonicalize_subcategory(category, subcategory, conditions)
    summary = build_summary(
        title,
        focused_text,
        valid_from,
        valid_until,
        min_amount,
        max_cashback,
        requires_registration,
        summary_noise_tokens=SUMMARY_NOISE_TOKENS,
    )

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
        "channel": _infer_channel(title, focused_text),
        "cashbackType": reward["type"],
        "cashbackValue": reward["value"],
        "minAmount": min_amount,
        "maxCashback": max_cashback,
        "frequencyLimit": frequency_limit,
        "requiresRegistration": requires_registration,
        "recommendationScope": recommendation_scope,
        "eligibilityType": infer_eligibility_type(card.card_name),
        "validFrom": valid_from,
        "validUntil": valid_until,
        "conditions": conditions,
        "excludedConditions": [],
        "sourceUrl": source_url,
        "summary": summary,
        "status": "ACTIVE",
        "planId": plan_id,
    }


def _select_marketing_title(lines: List[str], page_text: str) -> str:
    for line in lines[:20]:
        if len(line) > 80:
            continue
        if not any(keyword in line for keyword in RICHART_KEYWORDS):
            continue
        if not re.search(r"\d+(?:\.\d+)?%|[\d,]+\s*(?:點|元|Point)", line):
            continue
        return line

    for line in lines[:40]:
        if len(line) <= 60 and any(keyword in line for keyword in RICHART_KEYWORDS):
            return line

    match = re.search(r"([^。]{0,40}Richart[^。]{0,40})", page_text)
    if match:
        return match.group(1).strip()
    return "Richart優惠"


def _build_marketing_focus_text(lines: List[str]) -> str:
    focused_lines: List[str] = []
    for line in lines:
        if len(line) > 160:
            continue
        if any(token in line for token in MARKETING_NOISE_TOKENS):
            continue
        if any(keyword in line for keyword in RICHART_KEYWORDS):
            focused_lines.append(line)
            continue
        if re.search(r"\d{3,4}/\d{1,2}/\d{1,2}", line):
            focused_lines.append(line)
            continue
        if re.search(r"\d+(?:\.\d+)?%", line) and len(line) <= 120:
            focused_lines.append(line)
            continue
        if any(token in line for token in ("LINE Pay", "台新Pay", "街口", "高鐵", "臺鐵", "台鐵", "餐飲", "影音", "旅遊", "訂房")):
            focused_lines.append(line)

    return clean_offer_text(" ".join(dict.fromkeys(focused_lines)))


def _resolve_richart_plan_id(card_code: str, category: str, title: str, body: str) -> str | None:
    if card_code != "TAISHIN_RICHART":
        return infer_plan_id(card_code, category, title=title)

    combined = f"{title} {body}"
    for keywords, plan_id in RICHART_PLAN_HINTS:
        if any(keyword in combined for keyword in keywords):
            return plan_id
    return infer_plan_id(card_code, category, title=title)


def _append_richart_plan_conditions(
    plan_id: str | None,
    subcategory: str | None,
    conditions: List[Dict[str, object]],
) -> List[Dict[str, object]]:
    if not plan_id or not subcategory:
        return conditions

    extra_conditions = RICHART_PLAN_CONDITIONS.get((plan_id, subcategory.upper()))
    if not extra_conditions:
        return conditions

    merged = list(conditions)
    seen = {
        (str(condition.get("type", "")).upper(), str(condition.get("value", "")).upper())
        for condition in merged
    }
    for condition in extra_conditions:
        key = (condition["type"].upper(), condition["value"].upper())
        if key in seen:
            continue
        merged.append(dict(condition))
        seen.add(key)
    return merged


def _append_richart_tier_conditions(
    plan_id: str | None,
    cashback_value: object,
    conditions: List[Dict[str, object]],
) -> List[Dict[str, object]]:
    if not plan_id or plan_id not in RICHART_TIERED_PLAN_IDS:
        return conditions

    try:
        normalized_rate = round(float(cashback_value), 1)
    except (TypeError, ValueError):
        return conditions

    if normalized_rate not in RICHART_TIER_SENSITIVE_RATES:
        return conditions

    marker = {
        "type": "TEXT",
        "value": "RICHART_BENEFIT_TIER_REQUIRED",
        "label": "Richart LEVEL 1 / LEVEL 2 affects actual reward rate",
    }

    merged = list(conditions)
    if any(
        str(condition.get("type", "")).upper() == marker["type"]
        and str(condition.get("value", "")).upper() == marker["value"]
        for condition in merged
    ):
        return merged

    merged.append(marker)
    return merged


def _should_skip_richart_marketing(title: str, text: str) -> bool:
    combined = f"{title} {text}"
    return any(token in combined for token in RICHART_EXCLUDED_ACTIVITY_TOKENS)


def _resolve_richart_marketing_scope(
    title: str, text: str, category: str, requires_registration: bool,
    *, plan_id: str | None = None,
) -> str:
    if plan_id and requires_registration:
        scope = classify_recommendation_scope(title, text, category)
        if scope != "FUTURE_SCOPE":
            return "RECOMMENDABLE"
    combined = f"{title} {text}"
    hard_catalog_tokens = [token for token in RICHART_CATALOG_ONLY_TOKENS if token not in REGISTRATION_TOKENS]
    if any(token in combined for token in hard_catalog_tokens):
        return "CATALOG_ONLY"
    scope = classify_recommendation_scope(title, text, category)
    if requires_registration and scope == "RECOMMENDABLE" and is_registration_heavy_catalog_offer(combined):
        return "CATALOG_ONLY"
    return scope


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
