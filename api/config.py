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

_KNOWN_WEAK_DEFAULTS = frozenset({
    'dev-secret-key-for-testing',
    'lemma_platform_production_key_2024',
    'lemma_platform_internal_key_2024',
    'admin123',
    'secret',
    'changeme',
    'test',
})

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
        enforce_production_secret_distinctness(self)
    
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


def enforce_production_secret_distinctness(secrets: LemmaSecrets) -> None:
    """Fail production startup on weak, missing, or duplicated core secrets."""
    if not is_production():
        return

    tracked = {
        'SECRET_KEY': secrets.flask_secret,
        'LEMMA_OAUTH_JWT_SECRET': secrets.oauth_jwt_secret,
        'LEMMA_NETWORK_AUTH_KEY': secrets.network_auth_key,
        'LEMMA_PPID_ROOT_KEY': secrets.ppid_root_key,
        'LEMMA_IDENTITY_ROOT_PEPPER_V1': secrets.identity_root_pepper,
        'LEMMA_PERSON_ROOT_SALT_V1': secrets.person_root_salt,
        'LEMMA_BILLING_HMAC_SECRET': secrets.billing_hmac_secret,
        'LEMMA_HPKE_SERVER_KEY': secrets.hpke_server_key,
        'LEMMA_WALLET_SALT': secrets.wallet_salt,
    }

    seen_values: dict[str, str] = {}
    for name, value in tracked.items():
        if not value:
            raise RuntimeError(f"CRITICAL: Required secret {name} not set in production!")
        if value in _KNOWN_WEAK_DEFAULTS or value.startswith('DEV_ONLY_'):
            raise RuntimeError(f"CRITICAL: Secret {name} uses a known weak/default value in production!")
        if len(value) < 16:
            raise RuntimeError(f"CRITICAL: Secret {name} too short for production!")
        if value in seen_values:
            raise RuntimeError(
                f"CRITICAL: Secret {name} must be distinct from {seen_values[value]} in production!"
            )
        seen_values[value] = name


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


