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
    if not site_norm:
        site_norm = set(_LEMMA_PLATFORM_SITES)
    elif not site_norm.issubset(_LEMMA_PLATFORM_SITES):
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


def extract_agent_session_principal(
    *,
    request_path: str | None = None,
    required_scope: str | None = None,
) -> Tuple[Optional[AuthzPrincipal], Optional[str]]:
    """
    Map a Flask browser session created via /api/agent/session to an AuthzPrincipal.
    """
    from flask import session

    if not session.get('agent_authenticated'):
        return None, 'missing_lemma_header'

    scope_raw = session.get('agent_scope') or []
    scope = normalize_scopes(scope_raw if isinstance(scope_raw, (list, tuple, set)) else [])
    scope_norm = {str(s).strip().lower() for s in scope}

    if required_scope == 'admin' and 'admin' not in scope_norm:
        return None, 'missing_scope'

    allowed_sites = session.get('agent_allowed_sites')
    if allowed_sites is not None:
        if isinstance(allowed_sites, str):
            allowed_sites = [allowed_sites]
        site_norm = {
            str(site).strip().lower()
            for site in allowed_sites
            if str(site).strip()
        }
        if site_norm and not site_norm.issubset(_LEMMA_PLATFORM_SITES):
            return None, 'agent_site_binding_mismatch'

    ppid = session.get('agent_ppid')
    if not ppid or not str(ppid).startswith('did:lemma:ppid_'):
        return None, 'invalid_lemma_subject'

    permission_id = 'admin_access' if 'admin' in scope_norm else 'customer_access'

    principal = AuthzPrincipal(
        principal_type='agent_delegation',
        auth_method='agent_session',
        ppid=str(ppid),
        credential_id=session.get('agent_token_id'),
        permission_id=permission_id,
        scope=scope,
        site_binding='lemma.id',
    )
    return principal, None
