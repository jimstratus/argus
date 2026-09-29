# Benchmark model attribution

For `benchmark.py` and `stats.py` model-attribution changes, record the model slug only when a route produced output, persist it with benchmark rows, and test stale/unverified model flags against parsed `stats.py --format json` output from a seeded history database.
