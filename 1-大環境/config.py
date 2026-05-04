"""景氣與政策 Score 系統 - 配置檔"""

# FRED Series (日頻版本優先)
FRED_SERIES = {
    'CPN3M':      'CPN3M',       # 90-Day AA Commercial Paper Rate
    'DTB6':       'DTB6',        # 6-Month Treasury Bill (Daily)
    'DPRIME':     'DPRIME',      # Bank Prime Loan Rate (Daily)
    'DBAA':       'DBAA',        # Moody's Baa Corporate Bond Yield (Daily)
    'DGS10':      'DGS10',       # 10-Year Treasury Constant Maturity (Daily)
    'DFF':        'DFF',         # Effective Federal Funds Rate (Daily)
    'CPIAUCSL':   'CPIAUCSL',    # CPI All Urban Consumers (Monthly)
    'DTWEXBGS':   'DTWEXBGS',    # Nominal Broad U.S. Dollar Index (Daily)
    'EMVEXRATES': 'EMVEXRATES',  # Exchange Rate Volatility Tracker
}

# 資料範圍
DATA_START_DATE = '2010-01-01'
CPI_START_DATE  = '2009-01-01'   # CPI 需要額外 12 個月計算 YoY

# Rolling Z-score 參數
ZSCORE_WINDOW      = 2520        # ~10 年交易日
ZSCORE_MIN_PERIODS = 1260        # ~5 年最少期數

# 子 score 權重
WEIGHT_CREDIT  = 0.4
WEIGHT_POLICY  = 0.3
WEIGHT_PRICEFX = 0.3

# Regime 門檻 (由高到低檢查)
REGIME_MAP = [
    (1.0,            3, '宽鬆 / 有利風險資產'),
    (0.0,            2, '中性偏多'),
    (-1.0,           1, '中性偏保守'),
    (float('-inf'),  0, '緊縮 / 風險極高'),
]

# API 速率控制
API_DELAY_SECONDS = 0.6
