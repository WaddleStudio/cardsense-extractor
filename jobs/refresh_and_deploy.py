"""
CardSense: 全銀行提取 → 匯入 DB → 部署流程

Usage:
    # 提取全部銀行、匯入 DB、複製到 API
    uv run python jobs/refresh_and_deploy.py

    # 只提取指定銀行
    uv run python jobs/refresh_and_deploy.py --banks FUBON TAISHIN

    # 跳過提取，只匯入最新 JSONL 並部署
    uv run python jobs/refresh_and_deploy.py --import-only

    # 提取 + 匯入，但不複製到 API
    uv run python jobs/refresh_and_deploy.py --no-deploy

    # 每家銀行限制提取卡片數（測試用）
    uv run python jobs/refresh_and_deploy.py --limit 2

流程:
    1. 依序跑各銀行 extractor → 產出 JSONL
    2. 將每份 JSONL 匯入 extractor 的 SQLite DB
    3. 複製 DB 到 cardsense-api/data/（供 Docker build 使用）
    4. 印出摘要與後續指令提示
"""

from __future__ import annotations

import argparse
import glob
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

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
    return parser.parse_args()


def find_latest_jsonl(bank_label: str) -> str | None:
    """Find the most recent JSONL file for a given bank."""
    output_dir = os.path.join(project_root, "outputs")
    pattern = os.path.join(output_dir, f"{bank_label.lower()}-real-*.jsonl")
    files = sorted(glob.glob(pattern), reverse=True)
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


def run_sync(db_path: str) -> bool:
    """Sync SQLite → Supabase. Returns True on success, False on failure."""
    load_dotenv()
    supabase_url = os.environ.get("SUPABASE_DATABASE_URL")
    if not supabase_url:
        _console(">>> SKIP Supabase sync: SUPABASE_DATABASE_URL not set")
        return False

    from extractor.supabase_store import sync_sqlite_to_supabase
    _console("\n>>> SYNCING to Supabase...")
    result = sync_sqlite_to_supabase(db_path, supabase_url)
    _console(f">>> Supabase sync: runs={result.runs_upserted} versions={result.versions_upserted} current={result.current_upserted} failures={result.failures}")
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

    # Summary
    print_db_summary(args.db)

    # Supabase sync (default when SUPABASE_DATABASE_URL is set)
    if not args.no_supabase:
        synced = run_sync(args.db)
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
