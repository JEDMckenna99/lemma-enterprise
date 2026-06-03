"""
Database setup and models for Lemma.id platform
"""

import os
import logging
import psycopg2
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    create_engine,
    Column,
    String,
    DateTime,
    Boolean,
    Integer,
    Text,
    JSON,
    LargeBinary,
    UniqueConstraint,
    Index,
    text,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from dataclasses import dataclass, asdict

# Redis for caching and session storage
try:
    import redis
    redis_available = True
except ImportError:
    redis_available = False
    logger.warning("⚠️ Redis library not available")

logger = logging.getLogger(__name__)

# Redis client (lazy initialization)
_redis_client = None

def get_redis_client():
    """Get Redis client (singleton pattern)"""
    global _redis_client
    
    if not redis_available:
        raise Exception("Redis library not installed")
    
    if _redis_client is None:
        redis_url = os.getenv('REDIS_URL') or os.getenv('REDIS_TLS_URL')
        
        if not redis_url:
            raise Exception("REDIS_URL not set in environment")
        
        logger.info(f"🔗 Connecting to Redis...")

        from redis.backoff import ExponentialBackoff
        from redis.retry import Retry
        from redis.exceptions import (
            ConnectionError as RedisConnectionError,
            TimeoutError as RedisTimeoutError,
        )

        # Parse URL and connect (disable SSL verification for Heroku self-signed certs).
        # Bounded pool + retry/backoff keep us resilient to the shared 20-connection
        # Mini cap and the provider's 300s idle-connection cull.
        conn_kwargs = dict(
            decode_responses=True,  # Return strings instead of bytes
            socket_connect_timeout=5,
            socket_timeout=5,
            socket_keepalive=True,
            health_check_interval=30,
            max_connections=int(os.getenv('LEMMA_DB_REDIS_MAX_CONNECTIONS', '6')),
            retry=Retry(ExponentialBackoff(cap=1.0, base=0.1), retries=3),
            retry_on_error=[RedisConnectionError, RedisTimeoutError],
        )
        if redis_url.startswith('rediss://'):
            import ssl
            conn_kwargs['ssl_cert_reqs'] = ssl.CERT_NONE  # Heroku uses self-signed certs

        _redis_client = redis.from_url(redis_url, **conn_kwargs)
        
        # Test connection
        _redis_client.ping()
        logger.info(f"✅ Redis connected successfully")
    
    return _redis_client

# Database setup
DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    # Fix for SQLAlchemy 1.4+ which requires postgresql://
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Raw psycopg2 connection for IAM API (needs cursor access)
def get_db_connection(site_id=None):
    """
    Get raw psycopg2 database connection for IAM API
    Returns connection with cursor() method for SQL queries
    
    Args:
        site_id (str, optional): Site ID for Row-Level Security (RLS) context
    
    If site_id is provided, sets PostgreSQL session variable for RLS policies.
    This ensures even with SQL injection, customers only see their own data.
    """
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        raise Exception("DATABASE_URL not set in environment")
    
    # Fix URL for psycopg2
    if db_url.startswith('postgres://'):
        db_url = db_url.replace('postgres://', 'postgresql://', 1)
    
    # Connect with SSL required (Heroku)
    conn = psycopg2.connect(db_url, sslmode='require')
    
    # Set RLS context if site_id provided (for Row-Level Security policies)
    if site_id:
        cursor = conn.cursor()
        # Set session variable for RLS policies
        # This makes all queries automatically filtered by site_id
        cursor.execute("SET app.current_site_id = %s", (site_id,))
        cursor.close()
    
    return conn

