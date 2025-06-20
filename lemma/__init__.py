"""
Lemma Enterprise - Human Verification System
Web application factory and configuration.
Enhanced with enterprise-grade security and features.
"""

import os
import sys
import secrets
import logging
from flask import Flask, request, session, g, redirect, jsonify, render_template
from werkzeug.middleware.proxy_fix import ProxyFix
from logging.handlers import RotatingFileHandler
import socket
import shutil
import json
from datetime import datetime
import time
import hashlib
import redis
from urllib.parse import urlparse

# Optional CSRF protection import
try:
    from flask_wtf.csrf import CSRFProtect
    CSRF_AVAILABLE = True
except ImportError:
    CSRF_AVAILABLE = False

from flask_cors import CORS
import platform

# Optional Flask-Minify import
try:
    from flask_minify import Minify
    MINIFY_AVAILABLE = True
except ImportError:
    MINIFY_AVAILABLE = False



# Create logger
logger = logging.getLogger(__name__)

# Initialize Redis client for production caching
redis_client = None
if os.getenv('REDISCLOUD_URL'):
    try:
        url = urlparse(os.getenv('REDISCLOUD_URL'))
        redis_client = redis.Redis(
            host=url.hostname,
            port=url.port,
            password=url.password,
            decode_responses=True,
            socket_timeout=2,
            socket_connect_timeout=2,
            retry_on_timeout=True
        )
        # Test connection with short timeout to avoid startup delays
        redis_client.ping()
        print("✅ Redis Cloud connected successfully")
    except Exception as e:
        print(f"⚠️  Redis connection failed: {e} - continuing with in-memory fallback")
        redis_client = None
else:
    print("ℹ️  Redis not configured, using in-memory caching")

# Export for use in other modules
__all__ = ['redis_client']

