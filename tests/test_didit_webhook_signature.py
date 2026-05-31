"""Unit tests for didit webhook X-Signature-V2 verification.

Verifies the canonicalization (sortKeys + shortenFloats + compact JSON) and the
fail-closed behavior on bad signature, stale timestamp, and missing headers.
"""

from __future__ import annotations

import json
import time

import pytest

from billing.didit_manager import (
    DiditWebhookError,
    canonical_webhook_json,
    compute_v2_signature,
    verify_webhook,
)

SECRET = "whsec_didit_test_secret"


def _signed(body: dict, *, ts: int | None = None):
    """Return (raw_bytes, signature, timestamp) for a body as didit would send."""
    # The raw bytes a server transmits need not be canonical; V2 is parser
    # tolerant and we verify over the re-encoded parsed body. Use a deliberately
    # non-canonical encoding (spaces, unsorted) to prove tolerance.
    raw = json.dumps(body, separators=(", ", ": "), sort_keys=False).encode("utf-8")
    ts = ts if ts is not None else int(time.time())
    sig = compute_v2_signature(body, SECRET)
    return raw, sig, str(ts)


@pytest.mark.unit
def test_valid_signature_passes_despite_noncanonical_raw():
    body = {"webhook_type": "status.updated", "status": "Approved", "session_id": "s1", "score": 95.0}
    raw, sig, ts = _signed(body)
    parsed = verify_webhook(raw, x_signature_v2=sig, x_timestamp=ts, secret=SECRET)
    assert parsed["status"] == "Approved"


@pytest.mark.unit
def test_shorten_floats_canonicalization():
    # 95.0 must canonicalize to 95 (integral float -> int); 95.4 stays.
    assert canonical_webhook_json({"a": 95.0}) == b'{"a":95}'
    assert canonical_webhook_json({"a": 95.4}) == b'{"a":95.4}'
    # sortKeys recursive + unicode unescaped.
    assert canonical_webhook_json({"b": {"z": 1, "a": 2}, "a": "ñ"}) == \
        '{"a":"ñ","b":{"a":2,"z":1}}'.encode("utf-8")


@pytest.mark.unit
def test_unicode_payload_round_trip():
    body = {"webhook_type": "status.updated", "status": "Approved", "name": "Jané Doé ñ", "session_id": "s2"}
    raw, sig, ts = _signed(body)
    parsed = verify_webhook(raw, x_signature_v2=sig, x_timestamp=ts, secret=SECRET)
    assert parsed["name"] == "Jané Doé ñ"


@pytest.mark.unit
def test_tampered_body_fails():
    body = {"status": "Declined", "session_id": "s3"}
    raw, sig, ts = _signed(body)
    tampered = json.dumps({"status": "Approved", "session_id": "s3"}).encode("utf-8")
    with pytest.raises(DiditWebhookError):
        verify_webhook(tampered, x_signature_v2=sig, x_timestamp=ts, secret=SECRET)


@pytest.mark.unit
def test_stale_timestamp_fails():
    body = {"status": "Approved", "session_id": "s4"}
    raw, sig, _ = _signed(body)
    old_ts = str(int(time.time()) - 1000)
    with pytest.raises(DiditWebhookError):
        verify_webhook(raw, x_signature_v2=sig, x_timestamp=old_ts, secret=SECRET)


@pytest.mark.unit
def test_missing_headers_fail():
    body = {"status": "Approved"}
    raw, sig, ts = _signed(body)
    with pytest.raises(DiditWebhookError):
        verify_webhook(raw, x_signature_v2=None, x_timestamp=ts, secret=SECRET)
    with pytest.raises(DiditWebhookError):
        verify_webhook(raw, x_signature_v2=sig, x_timestamp=None, secret=SECRET)


@pytest.mark.unit
def test_missing_secret_fails():
    body = {"status": "Approved"}
    raw, sig, ts = _signed(body)
    with pytest.raises(DiditWebhookError):
        verify_webhook(raw, x_signature_v2=sig, x_timestamp=ts, secret="")
