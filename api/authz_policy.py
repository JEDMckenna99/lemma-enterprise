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
    risk_tier: str = "low"
    auth_mode: str = "compat_bearer"
    compat_bearer_sunset_utc: Optional[str] = None


# Principal sets: mutations require verified credential or agent token (PPID-bound).
READ_PRINCIPALS = ("user_lemma", "agent_token", "access_token", "api_key")
MUTATE_PRINCIPALS = ("user_lemma", "agent_token", "access_token")
API_KEY_ONLY_PRINCIPALS = ("api_key",)


# Expanded matrix for protected API routes.
ROUTE_AUTHZ_POLICY: dict[tuple[str, str], RouteAuthPolicy] = {
    # Developer platform
    ("GET", "/api/developer/stats"): RouteAuthPolicy(
        required_scope="read",
        allowed_principals=READ_PRINCIPALS,
    ),
    ("GET", "/api/developer/sites"): RouteAuthPolicy(
        required_scope="read",
        allowed_principals=READ_PRINCIPALS,
    ),
    ("POST", "/api/developer/sites"): RouteAuthPolicy(
        required_scope="write",
        allowed_principals=MUTATE_PRINCIPALS,
        auth_mode="credential_required",
    ),
    ("GET", "/api/developer/sites/<site_id>"): RouteAuthPolicy(
        required_scope="read",
        allowed_principals=READ_PRINCIPALS,
        site_binding_required=True,
    ),
    ("GET", "/api/developer/sites/<site_id>/bootstrap-status"): RouteAuthPolicy(
        required_scope="read",
        allowed_principals=READ_PRINCIPALS,
        site_binding_required=True,
    ),
    ("POST", "/api/developer/sites/<site_id>/bootstrap-admin"): RouteAuthPolicy(
        required_scope="admin",
        allowed_principals=MUTATE_PRINCIPALS,
        site_binding_required=True,
        risk_tier="critical",
        auth_mode="proof_required",
    ),
    ("POST", "/api/developer/sites/<site_id>/admin-transfer-token"): RouteAuthPolicy(
        required_scope="admin",
        allowed_principals=MUTATE_PRINCIPALS,
        site_binding_required=True,
        risk_tier="high",
        auth_mode="proof_required",
    ),
    ("POST", "/api/developer/credential-transfer/redeem"): RouteAuthPolicy(
        required_scope="write",
        allowed_principals=MUTATE_PRINCIPALS,
    ),
    ("GET", "/api/developer/sites/<site_id>/stats-summary"): RouteAuthPolicy(
        required_scope="read",
        allowed_principals=READ_PRINCIPALS,
        site_binding_required=True,
    ),
    ("GET", "/api/developer/sites/<site_id>/keys"): RouteAuthPolicy(
        required_scope="read",
        allowed_principals=READ_PRINCIPALS,
        site_binding_required=True,
    ),
    ("POST", "/api/developer/sites/<site_id>/keys"): RouteAuthPolicy(
        required_scope="admin",
        allowed_principals=MUTATE_PRINCIPALS,
        site_binding_required=True,
        risk_tier="high",
        auth_mode="proof_required",
    ),
    ("POST", "/api/developer/sites/<site_id>/keys/<key_id>/rotate"): RouteAuthPolicy(
        required_scope="admin",
        allowed_principals=MUTATE_PRINCIPALS,
        site_binding_required=True,
        risk_tier="high",
        auth_mode="proof_required",
    ),
    ("DELETE", "/api/developer/sites/<site_id>/keys/<key_id>"): RouteAuthPolicy(
        required_scope="admin",
        allowed_principals=MUTATE_PRINCIPALS,
        site_binding_required=True,
        risk_tier="high",
        auth_mode="proof_required",
    ),
    ("GET", "/api/developer/sites/<site_id>/users-summary"): RouteAuthPolicy(
        required_scope="read",
        allowed_principals=READ_PRINCIPALS,
        site_binding_required=True,
    ),
    # Site management API
    ("GET", "/api/developer/sites/<site_id>/users"): RouteAuthPolicy(
        required_scope="read",
        allowed_principals=READ_PRINCIPALS,
        site_binding_required=True,
    ),
    ("POST", "/api/developer/sites/<site_id>/users"): RouteAuthPolicy(
        required_scope="write",
        allowed_principals=MUTATE_PRINCIPALS,
        site_binding_required=True,
        auth_mode="credential_required",
    ),
    ("GET", "/api/developer/sites/<site_id>/users/<ppid>"): RouteAuthPolicy(
        required_scope="read",
        allowed_principals=READ_PRINCIPALS,
        site_binding_required=True,
    ),
    ("PUT", "/api/developer/sites/<site_id>/users/<ppid>"): RouteAuthPolicy(
        required_scope="write",
        allowed_principals=MUTATE_PRINCIPALS,
        site_binding_required=True,
        auth_mode="credential_required",
    ),
    ("POST", "/api/developer/sites/<site_id>/users/<ppid>/revoke"): RouteAuthPolicy(
        required_scope="admin",
        allowed_principals=MUTATE_PRINCIPALS,
        site_binding_required=True,
        risk_tier="high",
        auth_mode="proof_required",
    ),
    ("POST", "/api/developer/sites/<site_id>/users/<ppid>/unblock"): RouteAuthPolicy(
        required_scope="admin",
        allowed_principals=MUTATE_PRINCIPALS,
        site_binding_required=True,
        risk_tier="high",
        auth_mode="proof_required",
    ),
    ("GET", "/api/developer/sites/<site_id>/users/export"): RouteAuthPolicy(
        required_scope="read",
        allowed_principals=READ_PRINCIPALS,
        site_binding_required=True,
    ),
    ("GET", "/api/developer/sites/<site_id>/permissions"): RouteAuthPolicy(
        required_scope="read",
        allowed_principals=READ_PRINCIPALS,
        site_binding_required=True,
    ),
    ("POST", "/api/developer/sites/<site_id>/permissions"): RouteAuthPolicy(
        required_scope="write",
        allowed_principals=MUTATE_PRINCIPALS,
        site_binding_required=True,
        risk_tier="high",
        auth_mode="proof_required",
    ),
    ("PUT", "/api/developer/sites/<site_id>/permissions/<permission_id>"): RouteAuthPolicy(
        required_scope="admin",
        allowed_principals=MUTATE_PRINCIPALS,
        site_binding_required=True,
        risk_tier="high",
        auth_mode="proof_required",
    ),
    ("DELETE", "/api/developer/sites/<site_id>/permissions/<permission_id>"): RouteAuthPolicy(
        required_scope="admin",
        allowed_principals=MUTATE_PRINCIPALS,
        site_binding_required=True,
        risk_tier="high",
        auth_mode="proof_required",
    ),
    ("POST", "/api/developer/sites/<site_id>/users/<ppid>/permissions"): RouteAuthPolicy(
        required_scope="admin",
        allowed_principals=MUTATE_PRINCIPALS,
        site_binding_required=True,
        risk_tier="high",
        auth_mode="proof_required",
    ),
    ("DELETE", "/api/developer/sites/<site_id>/users/<ppid>/permissions/<permission_id>"): RouteAuthPolicy(
        required_scope="admin",
        allowed_principals=MUTATE_PRINCIPALS,
        site_binding_required=True,
        risk_tier="high",
        auth_mode="proof_required",
    ),
    ("GET", "/api/developer/sites/<site_id>/stats"): RouteAuthPolicy(
        required_scope="read",
        allowed_principals=READ_PRINCIPALS,
        site_binding_required=True,
    ),
    # Customer and dashboard
    ("GET", "/api/customer/profile"): RouteAuthPolicy(
        required_scope="read",
        allowed_principals=("user_lemma", "agent_token", "access_token"),
    ),
    ("GET", "/api/customer/usage"): RouteAuthPolicy(
        required_scope="read",
        allowed_principals=("user_lemma", "agent_token", "access_token", "api_key"),
    ),
    ("GET", "/api/customer/api-keys"): RouteAuthPolicy(
        required_scope="read",
        allowed_principals=("user_lemma", "agent_token", "access_token", "api_key"),
    ),
    ("POST", "/api/customer/api-keys"): RouteAuthPolicy(
        required_scope="write",
        allowed_principals=("user_lemma", "agent_token", "access_token", "api_key"),
    ),
    ("DELETE", "/api/customer/api-keys"): RouteAuthPolicy(
        required_scope="admin",
        allowed_principals=("user_lemma", "agent_token", "access_token", "api_key"),
    ),
    ("POST", "/api/customer/api-keys/rotate"): RouteAuthPolicy(
        required_scope="admin",
        allowed_principals=("user_lemma", "agent_token", "access_token", "api_key"),
    ),
    ("POST", "/api/customer/register-site"): RouteAuthPolicy(
        required_scope="write",
        allowed_principals=("user_lemma", "agent_token", "access_token", "api_key"),
    ),
    # Issuance/admin endpoints
    ("POST", "/api/developer/issue-self-permission"): RouteAuthPolicy(
        required_scope="write",
        allowed_principals=MUTATE_PRINCIPALS,
        auth_mode="credential_required",
    ),
    ("POST", "/api/v1/iam/admin/self-issue"): RouteAuthPolicy(
        required_scope="admin",
        allowed_principals=API_KEY_ONLY_PRINCIPALS,
    ),
    # Agent APIs
    ("GET", "/api/agent/credentials"): RouteAuthPolicy(
        required_scope="read",
        allowed_principals=("user_lemma", "agent_token", "access_token", "api_key"),
    ),
    ("POST", "/api/agent/credentials/issue"): RouteAuthPolicy(
        required_scope="write",
        allowed_principals=("user_lemma", "agent_token", "access_token"),
        risk_tier="high",
        auth_mode="compat_proof_wrapped",
    ),
    ("POST", "/api/agent/credentials/<token_id>/revoke"): RouteAuthPolicy(
        required_scope="write",
        allowed_principals=("user_lemma", "agent_token", "access_token", "api_key"),
    ),
    ("GET", "/api/agent/credentials/audit"): RouteAuthPolicy(
        required_scope="read",
        allowed_principals=("user_lemma", "agent_token", "access_token", "api_key"),
    ),
    ("GET", "/api/agent/credentials/<token_id>/task-report"): RouteAuthPolicy(
        required_scope="read",
        allowed_principals=("user_lemma", "agent_token", "access_token", "api_key"),
    ),
    # SDK auth admin endpoints
    ("POST", "/api/auth/introspect"): RouteAuthPolicy(
        required_scope="read",
        allowed_principals=API_KEY_ONLY_PRINCIPALS,
    ),
    ("POST", "/api/auth/revoke"): RouteAuthPolicy(
        required_scope="write",
        allowed_principals=API_KEY_ONLY_PRINCIPALS,
    ),
    # Stripe checkout endpoints
    ("POST", "/api/create-checkout-session"): RouteAuthPolicy(
        required_scope="write",
        allowed_principals=("user_lemma", "agent_token", "access_token", "api_key"),
    ),
    ("GET", "/api/subscription/status"): RouteAuthPolicy(
        required_scope="read",
        allowed_principals=("user_lemma", "agent_token", "access_token", "api_key"),
    ),
}


