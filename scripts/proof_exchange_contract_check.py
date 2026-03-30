#!/usr/bin/env python3
"""
Proof exchange contract checks for production/staging.

Modes:
- Baseline mode (default): verifies endpoint guardrails and invalid proof rejection.
- Positive mode: when a trusted proof fixture is provided, verifies:
    proof -> access token -> protected endpoint call.

Environment variables:
  LEMMA_BASE_URL                  Default: https://lemma.id
  LEMMA_PROOF_FIXTURE_JSON        Optional JSON string credential fixture
  LEMMA_PROOF_FIXTURE_PATH        Optional file path to credential fixture JSON
  LEMMA_EXCHANGE_SITE_ID          Optional requested site_id for exchange
  LEMMA_EXCHANGE_SCOPE            Optional requested_scope (csv or single value)
  LEMMA_STRICT_POSITIVE           "1" to fail if positive fixture is missing
  LEMMA_PLATFORM_API_KEY          Optional API key for introspect/revoke cycle
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
import base64
from typing import Any


BASE_URL = os.environ.get("LEMMA_BASE_URL", "https://lemma.id").rstrip("/")


def _request(
    url: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, str]:
    payload = None
    req_headers = {"User-Agent": "lemma-proof-exchange-check/1.0"}
    if headers:
        req_headers.update(headers)
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        req_headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url=url, method=method, data=payload, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.getcode(), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8", errors="replace")


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _parse_json(content: str) -> dict[str, Any]:
    if not content:
        return {}
    return json.loads(content)


def _encode_lemma_header(lemma: dict[str, Any]) -> str:
    raw = json.dumps(lemma, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _load_fixture() -> dict[str, Any] | None:
    raw = os.environ.get("LEMMA_PROOF_FIXTURE_JSON", "").strip()
    path = os.environ.get("LEMMA_PROOF_FIXTURE_PATH", "").strip()

    if raw:
        try:
            fixture = json.loads(raw)
            if isinstance(fixture, dict):
                return fixture
        except Exception:
            return None

    if path:
        try:
            with open(path, "r", encoding="utf-8") as f:
                fixture = json.load(f)
            if isinstance(fixture, dict):
                return fixture
        except Exception:
            return None

    return None


def _run_baseline_checks() -> None:
    print(f"Running baseline proof-exchange checks against: {BASE_URL}")

    exchange_url = f"{BASE_URL}/api/auth/exchange-proof"
    status, content = _request(exchange_url, method="POST", body={})
    print(f"POST {exchange_url} (missing credential) -> {status}")
    _assert(status == 400, f"Expected 400 for missing credential, got {status}")

    invalid_credential = {
        "issuer": "did:lemma:fake",
        "claims": {"siteId": "lemma.id", "scope": ["read"]},
        "proof": {"signatureValue": "deadbeef"},
    }
    status, content = _request(exchange_url, method="POST", body={"credential": invalid_credential})
    print(f"POST {exchange_url} (invalid credential) -> {status}")
    _assert(status == 401, f"Expected 401 for invalid proof, got {status}")


def _run_positive_check(fixture: dict[str, Any]) -> dict[str, Any]:
    exchange_url = f"{BASE_URL}/api/auth/exchange-proof"
    requested_site = os.environ.get("LEMMA_EXCHANGE_SITE_ID", "").strip()
    requested_scope = os.environ.get("LEMMA_EXCHANGE_SCOPE", "").strip()

    exchange_body: dict[str, Any] = {"credential": fixture}
    if requested_site:
        exchange_body["site_id"] = requested_site
    if requested_scope:
        exchange_body["requested_scope"] = requested_scope

    status, content = _request(exchange_url, method="POST", body=exchange_body)
    print(f"POST {exchange_url} (trusted fixture) -> {status}")
    _assert(status == 200, f"Expected 200 for trusted fixture exchange, got {status}")

    payload = _parse_json(content)
    token = payload.get("access_token", "")
    _assert(token.startswith("lm_at_"), "Expected lm_at_ access token prefix")
    print(f"  token_type={payload.get('token_type')} expires_in={payload.get('expires_in')}")

    protected_url = f"{BASE_URL}/api/billing/usage/cus_test"
    lemma_header = _encode_lemma_header(fixture)
    status, _content = _request(
        protected_url,
        method="GET",
        headers={"X-Lemma-Credential": lemma_header},
    )
    print(f"GET {protected_url} (lemma header) -> {status}")
    _assert(status == 200, f"Expected 200 from protected endpoint with lemma header, got {status}")

    status, content = _request(
        protected_url,
        method="GET",
        headers={"Authorization": f"Bearer {token}"},
    )
    print(f"GET {protected_url} (bearer access token) -> {status}")
    expected_bearer_runtime = os.environ.get("LEMMA_EXPECT_BEARER_RUNTIME", "").strip()
    if expected_bearer_runtime == "1":
        _assert(status == 200, f"Expected 200 from protected endpoint with exchanged token, got {status}")
    elif expected_bearer_runtime == "0":
        _assert(status == 401, f"Expected 401 from protected endpoint in VC-only runtime mode, got {status}")

    protected_payload = _parse_json(content)
    if status == 200:
        _assert(protected_payload.get("success") is True, "Protected endpoint success != true")
    print("Positive flow passed: proof -> token + VC/header authorization checks")
    return payload


def _run_control_plane_cycle(token: str, site_id: str, api_key: str, refresh_token: str = "") -> None:
    if not api_key:
        print("Control-plane cycle skipped: set LEMMA_PLATFORM_API_KEY to test introspect/revoke.")
        return

    headers = {"X-API-Key": api_key}
    current_token = token
    expected_bearer_runtime = os.environ.get("LEMMA_EXPECT_BEARER_RUNTIME", "").strip()

    if refresh_token:
        refresh_url = f"{BASE_URL}/api/auth/refresh"
        status, content = _request(
            refresh_url,
            method="POST",
            body={"refresh_token": refresh_token, "site_id": site_id},
        )
        print(f"POST {refresh_url} -> {status}")
        _assert(status == 200, f"Expected 200 from refresh endpoint, got {status}")
        refresh_payload = _parse_json(content)
        _assert(refresh_payload.get("success") is True, "Refresh success != true")
        new_access = refresh_payload.get("access_token", "")
        new_refresh = refresh_payload.get("refresh_token", "")
        _assert(new_access.startswith("lm_at_"), "Refresh did not return lm_at_ access token")
        _assert(new_refresh.startswith("lm_rt_"), "Refresh did not rotate lm_rt_ refresh token")

        protected_url = f"{BASE_URL}/api/billing/usage/cus_test"
        status, content = _request(
            protected_url,
            method="GET",
            headers={"Authorization": f"Bearer {new_access}"},
        )
        print(f"GET {protected_url} (refreshed token) -> {status}")
        if expected_bearer_runtime == "1":
            _assert(status == 200, f"Expected 200 from protected endpoint with refreshed token, got {status}")
        elif expected_bearer_runtime == "0":
            _assert(status == 401, f"Expected 401 from protected endpoint in VC-only runtime mode, got {status}")

        # Old refresh token should be invalid after rotation.
        status, content = _request(
            refresh_url,
            method="POST",
            body={"refresh_token": refresh_token, "site_id": site_id},
        )
        print(f"POST {refresh_url} (old refresh token) -> {status}")
        _assert(status == 401, f"Expected 401 from old refresh token, got {status}")
        current_token = new_access

    introspect_url = f"{BASE_URL}/api/auth/introspect"
    status, content = _request(
        introspect_url,
        method="POST",
        body={"token": current_token, "site_id": site_id},
        headers=headers,
    )
    print(f"POST {introspect_url} (before revoke) -> {status}")
    _assert(status == 200, f"Expected 200 from introspect before revoke, got {status}")
    intro_payload = _parse_json(content).get("introspection", {})
    _assert(intro_payload.get("active") is True, "Expected active token before revoke")

    revoke_url = f"{BASE_URL}/api/auth/revoke"
    status, content = _request(
        revoke_url,
        method="POST",
        body={"token": current_token, "reason": "proof_exchange_contract_check"},
        headers=headers,
    )
    print(f"POST {revoke_url} -> {status}")
    _assert(status == 200, f"Expected 200 from revoke endpoint, got {status}")
    revoke_payload = _parse_json(content)
    _assert(revoke_payload.get("success") is True, "Revoke endpoint success != true")
    _assert(revoke_payload.get("revoked") is True, "Revoke endpoint revoked != true")

    status, content = _request(
        introspect_url,
        method="POST",
        body={"token": current_token, "site_id": site_id},
        headers=headers,
    )
    print(f"POST {introspect_url} (after revoke) -> {status}")
    _assert(status == 200, f"Expected 200 from introspect after revoke, got {status}")
    intro_payload = _parse_json(content).get("introspection", {})
    _assert(intro_payload.get("active") is False, "Expected inactive token after revoke")
    _assert(intro_payload.get("error") == "token_revoked", "Expected token_revoked after revoke")

    protected_url = f"{BASE_URL}/api/billing/usage/cus_test"
    status, content = _request(
        protected_url,
        method="GET",
        headers={"Authorization": f"Bearer {current_token}"},
    )
    print(f"GET {protected_url} (revoked token) -> {status}")
    _assert(status == 401, f"Expected 401 from protected endpoint after revoke, got {status}")
    print("Control-plane cycle passed: introspect -> revoke -> enforcement")


def main() -> int:
    _run_baseline_checks()

    fixture = _load_fixture()
    strict_positive = os.environ.get("LEMMA_STRICT_POSITIVE", "0") == "1"

    if not fixture:
        message = (
            "Positive check skipped: set LEMMA_PROOF_FIXTURE_JSON or "
            "LEMMA_PROOF_FIXTURE_PATH with a trusted proof fixture."
        )
        if strict_positive:
            raise AssertionError(message)
        print(message)
        print("Baseline checks passed.")
        return 0

    exchange_payload = _run_positive_check(fixture)
    token = exchange_payload.get("access_token", "")
    refresh_token = exchange_payload.get("refresh_token", "")
    site_id = (exchange_payload.get("site_id") or os.environ.get("LEMMA_EXCHANGE_SITE_ID") or "").strip().lower()
    api_key = os.environ.get("LEMMA_PLATFORM_API_KEY", "").strip()
    _run_control_plane_cycle(token, site_id, api_key, refresh_token=refresh_token)
    print("All proof-exchange checks passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Proof exchange checks failed: {exc}", file=sys.stderr)
        raise SystemExit(1)

