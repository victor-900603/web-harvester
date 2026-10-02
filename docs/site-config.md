# 網站設定說明

站點設定檔 `config/sites/<name>.yaml` 由 `config/schema/site.schema.json` 嚴格驗證（`additionalProperties: false`，啟動時 fail-fast，詳見 `src/utils/config.py:validate_config`）。所有欄位含型別、取值範圍與必填約束皆以該 Schema 為準；以下說明逐欄對應 Schema 定義，未列出的欄位寫入即報錯。

相關全域設定（`limits` / `request` / `category_normalization` / CLI 覆寫）見 [global-config.md](global-config.md)。

## 目錄

1. [頂層欄位速查](#1-頂層欄位速查)
2. [快速開始](#2-快速開始)
3. [limits](#3-limits)
4. [request](#4-request)
5. [list_page](#5-list_page)
6. [article_page](#6-article_page)
7. [分類與標籤](#7-分類與標籤)
8. [搜尋與篩選](#8-搜尋與篩選)
9. [驗證與除錯](#9-驗證與除錯)
10. [附錄：完整 Schema 對照範本](#10-附錄完整-schema-對照範本)

---

## 1. 頂層欄位速查

| 欄位 | 類型 | 必填 | 預設 | 說明 |
|------|------|------|------|------|
| `name` | `string` (`minLength: 1`) | 是 | - | 站點顯示名稱，同時作為儲存與日誌的 `source` 識別 |
| `base_url` | `string` (`pattern: ^https?://`) | 是 | - | 基底 URL，用於相對連結補全（`src/crawler/site_crawler.py:281` `urljoin`） |
| `limits` | `object` | 否 | 繼承 `config/settings.yaml:limits` | 單站覆寫全域限制，見 [§3](#3-limits) |
| `request` | `object` | 否 | `{}` | 僅套用本站的請求附加設定，見 [§4](#4-request) |
| `list_page` | `object` | 否 | `{}` | 列表頁設定；若提供則 `sources` 必填，見 [§5](#5-list_page) |
| `article_page` | `object` | 否 | - | 文章頁設定；未提供時列表 URL 直接輸出為 `link` 類型 Item，見 [§6](#6-article_page) |
| `category` | `object` | 否 | - | 單值分類（多來源累加、去重、失敗兜底），見 [§7](#7-分類與標籤) |
| `tags` | `object` | 否 | - | 多值標籤（多來源累加、去重、無兜底），見 [§7](#7-分類與標籤) |

> 約束：頂層 `additionalProperties: false`；`list_page.sources` 為列表頁唯一必填子欄位；`article_page` 若出現則 `type` 必填。

---

## 2. 快速開始

### 2.1 最小可運行範例

可直接複製為 `config/sites/my_site.yaml` 並執行 `python main.py --site my_site`：

```yaml
name: "example"
base_url: "https://example.com"

list_page:
  sources:
    - url: "https://example.com/news?page={page}"
      type: "html"
      extract:
        item_selector: "article.news-item"  # 每筆列表項容器
        link_selector: "a"                  # 容器內的連結元素
        link_attr: "href"                   # 連結屬性

article_page:
  type: "html"
  fields:
    title: "h1.article-title"
    content:
      as: "text"
      selector: "div.article-body"
      attr: "text"
```

### 2.2 完整範例（涵蓋常用選用欄位）

行尾註解標示對應章節，完整可運行對照見 `config/sites/full_example.yaml`：

```yaml
name: "網站名稱"
base_url: "https://example.com"

limits:                              # §3
  max_items: 50
  max_pages: 5
  stop_on_duplicate: true
  timeout: 300

request:                             # §4
  headers:
    Referer: "https://example.com"
  cookies:
    session: "xxx"

list_page:                           # §5
  categories:                        # --category 名稱 → 站內值
    "股市": "7251"
    "政治": "6645"
  category_default: "0"              # 未指定 --category 時 {category} 填值
  sources:                           # 必填，至少一項；每個來源自帶完整設定
    - url: "https://example.com/news?page={page}&cat={category}"
      type: "html"
      extract:
        item_selector: "article.news-item"
        link_selector: "a"
        link_attr: "href"
      pagination:
        enabled: true
        start: 1
    - url: "https://example.com/search?q={keyword}&page={page}"
      type: "html"
      extract:
        item_selector: "div.search-item"
        link_selector: "a.title"
        link_attr: "href"
      pagination:
        enabled: true
        start: 1

article_page:                        # §6
  type: "html"                       # html | json
  fields:
    title: "h1.article-title"
    content:
      as: "text"
      selector: "div.article-body"
      attr: "text"
    published_at:
      as: "datetime"
      selector: "time"
      attr: "text"
      datetime_format: "%Y-%m-%d %H:%M"

category:                            # §7
  sources:
    - source: "html"
      selector: 'meta[name="section"]'
      attr: "content"
  default: "其他"

tags:                                # §7
  sources:
    - source: "html"
      selector: 'meta[name="news_keywords"]'
      attr: "content"
      split: ","
```

---

## 3. limits

單站選用覆寫，欄位與全域 `config/settings.yaml:limits` 一致（`config/schema/site.schema.json:18-42`）。未寫入的欄位沿用全域值。

| 欄位 | 類型 | 必填 | 預設（全域） | 說明 |
|------|------|------|--------------|------|
| `max_items` | `integer` `>=1` | 否 | `100` | 收集達標即停止（engine 逐項計數） |
| `max_pages` | `integer` `>=1` | 否 | `3` | 列表頁數上限，唯一權威值；`pagination` 僅管 `enabled` / `type` / `start` / `next_cursor_path`（`src/crawler/site_crawler.py` `start_requests` / `_build_next_cursor_request`） |
| `stop_on_duplicate` | `boolean` | 否 | `false` | `true` 遇到重複 URL 即停止；`false` 僅跳過該 URL 繼續 |
| `timeout` | `number` `>0` | 否 | `180` | 整體爬取逾時（秒） |

三層合併（`src/utils/config.py:merge_limits`，後者覆寫、跳過 `None`）：

```
CLI 參數 (--max-items 等) > site.limits > settings.limits > 程式碼預設
```

CLI 僅本次生效，不寫回檔案，詳見 [global-config.md](global-config.md)。

---

## 4. request

僅套用本站（`src/crawler/site_crawler.py:198,249` 注入 `Request.headers` / `cookies`）。全域 `request.user_agent` / `verify_ssl` 自動套用所有請求（見 [global-config.md](global-config.md)）。

| 欄位 | 類型 | 必填 | 預設 | 說明 |
|------|------|------|------|------|
| `request.headers` | `object<string,string>` | 否 | `{}` | 附加至本站所有請求的標頭（列表與文章共用） |
| `request.cookies` | `object<string,string>` | 否 | `{}` | 附加至本站所有請求的 Cookie |

範例：

```yaml
request:
  headers:
    Referer: "https://example.com"
    X-Custom: "value"
  cookies:
    session: "xxx"
```

> 注意：`request` 容器本身 `additionalProperties: false`，僅允許 `headers` / `cookies`。

---

## 5. list_page

`list_page`（`config/schema/site.schema.json`）為選填物件；一旦提供，`sources` 必填。`list_page` 本身只承載 `sources` / `categories` / `category_default`；**每個 `source` 皆為 self-contained，各自帶 `type`（必填）、`extract`（必填）以及選用的 `method` / `pagination` / `body` / `json_body`，彼此不繼承、不合併**（`src/crawler/site_crawler.py:_select_list_cfg` 直接回傳選中的來源設定）。

### 5.1 來源設定模型

每個 `source` 獨立、完整，無跨來源或跨 `list_page` 的預設值：

| 欄位 | 是否必填 | 說明 |
|------|----------|------|
| `url` | 是 | 列表 URL 模板，每個來源獨立 |
| `type` | 是 | `html` / `json`，決定 `extract` 形態與解析分支（`src/crawler/site_crawler.py:parse_list`） |
| `extract` | 是 | 完整形態（含 `required`），HTML 或 JSON 二選一，須與 `type` 一致（schema `allOf if/then`） |
| `method` | 否 | `GET`（預設）/ `POST` |
| `pagination` | 否 | 選用；未提供時視為不分頁 |
| `body` / `json_body` | 否 | POST 請求本文，見 [§5.6](#56-post-請求本文body--json_body) |

### 5.2 sources

| 欄位 | 類型 | 必填 | 預設 | 說明 |
|------|------|------|------|------|
| `url` | `string` `minLength:1` | 是 | - | 列表 URL 模板，可含 `{page}` / `{keyword}` / `{category}` 佔位符（見 [§8.1](#81-佔位符)）；出現即宣告該來源支援對應篩選 |
| `type` | `enum: html\|json` | 是 | - | 決定 `extract` 形態與解析器；須與 `extract` 形態一致（schema `allOf if/then`） |
| `extract` | `object` | 是 | - | 完整 extract，依 `type` 為 HTML 或 JSON 形態（見 [§5.3](#53-extract)） |
| `method` | `enum: GET\|POST` | 否 | `GET` | 請求方法 |
| `pagination` | `object` (`$defs/pagination`) | 否 | 不分頁 | 見 [§5.4](#54-pagination) |
| `body` | `string` | 否 | - | 原始請求本文（POST），可含 `{page}` / `{keyword}` / `{category}` 佔位符（見 [§5.6](#56-post-請求本文body--json_body)） |
| `json_body` | `object` | 否 | - | JSON 請求本文（POST），字串值可含佔位符（見 [§5.6](#56-post-請求本文body--json_body)） |

第一個不含 `{keyword}` 的來源為預設來源（皆含時取 `sources[0]`）；關鍵字/分類請求的來源選擇見 [§8.2](#82-來源選擇)。

### 5.3 extract

每個來源的 `extract` 為完整形態（含 `required`），依 `type` 二選一、不可混用（`$defs/list_extract_html` / `$defs/list_extract_json`，schema `allOf if/then`；`src/crawler/site_crawler.py:parse_list` 依 `type` 分派）。

#### HTML 列表（`type: html`，`src/crawler/site_crawler.py:_parse_html_list`）

| 欄位 | 類型 | 必填 | 預設（程式） | 說明 |
|------|------|------|--------------|------|
| `item_selector` | `string` | 是 | `"a"`（僅 `_parse_html_list` 內） | 每筆列表項容器的 CSS selector |
| `link_selector` | `string` | 否 | `"a"` | 容器內連結元素的 CSS selector；等於 `item_selector` 時直接取容器本身（`site_crawler.py:273`） |
| `link_attr` | `string` | 否 | `"href"` | 連結屬性名；`text` 表示取元素文字（`site_crawler.py:277`） |

行為細節：遍歷 `parser.select(item_selector)` → 每項取 `select_one(link_selector)` → `get(link_attr)` 或 `get_text` → `urljoin(base_url, href)`。

#### JSON 列表（`type: json`，`src/crawler/site_crawler.py:_parse_json_list`）

| 欄位 | 類型 | 必填 | 預設（程式） | 說明 |
|------|------|------|--------------|------|
| `items_path` | `string` | 是 | `""`（根） | 指向陣列的 JSON path（dot 分隔，空字串表示根即陣列；若指向物件則取其 values；`site_crawler.py:309-313`） |
| `url_field` | `string` | 是 | `"url"` | 每筆 item 內文章 URL 的欄位名（僅取當層 key，非 path） |
| `url_template` | `string` | 否 | `"{url}"` | 用 `{url}` 佔位符組合最終 URL（`site_crawler.py:324` `format(url=raw_url)`）；空字串時改走 `urljoin(base_url, raw_url)` |
| `url_filter` | `string` | 否 | - | 選用正則；最終 URL 不符者跳過（`re.search`，如僅保留主網域文章） |

行為細節：`parser.extract_path(items_path)` → 非陣列則包為單項陣列（物件取其 values）→ 每項取 `item[url_field]` → `url_template.format(url=raw_url)` → 若 `url_filter` 且 URL 不符則跳過 → 注入 `meta.list_data` 供分類 `json/from: list_data` 使用（`site_crawler.py:328-335`）。

### 5.4 pagination

`pagination` 為各 `source` 的選用欄位（`$defs/pagination`）。未提供時視為不分頁（僅請求單頁）。

| 欄位 | 類型 | 必填 | 預設 | 說明 |
|------|------|------|------|------|
| `enabled` | `boolean` | 是 | - | 是否分頁；`false` 時僅請求單頁 |
| `type` | `string` | 否 | `page` | 分頁型態：`page`（以 `{page}` 遞增）或 `cursor`（跟隨回應中的下一頁游標） |
| `start` | `integer` `>=0` | 否 | `1` | `page` 型態的起始頁碼；0 基 API 可設 `0`。`cursor` 型態時作為頁數計數基準 |
| `next_cursor_path` | `string` | `type: cursor` 時必填 | - | 回應內「下一頁游標」的 JSON 路徑（如 `meta.pagination.next_cursor`） |

**page 型態（預設）**：實際爬取頁數由 `limits.max_pages` 控制，`start_requests` 產生 `range(start, start + max_pages)` 個請求；`pagination` 不決定總頁數，僅決定起始與是否啟用。

**cursor 型態**：首個請求以空游標發出（URL 的 `{cursor}` 填 `""`）；每解析完一頁後，由 `next_cursor_path` 取出下一頁游標，填入 URL 的 `{cursor}` 產生下一頁請求（callback 仍為 `parse_list`），直到無游標或已達 `max_pages` 頁（`site_crawler.py:_build_next_cursor_request`）。適用於 cursor / token 型分頁 API（如 TVBS）。`cursor` 型態目前僅支援 `type: json` 的來源。

### 5.5 categories

| 欄位 | 類型 | 必填 | 預設 | 說明 |
|------|------|------|------|------|
| `categories` | `object<string,string>` (`values minLength:1`) | 否 | `{}` | `{ 顯示名: 站內值 }`，`--category` 傳顯示名，經此表轉為站內值填入 `{category}`（`site_crawler.py:169-177`） |
| `category_default` | `string` | 否 | `""` | 未指定 `--category` 時 `{category}` 的填值（`site_crawler.py:178-179`）；僅當 URL 含 `{category}` 且未傳參時生效 |

名稱不在表中時保留原名並記 `warning`（`site_crawler.py:174`）。

### 5.6 POST 請求本文（body / json_body）

部分站點的列表 API 需要 POST 並帶請求本文。各 `source` 可設定 `body`（原始字串）或 `json_body`（JSON 物件）；`method: POST` 時由 HTTP client 送出（`src/core/http_client/curl_cffi_client.py` 以 `data=body, json=json_body` 傳遞）。

| 欄位 | 類型 | 說明 |
|------|------|------|
| `body` | `string` | 原始請求本文；字串內可用 `{page}` / `{keyword}` / `{category}` 佔位符 |
| `json_body` | `object` | JSON 請求本文；**字串值**可含佔位符，若某字串值**恰為單一佔位符**（如 `"{page}"`），會以原生型別代入（`{page}` 為整數） |

佔位符支援度以 `url` + `body` + `json_body` 三者合併判斷：只要任一處出現 `{keyword}` / `{category}`，該來源即被視為支援對應篩選（見 [§8.2](#82-來源選擇)）。

範例（中央社 WNewsList API，`config/sites/cna.yaml`）：

```yaml
list_page:
  method: "POST"
  type: "json"
  extract:
    items_path: "ResultData.Items"
    url_field: "PageUrl"
    url_template: "{url}"
  pagination:
    enabled: true
    start: 1
  sources:
    - url: "https://www.cna.com.tw/cna2018api/api/WNewsList"
      json_body:
        action: "0"
        category: "{category}"   # 由 categories 對應表轉為站內值
        pagesize: "100"
        pageidx: "{page}"        # 整值佔位符 -> 以整數代入
```

---

## 6. article_page

| 欄位 | 類型 | 必填 | 預設 | 說明 |
|------|------|------|------|------|
| `type` | `enum: html\|json` | 是 | - | 回應格式，決定 `fields` 內欄位物件的形態（`allOf if/then`，`config/schema/site.schema.json:180-231`） |
| `fields` | `object<string, string\|object>` | 否 | `{}` | `{ 欄位名: 字串簡寫 \| 物件 }`，輸出至 `Item.data`（`site_crawler.py:352`） |

未提供 `article_page` 時，列表 URL 直接輸出為 `link` 類型 Item，不發文章請求（`site_crawler.py:291-297,336-341`）。

### 6.1 兩種寫法

```yaml
# 字串簡寫：依 article_page.type 決定語意
fields:
  title: "h1.article-title"        # html：CSS selector 取 text（site_crawler.py:386）
  title: "data.title"              # json：JSON path（site_crawler.py:413）

# 物件完整寫法：依 type 區分（不可混用，否則 Schema 驗證失敗）
fields:
  published_at:                    # html 物件
    as: "datetime"
    selector: "time"
    attr: "text"
    datetime_format: "%Y-%m-%d %H:%M"
  published_at:                    # json 物件
    as: "datetime"
    path: "data.publishedAt"
    datetime_format: "%Y-%m-%dT%H:%M:%S"
```

### 6.2 HTML 欄位物件（`$defs/html_field_config`，`article_page.type: html` 時）

| 欄位 | 類型 | 必填 | 預設 | 說明 |
|------|------|------|------|------|
| `selector` | `string` | 是 | - | CSS selector（`site_crawler.py:388` 缺省即 `warning` 跳過） |
| `attr` | `string` | 否 | `"text"` | 擷取屬性；`text` 取 `parser.extract(selector, "text")` 的文字，否則取 `el.get(attr)`（`site_crawler.py:392-393`；常見 `content` 取 `<meta>`） |
| `as` | `enum: text\|datetime` | 否 | 省略即 raw | 萃取策略（見 [§6.4](#64-共通行為-as--regex--datetime_format)） |
| `datetime_format` | `string` | 否 | `fromisoformat` | 僅 `as: datetime` 時有效；`strptime` 格式，未指定時走 `datetime.fromisoformat`（`site_crawler.py:433-438`） |
| `regex` | `string` | 否 | - | 對擷取結果套正則，取 `match.groups()` 以 `/` 串接（`site_crawler.py:441-443,448-450`） |

### 6.3 JSON 欄位物件（`$defs/json_field_config`，`article_page.type: json` 時）

| 欄位 | 類型 | 必填 | 預設 | 說明 |
|------|------|------|------|------|
| `path` | `string` | 是 | - | JSON path（dot 分隔，`site_crawler.py:415-416` `parser.extract_path(path)`） |
| `as` | `enum: text\|datetime` | 否 | 省略即 raw | 萃取策略（見 [§6.4](#64-共通行為-as--regex--datetime_format)） |
| `datetime_format` | `string` | 否 | `fromisoformat` | 僅 `as: datetime` 時有效；同 HTML |
| `regex` | `string` | 否 | - | 同 HTML，對字串結果套正則 |

### 6.4 共通行為：`as` / `regex` / `datetime_format`

後處理由 `SiteCrawler._extract_field`（`site_crawler.py:427-456`）執行：

| `as` | 行為 |
|------|------|
| 省略（raw） | 若有 `regex` 則套用 `re.search` 取 groups 串接，否則原樣回傳 |
| `text` | `value.strip()`；若有 `regex` 先套用再 `strip` |
| `datetime` | 若有 `datetime_format` 則 `datetime.strptime(value, format)`，否則 `datetime.fromisoformat(value)`；`regex` 不適用於此分支 |

> 例：取 `<meta name="author" content="...">` 無需宣告 `as`，僅寫 `selector` + `attr: content` 即可（`as` 省略仍可配合 `regex`）。

---

## 7. 分類與標籤

兩者皆為多值累加、自動去重（`src/crawler/classifier.py:48-97`）。差異：`category` 全失敗時取 `default`；`tags` 無兜底。

### 7.1 category / tags 對照

| 項目 | `category` | `tags` |
|------|-----------|--------|
| Schema | `config/schema/site.schema.json:43-62`，`required: [sources]` | `config/schema/site.schema.json:63-78`，`required: [sources]` |
| 來源累加 | 全部命中值累加為陣列（`classifier.py:48-61`） | 同左（`classifier.py:83-97`） |
| 去重 | 是（保序，`classifier.py:74-81`） | 是 |
| 兜底 | `default: "其他"`（可選，全部來源皆空時生效） | 無 |
| 多值分割 | `split`（所有 `source` 通用，`classifier.py:53`） | 同左 |
| 多元素處理 | `multiple` / `join`（僅 `html` 來源，`classifier.py:129-145`） | 同左 |

輸出位置（`site_crawler.py:361-367`）：`data.category`（原始）、`data.normalized_category`（經 `category_normalization` 轉換後）、`data.tags`。

### 7.2 支援的來源類型總覽

`classifier_source` 為 `oneOf` 4 型（`config/schema/site.schema.json:326-449`），由 `source` 欄位決定形態：

| `source` | 判斷欄位 | 適用情境 |
|----------|----------|----------|
| `url` | `regex` | 從文章 URL 提煉分類（如 `/story/<id>/` 映射） |
| `html` | `selector` | 從文章 HTML 萃取（CSS selector + attr） |
| `json` | `from` + `path` | 從 JSON 資料源萃取（`json_ld` / `list_data` / `article_json`） |
| `keyword` | `rules` | 依標題與內文關鍵字命中 |

所有類型皆可選 `mapping` / `split`；`html` 另有 `multiple` / `join`（互斥）。

### 7.3 各來源詳細參數

#### url 來源（`source: url`，`classifier.py:_extract_url`）

| 參數 | 類型 | 必填 | 預設 | 說明 |
|------|------|------|------|------|
| `source` | `const: "url"` | 是 | - | 來源類型識別 |
| `regex` | `string` | 是 | - | 對 `response.url` 套 `re.search`；有捕獲組取第 1 組，否則取完整匹配（`classifier.py:117-120`） |
| `split` | `string` | 否 | - | 將單一字串拆為多值（如 `","`） |
| `mapping` | `object<string,string>` | 否 | - | 值轉換表（見 [§7.4](#74-通用後處理-mapping--split--multiple--join)） |

#### html 來源（`source: html`，`classifier.py:_extract_html`）

| 參數 | 類型 | 必填 | 預設 | 說明 |
|------|------|------|------|------|
| `source` | `const: "html"` | 是 | - | 來源類型識別 |
| `selector` | `string` | 是 | - | CSS selector 指向文章 HTML 元素 |
| `attr` | `string` | 否 | `"text"` | 擷取屬性；`text` 取文字，否則取屬性值（`classifier.py:127`）；常見 `content` 取 `<meta>` |
| `multiple` | `boolean` | 否 | `false` | `true` 回清單（多元素各自取 `attr`）；與 `join` 互斥（`classifier.py:130-145`） |
| `join` | `string` | 否 | - | 多匹配串接分隔符（如 `">"` 串接麵包屑）；與 `multiple` 互斥，同時出現時 `join` 優先並記 `warning` |
| `split` | `string` | 否 | - | 將單一字串拆為多值 |
| `mapping` | `object<string,string>` | 否 | - | 值轉換表 |

萃取規則（`classifier.py:122-146`）：`join` 存在時遍歷 `parser.select(selector)` 全部拼接；`multiple: true` 時回陣列；否則取首個匹配（`parser.extract`）。

#### json 來源（`source: json`，`classifier.py:_extract_json`）

| 參數 | 類型 | 必填 | 預設 | 說明 |
|------|------|------|------|------|
| `source` | `const: "json"` | 是 | - | 來源類型識別 |
| `from` | `enum: json_ld\|list_data\|article_json` | 是 | - | 資料源（見下表） |
| `path` | `string` | 是 | - | dot 分隔 JSON path（`classifier.py:159,169,173`） |
| `split` | `string` | 否 | - | 將單一字串拆為多值 |
| `mapping` | `object<string,string>` | 否 | - | 值轉換表 |

`from` 取值：

| `from` | 資料來源 | 說明 |
|--------|----------|------|
| `json_ld` | 文章 HTML 內第一個 `script[type="application/ld+json"]` | 遍歷所有 JSON-LD 區塊，首個命中 `path` 非空即回傳（`classifier.py:151-162`） |
| `list_data` | 列表 JSON 的 `meta.list_data`（`site_crawler.py:334` 注入） | 取自列表頁對應 item 的原始 JSON；`path` 為相對於該 item 的路徑 |
| `article_json` | 文章 JSON 回應全文 | 直接對 `response.text` 的 JSON 解析結果取 `path`（`classifier.py:171-173`） |

#### keyword 來源（`source: keyword`，`classifier.py:_extract_keyword`）

| 參數 | 類型 | 必填 | 預設 | 說明 |
|------|------|------|------|------|
| `source` | `const: "keyword"` | 是 | - | 來源類型識別 |
| `rules` | `array<object>` `minItems:1` | 是 | - | 規則陣列，逐條命中（見下表） |
| `mapping` | `object<string,string>` | 否 | - | 對命中後的 `value` 再做轉換（較少用） |

`rules[]` 單條規則：

| 參數 | 類型 | 必填 | 說明 |
|------|------|------|------|
| `keywords` | `array<string>` `minItems:1` | 是 | 關鍵字清單，任一 `kw in (title + content)` 即命中（`classifier.py:183` 子字串比對） |
| `value` | `string` | 是 | 命中時回傳的分類/標籤值 |

比對文本為 `data.title` + `data.content` 的字串拼接（`classifier.py:179`），命中多條規則時回陣列累加。

### 7.4 通用後處理：`mapping` / `split` / `multiple` / `join`

| 參數 | 適用 | 處理時機與邏輯 |
|------|------|----------------|
| `mapping` | 全部 4 型 | 萃取後、分割前/後皆可映射（`classifier.py:187-193,59,95`）；`{ 原始值: 顯示名 }`，未命中保留原值 |
| `split` | 全部 4 型 | 若值為字串且指定 `split`，則 `value.split(split)` 並 `strip` 去空（`classifier.py:53,89`）；若值已為陣列（`multiple`/`keyword`）則不分割 |
| `multiple` | 僅 `html` | 回陣列供外層直接展開（`classifier.py:55` `isinstance(value, list)` 分支） |
| `join` | 僅 `html` | 回單一字串（多值串接）；外層視為單值，若需再拆須配合 `split` |

> 約束：`multiple` 與 `join` 互斥（Schema 未強制，但程式以 `join` 為優先並告警）。

### 7.5 範例

```yaml
# category：多來源累加 + default + mapping / join / split + 4 型全覆蓋
category:
  sources:
    - source: "html"
      selector: 'meta[name="section"]'
      attr: "content"
    - source: "url"
      regex: "/story/(\\d+)/"
      mapping:
        "7251": "股市"
    - source: "html"
      selector: "a.breadcrumb-item"
      attr: "text"
      join: ">"
    - source: "json"
      from: "json_ld"
      path: "itemListElement.1.name"
    - source: "json"
      from: "list_data"
      path: "category"
    - source: "keyword"
      rules:
        - keywords: ["台股", "股市"]
          value: "財經"
  default: "其他"

# tags：累加 + split + multiple + keyword
tags:
  sources:
    - source: "html"
      selector: 'meta[name="news_keywords"]'
      attr: "content"
      split: ","
    - source: "html"
      selector: "a.tag"
      attr: "text"
      multiple: true
    - source: "keyword"
      rules:
        - keywords: ["台股"]
          value: "台股"
```

### 7.6 跨站統一（category_normalization）

各站同義分類（如「股市」/「金融」）在 `config/category_normalization.yaml` 設定全域對應表，`Settings` 載入時自動合併（`settings.yaml` 內的值優先）：

```yaml
# config/category_normalization.yaml
"股市": "財經"
"金融": "財經"
"資通訊": "科技"
```

分類結果同時寫入 `data.category`（原始，去重後）與 `data.normalized_category`（經 `Classifier._normalize` 轉換，無對應則保留原值，去重，`classifier.py:66-72`）。

---

## 8. 搜尋與篩選

CLI `--keyword` / `--category` 為選用、可組合，需站點 `sources[].url` 含對應佔位符才生效（`src/crawler/site_crawler.py:_select_list_cfg` / `_build_list_url`）。

### 8.1 佔位符

| 佔位符 | 來源 | 填值規則 |
|--------|------|----------|
| `{page}` | 分頁迴圈 | `pagination.start` 起算，`max_pages` 控制上限；非分頁時填 `start` |
| `{keyword}` | `--keyword` | 有則填值，無則空字串（`site_crawler.py:181-183` `_FormatDict`） |
| `{category}` | `--category` | 有則查 `categories` 表轉站內值（不在表則用原名並 `warning`）；無則填 `category_default`（預設空字串，`site_crawler.py:169-179`） |
| `{cursor}` | `pagination.type: cursor` | 首頁填空字串；後續頁由 `next_cursor_path` 從回應取出並填入（`site_crawler.py:_build_next_cursor_request`） |

URL 模板內未出現的佔位符不影響爬取；多餘佔位符以空字串或 `start` 補齊，不中斷流程。`body` / `json_body` 亦支援同一組佔位符（見 [§5.6](#56-post-請求本文body--json_body)）。

### 8.2 來源選擇

依 URL 內實際出現的佔位符判斷支援度，永遠優雅降級（`src/crawler/site_crawler.py:_select_list_cfg`），結果快取於 `_selected_list_cfg`：

| 請求 | 優先順序 | 行為 |
|------|----------|------|
| `--keyword` + `--category` | 1. 同時含 `{keyword}`+`{category}` 的來源 → 2. 含 `{keyword}` 的來源（`warning` 忽略 `--category`） → 3. 含 `{category}` 的來源（`warning` 忽略 `--keyword`） → 4. 預設來源 | 關鍵字優先降級（`site_crawler.py:106-128`） |
| 僅 `--keyword` | 1. 含 `{keyword}` 且不含 `{category}` 的來源 → 2. 任一含 `{keyword}` 的來源 → 3. 預設來源 | 避免帶出多餘篩選（`site_crawler.py:129-139`） |
| 僅 `--category` | 1. 含 `{category}` 且不含 `{keyword}` 的來源 → 2. 任一含 `{category}` 的來源 → 3. 預設來源 | 同上（`site_crawler.py:140-150`） |
| 無篩選 | 預設來源（第一個不含 `{keyword}` 者，皆含時取 `sources[0]`） | - |

### 8.3 填值規則

* 每個來源的 `method` / `type` / `extract` / `pagination` / `body` / `json_body` 皆為來源自有，無繼承或合併（[§5.1](#51-來源設定模型)）。
* `{keyword}` / `{category}` / `{page}` 未命中時以空字串或 `start` 補齊，不中斷爬取，僅記 `warning`。
* `keyword` / `category` 的解析為 `SiteCrawler` 建構期參數，`_select_list_cfg` 為純函數，`parse_list` 重算結果一致，無需依賴請求 `meta`。

---

## 9. 驗證與除錯

所有設定載入時以 JSON Schema 嚴格驗證（`site.schema.json` / `settings.schema.json`，`src/utils/config.py:validate_config`），失敗拋 `ConfigValidationError` 並標示 JSON Pointer 路徑。

### 9.1 常見錯誤

| 錯誤訊息要點 | 原因 | 修正 |
|--------------|------|------|
| `additionalProperties` | 欄位拼寫錯誤或層級放錯（`additionalProperties: false`） | 檢查欄位名與縮排；`request` 僅允許 `headers`/`cookies`，`pagination` 僅 `enabled`/`type`/`start`/`next_cursor_path` |
| `is not one of ['html', 'json']` | `type` / `source` / `from` 枚舉錯誤 | `type: html\|json`；`source: url\|html\|json\|keyword`；`from: json_ld\|list_data\|article_json` |
| `is not one of ['GET', 'POST']` | `method` 大小寫錯誤 | 僅接受大寫 `GET` / `POST` |
| `is not of type 'string'` / `minimum` / `pattern` | 型別或數值範圍不符 | `name` 非空、`base_url` 須 `^https?://`、`max_items`/`max_pages` `>=1`、`timeout` `>0`、`start` `>=0` |
| `allOf` / `list_extract_html` / `list_extract_json` 失敗 | 來源 `extract` 形態與 `type` 不一致或缺少必填欄位 | `type: html` 需 `extract.item_selector`；`type: json` 需 `extract.items_path` 與 `url_field`；不可跨形態混用 |
| `html_field_config` 要求 `selector` / `json_field_config` 要求 `path` | `article_page.type` 與 `fields` 形態不一致 | `type: html` 時物件必含 `selector`，`type: json` 必含 `path`（`allOf if/then`） |
| `is not of type 'array'` / `minItems` | `sources` / `rules` / `keywords` 空陣列 | `sources` / `rules` / `keywords` 至少 1 項 |
| `required` 缺 `url` / `type` / `extract` / `sources` | 必填欄位缺失 | `list_page.sources[].url` / `type` / `extract`、`list_page.sources`、`article_page.type`、`classifier source` 的 `source` 等 |

### 9.2 檢查方式

```bash
# 啟動即驗證，報錯含路徑與 Schema 關鍵字
python main.py --site <site_id>

# 確認站點已註冊（掃描 config/sites/*.yaml）
python main.py --list-sites

# 僅驗證單站（不發請求）
python -c "from src.utils.config import load_site_config; load_site_config('full_example')"
```

新增或修改欄位時須同步更新 `config/schema/site.schema.json`，否則載入直接失敗。

---

## 10. 附錄：完整 Schema 對照範本

以下範本逐欄對應 `config/schema/site.schema.json` 的所有定義，含必填/選填、枚舉與形態區分。可直接複製為 `config/sites/<name>.yaml` 起始檔，刪除不需要的區塊即可。

```yaml
# Schema: config/schema/site.schema.json
# 驗證：python main.py --site <site_id> 啟動即檢查

# ── 頂層 (required: ["name","base_url"]) ──
name: "完整範例站"
base_url: "https://example.com"          # pattern ^https?://

# ── limits 選填 (§3) ──
limits:
  max_items: 50                          # integer >=1
  max_pages: 5                           # integer >=1，唯一頁數權威值
  stop_on_duplicate: true                # boolean
  timeout: 300                           # number >0

# ── request 選填 (§4) ──
request:
  headers:                               # map<string,string>
    Referer: "https://example.com"
    X-Custom: "value"
  cookies:                               # map<string,string>
    session: "xxx"

# ── list_page 選填，唯 sources 必填 (§5) ──
# list_page 只承載 sources / categories / category_default；
# 每個 source 自帶 type + extract（必填）與選用 method / pagination / body / json_body。
list_page:
  categories:                            # map<string,string>
    "股市": "7251"
    "政治": "6645"
  category_default: "0"                  # string

  sources:                               # 必填 >=1 項
    # 來源 1：預設列表（不含 {keyword}，符合 §8.2 預設來源定義）
    - url: "https://example.com/news?page={page}&cat={category}"
      type: "html"                       # 必填 enum html|json
      extract:                           # 必填，形態須與 type 一致
        item_selector: "article.news-item"  # HTML 必填
        link_selector: "a"               # 選填，預設 a
        link_attr: "href"                # 選填，預設 href，text 表示取文字
      pagination:                        # $defs/pagination
        enabled: true                    # 必填 boolean
        type: "page"                     # 選填 enum page|cursor，預設 page
        start: 1                         # integer >=0，預設 1
        # next_cursor_path: "meta.pagination.next_cursor"  # type: cursor 時必填

    # 來源 2：關鍵字搜尋（宣告支援 {keyword}）
    - url: "https://example.com/search?q={keyword}&page={page}"
      type: "html"
      extract:
        item_selector: "div.search-item"
        link_selector: "a.title"
        link_attr: "href"

    # 來源 3：JSON 列表
    - url: "https://example.com/api/list?page={page}"
      type: "json"
      method: "GET"                      # 選填 enum GET|POST，預設 GET
      extract:
        items_path: "result.articles"    # JSON 必填
        url_field: "slug"                # 必填
        url_template: "https://example.com/article/{url}"  # 選填，{url} 佔位符；空字串走 urljoin
        # url_filter: "^https://example\\.com/"  # 選填，最終 URL 不符則跳過
      pagination:
        enabled: true
        start: 1

    # 來源 4：POST JSON 列表（請求本文帶佔位符；整值佔位符以原生型別代入）
    - url: "https://example.com/api/search"
      type: "json"
      method: "POST"
      json_body:
        category: "{category}"
        pageidx: "{page}"
      extract:
        items_path: "result.items"
        url_field: "url"

    # 來源 5：cursor 分頁 JSON 列表（首頁空游標，後續由回應的 next_cursor 帶入）
    - url: "https://example.com/api/realtime?cursor={cursor}"
      type: "json"
      extract:
        items_path: "data"
        url_field: "article_url"
        url_template: "{url}"
      pagination:
        enabled: true
        type: "cursor"
        start: 1
        next_cursor_path: "meta.pagination.next_cursor"  # 回應內下一頁游標路徑

# ── article_page 選填 (§6) ──
article_page:
  type: "html"                           # 必填 enum html|json
  fields:                                # map<field, string|object>
    # 字串簡寫：html 為 CSS 取 text，json 為 JSON path (§6.1)
    title: "h1.article-title"
    # title: "data.title"                # json 簡寫對照

    # 物件完整寫法依 type 區分 (allOf if/then，§6.2/§6.3)
    # $defs/html_field_config 要求 selector，$defs/json_field_config 要求 path
    content:
      as: "text"                         # enum text|datetime，省略即 raw
      selector: "div.article-body"
      attr: "text"                       # 預設 text，取文字；content 取 meta 屬性
      regex: "(.*)"                      # 選填，正則取 groups 以 / 串接
    published_at:
      as: "datetime"
      selector: "time"
      attr: "text"
      datetime_format: "%Y-%m-%d %H:%M"  # strptime，省略則 fromisoformat
    author:
      selector: "meta[name='author']"    # raw 範例：不寫 as，直接取屬性
      attr: "content"

    # 當 type: json 時，改用 json_field_config 要求 path：
    # content:
    #   as: "text"
    #   path: "data.body"
    # published_at:
    #   as: "datetime"
    #   path: "data.publishedAt"
    #   datetime_format: "%Y-%m-%dT%H:%M:%S"

# ── category 選填 (§7) ──
category:
  sources:                               # 必填 >=1，$defs/classifier_source oneOf 4 型
    - source: "html"                     # html 來源 (§7.3)
      selector: 'meta[name="section"]'
      attr: "content"                    # 預設 text
      # multiple: true                   # 與 join 互斥，取全部回清單
      # join: ">"                        # 與 multiple 互斥，多匹配串接
      # split: ","                       # 選填，所有類型皆可
      mapping:                           # 選填，所有類型通用 map<string,string>
        "raw1": "顯示名1"
    - source: "url"                      # url 來源
      regex: "/story/(\\d+)/"            # 取第 1 group
      mapping:
        "7251": "股市"
    - source: "html"
      selector: "a.breadcrumb-item"
      attr: "text"
      join: ">"
    - source: "json"                     # json 來源
      from: "json_ld"                    # enum json_ld|list_data|article_json
      path: "about.name"                 # dot path
    - source: "json"
      from: "list_data"
      path: "category"                   # 取自 meta.list_data
    - source: "json"
      from: "article_json"
      path: "data.category"              # 取自文章 JSON
    - source: "keyword"                  # keyword 來源
      rules:                             # >=1 項
        - keywords: ["台股", "股市"]     # >=1 項
          value: "財經"                  # 命中回傳值
        - keywords: ["AI"]
          value: "科技"
  default: "其他"                        # 全部失敗時兜底（category 獨有）

# ── tags 選填 (§7) ──
tags:
  sources:
    - source: "html"
      selector: 'meta[name="news_keywords"]'
      attr: "content"
      split: ","                         # 將單字串拆多標籤
    - source: "html"
      selector: "a.tag"
      attr: "text"
      multiple: true
    - source: "keyword"
      rules:
        - keywords: ["台股"]
          value: "台股"
```

對照要點：

| Schema 位置 | 規則 |
|-------------|------|
| `additionalProperties: false` 全域 | 未知欄位/拼錯立即報錯（含頂層、`request`、`pagination`、`html/json_field_config` 等） |
| `list_page` self-contained | `list_page` 只允許 `sources` / `categories` / `category_default`；每個 `source` 必填 `type` + `extract`，並以 `allOf if/then` 強制 `extract` 形態與 `type` 一致（`src/crawler/site_crawler.py:_select_list_cfg`） |
| `article_page` `allOf` | `type: html` 時物件必含 `selector`，`type: json` 必含 `path`，混用驗證失敗；`as` 僅 `text`/`datetime`，`attr` 值不再受限 |
| `classifier_source` `oneOf` 4 型 | `source` 決定形態：`url` 需 `regex`、`html` 需 `selector`、`json` 需 `from`+`path`、`keyword` 需 `rules`；`mapping`/`split` 通用；`html` 的 `multiple`/`join` 互斥 |
| `classifier_mapping` | `object<string,string>`，未命中保留原值（`src/crawler/classifier.py:187-193`） |
