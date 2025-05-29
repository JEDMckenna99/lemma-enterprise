"""
Lemma Cryptographic Security Enhancements - Server Side
Implements enhanced security validation and crypto operations
"""

import hashlib
import hmac
import time
import json
import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Tuple, Optional, List
from flask import request, current_app

logger = logging.getLogger(__name__)

class LemmaCryptoHardened:
    """Enhanced cryptographic operations and validations for Lemma"""
    
    # Security constants
    MIN_CHALLENGE_ENTROPY_BITS = 256  # 32 bytes
    MIN_TOKEN_ENTROPY_BITS = 256      # 32 bytes
    MAX_PRESENTATION_AGE_MINUTES = 5
    SUPPORTED_CRYPTO_VERSIONS = ['1.0', '2.0']
    
    @staticmethod
    def generate_secure_challenge() -> str:
        """Generate cryptographically secure 256-bit challenge"""
        challenge_bytes = secrets.token_bytes(32)  # 256 bits
        return challenge_bytes.hex()
    
    @staticmethod
    def generate_security_token() -> str:
        """Generate cryptographically secure 256-bit security token"""
        token_bytes = secrets.token_bytes(32)  # 256 bits
        return token_bytes.hex()
    
    @staticmethod
    def constant_time_compare(a: str, b: str) -> bool:
        """Constant-time string comparison to prevent timing attacks"""
        if not a or not b:
            return False
        return hmac.compare_digest(a.encode('utf-8'), b.encode('utf-8'))
    
    @staticmethod
    def validate_timestamp(timestamp_str: str, max_age_minutes: int = 5) -> Tuple[bool, str]:
        """
        Validate timestamp to prevent replay attacks
        
        Args:
            timestamp_str: ISO format timestamp string
            max_age_minutes: Maximum age in minutes
            
        Returns:
            Tuple of (is_valid, reason)
        """
        try:
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            
            # Check if timestamp is in the future (clock skew tolerance: 1 minute)
            if timestamp > now + timedelta(minutes=1):
                return False, "Timestamp is in the future"
            
            # Check if timestamp is too old
            age = now - timestamp
            if age > timedelta(minutes=max_age_minutes):
                return False, f"Timestamp too old (age: {age.total_seconds():.1f}s, max: {max_age_minutes}m)"
            
            return True, "Valid timestamp"
            
        except (ValueError, TypeError) as e:
            return False, f"Invalid timestamp format: {str(e)}"
    
    @staticmethod
    def validate_challenge_entropy(challenge: str) -> Tuple[bool, str]:
        """Validate challenge has sufficient entropy"""
        if not challenge:
            return False, "Challenge is empty"
        
        # Check length (64 hex chars = 32 bytes = 256 bits)
        if len(challenge) < 64:
            return False, f"Challenge insufficient entropy: {len(challenge)*4} bits < 256 bits required"
        
        # Check if hex format
        try:
            int(challenge, 16)
        except ValueError:
            return False, "Challenge is not valid hexadecimal"
        
        return True, "Challenge entropy sufficient"
    
    @staticmethod
    def validate_security_token(token: str) -> Tuple[bool, str]:
        """Validate security token entropy"""
        if not token:
            return False, "Security token is empty"
        
        # Check length (64 hex chars = 32 bytes = 256 bits)
        if len(token) < 64:
            return False, f"Security token insufficient entropy: {len(token)*4} bits < 256 bits required"
        
        # Check if hex format
        try:
            int(token, 16)
        except ValueError:
            return False, "Security token is not valid hexadecimal"
        
        return True, "Security token entropy sufficient"
    
    @staticmethod
    def validate_domain_binding(presentation_domain: str, request_host: str) -> Tuple[bool, str]:
        """Validate domain binding to prevent cross-site replay attacks"""
        if not presentation_domain:
            return False, "Domain binding missing"
        
        if not request_host:
            return False, "Request host missing"
        
        # Normalize domains (remove port numbers for comparison)
        presentation_domain = presentation_domain.split(':')[0].lower()
        request_host = request_host.split(':')[0].lower()
        
        if presentation_domain != request_host:
            return False, f"Domain mismatch: presentation={presentation_domain}, request={request_host}"
        
        return True, "Domain binding valid"
    
    @staticmethod
    def hash_presentation(presentation: Dict[str, Any]) -> str:
        """Create SHA-256 hash of presentation for integrity verification"""
        # Create canonical representation (sorted keys)
        canonical = json.dumps(presentation, sort_keys=True, separators=(',', ':'))
        
        # Hash with SHA-256
        hash_obj = hashlib.sha256(canonical.encode('utf-8'))
        return hash_obj.hexdigest()
    
    @staticmethod
    def validate_presentation_integrity(presentation: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate presentation integrity using hash"""
        proof = presentation.get('proof', {})
        provided_hash = proof.get('presentationHash')
        
        if not provided_hash:
            return False, "Presentation hash missing"
        
        # Remove hash from presentation and recalculate
        presentation_copy = json.loads(json.dumps(presentation))  # Deep copy
        if 'proof' in presentation_copy and 'presentationHash' in presentation_copy['proof']:
            del presentation_copy['proof']['presentationHash']
        
        computed_hash = LemmaCryptoHardened.hash_presentation(presentation_copy)
        
        if not LemmaCryptoHardened.constant_time_compare(provided_hash, computed_hash):
            return False, f"Presentation integrity check failed: provided={provided_hash[:16]}..., computed={computed_hash[:16]}..."
        
        return True, "Presentation integrity valid"
    
    @staticmethod
    def validate_enhanced_presentation(presentation: Dict[str, Any], 
                                     expected_challenge: str = None,
                                     request_host: str = None) -> Tuple[bool, List[str]]:
        """
        Comprehensive validation of enhanced presentation
        
        Args:
            presentation: The presentation to validate
            expected_challenge: Expected challenge value
            request_host: Host from the request
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        # Check basic structure
        if not isinstance(presentation, dict):
            errors.append("Presentation is not a dictionary")
            return False, errors
        
        proof = presentation.get('proof', {})
        if not proof:
            errors.append("Presentation proof missing")
            return False, errors
        
        # Validate crypto version
        crypto_version = proof.get('cryptoVersion', '1.0')
        if crypto_version not in LemmaCryptoHardened.SUPPORTED_CRYPTO_VERSIONS:
            errors.append(f"Unsupported crypto version: {crypto_version}")
        
        # Enhanced validations for v2.0
        if crypto_version == '2.0':
            # Validate timestamp
            timestamp = proof.get('created')
            if timestamp:
                is_valid, reason = LemmaCryptoHardened.validate_timestamp(timestamp)
                if not is_valid:
                    errors.append(f"Timestamp validation failed: {reason}")
            else:
                errors.append("Timestamp missing in v2.0 presentation")
            
            # Validate challenge entropy
            challenge = proof.get('challenge')
            if challenge:
                is_valid, reason = LemmaCryptoHardened.validate_challenge_entropy(challenge)
                if not is_valid:
                    errors.append(f"Challenge validation failed: {reason}")
                
                # Check expected challenge
                if expected_challenge and not LemmaCryptoHardened.constant_time_compare(challenge, expected_challenge):
                    errors.append("Challenge mismatch")
            else:
                errors.append("Challenge missing in v2.0 presentation")
            
            # Validate security token
            security_token = proof.get('securityToken')
            if security_token:
                is_valid, reason = LemmaCryptoHardened.validate_security_token(security_token)
                if not is_valid:
                    errors.append(f"Security token validation failed: {reason}")
            else:
                errors.append("Security token missing in v2.0 presentation")
            
            # Validate nonce
            nonce = proof.get('nonce')
            if nonce:
                is_valid, reason = LemmaCryptoHardened.validate_security_token(nonce)  # Same validation as security token
                if not is_valid:
                    errors.append(f"Nonce validation failed: {reason}")
            else:
                errors.append("Nonce missing in v2.0 presentation")
            
            # Validate domain binding
            domain = proof.get('domain')
            if domain and request_host:
                is_valid, reason = LemmaCryptoHardened.validate_domain_binding(domain, request_host)
                if not is_valid:
                    errors.append(f"Domain binding validation failed: {reason}")
            
            # Validate expiry
            expires_at = proof.get('expiresAt')
            if expires_at:
                try:
                    expiry_time = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                    if datetime.now(timezone.utc) > expiry_time:
                        errors.append("Presentation has expired")
                except (ValueError, TypeError):
                    errors.append("Invalid expiry timestamp format")
            
            # Validate presentation integrity
            if 'presentationHash' in proof:
                is_valid, reason = LemmaCryptoHardened.validate_presentation_integrity(presentation)
                if not is_valid:
                    errors.append(f"Integrity validation failed: {reason}")
        
        return len(errors) == 0, errors

class SecurityLogger:
    """Enhanced security event logging"""
    
    @staticmethod
    def log_security_event(event_type: str, data: Dict[str, Any] = None, level: str = 'INFO'):
        """Log security events with structured data"""
        
        if data is None:
            data = {}
        
        # Add request context if available
        if request:
            data.update({
                'ip_address': request.remote_addr,
                'user_agent': request.headers.get('User-Agent', ''),
                'request_path': request.path,
                'request_method': request.method,
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            })
        
        # Log with appropriate level
        log_entry = {
            'event_type': event_type,
            'data': data
        }
        
        log_message = f"[SECURITY] {event_type}: {json.dumps(data)}"
        
        if level == 'ERROR':
            logger.error(log_message)
        elif level == 'WARNING':
            logger.warning(log_message)
        else:
            logger.info(log_message)
        
        # For critical events, also log to security file
        critical_events = [
            'crypto_verification_failed',
            'replay_attack_detected',
            'timing_attack_detected', 
            'presentation_integrity_failed',
            'revoked_credential_used'
        ]
        
        if event_type in critical_events:
            SecurityLogger._log_to_security_file(log_entry)
    
    @staticmethod
    def _log_to_security_file(log_entry: Dict[str, Any]):
        """Log critical security events to dedicated security log file"""
        try:
            security_log_path = current_app.config.get('SECURITY_LOG_PATH', '/tmp/lemma_security.log')
            with open(security_log_path, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception as e:
            logger.error(f"Failed to write to security log: {e}")

class CryptoValidationMiddleware:
    """Middleware for crypto validation in requests"""
    
    @staticmethod
    def validate_request_crypto_headers(required_version: str = '2.0') -> Tuple[bool, str]:
        """Validate crypto-related request headers"""
        
        crypto_version = request.headers.get('X-Crypto-Version', '1.0')
        
        if crypto_version not in LemmaCryptoHardened.SUPPORTED_CRYPTO_VERSIONS:
            return False, f"Unsupported crypto version: {crypto_version}"
        
        if required_version and crypto_version != required_version:
            return False, f"Required crypto version {required_version}, got {crypto_version}"
        
        # For v2.0, validate additional headers
        if crypto_version == '2.0':
            presentation_hash = request.headers.get('X-Presentation-Hash')
            if not presentation_hash:
                return False, "X-Presentation-Hash header missing for crypto v2.0"
            
            # Validate hash format
            try:
                int(presentation_hash, 16)
                if len(presentation_hash) != 64:  # SHA-256 = 64 hex chars
                    return False, "Invalid presentation hash length"
            except ValueError:
                return False, "Invalid presentation hash format"
        
        return True, "Request crypto headers valid"

# Enhanced verification functions
def enhanced_verify_presentation(presentation: Dict[str, Any], 
                               challenge: str = None,
                               require_crypto_v2: bool = True) -> Dict[str, Any]:
    """
    Enhanced presentation verification with crypto hardening
    
    Args:
        presentation: The presentation to verify
        challenge: Expected challenge value
        require_crypto_v2: Whether to require crypto version 2.0
        
    Returns:
        Dict with verification results
    """
    
    start_time = time.time()
    result = {
        'valid': False,
        'crypto_valid': False,
        'errors': [],
        'crypto_version': '1.0',
        'security_level': 'basic'
    }
    
    try:
        # Extract crypto version
        proof = presentation.get('proof', {})
        crypto_version = proof.get('cryptoVersion', '1.0')
        result['crypto_version'] = crypto_version
        
        # Validate request headers
        if require_crypto_v2:
            headers_valid, header_error = CryptoValidationMiddleware.validate_request_crypto_headers('2.0')
            if not headers_valid:
                result['errors'].append(f"Request validation failed: {header_error}")
                SecurityLogger.log_security_event('crypto_header_validation_failed', {
                    'error': header_error,
                    'crypto_version': crypto_version
                }, 'WARNING')
                return result
        
        # Enhanced presentation validation
        request_host = request.headers.get('Host', '') if request else ''
        is_valid, validation_errors = LemmaCryptoHardened.validate_enhanced_presentation(
            presentation, challenge, request_host
        )
        
        if not is_valid:
            result['errors'].extend(validation_errors)
            SecurityLogger.log_security_event('presentation_validation_failed', {
                'errors': validation_errors,
                'crypto_version': crypto_version
            }, 'WARNING')
            return result
        
        # Set security level based on crypto version
        if crypto_version == '2.0':
            result['security_level'] = 'enhanced'
            result['crypto_valid'] = True
        
        # Additional validations would go here (signature verification, etc.)
        # For now, mark as valid if all validations pass
        result['valid'] = True
        
        # Log successful verification
        verification_time = time.time() - start_time
        SecurityLogger.log_security_event('enhanced_verification_success', {
            'crypto_version': crypto_version,
            'security_level': result['security_level'],
            'verification_time_ms': round(verification_time * 1000, 2)
        })
        
    except Exception as e:
        result['errors'].append(f"Verification exception: {str(e)}")
        SecurityLogger.log_security_event('verification_exception', {
            'error': str(e),
            'crypto_version': result.get('crypto_version', 'unknown')
        }, 'ERROR')
    
    return result 