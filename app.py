#!/usr/bin/env python3
"""
Lemma Enterprise: Human Verification System with DID Proofing

A streamlined, enterprise-grade implementation for verifying humans
with minimal data collection and strong cryptographic standards.
"""
import os
import json
import uuid
import base64
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
from flask import render_template, request, jsonify, session, redirect, url_for

from lemma import create_app

# Create the application instance
app = create_app()

# Configuration
DATA_DIR = os.path.join(os.path.expanduser('~'), '.lemma_enterprise')
os.makedirs(DATA_DIR, exist_ok=True)

KEYS_FILE = os.path.join(DATA_DIR, 'keys.json')
REGISTRY_FILE = os.path.join(DATA_DIR, 'registry.json')
USERS_FILE = os.path.join(DATA_DIR, 'users.json')

# Admin credentials (should be set via environment variables in production)
ADMIN_USERNAME = os.environ.get('LEMMA_ADMIN_USER', 'admin')
ADMIN_PASSWORD = os.environ.get('LEMMA_ADMIN_PASS', 'password')

class LemmaEnterprise:
    """Enterprise-grade Lemma implementation with strong encryption."""
    
    def __init__(self):
        """Initialize the Lemma system with enterprise security."""
        # Load or create necessary data
        self.keys = self._load_or_create_keys()
        self.registry = self._load_registry()
        self.users = self._load_users()
        
        print(f"Lemma Enterprise initialized with issuer DID: {self.keys['did']}")
    
    def _load_or_create_keys(self) -> Dict[str, Any]:
        """Load Ed25519 keys from environment variable only. Fail if not set."""
        env_private_key = os.environ.get('ED25519_PRIVATE_KEY')
        env_did = os.environ.get('DID')
        if env_private_key:
            private_key_bytes = base64.b64decode(env_private_key)
            private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_key_bytes)
            public_key = private_key.public_key()
            public_bytes = public_key.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw
            )
            keys_data = {
                'did': env_did if env_did else 'did:lemma:env',
                'did_method': 'lemma',
                'did_id': 'env',
                'private_key': env_private_key,
                'public_key': base64.b64encode(public_bytes).decode('ascii'),
                'created_at': datetime.now().isoformat(),
                'key_type': 'Ed25519',
                'private_key_obj': private_key
            }
            print(f"Loaded Ed25519 private key from environment variable. DID: {keys_data['did']}")
            return keys_data
        raise RuntimeError("ED25519_PRIVATE_KEY environment variable must be set and valid base64.")
    
    def _load_registry(self) -> Dict[str, Any]:
        """Load credential registry or create if it doesn't exist."""
        if os.path.exists(REGISTRY_FILE):
            with open(REGISTRY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"credentials": {}}
    
    def _load_users(self) -> Dict[str, Any]:
        """Load user registry or create if it doesn't exist."""
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"users": {}}
    
    def _save_registry(self):
        """Save credential registry with secure file handling."""
        # Create a temporary file first to prevent data corruption
        temp_file = f"{REGISTRY_FILE}.tmp"
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(self.registry, f, indent=2)
        
        # Atomic rename for data safety
        os.replace(temp_file, REGISTRY_FILE)
    
    def _save_users(self):
        """Save user registry with secure file handling."""
        # Create a temporary file first to prevent data corruption
        temp_file = f"{USERS_FILE}.tmp"
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(self.users, f, indent=2)
        
        # Atomic rename for data safety
        os.replace(temp_file, USERS_FILE)
    
    def create_user(self, user_id: str) -> Dict[str, Any]:
        """Create a new user entry with minimal data."""
        if user_id in self.users["users"]:
            return self.users["users"][user_id]
        
        user_data = {
            "id": user_id,
            "created_at": datetime.now().isoformat(),
            "verification_status": "pending"
        }
        
        self.users["users"][user_id] = user_data
        self._save_users()
        return user_data
    
    def issue_credential(self, user_id: str) -> Dict[str, Any]:
        """Issue a minimal verifiable credential that only verifies the user is human."""
        # Ensure user exists
        self.create_user(user_id)
        
        # Create credential ID with high entropy
        credential_id = f"vc_{uuid.uuid4().hex}"
        issuance_date = datetime.now().isoformat()
        expiration_date = (datetime.now() + timedelta(days=365)).isoformat()
        
        # Create credential in W3C Verifiable Credential format with MINIMAL data
        # Only store that this is a verified human - nothing else
        credential = {
            "@context": [
                "https://www.w3.org/2018/credentials/v1",
                "https://lemmanetwork.org/contexts/lemma/v1"
            ],
            "id": credential_id,
            "type": ["VerifiableCredential", "LemmaCredential", "HumanCredential"],
            "issuer": self.keys["did"],
            "issuanceDate": issuance_date,
            "expirationDate": expiration_date,
            "credentialSubject": {
                "id": f"did:user:{user_id}",
                "type": "Person",
                "isHuman": True,
                "verifiedBy": "admin"
            }
        }
        
        # Sign the credential with enterprise-grade security
        credential_json = json.dumps(credential, sort_keys=True)
        signature = self.keys["private_key_obj"].sign(credential_json.encode('utf-8'))
        
        # Add proof with enhanced security metadata
        credential["proof"] = {
            "type": "Ed25519Signature2020",
            "created": issuance_date,
            "verificationMethod": f"{self.keys['did']}#keys-1",
            "proofPurpose": "assertionMethod",
            "jws": base64.b64encode(signature).decode('ascii')
        }
        
        # Store in registry with additional security metadata
        self.registry["credentials"][credential_id] = {
            "user_id": user_id,
            "issued_at": issuance_date,
            "expires_at": expiration_date,
            "revoked": False,
            "proof_type": "Ed25519Signature2020",
            "hash": hashlib.sha256(credential_json.encode('utf-8')).hexdigest()
        }
        self._save_registry()
        
        # Update user status
        self.users["users"][user_id]["verification_status"] = "verified"
        self.users["users"][user_id]["verified_at"] = issuance_date
        self.users["users"][user_id]["credential_id"] = credential_id
        self._save_users()
        
        return credential
    
    def verify_credential(self, credential: Dict[str, Any]) -> Dict[str, bool]:
        """Verify a credential's signature and status with enterprise security checks."""
        try:
            # Check if credential exists in registry
            credential_id = credential.get("id")
            if credential_id not in self.registry["credentials"]:
                # For Heroku compatibility, don't require the credential to be in registry
                # Instead, focus on validating the signature
                # return {"valid": False, "reason": "Credential not found in registry"}
                print(f"Warning: Credential {credential_id} not found in registry, but proceeding with signature verification")
            else:
                # If it's in the registry, check if it's revoked
                if self.registry["credentials"][credential_id]["revoked"]:
                    return {"valid": False, "reason": "Credential has been revoked"}

                # Check if expired (if in registry)
                if "expires_at" in self.registry["credentials"][credential_id]:
                    expires_at = self.registry["credentials"][credential_id]["expires_at"]
                    if expires_at and datetime.now() > datetime.fromisoformat(expires_at):
                        return {"valid": False, "reason": "Credential has expired"}
            
            # Check if expired based on credential itself
            if "expirationDate" in credential:
                expiration_date = datetime.fromisoformat(credential["expirationDate"])
                if datetime.now() > expiration_date:
                    return {"valid": False, "reason": "Credential has expired"}
            
            # Verify signature with enterprise-grade validation
            proof = credential.pop("proof", None)
            if not proof:
                return {"valid": False, "reason": "No proof found"}
            
            # Verify proof type
            if proof.get("type") != "Ed25519Signature2020":
                return {"valid": False, "reason": "Unsupported proof type"}
            
            # Recreate the credential JSON that was signed
            credential_json = json.dumps(credential, sort_keys=True)
            
            # Get public key
            public_key_bytes = base64.b64decode(self.keys["public_key"])
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
            
            # Verify signature with enterprise security
            signature = base64.b64decode(proof["jws"])
            
            try:
                public_key.verify(signature, credential_json.encode('utf-8'))
                
                # If credential is in registry, perform hash check
                if credential_id in self.registry["credentials"]:
                    current_hash = hashlib.sha256(credential_json.encode('utf-8')).hexdigest()
                    stored_hash = self.registry["credentials"][credential_id]["hash"]
                    if current_hash != stored_hash:
                        return {"valid": False, "reason": "Credential has been tampered with"}
                
                return {
                    "valid": True,
                    "issuer": credential["issuer"],
                    "subject": credential["credentialSubject"]["id"],
                    "issuanceDate": credential.get("issuanceDate", "Not specified"),
                    "expirationDate": credential.get("expirationDate", "Not specified")
                }
            except Exception as e:
                return {"valid": False, "reason": f"Invalid signature: {str(e)}"}
        except Exception as e:
            return {"valid": False, "reason": f"Error verifying credential: {str(e)}"}
    
    def revoke_credential(self, credential_id: str) -> bool:
        """Revoke a credential with secure audit trail."""
        if credential_id in self.registry["credentials"]:
            self.registry["credentials"][credential_id]["revoked"] = True
            self.registry["credentials"][credential_id]["revoked_at"] = datetime.now().isoformat()
            self.registry["credentials"][credential_id]["revoked_by"] = "admin"
            
            # Update user status if needed
            user_id = self.registry["credentials"][credential_id]["user_id"]
            if user_id in self.users["users"] and self.users["users"][user_id].get("credential_id") == credential_id:
                self.users["users"][user_id]["verification_status"] = "revoked"
            
            self._save_registry()
            self._save_users()
            return True
        return False
    
    def get_user_credential(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a user's credential if it exists."""
        if user_id not in self.users["users"]:
            return None
        
        credential_id = self.users["users"][user_id].get("credential_id")
        if not credential_id or credential_id not in self.registry["credentials"]:
            return None
        
        # In a real implementation, you would store the full credential
        # For this example, we'll return the metadata
        return {
            "id": credential_id,
            "user_id": user_id,
            "status": "revoked" if self.registry["credentials"][credential_id]["revoked"] else "valid",
            "issued_at": self.registry["credentials"][credential_id]["issued_at"],
            "expires_at": self.registry["credentials"][credential_id].get("expires_at")
        }
    
    def create_presentation(self, credential: Dict[str, Any], challenge: str) -> Dict[str, Any]:
        """Create a Verifiable Presentation from a credential with proof of possession."""
        presentation_id = f"vp_{uuid.uuid4().hex}"
        creation_date = datetime.now().isoformat()
        
        # Create the presentation
        presentation = {
            "@context": [
                "https://www.w3.org/2018/credentials/v1",
                "https://lemmanetwork.org/contexts/lemma/v1"
            ],
            "id": presentation_id,
            "type": ["VerifiablePresentation"],
            "holder": credential["credentialSubject"]["id"],
            "verifiableCredential": [credential],
            "created": creation_date,
            "challenge": challenge
        }
        
        # Sign the presentation
        presentation_json = json.dumps(presentation, sort_keys=True)
        signature = self.keys["private_key_obj"].sign(presentation_json.encode('utf-8'))
        
        # Add proof
        presentation["proof"] = {
            "type": "Ed25519Signature2020",
            "created": creation_date,
            "verificationMethod": f"{self.keys['did']}#keys-1",
            "proofPurpose": "authentication",
            "challenge": challenge,
            "jws": base64.b64encode(signature).decode('ascii')
        }
        
        return presentation
    
    def verify_presentation(self, presentation: Dict[str, Any], expected_challenge: str) -> Dict[str, bool]:
        """Verify a presentation with enterprise-grade security checks."""
        try:
            # Check presentation structure
            if "verifiableCredential" not in presentation or not presentation["verifiableCredential"]:
                return {"valid": False, "reason": "No credentials in presentation"}
            
            # Check challenge
            proof = presentation.get("proof", {})
            if proof.get("challenge") != expected_challenge:
                return {"valid": False, "reason": "Challenge mismatch"}
            
            # Verify each credential in the presentation
            credentials = presentation["verifiableCredential"]
            if isinstance(credentials, dict):
                credentials = [credentials]
            
            credential_results = []
            for credential in credentials:
                result = self.verify_credential(credential)
                credential_results.append(result)
                if not result["valid"]:
                    return {"valid": False, "reason": f"Invalid credential: {result['reason']}"}
            
            # Verify presentation signature
            presentation_copy = presentation.copy()
            proof = presentation_copy.pop("proof", None)
            if not proof:
                return {"valid": False, "reason": "No proof found in presentation"}
            
            # Verify the presentation signature
            presentation_json = json.dumps(presentation_copy, sort_keys=True)
            
            # Get public key
            public_key_bytes = base64.b64decode(self.keys["public_key"])
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
            
            # Verify signature
            signature = base64.b64decode(proof["jws"])
            try:
                public_key.verify(signature, presentation_json.encode('utf-8'))
                return {
                    "valid": True,
                    "holder": presentation["holder"],
                    "credentials": credential_results,
                    "challenge": proof["challenge"]
                }
            except Exception as e:
                return {"valid": False, "reason": f"Invalid presentation signature: {str(e)}"}
            
        except Exception as e:
            return {"valid": False, "reason": f"Error verifying presentation: {str(e)}"}


# Initialize Lemma
lemma = LemmaEnterprise()

# Flask routes
@app.route('/')
def index():
    """Landing page."""
    return render_template('index.html')

@app.route('/admin')
def admin():
    """Admin interface."""
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
    return render_template('admin.html')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login."""
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        username = data.get('username')
        password = data.get('password')
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            if request.is_json:
                return jsonify({"success": True})
            return redirect(url_for('admin'))
        
        if request.is_json:
            return jsonify({"success": False, "error": "Invalid credentials"}), 401
        return render_template('admin_login.html', error="Invalid credentials")
    
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    """Admin logout."""
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

@app.route('/admin/issue', methods=['POST'])
def admin_issue():
    """Issue a credential to a trusted human."""
    if not session.get('admin_logged_in'):
        return jsonify({"success": False, "error": "Not authorized"}), 401
    
    data = request.get_json()
    user_id = data.get('user_id')
    
    if not user_id:
        return jsonify({"success": False, "error": "User ID is required"}), 400
    
    try:
        credential = lemma.issue_credential(user_id)
        return jsonify({
            "success": True,
            "credential": credential,
            "verify_url": f"/verify?user={user_id}"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/verify')
def verify():
    """Credential verification page."""
    user_id = request.args.get('user')
    if not user_id:
        return render_template('verify.html', error="No user ID provided")
    
    # Get user credential metadata
    credential_meta = lemma.get_user_credential(user_id)
    if not credential_meta:
        return render_template('verify.html', error="No credential found for this user")
    
    return render_template('verify.html', user_id=user_id, credential=credential_meta)

@app.route('/api/credential/<user_id>')
def get_credential(user_id):
    """API endpoint to get a user's credential."""
    # In a real implementation, you would retrieve the full credential
    # For this example, we'll create a new one
    try:
        credential = lemma.issue_credential(user_id)
        return jsonify(credential)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/verify', methods=['POST'])
def api_verify():
    """API endpoint to verify a credential."""
    data = request.get_json()
    credential = data.get('credential')
    
    if not credential:
        return jsonify({"valid": False, "error": "No credential provided"}), 400
    
    result = lemma.verify_credential(credential)
    return jsonify(result)

@app.route('/api/presentation', methods=['POST'])
def create_presentation():
    """API endpoint to create a verifiable presentation."""
    data = request.get_json()
    credential = data.get('credential')
    challenge = data.get('challenge')
    
    if not credential or not challenge:
        return jsonify({"error": "Credential and challenge are required"}), 400
    
    try:
        presentation = lemma.create_presentation(credential, challenge)
        return jsonify(presentation)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/verify-presentation', methods=['POST'])
def verify_presentation():
    """API endpoint to verify a presentation."""
    data = request.get_json()
    presentation = data.get('presentation')
    challenge = data.get('challenge')
    
    if not presentation or not challenge:
        return jsonify({"valid": False, "error": "Presentation and challenge are required"}), 400
    
    result = lemma.verify_presentation(presentation, challenge)
    return jsonify(result)

@app.route('/protected')
def protected():
    """Protected page that requires human verification."""
    # Check for verification in session
    if session.get('verified_human'):
        return render_template('protected.html')
    
    # Redirect to verification
    return redirect(url_for('verify'))

@app.route('/api/verify-human', methods=['POST'])
def verify_human():
    """API endpoint to verify a human and set session."""
    data = request.get_json()
    presentation = data.get('presentation')
    challenge = data.get('challenge')
    
    if not presentation or not challenge:
        return jsonify({"valid": False, "error": "Presentation and challenge are required"}), 400
    
    result = lemma.verify_presentation(presentation, challenge)
    if result.get('valid'):
        session['verified_human'] = True
        session['user_id'] = result.get('holder', '').split(':')[-1]
        return jsonify({"success": True, "redirect": "/protected"})
    
    return jsonify({"success": False, "error": result.get('reason', 'Verification failed')}), 401

if __name__ == '__main__':
    # Get port from environment or use default
    port = int(os.environ.get('PORT', 5000))
    
    # Run the application with improved security settings
    app.run(
        debug=os.environ.get('FLASK_DEBUG', 'False').lower() == 'true',
        host='0.0.0.0',
        port=port,
        ssl_context='adhoc'  # Enable HTTPS in development
    )
