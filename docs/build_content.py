# -*- coding: utf-8 -*-
"""Content, CSS and JS for the Argus KB site. Imported by build.py.

Kept separate so build.py stays focused on rendering/chrome and this file
holds the (long) per-page HTML fragments plus the shared stylesheet/script.
"""

# =========================================================================== #
#  CSS  (shared, written once to assets/style.css)
# =========================================================================== #
CSS = r"""
/* ---------- Design tokens ---------- */
:root{
  --accent-1:#7c3aed;          /* violet */
  --accent-2:#06b6d4;          /* cyan   */
  --accent-grad:linear-gradient(120deg,#7c3aed 0%,#6366f1 45%,#06b6d4 100%);
  --radius:14px;
  --radius-sm:9px;
  --maxw:1080px;
  --font:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
  --mono:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  --topbar-h:60px;
  --side-w:264px;
  --transition:.22s cubic-bezier(.4,0,.2,1);
}
:root[data-theme="light"]{
  --bg:#f7f8fb;
  --bg-elev:#ffffff;
  --bg-soft:#f1f2f8;
  --text:#1c2230;
  --text-soft:#5a6478;
  --muted:#7c8499;
  --border:#e4e7ef;
  --border-strong:#d2d7e3;
  --code-bg:#f4f5fb;
  --code-text:#3a2a6d;
  --shadow:0 1px 2px rgba(20,24,40,.06),0 8px 24px rgba(20,24,40,.06);
  --shadow-sm:0 1px 2px rgba(20,24,40,.07);
  --side-bg:#ffffff;
  --table-stripe:#f7f8fc;
}
:root[data-theme="dark"]{
  --bg:#0d1018;
  --bg-elev:#161a26;
  --bg-soft:#1b2030;
  --text:#e6e9f2;
  --text-soft:#a8b0c5;
  --muted:#7f879d;
  --border:#262c3c;
  --border-strong:#333b50;
  --code-bg:#121622;
  --code-text:#c7b8ff;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 12px 32px rgba(0,0,0,.4);
  --shadow-sm:0 1px 2px rgba(0,0,0,.4);
  --side-bg:#11151f;
  --table-stripe:#171c29;
}

*{box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:calc(var(--topbar-h) + 16px)}
body{
  margin:0;font-family:var(--font);background:var(--bg);color:var(--text);
  line-height:1.65;-webkit-font-smoothing:antialiased;
}
a{color:var(--accent-1);text-decoration:none}
:root[data-theme="dark"] a{color:#a78bfa}
a:hover{text-decoration:underline}

.skip-link{position:absolute;left:-999px;top:0;background:var(--accent-1);color:#fff;
  padding:10px 16px;border-radius:0 0 8px 0;z-index:200}
.skip-link:focus{left:0}

/* ---------- Top bar ---------- */
.topbar{
  position:sticky;top:0;z-index:100;height:var(--topbar-h);
  display:flex;align-items:center;gap:12px;padding:0 16px;
  background:color-mix(in srgb,var(--bg-elev) 88%,transparent);
  backdrop-filter:saturate(150%) blur(10px);
  border-bottom:1px solid var(--border);
}
.brand{display:flex;align-items:baseline;gap:8px;color:var(--text)}
.brand:hover{text-decoration:none}
.brand-eye{width:18px;height:18px;border-radius:50%;background:var(--accent-grad);
  position:relative;align-self:center;box-shadow:0 0 0 3px color-mix(in srgb,var(--accent-1) 22%,transparent)}
.brand-eye::after{content:"";position:absolute;inset:6px;border-radius:50%;background:var(--bg-elev)}
.brand-name{font-weight:800;font-size:1.18rem;letter-spacing:-.02em;
  background:var(--accent-grad);-webkit-background-clip:text;background-clip:text;color:transparent}
.brand-sub{font-size:.78rem;color:var(--muted);font-weight:500}
@media(max-width:640px){.brand-sub{display:none}}
.topbar-spacer{flex:1}
.topbar-link{display:flex;align-items:center;color:var(--text-soft);padding:8px;border-radius:8px}
.topbar-link:hover{color:var(--text);background:var(--bg-soft)}

.icon-btn{
  display:inline-flex;align-items:center;justify-content:center;
  width:38px;height:38px;border:1px solid var(--border);border-radius:10px;
  background:var(--bg-elev);color:var(--text-soft);cursor:pointer;transition:var(--transition);
}
.icon-btn:hover{color:var(--text);border-color:var(--border-strong);background:var(--bg-soft)}
.hamburger{display:none}
@media(max-width:980px){.hamburger{display:inline-flex}}

/* theme toggle icon swap */
.ico-moon{display:none}
:root[data-theme="dark"] .ico-sun{display:none}
:root[data-theme="dark"] .ico-moon{display:inline}

/* ---------- Layout ---------- */
.layout{display:flex;align-items:flex-start;max-width:1320px;margin:0 auto}
.sidebar{
  position:sticky;top:var(--topbar-h);align-self:flex-start;
  width:var(--side-w);height:calc(100vh - var(--topbar-h));overflow-y:auto;
  background:var(--side-bg);border-right:1px solid var(--border);
  padding:18px 12px 40px;flex:none;transition:transform var(--transition);
}
.content{flex:1;min-width:0;max-width:var(--maxw);margin:0 auto;padding:28px 28px 60px;width:100%}

/* sidebar collapsed (desktop) */
body.sidebar-collapsed .sidebar{display:none}

/* ---------- Sidebar nav ---------- */
.nav-group{margin-bottom:18px}
.nav-group-title{font-size:.72rem;text-transform:uppercase;letter-spacing:.09em;
  color:var(--muted);font-weight:700;padding:0 12px 6px}
.side-nav ul{list-style:none;margin:0;padding:0}
.side-nav a{
  display:block;padding:8px 12px;border-radius:9px;color:var(--text-soft);
  font-size:.93rem;font-weight:500;transition:var(--transition);
}
.side-nav a:hover{background:var(--bg-soft);color:var(--text);text-decoration:none}
.side-nav a.active{
  color:#fff;background:var(--accent-grad);
  box-shadow:0 4px 12px color-mix(in srgb,var(--accent-1) 35%,transparent);
}
:root[data-theme="dark"] .side-nav a.active{color:#fff}

/* ---------- backdrop (mobile) ---------- */
.backdrop{position:fixed;inset:var(--topbar-h) 0 0 0;background:rgba(8,10,18,.5);
  z-index:80;backdrop-filter:blur(2px)}

@media(max-width:980px){
  .sidebar{
    position:fixed;top:var(--topbar-h);left:0;z-index:90;
    height:calc(100vh - var(--topbar-h));box-shadow:var(--shadow);
    transform:translateX(-105%);display:block;
  }
  body.sidebar-open .sidebar{transform:translateX(0)}
  body.sidebar-collapsed .sidebar{display:block}  /* class is desktop-only meaning */
  .content{max-width:100%;padding:20px 16px 50px}
}

/* ---------- Prose ---------- */
.breadcrumb{font-size:.82rem;color:var(--muted);margin-bottom:10px}
.breadcrumb a{color:var(--text-soft)}
.breadcrumb .sep{opacity:.5;margin:0 6px}
.breadcrumb .crumb-cur{color:var(--text)}

.page-head{display:flex;align-items:center;justify-content:space-between;gap:16px;
  flex-wrap:wrap;border-bottom:1px solid var(--border);padding-bottom:16px;margin-bottom:8px}
.page-head h1{margin:0;font-size:2rem;letter-spacing:-.02em;line-height:1.2}
.md-link{display:inline-flex;align-items:center;gap:7px;font-size:.85rem;font-weight:600;
  padding:8px 13px;border:1px solid var(--border-strong);border-radius:10px;
  background:var(--bg-elev);color:var(--text-soft);white-space:nowrap}
.md-link:hover{color:var(--text);border-color:var(--accent-1);text-decoration:none;
  box-shadow:var(--shadow-sm)}

.on-this-page{float:right;width:220px;margin:6px 0 18px 24px;padding:14px 16px;
  background:var(--bg-elev);border:1px solid var(--border);border-radius:var(--radius)}
.on-this-page .otp-title{font-size:.74rem;text-transform:uppercase;letter-spacing:.08em;
  color:var(--muted);font-weight:700;margin-bottom:8px}
.on-this-page ul{list-style:none;margin:0;padding:0}
.on-this-page a{display:block;padding:4px 0;font-size:.85rem;color:var(--text-soft)}
.on-this-page a:hover{color:var(--accent-1)}
@media(max-width:760px){.on-this-page{float:none;width:auto;margin:0 0 20px}}

.prose h2{font-size:1.5rem;margin:2.2rem 0 .8rem;letter-spacing:-.01em;
  padding-top:.4rem;scroll-margin-top:calc(var(--topbar-h) + 12px)}
.prose h3{font-size:1.18rem;margin:1.8rem 0 .6rem}
.prose p{margin:.7rem 0;color:var(--text)}
.prose ul,.prose ol{padding-left:1.4rem}
.prose li{margin:.35rem 0}
.prose strong{color:var(--text);font-weight:700}
.prose code{font-family:var(--mono);font-size:.86em;background:var(--code-bg);
  color:var(--code-text);padding:.12em .42em;border-radius:6px;
  border:1px solid var(--border)}
.prose pre{background:var(--code-bg);border:1px solid var(--border);border-radius:var(--radius);
  padding:16px 18px;overflow:auto;position:relative;margin:1.1rem 0}
.prose pre code{background:none;border:none;padding:0;color:var(--text);font-size:.85rem;line-height:1.6}
hr{border:none;border-top:1px solid var(--border);margin:2rem 0}

/* copy button */
.copy-btn{position:absolute;top:8px;right:8px;font-size:.72rem;font-weight:600;
  padding:5px 10px;border:1px solid var(--border-strong);border-radius:8px;
  background:var(--bg-elev);color:var(--text-soft);cursor:pointer;opacity:0;transition:var(--transition)}
.prose pre:hover .copy-btn{opacity:1}
.copy-btn:hover{color:var(--text);border-color:var(--accent-1)}
.copy-btn.copied{color:#fff;background:var(--accent-1);border-color:var(--accent-1)}

/* ---------- Tables ---------- */
.table-wrap{overflow-x:auto;margin:1.1rem 0;border:1px solid var(--border);border-radius:var(--radius)}
table{border-collapse:collapse;width:100%;font-size:.9rem;min-width:520px}
th,td{text-align:left;padding:10px 14px;border-bottom:1px solid var(--border);vertical-align:top}
thead th{background:var(--bg-soft);font-weight:700;color:var(--text);white-space:nowrap;
  position:sticky;top:0}
tbody tr:nth-child(even){background:var(--table-stripe)}
tbody tr:last-child td{border-bottom:none}
td code{white-space:nowrap}

/* ---------- Cards ---------- */
.card-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px;margin:1.4rem 0}
.card{background:var(--bg-elev);border:1px solid var(--border);border-radius:var(--radius);
  padding:20px;box-shadow:var(--shadow-sm);transition:var(--transition)}
.card:hover{transform:translateY(-3px);box-shadow:var(--shadow);border-color:var(--border-strong)}
.card h3{margin:.2rem 0 .5rem;font-size:1.08rem}
.card p{margin:0;color:var(--text-soft);font-size:.92rem}
.card a{font-weight:600}
.card .card-ico{width:40px;height:40px;border-radius:11px;display:flex;align-items:center;
  justify-content:center;background:var(--accent-grad);color:#fff;margin-bottom:12px;font-size:1.2rem}

/* ---------- Badges / callouts ---------- */
.badge{display:inline-block;font-size:.74rem;font-weight:700;padding:2px 9px;border-radius:999px;
  background:color-mix(in srgb,var(--accent-1) 14%,transparent);color:var(--accent-1);
  border:1px solid color-mix(in srgb,var(--accent-1) 30%,transparent)}
:root[data-theme="dark"] .badge{color:#c4b5fd}
.badge.green{background:#10b98122;color:#059669;border-color:#10b98155}
.badge.amber{background:#f59e0b22;color:#b45309;border-color:#f59e0b55}
.badge.red{background:#ef444422;color:#dc2626;border-color:#ef444455}
.badge.gray{background:var(--bg-soft);color:var(--muted);border-color:var(--border)}
:root[data-theme="dark"] .badge.green{color:#34d399}
:root[data-theme="dark"] .badge.amber{color:#fbbf24}
:root[data-theme="dark"] .badge.red{color:#f87171}

.callout{display:flex;gap:12px;padding:14px 16px;border-radius:var(--radius);margin:1.2rem 0;
  border:1px solid var(--border);background:var(--bg-elev)}
.callout .ico{font-size:1.15rem;line-height:1.5}
.callout.tip{border-left:4px solid var(--accent-2);background:color-mix(in srgb,var(--accent-2) 7%,var(--bg-elev))}
.callout.note{border-left:4px solid var(--accent-1);background:color-mix(in srgb,var(--accent-1) 7%,var(--bg-elev))}
.callout.warn{border-left:4px solid #f59e0b;background:#f59e0b12}
.callout p{margin:.2rem 0}
.callout strong{display:block;margin-bottom:2px}

/* ---------- Hero (home) ---------- */
.hero{position:relative;overflow:hidden;border-radius:24px;padding:54px 40px;margin:6px 0 30px;
  background:var(--accent-grad);color:#fff;box-shadow:0 20px 50px color-mix(in srgb,var(--accent-1) 35%,transparent)}
.hero::after{content:"";position:absolute;inset:0;
  background:radial-gradient(circle at 80% 20%,rgba(255,255,255,.25),transparent 45%),
             radial-gradient(circle at 15% 90%,rgba(255,255,255,.15),transparent 40%);pointer-events:none}
.hero-eyes{position:absolute;right:34px;top:34px;display:grid;grid-template-columns:repeat(3,1fr);
  gap:9px;opacity:.5}
.hero-eyes span{width:13px;height:13px;border-radius:50%;background:rgba(255,255,255,.6);
  box-shadow:inset 0 0 0 3px rgba(255,255,255,.3)}
@media(max-width:640px){.hero-eyes{display:none}}
.hero h1{font-size:2.6rem;margin:0 0 6px;letter-spacing:-.03em;line-height:1.1;color:#fff}
.hero .tagline{font-size:1.25rem;font-weight:600;margin:0 0 10px;color:#fff}
.hero p{font-size:1.02rem;max-width:60ch;color:rgba(255,255,255,.92);position:relative}
.hero .cta-row{display:flex;gap:12px;flex-wrap:wrap;margin-top:22px;position:relative}
.btn{display:inline-flex;align-items:center;gap:8px;font-weight:700;font-size:.95rem;
  padding:12px 22px;border-radius:12px;transition:var(--transition);cursor:pointer;border:1px solid transparent}
.btn-primary{background:#fff;color:var(--accent-1)}
.btn-primary:hover{text-decoration:none;transform:translateY(-2px);box-shadow:0 10px 24px rgba(0,0,0,.18)}
.btn-ghost{background:rgba(255,255,255,.14);color:#fff;border-color:rgba(255,255,255,.4)}
.btn-ghost:hover{text-decoration:none;background:rgba(255,255,255,.24)}
@media(max-width:640px){.hero{padding:36px 24px}.hero h1{font-size:2rem}}

.stat-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin:1.4rem 0}
.stat{background:var(--bg-elev);border:1px solid var(--border);border-radius:var(--radius);
  padding:18px;text-align:center}
.stat .num{font-size:1.8rem;font-weight:800;
  background:var(--accent-grad);-webkit-background-clip:text;background-clip:text;color:transparent}
.stat .lbl{font-size:.82rem;color:var(--muted);font-weight:600}

/* ---------- Mermaid + chart ---------- */
.mermaid{background:var(--bg-elev);border:1px solid var(--border);border-radius:var(--radius);
  padding:18px;margin:1.2rem 0;text-align:center;overflow-x:auto}
.chart-wrap{background:var(--bg-elev);border:1px solid var(--border);border-radius:var(--radius);
  padding:18px;margin:1.2rem 0}

.page-footer{margin-top:48px;padding-top:22px;border-top:1px solid var(--border);
  font-size:.86rem;color:var(--text-soft)}
.page-footer .muted{color:var(--muted);font-size:.82rem}
.muted{color:var(--muted)}

/* details/FAQ */
details.faq{border:1px solid var(--border);border-radius:var(--radius);margin:.7rem 0;
  background:var(--bg-elev);overflow:hidden}
details.faq summary{cursor:pointer;padding:14px 18px;font-weight:600;list-style:none;
  display:flex;justify-content:space-between;align-items:center}
details.faq summary::-webkit-details-marker{display:none}
details.faq summary::after{content:"+";color:var(--accent-1);font-size:1.3rem;font-weight:700}
details.faq[open] summary::after{content:"\2013"}
details.faq summary:hover{background:var(--bg-soft)}
details.faq .faq-body{padding:0 18px 16px;color:var(--text-soft)}
details.faq .faq-body p{margin:.4rem 0}

dl.gloss{margin:1rem 0}
dl.gloss dt{font-weight:700;margin-top:1rem;color:var(--text)}
dl.gloss dt .badge{margin-left:8px;font-weight:600}
dl.gloss dd{margin:.2rem 0 0;color:var(--text-soft);padding-left:0}
"""


