"""
Shared storage helpers for the workspace-first Agent Ops schema.

The helpers in this module keep the new canonical tables populated while the
legacy IAM and wallet-auth flows continue to operate during migration.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SCHEMA_READY = False
_MIGRATION_PATH = Path(__file__).resolve().parent.parent / "migrations" / "022_agent_ops_workspace_schema.sql"


def _normalize_site_identifier(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    text = text.split("://", 1)[-1]
    text = text.split("/", 1)[0]
    text = text.split(":", 1)[0]
    if text.startswith("www."):
        text = text[4:]
    return text or None


def _clean_identifier(value: str | None, fallback: str, max_len: int = 120) -> str:
    cleaned = "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum() or ch in {"-", "_", "."})
    cleaned = cleaned[:max_len]
    return cleaned or fallback


def _normalize_org_id(value: str | None) -> str:
    return _clean_identifier(value, "org_default", max_len=120)


def _normalize_environment(value: str | None) -> str:
    env = _clean_identifier(value, "prod", max_len=32)
    return env if env in {"dev", "staging", "prod"} else "prod"


def _normalize_root_type(value: str | None) -> str:
    root_type = _clean_identifier(value, "passkey_root", max_len=32)
    return root_type if root_type in {"passkey_root", "workload_root", "policy_root"} else "passkey_root"


def _synthetic_user_did(*, ppid: str | None, email: str | None, wallet_id: str | None) -> str:
    candidate = str(ppid or "").strip()
    if candidate.startswith("did:lemma:ppid_"):
        return candidate
    basis = (str(email or "").strip().lower() or str(wallet_id or "").strip() or "anonymous").encode("utf-8")
    digest = hashlib.sha256(basis).hexdigest()[:24]
    return f"did:lemma:workspace_user_{digest}"


def _workspace_slug(
    *,
    explicit_workspace_id: str | None,
    site_ids: list[str] | None,
    ppid: str | None,
    email: str | None,
    wallet_id: str | None,
) -> tuple[str, str]:
    if explicit_workspace_id:
        workspace_id = _clean_identifier(explicit_workspace_id, "ws_default")
        slug = workspace_id.removeprefix("ws_")
        return workspace_id, slug

    first_site = next((site for site in (site_ids or []) if site), None)
    seed = first_site or str(email or "").split("@", 1)[0] or str(ppid or "").rsplit("_", 1)[-1] or str(wallet_id or "")[:24]
    seed = _clean_identifier(seed, "workspace", max_len=64)
    digest_basis = "|".join([first_site or "", str(ppid or ""), str(email or "").lower(), str(wallet_id or "")]).encode("utf-8")
    digest = hashlib.sha256(digest_basis).hexdigest()[:10]
    slug = f"{seed}-{digest}"
    return f"ws_{slug}", slug


def ensure_agent_ops_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    from api.database import get_db_connection

    migration_sql = _MIGRATION_PATH.read_text(encoding="utf-8")
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(migration_sql)
        conn.commit()
        _SCHEMA_READY = True
    finally:
        cursor.close()
        conn.close()


def ensure_workspace_context(
    *,
    ppid: str | None = None,
    email: str | None = None,
    wallet_id: str | None = None,
    workspace_id: str | None = None,
    site_ids: list[str] | None = None,
    display_name: str | None = None,
    membership_role: str = "owner",
) -> str:
    ensure_agent_ops_schema()
    from api.database import get_db_connection

    normalized_sites = [site for site in (_normalize_site_identifier(site) for site in (site_ids or [])) if site]
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        resolved_workspace_id = None
        if normalized_sites:
            cursor.execute(
                """
                SELECT workspace_id
                FROM sites
                WHERE site_id = ANY(%s) AND workspace_id IS NOT NULL AND workspace_id <> ''
                ORDER BY workspace_id
                LIMIT 1
                """,
                (normalized_sites,),
            )
            row = cursor.fetchone()
            if row and row[0]:
                resolved_workspace_id = str(row[0])

        workspace_key, slug = _workspace_slug(
            explicit_workspace_id=workspace_id or resolved_workspace_id,
            site_ids=normalized_sites,
            ppid=ppid,
            email=email,
            wallet_id=wallet_id,
        )
        display = str(display_name or normalized_sites[0] if normalized_sites else "" or "").strip()
        if not display:
            display = (
                str(email or "").strip().split("@", 1)[0]
                or str(ppid or "").strip().rsplit("_", 1)[-1]
                or slug
            )
        display = display[:255]

        cursor.execute(
            """
            INSERT INTO workspaces (
                workspace_id, slug, display_name, owner_ppid, owner_email, owner_wallet_id, status, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'active', NOW())
            ON CONFLICT (workspace_id)
            DO UPDATE SET
                slug = EXCLUDED.slug,
                display_name = COALESCE(NULLIF(EXCLUDED.display_name, ''), workspaces.display_name),
                owner_ppid = COALESCE(EXCLUDED.owner_ppid, workspaces.owner_ppid),
                owner_email = COALESCE(EXCLUDED.owner_email, workspaces.owner_email),
                owner_wallet_id = COALESCE(EXCLUDED.owner_wallet_id, workspaces.owner_wallet_id),
                updated_at = NOW()
            """,
            (workspace_key, slug, display, ppid or None, (email or "").strip().lower() or None, wallet_id or None),
        )

        user_did = _synthetic_user_did(ppid=ppid, email=email, wallet_id=wallet_id)
        cursor.execute(
            """
            INSERT INTO workspace_users (
                user_did, primary_email, display_name, wallet_id, verification_level, status, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, 'active', NOW())
            ON CONFLICT (user_did)
            DO UPDATE SET
                primary_email = COALESCE(EXCLUDED.primary_email, workspace_users.primary_email),
                display_name = COALESCE(NULLIF(EXCLUDED.display_name, ''), workspace_users.display_name),
                wallet_id = COALESCE(EXCLUDED.wallet_id, workspace_users.wallet_id),
                verification_level = COALESCE(EXCLUDED.verification_level, workspace_users.verification_level),
                status = 'active',
                updated_at = NOW()
            RETURNING id
            """,
            (
                user_did,
                (email or "").strip().lower() or None,
                display,
                wallet_id or None,
                "human_verified" if ppid else "base",
            ),
        )
        workspace_user_id = int(cursor.fetchone()[0])
        cursor.execute(
            """
            INSERT INTO workspace_memberships (
                workspace_id, workspace_user_id, role, invite_status, joined_at, invited_by
            )
            VALUES (%s, %s, %s, 'active', NOW(), %s)
            ON CONFLICT (workspace_id, workspace_user_id)
            DO UPDATE SET
                role = CASE
                    WHEN workspace_memberships.role = 'owner' THEN workspace_memberships.role
                    ELSE EXCLUDED.role
                END,
                invite_status = 'active'
            """,
            (workspace_key, workspace_user_id, membership_role, user_did),
        )

        if normalized_sites:
            cursor.execute(
                """
                UPDATE sites
                SET workspace_id = COALESCE(NULLIF(workspace_id, ''), %s)
                WHERE site_id = ANY(%s)
                """,
                (workspace_key, normalized_sites),
            )

        if ppid:
            cursor.execute(
                """
                UPDATE customers
                SET workspace_id = COALESCE(NULLIF(workspace_id, ''), %s)
                WHERE customer_did = %s
                """,
                (workspace_key, ppid),
            )
        if email:
            cursor.execute(
                """
                UPDATE customers
                SET workspace_id = COALESCE(NULLIF(workspace_id, ''), %s)
                WHERE LOWER(COALESCE(email, '')) = %s OR LOWER(COALESCE(billing_email, '')) = %s
                """,
                (workspace_key, email.strip().lower(), email.strip().lower()),
            )

        conn.commit()
        return workspace_key
    finally:
        cursor.close()
        conn.close()


def owned_sites_for_principal(*, ppid: str | None, email: str | None) -> set[str]:
    ensure_agent_ops_schema()
    from api.database import get_db_connection

    ppid = str(ppid or "").strip()
    email = str(email or "").strip().lower()
    if not ppid and not email:
        return set()

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        owned_sites: set[str] = set()

        role_params: list[Any] = []
        principal_clauses: list[str] = []
        if ppid:
            principal_clauses.append("sa.admin_did = %s")
            role_params.append(ppid)
        if email:
            principal_clauses.append("LOWER(COALESCE(sa.admin_email, '')) = %s")
            role_params.append(email)
        if principal_clauses:
            cursor.execute(
                f"""
                SELECT sa.site_id
                FROM site_admins sa
                WHERE sa.is_active = TRUE
                  AND LOWER(COALESCE(sa.admin_role, '')) IN ('owner', 'admin', 'super_admin', 'superadmin')
                  AND ({' OR '.join(principal_clauses)})
                """,
                tuple(role_params),
            )
            for row in cursor.fetchall() or []:
                site_value = _normalize_site_identifier(row[0] if row else None)
                if site_value:
                    owned_sites.add(site_value)

        membership_clauses: list[str] = []
        membership_params: list[Any] = []
        if ppid:
            membership_clauses.append("wu.user_did = %s")
            membership_params.append(ppid)
        if email:
            membership_clauses.append("LOWER(COALESCE(wu.primary_email, '')) = %s")
            membership_params.append(email)
        if membership_clauses:
            cursor.execute(
                f"""
                SELECT s.site_id, s.site_domain
                FROM workspace_memberships wm
                JOIN workspace_users wu ON wu.id = wm.workspace_user_id
                JOIN sites s ON s.workspace_id = wm.workspace_id
                WHERE wm.invite_status = 'active'
                  AND LOWER(COALESCE(wm.role, 'viewer')) IN ('owner', 'admin', 'operator')
                  AND ({' OR '.join(membership_clauses)})
                """,
                tuple(membership_params),
            )
            for row in cursor.fetchall() or []:
                site_value = _normalize_site_identifier((row[1] if row and row[1] else None) or (row[0] if row else None))
                if site_value:
                    owned_sites.add(site_value)
        return owned_sites
    finally:
        cursor.close()
        conn.close()


def record_delegation(
    *,
    token_id: str,
    delegation_id: str,
    delegator_ppid: str | None,
    delegated_by_user_ref: str | None,
    acting_for_ppid: str | None,
    acting_for_user_ref: str | None,
    requested_by_ppid: str | None,
    requested_by_user_ref: str | None,
    subject_type: str,
    subject_ref: str,
    scope: list[str] | None,
    allowed_sites: list[str] | None,
    audience: str | None,
    task_description: str | None,
    task_hash: str | None,
    allowed_paths: list[str] | None,
    max_operations: int | None,
    expires_at,
    reason: str | None,
    runtime_id: str | None = None,
    org_id: str | None = None,
    environment: str | None = None,
    root_type: str | None = None,
) -> str:
    ensure_agent_ops_schema()
    workspace_id = ensure_workspace_context(
        ppid=delegator_ppid,
        email=delegated_by_user_ref,
        site_ids=[audience] if audience else (allowed_sites or []),
    )
    from api.database import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO delegations (
                delegation_id, workspace_id, org_id, environment, root_type, runtime_id, token_id, delegator_ppid,
                delegated_by_user_ref, acting_for_ppid, acting_for_user_ref,
                requested_by_ppid, requested_by_user_ref, subject_type, subject_ref,
                audience, scope_json, allowed_sites_json, task_description, task_hash,
                allowed_paths_json, max_operations, expires_at, status, reason, updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, 'active', %s, NOW()
            )
            ON CONFLICT (delegation_id)
            DO UPDATE SET
                token_id = EXCLUDED.token_id,
                org_id = EXCLUDED.org_id,
                environment = EXCLUDED.environment,
                root_type = EXCLUDED.root_type,
                runtime_id = COALESCE(EXCLUDED.runtime_id, delegations.runtime_id),
                subject_ref = EXCLUDED.subject_ref,
                audience = COALESCE(EXCLUDED.audience, delegations.audience),
                scope_json = EXCLUDED.scope_json,
                allowed_sites_json = EXCLUDED.allowed_sites_json,
                task_description = COALESCE(EXCLUDED.task_description, delegations.task_description),
                task_hash = COALESCE(EXCLUDED.task_hash, delegations.task_hash),
                allowed_paths_json = EXCLUDED.allowed_paths_json,
                max_operations = EXCLUDED.max_operations,
                expires_at = EXCLUDED.expires_at,
                reason = COALESCE(EXCLUDED.reason, delegations.reason),
                status = CASE WHEN delegations.revoked_at IS NULL THEN 'active' ELSE delegations.status END,
                updated_at = NOW()
            """,
            (
                delegation_id,
                workspace_id,
                _normalize_org_id(org_id),
                _normalize_environment(environment),
                _normalize_root_type(root_type),
                runtime_id or None,
                token_id,
                delegator_ppid or None,
                delegated_by_user_ref or None,
                acting_for_ppid or None,
                acting_for_user_ref or None,
                requested_by_ppid or None,
                requested_by_user_ref or None,
                subject_type,
                subject_ref,
                audience or None,
                json.dumps(scope or []),
                json.dumps([site for site in (_normalize_site_identifier(site) for site in (allowed_sites or [])) if site]),
                task_description or None,
                task_hash or None,
                json.dumps(allowed_paths or []),
                max_operations,
                expires_at,
                reason or None,
            ),
        )
        conn.commit()
        return workspace_id
    finally:
        cursor.close()
        conn.close()