class Customer(Base):
    """
    Customer account model (for billing/business customers)
    Note: For permission system users, see PlatformUser model
    """
    __tablename__ = 'customers'
    
    customer_id = Column(String, primary_key=True)
    customer_did = Column(String, unique=True)  # DID identifier (primary for wallet-first)
    email = Column(String, unique=True, nullable=True)  # Now optional - for notifications only
    name = Column(String, nullable=True)  # Optional
    company = Column(String, nullable=True)  # Optional
    display_name = Column(String)  # User-friendly name for UI
    stripe_customer_id = Column(String)
    api_keys = Column(JSON, default=list)
    sites = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default='active')
    subscription_status = Column(String, default='none')
    monthly_usage = Column(JSON, default=dict)
    workspace_id = Column(String, index=True)
    billing_email = Column(String)
    password_hash = Column(String)
    role = Column(String, default='customer')
    permissions = Column(JSON, default=list)
    last_login = Column(DateTime)
    login_count = Column(Integer, default=0)
    wallet_id = Column(String)  # Link to browser wallet


class PlatformUser(Base):
    """
    Users for the permission system (identified by DID, email optional)
    Separate from Customer which is for billing/business accounts
    """
    __tablename__ = 'platform_users'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_did = Column(String, unique=True, nullable=False)  # Primary identifier
    
    # Optional identity info
    email = Column(String)  # Optional, for notifications only
    display_name = Column(String)  # Optional, for UI
    
    # Wallet linkage  
    wallet_id = Column(String)  # Browser wallet ID
    passkey_credential_id = Column(String)  # Primary passkey credential
    
    # Account state
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime)
    status = Column(String, default='active')  # active, suspended, deleted
    
    # Metadata
    auth_method = Column(String, default='passkey')  # passkey, email_link, oauth
    verification_level = Column(String, default='base')  # base, email_verified, human_verified


class PlatformUserSite(Base):
    """Link table: which users have access to which sites"""
    __tablename__ = 'platform_user_sites'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_did = Column(String, nullable=False)  # References platform_users.user_did
    site_id = Column(String, nullable=False)  # Site they have access to
    role = Column(String, default='user')  # user, admin, owner
    joined_at = Column(DateTime, default=datetime.utcnow)
    invited_by = Column(String)  # Who invited them
    status = Column(String, default='active')  # active, pending, revoked

class Site(Base):
    """Site model for IAM"""
    __tablename__ = 'sites'
    
    site_id = Column(String, primary_key=True)
    workspace_id = Column(String, index=True)
    site_domain = Column(String, nullable=False)
    company_name = Column(String, nullable=False)
    admin_email = Column(String, nullable=False)
    plan = Column(String, default='starter')
    api_key = Column(String, nullable=False)
    oauth_client_id = Column(String, nullable=False)
    oauth_client_secret = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # KMS-encrypted Ed25519 signing key (HSM-backed storage)
    kms_encrypted_signing_key = Column(Text)  # Base64-encoded KMS ciphertext
    kms_key_id = Column(String)  # AWS KMS CMK ID used for encryption
    public_key_hex = Column(String)  # Ed25519 public key (64 hex chars)
    issuer_did = Column(String)  # did:lemma:{public_key_hex}
    
    # Key lifecycle management
    key_created_at = Column(DateTime)
    key_last_used = Column(DateTime)
    key_rotation_due = Column(DateTime)
    key_status = Column(String, default='active')  # 'active', 'rotating', 'deprecated', 'revoked'

class Permission(Base):
    """Permission model for IAM"""
    __tablename__ = 'permissions'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    site_id = Column(String, nullable=False)
    permission_id = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    scope = Column(JSON, nullable=False)
    conditions = Column(JSON, default=list)
    delegation_allowed = Column(Boolean, default=False)
    priority = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String)

