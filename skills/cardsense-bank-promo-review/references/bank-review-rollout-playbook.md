# Bank Review And Rollout Playbook

Use this playbook when reviewing and shipping updates for one bank or one card.

It is designed for the CardSense workflow:

1. source review
2. extractor changes
3. tests
4. bank rerun
5. SQLite validation
6. scoped Supabase sync

## 1. Source review

- capture the official bank URL or PDF
- separate evergreen rewards from campaign copy
- mark plan metadata, merchant clusters, payment conditions, exclusions, and runtime-only requirements
- classify each promo into `RECOMMENDABLE`, `CATALOG_ONLY`, or `FUTURE_SCOPE`

## 2. Extractor review

Before editing, identify:

- card-specific parser file
- shared normalize / promotion-rules logic that may affect multiple banks
- tests covering normalize, subcategory inference, and bank-specific parsing

Common touch points:

- `extractor/<bank>_real.py`
- `extractor/normalize.py`
- `extractor/promotion_rules.py`
- `tests/test_<bank>_real.py`
- `tests/test_normalize.py`
- `tests/test_subcategory_conditions.py`

## 3. Payment-condition review

Apply:

- [payment-condition-policy.md](payment-condition-policy.md)

Checklist:

- remove false-positive payment rows
- canonicalize platform aliases
- keep payment only when wording is explicitly positive
- remove positive payment conditions for excluded rails
- check whether merchant / subcategory should also be structured

## 4. Card-by-card review

For each affected card:

- list promos that should lose payment conditions
- list promos that should keep payment conditions
- list promos that need better `merchant`, `subcategory`, or `channel`
- list promos that should move to `CATALOG_ONLY`
- note any runtime gaps that block safe recommendation

## 5. Validation before rerun

At minimum run targeted tests:

- `uv run python -m pytest tests/test_normalize.py`
- `uv run python -m pytest tests/test_subcategory_conditions.py`
- `uv run python -m pytest tests/test_<bank>_real.py`

Run broader extractor tests if shared rules changed across banks.

## 6. Bank rerun

Run the bank extractor only:

```powershell
uv run python jobs/run_<bank>_real_job.py
```

Confirm:

- cards processed count
- promotions loaded count
- no card failures

## 7. Inspect output JSONL

Spot-check the generated JSONL before import:

- payment-conditioned rows count
- key cards you intentionally changed
- `category`, `subcategory`, `channel`
- `conditions`
- `excludedConditions`
- `recommendationScope`

If shared logic changed, also sample non-target cards that are likely affected.

## 8. Import and sync

Prefer scoped rollout whenever possible.

Example:

```powershell
uv run python jobs/refresh_and_deploy.py --import-only --banks ESUN --sync-bank ESUN
```

If you are only rolling one card and the tool chain supports it, prefer the narrower scope.

## 9. SQLite verification

After import, verify:

- total `promotion_current` rows for the bank
- payment-conditioned row count
- key cards and promo titles
- whether suspicious rows still carry noisy conditions

Typical checks:

- count by `bank_code`
- count rows where `conditions_json` contains `PAYMENT_`
- group payment rows by `card_code`

## 10. Supabase verification

After sync, verify:

- sync scope was correct
- no table failures
- expected current-row count landed
- a quick live sample from `promotion_current` matches the reviewed output

## 11. Review deliverable

For each bank review, produce:

- what was wrong before
- what rules changed
- what cards still need manual follow-up
- what was synced
- what remains risky or approximate

If needed, format the review with:

- [review-output-template.md](review-output-template.md)
