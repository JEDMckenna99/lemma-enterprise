"""
Authentication decorators for Lemma.id, local-first credential verification.

Single auth path: X-Lemma-Credential header containing a signed credential.
Verification is local (Ed25519 signature + pinned issuer trust + Bloom filter
revocation). No database or Redis queries on the verification hot path.

Legacy decorator names (require_site_admin, require_admin, etc.) are preserved
as thin aliases so existing route registrations keep working without changes.
"""

from functools import wraps
from flask import request, jsonify, g, make_response
from typing import Optional
import logging
import os

from auth.permissions import normalize_scopes, is_admin_permission
from api.authz_engine import extract_user_lemma_principal, try_wallet_session_principal
from api.authz_policy import get_error_defaults

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Error helper
# ---------------------------------------------------------------------------

def _auth_error(
    code: str,
    message: Optional[str] = None,
    status: Optional[int] = None,
    auth_method: str = "none",
    required_scope=None,
    provided_scope=None,
):
    default_status, default_message = get_error_defaults(code)
    payload = {
        "error": code,
        "message": message or default_message,
        "auth_method": auth_method,
    }
    if required_scope is not None:
        payload["required_scope"] = required_scope
    if provided_scope is not None:
        payload["provided_scope"] = provided_scope
    return jsonify(payload), (status or default_status)


# ---------------------------------------------------------------------------
# Core decorator
# ---------------------------------------------------------------------------

