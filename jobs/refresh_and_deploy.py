"""
CardSense: 全銀行提取 → 匯入 DB → 同步 Supabase 流程

Usage:
    # 提取全部銀行、匯入 DB、同步 Supabase
    uv run python jobs/refresh_and_deploy.py

    # 只提取指定銀行
    uv run python jobs/refresh_and_deploy.py --banks FUBON TAISHIN

    # 跳過提取，只匯入最新 JSONL 並同步
    uv run python jobs/refresh_and_deploy.py --import-only

    # 提取 + 匯入，但跳過 Supabase 同步
    uv run python jobs/refresh_and_deploy.py --no-supabase

    # 提取 + 匯入 + 同步，並複製 DB 到 cardsense-api/data/（本機測試用）
    uv run python jobs/refresh_and_deploy.py --deploy-local

    # 每家銀行限制提取卡片數（測試用）
    uv run python jobs/refresh_and_deploy.py --limit 2

流程:
    1. 依序跑各銀行 extractor → 產出 JSONL
    2. 將每份 JSONL 匯入 extractor 的 SQLite DB
    3. 同步 SQLite DB 到 Supabase（PostgreSQL）
    4. 印出摘要與後續指令提示
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

BANK_RUNNERS = {
    "ESUN": "jobs.run_esun_real_job",
    "CATHAY": "jobs.run_cathay_real_job",
    "TAISHIN": "jobs.run_taishin_real_job",
    "FUBON": "jobs.run_fubon_real_job",
    "CTBC": "jobs.run_ctbc_real_job",
}

DEFAULT_DB_PATH = os.path.join(project_root, "data", "cardsense.db")
API_DB_PATH = os.path.abspath(os.path.join(project_root, "..", "cardsense-api", "data", "cardsense.db"))


def _console(message: str) -> None:
    encoding = sys.stdout.encoding or "utf-8"
    safe = message.encode(encoding, errors="replace").decode(encoding, errors="replace")
    print(safe)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CardSense: extract → import → sync")
    parser.add_argument("--banks", nargs="*", default=None,
                        help=f"Banks to extract (default: all). Choices: {', '.join(BANK_RUNNERS)}")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit cards per bank (for testing)")
    parser.add_argument("--import-only", action="store_true",
                        help="Skip extraction, import latest JSONL files per bank")
    parser.add_argument("--no-supabase", action="store_true",
                        help="Skip Supabase sync step")
    parser.add_argument("--deploy-local", action="store_true",
                        help="Copy DB to cardsense-api/data/ after sync (local dev only)")
    parser.add_argument("--db", default=DEFAULT_DB_PATH,
                        help="SQLite DB path")
    parser.add_argument("--sync-bank", default=None,
                        help="Limit Supabase sync to a single bank_code")
    parser.add_argument("--sync-card", default=None,
                        help="Limit Supabase sync to a single card_code")
    return parser.parse_args()


def find_latest_jsonl(bank_label: str) -> str | None:
    """Find the most recent JSONL file for a given bank."""
    output_dir = os.path.join(project_root, "outputs")
    pattern = os.path.join(output_dir, f"{bank_label.lower()}-real-*.jsonl")
    files = glob.glob(pattern)
    timestamped_files = [
        path
        for path in files
        if re.search(rf"{bank_label.lower()}-real-\d{{8}}-\d{{6}}\.jsonl$", os.path.basename(path))
    ]
    if timestamped_files:
        files = timestamped_files
    files.sort(key=os.path.getmtime, reverse=True)
    return files[0] if files else None


def run_extraction(bank: str, limit: int | None) -> str | None:
    """Run the extraction job for one bank. Returns the output JSONL path."""
    _console(f"\n{'='*60}")
    _console(f">>> EXTRACTING: {bank}")
    _console(f"{'='*60}")

    module_name = BANK_RUNNERS[bank]
    try:
        module = __import__(module_name, fromlist=["run"])
        exit_code = module.run(limit=limit)
        if exit_code != 0:
            _console(f">>> WARNING: {bank} extraction returned exit code {exit_code}")
            return None
    except Exception as error:
        _console(f">>> ERROR: {bank} extraction failed: {error}")
        return None

    return find_latest_jsonl(bank)


def run_import(jsonl_path: str, db_path: str) -> int:
    """Import JSONL into SQLite DB. Returns count of imported promotions."""
    from extractor import db_store

    connection = db_store.initialize_database(db_path)
    imported = 0
    failures = 0
    bank_code = None
    reset_done = False

    import json
    run_id = db_store.create_extract_run(
        connection, bank_code=None, source="refresh-and-deploy",
        extractor_version="unknown", input_file=jsonl_path, output_file=None,
    )

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                bank_code = bank_code or payload.get("bankCode")
                if bank_code and not reset_done:
                    db_store.delete_current_promotions_for_bank(connection, bank_code)
                    reset_done = True
                db_store.upsert_promotion(connection, payload, run_id)
                imported += 1
            except Exception as error:
                failures += 1
                _console(f">>> Import failed at line {line_num}: {error}")

    db_store.finalize_extract_run(
        connection, run_id=run_id,
        status="SUCCESS" if failures == 0 else "PARTIAL_SUCCESS",
        cards_processed=0, promotions_loaded=imported, failures=failures,
        notes=f"refresh_and_deploy: {os.path.basename(jsonl_path)}",
    )
    connection.close()
    return imported


def deploy_db(db_path: str) -> bool:
    """Copy DB to cardsense-api/data/ for Docker build."""
    if not os.path.exists(os.path.dirname(API_DB_PATH)):
        _console(f">>> SKIP deploy: {os.path.dirname(API_DB_PATH)} does not exist")
        return False

    shutil.copy2(db_path, API_DB_PATH)
    _console(f">>> DB copied to {API_DB_PATH}")
    return True


def apply_benefit_plan_tags(db_path: str) -> None:
    from jobs.tag_plan_ids import tag_plan_ids

    _console("\n>>> TAGGING benefit plan ids")
    tag_plan_ids(db_path, dry_run=False)


def _iter_supabase_candidates(validate_supabase_url) -> tuple[list[tuple[str, str]], list[str]]:
    candidates = (
        ("SUPABASE_POOL_MODE", os.environ.get("SUPABASE_POOL_MODE")),
        ("SUPABASE_DATABASE_URL", os.environ.get("SUPABASE_DATABASE_URL")),
    )

    valid_candidates: list[tuple[str, str]] = []
    config_errors: list[str] = []
    seen_values: set[str] = set()
    for env_name, value in candidates:
        if not value or value in seen_values:
            continue
        seen_values.add(value)
        try:
            validate_supabase_url(value)
        except ValueError as error:
            config_errors.append(f"{env_name}: {error}")
            continue
        valid_candidates.append((env_name, value))
    return valid_candidates, config_errors


def _describe_supabase_target(supabase_url: str) -> str:
    host = urlsplit(supabase_url).hostname or "unknown-host"
    if ".pooler.supabase.com" in host:
        return f"{host} (pooler)"
    if host.startswith("db.") and host.endswith(".supabase.co"):
        return f"{host} (direct)"
    return host


def _get_supabase_http_candidate(validate_supabase_project_url) -> tuple[tuple[str, str, str] | None, list[str]]:
    project_url = os.environ.get("SUPABASE_URL")
    service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not project_url and not service_role_key:
        return None, []

    config_errors: list[str] = []
    if not project_url:
        config_errors.append("SUPABASE_URL: missing HTTPS project URL for REST sync")
    if not service_role_key:
        config_errors.append("SUPABASE_SERVICE_ROLE_KEY: missing service-role key for REST sync")
    if config_errors:
        return None, config_errors

    try:
        validate_supabase_project_url(project_url)
    except ValueError as error:
        return None, [f"SUPABASE_URL: {error}"]
    return ("SUPABASE_REST", project_url, service_role_key), []


def run_sync(db_path: str, sync_bank: str | None = None, sync_card: str | None = None) -> bool:
    """Sync SQLite → Supabase. Returns True on success, False on failure."""
    load_dotenv()
    from extractor.supabase_store import (
        SyncFilter,
        get_reconnect_warn_threshold,
        get_http_timeout_seconds,
        sync_sqlite_to_supabase_http,
        sync_sqlite_to_supabase,
        validate_supabase_project_url,
        validate_supabase_url,
    )
    sync_filter = SyncFilter(
        bank_code=sync_bank.upper() if sync_bank else None,
        card_code=sync_card.upper() if sync_card else None,
    )

    http_candidate, http_config_errors = _get_supabase_http_candidate(validate_supabase_project_url)
    candidates, config_errors = _iter_supabase_candidates(validate_supabase_url)

    if not http_candidate and not candidates:
        _console(">>> SKIP Supabase sync: no valid Supabase DSN found")
        for error in http_config_errors + config_errors:
            _console(f">>> CONFIG ERROR: {error}")
        return False

    _console("\n>>> SYNCING to Supabase...")
    _console(
        ">>> Sync config: "
        f"batch_size={os.environ.get('SUPABASE_SYNC_BATCH_SIZE', '10')} "
        f"statement_timeout_ms={os.environ.get('SUPABASE_STATEMENT_TIMEOUT_MS', '300000')} "
        f"http_timeout_sec={get_http_timeout_seconds()}"
    )
    if sync_filter.has_filter():
        scope_parts = []
        if sync_filter.bank_code:
            scope_parts.append(f"bank={sync_filter.bank_code}")
        if sync_filter.card_code:
            scope_parts.append(f"card={sync_filter.card_code}")
        _console(f">>> Sync scope: {' '.join(scope_parts)}")

    errors: list[str] = []
    if http_candidate:
        _, project_url, service_role_key = http_candidate
        rest_host = urlsplit(project_url).hostname or "unknown-host"
        _console(f">>> Trying SUPABASE_REST: {rest_host} (https)")
        try:
            result = sync_sqlite_to_supabase_http(db_path, project_url, service_role_key, sync_filter)
        except Exception as error:
            errors.append(f"SUPABASE_REST: {error}")
            _console(f">>> WARNING: SUPABASE_REST failed: {error}")
        else:
            _console(f">>> Supabase sync transport: SUPABASE_REST")
            return _report_sync_result(result, get_reconnect_warn_threshold())

    for env_name, supabase_url in candidates:
        _console(
            f">>> Trying {env_name}: {_describe_supabase_target(supabase_url)}"
        )
        try:
            result = sync_sqlite_to_supabase(db_path, supabase_url, sync_filter)
            break
        except Exception as error:
            errors.append(f"{env_name}: {error}")
            _console(f">>> WARNING: {env_name} failed: {error}")
    else:
        _console(">>> ERROR: Supabase sync failed for all configured DSNs")
        for error in http_config_errors + config_errors + errors:
            _console(f">>> CONFIG ERROR: {error}")
        return False

    _console(f">>> Supabase sync transport: {env_name}")
    return _report_sync_result(result, get_reconnect_warn_threshold())


def _report_sync_result(result, reconnect_warn_threshold: int) -> bool:
    _console(f">>> Supabase sync: runs={result.runs_upserted} versions={result.versions_upserted} current={result.current_upserted} failures={result.failures}")
    _console(f">>> Supabase reconnects: {result.reconnects}")
    if result.table_durations:
        _console(
            ">>> Table durations: "
            + " ".join(
                f"{table}={seconds:.1f}s"
                for table, seconds in result.table_durations.items()
            )
        )
    if result.reconnects > reconnect_warn_threshold:
        _console(
            f">>> WARNING: reconnects={result.reconnects} exceeded threshold={reconnect_warn_threshold}"
        )
    if result.failures > 0:
        _console(f">>> WARNING: {result.failures} rows failed to sync")
        return False
    return True


def print_db_summary(db_path: str) -> None:
    """Print a summary of the current DB state."""
    conn = sqlite3.connect(db_path)

    _console(f"\n{'='*60}")
    _console(">>> DB SUMMARY")
    _console(f"{'='*60}")

    rows = conn.execute(
        "SELECT bank_code, count(*) as cnt FROM promotion_current GROUP BY bank_code ORDER BY cnt DESC"
    ).fetchall()
    total = 0
    for bank_code, count in rows:
        _console(f"  {bank_code}: {count} promotions")
        total += count
    _console(f"  TOTAL: {total}")

    _console("")
    rows = conn.execute(
        "SELECT recommendation_scope, count(*) FROM promotion_current GROUP BY recommendation_scope"
    ).fetchall()
    for scope, count in rows:
        _console(f"  {scope}: {count}")

    conn.close()


def main() -> int:
    args = parse_args()
    banks = [b.upper() for b in args.banks] if args.banks else list(BANK_RUNNERS.keys())

    # Validate bank names
    invalid = [b for b in banks if b not in BANK_RUNNERS]
    if invalid:
        _console(f">>> ERROR: Unknown banks: {invalid}. Valid: {list(BANK_RUNNERS.keys())}")
        return 1

    start_time = datetime.now()
    results: dict[str, dict] = {}

    for bank in banks:
        if args.import_only:
            jsonl_path = find_latest_jsonl(bank)
            if not jsonl_path:
                _console(f">>> SKIP: no JSONL found for {bank}")
                results[bank] = {"status": "SKIPPED", "reason": "no JSONL"}
                continue
        else:
            jsonl_path = run_extraction(bank, args.limit)
            if not jsonl_path:
                results[bank] = {"status": "EXTRACT_FAILED"}
                continue

        _console(f"\n>>> IMPORTING: {bank} from {os.path.basename(jsonl_path)}")
        imported = run_import(jsonl_path, args.db)
        results[bank] = {"status": "OK", "imported": imported, "jsonl": os.path.basename(jsonl_path)}
        _console(f">>> {bank}: {imported} promotions imported")

    apply_benefit_plan_tags(args.db)

    # Summary
    print_db_summary(args.db)

    # Supabase sync (default when SUPABASE_DATABASE_URL is set)
    if not args.no_supabase:
        synced = run_sync(args.db, sync_bank=args.sync_bank, sync_card=args.sync_card)
        if synced:
            _console("\n>>> NEXT STEPS:")
            _console("  Railway will auto-deploy from Supabase data (no git push needed)")
    else:
        _console("\n>>> --no-supabase: skipped Supabase sync")

    # Local deploy (opt-in, for local Docker testing)
    if args.deploy_local:
        _console("")
        deployed = deploy_db(args.db)
        if deployed:
            _console("  cd ../cardsense-api && git add data/cardsense.db && git push")

    elapsed = (datetime.now() - start_time).total_seconds()
    _console(f"\n>>> Done in {elapsed:.0f}s")

    failed = [b for b, r in results.items() if r["status"] != "OK"]
    if failed:
        _console(f">>> WARNINGS: {failed}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
