/* ================================================================
   data.js — 資料抓取與快取層
   資料來源：Supabase REST API（macro_scores + macro_raw）
   ================================================================ */

const DataService = (() => {
  'use strict';

  const SUPA_URL = 'https://yxydsxygylpzewumevsz.supabase.co';
  const SUPA_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inl4eWRzeHlneWxwemV3dW1ldnN6Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3OTExMjk2MywiZXhwIjoyMDk0Njg4OTYzfQ.LIfd-Aa9HLNAqkD5_UUL6pu2kZT1gESTjXwY8pfxs3o';
  const HDRS = { apikey: SUPA_KEY, Authorization: `Bearer ${SUPA_KEY}` };

  // macro_scores 分數欄位 → sub_scores 鍵（SUB_XXX）
  const SCORE_COLS = [
    'score_credit_spread', 'score_mortgage_spread', 'score_drblacbs',
    'score_net_liq_chg', 'score_dff', 'score_t10y2y',
    'score_jtsjol', 'score_jtsqur', 'score_babatotalsaus',
    'score_indpro', 'score_payems', 'score_dtwexbgs',
    'score_emvexrates', 'score_tic_grand_total',
  ];

  let _cache = null;
  let _loading = null;
  let _dimCache = null;
  let _scoreRows = null;   // 保留原始列，供 fetchDimScores 複用

  // ── 分頁抓取（Supabase 預設 1000 筆/頁）──────────────────────────
  async function _fetchAll(path) {
    const PAGE = 1000;
    let offset = 0;
    const all = [];
    while (true) {
      const resp = await fetch(`${SUPA_URL}${path}&limit=${PAGE}&offset=${offset}`, { headers: HDRS });
      if (!resp.ok) throw new Error(`Supabase ${resp.status}: ${path}`);
      const rows = await resp.json();
      all.push(...rows);
      if (rows.length < PAGE) break;
      offset += PAGE;
    }
    return all;
  }

  // ── 從 Supabase 組裝 data 結構 ────────────────────────────────────
  async function _fetchSupabase() {
    const cols = [
      'observation_date', 'macro_score', 'regime',
      'dim1_score', 'dim2_score', 'dim3_score', 'dim4_score', 'dim2_credibility',
      ...SCORE_COLS,
    ].join(',');

    // 同步發出：評分序列 + 指數序列
    const [scoreRows, idxRows] = await Promise.all([
      _fetchAll(`/rest/v1/macro_scores?select=${cols}&order=observation_date.asc`),
      _fetchAll(`/rest/v1/macro_raw?select=observation_date,ticker,raw_value&ticker=in.(SP500,NASDAQCOM,DJIA,RUT)&order=observation_date.asc`),
    ]);

    _scoreRows = scoreRows;

    const toSeries = (col) =>
      scoreRows.filter(r => r[col] != null).map(r => ({ date: r.observation_date, value: r[col] }));

    // sub_scores：score_xxx → SUB_XXX
    const sub_scores = {};
    for (const col of SCORE_COLS)
      sub_scores['SUB_' + col.replace('score_', '').toUpperCase()] = toSeries(col);

    // indices：依 ticker 分組
    const indices = {};
    for (const r of idxRows) {
      if (r.raw_value == null) continue;
      (indices[r.ticker] ??= []).push({ date: r.observation_date, value: r.raw_value });
    }

    const latest = scoreRows[scoreRows.length - 1];
    return {
      generated_at: latest ? latest.observation_date + ' (Supabase)' : '—',
      scores: {
        MACRO_SCORE:   toSeries('macro_score'),
        REGIME:        toSeries('regime'),
        CREDIT_SCORE:  toSeries('dim1_score'),
        POLICY_SCORE:  scoreRows
          .filter(r => r.dim2_score != null)
          .map(r => ({ date: r.observation_date, value: r.dim2_score / 2 })),
        PRICEFX_SCORE: toSeries('dim4_score'),
      },
      sub_scores,
      indices,
    };
  }

  function _parseDates(data) {
    for (const key of Object.keys(data.scores || {}))
      data.scores[key].forEach(d => { d._d = new Date(d.date); });
    for (const key of Object.keys(data.indices || {}))
      data.indices[key].forEach(d => { d._d = new Date(d.date); });
    for (const key of Object.keys(data.sub_scores || {}))
      data.sub_scores[key].forEach(d => { d._d = new Date(d.date); });
  }

  // ── 公開 API ──────────────────────────────────────────────────────

  async function fetchData() {
    if (_cache) return _cache;
    if (_loading) return _loading;
    _loading = _fetchSupabase().then(data => { _parseDates(data); return data; });
    _cache = await _loading;
    _loading = null;
    return _cache;
  }

  // 取最新一列的四大面向分數（供 buildDimSection 初始渲染）
  async function fetchDimScores() {
    if (_dimCache) return _dimCache;
    if (!_scoreRows) await fetchData();   // 確保 _scoreRows 已填入
    const r = _scoreRows[_scoreRows.length - 1] || {};
    _dimCache = [{
      DIM1_SCORE:       r.dim1_score,
      DIM2_SCORE:       r.dim2_score,
      DIM2_CREDIBILITY: r.dim2_credibility,
      DIM3_SCORE:       r.dim3_score,
      DIM4_SCORE:       r.dim4_score,
    }];
    return _dimCache;
  }

  // 按日期按需抓取原始指標（取代原本全量 fetchRawData，避免下載 200K+ 列）
  async function fetchRawDataForDate(date) {
    if (!date) return {};
    try {
      const resp = await fetch(
        `${SUPA_URL}/rest/v1/macro_raw?select=ticker,raw_value&observation_date=eq.${date}`,
        { headers: HDRS }
      );
      if (!resp.ok) return {};
      const rows = await resp.json();
      return Object.fromEntries(rows.map(r => [r.ticker, r.raw_value]));
    } catch { return {}; }
  }

  // ── 工具函數（API 維持不變）───────────────────────────────────────

  function filterByRange(arr, from, to) {
    return arr.filter(d => d._d >= from && d._d <= to);
  }

  function getLatestScore(data) {
    const ms = data.scores.MACRO_SCORE;
    return ms.length ? ms[ms.length - 1] : null;
  }

  function getLatestRegime(data) {
    const r = data.scores.REGIME;
    return r.length ? r[r.length - 1] : null;
  }

  function getLatestSubScores(data) {
    const result = {};
    for (const [key, arr] of Object.entries(data.sub_scores))
      result[key] = arr.length ? arr[arr.length - 1].value : null;
    return result;
  }

  function getDelta(arr, daysBack = 30) {
    if (arr.length < 2) return null;
    const latest = arr[arr.length - 1];
    const cutoff = new Date(latest._d);
    cutoff.setDate(cutoff.getDate() - daysBack);
    const prev = arr.filter(d => d._d <= cutoff);
    return prev.length ? latest.value - prev[prev.length - 1].value : null;
  }

  function getRecent(arr, n = 60) { return arr.slice(-n); }

  function getLatestDimScores(rows) {
    if (!rows || !rows.length) return {};
    const latest = rows[rows.length - 1];
    const result = {};
    for (const k of ['DIM1_SCORE', 'DIM2_SCORE', 'DIM2_CREDIBILITY', 'DIM3_SCORE', 'DIM4_SCORE']) {
      const raw = latest[k];
      result[k] = raw != null ? parseFloat(raw) : null;
    }
    return result;
  }

  return {
    fetchData,
    fetchDimScores,
    fetchRawDataForDate,
    getLatestDimScores,
    filterByRange,
    getLatestScore,
    getLatestRegime,
    getLatestSubScores,
    getDelta,
    getRecent,
  };
})();
