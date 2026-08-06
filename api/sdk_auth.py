"""
SDK Authentication API for External Sites
Handles sign-in flow for sites using Lemma Sign-In SDK
"""

import os
import secrets
import logging
import ast
import time
from flask import Blueprint, request, jsonify, redirect, render_template_string
from flask_cors import cross_origin
from urllib.parse import urlencode, urlparse
from auth.decorators import require_api_key
from auth.redis_store import store as redis_store, get as redis_get, delete as redis_delete, cleanup_expired as redis_cleanup_expired

logger = logging.getLogger(__name__)

sdk_auth_bp = Blueprint('sdk_auth', __name__)

SDK_PENDING_REQUEST_TTL_SECONDS = 600
SDK_PENDING_REQUEST_KEY_PREFIX = "sdk_auth:pending"


def _pending_request_key(state: str) -> str:
    return f"{SDK_PENDING_REQUEST_KEY_PREFIX}:{state}"


def _store_pending_sdk_request(state: str, payload: dict) -> bool:
    if not state or not isinstance(payload, dict):
        return False
    return redis_store(_pending_request_key(state), payload, ttl_seconds=SDK_PENDING_REQUEST_TTL_SECONDS)


def _consume_pending_sdk_request(state: str) -> dict | None:
    """
    Fetch and delete a pending request in one logical step so callback state
    tokens are one-time-use even when replayed.
    """
    if not state:
        return None

    key = _pending_request_key(state)
    pending = redis_get(key)
    if not pending:
        return None

    redis_delete(key)
    return pending if isinstance(pending, dict) else None


def _resolve_site_allowed_hosts(site: str) -> set[str]:
    """
    Resolve the set of hosts a site's SDK return URL may point at.

    ``siteId`` is documented as the site's canonical hostname, so that host is
    allowed directly. For internal ``site_*`` identifiers (or to pick up the
    registered domain) we also consult the ``sites`` table. Binding the return
    URL to the site's own domain prevents the sign-in flow from being used as an
    open redirect to attacker-controlled destinations.
    """
    hosts: set[str] = set()
    raw = (site or "").strip()
    if not raw:
        return hosts

    from api.site_hostname import try_canonicalize_site_hostname

    if not raw.lower().startswith("site_"):
        canonical, _err = try_canonicalize_site_hostname(raw)
        if canonical:
            hosts.add(canonical)

    try:
        from api.database import SessionLocal, Site

        db = SessionLocal()
        try:
            site_row = (
                db.query(Site).filter_by(site_id=raw).first()
                or db.query(Site).filter_by(site_domain=raw).first()
            )
            domain = getattr(site_row, "site_domain", None) if site_row else None
            if domain:
                canonical, _err = try_canonicalize_site_hostname(domain)
                if canonical:
                    hosts.add(canonical)
        finally:
            db.close()
    except Exception as exc:  # pragma: no cover - DB optional in some contexts
        logger.debug("sdk return-url site resolution unavailable: %s", exc)

    return hosts


def _normalize_scopes(raw_scopes) -> list[str]:
    """Normalize scope values from claims/request into canonical lowercase list."""
    if raw_scopes is None:
        return []

    values = raw_scopes
    if isinstance(raw_scopes, str):
        text = raw_scopes.strip()
        if not text:
            return []
        # Support stringified list formats like "['read']" or "[\"read\",\"write\"]".
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = ast.literal_eval(text)
                values = parsed
            except Exception:
                values = text
        else:
            values = text

    if isinstance(values, (list, tuple, set)):
        source = values
    else:
        source = str(values).split(",")

    normalized = []
    for item in source:
        scope = str(item).strip().strip("'\"").lower()
        if scope and scope not in normalized:
            normalized.append(scope)
    return normalized


@sdk_auth_bp.route('/auth/sdk-request', methods=['GET'])
@cross_origin()
def sdk_auth_request():
    """
    SDK sign-in request endpoint
    Called when user clicks "Sign in with Lemma" button
    
    Query params:
        site: Site ID or domain
        return: Return URL after authentication
    """
    site_id = request.args.get('site', '')
    return_url = request.args.get('return', '')
    
    if not site_id:
        return jsonify({'error': 'Site ID required'}), 400
    
    if not return_url:
        return jsonify({'error': 'Return URL required'}), 400
    
    # Open-redirect guard: the return URL must be an https URL on the requesting
    # site's own registered domain. Previously any URL with a scheme+netloc was
    # accepted, so `?return=https://evil.com` turned this post-authentication
    # redirect into an open redirect usable for phishing.
    allowed_hosts = _resolve_site_allowed_hosts(site_id)
    if not allowed_hosts:
        return jsonify({'error': 'Unknown site', 'message': 'site is not a recognized lemma.id site'}), 400

    from api.url_safety import is_host_allowed_redirect
    if not is_host_allowed_redirect(return_url, allowed_hosts):
        return jsonify({
            'error': 'Invalid return URL',
            'message': 'return must be an https URL on the site domain',
        }), 400
    
    # Generate state token for CSRF protection
    state = secrets.token_urlsafe(32)
    
    # Store pending request with TTL in shared storage (Redis when available).
    stored = _store_pending_sdk_request(state, {
        'site_id': site_id,
        'return_url': return_url,
        'created_at': time.time()
    })
    if not stored:
        return jsonify({'error': 'Unable to initialize sign-in request'}), 500
    
    # Redirect to login with SDK context
    params = urlencode({
        'sdk_state': state,
        'site_id': site_id,
        'return_url': return_url
    })
    
    return redirect(f'/login?{params}')


