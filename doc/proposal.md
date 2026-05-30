# Stock King — Macro-Regime Trading Assistant V2 Proposal

> 最後更新：2026-05-18  
> 版本：V2（Phase 1 & Phase 2 已完成，Phase 3 前端展示進行中）

---

## 1. 專案簡介

**Stock King** 是一個模組化投資分析與決策支援平台。其首要模組「**M1 大環境**」作為「大環境宏觀輔助交易系統」，將複雜的總體經濟與金融市場資訊轉換為結構化的 Regime、分數與燈號，協助交易者判斷：

- 現在的市場是否適合加大 / 降低風險曝險
- 哪些策略類型在當前 Regime 中更適合啟用或暫停

系統以主流宏觀經濟與金融理論為基礎（Bernanke 外部融資溢酬、Lucas 預期理論、創造性破壞等），搭配 FRED API、FOMC 點陣圖、Polymarket 預測市場、TIC 國際資本數據等公開來源，建構可量化、可回測、可視覺化的大環境評分框架。

---

## 2. 平台模組總覽

Stock King 平台規劃 **5 大功能模組**，目前僅 M1 已實作，其餘模組保留介面佔位：

| 模組 | 名稱 | 狀態 | 說明 |
|------|------|------|------|
| **M1** | 📊 大環境 | ✅ 已實作 | 宏觀經濟環境評分與 Regime 判定 |
| M2 | 📈 基本面 | 🔜 規劃中 | 財務健康度評分、財報比對 |
| M3 | 📉 技術指標 | 🔜 規劃中 | RSI、MACD、布林通道等技術信號 |
| M4 | 🎯 交易策略 | 🔜 規劃中 | 買入點建議、止損位與部位管理 |
| M5 | 🤖 AI 決策 | 🔜 規劃中 | 綜合所有模組輸出的 AI 投資建議 |

---

## 3. M1 大環境 — 主要目標

1. **將大環境狀態量化為少數關鍵分數與 Regime**
   - 建立四大面向的環境分數，加權聚合為單一 Macro Score。
   - 額外建構「政策預期與可信度」指標（基於點陣圖與市場預期）。

2. **避免常見量化陷阱**
   - 嚴格使用 real-time / vintage 資料，避免未來函數（Look-ahead bias）。
   - 使用 EWMA 替代固定窗口標準化，處理參數漂移（Parameter drift）。

3. **提供清晰的儀表板**
   - 讓使用者在 5–10 秒內回答：「現在是要押風險、保持中立，還是防守為主？」

4. **作為上層模組供下游策略引用**
   - 預留介面讓其他交易策略引用 Score 做部位上限調整、策略啟停、權重切換。

---

## 4. 四大宏觀面向

### 面向一：信用市場與金融中介健康度（佔 Macro Score 30%）

- **核心目標**：觀察市場流動性壓力、企業融資成本與銀行體系的資產品質。
- **監測指標**：CPN3M、DTB6、DPRIME、DBAA、DGS10、DRBLACBS
- **合成指標**：CREDIT_SPREAD（DBAA − DGS10）、MORTGAGE_SPREAD（MORTGAGE30US − DGS10）

### 面向二：政策預期與體制可信度（佔 Macro Score 30%）

- **核心目標**：追蹤 Fed 政策路徑、縮表進度與市場對未來的定價。
- **監測指標**：DFF、WALCL、WTREGEN、RRPONTSYD、T10Y2Y、DGS2、DGS30、MORTGAGE30US
- **合成指標**：NET_LIQUIDITY（WALCL − WTREGEN − RRPONTSYD）、NET_LIQ_CHG
- **額外輸出**：
  - SEP 點陣圖預期（SEP_FFR_CURRENT / 1Y / 2Y / Long）
  - Polymarket 市場定價（POLYMARKET_RATE）
  - **Credibility %**（央行 vs 市場預期的吻合度）

### 面向三：國家經濟動能（佔 Macro Score 25%）

- **核心目標**：評估通膨、就業、生產力與消費者信心。
- **通膨指標**：CPIAUCSL、PCE、PPIACO
- **就業/生產**：UNRATE、PAYEMS、ICSA、JTSJOL、JTSQUR、INDPRO、GDP
- **情緒指標**：UMCSENT、BABATOTALSAUS

