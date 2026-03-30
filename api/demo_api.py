"""
Public demo API routes.

Non-negotiable rule for this module: all issuance, revocation, and token
validation must come from real Lemma production control-plane APIs.
"""

from __future__ import annotations

import json as _json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from flask import Blueprint, jsonify, request

from api.action_taxonomy import build_default_actions
from api.agent_credentials import check_path_allowed
from api.agent_ops_store import record_decision_logs
from api.services.demo_lemma_client import DemoClientError, DemoLemmaClient
from auth.rate_limiter import rate_limit

logger = logging.getLogger(__name__)

demo_api_bp = Blueprint("demo_api", __name__)


@dataclass(frozen=True)
class DemoAction:
    action_id: str
    label: str
    method: str
    route_path: str
    required_scope: str
    risk_tier: str


ALLOWED_RUNTIMES = {
    item.strip()
    for item in str(os.getenv("LEMMA_DEMO_ALLOWED_RUNTIMES", "lemma-firewall-demo-runtime")).split(",")
    if item.strip()
}

DEFAULT_ISSUER = str(os.getenv("LEMMA_DEMO_ISSUER_ID", "demo-issuer")).strip() or "demo-issuer"
DEFAULT_SITE = str(os.getenv("LEMMA_DEMO_SITE_ID", "lemma.id")).strip() or "lemma.id"
DEFAULT_AGENT_NAME = str(os.getenv("LEMMA_DEMO_AGENT_NAME", "lemma-demo-runtime")).strip() or "lemma-demo-runtime"
DEFAULT_OWNER_PPID = str(os.getenv("LEMMA_DEMO_OWNER_PPID", "did:lemma:ppid_demo")).strip() or "did:lemma:ppid_demo"
DEFAULT_USER_REF = str(os.getenv("LEMMA_DEMO_USER_REF", "public-demo")).strip() or "public-demo"

ACTIONS: dict[str, DemoAction] = {
    "read_src_app": DemoAction(
        action_id="read_src_app",
        label="Read src/app.ts",
        method="GET",
        route_path="/runtime/fs/read/src/app.ts",
        required_scope="read",
        risk_tier="low",
    ),
    "write_src_app": DemoAction(
        action_id="write_src_app",
        label="Write src/app.ts",
        method="POST",
        route_path="/runtime/fs/write/src/app.ts",
        required_scope="write",
        risk_tier="high",
    ),
    "write_deploy_workflow": DemoAction(
        action_id="write_deploy_workflow",
        label="Write .github/workflows/deploy.yml",
        method="POST",
        route_path="/runtime/fs/write/.github/workflows/deploy.yml",
        required_scope="write",
        risk_tier="critical",
    ),
    "ingest_external_docs": DemoAction(
        action_id="ingest_external_docs",
        label="Ingest external docs",
        method="POST",
        route_path="/runtime/ingest/external/docs",
        required_scope="read",
        risk_tier="high",
    ),
    "shell_exec_pytest": DemoAction(
        action_id="shell_exec_pytest",
        label="Shell exec: pytest",
        method="POST",
        route_path="/runtime/shell/exec/pytest",
        required_scope="admin",
        risk_tier="critical",
    ),
    "curl_external_domain": DemoAction(
        action_id="curl_external_domain",
        label="Attempt curl to external domain",
        method="POST",
        route_path="/runtime/network/egress/external",
        required_scope="admin",
        risk_tier="critical",
    ),
}

_RUNTIME_STATE_TTL = 3600


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _client() -> DemoLemmaClient:
    return DemoLemmaClient.from_env()


def _get_runtime_state(runtime_id: str) -> dict[str, Any]:
    from auth.redis_store import get as redis_get
    state = redis_get(f"demo_runtime:{runtime_id}")
    if state:
        return dict(state)
    created = {"runtime_id": runtime_id, "taint_epoch": 0, "trust_state": "trusted", "updated_at": _iso_now()}
    _set_runtime_state(runtime_id, 0, "trusted")
    return created


