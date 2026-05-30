/* ================================================================
   main.js — App Shell 主控制器
   Tab 路由、主題切換、全局 State、事件綁定
   ================================================================ */

(async () => {
  'use strict';

  // ===== Global State =====
  const STATE = {
    range: '1Y',
    customFrom: null,
    customTo: null,
    activeIndices: new Set(['SP500', 'NASDAQCOM']),
    activeSubs: new Set(),
    currentModule: 'm1-macro',
    data: null,
  };

  // ===== 四大面向規格常數 =====
  const DIMS = [
    {
      key: 'DIM1_SCORE',
      label: '面向一',
      name: '信用市場',
      weight: '30%',
      color: 'var(--chart-color-2)',
      composition: [
        '70% RT：CREDIT_SPREAD, MORTGAGE_SPREAD',
        '30% Lag：DRBLACBS',
      ],
    },
    {
      key: 'DIM2_SCORE',
      label: '面向二',
      name: '政策流動性',
      weight: '30%',
      color: 'var(--chart-color-3)',
      composition: [
        '60% RT：NET_LIQ_CHG, DFF',
        '40% Lead：T10Y2Y',
        '+ Credibility % 獨立輸出',
      ],
    },
    {
      key: 'DIM3_SCORE',
      label: '面向三',
      name: '經濟動能',
      weight: '25%',
      color: 'var(--chart-color-4)',
      composition: [
        '70% Lead：JTSJOL, JTSQUR, BABATOTALSAUS',
        '30% Lag：INDPRO, PAYEMS',
      ],
    },
    {
      key: 'DIM4_SCORE',
      label: '面向四',
      name: '國際資本',
      weight: '15%',
      color: 'var(--chart-color-5)',
      composition: [
        '70% RT：DTWEXBGS, EMVEXRATES',
        '30% Lag：TIC_GRAND_TOTAL_MOM',
      ],
    },
  ];

  const RAW_INDICATORS = {
    DIM1_SCORE: [
      { key: 'CPN3M', label: 'CPN3M(3個月商業本票利率)' },
      { key: 'DTB6', label: 'DTB6(6個月國庫券利率)' },
      { key: 'DPRIME', label: 'DPRIME(銀行優惠貸款利率)' },
      { key: 'DBAA', label: 'DBAA(穆迪 BAA 級企業債收益率)' },
      { key: 'DGS10', label: 'DGS10(10年期國債收益率)' },
      { key: 'DRBLACBS', label: 'DRBLACBS(銀行資產核銷率)' },
    ],
    DIM2_SCORE: [
      { key: 'DFF', altKey: 'FEDFUNDS', label: 'DFF / FEDFUNDS(有效聯邦基金利率)' },
      { key: 'WALCL', label: 'WALCL(聯準會資產負債表總規模)' },
      { key: 'WTREGEN', label: 'WTREGEN(財政部一般帳戶)' },
      { key: 'RRPONTSYD', label: 'RRPONTSYD(隔夜逆回購)' },
      { key: 'T10Y2Y', label: 'T10Y2Y(10年與2年期國債利差)' },
      { key: 'DGS2', label: 'DGS2(2年期國債收益率)' },
      { key: 'DGS30', label: 'DGS30(30年期國債收益率)' },
      { key: 'MORTGAGE30US', label: 'MORTGAGE30US(30年期房貸利率)' },
      { key: 'SEP_FFR', label: 'SEP_FFR(Fed 點陣圖預期)' },
      { key: 'POLYMARKET_RATE', label: 'POLYMARKET_RATE(預測市場利率)' },
    ],
    DIM3_SCORE: [
      { key: 'CPIAUCSL', label: 'CPIAUCSL(消費者物價指數 CPI)' },
      { key: 'PCE', label: 'PCE(個人消費支出物價指數)' },
      { key: 'PPIACO', label: 'PPIACO(生產者物價指數)' },
      { key: 'UNRATE', altKey: 'PAYEMS', label: 'UNRATE / PAYEMS(失業率與非農就業)' },
      { key: 'ICSA', label: 'ICSA(初次申領失業救濟金人數)' },
      { key: 'JTSJOL', altKey: 'JTSQUR', label: 'JTSJOL / JTSQUR(職位空缺與離職率)' },
      { key: 'INDPRO', altKey: 'GDP', label: 'INDPRO / GDP(工業生產與國內生產總值)' },
      { key: 'UMCSENT', label: 'UMCSENT(密西根大學消費者信心指數)' },
      { key: 'BABATOTALSAUS', label: 'BABATOTALSAUS(商業總銷售額)' },
    ],
    DIM4_SCORE: [
      { key: 'DTWEXBGS', label: 'DTWEXBGS(美元貿易加權指數)' },
      { key: 'EMVEXRATES', label: 'EMVEXRATES(匯率波動率)' },
      { key: 'BOPBCA', label: 'BOPBCA(經常帳餘額)' },
      { key: 'TIC_GRAND_TOTAL', label: 'TIC_GRAND_TOTAL(外國人買入美國證券總淨額)' },
      { key: 'TIC_OFFICIAL', label: 'TIC_OFFICIAL (Bills/Bonds)(外國央行對美債增減持)' },
      { key: 'TIC_JAPAN', label: 'TIC_JAPAN(日本持倉變動)' },
      { key: 'TIC_CHINA', label: 'TIC_CHINA(中國持倉變動)' },
    ],
  };

  // ===== Theme Toggle =====
  const themeBtn = document.getElementById('themeToggle');
  const savedTheme = localStorage.getItem('theme') || 'dark';
  document.documentElement.setAttribute('data-theme', savedTheme);
  updateThemeIcon(savedTheme);

  themeBtn.addEventListener('click', () => {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    updateThemeIcon(next);
    // Rebuild charts with new theme colors
    if (STATE.data) Charts.rebuildAll(STATE.data, STATE);
  });

  function updateThemeIcon(theme) {
    themeBtn.textContent = theme === 'dark' ? '☀️' : '🌙';
    themeBtn.title = theme === 'dark' ? '切換至亮色模式' : '切換至暗色模式';
  }

  // ===== Tab Routing =====
  const tabBtns = document.querySelectorAll('.tab-btn');
  const modulePanels = document.querySelectorAll('.module-panel');

  function switchModule(moduleId) {
    tabBtns.forEach(btn => {
      btn.setAttribute('aria-selected', btn.dataset.module === moduleId ? 'true' : 'false');
    });
    modulePanels.forEach(panel => {
      panel.style.display = panel.id === moduleId ? '' : 'none';
    });
    STATE.currentModule = moduleId;
    window.location.hash = moduleId;
  }

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      if (!btn.disabled) switchModule(btn.dataset.module);
    });
  });

  // Hash routing on load
  const hash = window.location.hash.replace('#', '');
  if (hash && document.getElementById(hash)) {
    switchModule(hash);
  }

  // ===== Hamburger (Mobile Sidebar) =====
  const hamburgerBtn = document.getElementById('hamburgerBtn');
  const sidebar = document.getElementById('sidebar');
  hamburgerBtn.addEventListener('click', () => {
    sidebar.classList.toggle('open');
  });
  // Close sidebar when clicking main content on mobile
  document.getElementById('mainContent').addEventListener('click', () => {
    if (sidebar.classList.contains('open')) sidebar.classList.remove('open');
  });

  let dimScores = {};   // 預設空物件，確保後續 buildDimSection 不 crash
  try {
    STATE.data = await DataService.fetchData();
    const dimRows = await DataService.fetchDimScores();
    dimScores = DataService.getLatestDimScores(dimRows);
    STATE.rawData = await DataService.fetchRawData();

    // 將實際資料日期注入 DrumPicker（day 模式只跳到有資料的交易日）
    if (typeof DrumPicker !== 'undefined' && STATE.data?.scores?.MACRO_SCORE?.length) {
      const dates = STATE.data.scores.MACRO_SCORE.map(d => d.date);
      DrumPicker.setValidDates(dates);
    }

    // 建立各分數序列的日期索引 Map，供確認按鈕查指定日期分數
    STATE.scoreMaps = {};
    for (const [key, arr] of Object.entries(STATE.data.scores)) {
      STATE.scoreMaps[key] = new Map(arr.map(d => [d.date, d.value]));
    }
  } catch (err) {
    document.getElementById('mainContent').innerHTML = `
      <div class="module-placeholder">
        <div class="placeholder-icon">⚠️</div>
        <h2>資料載入失敗</h2>
        <p>找不到 dashboard_data.json<br><code style="color:var(--color-primary)">python export_dashboard_data.py</code></p>
        <p style="font-size:.78rem;color:var(--color-text-faint)">${err.message}</p>
      </div>`;
    return;
  }

  // ===== Populate Info Bar =====
  document.getElementById('infoGenAt').textContent = STATE.data.generated_at || '—';
  const latestScore = DataService.getLatestScore(STATE.data);
  if (latestScore) {
    document.getElementById('infoLatest').textContent = `${latestScore.value >= 0 ? '+' : ''}${latestScore.value.toFixed(3)} (${latestScore.date})`;
  }
  const latestRegime = DataService.getLatestRegime(STATE.data);
  if (latestRegime) {
    const regimeLabels = { 3: '寬鬆', 2: '中性偏多', 1: '中性偏保守', 0: '緊縮' };
    document.getElementById('infoRegime').textContent = `${latestRegime.value} — ${regimeLabels[latestRegime.value] || '?'}`;
  }

  // ===== Init Gauge (Section A) =====
  GaugeChart.render(STATE.data);

  // ===== Init Data Date Selector =====
  const dataYear = document.getElementById('dataYear');
  const dataMonth = document.getElementById('dataMonth');
  const dataDay = document.getElementById('dataDay');
  const dataDateConfirm = document.getElementById('dataDateConfirm');

  if (dataYear && dataMonth && dataDay && STATE.data && STATE.data.scores && STATE.data.scores.MACRO_SCORE) {
    const dates = STATE.data.scores.MACRO_SCORE.map(d => d.date).sort().reverse(); // latest first
    const dateTree = {};
    dates.forEach(d => {
      const [y, m, day] = d.split('-');
      if (!dateTree[y]) dateTree[y] = {};
      if (!dateTree[y][m]) dateTree[y][m] = [];
      if (!dateTree[y][m].includes(day)) dateTree[y][m].push(day);
    });

    const populateSelect = (select, options) => {
      select.innerHTML = options.map(opt => `<option value="${opt}">${opt}</option>`).join('');
    };

    const updateMonths = (y) => {
      if (!y || !dateTree[y]) return;
      const months = Object.keys(dateTree[y]).sort().reverse();
      populateSelect(dataMonth, months);
      updateDays(y, dataMonth.value);
    };

    const updateDays = (y, m) => {
      if (!y || !m || !dateTree[y][m]) return;
      const days = dateTree[y][m].sort().reverse();
      populateSelect(dataDay, days);
    };

    // Init with available years
    const years = Object.keys(dateTree).sort().reverse();
    populateSelect(dataYear, years);
    updateMonths(dataYear.value);

    // Cascading Event Listeners
    dataYear.addEventListener('change', () => updateMonths(dataYear.value));
    dataMonth.addEventListener('change', () => updateDays(dataYear.value, dataMonth.value));

    // Default selected date
    STATE.selectedDataDate = `${dataYear.value}-${dataMonth.value}-${dataDay.value}`;

    // 從日期字串同步到三個 select（供 DrumPicker 呼叫）
    window.syncDrumDate = (dateStr) => {
      const [y, m, d] = dateStr.split('-');
      if (!dateTree[y]) return;

      dataYear.value = y;

      const months = Object.keys(dateTree[y]).sort().reverse();
      populateSelect(dataMonth, months);
      if (dateTree[y][m]) dataMonth.value = m;

      const days = dateTree[y]?.[m] ? [...dateTree[y][m]].sort().reverse() : [];
      populateSelect(dataDay, days);
      if (dateTree[y]?.[m]?.includes(d)) dataDay.value = d;
    };

    // 初始化時將 drum 目前日期同步到 select
    if (typeof DrumPicker !== 'undefined') {
      const dObj = DrumPicker.getDate();
      const dStr = `${dObj.getFullYear()}-${String(dObj.getMonth()+1).padStart(2,'0')}-${String(dObj.getDate()).padStart(2,'0')}`;
      window.syncDrumDate(dStr);
    }

    // Drum 選日期時即時同步到 select，並高亮當前模式對應的 select
    document.addEventListener('drumDateChange', (e) => {
      if (window.syncDrumDate) window.syncDrumDate(e.detail.date);
      const mode = e.detail.mode;
      ['dataYear', 'dataMonth', 'dataDay'].forEach(id => {
        document.getElementById(id)?.classList.remove('drum-active-select');
      });
      const activeId = mode === 'year' ? 'dataYear' : mode === 'month' ? 'dataMonth' : 'dataDay';
      document.getElementById(activeId)?.classList.add('drum-active-select');
    });

    // Confirm Button
    dataDateConfirm.addEventListener('click', () => {
      const y = dataYear.value;
      const m = dataMonth.value;
      const d = dataDay.value;
      STATE.selectedDataDate = `${y}-${m}-${d}`;

      // 四大面向：從 dashboard_data.json 按日期查詢對應分數
      // POLICY_SCORE 是 DIM2/2 正規化後的值，還原要 ×2
      const SCORE_TO_DIM = {
        DIM1_SCORE: { src: 'CREDIT_SCORE',  factor: 1.0 },
        DIM2_SCORE: { src: 'POLICY_SCORE',   factor: 2.0 },
        DIM3_SCORE: null,
        DIM4_SCORE: { src: 'PRICEFX_SCORE', factor: 1.0 },
      };
      const newDimScores = {};
      for (const [dimKey, mapping] of Object.entries(SCORE_TO_DIM)) {
        if (!mapping) { newDimScores[dimKey] = null; continue; }
        const val = STATE.scoreMaps?.[mapping.src]?.get(STATE.selectedDataDate);
        newDimScores[dimKey] = val != null ? val * mapping.factor : null;
      }
      updateDimCards(newDimScores);

      // 環境總分 Gauge
      GaugeChart.renderForDate(STATE.scoreMaps, STATE.selectedDataDate);

      // Info bar
      const macroVal = STATE.scoreMaps?.MACRO_SCORE?.get(STATE.selectedDataDate);
      if (macroVal != null) {
        document.getElementById('infoLatest').textContent =
          `${macroVal >= 0 ? '+' : ''}${macroVal.toFixed(3)} (${STATE.selectedDataDate})`;
      }

      if (window.refreshActiveDimDetail) {
        window.refreshActiveDimDetail();
      }
    });
  }

  // ===== Init Dimension Scores (Section B) =====
  STATE.currentDimScores = { ...dimScores };
  buildDimSection(dimScores);

  // ===== Init Sub-indicator Pills (Section D) =====
  const subKeys = Object.keys(STATE.data.sub_scores);
  subKeys.slice(0, 3).forEach(k => STATE.activeSubs.add(k));
  buildSubPills(subKeys);

  // ===== Init Charts (Section C & D) =====
  Charts.buildChartC(STATE.data, STATE);
  Charts.buildChartD(STATE.data, STATE);

  // ===== Init Animations =====
  Animations.init();

  // ===== Formula Modal 開關 =====
  const dimFormulaBtn = document.getElementById('dimFormulaBtn');
  const dimFormulaModal = document.getElementById('dimFormulaModal');
  const dimFormulaClose = document.getElementById('dimFormulaClose');

  dimFormulaBtn.addEventListener('click', () => {
    dimFormulaModal.style.display = 'flex';
  });
  dimFormulaClose.addEventListener('click', () => {
    dimFormulaModal.style.display = 'none';
  });
  // 點外部關閉
  dimFormulaModal.addEventListener('click', e => {
    if (e.target === dimFormulaModal) dimFormulaModal.style.display = 'none';
  });
  // ESC 關閉
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') dimFormulaModal.style.display = 'none';
  });

  // ===== Time Range Buttons (sidebar + inline) =====
  function bindRangeButtons() {
    document.querySelectorAll('.btn-range[data-range]').forEach(btn => {
      btn.addEventListener('click', () => {
        // Update active state on ALL range buttons
        document.querySelectorAll('.btn-range[data-range]').forEach(b => {
          b.setAttribute('aria-pressed', 'false');
          b.classList.remove('active');
        });
        // Set the clicked value on all matching buttons
        document.querySelectorAll(`.btn-range[data-range="${btn.dataset.range}"]`).forEach(b => {
          b.setAttribute('aria-pressed', 'true');
          b.classList.add('active');
        });

        STATE.range = btn.dataset.range;

        const customEl = document.getElementById('customRange');
        if (STATE.range === 'CUSTOM') {
          customEl.classList.add('visible');
        } else {
          customEl.classList.remove('visible');
          Charts.updateChartC(STATE.data, STATE);
          Charts.updateChartD(STATE.data, STATE);
        }
      });
    });
  }
  bindRangeButtons();

  // Custom date apply
  document.getElementById('applyCustom').addEventListener('click', () => {
    STATE.customFrom = document.getElementById('dateFrom').value || null;
    STATE.customTo = document.getElementById('dateTo').value || null;
    Charts.updateChartC(STATE.data, STATE);
    Charts.updateChartD(STATE.data, STATE);
  });

  // ===== Index Toggle Pills (sidebar + inline) =====
  function bindIndexToggles() {
    document.querySelectorAll('.toggle-pill[data-index]').forEach(btn => {
      btn.addEventListener('click', () => {
        const key = btn.dataset.index;
        const isActive = STATE.activeIndices.has(key);
        if (isActive) {
          STATE.activeIndices.delete(key);
        } else {
          STATE.activeIndices.add(key);
        }
        // Sync ALL matching toggles
        document.querySelectorAll(`.toggle-pill[data-index="${key}"]`).forEach(b => {
          b.classList.toggle('active', !isActive);
        });
        Charts.updateChartC(STATE.data, STATE);
      });
    });
  }
  bindIndexToggles();


  // ===== Mini Gauge SVG 產生器 =====
  function _buildMiniGaugeSVG(score, color) {
    const cx = 60, cy = 62, r = 42;
    const clamped = Math.max(-1, Math.min(1, score));
    const angleRad = clamped * (Math.PI / 2);
    const needleLen = 31;
    const nx = (cx + needleLen * Math.sin(angleRad)).toFixed(2);
    const ny = (cy - needleLen * Math.cos(angleRad)).toFixed(2);
    const arcLen = (Math.PI * r).toFixed(2);
    const filled = ((clamped + 1) / 2 * Math.PI * r).toFixed(2);
    const dashOff = (Math.PI * r - filled).toFixed(2);
    const x1 = cx - r;
    const x2 = cx + r;

    return `
      <svg viewBox="0 0 120 75" class="dim-gauge-svg" aria-hidden="true">
        <path d="M ${x1} ${cy} A ${r} ${r} 0 0 1 ${x2} ${cy}"
          fill="none" stroke="var(--color-border)"
          stroke-width="7" stroke-linecap="round"/>
        <path d="M ${x1} ${cy} A ${r} ${r} 0 0 1 ${x2} ${cy}"
          fill="none" stroke="${color}" stroke-width="7"
          stroke-linecap="round" opacity=".75"
          stroke-dasharray="${arcLen}" stroke-dashoffset="${dashOff}"/>
        <line x1="${cx}" y1="${cy}" x2="${nx}" y2="${ny}"
          stroke="var(--color-text)" stroke-width="2.5" stroke-linecap="round"/>
        <circle cx="${cx}" cy="${cy}" r="4.5" fill="var(--color-text)"/>
      </svg>`;
  }

  // ===== Formula Modal 表格填入 =====
  function _fillFormulaModal(scores) {
    const tbody = document.getElementById('dimFormulaTableBody');
    if (!tbody) return;

    tbody.innerHTML = DIMS.map(dim => {
      const s = scores[dim.key] ?? null;
      const sStr = s !== null ? `${s >= 0 ? '+' : ''}${s.toFixed(3)}` : '—';
      const sCls = s > 0 ? 'positive' : s < 0 ? 'negative' : '';

      return `
        <tr style="border-bottom:1px solid var(--color-divider)">
          <td style="padding:10px 8px;font-weight:500;white-space:nowrap">
            ${dim.label}（${dim.name}）
          </td>
          <td style="padding:10px 8px;color:var(--color-primary);font-weight:600">
            ${dim.weight}
          </td>
          <td style="padding:10px 8px;color:var(--color-text-muted);
                     font-size:.82rem;line-height:1.7">
            ${dim.composition.join('<br>')}
          </td>
          <td style="padding:10px 8px;text-align:right;font-weight:600"
              class="${sCls} tabular-nums">${sStr}
          </td>
        </tr>`;
    }).join('');
  }

  // ===== Section B: buildDimSection =====
  function buildDimSection(scores) {
    const container = document.getElementById('dimGaugesContainer');
    container.innerHTML = '';

    DIMS.forEach((dim, i) => {
      const s = scores[dim.key] ?? null;
      const sStr = s !== null ? `${s >= 0 ? '+' : ''}${s.toFixed(3)}` : '—';
      const sCls = s !== null ? (s > 0 ? 'positive' : s < 0 ? 'negative' : 'neutral') : 'neutral';
      const gaugeScore = s !== null ? s : 0;

      const card = document.createElement('div');
      card.className = 'dim-gauge-card';
      card.innerHTML = `
        <span class="dim-score-top ${sCls}">${sStr}</span>
        ${_buildMiniGaugeSVG(gaugeScore, dim.color)}
        <button class="dim-label-btn" data-dim-idx="${i}">
          ${dim.label}<small>${dim.name}</small>
        </button>`;
      container.appendChild(card);
    });

    // ── 展開/收合 Detail Panel ──
    let activeDimIdx = null;
    const detailPanel = document.getElementById('dimDetailPanel');
    const detailContent = document.getElementById('dimDetailContent');

    window.refreshActiveDimDetail = () => {
      if (activeDimIdx === null) return;
      const dim = DIMS[activeDimIdx];
      const s = STATE.currentDimScores?.[dim.key] ?? null;
      const sStr = s !== null ? `${s >= 0 ? '+' : ''}${s.toFixed(3)}` : '—';
      const sCls = s > 0 ? 'positive' : s < 0 ? 'negative' : '';

      // Generate Raw Indicators HTML
      let indicatorsHtml = '';
      const indDefs = RAW_INDICATORS[dim.key] || [];
      const selectedDate = STATE.selectedDataDate;
      const dateData = (STATE.rawData && STATE.rawData[selectedDate]) ? STATE.rawData[selectedDate] : {};

      if (indDefs.length > 0) {
        indicatorsHtml = indDefs.map((ind, idx) => {
          let val = dateData[ind.key];
          if (val === undefined && ind.altKey) val = dateData[ind.altKey];
          const valStr = val !== undefined ? Number(val).toLocaleString(undefined, {maximumFractionDigits: 4}) : '—';
          const isLast = idx === indDefs.length - 1;
          return `
            <div style="display:flex; justify-content:space-between; align-items:center; padding: 6px 0; ${isLast ? '' : 'border-bottom: 1px dashed var(--color-divider);'}">
              <span style="color:var(--color-text);font-weight:500;">${ind.label}</span>
              <span class="tabular-nums" style="font-weight:600; color:var(--color-primary);">${valStr}</span>
            </div>
          `;
        }).join('');
      } else {
        indicatorsHtml = `<div style="color:var(--color-text-muted);font-size:.83rem;padding: 6px 0;">尚無詳細數據</div>`;
      }

      detailContent.innerHTML = `
        <h4 style="margin-bottom:12px;font-size:.95rem">
          ${dim.label}（${dim.name}）— ${selectedDate} 詳細指標數據
        </h4>
        <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px">
          <div class="info-chip">
            <span class="chip-label">大環境總分佔比最新分數</span>
            <span class="chip-value ${sCls} tabular-nums">${sStr} (${dim.weight})</span>
          </div>
        </div>
        <div style="padding:14px 16px;background:var(--color-surface-2);
                    border-radius:10px;border:1px dashed var(--color-border);
                    color:var(--color-text-muted);font-size:.83rem;line-height:1.7">
          <div style="margin-bottom: 8px; font-weight: 600; color: var(--color-primary);">📊 底層原始數據 (${selectedDate})</div>
          <div style="margin-bottom: 12px;">
            ${indicatorsHtml}
          </div>
          <div style="font-size: .78rem; opacity: 0.8; border-top: 1px dashed var(--color-divider); padding-top: 8px;">
            組成：${dim.composition.join('　/　')}
          </div>
        </div>`;
    };

    container.addEventListener('click', e => {
      const btn = e.target.closest('.dim-label-btn');
      if (!btn) return;

      const i = parseInt(btn.dataset.dimIdx, 10);
      const allBtns = container.querySelectorAll('.dim-label-btn');

      if (activeDimIdx === i) {
        // ── 收合 ──
        activeDimIdx = null;
        detailPanel.style.display = 'none';
        allBtns.forEach(b => b.classList.remove('active'));
      } else {
        // ── 展開 / 切換 ──
        activeDimIdx = i;
        allBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        window.refreshActiveDimDetail();

        // 重新觸發 CSS 動畫
        detailPanel.style.display = 'none';
        requestAnimationFrame(() => { detailPanel.style.display = 'block'; });
      }
    });

    // 填入 Formula Modal 表格
    _fillFormulaModal(scores);
  }

  // ===== Section B: 更新四大面向分數卡片 =====
  function updateDimCards(newScores) {
    STATE.currentDimScores = newScores;
    const container = document.getElementById('dimGaugesContainer');
    DIMS.forEach((dim, i) => {
      const s = newScores[dim.key] ?? null;
      const sStr = s !== null ? `${s >= 0 ? '+' : ''}${s.toFixed(3)}` : '—';
      const sCls = s !== null ? (s > 0 ? 'positive' : s < 0 ? 'negative' : 'neutral') : 'neutral';
      const gaugeScore = s !== null ? s : 0;

      const card = container.querySelectorAll('.dim-gauge-card')[i];
      if (!card) return;

      const scoreEl = card.querySelector('.dim-score-top');
      if (scoreEl) {
        scoreEl.textContent = sStr;
        scoreEl.className = `dim-score-top ${sCls}`;
      }

      const oldSvg = card.querySelector('.dim-gauge-svg');
      if (oldSvg) {
        const tmp = document.createElement('div');
        tmp.innerHTML = _buildMiniGaugeSVG(gaugeScore, dim.color);
        oldSvg.replaceWith(tmp.firstElementChild);
      }
    });
    _fillFormulaModal(newScores);
    if (window.refreshActiveDimDetail) window.refreshActiveDimDetail();
  }

  // ===== Sub-indicator Pill Builder =====
  function buildSubPills(subKeys) {
    const container = document.getElementById('subPills');
    subKeys.forEach((key, idx) => {
      const color = Charts.SUB_COLORS[idx % Charts.SUB_COLORS.length];
      const btn = document.createElement('button');
      btn.className = 'toggle-pill' + (STATE.activeSubs.has(key) ? ' active' : '');
      btn.dataset.sub = key;
      btn.innerHTML = `<span class="dot" style="background:${color}"></span>${Charts.SUB_LABELS[key] || key}`;
      btn.addEventListener('click', () => {
        if (STATE.activeSubs.has(key)) {
          STATE.activeSubs.delete(key);
          btn.classList.remove('active');
        } else {
          STATE.activeSubs.add(key);
          btn.classList.add('active');
        }
        Charts.updateChartD(STATE.data, STATE);
      });
      container.appendChild(btn);
    });
  }

})();
