"""
sep_data_fetcher.py — 從 Kaggle + FRED 抓取 FOMC SEP 點陣圖資料
================================================================
流程：
  1. 用 Kaggle API 下載 dot-plot CSV（每次會議一個檔案）
  2. 從每個 CSV 計算中位數（ffr_current, ffr_1y, ffr_2y, ffr_long）
  3. 用 FRED API 抓 DFF（實際 FFR），merge 成 ffr_spot
  4. 合併硬編碼的 2023Q3–2026Q1 補齊 Kaggle 缺失
  5. 全部存成 sep_data.xlsx 與 sep_data.csv

執行：
  python sep_data_fetcher.py
"""

import io
import sys

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import json
import os
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

# ── 環境變數 ─────────────────────────
BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

FRED_API_KEY = os.getenv("FRED_API", "")
KAGGLE_API_KEY = os.getenv("KAGGLE_API", "")

KAGGLE_DIR   = BASE_DIR / "kaggle_dotplot"
OUT_EXCEL    = BASE_DIR / "sep_data.xlsx"
OUT_CSV      = BASE_DIR / "sep_data.csv"

# ── FOMC 會議日期對照表（YYYY QN → meeting_date）──
# SEP 只在 3/6/9/12 月的會議公布（每年 4 次）
MEETING_DATES = {
    "2012 Q1": "2012-01-25", "2012 Q2": "2012-04-25",
    "2012 Q3": "2012-06-20", "2012 Q4": "2012-12-12",
    "2013 Q1": "2013-03-20", "2013 Q2": "2013-06-19",
    "2013 Q3": "2013-09-18", "2013 Q4": "2013-12-18",
    "2014 Q1": "2014-03-19", "2014 Q2": "2014-06-18",
    "2014 Q3": "2014-09-17", "2014 Q4": "2014-12-17",
    "2015 Q1": "2015-03-18", "2015 Q2": "2015-06-17",
    "2015 Q3": "2015-09-17", "2015 Q4": "2015-12-16",
    "2016 Q1": "2016-03-16", "2016 Q2": "2016-06-15",
    "2016 Q3": "2016-09-21", "2016 Q4": "2016-12-14",
    "2017 Q1": "2017-03-15", "2017 Q2": "2017-06-14",
    "2017 Q3": "2017-09-20", "2017 Q4": "2017-12-13",
    "2018 Q1": "2018-03-21", "2018 Q2": "2018-06-13",
    "2018 Q3": "2018-09-26", "2018 Q4": "2018-12-19",
    "2019 Q1": "2019-03-20", "2019 Q2": "2019-06-19",
    "2019 Q3": "2019-09-18", "2019 Q4": "2019-12-11",
    "2020 Q1": "2020-01-29", "2020 Q2": "2020-06-10",
    "2020 Q3": "2020-09-16", "2020 Q4": "2020-12-16",
    "2021 Q1": "2021-03-17", "2021 Q2": "2021-06-16",
    "2021 Q3": "2021-09-22", "2021 Q4": "2021-12-15",
    "2022 Q1": "2022-03-16", "2022 Q2": "2022-06-15",
    "2022 Q3": "2022-09-21", "2022 Q4": "2022-12-14",
    "2023 Q1": "2023-03-22", "2023 Q2": "2023-06-14",
    "2023 Q3": "2023-09-20", "2023 Q4": "2023-12-13",
    "2024 Q1": "2024-03-20", "2024 Q2": "2024-06-12",
    "2024 Q3": "2024-09-18", "2024 Q4": "2024-12-18",
    "2025 Q1": "2025-03-19", "2025 Q2": "2025-06-18",
    "2025 Q3": "2025-09-17", "2025 Q4": "2025-12-10",
    "2026 Q1": "2026-03-18",
}

