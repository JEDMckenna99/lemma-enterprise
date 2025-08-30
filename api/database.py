"""
Database setup and models for Lemma.id platform
"""

import os
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import create_engine, Column, String, DateTime, Boolean, Integer, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

# Database setup
DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    # Fix for SQLAlchemy 1.4+ which requires postgresql://
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

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
    metadata = Column(JSON, default=dict)  # Additional context
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
