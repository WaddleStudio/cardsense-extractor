from __future__ import annotations

from copy import deepcopy
from typing import Iterable, List, Sequence, Tuple

from extractor.html_utils import collapse_text
from extractor.promotion_rules import (
    BANK_WIDE_PROMOTION_MARKER,
    BANK_WIDE_SOURCE_MARKER_PREFIX,
    BANK_WIDE_SUPPLEMENT_MARKER,
)


def apply_bank_wide_promotion_supplements(
    extracted_cards: Sequence[Tuple[object, List[dict[str, object]]]],
) -> tuple[list[tuple[object, list[dict[str, object]]]], int]:
    updated_cards: list[tuple[object, list[dict[str, object]]]] = [
        (card, [dict(promotion) for promotion in promotions])
        for card, promotions in extracted_cards
    ]
    supplement_count = 0

    for index, (target_card, target_promotions) in enumerate(updated_cards):
        target_name = str(getattr(target_card, "card_name", "") or "")
        target_code = str(getattr(target_card, "card_code", "") or "")
        target_bank = str(
            next((promotion.get("bankCode") for promotion in target_promotions if promotion.get("bankCode")), "")
        )
        if not _is_cobrand_card(target_name):
            continue

        existing_keys = {_promotion_equivalence_key(promotion, target_name) for promotion in target_promotions}

        for source_card, source_promotions in updated_cards:
            source_code = str(getattr(source_card, "card_code", "") or "")
            if source_code == target_code:
                continue
            for source_promotion in source_promotions:
                source_bank = str(source_promotion.get("bankCode", "") or "")
                if target_bank and source_bank != target_bank:
                    continue
                if not _is_bank_wide_candidate(source_promotion):
                    continue

                candidate = _clone_for_target_card(source_promotion, target_code, target_name)
                candidate_key = _promotion_equivalence_key(candidate, target_name)
                if candidate_key in existing_keys:
                    continue

                target_promotions.append(candidate)
                existing_keys.add(candidate_key)
                supplement_count += 1

        updated_cards[index] = (target_card, target_promotions)

    return updated_cards, supplement_count


def _is_cobrand_card(card_name: str) -> bool:
    normalized = collapse_text(card_name).upper()
    return "聯名" in normalized or "CO-BRAND" in normalized or "COBRAND" in normalized


def _is_bank_wide_candidate(promotion: dict[str, object]) -> bool:
    if str(promotion.get("recommendationScope", "")).upper() != "RECOMMENDABLE":
        return False
    if bool(promotion.get("requiresRegistration")):
        return False
    if promotion.get("planId"):
        return False
    if str(promotion.get("subcategory", "GENERAL")).upper() != "GENERAL":
        return False

    conditions = promotion.get("conditions") or []
    for condition in conditions:
        condition_type = str(condition.get("type", "")).upper()
        condition_value = str(condition.get("value", "")).upper()
        if condition_type in {"MERCHANT", "RETAIL_CHAIN", "ECOMMERCE_PLATFORM"}:
            return False
        if condition_type == "TEXT" and condition_value == BANK_WIDE_PROMOTION_MARKER:
            return True
    return False


def _clone_for_target_card(
    promotion: dict[str, object],
    target_card_code: str,
    target_card_name: str,
) -> dict[str, object]:
    cloned = deepcopy(promotion)
    source_card_code = str(promotion.get("cardCode", "") or "")
    source_card_name = str(promotion.get("cardName", "") or "")

    cloned["cardCode"] = target_card_code
    cloned["cardName"] = target_card_name
    cloned["title"] = _retitle_for_target_card(str(promotion.get("title", "") or ""), source_card_name, target_card_name)
    cloned["summary"] = _retitle_for_target_card(str(promotion.get("summary", "") or ""), source_card_name, target_card_name)
    cloned["conditions"] = _append_supplement_markers(cloned.get("conditions") or [], source_card_code)
    return cloned


def _append_supplement_markers(
    conditions: Iterable[dict[str, object]],
    source_card_code: str,
) -> list[dict[str, object]]:
    cloned_conditions = [dict(condition) for condition in conditions]
    markers = [
        {
            "type": "TEXT",
            "value": BANK_WIDE_SUPPLEMENT_MARKER,
            "label": "Supplemented from bank-wide promotion source",
        },
        {
            "type": "TEXT",
            "value": f"{BANK_WIDE_SOURCE_MARKER_PREFIX}{source_card_code}",
            "label": f"Bank-wide source card: {source_card_code}",
        },
    ]
    existing = {
        (str(condition.get("type", "")).upper(), str(condition.get("value", "")).upper())
        for condition in cloned_conditions
    }
    for marker in markers:
        key = (marker["type"].upper(), marker["value"].upper())
        if key in existing:
            continue
        cloned_conditions.append(marker)
        existing.add(key)
    return cloned_conditions


def _retitle_for_target_card(text: str, source_card_name: str, target_card_name: str) -> str:
    normalized = collapse_text(text)
    if not normalized:
        return target_card_name
    if source_card_name and normalized.startswith(source_card_name):
        return f"{target_card_name}{normalized[len(source_card_name):]}"
    return normalized.replace(source_card_name, target_card_name, 1) if source_card_name in normalized else normalized


def _promotion_equivalence_key(promotion: dict[str, object], target_card_name: str) -> tuple[object, ...]:
    normalized_title = _retitle_for_target_card(
        str(promotion.get("title", "") or ""),
        str(promotion.get("cardName", "") or ""),
        target_card_name,
    )
    return (
        normalized_title,
        promotion.get("category"),
        promotion.get("subcategory"),
        promotion.get("channel"),
        promotion.get("cashbackType"),
        promotion.get("cashbackValue"),
        promotion.get("minAmount"),
        promotion.get("maxCashback"),
        promotion.get("validFrom"),
        promotion.get("validUntil"),
        promotion.get("planId"),
    )