def _set_runtime_state(runtime_id: str, taint_epoch: int, trust_state: str) -> dict[str, Any]:
    from auth.redis_store import store as redis_store
    state = {
        "runtime_id": runtime_id,
        "taint_epoch": int(max(0, taint_epoch)),
        "trust_state": str(trust_state or "trusted"),
        "updated_at": _iso_now(),
    }
    redis_store(f"demo_runtime:{runtime_id}", state, ttl_seconds=_RUNTIME_STATE_TTL)
    return state


def _is_revoked_in_control_plane(client: DemoLemmaClient, token_id: str) -> bool:
    """Check real revocation delta feed for token revocation evidence."""
    if not token_id:
        return False
    try:
        payload = client.revocation_delta(0)
    except Exception:
        return False
    changes = payload.get("changes")
    if not isinstance(changes, list):
        return False
    for item in changes:
        if not isinstance(item, dict):
            continue
        revoked_id = str(item.get("credential_id") or item.get("lemma_id") or "").strip()
        if revoked_id and revoked_id == token_id:
            return True
    return False


def _log_decision(
    *,
    runtime_id: str,
    action: DemoAction,
    decision: str,
    reason_code: str,
    status_code: int,
    metadata: dict[str, Any],
) -> None:
    try:
        event = {
            "token_id": metadata.get("token_id"),
            "action": action.action_id,
            "resource": action.route_path,
            "method": action.method,
            "path": f"/api/demo/verify/{action.action_id}",
            "status_code": status_code,
            "success": decision == "allow",
            "metadata": {
                "runtime_id": runtime_id,
                "risk_tier": action.risk_tier,
                "decision": decision,
                "reason_code": reason_code,
                "trust_state": metadata.get("trust_state"),
                "taint_epoch": metadata.get("taint_epoch"),
                "request_id": metadata.get("request_id"),
                "proof_jti": metadata.get("token_id"),
            },
        }
        record_decision_logs([event])
    except Exception as exc:
        logger.warning("demo decision log write failed: %s", exc)


def _require_runtime(runtime_id: str) -> tuple[bool, Any]:
    if runtime_id in ALLOWED_RUNTIMES:
        return True, None
    return False, (
        jsonify(
            {
                "success": False,
                "error": "runtime_not_allowed",
                "message": "Runtime is not in the demo allowlist.",
                "allowed_runtimes": sorted(ALLOWED_RUNTIMES),
            }
        ),
        403,
    )


def _normalize_issue_payload(body: dict[str, Any]) -> dict[str, Any]:
    runtime_id = str(body.get("runtime_id") or "").strip()
    action_ids = body.get("action_ids")
    if not isinstance(action_ids, list) or not action_ids:
        action_ids = ["read_src_app", "write_src_app", "shell_exec_pytest"]
    selected = [ACTIONS[action_id] for action_id in action_ids if action_id in ACTIONS]
    if not selected:
        raise ValueError("No valid demo actions were selected")

    scopes = sorted({action.required_scope for action in selected})
    allowed_paths = sorted({action.route_path for action in selected})
    ttl_hours = int(body.get("ttl_hours") or 1)
    ttl_hours = min(max(ttl_hours, 1), 24)

    return {
        "runtime_id": runtime_id,
        "upstream_payload": {
            "ttl_hours": ttl_hours,
            "scope": scopes,
            "agent_name": str(body.get("agent_name") or DEFAULT_AGENT_NAME),
            "task": str(body.get("task") or "lemma.id demo issuance"),
            "allowed_paths": allowed_paths,
            "max_operations": int(body.get("max_operations") or 100),
            "allowed_sites": [str(body.get("site_id") or DEFAULT_SITE)],
            "intended_platform": str(body.get("site_id") or DEFAULT_SITE),
            "delegation_reason": "public_demo_issue",
            "delegation_id": f"demo_{int(time.time())}",
            "acting_for_ppid": DEFAULT_OWNER_PPID,
            "requested_by_ppid": DEFAULT_OWNER_PPID,
            "delegated_by_user_ref": DEFAULT_USER_REF,
            "acting_for_user_ref": DEFAULT_USER_REF,
            "requested_by_user_ref": DEFAULT_USER_REF,
            "issuer_id": str(body.get("issuer_id") or DEFAULT_ISSUER),
        },
        "selected_actions": [action.action_id for action in selected],
    }


