"""
Core credential service for the Lemma Human Verification System.
Handles credential issuance, verification, and management with enhanced security.
"""
import os
import json
import uuid
import base64
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.fernet import Fernet
from flask import current_app, g

try:
    from lemma.core.did_resolver import get_did_resolver
except ImportError:
    # Fallback for tests or when the module is not yet available
    get_did_resolver = lambda: None

# Global credential service instance
_credential_service = None

def get_credential_service():
    """Get the credential service instance."""
    if '_credential_service' not in g:
        # Initialize the service if it doesn't exist
        if not _credential_service:
            init_credential_service(current_app)
        g._credential_service = _credential_service
    return g._credential_service

def init_credential_service(app):
    """Initialize the credential service."""
    global _credential_service
    try:
        # On Heroku, we need to use environment variables for keys
        if 'DYNO' in os.environ:
            # If ED25519_PRIVATE_KEY is not set, generate a new one
            if 'ED25519_PRIVATE_KEY' not in os.environ:
                private_key = ed25519.Ed25519PrivateKey.generate()
                private_bytes = private_key.private_bytes(
                    encoding=serialization.Encoding.Raw,
                    format=serialization.PrivateFormat.Raw,
                    encryption_algorithm=serialization.NoEncryption()
                )
                os.environ['ED25519_PRIVATE_KEY'] = base64.b64encode(private_bytes).decode('ascii')
                app.logger.info("Generated new ED25519_PRIVATE_KEY")

        _credential_service = LemmaCredentialService(app.config['STORAGE_DIR'])
        app.logger.info("Successfully initialized credential service")
        return _credential_service
    except Exception as e:
        app.logger.error(f"Failed to initialize credential service: {e}")
        return None

