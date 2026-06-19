"""
將爬蟲抓到的 raw data 寫入 Supabase（schema v2）。
支援 6 張財報 sheet 的完整欄位，季度粒度。
"""

from supabase import create_client
import config

supabase = create_client(config.REST_API, config.service_role)

# API key → 資料庫欄位名稱
# Equity / CommonStocks / RetainedEarnings 在 nav 和 liabilities 兩張 sheet 重複，
# 這裡只對應一次（nav 優先），重複 key 不覆蓋已有值。
METRIC_MAP = {
    # ── EPS ──────────────────────────────────────────────────
    "EPS":              "eps",
    "EPST4Q":           "eps_ttm",
    "EPST4QAvg":        "eps_ttm_avg",
    "EPSQOQ":           "eps_qoq",
    "EPSYOY":           "eps_yoy",
    "EPST4QQOQ":        "eps_ttm_qoq",
    "EPST4QYOY":        "eps_ttm_yoy",
    # ── NAV / 股東權益 ────────────────────────────────────────
    "NAV":              "nav",
    "Equity":           "equity",
    "CommonStocks":     "common_stocks",
    "RetainedEarnings": "retained_earnings",
    "ROE":              "roe",
    "ROET4Q":           "roe_ttm",
    # ── 損益表 ───────────────────────────────────────────────
    "Revenue":                                  "revenue",
    "GrossProfit":                              "gross_profit",
    "OperatingExpenses":                        "operating_expenses",
    "ResearchAndDevelopmentExpenses":           "rd_expenses",
    "SellingAndAdministrativeExpenses":         "sga_expenses",
    "OperatingIncome":                          "operating_income",
    "ProfitBeforeTax":                          "profit_before_tax",
    "NetIncome":                                "net_income",
    "NetIncomeAttributableToOwnersOfTheParent": "net_income_parent",
    "GrossMargin":                              "gross_margin",
    "OperatingMargin":                          "operating_margin",
    "NetIncomeMargin":                          "net_income_margin",
    # ── 資產 ─────────────────────────────────────────────────
    "Assets":                     "assets",
    "CurrentAssets":              "current_assets",
    "CashAndCashEquivalents":     "cash_equivalents",
    "ShortTermInvestment":        "short_term_investment",
    "AccountsAndNotesReceivable": "accounts_receivable",
    "Inventories":                "inventories",
    "LongTermInvestment":         "long_term_investment",
    "FixedAssets":                "fixed_assets",
    # ── 負債（重複欄位 Equity/CommonStocks/RetainedEarnings 已在上方處理）──
    "Liabilities":          "liabilities",
    "CurrentLiabilities":   "current_liabilities",
    "LongTermLiabilities":  "long_term_liabilities",
    "AccountsAndNotesPayable": "accounts_payable",
    "AdvanceReceipts":      "advance_receipts",
    "ShortTermBorrowingsAndLongTermLiabilitiesCurrentPortion": "short_term_borrowings",
    "DebtRatio":            "debt_ratio",
    "CurrentRatio":         "current_ratio",
    "QuickRatio":           "quick_ratio",
    # ── 現金流量 ─────────────────────────────────────────────
    "OperatingCashFlow":           "operating_cash_flow",
    "InvestingCashFlow":           "investing_cash_flow",
    "FinancingCashFlow":           "financing_cash_flow",
    "FreeCashFlow":                "free_cash_flow",
    "NetCashFlow":                 "net_cash_flow",
    "CAPEX":                       "capex",
    "DepreciationAndAmortization": "depreciation_amortization",
    "OperatingCashFlowPerShare":   "operating_cash_flow_per_share",
    "FreeCashFlowPerShare":        "free_cash_flow_per_share",
}


def _build_rows(data: dict, ticker: str) -> list[dict]:
    """從 data["quarterly"] 組出每季一筆的 row dict。"""
    time_map = {
        item[0]: item[1]
        for item in data.get("common", {})
                        .get("TimeFiscalQ", {})
                        .get("data", [])
    }

    quarterly = data.get("quarterly", {})
    records: dict[str, dict] = {}

    for api_key, col in METRIC_MAP.items():
        metric_data = quarterly.get(api_key, {}).get("data", [])
        for idx, val in metric_data:
            period = time_map.get(idx)
            if not period:
                continue
            # "無" 及任何非數值字串轉為 None，避免 NUMERIC 欄位寫入失敗
            if isinstance(val, str):
                try:
                    val = float(val)
                except ValueError:
                    val = None
            records.setdefault(period, {"ticker": ticker, "period": period})
            if col not in records[period]:   # 重複 key 不覆蓋
                records[period][col] = val

    return list(records.values())


def upsert_company(data: dict, ticker: str) -> None:
    info = data.get("common", {}).get("StockInfo", {}).get("data", {})
    row = {
        "ticker":   ticker,
        "name":     info.get("name") or info.get("companyName") or ticker,
        "exchange": info.get("exchange"),
        "currency": info.get("currency"),
    }
    supabase.table("companies").upsert(row, on_conflict="ticker").execute()
    print(f"[{ticker}] 公司資訊 upsert OK")


def upsert_fundamentals(data: dict, ticker: str) -> None:
    rows = _build_rows(data, ticker)
    if not rows:
        print(f"[{ticker}] 無季度資料，略過")
        return
    supabase.table("fundamentals").upsert(
        rows, on_conflict="ticker,period"
    ).execute()
    print(f"[{ticker}] 季度財報 upsert {len(rows)} 筆 OK")


def has_data(data: dict) -> bool:
    """monthly.PE 有至少 1 筆非 null 值才視為有效資料。"""
    pe_points = data.get("monthly", {}).get("PE", {}).get("data", [])
    return any(v is not None for _, v in pe_points)


def save(data: dict, ticker: str) -> None:
    """主入口：公司資訊 + 完整季度財報"""
    if not has_data(data):
        print(f"[{ticker}] 無資料，略過")
        return
    upsert_company(data, ticker)
    upsert_fundamentals(data, ticker)
