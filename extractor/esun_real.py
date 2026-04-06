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
    append_inferred_subcategory_conditions,
    append_inferred_payment_method_conditions,
    append_catalog_review_conditions,
    append_bank_wide_promotion_condition,
    canonicalize_subcategory,
    sanitize_payment_conditions,
    SUBCATEGORY_SIGNALS,
    to_condition_value,
)


CARD_LIST_URL = "https://www.esunbank.com/zh-tw/personal/credit-card/intro"
BANK_CODE = "ESUN"
BANK_NAME = "玉山銀行"

UNICARD_TRANSPORT_CLUSTERS = (
    (
        "RIDESHARE",
        "共享交通",
        (
            {"type": "MERCHANT", "value": "GOSHARE", "label": "GoShare"},
            {"type": "MERCHANT", "value": "WEMO", "label": "WeMo"},
        ),
    ),
    (
        "EV_CHARGING",
        "充電通路",
        (
            {"type": "MERCHANT", "value": "U_POWER", "label": "U-POWER"},
            {"type": "MERCHANT", "value": "EVOASIS", "label": "EVOASIS"},
            {"type": "MERCHANT", "value": "AMPGO", "label": "AmpGO"},
            {"type": "MERCHANT", "value": "NATIONWIDE_FAST_CHARGING", "label": "全國特急電"},
        ),
    ),
)

UNICARD_PLAN_CONDITIONS: dict[tuple[str, str], tuple[dict[str, str], ...]] = {
    ("ESUN_UNICARD_FLEXIBLE", "MOBILE_PAY"): (
        {"type": "PAYMENT_PLATFORM", "value": "LINE_PAY", "label": "LINE Pay"},
        {"type": "PAYMENT_PLATFORM", "value": "JKOPAY", "label": "街口支付"},
        {"type": "PAYMENT_PLATFORM", "value": "ESUN_WALLET", "label": "玉山 Wallet"},
    ),
    ("ESUN_UNICARD_FLEXIBLE", "STREAMING"): (
        {"type": "MERCHANT", "value": "NETFLIX", "label": "Netflix"},
        {"type": "MERCHANT", "value": "SPOTIFY", "label": "Spotify"},
        {"type": "MERCHANT", "value": "DISNEY_PLUS", "label": "Disney+"},
        {"type": "MERCHANT", "value": "YOUTUBE_PREMIUM", "label": "YouTube Premium"},
    ),
    ("ESUN_UNICARD_SIMPLE", "SUPERMARKET"): (
        {"type": "RETAIL_CHAIN", "value": "PXMART", "label": "全聯"},
        {"type": "RETAIL_CHAIN", "value": "CARREFOUR", "label": "家樂福"},
        {"type": "RETAIL_CHAIN", "value": "LOPIA", "label": "LOPIA"},
    ),
    ("ESUN_UNICARD_SIMPLE", "DEPARTMENT"): (
        {"type": "RETAIL_CHAIN", "value": "SHIN_KONG_MITSUKOSHI", "label": "新光三越"},
        {"type": "RETAIL_CHAIN", "value": "SOGO", "label": "遠東SOGO"},
        {"type": "RETAIL_CHAIN", "value": "FAR_EAST_DEPARTMENT_STORE", "label": "遠東百貨"},
    ),
    ("ESUN_UNICARD_SIMPLE", "GAS_STATION"): (
        {"type": "RETAIL_CHAIN", "value": "CPC", "label": "台灣中油"},
        {"type": "RETAIL_CHAIN", "value": "NATIONWIDE_GAS", "label": "全國加油"},
        {"type": "RETAIL_CHAIN", "value": "FORMOSA_PETROCHEMICAL", "label": "台塑石油"},
        {"type": "RETAIL_CHAIN", "value": "TAIA", "label": "台亞"},
        {"type": "RETAIL_CHAIN", "value": "FORMOZA", "label": "福懋"},
    ),
    ("ESUN_UNICARD_UP", "SUPERMARKET"): (
        {"type": "RETAIL_CHAIN", "value": "PXMART", "label": "全聯"},
        {"type": "RETAIL_CHAIN", "value": "CARREFOUR", "label": "家樂福"},
        {"type": "RETAIL_CHAIN", "value": "LOPIA", "label": "LOPIA"},
    ),
    ("ESUN_UNICARD_UP", "DEPARTMENT"): (
        {"type": "RETAIL_CHAIN", "value": "SHIN_KONG_MITSUKOSHI", "label": "新光三越"},
        {"type": "RETAIL_CHAIN", "value": "SOGO", "label": "遠東SOGO"},
        {"type": "RETAIL_CHAIN", "value": "FAR_EAST_DEPARTMENT_STORE", "label": "遠東百貨"},
    ),
}

