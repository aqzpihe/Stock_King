# 資料庫結構

Supabase 專案：`yxydsxygylpzewumevsz`

---

## 資料表

### `companies`
公司基本資訊，每間公司一列。

| 欄位 | 型別 | 說明 |
|------|------|------|
| `ticker` | TEXT (PK) | 股票代碼，如 NVDA |
| `name` | TEXT | 公司名稱 |
| `exchange` | TEXT | 交易所 |
| `currency` | TEXT | 幣別 |
| `updated_at` | TIMESTAMPTZ | 最後更新時間（自動） |

---

### `fundamentals_yearly`
年度財報指標，以 `(ticker, fiscal_year)` 為主鍵。

| 欄位 | 型別 | 對應 API Key | 中文名稱 |
|------|------|-------------|---------|
| `ticker` | TEXT (PK) | — | 股票代碼 |
| `fiscal_year` | INTEGER (PK) | `TimeFiscalY` | 會計年度 |
| `eps` | NUMERIC | `EPS` | 每股盈餘 |
| `nav` | NUMERIC | `NAV` | 每股淨值 |
| `revenue` | NUMERIC | `Revenue` | 營業收入 |
| `liabilities` | NUMERIC | `Liabilities` | 總負債 |
| `net_cash_flow` | NUMERIC | `NetCashFlow` | 淨現金流 |
| `assets` | NUMERIC | `Assets` | 總資產 |
| `updated_at` | TIMESTAMPTZ | — | 最後更新時間（自動） |

---

## 版本紀錄

| 版本 | 檔案 | 說明 |
|------|------|------|
| v1 | `schema_v1.sql` | 初始建表，6 個年度測試指標 |
