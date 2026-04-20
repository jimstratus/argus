# Argus — project context for Claude

> Multi-model code review skill. Dispatches a diff to a configurable roster of
> frontier LLM reviewers (GLM-5.1, MiniMax M2.7, Kimi K2, MiMo-V2-Pro,
> Qwen3.6-Plus, Grok 4.20, DeepSeek V3.2, Hermes 4.3, Gemini CLI, Codex CLI,
> Claude CLI, OpenCode CLI, GitHub Copilot CLI), runs them in parallel, filters
> by confidence with cross-reviewer corroboration, and produces one merged
> review. Includes a benchmark mode that runs a fixture suite across all
> reviewers to build a leaderboard.

**Working directory for this project:** `d:\projects\.skills\argus\`

## Layout

```
argus/
├── SKILL.md                   # Claude Code skill entry — what /argus runs
├── README.md                  # human-facing overview
├── CLAUDE.md                  # this file
├── config.yaml                # reviewer registry, profiles, host rules, CLI cmds
├── .gitignore
├── prompts/
│   ├── reviewer_prompt.md     # strict-schema JSON prompt (base)
│   └── overlays/
│       ├── security.md
│       └── deep.md
├── scripts/
│   ├── _common.py             # subprocess + JSON + config + history.db helpers
│   ├── detect_host.py         # host CLI detection (claude/codex/gemini/opencode/unknown)
│   ├── dispatch.py            # parallel reviewer fan-out → reviews/*.json
│   ├── merge.py               # confidence filter + corroboration → merged.md + metrics.json
│   ├── estimate_cost.py       # pre-flight cost gate ($0.50 warn / $2 block review; $10/$30 bench)
│   ├── verify.py              # route reachability ping with fallback try
│   ├── benchmark.py           # fixture-suite leaderboard + agreement matrix
│   ├── stats.py               # reads history.db
│   ├── install_aichat.py      # generates ~/.config/aichat/config.yaml (no keys on disk)
│   └── adapters/
│       ├── __init__.py        # ROUTE_ADAPTERS registry
│       ├── aichat.py          # universal aichat wrapper (all 8 provider routes)
│       ├── gemini_cli.py      # gemini --yolo -p "<prompt>"
│       ├── codex_cli.py       # codex exec --skip-git-repo-check -  (stdin)
│       ├── claude_cli.py      # claude -p --output-format text --bare  (stdin, nested-from-claude blocked)
│       ├── opencode_cli.py    # opencode run -  (stdin)
│       └── copilot_cli.py     # copilot -p "<prompt>" --model X --allow-all-tools
├── fixtures/                  # benchmark inputs (diff.patch + ground-truth.json pairs)
│   ├── sql-injection/
│   ├── race-refund/
│   ├── secrets-leak/
│   └── clean-baseline/        # false-positive control (expected: 0 findings)
├── runs/                      # per-invocation artifacts (gitignored)
├── benchmarks/                # per-benchmark leaderboards (gitignored)
└── history.db                 # SQLite — runs, reviewer_runs, findings, benchmarks (gitignored)
```

## Environment — always use these conventions

- **OS:** Windows 11. Python `py -3.12 script.py` (not `python` — Windows Store stub). Bash via Git Bash.
- **ARGUS_HOME:** always set to `d:/projects/.skills/argus` before running scripts:
  ```bash
  export ARGUS_HOME=/d/projects/.skills/argus
  export PYTHONIOENCODING=utf-8          # required on Windows for non-ASCII output
  py -3.12 "$ARGUS_HOME/scripts/<script>.py" ...
  ```
- **API keys in env (never on disk):** `ZAI_API_KEY`, `MINIMAX_API_KEY`,
  `OPENROUTER_API_KEY`, `KIMI_API_KEY` (consumer — not usable for Moonshot
  dev API), `NOUSRESEARCH_API_KEY` (missing — Hermes primary uses OR fallback),
  `GEMINI_API_KEY`, `OPENAI_API_KEY`. Claude CLI uses its own auth. `_common.build_aichat_env()` forwards `$<PROVIDER>_API_KEY` → `AICHAT_<CLIENT>_API_KEY` at subprocess dispatch.
- **Installed CLIs:** `aichat 0.30.0` (scoop), `gemini` / `codex` / `copilot` (npm globals as `.cmd` shims — `shutil.which` resolves them), `claude`, `opencode` (scoop).

## Commit style

Follow the trailers convention used in OMC (the user's preferred style):

```
<type>(<scope>): <subject>

