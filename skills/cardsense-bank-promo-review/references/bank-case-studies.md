# Bank Case Studies

Use these as anchor examples when reviewing future cards.

## Cathay CUBE

### Why it matters

CUBE is a clean example of a benefit-plan switching card with:

- clear plan catalog
- high merchant diversity
- tiered reward levels
- some campaign-heavy noise around the base plans

### What CardSense handles well

- plan catalog metadata
- `category -> planId` mapping
- subcategory refinement for digital, travel, and essentials scenarios

### Main caution

`Level 1 / 2 / 3` means the same plan can produce different rates depending on user status.

Safe default:

- use conservative base/default logic unless runtime tier is known

### Good review output

- update `benefit-plans.json`
- correct `PLAN_MAPPING`
- add `subcategory` coverage such as `AI_TOOL`, `DRUGSTORE`, `RIDESHARE`, `EV_CHARGING`
- keep coupon boosts separate

## E.SUN Unicard

### Why it matters

Unicard is the best example of a card whose plan catalog fits the current model, but whose runtime recommendation can exceed current engine capabilities.

### Important traits

- `簡單選`
- `任意選`
- `UP選`
- month-end final selected plan affects monthly bonus
- `任意選` can depend on user-selected merchants
- `UP選` can be task-unlocked or e-point subscribed

### What CardSense handles well

- plan catalog metadata
- broad promotion display
- some category/subcategory routing

### Main caution

CardSense currently lacks a native way to model:

- month-end final plan state
- merchant-slot configuration
- unlock/subscription state as runtime input

Safe verdict:

- often `compatible with approximation`
- or base promotions `CATALOG_ONLY` until runtime state is modeled

## Taishin Richart

### Why it matters

Richart is the best example of a card where payment rail, MCC, merchant-recognition, and campaign wording all influence whether a reward is actually obtainable.

### Important traits

- many named plans
- short-term campaign overlays
- wallet/payment-rail dependence
- domestic vs overseas recognition rules
- airline/direct-booking restrictions
- restaurant/MCC-like semantics

### What CardSense handles well

- plan catalog metadata
- broad category mapping
- coarse channel and subcategory inference

### Main caution

A rule may look deterministic in marketing copy while actually depending on:

- wallet rail
- statement recognition
- merchant route
- issuer-defined classification

Safe verdict:

- plan catalog is usually compatible
- many detailed bonuses need approximation or `CATALOG_ONLY`

## Reusable lesson

When a new bank card resembles:

- `CUBE`: think `tiered plan`
- `Unicard`: think `runtime plan-state`
- `Richart`: think `rail / classification / routing sensitivity`

Use the closest case as your first review template.