def revoke_delegation_for_token(*, token_id: str, reason: str | None, revoked_by: str | None) -> None:
    ensure_agent_ops_schema()
    from api.database import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE delegations
            SET revoked_at = NOW(),
                status = 'revoked',
                reason = COALESCE(%s, reason),
                updated_at = NOW()
            WHERE token_id = %s
            """,
            (reason or None, token_id),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def record_revocation(
    *,
    subject_type: str,
    subject_ref: str,
    workspace_id: str | None = None,
    runtime_id: str | None = None,
    delegator_ppid: str | None = None,
    reason_code: str | None = None,
    revoked_by: str | None = None,
    effective_epoch: int | None = None,
    metadata: dict[str, Any] | None = None,
    org_id: str | None = None,
    environment: str | None = None,
    root_type: str | None = None,
) -> None:
    ensure_agent_ops_schema()
    from api.database import get_db_connection

    resolved_workspace_id = workspace_id
    if not resolved_workspace_id and delegator_ppid:
        resolved_workspace_id = ensure_workspace_context(ppid=delegator_ppid)
    revocation_id = f"rev_{secrets.token_urlsafe(8)}"
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO agent_ops_revocations (
                revocation_id, workspace_id, org_id, environment, root_type, subject_type, subject_ref, runtime_id,
                delegator_ppid, reason_code, revoked_by, effective_epoch, metadata_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                revocation_id,
                resolved_workspace_id,
                _normalize_org_id(org_id),
                _normalize_environment(environment),
                _normalize_root_type(root_type),
                subject_type,
                subject_ref,
                runtime_id or None,
                delegator_ppid or None,
                reason_code or None,
                revoked_by or None,
                effective_epoch,
                json.dumps(metadata or {}),
            ),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def upsert_runtime(
    *,
    runtime_id: str,
    agent_id: str,
    workspace_id: str | None,
    display_name: str | None,
    policy_profile: str,
    risk_defaults: dict[str, Any] | None,
    kill_switch_enabled: bool,
    owner_wallet_id: str | None,
    owner_ppid: str | None,
    site_id: str | None = None,
    org_id: str | None = None,
    environment: str | None = None,
    root_type: str | None = None,
) -> dict[str, Any]:
    ensure_agent_ops_schema()
    resolved_workspace_id = ensure_workspace_context(
        ppid=owner_ppid,
        wallet_id=owner_wallet_id,
        workspace_id=workspace_id,
        site_ids=[site_id] if site_id else None,
        display_name=display_name,
    )
    from api.database import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO runtimes (
                runtime_id, workspace_id, org_id, environment, root_type, site_id, owner_ppid, owner_wallet_id, agent_id,
                display_name, policy_profile_id, policy_profile_version, risk_defaults_json,
                kill_switch_enabled, active, last_connected_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'v1', %s, %s, TRUE, NOW(), NOW())
            ON CONFLICT (runtime_id)
            DO UPDATE SET
                workspace_id = EXCLUDED.workspace_id,
                org_id = EXCLUDED.org_id,
                environment = EXCLUDED.environment,
                root_type = EXCLUDED.root_type,
                site_id = COALESCE(EXCLUDED.site_id, runtimes.site_id),
                owner_ppid = COALESCE(EXCLUDED.owner_ppid, runtimes.owner_ppid),
                owner_wallet_id = COALESCE(EXCLUDED.owner_wallet_id, runtimes.owner_wallet_id),
                agent_id = EXCLUDED.agent_id,
                display_name = COALESCE(EXCLUDED.display_name, runtimes.display_name),
                policy_profile_id = EXCLUDED.policy_profile_id,
                risk_defaults_json = EXCLUDED.risk_defaults_json,
                kill_switch_enabled = EXCLUDED.kill_switch_enabled,
                active = TRUE,
                killed_at = NULL,
                kill_reason = NULL,
                last_connected_at = NOW(),
                updated_at = NOW()
            RETURNING runtime_id, agent_id, workspace_id, org_id, environment, root_type, site_id, display_name,
                      policy_profile_id, policy_profile_version, risk_defaults_json, trust_state, taint_epoch,
                      kill_switch_enabled, emergency_stopped, quota_json, active,
                      created_at, updated_at, last_connected_at, killed_at, kill_reason
            """,
            (
                runtime_id,
                resolved_workspace_id,
                _normalize_org_id(org_id),
                _normalize_environment(environment),
                _normalize_root_type(root_type),
                _normalize_site_identifier(site_id) if site_id else None,
                owner_ppid or None,
                owner_wallet_id or None,
                agent_id,
                display_name or None,
                policy_profile or "lemma_firewall_default_v1",
                json.dumps(risk_defaults or {}),
                bool(kill_switch_enabled),
            ),
        )
        row = cursor.fetchone()
        conn.commit()
        return _runtime_row_to_dict(row)
    finally:
        cursor.close()
        conn.close()


