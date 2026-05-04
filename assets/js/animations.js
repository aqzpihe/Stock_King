/* ================================================================
   animations.js — GSAP + ScrollTrigger + 手動 SplitText + Lenis
   ================================================================ */

const Animations = (() => {
  // Check for reduced motion preference
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const isLowEnd = navigator.hardwareConcurrency && navigator.hardwareConcurrency < 4;

  // --- IntersectionObserver for .reveal elements ---
  function initRevealObserver() {
    if (prefersReducedMotion) {
      document.querySelectorAll('.reveal').forEach(el => el.classList.add('visible'));
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.1 });
    document.querySelectorAll('.reveal').forEach(el => observer.observe(el));
  }

  // --- Manual SplitText: Character Drop-in ---
  function animateCharDrop(el) {
    if (prefersReducedMotion) return;
    const text = el.textContent;
    el.innerHTML = '';
    [...text].forEach((char, i) => {
      const span = document.createElement('span');
      span.className = 'char';
      span.textContent = char === ' ' ? '\u00A0' : char;
      span.style.animationDelay = `${i * 40}ms`;
      el.appendChild(span);
    });
  }

  // --- Clip-path Reveal ---
  function animateClipReveal(container) {
    if (prefersReducedMotion) {
      container.querySelectorAll('.clip-reveal').forEach(el => el.classList.add('visible'));
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.querySelector('.clip-reveal')?.classList.add('visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.3 });
    container.querySelectorAll('.clip-reveal-wrapper').forEach(el => observer.observe(el));
  }

  // --- Word Color Scrub ---
  function initWordScrub(container) {
    if (prefersReducedMotion || typeof gsap === 'undefined') {
      container.querySelectorAll('.word-scrub .word').forEach(el => el.classList.add('lit'));
      return;
    }
    container.querySelectorAll('.word-scrub').forEach(p => {
      const text = p.textContent;
      p.innerHTML = '';
      text.split(/(\s+)/).forEach(word => {
        if (word.trim()) {
          const span = document.createElement('span');
          span.className = 'word';
          span.textContent = word;
          p.appendChild(span);
        } else {
          p.appendChild(document.createTextNode(word));
        }
      });

      // Use GSAP ScrollTrigger if available and not low-end
      if (typeof ScrollTrigger !== 'undefined' && !isLowEnd) {
        const words = p.querySelectorAll('.word');
        gsap.registerPlugin(ScrollTrigger);
        words.forEach((word, i) => {
          ScrollTrigger.create({
            trigger: word,
            scroller: container,
            start: 'top 85%',
            onEnter: () => word.classList.add('lit'),
          });
        });
      } else {
        // Fallback: IntersectionObserver
        const observer = new IntersectionObserver((entries) => {
          entries.forEach(entry => {
            if (entry.isIntersecting) {
              entry.target.classList.add('lit');
            }
          });
        }, { threshold: 0.5 });
        p.querySelectorAll('.word').forEach(w => observer.observe(w));
      }
    });
  }

  // --- Row Stagger Slide ---
  function animateRowStagger(container) {
    if (prefersReducedMotion) {
      container.querySelectorAll('.row-stagger tr').forEach(el => el.classList.add('visible'));
      return;
    }
    container.querySelectorAll('.row-stagger').forEach(table => {
      const rows = table.querySelectorAll('tbody tr');
      const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            rows.forEach((row, i) => {
              setTimeout(() => row.classList.add('visible'), i * 60);
            });
            observer.unobserve(entry.target);
          }
        });
      }, { threshold: 0.2 });
      observer.observe(table);
    });
  }

  // --- Drawer animations ---
  function initDrawer() {
    const overlay = document.getElementById('drawerOverlay');
    const drawer = document.getElementById('explainDrawer');
    const openBtn = document.getElementById('openExplainBtn');
    const closeBtn = document.getElementById('drawerCloseBtn');

    function open() {
      overlay.classList.add('open');
      drawer.classList.add('open');
      // Trigger animations inside drawer
      const title = document.getElementById('drawerTitle');
      animateCharDrop(title);
      animateClipReveal(drawer);
      animateRowStagger(drawer);
      initWordScrub(drawer);
    }

    function close() {
      overlay.classList.remove('open');
      drawer.classList.remove('open');
    }

    // Bind ALL open buttons (sidebar, gauge area, section E)
    document.querySelectorAll('.openExplainBtn, #openExplainBtn').forEach(btn => {
      btn.addEventListener('click', open);
    });
    if (closeBtn) closeBtn.addEventListener('click', close);
    if (overlay) overlay.addEventListener('click', close);
    // ESC key
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && drawer.classList.contains('open')) close();
    });
  }

  // --- KPI Card Sparkline SVG ---
  function createSparklineSVG(values, color) {
    if (!values.length) return '';
    const w = 120, h = 32, pad = 2;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    const points = values.map((v, i) => {
      const x = pad + (i / (values.length - 1)) * (w - 2 * pad);
      const y = pad + (1 - (v - min) / range) * (h - 2 * pad);
      return `${x},${y}`;
    }).join(' ');

    // Calculate path length for animation
    let pathLen = 0;
    for (let i = 1; i < values.length; i++) {
      const [x1, y1] = points.split(' ')[i - 1].split(',').map(Number);
      const [x2, y2] = points.split(' ')[i].split(',').map(Number);
      pathLen += Math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2);
    }

    return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
      <polyline points="${points}" fill="none" stroke="${color}" stroke-width="1.5"
                stroke-linejoin="round" stroke-linecap="round"
                class="sparkline-animate" style="--spark-length:${Math.ceil(pathLen + 10)}"/>
    </svg>`;
  }

  // --- Init all ---
  function init() {
    initRevealObserver();
    initDrawer();
  }

  return { init, createSparklineSVG, animateCharDrop };
})();