def require_credential(
    required_scope: Optional[str] = None,
    required_permission: Optional[str] = None,
    allow_unauthenticated: bool = False,
):
    """
    Single auth path: verify X-Lemma-Credential locally.

    Ed25519 signature + pinned issuer trust + Bloom revocation + claim checks.
    No DB. No Redis. No session state on the verification path.

    Parameters
    ----------
    required_scope : str, optional
        If set, the credential must contain this scope (e.g. 'admin').
    required_permission : str, optional
        If set, the credential's permission_id must match (unless admin).
    allow_unauthenticated : bool
        If True, missing or invalid credentials are allowed, the handler
        can inspect ``g.authenticated`` to decide behaviour.
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            _set_tenant_context_from_request()

            principal, error = extract_user_lemma_principal(request.headers)

            if not principal:
                from auth.agent_principal import extract_agent_admin_principal, extract_agent_session_principal

                agent_info = None
                principal, agent_error, agent_info = extract_agent_admin_principal(
                    request.headers,
                    request_path=request.path,
                )
                if principal:
                    error = None
                    g.agent_credential = agent_info
                elif error is None:
                    error = agent_error

            if not principal:
                session_principal, session_error = extract_agent_session_principal(
                    request_path=request.path,
                    required_scope=required_scope,
                )
                if session_principal:
                    principal = session_principal
                    error = None
                elif error is None and session_error:
                    error = session_error

            if not principal:
                wallet_error = None
                wallet_principal, wallet_error = try_wallet_session_principal(request.headers)
                if wallet_principal:
                    principal = wallet_principal
                    error = None

            if not principal:
                if allow_unauthenticated:
                    g.authenticated = False
                    return f(*args, **kwargs)
                return _auth_error(
                    "auth_required",
                    f"Credential required: {error or wallet_error}",
                    status=401,
                )

            g.authenticated = True
            g.auth_method = getattr(principal, "auth_method", None) or "credential"
            g.ppid = principal.ppid
            g.credential_id = principal.credential_id
            g.permission_id = principal.permission_id
            g.scope = principal.scope
            g.site_binding = principal.site_binding
            g.is_admin = (
                is_admin_permission(principal.permission_id)
                or "admin" in principal.scope
            )

            if required_scope and required_scope not in principal.scope:
                return _auth_error(
                    "missing_scope",
                    f"Required scope '{required_scope}' not present in credential.",
                    status=403,
                    auth_method="credential",
                    required_scope=[required_scope],
                    provided_scope=principal.scope,
                )

            if required_scope == "admin":
                from api.platform_owner import (
                    is_platform_owner_ppid,
                    is_platform_site,
                    platform_owner_enforcement_enabled,
                )

                site_binding = (principal.site_binding or "").strip().lower()
                if (
                    platform_owner_enforcement_enabled()
                    and is_platform_site(site_binding)
                    and not is_platform_owner_ppid(principal.ppid)
                ):
                    return _auth_error(
                        "platform_owner_required",
                        "Platform admin access is restricted to the configured platform owner.",
                        status=403,
                        auth_method="credential",
                    )

            if required_permission:
                if not g.is_admin and principal.permission_id != required_permission:
                    return _auth_error(
                        "missing_permission",
                        f"Required permission '{required_permission}', got '{principal.permission_id}'.",
                        status=403,
                        auth_method="credential",
                    )

            return f(*args, **kwargs)
        return wrapped
    return decorator


# ---------------------------------------------------------------------------
# Legacy aliases: keep existing route decorators working
# ---------------------------------------------------------------------------

def require_site_admin(f):
    """Admin-scoped credential required.

    NOTE: This only proves the caller holds an admin-scoped credential for
    *some* site. It does NOT bind the admin authority to the specific resource
    being acted on. Site-scoped routes that take a ``site_id`` from the request
    MUST additionally enforce ``api.site_access.require_site_ownership`` (or an
    equivalent per-site check); platform-operator routes MUST use
    ``require_platform_admin`` instead.
    """
    return require_credential(required_scope="admin")(f)


def require_admin(f):
    """Admin-scoped credential required (alias for require_site_admin)."""
    return require_credential(required_scope="admin")(f)


def _principal_is_platform_admin(
    ppid: Optional[str], site_binding: Optional[str] = None
) -> bool:
    """Server-authoritative platform-operator check (not client-forgeable).

    A principal counts as a platform operator when ANY of the following hold:

      1. Its verified credential is bound to a platform site
         (``lemma.id`` / ``lemma_platform``). ``site_binding`` comes from a
         signature-verified, trusted-issuer credential; a relying-site issuer
         signs its own ``siteId`` and the platform issuer only mints
         ``lemma.id``-bound admin credentials for real operators, so a customer
         cannot forge this.
      2. It is the env-pinned platform owner PPID (constant-time compared).
      3. It has an active ``lemma.id`` / ``lemma_platform`` SiteAdmin row.

    Deliberately avoids ``api.site_access.is_platform_operator_ppid`` because
    its ``_is_lemma_platform_operator`` fallback trusts an UNVERIFIED admin-lemma
    context parsed straight from request headers/body — which a caller holding
    only a relying-site admin credential could forge.
    """
    try:
        from api.platform_owner import is_platform_site

        if site_binding and is_platform_site(site_binding):
            return True
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("platform site-binding check failed: %s", exc)

    if not ppid:
        return False

    try:
        from api.platform_owner import is_platform_owner_ppid

        if is_platform_owner_ppid(ppid):
            return True
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("platform owner check failed: %s", exc)

    try:
        from api.site_access import verify_site_ownership

        return bool(
            verify_site_ownership("lemma.id", ppid)
            or verify_site_ownership("lemma_platform", ppid)
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("platform operator lookup failed (failing closed): %s", exc)
        return False


def require_platform_admin(f):
    """Platform-operator admin required (stronger than ``require_site_admin``).

    The caller must (a) present a valid admin-scoped credential AND (b) be a
    lemma.id platform operator per ``_principal_is_platform_admin``. A customer's
    admin lemma bound to their own relying site does NOT grant access to
    platform-operator endpoints, closing the cross-tenant platform-admin
    escalation. When platform-owner enforcement is enabled, ``require_credential``
    additionally restricts platform-bound admins to the configured owner.
    """
    @wraps(f)
    def _platform_checked(*args, **kwargs):
        ppid = getattr(g, "ppid", None)
        site_binding = getattr(g, "site_binding", None)
        if not _principal_is_platform_admin(ppid, site_binding):
            return _auth_error(
                "platform_admin_required",
                "This endpoint is restricted to lemma.id platform operators.",
                status=403,
                auth_method=getattr(g, "auth_method", "credential"),
            )
        return f(*args, **kwargs)

    return require_credential(required_scope="admin")(_platform_checked)


def require_wallet_ppid(f):
    """Any valid credential with a PPID required."""
    return require_credential()(f)


def require_customer_or_admin(f):
    """Any valid credential required (customer or admin)."""
    return require_credential()(f)


def require_authenticated(f):
    """Any valid credential required."""
    return require_credential()(f)


def optional_auth(f):
    """Credential checked but not required; sets g.authenticated."""
    return require_credential(allow_unauthenticated=True)(f)


def require_api_key(f):
    """
    Legacy API-key decorator, now requires a credential instead.
    Endpoints previously gated by API key must present a signed credential.
    """
    return require_credential()(f)


def require_permission_lemma(site_id="lemma.id", required_permissions=None):
    """
    Legacy permission-lemma decorator.

    Now verifies the full credential and checks scope / site binding.
    """
    if required_permissions is None:
        required_permissions = ["customer_access", "admin_access"]

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            principal, error = extract_user_lemma_principal(request.headers)
            if not principal:
                from flask import redirect, url_for
                return redirect(url_for("customer_accounts.login"))

            if principal.permission_id not in required_permissions:
                if not is_admin_permission(principal.permission_id):
                    from flask import redirect, url_for
                    return redirect(url_for("customer_accounts.login"))

            if site_id and principal.site_binding and principal.site_binding != site_id:
                from flask import redirect, url_for
                return redirect(url_for("customer_accounts.login"))

            g.authenticated = True
            g.credential_id = principal.credential_id
            g.permission_id = principal.permission_id
            g.ppid = principal.ppid
            g.user_email = (
                request.headers.get("X-User-Email")
            )
            return f(*args, **kwargs)
        return wrapped
    return decorator


# ---------------------------------------------------------------------------
# Utility decorators & helpers (kept as-is)
# ---------------------------------------------------------------------------

def cors_headers(f):
    """Add CORS headers to response."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        response = make_response(f(*args, **kwargs))
        origin = request.headers.get("Origin", "*")
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, Authorization, X-Lemma-Credential, X-Lemma-Proof, "
            "X-Lemma-PoP, X-Agent-Token, X-API-Key, X-Lemma-CSRF, X-CSRF-Token"
        )
        response.headers["Access-Control-Allow-Credentials"] = "true"
        return response
    return decorated_function


