"""
polymarket_fed.py — Polymarket 聯準會利率決策預測市場
=======================================================
功能：
  1. 自動偵測最近一次 FOMC 會議（依硬編碼時程 + 動態 slug 推算）
  2. 從 Polymarket Gamma API 抓取最近 Fed 決策市場的機率
  3. 同時支援「直接指定 slug」與「自動搜尋」兩種模式
  4. 將結果存成 polymarket_fed.json，供 dashboard 使用

執行方式：
  python polymarket_fed.py
"""

import io
import sys

# 強制 UTF-8 輸出，避免 Windows cp950/GBK 問題
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import json
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests

# ─────────────────────────────────────────────
# 1. FOMC 會議時程（每年 8 次，取「結束日」）
# 更新說明：每年 12 月在 Fed 官網公告下一年時程後補充。
# ─────────────────────────────────────────────
FOMC_SCHEDULE: list[str] = [
    # 2025
    "2025-01-29", "2025-03-19", "2025-04-30",
    "2025-06-18", "2025-07-30", "2025-09-17",
    "2025-10-29", "2025-12-10",
    # 2026
    "2026-01-28", "2026-03-18", "2026-04-29",
    "2026-06-17", "2026-07-29", "2026-09-16",
    "2026-10-28", "2026-12-09",
    # 2027（預估）
    "2027-01-27", "2027-03-17", "2027-04-28",
    "2027-06-16", "2027-07-28", "2027-09-15",
    "2027-10-27", "2027-12-08",
]

# ─────────────────────────────────────────────
# 2. Polymarket Gamma API
# ─────────────────────────────────────────────
GAMMA_BASE = "https://gamma-api.polymarket.com"

# 已知的 Polymarket Fed 決策事件 slug 對應表
# 格式：YYYY-MM → slug（從 embed code 或手動記錄）
KNOWN_SLUGS: dict[str, str] = {
    "2026-06": "fed-decision-in-june-825",
    # 新月份請補充，例如：
    # "2026-07": "fed-decision-in-july-???",
}

# 用來搜尋的關鍵詞列表（依序嘗試）
SEARCH_KEYWORDS = [
    "fed decrease interest rates",
    "fed rate decision",
    "fomc rate",
    "federal reserve rate",
]

# ─────────────────────────────────────────────
# 3. 核心函式
# ─────────────────────────────────────────────

def get_next_fomc() -> tuple[str | None, str | None]:
    """
    回傳 (日期字串 YYYY-MM-DD, 月份字串 YYYY-MM)
    自動找出「今天之後最近的一次 FOMC 會議」。
    """
    today = date.today().isoformat()
    upcoming = [d for d in FOMC_SCHEDULE if d > today]
    if not upcoming:
        return None, None
    next_date = upcoming[0]
    month_key = next_date[:7]  # YYYY-MM
    return next_date, month_key


def fetch_event_by_slug(slug: str) -> dict | None:
    """用 slug 直接從 Gamma API 取得事件資料。"""
    url = f"{GAMMA_BASE}/events"
    params = {"slug": slug, "limit": 1}
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list) and data:
            return data[0]
    except Exception as e:
        print(f"  [WARN] slug 查詢失敗 ({slug}): {e}")
    return None


def search_fed_events(month_key: str) -> list[dict]:
    """
    多關鍵詞搜尋，過濾出包含目標月份的 Fed 利率事件。
    month_key: YYYY-MM，例如 "2026-06"
    """
    dt = datetime.strptime(month_key, "%Y-%m")
    month_en = dt.strftime("%B").lower()  # e.g. "june"
    year = dt.year

    target_patterns = [
        f"{month_en} {year}",   # "june 2026"
        f"{month_en}-{year}",   # "june-2026"
        f"fed-decision-in-{month_en}",  # slug 部分
    ]

    results: list[dict] = []

    for kw in SEARCH_KEYWORDS:
        url = f"{GAMMA_BASE}/events"
        params = {
            "search": kw,
            "active": "true",
            "closed": "false",
            "limit": 20,
        }
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            events: list[dict] = resp.json()

            for ev in events:
                title_slug = (ev.get("title", "") + " " + ev.get("slug", "")).lower()
                if any(pat in title_slug for pat in target_patterns):
                    if ev not in results:
                        results.append(ev)
        except Exception as e:
            print(f"  [WARN] 搜尋失敗 (kw={kw!r}): {e}")
            continue

        if results:
            break  # 找到就停止，減少 API 呼叫

        time.sleep(0.3)  # 避免過快

    return results


def auto_build_slug(month_key: str) -> str | None:
    """
    嘗試從 slug 命名模式推算。
    Polymarket 的 Fed 事件 slug 格式通常是：
    fed-decision-in-{month}-{number}
    此函數無法知道 {number}，僅列出可能的前綴供搜尋用。
    """
    dt = datetime.strptime(month_key, "%Y-%m")
    month_en = dt.strftime("%B").lower()
    return f"fed-decision-in-{month_en}"


def parse_market_outcomes(market: dict) -> list[dict]:
    """解析市場的 outcomes 與 outcomePrices。"""
    raw_outcomes = market.get("outcomes", "[]")
    raw_prices = market.get("outcomePrices", "[]")

    if isinstance(raw_outcomes, str):
        try:
            outcomes = json.loads(raw_outcomes)
        except Exception:
            outcomes = []
    else:
        outcomes = raw_outcomes

    if isinstance(raw_prices, str):
        try:
            prices = json.loads(raw_prices)
        except Exception:
            prices = []
    else:
        prices = raw_prices

    result = []
    for i, outcome in enumerate(outcomes):
        price_raw = prices[i] if i < len(prices) else "0"
        try:
            pct = float(price_raw) * 100
        except Exception:
            pct = 0.0
        result.append({"outcome": outcome, "probability": round(pct, 1)})

    return result


