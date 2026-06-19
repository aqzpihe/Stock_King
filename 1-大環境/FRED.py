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
  利率與殖利率            FEDFUNDS, DGS2, DGS30, MORTGAGE30US
  通膨與價格指數          CPIAUCSL, PCE, PPIACO
  就業市場                UNRATE, PAYEMS, ICSA
  GDP與商業活動           GDP, INDPRO, UMCSENT
  信用壓力                DRBLACBS
  衰退預警                T10Y2Y
  勞動市場動能V2          JTSJOL, JTSQUR
  創新創造                BABATOTALSAUS
  國際資本                BOPBCA
  淨流動性                WALCL, WTREGEN, RRPONTSYD

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

EXCEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "fred_data.xlsx")
os.makedirs(os.path.dirname(EXCEL_PATH), exist_ok=True)

# Google Sheets / Excel 工作表分類定義
# 格式：(工作表名稱, [series_id, ...], 起始日期, 備註)
SHEET_CATEGORIES = [
    (
        "信用利差",
        ["CPN3M", "DTB6", "DPRIME", "DBAA", "DGS10"],
        "2009-01-01",
        # CPN3M : 90-Day AA Nonfinancial Commercial Paper Rate (月頻)
        # DTB6  : 6-Month Treasury Bill Secondary Market Rate  (日頻)
        # DPRIME: Bank Prime Loan Rate                         (日頻)
        # DBAA  : Moody's Seasoned Baa Corporate Bond Yield   (日頻)
        # DGS10 : 10-Year Treasury Constant Maturity Rate     (日頻)
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
        # CPIAUCSL: CPI All Urban Consumers (月頻)
    ),
    (
        "匯率",
        ["DTWEXBGS", "EMVEXRATES"],
        "2009-01-01",
        # DTWEXBGS  : Nominal Broad U.S. Dollar Index   (日頻)
        # EMVEXRATES: Exchange Rate Volatility Tracker  (月頻)
    ),
    (
        "股市指數",
        ["DJIA"],
        "2009-01-01",
        # DJIA: Dow Jones Industrial Average (日頻)
    ),
    (
        "利率與殖利率",
        ["FEDFUNDS", "DGS2", "DGS30", "MORTGAGE30US"],
        "2009-01-01",
        # FEDFUNDS    : Effective Federal Funds Rate            (月頻)
        # DGS2        : 2-Year Treasury Constant Maturity Rate  (日頻)
        # DGS30       : 30-Year Treasury Constant Maturity Rate (日頻)
        # MORTGAGE30US: 30-Year Fixed Rate Mortgage Average     (週頻)
    ),
    (
        "通膨與價格指數",
        ["CPIAUCSL", "PCE", "PPIACO"],
        "2009-01-01",
        # CPIAUCSL: 消費者物價指數 (月頻)
        # PCE     : 個人消費支出價格指數 (月頻)
        # PPIACO  : 生產者物價指數 (月頻)
    ),
    (
        "就業市場",
        ["UNRATE", "PAYEMS", "ICSA"],
        "2009-01-01",
        # UNRATE : 失業率 (月頻)
        # PAYEMS : 非農就業人數 (月頻)
        # ICSA   : 初次申領失業救濟金人數 (週頻)
    ),
    (
        "GDP與商業活動",
        ["GDP", "INDPRO", "UMCSENT"],
        "2009-01-01",
        # GDP    : 國內生產總值 (季頻)
        # INDPRO : 工業生產指數 (月頻)
        # UMCSENT: 密西根大學消費者信心指數 (月頻)
    ),
    (
        "信用壓力",
        ["DRBLACBS"],
        "2009-01-01",
        # DRBLACBS: Delinquency Rate on Business Loans (季頻)
    ),
    (
        "衰退預警",
        ["T10Y2Y"],
        "2000-01-01",
        # T10Y2Y: 10-Year minus 2-Year Treasury Spread (日頻)
    ),
    (
        "勞動市場動能V2",
        ["JTSJOL", "JTSQUR"],
        "2000-12-01",
        # JTSJOL: Job Openings: Total Nonfarm (月頻，千人)
        # JTSQUR: Quits: Total Nonfarm Rate  (月頻，%)
    ),
    (
        "創新創造",
        ["BABATOTALSAUS"],   # ← 修正：原 BABATOT 已更名
        "2004-01-01",
        # BABATOTALSAUS: Business Applications: Total (月頻)
    ),
    (
        "國際資本",
        ["BOPBCA"],
        "2000-01-01",
        # BOPBCA: Current Account Balance (季頻，十億美元)
    ),
    (
        "淨流動性",
        ["WALCL", "WTREGEN", "RRPONTSYD"],
        "2003-01-01",
        # WALCL    : Fed 資產負債表總資產 (週頻，百萬美元)
        # WTREGEN  : U.S. Treasury General Account / TGA (週頻，十億美元)
        # RRPONTSYD: 隔夜逆回購餘額 / RRP (日頻，十億美元)
        #
        # 淨流動性公式：
        #   Net Liquidity = WALCL(M$) / 1000 - WTREGEN(B$) - RRPONTSYD(B$)
    ),
]

# API 速率控制（< 120 req/min）
API_DELAY_SECONDS = 0.6

