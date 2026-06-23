
/* Argus KB site behavior: theme, sidebar, copy buttons, mermaid re-theme. */
(function () {
  'use strict';
  var root = document.documentElement;
  var body = document.body;
  var DESKTOP = '(min-width: 981px)';

  /* ---------- Theme ---------- */
  function currentTheme() {
    return root.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
  }
  function applyTheme(theme, persist) {
    root.setAttribute('data-theme', theme);
    if (persist) { try { localStorage.setItem('argus-theme', theme); } catch (e) {} }
    document.dispatchEvent(new CustomEvent('themechange', { detail: { theme: theme } }));
  }
  var themeBtn = document.getElementById('theme-toggle');
  if (themeBtn) {
    themeBtn.addEventListener('click', function () {
      applyTheme(currentTheme() === 'dark' ? 'light' : 'dark', true);
    });
  }
  // If user has NOT chosen explicitly, follow system changes live.
  if (window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function (e) {
      var saved;
      try { saved = localStorage.getItem('argus-theme'); } catch (err) {}
      if (!saved) applyTheme(e.matches ? 'dark' : 'light', false);
    });
  }

  /* ---------- Sidebar ---------- */
  var sidebarBtn = document.getElementById('sidebar-toggle');
  var backdrop = document.getElementById('backdrop');

  function isDesktop() { return window.matchMedia(DESKTOP).matches; }

  // Desktop: persisted collapse state. Default = open.
  function initDesktopSidebar() {
    var pref;
    try { pref = localStorage.getItem('argus-sidebar'); } catch (e) {}
    if (pref === 'collapsed') body.classList.add('sidebar-collapsed');
    else body.classList.remove('sidebar-collapsed');
  }

  function openMobile() {
    body.classList.add('sidebar-open');
    if (backdrop) backdrop.hidden = false;
    if (sidebarBtn) sidebarBtn.setAttribute('aria-expanded', 'true');
  }
  function closeMobile() {
    body.classList.remove('sidebar-open');
    if (backdrop) backdrop.hidden = true;
    if (sidebarBtn) sidebarBtn.setAttribute('aria-expanded', 'false');
  }

  function toggleSidebar() {
    if (isDesktop()) {
      var collapsed = body.classList.toggle('sidebar-collapsed');
      try { localStorage.setItem('argus-sidebar', collapsed ? 'collapsed' : 'open'); } catch (e) {}
      if (sidebarBtn) sidebarBtn.setAttribute('aria-expanded', String(!collapsed));
    } else {
      if (body.classList.contains('sidebar-open')) closeMobile();
      else openMobile();
    }
  }

  if (sidebarBtn) sidebarBtn.addEventListener('click', toggleSidebar);
  if (backdrop) backdrop.addEventListener('click', closeMobile);

  // Mobile: tapping a nav link closes the overlay.
  document.querySelectorAll('.side-nav a').forEach(function (a) {
    a.addEventListener('click', function () { if (!isDesktop()) closeMobile(); });
  });

  // Escape closes the mobile drawer.
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !isDesktop()) closeMobile();
  });

  // Reset overlay state when crossing the breakpoint.
  var mq = window.matchMedia(DESKTOP);
  mq.addEventListener('change', function () {
    closeMobile();
    if (isDesktop()) initDesktopSidebar();
  });

  initDesktopSidebar();           // desktop default = open (mobile default = closed/hidden)
  if (!isDesktop()) closeMobile();

  /* ---------- Copy buttons ---------- */
  document.querySelectorAll('.prose pre').forEach(function (pre) {
    var btn = document.createElement('button');
    btn.className = 'copy-btn';
    btn.type = 'button';
    btn.textContent = 'Copy';
    btn.addEventListener('click', function () {
      var code = pre.querySelector('code');
      var text = code ? code.innerText : pre.innerText;
      navigator.clipboard.writeText(text).then(function () {
        btn.textContent = 'Copied!';
        btn.classList.add('copied');
        setTimeout(function () { btn.textContent = 'Copy'; btn.classList.remove('copied'); }, 1600);
      }).catch(function () { btn.textContent = 'Error'; });
    });
    pre.appendChild(btn);
  });

  /* ---------- Mermaid (themed, re-render on theme change) ---------- */
  var mermaidSources = [];
  function mermaidTheme() { return currentTheme() === 'dark' ? 'dark' : 'neutral'; }

  function initMermaid() {
    if (typeof window.mermaid === 'undefined') return;
    var nodes = document.querySelectorAll('.mermaid');
    if (!nodes.length) return;
    // Cache original definitions once so we can re-render after theme swap.
    if (!mermaidSources.length) {
      nodes.forEach(function (n) { mermaidSources.push(n.textContent); });
    }
    nodes.forEach(function (n, i) {
      n.removeAttribute('data-processed');
      n.innerHTML = mermaidSources[i];
    });
    window.mermaid.initialize({
      startOnLoad: false,
      theme: mermaidTheme(),
      securityLevel: 'strict',
      fontFamily: "Inter, sans-serif"
    });
    try { window.mermaid.run({ nodes: nodes }); } catch (e) {}
  }

  if (typeof window.mermaid !== 'undefined') initMermaid();
  else window.addEventListener('load', initMermaid);

  /* ---------- Chart.js benchmark chart (re-theme aware) ---------- */
  var benchChart = null;
  function chartColors() {
    var dark = currentTheme() === 'dark';
    return {
      grid: dark ? 'rgba(255,255,255,.08)' : 'rgba(0,0,0,.08)',
      tick: dark ? '#a8b0c5' : '#5a6478'
    };
  }
  function renderBenchChart() {
    var canvas = document.getElementById('bench-chart');
    if (!canvas || typeof window.Chart === 'undefined') return;
    var data;
    try { data = JSON.parse(canvas.getAttribute('data-bench')); } catch (e) { return; }
    var c = chartColors();
    var grad = canvas.getContext('2d').createLinearGradient(0, 0, 0, 360);
    grad.addColorStop(0, '#7c3aed');
    grad.addColorStop(1, '#06b6d4');
    if (benchChart) benchChart.destroy();
    benchChart = new window.Chart(canvas, {
      type: 'bar',
      data: {
        labels: data.map(function (d) { return d[0]; }),
        datasets: [{
          label: 'F1 score',
          data: data.map(function (d) { return d[1]; }),
          backgroundColor: grad,
          borderRadius: 6,
          maxBarThickness: 46
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          y: { beginAtZero: true, max: 1, grid: { color: c.grid }, ticks: { color: c.tick } },
          x: { grid: { display: false }, ticks: { color: c.tick, maxRotation: 60, minRotation: 30 } }
        }
      }
    });
  }
  if (typeof window.Chart !== 'undefined') renderBenchChart();
  else window.addEventListener('load', renderBenchChart);

  /* ---------- Re-theme diagrams + charts on toggle ---------- */
  document.addEventListener('themechange', function () {
    initMermaid();
    renderBenchChart();
  });
})();
