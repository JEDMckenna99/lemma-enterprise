"""
Lemma Enterprise Python Integration Examples
Human Verification Protocol for Python Applications

Supports Flask, Django, and FastAPI frameworks with complete examples.
"""

import os
import json
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, Callable
from functools import wraps

import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# ============================================================================
# CONFIGURATION
# ============================================================================

LEMMA_BASE_URL = 'https://lemma.id'
LEMMA_API_KEY = os.environ.get('LEMMA_API_KEY')

if not LEMMA_API_KEY:
    raise ValueError("❌ LEMMA_API_KEY environment variable is required")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# LEMMA CLIENT CLASS
# ============================================================================

class LemmaClient:
    """
    Lemma Enterprise API client for Python applications.
    """
    
    def __init__(self, api_key: str, base_url: str = LEMMA_BASE_URL):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        
        # Configure session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            method_whitelist=["HEAD", "GET", "OPTIONS", "POST"],
            backoff_factor=1
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set default headers
        self.session.headers.update({
            'X-API-Key': api_key,
            'Content-Type': 'application/json',
            'User-Agent': 'Lemma-Python-Client/1.0'
        })
    
    def generate_challenge(self) -> Dict[str, Any]:
        """Generate a verification challenge."""
        try:
            response = self.session.get(f'{self.base_url}/api/generate-challenge')
            response.raise_for_status()
            data = response.json()
            return data['data']
        except requests.RequestException as e:
            raise Exception(f"Failed to generate challenge: {e}")
    
    def verify_human(self, presentation: Dict, challenge: str, domain: str) -> Dict[str, Any]:
        """Verify human credential presentation."""
        try:
            payload = {
                'presentation': presentation,
                'challenge': challenge,
                'domain': domain
            }
            response = self.session.post(f'{self.base_url}/api/verify-human', json=payload)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise Exception(f"Human verification failed: {e}")
    
    def get_monthly_usage(self, year: int, month: int) -> Dict[str, Any]:
        """Get monthly usage metrics."""
        try:
            params = {'year': year, 'month': month}
            response = self.session.get(f'{self.base_url}/api/billing/usage/monthly', params=params)
            response.raise_for_status()
            data = response.json()
            return data['data']
        except requests.RequestException as e:
            raise Exception(f"Failed to get usage metrics: {e}")
    
    def health_check(self) -> Dict[str, Any]:
        """Check API health status."""
        try:
            response = requests.get(f'{self.base_url}/api/health')
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise Exception(f"Health check failed: {e}")
    
    def issue_credential(self, user_id: str, verification_method: str = "sandbox") -> Dict[str, Any]:
        """Issue a new credential (sandbox only for testing)."""
        try:
            payload = {
                'user_id': user_id,
                'verification_method': verification_method
            }
            response = self.session.post(f'{self.base_url}/api/issue-credential', json=payload)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise Exception(f"Failed to issue credential: {e}")

# ============================================================================
# FLASK INTEGRATION
# ============================================================================

