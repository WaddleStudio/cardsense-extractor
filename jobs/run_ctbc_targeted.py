"""Run CTBC extraction for a specific set of cards by URL slug."""
import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

from extractor.ctbc_real import CardRecord, extract_card_promotions, list_ctbc_cards, _build_card_code

TARGET_SLUGS = [
    "B_Cashback_Signature",
    "B_Cashback_Titanium",
    "B_SLV",
    "B_IR",
    "C_SHOWTIME",
    "C_TSDreamMall",
    "C_XUEXUE",
    "C_Globalmall",
]


def list_targeted_cards() -> list[CardRecord]:
    """Return only cards matching TARGET_SLUGS."""
    all_cards = list_ctbc_cards()
    target_codes = {_build_card_code(slug) for slug in TARGET_SLUGS}
    return [c for c in all_cards if c.card_code in target_codes]


if __name__ == "__main__":
    from jobs.run_real_bank_job import run_real_bank_job

    code = run_real_bank_job(
        bank_label="CTBC-targeted",
        output_prefix="ctbc-targeted",
        list_cards=list_targeted_cards,
        extract_card_promotions=extract_card_promotions,
    )
    raise SystemExit(code)
