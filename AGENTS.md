# AGENTS.md

設定檔驅動的新聞爬蟲框架（Python）。無測試框架、無 lint/typecheck 設定。

## 開發指令

- 執行：`python run.py`（在專案根目錄執行；路徑皆為相對根目錄）
- venv：`.venv`（Python 3.11），啟動：`.venv\Scripts\Activate.ps1`
- 測試：`python -m pytest test`（pytest 於 requirements.txt）；engine 測試用 monkeypatch `CrawlerEngine._process_sync` / `_fetch_async` 跳過真實網路，storage 測試用 pytest `tmp_path`
- 無 lint / formatter / typecheck 設定，改完直接跑測試 + `python run.py`

## 架構與執行流程

```
run.py → Settings (config/settings.yaml) → setup_logging
       → load_site_config("udn_news") → build_engine(settings) → SiteCrawler(site_config) → engine.run(crawler)
```

- 換目標網站：改 `run.py` 的 `load_site_config(...)` 參數（site yaml 檔名不含副檔名），在 `config/sites/<name>.yaml` 新增對應設定
- `engine.mode`（`sync`/`async`）由 `config/settings.yaml` 控制；async 用 `asyncio` + `httpx.AsyncClient`，sync 用 `httpx.Client`
- 全域 `request` 區塊的 `user_agent` / `verify_ssl` 自動套用到所有請求；site 層級 `request.headers/cookies` 僅套用到該站
- 儲存後端由 `build_engine`（engine.py:376）依 settings 掛載：JSON（batch 模式，close 時才寫檔，檔名 `{source}_{date}.json`）+ SQLAlchemy（預設 SQLite）

## Config 與 Schema

- 所有 YAML 載入時以 `config/schema/` 下的 JSON Schema 嚴格驗證（fail-fast，`additionalProperties: false`），違規拋 `ConfigValidationError`（src/utils/config.py:28）
- 修改或新增 config 欄位時，必須同步更新對應 schema（settings.schema.json / site.schema.json），否則載入直接失敗
- site `limits` 語意（同步/非同步都支援）：
  - `max_items`：收集達標即停止
  - `stop_on_duplicate`：遇到重複 URL 即停止；未開啟則跳過繼續
  - `timeout`：整體爬取逾時（秒）
  - `max_pages`：蓋住 `list_page.pagination.max_pages`

## 已知陷阱

- `JSONStorage._append_to_file`（json_storage.py:90）在檔案不存在且 `batch_mode=False` 時有既有 `NameError` bug；預設 `batch_mode=True` 不受影響
- udn 站的文章 selectors 部分回傳 None（site 設定與實際頁面結構不符，既有問題）
- `data/`、`logs/`、`.venv/` 已在 .gitignore

## 規範

- 全域規範（C:\Users\fg562\.config\opencode\AGENTS.md）：程式碼變更須同步更新 README 等文件、全面禁用 emoji
- Commit 採 Conventional Commits 格式（如 `feat(config): ...`），訊息用中文繁體