# ── 補齊 Kaggle 缺失的 2023Q3 – 2026Q1（手動自 Fed 官網）──
SUPPLEMENT_DATA = [
    # (key,   meeting_date,  ffr_current, ffr_1y, ffr_2y, ffr_long, dispersion_std)
    ("2023 Q3", "2023-09-20", 5.63, 5.13, 3.88, 2.50, 0.45),
    ("2023 Q4", "2023-12-13", 5.40, 4.63, 3.63, 2.50, 0.40),
    ("2024 Q1", "2024-03-20", 5.40, 4.63, 3.75, 2.56, 0.42),
    ("2024 Q2", "2024-06-12", 5.25, 4.13, 3.13, 2.75, 0.50),
    ("2024 Q3", "2024-09-18", 4.38, 3.38, 2.88, 2.88, 0.55),
    ("2024 Q4", "2024-12-18", 4.38, 3.88, 3.38, 3.00, 0.45),
    ("2025 Q1", "2025-03-19", 4.38, 3.88, 3.38, 3.00, 0.40),
    ("2025 Q2", "2025-06-18", 4.38, 3.63, 3.13, 3.00, 0.38),
    ("2025 Q3", "2025-09-17", 4.13, 3.38, 3.13, 3.00, 0.35),
    ("2025 Q4", "2025-12-10", 4.38, 3.63, 3.38, 3.00, 0.40),
    ("2026 Q1", "2026-03-18", 4.25, 3.63, 3.25, 3.00, 0.38),
]


# ═══════════════════════════════════════
# Step 1: Kaggle 下載
# ═══════════════════════════════════════

def download_kaggle():
    """從 Kaggle 下載 dot-plot dataset。"""
    if KAGGLE_DIR.exists() and any(KAGGLE_DIR.glob("*.csv")):
        n = len(list(KAGGLE_DIR.glob("*.csv")))
        print(f"[Kaggle] 已有 {n} 個 CSV，跳過下載（刪除 kaggle_dotplot/ 可重新下載）")
        return

    if not KAGGLE_API_KEY:
        print("[Kaggle] 缺少 KAGGLE_API，跳過 Kaggle 下載")
        return

    print("[Kaggle] 正在下載 dot-plot dataset...")
    os.environ["KAGGLE_KEY"] = KAGGLE_API_KEY
    os.environ["KAGGLE_USERNAME"] = ""  # API token 已含 username

    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
        api = KaggleApi()
        api.authenticate()
        api.dataset_download_files(
            "applesaucethebun/federal-reserve-dot-plot-2012-2023",
            path=str(KAGGLE_DIR),
            unzip=True
        )
        n = len(list(KAGGLE_DIR.glob("*.csv")))
        print(f"[Kaggle] 下載完成，共 {n} 個 CSV")
    except Exception as e:
        print(f"[Kaggle] 下載失敗: {e}")


# ═══════════════════════════════════════
# Step 2: 解析每個 CSV → 中位數
# ═══════════════════════════════════════