# =========================================================================== #
#  JS  (shared, written once to assets/app.js)
# =========================================================================== #
JS = r"""
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
"""


# =========================================================================== #
#  PAGES
# =========================================================================== #
REPO = "https://github.com/jimstratus/argus"
BLOB = REPO + "/blob/master"

PAGES = {}

# ---------------------------------------------------------------- index ----- #
PAGES["index"] = {
    "title": "Argus",
    "desc": "Argus is a multi-model code-review CLI skill: it dispatches a diff to a roster of frontier LLM reviewers in parallel, filters by confidence with cross-reviewer corroboration, and produces one merged review.",
    "md_label": "View README.md",
    "md_url": BLOB + "/README.md",
    "mermaid": False,
    "body": r"""
<section class="hero">
  <div class="hero-eyes"><span></span><span></span><span></span><span></span><span></span><span></span></div>
  <h1>Argus</h1>
  <p class="tagline">Multi-model code review, in parallel.</p>
  <p>Argus dispatches a git diff, PR, or file set to a roster of frontier LLM reviewers at the same time,
  filters their findings by confidence with cross-reviewer corroboration, and merges everything into a
  single, de-duplicated review. One model misses bugs; two produce noise &mdash; a filtered panel of six
  beats any single reviewer.</p>
  <div class="cta-row">
    <a class="btn btn-primary" href="getting-started.html">Get started &rarr;</a>
    <a class="btn btn-ghost" href="architecture.html">How it works</a>
    <a class="btn btn-ghost" href="https://github.com/jimstratus/argus" target="_blank" rel="noopener">GitHub</a>
  </div>
</section>

<p>Named for <strong>Argus Panoptes</strong>, the hundred-eyed giant of Greek myth. The original
Linus&rsquo;s Law: <em>given enough eyeballs, all bugs are shallow.</em> Argus is a
<a href="getting-started.html">Claude Code skill</a> &mdash; invoke it as <code>/argus</code> &mdash; backed by a
small set of standalone Python scripts.</p>

<div class="stat-row">
  <div class="stat"><div class="num">15</div><div class="lbl">Reviewers in the registry</div></div>
  <div class="stat"><div class="num">8</div><div class="lbl">Curated profiles</div></div>
  <div class="stat"><div class="num">&ge;2</div><div class="lbl">Reviewers to corroborate</div></div>
  <div class="stat"><div class="num">80</div><div class="lbl">Confidence threshold</div></div>
</div>

<h2 id="why">Why a panel?</h2>
<div class="card-grid">
  <div class="card">
    <div class="card-ico">1</div>
    <h3>One model misses bugs</h3>
    <p>Even frontier models have blind spots. A single reviewer&rsquo;s recall is capped by its own biases.</p>
  </div>
  <div class="card">
    <div class="card-ico">2</div>
    <h3>Two produce noise</h3>
    <p>Add a second voice and you get more coverage &mdash; but also more false positives competing for attention.</p>
  </div>
  <div class="card">
    <div class="card-ico">6</div>
    <h3>Six, filtered, win</h3>
    <p>A panel filtered by a confidence threshold and a corroboration boost surfaces real issues and suppresses the noise.</p>
  </div>
</div>

<h2 id="features">What you get</h2>
<div class="card-grid">
  <div class="card"><h3><a href="reviewers.html">Frontier roster</a></h3><p>GLM&#8209;5.2, MiniMax&nbsp;M3, DeepSeek&nbsp;V4&nbsp;Pro, Kimi, Qwen, Grok, plus Codex / Claude / OpenCode CLIs.</p></div>
  <div class="card"><h3><a href="configuration.html">Routing preference</a></h3><p>One knob picks OpenRouter-first (public default) or your own direct-API subscriptions first.</p></div>
  <div class="card"><h3><a href="architecture.html">Corroboration merge</a></h3><p>Confidence threshold + a +15 boost when reviewers agree, with &plusmn;3-line clustering.</p></div>
  <div class="card"><h3><a href="benchmarks.html">Benchmark mode</a></h3><p>Score reviewers against labeled fixtures (precision / recall / F1) to build a leaderboard.</p></div>
  <div class="card"><h3><a href="profiles.html">Profiles</a></h3><p>quick, standard, panel, security, deep, favorites, direct, leaderboard&#8209;top5.</p></div>
  <div class="card"><h3><a href="faq.html">Privacy-aware</a></h3><p>API keys live only in your environment &mdash; never written to disk by Argus.</p></div>
</div>

<h2 id="quick-start">Quick start</h2>
<p>Inside Claude Code, the simplest invocation reviews your current diff with the default
<code>standard</code> profile:</p>
<pre><code>/argus
/argus --profile security
/argus --custom "glm-5.2,deepseek-v4-pro,claude"
/argus --pr https://github.com/owner/repo/pull/123
/argus --benchmark --runs 3
/argus --dry-run</code></pre>
<p>Prefer the shell? The end-to-end pipeline is three scripts &mdash; estimate, dispatch, merge:</p>
<pre><code>RUN_DIR="$ARGUS_HOME/runs/$(date +%Y%m%dT%H%M%S)-manual"; mkdir -p "$RUN_DIR"
git diff HEAD &gt; "$RUN_DIR/diff.patch"
python scripts/estimate_cost.py --roster "glm-5.2,minimax-m3,gemini-or,codex" --diff "$RUN_DIR/diff.patch"
python scripts/dispatch.py --run-dir "$RUN_DIR" --roster "glm-5.2,minimax-m3,gemini-or,codex" --diff "$RUN_DIR/diff.patch"
python scripts/merge.py --run-dir "$RUN_DIR"</code></pre>

<div class="callout tip"><div class="ico">&#128161;</div><div>
<strong>New here?</strong><p>Head to <a href="getting-started.html">Getting Started</a> for a beginner track
(one API key, five commands) and an advanced track (direct-API routing, profiles, parallel benchmarks).</p>
</div></div>
""",
    "toc": [("why", "Why a panel?"), ("features", "What you get"),
            ("quick-start", "Quick start")],
}


