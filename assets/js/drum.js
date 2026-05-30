/* ================================================================
   drum.js — 日期選擇滾輪
   day 模式：只在真實資料存在的日期之間跳轉（無資料的日期跳過）
   year / month 模式：按月 / 年跳轉後 snap 到最近有效日期
   ================================================================ */

const DrumPicker = (() => {

  // ── 視覺常數 ────────────────────────────────────────────────────
  const PATTERN  = ['A', 'B', 'A', 'C'];
  const WIDTHS   = { A: 0.84, B: 0.65, C: 0.47 };
  const VISIBLE  = 21;
  const CENTER   = Math.floor(VISIBLE / 2);   // = 10
  const LINE_H_C = 3.0;
  const LINE_H_E = 1.2;

  // ── 有效日期（由外部 setValidDates() 填入）──────────────────────
  let validDates  = [];          // 排序後的 Date 物件陣列
  let validIdxMap = new Map();   // timestamp → index，O(1) 查詢

  // ── 日期邊界 ─────────────────────────────────────────────────────
  let MIN_DATE = new Date('2000-01-03');
  let MAX_DATE = new Date();

  // ── 模式 ────────────────────────────────────────────────────────
  const MODES  = ['year', 'month', 'day'];
  let modeIdx  = 0;

  // ── 選取日期 ──────────────────────────────────────────────────────
  let sel = new Date(MAX_DATE);
  _clamp();

  let autoTimer = null;

  // ── 工具 ────────────────────────────────────────────────────────
  function _clamp() {
    if (sel < MIN_DATE) sel = new Date(MIN_DATE);
    if (sel > MAX_DATE) sel = new Date(MAX_DATE);
  }

  function _daysInMonth(y, m) { return new Date(y, m, 0).getDate(); }
  function _mode()             { return MODES[modeIdx]; }

  /** 在 validDates 中找最接近 target 的索引（二分搜尋） */
  function _nearestIdx(target) {
    if (!validDates.length) return -1;
    const t = +target;
    let lo = 0, hi = validDates.length - 1;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (+validDates[mid] < t) lo = mid + 1;
      else hi = mid;
    }
    if (lo > 0 && Math.abs(+validDates[lo - 1] - t) < Math.abs(+validDates[lo] - t)) {
      return lo - 1;
    }
    return lo;
  }

  /** 將 sel snap 到最近的有效日期 */
  function _snapToValid() {
    if (!validDates.length) return;
    const idx = _nearestIdx(sel);
    sel = new Date(validDates[idx]);
  }

  /** 取得目前模式的合法範圍（年/月模式用） */
  function _range() {
    const y   = sel.getFullYear();
    const m   = sel.getMonth() + 1;
    const minY = MIN_DATE.getFullYear(), maxY = MAX_DATE.getFullYear();

    switch (_mode()) {
      case 'year':
        return { min: minY, max: maxY };
      case 'month':
        return {
          min: y === minY ? MIN_DATE.getMonth() + 1 : 1,
          max: y === maxY ? MAX_DATE.getMonth() + 1 : 12,
        };
      case 'day': {
        const dim   = _daysInMonth(y, m);
        const atMin = y === MIN_DATE.getFullYear() && m === MIN_DATE.getMonth() + 1;
        const atMax = y === MAX_DATE.getFullYear() && m === MAX_DATE.getMonth() + 1;
        return {
          min: atMin ? MIN_DATE.getDate() : 1,
          max: atMax ? Math.min(MAX_DATE.getDate(), dim) : dim,
        };
      }
    }
  }

  function _curVal() {
    switch (_mode()) {
      case 'year':  return sel.getFullYear();
      case 'month': return sel.getMonth() + 1;
      case 'day':   return sel.getDate();
    }
  }

  // ── 套用 delta ───────────────────────────────────────────────────
  function _applyDelta(delta) {
    // day 模式：只在 validDates 陣列中移動
    if (_mode() === 'day' && validDates.length > 0) {
      const curIdx = validIdxMap.get(+sel) ?? _nearestIdx(sel);
      const nextIdx = Math.max(0, Math.min(validDates.length - 1, curIdx + delta));
      if (nextIdx === curIdx) return false;
      sel = new Date(validDates[nextIdx]);
      return true;
    }

    // year / month 模式：按整數步進，再 snap 到最近有效日期
    const { min, max } = _range();
    const cur  = _curVal();
    const next = Math.max(min, Math.min(max, cur + delta));
    if (next === cur) return false;

    const d = new Date(sel);
    switch (_mode()) {
      case 'year': {
        d.setFullYear(next);
        const minM = next === MIN_DATE.getFullYear() ? MIN_DATE.getMonth() + 1 : 1;
        const maxM = next === MAX_DATE.getFullYear() ? MAX_DATE.getMonth() + 1 : 12;
        const newM = Math.max(minM, Math.min(maxM, d.getMonth() + 1));
        const dim  = _daysInMonth(next, newM);
        const minD = next === MIN_DATE.getFullYear() && newM === MIN_DATE.getMonth() + 1 ? MIN_DATE.getDate() : 1;
        const maxD = next === MAX_DATE.getFullYear() && newM === MAX_DATE.getMonth() + 1 ? Math.min(MAX_DATE.getDate(), dim) : dim;
        d.setMonth(newM - 1);
        d.setDate(Math.max(minD, Math.min(maxD, d.getDate())));
        break;
      }
      case 'month': {
        const y   = d.getFullYear();
        const dim = _daysInMonth(y, next);
        const minD = y === MIN_DATE.getFullYear() && next === MIN_DATE.getMonth() + 1 ? MIN_DATE.getDate() : 1;
        const maxD = y === MAX_DATE.getFullYear() && next === MAX_DATE.getMonth() + 1 ? Math.min(MAX_DATE.getDate(), dim) : dim;
        d.setMonth(next - 1);
        d.setDate(Math.max(minD, Math.min(maxD, d.getDate())));
        break;
      }
    }

    sel = d;
    _clamp();
    _snapToValid();   // 換年/月後 snap 到最近有效日期
    return true;
  }

  // ── 視覺 ────────────────────────────────────────────────────────
  function _lineType(i) {
    return PATTERN[((i % 4) + 4) % 4];
  }

  function _styleAt(dist, inRange) {
    const t   = dist / CENTER;
    const tSq = t * t;
    const base = Math.max(0.08, 1 - tSq * 0.92);
    return {
      opacity:   inRange ? base : Math.min(base * 0.30, 0.10),
      thickness: LINE_H_E + (LINE_H_C - LINE_H_E) * (1 - tSq),
    };
  }

  function render() {
    const track = document.getElementById('drumTrack');
    if (!track) return;

    let lines = track.querySelectorAll('.drum-line');
    while (lines.length < VISIBLE) {
      const el = document.createElement('div');
      el.className = 'drum-line';
      track.appendChild(el);
      lines = track.querySelectorAll('.drum-line');
    }

    if (_mode() === 'day' && validDates.length > 0) {
      // day 模式：以 validDates 索引為基準
      const selIdx = validIdxMap.get(+sel) ?? _nearestIdx(sel);
      lines.forEach((el, i) => {
        const dateIdx = selIdx + (i - CENTER);
        const inRange = dateIdx >= 0 && dateIdx < validDates.length;
        const d       = Math.abs(i - CENTER);
        const { opacity, thickness } = _styleAt(d, inRange);
        const type    = _lineType(i);
        el.style.width   = `${(WIDTHS[type] * 100).toFixed(1)}%`;
        el.style.height  = `${thickness.toFixed(2)}px`;
        el.style.opacity = opacity.toFixed(3);
      });
    } else {
      // year / month 模式：以數值連續範圍為基準
      const { min, max } = _range();
      const curVal = _curVal();
      lines.forEach((el, i) => {
        const val     = curVal + (i - CENTER);
        const inRange = val >= min && val <= max;
        const d       = Math.abs(i - CENTER);
        const { opacity, thickness } = _styleAt(d, inRange);
        const type    = _lineType(i);
        el.style.width   = `${(WIDTHS[type] * 100).toFixed(1)}%`;
        el.style.height  = `${thickness.toFixed(2)}px`;
        el.style.opacity = opacity.toFixed(3);
      });
    }

    _updateUI();
  }

  function _updateUI() {
    const y  = sel.getFullYear();
    const mm = String(sel.getMonth() + 1).padStart(2, '0');
    const dd = String(sel.getDate()).padStart(2, '0');
    const mode = _mode();

    // 日期顯示列
    const display = document.getElementById('drumDateDisplay');
    if (display) {
      display.innerHTML =
        `<span class="drum-dp${mode === 'year'  ? ' drum-dp-on' : ''}">${y}</span>` +
        `<span class="drum-ds">/</span>` +
        `<span class="drum-dp${mode === 'month' ? ' drum-dp-on' : ''}">${mm}</span>` +
        `<span class="drum-ds">/</span>` +
        `<span class="drum-dp${mode === 'day'   ? ' drum-dp-on' : ''}">${dd}</span>`;
    }

    // 模式 tab
    document.querySelectorAll('.drum-mode-tab').forEach((tab, i) => {
      tab.classList.toggle('active', i === modeIdx);
    });

    // 側邊標籤與按鈕啟用狀態
    const ADJ = [
      { left: null, right: '月' },  // year：左側無更大單位
      { left: '年', right: '日' },  // month：兩側皆有
      { left: '月', right: null },  // day：右側無更小單位
    ];
    const adj = ADJ[modeIdx];
    const lblL = document.getElementById('drumLabelLeft');
    const lblR = document.getElementById('drumLabelRight');
    const btnL = document.getElementById('drumLeft');
    const btnR = document.getElementById('drumRight');
    if (lblL) lblL.textContent = adj.left  ?? '';
    if (lblR) lblR.textContent = adj.right ?? '';
    if (btnL) btnL.classList.toggle('drum-disabled', adj.left  === null);
    if (btnR) btnR.classList.toggle('drum-disabled', adj.right === null);

    // 通知外部（圖表篩選用）
    document.dispatchEvent(new CustomEvent('drumDateChange', {
      bubbles: true,
      detail: { date: `${y}-${mm}-${dd}`, dateObj: new Date(sel), mode: _mode() },
    }));
  }

  // ── 滾動 ────────────────────────────────────────────────────────
  function step(delta) {
    _applyDelta(delta);
    render();
  }

  function startAutoScroll(delta, delay = 110) {
    stopAutoScroll();
    step(delta);
    autoTimer = setInterval(() => step(delta), delay);
  }

  function stopAutoScroll() {
    if (autoTimer) { clearInterval(autoTimer); autoTimer = null; }
  }

  function switchMode(dir) {
    const next = modeIdx + dir;
    if (next < 0 || next >= MODES.length) return;
    modeIdx = next;
    render();
  }

  // ── 初始化 ──────────────────────────────────────────────────────
  function init() {
    render();

    function bindVertical(id, delta) {
      const btn = document.getElementById(id);
      if (!btn) return;
      btn.addEventListener('mousedown',  () => startAutoScroll(delta));
      btn.addEventListener('touchstart', () => startAutoScroll(delta), { passive: true });
      btn.addEventListener('mouseup',    stopAutoScroll);
      btn.addEventListener('mouseleave', stopAutoScroll);
      btn.addEventListener('touchend',   stopAutoScroll);
    }
    bindVertical('drumPlus',  +1);
    bindVertical('drumMinus', -1);

    document.getElementById('drumLeft') ?.addEventListener('click', () => switchMode(-1));
    document.getElementById('drumRight')?.addEventListener('click', () => switchMode(+1));

    document.querySelectorAll('.drum-mode-tab').forEach((tab, i) => {
      tab.addEventListener('click', () => { modeIdx = i; render(); });
    });

    const vp = document.getElementById('drumViewport');
    vp?.addEventListener('wheel', (e) => {
      e.preventDefault();
      step(e.deltaY > 0 ? +1 : -1);
    }, { passive: false });

    let touchY0 = 0, touchAcc = 0;
    vp?.addEventListener('touchstart', (e) => {
      touchY0 = e.touches[0].clientY; touchAcc = 0;
    }, { passive: true });
    vp?.addEventListener('touchmove', (e) => {
      e.preventDefault();
      const dy = touchY0 - e.touches[0].clientY;
      touchAcc += dy;
      touchY0 = e.touches[0].clientY;
      if (Math.abs(touchAcc) >= 11) { step(touchAcc > 0 ? +1 : -1); touchAcc = 0; }
    }, { passive: false });
  }

  // ── 公開 API ─────────────────────────────────────────────────────

  /** 從 dashboard_data.json 的日期列表初始化有效日期 */
  function setValidDates(dateStrings) {
    validDates = dateStrings
      .map(s => { const d = new Date(s); d.setHours(0, 0, 0, 0); return d; })
      .sort((a, b) => a - b);

    validIdxMap.clear();
    validDates.forEach((d, i) => validIdxMap.set(+d, i));

    if (validDates.length > 0) {
      MIN_DATE = new Date(validDates[0]);
      MAX_DATE = new Date(validDates[validDates.length - 1]);
      sel = new Date(MAX_DATE);
    }
    render();
  }

  function setBounds(minDate, maxDate) {
    MIN_DATE = new Date(minDate);
    MAX_DATE = new Date(maxDate);
    sel = new Date(MAX_DATE);
    _clamp();
    render();
  }

  function getDate() { return new Date(sel); }

  return { init, step, switchMode, setValidDates, setBounds, getDate };
})();

DrumPicker.init();
