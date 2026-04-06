from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List
from urllib.parse import urljoin

from extractor import ingest
from extractor.benefit_plans import apply_plan_subcategory_hint
from extractor.html_utils import collapse_text, html_to_lines
from extractor.normalize import clean_card_name, infer_eligibility_type
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


CARD_LIST_URL = "https://www.cathay-cube.com.tw/cathaybk/personal/product/credit-card/cards"
CARD_LIST_MODEL_URL = f"{CARD_LIST_URL}.model.json"
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
PROMOTION_SIGNAL_PATTERN = re.compile(r"\d+(?:\.\d+)?%|[\d,]+\s*(?:元|點|日圓)|回饋|折扣|現折|優惠|加碼|里程|哩程|點數")
DATE_PATTERN = re.compile(r"\d{4}/\d{1,2}/\d{1,2}\s*[~～-]\s*\d{4}/\d{1,2}/\d{1,2}")

CUBE_LIST_URL = "https://www.cathay-cube.com.tw/cathaybk/personal/product/credit-card/cards/cube-list"

# Plan name → (planId, default_cashback_rate, primary category)
# Used for plans whose rate isn't embedded in the JSON model data.
CUBE_PLAN_CONFIG: dict[str, tuple[str, str, str]] = {
    "玩數位": ("CATHAY_CUBE_DIGITAL", "3", "ONLINE"),
    "樂饗購": ("CATHAY_CUBE_SHOPPING", "3", "SHOPPING"),
    "趣旅行": ("CATHAY_CUBE_TRAVEL", "3", "OVERSEAS"),
    "集精選": ("CATHAY_CUBE_ESSENTIALS", "2", "OTHER"),
    "慶生月": ("CATHAY_CUBE_BIRTHDAY", "3.5", "DINING"),
    "童樂匯": ("CATHAY_CUBE_KIDS", "5", "OTHER"),
    "日本賞": ("CATHAY_CUBE_JAPAN", "3.5", "OVERSEAS"),
}

CUBE_PLAN_VARIANTS: dict[str, list[dict[str, str]]] = {
    "玩數位": [
        {
            "title_suffix": "指定通路回饋",
            "category": "ONLINE",
            "subcategory": "GENERAL",
            "channel": "ONLINE",
            "body": "網購、數位訂閱與 AI 工具等指定通路",
        },
        {
            "title_suffix": "AI工具訂閱",
            "category": "ONLINE",
            "subcategory": "AI_TOOL",
            "channel": "ONLINE",
            "body": "ChatGPT、Canva、Claude、Cursor、Duolingo、Gamma、Gemini、Notion、Perplexity、Speak",
        },
        {
            "title_suffix": "串流影音平台",
            "category": "ENTERTAINMENT",
            "subcategory": "STREAMING",
            "channel": "ONLINE",
            "body": "Apple 媒體服務、Google Play、Disney+、Netflix、Spotify、YouTube Premium、Max",
        },
        {
            "title_suffix": "網購平台",
            "category": "ONLINE",
            "subcategory": "ECOMMERCE",
            "channel": "ONLINE",
            "body": "蝦皮購物、momo購物網、PChome 24h購物、小樹購",
        },
        {
            "title_suffix": "國際電商",
            "category": "ONLINE",
            "subcategory": "INTERNATIONAL_ECOMMERCE",
            "channel": "ONLINE",
            "body": "Coupang 酷澎(台灣)、淘寶、天貓",
        },
    ],
    "樂饗購": [
        {
            "title_suffix": "指定通路回饋",
            "category": "SHOPPING",
            "subcategory": "GENERAL",
            "channel": "ALL",
            "body": "百貨購物、美食餐廳、外送平台與藥妝等指定通路",
        },
        {
            "title_suffix": "國內餐飲",
            "category": "DINING",
            "subcategory": "GENERAL",
            "channel": "OFFLINE",
            "body": "國內餐飲與麥當勞等指定餐飲通路",
        },
        {
            "title_suffix": "外送平台",
            "category": "DINING",
            "subcategory": "DELIVERY",
            "channel": "ONLINE",
            "body": "Uber Eats、foodpanda",
        },
        {
            "title_suffix": "百貨購物",
            "category": "SHOPPING",
            "subcategory": "DEPARTMENT",
            "channel": "OFFLINE",
            "body": "遠東SOGO、新光三越、遠東百貨、台北101、BELLAVITA、微風廣場、誠品生活、京站、夢時代、漢神百貨等指定百貨",
        },
        {
            "title_suffix": "藥妝通路",
            "category": "SHOPPING",
            "subcategory": "DRUGSTORE",
            "channel": "OFFLINE",
            "body": "康是美、屈臣氏",
        },
    ],
    "趣旅行": [
        {
            "title_suffix": "指定通路回饋",
            "category": "OVERSEAS",
            "subcategory": "GENERAL",
            "channel": "ALL",
            "body": "海外消費、交通、航空、飯店、旅遊平台與旅行社等指定通路",
        },
        {
            "title_suffix": "指定交通",
            "category": "TRANSPORT",
            "subcategory": "GENERAL",
            "channel": "ALL",
            "body": "Apple 錢包指定交通卡、Uber、Grab、台灣高鐵、yoxi、台灣大車隊、iRent、和運租車、格上租車",
        },
        {
            "title_suffix": "叫車租車",
            "category": "TRANSPORT",
            "subcategory": "RIDESHARE",
            "channel": "ALL",
            "body": "Uber、Grab、yoxi、台灣大車隊、iRent、和運租車、格上租車",
        },
        {
            "title_suffix": "指定航空公司",
            "category": "TRANSPORT",
            "subcategory": "AIRLINE",
            "channel": "ALL",
            "body": "中華航空、長榮航空、星宇航空、台灣虎航、國泰航空、樂桃航空、阿聯酋航空、酷航、捷星航空、日本航空、ANA全日空、亞洲航空、聯合航空、新加坡航空、越捷航空、大韓航空、達美航空、土耳其航空、卡達航空、法國航空",
        },
        {
            "title_suffix": "海外實體消費",
            "category": "OVERSEAS",
            "subcategory": "OVERSEAS_IN_STORE",
            "channel": "OFFLINE",
            "body": "海外實體消費(含國外餐飲、飯店到店付款等)",
        },
        {
            "title_suffix": "旅遊訂房平台",
            "category": "OVERSEAS",
            "subcategory": "TRAVEL_PLATFORM",
            "channel": "ONLINE",
            "body": "KKday、Klook、Agoda、Airbnb、Booking.com、Trip.com、ezTravel易遊網",
        },
    ],
    "集精選": [
        {
            "title_suffix": "指定通路回饋",
            "category": "OTHER",
            "subcategory": "GENERAL",
            "channel": "ALL",
            "body": "超商超市、加油、充電停車與生活家居等指定通路",
        },
        {
            "title_suffix": "量販超市",
            "category": "GROCERY",
            "subcategory": "SUPERMARKET",
            "channel": "OFFLINE",
            "body": "家樂福、LOPIA台灣、全聯福利中心實體門市",
        },
        {
            "title_suffix": "超商通路",
            "category": "GROCERY",
            "subcategory": "CONVENIENCE_STORE",
            "channel": "OFFLINE",
            "body": "7-ELEVEN實體門市、全家便利商店實體門市",
        },
        {
            "title_suffix": "充電通路",
            "category": "OTHER",
            "subcategory": "EV_CHARGING",
            "channel": "ALL",
            "body": "U-POWER、EVOASIS、EVALUE、TAIL、iCharging",
        },
        {
            "title_suffix": "停車通路",
            "category": "OTHER",
            "subcategory": "PARKING",
            "channel": "ALL",
            "body": "車麻吉、uTagGo",
        },
        {
            "title_suffix": "生活家居",
            "category": "OTHER",
            "subcategory": "HOME_LIVING",
            "channel": "OFFLINE",
            "body": "IKEA宜家家居",
        },
    ],
}

