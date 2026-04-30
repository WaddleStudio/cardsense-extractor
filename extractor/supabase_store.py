"""Sync SQLite tables to Supabase via PostgreSQL or HTTPS REST."""
from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import psycopg2
import psycopg2.extras
import requests

from extractor.card_lifecycle import normalize_card_status, normalize_promotion_status

_DEFAULT_BATCH_SIZE = 10
_DEFAULT_STATEMENT_TIMEOUT_MS = 300000
_DEFAULT_RECONNECT_WARN_THRESHOLD = 3
_DEFAULT_HTTP_TIMEOUT_SEC = 60

# Column order must match supabase_schema.sql exactly.
_EXTRACT_RUN_COLS = (
    "run_id", "bank_code", "source", "extractor_version",
    "started_at", "finished_at", "status", "cards_processed",
    "promotions_loaded", "failures", "input_file", "output_file", "notes",
)

_PROMOTION_VERSION_COLS = (
    "promo_version_id", "promo_id", "title", "bank_code", "bank_name",
    "card_code", "card_name", "card_status", "annual_fee", "apply_url",
    "category", "subcategory", "channel", "cashback_type", "cashback_value", "min_amount",
    "max_cashback", "frequency_limit", "requires_registration",
    "recommendation_scope", "eligibility_type", "valid_from", "valid_until",
    "conditions_json", "excluded_conditions_json", "source_url",
    "raw_text_hash", "summary", "extractor_version", "extracted_at",
    "confidence", "status", "plan_id", "run_id", "raw_payload_json",
)

_PROMOTION_CURRENT_COLS = (
    "promo_id", "promo_version_id", "title", "bank_code", "bank_name",
    "card_code", "card_name", "card_status", "annual_fee", "apply_url",
    "category", "subcategory", "channel", "cashback_type", "cashback_value", "min_amount",
    "max_cashback", "frequency_limit", "requires_registration",
    "recommendation_scope", "eligibility_type", "valid_from", "valid_until",
    "conditions_json", "excluded_conditions_json", "source_url",
    "raw_text_hash", "summary", "extractor_version", "extracted_at",
    "confidence", "status", "plan_id", "run_id", "raw_payload_json",
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


@dataclass(frozen=True)
class SyncFilter:
    bank_code: str | None = None
    card_code: str | None = None

    def has_filter(self) -> bool:
        return bool(self.bank_code or self.card_code)


def validate_supabase_url(supabase_url: str) -> None:
    """Reject placeholder or malformed Postgres DSNs before psycopg2 connects."""
    if "://" not in supabase_url:
        raise ValueError("Supabase DSN must start with postgresql:// or postgres://")

    after_scheme = supabase_url.split("://", 1)[1]
    if "@" in after_scheme:
        raw_userinfo = after_scheme.rsplit("@", 1)[0]
        if any(char in raw_userinfo for char in "?#/"):
            raise ValueError(
                "Supabase DSN contains unencoded reserved characters in the username or password; URL-encode characters like ?, #, /, and @"
            )

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


def validate_supabase_project_url(supabase_project_url: str) -> None:
    """Validate the HTTPS project URL used by Supabase REST APIs."""
    parsed = urlsplit(supabase_project_url)
    if parsed.scheme != "https":
        raise ValueError("Supabase project URL must start with https://")
    if not parsed.hostname:
        raise ValueError("Supabase project URL is missing a hostname")


def sync_sqlite_to_supabase(
    sqlite_db_path: str,
    supabase_url: str,
    sync_filter: SyncFilter | None = None,
) -> SyncResult:
    """Read all three tables from SQLite and upsert into Supabase PostgreSQL.

    Tables are synced in foreign-key order:
        extract_runs → promotion_versions → promotion_current

    The requires_registration column is converted from SQLite INTEGER (0/1)
    to Python bool so PostgreSQL receives the correct BOOLEAN value.

    Rows are upserted in batches to avoid Supabase statement timeouts.
    """
    validate_supabase_url(supabase_url)
    sync_filter = sync_filter or SyncFilter()
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
                sync_filter=sync_filter,
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
                sync_filter=sync_filter,
            )
            result.table_durations["promotion_versions"] = time.perf_counter() - table_start

            table_start = time.perf_counter()
            pg_conn, _ = _replace_current_pg_atomically(
                sqlite_conn, pg_conn, supabase_url,
                result=result,
                required_parent_keys=synced_version_ids,
                sync_filter=sync_filter,
            )
            result.table_durations["promotion_current"] = time.perf_counter() - table_start
        finally:
            pg_conn.close()
    finally:
        sqlite_conn.close()

    return result