def _env_truthy(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def is_ishuman_idv_mobile_handoff_enabled() -> bool:
    """Silent mobile wallet provision during Didit IDV return (default on).

    Set LEMMA_IDV_MOBILE_HANDOFF_ENABLED=0 to disable the one-time handoff
    relay without affecting the core IDV popup flow.
    """
    return _env_truthy("LEMMA_IDV_MOBILE_HANDOFF_ENABLED", True)


def ishuman_idv_handoff_ttl_seconds() -> int:
    """One-time mobile handoff relay TTL (default 300s)."""
    raw = os.environ.get("LEMMA_IDV_HANDOFF_TTL_SECONDS", "300")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 300
    return max(60, min(value, 900))


def is_ishuman_idv_handoff_strict_claim_enabled() -> bool:
    """Require handoff_id + session_id + mk proof on mobile handoff claim.

    Set LEMMA_IDV_HANDOFF_STRICT_CLAIM=0 for emergency rollback to the legacy
    session-only claim path (logged as deprecated).
    """
    return _env_truthy("LEMMA_IDV_HANDOFF_STRICT_CLAIM", True)


def ishuman_skeleton_credential_ttl_seconds() -> int:
    """Short-lived master credentials for demo/skeleton IDV flows (default 1h)."""
    raw = os.environ.get("LEMMA_ISHUMAN_SKELETON_CREDENTIAL_TTL_SECONDS", "3600")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 3600
    return max(300, min(value, 86400))


def is_ishuman_skeleton_idv_enabled() -> bool:
    """Bypass Didit for autonomous demo/testing on non-production deploys."""
    if os.getenv("ENVIRONMENT", "").strip().lower() == "production":
        return False
    return _env_truthy("LEMMA_ISHUMAN_SKELETON_IDV_ENABLED", True)


def is_ishuman_demo_qr_idv_enabled() -> bool:
    """Public QR shell demo on /demo (short-lived, no Didit).

    Enabled explicitly on production via LEMMA_ISHUMAN_DEMO_QR_IDV_ENABLED.
    On non-production, follows skeleton IDV unless disabled.
    """
    if _env_truthy("LEMMA_ISHUMAN_DEMO_QR_IDV_ENABLED", False):
        return True
    return is_ishuman_skeleton_idv_enabled()


def ishuman_demo_qr_credential_ttl_seconds() -> int:
    """Demo QR IDV master credential lifetime (default 15 minutes)."""
    raw = os.environ.get("LEMMA_ISHUMAN_DEMO_QR_CREDENTIAL_TTL_SECONDS", "900")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 900
    return max(300, min(value, 86400))


def is_ishuman_network_revocation_enabled() -> bool:
    """Network-wide isHuman revocation is permanently retired."""
    return False


def is_ishuman_pull_fallback_enabled() -> bool:
    """Whether status-poll may actively pull a didit decision to issue.

    Webhook is the fast path; this guarantees issuance completes even if a
    webhook is delayed or dropped. Enabled by default whenever the didit rail is
    configured; set LEMMA_ISHUMAN_PULL_FALLBACK=0 to disable.
    """
    if not is_ishuman_didit_enabled():
        return False
    return _env_truthy("LEMMA_ISHUMAN_PULL_FALLBACK", True)


def get_ishuman_allowed_countries() -> frozenset[str]:
    """Issuing countries accepted for isHuman IDV root derivation.

    Defaults to US and CA. Override with comma-separated alpha-2 codes via
    ``LEMMA_ISHUMAN_ALLOWED_COUNTRIES`` (e.g. ``US,CA,MX``).
    """
    raw = (os.environ.get("LEMMA_ISHUMAN_ALLOWED_COUNTRIES") or "US,CA").strip()
    countries = {
        part.strip().upper()
        for part in raw.split(",")
        if part.strip()
    }
    return frozenset(countries) if countries else frozenset({"US", "CA"})


def get_ishuman_allowed_document_types() -> frozenset[str]:
    """Document types accepted for isHuman IDV root derivation.

    Defaults to driving_license and id_card (passports rejected). Override with
    comma-separated canonical types via ``LEMMA_ISHUMAN_ALLOWED_DOCUMENT_TYPES``.
    """
    raw = (
        os.environ.get("LEMMA_ISHUMAN_ALLOWED_DOCUMENT_TYPES")
        or "driving_license,id_card"
    ).strip()
    types = {
        part.strip().lower()
        for part in raw.split(",")
        if part.strip()
    }
    return frozenset(types) if types else frozenset({"driving_license", "id_card"})


def is_ishuman_didit_purge_enabled() -> bool:
    """Whether to delete the upstream didit session after credential issuance.

    Implements didit's "process-and-purge" data-minimization pattern
    (https://docs.didit.me/console/data-retention): once Lemma has durably
    issued the credential, the raw IDV session (document image, liveness,
    decision) at didit is no longer needed and is deleted from the upstream
    processor. Best-effort and non-fatal to issuance. Enabled by default
    whenever the didit rail is configured; set LEMMA_ISHUMAN_DIDIT_PURGE=0 to
    disable (e.g. to retain sessions for debugging in a staging environment).
    """
    if not is_ishuman_didit_enabled():
        return False
    return _env_truthy("LEMMA_ISHUMAN_DIDIT_PURGE", True)


def ppid_require_person_root() -> bool:
    """Fail closed instead of deriving a divergent legacy wallet-secret PPID.

    The canonical PPID is derived from the server-side person root. A legacy
    fallback path derives a DIFFERENT identifier from the wallet secret, which
    silently breaks account continuity. When this is on, authoritative
    (non-provisional) server-side derivation refuses to fall back to the
    wallet-secret path.

    Default ON: derivation now resolves the person root from the wallet binding
    for any verified wallet, so issuance/derive flows always take the canonical
    path. Only genuinely pre-IDV provisional callers (which pass
    provisional=True) may still use the wallet-secret path. Set
    LEMMA_PPID_REQUIRE_PERSON_ROOT=0 to restore the legacy permissive behavior.
    """
    return _env_truthy("LEMMA_PPID_REQUIRE_PERSON_ROOT", True)


def use_assigned_person_root() -> bool:
    """When true, new lemma_person rows get a server-assigned person_root instead
    of HKDF(document_root). Document roots become renewable attestations; PPIDs
    stay stable across document number changes when the wallet is rebound.

    Env: ``LEMMA_PERSON_ROOT_SOURCE=assigned_v1`` (default and production invariant).
    """
    mode = (os.environ.get("LEMMA_PERSON_ROOT_SOURCE") or "assigned_v1").strip().lower()
    return mode in ("assigned_v1", "assigned", "assigned_v2")


def one_ppid_assurance_model_enabled() -> bool:
    """Enable one-PPID evolution: provisional person root at wallet bind, assurance tiers.

    When on, site PPIDs derive from a stable assigned person_root created before IDV.
    ``isHuman`` becomes an added proof (assurance escalation), not a PPID root change.

    Env: ``LEMMA_ONE_PPID_ASSURANCE_MODEL=1`` (default off for rollout).
    """
    return _env_truthy("LEMMA_ONE_PPID_ASSURANCE_MODEL", False)


def passkey_assurance_enabled() -> bool:
    """Issue passkey-assurance site credentials before IDV when the one-PPID model is on.

    Requires ``LEMMA_ONE_PPID_ASSURANCE_MODEL=1``. Env: ``LEMMA_PASSKEY_ASSURANCE_ENABLED=1``.
    """
    if not one_ppid_assurance_model_enabled():
        return False
    return _env_truthy("LEMMA_PASSKEY_ASSURANCE_ENABLED", False)


def ppid_convergence_enabled() -> bool:
    """Issue signed convergence artifacts when a provisional wallet rebinds to a known person.

    Requires ``LEMMA_ONE_PPID_ASSURANCE_MODEL=1``. Env: ``LEMMA_PPID_CONVERGENCE_ENABLED=1``.
    """
    if not one_ppid_assurance_model_enabled():
        return False
    return _env_truthy("LEMMA_PPID_CONVERGENCE_ENABLED", False)


def warn_client_ppid_issuance() -> bool:
    """Emit deprecation telemetry/headers for bare client-supplied PPID issuance."""
    return _env_truthy("LEMMA_WARN_CLIENT_PPID_ISSUANCE", True)


def reject_client_ppid_issuance() -> bool:
    """Hard-reject bare client-supplied PPID on wallet-auth issue (except platform allowlist)."""
    return _env_truthy("LEMMA_REJECT_CLIENT_PPID_ISSUANCE", False)
