#!/usr/bin/env python3
"""
Full Gap Test -- proves the remaining containment gaps:
1. Revocation via delta sync (not just local /aim/revoke)
2. Proof chain delegation with scope narrowing
3. Concurrent load test

Prerequisites: firewall running locally with simulation_policy.json
"""

import concurrent.futures
import json
import os
import sys
import time

import requests

API_BASE = os.environ.get("LEMMA_BASE_URL", "https://lemma.id").rstrip("/")
FIREWALL = os.environ.get("FIREWALL_URL", "http://localhost:8787")
RUNTIME_ID = "lemma-demo-runtime"


def _check_firewall():
    try:
        r = requests.get(f"{FIREWALL}/aim/health", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def _issue_credential(scope, taint_epoch=None):
    body = {"runtime_id": RUNTIME_ID, "scope": scope}
    if taint_epoch is not None:
        body["taint_epoch"] = taint_epoch
    r = requests.post(f"{API_BASE}/api/demo/issue-credential", json=body, timeout=15)
    if r.status_code == 200:
        return r.json().get("credential")
    return None


# ─── Test 1: Revocation via delta sync ───

def test_delta_revocation():
    print("=" * 60)
    print("TEST 1: Revocation via control plane delta sync")
    print("=" * 60)

    # Get current taint epoch
    current_epoch = 0
    try:
        sr = requests.get(f"{API_BASE}/api/demo/state", params={"runtime_id": RUNTIME_ID}, timeout=10)
        if sr.status_code == 200:
            current_epoch = int(sr.json().get("runtime_state", {}).get("taint_epoch") or 0)
    except Exception:
        pass

    cred = _issue_credential(["read", "write"], taint_epoch=current_epoch)
    if not cred:
        print("  FAIL: could not issue credential")
        return False

    cred_id = cred.get("id", "")
    cred_json = json.dumps(cred)

    # Verify credential works
    r = requests.get(f"{FIREWALL}/firewall/httpbin/get",
        headers={"X-Lemma-Credential": cred_json}, timeout=15)
    if r.status_code != 200:
        print(f"  FAIL: credential not accepted ({r.status_code})")
        return False
    print(f"  Credential works: {cred_id[:24]}...")

    # Revoke via control plane (writes to revocation_list DB)
    rev = requests.post(f"{API_BASE}/api/demo/revoke-credential",
        json={"credential_id": cred_id}, timeout=10)
    if rev.status_code != 200:
        print(f"  FAIL: revocation failed ({rev.status_code})")
        return False
    print(f"  Revoked on control plane: {cred_id[:24]}...")

    # Wait for firewall delta sync (5s interval in demo mode)
    print("  Waiting for delta sync...", end="", flush=True)
    denied = False
    for attempt in range(15):
        time.sleep(3)
        print(".", end="", flush=True)
        r = requests.get(f"{FIREWALL}/firewall/httpbin/get",
            headers={"X-Lemma-Credential": cred_json}, timeout=10)
        body = r.json() if r.content else {}
        if r.status_code == 401 and "revoked" in str(body.get("error", "")):
            denied = True
            break
    print()

    if denied:
        print(f"  PASS: revoked credential denied via delta sync (attempt {attempt + 1})")
        return True
    else:
        print(f"  FAIL: credential still accepted after 45s (sync may need more time)")
        return False


# ─── Test 2: Proof chain delegation ───

def test_proof_chain_delegation():
    print()
    print("=" * 60)
    print("TEST 2: Proof chain delegation with scope narrowing")
    print("=" * 60)

    # Issue a proof chain: root has read+write, delegated has only read
    r = requests.post(f"{API_BASE}/api/demo/issue-proof-chain",
        json={
            "runtime_id": RUNTIME_ID,
            "scope": ["read", "write", "admin"],
            "delegated_scope": ["read"],
        },
        timeout=15)

    if r.status_code != 200:
        print(f"  FAIL: proof chain issuance failed ({r.status_code} {r.text[:200]})")
        return False

    body = r.json()
    chain = body.get("proof_chain")
    root_scope = body.get("root_scope")
    delegated_scope = body.get("delegated_scope")
    print(f"  Chain issued: root_scope={root_scope}, delegated_scope={delegated_scope}")

    if not chain:
        print("  FAIL: no proof_chain in response")
        return False

    root = chain.get("root_proof", {})
    delegated = chain.get("delegated_proof", {})
    print(f"  Root proof: {root.get('proof_id', '?')[:20]}... scope={root.get('scope')}")
    print(f"  Delegated:  {delegated.get('proof_id', '?')[:20]}... scope={delegated.get('scope')}")
    print(f"  Delegation depth: root={root.get('delegation_depth')}, delegated={delegated.get('delegation_depth')}")

    # Verify scope attenuation
    root_scope_set = set(root.get("scope", []))
    delegated_scope_set = set(delegated.get("scope", []))
    attenuated = delegated_scope_set.issubset(root_scope_set)
    print(f"  Scope attenuated: {attenuated} ({delegated_scope_set} subset of {root_scope_set})")

    # Verify parent link
    parent_linked = delegated.get("parent_proof_id") == root.get("proof_id")
    print(f"  Parent linked: {parent_linked}")

    if attenuated and parent_linked:
        print("  PASS: proof chain has correct delegation structure")
        return True
    else:
        print("  FAIL: chain structure invalid")
        return False


# ─── Test 3: Concurrent load test ───

def test_concurrent_load():
    print()
    print("=" * 60)
    print("TEST 3: Concurrent load test")
    print("=" * 60)

    # Get current taint epoch
    current_epoch = 0
    try:
        sr = requests.get(f"{API_BASE}/api/demo/state", params={"runtime_id": RUNTIME_ID}, timeout=10)
        if sr.status_code == 200:
            current_epoch = int(sr.json().get("runtime_state", {}).get("taint_epoch") or 0)
    except Exception:
        pass

    cred = _issue_credential(["read", "write"], taint_epoch=current_epoch)
    if not cred:
        print("  FAIL: could not issue credential")
        return False

    cred_json = json.dumps(cred)
    num_requests = 50
    num_workers = 10

    def _make_request(i):
        start = time.time()
        try:
            r = requests.get(f"{FIREWALL}/firewall/httpbin/get",
                headers={"X-Lemma-Credential": cred_json}, timeout=15)
            elapsed = round((time.time() - start) * 1000)
            return {"i": i, "status": r.status_code, "elapsed_ms": elapsed}
        except Exception as e:
            elapsed = round((time.time() - start) * 1000)
            return {"i": i, "status": 0, "elapsed_ms": elapsed, "error": str(e)}

    print(f"  Sending {num_requests} concurrent requests ({num_workers} workers)...")
    start_all = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(_make_request, i) for i in range(num_requests)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    total_time = round((time.time() - start_all) * 1000)
    successes = sum(1 for r in results if r["status"] == 200)
    failures = sum(1 for r in results if r["status"] != 200)
    latencies = [r["elapsed_ms"] for r in results if r["status"] == 200]

    if latencies:
        avg_ms = round(sum(latencies) / len(latencies))
        p50 = sorted(latencies)[len(latencies) // 2]
        p95 = sorted(latencies)[int(len(latencies) * 0.95)]
        p99 = sorted(latencies)[int(len(latencies) * 0.99)]
        rps = round(successes / (total_time / 1000), 1)
    else:
        avg_ms = p50 = p95 = p99 = 0
        rps = 0

    print(f"  Results: {successes}/{num_requests} succeeded, {failures} failed")
    print(f"  Total time: {total_time}ms")
    print(f"  Throughput: {rps} requests/sec")
    print(f"  Latency: avg={avg_ms}ms  p50={p50}ms  p95={p95}ms  p99={p99}ms")

    if successes == num_requests:
        print("  PASS: all concurrent requests handled")
        return True
    elif successes >= num_requests * 0.95:
        print(f"  PASS (with {failures} errors): >95% success rate under load")
        return True
    else:
        print(f"  FAIL: too many failures under load")
        for r in results:
            if r["status"] != 200:
                print(f"    Request {r['i']}: status={r['status']} {r.get('error', '')}")
        return False


def main():
    if not _check_firewall():
        print(f"Firewall not running at {FIREWALL}")
        print("Start it: python -m scripts.lemma_cli demo --skip-firewall")
        sys.exit(1)

    results = {}
    results["delta_revocation"] = test_delta_revocation()
    results["proof_chain"] = test_proof_chain_delegation()
    results["concurrent_load"] = test_concurrent_load()

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {name:30s} {status}")

    total = len(results)
    passed = sum(1 for v in results.values() if v)
    print(f"\n  {passed}/{total} tests passed")

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
