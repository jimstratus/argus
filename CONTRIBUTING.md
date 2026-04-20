# Contributing to Argus

## Reviewer / provider changes

Adding or changing a reviewer is a config change, not a code change:

1. Edit `config.yaml` → add entry to `reviewers:` with `primary` + optional `fallback`
2. If it's a new CLI, add an adapter under `scripts/adapters/<name>_cli.py` (see existing ones for the shape)
3. `python scripts/verify.py --roster <name>` to confirm the route works
4. Optionally add the reviewer to a profile

## Fixture contributions

New fixtures are valuable — they sharpen the benchmark signal.

- One directory per fixture under `fixtures/`
- `diff.patch` (realistic git-diff output) + `ground-truth.json`
- Ground truth should list **only** bugs a senior engineer would actually flag — false-positive-prone fixtures are anti-contributions
- Clean baselines (empty `issues[]`) are valuable for FP-rate measurement

## Bug reports

- Include the full `error` or `stderr_preview` from a `runs/<id>/reviews/<name>.json` if the issue is reviewer-specific
- Include `scripts/verify.py --json --roster <name>` output for reachability issues
- Report `aichat --version`, Python version, OS

## Code style

- Python 3.12+. Type hints where they clarify; not exhaustive.
- No new dependencies without justification. pyyaml + psutil is the current bar.
- Shell scripts must work on both Git Bash (Windows) and POSIX.

## Don't break

- API keys must stay in env vars. Never written to disk in any code path.
- `privacy_mode: true` default. Any new reviewer that logs prompts must set `privacy: LOGS`.
- Cost gates ($2 review / $30 benchmark defaults) must remain enforceable.
- `verify.py --all` must respect `disabled: true` reviewers.
