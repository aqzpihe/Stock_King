-- ============================================================
-- Schema：1-大環境 總經評分模組
-- 包含兩張表：
--   macro_raw    — 原始總經指標（長表）
--   macro_scores — 每日維度評分與 Macro Score
-- 在 Supabase SQL Editor 執行此檔案
-- ============================================================

-- ── 1. macro_raw：原始總經資料 ────────────────────────────────
-- 對應 data/data.csv，格式為長表（一筆 = 一個 ticker 某日的值）
CREATE TABLE IF NOT EXISTS macro_raw (
    observation_date  DATE        NOT NULL,
    ticker            TEXT        NOT NULL,
    raw_value         NUMERIC,
    frequency         TEXT,        -- D / W / M / Q
    lag_category      TEXT,        -- Leading / Real-time / Lagging / Confirming
    dimension         INTEGER,     -- 1=信用 2=政策 3=通膨匯率 4=景氣動能
    updated_at        TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (observation_date, ticker)
);

CREATE INDEX IF NOT EXISTS idx_macro_raw_ticker ON macro_raw(ticker);
CREATE INDEX IF NOT EXISTS idx_macro_raw_date   ON macro_raw(observation_date);

-- ── 2. macro_scores：每日評分結果 ─────────────────────────────
-- 對應 data/scores.csv，一筆 = 一天的所有子指標分數與總分
CREATE TABLE IF NOT EXISTS macro_scores (
    observation_date          DATE    NOT NULL PRIMARY KEY,

    -- 子指標分數（各 ticker 經 EWMA Sigmoid 轉換後的分數）
    score_credit_spread       NUMERIC,   -- 信用利差 (DBAA-DGS10)
    score_mortgage_spread     NUMERIC,   -- 房貸利差 (MORTGAGE30US-DFF)
    score_drblacbs            NUMERIC,   -- 商業貸款違約率
    score_net_liq_chg         NUMERIC,   -- 淨流動性變化 (WALCL-WTREGEN-RRPONTSYD)
    score_dff                 NUMERIC,   -- 聯邦基金利率
    score_t10y2y              NUMERIC,   -- 殖利率曲線斜率 (10Y-2Y)
    score_jtsjol              NUMERIC,   -- 職位空缺數
    score_jtsqur              NUMERIC,   -- 自主辭職率
    score_babatotalsaus       NUMERIC,   -- 新企業成立申請數
    score_indpro              NUMERIC,   -- 工業生產指數
    score_payems              NUMERIC,   -- 非農就業人數
    score_dtwexbgs            NUMERIC,   -- 美元指數
    score_emvexrates          NUMERIC,   -- 匯率波動性
    score_tic_grand_total     NUMERIC,   -- TIC 外資持有美債

    -- 四大面向維度分數
    dim1_score                NUMERIC,   -- 信用與流動性
    dim2_score                NUMERIC,   -- 貨幣政策
    dim2_credibility          NUMERIC,   -- 政策可信度調整
    dim3_score                NUMERIC,   -- 通膨與匯率
    dim4_score                NUMERIC,   -- 景氣動能

    -- 最終總分與 Regime
    macro_score               NUMERIC,   -- 加權總分
    regime                    INTEGER,   -- 0=緊縮 1=中性偏保守 2=中性偏多 3=寬鬆

    updated_at                TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_macro_scores_date ON macro_scores(observation_date);

-- ── 3. 自動更新 updated_at ────────────────────────────────────
-- 若已存在 set_updated_at 函式（2-基本面 schema 已建立），可跳過此段
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_macro_raw_updated_at ON macro_raw;
CREATE TRIGGER trg_macro_raw_updated_at
  BEFORE UPDATE ON macro_raw
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_macro_scores_updated_at ON macro_scores;
CREATE TRIGGER trg_macro_scores_updated_at
  BEFORE UPDATE ON macro_scores
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ── 4. 權限 ───────────────────────────────────────────────────
GRANT ALL ON public.macro_raw    TO service_role;
GRANT ALL ON public.macro_scores TO service_role;
