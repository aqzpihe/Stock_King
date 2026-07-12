"""
fmp_updater.py — 混合策略季報增量更新
  FMP   → 前百大公司.xlsx C欄=True  (19 家大型股)
  EDGAR → 前百大公司.xlsx C欄=False (82 家，SEC免費全覆蓋)

Period 格式：'20263' = FY2026 Q3（同 StatementDog）

執行：python fmp_updater.py
單一測試：python fmp_updater.py --ticker NVDA
強制全量：python fmp_updater.py --force
只跑 EDGAR：python fmp_updater.py --source edgar
"""
import argparse, math, os, sys, time
from datetime import date
from pathlib import Path

import openpyxl
import pandas as pd
import requests
from dotenv import load_dotenv
from supabase import create_client

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / "auto" / ".env", override=False)

FMP_KEY  = os.environ.get("FMP_API") or os.environ.get("FMP_KEY", "")
SUPA_URL = os.environ.get("SUPABASE_URL", "https://yxydsxygylpzewumevsz.supabase.co")
SUPA_KEY = os.environ.get("SUPABASE_KEY", "")
EDGAR_UA = "stock-fundamentals-tracker nuuai2025@gmail.com"

if not FMP_KEY:  sys.exit("[FAIL] 缺少 FMP_API")
if not SUPA_KEY: sys.exit("[FAIL] 缺少 SUPABASE_KEY")

sb = create_client(SUPA_URL, SUPA_KEY)

# FMP 免費版支援的標的（固定清單，同時作為 CI 無 Excel 時的路由依據）
FMP_SUPPORTED = {
    "NVDA","AAPL","MSFT","AMZN","GOOGL","META","TSLA",
    "WMT","AMD","INTC","CSCO","COST","NFLX","PLTR",
    "PEP","SHOP","SBUX","ADBE","PYPL",
}

# ══════════════════════════════════════════════════════════════════════
#  FMP 欄位對照
# ══════════════════════════════════════════════════════════════════════
FMP_BASE = "https://financialmodelingprep.com/stable"

FMP_INCOME = {
    "epsDiluted":                              "eps",
    "revenue":                                 "revenue",
    "grossProfit":                             "gross_profit",
    "operatingExpenses":                       "operating_expenses",
    "researchAndDevelopmentExpenses":          "rd_expenses",
    "sellingGeneralAndAdministrativeExpenses": "sga_expenses",
    "operatingIncome":                         "operating_income",
    "incomeBeforeTax":                         "profit_before_tax",
    "netIncome":                               "net_income",
    "depreciationAndAmortization":             "depreciation_amortization",
}
FMP_BALANCE = {
    "totalStockholdersEquity":    "equity",
    "commonStock":                "common_stocks",
    "retainedEarnings":           "retained_earnings",
    "totalAssets":                "assets",
    "totalCurrentAssets":         "current_assets",
    "cashAndCashEquivalents":     "cash_equivalents",
    "shortTermInvestments":       "short_term_investment",
    "netReceivables":             "accounts_receivable",
    "inventory":                  "inventories",
    "longTermInvestments":        "long_term_investment",
    "propertyPlantEquipmentNet":  "fixed_assets",
    "totalLiabilities":           "liabilities",
    "totalCurrentLiabilities":    "current_liabilities",
    "totalNonCurrentLiabilities": "long_term_liabilities",
    "accountPayables":            "accounts_payable",
    "deferredRevenue":            "advance_receipts",
    "shortTermDebt":              "short_term_borrowings",
}
FMP_CASHFLOW = {
    "operatingCashFlow":                        "operating_cash_flow",
    "netCashUsedForInvestingActivites":         "investing_cash_flow",
    "netCashUsedProvidedByFinancingActivities": "financing_cash_flow",
    "freeCashFlow":                             "free_cash_flow",
    "netChangeInCash":                          "net_cash_flow",
    "capitalExpenditure":                       "capex",
}

