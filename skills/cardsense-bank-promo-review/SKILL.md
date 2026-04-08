---
name: cardsense-bank-promo-review
description: Review a bank credit-card rewards page for the CardSense project, assess compatibility with CardSense schemas and runtime logic, propose taxonomy and plan-mapping updates, classify promotions into recommendable versus catalog-only buckets, and prepare safe importer-friendly data updates for cards such as Cathay CUBE, E.SUN Unicard, and Taishin Richart.
---

# CardSense Bank Promo Review

Use this skill when working inside the CardSense workspace and the task is to review a bank card's rewards or benefit-plan page, extract reusable structure, or decide what should change in CardSense contracts, extractor logic, API runtime logic, frontend integration, and imported promotion data.

This skill is optimized for:

- benefit-plan switching cards such as `CATHAY_CUBE`, `ESUN_UNICARD`, and `TAISHIN_RICHART`
- comparing official bank pages with current CardSense schemas and runtime behavior
- deciding whether a rule is `RECOMMENDABLE`, `CATALOG_ONLY`, or `FUTURE_SCOPE`
- updating plan metadata, `category -> planId` mappings, and subcategory coverage
- preparing extractor-native or importer-friendly data updates
- validating safe SQLite and Supabase rollout scope for a specific bank or card
- reviewing and cleaning payment-condition quality before a bank-scoped sync

## Core Principles

- Official bank pages and PDFs are the source of truth.
- Secondary sources can help discover missing merchant lists or hidden structure, but must not become production truth without official confirmation.
- Keep `category` stable whenever possible and prefer refining `subcategory`.
- Favor conservative recommendation defaults when runtime state is unknown.
- Prefer extractor-native output over curated merge files once the desired shape is understood.
- When syncing online data, use scoped sync for the intended `bank_code` or `card_code` when possible.

## Outcome

Produce these outputs when applicable:

1. A compatibility verdict:
   `fully compatible`, `compatible with approximation`, or `catalog-only until schema/runtime changes`
2. A data-model gap list:
   what the current CardSense schema or engine cannot represent safely
3. Concrete implementation changes:
   `benefit-plans.json`, extractor mapping, taxonomy/subcategory updates, runtime/API/frontend implications, DB import, scoped sync plan, and validation steps

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
  - tier qualification state
  - registration state
  - spend progress / caps / milestone progress

### 3. Judge compatibility

Assess compatibility against:

- `cardsense-contracts/benefit-plan/benefit-plan.schema.json`
- `cardsense-contracts/promotion/promotion-normalized.schema.json`
- `cardsense-extractor/extractor/benefit_plans.py`
- `cardsense-extractor/models/promotion.py`
- `cardsense-api/src/main/java/com/cardsense/api/service/DecisionEngine.java`
- `cardsense-web/src/components/RecommendationForm.tsx`
- `cardsense-web/src/components/RecommendationResults.tsx`
- `cardsense-web/src/pages/CalcPage.tsx`

Use this rule of thumb:

- if a reward can be chosen and applied to a single transaction with stable conditions, it is often `RECOMMENDABLE`
- if it depends on month-end state, user-selected merchant slots, milestone completion, or opaque payment rails, it may require approximation or runtime-state extensions

If you need CardSense-specific field guidance, read:
- [references/cardsense-data-model.md](references/cardsense-data-model.md)

### 4. Taxonomy policy

Nine top-level categories: DINING, TRANSPORT, ONLINE, TRAVEL, OVERSEAS, SHOPPING, GROCERY, ENTERTAINMENT, OTHER.

Key distinctions:

- **TRAVEL** = domestic travel services (hotels, booking platforms, travel agencies)
- **OVERSEAS** = foreign spending only (海外刷卡回饋, OVERSEAS_IN_STORE)
- **TRANSPORT** includes AIRLINE, GAS_STATION, EV_CHARGING, PARKING
- **SHOPPING** includes HOME_LIVING
- **OTHER** is fallback only (GENERAL)