def _runtime_row_to_dict(row) -> dict[str, Any]:
    if not row:
        return {}
    risk_defaults = row[10] if isinstance(row[10], dict) else json.loads(row[10] or "{}")
    quota_json = row[15] if isinstance(row[15], dict) else json.loads(row[15] or "{}")
    return {
        "runtime_id": str(row[0] or ""),
        "agent_id": str(row[1] or ""),
        "workspace_id": str(row[2] or ""),
        "org_id": str(row[3] or "org_default"),
        "environment": str(row[4] or "prod"),
        "root_type": str(row[5] or "passkey_root"),
        "site_id": str(row[6] or ""),
        "display_name": str(row[7] or ""),
        "policy_profile": str(row[8] or "lemma_firewall_default_v1"),
        "policy_profile_version": str(row[9] or "v1"),
        "risk_defaults": risk_defaults if isinstance(risk_defaults, dict) else {},
        "trust_state": str(row[11] or "clean_internal"),
        "taint_epoch": int(row[12]) if row[12] is not None else 0,
        "kill_switch_enabled": bool(row[13]),
        "emergency_stopped": bool(row[14]),
        "quota_json": quota_json if isinstance(quota_json, dict) else {},
        "active": bool(row[16]),
        "created_at": row[17].isoformat() + "Z" if row[17] else None,
        "updated_at": row[18].isoformat() + "Z" if row[18] else None,
        "last_connected_at": row[19].isoformat() + "Z" if row[19] else None,
        "killed_at": row[20].isoformat() + "Z" if row[20] else None,
        "kill_reason": str(row[21] or ""),
    }


def _wallet_ids_for_ppid(cursor, ppid: str) -> list[str]:
    cursor.execute(
        """
        WITH ids AS (
            SELECT wallet_id
            FROM platform_users
            WHERE user_did = %s
              AND COALESCE(status, 'active') = 'active'
              AND wallet_id IS NOT NULL
              AND wallet_id <> ''
            UNION
            SELECT wallet_id
            FROM customers
            WHERE customer_did = %s
              AND COALESCE(status, 'active') = 'active'
              AND wallet_id IS NOT NULL
              AND wallet_id <> ''
        )
        SELECT wallet_id FROM ids
        """,
        (ppid, ppid),
    )
    return [str(row[0] or "").strip() for row in (cursor.fetchall() or []) if row and str(row[0] or "").strip()]


def _backfill_runtime_from_legacy(*, runtime_id: str, wallet_id: str | None = None, ppid: str | None = None) -> dict[str, Any]:
    ensure_agent_ops_schema()
    from api.database import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        wallet_ids: list[str] = []
        if wallet_id:
            wallet_ids.append(wallet_id)
        if ppid:
            wallet_ids.extend(_wallet_ids_for_ppid(cursor, ppid))
        wallet_ids = [item for item in dict.fromkeys(wallet_ids) if item]
        if not wallet_ids:
            return {}
        try:
            cursor.execute(
                """
                SELECT wallet_id, runtime_id, agent_id, workspace_id, display_name,
                       policy_profile, risk_defaults_json, kill_switch_enabled,
                       active, last_connected_at, killed_at, kill_reason
                FROM wallet_firewall_runtimes
                WHERE runtime_id = %s AND wallet_id = ANY(%s)
                ORDER BY COALESCE(last_connected_at, updated_at, created_at) DESC
                LIMIT 1
                """,
                (runtime_id, wallet_ids),
            )
        except Exception:
            return {}
        row = cursor.fetchone()
        if not row:
            return {}
        resolved_wallet_id = str(row[0] or "")
        resolved_ppid = ppid
        if not resolved_ppid and resolved_wallet_id:
            cursor.execute(
                """
                WITH candidates AS (
                    SELECT user_did AS ppid, COALESCE(last_seen, created_at) AS seen_at
                    FROM platform_users
                    WHERE wallet_id = %s
                      AND COALESCE(status, 'active') = 'active'
                      AND user_did LIKE 'did:lemma:ppid_%%'
                    UNION ALL
                    SELECT customer_did AS ppid, created_at AS seen_at
                    FROM customers
                    WHERE wallet_id = %s
                      AND COALESCE(status, 'active') = 'active'
                      AND customer_did LIKE 'did:lemma:ppid_%%'
                )
                SELECT ppid
                FROM candidates
                ORDER BY seen_at DESC NULLS LAST
                LIMIT 1
                """,
                (resolved_wallet_id, resolved_wallet_id),
            )
            ppid_row = cursor.fetchone()
            resolved_ppid = str(ppid_row[0] or "").strip() if ppid_row else None
        risk_defaults = {}
        try:
            risk_defaults = json.loads(str(row[6] or "{}"))
        except Exception:
            risk_defaults = {}
        return upsert_runtime(
            runtime_id=str(row[1] or runtime_id),
            agent_id=str(row[2] or ""),
            workspace_id=str(row[3] or "") or None,
            display_name=str(row[4] or "") or None,
            policy_profile=str(row[5] or "lemma_firewall_default_v1"),
            risk_defaults=risk_defaults if isinstance(risk_defaults, dict) else {},
            kill_switch_enabled=bool(row[7]),
            owner_wallet_id=resolved_wallet_id or None,
            owner_ppid=resolved_ppid or None,
        )
    finally:
        cursor.close()
        conn.close()


