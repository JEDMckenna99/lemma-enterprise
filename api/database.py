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
