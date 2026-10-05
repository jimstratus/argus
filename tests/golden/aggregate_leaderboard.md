# Argus Benchmark — `20261004T120000` (parallel-shell aggregate)

**Reviewers collected:** 5

## Leaderboard (by F1)

| Rank | Reviewer | F1 | Precision | Recall | Avg call (s) | Total calls (s) | Status |
|------|----------|----|-----------|--------|--------------|-----------------|--------|
| 1 | `beta` | 0.833 | 0.750 | 1.000 | 7.33 | 44.0 | ok |
| 2 | `alpha` | 0.500 | 0.500 | 0.500 | 5.50 | 22.0 | ok |
| 3 | `partial-one` | 0.500 | 0.000 | 0.000 | 0.00 | 0.0 | partial |
| 4 | `delta` | 0.000 | 0.000 | 0.000 | 0.00 | 0.0 | fatal |
| 5 | `?` | 0.000 | 0.000 | 0.000 | 0.00 | 0.0 | ok |

## Per-fixture detail

### `beta` — overall F1 = 0.833

| Fixture | Precision | Recall | F1 | Avg findings | Avg latency (s) |
|---------|-----------|--------|----|--------------|-----------------|
| clean-baseline | 1.000 | 1.000 | 1.000 | 0.0 | 3.25 |
| sql-injection | 0.500 | 1.000 | 0.667 | 2.0 | 11.40 |

### `alpha` — overall F1 = 0.500

| Fixture | Precision | Recall | F1 | Avg findings | Avg latency (s) |
|---------|-----------|--------|----|--------------|-----------------|
| clean-baseline | 0.250 | 0.000 | 0.000 | 0.0 | 0.00 |
| ? | 0.000 | 0.000 | 0.000 | 0.0 | 0.00 |

### `partial-one` — overall F1 = 0.500
_No data._

### `delta` — overall F1 = 0.000
_Fatal: RuntimeError: boom_

### `?` — overall F1 = 0.000

| Fixture | Precision | Recall | F1 | Avg findings | Avg latency (s) |
|---------|-----------|--------|----|--------------|-----------------|
| x | 0.100 | 0.200 | 0.300 | 0.4 | 0.50 |
