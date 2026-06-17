#!/usr/bin/env python3
"""Internal metrics: offline VC verification speed + package audit chain."""

from __future__ import annotations

import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crypto.device_keys import ensure_device_keypair, ensure_issuer_keypair, load_public_key_b64
from crypto.issuer import build_fake_packages, issue_route_credential
from crypto.verifier import (
    sign_delivery_event,
    verify_delivery_event,
    verify_package_against_route,
    verify_package_assignment,
    verify_route_credential,
)
from models.schemas import new_event_id

ITERATIONS = 100
HEROKU_BASE = "https://lemma-delivery-prototype-c5afc69633cb.herokuapp.com"


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, min(len(s) - 1, int(round((p / 100) * (len(s) - 1)))))
    return s[idx]


def stats(times: list[float]) -> dict:
    return {
        "n": len(times),
        "avg_ms": round(statistics.mean(times) * 1000, 3),
        "median_ms": round(statistics.median(times) * 1000, 3),
        "p95_ms": round(percentile(times, 95) * 1000, 3),
        "min_ms": round(min(times) * 1000, 3),
        "max_ms": round(max(times) * 1000, 3),
    }


def bench_local_verification() -> dict:
    issuer = ensure_issuer_keypair(ROOT / "data" / "keys" / "issuer_private.pem")
    device = ensure_device_keypair(ROOT / "data" / "keys" / "device_private.pem")
    packages = build_fake_packages(
        issuer, "R-METRICS", ["S-014", "S-015"], 10,
        {"photo_required": True, "signature_required": False, "otp_required": False},
    )
    credential = issue_route_credential(
        issuer,
        route_id="R-METRICS",
        driver_id="D-1",
        device_id="DEVICE-001",
        device_pubkey=load_public_key_b64(device),
        stops=["S-014", "S-015"],
        packages=[
            {"package_id": p["package_id"], "stop_id": p["stop_id"], "policy": p["policy"]}
            for p in packages
        ],
        policy_defaults={"photo_required": True, "signature_required": False, "otp_required": False},
    )
    assignment = packages[0]["assignment"]

    route_times, pkg_times, full_times, sign_times, verify_event_times = [], [], [], [], []
    prior = None
    for i in range(ITERATIONS):
        t0 = time.perf_counter()
        verify_route_credential(credential, device_id="DEVICE-001")
        route_times.append(time.perf_counter() - t0)

        t0 = time.perf_counter()
        verify_package_assignment(assignment)
        pkg_times.append(time.perf_counter() - t0)

        t0 = time.perf_counter()
        verify_route_credential(credential, device_id="DEVICE-001")
        verify_package_against_route(assignment, credential)
        full_times.append(time.perf_counter() - t0)

        unsigned = {
            "event_id": new_event_id(),
            "event_type": "DELIVERED",
            "package_id": packages[i % len(packages)]["package_id"],
            "route_id": "R-METRICS",
            "stop_id": packages[i % len(packages)]["stop_id"],
            "timestamp": "2026-06-16T12:00:00Z",
            "gps_precision_bucket": "within_50m",
            "proof": {"photo_hash": "fake", "requirements_met": True},
            "device_id": "DEVICE-001",
        }
        t0 = time.perf_counter()
        event = sign_delivery_event(unsigned, device, credential, prior)
        sign_times.append(time.perf_counter() - t0)

        t0 = time.perf_counter()
        verify_delivery_event(event, route_credential=credential, prior_event=prior)
        verify_event_times.append(time.perf_counter() - t0)
        prior = event

    return {
        "iterations": ITERATIONS,
        "offline_route_credential_verify": stats(route_times),
        "offline_package_assignment_verify": stats(pkg_times),
        "offline_full_scan_verify": stats(full_times),
        "offline_delivery_event_sign": stats(sign_times),
        "offline_delivery_event_verify": stats(verify_event_times),
    }


