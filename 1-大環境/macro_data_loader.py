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
    抓取所有 FRED 序列 -> 計算 CPI YoY -> 對齊至日頻 DataFrame
    """
    load_env()
    api_key = os.environ.get('FRED_API')
    if not api_key:
        raise ValueError("未在 .env 中找到 FRED_API")

    print("=== FRED API 資料抓取 ===\n")
    all_series = {}

    # 日頻序列
    daily_ids = ['CPN3M', 'DTB6', 'DPRIME', 'DBAA', 'DGS10',
                 'DFF', 'DTWEXBGS', 'EMVEXRATES', 'DJIA']
    for sid in daily_ids:
        s = fetch_fred_series(api_key, sid, start_date, end_date, delay)
        if not s.empty:
            all_series[sid] = s

    # 月頻 CPI (額外回溯 12 個月算 YoY)
    cpi = fetch_fred_series(api_key, 'CPIAUCSL', cpi_start, end_date, delay)
    if not cpi.empty:
        inf_yoy = (cpi / cpi.shift(12) - 1) * 100
        inf_yoy = inf_yoy.dropna()
        inf_yoy.name = 'INF_YOY'
        all_series['INF_YOY'] = inf_yoy
        print(f"  [CALC] INF_YOY: 由 CPIAUCSL 計算完成, {len(inf_yoy)} 筆")

    if not all_series:
        raise ValueError("無法抓取任何資料")

    # 合併 + 營業日 index + forward-fill
    df = pd.DataFrame(all_series)
    full_idx = pd.bdate_range(df.index.min(), df.index.max())
    df = df.reindex(full_idx).ffill()
    df = df[df.index >= start_date]

    print(f"\n=== 最終 DataFrame: {df.shape[0]} 天 x {df.shape[1]} 欄位 ===")
    print(f"日期: {df.index.min().date()} ~ {df.index.max().date()}")
    print(f"欄位: {list(df.columns)}")
    return df