Subcategory→category remapping is enforced in `db_store.py` and `normalize.py` via `_SUBCATEGORY_CATEGORY_REMAP`. If you assign subcategory HOTEL, TRAVEL_PLATFORM, or TRAVEL_AGENCY, the category will be overridden to TRAVEL regardless of what the extractor returns. Same for AIRLINE→TRANSPORT, GAS_STATION→TRANSPORT, HOME_LIVING→SHOPPING, etc.

Prefer:

- preserving current `category`
- adding or refining `subcategory`
- only proposing a new top-level category when repeated product/API/UI needs cannot be represented safely by subcategory

Common pattern:

- `category` is the product/API spine
- `subcategory` captures bank-specific merchant or program detail
- when a user selects a specific `subcategory`, CardSense runtime should compare the matching scene together with `GENERAL` promos, not scene-only exact match

### 5. Merchant modeling policy

Prefer this progression:

1. stable cluster promo
2. cluster-specific `subcategory`
3. structured merchant conditions inside the promo

Do not immediately explode one merchant into one promo row unless:

- the bank page clearly treats each merchant as a standalone rule
- or the cluster form is too coarse for recommendation correctness

A good default is:

- one promo for `AI_TOOL`
- one promo for `SUPERMARKET`
- one promo for `AIRLINE`
- with `conditions` carrying merchants such as `CHATGPT`, `PXMART`, `CHINA_AIRLINES`

### 5.5. Payment-condition policy

Before treating payment rails as structured conditions, apply the payment review policy.

Use:

- [references/payment-condition-policy.md](references/payment-condition-policy.md)

Rule of thumb:

- keep payment conditions only when the bank copy clearly makes payment route a positive eligibility condition
- remove positive payment conditions when the bank copy says the route is excluded
- normalize aliases before reviewing result quality
- do not treat generic wallet app mentions as payment conditions

### 6. Plan-mapping policy

For benefit-plan cards:

- check whether current `PLAN_MAPPING` matches actual bank plan semantics
- check `PLAN_NAME_SIGNALS`
- check `PLAN_SUBCATEGORY_HINTS`

If a bank page says dining belongs to a different plan than current mapping, prefer fixing mapping rather than hiding the mismatch in summary text.

### 7. Scope policy

Classify each extracted rule into one of:

- `RECOMMENDABLE`
- `CATALOG_ONLY`
- `FUTURE_SCOPE`

The `classify_recommendation_scope` function in `promotion_rules.py` uses token matching:
- `FUTURE_SCOPE` tokens: 新戶, 首刷, 首次申辦, 核卡後, 保費, 壽險, 保險, etc.
- `CATALOG_ONLY` tokens: 道路救援, 機場接送, 貴賓室, 停車, 專屬禮遇, 禮賓服務, 接送服務, 借電券, 折扣券, 優惠券, 兌換碼, 抽獎, 名額, etc.

Note: generic "服務" and "禮遇" were removed as tokens (2026-04-08) because they caused false positives — e.g., "不含10%服務費" in dining promos, "海外禮遇" in cashback promos. Specific patterns like "禮賓服務", "接送服務" are used instead.

Prefer `CATALOG_ONLY` when:

- registration is required and likely missing from runtime state
- the user must pre-select merchant slots
- the plan is resolved at month-end rather than per-transaction
- the rule depends on payment-rail or MCC details CardSense cannot yet calculate safely
- the promo involves coupons, lottery, limited quantity, or non-deterministic benefits

### 8. Tier policy

For tiered switching cards such as `CATHAY_CUBE`:

- treat unknown runtime tier conservatively
- default recommendation to the safest base tier
- require explicit request/runtime state to unlock higher-tier calculation

Current CardSense policy:

- `CATHAY_CUBE` defaults to `LEVEL_1`
- `LEVEL_2` and `LEVEL_3` should be explicit runtime input

### 9. Implementation order

When asked to make changes, use this order:

1. update `benefit-plans.json`
2. update `benefit_plans.py`
3. expand `subcategory` enum/signals only if needed
4. update extractor-native card-specific parsing
5. add or refine tests
6. import to SQLite and validate results
7. perform scoped Supabase sync if rollout is intended
8. update frontend when new runtime inputs or result explanations are now meaningful

