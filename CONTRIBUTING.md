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

## Tests

- `python -m pytest tests/ -q` must pass — CI runs it on every push/PR.
  Tests need no network or API keys.
- Bug fixes in `_common.py` (extract_json, run_subprocess, merge scoring)
  should come with a regression test alongside the existing ones in `tests/`.

## Code style

- Python 3.12+. Type hints where they clarify; not exhaustive.
- No new dependencies without justification. pyyaml + psutil is the current bar.
- Shell scripts must work on both Git Bash (Windows) and POSIX.
- Roster policy lives only in `_common.resolve_roster` — don't add inline
  roster filters to individual scripts.

## Don't break

- API keys must stay in env vars. Never written to disk in any code path.
- `privacy_mode: true` default. Any new reviewer that logs prompts must set `privacy: LOGS`.
- Cost gates ($2 review / $30 benchmark defaults) must remain enforceable.
- `verify.py --all` must respect `disabled: true` reviewers.