@sdk_auth_bp.route('/auth/sdk-callback', methods=['GET'])
@cross_origin()
def sdk_auth_callback():
    """
    Legacy SDK redirect callback — quarantined.

    This route does not verify a presentation or bind a subject. Primary SIWL
    uses <lemma-signin> / ProofVerifier.verifyForBackend and posts the
    presentation to the relying site's backend directly.
    """
    state = request.args.get('state', '')

    if not state:
        return jsonify({
            'error': 'callback_unbound',
            'code': 'callback_unbound',
            'message': 'Missing or invalid SDK callback state.',
        }), 401

    pending = _consume_pending_sdk_request(state)
    if not pending:
        return jsonify({
            'error': 'callback_unbound',
            'code': 'callback_unbound',
            'message': 'Invalid or expired SDK callback state.',
        }), 401

    return_url = pending.get('return_url', '')
    if return_url:
        separator = '&' if '?' in return_url else '?'
        return redirect(
            f"{return_url}{separator}lemma_auth=error&reason=callback_unbound"
        )

    return jsonify({
        'error': 'callback_unbound',
        'code': 'callback_unbound',
        'message': 'SDK redirect callback is retired; verify presentations on your backend.',
    }), 409


@sdk_auth_bp.route('/api/auth/signout', methods=['POST', 'OPTIONS'])
@cross_origin()
def sdk_signout():
    """
    Sign out endpoint for SDK
    Clears any server-side session (if applicable)
    """
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200
    
    # In session-free architecture, sign-out is primarily client-side
    # This endpoint exists for compatibility and future session management
    return jsonify({
        'success': True,
        'message': 'Signed out successfully'
    })


@sdk_auth_bp.route('/api/verify-credential', methods=['POST', 'OPTIONS'])
@cross_origin()
def verify_credential():
    """
    Verify a credential is still valid
    Used by SDK to check credential validity
    
    SECURITY: Now includes trusted issuer validation to reject credentials
    signed by unknown/revoked issuers.
    """
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200
    
    try:
        data = request.get_json()
        credential = data.get('credential', {})
        
        if not credential:
            return jsonify({'valid': False, 'error': 'No credential provided'}), 400
        
        # Use secure verification with trusted issuer check
        from .trusted_issuers import verify_credential_with_trust
        result = verify_credential_with_trust(credential)
        
        claims = credential.get('claims', credential.get('credentialSubject', {}))
        
        return jsonify({
            'valid': result['valid'],
            'claims': claims if result['valid'] else {},
            'reason': result.get('reason'),
            'issuer_trusted': result['issuer_trusted'],
            'signature_valid': result['signature_valid']
        })
        
    except Exception as e:
        logger.error(f"Credential verification error: {e}")
        return jsonify({'valid': False, 'error': str(e)}), 500


