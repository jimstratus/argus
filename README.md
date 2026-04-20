# Argus — multi-model code review skill

Dispatches a diff, PR, or file set to a configurable roster of frontier code
reviewers in parallel, applies a confidence filter with cross-reviewer
corroboration, and produces one merged review. Includes a benchmark mode that
runs the full fixture suite to establish preferred reviewers over time.

Skill root: `d:/projects/.skills/argus/`

## Reviewers

| Reviewer | Route | Primary API | Tier |
|---|---|---|---|
| `glm-5.1`       | aichat → z.ai direct (fallback: OpenRouter) | `$ZAI_API_KEY` | paid |
| `minimax-m2.7`  | aichat → minimax.io direct (fallback: OpenRouter) | `$MINIMAX_API_KEY` | paid |
| `kimi-k2.6`     | aichat → Moonshot direct (fallback: OpenRouter) | `$KIMI_API_KEY` | paid |
| `mimo-v2-pro`   | aichat → OpenRouter | `$OPENROUTER_API_KEY` | paid |
| `qwen-3.6-plus` | aichat → OpenRouter | `$OPENROUTER_API_KEY` | paid |
| `grok-4.20`     | aichat → OpenRouter | `$OPENROUTER_API_KEY` | paid |
| `deepseek-v3.2` | aichat → OpenRouter | `$OPENROUTER_API_KEY` | paid |
| `hermes-4.3`    | aichat → Nous Portal (fallback: OR) — custom-only | `$NOUSRESEARCH_API_KEY` | paid |
| `gemini`        | gemini CLI (paid sub) | — | paid |
| `codex`         | codex CLI (paid sub) | — | paid |
| `claude`        | claude CLI (paid sub, auto-added when host != claude) | — | paid |
| `opencode`      | opencode CLI (your Go sub) | — | paid |
| `copilot-gpt5`  | GitHub Copilot CLI — custom-only, for harness comparison | — | paid |

## Profiles

| Profile | Members | Purpose |
|---|---|---|
| `quick` | glm-5.1, gemini | 2-reviewer smoke test |
| `standard` *(default)* | glm-5.1, minimax-m2.7, gemini, codex | everyday review |
| `panel` | all minus custom-only | maximum coverage |
| `security` | glm-5.1, deepseek-v3.2, codex, claude | auth / crypto / input handling |
| `deep` | grok-4.20, mimo-v2-pro, gemini, codex | long-context / large diffs |
| `favorites` | glm-5.1, minimax-m2.7 | your direct-sub picks |

## Usage

```bash
# Default profile (standard), diff = git diff HEAD
python scripts/dispatch.py ...      # invoked from SKILL.md

# Via Claude Code skill invocation:
/argus
/argus --profile security
/argus --custom "glm-5.1,deepseek-v3.2,claude,copilot-gpt5"
/argus --pr https://github.com/org/repo/pull/42
/argus --files "src/auth/**/*.ts"
/argus --benchmark --runs 3
/argus --stats
/argus --dry-run
```

## Flags

| Flag | Effect |
|---|---|
| `--profile NAME` | Named profile |
| `--custom "a,b,c"` | One-off roster (combine with `--save-as`) |
| `--models "a,b,c"` | Alias for `--custom`, not saved |
| `--pr URL` / `--files GLOB` / `-` | Diff source |
| `--benchmark [--runs N]` | Fixture-suite benchmark + leaderboard |
| `--stats` | History.db dump |
| `--dry-run` | Roster + cost estimate, no dispatch |
| `--yes-cost` | Bypass $2 per-run hard block |
| `--allow-free` | Include free-tier reviewers |
| `--allow-logging` | Include reviewers that log prompts |
| `--save-as NAME` | Persist custom roster as named profile |
| `--output {md,json,gsd}` | Output format (default: md; `gsd` emits REVIEW.md for gsd-code-review-fix consumption) |
| `--refresh` | Check for model-ID updates |
| `--compare RUN_A RUN_B` | Diff two prior runs |

## Quality mechanics

1. **Strict-schema JSON output** — every reviewer is instructed to return
   `{findings: [{file, line, severity, category, description, confidence}]}`.
   `_common.extract_json` is tolerant of fenced code blocks and stray prose.
2. **Context-window pre-check** — if estimated prompt tokens > 70% of the
   reviewer's context window, the reviewer is skipped (logged, run continues).
