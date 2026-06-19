"""
sep_alfred_fetcher.py
=====================
FOMC SEP 資料的全官方替代方案，完全取代 Kaggle 私人資料集。
使用 FRED ALFRED Vintage API：

  FEDTARMD   → SEP_FFR_CURRENT / SEP_FFR_1Y / SEP_FFR_2Y
  FEDTARMDLR → SEP_FFR_LONG
  DFF (月均)  → SEP_FFR_SPOT

流程：
  1. 取得所有 FEDTARMD vintage dates（每次 SEP 發布日，~4次/年）
  2. 查 Supabase 找 SEP_FFR_CURRENT 的最新日期，只抓新增 vintages
  3. 對每個 vintage 拉三個系列，組成 macro_raw 格式的 rows
  4. Upsert 至 macro_raw

執行：
  python sep_alfred_fetcher.py          # 增量（只補新資料）
  python sep_alfred_fetcher.py --full   # 從頭全量抓（首次或重建）
"""

import argparse
import json
import math
import os
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client

# ── 環境設定 ────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

FRED_API_KEY = os.getenv("FRED_API", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://yxydsxygylpzewumevsz.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
FRED_BASE    = "https://api.stlouisfed.org/fred"

# ── macro_raw 元資料（與 build_data_csv.py TICKER_META 對齊）────────
SEP_META = {
    "SEP_FFR_CURRENT": {"freq": "Q", "lag": "Leading", "dim": 2},
    "SEP_FFR_1Y":      {"freq": "Q", "lag": "Leading", "dim": 2},
    "SEP_FFR_2Y":      {"freq": "Q", "lag": "Leading", "dim": 2},
    "SEP_FFR_LONG":    {"freq": "Q", "lag": "Leading", "dim": 2},
    "SEP_FFR_SPOT":    {"freq": "Q", "lag": "Leading", "dim": 2},
}


# ── FRED helpers ─────────────────────────────────────────────────────

def _fred_get(endpoint: str, params: dict) -> dict:
    p = {**params, "api_key": FRED_API_KEY, "file_type": "json"}
    qs = "&".join(f"{k}={v}" for k, v in p.items())
    req = urllib.request.Request(f"{FRED_BASE}/{endpoint}?{qs}")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def _observations_at_vintage(series_id: str, vintage_date: str) -> pd.DataFrame:
    """取得指定 vintage 的觀測值（ALFRED 模式）。"""
    data = _fred_get("series/observations", {
        "series_id":      series_id,
        "realtime_start": vintage_date,
        "realtime_end":   vintage_date,
    })
    rows = [
        {"date": o["date"], "value": float(o["value"])}
        for o in data.get("observations", [])
        if o["value"] != "."
    ]
    return pd.DataFrame(rows)


def _get_all_vintage_dates() -> list[str]:
    """取得 FEDTARMD 所有歷史 vintage dates（= SEP 發布日）。"""
    data = _fred_get("series/vintagedates", {"series_id": "FEDTARMD"})
    return data.get("vintage_dates", [])


# ── Supabase helpers ─────────────────────────────────────────────────

def _get_last_sep_date(sb) -> str | None:
    """查詢 DB 中 SEP_FFR_CURRENT 的最新 observation_date。"""
    res = (
        sb.table("macro_raw")
        .select("observation_date")
        .eq("ticker", "SEP_FFR_CURRENT")
        .order("observation_date", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0]["observation_date"] if res.data else None


def _upsert(sb, rows: list[dict]) -> None:
    BATCH = 100
    rows = [{k: (None if isinstance(v, float) and not math.isfinite(v) else v)
             for k, v in r.items()} for r in rows]
    for i in range(0, len(rows), BATCH):
        batch = rows[i:i+BATCH]
        for attempt in range(3):
            try:
                sb.table("macro_raw").upsert(
                    batch, on_conflict="observation_date,ticker"
                ).execute()
                break
            except Exception as e:
                if attempt < 2:
                    print(f"  [RETRY {attempt+1}] {e}")
                    time.sleep(3)
                else:
                    raise


# ── 主要邏輯 ─────────────────────────────────────────────────────────

def _fetch_vintage_rows(vintage_date: str) -> list[dict]:
    """
    對單次 FOMC 會議的 vintage date 拉 SEP 資料，
    回傳可直接 upsert 的 macro_raw rows。
    """
    year = int(vintage_date[:4])

    # FEDTARMD: date 欄位格式 "2025-01-01" 代表預測年份
    df_md = _observations_at_vintage("FEDTARMD", vintage_date)
    time.sleep(0.6)

    df_lr = _observations_at_vintage("FEDTARMDLR", vintage_date)
    time.sleep(0.6)

    rows = []

    def _row(ticker: str, value) -> dict | None:
        if value is None:
            return None
        meta = SEP_META[ticker]
        return {
            "observation_date": vintage_date,
            "ticker":           ticker,
            "raw_value":        round(float(value), 4),
            "frequency":        meta["freq"],
            "lag_category":     meta["lag"],
            "dimension":        meta["dim"],
        }

    if not df_md.empty:
        df_md["year"] = df_md["date"].str[:4].astype(int)
        by_year = dict(zip(df_md["year"], df_md["value"]))
        for ticker, target_year in [
            ("SEP_FFR_CURRENT", year),
            ("SEP_FFR_1Y",      year + 1),
            ("SEP_FFR_2Y",      year + 2),
        ]:
            r = _row(ticker, by_year.get(target_year))
            if r:
                rows.append(r)

    if not df_lr.empty:
        r = _row("SEP_FFR_LONG", df_lr["value"].iloc[-1])
        if r:
            rows.append(r)

    return rows


def _fetch_spot_rows(vintage_dates: list[str]) -> list[dict]:
    """抓 DFF 月均作為各 vintage 的 ffr_spot。"""
    data = _fred_get("series/observations", {
        "series_id":        "DFF",
        "observation_start": min(vintage_dates)[:7] + "-01",
    })
    dff_rows = [
        {"date": o["date"], "value": float(o["value"])}
        for o in data.get("observations", [])
        if o["value"] != "."
    ]
    if not dff_rows:
        return []

    dff = pd.DataFrame(dff_rows)
    dff["date"] = pd.to_datetime(dff["date"])
    monthly = dff.set_index("date")["value"].resample("ME").mean()

    meta = SEP_META["SEP_FFR_SPOT"]
    result = []
    for vd in vintage_dates:
        month_end = pd.Period(vd[:7], freq="M").to_timestamp("M")
        if month_end in monthly.index:
            spot = monthly[month_end]
        else:
            idx = monthly.index.get_indexer([month_end], method="nearest")
            spot = monthly.iloc[idx[0]] if idx[0] >= 0 else None
        if spot is not None:
            result.append({
                "observation_date": vd,
                "ticker":           "SEP_FFR_SPOT",
                "raw_value":        round(float(spot), 4),
                "frequency":        meta["freq"],
                "lag_category":     meta["lag"],
                "dimension":        meta["dim"],
            })
    return result


def main(full: bool = False):
    if not FRED_API_KEY:
        raise RuntimeError("缺少 FRED_API，請在 .env 設定")
    if not SUPABASE_KEY:
        raise RuntimeError("缺少 SUPABASE_KEY，請在 .env 設定")

    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    print("=" * 60)
    print("  SEP ALFRED Fetcher")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. 取得所有 vintage dates
    print("\n[1] 取得 FEDTARMD vintage dates ...")
    all_vintages = _get_all_vintage_dates()
    print(f"    共 {len(all_vintages)} 個（{all_vintages[0]} ~ {all_vintages[-1]}）")

    # 2. 決定需要抓取的 vintages
    if full:
        target = all_vintages
        print("\n[2] 全量模式：抓取所有 vintage")
    else:
        last = _get_last_sep_date(sb)
        print(f"\n[2] DB 最新 SEP 日期：{last or '（無資料）'}")
        target = [v for v in all_vintages if last is None or v > last]
        if not target:
            print("    已是最新，無需更新")
            return

    print(f"    需抓取 {len(target)} 個 vintage")

    # 3. 抓取每個 vintage 的 SEP 中位數
    print("\n[3] 抓取 FEDTARMD / FEDTARMDLR ...")
    all_rows: list[dict] = []
    for vd in target:
        rows = _fetch_vintage_rows(vd)
        print(f"    {vd} → {len(rows)} 筆")
        all_rows.extend(rows)

    # 4. 補 ffr_spot (DFF 月均)
    print("\n[4] 抓取 DFF spot ...")
    all_rows.extend(_fetch_spot_rows(target))

    # 5. Upsert
    print(f"\n[5] Upsert {len(all_rows)} 筆至 macro_raw ...")
    _upsert(sb, all_rows)

    print(f"\n{'=' * 60}")
    print(f"  完成！共寫入 {len(all_rows)} 筆 SEP 資料")
    print(f"  涵蓋 {len(target)} 次 FOMC 會議")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SEP ALFRED Fetcher")
    parser.add_argument("--full", action="store_true", help="全量抓取（首次或重建）")
    args = parser.parse_args()
    main(full=args.full)
