#!/usr/bin/env python3
"""CLI benchmark: cloud-check vs local-first verification timing."""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import app
from config import BENCHMARK_DIR, CLOUD_DELAYS
from crypto.device_keys import ensure_device_keypair, ensure_issuer_keypair, load_public_key_b64
from crypto.issuer import build_fake_packages, issue_route_credential
from crypto.verifier import verify_package_against_route, verify_route_credential
from models.db import save_benchmark_run


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = max(0, min(len(values) - 1, int(round((p / 100) * (len(values) - 1)))))
    return values[idx]


def run_local(iterations: int) -> dict:
    issuer = ensure_issuer_keypair(ROOT / "data" / "keys" / "issuer_private.pem")
    device = ensure_device_keypair(ROOT / "data" / "keys" / "device_private.pem")
    packages = build_fake_packages(issuer, "R-BENCH", ["S-1", "S-2"], 5, {
        "photo_required": True,
        "signature_required": False,
        "otp_required": False,
    })
    credential = issue_route_credential(
        issuer,
        route_id="R-BENCH",
        driver_id="D-1",
        device_id="DEVICE-001",
        device_pubkey=load_public_key_b64(device),
        stops=["S-1", "S-2"],
        packages=[{"package_id": p["package_id"], "stop_id": p["stop_id"], "policy": p["policy"]} for p in packages],
        policy_defaults={"photo_required": True, "signature_required": False, "otp_required": False},
    )
    assignment = packages[0]["assignment"]
    times = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        verify_route_credential(credential)
        verify_package_against_route(assignment, credential)
        times.append(time.perf_counter() - t0)
    return {
        "mode": "local-first",
        "avg_sec": round(sum(times) / len(times), 4),
        "p95_sec": round(percentile(times, 95), 4),
        "failure_rate": 0.0,
    }


def run_cloud(iterations: int, profile: str) -> dict:
    client = app.test_client()
    times = []
    failures = 0
    for _ in range(iterations):
        t0 = time.perf_counter()
        res = client.post("/api/cloud/confirm", json={"package_id": "P-1001", "network_profile": profile})
        if res.status_code >= 400:
            failures += 1
        else:
            client.post("/api/cloud/deliver", json={"package_id": "P-1001", "network_profile": profile})
        times.append(time.perf_counter() - t0)
    return {
        "mode": "cloud-check",
        "network_profile": profile,
        "avg_sec": round(sum(times) / len(times), 4),
        "p95_sec": round(percentile(times, 95), 4),
        "failure_rate": round(failures / iterations, 4),
        "expected_delay_sec": CLOUD_DELAYS.get(profile),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--profiles", default="good,weak,offline")
    args = parser.parse_args()

    local = run_local(args.iterations)
    cloud_results = {}
    for profile in [p.strip() for p in args.profiles.split(",") if p.strip()]:
        cloud_results[profile] = run_cloud(args.iterations, profile)

    payload = {"local_first": local, "cloud_check": cloud_results, "iterations": args.iterations}
    BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)
    out = BENCHMARK_DIR / f"benchmark_{int(time.time())}.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    from config import DB_PATH

    save_benchmark_run(
        DB_PATH,
        f"BENCH-{uuid.uuid4().hex[:8].upper()}",
        "comparison",
        args.profiles,
        payload,
        _now(),
    )
    print(json.dumps(payload, indent=2))
    print(f"Saved to {out}")


if __name__ == "__main__":
    main()
