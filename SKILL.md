---
name: argus
description: >-
  Multi-model code review. Dispatches a diff / PR / files to a configurable roster
  of reviewers (GLM-5.1, MiniMax M2.7, Kimi K2.6, MiMo-V2-Pro, Qwen3.6-Plus,
  Grok 4.20, DeepSeek V3.2, Gemini CLI, Codex CLI, Claude CLI, OpenCode CLI)
  in parallel, applies a confidence filter with cross-reviewer corroboration,
  and produces one merged review. Includes benchmark mode that runs the full
  fixture suite to establish preferred reviewers.
argument-hint: "[--profile NAME | --custom LIST | --models LIST] [--pr URL | --files GLOB | -] [--benchmark] [--stats] [--dry-run] [--yes-cost] [--allow-free] [--save-as NAME] [--output {md,json,gsd}]"
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
---

<objective>
Run a multi-model code review using the Argus skill at `d:/projects/.skills/argus/`.
</objective>

<context>
- Skill root: `d:/projects/.skills/argus/` (env: `ARGUS_HOME`)
- Config: `$ARGUS_HOME/config.yaml`
- Scripts: `$ARGUS_HOME/scripts/*.py` (Python 3.12)
- Runs: `$ARGUS_HOME/runs/<ISO-ts>-<id>/`
- Benchmarks: `$ARGUS_HOME/benchmarks/<ts>.{md,json}`
- History: `$ARGUS_HOME/history.db` (SQLite, created on first run)
</context>

<execution>

## 1. Parse arguments

Extract from `$ARGUMENTS`:

| Flag | Effect |
|---|---|
| `--profile NAME` | Use named profile (quick / standard / panel / security / deep / favorites / saved-custom-name) |
| `--custom "a,b,c"` | One-off roster; combine with `--save-as NAME` to persist |
| `--models "a,b,c"` | Alias for `--custom`, never saved |
| `--pr URL` | Diff via `gh pr diff URL` |
| `--files GLOB` | Scope via `git diff -- GLOB` |
| `-` or no scope | Stdin, else `git diff HEAD` |
| `--benchmark [--runs N]` | Run fixture suite (default N=3), produce leaderboard |
| `--stats` | Per-reviewer accuracy, cost, agreement matrix from history.db |
| `--dry-run` | Print roster + cost estimate, do not dispatch |
| `--yes-cost` | Bypass $2 hard block for this run |
| `--allow-free` | Allow free-tier reviewers |
| `--allow-logging` | Include reviewers that log prompts/completions |
| `--save-as NAME` | Persist `--custom` list as a named profile |
| `--output {md,json,gsd}` | Output format (default: md) |
| `--refresh` | Check for model ID updates on OpenRouter |
| `--compare RUN_A RUN_B` | Diff two previous runs |

Env overrides: `ARGUS_PROFILE`, `ARGUS_YES_COST=1`, `ARGUS_OUTPUT=gsd`.

## 2. Detect host CLI and adapt roster

```bash
HOST=$(python "$ARGUS_HOME/scripts/detect_host.py")
```

Apply `host_rules[$HOST]` from config.yaml: remove `skip` list, append `add` list.

## 3. Resolve the roster

1. Load config.yaml
2. Base list from `--profile` / `--custom` / `--models` / default profile
3. Apply host rules (step 2 above)
4. Apply filters:
   - drop reviewers with `tier: free` unless `--allow-free`
   - drop reviewers with `privacy: LOGS` unless `--allow-logging`
   - drop reviewers with `custom_only: true` unless explicitly named
5. Dedupe

If roster is empty, abort with message and list disabled reasons.

## 4. Gather scope → diff

Produce a single diff.patch in the new run directory:

- `--pr URL` → `gh pr diff URL > diff.patch`
- `--files GLOB` → `git diff -- GLOB > diff.patch`
- stdin present → read stdin into diff.patch
- else → `git diff HEAD > diff.patch`

Apply `.argusignore` (project root) to strip matching paths from diff.