class Workspace(Base):
    """Canonical Agent Ops tenant boundary."""
    __tablename__ = 'workspaces'

    workspace_id = Column(String, primary_key=True)
    slug = Column(String, unique=True, nullable=False)
    display_name = Column(String, nullable=False)
    owner_ppid = Column(String, index=True)
    owner_email = Column(String)
    owner_wallet_id = Column(String)
    billing_customer_id = Column(String, index=True)
    status = Column(String, default='active')
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class WorkspaceUser(Base):
    """Canonical platform operator identity."""
    __tablename__ = 'workspace_users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_did = Column(String, unique=True, nullable=False)
    primary_email = Column(String)
    display_name = Column(String)
    wallet_id = Column(String)
    verification_level = Column(String, default='base')
    status = Column(String, default='active')
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class WorkspaceMembership(Base):
    """Workspace membership and operator role."""
    __tablename__ = 'workspace_memberships'
    __table_args__ = (
        UniqueConstraint('workspace_id', 'workspace_user_id', name='uq_workspace_memberships_workspace_user'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    workspace_id = Column(String, nullable=False, index=True)
    workspace_user_id = Column(Integer, nullable=False, index=True)
    role = Column(String, default='viewer')
    invite_status = Column(String, default='active')
    joined_at = Column(DateTime, default=datetime.utcnow)
    invited_by = Column(String)
    metadata_json = Column(JSON, default=dict)

class PolicyProfile(Base):
    """Named policy profile attached to runtimes."""
    __tablename__ = 'policy_profiles'

    policy_profile_id = Column(String, primary_key=True)
    workspace_id = Column(String, index=True)
    policy_version = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    description = Column(Text)
    policy_document = Column(JSON, default=dict)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class AgentOpsRuntime(Base):
    """Canonical runtime registry for Agent Ops."""
    __tablename__ = 'runtimes'

    id = Column(Integer, primary_key=True, autoincrement=True)
    runtime_id = Column(String, unique=True, nullable=False)
    workspace_id = Column(String, nullable=False, index=True)
    site_id = Column(String, index=True)
    owner_ppid = Column(String, index=True)
    owner_wallet_id = Column(String, index=True)
    agent_id = Column(String, nullable=False)
    display_name = Column(String)
    policy_profile_id = Column(String, default='lemma_firewall_default_v1')
    policy_profile_version = Column(String, default='v1')
    risk_defaults_json = Column(JSON, default=dict)
    trust_state = Column(String, default='clean_internal')
    taint_epoch = Column(Integer, default=0)
    kill_switch_enabled = Column(Boolean, default=True)
    active = Column(Boolean, default=True)
    last_connected_at = Column(DateTime)
    killed_at = Column(DateTime)
    kill_reason = Column(String)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Delegation(Base):
    """First-class delegated authorization record."""
    __tablename__ = 'delegations'

    id = Column(Integer, primary_key=True, autoincrement=True)
    delegation_id = Column(String, unique=True, nullable=False)
    workspace_id = Column(String, nullable=False, index=True)
    runtime_id = Column(String, index=True)
    token_id = Column(String, index=True)
    delegator_ppid = Column(String, index=True)
    delegated_by_user_ref = Column(String)
    acting_for_ppid = Column(String)
    acting_for_user_ref = Column(String)
    requested_by_ppid = Column(String)
    requested_by_user_ref = Column(String)
    subject_type = Column(String, nullable=False, default='agent_credential')
    subject_ref = Column(String)
    audience = Column(String)
    scope_json = Column(JSON, default=list)
    allowed_sites_json = Column(JSON, default=list)
    resource_bounds_json = Column(JSON, default=dict)
    task_description = Column(Text)
    task_hash = Column(String)
    allowed_paths_json = Column(JSON, default=list)
    max_operations = Column(Integer)
    expires_at = Column(DateTime)
    revoked_at = Column(DateTime)
    status = Column(String, default='active')
    reason = Column(String)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class DecisionLog(Base):
    """Normalized Agent Ops decision log."""
    __tablename__ = 'decision_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    workspace_id = Column(String, index=True)
    runtime_id = Column(String, index=True)
    agent_id = Column(String, index=True)
    delegator_ppid = Column(String, index=True)
    credential_ref = Column(String, index=True)
    token_id = Column(String, index=True)
    route = Column(String)
    action = Column(String)
    resource = Column(String)
    method = Column(String)
    path = Column(String)
    decision = Column(String, nullable=False)
    reason_code = Column(String, nullable=False)
    policy_profile = Column(String)
    policy_version = Column(String)
    request_correlation_id = Column(String, index=True)
    trust_state = Column(String)
    taint_epoch = Column(Integer)
    status_code = Column(Integer)
    metadata_json = Column(JSON, default=dict)

class AgentOpsRevocation(Base):
    """Unified revocation registry for Agent Ops control plane subjects."""
    __tablename__ = 'agent_ops_revocations'

    id = Column(Integer, primary_key=True, autoincrement=True)
    revocation_id = Column(String, unique=True, nullable=False)
    workspace_id = Column(String, index=True)
    subject_type = Column(String, nullable=False)
    subject_ref = Column(String, nullable=False, index=True)
    runtime_id = Column(String, index=True)
    delegator_ppid = Column(String, index=True)
    reason_code = Column(String)
    revoked_by = Column(String)
    revoked_at = Column(DateTime, default=datetime.utcnow, index=True)
    effective_epoch = Column(Integer)
    metadata_json = Column(JSON, default=dict)

class FederatedSite(Base):
    """Sites registered for Federated Identity Network (PoH service)"""
    __tablename__ = 'federated_sites'
    
    site_id = Column(String, primary_key=True)
    site_domain = Column(String, unique=True, nullable=False)
    company_name = Column(String, nullable=False)
    admin_email = Column(String, nullable=False)
    api_key = Column(String, unique=True, nullable=False)
    service_type = Column(String, default='poh_network')  # 'poh_network' or 'iam' or 'both'
    plan = Column(String, default='starter')  # 'starter', 'professional', 'enterprise'
    status = Column(String, default='active')  # 'active', 'suspended', 'pending'
    monthly_active_users = Column(Integer, default=0)
    total_verifications = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_activity = Column(DateTime)
    billing_settings = Column(JSON, default=dict)  # MAU pricing, billing cycle, etc.

class UserLemma(Base):
    """User lemmas/credentials for both PoH and site-specific permissions"""
    __tablename__ = 'user_lemmas'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_did = Column(String, nullable=False)  # User's decentralized identifier
    lemma_type = Column(String, nullable=False)  # 'poh', 'permission', 'access'
    site_id = Column(String)  # NULL for universal PoH, specific for site permissions
    permission_id = Column(String)  # NULL for PoH, specific permission for IAM
    lemma_data = Column(JSON, nullable=False)  # The actual lemma/credential data
    issued_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    revoked_at = Column(DateTime)
    is_active = Column(Boolean, default=True)
    verification_count = Column(Integer, default=0)
    last_verified = Column(DateTime)

class SitePermissionGrant(Base):
    """Permission grants for users on specific sites (IAM service)"""
    __tablename__ = 'site_permission_grants'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    site_id = Column(String, nullable=False)
    user_did = Column(String, nullable=False)
    permission_id = Column(String, nullable=False)
    granted_by = Column(String, nullable=False)  # Admin who granted permission
    granted_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    revoked_at = Column(DateTime)
    is_active = Column(Boolean, default=True)
    conditions = Column(JSON, default=dict)  # Additional conditions/metadata

class NetworkActivity(Base):
    """
    Activity log for administrative operations only (grants, revokes).
    
    PRIVACY COMMITMENT: This table does NOT log verification events.
    - No IP addresses are collected
    - No user agents are collected  
    - Verification happens client-side (local Ed25519) - Lemma cannot observe it
    - Only administrative actions (permission grants/revokes) are logged for audit
    """
    __tablename__ = 'network_activity'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    site_id = Column(String, nullable=False)
    user_did = Column(String)  # PPID only (site-specific, unlinkable)
    activity_type = Column(String, nullable=False)  # 'grant', 'revoke' ONLY - no verification logging
    service_type = Column(String, nullable=False)  # 'iam' - administrative operations
    success = Column(Boolean, nullable=False)
    verification_time_us = Column(Integer)  # Performance metrics only
    # REMOVED: activity_metadata - could leak sensitive context
    timestamp = Column(DateTime, default=datetime.utcnow)
    # REMOVED: ip_address - privacy violation, not needed
    # REMOVED: user_agent - privacy violation, not needed

class BillingRecord(Base):
    """Billing records for MAU tracking and invoicing"""
    __tablename__ = 'billing_records'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    site_id = Column(String, nullable=False)
    billing_month = Column(String, nullable=False)  # 'YYYY-MM' format
    service_type = Column(String, nullable=False)  # 'poh_network', 'iam'
    monthly_active_users = Column(Integer, default=0)
    poh_verifications = Column(Integer, default=0)
    iam_verifications = Column(Integer, default=0)
    stripe_identity_verifications = Column(Integer, default=0)
    total_amount_cents = Column(Integer, default=0)
    stripe_invoice_id = Column(String)
    payment_status = Column(String, default='pending')  # 'pending', 'paid', 'failed'
    created_at = Column(DateTime, default=datetime.utcnow)
    paid_at = Column(DateTime)

class RevocationList(Base):
    """Revocation list for lemmas (both PoH and permissions)
    
    Supports THREE types of revocation:
    - credential: Revokes ONE specific credential (one device)
    - user: Revokes ALL credentials for a PPID (all devices on one site)
    - wallet: Revokes ALL credentials for a wallet_id (all sites, all devices)
    """
    __tablename__ = 'revocation_list'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    lemma_id = Column(String, unique=True, nullable=False)  # Unique lemma identifier (primary)
    credential_id = Column(String)  # Alias for lemma_id (backward compatibility)
    lemma_type = Column(String, nullable=False, default='permission')  # 'poh', 'permission'
    site_id = Column(String)  # NULL for universal PoH revocations
    user_did = Column(String)  # User DID (optional for some revocation types)
    ppid = Column(String, index=True)  # PPID for user-level revocation (all devices on one site)
    wallet_id = Column(String, index=True)  # wallet_id for global revocation (all sites, all devices)
    revocation_type = Column(String, default='credential')  # 'credential', 'user', or 'wallet'
    revoked_by = Column(String)  # Who revoked it
    revoked_at = Column(DateTime, default=datetime.utcnow)
    reason = Column(String)  # Reason for revocation
    bloom_filter_updated = Column(Boolean, default=False)  # For efficient offline checking
    # When False, a fresh IDV does NOT lift this row (governance-approved
    # coordinated-fraud kills stay sticky until explicitly reinstated). Defaults
    # True so ordinary site/user revocations remain amnesty-eligible. See
    # clear_amnesty_eligible_wallet_revocations + migration 030.
    is_amnesty_eligible = Column(
        Boolean, nullable=False, default=True, server_default=text('true')
    )

class SiteUser(Base):
    """Site-specific user registry for IAM subnet management"""
    __tablename__ = 'site_users'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    site_id = Column(String, nullable=False)
    user_did = Column(String, nullable=False)  # User's DID (can be site-specific or universal)
    user_email = Column(String)  # Optional: site-specific email
    display_name = Column(String)  # Site-specific display name
    user_status = Column(String, default='active')  # 'active', 'suspended', 'pending', 'banned'
    user_role = Column(String, default='user')  # Site-defined role (admin, moderator, user, etc.)
    site_user_metadata = Column(JSON, default=dict)  # Site-specific user data
    added_by = Column(String, nullable=False)  # Admin who added user
    added_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)
    login_count = Column(Integer, default=0)
    # Unique constraint: one user per site
    __table_args__ = (
        {'extend_existing': True}
    )

class SiteAdmin(Base):
    """Site administrators for IAM subnet management"""
    __tablename__ = 'site_admins'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    site_id = Column(String, nullable=False)
    admin_did = Column(String, nullable=False)  # Admin's DID
    admin_email = Column(String, nullable=False)  # Admin email
    admin_role = Column(String, default='admin')  # 'owner', 'admin', 'moderator'
    permissions = Column(JSON, default=list)  # What they can manage ['users', 'permissions', 'billing']
    added_by = Column(String)  # Who granted admin access (NULL for site owner)
    added_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    last_activity = Column(DateTime)

class PermissionRole(Base):
    """Role-based permission bundles for easier management"""
    __tablename__ = 'permission_roles'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    site_id = Column(String, nullable=False)
    role_id = Column(String, nullable=False)  # 'admin', 'moderator', 'editor', etc.
    role_name = Column(String, nullable=False)  # Display name
    description = Column(Text)
    permissions = Column(JSON, nullable=False)  # List of permission_ids
    is_default = Column(Boolean, default=False)  # Default role for new users
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

class UserSession(Base):
    """Active user sessions for IAM sites"""
    __tablename__ = 'user_sessions'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    site_id = Column(String, nullable=False)
    user_did = Column(String, nullable=False)
    session_token = Column(String, unique=True, nullable=False)
    oauth_access_token = Column(String)  # For "Sign in with Lemma"
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    last_activity = Column(DateTime, default=datetime.utcnow)
    ip_address = Column(String)
    user_agent = Column(String)
    is_active = Column(Boolean, default=True)

class Passkey(Base):
    """WebAuthn passkey credentials for users"""
    __tablename__ = 'passkeys'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False)  # Links to customer_id or user_did
    credential_id = Column(String, unique=True, nullable=False)  # Base64 encoded
    public_key = Column(Text, nullable=False)  # COSE format, base64 encoded
    sign_count = Column(Integer, default=0)
    
    # Device/authenticator info
    device_name = Column(String)  # User-friendly name ("iPhone", "YubiKey")
    authenticator_type = Column(String)  # 'platform', 'cross-platform'
    transports = Column(JSON, default=list)  # ['usb', 'nfc', 'ble', 'internal']
    
    # Attestation (for hardware verification)
    attestation_format = Column(String)  # 'packed', 'tpm', 'android-safetynet', 'none'
    attestation_data = Column(Text)  # Full attestation for high-security verification
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime)
    is_active = Column(Boolean, default=True)