# ══════════════════════════════════════════════════════════════════════
#  EDGAR 概念對照
#  INSTANT = 資產負債表（無 start，取 10-Q Q1/Q2/Q3 + 10-K Q4）
#  DURATION= 損益/現金流（有 start，filter ~3個月區間）
# ══════════════════════════════════════════════════════════════════════
EDGAR_INSTANT = {
    "equity":                ["StockholdersEquity", "StockholdersEquityAttributableToParent"],
    "common_stocks":         ["CommonStockValue"],
    "retained_earnings":     ["RetainedEarningsAccumulatedDeficit"],
    "assets":                ["Assets"],
    "current_assets":        ["AssetsCurrent"],
    "cash_equivalents":      ["CashAndCashEquivalentsAtCarryingValue"],
    "short_term_investment":  ["ShortTermInvestments"],
    "accounts_receivable":   ["AccountsReceivableNetCurrent"],
    "inventories":           ["InventoryNet"],
    "long_term_investment":  ["LongTermInvestments"],
    "fixed_assets":          ["PropertyPlantAndEquipmentNet"],
    "liabilities":           ["Liabilities"],
    "current_liabilities":   ["LiabilitiesCurrent"],
    "long_term_liabilities": ["LiabilitiesNoncurrent"],
    "accounts_payable":      ["AccountsPayableCurrent"],
    "advance_receipts":      ["DeferredRevenueCurrent", "ContractWithCustomerLiabilityCurrent"],
    "short_term_borrowings": ["ShortTermBorrowings", "LongTermDebtCurrent"],
}
EDGAR_DURATION = {
    "revenue":              ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"],
    "gross_profit":         ["GrossProfit"],
    "operating_expenses":   ["OperatingExpenses"],
    "rd_expenses":          ["ResearchAndDevelopmentExpense"],
    "sga_expenses":         ["SellingGeneralAndAdministrativeExpense"],
    "operating_income":     ["OperatingIncomeLoss"],
    "profit_before_tax":    ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"],
    "net_income":           ["NetIncomeLoss"],
    "net_income_parent":    ["NetIncomeLossAttributableToParent", "NetIncomeLoss"],
    "depreciation_amortization": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization"],
    "operating_cash_flow":  ["NetCashProvidedByUsedInOperatingActivities"],
    "investing_cash_flow":  ["NetCashProvidedByUsedInInvestingActivities"],
    "financing_cash_flow":  ["NetCashProvidedByUsedInFinancingActivities"],
    "net_cash_flow":        ["CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect",
                             "CashAndCashEquivalentsPeriodIncreaseDecrease"],
    # ponytail: capex 從 EDGAR 取正值後取反，與 StatementDog 負號慣例一致
    "capex":                ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "eps":                  ["EarningsPerShareDiluted"],
    "_shares":              ["WeightedAverageNumberOfDilutedSharesOutstanding"],
}

# ══════════════════════════════════════════════════════════════════════
#  共用工具
# ══════════════════════════════════════════════════════════════════════
def _safe_div(a, b):
    try:
        return round(a / b, 6) if b else None
    except (TypeError, ZeroDivisionError):
        return None


