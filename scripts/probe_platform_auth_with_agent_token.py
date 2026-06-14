#!/usr/bin/env python3
"""
Probe protected platform routes with an agent delegation token.

Usage:
  export LEMMA_AGENT_TOKEN=lm_agent_...
  python scripts/probe_platform_auth_with_agent_token.py
  python scripts/probe_platform_auth_with_agent_token.py --base-url https://lemma.id --token lm_agent_...
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Callable

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@dataclass(frozen=True)
class ProbeRoute:
    name: str
    method: str
    path: str
    json_body: dict | None = None
    expect_status: Callable[[int], bool] | None = None


DEFAULT_ROUTES = [
    ProbeRoute("health", "GET", "/health", expect_status=lambda s: s == 200),
    ProbeRoute("health_detailed", "GET", "/api/health/detailed", expect_status=lambda s: s in {200, 503}),
    ProbeRoute("developer_stats", "GET", "/api/developer/stats", expect_status=lambda s: s == 200),
    ProbeRoute("developer_sites", "GET", "/api/developer/sites", expect_status=lambda s: s == 200),
    ProbeRoute("admin_trust_queue", "GET", "/api/admin/trust/queue", expect_status=lambda s: s == 200),
    ProbeRoute("admin_trust_blocks", "GET", "/api/admin/trust/blocks", expect_status=lambda s: s == 200),
    ProbeRoute("customer_api_keys", "GET", "/api/customer/api-keys", expect_status=lambda s: s == 200),
    ProbeRoute("customer_sites", "GET", "/api/customer/sites", expect_status=lambda s: s == 200),
    ProbeRoute("audit_logs", "GET", "/api/v1/audit/logs?site_id=lemma.id&limit=1", expect_status=lambda s: s in {200, 404}),
    ProbeRoute("site_binding_check", "GET", "/api/ishuman/site-binding-check?hostname=lemma.id", expect_status=lambda s: s == 200),
    ProbeRoute("agent_credentials_list", "GET", "/api/agent/credentials", expect_status=lambda s: s in {200, 403}),
]


def _probe(base: str, token: str, route: ProbeRoute) -> dict:
    url = f"{base.rstrip('/')}{route.path}"
    headers = {"X-Agent-Token": token, "Accept": "application/json"}
    if route.method == "GET":
        resp = requests.get(url, headers=headers, timeout=30)
    else:
        resp = requests.request(
            route.method,
            url,
            headers={**headers, "Content-Type": "application/json"},
            json=route.json_body or {},
            timeout=30,
        )
    ok = route.expect_status(resp.status_code) if route.expect_status else resp.ok
    detail = ""
    try:
        body = resp.json()
        detail = json.dumps(body)[:180]
    except Exception:
        detail = (resp.text or "")[:180]
    return {
        "name": route.name,
        "method": route.method,
        "path": route.path,
        "status": resp.status_code,
        "ok": ok,
        "detail": detail,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe platform auth with agent token")
    parser.add_argument("--base-url", default=os.getenv("ISHUMAN_LIVE_BASE_URL", "http://127.0.0.1:5000"))
    parser.add_argument("--token", default=os.getenv("LEMMA_AGENT_TOKEN", ""))
    args = parser.parse_args()

    token = (args.token or "").strip()
    if not token.startswith("lm_agent_"):
        print("Set LEMMA_AGENT_TOKEN or pass --token lm_agent_...", file=sys.stderr)
        return 2

    results = [_probe(args.base_url, token, route) for route in DEFAULT_ROUTES]
    passed = sum(1 for row in results if row["ok"])
    for row in results:
        status = "PASS" if row["ok"] else "FAIL"
        print(f"[{status}] {row['method']} {row['path']} -> {row['status']} {row['detail']}")
    print(f"\nSummary: {passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
