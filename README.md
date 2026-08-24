# Web Harvester

一個基於設定檔驅動的新聞爬蟲框架，支援 HTML / JSON 頁面解析、同步 / 非同步執行模式，以及多種儲存後端。

## 功能特色

- **設定檔驅動**：透過 YAML 定義爬蟲行為，無需修改程式碼即可新增目標網站
- **雙執行模式**：支援同步（`sync`）與非同步（`async`）兩種模式
- **複合解析器**：可解析 HTML（BeautifulSoup）與 JSON 格式的列表頁與文章頁
- **多種儲存後端**：JSON 檔案、SQLite、PostgreSQL、MySQL（透過 SQLAlchemy）
- **分頁爬取**：自動依設定逐頁取得列表
- **重試機制**：可設定失敗請求的最大重試次數
- **彩色日誌**：透過 `colorlog` 輸出結構化日誌

## 專案結構

```
web-harvester/
├── main.py                  # 主程式進入點（CLI）
├── requirements.txt
├── config/
│   ├── settings.yaml       # 全域設定（引擎、日誌、儲存）
│   ├── category_normalization.yaml  # 跨站分類統一對應表（Settings 自動合併）
│   ├── schema/             # 設定檔驗證 JSON Schema
│   │   ├── settings.schema.json
│   │   └── site.schema.json
│   └── sites/
│       ├── example.yaml    # 範例網站設定
│       └── udn_news.yaml   # 聯合新聞網設定
├── docs/
│   └── site-config.md      # 網站設定完整說明
├── src/
│   ├── core/               # 核心引擎（Engine、Request、Response、Item）
│   ├── crawler/            # 爬蟲邏輯（BaseCrawler、SiteCrawler）
│   ├── parsers/            # 解析器（HTMLParser、JSONParser）
│   ├── storage/            # 儲存後端（JSON、Database）
│   └── utils/              # 工具函式（設定載入、日誌）
├── data/
│   └── json/               # JSON 輸出目錄
└── test/                   # 單元測試（pytest）
    ├── conftest.py
    ├── test_config.py
    ├── test_core.py
    ├── test_engine.py
    ├── test_logging.py
    ├── test_parsers.py
    ├── test_site_crawler.py
    └── test_storage.py
```

## 安裝

### 1. 建立虛擬環境

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
source .venv/bin/activate   # macOS / Linux
```

### 2. 安裝依賴套件

```bash
pip install -r requirements.txt
```

## 測試

使用 pytest（需在專案根目錄執行，路徑皆為相對根目錄）：

```bash
python -m pytest test
```

單元測試不連真實網路：engine 測試透過 monkeypatch `CrawlerEngine._process_sync` / `_fetch_async` 模擬回應；storage 測試使用 pytest 的 `tmp_path` 臨時目錄。涵蓋範圍：

- 設定載入與 JSON Schema 驗證（正反向）
- Request / Response / Item 資料結構
- HTML / JSON 解析器
- SiteCrawler 分頁、列表與文章解析
- 引擎 sync / async 模式的 `max_items` / `stop_on_duplicate` / `timeout` 限制
- 非 2xx HTTP 回應觸發重試、失敗後不解析
- JSON 與資料庫儲存後端

## 快速開始

### 列出可用站點

```bash
python main.py --list-sites
```

### 執行內建範例（聯合新聞網）

```bash
python main.py --site udn_news
```

### 更換目標網站

在 `config/sites/` 新增對應設定檔後，以 `--site` 指定站點 ID（設定檔名不含副檔名）：

```bash
python main.py --site your_site
```

### 關鍵字搜尋與分類篩選

若站點設定提供 `list_page.sources` 與 `list_page.categories`，可搭配 `--keyword` / `--category` 使用：

```bash
python main.py --site udn_news --keyword 台股
python main.py --site udn_news --category 股市
python main.py --site udn_news --keyword 台股 --category 股市   # 可組合
```

`--category` 傳站內分類「名稱」，由 `categories` 對應表轉成站內實際值；名稱不在表中時改用原始名稱。詳見下方「搜尋與篩選」小節。

### 以指令覆寫爬取限制（limits）

可透過 CLI 參數臨時覆寫爬取限制（僅本次執行生效，不寫回設定檔），適用於所有站點：

```bash
python main.py --site udn_news --max-items 50
python main.py --site udn_news --max-pages 5 --timeout 120
python main.py --site udn_news --no-stop-on-duplicate
```

| 參數 | 覆寫欄位 | 說明 |
|------|---------|------|
| `--max-items N` | `limits.max_items` | 收集達 N 筆即停止（>= 1） |
| `--max-pages N` | `limits.max_pages` | 爬取列表頁數上限（>= 1） |
| `--stop-on-duplicate` / `--no-stop-on-duplicate` | `limits.stop_on_duplicate` | 遇到重複 URL 是否停止 |
| `--timeout SEC` | `limits.timeout` | 整體爬取逾時（秒，> 0） |

爬取限制的最終值採「逐欄位、高優先權覆寫」的三層合併：**CLI 參數 > 站點 `limits`（選用）> 全域 `limits`（`config/settings.yaml`）> 程式碼預設**。未指定的欄位沿用較低層的值。

## 設定說明

### 全域設定（`config/settings.yaml`）

| 欄位 | 說明 | 預設值 |
|------|------|--------|
| `engine.mode` | 執行模式（`sync` / `async`） | `sync` |
| `engine.max_concurrency` | 非同步模式最大並行數 | `10` |
| `engine.request_timeout` | 請求逾時（秒） | `30` |
| `engine.download_delay` | 同一網域請求間隔（秒） | `1.0` |
| `engine.max_retries` | 失敗請求最大重試次數 | `3` |
| `request.user_agent` | 全域請求的 User-Agent | `web-harvester/1.0` |
| `request.verify_ssl` | 是否驗證 SSL 憑證（僅開發測試時關閉） | `true` |
| `limits.max_items` | 各站全域預設：最大爬取筆數，達到即停止 | `100` |
| `limits.max_pages` | 各站全域預設：最大爬取頁數上限 | `3` |
| `limits.stop_on_duplicate` | 各站全域預設：遇到重複 URL 即停止 | `false` |
| `limits.timeout` | 各站全域預設：整體爬取時間上限（秒） | `180` |
| `category_normalization` | 跨站分類統一對應表（原始名 → 統一值，定義於 `config/category_normalization.yaml`） | `{}` |
| `json_storage.enabled` | 是否啟用 JSON 輸出 | `true` |
| `json_storage.output_dir` | JSON 輸出目錄 | `data/json` |
| `database.enabled` | 是否啟用資料庫儲存 | `true` |
| `database.url` | 資料庫連線字串 | `sqlite:///data/articles.db` |
| `database.pool_size` | 連線池大小（僅非 SQLite backend 生效） | `5` |
| `database.max_overflow` | 連線池溢位上限（僅非 SQLite backend 生效） | `10` |

