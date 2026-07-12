/* ================================================================
   technical.js — 指標屬性圖譜 + 策略評分
   §5 加權重心定位 / §6 面向覆蓋度 + 偏食檢測
   ================================================================ */
(function () {
  'use strict';

  const AXES = ['trend', 'momentum', 'volatility', 'volume', 'support_resistance', 'cycle'];
  const AXIS_LABELS = { trend: '趨勢', momentum: '動能', volatility: '波動率', volume: '量能', support_resistance: '支撐壓力', cycle: '週期' };
  const AXIS_COLORS = { trend: '#8B2E2E', momentum: '#7A93B8', volatility: '#C94F4F', volume: '#9A9DA6', support_resistance: '#C9A227', cycle: '#5A7499' };
  const PILLARS = ['trend', 'momentum', 'volatility', 'volume'];
  const THRESHOLD = 0.5;

  // 淺色主題背景接近白色，寫死的白色格線/連線在切換後會直接隱形——一律透過此 helper 取色
  function isDarkTheme() {
    return document.documentElement.getAttribute('data-theme') !== 'light';
  }
  function gridStroke(alpha) {
    return isDarkTheme() ? `rgba(154,157,166,${alpha})` : `rgba(107,110,120,${alpha})`;
  }

  // ── 3D geometry: 6 axes = 6 vertices of a triangular prism (top 3 / bottom 3) ──
  const MAP_SCALE = 1.5; // 整體放大倍率（畫布尺寸＋鏡頭焦距一起放，畫面線性放大）
  const MAP_W = 500 * MAP_SCALE, MAP_H = 500 * MAP_SCALE, CX = 250 * MAP_SCALE, CY = 250 * MAP_SCALE;
  const PRISM_R = 140, PRISM_H = 240; // 模型空間座標，不隨畫面放大縮放
  const CAM_DIST = 600, FOCAL = 520 * MAP_SCALE;
  const BASE_SCALE = FOCAL / CAM_DIST;

  const anchors = AXES.map((ax, i) => {
    const top = i < 3;
    const angle = Math.PI / 2 + (i % 3) * (2 * Math.PI / 3);
    return { ax, x: PRISM_R * Math.cos(angle), y: top ? PRISM_H / 2 : -PRISM_H / 2, z: PRISM_R * Math.sin(angle) };
  });

  let rotY = Math.PI / 6, rotX = Math.PI / 7; // yaw, pitch — 拖曳圖譜可旋轉

  function rotate3d(p) {
    const cosY = Math.cos(rotY), sinY = Math.sin(rotY);
    const x1 = p.x * cosY + p.z * sinY;
    const z1 = -p.x * sinY + p.z * cosY;
    const cosX = Math.cos(rotX), sinX = Math.sin(rotX);
    return { x: x1, y: p.y * cosX - z1 * sinX, z: p.y * sinX + z1 * cosX };
  }

  function project(p) {
    const r = rotate3d(p);
    const camZ = r.z + CAM_DIST;
    const scale = FOCAL / camZ;
    return { x: CX + r.x * scale, y: CY - r.y * scale, scale, depth: camZ };
  }

  // §5.2 weighted centroid (3D; projected to screen at draw time)
  function calcPos(scores) {
    let sumW = 0, px = 0, py = 0, pz = 0;
    AXES.forEach((ax, i) => {
      const w = scores[ax] || 0;
      sumW += w; px += w * anchors[i].x; py += w * anchors[i].y; pz += w * anchors[i].z;
    });
    return sumW > 0 ? { x: px / sumW, y: py / sumW, z: pz / sumW } : { x: 0, y: 0, z: 0 };
  }

  let indicators = [];
  let selected = new Set();
  let previewedId = null; // item currently shown in the left detail panel (not yet in the basket)
  // ponytail: store hit positions (screen space, drawn order) to avoid recalc on every click
  let hitPositions = [];

  // ── View switch: 3D gravity graph ↔ small-card radar grid ──
  let viewMode = '3d';
  const VIEW_HINTS = {
    '3d': '拖曳旋轉檢視 ／ 點擊球體查看說明，於左側「新增至策略」加入 ／ 六頂點（三角柱）為教科書錨點',
    grid: '點擊卡片查看說明，於左側「新增至策略」加入',
  };

  function setViewMode(mode) {
    viewMode = mode;
    const canvas = document.getElementById('tech-map-canvas');
    const grid = document.getElementById('tech-grid-view');
    if (canvas) canvas.style.display = mode === '3d' ? '' : 'none';
    if (grid) grid.style.display = mode === 'grid' ? '' : 'none';
    document.querySelectorAll('.tech-view-btn').forEach(b => {
      const active = b.dataset.view === mode;
      b.classList.toggle('active', active);
      b.setAttribute('aria-selected', String(active));
    });
    const hint = document.getElementById('tech-map-hint');
    if (hint) hint.textContent = VIEW_HINTS[mode];
    render();
  }

  async function init() {
    try {
      const resp = await fetch('./3-技術指標/indicators.json');
      const data = await resp.json();
      indicators = data.indicators;
      checkSpecCoverage();
      render();
    } catch (e) {
      console.error('technical.js: failed to load indicators.json', e);
    }
  }

  // 新增指標需同時維護 indicators.json（分類/評分）與 backtest.js 的 SPECS（怎麼算/怎麼交易），
  // id 對不上時原本會靜默失效（球不見或選了跑不出熱力圖），這裡在載入時直接吼出來。
  function checkSpecCoverage() {
    if (!window.Backtest) { console.warn('technical.js: backtest.js 尚未載入，無法回測任何指標'); return; }
    const specIds = Object.keys(window.Backtest.SPECS);
    const jsonIds = indicators.map(i => i.id);
    jsonIds.filter(id => !specIds.includes(id)).forEach(id =>
      console.warn(`technical.js: indicators.json 的 "${id}" 沒有對應的 backtest.js SPECS，無法回測/疊圖`));
    specIds.filter(id => !jsonIds.includes(id)).forEach(id =>
      console.warn(`technical.js: backtest.js SPECS 的 "${id}" 沒有對應的 indicators.json 項目，圖譜上不會出現`));
  }

  function render() {
    if (viewMode === '3d') drawMap(); else renderGridView();
    renderBasket();
    renderRadar();
    if (previewedId) renderIndicatorDetail(previewedId);
  }

  // ── Map canvas ──
  function drawMap() {
    const canvas = document.getElementById('tech-map-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    canvas.width = MAP_W * dpr;
    canvas.height = MAP_H * dpr;
    canvas.style.width = MAP_W + 'px';
    canvas.style.maxWidth = '100%';
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, MAP_W, MAP_H);

    // prism wireframe (top triangle / bottom triangle / 3 verticals)
    const ap = anchors.map(project);
    const edge = (a, b) => { ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); };
    ctx.strokeStyle = gridStroke(0.1);
    ctx.lineWidth = MAP_SCALE;
    edge(ap[0], ap[1]); edge(ap[1], ap[2]); edge(ap[2], ap[0]);
    edge(ap[3], ap[4]); edge(ap[4], ap[5]); edge(ap[5], ap[3]);
    edge(ap[0], ap[3]); edge(ap[1], ap[4]); edge(ap[2], ap[5]);

    // indicator balls: project + depth-sort (painter's algorithm, far → near)
    hitPositions = [];
    const balls = indicators
      .map(ind => ({ ind, sp: project(calcPos(ind.facet_scores)) }))
      .sort((a, b) => b.sp.depth - a.sp.depth);

    balls.forEach(({ ind, sp }) => {
      const r = Math.max(6 * MAP_SCALE, 14 * MAP_SCALE * (sp.scale / BASE_SCALE));
      hitPositions.push({ id: ind.id, x: sp.x, y: sp.y, r });
      const isSel = selected.has(ind.id);
      const isPreview = previewedId === ind.id;

      // connection lines (§5.3 threshold ≥ 0.3) — 粗細＋透明度依分數線性增加，各自封頂避免分數 1.0 時線條過度搶眼
      AXES.forEach((ax, i) => {
        const score = ind.facet_scores[ax] || 0;
        if (score < 0.3) return;
        const t = Math.min(1, (score - 0.3) / 0.7); // 0.3→0, 1.0→1
        ctx.beginPath();
        ctx.moveTo(sp.x, sp.y);
        ctx.lineTo(ap[i].x, ap[i].y);
        ctx.strokeStyle = gridStroke(0.15 + t * 0.45); // 0.15 .. 0.6
        ctx.lineWidth = MAP_SCALE * (1 + t * 2); // 1px .. 3px（再依畫面放大倍率縮放）
        ctx.stroke();
      });

      // ball (size shrinks with perspective depth)
      ctx.beginPath();
      ctx.arc(sp.x, sp.y, r, 0, 2 * Math.PI);
      ctx.fillStyle = isSel ? '#8B2E2E' : '#1B1D22';
      ctx.fill();
      ctx.strokeStyle = isSel ? '#C94F4F' : (isPreview ? '#C9A227' : '#2A2D34');
      ctx.lineWidth = (isPreview ? 3 : 2) * MAP_SCALE;
      ctx.stroke();

      ctx.fillStyle = isSel ? '#E8E6E3' : '#9A9DA6';
      ctx.font = `${isSel ? 700 : 500} ${Math.max(7 * MAP_SCALE, 9 * MAP_SCALE * (sp.scale / BASE_SCALE))}px Inter, sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(ind.name_en.slice(0, 7), sp.x, sp.y);
    });

    // anchor nodes (drawn last, always on top)
    anchors.forEach((a, i) => {
      const p = ap[i];
      ctx.beginPath();
      ctx.arc(p.x, p.y, 7 * MAP_SCALE * (p.scale / BASE_SCALE), 0, 2 * Math.PI);
      ctx.fillStyle = AXIS_COLORS[a.ax];
      ctx.fill();

      const lx = CX + (p.x - CX) * 1.18, ly = CY + (p.y - CY) * 1.18;
      ctx.fillStyle = AXIS_COLORS[a.ax];
      ctx.font = `600 ${12 * MAP_SCALE}px Inter, sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(AXIS_LABELS[a.ax], lx, ly);
    });
  }

  // ── Mode 2: small-card radar grid (one mini hexagon radar per indicator) ──
  function miniRadarSvg(scores) {
    const W = 120, H = 108, CR = 40, CCX = 60, CCY = 52;
    const angle = i => Math.PI / 2 - i * (2 * Math.PI / 6);
    const rings = [0.5, 1.0].map(f => {
      const pts = AXES.map((_, i) => `${CCX + CR * f * Math.cos(angle(i))},${CCY - CR * f * Math.sin(angle(i))}`).join(' ');
      return `<polygon points="${pts}" fill="none" stroke="${gridStroke(0.1)}" stroke-width="1"/>`;
    }).join('');
    const spokes = AXES.map((_, i) =>
      `<line x1="${CCX}" y1="${CCY}" x2="${CCX + CR * Math.cos(angle(i))}" y2="${CCY - CR * Math.sin(angle(i))}" stroke="${gridStroke(0.12)}"/>`
    ).join('');
    const pts = AXES.map((ax, i) => {
      const r = (scores[ax] || 0) * CR;
      return `${CCX + r * Math.cos(angle(i))},${CCY - r * Math.sin(angle(i))}`;
    }).join(' ');
    return `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
      ${rings}${spokes}
      <polygon points="${pts}" fill="rgba(201,79,79,0.15)" stroke="#C94F4F" stroke-width="1.5"/>
    </svg>`;
  }

  function renderGridView() {
    const el = document.getElementById('tech-grid-view');
    if (!el) return;
    el.innerHTML = indicators.map(ind => `
      <div class="tech-grid-card${selected.has(ind.id) ? ' selected' : ''}${previewedId === ind.id ? ' previewed' : ''}" data-id="${ind.id}">
        ${miniRadarSvg(ind.facet_scores)}
        <div class="tech-grid-card-name">${ind.name}</div>
        <div class="tech-grid-card-en">${ind.name_en}</div>
      </div>`).join('');
    el.querySelectorAll('.tech-grid-card').forEach(card =>
      card.addEventListener('click', () => {
        previewedId = card.dataset.id;
        renderGridView();
        renderIndicatorDetail(previewedId);
      })
    );
  }

  // ── Drag to rotate / click (no-drag) to preview in the sidebar ──
  let dragging = false, dragMoved = false, lastPX = 0, lastPY = 0;

  function onPointerDown(e) {
    dragging = true; dragMoved = false;
    lastPX = e.clientX; lastPY = e.clientY;
    const canvas = document.getElementById('tech-map-canvas');
    if (canvas) canvas.style.cursor = 'grabbing';
  }
  function onPointerMove(e) {
    if (!dragging) return;
    const dx = e.clientX - lastPX, dy = e.clientY - lastPY;
    if (Math.abs(dx) + Math.abs(dy) > 3) dragMoved = true;
    rotY += dx * 0.008;
    rotX = Math.max(-1.3, Math.min(1.3, rotX - dy * 0.008));
    lastPX = e.clientX; lastPY = e.clientY;
    drawMap();
  }
  function onPointerUp(e) {
    const canvas = document.getElementById('tech-map-canvas');
    if (canvas) canvas.style.cursor = 'grab';
    if (dragging && !dragMoved) handleMapClick(e);
    dragging = false;
  }

  function handleMapClick(e) {
    const canvas = document.getElementById('tech-map-canvas');
    const rect = canvas.getBoundingClientRect();
    const scaleX = MAP_W / rect.width;
    const mx = (e.clientX - rect.left) * scaleX;
    const my = (e.clientY - rect.top) * scaleX;

    // topmost (nearest) ball drawn last, so hit-test from the end
    for (let i = hitPositions.length - 1; i >= 0; i--) {
      const p = hitPositions[i];
      if (Math.hypot(mx - p.x, my - p.y) < Math.max(16 * MAP_SCALE, p.r + 4)) {
        previewedId = p.id;
        drawMap();
        renderIndicatorDetail(p.id);
        break;
      }
    }
  }

  // ── Sidebar: indicator detail ──
  function renderIndicatorDetail(id) {
    const el = document.getElementById('m3IndicatorDetailBody');
    if (!el) return;
    const ind = indicators.find(i => i.id === id);
    if (!ind) return;

    const bars = AXES.map(ax => {
      const score = ind.facet_scores[ax] || 0;
      return `
        <div class="tech-axis-bar-row">
          <span class="tech-axis-bar-label">${AXIS_LABELS[ax]}</span>
          <span class="tech-axis-bar-track"><span class="tech-axis-bar-fill" style="width:${score * 100}%;background:${AXIS_COLORS[ax]}"></span></span>
          <span class="tech-axis-bar-val">${score.toFixed(2)}</span>
        </div>`;
    }).join('');

    el.innerHTML = `
      <div class="tech-detail-name">${ind.name}</div>
      <div class="tech-detail-en">${ind.name_en}</div>
      <div class="tech-detail-row">
        <div class="tech-detail-label">公式</div>
        <div class="tech-detail-formula">${ind.formula}</div>
      </div>
      <div class="tech-detail-row">
        <div class="tech-detail-label">滯後性</div>
        <div class="tech-detail-lag">${ind.lag_note}</div>
      </div>
      <div class="tech-detail-row">
        <div class="tech-detail-label">六維面向分數</div>
        ${bars}
      </div>
      <button class="btn-primary tech-add-btn" id="m3AddToBasketBtn">${selected.has(id) ? '－ 移除策略' : '＋ 新增至策略'}</button>`;

    document.getElementById('m3AddToBasketBtn')?.addEventListener('click', () => {
      selected.has(id) ? selected.delete(id) : selected.add(id);
      render();
    });
  }

  // ── Strategy basket ──
  function renderBasket() {
    const el = document.getElementById('tech-basket');
    if (!el) return;
    const countEl = document.getElementById('tech-basket-count');
    if (selected.size === 0) {
      if (countEl) countEl.textContent = '';
      el.innerHTML = '<p class="tech-empty">點選圖譜上的球體查看說明，於左側按「新增至策略」加入</p>';
      return;
    }
    if (countEl) countEl.textContent = `(${selected.size})`;
    const selInds = indicators.filter(i => selected.has(i.id));
    el.innerHTML = selInds.map(ind => `
      <div class="tech-tag">
        <span class="tech-tag-name">${ind.name_en}</span>
        <span class="tech-tag-zh">${ind.name}</span>
        <button class="tech-tag-rm" data-id="${ind.id}" aria-label="移除">×</button>
      </div>`).join('');
    el.querySelectorAll('.tech-tag-rm').forEach(btn =>
      btn.addEventListener('click', () => { selected.delete(btn.dataset.id); render(); })
    );
  }

  // ── Strategy radar (SVG, no deps) ──
  function renderRadar() {
    const container = document.getElementById('tech-radar');
    const info = document.getElementById('tech-score-info');
    if (!container) return;

    const selInds = indicators.filter(i => selected.has(i.id));
    if (selInds.length === 0) {
      container.innerHTML = '<p class="tech-empty">選擇指標後顯示策略雷達圖</p>';
      if (info) info.innerHTML = '';
      return;
    }

    // §6.1 coverage sum
    const cov = Object.fromEntries(AXES.map(ax => [ax, 0]));
    selInds.forEach(ind => AXES.forEach(ax => { cov[ax] += ind.facet_scores[ax] || 0; }));

    // §6.1.1 dynamic axis max
    const axMax = Math.max(...Object.values(cov), 1.0);

    // SVG radar
    const W = 280, H = 280, CR = 100, CCX = 140, CCY = 140;
    const angle = i => Math.PI / 2 - i * (2 * Math.PI / 6);

    const rings = [0.25, 0.5, 0.75, 1.0].map(f => {
      const pts = AXES.map((_, i) => `${CCX + CR * f * Math.cos(angle(i))},${CCY - CR * f * Math.sin(angle(i))}`).join(' ');
      return `<polygon points="${pts}" fill="none" stroke="${gridStroke(0.09)}" stroke-width="1"/>`;
    }).join('');

    const spokes = AXES.map((_, i) =>
      `<line x1="${CCX}" y1="${CCY}" x2="${CCX + CR * Math.cos(angle(i))}" y2="${CCY - CR * Math.sin(angle(i))}" stroke="${gridStroke(0.12)}"/>`
    ).join('');

    // threshold ring at 0.5
    const thrF = 0.5 / axMax;
    const thrPts = AXES.map((_, i) => `${CCX + CR * thrF * Math.cos(angle(i))},${CCY - CR * thrF * Math.sin(angle(i))}`).join(' ');

    const covPts = AXES.map((ax, i) => {
      const r = (cov[ax] / axMax) * CR;
      return `${CCX + r * Math.cos(angle(i))},${CCY - r * Math.sin(angle(i))}`;
    }).join(' ');

    const labels = AXES.map((ax, i) => {
      const lx = CCX + (CR + 20) * Math.cos(angle(i));
      const ly = CCY - (CR + 20) * Math.sin(angle(i));
      const val = cov[ax] > 0 ? ` (${cov[ax].toFixed(1)})` : '';
      return `<text x="${lx}" y="${ly}" text-anchor="middle" dominant-baseline="middle"
        fill="${AXIS_COLORS[ax]}" font-size="10" font-family="Inter,sans-serif"
        font-weight="600">${AXIS_LABELS[ax]}${val}</text>`;
    }).join('');

    container.innerHTML = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
      ${rings}${spokes}
      <polygon points="${thrPts}" fill="none" stroke="rgba(212,160,23,0.5)" stroke-width="1" stroke-dasharray="4,3"/>
      <polygon points="${covPts}" fill="rgba(201,79,79,0.12)" stroke="#C94F4F" stroke-width="2"/>
      ${labels}
    </svg>`;

    if (!info) return;

    // §6.2 completeness
    const covered = PILLARS.filter(ax => cov[ax] >= THRESHOLD).length;
    const completeness = covered / PILLARS.length;

    // §6.3 datasource
    const ds = { price: 0, volume: 0, time: 0 };
    selInds.forEach(ind => ['price', 'volume', 'time'].forEach(s => {
      ds[s] = Math.max(ds[s], ind.datasource_scores[s] || 0);
    }));

    // diagnostic warnings
    const warns = [];
    if (cov.volatility < THRESHOLD) warns.push('⚠ 波動率軸不足，建議加入 ATR 做風控停損');
    if (cov.volume < THRESHOLD) warns.push('⚠ 量能軸不足，量價未確認');
    if (ds.volume === 0) warns.push('⚠ 整套策略無成交量資料，數據偏食');
    AXES.forEach(ax => {
      if (cov[ax] > 2.0) warns.push(`⚠ ${AXIS_LABELS[ax]}軸 = ${cov[ax].toFixed(1)}，重複下注過多`);
    });

    const scoreClass = completeness >= 0.75 ? 'pos' : completeness >= 0.5 ? 'warn' : 'neg';
    info.innerHTML = `
      <div class="tech-score-row">
        <span>策略完整度</span>
        <span class="tech-score-val ${scoreClass}">${(completeness * 100).toFixed(0)}%
          <small>(${covered}/4 支柱)</small></span>
      </div>
      <div class="tech-score-row">
        <span>數據源依賴</span>
        <span class="tech-score-val">價 ${(ds.price * 100).toFixed(0)}% ／ 量 ${(ds.volume * 100).toFixed(0)}% ／ 時 ${(ds.time * 100).toFixed(0)}%</span>
      </div>
      ${warns.map(w => `<div class="tech-warn">${w}</div>`).join('')}`;
  }

  // ── Stock price chart (multi-provider: FMP / Twelve Data / Alpaca) ──
  const PROVIDERS = {
    fmp: {
      label: 'FMP',
      keyHelp: '<a href="https://site.financialmodelingprep.com/developer/docs" target="_blank" rel="noopener">FMP API Key</a>（免費申請，僅日線）',
      needsSecret: false,
      intervals: [{ value: 'daily', label: '日線' }],
      buildRequest(symbol, key) {
        return { url: `https://financialmodelingprep.com/stable/historical-price-eod/full?symbol=${encodeURIComponent(symbol)}&apikey=${encodeURIComponent(key)}` };
      },
      parse(data) {
        if (!Array.isArray(data) || data.length === 0) return { error: data?.['Error Message'] || '查無資料，請確認代碼或 API Key' };
        const rows = [...data].reverse().map(r => ({ date: r.date, open: r.open, high: r.high, low: r.low, close: r.close, volume: r.volume }));
        return { rows };
      },
    },
    twelvedata: {
      label: 'Twelve Data',
      keyHelp: '<a href="https://twelvedata.com/pricing" target="_blank" rel="noopener">Twelve Data API Key</a>（免費申請，支援分鐘線，每日額度有限）',
      needsSecret: false,
      intervals: [
        { value: '1day', label: '日線' },
        { value: '1h', label: '1小時' },
        { value: '30min', label: '30分鐘' },
        { value: '15min', label: '15分鐘' },
        { value: '5min', label: '5分鐘' },
        { value: '1min', label: '1分鐘' },
      ],
      buildRequest(symbol, key, interval) {
        return { url: `https://api.twelvedata.com/time_series?symbol=${encodeURIComponent(symbol)}&interval=${interval}&outputsize=500&apikey=${encodeURIComponent(key)}` };
      },
      parse(data) {
        if (!Array.isArray(data?.values)) return { error: data?.message || '查無資料，請確認代碼或 API Key' };
        const rows = [...data.values].reverse().map(r => ({
          date: r.datetime.replace(' ', 'T'),
          open: +r.open, high: +r.high, low: +r.low, close: +r.close, volume: +(r.volume || 0),
        }));
        return { rows };
      },
    },
    alpaca: {
      label: 'Alpaca',
      keyHelp: '<a href="https://alpaca.markets/docs/api-references/market-data-api/" target="_blank" rel="noopener">Alpaca API Key + Secret</a>（免費申請，美股分鐘線，IEX 資料源）',
      needsSecret: true,
      intervals: [
        { value: '1Day', label: '日線' },
        { value: '1Hour', label: '1小時' },
        { value: '30Min', label: '30分鐘' },
        { value: '15Min', label: '15分鐘' },
        { value: '5Min', label: '5分鐘' },
        { value: '1Min', label: '1分鐘' },
      ],
      buildRequest(symbol, key, interval, secret) {
        const end = new Date();
        const start = new Date(end.getTime() - 60 * 24 * 3600 * 1000); // 近 60 天
        const url = `https://data.alpaca.markets/v2/stocks/${encodeURIComponent(symbol)}/bars?timeframe=${interval}&start=${start.toISOString()}&end=${end.toISOString()}&limit=1000&adjustment=raw&feed=iex`;
        return { url, headers: { 'APCA-API-KEY-ID': key, 'APCA-API-SECRET-KEY': secret } };
      },
      parse(data) {
        if (!Array.isArray(data?.bars)) return { error: data?.message || '查無資料，請確認代碼或 API Key/Secret' };
        const rows = data.bars.map(b => ({ date: b.t, open: b.o, high: b.h, low: b.l, close: b.c, volume: b.v }));
        return { rows };
      },
    },
  };

  let priceChart = null;
  let selectedTrade = null; // { entry, exit }：交易清單點選的持有區間，畫在價格圖上（DESIGN-HANDOFF §5a）
  let lastSymbol = null;
  let lastRows = null;

  function currentProvider() {
    return PROVIDERS[document.getElementById('stock-provider')?.value] || PROVIDERS.fmp;
  }
  const keyStorageId = providerId => `stockapi_${providerId}_key`;
  const secretStorageId = providerId => `stockapi_${providerId}_secret`;

  function refreshProviderUI() {
    const providerSel = document.getElementById('stock-provider');
    if (!providerSel) return;
    const providerId = providerSel.value;
    const provider = currentProvider();

    const hintEl = document.getElementById('stock-provider-hint');
    if (hintEl) hintEl.innerHTML = provider.keyHelp;

    const intervalSel = document.getElementById('stock-interval');
    if (intervalSel) intervalSel.innerHTML = provider.intervals.map(iv => `<option value="${iv.value}">${iv.label}</option>`).join('');

    const keyInput = document.getElementById('stock-apikey');
    const secretInput = document.getElementById('stock-apisecret');
    if (keyInput) keyInput.value = localStorage.getItem(keyStorageId(providerId)) || '';
    if (secretInput) {
      secretInput.style.display = provider.needsSecret ? '' : 'none';
      secretInput.value = localStorage.getItem(secretStorageId(providerId)) || '';
    }
  }

  async function fetchStockPrice() {
    const providerId = document.getElementById('stock-provider')?.value;
    const provider = currentProvider();
    const symbol = document.getElementById('stock-symbol')?.value.trim().toUpperCase();
    const apiKey = document.getElementById('stock-apikey')?.value.trim();
    const apiSecret = document.getElementById('stock-apisecret')?.value.trim();
    const interval = document.getElementById('stock-interval')?.value;
    const statusEl = document.getElementById('stock-status');

    if (!symbol || !apiKey || (provider.needsSecret && !apiSecret)) {
      if (statusEl) statusEl.textContent = `請輸入股票代碼與 API Key${provider.needsSecret ? '/Secret' : ''}`;
      return;
    }
    localStorage.setItem(keyStorageId(providerId), apiKey);
    if (provider.needsSecret) localStorage.setItem(secretStorageId(providerId), apiSecret);
    if (statusEl) statusEl.textContent = '讀取中…';

    try {
      const { url, headers } = provider.buildRequest(symbol, apiKey, interval, apiSecret);
      const resp = await fetch(url, headers ? { headers } : undefined);
      const data = await resp.json();
      const { rows, error } = provider.parse(data);
      if (error || !rows || rows.length === 0) {
        if (statusEl) statusEl.textContent = `查無資料：${error || '請確認代碼或金鑰'}`;
        return;
      }
      lastSymbol = symbol;
      lastRows = rows;
      drawPriceChart(symbol, rows);
      if (statusEl) statusEl.textContent = `${symbol}（${provider.label}）共 ${rows.length} 筆資料`;
    } catch (e) {
      if (statusEl) statusEl.textContent = '讀取失敗，請檢查網路或金鑰';
      console.error('technical.js: stock price fetch failed', e);
    }
  }

  function drawPriceChart(symbol, rows, overlays = []) {
    const canvas = document.getElementById('stock-price-chart');
    if (!canvas || typeof Chart === 'undefined') return;
    const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
    const grid = isDark ? 'rgba(42,42,42,0.6)' : 'rgba(208,207,204,0.5)';
    const tick = isDark ? '#9A9DA6' : '#6B6E78';
    const hasOsc = overlays.some(o => o.yAxisID === 'yOsc');

    if (priceChart) priceChart.destroy();
    // legend 底部加 10px 間距：繪圖區頂端要放持有區間倒三角（DESIGN-HANDOFF §5a），避免頂到 legend
    const legendGap = {
      id: 'legendGap',
      beforeInit(chart) {
        const fit = chart.legend.fit;
        chart.legend.fit = function () { fit.call(this); this.height += 10; };
      },
    };
    // 持有區間標記：進場 info／出場 gold，垂直虛線＋貼齊繪圖區頂端的倒三角（三角本體畫在 legendGap 預留的 10px 內）
    const cssVar = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    const tradeRange = {
      id: 'tradeRange',
      afterDatasetsDraw(chart) {
        if (!selectedTrade) return;
        const { ctx, chartArea: a, scales: { x } } = chart;
        [[selectedTrade.entry, cssVar('--color-info') || '#7A93B8'],
         [selectedTrade.exit, cssVar('--color-gold') || '#C9A227']].forEach(([d, color]) => {
          if (!d) return;
          // 用 x 軸自己的 parse，跟 dataset 的日期解析走同一套 adapter，避免時區偏移
          const v = typeof x.parse === 'function' ? x.parse(d) : +new Date(d);
          const px = x.getPixelForValue(v);
          if (!isFinite(px) || px < a.left || px > a.right) return; // 縮放後超出視窗就不畫
          ctx.save();
          ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = 1;
          ctx.setLineDash([4, 3]);
          ctx.beginPath(); ctx.moveTo(px, a.top); ctx.lineTo(px, a.bottom); ctx.stroke();
          ctx.setLineDash([]);
          ctx.beginPath();
          ctx.moveTo(px, a.top);
          ctx.lineTo(px - 4, a.top - 8);
          ctx.lineTo(px + 4, a.top - 8);
          ctx.closePath(); ctx.fill();
          ctx.restore();
        });
      },
    };
    priceChart = new Chart(canvas.getContext('2d'), {
      type: 'line',
      plugins: [legendGap, tradeRange],
      data: {
        datasets: [{
          label: `${symbol} 收盤價`,
          data: rows.map(r => ({ x: r.date, y: r.close })),
          borderColor: '#8B2E2E',
          backgroundColor: 'rgba(192,57,43,0.08)',
          borderWidth: 2,
          pointRadius: 0,
          pointHoverRadius: 4,
          tension: 0.15,
          fill: true,
          yAxisID: 'y',
        }, ...overlays],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { labels: { color: tick, font: { family: 'Inter', size: 11 } } },
          zoom: {
            pan: { enabled: true, mode: 'x' },
            zoom: {
              wheel: { enabled: true },
              pinch: { enabled: true },
              mode: 'x',
            },
            limits: { x: { min: 'original', max: 'original' } },
          },
        },
        scales: {
          x: {
            type: 'time',
            grid: { color: grid },
            ticks: { color: tick, font: { family: 'Inter', size: 10 }, maxTicksLimit: 12 },
          },
          y: {
            position: 'left',
            grid: { color: grid },
            ticks: { color: tick, font: { family: 'Inter', size: 10 } },
          },
          ...(hasOsc ? {
            yOsc: {
              position: 'right', min: 0, max: 100,
              grid: { drawOnChartArea: false },
              ticks: { color: tick, font: { family: 'Inter', size: 10 } },
              title: { display: true, text: '指標值（標準化）', color: tick, font: { family: 'Inter', size: 10 } },
            },
          } : {}),
        },
      },
    });
  }

  function bootPriceChart() {
    const btn = document.getElementById('stock-fetch-btn');
    if (!btn) return;
    refreshProviderUI();
    document.getElementById('stock-provider')?.addEventListener('change', refreshProviderUI);
    btn.addEventListener('click', fetchStockPrice);
    document.getElementById('stock-symbol')?.addEventListener('keydown', e => {
      if (e.key === 'Enter') fetchStockPrice();
    });
    document.getElementById('stock-zoom-reset')?.addEventListener('click', () => priceChart?.resetZoom());
  }

  // ── Parameter optimization (backtest.js) + overlay onto price chart ──
  const OVERLAY_COLORS = ['#7A93B8', '#C9A227', '#C94F4F', '#9A9DA6', '#5A7499', '#A03636', '#6B6E78'];
  let overlayState = {}; // id -> { datasets, label, ret, visible }

  function buildOhlc(rows) {
    return {
      dates: rows.map(r => r.date),
      opens: rows.map(r => r.open),
      highs: rows.map(r => r.high),
      lows: rows.map(r => r.low),
      closes: rows.map(r => r.close),
      volumes: rows.map(r => r.volume),
    };
  }

  function paramLabel(ind, spec, params) {
    const paramStr = spec.params.map(p => `${p.label}=${params[p.key]}`).join(',');
    const name = ind ? ind.name_en : spec.id;
    return paramStr ? `${name}(${paramStr})` : name;
  }

  function buildOverlayDatasets(id, spec, params, ohlc, colorOffset) {
    const seriesMap = spec.series(ohlc, params);
    let names = Object.keys(seriesMap);
    let values = names.map(n => seriesMap[n]);
    if (spec.displayNormalize) values = window.Backtest.normalize01(values);
    return names.map((name, i) => ({
      label: `${id} ${name}`,
      data: ohlc.dates.map((d, j) => ({ x: d, y: values[i][j] })),
      borderColor: OVERLAY_COLORS[(colorOffset + i) % OVERLAY_COLORS.length],
      borderWidth: 1.5,
      pointRadius: 0,
      pointHoverRadius: 3,
      tension: 0.1,
      fill: false,
      yAxisID: spec.overlayAxis === 'osc' ? 'yOsc' : 'y',
    }));
  }

  // set/replace the chart overlay for one indicator (used both by the
  // optimize button and by clicking a heatmap cell) without touching the others
  function setOverlay(id, spec, params, ohlc, ret) {
    const ind = indicators.find(i => i.id === id);
    const idx = indicators.findIndex(i => i.id === id);
    overlayState[id] = {
      datasets: buildOverlayDatasets(id, spec, params, ohlc, idx * 2),
      label: paramLabel(ind, spec, params),
      ret,
      visible: overlayState[id] ? overlayState[id].visible : true,
    };
  }

  function renderPriceOverlays() {
    const toggleEl = document.getElementById('stock-overlay-toggles');
    const ids = Object.keys(overlayState);
    if (toggleEl) {
      toggleEl.innerHTML = ids.map(id => {
        const st = overlayState[id];
        const retPct = (st.ret * 100).toFixed(1);
        return `<button class="overlay-chip${st.visible ? ' active' : ''}" data-id="${id}">${st.label} ${retPct}%</button>`;
      }).join('');
      toggleEl.querySelectorAll('.overlay-chip').forEach(btn => {
        btn.addEventListener('click', () => {
          overlayState[btn.dataset.id].visible = !overlayState[btn.dataset.id].visible;
          renderPriceOverlays();
        });
      });
    }
    const overlays = ids.filter(id => overlayState[id].visible).flatMap(id => overlayState[id].datasets);
    drawPriceChart(lastSymbol, lastRows, overlays);
  }

  // ── 策略測試器（TradingView 式底部面板）──
  const ALGO_LABELS = { none: '固定公式', grid: '網格搜尋', ga: '遺傳演算法', pso: '粒子群 PSO', bayes: '貝氏優化' };
  let optResults = {};      // id -> Optimizer.optimize() 結果（附 .ohlc）
  let activeOptId = null;
  let activeOptTab = 'overview';
  let optEquityChart = null;
  let optConfig = loadOptConfig();

  function loadOptConfig() {
    try { return JSON.parse(localStorage.getItem('tech-opt-config')) || {}; } catch { return {}; }
  }

  const fmtPct = v => v == null ? '—' : (v * 100).toFixed(1) + '%';
  const fmtNum = (v, d = 2) => v == null ? '—' : (+v).toFixed(d);
  const signCls = v => v > 0 ? 'pos' : v < 0 ? 'neg' : '';
  const paramText = (spec, params) => spec.params.map(p => `${p.label}=${params[p.key]}`).join('、');

  // ── 各指標進度列：回傳 update(id, pct, text, cls) ──
  function initProgressRows(ids) {
    const el = document.getElementById('tech-opt-progress');
    if (!el) return () => {};
    el.innerHTML = ids.map(id => {
      const ind = indicators.find(i => i.id === id);
      return `<div class="opt-prog-row" data-id="${id}">
        <span class="opt-prog-name">${ind ? ind.name : id}</span>
        <span class="opt-prog-track"><span class="opt-prog-fill"></span></span>
        <span class="opt-prog-text">等待中</span>
      </div>`;
    }).join('');
    return function update(id, pct, text, cls) {
      const row = el.querySelector(`.opt-prog-row[data-id="${id}"]`);
      if (!row) return;
      row.className = 'opt-prog-row' + (cls ? ' ' + cls : '');
      row.querySelector('.opt-prog-fill').style.width = `${Math.max(0, Math.min(100, pct))}%`;
      row.querySelector('.opt-prog-text').textContent = text;
    };
  }

  async function runOptimization() {
    const statusEl = document.getElementById('tech-optimize-status');
    if (selected.size === 0) {
      if (statusEl) statusEl.textContent = '請先在上方圖譜點選要納入策略籃的指標';
      return;
    }
    if (!lastRows || !window.Optimizer) {
      if (statusEl) statusEl.textContent = '請先在下方輸入股票代碼並抓取股價';
      return;
    }
    const btn = document.getElementById('tech-optimize-btn');
    if (btn) btn.disabled = true;
    const ohlc = buildOhlc(lastRows);
    overlayState = {};
    optResults = {};
    selectedTrade = null; // 舊的持有區間標記對新結果沒有意義
    const ids = [...selected];
    const setProg = initProgressRows(ids);
    try {
      for (let i = 0; i < ids.length; i++) {
        const id = ids[i];
        if (statusEl) statusEl.textContent = `回測中 ${i + 1}/${ids.length}（${id}）…`;
        setProg(id, 0, '計算中…', 'run');
        try {
          const result = await window.Optimizer.optimize(id, ohlc, optConfig, (phase, it, total, evals) => {
            setProg(id, total ? it / total * 100 : 0,
              `${phase} ${it}/${total}${evals ? `・已評估 ${evals} 組` : ''}`, 'run');
          });
          if (!result) { setProg(id, 100, '無回測規格，已跳過', 'skip'); continue; }
          result.ohlc = ohlc; // 熱力圖點格子切換疊圖時要用
          optResults[id] = result;
          setOverlay(id, result.spec, result.best.params, ohlc, result.best.ret);
          setProg(id, 100, `完成・報酬 ${fmtPct(result.best.ret)}`, 'done');
        } catch (e) {
          console.error(`technical.js: optimize ${id} failed`, e);
          setProg(id, 100, `失敗：${e.message}`, 'fail');
        }
      }
    } finally {
      if (btn) btn.disabled = false;
    }
    const okIds = Object.keys(optResults);
    activeOptId = okIds[0] || null;
    const cardEl = document.getElementById('tech-opt-card');
    if (cardEl) cardEl.style.display = okIds.length ? '' : 'none';
    renderPriceOverlays();
    renderOptPanel();
    if (statusEl) statusEl.textContent = okIds.length
      ? `完成 ${okIds.length}/${ids.length} 個指標；已疊圖最佳參數，詳細績效見下方策略測試器`
      : '沒有指標完成回測，原因見上方各指標進度列';
  }

  function currentResult() { return activeOptId ? optResults[activeOptId] : null; }

  function renderOptPanel() {
    const el = document.getElementById('opt-ind-chips');
    if (el) {
      el.innerHTML = Object.keys(optResults).map(id => {
        const ind = indicators.find(i => i.id === id);
        return `<button class="overlay-chip${id === activeOptId ? ' active' : ''}" data-id="${id}">${ind ? ind.name_en : id}</button>`;
      }).join('');
      el.querySelectorAll('button').forEach(b =>
        b.addEventListener('click', () => {
          activeOptId = b.dataset.id;
          selectedTrade = null; // 標記屬於前一個指標的交易，換指標即清除
          if (priceChart) priceChart.update('none');
          renderOptPanel();
        }));
    }
    renderActivePane();
  }

  function renderActivePane() {
    const r = currentResult();
    if (activeOptTab === 'overview') renderOverview(r);
    else if (activeOptTab === 'perf') renderPerf(r);
    else if (activeOptTab === 'plateau') renderPlateau(r);
    else if (activeOptTab === 'trades') renderTrades(r);
    // settings 為常駐表單，不依賴回測結果
  }

  // ── 總覽：KPI 條 + 收斂圖 + 權益曲線 ──
  function renderOverview(r) {
    const kpiEl = document.getElementById('opt-kpis');
    const convEl = document.getElementById('opt-converge');
    if (!kpiEl) return;
    if (convEl) convEl.innerHTML = '';
    if (!r) { kpiEl.innerHTML = '<p class="tech-empty">尚無回測結果</p>'; destroyEquityChart(); return; }
    const m = r.best.metrics;
    const kpis = [
      ['總報酬', fmtPct(m.roi), signCls(m.roi)],
      ['年化報酬', fmtPct(m.annRoi), signCls(m.annRoi)],
      ['Sharpe', fmtNum(m.sharpe), signCls(m.sharpe)],
      ['最大回撤', fmtPct(m.maxDrawdown), m.maxDrawdown > 0 ? 'neg' : ''],
      ['勝率', fmtPct(m.winRate), ''],
      ['交易筆數', String(m.tradeCount), ''],
      ['曝險比', fmtPct(m.exposure), ''],
    ];
    if (r.best.plateau != null) kpis.push(['高原分數', fmtNum(r.best.plateau, 3), '']);
    if (r.wfa) {
      kpis.push(['平均 WFE', fmtNum(r.wfa.avgWfe), signCls(r.wfa.avgWfe)]);
      kpis.push(['OOS 總報酬', fmtPct(r.wfa.stitched.roi), signCls(r.wfa.stitched.roi)]);
    }
    if (r.mc) {
      kpis.push(['MC 中位報酬', fmtPct(r.mc.finalRoi.p50), signCls(r.mc.finalRoi.p50)]);
      kpis.push(['獲利機率', fmtPct(r.mc.probPositive), '']);
    }
    kpiEl.innerHTML =
      `<div class="opt-kpi-meta">最佳參數：${paramText(r.spec, r.best.params) || '無可調參數'}（${ALGO_LABELS[r.mode] || r.mode}，評估 ${r.evalCount} 組）</div>` +
      '<div class="opt-kpi-row">' +
      kpis.map(([l, v, c]) => `<div class="opt-kpi"><span class="opt-kpi-label">${l}</span><span class="opt-kpi-val ${c}">${v}</span></div>`).join('') +
      '</div>';
    if (convEl && r.history && r.history.length > 1) {
      drawSparkline(convEl, r.history, `${ALGO_LABELS[r.mode]}收斂過程：各代最佳 fitness`);
    }
    renderEquityChart(r);
  }

  function destroyEquityChart() {
    if (optEquityChart) { optEquityChart.destroy(); optEquityChart = null; }
  }

  function renderEquityChart(r) {
    const canvas = document.getElementById('opt-equity-chart');
    if (!canvas || typeof Chart === 'undefined') return;
    destroyEquityChart();
    const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
    const grid = isDark ? 'rgba(42,42,42,0.6)' : 'rgba(208,207,204,0.5)';
    const tick = isDark ? '#9A9DA6' : '#6B6E78';
    const labels = r.dates ? r.dates.map(d => String(d).slice(0, 10)) : [...r.best.metrics.equityCurve].map((_, i) => i);
    const datasets = [
      { label: '策略權益', data: [...r.best.metrics.equityCurve], borderColor: '#8B2E2E', borderWidth: 2, pointRadius: 0, tension: 0.1, fill: false },
      { label: '買進持有', data: [...r.buyHold], borderColor: tick, borderDash: [5, 4], borderWidth: 1.5, pointRadius: 0, tension: 0.1, fill: false },
    ];
    if (r.mc && r.mc.envelope) { // daily 模式的分位包絡（重抽樣不對應實際日期，僅示分布）
      datasets.push({ label: 'MC P95', data: [1, ...r.mc.envelope.p95], borderColor: 'rgba(39,174,96,0.5)', borderWidth: 1, pointRadius: 0, fill: false });
      datasets.push({ label: 'MC P5', data: [1, ...r.mc.envelope.p5], borderColor: 'rgba(192,57,43,0.5)', borderWidth: 1, pointRadius: 0, fill: '-1', backgroundColor: 'rgba(150,150,150,0.08)' });
    }
    optEquityChart = new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: { labels, datasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { labels: { color: tick, font: { family: 'Inter', size: 11 } } } },
        scales: {
          x: { ticks: { color: tick, maxTicksLimit: 10, font: { family: 'Inter', size: 10 } }, grid: { color: grid } },
          y: { ticks: { color: tick, font: { family: 'Inter', size: 10 } }, grid: { color: grid } },
        },
      },
    });
  }

  // ── 績效摘要：全樣本統計 +（WFE 視窗明細 / 蒙地卡羅分位）──
  function renderPerf(r) {
    const el = document.getElementById('opt-perf-body');
    if (!el) return;
    if (!r) { el.innerHTML = '<p class="tech-empty">尚無回測結果</p>'; return; }
    const m = r.best.metrics;
    const rows = [
      ['總報酬', fmtPct(m.roi), signCls(m.roi)],
      ['年化報酬', fmtPct(m.annRoi), signCls(m.annRoi)],
      ['Sharpe Ratio', fmtNum(m.sharpe), signCls(m.sharpe)],
      ['最大回撤', fmtPct(m.maxDrawdown), m.maxDrawdown > 0 ? 'neg' : ''],
      ['勝率', fmtPct(m.winRate), ''],
      ['交易筆數', String(m.tradeCount), ''],
      ['曝險比', fmtPct(m.exposure), ''],
      ['綜合 Fitness', fmtNum(r.best.fitness, 4), ''],
      ['高原分數', r.best.plateau == null ? '—' : fmtNum(r.best.plateau, 4), ''],
      ['評估參數組數', String(r.evalCount), ''],
    ];
    let html = `<table class="opt-table"><tbody>${rows.map(([k, v, c]) =>
      `<tr><td>${k}</td><td class="${c}">${v}</td></tr>`).join('')}</tbody></table>`;

    if (r.wfa) {
      const w = r.wfa;
      const pd = d => d ? String(d).slice(0, 10) : '?';
      html += `<div class="opt-section-title">Walk-Forward 視窗明細（${w.windows.length} 視窗，有效 WFE ${w.validWindows}）</div>`;
      html += `<div class="opt-table-scroll"><table class="opt-table"><thead><tr>
        <th>#</th><th>IS 期間</th><th>OOS 期間</th><th>視窗最佳參數</th><th>IS 年化</th><th>OOS 年化</th><th>WFE</th></tr></thead><tbody>`;
      html += w.windows.map((win, i) => `<tr><td>${i + 1}</td>
        <td>${win.isDates ? pd(win.isDates[0]) + '～' + pd(win.isDates[1]) : win.isIdx.join('–')}</td>
        <td>${win.oosDates ? pd(win.oosDates[0]) + '～' + pd(win.oosDates[1]) : win.oosIdx.join('–')}</td>
        <td>${paramText(r.spec, win.bestParams) || '—'}</td>
        <td class="${signCls(win.is.annRoi)}">${fmtPct(win.is.annRoi)}</td>
        <td class="${signCls(win.oos.annRoi)}">${fmtPct(win.oos.annRoi)}</td>
        <td>${win.wfe == null ? '—' : fmtNum(win.wfe)}</td></tr>`).join('');
      html += '</tbody></table></div>';
      html += `<table class="opt-table"><tbody>
        <tr><td>平均 WFE</td><td>${fmtNum(w.avgWfe)}</td></tr>
        <tr><td>中位 WFE</td><td>${fmtNum(w.medianWfe)}</td></tr>
        <tr><td>串接 OOS 總報酬</td><td class="${signCls(w.stitched.roi)}">${fmtPct(w.stitched.roi)}</td></tr>
        <tr><td>串接 OOS Sharpe</td><td>${fmtNum(w.stitched.sharpe)}</td></tr>
        <tr><td>串接 OOS 最大回撤</td><td class="neg">${fmtPct(w.stitched.maxDrawdown)}</td></tr>
      </tbody></table>
      <div class="opt-item-note">WFE = OOS 年化報酬 ÷ IS 年化報酬（IS ≤ 0 的視窗不計）；&gt; 0.5 一般視為參數在樣本外仍保有效力</div>`;
    }
    if (r.mc) {
      const s = r.mc;
      const cols = ['p5', 'p25', 'p50', 'p75', 'p95', 'mean'];
      html += `<div class="opt-section-title">蒙地卡羅重抽樣（${s.runs} 次，${s.mode === 'daily' ? '日報酬' : '逐筆交易'}模式）</div>`;
      html += `<table class="opt-table"><thead><tr><th></th><th>P5</th><th>P25</th><th>P50</th><th>P75</th><th>P95</th><th>平均</th></tr></thead><tbody>
        <tr><td>最終報酬</td>${cols.map(k => `<td class="${signCls(s.finalRoi[k])}">${fmtPct(s.finalRoi[k])}</td>`).join('')}</tr>
        <tr><td>最大回撤</td>${cols.map(k => `<td>${fmtPct(s.maxDrawdown[k])}</td>`).join('')}</tr>
      </tbody></table>
      <div class="opt-item-note">獲利機率 P(報酬 &gt; 0) = ${fmtPct(s.probPositive)}${s.mode === 'trades' ? '；逐筆模式的最大回撤為逐筆近似（忽略持倉中回撤）' : ''}</div>`;
    }
    el.innerHTML = html;
  }

  // ── 交易清單（點一列 → 該列框選＋價格圖畫出持有區間）──
  function renderTrades(r) {
    const el = document.getElementById('opt-trades-body');
    if (!el) return;
    if (!r) { el.innerHTML = '<p class="tech-empty">尚無回測結果</p>'; return; }
    const trades = r.best.metrics.trades;
    if (!trades.length) { el.innerHTML = '<p class="tech-empty">最佳參數在此區間沒有任何交易</p>'; return; }
    const pd = d => d ? String(d).slice(0, 10) : '—';
    const isSel = t => selectedTrade && selectedTrade.entry === t.entryDate && selectedTrade.exit === t.exitDate;
    el.innerHTML = `<table class="opt-table opt-trades"><thead><tr>
      <th>#</th><th>進場日</th><th>進場價</th><th>出場日</th><th>出場價</th><th>K棒數</th><th>報酬</th></tr></thead><tbody>` +
      trades.map((t, i) => `<tr data-i="${i}"${isSel(t) ? ' class="sel-trade"' : ''}><td>${i + 1}${t.open ? '（未平倉）' : ''}</td>
        <td>${pd(t.entryDate)}</td><td class="t-entry">${t.entryPrice.toFixed(2)}</td>
        <td>${pd(t.exitDate)}</td><td class="t-exit">${t.exitPrice.toFixed(2)}</td>
        <td>${t.bars}</td><td class="${signCls(t.ret)}">${fmtPct(t.ret)}</td></tr>`).join('') +
      '</tbody></table>';
    el.querySelectorAll('tbody tr').forEach(tr => tr.addEventListener('click', () => {
      const t = trades[+tr.dataset.i];
      const same = isSel(t);
      selectedTrade = same ? null : { entry: t.entryDate, exit: t.exitDate }; // 再點一次取消
      el.querySelectorAll('tbody tr').forEach(row => row.classList.toggle('sel-trade', row === tr && !same));
      if (priceChart) priceChart.update('none');
    }));
  }

  // ── 參數高原：熱力圖 + 等高線 + 高原高亮 + 切片選擇 ──
  function renderPlateau(r) {
    const ctrlEl = document.getElementById('opt-slice-controls');
    const wrapEl = document.getElementById('opt-heatmap-wrap');
    if (!ctrlEl || !wrapEl) return;
    ctrlEl.innerHTML = '';
    wrapEl.innerHTML = '';
    if (!r) { wrapEl.innerHTML = '<p class="tech-empty">尚無回測結果</p>'; return; }
    if (!r.grid) { wrapEl.innerHTML = '<p class="tech-empty">此指標無可調參數，無參數高原視圖</p>'; return; }
    const ps = r.spec.params;
    let dimX = r.grid.dims[0].key;
    let dimY = r.grid.dims[1] ? r.grid.dims[1].key : null;
    let valueKey = 'fitness';
    let slice = r.grid;

    function renderControls() {
      const dimSelects = ps.length >= 3 ? `
        <label>橫軸 <select id="opt-dim-x">${ps.map(p => `<option value="${p.key}"${p.key === dimX ? ' selected' : ''}>${p.label}</option>`).join('')}</select></label>
        <label>縱軸 <select id="opt-dim-y">${ps.filter(p => p.key !== dimX).map(p => `<option value="${p.key}"${p.key === dimY ? ' selected' : ''}>${p.label}</option>`).join('')}</select></label>
        <span>其餘參數固定於最佳值</span>` : '';
      ctrlEl.innerHTML = `<label>色階 <select id="opt-val-key">
        <option value="fitness"${valueKey === 'fitness' ? ' selected' : ''}>綜合 Fitness</option>
        <option value="roi"${valueKey === 'roi' ? ' selected' : ''}>報酬率</option>
        <option value="plateau"${valueKey === 'plateau' ? ' selected' : ''}>高原分數</option>
      </select></label>${dimSelects}`;
      document.getElementById('opt-val-key').addEventListener('change', e => { valueKey = e.target.value; paint(); });
      if (ps.length >= 3) {
        document.getElementById('opt-dim-x').addEventListener('change', async e => {
          dimX = e.target.value;
          if (dimY === dimX) dimY = ps.find(p => p.key !== dimX).key;
          await reslice();
        });
        document.getElementById('opt-dim-y').addEventListener('change', async e => { dimY = e.target.value; await reslice(); });
      }
    }
    async function reslice() {
      wrapEl.innerHTML = '<p class="tech-empty">切片計算中…</p>';
      slice = await r.slice(dimX, dimY);
      renderControls();
      paint();
    }
    function paint() {
      wrapEl.innerHTML = '';
      drawPlateauHeatmap(wrapEl, r, slice, valueKey);
    }
    renderControls();
    paint();
  }

  function drawPlateauHeatmap(container, r, slice, valueKey) {
    const { dims, cells } = slice;
    const val = c => valueKey === 'roi' ? c.m.roi : valueKey === 'plateau' ? c.plateau : c.fitness;
    const d1 = [...new Set(cells.map(c => c.v1))].sort((a, b) => a - b);
    const d2 = dims.length > 1 ? [...new Set(cells.map(c => c.v2))].sort((a, b) => a - b) : [undefined];
    const cellMap = new Map(cells.map(c => [`${c.v1}|${c.v2}`, c]));
    const vals = cells.map(val);
    const vMin = Math.min(...vals), vMax = Math.max(...vals);
    const maxAbs = Math.max(...vals.map(Math.abs), 1e-9);
    // 高原門檻：切片高原分數 P80
    const sortedPl = cells.map(c => c.plateau).filter(v => v != null).sort((a, b) => a - b);
    const plThr = sortedPl.length ? sortedPl[Math.min(sortedPl.length - 1, Math.floor(sortedPl.length * 0.8))] : null;

    const cellW = 34, cellH = 24, padL = 48, padT = 8, padB = 30, padR = 8;
    const w = padL + d1.length * cellW + padR;
    const h = padT + d2.length * cellH + padB;
    const canvas = document.createElement('canvas');
    const dpr = window.devicePixelRatio || 1;
    canvas.width = w * dpr; canvas.height = h * dpr;
    canvas.style.width = w + 'px'; canvas.style.height = h + 'px';
    canvas.style.cursor = 'pointer';
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);

    let selectedCell = {
      v1: r.best.params[dims[0].key],
      v2: dims.length > 1 ? r.best.params[dims[1].key] : undefined,
    };

    const drawSegs = segs => {
      ctx.beginPath();
      segs.forEach(([x1, y1, x2, y2]) => {
        ctx.moveTo(padL + (x1 + 0.5) * cellW, padT + (y1 + 0.5) * cellH);
        ctx.lineTo(padL + (x2 + 0.5) * cellW, padT + (y2 + 0.5) * cellH);
      });
      ctx.stroke();
    };

    function paint() {
      ctx.clearRect(0, 0, w, h);
      d2.forEach((v2, yi) => d1.forEach((v1, xi) => {
        const c = cellMap.get(`${v1}|${v2}`);
        if (!c) return;
        const x = padL + xi * cellW, y = padT + yi * cellH;
        const t = val(c) / maxAbs;
        ctx.fillStyle = t >= 0
          ? `rgba(39,174,96,${0.12 + Math.min(Math.abs(t), 1) * 0.75})`
          : `rgba(192,57,43,${0.12 + Math.min(Math.abs(t), 1) * 0.75})`;
        ctx.fillRect(x, y, cellW - 1, cellH - 1);
        if (plThr != null && c.plateau >= plThr) { // 高原區高亮
          ctx.fillStyle = 'rgba(212,160,23,0.28)';
          ctx.fillRect(x, y, cellW - 1, cellH - 1);
        }
        if (c.v1 === selectedCell.v1 && (dims.length < 2 || c.v2 === selectedCell.v2)) {
          ctx.strokeStyle = '#C9A227'; ctx.lineWidth = 2;
          ctx.strokeRect(x + 1, y + 1, cellW - 3, cellH - 3);
        }
      }));
      if (d1.length > 1 && d2.length > 1 && vMax > vMin && window.Optimizer) {
        // 等值線（值域 25/50/75%）
        const gridVals = d2.map(v2 => d1.map(v1 => { const c = cellMap.get(`${v1}|${v2}`); return c ? val(c) : null; }));
        [[0.25, 'rgba(255,255,255,0.22)'], [0.5, 'rgba(255,255,255,0.38)'], [0.75, 'rgba(255,255,255,0.6)']].forEach(([q, color]) => {
          ctx.strokeStyle = color; ctx.lineWidth = 1;
          drawSegs(window.Optimizer.marchingSquares(gridVals, vMin + (vMax - vMin) * q));
        });
        // 高原邊界（金色虛線）
        if (plThr != null) {
          const plVals = d2.map(v2 => d1.map(v1 => { const c = cellMap.get(`${v1}|${v2}`); return c ? c.plateau : null; }));
          ctx.strokeStyle = '#C9A227'; ctx.lineWidth = 1.5; ctx.setLineDash([4, 3]);
          drawSegs(window.Optimizer.marchingSquares(plVals, plThr));
          ctx.setLineDash([]);
        }
      }
      ctx.fillStyle = '#9A9DA6';
      ctx.font = '9px Inter, sans-serif';
      ctx.textAlign = 'center';
      d1.forEach((v, i) => ctx.fillText(String(v), padL + i * cellW + cellW / 2, padT + d2.length * cellH + 11));
      if (dims.length > 1) {
        ctx.textAlign = 'right';
        d2.forEach((v, i) => ctx.fillText(String(v), padL - 4, padT + i * cellH + cellH / 2 + 3));
      }
    }
    paint();

    canvas.addEventListener('click', e => {
      const xi = Math.floor((e.offsetX - padL) / cellW);
      const yi = Math.floor((e.offsetY - padT) / cellH);
      if (xi < 0 || xi >= d1.length || yi < 0 || yi >= d2.length) return;
      const c = cellMap.get(`${d1[xi]}|${d2[yi]}`);
      if (!c) return;
      selectedCell = { v1: d1[xi], v2: d2[yi] };
      paint();
      const params = { ...slice.fixed, [dims[0].key]: d1[xi] };
      if (dims.length > 1) params[dims[1].key] = d2[yi];
      setOverlay(r.indicatorId, r.spec, params, r.ohlc, c.m.roi);
      renderPriceOverlays();
      note.textContent = `目前疊圖參數：${paramText(r.spec, params)}（報酬 ${fmtPct(c.m.roi)}）`;
    });

    container.appendChild(canvas);
    const note = document.createElement('div');
    note.className = 'opt-item-note';
    note.textContent = (dims.length > 1 ? `橫軸 ${dims[0].label}／縱軸 ${dims[1].label}，` : `橫軸 ${dims[0].label}，`) +
      '色深=' + ({ fitness: '綜合 Fitness', roi: '報酬率', plateau: '高原分數' })[valueKey] +
      '；黃底=高原區（高原分數 P80）、金色虛線=高原邊界、白線=等值線、金框=目前選取；點格子切換股價圖疊加參數';
    container.appendChild(note);
  }

  function drawSparkline(container, history, noteText) {
    const w = 220, hgt = 50;
    const canvas = document.createElement('canvas');
    const dpr = window.devicePixelRatio || 1;
    canvas.width = w * dpr; canvas.height = hgt * dpr;
    canvas.style.width = w + 'px'; canvas.style.height = hgt + 'px';
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    const max = Math.max(...history), min = Math.min(...history);
    ctx.beginPath();
    history.forEach((v, i) => {
      const x = (i / (history.length - 1 || 1)) * (w - 4) + 2;
      const y = hgt - 4 - ((v - min) / (max - min || 1)) * (hgt - 8);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.strokeStyle = '#8B2E2E'; ctx.lineWidth = 2; ctx.stroke();
    container.appendChild(canvas);
    const note = document.createElement('div');
    note.className = 'opt-item-note';
    note.textContent = noteText;
    container.appendChild(note);
  }

  // ── 設定 tab（常駐表單，儲存到 localStorage，下次回測生效）──
  function renderSettingsForm() {
    const form = document.getElementById('opt-settings-form');
    if (!form || !window.Optimizer) return;
    const c = window.Optimizer.normalizeConfig(optConfig);
    const sel = (name, label, opts, cur) => `<label class="opt-field">${label}
      <select name="${name}">${opts.map(([v, l]) => `<option value="${v}"${String(cur) === String(v) ? ' selected' : ''}>${l}</option>`).join('')}</select></label>`;
    const num = (name, label, cur, step = 'any') => `<label class="opt-field">${label}
      <input type="number" name="${name}" value="${cur}" step="${step}"></label>`;
    const date = (name, label, cur) => `<label class="opt-field">${label}
      <input type="date" name="${name}" value="${cur || ''}"></label>`;
    form.innerHTML = `
      <div class="opt-form-section">回測方法與範圍</div>
      ${sel('method', '回測方法', [['normal', '一般回測'], ['montecarlo', '蒙地卡羅'], ['wfe', 'Walk-Forward（WFE）']], c.method)}
      ${sel('algorithm', '搜尋演算法', [['auto', '自動（組合少走網格，多走 PSO/貝氏）'], ['grid', '網格搜尋'], ['ga', '遺傳演算法'], ['pso', '粒子群 PSO'], ['bayes', '貝氏優化']], c.algorithm)}
      ${sel('objective', '目標函數', [['roi', '報酬率'], ['sharpe', 'Sharpe']], c.objective)}
      ${date('range.from', '回測起日（留空=全部）', c.range.from)}
      ${date('range.to', '回測迄日（留空=全部）', c.range.to)}
      ${num('seed', '隨機種子（留空=隨機）', c.seed == null ? '' : c.seed, 1)}
      <div class="opt-form-section">Fitness 權重（0 = 停用該項）</div>
      ${num('weights.base', '基礎目標', c.weights.base, 0.1)}
      ${num('weights.plateau', '高原分數', c.weights.plateau, 0.1)}
      ${num('weights.sharpe', 'Sharpe', c.weights.sharpe, 0.1)}
      ${num('weights.mdd', '最大回撤（懲罰）', c.weights.mdd, 0.1)}
      ${num('weights.trades', '交易筆數（10 筆飽和）', c.weights.trades, 0.1)}
      ${num('weights.xwin', '跨視窗平均績效', c.weights.xwin, 0.1)}
      <div class="opt-form-section">高原分數</div>
      ${num('plateau.radius', '鄰域半徑（步數）', c.plateau.radius, 1)}
      ${sel('plateau.metric', '評分指標', [['roi', '報酬率'], ['sharpe', 'Sharpe'], ['mdd', '最大回撤']], c.plateau.metric)}
      ${num('plateau.lambda', 'λ（鄰域方差懲罰）', c.plateau.lambda, 0.1)}
      <div class="opt-form-section">Walk-Forward</div>
      ${num('wfa.isBars', 'IS 視窗長度（K棒）', c.wfa.isBars, 1)}
      ${num('wfa.oosBars', 'OOS 視窗長度（K棒）', c.wfa.oosBars, 1)}
      ${num('wfa.step', '滾動步長（K棒）', c.wfa.step, 1)}
      <div class="opt-form-section">蒙地卡羅</div>
      ${num('mc.runs', '模擬次數', c.mc.runs, 10)}
      ${sel('mc.mode', '重抽樣單位', [['trades', '逐筆交易'], ['daily', '日報酬']], c.mc.mode)}
      <div class="opt-form-actions">
        <button type="submit" class="btn-primary">儲存設定</button>
        <span class="tech-price-status" id="opt-settings-status"></span>
      </div>`;
    form.onsubmit = e => {
      e.preventDefault();
      const cfg = {};
      const set = (path, v) => {
        const keys = path.split('.');
        let o = cfg;
        for (let i = 0; i < keys.length - 1; i++) o = o[keys[i]] = o[keys[i]] || {};
        o[keys[keys.length - 1]] = v;
      };
      for (const inp of form.querySelectorAll('[name]')) {
        const raw = inp.value.trim();
        if (inp.name === 'seed') set('seed', raw === '' ? null : +raw);
        else if (inp.name.startsWith('range.')) set(inp.name, raw === '' ? null : raw);
        else if (inp.type === 'number') set(inp.name, raw === '' ? 0 : +raw);
        else set(inp.name, raw);
      }
      optConfig = cfg;
      localStorage.setItem('tech-opt-config', JSON.stringify(cfg));
      const st = document.getElementById('opt-settings-status');
      if (st) st.textContent = '已儲存；點「回測最佳化參數並疊圖」以新設定重新計算';
    };
  }

  function bootOptimize() {
    document.getElementById('tech-optimize-btn')?.addEventListener('click', runOptimization);
    document.querySelectorAll('#opt-tabs .opt-tab').forEach(btn => {
      btn.addEventListener('click', () => {
        activeOptTab = btn.dataset.tab;
        document.querySelectorAll('#opt-tabs .opt-tab').forEach(b => b.classList.toggle('active', b === btn));
        document.querySelectorAll('#tech-opt-card .opt-pane').forEach(p => { p.hidden = p.dataset.pane !== activeOptTab; });
        renderActivePane();
      });
    });
    renderSettingsForm();
  }

  // ── 除錯/驗證掛鉤：indicators.json 為空時仍可從 console 驗證回測管線 ──
  // 用法：TechDebug.loadFixture(); TechDebug.run('rsi')
  function genSyntheticRows(n = 500) {
    const rows = [];
    let price = 100;
    const start = Date.UTC(2024, 0, 1);
    for (let i = 0; i < n; i++) {
      price *= 1 + 0.0004 + Math.sin(i / 25) * 0.01 + (Math.random() - 0.5) * 0.02;
      const open = price * (1 + (Math.random() - 0.5) * 0.005);
      rows.push({
        date: new Date(start + i * 86400000).toISOString().slice(0, 10),
        open, high: Math.max(open, price) * 1.01, low: Math.min(open, price) * 0.99,
        close: price, volume: 1e6 * (1 + Math.random()),
      });
    }
    return rows;
  }
  window.TechnicalModule = {
    // 主題切換是畫死的 canvas/SVG 顏色，得重畫一次才會生效（main.js 呼叫）
    rebuildTheme() { render(); },
  };
  window.TechDebug = {
    loadFixture(n) {
      lastRows = genSyntheticRows(n);
      lastSymbol = 'TEST';
      drawPriceChart(lastSymbol, lastRows);
      const st = document.getElementById('stock-status');
      if (st) st.textContent = `TEST 合成資料已載入（${lastRows.length} 根）`;
    },
    run(id) { if (id) selected.add(id); return runOptimization(); },
    setConfig(c) { optConfig = c || {}; renderSettingsForm(); },
    results: () => optResults,
  };

  // ── Boot ──
  function boot() {
    const canvas = document.getElementById('tech-map-canvas');
    bootPriceChart();
    bootOptimize();
    if (!canvas) return;
    canvas.style.cursor = 'grab';
    canvas.addEventListener('pointerdown', onPointerDown);
    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerUp);
    document.querySelectorAll('.tech-view-btn').forEach(b =>
      b.addEventListener('click', () => setViewMode(b.dataset.view))
    );
    init();
  }

  document.addEventListener('DOMContentLoaded', boot);

  // re-init if tab clicked before DOMContentLoaded resolved (edge case)
  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('tabM3')?.addEventListener('click', () => {
      if (indicators.length === 0) init();
    });
  });
})();