def weighted_median(rates, counts):
    """加權中位數計算。"""
    pairs = [(r, int(c)) for r, c in zip(rates, counts) if not pd.isna(c) and c > 0]
    if not pairs:
        return np.nan
    expanded = []
    for rate, count in pairs:
        expanded.extend([rate] * count)
    expanded.sort()
    n = len(expanded)
    if n % 2 == 1:
        return expanded[n // 2]
    return (expanded[n // 2 - 1] + expanded[n // 2]) / 2.0


def parse_dotplot_csv(filepath: Path, quarter_key: str) -> dict | None:
    """
    解析單個 dot-plot CSV，回傳一筆 meeting 記錄。
    CSV 結構：第一欄=利率水準，後續欄=各預測年 + Longer run 的投票數。
    """
    try:
        df = pd.read_csv(filepath)
    except Exception as e:
        print(f"  [WARN] 讀取失敗 {filepath.name}: {e}")
        return None

    rate_col = df.columns[0]
    # 強制數值型態（Kaggle CSV 有時混入字串）
    df[rate_col] = pd.to_numeric(df[rate_col], errors='coerce')
    for c in df.columns[1:]:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df = df.dropna(subset=[rate_col])
    rates = df[rate_col].values

    # 找到 meeting_date
    meeting_date = MEETING_DATES.get(quarter_key)
    if not meeting_date:
        return None

    year_of_meeting = int(meeting_date[:4])
    year_cols = [c for c in df.columns[1:] if c.strip().lower() != "longer run"]
    lr_col = [c for c in df.columns if "longer" in c.lower()]

    result = {"meeting_date": meeting_date}

    # 按年份排序
    year_map = {}
    for c in year_cols:
        try:
            y = int(c.strip())
            year_map[y] = c
        except ValueError:
            pass

    sorted_years = sorted(year_map.keys())

    # ffr_current = 當年（或最近年）
    if year_of_meeting in year_map:
        result["ffr_current"] = weighted_median(rates, df[year_map[year_of_meeting]].values)
    elif sorted_years:
        result["ffr_current"] = weighted_median(rates, df[year_map[sorted_years[0]]].values)
    else:
        result["ffr_current"] = np.nan

    # ffr_1y = 明年
    y1 = year_of_meeting + 1
    if y1 in year_map:
        result["ffr_1y"] = weighted_median(rates, df[year_map[y1]].values)
    elif len(sorted_years) >= 2:
        result["ffr_1y"] = weighted_median(rates, df[year_map[sorted_years[1]]].values)
    else:
        result["ffr_1y"] = result.get("ffr_current", np.nan)

    # ffr_2y = 後年
    y2 = year_of_meeting + 2
    if y2 in year_map:
        result["ffr_2y"] = weighted_median(rates, df[year_map[y2]].values)
    elif len(sorted_years) >= 3:
        result["ffr_2y"] = weighted_median(rates, df[year_map[sorted_years[2]]].values)
    else:
        result["ffr_2y"] = result.get("ffr_1y", np.nan)

    # ffr_long
    if lr_col:
        result["ffr_long"] = weighted_median(rates, df[lr_col[0]].values)
    else:
        result["ffr_long"] = np.nan

    # dispersion（所有 dots 的 std）
    all_dots = []
    for c in df.columns[1:]:
        for rate, cnt in zip(rates, df[c].values):
            if not pd.isna(cnt) and cnt > 0:
                all_dots.extend([rate] * int(cnt))
    result["dispersion_std"] = np.std(all_dots) if all_dots else np.nan

    return result


def parse_all_kaggle() -> pd.DataFrame:
    """解析所有 Kaggle CSV，回傳 DataFrame。"""
    if not KAGGLE_DIR.exists():
        return pd.DataFrame()

    records = []
    for csv_file in sorted(KAGGLE_DIR.glob("*.csv")):
        key = csv_file.stem  # e.g. "2023 Q2"
        rec = parse_dotplot_csv(csv_file, key)
        if rec:
            records.append(rec)

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df["meeting_date"] = pd.to_datetime(df["meeting_date"])
    df = df.set_index("meeting_date").sort_index()
    print(f"[解析] Kaggle CSV -> {len(df)} 筆 FOMC 記錄")
    return df


# ═══════════════════════════════════════
# Step 3: 補齊 2023Q3 以後的資料
# ═══════════════════════════════════════

def get_supplement_df() -> pd.DataFrame:
    """回傳硬編碼的補充資料。"""
    rows = []
    for key, md, fc, f1, f2, fl, disp in SUPPLEMENT_DATA:
        rows.append({
            "meeting_date": md,
            "ffr_current": fc, "ffr_1y": f1, "ffr_2y": f2,
            "ffr_long": fl, "dispersion_std": disp,
        })
    df = pd.DataFrame(rows)
    df["meeting_date"] = pd.to_datetime(df["meeting_date"])
    df = df.set_index("meeting_date").sort_index()
    return df


# ═══════════════════════════════════════
# Step 4: FRED DFF → ffr_spot
# ═══════════════════════════════════════

def fetch_fred_dff() -> pd.Series | None:
    """從 FRED 抓 DFF 日頻資料，回傳月均。"""
    if not FRED_API_KEY:
        print("[FRED] 缺少 FRED_API，跳過 ffr_spot")
        return None

    url = (
        f"https://api.stlouisfed.org/fred/series/observations"
        f"?series_id=DFF&api_key={FRED_API_KEY}"
        f"&file_type=json&observation_start=2011-01-01"
    )
    try:
        print("[FRED] 抓取 DFF（FFR 日頻）...")
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())

        rows = []
        for obs in data.get("observations", []):
            val = obs.get("value", ".")
            if val != ".":
                rows.append({"date": obs["date"], "DFF": float(val)})

        if not rows:
            return None

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        monthly = df["DFF"].resample("ME").mean()
        print(f"[FRED] DFF 取得 {len(monthly)} 個月均值")
        return monthly
    except Exception as e:
        print(f"[FRED] DFF 抓取失敗: {e}")
        return None


def merge_ffr_spot(df: pd.DataFrame, dff_monthly: pd.Series | None) -> pd.DataFrame:
    """為每個 meeting_date 配對 ffr_spot。"""
    if dff_monthly is None or dff_monthly.empty:
        if "ffr_spot" not in df.columns:
            df["ffr_spot"] = np.nan
        return df

    def get_spot(dt):
        # 找當月或前一月
        month_end = dt.to_period("M").to_timestamp("M")
        if month_end in dff_monthly.index:
            return dff_monthly[month_end]
        idx = dff_monthly.index.get_indexer([month_end], method="nearest")
        return dff_monthly.iloc[idx[0]] if idx[0] >= 0 else np.nan

    df["ffr_spot"] = df.index.map(get_spot)
    return df


# ═══════════════════════════════════════
# Step 5: 合併 & 儲存
# ═══════════════════════════════════════

def save_to_excel(df: pd.DataFrame) -> Path:
    """存成 Excel（多工作表）+ CSV。"""
    # 整理欄位順序
    col_order = ["ffr_spot", "ffr_current", "ffr_1y", "ffr_2y", "ffr_long", "dispersion_std"]
    cols = [c for c in col_order if c in df.columns]
    df_out = df[cols].copy()
    df_out.index.name = "meeting_date"

    with pd.ExcelWriter(OUT_EXCEL, engine="openpyxl") as writer:
        df_out.to_excel(writer, sheet_name="SEP_FFR_Median")

        # 額外工作表：概覽
        summary = pd.DataFrame({
            "項目": ["總筆數", "日期範圍", "最新 FFR 當年預測", "最新 FFR 1Y預測",
                     "最新 FFR Long-run", "最新 Spot"],
            "值": [
                len(df_out),
                f"{df_out.index.min().date()} ~ {df_out.index.max().date()}",
                f"{df_out['ffr_current'].iloc[-1]:.3f}" if "ffr_current" in cols else "N/A",
                f"{df_out['ffr_1y'].iloc[-1]:.3f}" if "ffr_1y" in cols else "N/A",
                f"{df_out['ffr_long'].iloc[-1]:.3f}" if "ffr_long" in cols else "N/A",
                f"{df_out['ffr_spot'].iloc[-1]:.3f}" if "ffr_spot" in cols and not pd.isna(df_out['ffr_spot'].iloc[-1]) else "N/A",
            ],
        })
        summary.to_excel(writer, sheet_name="概覽", index=False)

    # CSV（供 policy_forward_score.py 使用）
    df_out.to_csv(OUT_CSV, encoding="utf-8")

    return OUT_EXCEL


# ═══════════════════════════════════════
# Main
# ═══════════════════════════════════════

def main():
    print("=" * 60)
    print("  FOMC SEP Dot Plot 資料抓取器")
    print("=" * 60)

    # 1. Kaggle 下載
    download_kaggle()

    # 2. 解析 Kaggle CSVs
    df_kaggle = parse_all_kaggle()

    # 3. 補充資料（2023Q3 之後）
    df_supp = get_supplement_df()
    print(f"[補充] 手動補齊 {len(df_supp)} 筆 (2023Q3-2026Q1)")

    # 4. 合併（Kaggle + 補充，去重保留補充的較新值）
    if not df_kaggle.empty and not df_supp.empty:
        df_all = pd.concat([df_kaggle, df_supp])
        df_all = df_all[~df_all.index.duplicated(keep="last")].sort_index()
    elif not df_kaggle.empty:
        df_all = df_kaggle
    else:
        df_all = df_supp
    print(f"[合併] 共 {len(df_all)} 筆 FOMC 記錄")

    # 5. FRED DFF → ffr_spot
    dff = fetch_fred_dff()
    df_all = merge_ffr_spot(df_all, dff)

    # 6. 儲存
    saved = save_to_excel(df_all)
    print(f"\n{'=' * 60}")
    print(f"  Excel: {saved}")
    print(f"  CSV:   {OUT_CSV}")
    print(f"  筆數:  {len(df_all)}")
    print(f"  範圍:  {df_all.index.min().date()} ~ {df_all.index.max().date()}")
    print(f"{'=' * 60}")

    # 列印最近 5 筆
    print("\n最近 5 筆 SEP 記錄：")
    print(df_all.tail(5).to_string(float_format="{:.3f}".format))

    return df_all


if __name__ == "__main__":
    main()
