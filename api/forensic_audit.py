"""
Server-side forensic action proof capture for high-risk platform mutations.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from flask import g, request

logger = logging.getLogger(__name__)


def _redact_credential(credential: dict) -> dict:
    """Store enough VC material for offline re-verification without excess payload."""
    if not isinstance(credential, dict):
        return {}
    claims = credential.get("claims") or credential.get("credentialSubject") or {}
    return {
        "id": credential.get("id"),
        "subject": credential.get("subject") or credential.get("sub"),
        "issuer": credential.get("issuer"),
        "packageType": credential.get("packageType") or claims.get("packageType"),
        "permissionId": claims.get("permissionId") or claims.get("permission_id"),
        "siteId": claims.get("siteId") or claims.get("site_id"),
        "scope": claims.get("scope"),
        "proof": credential.get("proof"),
        "signatureValueWeb": credential.get("signatureValueWeb"),
        "expiresAt": claims.get("expiresAt") or claims.get("expires_at"),
    }


def _verified_credential_from_request() -> Optional[dict]:
    try:
        from api.authz_engine import extract_user_lemma_principal

        principal, _error = extract_user_lemma_principal(request.headers)
        if not principal:
            return None
        raw = request.headers.get("X-Lemma-Credential")
        if not raw:
            return None
        text = str(raw).strip()
        if text.startswith("{"):
            import json
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        import base64
        import json
        padded = text + ("=" * (-len(text) % 4))
        decoded = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
        parsed = json.loads(decoded)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def build_action_proof(
    *,
    action: str,
    site_id: Optional[str] = None,
    resource: Optional[str] = None,
) -> Dict[str, Any]:
    credential = _verified_credential_from_request()
    proof_header = (request.headers.get("X-Lemma-Proof") or "").strip()
    proof: Dict[str, Any] = {
        "action": action,
        "route": request.path,
        "method": request.method,
        "site_id": site_id,
        "resource": resource,
        "ppid": getattr(g, "ppid", None),
        "credential_id": getattr(g, "credential_id", None),
        "permission_id": getattr(g, "permission_id", None),
        "auth_method": getattr(g, "auth_method", None),
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "proof_header_present": bool(proof_header),
    }
    if credential:
        proof["credential"] = _redact_credential(credential)
        if proof.get("ppid") is None:
            proof["ppid"] = credential.get("subject") or credential.get("sub")
        if proof.get("credential_id") is None:
            proof["credential_id"] = credential.get("id")
    agent_info = getattr(g, "agent_credential", None)
    if isinstance(agent_info, dict):
        proof["agent_token_id"] = agent_info.get("token_id")
        proof["authorized_by_ppid"] = agent_info.get("authorized_by_ppid")
    return proof


def capture_action_proof(
    *,
    action: str,
    site_id: Optional[str] = None,
    resource: Optional[str] = None,
) -> None:
    """Persist verified credential evidence for a successful mutation."""
    try:
        from api.audit_logger import AuditEvent, log_event

        proof = build_action_proof(action=action, site_id=site_id, resource=resource)
        ppid = proof.get("ppid")
        log_event(
            AuditEvent.ADMIN_ACTION,
            result="success",
            user_did=str(ppid) if ppid else None,
            site_id=site_id,
            resource=resource or request.path,
            action=action,
            credential_id=proof.get("credential_id"),
            metadata={"action_proof": deepcopy(proof)},
        )
    except Exception as exc:
        logger.warning("Failed to capture action proof for %s: %s", action, exc)
