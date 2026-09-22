"""Unit tests for reviewer-name aliasing in scripts/_common.py.

Reviewer keys went version-free on 2026-09-22 (glm-5.2 -> glm). `aliases:` in
config.yaml keeps every previously-valid roster string working. These tests
pin the behaviour that makes that safe:

  - legacy names resolve to the canonical key
  - a real registry key always beats the alias map
  - unknown names pass through (callers own the error message)
  - mixing a legacy name and its canonical key dispatches ONE reviewer, not two
  - the shipped config.yaml is internally consistent

Run: python -m pytest tests/ -q
Or:  python tests/test_aliases.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make scripts/ importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from _common import (  # noqa: E402
    canonical_reviewer,
    canonicalize_roster,
    load_config,
    resolve_roster,
)

# Minimal synthetic config — keeps these tests independent of registry churn.
CFG = {
    "defaults": {"profile": "std"},
    "reviewers": {
        "glm": {"tier": "paid", "privacy": "ok"},
        "kimi": {"tier": "paid", "privacy": "ok"},
        "grok-longctx": {"tier": "paid", "privacy": "ok", "custom_only": True},
    },
    "aliases": {"glm-5.2": "glm", "kimi-k2.6": "kimi", "grok-4.20": "grok-longctx"},
    "profiles": {"std": {"members": ["glm", "kimi"]}},
    "host_rules": {"unknown": {"skip": [], "add": []}},
}


def test_legacy_name_resolves_to_canonical():
    assert canonical_reviewer(CFG, "glm-5.2") == "glm"
    assert canonical_reviewer(CFG, "kimi-k2.6") == "kimi"


def test_canonical_name_is_identity():
    assert canonical_reviewer(CFG, "glm") == "glm"


def test_registry_key_beats_alias_map():
    """A name that IS a registry key must never be rewritten by the alias map.

    This lets a future reviewer reuse a retired name without the stale alias
    silently hijacking it.
    """
    cfg = dict(CFG, reviewers={**CFG["reviewers"], "glm-5.2": {"tier": "paid"}})
    assert canonical_reviewer(cfg, "glm-5.2") == "glm-5.2"


def test_unknown_name_passes_through():
    # Callers own the "not in registry" error, so the message names what the
    # user actually typed rather than a mangled version of it.
    assert canonical_reviewer(CFG, "nope") == "nope"


def test_roster_dedupes_alias_and_canonical():
    """glm-5.2 + glm is ONE reviewer.

    Dispatching it twice would make it a self-corroborating voter in merge.py
    and let its solo findings clear the confidence threshold on their own.
    """
    assert canonicalize_roster(CFG, ["glm-5.2", "glm", "kimi"]) == ["glm", "kimi"]


def test_roster_preserves_order():
    assert canonicalize_roster(CFG, ["kimi-k2.6", "glm-5.2"]) == ["kimi", "glm"]


def test_resolve_roster_accepts_legacy_custom_names():
    roster, drops = resolve_roster(
        CFG, "custom", ["glm-5.2", "kimi-k2.6"], "unknown", explicit=True
    )
    assert roster == ["glm", "kimi"]
    assert drops == []


def test_resolve_roster_legacy_name_waives_custom_only_when_explicit():
    """--custom "grok-4.20" must still reach the custom_only reviewer.

    The custom_only gate compares canonical keys, so aliasing has to happen
    before the gate runs or an explicitly-named legacy reviewer gets dropped.
    """
    roster, _ = resolve_roster(
        CFG, "custom", ["grok-4.20"], "unknown", explicit=True
    )
    assert roster == ["grok-longctx"]


def test_host_rules_skip_matches_canonical_key():
    cfg = dict(CFG, host_rules={"claude": {"skip": ["glm"], "add": []}})
    roster, drops = resolve_roster(cfg, "custom", ["glm-5.2", "kimi"], "claude",
                                   explicit=True)
    assert roster == ["kimi"]
    assert [n for n, _ in drops] == ["glm"]


# ── Shipped-config integrity ────────────────────────────────────────────

def test_shipped_config_aliases_and_profiles_resolve():
    cfg = load_config()
    reviewers = cfg["reviewers"]
    for old, new in cfg.get("aliases", {}).items():
        assert old not in reviewers, f"alias {old!r} shadows a real reviewer"
        assert new in reviewers, f"alias {old!r} -> unknown reviewer {new!r}"
    for pname, prof in cfg["profiles"].items():
        for member in prof["members"]:
            assert member in reviewers, f"profile {pname!r}: unknown member {member!r}"


def test_shipped_config_routes_are_wired():
    """Every declared route points at a real CLI command / aichat client."""
    cfg = load_config()
    clients = set(cfg["aichat_clients"])
    commands = set(cfg["cli_commands"])
    for name, spec in cfg["reviewers"].items():
        for slot in ("primary", "fallback"):
            route = spec.get(slot)
            if not route:
                continue
            assert route["route"] in commands, f"{name}.{slot}: bad route"
            if route["route"] == "aichat":
                assert route.get("client") in clients, f"{name}.{slot}: bad client"


def test_bench_cost_prices_legacy_reviewer_names():
    """Historical benchmark artifacts must still price correctly.

    Regression: bench_cost.py reads reviewer names from benchmark artifacts on
    disk, which is the one path that never goes through resolve_roster. A
    pre-rename run carries `glm-5.2`; a direct registry lookup missed, rates
    came back None, and the row printed as a $0 "paid CLI sub" — silently
    understating what the run cost.
    """
    from bench_cost import rates_for
    cfg = load_config()
    for legacy in ("glm-5.2", "kimi-k2.6", "qwen-3.6-plus"):
        canonical, rates, status = rates_for(cfg, legacy)
        # 'estimated' (not 'cli-sub'): the alias resolved and the reviewer is
        # metered. Whether the price is exact is a separate axis, covered by
        # test_bench_cost_prefers_rates_recorded_in_the_artifact.
        assert status == "estimated", f"{legacy} priced as {status}"
        assert rates and rates["input"] > 0, f"{legacy} resolved to no rates"


def test_bench_cost_columns_fit_the_widest_alias_label():
    """The cost table must size its columns to the data, not a fixed width.

    Regression: rows are labelled `recorded->canonical`, and
    `opencode-minimax-m3->opencode-minimax` is 36 chars against a hard-coded
    18-wide field. Python pads but never truncates, so five of the eleven
    aliases shoved every column to their right out of alignment — visible only
    on exactly the historical artifacts the alias fix was written for.
    """
    cfg = load_config()
    widest = max(len(f"{old}\u2192{new}") for old, new in cfg["aliases"].items())
    src = (Path(__file__).resolve().parent.parent
           / "scripts" / "bench_cost.py").read_text(encoding="utf-8")
    assert "{name_w}" in src and "len(r[\"reviewer\"]) for r in rows" in src, (
        "bench_cost.py must derive its reviewer column width from the rows; a "
        f"fixed width fails on the widest alias label ({widest} chars)"
    )
    # And the notes column too — it was truncating "paid CLI sub (no per-token
    # cost)" to "paid CLI sub (".
    assert "{note_w}" in src and "note[:14]" not in src


def test_bench_cost_prefers_rates_recorded_in_the_artifact():
    """A historical run must be priced at what it was billed, not today's rate.

    Regression: resolving a legacy name to the current registry fixed the $0
    under-report but introduced a different wrong number. `qwen-3.6-plus` ran
    at $0.50/$2.00; today's `qwen` is qwen3.8-max at $2.00/$6.00, so pricing
    the old run at the new rate overstates it ~3.2x. Rates recorded in the
    artifact take precedence.
    """
    from bench_cost import rates_for
    cfg = load_config()
    recorded = {"input": 0.50, "output": 2.00}
    canonical, rates, status = rates_for(cfg, "qwen-3.6-plus", recorded)
    assert canonical == "qwen"
    assert rates == recorded, "recorded rates must win over the current registry"
    assert status == "recorded"


def test_bench_cost_marks_unrecorded_rates_as_estimated():
    """Same arithmetic, weaker claim — and it must say so.

    Artifacts written before rate snapshotting cannot be costed exactly. They
    still get a number, but it must be distinguishable from an exact one so a
    total is never quoted as actual spend when it is a present-day estimate.
    """
    from bench_cost import rates_for
    cfg = load_config()
    _, rates, status = rates_for(cfg, "qwen-3.6-plus", None)
    assert status == "estimated", "unrecorded rates must not claim to be actuals"
    assert rates  # still priced, just not claimed as exact


def test_benchmark_snapshots_rates_into_new_artifacts():
    """Going forward, artifacts must carry the rates they ran under."""
    src = (Path(__file__).resolve().parent.parent
           / "scripts" / "benchmark.py").read_text(encoding="utf-8")
    assert '"rates": spec.get("cost_per_m")' in src, (
        "benchmark.py must record cost_per_m in each per-reviewer artifact so "
        "future cost reports do not depend on a registry that has since moved"
    )


def test_bench_cost_flags_cli_sub_that_fell_back_to_a_metered_route():
    """A CLI sub that fell back to OpenRouter did not cost $0.

    Regression: the artifact snapshot records the reviewer-level cost_per_m,
    which is null for CLI-sub reviewers. But `_dispatch` falls back from a
    failed CLI to the metered OpenRouter route, spending real money that
    config.yaml has no price for. Reporting that run as a $0 "paid CLI sub"
    under-reports spend exactly the way the original null-rate lookup did.
    """
    from bench_cost import rates_for
    cfg = load_config()
    _, _, status = rates_for(cfg, "codex", None, fallback_calls=2)
    assert status == "mixed", "metered fallback on a CLI sub must not read as $0"
    # No fallback: genuinely free, and must still say so.
    _, _, clean = rates_for(cfg, "codex", None, fallback_calls=0)
    assert clean == "cli-sub"


def test_fallback_outranks_the_rate_source():
    """A recorded rate must not label a fallback call exact.

    Regression: `rates_for` returned 'recorded' before checking
    fallback_calls, so a metered reviewer that fell back had those calls
    billed at the PRIMARY's rate and marked exact. `kimi` is the live case:
    primary kimi-k3 at $3/$15, fallback kimi-k2.7-code at $0.71/$3.21 — a
    price config.yaml does not carry, because it stores one rate per
    reviewer. The earlier fix only guarded the cli-sub path.
    """
    from bench_cost import rates_for
    cfg = load_config()
    recorded = {"input": 3.00, "output": 15.00}
    _, rates, status = rates_for(cfg, "kimi", recorded, fallback_calls=2)
    assert status == "mixed", (
        "a metered reviewer that fell back must not claim 'recorded'"
    )
    # Rates still come back so the caller can price the primary-served calls;
    # only the fallback ones are unpriceable.
    assert rates == recorded

    # Without a fallback, the recorded rate is exact and should say so.
    assert rates_for(cfg, "kimi", recorded, fallback_calls=0)[2] == "recorded"


def test_bench_cost_trusts_recorded_rates_for_reviewers_removed_from_registry():
    """A reviewer deleted from config.yaml is still priceable from its artifact.

    Regression: reordering rates_for put the `spec is None` short-circuit
    ahead of the recorded branch, so a deleted reviewer whose artifact carried
    exact rates read as 'unknown', priced $0 and forced exit 1 — discarding
    the very number rate-snapshotting exists to preserve. 'unknown' must mean
    unpriceable, not merely absent from the current registry.
    """
    from bench_cost import rates_for
    cfg = load_config()
    recorded = {"input": 0.50, "output": 2.00}
    canonical, rates, status = rates_for(cfg, "retired-reviewer", recorded)
    assert status == "recorded", f"deleted reviewer priced as {status}"
    assert rates == recorded

    # Absent from the registry AND no recorded rates is genuinely unpriceable.
    assert rates_for(cfg, "retired-reviewer", None)[2] == "unknown"


def test_bench_cost_uses_one_source_for_the_fallback_count():
    """Status and printed note must come from the same fallback count.

    Regression: the status was decided from the artifact's `fallback_calls`
    total while the note printed a locally recomputed figure. They agreed in
    the steady state, but nothing kept them in step — so a corrupted artifact
    or a change to what benchmark.py counts would have the two disagree
    silently.
    """
    src = (Path(__file__).resolve().parent.parent
           / "scripts" / "bench_cost.py").read_text(encoding="utf-8")
    assert "rates_for(cfg, name, data.get(\"rates\"), fb_calls)" in src, (
        "rates_for must be called with the locally computed fb_calls, the same "
        "count used for the printed note"
    )
    assert 'int(data.get("fallback_calls") or 0)' not in src, (
        "the artifact's fallback_calls must not be a second source for the "
        "status decision"
    )


def test_bench_cost_does_not_call_a_counted_row_excluded():
    """A partially priced row is in the TOTAL, so it is not 'excluded'.

    Regression: a `mixed` row in the priced branch set `unpriced=True` while
    its cost was still added to the total, so the run announced
    "could not be priced, excluded from the total: kimi" about a row whose
    cost was in that very total. The arithmetic was right; the sentence was
    not.
    """
    src = (Path(__file__).resolve().parent.parent
           / "scripts" / "bench_cost.py").read_text(encoding="utf-8")
    # The priced branch flags rows as partial, never as unpriced.
    priced_branch = src[src.index("if rates:"):src.index("else:", src.index("if rates:"))]
    assert '"partial": status == "mixed"' in priced_branch
    assert '"unpriced"' not in priced_branch, (
        "a row whose cost is added to the total must not be flagged unpriced"
    )
    assert "partially priced" in src


def test_a_lower_bound_total_always_fails_the_run():
    """If any spend is missing from the TOTAL, the run must exit non-zero.

    Regression: splitting `unpriced` into `partial` (row counted, some calls
    unpriced) and `unpriced` (row excluded entirely) fixed the wording but
    left the exit status keyed off `unpriced` alone. A partially priced run
    then printed "the TOTAL is a LOWER BOUND" and exited 0 — and the exit
    code is the only part of that sentence automation reads.

    The two flags differ in HOW MUCH is missing, not in WHETHER anything is,
    so both must fail the run.
    """
    src = (Path(__file__).resolve().parent.parent
           / "scripts" / "bench_cost.py").read_text(encoding="utf-8")
    assert "if unpriced or partial:" in src, (
        "the exit status must account for partially priced rows, not just "
        "fully excluded ones"
    )
    # And the failing branch is the one that returns 1.
    tail = src[src.index("if unpriced or partial:"):]
    assert "return 1" in tail.split("return 0")[0]


def test_rates_for_docstring_lists_every_status_it_returns():
    """The documented contract must match the values callers can receive."""
    import bench_cost
    doc = bench_cost.rates_for.__doc__ or ""
    for status in ("recorded", "estimated", "mixed", "cli-sub", "unknown"):
        assert f"'{status}'" in doc, f"status {status!r} missing from docstring"
    assert "'metered'" not in doc, "docstring still lists the removed 'metered' status"


def test_bench_cost_separates_unknown_from_free_cli():
    """$0 for a CLI sub and $0 for an unpriceable name must not look alike.

    Both cost nothing in the report, but the first is a real price and the
    second is a missing one. Collapsing them is how a reviewer disappears into
    a total that reads as complete.
    """
    from bench_cost import rates_for
    cfg = load_config()
    assert rates_for(cfg, "codex")[2] == "cli-sub"
    assert rates_for(cfg, "no-such-reviewer-anywhere")[2] == "unknown"


# Reviewer names as recorded in this repo's reference benchmark (README.md
# "Reference benchmark" table and docs/benchmarks.html). These are the
# historical artifact names bench_cost.py must still be able to price.
DOCUMENTED_HISTORICAL_NAMES = [
    "opencode", "qwen-3.6-plus", "glm-5.1", "gemini-or", "minimax-m2.7",
    "mimo-v2-pro", "codex", "deepseek-v3.2", "grok-4.20", "hermes-4.3",
    "kimi-k2.6",
]


def test_every_documented_historical_name_is_priceable():
    """The repo's own documented benchmark must still cost cleanly.

    Regression: `glm-5.1` and `minimax-m2.7` appear in the reference
    leaderboard but had no aliases, so bench_cost.py marked them `unknown`,
    dropped them from the total, and — once unknown names became fatal —
    exited 1. The historical-compatibility promise has to cover at minimum
    the artifacts this repository documents.

    'estimated' is the expected status for most of these: the run predates
    rate snapshotting, so it is priced at current rates and labelled as an
    estimate. What must never happen is 'unknown'.
    """
    from bench_cost import rates_for
    cfg = load_config()
    unknown = [n for n in DOCUMENTED_HISTORICAL_NAMES
               if rates_for(cfg, n)[2] == "unknown"]
    assert not unknown, (
        "documented benchmark reviewers cannot be priced (no alias, not in "
        f"registry): {unknown}"
    )


# Files that state what the 2026-09-22 catalog check covered. The claim is
# only true of OpenRouter-routed pins; direct-provider and CLI-provider slugs
# are invisible to that API.
CATALOG_CLAIM_FILES = [
    "config.yaml", "README.md", "CLAUDE.md",
    "docs/build_content.py", "docs/reviewers.html",
]


def test_catalog_validation_claim_is_scoped_everywhere():
    """No file may claim the catalog check covered every pin.

    Regression: the claim was scoped in config.yaml but left blanket in
    CLAUDE.md, README.md and the docs generator — three copies of a
    validation guarantee the project cannot make. `opencode-glm` is the
    standing counter-example: deliberately unbumped *because* its catalog
    is not visible from the OpenRouter API.
    """
    import re
    root = Path(__file__).resolve().parent.parent
    unscoped = []
    for rel in CATALOG_CLAIM_FILES:
        f = root / rel
        if not f.exists():
            continue
        text = re.sub(r"\s+", " ", f.read_text(encoding="utf-8"))
        idx = text.find("were verified against")
        if idx < 0:
            continue
        window = text[max(0, idx - 120):idx]
        if not re.search(r"OpenRouter-routed|OPENROUTER-ROUTED|client: openrouter",
                         window, re.I):
            unscoped.append(rel)
    assert not unscoped, (
        "catalog-validation claim is not scoped to OpenRouter-routed pins in: "
        f"{unscoped}"
    )


def test_stats_canonicalizes_history_reviewer_names():
    """history.db rows written before the rename must merge with new ones.

    Regression: stats.py grouped `reviewer_runs` by the raw stored name and
    keyed benchmark metrics the same way, so a reviewer that ran as `glm-5.2`
    before 2026-09-22 and `glm` after appeared as two reviewers, and the old
    benchmark F1 never attached to the canonical name. That is precisely the
    history continuity the alias map exists to preserve.

    This was the fourth reader of reviewer names outside `resolve_roster`,
    and the one an earlier sweep missed because it reads the DB rather than
    `cfg["reviewers"]`.
    """
    src = (Path(__file__).resolve().parent.parent
           / "scripts" / "stats.py").read_text(encoding="utf-8")
    assert "canonical_reviewer" in src, (
        "stats.py must canonicalize names read from history.db"
    )
    # Averages must be re-derived from run-weighted totals, not averaged again.
    assert "lat_total" in src and "m[\"runs\"]" in src, (
        "merged rows must recompute averages from totals, not average averages"
    )


def test_no_unattributed_benchmark_claims_on_unbenchmarked_models():
    """A measurement must name the model it measured.

    Regression: the `gemini-or` row carried "~2s/call, best value" from the
    2.5-Flash benchmark after the entry was repointed at 3.8 Flash, which
    this PR never benchmarked — presenting one model's numbers as another's
    properties, in three places plus the generated page.
    """
    import re
    root = Path(__file__).resolve().parent.parent
    offenders = []
    for rel in ("README.md", "config.yaml", "docs/build_content.py",
                "docs/reviewers.html"):
        f = root / rel
        if not f.exists():
            continue
        text = re.sub(r"\s+", " ", f.read_text(encoding="utf-8"))
        for m in re.finditer(r"best value", text):
            window = text[max(0, m.start() - 260):m.start() + 60]
            # Acceptable only when the window says which model it measured.
            if not re.search(r"2\.5(&nbsp;|\s)?Flash|2\.5-flash", window, re.I):
                offenders.append(rel)
    assert not offenders, (
        f"unattributed benchmark claim on an unbenchmarked model in: {offenders}"
    )


def _stats_rows(tmp_path, monkeypatch, capsys, rows):
    """Seed a throwaway history.db and return stats.py's ACTUAL output rows.

    Runs stats.main() in-process with HISTORY_DB redirected, so the assertions
    exercise the real data path — seeded row -> bench_raw -> bench -> rows ->
    json.dumps — rather than the source text. stats.py imports HISTORY_DB by
    value, so both it and _common (whose history_conn reads the module global)
    have to be patched.
    """
    import json as _json
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import _common
    import stats

    db = tmp_path / "history.db"
    monkeypatch.setattr(_common, "HISTORY_DB", db)
    monkeypatch.setattr(stats, "HISTORY_DB", db)

    conn = _common.history_conn()
    conn.execute("INSERT INTO runs (run_id, ts, roster) "
                 "VALUES ('r1','2026-06-01T00:00:00+00:00','x')")
    for reviewer, model in rows:
        conn.execute(
            "INSERT INTO reviewer_runs (run_id,reviewer,latency_sec,n_findings,"
            "fallback_used,exit_code) VALUES ('r1',?,1.0,1,0,0)", (reviewer,))
        conn.execute(
            'INSERT INTO benchmarks (ts,reviewer,fixture,run_idx,"precision",'
            'recall,f1,model) VALUES (?,?,?,?,?,?,?,?)',
            ("20260601T000000", reviewer, "f", 0, 0.736, 0.639, 0.681, model))
    conn.commit()
    conn.close()

    monkeypatch.setattr(_sys, "argv", ["stats.py", "--format", "json"])
    assert stats.main() == 0
    return _json.loads(capsys.readouterr().out)


def test_stats_flags_scores_measured_on_a_model_the_reviewer_no_longer_runs(
        tmp_path, monkeypatch, capsys):
    """A stable KEY can hide a changed MODEL, and that must still be visible.

    Regression: `merged_from` only fires when two raw names canonicalize to
    one key (`glm-5.2` -> `glm`). `gemini-or` kept its name across this PR
    while its slug moved `google/gemini-2.5-flash` -> `google/gemini-3.8-flash`,
    so nothing fired and its 2.5-Flash F1 printed under a 3.8-Flash reviewer —
    programmatically reproducing the misattribution four documentation edits
    in the same commit were written to prevent.

    This asserts on the emitted JSON, not on stats.py's source: an earlier
    version of this test checked for substrings and would have passed even if
    `bench_stale_models` were computed and never plumbed into the row.
    """
    rows = _stats_rows(tmp_path, monkeypatch, capsys,
                       [("gemini-or", "google/gemini-2.5-flash")])
    row = next(r for r in rows if r["reviewer"] == "gemini-or")
    assert row["bench_stale_models"] == ["google/gemini-2.5-flash"], (
        "a score measured on a model the reviewer no longer runs must name "
        f"that model in the emitted row; got {row!r}"
    )
    assert row["bench_model_unverified"] is False
    # The score itself is still reported — flagged, not hidden.
    assert row["bench_f1"] == 0.681


def test_stats_does_not_flag_a_reviewer_still_on_its_measured_model(
        tmp_path, monkeypatch, capsys):
    """The marker must stay off when nothing moved, or it becomes noise."""
    rows = _stats_rows(tmp_path, monkeypatch, capsys,
                       [("mimo", "xiaomi/mimo-v2.6-pro")])
    row = next(r for r in rows if r["reviewer"] == "mimo")
    assert row["bench_stale_models"] is None
    assert row["bench_model_unverified"] is False


def test_stats_does_not_flag_cli_reviewers_that_have_no_model(
        tmp_path, monkeypatch, capsys):
    """A CLI reviewer has no slug, so a NULL model is accurate, not missing."""
    rows = _stats_rows(tmp_path, monkeypatch, capsys, [("opencode", None)])
    row = next(r for r in rows if r["reviewer"] == "opencode")
    assert row["bench_model_unverified"] is False, (
        "flagging every CLI reviewer forever would train readers to ignore "
        "the marker"
    )
    assert row["bench_stale_models"] is None


def test_stats_merges_legacy_names_and_weights_averages_by_runs(
        tmp_path, monkeypatch, capsys):
    """Pre- and post-rename rows are one reviewer, averaged by run count."""
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import _common, stats, json as _json

    db = tmp_path / "history.db"
    monkeypatch.setattr(_common, "HISTORY_DB", db)
    monkeypatch.setattr(stats, "HISTORY_DB", db)
    conn = _common.history_conn()
    # reviewer_runs is PRIMARY KEY (run_id, reviewer) — one row per reviewer
    # per run — so three runs means three run_ids, not three rows on one.
    for i in range(3):
        conn.execute("INSERT INTO runs (run_id, ts, roster) VALUES (?,?,?)",
                     (f"old{i}", "2026-06-01T00:00:00+00:00", "glm-5.2"))
        conn.execute("INSERT INTO reviewer_runs (run_id,reviewer,latency_sec,"
                     "n_findings,fallback_used,exit_code) "
                     "VALUES (?,'glm-5.2',30.0,5,0,0)", (f"old{i}",))
    conn.execute("INSERT INTO runs (run_id, ts, roster) "
                 "VALUES ('new0','2026-09-22T00:00:00+00:00','glm')")
    conn.execute("INSERT INTO reviewer_runs (run_id,reviewer,latency_sec,"
                 "n_findings,fallback_used,exit_code) "
                 "VALUES ('new0','glm',10.0,1,0,0)")
    conn.commit(); conn.close()

    monkeypatch.setattr(_sys, "argv", ["stats.py", "--format", "json"])
    assert stats.main() == 0
    rows = _json.loads(capsys.readouterr().out)
    assert [r["reviewer"] for r in rows] == ["glm"], "legacy rows must merge"
    row = rows[0]
    assert row["runs"] == 4
    # Run-weighted: (30*3 + 10*1)/4 = 25. Averaging the averages gives 20.
    assert row["avg_latency_sec"] == 25.0, (
        "averages must be re-derived from run-weighted totals, not averaged"
    )
    assert row["merged_from"] == ["glm-5.2"]


_MISSING = object()


def test_benchmarks_table_records_the_model_measured(tmp_path, monkeypatch):
    """The writer must persist the model per run — and NULL when none served.

    Behavioural, not a source grep: staleness reporting is only as good as
    what actually lands in the column. Two rows go in — one served, one
    wall-capped — and the assertion is on the stored values.

    Regression: the writer fell back to the reviewer-level primary slug when
    a run recorded no model, so a wall-capped or crashed run (which served
    nothing and scores zero) was filed in history as a measurement of a model
    that never ran.
    """
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import _common
    import benchmark

    db = tmp_path / "history.db"
    monkeypatch.setattr(_common, "HISTORY_DB", db)
    monkeypatch.setattr(benchmark, "history_conn", _common.history_conn)

    def _row(idx, model, exit_code):
        r = {"run_idx": idx, "precision": 0.0, "recall": 0.0, "f1": 0.0,
             "n_findings": 0, "latency_sec": 0.0, "error": None,
             "exit_code": exit_code}
        if model is not _MISSING:
            r["model"] = model
        return r

    benchmark._write_history([{
        "reviewer": "glm",
        "model": "vendor/reviewer-level-snapshot",
        "fixtures": [{"fixture": "f", "runs": [
            _row(0, "vendor/served", 0),      # a real call
            _row(1, None, 137),               # wall-capped: nothing served
            _row(2, _MISSING, 1),             # older row shape: no key at all
        ]}],
    }], "20260601T000000")

    import sqlite3 as _sqlite3
    stored = dict(_sqlite3.connect(db).execute(
        "SELECT run_idx, model FROM benchmarks ORDER BY run_idx").fetchall())
    assert stored[0] == "vendor/served"
    assert stored[1] is None, (
        "a wall-capped run served no model; filing it under the reviewer's "
        f"primary makes a zero score look like a measurement (got {stored[1]!r})"
    )
    assert stored[2] is None


def test_history_schema_declares_the_model_column_and_its_migration():
    """The column must exist on a NEW database and be added to an OLD one."""
    common = (Path(__file__).resolve().parent.parent
              / "scripts" / "_common.py").read_text(encoding="utf-8")
    assert "model TEXT" in common, "benchmarks table needs a model column"
    assert "ALTER TABLE benchmarks ADD COLUMN model" in common, (
        "CREATE TABLE IF NOT EXISTS is a no-op on an existing database, so the "
        "new column needs an explicit migration"
    )


def test_stats_does_not_flag_a_cli_run_that_correctly_recorded_no_model(
        tmp_path, monkeypatch, capsys):
    """A model-less route makes NULL a CURRENT record, not a missing one.

    Regression: the unverified (`?`) marker fired whenever a NULL row belonged
    to a reviewer with any modelled route. `codex` and `gemini` have a
    model-less CLI primary alongside a modelled OpenRouter fallback, so a
    successful CLI benchmark records NULL correctly — and was flagged as
    predating model recording on the run that produced it.
    """
    cfg = load_config()
    spec = cfg["reviewers"]["codex"]
    # Guard the premise: CLI primary with no slug, modelled fallback.
    assert not (spec.get("primary") or {}).get("model")
    assert (spec.get("fallback") or {}).get("model")

    rows = _stats_rows(tmp_path, monkeypatch, capsys, [("codex", None)])
    row = next(r for r in rows if r["reviewer"] == "codex")
    assert row["bench_model_unverified"] is False, (
        "a CLI reviewer's successful run records no model slug because its "
        "route has none; that is current, not unverified"
    )


def test_docs_registry_table_lists_every_reviewer():
    """The generated reviewer table must cover the whole registry.

    Regression: the docs page advertised a reviewer count taken from
    config.yaml while its table still omitted `opencode-minimax` and
    `opencode-glm`, so the generated reference contradicted itself. Adding a
    reviewer without a table row is the easy way to reintroduce that.
    """
    import re
    cfg = load_config()
    src = (Path(__file__).resolve().parent.parent
           / "docs" / "build_content.py").read_text(encoding="utf-8")
    start = src.index("<thead><tr><th>Reviewer</th><th>Route(s)</th>")
    table = src[start:src.index("</tbody>", start)]
    listed = set(re.findall(r"<tr><td><code>([a-z0-9.\-]+)</code>", table))
    missing = sorted(set(cfg["reviewers"]) - listed)
    assert not missing, f"reviewers absent from the docs registry table: {missing}"


def test_grok_legacy_alias_preserves_the_2m_window():
    """grok-4.20 must NOT map to `grok` (Grok 4.7, 500K ctx).

    The old key named the 2M-context model specifically; remapping it to the
    newer-but-smaller flagship would silently shrink an existing roster's
    context window, which is the one thing that reviewer exists to provide.
    """
    cfg = load_config()
    target = cfg["aliases"]["grok-4.20"]
    assert cfg["reviewers"][target]["ctx"] == 2_000_000


# Aliases whose LEGACY reviewer was already custom_only before the version-free
# rename. For these, resolving to a custom_only target preserves the old
# behaviour rather than regressing it, so they're exempt from the check below.
ALREADY_CUSTOM_ONLY = {
    "hermes-4.3", "opencode-minimax-m3", "opencode-glm-5.2", "copilot-gpt5",
}


def test_alias_does_not_newly_gate_a_previously_open_reviewer():
    """An alias must not turn a formerly profile-eligible reviewer custom_only.

    Regression: `grok-4.20` was a normal reviewer before the rename, and its
    alias target `grok-longctx` was briefly marked `custom_only`. Profile
    resolution is non-explicit, so a saved profile (--save-as) holding the
    legacy name resolved the alias and *then* had the reviewer dropped by the
    custom_only gate — silently losing it while advertising backward
    compatibility.

    Aliases in ALREADY_CUSTOM_ONLY are exempt: their legacy reviewers carried
    the same gate, so nothing changed for them.
    """
    cfg = load_config()
    trapped = [
        f"{old} -> {new}"
        for old, new in cfg.get("aliases", {}).items()
        if old not in ALREADY_CUSTOM_ONLY
        and cfg["reviewers"][new].get("custom_only")
    ]
    assert not trapped, (
        "alias newly gates a reviewer behind custom_only, so a saved profile "
        f"using the legacy name silently loses it: {trapped}"
    )


def test_saved_profile_with_legacy_names_keeps_every_reviewer():
    """End-to-end guard for the same regression, via resolve_roster."""
    cfg = load_config()
    cfg = dict(cfg, profiles={**cfg["profiles"],
                              "_saved": {"members": ["glm-5.2", "grok-4.20"]}})
    roster, drops = resolve_roster(cfg, "profile", ["_saved"], "unknown")
    assert roster == ["glm", "grok-longctx"], f"roster={roster} drops={drops}"
    assert drops == []


def test_verify_fails_when_a_name_was_never_verified():
    """An unknown reviewer must fail the run, not merely warn.

    Regression: filtering unknown names out left an all-unknown roster with
    `results == []`, and `any([])` is False — so the exit status was 0 after
    verifying nothing. A caller gating on that exit code (CI, a wrapper
    script) would read it as "all routes reachable", which is the same
    silent-success trap the filter was added to close, one level up.
    """
    source = (Path(__file__).resolve().parent.parent
              / "scripts" / "verify.py").read_text(encoding="utf-8")
    assert 'return 1 if unknown or any(not r["ok"] for r in results) else 0' in source, (
        "verify.py exit status must account for unknown names, not just "
        "failed pings"
    )


def test_verify_canonicalizes_every_roster_source():
    """verify.py must alias profile members too, not just --roster.

    Regression: the --profile branch passed members straight to a
    `if n in reviewers` filter, so a saved profile holding legacy names
    verified *nothing* and still reported success — the same silent-omission
    failure mode that hid a delisted model slug.
    """
    import verify  # noqa: F401  (import guard: module must load cleanly)
    source = (Path(__file__).resolve().parent.parent
              / "scripts" / "verify.py").read_text(encoding="utf-8")
    # Canonicalization must happen after the branch chain, not inside one arm.
    assert "roster = canonicalize_roster(cfg, roster)" in source
    # And unknown names must be reported, never dropped in silence.
    assert "FAIL: not in registry, not verified" in source


def test_stats_does_not_flag_a_score_served_by_the_fallback_route(
        tmp_path, monkeypatch, capsys):
    """A dual-route reviewer has TWO current models, and either may serve.

    Regression: `_current_model` returned the declared primary only. But
    `route_preference` decides which of a dual-route reviewer's models is
    tried first, and a primary failure serves the other one — so under the
    default OpenRouter preference a fresh `glm` run records the OpenRouter
    slug while the declared primary is the z.ai one. stats.py then marked the
    run stale on the very pass that produced it, which is the false positive
    that makes a real staleness marker unreadable.
    """
    cfg = load_config()
    spec = cfg["reviewers"]["glm"]
    fallback_model = spec["fallback"]["model"]
    # Guard the premise: this test is only meaningful while the two routes
    # name different slugs.
    assert fallback_model != spec["primary"]["model"]

    rows = _stats_rows(tmp_path, monkeypatch, capsys, [("glm", fallback_model)])
    row = next(r for r in rows if r["reviewer"] == "glm")
    assert row["bench_stale_models"] is None, (
        "a score served by the reviewer's own fallback route is current, not "
        f"stale; got {row['bench_stale_models']!r}"
    )


def test_history_conn_survives_a_concurrent_migrator(tmp_path, monkeypatch):
    """Two processes opening an un-migrated DB must both keep their writes.

    Regression: check-then-ALTER raced. The documented protocol runs one shell
    per reviewer, so on the first open of an existing database both can see
    the `model` column missing; one ALTERs and the other died with
    `duplicate column name: model`, losing that reviewer's history write.
    """
    import sqlite3 as _sqlite3
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import _common

    db = tmp_path / "history.db"
    monkeypatch.setattr(_common, "HISTORY_DB", db)

    # Build a pre-migration database: the initial schema, minus the column
    # the migration adds. This is the shape a real user's history.db has.
    pre = _common.HISTORY_SCHEMA.replace("    model TEXT,\n", "")
    assert pre != _common.HISTORY_SCHEMA, "schema no longer declares model"
    seed = _sqlite3.connect(db)
    seed.executescript(pre)
    seed.commit()
    seed.close()

    # Simulate the loser of the race: another process commits the ALTER
    # between this connection's inspection (which saw the column missing) and
    # its own ALTER. sqlite3's C Connection type is immutable, so the hook
    # goes in via a connection subclass rather than a patched method.
    raced = {"done": False}

    class _RacingConnection(_sqlite3.Connection):
        def execute(self, sql, *a, **kw):
            if not raced["done"] and sql.startswith("ALTER TABLE benchmarks"):
                # The other process commits the same ALTER first; ours then
                # runs into `duplicate column name: model`, which is exactly
                # what killed the losing process before the fix.
                raced["done"] = True
                other = _sqlite3.connect(db)
                other.execute(sql)
                other.commit()
                other.close()
            return super().execute(sql, *a, **kw)

    real_connect = _sqlite3.connect
    monkeypatch.setattr(
        _common.sqlite3, "connect",
        lambda *a, **kw: real_connect(*a, **{**kw, "factory": _RacingConnection}))

    conn = _common.history_conn()          # must not raise
    monkeypatch.undo()
    cols = {r[1] for r in real_connect(db).execute("PRAGMA table_info(benchmarks)")}
    conn.close()
    assert raced["done"], "the race was never triggered; test proves nothing"
    assert "model" in cols


def test_benchmark_records_the_model_that_actually_served_each_run():
    """A fallback-served score must not be filed under the model that failed.

    Regression: benchmark.py snapshotted the resolved PRIMARY model once per
    reviewer and wrote it to every history row, including runs where
    `fallback_used` was true. The new stale-model reporting then named the
    slug that errored as the one that produced the number.
    """
    import asyncio
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import benchmark

    primary = {"route": "primary_route", "model": "vendor/failing"}
    fallback = {"route": "fallback_route", "model": "vendor/serving"}

    class _Adapter:
        def __init__(self, exit_code, stdout):
            self.exit_code, self.stdout = exit_code, stdout

        async def send(self, prompt, route, timeout):
            return {"exit_code": self.exit_code, "stdout": self.stdout,
                    "stderr": "boom", "latency_sec": 1.0}

    ok = '{"findings": []}'
    adapters = {"primary_route": _Adapter(1, ""),
                "fallback_route": _Adapter(0, ok)}
    orig = benchmark.adapters
    benchmark.adapters = adapters
    try:
        d = asyncio.run(benchmark._dispatch(
            "glm", {"primary": primary, "fallback": fallback}, "p", 5))
    finally:
        benchmark.adapters = orig

    assert d["fallback_used"] is True
    assert d["model"] == "vendor/serving", (
        "the run must record the route that served it, not the one that "
        f"failed; got {d['model']!r}"
    )


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
