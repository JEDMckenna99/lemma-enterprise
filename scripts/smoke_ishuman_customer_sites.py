#!/usr/bin/env python3
"""Smoke-check isHuman customer demo sites (HTTP + SDK snippet)."""

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request

DEFAULT_SITES = {
    "tickets": {
        "url": "https://lemma-demo-tickets-1d3d7411af33.herokuapp.com",
        "site_id": "tickets-demo.lemma.id",
    },
    "trials": {
        "url": "https://lemma-demo-trials-7090f46cae0d.herokuapp.com",
        "site_id": "trials-demo.lemma.id",
    },
}

SDK_PATTERN = re.compile(r"ishuman-verifier\.js", re.I)
SITE_ID_PATTERN = re.compile(r"siteId\s*:\s*['\"]([^'\"]+)['\"]")
AUTO_PROVISION_PATTERN = re.compile(
    r"autoProvision\s*:\s*true|makeVerifier\s*\(\s*true\s*\)",
    re.I,
)


def fetch(url: str, timeout: int = 30) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "lemma-ishuman-demo-smoke/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return exc.code, body


def check_site(name: str, spec: dict) -> list[str]:
    errors: list[str] = []
    url = spec["url"]
    expected_site_id = spec["site_id"]

    status, body = fetch(url)
    if status != 200:
        errors.append(f"{name}: HTTP {status} for {url}")
        return errors

    if not SDK_PATTERN.search(body):
        errors.append(f"{name}: page missing ishuman-verifier.js reference ({url})")

    match = SITE_ID_PATTERN.search(body)
    if not match:
        errors.append(f"{name}: page missing IsHumanVerifier siteId binding ({url})")
    elif match.group(1) != expected_site_id:
        errors.append(
            f"{name}: siteId {match.group(1)!r} != expected {expected_site_id!r}"
        )

    if not AUTO_PROVISION_PATTERN.search(body):
        errors.append(f"{name}: page missing autoProvision: true ({url})")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    all_errors: list[str] = []
    for name, spec in DEFAULT_SITES.items():
        all_errors.extend(check_site(name, spec))

    if all_errors:
        print("FAIL — customer site smoke")
        for err in all_errors:
            print(f"  - {err}")
        return 1

    print("PASS — customer site smoke (tickets + trials)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