UNICARD_HUNDRED_STORE_CLUSTER_META: dict[str, dict[str, str]] = {
    "行動支付": {
        "category": "ONLINE",
        "subcategory": "GENERAL",
        "channel": "ONLINE",
        "condition_type": "PAYMENT_PLATFORM",
    },
    "加油交通": {
        "category": "TRANSPORT",
        "subcategory": "GENERAL",
        "channel": "ALL",
        "condition_type": "MERCHANT",
    },
    "國內百貨": {
        "category": "SHOPPING",
        "subcategory": "DEPARTMENT",
        "channel": "OFFLINE",
        "condition_type": "RETAIL_CHAIN",
    },
    "餐飲美食": {
        "category": "DINING",
        "subcategory": "GENERAL",
        "channel": "ALL",
        "condition_type": "MERCHANT",
    },
    "航空旅遊": {
        "category": "OVERSEAS",
        "subcategory": "GENERAL",
        "channel": "ALL",
        "condition_type": "MERCHANT",
    },
    "精選商家": {
        "category": "SHOPPING",
        "subcategory": "GENERAL",
        "channel": "ALL",
        "condition_type": "RETAIL_CHAIN",
    },
    "生活採買": {
        "category": "GROCERY",
        "subcategory": "GENERAL",
        "channel": "ALL",
        "condition_type": "RETAIL_CHAIN",
    },
    "電商平台": {
        "category": "ONLINE",
        "subcategory": "ECOMMERCE",
        "channel": "ONLINE",
        "condition_type": "ECOMMERCE_PLATFORM",
    },
    "國外實體": {
        "category": "OVERSEAS",
        "subcategory": "GENERAL",
        "channel": "OFFLINE",
        "condition_type": "LOCATION_ONLY",
    },
    "ESG消費": {
        "category": "OTHER",
        "subcategory": "GENERAL",
        "channel": "ALL",
        "condition_type": "MERCHANT",
    },
}

