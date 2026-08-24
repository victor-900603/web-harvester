# 日誌設定說明

日誌設定位於 `config/settings.yaml` 的 `logging` 區塊，由 `config/schema/settings.schema.json` 驗證。

## 完整範例

```yaml
logging:
  level: "INFO"
  format: "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
  file: "logs/crawler.log"
  max_bytes: 10485760         # 10MB
  backup_count: 5
```

## 欄位說明

| 欄位 | 說明 | 預設值 |
|------|------|--------|
| `logging.level` | 日誌等級（`DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL`） | `INFO` |
| `logging.format` | 日誌格式字串 | `%(asctime)s [%(levelname)s] %(name)s: %(message)s` |
| `logging.file` | 日誌檔案路徑 | `logs/crawler.log` |
| `logging.max_bytes` | 單檔大小上限（bytes），超過即輪轉 | `10485760` |
| `logging.backup_count` | 輪轉保留檔數 | `5` |

日誌透過 `colorlog` 輸出彩色終端日誌，並同時寫入檔案（依 `max_bytes` / `backup_count` 輪轉）。
