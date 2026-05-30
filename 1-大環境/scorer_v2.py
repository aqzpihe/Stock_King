"""
scorer_v2.py - Phase 2 量化模型：EWMA 標準化與四大面向 Score 計算
================================================================

理論基礎：
  - Bernanke「外部融資溢酬」(External Finance Premium)
  - Lucas 批判：政策預期與參數漂移 → 使用 EWMA 替代固定窗口

演算法管線：
  1. 從 data.csv 載入長表，pivot 為寬表（日期 × ticker）
  2. 頻率對齊：所有指標 forward-fill 至每日
  3. §4.4 合成指標計算（先於 Z-Score）
  4. §4.1 EWMA Z-Score + 極性乘數 + Sigmoid 壓縮
  5. §4.2 體制可信度 Credibility (%)
  6. §4.3 四大面向加權聚合
  7. 輸出 data/scores.csv

執行：
  python scorer_v2.py
"""

import os
import json
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
INPUT_CSV  = DATA_DIR / "data.csv"
OUTPUT_CSV = DATA_DIR / "scores.csv"

# ══════════════════════════════════════════════════════════════
# §4.1 參數配置
# ══════════════════════════════════════════════════════════════

# EWMA Half-life（交易日）：24~36 個月 → 約 504~756 交易日
EWMA_HALFLIFE = 504          # 24 個月 (保守值)
EWMA_MIN_PERIODS = 252       # 至少 1 年觀測值才開始計算

# Sigmoid 平滑參數
SIGMOID_K = 0.5

# ──────────────────────────────────────────────
# §4.1 極性定義 (Directionality)
# D_i = 1  → 數值上升 = 環境轉好
# D_i = -1 → 數值上升 = 環境惡化
# ──────────────────────────────────────────────
DIRECTIONALITY = {
    # === 面向一 合成指標 ===
    "CREDIT_SPREAD":   -1,    # 信用利差上升 = 惡化
    "MORTGAGE_SPREAD": -1,    # 房貸利差上升 = 惡化
    "DRBLACBS":        -1,    # 違約率上升 = 惡化

    # === 面向二 ===
    "NET_LIQ_CHG":     +1,    # 淨流動性增加 = 寬鬆
    "DFF":             -1,    # 聯邦基金利率上升 = 緊縮
    "T10Y2Y":          +1,    # 利差為正 = 正常曲線 (倒掛=負值=惡化)

    # === 面向三 ===
    "JTSJOL":          +1,    # 職缺數增加 = 經濟好
    "JTSQUR":          +1,    # 辭職率上升 = 勞動者信心
    "BABATOTALSAUS":   +1,    # 新企業成立 = 創造性破壞動能
    "INDPRO":          +1,    # 工業生產上升 = 經濟好
    "PAYEMS":          +1,    # 非農增加 = 經濟好

    # === 面向四 ===
    "DTWEXBGS":        -1,    # 美元急升 = 新興市場壓力
    "EMVEXRATES":      -1,    # 匯率波動上升 = 風險
    "TIC_GRAND_TOTAL_MOM": +1, # 外資增持美債 = 避險需求/信心
}


# ══════════════════════════════════════════════════════════════
# 核心數學函數
# ══════════════════════════════════════════════════════════════

def ewma_zscore(series: pd.Series, halflife: int = EWMA_HALFLIFE,
                min_periods: int = EWMA_MIN_PERIODS) -> pd.Series:
    """
    指數加權移動平均 Z-Score（解決 Lucas 批判的參數漂移問題）

    Z_t = (X_t - EWMA_t) / EWMSD_t
    """
    ewma_mean = series.ewm(halflife=halflife, min_periods=min_periods).mean()
    ewma_std  = series.ewm(halflife=halflife, min_periods=min_periods).std()

    # 避免除以零
    ewma_std = ewma_std.replace(0, np.nan)

    z = (series - ewma_mean) / ewma_std
    return z


