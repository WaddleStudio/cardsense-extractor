# CardSense Extractor — VIBE_SPEC
### Updated: 2026-04-01

## Purpose
This repository implements the extraction and normalization pipeline for CardSense.

## Current Stack
- Python 3.13+
- `uv` for environment and execution
- Pydantic v2 for schema validation
- Playwright + playwright-stealth for browser rendering (Taishin, Fubon, CTBC)
- Cloudflare Browser Rendering for anti-bot bypass (Taishin, Fubon)
- psycopg2 for Supabase PostgreSQL sync
- python-dotenv for environment management

## Supported Banks

| Bank | Code | Extraction Method |
|------|------|-------------------|
| E.SUN（玉山） | ESUN | HTML 頁面抽取 |
| Cathay（國泰） | CATHAY | Model JSON 抽取 |
| Taishin（台新） | TAISHIN | Cloudflare Browser Rendering + HTML 抽取 |
| Fubon（富邦） | FUBON | Cloudflare Browser Rendering + HTML 抽取 |
| CTBC（中信） | CTBC | Playwright + JSON API 抽取 |

## Current Architecture
```text
cardsense-extractor/
├── extractor/
│   ├── esun_real.py          # E.SUN real extractor
│   ├── cathay_real.py        # Cathay real extractor
│   ├── taishin_real.py       # Taishin real extractor
│   ├── fubon_real.py         # Fubon real extractor
│   ├── ctbc_real.py          # CTBC real extractor
│   ├── ingest.py
│   ├── parse_rules.py
│   ├── normalize.py
│   ├── validate.py
│   ├── versioning.py
│   ├── load.py
│   ├── db_store.py           # SQLite persistence
│   ├── supabase_store.py     # Supabase PostgreSQL sync
│   └── tag_plan_ids.py       # Plan inference tagging
├── jobs/
│   ├── run_esun_real_job.py
│   ├── run_cathay_real_job.py
│   ├── run_taishin_real_job.py
│   ├── run_fubon_real_job.py
│   ├── run_ctbc_real_job.py
│   ├── import_jsonl_to_db.py
│   └── refresh_and_deploy.py # One-click: extract → import → Supabase sync
├── sql/
│   └── supabase_schema.sql   # PostgreSQL DDL
├── models/
│   └── promotion.py
├── data/
│   └── cardsense.db          # Local SQLite database
├── outputs/                  # JSONL extraction outputs
├── tests/
└── pyproject.toml
```

## Data Pipeline
```
Bank Website → Extractor → JSONL → SQLite → Supabase (PostgreSQL)
                                     ↑
                          refresh_and_deploy.py orchestrates all steps
```

## Non-negotiable Rules
- Invalid data must not pass validation
- `conditions` and `excludedConditions` must be structured objects
- `promoVersionId` must change on semantic change
- `rawTextHash` must be deterministic from source text
- `cashbackValue` must be positive
- `validFrom` must be on or before `validUntil`
- Always use `uv run` for Python execution, never activate venv manually

## Environment Variables
- `CLOUDFLARE_ACCOUNT_ID` / `CLOUDFLARE_API_TOKEN` — for Taishin/Fubon browser rendering
- `SUPABASE_DATABASE_URL` — for PostgreSQL direct connection (psycopg2)
- `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` — for REST sync fallback
