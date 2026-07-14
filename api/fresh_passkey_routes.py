"""HTTP routes for server-attested fresh-passkey action ceremonies."""

from __future__ import annotations

import base64
import logging
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request
from flask_cors import cross_origin

from api.fresh_passkey_attestation import (
    build_action_commitment,
    delete_fresh_passkey_challenge,
    get_fresh_passkey_challenge,
    issue_fresh_passkey_attestation,
    lookup_wallet_passkey_public_key,
    store_fresh_passkey_challenge,
    update_wallet_passkey_sign_count,
    verify_wallet_webauthn_assertion,
)
from api.passkey_auth import ORIGIN, RP_ID

logger = logging.getLogger(__name__)

fresh_passkey_bp = Blueprint("fresh_passkey", __name__)


@fresh_passkey_bp.route("/api/ishuman/fresh-passkey/begin", methods=["POST", "OPTIONS"])
@cross_origin()
def fresh_passkey_begin():
    """Issue a WebAuthn challenge bound to an opaque action commitment."""
    body = request.get_json(silent=True) or {}
    site_id = (body.get("site_id") or "").strip()
    action_commitment = (body.get("action_commitment") or "").strip().lower()
    credential_id = (body.get("credential_id") or "").strip()
    passkey_credential_id = (body.get("passkey_credential_id") or "").strip()
    subject = (body.get("subject") or "").strip()
    wallet_id = (body.get("wallet_id") or "").strip()

    if not site_id or not action_commitment:
        return jsonify({"success": False, "error": "site_id and action_commitment required"}), 400
    if not credential_id or not subject:
        return jsonify({"success": False, "error": "credential_id and subject required"}), 400
    if not passkey_credential_id:
        return jsonify({"success": False, "error": "passkey_credential_id required"}), 400

    challenge = secrets.token_bytes(32)
    challenge_key = f"fpa_{secrets.token_urlsafe(16)}"
    expires = (datetime.utcnow() + timedelta(seconds=120)).isoformat()
    store_fresh_passkey_challenge(
        challenge_key,
        {
            "challenge": base64.urlsafe_b64encode(challenge).decode("utf-8"),
            "site_id": site_id,
            "action_commitment": action_commitment,
            "credential_id": credential_id,
            "passkey_credential_id": passkey_credential_id,
            "subject": subject,
            "wallet_id": wallet_id,
            "expires": expires,
        },
    )
    return jsonify(
        {
            "success": True,
            "challenge_key": challenge_key,
            "challenge": base64.urlsafe_b64encode(challenge).decode("utf-8"),
            "expires": expires,
            "rp_id": RP_ID,
        }
    )


@fresh_passkey_bp.route("/api/ishuman/fresh-passkey/complete", methods=["POST", "OPTIONS"])
@cross_origin()
def fresh_passkey_complete():
    """Verify WebAuthn assertion and issue a short-lived fresh-passkey attestation."""
    body = request.get_json(silent=True) or {}
    challenge_key = (body.get("challenge_key") or "").strip()
    credential = body.get("credential")
    if not challenge_key or not isinstance(credential, dict):
        return jsonify({"success": False, "error": "challenge_key and credential required"}), 400

    stored = get_fresh_passkey_challenge(challenge_key)
    if not stored:
        return jsonify({"success": False, "error": "challenge_expired"}), 401

    expires_str = stored.get("expires")
    if expires_str:
        expires = datetime.fromisoformat(expires_str)
        if datetime.utcnow() > expires:
            delete_fresh_passkey_challenge(challenge_key)
            return jsonify({"success": False, "error": "challenge_expired"}), 401

    credential_id_b64 = str(credential.get("id") or "").strip()
    expected_passkey_credential_id = str(
        stored.get("passkey_credential_id") or stored.get("credential_id") or ""
    ).strip()
    if not credential_id_b64 or credential_id_b64 != expected_passkey_credential_id:
        return jsonify({"success": False, "error": "credential_id_mismatch"}), 403

    public_key_b64, sign_count = lookup_wallet_passkey_public_key(credential_id_b64)
    if not public_key_b64:
        return jsonify({"success": False, "error": "passkey_not_registered_on_server"}), 403

    ok, reason, new_sign_count = verify_wallet_webauthn_assertion(
        credential=credential,
        expected_challenge=base64.urlsafe_b64decode(stored["challenge"]),
        rp_id=RP_ID,
        origin=ORIGIN,
        public_key_b64=public_key_b64,
        sign_count=sign_count,
    )
    if not ok:
        return jsonify({"success": False, "error": reason}), 403

    update_wallet_passkey_sign_count(credential_id_b64, new_sign_count)
    delete_fresh_passkey_challenge(challenge_key)

    attestation = issue_fresh_passkey_attestation(
        site_id=stored["site_id"],
        credential_id=stored["credential_id"],
        subject=stored["subject"],
        action_commitment=stored["action_commitment"],
    )
    return jsonify({"success": True, "fresh_passkey_attestation": attestation})


@fresh_passkey_bp.route("/api/ishuman/action-commitment", methods=["POST", "OPTIONS"])
@cross_origin()
def action_commitment_helper():
    """Server-side helper for relying sites to compute opaque action commitments."""
    body = request.get_json(silent=True) or {}
    commitment = build_action_commitment(
        server_nonce=(body.get("server_nonce") or "").strip(),
        site_id=(body.get("site_id") or "").strip(),
        action=(body.get("action") or "").strip(),
        method=(body.get("method") or "POST").strip(),
        path=(body.get("path") or "").strip(),
        body_hash=(body.get("body_hash") or "").strip(),
    )
    return jsonify({"success": True, "action_commitment": commitment})
