/* ================================================================
   fundamentals.js — M2 基本面模組
   Supabase REST API → Chart.js 圖表 + 季度明細表
   支援 X 軸縮放（滾輪 / 拖曳滾輪，右側錨點）+ 拖曳平移 + 底部橫向捲動條
   ================================================================ */

const FundamentalsModule = (() => {
  'use strict';

  const SUPA_URL = 'https://yxydsxygylpzewumevsz.supabase.co';
  const SUPA_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inl4eWRzeHlneWxwemV3dW1ldnN6Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3OTExMjk2MywiZXhwIjoyMDk0Njg4OTYzfQ.LIfd-Aa9HLNAqkD5_UUL6pu2kZT1gESTjXwY8pfxs3o';
  const HDRS = { apikey: SUPA_KEY, Authorization: `Bearer ${SUPA_KEY}` };

  // ── Tab definitions ─────────────────────────────────────────
  const TABS = {
    eps: {
      label: 'EPS / 盈利', chartTitle: 'EPS 季度走勢', chartType: 'combo',
      barCols:  [{ key: 'eps',     label: 'EPS' }],
      lineCols: [{ key: 'eps_ttm', label: 'EPS TTM' }],
      tableCols: [
        { key: 'eps',     label: 'EPS' },
        { key: 'eps_ttm', label: 'TTM' },
        { key: 'eps_qoq', label: 'QoQ%', pct: true, signed: true },
        { key: 'eps_yoy', label: 'YoY%', pct: true, signed: true },
        { key: 'roe',     label: 'ROE%', pct: true },
      ],
    },
    income: {
      label: '損益表', chartTitle: '營收 & 利潤率走勢', chartType: 'combo',
      barCols:  [{ key: 'revenue', label: '營收' }],
      lineCols: [
        { key: 'gross_margin',      label: '毛利率%', pct: true },
        { key: 'operating_margin',  label: '營利率%', pct: true },
        { key: 'net_income_margin', label: '淨利率%', pct: true },
      ],
      tableCols: [
        { key: 'revenue',           label: '營收' },
        { key: 'gross_margin',      label: '毛利率%', pct: true },
        { key: 'operating_margin',  label: '營利率%', pct: true },
        { key: 'net_income_margin', label: '淨利率%', pct: true },
        { key: 'net_income',        label: '淨利' },
      ],
    },
    balance: {
      label: '資產負債', chartTitle: '資產結構（堆疊）', chartType: 'stacked',
      stackCols: [
        { key: 'current_assets',       label: '流動資產' },
        { key: 'fixed_assets',         label: '固定資產' },
        { key: 'long_term_investment', label: '長期投資' },
      ],
      tableCols: [
        { key: 'assets',        label: '總資產' },
        { key: 'liabilities',   label: '總負債' },
        { key: 'equity',        label: '股東權益' },
        { key: 'current_ratio', label: '流動比' },
        { key: 'quick_ratio',   label: '速動比' },
        { key: 'debt_ratio',    label: '負債比%', pct: true },
      ],
    },
    cashflow: {
      label: '現金流量', chartTitle: '現金流量走勢', chartType: 'grouped',
      barCols: [
        { key: 'operating_cash_flow', label: '營業CF' },
        { key: 'investing_cash_flow', label: '投資CF' },
        { key: 'financing_cash_flow', label: '融資CF' },
        { key: 'free_cash_flow',      label: '自由CF' },
      ],
      tableCols: [
        { key: 'operating_cash_flow',           label: '營業現金流' },
        { key: 'free_cash_flow',                label: '自由現金流' },
        { key: 'capex',                         label: 'CAPEX' },
        { key: 'free_cash_flow_per_share',      label: 'FCF/股' },
        { key: 'operating_cash_flow_per_share', label: 'OCF/股' },
      ],
    },
  };

  const C = ['#8B2E2E', '#7A93B8', '#C9A227', '#C94F4F', '#9A9DA6', '#A03636'];

  // ── Per-tab glossary definitions ─────────────────────────────
  const GLOSSARY = {
    eps: [
      {
        colKey: 'eps',
        term: '單季 EPS',
        formula: '單季稅後淨利 ÷ 已發行股數',
        desc: '每單位資本額的獲利能力，越高報酬率越佳。股價對 EPS 複合年成長率敏感，應重視長期趨勢。',
      },
      {
        colKey: 'eps_ttm',
        term: 'EPS TTM（近4季累積）',
        formula: '最近4季母公司業主淨利總和 ÷ 期末在外流通股數',
        desc: '滾動式近一年 EPS，消除單季波動，呈現更穩定的獲利水準。',
      },
      {
        colKey: 'eps_qoq',
        term: 'EPS QoQ%（季增率）',
        formula: '(本季 EPS ÷ 上季 EPS − 1) × 100%',
        desc: '衡量短期季度環比變化，易受淡旺季影響，單獨觀察意義有限。',
      },
      {
        colKey: 'eps_yoy',
        term: 'EPS YoY%（年增率）',
        formula: '(本季 EPS ÷ 去年同期 EPS − 1) × 100%',
        desc: '排除淡旺季失真，反映真實年成長動能；連續正成長為強勢訊號。',
      },
      {
        colKey: 'roe',
        term: 'ROE%（股東權益報酬率）',
        formula: '稅後淨利 ÷ 股東權益 × 100%',
        desc: '衡量股東資金的獲利效率。巴菲特偏好 ROE 長期穩定高於 15% 的公司。',
      },
    ],
    income: [
      {
        colKey: 'revenue',
        term: '營業收入',
        formula: '銷售產品或提供勞務的總收入（未扣成本）',
        desc: '上市櫃每月強制公佈，是財報中最即時的數據。應重視年增率趨勢，忽略淡旺季影響。',
      },
      {
        colKey: 'gross_margin',
        term: '毛利率%',
        formula: '(營收 − 銷貨成本) ÷ 營收 × 100%',
        desc: '觀察產品本身的成本結構變化。毛利率是企業營運活動的源頭，應與同產業橫向比較。',
      },
      {
        colKey: 'operating_margin',
        term: '營業利益率%',
        formula: '營業利益 ÷ 營收 × 100%',
        desc: '扣除銷貨成本與所有營業費用（薪資、廣告、研發）後的本業獲利比率。',
      },
      {
        colKey: 'net_income_margin',
        term: '淨利率%',
        formula: '稅後淨利 ÷ 營收 × 100%',
        desc: '含業外損益，需注意一次性收益或虧損的影響。若淨利率大於 100% 應特別審視業外來源。',
      },
      {
        colKey: 'net_income',
        term: '稅後淨利',
        formula: '稅前淨利 × (1 − 所得稅率)',
        desc: '公司最終盈餘成果。受業外損益影響，建議搭配營業利益率一起觀察。',
      },
    ],
    balance: [
      {
        colKey: 'assets',
        term: '總資產',
        formula: '流動資產 + 長期投資 + 固定資產 + 無形資產',
        desc: '企業取得的一切能帶來經濟利益的資源。透過 ROA 可衡量資產使用效率。',
      },
      {
        colKey: 'liabilities',
        term: '總負債',
        formula: '流動負債 + 長期負債',
        desc: '適度舉債有助成長，但穩健企業負債比率通常低於 60%。短期借款比例越低，償債壓力越小。',
      },
      {
        colKey: 'equity',
        term: '股東權益（淨值）',
        formula: '總資產 − 總負債',
        desc: '公司自有資金，主要包含股本、資本公積與保留盈餘。ROE 衡量其獲利效率。',
      },
      {
        colKey: 'current_ratio',
        term: '流動比',
        formula: '流動資產 ÷ 流動負債',
        desc: '短期償債能力指標，一般認為高於 2 為佳，需搭配產業特性判斷。',
      },
      {
        colKey: 'quick_ratio',
        term: '速動比',
        formula: '(流動資產 − 存貨) ÷ 流動負債',
        desc: '排除變現速度較慢的存貨，更嚴格衡量短期償債能力，一般認為高於 1 為安全線。',
      },
      {
        colKey: 'debt_ratio',
        term: '負債比%',
        formula: '總負債 ÷ 總資產 × 100%',
        desc: '穩健成長企業通常低於 60%。觀察組成結構時，短期借款與長期負債佔比越低越佳。',
      },
    ],
    cashflow: [
      {
        colKey: 'operating_cash_flow',
        term: '營業現金流（OCF）',
        formula: '由核心營運活動帶回的現金流入',
        desc: '比損益表更難造假，是判斷獲利品質的關鍵。OCF 長期大於淨利，代表獲利含金量高。',
      },
      {
        colKey: 'free_cash_flow',
        term: '自由現金流（FCF）',
        formula: '營業現金流 − 資本支出（CAPEX）',
        desc: '企業可自由運用的剩餘資金。長年大於 0 表示本業造血充足，可支應股利或再投資。',
      },
      {
        colKey: 'capex',
        term: 'CAPEX（資本支出）',
        formula: '購買廠房、設備、不動產等固定資產的現金流出',
        desc: '反映管理層對未來業績的樂觀程度。成長期企業 CAPEX 逐年擴大，成熟期則縮小。',
      },
      {
        colKey: 'free_cash_flow_per_share',
        term: 'FCF / 股',
        formula: '自由現金流 ÷ 在外流通股數',
        desc: '每股可自由運用的現金，用於評估股息可持續性及公司內在價值。',
      },
      {
        colKey: 'operating_cash_flow_per_share',
        term: 'OCF / 股',
        formula: '營業現金流 ÷ 在外流通股數',
        desc: '每股由本業帶回的現金，消除股本大小的影響，適合跨公司比較。',
      },
    ],
  };

  // ── Module state ────────────────────────────────────────────
  let _companies    = [];
  let _data         = [];
  let _tab          = 'eps';
  let _chart        = null;
  let _ready        = false;
  let _glossaryOpen = false;

  // X 軸視窗（start = 最舊可見季度 index，count = 可見數量）
  let _view = { start: 0, count: 0 };
  let _zoomIdx = 0;     // 刻度器目前刻度（持久狀態；勿從 ratio 反推，短資料會因取整卡死）
  let _markedPeriod = null;  // 表格點擊標記的期間（以 period 字串記，view 平移不失效）
  const ZOOM_MIN = 4;   // 最少 4 季（1 年）

  // ── Supabase REST helper ─────────────────────────────────────
  async function _get(path) {
    const r = await fetch(`${SUPA_URL}/rest/v1/${path}`, { headers: HDRS });
    if (!r.ok) throw new Error(`Supabase ${r.status}: ${path}`);
    return r.json();
  }

  // ── Value formatter ──────────────────────────────────────────
  function _fmt(v, col) {
    if (v === null || v === undefined) return '—';
    const n = Number(v);
    if (isNaN(n)) return '—';
    if (col.pct) return n.toFixed(1) + '%';
    const a = Math.abs(n);
    if (a >= 1e9) return (n / 1e9).toFixed(2) + 'B';
    if (a >= 1e6) return (n / 1e6).toFixed(1) + 'M';
    if (a >= 1e3) return (n / 1e3).toFixed(1) + 'K';
    return n.toFixed(2);
  }

  // '20164' → '2016 Q4'
  function _period(p) {
    const s = String(p);
    return s.slice(0, 4) + ' Q' + s.slice(4);
  }

  // ── View helpers ─────────────────────────────────────────────
  function _getVisible() {
    if (!_data.length) return [];
    return _data.slice(_view.start, _view.start + _view.count);
  }

  function _clampView() {
    const max = _data.length;
    _view.count = Math.max(ZOOM_MIN, Math.min(max, _view.count));
    _view.start = Math.max(0, Math.min(max - _view.count, _view.start));
  }

  // ── 多邊形刻度器（規格：DESIGN-HANDOFF §6，勿自行變更規則） ──
  // 刻度陣列：1.0→4.2 步進 0.1 ＋ 5.3/7/10.5，共 36 值（35 刻）
  const ZOOM_STEPS = (() => {
    const a = [];
    for (let v = 10; v <= 42; v++) a.push(v / 10);
    a.push(5.3, 7, 10.5);
    return a;
  })();

  // 邊數：起點 3 邊；沿刻度累積變動量，滿 0.2 就 +1 邊並歸零
  function _sidesAt(i) {
    let sides = 3, acc = 0;
    for (let k = 1; k <= i; k++) {
      acc += ZOOM_STEPS[k] - ZOOM_STEPS[k - 1];
      if (acc >= 0.2 - 1e-9) { sides++; acc = 0; }
    }
    return sides;
  }

  // 正 n 邊形頂點，從正上方（-90°）起算
  function _polyPoints(n, cx = 48, cy = 48, r = 34) {
    const pts = [];
    for (let k = 0; k < n; k++) {
      const a = -Math.PI / 2 + k * 2 * Math.PI / n;
      pts.push((cx + r * Math.cos(a)).toFixed(2) + ',' + (cy + r * Math.sin(a)).toFixed(2));
    }
    return pts.join(' ');
  }

  function _updateZoomInfo() {
    if (!_data.length) return;
    const i = _zoomIdx;
    const ring = document.getElementById('fundZoomRing');
    const poly = document.getElementById('fundZoomPoly');
    const readout = document.getElementById('fundZoomReadout');
    const sub = document.getElementById('fundZoomReadoutSub');
    if (!ring) return;
    // 外環＝全行程進度：第 i 刻走 i/35 圈，與倍率大小無關
    ring.setAttribute('stroke-dasharray', `${(i / 35 * 100).toFixed(2)} 100`);
    const sides = _sidesAt(i);
    poly.setAttribute('points', _polyPoints(sides));
    readout.textContent = '×' + ZOOM_STEPS[i].toFixed(1);
    sub.textContent = `${sides} 邊・刻度 ${i}/35`;
  }

  function _updateScrollBar() {
    const wrap   = document.getElementById('fundHScrollWrap');
    const slider = document.getElementById('fundHScroll');
    if (!wrap || !slider) return;
    const zoomed = _data.length > 0 && _view.count < _data.length;
    wrap.style.display  = zoomed ? '' : 'none';
    slider.max   = String(Math.max(0, _data.length - _view.count));
    slider.value = String(_view.start);
  }

  function _updatePanCursor() {
    const wrap = document.querySelector('.fund-chart-wrap');
    if (!wrap) return;
    if (_data.length && _view.count < _data.length) {
      wrap.classList.add('pan-active');
    } else {
      wrap.classList.remove('pan-active');
    }
  }

  // Fast in-place chart update — used during zoom / pan (no destroy/recreate)
  function _applyView() {
    if (!_chart) { _buildChart(); return; }
    const visible = _getVisible();
    _chart.data.labels = visible.map(r => _period(r.period));

    const cfg  = TABS[_tab];
    const cols = [...(cfg.barCols || []), ...(cfg.lineCols || []), ...(cfg.stackCols || [])];
    _chart.data.datasets.forEach((ds, i) => {
      const col = cols[i]; if (!col) return;
      ds.data = visible.map(r => r[col.key] ?? null);
      if (cfg.chartType === 'grouped') {
        ds.backgroundColor = visible.map(r => (r[col.key] ?? 0) >= 0 ? C[i] + 'cc' : '#8B2E2Ecc');
        ds.borderColor     = visible.map(r => (r[col.key] ?? 0) >= 0 ? C[i]        : '#8B2E2E');
      }
    });
    _chart.update('none');
    _updatePanCursor();
  }

  // ── Glossary toggle ──────────────────────────────────────────
  function _renderGlossary(highlightKey = null) {
    const wrap = document.getElementById('fundTableWrap');
    const btn  = document.getElementById('fundGuideBtn');
    if (!wrap) return;

    const entries = GLOSSARY[_tab] || [];
    wrap.innerHTML = `
      <div class="fund-glossary">
        ${entries.map(e => `
          <div class="gls-card${e.colKey === highlightKey ? ' gls-highlighted' : ''}" id="gls-${e.colKey}">
            <div class="gls-term">${e.term}</div>
            <div class="gls-formula">${e.formula}</div>
            <div class="gls-desc">${e.desc}</div>
          </div>`).join('')}
      </div>`;

    if (btn) btn.classList.add('active');

    if (highlightKey) {
      const card = document.getElementById(`gls-${highlightKey}`);
      if (card) card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }

  function _toggleGlossary() {
    _glossaryOpen = !_glossaryOpen;
    const btn = document.getElementById('fundGuideBtn');
    if (_glossaryOpen) {
      _renderGlossary(null);
    } else {
      if (btn) btn.classList.remove('active');
      _buildTable(_data);
    }
  }

  // ── Chart builder ─────────────────────────────────────────────
  // 標記期間的直式高亮帶（綠：palette 中唯一未當系列色的顏色，亮/暗各一；
  // 不讀 --color-down 變數，避免美式漲跌切換後變紅與柱色相撞）
  const _periodMarkPlugin = {
    id: 'periodMark',
    beforeDatasetsDraw(chart) {
      if (_markedPeriod === null) return;
      const vis = _getVisible();
      const i = vis.findIndex(r => r.period === _markedPeriod);
      if (i < 0) return;
      const xs = chart.scales.x;
      const cx = xs.getPixelForValue(i);
      const half = vis.length > 1
        ? Math.abs(xs.getPixelForValue(1) - xs.getPixelForValue(0)) / 2
        : xs.width / 2;
      const { top, bottom } = chart.chartArea;
      const light = document.documentElement.getAttribute('data-theme') === 'light';
      const ctx = chart.ctx;
      ctx.save();
      ctx.fillStyle = light ? 'rgba(46,125,82,.14)' : 'rgba(62,155,107,.14)';
      ctx.fillRect(cx - half, top, half * 2, bottom - top);
      ctx.strokeStyle = light ? '#2E7D52' : '#3E9B6B';
      ctx.lineWidth = 1;
      ctx.strokeRect(cx - half + .5, top + .5, half * 2 - 1, bottom - top - 1);
      ctx.restore();
    },
  };

  function _buildChart() {
    const el = document.getElementById('fundChart');
    if (!el) return;
    if (_chart) { _chart.destroy(); _chart = null; }

    const rows = _getVisible();
    if (!rows.length) return;

    const cfg    = TABS[_tab];
    const labels = rows.map(r => _period(r.period));
    const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
    const gridC  = isDark ? 'rgba(255,255,255,.05)' : 'rgba(0,0,0,.06)';
    const tickC  = isDark ? '#9A9DA6' : '#6B6E78';

    const baseScale = { grid: { color: gridC }, ticks: { color: tickC, font: { size: 10 } } };
    const xScale    = { ...baseScale, ticks: { ...baseScale.ticks, maxRotation: 45, autoSkip: true, maxTicksLimit: 14 } };

    let datasets = [];
    let scales   = { x: xScale };

    if (cfg.chartType === 'combo') {
      cfg.barCols.forEach((col, i) => {
        datasets.push({
          type: 'bar', label: col.label,
          data: rows.map(r => r[col.key] ?? null),
          backgroundColor: C[i] + 'aa', borderColor: C[i], borderWidth: 1,
          yAxisID: 'yL',
        });
      });
      cfg.lineCols.forEach((col, i) => {
        datasets.push({
          type: 'line', label: col.label,
          data: rows.map(r => r[col.key] ?? null),
          borderColor: C[cfg.barCols.length + i],
          backgroundColor: 'transparent',
          borderWidth: 2, pointRadius: 2, tension: 0.3, spanGaps: true,
          yAxisID: 'yR',
        });
      });
      scales.yL = { ...baseScale, position: 'left' };
      scales.yR = { ...baseScale, position: 'right', grid: { display: false } };

    } else if (cfg.chartType === 'stacked') {
      cfg.stackCols.forEach((col, i) => {
        datasets.push({
          type: 'bar', label: col.label,
          data: rows.map(r => r[col.key] ?? null),
          backgroundColor: C[i] + 'cc', borderColor: C[i], borderWidth: 1,
          stack: 'total',
        });
      });
      scales.x = { ...xScale, stacked: true };
      scales.y = { ...baseScale, stacked: true };

    } else {
      cfg.barCols.forEach((col, i) => {
        datasets.push({
          type: 'bar', label: col.label,
          data: rows.map(r => r[col.key] ?? null),
          backgroundColor: rows.map(r => (r[col.key] ?? 0) >= 0 ? C[i] + 'cc' : '#8B2E2Ecc'),
          borderColor:     rows.map(r => (r[col.key] ?? 0) >= 0 ? C[i]        : '#8B2E2E'),
          borderWidth: 1,
        });
      });
      scales.y = baseScale;
    }

    const allCols = [...(cfg.barCols||[]), ...(cfg.lineCols||[]), ...(cfg.stackCols||[])];

    _chart = new Chart(el, {
      type: 'bar',
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: {
            position: 'top',
            labels: { color: tickC, boxWidth: 12, padding: 10, font: { size: 11 } },
          },
          tooltip: {
            callbacks: {
              label(ctx) {
                if (ctx.raw === null) return null;
                const col = allCols[ctx.datasetIndex] || {};
                return ` ${ctx.dataset.label}: ${_fmt(ctx.raw, col)}`;
              },
            },
          },
        },
        scales,
      },
      plugins: [_periodMarkPlugin],
    });

    _updatePanCursor();
  }

  // ── Table builder ─────────────────────────────────────────────
  function _buildTable(rows) {
    const wrap = document.getElementById('fundTableWrap');
    if (!wrap) return;
    if (!rows.length) {
      wrap.innerHTML = '<div class="fund-empty">此公司尚無基本面資料</div>';
      return;
    }
    const cols = TABS[_tab].tableCols;
    const rev  = [...rows].reverse();
    const ths  = cols.map(c => `<th class="fund-th-link" data-col-key="${c.key}" title="點擊查看說明">${c.label}</th>`).join('');
    const trs  = rev.map((r, ri) => {
      const tds = cols.map(c => {
        const v   = r[c.key];
        const str = _fmt(v, c);
        let cls   = 'tabular-nums';
        if (c.signed && v !== null && v !== undefined) cls += Number(v) >= 0 ? ' val-pos' : ' val-neg';
        return `<td class="${cls}">${str}</td>`;
      }).join('');
      const dataIdx = rows.length - 1 - ri;
      return `<tr data-idx="${dataIdx}" title="點擊跳轉圖表至此期間"><td class="period-cell">${_period(r.period)}</td>${tds}</tr>`;
    }).join('');
    wrap.innerHTML = `
      <table class="fund-table">
        <thead><tr><th>期間</th>${ths}</tr></thead>
        <tbody>${trs}</tbody>
      </table>`;
  }

  // ── Render (full rebuild, resets view to show ALL data) ──────
  function _render() {
    _view = { start: 0, count: _data.length };
    _zoomIdx = 0;
    _markedPeriod = null;
    _glossaryOpen = false;
    const btn = document.getElementById('fundGuideBtn');
    if (btn) btn.classList.remove('active');
    const cfg = TABS[_tab];
    document.getElementById('fundChartTitle').textContent = cfg.chartTitle;
    document.getElementById('fundTableTitle').textContent = cfg.label + ' 明細';
    _buildChart();
    _buildTable(_data);
    _updateZoomInfo();
    _updateScrollBar();
  }

  // ── Company selected ─────────────────────────────────────────
  async function _pick(company) {
    document.getElementById('fundSearch').value = company.ticker;
    document.getElementById('fundSearchDropdown').style.display = 'none';

    const infoEl = document.getElementById('fundCompanyInfo');
    infoEl.style.display = '';
    document.getElementById('fundCompanyName').textContent = company.name || company.ticker;
    document.getElementById('fundCompanyMeta').innerHTML = [company.exchange, company.currency]
      .filter(Boolean).map(t => `<span class="fund-badge">${t}</span>`).join('');

    document.getElementById('fundTableWrap').innerHTML = '<div class="fund-empty">載入資料中…</div>';
    if (_chart) { _chart.destroy(); _chart = null; }

    try {
      _data = await _get(
        `fundamentals?ticker=eq.${encodeURIComponent(company.ticker)}&order=period.asc&limit=60`
      );
    } catch (e) {
      _data = [];
      console.error('[M2] fundamentals fetch:', e);
    }

    _render();
  }

  // ── Search dropdown ──────────────────────────────────────────
  function _dropdown(query) {
    const dd = document.getElementById('fundSearchDropdown');
    const q  = query.trim().toLowerCase();
    if (!q) { dd.style.display = 'none'; return; }

    const hits = _companies
      .filter(c => c.ticker.toLowerCase().includes(q) || (c.name || '').toLowerCase().includes(q))
      .slice(0, 12);

    if (!hits.length) { dd.style.display = 'none'; return; }

    dd.innerHTML = hits.map(c => `
      <div class="fund-dd-item" data-ticker="${c.ticker}" tabindex="0" role="option">
        <span class="fund-dd-ticker">${c.ticker}</span>
        <span class="fund-dd-name">${c.name || ''}</span>
      </div>`).join('');
    dd.style.display = 'block';

    dd.querySelectorAll('.fund-dd-item').forEach(el => {
      const pick = () => {
        const co = _companies.find(c => c.ticker === el.dataset.ticker);
        if (co) _pick(co);
      };
      el.addEventListener('click', pick);
      // Tab 移動焦點、Enter 選取
      el.addEventListener('keydown', e => {
        if (e.key === 'Enter') { e.preventDefault(); pick(); }
      });
    });
  }

  // ── Tab switch (preserves zoom/pan state + glossary mode) ────
  function _switchTab(key) {
    _tab = key;
    document.querySelectorAll('.fund-tab').forEach(b => b.classList.toggle('active', b.dataset.tab === key));
    if (_data.length) {
      document.getElementById('fundChartTitle').textContent = TABS[_tab].chartTitle;
      document.getElementById('fundTableTitle').textContent = TABS[_tab].label + ' 明細';
      _buildChart();
      if (_glossaryOpen) _renderGlossary(null); else _buildTable(_data);
    }
  }

  // ── Public: rebuild chart colors on theme change ─────────────
  function rebuildChart() {
    if (_data.length) _buildChart();
  }

  // ── Init ─────────────────────────────────────────────────────
  async function init() {
    if (_ready) return;
    _ready = true;

    try {
      _companies = await _get('companies?select=ticker,name,exchange,currency&order=ticker');
    } catch (e) {
      console.warn('[M2] companies fetch failed:', e);
    }

    const input = document.getElementById('fundSearch');
    const dd    = document.getElementById('fundSearchDropdown');

    input.addEventListener('input',   () => _dropdown(input.value));
    input.addEventListener('focus',   () => { if (input.value.trim()) _dropdown(input.value); });
    input.addEventListener('keydown', e => {
      if (e.key !== 'Enter') return;
      const first = dd.querySelector('.fund-dd-item');
      if (first) {
        const co = _companies.find(c => c.ticker === first.dataset.ticker);
        if (co) { _pick(co); return; }
      }
      const q = input.value.trim().toUpperCase();
      const exact = _companies.find(c => c.ticker === q);
      if (exact) _pick(exact);
    });

    document.addEventListener('click', e => {
      if (!e.target.closest('.fund-search-wrap')) dd.style.display = 'none';
    });

    document.querySelectorAll('.fund-tab').forEach(btn => {
      btn.addEventListener('click', () => _switchTab(btn.dataset.tab));
    });

    document.getElementById('fundGuideBtn')?.addEventListener('click', _toggleGlossary);

    // 點擊表格欄位標題 → 開啟說明書並定位到對應指標
    // 點擊資料列 → 帶著目前刻度跳轉圖表至該期間並標記該列
    document.getElementById('fundTableWrap')?.addEventListener('click', e => {
      const th = e.target.closest('.fund-th-link');
      if (th) {
        _glossaryOpen = true;
        _renderGlossary(th.dataset.colKey);
        return;
      }
      const tr = e.target.closest('tr[data-idx]');
      if (!tr || !_data.length) return;
      const target = parseInt(tr.dataset.idx, 10);
      _markedPeriod = _data[target]?.period ?? null;
      // 保持目前縮放（count 不變），將目標期間置中
      _view.start = Math.max(0, Math.min(
        _data.length - _view.count,
        target - Math.floor((_view.count - 1) / 2)
      ));
      _updateScrollBar();
      _applyView();
      tr.closest('tbody')?.querySelectorAll('.fund-row-marked')
        .forEach(el => el.classList.remove('fund-row-marked'));
      tr.classList.add('fund-row-marked');
    });

    // ── 橫向捲動條 ───────────────────────────────────────────────
    const hScroll = document.getElementById('fundHScroll');
    if (hScroll) {
      hScroll.addEventListener('input', () => {
        _view.start = parseInt(hScroll.value, 10);
        _clampView();
        _applyView();
      });
    }

    // ── 多邊形刻度器：滾輪＋±按鈕（右側錨點） ─────────────────────
    const zoomEl = document.getElementById('fundZoomWheel');

    function _setZoomIdx(i) {
      if (!_data.length) return;
      // 刻度永遠可走滿 0..35；可見季數另以 ZOOM_MIN 下限保護
      _zoomIdx = Math.max(0, Math.min(ZOOM_STEPS.length - 1, i));
      const rightEdge = _view.start + _view.count;
      _view.count = Math.max(ZOOM_MIN, Math.min(_data.length, Math.round(_data.length / ZOOM_STEPS[_zoomIdx])));
      _view.start = Math.max(0, rightEdge - _view.count);
      _clampView();
      _updateZoomInfo();
      _updateScrollBar();
      _applyView();
    }

    function _stepZoom(dir) {
      _setZoomIdx(_zoomIdx + dir);
    }

    zoomEl.addEventListener('wheel', e => {
      e.preventDefault();
      _stepZoom(e.deltaY < 0 ? 1 : -1);   // 上=放大
    }, { passive: false });

    document.getElementById('fundZoomPlus')?.addEventListener('click', () => _stepZoom(1));
    document.getElementById('fundZoomMinus')?.addEventListener('click', () => _stepZoom(-1));

    // ── 圖表拖曳平移 ─────────────────────────────────────────────
    const chartCanvas = document.getElementById('fundChart');
    const chartWrap   = document.querySelector('.fund-chart-wrap');

    // 圖表上直接滾輪縮放（走同一套刻度，左下角多邊形刻度器自動連動）
    chartCanvas.addEventListener('wheel', e => {
      if (!_data.length) return;
      e.preventDefault();
      _stepZoom(e.deltaY < 0 ? 1 : -1);   // 上=放大
    }, { passive: false });

    let _pDrag = { on: false, x0: 0, s0: 0 };

    chartCanvas.addEventListener('mousedown', e => {
      if (!_chart || _view.count >= _data.length) return;
      _pDrag = { on: true, x0: e.clientX, s0: _view.start };
      chartWrap?.classList.add('dragging');
      e.preventDefault();
    });

    // ── 全域 mousemove / mouseup ──────────────────────────────────
    document.addEventListener('mousemove', e => {
      // 平移拖曳（左右拖動圖表）
      if (_pDrag.on && _chart && _data.length) {
        const dx     = e.clientX - _pDrag.x0;
        const areaW  = _chart.chartArea?.width || 1;
        const pxPerQ = areaW / Math.max(1, _view.count - 1);
        _view.start  = Math.max(0, Math.min(
          _data.length - _view.count,
          _pDrag.s0 - Math.round(dx / pxPerQ)
        ));
        _updateScrollBar();
        _applyView();
      }
    });

    document.addEventListener('mouseup', () => {
      _pDrag.on = false;
      chartWrap?.classList.remove('dragging');
    });
  }

  return { init, rebuildChart };
})();