def _compute_derived(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("period").reset_index(drop=True)

    if "eps" in df.columns:
        e = df["eps"]
        df["eps_ttm"]     = e.rolling(4).sum()
        df["eps_ttm_avg"] = e.rolling(4).mean()
        df["eps_qoq"]     = e.pct_change(1).round(6)
        df["eps_yoy"]     = e.pct_change(4).round(6)
        df["eps_ttm_qoq"] = df["eps_ttm"].pct_change(1).round(6)
        df["eps_ttm_yoy"] = df["eps_ttm"].pct_change(4).round(6)

    for num, den, col in [
        ("gross_profit",     "revenue", "gross_margin"),
        ("operating_income", "revenue", "operating_margin"),
        ("net_income",       "revenue", "net_income_margin"),
    ]:
        if num in df.columns and den in df.columns:
            df[col] = df.apply(lambda r: _safe_div(r.get(num), r.get(den)), axis=1)

    if "equity" in df.columns:
        if "_shares" in df.columns:
            df["nav"] = df.apply(lambda r: _safe_div(r.get("equity"), r.get("_shares")), axis=1)
        if "net_income" in df.columns:
            df["roe"]     = df.apply(lambda r: _safe_div(r.get("net_income"), r.get("equity")), axis=1)
            ni_ttm        = df["net_income"].rolling(4).sum()
            df["roe_ttm"] = [_safe_div(ni, eq) for ni, eq in zip(ni_ttm, df["equity"])]

    if "liabilities" in df.columns and "assets" in df.columns:
        df["debt_ratio"] = df.apply(lambda r: _safe_div(r.get("liabilities"), r.get("assets")), axis=1)

    if "current_assets" in df.columns and "current_liabilities" in df.columns:
        df["current_ratio"] = df.apply(
            lambda r: _safe_div(r.get("current_assets"), r.get("current_liabilities")), axis=1
        )
        if "inventories" in df.columns:
            df["quick_ratio"] = df.apply(
                lambda r: _safe_div(
                    (r.get("current_assets") or 0) - (r.get("inventories") or 0),
                    r.get("current_liabilities"),
                ), axis=1
            )

    # FCF：EDGAR 無直接欄位，由 OCF + capex 計算（capex 已存負值）
    if "free_cash_flow" not in df.columns and \
       "operating_cash_flow" in df.columns and "capex" in df.columns:
        df["free_cash_flow"] = df.apply(
            lambda r: (r.get("operating_cash_flow") or 0) + (r.get("capex") or 0), axis=1
        )

    for num, col in [
        ("operating_cash_flow", "operating_cash_flow_per_share"),
        ("free_cash_flow",      "free_cash_flow_per_share"),
    ]:
        if num in df.columns and "_shares" in df.columns:
            df[col] = df.apply(lambda r: _safe_div(r.get(num), r.get("_shares")), axis=1)

    if "net_income" in df.columns and "net_income_parent" not in df.columns:
        df["net_income_parent"] = df["net_income"]

    return df


def _upsert(rows: list[dict]) -> None:
    clean = [
        {k: (None if isinstance(v, float) and not math.isfinite(v) else v)
         for k, v in r.items() if not k.startswith("_")}
        for r in rows
    ]
    for i in range(0, len(clean), 50):
        sb.table("fundamentals").upsert(clean[i:i + 50], on_conflict="ticker,period").execute()


def _latest_period(ticker: str) -> str | None:
    res = (sb.table("fundamentals").select("period")
           .eq("ticker", ticker).order("period", desc=True).limit(1).execute())
    return res.data[0]["period"] if res.data else None


def _since_date(ticker: str) -> str:
    """DB 最後寫入時間（YYYY-MM-DD），用於比對 EDGAR 申報日期。"""
    res = (sb.table("fundamentals").select("updated_at")
           .eq("ticker", ticker).order("updated_at", desc=True).limit(1).execute())
    return res.data[0]["updated_at"][:10] if res.data else "2000-01-01"


def _has_new_10q(cik: str, since: str) -> bool:
    """輕量 submissions 檢查：since 之後是否有新 10-Q 申報。"""
    r = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json",
                     headers={"User-Agent": EDGAR_UA}, timeout=30)
    r.raise_for_status()
    recent = r.json().get("filings", {}).get("recent", {})
    for form, filed in zip(recent.get("form", []), recent.get("filingDate", [])):
        if form == "10-Q" and filed > since:
            return True
    return False


def _upload(ticker: str, df: pd.DataFrame, latest: str | None, force: bool) -> int:
    rows = df.to_dict(orient="records")
    if latest and not force:
        rows = [r for r in rows if str(r.get("period", "")) > latest]
    if not rows:
        print(f"  [OK]   {ticker} 已是最新（{latest}）")
        return 0
    periods = sorted(str(r["period"]) for r in rows)
    _upsert(rows)
    print(f"  [OK]   {ticker} 新增 {len(rows)} 季（{periods[0]}~{periods[-1]}）")
    return len(rows)


# ══════════════════════════════════════════════════════════════════════
#  FMP
# ══════════════════════════════════════════════════════════════════════
def _fmp_fetch(endpoint: str, symbol: str) -> list:
    r = requests.get(f"{FMP_BASE}/{endpoint}",
                     # ponytail: limit=5 是 FMP 免費版上限，增量更新已足夠
                     params={"symbol": symbol, "period": "quarter", "limit": 5, "apikey": FMP_KEY},
                     timeout=30)
    r.raise_for_status()
    d = r.json()
    return d if isinstance(d, list) else []


