"""
build_data_csv.py — V2 ETL 管線：統一彙整所有資料至 data.csv
=============================================================
依照 PRD § 2.2，將所有已清洗的特徵資料統一儲存為長表格式：

欄位設計：
  observation_date  : 資料所屬日期（月底/季底/日期）
  ticker            : 數據代碼（如 DBAA, JTSJOL, TIC_GRAND_TOTAL）
  raw_value         : 原始數值
  frequency         : 數據頻率（D/W/M/Q）
  lag_category      : Leading / Real-time / Lagging / Confirming
  dimension         : 所屬四大面向 (1, 2, 3, 4)

資料來源：
  1. data/fred_data.xlsx      — FRED 所有工作表
  3. data/sep_data.csv        — FOMC SEP 點陣圖
  4. data/tic_holdings.csv    — TIC 外資持有美債（由 tic_preprocessor.py 產生）
  5. polymarket_fed.json      — Polymarket 預測市場（最新一期）

執行：
  python build_data_csv.py
"""

import os
import json
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
OUTPUT   = DATA_DIR / "data.csv"

# ──────────────────────────────────────────────
# Ticker 元資料 (frequency, lag_category, dimension)
# ──────────────────────────────────────────────
# dimension: 1=信用/中介, 2=政策預期, 3=國家經濟, 4=國際資本
# lag: Leading, Real-time, Lagging, Confirming

TICKER_META = {
    # ===== 面向一：信用市場與金融中介健康度 =====
    "CPN3M":      {"freq": "D", "lag": "Real-time",  "dim": 1},
    "DTB6":       {"freq": "D", "lag": "Real-time",  "dim": 1},
    "DPRIME":     {"freq": "D", "lag": "Real-time",  "dim": 1},
    "DBAA":       {"freq": "D", "lag": "Real-time",  "dim": 1},
    "DGS10":      {"freq": "D", "lag": "Real-time",  "dim": 1},
    "DRBLACBS":   {"freq": "Q", "lag": "Lagging",    "dim": 1},
    # ===== 面向二：政策預期與體制可信度 =====
    "DFF":        {"freq": "D", "lag": "Real-time",  "dim": 2},
    "FEDFUNDS":   {"freq": "M", "lag": "Real-time",  "dim": 2},
    "WALCL":      {"freq": "W", "lag": "Real-time",  "dim": 2},
    "T10Y2Y":     {"freq": "D", "lag": "Leading",    "dim": 2},
    "WTREGEN":    {"freq": "W", "lag": "Real-time",  "dim": 2},
    "RRPONTSYD":  {"freq": "D", "lag": "Real-time",  "dim": 2},
    "DGS2":       {"freq": "D", "lag": "Real-time",  "dim": 2},
    "DGS30":      {"freq": "D", "lag": "Real-time",  "dim": 2},
    "MORTGAGE30US": {"freq": "W", "lag": "Real-time", "dim": 2},
    # SEP / Polymarket
    "SEP_FFR_CURRENT": {"freq": "Q", "lag": "Leading", "dim": 2},
    "SEP_FFR_1Y":      {"freq": "Q", "lag": "Leading", "dim": 2},
    "SEP_FFR_2Y":      {"freq": "Q", "lag": "Leading", "dim": 2},
    "SEP_FFR_LONG":    {"freq": "Q", "lag": "Leading", "dim": 2},
    "SEP_FFR_SPOT":    {"freq": "Q", "lag": "Leading", "dim": 2},
    "POLYMARKET_RATE":    {"freq": "D", "lag": "Leading", "dim": 2},
    # ===== 面向三：國家經濟情況 =====
    "CPIAUCSL":   {"freq": "M", "lag": "Lagging",    "dim": 3},
    "PCE":        {"freq": "M", "lag": "Lagging",    "dim": 3},
    "PPIACO":     {"freq": "M", "lag": "Lagging",    "dim": 3},
    "UNRATE":     {"freq": "M", "lag": "Lagging",    "dim": 3},
    "PAYEMS":     {"freq": "M", "lag": "Lagging",    "dim": 3},
    "ICSA":       {"freq": "W", "lag": "Leading",    "dim": 3},
    "INDPRO":     {"freq": "M", "lag": "Lagging",    "dim": 3},
    "GDP":        {"freq": "Q", "lag": "Lagging",    "dim": 3},
    "UMCSENT":    {"freq": "M", "lag": "Leading",    "dim": 3},
    "JTSJOL":     {"freq": "M", "lag": "Leading",    "dim": 3},
    "JTSQUR":     {"freq": "M", "lag": "Leading",    "dim": 3},
    "BABATOTALSAUS": {"freq": "M", "lag": "Leading", "dim": 3},
    # ===== 面向四：國際資本傳導與匯率環境 =====
    "DTWEXBGS":   {"freq": "D", "lag": "Real-time",  "dim": 4},
    "EMVEXRATES": {"freq": "M", "lag": "Real-time",  "dim": 4},
    "BOPBCA":     {"freq": "Q", "lag": "Lagging",    "dim": 4},

    # TIC
    "TIC_GRAND_TOTAL":     {"freq": "M", "lag": "Lagging", "dim": 4},
    "TIC_OFFICIAL":        {"freq": "M", "lag": "Lagging", "dim": 4},
    "TIC_OFFICIAL_BILLS":  {"freq": "M", "lag": "Lagging", "dim": 4},
    "TIC_OFFICIAL_BONDS":  {"freq": "M", "lag": "Lagging", "dim": 4},
    "TIC_JAPAN":           {"freq": "M", "lag": "Lagging", "dim": 4},
    "TIC_CHINA":           {"freq": "M", "lag": "Lagging", "dim": 4},
    "TIC_GRAND_TOTAL_MOM": {"freq": "M", "lag": "Lagging", "dim": 4},
    "TIC_OFFICIAL_MOM":    {"freq": "M", "lag": "Lagging", "dim": 4},
}