def extract_event_info(event: dict) -> dict:
    """從事件中提取所有子市場的機率。"""
    markets_raw = event.get("markets", [])
    parsed_markets = []

    for m in markets_raw:
        if m.get("closed"):
            continue  # 跳過已結束的市場

        outcomes = parse_market_outcomes(m)
        parsed_markets.append({
            "question":    m.get("question", ""),
            "slug":        m.get("slug", ""),
            "outcomes":    outcomes,
            "volume_usd":  round(float(m.get("volume", 0) or 0), 0),
            "liquidity":   round(float(m.get("liquidity") or m.get("liquidityClob") or 0), 0),
            "end_date":    m.get("endDate", ""),
            "active":      m.get("active", True),
            "polymarket_url": f"https://polymarket.com/event/{event.get('slug', '')}",
            "embed_url":   f"https://embed.polymarket.com/market?market={m.get('slug', '')}&height=300",
        })

    return {
        "event_id":    event.get("id", ""),
        "event_slug":  event.get("slug", ""),
        "event_title": event.get("title", ""),
        "event_url":   f"https://polymarket.com/event/{event.get('slug', '')}",
        "markets":     parsed_markets,
        "total_volume_usd": round(float(event.get("volume", 0) or 0), 0),
    }


# ─────────────────────────────────────────────
# 4. 主函式
# ─────────────────────────────────────────────

def fetch_fed_predictions(verbose: bool = True) -> dict | None:
    """
    主函式：自動偵測最近 FOMC，抓取 Polymarket 機率。
    回傳整理後的 dict，或 None（失敗時）。
    """
    next_date, month_key = get_next_fomc()

    if not next_date:
        print("[Polymarket] ⚠️  FOMC 時程已過期，請更新 FOMC_SCHEDULE。")
        return None

    if verbose:
        print(f"[Polymarket] 🗓  最近 FOMC：{next_date}（{month_key}）")

    event: dict | None = None

    # --- 方法一：已知 slug 直接查 ---
    if month_key in KNOWN_SLUGS:
        known_slug = KNOWN_SLUGS[month_key]
        if verbose:
            print(f"[Polymarket] 🔑 使用已知 slug：{known_slug}")
        event = fetch_event_by_slug(known_slug)

    # --- 方法二：根據 slug 前綴搜尋（無 ID 時） ---
    if not event:
        slug_prefix = auto_build_slug(month_key)
        if verbose:
            print(f"[Polymarket] 🔍 嘗試 slug 前綴查詢：{slug_prefix}*")

        url = f"{GAMMA_BASE}/events"
        try:
            resp = requests.get(url, params={"slug": slug_prefix, "limit": 5}, timeout=10)
            resp.raise_for_status()
            candidates = resp.json()
            if isinstance(candidates, list):
                for c in candidates:
                    if slug_prefix in c.get("slug", ""):
                        event = c
                        break
        except Exception as e:
            print(f"  [WARN] 前綴查詢失敗：{e}")

    # --- 方法三：關鍵詞搜尋 ---
    if not event:
        if verbose:
            print("[Polymarket] 🔍 關鍵詞搜尋中...")
        candidates = search_fed_events(month_key)
        if candidates:
            event = candidates[0]

    # --- 失敗處理 ---
    if not event:
        print(f"[Polymarket] ❌ 找不到 {month_key} 的聯準會市場，請手動補充 KNOWN_SLUGS。")
        print(f"  → 請至 https://polymarket.com 搜尋 'fed {month_key}' 並取得 slug 後加入 KNOWN_SLUGS。")
        return None

    if verbose:
        print(f"[Polymarket] ✅ 找到事件：{event.get('title', '?')}")

    # 組合結果
    info = extract_event_info(event)
    result = {
        "fomc_date":    next_date,
        "fomc_month":   month_key,
        "fetched_at":   datetime.now(timezone.utc).isoformat(),
        **info,
    }

    return result


# ─────────────────────────────────────────────
# 5. 輸出與儲存
# ─────────────────────────────────────────────

def print_result(result: dict) -> None:
    """格式化列印結果。"""
    print("\n" + "═" * 55)
    print(f"📊 {result['event_title']}")
    print(f"🗓  FOMC：{result['fomc_date']}")
    print(f"🔗 {result['event_url']}")
    print(f"💰 總交易量：${result['total_volume_usd']:,.0f}")
    print("─" * 55)

    for m in result["markets"]:
        print(f"\n  ❓ {m['question']}")
        print(f"     成交量：${m['volume_usd']:,.0f} | 流動性：${m['liquidity']:,.0f}")
        for o in m["outcomes"]:
            bar_len = int(o["probability"] / 5)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            print(f"     [{bar}] {o['outcome']:4s}：{o['probability']:.1f}%")
        print(f"     嵌入：{m['embed_url']}")

    print("═" * 55)


def save_result(result: dict, out_path: Path | None = None) -> Path:
    """儲存 JSON 至檔案。"""
    if out_path is None:
        out_path = Path(__file__).parent / "data" / "polymarket_fed.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    return out_path


# ─────────────────────────────────────────────
# 6. 直接執行入口
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  Polymarket 聯準會利率決策抓取器")
    print("=" * 55)

    result = fetch_fed_predictions(verbose=True)

    if result:
        print_result(result)
        saved = save_result(result)
        print(f"\n✅ 結果已儲存至：{saved}")
    else:
        print("\n❌ 抓取失敗，請檢查網路或手動補充 KNOWN_SLUGS。")
        sys.exit(1)
