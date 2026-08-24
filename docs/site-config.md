# 網站設定說明

本站點設定檔位於 `config/sites/<name>.yaml`，由 `config/schema/site.schema.json` 嚴格驗證。

## 最小範例

參考 `config/sites/example.yaml`，僅需填寫必填欄位即可運行。

## 完整範例

```yaml
name: "網站名稱"
base_url: "https://example.com"

limits:                        # 選用：各站覆寫全域 limits（config/settings.yaml）
  max_items: 50                # 最大爬取筆數，達到即停止
  max_pages: 5                 # 最大爬取頁數上限（唯一權威值，pagination 不再管頁數）
  stop_on_duplicate: true      # 遇到重複 URL 即停止
  timeout: 300                 # 整體爬取時間上限（秒）

request:
  headers:
    Referer: "https://example.com"

list_page:
  method: "GET"            # GET | POST，列表請求方法（預設 GET）
  type: "html"             # html | json（list_page 層為來源的繼承預設）
  categories:              # 選用：分類名稱 → 站內 URL 值
    "股市": "7251"
    "政治": "6645"
  category_default: "0"    # 選用：未指定 --category 時 {category} 的填值
  selectors:               # 選用：來源的繼承預設（items/link/link_attr/url_field/url_template）
    items: "article.news-item"
    link: "a"
    link_attr: "href"
  pagination:              # 選用：來源的繼承預設
    enabled: true
    start: 1
  sources:                 # 必填：至少一個列表來源，URL 內可含 {page}/{keyword}/{category} 佔位符
    - url: "https://example.com/news?page={page}&cat={category}"   # 預設來源（不含 {keyword}）
      type: "html"
      selectors:
        items: "article.news-item"
        link: "a"
        link_attr: "href"
    - url: "https://example.com/search?q={keyword}&page={page}"    # 關鍵字來源（含 {keyword}）
      type: "html"
      selectors:
        items: "article.news-item"
        link: "a"
        link_attr: "href"

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

## 爬取限制（limits）

三層優先權（逐欄位、高優先權覆寫）：**CLI 參數 > 站點 `limits`（選用）> 全域 `limits`（`config/settings.yaml`）> 程式碼預設**。

| 欄位 | 說明 |
|------|------|
| `max_items` | 收集達標即停止 |
| `max_pages` | 爬取列表頁數上限（唯一權威值，`pagination` 只管 `enabled`/`start`） |
| `stop_on_duplicate` | 遇到重複 URL 即停止；未開啟則跳過繼續 |
| `timeout` | 整體爬取逾時（秒） |

CLI 可臨時覆寫：`--max-items` / `--max-pages` / `--stop-on-duplicate`（與 `--no-stop-on-duplicate`）/ `--timeout`。

## 支援的 Selector 類型

| 類型 | 說明 |
|------|------|
| `text` | 擷取元素文字內容 |
| `datetime` | 解析日期時間字串，可指定 `datetime_format` |
| `attr` | 擷取指定 HTML 屬性值 |

Selector 亦支援 `regex` 欄位，對擷取結果進行正規表達式比對與命名群組萃取。

## Schema 驗證

所有設定檔在載入時會透過 [JSON Schema](https://json-schema.org/) 進行嚴格驗證，欄位打錯或型別不符時會在載入階段直接拋出 `ConfigValidationError`，避免錯誤設定靜默進入執行階段。

- `config/schema/settings.schema.json`：驗證 `config/settings.yaml`
- `config/schema/site.schema.json`：驗證 `config/sites/*.yaml`

驗證內容包含：

- 必填欄位（如 site 的 `name`、`base_url`，settings 的 `app`、`engine`）
- 欄位型別與數值範圍（如 `engine.max_concurrency` 須為正整數）
- 枚舉值（如 `type` 僅允許 `html` / `json`、`engine.mode` 僅允許 `sync` / `async`）
- 未知欄位攔截（`additionalProperties: false`），打錯字會直接報錯
- site 的 `list_page.selectors` 會區分 HTML 與 JSON 兩種結構，混用即失敗
- `article_page` 的欄位設定物件依 `article_page.type` 區分（`html` 型必填 `selector`、`json` 型必填 `path`），混用即報錯

新增或修改網站設定後，可直接執行 `python main.py --site <site_id>`，若設定不符 schema 會在啟動時立即收到明確的錯誤訊息。

## 分類機制

每個站點可透過頂層 `category` 與 `tags` 區塊設定自動分類與標籤，兩者皆為選用。

### category（多值分類）

`sources` 的所有命中值**累加**成分類陣列（自動去重），可同時有多個分類（如科技、財經）；全部失敗時使用 `default`：

```yaml
category:
  sources:
    - type: "meta"                   # <meta name="section" content="股市">
      name: "section"
    - type: "url"                    # 從網址擷取（regex 第一個 group）
      regex: "/story/(\\d+)/"
      mapping:                       # 可選：值 → 顯示名
        "7251": "股市"
    - type: "selector"               # CSS selector（attr 預設 text；join 串接多匹配）
      selector: "a.breadcrumb-item"
      attr: "text"
      join: ">"
    - type: "keyword"                # 比對標題/內容，命中任一關鍵字即用該值
      rules:
        - keywords: ["台股", "股市"]
          value: "財經"
  default: "其他"
```

### category_normalization（跨站分類統一）

各站對同一主題可能用不同分類名（如「股市」與「金融」其實同屬財經）。在 `config/category_normalization.yaml` 設定全域對應表（`Settings` 載入 `settings.yaml` 時自動合併，兩處同時存在時以 `settings.yaml` 內的值優先），比對結果會同時存入 `normalized_category`，供跨站篩選使用：

```yaml
# config/category_normalization.yaml
"股市": "財經"
"金融": "財經"
"資通訊": "科技"
```

`category` 保留各站原始分類名，`normalized_category` 存放對應後的統一值；無對應時保留原值。

### tags（多值標籤）

全部來源的值累加成標籤陣列（自動去重）；`split` 可把單一字串拆成多個：

```yaml
tags:
  sources:
    - type: "meta"
      name: "news_keywords"
      split: ","
    - type: "keyword"
      rules:
        - keywords: ["台股"]
          value: "台股"
```

### 支援的來源類型

| type | 說明 |
|------|------|
| `url` | 從文章網址用 `regex` 擷取（第一個 group）；可選 `mapping` |
| `meta` | 讀取 `<meta>` 標籤的 `content`，用 `name` 或 `property` 指定 |
| `selector` | CSS selector 萃取（`attr` 預設 text；`join` 可串接多匹配） |
| `json_ld` | 解析第一個 `script[type="application/ld+json"]`，以 `path` 取值 |
| `list_data` | 從列表頁 JSON item（request meta 的 `list_data`）以 `path` 取值 |
| `article_json` | 從文章 JSON 回應以 `path` 取值 |
| `keyword` | 比對標題與內容的關鍵字規則，命中任一即回傳該 `value` |

每個來源都可選配 `mapping`（原始值 → 顯示名）。`category` 與 `tags` 皆為多值累加並自動去重，`category` 支援 `default` 兜底值；兩者皆支援 meta 來源的 `split` 分隔符。

## 搜尋與篩選

爬取前可透過 CLI 參數針對列表頁做關鍵字搜尋或分類篩選，皆為選用、可組合。站點須在 `list_page` 提供對應欄位。

### 佔位符

每個 `list_page.sources[*].url` 都支援三種佔位符：

| 佔位符 | 來源 | 說明 |
|--------|------|------|
| `{page}` | 分頁迴圈 | 由 `pagination` 控制；非分頁時填 `pagination.start` |
| `{keyword}` | `--keyword` | 未提供時填空字串 |
| `{category}` | `--category` | 查 `categories` 對應表填站內值；未提供時填 `category_default`（缺省空字串） |

### 來源選擇

爬蟲依「來源 URL 內實際出現的佔位符」判斷該來源支援哪些篩選，再依請求的 `--keyword` / `--category` 選擇來源，永遠優雅降級、不中斷爬取：

- **精確匹配**：有來源恰好支援所有請求的篩選（如兩者皆含 `{keyword}` 與 `{category}`）→ 優先採用。
- **超集**：無精確來源時，採用含 `{keyword}` 的來源（記 warning 忽略 `--category`）；再無則採用含 `{category}` 的來源（記 warning 忽略 `--keyword`）。
- **降級**：單一篩選請求會優先挑「不含另一個佔位符」的精確來源，避免帶出多餘篩選。
- **預設來源**：都不符合時回退到第一個不含 `{keyword}` 的來源（純列表、支援 `--category` 或兩者皆無）。

### 行為規則

- 單一來源的 `method`/`type`/`pagination` 直接覆蓋 list_page 層預設；`selectors` 為深合併（來源只需覆蓋 `url_template` 即可，`items`/`url_field` 等繼承 list_page 層）。
- 有 `--category` → 以名稱查 `categories` 表取得站內值；名稱不在表中記 warning 改用原始名稱。
- 同時指定 `--keyword` 與 `--category` 且無來源支援兩者 → 自動降級（關鍵字優先），不再整頁跳過。
