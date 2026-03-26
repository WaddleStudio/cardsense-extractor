# Design: Extractor → Supabase Sync

**Date:** 2026-03-26
**Status:** Approved

---

## Problem

The current deploy flow bakes a SQLite `.db` file into the Docker image. With `SupabasePromotionRepository` now live in `cardsense-api`, the prod API reads from Supabase — but the extractor still only writes to SQLite, so Supabase never gets populated.

---

## Approach

**SQLite-first dual-write (B):** The extractor continues writing to SQLite (unchanged). After each extraction run, a new sync step pushes all three tables from SQLite to Supabase via direct PostgreSQL connection (`psycopg2`). Copying the `.db` file to `cardsense-api` is no longer required for prod deployment.

```
refresh_and_deploy.py
  └── run_import()          (unchanged — writes to SQLite via db_store.py)
  └── sync_to_supabase()    (new — reads SQLite, upserts to Supabase)
```

---

## Files Changed

| File | Action |
|------|--------|
| `sql/supabase_schema.sql` | New — PostgreSQL DDL for all three tables |
| `extractor/supabase_store.py` | New — sync logic |
| `jobs/refresh_and_deploy.py` | Modified — add sync step, add `--no-supabase` flag |
| `pyproject.toml` | Modified — add `psycopg2-binary` dependency |
| `.env.example` | Modified — add `SUPABASE_DATABASE_URL` |

---

## Schema: `sql/supabase_schema.sql`

Mirrors `sql/cardsense_schema.sql` with these PostgreSQL-specific changes:

- `requires_registration`: `INTEGER` → `BOOLEAN` (required for `SupabasePromotionRepository.java` which calls `Boolean.TRUE.equals(rs.getObject(...))`)
- `cashback_value`: `NUMERIC` → `NUMERIC` (same)
- Date fields (`valid_from`, `valid_until`, `extracted_at`, `started_at`, etc.): kept as `TEXT` (ISO strings), matching how `SupabasePromotionRepository` parses them with `::date` cast
- Constraints: same PRIMARY KEY / UNIQUE / FOREIGN KEY structure, using PostgreSQL `ON CONFLICT DO UPDATE` syntax

---

## `extractor/supabase_store.py`

Single public function:

```python
@dataclass
class SyncResult:
    runs_upserted: int
    versions_upserted: int
    current_upserted: int
    failures: int

def sync_sqlite_to_supabase(sqlite_db_path: str, supabase_url: str) -> SyncResult
```

**Implementation:**
1. Open SQLite read-only; open psycopg2 connection to Supabase
2. Upsert in foreign-key order: `extract_runs` → `promotion_versions` → `promotion_current`
3. Convert `requires_registration` from SQLite INTEGER (0/1) to Python `bool` before inserting
4. Use `INSERT ... ON CONFLICT (pk) DO UPDATE SET ...` for idempotent upserts
5. Commit once per table; on any exception, rollback and accumulate failure count
6. Return `SyncResult`

**Error handling:** Per-row try/except — one bad row does not abort the whole table. Failures are counted and reported.

---

## `refresh_and_deploy.py` Changes

1. Load `SUPABASE_DATABASE_URL` from `.env` via `python-dotenv`
2. After `run_import()`, call `sync_to_supabase()` unless:
   - `--no-supabase` flag is set, or
   - `SUPABASE_DATABASE_URL` is not set (print warning, skip)
3. `deploy_db()` (copy `.db` to cardsense-api) is **removed from default flow**; it can be re-enabled with `--deploy-local` flag for local testing
4. Exit code: non-zero if sync failures > 0

**New CLI flags:**

| Flag | Meaning |
|------|---------|
| `--no-supabase` | Skip Supabase sync |
| `--deploy-local` | Copy `.db` to `cardsense-api/data/` (old behaviour) |
| `--no-deploy` | **Removed** — replaced by `--no-supabase` + absence of `--deploy-local` |

---

## Environment Variables

`.env` / `.env.example`:

```
SUPABASE_DATABASE_URL=postgresql://postgres:<password>@db.<project>.supabase.co:5432/postgres
```

Same credential used by `cardsense-api` (`cardsense.supabase.url` + `cardsense.supabase.password`).

---

## Testing

- Unit test `supabase_store.py` with a real SQLite fixture and a mocked psycopg2 connection
- `requires_registration` conversion: assert SQLite `1` → Supabase `True`, `0` → `False`
- Idempotency: running sync twice produces the same row count
- Integration test (optional, skipped in CI unless `SUPABASE_DATABASE_URL` set): full round-trip with live Supabase

---

## What Does NOT Change

- `db_store.py` — zero changes
- All bank runner jobs — zero changes
- `cardsense-api` — already done (`SupabasePromotionRepository`, `application-prod.properties`)
- SQLite remains the local dev source of truth
