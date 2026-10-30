# 儲存設定說明

儲存設定位於 `config/settings.yaml` 的 `json_storage` 與 `database` 區塊，由 `config/schema/settings.schema.json` 驗證。兩者可同時啟用，由 `src/core/engine.py:build_engine` 掛載。

## 完整範例

```yaml
json_storage:
  enabled: true
  output_dir: "data/json"

database:
  enabled: true
  url: "sqlite:///data/articles.db"
  # PostgreSQL: "postgresql://user:pass@localhost:5432/news_db"
  # MySQL: "mysql+pymysql://user:pass@localhost:3306/news_db"
  echo: false
  pool_size: 5
  max_overflow: 10
```

## 欄位說明

### json_storage

| 欄位 | 說明 | 預設值 |
|------|------|--------|
| `json_storage.enabled` | 是否啟用 JSON 輸出 | `true` |
| `json_storage.output_dir` | JSON 輸出目錄 | `data/json` |

JSON 為 batch 模式，`close` 時才寫檔，檔名為 `{source}_{YYYYmmdd_HHMMSS}.json`（`date` 為時間戳）。

### database

| 欄位 | 說明 | 預設值 |
|------|------|--------|
| `database.enabled` | 是否啟用資料庫儲存 | `true` |
| `database.url` | 資料庫連線字串（SQLAlchemy） | `sqlite:///data/articles.db` |
| `database.echo` | 是否輸出 SQL 語句 | `false` |
| `database.pool_size` | 連線池大小（僅非 SQLite backend 生效） | `5` |
| `database.max_overflow` | 連線池溢位上限（僅非 SQLite backend 生效） | `10` |

`pool_size` 與 `max_overflow` 僅對非 SQLite 後端生效，SQLite 會由儲存層忽略。

## 去重機制

寫入前先以 `url` 查詢是否已存在（`data.url` 優先於 `item.url`），存在則跳過；`url` 欄位另有 unique 約束做第二層防護，若併發插入撞約束會捕獲 `IntegrityError` 後跳過，不會中斷爬取。

## 增量爬取支援

`BaseStorage.known_urls() -> set[str]` 供引擎在啟動時取得已存網址（`engine.skip_seen_urls`，預設開啟）：

- 資料庫後端以單次 `SELECT url FROM articles` 查詢，失敗時記錄 error 並回傳空集合。
- JSON 後端為 batch 寫檔，無既有資料可查，固定回傳空集合。