def sigmoid_compress(z: pd.Series, k: float = SIGMOID_K) -> pd.Series:
    """
    Sigmoid 壓縮至 [-1, 1]：
    Score = 2 / (1 + e^(-k * Z)) - 1
    """
    return 2.0 / (1.0 + np.exp(-k * z)) - 1.0


def compute_indicator_score(series: pd.Series, directionality: int,
                            halflife: int = EWMA_HALFLIFE) -> pd.Series:
    """
    單一指標完整管線：
    1. EWMA Z-Score
    2. 極性乘數
    3. Sigmoid 壓縮 → [-1, 1]
    """
    z = ewma_zscore(series, halflife=halflife)
    z_directed = directionality * z
    score = sigmoid_compress(z_directed)
    return score


# ══════════════════════════════════════════════════════════════
# §4.4 合成指標計算
# ══════════════════════════════════════════════════════════════

def compute_synthetic_indicators(wide: pd.DataFrame) -> pd.DataFrame:
    """
    在 Z-Score 之前計算合成指標：
    1. CREDIT_SPREAD   = DBAA - DGS10 (企業信用利差)
    2. MORTGAGE_SPREAD = MORTGAGE30US - DGS10 (房貸信用利差)
    3. NET_LIQUIDITY   = WALCL - WTREGEN - RRPONTSYD
    4. NET_LIQ_CHG     = NET_LIQUIDITY 的週變動率
    """
    df = wide.copy()

    # 1. 企業信用利差 (Bernanke 外部融資溢酬)
    if "DBAA" in df.columns and "DGS10" in df.columns:
        df["CREDIT_SPREAD"] = df["DBAA"] - df["DGS10"]
        print("  [Synthetic] CREDIT_SPREAD = DBAA - DGS10")

    # 2. 房貸信用利差
    if "MORTGAGE30US" in df.columns and "DGS10" in df.columns:
        df["MORTGAGE_SPREAD"] = df["MORTGAGE30US"] - df["DGS10"]
        print("  [Synthetic] MORTGAGE_SPREAD = MORTGAGE30US - DGS10")

    # 3. 聯準會實質淨流動性
    liq_cols = ["WALCL", "WTREGEN", "RRPONTSYD"]
    if all(c in df.columns for c in liq_cols):
        # WALCL 單位是百萬美元，WTREGEN 與 RRPONTSYD 單位是十億
        # FRED 的 WALCL 單位 = Millions，WTREGEN = Millions，RRPONTSYD = Billions
        # 實際上 RRPONTSYD 在 FRED 上是 Billions，先統一除以 1000
        df["NET_LIQUIDITY"] = df["WALCL"] / 1000 - df["WTREGEN"] - df["RRPONTSYD"]

        # 4. 週變動率（用 5 個交易日的差值）
        df["NET_LIQ_CHG"] = df["NET_LIQUIDITY"].diff(periods=5)
        print("  [Synthetic] NET_LIQUIDITY = WALCL/1000 - WTREGEN - RRPONTSYD")
        print("  [Synthetic] NET_LIQ_CHG = NET_LIQUIDITY.diff(5)")

    return df


# ══════════════════════════════════════════════════════════════
# §4.2 體制可信度 (Credibility %)
# ══════════════════════════════════════════════════════════════

def compute_credibility(wide: pd.DataFrame) -> pd.Series:
    """
    Credibility (%) = Max(0, 100% - |POLYMARKET_RATE - SEP_FFR_CURRENT| * 50)

    量化市場資金定價與央行官方指引之間的「預期落差」
    注意：SEP_FFR_CURRENT 為季度資料，需要 forward-fill
    """
    sep_col = "SEP_FFR_CURRENT"
    poly_col = "POLYMARKET_RATE"

    if sep_col not in wide.columns or poly_col not in wide.columns:
        print("  [WARN] Credibility: 缺少 SEP_FFR_CURRENT 或 POLYMARKET_RATE")
        return pd.Series(np.nan, index=wide.index, name="CREDIBILITY_PCT")

    gap = (wide[poly_col] - wide[sep_col]).abs()
    credibility = (100.0 - gap * 50).clip(lower=0)
    credibility.name = "CREDIBILITY_PCT"

    valid = credibility.dropna()
    if len(valid) > 0:
        print(f"  [Credibility] 最新值: {valid.iloc[-1]:.1f}%  "
              f"(range: {valid.min():.1f}% ~ {valid.max():.1f}%)")

    return credibility