CUBE_VARIANT_CONDITIONS: dict[tuple[str, str], list[dict[str, str]]] = {
    ("玩數位", "AI_TOOL"): [
        {"type": "MERCHANT", "value": "CHATGPT", "label": "ChatGPT"},
        {"type": "MERCHANT", "value": "CANVA", "label": "Canva"},
        {"type": "MERCHANT", "value": "CLAUDE", "label": "Claude"},
        {"type": "MERCHANT", "value": "CURSOR", "label": "Cursor"},
        {"type": "MERCHANT", "value": "DUOLINGO", "label": "Duolingo"},
        {"type": "MERCHANT", "value": "GAMMA", "label": "Gamma"},
        {"type": "MERCHANT", "value": "GEMINI", "label": "Gemini"},
        {"type": "MERCHANT", "value": "NOTION", "label": "Notion"},
        {"type": "MERCHANT", "value": "PERPLEXITY", "label": "Perplexity"},
        {"type": "MERCHANT", "value": "SPEAK", "label": "Speak"},
    ],
    ("玩數位", "STREAMING"): [
        {"type": "MERCHANT", "value": "APPLE_MEDIA_SERVICES", "label": "Apple 媒體服務"},
        {"type": "MERCHANT", "value": "GOOGLE_PLAY", "label": "Google Play"},
        {"type": "MERCHANT", "value": "DISNEY_PLUS", "label": "Disney+"},
        {"type": "MERCHANT", "value": "NETFLIX", "label": "Netflix"},
        {"type": "MERCHANT", "value": "SPOTIFY", "label": "Spotify"},
        {"type": "MERCHANT", "value": "YOUTUBE_PREMIUM", "label": "YouTube Premium"},
        {"type": "MERCHANT", "value": "MAX", "label": "Max"},
    ],
    ("玩數位", "ECOMMERCE"): [
        {"type": "ECOMMERCE_PLATFORM", "value": "SHOPEE", "label": "蝦皮購物"},
        {"type": "ECOMMERCE_PLATFORM", "value": "MOMO", "label": "momo購物網"},
        {"type": "ECOMMERCE_PLATFORM", "value": "PCHOME_24H", "label": "PChome 24h購物"},
        {"type": "ECOMMERCE_PLATFORM", "value": "CUBE_SHOP", "label": "小樹購"},
    ],
    ("玩數位", "INTERNATIONAL_ECOMMERCE"): [
        {"type": "ECOMMERCE_PLATFORM", "value": "COUPANG", "label": "Coupang 酷澎"},
        {"type": "ECOMMERCE_PLATFORM", "value": "TAOBAO", "label": "淘寶"},
        {"type": "ECOMMERCE_PLATFORM", "value": "TMALL", "label": "天貓"},
    ],
    ("樂饗購", "DELIVERY"): [
        {"type": "MERCHANT", "value": "UBER_EATS", "label": "Uber Eats"},
        {"type": "MERCHANT", "value": "FOODPANDA", "label": "foodpanda"},
    ],
    ("樂饗購", "DEPARTMENT"): [
        {"type": "RETAIL_CHAIN", "value": "SOGO", "label": "遠東SOGO百貨"},
        {"type": "RETAIL_CHAIN", "value": "SHIN_KONG_MITSUKOSHI", "label": "新光三越"},
        {"type": "RETAIL_CHAIN", "value": "BREEZE", "label": "微風廣場"},
        {"type": "RETAIL_CHAIN", "value": "FAR_EAST_DEPARTMENT_STORE", "label": "遠東百貨"},
        {"type": "RETAIL_CHAIN", "value": "TAIPEI_101", "label": "台北101"},
    ],
    ("樂饗購", "DRUGSTORE"): [
        {"type": "RETAIL_CHAIN", "value": "COSMED", "label": "康是美"},
        {"type": "RETAIL_CHAIN", "value": "WATSONS", "label": "屈臣氏"},
    ],
    ("趣旅行", "RIDESHARE"): [
        {"type": "MERCHANT", "value": "UBER", "label": "Uber"},
        {"type": "MERCHANT", "value": "GRAB", "label": "Grab"},
        {"type": "MERCHANT", "value": "YOXI", "label": "yoxi"},
        {"type": "MERCHANT", "value": "TAIWAN_TAXI", "label": "台灣大車隊"},
        {"type": "MERCHANT", "value": "IRENT", "label": "iRent"},
    ],
    ("趣旅行", "AIRLINE"): [
        {"type": "MERCHANT", "value": "CHINA_AIRLINES", "label": "中華航空"},
        {"type": "MERCHANT", "value": "CAL", "label": "華航"},
        {"type": "MERCHANT", "value": "EVA_AIR", "label": "長榮航空"},
        {"type": "MERCHANT", "value": "STARLUX", "label": "星宇航空"},
        {"type": "MERCHANT", "value": "CATHAY_PACIFIC", "label": "國泰航空"},
        {"type": "MERCHANT", "value": "JAPAN_AIRLINES", "label": "日本航空"},
        {"type": "MERCHANT", "value": "ANA", "label": "ANA 全日空"},
        {"type": "MERCHANT", "value": "SINGAPORE_AIRLINES", "label": "新加坡航空"},
    ],
    ("趣旅行", "TRAVEL_PLATFORM"): [
        {"type": "MERCHANT", "value": "KKDAY", "label": "KKday"},
        {"type": "MERCHANT", "value": "KLOOK", "label": "Klook"},
        {"type": "MERCHANT", "value": "AGODA", "label": "Agoda"},
        {"type": "MERCHANT", "value": "AIRBNB", "label": "Airbnb"},
        {"type": "MERCHANT", "value": "BOOKING", "label": "Booking.com"},
        {"type": "MERCHANT", "value": "TRIP_COM", "label": "Trip.com"},
        {"type": "MERCHANT", "value": "EZTRAVEL", "label": "ezTravel"},
    ],
    ("集精選", "SUPERMARKET"): [
        {"type": "RETAIL_CHAIN", "value": "CARREFOUR", "label": "家樂福"},
        {"type": "RETAIL_CHAIN", "value": "LOPIA", "label": "LOPIA"},
        {"type": "RETAIL_CHAIN", "value": "PXMART", "label": "全聯福利中心"},
        {"type": "RETAIL_CHAIN", "value": "PXMART", "label": "全聯"},
    ],
    ("集精選", "CONVENIENCE_STORE"): [
        {"type": "RETAIL_CHAIN", "value": "7_ELEVEN", "label": "7-ELEVEN"},
        {"type": "RETAIL_CHAIN", "value": "FAMILYMART", "label": "全家便利商店"},
    ],
    ("集精選", "EV_CHARGING"): [
        {"type": "MERCHANT", "value": "U_POWER", "label": "U-POWER"},
        {"type": "MERCHANT", "value": "EVOASIS", "label": "EVOASIS"},
        {"type": "MERCHANT", "value": "EVALUE", "label": "EVALUE"},
        {"type": "MERCHANT", "value": "TAIL", "label": "TAIL"},
        {"type": "MERCHANT", "value": "ICHARGING", "label": "iCharging"},
    ],
    ("集精選", "PARKING"): [
        {"type": "MERCHANT", "value": "CHEMAJI", "label": "車麻吉"},
        {"type": "MERCHANT", "value": "UTAGGO", "label": "uTagGo"},
    ],
    ("集精選", "HOME_LIVING"): [
        {"type": "RETAIL_CHAIN", "value": "IKEA", "label": "IKEA"},
    ],
}

