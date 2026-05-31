"""Didit IDV rail manager (Phase 3.2 second issuer).

Mirrors billing/stripe_manager.StripeManager for the parts the isHuman
issuance pipeline needs:

  * create_identity_verification_session() -> POST /v3/session/ (hosted flow)
  * verify_webhook() -> X-Signature-V2 HMAC-SHA256 verification of a raw body

Didit is the *upstream IDV verifier*; Lemma remains the sole credential issuer.
This manager never signs credentials. It only starts didit sessions and
authenticates didit webhook deliveries so the existing document-root pipeline
can consume the decision payload.

Docs: https://docs.didit.me/integration/api-full-flow and
https://docs.didit.me/integration/webhooks
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

# Maximum allowed clock skew between X-Timestamp and now (didit spec: 300s).
WEBHOOK_MAX_SKEW_SECONDS = 300
_SESSION_TIMEOUT_SECONDS = 15


class DiditWebhookError(Exception):
    """Raised when a didit webhook fails authentication or freshness checks."""


def _shorten_floats(value: Any) -> Any:
    """Recursively convert integral floats to ints (didit ``shortenFloats``).

    Didit canonicalizes whole-number floats (95.0 -> 95) before signing; mirror
    that so our recomputed HMAC matches X-Signature-V2.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return value
    if isinstance(value, dict):
        return {k: _shorten_floats(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_shorten_floats(v) for v in value]
    return value


def canonical_webhook_json(parsed_body: Any) -> bytes:
    """Reproduce didit's canonical JSON: sortKeys + shortenFloats + compact.

    json.dumps with sort_keys recursively orders keys; separators give compact
    output; ensure_ascii=False keeps unicode unescaped (didit default).
    """
    shortened = _shorten_floats(parsed_body)
    return json.dumps(
        shortened,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def compute_v2_signature(parsed_body: Any, secret: str) -> str:
    canonical = canonical_webhook_json(parsed_body)
    return hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()


def verify_webhook(
    raw_body: bytes,
    *,
    x_signature_v2: Optional[str],
    x_timestamp: Optional[str],
    secret: str,
    now: Optional[int] = None,
) -> Dict[str, Any]:
    """Verify a didit webhook delivery and return the parsed JSON body.

    Raises DiditWebhookError on any failure (missing headers, stale timestamp,
    bad signature). The signature is verified over the canonical re-encoding of
    the parsed body (X-Signature-V2 is parser-tolerant per didit's spec).
    """
    if not secret:
        raise DiditWebhookError("webhook secret not configured")
    if not x_signature_v2:
        raise DiditWebhookError("missing X-Signature-V2")
    if not x_timestamp:
        raise DiditWebhookError("missing X-Timestamp")

    try:
        ts = int(str(x_timestamp).strip())
    except (TypeError, ValueError) as exc:
        raise DiditWebhookError("invalid X-Timestamp") from exc

    current = int(now if now is not None else time.time())
    if abs(current - ts) > WEBHOOK_MAX_SKEW_SECONDS:
        raise DiditWebhookError("stale webhook timestamp")

    try:
        parsed = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DiditWebhookError("invalid JSON body") from exc

    expected = compute_v2_signature(parsed, secret)
    if not hmac.compare_digest(expected, str(x_signature_v2).strip()):
        raise DiditWebhookError("signature mismatch")

    return parsed


class DiditManager:
    """Manages didit verification sessions for the federated identity network."""

    def __init__(self):
        from api.config import (
            get_didit_api_base,
            get_didit_api_key,
            get_didit_webhook_secret,
            get_didit_workflow_id,
            is_ishuman_didit_enabled,
        )

        self.api_base = (get_didit_api_base() or "https://verification.didit.me").rstrip("/")
        self.api_key = get_didit_api_key()
        self.workflow_id = get_didit_workflow_id()
        self.webhook_secret = get_didit_webhook_secret()
        self.enabled = is_ishuman_didit_enabled()
        if self.enabled:
            logger.info("Didit IDV rail initialized")
        else:
            logger.info("Didit IDV rail disabled or not configured")

    def create_identity_verification_session(
        self,
        user_id: str,
        return_url: str,
        callback_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a didit session and return the hosted verification URL.

        ``user_id`` is echoed back as ``vendor_data`` for webhook correlation.
        ``return_url`` is where the user lands after verification (the popup),
        and ``callback_url`` (if given) is didit's server-to-server callback.
        """
        if not self.enabled:
            return {"success": False, "error": "didit_not_configured"}

        url = f"{self.api_base}/v3/session/"
        payload: Dict[str, Any] = {
            "workflow_id": self.workflow_id,
            "vendor_data": user_id,
            "callback": return_url,
        }
        if callback_url:
            payload["callback"] = callback_url
        try:
            resp = requests.post(
                url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": self.api_key,
                },
                timeout=_SESSION_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            logger.error("Didit session request failed: %s", exc)
            return {"success": False, "error": "didit_request_failed", "message": str(exc)}

        if resp.status_code not in (200, 201):
            logger.error("Didit session creation failed: %s %s", resp.status_code, resp.text[:500])
            return {
                "success": False,
                "error": "didit_session_failed",
                "status_code": resp.status_code,
            }

        data = resp.json() if resp.content else {}
        session_id = data.get("session_id") or data.get("id")
        hosted_url = data.get("url") or data.get("verification_url") or data.get("session_url")
        if not session_id or not hosted_url:
            logger.error("Didit session response missing fields: %s", data)
            return {"success": False, "error": "didit_response_incomplete"}

        logger.info("Created didit session %s", session_id)
        return {
            "success": True,
            "session_id": session_id,
            "url": hosted_url,
            "status": data.get("status"),
        }

    def verify_webhook(
        self,
        raw_body: bytes,
        *,
        x_signature_v2: Optional[str],
        x_timestamp: Optional[str],
    ) -> Dict[str, Any]:
        return verify_webhook(
            raw_body,
            x_signature_v2=x_signature_v2,
            x_timestamp=x_timestamp,
            secret=self.webhook_secret,
        )
