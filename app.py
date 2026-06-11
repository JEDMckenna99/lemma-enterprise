"""
Lemma Platform - Clean Production Application
Essential components only - no redundant endpoints
"""
import os
import logging
import secrets
import time
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, g

# Set up logging (override with LOG_LEVEL, e.g. DEBUG/INFO/WARNING/ERROR)
_LOG_LEVEL_NAME = os.environ.get('LOG_LEVEL', 'INFO').upper()
_LOG_LEVEL = getattr(logging, _LOG_LEVEL_NAME, logging.INFO)
logging.basicConfig(level=_LOG_LEVEL)
logger = logging.getLogger(__name__)

# Route prefixes that need expanded script-src (see docs/security/THIRD_PARTY_SCRIPTS.md)
_CSP_UNLOCK_IDV_PREFIXES = (
    '/unlock',
    '/wallet/unlock',
    '/wallet/popup',
    '/wallet/ishuman-idv',
)
_CSP_LINK_QR_PREFIXES = (
    '/link',
    '/wallet/link',
)


def _path_matches_prefix(path: str, prefixes: tuple[str, ...]) -> bool:
    normalized = path or '/'
    for prefix in prefixes:
        if normalized == prefix or normalized.startswith(prefix + '/'):
            return True
    return False


def resolve_csp_profile(path: str) -> str:
    """Return CSP profile name for a request path."""
    if _path_matches_prefix(path, _CSP_LINK_QR_PREFIXES):
        return 'link_qr'
    if _path_matches_prefix(path, _CSP_UNLOCK_IDV_PREFIXES):
        return 'unlock_idv'
    return 'strict'


def build_content_security_policy(nonce: str, profile: str = 'strict') -> str:
    """Build CSP header value for the given route profile."""
    script_src = [f"'self'", f"'nonce-{nonce}'"]
    connect_src = ["'self'", "https://lemma.id"]
    frame_src = ["'self'"]
    form_action = ["'self'"]

    if profile in ('unlock_idv', 'link_qr'):
        script_src.extend([
            "https://challenges.cloudflare.com",  # CSP-ALLOW: Cloudflare Turnstile
            "https://js.stripe.com",  # CSP-ALLOW: Stripe payments
            "https://cdn.jsdelivr.net/npm/",  # CSP-ALLOW: @noble/* ESM (lemma-keys.js)
        ])
        connect_src.extend([
            "https://*.stripe.com",
            "https://api.stripe.com",
            "https://cdn.jsdelivr.net",  # CSP-ALLOW: @noble/* ESM sub-imports
        ])
        frame_src.extend(["https://*.stripe.com", "https://challenges.cloudflare.com"])
        form_action.append("https://*.stripe.com")

    if profile == 'link_qr':
        script_src.append("https://unpkg.com/")  # CSP-ALLOW: html5-qrcode scanner

    return (
        "default-src 'self'; "
        f"script-src {' '.join(script_src)}; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https:; "
        "media-src 'self' blob:; "
        f"connect-src {' '.join(connect_src)}; "
        f"frame-src {' '.join(frame_src)} "
            "https://lemma-demo-tickets-1d3d7411af33.herokuapp.com "
            "https://lemma-demo-trials-7090f46cae0d.herokuapp.com; "
        "object-src 'none'; "
        "base-uri 'self'; "
        f"form-action {' '.join(form_action)}; "
        "upgrade-insecure-requests; "
        "report-uri /api/security/csp-report"
    )


