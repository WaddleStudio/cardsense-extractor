# CardSense Extractor

CardSense 的資料擷取與正規化 pipeline。

## 目前實作狀態
- 以 Python + `uv` 執行 sample / mock pipeline
- 使用 Pydantic 驗證 normalized promotion model
- 已對齊新版 promotion schema 與結構化 condition object
- 已提供玉山銀行 real extractor 第一版，支援卡列表抓取、卡詳頁解析與 JSONL 落檔
- 已將 section / block 頁面規則抽成 `page_extractors` 共用層，方便擴充第二家銀行
- 已新增國泰世華 real extractor skeleton，沿用共用 promotion / page extractor 模組

## 目錄
```text
cardsense-extractor/
├── extractor/
│   ├── ingest.py
│   ├── esun_real.py
│   ├── cathay_real.py
│   ├── page_extractors/
│   │   └── sectioned_page.py
│   ├── parse_rules.py
│   ├── normalize.py
│   ├── validate.py
│   ├── versioning.py
│   └── load.py
├── jobs/
│   ├── run_sample_job.py
│   ├── run_esun_real_job.py
│   ├── analyze_jsonl_output.py
│   └── test_real_fetch.py
├── models/
│   └── promotion.py
├── tests/
│   └── verify_pipeline.py
└── pyproject.toml
```

## Pipeline
1. `ingest.py` 提供 mock/raw promotion text
2. `parse_rules.py` 轉成 key-value 結構
3. `normalize.py` 對齊 contracts schema
4. `versioning.py` 產生 `promoId` / `promoVersionId` / `rawTextHash`
5. `validate.py` 用 Pydantic 驗證
6. `load.py` 將 normalized promotion 寫成 JSONL，方便比對與後續匯入

## 執行方式
```bash
uv run python tests/verify_pipeline.py
uv run python jobs/run_sample_job.py
uv run python jobs/test_real_fetch.py
uv run python jobs/run_esun_real_job.py
uv run python jobs/analyze_jsonl_output.py --input outputs/esun-v5-full.jsonl
```

## 共用抽取層
- `extractor/page_extractors/sectioned_page.py`：抽出 section heading、subsection 與 offer block 的頁面規則
- `extractor/promotion_rules.py`：抽出 reward、summary、conditions、category / channel inference 規則
- `extractor/esun_real.py`：保留玉山銀行專屬 URL、signals 與頁面設定
- `extractor/cathay_real.py`：第二家銀行 skeleton，可直接補 card list selector 與 heading 規則

## Real Extractor 輸出
- `jobs/run_esun_real_job.py` 預設會將結果寫到 `outputs/esun-real-<timestamp>.jsonl`
- 可用 `CARDSENSE_OUTPUT_JSONL` 指定輸出路徑
- 可用 `ESUN_REAL_LIMIT` 先做小量抽樣驗證

```bash
ESUN_REAL_LIMIT=5 uv run python jobs/run_esun_real_job.py
CARDSENSE_OUTPUT_JSONL=outputs/esun-check.jsonl uv run python jobs/run_esun_real_job.py
```

## SQLite Schema 與匯入流程
- DB schema 定義於 `sql/cardsense_schema.sql`
- `promotion_versions` 保存每次抽取到的版本資料
- `promotion_current` 保存每個 `promoId` 當前最新版本，供 API 查詢
- `extract_runs` 保存每次 JSONL 匯入紀錄
- 匯入同一銀行的全量 JSONL 時，會先刷新該銀行在 `promotion_current` 的舊資料，再寫入最新版，避免 current table 混入舊版本

### 匯入 JSONL 到 SQLite
```bash
uv run python jobs/import_jsonl_to_db.py --input outputs/esun-v4-full.jsonl --db data/cardsense.db
```

### 環境變數
- `CARDSENSE_INPUT_JSONL`: 指定輸入 JSONL
- `CARDSENSE_DB_PATH`: 指定 SQLite DB 路徑
- `CARDSENSE_RUN_ID`: 指定匯入 run id

匯入後可讓 API 直接讀取 `promotion_current`，不需要再依賴 mock `promotions.json`。

目前玉山實跑建議以最新的 `outputs/esun-v5-full.jsonl` 作為匯入來源。

若要比較 heuristic 收斂前後的分佈，可先重跑玉山 extractor，再用 `jobs/analyze_jsonl_output.py` 檢查 `OTHER` 與 `ALL` 的主要來源。
