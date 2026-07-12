/* ================================================================
   backtest.js — 指標定義（SPECS）與單次回測核心
   參數搜尋（網格/GA/PSO/貝氏）在 optimizer.js
   ================================================================ */
(function () {
  'use strict';

  // ── numeric helpers ──
  function sma(arr, p) {
    const out = new Array(arr.length).fill(null);
    let sum = 0;
    for (let i = 0; i < arr.length; i++) {
      sum += arr[i];
      if (i >= p) sum -= arr[i - p];
      if (i >= p - 1) out[i] = sum / p;
    }
    return out;
  }

  function ema(arr, p) {
    const out = new Array(arr.length).fill(null);
    const k = 2 / (p + 1);
    let prev = null;
    for (let i = 0; i < arr.length; i++) {
      prev = prev == null ? arr[i] : arr[i] * k + prev * (1 - k);
      out[i] = prev;
    }
    return out;
  }

  function stddev(arr, p) {
    const out = new Array(arr.length).fill(null);
    for (let i = p - 1; i < arr.length; i++) {
      let mean = 0;
      for (let j = i - p + 1; j <= i; j++) mean += arr[j];
      mean /= p;
      let v = 0;
      for (let j = i - p + 1; j <= i; j++) v += (arr[j] - mean) ** 2;
      out[i] = Math.sqrt(v / p);
    }
    return out;
  }

  function rollingMax(arr, p) {
    const out = new Array(arr.length).fill(null);
    for (let i = p - 1; i < arr.length; i++) out[i] = Math.max(...arr.slice(i - p + 1, i + 1));
    return out;
  }

  function rollingMin(arr, p) {
    const out = new Array(arr.length).fill(null);
    for (let i = p - 1; i < arr.length; i++) out[i] = Math.min(...arr.slice(i - p + 1, i + 1));
    return out;
  }

  function rsiCalc(closes, p) {
    const out = new Array(closes.length).fill(null);
    let gain = 0, loss = 0;
    for (let i = 1; i < closes.length; i++) {
      const diff = closes[i] - closes[i - 1];
      const g = Math.max(diff, 0), l = Math.max(-diff, 0);
      if (i < p) { gain += g; loss += l; continue; }
      if (i === p) { gain = (gain + g) / p; loss = (loss + l) / p; }
      else { gain = (gain * (p - 1) + g) / p; loss = (loss * (p - 1) + l) / p; }
      out[i] = loss === 0 ? 100 : 100 - 100 / (1 + gain / loss);
    }
    return out;
  }

  function atrCalc(highs, lows, closes, p) {
    const tr = closes.map((c, i) => i === 0 ? highs[i] - lows[i]
      : Math.max(highs[i] - lows[i], Math.abs(highs[i] - closes[i - 1]), Math.abs(lows[i] - closes[i - 1])));
    return sma(tr, p);
  }

  function normalize01(arrays, scale = 100) {
    let min = Infinity, max = -Infinity;
    arrays.forEach(arr => arr.forEach(v => { if (v != null) { if (v < min) min = v; if (v > max) max = v; } }));
    const span = (max - min) || 1;
    return arrays.map(arr => arr.map(v => v == null ? null : ((v - min) / span) * scale));
  }

  // ── indicator specs: params / series(overlay) / signal(backtest) ──
  // 新增一個指標要動兩個檔案，id 必須完全一致（大小寫敏感）：
  //   1. 3-技術指標/indicators.json：加一筆 {id, name, name_en, formula, facet_scores, ...}（圖譜/雷達圖用）
  //   2. 這裡的 SPECS：加 [id]: { params, overlayAxis, series(), signal() }（回測/疊圖用）
  // 兩邊 id 對不上時，technical.js 開頭的 checkSpecCoverage() 會在 console 印警告，不會靜默失效。
  const SPECS = {
    moving_average: {
      params: [{ key: 'period', label: '週期', min: 20, max: 300, step: 20, default: 200 }],
      overlayAxis: 'price',
      series(o, p) { return { 'SMA': sma(o.closes, p.period) }; },
      signal(o, p) { const s = sma(o.closes, p.period); return o.closes.map((c, i) => s[i] != null && c > s[i] ? 1 : 0); },
    },
    ema20: {
      params: [{ key: 'period', label: '週期', min: 5, max: 60, step: 5, default: 20 }],
      overlayAxis: 'price',
      series(o, p) { return { 'EMA': ema(o.closes, p.period) }; },
      signal(o, p) { const s = ema(o.closes, p.period); return o.closes.map((c, i) => s[i] != null && c > s[i] ? 1 : 0); },
    },
    rsi: {
      params: [
        { key: 'period', label: '週期', min: 5, max: 30, step: 1, default: 14 },
        { key: 'band', label: '超買超賣帶寬', min: 5, max: 30, step: 5, default: 20 },
      ],
      overlayAxis: 'osc',
      series(o, p) { return { 'RSI': rsiCalc(o.closes, p.period) }; },
      signal(o, p) {
        const r = rsiCalc(o.closes, p.period);
        const lo = 50 - p.band, hi = 50 + p.band;
        let pos = 0;
        return o.closes.map((_, i) => {
          if (r[i] == null) return 0;
          if (r[i] < lo) pos = 1; else if (r[i] > hi) pos = 0;
          return pos;
        });
      },
    },
    atr: {
      params: [
        { key: 'period', label: '週期', min: 5, max: 30, step: 1, default: 14 },
        { key: 'mult', label: 'ATR 倍數', min: 1, max: 4, step: 0.5, default: 2 },
      ],
      overlayAxis: 'price',
      series(o, p) {
        const atr = atrCalc(o.highs, o.lows, o.closes, p.period);
        return {
          'ATR上緣': o.closes.map((c, i) => atr[i] == null ? null : c + p.mult * atr[i]),
          'ATR下緣': o.closes.map((c, i) => atr[i] == null ? null : c - p.mult * atr[i]),
        };
      },
      signal(o, p) {
        const atr = atrCalc(o.highs, o.lows, o.closes, p.period);
        let pos = 0;
        return o.closes.map((c, i) => {
          if (i === 0 || atr[i - 1] == null) return 0;
          if (c > o.closes[i - 1] + p.mult * atr[i - 1]) pos = 1;
          else if (c < o.closes[i - 1] - p.mult * atr[i - 1]) pos = 0;
          return pos;
        });
      },
    },
    obv: {
      params: [{ key: 'period', label: '平滑週期', min: 5, max: 50, step: 5, default: 20 }],
      overlayAxis: 'osc',
      displayNormalize: true,
      series(o, p) {
        const obv = obvCalc(o.closes, o.volumes);
        return { 'OBV': obv, 'OBV_MA': sma(obv, p.period) };
      },
      signal(o, p) {
        const obv = obvCalc(o.closes, o.volumes);
        const ma = sma(obv, p.period);
        return obv.map((v, i) => ma[i] != null && v > ma[i] ? 1 : 0);
      },
    },
    pivot: {
      params: [],
      overlayAxis: 'price',
      series(o) {
        const { P, R1, S1 } = pivotCalc(o);
        return { 'Pivot P': P, 'Pivot R1': R1, 'Pivot S1': S1 };
      },
      signal(o) {
        const { P } = pivotCalc(o);
        return o.closes.map((c, i) => P[i] != null && c > P[i] ? 1 : 0);
      },
    },
    vwap: {
      params: [],
      overlayAxis: 'price',
      series(o) { return { 'VWAP': vwapCalc(o) }; },
      signal(o) { const v = vwapCalc(o); return o.closes.map((c, i) => v[i] != null && c > v[i] ? 1 : 0); },
    },
    macd: {
      params: [
        { key: 'fast', label: '快線', min: 6, max: 15, step: 1, default: 12 },
        { key: 'slow', label: '慢線', min: 20, max: 30, step: 2, default: 26 },
        { key: 'signal', label: '訊號線', min: 5, max: 12, step: 1, default: 9 },
      ],
      overlayAxis: 'osc',
      displayNormalize: true,
      series(o, p) {
        const { dif, dea } = macdCalc(o.closes, p);
        return { 'DIF': dif, 'DEA': dea };
      },
      signal(o, p) {
        const { dif, dea } = macdCalc(o.closes, p);
        return dif.map((v, i) => v != null && dea[i] != null && v > dea[i] ? 1 : 0);
      },
    },
    bollinger_bands: {
      params: [
        { key: 'period', label: '週期', min: 10, max: 40, step: 2, default: 20 },
        { key: 'mult', label: '標準差倍數', min: 1, max: 3, step: 0.25, default: 2 },
      ],
      overlayAxis: 'price',
      series(o, p) {
        const mid = sma(o.closes, p.period), sd = stddev(o.closes, p.period);
        return {
          'BB上軌': mid.map((m, i) => m == null ? null : m + p.mult * sd[i]),
          'BB中軌': mid,
          'BB下軌': mid.map((m, i) => m == null ? null : m - p.mult * sd[i]),
        };
      },
      signal(o, p) {
        const mid = sma(o.closes, p.period), sd = stddev(o.closes, p.period);
        let pos = 0;
        return o.closes.map((c, i) => {
          if (mid[i] == null) return 0;
          const upper = mid[i] + p.mult * sd[i], lower = mid[i] - p.mult * sd[i];
          if (c > upper) pos = 1; else if (c < lower) pos = 0;
          return pos;
        });
      },
    },
    stochastic: {
      params: [
        { key: 'kPeriod', label: '%K 週期', min: 5, max: 21, step: 2, default: 14 },
        { key: 'dPeriod', label: '%D 週期', min: 2, max: 9, step: 1, default: 3 },
        { key: 'smooth', label: '%K 平滑', min: 2, max: 6, step: 1, default: 3 },
      ],
      overlayAxis: 'osc',
      series(o, p) {
        const { k, d } = stochCalc(o, p);
        return { '%K': k, '%D': d };
      },
      signal(o, p) {
        const { k, d } = stochCalc(o, p);
        return k.map((v, i) => v != null && d[i] != null && v > d[i] ? 1 : 0);
      },
    },
    ichimoku: {
      params: [
        { key: 'tenkan', label: '轉換線', min: 5, max: 15, step: 1, default: 9 },
        { key: 'kijun', label: '基準線', min: 20, max: 40, step: 2, default: 26 },
        { key: 'senkouB', label: '先行帶B', min: 40, max: 80, step: 5, default: 52 },
        { key: 'chikouShift', label: '遲行帶位移', min: 15, max: 35, step: 5, default: 26 },
      ],
      overlayAxis: 'price',
      series(o, p) {
        const { tenkan, kijun, spanA, spanB } = ichimokuCalc(o, p);
        return { '轉換線': tenkan, '基準線': kijun, '先行帶A': spanA, '先行帶B': spanB };
      },
      signal(o, p) {
        const { spanA, spanB } = ichimokuCalc(o, p);
        return o.closes.map((c, i) => {
          if (spanA[i] == null || spanB[i] == null) return 0;
          return c > Math.max(spanA[i], spanB[i]) ? 1 : 0;
        });
      },
    },
  };

  function obvCalc(closes, volumes) {
    const out = new Array(closes.length).fill(0);
    for (let i = 1; i < closes.length; i++) {
      out[i] = out[i - 1] + (closes[i] > closes[i - 1] ? volumes[i] : closes[i] < closes[i - 1] ? -volumes[i] : 0);
    }
    return out;
  }

  function pivotCalc(o) {
    const P = new Array(o.closes.length).fill(null);
    const R1 = new Array(o.closes.length).fill(null);
    const S1 = new Array(o.closes.length).fill(null);
    for (let i = 1; i < o.closes.length; i++) {
      const p = (o.highs[i - 1] + o.lows[i - 1] + o.closes[i - 1]) / 3;
      P[i] = p; R1[i] = 2 * p - o.lows[i - 1]; S1[i] = 2 * p - o.highs[i - 1];
    }
    return { P, R1, S1 };
  }

  function vwapCalc(o) {
    const out = new Array(o.closes.length).fill(null);
    let cumPV = 0, cumV = 0;
    for (let i = 0; i < o.closes.length; i++) {
      const typical = (o.highs[i] + o.lows[i] + o.closes[i]) / 3;
      cumPV += typical * o.volumes[i]; cumV += o.volumes[i];
      out[i] = cumV > 0 ? cumPV / cumV : null;
    }
    return out;
  }

  function macdCalc(closes, p) {
    const fast = ema(closes, p.fast), slow = ema(closes, p.slow);
    const dif = fast.map((f, i) => f == null || slow[i] == null ? null : f - slow[i]);
    const dea = ema(dif.map(v => v == null ? 0 : v), p.signal);
    return { dif, dea };
  }

  function stochCalc(o, p) {
    const hh = rollingMax(o.highs, p.kPeriod), ll = rollingMin(o.lows, p.kPeriod);
    const rawK = o.closes.map((c, i) => hh[i] == null ? null : (hh[i] === ll[i] ? 50 : (c - ll[i]) / (hh[i] - ll[i]) * 100));
    const k = sma(rawK.map(v => v == null ? 0 : v), p.smooth).map((v, i) => rawK[i] == null ? null : v);
    const d = sma(k.map(v => v == null ? 0 : v), p.dPeriod).map((v, i) => k[i] == null ? null : v);
    return { k, d };
  }

  function ichimokuCalc(o, p) {
    const hh9 = rollingMax(o.highs, p.tenkan), ll9 = rollingMin(o.lows, p.tenkan);
    const hh26 = rollingMax(o.highs, p.kijun), ll26 = rollingMin(o.lows, p.kijun);
    const hh52 = rollingMax(o.highs, p.senkouB), ll52 = rollingMin(o.lows, p.senkouB);
    const tenkan = hh9.map((h, i) => h == null ? null : (h + ll9[i]) / 2);
    const kijun = hh26.map((h, i) => h == null ? null : (h + ll26[i]) / 2);
    const spanARaw = tenkan.map((t, i) => t == null || kijun[i] == null ? null : (t + kijun[i]) / 2);
    const spanBRaw = hh52.map((h, i) => h == null ? null : (h + ll52[i]) / 2);
    // 先行帶依基準線週期向未來位移，對齊到目前 K 棒時取「位移前 chikouShift 根」的值
    const shift = p.chikouShift;
    const spanA = spanARaw.map((_, i) => i >= shift ? spanARaw[i - shift] : null);
    const spanB = spanBRaw.map((_, i) => i >= shift ? spanBRaw[i - shift] : null);
    return { tenkan, kijun, spanA, spanB };
  }

  // ── backtest core ──
  // positions[i] = 該根收盤後決定、於 i→i+1 持有的倉位（1 做多 / 0 空手）。
  // start/end 限定「評估區間」；signal 一律以全序列計算，避免指標暖機期損失。
  function runBacktest(ohlc, positions, opts = {}) {
    const closes = ohlc.closes;
    const N = closes.length;
    const start = Math.max(0, opts.start ?? 0);
    const end = Math.min(N - 1, opts.end ?? N - 1);
    const ann = opts.annualize ?? 252;
    const bars = Math.max(end - start + 1, 1);

    const equityCurve = new Float64Array(bars);
    const barReturns = new Float64Array(bars);
    equityCurve[0] = 1;
    let equity = 1, peak = 1, maxDrawdown = 0, heldBars = 0;
    for (let i = start + 1; i <= end; i++) {
      const pos = positions[i - 1] ? 1 : 0;
      if (pos) heldBars++;
      const r = pos * (closes[i] - closes[i - 1]) / closes[i - 1];
      equity *= 1 + r;
      barReturns[i - start] = r;
      equityCurve[i - start] = equity;
      if (equity > peak) peak = equity;
      const dd = (peak - equity) / peak;
      if (dd > maxDrawdown) maxDrawdown = dd;
    }

    // 逐筆交易：0→1 於 i 以 closes[i] 進場、1→0 於 j 以 closes[j] 出場（與 equity 連乘一致）；
    // 區間末仍持倉 → 以最後收盤結算並標 open:true
    const trades = [];
    let entryI = -1;
    for (let j = start + 1; j <= end; j++) {
      if ((positions[j - 1] ? 1 : 0) && entryI < 0) entryI = j - 1;
      if (entryI >= 0 && (j === end || !(positions[j] ? 1 : 0))) {
        trades.push({
          entryIdx: entryI, exitIdx: j,
          entryDate: ohlc.dates ? ohlc.dates[entryI] : null,
          exitDate: ohlc.dates ? ohlc.dates[j] : null,
          entryPrice: closes[entryI], exitPrice: closes[j],
          ret: closes[j] / closes[entryI] - 1,
          bars: j - entryI,
          open: j === end && !!positions[j],
        });
        entryI = -1;
      }
    }

    const roi = equity - 1;
    const periods = bars - 1;
    const annRoi = periods > 0 ? Math.pow(1 + roi, ann / periods) - 1 : 0;
    let mean = 0;
    for (let i = 1; i < bars; i++) mean += barReturns[i];
    mean = periods > 0 ? mean / periods : 0;
    let variance = 0;
    for (let i = 1; i < bars; i++) variance += (barReturns[i] - mean) ** 2;
    const sd = Math.sqrt(periods > 0 ? variance / periods : 0);
    const sharpe = sd > 1e-12 ? (mean / sd) * Math.sqrt(ann) : 0;
    const wins = trades.filter(t => t.ret > 0).length;

    return {
      roi, annRoi, sharpe, maxDrawdown,
      winRate: trades.length ? wins / trades.length : null,
      tradeCount: trades.length,
      exposure: periods > 0 ? heldBars / periods : 0,
      trades, equityCurve, barReturns,
    };
  }

  function rangeValues(p) {
    const vals = [];
    for (let v = p.min; v <= p.max + 1e-9; v += p.step) vals.push(+v.toFixed(4));
    return vals;
  }

  function snapToStep(p, v) {
    v = Math.min(p.max, Math.max(p.min, v));
    return +(p.min + Math.round((v - p.min) / p.step) * p.step).toFixed(4);
  }

  window.Backtest = { SPECS, runBacktest, rangeValues, snapToStep, normalize01 };
})();
