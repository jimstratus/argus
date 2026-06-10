# Argus — Development Guide

Multi-model code review skill. Dispatches diffs to a roster of LLM reviewers in parallel, filters by confidence with cross-reviewer corroboration, and produces one merged review.

## Prerequisites

- **Python** 3.12+
- **aichat** 0.30+ ([github.com/sigoden/aichat](https://github.com/sigoden/aichat))
- **pip** packages: `pyyaml`, `psutil`
- At least one CLI reviewer: `claude`, `codex`, `gemini`, `opencode`, or `copilot`
- At least one API key: `OPENROUTER_API_KEY` (covers 8 of 14 reviewers)

## Setup

```bash
git clone https://github.com/jimstratus/argus.git
cd argus
export ARGUS_HOME="$PWD"
pip install pyyaml psutil

# Configure aichat (api_base only; keys stay in env)
python scripts/install_aichat.py --merge

# Verify reachability
python scripts/verify.py --all
```

## Environment

API keys live in env — **never** written to disk by Argus. aichat reads `AICHAT_<CLIENT>_API_KEY`, which Argus forwards at subprocess dispatch time.

```bash
export OPENROUTER_API_KEY=***
export ZAI_API_KEY=***
export MINIMAX_API_KEY=***
export KIMI_API_KEY=***
export GEMINI_API_KEY=***
export OPENAI_API_KEY=***
export NOUSRESEARCH_API_KEY=***     # optional
```

## Project Structure

```
argus/
├── SKILL.md                    # Claude Code skill entry
├── README.md                   # Human-facing overview
├── CLAUDE.md                   # Project context for contributors
├── CONTRIBUTING.md             # Contribution guidelines
├── config.yaml                 # Reviewers, profiles, host rules, CLI commands, aichat patches
├── prompts/
│   ├── reviewer_prompt.md      # Strict-schema JSON prompt (base)
│   └── overlays/
│       ├── security.md
│       ├── deep.md
│       └── audit.md
├── scripts/
│   ├── _common.py              # Shared helpers (subprocess, JSON, config, history.db)
│   ├── detect_host.py          # Host CLI detection
│   ├── dispatch.py             # Parallel reviewer fan-out
│   ├── merge.py                # Confidence filter + corroboration + output
│   ├── benchmark.py            # Fixture-suite leaderboard
│   ├── aggregate_bench.py      # Merge per-reviewer JSONs from parallel-shell runs
│   ├── estimate_cost.py        # Pre-flight cost gate
│   ├── bench_cost.py           # Retrospective cost analysis
│   ├── verify.py               # Route reachability ping
│   ├── or_balance.py           # OpenRouter balance check
│   ├── stats.py                # history.db summary
│   ├── install_aichat.py       # aichat config management
│   └── adapters/
│       ├── aichat.py
│       ├── gemini_cli.py
│       ├── codex_cli.py
│       ├── claude_cli.py
│       ├── opencode_cli.py
│       └── copilot_cli.py
├── fixtures/                   # Benchmark inputs (diff.patch + ground-truth.json)
├── runs/                       # Per-invocation artifacts (gitignored)
├── benchmarks/                 # Leaderboard outputs (gitignored)
└── history.db                  # SQLite — runs, findings, benchmarks (gitignored)
```

## Key Scripts

### Review Pipeline

```bash
# Estimate cost before running
python scripts/estimate_cost.py --roster "glm-5.1,minimax-m2.7,gemini-or,codex" \
  --diff <(git diff HEAD)

# Dispatch parallel review
RUN_DIR="$ARGUS_HOME/runs/$(date +%Y%m%dT%H%M%S)-manual"
mkdir -p "$RUN_DIR"
git diff HEAD > "$RUN_DIR/diff.patch"
python scripts/dispatch.py --run-dir "$RUN_DIR" \
  --roster "glm-5.1,minimax-m2.7,gemini-or,codex" \
  --diff "$RUN_DIR/diff.patch"

# Merge results
python scripts/merge.py --run-dir "$RUN_DIR"
```

### Benchmark

```bash
# Full benchmark suite
python scripts/benchmark.py --runs 3 --profile standard --progress

# For large rosters, use parallel shells:
TS=$(date +%Y%m%dT%H%M%S)
for reviewer in glm-5.1 minimax-m2.7 gemini-or codex opencode; do
  python scripts/benchmark.py \
    --roster "$reviewer" \
    --runs 3 --progress \
    --benchmark-ts "$TS" \
    --max-wall-sec 600 &
done
wait
python scripts/aggregate_bench.py --ts "$TS"
```

### Verification

```bash
# Check all reviewer routes
python scripts/verify.py --all

# Check specific reviewer
python scripts/verify.py --roster glm-5.1

# JSON output for scripting
python scripts/verify.py --json --all
```

### Stats

```bash
python scripts/stats.py
```

## Architecture Notes

### Host-CLI Awareness

`detect_host.py` inspects env + parent process tree. Returns `claude | codex | gemini | opencode | unknown`. The matching reviewer is removed from the roster; non-claude hosts auto-add `claude`.

### Confidence Filter + Corroboration

- Findings with effective confidence < 80 are dropped
- +15 confidence bonus (cap 100) when >=2 reviewers flag the same file:line
- Merge dedupes by exact file:line

### Cost Gates

| Mode | Warn | Hard block | Override |
|------|------|-----------|----------|
| review | $0.50 | $2.00 | `--yes-cost` |
| benchmark | $10 | $30 | `--yes-cost` |
| OR balance | (auto) | `available < safety × estimate` | `--skip-balance-check` |

### JSON Extraction

`_common.extract_json` handles: raw JSON, `<think>` reasoning blocks (Qwen3/DeepSeek-R1), fenced code blocks, and embedded objects by "findings" or "ok" key.

## Testing

```bash
# Verify all routes are reachable
python scripts/verify.py --all

# Dry-run benchmark (one fixture, one run)
python scripts/benchmark.py --runs 1 --fixtures sql-injection --progress

# Cost estimate without dispatching
python scripts/estimate_cost.py --roster "glm-5.1,minimax-m2.7,gemini-or,codex" \
  --diff <(git diff HEAD)
```

## Code Style

- Python 3.12+. Type hints where they clarify; not exhaustive.
- No new dependencies without justification (`pyyaml` + `psutil` is the current bar)
- New CLI adapters follow the pattern in `scripts/adapters/`

## Known Gotchas

- **Windows .cmd shim tree-kill**: fixed — `run_subprocess` kills the whole process tree on timeout (killpg on POSIX, `taskkill /T /F` on Windows). gemini-direct stays disabled until re-tested on Windows; `gemini-or` remains the default route.
- **OpenRouter reasoning providers**: `z-ai/glm-5.1` and `minimax/minimax-m2.7` may route to providers returning `{content: null}`. Mitigation: aichat patch applies reasoning-exclude + provider-ignore.
- **Argv length on Windows (~32KB)**: fixed — all CLI adapters pipe the prompt via stdin; no adapter embeds it in argv.
- **Full-codebase audit prompt mismatch**: Default prompt optimized for PR review. Use `--overlay audit` for empty-tree→HEAD diffs.
