from __future__ import annotations

from typing import Any


DISCONTINUED_TOKENS = (
    "停發",
    "已停發",
    "停卡",
    "已停卡",
    "停用",
    "已停用",
)

ACTIVE_CARD_STATUSES = {"ACTIVE", "ISSUED"}
DISCONTINUED_CARD_STATUSES = {"DISCONTINUED", "INACTIVE", "STOPPED"}


def is_discontinued_card_name(card_name: str | None) -> bool:
    if not card_name:
        return False
    return any(token in card_name for token in DISCONTINUED_TOKENS)


def normalize_card_status(*values: Any, card_name: str | None = None) -> str:
    if is_discontinued_card_name(card_name):
        return "DISCONTINUED"

    for value in values:
        if value is None:
            continue
        normalized = str(value).strip().upper()
        if not normalized:
            continue
        if normalized in ACTIVE_CARD_STATUSES:
            return "ACTIVE"
        if normalized in DISCONTINUED_CARD_STATUSES:
            return "DISCONTINUED"

    return "ACTIVE"


def normalize_promotion_status(*values: Any, card_name: str | None = None) -> str:
    if is_discontinued_card_name(card_name):
        return "INACTIVE"

    for value in values:
        if value is None:
            continue
        normalized = str(value).strip().upper()
        if not normalized:
            continue
        if normalized == "ACTIVE":
            return "ACTIVE"
        if normalized in {"INACTIVE", "DISCONTINUED", "STOPPED"}:
            return "INACTIVE"

    return "ACTIVE"