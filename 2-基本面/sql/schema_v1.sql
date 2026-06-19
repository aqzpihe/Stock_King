-- ============================================================
-- Schema v1：測試版（6 個年度指標）
-- 在 Supabase SQL Editor 執行此檔案建立資料表
-- ============================================================

-- 公司基本資訊
CREATE TABLE IF NOT EXISTS companies (
    ticker     TEXT PRIMARY KEY,
    name       TEXT,
    exchange   TEXT,
    currency   TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 年度財報（6 個測試指標）
CREATE TABLE IF NOT EXISTS fundamentals_yearly (
    ticker        TEXT    NOT NULL,
    fiscal_year   INTEGER NOT NULL,
    eps           NUMERIC,   -- EPS
    nav           NUMERIC,   -- 每股淨值
    revenue       NUMERIC,   -- 營業收入
    liabilities   NUMERIC,   -- 總負債
    net_cash_flow NUMERIC,   -- 淨現金流
    assets        NUMERIC,   -- 總資產
    updated_at    TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (ticker, fiscal_year)
);

-- 自動更新 updated_at
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_companies_updated_at
  BEFORE UPDATE ON companies
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_fundamentals_yearly_updated_at
  BEFORE UPDATE ON fundamentals_yearly
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
