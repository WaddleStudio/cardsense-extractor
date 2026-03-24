# CardSense Extractor

CardSense 平台的資料擷取與正規化模組，負責把銀行官網的原始優惠資訊轉成可驗證、可版本化、可匯入 SQLite 的 normalized promotion dataset。

## 職責

**負責**：
- 擷取銀行信用卡優惠頁內容
- 將 raw text / page block 解析成結構化欄位
- 對齊 CardSense promotion contract
- 產生 `promoId`、`promoVersionId`、`rawTextHash`
- 驗證資料合法性並輸出 JSONL
- 匯入 SQLite 供 API 讀取 `promotion_current`
- 區分 `RECOMMENDABLE`、`CATALOG_ONLY`、`FUTURE_SCOPE`

**不負責**：
- REST API 或 recommendation ranking
- 前端展示
- Migration framework 或外部排程平台

## 技術棧

- Python 3.13+
- uv（套件與執行管理）
- Pydantic（schema 驗證）
- SQLite（資料儲存）
- Playwright + playwright-stealth（JS 挑戰頁面爬取，用於 CTBC）
- pytest

## 快速開始

```bash
cd cardsense-extractor
uv sync                                           # 安裝依賴

# 驗證
uv run pytest                                      # 單元測試
uv run python tests/verify_pipeline.py             # mock pipeline 驗證

# Real extraction
uv run python jobs/run_esun_real_job.py            # 玉山
uv run python jobs/run_cathay_real_job.py          # 國泰
uv run python jobs/run_taishin_real_job.py         # 台新（Cloudflare Browser Rendering）
uv run python jobs/run_fubon_real_job.py           # 富邦（Cloudflare Browser Rendering）
uv run python jobs/run_ctbc_real_job.py            # 中信（JSON API + Playwright）

# 匯入 SQLite
uv run python jobs/import_jsonl_to_db.py \
  --input outputs/fubon-real-*.jsonl \
  --db data/cardsense.db

# 一鍵全銀行提取 → 匯入 DB → 複製到 API
uv run python jobs/refresh_and_deploy.py
```

抽樣限制與自訂輸出路徑：

```bash
ESUN_REAL_LIMIT=5 uv run python jobs/run_esun_real_job.py
CATHAY_REAL_LIMIT=5 uv run python jobs/run_cathay_real_job.py
TAISHIN_REAL_LIMIT=3 uv run python jobs/run_taishin_real_job.py
FUBON_REAL_LIMIT=3 uv run python jobs/run_fubon_real_job.py
CTBC_REAL_LIMIT=5 uv run python jobs/run_ctbc_real_job.py
CARDSENSE_OUTPUT_JSONL=outputs/esun-check.jsonl uv run python jobs/run_esun_real_job.py
```

## 專案結構

```text
cardsense-extractor/
├── extractor/
│   ├── esun_real.py               # E.SUN extractor
│   ├── cathay_real.py             # Cathay extractor
│   ├── taishin_real.py            # Taishin extractor (Cloudflare Browser Rendering)
│   ├── fubon_real.py              # Fubon extractor (Cloudflare Browser Rendering)
│   ├── ctbc_real.py               # CTBC extractor (JSON API + Playwright)
│   ├── promotion_rules.py         # reward / category / condition heuristics
│   ├── html_utils.py              # HTML cleanup helpers
│   ├── ingest.py                  # mock 與 real page fetch entrypoint
│   ├── normalize.py               # normalize to contract fields
│   ├── parse_rules.py             # raw text → intermediate fields
│   ├── validate.py                # Pydantic validation layer
│   ├── versioning.py              # promoId / promoVersionId / hash
│   ├── load.py                    # JSONL writer
│   ├── db_store.py                # SQLite persistence helpers
│   └── page_extractors/
│       └── sectioned_page.py      # shared section / offer block extraction
├── jobs/
│   ├── run_real_bank_job.py       # shared runner for bank extractors
│   ├── run_esun_real_job.py       # E.SUN runner
│   ├── run_cathay_real_job.py     # Cathay runner
│   ├── run_taishin_real_job.py    # Taishin runner
│   ├── run_fubon_real_job.py      # Fubon runner
│   ├── run_ctbc_real_job.py       # CTBC runner
│   ├── run_sample_job.py          # mock pipeline runner
│   ├── import_jsonl_to_db.py      # JSONL → SQLite importer
│   ├── refresh_and_deploy.py      # 全銀行 extract → import → deploy 一鍵流程
│   ├── analyze_jsonl_output.py    # distribution / quality inspection
│   └── test_real_fetch.py         # real source connectivity smoke test
├── models/
│   └── promotion.py               # Promotion model
├── outputs/                       # generated JSONL outputs
├── sql/
│   └── cardsense_schema.sql       # SQLite schema
├── tests/
└── pyproject.toml
```

