# Payment Condition Policy

Use this policy when deciding whether a promo should keep, add, remove, or canonicalize `PAYMENT_METHOD` and `PAYMENT_PLATFORM`.

This policy exists because payment conditions directly affect recommendation filtering. Over-broad payment tagging causes false negatives, noisy `/calc` results, and misleading frontend filter behavior.

## Core rule

Only keep or add payment conditions when the bank copy clearly says the reward:

- requires a specific payment platform
- requires a payment-method family such as `行動支付`
- limits eligibility to a specific wallet / pay rail
- or explicitly grants a bonus for a specific payment route

If the copy does not clearly express one of the above, do not add payment conditions.

## Keep or add payment conditions when

Examples of positive wording:

- `使用 LINE Pay 付款享 5%`
- `綁定 Apple Pay / Google Pay / LINE Pay 享加碼`
- `以悠遊付消費回饋`
- `全支付首綁滿額禮`
- `指定行動支付享回饋`
- `玉山WALLET電子支付享加碼`

These should usually produce:

- `PAYMENT_PLATFORM=<specific platform>` when a concrete platform is named
- `PAYMENT_METHOD=MOBILE_PAY` when the bank only states a general mobile-pay concept or when a concrete mobile-pay platform is present and the grouping is useful

## Remove or avoid payment conditions when

Do not add payment conditions for these patterns:

- generic app promotion copy
- card application copy
- new-card welcome gifts
- first-swipe gifts
- general base rewards
- pages that merely list wallet support
- channel copy such as `玉山Wallet 卡友必備APP`
- statement / point-query app references

Examples:

- `首刷禮`
- `一般消費享 0.5%`
- `回饋點數明細詳見 玉山Wallet`
- `下載 App 查詢`

These should not create `PAYMENT_METHOD` or `PAYMENT_PLATFORM`.

## Negative wording policy

If the bank copy says a payment path is excluded, do not keep a positive payment condition for it.

Examples:

- `不適用 Apple Pay`
- `恕無法參加 LINE Pay 綁定支付`
- `Apple Pay、Google Pay、LINE Pay 等相關綁定行動載具支付恕無法參加`
- `不列入行動支付交易`

Preferred handling:

- remove positive `PAYMENT_PLATFORM` conditions for the excluded rails
- remove positive `PAYMENT_METHOD=MOBILE_PAY` if the sentence negates the whole mobile-pay path
- if needed later, model these in `excludedConditions`

## Canonical platform values

Keep platform values normalized across banks and extractors.

Current canonical examples:

- `LINE_PAY`
- `APPLE_PAY`
- `GOOGLE_PAY`
- `SAMSUNG_PAY`
- `JKOPAY`
- `ESUN_WALLET`
- `全支付`
- `悠遊付`
- `全盈_PAY`
- `IPASS_MONEY`
- `ICASH_PAY`
- `TWQR`

Alias cleanup examples:

- `街口支付` -> `JKOPAY`
- `JKOPay` -> `JKOPAY`
- `玉山WALLET電子支付` -> `ESUN_WALLET`
- `玉山 Wallet電子支付` -> `ESUN_WALLET`

Do not leave mixed aliases in production rows if one normalized value exists.

## Data-quality review questions

When reviewing a bank card page, ask:

1. Is this reward truly gated by a payment platform, or is the platform only mentioned in surrounding marketing copy?
2. Is the wording positive, negative, or neutral about the payment path?
3. Is the platform named concretely, or only as a broad family like `行動支付`?
4. Would keeping this payment condition improve recommendation correctness, or just narrow results incorrectly?
5. Does the extracted row also need `merchant`, `retail chain`, `subcategory`, or `channel` structure so payment is not the only modeled dimension?

## Safe default

If you are unsure whether payment is a true condition, prefer:

- no positive payment condition
- or `CATALOG_ONLY`

This is safer than polluting structured filters with payment noise.