def update_via_fmp(ticker: str, cik_map: dict, force: bool = False) -> int:
    if not force:
        cik = cik_map.get(ticker)
        if cik:
            try:
                if not _has_new_10q(cik, _since_date(ticker)):
                    print(f"  [OK]   {ticker} 無新申報，跳過")
                    time.sleep(0.1)
                    return 0
            except Exception:
                pass  # submissions 失敗時繼續正常抓取
            time.sleep(0.15)

    latest = None if force else _latest_period(ticker)
    try:
        income   = _fmp_fetch("income-statement",       ticker); time.sleep(0.3)
        balance  = _fmp_fetch("balance-sheet-statement", ticker); time.sleep(0.3)
        cashflow = _fmp_fetch("cash-flow-statement",     ticker); time.sleep(0.3)
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 402:
            msg = "免費版不支援" if "symbol" in e.response.text.lower() else "402 超出限制"
            print(f"  [SKIP] {ticker} FMP {msg}")
        else:
            print(f"  [WARN] {ticker} FMP: {e}")
        return 0
    except Exception as e:
        print(f"  [WARN] {ticker} FMP: {e}")
        return 0

    merged: dict[str, dict] = {}
    for src, mapping in [(income, FMP_INCOME), (balance, FMP_BALANCE), (cashflow, FMP_CASHFLOW)]:
        for row in src:
            fy = str(row.get("fiscalYear", ""))
            p  = str(row.get("period", ""))
            if not fy or not p.startswith("Q"):
                continue
            pk = f"{fy}{p[1]}"
            m  = merged.setdefault(pk, {"ticker": ticker, "period": pk})
            for fc, dc in mapping.items():
                if row.get(fc) is not None:
                    m[dc] = row[fc]
            for sh in ("weightedAverageShsOutDil", "weightedAverageShsOut"):
                if row.get(sh):
                    m["_shares"] = row[sh]

    if not merged:
        print(f"  [SKIP] {ticker} FMP 無資料")
        return 0

    return _upload(ticker, _compute_derived(pd.DataFrame(list(merged.values()))), latest, force)


# ══════════════════════════════════════════════════════════════════════
#  EDGAR
# ══════════════════════════════════════════════════════════════════════
_cik_cache: dict[str, str] = {}


def _load_cik_map() -> dict[str, str]:
    global _cik_cache
    if _cik_cache:
        return _cik_cache
    r = requests.get("https://www.sec.gov/files/company_tickers.json",
                     headers={"User-Agent": EDGAR_UA}, timeout=30)
    r.raise_for_status()
    _cik_cache = {v["ticker"]: str(v["cik_str"]).zfill(10) for v in r.json().values()}
    return _cik_cache


def _edgar_get(facts: dict, concepts: list, instant: bool) -> dict[str, float]:
    """嘗試 concepts 清單，回傳第一個有季度資料的 {period_key: value}。"""
    for concept in concepts:
        if concept not in facts:
            continue
        for _, points in facts[concept].get("units", {}).items():
            result: dict[str, tuple] = {}
            for pt in points:
                form = pt.get("form", "")
                fp   = str(pt.get("fp", ""))
                fy   = pt.get("fy")
                if not fy:
                    continue
                if instant:
                    if form == "10-Q" and fp in ("Q1", "Q2", "Q3"):
                        pk = f"{fy}{fp[1]}"
                    elif form == "10-K" and fp == "FY":
                        pk = f"{fy}4"   # 年底資產負債表當作 Q4
                    else:
                        continue
                else:
                    if form != "10-Q" or "start" not in pt:
                        continue
                    try:
                        days = (date.fromisoformat(pt["end"]) - date.fromisoformat(pt["start"])).days
                    except ValueError:
                        continue
                    if not (75 <= days <= 105):   # ~3個月
                        continue
                    if fp not in ("Q1", "Q2", "Q3"):
                        continue
                    pk = f"{fy}{fp[1]}"
                filed = pt.get("filed", "")
                if pk not in result or filed > result[pk][1]:
                    result[pk] = (pt["val"], filed)
            if result:
                return {k: v[0] for k, v in result.items()}
    return {}


