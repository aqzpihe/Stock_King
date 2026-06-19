import requests
import json
import time
import pandas as pd

# ============================================================
# 步驟：F12 → Application → Cookies → statementdog.com
#       複製 _statementdog_session_v2 的值貼到下方
# ============================================================
SESSION_COOKIE = "721HhHAF%2BxiMeUCVKG7T1kajdWizn500vP5XjpGhmqfd%2FOYH90%2BH%2BOnloDkLeFrk3GotUMMb7MmZgKCNu5w6g55eoOv4UIyl3b%2B0k6X%2F78qoN8CjWse6TH4%2Bx1gWhRgTgaCw2ksSg1maBwBc6VpIeQLG%2FOSegJBnA%2F4%2Bkp3aVWqEmvgZwOTciZcX40VRbHCVJLyXjEQB8WknLbV%2FszRtUybB51fa0Si5%2BkxHNBWLgWBinhYB1Kx0wSSuF2JQJ6fuBMLbXs6j0eSlk%2FdAr58VnQ7KlmI5g8TwY90Tl8mZeXJgYeCA9Z%2B3%2Bgq0Ttrh%2FRjuLf%2FoND47l8PojUp6PsnoT6MbaydFwQQrnLSt%2B1BXQ8A9yYzImitumOYu3%2By0J%2FVAG21QA7T5dHqFSgAKOF3ziC%2F4BxnAL9ugL9V6X8NLpuqeMxYAiRxdqoYvSFAm7Y0rREqk%2BsaXzpUeMVb99HeCjU1FcMlAn2bxRwcWus7ewwP%2FURMAT%2FZYuCwLoz0CZWmb5D8AMKliyeVzE8OhAtAK9HT7HhLEqJ9T3hgBzw9a14%2FesrzSwum2lx2CYjYxvIjbRpx7Vw9X--SyxVnBlzYnhL9nhh--Z2ijxg8iVygy0mTWSLah8g%3D%3D"

# ============================================================

