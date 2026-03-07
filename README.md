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
├── run.py                  # 主程式進入點
├── requirements.txt
├── config/
│   ├── settings.yaml       # 全域設定（引擎、日誌、儲存）
│   └── sites/
│       ├── example.yaml    # 範例網站設定
│       └── udn_news.yaml   # 聯合新聞網設定
├── src/
│   ├── core/               # 核心引擎（Engine、Request、Response、Item）
│   ├── crawler/            # 爬蟲邏輯（BaseCrawler、SiteCrawler）
│   ├── parsers/            # 解析器（HTMLParser、JSONParser）
│   ├── storage/            # 儲存後端（JSON、Database）
│   └── utils/              # 工具函式（設定載入、日誌）
├── data/
│   └── json/               # JSON 輸出目錄
└── test/
    └── test.py
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

## 快速開始

### 執行內建範例（聯合新聞網）

```bash
python run.py
```

### 更換目標網站

編輯 [run.py](run.py)，將 `load_site_config` 的參數改為對應設定檔名稱（不含副檔名）：

```python
site_config = load_site_config("your_site")
```

## 設定說明

### 全域設定（`config/settings.yaml`）

| 欄位 | 說明 | 預設值 |
|------|------|--------|
| `engine.mode` | 執行模式（`sync` / `async`） | `sync` |
| `engine.max_concurrency` | 非同步模式最大並行數 | `10` |
| `engine.request_timeout` | 請求逾時（秒） | `30` |
| `engine.download_delay` | 同一網域請求間隔（秒） | `1.0` |
| `engine.max_retries` | 失敗請求最大重試次數 | `3` |
| `json_storage.enabled` | 是否啟用 JSON 輸出 | `true` |
| `json_storage.output_dir` | JSON 輸出目錄 | `data/json` |
| `database.enabled` | 是否啟用資料庫儲存 | `true` |
| `database.url` | 資料庫連線字串 | `sqlite:///data/articles.db` |

### 網站設定（`config/sites/<name>.yaml`）

```yaml
name: "網站名稱"
base_url: "https://example.com"

limits:
  max_items: 50          # 最大爬取筆數
  max_pages: 5           # 最大爬取頁數
  stop_on_duplicate: true
  timeout: 300

request:
  headers:
    Referer: "https://example.com"

list_page:
  url: "https://example.com/news?page={page}"
  type: "html"           # html | json
  selectors:
    items: "article.news-item"
    link: "a"
    link_attr: "href"
  pagination:
    enabled: true
    start: 1
    max_pages: 5

article_page:
  type: "html"
  selectors:
    title: "h1.article-title"
    content:
      type: "text"
      selector: "div.article-body"
      attr: "text"
    published_at:
      type: "datetime"
      selector: "time"
      attr: "text"
      datetime_format: "%Y-%m-%d %H:%M"
```

### 支援的 Selector 類型

| 類型 | 說明 |
|------|------|
| `text` | 擷取元素文字內容 |
| `datetime` | 解析日期時間字串，可指定 `datetime_format` |
| `attr` | 擷取指定 HTML 屬性值 |

Selector 亦支援 `regex` 欄位，對擷取結果進行正規表達式比對與命名群組萃取。

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
| `category` | String | 分類 |
| `tags` | String | 標籤（逗號分隔） |
| `crawler_at` | DateTime | 爬取時間（UTC） |
| `extra_data` | Text | 額外資料（JSON 格式） |

## 新增網站

1. 在 `config/sites/` 目錄下新增 `<site_name>.yaml`，參考 [config/sites/example.yaml](config/sites/example.yaml) 填寫各欄位。
2. 在 [run.py](run.py) 中呼叫 `load_site_config("<site_name>")`。
3. 執行 `python run.py`。

## 依賴套件

| 套件 | 用途 |
|------|------|
| `requests` / `aiohttp` / `httpx` | HTTP 請求 |
| `beautifulsoup4` + `lxml` | HTML 解析 |
| `PyYAML` | 設定檔讀取 |
| `SQLAlchemy` | 資料庫 ORM |
| `colorlog` | 彩色日誌輸出 |
| `celery` + `redis` | 非同步任務佇列（選用） |

## 待辦清單

- [ ] 整合 Celery 以支援分散式任務處理
- [ ] 設計與實作 Middleware 機制以增強爬蟲靈活性

## 授權

MIT License
