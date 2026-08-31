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
  extract:
    item_selector: "article.news-item"  # 每筆列表項容器
    link_selector: "a"                  # 容器內的連結元素
    link_attr: "href"                   # 連結屬性
  sources:
    - url: "https://example.com/news?page={page}"

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
  method: "GET"                      # 繼承預設：GET | POST
  type: "html"                       # 繼承預設：html | json
  categories:                        # --category 名稱 → 站內值
    "股市": "7251"
    "政治": "6645"
  category_default: "0"              # 未指定 --category 時 {category} 填值
  extract:                           # 繼承預設，深合併至各 source
    item_selector: "article.news-item"
    link_selector: "a"
    link_attr: "href"
  pagination:                        # 繼承預設
    enabled: true
    start: 1
  sources:                           # 必填，至少一項
    - url: "https://example.com/news?page={page}&cat={category}"
    - url: "https://example.com/search?q={keyword}&page={page}"

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
| `max_pages` | `integer` `>=1` | 否 | `3` | 列表頁數上限，唯一權威值；`pagination` 僅管 `enabled` / `start`（`src/crawler/site_crawler.py:202-205` `range(start, start + max_pages)`） |
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

`list_page`（`config/schema/site.schema.json:97-165`）為選填物件；一旦提供，`sources` 必填。`method` / `type` / `extract` / `pagination` 為所有 `sources` 的繼承預設值。

### 5.1 繼承模型

單一 `source` 內同名欄位覆蓋規則（`src/crawler/site_crawler.py:88-98`）：

| 欄位 | 合併方式 | 說明 |
|------|----------|------|
| `method` | 直接覆蓋 | 來源未寫則沿用 `list_page.method`，否則取來源值 |
| `type` | 直接覆蓋 | 同上（`html` / `json` 決定解析分支 `src/crawler/site_crawler.py:247-255`） |
| `pagination` | 直接覆蓋 | 同上 |
| `extract` | 深合併（shallow merge） | `dict(base_extract, **source_extract)`；來源只需寫差異欄位，例如僅覆蓋 `url_template`（`src/crawler/site_crawler.py:94-97`） |
| `url` | 來源自有 | 無繼承，每個來源獨立 |

### 5.2 sources