def get_runtime(
    *,
    runtime_id: str,
    wallet_id: str | None = None,
    ppid: str | None = None,
    org_id: str | None = None,
    environment: str | None = None,
) -> dict[str, Any]:
    ensure_agent_ops_schema()
    from api.database import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        clauses = ["runtime_id = %s"]
        params: list[Any] = [runtime_id]
        if wallet_id:
            clauses.append("owner_wallet_id = %s")
            params.append(wallet_id)
        elif ppid:
            clauses.append("owner_ppid = %s")
            params.append(ppid)
        clauses.append("org_id = %s")
        params.append(_normalize_org_id(org_id))
        clauses.append("environment = %s")
        params.append(_normalize_environment(environment))
        cursor.execute(
            f"""
            SELECT runtime_id, agent_id, workspace_id, org_id, environment, root_type, site_id, display_name,
                   policy_profile_id, policy_profile_version, risk_defaults_json, trust_state, taint_epoch,
                   kill_switch_enabled, emergency_stopped, quota_json, active,
                   created_at, updated_at, last_connected_at, killed_at, kill_reason
            FROM runtimes
            WHERE {' AND '.join(clauses)}
            LIMIT 1
            """,
            tuple(params),
        )
        row = cursor.fetchone()
        if row:
            return _runtime_row_to_dict(row)
    finally:
        cursor.close()
        conn.close()
    return _backfill_runtime_from_legacy(runtime_id=runtime_id, wallet_id=wallet_id, ppid=ppid)


def list_runtimes(
    *,
    wallet_id: str | None = None,
    ppid: str | None = None,
    org_id: str | None = None,
    environment: str | None = None,
) -> list[dict[str, Any]]:
    ensure_agent_ops_schema()
    from api.database import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        clauses: list[str] = []
        params: list[Any] = []
        if wallet_id:
            clauses.append("owner_wallet_id = %s")
            params.append(wallet_id)
        if ppid:
            clauses.append("owner_ppid = %s")
            params.append(ppid)
        actor_clause = f"({' OR '.join(clauses)})" if clauses else "TRUE"
        where = f"WHERE {actor_clause} AND org_id = %s AND environment = %s"
        params.extend([_normalize_org_id(org_id), _normalize_environment(environment)])
        cursor.execute(
            f"""
            SELECT runtime_id, agent_id, workspace_id, org_id, environment, root_type, site_id, display_name,
                   policy_profile_id, policy_profile_version, risk_defaults_json, trust_state, taint_epoch,
                   kill_switch_enabled, emergency_stopped, quota_json, active,
                   created_at, updated_at, last_connected_at, killed_at, kill_reason
            FROM runtimes
            {where}
            ORDER BY COALESCE(last_connected_at, updated_at, created_at) DESC
            """,
            tuple(params),
        )
        rows = cursor.fetchall() or []
        if rows:
            return [_runtime_row_to_dict(row) for row in rows]
    finally:
        cursor.close()
        conn.close()

    if wallet_id:
        _backfill_runtime_from_legacy(runtime_id="lemma-firewall-default", wallet_id=wallet_id, ppid=ppid)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        clauses = []
        params = []
        if wallet_id:
            clauses.append("owner_wallet_id = %s")
            params.append(wallet_id)
        if ppid:
            clauses.append("owner_ppid = %s")
            params.append(ppid)
        actor_clause = f"({' OR '.join(clauses)})" if clauses else "TRUE"
        where = f"WHERE {actor_clause} AND org_id = %s AND environment = %s"
        params.extend([_normalize_org_id(org_id), _normalize_environment(environment)])
        cursor.execute(
            f"""
            SELECT runtime_id, agent_id, workspace_id, org_id, environment, root_type, site_id, display_name,
                   policy_profile_id, policy_profile_version, risk_defaults_json, trust_state, taint_epoch,
                   kill_switch_enabled, emergency_stopped, quota_json, active,
                   created_at, updated_at, last_connected_at, killed_at, kill_reason
            FROM runtimes
            {where}
            ORDER BY COALESCE(last_connected_at, updated_at, created_at) DESC
            """,
            tuple(params),
        )
        return [_runtime_row_to_dict(row) for row in (cursor.fetchall() or [])]
    finally:
        cursor.close()
        conn.close()


def kill_runtime(
    *,
    wallet_id: str,
    runtime_id: str,
    reason: str,
    ppid: str | None = None,
    org_id: str | None = None,
    environment: str | None = None,
) -> bool:
    ensure_agent_ops_schema()
    from api.database import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE runtimes
            SET active = FALSE, killed_at = NOW(), kill_reason = %s, updated_at = NOW()
            WHERE runtime_id = %s AND owner_wallet_id = %s AND org_id = %s AND environment = %s
            """,
            (reason, runtime_id, wallet_id, _normalize_org_id(org_id), _normalize_environment(environment)),
        )
        changed = cursor.rowcount > 0
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    if not changed:
        runtime = _backfill_runtime_from_legacy(runtime_id=runtime_id, wallet_id=wallet_id, ppid=ppid)
        if not runtime:
            return False
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE runtimes
                SET active = FALSE, killed_at = NOW(), kill_reason = %s, updated_at = NOW()
                WHERE runtime_id = %s AND owner_wallet_id = %s
                """,
                (reason, runtime_id, wallet_id),
            )
            changed = cursor.rowcount > 0
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    if changed:
        record_revocation(
            subject_type="runtime",
            subject_ref=runtime_id,
            runtime_id=runtime_id,
            delegator_ppid=ppid,
            reason_code="runtime_killed",
            revoked_by=ppid or wallet_id,
            metadata={"kill_reason": reason},
        )
    return changed


def _decision_reason_code(metadata: dict[str, Any], status_code: int | None, success: bool | None) -> str:
    reason_code = str(metadata.get("reason_code") or "").strip().upper()
    if reason_code:
        return reason_code
    if bool(success):
        return "ALLOW"
    if int(status_code or 0) == 401:
        return "AUTH_REQUIRED"
    if int(status_code or 0) == 403:
        return "POLICY_DENY"
    if int(status_code or 0) >= 500:
        return "UPSTREAM_ERROR"
    return "DENY"