FORMOSA_GAS_STATION_CONDITIONS: tuple[dict[str, str], ...] = (
    {"type": "RETAIL_CHAIN", "value": "FORMOSA_PETROCHEMICAL", "label": "台塑石油"},
    {"type": "RETAIL_CHAIN", "value": "TAIA", "label": "台亞"},
    {"type": "RETAIL_CHAIN", "value": "FORMOZA", "label": "福懋"},
)

FORMOSA_AFFILIATE_CONDITIONS: tuple[dict[str, str], ...] = (
    {"type": "MERCHANT", "value": "FORMOSA_BIOMEDICAL", "label": "台塑生醫"},
    {"type": "MERCHANT", "value": "CHANG_GUNG_BIOTECH", "label": "長庚生技"},
    {"type": "MERCHANT", "value": "FORMOSA_SHOPPING", "label": "台塑購物網"},
    {"type": "MERCHANT", "value": "FORMOSA_TRAVEL", "label": "台塑網旅行社"},
)

FORMOSA_PROMO_DEFAULTS: dict[str, dict[str, object]] = {
    "加油降價天天享": {
        "reward": {"type": "FIXED", "value": 1.2},
        "category": "TRANSPORT",
        "subcategory": "GAS_STATION",
        "channel": "OFFLINE",
        "recommendation_scope": "CATALOG_ONLY",
        "valid_from": "2026-01-01",
        "valid_until": "2026-03-31",
        "conditions": FORMOSA_GAS_STATION_CONDITIONS,
    },
    "加油金再折抵": {
        "reward": {"type": "FIXED", "value": 2.0},
        "category": "TRANSPORT",
        "subcategory": "GAS_STATION",
        "channel": "OFFLINE",
        "recommendation_scope": "CATALOG_ONLY",
        "valid_from": "2026-01-01",
        "valid_until": "2026-07-31",
        "conditions": FORMOSA_GAS_STATION_CONDITIONS,
    },
    "週三加油日": {
        "reward": {"type": "FIXED", "value": 15.0},
        "category": "TRANSPORT",
        "subcategory": "GAS_STATION",
        "channel": "OFFLINE",
        "recommendation_scope": "CATALOG_ONLY",
        "valid_from": "2026-01-01",
        "valid_until": "2026-03-31",
        "conditions": FORMOSA_GAS_STATION_CONDITIONS,
    },
    "站外高回饋 最高回饋1%加油金": {
        "reward": {"type": "PERCENT", "value": 1.0},
        "category": "SHOPPING",
        "subcategory": "GENERAL",
        "channel": "ALL",
        "recommendation_scope": "CATALOG_ONLY",
        "valid_from": "2026-01-01",
        "valid_until": "2026-07-31",
        "conditions": FORMOSA_AFFILIATE_CONDITIONS,
    },
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


def list_cathay_cards() -> List[CardRecord]:
    model = _fetch_json(CARD_LIST_MODEL_URL)
    seen: set[tuple[str, str]] = set()
    cards: List[CardRecord] = []
    for component in _iter_components(model):
        credit_cards = component.get("creditCards")
        if not isinstance(credit_cards, list):
            continue
        for entry in credit_cards:
            if not isinstance(entry, dict):
                continue
            detail_url = _normalize_url(entry.get("ctaLink") or entry.get("cardLink") or entry.get("cardBtnLink"), CARD_LIST_URL)
            if not detail_url or "/credit-card/cards/" not in detail_url:
                continue
            card_name = clean_card_name(collapse_text(str(entry.get("cardName") or entry.get("itemName") or entry.get("title") or "")))
            if not card_name:
                continue
            dedupe_key = (card_name, detail_url)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            sections = _collect_text_list(entry.get("features"))
            cards.append(
                CardRecord(
                    card_code=_build_card_code(detail_url),
                    card_name=card_name,
                    detail_url=detail_url,
                    apply_url=_normalize_url(entry.get("cardBtnLink"), CARD_LIST_URL),
                    annual_fee_summary=None,
                    application_requirements=[],
                    sections=sections,
                )
            )

    return cards


def extract_card_promotions(card: CardRecord) -> tuple[CardRecord, List[Dict[str, object]]]:
    detail_model_url = _model_url(card.detail_url)
    model = _fetch_json(detail_model_url)
    components = list(_iter_components(model))

    detail_card_name = clean_card_name(_extract_detail_card_name(components) or card.card_name)
    apply_url = card.apply_url
    annual_fee_summary = card.annual_fee_summary
    application_requirements = list(card.application_requirements)

    for component in components:
        component_type = _component_type(component)
        if "creditcardapplyinfo" not in component_type:
            continue
        apply_url = _normalize_url(component.get("mainBtnLink") or component.get("subBtnLink"), card.detail_url) or apply_url
        information_lines = _collect_text_list(component.get("information"))
        if not annual_fee_summary:
            annual_fee_summary = _pick_annual_fee_summary(information_lines)
        application_requirements.extend(_extract_application_requirements(information_lines))

    enriched_card = CardRecord(
        card_code=card.card_code,
        card_name=detail_card_name,
        detail_url=card.detail_url,
        apply_url=apply_url,
        annual_fee_summary=annual_fee_summary,
        application_requirements=list(dict.fromkeys(application_requirements)),
        sections=card.sections,
    )

    promotions: List[Dict[str, object]] = []
    eligibility_type = infer_eligibility_type(enriched_card.card_name)
    for component in components:
        component_type = _component_type(component)
        if not any(
            token in component_type
            for token in ("horgraphictab", "simplegraphictab", "discountcard", "campaignpromotioncard", "treepointscardcf")
        ):
            continue

        for candidate in _extract_component_candidates(component):
            clean_title = normalize_promotion_title(
                enriched_card.card_name,
                candidate["title"],
                candidate["body"],
                generic_title_tokens=GENERIC_TITLE_TOKENS,
                summary_noise_tokens=SUMMARY_NOISE_TOKENS,
                bank_suffixes=(BANK_NAME, "國泰世華銀行"),
            )
            if not clean_title:
                continue

            clean_body = clean_offer_text(candidate["body"])

            reward = extract_reward(clean_title, clean_body)
            reward = _apply_card_specific_reward_override(
                enriched_card.card_code,
                clean_title,
                reward,
            )
            if reward is None:
                continue

            valid_from, valid_until = extract_date_range(clean_body)
            valid_from, valid_until = _apply_card_specific_validity_override(
                enriched_card.card_code,
                clean_title,
                valid_from,
                valid_until,
            )
            if not valid_from or not valid_until:
                continue

            requires_registration = "登錄" in clean_body
            min_amount = extract_min_amount(clean_body)
            max_cashback = extract_cap(clean_body)
            category = infer_category(clean_title, clean_body, CATEGORY_SIGNALS, overseas_category="OVERSEAS")
            subcategory = infer_subcategory(clean_title, clean_body, category, SUBCATEGORY_SIGNALS)
            recommendation_scope = classify_recommendation_scope(clean_title, clean_body, category)
            conditions = append_inferred_subcategory_conditions(
                clean_title,
                clean_body,
                category,
                subcategory,
                build_conditions(clean_body, enriched_card.application_requirements, requires_registration),
            )
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
            channel = infer_channel(clean_title, clean_body, CHANNEL_SIGNALS)
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
                    "frequencyLimit": extract_frequency_limit(candidate["body"]),
                    "requiresRegistration": requires_registration,
                    "recommendationScope": recommendation_scope,
                    "eligibilityType": eligibility_type,
                    "validFrom": valid_from,
                    "validUntil": valid_until,
                    "conditions": conditions,
                    "excludedConditions": [],
                    "sourceUrl": enriched_card.detail_url,
                    "summary": build_summary(
                        clean_title,
                        clean_body,
                        valid_from,
                        valid_until,
                        min_amount,
                        max_cashback,
                        requires_registration,
                        summary_noise_tokens=SUMMARY_NOISE_TOKENS,
                    ),
                    "status": "ACTIVE",
                }
            )

    plan_promotions = _extract_plan_promotions(enriched_card)
    promotions.extend(plan_promotions)

    return enriched_card, dedupe_promotions(promotions)


