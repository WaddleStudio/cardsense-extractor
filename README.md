# CardSense Extractor

CardSense Extractor 是 CardSense 平台中的資料擷取與正規化模組，負責把銀行官網或 mock source 的原始優惠資訊，轉成可驗證、可版本化、可匯入 SQLite、可被 API 直接讀取的 normalized promotion dataset。

這個 repo 的核心目標不是做通用爬蟲，而是建立一條可維護的 extraction pipeline：

- 來源資料可追溯
- 規則可測試
- 輸出契約可驗證
- 版本差異可比對
- 可直接餵給 downstream recommendation API

## Repo 定位

本 repo 負責：

- 擷取銀行信用卡優惠頁內容
- 將 raw text / page block 解析成結構化欄位
- 對齊 CardSense promotion contract
- 產生 `promoId`、`promoVersionId`、`rawTextHash`
- 驗證資料合法性並輸出 JSONL
- 匯入 SQLite 給 API 讀取 `promotion_current`

本 repo 不負責：

- 提供 REST API
- recommendation ranking 與回應組裝
- 前端展示
- migration framework 或外部排程平台

## 目前狀態

- 使用 Python 3.13+ 與 `uv` 管理執行流程
- 已有 mock pipeline，可驗證 schema 與 normalization 規則
- 已有 E.SUN 與 Cathay 兩個 real extractor 路徑
- 已把部分抽取邏輯抽成 reusable page / promotion rules
- 已支援 JSONL 匯入 SQLite，供 `cardsense-api` 直接查詢
- 已區分 `RECOMMENDABLE`、`CATALOG_ONLY`、`FUTURE_SCOPE`

## 技術棧

- Python
- `uv`
- Pydantic
- SQLite
- pytest

## 專案結構

```text
cardsense-extractor/
├── extractor/
│   ├── cathay_real.py             # Cathay extractor
│   ├── db_store.py                # SQLite persistence helpers
│   ├── esun_real.py               # E.SUN extractor
│   ├── html_utils.py              # HTML cleanup / text extraction helpers
│   ├── ingest.py                  # Mock 與 real page fetch entrypoint
│   ├── load.py                    # JSONL writer
│   ├── normalize.py               # Normalize to contract fields
│   ├── parse_rules.py             # Parse raw text into intermediate fields
│   ├── promotion_rules.py         # Reward / category / condition heuristics
│   ├── validate.py                # Pydantic validation layer
│   ├── versioning.py              # promoId / promoVersionId / hash assignment
│   └── page_extractors/
│       └── sectioned_page.py      # Shared section / offer block extraction
├── jobs/
│   ├── analyze_jsonl_output.py    # Distribution / quality inspection
│   ├── import_jsonl_to_db.py      # JSONL -> SQLite importer
│   ├── run_cathay_real_job.py     # Cathay real extraction runner
│   ├── run_esun_real_job.py       # E.SUN real extraction runner
│   ├── run_real_bank_job.py       # Shared runner for bank extractors
│   ├── run_sample_job.py          # Mock pipeline runner
│   └── test_real_fetch.py         # Real source connectivity smoke test
├── models/
│   └── promotion.py               # Promotion model
├── outputs/                       # Generated JSONL outputs
├── sql/
│   └── cardsense_schema.sql       # SQLite schema
├── tests/
│   ├── test_cathay_real.py
│   ├── test_esun_real.py
│   ├── test_promotion_rules.py
│   ├── test_sectioned_page.py
│   └── verify_pipeline.py
└── pyproject.toml
```

## Quick Start

### 1. 安裝依賴

```bash
uv sync
```

### 2. 驗證基本 pipeline

```bash
uv run python tests/verify_pipeline.py
uv run pytest
```

### 3. 執行 mock sample job

```bash
uv run python jobs/run_sample_job.py
```

### 4. 驗證 real source 可讀

```bash
uv run python jobs/test_real_fetch.py
```

### 5. 執行 real extractor

```bash
uv run python jobs/run_esun_real_job.py
uv run python jobs/run_cathay_real_job.py
```

### 6. 匯入 SQLite

```bash
uv run python jobs/import_jsonl_to_db.py --input outputs/esun-v5-full.jsonl --db data/cardsense.db
```

## End-to-End 流程

完整資料流如下：

1. `ingest.py` 從 mock source 或 real page 取得原始內容
2. `parse_rules.py` 把原始內容轉成中介欄位
3. `normalize.py` 對齊 CardSense contract schema
4. `versioning.py` 根據語義內容產生版本識別碼
5. `validate.py` 以 Pydantic 驗證欄位完整性與型別
6. `load.py` 把合法 promotion 輸出成 JSONL
7. `jobs/import_jsonl_to_db.py` 把 JSONL 匯入 SQLite
8. `cardsense-api` 透過 SQLite repository 讀取 `promotion_current`

## 抽取設計

### Shared Extraction Layer

- `extractor/page_extractors/sectioned_page.py`
	用於 section heading、subsection、offer block 的共用頁面抽取邏輯。
- `extractor/promotion_rules.py`
	封裝 reward detection、summary 組裝、condition inference、category / channel inference。
- `jobs/run_real_bank_job.py`
	提供兩家銀行共用的 real extraction runner，包括輸出檔命名、validation、summary 統計與失敗處理。

### Bank-Specific Extractor

- `extractor/esun_real.py`
	以玉山銀行頁面結構與 section 規則為主。
- `extractor/cathay_real.py`
	以 Cathay model JSON 為主，從 component tree 擷取卡片資訊與 promotion candidate。

## Recommendation Scope 定義

- `RECOMMENDABLE`
	可由單筆交易上下文 deterministic 判斷的交易型優惠，可直接進入 `/v1/recommendations/card`。
