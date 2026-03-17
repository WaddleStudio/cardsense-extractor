# CardSense Extractor

CardSense 的資料擷取與正規化 pipeline。

本服務將台灣各銀行官網的信用卡優惠文字，透過 LLM（Gemini Flash，離線批次）轉換為結構化資料，經過驗證和版本控制後寫入 PostgreSQL。

## 本 repo 的職責
- 爬取銀行優惠頁面（Jsoup 處理靜態頁、Playwright 處理 SPA）
- 使用 Gemini Flash 離線擷取結構化資料（純批次，不在用戶請求路徑）
- 將原始值正規化為 `cardsense-contracts` 定義的列舉型別
- 依 contracts schema 和商業規則驗證記錄
- 版本控制（SHA-256 hash 去重，不可變版本）
- 將驗證通過的記錄寫入 PostgreSQL（staging → normalized）

## 本 repo 不做的事
- 不包含推薦邏輯（屬於 `cardsense-api`）
- 不包含用戶狀態管理
- 不提供對外同步 API
- 不高頻爬取（遵守各銀行 ToS）

## 技術棧
| 元件 | 選擇 | 說明 |
|------|------|------|
| 語言 | Java 21 | 與 contracts + API 共用型別 |
| 框架 | Spring Boot 4 | 排程、DI、JPA |
| 爬蟲（靜態） | Jsoup | 主要方案 — 快速輕量 |
| 爬蟲（SPA） | Playwright-Java | 動態銀行頁面備選 |
| 爬蟲（評估中） | Cloudflare `/crawl` API | Render-as-a-service 替代方案 |
| LLM（主力） | Gemini Flash (AI Studio) | 免費額度；結構化輸出能力強 |
| LLM（PDF 備選） | Mistral OCR 3 | PDF/圖片場景 |
| 資料庫 | PostgreSQL (Supabase) | 與 API 共用 |
| ORM | Spring Data JPA | 與 API repo 一致 |

## 專案結構

```
cardsense-extractor/
├── src/main/java/com/cardsense/extractor/
│   ├── scraper/            ← 銀行頁面爬蟲 (Jsoup / Playwright / Cloudflare)
│   ├── parser/             ← LLM 驅動的文字 → 結構化 JSON (Gemini Flash)
│   ├── normalizer/         ← 原始值 → contracts 列舉對應
│   ├── validator/          ← Schema 驗證 + 商業規則檢查
│   ├── versioning/         ← SHA-256 hash 去重、版本指派
│   └── loader/             ← staging → normalized（僅附加，不更新）
├── src/main/java/com/cardsense/extractor/model/
│   └── RawPromotion.java   ← 正規化前的內部模型
├── src/main/java/com/cardsense/extractor/job/
│   └── RunSampleJob.java   ← 端到端測試任務
├── src/main/resources/
│   ├── prompts/
│   │   └── extraction-prompt.txt   ← Gemini Flash prompt 模板
│   └── application.yml
├── src/test/fixtures/       ← 範例 HTML + 預期 JSON
├── build.gradle.kts         ← 依賴 cardsense-contracts
├── VIBE_SPEC.md
└── README.md
```

## Pipeline 流程

```
銀行官網 → 爬取 → LLM 擷取 → 正規化 → 驗證 → 版本控制 → 寫入
 (HTML)   (Jsoup) (Gemini Flash) (enums)  (schema)  (hash)    (PG)
```

1. **爬取**：抓取公開優惠頁面（遵守 robots.txt、每銀行每秒最多 1 次請求）
2. **擷取**：Gemini Flash 將原始文字轉為結構化 JSON
3. **正規化**：自由文字對應到 contracts 列舉（category、cashback type 等）
4. **驗證**：檢查必填欄位、型別、商業規則（日期、金額合理性）
5. **版本控制**：SHA-256 hash → 相同 hash = 跳過；新 hash = 新版本
6. **寫入**：先寫入 `promotions_staging` → 驗證通過後升級至 `promotions`

## Sprint 1 目標銀行

| 優先順序 | 銀行 | 代碼 | 爬取方式 |
|---------|------|------|---------|
| 1 | 中國信託 | CTBC | Jsoup |
| 2 | 玉山銀行 | ESUN | Jsoup |
| 3 | 台新銀行 | TAISHIN | Jsoup |
| 4 | 國泰世華 | CATHAY | Jsoup / Playwright |
| 5 | 富邦銀行 | FUBON | Jsoup |

## 執行方式

```bash
# 執行範例擷取任務（Sprint 1 手動觸發）
./gradlew bootRun --args='--job=sample'

# 完整每日擷取（Phase 2 以後）
# 由 Spring @Scheduled cron 在每日 08:00 UTC+8 自動執行
```

## 法律與合規
- 僅爬取**公開可存取**的優惠頁面
- 遵守所有銀行網域的 `robots.txt`
- 頻率限制：每銀行網域每秒最多 1 次請求
- 不繞過登入牆
- 儲存 `source_url` 用於來源追溯與審計
- 各銀行 ToS 合規須在正式爬取前逐一確認

## 關聯 Repository
| Repo | 角色 | 關係 |
|------|------|------|
| [cardsense-contracts](https://github.com/skywalker6666/cardsense-contracts) | 共用 schema 和列舉 | ⬆️ 上游依賴 |
| [cardsense-api](https://github.com/skywalker6666/cardsense-api) | 對外推薦 API | 讀取本 repo 產出的資料 |
| [fleet-command](https://github.com/skywalker6666/fleet-command) | 專案規格書庫 | CardSense-Spec.md |

---

*Owner: Alan | 隸屬 [CardSense](https://github.com/skywalker6666?tab=repositories&q=cardsense) 平台*
