import os
import json
import pandas as pd
import numpy as np

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scorer_v2 import (
    compute_synthetic_indicators, compute_indicator_score,
    compute_credibility, aggregate_dimensions, DIRECTIONALITY,
)
from policy_forward_score import PolicyForwardScoreEngine

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_DIR  = os.path.join(BASE_DIR, "data")
INPUT_CSV = os.path.join(DATA_DIR, "data.csv")
INDEX_EXCEL = os.path.join(DATA_DIR, "indices_data.xlsx")
REPO_ROOT   = os.path.dirname(BASE_DIR)
OUTPUT_JSON = os.path.join(REPO_ROOT, "assets", "data", "dashboard_data.json")


def run_v2_scoring():
    """從 data.csv 執行 scorer_v2 管線，回傳 (scores_df, dim_scores)

    - scores_df : 各指標 EWMA Sigmoid score（欄名 = ticker）
    - dim_scores: DIM1~DIM4, MACRO_SCORE, REGIME
    """
    print("=== 執行 scorer_v2 管線 ===\n")

    raw = pd.read_csv(INPUT_CSV, parse_dates=["observation_date"])
    raw = raw.sort_values("observation_date")

    wide = raw.pivot_table(
        index="observation_date",
        columns="ticker",
        values="raw_value",
        aggfunc="last",
    )
    wide = wide.sort_index()
    print(f"  Pivot: {wide.shape[0]} 天 x {wide.shape[1]} tickers")

    full_idx = pd.bdate_range(start=wide.index.min(), end=wide.index.max())
    wide = wide.reindex(full_idx)
    wide.index.name = "observation_date"
    wide = wide.ffill()
    print(f"  Forward-fill 後: {wide.shape[0]} 交易日")

    wide = compute_synthetic_indicators(wide)

    scores_df = pd.DataFrame(index=wide.index)
    for ticker, direction in DIRECTIONALITY.items():
        if ticker not in wide.columns:
            print(f"  [SKIP] {ticker} 不在 data.csv")
            continue
        scores_df[ticker] = compute_indicator_score(wide[ticker], directionality=direction)

    credibility = compute_credibility(wide)
    dim_scores  = aggregate_dimensions(scores_df, credibility)

    valid = dim_scores["MACRO_SCORE"].dropna()
    print(f"\n  有效天數: {len(valid)}")
    print(f"  日期範圍: {valid.index.min().date()} ~ {valid.index.max().date()}")
    print(f"  最新 MACRO_SCORE: {valid.iloc[-1]:+.4f}")

    return scores_df, dim_scores



def load_indices_from_excel():
    """從 indices_data.xlsx 讀取各股市指數"""
    print("\n=== 從 indices_data.xlsx 讀取指數 ===\n")
    indices = {}
    xl = pd.ExcelFile(INDEX_EXCEL)
    for sheet in xl.sheet_names:
        df = xl.parse(sheet, parse_dates=["date"], index_col="date")
        col = [c for c in df.columns if c != "date"]
        if col:
            name = col[0]
            s = df[name].dropna()
            indices[name] = s
            print(f"  [OK] {name}: {len(s)} 筆  "
                  f"{s.index.min().date()} ~ {s.index.max().date()}")
    return indices


def series_to_json(series, date_fmt="%Y-%m-%d"):
    """pandas Series -> [{date, value}, ...]"""
    s = series.dropna()
    return [
        {"date": d.strftime(date_fmt), "value": round(float(v), 4)}
        for d, v in zip(s.index, s.values)
    ]


def main():
    # 1. V2 評分管線
    scores_df, dim_scores = run_v2_scoring()

    # 2. 讀取股市指數
    indices = load_indices_from_excel()

    # 3. PolicyForwardScore（點陣圖 + Polymarket）
    print("\n=== 計算 Policy Forward Score ===\n")
    pfs_engine = PolicyForwardScoreEngine(window=40)
    pfs_engine.load_data()
    pfs_engine.build_features()
    pfs_engine.compute_scores()
    pfs_latest = pfs_engine.get_score()

    dotplot_rows = []
    if pfs_engine.monthly_scores is not None:
        ms = pfs_engine.monthly_scores
        for idx, row in ms.iterrows():
            r = {}
            for col in ["ffr_spot", "ffr_current", "ffr_1y", "ffr_2y", "ffr_long",
                        "policy_forward_score", "combined_policy_score"]:
                v = row.get(col, float("nan"))
                r[col] = round(float(v), 3) if not (isinstance(v, float) and np.isnan(v)) else None
            r["date"] = idx.strftime("%Y-%m-%d")
            if any(v is not None for k, v in r.items() if k != "date"):
                dotplot_rows.append(r)

    # 4. 組裝 JSON
    print("\n=== 匯出 dashboard_data.json ===\n")

    # DIM2 原始範圍 [-2, 2]，正規化到 [-1, 1] 再存入 POLICY_SCORE
    policy_series = (dim_scores["DIM2_SCORE"] / 2.0).dropna()

    output = {
        "generated_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
        "scores": {
            "MACRO_SCORE":   series_to_json(dim_scores["MACRO_SCORE"]),
            "CREDIT_SCORE":  series_to_json(dim_scores["DIM1_SCORE"]),
            "POLICY_SCORE":  series_to_json(policy_series),
            "PRICEFX_SCORE": series_to_json(dim_scores["DIM4_SCORE"]),
            "REGIME":        series_to_json(dim_scores["REGIME"]),
        },
        "sub_scores": {},
        "indices": {},
        "policy_forward": {
            "latest":          pfs_latest,
            "dotplot_history": dotplot_rows,
            "blend_weights":   {"dot_plot": 0.70, "polymarket": 0.30},
        },
    }

    for col in scores_df.columns:
        output["sub_scores"][f"SUB_{col}"] = series_to_json(scores_df[col])

    for name, s in indices.items():
        label = name.replace("^", "")
        output["indices"][label] = series_to_json(s)

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False)

    size_mb = os.path.getsize(OUTPUT_JSON) / 1024 / 1024
    print(f"  -> 已寫入: {OUTPUT_JSON}")
    print(f"  -> 檔案大小: {size_mb:.2f} MB")
    print(f"  -> scores 天數: {len(output['scores']['MACRO_SCORE'])}")
    print(f"  -> 指數數量: {len(output['indices'])}")
    print(f"  -> 子指標數量: {len(output['sub_scores'])}")
    print(f"  -> 點陣圖歷史: {len(dotplot_rows)} 筆")
    pf = pfs_latest
    print(f"  -> combined_policy_score: {pf.get('combined_policy_score')} ({pf.get('label')})")


if __name__ == "__main__":
    main()

