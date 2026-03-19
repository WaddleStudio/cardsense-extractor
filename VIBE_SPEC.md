# CardSense Extractor — VIBE_SPEC
### Updated: 2026-03-19

## Purpose
This repository implements the extraction and normalization pipeline for CardSense.

## Current Stack
- Python 3.13+
- `uv` for environment and execution
- Pydantic v2 for schema validation

## Current Architecture
```text
cardsense-extractor/
├── extractor/
│   ├── ingest.py
│   ├── parse_rules.py
│   ├── normalize.py
│   ├── validate.py
│   ├── versioning.py
│   └── load.py
├── jobs/
│   └── run_sample_job.py
├── models/
│   └── promotion.py
├── tests/
│   └── verify_pipeline.py
└── pyproject.toml
```

## Non-negotiable Rules
- Invalid data must not pass validation
- `conditions` and `excludedConditions` must be structured objects
- `promoVersionId` must change on semantic change
- `rawTextHash` must be deterministic from source text
- `cashbackValue` must be positive
- `validFrom` must be on or before `validUntil`