def _extract_plan_promotions(card: CardRecord) -> List[Dict[str, object]]:
    """Extract CUBE plan-based promotions from treepointscardcf and cube-list page."""
    if card.card_code != "CATHAY_CUBE":
        return []

    # Step 1: Get date ranges from cube-list page cubelisttitle components
    plan_dates: dict[str, tuple[str, str]] = {}
    try:
        cubelist_model = _fetch_json(_model_url(CUBE_LIST_URL))
        current_plan_name: str | None = None
        for comp in _iter_components(cubelist_model):
            ct = _component_type(comp)
            if "cubelisttitle" in ct:
                title_html = comp.get("mainTitle", "")
                plan_match = re.search(r">([^<]+?)(?:&nbsp;|\s*<)", title_html)
                if plan_match:
                    current_plan_name = plan_match.group(1).strip()
                date_match = re.search(
                    r"適用期間[：:](\d{4}/\d{1,2}/\d{1,2})\s*[~～]\s*(\d{4}/\d{1,2}/\d{1,2})",
                    title_html,
                )
                if date_match and current_plan_name:
                    vf = _normalize_date(date_match.group(1))
                    vu = _normalize_date(date_match.group(2))
                    if vf and vu:
                        plan_dates[current_plan_name] = (vf, vu)
    except Exception:
        pass  # cube-list page may be unavailable; proceed with what we have

    # Step 2: Extract structured rates from treepointscardcf on the main card page
    plan_rates: dict[str, list[dict[str, str]]] = {}
    try:
        detail_model = _fetch_json(_model_url(card.detail_url))
        for comp in _iter_components(detail_model):
            ct = _component_type(comp)
            if "treepointscard" not in ct:
                continue
            for tree in comp.get("contentTrees", []):
                tab_text = (tree.get("contentTreeItem") or {}).get("tabText", "")
                if not tab_text:
                    continue
                tiers: list[dict[str, str]] = []
                for card_item in tree.get("cardList", []):
                    rate = card_item.get("rate")
                    title = card_item.get("title", "")
                    content = collapse_text(card_item.get("content", ""))
                    content_clean = re.sub(r"<[^>]+>", "", content)
                    if rate and title and title != "一般消費":
                        tiers.append({"rate": rate, "title": title, "merchants": content_clean})
                if tiers:
                    plan_rates[tab_text] = tiers
    except Exception:
        pass

    # Step 3: Build promotions for each plan
    promotions: List[Dict[str, object]] = []
    seen_plans: set[str] = set()

    # 3a: Plans with structured rate data from treepointscardcf
    for plan_name, tiers in plan_rates.items():
        seen_plans.add(plan_name)
        config = CUBE_PLAN_CONFIG.get(plan_name)
        plan_id = config[0] if config else None
        dates = plan_dates.get(plan_name)

        for tier in tiers:
            rate = tier["rate"]
            tier_title = tier["title"]
            merchants = tier["merchants"]
            valid_from = dates[0] if dates else None
            valid_until = dates[1] if dates else None

            if not valid_from or not valid_until:
                continue

            variants = CUBE_PLAN_VARIANTS.get(plan_name)
            if variants:
                for variant in variants:
                    promo = _build_plan_promotion_with_conditions(
                        card=card,
                        title=f"{card.card_name} {plan_name} {variant['title_suffix']}",
                        body=f"{variant['body']}；{tier_title} 享{rate}%小樹點回饋",
                        rate=rate,
                        category=variant["category"],
                        subcategory=variant["subcategory"],
                        channel=variant["channel"],
                        valid_from=valid_from,
                        valid_until=valid_until,
                        plan_id=plan_id,
                        plan_name=plan_name,
                        extra_conditions=_build_variant_conditions(plan_name, variant["subcategory"]),
                    )
                    promotions.append(promo)
                continue

            category = infer_category(tier_title, merchants, CATEGORY_SIGNALS, overseas_category="OVERSEAS")
            subcategory = infer_subcategory(tier_title, merchants, category, SUBCATEGORY_SIGNALS)
            category, subcategory = apply_plan_subcategory_hint(
                plan_id,
                category,
                subcategory,
                title=tier_title,
                body=merchants,
            )
            channel = infer_channel(tier_title, merchants, CHANNEL_SIGNALS)
            title = f"{card.card_name} {plan_name} {tier_title}"
            body = f"{tier_title} 享{rate}%小樹點回饋 {merchants}"

            promo = _build_plan_promotion_with_conditions(
                card=card,
                title=title,
                body=body,
                rate=rate,
                category=category,
                subcategory=subcategory,
                channel=channel,
                valid_from=valid_from,
                valid_until=valid_until,
                plan_id=plan_id,
                plan_name=plan_name,
            )
            promotions.append(promo)

    # 3b: Plans without treepointscardcf data — use config fallback rates
    for plan_name, (plan_id, default_rate, default_category) in CUBE_PLAN_CONFIG.items():
        if plan_name in seen_plans:
            continue
        dates = plan_dates.get(plan_name)
        if not dates:
            continue

        valid_from, valid_until = dates
        variants = CUBE_PLAN_VARIANTS.get(plan_name)
        if variants:
            for variant in variants:
                promo = _build_plan_promotion_with_conditions(
                    card=card,
                    title=f"{card.card_name} {plan_name} {variant['title_suffix']}",
                    body=f"{variant['body']}；指定通路享{default_rate}%小樹點回饋",
                    rate=default_rate,
                    category=variant["category"],
                    subcategory=variant["subcategory"],
                    channel=variant["channel"],
                    valid_from=valid_from,
                    valid_until=valid_until,
                    plan_id=plan_id,
                    plan_name=plan_name,
                    extra_conditions=_build_variant_conditions(plan_name, variant["subcategory"]),
                )
                promotions.append(promo)
            continue

        title = f"{card.card_name} {plan_name} 指定通路回饋"
        body = f"{plan_name}方案 指定通路享{default_rate}%小樹點回饋"
        channel = "ONLINE" if default_category == "ONLINE" else "ALL"
        fallback_subcategory = infer_subcategory(title, body, default_category, SUBCATEGORY_SIGNALS)
        default_category, fallback_subcategory = apply_plan_subcategory_hint(
            plan_id,
            default_category,
            fallback_subcategory,
            title=title,
            body=body,
        )

        promo = _build_plan_promotion_with_conditions(
            card=card,
            title=title,
            body=body,
            rate=default_rate,
            category=default_category,
            subcategory=fallback_subcategory,
            channel=channel,
            valid_from=valid_from,
            valid_until=valid_until,
            plan_id=plan_id,
            plan_name=plan_name,
        )
        promotions.append(promo)

    return promotions


