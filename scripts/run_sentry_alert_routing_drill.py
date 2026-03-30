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
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests
try:
    import sentry_sdk
except ImportError:  # pragma: no cover
    sentry_sdk = None


class SentryRateLimitedError(RuntimeError):
    """Raised when Sentry indicates API or ingestion rate limiting."""


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(ts: dt.datetime) -> str:
    return ts.astimezone(dt.timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a Sentry alert-routing drill")
    parser.add_argument("--output-dir", default="ops/evidence/launch")
    parser.add_argument("--sentry-dsn", default=os.getenv("SENTRY_DSN", ""))
    parser.add_argument("--sentry-auth-token", default=os.getenv("SENTRY_AUTH_TOKEN", ""))
    parser.add_argument("--sentry-org", default=os.getenv("SENTRY_ORG", ""))
    parser.add_argument("--sentry-project", default=os.getenv("SENTRY_PROJECT", ""))
    parser.add_argument("--sentry-base-url", default=os.getenv("SENTRY_BASE_URL", "https://sentry.io"))
    parser.add_argument("--poll-timeout-seconds", type=int, default=180)
    parser.add_argument("--poll-interval-seconds", type=int, default=5)
    parser.add_argument("--app-label", default="lemma-enterprise")
    parser.add_argument("--debug", action="store_true", help="Print diagnostic identifiers on failure")
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


def get_json_with_retry(
    url: str,
    headers: Dict[str, str],
    params: Dict[str, str],
    timeout_seconds: int = 20,
    attempts: int = 4,
) -> Any:
    last_exc: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=timeout_seconds)
            if resp.status_code == 429 or resp.headers.get("x-sentry-rate-limits"):
                raise SentryRateLimitedError(
                    "Sentry API rate-limited this request. "
                    f"status={resp.status_code} "
                    f"x-sentry-rate-limits={resp.headers.get('x-sentry-rate-limits', '')}"
                )
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"Sentry API query failed: status={resp.status_code} body={resp.text[:500]}"
                )
            return resp.json()
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            last_exc = exc
            if attempt == attempts:
                break
            sleep_s = min(8.0, 1.2 * attempt) + random.uniform(0.0, 0.6)
            time.sleep(sleep_s)
    raise RuntimeError(f"Sentry API request failed after retries: {last_exc}")


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
        payload = get_json_with_retry(url=url, headers=headers, params=params)
        if isinstance(payload, list) and payload:
            return payload[0]
        time.sleep(interval_seconds)
    return None


def poll_event(
    base_url: str,
    token: str,
    org: str,
    project: str,
    query: str,
    timeout_seconds: int,
    interval_seconds: int,
) -> Optional[Dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds
    url = f"{base_url.rstrip('/')}/api/0/projects/{org}/{project}/events/"
    params = {"query": query}
    headers = sentry_headers(token)

    while time.monotonic() < deadline:
        payload = get_json_with_retry(url=url, headers=headers, params=params)
        if isinstance(payload, list) and payload:
            return payload[0]
        time.sleep(interval_seconds)
    return None


def poll_event_by_id(
    base_url: str,
    token: str,
    org: str,
    project: str,
    event_id: str,
    timeout_seconds: int,
    interval_seconds: int,
) -> Optional[Dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds
    url = f"{base_url.rstrip('/')}/api/0/projects/{org}/{project}/events/{event_id}/"
    headers = sentry_headers(token)

    while time.monotonic() < deadline:
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code == 429 or resp.headers.get("x-sentry-rate-limits"):
            raise SentryRateLimitedError(
                "Sentry API rate-limited event lookup. "
                f"status={resp.status_code} "
                f"x-sentry-rate-limits={resp.headers.get('x-sentry-rate-limits', '')}"
            )
        if resp.status_code == 404:
            time.sleep(interval_seconds)
            continue
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Sentry API event-by-id query failed: status={resp.status_code} body={resp.text[:500]}"
            )
        payload = resp.json()
        if isinstance(payload, dict) and payload:
            return payload
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
    event_id = sentry_sdk.capture_message(drill_message, level="error")
    sentry_sdk.flush(timeout=10)

    try:
        found_payload = poll_event_by_id(
            base_url=args.sentry_base_url,
            token=token,
            org=org,
            project=project,
            event_id=event_id,
            timeout_seconds=args.poll_timeout_seconds,
            interval_seconds=args.poll_interval_seconds,
        )
        detect_time = utc_now()
        payload_type = "event_by_id"

        if not found_payload:
            found_payload = poll_issue(
                base_url=args.sentry_base_url,
                token=token,
                org=org,
                project=project,
                query=f'message:"{drill_id}"',
                timeout_seconds=args.poll_timeout_seconds,
                interval_seconds=args.poll_interval_seconds,
            )
            detect_time = utc_now()
            payload_type = "issue_search"

        if not found_payload:
            found_payload = poll_event(
                base_url=args.sentry_base_url,
                token=token,
                org=org,
                project=project,
                query=f"message:{drill_id}",
                timeout_seconds=args.poll_timeout_seconds,
                interval_seconds=args.poll_interval_seconds,
            )
            detect_time = utc_now()
            payload_type = "event_search"
    except SentryRateLimitedError as exc:
        print(f"ERROR: {exc}")
        if args.debug:
            print(f"DEBUG: drill_id={drill_id}")
            print(f"DEBUG: event_id={event_id}")
            print(f"DEBUG: sentry_org={org}")
            print(f"DEBUG: sentry_project={project}")
        print(
            "Sentry is rate-limiting this drill. Check project/org quota and dropped events, "
            "then rerun after limits reset."
        )
        return 3

    if not found_payload:
        print("ERROR: Drill event not discovered as Sentry issue or event within timeout.")
        if args.debug:
            print(f"DEBUG: drill_id={drill_id}")
            print(f"DEBUG: event_id={event_id}")
            print(f"DEBUG: sentry_org={org}")
            print(f"DEBUG: sentry_project={project}")
        return 1

    mttd_seconds = int(round((detect_time - trigger_time).total_seconds()))
    evidence_path = out_dir / f"{stamp}-incident-alert-routing-test.md"

    issue_id = str(found_payload.get("id", "unknown"))
    issue_title = str(found_payload.get("title", "unknown"))
    issue_permalink = str(found_payload.get("permalink", ""))
    issue_first_seen = str(found_payload.get("firstSeen", found_payload.get("dateCreated", "")))

    evidence = f"""# Incident Alert Routing Test

- Drill ID: {drill_id}
- Date (UTC): {iso(utc_now())}
- Alert source: Sentry
- App label: {args.app_label}
- Sentry org/project: {org}/{project}
- Trigger method: scripted `capture_message` drill event
- Detection source type: {payload_type}
- Event ID: {event_id}
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
{json.dumps(found_payload, indent=2)}
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
