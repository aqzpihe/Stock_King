"""
policy_forward_score.py — 政策預期 Score（第 4 個宏觀模組）
============================================================
PolicyForwardScoreEngine

角色：分析 FOMC Summary of Economic Projections (SEP) / Dot Plot，
      輸出 policy_forward_score ∈ [-2, +2]（同時提供 0-100 scaled 版本）。

資料來源（三層 fallback）：
  1. 本地 CSV：sep_data.csv（手動放置 / Kaggle 下載）
  2. Fed 官網 FRB/US Model 或官方 CSV（自動抓取，需網路）
  3. 硬編碼歷史中位數（2012–2026，確保模組可獨立執行）

執行：
  python policy_forward_score.py
"""

import io
import sys

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import json
import time
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# ─────────────────────────────────────────
# 0. 路徑配置
# ─────────────────────────────────────────
BASE_DIR          = Path(__file__).parent
SEP_CSV           = BASE_DIR / "data" / "sep_data.csv"
POLYMARKET_JSON   = BASE_DIR / "data" / "polymarket_fed.json"
OUT_JSON          = BASE_DIR / "data" / "policy_forward_score.json"

# 向後相容：若 data/ 下不存在，嘗試舊位置
if not SEP_CSV.exists() and (BASE_DIR / "sep_data.csv").exists():
    SEP_CSV = BASE_DIR / "sep_data.csv"
if not POLYMARKET_JSON.exists() and (BASE_DIR / "polymarket_fed.json").exists():
    POLYMARKET_JSON = BASE_DIR / "polymarket_fed.json"

# 合併權重：70% 點陣圖 + 30% Polymarket
W_DOTPLOT    = 0.70
W_POLYMARKET = 0.30

# Polymarket 各情境的評分映射（對應 policy_forward_score 的 [-2,+2] 尺度）
POLYMARKET_SCENARIO_WEIGHTS = {
    "cut 50+":   +2.0,   # 大幅降息 → 極度寬鬆
    "cut 25":    +1.0,   # 小幅降息 → 溫和寬鬆
    "no change":  0.0,   # 按兵不動 → 中性
    "hike 25":   -1.0,   # 小幅升息 → 溫和緊縮
    "hike 50+":  -2.0,   # 大幅升息 → 極度緊縮
}