def sync_sqlite_to_supabase_http(
    sqlite_db_path: str,
    supabase_project_url: str,
    service_role_key: str,
    sync_filter: SyncFilter | None = None,
) -> SyncResult:
    """Sync all three SQLite tables to Supabase via the REST API over HTTPS."""
    validate_supabase_project_url(supabase_project_url)
    if not service_role_key:
        raise ValueError("Supabase service role key is required for REST sync")

    sync_filter = sync_filter or SyncFilter()
    result = SyncResult()
    sqlite_conn = sqlite3.connect(sqlite_db_path)
    sqlite_conn.row_factory = sqlite3.Row
    session = requests.Session()
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    timeout_sec = get_http_timeout_seconds()
    base_url = supabase_project_url.rstrip("/")

    try:
        table_start = time.perf_counter()
        synced_run_ids = _sync_table_http(
            sqlite_conn,
            session,
            base_url=base_url,
            headers=headers,
            sqlite_table="extract_runs",
            rest_table="extract_runs",
            cols=_EXTRACT_RUN_COLS,
            pk="run_id",
            bool_cols=frozenset(),
            counter_attr="runs_upserted",
            result=result,
            timeout_sec=timeout_sec,
            sync_filter=sync_filter,
        )
        result.table_durations["extract_runs"] = time.perf_counter() - table_start

        table_start = time.perf_counter()
        synced_version_ids = _sync_table_http(
            sqlite_conn,
            session,
            base_url=base_url,
            headers=headers,
            sqlite_table="promotion_versions",
            rest_table="promotion_versions",
            cols=_PROMOTION_VERSION_COLS,
            pk="promo_version_id",
            bool_cols=frozenset({"requires_registration"}),
            counter_attr="versions_upserted",
            result=result,
            timeout_sec=timeout_sec,
            required_parent_keys=synced_run_ids,
            parent_key_col="run_id",
            sync_filter=sync_filter,
        )
        result.table_durations["promotion_versions"] = time.perf_counter() - table_start

        table_start = time.perf_counter()
        _clear_table_http(
            session,
            base_url=base_url,
            headers=headers,
            rest_table="promotion_current",
            timeout_sec=timeout_sec,
            sync_filter=sync_filter,
        )
        _sync_table_http(
            sqlite_conn,
            session,
            base_url=base_url,
            headers=headers,
            sqlite_table="promotion_current",
            rest_table="promotion_current",
            cols=_PROMOTION_CURRENT_COLS,
            pk="promo_id",
            bool_cols=frozenset({"requires_registration"}),
            counter_attr="current_upserted",
            result=result,
            timeout_sec=timeout_sec,
            required_parent_keys=synced_version_ids,
            parent_key_col="promo_version_id",
            sync_filter=sync_filter,
        )
        result.table_durations["promotion_current"] = time.perf_counter() - table_start
    finally:
        sqlite_conn.close()
        session.close()

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


def get_http_timeout_seconds() -> int:
    return _get_positive_int_env("SUPABASE_HTTP_TIMEOUT_SEC", _DEFAULT_HTTP_TIMEOUT_SEC)


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
    sync_filter: SyncFilter | None = None,
):
    """Upsert rows in batches. Returns pg_conn plus synced primary keys."""
    batch_size = _get_batch_size()
    rows = _read_sqlite_rows(sqlite_conn, sqlite_table, cols, bool_cols, sync_filter)
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


def _replace_current_pg_atomically(
    sqlite_conn: sqlite3.Connection,
    pg_conn,
    supabase_url: str,
    *,
    result: SyncResult,
    required_parent_keys: set[str],
    sync_filter: SyncFilter | None = None,
):
    rows = _read_sqlite_rows(
        sqlite_conn,
        "promotion_current",
        _PROMOTION_CURRENT_COLS,
        frozenset({"requires_registration"}),
        sync_filter,
    )
    parent_idx = _PROMOTION_CURRENT_COLS.index("promo_version_id")
    filtered_rows = [row for row in rows if row[parent_idx] in required_parent_keys]
    skipped_rows = len(rows) - len(filtered_rows)
    if skipped_rows:
        result.failures += skipped_rows
        print(
            f"[supabase_store] skipping {skipped_rows} promotion_current rows because parent promo_version_id was not synced",
            flush=True,
        )
    if not filtered_rows:
        result.current_upserted = 0
        return pg_conn, set()

    sql = _build_upsert_sql("promotion_current", _PROMOTION_CURRENT_COLS, "promo_id")
    pk_idx = _PROMOTION_CURRENT_COLS.index("promo_id")
    batch_size = _get_batch_size()
    try:
        with pg_conn.cursor() as cursor:
            if sync_filter and sync_filter.has_filter():
                where_sql, params = _build_postgres_filter_clause(sync_filter)
                cursor.execute(f"DELETE FROM promotion_current WHERE {where_sql}", params)
            else:
                cursor.execute("DELETE FROM promotion_current")
            psycopg2.extras.execute_values(
                cursor,
                sql,
                filtered_rows,
                page_size=min(batch_size, len(filtered_rows)),
            )
        pg_conn.commit()
        result.current_upserted = len(filtered_rows)
        return pg_conn, {row[pk_idx] for row in filtered_rows}
    except Exception as exc:
        try:
            pg_conn.rollback()
        except Exception:
            pass
        result.failures += len(filtered_rows)
        print(
            f"[supabase_store] atomic promotion_current replace failed ({len(filtered_rows)} rows): {exc}",
            flush=True,
        )
        if pg_conn.closed:
            print("[supabase_store] reconnecting to Supabase...", flush=True)
            result.reconnects += 1
            pg_conn = _pg_connect(supabase_url)
        result.current_upserted = 0
        return pg_conn, set()


