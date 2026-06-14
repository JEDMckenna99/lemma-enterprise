"""
Shared request principal resolution for credential and agent delegation paths.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Optional, Tuple

from auth.permissions import is_admin_permission


def get_context_ppid() -> Optional[str]:
    """Return PPID set on Flask g by auth decorators."""
    try:
        from flask import g

        ppid = getattr(g, "ppid", None)
        if ppid and str(ppid).startswith("did:lemma:ppid_"):
            return str(ppid)
    except RuntimeError:
        return None
    return None


def resolve_admin_principal(*, request_path: str | None = None) -> Tuple[Any | None, Optional[str]]:
    """
    Resolve an admin principal from decorator context, lemma header, or agent token.
    """
    from flask import g, request

    path = request_path or request.path

    if getattr(g, "authenticated", False) and getattr(g, "is_admin", False):
        ppid = get_context_ppid()
        if ppid:
            return SimpleNamespace(
                ppid=ppid,
                permission_id=getattr(g, "permission_id", None) or "admin_access",
                scope=getattr(g, "scope", None) or ["admin"],
                auth_method=getattr(g, "auth_method", None) or "credential",
            ), None

    from api.authz_engine import extract_user_lemma_principal

    principal, error = extract_user_lemma_principal(request.headers)
    if principal and (
        is_admin_permission(principal.permission_id)
        or "admin" in (principal.scope or [])
    ):
        return principal, None

    from auth.agent_principal import extract_agent_admin_principal

    agent_principal, agent_error, _info = extract_agent_admin_principal(
        request.headers,
        request_path=path,
    )
    if agent_principal:
        return agent_principal, None

    return None, error or agent_error or "admin_required"
