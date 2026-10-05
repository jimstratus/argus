# Argus Benchmark — `20261004T120000`

**Fixtures (2):** clean-baseline, sql-injection  
**Runs per fixture:** 3  
**Reviewers tested:** 4  
**Total calls:** 24

## Leaderboard (by F1)

| Rank | Reviewer | F1 | Precision | Recall | Avg latency (s) |
|------|----------|----|-----------|--------|-----------------|
| 1 | `beta` | 0.833 | 0.75 | 1.0 | 7.33 |
| 2 | `alpha` | 0.5 | 0.5 | 0.5 | 5.5 |
| 3 | `gamma` | 0.5 | 0.167 | 0.25 | 10.06 |
| 4 | `delta` | 0.0 | 0.0 | 0.0 | 0.0 |

## Per-fixture detail

### `beta` — overall F1 = 0.833

| Fixture | Precision | Recall | F1 | Avg findings | Avg latency (s) |
|---------|-----------|--------|----|--------------|-----------------|
| clean-baseline | 1.0 | 1.0 | 1.0 | 0.0 | 3.25 |
| sql-injection | 0.5 | 1.0 | 0.667 | 2.0 | 11.4 |

### `alpha` — overall F1 = 0.5

| Fixture | Precision | Recall | F1 | Avg findings | Avg latency (s) |
|---------|-----------|--------|----|--------------|-----------------|
| clean-baseline | 0.0 | 0.0 | 0.0 | 1.3 | 2.0 |
| sql-injection | 1 | 1 | 1 | 1 | 9 |

### `gamma` — overall F1 = 0.5

| Fixture | Precision | Recall | F1 | Avg findings | Avg latency (s) |
|---------|-----------|--------|----|--------------|-----------------|
| clean-baseline | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| sql-injection | 0.333 | 0.5 | 0.4 | 3.0 | 20.12 |

### `delta` — overall F1 = 0.0

| Fixture | Precision | Recall | F1 | Avg findings | Avg latency (s) |
|---------|-----------|--------|----|--------------|-----------------|

## Agreement matrix (Jaccard on finding locations)

> Values close to 1.0 indicate reviewers find nearly the same issues. Pairs above 0.85 are candidates for demotion (one becomes a fallback/custom).

| | `alpha` | `beta` | `delta` | `gamma` |
|---|---|---|---|---|
| `alpha` | 1.00 | 0.90 | 0.00 | 0.50 |
| `beta` | 0.90 | 1.00 | 0.00 | 0.50 |
| `delta` | 0.00 | 0.00 | 0.00 | 0.00 |
| `gamma` | 0.50 | 0.50 | 0.00 | 1.00 |

### Redundancy suggestions (≥ 0.85 agreement)

- `alpha` ↔ `beta`: 0.90 — consider demoting the lower-F1 reviewer to custom/fallback.