Use curated JSONL only when extractor-native output is still too coarse and you need a short-lived validation step.

### 10. Validation

At minimum, validate:

- extractor tests related to normalize, subcategory inference, and card-specific parsing
- API tests if runtime logic changed
- benefit-plan repository tests if plan metadata changed
- frontend build if request or result behavior changed
- SQLite rows for the affected `card_code`

Useful checks:

- count total promotions for the card in `promotion_current`
- count plan-bound promotions
- inspect `category`, `subcategory`, `plan_id`, `cashback_value`, and `conditions_json`
- spot-check merchant-aware conditions for representative rows
- spot-check payment-conditioned rows for false positives and alias consistency
- verify non-target cards are not affected by scoped sync

### 11. Safe sync policy

Before syncing to Supabase, explicitly check whether the sync path is:

- whole-table
- bank-scoped
- or card-scoped

If the intended rollout is only for one card, prefer scoped sync.

Example:

- `--sync-bank CATHAY --sync-card CATHAY_CUBE`

This matters when the same bank has many other cards already loaded in SQLite.

### 12. Frontend follow-up policy

When recommendation quality improves because of new runtime inputs or condition structure, check whether frontend should also change.

Typical follow-ups:

- add `merchantName` input or merchant chips
- add tier selector for tiered cards
- surface condition badges in recommendation results
- surface active plan hints more clearly
- if `/calc` or other compare flows expose `subcategory`, make sure merchant-scoped scenes such as `AI_TOOL`, `DELIVERY`, `AIRLINE`, or `SUPERMARKET` can also pass `merchantName` or clearly explain the limitation

If you need a step-by-step review template, read:
- [references/review-checklist.md](references/review-checklist.md)

If you are shipping a bank-wide cleanup or a card-by-card review rollout, use:
- [references/bank-review-rollout-playbook.md](references/bank-review-rollout-playbook.md)

If you want concrete examples and known edge cases for current CardSense target cards, read:
- [references/bank-case-studies.md](references/bank-case-studies.md)

If you want a fixed review deliverable format, use:
- [references/review-output-template.md](references/review-output-template.md)

## Bank-specific heuristics

### Cathay CUBE

- watch for `Level 1 / Level 2 / Level 3` tiered rates
- default recommendation should be conservative when runtime tier is unknown
- prefer merchant-aware cluster promos over immediately splitting into one promo per merchant
- use scoped sync when rolling out only `CATHAY_CUBE`
- frontend likely needs `merchantName`, `CUBE tier`, and visible condition badges

### E.SUN Unicard

- distinguish `簡單選`, `任意選`, `UP選`
- **百大指定消費** promos are now expanded into 3 plan-specific RECOMMENDABLE promos per cluster:
  - `ESUN_UNICARD_SIMPLE` (簡單選 3%, max 1,000/mo)
  - `ESUN_UNICARD_FLEXIBLE` (任意選 3.5%, max 1,000/mo)
  - `ESUN_UNICARD_UP` (UP選 4.5%, max 5,000/mo)
  - Plan rates and caps defined in `_UNICARD_HUNDRED_STORE_PLANS` in `esun_real.py`
- be careful with month-end final-plan settlement and user-selected merchant slots
- review subscription/task-unlock behavior separately from plan catalog metadata
- prefer `subcategory` cleanup before proposing new top-level taxonomy:
  - `樂園` / `遊樂園` / `麗寶` / `六福村` / `劍湖山` -> `ENTERTAINMENT` + `THEME_PARK`
  - `加油` / `中油` / `全國加油` / `台塑石油` / `台亞` / `福懋` -> `TRANSPORT` + `GAS_STATION`
  - `GoShare` / `WeMo` and similar shared-mobility terms -> `TRANSPORT` + `RIDESHARE`
- expect some rows to remain `OTHER` or `GENERAL` after safe cleanup:
  - first-purchase / new-card / welcome campaigns
  - insurance-premium / registration-heavy offers
  - broad coupon pages where CardSense cannot safely infer a durable merchant cluster