def _parse_json_column(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return fallback
    return fallback


def _delegation_lineage_from_row(row) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "delegation_id": str(row[0] or ""),
        "token_id": str(row[1] or ""),
        "runtime_id": str(row[2] or ""),
        "delegator_ppid": str(row[3] or ""),
        "delegated_by_user_ref": str(row[4] or ""),
        "acting_for_ppid": str(row[5] or ""),
        "acting_for_user_ref": str(row[6] or ""),
        "requested_by_ppid": str(row[7] or ""),
        "requested_by_user_ref": str(row[8] or ""),
        "subject_type": str(row[9] or ""),
        "subject_ref": str(row[10] or ""),
        "audience": str(row[11] or ""),
        "scope": _parse_json_column(row[12], []),
        "allowed_sites": _parse_json_column(row[13], []),
        "resource_bounds": _parse_json_column(row[14], {}),
        "allowed_paths": _parse_json_column(row[15], []),
        "max_operations": int(row[16]) if row[16] is not None else None,
        "expires_at": row[17].isoformat() + "Z" if row[17] else None,
        "revoked_at": row[18].isoformat() + "Z" if row[18] else None,
        "status": str(row[19] or "active"),
        "reason": str(row[20] or ""),
        "task_hash": str(row[21] or ""),
    }


def _lookup_delegation_lineage(cursor, *, token_id: str | None, credential_ref: str | None) -> dict[str, Any] | None:
    candidates = []
    for value in [token_id, credential_ref]:
        text = str(value or "").strip()
        if text and text not in candidates:
            candidates.append(text)
    if not candidates:
        return None
    cursor.execute(
        """
        SELECT delegation_id, token_id, runtime_id, delegator_ppid, delegated_by_user_ref,
               acting_for_ppid, acting_for_user_ref, requested_by_ppid, requested_by_user_ref,
               subject_type, subject_ref, audience, scope_json, allowed_sites_json,
               resource_bounds_json, allowed_paths_json, max_operations, expires_at, revoked_at,
               status, reason, task_hash
        FROM delegations
        WHERE token_id = ANY(%s) OR subject_ref = ANY(%s)
        ORDER BY COALESCE(updated_at, created_at) DESC
        LIMIT 1
        """,
        (candidates, candidates),
    )
    return _delegation_lineage_from_row(cursor.fetchone())


