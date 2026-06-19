"""
將 V2 管線產出的 data.csv 和 scores.csv 上傳至 Supabase。
- 支援首次全量上傳與每日增量 upsert（衝突時自動覆蓋）
- 大批資料分批上傳，避免單次請求過大
"""

import os
import math
import time
import pandas as pd
from supabase import create_client

def _load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

_load_env()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://yxydsxygylpzewumevsz.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_KEY:
    raise RuntimeError("找不到 SUPABASE_KEY，請在 .env 加入 SUPABASE_KEY=...")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
BATCH_SIZE = 100  # 每批上傳筆數（小批次避免 timeout）


def _clean_rows(rows: list) -> list:
    """將 NaN / inf / -inf 全部換成 None，避免 JSON 序列化失敗。"""
    def clean(v):
        if isinstance(v, float) and not math.isfinite(v):
            return None
        return v
    return [{k: clean(v) for k, v in row.items()} for row in rows]


def _upsert_batch(table: str, rows: list, conflict_col: str) -> None:
    rows = _clean_rows(rows)
    total = len(rows)
    for i in range(0, total, BATCH_SIZE):
        batch = rows[i: i + BATCH_SIZE]
        retries = 3
        for attempt in range(retries):
            try:
                supabase.table(table).upsert(batch, on_conflict=conflict_col).execute()
                break
            except Exception as e:
                if attempt < retries - 1:
                    print(f"  [RETRY {attempt+1}] 批次 {i}~{i+len(batch)} 失敗：{e}")
                    time.sleep(3)
                else:
                    raise
        if (i // BATCH_SIZE) % 10 == 0:
            print(f"  [{table}] {min(i + BATCH_SIZE, total)}/{total} 筆...")
    print(f"  [{table}] upsert {total} 筆 OK")


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
    df = df.replace([float("inf"), float("-inf")], None)
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


def upload_indices(since_date: str = None) -> None:
    """
    從 indices_data.xlsx 上傳股市指數至 macro_raw（SP500, NASDAQCOM, DJIA, RUT）。
    dimension=5 代表市場指數，不參與評分管線。
    """
    path = os.path.join(DATA_DIR, "indices_data.xlsx")
    if not os.path.exists(path):
        print(f"[indices] {path} 不存在，跳過")
        return

    xl = pd.ExcelFile(path)
    rows = []
    for sheet in xl.sheet_names:
        df = xl.parse(sheet, parse_dates=["date"])
        if "date" not in df.columns or sheet not in df.columns:
            continue
        df = df.set_index("date")
        series = df[sheet].dropna()

        if since_date:
            series = series[series.index >= pd.Timestamp(since_date)]

        for dt, val in series.items():
            rows.append({
                "observation_date": dt.strftime("%Y-%m-%d"),
                "ticker":           sheet,
                "raw_value":        round(float(val), 4),
                "frequency":        "D",
                "lag_category":     "Real-time",
                "dimension":        5,
            })

    print(f"[indices] 準備上傳 {len(rows)} 筆...")
    _upsert_batch("macro_raw", rows, "observation_date,ticker")


def get_latest_date(table: str, date_col: str = "observation_date") -> str | None:
    """查詢資料庫中最新的日期，用於增量上傳。"""
    res = supabase.table(table).select(date_col).order(date_col, desc=True).limit(1).execute()
    if res.data:
        return res.data[0][date_col]
    return None


if __name__ == "__main__":
    print("=" * 60)
    print("  macro_db_writer — 智慧增量上傳")
    print("=" * 60)

    # ── 偵測資料庫現有資料 ──────────────────────────────────────────
    print("\n[偵測] 查詢資料庫中已有資料的最新日期...")

    # 評分原始資料（dimension 1–4，不含指數 dimension=5）
    _res = supabase.table("macro_raw").select("observation_date") \
        .in_("dimension", [1, 2, 3, 4]) \
        .order("observation_date", desc=True).limit(1).execute()
    since_raw = _res.data[0]["observation_date"] if _res.data else None

    # 每日評分結果
    since_scores = get_latest_date("macro_scores")

    # 市場指數（dimension=5）
    _res = supabase.table("macro_raw").select("observation_date") \
        .eq("dimension", 5) \
        .order("observation_date", desc=True).limit(1).execute()
    since_idx = _res.data[0]["observation_date"] if _res.data else None

    print(f"  macro_raw  (評分資料) : {since_raw  or '（無資料，將全量上傳）'}")
    print(f"  macro_scores          : {since_scores or '（無資料，將全量上傳）'}")
    print(f"  macro_raw  (市場指數) : {since_idx   or '（無資料，將全量上傳）'}")

    # ── 執行上傳 ────────────────────────────────────────────────────
    print("\n[上傳] 開始上傳新增資料...\n")
    upload_macro_raw(since_date=since_raw)
    upload_macro_scores(since_date=since_scores)
    upload_indices(since_date=since_idx)

    print("\n完成")