class StatementDogScraper:
    BASE_URL = "https://statementdog.com"
    API_BASE = "https://statementdog.com/api/v2/fundamentals"

    # 頁面對應的指標群組
    PAGE_KEYS = {
        "eps": [
            "EPS", "EPST4Q", "EPST4QAvg",
            "EPSQOQ", "EPSYOY", "EPST4QQOQ", "EPST4QYOY",
        ],
        "nav": [
            "NAV", "Equity", "CommonStocks", "RetainedEarnings",
            "ROE", "ROET4Q",
        ],
        "income-statement": [
            "Revenue", "GrossProfit", "OperatingExpenses",
            "ResearchAndDevelopmentExpenses", "SellingAndAdministrativeExpenses",
            "OperatingIncome", "ProfitBeforeTax", "NetIncome",
            "NetIncomeAttributableToOwnersOfTheParent",
            "GrossMargin", "OperatingMargin", "NetIncomeMargin",
        ],
        "assets": [
            "Assets", "CurrentAssets", "CashAndCashEquivalents",
            "ShortTermInvestment", "AccountsAndNotesReceivable",
            "Inventories", "LongTermInvestment", "FixedAssets",
        ],
        "liabilities-and-equity": [
            "Liabilities", "CurrentLiabilities", "LongTermLiabilities",
            "AccountsAndNotesPayable", "AdvanceReceipts",
            "ShortTermBorrowingsAndLongTermLiabilitiesCurrentPortion",
            "Equity", "CommonStocks", "RetainedEarnings",
            "DebtRatio", "CurrentRatio", "QuickRatio",
        ],
        "cash-flow-statement": [
            "OperatingCashFlow", "InvestingCashFlow", "FinancingCashFlow",
            "FreeCashFlow", "NetCashFlow", "CAPEX",
            "DepreciationAndAmortization",
            "OperatingCashFlowPerShare", "FreeCashFlowPerShare",
        ],
    }

    def __init__(self, session_cookie: str):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept":          "application/json, text/plain, */*",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        })
        # 設定登入 Cookie
        self.session.cookies.set(
            "_statementdog_session_v2",
            session_cookie,
            domain="statementdog.com",
        )
        # 驗證是否成功登入
        resp = self.session.get(f"{self.BASE_URL}/")
        if '"is_signed_in":true' in resp.text:
            print("[初始化] 登入成功 ✓")
        else:
            print("[初始化] ⚠️  Cookie 無效或已過期，請重新從 F12 複製")

    # ── 抓取財報 ─────────────────────────────────────────────
    def fetch(
        self,
        ticker:     str,
        start_year: int = 2020,
        end_year:   int = 2026,
        stmt_type:  str = "cf",
        delay:      float = 1.5,
    ) -> dict:
        analysis_url = f"{self.BASE_URL}/analysis/{ticker}"
        self.session.get(analysis_url)
        time.sleep(delay)

        url = (
            f"{self.API_BASE}/{ticker}"
            f"/{start_year}/{end_year}/{stmt_type}"
            f"?qbu=true&qf=analysis"
        )
        resp = self.session.get(url, headers={"Referer": analysis_url}, timeout=15)
        data = resp.json()

        if "error" in data:
            raise RuntimeError(f"API 錯誤: {data['error']}")

        q_count = len(data.get("quarterly", {}))
        m_count = len(data.get("monthly", {}))
        print(f"[{ticker}] 季度: {q_count} 月度: {m_count}")
        return data

    # ── 轉成 DataFrame ───────────────────────────────────────
    @staticmethod
    def to_df(data: dict, keys: list = None) -> pd.DataFrame:
        """
        將 quarterly 資料轉成 DataFrame
        時間軸使用 TimeFiscalQ（會計季度，如 "20211"）
        """
        # 建立時間對應
        time_map = {
            item[0]: item[1]
            for item in data.get("common", {})
                            .get("TimeFiscalQ", {})
                            .get("data", [])
        }

        quarterly = data.get("quarterly", {})
        records = {}

        for key, info in quarterly.items():
            if keys and key not in keys:
                continue
            for idx, val in info.get("data", []):
                period = time_map.get(idx, str(idx))
                records.setdefault(period, {})[key] = val

        df = pd.DataFrame.from_dict(records, orient="index").sort_index()
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df

    # ── 依頁面名稱取得對應 DataFrame ────────────────────────
    def get_page_df(self, data: dict, page: str) -> pd.DataFrame:
        """
        page: eps / nav / income-statement /
              assets / liabilities-and-equity / cash-flow-statement
        """
        keys = self.PAGE_KEYS.get(page, [])
        df   = self.to_df(data, keys)
        # 只保留實際存在的欄位
        exist = [k for k in keys if k in df.columns]
        return df[exist] if exist else df

    # ── 存成 Excel ───────────────────────────────────────────
    def save_excel(self, data: dict, ticker: str, start: int, end: int):
        filename = f"{ticker}_財報_{start}_{end}.xlsx"
        with pd.ExcelWriter(filename, engine="openpyxl") as writer:
            for page in self.PAGE_KEYS:
                df = self.get_page_df(data, page)
                if not df.empty:
                    df.to_excel(writer, sheet_name=page)
                    print(f"  [{page}] {df.shape[0]} 季 × {df.shape[1]} 指標")
            # 股票資訊
            info = data.get("common", {}).get("StockInfo", {}).get("data", {})
            pd.DataFrame([info]).T.to_excel(writer, sheet_name="StockInfo")
        print(f"\n✓ 已儲存：{filename}")
        return filename


# ============================================================
# 主程式
# ============================================================
if __name__ == "__main__":
    scraper = StatementDogScraper(SESSION_COOKIE)

    TICKER     = "WMT"
    START_YEAR = 2016
    END_YEAR   = 2026

    # 抓取資料
    data = scraper.fetch(TICKER, START_YEAR, END_YEAR)

    # 顯示各頁面資料
    for page in scraper.PAGE_KEYS:
        df = scraper.get_page_df(data, page)
        print(f"\n── {page} ──")
        print(df.tail(4).to_string())

    # 存 Excel
    scraper.save_excel(data, TICKER, START_YEAR, END_YEAR)

    # 存 JSON 備份
    with open(f"{TICKER}_raw.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✓ 已儲存：{TICKER}_raw.json")

