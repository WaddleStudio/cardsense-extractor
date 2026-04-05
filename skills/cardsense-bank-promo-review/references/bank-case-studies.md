# Bank Case Studies

Use these as anchor examples when reviewing future cards.

## Cathay CUBE

### Why it matters

CUBE is the clearest CardSense example of a benefit-plan switching card that now spans:

- plan catalog metadata
- corrected `category -> planId` mapping
- expanded subcategory coverage
- merchant-aware cluster promotions
- runtime tier handling
- scoped Supabase rollout

### What CardSense now handles well

- plan catalog metadata
- `category -> planId` mapping
- subcategory refinement such as `AI_TOOL`, `DRUGSTORE`, `RIDESHARE`, `EV_CHARGING`
- merchant-aware cluster promos via structured `conditions`
- conservative tier fallback with explicit `LEVEL_2` / `LEVEL_3` runtime input
- card-scoped Supabase sync for `CATHAY_CUBE`

### Current implementation pattern

Use:

- cluster promo plus merchant conditions

Examples:

- `AI_TOOL` promo with merchants like `CHATGPT`, `CLAUDE`, `CANVA`
- `SUPERMARKET` promo with chains like `PXMART`, `CARREFOUR`
- `AIRLINE` promo with merchants like `CHINA_AIRLINES`, `EVA_AIR`

### Main caution

`Level 1 / Level 2 / Level 3` means the same plan can produce different rates depending on user state.

Safe default:

- use `LEVEL_1` unless runtime tier is explicitly provided

### Frontend lesson

If the backend now supports merchant-aware and tier-aware recommendation, frontend should usually add:

- `merchantName` input or merchant chips
- tier selector
- clearer condition badges

## E.SUN Unicard

### Why it matters

Unicard is the strongest example of a card whose plan catalog fits the current model, but whose runtime recommendation can exceed current engine capabilities.

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
- some category and subcategory routing

### Main caution

CardSense currently lacks a native way to model:

- month-end final plan state
- merchant-slot configuration
- unlock or subscription state as runtime input

### Safe verdict

- often `compatible with approximation`
- or base promotions `CATALOG_ONLY` until runtime state is modeled

## Taishin Richart

### Why it matters

Richart is the best example of a card where payment rail, MCC, merchant recognition, and campaign wording all influence whether a reward is actually obtainable.

### Important traits

- many named plans
- short-term campaign overlays
- wallet or payment-rail dependence
- domestic vs overseas recognition rules
- airline or direct-booking restrictions
- restaurant or MCC-like semantics

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

### Safe verdict

- plan catalog is usually compatible
- many detailed bonuses need approximation or `CATALOG_ONLY`

## Reusable lesson

When a new bank card resembles:

- `CUBE`: think `tiered plan + merchant-aware cluster promo + scoped rollout`
- `Unicard`: think `runtime plan-state`
- `Richart`: think `rail / classification / routing sensitivity`

Use the closest case as your first review template.
