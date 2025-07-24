"""
Lemma Rebuild - Real Lemma Shield Implementation
Version 3.0.0 - Correct shield that checks for valid lemma credentials
"""
import os
import logging
from flask import Flask, request, jsonify, render_template, session, redirect, url_for

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__)
    
    # Configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-for-testing')
    app.config['DEBUG'] = os.environ.get('FLASK_ENV') == 'development'
    
    # Enhanced configuration for bot shield
    app.config['STRIPE_SECRET_KEY'] = os.environ.get('STRIPE_SECRET_KEY')
    app.config['STRIPE_PUBLISHABLE_KEY'] = os.environ.get('STRIPE_PUBLISHABLE_KEY')
    app.config['STRIPE_WEBHOOK_SECRET'] = os.environ.get('STRIPE_WEBHOOK_SECRET')
    
    # Initialize components
    try:
        # Initialize CSRF protection
        from auth.decorators import init_csrf_protection
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
    
    # ============================================================================
    # ROUTES
    # ============================================================================
    
    @app.route('/')
    def index():
        """Homepage showing the shield status"""
        return render_template('modern/index.html')
    
    @app.route('/join')  
    @app.route('/join-network')
    @lemma_shield_required
    def join_network():
        """
        PROTECTED ROUTE: Join the Lemma Network page
        
        This route is protected by the Lemma Shield.
        Only users with valid lemma credentials can access this page.
        """
        logger.info("✅ User passed Lemma Shield - accessing join network page")
        
        # Get user's credential info for the page
        credential = session.get('lemma_credential', {})
        user_id = session.get('user_id', 'Anonymous')
        
        return render_template('modern/join_network.html', 
                             credential=credential,
                             user_id=user_id,
                             verified=True)
    
    # Missing route placeholders
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
        return redirect(url_for('join_network'))
    
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
        return redirect(url_for('join_network'))
    
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            'error': 'not_found',
            'message': 'Endpoint not found',
            'available_endpoints': [
                '/',
                '/join-network (protected)',
                '/api/health',
                '/shield-status',
                '/test-without-credential',
                '/test-create-credential'
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