def get_meta(ticker: str) -> dict:
    """查找 ticker 元資料，未知的給予預設值"""
    return TICKER_META.get(ticker, {"freq": "?", "lag": "?", "dim": 0})


# ──────────────────────────────────────────────
# 1. FRED Excel → 長表
# ──────────────────────────────────────────────
def load_fred_excel() -> pd.DataFrame:
    """從 fred_data.xlsx 讀取所有工作表，轉換為長表"""
    path = DATA_DIR / "fred_data.xlsx"
    if not path.exists():
        print(f"  [SKIP] {path} 不存在")
        return pd.DataFrame()

    print(f"[FRED] 讀取 {path}")
    xl = pd.ExcelFile(path)
    rows = []

    for sheet in xl.sheet_names:
        df = xl.parse(sheet, parse_dates=["date"], index_col="date")
        for col in df.columns:
            if col == "date":
                continue
            series = df[col].dropna()
            for dt, val in series.items():
                rows.append({
                    "observation_date": dt.strftime("%Y-%m-%d"),
                    "ticker": col,
                    "raw_value": float(val),
                })
        print(f"  [{sheet}] {', '.join(c for c in df.columns)} → {len(df)} 天")

    return pd.DataFrame(rows)





# ──────────────────────────────────────────────
# 3. SEP 點陣圖 CSV → 長表
# ──────────────────────────────────────────────
def load_sep_csv() -> pd.DataFrame:
    path = DATA_DIR / "sep_data.csv"
    if not path.exists():
        print(f"  [SKIP] {path} 不存在")
        return pd.DataFrame()

    print(f"[SEP] 讀取 {path}")
    df = pd.read_csv(path, parse_dates=["meeting_date"], index_col="meeting_date")
    rows = []

    col_map = {
        "ffr_spot":    "SEP_FFR_SPOT",
        "ffr_current": "SEP_FFR_CURRENT",
        "ffr_1y":      "SEP_FFR_1Y",
        "ffr_2y":      "SEP_FFR_2Y",
        "ffr_long":    "SEP_FFR_LONG",
    }

    for col, ticker in col_map.items():
        if col in df.columns:
            series = df[col].dropna()
            for dt, val in series.items():
                rows.append({
                    "observation_date": dt.strftime("%Y-%m-%d"),
                    "ticker": ticker,
                    "raw_value": float(val),
                })

    print(f"  {len(df)} 次 FOMC 會議 → {len(rows)} 筆記錄")
    return pd.DataFrame(rows)


# ──────────────────────────────────────────────
# 4. TIC 外資持債 CSV → 長表（已是長表格式）
# ──────────────────────────────────────────────
def load_tic_csv() -> pd.DataFrame:
    path = DATA_DIR / "tic_holdings.csv"
    if not path.exists():
        print(f"  [SKIP] {path} 不存在（請先執行 tic_preprocessor.py）")
        return pd.DataFrame()

    print(f"[TIC] 讀取 {path}")
    df = pd.read_csv(path)
    print(f"  {len(df)} 筆, tickers: {sorted(df['ticker'].unique())}")
    return df


# ──────────────────────────────────────────────
# 5. Polymarket JSON → 長表（僅最新一期）
# ──────────────────────────────────────────────
def load_polymarket_json() -> pd.DataFrame:
    path = BASE_DIR / "polymarket_fed.json"
    # 也嘗試 data/ 下
    if not path.exists():
        path = DATA_DIR / "polymarket_fed.json"
    if not path.exists():
        print(f"  [SKIP] polymarket_fed.json 不存在")
        return pd.DataFrame()

    print(f"[POLYMARKET] 讀取 {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [WARN] 讀取失敗: {e}")
        return pd.DataFrame()

    fomc_date = data.get("fomc_date")
    if not fomc_date:
        return pd.DataFrame()

    # 從各子市場萃取加權預期利率分數
    markets = data.get("markets", [])
    rows = []

    # 簡單做法：提取 Yes 機率加權後的預期
    keyword_weights = {
        "decrease": {"50": 2.0, "25": 1.0},
        "no change": {"": 0.0},
        "increase": {"25": -1.0, "50": -2.0},
    }

    score_sum = 0.0
    prob_sum = 0.0
    for m in markets:
        q = m.get("question", "").lower()
        outcomes = m.get("outcomes", [])
        yes_prob = None
        for o in outcomes:
            if o.get("outcome", "").lower() == "yes":
                yes_prob = o.get("probability", 0) / 100
                break
        if yes_prob is None:
            continue

        for kw1, sub in keyword_weights.items():
            for kw2, weight in sub.items():
                if kw1 in q and (not kw2 or kw2 in q):
                    score_sum += yes_prob * weight
                    prob_sum += yes_prob
                    break

    if prob_sum > 0 and abs(prob_sum - 1.0) > 0.05:
        score_sum /= prob_sum

    rows.append({
        "observation_date": data.get("fetched_at", fomc_date)[:10],
        "ticker": "POLYMARKET_RATE",
        "raw_value": round(score_sum, 4),
    })

    print(f"  FOMC={fomc_date}, polymarket_score={score_sum:.4f}")
    return pd.DataFrame(rows)


