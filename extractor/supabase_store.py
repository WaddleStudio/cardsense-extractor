"""Sync all three SQLite tables to Supabase (PostgreSQL) via psycopg2."""
from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import psycopg2
import psycopg2.extras

_DEFAULT_BATCH_SIZE = 10
_DEFAULT_STATEMENT_TIMEOUT_MS = 300000
_DEFAULT_RECONNECT_WARN_THRESHOLD = 3

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
    "recommendation_scope", "eligibility_type", "valid_from", "valid_until",
    "conditions_json", "excluded_conditions_json", "source_url",
    "raw_text_hash", "summary", "extractor_version", "extracted_at",
    "confidence", "status", "run_id", "raw_payload_json",
)

_PROMOTION_CURRENT_COLS = (
    "promo_id", "promo_version_id", "title", "bank_code", "bank_name",
    "card_code", "card_name", "card_status", "annual_fee", "apply_url",
    "category", "channel", "cashback_type", "cashback_value", "min_amount",
    "max_cashback", "frequency_limit", "requires_registration",
    "recommendation_scope", "eligibility_type", "valid_from", "valid_until",
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
    reconnects: int = 0
    table_durations: dict[str, float] | None = None

    def __post_init__(self) -> None:
        if self.table_durations is None:
            self.table_durations = {}


def validate_supabase_url(supabase_url: str) -> None:
    """Reject placeholder or malformed Postgres DSNs before psycopg2 connects."""
    parsed = urlsplit(supabase_url)
    if parsed.scheme not in {"postgresql", "postgres"}:
        raise ValueError("Supabase DSN must start with postgresql:// or postgres://")

    host = parsed.hostname
    if not host:
        raise ValueError("Supabase DSN is missing a hostname")

    if (
        host == "aws-0-region.pooler.supabase.com"
        or "<project-ref>" in host
        or ".region.pooler.supabase.com" in host
    ):
        raise ValueError(
            "Supabase DSN still contains a placeholder host; replace it with the real pooler hostname from Supabase settings"
        )


def sync_sqlite_to_supabase(sqlite_db_path: str, supabase_url: str) -> SyncResult:
    """Read all three tables from SQLite and upsert into Supabase PostgreSQL.

    Tables are synced in foreign-key order:
        extract_runs → promotion_versions → promotion_current

    The requires_registration column is converted from SQLite INTEGER (0/1)
    to Python bool so PostgreSQL receives the correct BOOLEAN value.

    Rows are upserted in batches to avoid Supabase statement timeouts.
    """
    validate_supabase_url(supabase_url)
    result = SyncResult()
    sqlite_conn = sqlite3.connect(sqlite_db_path)
    sqlite_conn.row_factory = sqlite3.Row
    try:
        pg_conn = _pg_connect(supabase_url)
        try:
            table_start = time.perf_counter()
            pg_conn, _ = _sync_table(
                sqlite_conn, pg_conn, supabase_url,
                sqlite_table="extract_runs",
                pg_table="extract_runs",
                cols=_EXTRACT_RUN_COLS,
                pk="run_id",
                bool_cols=frozenset(),
                counter_attr="runs_upserted",
                result=result,
            )
            result.table_durations["extract_runs"] = time.perf_counter() - table_start

            table_start = time.perf_counter()
            pg_conn, synced_version_ids = _sync_table(
                sqlite_conn, pg_conn, supabase_url,
                sqlite_table="promotion_versions",
                pg_table="promotion_versions",
                cols=_PROMOTION_VERSION_COLS,
                pk="promo_version_id",
                bool_cols=frozenset({"requires_registration"}),
                counter_attr="versions_upserted",
                result=result,
            )
            result.table_durations["promotion_versions"] = time.perf_counter() - table_start

            table_start = time.perf_counter()
            pg_conn, _ = _sync_table(
                sqlite_conn, pg_conn, supabase_url,
                sqlite_table="promotion_current",
                pg_table="promotion_current",
                cols=_PROMOTION_CURRENT_COLS,
                pk="promo_id",
                bool_cols=frozenset({"requires_registration"}),
                counter_attr="current_upserted",
                result=result,
                required_parent_keys=synced_version_ids,
                parent_key_col="promo_version_id",
            )
            result.table_durations["promotion_current"] = time.perf_counter() - table_start
        finally:
            pg_conn.close()
    finally:
        sqlite_conn.close()

    return result


def _pg_connect(supabase_url: str):
    """Open a PostgreSQL connection with a configurable statement timeout."""
    timeout_ms = _get_positive_int_env(
        "SUPABASE_STATEMENT_TIMEOUT_MS",
        _DEFAULT_STATEMENT_TIMEOUT_MS,
    )
    conn = psycopg2.connect(
        supabase_url,
        options=f"-c statement_timeout={timeout_ms}",
    )
    return conn


def _get_batch_size() -> int:
    return _get_positive_int_env("SUPABASE_SYNC_BATCH_SIZE", _DEFAULT_BATCH_SIZE)


def get_reconnect_warn_threshold() -> int:
    return _get_positive_int_env(
        "SUPABASE_RECONNECT_WARN_THRESHOLD",
        _DEFAULT_RECONNECT_WARN_THRESHOLD,
    )


def _get_positive_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _sync_table(
    sqlite_conn: sqlite3.Connection,
    pg_conn,
    supabase_url: str,
    *,
    sqlite_table: str,
    pg_table: str,
    cols: tuple[str, ...],
    pk: str,
    bool_cols: frozenset[str],
    counter_attr: str,
    result: SyncResult,
    required_parent_keys: set[str] | None = None,
    parent_key_col: str | None = None,
):
    """Upsert rows in batches. Returns pg_conn plus synced primary keys."""
    batch_size = _get_batch_size()
    rows = [
        _to_pg_row(row, cols, bool_cols)
        for row in sqlite_conn.execute(f"SELECT {', '.join(cols)} FROM {sqlite_table}")
    ]
    if required_parent_keys is not None and parent_key_col is not None:
        parent_idx = cols.index(parent_key_col)
        filtered_rows = [row for row in rows if row[parent_idx] in required_parent_keys]
        skipped_rows = len(rows) - len(filtered_rows)
        if skipped_rows:
            result.failures += skipped_rows
            print(
                f"[supabase_store] skipping {skipped_rows} {pg_table} rows because parent {parent_key_col} was not synced",
                flush=True,
            )
        rows = filtered_rows
    if not rows:
        setattr(result, counter_attr, 0)
        return pg_conn, set()

    sql = _build_upsert_sql(pg_table, cols, pk)

    upserted = 0
    synced_keys: set[str] = set()
    pk_idx = cols.index(pk)
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        pg_conn, succeeded_rows = _upsert_with_fallback(
            pg_conn=pg_conn,
            supabase_url=supabase_url,
            pg_table=pg_table,
            sql=sql,
            rows=batch,
            batch_size=batch_size,
            result=result,
            batch_num=i // batch_size + 1,
            pk_idx=pk_idx,
        )
        upserted += len(succeeded_rows)
        synced_keys.update(row[pk_idx] for row in succeeded_rows)

    setattr(result, counter_attr, upserted)
    return pg_conn, synced_keys


def _build_upsert_sql(pg_table: str, cols: tuple[str, ...], pk: str) -> str:
    col_list = ", ".join(cols)
    update_cols = [col for col in cols if col != pk]
    update_set = ", ".join(f"{col} = EXCLUDED.{col}" for col in update_cols)
    changed_predicate = " OR ".join(
        f"{pg_table}.{col} IS DISTINCT FROM EXCLUDED.{col}" for col in update_cols
    )
    return f"""
        INSERT INTO {pg_table} ({col_list})
        VALUES %s
        ON CONFLICT ({pk}) DO UPDATE SET {update_set}
        WHERE {changed_predicate}
    """


def _upsert_with_fallback(
    *,
    pg_conn,
    supabase_url: str,
    pg_table: str,
    sql: str,
    rows: list[tuple],
    batch_size: int,
    result: SyncResult,
    batch_num: int,
    pk_idx: int,
):
    """Try a batch, then recursively split it to isolate slow/bad rows."""
    try:
        with pg_conn.cursor() as cursor:
            psycopg2.extras.execute_values(cursor, sql, rows, page_size=min(batch_size, len(rows)))
        pg_conn.commit()
        return pg_conn, rows
    except Exception as exc:
        try:
            pg_conn.rollback()
        except Exception:
            pass

        if len(rows) == 1:
            result.failures += 1
            print(
                f"[supabase_store] failed to sync {pg_table} row {rows[0][pk_idx]} in batch {batch_num}: {exc}",
                flush=True,
            )
            if pg_conn.closed:
                print(f"[supabase_store] reconnecting to Supabase...", flush=True)
                result.reconnects += 1
                pg_conn = _pg_connect(supabase_url)
            return pg_conn, []

        print(
            f"[supabase_store] failed to sync {pg_table} batch {batch_num} ({len(rows)} rows): {exc}; retrying with smaller chunks",
            flush=True,
        )
        if pg_conn.closed:
            print(f"[supabase_store] reconnecting to Supabase...", flush=True)
            result.reconnects += 1
            pg_conn = _pg_connect(supabase_url)

        midpoint = len(rows) // 2
        pg_conn, first_succeeded = _upsert_with_fallback(
            pg_conn=pg_conn,
            supabase_url=supabase_url,
            pg_table=pg_table,
            sql=sql,
            rows=rows[:midpoint],
            batch_size=batch_size,
            result=result,
            batch_num=batch_num,
            pk_idx=pk_idx,
        )
        pg_conn, second_succeeded = _upsert_with_fallback(
            pg_conn=pg_conn,
            supabase_url=supabase_url,
            pg_table=pg_table,
            sql=sql,
            rows=rows[midpoint:],
            batch_size=batch_size,
            result=result,
            batch_num=batch_num,
            pk_idx=pk_idx,
        )
        return pg_conn, first_succeeded + second_succeeded


def _to_pg_row(row: sqlite3.Row, cols: tuple[str, ...], bool_cols: frozenset[str]) -> tuple:
    return tuple(
        bool(row[col]) if col in bool_cols else row[col]
        for col in cols
    )
