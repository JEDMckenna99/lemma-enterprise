"""
Trusted Issuer Registry

This module maintains the list of trusted issuer DIDs.
Credentials MUST be signed by a trusted issuer to be considered valid.

Security: Without this check, anyone can create a keypair and sign credentials
that would cryptographically verify but are NOT authorized by the network.
"""

import logging
from typing import Set, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Cache for trusted issuers (refresh every 5 minutes)
_trusted_issuers_cache: Optional[Set[str]] = None
_cache_expires_at: Optional[datetime] = None
CACHE_TTL_SECONDS = 300  # 5 minutes


def get_trusted_issuer_dids() -> Set[str]:
    """
    Get the set of trusted issuer DIDs from the database.
    
    Only issuers with KMS-backed keys are trusted.
    Results are cached for performance.
    """
    global _trusted_issuers_cache, _cache_expires_at
    
    # Check cache
    if _trusted_issuers_cache is not None and _cache_expires_at and datetime.utcnow() < _cache_expires_at:
        return _trusted_issuers_cache
    
    # Refresh from database
    try:
        from api.database import SessionLocal, Site
        db = SessionLocal()
        
        trusted_dids = set()
        
        # Get all sites with KMS-encrypted signing keys (these are the trusted issuers)
        sites = db.query(Site).filter(
            Site.kms_encrypted_signing_key != None,
            Site.issuer_did != None,
            Site.key_status == 'active'
        ).all()
        
        for site in sites:
            trusted_dids.add(site.issuer_did)
            logger.debug(f"Trusted issuer: {site.site_id} -> {site.issuer_did[:50]}...")
        
        db.close()
        
        # Update cache
        _trusted_issuers_cache = trusted_dids
        _cache_expires_at = datetime.utcnow() + timedelta(seconds=CACHE_TTL_SECONDS)
        
        logger.info(f"✅ Loaded {len(trusted_dids)} trusted issuer DIDs")
        return trusted_dids
        
    except Exception as e:
        logger.error(f"❌ Failed to load trusted issuers: {e}")
        # Return cached value if available, otherwise empty set
        return _trusted_issuers_cache or set()


def is_trusted_issuer(issuer_did: str) -> bool:
    """
    Check if an issuer DID is in the trusted registry.
    
    Args:
        issuer_did: The issuer DID from a credential
        
    Returns:
        True if the issuer is trusted, False otherwise
    """
    if not issuer_did:
        return False
    
    trusted = get_trusted_issuer_dids()
    is_trusted = issuer_did in trusted
    
    if not is_trusted:
        logger.warning(f"⚠️ UNTRUSTED ISSUER: {issuer_did[:50]}...")
    
    return is_trusted


def clear_cache():
    """Clear the trusted issuer cache (useful for testing)"""
    global _trusted_issuers_cache, _cache_expires_at
    _trusted_issuers_cache = None
    _cache_expires_at = None


def verify_credential_with_trust(credential: dict) -> dict:
    """
    Verify a credential including trusted issuer check.
    
    This is the SECURE verification function that should be used
    instead of raw signature verification.
    
    Returns:
        {
            'valid': bool,
            'signature_valid': bool,
            'issuer_trusted': bool,
            'not_expired': bool,
            'not_revoked': bool,
            'reason': str (if invalid)
        }
    """
    import json
    import time
    
    result = {
        'valid': False,
        'signature_valid': False,
        'issuer_trusted': False,
        'not_expired': True,
        'not_revoked': True,
        'reason': None
    }
    
    try:
        # 1. Check issuer trust FIRST
        issuer_did = credential.get('issuer')
        if not issuer_did:
            result['reason'] = 'missing_issuer'
            return result
        
        if not is_trusted_issuer(issuer_did):
            result['reason'] = 'untrusted_issuer'
            logger.warning(f"🚫 Credential rejected: untrusted issuer {issuer_did[:50]}...")
            return result
        
        result['issuer_trusted'] = True
        
        # 2. Check expiration
        claims = credential.get('claims', credential.get('credentialSubject', {}))
        expires_at = claims.get('expiresAt') or credential.get('expires_at')
        if expires_at:
            if int(expires_at) < time.time():
                result['not_expired'] = False
                result['reason'] = 'expired'
                return result
        
        # 3. Check revocation
        credential_id = credential.get('id')
        if credential_id:
            try:
                from api.revocation_api import get_global_verifier
                verifier = get_global_verifier()
                if verifier and verifier.is_revoked(credential_id):
                    result['not_revoked'] = False
                    result['reason'] = 'revoked'
                    return result
            except Exception as e:
                logger.warning(f"Revocation check failed: {e}")
        
        # 4. Verify cryptographic signature
        try:
            from lemma_crypto import PyOptimizedVerifier
            verifier = PyOptimizedVerifier()
            
            cred_json = json.dumps(credential) if isinstance(credential, dict) else credential
            crypto_result = verifier.verify_credential(cred_json)
            
            result['signature_valid'] = crypto_result.verified
            
            if not crypto_result.verified:
                result['reason'] = 'invalid_signature'
                return result
                
        except Exception as e:
            logger.error(f"Crypto verification failed: {e}")
            result['reason'] = f'verification_error: {e}'
            return result
        
        # All checks passed
        result['valid'] = True
        return result
        
    except Exception as e:
        logger.error(f"Credential verification error: {e}")
        result['reason'] = str(e)
        return result

