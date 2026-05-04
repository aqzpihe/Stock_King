"""景氣與政策 Score - 正規化與評分模組
Rolling Z-score -> 離散子 score -> 加權聚合 -> Regime
"""
import pandas as pd
import numpy as np
import config as cfg


# ============================================================
# Z-score 計算
# ============================================================
def rolling_zscore(series, window=None, min_periods=None):
    """計算滾動 z-score (只使用 t 及以前的資料，無前瞻偏差)"""
    w = window or cfg.ZSCORE_WINDOW
    mp = min_periods or cfg.ZSCORE_MIN_PERIODS
    mu = series.rolling(w, min_periods=mp).mean()
    sigma = series.rolling(w, min_periods=mp).std()
    return (series - mu) / sigma


# ============================================================
# 離散子 score 映射
# ============================================================
def map_score_monotone_neg(z):
    """值越大 -> 景氣越差 (信用利差、FFR、匯率波動)
    Z>=2 -> -2,  1<=Z<2 -> -1,  -1<Z<1 -> 0,  -2<Z<=-1 -> +1,  Z<=-2 -> +2
    """
    if pd.isna(z):
        return np.nan
    if z >= 2:
        return -2
    elif z >= 1:
        return -1
    elif z > -1:
        return 0
    elif z > -2:
        return 1
    else:
        return 2


def map_score_inflation(z):
    """通膨: V 型，過高或過低都扣分
    |Z|>=2 -> -2,  |Z|>=1 -> -1,  else -> 0
    """
    if pd.isna(z):
        return np.nan
    az = abs(z)
    if az >= 2:
        return -2
    elif az >= 1:
        return -1
    else:
        return 0


def map_score_fx_change(z):
    """美元急升 (Z 大) -> 負分;  美元走弱 (Z 小) -> 正分"""
    return map_score_monotone_neg(z)


# ============================================================
# 子模組聚合
# ============================================================
def compute_all_scores(features):
    """
    計算 z-score -> 子 score -> 三大子模組 -> macro_score -> regime

    回傳 DataFrame 包含所有中間與最終結果
    """
    result = pd.DataFrame(index=features.index)

    # --- Z-scores ---
    zscore_map = {}
    for col in features.columns:
        z = rolling_zscore(features[col])
        zscore_map[col] = z
        result[f'Z_{col}'] = z

    # --- 子 scores ---
    credit_cols = []
    # 信用利差 (值越大越糟)
    for col in ['SPREAD_CP_TB6', 'SPREAD_PRIME_TB6', 'SPREAD_BAA_GS10']:
        if col in zscore_map:
            s = zscore_map[col].apply(map_score_monotone_neg)
            result[f'SUB_{col}'] = s
            credit_cols.append(f'SUB_{col}')

    # 貨幣政策 (利率越高越緊縮)
    policy_cols = []
    if 'FFR' in zscore_map:
        s = zscore_map['FFR'].apply(map_score_monotone_neg)
        result['SUB_FFR'] = s
        policy_cols.append('SUB_FFR')

    # 通膨 + 匯率 (Price & FX Stability)
    pricefx_cols = []
    if 'INF_YOY' in zscore_map:
        s = zscore_map['INF_YOY'].apply(map_score_inflation)
        result['SUB_INF_YOY'] = s
        pricefx_cols.append('SUB_INF_YOY')

    if 'FX_CHG_63D' in zscore_map:
        s = zscore_map['FX_CHG_63D'].apply(map_score_fx_change)
        result['SUB_FX_CHG'] = s
        pricefx_cols.append('SUB_FX_CHG')

    if 'FX_VOL' in zscore_map:
        s = zscore_map['FX_VOL'].apply(map_score_monotone_neg)
        result['SUB_FX_VOL'] = s
        pricefx_cols.append('SUB_FX_VOL')

    # --- 模組內聚合 ---
    if credit_cols:
        result['CREDIT_SCORE'] = result[credit_cols].mean(axis=1)
    else:
        result['CREDIT_SCORE'] = 0.0

    if policy_cols:
        result['POLICY_SCORE'] = result[policy_cols].mean(axis=1)
    else:
        result['POLICY_SCORE'] = 0.0

    if pricefx_cols:
        result['PRICEFX_SCORE'] = result[pricefx_cols].mean(axis=1)
    else:
        result['PRICEFX_SCORE'] = 0.0

    # --- 最終 macro_score ---
    result['MACRO_SCORE'] = (
        cfg.WEIGHT_CREDIT  * result['CREDIT_SCORE'] +
        cfg.WEIGHT_POLICY  * result['POLICY_SCORE'] +
        cfg.WEIGHT_PRICEFX * result['PRICEFX_SCORE']
    )

    # --- Regime ---
    def to_regime(score):
        if pd.isna(score):
            return np.nan
        for threshold, regime, _ in cfg.REGIME_MAP:
            if score >= threshold:
                return regime
        return 0

    result['REGIME'] = result['MACRO_SCORE'].apply(to_regime)

    print(f"\n=== 評分完成 ===")
    valid = result['MACRO_SCORE'].dropna()
    if len(valid) > 0:
        print(f"  有效天數: {len(valid)}")
        print(f"  MACRO_SCORE 範圍: [{valid.min():.3f}, {valid.max():.3f}]")
        print(f"  最新 MACRO_SCORE: {valid.iloc[-1]:.3f}")
        last_regime = result['REGIME'].dropna().iloc[-1]
        regime_label = [lbl for t, r, lbl in cfg.REGIME_MAP if r == last_regime]
        print(f"  最新 REGIME: {int(last_regime)} ({regime_label[0] if regime_label else '?'})")

    return result
