"""
tic_preprocessor.py — TIC 原始 TXT 前處理
==========================================
解析 mfh_history.txt (Major Foreign Holders of Treasury Securities)
提取所有年月的：
  - Grand Total (全球外國持有美債總額)
  - For. Official (官方持有量)
輸出 data/tic_holdings.csv，格式為長表：
  observation_date, ticker, raw_value

TIC 資料結構分析：
  - mfh_history.txt 是多年度堆疊的寬表
  - 每年一個區塊：先 header (月份列 + 國名列 + ------分隔列)
  - 各國持債量按 tab 分隔
  - 區塊末尾有 Grand Total / For. Official / Treasury Bills / T-Bonds & Notes
  - mfh_table5.txt 是最新一期（格式類似但只有一年）

執行方式：
  python tic_preprocessor.py
"""

import os
import re
from pathlib import Path
import pandas as pd
import numpy as np

BASE_DIR     = Path(__file__).parent
TIC_DATA_DIR = BASE_DIR / "data" / "tic_data"
OUTPUT_CSV   = BASE_DIR / "data" / "tic_holdings.csv"

# 月份名稱 → 數字
MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def parse_mfh_history(filepath: Path) -> pd.DataFrame:
    """
    解析 mfh_history.txt 的多年堆疊寬表。

    每個年度區塊結構：
      Row 1:  \tDec\tNov\tOct\t...  (月份)
      Row 2:  Country\t2025\t2025\t...  (年份)
      Row 3:  \t------\t------\t...   (分隔線)
      Row 4+: 國名\t數值\t數值\t...
      ...
      Grand Total\t數值\t數值\t...
      Of which:
      For. Official\t數值\t數值\t...
      Treasury Bills\t數值\t數值\t...
      T-Bonds & Notes\t數值\t數值\t...
    """
    raw = filepath.read_bytes()
    lines = [b.decode("utf-8", errors="replace") for b in raw.split(b"\r\r\n")]
    # Fallback：若 \r\r\n 分割後行數太少，改用一般 splitlines
    if len(lines) < 10:
        lines = filepath.read_text(encoding="utf-8").splitlines()

    records = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # 尋找月份 header 行（含 tab + 月份名稱）
        # 格式：\tDec\tNov\tOct\t...
        cells = line.split("\t")
        months_in_header = [c.strip().lower() for c in cells if c.strip().lower() in MONTH_MAP]

        if len(months_in_header) >= 6:
            # 這是月份 header
            month_cells = [c.strip() for c in cells]

            # 下一行應該是年份 header
            i += 1
            if i >= len(lines):
                break
            year_line = lines[i].strip()
            year_cells = [c.strip() for c in year_line.split("\t")]

            # 解析年份（取第一個 4 位數字）
            year = None
            for yc in year_cells:
                if re.match(r"^\d{4}$", yc):
                    year = int(yc)
                    break

            if year is None:
                i += 1
                continue

            # 建立 (月, 年) → 欄位索引 映射
            # month_cells 和 year_cells 的索引要對齊
            col_dates = {}
            for idx in range(len(month_cells)):
                m_name = month_cells[idx].lower()
                if m_name in MONTH_MAP:
                    month_num = MONTH_MAP[m_name]
                    # 構造月底日期
                    try:
                        dt = pd.Timestamp(year=year, month=month_num, day=1) + pd.offsets.MonthEnd(0)
                        col_dates[idx] = dt
                    except Exception:
                        pass

            if not col_dates:
                i += 1
                continue

            # 跳過分隔線 (------) 和空行
            i += 1
            while i < len(lines) and (lines[i].strip().replace("\t", "").replace("-", "") == ""
                                       or "------" in lines[i]):
                i += 1

            # 讀取資料行，直到遇到下一個年度區塊或空段落
            while i < len(lines):
                data_line = lines[i].strip()

                # 空行群組（連續空行代表區塊結束）
                if data_line.replace("\t", "").strip() == "":
                    # 檢查下一行是否也是空行或新 header
                    i += 1
                    if i < len(lines):
                        next_line = lines[i].strip()
                        if next_line.replace("\t", "").strip() == "":
                            break  # 雙空行，區塊結束
                        # 單空行，可能是 "Of which:" 前的分隔
                        continue
                    break

                # 跳過 "Of which:" 標記行
                if data_line.lower().startswith("of which"):
                    i += 1
                    continue

                data_cells = data_line.split("\t")
                if len(data_cells) < 2:
                    i += 1
                    continue

                # 第一欄是國名/類別名
                label = data_cells[0].strip().strip('"').strip()

                # 我們只需要這些 summary 行
                target_labels = {
                    "Grand Total": "TIC_GRAND_TOTAL",
                    "For. Official": "TIC_OFFICIAL",
                    "Treasury Bills": "TIC_OFFICIAL_BILLS",
                    "T-Bonds & Notes": "TIC_OFFICIAL_BONDS",
                    # 也擷取主要國家
                    "Japan": "TIC_JAPAN",
                    "China, Mainland": "TIC_CHINA",
                }

                ticker = target_labels.get(label)
                if ticker:
                    for idx, dt in col_dates.items():
                        if idx < len(data_cells):
                            val_str = data_cells[idx].strip().replace(",", "")
                            try:
                                val = float(val_str)
                                records.append({
                                    "observation_date": dt.strftime("%Y-%m-%d"),
                                    "ticker": ticker,
                                    "raw_value": val,
                                })
                            except (ValueError, TypeError):
                                pass

                i += 1
            continue

        i += 1

    df = pd.DataFrame(records)
    if not df.empty:
        df = df.drop_duplicates(subset=["observation_date", "ticker"], keep="last")
        df = df.sort_values(["ticker", "observation_date"]).reset_index(drop=True)

    return df


