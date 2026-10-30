# 全域設定說明

全域設定檔為 `config/settings.yaml`，由 `config/schema/settings.schema.json` 嚴格驗證。`config/category_normalization.yaml` 會由 `Settings` 自動合併至 `category_normalization` 欄位（兩處同時存在時以 `settings.yaml` 內的值優先）。

## 設定目錄解析

程式不再假設從專案根目錄執行。設定目錄的解析順序（`web_harvester/utils/config.py:resolve_config_dir`）：

1. CLI `--config-dir <dir>`
2. 環境變數 `WEB_HARVESTER_CONFIG_DIR`
3. 目前工作目錄下的 `config/`
4. 由目前工作目錄逐層向上的 `config/`
5. `~/.config/web-harvester`

候選目錄必須含有 `settings.yaml` 才算命中。明確指定的目錄（來源 1、2）若不含 `settings.yaml` 會直接報錯，不會靜默退回其他路徑。全部落空時拋 `ConfigDirNotFound`，訊息會列出所有嘗試過的路徑。

## 完整範例

```yaml
app:
  name: "news-crawler"
  version: "1.0.0"

engine:
  mode: "sync"                # sync | async
  max_concurrency: 10
  request_timeout: 30
  download_delay: 1.0
  max_retries: 3              # 失敗請求最大嘗試次數（僅可重試錯誤）
  skip_seen_urls: true        # 啟動時略過儲存後端已存的 URL
  retry:                      # 指數回退設定
    base_delay: 1.0           # 第一次重試前等待秒數
    max_delay: 30.0           # 單次回退延遲上限（秒）
    multiplier: 2.0           # 每次嘗試的成長倍率
    jitter: "full"            # none | full | equal
    respect_retry_after: true # 是否尊重 Retry-After（以 max_delay 封頂）

request:
  user_agent: "web-harvester/1.0"
  verify_ssl: true
  respect_robots: true        # 請求前檢查 robots.txt；站點可覆寫
  http_client: "curl_cffi"    # curl_cffi（預設，支援 TLS 指紋） | httpx（備援）
  impersonate: "chrome131"    # 瀏覽器偽裝，需 http_client=curl_cffi；"" 表示停用
  # ja3: ""                   # 自訂 JA3，僅 impersonate="" 時生效
  # akamai: ""                # 自訂 Akamai，僅 impersonate="" 時生效

limits:
  max_items: 100
  max_pages: 3
  stop_on_duplicate: false
  timeout: 180

category_normalization: {}
```

日誌與儲存設定請見 [logging.md](logging.md) 與 [storage.md](storage.md)。

## 欄位說明

### app

| 欄位 | 說明 | 預設值 |
|------|------|--------|
| `app.name` | 應用程式名稱 | `news-crawler` |
| `app.version` | 版本號 | `1.0.0` |

### engine

| 欄位 | 說明 | 預設值 |
|------|------|--------|
| `engine.mode` | 執行模式（`sync` / `async`） | `sync` |
| `engine.max_concurrency` | 非同步模式最大並行數 | `10` |
| `engine.request_timeout` | 單一請求逾時（秒）；實際值取 `min(request_timeout, 剩餘的 limits.timeout 預算)` | `30` |
| `engine.download_delay` | 同一網域相鄰請求的最小間隔（秒），`0` 表示停用；不同網域互不影響 | `1.0` |
| `engine.max_retries` | 失敗請求最大嘗試次數（僅可重試錯誤；含首次嘗試） | `3` |
| `engine.retry.base_delay` | 第一次重試前的延遲（秒） | `1.0` |
| `engine.retry.max_delay` | 單次回退延遲上限（秒） | `30.0` |
| `engine.retry.multiplier` | 每次嘗試的指數成長倍率 | `2.0` |
| `engine.retry.jitter` | 抖動模式：`none` / `full` / `equal` | `full` |
| `engine.retry.respect_retry_after` | 是否尊重回應的 `Retry-After` 標頭 | `true` |
| `engine.skip_seen_urls` | 啟動時讀取各儲存後端的 `known_urls()`，略過已存的 URL；CLI `--skip-seen` / `--no-skip-seen` 可臨時覆寫 | `true` |

