# Supabase Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After each extraction run, sync all three SQLite tables (`extract_runs`, `promotion_versions`, `promotion_current`) to Supabase PostgreSQL so `cardsense-api` prod can read live promotion data.

**Architecture:** SQLite remains the local write target (unchanged). A new `supabase_store.py` reads from SQLite and upserts to Supabase via `psycopg2`. `refresh_and_deploy.py` calls the sync after import; `deploy_db()` (copy .db file) is removed from the default flow.

**Tech Stack:** Python 3.13, psycopg2-binary, sqlite3 (stdlib), python-dotenv (already in deps)

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `sql/supabase_schema.sql` | Create | PostgreSQL DDL for all three tables |
| `extractor/supabase_store.py` | Create | `sync_sqlite_to_supabase()` + helpers |
| `tests/test_supabase_store.py` | Create | Unit tests with mocked psycopg2 |
| `jobs/refresh_and_deploy.py` | Modify | Add sync step, `--no-supabase` / `--deploy-local` flags |
| `pyproject.toml` | Modify | Add `psycopg2-binary` dependency |
| `.env.example` | Modify | Document `SUPABASE_DATABASE_URL` |

---

## Task 1: Add psycopg2-binary + env var doc

**Files:**
- Modify: `pyproject.toml`
- Modify: `.env.example`

- [ ] **Step 1: Add psycopg2-binary to pyproject.toml**

Open `pyproject.toml`. Change:
```toml
dependencies = [
    "playwright>=1.49.0",
    "playwright-stealth>=1.0.6",
    "pydantic>=2.12.5",
    "pytest>=9.0.2",
    "python-dotenv>=1.1.0",
    "requests>=2.32.0",
]
```
To:
```toml
dependencies = [
    "playwright>=1.49.0",
    "playwright-stealth>=1.0.6",
    "psycopg2-binary>=2.9",
    "pydantic>=2.12.5",
    "pytest>=9.0.2",
    "python-dotenv>=1.1.0",
    "requests>=2.32.0",
]
```

- [ ] **Step 2: Document SUPABASE_DATABASE_URL in .env.example**

Current `.env.example`:
```
CLOUDFLARE_ACCOUNT_ID=your_account_id_here
CLOUDFLARE_API_TOKEN=your_api_token_here
```
New `.env.example`:
```
CLOUDFLARE_ACCOUNT_ID=your_account_id_here
CLOUDFLARE_API_TOKEN=your_api_token_here
# PostgreSQL connection string for Supabase (used by sync_to_supabase step)
SUPABASE_DATABASE_URL=postgresql://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres
```

- [ ] **Step 3: Install dependency**

```bash
uv sync
```
Expected: resolves and installs psycopg2-binary without errors.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml .env.example uv.lock
git commit -m "chore: add psycopg2-binary dep and document SUPABASE_DATABASE_URL"
```

---

## Task 2: Create Supabase PostgreSQL schema

**Files:**
- Create: `sql/supabase_schema.sql`

- [ ] **Step 1: Create sql/supabase_schema.sql**

```sql
-- Supabase (PostgreSQL) schema for cardsense promotion data.
-- Run once against your Supabase project to create the tables.
-- Key difference from cardsense_schema.sql (SQLite):
--   requires_registration is BOOLEAN (not INTEGER 0/1)

