/* ================================================================
   data.js — 資料抓取與快取層
   支援本地 JSON + Google Sheets CSV/API
   ================================================================ */

const DataService = (() => {
  // --- Config ---
  const LOCAL_JSON_PATH = './assets/data/dashboard_data.json';
  const SCORES_CSV_PATH = './assets/data/scores.csv';
  const SHEET_ID = '1Qt9QcPKb606b9h0bm7fQQ5dqDWEqLiU7vfxjFTmJITU';

  // Google Sheets tab GIDs (to be configured when sheets are populated)
  const SHEET_GIDS = {
    M1_scores: 0,
    M1_sub_indicators: null,
    M1_history: null,
  };

  // --- In-memory cache ---
  let _cache = null;
  let _loading = null;
  let _dimCache = null;

  // --- Core fetch ---
  async function fetchData() {
    if (_cache) return _cache;
    if (_loading) return _loading;

    _loading = _fetchLocal();
    _cache = await _loading;
    _loading = null;
    return _cache;
  }

  async function _fetchLocal() {
    const resp = await fetch(LOCAL_JSON_PATH);
    if (!resp.ok) throw new Error(`Failed to load ${LOCAL_JSON_PATH}: ${resp.status}`);
    const data = await resp.json();
    _parseDates(data);
    return data;
  }

  // Google Sheets CSV fetch (for future use)
  async function _fetchSheetCSV(gid) {
    const url = `https://docs.google.com/spreadsheets/d/${SHEET_ID}/export?format=csv&gid=${gid}&t=${Date.now()}`;
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`Google Sheets fetch failed: ${resp.status}`);
    const text = await resp.text();
    return _parseCSV(text);
  }

  function _parseCSV(text) {
    const lines = text.trim().split('\n');
    if (lines.length < 2) return [];
    const headers = lines[0].split(',').map(h => h.trim().replace(/"/g, ''));
    return lines.slice(1).map(line => {
      const vals = line.split(',').map(v => v.trim().replace(/"/g, ''));
      const obj = {};
      headers.forEach((h, i) => { obj[h] = vals[i]; });
      return obj;
    });
  }

  function _parseDates(data) {
    for (const key of Object.keys(data.scores || {})) {
      data.scores[key].forEach(d => { d._d = new Date(d.date); });
    }
    for (const key of Object.keys(data.indices || {})) {
      data.indices[key].forEach(d => { d._d = new Date(d.date); });
    }
    for (const key of Object.keys(data.sub_scores || {})) {
      data.sub_scores[key].forEach(d => { d._d = new Date(d.date); });
    }
  }

  // --- Query helpers ---
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
    for (const [key, arr] of Object.entries(data.sub_scores)) {
      result[key] = arr.length ? arr[arr.length - 1].value : null;
    }
    return result;
  }

  // Get a recent delta (current - N days ago)
  function getDelta(arr, daysBack = 30) {
    if (arr.length < 2) return null;
    const latest = arr[arr.length - 1];
    const cutoff = new Date(latest._d);
    cutoff.setDate(cutoff.getDate() - daysBack);
    const prev = arr.filter(d => d._d <= cutoff);
    if (!prev.length) return null;
    return latest.value - prev[prev.length - 1].value;
  }

  // Get recent N points for sparkline
  function getRecent(arr, n = 60) {
    return arr.slice(-n);
  }

  // ── DIM 分數 CSV 讀取 ──
  async function fetchDimScores() {
    if (_dimCache) return _dimCache;
    try {
      const resp = await fetch(SCORES_CSV_PATH);
      if (!resp.ok) throw new Error(`scores.csv 載入失敗 (${resp.status})`);
      const text = await resp.text();
      _dimCache = _parseCSV(text);   // 複用既有的 _parseCSV
      return _dimCache;
    } catch (e) {
      console.warn('[DataService] fetchDimScores:', e.message);
      return [];   // 找不到時 graceful 降級，不影響其他功能
    }
  }

  // 取最後一行的四大面向分數
  function getLatestDimScores(rows) {
    if (!rows || !rows.length) return {};
    const latest = rows[rows.length - 1];
    const keys = ['DIM1_SCORE', 'DIM2_SCORE', 'DIM2_CREDIBILITY', 'DIM3_SCORE', 'DIM4_SCORE'];
    const result = {};
    for (const k of keys) {
      const raw = latest[k];
      result[k] = (raw !== undefined && raw !== '') ? parseFloat(raw) : null;
    }
    return result;
  }

  // ── Raw Data CSV 讀取 (從 1-大環境) ──
  let _rawDataCache = null;
  async function fetchRawData() {
    if (_rawDataCache) return _rawDataCache;
    try {
      const resp = await fetch('./1-大環境/data/data.csv');
      if (!resp.ok) throw new Error(`data.csv 載入失敗 (${resp.status})`);
      const text = await resp.text();
      const rows = _parseCSV(text);
      
      // 依日期和 ticker 分組
      const dateMap = {};
      for (const r of rows) {
        if (!r.observation_date) continue;
        if (!dateMap[r.observation_date]) {
          dateMap[r.observation_date] = {};
        }
        dateMap[r.observation_date][r.ticker] = r.raw_value;
      }
      _rawDataCache = dateMap;
      return dateMap;
    } catch (e) {
      console.warn('[DataService] fetchRawData:', e.message);
      return {};
    }
  }

  // --- Public API ---
  return {
    fetchData,
    fetchDimScores,
    fetchRawData,
    getLatestDimScores,
    filterByRange,
    getLatestScore,
    getLatestRegime,
    getLatestSubScores,
    getDelta,
    getRecent,
    SHEET_ID,
  };
})();
