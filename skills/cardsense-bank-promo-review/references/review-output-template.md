# Review Output Template

Use this template when reviewing a new bank card or benefit-plan page for CardSense.

## 1. Review Target

- Bank:
- Card:
- Official source URL:
- Review date:
- Reviewer:

## 2. Executive Verdict

- Compatibility verdict:
  - `fully compatible`
  - `compatible with approximation`
  - `catalog-only until schema/runtime changes`
- Confidence:
- Recommended immediate action:

## 3. Benefit-Plan Summary

- Has benefit-plan switching: `yes/no`
- Plan names:
- Switch cadence:
- Exclusive group:
- Subscription or unlock requirement:
- Main validity period:
- Temporary or seasonal plans:

## 4. Base Reward Structure

- Default or base reward:
- Higher-tier reward logic:
- Tier or qualification requirements:
- Main reward caps:
- Frequency limits:
- Registration requirement:

## 5. Taxonomy Fit

- Recommended top-level categories:
- Recommended subcategories:
- Category or subcategory mismatches found:
- Need new category enum: `yes/no`
- Need only subcategory expansion: `yes/no`

## 6. Plan Mapping Fit

- Proposed `planId` values:
- Proposed `PLAN_MAPPING` updates:
- Proposed `PLAN_NAME_SIGNALS` updates:
- Proposed `PLAN_SUBCATEGORY_HINTS` updates:

## 7. Merchant Modeling Fit

- Cluster promos sufficient: `yes/no`
- Merchant-level conditions needed: `yes/no`
- Example merchant conditions:
- Need one-merchant-one-promo rows: `yes/no`

## 8. Promotion Scope Split

### Recommendable

- List stable, deterministic-enough rules here

### Catalog Only

- List displayable but unsafe-to-rank rules here

### Future Scope

- List rules blocked by schema/runtime gaps here

## 9. Blocking Schema / Runtime Gaps

- Missing runtime state:
- Missing request fields:
- Missing condition types:
- Engine behavior mismatch:
- Needed schema changes:

## 10. Frontend / UX Follow-up

- Need merchant input or merchant chips: `yes/no`
- Need tier selector: `yes/no`
- Need clearer condition badges: `yes/no`
- Need active-plan UX changes: `yes/no`

## 11. Data Source Trust Notes

- Official facts confirmed:
- Secondary-source-only facts:
- Facts that still require official confirmation:

## 12. Implementation Plan

- Update `benefit-plans.json`: `yes/no`
- Update `benefit_plans.py`: `yes/no`
- Expand `subcategory` enum or signals: `yes/no`
- Update card-specific extractor parser: `yes/no`
- Use curated JSONL temporarily: `yes/no`
- Re-run extractor for this bank: `yes/no`
- Import to SQLite: `yes/no`
- Scoped Supabase sync needed: `yes/no`

## 13. Validation Plan

- Tests to run:
- DB checks to run:
- Sync-safety checks to run:
- Manual spot checks:

## 14. Suggested Follow-up

- Product or UI follow-up:
- Schema follow-up:
- Extractor follow-up:
- API or runtime follow-up:
