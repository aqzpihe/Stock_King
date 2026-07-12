# 資料來源覆蓋率驗證腳本 — 使用說明

## 用途
針對 MSFT,實際呼叫各 API,逐一驗證 PDF 圖表宣稱的「✅直接 / 需計算 / ❌無資料」覆蓋狀態是否屬實。

## 安裝
```bash
pip install requests pandas openpyxl
```

## 設定金鑰(只需設定你有的;沒設的來源會自動跳過)
```bash
export FMP_KEY=你的FMP金鑰
export FINNHUB_KEY=你的Finnhub金鑰
export AV_KEY=你的AlphaVantage金鑰
# SEC EDGAR 免金鑰,一定會跑
```

## 執行
```bash
python3 validate_sources.py
```

## 輸出
`coverage_validation_MSFT.xlsx`,含兩個工作表:
- **驗證矩陣**:51 指標 × 各來源,每來源三欄 = 圖表宣稱(claim)/ 實測(actual)/ 判定(MATCH/MISMATCH/SKIP)
- **總結**:每來源的相符、不符、未測數量與相符率

## 判定規則
| 值 | 意義 | 實測方式 |
|----|------|----------|
| 2 直接取值 | API 該欄位直接回傳數值 | 對應欄位存在且有值 |
| 1 需計算 | 原始數據在,衍生指標需自算 | 公式所需原始欄位都拿得到 |
| 0 無資料 | 連原始欄位都缺 | 對應欄位拿不到 |

## 重要注意事項
1. **EDGAR / AV / Finnhub 的判定較粗略**:腳本用 XBRL concept 名稱比對 companyfacts 的可用欄位,以及 Finnhub metric key 命中。原始報表類指標(非比率)Finnhub 需另用 `financials-reported` endpoint,目前標為「未測 SKIP」以免誤判——若要完整驗 Finnhub,建議補上該 endpoint。
2. **FMP 判定最完整**:有完整欄位對應表(`FMP_MAP`),DIRECT vs CALC 區分清楚。
3. **AV 免費限速 5 req/min**:腳本內已 `sleep(13)`,跑完三張報表約 40 秒,屬正常。
4. **欄位名稱會隨 API 版本變動**:若某指標被誤判為「無資料」,先去 `FMP_MAP` / 各 judge 函式確認欄位名是否仍正確,API 改版時這裡最需要維護。
5. 想換測試公司:改檔頭 `TICKER` 與 `CIK`(EDGAR 需要 10 位補零的 CIK)。

## 沙箱限制說明
此腳本在本對話環境無法實跑,因為環境網路白名單不含 data.sec.gov 及各 API 主機。在你自己的電腦上不受此限。