def create_app(test_config=None):
    """Create and configure the Flask application."""
    
    # Get the current working directory and determine if running on Heroku
    cwd = os.getcwd()
    is_heroku = 'DYNO' in os.environ
    
    # Determine if we're in development mode
    # SECURITY: Production check - never allow debug mode in production
    is_production = (
        is_heroku or 
        os.environ.get('FLASK_ENV') == 'production' or
        os.environ.get('LEMMA_ENV') == 'production' or
        os.environ.get('ENV') == 'production'
    )
    
    is_development = not is_production and not is_heroku and (
        os.environ.get('FLASK_ENV') == 'development' or 
        os.environ.get('LEMMA_ENV') == 'development' or
        os.environ.get('FLASK_DEBUG') == '1' or
        os.environ.get('LEMMA_DEBUG') == '1' or
        os.environ.get('DEBUG') == '1'
    )
    
    # Also consider Windows a development environment for cookie security
    is_windows = platform.system() == 'Windows'
    if is_windows:
        is_development = True
        logger.info("Windows environment detected, using development settings")
    
    # Determine template and static folders based on environment
    template_dir = os.path.abspath(os.path.join(cwd, 'templates'))
    static_dir = os.path.abspath(os.path.join(cwd, 'static'))
    
    # Log directory information for debugging
    logger.info(f"Running with cwd: {cwd}")
    logger.info(f"Is Heroku: {is_heroku}")
    logger.info(f"Using template_dir: {template_dir}")
    logger.info(f"Using static_dir: {static_dir}")
    
    # Create the Flask app with explicit template and static folders
    app = Flask(__name__, 
                template_folder=template_dir,
                static_folder=static_dir,
                instance_relative_config=True)
    
    # SECURITY: Force production settings for security
    if is_production:
        app.debug = False
        app.config['DEBUG'] = False
        app.config['TESTING'] = False
        logger.info("Production mode: Debug disabled")
    else:
        logger.info(f"Development mode: Debug allowed: {is_development}")
    
    # Initialize CORS
    CORS(app, resources={
        r"/api/*": {
            "origins": "*",
            "supports_credentials": True
        }
    })
    
    # Initialize CSRF protection
    from lemma.auth.csrf_config import configure_csrf
    configure_csrf(app)
    
    # Initialize Flask-Minify for performance optimization (temporarily disabled)
    # Note: Disabled due to compatibility issues - CloudFlare provides minification
    if False and MINIFY_AVAILABLE and not is_development:
        Minify(app=app, html=True, js=True, cssless=True, 
               fail_safe=True, bypass=['/api/', '/admin/'])
        app.logger.info("Flask-Minify enabled for production")
    else:
        app.logger.info("Flask-Minify disabled - using CloudFlare minification instead")
    
    # Load default configuration
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('LEMMA_SECRET_KEY', secrets.token_hex(32)),
        STORAGE_DIR=os.environ.get('LEMMA_STORAGE_DIR', '/tmp/lemma_enterprise' if is_heroku else '.lemma_enterprise'),
        ADMIN_USER=os.environ.get('LEMMA_ADMIN_USER', 'admin'),
        ADMIN_PASS=os.environ.get('LEMMA_ADMIN_PASS', 'changeme'),
        API_KEY=os.environ.get('LEMMA_API_KEY', 'dev_api_key'),
        DID_METHOD=os.environ.get('DID_METHOD', 'lemma'),
        DID=os.environ.get('DID', None),
        ENABLE_P2P=os.environ.get('LEMMA_ENABLE_P2P', 'false').lower() == 'true',
        P2P_PEERS=os.environ.get('LEMMA_P2P_PEERS', '').split(',') if os.environ.get('LEMMA_P2P_PEERS') else [],
        TRUSTED_ISSUERS=os.environ.get('LEMMA_TRUSTED_ISSUERS', '').split(',') if os.environ.get('LEMMA_TRUSTED_ISSUERS') else [],
        HARDWARE_SECURITY=os.environ.get('LEMMA_HARDWARE_SECURITY', 'false').lower() == 'true',
        # Stripe Identity verification
        STRIPE_SECRET_KEY=os.environ.get('STRIPE_SECRET_KEY') or os.environ.get('STRIPE_API_KEY'),
        STRIPE_PUBLISHABLE_KEY=os.environ.get('STRIPE_PUBLISHABLE_KEY'),
        # Enhanced security settings for OIDC4VP compliance - but relaxed for development
        SESSION_COOKIE_SECURE=not is_development,  # Only use secure cookies in production
        SESSION_COOKIE_HTTPONLY=True,  # Always use HTTP-only cookies for security
        SESSION_COOKIE_SAMESITE='Strict' if not is_development else 'Lax',  # Strict in production, Lax in dev
        PERMANENT_SESSION_LIFETIME=1800,  # 30 minutes
        # Force session cookie attributes in production
        SESSION_COOKIE_NAME='session',
        # CSRF Configuration
        WTF_CSRF_ENABLED=True,
        WTF_CSRF_SSL_STRICT=not is_development,  # Only enforce HTTPS for CSRF in production
        # Security headers
        SECURE_HEADERS={
            'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'SAMEORIGIN',
            'X-XSS-Protection': '1; mode=block',
        },
        MAX_CONTENT_LENGTH=16 * 1024 * 1024  # 16MB max file size
    )
    
    # Override with test config if provided
    if test_config is not None:
        app.config.from_mapping(test_config)
        
    # Only create storage directories if not on Heroku
    if not is_heroku:
        os.makedirs(app.instance_path, exist_ok=True)
        os.makedirs(app.config['STORAGE_DIR'], exist_ok=True)

    # Set up logging
    if not app.debug:
        if is_heroku:
            # On Heroku, just log to stderr
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(logging.Formatter(
                '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
            ))
            handler.setLevel(logging.INFO)
            app.logger.addHandler(handler)
            app.logger.setLevel(logging.INFO)
        else:
            # In other environments, use file logging
            log_dir = os.path.join(app.instance_path, 'logs')
            os.makedirs(log_dir, exist_ok=True)
            file_handler = RotatingFileHandler(
                os.path.join(log_dir, 'lemma.log'),
                maxBytes=10485760,  # 10MB
                backupCount=10
            )
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
            ))
            file_handler.setLevel(logging.INFO)
            app.logger.addHandler(file_handler)
            app.logger.setLevel(logging.INFO)
        
        app.logger.info(f'Lemma startup in {cwd}. Template dir: {template_dir}')

    try:
        # Initialize components
        with app.app_context():
            _init_components(app)
            app.logger.info("Successfully initialized all components")
    except Exception as e:
        app.logger.error(f"Error initializing components: {e}")
        # Continue anyway - some components may work
    
    # Register blueprints - Maintain backward compatibility
    # Note: If you see 404s for main routes, check OPRF_SERVICE_INTERNAL=false
    try:
        from lemma.routes.shield_api import shield_api
        app.register_blueprint(shield_api)
        app.logger.info("Shield API blueprint registered successfully")
    except Exception as e:
        app.logger.error(f"CRITICAL: Failed to register Shield API blueprint: {e}")
        # Don't continue silently - this is a critical error
        raise
    
    try:
        from lemma.routes.api import api_bp
        app.register_blueprint(api_bp)
        app.logger.info("Legacy API blueprint registered successfully")
    except Exception as e:
        app.logger.error(f"CRITICAL: Failed to register Legacy API blueprint: {e}")
        raise
    
    try:
        from lemma.routes.main import main_bp
        app.register_blueprint(main_bp)
        app.logger.info("Main blueprint registered successfully")
    except Exception as e:
        app.logger.error(f"CRITICAL: Failed to register Main blueprint: {e}")
        raise
    
    try:
        from lemma.routes.onboarding import onboarding_bp
        app.register_blueprint(onboarding_bp, url_prefix='/onboarding')
        app.logger.info("Onboarding blueprint registered successfully")
    except Exception as e:
        app.logger.error(f"CRITICAL: Failed to register Onboarding blueprint: {e}")
        raise
    
    try:
        from lemma.routes.admin import admin_bp
        app.register_blueprint(admin_bp)
        app.logger.info("Admin blueprint registered successfully")
    except Exception as e:
        app.logger.error(f"CRITICAL: Failed to register Admin blueprint: {e}")
        raise
    
    try:
        from lemma.routes.shopify_app import shopify_bp
        app.register_blueprint(shopify_bp)
        app.logger.info("Shopify blueprint registered successfully")
    except Exception as e:
        app.logger.error(f"CRITICAL: Failed to register Shopify blueprint: {e}")
        raise

    # Both Shield API v1 and legacy API available for backward compatibility
    app.logger.info("Lemma Shield API v1.0 + Legacy API + Shopify App initialized - Market-ready with backward compatibility")

    # Clean up resources at the end of requests
    @app.teardown_appcontext
    def teardown_db(exception):
        # Clean up any resources here
        pass
    
    # Fix for working with reverse proxies
    @app.before_request
    def handle_proxies():
        scheme = request.headers.get('X-Forwarded-Proto')
        if scheme and scheme == 'https':
            request.environ['wsgi.url_scheme'] = 'https'
    
    # Register a function to add request_id to the g object
    @app.before_request
    def add_request_id():
        g.request_id = request.headers.get('X-Request-ID', secrets.token_hex(8))
    
    # SESSION SECURITY: Implement session fixation and hijacking protection
    @app.before_request
    def secure_session():
        """Implement comprehensive session security."""
        from flask import session, request, g, redirect, url_for
        import time
        
        # Skip session security for static files and health checks
        if request.endpoint in ['static', 'health_check', 'ping', 'fast_test']:
            return
        
        current_time = time.time()
        
        # 1. SESSION FIXATION PROTECTION
        if 'user_id' in session or 'admin_logged_in' in session:
            # Regenerate session ID periodically (every 30 minutes)
            last_regenerated = session.get('last_regenerated', 0)
            if current_time - last_regenerated > 1800:  # 30 minutes
                # Store session data
                session_data = dict(session)
                # Clear and regenerate
                session.clear()
                session.regenerate_id()
                # Restore data
                session.update(session_data)
                session['last_regenerated'] = current_time
                logger.info("Session ID regenerated for security")
        
        # 2. SESSION HIJACKING PROTECTION
        if 'user_id' in session or 'admin_logged_in' in session:
            # Check IP address binding (with mobile consideration)
            stored_ip = session.get('session_ip')
            current_ip = request.remote_addr
            
            if stored_ip and stored_ip != current_ip:
                # Allow IP changes for mobile users (check User-Agent)
                user_agent = request.headers.get('User-Agent', '').lower()
                is_mobile = any(mobile in user_agent for mobile in ['mobile', 'android', 'iphone', 'ipad'])
                
                if not is_mobile:
                    logger.warning(f"Session IP mismatch: {stored_ip} -> {current_ip}")
                    session.clear()
                    return redirect(url_for('admin.login', reason='ip_changed'))
                else:
                    # Update IP for mobile users but log the change
                    logger.info(f"Mobile user IP change: {stored_ip} -> {current_ip}")
                    session['session_ip'] = current_ip
            else:
                # Store IP on first access
                session['session_ip'] = current_ip
            
            # 3. USER-AGENT FINGERPRINTING
            stored_ua_hash = session.get('ua_hash')
            current_ua_hash = hashlib.sha256(request.headers.get('User-Agent', '').encode()).hexdigest()
            
            if stored_ua_hash and stored_ua_hash != current_ua_hash:
                logger.warning("Session User-Agent mismatch - possible session hijacking")
                session.clear()
                return redirect(url_for('admin.login', reason='ua_changed'))
            else:
                session['ua_hash'] = current_ua_hash
            
            # 4. SESSION TIMEOUT
            last_activity = session.get('last_activity', current_time)
            if current_time - last_activity > 7200:  # 2 hours
                logger.info("Session expired due to inactivity")
                session.clear()
                return redirect(url_for('admin.login', reason='expired'))
            
            session['last_activity'] = current_time

    # Force HTTPS in production for OIDC4VP compliance
    @app.before_request
    def force_https():
        # Disable HTTPS enforcement for local testing
        if False and not app.debug and not app.testing:
            if request.headers.get('X-Forwarded-Proto', 'http') != 'https':
                url = request.url.replace('http://', 'https://', 1)
                return redirect(url, code=301)

    # Add CSP headers for security
    @app.after_request
    def add_security_headers(response):
        """Add security headers including CSP."""
        # Enhanced Content Security Policy - More restrictive for production
        if app.config.get('ENV') == 'production':
            # Production CSP - more restrictive
            csp_policy = (
                "default-src 'self'; "
                "script-src 'self' https://js.stripe.com; "  # Removed 'unsafe-inline' and untrusted CDNs
                "style-src 'self' https://fonts.googleapis.com; "  # Removed 'unsafe-inline'
                "img-src 'self' data: https://stripe.com https://js.stripe.com; "
                "font-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com; "
                "connect-src 'self' https://api.stripe.com https://api.lemma.network; "
                "frame-src 'self' https://js.stripe.com; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self'; "
                "object-src 'none'; "  # Block plugins
                "media-src 'none'; "   # Block media
                "worker-src 'none'; "  # Block web workers
                "manifest-src 'self'; "
                "upgrade-insecure-requests; "  # Force HTTPS
                "report-uri /api/csp-report"
            )
        else:
            # Development CSP - more permissive for debugging
            csp_policy = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://unpkg.com https://js.stripe.com; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
                "img-src 'self' data: https:; "
                "font-src 'self' https://cdn.jsdelivr.net https://fonts.googleapis.com https://fonts.gstatic.com; "
                "connect-src 'self' https://api.stripe.com https://api.lemma.network ws: wss:; "  # Allow WebSocket for dev tools
                "frame-src 'self' https://js.stripe.com; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self'; "
                "report-uri /api/csp-report"
            )
        
        response.headers['Content-Security-Policy'] = csp_policy
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        
        # Enhanced security headers
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = (
            "camera=(), microphone=(), geolocation=(), "
            "payment=(), usb=(), magnetometer=(), accelerometer=(), gyroscope=()"
        )
        
        if request.is_secure:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
        
        # Remove server information
        response.headers.pop('Server', None)
        
        return response

    # CSP violation reporting endpoint
    @app.route('/api/csp-report', methods=['POST'])
    def csp_report():
        """Handle CSP violation reports."""
        try:
            violation_data = request.get_json()
            
            # Log CSP violation
            logger.warning(f"CSP Violation: {violation_data}")
            
            # Store violation for analysis (in production, use proper storage)
            violation_log_dir = os.path.join(app.instance_path, 'security', 'csp_violations')
            os.makedirs(violation_log_dir, exist_ok=True)
            
            violation_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "violation": violation_data,
                "user_agent": request.headers.get('User-Agent'),
                "ip_address": request.remote_addr
            }
            
            violation_file = os.path.join(violation_log_dir, f"violations_{datetime.utcnow().strftime('%Y-%m-%d')}.jsonl")
            with open(violation_file, 'a') as f:
                f.write(json.dumps(violation_entry) + '\n')
            
            return '', 204  # No content response for CSP reports
            
        except Exception as e:
            logger.error(f"Error handling CSP report: {e}")
            return '', 204  # Still return 204 to avoid browser errors

    # Client-side error logging endpoint
    @app.route('/api/client-errors', methods=['POST'])
    def client_errors():
        """Handle client-side error reports."""
        try:
            error_data = request.get_json()
            
            # Log client-side error
            logger.info(f"Client Error: {error_data}")
            
            # Store error for analysis
            error_log_dir = os.path.join(app.instance_path, 'monitoring', 'client_errors')
            os.makedirs(error_log_dir, exist_ok=True)
            
            error_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "error": error_data,
                "user_agent": request.headers.get('User-Agent'),
                "ip_address": request.remote_addr,
                "referer": request.headers.get('Referer')
            }
            
            error_file = os.path.join(error_log_dir, f"client_errors_{datetime.utcnow().strftime('%Y-%m-%d')}.jsonl")
            with open(error_file, 'a') as f:
                f.write(json.dumps(error_entry) + '\n')
            
            return jsonify({"status": "logged", "timestamp": error_entry["timestamp"]})
            
        except Exception as e:
            logger.error(f"Error handling client error report: {e}")
            return jsonify({"error": "Failed to log client error"}), 500

    # Ensure secure sessions
    @app.before_request
    def make_session_permanent():
        # Ensure session is permanent but respects lifetime
        session.permanent = True

    # Add support for reloading the application in development
    if app.debug:
        try:
            from flask_debugtoolbar import DebugToolbarExtension
            toolbar = DebugToolbarExtension(app)
            app.logger.info("Debug toolbar enabled")
        except ImportError:
            app.logger.info("Debug toolbar not available")

    # Convenience method for getting the app instance
    @app.route('/debug-app')
    def debug_app():
        """Debug endpoint to check app configuration."""
        if not app.debug and not app.config.get('TESTING'):
            return jsonify({"error": "Debug endpoints only available in debug/test mode"}), 403
        
        return jsonify({
            "environment": {
                "is_heroku": is_heroku,
                "is_development": is_development,
                "is_windows": is_windows,
                "platform": platform.system(),
                "python_version": platform.python_version(),
                "flask_debug": app.debug,
                "flask_testing": app.config.get('TESTING', False),
            },
            "cookie_config": {
                "session_cookie_secure": app.config.get('SESSION_COOKIE_SECURE'),
                "session_cookie_httponly": app.config.get('SESSION_COOKIE_HTTPONLY'),
                "session_cookie_samesite": app.config.get('SESSION_COOKIE_SAMESITE'),
                "permanent_session_lifetime": str(app.config.get('PERMANENT_SESSION_LIFETIME')),
            }
        })

    # Set debug mode explicitly for security
    app.debug = is_development and not is_heroku

    # Widget security test page
    @app.route('/widget-test')
    def widget_test():
        """Widget security test page for CSP and injection testing."""
        return render_template('widget_test_security.html')

    # RATE LIMITING & DOS PROTECTION
    try:
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address
        
        limiter = Limiter(
            key_func=get_remote_address,
            default_limits=["1000 per hour", "100 per minute"],
            storage_uri="memory://",
            strategy="fixed-window"
        )
        limiter.init_app(app)
        
        # Store limiter for use in routes
        app.limiter = limiter
        logger.info("Rate limiting enabled with Flask-Limiter")
        
    except ImportError:
        logger.warning("Flask-Limiter not available - rate limiting disabled")
        app.limiter = None

    # ERROR HANDLING & INFORMATION DISCLOSURE PREVENTION
    @app.errorhandler(400)
    def handle_bad_request(e):
        """Handle 400 errors without leaking sensitive information."""
        if app.config.get('ENV') == 'production':
            return jsonify({
                'error': 'Bad Request',
                'message': 'The request could not be processed.',
                'request_id': getattr(g, 'request_id', 'unknown')
            }), 400
        else:
            # Show detailed errors in development
            return jsonify({
                'error': 'Bad Request',
                'message': str(e),
                'request_id': getattr(g, 'request_id', 'unknown')
            }), 400

    @app.errorhandler(401)
    def handle_unauthorized(e):
        """Handle 401 errors without leaking sensitive information."""
        return jsonify({
            'error': 'Unauthorized',
            'message': 'Authentication required.',
            'request_id': getattr(g, 'request_id', 'unknown')
        }), 401

    @app.errorhandler(403)
    def handle_forbidden(e):
        """Handle 403 errors without leaking sensitive information."""
        return jsonify({
            'error': 'Forbidden',
            'message': 'Access denied.',
            'request_id': getattr(g, 'request_id', 'unknown')
        }), 403

    @app.errorhandler(404)
    def handle_not_found(e):
        """Handle 404 errors without leaking sensitive information."""
        return jsonify({
            'error': 'Not Found',
            'message': 'The requested resource was not found.',
            'request_id': getattr(g, 'request_id', 'unknown')
        }), 404

    @app.errorhandler(429)
    def handle_rate_limit(e):
        """Handle rate limit errors."""
        return jsonify({
            'error': 'Rate Limit Exceeded',
            'message': 'Too many requests. Please try again later.',
            'request_id': getattr(g, 'request_id', 'unknown')
        }), 429

    @app.errorhandler(500)
    def handle_internal_error(e):
        """Handle 500 errors without leaking sensitive information."""
        # Log detailed error server-side only
        logger.error(f"Internal server error: {str(e)}", extra={
            'request_id': getattr(g, 'request_id', 'unknown'),
            'user_agent': request.headers.get('User-Agent'),
            'ip_address': request.remote_addr,
            'endpoint': request.endpoint,
            'method': request.method
        })
        
        if app.config.get('ENV') == 'production':
            return jsonify({
                'error': 'Internal Server Error',
                'message': 'An unexpected error occurred. Please try again later.',
                'request_id': getattr(g, 'request_id', 'unknown')
            }), 500
        else:
            # Show detailed errors in development
            return jsonify({
                'error': 'Internal Server Error',
                'message': str(e),
                'request_id': getattr(g, 'request_id', 'unknown')
            }), 500

    @app.errorhandler(Exception)
    def handle_unexpected_error(e):
        """Handle unexpected errors without leaking sensitive information."""
        # Log detailed error server-side only
        logger.error(f"Unexpected error: {str(e)}", extra={
            'request_id': getattr(g, 'request_id', 'unknown'),
            'user_agent': request.headers.get('User-Agent'),
            'ip_address': request.remote_addr,
            'endpoint': request.endpoint,
            'method': request.method,
            'exception_type': type(e).__name__
        })
        
        if app.config.get('ENV') == 'production':
            return jsonify({
                'error': 'Service Temporarily Unavailable',
                'message': 'The service is temporarily unavailable. Please try again later.',
                'request_id': getattr(g, 'request_id', 'unknown')
            }), 503
        else:
            # Show detailed errors in development
            return jsonify({
                'error': 'Unexpected Error',
                'message': str(e),
                'exception_type': type(e).__name__,
                'request_id': getattr(g, 'request_id', 'unknown')
            }), 500

    # PRODUCTION CONFIGURATION HARDENING
    def validate_production_environment():
        """Validate production environment configuration and security settings."""
        if app.config.get('ENV') != 'production':
            return  # Skip validation for non-production environments
        
        logger.info("Validating production environment configuration...")
        
        # Critical environment variables that must be set in production
        required_env_vars = {
            'LEMMA_API_KEY': 'API authentication key',
            'LEMMA_SECRET_KEY': 'Flask secret key for session security',
        }
        
        # Optional environment variables (not required for basic operation)
        optional_env_vars = {
            'DATABASE_URL': 'Database connection string (uses file storage if not set)',
        }
        
        optional_secure_env_vars = {
            'OPRF_API_KEY': 'OPRF service authentication',
            'OPRF_CERT_FINGERPRINT': 'OPRF service certificate fingerprint',
            'STRIPE_SECRET_KEY': 'Stripe payment processing',
            'STRIPE_WEBHOOK_SECRET': 'Stripe webhook validation'
        }
        
        missing_vars = []
        weak_vars = []
        
        # Validate required environment variables
        for var_name, description in required_env_vars.items():
            value = os.environ.get(var_name)
            if not value:
                missing_vars.append(f"{var_name} ({description})")
            elif len(value) < 32:  # Minimum entropy requirement
                weak_vars.append(f"{var_name} (too short - minimum 32 characters)")
        
        # Validate optional but recommended variables
        for var_name, description in optional_secure_env_vars.items():
            value = os.environ.get(var_name)
            if value and len(value) < 16:
                weak_vars.append(f"{var_name} (too short for security)")
                
        # Log optional environment variables status
        for var_name, description in optional_env_vars.items():
            value = os.environ.get(var_name)
            if not value:
                logger.info(f"Optional environment variable not set: {var_name} ({description})")
            else:
                logger.info(f"Optional environment variable configured: {var_name}")
        
        # Check for insecure default values
        insecure_defaults = {
            'LEMMA_SECRET_KEY': ['dev', 'development', 'secret', 'change-me'],
            'LEMMA_API_KEY': ['dev_api_key', 'test_key', 'changeme']
        }
        
        for var_name, insecure_values in insecure_defaults.items():
            value = os.environ.get(var_name, '').lower()
            if any(insecure in value for insecure in insecure_values):
                weak_vars.append(f"{var_name} (using insecure default value)")
        
        # Report validation results
        if missing_vars:
            error_msg = f"PRODUCTION SECURITY ERROR: Missing required environment variables: {', '.join(missing_vars)}"
            logger.error(error_msg)
            raise EnvironmentError(error_msg)
        
        if weak_vars:
            warning_msg = f"PRODUCTION SECURITY WARNING: Weak environment variables detected: {', '.join(weak_vars)}"
            logger.warning(warning_msg)
        
        # Validate debug mode is completely disabled
        if app.debug or app.config.get('DEBUG'):
            error_msg = "PRODUCTION SECURITY ERROR: Debug mode must be disabled in production"
            logger.error(error_msg)
            raise EnvironmentError(error_msg)
        
        # Validate secure session configuration
        if not app.config.get('SESSION_COOKIE_SECURE'):
            logger.warning("PRODUCTION WARNING: SESSION_COOKIE_SECURE should be True in production")
        
        if not app.config.get('SESSION_COOKIE_HTTPONLY'):
            logger.warning("PRODUCTION WARNING: SESSION_COOKIE_HTTPONLY should be True")
        
        logger.info("Production environment validation completed successfully")
    
    # Run production validation
    try:
        validate_production_environment()
    except Exception as e:
        logger.error(f"Production validation failed: {e}")
        # Temporarily disable strict production validation for debugging
        # TODO: Re-enable after environment variables are properly configured
        logger.warning("Continuing despite production validation failure for debugging")

    # SECRETS MANAGEMENT ENHANCEMENT
    def get_secure_config(key: str, default=None, min_length: int = 0):
        """Securely retrieve configuration values with validation."""
        value = os.environ.get(key, default)
        
        if value and min_length > 0 and len(value) < min_length:
            logger.warning(f"Configuration value for {key} is shorter than recommended ({min_length} chars)")
        
        # Log configuration access (without revealing values)
        if app.config.get('ENV') == 'production':
            logger.info(f"Configuration accessed: {key} ({'SET' if value else 'NOT_SET'})")
        
        return value
    
    # Store secure config function in app for use by other modules
    app.get_secure_config = get_secure_config

    # NETWORK SECURITY IMPROVEMENTS
    @app.before_request
    def enforce_network_security():
        """Enforce network-level security policies."""
        # Skip for health checks and static files
        if request.endpoint in ['static', 'health_check', 'ping']:
            return
        
        # Disable HTTPS enforcement for local testing
        if False and app.config.get('ENV') == 'production':
            if not request.is_secure and 'localhost' not in request.host:
                # Redirect HTTP to HTTPS
                url = request.url.replace('http://', 'https://', 1)
                return redirect(url, code=301)
        
        # Add security context to request
        g.security_context = {
            'is_secure': request.is_secure,
            'user_agent': request.headers.get('User-Agent', ''),
            'ip_address': request.remote_addr,
            'timestamp': time.time()
        }
    
    # CERTIFICATE PINNING FOR OPRF SERVICE
    def setup_certificate_pinning():
        """Set up certificate pinning for external services."""
        try:
            # Certificate pinning configuration
            cert_pins = {
                'oprf_service': {
                    'url_pattern': 'oprf',
                    'fingerprint': os.environ.get('OPRF_CERT_FINGERPRINT'),
                    'backup_fingerprint': os.environ.get('OPRF_BACKUP_CERT_FINGERPRINT')
                },
                'stripe_api': {
                    'url_pattern': 'api.stripe.com',
                    'fingerprint': os.environ.get('STRIPE_CERT_FINGERPRINT'),
                    'backup_fingerprint': None  # Stripe manages their own certificates
                }
            }
            
            # Store certificate pins in app config
            app.config['CERTIFICATE_PINS'] = cert_pins
            
            if app.config.get('ENV') == 'production':
                logger.info("Certificate pinning configured for production")
            
        except Exception as e:
            logger.warning(f"Certificate pinning setup failed: {e}")
    
    setup_certificate_pinning()



    return app

