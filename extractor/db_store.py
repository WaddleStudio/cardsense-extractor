from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCHEMA_PATH = Path(__file__).resolve().parent.parent / "sql" / "cardsense_schema.sql"


def initialize_database(db_path: str) -> sqlite3.Connection:
    target = Path(db_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target)
    connection.row_factory = sqlite3.Row
    with SCHEMA_PATH.open("r", encoding="utf-8") as handle:
        connection.executescript(handle.read())
    _ensure_column(connection, "promotion_versions", "title", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "promotion_current", "title", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "promotion_versions", "recommendation_scope", "TEXT NOT NULL DEFAULT 'RECOMMENDABLE'")
    _ensure_column(connection, "promotion_current", "recommendation_scope", "TEXT NOT NULL DEFAULT 'RECOMMENDABLE'")
    _ensure_column(connection, "promotion_versions", "eligibility_type", "TEXT NOT NULL DEFAULT 'GENERAL'")
    _ensure_column(connection, "promotion_current", "eligibility_type", "TEXT NOT NULL DEFAULT 'GENERAL'")
    return connection


def create_extract_run(
    connection: sqlite3.Connection,
    *,
    bank_code: str | None,
    source: str,
    extractor_version: str,
    input_file: str,
    output_file: str | None,
    notes: str | None = None,
    run_id: str | None = None,
) -> str:
    created_run_id = run_id or f"run_{uuid.uuid4().hex}"
    connection.execute(
        """
        INSERT INTO extract_runs (
            run_id, bank_code, source, extractor_version, started_at, status, input_file, output_file, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            created_run_id,
            bank_code,
            source,
            extractor_version,
            _now_iso(),
            "RUNNING",
            input_file,
            output_file,
            notes,
        ),
    )
    connection.commit()
    return created_run_id


def upsert_promotion(connection: sqlite3.Connection, payload: dict[str, Any], run_id: str) -> None:
    record = _build_db_record(payload, run_id)
    columns = list(record.keys())
    placeholders = ", ".join("?" for _ in columns)
    updates = ", ".join(f"{column}=excluded.{column}" for column in columns if column != "promo_version_id")

    connection.execute(
        f"""
        INSERT INTO promotion_versions ({", ".join(columns)})
        VALUES ({placeholders})
        ON CONFLICT(promo_version_id) DO UPDATE SET {updates}
        """,
        [record[column] for column in columns],
    )

    current_columns = [column for column in columns if column != "promo_version_id"]
    current_record = {column: record[column] for column in current_columns}
    current_record["promo_version_id"] = record["promo_version_id"]

    ordered_current_columns = [
        "promo_id",
        "promo_version_id",
        "title",
        "bank_code",
        "bank_name",
        "card_code",
        "card_name",
        "card_status",
        "annual_fee",
        "apply_url",
        "category",
        "channel",
        "cashback_type",
        "cashback_value",
        "min_amount",
        "max_cashback",
        "frequency_limit",
        "requires_registration",
        "recommendation_scope",
        "eligibility_type",
        "valid_from",
        "valid_until",
        "conditions_json",
        "excluded_conditions_json",
        "source_url",
        "raw_text_hash",
        "summary",
        "extractor_version",
        "extracted_at",
        "confidence",
        "status",
        "run_id",
        "raw_payload_json",
    ]
    current_placeholders = ", ".join("?" for _ in ordered_current_columns)
    current_updates = ", ".join(
        f"{column}=excluded.{column}" for column in ordered_current_columns if column != "promo_id"
    )
    connection.execute(
        f"""
        INSERT INTO promotion_current ({", ".join(ordered_current_columns)})
        VALUES ({current_placeholders})
        ON CONFLICT(promo_id) DO UPDATE SET {current_updates}
        """,
        [current_record[column] for column in ordered_current_columns],
    )


def finalize_extract_run(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    status: str,
    cards_processed: int,
    promotions_loaded: int,
    failures: int,
    notes: str | None = None,
) -> None:
    connection.execute(
        """
        UPDATE extract_runs
        SET finished_at = ?, status = ?, cards_processed = ?, promotions_loaded = ?, failures = ?, notes = COALESCE(?, notes)
        WHERE run_id = ?
        """,
        (_now_iso(), status, cards_processed, promotions_loaded, failures, notes, run_id),
    )
    connection.commit()


def delete_current_promotions_for_bank(connection: sqlite3.Connection, bank_code: str) -> None:
    connection.execute("DELETE FROM promotion_current WHERE bank_code = ?", (bank_code,))
    connection.commit()


def _build_db_record(payload: dict[str, Any], run_id: str) -> dict[str, Any]:
    return {
        "promo_version_id": payload["promoVersionId"],
        "promo_id": payload["promoId"],
        "title": payload["title"],
        "bank_code": payload["bankCode"],
        "bank_name": payload["bankName"],
        "card_code": payload["cardCode"],
        "card_name": payload["cardName"],
        "card_status": payload.get("cardStatus"),
        "annual_fee": payload.get("annualFee", 0),
        "apply_url": payload.get("applyUrl"),
        "category": payload["category"],
        "channel": payload.get("channel"),
        "cashback_type": payload["cashbackType"],
        "cashback_value": payload["cashbackValue"],
        "min_amount": payload.get("minAmount", 0),
        "max_cashback": payload.get("maxCashback"),
        "frequency_limit": payload.get("frequencyLimit"),
        "requires_registration": 1 if payload.get("requiresRegistration") else 0,
        "recommendation_scope": payload.get("recommendationScope", "RECOMMENDABLE"),
        "eligibility_type": payload.get("eligibilityType", "GENERAL"),
        "valid_from": payload["validFrom"],
        "valid_until": payload["validUntil"],
        "conditions_json": json.dumps(payload.get("conditions", []), ensure_ascii=False, separators=(",", ":")),
        "excluded_conditions_json": json.dumps(payload.get("excludedConditions", []), ensure_ascii=False, separators=(",", ":")),
        "source_url": payload["sourceUrl"],
        "raw_text_hash": payload["rawTextHash"],
        "summary": payload["summary"],
        "extractor_version": payload["extractorVersion"],
        "extracted_at": payload["extractedAt"],
        "confidence": payload["confidence"],
        "status": payload["status"],
        "run_id": run_id,
        "raw_payload_json": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
    }


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _ensure_column(connection: sqlite3.Connection, table_name: str, column_name: str, column_definition: str) -> None:
    columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()}
    if column_name not in columns:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")
        connection.commit()