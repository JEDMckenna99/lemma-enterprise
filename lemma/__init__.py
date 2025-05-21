"""
Lemma Enterprise - Human Verification System
Web application factory and configuration.
Enhanced with enterprise-grade security and features.
"""

import os
import sys
import secrets
import logging
from flask import Flask, request, session, g, redirect
from werkzeug.middleware.proxy_fix import ProxyFix
from logging.handlers import RotatingFileHandler
import socket
import shutil
from flask_wtf.csrf import CSRFProtect

# Create logger
logger = logging.getLogger(__name__)

def create_app(test_config=None):
    """Create and configure the Flask application."""
    
    # Get the current working directory and determine if running on Heroku
    cwd = os.getcwd()
    is_heroku = 'DYNO' in os.environ
    
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
    
    # Initialize CSRF protection
    from lemma.auth.csrf_config import configure_csrf
    configure_csrf(app)
    
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
        # Enhanced security settings for OIDC4VP compliance
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Strict',  # Changed from 'Lax' to 'Strict' for OIDC4VP
        PERMANENT_SESSION_LIFETIME=1800,  # 30 minutes
        # CSRF Configuration
        WTF_CSRF_ENABLED=True,
        WTF_CSRF_SSL_STRICT=True,  # Enforce HTTPS for CSRF tokens
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
        
        app.register_blueprint(main_bp)
        app.register_blueprint(admin_bp, url_prefix='/admin')
        app.register_blueprint(api_bp, url_prefix='/api')
        app.logger.info("Successfully registered all blueprints")
    except Exception as e:
        app.logger.error(f"Error registering blueprints: {e}")
        raise  # This is critical - we need the routes

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

    # Enable HSTS in production
    @app.after_request
    def add_security_headers(response):
        if not app.debug and not app.testing:
            # Enable HTTP Strict Transport Security (HSTS)
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
            # Prevent MIME type sniffing
            response.headers['X-Content-Type-Options'] = 'nosniff'
            # Enable XSS protection
            response.headers['X-XSS-Protection'] = '1; mode=block'
            # Prevent clickjacking
            response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        return response

    return app

def _init_components(app):
    """Initialize all Lemma components."""
    # Initialize credential service
    from lemma.core.credential_service import init_credential_service
    if not init_credential_service(app):
        app.logger.warning("Failed to initialize credential service")
    
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