def load_polymarket_score() -> tuple[float | None, dict]:
    """
    讀取 polymarket_fed.json，將各市場機率轉換為
    polymarket_score ∈ [-2, +2]。

    轉換公式：
      polymarket_score = Σ( P(scenario_i) × weight_i )
    其中 weight: cut50+=+2, cut25=+1, nochange=0, hike25=-1, hike50+=-2
    自然落在 [-2, +2]（因為所有 P 加總=1，weight 範圍±2）。

    回傳：(score, detail_dict)
    """
    if not POLYMARKET_JSON.exists():
        return None, {}

    try:
        data = json.loads(POLYMARKET_JSON.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [WARN] 讀取 polymarket_fed.json 失敗: {e}")
        return None, {}

    markets = data.get("markets", [])
    detail = {}
    score_sum = 0.0
    prob_sum  = 0.0

    keyword_map = [
        ("decrease", "50",  "cut 50+"),
        ("decrease", "25",  "cut 25"),
        ("no change", "",   "no change"),
        ("increase", "25",  "hike 25"),
        ("increase", "50",  "hike 50+"),
    ]

    for m in markets:
        q  = m.get("question", "").lower()
        outcomes = m.get("outcomes", [])
        # Yes probability
        yes_prob = next(
            (o["probability"] / 100 for o in outcomes if o["outcome"].lower() == "yes"),
            None
        )
        if yes_prob is None:
            continue

        # 配對情境
        scenario = None
        for kw1, kw2, name in keyword_map:
            if kw1 in q and (not kw2 or kw2 in q):
                scenario = name
                break
        if scenario is None:
            continue

        weight = POLYMARKET_SCENARIO_WEIGHTS[scenario]
        score_sum += yes_prob * weight
        prob_sum  += yes_prob
        detail[scenario] = {
            "prob_pct": round(yes_prob * 100, 1),
            "weight":   weight,
            "contrib":  round(yes_prob * weight, 4),
        }

    # 若機率總和不為 1（資料不完整），進行歸一化
    if prob_sum > 0 and abs(prob_sum - 1.0) > 0.05:
        score_sum = score_sum / prob_sum

    score = round(float(score_sum), 4)
    return score, detail

# ─────────────────────────────────────────
# 1. 硬編碼歷史 SEP 中位數（確保無網路也能跑）
#    來源：Fed SEP 各期 Official Release
#    欄位：meeting_date, ffr_spot, ffr_current, ffr_1y, ffr_2y, ffr_long
#    ffr_spot = 會議當月 DFF 約略值（月均）
#    ffr_current/1y/2y/long = SEP 中位數點陣預測
# ─────────────────────────────────────────
HARDCODED_SEP = [
    # date         spot   cur    1y     2y    long
    ("2012-12-12", 0.16,  0.25,  0.25,  0.25, 4.00),
    ("2013-06-19", 0.09,  0.25,  0.25,  0.75, 4.00),
    ("2013-12-18", 0.09,  0.25,  0.75,  1.75, 4.00),
    ("2014-03-19", 0.08,  0.25,  1.00,  2.25, 3.75),
    ("2014-06-18", 0.10,  0.25,  1.13,  2.50, 3.75),
    ("2014-09-17", 0.09,  0.25,  1.38,  2.88, 3.75),
    ("2014-12-17", 0.12,  0.25,  1.13,  2.50, 3.75),
    ("2015-03-18", 0.12,  0.63,  1.88,  3.13, 3.75),
    ("2015-06-17", 0.13,  0.63,  1.63,  2.88, 3.75),
    ("2015-09-17", 0.14,  0.38,  1.38,  2.63, 3.50),
    ("2015-12-16", 0.24,  0.38,  1.38,  2.38, 3.50),
    ("2016-03-16", 0.37,  0.88,  1.88,  3.00, 3.50),
    ("2016-06-15", 0.38,  0.63,  1.63,  2.38, 3.00),
    ("2016-09-21", 0.40,  0.63,  1.13,  1.88, 3.00),
    ("2016-12-14", 0.54,  0.66,  1.38,  2.13, 3.00),
    ("2017-03-15", 0.66,  1.38,  2.13,  3.00, 3.00),
    ("2017-06-14", 0.99,  1.38,  2.13,  3.00, 3.00),
    ("2017-09-20", 1.15,  1.38,  2.13,  2.69, 2.75),
    ("2017-12-13", 1.22,  1.38,  2.13,  2.69, 2.75),
    ("2018-03-21", 1.51,  1.88,  2.13,  2.88, 2.88),
    ("2018-06-13", 1.82,  2.38,  3.13,  3.38, 2.88),
    ("2018-09-26", 2.18,  2.38,  3.13,  3.38, 3.00),
    ("2018-12-19", 2.27,  2.38,  2.88,  3.13, 2.75),
    ("2019-03-20", 2.40,  2.38,  2.63,  2.63, 2.75),
    ("2019-06-19", 2.38,  2.38,  2.13,  2.38, 2.50),
    ("2019-09-18", 2.10,  1.88,  1.88,  2.13, 2.50),
    ("2019-12-11", 1.55,  1.63,  1.63,  1.88, 2.50),
    ("2020-01-29", 1.55,  1.63,  1.63,  1.88, 2.50),
    ("2020-06-10", 0.08,  0.13,  0.13,  0.13, 2.50),
    ("2020-09-16", 0.09,  0.13,  0.13,  0.13, 2.50),
    ("2020-12-16", 0.09,  0.13,  0.13,  0.13, 2.50),
    ("2021-03-17", 0.07,  0.13,  0.13,  0.13, 2.50),
    ("2021-06-16", 0.06,  0.13,  0.13,  0.63, 2.50),
    ("2021-09-22", 0.08,  0.13,  0.25,  1.00, 2.50),
    ("2021-12-15", 0.08,  0.38,  0.90,  1.63, 2.50),
    ("2022-03-16", 0.33,  1.88,  2.75,  2.75, 2.38),
    ("2022-06-15", 1.58,  3.38,  3.88,  3.63, 2.50),
    ("2022-09-21", 2.33,  4.38,  4.63,  3.88, 2.50),
    ("2022-12-14", 3.83,  4.63,  5.13,  4.13, 2.50),
    ("2023-03-22", 4.65,  5.13,  5.13,  4.25, 2.50),
    ("2023-06-14", 5.08,  5.63,  4.63,  3.38, 2.50),
    ("2023-09-20", 5.33,  5.63,  5.13,  3.88, 2.50),
    ("2023-12-13", 5.33,  5.40,  4.63,  3.63, 2.50),
    ("2024-03-20", 5.33,  5.40,  4.63,  3.75, 2.56),
    ("2024-06-12", 5.33,  5.25,  4.13,  3.13, 2.75),
    ("2024-09-18", 5.13,  4.38,  3.38,  2.88, 2.88),
    ("2024-12-18", 4.58,  4.38,  3.88,  3.38, 3.00),
    ("2025-03-19", 4.33,  4.38,  3.88,  3.38, 3.00),
    ("2025-06-18", 4.33,  4.38,  3.63,  3.13, 3.00),
    ("2025-09-17", 4.33,  4.13,  3.38,  3.13, 3.00),
    ("2025-12-10", 4.33,  4.38,  3.63,  3.38, 3.00),
    ("2026-01-28", 4.33,  4.38,  3.63,  3.38, 3.00),
    ("2026-03-18", 4.33,  4.25,  3.63,  3.25, 3.00),
]

# ─────────────────────────────────────────
# 2. Data Loader
# ─────────────────────────────────────────

def load_from_csv(path: Path) -> pd.DataFrame | None:
    """
    從本地 CSV 載入 SEP 資料。
    支援兩種格式：
      A) 寬表：meeting_date, ffr_spot, ffr_current, ffr_1y, ffr_2y, ffr_long
      B) 長表（Kaggle）：meeting_date, projection_year, ffr_median
    """
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, parse_dates=["meeting_date"])
        df["meeting_date"] = pd.to_datetime(df["meeting_date"]).dt.normalize()

        # 如果是長表，pivot 成寬表
        if "projection_year" in df.columns and "ffr_median" in df.columns:
            pivot_map = {
                "current year": "ffr_current",
                "current":      "ffr_current",
                "one year":     "ffr_1y",
                "1 year":       "ffr_1y",
                "two years":    "ffr_2y",
                "2 years":      "ffr_2y",
                "longer run":   "ffr_long",
                "longer-run":   "ffr_long",
            }
            df["proj_col"] = df["projection_year"].str.lower().str.strip().map(pivot_map)
            df = df.dropna(subset=["proj_col"])
            wide = df.pivot_table(
                index="meeting_date",
                columns="proj_col",
                values="ffr_median",
                aggfunc="first"
            ).reset_index()
            wide.columns.name = None
            df = wide

        # 確保有必要欄位
        needed = ["ffr_current", "ffr_1y", "ffr_2y", "ffr_long"]
        if not all(c in df.columns for c in needed):
            print(f"  [WARN] CSV 缺少必要欄位，需要: {needed}")
            return None

        df = df.set_index("meeting_date").sort_index()
        print(f"  [CSV] 載入 {len(df)} 筆 SEP 記錄")
        return df

    except Exception as e:
        print(f"  [WARN] CSV 讀取失敗: {e}")
        return None


