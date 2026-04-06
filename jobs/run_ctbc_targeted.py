"""Run CTBC extraction for a specific set of cards by URL slug.

Usage:
    # Default target slugs (8 cards):
    uv run python jobs/run_ctbc_targeted.py

    # Custom slugs via CLI args:
    uv run python jobs/run_ctbc_targeted.py B_Cashback_Signature B_SLV

    # Custom slugs via env var (comma-separated):
    CTBC_TARGET_SLUGS=B_Cashback_Signature,B_SLV uv run python jobs/run_ctbc_targeted.py
"""
import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

from extractor.ctbc_real import CardRecord, extract_card_promotions, list_ctbc_cards, _build_card_code

DEFAULT_TARGET_SLUGS = [
    "B_Cashback_Signature",
    "B_Cashback_Titanium",
    "B_SLV",
    "B_IR",
    "C_SHOWTIME",
    "C_TSDreamMall",
    "C_XUEXUE",
    "C_Globalmall",
]


def _resolve_slugs() -> list[str]:
    """Resolve target slugs from CLI args, env var, or defaults."""
    if len(sys.argv) > 1:
        return sys.argv[1:]
    env_slugs = os.getenv("CTBC_TARGET_SLUGS", "")
    if env_slugs.strip():
        return [s.strip() for s in env_slugs.split(",") if s.strip()]
    return DEFAULT_TARGET_SLUGS


def list_targeted_cards(slugs: list[str] | None = None) -> list[CardRecord]:
    """Return only cards matching the given slugs (or defaults)."""
    target_slugs = slugs or DEFAULT_TARGET_SLUGS
    all_cards = list_ctbc_cards()
    target_codes = {_build_card_code(slug) for slug in target_slugs}
    return [c for c in all_cards if c.card_code in target_codes]


if __name__ == "__main__":
    from jobs.run_real_bank_job import run_real_bank_job

    slugs = _resolve_slugs()
    code = run_real_bank_job(
        bank_label="CTBC-targeted",
        output_prefix="ctbc-targeted",
        list_cards=lambda: list_targeted_cards(slugs),
        extract_card_promotions=extract_card_promotions,
    )
    raise SystemExit(code)