AUTH_ERROR_CATALOG: dict[str, tuple[int, str]] = {
    "auth_required": (401, "Authentication required"),
    "missing_lemma_header": (401, "X-Lemma-Credential header required"),
    "invalid_lemma_header": (401, "Invalid X-Lemma-Credential header"),
    "invalid_lemma_subject": (401, "Credential subject is invalid"),
    "credential_id_mismatch": (401, "Credential ID header mismatch"),
    "invalid_lemma": (401, "Credential verification failed"),
    "invalid_access_token": (401, "Invalid or expired access token"),
    "missing_scope": (403, "Insufficient scope"),
    "missing_permission": (403, "Insufficient permissions"),
    "site_mismatch": (403, "Credential site binding mismatch"),
    "credential_revoked": (401, "Credential has been revoked"),
    "site_not_allowed": (403, "Site is not allowed for this principal"),
    "site_scope_validation_failed": (500, "Unable to validate site restrictions"),
    "AUTH_PROOF_REQUIRED": (403, "Proof-native authorization is required for this route"),
    "AUTH_MODE_DOWNGRADE": (403, "Authorization mode downgrade is not allowed"),
    "AUTH_COMPAT_MODE_EXPIRED": (403, "Compatibility bearer mode has expired for this route"),
    "AUTH_REPLAY_DETECTED": (401, "Replay detected for proof-of-possession envelope"),
    "AUTH_PROOF_OF_POSSESSION_FAILED": (401, "Proof-of-possession validation failed"),
    "AUTH_RISK_STEP_UP_REQUIRED": (403, "Step-up or freshness refresh required for this route"),
    "AUTH_CREDENTIAL_REQUIRED": (403, "Verified X-Lemma-Credential or X-Agent-Token required for this route"),
}


def _path_matches_template(template: str, path: str) -> bool:
    template_parts = [p for p in str(template).strip().split("/") if p]
    path_parts = [p for p in str(path).strip().split("/") if p]
    if len(template_parts) != len(path_parts):
        return False

    for template_part, path_part in zip(template_parts, path_parts):
        if template_part.startswith("<") and template_part.endswith(">"):
            continue
        if template_part != path_part:
            return False
    return True


def get_policy_for_request(method: str, path: str) -> Optional[RouteAuthPolicy]:
    """Resolve policy by exact or template path match."""
    if not method or not path:
        return None

    request_method = str(method).upper()
    request_path = str(path)

    exact = ROUTE_AUTHZ_POLICY.get((request_method, request_path))
    if exact is not None:
        return exact

    for (policy_method, policy_path), policy in ROUTE_AUTHZ_POLICY.items():
        if policy_method != request_method:
            continue
        if _path_matches_template(policy_path, request_path):
            return policy
    return None


def get_error_defaults(code: str) -> tuple[int, str]:
    """Return default (status, message) for a known auth error code."""
    if not code:
        return 401, "Authentication required"
    return AUTH_ERROR_CATALOG.get(code, (401, "Authentication required"))