def _build_plan_promotion(
    *,
    card: CardRecord,
    title: str,
    body: str,
    rate: str,
    category: str,
    subcategory: str = "GENERAL",
    channel: str,
    valid_from: str,
    valid_until: str,
    plan_id: str | None,
    plan_name: str,
    extra_conditions: list[dict[str, str]] | None = None,
) -> Dict[str, object]:
    conditions = [
        {"type": "TEXT", "value": f"需切換至「{plan_name}」方案", "label": f"需切換至「{plan_name}」方案"}
    ]
    if extra_conditions:
        conditions.extend(extra_conditions)
    return {
        "title": title,
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
        "cashbackValue": rate,
        "minAmount": 0,
        "maxCashback": None,
        "frequencyLimit": "NONE",
        "requiresRegistration": False,
        "recommendationScope": "RECOMMENDABLE",
        "eligibilityType": infer_eligibility_type(card.card_name),
        "validFrom": valid_from,
        "validUntil": valid_until,
        "conditions": [{"type": "TEXT", "value": f"需切換至「{plan_name}」方案", "label": f"需切換至「{plan_name}」方案"}],
        "excludedConditions": [],
        "sourceUrl": card.detail_url,
        "summary": f"{title}；享{rate}%小樹點回饋；期間 {valid_from}~{valid_until}",
        "status": "ACTIVE",
        "planId": plan_id,
    }


