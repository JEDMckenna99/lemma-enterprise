"""
Trusted Issuer Registry

This module maintains the list of trusted issuer DIDs.
Credentials MUST be signed by a trusted issuer to be considered valid.

Security: Without this check, anyone can create a keypair and sign credentials
that would cryptographically verify but are NOT authorized by the network.
"""

import logging
import os
from typing import Set, Optional
from datetime import datetime, timedelta
from sqlalchemy import or_

logger = logging.getLogger(__name__)

# Cache for trusted issuers (refresh every 5 minutes)
_trusted_issuers_cache: Optional[Set[str]] = None
_cache_expires_at: Optional[datetime] = None
CACHE_TTL_SECONDS = 300  # 5 minutes


def _normalize_issuer_did(issuer_did: str) -> str:
    """Normalize issuer DID for trust comparison across legacy formats."""
    if not issuer_did:
        return ""
    text = str(issuer_did).strip()
    if not text:
        return ""
    # Ignore fragment/query variants (e.g. did:web:lemma.id#key-1).
    text = text.split('#', 1)[0].split('?', 1)[0].rstrip('/')
    return text.lower()


def _extract_issuer_did(credential: dict) -> Optional[str]:
    """
    Extract issuer DID from modern and legacy credential shapes.
    Supports:
    - issuer: "did:..."
    - issuer: {"id": "did:..."} / {"did": "did:..."}
    - issuerInfo.did
    """
    if not isinstance(credential, dict):
        return None

    issuer = credential.get('issuer')
    if isinstance(issuer, dict):
        issuer_did = issuer.get('id') or issuer.get('did')
    else:
        issuer_did = issuer

    if not issuer_did:
        issuer_info = credential.get('issuerInfo') or {}
        if isinstance(issuer_info, dict):
            issuer_did = issuer_info.get('did')

    if issuer_did:
        return str(issuer_did).strip()
    return None


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
        
        # Primary trust source: active sites with KMS-encrypted signing keys.
        sites = db.query(Site).filter(
            Site.kms_encrypted_signing_key != None,
            Site.issuer_did != None,
            or_(Site.key_status == 'active', Site.key_status == None)
        ).all()
        
        for site in sites:
            trusted_dids.add(site.issuer_did)
            logger.debug(f"Trusted issuer: {site.site_id} -> {site.issuer_did[:50]}...")

        # Compatibility trust source for platform lemma issuers:
        # Some deployments rotate/store platform signing metadata differently and may not
        # populate kms_encrypted_signing_key on the platform site rows.
        platform_sites = db.query(Site).filter(
            Site.site_id.in_(['lemma.id', 'lemma_platform']),
            Site.issuer_did != None,
            or_(Site.key_status == 'active', Site.key_status == None)
        ).all()
        for site in platform_sites:
            if site.issuer_did not in trusted_dids:
                trusted_dids.add(site.issuer_did)
                logger.info(f"Trusted platform issuer added: {site.site_id} -> {site.issuer_did[:50]}...")

        # Additional trust source: verified active issuer-registry records.
        try:
            from api.issuer_registry import IssuerRecord
            registry_issuers = db.query(IssuerRecord).filter(
                IssuerRecord.verified == True,
                IssuerRecord.is_active == True,
                IssuerRecord.revoked_at == None,
            ).all()
            for issuer in registry_issuers:
                if issuer.issuer_did and issuer.issuer_did not in trusted_dids:
                    trusted_dids.add(issuer.issuer_did)
                    logger.info(f"Trusted registry issuer added: {issuer.issuer_did[:50]}...")
        except Exception as e:
            logger.warning(f"Issuer-registry trust source unavailable: {e}")

        # Compatibility trust source: active lemma.id issuer records even when legacy
        # verification metadata is incomplete.
        try:
            from api.issuer_registry import IssuerRecord
            platform_registry_issuers = db.query(IssuerRecord).filter(
                IssuerRecord.domain.in_(['lemma.id', 'www.lemma.id']),
                IssuerRecord.is_active == True,
                IssuerRecord.revoked_at == None,
            ).all()
            for issuer in platform_registry_issuers:
                if issuer.issuer_did and issuer.issuer_did not in trusted_dids:
                    trusted_dids.add(issuer.issuer_did)
                    logger.warning(f"Trusted legacy platform registry issuer added: {issuer.issuer_did[:50]}...")
        except Exception as e:
            logger.warning(f"Legacy platform registry trust source unavailable: {e}")

        # Runtime canonical issuer fallback: include currently loaded platform IAM issuers.
        try:
            from api.issuer_management import get_issuer_manager
            issuer_manager = get_issuer_manager()
            for platform_site in ('lemma.id', 'lemma_platform'):
                try:
                    runtime_did = issuer_manager.get_iam_issuer(platform_site).get_did()
                    if runtime_did and runtime_did not in trusted_dids:
                        trusted_dids.add(runtime_did)
                        logger.info(f"Trusted runtime issuer added: {platform_site} -> {runtime_did[:50]}...")
                except Exception as inner_e:
                    logger.warning(f"Runtime issuer unavailable for {platform_site}: {inner_e}")
            try:
                federated_did = issuer_manager.get_federated_issuer().get_did()
                if federated_did and federated_did not in trusted_dids:
                    trusted_dids.add(federated_did)
                    logger.info(f"Trusted runtime federated issuer added: {federated_did[:50]}...")
            except Exception as inner_e:
                logger.warning(f"Runtime federated issuer unavailable: {inner_e}")
        except Exception as e:
            logger.warning(f"Runtime issuer fallback unavailable: {e}")

        # Optional explicit override via env for emergency trust bootstrapping.
        env_trusted = os.getenv('TRUSTED_ISSUER_DIDS', '')
        if env_trusted:
            for did in [d.strip() for d in env_trusted.split(',') if d.strip()]:
                if did not in trusted_dids:
                    trusted_dids.add(did)
                    logger.warning(f"Trusted issuer added from TRUSTED_ISSUER_DIDS: {did[:50]}...")
        
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
    # Fast path exact match.
    if issuer_did in trusted:
        return True

    normalized_issuer = _normalize_issuer_did(issuer_did)
    trusted_normalized = {_normalize_issuer_did(did) for did in trusted}
    is_trusted = normalized_issuer in trusted_normalized
    
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
        issuer_did = _extract_issuer_did(credential)
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
            signature_valid = verifier.verify_credential_json(cred_json)  # Returns boolean
            
            result['signature_valid'] = signature_valid
            
            if not signature_valid:
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

