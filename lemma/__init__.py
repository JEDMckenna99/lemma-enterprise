"""
Lemma Enterprise - Human Verification System
Web application factory and configuration.
Enhanced with enterprise-grade security and features.
"""

import os
import sys
import secrets
import logging
from flask import Flask, request, session, g
from werkzeug.middleware.proxy_fix import ProxyFix
from logging.handlers import RotatingFileHandler
import socket

# Create logger
logger = logging.getLogger(__name__)

def create_app(test_config=None):
    """Create and configure the Flask application."""
    
    # Create the Flask app
    app = Flask(__name__, instance_relative_config=True)
    
    # Enable trusted proxy support
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    
    # Load default configuration
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('LEMMA_SECRET_KEY', secrets.token_hex(32)),
        ADMIN_USER=os.environ.get('LEMMA_ADMIN_USER', 'admin'),
        ADMIN_PASS=os.environ.get('LEMMA_ADMIN_PASS', 'password'),
        API_KEY=os.environ.get('LEMMA_API_KEY', 'api-key'),
        TESTING=False,
        SKIP_AUTH_IN_TESTS=False,
        DEBUG=False,
        ENABLE_HARDWARE_SECURITY=os.environ.get('LEMMA_HARDWARE_SECURITY', 'false').lower() == 'true',
        ENABLE_P2P=os.environ.get('LEMMA_ENABLE_P2P', 'false').lower() == 'true',
        CREDENTIAL_EXPIRY_DAYS=int(os.environ.get('LEMMA_CREDENTIAL_EXPIRY_DAYS', '365')),
        MAX_CREDENTIALS_PER_USER=int(os.environ.get('LEMMA_MAX_CREDENTIALS_PER_USER', '1')),
        DID_METHOD=os.environ.get('DID_METHOD', 'key'),
        DID=os.environ.get('DID', 'did:lemma:local'),
        TRUSTED_ISSUERS=[os.environ.get('DID', 'did:lemma:local')],
        PEERS=os.environ.get('LEMMA_PEERS', '').split(',') if os.environ.get('LEMMA_PEERS') else [],
        MAX_VERIFICATION_ATTEMPTS=int(os.environ.get('LEMMA_MAX_VERIFICATION_ATTEMPTS', '10')),
        RATE_LIMIT_ENABLED=os.environ.get('LEMMA_RATE_LIMIT', 'true').lower() == 'true',
        # Enhanced security settings
        PERMANENT_SESSION_LIFETIME=int(os.environ.get('LEMMA_SESSION_LIFETIME', '3600')),  # 1 hour
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',  # Set to 'Lax' for better UX across site navigation
        REMEMBER_COOKIE_SECURE=True,
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SAMESITE='Lax',
        # CSRF Configuration
        WTF_CSRF_ENABLED=True,
        WTF_CSRF_TIME_LIMIT=int(os.environ.get('LEMMA_CSRF_TIME_LIMIT', '3600')),  # 1 hour
        WTF_CSRF_SSL_STRICT=True,
        # Audit logging
        AUDIT_LOGGING_ENABLED=os.environ.get('LEMMA_AUDIT_LOGGING', 'true').lower() == 'true',
        # Content Security Policy
        CSP_ENABLED=os.environ.get('LEMMA_CSP_ENABLED', 'true').lower() == 'true',
        # Hardware security
        HARDWARE_SECURITY=os.environ.get('LEMMA_HARDWARE_SECURITY', 'false').lower() == 'true',
        # P2P settings
        P2P_DISCOVERY_ENABLED=os.environ.get('LEMMA_P2P_DISCOVERY', 'false').lower() == 'true',
    )
    
    # Override configuration with test config if provided
    if test_config:
        app.config.update(test_config)
        
    # Ensure the instance folder exists
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass
    
    # Configure logging
    configure_logging(app)
    
    # Register security-related extensions
    register_security_extensions(app)
    
    # Register blueprints
    register_blueprints(app)
    
    # Register error handlers
    register_error_handlers(app)
    
    # Create credential service and storage directory
    init_credential_service(app)
    
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
    
    return app

def _init_components(app):
    """Initialize all Lemma components."""
    # Initialize credential service
    from lemma.core.credential_service import init_credential_service
    init_credential_service(app)
    
    # Initialize DID resolver
    try:
        from lemma.core.did_resolver import get_did_resolver
        app.logger.info('Initialized DID resolver')
    except ImportError:
        app.logger.warning('DID resolver module not available')
    
    # Initialize revocation registry if enabled
    if app.config.get('ENABLE_P2P', False):
        try:
            from lemma.core.revocation import init_revocation_registry, P2PRevocationNetwork
            
            # Initialize the registry
            registry = init_revocation_registry(os.path.join(app.config['STORAGE_DIR'], 'revocation'))
            app.logger.info('Initialized revocation registry')
            
            # Set up P2P network if peers are configured
            if app.config.get('P2P_PEERS'):
                network = P2PRevocationNetwork(registry, app.config['P2P_PEERS'])
                app.config['P2P_NETWORK'] = network
                app.logger.info(f'Initialized P2P network with {len(app.config["P2P_PEERS"])} peers')
                
            # Initialize peer discovery system
            try:
                from lemma.utils.network_utilities import init_peer_discovery
                
                # Get DID for node ID
                node_id = app.config.get('DID', f"did:lemma:{socket.gethostname()}")
                
                # Get node URL from config or try to determine it
                node_url = app.config.get('NODE_URL')
                if not node_url:
                    # Try to get hostname or IP address
                    try:
                        host = socket.gethostname()
                        # Get port from config or use default
                        port = app.config.get('PORT', 5000)
                        # Construct URL
                        node_url = f"http://{host}:{port}"
                    except:
                        node_url = "http://localhost:5000"
                
                # Get trusted peers from config
                trusted_peers = []
                for peer in app.config.get('P2P_PEERS', []):
                    trusted_peers.append({
                        'id': peer.get('id', f"did:lemma:peer{len(trusted_peers)}"),
                        'url': peer
                    })
                
                # Initialize peer discovery
                discovery = init_peer_discovery(node_id, node_url, trusted_peers)
                app.config['PEER_DISCOVERY'] = discovery
                app.logger.info(f'Initialized peer discovery as {node_id}')
            except ImportError:
                app.logger.warning('Peer discovery module not available')
        except ImportError:
            app.logger.warning('Revocation registry module not available')
    
    # Initialize secure storage if enabled
    if app.config.get('HARDWARE_SECURITY', False):
        try:
            from lemma.utils.secure_storage import get_secure_storage
            storage = get_secure_storage()
            app.config['SECURE_STORAGE'] = storage
            app.logger.info(f'Initialized secure storage on {storage.platform}')
        except ImportError:
            app.logger.warning('Secure storage module not available')
    
    # Initialize zero-knowledge components
    try:
        from lemma.utils.zero_knowledge import ZKProof, SelectiveDisclosure
        app.logger.info('Initialized zero-knowledge components')
    except ImportError:
        app.logger.warning('Zero-knowledge modules not available')
