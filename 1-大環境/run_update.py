"""
run_update.py — 1-大環境 自動更新主控腳本
=========================================
邏輯：
  1. 查詢 Supabase macro_scores 的最新 observation_date
  2. 與最近工作日比較：若已是最新則直接結束（跳過）
  3. 否則依序執行完整管線並上傳至 Supabase

執行：
  python run_update.py              # 自動偵測，CI / cron 用
  python run_update.py --force      # 強制重跑（忽略偵測）
"""

import argparse
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

# 強制 UTF-8 + 行緩衝（Windows cp950 不支援 emoji，且避免子程序輸出亂序）
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://yxydsxygylpzewumevsz.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")


# ── 工具函式 ─────────────────────────────────────────────────────────

def last_business_day() -> date:
    """回傳最近的工作日（週一~週五）。"""
    d = date.today() - timedelta(days=1)
    while d.weekday() >= 5:          # 5=Sat, 6=Sun
        d -= timedelta(days=1)
    return d


def detect_last_db_date() -> str | None:
    """查詢 Supabase macro_scores 最新 observation_date。"""
    from supabase import create_client
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    res = (
        sb.table("macro_scores")
        .select("observation_date")
        .order("observation_date", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0]["observation_date"] if res.data else None


def run(script: str, required: bool = True) -> None:
    """在 BASE_DIR 中執行指定 Python 腳本，繼承父程序的環境變數。"""
    print(f"\n{'─'*50}")
    print(f">> python {script}")
    print(f"{'─'*50}")
    env = {**os.environ, "PYTHONUTF8": "1"}  # ponytail: force UTF-8 so emoji in child scripts don't crash on cp950
    result = subprocess.run(
        [sys.executable, script],
        cwd=str(BASE_DIR),
        env=env,
    )
    if result.returncode != 0:
        if required:
            print(f"\n[FAIL] {script} 失敗（exit {result.returncode}），中止。")
            sys.exit(result.returncode)
        else:
            print(f"\n[WARN] {script} 失敗（exit {result.returncode}），非必要步驟，繼續執行。")


# ── 主程式 ───────────────────────────────────────────────────────────

def main(force: bool = False) -> None:
    print("=" * 60)
    print("  1-大環境 自動更新管線")
    print("=" * 60)

    if not SUPABASE_KEY:
        print("[FAIL] 缺少 SUPABASE_KEY，請設定環境變數後重試。")
        sys.exit(1)

    # ── 偵測 ──────────────────────────────────────────────────────
    print("\n[偵測] 查詢 Supabase 現有資料...")
    last     = detect_last_db_date()
    expected = last_business_day()
    print(f"  DB 最新資料日期 : {last or '（無資料）'}")
    print(f"  預期最新交易日  : {expected}")

    if not force and last and last >= str(expected):
        print(f"\n[OK] 資料已是最新（{last}），本次跳過。")
        return

    gap = f"缺少 {last} 之後的資料" if last else "DB 無任何資料"
    print(f"\n[更新] {gap}，開始執行管線...\n")

    # ── 資料抓取層 ────────────────────────────────────────────────
    run("FRED.py")                             # FRED 總經 → fred_data.xlsx（增量）
    run("indices_fetch.py")                    # 股市指數 → indices_data.xlsx（增量）
    run("sep_alfred_fetcher.py")               # FOMC SEP → Supabase（官方 FRED ALFRED，增量）
    run("sep_data_fetcher.py", required=False) # SEP 本地 CSV → 供評分管線用（無 Kaggle 用補充資料）
    run("polymarket_fed.py",   required=False) # Polymarket 預測市場（外部服務，失敗不中止）
    run("tic_scraper.py",      required=False) # TIC 外債資料（月更，失敗不中止）
    run("tic_preprocessor.py", required=False) # 依賴 tic_scraper，月更，失敗不中止

    # ── ETL + 評分層 ──────────────────────────────────────────────
    run("build_data_csv.py")  # 整合所有來源 → data.csv
    run("scorer_v2.py")       # 計算評分 → scores.csv

    # ── 上傳至 Supabase ───────────────────────────────────────────
    run("macro_db_writer.py")  # 智慧增量上傳（內部再次偵測日期）

    print("\n" + "=" * 60)
    print("  [DONE] 全部完成")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="1-大環境 自動更新")
    parser.add_argument("--force", action="store_true", help="強制重跑，忽略已是最新的偵測")
    args = parser.parse_args()
    main(force=args.force)