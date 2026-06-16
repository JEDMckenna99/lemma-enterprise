# Delivery Prototype Outline

Full product outline for the local-first delivery custody prototype and field metrics logger. See plan sections 1–12 in the project plan for thesis, metrics targets, and weekly build order.

## Apps

1. **Prototype demo** — fake routes/packages, cloud-check vs local-first, offline queue, audit chain
2. **Field metrics** — delay logging without sensitive data, CSV export

## Safety

- `DELIVERY_PROTOTYPE_FAKE_DATA_ONLY=1` (default)
- No customer names, addresses, tracking numbers, photos, or GPS points in metrics
- Separate SQLite database under `data/delivery_prototype.db`

## Weekly milestones

| Week | Focus |
|------|-------|
| 1 | Field metrics logger |
| 2 | Fake route + QR generation |
| 3 | Cloud vs local scan modes |
| 4 | Signed events + offline sync |
| 5 | Audit dashboard + benchmark |

## Benchmark targets

See [docs/BENCHMARK_TARGETS.md](docs/BENCHMARK_TARGETS.md).
