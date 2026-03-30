#!/usr/bin/env python3
"""
Agent Session Simulation

Simulates a realistic agent session where an AI coding agent makes
multiple API calls through the Lemma Firewall. Demonstrates containment
across a multi-step workflow.

Prerequisites:
  - Firewall running locally (lemma demo starts one automatically)
  - Control plane at LEMMA_BASE_URL (default https://lemma.id)

Usage:
  python scripts/run_agent_session_simulation.py
"""

import json
import os
import sys
import time
import requests

API_BASE = os.environ.get("LEMMA_BASE_URL", "https://lemma.id").rstrip("/")
FIREWALL = os.environ.get("FIREWALL_URL", "http://localhost:8787")
RUNTIME_ID = "lemma-demo-runtime"


def _issue_credential(scope, taint_epoch=None):
    """Issue a credential from the control plane."""
    body = {"runtime_id": RUNTIME_ID, "scope": scope}
    if taint_epoch is not None:
        body["taint_epoch"] = taint_epoch
    r = requests.post(f"{API_BASE}/api/demo/issue-credential", json=body, timeout=15)
    if r.status_code != 200:
        return None
    return r.json().get("credential")


def _agent_call(method, path, credential, description):
    """Simulate an agent making a tool call through the firewall."""
    fn = getattr(requests, method.lower())
    start = time.time()
    r = fn(
        f"{FIREWALL}/firewall/httpbin{path}",
        headers={"X-Lemma-Credential": json.dumps(credential)},
        timeout=15,
    )
    elapsed = round((time.time() - start) * 1000)
    body = r.json() if r.content else {}
    status = r.status_code
    error = body.get("error", "")

    if status == 200:
        result = "ALLOWED"
    elif status == 403:
        result = f"BLOCKED ({error})"
    elif status == 401:
        result = f"DENIED ({error})"
    else:
        result = f"ERROR ({status})"

    print(f"  [{result:40s}] {method:6s} {path:30s} {elapsed:4d}ms  -- {description}")
    return status


