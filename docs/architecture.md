# 架構說明

## 分層職責

| 層 | 模組 | 職責 |
|----|------|------|
| 入口 | `web_harvester/cli.py`（`main.py` 為相容薄層） | 解析 CLI、解析設定目錄、載入站點設定、建立 Settings 與 Engine |
| 設定 | `web_harvester/utils/config.py` | 載入 YAML、JSON Schema 驗證、合併 limits 與分類對照表 |
| 引擎 | `web_harvester/core/engine.py` | 佇列排程、重試、限制條件、儲存掛載 |
| 請求 | `web_harvester/core/http_client/` | HTTP 抽象層（`curl_cffi` 預設、`httpx` 備援） |
| 合規 | `web_harvester/core/robots.py` | robots.txt 解析、per-origin 快取與允許判定 |
| 爬蟲 | `web_harvester/crawler/site_crawler.py` | 來源選擇、URL/body 填值、列表與文章解析 |
| 分類 | `web_harvester/crawler/classifier.py` | 由 html / url / json / keyword 規則推導 category 與 tags |
| 解析 | `web_harvester/parsers/` | HTML 與 JSON 的通用抽取 |
| 儲存 | `web_harvester/storage/` | JSON 批次輸出與 SQLAlchemy 寫入 |

## 請求生命週期

```
web-harvester（或 python main.py）
  └─ resolve_config_dir(--config-dir / env / 向上尋找)  # 決定 config/ 位置
  └─ Settings()                      # config/settings.yaml + category_normalization.yaml
  └─ load_site_config(site)          # config/sites/<site>.yaml，Schema 驗證 fail-fast
  └─ build_engine(settings)          # 建立 HTTP client 與 storage backend
  └─ SiteCrawler(site_config, ...)   # 合併 limits、初始化 Classifier
  └─ engine.run(crawler)
       ├─ 載入已知 URL            # skip_seen_urls 開啟時 union 各 storage 的 known_urls()
       ├─ start_requests()           # 由 list_page.sources 產生第一個列表請求
       ├─ 佇列取請求 → 已知 URL 略過 → dry run 略過文章頁 → robots 檢查 → HTTP 取得回應 → callback 解析
       │    ├─ 回傳 Request          # 下一頁（is_article=False）或文章頁（is_article=True），入列
       │    └─ 回傳 Item             # 去重後寫入所有 storage
       └─ 達到 max_items / timeout / 重複即停止
```

`--dry-run` 只影響標記為 `Request.is_article` 的請求：列表頁照常抓取並解析，文章頁在發出請求前即跳過，
計數記在 `skipped_articles`，因此可以在不寫入任何資料的情況下驗證設定。

`--all-sites` 對每個站點各自建立一個 engine 與 crawler，因此儲存後端、去重狀態與統計互不干擾；
單一 SiteCrawler 的 `_selected_list_cfg` 快取與 `_current_source` 也不會跨站污染。

同步模式以 `deque` 搭配單執行緒迴圈，並在每次請求間套用 `download_delay`。
非同步模式以固定數量 worker 共用 `asyncio.Queue`，去重與停止條件透過 `stop_event` 收斂。

## 來源選擇（`_select_list_cfg`）

`list_page.sources` 的每個來源都是 self-contained（不繼承、不合併），依請求的關鍵字與分類挑選：

| 情境 | 選擇順序 |
|------|----------|
| 同時指定 keyword + category | 支援兩者 → 支援 keyword（略過 category）→ 支援 category（略過 keyword）→ 預設來源 |
| 只指定 keyword | 只含 `{keyword}` 的來源 → 任何支援 keyword 的來源 → 預設來源 |
| 只指定 category | 只含 `{category}` 的來源 → 任何支援 category 的來源 → 預設來源 |
| 未指定 | 第一個不含 `{keyword}` 的來源 |

判定依據是來源的 `url`、`body` 與 `json_body` 串接後是否含對應佔位符。
結果快取於 `_selected_list_cfg`，解析回應時可重新推導同一個來源，不需要額外的請求中介資料。

## 去重與增量設計

四層防護，職責互不重疊：

1. **跨執行層**（`_known_urls`）：`engine.skip_seen_urls` 開啟時，啟動階段 union 各 storage 的 `known_urls()`，已存的文章 URL 直接跳過、不發出請求。
2. **請求層**（`_request_key`）：`(method, url, body, json_body)`。
   只以 URL 去重會讓 POST offset 分頁的後續頁被誤判為重複，因此 body 與 json_body 一併納入鍵值。
3. **寫入層**：存入前以 `url` 查詢既有資料，存在即跳過。
4. **資料庫約束**：`url` 具 unique 約束，併發插入撞約束時捕獲 `IntegrityError` 並跳過。

`limits.stop_on_duplicate` 開啟時，遇到重複請求或已知 URL 即中止整輪爬取（適用於「最新 N 筆」情境）。

## robots.txt

`request.respect_robots`（預設 `true`）開啟時，引擎在送出請求前以 `RobotsPolicy.allowed()` 判定，
實作位於 `web_harvester/core/robots.py`：

- 以 origin 為快取單位，同一次執行對每個網域只抓一次 robots.txt。
- 4xx 視為無限制；5xx 或連線失敗記 warning 並跳過該 URL，且不快取失敗結果，下次執行重新嘗試。
- 拒絕時計入 `skipped by robots.txt`，不進入 HTTP 請求階段。
- `Crawl-delay` 不覆寫 `engine.download_delay`。

## 為什麼不用瀏覽器

多數新聞站點的列表與文章內容可直接從 HTML 或 JSON API 取得，主要障礙是 TLS 指紋與 header 檢查，
而不是 JavaScript 渲染。以 `curl_cffi` 模擬瀏覽器指紋可避開大部分封鎖，同時避免瀏覽器帶來的啟動成本與記憶體開銷。
需要 JS 渲染的站點不在支援範圍（見 README 已知限制）。

## 擴充點

- **新增站點**：只加 `config/sites/<name>.yaml`，同步確認 `config/schema/site.schema.json` 已涵蓋所需欄位。
- **新增 HTTP client**：實作 `web_harvester/core/http_client/base.py` 的 `BaseHttpClient`，並在 `factory.py` 註冊。
- **新增儲存後端**：實作 `web_harvester/storage/base.py` 的 `BaseStorage`，於 `build_engine` 掛載。
- **新增解析格式**：在 `web_harvester/parsers/` 增加實作，並於 `SiteCrawler` 依 `type` 分派。