Optional body.

Constraint: <constraint>
Rejected: <alt> | <why>
Confidence: high|medium|low
Scope-risk: narrow|moderate|broad
Directive: <warning for future modifiers>
Not-tested: <uncovered scenario>
```

Include trailers when the decision matters. Skip them for typos / formatting.

## Canonical workflows

### Full verify (all routes)
```bash
py -3.12 "$ARGUS_HOME/scripts/verify.py" --all
```

### End-to-end review on current diff
```bash
RUN_DIR="$ARGUS_HOME/runs/$(date +%Y%m%dT%H%M%S)-manual"
mkdir -p "$RUN_DIR"
git diff HEAD > "$RUN_DIR/diff.patch"
py -3.12 "$ARGUS_HOME/scripts/estimate_cost.py" --roster "glm-5.1,minimax-m2.7,gemini,codex" --diff "$RUN_DIR/diff.patch"
py -3.12 "$ARGUS_HOME/scripts/dispatch.py" --run-dir "$RUN_DIR" --roster "glm-5.1,minimax-m2.7,gemini,codex" --diff "$RUN_DIR/diff.patch"
py -3.12 "$ARGUS_HOME/scripts/merge.py" --run-dir "$RUN_DIR"
```

### Benchmark (fixture suite → leaderboard)
```bash
py -3.12 "$ARGUS_HOME/scripts/benchmark.py" --runs 3 --profile panel
# or: --roster "a,b,c"  --fixtures "sql-injection,secrets-leak"
```

## Important behavior

### Host-CLI awareness
`detect_host.py` inspects env + parent process tree. Returns one of
`claude | codex | gemini | opencode | unknown`. `host_rules` in config.yaml
removes the matching reviewer from the roster and (for non-claude hosts) adds
`claude` in. **When running inside Claude Code, the `claude` reviewer is
auto-skipped** — Claude's nested-invocation policy would block it anyway.

### Confidence filter + corroboration
- Drop findings with effective confidence < 80.
- Bonus: +15 points when ≥2 reviewers flag the same `file:line` (capped at 100).
- Merge dedupes by exact `file:line`. Nearby-line corroboration is NOT done today — reviewers often disagree on line numbers by ±3 within the same diff hunk; this under-counts corroboration. Candidate v2 fix: bucket by file + ±3-line range.

### Cost gates
- Review: warn $0.50, hard block $2.00 — overridable with `--yes-cost`
- Benchmark: warn $10, hard block $30
- Paid-CLI reviewers (Gemini / Codex / Claude / OpenCode / Copilot) have `cost_per_m: null` and count as $0.

### JSON extraction
`_common.extract_json` handles: raw JSON, `<think>` reasoning blocks
(Qwen3 / DeepSeek-R1 style), fenced code blocks, and embedded objects by
"findings" or "ok" key. Every aichat reviewer we tested returns usable JSON.

## Benchmark run protocol (learned from first full bench)

- **One shell per reviewer, always.** Even for aichat-routed reviewers. A
  single shell batching 6 aichat reviewers via asyncio is faster in CPU terms
  but blocks all result visibility until the slowest reviewer in the batch
  completes. Per-reviewer shells give per-reviewer timestamps, per-reviewer
  progress logs, and independent completion notifications.
- **Max 5 shells concurrent** on this machine (CPU + RAM + network headroom).
  Queue the rest; launch next-5 when any of the first 5 completes.
- **Hard wall-cap per reviewer.** `--max-wall-sec`. Defaults: aichat=600s,
  paid-CLI=1200s (CLIs have slow cold-starts). Cap prevents silent 40-min
  stalls like the first aborted run.
- **Always use `asyncio.gather(*tasks, return_exceptions=True)`** +
  per-reviewer try/except. One broken reviewer never kills the whole run.
- **Per-reviewer incremental writes.** Every reviewer writes its own
  `benchmarks/<TS>/per_reviewer/<reviewer>.json` when it finishes — tailable.
  Use `aggregate_bench.py --ts TS` to produce the combined leaderboard.
- **Always dry-run first.** `--runs 1 --fixtures <one>` with the full
  roster catches provider-config bugs in ~30s instead of 40 min.
- **Track wall-time per reviewer in the leaderboard.** Not a ranking axis
  on its own — a cost/quality trade-off column. Fast cheap frontier wins over
  slow expensive frontier when F1 is comparable.

## v2 ideas (captured for later)
- **Nearby-line corroboration in merge.** Currently bucket by exact
  `file:line`; reviewers often differ by ±3 within the same hunk. Bucket
  by file + ±3-line range to increase corroboration accuracy.
- **User-action capture.** After merged.md is shown, collect accepted/rejected
  per finding into history.db. Use this for usage-driven preference weights.
- **`--refresh` command.** Query OpenRouter `/models` and diff against pinned
  model IDs in config.yaml; prompt for edits when upstream renames happen.
- **`--compare runA runB`** diff two merged.md outputs side-by-side.

## Known issues / open work

| Issue | Status | Fix |
|---|---|---|
| GLM-5.1 z.ai direct → "Insufficient balance" | fallback via OR works | top up z.ai account |
| MiniMax-M2.7 direct → works (slow, 20s for fixture) | — | — |
| Kimi `KIMI_API_KEY` is consumer-only | forced OR primary (`moonshotai/kimi-k2.5`) | need Moonshot Platform dev key for k2.6-preview |
| Nous Hermes direct → `NOUSRESEARCH_API_KEY` not in env | OR fallback works | set env var if wanted |
| Gemini CLI slow (60-70s/call) | works, use sparingly for quick reviews | no fix — CLI startup time |
| OpenCode CLI slow (42+s/call) | works, barely fits 45s verify timeout | set longer timeout in dispatch (already 180s) |
| Merge doesn't apply line-tolerance to corroboration | under-counts corroborated findings | v2: ±3-line bucketing |
| Fixtures only cover 4 scenarios | leaderboard is noisy at N=4 | author more fixtures (auth bypass, XSS, null-deref, async races, TOCTOU, etc.) |

## Reviewer recommendations (initial, pre-benchmark)

Ryan's preferences so far: GLM-5.1 and MiniMax M2.7 (has direct subs).
Default `standard` profile: `glm-5.1, minimax-m2.7, gemini, codex` — balances
Chinese + Western frontier, direct subs + paid CLIs.

After benchmark completes we'll know agreement-matrix redundancies and which
reviewers can demote to `custom_only` or fallback.

## GitHub push plan (deferred)

Ryan intends to publish Argus to his personal GitHub. Might be a general
skills repo or standalone. Before pushing:

- Verify `.gitignore` excludes `runs/`, `benchmarks/`, `history.db`, `__pycache__/`
- Ensure no API keys anywhere on disk (they aren't; double-check)
- Strip the initial-commit git history we made for self-review
- Consider README polish + screenshots of merged.md / leaderboard output

## Interaction with other skills/plugins

- `/gsd-code-review` has a sibling workflow; Argus's `--output gsd` emits
  the REVIEW.md schema so `/gsd-code-review-fix` can consume Argus output.
- OMC's benchmark fixtures at
  `~/.claude/plugins/marketplaces/omc/benchmarks/code-reviewer/` use a
  different schema (full code files + location-by-explanation ground truth).
  Argus fixtures are diff-based. Do NOT copy OMC fixtures directly — the
  schemas differ. Can port by synthesizing diffs from their code files.
