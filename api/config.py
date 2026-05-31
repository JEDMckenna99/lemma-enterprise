"""
Lemma Configuration Module
Centralizes all secrets and configuration with proper environment variable handling.

SECURITY: All secrets MUST come from environment variables in production.
This module will FAIL FAST if critical secrets are missing.
"""

import os
import logging
import secrets as secrets_module

logger = logging.getLogger(__name__)

# ============================================
# ENVIRONMENT DETECTION
# ============================================

def is_production():
    """Check if running in production environment"""
    return os.environ.get('FLASK_ENV') == 'production' or \
           os.environ.get('ENVIRONMENT') == 'production' or \
           'herokuapp.com' in os.environ.get('HEROKU_APP_NAME', '')


def is_development():
    """Check if running in development environment"""
    return not is_production()


# ============================================
# SECRET LOADING WITH VALIDATION
# ============================================

def get_required_secret(name: str, min_length: int = 32) -> str:
    """
    Get a required secret from environment.
    In production, FAILS if not set or too short.
    In development, generates a warning and returns a dev fallback.
    """
    value = os.environ.get(name)
    
    if value and len(value) >= min_length:
        return value
    
    if is_production():
        if not value:
            raise RuntimeError(f"CRITICAL: Required secret {name} not set in production!")
        if len(value) < min_length:
            raise RuntimeError(f"CRITICAL: Secret {name} too short (min {min_length} chars)")
    
    # Development fallback - generate deterministic dev key
    dev_key = f"DEV_ONLY_{name}_{secrets_module.token_urlsafe(32)}"
    logger.warning(f"⚠️ DEV MODE: Using generated fallback for {name}")
    return dev_key


def get_optional_secret(name: str, default: str = None) -> str:
    """Get an optional secret, returns default if not set"""
    return os.environ.get(name, default)


# ============================================
# CORE SECRETS
# ============================================