# -------------------------------------------------------- getting-started --- #
PAGES["getting-started"] = {
    "title": "Getting Started",
    "desc": "Onboarding for Argus: a beginner track (clone, one API key, verify, run /argus) and an advanced track (direct-API routing, profiles, parallel benchmarks, host-CLI awareness).",
    "md_label": "View SKILL.md",
    "md_url": BLOB + "/SKILL.md",
    "body": r"""
<p>Argus runs two ways: as the <code>/argus</code> Claude Code skill, or as standalone Python scripts
from a shell. Both share the same <a href="configuration.html">config.yaml</a> and environment variables.
Pick the track that matches you.</p>

<div class="callout note"><div class="ico">&#9989;</div><div>
<strong>Prerequisites</strong>
<ul>
  <li><strong>Python 3.10+</strong> (the project targets 3.12).</li>
  <li><strong>git</strong> &mdash; Argus reviews diffs.</li>
  <li><strong><a href="https://github.com/sigoden/aichat" target="_blank" rel="noopener">aichat</a></strong> &mdash; the universal LLM client Argus uses for API-routed reviewers.</li>
  <li><strong>At least one API key</strong> in your environment. For the easiest start, just an <code>OPENROUTER_API_KEY</code>.</li>
  <li>Python packages: <code>pyyaml</code> and <code>psutil</code>.</li>
</ul>
</div></div>

<h2 id="beginner">Beginner track</h2>
<p>Five steps. One key. You will be reviewing diffs in a couple of minutes.</p>

<h3>1. Clone and enter the repo</h3>
<pre><code>git clone https://github.com/jimstratus/argus.git
cd argus</code></pre>

<h3>2. Install the Python dependencies</h3>
<pre><code>pip install pyyaml psutil</code></pre>

<h3>3. Point Argus at itself</h3>
<p><code>ARGUS_HOME</code> tells every script where the config and prompts live. Set it to the repo root:</p>
<pre><code>export ARGUS_HOME=$PWD</code></pre>

<h3>4. Set one API key</h3>
<p>The public default route is OpenRouter &mdash; a single key covers most reviewers. Keys live only in
your environment; Argus never writes them to disk.</p>
<pre><code>export OPENROUTER_API_KEY="sk-or-..."</code></pre>

<h3>5. Generate the aichat config, verify, and review</h3>
<p><code>install_aichat.py</code> writes <code>~/.config/aichat/config.yaml</code> with the provider client
definitions (no keys on disk &mdash; keys are forwarded from the environment at dispatch time).</p>
<pre><code>python scripts/install_aichat.py --merge
python scripts/verify.py --all
</code></pre>
<p>Then run a review. Inside Claude Code:</p>
<pre><code>/argus</code></pre>
<p>That reviews your current diff with the default <code>standard</code> profile and prints one merged review.</p>

<div class="callout tip"><div class="ico">&#128161;</div><div>
<strong>Try a dry run first</strong><p><code>/argus --dry-run</code> resolves the roster and shows the cost estimate
without spending anything. Great for a sanity check.</p>
</div></div>

<h2 id="advanced">Advanced track</h2>
<p>For power users with their own provider subscriptions, large diffs, and benchmark needs.</p>

<h3>Multiple provider keys + direct-API routing</h3>
<p>Three reviewers are <strong>dual-route</strong>: <code>glm-5.2</code>, <code>minimax-m3</code>, and
<code>deepseek-v4-pro</code>. With their direct keys set, you can prefer each provider&rsquo;s own API
first (cheaper, uses your subscriptions) and keep OpenRouter as the fallback.</p>
<pre><code>export ZAI_API_KEY="..."          # GLM direct (z.ai Coding Plan)
export MINIMAX_API_KEY="..."      # MiniMax direct
export DEEPSEEK_API_KEY="..."     # DeepSeek direct (api.deepseek.com)

# Choose direct-first for this run:
python scripts/verify.py --all --prefer-direct
# or persist it:  set route_preference: direct in config.yaml
# or per-shell:   export ARGUS_ROUTE_PREF=direct</code></pre>
<p>See <a href="configuration.html#routing">Routing preference</a> for the full precedence rules. CLI
reviewers (Codex / Claude / OpenCode / Gemini) are never reordered &mdash; their subscription stays primary.</p>

<h3>Profiles</h3>
<p>Skip naming individual reviewers &mdash; pick a <a href="profiles.html">profile</a>:</p>
<pre><code>/argus --profile panel        # maximum coverage
/argus --profile security     # auth / crypto / input focus
/argus --profile deep         # long-context reviewers for large diffs
/argus --profile direct       # direct-API subs only (pair with route_preference: direct)</code></pre>

<h3>Manual shell pipeline</h3>
<pre><code>RUN_DIR="$ARGUS_HOME/runs/$(date +%Y%m%dT%H%M%S)-manual"; mkdir -p "$RUN_DIR"
git diff HEAD &gt; "$RUN_DIR/diff.patch"
python scripts/estimate_cost.py --roster "glm-5.2,minimax-m3,gemini-or,codex" --diff "$RUN_DIR/diff.patch"
python scripts/dispatch.py --run-dir "$RUN_DIR" --roster "glm-5.2,minimax-m3,gemini-or,codex" --diff "$RUN_DIR/diff.patch"
python scripts/merge.py --run-dir "$RUN_DIR"</code></pre>

<h3>Benchmark seeding + parallel shells</h3>
<p>Benchmark mode scores reviewers against labeled fixtures to build a <a href="benchmarks.html">leaderboard</a>.
Always dry-run a single fixture first to catch provider-config bugs in ~30 seconds:</p>
<pre><code>python scripts/benchmark.py --runs 1 --fixtures sql-injection --profile panel   # smoke test
python scripts/benchmark.py --runs 3 --profile panel                            # full run</code></pre>
<p>The recommended protocol is <strong>one shell per reviewer, max five concurrent</strong>, with a hard
wall-cap per reviewer (<code>--max-wall-sec</code>) so a single stalled provider never blocks the run.
Each reviewer writes its own incremental JSON for tailable progress.</p>

<h3>Host-CLI awareness</h3>
<p>Argus detects the CLI host it runs inside (claude / codex / gemini / opencode / unknown) and never asks a
host CLI to review its own invocation. Inside Claude Code the <code>claude</code> reviewer is auto-skipped.
For profile rosters, the <code>claude</code> reviewer is auto-added when the host is not Claude. See the
<a href="architecture.html#host">host-CLI table</a>.</p>
""",
    "toc": [("beginner", "Beginner track"), ("advanced", "Advanced track")],
}


