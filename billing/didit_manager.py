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
import os
import time
from typing import Any, Dict, Optional

import requests

from api.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

# Maximum allowed clock skew between X-Timestamp and now (didit spec: 300s).
WEBHOOK_MAX_SKEW_SECONDS = 300
_SESSION_TIMEOUT_SECONDS = 15

_didit_breaker = CircuitBreaker(
    "didit",
    failure_threshold=int(os.getenv("LEMMA_DIDIT_CIRCUIT_FAILURES", "5")),
    recovery_seconds=float(os.getenv("LEMMA_DIDIT_CIRCUIT_RECOVERY_SECONDS", "60")),
)


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

        if not _didit_breaker.allow():
            logger.warning("Didit circuit open — refusing session create")
            return {"success": False, "error": "didit_circuit_open"}

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
            _didit_breaker.record_failure()
            logger.error("Didit session request failed: %s", exc)
            return {"success": False, "error": "didit_request_failed", "message": str(exc)}

        if resp.status_code not in (200, 201):
            _didit_breaker.record_failure()
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
            _didit_breaker.record_failure()
            logger.error("Didit session response missing fields: %s", data)
            return {"success": False, "error": "didit_response_incomplete"}

        _didit_breaker.record_success()
        logger.info("Created didit session %s", session_id)
        return {
            "success": True,
            "session_id": session_id,
            "url": hosted_url,
            "status": data.get("status"),
        }

    def retrieve_session_decision(self, session_id: str) -> Dict[str, Any]:
        """Fetch a session's decision payload directly from didit (pull fallback).

        The webhook is the fast path for issuance, but webhook delivery is
        outside our control (provider drops/delays, transient misconfig). This
        lets the status-poll endpoint actively pull the authenticated decision so
        a user who completed IDV is never stranded without a credential just
        because a webhook never landed. Returns ``{"success": bool, ...}``; the
        ``decision`` field mirrors the shape the webhook delivers so it can feed
        the same ``_complete_verified_ishuman_from_didit`` issuance path.

        Docs: https://docs.didit.me/identity-verification/api-reference/retrieve-session
        """
        if not self.enabled:
            return {"success": False, "error": "didit_not_configured"}
        if not session_id:
            return {"success": False, "error": "session_id required"}

        if not _didit_breaker.allow():
            logger.warning("Didit circuit open — refusing decision fetch")
            return {"success": False, "error": "didit_circuit_open"}

        url = f"{self.api_base}/v3/session/{session_id}/decision/"
        try:
            resp = requests.get(
                url,
                headers={
                    "accept": "application/json",
                    "x-api-key": self.api_key,
                },
                timeout=_SESSION_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            _didit_breaker.record_failure()
            logger.error("Didit decision fetch failed: %s", exc)
            return {"success": False, "error": "didit_request_failed", "message": str(exc)}

        if resp.status_code != 200:
            _didit_breaker.record_failure()
            logger.warning(
                "Didit decision fetch non-200: %s %s", resp.status_code, resp.text[:300]
            )
            return {"success": False, "error": "didit_decision_unavailable",
                    "status_code": resp.status_code}

        _didit_breaker.record_success()
        decision = resp.json() if resp.content else {}
        status = str(decision.get("status") or "").strip().lower()
        return {"success": True, "status": status, "decision": decision}

    @staticmethod
    def _delete_response_success(resp: requests.Response) -> bool:
        """True when Didit accepted a session delete (or it is already gone)."""
        if resp.status_code in (200, 202, 204):
            return True
        if resp.status_code != 404:
            return False
        # HTML 404 means we hit the wrong route, not "session already deleted".
        content_type = (resp.headers.get("content-type") or "").lower()
        body = (resp.text or "").strip()
        if "text/html" in content_type or body.startswith("<!"):
            return False
        return True

    def _delete_session_paths(self, session_id: str) -> list[str]:
        import os

        override = (os.environ.get("DIDIT_DELETE_PATH_TEMPLATE") or "").strip()
        if override:
            return [override]
        return (
            "/v3/session/{session_id}/delete/",
            "/v3/session/{session_id}/",
        )

    def delete_session(self, session_id: str) -> Dict[str, Any]:
        """Delete (purge) a verification session from didit.

        Implements didit's "process-and-purge" data-minimization pattern: once
        Lemma has issued the credential, the upstream IDV session (document
        image, liveness, decision) is no longer needed and is removed from
        didit. This is a soft delete on didit's side (sets ``deleted_at`` and
        immediately hides the session and its feature records from the list and
        decision endpoints); the row is hard-deleted once didit's configured
        retention window expires.

        Idempotent: ``204 No Content`` (deleted) and genuine API ``404`` (already
        gone) are treated as success. HTML ``404`` responses are *not* success —
        they indicate the wrong delete route was used.

        Never raises; the caller treats any failure as non-fatal so issuance is
        never coupled to upstream purge availability.

        Docs: https://docs.didit.me/sessions-api/delete-session
        (``DELETE /v3/session/{session_id}/delete/``).
        """
        if not self.enabled:
            return {"success": False, "error": "didit_not_configured"}
        if not session_id:
            return {"success": False, "error": "session_id required"}

        headers = {
            "accept": "application/json",
            "x-api-key": self.api_key,
        }
        last_failure: Dict[str, Any] = {"success": False, "error": "didit_delete_failed"}

        for path_template in self._delete_session_paths(session_id):
            url = f"{self.api_base}{path_template.format(session_id=session_id)}"
            try:
                resp = requests.delete(url, headers=headers, timeout=_SESSION_TIMEOUT_SECONDS)
            except requests.RequestException as exc:
                logger.error("Didit session delete failed: %s", exc)
                return {"success": False, "error": "didit_request_failed", "message": str(exc)}

            if self._delete_response_success(resp):
                logger.info(
                    "Didit session delete ok: session=%s path=%s status=%s",
                    session_id, path_template, resp.status_code,
                )
                return {"success": True, "status_code": resp.status_code, "path": path_template}

            last_failure = {
                "success": False,
                "error": "didit_delete_failed",
                "status_code": resp.status_code,
                "path": path_template,
            }
            logger.warning(
                "Didit session delete attempt failed: session=%s path=%s status=%s body=%s",
                session_id, path_template, resp.status_code, resp.text[:200],
            )

        return last_failure

    def delete_user(self, vendor_data: str) -> Dict[str, Any]:
        """Delete a Didit user entity keyed by ``vendor_data`` (our wallet id).

        Session delete removes the verification session; user delete clears the
        consolidated user record (including portrait/document history shown in
        the Didit console). Best-effort and idempotent.
        """
        if not self.enabled:
            return {"success": False, "error": "didit_not_configured"}
        vendor = (vendor_data or "").strip()
        if not vendor:
            return {"success": False, "error": "vendor_data required"}

        url = f"{self.api_base}/v3/users/delete/"
        try:
            resp = requests.post(
                url,
                json={"vendor_data_list": [vendor]},
                headers={
                    "Content-Type": "application/json",
                    "accept": "application/json",
                    "x-api-key": self.api_key,
                },
                timeout=_SESSION_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            logger.error("Didit user delete failed: %s", exc)
            return {"success": False, "error": "didit_request_failed", "message": str(exc)}

        if resp.status_code in (200, 202, 204):
            logger.info("Didit user delete ok: vendor_data=%s status=%s", vendor, resp.status_code)
            return {"success": True, "status_code": resp.status_code}

        if resp.status_code == 404:
            body = (resp.text or "").strip()
            if not body.startswith("<!"):
                return {"success": True, "status_code": resp.status_code}

        logger.warning(
            "Didit user delete non-success: vendor=%s status=%s body=%s",
            vendor, resp.status_code, resp.text[:300],
        )
        return {
            "success": False,
            "error": "didit_user_delete_failed",
            "status_code": resp.status_code,
        }

    def purge_verification_data(
        self,
        session_id: str,
        *,
        vendor_data: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Delete session artifacts and the consolidated Didit user record."""
        session_result = self.delete_session(session_id)
        if not session_result.get("success"):
            return session_result
        if not vendor_data:
            return session_result
        user_result = self.delete_user(vendor_data)
        if not user_result.get("success"):
            return {
                "success": False,
                "error": user_result.get("error", "didit_user_delete_failed"),
                "session": session_result,
                "user": user_result,
            }
        return {
            "success": True,
            "session": session_result,
            "user": user_result,
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
