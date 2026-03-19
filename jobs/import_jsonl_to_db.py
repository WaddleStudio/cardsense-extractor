from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from extractor import db_store


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import normalized CardSense JSONL into SQLite")
    parser.add_argument("--input", default=os.getenv("CARDSENSE_INPUT_JSONL"), help="Input JSONL file path")
    parser.add_argument("--db", default=os.getenv("CARDSENSE_DB_PATH", os.path.join(project_root, "data", "cardsense.db")), help="SQLite database path")
    parser.add_argument("--run-id", default=os.getenv("CARDSENSE_RUN_ID"), help="Optional extract run ID")
    parser.add_argument("--source", default=os.getenv("CARDSENSE_IMPORT_SOURCE", "jsonl-import"), help="Run source label")
    return parser.parse_args()


def run(input_path: str, db_path: str, run_id: str | None, source: str) -> int:
    target = Path(input_path)
    if not target.exists():
        raise FileNotFoundError(f"Input JSONL not found: {target}")

    connection = db_store.initialize_database(db_path)
    promotions_loaded = 0
    failures = 0
    bank_code = None
    extractor_version = "unknown"
    reset_current_bank = False

    created_run_id = db_store.create_extract_run(
        connection,
        bank_code=None,
        source=source,
        extractor_version=extractor_version,
        input_file=str(target),
        output_file=None,
        run_id=run_id,
    )

    try:
        with target.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                    bank_code = bank_code or payload.get("bankCode")
                    extractor_version = payload.get("extractorVersion", extractor_version)
                    if bank_code and not reset_current_bank:
                        db_store.delete_current_promotions_for_bank(connection, bank_code)
                        reset_current_bank = True
                    db_store.upsert_promotion(connection, payload, created_run_id)
                    promotions_loaded += 1
                except Exception as error:
                    failures += 1
                    print(f">>> Import failed at line {line_number}: {error}")

        db_store.finalize_extract_run(
            connection,
            run_id=created_run_id,
            status="SUCCESS" if failures == 0 else "PARTIAL_SUCCESS",
            cards_processed=0,
            promotions_loaded=promotions_loaded,
            failures=failures,
            notes=f"Imported from {target.name}",
        )
    finally:
        connection.close()

    print(f">>> SQLite DB: {db_path}")
    print(f">>> Extract run ID: {created_run_id}")
    print(f">>> Promotions imported: {promotions_loaded}")
    print(f">>> Import failures: {failures}")
    return 0 if promotions_loaded > 0 and failures == 0 else 1 if promotions_loaded == 0 else 0


if __name__ == "__main__":
    arguments = parse_args()
    if not arguments.input:
        raise SystemExit("Missing --input or CARDSENSE_INPUT_JSONL")
    raise SystemExit(run(arguments.input, arguments.db, arguments.run_id, arguments.source))