def rate_limit(max_requests=100, window=60):
    """Rate limit decorator backed by the shared flask-limiter instance.

    Historically this was a no-op stub, which silently disabled every
    ``@rate_limit(max_requests=..., window=...)`` decorator across the SDK API
    (issuance, revocation, IDV, verify). It now delegates to the real limiter in
    ``auth.rate_limiter`` so the documented per-endpoint ceilings are actually
    enforced. The legacy ``(max_requests, window-seconds)`` signature is
    preserved and translated into a limits-compatible rate string.

    Fails open only when the limiter backend is unavailable (matching the
    limiter's configured degraded mode), never silently disabled.
    """
    from auth.rate_limiter import rate_limit as _limiter_rate_limit

    try:
        limit_string = f"{int(max_requests)} per {int(window)} seconds"
    except (TypeError, ValueError):
        limit_string = "100 per 60 seconds"

    return _limiter_rate_limit(limit_string)


def extract_authenticated_ppid_from_request() -> Optional[str]:
    """Return PPID from request context or verified credential header."""
    from auth.request_principal import get_context_ppid

    ppid = get_context_ppid()
    if ppid:
        return ppid

    principal, _ = extract_user_lemma_principal(request.headers)
    if principal:
        return principal.ppid
    return None


def get_current_user():
    """Get current authenticated user information from request context."""
    if hasattr(g, "ppid") and g.ppid:
        return {"ppid": g.ppid, "type": "credential"}
    if hasattr(g, "credential_id") and g.credential_id:
        return {
            "credential_id": g.credential_id,
            "permission_id": getattr(g, "permission_id", None),
            "type": "credential",
        }
    return None


# ---------------------------------------------------------------------------
# Tenant context (unchanged)
# ---------------------------------------------------------------------------

def _normalize_tenant_identifier(value, fallback: str, max_len: int = 120) -> str:
    cleaned = "".join(
        ch for ch in str(value or "").strip().lower()
        if ch.isalnum() or ch in {"-", "_", "."}
    )
    cleaned = cleaned[:max_len]
    return cleaned or fallback


