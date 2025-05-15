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
import shutil

# Create logger
logger = logging.getLogger(__name__)

def create_app(test_config=None):
    """Create and configure the Flask application."""
    
    # Get the current working directory and determine if running on Heroku
    cwd = os.getcwd()
    is_heroku = 'DYNO' in os.environ
    
    # Determine template and static folders based on environment
    # We'll use absolute paths for everything for consistency
    template_dir = os.path.abspath(os.path.join(cwd, 'templates'))
    static_dir = os.path.abspath(os.path.join(cwd, 'static'))
    
    # Log directory information for debugging
    logger.info(f"Running with cwd: {cwd}")
    logger.info(f"Is Heroku: {is_heroku}")
    logger.info(f"Using template_dir: {template_dir}")
    logger.info(f"Using static_dir: {static_dir}")
    
    # List the contents of the app directory
    try:
        logger.info(f"App directory contents: {os.listdir(cwd)}")
        if os.path.exists(template_dir):
            logger.info(f"Template directory contents: {os.listdir(template_dir)}")
        else:
            logger.error(f"Template directory {template_dir} does not exist!")
    except Exception as e:
        logger.error(f"Error listing directories: {str(e)}")
    
    # Make sure the template directory exists
    if not os.path.exists(template_dir):
        os.makedirs(template_dir, exist_ok=True)
        logger.warning(f"Had to create templates directory at {template_dir}")
    
    # Make sure the static directory exists
    if not os.path.exists(static_dir):
        os.makedirs(static_dir, exist_ok=True)
        # Create an empty CSS file to make Flask happy
        try:
            with open(os.path.join(static_dir, 'dummy.css'), 'w') as f:
                f.write('/* Placeholder file */')
            logger.warning(f"Had to create static directory at {static_dir} with dummy file")
        except Exception as e:
            logger.error(f"Error creating dummy static file: {str(e)}")
    
    # Create the Flask app with explicit template and static folders
    app = Flask(__name__, 
                template_folder=template_dir,
                static_folder=static_dir,
                instance_relative_config=True)
    
    # Override Jinja loader to handle potential issues 
    from flask.templating import DispatchingJinjaLoader
    from jinja2 import FileSystemLoader, ChoiceLoader
    
    # Create a choice loader that will try multiple possible locations for templates
    template_dirs = [
        template_dir,  # First try the specified location
        os.path.join(cwd, 'templates'),  # Then try project root/templates
        os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates'),  # Then package parent/templates
    ]
    
    # Log the template search paths
    logger.info(f"Template search paths: {template_dirs}")
    
    # Create a choice loader with multiple possible paths
    choice_loader = ChoiceLoader([
        FileSystemLoader(template_dirs),
        app.jinja_loader  # Keep the default loader as fallback
    ])
    
    app.jinja_loader = choice_loader
    
    # Enable trusted proxy support
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    
    # Load default configuration
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('LEMMA_SECRET_KEY', secrets.token_hex(32)),
        STORAGE_DIR=os.environ.get('LEMMA_STORAGE_DIR', '.lemma_enterprise'),
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
        # Enhanced security settings
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',  # Set to 'Lax' for better UX across site navigation
        # CSRF Configuration
        WTF_CSRF_ENABLED=True,
    )
    
    # Override with test config if provided
    if test_config is not None:
        app.config.from_mapping(test_config)
        
    # Ensure the instance and storage folders exist
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config['STORAGE_DIR'], exist_ok=True)

    # Set up logging
    if not app.debug:
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

    # Initialize components
    _init_components(app)
    
    # Register blueprints directly from their modules
    from lemma.routes.main import main_bp
    from lemma.routes.admin import admin_bp 
    from lemma.routes.api import api_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(api_bp, url_prefix='/api')

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
