import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

# 設定 matplotlib 顯示中文字體 (Windows 預設微軟正黑體)
plt.rcParams['font.sans-serif'] = ['Microsoft JhengHei'] 
plt.rcParams['axes.unicode_minus'] = False

def main():
    base_dir = Path(__file__).parent
    csv_path = base_dir / "data" / "scores.csv"
    out_path = base_dir / "data" / "scores_visualization.png"
    
    if not csv_path.exists():
        print(f"錯誤: 找不到 {csv_path}，請先執行 scorer_v2.py")
        return

    print("載入資料中...")
    df = pd.read_csv(csv_path, parse_dates=["observation_date"], index_col="observation_date")
    
    if df.empty:
        print("錯誤: 資料為空。")
        return
        
    print(f"成功載入資料: 共 {len(df)} 筆，時間範圍 {df.index.min().date()} ~ {df.index.max().date()}")

    # 準備繪圖的欄位與設定
    dims = [
        ("DIM1_SCORE", "面向一：信用市場健康度 [-1, 1]", "blue"),
        ("DIM2_SCORE", "面向二：政策預期與流動性 [-2, 2]", "red"),
        ("DIM3_SCORE", "面向三：國家經濟動能 [-1, 1]", "green"),
        ("DIM4_SCORE", "面向四：國際資本與匯率 [-1, 1]", "purple"),
        ("MACRO_SCORE", "總體 MACRO SCORE [-1, 1]", "black")
    ]

    fig, axes = plt.subplots(len(dims), 1, figsize=(14, 16), sharex=True)
    fig.suptitle("Macro-Regime V2: 四大面向與總體分數走勢", fontsize=18, fontweight='bold')

    # 為了讓圖表更清晰，我們可以預設只畫近 10 年的資料
    start_date = "2015-01-01"
    df_plot = df[df.index >= start_date]
    print(f"正在繪製 {start_date} 至今的資料走勢...")

    for ax, (col, title, color) in zip(axes, dims):
        if col in df_plot.columns:
            # 繪製曲線
            ax.plot(df_plot.index, df_plot[col], color=color, linewidth=1.2)
            
            # 加上零軸基準線
            ax.axhline(0, color='gray', linestyle='--', linewidth=1.5, alpha=0.7) 
            
            ax.set_title(title, fontsize=14)
            ax.grid(True, alpha=0.3)
            
            # 設定 Y 軸範圍
            if col == "DIM2_SCORE":
                ax.set_ylim(-2.2, 2.2)
            else:
                ax.set_ylim(-1.2, 1.2)
                
            # 若是 MACRO_SCORE，可以補上 Regime 的背景顏色區間
            if col == "MACRO_SCORE":
                ax.axhspan(0.3, 1.2, color='green', alpha=0.1, label='Regime 3: 寬鬆')
                ax.axhspan(0.0, 0.3, color='yellow', alpha=0.1, label='Regime 2: 偏多')
                ax.axhspan(-0.3, 0.0, color='orange', alpha=0.1, label='Regime 1: 偏保守')
                ax.axhspan(-1.2, -0.3, color='red', alpha=0.1, label='Regime 0: 緊縮')
                ax.legend(loc="upper left", fontsize=10)
        else:
            ax.text(0.5, 0.5, f"找不到欄位 {col}", ha='center', va='center', fontsize=12)
            
    axes[-1].set_xlabel("日期", fontsize=12)
    plt.tight_layout(rect=[0, 0, 1, 0.97]) # 留出 title 的空間
    
    # 儲存圖表到 data 資料夾
    plt.savefig(out_path, dpi=300)
    print(f"圖表已儲存至: {out_path}")
    
    # 彈出視窗顯示
    print("開啟圖表視窗...")
    plt.show()

if __name__ == "__main__":
    main()