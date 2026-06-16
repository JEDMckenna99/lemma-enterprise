# Benchmark Targets

Reference targets from prototype spec (section 8). Used for comparison, not hard CI gates initially.

## Cloud-check under weak network

| Metric | Target |
|--------|--------|
| Avg scan-to-complete | ~5.8 sec |
| 95th percentile | ~12.4 sec |
| Retry rate | ~14% |

## Local-first

| Metric | Target |
|--------|--------|
| Avg scan-to-complete | ~0.4 sec |
| 95th percentile | ~0.8 sec |
| Scan-time retry rate | 0% |
| Queued event sync success | 100% |
| Tampered event rejection | 100% |

## Delay bucket midpoints (field metrics)

| Bucket | Estimate |
|--------|---------:|
| 0–2 sec | 1 sec |
| 3–5 sec | 4 sec |
| 6–10 sec | 8 sec |
| 10–20 sec | 15 sec |
| 20+ sec | 25 sec |
| Failed/retry | 20 sec |
