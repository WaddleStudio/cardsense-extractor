from __future__ import annotations

from typing import Final


# cardCode -> { category -> planId }
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


def infer_plan_id(card_code: str | None, category: str | None) -> str | None:
    if not card_code or not category:
        return None

    category_map = PLAN_MAPPING.get(card_code.upper())
    if not category_map:
        return None

    return category_map.get(category.upper())