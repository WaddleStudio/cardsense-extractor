from __future__ import annotations

from typing import Final

from extractor.promotion_rules import SUBCATEGORY_SIGNALS, score_signals


# cardCode -> { category -> planId }
# Fallback when the promotion title does not contain a plan-name keyword.
PLAN_MAPPING: Final[dict[str, dict[str, str]]] = {
    "CATHAY_CUBE": {
        "ONLINE": "CATHAY_CUBE_DIGITAL",
        "ENTERTAINMENT": "CATHAY_CUBE_DIGITAL",
        "SHOPPING": "CATHAY_CUBE_SHOPPING",
        "DINING": "CATHAY_CUBE_SHOPPING",
        "OVERSEAS": "CATHAY_CUBE_TRAVEL",
        "TRANSPORT": "CATHAY_CUBE_TRAVEL",
        "GROCERY": "CATHAY_CUBE_ESSENTIALS",
        "OTHER": "CATHAY_CUBE_ESSENTIALS",
    },
    "ESUN_UNICARD": {
        "ONLINE": "ESUN_UNICARD_FLEXIBLE",
        "ENTERTAINMENT": "ESUN_UNICARD_FLEXIBLE",
        "DINING": "ESUN_UNICARD_SIMPLE",
        "GROCERY": "ESUN_UNICARD_SIMPLE",
        "OVERSEAS": "ESUN_UNICARD_SIMPLE",
        "TRANSPORT": "ESUN_UNICARD_SIMPLE",
        "SHOPPING": "ESUN_UNICARD_SIMPLE",
        "OTHER": "ESUN_UNICARD_SIMPLE",
    },
    "TAISHIN_RICHART": {
        "ONLINE": "TAISHIN_RICHART_DIGITAL",
        "ENTERTAINMENT": "TAISHIN_RICHART_DIGITAL",
        "DINING": "TAISHIN_RICHART_DINING",
        "OVERSEAS": "TAISHIN_RICHART_TRAVEL",
        "TRANSPORT": "TAISHIN_RICHART_TRAVEL",
        "SHOPPING": "TAISHIN_RICHART_DAILY",
        "GROCERY": "TAISHIN_RICHART_DAILY",
        "OTHER": "TAISHIN_RICHART_DAILY",
    },
}

# cardCode -> [(keyword_in_title, planId)]
# Title keywords are matched before category fallback.
# Order matters: more specific keywords should come before generic ones.
PLAN_NAME_SIGNALS: Final[dict[str, list[tuple[str, str]]]] = {
    "CATHAY_CUBE": [
        ("慶生月", "CATHAY_CUBE_BIRTHDAY"),
        ("童樂匯", "CATHAY_CUBE_KIDS"),
        ("日本賞", "CATHAY_CUBE_JAPAN"),
        ("玩數位", "CATHAY_CUBE_DIGITAL"),
        ("樂饗購", "CATHAY_CUBE_SHOPPING"),
        ("趣旅行", "CATHAY_CUBE_TRAVEL"),
        ("集精選", "CATHAY_CUBE_ESSENTIALS"),
    ],
    "TAISHIN_RICHART": [
        ("Pay著刷", "TAISHIN_RICHART_PAY"),
        ("天天刷", "TAISHIN_RICHART_DAILY"),
        ("大筆刷", "TAISHIN_RICHART_BIG"),
        ("好饗刷", "TAISHIN_RICHART_DINING"),
        ("數趣刷", "TAISHIN_RICHART_DIGITAL"),
        ("玩旅刷", "TAISHIN_RICHART_TRAVEL"),
        ("假日刷", "TAISHIN_RICHART_WEEKEND"),
    ],
    "ESUN_UNICARD": [
        ("UP選", "ESUN_UNICARD_UP"),
        ("簡單選", "ESUN_UNICARD_SIMPLE"),
        ("任意選", "ESUN_UNICARD_FLEXIBLE"),
    ],
}

