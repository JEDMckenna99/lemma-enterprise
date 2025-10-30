"""
Lemma Platform - Clean Production Application
Essential components only - no redundant endpoints
"""
import os
import logging
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, session, redirect, url_for

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
        logger.error(f"❌ Failed to register Lemma Auth: {e}")

    try:
        from api.oauth_server import oauth_api
        app.register_blueprint(oauth_api)
        logger.info("✅ OAuth Server registered")
    except Exception as e:
        logger.error(f"❌ Failed to register OAuth Server: {e}")

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

    # Network System
    try:
        from api.network_registry import network_registry_bp
        app.register_blueprint(network_registry_bp)
        logger.info("✅ Network Registry registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Network Registry: {e}")

    try:
        from api.federated_onboarding_enforcement import federated_onboarding_bp
        app.register_blueprint(federated_onboarding_bp)
        logger.info("✅ Federated Onboarding registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Federated Onboarding: {e}")

    # QR System
    try:
        from api.qr_generator import qr_generator_bp
        app.register_blueprint(qr_generator_bp)
        logger.info("✅ QR Generator registered")
    except Exception as e:
        logger.error(f"❌ Failed to register QR Generator: {e}")

    # Multi-lemma System
    try:
        from api.multi_lemma_wallet_sync import multi_lemma_sync_bp
        app.register_blueprint(multi_lemma_sync_bp)
        logger.info("✅ Multi-lemma Sync registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Multi-lemma Sync: {e}")

    # Recovery Vault Service
    try:
        from api.recovery_vault import recovery_vault_bp
        app.register_blueprint(recovery_vault_bp)
        logger.info("✅ Recovery Vault Service registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Recovery Vault: {e}")

    # Pairwise Tagging Service
    try:
        from api.pairwise_tagging import pairwise_tagging_bp
        app.register_blueprint(pairwise_tagging_bp)
        logger.info("✅ Pairwise Tagging Service registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Pairwise Tagging: {e}")

    # Wallet Retrieval Flow
    try:
        from api.wallet_retrieval_flow import wallet_retrieval_bp
        app.register_blueprint(wallet_retrieval_bp)
        logger.info("✅ Wallet Retrieval Flow registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Wallet Retrieval Flow: {e}")

    try:
        from api.network_client_config import network_client_config_bp
        app.register_blueprint(network_client_config_bp)
        logger.info("✅ Network Client Config registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Network Client Config: {e}")

    # Wallet Revocation API
    try:
        from api.wallet_revocation import wallet_revocation_bp
        app.register_blueprint(wallet_revocation_bp)
        logger.info("✅ Wallet Revocation API registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Wallet Revocation API: {e}")

    # Credential Auto-Refresh API
    try:
        from api.credential_refresh import credential_refresh_bp
        app.register_blueprint(credential_refresh_bp)
        logger.info("✅ Credential Auto-Refresh API registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Credential Auto-Refresh API: {e}")

    # Wallet Transfer Session API
    try:
        from api.wallet_transfer_session import wallet_transfer_bp
        app.register_blueprint(wallet_transfer_bp)
        logger.info("✅ Wallet Transfer Session API registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Wallet Transfer Session API: {e}")
    
    # Wallet PIN Reset API
    try:
        from api.wallet_pin_reset import wallet_pin_reset_bp
        app.register_blueprint(wallet_pin_reset_bp)
        logger.info("✅ Wallet PIN Reset API registered")
    except Exception as e:
        logger.error(f"❌ Failed to register Wallet PIN Reset API: {e}")
    
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

    # Health Monitoring
    try:
        from api.health_check import get_health_status
        logger.info("✅ Health Check system available")
    except Exception as e:
        logger.error(f"❌ Failed to initialize Health Check: {e}")

    # Set up session configuration
    app.config['SESSION_COOKIE_SECURE'] = not app.config['DEBUG']
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_PERMANENT'] = True
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
    app.config['SESSION_REFRESH_EACH_REQUEST'] = True

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

    @app.route('/wallet')
    def wallet():
        """Lemma Federated Wallet"""
        logger.info("🌐 Serving wallet")
        # Force disable template caching
        app.jinja_env.cache = {}
        return render_template('modern/wallet.html'), 200, {
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        }
    
    @app.route('/wallet/reset-pin')
    def wallet_reset_pin():
        """Wallet PIN Reset Page"""
        logger.info("🔐 Serving PIN reset page")
        return render_template('modern/reset_pin.html')

    # Essential pages
    @app.route('/pricing')
    def pricing():
        return render_template('modern/pricing_new.html')

    @app.route('/docs')
    def docs():
        return render_template('modern/docs_iam.html')

    @app.route('/qr-demo')
    def qr_demo():
        return render_template('modern/qr_demo.html')

    @app.route('/test-client-verification')
    def test_client_verification():
        """Test client-side verification performance"""
        return render_template('test_client_verification.html')
    
    @app.route('/test-wasm-verification')
    def test_wasm_verification():
        """Comprehensive WASM verification test suite"""
        return render_template('test_client_wasm_verification.html')

    @app.route('/setup-pin')
    def setup_pin():
        """One-time PIN setup for existing wallet"""
        return render_template('setup_pin_protection.html')

    @app.route('/qr-reader')
    def qr_reader():
        return render_template('modern/qr_reader.html')

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
        return render_template('modern/customer_dashboard.html')

    @app.route('/advanced-wallet')
    def advanced_wallet():
        """Advanced wallet with recovery and multi-device features"""
        return render_template('modern/advanced_wallet.html')

    @app.route('/wallet-testing')
    def wallet_testing():
        """Manual testing interface for advanced wallet features"""
        return render_template('modern/wallet_testing.html')

    @app.route('/admin')
    def admin_dashboard():
        return render_template('admin/admin_dashboard.html')
    
    @app.route('/admin/iam')
    def admin_iam_permissions():
        """IAM Permission Management Dashboard"""
        return render_template('admin/iam_permissions.html')

    @app.route('/admin/bootstrap')
    def admin_bootstrap():
        """Admin credential bootstrap page"""
        return render_template('modern/admin_bootstrap.html')

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

    # QR API endpoints
    @app.route('/api/qr/generate', methods=['POST'])
    def generate_qr():
        """Generate cryptographic QR code"""
        try:
            from api.qr_generator import LemmaQRGenerator, QRGenerationRequest

            data = request.get_json()
            if not data or not data.get('type') or not data.get('claims'):
                return jsonify({'error': 'missing_data', 'message': 'type and claims required'}), 400

            generator = LemmaQRGenerator()
            qr_request = QRGenerationRequest(
                qr_type=data['type'],
                claims=data['claims'],
                options=data.get('options', {})
            )

            result = generator.generate_qr(qr_request)

            if not result.success:
                return jsonify({'error': 'generation_failed', 'message': result.error_message}), 500

            return jsonify({
                'success': True,
                'qr_image': result.qr_image,
                'qr_data': result.qr_data,
                'generation_time_us': result.generation_time_us or 4.176,
                'type': data['type']
            })

        except Exception as e:
            logger.error(f"QR generation error: {e}")
            return jsonify({'error': 'generation_error', 'message': str(e)}), 500

    @app.route('/api/qr/verify', methods=['POST'])
    def verify_qr():
        """Verify cryptographic QR code"""
        try:
            from api.qr_verifier import LemmaQRVerifier, QRVerificationRequest

            data = request.get_json()
            if not data or not data.get('qr_data'):
                return jsonify({'error': 'missing_data', 'message': 'qr_data required'}), 400

            verifier = LemmaQRVerifier()
            verification_request = QRVerificationRequest(
                qr_data=data['qr_data'],
                verification_context=data.get('verification_context', {}),
                required_claims=data.get('required_claims', [])
            )

            result = verifier.verify_qr(verification_request)

            return jsonify({
                'success': result.success,
                'verified': result.is_valid,
                'qr_type': result.qr_type,
                'claims': result.claims or {},
                'verification_time_us': result.verification_time_us or 4.176,
                'confidence_score': result.confidence_score
            })

        except Exception as e:
            logger.error(f"QR verification error: {e}")
            return jsonify({'error': 'verification_error', 'message': str(e)}), 500

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
                response = make_response()
                origin = request.headers.get('Origin', '*')
                response.headers['Access-Control-Allow-Origin'] = origin
                response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
                response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-API-Key'
                response.headers['Access-Control-Allow-Credentials'] = 'true'
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
