"""
Lemma Enterprise - Human Verification System
Web application factory and configuration.
Enhanced with enterprise-grade security and features.
"""

import os
import sys
import secrets
import logging
from flask import Flask, request, session, g, redirect, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix
from logging.handlers import RotatingFileHandler
import socket
import shutil

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

def create_app(test_config=None):
    """Create and configure the Flask application."""
    
    # Get the current working directory and determine if running on Heroku
    cwd = os.getcwd()
    is_heroku = 'DYNO' in os.environ
    
    # Determine if we're in development mode
    is_development = not is_heroku and (
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
        STRIPE_API_KEY=os.environ.get('STRIPE_API_KEY'),
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
        }
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
    
    # Register blueprints directly from their modules
    try:
        from lemma.routes.main import main_bp
        from lemma.routes.admin import admin_bp 
        from lemma.routes.api import api_bp
        from lemma.routes.onboarding import onboarding_bp
        from lemma.routes.billing import billing_bp
        from lemma.routes.gate_demo import gate_demo
        
        app.register_blueprint(main_bp)
        app.register_blueprint(admin_bp, url_prefix='/admin')
        app.register_blueprint(api_bp, url_prefix='/api')
        app.register_blueprint(onboarding_bp, url_prefix='/onboarding')
        app.register_blueprint(billing_bp, url_prefix='/billing')
        app.register_blueprint(gate_demo)  # No prefix for gate demo routes
        app.logger.info("Successfully registered all blueprints including gate demo")
    except Exception as e:
        app.logger.error(f"Error registering blueprints: {e}")
        raise  # This is critical - we need the routes

    # Register billing API blueprint
    try:
        from lemma.routes.billing_api import billing_api
        app.register_blueprint(billing_api)
        app.logger.info("Billing API endpoints registered successfully")
    except ImportError as e:
        app.logger.warning(f"Billing API not available: {e}")
    except Exception as e:
        app.logger.error(f"Error registering billing API: {e}")

    # Register enhanced API blueprint
    try:
        from lemma.routes.api_enhanced import api_enhanced
        app.register_blueprint(api_enhanced)
        app.logger.info("Enhanced API v2 endpoints registered successfully")
    except ImportError as e:
        app.logger.warning(f"Enhanced API not available: {e}")

    # Register compliance API blueprint
    try:
        from lemma.routes.compliance import compliance_bp
        app.register_blueprint(compliance_bp)
        app.logger.info("Compliance API endpoints registered successfully")
    except ImportError as e:
        app.logger.warning(f"Compliance API not available: {e}")
    except Exception as e:
        app.logger.error(f"Error registering compliance API: {e}")

    # Register SRE monitoring blueprint
    try:
        from lemma.routes.sre_monitoring import sre_bp
        app.register_blueprint(sre_bp, url_prefix='/api/sre')
        app.logger.info("SRE monitoring endpoints registered successfully")
    except ImportError as e:
        app.logger.warning(f"SRE monitoring not available: {e}")
    except Exception as e:
        app.logger.error(f"Error registering SRE monitoring: {e}")

    # Initialize SRE monitoring system
    try:
        from lemma.utils.sre_middleware import init_sre_monitoring
        init_sre_monitoring(app)
        app.logger.info("SRE monitoring system initialized successfully")
    except ImportError as e:
        app.logger.warning(f"SRE monitoring not available: {e}")
    except Exception as e:
        app.logger.error(f"Error initializing SRE monitoring: {e}")

    # Initialize performance optimizations
    try:
        from lemma.utils.performance_middleware import init_performance_middleware
        init_performance_middleware(app)
        app.logger.info("Performance optimizations initialized - targeting <250ms response times")
    except ImportError as e:
        app.logger.warning(f"Performance middleware not available: {e}")
    except Exception as e:
        app.logger.error(f"Error initializing performance middleware: {e}")

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
    
    # Force HTTPS in production for OIDC4VP compliance
    @app.before_request
    def force_https():
        if not app.debug and not app.testing:
            if request.headers.get('X-Forwarded-Proto', 'http') != 'https':
                url = request.url.replace('http://', 'https://', 1)
                return redirect(url, code=301)

    # Configure security headers
    @app.after_request
    def add_security_headers(response):
        # Add security headers based on environment
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        
        # Only add HSTS in production
        if not is_development and not app.config.get('TESTING'):
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        
        # Ensure session cookies have proper security flags
        if 'Set-Cookie' in response.headers:
            cookies = response.headers.getlist('Set-Cookie')
            new_cookies = []
            
            for cookie in cookies:
                # Apply security flags to session cookies
                if 'session=' in cookie:
                    # Ensure HttpOnly is present for session cookies
                    if 'HttpOnly' not in cookie:
                        cookie += '; HttpOnly'
                    # In production, ensure secure flag is present for HTTPS
                    if not is_development and 'Secure' not in cookie:
                        cookie += '; Secure'
                    # Ensure SameSite is set correctly
                    if 'SameSite' not in cookie:
                        samesite_value = 'Strict' if not is_development else 'Lax'
                        cookie += f'; SameSite={samesite_value}'
                new_cookies.append(cookie)
            
            # Replace all cookies
            response.headers.pop('Set-Cookie')
            for cookie in new_cookies:
                response.headers.add('Set-Cookie', cookie)
        
        return response

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