def record_decision_logs(events: list[dict[str, Any]]) -> None:
    if not events:
        return
    ensure_agent_ops_schema()
    from api.database import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        rows: list[tuple[Any, ...]] = []
        for event in events:
            metadata_raw = event.get("metadata_json")
            if isinstance(metadata_raw, str):
                try:
                    metadata = json.loads(metadata_raw)
                except Exception:
                    metadata = {}
            elif isinstance(metadata_raw, dict):
                metadata = metadata_raw
            else:
                metadata = {}
            runtime_id = str(metadata.get("runtime_id") or "").strip() or None
            delegator_ppid = str(metadata.get("delegated_by_ppid") or "").strip() or None
            audience = str(metadata.get("token_audience") or "").strip().lower() or None
            org_id = _normalize_org_id(str(metadata.get("org_id") or ""))
            environment = _normalize_environment(str(metadata.get("environment") or ""))
            root_type = _normalize_root_type(str(metadata.get("root_type") or ""))
            workspace_id = None
            if event.get("token_id"):
                cursor.execute(
                    """
                    SELECT workspace_id
                    FROM delegations
                    WHERE token_id = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (event.get("token_id"),),
                )
                workspace_row = cursor.fetchone()
                if workspace_row and workspace_row[0]:
                    workspace_id = str(workspace_row[0])
            if not workspace_id and runtime_id:
                cursor.execute(
                    "SELECT workspace_id FROM runtimes WHERE runtime_id = %s LIMIT 1",
                    (runtime_id,),
                )
                workspace_row = cursor.fetchone()
                if workspace_row and workspace_row[0]:
                    workspace_id = str(workspace_row[0])
            if not workspace_id and delegator_ppid:
                workspace_id = ensure_workspace_context(ppid=delegator_ppid, site_ids=[audience] if audience else None)
            status_code = int(event.get("status_code") or 0) if event.get("status_code") is not None else None
            success = bool(event.get("success")) if event.get("success") is not None else None
            rows.append(
                (
                    workspace_id,
                    org_id,
                    environment,
                    root_type,
                    runtime_id,
                    str(metadata.get("agent_id") or "").strip() or None,
                    delegator_ppid,
                    event.get("token_id"),
                    event.get("token_id"),
                    event.get("path"),
                    event.get("action"),
                    event.get("resource"),
                    event.get("method"),
                    event.get("path"),
                    "allow" if bool(success) else "deny",
                    _decision_reason_code(metadata, status_code, success),
                    str(metadata.get("policy_profile") or "").strip() or None,
                    str(metadata.get("policy_version") or "v1").strip() or "v1",
                    str(metadata.get("request_id") or metadata.get("request_correlation_id") or "").strip() or None,
                    str(metadata.get("trust_state") or "").strip() or None,
                    int(metadata.get("taint_epoch") or 0) if metadata.get("taint_epoch") is not None else None,
                    status_code,
                    json.dumps(metadata),
                )
            )
        if rows:
            cursor.executemany(
                """
                INSERT INTO decision_logs (
                    workspace_id, org_id, environment, root_type, runtime_id, agent_id, delegator_ppid, credential_ref, token_id,
                    route, action, resource, method, path, decision, reason_code,
                    policy_profile, policy_version, request_correlation_id,
                    trust_state, taint_epoch, status_code, metadata_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                rows,
            )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def list_decisions(
    *,
    delegator_ppid: str,
    runtime_id: str | None,
    limit: int,
    org_id: str | None = None,
    environment: str | None = None,
) -> list[dict[str, Any]]:
    ensure_agent_ops_schema()
    from api.database import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        filters = ["delegator_ppid = %s"]
        params: list[Any] = [delegator_ppid]
        if runtime_id:
            filters.append("runtime_id = %s")
            params.append(runtime_id)
        filters.append("org_id = %s")
        params.append(_normalize_org_id(org_id))
        filters.append("environment = %s")
        params.append(_normalize_environment(environment))
        params.append(limit)
        cursor.execute(
            f"""
            SELECT id, timestamp, credential_ref, action, resource, method, path,
                   status_code, decision, reason_code, policy_profile, runtime_id,
                   delegator_ppid, request_correlation_id
            FROM decision_logs
            WHERE {' AND '.join(filters)}
            ORDER BY timestamp DESC, id DESC
            LIMIT %s
            """,
            tuple(params),
        )
        rows = cursor.fetchall() or []
        if rows:
            decisions = []
            for row in rows:
                item = {
                    "decision_id": int(row[0]),
                    "timestamp": row[1].isoformat() + "Z" if row[1] else None,
                    "credential_ref": str(row[2] or ""),
                    "action": str(row[3] or ""),
                    "resource": str(row[4] or ""),
                    "method": str(row[5] or "").upper(),
                    "path": str(row[6] or ""),
                    "status_code": int(row[7]) if row[7] is not None else None,
                    "decision": str(row[8] or ""),
                    "reason_code": str(row[9] or ""),
                    "policy_profile": str(row[10] or ""),
                    "runtime_id": str(row[11] or ""),
                    "delegator_ppid": str(row[12] or ""),
                    "request_correlation_id": str(row[13] or ""),
                }
                lineage = _lookup_delegation_lineage(
                    cursor,
                    token_id=item.get("credential_ref"),
                    credential_ref=item.get("credential_ref"),
                )
                if lineage:
                    item["delegation_lineage"] = lineage
                decisions.append(item)
            return decisions

        filters = ["(COALESCE(ac.authorized_by_ppid, al.metadata->>'delegated_by_ppid') = %s)"]
        legacy_params: list[Any] = [delegator_ppid]
        if runtime_id:
            filters.append("(al.metadata->>'runtime_id' = %s)")
            legacy_params.append(runtime_id)
        legacy_params.append(limit)
        cursor.execute(
            f"""
            SELECT al.id, al.timestamp, al.token_id, al.action, al.resource,
                   al.method, al.path, al.status_code, al.success, al.metadata,
                   COALESCE(ac.authorized_by_ppid, al.metadata->>'delegated_by_ppid') AS effective_ppid
            FROM agent_audit_log al
            LEFT JOIN agent_credentials ac ON al.credential_id = ac.id
            WHERE {' AND '.join(filters)}
            ORDER BY al.timestamp DESC
            LIMIT %s
            """,
            tuple(legacy_params),
        )
        legacy_rows = cursor.fetchall() or []
        decisions: list[dict[str, Any]] = []
        for row in legacy_rows:
            metadata = row[9] if isinstance(row[9], dict) else json.loads(row[9] or "{}")
            status_code = int(row[7] or 0) if row[7] is not None else None
            success = bool(row[8]) if row[8] is not None else None
            item = {
                "decision_id": int(row[0]),
                "timestamp": row[1].isoformat() + "Z" if row[1] else None,
                "credential_ref": str(row[2] or ""),
                "action": str(row[3] or ""),
                "resource": str(row[4] or ""),
                "method": str(row[5] or "").upper(),
                "path": str(row[6] or ""),
                "status_code": status_code,
                "decision": "allow" if bool(success) else "deny",
                "reason_code": _decision_reason_code(metadata, status_code, success),
                "policy_profile": str(metadata.get("policy_profile") or ""),
                "runtime_id": str(metadata.get("runtime_id") or ""),
                "delegator_ppid": str(row[10] or delegator_ppid),
                "request_correlation_id": str(metadata.get("request_id") or metadata.get("request_correlation_id") or ""),
            }
            lineage = _lookup_delegation_lineage(
                cursor,
                token_id=item.get("credential_ref"),
                credential_ref=item.get("credential_ref"),
            )
            if lineage:
                item["delegation_lineage"] = lineage
            decisions.append(item)
        return decisions
    finally:
        cursor.close()
        conn.close()


def get_decision(
    *,
    decision_id: int,
    delegator_ppid: str,
    org_id: str | None = None,
    environment: str | None = None,
) -> dict[str, Any]:
    ensure_agent_ops_schema()
    from api.database import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, timestamp, credential_ref, action, resource, method, path, status_code,
                   decision, reason_code, policy_profile, policy_version, runtime_id,
                   delegator_ppid, request_correlation_id, trust_state, taint_epoch, metadata_json
            FROM decision_logs
            WHERE id = %s AND delegator_ppid = %s AND org_id = %s AND environment = %s
            LIMIT 1
            """,
            (decision_id, delegator_ppid, _normalize_org_id(org_id), _normalize_environment(environment)),
        )
        row = cursor.fetchone()
        if row:
            metadata = row[17] if isinstance(row[17], dict) else json.loads(row[17] or "{}")
            item = {
                "decision_id": int(row[0]),
                "timestamp": row[1].isoformat() + "Z" if row[1] else None,
                "credential_ref": str(row[2] or ""),
                "action": str(row[3] or ""),
                "resource": str(row[4] or ""),
                "method": str(row[5] or "").upper(),
                "path": str(row[6] or ""),
                "status_code": int(row[7]) if row[7] is not None else None,
                "decision": str(row[8] or ""),
                "reason_code": str(row[9] or ""),
                "policy_profile": str(row[10] or ""),
                "policy_version": str(row[11] or "v1"),
                "runtime_id": str(row[12] or ""),
                "delegator_ppid": str(row[13] or ""),
                "request_correlation_id": str(row[14] or ""),
                "trust_state": str(row[15] or ""),
                "taint_epoch": int(row[16]) if row[16] is not None else None,
                "metadata": metadata if isinstance(metadata, dict) else {},
            }
            lineage = _lookup_delegation_lineage(
                cursor,
                token_id=item.get("credential_ref"),
                credential_ref=item.get("credential_ref"),
            )
            if lineage:
                item["delegation_lineage"] = lineage
            return item

        cursor.execute(
            """
            SELECT al.id, al.timestamp, al.token_id, al.action, al.resource,
                   al.method, al.path, al.status_code, al.success, al.metadata,
                   COALESCE(ac.authorized_by_ppid, al.metadata->>'delegated_by_ppid') AS effective_ppid
            FROM agent_audit_log al
            LEFT JOIN agent_credentials ac ON al.credential_id = ac.id
            WHERE al.id = %s
            LIMIT 1
            """,
            (decision_id,),
        )
        legacy_row = cursor.fetchone()
        if not legacy_row:
            return {}
        effective_ppid = str(legacy_row[10] or "").strip()
        if effective_ppid and effective_ppid != delegator_ppid:
            return {}
        metadata = legacy_row[9] if isinstance(legacy_row[9], dict) else json.loads(legacy_row[9] or "{}")
        status_code = int(legacy_row[7] or 0) if legacy_row[7] is not None else None
        success = bool(legacy_row[8]) if legacy_row[8] is not None else None
        item = {
            "decision_id": int(legacy_row[0]),
            "timestamp": legacy_row[1].isoformat() + "Z" if legacy_row[1] else None,
            "credential_ref": str(legacy_row[2] or ""),
            "action": str(legacy_row[3] or ""),
            "resource": str(legacy_row[4] or ""),
            "method": str(legacy_row[5] or "").upper(),
            "path": str(legacy_row[6] or ""),
            "status_code": status_code,
            "decision": "allow" if bool(success) else "deny",
            "reason_code": _decision_reason_code(metadata, status_code, success),
            "policy_profile": str(metadata.get("policy_profile") or ""),
            "policy_version": str(metadata.get("policy_version") or "v1"),
            "runtime_id": str(metadata.get("runtime_id") or ""),
            "delegator_ppid": effective_ppid or delegator_ppid,
            "request_correlation_id": str(metadata.get("request_id") or metadata.get("request_correlation_id") or ""),
            "trust_state": str(metadata.get("trust_state") or ""),
            "taint_epoch": int(metadata.get("taint_epoch") or 0) if metadata.get("taint_epoch") is not None else None,
            "metadata": metadata if isinstance(metadata, dict) else {},
        }
        lineage = _lookup_delegation_lineage(
            cursor,
            token_id=item.get("credential_ref"),
            credential_ref=item.get("credential_ref"),
        )
        if lineage:
            item["delegation_lineage"] = lineage
        return item
    finally:
        cursor.close()
        conn.close()


def list_policy_profiles(*, org_id: str | None = None, environment: str | None = None) -> list[dict[str, Any]]:
    ensure_agent_ops_schema()
    from api.database import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT policy_profile_id, display_name, description, policy_document, policy_version,
                   published_version, previous_published_version, status, root_type, org_id, environment, updated_at
            FROM policy_profiles
            WHERE org_id = %s AND environment = %s
            ORDER BY updated_at DESC, policy_profile_id ASC
            """,
            (_normalize_org_id(org_id), _normalize_environment(environment)),
        )
        rows = cursor.fetchall() or []
        results: list[dict[str, Any]] = []
        for row in rows:
            policy_document = row[3] if isinstance(row[3], dict) else json.loads(row[3] or "{}")
            results.append(
                {
                    "policy_profile_id": str(row[0] or ""),
                    "display_name": str(row[1] or ""),
                    "description": str(row[2] or ""),
                    "policy_document": policy_document if isinstance(policy_document, dict) else {},
                    "policy_version": str(row[4] or "v1"),
                    "published_version": str(row[5] or row[4] or "v1"),
                    "previous_published_version": str(row[6] or ""),
                    "status": str(row[7] or "active"),
                    "root_type": _normalize_root_type(row[8]),
                    "org_id": str(row[9] or "org_default"),
                    "environment": str(row[10] or "prod"),
                    "updated_at": row[11].isoformat() + "Z" if row[11] else None,
                }
            )
        return results
    finally:
        cursor.close()
        conn.close()


