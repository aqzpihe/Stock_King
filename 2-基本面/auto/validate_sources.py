#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
驗證 PDF 圖表宣稱的「各資料來源對 51 指標覆蓋狀態」是否屬實。
測試標的: MSFT
來源: SEC EDGAR (免金鑰) + FMP / Finnhub / Alpha Vantage (免費金鑰, 從環境變數讀)

覆蓋判定:
  2 = 直接取值 (API 該欄位有直接數值)
  1 = 需計算   (原始數據存在, 但該衍生指標本身不直接回傳)
  0 = 無資料   (連計算所需原始欄位都拿不到)

金鑰用環境變數:
  export FMP_KEY=xxx
  export FINNHUB_KEY=xxx
  export AV_KEY=xxx
缺金鑰的來源會自動跳過 (標記 SKIPPED, 不影響其他來源)。
"""
import os, sys, time, json, requests
from collections import OrderedDict

TICKER = "MSFT"
CIK = "0000789019"   # Microsoft CIK (zero-padded to 10)
UA = {"User-Agent": "coverage-validator research@example.com"}

FMP_KEY     = os.getenv("FMP_KEY", "")
FINNHUB_KEY = os.getenv("FINNHUB_KEY", "")
AV_KEY      = os.getenv("AV_KEY", "")

# ------------------------------------------------------------------
# PDF 圖表宣稱的覆蓋狀態 (2=直接, 1=需計算, 0=無資料)
# 欄位順序: EDGAR, edgartools, FMP, AlphaVantage, Finnhub, EODHD
# 空白格在原表代表「需計算」(1); 我把每格依 PDF 標示填入。
# 本腳本只驗證有金鑰/免金鑰的來源: EDGAR, FMP, AlphaVantage, Finnhub
# edgartools = EDGAR 同源(視為等同), EODHD 付費不驗。
# ------------------------------------------------------------------
# claim[indicator] = {"EDGAR":x,"FMP":x,"AV":x,"Finnhub":x}
CLAIM = OrderedDict()
def C(name, xbrl, edgar, fmp, av, finnhub):
    CLAIM[name] = {"xbrl": xbrl, "EDGAR": edgar, "FMP": fmp, "AV": av, "Finnhub": finnhub}

# EPS 區塊
C("eps","EarningsPerShareDiluted",1,2,2,2)
C("eps_ttm","sum(EPS,4Q)",1,2,1,2)
C("eps_ttm_avg","mean(EPS,4Q)",1,1,0,1)
C("eps_qoq","(Q-Q1)/Q1",1,2,0,1)
C("eps_yoy","(Q-Q4)/Q4",1,2,0,1)
C("eps_ttm_qoq","TTM QoQ",1,1,0,0)
C("eps_ttm_yoy","TTM YoY",1,1,0,0)
# NAV / 權益
C("nav","Equity/Shares",1,2,0,2)
C("equity","StockholdersEquity",2,2,2,2)
C("common_stocks","CommonStockValue",2,2,1,1)
C("retained_earnings","RetainedEarningsAccumulatedDeficit",2,2,1,1)
C("roe","NetIncome/Equity",1,2,2,2)
C("roe_ttm","NetIncome_TTM/Equity",1,2,0,1)
# 損益表
C("revenue","RevenueFromContractWithCustomer",2,2,2,2)
C("gross_profit","GrossProfit",2,2,2,2)
C("operating_expenses","OperatingExpenses",2,2,1,2)
C("rd_expenses","ResearchAndDevelopmentExpense",2,2,2,2)
C("sga_expenses","SellingGeneralAndAdministrativeExpense",2,2,2,2)
C("operating_income","OperatingIncomeLoss",2,2,2,2)
C("profit_before_tax","IncomeLossBeforeIncomeTaxes",2,2,2,2)
C("net_income","NetIncomeLoss",2,2,2,2)
C("net_income_parent","NetIncomeLossAttributableToParent",2,2,1,1)
C("gross_margin","GrossProfit/Revenue",1,2,2,2)
C("operating_margin","OperatingIncome/Revenue",1,2,2,2)
C("net_income_margin","NetIncome/Revenue",1,2,2,2)
# 資產
C("assets","Assets",2,2,2,2)
C("current_assets","AssetsCurrent",2,2,2,2)
C("cash_equivalents","CashAndCashEquivalentsAtCarryingValue",2,2,2,2)
C("short_term_investment","ShortTermInvestments",2,2,1,1)
C("accounts_receivable","AccountsReceivableNetCurrent",2,2,2,2)
C("inventories","InventoryNet",2,2,2,2)
C("long_term_investment","LongTermInvestments",2,1,0,1)
C("fixed_assets","PropertyPlantAndEquipmentNet",2,2,2,2)
# 負債
C("liabilities","Liabilities",2,2,2,2)
C("current_liabilities","LiabilitiesCurrent",2,2,2,2)
C("long_term_liabilities","LiabilitiesNoncurrent",2,2,1,2)
C("accounts_payable","AccountsPayableCurrent",2,2,2,2)
C("advance_receipts","DeferredRevenueCurrent",2,1,0,1)
C("short_term_borrowings","ShortTermBorrowings+LTDebtCurrent",2,2,1,2)
C("debt_ratio","Liabilities/Assets",1,2,1,2)
C("current_ratio","AssetsCurrent/LiabilitiesCurrent",1,2,2,2)
C("quick_ratio","(Current-Inventory)/CurrentLiab",1,2,2,2)
# 現金流量
C("operating_cash_flow","NetCashFromOperating",2,2,2,2)
C("investing_cash_flow","NetCashFromInvesting",2,2,2,2)
C("financing_cash_flow","NetCashFromFinancing",2,2,2,2)
C("free_cash_flow","OCF+Capex",1,2,2,2)
C("net_cash_flow","CashPeriodIncreaseDecrease",2,2,1,2)
C("capex","PaymentsToAcquirePPE",2,2,2,2)
C("depreciation_amortization","DepreciationDepletionAndAmortization",2,2,2,2)
C("operating_cash_flow_per_share","OCF/Shares",1,2,0,2)
C("free_cash_flow_per_share","FCF/Shares",1,2,0,1)

assert len(CLAIM) == 51, f"指標數應為51, 實際 {len(CLAIM)}"

# ------------------------------------------------------------------
# 對應表: 各來源「直接欄位名稱」。值為 list 代表任一命中即算直接取值。
# 若指標在某來源屬衍生指標, 用 ("CALC", [需要的原始欄位...]) 表示。
# ------------------------------------------------------------------
def direct(*names): return ("DIRECT", list(names))
def calc(*deps):    return ("CALC", list(deps))

# FMP 用 statement 的 key 名
FMP_MAP = {
 "eps":direct("epsdiluted","eps"), "eps_ttm":calc("eps"), "eps_ttm_avg":calc("eps"),
 "eps_qoq":calc("eps"), "eps_yoy":calc("eps"), "eps_ttm_qoq":calc("eps"), "eps_ttm_yoy":calc("eps"),
 "nav":calc("totalStockholdersEquity","weightedAverageShsOut"),
 "equity":direct("totalStockholdersEquity"),
 "common_stocks":direct("commonStock"),
 "retained_earnings":direct("retainedEarnings"),
 "roe":calc("netIncome","totalStockholdersEquity"),
 "roe_ttm":calc("netIncome","totalStockholdersEquity"),
 "revenue":direct("revenue"), "gross_profit":direct("grossProfit"),
 "operating_expenses":direct("operatingExpenses"),
 "rd_expenses":direct("researchAndDevelopmentExpenses"),
 "sga_expenses":direct("sellingGeneralAndAdministrativeExpenses","generalAndAdministrativeExpenses"),
 "operating_income":direct("operatingIncome"),
 "profit_before_tax":direct("incomeBeforeTax"),
 "net_income":direct("netIncome"),
 "net_income_parent":direct("netIncome"),
 "gross_margin":calc("grossProfit","revenue"),
 "operating_margin":calc("operatingIncome","revenue"),
 "net_income_margin":calc("netIncome","revenue"),
 "assets":direct("totalAssets"), "current_assets":direct("totalCurrentAssets"),
 "cash_equivalents":direct("cashAndCashEquivalents"),
 "short_term_investment":direct("shortTermInvestments"),
 "accounts_receivable":direct("netReceivables"),
 "inventories":direct("inventory"),
 "long_term_investment":direct("longTermInvestments"),
 "fixed_assets":direct("propertyPlantEquipmentNet"),
 "liabilities":direct("totalLiabilities"),
 "current_liabilities":direct("totalCurrentLiabilities"),
 "long_term_liabilities":direct("totalNonCurrentLiabilities"),
 "accounts_payable":direct("accountPayables"),
 "advance_receipts":direct("deferredRevenue"),
 "short_term_borrowings":direct("shortTermDebt"),
 "debt_ratio":calc("totalLiabilities","totalAssets"),
 "current_ratio":calc("totalCurrentAssets","totalCurrentLiabilities"),
 "quick_ratio":calc("totalCurrentAssets","inventory","totalCurrentLiabilities"),
 "operating_cash_flow":direct("operatingCashFlow","netCashProvidedByOperatingActivities"),
 "investing_cash_flow":direct("netCashUsedForInvestingActivites","netCashProvidedByInvestingActivities"),
 "financing_cash_flow":direct("netCashUsedProvidedByFinancingActivities"),
 "free_cash_flow":direct("freeCashFlow"),
 "net_cash_flow":direct("netChangeInCash"),
 "capex":direct("capitalExpenditure"),
 "depreciation_amortization":direct("depreciationAndAmortization"),
 "operating_cash_flow_per_share":calc("operatingCashFlow","weightedAverageShsOut"),
 "free_cash_flow_per_share":calc("freeCashFlow","weightedAverageShsOut"),
}

# ------------------------------------------------------------------
# 抓取各來源原始資料
# ------------------------------------------------------------------
def get_fmp():
    """回傳 dict: 最新一期合併的所有欄位 (income+balance+cashflow+ratios)"""
    if not FMP_KEY: return None
    base="https://financialmodelingprep.com/stable"
    merged={}
    for stmt in ["income-statement","balance-sheet-statement","cash-flow-statement"]:
        try:
            r=requests.get(f"{base}/{stmt}",
                           params={"symbol":TICKER,"period":"quarter","limit":5,"apikey":FMP_KEY},timeout=30)
            data=r.json()
            if isinstance(data,list) and data:
                # 收集所有 key (用最新一期; 多期供成長率判定)
                for k,v in data[0].items():
                    merged.setdefault(k,v)
                merged["__history__"]=merged.get("__history__",{})
                merged["__history__"][stmt]=data
        except Exception as e:
            print(f"  [FMP] {stmt} error: {e}")
        time.sleep(0.3)
    return merged if merged else None

def get_edgar():
    """SEC companyfacts: 回傳所有可用的 us-gaap concept 名稱集合"""
    url=f"https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK}.json"
    try:
        r=requests.get(url,headers=UA,timeout=60)
        facts=r.json().get("facts",{}).get("us-gaap",{})
        return set(facts.keys())
    except Exception as e:
        print(f"  [EDGAR] error: {e}")
        return None

def get_finnhub():
    if not FINNHUB_KEY: return None
    url="https://finnhub.io/api/v1/stock/metric"
    try:
        r=requests.get(url,params={"symbol":TICKER,"metric":"all","token":FINNHUB_KEY},timeout=30)
        m=r.json().get("metric",{})
        # finnhub basic financials: 我們收集 metric keys; 另外抓 financials-reported 看原始
        return {"metrics":set(m.keys()), "raw":m}
    except Exception as e:
        print(f"  [Finnhub] error: {e}")
        return None

def get_av():
    if not AV_KEY: return None
    base="https://www.alphavantage.co/query"
    out={}
    for fn in ["INCOME_STATEMENT","BALANCE_SHEET","CASH_FLOW"]:
        try:
            r=requests.get(base,params={"function":fn,"symbol":TICKER,"apikey":AV_KEY},timeout=30)
            j=r.json()
            rep=j.get("quarterlyReports") or j.get("annualReports")
            if rep: out[fn]=rep[0]
        except Exception as e:
            print(f"  [AV] {fn} error: {e}")
        time.sleep(13)  # AV 免費 5 req/min
    return out if out else None

# ------------------------------------------------------------------
# 各來源判定函式: 回傳 0/1/2 或 None(skip)
# ------------------------------------------------------------------
def judge_edgar(name, edgar_concepts):
    if edgar_concepts is None: return None
    xbrl=CLAIM[name]["xbrl"]
    # 取 XBRL 公式裡的 concept 名 (簡易: 抓駝峰字, 多 concept 用 + 連)
    import re
    tokens=re.findall(r"[A-Z][A-Za-z]+", xbrl)
    # 衍生指標 (公式含 / 或 sum/mean/TTM) -> 需計算
    is_derived = any(s in xbrl for s in ["/","sum","mean","TTM","QoQ","YoY","+","("]) and not xbrl[0].isupper() or \
                 any(s in xbrl for s in ["/","sum(","mean(","TTM","QoQ","YoY"])
    # 判定: 主要 concept 是否存在
    primary=[t for t in tokens if len(t)>4]
    hit=any(t in edgar_concepts for t in primary)
    if any(s in xbrl for s in ["/","sum","mean","QoQ","YoY","TTM"]):
        # 衍生: 看原始 concept 在不在 -> 在=需計算(1), 不在=無(0)
        return 1 if hit else 0
    return 2 if hit else (1 if primary else 0)

def judge_fmp(name, fmp_data):
    if fmp_data is None: return None
    spec=FMP_MAP.get(name)
    if spec is None: return 0
    kind,keys=spec
    present=lambda k: (k in fmp_data and fmp_data[k] not in (None,"",0)) or \
                      (k in fmp_data)  # key 存在即視為提供 (值可能合法為0)
    if kind=="DIRECT":
        return 2 if any(present(k) for k in keys) else 0
    else: # CALC
        return 1 if all(present(k) for k in keys) else 0

def judge_av(name, av_data):
    if av_data is None: return None
    # AV 欄位名是 PascalCase XBRL-like; 用 claim 的 AV 值作參照 + 實測欄位存在性
    flat={}
    for sec in av_data.values():
        if isinstance(sec,dict): flat.update(sec)
    xbrl=CLAIM[name]["xbrl"]
    import re
    tokens=re.findall(r"[A-Z][A-Za-z]+", xbrl)
    hit=any(t in flat and flat[t] not in (None,"None","") for t in tokens)
    if any(s in xbrl for s in ["/","sum","mean","QoQ","YoY","TTM","+"]):
        return 1 if hit else 0
    return 2 if hit else 0

def judge_finnhub(name, fh):
    if fh is None: return None
    # Finnhub basic financials 提供大量 ratio/per-share; income/balance 原始較少
    # 用 claim 值做合理性比對的同時, 嘗試從 metric keys 命中
    raw=fh["raw"]
    # 簡易命中: 指標名關鍵字 vs finnhub metric key
    key_hits={
        "roe":"roe", "roe_ttm":"roeTTM", "gross_margin":"grossMargin",
        "operating_margin":"operatingMargin", "net_income_margin":"netProfitMargin",
        "current_ratio":"currentRatio", "quick_ratio":"quickRatio",
        "debt_ratio":"totalDebt/totalEquity", "eps":"epsTTM",
        "nav":"bookValuePerShare", "free_cash_flow_per_share":"cashFlowPerShareTTM",
    }
    if name in key_hits:
        k=key_hits[name]
        if any(k.lower() in mk.lower() for mk in raw):
            return 2
    # 否則回傳 claim 推定 (Finnhub 原始報表需另一 endpoint, 此處標記為需計算/無)
    return None  # 標記為「未實測」, 避免誤判

# ------------------------------------------------------------------
# 主流程
# ------------------------------------------------------------------
def main():
    print("="*60)
    print(f"驗證標的: {TICKER}  |  比對 PDF 圖表覆蓋宣稱")
    print("="*60)
    print("抓取資料來源中...")

    print(" - SEC EDGAR (免金鑰)...")
    edgar=get_edgar()
    print(f"   {'OK, concepts='+str(len(edgar)) if edgar else 'FAILED'}")

    fmp=None
    if FMP_KEY:
        print(" - FMP..."); fmp=get_fmp()
        print(f"   {'OK, fields='+str(len([k for k in fmp if not k.startswith('__')])) if fmp else 'FAILED'}")
    else:
        print(" - FMP: SKIPPED (no FMP_KEY)")

    fh=None
    if FINNHUB_KEY:
        print(" - Finnhub..."); fh=get_finnhub()
    else:
        print(" - Finnhub: SKIPPED (no FINNHUB_KEY)")

    av=None
    if AV_KEY:
        print(" - Alpha Vantage (慢, 每13秒一次)..."); av=get_av()
    else:
        print(" - Alpha Vantage: SKIPPED (no AV_KEY)")

    # 逐指標判定
    rows=[]
    src_funcs={"EDGAR":(judge_edgar,edgar),"FMP":(judge_fmp,fmp),
               "AV":(judge_av,av),"Finnhub":(judge_finnhub,fh)}
    label={2:"✅直接",1:"需計算",0:"❌無資料",None:"—未測"}

    summary={s:{"match":0,"mismatch":0,"untested":0} for s in src_funcs}

    for name,info in CLAIM.items():
        row={"indicator":name,"xbrl":info["xbrl"]}
        for s,(fn,data) in src_funcs.items():
            actual=fn(name,data)
            claimed=info[s]
            row[f"{s}_claim"]=label[claimed]
            if actual is None:
                row[f"{s}_actual"]="—未測"
                row[f"{s}_verdict"]="SKIP"
                summary[s]["untested"]+=1
            else:
                row[f"{s}_actual"]=label[actual]
                ok = (actual==claimed)
                row[f"{s}_verdict"]="MATCH" if ok else "MISMATCH"
                summary[s]["match" if ok else "mismatch"]+=1
        rows.append(row)

    # 輸出 Excel
    import pandas as pd
    df=pd.DataFrame(rows)
    out=os.path.join(os.path.dirname(os.path.abspath(__file__)), "coverage_validation_MSFT.xlsx")
    with pd.ExcelWriter(out,engine="openpyxl") as w:
        df.to_excel(w,sheet_name="驗證矩陣",index=False)
        sm=pd.DataFrame([{"來源":s,"相符":d["match"],"不符":d["mismatch"],"未測":d["untested"]}
                         for s,d in summary.items()])
        sm.to_excel(w,sheet_name="總結",index=False)

    print("\n"+"="*60)
    print("驗證總結 (相符 / 不符 / 未測):")
    for s,d in summary.items():
        tested=d["match"]+d["mismatch"]
        rate=f"{100*d['match']/tested:.0f}%" if tested else "N/A"
        print(f"  {s:8s}: 相符{d['match']:2d} 不符{d['mismatch']:2d} 未測{d['untested']:2d}  (相符率 {rate})")
    print(f"\nExcel 已輸出: {out}")
    return out

if __name__=="__main__":
    main()