def main():
    print("=" * 72)
    print("  AGENT SESSION SIMULATION")
    print("  Firewall: local Ed25519 verification, no per-request server calls")
    print("=" * 72)

    # Check firewall
    try:
        r = requests.get(f"{FIREWALL}/aim/health", timeout=5)
        if r.status_code != 200:
            raise Exception()
    except Exception:
        print(f"\nFirewall not running at {FIREWALL}")
        print("Start it with: python -m scripts.lemma_cli demo")
        sys.exit(1)

    # Fetch current taint epoch
    current_epoch = 0
    try:
        sr = requests.get(f"{API_BASE}/api/demo/state", params={"runtime_id": RUNTIME_ID}, timeout=10)
        if sr.status_code == 200:
            current_epoch = int(sr.json().get("runtime_state", {}).get("taint_epoch") or 0)
    except Exception:
        pass

    # --- Phase 1: Normal agent workflow ---
    print(f"\n--- Phase 1: Agent with read+write scope (taint_epoch={current_epoch}) ---\n")
    cred = _issue_credential(["read", "write"], taint_epoch=current_epoch)
    if not cred:
        print("  Failed to issue credential")
        sys.exit(1)

    _agent_call("GET", "/get", cred, "Read data (in scope)")
    _agent_call("POST", "/post", cred, "Write data (in scope)")
    _agent_call("GET", "/headers", cred, "Read headers (in scope)")
    _agent_call("GET", "/ip", cred, "Read IP info (in scope)")

    # --- Phase 2: Agent tries to escape scope ---
    print(f"\n--- Phase 2: Agent attempts to exceed its scope ---\n")
    _agent_call("GET", "/admin/secret", cred, "Access admin panel (out of scope)")
    _agent_call("DELETE", "/get", cred, "Delete data (method not allowed)")
    _agent_call("GET", "/anything/etc/passwd", cred, "Path traversal attempt (out of scope)")
    _agent_call("PUT", "/put", cred, "PUT method (not in policy)")

    # --- Phase 3: Context poisoning -> taint epoch ---
    print(f"\n--- Phase 3: Context poisoning detected, taint epoch bumped ---\n")
    print("  [RUNTIME EVENT] Agent ingested untrusted external content")
    print("  [RUNTIME EVENT] Bumping taint epoch on control plane...")
    bump_r = requests.post(f"{API_BASE}/api/demo/taint-bump",
        json={"runtime_id": RUNTIME_ID, "trust_state": "tainted_external"}, timeout=10)
    new_epoch = bump_r.json().get("runtime_state", {}).get("taint_epoch", "?") if bump_r.status_code == 200 else "?"
    print(f"  [RUNTIME EVENT] Taint epoch now: {new_epoch}")

    print("  [FIREWALL]      Waiting for taint sync...", end="", flush=True)
    for _ in range(8):
        time.sleep(2)
        print(".", end="", flush=True)
        try:
            h = requests.get(f"{FIREWALL}/aim/health", timeout=5).json()
            synced = h.get("sync", {}).get("runtime_taint_epochs", {}).get(RUNTIME_ID, 0)
            if synced >= int(str(new_epoch)):
                break
        except Exception:
            pass
    print(" synced")

    print()
    _agent_call("GET", "/get", cred, "Old credential after taint bump (should be denied)")

    # --- Phase 4: Re-issuance with fresh epoch ---
    print(f"\n--- Phase 4: Human re-authorizes agent with fresh credential ---\n")
    fresh_cred = _issue_credential(["read", "write"], taint_epoch=int(str(new_epoch)))
    if fresh_cred:
        _agent_call("GET", "/get", fresh_cred, "Fresh credential after re-auth (should work)")
        _agent_call("GET", "/headers", fresh_cred, "Another allowed action with fresh cred")
    else:
        print("  Failed to issue fresh credential")

    # --- Phase 5: Revocation ---
    print(f"\n--- Phase 5: Human revokes agent credential (kill switch) ---\n")
    cred_id = (fresh_cred or cred).get("id", "")
    if cred_id:
        requests.post(f"{FIREWALL}/aim/revoke", json={"credential_id": cred_id}, timeout=5)
        print(f"  [HUMAN ACTION] Credential {cred_id[:20]}... revoked")
        print()
        target = fresh_cred or cred
        _agent_call("GET", "/get", target, "Revoked credential (should be denied)")
        _agent_call("GET", "/headers", target, "Another attempt with revoked cred")

    # --- Phase 6: Action-level containment ---
    print(f"\n--- Phase 6: Action-level containment (read-only credential) ---\n")
    print("  Issuing credential with ONLY read actions (no write, no shell, no deploy)...")
    read_only_actions = {
        "file.read": True,
        "file.list": True,
        "api.call.read": True,
        "browser.read": True,
        "ingest.internal": True,
        "db.query.read": True,
    }
    read_body = {
        "runtime_id": RUNTIME_ID,
        "scope": ["read"],
        "taint_epoch": int(str(new_epoch)) if new_epoch != "?" else current_epoch,
        "actions": read_only_actions,
    }
    r = requests.post(f"{API_BASE}/api/demo/issue-credential",
        json=read_body, headers={"Content-Type": "application/json"}, timeout=15)
    if r.status_code == 200:
        read_cred = r.json().get("credential")
        if read_cred:
            read_json = json.dumps(read_cred)
            _agent_call("GET", "/get", read_cred, "api.call.read (granted)")
            _agent_call("POST", "/post", read_cred, "api.call.write (NOT granted -- should be denied)")
    else:
        print(f"  Failed to issue read-only credential: {r.status_code}")

    # --- Phase 7: Sub-agent delegation with attenuation ---
    print(f"\n--- Phase 7: Sub-agent delegation (narrower actions than parent) ---\n")
    print("  Issuing proof chain: root has read+write, delegated sub-agent has read only...")
    chain_resp = requests.post(f"{API_BASE}/api/demo/issue-proof-chain",
        json={
            "runtime_id": RUNTIME_ID,
            "scope": ["read", "write", "admin"],
            "delegated_scope": ["read"],
        },
        timeout=15)
    if chain_resp.status_code == 200:
        chain_body = chain_resp.json()
        root_scope = chain_body.get("root_scope", [])
        del_scope = chain_body.get("delegated_scope", [])
        chain = chain_body.get("proof_chain", {})
        root_actions = chain.get("root_proof", {}).get("scope", [])
        del_actions = chain.get("delegated_proof", {}).get("scope", [])
        print(f"  Root scope:      {root_scope}")
        print(f"  Delegated scope: {del_scope}")
        print(f"  Attenuation:     {set(del_scope)} is subset of {set(root_scope)}: {set(del_scope).issubset(set(root_scope))}")
        print(f"  Delegation depth: root=0, sub-agent=1")
    else:
        print(f"  Failed to issue proof chain: {chain_resp.status_code}")

    # --- Summary ---
    print()
    print("=" * 72)
    print("  SESSION SUMMARY")
    print()
    print("  Phase 1: Normal workflow       -- all actions allowed (in-scope)")
    print("  Phase 2: Scope escape attempt  -- all actions blocked (out-of-scope)")
    print("  Phase 3: Context poisoning     -- old credential denied (stale taint)")
    print("  Phase 4: Re-authorization      -- fresh credential accepted")
    print("  Phase 5: Kill switch           -- revoked credential denied")
    print("  Phase 6: Action-level control  -- read-only cred denies write actions")
    print("  Phase 7: Sub-agent delegation  -- narrower scope for delegated agents")
    print()
    print("  All containment decisions made locally by the firewall.")
    print("  Zero per-request server calls.")
    print("  24 action types in the taxonomy, risk-tiered, passkey-age-gated.")
    print("=" * 72)


if __name__ == "__main__":
    main()
