import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from extractor.fubon_real import extract_card_promotions, list_fubon_cards
from jobs.run_real_bank_job import run_real_bank_job


def run(limit: int | None = None) -> int:
    return run_real_bank_job(
        bank_label="FUBON",
        output_prefix="fubon-real",
        list_cards=list_fubon_cards,
        extract_card_promotions=extract_card_promotions,
        limit=limit,
    )


if __name__ == "__main__":
    limit_value = os.getenv("FUBON_REAL_LIMIT")
    limit = int(limit_value) if limit_value else None
    raise SystemExit(run(limit=limit))