def _build_plan_promotion_with_conditions(
    *,
    card: CardRecord,
    title: str,
    body: str,
    rate: str,
    category: str,
    subcategory: str = "GENERAL",
    channel: str,
    valid_from: str,
    valid_until: str,
    plan_id: str | None,
    plan_name: str,
    extra_conditions: list[dict[str, str]] | None = None,
) -> Dict[str, object]:
    conditions = [
        {"type": "TEXT", "value": f"需切換至「{plan_name}」方案", "label": f"需切換至「{plan_name}」方案"}
    ]
    if extra_conditions:
        conditions.extend(extra_conditions)

    return {
        "title": title,
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
        "cashbackValue": rate,
        "minAmount": 0,
        "maxCashback": None,
        "frequencyLimit": "NONE",
        "requiresRegistration": False,
        "recommendationScope": "RECOMMENDABLE",
        "eligibilityType": infer_eligibility_type(card.card_name),
        "validFrom": valid_from,
        "validUntil": valid_until,
        "conditions": conditions,
        "excludedConditions": [],
        "sourceUrl": card.detail_url,
        "summary": f"{title}；{rate}% 小樹點回饋；期間 {valid_from}~{valid_until}",
        "status": "ACTIVE",
        "planId": plan_id,
    }


def _build_variant_conditions(plan_name: str, subcategory: str) -> list[dict[str, str]]:
    return [dict(condition) for condition in CUBE_VARIANT_CONDITIONS.get((plan_name, subcategory), [])]