If diff is empty after filtering, abort.

## 5. Pre-flight cost estimate

```bash
python "$ARGUS_HOME/scripts/estimate_cost.py" --roster "$ROSTER" --diff "$RUN_DIR/diff.patch"
```

Exit codes: 0 OK, 1 WARN (≥ warn), 2 BLOCK (≥ block).
On BLOCK without `--yes-cost`: stop. Report estimate to user.

If `--dry-run`: stop here and print roster + estimate. Do not dispatch.

## 6. Dispatch

Argus supports two dispatch modes. **Subagent-per-reviewer is the default
recommended pattern** — single-process is the legacy / quick path.

### 6a. Default: subagent-per-reviewer (recommended)

When more than one reviewer is in the roster, the calling agent should
dispatch ONE subagent per reviewer via the parent platform's Agent /
subagent API (Claude Code: Agent tool with `run_in_background: true`).
Each subagent runs:

```bash
python "$ARGUS_HOME/scripts/dispatch.py" \
  --run-dir "$RUN_DIR" \
  --roster "<single-reviewer-name>" \
  --diff   "$RUN_DIR/diff.patch" \
  [--overlay security|deep]
```

**Concurrency cap: at most 4 subagents running in parallel.** If the roster
has more than 4 reviewers, dispatch the first 4 in a wave, then queue the
rest and dispatch as each completes. This matches `defaults.max_parallel: 4`
in config.yaml and keeps per-reviewer visibility (independent timestamps,
streaming progress, isolated failure modes).

### 6b. Legacy / quick path: single-process dispatch

For a roster of ≤4 reviewers OR when per-reviewer subagent visibility isn't
needed, the calling agent MAY run argus's in-process dispatch:

```bash
python "$ARGUS_HOME/scripts/dispatch.py" \
  --run-dir "$RUN_DIR" \
  --roster "$ROSTER" \
  --diff   "$RUN_DIR/diff.patch" \
  [--overlay security|deep]
```

This still uses argus's internal `max_parallel: 4` cap from config.yaml.

### 6c. Failure semantics (both modes)

Each reviewer writes `$RUN_DIR/reviews/<name>.json`. Timeouts, non-zero
exits, and parse failures are logged but do not abort the run; other
reviewers continue. After all reviewers return (subagent or in-process),
run `merge.py` exactly once in the main session (step 7).

## 7. Merge + filter

```bash
python "$ARGUS_HOME/scripts/merge.py" --run-dir "$RUN_DIR"
```

Applies confidence threshold, corroboration boost, dedupes by file:line,
writes `merged.md` and `metrics.json`. Also appends a row to `history.db`.

## 8. Present

Print `merged.md`. Include summary line: N findings, corroborated/solo breakdown,
wall time, total estimated cost, run directory path.

## 9. Optional: benchmark mode

```bash
python "$ARGUS_HOME/scripts/benchmark.py" --runs 3 [--profile panel | --roster LIST]
```

Runs every roster member against every fixture N times. Produces
`benchmarks/<ts>.md` (leaderboard) and `benchmarks/<ts>.json`. Uses the
separate benchmark cost gate ($10 warn / $30 block).

## 10. Optional: stats mode

```bash
python "$ARGUS_HOME/scripts/stats.py"
```

Per-reviewer: runs, avg cost, avg latency, accuracy (if benchmarks present),
pairwise agreement matrix. Flags redundant pairs (>85% agreement) as
candidates for demotion to fallbacks/custom.

</execution>

<rules>
- Respect `privacy_mode: true` by default. Never include logger reviewers without `--allow-logging`.
- Never pass free-tier reviewers without `--allow-free`.
- Never exceed review cost block threshold without `--yes-cost` (env: `ARGUS_YES_COST=1`).
- Never rewrite config.yaml without explicit user approval (only `--save-as` adds profiles, and only after showing the diff).
- Reviewer timeouts or bad output never abort the run; they're logged and the run continues with surviving reviewers.
- After every run, append to `history.db`.
</rules>
