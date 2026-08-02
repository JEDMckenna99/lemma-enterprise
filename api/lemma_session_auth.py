"""
Sign in with lemma.id — for lemma.id itself.

lemma.id dogfoods its own product: a user's lemma.id signs a presentation
bound to this site (siteId ``lemma.id``), the server verifies it with the
exact same logic relying sites use, and only then mints an HttpOnly session.
That session is what opens the lemma.id manager at /app.

Hard rules honored here (AGENTS.md):
  * The session is minted ONLY from a server-verified signed presentation —
    never from a bare client-supplied ppid.
  * Fail closed: any verification failure leaves the session untouched.
  * Site binding key is the canonical hostname (``lemma.id``), never an
    internal ``site_...`` id.
"""

from __future__ import annotations

import logging
import os
import time

from flask import Blueprint, jsonify, request, session

logger = logging.getLogger(__name__)

lemma_session_bp = Blueprint("lemma_session", __name__)

SESSION_KEY = "lemma_signin"


def _expected_site_binding() -> str:
    """Canonical site binding this server accepts for its own sign-in.

    Production always binds to ``lemma.id``. Non-production environments bind
    to the request host (e.g. ``localhost`` in dev, the staging hostname on
    staging) so the dogfooded flow works everywhere.
    """
    if os.getenv("ENVIRONMENT", "").strip().lower() == "production":
        return "lemma.id"
    from api.site_hostname import normalize_runtime_site_binding

    return normalize_runtime_site_binding(request.host) or "lemma.id"


def current_signin_session() -> dict | None:
    """Return the verified sign-in session dict, or None."""
    data = session.get(SESSION_KEY)
    if not isinstance(data, dict) or not data.get("ppid"):
        return None
    return data


@lemma_session_bp.route("/api/auth/session", methods=["POST"])
def create_session():
    """Verify a signed presentation bound to this site and mint a session.

    Body: ``{"presentation": {credential, session_assertion, session_signature,
    session_nonce, bloom_sequence, ...}}`` — the object returned by the browser
    SDK's ``verifyForBackend()``.
    """
    body = request.get_json(silent=True) or {}
    presentation = body.get("presentation")
    if not isinstance(presentation, dict):
        return jsonify({"success": False, "error": "presentation_required"}), 400

    expected_site = _expected_site_binding()
    verify_body = {
        "site_id": expected_site,
        "required_assurance": "passkey",
        "credential": presentation.get("credential"),
        "session_assertion": presentation.get("session_assertion"),
        "session_signature": presentation.get("session_signature"),
        "session_nonce": presentation.get("session_nonce"),
        "bloom_sequence": presentation.get("bloom_sequence"),
    }

    try:
        from api.ishuman import verify_presentation_payload

        result, _status = verify_presentation_payload(verify_body)
    except Exception:  # noqa: BLE001 — fail closed on any verifier error
        logger.exception("Platform sign-in verification crashed")
        return jsonify({"success": False, "error": "verification_failed"}), 401

    if not result.get("success") or not result.get("ppid"):
        logger.info(
            "Platform sign-in rejected: %s", result.get("error", "unknown")
        )
        return (
            jsonify({
                "success": False,
                "error": result.get("error", "not_verified"),
            }),
            401,
        )

    session[SESSION_KEY] = {
        "ppid": result["ppid"],
        "assurance": result.get("assurance"),
        "signed_in_at": int(time.time()),
    }
    session.permanent = False

    return jsonify({
        "success": True,
        "ppid": result["ppid"],
        "assurance": result.get("assurance"),
    })


@lemma_session_bp.route("/api/auth/session", methods=["GET"])
def get_session():
    """Current sign-in state, used by the demo flow and the /app gate."""
    data = current_signin_session()
    if not data:
        return jsonify({"signed_in": False})
    return jsonify({
        "signed_in": True,
        "ppid": data.get("ppid"),
        "assurance": data.get("assurance"),
        "signed_in_at": data.get("signed_in_at"),
    })


@lemma_session_bp.route("/api/auth/session/logout", methods=["POST"])
def logout_session():
    """Clear the platform sign-in session (the demo's 'reset' is a logout)."""
    session.pop(SESSION_KEY, None)
    return jsonify({"success": True})
