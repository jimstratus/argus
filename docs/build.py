#!/usr/bin/env python3
"""Argus knowledge-base static-site generator (stdlib only).

Run:  python3 docs/build.py

Writes:
  docs/assets/style.css   shared CSS
  docs/assets/app.js      shared JS (theme, sidebar, copy, mermaid re-theme, charts)
  docs/<slug>.html        one file per page with shared chrome
  docs/.nojekyll          empty (disable Jekyll)
  docs/llms.txt           AI-friendly project summary + page index

Design goals: readable, no external build deps, no copy-paste chrome drift.
"""

from __future__ import annotations

import os
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")

SITE_TITLE = "Argus"
SITE_TAGLINE = "Multi-model code review, in parallel."
REPO = "https://github.com/jimstratus/argus"
REPO_BLOB = REPO + "/blob/master"
BASE_URL = "https://jimstratus.github.io/argus/"
YEAR = datetime.date.today().year

# --------------------------------------------------------------------------- #
#  Navigation model
# --------------------------------------------------------------------------- #
# group -> list of (slug, title)
NAV = [
    ("Start", [
        ("index", "Home"),
        ("getting-started", "Getting Started"),
        ("configuration", "Configuration"),
    ]),
    ("Reference", [
        ("reviewers", "Reviewers"),
        ("profiles", "Profiles"),
        ("architecture", "Architecture"),
        ("benchmarks", "Benchmarks"),
    ]),
    ("Project", [
        ("contributing", "Contributing"),
        ("faq", "FAQ"),
        ("glossary", "Glossary"),
    ]),
]

SLUG_TITLE = {slug: title for _, items in NAV for slug, title in items}


# --------------------------------------------------------------------------- #
#  Page content is imported from build_content.py to keep this file readable.
# --------------------------------------------------------------------------- #
from build_content import PAGES, CSS, JS  # noqa: E402


def render_sidebar(active: str) -> str:
    out = ['<nav class="side-nav" aria-label="Primary">']
    for group, items in NAV:
        out.append(f'<div class="nav-group"><div class="nav-group-title">{group}</div><ul>')
        for slug, title in items:
            cls = ' class="active" aria-current="page"' if slug == active else ""
            out.append(f'<li><a href="{slug}.html"{cls}>{title}</a></li>')
        out.append("</ul></div>")
    out.append("</nav>")
    return "\n".join(out)


