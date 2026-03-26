"""Sync all three SQLite tables to Supabase (PostgreSQL) via psycopg2."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

import psycopg2
import psycopg2.extras

# Column order must match supabase_schema.sql exactly.
_EXTRACT_RUN_COLS = (
    "run_id", "bank_code", "source", "extractor_version",
    "started_at", "finished_at", "status", "cards_processed",
    "promotions_loaded", "failures", "input_file", "output_file", "notes",
)

_PROMOTION_VERSION_COLS = (
    "promo_version_id", "promo_id", "title", "bank_code", "bank_name",
    "card_code", "card_name", "card_status", "annual_fee", "apply_url",
    "category", "channel", "cashback_type", "cashback_value", "min_amount",
    "max_cashback", "frequency_limit", "requires_registration",
    "recommendation_scope", "valid_from", "valid_until",
    "conditions_json", "excluded_conditions_json", "source_url",
    "raw_text_hash", "summary", "extractor_version", "extracted_at",
    "confidence", "status", "run_id", "raw_payload_json",
)

_PROMOTION_CURRENT_COLS = (
    "promo_id", "promo_version_id", "title", "bank_code", "bank_name",
    "card_code", "card_name", "card_status", "annual_fee", "apply_url",
    "category", "channel", "cashback_type", "cashback_value", "min_amount",
    "max_cashback", "frequency_limit", "requires_registration",
    "recommendation_scope", "valid_from", "valid_until",
    "conditions_json", "excluded_conditions_json", "source_url",
    "raw_text_hash", "summary", "extractor_version", "extracted_at",
    "confidence", "status", "run_id", "raw_payload_json",
)


@dataclass
class SyncResult:
    runs_upserted: int = 0
    versions_upserted: int = 0
    current_upserted: int = 0
    failures: int = 0


def sync_sqlite_to_supabase(sqlite_db_path: str, supabase_url: str) -> SyncResult:
    """Read all three tables from SQLite and upsert into Supabase PostgreSQL.

    Tables are synced in foreign-key order:
        extract_runs → promotion_versions → promotion_current

    The requires_registration column is converted from SQLite INTEGER (0/1)
    to Python bool so PostgreSQL receives the correct BOOLEAN value.
    """
    result = SyncResult()
    sqlite_conn = sqlite3.connect(sqlite_db_path)
    sqlite_conn.row_factory = sqlite3.Row
    try:
        pg_conn = psycopg2.connect(supabase_url)
        try:
            _sync_table(
                sqlite_conn, pg_conn,
                sqlite_table="extract_runs",
                pg_table="extract_runs",
                cols=_EXTRACT_RUN_COLS,
                pk="run_id",
                bool_cols=frozenset(),
                counter_attr="runs_upserted",
                result=result,
            )
            _sync_table(
                sqlite_conn, pg_conn,
                sqlite_table="promotion_versions",
                pg_table="promotion_versions",
                cols=_PROMOTION_VERSION_COLS,
                pk="promo_version_id",
                bool_cols=frozenset({"requires_registration"}),
                counter_attr="versions_upserted",
                result=result,
            )
            _sync_table(
                sqlite_conn, pg_conn,
                sqlite_table="promotion_current",
                pg_table="promotion_current",
                cols=_PROMOTION_CURRENT_COLS,
                pk="promo_id",
                bool_cols=frozenset({"requires_registration"}),
                counter_attr="current_upserted",
                result=result,
            )
        finally:
            pg_conn.close()
    finally:
        sqlite_conn.close()

    return result


def _sync_table(
    sqlite_conn: sqlite3.Connection,
    pg_conn,
    *,
    sqlite_table: str,
    pg_table: str,
    cols: tuple[str, ...],
    pk: str,
    bool_cols: frozenset[str],
    counter_attr: str,
    result: SyncResult,
) -> None:
    rows = [
        _to_pg_row(row, cols, bool_cols)
        for row in sqlite_conn.execute(f"SELECT {', '.join(cols)} FROM {sqlite_table}")
    ]
    if not rows:
        return

    col_list = ", ".join(cols)
    update_set = ", ".join(
        f"{col} = EXCLUDED.{col}" for col in cols if col != pk
    )
    sql = f"""
        INSERT INTO {pg_table} ({col_list})
        VALUES %s
        ON CONFLICT ({pk}) DO UPDATE SET {update_set}
    """

    try:
        with pg_conn.cursor() as cursor:
            psycopg2.extras.execute_values(cursor, sql, rows)
        pg_conn.commit()
        setattr(result, counter_attr, len(rows))
    except Exception as exc:
        pg_conn.rollback()
        result.failures += len(rows)
        print(f"[supabase_store] failed to sync {pg_table}: {exc}", flush=True)


def _to_pg_row(row: sqlite3.Row, cols: tuple[str, ...], bool_cols: frozenset[str]) -> tuple:
    return tuple(
        bool(row[col]) if col in bool_cols else row[col]
        for col in cols
    )
