---
name: argus
description: >-
  Multi-model code review. Dispatches a diff / PR / files to a configurable roster
  of reviewers (GLM-5.2, MiniMax M3, Kimi K2.6, MiMo-V2-Pro, Qwen3.6-Plus,
  Grok 4.20, DeepSeek V4 Pro, Gemini CLI, Codex CLI, Claude CLI, OpenCode CLI)
  in parallel, applies a confidence filter with cross-reviewer corroboration,
  and produces one merged review. Includes benchmark mode that runs the full
  fixture suite to establish preferred reviewers.
argument-hint: "[--profile NAME | --custom LIST | --models LIST] [--pr URL | --files GLOB | -] [--route-pref {openrouter,direct} | --prefer-direct | --prefer-openrouter] [--benchmark] [--stats] [--dry-run] [--yes-cost] [--allow-free] [--save-as NAME] [--output {md,json,gsd}]"
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
| `--profile NAME` | Use named profile (quick / standard / panel / security / deep / favorites / direct / leaderboard-top5 / saved-custom-name) |
| `--route-pref {openrouter,direct}` | Route preference for dual-route reviewers (glm-5.2 / minimax-m3 / deepseek-v4-pro). `openrouter` (default) tries OpenRouter first; `direct` tries each provider's own API first. Shorthands: `--prefer-direct`, `--prefer-openrouter`. Env: `ARGUS_ROUTE_PREF`. |
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

Env overrides: `ARGUS_PROFILE`, `ARGUS_YES_COST=1`, `ARGUS_OUTPUT=gsd`,
`ARGUS_ROUTE_PREF={openrouter,direct}`.

## 2. Detect host CLI and adapt roster

```bash
HOST=$(python "$ARGUS_HOME/scripts/detect_host.py")
```

Apply `host_rules[$HOST]` from config.yaml: remove `skip` list, append `add` list.

## 3. Resolve the roster

1. Load config.yaml
2. Base list from `--profile` / `--custom` / `--models` / default profile
3. Apply host rules (step 2 above). For explicitly-named rosters
   (`--custom` / `--models`) apply only the `skip` list — never inject
   `add` reviewers the user didn't ask for.
4. Apply filters:
   - drop reviewers with `disabled: true` unless explicitly named
   - drop reviewers with `tier: free` unless `--allow-free`
   - drop reviewers with `privacy: LOGS` unless `--allow-logging`
   - drop reviewers with `custom_only: true` unless explicitly named
5. Dedupe

If roster is empty, abort with message and list disabled reasons.

Defense in depth: `dispatch.py` and `benchmark.py` enforce this same policy
internally via `_common.resolve_roster` (drops recorded in
`dispatch_summary.json` under `"dropped"`), and `estimate_cost.py` rejects
unknown reviewer names — so a skipped filter here fails safe downstream.

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

If the user passed `--route-pref` / `--prefer-direct` / `--prefer-openrouter`
(or `ARGUS_ROUTE_PREF` is set), forward the same flag to `estimate_cost.py`,
`dispatch.py`, and `benchmark.py` so the cost/balance gate and dispatch agree
on which provider each dual-route reviewer hits first.

Exit codes: 0 OK, 1 WARN (≥ warn threshold or low OpenRouter balance),
2 BLOCK (≥ block threshold) **or invalid roster** — check stderr to tell them
apart; `--yes-cost` downgrades a cost BLOCK to WARN but cannot fix an invalid
roster. On BLOCK without `--yes-cost`: stop. Report estimate to user.

If `--dry-run`: stop here and print roster + estimate. Do not dispatch.

## 6. Dispatch

Argus supports two dispatch modes. **Subagent-per-reviewer is the default
recommended pattern** — single-process is the legacy / quick path.

### 6a. Default: subagent-per-reviewer (recommended)

When more than one reviewer is in the roster, the calling agent should
dispatch ONE subagent per reviewer via the parent platform's Agent /
subagent API (Claude Code: Agent tool with `run_in_background: true` on the
**parent's** Agent call — so the parent fans out concurrent subagents
without blocking). Each subagent runs:

```bash
python "$ARGUS_HOME/scripts/dispatch.py" \
  --run-dir "$RUN_DIR" \
  --roster "<single-reviewer-name>" \
  --diff   "$RUN_DIR/diff.patch" \
  [--overlay security|deep]
```

#### CRITICAL: subagent execution semantics

The subagent MUST run `dispatch.py` **synchronously in its OWN session
(foreground)** and wait for the process to exit before ending. If the
subagent uses its own `run_in_background: true` to spawn `dispatch.py`,
the subagent's session ends BEFORE `dispatch.py` completes, and
`$RUN_DIR/reviews/<name>.json` is never written. The parent then sees a
"completed" subagent with no result.

This is observed when a subagent reports back with a plan ("I'll wait
for the dispatch...") instead of actual results — that's the
fingerprint of the bailout bug.

**Always include explicit synchronous-execution wording in the subagent
prompt.** A minimal safe template:

```
You are dispatching a SINGLE argus reviewer. Do not do any other work.

Run this command IN THE FOREGROUND (synchronously) and WAIT for it to
exit. Do NOT use run_in_background. This may take 30s–5min depending on
the reviewer; that is expected — block your session until it returns.

    python "$ARGUS_HOME/scripts/dispatch.py" \
      --run-dir "<RUN_DIR>" \
      --roster "<reviewer-name>" \
      --diff   "<RUN_DIR>/diff.patch" \
      [--overlay security|deep]

After it exits, read `<RUN_DIR>/reviews/<reviewer-name>.json` and
report back in under 100 words:

- exit code from the dispatch command
- latency_sec field from the JSON
- count of findings (length of .findings array, 0 if missing)
- skipped status + skip_reason if set
- error field if present
- fallback_used flag

Do NOT run merge.py — the parent session handles that.
Do NOT modify any files. Do NOT do any other work.
```

If a subagent's result-reporting indicates it never read the review
JSON (or the file is missing on disk), re-dispatch that single reviewer
either as a fresh subagent with stricter prompt wording, or directly
in the parent session with `run_in_background: true` on the parent's
Bash call (parent stays responsive while waiting for completion).

#### Concurrency cap

**At most 4 subagents running in parallel.** If the roster has more than
4 reviewers, dispatch the first 4 in a wave, then queue the rest and
dispatch as each completes. This matches `defaults.max_parallel: 4` in
config.yaml and keeps per-reviewer visibility (independent timestamps,
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

Applies the confidence threshold, corroboration boost, and anchor-based
±3-line clustering (`defaults.merge_line_tolerance` / `--line-tolerance`),
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