# ══════════════════════════════════════════════════════════════
# §4.3 四大面向加權聚合
# ══════════════════════════════════════════════════════════════

def aggregate_dimensions(scores_df: pd.DataFrame,
                         credibility: pd.Series) -> pd.DataFrame:
    """
    依據理論權重聚合四大面向分數。

    面向 1：信用市場健康度 [-1, 1]
        70% Real-time: CREDIT_SPREAD, MORTGAGE_SPREAD
        30% Lagging:   DRBLACBS

    面向 2：政策預期與流動性 [-2, 2]
        60% Real-time: NET_LIQ_CHG, DFF
        40% Leading:   T10Y2Y
        (+ Credibility % 獨立輸出)

    面向 3：國家經濟動能 [-1, 1]
        70% Leading:  JTSJOL, JTSQUR, BABATOTALSAUS
        30% Lagging:  INDPRO, PAYEMS

    面向 4：國際資本與匯率 [-1, 1]
        70% Real-time: DTWEXBGS, EMVEXRATES
        30% Lagging:   TIC_GRAND_TOTAL_MOM
    """
    result = pd.DataFrame(index=scores_df.index)

    # ── 面向一：信用市場健康度 ──────────────────────
    dim1_rt = _safe_mean(scores_df, ["CREDIT_SPREAD", "MORTGAGE_SPREAD"])
    dim1_lag = _safe_col(scores_df, "DRBLACBS")
    result["DIM1_SCORE"] = 0.70 * dim1_rt + 0.30 * dim1_lag
    result["DIM1_SCORE"] = result["DIM1_SCORE"].clip(-1, 1)

    # ── 面向二：政策預期與流動性 ────────────────────
    dim2_rt = _safe_mean(scores_df, ["NET_LIQ_CHG", "DFF"])
    dim2_lead = _safe_col(scores_df, "T10Y2Y")
    result["DIM2_SCORE"] = (0.60 * dim2_rt + 0.40 * dim2_lead) * 2  # scale to [-2, 2]
    result["DIM2_SCORE"] = result["DIM2_SCORE"].clip(-2, 2)
    result["DIM2_CREDIBILITY"] = credibility

    # ── 面向三：國家經濟動能 ───────────────────────
    dim3_lead = _safe_mean(scores_df, ["JTSJOL", "JTSQUR", "BABATOTALSAUS"])
    dim3_lag = _safe_mean(scores_df, ["INDPRO", "PAYEMS"])
    result["DIM3_SCORE"] = 0.70 * dim3_lead + 0.30 * dim3_lag
    result["DIM3_SCORE"] = result["DIM3_SCORE"].clip(-1, 1)

    # ── 面向四：國際資本與匯率 ─────────────────────
    dim4_rt = _safe_mean(scores_df, ["DTWEXBGS", "EMVEXRATES"])
    dim4_lag = _safe_col(scores_df, "TIC_GRAND_TOTAL_MOM")
    result["DIM4_SCORE"] = 0.70 * dim4_rt + 0.30 * dim4_lag
    result["DIM4_SCORE"] = result["DIM4_SCORE"].clip(-1, 1)

    # ── 總體 Macro Score (加權平均) ────────────────
    # 四個面向先歸一化到同一 scale [-1, 1]
    d2_norm = result["DIM2_SCORE"] / 2.0  # [-2,2] → [-1,1]
    result["MACRO_SCORE"] = (
        0.30 * result["DIM1_SCORE"] +
        0.30 * d2_norm +
        0.25 * result["DIM3_SCORE"] +
        0.15 * result["DIM4_SCORE"]
    )

    # ── Regime 判定 ────────────────────────────────
    result["REGIME"] = result["MACRO_SCORE"].apply(_to_regime)

    return result