### 面向四：國際資本傳導與匯率環境（佔 Macro Score 15%）

- **核心目標**：追蹤美元強弱、跨境資金流向與外資對美債的偏好。
- **匯率指標**：DTWEXBGS、EMVEXRATES、BOPBCA
- **TIC 數據**：TIC_GRAND_TOTAL、TIC_OFFICIAL（Bills/Bonds）、TIC_JAPAN、TIC_CHINA

---

## 5. 評分模型概述

| 階段 | 方法 | 輸出 |
|------|------|------|
| 合成指標 | 原始序列組合（差值/比率） | CREDIT_SPREAD, MORTGAGE_SPREAD, NET_LIQUIDITY 等 |
| 標準化 | EWMA Z-Score（halflife = 504 交易日）× 極性乘數 | 去趨勢化 Z 值 |
| 壓縮 | Sigmoid 壓縮至 [−1, +1] | 各指標 Score |
| 面向聚合 | 四大面向加權（30/30/25/15） | DIM1–DIM4 Score |
| 總分 | 加權平均 → MACRO_SCORE | [-1, +1] |
| Regime | 門檻分類 | 0（緊縮）~ 3（寬鬆） |

### Regime 定義

| MACRO_SCORE | Regime | 標籤 |
|-------------|--------|------|
| ≥ +0.3 | 3 | Expansionary — 寬鬆/有利風險資產 |
| ≥ 0.0 | 2 | Neutral-Bullish — 中性偏多 |
| ≥ −0.3 | 1 | Neutral-Cautious — 中性偏保守 |
| < −0.3 | 0 | Contractionary — 緊縮/風險極高 |

---

## 6. 前端 Dashboard 功能

前端以純靜態網頁實作（HTML + CSS + JavaScript），部署於 GitHub Pages。

### 6.1 全域功能

- **模組 Tab 導覽**：Header 包含 M1–M5 五個模組切換 Tab
- **亮/暗主題切換**：使用者可切換深色（預設）與淺色模式
- **響應式設計**：支援桌面、平板、手機三種佈局
- **GSAP 動畫**：ScrollTrigger 視差動畫、Clip-path 文字揭示、逐字掉落等

### 6.2 側邊欄 (Sidebar)

- **時間範圍切換**：1M / 3M / 6M / 1Y / 3Y / ALL
- **指定資料日期**：年-月-日三級級聯選單，搭配確認按鈕
- **比較指數開關**：S&P 500 / NASDAQ / 道瓊工業 / Russell 2000
- **分數說明入口**

### 6.3 Section A — 環境總分 Macro Score

- SVG 半圓弧 Gauge 指針（動畫計數）
- Regime 語意徽章（寬鬆 / 中性偏多 / 中性偏保守 / 緊縮）
- 子模組分數摘要 Chips（信用、政策、通膨/匯率）

### 6.4 Section B — 四大面向評分 Dimension Scores

- 四個 Mini Gauge SVG（各面向的分數指針）
- 點擊面向按鈕展開 Detail Panel：
  - 顯示該面向的底層原始指標數值（依選定日期從 data.csv 讀取）
  - 顯示面向組成公式與佔比
- ⚙️ 計算公式 Modal：彈出視窗顯示四大面向的權重架構表

### 6.5 Section C — 大環境分數 vs. 美股指數

- 雙 Y 軸折線圖（左：Macro Score，右：指數點位）
- 支援 1M–ALL + 自訂日期範圍
- 指數 Toggle Pill（可開關不同指數）
- 十字準星 Crosshair 插件

### 6.6 Section D — 子指標分數歷史走勢

- 多系列折線圖，依子指標分色
- Toggle Pill 控制各子指標的顯示/隱藏

### 6.7 Section E — 指標說明書入口

- 一鍵開啟 Explainability Drawer
- Drawer 內含完整四大面向指標說明（代碼、名稱、用途、市場關聯性）
- 總結面向之間的連動邏輯

---

## 7. 後端資料管線架構

### 7.1 資料來源

