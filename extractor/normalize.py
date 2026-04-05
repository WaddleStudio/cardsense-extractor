import re
from typing import Any, Dict, List

from extractor.benefit_plans import apply_plan_subcategory_hint, infer_plan_id


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

_PROFESSION_KEYWORDS = (
    "醫師",
    "醫護",
    "藥師",
    "教師",
    "軍警",
    "公教",
    "律師",
    "會計師",
    "醫事",
)

_BUSINESS_KEYWORDS = (
    "商務",
    "公司卡",
    "採購卡",
    "企業",
)

_CARD_NAME_STATUS_SUFFIX_PATTERNS = (
    re.compile(r"\s*-\s*.+銀行\s*$"),
    re.compile(r"\s*[|｜].+$"),
    re.compile(r"\s*[，,]\s*已停發.*$"),
    re.compile(r"\s*《[^》]*(?:停止申辦|停止發行)[^》]*》\s*$"),
    re.compile(r"\s*[（(][^）)]*停發[^）)]*[）)]\s*$"),
    re.compile(r"\s+卡友必備APP.*$"),
)

_CARD_NAME_CORE_PATTERN = re.compile(
    r"^(.{2,80}?(?:"
    r"簽帳金融卡|信用卡|聯名卡|認同卡|御璽卡|鈦金卡|白金卡|無限卡|世界卡|晶緻卡|"
    r"商務卡|金融卡|悠遊卡|Debit卡|Unicard|UniCard|Only卡|卡"
    r"))(?=\s|$|[，,（(《【])"
)


def clean_card_name(raw_name: str | None) -> str | None:
    """Strip promotional text, bank suffixes, and issuance-status suffixes."""
    if not raw_name:
        return raw_name

    name = raw_name.strip()

    for pattern in _CARD_NAME_STATUS_SUFFIX_PATTERNS:
        name = pattern.sub("", name).strip()

    match = _CARD_NAME_CORE_PATTERN.match(name)
    if match:
        name = match.group(1).strip()

    if len(name) < 3:
        return raw_name.strip()

    return name


def _clean_card_name(raw_name: str | None) -> str | None:
    return clean_card_name(raw_name)


def infer_eligibility_type(card_name: str | None) -> str:
    if not card_name:
        return "GENERAL"
    for kw in _PROFESSION_KEYWORDS:
        if kw in card_name:
            return "PROFESSION_SPECIFIC"
    for kw in _BUSINESS_KEYWORDS:
        if kw in card_name:
            return "BUSINESS"
    return "GENERAL"


def normalize_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize parsed data to the current CardSense promotion shape."""
    card_code = _normalize_string(data.get("card_code"))
    category = _normalize_enum(data.get("category"), CATEGORY_ALIASES, default="OTHER")
    explicit_plan_id = _normalize_string(data.get("plan_id"))
    title_text = _normalize_string(data.get("promotion")) or _normalize_string(data.get("summary"))
    subcategory = _normalize_string(data.get("subcategory")) or "GENERAL"
    plan_id = explicit_plan_id or infer_plan_id(card_code, category, title=title_text, subcategory=subcategory)
    category, subcategory = apply_plan_subcategory_hint(plan_id, category, subcategory)

    normalized = {
        "bankCode": _normalize_string(data.get("bank")),
        "bankName": _normalize_string(data.get("bank_name")),
        "cardCode": card_code,
        "cardName": clean_card_name(_normalize_string(data.get("card_name"))),
        "category": category,
        "subcategory": subcategory,
        "channel": _normalize_enum(data.get("channel"), CHANNEL_ALIASES, default=None),
        "cashbackType": _normalize_enum(data.get("cashback_type"), CASHBACK_TYPE_ALIASES, default=None),
        "cashbackValue": _normalize_decimal(data.get("cashback_value")),
        "minAmount": _normalize_int(data.get("min_amount"), default=0),
        "maxCashback": _normalize_nullable_int(data.get("max_cashback")),
        "frequencyLimit": _normalize_enum(data.get("frequency_limit"), FREQUENCY_LIMIT_ALIASES, default="NONE"),
        "requiresRegistration": _normalize_bool(data.get("requires_registration"), default=False),
        "recommendationScope": _normalize_string(data.get("recommendation_scope")) or "RECOMMENDABLE",
        "eligibilityType": infer_eligibility_type(_normalize_string(data.get("card_name"))),
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
        "planId": plan_id,
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
    if any("憭馳" in condition.get("label", "") or "瘚瑕?" in condition.get("label", "") for condition in conditions):
        return "ONLINE"
    return "ALL"


def _normalize_conditions(values: List[str]) -> List[Dict[str, str]]:
    conditions: List[Dict[str, str]] = []
    for value in values:
        if value.startswith("LOCATION_ONLY:"):
            location = value.split(":", 1)[1].strip().upper()
            conditions.append({"type": "LOCATION_ONLY", "value": location, "label": f"??{location} ?拍"})
            continue

        conditions.append({"type": "TEXT", "value": value.upper().replace(" ", "_"), "label": value})

    return conditions


def _normalize_excluded_conditions(values: List[str]) -> List[Dict[str, str]]:
    conditions: List[Dict[str, str]] = []
    for value in values:
        if value.startswith("LOCATION:"):
            location = value.split(":", 1)[1].strip().upper()
            conditions.append({"type": "LOCATION_EXCLUDE", "value": location, "label": f"? {location}"})
            continue
        if value.startswith("CATEGORY:"):
            category = value.split(":", 1)[1].strip().upper()
            conditions.append({"type": "CATEGORY_EXCLUDE", "value": category, "label": f"? {category}"})
            continue

        conditions.append({"type": "TEXT", "value": value.upper().replace(" ", "_"), "label": value})

    return conditions