def _extract_issued_proof_fields(issued: dict[str, Any]) -> dict[str, Any]:
    """Normalize issuer response shapes without inventing values."""
    credential = issued.get("credential") if isinstance(issued.get("credential"), dict) else issued
    token = credential.get("token")
    token_id = credential.get("token_id")
    expires_at = credential.get("expires_at")
    scope = credential.get("scope", [])
    allowed_paths = credential.get("allowed_paths", [])
    signature = None
    if isinstance(credential.get("proof"), dict):
        signature = credential["proof"].get("signatureValue") or credential["proof"].get("signature")
    if not token or not token_id:
        raise DemoClientError(f"issuer_response_missing_token_fields:{issued}")
    return {
        "jti": token_id,
        "token": token,
        "scope": scope if isinstance(scope, list) else [],
        "expires_at": expires_at,
        "allowed_paths": allowed_paths if isinstance(allowed_paths, list) else [],
        "signature": signature,
    }


def _normalize_client_error(exc: DemoClientError, fallback_error: str) -> tuple[dict[str, Any], int]:
    raw = str(exc)
    status = None
    if raw.startswith("upstream_error:"):
        parts = raw.split(":", 3)
        if len(parts) >= 3:
            try:
                status = int(parts[2])
            except Exception:
                status = None
    if status == 401:
        return (
            {
                "success": False,
                "error": fallback_error,
                "error_code": "demo_service_unauthorized",
                "message": "Demo service credential unauthorized. Rotate LEMMA_DEMO_SERVICE_AGENT_TOKEN.",
            },
            502,
        )
    if status and status >= 500:
        return (
            {
                "success": False,
                "error": fallback_error,
                "error_code": "demo_service_unavailable",
                "message": "Production control plane temporarily unavailable.",
            },
            502,
        )
    return (
        {
            "success": False,
            "error": fallback_error,
            "error_code": "upstream_request_failed",
            "message": raw,
        },
        502,
    )


@demo_api_bp.route("/api/demo/issue-proof", methods=["POST"])
@rate_limit("30 per minute")
def demo_issue_proof():
    try:
        body = request.get_json(silent=True) or {}
        normalized = _normalize_issue_payload(body)
        runtime_id = normalized["runtime_id"]
        allowed, failure = _require_runtime(runtime_id)
        if not allowed:
            return failure

        client = _client()
        issued = client.issue_proof(normalized["upstream_payload"])
        _set_runtime_state(runtime_id, int(body.get("taint_epoch") or 0), str(body.get("trust_state") or "trusted"))
        proof_view = _extract_issued_proof_fields(issued)
        proof_view["taint_epoch"] = int(body.get("taint_epoch") or 0)

        return jsonify(
            {
                "success": True,
                "runtime_id": runtime_id,
                "proof": proof_view,
                "selected_actions": normalized["selected_actions"],
                "issued_at": _iso_now(),
            }
        )
    except ValueError as exc:
        return jsonify({"success": False, "error": "invalid_request", "message": str(exc)}), 400
    except DemoClientError as exc:
        payload, status_code = _normalize_client_error(exc, "upstream_issue_failed")
        return jsonify(payload), status_code
    except Exception as exc:
        logger.exception("demo issue route failed")
        return jsonify({"success": False, "error": "issue_failed", "message": str(exc)}), 500