| 來源 | 說明 | 抓取腳本 |
|------|------|----------|
| FRED API | 40+ 總經指標（信用、政策、通膨、匯率等） | `FRED.py` |
| FOMC SEP | 點陣圖利率預測（Kaggle + 手動補充） | `sep_data_fetcher.py` |
| Polymarket | FOMC 利率決策市場機率 | `polymarket_fed.py` |
| TIC | 美國財政部外資持債數據 | `tic_preprocessor.py` |
| Yahoo / FRED | 美股指數（S&P 500, NASDAQ, DJIA, Russell 2000） | `indices_fetch.py` |

### 7.2 處理管線

```
資料抓取 → ETL 整合 → 量化評分 → 前端匯出
```

| 階段 | 腳本 | 輸入 | 輸出 |
|------|------|------|------|
| 資料抓取 | FRED.py / sep_data_fetcher.py / polymarket_fed.py / tic_preprocessor.py | 各 API / 原始檔 | fred_data.xlsx / sep_data.csv / polymarket_fed.json / tic_holdings.csv |
| ETL 整合 | `build_data_csv.py` | 上述所有來源 | `data/data.csv`（標準化長表） |
| V2 評分 | `scorer_v2.py` | data/data.csv | `data/scores.csv`（四大面向 + MACRO_SCORE） |
| 視覺驗證 | `test.py` | data/scores.csv | scores_visualization.png |
| V1 匯出 | `export_dashboard_data.py` | fred_data.xlsx + indices_data.xlsx | `dashboard_data.json` |

---

## 8. 程式框架

### 8.1 目錄結構

```
stock/
├── index.html                      # 平台主進入點（前端 SPA）
├── logo.png                        # 平台 Logo
├── README.md                       # 專案說明
├── 實作步驟.txt                     # 完整交易系統 7 步驟規劃
│
├── assets/                         # 前端靜態資源
│   ├── css/
│   │   ├── style.css               # 主設計系統（紅黑主題、亮/暗模式）
│   │   └── animations.css          # 動畫樣式（reveal、sparkline、clip-path）
│   ├── js/
│   │   ├── data.js                 # 資料抓取與快取層（DataService）
│   │   ├── gauge.js                # SVG 半圓弧 Gauge + Regime 徽章
│   │   ├── charts.js               # Chart.js 雙軸折線圖（ChartC, ChartD）
│   │   ├── animations.js           # GSAP ScrollTrigger 動畫控制器
│   │   └── main.js                 # App Shell 主控制器（State, 路由, 事件綁定）
│   └── data/
│       ├── dashboard_data.json     # V1 前端圖表資料
│       └── scores.csv              # V2 四大面向分數（供 Section B 讀取）
│
├── doc/
│   └── proposal.md                 # 本文件
│
└── 1-大環境/                       # M1 後端模組
    ├── config.py                   # 全域參數配置
    ├── FRED.py                     # FRED API 資料抓取
    ├── indices_fetch.py            # 美股指數抓取
    ├── sep_data_fetcher.py         # FOMC SEP 點陣圖
    ├── polymarket_fed.py           # Polymarket 預測市場
    ├── tic_scraper.py              # TIC 資料下載
    ├── tic_preprocessor.py         # TIC txt 解析 → CSV
    ├── build_data_csv.py           # V2 核心 ETL
    ├── scorer_v2.py                # V2 EWMA 評分引擎
    ├── macro_data_loader.py        # V1 FRED 資料載入
    ├── macro_feature_engineer.py   # V1 特徵工程
    ├── macro_scorer.py             # V1 評分引擎
    ├── policy_forward_score.py     # 政策預期引擎（SEP 70% + PM 30%）
    ├── export_dashboard_data.py    # V1 dashboard JSON 匯出
    ├── main.py                     # V1 完整管線（API → 評分 → 圖表）
    ├── test.py                     # V2 視覺化驗證
    ├── 架構.md                     # 模組架構說明文件
    ├── 指標說明書.md                # 四大面向指標手冊
    └── data/                       # 資料存放
        ├── fred_data.xlsx          # FRED 原始快取
        ├── sep_data.csv / .xlsx    # SEP 點陣圖快取
        ├── tic_holdings.csv        # TIC 長表
        ├── indices_data.xlsx       # 美股指數快取
        ├── data.csv                # V2 主資料表（標準化長表）
        ├── data.xlsx               # V2 分析表（四面向分頁）
        └── scores.csv              # V2 評分結果
```

