"""景氣與政策 Score - 特徵工程模組
計算信用利差、匯率變動率等衍生特徵
"""
import pandas as pd
import numpy as np


def compute_features(df):
    """
    從原始資料計算所有衍生特徵

    輸入欄位: CPN3M, DTB6, DPRIME, DBAA, DGS10, DFF, INF_YOY, DTWEXBGS, EMVEXRATES
    輸出: 新 DataFrame 包含所有特徵欄位
    """
    feat = pd.DataFrame(index=df.index)

    # ========== 信用利差 ==========
    # 1. CP-Tbill: 商業本票 vs 6M 國庫券
    if 'CPN3M' in df.columns and 'DTB6' in df.columns:
        feat['SPREAD_CP_TB6'] = df['CPN3M'] - df['DTB6']

    # 2. Prime-Tbill: 銀行 Prime Rate vs 6M 國庫券
    if 'DPRIME' in df.columns and 'DTB6' in df.columns:
        feat['SPREAD_PRIME_TB6'] = df['DPRIME'] - df['DTB6']

    # 3. Baa-Treasury: Baa 公司債 vs 10Y 國債
    if 'DBAA' in df.columns and 'DGS10' in df.columns:
        feat['SPREAD_BAA_GS10'] = df['DBAA'] - df['DGS10']

    # ========== 貨幣政策 ==========
    if 'DFF' in df.columns:
        feat['FFR'] = df['DFF']

    # ========== 通膨 ==========
    if 'INF_YOY' in df.columns:
        feat['INF_YOY'] = df['INF_YOY']

    # ========== 匯率 ==========
    # 美元指數 63 日變動率 (~3 個月)
    if 'DTWEXBGS' in df.columns:
        feat['FX_CHG_63D'] = df['DTWEXBGS'].pct_change(63) * 100

    # 匯率波動指標 (直接使用)
    if 'EMVEXRATES' in df.columns:
        feat['FX_VOL'] = df['EMVEXRATES']

    n_feat = feat.shape[1]
    print(f"\n=== 特徵工程完成: {n_feat} 個特徵 ===")
    for col in feat.columns:
        valid = feat[col].dropna()
        if len(valid) > 0:
            print(f"  {col:20s}  有效: {len(valid):>5d} 天  "
                  f"最新: {valid.iloc[-1]:>8.3f}")
    return feat
