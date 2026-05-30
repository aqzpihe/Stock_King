#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════╗
║  美國財政部 TIC 數據爬蟲                              ║
║  US Treasury International Capital (TIC) Scraper     ║
║                                                      ║
║  抓取三類核心數據：                                   ║
║  1. MFH  — 主要外國持有美債量 (Major Foreign Holders) ║
║  2. SLT  — 加總持有量 (Aggregate Holdings, Tables 1-4)║
║  3. 交易數據 — SLT Table 4 (S-Form 停用後的替代方案)  ║
╚══════════════════════════════════════════════════════╝

使用方式：
    pip install requests pandas
    python tic_scraper.py

輸出：
    ./tic_data/  目錄下的 .txt 原始檔與 .csv 解析檔
"""

import os
import re
import time
import requests
import pandas as pd
from io import StringIO
from datetime import datetime

# ─────────────────────────────────────────
# ① 設定
# ─────────────────────────────────────────
BASE_URL   = "https://ticdata.treasury.gov"
OUTPUT_DIR = "./data/tic_data"
HEADERS    = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}
REQUEST_DELAY = 1.0   # 每次請求間隔秒數（禮貌性爬取）
RETRIES       = 3     # 請求失敗重試次數

os.makedirs(OUTPUT_DIR, exist_ok=True)


# ─────────────────────────────────────────
# ② 工具函式
# ─────────────────────────────────────────
def fetch(url: str) -> requests.Response | None:
    """帶重試的 HTTP GET，失敗回傳 None。"""
    for attempt in range(1, RETRIES + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            print(f"    [嘗試 {attempt}/{RETRIES}] 請求失敗 → {e}")
            if attempt < RETRIES:
                time.sleep(REQUEST_DELAY * 2)
    return None


def save_txt(fname: str, text: str) -> str:
    path = os.path.join(OUTPUT_DIR, fname)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def parse_and_save_csv(text: str, fname_base: str) -> pd.DataFrame | None:
    """
    嘗試將 tab-delimited TXT 解析為 DataFrame，
    並存成 UTF-8 BOM 的 CSV（Excel 可直接開啟）。
    回傳 DataFrame 或 None。
    """
    lines = text.splitlines()
    # 找第一個含 \t 且有數字的行作為資料起點
    data_start = next(
        (i for i, ln in enumerate(lines) if "\t" in ln and re.search(r"\d", ln)),
        None
    )
    if data_start is None:
        return None

    try:
        clean = "\n".join(lines[data_start:])
        df = pd.read_csv(StringIO(clean), sep="\t", on_bad_lines="skip")
        df = df.dropna(how="all", axis=1).dropna(how="all", axis=0)

        csv_path = os.path.join(OUTPUT_DIR, fname_base + ".csv")
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        return df
    except Exception as e:
        print(f"    ⚠️  解析 CSV 失敗：{e}")
        return None


def download(label: str, fname_base: str, url: str) -> pd.DataFrame | None:
    """下載、儲存 TXT、解析 CSV，回傳 DataFrame。"""
    print(f"  ▶ {label}")
    print(f"    URL  : {url}")
    resp = fetch(url)
    if resp is None:
        print(f"    ❌ 下載失敗，略過。")
        return None

    txt_path = save_txt(fname_base + ".txt", resp.text)
    size_kb  = len(resp.content) / 1024
    print(f"    TXT  : {txt_path}  ({size_kb:.1f} KB)")

    df = parse_and_save_csv(resp.text, fname_base)
    if df is not None:
        print(f"    CSV  : {os.path.join(OUTPUT_DIR, fname_base+'.csv')}"
              f"  ({len(df)} rows × {len(df.columns)} cols)")
    else:
        print(f"    ⚠️  無法自動解析為表格，僅儲存原始 TXT。")

    time.sleep(REQUEST_DELAY)
    return df


# ─────────────────────────────────────────
# ③ 任務定義
# ─────────────────────────────────────────

TASKS = {

    # ════════════════════════════════════════
    # 第一類：MFH — Major Foreign Holders
    # 最新月份大國持債排名（前 30 大）
    # ════════════════════════════════════════
    "【MFH】Table 5 (最新月 + 歷史)": {
        "fname": "mfh_table5",
        "url"  : f"{BASE_URL}/resource-center/data-chart-center/tic/Documents/slt_table5.txt",
    },
    "【MFH】mfh.txt (當期詳細版本)": {
        "fname": "mfh_latest",
        "url"  : f"{BASE_URL}/Publish/mfh.txt",
    },
    "【MFH】歷史 (每年12月, back to 2000)": {
        "fname": "mfh_history",
        "url"  : f"{BASE_URL}/Publish/mfhhis01.txt",
    },

    # ════════════════════════════════════════
    # 第二類：SLT — Aggregate Holdings
    # ════════════════════════════════════════
    "【SLT】Table 1 外國人持有美國長期證券": {
        "fname": "slt_table1",
        "url"  : f"{BASE_URL}/resource-center/data-chart-center/tic/Documents/slt_table1.txt",
    },
    "【SLT】Table 2 美國人持有外國長期證券": {
        "fname": "slt_table2",
        "url"  : f"{BASE_URL}/resource-center/data-chart-center/tic/Documents/slt_table2.txt",
    },
    "【SLT】Table 3 外國人持有美國國庫券細項": {
        "fname": "slt_table3",
        "url"  : f"{BASE_URL}/resource-center/data-chart-center/tic/Documents/slt_table3.txt",
    },

    # ════════════════════════════════════════
    # 第三類：交易數據（S-Form 替代方案）
    # S-Form 已於 2023-02-21 停用
    # 現在改用 SLT Table 4 (淨買賣交易量)
    # ════════════════════════════════════════
    "【交易】SLT Table 4 淨買賣（S-Form 替代）": {
        "fname": "slt_table4",
        "url"  : f"{BASE_URL}/resource-center/data-chart-center/tic/Documents/slt_table4.txt",
    },
    # 保留 2023-01 以前的歷史 S-Form 彙整（若伺服器仍存在）
    "【交易】S-Form 歷史彙整 (ends 2023-01)": {
        "fname": "sform_legacy_s1_99996",
        "url"  : f"{BASE_URL}/resource-center/data-chart-center/tic/Documents/s1_99996.txt",
    },
}


# ─────────────────────────────────────────
# ④ 主程式
# ─────────────────────────────────────────
def main():
    print()
    print("╔══════════════════════════════════════════╗")
    print("║  TIC 數據爬蟲  啟動                      ║")
    print(f"║  執行時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}          ║")
    print("╚══════════════════════════════════════════╝")
    print(f"輸出目錄：{os.path.abspath(OUTPUT_DIR)}")
    print()

    all_results: dict[str, pd.DataFrame | None] = {}

    section_map = {
        "【MFH】":  "1. MFH — 主要外國持有美債量",
        "【SLT】":  "2. SLT — 加總持有量 (Aggregate Holdings)",
        "【交易】": "3. 交易數據 (S-Form / SLT Table 4)",
    }
    current_section = ""

    for label, cfg in TASKS.items():
        # 印出章節標題
        for prefix, section_title in section_map.items():
            if label.startswith(prefix) and section_title != current_section:
                current_section = section_title
                print("=" * 55)
                print(f"  {section_title}")
                print("=" * 55)

        df = download(label, cfg["fname"], cfg["url"])
        all_results[label] = df

    # ── 完成摘要 ──
    print()
    print("=" * 55)
    print("  ✅ 下載完成！檔案清單：")
    print("=" * 55)
    files = sorted(os.listdir(OUTPUT_DIR))
    total_kb = 0
    for fn in files:
        fp   = os.path.join(OUTPUT_DIR, fn)
        kb   = os.path.getsize(fp) / 1024
        total_kb += kb
        print(f"  {fn:<40} {kb:>8.1f} KB")
    print(f"  {'合計：':<40} {total_kb:>8.1f} KB")

    print()
    print("後續分析建議：")
    print("  mfh_table5.csv / mfh_latest.txt   → 各國持債排名、月度變化追蹤")
    print("  slt_table1.csv                     → 外國資本全類型持倉（美債+公司債+股票）")
    print("  slt_table3.csv                     → 純美債細項（到期結構、official vs private）")
    print("  slt_table4.csv                     → 淨交易量 → 流動性模型、資金流向分析")
    print()


if __name__ == "__main__":
    main()
