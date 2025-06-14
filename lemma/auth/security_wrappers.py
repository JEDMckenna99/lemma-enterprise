"""
🔒 SECURITY WRAPPERS FOR HIGH-SECURITY PARTNERS
==============================================
Implements mTLS and timestamp-HMAC authentication for SOC 2 Type II compliance
"""

import os
import json
import hmac
import hashlib
import time
import ssl
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple, Any
from flask import request, current_app, g
from functools import wraps
import logging
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
import base64

logger = logging.getLogger(__name__)

class mTLSValidator:
    """
    Mutual TLS certificate validation for high-security partners.
    
    Validates client certificates against a trusted certificate authority
    and maintains certificate revocation checking.
    """
    
    def __init__(self, ca_cert_path: str = None, crl_path: str = None):
        self.ca_cert_path = ca_cert_path or os.environ.get('LEMMA_CA_CERT_PATH')
        self.crl_path = crl_path or os.environ.get('LEMMA_CRL_PATH')
        self.trusted_ca = None
        self.revoked_certs = set()
        
        if self.ca_cert_path:
            self._load_ca_certificate()
        if self.crl_path:
            self._load_certificate_revocation_list()
    
    def _load_ca_certificate(self):
        """Load the trusted CA certificate."""
        try:
            with open(self.ca_cert_path, 'rb') as f:
                cert_data = f.read()
            
            # Try PEM format first
            try:
                self.trusted_ca = x509.load_pem_x509_certificate(cert_data)
            except:
                # Try DER format
                self.trusted_ca = x509.load_der_x509_certificate(cert_data)
            
            logger.info(f"Loaded trusted CA certificate: {self.trusted_ca.subject}")
        except Exception as e:
            logger.error(f"Failed to load CA certificate: {e}")
    
    def _load_certificate_revocation_list(self):
        """Load certificate revocation list."""
        try:
            with open(self.crl_path, 'rb') as f:
                crl_data = f.read()
            
            # Try PEM format first
            try:
                crl = x509.load_pem_x509_crl(crl_data)
            except:
                # Try DER format
                crl = x509.load_der_x509_crl(crl_data)
            
            # Extract revoked certificate serial numbers
            for revoked_cert in crl:
                self.revoked_certs.add(revoked_cert.serial_number)
            
            logger.info(f"Loaded CRL with {len(self.revoked_certs)} revoked certificates")
        except Exception as e:
            logger.error(f"Failed to load CRL: {e}")
    
    def validate_client_certificate(self, cert_pem: str) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Validate a client certificate against the trusted CA.
        
        Returns:
            Tuple of (is_valid, error_message, cert_info)
        """
        try:
            # Parse the certificate
            cert_bytes = cert_pem.encode() if isinstance(cert_pem, str) else cert_pem
            cert = x509.load_pem_x509_certificate(cert_bytes)
            
            # Check if we have a trusted CA
            if not self.trusted_ca:
                return False, "No trusted CA configured", None
            
            # Verify certificate chain
            try:
                # In production, you would do full chain validation
                # This is a simplified version for demonstration
                public_key = self.trusted_ca.public_key()
                public_key.verify(
                    cert.signature,
                    cert.tbs_certificate_bytes,
                    padding.PKCS1v15(),
                    cert.signature_hash_algorithm
                )
            except Exception as e:
                return False, f"Certificate signature verification failed: {e}", None
            
            # Check validity period
            now = datetime.now(timezone.utc)
            if now < cert.not_valid_before:
                return False, "Certificate not yet valid", None
            if now > cert.not_valid_after:
                return False, "Certificate has expired", None
            
            # Check revocation status
            if cert.serial_number in self.revoked_certs:
                return False, "Certificate has been revoked", None
            
            # Extract certificate information
            cert_info = {
                "subject": str(cert.subject),
                "issuer": str(cert.issuer),
                "serial_number": str(cert.serial_number),
                "not_valid_before": cert.not_valid_before.isoformat(),
                "not_valid_after": cert.not_valid_after.isoformat(),
                "fingerprint": cert.fingerprint(hashes.SHA256()).hex()
            }
            
            logger.info(f"Client certificate validated: {cert_info['subject']}")
            return True, None, cert_info
            
        except Exception as e:
            logger.error(f"Certificate validation error: {e}")
            return False, f"Certificate validation error: {e}", None

class HMACTimestampValidator:
    """
    HMAC-SHA256 with timestamp validation for API requests.
    
    Provides cryptographic verification of request integrity and authenticity
    with replay attack protection via timestamp validation.
    """
    
    def __init__(self, shared_secrets: Dict[str, str] = None, window_seconds: int = 300):
        """
        Initialize HMAC validator.
        
        Args:
            shared_secrets: Mapping of partner_id -> shared_secret
            window_seconds: Time window for timestamp validation (default 5 minutes)
        """
        self.shared_secrets = shared_secrets or {}
        self.window_seconds = window_seconds
        self._load_shared_secrets()
    
    def _load_shared_secrets(self):
        """Load shared secrets from secure storage or environment."""
        # In production, load from secure key management system
        secrets_file = os.environ.get('LEMMA_HMAC_SECRETS_FILE')
        if secrets_file and os.path.exists(secrets_file):
            try:
                with open(secrets_file, 'r') as f:
                    stored_secrets = json.load(f)
                self.shared_secrets.update(stored_secrets)
                logger.info(f"Loaded {len(stored_secrets)} HMAC shared secrets")
            except Exception as e:
                logger.error(f"Failed to load HMAC secrets: {e}")
    
    def generate_hmac_signature(self, partner_id: str, timestamp: int, 
                               method: str, path: str, body: bytes = b'') -> str:
        """
        Generate HMAC signature for a request.
        
        Args:
            partner_id: Partner identifier
            timestamp: Unix timestamp
            method: HTTP method
            path: Request path
            body: Request body
            
        Returns:
            Base64-encoded HMAC signature
        """
        shared_secret = self.shared_secrets.get(partner_id)
        if not shared_secret:
            raise ValueError(f"No shared secret configured for partner: {partner_id}")
        
        # Create string to sign
        string_to_sign = f"{method}\n{path}\n{timestamp}\n{partner_id}\n"
        if body:
            body_hash = hashlib.sha256(body).hexdigest()
            string_to_sign += body_hash
        
        # Generate HMAC
        signature = hmac.new(
            shared_secret.encode(),
            string_to_sign.encode(),
            hashlib.sha256
        ).digest()
        
        return base64.b64encode(signature).decode()
    
    def validate_hmac_signature(self, partner_id: str, timestamp: int, method: str,
                               path: str, body: bytes, provided_signature: str) -> Tuple[bool, Optional[str]]:
        """
        Validate HMAC signature for a request.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Check timestamp window
            current_time = int(time.time())
            if abs(current_time - timestamp) > self.window_seconds:
                return False, f"Timestamp outside acceptable window ({self.window_seconds}s)"
            
            # Generate expected signature
            expected_signature = self.generate_hmac_signature(
                partner_id, timestamp, method, path, body
            )
            
            # Compare signatures (constant time)
            if not hmac.compare_digest(expected_signature, provided_signature):
                return False, "HMAC signature verification failed"
            
            return True, None
            
        except Exception as e:
            logger.error(f"HMAC validation error: {e}")
            return False, f"HMAC validation error: {e}"

