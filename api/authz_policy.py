"""
Central authz policy matrix and deny-reason catalog.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RouteAuthPolicy:
    required_scope: str
    allowed_principals: tuple[str, ...]
    site_binding_required: bool = False


# Phase 5 bootstrap matrix for highest-traffic protected API routes.
ROUTE_AUTHZ_POLICY: dict[tuple[str, str], RouteAuthPolicy] = {
    ("GET", "/api/developer/sites"): RouteAuthPolicy(
        required_scope="read",
        allowed_principals=("user_lemma", "agent_token", "access_token", "api_key"),
    ),
    ("POST", "/api/developer/sites"): RouteAuthPolicy(
        required_scope="write",
        allowed_principals=("user_lemma", "agent_token", "access_token", "api_key"),
    ),
    ("GET", "/api/agent/credentials"): RouteAuthPolicy(
        required_scope="read",
        allowed_principals=("user_lemma", "agent_token", "access_token", "api_key"),
    ),
    ("POST", "/api/agent/credentials/issue"): RouteAuthPolicy(
        required_scope="write",
        allowed_principals=("user_lemma", "agent_token", "access_token"),
    ),
}


AUTH_ERROR_CATALOG: dict[str, tuple[int, str]] = {
    "auth_required": (401, "Authentication required"),
    "missing_lemma_header": (401, "X-Lemma-Credential header required"),
    "invalid_lemma_header": (401, "Invalid X-Lemma-Credential header"),
    "invalid_lemma_subject": (401, "Credential subject is invalid"),
    "credential_id_mismatch": (401, "Credential ID header mismatch"),
    "invalid_lemma": (401, "Credential verification failed"),
    "missing_scope": (403, "Insufficient scope"),
    "site_mismatch": (403, "Credential site binding mismatch"),
}


def get_policy_for_request(method: str, path: str) -> Optional[RouteAuthPolicy]:
    """Resolve policy by exact method+path match."""
    if not method or not path:
        return None
    return ROUTE_AUTHZ_POLICY.get((str(method).upper(), str(path)))


def get_error_defaults(code: str) -> tuple[int, str]:
    """Return default (status, message) for a known auth error code."""
    if not code:
        return 401, "Authentication required"
    return AUTH_ERROR_CATALOG.get(code, (401, "Authentication required"))

