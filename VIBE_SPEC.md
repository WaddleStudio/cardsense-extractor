# CardSense Extractor — VIBE_SPEC

## Purpose
This repository implements the **data extraction and normalization pipeline**
for CardSense.

Its job is to convert raw promotion text into
**validated, versioned, normalized promotion records**.

---

## Scope (DO)
- Ingest raw promotion text (file-based or list-based)
- Extract structured fields (rule-based first)
- Normalize values and categories
- Validate against cardsense-contracts schema
- Version promotions and write to PostgreSQL

## Out of Scope (DO NOT)
- No recommendation logic
- No user-specific state
- No synchronous external API
- LLM usage is optional and pluggable (stub allowed)

---

## Required Architecture

extractor/
├─ ingest.py
├─ parse_rules.py
├─ normalize.py
├─ validate.py
├─ versioning.py
└─ load.py

models/
└─ promotion.py # Pydantic model aligned to contracts

jobs/
└─ run_sample_job.py

tests/
└─ fixtures/


---

## Pipeline Rules (Non-Negotiable)

1. Invalid data MUST NOT reach normalized tables
2. Every record MUST include:
   - promo_version_id
   - extractor_version
   - confidence
3. Partial extraction:
   - Explicit nulls
   - Reduced confidence
4. Raw promotion text MUST NOT be stored in normalized tables

---

## Versioning Rules

- Same promo_id + different raw_text_hash → new version
- Same hash + re-run → no-op or heartbeat
- Old versions are immutable

---

## Database Interaction Rules

- Write to staging first
- Promote to normalized only after validation
- Do not update existing normalized rows

---

## Success Criteria
- `run_sample_job.py` inserts at least:
  - 1 valid promotion
  - 1 rejected promotion
- All normalized records pass schema validation
- Logs clearly explain acceptance/rejection

---

## Agent Instructions
- You may only modify files in this repository
- Do NOT change contracts schema
- Prefer correctness and explainability over cleverness