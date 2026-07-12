/* ================================================================
   gauge.js — SVG 半圓弧 Gauge Chart + 語意徽章
   ================================================================ */

const GaugeChart = (() => {
  const ARC_LENGTH = 251.3; // Approximate semicircle path length for r=80

  const REGIME_CONFIG = {
    3: { label: '寬鬆 — 有利風險資產',   color: 'var(--color-down)', cls: 'bullish',  desc: '當前環境對風險資產有利，信用利差低、政策寬鬆、通膨穩定。' },
    2: { label: '中性偏多',              color: 'var(--color-accent)', cls: 'bullish',  desc: '環境溫和正向，基本面未見明顯壓力，可維持適度風險部位。' },
    1: { label: '中性偏保守',            color: 'var(--color-gold)', cls: 'cautious', desc: '出現部分壓力信號，建議降低風險敞口，留意政策轉向。' },
    0: { label: '緊縮 — 風險極高',       color: 'var(--color-up)', cls: 'bearish',  desc: '多重指標示警，信用環境緊縮，建議防禦性配置。' },
  };

  const SCORE_LABELS = [
    { min:  0.6, label: '強勢看多',     cls: 'bullish'  },
    { min:  0.2, label: '偏多',         cls: 'bullish'  },
    { min: -0.2, label: '中性',         cls: 'cautious' },
    { min: -0.6, label: '偏空',         cls: 'bearish'  },
    { min: -Infinity, label: '高度警戒', cls: 'bearish'  },
  ];

  function getScoreLabel(score) {
    return SCORE_LABELS.find(s => score >= s.min) || SCORE_LABELS[SCORE_LABELS.length - 1];
  }

  function getArcColor(score) {
    if (score >= 0.3)  return 'var(--color-success)';
    if (score >= -0.3) return 'var(--color-warning)';
    return 'var(--color-error)';
  }

  function getArcOffset(score) {
    // score: -1 → full offset (hidden), +1 → 0 (full arc)
    // Normalized: 0 (score=-1) to 1 (score=+1)
    const normalized = (score + 1) / 2;
    const clamped = Math.max(0, Math.min(1, normalized));
    return ARC_LENGTH * (1 - clamped);
  }

  function render(data) {
    const latest = DataService.getLatestScore(data);
    const regime = DataService.getLatestRegime(data);
    if (!latest) return;

    const score = latest.value;
    const regimeVal = regime ? regime.value : 2;
    const config = REGIME_CONFIG[regimeVal] || REGIME_CONFIG[2];
    const scoreLabel = getScoreLabel(score);

    // Gauge arc
    const arcEl = document.getElementById('gaugeArc');
    const targetOffset = getArcOffset(score);
    const arcColor = getArcColor(score);

    arcEl.style.stroke = arcColor;
    arcEl.style.transition = 'stroke-dashoffset 1.2s cubic-bezier(0.25, 0.46, 0.45, 0.94), stroke .5s';
    requestAnimationFrame(() => {
      arcEl.setAttribute('stroke-dashoffset', targetOffset);
    });

    // Score number with counting animation
    const gaugeValueEl = document.getElementById('gaugeValue');
    animateCounter(gaugeValueEl, score, 1200);
    gaugeValueEl.style.color = arcColor;

    // Regime badge
    const badgeEl = document.getElementById('regimeBadge');
    badgeEl.className = `regime-badge ${config.cls}`;
    const _ri = document.getElementById('regimeIcon');
    _ri.textContent = '';
    _ri.style.cssText = 'display:inline-block;width:8px;height:8px;background:' + config.color + ';';
    document.getElementById('regimeText').textContent = config.label;

    // Regime description
    document.getElementById('regimeDescription').textContent = config.desc;

    // Sub-score summary chips
    const subContainer = document.getElementById('subScoreSummary');
    subContainer.innerHTML = '';
    const subLabels = {
      CREDIT_SCORE: { name: '信用', color: 'var(--chart-color-2)' },
      POLICY_SCORE: { name: '政策', color: 'var(--chart-color-3)' },
      PRICEFX_SCORE: { name: '通膨/匯率', color: 'var(--chart-color-4)' },
    };
    for (const [key, meta] of Object.entries(subLabels)) {
      const arr = data.scores[key];
      if (!arr || !arr.length) continue;
      const val = arr[arr.length - 1].value;
      const chip = document.createElement('div');
      chip.className = 'info-chip';
      chip.innerHTML = `<span class="chip-label" style="color:${meta.color}">${meta.name}</span><span class="chip-value tabular-nums" style="color:${val >= 0 ? 'var(--color-success)' : 'var(--color-error)'}">${val >= 0 ? '+' : ''}${val.toFixed(2)}</span>`;
      subContainer.appendChild(chip);
    }
  }

  // Counting animation
  function animateCounter(el, target, duration) {
    const start = performance.now();
    const from = 0;
    function update(now) {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      const current = from + (target - from) * eased;
      el.textContent = (current >= 0 ? '+' : '') + current.toFixed(3);
      if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
  }

  // 渲染指定日期的 Gauge（接受預建的 scoreMaps）
  function renderForDate(scoreMaps, dateStr) {
    const macroVal = scoreMaps?.MACRO_SCORE?.get(dateStr);
    const regimeVal = scoreMaps?.REGIME?.get(dateStr);
    if (macroVal == null) return;

    const score = macroVal;
    const regimeNum = regimeVal != null ? Math.round(regimeVal) : 2;
    const config = REGIME_CONFIG[regimeNum] || REGIME_CONFIG[2];
    const arcColor = getArcColor(score);

    const arcEl = document.getElementById('gaugeArc');
    arcEl.style.stroke = arcColor;
    arcEl.style.transition = 'stroke-dashoffset .8s cubic-bezier(0.25, 0.46, 0.45, 0.94), stroke .4s';
    requestAnimationFrame(() => {
      arcEl.setAttribute('stroke-dashoffset', getArcOffset(score));
    });

    const gaugeValueEl = document.getElementById('gaugeValue');
    animateCounter(gaugeValueEl, score, 800);
    gaugeValueEl.style.color = arcColor;

    const badgeEl = document.getElementById('regimeBadge');
    badgeEl.className = `regime-badge ${config.cls}`;
    const _ri = document.getElementById('regimeIcon');
    _ri.textContent = '';
    _ri.style.cssText = 'display:inline-block;width:8px;height:8px;background:' + config.color + ';';
    document.getElementById('regimeText').textContent = config.label;
    document.getElementById('regimeDescription').textContent = config.desc;

    const subContainer = document.getElementById('subScoreSummary');
    subContainer.innerHTML = '';
    const subLabels = {
      CREDIT_SCORE:  { name: '信用',      color: 'var(--chart-color-2)' },
      POLICY_SCORE:  { name: '政策',      color: 'var(--chart-color-3)' },
      PRICEFX_SCORE: { name: '通膨/匯率', color: 'var(--chart-color-4)' },
    };
    for (const [key, meta] of Object.entries(subLabels)) {
      const val = scoreMaps?.[key]?.get(dateStr);
      if (val == null) continue;
      const chip = document.createElement('div');
      chip.className = 'info-chip';
      chip.innerHTML =
        `<span class="chip-label" style="color:${meta.color}">${meta.name}</span>` +
        `<span class="chip-value tabular-nums" style="color:${val >= 0 ? 'var(--color-success)' : 'var(--color-error)'}">` +
        `${val >= 0 ? '+' : ''}${val.toFixed(2)}</span>`;
      subContainer.appendChild(chip);
    }
  }

  return { render, renderForDate };
})();