PLAN_SUBCATEGORY_HINTS: Final[dict[str, dict[str, str]]] = {
    "CATHAY_CUBE_DIGITAL": {
        "ONLINE": "ECOMMERCE",
        "ENTERTAINMENT": "STREAMING",
    },
    "CATHAY_CUBE_SHOPPING": {
        "DINING": "RESTAURANT",
        "SHOPPING": "DEPARTMENT",
    },
    "CATHAY_CUBE_TRAVEL": {
        "TRANSPORT": "RIDESHARE",
        "OVERSEAS": "OVERSEAS_IN_STORE",
    },
    "CATHAY_CUBE_ESSENTIALS": {
        "GROCERY": "SUPERMARKET",
        "OTHER": "EV_CHARGING",
    },
    "CATHAY_CUBE_BIRTHDAY": {
        "DINING": "RESTAURANT",
        "SHOPPING": "DEPARTMENT",
    },
    "TAISHIN_RICHART_PAY": {
        "ONLINE": "MOBILE_PAY",
    },
    "TAISHIN_RICHART_DAILY": {
        "GROCERY": "SUPERMARKET",
    },
    "TAISHIN_RICHART_BIG": {
        "SHOPPING": "DEPARTMENT",
    },
    "TAISHIN_RICHART_DINING": {
        "DINING": "RESTAURANT",
    },
    "TAISHIN_RICHART_DIGITAL": {
        "ONLINE": "ECOMMERCE",
        "ENTERTAINMENT": "STREAMING",
    },
    "TAISHIN_RICHART_TRAVEL": {
        "ONLINE": "TRAVEL_PLATFORM",
        "OVERSEAS": "OVERSEAS_IN_STORE",
    },
    "ESUN_UNICARD_FLEXIBLE": {
        "ONLINE": "MOBILE_PAY",
        "ENTERTAINMENT": "STREAMING",
    },
    "ESUN_UNICARD_SIMPLE": {
        "DINING": "RESTAURANT",
        "GROCERY": "SUPERMARKET",
        "SHOPPING": "DEPARTMENT",
    },
    "ESUN_UNICARD_UP": {
        "DINING": "RESTAURANT",
        "GROCERY": "SUPERMARKET",
        "SHOPPING": "DEPARTMENT",
    },
}


def infer_plan_id(
    card_code: str | None,
    category: str | None,
    title: str | None = None,
    subcategory: str | None = None,
) -> str | None:
    if not card_code:
        return None

    code = card_code.upper()

    # 1. Match plan-name keywords in title first.
    if title:
        signals = PLAN_NAME_SIGNALS.get(code)
        if signals:
            for keyword, plan_id in signals:
                if keyword in title:
                    return plan_id

    # 2. Use known subcategory hints when available.
    if subcategory:
        normalized_subcategory = subcategory.upper()
        for plan_id, category_hints in PLAN_SUBCATEGORY_HINTS.items():
            if plan_id.startswith(code) and normalized_subcategory in category_hints.values():
                return plan_id

    # 3. Fall back to category-based mapping.
    if not category:
        return None

    category_map = PLAN_MAPPING.get(code)
    if not category_map:
        return None

    return category_map.get(category.upper())


def apply_plan_subcategory_hint(
    plan_id: str | None,
    category: str | None,
    subcategory: str | None,
    *,
    title: str | None = None,
    body: str | None = None,
) -> tuple[str | None, str | None]:
    if not plan_id:
        return category, subcategory

    category_hints = PLAN_SUBCATEGORY_HINTS.get(plan_id.upper())
    if not category_hints:
        return category, subcategory

    resolved_category = category
    if resolved_category is None and len(category_hints) == 1:
        resolved_category = next(iter(category_hints))

    resolved_subcategory = subcategory
    if resolved_category:
        hinted_subcategory = category_hints.get(resolved_category.upper())
        if hinted_subcategory and (not resolved_subcategory or resolved_subcategory.upper() == "GENERAL"):
            evidence_text = (title or "").strip()
            if not evidence_text:
                return resolved_category, resolved_subcategory

            hint_signals = (
                SUBCATEGORY_SIGNALS
                .get(resolved_category.upper(), {})
                .get(hinted_subcategory.upper(), [])
            )
            if score_signals(evidence_text, hint_signals) < 3:
                return resolved_category, resolved_subcategory
            resolved_subcategory = hinted_subcategory

    return resolved_category, resolved_subcategory