# ---------------------------------------------------------- configuration --- #
PAGES["configuration"] = {
    "title": "Configuration",
    "desc": "How Argus is configured: config.yaml structure, the route_preference knob, environment variables, aichat clients, and cost gates.",
    "md_label": "View config.yaml",
    "md_url": BLOB + "/config.yaml",
    "mermaid": True,
    "body": r"""
<p>Everything about Argus &mdash; the reviewer registry, profiles, host rules, routing, CLI commands, and
cost gates &mdash; lives in <a href="https://github.com/jimstratus/argus/blob/master/config.yaml" target="_blank" rel="noopener"><code>config.yaml</code></a>.
API keys are the one thing that is <em>not</em> in config: they come from environment variables only.</p>

<h2 id="structure">config.yaml at a glance</h2>
<div class="table-wrap"><table>
<thead><tr><th>Section</th><th>What it holds</th></tr></thead>
<tbody>
<tr><td><code>defaults</code></td><td>Global knobs: <code>route_preference</code>, confidence threshold, corroboration boost, <code>merge_line_tolerance</code>, default profile.</td></tr>
<tr><td><code>reviewers</code></td><td>The registry &mdash; one entry per reviewer with its route(s), model IDs, context window, tier, and cost.</td></tr>
<tr><td><code>profiles</code></td><td>Named rosters (quick, standard, panel, security, deep, favorites, direct, leaderboard-top5).</td></tr>
<tr><td><code>host_rules</code></td><td>Per-host <code>skip</code> / <code>add</code> rules for host-CLI awareness.</td></tr>
<tr><td><code>cost</code></td><td>Warn / hard-block thresholds for review and benchmark modes.</td></tr>
</tbody>
</table></div>

<h2 id="routing">Routing preference <span class="badge">new</span></h2>
<p>A single knob, <code>route_preference</code> under <code>defaults:</code>, decides which provider a
<strong>dual-route</strong> reviewer tries <em>first</em>:</p>
<div class="table-wrap"><table>
<thead><tr><th>Value</th><th>Order</th><th>When to use</th></tr></thead>
<tbody>
<tr><td><code>openrouter</code> <span class="badge green">public default</span></td><td>OpenRouter first, direct API as fallback.</td><td>The simplest setup &mdash; one <code>OPENROUTER_API_KEY</code> covers most reviewers.</td></tr>
<tr><td><code>direct</code></td><td>Each provider&rsquo;s own API first, OpenRouter as fallback.</td><td>Cheaper / use your own subscriptions, or when your OpenRouter balance is depleted.</td></tr>
</tbody>
</table></div>
<p>Only the three dual-route reviewers are reordered by this knob: <code>glm-5.2</code>,
<code>minimax-m3</code>, and <code>deepseek-v4-pro</code>. <strong>CLI reviewers</strong>
(Codex / Claude / OpenCode / Gemini) are <em>never</em> reordered &mdash; their CLI subscription stays
primary and OpenRouter stays a true fallback.</p>

<h3 id="precedence">Override precedence</h3>
<p>Precedence is <strong>CLI flag &gt; env var &gt; config</strong>:</p>
<pre><code># 1. CLI flag on dispatch.py / verify.py / benchmark.py / estimate_cost.py
python scripts/dispatch.py ... --route-pref direct
python scripts/verify.py --all --prefer-direct        # shorthand
python scripts/dispatch.py ... --prefer-openrouter    # shorthand

# 2. Environment variable
export ARGUS_ROUTE_PREF=direct

# 3. config.yaml default
#    defaults:
#      route_preference: openrouter</code></pre>
<div class="callout tip"><div class="ico">&#129520;</div><div>
<strong>The <code>direct</code> profile</strong><p>For when your OpenRouter balance is depleted, pair
<code>route_preference: direct</code> with the <a href="profiles.html"><code>direct</code> profile</a>
(direct-API subs only, no Gemini): <code>glm-5.2, minimax-m3, deepseek-v4-pro, codex, claude, opencode</code>.</p>
</div></div>

<h2 id="env">Environment variables</h2>
<p>API keys live in the environment, never on disk. aichat reads <code>AICHAT_&lt;CLIENT&gt;_API_KEY</code>,
which Argus forwards from <code>$&lt;PROVIDER&gt;_API_KEY</code> at subprocess dispatch time. The Claude CLI
uses its own auth.</p>
<div class="table-wrap"><table>
<thead><tr><th>Variable</th><th>Purpose</th><th>Required?</th></tr></thead>
<tbody>
<tr><td><code>ARGUS_HOME</code></td><td>Path to the Argus checkout</td><td><span class="badge red">required</span> (set to repo root)</td></tr>
<tr><td><code>OPENROUTER_API_KEY</code></td><td>OpenRouter &mdash; covers most reviewers</td><td><span class="badge green">recommended</span> (public default route)</td></tr>
<tr><td><code>ZAI_API_KEY</code></td><td>z.ai Coding Plan endpoint (GLM direct)</td><td>optional</td></tr>
<tr><td><code>MINIMAX_API_KEY</code></td><td>MiniMax direct</td><td>optional</td></tr>
<tr><td><code>DEEPSEEK_API_KEY</code> <span class="badge">new</span></td><td>DeepSeek direct (api.deepseek.com)</td><td>optional</td></tr>
<tr><td><code>KIMI_API_KEY</code></td><td>Consumer-scoped (not Moonshot Platform)</td><td>optional</td></tr>
<tr><td><code>GEMINI_API_KEY</code></td><td>Gemini</td><td>optional</td></tr>
<tr><td><code>OPENAI_API_KEY</code></td><td>Used by the Codex CLI fallback</td><td>optional</td></tr>
<tr><td><code>NOUSRESEARCH_API_KEY</code></td><td>Hermes direct</td><td>optional</td></tr>
<tr><td><code>ARGUS_ROUTE_PREF</code></td><td><code>openrouter</code> | <code>direct</code> route override</td><td>optional</td></tr>
<tr><td><code>ARGUS_YES_COST=1</code></td><td>Downgrade a cost hard-block to a warning</td><td>optional</td></tr>
</tbody>
</table></div>

<h2 id="aichat">aichat clients</h2>
<p>Run <code>python scripts/install_aichat.py --merge</code> to generate
<code>~/.config/aichat/config.yaml</code> with a client definition per provider route. No keys are written
&mdash; each client reads its <code>AICHAT_&lt;CLIENT&gt;_API_KEY</code> from the environment, which Argus
sets at dispatch. The universal aichat adapter handles all of the OpenRouter and direct-API routes.</p>

<h2 id="cost">Cost gates</h2>
<p>Before any spend, Argus estimates cost and applies a warn / hard-block gate.</p>
<div class="table-wrap"><table>
<thead><tr><th>Mode</th><th>Warn</th><th>Hard block</th><th>Override</th></tr></thead>
<tbody>
<tr><td>review</td><td>$0.50</td><td>$2.00</td><td><code>--yes-cost</code> / <code>ARGUS_YES_COST=1</code></td></tr>
<tr><td>benchmark</td><td>$10</td><td>$30</td><td><code>--yes-cost</code> / <code>ARGUS_YES_COST=1</code></td></tr>
<tr><td>OR balance</td><td>auto warn (review)</td><td>blocks (benchmark) when available &lt; safety&times;estimate</td><td><code>--skip-balance-check</code></td></tr>
</tbody>
</table></div>
<p>Paid-CLI reviewers (Gemini / Codex / Claude / OpenCode / Copilot) have <code>cost_per_m: null</code>,
so they count as $0 in the estimate.</p>

<h3 id="cost-flow">Cost-gate flow</h3>
<div class="mermaid">
flowchart TD
  A[Resolve roster] --> B[Estimate $ per reviewer]
  B --> C{Total &gt; hard block?}
  C -- yes --> D{--yes-cost or ARGUS_YES_COST?}
  D -- no --> X[Abort: cost block]
  D -- yes --> E[Warn and continue]
  C -- no --> F{Total &gt; warn threshold?}
  F -- yes --> E
  F -- no --> G[Proceed silently]
  E --> H{OpenRouter balance &lt; safety x estimate?}
  G --> H
  H -- yes, benchmark --> X2[Abort: low balance]
  H -- yes, review --> I[Warn and continue]
  H -- no --> J[Dispatch reviewers]
  I --> J
</div>
""",
    "toc": [("structure", "config.yaml"), ("routing", "Routing preference"),
            ("env", "Environment variables"), ("aichat", "aichat clients"),
            ("cost", "Cost gates")],
}


