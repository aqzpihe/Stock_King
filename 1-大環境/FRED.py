"""
FRED.py — FRED 資料抓取與本地 Excel 快取
=========================================
用途：
  一次性（或按需）從 FRED API 抓取所有景氣與政策所需序列，
  依「分類」存至 Excel 多個工作表，結構與未來 Google Sheets 對齊。

Excel 工作表分類（直接對應 Google Sheets 分頁）：
  Sheet 名稱              Series IDs
  ─────────────────────────────────────────────
  信用利差                CPN3M, DTB6, DPRIME, DBAA, DGS10
  貨幣政策                DFF
  通膨                    CPIAUCSL
  匯率                    DTWEXBGS, EMVEXRATES
  股市指數                DJIA

每個工作表格式（欄位）：
  date | <series_id_1> | <series_id_2> | ...

使用：
  python FRED.py                   # 抓取並更新 fred_data.xlsx
  python FRED.py --check           # 只印出目前快取的資料概況，不打 API
"""

import os
import sys
import json
import time
import argparse
import urllib.request
import urllib.parse
from datetime import datetime

import pandas as pd
import numpy as np


# ──────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────

EXCEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fred_data.xlsx")

# Google Sheets / Excel 工作表分類定義
# 格式：(工作表名稱, [series_id, ...], 起始日期, 備註)
SHEET_CATEGORIES = [
    (
        "信用利差",
        ["CPN3M", "DTB6", "DPRIME", "DBAA", "DGS10"],
        "2009-01-01",
        # CPN3M: 90-Day AA Nonfinancial Commercial Paper Rate (月頻)
        # DTB6 : 6-Month Treasury Bill Secondary Market Rate   (日頻)
        # DPRIME: Bank Prime Loan Rate                          (日頻)
        # DBAA  : Moody's Seasoned Baa Corporate Bond Yield    (日頻)
        # DGS10 : 10-Year Treasury Constant Maturity Rate      (日頻)
    ),
    (
        "貨幣政策",
        ["DFF"],
        "2009-01-01",
        # DFF: Effective Federal Funds Rate (日頻)
    ),
    (
        "通膨",
        ["CPIAUCSL"],
        "2009-01-01",
        # CPIAUCSL: CPI All Urban Consumers (月頻) — 需多抓 12 個月算 YoY
    ),
    (
        "匯率",
        ["DTWEXBGS", "EMVEXRATES"],
        "2009-01-01",
        # DTWEXBGS  : Nominal Broad U.S. Dollar Index        (日頻)
        # EMVEXRATES: Exchange Rate Volatility Tracker       (月頻)
    ),
    (
        "股市指數",
        ["DJIA"],
        "2009-01-01",
        # DJIA: Dow Jones Industrial Average (日頻)
    ),
    # -------------------- 新增資料類別 --------------------
    (
        "利率與殖利率",
        ["FEDFUNDS", "DGS2", "DGS30", "MORTGAGE30US"],
        "2009-01-01",
        # FEDFUNDS: Effective Federal Funds Rate (日頻)
        # DGS2: 2-Year Treasury Constant Maturity Rate (日頻)
        # DGS30: 30-Year Treasury Constant Maturity Rate (日頻)
        # MORTGAGE30US: 30-Year Fixed Rate Mortgage Average (日頻)
    ),
    (
        "通膨與價格指數",
        ["CPIAUCSL", "PCE", "PPIACO"],
        "2009-01-01",
        # CPIAUCSL: 消費者物價指數 (月頻)
        # PCE: 個人消費支出價格指數 (月頻)
        # PPIACO: 生產者物價指數 (月頻)
    ),
    (
        "就業市場",
        ["UNRATE", "PAYEMS", "ICSA"],
        "2009-01-01",
        # UNRATE: 失業率 (月頻)
        # PAYEMS: 非農就業人數 (月頻)
        # ICSA: 初次申領失業救濟金人數 (月頻)
    ),
    (
        "GDP與商業活動",
        ["GDP", "INDPRO", "UMCSENT"],
        "2009-01-01",
        # GDP: 國內生產總值 (季頻) -> 會被抓回日頻（FRED 會回傳每季最後一天）
        # INDPRO: 工業生產指數 (月頻)
        # UMCSENT: 密西根大學消費者信心指數 (月頻)
    ),
]

# API 速率控制（< 120 req/min）
API_DELAY_SECONDS = 0.6
FETCH_START_DEFAULT = "2009-01-01"


