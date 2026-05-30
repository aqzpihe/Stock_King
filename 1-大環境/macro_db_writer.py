"""
將 V2 管線產出的 data.csv 和 scores.csv 上傳至 Supabase。
- 支援首次全量上傳與每日增量 upsert（衝突時自動覆蓋）
- 大批資料分批上傳，避免單次請求過大
"""

import os
import pandas as pd
from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://yxydsxygylpzewumevsz.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# 本機執行時從 config.py 取 key
if SUPABASE_KEY is None:
    try:
        import sys
        sys.path.insert(0, str(__file__.replace("macro_db_writer.py", "")))
        import config
        SUPABASE_KEY = config.service_role
    except ImportError:
        raise RuntimeError("找不到 SUPABASE_KEY，請設定環境變數或確認 config.py 存在")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
BATCH_SIZE = 500  # 每批上傳筆數


def _upsert_batch(table: str, rows: list, conflict_col: str) -> None:
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i: i + BATCH_SIZE]
        supabase.table(table).upsert(batch, on_conflict=conflict_col).execute()
    print(f"  [{table}] upsert {len(rows)} 筆 OK")


def upload_macro_raw(since_date: str = None) -> None:
    """
    上傳 data/data.csv 到 macro_raw。
    since_date: 只上傳此日期之後的資料（如 '2025-01-01'），None 表示全量。
    """
    path = os.path.join(DATA_DIR, "data.csv")
    df = pd.read_csv(path, parse_dates=["observation_date"])

    if since_date:
        df = df[df["observation_date"] >= since_date]

    df["observation_date"] = df["observation_date"].dt.strftime("%Y-%m-%d")
    df = df.where(pd.notna(df), None)  # NaN → None（JSON null）

    rows = df.rename(columns={
        "observation_date": "observation_date",
        "ticker":           "ticker",
        "raw_value":        "raw_value",
        "frequency":        "frequency",
        "lag_category":     "lag_category",
        "dimension":        "dimension",
    }).to_dict(orient="records")

    print(f"[macro_raw] 準備上傳 {len(rows)} 筆...")
    _upsert_batch("macro_raw", rows, "observation_date,ticker")


def upload_macro_scores(since_date: str = None) -> None:
    """
    上傳 data/scores.csv 到 macro_scores。
    since_date: 只上傳此日期之後的資料，None 表示全量。
    """
    path = os.path.join(DATA_DIR, "scores.csv")
    df = pd.read_csv(path, parse_dates=["observation_date"])

    if since_date:
        df = df[df["observation_date"] >= since_date]

    df["observation_date"] = df["observation_date"].dt.strftime("%Y-%m-%d")
    df = df.where(pd.notna(df), None)

    col_map = {
        "observation_date":          "observation_date",
        "SCORE_CREDIT_SPREAD":       "score_credit_spread",
        "SCORE_MORTGAGE_SPREAD":     "score_mortgage_spread",
        "SCORE_DRBLACBS":            "score_drblacbs",
        "SCORE_NET_LIQ_CHG":         "score_net_liq_chg",
        "SCORE_DFF":                 "score_dff",
        "SCORE_T10Y2Y":              "score_t10y2y",
        "SCORE_JTSJOL":              "score_jtsjol",
        "SCORE_JTSQUR":              "score_jtsqur",
        "SCORE_BABATOTALSAUS":       "score_babatotalsaus",
        "SCORE_INDPRO":              "score_indpro",
        "SCORE_PAYEMS":              "score_payems",
        "SCORE_DTWEXBGS":            "score_dtwexbgs",
        "SCORE_EMVEXRATES":          "score_emvexrates",
        "SCORE_TIC_GRAND_TOTAL_MOM": "score_tic_grand_total",
        "DIM1_SCORE":                "dim1_score",
        "DIM2_SCORE":                "dim2_score",
        "DIM2_CREDIBILITY":          "dim2_credibility",
        "DIM3_SCORE":                "dim3_score",
        "DIM4_SCORE":                "dim4_score",
        "MACRO_SCORE":               "macro_score",
        "REGIME":                    "regime",
    }
    df = df.rename(columns=col_map)[[c for c in col_map.values() if c in df.rename(columns=col_map).columns]]

    rows = df.to_dict(orient="records")
    print(f"[macro_scores] 準備上傳 {len(rows)} 筆...")
    _upsert_batch("macro_scores", rows, "observation_date")


def get_latest_date(table: str, date_col: str = "observation_date") -> str | None:
    """查詢資料庫中最新的日期，用於增量上傳。"""
    res = supabase.table(table).select(date_col).order(date_col, desc=True).limit(1).execute()
    if res.data:
        return res.data[0][date_col]
    return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="全量上傳（首次使用）")
    args = parser.parse_args()

    if args.full:
        print("=== 全量上傳模式 ===")
        upload_macro_raw()
        upload_macro_scores()
    else:
        print("=== 增量上傳模式 ===")
        since_raw    = get_latest_date("macro_raw")
        since_scores = get_latest_date("macro_scores")
        print(f"  macro_raw    最新日期：{since_raw}")
        print(f"  macro_scores 最新日期：{since_scores}")
        upload_macro_raw(since_date=since_raw)
        upload_macro_scores(since_date=since_scores)

    print("\n完成")
