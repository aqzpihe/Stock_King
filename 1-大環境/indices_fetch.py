"""
indices_fetch.py – 抓取主要美股指數並寫入單獨的 Excel 快取
=================================================================
用途：
  依需求抓取美國主要股市指數（S&P 500、NASDAQ Composite），
  並將結果寫入 `indices_data.xlsx`，與 `fred_data.xlsx` 分離，以便後續比較。

支援的指數（預設勾選）
  - S&P 500      → series_id = "SP500"
  - NASDAQ       → series_id = "NASDAQCOM"
  - DJIA         → series_id = "DJIA"      
  - Russell 2000 → series_id = "RUT"      

使用方法：
  python indices_fetch.py            # 抓取並更新 indices_data.xlsx
  python indices_fetch.py --check    # 只檢視已有快取概況（不呼叫 API）
"""

import os
import argparse
import json
import time
import urllib.request
import urllib.parse
from datetime import datetime

import pandas as pd
import numpy as np
import yfinance as yf  # Yahoo Finance for symbols not in FRED


# -------------------------------------------------------------------
# 設定
# -------------------------------------------------------------------

# Excel 輸出路徑（與 fred_data.xlsx 分離）
INDICES_EXCEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "indices_data.xlsx")
os.makedirs(os.path.dirname(INDICES_EXCEL), exist_ok=True)

# 預設抓取的指數，對應 FRED series_id
SELECTED_INDICES = [
    ("S&P 500", "SP500"),
    ("NASDAQ Composite", "NASDAQCOM"),
    ("DJIA", "DJIA"),
    ("Russell 2000", "RUT"),
]

# 抓取起始日（可自行調整）
START_DATE = "2000-01-01"

# API 速率控制（< 120 req/min）
API_DELAY_SECONDS = 0.6

# -------------------------------------------------------------------
# 輔助函式
# -------------------------------------------------------------------

def load_env():
    """讀取 .env 檔案中的環境變數（FRED_API）"""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip()


def fetch_series(api_key, series_id, start_date, end_date=None):
    """抓取單一 series 的 observations，回傳 pandas.Series（index 為 datetime）"""
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start_date,
    }
    if end_date:
        params["observation_end"] = end_date

    url = "https://api.stlouisfed.org/fred/series/observations?" + urllib.parse.urlencode(params)
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
        series = pd.Series(values, index=pd.to_datetime(dates), name=series_id)
        print(f"  [OK] {series_id:15s} {len(series):>5d} 筆  {series.index.min().date()} ~ {series.index.max().date()}")
    except Exception as e:
        print(f"  [FAIL] {series_id}: {e}")
        series = pd.Series(dtype=float, name=series_id)
    time.sleep(API_DELAY_SECONDS)
    return series


def fetch_yahoo_series(ticker, start_date, end_date=None, max_retries=3):
    """使用 yfinance 下載指定 ticker 的每日收盤價，含重試機制"""
    for attempt in range(1, max_retries + 1):
        try:
            if attempt > 1:
                wait = 10 * attempt  # 第2次等20秒，第3次等30秒
                print(f"  [RETRY] 第 {attempt} 次嘗試，先等待 {wait} 秒...")
                time.sleep(wait)
            data = yf.download(ticker, start=start_date, end=end_date, progress=False, auto_adjust=True)
            if data.empty:
                print(f"  [WARN] {ticker}: 第 {attempt} 次嘗試回傳空資料")
                continue
            close = data["Close"].squeeze()
            close = close.dropna()
            close.name = ticker
            print(f"  [OK] {ticker:15s} {len(close):>5d} 筆  "
                  f"{close.index.min().date()} ~ {close.index.max().date()}")
            return close
        except Exception as e:
            print(f"  [WARN] {ticker}: 第 {attempt} 次嘗試失敗 - {e}")
    print(f"  [FAIL] {ticker}: 重試 {max_retries} 次後仍失敗")
    return pd.Series(dtype=float, name=ticker)

# -------------------------------------------------------------------
# 主流程
# -------------------------------------------------------------------

def fetch_and_save():
    """抓取所有選取的指數並寫入 `indices_data.xlsx`"""
    load_env()
    api_key = os.environ.get("FRED_API")
    if not api_key:
        raise ValueError("未在 .env 中找到 FRED_API")

    print(f"\n{'='*60}")
    print(f"  指數資料抓取  →  {INDICES_EXCEL}")
    print(f"  時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    selected = [(name, sid) for name, sid in SELECTED_INDICES]

    with pd.ExcelWriter(INDICES_EXCEL, engine="openpyxl") as writer:
        for name, sid in selected:
            print(f"[指數] {name} ({sid})")
            if sid == "RUT":
                series = fetch_yahoo_series("^RUT", START_DATE)
            else:
                series = fetch_series(api_key, sid, START_DATE)
            if series.empty:
                print(f"  !! {name} 無資料，跳過\n")
                continue
            df = series.reset_index()
            df.columns = ["date", sid]
            df["date"] = df["date"].dt.strftime("%Y-%m-%d")
            # 每個指數一個工作表，工作表名稱使用簡潔的英文名稱
            sheet_name = sid
            df.to_excel(writer, sheet_name=sheet_name, index=False)
            print(f"  -> 寫入 '{sheet_name}'：{df.shape[0]} 筆 x {df.shape[1]} 欄\n")

    print(f"{'='*60}")
    print("  完成！指數資料已寫入:")
    print(f"  {INDICES_EXCEL}")
    print(f"{'='*60}\n")


def check_cache():
    """列出已快取的指數檔案概況（不呼叫 API）"""
    if not os.path.exists(INDICES_EXCEL):
        print(f"!! 找不到快取檔案：{INDICES_EXCEL}")
        print("   請先執行 `python indices_fetch.py` 以建立快取。")
        return
    print(f"\n{'='*60}")
    print(f"  指數快取概況：{INDICES_EXCEL}")
    print(f"{'='*60}\n")
    xl = pd.ExcelFile(INDICES_EXCEL)
    for sheet in xl.sheet_names:
        df = xl.parse(sheet, parse_dates=["date"])
        cols = [c for c in df.columns if c != "date"]
        dates = df["date"].dropna()
        print(f"  [{sheet}]")
        print(f"    欄位: {', '.join(cols)}")
        if len(dates) > 0:
            print(f"    日期: {dates.min().date()} ~ {dates.max().date()}  ({len(df)} 筆)")
            last = df.iloc[-1]
            vals = {c: f"{last[c]:.4f}" if pd.notna(last[c]) else "NaN" for c in cols}
            print(f"    最新: {vals}")
        print()

# -------------------------------------------------------------------
# 入口
# -------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="抓取美股指數並寫入 Excel 快取")
    parser.add_argument("--check", action="store_true", help="只檢視快取概況，不打 API")
    args = parser.parse_args()
    if args.check:
        check_cache()
    else:
        fetch_and_save()
