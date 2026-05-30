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
DATA_DIR = os.path.join(BASE_DIR, "data")
FRED_EXCEL   = os.path.join(DATA_DIR, "fred_data.xlsx")
INDEX_EXCEL  = os.path.join(DATA_DIR, "indices_data.xlsx")
OUTPUT_JSON  = os.path.join(BASE_DIR, "dashboard_data.json")

# 向後相容：若 data/ 下不存在，嘗試舊位置
if not os.path.exists(FRED_EXCEL) and os.path.exists(os.path.join(BASE_DIR, "fred_data.xlsx")):
    FRED_EXCEL = os.path.join(BASE_DIR, "fred_data.xlsx")
if not os.path.exists(INDEX_EXCEL) and os.path.exists(os.path.join(BASE_DIR, "indices_data.xlsx")):
    INDEX_EXCEL = os.path.join(BASE_DIR, "indices_data.xlsx")


def load_fred_from_excel():
    """從 fred_data.xlsx 讀取原始資料，組裝成 macro_data_loader 相同的 DataFrame

    同時讀取 V1 原有工作表與 V2 新增工作表。
    若某工作表不存在（尚未執行 FRED.py 更新），該群組會自動跳過。
    """
    print("=== 從 fred_data.xlsx 讀取資料 (V2) ===\n")

    xl = pd.ExcelFile(FRED_EXCEL)
    sheets = xl.sheet_names
    all_series = {}

    def _read_sheet(sheet_name, cols):
        """讀取指定工作表的欄位，回傳 {col: Series} dict"""
        if sheet_name not in sheets:
            print(f"  [SKIP] 工作表 '{sheet_name}' 不存在（請重新執行 FRED.py）")
            return
        df_s = xl.parse(sheet_name, parse_dates=["date"], index_col="date")
        for col in cols:
            if col in df_s.columns:
                all_series[col] = df_s[col]
                print(f"  [OK] {col}: {df_s[col].dropna().shape[0]} 筆")

    # ── V1：原有工作表 ────────────────────────────────────────────
    print("[V1] 信用利差")
    _read_sheet("信用利差", ["CPN3M", "DTB6", "DPRIME", "DBAA", "DGS10"])

    print("[V1] 貨幣政策")
    _read_sheet("貨幣政策", ["DFF"])

    print("[V1] 通膨 → INF_YOY")
    if "通膨" in sheets:
        df_inf = xl.parse("通膨", parse_dates=["date"], index_col="date")
        if "CPIAUCSL" in df_inf.columns:
            cpi = df_inf["CPIAUCSL"].dropna()
            inf_yoy = (cpi / cpi.shift(12) - 1) * 100
            inf_yoy = inf_yoy.dropna()
            inf_yoy.name = "INF_YOY"
            all_series["INF_YOY"] = inf_yoy
            print(f"  [CALC] INF_YOY: {len(inf_yoy)} 筆")

    print("[V1] 匯率")
    _read_sheet("匯率", ["DTWEXBGS", "EMVEXRATES"])

    print("[V1] 股市指數")
    _read_sheet("股市指數", ["DJIA"])

    # ── V2：新增工作表 ────────────────────────────────────────────
    print("\n[V2] 信用壓力（違約率）")
    _read_sheet("信用壓力", ["DRBLACBS"])

    print("[V2] 衰退預警（殖利率倒掛）")
    _read_sheet("衰退預警", ["T10Y2Y"])

    print("[V2] 勞動市場動能V2")
    _read_sheet("勞動市場動能V2", ["JTSJOL", "JTSQUR"])

    print("[V2] 創新創造")
    _read_sheet("創新創造", ["BABATOT"])

    print("[V2] 國際資本")
    _read_sheet("國際資本", ["BOPBCA"])

    print("[V2] 淨流動性")
    _read_sheet("淨流動性", ["WALCL", "WTREGEN", "RRPONTSYD"])

    # ── 組裝 DataFrame ────────────────────────────────────────────
    df = pd.DataFrame(all_series)
    full_idx = pd.bdate_range(df.index.min(), df.index.max())
    df = df.reindex(full_idx).ffill()
    df = df[df.index >= cfg.DATA_START_DATE]

    # ── 衍生：淨流動性 ────────────────────────────────────────────
    # Net Liquidity (B$) = WALCL(M$)/1000 - WTREGEN(B$) - RRPONTSYD(B$)
    if all(c in df.columns for c in ["WALCL", "WTREGEN", "RRPONTSYD"]):
        df["NET_LIQUIDITY"] = df["WALCL"] / 1000 - df["WTREGEN"] - df["RRPONTSYD"]
        latest_liq = df["NET_LIQUIDITY"].dropna()
        if not latest_liq.empty:
            print(f"  [CALC] NET_LIQUIDITY: {len(latest_liq)} 筆"
                  f"  (最新: {latest_liq.iloc[-1]:.1f} B$)")

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