| 欄位 | 類型 | 必填 | 預設 | 說明 |
|------|------|------|------|------|
| `url` | `string` `minLength:1` | 是 | - | 列表 URL 模板，可含 `{page}` / `{keyword}` / `{category}` 佔位符（見 [§8.1](#81-佔位符)）；出現即宣告該來源支援對應篩選 |
| `method` | `enum: GET\|POST` | 否 | 繼承 `list_page.method` → `GET` | 覆蓋繼承預設 |
| `type` | `enum: html\|json` | 否 | 繼承 `list_page.type` → `html` | 覆蓋繼承預設，決定 `extract` 形態與解析器 |
| `extract` | `object` (`$defs/list_extract_partial`) | 否 | 繼承 `list_page.extract` | 部分 extract，深合併 |
| `pagination` | `object` (`$defs/pagination`) | 否 | 繼承 `list_page.pagination` | 覆蓋繼承預設 |

第一個不含 `{keyword}` 的來源為預設來源（皆含時取 `sources[0]`）；關鍵字/分類請求的來源選擇見 [§8.2](#82-來源選擇)。

### 5.3 extract

依列表回應類型二選一，不可混用（`$defs/list_extract` `oneOf`，`src/crawler/site_crawler.py:252-255` 分派）。`list_page.extract` 為完整形態（含 `required`），`sources[].extract` 為部分形態（`$defs/list_extract_partial`，全選填、深合併）。

#### HTML 列表（`type: html`，`src/crawler/site_crawler.py:_parse_html_list`）

| 欄位 | 類型 | 必填（`list_page.extract`） | 預設（程式） | 說明 |
|------|------|------------------------------|--------------|------|
| `item_selector` | `string` | 是 | `"a"`（僅 `_parse_html_list` 內） | 每筆列表項容器的 CSS selector |
| `link_selector` | `string` | 否 | `"a"` | 容器內連結元素的 CSS selector；等於 `item_selector` 時直接取容器本身（`site_crawler.py:273`） |
| `link_attr` | `string` | 否 | `"href"` | 連結屬性名；`text` 表示取元素文字（`site_crawler.py:277`） |

行為細節：遍歷 `parser.select(item_selector)` → 每項取 `select_one(link_selector)` → `get(link_attr)` 或 `get_text` → `urljoin(base_url, href)`。

#### JSON 列表（`type: json`，`src/crawler/site_crawler.py:_parse_json_list`）

| 欄位 | 類型 | 必填（`list_page.extract`） | 預設（程式） | 說明 |
|------|------|------------------------------|--------------|------|
| `items_path` | `string` | 是 | `""`（根） | 指向陣列的 JSON path（dot 分隔，空字串表示根即陣列；`site_crawler.py:309-313`） |
| `url_field` | `string` | 是 | `"url"` | 每筆 item 內文章 URL 的欄位名（僅取當層 key，非 path） |
| `url_template` | `string` | 否 | `"{url}"` | 用 `{url}` 佔位符組合最終 URL（`site_crawler.py:324` `format(url=raw_url)`）；空字串時改走 `urljoin(base_url, raw_url)` |

行為細節：`parser.extract_path(items_path)` → 非陣列則包為單項陣列 → 每項取 `item[url_field]` → `url_template.format(url=raw_url)` → 注入 `meta.list_data` 供分類 `json/from: list_data` 使用（`site_crawler.py:328-335`）。

### 5.4 pagination

`$defs/pagination`（`config/schema/site.schema.json:236-249`）

| 欄位 | 類型 | 必填 | 預設 | 說明 |
|------|------|------|------|------|
| `enabled` | `boolean` | 是 | - | 是否分頁；`false` 時僅請求單頁（`site_crawler.py:200-227`） |
| `start` | `integer` `>=1` | 否 | `1` | 起始頁碼 |

實際爬取頁數由 `limits.max_pages` 控制：`range(start, start + max_pages)`。`pagination` 不決定總頁數，僅決定起始與是否啟用。

### 5.5 categories

| 欄位 | 類型 | 必填 | 預設 | 說明 |
|------|------|------|------|------|
| `categories` | `object<string,string>` (`values minLength:1`) | 否 | `{}` | `{ 顯示名: 站內值 }`，`--category` 傳顯示名，經此表轉為站內值填入 `{category}`（`site_crawler.py:169-177`） |
| `category_default` | `string` | 否 | `""` | 未指定 `--category` 時 `{category}` 的填值（`site_crawler.py:178-179`）；僅當 URL 含 `{category}` 且未傳參時生效 |

名稱不在表中時保留原名並記 `warning`（`site_crawler.py:174`）。

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
| `{page}` | 分頁迴圈 | `pagination.start` 起算，`max_pages` 控制上限（`site_crawler.py:180-188,205`）；非分頁時填 `start` |
| `{keyword}` | `--keyword` | 有則填值，無則空字串（`site_crawler.py:181-183` `_FormatDict`） |
| `{category}` | `--category` | 有則查 `categories` 表轉站內值（不在表則用原名並 `warning`）；無則填 `category_default`（預設空字串，`site_crawler.py:169-179`） |

URL 模板內未出現的佔位符不影響爬取；多餘佔位符以空字串或 `start` 補齊，不中斷流程。

### 8.2 來源選擇

依 URL 內實際出現的佔位符判斷支援度，永遠優雅降級（`src/crawler/site_crawler.py:_select_list_cfg`），結果快取於 `_selected_list_cfg`：

| 請求 | 優先順序 | 行為 |
|------|----------|------|
| `--keyword` + `--category` | 1. 同時含 `{keyword}`+`{category}` 的來源 → 2. 含 `{keyword}` 的來源（`warning` 忽略 `--category`） → 3. 含 `{category}` 的來源（`warning` 忽略 `--keyword`） → 4. 預設來源 | 關鍵字優先降級（`site_crawler.py:106-128`） |
| 僅 `--keyword` | 1. 含 `{keyword}` 且不含 `{category}` 的來源 → 2. 任一含 `{keyword}` 的來源 → 3. 預設來源 | 避免帶出多餘篩選（`site_crawler.py:129-139`） |
| 僅 `--category` | 1. 含 `{category}` 且不含 `{keyword}` 的來源 → 2. 任一含 `{category}` 的來源 → 3. 預設來源 | 同上（`site_crawler.py:140-150`） |
| 無篩選 | 預設來源（第一個不含 `{keyword}` 者，皆含時取 `sources[0]`） | - |

### 8.3 繼承與填值規則

* 單一來源的 `method` / `type` / `pagination` 直接覆蓋 list_page 預設；`extract` 深合併（[§5.1](#51-繼承模型)）。
* `{keyword}` / `{category}` / `{page}` 未命中時以空字串或 `start` 補齊，不中斷爬取，僅記 `warning`。
* `keyword` / `category` 的解析為 `SiteCrawler` 建構期參數，`_select_list_cfg` 為純函數，`parse_list` 重算結果一致，無需依賴請求 `meta`。

---

## 9. 驗證與除錯

所有設定載入時以 JSON Schema 嚴格驗證（`site.schema.json` / `settings.schema.json`，`src/utils/config.py:validate_config`），失敗拋 `ConfigValidationError` 並標示 JSON Pointer 路徑。

### 9.1 常見錯誤

| 錯誤訊息要點 | 原因 | 修正 |
|--------------|------|------|
| `additionalProperties` | 欄位拼寫錯誤或層級放錯（`additionalProperties: false`） | 檢查欄位名與縮排；`request` 僅允許 `headers`/`cookies`，`pagination` 僅 `enabled`/`start` |
| `is not one of ['html', 'json']` | `type` / `source` / `from` 枚舉錯誤 | `type: html\|json`；`source: url\|html\|json\|keyword`；`from: json_ld\|list_data\|article_json` |
| `is not one of ['GET', 'POST']` | `method` 大小寫錯誤 | 僅接受大寫 `GET` / `POST` |
| `is not of type 'string'` / `minimum` / `pattern` | 型別或數值範圍不符 | `name` 非空、`base_url` 須 `^https?://`、`max_items`/`max_pages` `>=1`、`timeout` `>0`、`start` `>=1` |
| `oneOf` / `list_extract` 失敗 | HTML 與 JSON 的 `extract` 形態混用 | 同一 `extract` 內不可同時出現 `item_selector` 與 `items_path` 等跨形態欄位 |
| `html_field_config` 要求 `selector` / `json_field_config` 要求 `path` | `article_page.type` 與 `fields` 形態不一致 | `type: html` 時物件必含 `selector`，`type: json` 必含 `path`（`allOf if/then`） |
| `is not of type 'array'` / `minItems` | `sources` / `rules` / `keywords` 空陣列 | `sources` / `rules` / `keywords` 至少 1 項 |
| `required` 缺 `url` / `sources` / `type` | 必填欄位缺失 | `list_page.sources[].url`、`article_page.type`、`classifier source` 的 `source` 等 |

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
list_page:
  method: "GET"                          # enum GET|POST，作為 sources 繼承預設
  type: "html"                           # enum html|json，作為 sources 繼承預設
  categories:                            # map<string,string>
    "股市": "7251"
    "政治": "6645"
  category_default: "0"                  # string

  # extract 繼承預設，深合併至各 source
  # $defs/list_extract HTML vs JSON 二選一，不可混用
  extract:                               # HTML 範例
    item_selector: "article.news-item"   # 必填
    link_selector: "a"                   # 選填，預設 a
    link_attr: "href"                    # 選填，預設 href，text 表示取文字
  # extract:                             # JSON 範例（二選一）
  #   items_path: "data.list"            # JSON path，必填
  #   url_field: "url"                   # 必填
  #   url_template: "https://example.com{url}"  # 選填，{url} 佔位符；空字串走 urljoin

  pagination:                            # $defs/pagination
    enabled: true                        # 必填 boolean
    start: 1                             # integer >=1，預設 1

  sources:                               # 必填 >=1 項
    # 來源 1：預設列表（不含 {keyword}，符合 §8.2 預設來源定義）
    - url: "https://example.com/news?page={page}&cat={category}"
      # method/type/pagination/extract 可覆蓋繼承預設
      # extract 為 $defs/list_extract_partial 深合併，全選填

    # 來源 2：關鍵字搜尋（宣告支援 {keyword}）
    - url: "https://example.com/search?q={keyword}&page={page}"
      type: "html"
      extract:
        item_selector: "div.search-item"
        link_selector: "a.title"
        link_attr: "href"

    # 來源 3：JSON 列表覆蓋
    - url: "https://example.com/api/list?page={page}"
      type: "json"
      method: "GET"
      extract:
        items_path: "result.articles"
        url_field: "slug"
        url_template: "https://example.com/article/{url}"
      pagination:
        enabled: true
        start: 1

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
| `list_page` vs `sources[].extract` | 前者 `$defs/list_extract` 含 `required`，後者 `$defs/list_extract_partial` 全選填、深合併（`src/crawler/site_crawler.py:88-98`） |
| `article_page` `allOf` | `type: html` 時物件必含 `selector`，`type: json` 必含 `path`，混用驗證失敗；`as` 僅 `text`/`datetime`，`attr` 值不再受限 |
| `classifier_source` `oneOf` 4 型 | `source` 決定形態：`url` 需 `regex`、`html` 需 `selector`、`json` 需 `from`+`path`、`keyword` 需 `rules`；`mapping`/`split` 通用；`html` 的 `multiple`/`join` 互斥 |
| `classifier_mapping` | `object<string,string>`，未命中保留原值（`src/crawler/classifier.py:187-193`） |