### 網站設定（`config/sites/<name>.yaml`）

最小範例請見 `config/sites/example.yaml`。完整欄位、範例與選項說明請見 [docs/site-config.md](docs/site-config.md)，包含：

- 完整 YAML 範例（含 `limits` 選用覆寫、`list_page` / `article_page` 全部欄位）
- Selector 類型與 `regex` 用法
- Schema 驗證規則

新增或修改網站設定後，可直接執行 `python main.py --site <site_id>`，若設定不符 schema 會在啟動時立即收到明確的錯誤訊息。

## 資料庫結構

資料存入 `articles` 資料表，主要欄位如下：

| 欄位 | 類型 | 說明 |
|------|------|------|
| `source` | String | 來源網站名稱 |
| `url` | String | 文章網址（唯一） |
| `title` | String | 標題 |
| `author` | String | 作者 |
| `published_at` | DateTime | 發布時間 |
| `content` | Text | 文章內容 |
| `category` | Text | 分類（JSON 陣列） |
| `normalized_category` | Text | 統一後分類（JSON 陣列，跨站比對用） |
| `tags` | Text | 標籤（JSON 陣列） |
| `crawler_at` | DateTime | 爬取時間（UTC） |
| `extra_data` | Text | 額外資料（JSON 格式） |

去重機制：寫入前先以 `url` 查詢是否已存在（`data.url` 優先於 `item.url`），存在則跳過；`url` 欄位另有 unique 約束做第二層防護，若併發插入撞約束會捕獲 `IntegrityError` 後跳過，不會中斷爬取。

## 分類與搜尋

分類（`category` / `tags`）、跨站統一（`category_normalization`）、搜尋與篩選（`{page}` / `{keyword}` / `{category}` 佔位符與來源選擇）等完整說明請見 [docs/site-config.md](docs/site-config.md)。

## 新增網站

1. 在 `config/sites/` 目錄下新增 `<site_name>.yaml`，參考 [config/sites/example.yaml](config/sites/example.yaml) 填寫各欄位。
2. 以 `--site` 指定站點 ID 執行：`python main.py --site <site_name>`。
3. 也可先用 `python main.py --list-sites` 確認站點已註冊。

## 依賴套件

| 套件 | 用途 |
|------|------|
| `requests` / `aiohttp` / `httpx` | HTTP 請求 |
| `beautifulsoup4` + `lxml` | HTML 解析 |
| `PyYAML` | 設定檔讀取 |
| `jsonschema` | 設定檔 Schema 驗證 |
| `SQLAlchemy` | 資料庫 ORM |
| `colorlog` | 彩色日誌輸出 |
| `celery` + `redis` | 非同步任務佇列（選用） |

## 待辦清單

- [ ] 整合 Celery 以支援分散式任務處理
- [ ] 設計與實作 Middleware 機制以增強爬蟲靈活性

## 授權

MIT License
