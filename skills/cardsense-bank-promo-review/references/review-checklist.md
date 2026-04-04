# Review Checklist

Use this checklist when reviewing a benefit-plan card.

## Source

- official source page URL captured
- benefit validity dates captured
- official exclusions captured
- secondary source clearly separated from official source

## Benefit-plan metadata

- plan names identified
- switch cadence identified
- exclusive-group relationship identified
- subscription or paid unlock identified
- temporary plans separated from evergreen plans

## Promotion extraction

- stable base rewards separated from campaign rewards
- category/subcategory mapping proposed
- plan binding proposed
- exclusions captured
- caps / frequency / registration captured

## Compatibility review

- current schema can represent plan catalog
- current schema can represent base promotions
- runtime state missing items listed explicitly
- recommendation safety assessed

## Implementation

- `benefit-plans.json` update needed or not
- `benefit_plans.py` update needed or not
- subcategory expansion needed or not
- curated JSONL needed or not
- SQLite import plan decided

## Validation

- extractor tests run
- repository tests run when benefit plans changed
- DB row counts checked
- affected `plan_id` and `subcategory` values spot-checked