def parse_mfh_table5(filepath: Path) -> pd.DataFrame:
    """
    解析 mfh_table5.txt — 最新一期的簡潔格式。
    格式：Country\t2026-02\t2026-01\t...
    """
    raw = filepath.read_bytes()
    lines = [b.decode("utf-8", errors="replace") for b in raw.split(b"\r\r\n")]
    if len(lines) < 5:
        lines = filepath.read_text(encoding="utf-8").splitlines()

    # 找到 Country 開頭的 header 行
    header_idx = None
    for idx, line in enumerate(lines):
        cleaned = line.strip()
        if cleaned.startswith("Country\t"):
            header_idx = idx
            break

    if header_idx is None:
        print("  [WARN] mfh_table5.txt 找不到 Country header")
        return pd.DataFrame()

    header_cells = lines[header_idx].strip().split("\t")
    # header_cells[0] = "Country", header_cells[1:] = "2026-02", "2026-01", ...
    date_cols = {}
    for i, cell in enumerate(header_cells[1:], start=1):
        cell = cell.strip()
        try:
            dt = pd.Timestamp(cell + "-01") + pd.offsets.MonthEnd(0)
            date_cols[i] = dt
        except Exception:
            pass

    target_labels = {
        "Grand Total": "TIC_GRAND_TOTAL",
        "Of Which: Foreign Official": "TIC_OFFICIAL",
        "Of Which: Foreign Official Treasury Bills": "TIC_OFFICIAL_BILLS",
        "Of Which: Foreign Official T-Bonds & Notes": "TIC_OFFICIAL_BONDS",
        "Japan": "TIC_JAPAN",
        "China, Mainland": "TIC_CHINA",
    }

    records = []
    for line in lines[header_idx + 1:]:
        cleaned = line.strip()
        if not cleaned or cleaned.startswith("Notes:"):
            break

        cells = cleaned.split("\t")
        label = cells[0].strip().strip('"')

        ticker = target_labels.get(label)
        if ticker:
            for idx, dt in date_cols.items():
                if idx < len(cells):
                    val_str = cells[idx].strip().replace(",", "")
                    try:
                        val = float(val_str)
                        records.append({
                            "observation_date": dt.strftime("%Y-%m-%d"),
                            "ticker": ticker,
                            "raw_value": val,
                        })
                    except (ValueError, TypeError):
                        pass

    df = pd.DataFrame(records)
    if not df.empty:
        df = df.drop_duplicates(subset=["observation_date", "ticker"], keep="last")
    return df


def main():
    print("=" * 60)
    print("  TIC 原始資料前處理")
    print("=" * 60)

    all_frames = []

    # 1. 歷史資料（多年度）
    hist_path = TIC_DATA_DIR / "mfh_history.txt"
    if hist_path.exists():
        print(f"\n[1] 解析 mfh_history.txt ...")
        df_hist = parse_mfh_history(hist_path)
        print(f"    提取 {len(df_hist)} 筆記錄")
        if not df_hist.empty:
            for t in df_hist["ticker"].unique():
                sub = df_hist[df_hist["ticker"] == t]
                print(f"      {t:25s}  {len(sub):>4d} 筆  "
                      f"{sub['observation_date'].min()} ~ {sub['observation_date'].max()}")
            all_frames.append(df_hist)
    else:
        print(f"  [SKIP] 找不到 {hist_path}")

    # 2. 最新一期（table5）— 補充 history 可能缺少的最近月份
    t5_path = TIC_DATA_DIR / "mfh_table5.txt"
    if t5_path.exists():
        print(f"\n[2] 解析 mfh_table5.txt ...")
        df_t5 = parse_mfh_table5(t5_path)
        print(f"    提取 {len(df_t5)} 筆記錄")
        if not df_t5.empty:
            all_frames.append(df_t5)
    else:
        print(f"  [SKIP] 找不到 {t5_path}")

    # 3. 合併去重
    if not all_frames:
        print("\n!! 無任何 TIC 資料可處理")
        return

    df_all = pd.concat(all_frames, ignore_index=True)
    df_all = df_all.drop_duplicates(subset=["observation_date", "ticker"], keep="last")
    df_all = df_all.sort_values(["ticker", "observation_date"]).reset_index(drop=True)

    # 4. 計算衍生指標：月度變化量 (MoM Change)
    derived = []
    for ticker in ["TIC_GRAND_TOTAL", "TIC_OFFICIAL"]:
        sub = df_all[df_all["ticker"] == ticker].copy()
        sub = sub.sort_values("observation_date")
        sub["mom_change"] = sub["raw_value"].diff()
        for _, row in sub.dropna(subset=["mom_change"]).iterrows():
            derived.append({
                "observation_date": row["observation_date"],
                "ticker": ticker + "_MOM",
                "raw_value": round(row["mom_change"], 2),
            })

    if derived:
        df_derived = pd.DataFrame(derived)
        df_all = pd.concat([df_all, df_derived], ignore_index=True)

    # 5. 儲存
    os.makedirs(OUTPUT_CSV.parent, exist_ok=True)
    df_all.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")

    print(f"\n{'=' * 60}")
    print(f"  TIC 資料處理完成")
    print(f"  輸出：{OUTPUT_CSV}")
    print(f"  總筆數：{len(df_all)}")
    print(f"  Tickers：{sorted(df_all['ticker'].unique())}")
    print(f"  日期範圍：{df_all['observation_date'].min()} ~ {df_all['observation_date'].max()}")
    print(f"{'=' * 60}")

    return df_all


if __name__ == "__main__":
    main()
