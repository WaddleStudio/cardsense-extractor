import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Dict


EXTRACTOR_VERSION = "extractor-0.4.0"


def assign_version_ids(data: Dict[str, Any], raw_text: str) -> Dict[str, Any]:
    """Assign stable promo and version identifiers using the current spec fields."""
    versioned = data.copy()

    raw_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    versioned["rawTextHash"] = raw_hash

    logical_key = {
        "bankCode": versioned.get("bankCode"),
        "cardCode": versioned.get("cardCode"),
        "category": versioned.get("category"),
        "validFrom": versioned.get("validFrom"),
        "title": versioned.get("title"),
    }
    versioned["promoId"] = _hash_dict(logical_key, algorithm="md5")

    versioned["extractorVersion"] = EXTRACTOR_VERSION
    versioned["extractedAt"] = datetime.now(UTC).isoformat()
    versioned["confidence"] = _estimate_confidence(versioned)

    semantic_payload = {
        key: value
        for key, value in versioned.items()
        if key not in {"promoVersionId", "extractedAt", "confidence"}
    }
    versioned["promoVersionId"] = _hash_dict(semantic_payload, algorithm="sha256")

    return versioned


def _hash_dict(value: Dict[str, Any], algorithm: str) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if algorithm == "md5":
        return hashlib.md5(encoded).hexdigest()
    return hashlib.sha256(encoded).hexdigest()


def _estimate_confidence(payload: Dict[str, Any]) -> float:
    required_signals = [
        payload.get("bankCode"),
        payload.get("cardCode"),
        payload.get("category"),
        payload.get("cashbackType"),
        payload.get("cashbackValue"),
        payload.get("validFrom"),
        payload.get("validUntil"),
        payload.get("sourceUrl"),
    ]
    present = sum(1 for signal in required_signals if signal not in (None, "", []))
    return round(0.5 + (present / len(required_signals)) * 0.5, 2)
