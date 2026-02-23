#!/usr/bin/env python3
"""
Automate a Sentry alert-routing drill.

This script:
1) Sends a unique drill event to Sentry via DSN.
2) Polls Sentry API for the resulting issue.
3) Writes a timestamped evidence markdown file.

Environment variables (or CLI args) required:
- SENTRY_DSN
- SENTRY_AUTH_TOKEN
- SENTRY_ORG
- SENTRY_PROJECT
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests
try:
    import sentry_sdk
except ImportError:  # pragma: no cover
    sentry_sdk = None


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(ts: dt.datetime) -> str:
    return ts.astimezone(dt.timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a Sentry alert-routing drill")
    parser.add_argument("--output-dir", default="docs/launch-evidence")
    parser.add_argument("--sentry-dsn", default=os.getenv("SENTRY_DSN", ""))
    parser.add_argument("--sentry-auth-token", default=os.getenv("SENTRY_AUTH_TOKEN", ""))
    parser.add_argument("--sentry-org", default=os.getenv("SENTRY_ORG", ""))
    parser.add_argument("--sentry-project", default=os.getenv("SENTRY_PROJECT", ""))
    parser.add_argument("--sentry-base-url", default=os.getenv("SENTRY_BASE_URL", "https://sentry.io"))
    parser.add_argument("--poll-timeout-seconds", type=int, default=180)
    parser.add_argument("--poll-interval-seconds", type=int, default=5)
    parser.add_argument("--app-label", default="lemma-enterprise")
    return parser.parse_args()


def require(value: str, name: str) -> str:
    if not value:
        raise ValueError(f"Missing required value: {name}")
    return value


def sentry_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def poll_issue(
    base_url: str,
    token: str,
    org: str,
    project: str,
    query: str,
    timeout_seconds: int,
    interval_seconds: int,
) -> Optional[Dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds
    url = f"{base_url.rstrip('/')}/api/0/projects/{org}/{project}/issues/"
    params = {"query": query}
    headers = sentry_headers(token)

    while time.monotonic() < deadline:
        resp = requests.get(url, headers=headers, params=params, timeout=20)
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Sentry API query failed: status={resp.status_code} body={resp.text[:500]}"
            )
        payload = resp.json()
        if isinstance(payload, list) and payload:
            return payload[0]
        time.sleep(interval_seconds)
    return None


def main() -> int:
    args = parse_args()

    if sentry_sdk is None:
        print(
            "ERROR: Missing dependency 'sentry_sdk'. Install requirements first: "
            "pip install -r requirements.txt"
        )
        return 2

    try:
        dsn = require(args.sentry_dsn, "SENTRY_DSN / --sentry-dsn")
        token = require(args.sentry_auth_token, "SENTRY_AUTH_TOKEN / --sentry-auth-token")
        org = require(args.sentry_org, "SENTRY_ORG / --sentry-org")
        project = require(args.sentry_project, "SENTRY_PROJECT / --sentry-project")
    except ValueError as exc:
        print(f"ERROR: {exc}")
        print(
            "Set required variables and retry: SENTRY_DSN, SENTRY_AUTH_TOKEN, "
            "SENTRY_ORG, SENTRY_PROJECT"
        )
        return 2

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stamp = utc_now().strftime("%Y-%m-%d-%H%M%S")
    drill_id = f"sentry-routing-drill-{stamp}"
    drill_message = f"INCIDENT_DRILL_ROUTING_TEST {drill_id}"

    sentry_sdk.init(dsn=dsn, traces_sample_rate=0.0)

    trigger_time = utc_now()
    sentry_sdk.capture_message(drill_message, level="error")
    sentry_sdk.flush(timeout=10)

    found_issue = poll_issue(
        base_url=args.sentry_base_url,
        token=token,
        org=org,
        project=project,
        query=drill_id,
        timeout_seconds=args.poll_timeout_seconds,
        interval_seconds=args.poll_interval_seconds,
    )
    detect_time = utc_now()

    if not found_issue:
        print("ERROR: Drill event not discovered as a Sentry issue within timeout.")
        return 1

    mttd_seconds = int(round((detect_time - trigger_time).total_seconds()))
    evidence_path = out_dir / f"{stamp}-incident-alert-routing-test.md"

    issue_id = str(found_issue.get("id", "unknown"))
    issue_title = str(found_issue.get("title", "unknown"))
    issue_permalink = str(found_issue.get("permalink", ""))
    issue_first_seen = str(found_issue.get("firstSeen", ""))

    evidence = f"""# Incident Alert Routing Test

- Drill ID: {drill_id}
- Date (UTC): {iso(utc_now())}
- Alert source: Sentry
- App label: {args.app_label}
- Sentry org/project: {org}/{project}
- Trigger method: scripted `capture_message` drill event
- T0 trigger: {iso(trigger_time)}
- T1 issue discovered: {iso(detect_time)}
- Routing latency (system-detection): {mttd_seconds}s
- Sentry issue id: {issue_id}
- Sentry issue title: {issue_title}
- Sentry issue firstSeen: {issue_first_seen}
- Sentry issue permalink: {issue_permalink}

## Delivery / Escalation Verification (Manual)

- First notification recipient(s): __________
- Notification channel(s): Email / Slack / PagerDuty / Other
- T2 first delivery observed (UTC): __________
- T3 acknowledged (UTC): __________
- Escalation policy result: PASS / FAIL

## Raw Issue Payload

```json
{json.dumps(found_issue, indent=2)}
```
"""

    evidence_path.write_text(evidence, encoding="utf-8")

    print("Sentry routing drill completed.")
    print(f"Drill ID: {drill_id}")
    print(f"System-detection latency: {mttd_seconds}s")
    print(f"Evidence: {evidence_path.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