# -------------------------------------------------------------- reviewers --- #
PAGES["reviewers"] = {
    "title": "Reviewers",
    "desc": "The Argus reviewer registry: 15 frontier LLM reviewers with their routes and notes, including the dual-route GLM-5.2, MiniMax M3, and DeepSeek V4 Pro.",
    "md_label": "View config.yaml",
    "md_url": BLOB + "/config.yaml",
    "body": r"""
<p>The registry has <strong>15 reviewers</strong>. Three are <strong>dual-route</strong> (a direct provider
API plus OpenRouter) and are reordered by the <a href="configuration.html#routing">routing preference</a>;
the rest are single-route API reviewers or paid-CLI reviewers. Model versions are the headline of this
release: <strong>GLM&#8209;5.2</strong>, <strong>MiniMax&nbsp;M3</strong>, and the new default
<strong>DeepSeek&nbsp;V4&nbsp;Pro</strong>.</p>

<div class="table-wrap"><table>
<thead><tr><th>Reviewer</th><th>Route(s)</th><th>Notes</th></tr></thead>
<tbody>
<tr><td><code>glm-5.2</code> <span class="badge">dual-route</span></td><td>z.ai direct + OpenRouter (<code>z-ai/glm-5.2</code>)</td><td>Strong security + logic.</td></tr>
<tr><td><code>minimax-m3</code> <span class="badge">dual-route</span></td><td>MiniMax direct + OpenRouter (<code>minimax/minimax-m3</code>)</td><td>High precision.</td></tr>
<tr><td><code>kimi-k2.6</code></td><td>OpenRouter (<code>moonshotai/kimi-k2.5</code>, fallback <code>kimi-k2-thinking</code>)</td><td>Long-context, agentic.</td></tr>
<tr><td><code>mimo-v2-pro</code></td><td>OpenRouter (<code>xiaomi/mimo-v2-pro</code>)</td><td>1M context window.</td></tr>
<tr><td><code>qwen-3.6-plus</code></td><td>OpenRouter (<code>qwen/qwen3.6-plus</code>)</td><td>1M ctx, conservative / high precision.</td></tr>
<tr><td><code>grok-4.20</code></td><td>OpenRouter (<code>x-ai/grok-4.20</code>)</td><td>2M ctx, pricey.</td></tr>
<tr><td><code>deepseek-v4-pro</code> <span class="badge">dual-route</span> <span class="badge green">default DeepSeek</span></td><td>DeepSeek direct + OpenRouter (<code>deepseek/deepseek-v4-pro</code>)</td><td>1.6T MoE, 49B active, ~1M ctx; reasoning + security.</td></tr>
<tr><td><code>deepseek-v3.2</code></td><td>OpenRouter</td><td><span class="badge gray">custom-only</span> superseded by v4-pro.</td></tr>
<tr><td><code>hermes-4.3</code></td><td>Nous direct + OpenRouter fallback</td><td><span class="badge gray">custom-only</span></td></tr>
<tr><td><code>gemini</code></td><td>Gemini CLI (paid sub)</td><td><span class="badge red">disabled</span> Windows .cmd tree-kill re-test pending; use <code>gemini-or</code> meanwhile.</td></tr>
<tr><td><code>gemini-or</code></td><td>OpenRouter (<code>google/gemini-2.5-flash</code>)</td><td>~2s/call, best value.</td></tr>
<tr><td><code>codex</code></td><td>Codex CLI (paid sub, GPT-5.x)</td><td>Thorough, slow; OpenRouter fallback.</td></tr>
<tr><td><code>claude</code></td><td>Claude CLI (paid sub)</td><td>Auto-added to profile rosters when host &ne; claude.</td></tr>
<tr><td><code>opencode</code></td><td>OpenCode CLI (paid sub)</td><td>Top benchmark performer, slow cold start.</td></tr>
<tr><td><code>copilot-gpt5</code></td><td>GitHub Copilot CLI</td><td><span class="badge red">disabled / eliminated</span> agent harness returns prose, not our JSON schema.</td></tr>
</tbody>
</table></div>

<div class="callout note"><div class="ico">&#128260;</div><div>
<strong>Dual-route vs CLI</strong>
<p>The three dual-route reviewers respect <code>route_preference</code>. CLI reviewers
(Codex / Claude / OpenCode / Gemini) keep their subscription primary with OpenRouter as a true fallback,
no matter the routing preference. See <a href="configuration.html#routing">Routing preference</a>.</p>
</div></div>

<p>Ready-made groupings of these reviewers live in <a href="profiles.html">Profiles</a>.</p>
""",
}