def _safe_col(df: pd.DataFrame, col: str) -> pd.Series:
    """安全取得欄位，不存在時回傳 0"""
    if col in df.columns:
        return df[col].fillna(0)
    return pd.Series(0, index=df.index)


def _safe_mean(df: pd.DataFrame, cols: list) -> pd.Series:
    """安全計算多欄平均，略過不存在的欄位"""
    existing = [c for c in cols if c in df.columns]
    if not existing:
        return pd.Series(0, index=df.index)
    return df[existing].mean(axis=1).fillna(0)


def _to_regime(score):
    """
    Regime 判定 (基於歸一化後的 MACRO_SCORE [-1, 1])
    """
    if pd.isna(score):
        return np.nan
    if score >= 0.3:
        return 3    # 寬鬆 / 有利風險資產
    elif score >= 0:
        return 2    # 中性偏多
    elif score >= -0.3:
        return 1    # 中性偏保守
    else:
        return 0    # 緊縮 / 風險極高


REGIME_LABELS = {
    3: "Expansionary",
    2: "Neutral-Bullish",
    1: "Neutral-Cautious",
    0: "Contractionary",
}


# ══════════════════════════════════════════════════════════════
# 主程式
# ══════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("  scorer_v2.py - Phase 2 量化模型")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # ── Step 1: 載入 data.csv 並 pivot 為寬表 ──────────
    print("\n[Step 1] 載入 data.csv ...")
    raw = pd.read_csv(INPUT_CSV, parse_dates=["observation_date"])
    raw = raw.sort_values("observation_date")

    # Pivot: 每日一行，每個 ticker 一欄
    wide = raw.pivot_table(
        index="observation_date",
        columns="ticker",
        values="raw_value",
        aggfunc="last"
    )
    wide = wide.sort_index()
    print(f"  Pivot 結果: {wide.shape[0]} 天 x {wide.shape[1]} tickers")
    print(f"  日期範圍: {wide.index.min().date()} ~ {wide.index.max().date()}")

    # ── Step 2: 頻率對齊（forward-fill） ──────────────
    print("\n[Step 2] 頻率對齊 (forward-fill) ...")

    # 建立完整日期索引（僅交易日，週一到週五）
    full_idx = pd.bdate_range(start=wide.index.min(), end=wide.index.max())
    wide = wide.reindex(full_idx)
    wide.index.name = "observation_date"

    # Forward-fill：低頻指標向前填充到每日
    wide = wide.ffill()
    print(f"  對齊後: {wide.shape[0]} 交易日 x {wide.shape[1]} 欄")

    # ── Step 3: 合成指標計算 ──────────────────────────
    print("\n[Step 3] 合成指標計算 (S4.4) ...")
    wide = compute_synthetic_indicators(wide)

    # ── Step 4: 逐指標 EWMA Z-Score + Sigmoid ────────
    print("\n[Step 4] EWMA Z-Score + Sigmoid 壓縮 (S4.1) ...")

    # 需要計算 score 的指標清單
    score_tickers = list(DIRECTIONALITY.keys())
    scores = pd.DataFrame(index=wide.index)

    for ticker in score_tickers:
        if ticker not in wide.columns:
            print(f"  [SKIP] {ticker} 不在資料中")
            continue

        series = wide[ticker].dropna()
        if len(series) < EWMA_MIN_PERIODS:
            print(f"  [WARN] {ticker} 只有 {len(series)} 天資料 "
                  f"(需要 >= {EWMA_MIN_PERIODS})，仍嘗試計算")

        d = DIRECTIONALITY[ticker]
        s = compute_indicator_score(wide[ticker], directionality=d)
        scores[ticker] = s

        valid = s.dropna()
        if len(valid) > 0:
            latest = valid.iloc[-1]
            print(f"  {ticker:25s} D={d:+d}  "
                  f"latest={latest:+.4f}  "
                  f"range=[{valid.min():+.4f}, {valid.max():+.4f}]")

    # ── Step 5: 體制可信度 ────────────────────────────
    print("\n[Step 5] 體制可信度 (S4.2) ...")
    credibility = compute_credibility(wide)

    # ── Step 6: 四大面向加權聚合 ──────────────────────
    print("\n[Step 6] 四大面向加權聚合 (S4.3) ...")
    dim_scores = aggregate_dimensions(scores, credibility)

    # ── Step 7: 組合輸出 ─────────────────────────────
    print("\n[Step 7] 組合輸出 ...")

    # 合併所有中間結果
    output = pd.DataFrame(index=wide.index)
    output.index.name = "observation_date"

    # 原始合成指標
    for col in ["CREDIT_SPREAD", "MORTGAGE_SPREAD", "NET_LIQUIDITY", "NET_LIQ_CHG"]:
        if col in wide.columns:
            output[f"RAW_{col}"] = wide[col]

    # 各指標的 score
    for col in scores.columns:
        output[f"SCORE_{col}"] = scores[col]

    # 面向分數
    for col in dim_scores.columns:
        output[col] = dim_scores[col]

    # 只保留有有效資料的行
    output = output.dropna(subset=["MACRO_SCORE"])

    # 儲存
    os.makedirs(DATA_DIR, exist_ok=True)
    output.to_csv(OUTPUT_CSV, encoding="utf-8")

    # ── 統計報告 ─────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"  [DONE] scores.csv 產出完成")
    print(f"  路徑: {OUTPUT_CSV}")
    print(f"  有效天數: {len(output):,}")
    print(f"  日期範圍: {output.index.min().date()} ~ {output.index.max().date()}")

    latest = output.iloc[-1]
    print(f"\n  === 最新分數 ({output.index[-1].date()}) ===")
    print(f"  面向一 (信用市場):   {latest['DIM1_SCORE']:+.4f}  [-1, 1]")
    print(f"  面向二 (政策流動性): {latest['DIM2_SCORE']:+.4f}  [-2, 2]")
    if not pd.isna(latest.get("DIM2_CREDIBILITY", np.nan)):
        print(f"    可信度:            {latest['DIM2_CREDIBILITY']:.1f}%")
    print(f"  面向三 (經濟動能):   {latest['DIM3_SCORE']:+.4f}  [-1, 1]")
    print(f"  面向四 (國際資本):   {latest['DIM4_SCORE']:+.4f}  [-1, 1]")
    print(f"  MACRO_SCORE:         {latest['MACRO_SCORE']:+.4f}  [-1, 1]")
    regime = int(latest["REGIME"]) if not pd.isna(latest["REGIME"]) else -1
    print(f"  REGIME:              {regime} ({REGIME_LABELS.get(regime, '?')})")

    # 各面向歷史統計
    print(f"\n  === 歷史統計 ===")
    for col, label in [("DIM1_SCORE", "面向一"), ("DIM2_SCORE", "面向二"),
                        ("DIM3_SCORE", "面向三"), ("DIM4_SCORE", "面向四"),
                        ("MACRO_SCORE", "總分")]:
        s = output[col].dropna()
        if len(s) > 0:
            print(f"  {label:8s}: mean={s.mean():+.4f}  "
                  f"std={s.std():.4f}  "
                  f"min={s.min():+.4f}  max={s.max():+.4f}")

    print(f"{'=' * 60}\n")
    return output


if __name__ == "__main__":
    main()
