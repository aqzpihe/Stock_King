import os
import json
import pandas as pd
import numpy as np

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config as cfg
from macro_feature_engineer import compute_features
from macro_scorer import compute_all_scores
from policy_forward_score import PolicyForwardScoreEngine

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRED_EXCEL   = os.path.join(BASE_DIR, "fred_data.xlsx")
INDEX_EXCEL  = os.path.join(BASE_DIR, "indices_data.xlsx")
OUTPUT_JSON  = os.path.join(BASE_DIR, "dashboard_data.json")


def load_fred_from_excel():
    """從 fred_data.xlsx 讀取原始資料，組裝成 macro_data_loader 相同的 DataFrame"""
    print("=== 從 fred_data.xlsx 讀取資料 ===\n")

    xl = pd.ExcelFile(FRED_EXCEL)
    all_series = {}

    df_credit = xl.parse("信用利差", parse_dates=["date"], index_col="date")
    for col in ["CPN3M", "DTB6", "DPRIME", "DBAA", "DGS10"]:
        if col in df_credit.columns:
            all_series[col] = df_credit[col]
            print(f"  [OK] {col}: {df_credit[col].dropna().shape[0]} 筆")

    df_policy = xl.parse("貨幣政策", parse_dates=["date"], index_col="date")
    if "DFF" in df_policy.columns:
        all_series["DFF"] = df_policy["DFF"]
        print(f"  [OK] DFF: {df_policy['DFF'].dropna().shape[0]} 筆")

    df_inf = xl.parse("通膨", parse_dates=["date"], index_col="date")
    if "CPIAUCSL" in df_inf.columns:
        cpi = df_inf["CPIAUCSL"].dropna()
        inf_yoy = (cpi / cpi.shift(12) - 1) * 100
        inf_yoy = inf_yoy.dropna()
        inf_yoy.name = "INF_YOY"
        all_series["INF_YOY"] = inf_yoy
        print(f"  [CALC] INF_YOY: {len(inf_yoy)} 筆")

    df_fx = xl.parse("匯率", parse_dates=["date"], index_col="date")
    for col in ["DTWEXBGS", "EMVEXRATES"]:
        if col in df_fx.columns:
            all_series[col] = df_fx[col]
            print(f"  [OK] {col}: {df_fx[col].dropna().shape[0]} 筆")

    if "股市指數" in xl.sheet_names:
        df_idx = xl.parse("股市指數", parse_dates=["date"], index_col="date")
        if "DJIA" in df_idx.columns:
            all_series["DJIA"] = df_idx["DJIA"]
            print(f"  [OK] DJIA: {df_idx['DJIA'].dropna().shape[0]} 筆")

    df = pd.DataFrame(all_series)
    full_idx = pd.bdate_range(df.index.min(), df.index.max())
    df = df.reindex(full_idx).ffill()
    df = df[df.index >= cfg.DATA_START_DATE]

    print(f"\n=== DataFrame: {df.shape[0]} 天 x {df.shape[1]} 欄 ===")
    return df


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
    # 1. 讀取 FRED 資料
    df_raw = load_fred_from_excel()

    # 2. 特徵工程
    features = compute_features(df_raw)

    # 3. 評分
    scores = compute_all_scores(features)

    # 4. 讀取股市指數
    indices = load_indices_from_excel()

    # 5. PolicyForwardScore（點陣圖 + Polymarket）
    print("\n=== 計算 Policy Forward Score ===\n")
    pfs_engine = PolicyForwardScoreEngine(window=40)
    pfs_engine.load_data()
    pfs_engine.build_features()
    pfs_engine.compute_scores()
    pfs_latest = pfs_engine.get_score()

    # dotplot_history 供 Chart E 使用
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

    # 6. 組裝 JSON
    print("\n=== 匯出 dashboard_data.json ===\n")

    output = {
        "generated_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
        "scores": {
            "MACRO_SCORE":   series_to_json(scores["MACRO_SCORE"]),
            "CREDIT_SCORE":  series_to_json(scores["CREDIT_SCORE"]),
            "POLICY_SCORE":  series_to_json(scores["POLICY_SCORE"]),
            "PRICEFX_SCORE": series_to_json(scores["PRICEFX_SCORE"]),
            "REGIME":        series_to_json(scores["REGIME"]),
        },
        "sub_scores": {},
        "indices": {},
        "policy_forward": {
            "latest":          pfs_latest,
            "dotplot_history": dotplot_rows,
            "blend_weights":   {"dot_plot": 0.70, "polymarket": 0.30},
        },
    }

    sub_cols = [c for c in scores.columns if c.startswith("SUB_")]
    for col in sub_cols:
        output["sub_scores"][col] = series_to_json(scores[col])

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