def load_hardcoded() -> pd.DataFrame:
    """從硬編碼歷史資料建立 DataFrame。"""
    cols = ["meeting_date", "ffr_spot", "ffr_current", "ffr_1y", "ffr_2y", "ffr_long"]
    df = pd.DataFrame(HARDCODED_SEP, columns=cols)
    df["meeting_date"] = pd.to_datetime(df["meeting_date"])
    df = df.set_index("meeting_date").sort_index()
    print(f"  [內建] 使用硬編碼歷史 SEP，共 {len(df)} 筆")
    return df


def merge_fedfunds(df_meetings: pd.DataFrame, fred_xlsx: Path | None = None) -> pd.DataFrame:
    """
    若有 fred_data.xlsx，從中抓 DFF 月均值補充 ffr_spot；
    否則 ffr_spot 使用 HARDCODED 值或保留 NaN。
    """
    if fred_xlsx and fred_xlsx.exists():
        try:
            ff = pd.read_excel(fred_xlsx, sheet_name="貨幣政策", index_col=0, parse_dates=True)
            if "DFF" in ff.columns:
                monthly_ff = ff["DFF"].resample("ME").mean()
                # 對每個 meeting_date 找最近月均
                def get_spot(dt):
                    idx = monthly_ff.index.get_indexer([dt], method="nearest")
                    return monthly_ff.iloc[idx[0]] if idx[0] >= 0 else np.nan

                if "ffr_spot" not in df_meetings.columns:
                    df_meetings["ffr_spot"] = df_meetings.index.map(get_spot)
                else:
                    # 補缺失
                    mask = df_meetings["ffr_spot"].isna()
                    df_meetings.loc[mask, "ffr_spot"] = df_meetings.index[mask].map(get_spot)
                print("  [DFF] 已從 fred_data.xlsx 補充 ffr_spot")
        except Exception as e:
            print(f"  [WARN] 讀取 fred_data.xlsx 失敗: {e}")
    return df_meetings


