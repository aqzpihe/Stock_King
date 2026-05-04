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

  // ===== Load Data =====
  try {
    STATE.data = await DataService.fetchData();
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

  // ===== Init KPI Cards (Section B) =====
  buildKPICards(STATE.data);

  // ===== Init Sub-indicator Pills (Section D) =====
  const subKeys = Object.keys(STATE.data.sub_scores);
  subKeys.slice(0, 3).forEach(k => STATE.activeSubs.add(k));
  buildSubPills(subKeys);

  // ===== Init Charts (Section C & D) =====
  Charts.buildChartC(STATE.data, STATE);
  Charts.buildChartD(STATE.data, STATE);

  // ===== Init Animations =====
  Animations.init();

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

  // ===== KPI Card Builder =====
  function buildKPICards(data) {
    const grid = document.getElementById('kpiGrid');
    grid.innerHTML = '';
    const subScores = DataService.getLatestSubScores(data);

    for (const [key, value] of Object.entries(subScores)) {
      if (value === null) continue;
      const label = Charts.SUB_LABELS[key] || key.replace('SUB_', '');
      const delta = DataService.getDelta(data.sub_scores[key], 30);
      const recentData = DataService.getRecent(data.sub_scores[key], 60);
      const recentValues = recentData.map(d => d.value);
      const idx = Object.keys(subScores).indexOf(key);
      const color = Charts.SUB_COLORS[idx % Charts.SUB_COLORS.length];

      const cls = value > 0 ? 'positive' : value < 0 ? 'negative' : 'neutral';
      const deltaStr = delta !== null ? (delta >= 0 ? `▲ ${delta.toFixed(2)}` : `▼ ${Math.abs(delta).toFixed(2)}`) : '';
      const deltaCls = delta > 0 ? 'up' : delta < 0 ? 'down' : '';

      const card = document.createElement('div');
      card.className = 'kpi-card reveal';
      card.innerHTML = `
        <div class="kpi-label">${label}</div>
        <div class="kpi-value ${cls} tabular-nums">${value >= 0 ? '+' : ''}${value.toFixed(1)}</div>
        ${deltaStr ? `<div class="kpi-delta ${deltaCls}">${deltaStr} <span style="color:var(--color-text-faint);font-weight:400">vs 30d</span></div>` : ''}
        <div class="kpi-sparkline">${Animations.createSparklineSVG(recentValues, color)}</div>
      `;
      grid.appendChild(card);
    }
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