def create_app():
    app = Flask(__name__)

    # Configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-for-testing')
    app.config['DEBUG'] = os.environ.get('FLASK_ENV') == 'development'
    
    # CRITICAL: Disable template caching (fixes stale HTML on Heroku)
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

    # Configure MIME types for proper asset serving
    import mimetypes
    mimetypes.add_type('image/svg+xml', '.svg')
    mimetypes.add_type('application/javascript', '.js')
    mimetypes.add_type('text/css', '.css')

    # Enhanced configuration for platform
    app.config['STRIPE_SECRET_KEY'] = os.environ.get('STRIPE_SECRET_KEY')
    app.config['STRIPE_PUBLISHABLE_KEY'] = os.environ.get('STRIPE_PUBLISHABLE_KEY')
    app.config['STRIPE_WEBHOOK_SECRET'] = os.environ.get('STRIPE_WEBHOOK_SECRET')

    # ================================================================================
    # CSP NONCE GENERATION - Secure inline scripts without 'unsafe-inline'
    # ================================================================================
    @app.before_request
    def generate_csp_nonce():
        """Generate a unique nonce for each request to allow inline scripts securely."""
        g.csp_nonce = secrets.token_urlsafe(16)
        g.csp_profile = resolve_csp_profile(request.path or '/')

    @app.before_request
    def capture_request_telemetry():
        """Track rolling request volume for admin health telemetry."""
        try:
            g.request_started_at = time.perf_counter()
            from monitoring.request_telemetry import record_request
            record_request()
        except Exception:
            # Health telemetry must never break request handling.
            pass
    
    @app.context_processor
    def inject_csp_nonce():
        """Make CSP nonce available to all templates."""
        return {'csp_nonce': getattr(g, 'csp_nonce', '')}

    @app.context_processor
    def inject_wallet_feature_flags():
        """Expose wallet feature flags to all templates.

        ``LEMMA_CROSS_SITE_LOCK_ENABLED`` controls the network overhead of the
        cross-site / cross-device lock-propagation layer (SSE heartbeat to
        ``lemma.id``, global-session polling, bridge auto-checks). The 24h
        IndexedDB session that gives "one passkey per day" on a single domain
        is *not* affected by this flag — it always works locally.

        Default ``true`` to preserve existing behavior; set to ``false`` on
        environments where lemma.id is not yet acting as a third-party login
        provider, to drop the cross-site sync overhead.
        """
        flag = os.getenv('LEMMA_CROSS_SITE_LOCK_ENABLED', 'true').strip().lower()
        try:
            from api.seed_envelope import use_person_root_seeds_enabled
            seeds_enabled = use_person_root_seeds_enabled()
        except Exception:
            seeds_enabled = False
        return {
            'cross_site_lock_enabled': flag in ('1', 'true', 'yes', 'on'),
            'ishuman_use_person_root_seeds': seeds_enabled,
            'wallet_debug_enabled': (os.getenv('LEMMA_WALLET_DEBUG') or '').strip().lower() in ('1', 'true', 'yes', 'on'),
        }

    # ================================================================================
    # SECURITY HEADERS - Industry standard protection
    # ================================================================================
    @app.after_request
    def add_security_headers(response):
        """Add security headers to all responses"""
        # Record response status telemetry for health dashboards.
        try:
            from monitoring.request_telemetry import record_response
            started = getattr(g, 'request_started_at', None)
            duration_ms = ((time.perf_counter() - started) * 1000.0) if started else None
            record_response(response.status_code, duration_ms=duration_ms)
        except Exception:
            pass

        # HSTS - Force HTTPS for 1 year
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
        
        # Prevent MIME type sniffing
        response.headers['X-Content-Type-Options'] = 'nosniff'
        
        # Prevent clickjacking
        if 'X-Frame-Options' not in response.headers:
            response.headers['X-Frame-Options'] = 'DENY'
        
        # XSS Protection (legacy but still useful)
        response.headers['X-XSS-Protection'] = '1; mode=block'
        
        # Referrer Policy - Don't leak URLs to third parties (routes may override, e.g. bridge)
        if 'Referrer-Policy' not in response.headers:
            response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # Permissions Policy - Disable unnecessary browser features
        response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        
        # Content Security Policy - Restrict resource loading
        # Skip if route already set its own CSP (e.g., wallet bridge)
        if 'Content-Security-Policy' not in response.headers:
            nonce = getattr(g, 'csp_nonce', '')
            profile = getattr(g, 'csp_profile', 'strict')
            response.headers['Content-Security-Policy'] = build_content_security_policy(nonce, profile)
        
        return response

    # Initialize components
    try:
        # Initialize error monitoring FIRST (catch initialization errors too)
        from monitoring.sentry_config import init_sentry
        sentry_enabled = init_sentry(app)
        if sentry_enabled:
            logger.info("✅ Sentry error monitoring active")
        
        # Initialize CSRF protection
        from auth.decorators import init_csrf_protection
        init_csrf_protection(app)

        # Initialize rate limiting (brute force protection)
        from auth.rate_limiter import create_limiter
        limiter = create_limiter(app)
        app.limiter = limiter  # Store on app for blueprint access
        logger.info(
            "Rate limiter degraded modes: auth=%s api=%s session_revocation=%s",
            (os.getenv("LEMMA_AUTH_LIMITER_DEGRADED_MODE") or "fail_open"),
            (os.getenv("LEMMA_API_RATE_LIMIT_DEGRADED_MODE") or "memory"),
            (os.getenv("LEMMA_SESSION_REVOCATION_DEGRADED_MODE") or "fail_open"),
        )
        logger.info("✅ Rate limiter initialized")

        # Initialize Stripe manager
        from billing.stripe_manager import init_stripe
        init_stripe()

        logger.info("✅ Core components initialized successfully")

    except Exception as e:
        logger.warning(f"⚠️ Some components failed to initialize: {e}")

    # ================================================================================
    # ESSENTIAL API BLUEPRINTS ONLY
    # ================================================================================

    # Core Shield System
    try:
        from api.lemma_shield import lemma_shield_bp
        app.register_blueprint(lemma_shield_bp)
        logger.info("✅ Lemma Shield registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Lemma Shield: {e}")

    # SDK Integration
    try:
        from api.sdk_api import sdk_api_bp
        app.register_blueprint(sdk_api_bp)
        logger.info("✅ SDK API registered")
    except Exception as e:
        logger.error(f"❌ Failed to register SDK API: {e}")

    # Customer Management
    try:
        from api.customer_accounts import customer_accounts_bp
        app.register_blueprint(customer_accounts_bp)
        logger.info("✅ Customer Accounts registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Customer Accounts: {e}")

    try:
        from api.dashboard_api import dashboard_bp
        app.register_blueprint(dashboard_bp)
        logger.info("✅ Dashboard API registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Dashboard API: {e}")

    # Billing System
    try:
        from api.automated_billing import automated_billing_bp
        app.register_blueprint(automated_billing_bp)
        logger.info("✅ Automated Billing registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Automated Billing: {e}")

    try:
        from api.stripe_checkout import stripe_checkout_bp
        app.register_blueprint(stripe_checkout_bp)
        logger.info("✅ Stripe Checkout registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Stripe Checkout: {e}")

    try:
        from api.mau_api import mau_api_bp
        app.register_blueprint(mau_api_bp)
        logger.info("✅ MAU API registered")
    except Exception as e:
        logger.error(f"❌ Failed to register MAU API: {e}")

    # IAM System
    try:
        from api.lemma_auth_endpoint import lemma_auth_bp
        app.register_blueprint(lemma_auth_bp)
        logger.info("✅ Lemma Auth registered")
    except Exception as e:
        logger.warning(f"⚠️ Lemma Auth not available: {e}")

    # Passkey (WebAuthn) Authentication
    try:
        from api.passkey_auth import passkey_bp
        app.register_blueprint(passkey_bp)
        logger.info("✅ Passkey Auth registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Passkey Auth: {e}")

    # Consolidated Wallet Service (replaces 8 separate wallet modules)
    try:
        from api.services.wallet_service import wallet_service_bp
        app.register_blueprint(wallet_service_bp)
        logger.info("✅ Consolidated Wallet Service registered (auth, session, transfer, PIN, sync)")
    except Exception as e:
        logger.error(f"❌ Failed to register Wallet Service: {e}")

    # Wallet Session Sync (cross-site session sharing, redirect token exchange)
    try:
        from api.wallet_session_sync import wallet_session_sync_bp
        app.register_blueprint(wallet_session_sync_bp)
        logger.info("✅ Wallet Session Sync registered (cross-site auth, redirect tokens)")
    except Exception as e:
        logger.error(f"❌ Failed to register Wallet Session Sync: {e}")

    # Issuer Registry (for wallet-centric architecture)
    try:
        from api.issuer_registry import issuer_registry_bp, init_issuer_registry_table
        app.register_blueprint(issuer_registry_bp)
        init_issuer_registry_table()
        logger.info("✅ Issuer Registry registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Issuer Registry: {e}")

    try:
        from api.permission_management_api import permission_api
        app.register_blueprint(permission_api)
        logger.info("✅ Permission Management registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Permission Management: {e}")
    
    # IAM Permission Types API (new structured permission system)
    try:
        from api.iam_permission_types import iam_types_bp
        app.register_blueprint(iam_types_bp)
        logger.info("✅ IAM Permission Types registered")
    except Exception as e:
        logger.error(f"❌ Failed to register IAM Permission Types: {e}")

    # Audit Logging API
    try:
        from api.audit_api import audit_api
        app.register_blueprint(audit_api)
        logger.info("✅ Audit API registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Audit API: {e}")

    # Revocation API (for client-side bloom filter)
    try:
        from api.revocation_api import revocation_api
        app.register_blueprint(revocation_api)
        logger.info("✅ Revocation API registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Revocation API: {e}")

    # IAM Email Confirmation
    try:
        from api.iam_email_confirmation import iam_email_bp
        app.register_blueprint(iam_email_bp)
        logger.info("✅ IAM Email Confirmation registered")
    except Exception as e:
        logger.error(f"❌ Failed to register IAM Email Confirmation: {e}")

    # Beta Access Request (Simplified Login)
    try:
        from api.beta_access import beta_access_bp
        app.register_blueprint(beta_access_bp)
        logger.info("✅ Beta Access Request registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Beta Access Request: {e}")

    # Admin Self-Issue
    try:
        from api.admin_self_issue import admin_self_issue_bp
        app.register_blueprint(admin_self_issue_bp)
        logger.info("✅ Admin Self-Issue registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Admin Self-Issue: {e}")

    # SDK Authentication API
    try:
        from api.sdk_auth import sdk_auth_bp
        app.register_blueprint(sdk_auth_bp)
        logger.info("✅ SDK Auth API registered")
    except Exception as e:
        logger.error(f"❌ Failed to register SDK Auth API: {e}")

    # Pairwise Tagging Service
    try:
        from api.pairwise_tagging import pairwise_tagging_bp
        app.register_blueprint(pairwise_tagging_bp)
        logger.info("✅ Pairwise Tagging Service registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Pairwise Tagging: {e}")

    # Credential Auto-Refresh API
    try:
        from api.credential_refresh import credential_refresh_bp
        app.register_blueprint(credential_refresh_bp)
        logger.info("✅ Credential Auto-Refresh API registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Credential Auto-Refresh API: {e}")

    # Permission Verification with Nonce (Bot Defense)
    try:
        from api.permission_verification import permission_verification_bp
        app.register_blueprint(permission_verification_bp)
        logger.info("✅ Permission Verification (Nonce Bot Defense) registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Permission Verification: {e}")
    
    # Test Credential Endpoint (for testing client-side verification)
    try:
        from api.test_credential_endpoint import test_credential_bp
        app.register_blueprint(test_credential_bp)
        logger.info("✅ Test Credential Endpoint registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Test Credential Endpoint: {e}")
    
    # Platform Statistics API
    try:
        from api.platform_stats import platform_stats_bp
        app.register_blueprint(platform_stats_bp)
        logger.info("✅ Platform Statistics API registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Platform Statistics API: {e}")
    
    # SSE Revocation Events API (real-time revocation notifications)
    try:
        from api.revocation_events import revocation_events_bp
        app.register_blueprint(revocation_events_bp)
        logger.info("✅ SSE Revocation Events API registered")
    except Exception as e:
        logger.error(f"❌ Failed to register SSE Revocation Events API: {e}")

    # Permission Type Management API (developer dashboard)
    try:
        from api.permission_type_api import permission_type_api
        app.register_blueprint(permission_type_api)
        logger.info("✅ Permission Type Management API registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Permission Type API: {e}")

    # SDK Remote Configuration (auto-update settings for all SDK instances)
    try:
        from api.sdk_config import sdk_config_bp
        app.register_blueprint(sdk_config_bp)
        logger.info("✅ SDK Remote Config API registered")
    except Exception as e:
        logger.error(f"❌ Failed to register SDK Config API: {e}")

    # SDK Integrity Hashes (SRI for supply chain security)
    try:
        from api.sri_hashes import sri_hashes_bp
        app.register_blueprint(sri_hashes_bp)
        logger.info("✅ SDK Integrity (SRI) API registered")
    except Exception as e:
        logger.error(f"❌ Failed to register SRI Hashes API: {e}")

    # Developer Self-Issue (developers can issue permissions to their own wallet)
    try:
        from api.developer_self_issue import developer_self_issue_bp
        app.register_blueprint(developer_self_issue_bp)
        logger.info("✅ Developer Self-Issue API registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Developer Self-Issue API: {e}")
    
    # Account Recovery
    try:
        from api.account_recovery import account_recovery_bp
        app.register_blueprint(account_recovery_bp)
        logger.info("✅ Account Recovery API registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Account Recovery API: {e}")
    
    # Developer Platform API (sites, stats, API keys)
    try:
        from api.developer_api import developer_api_bp
        app.register_blueprint(developer_api_bp)
        logger.info("✅ Developer Platform API registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Developer Platform API: {e}")

    # Agent Credentials API (passkey-authorized AI agent access)
    try:
        from api.agent_credentials import agent_credentials_bp
        app.register_blueprint(agent_credentials_bp)
        logger.info("✅ Agent Credentials API registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Agent Credentials API: {e}")

    # Public Demo API (real control-plane proxy routes)
    try:
        from api.demo_api import demo_api_bp
        app.register_blueprint(demo_api_bp)
        logger.info("✅ Demo API registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Demo API: {e}")

    try:
        from api.site_management_api import site_management_bp
        app.register_blueprint(site_management_bp)
        logger.info("✅ Site Management API registered (users, permissions, keys)")
    except Exception as e:
        logger.error(f"❌ Failed to register Site Management API: {e}")

    # Authz control-plane endpoints (v2 freshness APIs)
    try:
        from api.authz_control_plane import authz_control_bp
        app.register_blueprint(authz_control_bp)
        logger.info("✅ Authz Control Plane API registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Authz Control Plane API: {e}")

    # isHuman Network API (proof-of-humanity verification, site-blocks, revocation)
    try:
        from api.ishuman import ishuman_bp
        app.register_blueprint(ishuman_bp)
        logger.info("✅ isHuman Network API registered")
    except Exception as e:
        logger.error(f"❌ Failed to register isHuman Network API: {e}")

    # isHuman guided demo (thin wrapper around real issuance + verifier flows)
    try:
        from api.ishuman_demo import ishuman_demo_bp
        app.register_blueprint(ishuman_demo_bp)
        logger.info("✅ isHuman Demo registered")
    except Exception as e:
        logger.error(f"❌ Failed to register isHuman Demo: {e}")

    # Optional background freshness client for local-first authz runtime state.
    try:
        from api.authz.freshness_client import start_background_freshness_client

        if str(os.getenv("LEMMA_AUTHZ_ENABLE_FRESHNESS_CLIENT", "0")).strip().lower() in {"1", "true", "yes", "on"}:
            start_background_freshness_client()
            logger.info("✅ Authz Freshness Client started")
    except Exception as e:
        logger.warning(f"⚠️ Authz Freshness Client not started: {e}")

    # Health Monitoring
    try:
        from api.health_check import get_health_status
        logger.info("✅ Health Check system available")
    except Exception as e:
        logger.error(f"❌ Failed to initialize Health Check: {e}")

    # Initialize Revocation Event Bus (Redis pub/sub listener)
    # This must be done after all blueprints are registered
    try:
        from api.revocation_sync import get_event_bus, is_listening
        event_bus = get_event_bus()
        if is_listening():
            logger.info("✅ Revocation Event Bus initialized (Redis pub/sub listener active)")
        else:
            logger.warning("⚠️ Revocation Event Bus initialized (local mode - Redis unavailable)")
    except Exception as e:
        logger.warning(f"⚠️ Could not initialize Revocation Event Bus: {e}")

    # Session-free architecture: No server-side sessions needed!
    # Authentication is handled via client-side credential verification
    # with smart caching (5-minute TTL) and event-driven invalidation
    # This allows infinite scalability with zero server-side state

    # ================================================================================
    # HEALTH CHECK & MONITORING ENDPOINTS
    # ================================================================================

    @app.route('/health')
    def simple_health():
        """Simple health check endpoint for uptime monitoring"""
        try:
            # Check database connectivity
            from api.database import engine
            from sqlalchemy import text
            with engine.connect() as conn:
                conn.execute(text('SELECT 1'))
            
            return jsonify({
                'status': 'healthy',
                'timestamp': datetime.now().isoformat()
            }), 200
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return jsonify({
                'status': 'unhealthy',
                'error': str(e)
            }), 500

    @app.route('/ready')
    def ready_check():
        """Readiness check - detailed system status"""
        checks = {'database': False, 'crypto': False}
        
        try:
            from api.database import engine
            from sqlalchemy import text
            with engine.connect() as conn:
                conn.execute(text('SELECT 1'))
            checks['database'] = True
        except Exception as e:
            logger.warning(f"Database check failed: {e}")
        
        try:
            from lemma_crypto import PyMinimalVerifier
            PyMinimalVerifier()
            checks['crypto'] = True
        except Exception as e:
            logger.warning(f"Crypto check failed: {e}")
        
        all_healthy = all(checks.values())
        return jsonify({
            'ready': all_healthy,
            'checks': checks
        }), 200 if all_healthy else 503

    # ================================================================================
    # ESSENTIAL ROUTES ONLY
    # ================================================================================

    @app.route('/')
    def index():
        """
        Smart homepage routing:
        - Returning users (have session) → Lemma ID management app
        - New visitors → Marketing page (SEO optimized)

        This preserves SEO while giving existing users the "just type lemma.id" experience.
        """
        # Check if user has an existing session or has visited before
        has_session = request.cookies.get('lemma_wallet_session')
        has_wallet_cookie = request.cookies.get('lemma_wallet_csrf')

        if has_session or has_wallet_cookie:
            # Returning user with session → show app
            logger.info("🏠 Serving Lemma ID app (returning user)")
            app.jinja_env.cache = {}
            return render_template('wallet_simple.html'), 200, {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }
        else:
            # New visitor → show marketing page for SEO
            logger.info("🏠 Serving marketing page (new visitor)")
            return render_template('modern/index.html')

    @app.route('/app')
    def app_page():
        """Direct link to Lemma ID management app (bypasses smart routing)"""
        logger.info("🏠 Serving Lemma ID app (direct)")
        app.jinja_env.cache = {}
        return render_template('wallet_simple.html'), 200, {
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        }

    @app.route('/about')
    def about():
        """About Lemma - Marketing page covering origin, thesis, principles, founder, and vision."""
        logger.info("📄 Serving about page")
        return render_template('modern/about.html')

    @app.route('/trust')
    def trust():
        """Trust & data minimization - comparative transparency for users, integrators, and compliance."""
        logger.info("📄 Serving trust page")
        return render_template('modern/trust.html')

    @app.route('/partners')
    def partners():
        """Partners / For IDV Issuers - Marketing page targeting IDV provider partnerships"""
        logger.info("📄 Serving partners page")
        return render_template('modern/partners.html')

    @app.route('/lemma-sw.js')
    def service_worker():
        """Serve service worker from root for proper scope"""
        from flask import send_from_directory
        response = send_from_directory('static', 'sw.js', mimetype='application/javascript')
        # Force browsers to revalidate the service worker file on each navigation,
        # so route/template updates are applied without prolonged stale caching.
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response

    @app.route('/wallet')
    def wallet():
        """Legacy redirect: /wallet -> /app"""
        from flask import redirect
        return redirect('/app', code=301)

    @app.route('/wallet/simple')
    def wallet_simple():
        """Legacy redirect: /wallet/simple -> /app"""
        from flask import redirect
        return redirect('/app', code=301)
    
    @app.route('/wallet/popup')
    def wallet_popup():
        """Popup Wallet Unlock for Third-Party Sites"""
        logger.info("🔓 Serving popup unlock page")
        return render_template('wallet_popup.html'), 200, {
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        }
    
    @app.route('/link')
    def link_device():
        """Add Device Page - Add this device to existing Lemma ID"""
        logger.info("🔗 Serving add device page")
        return render_template('wallet_link.html'), 200, {
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        }

    @app.route('/wallet/link')
    def wallet_link():
        """Legacy redirect: /wallet/link -> /link"""
        from flask import redirect
        return redirect('/link', code=301)

    @app.route('/unlock')
    def unlock():
        """
        Sign-in page for redirect-based authentication.

        FLOW (lemma-credential redirect):
        1. Third-party SDK redirects here with return_url (+ optional state)
        2. User signs in via passkey (or uses existing session)
        3. lemma.id issues a site-bound signed credential (wallet_secret stays local)
        4. User redirected back to return_url with lemma_credential in the URL
        5. SDK stores the credential locally and establishes session

        This provides consistent UX across all platforms while preserving privacy.
        """
        logger.info("Serving sign-in page (redirect-based auth)")
        return render_template('wallet_unlock.html'), 200, {
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        }

    @app.route('/wallet/unlock')
    def wallet_unlock():
        """Legacy redirect: /wallet/unlock -> /unlock"""
        from flask import redirect, request
        # Preserve query params for redirect flow
        if request.query_string:
            return redirect(f'/unlock?{request.query_string.decode()}', code=302)
        return redirect('/unlock', code=301)

    # The cross-origin wallet bridge iframe and its denial telemetry endpoint
    # were removed in Phase 2.1. Verification and cross-site session flows are
    # popup-only now.

    # ================================================================================
    # HIGH-SECURITY: Fresh Authentication Verification API
    # For banks, financial apps that need server-side verification of auth freshness
    # ================================================================================
    
    @app.route('/api/verify-session-freshness', methods=['POST'])
    def verify_session_freshness():
        """
        Server-side verification of authentication freshness.
        
        High-security sites (banks, financial apps) can call this endpoint
        to verify that a user's authentication is genuinely fresh - not just
        trusting the client-side timestamp.
        
        Request body:
        {
            "walletId": "user's wallet ID",
            "authTimestamp": 1234567890123,  // Claimed auth timestamp
            "maxAgeMs": 30000  // Max acceptable age (default 30s)
        }
        
        Response:
        {
            "valid": true/false,
            "fresh": true/false,
            "reason": "valid" | "timestamp_mismatch" | "too_old" | "unknown_wallet"
        }
        
        SECURITY NOTES:
        - This endpoint allows sites to verify client claims
        - Without this, a compromised client could lie about auth freshness
        - Rate limited to prevent enumeration attacks
        """
        from flask import request
        
        data = request.get_json() or {}
        wallet_id = data.get('walletId')
        claimed_timestamp = data.get('authTimestamp')
        max_age_ms = data.get('maxAgeMs', 30000)
        
        if not wallet_id or not claimed_timestamp:
            return jsonify({
                'valid': False,
                'fresh': False,
                'reason': 'missing_parameters'
            }), 400
        
        # In production, this would check against a server-side session store
        # For now, we validate the timestamp is reasonable (not in future, not ancient)
        import time
        current_time = int(time.time() * 1000)
        
        # Validate timestamp is reasonable
        if claimed_timestamp > current_time + 60000:  # Allow 1 min clock drift
            return jsonify({
                'valid': False,
                'fresh': False,
                'reason': 'timestamp_in_future'
            })
        
        age_ms = current_time - claimed_timestamp
        
        if age_ms > max_age_ms:
            return jsonify({
                'valid': True,  # Timestamp is valid
                'fresh': False,  # But not fresh enough
                'reason': 'too_old',
                'ageMs': age_ms,
                'maxAgeMs': max_age_ms
            })
        
        # For true production security, we would:
        # 1. Store auth events server-side when they happen
        # 2. Verify the claimed timestamp matches our record
        # 3. Sign the response so sites can trust it
        
        return jsonify({
            'valid': True,
            'fresh': True,
            'reason': 'valid',
            'ageMs': age_ms,
            'maxAgeMs': max_age_ms,
            'verifiedAt': current_time
        })

    @app.route('/sdk/lemma-wallet.js')
    def lemma_wallet_sdk_fresh():
        """
        Serve the Lemma wallet SDK with no-cache headers for development.
        Use this endpoint when you need the absolute latest version.
        """
        from flask import send_from_directory
        response = send_from_directory('static/js', 'lemma-wallet.js', mimetype='application/javascript')
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        response.headers['X-SDK-Version'] = '2.36.0'
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response

    @app.route('/sdk/ishuman-verifier.js')
    def ishuman_verifier_sdk():
        """Serve the isHuman verifier SDK with cache-busting headers."""
        from flask import send_from_directory
        response = send_from_directory('static/js', 'ishuman-verifier.js', mimetype='application/javascript')
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        response.headers['X-SDK-Version'] = '1.7.1'
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response

    @app.route('/sdk/lemma-ishuman-verify.mjs')
    def ishuman_verify_backend_sdk():
        """Serve the relying-site backend verifier (Node.js/Deno/Workers/Bun/browser).

        Usage:
            import { createVerifier } from "https://lemma.id/sdk/lemma-ishuman-verify.mjs";
        """
        from flask import send_from_directory
        response = send_from_directory('static/js', 'lemma-ishuman-verify.mjs', mimetype='application/javascript')
        response.headers['Cache-Control'] = 'public, max-age=300'
        response.headers['X-SDK-Version'] = '1.2.0'
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response

    @app.route('/sdk/lemma_ishuman_verify.py')
    def ishuman_verify_python_sdk():
        """Serve the relying-site backend verifier for Python.

        Usage:
            curl -O https://lemma.id/sdk/lemma_ishuman_verify.py
            from lemma_ishuman_verify import VerificationContext
        """
        from flask import send_from_directory
        response = send_from_directory(
            'examples', 'relying_site_offline_verify.py', mimetype='text/x-python',
        )
        response.headers['Cache-Control'] = 'public, max-age=300'
        response.headers['X-SDK-Version'] = '1.2.0'
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response

    @app.route('/static/js/lemma-wallet.js')
    def lemma_wallet_static_fresh():
        """
        Override Flask's default static serving for lemma-wallet.js
        to ensure no caching - critical for SDK updates.
        """
        from flask import send_from_directory
        response = send_from_directory('static/js', 'lemma-wallet.js', mimetype='application/javascript')
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        response.headers['X-SDK-Version'] = '2.36.0'
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response

    # Essential pages
    @app.route('/pricing')
    def pricing():
        return render_template('modern/pricing_new.html')

    # ==================== DOCUMENTATION ====================
    @app.route('/docs')
    def docs_overview():
        """Public docs entrypoint — lemma.id proof of humanity."""
        return render_template('docs/ishuman.html')

    @app.route('/docs/agents')
    def docs_agents():
        """Agent Ops and Lemma Firewall documentation."""
        return render_template('docs/agents.html')

    @app.route('/docs/overview')
    def docs_overview_alias():
        """Legacy agent overview alias."""
        return redirect(url_for('docs_agents'), code=301)
    
    @app.route('/docs/quickstart')
    def docs_quickstart():
        """Legacy Agent Ops quickstart alias."""
        return redirect(f"{url_for('docs_agents')}#quickstart", code=301)
    
    @app.route('/docs/installation')
    def docs_installation():
        """Legacy Agent Ops installation alias."""
        return redirect(f"{url_for('docs_agents')}#installation", code=301)

    @app.route('/docs/cli')
    def docs_cli():
        """Legacy Agent Ops CLI alias."""
        return redirect(f"{url_for('docs_agents')}#cli", code=301)
    
    @app.route('/docs/wallet-flow')
    def docs_wallet_flow():
        """Legacy wallet-flow alias."""
        return redirect(url_for('docs_overview'), code=301)
    
    @app.route('/docs/verification')
    def docs_verification():
        """Legacy verification guide alias."""
        return redirect(url_for('docs_overview'), code=301)
    
    @app.route('/docs/permissions')
    def docs_permissions():
        """Legacy permissions guide alias."""
        return redirect(url_for('docs_overview'), code=301)

    @app.route('/docs/ishuman')
    def docs_ishuman():
        """Legacy alias — canonical docs live at /docs."""
        return redirect(url_for('docs_overview'), code=301)
    
    @app.route('/docs/sdk')
    def docs_sdk_js():
        """Legacy SDK docs alias."""
        return redirect(url_for('docs_overview'), code=301)
    
    @app.route('/docs/sdk/methods')
    def docs_sdk_methods():
        """Legacy SDK methods alias."""
        return redirect(url_for('docs_overview'), code=301)
    
    @app.route('/docs/sdk/events')
    def docs_sdk_events():
        """Legacy SDK events alias."""
        return redirect(url_for('docs_overview'), code=301)
    
    @app.route('/docs/api/auth')
    def docs_api_auth():
        """Legacy auth API alias."""
        return redirect(f"{url_for('docs_agents')}#api-reference", code=301)
    
    @app.route('/docs/api/verification')
    def docs_api_verification():
        """Legacy verification API alias."""
        return redirect(url_for('docs_overview'), code=301)
    
    @app.route('/docs/api/revocation')
    def docs_api_revocation():
        """Legacy revocation API alias."""
        return redirect(url_for('docs_overview'), code=301)
    
    @app.route('/docs/errors')
    def docs_error_codes():
        """Legacy error docs alias."""
        return redirect(url_for('docs_overview'), code=301)
    
    @app.route('/docs/examples')
    def docs_examples():
        """Legacy examples alias."""
        return redirect(f"{url_for('docs_agents')}#examples", code=301)
    
    @app.route('/docs/changelog')
    def docs_changelog():
        """Legacy changelog alias."""
        return redirect(url_for('docs_overview'), code=301)
    
    @app.route('/docs/setup')
    def docs_setup():
        """Legacy setup generator alias."""
        return redirect(url_for('docs_overview'), code=301)
    
    @app.route('/docs/iam')
    def docs_iam_legacy():
        """Legacy IAM docs - redirect to overview"""
        return redirect('/docs')

    # Legal pages
    @app.route('/terms')
    def terms_of_service():
        """Terms of Service"""
        return render_template('legal/terms.html')

    @app.route('/privacy')
    def privacy_policy():
        """Privacy Policy"""
        return render_template('legal/privacy.html')

    # Dashboard routes
    @app.route('/dashboard')
    def customer_dashboard():
        """Redirect old dashboard to developer platform"""
        return redirect('/developer')
    
    @app.route('/platform')
    def developer_platform_legacy():
        """Redirect legacy platform to developer dashboard"""
        return redirect('/developer/platform')
    
    # ================================================================================
    # ACCOUNT RECOVERY ROUTES
    # ================================================================================
    
    @app.route('/recover')
    def recover_account_page():
        """Account recovery - enter API key and site ID"""
        return render_template('recover.html')
    
    @app.route('/recover/complete')
    def recover_complete_page():
        """Account recovery - complete with passkey registration"""
        token = request.args.get('token', '')
        return render_template('recover_complete.html', token=token)
    
    # ================================================================================
    # DEVELOPER PLATFORM ROUTES
    # ================================================================================

    @app.route('/demo')
    def public_demo_playground():
        """Public demo entrypoint: isHuman is the core product demo."""
        return redirect('/demo/ishuman', code=302)

    @app.route('/demo/firewall')
    def public_firewall_demo_playground():
        """Deprecated Agent Ops / Lemma Firewall demo retained as a legacy deep link."""
        return render_template(
            'demo/index.html',
            demo_runtime_id=(os.environ.get('LEMMA_DEMO_PUBLIC_RUNTIME_ID') or 'lemma-firewall-demo-runtime').strip() or 'lemma-firewall-demo-runtime',
        )
    
    @app.route('/developer')
    def developer_overview():
        """Public developer entrypoint redirects to isHuman hub."""
        logger.info("↪️ Redirecting /developer to /developer/ishuman")
        response = redirect('/developer/ishuman', code=302)
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        response.headers['X-Lemma-Developer-Platform'] = 'ishuman-redirect-v1'
        return response

    @app.route('/developer/ishuman')
    def developer_ishuman():
        """Public isHuman developer platform entrypoint."""
        logger.info("🚀 Serving isHuman developer platform")
        return render_template(
            'developer/ishuman_platform.html',
            user_email=request.headers.get('X-User-Email'),
            user_name=None,
            is_admin=request.headers.get('X-Permission-ID', '').lower() in ['super_admin', 'admin_access']
        ), 200, {
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0',
            'X-Lemma-Developer-Platform': 'ishuman-public-v1'
        }

    @app.route('/developer/platform')
    def developer_platform():
        """Compatibility redirect for older platform links."""
        logger.info("↪️ Redirecting /developer/platform to /developer")
        return redirect('/developer')

    @app.route('/developer/issue-proof')
    def developer_issue_proof():
        """Retired public Agent Ops route kept as compatibility redirect."""
        logger.info("↪️ Redirecting deprecated public Agent Ops route: /developer/issue-proof")
        return redirect('/developer')

    @app.route('/developer/proofs')
    def developer_proofs():
        """Retired public Agent Ops route kept as compatibility redirect."""
        logger.info("↪️ Redirecting deprecated public Agent Ops route: /developer/proofs")
        return redirect('/developer')

    @app.route('/developer/settings')
    def developer_settings():
        """Retired public Agent Ops route kept as compatibility redirect."""
        logger.info("↪️ Redirecting deprecated public Agent Ops route: /developer/settings")
        return redirect('/developer')
    
    @app.route('/developer/sites')
    def developer_sites():
        """Legacy sites page removed from public UX."""
        logger.info("🌐 Redirecting deprecated /developer/sites to /developer")
        return redirect('/developer')
    
    @app.route('/developer/sites/new')
    def developer_sites_new():
        """Legacy create-site route redirected to developer hub."""
        return redirect('/developer')
    
    @app.route('/developer/sites/<site_id>')
    def developer_site_detail(site_id):
        """Legacy site dashboard route redirected to developer hub."""
        logger.info("📊 Redirecting deprecated site dashboard route: %s", site_id)
        return redirect('/developer')
    
    @app.route('/developer/sites/<site_id>/integration')
    def developer_site_integration(site_id):
        """Legacy site integration route redirected to developer hub."""
        logger.info("🧩 Redirecting deprecated site integration route: %s", site_id)
        return redirect('/developer')
    
    @app.route('/developer/sites/<site_id>/keys')
    def developer_site_keys(site_id):
        """Developer Platform - Site API keys management (legacy admin surface)."""
        logger.info(f"🔑 Serving API keys page: {site_id}")
        return _require_wallet_session(
            'developer/site_keys.html',
            site_id=site_id,
            user_email=request.headers.get('X-User-Email'),
            is_admin=request.headers.get('X-Permission-ID', '').lower() in ['super_admin', 'admin_access']
        )

    @app.route('/developer/external-api-keys')
    def developer_external_api_keys():
        """Developer Platform - external/customer API key manager."""
        logger.info("🔑 Serving external API key manager")
        return _require_wallet_session(
            'developer/external_api_keys_mvp.html',
            user_email=request.headers.get('X-User-Email'),
            user_name=None,
            is_admin=request.headers.get('X-Permission-ID', '').lower() in ['super_admin', 'admin_access']
        )
    
    @app.route('/developer/sites/<site_id>/users')
    def developer_site_users(site_id):
        """Legacy site users route redirected to developer hub."""
        logger.info("👥 Redirecting deprecated site users route: %s", site_id)
        return redirect('/developer')
    
    @app.route('/developer/sites/<site_id>/permissions')
    def developer_site_permissions(site_id):
        """Legacy site permissions route redirected to developer hub."""
        logger.info("🎫 Redirecting deprecated site permissions route: %s", site_id)
        return redirect('/developer')
    
    @app.route('/developer/sites/<site_id>/settings')
    def developer_site_settings(site_id):
        """Legacy site settings route redirected to developer hub."""
        logger.info("⚙️ Redirecting deprecated site settings route: %s", site_id)
        return redirect('/developer')
    
    @app.route('/developer/usage')
    def developer_usage():
        """Legacy usage route redirected to developer hub."""
        return redirect('/developer')

    @app.route('/developer/agent-delegation')
    def developer_agent_delegation():
        """Legacy agent delegation route redirected to developer hub."""
        return redirect('/developer')
    
    @app.route('/developer/billing')
    def developer_billing():
        """Developer Platform - Billing"""
        return redirect('/pricing')
    
    @app.route('/docs/<path:filename>')
    def serve_docs(filename):
        """Serve documentation markdown files"""
        from flask import send_from_directory, Response
        logger.info(f"📄 Serving documentation: {filename}")
        try:
            # Serve markdown files with correct MIME type
            response = send_from_directory('docs', filename)
            if filename.endswith('.md'):
                response.headers['Content-Type'] = 'text/markdown; charset=utf-8'
            return response
        except FileNotFoundError:
            return "Documentation not found", 404

    # ==================== ADMIN PLATFORM ====================
    # SECURITY: Server-side gate requires active wallet session to serve admin pages.
    # Defense-in-depth:
    #   Layer 1 (server): Wallet session cookie required (blocks anonymous visitors)
    #   Layer 2 (client): JS verifies admin credential via Ed25519 + bloom filter
    #   Layer 3 (API): require_admin decorator on all admin API endpoints
    
    def _require_wallet_session(template_name, **template_kwargs):
        """
        Server-side guard for admin pages.
        Requires an active wallet session cookie (or an authenticated admin
        agent session) before serving admin HTML.
        Returns the rendered template with noindex headers if session exists,
        or redirects to home if no session.
        """
        has_session = request.cookies.get('lemma_wallet_session')
        has_wallet_cookie = request.cookies.get('lemma_wallet_csrf')
        has_admin_agent_session = bool(session.get('agent_authenticated') and session.get('is_admin'))
        
        if not has_session and not has_wallet_cookie and not has_admin_agent_session:
            logger.warning(f"Admin page access denied - no wallet session: {request.path} from {request.remote_addr}")
            return redirect('/')
        
        response = render_template(template_name, **template_kwargs)
        return response, 200, {
            'X-Robots-Tag': 'noindex, nofollow',
            'Cache-Control': 'no-cache, no-store, must-revalidate, private',
            'Pragma': 'no-cache',
            'Expires': '0'
        }

    @app.route('/admin/agent-ops')
    def admin_agent_ops():
        """Admin-only archived Agent Ops dashboard."""
        logger.info("Serving admin archived Agent Ops dashboard")
        return _require_wallet_session(
            'developer/agent_ops_mvp.html',
            screen='dashboard',
            user_email=request.headers.get('X-User-Email'),
            user_name=None,
            is_admin=request.headers.get('X-Permission-ID', '').lower() in ['super_admin', 'admin_access']
        )

    @app.route('/admin/agent-ops/issue-proof')
    def admin_agent_ops_issue_proof():
        """Admin-only archived Agent Ops issue proof screen."""
        logger.info("Serving admin archived Agent Ops issue proof")
        return _require_wallet_session(
            'developer/agent_ops_mvp.html',
            screen='issue_proof',
            user_email=request.headers.get('X-User-Email'),
            user_name=None,
            is_admin=request.headers.get('X-Permission-ID', '').lower() in ['super_admin', 'admin_access']
        )

    @app.route('/admin/agent-ops/proofs')
    def admin_agent_ops_proofs():
        """Admin-only archived Agent Ops proofs screen."""
        logger.info("Serving admin archived Agent Ops proofs")
        return _require_wallet_session(
            'developer/agent_ops_mvp.html',
            screen='proofs',
            user_email=request.headers.get('X-User-Email'),
            user_name=None,
            is_admin=request.headers.get('X-Permission-ID', '').lower() in ['super_admin', 'admin_access']
        )

    @app.route('/admin/agent-ops/settings')
    def admin_agent_ops_settings():
        """Admin-only archived Agent Ops settings screen."""
        logger.info("Serving admin archived Agent Ops settings")
        return _require_wallet_session(
            'developer/agent_ops_mvp.html',
            screen='settings',
            user_email=request.headers.get('X-User-Email'),
            user_name=None,
            is_admin=request.headers.get('X-Permission-ID', '').lower() in ['super_admin', 'admin_access']
        )

    @app.route('/admin')
    def admin_dashboard():
        """Admin Dashboard - Platform overview"""
        logger.info("Serving admin dashboard")
        return _require_wallet_session('admin/dashboard.html')
    
    @app.route('/admin/monitoring')
    def admin_monitoring_page():
        """Admin Monitoring - Bloom filter, system health"""
        logger.info("Serving admin monitoring")
        return _require_wallet_session('admin/platform_monitoring.html')
    
    @app.route('/admin/health')
    def admin_health_page():
        """Admin Health - System health details"""
        logger.info("Serving admin health")
        return _require_wallet_session('admin/health.html')
    
    @app.route('/admin/users')
    def admin_users():
        """Admin Users - User management"""
        logger.info("Serving admin users")
        return _require_wallet_session('admin/users.html')
    
    @app.route('/admin/sites')
    def admin_sites():
        """Admin Sites - All registered sites"""
        logger.info("Serving admin sites")
        return _require_wallet_session('admin/sites.html')

    @app.route('/admin/site-manager')
    def admin_site_manager_legacy():
        """Admin-only legacy site manager list."""
        logger.info("Serving admin legacy site manager list")
        return _require_wallet_session(
            'developer/sites/list.html',
            layout_template='admin/layout.html',
            active_page='legacy_site_manager',
            sites_base_path='/admin/site-manager'
        )

    @app.route('/admin/site-manager/<site_id>')
    def admin_site_manager_legacy_detail(site_id):
        """Admin-only legacy site manager detail."""
        logger.info("Serving admin legacy site manager detail: %s", site_id)
        return _require_wallet_session(
            'developer/sites/detail.html',
            layout_template='admin/layout.html',
            active_page='legacy_site_manager',
            site_id=site_id,
            tab='overview',
            sites_base_path='/admin/site-manager'
        )

    @app.route('/admin/site-manager/<site_id>/integration')
    def admin_site_manager_legacy_integration(site_id):
        """Admin-only legacy site manager integration tab."""
        return _require_wallet_session(
            'developer/sites/detail.html',
            layout_template='admin/layout.html',
            active_page='legacy_site_manager',
            site_id=site_id,
            tab='integration',
            sites_base_path='/admin/site-manager'
        )

    @app.route('/admin/site-manager/<site_id>/keys')
    def admin_site_manager_legacy_keys(site_id):
        """Admin-only legacy site manager API keys tab."""
        return _require_wallet_session(
            'developer/sites/detail.html',
            layout_template='admin/layout.html',
            active_page='legacy_site_manager',
            site_id=site_id,
            tab='keys',
            sites_base_path='/admin/site-manager'
        )

    @app.route('/admin/site-manager/<site_id>/users')
    def admin_site_manager_legacy_users(site_id):
        """Admin-only legacy site manager users tab."""
        return _require_wallet_session(
            'developer/sites/detail.html',
            layout_template='admin/layout.html',
            active_page='legacy_site_manager',
            site_id=site_id,
            tab='users',
            sites_base_path='/admin/site-manager'
        )

    @app.route('/admin/site-manager/<site_id>/settings')
    def admin_site_manager_legacy_settings(site_id):
        """Admin-only legacy site manager settings tab."""
        return _require_wallet_session(
            'developer/sites/detail.html',
            layout_template='admin/layout.html',
            active_page='legacy_site_manager',
            site_id=site_id,
            tab='settings',
            sites_base_path='/admin/site-manager'
        )
    
    @app.route('/admin/credentials')
    def admin_credentials():
        """Admin Credentials - Credential management"""
        logger.info("Serving admin credentials")
        return _require_wallet_session('admin/credentials.html')
    
    @app.route('/admin/revocations')
    def admin_revocations():
        """Admin Revocations - Revocation management"""
        logger.info("Serving admin revocations")
        return _require_wallet_session('admin/revocations.html')
    
    @app.route('/admin/audit')
    def admin_audit():
        """Admin Audit - Audit log"""
        logger.info("Serving admin audit")
        return _require_wallet_session('admin/audit.html')

    @app.route('/admin/debug')
    def admin_debug():
        """Admin Debug - API endpoint testing for agent debugging"""
        logger.info("Serving admin debug dashboard")
        return _require_wallet_session('admin/debug.html')

    @app.route('/admin/agent-delegation')
    def admin_agent_delegation():
        """Admin legacy agent delegator (direct legacy template)."""
        logger.info("Serving admin legacy agent delegator")
        return _require_wallet_session('developer/agent_delegation.html')

    @app.route('/admin/agent-delegation/legacy-ui')
    def admin_agent_delegation_legacy_ui():
        """Legacy compatibility redirect to admin agent delegator."""
        return redirect('/admin/agent-delegation')

    @app.route('/admin/bootstrap')
    def admin_bootstrap():
        """Admin credential bootstrap page"""
        return _require_wallet_session('modern/admin_bootstrap.html')
    
    # Legacy redirects
    @app.route('/admin/legacy')
    def admin_dashboard_legacy():
        return redirect('/admin')
    
    @app.route('/admin/iam')
    def admin_iam_redirect():
        return redirect('/admin')

    # CSP violation reports (XSS detection)
    @app.route('/api/security/csp-report', methods=['POST'])
    def csp_report():
        """Accept browser CSP violation reports. No PII; log + optional Sentry."""
        payload = request.get_json(silent=True)
        if payload is None:
            raw = request.get_data(as_text=True) or ''
            try:
                import json as _json
                payload = _json.loads(raw) if raw else {}
            except Exception:
                payload = {}

        report = payload.get('csp-report') if isinstance(payload, dict) else None
        if not isinstance(report, dict):
            report = payload if isinstance(payload, dict) else {}

        violated = str(report.get('violated-directive') or report.get('effective-directive') or 'unknown')
        blocked = str(report.get('blocked-uri') or '')
        document_uri = str(report.get('document-uri') or report.get('source-file') or '')

        logger.warning(
            "CSP violation: directive=%s blocked=%s document=%s",
            violated,
            blocked[:200],
            document_uri[:200],
        )

        try:
            import sentry_sdk
            if sentry_sdk.Hub.current.client:
                sentry_sdk.capture_message(
                    f"CSP violation: {violated}",
                    level='warning',
                    tags={'security': 'csp', 'violated_directive': violated[:100]},
                    extras={'blocked_uri': blocked[:500], 'document_uri': document_uri[:500]},
                )
        except Exception:
            pass

        return ('', 204)

    # Health check
    @app.route('/api/health')
    def health():
        components = {
            'lemma_shield': True,
            'crypto_engine': True,
            'stripe_integration': 'STRIPE_SECRET_KEY' in os.environ,
        }

        return jsonify({
            'status': 'ok',
            'service': 'lemma-platform',
            'version': '4.0.0',
            'components': components,
            'endpoints': 'essential_only'
        })

    # Health monitoring
    @app.route('/api/health/check')
    def health_check():
        """System health check"""
        try:
            from api.health_check import get_health_status
            health_data = get_health_status()

            status_code = 200
            if health_data.get('status') == 'critical':
                status_code = 503
            elif health_data.get('status') == 'degraded':
                status_code = 206

            return jsonify(health_data), status_code

        except Exception as e:
            logger.error(f"Health check error: {e}")
            return jsonify({
                'status': 'critical',
                'error': 'health_check_failed',
                'message': str(e)
            }), 503

    # CORS handling
    @app.before_request
    def handle_cors_preflight():
        if request.method == "OPTIONS":
            if request.path.startswith('/api/'):
                from flask import make_response
                from urllib.parse import urlparse
                response = make_response()
                origin = request.headers.get('Origin')

                allowed_origins = {
                    o.strip().lower()
                    for o in os.environ.get('LEMMA_ALLOWED_ORIGINS', '').split(',')
                    if o.strip()
                }
                allowed_suffixes = [
                    s.strip().lower()
                    for s in os.environ.get('LEMMA_ALLOWED_ORIGIN_SUFFIXES', '').split(',')
                    if s.strip()
                ]
                allow_dev = os.environ.get('LEMMA_ALLOW_DEV_ORIGINS', '1') != '0'

                is_allowed = False
                if origin:
                    parsed = urlparse(origin)
                    hostname = parsed.hostname or ''
                    if origin.lower() in allowed_origins:
                        is_allowed = True
                    elif hostname:
                        for suffix in allowed_suffixes:
                            if hostname.endswith(suffix.lstrip('.')):
                                is_allowed = True
                                break
                    if allow_dev and hostname in {'localhost', '127.0.0.1'}:
                        is_allowed = True

                response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
                response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-API-Key, X-Lemma-CSRF, X-CSRF-Token'
                response.headers['Vary'] = 'Origin'

                if origin and is_allowed:
                    response.headers['Access-Control-Allow-Origin'] = origin
                    response.headers['Access-Control-Allow-Credentials'] = 'true'
                    return response

                # Harden API preflight handling: unknown origins should not receive
                # permissive wildcard CORS headers on privileged API surfaces.
                if origin and not is_allowed:
                    return response, 403

                # Non-browser/internal OPTIONS requests may omit Origin.
                return response

    # Error handlers
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            'error': 'not_found',
            'message': 'Endpoint not found',
            'version': '4.0.0'
        }), 404

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({
            'error': 'internal_error',
            'message': 'Internal server error',
            'version': '4.0.0'
        }), 500

    return app

# Create the app
app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