UNICARD_HUNDRED_STORE_VARIANTS: dict[str, tuple[dict[str, object], ...]] = {
    "加油交通": (
        {
            "title_suffix": "加油",
            "category": "TRANSPORT",
            "subcategory": "GAS_STATION",
            "channel": "ALL",
            "condition_type": "RETAIL_CHAIN",
            "match_tokens": ("台灣中油", "中油", "全國加油", "台塑石油", "台亞", "福懋"),
            "condition_overrides": {
                "台灣中油": ("CPC", "台灣中油"),
                "中油": ("CPC", "台灣中油"),
                "全國加油": ("NATIONWIDE_GAS", "全國加油"),
                "台塑石油": ("FORMOSA_PETROCHEMICAL", "台塑石油"),
                "台亞": ("TAIA", "台亞"),
                "福懋": ("FORMOZA", "福懋"),
            },
        },
        {
            "title_suffix": "大眾運輸",
            "category": "TRANSPORT",
            "subcategory": "PUBLIC_TRANSIT",
            "channel": "ALL",
            "condition_type": "MERCHANT",
            "match_tokens": ("台鐵", "臺鐵", "高鐵"),
            "condition_overrides": {
                "台鐵": ("TRA", "台鐵"),
                "臺鐵": ("TRA", "台鐵"),
                "高鐵": ("THSR", "高鐵"),
            },
        },
        {
            "title_suffix": "叫車 / 共享",
            "category": "TRANSPORT",
            "subcategory": "RIDESHARE",
            "channel": "ALL",
            "condition_type": "MERCHANT",
            "match_tokens": ("UBER", "YOXI", "55688", "台灣大車隊"),
            "condition_overrides": {
                "UBER": ("UBER", "Uber"),
                "YOXI": ("YOXI", "yoxi"),
                "55688": ("TAIWAN_TAXI", "台灣大車隊"),
                "台灣大車隊": ("TAIWAN_TAXI", "台灣大車隊"),
            },
        },
    ),
    "餐飲美食": (
        {
            "title_suffix": "外送",
            "category": "DINING",
            "subcategory": "DELIVERY",
            "channel": "ONLINE",
            "condition_type": "MERCHANT",
            "match_tokens": ("UBER EATS", "FOODPANDA"),
            "condition_overrides": {
                "UBER EATS": ("UBER_EATS", "Uber Eats"),
                "FOODPANDA": ("FOODPANDA", "foodpanda"),
            },
        },
        {
            "title_suffix": "餐廳",
            "category": "DINING",
            "subcategory": "RESTAURANT",
            "channel": "ALL",
            "condition_type": "MERCHANT",
            "exclude_tokens": ("UBER EATS", "FOODPANDA"),
            "condition_overrides": {
                "EZTABLE": ("EZTABLE", "EZTABLE"),
            },
        },
    ),
    "航空旅遊": (
        {
            "title_suffix": "航空",
            "category": "TRANSPORT",
            "subcategory": "AIRLINE",
            "channel": "ALL",
            "condition_type": "MERCHANT",
            "match_tokens": ("中華航空", "長榮航空", "日本航空", "台灣虎航", "樂桃航空", "酷航"),
            "condition_overrides": {
                "中華航空": ("CHINA_AIRLINES", "中華航空"),
                "長榮航空": ("EVA_AIR", "長榮航空"),
                "日本航空": ("JAPAN_AIRLINES", "日本航空"),
                "台灣虎航": ("TIGERAIR_TAIWAN", "台灣虎航"),
                "樂桃航空": ("PEACH", "樂桃航空"),
                "酷航": ("SCOOT", "酷航"),
            },
        },
        {
            "title_suffix": "旅遊平台",
            "category": "ONLINE",
            "subcategory": "TRAVEL_PLATFORM",
            "channel": "ONLINE",
            "condition_type": "MERCHANT",
            "exclude_tokens": ("中華航空", "長榮航空", "日本航空", "台灣虎航", "樂桃航空", "酷航"),
            "condition_overrides": {
                "TRIP.COM": ("TRIP_COM", "Trip.com"),
                "BOOKING.COM": ("BOOKING", "Booking.com"),
                "HOTELS.COM": ("HOTELS_COM", "Hotels.com"),
                "ASIAYO": ("ASIAYO", "AsiaYo"),
                "EXPEDIA": ("EXPEDIA", "Expedia"),
                "KKDAY": ("KKDAY", "KKday"),
                "KLOOK": ("KLOOK", "Klook"),
                "AGODA": ("AGODA", "Agoda"),
            },
        },
    ),
}

