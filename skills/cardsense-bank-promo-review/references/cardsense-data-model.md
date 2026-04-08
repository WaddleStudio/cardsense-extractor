# CardSense Data Model

Use these files as the current source of implementation truth:

- `cardsense-contracts/benefit-plan/benefit-plan.schema.json`
- `cardsense-contracts/promotion/promotion-normalized.schema.json`
- `cardsense-extractor/extractor/benefit_plans.py`
- `cardsense-extractor/models/promotion.py`
- `cardsense-api/src/main/java/com/cardsense/api/service/DecisionEngine.java`

## BenefitPlan layer

`benefit-plans.json` should describe plan catalog metadata only:

- `planId`
- `bankCode`
- `cardCode`
- `planName`
- `planDescription`
- `switchFrequency`
- `switchMaxPerMonth`
- `requiresSubscription`
- `subscriptionCost`
- `exclusiveGroup`
- `status`
- `validFrom`
- `validUntil`

What does not belong here:

- merchant slot choices
- tier-specific runtime state
- month-end selected plan state
- per-user unlock status

## Promotion layer

Use normalized promotions for concrete reward rules that can be evaluated or displayed.

Key fields:

- `category`: stable product/API grouping
- `subcategory`: detailed merchant/program grouping
- `planId`: bind rule to a benefit plan when applicable
- `conditions`: structured conditions when possible
- `excludedConditions`: exclusions and disallowed paths
- `recommendationScope`: use to protect deterministic behavior

## Runtime limits to remember

Current engine is strongest for:

- single-transaction reward comparison
- card/plan grouping via `planId` and `exclusiveGroup`
- stable category/subcategory matching

Current engine is weaker for:

- month-end plan resolution
- user-specific merchant slot configurations
- subscription/unlock states that are not part of request payload
- payment-rail recognition details unless already modeled as conditions

## Review decision rules

Choose `RECOMMENDABLE` when:

- a rule is stable
- requirements are visible and reasonably modelable
- reward can be determined for the transaction at evaluation time

Choose `CATALOG_ONLY` when:

- the rule is useful to display but unsafe to rank
- merchant slot or month-end state is unknown
- coupon/registration behavior exists but is not reliably present in request state
- the benefit is non-deterministic: coupons, lottery, limited quantity, voucher codes
- the benefit involves non-cashback perks: parking, roadside assistance, lounge access

Note: the automatic classifier (`classify_recommendation_scope`) uses token matching against the title+body text. It was refined (2026-04-08) to use specific service patterns instead of broad tokens like "服務" and "禮遇" that caused false positives on dining/hotel promos.

## Category taxonomy (updated 2026-04-08)

Nine top-level categories:

| Category | 中文 | Subcategories |
|----------|------|---------------|
| DINING | 餐飲 | RESTAURANT, CAFE, HOTEL_DINING, DELIVERY |
| TRANSPORT | 交通 | RIDESHARE, PUBLIC_TRANSIT, AIRLINE, GAS_STATION, EV_CHARGING, PARKING |
| ONLINE | 線上 | ECOMMERCE, SUBSCRIPTION, AI_TOOL, MOBILE_PAY, INTERNATIONAL_ECOMMERCE |
| TRAVEL | 旅遊 | HOTEL, TRAVEL_PLATFORM, TRAVEL_AGENCY |
| OVERSEAS | 海外 | OVERSEAS_IN_STORE, GENERAL |
| SHOPPING | 購物 | DEPARTMENT, WAREHOUSE, ELECTRONICS, DRUGSTORE, SPORTING_GOODS, APPAREL, HOME_LIVING |
| GROCERY | 生活採買 | SUPERMARKET, CONVENIENCE_STORE |
| ENTERTAINMENT | 娛樂 | MOVIE, THEME_PARK, SINGING, LIVE_EVENT, STREAMING |
| OTHER | 其他 | GENERAL (fallback) |

Key design decisions:
- **TRAVEL vs OVERSEAS**: TRAVEL is for domestic travel services (hotels, booking platforms, travel agencies). OVERSEAS is purely for foreign spending (海外刷卡回饋).
- **Cross-category VENUE matching**: The DecisionEngine bypasses category/subcategory checks when a request's merchantName matches a promo's VENUE condition. This allows hotel brands (e.g., MARRIOTT) to surface both DINING and TRAVEL promos.
- **Subcategory→category remap**: `db_store.py` and `normalize.py` contain `_SUBCATEGORY_CATEGORY_REMAP` that overrides extractor-assigned categories based on subcategory (e.g., HOTEL→TRAVEL, AIRLINE→TRANSPORT). This avoids touching individual bank extractors.

Choose `FUTURE_SCOPE` when:

- CardSense needs schema/runtime upgrades before safe use
- a rule is highly conditional or operationally fragile

