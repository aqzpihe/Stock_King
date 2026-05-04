# 景氣與政策 Score 量化評估系統

本系統旨在透過自動抓取美國聯準會 (FRED) 的各項總體經濟與金融數據，將多個維度的指標（包含信用利差、貨幣政策、通膨、匯率波動等）轉換為單一的「景氣與政策 Score」。這套分數與分類 (Regime) 能夠作為投資策略中控制風險曝險、決定策略啟用與否的客觀量化依據。

## 系統架構與檔案說明

本系統採模組化設計，包含以下核心檔案：

* **`.env`**：環境變數設定檔，必須包含您的 FRED API Key。
* **`config.py`**：系統參數配置檔。您可以在此調整資料抓取範圍、Rolling Z-score 的視窗大小、各子指標的權重配置，以及 Regime 的劃分門檻。
* **`macro_data_loader.py`**：資料載入模組。負責透過 API 抓取 FRED 各項資料，並將不同頻率的資料對齊為日頻 (Daily) DataFrame。
* **`macro_feature_engineer.py`**：特徵工程模組。計算各種衍生指標，如：CP-Tbill 利差、Prime-Tbill 利差、Baa-Treasury 利差、CPI 年增率 (YoY)、匯率變動率等。
* **`macro_scorer.py`**：評分核心模組。負責將特徵進行 Rolling Z-score 標準化、映射離散子分數 (Sub Scores)，最後加權聚合為總分的 `MACRO_SCORE` 以及對應的 `REGIME`。
* **`main.py`**：系統執行主程式。串接上述所有模組，執行完整的資料獲取、計算與可視化流程。

## 環境設定與安裝要求

1. **Python 環境**：確保您已安裝 Python 3.8+ 版本。
2. **安裝依賴套件**：請安裝 `pandas`, `numpy`, 與 `matplotlib`。
   ```bash
   pip install pandas numpy matplotlib
   ```
3. **設定 FRED API Key**：
   請在專案根目錄建立（或修改） `.env` 檔案，並填入您申請到的 FRED API Key：
   ```env
   FRED_API=您的FRED_API金鑰
   ```
   *(註：API 申請請至 [FRED 官方網站](https://fred.stlouisfed.org/docs/api/api_key.html))*

## 如何使用與產出報告

只需在終端機 (命令提示字元 / PowerShell) 執行主程式 `main.py` 即可自動產出報告與圖表：

```bash
python main.py
```

### 執行後的預期產出：

1. **終端機數據報告 (Console Output)**：
   執行時會在終端機印出詳細的運作進度與分析報告，內容包含：
   * 各項數據的成功獲取筆數與日期範圍。
   * **月度平均趨勢表**：顯示目標年份 (如 2025 年) 內每個月的 Credit, Policy, Price/FX 子分數及最終的 Macro Score 與 Regime 分布。
   * **Regime 分布統計**：全年度處於哪種景氣環境的天數與百分比。
   * **最新評分**：提供最後一個交易日的最新指標分數，以便了解當下的總體環境狀態。

2. **可視化圖表產出 (PNG 檔案)**：
   執行完成後，系統會自動在專案目錄下生成一張高解析度的圖表檔案（例如：`macro_score_2025.png`）。
   * **上半部圖表**：呈現 Macro Score 的每日折線圖，並使用不同的背景顏色直觀標示目前的 Regime 狀態 (例如：淺黃色代表中性偏保守、淺綠色代表寬鬆有利)。
   * **下半部圖表**：拆解三大核心子指標 (信用、政策、通膨與匯率) 的走勢，方便您交叉比對是哪一個維度的變化導致了總體分數的變動。

## 後續客製化與擴充

* **更改評估年份**：目前 `main.py` 中預設過濾並呈現 2025 年的數據作為實驗。您可以修改 `main.py` 裡的 `mask_2025` 條件，更改為想要分析的任何時間段。
* **調整權重與門檻**：若發現某項指標對您的交易策略過度敏感或反應太慢，可以直接打開 `config.py` 修改 `WEIGHT_CREDIT`, `WEIGHT_POLICY`, `WEIGHT_PRICEFX` 或 `REGIME_MAP`。
* **串接其他平台**：目前系統已能每日計算出最新的 Regime。未來可進一步將 `main.py` 的最後輸出結果串接至 Google Apps Script 或 GitHub Actions，實現每日自動更新至儀表板。