3. **Confidence threshold** — findings below 80 are dropped.
4. **Corroboration boost** — a finding flagged by ≥2 reviewers on the same
   `file:line` gets +15 confidence (capped at 100).
5. **Severity + confidence sort** — output sorted critical→low, then by
   confidence desc.

## Cost gates

| Mode | Warn | Block |
|---|---|---|
| review     | $0.50 | $2.00 |
| benchmark  | $10   | $30   |

Block is enforced unless `--yes-cost` (env: `ARGUS_YES_COST=1`) is set.
Paid-CLI reviewers (Gemini, Codex, Claude, OpenCode, Copilot) incur no tracked
cost (they use your host subscriptions).

## Host-CLI awareness

Argus detects which CLI it's running inside and adapts the roster:

| Host | Skip | Add |
|---|---|---|
| claude   | claude   | — |
| codex    | codex    | claude |
| gemini   | gemini   | claude |
| opencode | opencode | claude |
| unknown  | —        | — |

Rule: never ask the host CLI to review its own invocation; ensure Claude is in
the mix when Claude isn't the host.

## Privacy

- `privacy_mode: true` by default — reviewers with `privacy: LOGS` are excluded.
- API keys live in env vars (ZAI_API_KEY, MINIMAX_API_KEY, OPENROUTER_API_KEY,
  KIMI_API_KEY, NOUSRESEARCH_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY).
  Keys are never written to disk by any Argus script.
- aichat reads `AICHAT_<CLIENT>_API_KEY` for named openai-compatible clients.
  Argus forwards the source env var to that target name at subprocess
  dispatch time via `scripts/_common.build_aichat_env()`.

## One-time setup

```bash
# 1. Install aichat config (writes api_base only; no keys on disk)
python d:/projects/.skills/argus/scripts/install_aichat.py

# 2. Verify all configured routes reach a live model
python d:/projects/.skills/argus/scripts/verify.py --all

# 3. First benchmark to seed the leaderboard
python d:/projects/.skills/argus/scripts/benchmark.py --runs 3 --profile standard
```

## Files

```
argus/
├── SKILL.md                   # skill entry point
├── README.md                  # this file
├── config.yaml                # reviewer registry, profiles, host rules, CLI commands
├── prompts/
│   ├── reviewer_prompt.md     # strict-schema JSON prompt
│   └── overlays/{security,deep}.md
├── scripts/
│   ├── _common.py             # shared helpers (subprocess, JSON, config, history DB)
│   ├── detect_host.py         # env + process walk → host CLI identity
│   ├── dispatch.py            # parallel reviewer fan-out
│   ├── merge.py               # confidence filter + corroboration + output
│   ├── estimate_cost.py       # pre-flight cost gate
│   ├── verify.py              # route reachability ping
│   ├── benchmark.py           # fixture-suite leaderboard + agreement matrix
│   ├── stats.py               # history.db summary
│   ├── install_aichat.py      # generate ~/.config/aichat/config.yaml
│   └── adapters/
│       ├── __init__.py
│       ├── aichat.py
│       ├── gemini_cli.py
│       ├── codex_cli.py
│       ├── claude_cli.py
│       ├── opencode_cli.py
│       └── copilot_cli.py
├── fixtures/                  # benchmark fixtures
│   ├── sql-injection/
│   ├── race-refund/
│   ├── secrets-leak/
│   └── clean-baseline/        # false-positive control
├── runs/                      # per-invocation artifacts
├── benchmarks/                # per-benchmark leaderboards
└── history.db                 # SQLite, created on first run
```

## Known gotchas

- **Exact model IDs** for z.ai, MiniMax, Moonshot, and Nous are best-known
  guesses. Run `verify.py --all` after install; any failing route means the
  model ID in `config.yaml` needs a fix.
- **Copilot CLI prompt-as-arg** has a ~32KB Windows arg limit. Very large
  diffs will fail on that reviewer. Use a `--files` scope to shrink the diff.
- **OpenCode adapter** uses `opencode run -`. Verify this syntax against your
  installed version; `opencode run [message..]` is the documented form.
- **Gemini / Codex stdin** — both CLIs accept prompts via stdin with `-p ""`
  and `exec -` respectively, but adapter assumptions will be surfaced by
  `verify.py`. Tune `cli_commands:` in `config.yaml` if a CLI rejects stdin.
