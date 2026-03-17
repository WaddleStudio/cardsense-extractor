# CardSense Extractor — VIBE_SPEC
### Aligned with CardSense-Spec.md v1.0 | Updated: 2026-03-18

## Purpose
This repository implements the **data extraction and normalization pipeline**
for CardSense.

Its job is to convert raw bank promotion text into
**validated, versioned, normalized promotion records** in PostgreSQL.

---

## Scope (DO)
- Scrape bank promotion pages (public pages only, respect robots.txt)
- Extract structured fields using LLM (offline, Gemini Flash)
- Normalize values against cardsense-contracts enums
- Validate against contracts schema
- Version promotions and write to PostgreSQL (staging → normalized)
- Log acceptance/rejection with clear reasons

## Out of Scope (DO NOT)
- No recommendation logic
- No user-specific state
- No synchronous external API
- No high-frequency scraping (respect bank ToS)

---

## Required Architecture

```
cardsense-extractor/
├── src/main/java/com/cardsense/extractor/
│   ├── scraper/
│   │   ├── BankScraper.java          ← Interface
│   │   ├── JsoupScraper.java         ← Static HTML (primary)
│   │   ├── PlaywrightScraper.java    ← SPA fallback
│   │   └── CloudflareCrawlClient.java ← Cloudflare /crawl API (evaluating)
│   ├── parser/
│   │   ├── PromotionParser.java      ← Interface
│   │   ├── GeminiFlashParser.java    ← Primary: Gemini Flash extraction
│   │   └── MistralOcrParser.java     ← Fallback: PDF/image scenarios
│   ├── normalizer/
│   │   └── PromotionNormalizer.java  ← Map raw values → contracts enums
│   ├── validator/
│   │   ├── SchemaValidator.java      ← Validate against contracts model
│   │   └── BusinessRuleValidator.java ← Domain-specific checks
│   ├── versioning/
│   │   └── VersionManager.java       ← Hash comparison, version assignment
│   └── loader/
│       ├── StagingLoader.java        ← Write to staging table
│       └── NormalizedPromoter.java   ← Promote validated records
├── src/main/java/com/cardsense/extractor/model/
│   └── RawPromotion.java             ← Internal model before normalization
├── src/main/java/com/cardsense/extractor/job/
│   └── RunSampleJob.java             ← End-to-end test job
├── src/main/resources/
│   ├── prompts/
│   │   └── extraction-prompt.txt     ← Gemini Flash prompt template
│   └── application.yml
├── src/test/
│   └── fixtures/
│       ├── ctbc-sample-raw.html
│       ├── ctbc-sample-expected.json
│       └── invalid-promo-text.txt
├── build.gradle.kts                  ← depends on cardsense-contracts
└── README.md
```

**Dependency:** `cardsense-contracts` via Maven Local / GitHub Packages

---

## Technology Stack

| Component | Choice | Reason |
|-----------|--------|--------|
| Language | Java 21 | Aligned with contracts + API; shared types |
| Framework | Spring Boot 4 (batch/scheduling) | Scheduling, DI, JPA integration |
| Scraping (static) | Jsoup | Fast, lightweight HTML parsing |
| Scraping (SPA) | Playwright-Java | Headless browser for dynamic pages |
| Scraping (evaluation) | Cloudflare `/crawl` API | Render-as-a-service; `render: false` for free tier |
| LLM (primary) | Gemini Flash (AI Studio) | Free tier; strong structured output |
| LLM (PDF fallback) | Mistral OCR 3 | PDF/image extraction scenarios |
| LLM (complex cases) | Gemini Pro (manual) | Difficult promo text, escalation |
| DB | PostgreSQL (Supabase) | Shared with API; JSONB for conditions |
| ORM | Spring Data JPA | Consistent with API repo |

---

## Pipeline Flow

```
Bank Website (HTML/PDF)
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ 1. SCRAPE                                                │
│    Jsoup (static) / Playwright (SPA) / Cloudflare        │
│    Output: raw HTML/text per bank promotion page          │
│    Rate limit: max 1 request/second per bank             │
│    robots.txt: MUST respect                              │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ 2. EXTRACT (LLM — offline only)                          │
│    Gemini Flash: raw text → structured JSON               │
│    Uses extraction-prompt.txt template                    │
│    Output: RawPromotion (internal model)                  │
│    On failure: log error, skip record, continue pipeline  │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ 3. NORMALIZE                                             │
│    Map free-text → contracts enums                        │
│    cashback_value: always percentage (3% = 3.00)          │
│    Dates: YYYY-MM-DD                                     │
│    Unknown category → OTHER + reduced confidence          │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ 4. VALIDATE                                              │
│    Schema check: all required fields present + typed      │
│    Business rules:                                       │
│      - valid_from < valid_until                          │
│      - cashback_value > 0                                │
│      - category is valid enum                            │
│      - confidence > 0                                    │
│    Invalid → log rejection reason, store in rejected table │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ 5. VERSION                                               │
│    Compute SHA-256 of source_text → raw_text_hash         │
│    Same promo_id + different hash → new version           │
│    Same hash + re-run → no-op (skip)                     │
│    Assign promo_version_id (UUID)                         │
│    Assign extractor_version tag                          │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│ 6. LOAD                                                  │
│    Write to staging table first (promotions_staging)      │
│    After validation pass → promote to promotions table    │
│    Never update existing normalized rows (append-only)    │
│    source_text stored in staging for audit trail          │
└─────────────────────────────────────────────────────────┘
```

