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
- **百大指定消費 plan-specific expansion**: each cluster now produces 3 RECOMMENDABLE promos (簡單選 3% / 任意選 3.5% / UP選 4.5%) with correct `planId`, `cashbackValue`, and `maxCashback`
- broad promotion display
- category and subcategory routing (19 clusters × 3 plans = 57 promos)

### Main caution

CardSense currently lacks a native way to model:

- month-end final plan state (百大 uses month-end plan for calculation)
- merchant-slot configuration (任意選 requires user to select up to 8 merchants)
- unlock or subscription state as runtime input (UP選 requires task completion or subscription)

### Safe verdict

- 百大 promos are now `RECOMMENDABLE` with plan-specific rates — the decision engine selects the best plan
- campaign overlays and task-unlocked bonuses remain `CATALOG_ONLY` or `FUTURE_SCOPE`

### Payment review lesson

E.SUN also exposed a reusable payment-data lesson for every future bank review:

- generic wallet app copy must not become `PAYMENT_PLATFORM`
- excluded payment rails must not remain as positive payment conditions
- alias cleanup matters because frontend filters and backend matching depend on normalized values
- after cleanup, only keep payment rows that are truly recommendation-relevant

Practical examples from the E.SUN cleanup:

- `街口支付` should normalize to `JKOPAY`
- `玉山WALLET電子支付` should normalize to `ESUN_WALLET`
- `玉山Wallet 卡友必備APP` should not create a payment condition
- `Apple Pay / Google Pay / LINE Pay 恕無法參加` should remove positive payment conditions instead of keeping them

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

## CTBC (中國信託)

### Why it matters

CTBC is the largest issuer in Taiwan by card count (47+ cards). It demonstrates how to handle a bank with heavy bot protection (F5 BIG-IP ASM) and a mix of general-cashback cards and co-brand cards with very different promotion structures.

### Important traits

- F5 BIG-IP ASM bot protection — only Playwright with stealth works; plain HTTP and Cloudflare Browser Rendering both blocked
- card listing available via JSON API (`creditcards.cardlist.json`), detail pages are AEM-rendered HTML
- general cashback cards (御璽卡, 鈦金卡) have base rewards that apply across all categories
- co-brand cards (秀泰, Global Mall, 南紡, 學學) tend to have merchant-specific perks not structured as cashback
- additional benefits page contains service perks (airport, parking, roadside assistance), not cashback promotions

### What CardSense handles well

- JSON API card discovery + Playwright detail page scraping
- general reward expansion: base cashback (e.g. 0.5%) fanned out into per-category rows (7 rows for 6 domestic + overseas)
- CTBC-specific condition refinement: SOGO store promos, Hami Pay, e-commerce platforms (蝦皮/momo/Coupang/淘寶)
- registration-heavy campaign downgrade to `CATALOG_ONLY`
- targeted extraction by card slug (CLI args or env var)

### Main caution

- co-brand cards often yield only 1 promotion because merchant-specific perks lack structured cashback data
- some cards (分期紅利卡) are primarily installment/points products where the "reward" is points redemption, not straightforward cashback
- the additional benefits page is dynamic (JS-loaded sections) and contains non-promotion card features — do not attempt to extract as promotions

### Current implementation pattern

- `run_ctbc_real_job.py` for full bank extraction (all cards)
- `run_ctbc_targeted.py` for specific cards by slug (supports CLI args, env var, or defaults)
- `_refine_ctbc_promotion()` handles CTBC-specific post-processing (SOGO, Hami Pay, e-commerce reshaping)
- `expand_general_reward_promotions()` fans out base cashback into per-category rows

### Extraction statistics (2026-04-06)

- Full extraction: 54 promotions across all CTBC cards
- Targeted extraction (8 cards): 26 promotions (15 RECOMMENDABLE, 11 CATALOG_ONLY)
- Category distribution: OVERSEAS 5, DINING 4, TRANSPORT 4, ONLINE 3, SHOPPING 3, GROCERY 3, ENTERTAINMENT 3, OTHER 1

## Cathay Non-CUBE Feature Extractors

### Why it matters

Cathay has 30 cards but many (Shopee, EVA, Asia Miles, Dual Currency) extract 0 promotions from generic parsing because their page JSON structure lacks structured promo components. Feature extractors fill this gap.

### Current implementation pattern