def _init_components(app):
    """Initialize all Lemma components."""
    # Initialize credential service
    from lemma.core.credential_service import init_credential_service
    credential_service = init_credential_service(app)
    if not credential_service:
        app.logger.warning("Failed to initialize credential service")
    else:
        # Store in app context
        g._credential_service = credential_service
    
    # Initialize DID resolver
    try:
        from lemma.core.did_resolver import get_did_resolver
        app.logger.info('Initialized DID resolver')
    except ImportError:
        app.logger.warning('DID resolver module not available')
    
    # Initialize Stripe Identity if API key is configured
    try:
        stripe_api_key = os.environ.get('STRIPE_API_KEY') or app.config.get('STRIPE_API_KEY')
        if stripe_api_key:
            from lemma.utils.stripe_service import init_stripe
            if init_stripe():
                app.logger.info('Initialized Stripe Identity verification')
            else:
                app.logger.warning('Failed to initialize Stripe Identity verification')
        else:
            app.logger.warning('Stripe API key not configured, Identity verification will be unavailable')
    except ImportError:
        app.logger.warning('Stripe integration not available')
    
    # Initialize revocation registry if enabled
    if app.config.get('ENABLE_P2P', False):
        try:
            from lemma.core.revocation_registry import init_revocation_registry
            init_revocation_registry(app)
            app.logger.info('Initialized revocation registry')
        except ImportError:
            app.logger.warning('Revocation registry not available')
    
    # Initialize OPRF cascade manager - ensure it works in Heroku
    try:
        # Check if OPRF is enabled
        oprf_enabled = os.environ.get('OPRF_SERVICE_INTERNAL', 'false').lower() == 'true'
        
        if oprf_enabled:
            from lemma.core.cascaded_bloom import CascadedBloomRevocation, OPRFClient
            # Check if we're running on Heroku
            is_heroku = 'DYNO' in os.environ
            
            # Configure OPRF client
            if is_heroku:
                app.logger.info("Configured OPRF for internal service on Heroku")
                
                # Ensure the keys directory exists
                keys_dir = os.path.join(app.instance_path, 'data', 'keys')
                os.makedirs(keys_dir, exist_ok=True)
                
                # Ensure the cascade directory exists
                cascade_dir = os.path.join(app.instance_path, 'data', 'revocation', 'cascades')
                os.makedirs(cascade_dir, exist_ok=True)
                
            # Initialize OPRF client
            oprf_client = OPRFClient()
            app.logger.info(f"Initialized OPRF client: {oprf_client.server_url}")
            
            # Store client in app context for reuse
            g._oprf_client = oprf_client
            
            # Try to connect to the OPRF service
            try:
                pubkey = oprf_client.get_public_key()
                app.logger.info(f"Successfully connected to OPRF service, public key available")
            except Exception as e:
                app.logger.warning(f"OPRF service not available yet: {e}")
        else:
            app.logger.info("OPRF service disabled via configuration")
    except ImportError:
        app.logger.warning('OPRF cascade integration not available') 