/* ================================================================
   optimizer.js — 參數搜尋框架
   高原分數 / 綜合 fitness / 網格 / GA / PSO / 貝氏優化 /
   Walk-Forward / 蒙地卡羅 / marching squares 等高線
   規則：本檔不碰 DOM，Node 下 stub window 即可載入測試
   ================================================================ */
(function () {
  'use strict';

  const BT = () => window.Backtest;

  // ── 種子隨機數（cfg.seed 有值時結果可重現）──
  function mulberry32(seed) {
    let a = seed >>> 0;
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  const makeRng = seed => (seed == null ? Math.random : mulberry32(seed));

  function percentile(sorted, q) {
    if (!sorted.length) return null;
    const idx = (sorted.length - 1) * q;
    const lo = Math.floor(idx), hi = Math.ceil(idx);
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
  }

  // ── 設定 ──
  const DEFAULT_CONFIG = {
    method: 'normal',                 // normal | montecarlo | wfe
    range: { from: null, to: null },  // ISO 日期或 null（全範圍）
    algorithm: 'auto',                // auto | grid | ga | pso | bayes
    objective: 'roi',                 // roi | sharpe
    weights: { base: 1, plateau: 0, sharpe: 0, mdd: 0, trades: 0, xwin: 0 },
    plateau: { radius: 1, metric: 'roi', lambda: 1 }, // metric: roi | sharpe | mdd
    xwin: { segments: 4 },
    wfa: { isBars: 250, oosBars: 60, step: 60 },
    mc: { runs: 500, mode: 'trades' },                // trades | daily
    ga: { popSize: 24, generations: 20 },
    pso: { particles: 20, iters: 30, tolIters: 8 },
    bayes: { init: 8, iters: 40, xi: 0.01 },
    budget: 8000,        // 全域 runBacktest 次數上限
    gridAutoMax: 2000,   // auto 分派走網格的組合數上限
    gridHardMax: 30000,  // 手選網格的硬上限
    annualize: 252,
    seed: null,
  };

  function normalizeConfig(cfg) {
    const out = JSON.parse(JSON.stringify(DEFAULT_CONFIG));
    (function merge(dst, src) {
      if (!src) return;
      for (const k of Object.keys(src)) {
        if (src[k] && typeof src[k] === 'object' && !Array.isArray(src[k]) &&
            dst[k] && typeof dst[k] === 'object') merge(dst[k], src[k]);
        else if (src[k] !== undefined) dst[k] = src[k];
      }
    })(out, cfg);
    return out;
  }

  // ── 日期範圍 → 索引（ponytail: 線性掃描，N ≤ 幾千根無感）──
  function resolveRange(ohlc, range) {
    const dates = ohlc.dates || [];
    const N = ohlc.closes.length;
    let s = 0, e = N - 1;
    if (range && range.from) while (s < N - 1 && String(dates[s]) < range.from) s++;
    if (range && range.to) while (e > 0 && String(dates[e]).slice(0, range.to.length) > range.to) e--;
    if (e <= s) { s = 0; e = N - 1; }
    return { s, e };
  }

  // ── 記憶化 evaluator：同一組參數只跑一次 runBacktest ──
  function makeEvaluator(spec, ohlc, config, rangeIdx) {
    const cache = new Map();
    let evals = 0;
    const key = params => spec.params.map(p => params[p.key]).join(',');
    function entryOf(params) {
      const k = key(params);
      let ent = cache.get(k);
      if (ent) return ent;
      const positions = spec.signal(ohlc, params);
      const metrics = BT().runBacktest(ohlc, positions, { start: rangeIdx.s, end: rangeIdx.e, annualize: config.annualize });
      let xwin = null;
      if (config.weights.xwin) { // 跨視窗平均：同組參數切 k 段各算 objective 取平均（不重新優化）
        const segs = Math.max(2, config.xwin.segments);
        const len = rangeIdx.e - rangeIdx.s + 1;
        const objs = [];
        for (let i = 0; i < segs; i++) {
          const ss = rangeIdx.s + Math.floor(len * i / segs);
          const ee = i === segs - 1 ? rangeIdx.e : rangeIdx.s + Math.floor(len * (i + 1) / segs);
          if (ee - ss < 2) continue;
          const m = BT().runBacktest(ohlc, positions, { start: ss, end: ee, annualize: config.annualize });
          objs.push(objectiveOf(m, config));
        }
        xwin = objs.length ? objs.reduce((a, b) => a + b, 0) / objs.length : 0;
      }
      ent = { params: { ...params }, metrics, xwin };
      cache.set(k, ent);
      evals++;
      return ent;
    }
    return {
      spec, ohlc, config, rangeIdx, cache, key, entryOf,
      evalBase: params => entryOf(params).metrics,
      count: () => evals,
      exhausted: () => evals >= config.budget,
    };
  }

  const objectiveOf = (m, config) => config.objective === 'sharpe' ? m.sharpe : m.roi;
  const metricOf = (m, name) => name === 'sharpe' ? m.sharpe : name === 'mdd' ? -m.maxDrawdown : m.roi;
  const metricsLite = m => ({ roi: m.roi, annRoi: m.annRoi, sharpe: m.sharpe, maxDrawdown: m.maxDrawdown, winRate: m.winRate, tradeCount: m.tradeCount });

  // ── 高原分數：鄰域（含自身）metric 的 mean − λ·std，越高越「穩」──
  // 預設全鄰域 (2r+1)^d（網格模式全在快取，零額外成本）；
  // opts.axial: 只沿各軸 ±step（稀疏取樣當 fitness 用，控制額外評估次數）；
  // opts.dims: 鄰域限定在指定維（切片視圖用，off-slice 不觸發評估）。
  function plateauScore(ev, params, opts = {}) {
    const { radius, metric, lambda } = ev.config.plateau;
    const ps = opts.dims ? ev.spec.params.filter(p => opts.dims.includes(p.key)) : ev.spec.params;
    const snap = v => +v.toFixed(4);
    const vals = [];
    const push = q => vals.push(metricOf(ev.evalBase(q), metric));
    push(params);
    if (opts.axial) {
      for (const p of ps) for (let o = 1; o <= radius; o++) for (const sgn of [1, -1]) {
        const v = snap(params[p.key] + sgn * o * p.step);
        if (v < p.min - 1e-9 || v > p.max + 1e-9) continue;
        push({ ...params, [p.key]: v });
      }
    } else {
      (function rec(idx, acc, moved) {
        if (idx === ps.length) { if (moved) push({ ...params, ...acc }); return; }
        const p = ps[idx];
        for (let o = -radius; o <= radius; o++) {
          const v = snap(params[p.key] + o * p.step);
          if (v < p.min - 1e-9 || v > p.max + 1e-9) continue;
          acc[p.key] = v;
          rec(idx + 1, acc, moved || o !== 0);
        }
      })(0, {}, false);
    }
    const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
    const sd = Math.sqrt(vals.reduce((a, b) => a + (b - mean) ** 2, 0) / vals.length);
    return mean - lambda * sd;
  }

  // ── 綜合 fitness（權重可配置；plateauVal 給定時直接用，否則稀疏 axial 現算）──
  function fitnessOf(ev, params, plateauVal) {
    const ent = ev.entryOf(params);
    const m = ent.metrics;
    const w = ev.config.weights;
    let f = w.base * objectiveOf(m, ev.config);
    if (w.sharpe) f += w.sharpe * m.sharpe;
    if (w.mdd) f -= w.mdd * m.maxDrawdown;
    if (w.trades) f += w.trades * Math.min(m.tradeCount, 10) / 10; // 飽和於 10 筆：獎勵「有足夠交易」而非越多越好
    if (w.xwin) f += w.xwin * (ent.xwin || 0);
    if (w.plateau) f += w.plateau * (plateauVal != null ? plateauVal : plateauScore(ev, params, { axial: true }));
    return f;
  }

  // ── 主執行緒讓渡：累積 ~30ms 就讓出一次 macrotask ──
  function makeTicker() {
    let last = Date.now();
    return async function tick() {
      const now = Date.now();
      if (now - last > 30) { last = now; await new Promise(r => setTimeout(r, 0)); }
    };
  }

  // ── 網格搜尋（全枚舉 → 高原分數後處理 → fitness 排名）──
  async function gridSearch(ev, tick, progress) {
    const ps = ev.spec.params;
    const lists = ps.map(BT().rangeValues);
    const combos = [];
    (function rec(idx, acc) {
      if (idx === ps.length) { combos.push({ ...acc }); return; }
      for (const v of lists[idx]) { acc[ps[idx].key] = v; rec(idx + 1, acc); }
    })(0, {});
    let i = 0;
    for (const c of combos) {
      ev.evalBase(c);
      if (++i % 25 === 0) { await tick(); progress && progress('grid', i, combos.length, ev.count()); }
    }
    let best = null;
    for (const c of combos) {
      const plateau = plateauScore(ev, c); // 全鄰域，全在快取
      const fitness = fitnessOf(ev, c, plateau);
      if (!best || fitness > best.fitness) best = { params: c, fitness, plateau };
    }
    return { best, history: null };
  }

  // ── 遺傳演算法 ──
  async function gaSearch(ev, fitness, rng, tick, progress) {
    const ps = ev.spec.params;
    const { popSize, generations } = ev.config.ga;
    const snapRand = p => BT().snapToStep(p, p.min + rng() * (p.max - p.min));
    let pop = Array.from({ length: popSize }, () => Object.fromEntries(ps.map(p => [p.key, snapRand(p)])));
    let best = null;
    const history = [];
    for (let gen = 0; gen < generations && !ev.exhausted(); gen++) {
      const scored = [];
      for (const ind of pop) { scored.push({ ind, fit: fitness(ind) }); await tick(); }
      scored.sort((a, b) => b.fit - a.fit);
      if (!best || scored[0].fit > best.fitness) best = { params: scored[0].ind, fitness: scored[0].fit };
      history.push(best.fitness);
      const survivors = scored.slice(0, Math.ceil(popSize / 3)).map(s => s.ind);
      const next = [...survivors];
      while (next.length < popSize) {
        const a = survivors[(rng() * survivors.length) | 0];
        const b = survivors[(rng() * survivors.length) | 0];
        const child = {};
        ps.forEach(p => {
          let v = rng() < 0.5 ? a[p.key] : b[p.key];
          if (rng() < 0.2) v += (rng() - 0.5) * (p.max - p.min) * 0.2;
          child[p.key] = BT().snapToStep(p, v);
        });
        next.push(child);
      }
      pop = next;
      progress && progress('ga', gen + 1, generations, ev.count());
    }
    return { best, history };
  }

  // ── 粒子群（PSO，Clerc 常數；內部連續座標、評估時 snap 回網格）──
  async function psoSearch(ev, fitness, rng, tick, progress) {
    const ps = ev.spec.params;
    const { particles, iters, tolIters } = ev.config.pso;
    const d = ps.length;
    const toParams = x => Object.fromEntries(ps.map((p, i) => [p.key, BT().snapToStep(p, p.min + x[i] * (p.max - p.min))]));
    const X = [], V = [], pbestX = [], pbestF = [];
    let gbestX = null, gbestF = -Infinity, gbestParams = null;
    for (let i = 0; i < particles; i++) {
      X.push(Array.from({ length: d }, () => rng()));
      V.push(Array.from({ length: d }, () => (rng() - 0.5) * 0.2));
    }
    const history = [];
    let sinceImprove = 0;
    for (let it = 0; it < iters && !ev.exhausted(); it++) {
      let improved = false;
      for (let i = 0; i < particles; i++) {
        const params = toParams(X[i]);
        const f = fitness(params);
        if (it === 0 || f > pbestF[i]) { pbestF[i] = f; pbestX[i] = X[i].slice(); }
        if (f > gbestF) { gbestF = f; gbestX = X[i].slice(); gbestParams = params; improved = true; }
        await tick();
      }
      history.push(gbestF);
      sinceImprove = improved ? 0 : sinceImprove + 1;
      if (sinceImprove >= tolIters) break;
      for (let i = 0; i < particles; i++) {
        for (let k = 0; k < d; k++) {
          V[i][k] = 0.72 * V[i][k] + 1.49 * rng() * (pbestX[i][k] - X[i][k]) + 1.49 * rng() * (gbestX[k] - X[i][k]);
          X[i][k] = Math.min(1, Math.max(0, X[i][k] + V[i][k]));
        }
      }
      progress && progress('pso', it + 1, iters, ev.count());
    }
    return { best: { params: gbestParams, fitness: gbestF }, history };
  }

  // ── 貝氏優化：簡化 GP（RBF, ℓ=0.2, jitter 1e-4）+ Expected Improvement ──
  function cholesky(A) {
    const n = A.length;
    const L = Array.from({ length: n }, () => new Float64Array(n));
    for (let i = 0; i < n; i++) {
      for (let j = 0; j <= i; j++) {
        let s = A[i][j];
        for (let k = 0; k < j; k++) s -= L[i][k] * L[j][k];
        if (i === j) L[i][i] = Math.sqrt(Math.max(s, 1e-12));
        else L[i][j] = s / L[j][j];
      }
    }
    return L;
  }
  function solveLower(L, b) { // L y = b
    const n = L.length, y = new Float64Array(n);
    for (let i = 0; i < n; i++) {
      let s = b[i];
      for (let k = 0; k < i; k++) s -= L[i][k] * y[k];
      y[i] = s / L[i][i];
    }
    return y;
  }
  function solveUpperT(L, y) { // Lᵀ x = y
    const n = L.length, x = new Float64Array(n);
    for (let i = n - 1; i >= 0; i--) {
      let s = y[i];
      for (let k = i + 1; k < n; k++) s -= L[k][i] * x[k];
      x[i] = s / L[i][i];
    }
    return x;
  }
  const normPdf = z => Math.exp(-0.5 * z * z) / Math.sqrt(2 * Math.PI);
  function normCdf(z) { // Abramowitz–Stegun 26.2.17
    const t = 1 / (1 + 0.2316419 * Math.abs(z));
    const d = 0.3989422804014327 * Math.exp(-0.5 * z * z);
    const p = d * t * (0.31938153 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))));
    return z >= 0 ? 1 - p : p;
  }

  async function bayesSearch(ev, fitness, rng, tick, progress) {
    const ps = ev.spec.params;
    const d = ps.length;
    const cfg = ev.config.bayes;
    const ell2 = 2 * 0.2 * 0.2;
    const nMax = 120; // Cholesky O(n³) 上限，n=120 完全無感
    const toX = params => ps.map(p => (params[p.key] - p.min) / ((p.max - p.min) || 1));
    const randParams = () => Object.fromEntries(ps.map(p => [p.key, BT().snapToStep(p, p.min + rng() * (p.max - p.min))]));
    const kern = (a, b) => { let s = 0; for (let i = 0; i < d; i++) s += (a[i] - b[i]) ** 2; return Math.exp(-s / ell2); };
    const seen = new Set();
    const X = [], Y = [], P = [];
    async function observe(params) {
      const k = ev.key(params);
      if (seen.has(k)) return false;
      seen.add(k);
      X.push(toX(params)); P.push({ ...params }); Y.push(fitness(params));
      await tick();
      return true;
    }
    let guard = 0;
    while (X.length < Math.min(cfg.init, nMax) && guard++ < 500) await observe(randParams());
    const history = [];
    for (let it = 0; it < cfg.iters && !ev.exhausted() && X.length < nMax; it++) {
      const n = X.length;
      const mean = Y.reduce((a, b) => a + b, 0) / n;
      const sd = Math.sqrt(Y.reduce((a, b) => a + (b - mean) ** 2, 0) / n) || 1;
      const yn = Y.map(v => (v - mean) / sd);
      const K = Array.from({ length: n }, (_, i) => {
        const row = new Float64Array(n);
        for (let j = 0; j < n; j++) row[j] = kern(X[i], X[j]) + (i === j ? 1e-4 : 0);
        return row;
      });
      const L = cholesky(K);
      const alpha = solveUpperT(L, solveLower(L, yn));
      const yBest = Math.max(...yn);
      let bestCand = null, bestEI = -Infinity;
      for (let c = 0; c < 300; c++) { // 隨機候選取 EI 最大
        const cand = randParams();
        if (seen.has(ev.key(cand))) continue;
        const x = toX(cand);
        const ks = new Float64Array(n);
        for (let i = 0; i < n; i++) ks[i] = kern(x, X[i]);
        let mu = 0;
        for (let i = 0; i < n; i++) mu += ks[i] * alpha[i];
        const v = solveLower(L, ks);
        let s2 = 1 + 1e-4;
        for (let i = 0; i < n; i++) s2 -= v[i] * v[i];
        const s = Math.sqrt(Math.max(s2, 1e-12));
        const z = (mu - yBest - cfg.xi) / s;
        const ei = (mu - yBest - cfg.xi) * normCdf(z) + s * normPdf(z);
        if (ei > bestEI) { bestEI = ei; bestCand = cand; }
      }
      if (!bestCand) break; // 參數空間掃完
      await observe(bestCand);
      history.push(Math.max(...Y));
      progress && progress('bayes', it + 1, cfg.iters, ev.count());
    }
    let bi = 0;
    for (let i = 1; i < Y.length; i++) if (Y[i] > Y[bi]) bi = i;
    return { best: { params: P[bi], fitness: Y[bi] }, history };
  }

  // ── 切片：固定其餘維於 fixed，掃 keyX×keyY 兩維（快取重訪免費）──
  // 高原分數限定在切片維內，off-slice 鄰居不觸發額外評估
  async function evalSlice(ev, keyX, keyY, fixed) {
    const ps = ev.spec.params;
    const pX = ps.find(p => p.key === keyX);
    const pY = keyY ? ps.find(p => p.key === keyY) : null;
    const xs = BT().rangeValues(pX);
    const ys = pY ? BT().rangeValues(pY) : [null];
    const dims = pY ? [keyX, keyY] : [keyX];
    const tick = makeTicker();
    const cells = [];
    for (const vy of ys) {
      for (const vx of xs) {
        const params = { ...fixed, [keyX]: vx };
        if (pY) params[keyY] = vy;
        const m = ev.evalBase(params);
        const plateau = plateauScore(ev, params, { dims });
        cells.push({ v1: vx, v2: pY ? vy : undefined, fitness: fitnessOf(ev, params, plateau), plateau, m: metricsLite(m) });
        await tick();
      }
    }
    return { dims: pY ? [pX, pY] : [pX], cells, fixed: { ...fixed } };
  }

  // ── Walk-Forward：每視窗在 IS 重新優化，best 直接評 OOS ──
  function metricsFromReturns(returns, ann) {
    let eq = 1, peak = 1, mdd = 0;
    const curve = [1];
    for (const r of returns) {
      eq *= 1 + r;
      curve.push(eq);
      if (eq > peak) peak = eq;
      const dd = (peak - eq) / peak;
      if (dd > mdd) mdd = dd;
    }
    const n = returns.length;
    const mean = n ? returns.reduce((a, b) => a + b, 0) / n : 0;
    const sd = Math.sqrt(n ? returns.reduce((a, b) => a + (b - mean) ** 2, 0) / n : 0);
    return {
      roi: eq - 1,
      annRoi: n ? Math.pow(eq, ann / n) - 1 : 0,
      sharpe: sd > 1e-12 ? (mean / sd) * Math.sqrt(ann) : 0,
      maxDrawdown: mdd, equityCurve: curve,
    };
  }

  async function walkForward(spec, ohlc, config, algo, rng, progress) {
    const { s: s0, e: e0 } = resolveRange(ohlc, config.range);
    const { isBars, oosBars } = config.wfa;
    const step = Math.max(1, config.wfa.step);
    const dates = ohlc.dates;
    const wcfg = { ...config, budget: Math.max(500, Math.floor(config.budget / 2)) }; // 內層預算砍半
    const total = Math.max(0, Math.floor((e0 - s0 + 1 - isBars - oosBars) / step) + 1);
    const tick = makeTicker();
    const windows = [];
    const stitchedReturns = [], stitchedDates = [];
    for (let s = s0; s + isBars - 1 + oosBars <= e0; s += step) {
      const isR = { s, e: s + isBars - 1 };
      const oosR = { s: isR.e, e: isR.e + oosBars }; // 共用端點：首根 OOS 報酬用 IS 末日訊號，無前視
      const ev = makeEvaluator(spec, ohlc, wcfg, isR);
      const res = await runAlgo(algo, ev, rng, tick, null);
      const isM = ev.evalBase(res.best.params);
      const positions = spec.signal(ohlc, res.best.params);
      const oosM = BT().runBacktest(ohlc, positions, { start: oosR.s, end: oosR.e, annualize: config.annualize });
      for (let i = 1; i < oosM.barReturns.length; i++) {
        stitchedReturns.push(oosM.barReturns[i]);
        stitchedDates.push(dates ? dates[oosR.s + i] : null);
      }
      windows.push({
        isIdx: [isR.s, isR.e], oosIdx: [oosR.s, oosR.e],
        isDates: dates ? [dates[isR.s], dates[isR.e]] : null,
        oosDates: dates ? [dates[oosR.s], dates[oosR.e]] : null,
        bestParams: res.best.params,
        is: metricsLite(isM), oos: metricsLite(oosM),
        wfe: isM.annRoi > 0 ? oosM.annRoi / isM.annRoi : null, // IS ≤ 0 時 WFE 無意義
      });
      progress && progress('wfe', windows.length, total, null);
    }
    if (!windows.length) return null;
    const wfes = windows.map(w => w.wfe).filter(v => v != null).sort((a, b) => a - b);
    return {
      windows,
      stitched: { ...metricsFromReturns(stitchedReturns, config.annualize), dates: stitchedDates },
      avgWfe: wfes.length ? wfes.reduce((a, b) => a + b, 0) / wfes.length : null,
      medianWfe: wfes.length ? percentile(wfes, 0.5) : null,
      validWindows: wfes.length,
    };
  }

  // ── 蒙地卡羅：重抽樣日報酬（daily）或逐筆交易報酬（trades）──
  // ponytail: trades 模式 MDD 為逐筆近似（忽略持倉中回撤），daily 模式無此問題
  function monteCarlo(metrics, cfg, rng) {
    const runs = Math.max(10, cfg.runs);
    const finals = [], mdds = [];
    let envelope = null;
    if (cfg.mode === 'daily') {
      const rets = Array.from(metrics.barReturns.slice(1));
      const n = rets.length;
      if (!n) return null;
      const matrix = [];
      for (let r = 0; r < runs; r++) {
        let eq = 1, peak = 1, mdd = 0;
        const path = new Float64Array(n);
        for (let i = 0; i < n; i++) {
          eq *= 1 + rets[(rng() * n) | 0];
          path[i] = eq;
          if (eq > peak) peak = eq;
          const dd = (peak - eq) / peak;
          if (dd > mdd) mdd = dd;
        }
        matrix.push(path);
        finals.push(eq - 1); mdds.push(mdd);
      }
      const p5 = new Array(n), p50 = new Array(n), p95 = new Array(n);
      const col = new Float64Array(runs);
      for (let i = 0; i < n; i++) {
        for (let r = 0; r < runs; r++) col[r] = matrix[r][i];
        const sc = Array.from(col).sort((a, b) => a - b);
        p5[i] = percentile(sc, 0.05); p50[i] = percentile(sc, 0.5); p95[i] = percentile(sc, 0.95);
      }
      envelope = { p5, p50, p95 };
    } else {
      const rets = metrics.trades.map(t => t.ret);
      const n = rets.length;
      if (!n) return null;
      for (let r = 0; r < runs; r++) {
        let eq = 1, peak = 1, mdd = 0;
        for (let i = 0; i < n; i++) {
          eq *= 1 + rets[(rng() * n) | 0];
          if (eq > peak) peak = eq;
          const dd = (peak - eq) / peak;
          if (dd > mdd) mdd = dd;
        }
        finals.push(eq - 1); mdds.push(mdd);
      }
    }
    const fs = [...finals].sort((a, b) => a - b);
    const ds = [...mdds].sort((a, b) => a - b);
    const stat = arr => ({
      p5: percentile(arr, 0.05), p25: percentile(arr, 0.25), p50: percentile(arr, 0.5),
      p75: percentile(arr, 0.75), p95: percentile(arr, 0.95),
      mean: arr.reduce((a, b) => a + b, 0) / arr.length,
    });
    return {
      runs, mode: cfg.mode,
      finalRoi: stat(fs), maxDrawdown: stat(ds),
      probPositive: finals.filter(v => v > 0).length / finals.length,
      envelope,
    };
  }

  // ── marching squares：values[row][col] 對 thr 的等值線 ──
  // 回傳線段陣列 [x1,y1,x2,y2]（格點座標，col=x / row=y，可含小數）
  function marchingSquares(values, thr) {
    const segs = [];
    const rows = values.length, cols = rows ? values[0].length : 0;
    for (let y = 0; y < rows - 1; y++) {
      for (let x = 0; x < cols - 1; x++) {
        const tl = values[y][x], tr = values[y][x + 1], br = values[y + 1][x + 1], bl = values[y + 1][x];
        if (tl == null || tr == null || br == null || bl == null) continue;
        let idx = 0;
        if (tl > thr) idx |= 8;
        if (tr > thr) idx |= 4;
        if (br > thr) idx |= 2;
        if (bl > thr) idx |= 1;
        if (idx === 0 || idx === 15) continue;
        const t = (a, b) => (thr - a) / (b - a);
        const top = [x + t(tl, tr), y], right = [x + 1, y + t(tr, br)];
        const bottom = [x + t(bl, br), y + 1], left = [x, y + t(tl, bl)];
        const CASES = {
          1: [left, bottom], 2: [bottom, right], 3: [left, right], 4: [top, right],
          5: [top, right, left, bottom], 6: [top, bottom], 7: [top, left],
          8: [top, left], 9: [top, bottom], 10: [top, left, bottom, right],
          11: [top, right], 12: [left, right], 13: [bottom, right], 14: [left, bottom],
        };
        const pts = CASES[idx];
        for (let i = 0; i < pts.length; i += 2) segs.push([pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]]);
      }
    }
    return segs;
  }

  // ── 分派 ──
  const comboCount = spec => spec.params.reduce((acc, p) => acc * BT().rangeValues(p).length, 1);

  function pickAlgo(spec, config) {
    if (!spec.params.length) return 'none';
    if (config.algorithm && config.algorithm !== 'auto') return config.algorithm;
    if (comboCount(spec) <= config.gridAutoMax) return 'grid';
    return config.method === 'wfe' ? 'bayes' : 'pso'; // WFE 每視窗重優化，貝氏最省評估
  }

  async function runAlgo(algo, ev, rng, tick, progress) {
    const fitness = params => fitnessOf(ev, params);
    if (algo === 'grid') return gridSearch(ev, tick, progress);
    if (algo === 'ga') return gaSearch(ev, fitness, rng, tick, progress);
    if (algo === 'pso') return psoSearch(ev, fitness, rng, tick, progress);
    if (algo === 'bayes') return bayesSearch(ev, fitness, rng, tick, progress);
    throw new Error('未知演算法: ' + algo);
  }

  // ── 主入口 ──
  // progress(phase, i, total, evalCount) 進度回呼，可省略
  async function optimize(indicatorId, ohlc, userConfig, progress) {
    const spec = BT().SPECS[indicatorId];
    if (!spec) return null;
    const config = normalizeConfig(userConfig);
    const rng = makeRng(config.seed);
    const rangeIdx = resolveRange(ohlc, config.range);
    const algo = pickAlgo(spec, config);
    if (algo === 'grid' && comboCount(spec) > config.gridHardMax) {
      throw new Error(`參數組合 ${comboCount(spec)} 超過網格上限 ${config.gridHardMax}，請改用 PSO / 貝氏`);
    }
    const ev = makeEvaluator(spec, ohlc, config, rangeIdx);
    const tick = makeTicker();

    let result;
    if (algo === 'none') {
      const m = ev.evalBase({});
      result = { best: { params: {}, fitness: objectiveOf(m, config) }, history: null };
    } else {
      result = await runAlgo(algo, ev, rng, tick, progress);
    }
    const bestMetrics = ev.evalBase(result.best.params);
    const bestPlateau = spec.params.length
      ? plateauScore(ev, result.best.params, algo === 'grid' ? {} : { axial: true })
      : null;

    // 預設切片：前兩維，其餘固定在 best
    let grid = null;
    if (spec.params.length >= 1) {
      grid = await evalSlice(ev, spec.params[0].key, spec.params[1] ? spec.params[1].key : null, result.best.params);
    }

    // buy & hold 基準權益曲線
    const closes = ohlc.closes;
    const buyHold = new Float64Array(bestMetrics.equityCurve.length);
    for (let i = 0; i < buyHold.length; i++) buyHold[i] = closes[rangeIdx.s + i] / closes[rangeIdx.s];

    const out = {
      indicatorId, spec, config, mode: algo, rangeIdx,
      dates: ohlc.dates ? ohlc.dates.slice(rangeIdx.s, rangeIdx.e + 1) : null,
      best: {
        params: result.best.params, fitness: result.best.fitness,
        metrics: bestMetrics, plateau: bestPlateau,
        ret: bestMetrics.roi, // 沿用舊 overlay chip 契約
      },
      buyHold, grid,
      history: result.history || null,
      wfa: null, mc: null,
      evalCount: ev.count(),
      slice: (kx, ky) => evalSlice(ev, kx, ky, result.best.params), // UI 換維用（共用快取）
    };
    if (config.method === 'wfe' && spec.params.length) out.wfa = await walkForward(spec, ohlc, config, algo, rng, progress);
    if (config.method === 'montecarlo') out.mc = monteCarlo(bestMetrics, config.mc, rng);
    return out;
  }

  window.Optimizer = {
    optimize, DEFAULT_CONFIG, normalizeConfig, marchingSquares, comboCount,
    // 測試掛鉤（tests/opt-selftest.js 用）
    _internals: {
      mulberry32, percentile, cholesky, solveLower, solveUpperT, normCdf, normPdf,
      monteCarlo, resolveRange, plateauScore, makeEvaluator, fitnessOf,
      psoSearch, bayesSearch, metricsFromReturns, makeTicker,
    },
  };
})();
