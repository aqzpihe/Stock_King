"""景氣與政策 Score - 主程式
抓資料 -> 特徵工程 -> 評分 -> 輸出 2025 年實驗結果
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import config as cfg
from macro_data_loader import load_all_data
from macro_feature_engineer import compute_features
from macro_scorer import compute_all_scores


def print_separator(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def main():
    # ===== 1. 抓取資料 =====
    print_separator("Step 1: 從 FRED API 抓取資料")
    df_raw = load_all_data(
        start_date=cfg.DATA_START_DATE,
        cpi_start=cfg.CPI_START_DATE,
        delay=cfg.API_DELAY_SECONDS,
    )

    # ===== 2. 特徵工程 =====
    print_separator("Step 2: 特徵工程")
    features = compute_features(df_raw)

    # ===== 3. 評分 =====
    print_separator("Step 3: 計算 Macro Score & Regime")
    scores = compute_all_scores(features)

    # ===== 4. 2025 年實驗結果 =====
    print_separator("2025 年實驗結果")

    mask_2025 = (scores.index >= '2025-01-01') & (scores.index <= '2025-12-31')
    s2025 = scores[mask_2025].copy()

    if s2025.empty or s2025['MACRO_SCORE'].dropna().empty:
        print("!! 2025 年無有效 MACRO_SCORE 資料")
        return

    # 核心欄位
    core = ['CREDIT_SCORE', 'POLICY_SCORE', 'PRICEFX_SCORE',
            'MACRO_SCORE', 'REGIME']

    # --- 月度摘要 ---
    print("\n--- 2025 月度平均 MACRO_SCORE & REGIME 分布 ---\n")
    monthly = s2025[core].resample('ME').mean()
    monthly['REGIME'] = s2025['REGIME'].resample('ME').agg(
        lambda x: x.mode().iloc[0] if len(x.dropna()) > 0 else np.nan
    )

    regime_labels = {r: lbl for _, r, lbl in cfg.REGIME_MAP}
    monthly['REGIME_LABEL'] = monthly['REGIME'].map(
        lambda x: regime_labels.get(int(x), '?') if pd.notna(x) else '?'
    )
    print(monthly[['CREDIT_SCORE', 'POLICY_SCORE', 'PRICEFX_SCORE',
                    'MACRO_SCORE', 'REGIME', 'REGIME_LABEL']].to_string(
        float_format='{:.3f}'.format
    ))

    # --- Regime 分布統計 ---
    print("\n--- 2025 Regime 分布 (天數) ---\n")
    regime_counts = s2025['REGIME'].dropna().value_counts().sort_index()
    for reg_val, count in regime_counts.items():
        label = regime_labels.get(int(reg_val), '?')
        pct = count / len(s2025['REGIME'].dropna()) * 100
        print(f"  Regime {int(reg_val)} ({label}): {count} 天 ({pct:.1f}%)")

    # --- 極端日期 ---
    valid_scores = s2025['MACRO_SCORE'].dropna()
    print(f"\n--- 2025 極端值 ---\n")
    print(f"  最高 MACRO_SCORE: {valid_scores.max():.3f} "
          f"({valid_scores.idxmax().date()})")
    print(f"  最低 MACRO_SCORE: {valid_scores.min():.3f} "
          f"({valid_scores.idxmin().date()})")
    print(f"  年度平均: {valid_scores.mean():.3f}")
    print(f"  年度標準差: {valid_scores.std():.3f}")

    # --- 最新可用分數 ---
    latest = scores['MACRO_SCORE'].dropna()
    if not latest.empty:
        last_date = latest.index[-1]
        last_score = latest.iloc[-1]
        last_regime = int(scores.loc[last_date, 'REGIME'])
        last_label = regime_labels.get(last_regime, '?')
        print(f"\n--- 最新評分 ({last_date.date()}) ---\n")
        print(f"  CREDIT_SCORE:  {scores.loc[last_date, 'CREDIT_SCORE']:.3f}")
        print(f"  POLICY_SCORE:  {scores.loc[last_date, 'POLICY_SCORE']:.3f}")
        print(f"  PRICEFX_SCORE: {scores.loc[last_date, 'PRICEFX_SCORE']:.3f}")
        print(f"  MACRO_SCORE:   {last_score:.3f}")
        print(f"  REGIME:        {last_regime} ({last_label})")

    # --- 子 score 明細 (最新日) ---
    sub_cols = [c for c in scores.columns if c.startswith('SUB_')]
    if sub_cols and not latest.empty:
        print(f"\n--- 子 score 明細 ({last_date.date()}) ---\n")
        for c in sub_cols:
            v = scores.loc[last_date, c]
            print(f"  {c:25s}: {v:+.1f}" if pd.notna(v) else f"  {c:25s}: N/A")

    # ===== 5. 產出圖表 =====
    print_separator("Step 5: 產出可視化圖表")
    plot_results(s2025, df_raw, cfg)

    print(f"\n{'='*60}")
    print("  實驗完成")
    print(f"{'='*60}")

def plot_results(s2025, df_raw, cfg):
    """將 2025 年的 Macro Score、各子指標以及道瓊工業指數繪製成圖表並儲存"""
    plt.figure(figsize=(14, 10))
    
    # 解決中文字體顯示問題 (Windows)
    plt.rcParams['font.sans-serif'] = ['Microsoft JhengHei'] 
    plt.rcParams['axes.unicode_minus'] = False
    
    # 1. Macro Score & Regime
    ax1 = plt.subplot(2, 1, 1)
    ax1.plot(s2025.index, s2025['MACRO_SCORE'], label='Macro Score', color='black', linewidth=2)
    ax1.set_title('2025 景氣與政策 Macro Score', fontsize=16)
    ax1.set_ylabel('Score')
    ax1.grid(True, linestyle='--', alpha=0.6)
    
    # 根據 Regime 畫背景色
    regime_colors = {
        3: 'lightgreen',
        2: 'lightblue',
        1: 'lightyellow',
        0: 'lightcoral'
    }
    
    y_min, y_max = ax1.get_ylim()
    for r, color in regime_colors.items():
        mask = (s2025['REGIME'] == r)
        if mask.any():
            ax1.fill_between(s2025.index, y_min, y_max, 
                             where=mask, color=color, alpha=0.3, label=f'Regime {r}')
            
    # 新增道瓊工業指數 (DJIA) 至副坐標軸
    if 'DJIA' in df_raw.columns:
        ax1_twin = ax1.twinx()
        djia_2025 = df_raw.loc[s2025.index, 'DJIA']
        ax1_twin.plot(djia_2025.index, djia_2025, label='DJIA (道瓊工業指數)', color='orange', linewidth=2, linestyle='-.')
        ax1_twin.set_ylabel('DJIA Index', color='orange')
        ax1_twin.tick_params(axis='y', labelcolor='orange')
        
    # 合併兩個軸的圖例
    handles1, labels1 = ax1.get_legend_handles_labels()
    handles2, labels2 = ax1_twin.get_legend_handles_labels() if 'DJIA' in df_raw.columns else ([], [])
    
    handles = handles1 + handles2
    labels = labels1 + labels2
    
    by_label = dict(zip(labels, handles))
    ax1.legend(by_label.values(), by_label.keys(), loc='upper left')

    # 2. Sub Scores
    ax2 = plt.subplot(2, 1, 2)
    ax2.plot(s2025.index, s2025['CREDIT_SCORE'], label='Credit Score (信用)', color='blue', alpha=0.8)
    ax2.plot(s2025.index, s2025['POLICY_SCORE'], label='Policy Score (政策)', color='red', alpha=0.8)
    ax2.plot(s2025.index, s2025['PRICEFX_SCORE'], label='Price/FX Score (通膨與匯率)', color='green', alpha=0.8)
    ax2.set_title('2025 子指標分數 (Sub Scores)', fontsize=16)
    ax2.set_ylabel('Score')
    ax2.grid(True, linestyle='--', alpha=0.6)
    ax2.legend(loc='upper left')
    
    plt.tight_layout()
    plt.savefig('macro_score_2025.png', dpi=300)
    print("  -> 已將圖表儲存為: macro_score_2025.png")


if __name__ == '__main__':
    main()
