"""
Database setup and models for Lemma.id platform
"""

import os
import logging
import psycopg2
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import create_engine, Column, String, DateTime, Boolean, Integer, Text, JSON
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
        
        # Parse URL and connect
        _redis_client = redis.from_url(
            redis_url,
            decode_responses=True,  # Return strings instead of bytes
            socket_connect_timeout=5,
            socket_keepalive=True,
            health_check_interval=30
        )
        
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
    """Customer account model"""
    __tablename__ = 'customers'
    
    customer_id = Column(String, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    company = Column(String, nullable=False)
    stripe_customer_id = Column(String)
    api_keys = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default='active')
    subscription_status = Column(String, default='none')
    monthly_usage = Column(JSON, default=dict)
    billing_email = Column(String)
    password_hash = Column(String)
    role = Column(String, default='customer')
    permissions = Column(JSON, default=list)
    last_login = Column(DateTime)
    login_count = Column(Integer, default=0)

class Site(Base):
    """Site model for IAM"""
    __tablename__ = 'sites'
    
    site_id = Column(String, primary_key=True)
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
    """Activity log for both federated identity and IAM services"""
    __tablename__ = 'network_activity'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    site_id = Column(String, nullable=False)
    user_did = Column(String)  # May be hashed for privacy
    activity_type = Column(String, nullable=False)  # 'poh_verification', 'permission_check', 'login', 'grant', 'revoke'
    service_type = Column(String, nullable=False)  # 'poh_network', 'iam'
    success = Column(Boolean, nullable=False)
    verification_time_us = Column(Integer)  # Microsecond timing
    activity_metadata = Column(JSON, default=dict)  # Additional context
    timestamp = Column(DateTime, default=datetime.utcnow)
    ip_address = Column(String)  # For security/analytics
    user_agent = Column(String)

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
    """Revocation list for lemmas (both PoH and permissions)"""
    __tablename__ = 'revocation_list'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    lemma_id = Column(String, unique=True, nullable=False)  # Unique lemma identifier
    lemma_type = Column(String, nullable=False)  # 'poh', 'permission'
    site_id = Column(String)  # NULL for universal PoH revocations
    user_did = Column(String, nullable=False)
    revoked_by = Column(String, nullable=False)  # Who revoked it
    revoked_at = Column(DateTime, default=datetime.utcnow)
    reason = Column(String)  # Reason for revocation
    bloom_filter_updated = Column(Boolean, default=False)  # For efficient offline checking

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

def init_database():
    """Initialize database with tables"""
    try:
        create_tables()
        logger.info("✅ Database initialized successfully")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise e