def _sync_table_http(
    sqlite_conn: sqlite3.Connection,
    session: requests.Session,
    *,
    base_url: str,
    headers: dict[str, str],
    sqlite_table: str,
    rest_table: str,
    cols: tuple[str, ...],
    pk: str,
    bool_cols: frozenset[str],
    counter_attr: str,
    result: SyncResult,
    timeout_sec: int,
    required_parent_keys: set[str] | None = None,
    parent_key_col: str | None = None,
    sync_filter: SyncFilter | None = None,
) -> set[str]:
    """Upsert rows into Supabase REST in batches and return synced primary keys."""
    batch_size = _get_batch_size()
    rows = _read_sqlite_rows(sqlite_conn, sqlite_table, cols, bool_cols, sync_filter)
    if required_parent_keys is not None and parent_key_col is not None:
        parent_idx = cols.index(parent_key_col)
        filtered_rows = [row for row in rows if row[parent_idx] in required_parent_keys]
        skipped_rows = len(rows) - len(filtered_rows)
        if skipped_rows:
            result.failures += skipped_rows
            print(
                f"[supabase_store] skipping {skipped_rows} {rest_table} rows because parent {parent_key_col} was not synced",
                flush=True,
            )
        rows = filtered_rows
    if not rows:
        setattr(result, counter_attr, 0)
        return set()

    upserted = 0
    synced_keys: set[str] = set()
    pk_idx = cols.index(pk)
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        succeeded_rows = _upsert_http_with_fallback(
            session=session,
            base_url=base_url,
            headers=headers,
            rest_table=rest_table,
            pk=pk,
            rows=batch,
            cols=cols,
            batch_size=batch_size,
            result=result,
            batch_num=i // batch_size + 1,
            pk_idx=pk_idx,
            timeout_sec=timeout_sec,
        )
        upserted += len(succeeded_rows)
        synced_keys.update(row[pk_idx] for row in succeeded_rows)

    setattr(result, counter_attr, upserted)
    return synced_keys


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


def _clear_table_pg(pg_conn, pg_table: str, sync_filter: SyncFilter | None = None) -> None:
    with pg_conn.cursor() as cursor:
        if sync_filter and sync_filter.has_filter():
            where_sql, params = _build_postgres_filter_clause(sync_filter)
            cursor.execute(f"DELETE FROM {pg_table} WHERE {where_sql}", params)
        else:
            cursor.execute(f"DELETE FROM {pg_table}")
    pg_conn.commit()


def _clear_table_http(
    session: requests.Session,
    *,
    base_url: str,
    headers: dict[str, str],
    rest_table: str,
    timeout_sec: int,
    sync_filter: SyncFilter | None = None,
) -> None:
    if sync_filter and sync_filter.has_filter():
        params = _build_rest_filter_params(sync_filter)
    else:
        params = {rest_table.split("_")[0]: "not.is.null"} if rest_table == "extract_runs" else {"promo_id": "not.is.null"}
    response = session.delete(
        f"{base_url}/rest/v1/{rest_table}",
        params=params,
        headers={**headers, "Prefer": "return=minimal"},
        timeout=timeout_sec,
    )
    response.raise_for_status()


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