def _apply_card_specific_reward_override(
    card_code: str,
    title: str,
    reward: dict[str, object] | None,
) -> dict[str, object] | None:
    if card_code != "CATHAY_FORMOSA":
        return reward

    config = FORMOSA_PROMO_DEFAULTS.get(title)
    if not config:
        return reward
    return dict(config["reward"])


def _apply_card_specific_validity_override(
    card_code: str,
    title: str,
    valid_from: str | None,
    valid_until: str | None,
) -> tuple[str | None, str | None]:
    if card_code != "CATHAY_FORMOSA":
        return valid_from, valid_until

    config = FORMOSA_PROMO_DEFAULTS.get(title)
    if not config:
        return valid_from, valid_until
    return str(config["valid_from"]), str(config["valid_until"])


def _apply_card_specific_overrides(
    card_code: str,
    title: str,
    body: str,
    category: str,
    subcategory: str,
    channel: str,
    recommendation_scope: str,
    conditions: list[dict[str, str]],
) -> tuple[str, str, str, str, list[dict[str, str]]]:
    merged_conditions = [dict(condition) for condition in conditions]

    if card_code == "CATHAY_FORMOSA":
        config = FORMOSA_PROMO_DEFAULTS.get(title)
        if config:
            merged_conditions = [
                condition
                for condition in merged_conditions
                if str(condition.get("type", "")).upper() not in {"PAYMENT_METHOD", "PAYMENT_PLATFORM"}
            ]
            merged_conditions = _merge_conditions(
                merged_conditions,
                config.get("conditions", ()),
            )
            return (
                str(config["category"]),
                str(config["subcategory"]),
                str(config["channel"]),
                str(config["recommendation_scope"]),
                merged_conditions,
            )

    if card_code == "CATHAY_CASH_REBATE_SIGNATURE" and any(token in title for token in ("新戶", "首刷", "本活動已結束")):
        merged_conditions = [
            condition
            for condition in merged_conditions
            if str(condition.get("type", "")).upper() not in {"MERCHANT", "RETAIL_CHAIN", "ECOMMERCE_PLATFORM", "PAYMENT_METHOD", "PAYMENT_PLATFORM"}
        ]
        return ("OTHER", "GENERAL", "ALL", recommendation_scope, merged_conditions)

    if card_code == "CATHAY_EVA" and "倍速哩遇" in title:
        return ("OVERSEAS", "GENERAL", "ALL", "CATALOG_ONLY", merged_conditions)

    return category, subcategory, channel, recommendation_scope, merged_conditions