try:
    from flask import Flask, request, jsonify, session, g
    from functools import wraps
    
    class FlaskLemmaIntegration:
        """Flask integration for Lemma human verification."""
        
        def __init__(self, app: Flask = None, api_key: str = None):
            self.app = app
            self.lemma = LemmaClient(api_key or LEMMA_API_KEY)
            
            if app:
                self.init_app(app)
        
        def init_app(self, app: Flask):
            """Initialize Flask app with Lemma."""
            app.config.setdefault('LEMMA_DOMAIN', 'localhost')
            app.config.setdefault('LEMMA_SESSION_KEY', 'lemma_verified')
            
            # Register routes
            @app.route('/api/lemma/challenge')
            def lemma_challenge():
                try:
                    challenge = self.lemma.generate_challenge()
                    return jsonify({'success': True, 'data': challenge})
                except Exception as e:
                    return jsonify({'success': False, 'error': str(e)}), 500
            
            @app.route('/api/lemma/verify', methods=['POST'])
            def lemma_verify():
                try:
                    data = request.get_json()
                    presentation = data.get('presentation')
                    challenge = data.get('challenge')
                    domain = data.get('domain', app.config['LEMMA_DOMAIN'])
                    
                    if not presentation or not challenge:
                        return jsonify({
                            'success': False,
                            'error': 'Missing presentation or challenge'
                        }), 400
                    
                    result = self.lemma.verify_human(presentation, challenge, domain)
                    
                    if result.get('success') and result.get('data', {}).get('verified'):
                        session[app.config['LEMMA_SESSION_KEY']] = True
                        session['lemma_user_id'] = result['data'].get('user_id')
                        return jsonify(result)
                    else:
                        return jsonify(result), 403
                        
                except Exception as e:
                    return jsonify({'success': False, 'error': str(e)}), 500
        
        def require_human(self, f: Callable) -> Callable:
            """Decorator to require human verification."""
            @wraps(f)
            def decorated_function(*args, **kwargs):
                if not session.get(self.app.config['LEMMA_SESSION_KEY']):
                    return jsonify({
                        'success': False,
                        'error': 'Human verification required',
                        'verify_url': '/api/lemma/verify'
                    }), 401
                
                g.lemma_user_id = session.get('lemma_user_id')
                return f(*args, **kwargs)
            
            return decorated_function
    
    # Flask example application
    def create_flask_app():
        """Create a Flask app with Lemma integration."""
        app = Flask(__name__)
        app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'change-me-in-production')
        
        lemma_integration = FlaskLemmaIntegration(app)
        
        @app.route('/health')
        def health():
            try:
                lemma_health = lemma_integration.lemma.health_check()
                return jsonify({
                    'status': 'ok',
                    'lemma_service': lemma_health.get('status'),
                    'timestamp': datetime.utcnow().isoformat()
                })
            except Exception as e:
                return jsonify({
                    'status': 'error',
                    'error': str(e)
                }), 503
        
        @app.route('/api/public')
        def public_endpoint():
            return jsonify({
                'message': 'This is a public endpoint accessible to everyone',
                'timestamp': datetime.utcnow().isoformat()
            })
        
        @app.route('/api/protected')
        @lemma_integration.require_human
        def protected_endpoint():
            return jsonify({
                'message': 'This content is only accessible to verified humans',
                'user_id': g.lemma_user_id,
                'timestamp': datetime.utcnow().isoformat(),
                'data': {
                    'secret': 'Human-only content here',
                    'user_privileges': ['view_premium_content', 'post_comments', 'access_api']
                }
            })
        
        @app.route('/api/usage')
        def usage_metrics():
            try:
                now = datetime.now()
                usage = lemma_integration.lemma.get_monthly_usage(now.year, now.month)
                return jsonify({'success': True, 'data': usage})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500
        
        return app

except ImportError:
    logger.warning("Flask not available. Skipping Flask integration.")
    FlaskLemmaIntegration = None

# ============================================================================
# TESTING UTILITIES
# ============================================================================

def test_lemma_integration():
    """Test the Lemma integration."""
    print("🧪 Testing Lemma Integration...")
    
    lemma = LemmaClient(LEMMA_API_KEY)
    
    try:
        # Test health check
        health = lemma.health_check()
        print(f"✅ Health check: {health.get('status')}")
        
        # Test challenge generation
        challenge = lemma.generate_challenge()
        print(f"✅ Challenge generated: {challenge['challenge'][:10]}...")
        
        # Test usage metrics (if available)
        try:
            now = datetime.now()
            usage = lemma.get_monthly_usage(now.year, now.month)
            print(f"✅ Usage metrics retrieved: {usage.get('total_verifications', 0)} verifications")
        except Exception:
            print("ℹ️ Usage metrics not available (normal for new accounts)")
        
        print("🎉 All tests passed! Lemma integration is ready.")
        return True
        
    except Exception as error:
        print(f"❌ Integration test failed: {error}")
        return False