# --------------------------------------------------------------- profiles --- #
PAGES["profiles"] = {
    "title": "Profiles",
    "desc": "Argus profiles are named reviewer rosters: quick, standard (default), panel, security, deep, favorites, direct, and leaderboard-top5.",
    "md_label": "View config.yaml",
    "md_url": BLOB + "/config.yaml",
    "body": r"""
<p>A profile is a named roster &mdash; a curated set of <a href="reviewers.html">reviewers</a> for a job.
Pick one with <code>--profile &lt;name&gt;</code>; the default is <code>standard</code>.</p>

<div class="table-wrap"><table>
<thead><tr><th>Profile</th><th>Members</th><th>Use</th></tr></thead>
<tbody>
<tr><td><code>quick</code></td><td>glm-5.2, gemini-or</td><td>2-reviewer smoke test.</td></tr>
<tr><td><code>standard</code> <span class="badge green">default</span></td><td>glm-5.2, minimax-m3, gemini-or, codex</td><td>Everyday review.</td></tr>
<tr><td><code>panel</code></td><td>glm-5.2, minimax-m3, kimi-k2.6, mimo-v2-pro, qwen-3.6-plus, deepseek-v4-pro, gemini-or, codex, claude, opencode</td><td>Maximum coverage.</td></tr>
<tr><td><code>security</code></td><td>glm-5.2, deepseek-v4-pro, codex, claude</td><td>Auth / crypto / input focus (security overlay).</td></tr>
<tr><td><code>deep</code></td><td>mimo-v2-pro, gemini-or, kimi-k2.6, deepseek-v4-pro, codex</td><td>Long-context, large diffs (deep overlay).</td></tr>
<tr><td><code>favorites</code></td><td>glm-5.2, minimax-m3</td><td>Direct-sub picks.</td></tr>
<tr><td><code>direct</code> <span class="badge">new</span></td><td>glm-5.2, minimax-m3, deepseek-v4-pro, codex, claude, opencode</td><td>Direct-API subs only, no Gemini; pair with <code>route_preference: direct</code>.</td></tr>
<tr><td><code>leaderboard-top5</code></td><td>opencode, qwen-3.6-plus, glm-5.2, gemini-or, minimax-m3</td><td>Benchmark winners.</td></tr>
</tbody>
</table></div>

<h2 id="usage">Using a profile</h2>
<pre><code>/argus --profile security
/argus --profile panel
/argus --profile direct        # with route_preference: direct or ARGUS_ROUTE_PREF=direct</code></pre>
<p>Profile rosters get the full host policy applied: disabled reviewers are dropped, the host CLI is
skipped, and the <code>claude</code> reviewer is auto-added when the host is not Claude. Explicit
<code>--custom</code> lists waive those gates &mdash; see <a href="architecture.html#host">host-CLI awareness</a>.</p>

<div class="callout tip"><div class="ico">&#129520;</div><div>
<strong>Need your own set?</strong><p>Use <code>--custom "a,b,c"</code> to name reviewers directly, or add a
new profile under <code>profiles:</code> in <a href="configuration.html">config.yaml</a>.</p>
</div></div>
""",
}


# ----------------------------------------------------------- architecture --- #
PAGES["architecture"] = {
    "title": "Architecture",
    "desc": "How Argus works end to end: the review pipeline, subagent-per-reviewer dispatch, the merge / corroboration logic, host-CLI awareness, and the history.db schema.",
    "md_label": "View DEVELOPMENT.md",
    "md_url": BLOB + "/DEVELOPMENT.md",
    "mermaid": True,
    "body": r"""
<p>Argus is a pipeline: resolve a roster, estimate cost, dispatch reviewers in parallel, then merge their
findings into one review. The quality of the output comes from two ideas working together &mdash; a
confidence threshold and a corroboration boost.</p>

<h2 id="pipeline">Pipeline overview</h2>
<div class="mermaid">
flowchart LR
  D[Diff / PR / files] --> R[Resolve roster<br/>profile + host rules]
  R --> C[Estimate cost<br/>gate check]
  C --> P[Dispatch reviewers<br/>in parallel]
  P --> J[reviews/*.json<br/>strict schema]
  J --> M[Merge:<br/>filter + corroborate + cluster]
  M --> O[merged.md + metrics.json]
  P --> H[(history.db)]
  M --> H
</div>

<h2 id="dispatch">Dispatch pattern</h2>
<p>The default dispatch is <strong>subagent-per-reviewer</strong>, capped at <strong>4 concurrent</strong>;
the rest queue and launch as slots free up. Each subagent runs <code>dispatch.py</code>
<em>synchronously</em> for exactly one reviewer and writes that reviewer&rsquo;s JSON. The legacy / quick
path is a single-process <code>dispatch.py --roster a,b,c,d</code> for rosters of &le;4 reviewers. Either way,
<code>merge.py</code> runs exactly once at the end.</p>
<div class="mermaid">
sequenceDiagram
  participant O as Orchestrator
  participant Q as Queue (cap 4)
  participant S as Subagent (per reviewer)
  participant F as reviews/*.json
  O->>Q: enqueue all reviewers
  loop up to 4 at a time
    Q->>S: launch dispatch.py (one reviewer, sync)
    S-->>F: write &lt;reviewer&gt;.json
    S-->>Q: slot freed
  end
  Q-->>O: all reviewers done
  O->>O: merge.py (runs once)
</div>
<div class="callout warn"><div class="ico">&#9888;</div><div>
<strong>Subagents must run synchronously</strong><p>A subagent must run <code>dispatch.py</code> to
completion before its session ends &mdash; never <code>run_in_background</code> inside the subagent.
Otherwise the session ends first and the review JSON is never written.</p>
</div></div>

<h2 id="merge">Merge &amp; corroboration</h2>
<p>The merge step is where a noisy panel becomes a clean review:</p>
<ul>
  <li><strong>Confidence threshold</strong> &mdash; drop findings with effective confidence below <strong>80</strong>.</li>
  <li><strong>Corroboration boost</strong> &mdash; add <strong>+15</strong> confidence (capped at 100) when
  <strong>&ge;2 reviewers</strong> flag the same file within <strong>&plusmn;3 lines</strong>.</li>
  <li><strong>Anchor-based clustering</strong> &mdash; &plusmn;3-line proximity with dual tolerance (anchor
  <em>and</em> cluster-max) to avoid chain drift; the reported line is the cluster median and the worst
  severity wins.</li>
</ul>
<div class="mermaid">
flowchart TD
  A[All findings from all reviewers] --> B[Cluster by file + anchor +/-3 lines]
  B --> C{>=2 reviewers in cluster?}
  C -- yes --> D[+15 confidence boost, cap 100]
  C -- no --> E[Keep base confidence]
  D --> F{Effective confidence >= 80?}
  E --> F
  F -- no --> G[Drop finding]
  F -- yes --> H[Emit: median line, worst severity]
  H --> I[merged.md + metrics.json]
</div>

<h3 id="schema-json">Finding schema &amp; extraction</h3>
<p>Every reviewer returns strict-schema JSON findings:</p>
<pre><code>{ "file": "...", "line": 0, "severity": "...", "category": "...",
  "description": "...", "confidence": 0 }</code></pre>
<p>A tolerant extractor handles fenced code blocks, <code>&lt;think&gt;</code> reasoning prefixes (Qwen /
DeepSeek-R1 style), and braces inside string values. Other safeguards: a context-window pre-check skips a
reviewer if the prompt exceeds 70% of its context; an OpenRouter reasoning-exclude patch avoids providers
returning <code>{content:null, reasoning:...}</code>; and failure isolation means one broken reviewer never
kills the run (timeouts kill the whole process tree).</p>

<h2 id="host">Host-CLI awareness</h2>
<p>Argus inspects the environment and parent process tree to detect its host CLI, then applies per-host
rules. The rule is simple: never ask a host CLI to review its own invocation, so the matching reviewer is
always skipped. The <code>add</code> column applies to <strong>profile rosters only</strong>, not explicit
<code>--custom</code> lists.</p>
<div class="table-wrap"><table>
<thead><tr><th>Host</th><th>Skip</th><th>Add</th></tr></thead>
<tbody>
<tr><td>claude</td><td>claude</td><td>&mdash;</td></tr>
<tr><td>codex</td><td>codex</td><td>claude</td></tr>
<tr><td>gemini</td><td>gemini</td><td>claude</td></tr>
<tr><td>opencode</td><td>opencode</td><td>claude</td></tr>
<tr><td>unknown</td><td>&mdash;</td><td>&mdash;</td></tr>
</tbody>
</table></div>

<h2 id="schema-db">history.db schema</h2>
<p>Every run is logged to a local SQLite database (<code>history.db</code>) for stats and benchmarks.</p>
<div class="mermaid">
erDiagram
  RUNS ||--o{ REVIEWER_RUNS : has
  REVIEWER_RUNS ||--o{ FINDINGS : produces
  BENCHMARKS ||--o{ REVIEWER_RUNS : scores
  RUNS {
    int id PK
    text timestamp
    text mode
    text roster
    real est_cost
  }
  REVIEWER_RUNS {
    int id PK
    int run_id FK
    text reviewer
    text route
    real wall_sec
    text status
  }
  FINDINGS {
    int id PK
    int reviewer_run_id FK
    text file
    int line
    text severity
    int confidence
  }
  BENCHMARKS {
    int id PK
    text timestamp
    text fixture
    real f1
    real precision
    real recall
  }
</div>
""",
    "toc": [("pipeline", "Pipeline overview"), ("dispatch", "Dispatch pattern"),
            ("merge", "Merge & corroboration"), ("host", "Host-CLI awareness"),
            ("schema-db", "history.db schema")],
}