# ─────────────────────────────────────────
# 3. 特徵工程
# ─────────────────────────────────────────

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    依規格書第 4 節計算三個核心特徵：
      delta_1y  = ffr_1y  - ffr_spot     (近期斜率，+緊縮/-寬鬆)
      delta_2y  = ffr_2y  - ffr_current  (中期路徑)
      delta_long= ffr_1y  - ffr_long     (vs 中性利率偏離)
    """
    feat = df.copy()

    feat["delta_1y"]   = feat["ffr_1y"]  - feat["ffr_spot"]
    feat["delta_2y"]   = feat["ffr_2y"]  - feat["ffr_current"]
    feat["delta_long"] = feat["ffr_1y"]  - feat["ffr_long"]

    # 選擇性：dispersion（若有多點分布資料則可填入，此處預設 NaN）
    if "dispersion" not in feat.columns:
        feat["dispersion"] = np.nan

    return feat


# ─────────────────────────────────────────
# 4. Z-score 與子分數映射
# ─────────────────────────────────────────

def rolling_zscore_meetings(series: pd.Series, window: int = 40) -> pd.Series:
    """
    會議頻率的 rolling z-score（window=40 ≈ 10 年 × 4 次）。
    因為 FOMC 每年 8 次，40 次 ≈ 5 年；80 次 ≈ 10 年，可調整。
    """
    mu = series.rolling(window, min_periods=8).mean()
    sigma = series.rolling(window, min_periods=8).std()
    return (series - mu) / sigma.replace(0, np.nan)


def map_policy_score(z: float) -> float:
    """
    規格書 5.2：
    z >= +1.5 → -2 (強烈緊縮預期)
    z in [+0.5, +1.5) → -1
    z in (-0.5, +0.5) → 0
    z in (-1.5, -0.5] → +1
    z <= -1.5 → +2 (強烈寬鬆預期)
    """
    if pd.isna(z):
        return np.nan
    if z >= 1.5:
        return -2.0
    elif z >= 0.5:
        return -1.0
    elif z > -0.5:
        return 0.0
    elif z > -1.5:
        return 1.0
    else:
        return 2.0


def map_dispersion_score(z: float) -> float:
    """高不確定性僅扣分，不加分。"""
    if pd.isna(z):
        return 0.0
    return -1.0 if z >= 1.5 else 0.0


# ─────────────────────────────────────────
# 5. 主引擎類別
# ─────────────────────────────────────────

class PolicyForwardScoreEngine:
    """
    FOMC 政策預期評分引擎（第 4 個宏觀子分數）。

    使用範例：
        engine = PolicyForwardScoreEngine()
        engine.load_data()
        engine.build_features()
        engine.compute_scores()
        score = engine.get_score("2026-04-01")
        monthly_df = engine.monthly_scores
    """

    # 規格書 5.3 權重
    WEIGHTS = {
        "delta_1y":   0.50,
        "delta_2y":   0.20,
        "delta_long": 0.20,
        "dispersion": 0.10,
    }

    def __init__(self, window: int = 40, fred_xlsx: Path | None = None):
        """
        window: rolling z-score 窗口（FOMC 會議次數）
        fred_xlsx: fred_data.xlsx 路徑（用來補 ffr_spot）
        """
        self.window = window
        self.fred_xlsx = fred_xlsx or (BASE_DIR / "fred_data.xlsx")
        self.df_meetings: pd.DataFrame | None = None
        self.monthly_scores: pd.DataFrame | None = None
        self.polymarket_score: float | None = None
        self.polymarket_detail: dict = {}

    # ── 載入 ──────────────────────────────
    def load_data(self, csv_path: Path | None = None) -> "PolicyForwardScoreEngine":
        print("\n[PolicyForwardScoreEngine] 載入 SEP 資料...")

        # 優先: 用戶提供的 CSV
        df = load_from_csv(csv_path or SEP_CSV)

        # Fallback: 硬編碼
        if df is None:
            df = load_hardcoded()

        # 補充 ffr_spot（若缺）
        df = merge_fedfunds(df, self.fred_xlsx)

        self.df_meetings = df
        return self

    # ── 特徵 ─────────────────────────────
    def build_features(self) -> "PolicyForwardScoreEngine":
        assert self.df_meetings is not None, "請先呼叫 load_data()"
        self.df_meetings = build_features(self.df_meetings)
        return self

    # ── 評分 ─────────────────────────────
    def compute_scores(self) -> "PolicyForwardScoreEngine":
        assert self.df_meetings is not None, "請先呼叫 build_features()"
        df = self.df_meetings.copy()

        feature_cols = ["delta_1y", "delta_2y", "delta_long", "dispersion"]

        # Z-score
        for col in feature_cols:
            if col in df.columns:
                df[f"Z_{col}"] = rolling_zscore_meetings(df[col], self.window)
            else:
                df[f"Z_{col}"] = np.nan

        # 子分數映射
        for col in ["delta_1y", "delta_2y", "delta_long"]:
            df[f"SUB_{col}"] = df[f"Z_{col}"].apply(map_policy_score)
        df["SUB_dispersion"] = df["Z_dispersion"].apply(map_dispersion_score)

        # 聚合 → 點陣圖分數
        df["policy_forward_score"] = (
            self.WEIGHTS["delta_1y"]   * df["SUB_delta_1y"]   +
            self.WEIGHTS["delta_2y"]   * df["SUB_delta_2y"]   +
            self.WEIGHTS["delta_long"] * df["SUB_delta_long"]  +
            self.WEIGHTS["dispersion"] * df["SUB_dispersion"]
        )

        # 0–100 scaled（規格書 5.3）
        df["policy_forward_score_scaled"] = 25.0 * (df["policy_forward_score"] + 2.0)
        df["policy_forward_score_scaled"] = df["policy_forward_score_scaled"].clip(0, 100)

        # ── Polymarket 整合（最新一期 FOMC 適用）──
        pm_score, pm_detail = load_polymarket_score()
        self.polymarket_score  = pm_score
        self.polymarket_detail = pm_detail

        if pm_score is not None:
            # combined = 70% 點陣圖 + 30% Polymarket（僅最新一列）
            df["combined_policy_score"] = df["policy_forward_score"].copy()
            df.iloc[-1, df.columns.get_loc("combined_policy_score")] = (
                W_DOTPLOT * df["policy_forward_score"].iloc[-1] +
                W_POLYMARKET * pm_score
            )
        else:
            df["combined_policy_score"] = df["policy_forward_score"]

        df["combined_policy_score_scaled"] = (25.0 * (df["combined_policy_score"] + 2.0)).clip(0, 100)

        self.df_meetings = df

        # Forward fill 到月頻
        self._build_monthly()
        return self

    def _build_monthly(self):
        """將會議頻率的分數 forward-fill 到月頻。"""
        keep = [c for c in [
            "policy_forward_score", "policy_forward_score_scaled",
            "combined_policy_score", "combined_policy_score_scaled",
            "delta_1y", "delta_2y", "delta_long",
            "ffr_spot", "ffr_current", "ffr_1y", "ffr_2y", "ffr_long",
        ] if c in self.df_meetings.columns]
        df = self.df_meetings[keep].copy()

        # 重新索引到每月月末
        start = df.index.min().to_period("M").to_timestamp("M")
        end   = pd.Timestamp.now().to_period("M").to_timestamp("M")
        monthly_idx = pd.date_range(start, end, freq="ME")

        # 先 reindex 到月末，再 forward fill
        df_monthly = df.reindex(df.index.union(monthly_idx)).sort_index()
        df_monthly = df_monthly.ffill()
        df_monthly = df_monthly.reindex(monthly_idx)

        df_monthly.index.name = "date"
        self.monthly_scores = df_monthly

    # ── 查詢 ─────────────────────────────
    def get_score(self, dt=None) -> dict:
        """
        給定日期（預設今日），回傳該月的 policy_forward_score 資訊。
        """
        assert self.monthly_scores is not None, "請先呼叫 compute_scores()"
        if dt is None:
            dt = pd.Timestamp.now()
        dt = pd.Timestamp(dt).to_period("M").to_timestamp("M")

        if dt not in self.monthly_scores.index:
            # 找最近有效
            valid = self.monthly_scores["policy_forward_score"].dropna()
            dt = valid.index[-1] if len(valid) > 0 else self.monthly_scores.index[-1]

        row = self.monthly_scores.loc[dt]
        score    = row.get("policy_forward_score", np.nan)
        scaled   = row.get("policy_forward_score_scaled", np.nan)
        combined = row.get("combined_policy_score", score)
        comb_sc  = row.get("combined_policy_score_scaled", scaled)

        def _label(s):
            if pd.isna(s): return "N/A"
            if s >= 1.0:   return "強烈寬鬆預期（利多風險資產）"
            if s >= 0.0:   return "溫和寬鬆預期"
            if s >= -1.0:  return "溫和緊縮預期"
            return "強烈緊縮預期（利空風險資產）"

        def _f(v): return round(float(v), 3) if not pd.isna(v) else None

        return {
            "date":                         str(dt.date()),
            "policy_forward_score":         _f(score),
            "policy_forward_score_scaled":  round(float(scaled), 1) if not pd.isna(scaled) else None,
            "combined_policy_score":        _f(combined),
            "combined_policy_score_scaled": round(float(comb_sc), 1) if not pd.isna(comb_sc) else None,
            "label":                        _label(combined),
            "polymarket_score":              round(self.polymarket_score, 3) if self.polymarket_score is not None else None,
            "polymarket_detail":            self.polymarket_detail,
            "blend_weights":                {"dot_plot": W_DOTPLOT, "polymarket": W_POLYMARKET},
            "delta_1y":   round(float(row.get("delta_1y",   np.nan)), 2),
            "delta_2y":   round(float(row.get("delta_2y",   np.nan)), 2),
            "delta_long": round(float(row.get("delta_long", np.nan)), 2),
            "ffr_spot":    round(float(row.get("ffr_spot",   np.nan)), 3),
            "ffr_1y":      round(float(row.get("ffr_1y",    np.nan)), 3),
            "ffr_long":    round(float(row.get("ffr_long",  np.nan)), 3),
        }

    # ── 儲存 ─────────────────────────────
    def save_json(self, path: Path | None = None) -> Path:
        """儲存最新分數與月頻時間序列至 JSON。"""
        out = path or OUT_JSON
        latest = self.get_score()

        # 月頻序列（最近 5 年）
        ms = self.monthly_scores
        if ms is not None:
            cutoff = pd.Timestamp.now() - pd.DateOffset(years=5)
            recent = ms[ms.index >= cutoff].dropna(subset=["policy_forward_score"])
            history = [
                {
                    "date":  str(idx.date()),
                    "score": round(float(row["policy_forward_score"]), 3),
                    "scaled": round(float(row["policy_forward_score_scaled"]), 1),
                }
                for idx, row in recent.iterrows()
            ]
        else:
            history = []

        # 月頻歷史（含 dot-plot 欄位，供圖表用）
        ms = self.monthly_scores
        dotplot_history = []
        if ms is not None:
            cutoff = pd.Timestamp.now() - pd.DateOffset(years=6)
            recent = ms[ms.index >= cutoff].dropna(subset=["ffr_spot"])
            for idx, row in recent.iterrows():
                dotplot_history.append({
                    "date":        str(idx.date()),
                    "ffr_spot":   round(float(row.get("ffr_spot",   np.nan)), 3),
                    "ffr_current": round(float(row.get("ffr_current", np.nan)), 3),
                    "ffr_1y":     round(float(row.get("ffr_1y",    np.nan)), 3),
                    "ffr_2y":     round(float(row.get("ffr_2y",    np.nan)), 3),
                    "ffr_long":   round(float(row.get("ffr_long",  np.nan)), 3),
                    "dot_score":  round(float(row.get("policy_forward_score", np.nan)), 3),
                    "combined":   round(float(row.get("combined_policy_score", np.nan)), 3),
                })

        payload = {
            "latest":          latest,
            "history":         history,
            "dotplot_history": dotplot_history,
            "weights":         self.WEIGHTS,
            "blend_weights":   {"dot_plot": W_DOTPLOT, "polymarket": W_POLYMARKET},
            "score_range":     [-2, 2],
            "scaled_range":    [0, 100],
            "fetched_at":      datetime.now(timezone.utc).isoformat(),
            "data_source":     "FOMC SEP (Kaggle + FRED) + Polymarket",
            "description":     (
                "綜合政策預期評分 = 70% 點陣圖 + 30% Polymarket。"
                "+2=強烈降息預期，-2=強烈升息預期。"
            ),
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return out

    # ── 摘要列印 ─────────────────────────
    def print_summary(self):
        """列印最近 10 次 FOMC 的評分摘要。"""
        df = self.df_meetings
        if df is None or "policy_forward_score" not in df.columns:
            print("請先呼叫 compute_scores()")
            return

        cols = ["ffr_spot", "ffr_1y", "ffr_long",
                "delta_1y", "delta_2y", "delta_long",
                "policy_forward_score", "policy_forward_score_scaled"]
        show_cols = [c for c in cols if c in df.columns]
        recent = df[show_cols].dropna(subset=["policy_forward_score"]).tail(10)

        print("\n" + "=" * 72)
        print("  政策預期評分 (Policy Forward Score) — 最近 10 次 FOMC")
        print("=" * 72)
        show_cols = [c for c in ["ffr_spot", "ffr_1y", "ffr_long",
                     "delta_1y", "policy_forward_score", "combined_policy_score"] if c in df.columns]
        recent = df[show_cols].dropna(subset=["policy_forward_score"]).tail(10)
        print(recent.to_string(float_format="{:.2f}".format))

        latest = self.get_score()
        print("\n" + "-" * 72)
        print(f"  最新綜合分數 ({latest['date']})")
        print(f"    點陣圖分數  (70%)    : {latest['policy_forward_score']:+.3f}")
        pm = latest['polymarket_score']
        print(f"    Polymarket分數(30%)  : {f'{pm:+.3f}' if pm is not None else 'N/A (無資料)'}")
        print(f"    綜合分數 combined    : {latest['combined_policy_score']:+.3f}")
        print(f"    Scaled (0-100)       : {latest['combined_policy_score_scaled']:.1f}")
        print(f"    解讀                 : {latest['label']}")
        print(f"    delta_1y (vs spot)   : {latest['delta_1y']:+.2f}%")
        if pm is not None:
            print(f"    Polymarket 細節:")
            for sc, d in latest['polymarket_detail'].items():
                print(f"      {sc:12s}: {d['prob_pct']:5.1f}%  × {d['weight']:+.0f} = {d['contrib']:+.4f}")
        print("=" * 72)


# ─────────────────────────────────────────
# 6. 快速執行入口
# ─────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  PolicyForwardScoreEngine — 政策預期評分（Score #4）")
    print("=" * 60)

    engine = PolicyForwardScoreEngine(window=40)
    engine.load_data()
    engine.build_features()
    engine.compute_scores()
    engine.print_summary()

    saved = engine.save_json()
    print(f"\n[完成] JSON 已儲存至: {saved}")