#### 重試與指數回退行為

- 可重試錯誤：HTTP `408` / `429` / `5xx`、連線或逾時等傳輸錯誤，以及未知網路錯誤（例如 curl_cffi 自身錯誤）；其餘 4xx 直接失敗不重試。
- 延遲計算：`min(base_delay * multiplier ** (已失敗次數 - 1), max_delay)`，再依 `jitter` 加入隨機抖動（`full` 為 `[0, delay]` 均勻分布，`equal` 為 `[delay/2, delay]`，`none` 不加）。
- `respect_retry_after` 為 `true` 時，若錯誤回應帶有 `Retry-After`（支援秒數與 HTTP-date）則採用，但仍以 `max_delay` 封頂，避免伺服器回傳過大值造成長時間等待。
- `max_retries` 為總嘗試次數；最後一次失敗後不再等待，直接放棄該請求。
- 共用實作位於 `web_harvester/core/retry.py`（`BackoffPolicy` 等），sync / async 模式行為一致。

### request

| 欄位 | 說明 | 預設值 |
|------|------|--------|
| `request.user_agent` | 全域請求的 User-Agent，未啟用 impersonate 時套用到所有請求；啟用 impersonate 時由瀏覽器指紋覆蓋 | `web-harvester/1.0` |
| `request.verify_ssl` | 是否驗證 SSL 憑證（僅開發測試時關閉） | `true` |
| `request.respect_robots` | 請求前檢查目標網域的 robots.txt；站點 `request.respect_robots` 可覆寫本站行為 | `true` |
| `request.http_client` | HTTP 實作：`curl_cffi`（預設，支援 TLS 指紋偽裝）或 `httpx`（備援，無偽裝）；`curl_cffi` 未安裝時自動回落至 `httpx` | `curl_cffi` |
| `request.impersonate` | 瀏覽器偽裝目標，僅 `http_client=curl_cffi` 時生效；`""` 表示停用 | `chrome131` |
| `request.ja3` | 自訂 JA3 字串，僅 `impersonate=""` 且 `http_client=curl_cffi` 時生效；有 impersonate 時被忽略並記 warning | - |
| `request.akamai` | 自訂 Akamai HTTP/2 指紋，僅 `impersonate=""` 且 `http_client=curl_cffi` 時生效 | - |

支援的 `impersonate` 枚舉（`config/schema/settings.schema.json`）：`chrome99`/`chrome100`/`chrome101`/`chrome104`/`chrome107`/`chrome110`/`chrome116`/`chrome119`/`chrome120`/`chrome122`/`chrome124`/`chrome131`/`chrome131_android`/`safari15_3`/`safari15_5`/`safari17_0`/`safari17_2_ios`/`safari18_0`/`safari18_0_ios`/`firefox133`/`edge101`/`edge122`/`""`。實作位於 `web_harvester/core/http_client/factory.py:build_http_client` / `web_harvester/core/http_client/curl_cffi_client.py:CurlCffiClient`（常數見 `constants.py`，抽象見 `base.py`），引擎透過 `CrawlerEngine._http_client` 委派（`web_harvester/core/engine.py`）。

### limits

各站全域預設值，站點未覆寫時生效。相關說明亦見 [site-config.md](site-config.md)。

| 欄位 | 說明 | 預設值 |
|------|------|--------|
| `limits.max_items` | 最大爬取筆數，達到即停止；非同步模式會停止派發新請求，但已在傳輸中的請求仍可能完成，因此可能略高於設定值 | `100` |
| `limits.max_pages` | 最大爬取頁數上限（唯一權威值，`pagination` 只管 `enabled`/`type`/`start`/`next_cursor_path`） | `3` |
| `limits.stop_on_duplicate` | 遇到重複 URL 即停止；未開啟則跳過繼續 | `false` |
| `limits.timeout` | 整體爬取時間上限（秒）；會換算成每個請求的剩餘預算，非同步模式以 `asyncio.wait_for` 取消逾時請求 | `180` |