def require_mtls(f):
    """
    Decorator to require mutual TLS authentication.
    
    Validates client certificate against trusted CA and stores
    certificate information in Flask's g object.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Skip in test environment
        if current_app.config.get('TESTING', False):
            return f(*args, **kwargs)
        
        # Get client certificate from environment or headers
        # This depends on your proxy/load balancer configuration
        client_cert = None
        
        # Check for certificate in headers (set by reverse proxy)
        cert_header = request.headers.get('X-Client-Certificate')
        if cert_header:
            try:
                # Certificate might be URL-encoded or base64-encoded
                client_cert = base64.b64decode(cert_header).decode()
            except:
                client_cert = cert_header
        
        # Check for certificate in SSL context (direct connection)
        if not client_cert and hasattr(request, 'environ'):
            ssl_cert = request.environ.get('SSL_CLIENT_CERT')
            if ssl_cert:
                client_cert = ssl_cert
        
        if not client_cert:
            logger.warning(f"mTLS required but no client certificate provided from {request.remote_addr}")
            return {"error": "Client certificate required for mTLS authentication"}, 400
        
        # Validate certificate
        validator = mTLSValidator()
        is_valid, error_msg, cert_info = validator.validate_client_certificate(client_cert)
        
        if not is_valid:
            logger.warning(f"mTLS validation failed from {request.remote_addr}: {error_msg}")
            return {"error": f"Client certificate validation failed: {error_msg}"}, 403
        
        # Store certificate info for use in the endpoint
        g.client_cert_info = cert_info
        g.mtls_authenticated = True
        
        logger.info(f"mTLS authentication successful: {cert_info['subject']}")
        return f(*args, **kwargs)
    
    return decorated_function

def require_hmac_auth(f):
    """
    Decorator to require HMAC-SHA256 timestamp authentication.
    
    Validates HMAC signature and timestamp to prevent replay attacks.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Skip in test environment
        if current_app.config.get('TESTING', False):
            return f(*args, **kwargs)
        
        # Extract HMAC headers
        partner_id = request.headers.get('X-Partner-ID')
        timestamp_str = request.headers.get('X-Timestamp')
        signature = request.headers.get('X-Signature')
        
        if not all([partner_id, timestamp_str, signature]):
            return {
                "error": "HMAC authentication requires X-Partner-ID, X-Timestamp, and X-Signature headers"
            }, 400
        
        try:
            timestamp = int(timestamp_str)
        except ValueError:
            return {"error": "Invalid timestamp format"}, 400
        
        # Get request body
        body = request.get_data()
        
        # Validate HMAC
        validator = HMACTimestampValidator()
        is_valid, error_msg = validator.validate_hmac_signature(
            partner_id, timestamp, request.method, request.path, body, signature
        )
        
        if not is_valid:
            logger.warning(f"HMAC validation failed from {request.remote_addr}: {error_msg}")
            return {"error": f"HMAC authentication failed: {error_msg}"}, 403
        
        # Store authentication info
        g.partner_id = partner_id
        g.hmac_authenticated = True
        g.auth_timestamp = timestamp
        
        logger.info(f"HMAC authentication successful for partner: {partner_id}")
        return f(*args, **kwargs)
    
    return decorated_function

