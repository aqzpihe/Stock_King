-- ============================================================
-- Schema v1：大環境宏觀資料
-- ============================================================

-- 長表：所有原始指標數據（對應 data/data.csv）
CREATE TABLE IF NOT EXISTS macro_raw (
    observation_date  DATE    NOT NULL,
    ticker            TEXT    NOT NULL,
    raw_value         NUMERIC,
    frequency         TEXT,       -- D / W / M / Q
    lag_category      TEXT,       -- Leading / Real-time / Lagging / Confirming
    dimension         INTEGER,    -- 1~4 四大面向
    updated_at        TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (observation_date, ticker)
);

-- 評分結果日表（對應 data/scores.csv）
CREATE TABLE IF NOT EXISTS macro_scores (
    observation_date        DATE PRIMARY KEY,
    score_credit_spread     NUMERIC,
    score_mortgage_spread   NUMERIC,
    score_drblacbs          NUMERIC,
    score_net_liq_chg       NUMERIC,
    score_dff               NUMERIC,
    score_t10y2y            NUMERIC,
    score_jtsjol            NUMERIC,
    score_jtsqur            NUMERIC,
    score_babatotalsaus     NUMERIC,
    score_indpro            NUMERIC,
    score_payems            NUMERIC,
    score_dtwexbgs          NUMERIC,
    score_emvexrates        NUMERIC,
    score_tic_grand_total   NUMERIC,
    dim1_score              NUMERIC,
    dim2_score              NUMERIC,
    dim2_credibility        NUMERIC,
    dim3_score              NUMERIC,
    dim4_score              NUMERIC,
    macro_score             NUMERIC,
    regime                  INTEGER,
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

-- 權限
GRANT ALL ON public.macro_raw    TO service_role;
GRANT ALL ON public.macro_scores TO service_role;
