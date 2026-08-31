# Web Harvester

一個基於設定檔驅動的新聞爬蟲框架，支援 HTML / JSON 頁面解析、同步 / 非同步執行模式，以及多種儲存後端。

## 功能特色

- **設定檔驅動**：透過 YAML 定義爬蟲行為，無需修改程式碼即可新增目標網站
- **雙執行模式**：支援同步（`sync`）與非同步（`async`）兩種模式
- **TLS 指紋偽裝**：基於 `curl_cffi` 的瀏覽器指紋模擬（JA3/Akamai），支援 `chrome`/`safari`/`firefox`/`edge`  impersonate 與自訂 `ja3`/`akamai`，預設 `chrome131`，可切回 `httpx`
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
│   ├── site-config.md      # 網站設定完整說明
│   ├── global-config.md    # 全域設定完整說明
│   ├── logging.md          # 日誌設定說明
│   └── storage.md          # 儲存設定說明
├── src/
│   ├── core/               # 核心引擎（Engine、Request、Response、Item、HttpClient）
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

`--category` 傳站內分類「名稱」，由 `categories` 對應表轉成站內實際值；名稱不在表中時改用原始名稱。分類與篩選詳見 [docs/site-config.md](docs/site-config.md)，爬取限制覆寫詳見 [docs/global-config.md](docs/global-config.md)。

## 設定說明

### 全域設定（`config/settings.yaml`）

完整欄位與範例請見 [docs/global-config.md](docs/global-config.md)、[docs/logging.md](docs/logging.md) 與 [docs/storage.md](docs/storage.md)。

### 網站設定（`config/sites/<name>.yaml`）

最小範例請見 `config/sites/example.yaml`。完整欄位、範例與選項說明請見 [docs/site-config.md](docs/site-config.md)，包含：

- 頂層欄位速查與最小/完整 YAML 範例
- `limits` / `request` / `list_page`（繼承模型、sources、extract、pagination、categories）/ `article_page`（html/json、簡寫與物件寫法，`fields` + `as`）
- 分類與標籤（`category` / `tags` / `category_normalization`，4 種來源 `source: html|url|json|keyword` 與 `json.from` 對照）
- 搜尋與篩選（`{page}` / `{keyword}` / `{category}` 佔位符與來源選擇決策表）
- 驗證與除錯（常見 `ConfigValidationError` 對照）

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
| `curl_cffi`（預設）/ `httpx`（備援） | HTTP 請求與 TLS 指紋偽裝 |
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