class WalletSigningKey(Base):
    """Ed25519 public key registered for wallet-scoped API assertions."""
    __tablename__ = 'wallet_signing_keys'

    wallet_id = Column(String(128), primary_key=True)
    pubkey = Column(LargeBinary, nullable=False)
    algorithm = Column(String(32), nullable=False, default='ed25519')
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime)
    revoked_at = Column(DateTime)


class WalletSession(Base):
    """
    Global wallet sessions for cross-device "one passkey per day" experience.
    
    When a user unlocks their wallet on any device, we store the session here.
    Other devices with the same wallet_id can check if an unlock already happened today.
    
    Privacy note: We only store wallet_id (random string) and unlock timestamp.
    No user identity, sites visited, or credentials are stored.
    """
    __tablename__ = 'wallet_sessions'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    wallet_id = Column(String, nullable=False, index=True, unique=True)  # The wallet identifier
    unlocked_at = Column(DateTime, nullable=False)  # When passkey was last used
    expires_at = Column(DateTime, nullable=False)  # Session expiration (24h from unlock)
    profile_id = Column(String, default='default')  # Active profile when unlocked
    profile_name = Column(String, default='Personal')  # Profile display name
    device_hint = Column(String)  # Optional hint like "iPhone" or "Chrome on Windows"
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RedirectToken(Base):
    """
    Short-lived tokens for redirect-based authentication (mobile Safari).
    
    When mobile Safari blocks third-party storage/cookies, we use a redirect flow.
    User unlocks on lemma.id, we create a token, redirect back with token in URL,
    third-party site exchanges token for wallet data, token is deleted (single-use).
    
    Security:
    - Tokens expire in 60 seconds
    - Single-use (deleted after exchange)
    - Cryptographically random (32 bytes)
    """
    __tablename__ = 'redirect_tokens'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    token = Column(String, nullable=False, unique=True, index=True)
    wallet_id = Column(String, nullable=False)
    wallet_secret = Column(String, nullable=False)  # Encrypted in transit (HTTPS)
    return_url = Column(String)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class SiteConfiguration(Base):
    """Site-specific IAM configuration"""
    __tablename__ = 'site_configurations'
    
    site_id = Column(String, primary_key=True)
    # User Management Settings
    allow_self_registration = Column(Boolean, default=False)
    require_email_verification = Column(Boolean, default=True)
    default_user_role = Column(String, default='user')
    session_timeout_minutes = Column(Integer, default=480)  # 8 hours
    
    # Permission Settings
    permission_inheritance = Column(Boolean, default=True)  # Roles inherit permissions
    require_2fa_for_admin = Column(Boolean, default=False)
    
    # OAuth Settings
    oauth_enabled = Column(Boolean, default=True)
    oauth_scopes = Column(JSON, default=list)  # Available OAuth scopes
    oauth_redirect_uris = Column(JSON, default=list)  # Allowed redirect URIs
    
    # Branding & UI
    site_name = Column(String)
    site_logo_url = Column(String)
    custom_css = Column(Text)
    
    # Webhook Settings
    webhook_url = Column(String)  # For user events
    webhook_events = Column(JSON, default=list)  # ['user.created', 'permission.granted', etc.]
    
    # Security Settings
    ip_whitelist = Column(JSON, default=list)
    rate_limit_per_minute = Column(Integer, default=60)
    
    updated_at = Column(DateTime, default=datetime.utcnow)
    updated_by = Column(String)


