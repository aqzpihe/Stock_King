import json
import requests


def verify_sec_api():
    # 1. 設定 SEC 要求的 User-Agent 標頭（請記得將 Email 改為你自己的）
    # 格式必須是：姓名/組織名稱 聯絡Email
    headers = {
        "User-Agent": "Mao-Chen Shu your_email@example.com",
        "Accept-Encoding": "gzip, deflate",  # SEC 建議加入，可加快傳輸速度
    }

    # 2. SEC EDGAR 獲取所有公司股票代號與 CIK 對應表的 API 端點
    url = "https://data.sec.gov/files/company_tickers.json"

    print("正在發送請求至 SEC EDGAR API...")

    try:
        # 3. 發送 GET 請求
        response = requests.get(url, headers=headers)

        # 檢查 HTTP 狀態碼是否為 200 (成功)
        if response.status_code == 200:
            print("🎉 驗證成功！已順利連線至 SEC EDGAR API。")

            # 4. 解析 JSON 數據
            data = response.json()

            # 5. 簡單印出前 3 家公司資料來確認內容
            print("\n--- 取得的部分美股 CIK 列表範例 ---")
            # SEC 回傳的格式中，Key 是字串型態的數字（如 "0", "1", "2"...）
            for i in range(3):
                item = data.get(str(i))
                if item:
                    print(
                        f"公司名稱: {item['title']} | 股票代號: {item['ticker']} | CIK: {item['cik_str']}"
                    )

        elif response.status_code == 403:
            print("❌ 驗證失敗 (403 Forbidden)：")
            print(
                "這通常是因為 User-Agent 格式不符合 SEC 規定，或是你的 IP 發送請求太快被暫時封鎖。"
            )
        else:
            print(f"❌ 收到未期的狀態碼: {response.status_code}")

    except Exception as e:
        print(f"❌ 發生連線錯誤: {e}")


if __name__ == "__main__":
    verify_sec_api()