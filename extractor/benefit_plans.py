from __future__ import annotations

from typing import Final


# cardCode -> { category -> planId }  (fallback when title has no plan-name signal)
PLAN_MAPPING: Final[dict[str, dict[str, str]]] = {
    "CATHAY_CUBE": {
        "ONLINE": "CATHAY_CUBE_DIGITAL",
        "ENTERTAINMENT": "CATHAY_CUBE_DIGITAL",
        "SHOPPING": "CATHAY_CUBE_SHOPPING",
        "GROCERY": "CATHAY_CUBE_SHOPPING",
        "OVERSEAS": "CATHAY_CUBE_TRAVEL",
        "TRANSPORT": "CATHAY_CUBE_TRAVEL",
        "DINING": "CATHAY_CUBE_ESSENTIALS",
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

# cardCode -> [(keyword_in_title, planId)]  — matched first, before category fallback.
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

PLAN_SUBCATEGORY_HINTS: Final[dict[str, tuple[str, str]]] = {
    "CATHAY_CUBE_DIGITAL": ("ONLINE", "MOBILE_PAY"),
    "TAISHIN_RICHART_PAY": ("ONLINE", "MOBILE_PAY"),
    "TAISHIN_RICHART_DINING": ("DINING", "RESTAURANT"),
    "TAISHIN_RICHART_DIGITAL": ("ENTERTAINMENT", "STREAMING"),
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

    # 1. Match plan name keywords in the title (most accurate).
    if title:
        signals = PLAN_NAME_SIGNALS.get(code)
        if signals:
            for keyword, plan_id in signals:
                if keyword in title:
                    return plan_id

    # 2. Use a known subcategory hint when available.
    if subcategory:
        normalized_subcategory = subcategory.upper()
        for plan_id, (_, hinted_subcategory) in PLAN_SUBCATEGORY_HINTS.items():
            if plan_id.startswith(code) and hinted_subcategory == normalized_subcategory:
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
) -> tuple[str | None, str | None]:
    if not plan_id:
        return category, subcategory

    hint = PLAN_SUBCATEGORY_HINTS.get(plan_id.upper())
    if not hint:
        return category, subcategory

    hinted_category, hinted_subcategory = hint
    resolved_category = category or hinted_category
    resolved_subcategory = subcategory
    if not resolved_subcategory or resolved_subcategory.upper() == "GENERAL":
        resolved_subcategory = hinted_subcategory

    return resolved_category, resolved_subcategory