## 設計重點

### 資料流

```
銀行官網 → ingest → parse_rules → normalize → versioning → validate → load (JSONL) → import (SQLite)
```

### Shared Extraction Layer

- **`sectioned_page.py`**：section heading、subsection、offer block 的共用頁面抽取邏輯
- **`promotion_rules.py`**：reward detection、summary 組裝、condition inference、category / channel inference
- **`run_real_bank_job.py`**：各銀行共用的 real extraction runner，包括輸出檔命名、validation、summary 統計
- **`refresh_and_deploy.py`**：一鍵全銀行 extract → import DB → 複製到 API 的部署流程

### Bank-Specific Extractor

| 銀行 | Extractor | 擷取方式 |
|------|-----------|----------|
| E.SUN（玉山） | `esun_real.py` | HTML 頁面直接抓取 |
| CATHAY（國泰） | `cathay_real.py` | Model JSON 抽取 |
| TAISHIN（台新） | `taishin_real.py` | Cloudflare Browser Rendering + HTML |
| FUBON（富邦） | `fubon_real.py` | Cloudflare Browser Rendering + HTML |
| CTBC（中信） | `ctbc_real.py` | JSON API（creditcards.cardlist.json）+ Playwright（detail 頁）|

### Recommendation Scope

| Scope | 說明 |
|-------|------|
| `RECOMMENDABLE` | 可由單筆交易上下文 deterministic 判斷，進入推薦排名 |
| `CATALOG_ONLY` | 保留在卡片 catalog 展示，不進 ranking |
| `FUTURE_SCOPE` | 已抽取但 API 缺乏必要上下文，無法安全推薦（首刷、新戶、身份型等） |

### JSONL 版本化

- 同一 promotion 語義不變時，`promoVersionId` 應穩定
- 條件、回饋或有效期間變更時，產生新版本
- 下游元件以 JSONL / SQLite 正式欄位為準，不應自行猜測 raw text

### SQLite Schema

| Table | 用途 |
|-------|------|
| `promotion_versions` | 歷次 promotion version 資料 |
| `promotion_current` | 每個 `promoId` 的最新版本，供 API 查詢 |
| `extract_runs` | 每次抽取或匯入執行紀錄 |

匯入同一銀行的全量 JSONL 時，會先刷新該銀行在 `promotion_current` 的舊資料，再寫入最新版本。

## 與其他子專案的關係

- **cardsense-contracts**：提供 promotion schema，是本 repo normalize / validate 的契約來源
- **cardsense-api**：讀取本 repo 匯入後的 SQLite `promotion_current`

跨 repo 工作流：extraction → JSONL 分析 → 匯入 SQLite → 啟動 API 驗證

## 已知限制

- 銀行頁面結構可能改版，heuristic 需持續調整
- 部分活動屬於身份型、首刷型或分期型，目前只適合歸類為 `CATALOG_ONLY` 或 `FUTURE_SCOPE`
- Real extractor 依賴外部網站可用性，阻擋或內容重構都可能影響結果
- 優先處理 deterministic recommendation 所需欄位，不追求完整重建行銷文案