### 8.2 前端模組關係

```
index.html
  ├── style.css + animations.css        (設計系統 + 動畫)
  ├── Chart.js + chartjs-adapter        (CDN 圖表庫)
  ├── GSAP + ScrollTrigger              (CDN 動畫庫)
  ├── data.js (DataService)             → 載入 dashboard_data.json + scores.csv + data.csv
  ├── gauge.js (GaugeChart)             → 渲染 Section A Gauge
  ├── charts.js (Charts)                → 渲染 Section C & D 圖表
  ├── animations.js (Animations)        → 初始化所有動畫效果
  └── main.js                           → 全局 State 管理、Tab 路由、Section B 建構、事件綁定
```

### 8.3 後端模組關係

```
[資料來源]
  FRED.py ──────────→ fred_data.xlsx
  sep_data_fetcher.py → sep_data.csv
  polymarket_fed.py ──→ polymarket_fed.json
  tic_preprocessor.py → tic_holdings.csv
  indices_fetch.py ───→ indices_data.xlsx

[V2 管線]
  build_data_csv.py ──→ data.csv (整合 4 來源 + 元資料)
  scorer_v2.py ────────→ scores.csv (EWMA → Sigmoid → 四面向 → MACRO_SCORE)
  test.py ─────────────→ scores_visualization.png

[V1 管線（維持相容）]
  export_dashboard_data.py → dashboard_data.json
    ├── macro_feature_engineer.py
    ├── macro_scorer.py
    └── policy_forward_score.py
```

---

## 9. 開發進度

| Phase | 狀態 | 說明 |
|-------|------|------|
| Phase 1：資料工程 | ✅ 完成 | TIC 解析、ETL 整合、data.csv / data.xlsx 輸出 |
| Phase 2：量化評分 | ✅ 完成 | EWMA Z-Score、合成指標、四大面向聚合、scores.csv 輸出 |
| Phase 3：前端展示 | 🔄 進行中 | Section A–E 已完成基礎功能，接入 scores.csv + data.csv |
| Phase 4：M2–M5 模組 | 📋 規劃中 | 基本面、技術指標、交易策略、AI 決策 |

### 已完成的前端功能

- [x] Macro Score Gauge 動畫 + Regime 語意標籤
- [x] 四大面向 Mini Gauge + Detail Panel（含底層原始數據）
- [x] 大環境分數 vs 美股指數雙軸圖表
- [x] 子指標歷史走勢圖
- [x] 指標說明書 Drawer（完整四大面向指標表格）
- [x] 計算公式 Modal（四大面向權重架構）
- [x] 日期級聯選擇器（Year-Month-Day Cascading）
- [x] 亮/暗主題切換 + 響應式佈局
- [x] GSAP ScrollTrigger 動畫系統

---

## 10. 設計原則與非目標

### 10.1 設計原則

- **Real-time / Vintage 安全性**：回測時只使用當時已公開版本的資料
- **方向一致性**：所有指標標準化後映射到同一方向（極性乘數 D_i）
- **多面向判斷**：避免依賴單一宏觀指標，透過四個互補面向共同判定 Regime
- **輔助決策**：這是環境引擎，不是交易策略；輸出是環境描述，不是進出場信號

### 10.2 非目標（目前不在範圍內）

- 不直接提供單一股票的買賣建議
- 不在本階段引入 ML / 聚類模型做 Regime 分類
- 不處理高頻或日內交易信號（定位在日級/週級）
- 不提供自動下單或資產配置執行

---

## 11. 後續發展方向

平台整體交易系統規劃遵循 7 步驟框架：

1. ✅ **宏觀與市場 Regime 判斷**（M1 — 已完成）
2. 📋 標的與風險屬性（alpha / beta 層級）
3. 📋 趨勢判斷與交易方向
4. 📋 波動範圍與波動週期（ATR / 標準差）
5. 📋 分批進場/出場曲線設計
6. 📋 盈虧管理：TP / 動態停利 / 組合風控
7. 📋 回測與迭代

技術擴展方向：
- Regime-conditioned 策略組合回測框架
- ML / 聚類方法自動學習 Regime 分類
- 多國/多區域版本（歐洲、亞洲、新興市場）

---