# ------------------------------------------------------------- benchmarks --- #
PAGES["benchmarks"] = {
    "title": "Benchmarks",
    "desc": "Argus benchmark mode scores each reviewer against labeled fixtures using precision, recall, and F1 to build a leaderboard, with a clean-baseline false-positive control.",
    "md_label": "View DEVELOPMENT.md",
    "md_url": BLOB + "/DEVELOPMENT.md",
    "chart": True,
    "body": r"""
<p>Benchmark mode runs the whole fixture suite across a roster and scores each reviewer against
ground-truth labels. It answers the question that matters when choosing a roster: <em>which reviewers
actually find the planted bugs without crying wolf?</em></p>

<h2 id="metrics">Precision, recall, F1</h2>
<p>A finding <strong>matches</strong> ground truth when the file matches and the line is within tolerance
(<code>|line diff| &le; 3</code> by default). From the true positives (tp), false positives (fp), and false
negatives (fn):</p>
<ul>
  <li><strong>Precision</strong> = tp / (tp + fp) &mdash; of what it flagged, how much was real (low = noisy).</li>
  <li><strong>Recall</strong> = tp / (tp + fn) &mdash; of the real bugs, how many it caught (low = misses bugs).</li>
  <li><strong>F1</strong> = 2&middot;P&middot;R / (P + R) &mdash; the harmonic mean; the headline ranking axis.</li>
</ul>

<h2 id="fixtures">Fixtures &amp; scoring</h2>
<p>The current suite has four diff-based fixtures. The <strong>clean-baseline</strong> is a false-positive
control: it contains no real bug, so the correct output is zero findings.</p>
<div class="table-wrap"><table>
<thead><tr><th>Fixture</th><th>Expected</th></tr></thead>
<tbody>
<tr><td><code>sql-injection</code></td><td>Planted SQL injection.</td></tr>
<tr><td><code>race-refund</code></td><td>Concurrency / race on a refund path.</td></tr>
<tr><td><code>secrets-leak</code></td><td>Leaked secret / credential.</td></tr>
<tr><td><code>clean-baseline</code></td><td><strong>0 findings</strong> &mdash; false-positive control.</td></tr>
</tbody>
</table></div>
<p>A clean baseline with no findings scores P = R = F1 = 1.0 &mdash; but only for successful, parseable runs
(a reviewer that crashes or returns garbage does not get a free perfect score).</p>

<h2 id="leaderboard">Reference leaderboard</h2>
<p>F1 score by reviewer, from the reference benchmark run. The chart re-themes with light / dark mode.</p>
<div class="chart-wrap" style="height:360px">
  <canvas id="bench-chart" data-bench='[["opencode",0.811],["qwen-3.6-plus",0.761],["glm-5.x",0.697],["gemini-or",0.681],["minimax",0.674],["mimo-v2-pro",0.652],["codex",0.581],["deepseek",0.572],["grok-4.20",0.557],["hermes-4.3",0.551],["kimi-k2.6",0.505]]'></canvas>
</div>
<div class="table-wrap"><table>
<thead><tr><th>Rank</th><th>Reviewer</th><th>F1</th><th>Precision</th><th>Recall</th><th>Avg call (s)</th></tr></thead>
<tbody>
<tr><td>1</td><td>opencode</td><td>0.811</td><td>0.896</td><td>0.754</td><td>48</td></tr>
<tr><td>2</td><td>qwen-3.6-plus</td><td>0.761</td><td>1.000</td><td>0.650</td><td>76</td></tr>
<tr><td>3</td><td>glm-5.x</td><td>0.697</td><td>0.772</td><td>0.725</td><td>27</td></tr>
<tr><td>4</td><td>gemini-or (Flash)</td><td>0.681</td><td>0.736</td><td>0.639</td><td>2</td></tr>
<tr><td>5</td><td>minimax</td><td>0.674</td><td>0.875</td><td>0.588</td><td>29</td></tr>
<tr><td>6</td><td>mimo-v2-pro</td><td>0.652</td><td>0.736</td><td>0.600</td><td>49</td></tr>
<tr><td>7</td><td>codex</td><td>0.581</td><td>0.688</td><td>0.754</td><td>60</td></tr>
<tr><td>8</td><td>deepseek</td><td>0.572</td><td>0.778</td><td>0.494</td><td>6</td></tr>
<tr><td>9</td><td>grok-4.20</td><td>0.557</td><td>0.592</td><td>0.533</td><td>2</td></tr>
<tr><td>10</td><td>hermes-4.3</td><td>0.551</td><td>0.646</td><td>0.653</td><td>13</td></tr>
<tr><td>11</td><td>kimi-k2.6</td><td>0.505</td><td>0.729</td><td>0.575</td><td>83</td></tr>
</tbody>
</table></div>
<p class="muted"><strong>Footnote:</strong> This is a historical run (4 fixtures &times; 3 runs = 12 calls per
reviewer, ~$0.42 total). Reviewer names have since been version-bumped (e.g. <code>glm-5.x</code> &rarr;
<code>glm-5.2</code>, <code>minimax</code> &rarr; <code>minimax-m3</code>, <code>deepseek</code> &rarr;
<code>deepseek-v4-pro</code>); the numbers are shown as-recorded. With only four fixtures the leaderboard is
noisy &mdash; treat it as directional.</p>

<h2 id="running">Running a benchmark</h2>
<pre><code># Smoke test one fixture first (catches config bugs in ~30s):
python scripts/benchmark.py --runs 1 --fixtures sql-injection --profile panel

# Full run across the suite:
python scripts/benchmark.py --runs 3 --profile panel
python scripts/benchmark.py --runs 3 --roster "glm-5.2,minimax-m3,opencode"</code></pre>
<p>Average call time is a cost / quality trade-off column, not a ranking axis: a fast, cheap frontier
reviewer wins over a slow, expensive one when F1 is comparable.</p>
""",
    "toc": [("metrics", "Precision, recall, F1"), ("fixtures", "Fixtures & scoring"),
            ("leaderboard", "Reference leaderboard"), ("running", "Running a benchmark")],
}


# ----------------------------------------------------------- contributing --- #
PAGES["contributing"] = {
    "title": "Contributing",
    "desc": "How to contribute to Argus: adding or changing reviewers and providers (config-only), contributing benchmark fixtures, running tests, and the don't-break rules.",
    "md_label": "View CONTRIBUTING.md",
    "md_url": BLOB + "/CONTRIBUTING.md",
    "body": r"""
<p>Argus is built so the most common contributions are <strong>config-only</strong> &mdash; you rarely need
to touch Python to add a reviewer or a profile. Thanks for helping the panel see more.</p>

<h2 id="reviewers">Reviewer &amp; provider changes</h2>
<p>Adding, removing, or re-versioning a reviewer is a <a href="configuration.html">config.yaml</a> edit:
add an entry under <code>reviewers</code> with its route(s), model ID(s), context window, tier, and cost.
For a new <em>provider</em> route, add a client to the aichat generator
(<code>scripts/install_aichat.py</code>) and forward its <code>$&lt;PROVIDER&gt;_API_KEY</code>. No keys go
in the repo &mdash; ever.</p>
<ul>
  <li>Reuse the universal aichat adapter for any OpenAI-compatible endpoint.</li>
  <li>Mark superseded models <code>custom_only</code> rather than deleting them.</li>
  <li>Keep model IDs pinned; document upstream renames.</li>
</ul>

<h2 id="fixtures">Fixture contributions</h2>
<p>The leaderboard is only as good as its fixtures, and four is too few. New fixtures are very welcome:
auth bypass, XSS, null-deref, async races, TOCTOU, and more.</p>
<p>A fixture is a directory under <code>fixtures/</code> containing:</p>
<ul>
  <li><code>diff.patch</code> &mdash; the diff under review.</li>
  <li><code>ground-truth.json</code> &mdash; the labeled findings (file + line + severity) the panel should catch.</li>
</ul>
<p>Add at least one <strong>clean</strong> variant where appropriate so false positives are penalized.
Fixtures are diff-based &mdash; do not copy OMC&rsquo;s code-file fixtures directly; their schema differs.</p>

<h2 id="tests">Tests</h2>
<p>Run the suite before opening a PR:</p>
<pre><code>python -m pytest</code></pre>
<p>Add tests for new parsing paths (the JSON extractor is the riskiest surface) and for any merge / scoring
change.</p>

<h2 id="dont-break">Don&rsquo;t-break rules</h2>
<div class="callout warn"><div class="ico">&#9888;</div><div>
<ul>
  <li><strong>Don&rsquo;t re-implement &plusmn;3 bucketing</strong> &mdash; anchor-based clustering already
  exists in <code>merge.py</code>. Extend it; don&rsquo;t duplicate it.</li>
  <li><strong>Keep the finding schema strict</strong> &mdash; <code>{file, line, severity, category,
  description, confidence}</code>. Downstream merge and benchmark scoring depend on it.</li>
  <li><strong>Never write API keys to disk.</strong> Keys stay in the environment, forwarded at dispatch.</li>
  <li><strong>Preserve failure isolation</strong> &mdash; one broken reviewer must never kill the run.</li>
  <li><strong>CLI reviewers are never reordered</strong> by routing preference.</li>
</ul>
</div></div>

<p>See <a href="https://github.com/jimstratus/argus/blob/master/CONTRIBUTING.md" target="_blank" rel="noopener">CONTRIBUTING.md</a>
and <a href="https://github.com/jimstratus/argus/blob/master/DEVELOPMENT.md" target="_blank" rel="noopener">DEVELOPMENT.md</a>
for the full developer guide.</p>
""",
    "toc": [("reviewers", "Reviewer changes"), ("fixtures", "Fixtures"),
            ("tests", "Tests"), ("dont-break", "Don't-break rules")],
}


