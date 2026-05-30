"""景氣與政策 Score 系統 - 配置檔（V2）"""

# ── FRED Series 清單 ────────────────────────────────────────────
# 格式：'欄位名稱': 'FRED Series ID'
# 頻率說明：D=日, W=週, M=月, Q=季

# --- V1 原有指標 ---
FRED_SERIES = {
    # 信用利差（日頻）
    'CPN3M':      'CPN3M',       # 90-Day AA Commercial Paper Rate (D)
    'DTB6':       'DTB6',        # 6-Month Treasury Bill Secondary Market Rate (D)
    'DPRIME':     'DPRIME',      # Bank Prime Loan Rate (D)
    'DBAA':       'DBAA',        # Moody's Seasoned Baa Corporate Bond Yield (D)
    'DGS10':      'DGS10',       # 10-Year Treasury Constant Maturity Rate (D)
    # 貨幣政策（日頻）
    'DFF':        'DFF',         # Effective Federal Funds Rate (D)
    # 通膨（月頻）
    'CPIAUCSL':   'CPIAUCSL',    # CPI All Urban Consumers (M)
    # 匯率（日/月頻）
    'DTWEXBGS':   'DTWEXBGS',    # Nominal Broad U.S. Dollar Index (D)
    'EMVEXRATES': 'EMVEXRATES',  # Exchange Rate Volatility Tracker (M)
}

# --- V2 新增指標 ---
FRED_SERIES_V2 = {
    # 信用壓力（季頻，forward-fill 到日頻）
    'DRBLACBS':   'DRBLACBS',    # Delinquency Rate on Business Loans (Q) — 商業貸款違約率
    # 衰退預警（日頻）
    'T10Y2Y':     'T10Y2Y',      # 10-Year minus 2-Year Treasury Spread (D) — 殖利率曲線倒掛
    # 勞動市場動能（月頻）
    'JTSJOL':     'JTSJOL',      # Job Openings: Total Nonfarm (M) — 職位空缺數
    'JTSQUR':     'JTSQUR',      # Quits: Total Nonfarm Rate (M) — 自主辭職率
    # 創新與創造（月頻）
    'BABATOT':    'BABATOT',     # Business Applications: Total (M) — 新企業成立申請數
    # 國際資本（季頻）
    'BOPBCA':     'BOPBCA',      # Current Account Balance (Q) — 美國經常帳餘額
    # 淨流動性（週/日頻）
    'WALCL':      'WALCL',       # Assets: Total Assets: Total Assets (W) — Fed 資產負債表總額
    'WTREGEN':    'WTREGEN',     # U.S. Treasury: Cash Balance: General Account (W) — TGA 帳戶餘額
    'RRPONTSYD':  'RRPONTSYD',   # Overnight Reverse Repurchase Agreements (D) — 逆回購 (RRP)
}

# 淨流動性計算公式（V2）：
# Net Liquidity = WALCL - WTREGEN - RRPONTSYD
# 正值越大 → 市場流動性越充裕 → 風險資產偏多
NET_LIQUIDITY_FORMULA = {
    'total_assets': 'WALCL',
    'tga':          'WTREGEN',
    'rrp':          'RRPONTSYD',
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