@demo_api_bp.route("/api/demo/verify", methods=["POST"])
@rate_limit("120 per minute")
def demo_verify_action():
    request_id = f"demo_req_{int(time.time() * 1000)}"
    started_ms = int(time.time() * 1000)
    body = request.get_json(silent=True) or {}
    runtime_id = str(body.get("runtime_id") or "").strip()
    action_id = str(body.get("action_id") or "").strip()
    proof_token = str(body.get("proof_token") or "").strip()

    allowed, failure = _require_runtime(runtime_id)
    if not allowed:
        return failure
    action = ACTIONS.get(action_id)
    if not action:
        return jsonify({"success": False, "error": "action_not_allowed"}), 400
    if not proof_token:
        return jsonify({"success": False, "error": "proof_required"}), 400

    try:
        client = _client()
        validation = client.validate_token(proof_token)
        runtime = _get_runtime_state(runtime_id)
        taint_epoch_now = int(runtime.get("taint_epoch") or 0)
        trust_state = str(runtime.get("trust_state") or "trusted")
        status_code = int(validation.get("_status") or 0)

        if not validation.get("valid"):
            reason_code = str(validation.get("error") or "invalid_proof")
            _log_decision(
                runtime_id=runtime_id,
                action=action,
                decision="deny",
                reason_code=reason_code,
                status_code=401,
                metadata={
                    "request_id": request_id,
                    "token_id": validation.get("token_id"),
                    "trust_state": trust_state,
                    "taint_epoch": taint_epoch_now,
                },
            )
            return (
                jsonify(
                    {
                        "success": True,
                        "decision": "deny",
                        "reason_code": reason_code,
                        "status_code": 401,
                        "request_id": request_id,
                        "timestamp": _iso_now(),
                    }
                ),
                200,
            )

        validated_token_id = str(validation.get("token_id") or "").strip()
        if validated_token_id and _is_revoked_in_control_plane(client, validated_token_id):
            reason_code = "token_revoked"
            _log_decision(
                runtime_id=runtime_id,
                action=action,
                decision="deny",
                reason_code=reason_code,
                status_code=401,
                metadata={
                    "request_id": request_id,
                    "token_id": validated_token_id,
                    "trust_state": trust_state,
                    "taint_epoch": taint_epoch_now,
                },
            )
            return (
                jsonify(
                    {
                        "success": True,
                        "decision": "deny",
                        "reason_code": reason_code,
                        "status_code": 401,
                        "request_id": request_id,
                        "timestamp": _iso_now(),
                    }
                ),
                200,
            )

        granted_scopes = validation.get("scope") if isinstance(validation.get("scope"), list) else []
        if action.required_scope not in granted_scopes:
            reason_code = "proof_scope_denied"
            _log_decision(
                runtime_id=runtime_id,
                action=action,
                decision="deny",
                reason_code=reason_code,
                status_code=403,
                metadata={
                    "request_id": request_id,
                    "token_id": validation.get("token_id"),
                    "trust_state": trust_state,
                    "taint_epoch": taint_epoch_now,
                },
            )
            return jsonify(
                {
                    "success": True,
                    "decision": "deny",
                    "reason_code": reason_code,
                    "required_scope": action.required_scope,
                    "granted_scope": granted_scopes,
                    "request_id": request_id,
                    "timestamp": _iso_now(),
                }
            )

        allowed_paths = validation.get("allowed_paths")
        path_allowed, match_pattern = check_path_allowed(action.route_path, allowed_paths)
        if allowed_paths is not None and not path_allowed:
            reason_code = "proof_resource_denied"
            _log_decision(
                runtime_id=runtime_id,
                action=action,
                decision="deny",
                reason_code=reason_code,
                status_code=403,
                metadata={
                    "request_id": request_id,
                    "token_id": validation.get("token_id"),
                    "trust_state": trust_state,
                    "taint_epoch": taint_epoch_now,
                },
            )
            return jsonify(
                {
                    "success": True,
                    "decision": "deny",
                    "reason_code": reason_code,
                    "path": action.route_path,
                    "allowed_paths": allowed_paths,
                    "request_id": request_id,
                    "timestamp": _iso_now(),
                }
            )

        issued_epoch = int(body.get("proof_taint_epoch") or 0)
        if issued_epoch < taint_epoch_now:
            reason_code = "proof_taint_epoch_stale"
            _log_decision(
                runtime_id=runtime_id,
                action=action,
                decision="deny",
                reason_code=reason_code,
                status_code=403,
                metadata={
                    "request_id": request_id,
                    "token_id": validation.get("token_id"),
                    "trust_state": trust_state,
                    "taint_epoch": taint_epoch_now,
                },
            )
            return jsonify(
                {
                    "success": True,
                    "decision": "deny",
                    "reason_code": reason_code,
                    "proof_taint_epoch": issued_epoch,
                    "runtime_taint_epoch": taint_epoch_now,
                    "request_id": request_id,
                    "timestamp": _iso_now(),
                }
            )

        elapsed_ms = int(time.time() * 1000) - started_ms
        _log_decision(
            runtime_id=runtime_id,
            action=action,
            decision="allow",
            reason_code="proof_allowed",
            status_code=200,
            metadata={
                "request_id": request_id,
                "token_id": validation.get("token_id"),
                "trust_state": trust_state,
                "taint_epoch": taint_epoch_now,
            },
        )
        return jsonify(
            {
                "success": True,
                "decision": "allow",
                "reason_code": "proof_allowed",
                "request_id": request_id,
                "proof": {
                    "jti": validation.get("token_id"),
                    "expires_at": validation.get("expires_at"),
                    "scope": granted_scopes,
                    "matched_path_rule": match_pattern,
                },
                "runtime_state": runtime,
                "action": {
                    "action_id": action.action_id,
                    "label": action.label,
                    "route_path": action.route_path,
                    "method": action.method,
                    "risk_tier": action.risk_tier,
                    "required_scope": action.required_scope,
                },
                "auth_status_code": status_code,
                "latency_ms": elapsed_ms,
                "timestamp": _iso_now(),
            }
        )
    except DemoClientError as exc:
        payload, status_code = _normalize_client_error(exc, "upstream_verify_failed")
        return jsonify(payload), status_code
    except Exception as exc:
        logger.exception("demo verify route failed")
        return jsonify({"success": False, "error": "verify_failed", "message": str(exc)}), 500