Feature extractors are registered in `feature_builders` dict within `extract_card_promotions()`. Each adds manual promotions via `_build_manual_promotion()`.

Cards covered:
- `CATHAY_SHOPEE`: 蝦皮站內4%蝦幣 + 站外0.5% + 外送交通旅遊7%
- `CATHAY_EVA`: 消費最優NT$10/哩 + Expedia/Hotels.com NT$8/哩 + 機上免稅品9折
- `CATHAY_DUAL_CURRENCY`: 海外消費最高1.5%回饋
- `CATHAY_ASIA_MILES`: 哩程加速器最優NT$10/里數

### MILES cashback type

`MILES` was added to `CashbackTypeEnum` to properly represent airline mileage rewards. The `value` field represents miles earned per NTD spent (e.g., 0.1 = NT$10 per mile).

### Extraction statistics (2026-04-08)

- CATHAY total: ~220 promos, ~160 RECOMMENDABLE, 30 cards in DB
- CUBE: 29p (27 REC) — plan-based extraction
- 現金回饋御璽卡: 10p (7 REC) — colorbanner extraction
- 世界卡: 71p (~56 REC) — classifier fix (`d31c495`) upgraded venue dining promos from CATALOG_ONLY
  - 專屬優惠 venue promos (hotels, restaurants) now RECOMMENDABLE with correct DINING category
  - 海外禮遇 3.5% cashback now RECOMMENDABLE

## Fubon Feature Extractors

### Why it matters

Many Fubon cards (Insurance, Lifestyle, Open Possible) have clear reward structures on their pages but the generic sectioned-page extractor misses them.

### Cards covered

- `FUBON_INSURANCE`: 一般消費0.7%現金回饋無上限 + 保費0.5%回饋
- `FUBON_LIFESTYLE`: 8大生活消費紅利5倍（NT$20=5點）
- `FUBON_OPENPOSSIBLE`: myfone購物最高5%回饋

### Extraction statistics (2026-04-07)

- FUBON total: 100 promos, 36 RECOMMENDABLE, 18 cards in DB
- J卡: 24p (10 REC), Costco: 7p (7 REC), DDM: 14p (7 REC)

## Taishin Feature Extractors

### Why it matters

Taishin cards with dedicated promo pages (Gogoro, friDay, 街口, PX_MART, etc.) contain card-specific rewards not captured by generic extraction.

### Cards covered

9 feature extractor families: JKOPay, PX_MART, friDay, Gogoro, Dual Currency, Infinite, Shin Kong (御璽/無限), Tsann Kuen

### Extraction statistics (2026-04-07)

- TAISHIN total: 45 promos, 20 RECOMMENDABLE, 12 cards
- Targeted extraction job: `run_taishin_targeted.py` with 12 priority cards and extra promo URLs

## E.SUN Re-extraction

### Why it matters

E.SUN full re-extraction (2026-04-07→08) dramatically improved coverage from 14→45 cards and 85→271→~350+ RECOMMENDABLE promotions, picking up many cards that were previously missing.

### Extraction statistics (2026-04-08)

- ESUN total: ~480 promos, ~350 RECOMMENDABLE, 45 cards in DB
- Unicard 百大: 57 RECOMMENDABLE (3 plans × 19 clusters, was 17 CATALOG_ONLY)
- Top cards: Unicard (57+ REC with 百大 expansion), 熊本熊卡 (18 REC), Pi拍兔 (15 REC), 世界卡 (14 REC)
- Classifier fix: profession card dining promos (會計師/建築師/醫師等) now RECOMMENDABLE

## Reusable lesson

When a new bank card resembles:

- `CUBE`: think `tiered plan + merchant-aware cluster promo + scoped rollout`
- `Unicard`: think `plan-specific promo expansion + runtime plan-state`
- `Richart`: think `rail / classification / routing sensitivity`
- `CTBC cashback`: think `general reward expansion + bot protection + targeted extraction`
- `CTBC co-brand`: think `sparse promotions + merchant-specific perks outside cashback schema`
- `Cathay Shopee / EVA / Asia Miles`: think `feature extractor for pages with unstructured promo data`
- `Fubon Insurance / Lifestyle`: think `feature extractor for clear rewards missed by generic parser`
- `Taishin card families`: think `per-card feature extractor + targeted extraction with extra promo URLs`

Use the closest case as your first review template.