def _merge_conditions(
    base_conditions: list[dict[str, str]],
    extra_conditions: Iterable[dict[str, str]],
) -> list[dict[str, str]]:
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


def _normalize_date(date_str: str) -> str | None:
    """Convert '2026/1/1' to '2026-01-01'."""
    match = re.match(r"(\d{4})/(\d{1,2})/(\d{1,2})", date_str)
    if not match:
        return None
    return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"


def _fetch_json(url: str) -> Dict[str, Any]:
    return json.loads(ingest.fetch_real_page(url))


def _iter_components(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, dict):
        if ":type" in value:
            yield value
        for child in value.values():
            yield from _iter_components(child)
        return
    if isinstance(value, list):
        for child in value:
            yield from _iter_components(child)


def _component_type(component: Dict[str, Any]) -> str:
    return str(component.get(":type") or "").lower()


def _extract_detail_card_name(components: Iterable[Dict[str, Any]]) -> str:
    for component in components:
        for key in ("creditCardName", "cardName", "mainTitle"):
            value = collapse_text(str(component.get(key) or ""))
            if value and ("信用卡" in value or value.endswith("卡")):
                return value
    return ""


def _pick_annual_fee_summary(lines: Iterable[str]) -> str | None:
    for line in lines:
        if "年費" in line or "首年免年費" in line:
            return line[:200]
    return None


def _extract_application_requirements(lines: Iterable[str]) -> List[str]:
    tokens = ("年滿", "財力證明", "正卡", "附卡", "申辦", "限申請")
    results: List[str] = []
    for line in lines:
        if any(token in line for token in tokens):
            results.append(line[:120])
    return list(dict.fromkeys(results))


def _extract_component_candidates(component: Dict[str, Any]) -> List[Dict[str, str]]:
    candidates: List[Dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def walk(value: Any, title_stack: List[str]) -> None:
        if isinstance(value, list):
            for item in value:
                walk(item, title_stack)
            return

        if not isinstance(value, dict):
            return

        current_title = _primary_title(value)
        next_titles = title_stack
        if current_title and (not title_stack or current_title != title_stack[-1]):
            next_titles = [*title_stack, current_title]

        body = _compose_body(value)
        if current_title and body and _looks_like_promotion(current_title, body):
            title = current_title if len(next_titles) == 1 else " ".join(next_titles[-2:])
            dedupe_key = (title, body)
            if dedupe_key not in seen:
                seen.add(dedupe_key)
                candidates.append({"title": title, "body": body})

        for child_key, child_value in value.items():
            if child_key.startswith(":") or child_key in {
                "title",
                "mainTitle",
                "cardName",
                "creditCardName",
                "tabText",
                "content",
                "description",
                "rate",
                "noticeText",
                "noticeContent",
                "noticeContent1",
                "noticeContent2",
                "subTitle",
            }:
                continue
            walk(child_value, next_titles)

    walk(component, [])
    return candidates


def _primary_title(value: Dict[str, Any]) -> str:
    for key in ("title", "tabText", "mainTitle", "itemName", "cardName"):
        title = collapse_text(str(value.get(key) or ""))
        if title and title not in {"立即申辦", "注意事項", "了解更多"}:
            return title
    return ""


def _compose_body(value: Dict[str, Any]) -> str:
    body_parts: List[str] = []
    for key in ("subTitle", "content", "description", "rate", "noticeText", "noticeContent", "noticeContent1", "noticeContent2"):
        body_parts.extend(_collect_text_list(value.get(key)))
    return collapse_text(" • ".join(part for part in body_parts if part))


def _collect_text_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        results: List[str] = []
        for item in value:
            results.extend(_collect_text_list(item))
        return [item for item in results if item]
    if isinstance(value, dict):
        results: List[str] = []
        for key in ("text", "description", "content", "title", "noticeContent", "noticeText", "value"):
            results.extend(_collect_text_list(value.get(key)))
        return [item for item in results if item]

    text = str(value)
    if "<" in text and ">" in text:
        return html_to_lines(text)
    collapsed = collapse_text(text)
    return [collapsed] if collapsed else []


def _looks_like_promotion(title: str, body: str) -> bool:
    text = f"{title} {body}"
    if not DATE_PATTERN.search(text):
        return False
    return bool(PROMOTION_SIGNAL_PATTERN.search(text))


def _normalize_url(url: Any, base_url: str) -> str | None:
    if not url:
        return None
    normalized = urljoin(base_url, str(url).strip())
    return normalized.split("#", 1)[0]


def _model_url(detail_url: str) -> str:
    return f"{detail_url.rstrip('/')}.model.json"


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