UNICARD_HUNDRED_STORE_VARIANTS.update(
    {
        "精選商家": (
            {
                "title_suffix": "3C 家電",
                "category": "SHOPPING",
                "subcategory": "ELECTRONICS",
                "channel": "ALL",
                "condition_type": "RETAIL_CHAIN",
                "match_tokens": ("APPLE", "小米", "全國電子", "燦坤"),
                "condition_overrides": {
                    "APPLE": ("APPLE_STORE", "Apple直營店"),
                    "小米": ("MI_STORE", "小米台灣"),
                    "全國電子": ("ELIFE", "全國電子"),
                    "燦坤": ("TSANN_KUEN", "燦坤"),
                },
            },
            {
                "title_suffix": "運動用品",
                "category": "SHOPPING",
                "subcategory": "SPORTING_GOODS",
                "channel": "ALL",
                "condition_type": "RETAIL_CHAIN",
                "match_tokens": ("迪卡儂",),
                "condition_overrides": {
                    "迪卡儂": ("DECATHLON", "迪卡儂"),
                },
            },
        ),
        "生活採買": (
            {
                "title_suffix": "超市量販",
                "category": "GROCERY",
                "subcategory": "SUPERMARKET",
                "channel": "ALL",
                "condition_type": "RETAIL_CHAIN",
                "match_tokens": ("家樂福",),
                "condition_overrides": {
                    "家樂福": ("CARREFOUR", "家樂福"),
                },
            },
            {
                "title_suffix": "藥妝",
                "category": "SHOPPING",
                "subcategory": "DRUGSTORE",
                "channel": "ALL",
                "condition_type": "RETAIL_CHAIN",
                "match_tokens": ("屈臣氏", "康是美", "大樹藥局", "丁丁藥妝"),
                "condition_overrides": {
                    "屈臣氏": ("WATSONS", "屈臣氏"),
                    "康是美": ("COSMED", "康是美"),
                    "大樹藥局": ("GREAT_TREE", "大樹藥局"),
                    "丁丁藥妝": ("DING_DING", "丁丁藥妝"),
                },
            },
            {
                "title_suffix": "居家生活",
                "category": "OTHER",
                "subcategory": "HOME_LIVING",
                "channel": "ALL",
                "condition_type": "RETAIL_CHAIN",
                "match_tokens": ("特力屋", "HOLA", "HOI"),
                "condition_overrides": {
                    "特力屋": ("TR_PLUS", "特力屋"),
                    "HOLA": ("HOLA", "HOLA"),
                    "HOI": ("HOI", "hoi好好生活"),
                },
            },
            {
                "title_suffix": "服飾",
                "category": "SHOPPING",
                "subcategory": "APPAREL",
                "channel": "ALL",
                "condition_type": "RETAIL_CHAIN",
                "match_tokens": ("UNIQLO", "NET"),
                "condition_overrides": {
                    "UNIQLO": ("UNIQLO", "UNIQLO"),
                    "NET": ("NET", "NET"),
                },
            },
        ),
        "ESG消費": (
            {
                "title_suffix": "充電",
                "category": "OTHER",
                "subcategory": "EV_CHARGING",
                "channel": "ALL",
                "condition_type": "MERCHANT",
                "match_tokens": ("特斯拉", "GOGORO"),
                "condition_overrides": {
                    "特斯拉": ("TESLA_SUPERCHARGER", "特斯拉"),
                    "GOGORO": ("GOGORO_BATTERY", "Gogoro電池資費"),
                },
            },
            {
                "title_suffix": "大眾運輸",
                "category": "TRANSPORT",
                "subcategory": "PUBLIC_TRANSIT",
                "channel": "ALL",
                "condition_type": "MERCHANT",
                "match_tokens": ("YOUBIKE",),
                "condition_overrides": {
                    "YOUBIKE": ("YOUBIKE_2_0", "YouBike 2.0"),
                },
            },
            {
                "title_suffix": "公益 / 捐款",
                "category": "OTHER",
                "subcategory": "CHARITY_DONATION",
                "channel": "ALL",
                "condition_type": "MERCHANT",
                "match_tokens": ("愛心捐款",),
                "condition_overrides": {
                    "單筆捐款": ("ESUN_WALLET_DONATION_SINGLE", "玉山Wallet愛心捐款-單筆捐款"),
                    "定期定額": ("ESUN_WALLET_DONATION_RECURRING", "玉山Wallet愛心捐款-定期定額"),
                },
            },
        ),
    }
)

