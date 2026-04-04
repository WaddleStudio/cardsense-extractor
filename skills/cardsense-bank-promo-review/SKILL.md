---
name: cardsense-bank-promo-review
description: Review a bank credit-card rewards page for the CardSense project, assess compatibility with CardSense schemas and runtime logic, propose taxonomy and plan-mapping updates, classify promotions into recommendable versus catalog-only buckets, and prepare safe importer-friendly data updates for cards such as Cathay CUBE, E.SUN Unicard, and Taishin Richart.
---

# CardSense Bank Promo Review

Use this skill when working inside the CardSense workspace and the task is to review a bank card's rewards/benefit-plan page, extract reusable structure, or decide what should be changed in CardSense contracts, extractor logic, and SQLite-imported promotion data.

This skill is optimized for:

- benefit-plan switching cards such as `CATHAY_CUBE`, `ESUN_UNICARD`, and `TAISHIN_RICHART`
- comparing official bank pages with CardSense schemas and runtime behavior
- deciding whether a rule is `RECOMMENDABLE`, `CATALOG_ONLY`, or `FUTURE_SCOPE`
- updating plan metadata, `category -> planId` mappings, and subcategory coverage
- preparing importer-friendly JSONL or curated data patches

## Outcome

Produce these outputs when applicable:

1. A compatibility verdict:
   `fully compatible`, `compatible with approximation`, or `catalog-only until schema/runtime changes`
2. A data-model gap list:
   what the current CardSense schema or engine cannot represent safely
3. Concrete implementation changes:
   `benefit-plans.json`, extractor mapping, taxonomy/subcategory updates, curated JSONL, DB import, and validation

## Workflow

### 1. Source review

Prioritize official bank pages and PDFs as source of truth.

Secondary sources such as Money101 may be used only to:

- discover missing fields
- identify hidden benefit structures
- cross-check wording or merchant lists

Do not treat secondary sources as production truth unless the same fact is confirmed from official sources.

If source trust is important, read:
- [references/source-trust-policy.md](references/source-trust-policy.md)

### 2. Split the page into CardSense concepts

Break the source into these layers:

- `benefit plan metadata`
  - plan name
  - switching cadence
  - validity period
  - subscription requirement
  - exclusive group
- `base recommendable promotions`
  - stable, repeatable, deterministic enough for recommendation
- `campaign / coupon / milestone / welcome / registration-heavy offers`
  - likely `CATALOG_ONLY` or `FUTURE_SCOPE`
- `runtime-state requirements`
  - month-end selected plan
  - plan subscription state
  - merchant slot choices
  - registration state
  - spend progress / caps / milestone progress

### 3. Judge compatibility

Assess compatibility against:

- `cardsense-contracts/benefit-plan/benefit-plan.schema.json`
- `cardsense-contracts/promotion/promotion-normalized.schema.json`
- `cardsense-extractor/extractor/benefit_plans.py`
- `cardsense-extractor/models/promotion.py`
- `cardsense-api/src/main/java/com/cardsense/api/service/DecisionEngine.java`

Use this rule of thumb:

- if a reward can be chosen and applied to a single transaction with stable conditions, it is often `RECOMMENDABLE`
- if it depends on month-end state, user-selected merchant slots, milestone completion, or opaque payment rails, it may require approximation or runtime-state extensions

If you need CardSense-specific field guidance, read:
- [references/cardsense-data-model.md](references/cardsense-data-model.md)

### 4. Taxonomy policy

Default to keeping existing top-level `category` values stable.

Prefer:

- preserving current `category`
- adding or refining `subcategory`
- only proposing a new top-level category when repeated product/API/UI needs cannot be represented safely by subcategory

Common pattern:

- `category` is the product/API spine
- `subcategory` captures bank-specific merchant/program detail

### 5. Plan-mapping policy

For benefit-plan cards:

- check whether current `PLAN_MAPPING` matches actual bank plan semantics
- check `PLAN_NAME_SIGNALS`
- check `PLAN_SUBCATEGORY_HINTS`