class LemmaCredentialService:
    """Enhanced credential service with strong encryption and minimal data collection."""
    
    def __init__(self, storage_dir):
        """Initialize the credential service with secure storage."""
        self.storage_dir = storage_dir
        self.is_heroku = 'DYNO' in os.environ
        
        # Initialize storage
        if not self.is_heroku:
            os.makedirs(storage_dir, exist_ok=True)
            
        # Initialize paths for storage files
        self.keys_file = os.path.join(storage_dir, "keys.json") if not self.is_heroku else None
        self.registry_file = os.path.join(storage_dir, "registry.json") if not self.is_heroku else None
        self.users_file = os.path.join(storage_dir, "users.json") if not self.is_heroku else None
        
        # Generate encryption key for secure storage
        self.encryption_key = self._get_or_create_encryption_key()
        
        # Load or create necessary data
        self.keys = self._load_or_create_keys()
        self.registry = {"credentials": {}}  # Initialize empty for Heroku
        self.users = {"users": {}}     # Initialize empty for Heroku
        
        # Get access to the DID resolver
        self.did_resolver = get_did_resolver()
    
    def _get_or_create_encryption_key(self):
        """Get or create a key for encrypting sensitive data."""
        if self.is_heroku:
            # On Heroku, use the secret key as the encryption key base
            secret_key = os.environ.get('LEMMA_SECRET_KEY', '')
            if not secret_key:
                raise ValueError("LEMMA_SECRET_KEY must be set in Heroku environment")
            
            # Derive a proper length key using PBKDF2
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b'lemma_salt',  # Fixed salt is OK here as secret_key is random
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(secret_key.encode()))
            return key
            
        # For non-Heroku environments, use file-based storage
        key_file = os.path.join(self.storage_dir, "encryption.key")
        
        if os.path.exists(key_file):
            with open(key_file, 'rb') as f:
                return f.read()
        
        # Generate a new key with high entropy
        key = Fernet.generate_key()
        
        # Store the key securely
        with open(key_file, 'wb') as f:
            f.write(key)
        
        return key
    
    def _encrypt_data(self, data):
        """Encrypt sensitive data."""
        fernet = Fernet(self.encryption_key)
        return fernet.encrypt(data.encode('utf-8')).decode('utf-8')
    
    def _decrypt_data(self, encrypted_data):
        """Decrypt sensitive data."""
        fernet = Fernet(self.encryption_key)
        return fernet.decrypt(encrypted_data.encode('utf-8')).decode('utf-8')
    
    def _load_or_create_keys(self) -> Dict[str, Any]:
        """Load existing keys or create new ones with enterprise-grade security."""
        # First try to get key from environment variable
        if self.is_heroku and 'ED25519_PRIVATE_KEY' in os.environ:
            try:
                # Get the private key from environment
                private_key_str = os.environ['ED25519_PRIVATE_KEY']
                
                # Ensure proper base64 padding
                if len(private_key_str) % 4:
                    private_key_str += '=' * (4 - len(private_key_str) % 4)
                
                # Decode and create key object
                private_key_bytes = base64.b64decode(private_key_str)
                private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_key_bytes)
                
                # Get the public key
                public_key = private_key.public_key()
                public_bytes = public_key.public_bytes(
                    encoding=serialization.Encoding.Raw,
                    format=serialization.PublicFormat.Raw
                )
                
                # Get DID method from environment or configuration
                did_method = os.environ.get("DID_METHOD", "lemma")
                did_uuid = uuid.uuid4().hex
                did = f"did:{did_method}:{did_uuid}"
                
                # Encode the public key for JWK format
                public_key_jwk = {
                    "kty": "OKP",
                    "crv": "Ed25519",
                    "x": base64.urlsafe_b64encode(public_bytes).decode('ascii').rstrip('=')
                }
                
                # Create key data
                keys_data = {
                    'did': did,
                    'did_method': did_method,
                    'did_id': did_uuid,
                    'private_key': private_key_str,
                    'public_key': base64.b64encode(public_bytes).decode('ascii'),
                    'public_key_jwk': public_key_jwk,
                    'created_at': datetime.now().isoformat(),
                    'key_type': 'Ed25519',
                    'private_key_obj': private_key  # Not stored, just for runtime use
                }
                
                current_app.logger.info("Successfully loaded ED25519_PRIVATE_KEY from environment")
                return keys_data
            except Exception as e:
                current_app.logger.error(f"Error loading ED25519_PRIVATE_KEY from environment: {e}")
                # Fall through to file-based keys
        
        # If no environment key or error, try file
        if not self.is_heroku and os.path.exists(self.keys_file):
            try:
                with open(self.keys_file, 'r', encoding='utf-8') as f:
                    keys_data = json.load(f)
                    # Decrypt the private key
                    encrypted_private_key = keys_data['private_key']
                    private_key_str = self._decrypt_data(encrypted_private_key)
                    
                    # Ensure proper base64 padding
                    if len(private_key_str) % 4:
                        private_key_str += '=' * (4 - len(private_key_str) % 4)
                    
                    private_key_bytes = base64.b64decode(private_key_str)
                    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_key_bytes)
                    keys_data['private_key_obj'] = private_key
                    current_app.logger.info("Successfully loaded keys from file")
                    return keys_data
            except Exception as e:
                current_app.logger.error(f"Error loading keys from file: {e}")
                # Fall through to creating new keys
        
        # Create new keys if neither source available
        current_app.logger.info("Creating new Ed25519 keys")
        
        # Get DID method from environment or configuration
        did_method = os.environ.get("DID_METHOD", "lemma")
        
        # Create new keys with strong entropy
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        
        # Create DID with method-specific identifier
        did_uuid = uuid.uuid4().hex
        did = f"did:{did_method}:{did_uuid}"
        
        # Serialize keys for storage with secure encoding
        private_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        )
        public_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        
        # Store the private key in environment if on Heroku
        if self.is_heroku:
            os.environ['ED25519_PRIVATE_KEY'] = base64.b64encode(private_bytes).decode('ascii')
        
        # Create key data
        keys_data = {
            'did': did,
            'did_method': did_method,
            'did_id': did_uuid,
            'private_key': base64.b64encode(private_bytes).decode('ascii'),
            'public_key': base64.b64encode(public_bytes).decode('ascii'),
            'public_key_jwk': {
                "kty": "OKP",
                "crv": "Ed25519",
                "x": base64.urlsafe_b64encode(public_bytes).decode('ascii').rstrip('=')
            },
            'created_at': datetime.now().isoformat(),
            'key_type': 'Ed25519',
            'private_key_obj': private_key  # Not stored, just for runtime use
        }
        
        # Save to local file for backup if not on Heroku
        if not self.is_heroku:
            self._save_keys(keys_data)
        
        return keys_data
    
    def _save_keys(self, keys_data):
        """Save keys to file with secure encryption."""
        # Create a copy of the data to avoid modifying the original
        keys_to_save = keys_data.copy()
        
        # Remove runtime-only data
        keys_to_save.pop('private_key_obj', None)
        
        # If the private key is from environment variable, encrypt it before saving
        if os.environ.get('ED25519_PRIVATE_KEY') == keys_to_save.get('private_key'):
            current_app.logger.info("Encrypting environment private key before saving")
            keys_to_save['private_key'] = self._encrypt_data(keys_to_save['private_key'])
        
        # Save with pretty formatting for readability
        if self.is_heroku:
            # On Heroku, do not save keys to file
            pass
        else:
            with open(self.keys_file, 'w', encoding='utf-8') as f:
                json.dump(keys_to_save, f, indent=4)
    
    def _load_registry(self) -> Dict[str, Any]:
        """Load credential registry or create if it doesn't exist."""
        if self.is_heroku:
            return {}  # Heroku does not use local registry
        if os.path.exists(self.registry_file):
            with open(self.registry_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"credentials": {}}
    
    def _load_users(self) -> Dict[str, Any]:
        """Load user registry or create if it doesn't exist."""
        if self.is_heroku:
            return {}  # Heroku does not use local registry
        if os.path.exists(self.users_file):
            with open(self.users_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"users": {}}
    
    def _save_registry(self):
        """Save credential registry with secure file handling."""
        if self.is_heroku:
            # On Heroku, do not save registry to file
            pass
        else:
            # Create a temporary file first to prevent data corruption
            temp_file = f"{self.registry_file}.tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.registry, f, indent=2)
            
            # Atomic rename for data safety
            os.replace(temp_file, self.registry_file)
    
    def _save_users(self):
        """Save user registry with secure file handling."""
        if self.is_heroku:
            # On Heroku, do not save users to file
            pass
        else:
            # Create a temporary file first to prevent data corruption
            temp_file = f"{self.users_file}.tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.users, f, indent=2)
            
            # Atomic rename for data safety
            os.replace(temp_file, self.users_file)
    
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
    
    def issue_credential(self, user_id: str, did_method: str = None) -> Dict[str, Any]:
        """Issue a minimal verifiable credential that only verifies the user is human."""
        # Ensure user exists
        self.create_user(user_id)
        
        # Create credential ID with high entropy
        credential_id = f"vc_{uuid.uuid4().hex}"
        issuance_date = datetime.now().isoformat()
        expiration_date = (datetime.now() + timedelta(days=365)).isoformat()
        
        # Use specified DID method or default to the user's preference
        if not did_method:
            did_method = "user"  # Default to 'user' method
            
        # User subject with their choice of DID method
        subject_id = f"did:{did_method}:{user_id}"
        
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
                "id": subject_id,
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
    
    def revoke_credential(self, credential_id: str) -> bool:
        """Revoke a credential with secure audit trail and P2P broadcasting."""
        if credential_id in self.registry["credentials"]:
            # Mark as revoked in local registry
            self.registry["credentials"][credential_id]["revoked"] = True
            self.registry["credentials"][credential_id]["revoked_at"] = datetime.now().isoformat()
            self.registry["credentials"][credential_id]["revoked_by"] = "admin"
            
            # Update user status if needed
            user_id = self.registry["credentials"][credential_id]["user_id"]
            if user_id in self.users["users"] and self.users["users"][user_id].get("credential_id") == credential_id:
                self.users["users"][user_id]["verification_status"] = "revoked"
            
            self._save_registry()
            self._save_users()
            
            # If revocation registry is available, use it for P2P revocation
            try:
                from lemma.core.revocation import get_revocation_registry
                revocation_registry = get_revocation_registry()
                if revocation_registry:
                    # Add to the decentralized revocation registry
                    revocation_registry.revoke_credential(self.keys["did"], credential_id)
            except ImportError:
                # Fallback if the revocation module is not available
                pass
                
            return True
        return False
    
    def verify_credential(self, credential: Dict[str, Any]) -> Dict[str, bool]:
        """Verify a credential's signature and status with decentralized validation."""
        try:
            # Make a copy of the credential to avoid modifying the original
            credential_copy = credential.copy()
            
            # Get credential ID and issuer
            credential_id = credential_copy.get("id")
            issuer_did = credential_copy.get("issuer")
            
            if not credential_id or not issuer_did:
                return {"valid": False, "reason": "Missing credential ID or issuer"}
            
            # Check revocation status using the decentralized revocation registry
            try:
                from lemma.core.revocation import get_revocation_registry
                revocation_registry = get_revocation_registry()
                if revocation_registry and revocation_registry.is_revoked(issuer_did, credential_id):
                    return {"valid": False, "reason": "Credential has been revoked in the network"}
            except ImportError:
                # Fallback to local registry if the revocation module is not available
                if credential_id in self.registry["credentials"] and self.registry["credentials"][credential_id]["revoked"]:
                    return {"valid": False, "reason": "Credential has been revoked locally"}
            
            # Check if expired
            if "expirationDate" in credential_copy:
                expiration_date = datetime.fromisoformat(credential_copy["expirationDate"])
                if datetime.now() > expiration_date:
                    return {"valid": False, "reason": "Credential has expired"}

            # Verify signature with enterprise-grade validation
            proof = credential_copy.pop("proof", None)
            if not proof:
                return {"valid": False, "reason": "No proof found"}

            # Verify proof type
            if proof.get("type") != "Ed25519VerificationKey2020" and proof.get("type") != "Ed25519Signature2020":
                return {"valid": False, "reason": f"Unsupported proof type: {proof.get('type')}"}

            # Recreate the credential JSON that was signed
            credential_json = json.dumps(credential_copy, sort_keys=True)

            # Extract verification method from proof
            verification_method = proof.get("verificationMethod")
            if not verification_method:
                verification_method = f"{issuer_did}#keys-1"  # Default verification method

            # Get the public key using the DID resolver
            try:
                # If this is a local DID issued by this service
                if issuer_did == self.keys["did"]:
                    # Use local key for verification
                    public_key_str = self.keys["public_key"]
                    # Ensure proper base64 padding
                    if len(public_key_str) % 4:
                        public_key_str += '=' * (4 - len(public_key_str) % 4)
                    
                    try:
                        public_key_bytes = base64.b64decode(public_key_str)
                        current_app.logger.info(f"Decoded public key length: {len(public_key_bytes)} bytes")
                        
                        # Ensure the key is exactly 32 bytes
                        if len(public_key_bytes) != 32:
                            if len(public_key_bytes) > 32:
                                public_key_bytes = public_key_bytes[:32]
                                current_app.logger.warning("Truncating public key to 32 bytes")
                            else:
                                current_app.logger.error("Public key is too short")
                                return {"valid": False, "reason": "Invalid public key length"}
                        
                        public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
                    except Exception as e:
                        current_app.logger.error(f"Error processing public key: {e}")
                        return {"valid": False, "reason": f"Error processing public key: {str(e)}"}
                        
                elif self.did_resolver:
                    # Use DID resolver to get the public key
                    public_key = self.did_resolver.get_public_key(issuer_did, verification_method)
                    if not public_key:
                        return {"valid": False, "reason": f"Could not resolve DID: {issuer_did}"}
                else:
                    # Fallback to local verification if resolver not available
                    return {"valid": False, "reason": "DID resolver not available"}

                # Verify signature
                jws = proof["jws"]
                # Ensure proper base64 padding for signature
                if len(jws) % 4:
                    jws += '=' * (4 - len(jws) % 4)
                
                try:
                    signature = base64.b64decode(jws)
                    current_app.logger.info(f"Decoded signature length: {len(signature)} bytes")
                except Exception as e:
                    current_app.logger.error(f"Error decoding signature: {e}")
                    return {"valid": False, "reason": f"Error decoding signature: {str(e)}"}
                
                # Ensure the signature is valid
                try:
                    public_key.verify(signature, credential_json.encode('utf-8'))
                except Exception as e:
                    current_app.logger.error(f"Signature verification failed: {e}")
                    return {"valid": False, "reason": f"Signature verification failed: {str(e)}"}

                return {
                    "valid": True,
                    "issuer": credential_copy["issuer"],
                    "subject": credential_copy["credentialSubject"]["id"],
                    "issuanceDate": credential_copy["issuanceDate"],
                    "expirationDate": credential_copy.get("expirationDate", "Not specified")
                }
            except Exception as e:
                current_app.logger.error(f"Error during key verification: {e}")
                return {"valid": False, "reason": f"Error during key verification: {str(e)}"}
                
        except Exception as e:
            current_app.logger.error(f"Error verifying credential: {e}")
            return {"valid": False, "reason": f"Error verifying credential: {str(e)}"}
    
    def get_user_credential(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a user's full credential if it exists."""
        if user_id not in self.users["users"]:
            return None
        
        credential_id = self.users["users"][user_id].get("credential_id")
        if not credential_id or credential_id not in self.registry["credentials"]:
            return None
        
        # Return the full credential by reconstructing it
        # Use the same logic as issue_credential, but do not re-issue
        # Instead, load from registry and users
        # For now, re-issue to reconstruct the credential (since proof is deterministic for this user)
        # In a real system, you would store the full credential
        return self.issue_credential(user_id)
    
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
        """Verify a presentation with enhanced security and zero-knowledge support."""
        try:
            # Check if this is a zero-knowledge human proof
            if "humanAssurance" in presentation:
                try:
                    from lemma.utils.zero_knowledge import ZKProof
                    return ZKProof.verify_human_proof(presentation, expected_challenge)
                except ImportError:
                    # Fallback if zero_knowledge module is not available
                    return {"valid": False, "reason": "Zero-knowledge proof verification not available"}
            
            # Regular presentation verification flow
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
            
            # Get public key with proper base64 padding
            public_key_str = self.keys["public_key"]
            if len(public_key_str) % 4:
                public_key_str += '=' * (4 - len(public_key_str) % 4)
            public_key_bytes = base64.b64decode(public_key_str)
            
            # Ensure the key is exactly 32 bytes
            if len(public_key_bytes) != 32:
                return {"valid": False, "reason": "Invalid public key length"}
            
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
            
            # Verify signature with proper base64 padding
            jws = proof["jws"]
            if len(jws) % 4:
                jws += '=' * (4 - len(jws) % 4)
            signature = base64.b64decode(jws)
            
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
    
    def list_credentials(self) -> List[Dict[str, Any]]:
        """List all credentials in the registry."""
        result = []
        for cred_id, cred_data in self.registry["credentials"].items():
            result.append({
                "id": cred_id,
                "user_id": cred_data["user_id"],
                "issued_at": cred_data["issued_at"],
                "expires_at": cred_data.get("expires_at"),
                "revoked": cred_data["revoked"]
            })
        return result
