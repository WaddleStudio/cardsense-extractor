from typing import Any, Dict


def parse_promotion(raw_text: str) -> Dict[str, Any]:
    """Parse mock key-value raw text into a loosely structured promotion payload."""
    extracted: Dict[str, Any] = {"raw_text": raw_text}

    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped or ":" not in stripped:
            continue

        key, value = stripped.split(":", 1)
        extracted[_normalize_key(key)] = value.strip()

    if "promotion" in extracted and "summary" not in extracted:
        extracted["summary"] = extracted["promotion"]

    return extracted


def _normalize_key(key: str) -> str:
    return key.strip().lower().replace(" ", "_")