- `CATALOG_ONLY`
	可保留在卡片 catalog 展示，但不進 recommendation ranking。
- `FUTURE_SCOPE`
	已抽取到資料，但目前 API 缺乏必要上下文，無法安全做 deterministic recommendation，例如首刷、新戶、身份型、保險型活動。

這個 scope 分類是 extractor 與 API 邊界的重要契約，避免把不完整條件的優惠誤送進排名引擎。

## Real Extractor 使用方式

### E.SUN

- 預設輸出：`outputs/esun-real-<timestamp>.jsonl`
- 抽樣限制：`ESUN_REAL_LIMIT`

```bash
ESUN_REAL_LIMIT=5 uv run python jobs/run_esun_real_job.py
CARDSENSE_OUTPUT_JSONL=outputs/esun-check.jsonl uv run python jobs/run_esun_real_job.py
```

### Cathay

- 預設輸出：`outputs/cathay-real-<timestamp>.jsonl`
- 抽樣限制：`CATHAY_REAL_LIMIT`

```bash
CATHAY_REAL_LIMIT=5 uv run python jobs/run_cathay_real_job.py
CARDSENSE_OUTPUT_JSONL=outputs/cathay-check.jsonl uv run python jobs/run_cathay_real_job.py
```

### Real Fetch Smoke Test

```bash
uv run python jobs/test_real_fetch.py
```

這個 smoke test 只驗證來源頁面可讀、內容大小合理，不等同於 promotion 品質驗收。

## JSONL 輸出與版本化

每筆 promotion 在輸出前會經過版本化與驗證，關鍵欄位包括：

- `promoId`
- `promoVersionId`
- `rawTextHash`
- `recommendationScope`
- `conditions`
- `excludedConditions`

設計重點：

- 同一個 promotion 的語義不變時，`promoVersionId` 應穩定
- 只要條件、回饋或有效期間發生語義變更，就應產生新版本
- 所有 downstream 元件都應以 JSONL / SQLite 中的正式欄位為準，不應再自行猜測 raw text

## SQLite 匯入流程

SQLite schema 定義在 `sql/cardsense_schema.sql`，主要 table 如下：

- `promotion_versions`
	保存歷次抽取出的 promotion version 資料。
- `promotion_current`
	保存每個 `promoId` 對應的最新版本，供 API 線上查詢。
- `extract_runs`
	保存每次抽取或匯入執行紀錄。

匯入同一銀行的全量 JSONL 時，會先刷新該銀行在 `promotion_current` 的舊資料，再寫入最新版本，避免 current table 混入舊版資料。

### 匯入指令

```bash
uv run python jobs/import_jsonl_to_db.py --input outputs/esun-v5-full.jsonl --db data/cardsense.db
```

### 匯入環境變數

- `CARDSENSE_INPUT_JSONL`：指定輸入 JSONL
- `CARDSENSE_DB_PATH`：指定 SQLite DB 路徑
- `CARDSENSE_RUN_ID`：指定 extract run id
- `CARDSENSE_IMPORT_SOURCE`：指定匯入來源標籤

## 測試策略

### 基本驗證

```bash
uv run python tests/verify_pipeline.py
```

用途：

- 驗證 mock source 可被 parse / normalize / validate
- 驗證非法資料確實會被 validation 擋下

### 單元測試

```bash
uv run pytest
uv run pytest tests/test_esun_real.py
uv run pytest tests/test_cathay_real.py
```

測試涵蓋：

- shared page extractor
- promotion rule heuristics
- E.SUN extractor
- Cathay model JSON parser

## 與其他 repo 的關係

- `cardsense-contracts`
	提供 promotion schema 與 taxonomy，是本 repo normalize / validate 的契約來源。
- `cardsense-api`
	會讀取本 repo 匯入後的 SQLite `promotion_current`，用於 `/v1/cards` 與 `/v1/recommendations/card`。

建議的跨 repo 工作流：

1. 在 extractor 執行 real extraction
2. 分析 JSONL 分佈與異常項
3. 匯入 SQLite
4. 啟動 API 並驗證 recommendation / catalog 行為

## 常用指令

```bash
uv sync
uv run python main.py
uv run python tests/verify_pipeline.py
uv run pytest
uv run python jobs/test_real_fetch.py
uv run python jobs/run_esun_real_job.py
uv run python jobs/run_cathay_real_job.py
uv run python jobs/analyze_jsonl_output.py --input outputs/esun-v5-full.jsonl
uv run python jobs/import_jsonl_to_db.py --input outputs/esun-v5-full.jsonl --db data/cardsense.db
```

## 已知限制

- 銀行頁面結構仍可能改版，heuristic 需持續調整
- 某些活動屬於身份型、首刷型或分期型優惠，目前只適合歸類為 `CATALOG_ONLY` 或 `FUTURE_SCOPE`
- real extractor 依賴外部網站可用性，網站阻擋、SSL 例外或內容重構都可能造成抽取結果變動
- 目前 priority 是 deterministic recommendation 所需欄位，不追求完整重建所有行銷文案

## 維護建議

- 新增銀行時，優先復用 `promotion_rules.py` 與 shared runner
- 新 heuristic 先補 test，再擴充 extractor 規則
- 大量調整分類規則時，先用 `analyze_jsonl_output.py` 比對前後分佈
- 進 API 前只信任 validation 通過且已 versioned 的正式輸出

## 建議驗收流程

1. `uv run pytest`
2. `uv run python jobs/test_real_fetch.py`
3. 小量抽樣跑 real extractor
4. 用 `analyze_jsonl_output.py` 檢查 category / scope 分布
5. 匯入 SQLite
6. 在 `cardsense-api` 驗證 catalog 與 recommendation endpoint