def require_high_security(f):
    """
    Decorator that requires BOTH mTLS AND HMAC authentication.
    
    For the highest security partners that require multiple authentication factors.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Apply both security checks
        mtls_result = require_mtls(lambda: None)()
        if isinstance(mtls_result, tuple) and len(mtls_result) == 2:
            return mtls_result  # Return error response
        
        hmac_result = require_hmac_auth(lambda: None)()
        if isinstance(hmac_result, tuple) and len(hmac_result) == 2:
            return hmac_result  # Return error response
        
        # Both checks passed
        g.high_security_authenticated = True
        logger.info(f"High security authentication successful: mTLS + HMAC")
        return f(*args, **kwargs)
    
    return decorated_function

# Utility functions for partners to generate HMAC signatures

def generate_partner_hmac(partner_id: str, shared_secret: str, method: str, 
                         path: str, body: bytes = b'') -> Dict[str, str]:
    """
    Generate HMAC headers for partner API requests.
    
    Returns:
        Dictionary with X-Partner-ID, X-Timestamp, and X-Signature headers
    """
    timestamp = int(time.time())
    
    validator = HMACTimestampValidator({partner_id: shared_secret})
    signature = validator.generate_hmac_signature(
        partner_id, timestamp, method, path, body
    )
    
    return {
        'X-Partner-ID': partner_id,
        'X-Timestamp': str(timestamp),
        'X-Signature': signature
    }

def validate_partner_certificate(cert_pem: str) -> Dict[str, Any]:
    """
    Utility function to validate a partner certificate.
    
    Returns:
        Certificate validation result and information
    """
    validator = mTLSValidator()
    is_valid, error_msg, cert_info = validator.validate_client_certificate(cert_pem)
    
    return {
        'valid': is_valid,
        'error': error_msg,
        'certificate_info': cert_info
    } 