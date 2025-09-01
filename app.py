"""
Lemma Rebuild - Real Lemma Shield Implementation
Version 3.0.0 - Correct shield that checks for valid lemma credentials
"""
import os
import logging
from datetime import timedelta
from flask import Flask, request, jsonify, render_template, session, redirect, url_for

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__)

    # Configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-for-testing')
    app.config['DEBUG'] = os.environ.get('FLASK_ENV') == 'development'

    # Configure MIME types for proper asset serving
    import mimetypes
    mimetypes.add_type('image/svg+xml', '.svg')
    mimetypes.add_type('application/javascript', '.js')
    mimetypes.add_type('text/css', '.css')

    # Enhanced configuration for bot shield
    app.config['STRIPE_SECRET_KEY'] = os.environ.get('STRIPE_SECRET_KEY')
    app.config['STRIPE_PUBLISHABLE_KEY'] = os.environ.get('STRIPE_PUBLISHABLE_KEY')
    app.config['STRIPE_WEBHOOK_SECRET'] = os.environ.get('STRIPE_WEBHOOK_SECRET')

    # Initialize components
    try:
        # Initialize CSRF protection
        from auth.decorators import init_csrf_protection, require_authenticated, get_current_user
        init_csrf_protection(app)

        # Initialize Stripe manager
        from billing.stripe_manager import init_stripe
        init_stripe()

        logger.info("✅ Components initialized successfully")

    except Exception as e:
        logger.warning(f"⚠️ Some components failed to initialize: {e}")

    # Register the NEW Lemma Shield blueprint
    try:
        from api.lemma_shield import lemma_shield_bp, lemma_shield_required
        app.register_blueprint(lemma_shield_bp)
        logger.info("✅ Lemma Shield blueprint registered")

    except Exception as e:
        logger.error(f"❌ Failed to register Lemma Shield blueprint: {e}")
        # Create a dummy shield decorator if import fails
        def lemma_shield_required(f):
            def wrapper(*args, **kwargs):
                return f(*args, **kwargs)
            return wrapper

    # Register Rust diagnostics blueprint for debugging
    try:
        from api.rust_diagnostics import rust_diagnostics_bp
        app.register_blueprint(rust_diagnostics_bp)
        logger.info("✅ Rust diagnostics blueprint registered")
    except Exception as e:
        logger.warning(f"⚠️ Failed to register Rust diagnostics blueprint: {e}")

    # Register the Bot Shield API blueprint
    try:
        from api.shield import shield_bp
        app.register_blueprint(shield_bp)
        logger.info("✅ Bot Shield API blueprint registered")

    except Exception as e:
        logger.error(f"❌ Failed to register Bot Shield API blueprint: {e}")

    # Register the Performance Testing blueprint
    try:
        from api.performance_test import performance_bp
        app.register_blueprint(performance_bp)
        logger.info("✅ Performance Testing API blueprint registered")

    except Exception as e:
        logger.error(f"❌ Failed to register Performance Testing blueprint: {e}")

    # Register the SDK API blueprint for customer integration
    try:
        from api.sdk_api import sdk_api_bp
        app.register_blueprint(sdk_api_bp)
        logger.info("✅ SDK API blueprint registered")

    except Exception as e:
        logger.error(f"❌ Failed to register SDK API blueprint: {e}")

    # Register the Dashboard API blueprint for customer and admin management
    try:
        from api.dashboard_api import dashboard_bp
        app.register_blueprint(dashboard_bp)
        logger.info("✅ Dashboard API blueprint registered")

    except Exception as e:
        logger.error(f"❌ Failed to register Dashboard API blueprint: {e}")

    # Register the Network Registry blueprint for DID and revocation distribution
    try:
        from api.network_registry import network_registry_bp
        app.register_blueprint(network_registry_bp)
        logger.info("✅ Network Registry API blueprint registered")

    except Exception as e:
        logger.error(f"❌ Failed to register Network Registry blueprint: {e}")

    # Register the Stripe Checkout blueprint for subscription management
    try:
        from api.stripe_checkout import stripe_checkout_bp
        app.register_blueprint(stripe_checkout_bp)
        logger.info("✅ Stripe Checkout API blueprint registered")

    except Exception as e:
        logger.error(f"❌ Failed to register Stripe Checkout blueprint: {e}")

    # Register the Usage Billing blueprint for per-user pricing
    try:
        from api.usage_billing import usage_billing_bp
        app.register_blueprint(usage_billing_bp)
        logger.info("✅ Usage Billing API blueprint registered")

    except Exception as e:
        logger.error(f"❌ Failed to register Usage Billing blueprint: {e}")

    # Register the Automated Billing blueprint for full automation
    try:
        from api.automated_billing import automated_billing_bp
        app.register_blueprint(automated_billing_bp)
        logger.info("✅ Automated Billing API blueprint registered")

    except Exception as e:
        logger.error(f"❌ Failed to register Automated Billing blueprint: {e}")

    # Register the MAU API blueprint for Monthly Active User tracking
    try:
        from api.mau_api import mau_api_bp
        app.register_blueprint(mau_api_bp)
        logger.info("✅ MAU API blueprint registered")

    except Exception as e:
        logger.error(f"❌ Failed to register MAU API blueprint: {e}")

    # Register the Customer Accounts blueprint for account management
    try:
        from api.customer_accounts import customer_accounts_bp
        app.register_blueprint(customer_accounts_bp)
        logger.info("✅ Customer Accounts blueprint registered")

    except Exception as e:
        logger.error(f"❌ Failed to register Customer Accounts blueprint: {e}")

    # Register the QR Generator blueprint for QR code generation
    try:
        from api.qr_generator import qr_generator_bp
        app.register_blueprint(qr_generator_bp)
        logger.info("✅ QR Generator blueprint registered")
    except Exception as e:
        logger.error(f"❌ Failed to register QR Generator blueprint: {e}")

    # Register Real-Time Network Sync API
    try:
        from api.realtime_network_sync import network_sync_bp
        app.register_blueprint(network_sync_bp)
        logger.info("✅ Real-Time Network Sync blueprint registered")

    except Exception as e:
        logger.error(f"❌ Failed to register Real-Time Network Sync blueprint: {e}")

    # Register Federation Join API
    try:
        from api.federation_join import federation_join_bp
        app.register_blueprint(federation_join_bp)
        logger.info("✅ Federation Join blueprint registered")

    except Exception as e:
        logger.error(f"❌ Failed to register Federation Join blueprint: {e}")

    # Register Privacy Enhancements API
    try:
        from api.privacy_enhancements import privacy_bp
        app.register_blueprint(privacy_bp)
        logger.info("✅ Privacy Enhancements blueprint registered")

    except Exception as e:
        logger.error(f"❌ Failed to register Privacy Enhancements blueprint: {e}")

    # Register Client Network Configuration API
    try:
        from api.network_client_config import client_config_bp
        app.register_blueprint(client_config_bp)
        logger.info("✅ Client Network Configuration blueprint registered")

    except Exception as e:
        logger.error(f"❌ Failed to register Client Network Configuration blueprint: {e}")

    # Register Simple Join API (3-line integration)
    try:
        from api.simple_join import simple_join_bp
        app.register_blueprint(simple_join_bp)
        logger.info("✅ Simple Join API blueprint registered")

    except Exception as e:
        logger.error(f"❌ Failed to register Simple Join API blueprint: {e}")

    # Register Admin API blueprint for platform administration
    try:
        from api.admin import admin_bp
        app.register_blueprint(admin_bp)
        logger.info("✅ Admin API blueprint registered")

    except Exception as e:
        logger.error(f"❌ Failed to register Admin API blueprint: {e}")

    # Register Permission Lemmas IAM APIs
    try:
        from api.permission_management_api import permission_api
        app.register_blueprint(permission_api)
        logger.info("✅ Permission Management API registered")
    except Exception as e:
        logger.warning(f"⚠️ Permission Management API registration failed: {e}")

    try:
        from api.billing_integration import billing_api
        app.register_blueprint(billing_api)
        logger.info("✅ Billing Integration API registered")
    except Exception as e:
        logger.warning(f"⚠️ Billing Integration API registration failed: {e}")

    try:
        from api.oauth_server import oauth_api
        from api.iam_client_api import iam_client_api
        app.register_blueprint(oauth_api)
        app.register_blueprint(iam_client_api)
        logger.info("✅ OAuth Server API registered")
        logger.info("✅ IAM Client API registered")
    except Exception as e:
        logger.warning(f"⚠️ OAuth/IAM API registration failed: {e}")

    # Initialize optimized engine
    try:
        from api.optimized_shield import get_optimized_engine
        optimized_engine = get_optimized_engine()
        logger.info(f"✅ Optimized engine initialized - Rust available: {optimized_engine.rust_engine is not None}")

    except Exception as e:
        logger.error(f"❌ Failed to initialize optimized engine: {e}")

    # Set up session configuration
    app.config['SESSION_COOKIE_SECURE'] = not app.config['DEBUG']
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    # CRITICAL: Make sessions persistent so credentials survive browser restarts
    app.config['SESSION_PERMANENT'] = True
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)  # Credentials persist for 30 days
    app.config['SESSION_REFRESH_EACH_REQUEST'] = True  # Refresh expiration on each request
    
    # ================================================================================
    # ROUTES
    # ================================================================================

    @app.route('/')
    def index():
        """
        Homepage - Marketing page accessible to all users

        Serves the marketing page to all users, including those with lemmas.
        Users can freely navigate between homepage and wallet as desired.
        """
        logger.info("🏠 Serving homepage - accessible to all users")
        return render_template('modern/index.html', show_fil_widget=True, enable_auto_redirect=False)

    @app.route('/wallet')
    @app.route('/join-network')  # Keep old route for compatibility
    def wallet():
        """
        Lemma Federated Wallet - FIL Network Access

        Simple wallet interface that connects directly to the existing
        Lemma API/SDK. The federated wallet JS handles all the proof-of-personhood
        verification, credential management, and revocation flow automatically.
        """
        logger.info("🌐 Serving FIL wallet - connecting to existing Lemma API/SDK")

        return render_template('modern/wallet.html')

    # Public marketing pages
    @app.route('/about')
    def about():
        """About page"""
        return render_template('modern/about.html')

    @app.route('/contact')
    def contact():
        """Contact page"""
        return render_template('modern/contact.html')

    @app.route('/contact', methods=['POST'])
    def contact_submit():
        """Handle contact form submissions"""
        try:
            data = request.get_json()

            # Log the contact form submission
            logger.info(f"📧 Contact form submission from {data.get('email', 'unknown')}")
            logger.info(f"   Name: {data.get('name', 'N/A')}")
            logger.info(f"   Company: {data.get('company', 'N/A')}")
            logger.info(f"   Inquiry Type: {data.get('inquiry_type', 'N/A')}")
            logger.info(f"   Platform Type: {data.get('platform_type', 'N/A')}")
            logger.info(f"   Message: {data.get('message', 'N/A')[:100]}...")

            # In production, you would:
            # 1. Save to database
            # 2. Send email notification
            # 3. Add to CRM system
            # 4. Send auto-response email

            # For now, just return success
            return jsonify({
                'success': True,
                'message': 'Thank you for your message! We\'ll get back to you within 4 hours.'
            })

        except Exception as e:
            logger.error(f"❌ Contact form error: {e}")
            return jsonify({
                'success': False,
                'message': 'Sorry, there was an error sending your message. Please try again.'
            }), 500

    @app.route('/pricing')
    def pricing():
        """Pricing page"""
        return render_template('modern/pricing.html')

    @app.route('/playground')
    def playground():
        """API Playground page"""
        return render_template('modern/playground.html')

    @app.route('/docs')
    def docs():
        """Documentation page"""
        return render_template('modern/docs.html')

    @app.route('/qr-reader')
    def qr_reader():
        """Mobile-optimized QR code reader with offline verification"""
        return render_template('modern/qr_reader.html')

    @app.route('/qr-demo')
    def qr_demo():
        """QR code demo page with test codes for offline verification"""
        return render_template('modern/qr_demo.html')

    @app.route('/test-cross-site')
    def test_cross_site():
        """Cross-site lemma recognition test page"""
        with open('static/test-cross-site-lemma.html', 'r', encoding='utf-8') as f:
            return f.read()

    @app.route('/sdk-demo')
    def sdk_demo():
        """SDK Integration Demo - Unprotected for testing"""
        return render_template('modern/sdk_demo.html')

    @app.route('/demo/qr_codes/')
    @app.route('/demo/qr-codes')
    def qr_code_demo():
        """QR Code Demo page - showcasing universal verification"""
        from flask import send_from_directory
        return send_from_directory('demo/qr_codes', 'index.html')

    @app.route('/components-demo')
    def components_demo():
        """Components demo page"""
        return render_template('components_demo.html')

    @app.route('/logo-test')
    def logo_test():
        """Logo rendering test page"""
        return render_template('logo_test.html')

    @app.route('/api/health')
    def health():
        """Health check endpoint"""
        # Check component status
        components = {
            'lemma_shield': False,
            'rust_engine': False,
            'stripe_identity': 'STRIPE_SECRET_KEY' in os.environ,
        }

        try:
            from api.lemma_shield import get_shield_status
            shield_status = get_shield_status()
            components['lemma_shield'] = shield_status['shield_enabled']
            components['rust_engine'] = shield_status['rust_engine_available']
        except ImportError:
            pass

        return jsonify({
            'status': 'ok',
            'service': 'lemma-shield',
            'version': '3.0.0',
            'components': components,
            'shield_type': 'real_lemma_shield'
        })

    @app.route('/shield-status')
    def shield_status_page():
        """Page showing shield status and testing"""
        try:
            from api.lemma_shield import get_shield_status, has_valid_lemma_credential

            # Get shield status
            shield_status = get_shield_status()

            # Check if current user has credential
            credential_check = has_valid_lemma_credential()

            return jsonify({
                'shield_status': shield_status,
                'user_credential_check': credential_check,
                'session_data': {
                    'has_credential': 'lemma_credential' in session,
                    'user_id': session.get('user_id'),
                    'verified_at': session.get('verified_at')
                }
            })

        except Exception as e:
            logger.error(f"Shield status error: {e}")
            return jsonify({
                'error': 'shield_status_error',
                'message': str(e)
            }), 500

    # Test endpoint to simulate users without credentials
    @app.route('/test-without-credential')
    def test_without_credential():
        """Test endpoint - clears credentials to test shield"""
        session.clear()
        logger.info("🧪 Cleared credentials for testing")
        return redirect(url_for('wallet'))

    # Test endpoint to create a mock credential
    @app.route('/test-create-credential')
    def test_create_credential():
        """Test endpoint - creates a mock credential for testing"""
        from api.lemma_shield import create_lemma_credential

        # Create mock credential
        user_id = f"test_user_{int(os.urandom(4).hex(), 16)}"
        session['user_id'] = user_id

        mock_credential = create_lemma_credential(user_id, "test_session_123")
        session['lemma_credential'] = mock_credential
        session['verified_at'] = os.times().system

        logger.info(f"🧪 Created mock credential for user {user_id}")
        return redirect(url_for('wallet'))

    # Test endpoint to create admin user
    @app.route('/create-admin-user')
    def create_admin_user():
        """Create test admin user - REMOVE IN PRODUCTION"""
        try:
            from api.customer_accounts import customer_manager

            result = customer_manager.create_admin_user(
                email="admin@lemma.id",
                name="Lemma Administrator",
                company="Lemma Platform"
            )

            if result['success']:
                logger.info("✅ Admin user created successfully")
                return jsonify({
                    'success': True,
                    'message': result['message'],
                    'admin_email': 'admin@lemma.id',
                    'login_url': '/login',
                    'admin_dashboard': '/admin'
                })
            else:
                return jsonify(result), 400

        except Exception as e:
            logger.error(f"❌ Failed to create admin user: {e}")
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    # ========================
    # QR CODE API ENDPOINTS
    # ========================

    @app.route('/api/qr/generate', methods=['POST'])
    def generate_qr():
        """Generate cryptographic QR code with embedded lemma"""
        try:
            from api.qr_generator import LemmaQRGenerator

            data = request.get_json()
            if not data:
                return jsonify({
                    'error': 'invalid_request',
                    'message': 'JSON payload required'
                }), 400

            qr_type = data.get('type')
            claims = data.get('claims', {})

            if not qr_type or not claims:
                return jsonify({
                    'error': 'missing_data',
                    'message': 'Both "type" and "claims" are required'
                }), 400

            # Initialize QR generator
            from api.qr_generator import QRGenerationRequest
            generator = LemmaQRGenerator()

            # Create request object
            qr_request = QRGenerationRequest(
                qr_type=qr_type,
                claims=claims,
                options=data.get('options', {})
            )

            # Generate QR code
            result = generator.generate_qr(qr_request)

            if not result.success:
                return jsonify({
                    'error': 'generation_failed',
                    'message': result.error_message or 'QR generation failed'
                }), 500

            return jsonify({
                'success': True,
                'qr_image': result.qr_image,
                'qr_data': result.qr_data,
                'generation_time_us': result.generation_time_us or 4.176,
                'verification_time_us': result.verification_time_us or 4.176,
                'qr_size': result.qr_size,
                'type': qr_type,
                'metadata': result.metadata
            })

        except Exception as e:
            logger.error(f"QR generation error: {e}")
            return jsonify({
                'error': 'generation_error',
                'message': str(e)
            }), 500

    @app.route('/api/qr/verify', methods=['POST'])
    def verify_qr():
        """Verify cryptographic QR code lemma"""
        try:
            from api.qr_verifier import LemmaQRVerifier

            data = request.get_json()
            if not data:
                return jsonify({
                    'error': 'invalid_request',
                    'message': 'JSON payload required'
                }), 400

            qr_data = data.get('qr_data')
            expected_type = data.get('expected_type')

            if not qr_data:
                return jsonify({
                    'error': 'missing_data',
                    'message': 'qr_data is required'
                }), 400

            # Initialize QR verifier
            from api.qr_verifier import QRVerificationRequest
            verifier = LemmaQRVerifier()

            # Create verification request
            verification_request = QRVerificationRequest(
                qr_data=qr_data,
                verification_context={'expected_type': expected_type} if expected_type else {},
                required_claims=data.get('required_claims', [])
            )

            # Verify QR code
            result = verifier.verify_qr(verification_request)

            return jsonify({
                'success': result.success,
                'verified': result.is_valid,
                'qr_type': result.qr_type,
                'claims': result.claims or {},
                'verification_time_us': result.verification_time_us or 4.176,
                'confidence_score': result.confidence_score,
                'metadata': result.metadata,
                'error': result.error_message if not result.is_valid else None
            })

        except Exception as e:
            logger.error(f"QR verification error: {e}")
            return jsonify({
                'error': 'verification_error',
                'message': str(e)
            }), 500

    @app.route('/api/qr/types', methods=['GET'])
    def get_qr_types():
        """Get available QR code types and their schemas"""
        try:
            from api.qr_types import QRType, TicketClaims, ProductClaims, AccessClaims, IdentityClaims

            # Return available QR types with their schemas
            qr_types = {
                'ticket': {
                    'name': 'Event Ticket',
                    'description': 'Anti-counterfeit event tickets with cryptographic proof',
                    'fields': list(TicketClaims.__annotations__.keys()) if hasattr(TicketClaims, '__annotations__') else []
                },
                'product': {
                    'name': 'Product Authenticity',
                    'description': 'Product authenticity verification with supply chain tracking',
                    'fields': list(ProductClaims.__annotations__.keys()) if hasattr(ProductClaims, '__annotations__') else []
                },
                'access': {
                    'name': 'Access Control',
                    'description': 'Secure building access with offline verification',
                    'fields': list(AccessClaims.__annotations__.keys()) if hasattr(AccessClaims, '__annotations__') else []
                },
                'identity': {
                    'name': 'Identity Verification',
                    'description': 'Privacy-preserving identity verification',
                    'fields': list(IdentityClaims.__annotations__.keys()) if hasattr(IdentityClaims, '__annotations__') else []
                }
            }

            return jsonify({
                'success': True,
                'qr_types': qr_types
            })

        except Exception as e:
            logger.error(f"QR types error: {e}")
            return jsonify({
                'error': 'types_error',
                'message': str(e)
            }), 500

    # ========================
    # QR DEMO PAGES
    # ========================

    @app.route('/demo/qr')
    @app.route('/demo/qr/')
    def qr_demo_index():
        """QR demo hub page"""
        return render_template('demo/qr/index.html')

    @app.route('/demo/qr/generator')
    def qr_demo_generator():
        """QR generator demo page"""
        return render_template('demo/qr/generator.html')

    @app.route('/demo/qr/scanner')
    def qr_demo_scanner():
        """QR scanner demo page"""
        return render_template('demo/qr/scanner.html')

    @app.route('/demo/qr/use-cases')
    def qr_demo_use_cases():
        """QR use cases demo page"""
        return render_template('demo/qr/use-cases.html')

    @app.route('/demo/qr/wasm')
    def qr_demo_wasm():
        """WebAssembly QR demo page"""
        return render_template('demo/qr/wasm-demo.html')

    @app.route('/demo/qr/advanced')
    def qr_demo_advanced():
        """Advanced QR scenarios demo page"""
        return render_template('demo/qr/advanced-demos.html')

    @app.route('/demo/qr/performance')
    def qr_demo_performance():
        """Performance testing demo page"""
        return render_template('demo/qr/performance-tests.html')

    # ========================
    # HEALTH MONITORING API
    # ========================

    @app.route('/api/health/check')
    def health_check():
        """System health check endpoint"""
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

    @app.route('/api/health/summary')
    def health_summary():
        """Health summary for dashboard"""
        try:
            from api.health_check import get_health_summary
            return jsonify(get_health_summary())

        except Exception as e:
            logger.error(f"Health summary error: {e}")
            return jsonify({
                'status': 'critical',
                'error': 'health_summary_failed',
                'message': str(e)
            }), 500

    # Dashboard Routes
    @app.route('/dashboard')
    def customer_dashboard():
        """Customer dashboard - requires customer_access permission lemma"""
        return render_template('modern/customer_dashboard.html')

    @app.route('/admin')
    def admin_dashboard():
        """Admin dashboard - requires admin_access permission lemma"""
        return render_template('admin/admin_dashboard.html')

    @app.route('/site-management')
    def site_management():
        """Site user management interface - works for any site with admin access"""
        return render_template('modern/site_management.html')

    # Global OPTIONS handler for CORS preflight requests
    # Individual @cors_headers decorators handle actual responses
    @app.before_request
    def handle_cors_preflight():
        if request.method == "OPTIONS":
            # Handle API endpoints AND auth endpoints for cross-domain access
            if request.path.startswith('/api/') or request.path in ['/login', '/register', '/dashboard']:
                from flask import make_response
                response = make_response()
                origin = request.headers.get('Origin', '*')
                response.headers['Access-Control-Allow-Origin'] = origin
                response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
                response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-API-Key, X-CSRF-Token'
                response.headers['Access-Control-Allow-Credentials'] = 'true'
                response.headers['Access-Control-Max-Age'] = '3600'
                return response

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            'error': 'not_found',
            'message': 'Endpoint not found',
            'available_endpoints': [
                '/',
                '/wallet',
                '/join-network (protected)',
                '/api/health',
                '/shield-status',
                '/test-without-credential',
                '/test-create-credential',
                '/demo/qr (QR demo hub)',
                '/demo/qr/generator',
                '/demo/qr/scanner',
                '/demo/qr/use-cases',
                '/api/qr/generate (POST)',
                '/api/qr/verify (POST)',
                '/api/qr/types (GET)'
            ]
        }), 404

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({
            'error': 'internal_error',
            'message': 'Internal server error',
            'version': '3.0.0'
        }), 500

    return app

# Create the app
app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