@demo_api_bp.route("/api/demo/revoke", methods=["POST"])
@rate_limit("30 per minute")
def demo_revoke_proof():
    body = request.get_json(silent=True) or {}
    jti = str(body.get("jti") or "").strip()
    if not jti:
        return jsonify({"success": False, "error": "jti_required"}), 400

    reason = str(body.get("reason") or "demo_revoke").strip()
    try:
        revoked = _client().revoke_proof(jti, reason=reason)
        return jsonify({"success": bool(revoked.get("success", True)), "result": revoked, "revoked_at": _iso_now()})
    except DemoClientError as exc:
        payload, status_code = _normalize_client_error(exc, "upstream_revoke_failed")
        return jsonify(payload), status_code


@demo_api_bp.route("/api/demo/revocation-status", methods=["GET"])
@rate_limit("60 per minute")
def demo_revocation_status():
    jti = str(request.args.get("jti") or "").strip()
    if not jti:
        return jsonify({"success": False, "error": "jti_required"}), 400
    try:
        status = _client().revocation_status(jti)
        return jsonify({"success": True, "result": status, "checked_at": _iso_now()})
    except DemoClientError as exc:
        payload, status_code = _normalize_client_error(exc, "upstream_revocation_status_failed")
        return jsonify(payload), status_code