CREATE TABLE IF NOT EXISTS extract_runs (
    run_id TEXT PRIMARY KEY,
    bank_code TEXT,
    source TEXT NOT NULL,
    extractor_version TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    cards_processed INTEGER DEFAULT 0,
    promotions_loaded INTEGER DEFAULT 0,
    failures INTEGER DEFAULT 0,
    input_file TEXT,
    output_file TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS promotion_versions (
    promo_version_id TEXT PRIMARY KEY,
    promo_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    bank_code TEXT NOT NULL,
    bank_name TEXT NOT NULL,
    card_code TEXT NOT NULL,
    card_name TEXT NOT NULL,
    card_status TEXT,
    annual_fee INTEGER,
    apply_url TEXT,
    category TEXT NOT NULL,
    channel TEXT,
    cashback_type TEXT NOT NULL,
    cashback_value NUMERIC NOT NULL,
    min_amount INTEGER DEFAULT 0,
    max_cashback INTEGER,
    frequency_limit TEXT,
    requires_registration BOOLEAN NOT NULL DEFAULT FALSE,
    recommendation_scope TEXT NOT NULL DEFAULT 'RECOMMENDABLE',
    valid_from TEXT NOT NULL,
    valid_until TEXT NOT NULL,
    conditions_json TEXT NOT NULL,
    excluded_conditions_json TEXT NOT NULL,
    source_url TEXT NOT NULL,
    raw_text_hash TEXT NOT NULL,
    summary TEXT NOT NULL,
    extractor_version TEXT NOT NULL,
    extracted_at TEXT NOT NULL,
    confidence REAL NOT NULL,
    status TEXT NOT NULL,
    run_id TEXT REFERENCES extract_runs(run_id),
    raw_payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pv_promo_id ON promotion_versions (promo_id);
CREATE INDEX IF NOT EXISTS idx_pv_bank_card ON promotion_versions (bank_code, card_code);
CREATE INDEX IF NOT EXISTS idx_pv_valid_until ON promotion_versions (valid_until);

CREATE TABLE IF NOT EXISTS promotion_current (
    promo_id TEXT PRIMARY KEY,
    promo_version_id TEXT NOT NULL REFERENCES promotion_versions(promo_version_id),
    title TEXT NOT NULL DEFAULT '',
    bank_code TEXT NOT NULL,
    bank_name TEXT NOT NULL,
    card_code TEXT NOT NULL,
    card_name TEXT NOT NULL,
    card_status TEXT,
    annual_fee INTEGER,
    apply_url TEXT,
    category TEXT NOT NULL,
    channel TEXT,
    cashback_type TEXT NOT NULL,
    cashback_value NUMERIC NOT NULL,
    min_amount INTEGER DEFAULT 0,
    max_cashback INTEGER,
    frequency_limit TEXT,
    requires_registration BOOLEAN NOT NULL DEFAULT FALSE,
    recommendation_scope TEXT NOT NULL DEFAULT 'RECOMMENDABLE',
    valid_from TEXT NOT NULL,
    valid_until TEXT NOT NULL,
    conditions_json TEXT NOT NULL,
    excluded_conditions_json TEXT NOT NULL,
    source_url TEXT NOT NULL,
    raw_text_hash TEXT NOT NULL,
    summary TEXT NOT NULL,
    extractor_version TEXT NOT NULL,
    extracted_at TEXT NOT NULL,
    confidence REAL NOT NULL,
    status TEXT NOT NULL,
    run_id TEXT REFERENCES extract_runs(run_id),
    raw_payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pc_bank_category ON promotion_current (bank_code, category);
CREATE INDEX IF NOT EXISTS idx_pc_status_dates ON promotion_current (status, valid_from, valid_until);
```

- [ ] **Step 2: Commit**

```bash
git add sql/supabase_schema.sql
git commit -m "feat: add Supabase PostgreSQL schema DDL"
```

---

## Task 3: Write failing tests for supabase_store

**Files:**
- Create: `tests/test_supabase_store.py`

- [ ] **Step 1: Create the test file**

```python
"""Tests for extractor/supabase_store.py — psycopg2 is mocked throughout."""
from __future__ import annotations

import os
import sqlite3
import tempfile
from unittest.mock import MagicMock, call, patch

import pytest

from extractor.supabase_store import SyncResult, sync_sqlite_to_supabase


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sqlite_db():
    """Temporary SQLite DB with one row in each of the three tables."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE extract_runs (
            run_id TEXT PRIMARY KEY, bank_code TEXT, source TEXT NOT NULL,
            extractor_version TEXT, started_at TEXT NOT NULL, finished_at TEXT,
            status TEXT NOT NULL, cards_processed INTEGER DEFAULT 0,
            promotions_loaded INTEGER DEFAULT 0, failures INTEGER DEFAULT 0,
            input_file TEXT, output_file TEXT, notes TEXT
        );
        INSERT INTO extract_runs VALUES
            ('run1','TEST','test','1.0','2026-01-01T00:00:00',NULL,'SUCCESS',1,2,0,'in.jsonl',NULL,NULL);

        CREATE TABLE promotion_versions (
            promo_version_id TEXT PRIMARY KEY, promo_id TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '', bank_code TEXT NOT NULL,
            bank_name TEXT NOT NULL, card_code TEXT NOT NULL, card_name TEXT NOT NULL,
            card_status TEXT, annual_fee INTEGER, apply_url TEXT,
            category TEXT NOT NULL, channel TEXT, cashback_type TEXT NOT NULL,
            cashback_value NUMERIC NOT NULL, min_amount INTEGER DEFAULT 0,
            max_cashback INTEGER, frequency_limit TEXT,
            requires_registration INTEGER NOT NULL DEFAULT 0,
            recommendation_scope TEXT NOT NULL DEFAULT 'RECOMMENDABLE',
            valid_from TEXT NOT NULL, valid_until TEXT NOT NULL,
            conditions_json TEXT NOT NULL, excluded_conditions_json TEXT NOT NULL,
            source_url TEXT NOT NULL, raw_text_hash TEXT NOT NULL,
            summary TEXT NOT NULL, extractor_version TEXT NOT NULL,
            extracted_at TEXT NOT NULL, confidence REAL NOT NULL,
            status TEXT NOT NULL, run_id TEXT, raw_payload_json TEXT NOT NULL
        );
        INSERT INTO promotion_versions VALUES
            ('ver1','promo1','Test Promo','TEST','Test Bank','TEST_CARD','Test Card',
             'ACTIVE',0,NULL,'ONLINE',NULL,'PERCENT',3.0,0,NULL,NULL,
             1,'RECOMMENDABLE','2026-01-01','2026-12-31',
             '[]','[]','https://example.com','abc123','summary','1.0',
             '2026-01-01T00:00:00',0.9,'ACTIVE','run1','{}');

        CREATE TABLE promotion_current (
            promo_id TEXT PRIMARY KEY, promo_version_id TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '', bank_code TEXT NOT NULL,
            bank_name TEXT NOT NULL, card_code TEXT NOT NULL, card_name TEXT NOT NULL,
            card_status TEXT, annual_fee INTEGER, apply_url TEXT,
            category TEXT NOT NULL, channel TEXT, cashback_type TEXT NOT NULL,
            cashback_value NUMERIC NOT NULL, min_amount INTEGER DEFAULT 0,
            max_cashback INTEGER, frequency_limit TEXT,
            requires_registration INTEGER NOT NULL DEFAULT 0,
            recommendation_scope TEXT NOT NULL DEFAULT 'RECOMMENDABLE',
            valid_from TEXT NOT NULL, valid_until TEXT NOT NULL,
            conditions_json TEXT NOT NULL, excluded_conditions_json TEXT NOT NULL,
            source_url TEXT NOT NULL, raw_text_hash TEXT NOT NULL,
            summary TEXT NOT NULL, extractor_version TEXT NOT NULL,
            extracted_at TEXT NOT NULL, confidence REAL NOT NULL,
            status TEXT NOT NULL, run_id TEXT, raw_payload_json TEXT NOT NULL
        );
        INSERT INTO promotion_current VALUES
            ('promo1','ver1','Test Promo','TEST','Test Bank','TEST_CARD','Test Card',
             'ACTIVE',0,NULL,'ONLINE',NULL,'PERCENT',3.0,0,NULL,NULL,
             1,'RECOMMENDABLE','2026-01-01','2026-12-31',
             '[]','[]','https://example.com','abc123','summary','1.0',
             '2026-01-01T00:00:00',0.9,'ACTIVE','run1','{}');
    """)
    conn.commit()
    conn.close()

    yield db_path

    os.unlink(db_path)


@pytest.fixture()
def mock_pg():
    """Mock psycopg2.connect — returns a context-manager-aware connection mock."""
    with patch("extractor.supabase_store.psycopg2") as mock_psycopg2:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_psycopg2.connect.return_value = mock_conn
        mock_psycopg2.extras = MagicMock()
        yield mock_psycopg2, mock_conn, mock_cursor


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_sync_returns_sync_result(sqlite_db, mock_pg):
    result = sync_sqlite_to_supabase(sqlite_db, "postgresql://fake/db")
    assert isinstance(result, SyncResult)


def test_sync_counts_all_three_tables(sqlite_db, mock_pg):
    result = sync_sqlite_to_supabase(sqlite_db, "postgresql://fake/db")
    assert result.runs_upserted == 1
    assert result.versions_upserted == 1
    assert result.current_upserted == 1
    assert result.failures == 0


def test_sync_requires_registration_converted_to_bool(sqlite_db, mock_pg):
    """SQLite stores requires_registration as INTEGER 0/1; Supabase needs BOOLEAN."""
    mock_psycopg2, mock_conn, mock_cursor = mock_pg
    sync_sqlite_to_supabase(sqlite_db, "postgresql://fake/db")

    # Collect all rows passed to execute_values
    all_calls = mock_psycopg2.extras.execute_values.call_args_list
    # Find the promotion_versions upsert call (second table synced)
    versions_call = all_calls[1]
    rows = versions_call[0][2]  # positional arg: list of row tuples
    assert len(rows) == 1
    row = rows[0]
    # requires_registration is at index 17 in the promotion_versions column order
    requires_reg_value = row[17]
    assert requires_reg_value is True
    assert isinstance(requires_reg_value, bool)


def test_sync_requires_registration_zero_becomes_false(sqlite_db, mock_pg):
    """SQLite requires_registration=0 → PostgreSQL False."""
    # Update the fixture row to requires_registration=0
    conn = sqlite3.connect(sqlite_db)
    conn.execute("UPDATE promotion_versions SET requires_registration = 0")
    conn.execute("UPDATE promotion_current SET requires_registration = 0")
    conn.commit()
    conn.close()

    mock_psycopg2, mock_conn, mock_cursor = mock_pg
    sync_sqlite_to_supabase(sqlite_db, "postgresql://fake/db")

    all_calls = mock_psycopg2.extras.execute_values.call_args_list
    versions_call = all_calls[1]
    rows = versions_call[0][2]
    requires_reg_value = rows[0][17]
    assert requires_reg_value is False
    assert isinstance(requires_reg_value, bool)


def test_sync_commits_per_table(sqlite_db, mock_pg):
    """Each table upsert is followed by a commit."""
    mock_psycopg2, mock_conn, mock_cursor = mock_pg
    sync_sqlite_to_supabase(sqlite_db, "postgresql://fake/db")
    # Three tables → three commits
    assert mock_conn.commit.call_count == 3


def test_sync_closes_pg_connection_on_success(sqlite_db, mock_pg):
    mock_psycopg2, mock_conn, mock_cursor = mock_pg
    sync_sqlite_to_supabase(sqlite_db, "postgresql://fake/db")
    mock_conn.close.assert_called_once()


def test_sync_closes_pg_connection_on_error(sqlite_db, mock_pg):
    """pg connection must be closed even when execute_values raises."""
    mock_psycopg2, mock_conn, mock_cursor = mock_pg
    mock_psycopg2.extras.execute_values.side_effect = Exception("DB error")
    result = sync_sqlite_to_supabase(sqlite_db, "postgresql://fake/db")
    mock_conn.close.assert_called_once()
    assert result.failures > 0


def test_sync_upsert_order_runs_before_versions_before_current(sqlite_db, mock_pg):
    """Foreign-key constraint requires: extract_runs → promotion_versions → promotion_current."""
    mock_psycopg2, mock_conn, mock_cursor = mock_pg
    sync_sqlite_to_supabase(sqlite_db, "postgresql://fake/db")
    calls = mock_psycopg2.extras.execute_values.call_args_list
    assert len(calls) == 3
    # Verify SQL snippets identify the three tables in order
    assert "extract_runs" in calls[0][0][1]
    assert "promotion_versions" in calls[1][0][1]
    assert "promotion_current" in calls[2][0][1]
```

- [ ] **Step 2: Run tests to verify they fail (module not found)**

```bash
uv run pytest tests/test_supabase_store.py -v 2>&1 | head -20
```
Expected: `ModuleNotFoundError: No module named 'extractor.supabase_store'`

- [ ] **Step 3: Commit the tests**

```bash
git add tests/test_supabase_store.py
git commit -m "test: add failing tests for supabase_store sync"
```

---

## Task 4: Implement supabase_store.py

**Files:**
- Create: `extractor/supabase_store.py`

- [ ] **Step 1: Create extractor/supabase_store.py**

```python
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
        sqlite_conn.close()
        pg_conn.close()

    return result


def _sync_table(
    sqlite_conn: sqlite3.Connection,
    pg_conn: psycopg2.extensions.connection,
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
    except Exception:
        pg_conn.rollback()
        result.failures += len(rows)
        raise


def _to_pg_row(row: sqlite3.Row, cols: tuple[str, ...], bool_cols: frozenset[str]) -> tuple:
    return tuple(
        bool(row[col]) if col in bool_cols else row[col]
        for col in cols
    )
```

- [ ] **Step 2: Run tests**

```bash
uv run pytest tests/test_supabase_store.py -v
```
Expected: all 8 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add extractor/supabase_store.py
git commit -m "feat: implement supabase_store.sync_sqlite_to_supabase"
```

---

## Task 5: Update refresh_and_deploy.py

**Files:**
- Modify: `jobs/refresh_and_deploy.py`

- [ ] **Step 1: Read the current file top section**

The current `parse_args()` has `--no-deploy` and `--db`. We will:
- Remove `--no-deploy`
- Add `--no-supabase` (skip Supabase sync)
- Add `--deploy-local` (copy .db to cardsense-api — old default, now opt-in)
- Load `SUPABASE_DATABASE_URL` from dotenv

- [ ] **Step 2: Replace parse_args() in refresh_and_deploy.py**

Find and replace the `parse_args` function (lines ~59-71):

```python
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
```

- [ ] **Step 3: Add load_dotenv import and run_sync() function**

Add to the imports block at the top of the file (after the existing imports):
```python
from dotenv import load_dotenv
```

Add this new function after `deploy_db()`:

```python
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
```

- [ ] **Step 4: Replace the deploy block in main()**

Find the current deploy block in `main()` (around line 217):
```python
    # Deploy
    if not args.no_deploy:
        _console("")
        deployed = deploy_db(args.db)
        if deployed:
            _console("")
            _console(">>> NEXT STEPS:")
            _console("  cd ../cardsense-api")
            _console("  git add data/cardsense.db")
            _console('  git commit -m "data: refresh promotions DB"')
            _console("  git push    # triggers Railway auto-deploy")
    else:
        _console("\n>>> --no-deploy: skipped copying DB to cardsense-api")
```

Replace with:
```python
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
```

- [ ] **Step 5: Run a dry-run to verify no syntax errors**

```bash
uv run python jobs/refresh_and_deploy.py --help
```
Expected output includes `--no-supabase` and `--deploy-local` flags, no traceback.

- [ ] **Step 6: Commit**

```bash
git add jobs/refresh_and_deploy.py
git commit -m "feat: add Supabase sync step to refresh_and_deploy, replace --no-deploy with --no-supabase/--deploy-local"
```

---

## Task 6: Run full test suite + verify

**Files:** (none — verification only)

- [ ] **Step 1: Run all tests**

```bash
uv run pytest tests/ -v
```
Expected: all existing tests pass plus the 8 new `test_supabase_store` tests. Zero failures.

- [ ] **Step 2: Verify --no-supabase skips gracefully**

```bash
uv run python jobs/refresh_and_deploy.py --import-only --no-supabase --banks ESUN 2>&1 | grep -E "SKIP|sync|Supabase"
```
Expected output contains: `SKIP Supabase sync: SUPABASE_DATABASE_URL not set` or `--no-supabase: skipped Supabase sync`

- [ ] **Step 3: Final commit if any stray changes**

```bash
git status
# If clean: nothing to do
# If any changes: git add -p && git commit -m "chore: cleanup"
```