def upsert_policy_profile(
    *,
    policy_profile_id: str,
    display_name: str,
    description: str | None,
    policy_document: dict[str, Any] | None,
    policy_version: str,
    root_type: str | None,
    org_id: str | None,
    environment: str | None,
    actor_ref: str | None,
) -> dict[str, Any]:
    ensure_agent_ops_schema()
    from api.database import get_db_connection

    normalized_profile_id = _clean_identifier(policy_profile_id, "lemma_firewall_default_v1", max_len=120)
    normalized_version = _clean_identifier(policy_version, "v1", max_len=64)
    normalized_org_id = _normalize_org_id(org_id)
    normalized_env = _normalize_environment(environment)
    normalized_root = _normalize_root_type(root_type)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO policy_profiles (
                policy_profile_id, workspace_id, policy_version, display_name, description, policy_document,
                is_active, root_type, org_id, environment, status, published_version, updated_at
            )
            VALUES (%s, NULL, %s, %s, %s, %s, TRUE, %s, %s, %s, 'active', %s, NOW())
            ON CONFLICT (policy_profile_id)
            DO UPDATE SET
                policy_version = EXCLUDED.policy_version,
                display_name = EXCLUDED.display_name,
                description = EXCLUDED.description,
                policy_document = EXCLUDED.policy_document,
                root_type = EXCLUDED.root_type,
                org_id = EXCLUDED.org_id,
                environment = EXCLUDED.environment,
                status = 'active',
                updated_at = NOW()
            RETURNING policy_profile_id, display_name, description, policy_document, policy_version, root_type, org_id, environment, updated_at
            """,
            (
                normalized_profile_id,
                normalized_version,
                display_name[:255],
                description or None,
                json.dumps(policy_document or {}),
                normalized_root,
                normalized_org_id,
                normalized_env,
                normalized_version,
            ),
        )
        row = cursor.fetchone()
        cursor.execute(
            """
            INSERT INTO policy_profile_revisions (
                policy_profile_id, org_id, environment, policy_version, policy_document, change_summary, created_by
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (policy_profile_id, org_id, environment, policy_version)
            DO NOTHING
            """,
            (
                normalized_profile_id,
                normalized_org_id,
                normalized_env,
                normalized_version,
                json.dumps(policy_document or {}),
                "draft_update",
                actor_ref or None,
            ),
        )
        conn.commit()
        return {
            "policy_profile_id": str(row[0] or normalized_profile_id),
            "display_name": str(row[1] or ""),
            "description": str(row[2] or ""),
            "policy_document": row[3] if isinstance(row[3], dict) else json.loads(row[3] or "{}"),
            "policy_version": str(row[4] or normalized_version),
            "root_type": _normalize_root_type(row[5]),
            "org_id": str(row[6] or normalized_org_id),
            "environment": str(row[7] or normalized_env),
            "updated_at": row[8].isoformat() + "Z" if row[8] else None,
        }
    finally:
        cursor.close()
        conn.close()


def publish_policy_profile(
    *,
    policy_profile_id: str,
    policy_version: str,
    org_id: str | None,
    environment: str | None,
) -> bool:
    ensure_agent_ops_schema()
    from api.database import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE policy_profiles
            SET previous_published_version = published_version,
                published_version = %s,
                policy_version = %s,
                status = 'published',
                updated_at = NOW()
            WHERE policy_profile_id = %s AND org_id = %s AND environment = %s
            """,
            (
                _clean_identifier(policy_version, "v1", 64),
                _clean_identifier(policy_version, "v1", 64),
                _clean_identifier(policy_profile_id, "lemma_firewall_default_v1", 120),
                _normalize_org_id(org_id),
                _normalize_environment(environment),
            ),
        )
        changed = cursor.rowcount > 0
        if changed:
            cursor.execute(
                """
                UPDATE runtimes
                SET policy_profile_version = %s, updated_at = NOW()
                WHERE policy_profile_id = %s AND org_id = %s AND environment = %s
                """,
                (
                    _clean_identifier(policy_version, "v1", 64),
                    _clean_identifier(policy_profile_id, "lemma_firewall_default_v1", 120),
                    _normalize_org_id(org_id),
                    _normalize_environment(environment),
                ),
            )
        conn.commit()
        return changed
    finally:
        cursor.close()
        conn.close()


def rollback_policy_profile(*, policy_profile_id: str, org_id: str | None, environment: str | None) -> bool:
    ensure_agent_ops_schema()
    from api.database import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE policy_profiles
            SET policy_version = COALESCE(previous_published_version, published_version, policy_version),
                published_version = COALESCE(previous_published_version, published_version, policy_version),
                status = 'published',
                updated_at = NOW()
            WHERE policy_profile_id = %s AND org_id = %s AND environment = %s
            RETURNING published_version
            """,
            (
                _clean_identifier(policy_profile_id, "lemma_firewall_default_v1", 120),
                _normalize_org_id(org_id),
                _normalize_environment(environment),
            ),
        )
        row = cursor.fetchone()
        if row and row[0]:
            cursor.execute(
                """
                UPDATE runtimes
                SET policy_profile_version = %s, updated_at = NOW()
                WHERE policy_profile_id = %s AND org_id = %s AND environment = %s
                """,
                (
                    str(row[0]),
                    _clean_identifier(policy_profile_id, "lemma_firewall_default_v1", 120),
                    _normalize_org_id(org_id),
                    _normalize_environment(environment),
                ),
            )
        conn.commit()
        return bool(row)
    finally:
        cursor.close()
        conn.close()


def upsert_runtime_org_controls(
    *,
    org_id: str | None,
    environment: str | None,
    emergency_stop_enabled: bool,
    quota_json: dict[str, Any] | None,
    updated_by: str | None,
) -> dict[str, Any]:
    ensure_agent_ops_schema()
    from api.database import get_db_connection

    normalized_org_id = _normalize_org_id(org_id)
    normalized_env = _normalize_environment(environment)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO runtime_org_controls (org_id, environment, emergency_stop_enabled, quota_json, updated_by, updated_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (org_id, environment)
            DO UPDATE SET
                emergency_stop_enabled = EXCLUDED.emergency_stop_enabled,
                quota_json = EXCLUDED.quota_json,
                updated_by = EXCLUDED.updated_by,
                updated_at = NOW()
            RETURNING org_id, environment, emergency_stop_enabled, quota_json, updated_by, updated_at
            """,
            (normalized_org_id, normalized_env, bool(emergency_stop_enabled), json.dumps(quota_json or {}), updated_by or None),
        )
        row = cursor.fetchone()
        cursor.execute(
            """
            UPDATE runtimes
            SET emergency_stopped = %s,
                quota_json = %s,
                active = CASE WHEN %s THEN FALSE ELSE active END,
                updated_at = NOW()
            WHERE org_id = %s AND environment = %s
            """,
            (
                bool(emergency_stop_enabled),
                json.dumps(quota_json or {}),
                bool(emergency_stop_enabled),
                normalized_org_id,
                normalized_env,
            ),
        )
        conn.commit()
        return {
            "org_id": str(row[0] or normalized_org_id),
            "environment": str(row[1] or normalized_env),
            "emergency_stop_enabled": bool(row[2]),
            "quota_json": row[3] if isinstance(row[3], dict) else json.loads(row[3] or "{}"),
            "updated_by": str(row[4] or ""),
            "updated_at": row[5].isoformat() + "Z" if row[5] else None,
        }
    finally:
        cursor.close()
        conn.close()

