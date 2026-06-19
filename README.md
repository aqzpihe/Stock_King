# Stock King 投資分析平台

**Stock King** 是一個模組化的投資分析與決策支援平台。目前主要完成 **M1 大環境（宏觀經濟）模組**的開發，旨在透過多維度的經濟數據、貨幣政策與市場預期，量化目前的總體經濟環境，並產出易於解讀的環境評分（Score），輔助投資決策。
網頁:https://aqzpihe.github.io/Stock_King/index.html
---

## 🌟 核心模組與功能

### M1 大環境 / 國家經濟模組
本模組匯集了來自 FRED、Kaggle (FOMC SEP)、Polymarket 等多方數據，計算出 4 個維度的子指標，並匯總為整體的「宏觀大環境分數」。

1. **信用條件 (Credit Conditions)**
   - 評估市場流動性與企業借貸壓力。
2. **貨幣政策現況 (Monetary Policy)**
   - 衡量當前聯邦基金利率（FFR）等政策現狀。
3. **通膨 & 匯率穩定 (Inflation & FX)**
   - 監控物價水準變化與強勢貨幣風險。
4. **綜合政策預期 (Policy Forward Score)**
   - **70% FOMC 點陣圖 (Dot Plot)**：衡量聯準會官員對未來 1~2 年及長期的利率路徑預測（相較於中性利率與現價的差距）。
   - **30% Polymarket 預測市場**：透過真金白銀的預測市場，捕捉對下次 FOMC 會議升降息的即時機率。
   - 輸出範圍：`[-2, +2]`（轉換至 0-100 制），正值代表寬鬆預期，負值代表緊縮預期。

### 📊 前端視覺化 Dashboard
- 提供現代化、響應式的 Web 介面。
- **互動式圖表**：支援時間區間切換（1M, 3M, 1Y, ALL, 自訂）、多指數對比、十字準星對齊（Crosshair Hover）。
- **包含多種圖表**：
  - **大環境分數 vs 美股指數**：觀察宏觀分數與 S&P 500、NASDAQ 等指數的連動。
  - **子指標分數走勢**：拆解宏觀分數的組成變化。
  - **FOMC 點陣圖 vs 政策預期**：直觀比對聯準會利率預測路徑與本系統算出的政策預期分數。

---

## 📂 目錄結構

```text
stock/
│
├── index.html                   # 平台主進入點 (首頁)
│
├── 1-大環境/                    # M1 大環境模組 (後端 ETL 與資料處理)
│   ├── dashboard.html           # 大環境專屬儀表板介面
│   ├── dashboard_data.json      # 前端圖表讀取的最終資料檔 (由 Python 生成)
│   ├── .env                     # API Keys 設定檔 (需自行建立)
│   │
│   ├── FRED.py                  # FRED API 資料抓取腳本
│   ├── indices_fetch.py         # 股市指數資料抓取腳本
│   ├── sep_data_fetcher.py      # Kaggle FOMC Dot Plot 與 FRED DFF 下載與整合
│   ├── polymarket_fed.py        # Polymarket 降息預期機率抓取腳本
│   │
│   ├── macro_feature_engineer.py# 宏觀特徵工程處理
│   ├── macro_scorer.py          # 指標標準化與評分計算邏輯
│   ├── policy_forward_score.py  # 第 4 個子模組：計算綜合政策預期分數
│   │
│   └── export_dashboard_data.py # 核心整合腳本：執行所有評分並輸出 dashboard_data.json
│
└── README.md                    # 本說明文件
```

---

## ⚙️ 環境設定與安裝

### 1. 系統需求
- Python 3.8+
- 現代瀏覽器（Chrome, Edge, Firefox 等）

### 2. 安裝 Python 套件
請確保安裝以下主要套件：
```bash
pip install pandas numpy requests openpyxl python-dotenv kaggle
```

### 3. API 金鑰設定 (Environment Variables)
在 `1-大環境/` 目錄下建立 `.env` 檔案，並填入以下資訊：
```env
FRED_API_KEY=你的_FRED_API_KEY
KAGGLE_USERNAME=你的_KAGGLE_帳號
KAGGLE_KEY=你的_KAGGLE_API_金鑰
```
*(註：Polymarket 資料透過 Gamma API 抓取，目前不需額外申請 Key)*

---

## 🚀 資料更新與執行流程 (ETL Pipeline)

要更新 Dashboard 上的資料，請依序執行以下步驟（建議在 `1-大環境/` 目錄下執行）：

1. **更新基礎宏觀資料與指數**
   ```bash
   python FRED.py
   python indices_fetch.py
   ```
2. **更新政策預期相關資料**
   ```bash
   python polymarket_fed.py
   python sep_data_fetcher.py
   python policy_forward_score.py
   ```
3. **整合並匯出前端 JSON**
   ```bash
   python export_dashboard_data.py
   ```
   *執行完畢後，將會在同目錄生成更新後的 `dashboard_data.json`。*

*(未來可將上述指令整合至單一 Shell 腳本，或設定 GitHub Actions 進行每日排程自動更新。)*

---

## 🌐 開啟與使用網頁

由於使用純靜態檔案與本地 JSON 讀取，為了避免瀏覽器 CORS 跨源讀取限制，建議透過本地伺服器開啟網頁：

1. 在 `stock/` 根目錄下啟動 Python 內建伺服器：
   ```bash
   python -m http.server 8000
   ```
2. 打開瀏覽器，前往：
   - 平台首頁：`http://localhost:8000/index.html`
   - 大環境 Dashboard：`http://localhost:8000/1-大環境/dashboard.html`

---

## 🗺️ 未來開發藍圖 (Roadmap)
- **M2 模組**：基本面分析 (Company Fundamentals)
- **M3 模組**：技術指標 (Technical Analysis)
- **M4/M5 模組**：籌碼面與情緒面分析
- 完善 `index.html` 總表，實現各模組間的分數聯動與策略回測功能。