def _set_tenant_context_from_request() -> None:
    org_id = _normalize_tenant_identifier(
        request.headers.get("X-Lemma-Org-Id") or request.args.get("org_id"),
        "org_default",
        120,
    )
    environment = _normalize_tenant_identifier(
        request.headers.get("X-Lemma-Environment") or request.args.get("environment"),
        "prod",
        32,
    )
    if environment not in {"dev", "staging", "prod"}:
        environment = "prod"
    g.org_id = org_id
    g.environment = environment


# ---------------------------------------------------------------------------
# CSRF protection (unchanged: operates on cookies, not credential path)
# ---------------------------------------------------------------------------

def init_csrf_protection(app):
    """
    Initialize CSRF protection for the Flask app.
    Uses double-submit cookie pattern.
    """
    import secrets

    CSRF_COOKIE_NAME = "lemma_csrf_token"
    # Double-submit is validated against whichever CSRF cookie is present. The
    # wallet SDK issues/sends `lemma_wallet_csrf`; server-issued browser sessions
    # use `lemma_csrf_token`. Accept either so both flows keep working.
    CSRF_COOKIE_NAMES = ("lemma_csrf_token", "lemma_wallet_csrf")
    CSRF_HEADER_NAMES = ("X-Lemma-CSRF", "X-CSRF-Token")
    PROTECTED_METHODS = ["POST", "PUT", "DELETE", "PATCH"]
    # Cookies that confer ambient authentication. CSRF only matters when a
    # request is authenticated by one of these (the browser attaches them
    # automatically on cross-site requests). Header/bearer-authenticated API
    # calls cannot be forged cross-origin and are exempt below.
    AMBIENT_AUTH_COOKIES = ("session", "lemma_wallet_session")
    # Header credentials prove the request is NOT relying on ambient cookie auth,
    # so it is not CSRF-exploitable regardless of cookies the browser attached.
    CREDENTIAL_HEADERS = (
        "Authorization",
        "X-Lemma-Credential",
        "X-Agent-Token",
        "X-API-Key",
    )
    CSRF_EXEMPT_PREFIXES = [
        "/api/sdk/",
        "/api/webhook/",
        "/api/passkey/authenticate/",
        "/api/passkey/register/",
        # wallet session-sync enforces its own origin allowlist + unlock-token
        # (bearer) checks and per-endpoint _validate_csrf(); its cookies are
        # SameSite=None so it needs those bespoke defenses rather than this guard.
        "/api/wallet/",
        "/api/health",
        "/api/revocation/",
    ]

    @app.before_request
    def csrf_protect():
        from flask import request as _req, g as _g, jsonify
        if _req.method not in PROTECTED_METHODS:
            return
        for prefix in CSRF_EXEMPT_PREFIXES:
            if _req.path.startswith(prefix):
                return

        # Header/bearer-authenticated requests are not CSRF-exploitable: a
        # cross-origin attacker cannot set these headers without a CORS-approved
        # preflight. Let them through so SDK/server-to-server clients are unaffected.
        if any(_req.headers.get(h) for h in CREDENTIAL_HEADERS):
            return

        # No ambient auth cookie => nothing for an attacker to ride on.
        if not any(_req.cookies.get(name) for name in AMBIENT_AUTH_COOKIES):
            return

        header_token = None
        for header_name in CSRF_HEADER_NAMES:
            header_token = _req.headers.get(header_name)
            if header_token:
                break
        if not header_token:
            header_token = _req.form.get("csrf_token")

        cookie_tokens = [
            _req.cookies.get(name) for name in CSRF_COOKIE_NAMES if _req.cookies.get(name)
        ]

        token_ok = bool(header_token) and any(
            secrets.compare_digest(cookie_token, header_token) for cookie_token in cookie_tokens
        )
        if not token_ok:
            app.logger.warning(
                "CSRF validation failed (fail-closed) for %s %s", _req.method, _req.path
            )
            return jsonify({
                "success": False,
                "error": "csrf_validation_failed",
                "code": "csrf_validation_failed",
            }), 403
        _g.csrf_validated = True

    @app.after_request
    def set_csrf_cookie(response):
        from flask import request as _req
        if _req.cookies.get(CSRF_COOKIE_NAME):
            return response
        token = secrets.token_urlsafe(32)
        response.set_cookie(
            CSRF_COOKIE_NAME,
            token,
            httponly=False,
            secure=True,
            samesite="Lax",
            max_age=86400 * 7,
        )
        return response

    app.logger.info("CSRF protection initialized")