# 重試設定
MAX_RETRIES  = 3   # 最多重試次數（不含第一次）
RETRY_DELAY  = 8   # 每次重試前等待秒數（HTTP 500 暫時性故障）


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
# FRED API 抓取（含重試）
# ──────────────────────────────────────────────

def fetch_series(api_key, series_id, start_date, end_date=None):
    """
    抓單一 series 的 observations，回傳 pd.Series（index=date）。

    錯誤處理策略：
      - HTTP 400：Series ID 本身無效，直接放棄，不重試。
      - HTTP 500 / 其他網路錯誤：最多重試 MAX_RETRIES 次，
        每次間隔 RETRY_DELAY 秒，全部失敗才回傳空 Series。
    """
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

    for attempt in range(1, MAX_RETRIES + 1):
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
            time.sleep(API_DELAY_SECONDS)
            return s

        except Exception as e:
            err_str = str(e)

            # HTTP 400 → Series ID 無效，不重試
            if "400" in err_str:
                print(f"  [FAIL-400] {series_id}: Series ID 無效 → {e}")
                print(f"             請至 https://fred.stlouisfed.org 確認正確名稱")
                time.sleep(API_DELAY_SECONDS)
                return pd.Series(dtype=float, name=series_id)

            # HTTP 500 / 其他 → 重試
            if attempt < MAX_RETRIES:
                print(f"  [RETRY {attempt}/{MAX_RETRIES}] {series_id}: {e}"
                      f"  → 等 {RETRY_DELAY}s 後重試...")
                time.sleep(RETRY_DELAY)
            else:
                print(f"  [FAIL] {series_id}: 重試 {MAX_RETRIES} 次後仍失敗 → {e}")

    time.sleep(API_DELAY_SECONDS)
    return pd.Series(dtype=float, name=series_id)


# ──────────────────────────────────────────────
# 主邏輯
# ──────────────────────────────────────────────

def _read_existing_sheet(sheet_name: str) -> pd.DataFrame | None:
    """讀取現有 Excel 某工作表，回傳以 date 為 index 的 DataFrame；不存在則回傳 None。"""
    if not os.path.exists(EXCEL_PATH):
        return None
    try:
        df = pd.read_excel(EXCEL_PATH, sheet_name=sheet_name, parse_dates=["date"])
        df = df.set_index("date").sort_index()
        return df
    except Exception:
        return None


def fetch_and_save():
    """抓取所有 series 並依分類存至 Excel 多工作表（增量模式：只抓新資料）"""
    load_env()
    api_key = os.environ.get("FRED_API")
    if not api_key:
        raise ValueError("未在 .env 中找到 FRED_API")

    print(f"\n{'='*60}")
    print(f"  FRED 資料抓取  →  {EXCEL_PATH}")
    print(f"  時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    fail_log = []

    writer_mode = "a" if os.path.exists(EXCEL_PATH) else "w"
    writer_kwargs = {"engine": "openpyxl", "mode": writer_mode}
    if writer_mode == "a":
        writer_kwargs["if_sheet_exists"] = "replace"

    with pd.ExcelWriter(EXCEL_PATH, **writer_kwargs) as writer:
        for sheet_name, series_ids, start_date, *_ in SHEET_CATEGORIES:
            print(f"[工作表] {sheet_name}  ({', '.join(series_ids)})")

            # 讀現有資料，決定從哪天開始抓
            existing_df = _read_existing_sheet(sheet_name)
            if existing_df is not None and not existing_df.empty:
                last_date = existing_df.index.max()
                fetch_from = (last_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
                print(f"  [增量] 現有資料至 {last_date.date()}，從 {fetch_from} 補抓")
            else:
                fetch_from = start_date
                print(f"  [全量] 從 {fetch_from} 開始抓取")

            new_frames = {}
            for sid in series_ids:
                s = fetch_series(api_key, sid, fetch_from)
                if not s.empty:
                    new_frames[sid] = s
                else:
                    fail_log.append((sheet_name, sid))

            # 合併現有 + 新資料
            if existing_df is not None and new_frames:
                new_df = pd.DataFrame(new_frames)
                merged = pd.concat([existing_df, new_df])
                merged = merged[~merged.index.duplicated(keep="last")].sort_index()
            elif existing_df is not None:
                merged = existing_df  # 今天無新資料，保留舊的
            elif new_frames:
                merged = pd.DataFrame(new_frames).sort_index()
            else:
                print(f"  !! 此分類無任何資料，跳過\n")
                continue

            df = merged.ffill()
            df.index.name = "date"
            df = df.reset_index()
            df["date"] = df["date"].dt.strftime("%Y-%m-%d")

            df.to_excel(writer, sheet_name=sheet_name, index=False)
            print(f"  -> 寫入 '{sheet_name}'：{df.shape[0]} 筆 x {df.shape[1]} 欄\n")

    # 最終失敗摘要
    print(f"{'='*60}")
    print(f"  全部完成！Excel 已儲存至：")
    print(f"  {EXCEL_PATH}")
    if fail_log:
        print(f"\n  ⚠️  以下 Series 最終抓取失敗（已跳過）：")
        for sheet, sid in fail_log:
            print(f"     [{sheet}] {sid}")
    else:
        print(f"\n  ✅ 所有 Series 抓取成功，無失敗項目。")
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
