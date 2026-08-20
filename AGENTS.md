# AGENTS.md

設定檔驅動的新聞爬蟲框架（Python）。無測試框架、無 lint/typecheck 設定。

## 開發指令

- 執行：`python main.py --site <site_id>`（在專案根目錄執行；路徑皆為相對根目錄）；`python main.py --list-sites` 列出可用站點；選用 `--keyword <kw>` 關鍵字搜尋、`--category <名稱>` 分類篩選（可組合，需站點設定 `sources`/`categories`）
- venv：`.venv`（Python 3.11），啟動：`.venv\Scripts\Activate.ps1`
- 測試：`python -m pytest test`（pytest 於 requirements.txt）；engine 測試用 monkeypatch `CrawlerEngine._process_sync` / `_fetch_async` 跳過真實網路，storage 測試用 pytest `tmp_path`
- 無 lint / formatter / typecheck 設定，改完直接跑測試 + `python main.py --site <site_id>`

## 架構與執行流程

```
main.py → Settings (config/settings.yaml) → setup_logging
        → load_site_config(--site 指定的站點) → build_engine(settings) → SiteCrawler(site_config) → engine.run(crawler)
```

- 換目標網站：`python main.py --site <site_id>`（site yaml 檔名不含副檔名），在 `config/sites/<name>.yaml` 新增對應設定
- `engine.mode`（`sync`/`async`）由 `config/settings.yaml` 控制；async 用 `asyncio` + `httpx.AsyncClient`，sync 用 `httpx.Client`
- 列表來源：`list_page.sources` 為必填陣列（每項 `url` 必填），來源 URL 支援 `{page}`/`{keyword}`/`{category}` 佔位符，由 `SiteCrawler._select_list_cfg`（site_crawler.py）依請求篩選選擇來源（精確 → 超集 → 降級 → 預設，結果快取於 `_selected_list_cfg`），`_build_list_url` 填值；`--category` 傳名稱經 `categories` 對應表轉站內值；list_page 層的 method/type/selectors/pagination 為來源的繼承預設（selectors 深合併）
- 全域 `request` 區塊的 `user_agent` / `verify_ssl` 自動套用到所有請求；site 層級 `request.headers/cookies` 僅套用到該站
- 儲存後端由 `build_engine`（engine.py:376）依 settings 掛載：JSON（batch 模式，close 時才寫檔，檔名 `{source}_{date}.json`）+ SQLAlchemy（預設 SQLite）

## Config 與 Schema

- 所有 YAML 載入時以 `config/schema/` 下的 JSON Schema 嚴格驗證（fail-fast，`additionalProperties: false`），違規拋 `ConfigValidationError`（src/utils/config.py:28）
- 修改或新增 config 欄位時，必須同步更新對應 schema（settings.schema.json / site.schema.json），否則載入直接失敗
- `list_page` required 為 `["sources"]`；`sources[*]` 用 `$defs/list_selectors_partial`（部分 selectors，無 required），list_page 層 selectors 用完整 `list_selectors`（oneOf 表單）
- site `limits` 語意（同步/非同步都支援）：
  - `max_items`：收集達標即停止
  - `stop_on_duplicate`：遇到重複 URL 即停止；未開啟則跳過繼續
  - `timeout`：整體爬取逾時（秒）
  - `max_pages`：爬取列表頁數上限（唯一權威值，`pagination` 只管 `enabled`/`start`）

## 已知陷阱

- udn 站的文章 selectors 部分回傳 None（site 設定與實際頁面結構不符，既有問題）
- `data/`、`logs/`、`.venv/` 已在 .gitignore

## 規範

- 全域規範（C:\Users\fg562\.config\opencode\AGENTS.md）：程式碼變更須同步更新 README 等文件、全面禁用 emoji
- Commit 採 Conventional Commits 格式（如 `feat(config): ...`），訊息用中文繁體