def update_via_edgar(ticker: str, cik_map: dict[str, str], force: bool = False) -> int:
    cik = cik_map.get(ticker)
    if not cik:
        print(f"  [SKIP] {ticker} EDGAR 無 CIK")
        return 0

    if not force:
        try:
            if not _has_new_10q(cik, _since_date(ticker)):
                print(f"  [OK]   {ticker} 無新申報，跳過")
                time.sleep(0.1)
                return 0
        except Exception:
            pass  # submissions 失敗時繼續正常抓取
        time.sleep(0.15)

    latest = None if force else _latest_period(ticker)
    try:
        r = requests.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
                         headers={"User-Agent": EDGAR_UA}, timeout=60)
        r.raise_for_status()
        facts = r.json().get("facts", {}).get("us-gaap", {})
        time.sleep(0.15)
    except Exception as e:
        print(f"  [WARN] {ticker} EDGAR: {e}")
        return 0

    if not facts:
        print(f"  [SKIP] {ticker} EDGAR 無 us-gaap 資料")
        return 0

    raw: dict[str, dict[str, float]] = {}
    all_periods: set[str] = set()

    for dc, concepts in EDGAR_INSTANT.items():
        data = _edgar_get(facts, concepts, instant=True)
        if data:
            raw[dc] = data
            all_periods.update(data)

    for dc, concepts in EDGAR_DURATION.items():
        data = _edgar_get(facts, concepts, instant=False)
        if data:
            if dc == "capex":
                data = {k: -abs(v) for k, v in data.items()}   # 轉負值與 StatementDog 一致
            raw[dc] = data
            all_periods.update(data)

    if not all_periods:
        print(f"  [SKIP] {ticker} EDGAR 無可用季度")
        return 0

    rows_dict = {pk: {"ticker": ticker, "period": pk} for pk in all_periods}
    for dc, pv in raw.items():
        for pk, val in pv.items():
            if pk in rows_dict:
                rows_dict[pk][dc] = val

    return _upload(ticker, _compute_derived(pd.DataFrame(list(rows_dict.values()))), latest, force)


# ══════════════════════════════════════════════════════════════════════
#  主流程
# ══════════════════════════════════════════════════════════════════════
def _load_tickers(excel_path: Path) -> tuple[list[str], list[str]]:
    """返回 (fmp_list, edgar_list)。
    本地有 Excel → 讀 A/C 欄；CI 無 Excel → 從 Supabase companies 表 + FMP_SUPPORTED 分流。
    """
    if excel_path.exists():
        wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
        ws = wb.active
        fmp, edgar = [], []
        for row in ws.iter_rows(min_row=2, values_only=True):
            ticker = str(row[0]).strip() if row[0] else None
            if not ticker or ticker == "None":
                continue
            c = row[2] if len(row) > 2 else None
            if c is True or str(c).strip().lower() == "true":
                fmp.append(ticker)
            else:
                edgar.append(ticker)
        wb.close()
        return fmp, edgar
    else:
        # CI fallback：Excel 不在 repo，從 Supabase 取 ticker 清單
        print("  [INFO] Excel 不存在，從 Supabase companies 表讀取 ticker")
        all_t = [r["ticker"] for r in sb.table("companies").select("ticker").execute().data]
        return (
            [t for t in all_t if t in FMP_SUPPORTED],
            [t for t in all_t if t not in FMP_SUPPORTED],
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force",  action="store_true", help="忽略 DB 現有資料，全量上傳")
    parser.add_argument("--ticker", help="只更新指定 ticker（測試用）")
    parser.add_argument("--source", choices=["fmp", "edgar", "auto"], default="auto")
    args = parser.parse_args()

    print("=" * 60)
    print("  混合策略季報增量更新  (FMP + EDGAR)")
    if args.force: print("  模式：全量 --force")
    print("=" * 60)

    fmp_list, edgar_list = _load_tickers(BASE_DIR / "前百大公司.xlsx")
    total = 0

    # CIK map 兩條路都需要（submissions 偵測用）
    cik_map = _load_cik_map()
    print(f"  CIK 對照表 {len(cik_map)} 筆")

    if args.ticker:
        t = args.ticker.upper()
        src = args.source
        if src == "auto":
            src = "fmp" if t in fmp_list else "edgar"
        print(f"\n[{src.upper()}] {t}")
        if src == "fmp":
            total += update_via_fmp(t, cik_map, force=args.force)
        else:
            total += update_via_edgar(t, cik_map, force=args.force)
    else:
        if args.source in ("fmp", "auto") and fmp_list:
            print(f"\n── FMP（{len(fmp_list)} 家）" + "─" * 35)
            for i, t in enumerate(fmp_list, 1):
                print(f"[{i:>2}/{len(fmp_list)}] {t}")
                total += update_via_fmp(t, cik_map, force=args.force)

        if args.source in ("edgar", "auto") and edgar_list:
            print(f"\n── EDGAR（{len(edgar_list)} 家）" + "─" * 33)
            for i, t in enumerate(edgar_list, 1):
                print(f"[{i:>2}/{len(edgar_list)}] {t}")
                total += update_via_edgar(t, cik_map, force=args.force)

    print(f"\n{'=' * 60}")
    print(f"  完成，共新增 {total} 筆")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()