- after changing Unicard heuristics, rerun extractor and validate `ESUN_UNICARD` rows in SQLite rather than relying only on fixture tests

### CTBC (中國信託)

- CTBC pages are protected by F5 BIG-IP ASM; only Playwright with stealth can bypass (plain HTTP and Cloudflare Browser Rendering both blocked)
- card listing comes from JSON API (`creditcards.cardlist.json`), detail pages are AEM-rendered HTML
- general cashback cards (御璽卡 0.5%, 鈦金卡 0.5%) have base rewards that apply across all categories — use `expand_general_reward_promotions` to fan out into per-category rows
- CTBC co-brand cards (秀泰聯名卡, Global Mall聯名卡, 南紡購物中心聯名卡, 學學認同卡) often have only 1 extractable promotion because most benefits are merchant-specific perks not structured as cashback
- registration-heavy catalog offers (每月限量, 每戶加碼上限, 限量) should be downgraded to `CATALOG_ONLY`
- the additional benefits page (`cc_add_index.html`) contains service-type perks (airport lounge, parking, roadside assistance) — these are card features, not cashback promotions, and are not extracted
- targeted extraction supports specific card slugs via CLI or env var: `uv run python jobs/run_ctbc_targeted.py B_Cashback_Signature B_SLV`
- CTBC-specific refinement rules handle SOGO store promos, Hami Pay conditions, and e-commerce platform conditions (蝦皮/momo/Coupang/淘寶)
- after extraction, validate that general-reward cards have per-category fan-out rows (expect 7 rows for 6 domestic categories + overseas)

### Taishin (feature extractor pattern)

- Taishin cards use per-card feature extractors registered in a `builders` dict within `taishin_real.py`
- Each feature extractor function (e.g. `_extract_gogoro_feature_promotions`, `_extract_friday_feature_promotions`) adds manual promotions based on known card-specific rewards
- This pattern is useful when the card's detail page doesn't contain structured promotion data parseable by the generic extractor
- The same pattern has been adopted in `cathay_real.py` (Shopee, EVA, Dual Currency, Asia Miles) and `fubon_real.py` (Insurance, Lifestyle, Open Possible)
- Feature extractors use `_build_manual_promotion()` helper and should include accurate `valid_from`/`valid_until` dates
- Targeted extraction jobs (`run_taishin_targeted.py`) filter to specific cards and support extra promo URLs

### Taishin Richart

- distinguish benefit plans from short-term plan-specific campaigns
- watch payment rail, wallet, MCC, and domestic-vs-overseas rules
- do not over-promote rules that depend on transaction recognition details CardSense cannot yet model
- plan inference should prefer explicit plan-name signals over generic channel terms:
  - `玩旅刷` should not be overridden by generic `LINE Pay` / `台新Pay` / `行動支付` wording on travel pages
  - travel-platform pages such as `Hotels.com` / `Agoda` / `Booking` / `Trip.com` / `AsiaYo` / `AIRSIM` often belong to `TAISHIN_RICHART_TRAVEL`
- prefer these subcategory refinements when the official page is specific enough:
  - travel-platform pages -> `ONLINE` + `TRAVEL_PLATFORM`
  - `大筆刷` department-store style pages -> `SHOPPING` + `DEPARTMENT`
  - `天天刷` grocery / hypermarket pages -> `GROCERY` + `SUPERMARKET`
- some Richart rows may still remain coarse when the page mixes plan explanation with broad settlement text; document these separately instead of forcing a misleading subcategory

## Deliverable format

When reporting findings, prefer:

1. compatibility verdict
2. blocking schema/runtime gaps
3. safe implementation path
4. validation and rollout scope
5. optional frontend and follow-up improvements

## Skill maintenance

This repo contains a version-controlled copy of the skill under:

- `skills/cardsense-bank-promo-review`

If a local installed skill also exists under:

- `%USERPROFILE%\\.codex\\skills\\cardsense-bank-promo-review`

prefer linking the local skill path to the repo copy so only one version needs maintenance.
