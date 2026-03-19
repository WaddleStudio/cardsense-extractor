from typing import Any, Dict, List


CATEGORY_ALIASES = {
    "DINING": "DINING",
    "TRAVEL": "OTHER",
    "ONLINE": "ONLINE",
    "ONLINE_SHOPPING": "ONLINE",
    "GROCERIES": "GROCERY",
    "GROCERY": "GROCERY",
    "ENTERTAINMENT": "ENTERTAINMENT",
    "OVERSEAS": "OVERSEAS",
    "SHOPPING": "SHOPPING",
    "TRANSPORT": "TRANSPORT",
    "OTHER": "OTHER",
}

CHANNEL_ALIASES = {
    "ONLINE": "ONLINE",
    "OFFLINE": "OFFLINE",
    "ALL": "ALL",
}

CASHBACK_TYPE_ALIASES = {
    "PERCENT": "PERCENT",
    "CASHBACK": "PERCENT",
    "FIXED": "FIXED",
    "POINTS": "POINTS",
}

FREQUENCY_LIMIT_ALIASES = {
    "MONTHLY": "MONTHLY",
    "QUARTERLY": "QUARTERLY",
    "YEARLY": "YEARLY",
    "ONCE": "ONCE",
    "NONE": "NONE",
}


def normalize_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize parsed data to the current CardSense promotion shape."""
    normalized = {
        "bankCode": _normalize_string(data.get("bank")),
        "bankName": _normalize_string(data.get("bank_name")),
        "cardCode": _normalize_string(data.get("card_code")),
        "cardName": _normalize_string(data.get("card_name")),
        "category": _normalize_enum(data.get("category"), CATEGORY_ALIASES, default="OTHER"),
        "channel": _normalize_enum(data.get("channel"), CHANNEL_ALIASES, default=None),
        "cashbackType": _normalize_enum(data.get("cashback_type"), CASHBACK_TYPE_ALIASES, default=None),
        "cashbackValue": _normalize_decimal(data.get("cashback_value")),
        "minAmount": _normalize_int(data.get("min_amount"), default=0),
        "maxCashback": _normalize_nullable_int(data.get("max_cashback")),
        "frequencyLimit": _normalize_enum(data.get("frequency_limit"), FREQUENCY_LIMIT_ALIASES, default="NONE"),
        "requiresRegistration": _normalize_bool(data.get("requires_registration"), default=False),
        "validFrom": _normalize_string(data.get("valid_from")),
        "validUntil": _normalize_string(data.get("valid_until")),
        "conditions": _normalize_conditions(_split_list_field(data.get("conditions"))),
        "excludedConditions": _normalize_excluded_conditions(_split_list_field(data.get("excluded_conditions"))),
        "sourceUrl": _normalize_string(data.get("source_url")),
        "applyUrl": _normalize_string(data.get("apply_url")),
        "summary": _normalize_string(data.get("summary") or data.get("promotion")),
        "title": _normalize_string(data.get("promotion")),
        "status": _normalize_string(data.get("status") or "ACTIVE"),
        "cardStatus": _normalize_string(data.get("status") or "ACTIVE"),
        "annualFee": _normalize_int(data.get("annual_fee"), default=0),
    }

    if normalized["channel"] is None:
        normalized["channel"] = _infer_channel(normalized["category"], normalized["conditions"])

    return normalized


def _normalize_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_enum(value: Any, aliases: Dict[str, str], default: str | None) -> str | None:
    text = _normalize_string(value)
    if text is None:
        return default
    return aliases.get(text.upper(), default)


def _normalize_int(value: Any, default: int) -> int:
    text = _normalize_string(value)
    if text is None:
        return default
    return int(text)


def _normalize_nullable_int(value: Any) -> int | None:
    text = _normalize_string(value)
    if text is None:
        return None
    return int(text)


def _normalize_decimal(value: Any) -> float | None:
    text = _normalize_string(value)
    if text is None:
        return None
    return float(text)


def _normalize_bool(value: Any, default: bool) -> bool:
    text = _normalize_string(value)
    if text is None:
        return default
    return text.lower() in {"true", "1", "yes", "y"}


def _split_list_field(value: Any) -> List[str]:
    text = _normalize_string(value)
    if text is None:
        return []
    return [item.strip() for item in text.split(";") if item.strip()]


def _infer_channel(category: str | None, conditions: List[Dict[str, str]]) -> str:
    if category == "ONLINE":
        return "ONLINE"
    if any("外幣" in condition.get("label", "") or "海外" in condition.get("label", "") for condition in conditions):
        return "ONLINE"
    return "ALL"


def _normalize_conditions(values: List[str]) -> List[Dict[str, str]]:
    conditions: List[Dict[str, str]] = []
    for value in values:
        if value.startswith("LOCATION_ONLY:"):
            location = value.split(":", 1)[1].strip().upper()
            conditions.append({"type": "LOCATION_ONLY", "value": location, "label": f"限 {location} 適用"})
            continue

        conditions.append({"type": "TEXT", "value": value.upper().replace(" ", "_"), "label": value})

    return conditions


def _normalize_excluded_conditions(values: List[str]) -> List[Dict[str, str]]:
    conditions: List[Dict[str, str]] = []
    for value in values:
        if value.startswith("LOCATION:"):
            location = value.split(":", 1)[1].strip().upper()
            conditions.append({"type": "LOCATION_EXCLUDE", "value": location, "label": f"排除 {location}"})
            continue
        if value.startswith("CATEGORY:"):
            category = value.split(":", 1)[1].strip().upper()
            conditions.append({"type": "CATEGORY_EXCLUDE", "value": category, "label": f"排除 {category}"})
            continue

        conditions.append({"type": "TEXT", "value": value.upper().replace(" ", "_"), "label": value})

    return conditions