@sdk_auth_bp.route('/api/auth/exchange-proof', methods=['POST', 'OPTIONS'])
@cross_origin()
def exchange_proof_for_token():
    """
    Exchange a verified site permission proof for a short-lived access token.

    Request body:
        credential: Permission lemma credential object
        site_id: Optional site binding assertion
        requested_scope: Optional string or list, must be subset of credential scope
        ttl_seconds: Optional token TTL (default 900, min 300, max 3600)
    """
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200

    try:
        data = request.get_json() or {}
        credential = data.get('credential')
        if not isinstance(credential, dict):
            return jsonify({'success': False, 'error': 'credential object required'}), 400

        from .trusted_issuers import verify_credential_with_trust
        verification = verify_credential_with_trust(credential)
        if not verification.get('valid'):
            return jsonify({
                'success': False,
                'error': 'invalid_proof',
                'reason': verification.get('reason'),
                'issuer_trusted': verification.get('issuer_trusted', False),
                'signature_valid': verification.get('signature_valid', False),
            }), 401

        claims = credential.get('claims') or credential.get('credentialSubject') or {}
        subject = (
            credential.get('subject')
            or credential.get('sub')
            or claims.get('sub')
            or claims.get('ppid')
            or claims.get('id')
        )
        if not subject:
            return jsonify({'success': False, 'error': 'credential subject missing'}), 400

        credential_site = (claims.get('siteId') or claims.get('site_id') or '').strip().lower()
        requested_site = (data.get('site_id') or '').strip().lower()
        if requested_site and credential_site and requested_site != credential_site:
            return jsonify({
                'success': False,
                'error': 'site_mismatch',
                'message': f'Credential is bound to {credential_site}, not {requested_site}.'
            }), 403
        site_id = requested_site or credential_site
        if not site_id:
            return jsonify({'success': False, 'error': 'site_id missing in request and credential'}), 400

        permission_id = (
            claims.get('permissionId')
            or claims.get('permission_id')
            or claims.get('permission')
            or claims.get('accountType')
            or 'read'
        )

        scopes = _normalize_scopes(claims.get('scope', []))

        if not scopes:
            from auth.permissions import is_admin_permission
            scopes = ['admin', 'write', 'read'] if is_admin_permission(str(permission_id)) else ['read']

        requested_scope = data.get('requested_scope')
        if requested_scope:
            requested = _normalize_scopes(requested_scope)
            if requested and not set(requested).issubset(set(scopes)):
                return jsonify({
                    'success': False,
                    'error': 'scope_escalation_denied',
                    'granted_scope': scopes
                }), 403
            if requested:
                scopes = requested

        ttl_seconds = int(data.get('ttl_seconds', 900))
        from .access_tokens import issue_access_token, issue_refresh_token
        access_token, expires_in = issue_access_token(
            subject=subject,
            site_id=site_id,
            permission_id=str(permission_id),
            scopes=scopes,
            credential_id=credential.get('id'),
            issuer_did=credential.get('issuer'),
            ttl_seconds=ttl_seconds,
        )
        # Refresh token is longer-lived and tied to this auth context.
        from .access_tokens import DEFAULT_REFRESH_TTL_SECONDS
        refresh_token = None
        refresh_expires_in = None

        # Derive auth context jti from decoded access token.
        from .access_tokens import validate_access_token
        access_payload, _ = validate_access_token(access_token)
        if access_payload and access_payload.get('jti'):
            refresh_token, refresh_expires_in = issue_refresh_token(
                subject=subject,
                site_id=site_id,
                permission_id=str(permission_id),
                scopes=scopes,
                auth_context_jti=str(access_payload.get('jti')),
                ttl_seconds=DEFAULT_REFRESH_TTL_SECONDS,
            )
        else:
            # Fallback keeps exchange usable even if access payload decode changes.
            refresh_token, refresh_expires_in = issue_refresh_token(
                subject=subject,
                site_id=site_id,
                permission_id=str(permission_id),
                scopes=scopes,
                auth_context_jti="unknown_context",
                ttl_seconds=DEFAULT_REFRESH_TTL_SECONDS,
            )

        return jsonify({
            'success': True,
            'token_type': 'Bearer',
            'access_token': access_token,
            'expires_in': expires_in,
            'refresh_token': refresh_token,
            'refresh_expires_in': refresh_expires_in,
            'site_id': site_id,
            'subject': subject,
            'scope': scopes,
            'permission_id': permission_id,
        }), 200
    except Exception as e:
        logger.error(f"Proof exchange error: {e}")
        return jsonify({'success': False, 'error': 'exchange_failed'}), 500


@sdk_auth_bp.route('/api/auth/introspect', methods=['POST', 'OPTIONS'])
@cross_origin()
@require_api_key(allow_credential_fallback=False)
def introspect_access_token_endpoint():
    """Introspect a server-issued access token (requires API key auth)."""
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200

    data = request.get_json() or {}
    token = data.get('token', '').strip()
    required_site = (data.get('site_id') or '').strip().lower() or None
    if not token:
        return jsonify({'success': False, 'error': 'token_required'}), 400

    from .access_tokens import introspect_access_token
    result = introspect_access_token(token, required_site_id=required_site)
    return jsonify({'success': True, 'introspection': result}), 200


@sdk_auth_bp.route('/api/auth/revoke', methods=['POST', 'OPTIONS'])
@cross_origin()
@require_api_key(allow_credential_fallback=False)
def revoke_access_token_endpoint():
    """Revoke a server-issued access token (requires API key auth)."""
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200

    data = request.get_json() or {}
    token = (data.get('token') or '').strip() or None
    jti = (data.get('jti') or '').strip() or None
    reason = (data.get('reason') or 'revoked_by_api').strip()[:128]
    revoked_by = 'api_key'

    from .access_tokens import revoke_access_token
    ok, metadata, error = revoke_access_token(
        token=token,
        jti=jti,
        reason=reason,
        revoked_by=revoked_by,
    )

    if not ok:
        return jsonify({'success': False, 'error': error}), 400

    return jsonify({
        'success': True,
        'revoked': True,
        'metadata': metadata,
    }), 200


@sdk_auth_bp.route('/api/auth/refresh', methods=['POST', 'OPTIONS'])
@cross_origin()
def refresh_access_token_endpoint():
    """Refresh an access token using a refresh token."""
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200

    data = request.get_json() or {}
    refresh_token = (data.get('refresh_token') or '').strip()
    site_id = (data.get('site_id') or '').strip().lower() or None
    if not refresh_token:
        return jsonify({'success': False, 'error': 'refresh_token_required'}), 400

    from .access_tokens import refresh_access_token
    result, error = refresh_access_token(refresh_token, required_site_id=site_id)
    if not result:
        return jsonify({'success': False, 'error': error}), 401

    return jsonify({
        'success': True,
        'token_type': 'Bearer',
        **result,
    }), 200


# Clean up old pending requests periodically
def cleanup_pending_requests():
    """Remove expired pending auth records from fallback memory storage."""
    redis_cleanup_expired()