CATEGORY_SIGNALS = {
    "OVERSEAS": [("日本", 4), ("韓國", 4), ("海外", 4), ("外幣", 3), ("航空", 3), ("旅遊", 3), ("旅行", 3), ("飯店", 3), ("住宿", 3), ("機場", 2), ("日圓", 2), ("韓圓", 2)],
    "ONLINE": [("Booking", 3), ("Agoda", 3), ("Hotels.com", 3), ("Expedia", 3), ("Klook", 3), ("KKday", 3), ("PChome", 4), ("蝦皮", 4), ("網購", 4), ("LINE Pay", 3), ("Uber Eats", 3), ("網頁", 2), ("網站", 2), ("平台", 1), ("APP", 1)],
    "DINING": [("餐飲", 4), ("餐廳", 3), ("咖啡", 2), ("壽司", 2), ("爭鮮", 3), ("星巴克", 2), ("熟成紅茶", 2)],
    "TRANSPORT": [("交通", 4), ("乘車", 4), ("高鐵", 4), ("台鐵", 4), ("捷運", 4), ("巴士", 3), ("TAXI", 4), ("機場接送", 4), ("大眾交通", 4), ("Suica", 4), ("加油", 2), ("中油", 2)],
    "SHOPPING": [("百貨", 3), ("新光三越", 5), ("購物", 3), ("購物園區", 4), ("免稅", 2), ("商圈", 2), ("OUTLET", 2)],
    "GROCERY": [("家樂福", 5), ("全聯", 5), ("超市", 4), ("量販", 3)],
    "ENTERTAINMENT": [("影城", 4), ("電影", 4), ("串流", 4), ("購票", 2), ("演唱會", 4), ("轉播", 2), ("健身房", 2), ("學習平台", 2), ("樂園", 5), ("遊樂園", 5), ("麗寶", 4), ("六福村", 4), ("劍湖山", 4)],
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
            "百大指定消費",
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
    active_sections=frozenset({"卡片特色", "專屬優惠", "百大指定消費", "Pi拍錢包加碼", "卡友禮遇服務"}),
    subsection_skip=frozenset(
        {
            "卡片介紹",
            "卡片特色",
            "專屬優惠",
            "百大指定消費",
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
        if "一般消費" in clean_title:
            category = "OTHER"
            subcategory = "GENERAL"
        plan_id = infer_plan_id(enriched_card.card_code, category, title=clean_title, subcategory=subcategory)
        category, subcategory = apply_plan_subcategory_hint(
            plan_id,
            category,
            subcategory,
            title=clean_title,
            body=clean_body,
        )
        recommendation_scope = classify_recommendation_scope(clean_title, clean_body, category)
        conditions = build_conditions(clean_body, enriched_card.application_requirements, requires_registration)
        conditions = append_inferred_subcategory_conditions(clean_title, clean_body, category, subcategory, conditions)
        conditions = append_inferred_payment_method_conditions(category, subcategory, conditions, clean_title, clean_body)
        conditions = _append_unicard_plan_conditions(plan_id, subcategory, conditions)
        conditions = sanitize_payment_conditions(clean_title, clean_body, conditions)
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

        promotions.extend(_expand_card_specific_promotions(enriched_card.card_code, clean_title, clean_body, base_promotion))

    promotions.extend(_extract_unicard_hundred_store_promotions(lines, enriched_card, eligibility_type))

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


def _expand_card_specific_promotions(
    card_code: str,
    title: str,
    body: str,
    promotion: Dict[str, object],
) -> List[Dict[str, object]]:
    if (
        card_code == "ESUN_UNICARD"
        and promotion.get("category") == "TRANSPORT"
        and "指定交通通路" in title
    ):
        expanded: List[Dict[str, object]] = []
        for subcategory, title_suffix, merchant_conditions in UNICARD_TRANSPORT_CLUSTERS:
            clone = dict(promotion)
            clone["subcategory"] = subcategory
            clone["title"] = f"{promotion['title']}（{title_suffix}）"
            clone["conditions"] = [*promotion.get("conditions", []), *merchant_conditions]
            expanded.append(clone)
        return expanded

    return [promotion]


def _append_unicard_plan_conditions(
    plan_id: str | None,
    subcategory: str | None,
    conditions: List[Dict[str, object]],
) -> List[Dict[str, object]]:
    if not plan_id or not subcategory:
        return conditions

    extra_conditions = UNICARD_PLAN_CONDITIONS.get((plan_id, subcategory.upper()))
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


def _filter_unicard_variant_labels(
    merchant_labels: List[str],
    *,
    match_tokens: tuple[str, ...] | None = None,
    exclude_tokens: tuple[str, ...] | None = None,
) -> List[str]:
    filtered: List[str] = []
    normalized_match_tokens = tuple(token.upper() for token in (match_tokens or ()))
    normalized_exclude_tokens = tuple(token.upper() for token in (exclude_tokens or ()))

    for label in merchant_labels:
        normalized_label = label.upper()
        if normalized_exclude_tokens and any(token in normalized_label for token in normalized_exclude_tokens):
            continue
        if normalized_match_tokens and not any(token in normalized_label for token in normalized_match_tokens):
            continue
        filtered.append(label)

    return filtered


def _build_unicard_hundred_store_promotion(
    *,
    card: CardRecord,
    eligibility_type: str,
    valid_from: str,
    valid_until: str,
    notes: str,
    rate_summary: str,
    title_suffix: str,
    category: str,
    subcategory: str,
    channel: str,
    condition_type: str,
    merchant_labels: List[str],
    condition_overrides: dict[str, tuple[str, str]] | None = None,
) -> Dict[str, object] | None:
    if not merchant_labels:
        return None

    conditions = [
        {"type": "TEXT", "value": "UNICARD_HUNDRED_STORE_CATALOG", "label": notes},
        *_build_unicard_hundred_store_conditions(condition_type, merchant_labels, condition_overrides=condition_overrides),
    ]
    if condition_type == "PAYMENT_PLATFORM":
        conditions.insert(1, {"type": "PAYMENT_METHOD", "value": "MOBILE_PAY", "label": "行動支付"})

    summary = (
        f"{title_suffix}百大指定消費，{rate_summary}，"
        f"共 {len(merchant_labels)} 個指定通路，有效期間 {valid_from}~{valid_until}"
    )

    conditions = sanitize_payment_conditions(title_suffix, " ".join(merchant_labels), conditions)

    return {
        "title": f"{card.card_name} 百大指定消費 {title_suffix}",
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
        "cashbackType": "PERCENT",
        "cashbackValue": 4.5,
        "minAmount": 0,
        "maxCashback": None,
        "frequencyLimit": "NONE",
        "requiresRegistration": False,
        "recommendationScope": "CATALOG_ONLY",
        "eligibilityType": eligibility_type,
        "validFrom": valid_from,
        "validUntil": valid_until,
        "conditions": conditions,
        "excludedConditions": [],
        "sourceUrl": card.detail_url,
        "summary": summary,
        "status": "ACTIVE",
        "planId": None,
    }


def _extract_unicard_hundred_store_promotions(
    lines: List[str],
    card: CardRecord,
    eligibility_type: str,
) -> List[Dict[str, object]]:
    if card.card_code != "ESUN_UNICARD":
        return []

    valid_from, valid_until, clusters = _extract_unicard_hundred_store_clusters(lines)
    if not valid_from or not valid_until or not clusters:
        return []

    rate_summary = "簡單選 3% / 任意選 3.5% / UP選 4.5%"
    notes = (
        "百大指定消費加碼以每月最後一日最終方案計算；任意選需於 100 家指定消費中自選最多 8 家；"
        "簡單選與任意選月上限 1,000 點，UP選月上限 5,000 點。"
    )

    promotions: List[Dict[str, object]] = []
    for cluster_name, merchant_labels in clusters:
        meta = UNICARD_HUNDRED_STORE_CLUSTER_META.get(cluster_name)
        if not meta or not merchant_labels:
            continue

        variants = UNICARD_HUNDRED_STORE_VARIANTS.get(cluster_name)
        if variants:
            for variant in variants:
                variant_labels = _filter_unicard_variant_labels(
                    merchant_labels,
                    match_tokens=variant.get("match_tokens"),
                    exclude_tokens=variant.get("exclude_tokens"),
                )
                promotion = _build_unicard_hundred_store_promotion(
                    card=card,
                    eligibility_type=eligibility_type,
                    valid_from=valid_from,
                    valid_until=valid_until,
                    notes=notes,
                    rate_summary=rate_summary,
                    title_suffix=str(variant["title_suffix"]),
                    category=str(variant["category"]),
                    subcategory=str(variant["subcategory"]),
                    channel=str(variant["channel"]),
                    condition_type=str(variant["condition_type"]),
                    merchant_labels=variant_labels,
                    condition_overrides=variant.get("condition_overrides"),
                )
                if promotion:
                    promotions.append(promotion)
            continue

        promotion = _build_unicard_hundred_store_promotion(
            card=card,
            eligibility_type=eligibility_type,
            valid_from=valid_from,
            valid_until=valid_until,
            notes=notes,
            rate_summary=rate_summary,
            title_suffix=cluster_name,
            category=meta["category"],
            subcategory=meta["subcategory"],
            channel=meta["channel"],
            condition_type=meta["condition_type"],
            merchant_labels=merchant_labels,
        )
        if promotion:
            promotions.append(promotion)

    return promotions


def _extract_unicard_hundred_store_clusters(lines: List[str]) -> tuple[str | None, str | None, List[tuple[str, List[str]]]]:
    try:
        start_index = lines.index("百大指定消費列表")
    except ValueError:
        return None, None, []

    valid_from = None
    valid_until = None
    clusters: List[tuple[str, List[str]]] = []
    known_cluster_names = set(UNICARD_HUNDRED_STORE_CLUSTER_META)

    index = start_index + 1
    while index < len(lines):
        line = lines[index]
        if not valid_from or not valid_until:
            valid_from, valid_until = extract_date_range(line)

        if line == "百大指定消費列表注意事項":
            break

        if line in {"類別", "指定百大指定消費"} or "適用百大指定消費列表如下" in line or line.startswith("※"):
            index += 1
            continue

        if line in known_cluster_names and index + 1 < len(lines):
            merchant_line = lines[index + 1]
            if merchant_line == "百大指定消費列表注意事項":
                break
            clusters.append((line, _split_unicard_merchant_labels(merchant_line)))
            index += 2
            continue

        index += 1

    return valid_from, valid_until, clusters


def _split_unicard_merchant_labels(value: str) -> List[str]:
    labels: List[str] = []
    current: List[str] = []
    depth = 0

    for char in value:
        if char in "(（":
            depth += 1
        elif char in ")）" and depth > 0:
            depth -= 1

        if char == "、" and depth == 0:
            label = collapse_text("".join(current))
            if label:
                labels.append(label)
            current = []
            continue

        current.append(char)

    trailing = collapse_text("".join(current))
    if trailing:
        labels.append(trailing)

    return labels


def _build_unicard_hundred_store_conditions(
    condition_type: str,
    merchant_labels: List[str],
    condition_overrides: dict[str, tuple[str, str]] | None = None,
) -> List[Dict[str, str]]:
    conditions: List[Dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for label in merchant_labels:
        if not label:
            continue

        value = label.strip() if condition_type == "LOCATION_ONLY" else to_condition_value(label)
        normalized_label = label.upper()
        if condition_overrides:
            for token, override in condition_overrides.items():
                if token.upper() in normalized_label:
                    value, label = override
                    break

        key = (condition_type, value)
        if key in seen:
            continue
        seen.add(key)

        conditions.append({"type": condition_type, "value": value, "label": label})

    return conditions