def render_page(slug: str, page: dict) -> str:
    title = page["title"]
    desc = page["desc"]
    md_label = page.get("md_label", "View source on GitHub")
    md_url = page["md_url"]
    body = page["body"]
    toc = page.get("toc", [])
    needs_mermaid = page.get("mermaid", False)
    needs_chart = page.get("chart", False)

    full_title = title if slug == "index" else f"{title} · {SITE_TITLE}"
    canonical = BASE_URL + ("" if slug == "index" else f"{slug}.html")

    head_extra = ""
    if needs_mermaid:
        head_extra += (
            '\n  <script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>'
        )
    if needs_chart:
        head_extra += (
            '\n  <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>'
        )

    # breadcrumb
    group_name = next((g for g, items in NAV for s, _ in items if s == slug), "")
    crumb = (
        f'<a href="index.html">Home</a>'
        if slug == "index"
        else f'<a href="index.html">Home</a> <span class="sep">/</span> '
        f'<span class="crumb-group">{group_name}</span> <span class="sep">/</span> '
        f'<span class="crumb-cur">{title}</span>'
    )

    toc_html = ""
    if toc:
        items = "\n".join(
            f'<li><a href="#{anchor}">{label}</a></li>' for anchor, label in toc
        )
        toc_html = (
            '<aside class="on-this-page" aria-label="On this page">'
            '<div class="otp-title">On this page</div>'
            f"<ul>{items}</ul></aside>"
        )

    sidebar = render_sidebar(slug)

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{full_title}</title>
  <meta name="description" content="{desc}">
  <link rel="canonical" href="{canonical}">
  <meta property="og:type" content="website">
  <meta property="og:title" content="{full_title}">
  <meta property="og:description" content="{desc}">
  <meta property="og:url" content="{canonical}">
  <meta name="twitter:card" content="summary">
  <meta name="theme-color" content="#6d28d9">
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Cdefs%3E%3ClinearGradient id='g' x1='0' y1='0' x2='1' y2='1'%3E%3Cstop offset='0' stop-color='%237c3aed'/%3E%3Cstop offset='1' stop-color='%2306b6d4'/%3E%3C/linearGradient%3E%3C/defs%3E%3Ccircle cx='16' cy='16' r='14' fill='url(%23g)'/%3E%3Ccircle cx='16' cy='16' r='5' fill='white'/%3E%3C/svg%3E">
  <link rel="stylesheet" href="assets/style.css">
  <script>
  /* No-flash theme: runs before paint. */
  (function () {{
    try {{
      var saved = localStorage.getItem('argus-theme');
      var theme = saved || (window.matchMedia &&
        window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
      document.documentElement.setAttribute('data-theme', theme);
    }} catch (e) {{}}
  }})();
  </script>{head_extra}
</head>
<body>
  <a class="skip-link" href="#main">Skip to content</a>

  <header class="topbar">
    <button class="icon-btn hamburger" id="sidebar-toggle" aria-label="Toggle menu" aria-expanded="false">
      <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path fill="currentColor" d="M3 6h18v2H3zm0 5h18v2H3zm0 5h18v2H3z"/></svg>
    </button>
    <a class="brand" href="index.html">
      <span class="brand-eye" aria-hidden="true"></span>
      <span class="brand-name">Argus</span>
      <span class="brand-sub">multi-model code review</span>
    </a>
    <div class="topbar-spacer"></div>
    <a class="topbar-link" href="{REPO}" target="_blank" rel="noopener" aria-label="GitHub repository">
      <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="currentColor" d="M12 1.5a10.5 10.5 0 0 0-3.32 20.47c.52.1.71-.23.71-.5v-1.76c-2.9.63-3.52-1.4-3.52-1.4-.48-1.2-1.16-1.52-1.16-1.52-.95-.65.07-.64.07-.64 1.05.07 1.6 1.08 1.6 1.08.94 1.6 2.45 1.14 3.05.87.1-.68.37-1.14.66-1.4-2.32-.27-4.76-1.16-4.76-5.16 0-1.14.41-2.07 1.07-2.8-.11-.27-.46-1.34.1-2.78 0 0 .87-.28 2.86 1.07a9.9 9.9 0 0 1 5.2 0c1.98-1.35 2.85-1.07 2.85-1.07.57 1.44.21 2.51.11 2.78.67.73 1.07 1.66 1.07 2.8 0 4.01-2.45 4.88-4.78 5.14.38.33.71.97.71 1.96v2.9c0 .28.19.61.72.5A10.5 10.5 0 0 0 12 1.5Z"/></svg>
    </a>
    <button class="icon-btn theme-toggle" id="theme-toggle" aria-label="Toggle dark mode">
      <svg class="ico-sun" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="currentColor" d="M12 17a5 5 0 1 1 0-10 5 5 0 0 1 0 10Zm0-13a1 1 0 0 1 1 1v1a1 1 0 1 1-2 0V5a1 1 0 0 1 1-1Zm0 14a1 1 0 0 1 1 1v1a1 1 0 1 1-2 0v-1a1 1 0 0 1 1-1ZM4 11a1 1 0 0 1 0 2H3a1 1 0 1 1 0-2h1Zm17 0a1 1 0 1 1 0 2h-1a1 1 0 1 1 0-2h1ZM5.6 5.6a1 1 0 0 1 1.4 0l.7.7A1 1 0 0 1 6.3 7.7l-.7-.7a1 1 0 0 1 0-1.4Zm11 11a1 1 0 0 1 1.4 0l.7.7a1 1 0 0 1-1.4 1.4l-.7-.7a1 1 0 0 1 0-1.4Zm1.4-11a1 1 0 0 1 0 1.4l-.7.7a1 1 0 1 1-1.4-1.4l.7-.7a1 1 0 0 1 1.4 0Zm-11 11a1 1 0 0 1 0 1.4l-.7.7a1 1 0 0 1-1.4-1.4l.7-.7a1 1 0 0 1 1.4 0Z"/></svg>
      <svg class="ico-moon" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="currentColor" d="M21 12.8A8.5 8.5 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z"/></svg>
    </button>
  </header>

  <div class="layout">
    <div class="backdrop" id="backdrop" hidden></div>
    <aside class="sidebar" id="sidebar">
      {sidebar}
    </aside>

    <main id="main" class="content">
      <nav class="breadcrumb" aria-label="Breadcrumb">{crumb}</nav>
      <div class="page-head">
        <h1>{title}</h1>
        <a class="md-link" href="{md_url}" target="_blank" rel="noopener" title="Open the source markdown on GitHub">
          <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path fill="currentColor" d="M3 5h18v14H3V5Zm2 2v10h14V7H5Zm2 7V10l2 2 2-2v4h2V9h-2l-2 2-2-2H7v5h2-2Zm10-1 2.5-3H17V8h-2v5h2v0Z"/></svg>
          {md_label}
        </a>
      </div>
      {toc_html}
      <article class="prose">
        {body}
      </article>
      <footer class="page-footer">
        <p>Argus &mdash; {SITE_TAGLINE} &middot; <a href="{REPO}" target="_blank" rel="noopener">GitHub</a> &middot; MIT License &middot; &copy; {YEAR}</p>
        <p class="muted">Named for Argus Panoptes, the hundred-eyed giant. <em>Given enough eyeballs, all bugs are shallow.</em></p>
      </footer>
    </main>
  </div>

  <script src="assets/app.js"></script>
</body>
</html>
"""


def write(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  wrote {os.path.relpath(path, HERE)}  ({len(content)} bytes)")


def build_llms_txt() -> str:
    lines = [
        f"# {SITE_TITLE}",
        "",
        f"> {SITE_TAGLINE} Argus dispatches a git diff / PR / file set to a "
        "configurable roster of frontier LLM reviewers in parallel, filters findings "
        "by confidence with cross-reviewer corroboration, and produces one merged "
        "review. A benchmark mode scores reviewers against labeled fixtures to build a "
        "leaderboard. Named for Argus Panoptes, the hundred-eyed giant: given enough "
        "eyeballs, all bugs are shallow.",
        "",
        "Argus is a Claude Code skill (invoked as /argus) plus a set of standalone "
        "Python scripts. It is configured entirely through config.yaml and environment "
        "variables; API keys live only in the environment and are never written to disk.",
        "",
        "## Docs",
    ]
    for _, items in NAV:
        for slug, title in items:
            page = PAGES[slug]
            url = BASE_URL + ("" if slug == "index" else f"{slug}.html")
            lines.append(f"- [{title}]({url}): {page['desc']}")
    lines += [
        "",
        "## Source",
        f"- [README]({REPO_BLOB}/README.md): full human-facing overview",
        f"- [SKILL.md]({REPO_BLOB}/SKILL.md): the /argus skill definition",
        f"- [config.yaml]({REPO_BLOB}/config.yaml): reviewer registry, profiles, routing, cost gates",
        f"- [CONTRIBUTING]({REPO_BLOB}/CONTRIBUTING.md): contribution guide",
        f"- [DEVELOPMENT]({REPO_BLOB}/DEVELOPMENT.md): developer notes",
        "",
        "## Optional",
        f"- [Repository]({REPO}): GitHub source",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    os.makedirs(ASSETS, exist_ok=True)
    print("Building Argus KB site...")

    write(os.path.join(ASSETS, "style.css"), CSS)
    write(os.path.join(ASSETS, "app.js"), JS)

    for slug in SLUG_TITLE:
        if slug not in PAGES:
            raise SystemExit(f"Missing content for page '{slug}'")
        write(os.path.join(HERE, f"{slug}.html"), render_page(slug, PAGES[slug]))

    # 404 page (not in nav)
    write(os.path.join(HERE, "404.html"), render_page("404", PAGES["404"]))

    write(os.path.join(HERE, ".nojekyll"), "")
    write(os.path.join(HERE, "llms.txt"), build_llms_txt())

    print("Done.")


if __name__ == "__main__":
    main()