### category_normalization

跨站分類統一對應表（原始名 → 統一值），定義於 `config/category_normalization.yaml`，詳見 [site-config.md](site-config.md) 分類機制章節。

| 欄位 | 說明 | 預設值 |
|------|------|--------|
| `category_normalization` | 對應表物件 | `{}` |

## 爬取限制的三層合併與 CLI 覆寫

最終值採逐欄位、高優先權覆寫：**CLI 參數 > 站點 `limits`（`config/sites/<name>.yaml` 選用）> 全域 `limits`（本檔）> 程式碼預設**。未指定的欄位沿用較低層的值。

可透過 CLI 參數臨時覆寫（僅本次執行生效，不寫回設定檔），適用於所有站點：

```bash
web-harvester --site udn_news --max-items 50
web-harvester --site udn_news --max-pages 5 --timeout 120
web-harvester --site udn_news --no-stop-on-duplicate
```

| 參數 | 覆寫欄位 | 說明 |
|------|---------|------|
| `--max-items N` | `limits.max_items` | 收集達 N 筆即停止（>= 1） |
| `--max-pages N` | `limits.max_pages` | 爬取列表頁數上限（>= 1） |
| `--stop-on-duplicate` / `--no-stop-on-duplicate` | `limits.stop_on_duplicate` | 遇到重複 URL 是否停止 |
| `--timeout SEC` | `limits.timeout` | 整體爬取逾時（秒，> 0） |
| `--skip-seen` / `--no-skip-seen` | `engine.skip_seen_urls` | 是否略過儲存後端已存的 URL |
| `--dry-run` | 無（僅本次執行） | 只請求列表頁並統計可抓文章數，不抓文章頁、不寫入 |

## 增量爬取

`engine.skip_seen_urls` 預設為 `true`。引擎在 `run()` 開頭 union 各儲存後端的 `known_urls()`，
列表解析出的 URL 若已存在則不發出請求，並計入統計的 `skipped known URLs`。

- 只有資料庫後端能提供歷史網址；JSON 後端為 batch 寫檔，`known_urls()` 回空集合。
- 搭配 `limits.stop_on_duplicate: true` 時，遇到第一筆已知 URL 即中止該輪，可用最少請求補抓最新文章。
- CLI `--skip-seen` / `--no-skip-seen` 僅覆寫本次執行的行為。

## robots.txt 檢查

`request.respect_robots` 預設為 `true`，站點層級的 `request.respect_robots` 優先於全域設定。
實作位於 `web_harvester/core/robots.py`。

- 以 origin（scheme + host + port）為快取單位，同一次執行對每個 origin 只抓一次 robots.txt。
- robots.txt 回 4xx 時視為允許全部；回 5xx 或連線失敗時記 warning、跳過該次請求，且不保留結果（下次執行重新嘗試）。
- 被拒絕的 URL 計入統計的 `skipped by robots.txt`，不會寫入儲存後端。
- 未實作 `Crawl-delay` 覆寫；請求間隔仍由 `engine.download_delay` 決定。

## Schema 驗證

所有設定檔在載入時會透過 [JSON Schema](https://json-schema.org/) 進行嚴格驗證，欄位打錯或型別不符時會在載入階段直接拋出 `ConfigValidationError`。

- `config/schema/settings.schema.json`：驗證 `config/settings.yaml`
- `config/schema/site.schema.json`：驗證 `config/sites/*.yaml`（詳見 [site-config.md](site-config.md)）

全域設定的驗證內容包含：

- 必填欄位（`app.name`、`app.version`、`engine.mode`）
- 欄位型別與數值範圍（如 `engine.max_concurrency` 須為正整數）
- 枚舉值（`engine.mode` 僅允許 `sync` / `async`、`logging.level` 僅允許 `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL`）
- 未知欄位攔截（`additionalProperties: false`），打錯字會直接報錯
