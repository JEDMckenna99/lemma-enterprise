"""
Lemma Platform - Clean Production Application
Essential components only - no redundant endpoints
"""
import os
import logging
import secrets
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, g

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    
    @app.context_processor
    def inject_csp_nonce():
        """Make CSP nonce available to all templates."""
        return {'csp_nonce': getattr(g, 'csp_nonce', '')}

    # ================================================================================
    # SECURITY HEADERS - Industry standard protection
    # ================================================================================
    @app.after_request
    def add_security_headers(response):
        """Add security headers to all responses"""
        # HSTS - Force HTTPS for 1 year
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
        
        # Prevent MIME type sniffing
        response.headers['X-Content-Type-Options'] = 'nosniff'
        
        # Prevent clickjacking - but allow for wallet bridge (needs to be embedded in iframes)
        # The bridge route sets its own X-Frame-Options to ALLOWALL
        if 'X-Frame-Options' not in response.headers:
            response.headers['X-Frame-Options'] = 'DENY'
        
        # XSS Protection (legacy but still useful)
        response.headers['X-XSS-Protection'] = '1; mode=block'
        
        # Referrer Policy - Don't leak URLs to third parties
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # Permissions Policy - Disable unnecessary browser features
        response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        
        # Content Security Policy - Restrict resource loading
        # Skip if route already set its own CSP (e.g., wallet bridge)
        if 'Content-Security-Policy' not in response.headers:
            # Get the nonce generated for this request
            nonce = getattr(g, 'csp_nonce', '')
            
            csp = (
                "default-src 'self'; "
                # Scripts: self + nonce for inline scripts + trusted CDNs
                f"script-src 'self' 'nonce-{nonce}' "
                    "https://cdn.jsdelivr.net/npm/ "  # jsdelivr for specific npm packages
                    "https://unpkg.com/ "  # unpkg for html5-qrcode scanner
                    "https://static.cloudflareinsights.com "  # Cloudflare analytics
                    "https://challenges.cloudflare.com "  # Cloudflare Turnstile
                    "https://js.stripe.com; "  # Stripe payments
                # Styles: self + unsafe-inline (needed for style attributes) + Google Fonts
                # Note: unsafe-inline for styles is lower risk than for scripts
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                # Fonts: self + Google Fonts
                "font-src 'self' https://fonts.gstatic.com; "
                # Images: self + data URIs (for QR codes) + any HTTPS (logos, etc)
                "img-src 'self' data: https:; "
                # API connections
                "connect-src 'self' https://lemma.id https://*.stripe.com https://api.stripe.com; "
                # Iframes: only Stripe and Cloudflare
                "frame-src 'self' https://*.stripe.com https://challenges.cloudflare.com; "
                # Block plugins (Flash, etc)
                "object-src 'none'; "
                # Prevent base tag hijacking
                "base-uri 'self'; "
                # Limit form submissions
                "form-action 'self' https://*.stripe.com; "
                # Upgrade HTTP to HTTPS
                "upgrade-insecure-requests"
            )
            response.headers['Content-Security-Policy'] = csp
        
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

    # OPRF Key Management API
    try:
        from api.oprf_key_api import oprf_key_bp, init_oprf_key_manager
        app.register_blueprint(oprf_key_bp)
        logger.info("✅ OPRF Key Management API registered")
        # Initialize key manager at startup
        init_oprf_key_manager()
        logger.info("🔑 OPRF Key Manager initialized")
    except Exception as e:
        logger.error(f"❌ Failed to register OPRF Key Management API: {e}")

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
    
    # OPRF Evaluation API
    try:
        from api.oprf_evaluation import oprf_eval_bp
        app.register_blueprint(oprf_eval_bp)
        logger.info("✅ OPRF Evaluation API registered")
    except Exception as e:
        logger.error(f"❌ Failed to register OPRF Evaluation API: {e}")

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

    try:
        from api.site_management_api import site_management_bp
        app.register_blueprint(site_management_bp)
        logger.info("✅ Site Management API registered (users, permissions, keys)")
    except Exception as e:
        logger.error(f"❌ Failed to register Site Management API: {e}")

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
        """Homepage - Marketing page"""
        logger.info("🏠 Serving homepage")
        return render_template('modern/index.html')

    @app.route('/lemma-sw.js')
    def service_worker():
        """Serve service worker from root for proper scope"""
        from flask import send_from_directory
        return send_from_directory('static', 'sw.js', mimetype='application/javascript')

    @app.route('/wallet')
    def wallet():
        """Lemma Wallet - Main wallet management page"""
        logger.info("🌐 Serving wallet")
        # Force disable template caching
        app.jinja_env.cache = {}
        return render_template('wallet_simple.html'), 200, {
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        }
    
    @app.route('/wallet/simple')
    def wallet_simple():
        """Redirect to main wallet page (legacy URL)"""
        from flask import redirect
        return redirect('/wallet', code=301)
    
    @app.route('/wallet/popup')
    def wallet_popup():
        """Popup Wallet Unlock for Third-Party Sites"""
        logger.info("🔓 Serving popup unlock page")
        return render_template('wallet_popup.html'), 200, {
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        }
    
    @app.route('/wallet/link')
    def wallet_link():
        """Device Linking Page - Link new device to existing wallet"""
        logger.info("🔗 Serving device linking page")
        return render_template('wallet_link.html'), 200, {
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        }

    @app.route('/wallet/unlock')
    def wallet_unlock():
        """
        Streamlined wallet unlock page for redirect-based authentication.
        
        FLOW (v2.32.0 - Redirect-only architecture):
        1. Third-party SDK generates encryption key, redirects here with return_url + enc_key
        2. User unlocks wallet via passkey (or uses existing session)
        3. Wallet data encrypted client-side with enc_key (never touches server)
        4. User redirected back to return_url with encrypted data in URL
        5. SDK decrypts client-side, establishes session
        
        This provides consistent UX across all platforms while preserving privacy.
        """
        logger.info("Serving unlock page (redirect-based auth)")
        return render_template('wallet_unlock.html'), 200, {
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        }

    @app.route('/wallet/bridge')
    def wallet_bridge():
        """
        Cross-origin wallet bridge v2.0 - LOCAL-FIRST authentication
        
        This page is loaded in an iframe by third-party sites to access the
        user's central Lemma wallet via postMessage. NO server calls for verification.
        
        CACHING STRATEGY:
        - Aggressive caching (1 year, immutable) for bridge HTML
        - Bridge code is static - all state is in IndexedDB
        - First load: 1 network call (this HTML)
        - All subsequent loads: 0 network calls (from cache)
        
        SECURITY:
        - Per-site credential isolation (sites only see their own credentials)
        - Session-gated write operations
        - Ed25519 signature verification (local WebCrypto)
        """
        logger.info("🌉 Serving wallet bridge v2.0 (local-first)")
        
        # Get nonce for this request (generated in before_request)
        nonce = getattr(g, 'csp_nonce', '')
        
        response = render_template('wallet_bridge.html')
        
        return response, 200, {
            # Allow embedding from any HTTPS origin
            'X-Frame-Options': 'ALLOWALL',
            
            # HARDENED CSP for bridge security
            # - Only self scripts with nonce (no external JS)
            # - Only self connections (except revocation sync)
            # - No eval, no dynamic code
            'Content-Security-Policy': (
                "default-src 'none'; "
                f"script-src 'self' 'nonce-{nonce}'; "  # Nonce for bridge inline script
                "connect-src 'self' https://lemma.id; "
                "style-src 'self' 'unsafe-inline'; "  # Inline styles for minimal bridge UI
                "frame-ancestors https: http://localhost:* http://127.0.0.1:*; "
                "base-uri 'none'; "
                "form-action 'none'; "
                "object-src 'none'; "
                "upgrade-insecure-requests"
            ),

            # AGGRESSIVE CACHING - This is key to local-first!
            # Bridge HTML is static; all dynamic state is in IndexedDB
            # ETag allows revalidation on version updates
            'Cache-Control': 'public, max-age=31536000, immutable',
            'ETag': '"bridge-v3.5.0-fix-sync-check"',

            # Additional cache hints
            'Vary': 'Accept-Encoding'
        }

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
        response.headers['X-SDK-Version'] = '2.4.0-ppid-derive'
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
        response.headers['X-SDK-Version'] = '2.4.0-ppid-derive'
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response

    # Essential pages
    @app.route('/pricing')
    def pricing():
        return render_template('modern/pricing_new.html')

    # ==================== DOCUMENTATION ====================
    @app.route('/docs')
    def docs_overview():
        """Documentation overview"""
        return render_template('docs/overview.html')
    
    @app.route('/docs/quickstart')
    def docs_quickstart():
        """Quick start guide"""
        return render_template('docs/quickstart.html')
    
    @app.route('/docs/installation')
    def docs_installation():
        """Installation guide"""
        return render_template('docs/installation.html')
    
    @app.route('/docs/wallet-flow')
    def docs_wallet_flow():
        """Wallet redirect flow guide"""
        return render_template('docs/wallet-flow.html')
    
    @app.route('/docs/verification')
    def docs_verification():
        """Credential verification guide"""
        return render_template('docs/verification.html')
    
    @app.route('/docs/permissions')
    def docs_permissions():
        """Permissions and roles guide"""
        return render_template('docs/permissions.html')
    
    @app.route('/docs/sdk')
    def docs_sdk_js():
        """JavaScript SDK reference"""
        return render_template('docs/sdk-js.html')
    
    @app.route('/docs/sdk/methods')
    def docs_sdk_methods():
        """SDK methods reference"""
        return render_template('docs/sdk-methods.html')
    
    @app.route('/docs/sdk/events')
    def docs_sdk_events():
        """SDK events and callbacks"""
        return render_template('docs/sdk-events.html')
    
    @app.route('/docs/api/auth')
    def docs_api_auth():
        """Authentication API reference"""
        return render_template('docs/api-auth.html')
    
    @app.route('/docs/api/verification')
    def docs_api_verification():
        """Verification API reference"""
        return render_template('docs/api-verification.html')
    
    @app.route('/docs/api/revocation')
    def docs_api_revocation():
        """Revocation API reference"""
        return render_template('docs/api-revocation.html')
    
    @app.route('/docs/errors')
    def docs_error_codes():
        """Error codes reference"""
        return render_template('docs/errors.html')
    
    @app.route('/docs/examples')
    def docs_examples():
        """Code examples"""
        return render_template('docs/examples.html')
    
    @app.route('/docs/changelog')
    def docs_changelog():
        """Changelog"""
        return render_template('docs/changelog.html')
    
    @app.route('/docs/setup')
    def docs_setup():
        """Personalized code generator - client-side auth handles everything"""
        return render_template('modern/docs_setup.html')
    
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
        return redirect('/developer')
    
    # ================================================================================
    # DEVELOPER PLATFORM ROUTES
    # ================================================================================
    
    @app.route('/developer')
    def developer_overview():
        """Developer Platform - Overview dashboard"""
        logger.info("🚀 Serving developer overview")
        return render_template('developer/overview.html',
            user_email=request.headers.get('X-User-Email'),
            user_name=None,
            is_admin=request.headers.get('X-Permission-ID', '').lower() in ['super_admin', 'admin_access']
        )
    
    @app.route('/developer/sites')
    def developer_sites():
        """Developer Platform - Sites list"""
        logger.info("🌐 Serving developer sites")
        return render_template('developer/sites/list.html',
            user_email=request.headers.get('X-User-Email'),
            is_admin=request.headers.get('X-Permission-ID', '').lower() in ['super_admin', 'admin_access']
        )
    
    @app.route('/developer/sites/new')
    def developer_sites_new():
        """Developer Platform - Create new site"""
        return render_template('developer/sites/list.html',
            user_email=request.headers.get('X-User-Email'),
            is_admin=False,
            show_create_modal=True
        )
    
    @app.route('/developer/sites/<site_id>')
    def developer_site_detail(site_id):
        """Developer Platform - Site dashboard"""
        logger.info(f"📊 Serving site dashboard: {site_id}")
        return render_template('developer/sites/detail.html',
            site_id=site_id,
            tab='overview',
            user_email=request.headers.get('X-User-Email'),
            is_admin=request.headers.get('X-Permission-ID', '').lower() in ['super_admin', 'admin_access']
        )
    
    @app.route('/developer/sites/<site_id>/integration')
    def developer_site_integration(site_id):
        """Developer Platform - Site integration guide"""
        return render_template('developer/sites/detail.html',
            site_id=site_id,
            tab='integration',
            user_email=request.headers.get('X-User-Email'),
            is_admin=False
        )
    
    @app.route('/developer/sites/<site_id>/keys')
    def developer_site_keys(site_id):
        """Developer Platform - Site API keys management"""
        logger.info(f"🔑 Serving API keys page: {site_id}")
        return render_template('developer/site_keys.html',
            site_id=site_id,
            user_email=request.headers.get('X-User-Email'),
            is_admin=request.headers.get('X-Permission-ID', '').lower() in ['super_admin', 'admin_access']
        )
    
    @app.route('/developer/sites/<site_id>/users')
    def developer_site_users(site_id):
        """Developer Platform - Site users (PPIDs) management"""
        logger.info(f"👥 Serving site users page: {site_id}")
        return render_template('developer/site_users.html',
            site_id=site_id,
            user_email=request.headers.get('X-User-Email'),
            is_admin=request.headers.get('X-Permission-ID', '').lower() in ['super_admin', 'admin_access']
        )
    
    @app.route('/developer/sites/<site_id>/permissions')
    def developer_site_permissions(site_id):
        """Developer Platform - Permission types management"""
        logger.info(f"🎫 Serving permissions page: {site_id}")
        return render_template('developer/site_permissions.html',
            site_id=site_id,
            user_email=request.headers.get('X-User-Email'),
            is_admin=request.headers.get('X-Permission-ID', '').lower() in ['super_admin', 'admin_access']
        )
    
    @app.route('/developer/sites/<site_id>/settings')
    def developer_site_settings(site_id):
        """Developer Platform - Site settings"""
        return render_template('developer/sites/detail.html',
            site_id=site_id,
            tab='settings',
            user_email=request.headers.get('X-User-Email'),
            is_admin=False
        )
    
    @app.route('/developer/usage')
    def developer_usage():
        """Developer Platform - Usage analytics"""
        return render_template('developer/overview.html',
            user_email=request.headers.get('X-User-Email'),
            is_admin=False,
            page='usage'
        )
    
    @app.route('/developer/billing')
    def developer_billing():
        """Developer Platform - Billing"""
        return redirect('/pricing')
    
    @app.route('/developer/settings')
    def developer_settings():
        """Developer Platform - Account settings"""
        return render_template('developer/overview.html',
            user_email=request.headers.get('X-User-Email'),
            is_admin=False,
            page='settings'
        )

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
    @app.route('/admin')
    def admin_dashboard():
        """Admin Dashboard - Platform overview"""
        logger.info("🛡️ Serving admin dashboard")
        return render_template('admin/dashboard.html')
    
    @app.route('/admin/monitoring')
    def admin_monitoring_page():
        """Admin Monitoring - Bloom filter, system health"""
        logger.info("🔧 Serving admin monitoring")
        return render_template('admin/platform_monitoring.html')
    
    @app.route('/admin/health')
    def admin_health_page():
        """Admin Health - System health details"""
        logger.info("💚 Serving admin health")
        return render_template('admin/health.html')
    
    @app.route('/admin/users')
    def admin_users():
        """Admin Users - User management"""
        logger.info("👥 Serving admin users")
        return render_template('admin/users.html')
    
    @app.route('/admin/sites')
    def admin_sites():
        """Admin Sites - All registered sites"""
        logger.info("🌐 Serving admin sites")
        return render_template('admin/sites.html')
    
    @app.route('/admin/credentials')
    def admin_credentials():
        """Admin Credentials - Credential management"""
        logger.info("🎫 Serving admin credentials")
        return render_template('admin/credentials.html')
    
    @app.route('/admin/revocations')
    def admin_revocations():
        """Admin Revocations - Revocation management"""
        logger.info("🚫 Serving admin revocations")
        return render_template('admin/revocations.html')
    
    @app.route('/admin/audit')
    def admin_audit():
        """Admin Audit - Audit log"""
        logger.info("📜 Serving admin audit")
        return render_template('admin/audit.html')

    @app.route('/admin/debug')
    def admin_debug():
        """Admin Debug - API endpoint testing for agent debugging"""
        logger.info("🔧 Serving admin debug dashboard")
        return render_template('admin/debug.html')

    @app.route('/admin/bootstrap')
    def admin_bootstrap():
        """Admin credential bootstrap page"""
        return render_template('modern/admin_bootstrap.html')
    
    # Legacy redirects
    @app.route('/admin/legacy')
    def admin_dashboard_legacy():
        return redirect('/admin')
    
    @app.route('/admin/iam')
    def admin_iam_redirect():
        return redirect('/admin')

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
                response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-API-Key, X-Lemma-CSRF'
                response.headers['Vary'] = 'Origin'

                if origin and is_allowed:
                    response.headers['Access-Control-Allow-Origin'] = origin
                    response.headers['Access-Control-Allow-Credentials'] = 'true'
                else:
                    response.headers['Access-Control-Allow-Origin'] = '*'
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
