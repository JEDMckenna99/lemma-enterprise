"""
Lemma Enterprise - Human Verification System
A secure, privacy-focused system for verifying humans with minimal data collection.
"""
import os
from flask import Flask
from flask_cors import CORS

# Import enhanced CSRF protection
from lemma.auth.csrf_config import configure_csrf

def create_app(test_config=None):
    """Create and configure the Flask application
    
    Args:
        test_config: Optional dictionary of test configuration values
        
    Returns:
        The configured Flask application
    """
    app = Flask(__name__, 
                instance_relative_config=True,
                template_folder='../templates',
                static_folder='../static')
    
    # Load default configuration
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('LEMMA_SECRET_KEY', os.urandom(32)),
        STORAGE_DIR=os.environ.get('LEMMA_STORAGE_DIR', '.lemma_enterprise'),
        ADMIN_USERNAME=os.environ.get('LEMMA_ADMIN_USER', 'lemma_admin'),
        ADMIN_PASSWORD=os.environ.get('LEMMA_ADMIN_PASS', 'Secure_Lemma_Password_2025!'),
        API_KEY=os.environ.get('LEMMA_API_KEY', 'lemma_api_key_change_me'),
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        PERMANENT_SESSION_LIFETIME=7200,  # 2 hours
        SKIP_AUTH_IN_TESTS=False,  # Default to not skipping auth in tests
        WTF_CSRF_ENABLED=True,  # Enable CSRF protection by default
    )
    
    # Override with test config if provided
    if test_config:
        app.config.update(test_config)
        
        # Special handling for test environments
        if app.config.get('TESTING', False):
            # If in testing mode, adjust security settings
            app.config['WTF_CSRF_ENABLED'] = not app.config.get('SKIP_AUTH_IN_TESTS', False)
            app.config['SESSION_COOKIE_SECURE'] = False
            app.config['SESSION_COOKIE_HTTPONLY'] = False
            app.logger.info(f"Test mode detected. CSRF enabled: {app.config['WTF_CSRF_ENABLED']}")
    
    # Ensure storage directory exists
    os.makedirs(app.config['STORAGE_DIR'], exist_ok=True)
    
    # Initialize enhanced CSRF protection
    configure_csrf(app)
    
    # Initialize CORS with secure defaults - restrict to trusted origins in production
    if app.config.get('ENV') == 'production':
        # In production, only allow specific origins
        trusted_origins = os.environ.get('LEMMA_TRUSTED_ORIGINS', 'https://your-domain.com').split(',')
        CORS(app, resources={r"/api/*": {"origins": trusted_origins}})
    else:
        # In development, allow all origins
        CORS(app, resources={r"/api/*": {"origins": "*"}})
    
    # Register blueprints
    from lemma.routes.main import main_bp
    from lemma.routes.admin import admin_bp
    from lemma.routes.api import api_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    
    # Initialize the credential service
    from lemma.core.credential_service import init_credential_service
    init_credential_service(app)
    
    # Add template global for CSRF token
    @app.template_global()
    def csrf_token():
        """Generate a CSRF token for templates.
        
        This function makes the CSRF token available in templates via {{ csrf_token() }}.
        It uses the token from session, or generates a new one if needed.
        
        Returns:
            str: The CSRF token.
        """
        from lemma.auth.csrf_config import generate_csrf_token
        return generate_csrf_token()
    
    return app