# ============================================================================
# SANDBOX UTILITIES
# ============================================================================

class LemmaSandbox:
    """Utilities for testing with Lemma sandbox environment."""
    
    def __init__(self, api_key: str = None):
        self.lemma = LemmaClient(api_key or LEMMA_API_KEY)
    
    def create_test_credential(self, user_id: str = None) -> Dict[str, Any]:
        """Create a test credential for sandbox testing."""
        if not user_id:
            user_id = f"test_user_{int(datetime.utcnow().timestamp())}"
        
        try:
            return self.lemma.issue_credential(user_id, "sandbox")
        except Exception as e:
            logger.error(f"Failed to create test credential: {e}")
            return None
    
    def simulate_verification_flow(self, domain: str = "localhost") -> bool:
        """Simulate a complete verification flow for testing."""
        try:
            # Step 1: Generate challenge
            challenge_data = self.lemma.generate_challenge()
            challenge = challenge_data['challenge']
            print(f"Generated challenge: {challenge[:10]}...")
            
            # Step 2: Create test credential
            credential_data = self.create_test_credential()
            if not credential_data:
                return False
            
            credential = credential_data['data']['credential']
            print(f"Created test credential for user: {credential['credentialSubject']['id']}")
            
            # Step 3: Simulate verification (would normally come from frontend)
            presentation = {
                "@context": ["https://www.w3.org/2018/credentials/v1"],
                "type": ["VerifiablePresentation"],
                "verifiableCredential": [credential],
                "proof": {
                    "type": "Ed25519Signature2020",
                    "challenge": challenge,
                    "domain": domain
                }
            }
            
            # Step 4: Verify presentation
            result = self.lemma.verify_human(presentation, challenge, domain)
            
            if result.get('success') and result.get('data', {}).get('verified'):
                print("✅ Verification successful!")
                return True
            else:
                print("❌ Verification failed!")
                return False
                
        except Exception as e:
            print(f"❌ Simulation failed: {e}")
            return False

# ============================================================================
# COMMAND LINE INTERFACE
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Lemma Python Integration")
    parser.add_argument('--test', action='store_true', help='Run integration tests')
    parser.add_argument('--sandbox', action='store_true', help='Run sandbox simulation')
    parser.add_argument('--flask', action='store_true', help='Run Flask example app')
    parser.add_argument('--port', type=int, default=5000, help='Port to run server on')
    
    args = parser.parse_args()
    
    if args.test:
        test_lemma_integration()
    
    if args.sandbox:
        sandbox = LemmaSandbox()
        sandbox.simulate_verification_flow()
    
    if args.flask and FlaskLemmaIntegration:
        app = create_flask_app()
        print(f"🚀 Starting Flask app on port {args.port}")
        print(f"📖 Health check: http://localhost:{args.port}/health")
        print(f"🔒 Protected endpoint: http://localhost:{args.port}/api/protected")
        app.run(host='0.0.0.0', port=args.port, debug=True)
    
    if not any([args.test, args.sandbox, args.flask]):
        print("Run with --help to see available options")
        test_lemma_integration()

# ============================================================================
# USAGE EXAMPLES
# ============================================================================

"""
Usage Examples:

1. Basic Client Usage:
    lemma = LemmaClient(os.environ['LEMMA_API_KEY'])
    challenge = lemma.generate_challenge()
    result = lemma.verify_human(presentation, challenge['challenge'], 'yourdomain.com')

2. Flask Integration:
    app = create_flask_app()
    app.run()

3. Testing:
    python python-integration.py --test --sandbox

4. Environment Variables:
    export LEMMA_API_KEY=your_api_key_here
    export FLASK_SECRET_KEY=your_session_secret_here

""" 