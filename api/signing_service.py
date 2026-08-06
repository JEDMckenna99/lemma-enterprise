"""HTTP signing service for the federated issuer (private worker only)."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from functools import wraps
from typing import Any, Callable

from flask import Blueprint, jsonify, request

signing_bp = Blueprint("signing_service", __name__)


def _expected_token() -> str:
    return os.getenv("LEMMA_SIGNING_SERVICE_TOKEN", "").strip()


def require_signing_token(view: Callable):
    @wraps(view)
    def wrapped(*args, **kwargs):
        token = _expected_token()
        if not token:
            return jsonify({"success": False, "error": "signing_token_unconfigured"}), 503
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {token}":
            return jsonify({"success": False, "error": "unauthorized"}), 401
        return view(*args, **kwargs)

    return wrapped


@signing_bp.route("/health", methods=["GET"])
def signing_health():
    return jsonify({"status": "healthy", "service": "lemma-signing"})


@signing_bp.route("/internal/issuer-info", methods=["POST"])
@require_signing_token
def issuer_info():
    from api.federated_signer import LocalFederatedSigner

    signer = LocalFederatedSigner()
    return jsonify(
        {
            "success": True,
            "issuer_did": signer.get_did(),
            "pubkey_hex": signer.get_public_key_hex(),
        }
    )


@signing_bp.route("/internal/sign", methods=["POST"])
@require_signing_token
def internal_sign():
    from api.federated_signer import LocalFederatedSigner

    payload = request.get_json(silent=True) or {}
    message_b64 = str(payload.get("message_b64") or "").strip()
    signature_format = str(payload.get("signature_format") or "b64url").strip().lower()
    if not message_b64:
        return jsonify({"success": False, "error": "message_b64_required"}), 400

    try:
        message = base64.b64decode(message_b64)
    except Exception:
        return jsonify({"success": False, "error": "message_b64_invalid"}), 400

    signer = LocalFederatedSigner()
    if signature_format == "hex":
        digest = message if payload.get("message_is_digest") else hashlib.sha256(message).digest()
        signature = signer.sign_digest_hex(digest)
    elif signature_format == "b64url":
        signature = signer.sign_b64url(message)
    else:
        return jsonify({"success": False, "error": "signature_format_invalid"}), 400

    return jsonify(
        {
            "success": True,
            "signature": signature,
            "issuer_did": signer.get_did(),
            "pubkey_hex": signer.get_public_key_hex(),
        }
    )


@signing_bp.route("/internal/issue-credential", methods=["POST"])
@require_signing_token
def internal_issue_credential():
    from api.federated_signer import LocalFederatedSigner

    payload = request.get_json(silent=True) or {}
    ppid = str(payload.get("ppid") or "").strip()
    claims = payload.get("claims") or {}
    if not ppid or not isinstance(claims, dict):
        return jsonify({"success": False, "error": "ppid_and_claims_required"}), 400

    claims_for_issuer = {
        key: ("true" if value is True else "false" if value is False else str(value))
        for key, value in claims.items()
    }
    signer = LocalFederatedSigner()
    credential = signer.issue_credential(ppid, claims_for_issuer)
    return jsonify({"success": True, "credential": credential})