def _upsert_http_with_fallback(
    *,
    session: requests.Session,
    base_url: str,
    headers: dict[str, str],
    rest_table: str,
    pk: str,
    rows: list[tuple],
    cols: tuple[str, ...],
    batch_size: int,
    result: SyncResult,
    batch_num: int,
    pk_idx: int,
    timeout_sec: int,
) -> list[tuple]:
    """Try an HTTP upsert batch, then recursively split it to isolate bad rows."""
    try:
        response = session.post(
            f"{base_url}/rest/v1/{rest_table}",
            params={"on_conflict": pk},
            headers=headers,
            json=_rows_to_json_objects(rows, cols),
            timeout=timeout_sec,
        )
        response.raise_for_status()
        return rows
    except requests.RequestException as exc:
        if len(rows) == 1:
            result.failures += 1
            print(
                f"[supabase_store] failed to sync {rest_table} row {rows[0][pk_idx]} in batch {batch_num}: {exc}",
                flush=True,
            )
            return []

        print(
            f"[supabase_store] failed to sync {rest_table} batch {batch_num} ({len(rows)} rows): {exc}; retrying with smaller chunks",
            flush=True,
        )

        midpoint = len(rows) // 2
        first_succeeded = _upsert_http_with_fallback(
            session=session,
            base_url=base_url,
            headers=headers,
            rest_table=rest_table,
            pk=pk,
            rows=rows[:midpoint],
            cols=cols,
            batch_size=batch_size,
            result=result,
            batch_num=batch_num,
            pk_idx=pk_idx,
            timeout_sec=timeout_sec,
        )
        second_succeeded = _upsert_http_with_fallback(
            session=session,
            base_url=base_url,
            headers=headers,
            rest_table=rest_table,
            pk=pk,
            rows=rows[midpoint:],
            cols=cols,
            batch_size=batch_size,
            result=result,
            batch_num=batch_num,
            pk_idx=pk_idx,
            timeout_sec=timeout_sec,
        )
        return first_succeeded + second_succeeded


def _read_sqlite_rows(
    sqlite_conn: sqlite3.Connection,
    sqlite_table: str,
    cols: tuple[str, ...],
    bool_cols: frozenset[str],
    sync_filter: SyncFilter | None = None,
) -> list[tuple]:
    query, params = _build_sqlite_select(sqlite_table, cols, sync_filter or SyncFilter())
    return [
        _to_pg_row(row, cols, bool_cols)
        for row in sqlite_conn.execute(query, params)
    ]


def _build_sqlite_select(
    sqlite_table: str,
    cols: tuple[str, ...],
    sync_filter: SyncFilter,
) -> tuple[str, list[str]]:
    col_sql = ", ".join(cols)
    if not sync_filter.has_filter():
        return f"SELECT {col_sql} FROM {sqlite_table}", []

    if sqlite_table in {"promotion_versions", "promotion_current"}:
        where_sql, params = _build_sqlite_filter_clause(sync_filter)
        return f"SELECT {col_sql} FROM {sqlite_table} WHERE {where_sql}", params

    if sqlite_table == "extract_runs":
        where_sql, params = _build_sqlite_filter_clause(sync_filter, table_alias="promotion_versions")
        query = (
            f"SELECT {col_sql} FROM extract_runs "
            f"WHERE run_id IN ("
            f"SELECT DISTINCT run_id FROM promotion_versions WHERE run_id IS NOT NULL AND {where_sql}"
            f")"
        )
        return query, params

    return f"SELECT {col_sql} FROM {sqlite_table}", []


def _build_sqlite_filter_clause(sync_filter: SyncFilter, table_alias: str | None = None) -> tuple[str, list[str]]:
    prefix = f"{table_alias}." if table_alias else ""
    clauses: list[str] = []
    params: list[str] = []
    if sync_filter.bank_code:
        clauses.append(f"{prefix}bank_code = ?")
        params.append(sync_filter.bank_code)
    if sync_filter.card_code:
        clauses.append(f"{prefix}card_code = ?")
        params.append(sync_filter.card_code)
    return " AND ".join(clauses), params


def _build_postgres_filter_clause(sync_filter: SyncFilter) -> tuple[str, list[str]]:
    clauses: list[str] = []
    params: list[str] = []
    if sync_filter.bank_code:
        clauses.append("bank_code = %s")
        params.append(sync_filter.bank_code)
    if sync_filter.card_code:
        clauses.append("card_code = %s")
        params.append(sync_filter.card_code)
    return " AND ".join(clauses), params


def _build_rest_filter_params(sync_filter: SyncFilter) -> dict[str, str]:
    params: dict[str, str] = {}
    if sync_filter.bank_code:
        params["bank_code"] = f"eq.{sync_filter.bank_code}"
    if sync_filter.card_code:
        params["card_code"] = f"eq.{sync_filter.card_code}"
    return params


def _rows_to_json_objects(rows: list[tuple], cols: tuple[str, ...]) -> list[dict[str, object]]:
    return [dict(zip(cols, row, strict=True)) for row in rows]


def _to_pg_row(row: sqlite3.Row, cols: tuple[str, ...], bool_cols: frozenset[str]) -> tuple:
    normalized = {col: (bool(row[col]) if col in bool_cols else row[col]) for col in cols}

    if "card_name" in normalized:
        card_name = normalized["card_name"]
        if "card_status" in normalized:
            normalized["card_status"] = normalize_card_status(normalized["card_status"], normalized.get("status"), card_name=card_name)
        if "status" in normalized:
            normalized["status"] = normalize_promotion_status(normalized["status"], normalized.get("card_status"), card_name=card_name)

    return tuple(normalized[col] for col in cols)
