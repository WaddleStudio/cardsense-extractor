# CardSense Extractor

CardSense 的資料擷取與正規化 pipeline。

## 目前實作狀態
- 以 Python + `uv` 執行 sample / mock pipeline
- 使用 Pydantic 驗證 normalized promotion model
- 已對齊新版 promotion schema 與結構化 condition object

## 目錄
```text
cardsense-extractor/
├── extractor/
│   ├── ingest.py
│   ├── parse_rules.py
│   ├── normalize.py
│   ├── validate.py
│   ├── versioning.py
│   └── load.py
├── jobs/
│   └── run_sample_job.py
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
6. `load.py` 模擬輸出載入結果

## 執行方式
```bash
uv run python tests/verify_pipeline.py
uv run python jobs/run_sample_job.py
```