If a bank page says dining belongs to a different plan than current mapping, prefer fixing mapping rather than hiding the mismatch in summary text.

### 6. Scope policy

Classify each extracted rule into one of:

- `RECOMMENDABLE`
- `CATALOG_ONLY`
- `FUTURE_SCOPE`

Prefer `CATALOG_ONLY` when:

- registration is required and likely missing from runtime state
- the user must pre-select merchant slots
- the plan is resolved at month-end rather than per-transaction
- the rule depends on payment-rail or MCC details CardSense cannot yet calculate safely

### 7. Implementation order

When asked to make changes, use this order:

1. update `benefit-plans.json`
2. update `benefit_plans.py`
3. expand `subcategory` enum/signals only if needed
4. add or refine tests
5. generate curated JSONL only when extractor-native output is not yet precise enough
6. import to SQLite and validate results

### 8. Validation

At minimum, validate:

- extractor tests related to normalize and subcategory inference
- benefit-plan repository tests if plan metadata changed
- SQLite rows for the affected `card_code`

Useful checks:

- count total promotions for the card in `promotion_current`
- count plan-bound promotions
- inspect `category`, `subcategory`, `plan_id`, and `cashback_value`

If you need a step-by-step review template, read:
- [references/review-checklist.md](references/review-checklist.md)

If you want concrete examples and known edge cases for current CardSense target cards, read:
- [references/bank-case-studies.md](references/bank-case-studies.md)

If you want a fixed review deliverable format, use:
- [references/review-output-template.md](references/review-output-template.md)

## Bank-specific review heuristics

### Cathay CUBE

- watch for `Level 1 / Level 2 / Level 3` tiered rates
- default recommendation should be conservative when runtime tier is unknown
- many “extra” offers belong in coupon/campaign layers, not base recommendation

### E.SUN Unicard

- distinguish `簡單選`, `任意選`, `UP選`
- be careful with month-end final-plan settlement and user-selected merchant slots
- review subscription/task-unlock behavior separately from plan catalog metadata

### Taishin Richart

- distinguish benefit plans from short-term plan-specific campaigns
- watch payment rail / wallet / MCC / domestic-vs-overseas rules
- do not over-promote rules that depend on transaction recognition details CardSense cannot yet model

## Implementation patterns

### When to update only plan metadata

Do this when the bank page only clarifies:

- plan names
- dates
- plan descriptions
- switch cadence
- subscription requirement

Typical file:

- `cardsense-api/src/main/resources/benefit-plans.json`

### When to update mapping and taxonomy

Do this when the source shows the current CardSense mapping is semantically wrong, for example:

- dining should map to a different plan
- grocery should no longer map to shopping
- a recurring merchant cluster needs a new `subcategory`

Typical files:

- `cardsense-extractor/extractor/benefit_plans.py`
- `cardsense-extractor/extractor/promotion_rules.py`
- `cardsense-extractor/models/promotion.py`

### When to use curated JSONL

Use curated JSONL only when:

- extractor-native parsing is still too coarse
- you need to validate a product direction quickly
- you can keep the curated additions narrowly scoped and clearly sourced

Do not treat curated JSONL as the preferred steady-state solution.
Prefer replacing it later with extractor-native output.

### When to ask for schema/runtime changes

Escalate schema/runtime gaps when recommendation correctness depends on:

- month-end final plan state
- merchant-slot selection
- task unlock status
- tier state not present in request payload
- payment rail, MCC, transaction country, or billing currency that CardSense cannot currently express

## Deliverable format

When reporting findings, prefer:

1. compatibility verdict
2. blocking schema/runtime gaps
3. safe implementation path
4. optional follow-up improvements

When possible, structure the written output using the review template so repeated reviews are comparable across banks and cards.

## Skill maintenance

This repo contains a version-controlled copy of the skill under:

- `skills/cardsense-bank-promo-review`

If a local installed skill also exists under:

- `%USERPROFILE%\\.codex\\skills\\cardsense-bank-promo-review`

prefer linking the local skill path to the repo copy so only one version needs maintenance.