class LemmaSecrets:
    """Centralized secrets management"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._load_secrets()
        self._initialized = True
    
    def _load_secrets(self):
        """Load all secrets from environment"""
        
        # OAuth/JWT Secret - for signing OAuth tokens
        self.oauth_jwt_secret = get_required_secret('LEMMA_OAUTH_JWT_SECRET', min_length=32)
        
        # Network Authentication Key - for network-level auth
        self.network_auth_key = get_required_secret('LEMMA_NETWORK_AUTH_KEY', min_length=32)
        
        # PPID Root Key - for deriving pairwise identifiers
        self.ppid_root_key = get_required_secret('LEMMA_PPID_ROOT_KEY', min_length=32)

        # Stripe document-root pepper and person-root HKDF salt
        self.identity_root_pepper = get_required_secret('LEMMA_IDENTITY_ROOT_PEPPER_V1', min_length=32)
        self.person_root_salt = get_required_secret('LEMMA_PERSON_ROOT_SALT_V1', min_length=32)
        
        # Billing HMAC Secret - for billing data integrity
        self.billing_hmac_secret = get_required_secret('LEMMA_BILLING_HMAC_SECRET', min_length=32)
        
        # HPKE Server Key - for recovery vault encryption
        self.hpke_server_key = get_required_secret('LEMMA_HPKE_SERVER_KEY', min_length=32)
        
        # Wallet Derivation Salt - for wallet retrieval
        self.wallet_salt = get_required_secret('LEMMA_WALLET_SALT', min_length=32)
        
        # Flask Secret Key
        self.flask_secret = get_required_secret('SECRET_KEY', min_length=16)
        
        # Stripe (optional - can run without billing)
        self.stripe_secret_key = get_optional_secret('STRIPE_SECRET_KEY')
        self.stripe_publishable_key = get_optional_secret('STRIPE_PUBLISHABLE_KEY')
        self.stripe_webhook_secret = get_optional_secret('STRIPE_WEBHOOK_SECRET')

        # Didit IDV rail (optional - second IDV provider; see
        # docs/architecture/OPERATIONAL_HARDENING.md Phase 3.2). Gated behind
        # LEMMA_ISHUMAN_DIDIT_ENABLED so it is fully inert until configured.
        self.didit_api_key = get_optional_secret('DIDIT_API_KEY')
        self.didit_webhook_secret = get_optional_secret('DIDIT_WEBHOOK_SECRET')
        self.didit_workflow_id = get_optional_secret('DIDIT_WORKFLOW_ID')
        self.didit_api_base = get_optional_secret('DIDIT_API_BASE', 'https://verification.didit.me')
        self.ishuman_didit_enabled = (
            get_optional_secret('LEMMA_ISHUMAN_DIDIT_ENABLED', 'false') or 'false'
        ).strip().lower() in ('1', 'true', 'yes', 'on')
        
        # AWS KMS (optional - falls back to memory storage)
        self.aws_access_key = get_optional_secret('AWS_ACCESS_KEY_ID')
        self.aws_secret_key = get_optional_secret('AWS_SECRET_ACCESS_KEY')
        self.kms_key_id = get_optional_secret('LEMMA_KMS_KEY_ID')
        
        # Email services (optional)
        self.sendgrid_api_key = get_optional_secret('SENDGRID_API_KEY')
        self.mailgun_api_key = get_optional_secret('MAILGUN_API_KEY')
        
        # Redis (optional - falls back to in-memory)
        self.redis_url = get_optional_secret('REDIS_URL')
        
        # Passkey configuration
        self.passkey_rp_id = get_optional_secret('PASSKEY_RP_ID', 'lemma.id')
        self.passkey_rp_name = get_optional_secret('PASSKEY_RP_NAME', 'Lemma')
        self.passkey_origin = get_optional_secret('PASSKEY_ORIGIN', 'https://lemma.id')
        
        logger.info("✅ Secrets loaded successfully")
        if is_development():
            logger.warning("⚠️ Running in DEVELOPMENT mode - some secrets may be auto-generated")
    
    def validate_production_readiness(self) -> dict:
        """Check if all production secrets are properly configured"""
        issues = []
        
        required_vars = [
            'LEMMA_OAUTH_JWT_SECRET',
            'LEMMA_NETWORK_AUTH_KEY', 
            'LEMMA_PPID_ROOT_KEY',
            'LEMMA_BILLING_HMAC_SECRET',
            'LEMMA_HPKE_SERVER_KEY',
            'LEMMA_WALLET_SALT',
            'SECRET_KEY'
        ]
        
        for var in required_vars:
            value = os.environ.get(var)
            if not value:
                issues.append(f"Missing: {var}")
            elif len(value) < 32:
                issues.append(f"Too short: {var} (need 32+ chars)")
        
        return {
            'ready': len(issues) == 0,
            'issues': issues,
            'environment': 'production' if is_production() else 'development'
        }


# Global secrets instance
_secrets = None

def get_secrets() -> LemmaSecrets:
    """Get the global secrets instance"""
    global _secrets
    if _secrets is None:
        _secrets = LemmaSecrets()
    return _secrets


# ============================================
# CONVENIENCE ACCESSORS
# ============================================

def get_oauth_jwt_secret() -> str:
    return get_secrets().oauth_jwt_secret

def get_network_auth_key() -> str:
    return get_secrets().network_auth_key

def get_ppid_root_key() -> str:
    return get_secrets().ppid_root_key


def get_identity_root_pepper() -> str:
    return get_secrets().identity_root_pepper


def get_person_root_salt() -> str:
    return get_secrets().person_root_salt

def get_billing_hmac_secret() -> str:
    return get_secrets().billing_hmac_secret

def get_hpke_server_key() -> bytes:
    return get_secrets().hpke_server_key.encode()[:32]

def get_wallet_salt() -> bytes:
    return get_secrets().wallet_salt.encode()[:32]

def get_stripe_secret_key() -> str:
    return get_secrets().stripe_secret_key

def get_redis_url() -> str:
    return get_secrets().redis_url


# ============================================
# DIDIT IDV RAIL (Phase 3.2 second issuer)
# ============================================

def get_didit_api_key() -> str:
    return get_secrets().didit_api_key

def get_didit_webhook_secret() -> str:
    return get_secrets().didit_webhook_secret

def get_didit_workflow_id() -> str:
    return get_secrets().didit_workflow_id

def get_didit_api_base() -> str:
    return get_secrets().didit_api_base

def is_ishuman_didit_enabled() -> bool:
    """True only when the didit IDV rail is explicitly enabled AND configured.

    Returns False unless LEMMA_ISHUMAN_DIDIT_ENABLED is truthy and the minimum
    didit credentials (api key + workflow id) are present, so the rail is inert
    by default and degrades closed on partial configuration.
    """
    s = get_secrets()
    if not s.ishuman_didit_enabled:
        return False
    return bool(s.didit_api_key and s.didit_workflow_id)