---

## Pipeline Rules (Non-Negotiable)

1. **Invalid data MUST NOT reach normalized tables**
2. Every normalized record MUST include:
   - `promoVersionId` (UUID, immutable)
   - `extractorVersion` (string, e.g. "extractor-1.0.0")
   - `extractionModel` (string, e.g. "gemini-flash-2.0")
   - `confidence` (0.0–1.0)
   - `rawTextHash` (SHA-256)
3. Partial extraction handling:
   - Missing optional fields → explicit null
   - Reduced confidence (below 0.7 → flag for human review)
   - category unknown → map to OTHER
4. `sourceText` stored in staging table; normalized table stores `rawTextHash` + `sourceUrl` only
5. Scraping must be polite: respect robots.txt, max 1 req/sec/bank, no login-wall bypass

---

## LLM Extraction Prompt Template

File: `src/main/resources/prompts/extraction-prompt.txt`

```
你是信用卡優惠數據解析器。請將以下銀行促銷文字轉為 JSON。

規則：
1. 嚴格按照 schema，不要加入未明確提到的資訊
2. 不確定的欄位填 null
3. cashback_value 統一為百分比 (3% = 3.00)
4. 日期格式 YYYY-MM-DD
5. category 只能是: DINING, TRANSPORT, ONLINE, OVERSEAS, SHOPPING, GROCERY, ENTERTAINMENT, OTHER
6. frequency_limit 只能是: MONTHLY, QUARTERLY, YEARLY, ONCE, NONE
7. requires_registration: true 如果文字提到「需登錄」「需註冊」「需綁定」等

Schema:
{
  "card_name": string,
  "bank_code": string,
  "promotions": [{
    "title": string,
    "category": string,
    "cashback_type": "PERCENT" | "FIXED" | "POINTS",
    "cashback_value": number,
    "min_amount": number | null,
    "max_cashback": number | null,
    "frequency_limit": "MONTHLY" | "QUARTERLY" | "YEARLY" | "ONCE" | "NONE",
    "requires_registration": boolean,
    "valid_from": string,
    "valid_until": string,
    "conditions": [string],
    "excluded_conditions": [string]
  }]
}

促銷文字:
---
{raw_text}
---
```

---

## Versioning Rules

- Same `promoId` + different `rawTextHash` → new version (new `promoVersionId`)
- Same hash + re-run → no-op or heartbeat log
- Old versions are **immutable** — never update
- `version` integer auto-increments for each new version of same logical promo

---

## Database Interaction Rules

- Write to `promotions_staging` first
- Promote to `promotions` only after full validation pass
- Do NOT update existing rows in `promotions` (append-only)
- Rejected records → `promotions_rejected` table with rejection reason
- `source_text` lives in staging only; normalized table has `raw_text_hash`

---

## Scraping Strategy (Sprint 1)

| Priority | Bank | Code | Approach | Notes |
|----------|------|------|----------|-------|
| 1 | 中國信託 | CTBC | Jsoup | Most promotions, recommended first target |
| 2 | 玉山銀行 | ESUN | Jsoup | |
| 3 | 台新銀行 | TAISHIN | Jsoup | |
| 4 | 國泰世華 | CATHAY | Jsoup/Playwright | Some SPA pages |
| 5 | 富邦銀行 | FUBON | Jsoup | |

**Cloudflare `/crawl` API evaluation:** Test with CTBC promotions page, `render: false` (free during beta). If successful, may replace Playwright for SPA banks. Paid tier ~$5/mo covers ~12,000 pages. ToS compliance obligations unchanged.

---

## Scheduling

- **Sprint 1 (manual):** `RunSampleJob.java` triggered manually
- **Phase 2:** Spring `@Scheduled` cron — daily at 08:00 UTC+8
- **Phase 3:** OpenClaw PromoWatcher Agent triggers pipeline via webhook

---

## Success Criteria
- `RunSampleJob.java` processes at least:
  - 1 bank's promotions successfully extracted and loaded
  - 1 rejected promotion with clear rejection reason logged
- All normalized records pass contracts schema validation
- Logs clearly explain acceptance/rejection for every record
- Same input run twice → no duplicate records (hash dedup works)

---

## Copyright & Legal Compliance
- Only scrape **publicly accessible** promotion pages
- Respect `robots.txt` for all bank domains
- No login-wall bypass or credential stuffing
- Rate limit: max 1 request/second per bank domain
- Store `source_url` for attribution and audit
- Bank ToS compliance must be verified per-bank before production scraping

---

## Agent Instructions
- You may only modify files in this repository
- Do NOT change contracts schema — consume it as dependency
- Prefer correctness and explainability over cleverness
- All LLM calls are offline/batch — never in a user-facing request path
- Log every pipeline step with structured logging (bank, promo count, pass/fail)