def bench_auditability() -> dict:
    issuer = ensure_issuer_keypair(ROOT / "data" / "keys" / "issuer_private.pem")
    device = ensure_device_keypair(ROOT / "data" / "keys" / "device_private.pem")
    packages = build_fake_packages(
        issuer, "R-AUDIT", ["S-014"], 5,
        {"photo_required": True, "signature_required": False, "otp_required": False},
    )
    credential = issue_route_credential(
        issuer,
        route_id="R-AUDIT",
        driver_id="D-1",
        device_id="DEVICE-001",
        device_pubkey=load_public_key_b64(device),
        stops=["S-014"],
        packages=[
            {"package_id": p["package_id"], "stop_id": p["stop_id"], "policy": p["policy"]}
            for p in packages
        ],
        policy_defaults={"photo_required": True, "signature_required": False, "otp_required": False},
    )

    events = []
    prior = None
    for pkg in packages:
        event = sign_delivery_event(
            {
                "event_id": new_event_id(),
                "event_type": "DELIVERED",
                "package_id": pkg["package_id"],
                "route_id": "R-AUDIT",
                "stop_id": pkg["stop_id"],
                "timestamp": "2026-06-16T12:00:00Z",
                "gps_precision_bucket": "within_50m",
                "proof": {"photo_hash": "fake", "requirements_met": True},
                "device_id": "DEVICE-001",
            },
            device,
            credential,
            prior,
        )
        events.append(event)
        prior = event

    chain_checks = []
    audit_times = []
    prior = None
    for event in events:
        t0 = time.perf_counter()
        ok, reason = verify_delivery_event(event, route_credential=credential, prior_event=prior)
        audit_times.append(time.perf_counter() - t0)
        chain_checks.append({"event_id": event["event_id"], "valid": ok, "reason": reason})
        prior = event

    tamper_cases = []
    base = events[0]
    tampered_sig = dict(base)
    tampered_sig["proof"] = {"photo_hash": "tampered", "requirements_met": True}
    ok, reason = verify_delivery_event(tampered_sig, route_credential=credential)
    tamper_cases.append({"case": "mutate_after_sign", "rejected": not ok, "reason": reason})

    broken_chain = dict(events[1])
    broken_chain["previous_event_hash"] = "bad"
    ok, reason = verify_delivery_event(broken_chain, route_credential=credential, prior_event=events[0])
    tamper_cases.append({"case": "broken_previous_hash", "rejected": not ok, "reason": reason})

    wrong_route = dict(base)
    wrong_route["route_id"] = "R-EVIL"
    ok, reason = verify_delivery_event(wrong_route, route_credential=credential)
    tamper_cases.append({"case": "wrong_route_id", "rejected": not ok, "reason": reason})

    return {
        "packages_in_route": len(packages),
        "delivery_events_chained": len(events),
        "chain_valid_rate": round(
            sum(1 for c in chain_checks if c["valid"]) / len(chain_checks) * 100, 1
        ),
        "per_event_audit_verify": stats(audit_times),
        "custody_steps": [
            {"step": "route_credential_valid", "ok": verify_route_credential(credential)[0]},
            {"step": "all_package_assignments_valid", "ok": all(
                verify_package_assignment(p["assignment"])[0] for p in packages
            )},
            {"step": "all_events_signature_valid", "ok": all(c["valid"] for c in chain_checks)},
            {"step": "hash_chain_intact", "ok": all(c["valid"] for c in chain_checks)},
        ],
        "tamper_rejection": tamper_cases,
        "tamper_rejection_rate": round(
            sum(1 for t in tamper_cases if t["rejected"]) / len(tamper_cases) * 100, 1
        ),
    }


def bench_heroku(base: str) -> dict:
    result = {"base": base, "reachable": False}
    try:
        with urllib.request.urlopen(base + "/health", timeout=15) as r:
            result["health"] = json.loads(r.read())
            result["reachable"] = r.status == 200
    except Exception as exc:
        result["error"] = str(exc)
        return result

    t0 = time.perf_counter()
    body = json.dumps({
        "route_id": "R-LIVE-METRICS",
        "package_count": 5,
        "stops": ["S-014"],
    }).encode()
    req = urllib.request.Request(
        base + "/api/routes", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        route_data = json.loads(r.read())
    result["create_route_ms"] = round((time.perf_counter() - t0) * 1000, 1)

    with urllib.request.urlopen(base + "/api/routes/R-LIVE-METRICS/bundle", timeout=15) as r:
        bundle = json.loads(r.read())

    device = ensure_device_keypair(ROOT / "data" / "keys" / "device_private.pem")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    device = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(bundle["device_private_key_hex"]))
    cred = bundle["route_credential"]
    pkg = bundle["packages"][0]
    event = sign_delivery_event(
        {
            "event_id": new_event_id(),
            "event_type": "DELIVERED",
            "package_id": pkg["package_id"],
            "route_id": cred["route_id"],
            "stop_id": pkg["stop_id"],
            "timestamp": "2026-06-16T12:00:00Z",
            "gps_precision_bucket": "within_50m",
            "proof": {"photo_hash": "fake", "requirements_met": True},
            "device_id": cred["device_id"],
        },
        device,
        cred,
        None,
    )

    t0 = time.perf_counter()
    sync_body = json.dumps({"route_id": "R-LIVE-METRICS", "events": [event]}).encode()
    sync_req = urllib.request.Request(
        base + "/api/sync/events", data=sync_body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(sync_req, timeout=15) as r:
        sync = json.loads(r.read())
    result["sync_event_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    result["sync_status"] = sync

    t0 = time.perf_counter()
    with urllib.request.urlopen(base + "/api/audit/chain/R-LIVE-METRICS", timeout=15) as r:
        audit = json.loads(r.read())
    result["audit_chain_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    result["audit_tamper_free"] = audit.get("tamper_free")
    result["audit_steps"] = len(audit.get("steps", []))
    result["audit_step_summary"] = [
        {"step": s["step"], "valid": s["valid"]} for s in audit.get("steps", [])
    ]
    return result


def main() -> None:
    report = {
        "offline_vc_verification_speed": bench_local_verification(),
        "package_vc_auditability": bench_auditability(),
        "heroku_live": bench_heroku(HEROKU_BASE),
    }
    out = ROOT / "data" / "internal_vc_metrics.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