def backfill_agent_ops_schema() -> dict[str, int]:
    ensure_agent_ops_schema()
    from api.database import get_db_connection

    summary = {
        "workspaces": 0,
        "runtimes": 0,
        "delegations": 0,
        "revocations": 0,
    }

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT DISTINCT s.site_id, s.admin_email, s.company_name
            FROM sites s
            """
        )
        for site_id, admin_email, company_name in cursor.fetchall() or []:
            ensure_workspace_context(
                email=str(admin_email or "").strip().lower() or None,
                site_ids=[str(site_id or "")],
                display_name=str(company_name or site_id or "Workspace"),
                membership_role="owner",
            )
            summary["workspaces"] += 1

        try:
            cursor.execute(
                """
                SELECT wallet_id, runtime_id, agent_id, workspace_id, display_name,
                       policy_profile, risk_defaults_json, kill_switch_enabled
                FROM wallet_firewall_runtimes
                """
            )
            runtime_rows = cursor.fetchall() or []
        except Exception:
            runtime_rows = []
        for row in runtime_rows:
            wallet_id = str(row[0] or "").strip() or None
            resolved_ppid = None
            if wallet_id:
                cursor.execute(
                    """
                    WITH candidates AS (
                        SELECT user_did AS ppid, COALESCE(last_seen, created_at) AS seen_at
                        FROM platform_users
                        WHERE wallet_id = %s
                          AND COALESCE(status, 'active') = 'active'
                          AND user_did LIKE 'did:lemma:ppid_%%'
                        UNION ALL
                        SELECT customer_did AS ppid, created_at AS seen_at
                        FROM customers
                        WHERE wallet_id = %s
                          AND COALESCE(status, 'active') = 'active'
                          AND customer_did LIKE 'did:lemma:ppid_%%'
                    )
                    SELECT ppid
                    FROM candidates
                    ORDER BY seen_at DESC NULLS LAST
                    LIMIT 1
                    """,
                    (wallet_id, wallet_id),
                )
                ppid_row = cursor.fetchone()
                resolved_ppid = str(ppid_row[0] or "").strip() if ppid_row and ppid_row[0] else None
            risk_defaults = {}
            try:
                risk_defaults = json.loads(str(row[6] or "{}"))
            except Exception:
                risk_defaults = {}
            upsert_runtime(
                runtime_id=str(row[1] or ""),
                agent_id=str(row[2] or ""),
                workspace_id=str(row[3] or "") or None,
                display_name=str(row[4] or "") or None,
                policy_profile=str(row[5] or "lemma_firewall_default_v1"),
                risk_defaults=risk_defaults if isinstance(risk_defaults, dict) else {},
                kill_switch_enabled=bool(row[7]),
                owner_wallet_id=wallet_id,
                owner_ppid=resolved_ppid,
            )
            summary["runtimes"] += 1

        cursor.execute(
            """
            SELECT token_id, authorized_by_ppid, authorized_by_email, scope, allowed_sites,
                   expires_at, description, task_description, task_hash, allowed_paths, max_operations
            FROM agent_credentials
            """
        )
        for row in cursor.fetchall() or []:
            token_id = str(row[0] or "")
            cursor.execute("SELECT 1 FROM delegations WHERE token_id = %s LIMIT 1", (token_id,))
            if cursor.fetchone():
                continue
            description_meta = {}
            raw_description = row[6]
            if isinstance(raw_description, dict):
                description_meta = raw_description
            elif isinstance(raw_description, str):
                try:
                    parsed = json.loads(raw_description)
                    description_meta = parsed if isinstance(parsed, dict) else {}
                except Exception:
                    description_meta = {}
            scope = row[3] if isinstance(row[3], list) else json.loads(row[3] or "[]")
            allowed_sites = row[4] if isinstance(row[4], list) else json.loads(row[4] or "[]")
            allowed_paths = row[9] if isinstance(row[9], list) else json.loads(row[9] or "[]")
            record_delegation(
                token_id=token_id,
                delegation_id=str(description_meta.get("delegation_id") or f"dlg_{token_id}"),
                delegator_ppid=str(row[1] or "") or None,
                delegated_by_user_ref=str(description_meta.get("delegated_by_user_ref") or row[2] or "") or None,
                acting_for_ppid=str(description_meta.get("acting_for_ppid") or row[1] or "") or None,
                acting_for_user_ref=str(description_meta.get("acting_for_user_ref") or "") or None,
                requested_by_ppid=str(description_meta.get("requested_by_ppid") or row[1] or "") or None,
                requested_by_user_ref=str(description_meta.get("requested_by_user_ref") or "") or None,
                subject_type="agent_credential",
                subject_ref=token_id,
                scope=scope if isinstance(scope, list) else [],
                allowed_sites=allowed_sites if isinstance(allowed_sites, list) else [],
                audience=str(description_meta.get("audience") or "") or None,
                task_description=str(row[7] or "") or None,
                task_hash=str(row[8] or "") or None,
                allowed_paths=allowed_paths if isinstance(allowed_paths, list) else [],
                max_operations=int(row[10]) if row[10] is not None else None,
                expires_at=row[5],
                reason=str(description_meta.get("delegation_reason") or "") or None,
            )
            summary["delegations"] += 1

        cursor.execute(
            """
            SELECT COALESCE(credential_id, lemma_id), revocation_type, ppid, reason, revoked_by, revoked_at
            FROM revocation_list
            """
        )
        for subject_ref, revocation_type, ppid, reason, revoked_by, revoked_at in cursor.fetchall() or []:
            cursor.execute(
                """
                SELECT 1
                FROM agent_ops_revocations
                WHERE subject_ref = %s AND subject_type = 'proof'
                LIMIT 1
                """,
                (subject_ref,),
            )
            if cursor.fetchone():
                continue
            cursor.execute(
                """
                INSERT INTO agent_ops_revocations (
                    revocation_id, workspace_id, subject_type, subject_ref, delegator_ppid,
                    reason_code, revoked_by, revoked_at, metadata_json
                )
                VALUES (%s, %s, 'proof', %s, %s, %s, %s, %s, %s)
                """,
                (
                    f"rev_{secrets.token_urlsafe(8)}",
                    ensure_workspace_context(ppid=str(ppid or "").strip() or None) if ppid else None,
                    str(subject_ref or ""),
                    str(ppid or "") or None,
                    str(revocation_type or "legacy_revocation"),
                    str(revoked_by or "") or None,
                    revoked_at,
                    json.dumps({"reason": reason}),
                ),
            )
            summary["revocations"] += 1
        conn.commit()
        return summary
    finally:
        cursor.close()
        conn.close()
