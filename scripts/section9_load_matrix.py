"""Section 9 load matrix: bounded concurrent probes against key paths."""
from __future__ import annotations

import concurrent.futures
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ORIGIN = "https://lemma.id"
UA = "section9-load-matrix/1.0"
CONCURRENCY = 8
ROUNDS = 3


def _get(url: str) -> tuple[float, int]:
    started = time.perf_counter()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            resp.read()
            return (time.perf_counter() - started) * 1000.0, resp.status
    except urllib.error.HTTPError as exc:
        return (time.perf_counter() - started) * 1000.0, exc.code


def _post_json(url: str, payload: dict) -> tuple[float, int]:
    started = time.perf_counter()
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"User-Agent": UA, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            resp.read()
            return (time.perf_counter() - started) * 1000.0, resp.status
    except urllib.error.HTTPError as exc:
        return (time.perf_counter() - started) * 1000.0, exc.code


def _run_probe(name: str, fn, *, expect_status: int) -> dict:
    latencies: list[float] = []
    errors = 0
    for _ in range(ROUNDS * CONCURRENCY):
        with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
            futures = [pool.submit(fn) for _ in range(CONCURRENCY)]
            for fut in concurrent.futures.as_completed(futures):
                ms, status = fut.result()
                latencies.append(ms)
                if status != expect_status:
                    errors += 1
    latencies.sort()
    p50 = statistics.median(latencies) if latencies else None
    p95 = latencies[int(len(latencies) * 0.95) - 1] if latencies else None
    ok = errors == 0
    result = {
        "name": name,
        "ok": ok,
        "errors": errors,
        "samples": len(latencies),
        "p50_ms": round(p50, 1) if p50 is not None else None,
        "p95_ms": round(p95, 1) if p95 is not None else None,
        "expect_status": expect_status,
    }
    print(json.dumps(result))
    return result


def main() -> int:
    probes = [
        (
            "health-liveness",
            lambda: _get(f"{ORIGIN}/health"),
            200,
        ),
        (
            "ready",
            lambda: _get(f"{ORIGIN}/ready"),
            200,
        ),
        (
            "bloom-filter",
            lambda: _get(f"{ORIGIN}/api/revocation/bloom-filter"),
            200,
        ),
        (
            "recovery-reject-no-token",
            lambda: _post_json(f"{ORIGIN}/api/recovery/complete", {"token": "invalid"}),
            400,
        ),
        (
            "site-block-auth-fail",
            lambda: _get(f"{ORIGIN}/api/ishuman/site-block"),
            401,
        ),
    ]

    results = [_run_probe(name, fn, expect_status=status) for name, fn, status in probes]
    passed = sum(1 for r in results if r["ok"])
    print(f"\nsection9_load_matrix: {passed}/{len(results)} probes ok")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
