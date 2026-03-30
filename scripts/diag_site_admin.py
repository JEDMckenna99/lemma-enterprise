#!/usr/bin/env python3
"""
Diagnose Lemma site-admin visibility for AIM.

Checks:
1) Calls /api/developer/sites with X-Lemma-PPID + X-API-Key
2) Prints raw returned site fields
3) Applies AIM normalization/matching logic locally

Usage (PowerShell):
  $env:LEMMA_BASE_URL='https://lemma.id'
  $env:LEMMA_API_KEY='...'
  $env:LEMMA_PPID='did:lemma:ppid_...'
  $env:LEMMA_SITE_ID='agent_intelligence_monitor_271aa2e09a7a_herokuapp_com'
  python scripts/diag_site_admin.py
"""

import json
import os
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


def normalize_site_key(value: str) -> str:
    v = str(value or '').strip().lower()
    if v.startswith('https://'):
        v = v[len('https://'):]
    elif v.startswith('http://'):
        v = v[len('http://'):]
    if v.endswith('/'):
        v = v[:-1]

    out = []
    prev_us = False
    for ch in v:
        if ('a' <= ch <= 'z') or ('0' <= ch <= '9'):
            out.append(ch)
            prev_us = False
        else:
            if not prev_us:
                out.append('_')
                prev_us = True
    return ''.join(out).strip('_')


def main():
    base = (os.getenv('LEMMA_BASE_URL') or 'https://lemma.id').rstrip('/')
    api_key = os.getenv('LEMMA_API_KEY')
    ppid = os.getenv('LEMMA_PPID')
    site_id = os.getenv('LEMMA_SITE_ID')

    missing = [k for k, v in {
        'LEMMA_API_KEY': api_key,
        'LEMMA_PPID': ppid,
        'LEMMA_SITE_ID': site_id,
    }.items() if not v]

    if missing:
        print('Missing required env vars:', ', '.join(missing))
        sys.exit(2)

    url = f"{base}/api/developer/sites"
    headers = {
        'X-Lemma-PPID': ppid,
        'X-API-Key': api_key,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }

    req = Request(url, headers=headers, method='GET')
    try:
        with urlopen(req, timeout=20) as resp:
            raw = resp.read().decode('utf-8', errors='replace')
            status = resp.status
    except HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        print(f"HTTP {e.code} from {url}")
        print(body)
        sys.exit(1)
    except URLError as e:
        print(f"Network error: {e}")
        sys.exit(1)

    print(f"HTTP {status} from {url}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print('Non-JSON response:')
        print(raw[:2000])
        sys.exit(1)

    success = data.get('success')
    sites = data.get('sites') or []
    print(f"success={success} sites_count={len(sites)}")

    target_norm = normalize_site_key(site_id)
    print(f"\nTarget site: {site_id}")
    print(f"Target normalized: {target_norm}\n")

    matched = False
    for i, s in enumerate(sites, start=1):
        candidates = [
            s.get('site_id'),
            s.get('id'),
            s.get('siteId'),
            s.get('site_domain'),
            s.get('domain'),
            s.get('hostname'),
            s.get('url'),
        ]
        candidates = [c for c in candidates if c]
        norms = [normalize_site_key(c) for c in candidates]
        row_match = target_norm in norms
        if row_match:
            matched = True

        print(f"[{i}] name={s.get('name')}")
        print(f"    raw_candidates={candidates}")
        print(f"    normalized={norms}")
        print(f"    match={row_match}")

    print('\nRESULT:')
    if matched:
        print('MATCH_FOUND (AIM should pass site admin check)')
        sys.exit(0)
    else:
        print('NO_MATCH (AIM will return not_site_admin)')
        sys.exit(3)


if __name__ == '__main__':
    main()
