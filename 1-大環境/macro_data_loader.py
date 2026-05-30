"""景氣與政策 Score - 資料載入模組
透過 FRED API 抓取所有必要序列，對齊至日頻
"""
import os
import json
import time
import urllib.request
import urllib.parse
import pandas as pd
import numpy as np


def load_env():
    """從 .env 載入環境變數"""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    key, val = line.split('=', 1)
                    os.environ[key.strip()] = val.strip()


def fetch_fred_series(api_key, series_id, start_date, end_date=None, delay=0.6):
    """從 FRED API 抓取單一序列，回傳 pandas Series"""
    params = {
        'series_id': series_id,
        'api_key': api_key,
        'file_type': 'json',
        'observation_start': start_date,
    }
    if end_date:
        params['observation_end'] = end_date

    url = f"https://api.stlouisfed.org/fred/series/observations?{urllib.parse.urlencode(params)}"

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))

        observations = data.get('observations', [])
        dates, values = [], []
        for obs in observations:
            dates.append(obs['date'])
            val = obs['value']
            values.append(np.nan if val == '.' else float(val))

        series = pd.Series(values, index=pd.to_datetime(dates), name=series_id)
        print(f"  [OK] {series_id}: {len(series)} 筆 "
              f"({series.index.min().date()} ~ {series.index.max().date()})")
    except Exception as e:
        print(f"  [FAIL] {series_id}: {e}")
        series = pd.Series(dtype=float, name=series_id)

    time.sleep(delay)
    return series


def load_all_data(start_date='2010-01-01', cpi_start='2009-01-01',
                  end_date=None, delay=0.6):
    """
    抓取所有 FRED 序列 -> 計算衍生指標 -> 對齊至日頻 DataFrame

    V1 序列（原有）：
      日頻: CPN3M, DTB6, DPRIME, DBAA, DGS10, DFF, DTWEXBGS, EMVEXRATES, DJIA
      月頻: CPIAUCSL (多抓 12 個月計算 YoY)

    V2 新增序列：
      日頻: T10Y2Y (殖利率倒掛), RRPONTSYD (逆回購)
      週頻: WALCL (Fed 總資產), WTREGEN (TGA 帳戶)
      月頻: JTSJOL (職位空缺), JTSQUR (辭職率), BABATOT (新企業申請)
      季頻: DRBLACBS (商業貸款違約率), BOPBCA (經常帳餘額)

    衍生指標：
      INF_YOY      = (CPIAUCSL / CPIAUCSL.shift(12) - 1) * 100
      NET_LIQUIDITY = WALCL/1000 - WTREGEN - RRPONTSYD  (單位：十億美元)
    """
    load_env()
    api_key = os.environ.get('FRED_API')
    if not api_key:
        raise ValueError("未在 .env 中找到 FRED_API")

    print("=== FRED API 資料抓取 (V2) ===\n")
    all_series = {}

    # ── V1：日頻序列 ─────────────────────────────────────────────
    print("[V1] 日頻序列")
    daily_v1 = ['CPN3M', 'DTB6', 'DPRIME', 'DBAA', 'DGS10',
                 'DFF', 'DTWEXBGS', 'EMVEXRATES', 'DJIA']
    for sid in daily_v1:
        s = fetch_fred_series(api_key, sid, start_date, end_date, delay)
        if not s.empty:
            all_series[sid] = s

    # ── V1：月頻 CPI → INF_YOY ───────────────────────────────────
    print("\n[V1] CPI YoY 計算")
    cpi = fetch_fred_series(api_key, 'CPIAUCSL', cpi_start, end_date, delay)
    if not cpi.empty:
        inf_yoy = (cpi / cpi.shift(12) - 1) * 100
        inf_yoy = inf_yoy.dropna()
        inf_yoy.name = 'INF_YOY'
        all_series['INF_YOY'] = inf_yoy
        print(f"  [CALC] INF_YOY: 由 CPIAUCSL 計算完成, {len(inf_yoy)} 筆")

    # ── V2：日頻序列（衰退預警、逆回購）────────────────────────────
    print("\n[V2] 日頻序列（衰退預警、逆回購）")
    daily_v2 = ['T10Y2Y', 'RRPONTSYD']
    for sid in daily_v2:
        s = fetch_fred_series(api_key, sid, start_date, end_date, delay)
        if not s.empty:
            all_series[sid] = s

    # ── V2：週頻序列（Fed 資產負債表、TGA）──────────────────────────
    print("\n[V2] 週頻序列（淨流動性組件）")
    liq_start = min(start_date, '2003-01-01')   # WALCL 始於 2002-12
    weekly_v2 = ['WALCL', 'WTREGEN']
    for sid in weekly_v2:
        s = fetch_fred_series(api_key, sid, liq_start, end_date, delay)
        if not s.empty:
            all_series[sid] = s

    # ── V2：月頻序列（勞動市場動能、創新創造）────────────────────────
    print("\n[V2] 月頻序列（就業動能、新企業）")
    monthly_v2 = ['JTSJOL', 'JTSQUR', 'BABATOT']
    for sid in monthly_v2:
        s = fetch_fred_series(api_key, sid, start_date, end_date, delay)
        if not s.empty:
            all_series[sid] = s

    # ── V2：季頻序列（信用壓力、國際資本）────────────────────────────
    print("\n[V2] 季頻序列（違約率、經常帳）")
    quarterly_v2 = ['DRBLACBS', 'BOPBCA']
    for sid in quarterly_v2:
        s = fetch_fred_series(api_key, sid, start_date, end_date, delay)
        if not s.empty:
            all_series[sid] = s

    if not all_series:
        raise ValueError("無法抓取任何資料")

    # ── 合併 + 營業日 index + forward-fill ──────────────────────────
    df = pd.DataFrame(all_series)
    full_idx = pd.bdate_range(df.index.min(), df.index.max())
    df = df.reindex(full_idx).ffill()
    df = df[df.index >= start_date]

    # ── 衍生：淨流動性（V2）──────────────────────────────────────────
    # Net Liquidity (B$) = WALCL(M$)/1000 - WTREGEN(B$) - RRPONTSYD(B$)
    if all(c in df.columns for c in ['WALCL', 'WTREGEN', 'RRPONTSYD']):
        df['NET_LIQUIDITY'] = df['WALCL'] / 1000 - df['WTREGEN'] - df['RRPONTSYD']
        latest_liq = df['NET_LIQUIDITY'].dropna()
        if not latest_liq.empty:
            print(f"\n  [CALC] NET_LIQUIDITY: 計算完成"
                  f"  (最新: {latest_liq.iloc[-1]:.1f} B$)")

    print(f"\n=== 最終 DataFrame: {df.shape[0]} 天 x {df.shape[1]} 欄位 ===")
    print(f"日期: {df.index.min().date()} ~ {df.index.max().date()}")
    print(f"欄位: {list(df.columns)}")
    return df

