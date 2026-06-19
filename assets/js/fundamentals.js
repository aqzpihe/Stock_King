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
      label: 'EPS / 盈利', icon: '📊', chartTitle: 'EPS 季度走勢', chartType: 'combo',
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
      label: '損益表', icon: '📋', chartTitle: '營收 & 利潤率走勢', chartType: 'combo',
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
      label: '資產負債', icon: '⚖️', chartTitle: '資產結構（堆疊）', chartType: 'stacked',
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
      label: '現金流量', icon: '💰', chartTitle: '現金流量走勢', chartType: 'grouped',
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

  const C = ['#c0392b', '#3498db', '#9b59b6', '#e67e22', '#1abc9c', '#f39c12'];

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

  function _updateZoomInfo() {
    const el = document.getElementById('fundZoomInfo');
    if (!el) return;
    if (!_data.length) { el.textContent = ''; return; }
    const ratio = _data.length / _view.count;
    el.textContent = '×' + (ratio % 1 < 0.05 ? Math.round(ratio) : ratio.toFixed(1));
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
        ds.backgroundColor = visible.map(r => (r[col.key] ?? 0) >= 0 ? C[i] + 'cc' : '#c0392bcc');
        ds.borderColor     = visible.map(r => (r[col.key] ?? 0) >= 0 ? C[i]        : '#c0392b');
      }
    });
    _chart.update('none');
    _updatePanCursor();
  }

  // ── Zoom with right-edge anchor ──────────────────────────────
  // outward=true → 放大檢視（顯示更多季度，count 增加），向舊資料延伸
  // outward=false → 縮小檢視（顯示更少季度，count 減少），右側（最新）保持可見
  function _doZoom(outward) {
    if (!_data.length) return;
    const step     = Math.max(2, Math.floor(_view.count * 0.15));
    const oldCount = _view.count;
    _view.count    = Math.max(ZOOM_MIN, Math.min(_data.length, _view.count + (outward ? step : -step)));
    const diff     = _view.count - oldCount;
    // 錨定右側（最新資料）：count 增加 → start 向左移，count 減少 → start 向右移
    _view.start    = Math.max(0, _view.start - diff);
    _clampView();
    _updateZoomInfo();
    _updateScrollBar();
    _applyView();
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
    const tickC  = isDark ? '#888884' : '#6b6b6b';

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
          backgroundColor: rows.map(r => (r[col.key] ?? 0) >= 0 ? C[i] + 'cc' : '#c0392bcc'),
          borderColor:     rows.map(r => (r[col.key] ?? 0) >= 0 ? C[i]        : '#c0392b'),
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
    const trs  = rev.map(r => {
      const tds = cols.map(c => {
        const v   = r[c.key];
        const str = _fmt(v, c);
        let cls   = 'tabular-nums';
        if (c.signed && v !== null && v !== undefined) cls += Number(v) >= 0 ? ' val-pos' : ' val-neg';
        return `<td class="${cls}">${str}</td>`;
      }).join('');
      return `<tr><td class="period-cell">${_period(r.period)}</td>${tds}</tr>`;
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
      <div class="fund-dd-item" data-ticker="${c.ticker}">
        <span class="fund-dd-ticker">${c.ticker}</span>
        <span class="fund-dd-name">${c.name || ''}</span>
      </div>`).join('');
    dd.style.display = 'block';

    dd.querySelectorAll('.fund-dd-item').forEach(el => {
      el.addEventListener('click', () => {
        const co = _companies.find(c => c.ticker === el.dataset.ticker);
        if (co) _pick(co);
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
    document.getElementById('fundTableWrap')?.addEventListener('click', e => {
      const th = e.target.closest('.fund-th-link');
      if (!th) return;
      _glossaryOpen = true;
      _renderGlossary(th.dataset.colKey);
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

    // ── 垂直滾輪縮放 ─────────────────────────────────────────────
    const zoomEl   = document.getElementById('fundZoomWheel');
    const zoomBody = document.getElementById('fundZoomWheelBody');

    let _ribOffset = 0;

    function _spinRibs(delta) {
      _ribOffset += delta;
      const cycle = 11;
      zoomBody.style.transform = `translateY(${((_ribOffset % cycle) + cycle) % cycle}px)`;
    }

    // 滑鼠滾輪在滾輪元件上
    zoomEl.addEventListener('wheel', e => {
      e.preventDefault();
      _doZoom(e.deltaY > 0);         // 往下滾 = 放大（顯示更多）
      _spinRibs(e.deltaY > 0 ? 5 : -5);
    }, { passive: false });

    // 拖曳滾輪元件上下 → 縮放（右側錨點：rightEdge 固定）
    let _wDrag = { on: false, y0: 0, c0: 0, rightEdge: 0, o0: 0 };

    zoomEl.addEventListener('mousedown', e => {
      if (!_data.length) return;
      _wDrag = {
        on:        true,
        y0:        e.clientY,
        c0:        _view.count,
        rightEdge: _view.start + _view.count,   // 固定右側邊界
        o0:        _ribOffset,
      };
      e.preventDefault();
    });

    // ── 圖表拖曳平移 ─────────────────────────────────────────────
    const chartCanvas = document.getElementById('fundChart');
    const chartWrap   = document.querySelector('.fund-chart-wrap');

    let _pDrag = { on: false, x0: 0, s0: 0 };

    chartCanvas.addEventListener('mousedown', e => {
      if (!_chart || _view.count >= _data.length) return;
      _pDrag = { on: true, x0: e.clientX, s0: _view.start };
      chartWrap?.classList.add('dragging');
      e.preventDefault();
    });

    // ── 全域 mousemove / mouseup ──────────────────────────────────
    document.addEventListener('mousemove', e => {
      // 縮放拖曳（右側錨點）
      if (_wDrag.on && _data.length) {
        const dy      = e.clientY - _wDrag.y0;
        // 往下拖 = 放大（count 增加）；往上拖 = 縮小（count 減少）
        const delta   = Math.round(dy / 3) * 2;
        const newCnt  = Math.max(ZOOM_MIN, Math.min(_data.length, _wDrag.c0 + delta));
        _view.count   = newCnt;
        _view.start   = Math.max(0, _wDrag.rightEdge - newCnt);
        _clampView();
        _updateZoomInfo();
        _updateScrollBar();
        _applyView();
        _ribOffset = _wDrag.o0 + dy * 0.4;
        _spinRibs(0);
      }

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
      _wDrag.on = false;
      _pDrag.on = false;
      chartWrap?.classList.remove('dragging');
    });
  }

  return { init, rebuildChart };
})();
