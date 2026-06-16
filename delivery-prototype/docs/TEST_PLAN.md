# Test Plan

## Automated

```powershell
cd delivery-prototype
pytest -q
```

| Test file | Coverage |
|-----------|----------|
| `test_crypto_issuer.py` | Route credential signing |
| `test_crypto_verifier.py` | Route/device/package validation |
| `test_event_chain.py` | Hash chain + tamper rejection |
| `test_sync_api.py` | Event ingest + idempotency |
| `test_cloud_sim.py` | Network profiles |
| `test_audit_chain.py` | Custody chain happy path |
| `test_metrics_model.py` | Metrics schema + aggregation |
| `test_benchmark_harness.py` | CLI benchmark functions |

## Manual smoke

1. Create route with 20 packages; open QR sheet
2. Driver: download bundle for route
3. Local-first scan with network **Offline** — completes under 1s
4. Cloud-check with **Weak** — slower than local-first
5. Queue 3 offline events; sync from queue page
6. Audit page shows green custody chain
7. Metrics: log 5 delay events; export CSV; confirm no sensitive columns

## Benchmark CLI

```powershell
python scripts/run_benchmark.py --iterations 10 --profiles good,weak,offline
```

Results saved to `data/benchmark_results/` and SQLite.