class LemmaPerson(Base):
    """Stable Lemma identity for a verified human (person-root backed)."""
    __tablename__ = 'lemma_persons'

    id = Column(Integer, primary_key=True, autoincrement=True)
    person_id = Column(String, unique=True, nullable=False, index=True)
    # Encrypted at rest (api.column_crypto): the no-secret PPID-enumeration key.
    # Widened for the AES-GCM envelope; legacy 64-hex rows remain readable.
    person_root_hash = Column(String(255), nullable=False, index=True)
    root_version = Column(String, default='v1', nullable=False)
    primary_wallet_id = Column(String, index=True)
    status = Column(String, default='active')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LemmaDocumentRoot(Base):
    """Maps a Stripe-derived document root to a LemmaPerson."""
    __tablename__ = 'lemma_document_roots'

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_root_hash = Column(String(64), unique=True, nullable=False, index=True)
    lemma_person_id = Column(String, nullable=False, index=True)
    root_version = Column(String, default='v1', nullable=False)
    provider = Column(String, default='stripe_identity')
    stripe_verification_session_id = Column(String, index=True)
    stripe_verification_report_id = Column(String)
    document_country = Column(String(8))
    document_type = Column(String(32))
    confidence_level = Column(String(32))
    created_at = Column(DateTime, default=datetime.utcnow)
    revoked_at = Column(DateTime)