# ──────────────────────────────────────────────
# 環境變數
# ──────────────────────────────────────────────

def load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip()


# ──────────────────────────────────────────────
# FRED API 抓取
# ──────────────────────────────────────────────

def fetch_series(api_key, series_id, start_date, end_date=None):
    """抓單一 series 的 observations，回傳 pd.Series（index=date）"""
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start_date,
    }
    if end_date:
        params["observation_end"] = end_date

    url = ("https://api.stlouisfed.org/fred/series/observations?"
           + urllib.parse.urlencode(params))

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        obs = data.get("observations", [])
        dates, values = [], []
        for o in obs:
            dates.append(o["date"])
            v = o["value"]
            values.append(np.nan if v == "." else float(v))

        s = pd.Series(values, index=pd.to_datetime(dates), name=series_id)
        print(f"  [OK] {series_id:15s} {len(s):>5d} 筆  "
              f"{s.index.min().date()} ~ {s.index.max().date()}")
    except Exception as e:
        print(f"  [FAIL] {series_id}: {e}")
        s = pd.Series(dtype=float, name=series_id)

    time.sleep(API_DELAY_SECONDS)
    return s


# ──────────────────────────────────────────────
# 主邏輯
# ──────────────────────────────────────────────

def fetch_and_save():
    """抓取所有 series 並依分類存至 Excel 多工作表"""
    load_env()
    api_key = os.environ.get("FRED_API")
    if not api_key:
        raise ValueError("未在 .env 中找到 FRED_API")

    print(f"\n{'='*60}")
    print(f"  FRED 資料抓取  →  {EXCEL_PATH}")
    print(f"  時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    with pd.ExcelWriter(EXCEL_PATH, engine="openpyxl") as writer:
        for sheet_name, series_ids, start_date, *_ in SHEET_CATEGORIES:
            print(f"[工作表] {sheet_name}  ({', '.join(series_ids)})")

            # 抓各 series
            frames = {}
            for sid in series_ids:
                s = fetch_series(api_key, sid, start_date)
                if not s.empty:
                    frames[sid] = s

            if not frames:
                print(f"  !! 此分類無任何資料，跳過\n")
                continue

            # 合併為 DataFrame（date 為 index）
            df = pd.DataFrame(frames)

            # forward-fill（填週末/假日空值）後 reset index，date 成為欄位
            df = df.sort_index().ffill()
            df.index.name = "date"
            df = df.reset_index()
            df["date"] = df["date"].dt.strftime("%Y-%m-%d")

            # 寫入對應工作表
            df.to_excel(writer, sheet_name=sheet_name, index=False)
            print(f"  -> 寫入 '{sheet_name}'：{df.shape[0]} 筆 x {df.shape[1]} 欄\n")

    print(f"{'='*60}")
    print(f"  全部完成！Excel 已儲存至：")
    print(f"  {EXCEL_PATH}")
    print(f"{'='*60}\n")


def check_cache():
    """讀取現有 Excel 並印出各工作表的概況，不打 API"""
    if not os.path.exists(EXCEL_PATH):
        print(f"!! 找不到快取檔案：{EXCEL_PATH}")
        print("   請先執行 `python FRED.py` 以建立快取。")
        return

    print(f"\n{'='*60}")
    print(f"  快取概況：{EXCEL_PATH}")
    print(f"{'='*60}\n")

    xl = pd.ExcelFile(EXCEL_PATH)
    for sheet in xl.sheet_names:
        df = xl.parse(sheet, parse_dates=["date"])
        dates = df["date"].dropna()
        cols = [c for c in df.columns if c != "date"]
        print(f"  [{sheet}]")
        print(f"    欄位: {', '.join(cols)}")
        if len(dates) > 0:
            print(f"    日期: {dates.min().date()} ~ {dates.max().date()}"
                  f"  ({len(df)} 筆)")
            # 印最新一筆
            last = df.iloc[-1]
            vals = {c: f"{last[c]:.4f}" if pd.notna(last[c]) else "NaN"
                    for c in cols}
            print(f"    最新: {vals}")
        print()


# ──────────────────────────────────────────────
# 入口
# ──────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FRED 資料抓取與 Excel 快取")
    parser.add_argument("--check", action="store_true",
                        help="只查看現有快取概況，不打 API")
    args = parser.parse_args()

    if args.check:
        check_cache()
    else:
        fetch_and_save()
