"""
Crypto Validation Utilities
Connects DID validation to actual cryptographic operations
"""

import json
import logging
import time
from typing import Dict, Tuple, Optional

logger = logging.getLogger(__name__)

def extract_public_key_from_did(did: str) -> bytes:
    """
    Extract Ed25519 public key from lemma DID
    
    Args:
        did: DID in format did:lemma:{64_char_hex_public_key}
        
    Returns:
        bytes: 32-byte Ed25519 public key
        
    Raises:
        ValueError: If DID format is invalid
    """
    if not did or not isinstance(did, str):
        raise ValueError("DID must be a non-empty string")
    
    parts = did.split(':')
    if len(parts) != 3:
        raise ValueError(f"DID must have 3 parts separated by ':', got {len(parts)}")
    
    if parts[0] != 'did':
        raise ValueError(f"DID must start with 'did:', got '{parts[0]}'")
    
    if parts[1] != 'lemma':
        raise ValueError(f"DID method must be 'lemma', got '{parts[1]}'")
    
    public_key_hex = parts[2]
    
    if len(public_key_hex) != 64:
        raise ValueError(f"Public key must be 64 hex chars, got {len(public_key_hex)}")
    
    try:
        public_key_bytes = bytes.fromhex(public_key_hex)
    except ValueError:
        raise ValueError(f"Invalid hex in public key: {public_key_hex}")
    
    if len(public_key_bytes) != 32:
        raise ValueError(f"Public key must be 32 bytes, got {len(public_key_bytes)}")
    
    return public_key_bytes

def validate_did_format(did: str) -> Dict[str, any]:
    """
    Validate DID format and extract public key
    
    Returns:
        dict: Validation result with extracted public key
    """
    try:
        public_key_bytes = extract_public_key_from_did(did)
        
        return {
            'valid': True,
            'did': did,
            'public_key_hex': public_key_bytes.hex(),
            'public_key_bytes': public_key_bytes,
            'reason': 'Valid lemma DID format'
        }
    except ValueError as e:
        return {
            'valid': False,
            'did': did,
            'public_key_hex': None,
            'public_key_bytes': None,
            'reason': str(e)
        }

def verify_credential_with_extracted_crypto(credential: Dict) -> Dict[str, any]:
    """
    Verify credential using public key extracted from issuer DID
    
    This connects DID validation to actual cryptographic verification
    """
    try:
        # Extract issuer DID
        issuer_did = credential.get('issuer')
        if not issuer_did:
            return {
                'verified': False,
                'signature_valid': False,
                'not_revoked': False,
                'confidence': 0.0,
                'error': 'Missing issuer DID'
            }
        
        # Validate DID format and extract public key
        did_validation = validate_did_format(issuer_did)
        if not did_validation['valid']:
            return {
                'verified': False,
                'signature_valid': False,
                'not_revoked': False,
                'confidence': 0.0,
                'error': f"Invalid issuer DID: {did_validation['reason']}"
            }
        
        logger.info(f"🔐 Extracted public key from DID: {did_validation['public_key_hex'][:16]}...{did_validation['public_key_hex'][-16:]}")
        
        # Verify using real crypto engine
        from lemma_crypto import PyOptimizedVerifier
        verifier = PyOptimizedVerifier()
        
        verification_start = time.perf_counter_ns()
        result = verifier.verify_credential(json.dumps(credential))
        verification_time = time.perf_counter_ns() - verification_start
        
        logger.info(f"✅ DID-crypto verification: verified={result.verified}, time={verification_time/1000:.3f}μs")
        
        return {
            'verified': result.verified,
            'signature_valid': result.signature_valid,
            'not_revoked': result.not_revoked,
            'confidence': result.confidence,
            'verification_time_ns': verification_time,
            'did_validation': did_validation,
            'method': 'did_extracted_crypto'
        }
        
    except Exception as e:
        logger.error(f"❌ DID-crypto verification failed: {e}")
        return {
            'verified': False,
            'signature_valid': False,
            'not_revoked': False,
            'confidence': 0.0,
            'error': str(e),
            'method': 'did_crypto_error'
        }

def validate_credential_structure(credential: Dict) -> Dict[str, any]:
    """
    Validate W3C VC structure before crypto verification
    """
    if not isinstance(credential, dict):
        return {'valid': False, 'reason': 'Credential must be a dictionary'}
    
    # Check required W3C VC fields
    required_fields = ['id', 'issuer', 'subject', 'credentialSubject', 'proof']
    missing_fields = []
    
    for field in required_fields:
        if field not in credential:
            missing_fields.append(field)
    
    if missing_fields:
        return {
            'valid': False,
            'reason': f"Missing required fields: {', '.join(missing_fields)}"
        }
    
    # Validate proof structure
    proof = credential.get('proof', {})
    if proof.get('type') != 'Ed25519Signature2020':
        return {
            'valid': False,
            'reason': f"Invalid proof type: {proof.get('type')}, expected Ed25519Signature2020"
        }
    
    if not proof.get('signatureValue'):
        return {
            'valid': False,
            'reason': 'Missing signature value in proof'
        }
    
    # Validate issuer DID
    issuer_validation = validate_did_format(credential['issuer'])
    if not issuer_validation['valid']:
        return {
            'valid': False,
            'reason': f"Invalid issuer DID: {issuer_validation['reason']}"
        }
    
    return {
        'valid': True,
        'reason': 'W3C VC structure valid',
        'issuer_public_key': issuer_validation['public_key_hex']
    }

def get_crypto_validation_stats() -> Dict[str, int]:
    """Get crypto validation statistics"""
    # In production, would track validation metrics
    return {
        'did_validations': 0,
        'crypto_verifications': 0,
        'successful_verifications': 0,
        'average_verification_time_ns': 0
    }