# ------------------------------------------------------------------- faq ---- #
PAGES["faq"] = {
    "title": "FAQ",
    "desc": "Frequently asked questions about Argus: which models, which keys you need, OpenRouter vs direct API, privacy, Windows support, cost, and adding a reviewer.",
    "md_label": "View README.md",
    "md_url": BLOB + "/README.md",
    "body": r"""
<p>Short answers to the things people ask first. For depth, follow the links into the rest of the KB.</p>

<details class="faq" open><summary>What models does Argus use?</summary><div class="faq-body">
<p>A registry of 15 frontier reviewers &mdash; GLM&#8209;5.2, MiniMax&nbsp;M3, DeepSeek&nbsp;V4&nbsp;Pro,
Kimi&nbsp;K2.6, MiMo&#8209;V2&#8209;Pro, Qwen&nbsp;3.6&#8209;Plus, Grok&nbsp;4.20, plus the Codex, Claude, and
OpenCode CLIs. See the full <a href="reviewers.html">reviewer roster</a>.</p>
</div></details>

<details class="faq"><summary>Do I need all the API keys?</summary><div class="faq-body">
<p>No. The public default route is OpenRouter, so a single <code>OPENROUTER_API_KEY</code> covers most
reviewers. Direct provider keys (<code>ZAI_API_KEY</code>, <code>MINIMAX_API_KEY</code>,
<code>DEEPSEEK_API_KEY</code>) are optional &mdash; add them only if you want direct-API routing. See the
<a href="configuration.html#env">environment variables table</a>.</p>
</div></details>

<details class="faq"><summary>OpenRouter vs direct API &mdash; what&rsquo;s the difference?</summary><div class="faq-body">
<p>OpenRouter is one key in front of many models &mdash; simplest to set up. Direct APIs use each
provider&rsquo;s own endpoint, which can be cheaper and lets you use subscriptions you already pay for.
Three reviewers are dual-route and can use either; the <code>route_preference</code> knob picks which they
try first. See <a href="configuration.html#routing">Routing preference</a>.</p>
</div></details>

<details class="faq"><summary>How do I switch to direct API?</summary><div class="faq-body">
<p>Any of three ways (precedence: CLI flag &gt; env var &gt; config):</p>
<pre><code>python scripts/verify.py --all --prefer-direct   # per-run flag
export ARGUS_ROUTE_PREF=direct                    # per-shell env var
# or set  defaults.route_preference: direct  in config.yaml</code></pre>
<p>Pair it with the <a href="profiles.html"><code>direct</code> profile</a> when your OpenRouter balance is depleted.</p>
</div></details>

<details class="faq"><summary>Is my code sent anywhere? What about privacy?</summary><div class="faq-body">
<p>Your diff is sent to whichever reviewers you select, via their provider APIs or CLIs &mdash; that is
inherent to LLM review. What Argus does <em>not</em> do: it never writes your API keys to disk. Keys live in
your environment and are forwarded to subprocesses only at dispatch time. Choose a privacy-appropriate
roster for sensitive code.</p>
</div></details>

<details class="faq"><summary>Does Argus work on Windows?</summary><div class="faq-body">
<p>Yes &mdash; it is developed on Windows 11 (with Git Bash). Use <code>py -3.12</code> to invoke Python and
set <code>PYTHONIOENCODING=utf-8</code> for non-ASCII output. One known caveat: the Gemini CLI reviewer is
currently disabled pending a Windows <code>.cmd</code> tree-kill re-test &mdash; use <code>gemini-or</code>
(the OpenRouter route) meanwhile.</p>
</div></details>

<details class="faq"><summary>How much does a review cost?</summary><div class="faq-body">
<p>Usually cents. A typical review stays well under the $0.50 warning gate; the reference benchmark of 12
calls per reviewer across the suite totaled about $0.42. Cost gates warn at $0.50 and hard-block at $2.00
for reviews ($10 / $30 for benchmarks). Paid-CLI reviewers count as $0 in the estimate. See
<a href="configuration.html#cost">cost gates</a>.</p>
</div></details>

<details class="faq"><summary>How do I add a reviewer?</summary><div class="faq-body">
<p>Add an entry under <code>reviewers</code> in <a href="configuration.html">config.yaml</a> with its route(s)
and model ID(s); for a new provider, add a client in <code>install_aichat.py</code> and forward its
<code>$&lt;PROVIDER&gt;_API_KEY</code>. It&rsquo;s config-only in the common case &mdash; see
<a href="contributing.html#reviewers">Contributing</a>.</p>
</div></details>
""",
}


# -------------------------------------------------------------- glossary --- #
PAGES["glossary"] = {
    "title": "Glossary",
    "desc": "Definitions of Argus terms: reviewer, route, roster, profile, corroboration boost, confidence threshold, fixture, F1, host CLI, aichat, and overlay.",
    "md_label": "View README.md",
    "md_url": BLOB + "/README.md",
    "body": r"""
<p>Short definitions for the vocabulary used across the Argus docs.</p>
<dl class="gloss">
<dt>Reviewer</dt>
<dd>A single LLM (via an API route or a CLI) that examines the diff and returns findings. The 15 reviewers live in the <a href="reviewers.html">registry</a>.</dd>

<dt>Route</dt>
<dd>How a reviewer is reached &mdash; e.g. a direct provider API (z.ai, MiniMax, DeepSeek), OpenRouter, or a paid CLI. Dual-route reviewers have more than one.</dd>

<dt>Roster</dt>
<dd>The concrete set of reviewers chosen for a run, after a profile and host rules are applied.</dd>

<dt>Profile <span class="badge gray">named roster</span></dt>
<dd>A named, reusable roster in config.yaml: quick, standard, panel, security, deep, favorites, direct, leaderboard-top5. See <a href="profiles.html">Profiles</a>.</dd>

<dt>Route preference</dt>
<dd>The <code>route_preference</code> knob (<code>openrouter</code> | <code>direct</code>) that decides which provider a dual-route reviewer tries first. See <a href="configuration.html#routing">Configuration</a>.</dd>

<dt>Confidence threshold</dt>
<dd>The minimum effective confidence (80) a finding must reach to survive the merge. Lower-confidence findings are dropped.</dd>

<dt>Corroboration boost</dt>
<dd>+15 confidence (capped at 100) applied when &ge;2 reviewers flag the same file within &plusmn;3 lines &mdash; agreement is evidence.</dd>

<dt>Fixture</dt>
<dd>A labeled benchmark case: a <code>diff.patch</code> plus a <code>ground-truth.json</code> of the findings a good reviewer should catch. Includes a clean-baseline control. See <a href="benchmarks.html">Benchmarks</a>.</dd>

<dt>F1</dt>
<dd>The harmonic mean of precision and recall: <code>2&middot;P&middot;R / (P + R)</code>. The headline benchmark ranking axis.</dd>

<dt>Host CLI</dt>
<dd>The CLI Argus is running inside (claude / codex / gemini / opencode / unknown). The matching reviewer is always skipped so a CLI never reviews its own invocation. See <a href="architecture.html#host">host-CLI awareness</a>.</dd>

<dt>aichat</dt>
<dd>The universal LLM client Argus uses for API-routed reviewers. Its config is generated by <code>install_aichat.py</code>; keys are read from <code>AICHAT_&lt;CLIENT&gt;_API_KEY</code> at dispatch.</dd>

<dt>Overlay</dt>
<dd>A prompt add-on layered on the base reviewer prompt to focus a run &mdash; e.g. the <code>security</code> and <code>deep</code> overlays used by the matching profiles.</dd>
</dl>
""",
}


# ------------------------------------------------------------------- 404 ---- #
PAGES["404"] = {
    "title": "Page not found",
    "desc": "That page does not exist. Return to the Argus knowledge base.",
    "md_label": "View README.md",
    "md_url": BLOB + "/README.md",
    "body": r"""
<div class="callout note"><div class="ico">&#128064;</div><div>
<strong>Even a hundred eyes can&rsquo;t find this one.</strong>
<p>The page you&rsquo;re looking for doesn&rsquo;t exist or has moved.</p>
</div></div>
<p>Try one of these:</p>
<div class="card-grid">
  <div class="card"><h3><a href="index.html">Home</a></h3><p>What Argus is and why a panel beats a single model.</p></div>
  <div class="card"><h3><a href="getting-started.html">Getting Started</a></h3><p>Onboarding for beginners and advanced users.</p></div>
  <div class="card"><h3><a href="architecture.html">Architecture</a></h3><p>The pipeline, dispatch, and merge logic.</p></div>
  <div class="card"><h3><a href="faq.html">FAQ</a></h3><p>Quick answers to common questions.</p></div>
</div>
""",
}
