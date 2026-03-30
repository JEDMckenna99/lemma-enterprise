"""
Authz V2 control-plane freshness endpoints.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from api.authz_policy import ROUTE_AUTHZ_POLICY

authz_control_bp = Blueprint("authz_control", __name__)


def _revocation_shape_fields(credential_ref: str, revocation_type: str | None) -> dict:
    value = str(credential_ref or "").strip()
    lowered = value.lower()
    subject_type = str(revocation_type or "").strip().lower() or None

    proof_id = None
    root_grant_id = None
    token_id = None
    runtime_id = None
    root_type = "passkey_root"

    if lowered.startswith(("prf_", "dpf_", "proof_")):
        proof_id = value
        subject_type = subject_type or "proof"
    elif lowered.startswith(("rgr_", "root_grant_")):
        root_grant_id = value
        subject_type = subject_type or "root_grant"
    elif lowered.startswith(("wkr_", "workload_root_")):
        root_grant_id = value
        subject_type = subject_type or "workload_root"
        root_type = "workload_root"
    elif lowered.startswith(("plr_", "policy_root_")):
        root_grant_id = value
        subject_type = subject_type or "policy_root"
        root_type = "policy_root"
    elif lowered.startswith(("agt_", "lm_agent_", "token_", "tok_")):
        token_id = value
        subject_type = subject_type or "token"
    elif lowered.startswith(("runtime_", "rt_", "lemma-firewall-")):
        runtime_id = value
        subject_type = subject_type or "runtime"

    if ":" in value:
        prefix, _, suffix = value.partition(":")
        prefix_l = prefix.strip().lower()
        normalized_suffix = suffix.strip()
        if prefix_l == "proof" and normalized_suffix:
            proof_id = normalized_suffix
            subject_type = subject_type or "proof"
        elif prefix_l in {"root_grant", "grant"} and normalized_suffix:
            root_grant_id = normalized_suffix
            subject_type = subject_type or "root_grant"
        elif prefix_l in {"workload_root", "workload"} and normalized_suffix:
            root_grant_id = normalized_suffix
            subject_type = subject_type or "workload_root"
            root_type = "workload_root"
        elif prefix_l in {"policy_root", "policy"} and normalized_suffix:
            root_grant_id = normalized_suffix
            subject_type = subject_type or "policy_root"
            root_type = "policy_root"
        elif prefix_l in {"token", "agent_token"} and normalized_suffix:
            token_id = normalized_suffix
            subject_type = subject_type or "token"
        elif prefix_l == "runtime" and normalized_suffix:
            runtime_id = normalized_suffix
            subject_type = subject_type or "runtime"

    ancestor_ids = [item for item in [proof_id, root_grant_id, token_id, runtime_id] if item]
    if not ancestor_ids and value:
        ancestor_ids = [value]
    return {
        "subject_type": subject_type or "credential",
        "proof_id": proof_id,
        "root_grant_id": root_grant_id,
        "token_id": token_id,
        "runtime_id": runtime_id,
        "root_type": root_type,
        "ancestor_ids": ancestor_ids,
    }


def _snapshot_policy_payload() -> dict:
    entries = []
    for (method, route_path), policy in ROUTE_AUTHZ_POLICY.items():
        entries.append(
            {
                "method": method,
                "path": route_path,
                "required_scope": policy.required_scope,
                "allowed_principals": list(policy.allowed_principals),
                "site_binding_required": bool(policy.site_binding_required),
                "risk_tier": str(getattr(policy, "risk_tier", "low")),
                "auth_mode": str(getattr(policy, "auth_mode", "compat_bearer")),
            }
        )
    entries.sort(key=lambda item: (item["path"], item["method"]))
    raw = json.dumps(entries, separators=(",", ":"), sort_keys=True)
    version = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return {"policy_version": f"v2-{version}", "routes": entries}


@authz_control_bp.route("/api/authz/policy/snapshot", methods=["GET"])
def policy_snapshot():
    payload = _snapshot_policy_payload()
    requested = str(request.args.get("version") or "").strip()
    return jsonify(
        {
            "success": True,
            "policy": payload,
            "requested_version": requested or None,
            "up_to_date": (requested == payload["policy_version"]) if requested else None,
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
    ), 200


@authz_control_bp.route("/api/authz/revocation/delta", methods=["GET"])
def revocation_delta():
    since = max(0, int(request.args.get("since", "0") or "0"))
    limit = min(1000, max(1, int(request.args.get("limit", "250") or "250")))
    org_id = str(request.args.get("org_id") or "org_default").strip().lower() or "org_default"
    environment = str(request.args.get("environment") or "prod").strip().lower() or "prod"
    if environment not in {"dev", "staging", "prod"}:
        environment = "prod"
    changes: list[dict] = []
    max_cursor = since
    try:
        from api.database import get_db_connection

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                SELECT id, COALESCE(credential_id, lemma_id) AS credential_ref, ppid, wallet_id, revoked_at, revocation_type
                FROM revocation_list
                WHERE id > %s
                ORDER BY id ASC
                LIMIT %s
                """,
                (since, limit),
            )
            rows = cursor.fetchall()
            for row in rows:
                row_id = int(row[0] or 0)
                max_cursor = max(max_cursor, row_id)
                credential_ref = str(row[1] or "").strip()
                created_at = row[4]
                ts = None
                if created_at:
                    if getattr(created_at, "tzinfo", None) is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    ts = created_at.isoformat().replace("+00:00", "Z")
                shape = _revocation_shape_fields(credential_ref, row[5] if len(row) > 5 else None)
                changes.append(
                    {
                        "cursor": row_id,
                        "credential_id": credential_ref,
                        "subject_type": shape["subject_type"],
                        "proof_id": shape["proof_id"],
                        "root_grant_id": shape["root_grant_id"],
                        "token_id": shape["token_id"],
                        "runtime_id": shape["runtime_id"],
                        "root_type": shape["root_type"],
                        "ancestor_ids": shape["ancestor_ids"],
                        "revocation_epoch": row_id,
                        "ppid": row[2],
                        "wallet_id": row[3],
                        "revoked_at": ts,
                        "revocation_type": row[5] if len(row) > 5 else None,
                        "org_id": org_id,
                        "environment": environment,
                    }
                )
            cursor.execute(
                """
                SELECT id, subject_ref, subject_type, root_type, proof_id, root_grant_id, token_id, runtime_id,
                       delegator_ppid, revoked_at
                FROM (
                    SELECT
                        id,
                        subject_ref,
                        subject_type,
                        root_type,
                        NULL::VARCHAR AS proof_id,
                        NULL::VARCHAR AS root_grant_id,
                        NULL::VARCHAR AS token_id,
                        runtime_id,
                        delegator_ppid,
                        revoked_at
                    FROM agent_ops_revocations
                    WHERE id > %s AND org_id = %s AND environment = %s
                ) scoped
                ORDER BY id ASC
                LIMIT %s
                """,
                (since, org_id, environment, limit),
            )
            for row in cursor.fetchall() or []:
                row_id = int(row[0] or 0)
                max_cursor = max(max_cursor, row_id)
                credential_ref = str(row[1] or "").strip()
                shape = _revocation_shape_fields(credential_ref, row[2] if len(row) > 2 else None)
                root_type = str(row[3] or shape.get("root_type") or "passkey_root").strip().lower() or "passkey_root"
                created_at = row[9]
                revoked_at = created_at.isoformat().replace("+00:00", "Z") if created_at else None
                changes.append(
                    {
                        "cursor": row_id,
                        "credential_id": credential_ref,
                        "subject_type": shape["subject_type"],
                        "proof_id": shape["proof_id"],
                        "root_grant_id": shape["root_grant_id"],
                        "token_id": shape["token_id"],
                        "runtime_id": shape["runtime_id"],
                        "ancestor_ids": shape["ancestor_ids"],
                        "revocation_epoch": row_id,
                        "ppid": row[8],
                        "wallet_id": None,
                        "revoked_at": revoked_at,
                        "revocation_type": row[2],
                        "root_type": root_type,
                        "org_id": org_id,
                        "environment": environment,
                    }
                )
        finally:
            cursor.close()
            conn.close()
    except Exception:  # pylint: disable=broad-exception-caught
        # Fail-safe: return empty delta instead of 500 to preserve freshness clients.
        changes = []
        max_cursor = since

    return jsonify(
        {
            "success": True,
            "since": since,
            "org_id": org_id,
            "environment": environment,
            "next_cursor": max_cursor,
            "count": len(changes),
            "changes": changes,
            "generated_at_ms": int(time.time() * 1000),
            "ttl_ms": 30000,
        }
    ), 200


@authz_control_bp.route("/api/authz/jwks", methods=["GET"])
def authz_jwks():
    raw_jwks = str(os.getenv("LEMMA_AUTHZ_JWKS_JSON") or "").strip()
    if raw_jwks:
        try:
            payload = json.loads(raw_jwks)
            if isinstance(payload, dict) and isinstance(payload.get("keys"), list):
                return jsonify(
                    {
                        "success": True,
                        "jwks": payload,
                        "generated_at_ms": int(time.time() * 1000),
                        "source": "env",
                    }
                ), 200
        except json.JSONDecodeError:
            pass

    trusted = []
    try:
        from api.trusted_issuers import get_trusted_issuer_dids

        trusted = [str(did) for did in (get_trusted_issuer_dids() or [])]
    except Exception:  # pylint: disable=broad-exception-caught
        trusted = []
    keys = [{"kid": f"trusted:{idx}", "issuer": issuer, "kty": "unknown"} for idx, issuer in enumerate(sorted(set(trusted)))]
    return jsonify(
        {
            "success": True,
            "jwks": {"keys": keys},
            "generated_at_ms": int(time.time() * 1000),
            "source": "derived",
        }
    ), 200