# ──────────────────────────────────────────────
# 主程式：匯整 → 加元資料 → 寫入 data.csv
# ──────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  build_data_csv.py — V2 ETL 管線")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")

    frames = []

    # 1. FRED
    df = load_fred_excel()
    if not df.empty:
        frames.append(df)
        print(f"  → {len(df)} 筆\n")



    # 3. SEP
    df = load_sep_csv()
    if not df.empty:
        frames.append(df)
        print(f"  → {len(df)} 筆\n")

    # 4. TIC
    df = load_tic_csv()
    if not df.empty:
        frames.append(df)
        print(f"  → {len(df)} 筆\n")

    # 5. Polymarket
    df = load_polymarket_json()
    if not df.empty:
        frames.append(df)
        print(f"  → {len(df)} 筆\n")

    if not frames:
        print("!! 無任何資料來源可用")
        return

    # 合併
    print("-" * 60)
    print("  合併與元資料標注...")
    combined = pd.concat(frames, ignore_index=True)

    # 去重（同一天同一 ticker 只保留最後一筆）
    combined = combined.drop_duplicates(
        subset=["observation_date", "ticker"], keep="last"
    )

    # 加上元資料欄位
    combined["frequency"] = combined["ticker"].map(lambda t: get_meta(t)["freq"])
    combined["lag_category"] = combined["ticker"].map(lambda t: get_meta(t)["lag"])
    combined["dimension"] = combined["ticker"].map(lambda t: get_meta(t)["dim"])

    # 過濾掉未分類 (dim=0) 的多餘指標（例如指數等不需要的資料）
    combined = combined[combined["dimension"] > 0]

    # 排序
    combined = combined.sort_values(
        ["dimension", "ticker", "observation_date"]
    ).reset_index(drop=True)

    # 輸出 CSV
    os.makedirs(DATA_DIR, exist_ok=True)
    combined.to_csv(OUTPUT, index=False, encoding="utf-8")

    # 輸出 Excel (依四個面相分頁)
    OUTPUT_EXCEL = DATA_DIR / "data.xlsx"
    sheet_names = {
        1: "面向一_信用市場與金融中介健康度",
        2: "面向二_政策預期與體制可信度",
        3: "面向三_國家經濟情況(總量與微觀)",
        4: "面向四_國際資本傳導與匯率環境",
        0: "未分類",
    }
    with pd.ExcelWriter(OUTPUT_EXCEL, engine="openpyxl") as writer:
        for dim in sorted(combined["dimension"].unique()):
            sub = combined[combined["dimension"] == dim]
            if not sub.empty:
                s_name = sheet_names.get(dim, f"面向{dim}")
                sub.to_excel(writer, sheet_name=s_name, index=False)

    # 統計
    print(f"\n{'=' * 60}")
    print(f"  [DONE] data.csv 與 data.xlsx 建置完成")
    print(f"  CSV 路徑：{OUTPUT}")
    print(f"  Excel 路徑：{OUTPUT_EXCEL}")
    print(f"  總筆數：{len(combined):,}")
    print(f"  Tickers：{combined['ticker'].nunique()}")
    print(f"  日期範圍：{combined['observation_date'].min()} ~ {combined['observation_date'].max()}")
    print(f"\n  各面向 (dimension) 統計：")
    dim_labels = {
        1: "信用與中介健康度",
        2: "政策預期與可信度",
        3: "國家經濟情況",
        4: "國際資本與匯率",
        0: "未分類",
    }
    for dim in sorted(combined["dimension"].unique()):
        sub = combined[combined["dimension"] == dim]
        label = dim_labels.get(dim, "?")
        tickers = sorted(sub["ticker"].unique())
        print(f"    面向 {dim} ({label}): {len(sub):,} 筆, {len(tickers)} tickers")
        for t in tickers:
            n = len(sub[sub["ticker"] == t])
            print(f"      {t:25s} {n:>6,} 筆")

    print(f"\n  各 lag_category 統計：")
    for cat in ["Leading", "Real-time", "Lagging", "Confirming", "?"]:
        n = len(combined[combined["lag_category"] == cat])
        if n > 0:
            print(f"    {cat:15s}: {n:>8,} 筆")

    print(f"{'=' * 60}\n")
    return combined


if __name__ == "__main__":
    main()
