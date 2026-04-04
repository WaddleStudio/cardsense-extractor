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

Choose `FUTURE_SCOPE` when:

- CardSense needs schema/runtime upgrades before safe use
- a rule is highly conditional or operationally fragile