@demo_api_bp.route("/api/demo/issue-credential", methods=["POST"])
@rate_limit("20 per minute")
def demo_issue_credential():
    """Issue a signed W3C credential for demo/evaluation use.

    Returns a full credential JSON that can be passed as X-Lemma-Credential
    to the Lemma Firewall for local verification (no per-request server calls).
    """
    body = request.get_json(silent=True) or {}
    runtime_id = str(body.get("runtime_id") or "").strip()
    allowed, failure = _require_runtime(runtime_id)
    if not allowed:
        return failure

    scope = body.get("scope", ["read", "write"])
    if isinstance(scope, str):
        scope = [s.strip() for s in scope.split(",") if s.strip()]
    ttl_hours = min(int(body.get("ttl_hours") or 1), 24)

    try:
        from api.services.wallet_service import issue_permission_lemma
        from datetime import timedelta

        subject_ppid = str(body.get("ppid") or DEFAULT_OWNER_PPID)
        taint_epoch = int(body.get("taint_epoch") or 0)
        actions = body.get("actions") or build_default_actions(scope)
        credential = issue_permission_lemma(
            subject_ppid=subject_ppid,
            site_id=DEFAULT_SITE,
            permissions=scope,
            granted_by="demo_issue_credential",
            track_in_db=False,
            scope=scope,
            account_type="demo",
            custom_claims={
                "intendedPlatform": "demo",
                "useCase": "firewall_demo",
                "siteDomain": DEFAULT_SITE,
                "taint_epoch": str(taint_epoch),
                "passkey_verified_at": str(int(time.time())),
                "actions": _json.dumps(actions) if isinstance(actions, dict) else str(actions),
            },
        )

        _set_runtime_state(
            runtime_id,
            int(body.get("taint_epoch") or 0),
            str(body.get("trust_state") or "trusted"),
        )

        return jsonify({
            "success": True,
            "credential": credential,
            "runtime_id": runtime_id,
            "scope": scope,
            "usage": {
                "header": "X-Lemma-Credential",
                "value": "JSON-encode the credential object and pass as the header value",
                "verification": "local Ed25519 signature check -- no server call needed",
            },
            "issued_at": _iso_now(),
        })
    except Exception as exc:
        logger.exception("demo_issue_credential failed")
        return jsonify({
            "success": False,
            "error": "credential_issuance_failed",
            "message": str(exc),
        }), 500


@demo_api_bp.route("/api/demo/issue-proof-chain", methods=["POST"])
@rate_limit("20 per minute")
def demo_issue_proof_chain():
    """Issue a proof chain with delegation for demo use. Returns X-Lemma-Proof payload."""
    body = request.get_json(silent=True) or {}
    runtime_id = str(body.get("runtime_id") or "").strip()
    allowed, failure = _require_runtime(runtime_id)
    if not allowed:
        return failure

    root_scope = body.get("scope", ["read", "write"])
    if isinstance(root_scope, str):
        root_scope = [s.strip() for s in root_scope.split(",") if s.strip()]
    delegated_scope = body.get("delegated_scope", ["read"])
    if isinstance(delegated_scope, str):
        delegated_scope = [s.strip() for s in delegated_scope.split(",") if s.strip()]

    delegated_scope = [s for s in delegated_scope if s in root_scope]
    if not delegated_scope:
        delegated_scope = [root_scope[0]] if root_scope else ["read"]

    taint_epoch = int(body.get("taint_epoch") or 0)

    try:
        from api.services.wallet_service import issue_permission_lemma, _build_firewall_proof_chain_artifact

        subject_ppid = str(body.get("ppid") or DEFAULT_OWNER_PPID)
        root_actions = body.get("actions") or build_default_actions(root_scope)
        credential = issue_permission_lemma(
            subject_ppid=subject_ppid,
            site_id=DEFAULT_SITE,
            permissions=root_scope,
            granted_by="demo_issue_proof_chain",
            track_in_db=False,
            scope=root_scope,
            account_type="demo",
            custom_claims={
                "intendedPlatform": "demo",
                "useCase": "firewall_proof_chain_demo",
                "siteDomain": DEFAULT_SITE,
                "taint_epoch": str(taint_epoch),
                "actions": _json.dumps(root_actions) if isinstance(root_actions, dict) else str(root_actions),
            },
        )

        proof_chain = _build_firewall_proof_chain_artifact(
            permission_lemma=credential,
            ppid=subject_ppid,
            site_id=DEFAULT_SITE,
            policy_version="authz_profile_v2",
            agent_key_id=f"demo-agent-{runtime_id}",
            root_type="passkey_root",
            org_id="org_default",
            environment="prod",
        )

        delegated_actions = build_default_actions(delegated_scope)
        if "delegated_proof" in proof_chain:
            proof_chain["delegated_proof"]["scope"] = delegated_scope
            proof_chain["delegated_proof"]["actions"] = delegated_actions
        proof_chain["scope"] = delegated_scope
        proof_chain["actions"] = delegated_actions

        _set_runtime_state(runtime_id, taint_epoch, str(body.get("trust_state") or "trusted"))

        return jsonify({
            "success": True,
            "proof_chain": proof_chain,
            "root_scope": root_scope,
            "delegated_scope": delegated_scope,
            "runtime_id": runtime_id,
            "usage": {
                "header": "X-Lemma-Proof",
                "value": "Base64url-encode or JSON-encode the proof_chain and pass as the header value",
            },
            "issued_at": _iso_now(),
        })
    except Exception as exc:
        logger.exception("demo_issue_proof_chain failed")
        return jsonify({"success": False, "error": "proof_chain_issuance_failed", "message": str(exc)}), 500


