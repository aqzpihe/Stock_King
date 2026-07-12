/* ================================================================
   charts.js — Chart.js v4 互動圖表（C: 雙軸, D: 子指標）
   ================================================================ */

const Charts = (() => {
  let chartC = null;
  let chartD = null;

  // --- Palette ---
  const INDEX_META = {
    SP500:     { label: 'S&P 500',      color: '#C94F4F' },
    NASDAQCOM: { label: 'NASDAQ',        color: '#7A93B8' },
    DJIA:      { label: 'DJI',           color: '#C9A227' },
    RUT:       { label: 'Russell 2000',  color: '#9A9DA6' },
  };

  const SUB_COLORS = ['#8B2E2E','#7A93B8','#C9A227','#C94F4F','#9A9DA6','#A03636','#5A7499'];
  const SUB_LABELS = {
    SUB_SPREAD_CP_TB6:    'CP-TB6 利差',
    SUB_SPREAD_PRIME_TB6: 'Prime-TB6 利差',
    SUB_SPREAD_BAA_GS10:  'Baa-GS10 利差',
    SUB_FFR:              '聯邦基金利率',
    SUB_INF_YOY:          '通膨 YoY',
    SUB_FX_CHG:           '匯率變動',
    SUB_FX_VOL:           '匯率波動',
  };

  // --- Crosshair Plugin ---
  const crosshairPlugin = {
    id: 'crosshair',
    afterEvent(chart, args) {
      if (args.event.type === 'mousemove') {
        chart._crosshair = { x: args.event.x, y: args.event.y };
        chart.draw();
      } else if (args.event.type === 'mouseout') {
        chart._crosshair = null;
        chart.draw();
      }
    },
    afterDraw(chart) {
      if (chart._crosshair && chart.tooltip?._active?.length) {
        const x = chart.tooltip._active[0].element.x;
        const y = chart._crosshair.y;
        const ctx = chart.ctx;
        const { top, bottom, left, right } = chart.chartArea;
        if (y < top || y > bottom) return;
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(x, top);
        ctx.lineTo(x, bottom);
        ctx.moveTo(left, y);
        ctx.lineTo(right, y);
        ctx.lineWidth = 1;
        ctx.strokeStyle = 'rgba(192,57,43,0.4)';
        ctx.setLineDash([4, 4]);
        ctx.stroke();
        ctx.restore();
      }
    }
  };

  // --- Tooltip styling ---
  function tooltipConfig() {
    const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
    return {
      backgroundColor: isDark ? 'rgba(17,17,17,0.95)' : 'rgba(249,248,246,0.95)',
      titleColor: isDark ? '#E8E6E3' : '#26272B',
      bodyColor: isDark ? '#E8E6E3' : '#26272B',
      borderColor: isDark ? '#2A2D34' : '#D8D5CF',
      borderWidth: 1,
      padding: 12,
      cornerRadius: 8,
      bodyFont: { family: 'Inter', size: 12 },
      titleFont: { family: 'Inter', size: 12, weight: '600' },
    };
  }

  function scaleColor() {
    const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
    return {
      grid: isDark ? 'rgba(42,42,42,0.6)' : 'rgba(208,207,204,0.5)',
      tick: isDark ? '#9A9DA6' : '#6B6E78',
    };
  }

  // ============================== Chart C ==============================
  function buildChartC(data, state) {
    const ctx = document.getElementById('chartC').getContext('2d');
    const scoreData = filterData(data.scores.MACRO_SCORE, state);

    const datasets = [{
      label: '大環境分數',
      data: scoreData.map(d => ({ x: d.date, y: d.value })),
      borderColor: '#8B2E2E',
      backgroundColor: 'rgba(192,57,43,0.06)',
      yAxisID: 'yScore',
      borderWidth: 2.5,
      pointRadius: 0,
      pointHoverRadius: 4,
      tension: 0.3,
      fill: false,
      order: 0,
    }];

    for (const [key, meta] of Object.entries(INDEX_META)) {
      const raw = data.indices[key];
      if (!raw) continue;
      datasets.push({
        label: meta.label,
        data: filterData(raw, state).map(d => ({ x: d.date, y: d.value })),
        borderColor: meta.color,
        backgroundColor: meta.color + '14',
        yAxisID: 'yIndex',
        borderWidth: 1.8,
        pointRadius: 0,
        pointHoverRadius: 3,
        tension: 0.3,
        fill: false,
        hidden: !state.activeIndices.has(key),
        order: 1,
      });
    }

    if (chartC) chartC.destroy();
    const sc = scaleColor();

    chartC = new Chart(ctx, {
      type: 'line',
      data: { datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          tooltip: tooltipConfig(),
          legend: {
            labels: { color: sc.tick, font: { family: 'Inter', size: 11 }, usePointStyle: true, pointStyle: 'circle' },
          },
        },
        scales: {
          x: {
            type: 'time',
            time: { unit: 'month', tooltipFormat: 'yyyy-MM-dd' },
            grid: { color: sc.grid },
            ticks: { color: sc.tick, font: { family: 'Inter', size: 10 }, maxTicksLimit: 12 },
          },
          yScore: {
            type: 'linear', position: 'left',
            title: { display: true, text: '大環境分數', color: '#C94F4F', font: { family: 'Space Grotesk', size: 11 } },
            grid: { color: sc.grid },
            ticks: { color: '#C94F4F', font: { family: 'IBM Plex Mono', size: 10 } },
          },
          yIndex: {
            type: 'linear', position: 'right',
            title: { display: true, text: '指數', color: sc.tick, font: { family: 'Inter', size: 11 } },
            grid: { drawOnChartArea: false },
            ticks: { color: sc.tick, font: { family: 'Inter', size: 10 } },
          },
        },
      },
      plugins: [crosshairPlugin],
    });
  }

  function updateChartC(data, state) {
    if (!chartC) return buildChartC(data, state);
    const scoreData = filterData(data.scores.MACRO_SCORE, state);
    chartC.data.datasets[0].data = scoreData.map(d => ({ x: d.date, y: d.value }));

    let i = 1;
    for (const key of Object.keys(INDEX_META)) {
      const raw = data.indices[key];
      if (!raw) continue;
      const ds = chartC.data.datasets[i];
      if (ds) {
        ds.data = filterData(raw, state).map(d => ({ x: d.date, y: d.value }));
        ds.hidden = !state.activeIndices.has(key);
      }
      i++;
    }
    chartC.update('active');
  }

  // ============================== Chart D ==============================
  function buildChartD(data, state) {
    const ctx = document.getElementById('chartD').getContext('2d');
    const datasets = [];
    const subKeys = Object.keys(data.sub_scores);

    subKeys.forEach((key, idx) => {
      const raw = data.sub_scores[key];
      const color = SUB_COLORS[idx % SUB_COLORS.length];
      datasets.push({
        label: SUB_LABELS[key] || key,
        data: filterData(raw, state).map(d => ({ x: d.date, y: d.value })),
        borderColor: color,
        backgroundColor: color + '14',
        borderWidth: 1.8,
        pointRadius: 0,
        pointHoverRadius: 3,
        tension: 0.3,
        fill: 'origin',
        hidden: !state.activeSubs.has(key),
      });
    });

    if (chartD) chartD.destroy();
    const sc = scaleColor();

    chartD = new Chart(ctx, {
      type: 'line',
      data: { datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          tooltip: tooltipConfig(),
          legend: {
            labels: { color: sc.tick, font: { family: 'Inter', size: 11 }, usePointStyle: true, pointStyle: 'circle' },
          },
        },
        scales: {
          x: {
            type: 'time',
            time: { unit: 'month', tooltipFormat: 'yyyy-MM-dd' },
            grid: { color: sc.grid },
            ticks: { color: sc.tick, font: { family: 'Inter', size: 10 }, maxTicksLimit: 12 },
          },
          y: {
            title: { display: true, text: '子指標分數', color: sc.tick, font: { family: 'Inter', size: 11 } },
            grid: { color: sc.grid },
            ticks: { color: sc.tick, font: { family: 'Inter', size: 10 } },
          },
        },
      },
      plugins: [crosshairPlugin],
    });
  }

  function updateChartD(data, state) {
    if (!chartD) return buildChartD(data, state);
    const subKeys = Object.keys(data.sub_scores);
    subKeys.forEach((key, idx) => {
      const ds = chartD.data.datasets[idx];
      if (ds) {
        ds.data = filterData(data.sub_scores[key], state).map(d => ({ x: d.date, y: d.value }));
        ds.hidden = !state.activeSubs.has(key);
      }
    });
    chartD.update('active');
  }

  // --- Rebuild both charts (e.g. on theme change) ---
  function rebuildAll(data, state) {
    buildChartC(data, state);
    buildChartD(data, state);
  }

  // --- Filter helper ---
  function filterData(arr, state) {
    const { from, to } = getDateRange(state);
    return arr.filter(d => d._d >= from && d._d <= to);
  }

  function getDateRange(state) {
    const now = new Date();
    let from;
    switch (state.range) {
      case '1M':  from = new Date(now); from.setMonth(from.getMonth() - 1); break;
      case '3M':  from = new Date(now); from.setMonth(from.getMonth() - 3); break;
      case '6M':  from = new Date(now); from.setMonth(from.getMonth() - 6); break;
      case '1Y':  from = new Date(now); from.setFullYear(from.getFullYear() - 1); break;
      case '3Y':  from = new Date(now); from.setFullYear(from.getFullYear() - 3); break;
      case 'ALL': from = new Date('2000-01-01'); break;
      case 'CUSTOM':
        from = state.customFrom ? new Date(state.customFrom) : new Date('2000-01-01');
        return { from, to: state.customTo ? new Date(state.customTo) : now };
      default: from = new Date(now); from.setFullYear(from.getFullYear() - 1);
    }
    return { from, to: now };
  }

  // --- Public API ---
  return {
    buildChartC, updateChartC,
    buildChartD, updateChartD,
    rebuildAll,
    SUB_LABELS, SUB_COLORS, INDEX_META,
  };
})();