class LemmaWalletBinding(Base):
    """Links a wallet_id to a LemmaPerson after verified IDV."""
    __tablename__ = 'lemma_wallet_bindings'
    __table_args__ = (
        UniqueConstraint('wallet_id', name='uq_lemma_wallet_bindings_wallet'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    wallet_id = Column(String, nullable=False, index=True)
    lemma_person_id = Column(String, nullable=False, index=True)
    binding_status = Column(String, default='active')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class IsHumanVerification(Base):
    """Tracks Stripe Identity verification sessions for isHuman proofs.

    Each row represents one verification attempt. On success the issued
    credential_id links the verification to the credential stored in the
    user's wallet.
    """
    __tablename__ = 'ishuman_verifications'
    __table_args__ = (
        # One local verification row per (provider hosted session, wallet). The
        # provider can reuse a hosted session across repeated start-verification
        # calls; without this the webhook only flips the FIRST sibling to
        # verified and a client polling the other sibling sees 'pending' forever.
        # Partial so rows that legitimately omit either column (older Stripe rows
        # before backfill, NULL provider session) are unconstrained. See
        # migrations/028_ishuman_provider_session_unique.sql.
        Index(
            'uq_ishuman_provider_session_wallet',
            'provider_session_id', 'wallet_id',
            unique=True,
            postgresql_where=text(
                'provider_session_id IS NOT NULL AND wallet_id IS NOT NULL'
            ),
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, unique=True, nullable=False)
    # Nullable so non-Stripe issuers (e.g. didit) can omit it; their provider
    # session id is stored in provider_session_id instead.
    stripe_session_id = Column(String, unique=True, nullable=True)
    # v2 (Phase 3.2): generic upstream IDV session id for any issuer. The didit
    # webhook looks up records by this column (Stripe keys on stripe_session_id).
    provider_session_id = Column(String, index=True)
    wallet_id = Column(String, index=True)
    ppid = Column(String, index=True)
    credential_id = Column(String, index=True)
    lemma_person_id = Column(String, index=True)
    # Encrypted at rest (api.column_crypto): reference copy of the document root.
    # Not a lookup key here, so safe to encrypt. Widened for the AES-GCM envelope.
    document_root_hash = Column(String(255), index=True)
    root_version = Column(String, default='v1')
    # v2 (Phase 3.2 scaffold): which IDV issuer produced this verification.
    # Defaults to stripe_identity; multi-issuer integration is deferred.
    issuer_id = Column(String, default='stripe_identity', index=True)
    confidence_level = Column(String)
    status = Column(String, default='pending')  # pending, verified, failed, expired, revoked, superseded
    created_at = Column(DateTime, default=datetime.utcnow)
    verified_at = Column(DateTime)
    issued_at = Column(DateTime)
    expires_at = Column(DateTime)
    metadata_json = Column(JSON, default=dict)
    # v2 (Phase 1.1): server-sealed envelopes for person-root seed delivery.
    wallet_seed_envelope = Column(LargeBinary)
    person_root_proxy_envelope = Column(LargeBinary)
    seed_version = Column(String)


class DerivedCredential(Base):
    """Maps a master isHuman credential to its per-site derived credentials.

    When a master is revoked the server iterates all rows with the
    matching master_credential_id and adds every derived_credential_id
    to the revocation Bloom filter.  No cross-site linkable identifier
    is stored in the credential itself — only on the server.
    """
    __tablename__ = 'derived_credentials'
    __table_args__ = (
        UniqueConstraint('master_credential_id', 'target_site', name='uq_derived_master_site'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    master_credential_id = Column(String, nullable=False, index=True)
    derived_credential_id = Column(String, nullable=False, unique=True)
    wallet_id = Column(String, index=True)
    target_site = Column(String, nullable=False)
    derived_ppid = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    revoked_at = Column(DateTime)
    is_active = Column(Boolean, default=True)


class SiteBlock(Base):
    """Site-scoped PPID blocks for the isHuman network.

    When a site believes a user is not acting in good faith it can
    immediately block the PPID on its own domain.  This is the first
    tier of the two-tier revocation model — fast, site-local, and
    reversible.  Network-wide revocation is handled separately via
    RevocationList after evidence review.
    """
    __tablename__ = 'site_blocks'
    __table_args__ = (
        UniqueConstraint('site_id', 'ppid', name='uq_site_blocks_site_ppid'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    site_id = Column(String, nullable=False, index=True)
    ppid = Column(String, nullable=False, index=True)
    reason = Column(String)
    evidence_url = Column(String)
    blocked_at = Column(DateTime, default=datetime.utcnow)
    blocked_by = Column(String)
    is_active = Column(Boolean, default=True)
    network_revocation_requested = Column(Boolean, default=False)
    network_revocation_status = Column(String)  # pending_review, approved, rejected
    # When False, a fresh IDV does NOT deactivate this block (governance-approved
    # coordinated-fraud kills survive re-verification). Defaults True so ordinary
    # site self-blocks stay amnesty-eligible. See migration 030.
    is_amnesty_eligible = Column(
        Boolean, nullable=False, default=True, server_default=text('true')
    )


def create_tables():
    """Create all database tables"""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Database tables created successfully")
    except Exception as e:
        logger.error(f"❌ Failed to create database tables: {e}")

def get_db() -> Session:
    """Get database session"""
    db = SessionLocal()
    try:
        return db
    except Exception as e:
        db.close()
        raise e

def get_db_session() -> Session:
    """Backward-compatible database session helper."""
    return get_db()

def init_database():
    """Initialize database with tables"""
    try:
        create_tables()
        logger.info("✅ Database initialized successfully")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise e