@demo_api_bp.route("/api/demo/revoke-credential", methods=["POST"])
@rate_limit("20 per minute")
def demo_revoke_credential():
    """Revoke a demo credential so the firewall denies it on next sync."""
    body = request.get_json(silent=True) or {}
    credential_id = str(body.get("credential_id") or "").strip()
    if not credential_id:
        return jsonify({"success": False, "error": "credential_id_required"}), 400

    try:
        from api.database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO revocation_list
                (lemma_id, credential_id, lemma_type, site_id, user_did, revocation_type, revoked_at, reason, bloom_filter_updated)
                VALUES (%s, %s, 'permission', %s, %s, 'demo_revoke', NOW(), %s, FALSE)
                ON CONFLICT (lemma_id) DO UPDATE SET revoked_at = NOW()
                """,
                (credential_id, credential_id, "lemma.id", "demo", "demo_revoke"),
            )
            conn.commit()
        finally:
            cursor.close()
            conn.close()
        return jsonify({
            "success": True,
            "credential_id": credential_id,
            "event": "credential_revoked",
            "note": "Firewall will pick this up on next revocation sync",
        })
    except Exception as exc:
        logger.exception("demo_revoke_credential failed")
        return jsonify({"success": False, "error": "revocation_failed", "message": str(exc)}), 500


@demo_api_bp.route("/api/demo/taint-bump", methods=["POST"])
@rate_limit("20 per minute")
def demo_taint_bump():
    body = request.get_json(silent=True) or {}
    runtime_id = str(body.get("runtime_id") or "").strip()
    allowed, failure = _require_runtime(runtime_id)
    if not allowed:
        return failure

    current = _get_runtime_state(runtime_id)
    next_epoch = int(current.get("taint_epoch") or 0) + 1
    trust_state = str(body.get("trust_state") or "tainted")
    updated = _set_runtime_state(runtime_id, next_epoch, trust_state)
    return jsonify({"success": True, "runtime_state": updated, "event": "taint_epoch_bumped"})


@demo_api_bp.route("/api/demo/state", methods=["GET"])
@rate_limit("120 per minute")
def demo_state():
    runtime_id = str(request.args.get("runtime_id") or "").strip()
    if not runtime_id:
        return jsonify({"success": False, "error": "runtime_required"}), 400
    allowed, failure = _require_runtime(runtime_id)
    if not allowed:
        return failure
    state = _get_runtime_state(runtime_id)
    actions = [
        {
            "action_id": action.action_id,
            "label": action.label,
            "method": action.method,
            "route_path": action.route_path,
            "required_scope": action.required_scope,
            "risk_tier": action.risk_tier,
        }
        for action in ACTIONS.values()
    ]
    return jsonify(
        {
            "success": True,
            "runtime_state": state,
            "actions": actions,
            "allowed_runtimes": sorted(ALLOWED_RUNTIMES),
            "issuer_id": DEFAULT_ISSUER,
            "site_id": DEFAULT_SITE,
        }
    )
