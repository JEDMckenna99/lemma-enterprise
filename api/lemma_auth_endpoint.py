"""
Lemma Credential Issuance Endpoint

Pure issuance: verifies the caller's existing credential (or initial proof),
then issues a fresh signed credential. No session state, no trusting
client-supplied verification results.

The server's ONLY role in the auth flow is signing credentials.
Verification happens locally on every subsequent request.
"""

from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
import json
import logging
import time

logger = logging.getLogger(__name__)

lemma_auth_bp = Blueprint("lemma_auth", __name__)


@lemma_auth_bp.route("/api/auth/issue-credential", methods=["POST"])
@cross_origin()
def issue_credential():
    """
    Issue a signed credential to an authenticated caller.

    The caller MUST present a valid X-Lemma-Credential proving their
    identity (PPID) and current permissions.  The server re-issues a
    fresh credential signed with the platform key.

    POST /api/auth/issue-credential
    Headers:
        X-Lemma-Credential: <base64url or JSON credential>
    Body (optional JSON):
        {
            "requested_scope": ["read", "write"],
            "site_id": "example.com"
        }

    Returns a new signed credential or an error.
    """
    from api.authz_engine import extract_user_lemma_principal

    principal, error = extract_user_lemma_principal(request.headers)
    if not principal:
        return jsonify({"success": False, "error": f"Authentication required: {error}"}), 401

    body = request.get_json(silent=True) or {}
    requested_scope = body.get("requested_scope", principal.scope)
    site_id = body.get("site_id", principal.site_binding or "lemma.id")

    if not set(requested_scope).issubset(set(principal.scope)):
        return jsonify({
            "success": False,
            "error": "Cannot escalate scope beyond current credential",
            "current_scope": principal.scope,
            "requested_scope": requested_scope,
        }), 403

    try:
        from api.issuer_management import get_issuer_manager

        issuer_manager = get_issuer_manager()
        iam_issuer = issuer_manager.get_iam_issuer(site_id)

        current_time = int(time.time())
        claims = {
            "packageType": "permission",
            "siteId": site_id,
            "permissionId": principal.permission_id,
            "scope": ",".join(requested_scope),
            "issuedAt": str(current_time),
            "expiresAt": str(current_time + 86400),
        }

        credential_json = iam_issuer.issue_credential(principal.ppid, claims)
        credential_data = json.loads(credential_json)

        credential_data["issuerInfo"] = {
            "did": iam_issuer.get_did(),
            "publicKey": iam_issuer.get_public_key_hex(),
            "name": "Lemma IAM",
            "verified": True,
        }

        logger.info(f"Credential issued for {principal.ppid[:30]}... scope={requested_scope}")

        return jsonify({
            "success": True,
            "credential": credential_data,
            "ppid": principal.ppid,
            "scope": requested_scope,
        })

    except Exception as exc:
        logger.error(f"Credential issuance failed: {exc}")
        return jsonify({"success": False, "error": "Credential issuance failed"}), 500


@lemma_auth_bp.route("/api/auth/lemma-signin", methods=["POST"])
@cross_origin()
def lemma_signin():
    """
    Legacy sign-in endpoint — now a thin wrapper around issue_credential.

    Accepts the old request shape for backwards compatibility but does NOT
    trust client-supplied verification_result.  Instead it requires a valid
    X-Lemma-Credential header proving the caller's identity.
    """
    from api.authz_engine import extract_user_lemma_principal

    principal, error = extract_user_lemma_principal(request.headers)
    if not principal:
        return jsonify({"success": False, "error": f"Valid credential required: {error}"}), 401

    try:
        from api.issuer_management import get_issuer_manager

        issuer_manager = get_issuer_manager()
        iam_issuer = issuer_manager.get_iam_issuer("lemma.id")

        current_time = int(time.time())
        claims = {
            "packageType": "permission",
            "siteId": "lemma.id",
            "permissionId": principal.permission_id,
            "scope": ",".join(principal.scope),
            "issuedAt": str(current_time),
            "expiresAt": str(current_time + 86400),
        }

        credential_json = iam_issuer.issue_credential(principal.ppid, claims)
        credential_data = json.loads(credential_json)

        credential_data["issuerInfo"] = {
            "did": iam_issuer.get_did(),
            "publicKey": iam_issuer.get_public_key_hex(),
            "name": "Lemma IAM",
            "verified": True,
        }

        return jsonify({
            "success": True,
            "permission_lemma": credential_data,
            "ppid": principal.ppid,
            "user_role": principal.permission_id,
            "auth_method": "credential",
            "message": "Authenticated via credential verification",
        })

    except Exception as exc:
        logger.error(f"Sign-in credential issuance failed: {exc}")
        return jsonify({"success": False, "error": "Authentication failed"}), 500
