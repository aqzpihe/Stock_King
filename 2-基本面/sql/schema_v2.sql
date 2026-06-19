-- ============================================================
-- Schema v2：完整季度財報（合併 7 張 sheet 所有欄位）
-- period 格式：'20164' = 2016 財年第 4 季（同 statementdog 原始格式）
-- 在 Supabase SQL Editor 執行此檔案
-- ============================================================

-- 1. 清除舊版季度測試表（若存在）
DROP TABLE IF EXISTS fundamentals_yearly CASCADE;
DROP TABLE IF EXISTS fundamentals CASCADE;

-- 2. 公司基本資訊（保留舊版，ticker 為其他表的外鍵來源）
CREATE TABLE IF NOT EXISTS companies (
    ticker     TEXT PRIMARY KEY,
    name       TEXT,
    exchange   TEXT,
    currency   TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. 完整季度財報寬表
CREATE TABLE IF NOT EXISTS fundamentals (
    ticker   TEXT NOT NULL,
    period   TEXT NOT NULL,  -- e.g. '20164' = FY2016 Q4

    -- === EPS ===
    eps               NUMERIC,   -- 每股盈餘
    eps_ttm           NUMERIC,   -- 近四季 EPS (EPST4Q)
    eps_ttm_avg       NUMERIC,   -- 近四季平均 EPS (EPST4QAvg)
    eps_qoq           NUMERIC,   -- 單季 EPS 季增率 %
    eps_yoy           NUMERIC,   -- EPS 年增率 %
    eps_ttm_qoq       NUMERIC,   -- 近4季 EPS 季增率 %
    eps_ttm_yoy       NUMERIC,   -- 近4季 EPS 年增率 %

    -- === NAV / 股東權益 ===
    nav               NUMERIC,   -- 每股淨值
    equity            NUMERIC,   -- 總股東權益
    common_stocks     NUMERIC,   -- 普通股股本
    retained_earnings NUMERIC,   -- 保留盈餘
    roe               NUMERIC,   -- 單季 ROE %
    roe_ttm           NUMERIC,   -- 近四季 ROE %

    -- === 損益表 ===
    revenue                NUMERIC,  -- 營業收入
    gross_profit           NUMERIC,  -- 毛利
    operating_expenses     NUMERIC,  -- 營業費用
    rd_expenses            NUMERIC,  -- 研發費用
    sga_expenses           NUMERIC,  -- 銷售和管理費用
    operating_income       NUMERIC,  -- 營業利益
    profit_before_tax      NUMERIC,  -- 稅前淨利
    net_income             NUMERIC,  -- 稅後淨利
    net_income_parent      NUMERIC,  -- 母公司業主淨利
    gross_margin           NUMERIC,  -- 毛利率 %
    operating_margin       NUMERIC,  -- 營業利益率 %
    net_income_margin      NUMERIC,  -- 稅後淨利率 %

    -- === 資產負債表：資產 ===
    assets                 NUMERIC,  -- 總資產
    current_assets         NUMERIC,  -- 流動資產
    cash_equivalents       NUMERIC,  -- 現金及約當現金
    short_term_investment  NUMERIC,  -- 短期投資
    accounts_receivable    NUMERIC,  -- 應收帳款及票據
    inventories            NUMERIC,  -- 存貨
    long_term_investment   NUMERIC,  -- 長期投資
    fixed_assets           NUMERIC,  -- 固定資產

    -- === 資產負債表：負債 ===
    liabilities            NUMERIC,  -- 總負債
    current_liabilities    NUMERIC,  -- 流動負債
    long_term_liabilities  NUMERIC,  -- 長期負債
    accounts_payable       NUMERIC,  -- 應付帳款及票據
    advance_receipts       NUMERIC,  -- 預收款項
    short_term_borrowings  NUMERIC,  -- 短期借款和一年內到期長期負債
    debt_ratio             NUMERIC,  -- 負債比 %
    current_ratio          NUMERIC,  -- 流動比
    quick_ratio            NUMERIC,  -- 速動比

    -- === 現金流量表 ===
    operating_cash_flow          NUMERIC,  -- 營業現金流
    investing_cash_flow          NUMERIC,  -- 投資現金流
    financing_cash_flow          NUMERIC,  -- 融資現金流
    free_cash_flow               NUMERIC,  -- 自由現金流
    net_cash_flow                NUMERIC,  -- 淨現金流
    capex                        NUMERIC,  -- 資本支出
    depreciation_amortization    NUMERIC,  -- 折舊與攤銷
    operating_cash_flow_per_share NUMERIC, -- 每股營業現金流入
    free_cash_flow_per_share     NUMERIC,  -- 每股自由現金流入

    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (ticker, period),
    FOREIGN KEY (ticker) REFERENCES companies(ticker) ON DELETE CASCADE
);

-- 4. 索引（常見查詢：單一公司全歷史、某季度所有公司）
CREATE INDEX IF NOT EXISTS idx_fundamentals_ticker ON fundamentals(ticker);
CREATE INDEX IF NOT EXISTS idx_fundamentals_period ON fundamentals(period);

-- 5. 自動更新 updated_at
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_companies_updated_at ON companies;
CREATE TRIGGER trg_companies_updated_at
  BEFORE UPDATE ON companies
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_fundamentals_updated_at ON fundamentals;
CREATE TRIGGER trg_fundamentals_updated_at
  BEFORE UPDATE ON fundamentals
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 6. 權限
GRANT ALL ON public.companies     TO service_role;
GRANT ALL ON public.fundamentals  TO service_role;
