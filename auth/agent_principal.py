"""Map validated agent delegation tokens to admin API principals."""

from __future__ import annotations

from typing import Mapping, Optional, Tuple

from auth.permissions import normalize_scopes
from api.authz_engine import AuthzPrincipal

_LEMMA_PLATFORM_SITES = frozenset({'lemma.id', 'lemma_platform'})


def extract_agent_admin_principal(
    headers: Mapping[str, str],
    *,
    request_path: str | None = None,
) -> Tuple[Optional[AuthzPrincipal], Optional[str], Optional[dict]]:
    """
    Accept X-Agent-Token for operator-plane admin APIs when:
    - scope includes admin
    - allowed_sites is lemma.id only (lemma_platform alias allowed)
    - optional path is within token allowed_paths
    """
    token = (headers.get('X-Agent-Token') or '').strip()
    if not token:
        return None, 'missing_lemma_header', None
    if not token.startswith('lm_agent_'):
        return None, 'invalid_token', None

    from api.agent_credentials import check_path_allowed, validate_agent_token_with_reason

    info, reason = validate_agent_token_with_reason(token)
    if not info:
        return None, reason or 'invalid_token', None

    scope_raw = info.get('scope') or []
    if isinstance(scope_raw, str):
        scope = normalize_scopes([part.strip() for part in scope_raw.split(',') if part.strip()])
    else:
        scope = normalize_scopes(scope_raw if isinstance(scope_raw, (list, tuple, set)) else [])

    if 'admin' not in {str(s).strip().lower() for s in scope}:
        return None, 'missing_scope', None

    allowed_sites = info.get('allowed_sites') or []
    if isinstance(allowed_sites, str):
        allowed_sites = [allowed_sites]
    site_norm = {
        str(site).strip().lower()
        for site in allowed_sites
        if str(site).strip()
    }
    if not site_norm or not site_norm.issubset(_LEMMA_PLATFORM_SITES):
        return None, 'agent_site_binding_mismatch', None

    ppid = info.get('authorized_by_ppid') or info.get('authorized_by')
    if not ppid or not str(ppid).startswith('did:lemma:ppid_'):
        return None, 'invalid_lemma_subject', None

    if request_path:
        allowed_paths = info.get('allowed_paths')
        if allowed_paths is not None and not check_path_allowed(request_path, allowed_paths):
            return None, 'path_not_allowed', None

    principal = AuthzPrincipal(
        principal_type='agent_delegation',
        auth_method='agent_token',
        ppid=str(ppid),
        credential_id=info.get('token_id'),
        permission_id='admin_access',
        scope=scope,
        site_binding='lemma.id',
    )
    return principal, None, info
