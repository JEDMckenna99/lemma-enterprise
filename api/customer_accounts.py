"""
Customer Account Management System for Lemma Shield

Handles customer registration, API key generation, and account management.
"""

import os
import secrets
import hashlib
import logging
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict, field
from collections import defaultdict
from threading import Lock
from flask import Blueprint, request, jsonify, session, redirect, url_for, render_template, make_response
from flask_cors import cross_origin
import stripe
from sqlalchemy.orm import Session
from .database import get_db, Customer as DBCustomer, init_database
from auth.decorators import require_customer_or_admin, extract_authenticated_ppid_from_request

# Configure Stripe
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

logger = logging.getLogger(__name__)

# Create blueprint
customer_accounts_bp = Blueprint('customer_accounts', __name__)

def _parse_bool_env(value: Optional[str], default: bool = False) -> bool:
    """Parse boolean-like environment values safely."""
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _is_invite_only_mode_enabled() -> bool:
    """
    Determine whether invite-only registration is enabled.

    Priority:
    1) Explicit override via LEMMA_AUTH_INVITE_ONLY
    2) Default to enabled in development
    """
    configured = os.getenv("LEMMA_AUTH_INVITE_ONLY")
    if configured is not None:
        return _parse_bool_env(configured, default=False)

    return (os.getenv("FLASK_ENV", "").strip().lower() == "development")


def _get_allowed_invite_codes() -> List[str]:
    """
    Return normalized invite codes from environment.

    Use LEMMA_AUTH_INVITE_CODES as comma-separated values.
    In development, fall back to a default code if none configured.
    """
    configured_codes = os.getenv("LEMMA_AUTH_INVITE_CODES", "")
    codes = [code.strip() for code in configured_codes.split(",") if code.strip()]

    if codes:
        return codes

    if os.getenv("FLASK_ENV", "").strip().lower() == "development":
        return ["lemma-dev-invite"]

    return []


def _is_valid_invite_code(invite_code: str) -> bool:
    """Validate invite code using constant-time comparison."""
    if not invite_code:
        return False

    for allowed_code in _get_allowed_invite_codes():
        if secrets.compare_digest(invite_code, allowed_code):
            return True
    return False


def _public_cors_origins() -> List[str]:
    """
    CORS origins used for public customer auth endpoints.
    Internal deployment URLs are intentionally excluded from source.
    """
    origins = {"https://lemma.id"}
    if os.getenv("FLASK_ENV", "").strip().lower() == "development":
        origins.update({"http://localhost:5000", "http://127.0.0.1:5000"})
    return sorted(origins)

def _parse_bool_env(value: Optional[str], default: bool = False) -> bool:
    """Parse boolean-like environment values safely."""
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _is_invite_only_mode_enabled() -> bool:
    """
    Determine whether invite-only registration is enabled.

    Priority:
    1) Explicit override via LEMMA_AUTH_INVITE_ONLY
    2) Default to enabled in development
    """
    configured = os.getenv("LEMMA_AUTH_INVITE_ONLY")
    if configured is not None:
        return _parse_bool_env(configured, default=False)

    return (os.getenv("FLASK_ENV", "").strip().lower() == "development")


def _get_allowed_invite_codes() -> List[str]:
    """
    Return normalized invite codes from environment.

    Use LEMMA_AUTH_INVITE_CODES as comma-separated values.
    In development, fall back to a default code if none configured.
    """
    configured_codes = os.getenv("LEMMA_AUTH_INVITE_CODES", "")
    codes = [code.strip() for code in configured_codes.split(",") if code.strip()]

    if codes:
        return codes

    if os.getenv("FLASK_ENV", "").strip().lower() == "development":
        return ["lemma-dev-invite"]

    return []


def _is_valid_invite_code(invite_code: str) -> bool:
    """Validate invite code using constant-time comparison."""
    if not invite_code:
        return False

    for allowed_code in _get_allowed_invite_codes():
        if secrets.compare_digest(invite_code, allowed_code):
            return True
    return False


# =============================================================================
# RATE LIMITING FOR API KEY VALIDATION
# =============================================================================

class RateLimiter:
    """
    In-memory rate limiter for API key validation attempts.
    Prevents brute-force attacks on API keys.
    
    Configuration:
    - MAX_ATTEMPTS: Maximum validation attempts per window
    - WINDOW_SECONDS: Time window for rate limiting
    - LOCKOUT_SECONDS: How long to lock out after exceeding limit
    """
    
    MAX_ATTEMPTS = 100       # Max attempts per IP per window
    WINDOW_SECONDS = 60      # 1 minute window
    LOCKOUT_SECONDS = 300    # 5 minute lockout after exceeding limit
    
    # Stricter limits for failed attempts (potential attacks)
    MAX_FAILED_ATTEMPTS = 10  # Max failed attempts before lockout
    FAILED_WINDOW_SECONDS = 60
    
    def __init__(self):
        self._attempts: Dict[str, List[float]] = defaultdict(list)
        self._failed_attempts: Dict[str, List[float]] = defaultdict(list)
        self._lockouts: Dict[str, float] = {}
        self._lock = Lock()
    
    def _cleanup_old_entries(self, key: str, window: float):
        """Remove entries older than the window"""
        now = time.time()
        cutoff = now - window
        
        if key in self._attempts:
            self._attempts[key] = [t for t in self._attempts[key] if t > cutoff]
        if key in self._failed_attempts:
            self._failed_attempts[key] = [t for t in self._failed_attempts[key] if t > cutoff]
    
    def is_rate_limited(self, identifier: str) -> tuple[bool, Optional[str]]:
        """
        Check if an identifier (IP address) is rate limited.
        
        Returns:
            (is_limited, reason) - True if limited, with explanation
        """
        with self._lock:
            now = time.time()
            
            # Check if currently locked out
            if identifier in self._lockouts:
                lockout_until = self._lockouts[identifier]
                if now < lockout_until:
                    remaining = int(lockout_until - now)
                    return True, f"Rate limited. Try again in {remaining} seconds."
                else:
                    # Lockout expired
                    del self._lockouts[identifier]
            
            self._cleanup_old_entries(identifier, max(self.WINDOW_SECONDS, self.FAILED_WINDOW_SECONDS))
            
            # Check total attempts
            if len(self._attempts.get(identifier, [])) >= self.MAX_ATTEMPTS:
                self._lockouts[identifier] = now + self.LOCKOUT_SECONDS
                logger.warning(f"Rate limit exceeded for {identifier} - locking out for {self.LOCKOUT_SECONDS}s")
                return True, f"Too many requests. Try again in {self.LOCKOUT_SECONDS} seconds."
            
            # Check failed attempts (stricter)
            if len(self._failed_attempts.get(identifier, [])) >= self.MAX_FAILED_ATTEMPTS:
                self._lockouts[identifier] = now + self.LOCKOUT_SECONDS
                logger.warning(f"Too many failed attempts for {identifier} - potential attack, locking out")
                return True, f"Too many failed attempts. Try again in {self.LOCKOUT_SECONDS} seconds."
            
            return False, None
    
    def record_attempt(self, identifier: str, success: bool):
        """Record a validation attempt"""
        with self._lock:
            now = time.time()
            self._attempts[identifier].append(now)
            
            if not success:
                self._failed_attempts[identifier].append(now)
    
    def get_stats(self, identifier: str) -> Dict[str, Any]:
        """Get rate limit stats for an identifier"""
        with self._lock:
            self._cleanup_old_entries(identifier, max(self.WINDOW_SECONDS, self.FAILED_WINDOW_SECONDS))
            
            return {
                'total_attempts': len(self._attempts.get(identifier, [])),
                'failed_attempts': len(self._failed_attempts.get(identifier, [])),
                'max_attempts': self.MAX_ATTEMPTS,
                'max_failed': self.MAX_FAILED_ATTEMPTS,
                'is_locked': identifier in self._lockouts
            }


# Global rate limiter instance
api_key_rate_limiter = RateLimiter()


def _extract_customer_id_from_request() -> Optional[str]:
    """
    Attempt to extract customer_id from Authorization bearer credential,
    falling back to session if available. Returns None if not authenticated.
    
    SECURITY: Now validates that the credential's issuer is trusted before
    extracting customer info. Credentials from old/untrusted issuers are rejected.
    
    Supports multiple credential formats:
    - did:lemma:customer:{customer_id} - direct customer ID
    - did:lemma:user:{user_id} - IAM user, lookup by email in claims
    - Credential with email in claims - lookup customer by email
    """
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        try:
            credential_json = auth_header.split(' ', 1)[1]
            credential = json.loads(credential_json)
            
            # SECURITY: Validate issuer is trusted BEFORE processing credential
            issuer_did = credential.get('issuer')
            logger.info(f"🔍 Processing credential with issuer: {issuer_did[:60] if issuer_did else 'NONE'}...")
            
            if issuer_did:
                try:
                    from api.trusted_issuers import is_trusted_issuer
                    trusted = is_trusted_issuer(issuer_did)
                    logger.info(f"🔐 Issuer trusted: {trusted}")
                    
                    if not trusted:
                        logger.warning(f"🚫 REJECTED credential from UNTRUSTED issuer: {issuer_did}")
                        return None
                except Exception as e:
                    logger.error(f"Trusted issuer check failed: {e}")
                    # Fail closed - reject if we can't verify trust
                    return None
            else:
                logger.warning("⚠️ Credential has no issuer field - rejecting")
                return None
            
            subject = credential.get('subject', '')
            claims = credential.get('claims') or credential.get('credentialSubject') or {}
            
            # Direct customer ID format
            if subject.startswith('did:lemma:customer:'):
                return subject.replace('did:lemma:customer:', '')
            
            # PPID format (wallet-first auth) - lookup/create by DID
            if subject.startswith('did:lemma:ppid_'):
                # Look up existing customer by their DID
                customer = customer_manager.get_customer_by_did(subject)
                if customer:
                    logger.info(f"✅ Found customer by PPID: {customer.customer_id}")
                    return customer.customer_id
                
                # Create new customer for this PPID (wallet-first flow)
                # Only for lemma.id platform credentials
                site_id = claims.get('siteId') or claims.get('site_id')
                if site_id in ('lemma.id', 'lemma_platform'):
                    logger.info(f"Creating customer record for PPID: {subject[:40]}...")
                    result = customer_manager.create_customer(
                        email=None,  # No email - wallet-first
                        name=f"Wallet User",
                        company=None,
                        password=None,
                        customer_did=subject,  # Store PPID as customer DID
                        skip_default_api_key=True
                    )
                    if result.get('success'):
                        logger.info(f"✅ Created customer {result.get('customer_id')} for PPID")
                        return result.get('customer_id')
                
                logger.warning(f"Could not create customer for PPID: {subject[:40]}")
                return None
            
            # Try to extract email from claims and lookup customer
            email = claims.get('email')
            
            if email:
                # Lookup customer by email
                customer = customer_manager.get_customer_by_email(email)
                if customer:
                    return customer.customer_id
                    
                # If no customer exists, create one for this IAM user
                # This enables the developer platform flow where users get access via IAM
                # then can register sites and get API keys
                logger.info(f"Creating customer record for IAM user: {email}")
                site_id = claims.get('siteId') or claims.get('site_id') or 'lemma_platform'
                result = customer_manager.create_customer(
                    email=email,
                    name=email.split('@')[0],
                    company=site_id,
                    password=None,  # No password - IAM-only access
                    skip_default_api_key=True  # Don't create default key - user should register site first
                )
                if result.get('success'):
                    return result.get('customer_id')
            
            logger.warning(f"Could not extract customer from credential subject: {subject}")
            return None
        except Exception as e:
            logger.error(f"Failed to parse credential from Authorization header: {e}")
            return None
    
    # Check for PPID from verified full-lemma header.
    ppid = extract_authenticated_ppid_from_request()
    if ppid and ppid.startswith('did:lemma:ppid_'):
        customer = customer_manager.get_customer_by_did(ppid)
        if customer:
            logger.info(f"✅ Authenticated via lemma header PPID: {customer.customer_id}")
            return customer.customer_id
    
    # Check for credential headers (edge computing pattern)
    credential_id = request.headers.get('X-Credential-ID')
    user_email = request.headers.get('X-User-Email')
    if credential_id:
        # Trust client-side verification, but always enforce canonical revocation checks
        from api.revocation_verifier import is_credential_revoked
        if not is_credential_revoked(credential_id):
            # Look up customer by email from credential (if provided)
            if user_email:
                customer = customer_manager.get_customer_by_email(user_email)
                if customer:
                    logger.info(f"✅ Authenticated via credential header (email): {customer.customer_id}")
                    return customer.customer_id
            logger.info(f"✅ Credential {credential_id[:20]}... verified (no customer lookup)")
            return None  # Credential valid but no customer linkage
    
    # No valid authentication found
    logger.debug("No valid authentication found in request")
    return None


class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder for datetime objects"""
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

@dataclass
class Customer:
    """Customer account data structure"""
    customer_id: str
    email: Optional[str]  # Now optional - for notifications only
    name: Optional[str]  # Now optional
    company: Optional[str]  # Now optional
    stripe_customer_id: Optional[str]
    api_keys: List[Dict[str, Any]]
    created_at: datetime
    status: str  # 'pending', 'active', 'suspended'
    subscription_status: str  # 'none', 'active', 'past_due', 'canceled'
    monthly_usage: Dict[str, int]  # month -> user_count
    sites: List[Dict[str, Any]]
    billing_email: Optional[str]
    password_hash: Optional[str] = None  # Hashed password for authentication
    role: str = 'customer'  # 'customer' or 'admin'
    permissions: List[str] = field(default_factory=list)
    last_login: Optional[datetime] = None
    login_count: int = 0
    # New DID-first fields
    customer_did: Optional[str] = None  # Primary identifier for wallet-first
    display_name: Optional[str] = None  # User-friendly name for UI
    wallet_id: Optional[str] = None  # Link to browser wallet

class CustomerAccountManager:
    """Manages customer accounts and API keys with PostgreSQL backend"""
    
    def __init__(self):
        self.customers: Dict[str, Customer] = {}
        self.email_to_customer: Dict[str, str] = {}
        self.api_key_to_customer: Dict[str, str] = {}
        self.db_available = False
        
        try:
            init_database()
            self.db_available = True
            logger.info("✅ CustomerAccountManager initialized with PostgreSQL")
            self._refresh_api_key_cache()
        except Exception as e:
            logger.error(f"❌ Failed to initialize database: {e}")
            logger.warning("⚠️ Falling back to in-memory customer store for development")
    
    def _refresh_api_key_cache(self):
        """Populate in-memory API key -> customer mapping
        
        Caches both:
        - key_hash -> customer_id (new secure method)
        - key -> customer_id (legacy plain-text, for backward compat)
        """
        self.api_key_to_customer = {}
        
        if self.db_available:
            try:
                db = get_db()
                # Only load the columns we need
                db_customers = db.query(DBCustomer.customer_id, DBCustomer.api_keys).all()
                for customer_id, api_keys in db_customers:
                    for key_data in api_keys or []:
                        # Cache by hash (new secure method)
                        key_hash = key_data.get('key_hash')
                        if key_hash:
                            self.api_key_to_customer[key_hash] = customer_id
                        
                        # Also cache plain-text key for backward compatibility
                        key_value = key_data.get('key')
                        if key_value:
                            self.api_key_to_customer[key_value] = customer_id
                db.close()
                logger.info(f"Cached {len(self.api_key_to_customer)} API keys from database")
            except Exception as e:
                logger.error(f"Failed to refresh API key cache: {e}")
        else:
            for customer_id, customer in self.customers.items():
                for key_data in customer.api_keys or []:
                    key_hash = key_data.get('key_hash')
                    if key_hash:
                        self.api_key_to_customer[key_hash] = customer_id
                    
                    key_value = key_data.get('key')
                    if key_value:
                        self.api_key_to_customer[key_value] = customer_id
    
    def _hydrate_customer(self, db_customer: DBCustomer) -> Customer:
        """Convert ORM customer to dataclass"""
        return Customer(
            customer_id=db_customer.customer_id,
            email=db_customer.email,
            name=db_customer.name,
            company=db_customer.company,
            stripe_customer_id=db_customer.stripe_customer_id,
            api_keys=db_customer.api_keys or [],
            sites=db_customer.sites or [],
            created_at=db_customer.created_at,
            status=db_customer.status,
            subscription_status=db_customer.subscription_status,
            monthly_usage=db_customer.monthly_usage or {},
            billing_email=db_customer.billing_email,
            password_hash=db_customer.password_hash,
            role=db_customer.role,
            permissions=db_customer.permissions or [],
            last_login=db_customer.last_login,
            login_count=db_customer.login_count,
            # New DID-first fields
            customer_did=getattr(db_customer, 'customer_did', None),
            display_name=getattr(db_customer, 'display_name', None),
            wallet_id=getattr(db_customer, 'wallet_id', None)
        )
    
    def _store_customer_in_memory(self, customer: Customer):
        """Persist customer in local dictionaries when DB is unavailable"""
        if self.db_available:
            return
        self.customers[customer.customer_id] = customer
        if customer.email:  # Email is now optional
            self.email_to_customer[customer.email] = customer.customer_id
        for key_data in customer.api_keys or []:
            key_value = key_data.get('key')
            if key_value:
                self.api_key_to_customer[key_value] = customer.customer_id
    
    def cache_customer(self, customer: Customer):
        """Public helper to cache a customer when operating without a database"""
        self._store_customer_in_memory(customer)
    
    def get_customer_by_email(self, email: str) -> Optional[Customer]:
        """Get customer by email from database"""
        if not email:
            return None
        if self.db_available:
            try:
                db = get_db()
                db_customer = db.query(DBCustomer).filter(DBCustomer.email == email).first()
                db.close()
                
                if db_customer:
                    return self._hydrate_customer(db_customer)
            except Exception as e:
                logger.error(f"Error getting customer by email: {e}")
        
        customer_id = self.email_to_customer.get(email)
        if customer_id:
            return self.customers.get(customer_id)
        return None
    
    def get_customer_by_did(self, user_did: str) -> Optional[Customer]:
        """
        Get customer by DID (primary identifier for wallet-first flow)
        This is the preferred lookup method for the permission system
        """
        if not user_did:
            return None
        if self.db_available:
            try:
                db = get_db()
                db_customer = db.query(DBCustomer).filter(DBCustomer.customer_did == user_did).first()
                db.close()
                
                if db_customer:
                    return self._hydrate_customer(db_customer)
            except Exception as e:
                logger.error(f"Error getting customer by DID: {e}")
        
        # Fall back to in-memory lookup
        for cust in self.customers.values():
            if getattr(cust, 'customer_did', None) == user_did:
                return cust
        return None
    
    def get_customer_by_ppid(self, ppid: str) -> Optional[Customer]:
        """
        Get customer by PPID (Pseudonymous Permanent ID from wallet auth).
        PPIDs are site-specific identifiers derived from wallet_secret + domain.
        
        Format: did:lemma:ppid_{hex_string}
        
        This looks up the customer_did field in the database.
        """
        if not ppid or not ppid.startswith('did:lemma:ppid_'):
            return None
        
        # PPID IS a type of DID, so we can use the same lookup
        return self.get_customer_by_did(ppid)
    
    def get_or_create_by_did(self, user_did: str, email: str = None, 
                            display_name: str = None, wallet_id: str = None) -> Dict[str, Any]:
        """
        Get or create a customer by DID (wallet-first flow)
        Email is optional and used only for notifications
        
        Returns: {'success': bool, 'customer': Customer, 'created': bool}
        """
        # First try to find by DID
        existing = self.get_customer_by_did(user_did)
        if existing:
            return {
                'success': True,
                'customer': existing,
                'customer_id': existing.customer_id,
                'customer_did': existing.customer_did,
                'created': False
            }
        
        # If email provided, check if there's an existing customer with that email
        # and link them to this DID
        if email:
            email_customer = self.get_customer_by_email(email)
            if email_customer:
                # Update existing customer with DID
                try:
                    if self.db_available:
                        db = get_db()
                        db.query(DBCustomer).filter(
                            DBCustomer.customer_id == email_customer.customer_id
                        ).update({
                            'customer_did': user_did,
                            'wallet_id': wallet_id,
                            'display_name': display_name or email_customer.display_name
                        })
                        db.commit()
                        db.close()
                    email_customer.customer_did = user_did
                    email_customer.wallet_id = wallet_id
                    return {
                        'success': True,
                        'customer': email_customer,
                        'customer_id': email_customer.customer_id,
                        'customer_did': user_did,
                        'created': False,
                        'linked': True  # Linked email to DID
                    }
                except Exception as e:
                    logger.error(f"Error linking DID to existing customer: {e}")
        
        # Create new customer with DID as primary identifier
        customer_id = f"cust_{secrets.token_hex(8)}"
        
        result = self.create_customer(
            email=email,  # Optional
            name=display_name or "Wallet User",
            company="",  # No longer required
            customer_did=user_did,
            wallet_id=wallet_id,
            skip_default_api_key=True  # Don't create API key for permission users
        )
        
        if result.get('success'):
            result['created'] = True
            result['customer_did'] = user_did
        
        return result
    
    def get_customer(self, customer_id: str) -> Optional[Customer]:
        """Get customer by ID from database"""
        if self.db_available:
            try:
                db = get_db()
                db_customer = db.query(DBCustomer).filter(DBCustomer.customer_id == customer_id).first()
                db.close()
                
                if db_customer:
                    return self._hydrate_customer(db_customer)
            except Exception as e:
                logger.error(f"Error getting customer by ID: {e}")
        
        return self.customers.get(customer_id)

    def get_customer_by_id(self, customer_id: str) -> Optional[Customer]:
        """Compatibility helper for modules expecting get_customer_by_id"""
        return self.get_customer(customer_id)
        
    def get_all_customers(self, limit: int = 100, offset: int = 0) -> List[Customer]:
        """Get all customers from database (for admin dashboard)"""
        customers = []
        
        if self.db_available:
            try:
                db = get_db()
                db_customers = db.query(DBCustomer).order_by(
                    DBCustomer.created_at.desc()
                ).limit(limit).offset(offset).all()
                db.close()
                
                for db_customer in db_customers:
                    customer = self._hydrate_customer(db_customer)
                    if customer:
                        customers.append(customer)
                        
            except Exception as e:
                logger.error(f"Error getting all customers: {e}")
        
        # Fallback to in-memory customers if DB not available
        if not customers and self.customers:
            customers = list(self.customers.values())[offset:offset+limit]
        
        return customers
        
    def generate_api_key(self, prefix: str = "lemma") -> str:
        """Generate a secure API key
        
        Returns the raw key (to show to user once) - store only the hash!
        """
        # Generate 32 random alphanumeric characters
        raw_key = f"{prefix}_{''.join(secrets.choice('abcdefghijklmnopqrstuvwxyz0123456789') for _ in range(32))}"
        return raw_key
    
    def hash_api_key(self, api_key: str) -> str:
        """Hash an API key for secure storage using SHA-256
        
        We store only the hash in the database. When validating,
        we hash the incoming key and compare hashes.
        """
        return hashlib.sha256(api_key.encode()).hexdigest()
    
    def get_key_hint(self, api_key: str) -> str:
        """Get a hint/suffix of the API key for display purposes
        
        Shows only the last 8 characters, used for identifying keys in UI
        """
        return api_key[-8:] if len(api_key) > 8 else api_key
    
    def hash_password(self, password: str) -> str:
        """Hash a password using SHA-256 with salt"""
        salt = secrets.token_hex(16)
        password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
        return f"{salt}:{password_hash}"
    
    def verify_password(self, password: str, password_hash: str) -> bool:
        """Verify a password against its hash"""
        try:
            salt, stored_hash = password_hash.split(':')
            computed_hash = hashlib.sha256((password + salt).encode()).hexdigest()
            return computed_hash == stored_hash
        except ValueError:
            return False
    
    def create_customer(self, email: str = None, name: str = None, company: str = None, 
                       billing_email: Optional[str] = None, password: Optional[str] = None,
                       skip_default_api_key: bool = False,
                       customer_did: str = None, wallet_id: str = None,
                       display_name: str = None, role: str = 'customer') -> Dict[str, Any]:
        """Create a new customer account
        
        Args:
            email: Optional - for notifications only (wallet-first flow)
            name: Optional - display name
            company: Optional - company name
            billing_email: Optional - for billing notifications
            password: Optional - for password-based auth (legacy)
            skip_default_api_key: If True, don't create a default API key
            customer_did: Primary identifier for wallet-first flow
            wallet_id: Browser wallet ID
            display_name: User-friendly display name
        """
        try:
            # Check if customer already exists by DID first (preferred)
            if customer_did:
                existing_customer = self.get_customer_by_did(customer_did)
                if existing_customer:
                    return {
                        'success': False,
                        'error': 'Customer with this DID already exists'
                    }
            
            # Then check by email if provided
            if email:
                existing_customer = self.get_customer_by_email(email)
                if existing_customer:
                    return {
                        'success': False,
                        'error': 'Customer with this email already exists'
                    }
            
            # Generate customer ID
            customer_id = f"cus_{''.join(secrets.choice('abcdefghijklmnopqrstuvwxyz0123456789') for _ in range(16))}"
            
            # Generate DID if not provided
            if not customer_did:
                customer_did = f"did:lemma:user:{secrets.token_hex(16)}"
            
            # Create Stripe customer only if email is provided (for billing)
            stripe_customer_id = None
            if email:
                try:
                    stripe_customer = stripe.Customer.create(
                        email=email,
                        name=name or display_name or "Wallet User",
                        metadata={
                            'company': company or '',
                            'lemma_customer_id': customer_id,
                            'lemma_did': customer_did
                        }
                    )
                    stripe_customer_id = stripe_customer.id
                except Exception as stripe_err:
                    logger.warning(f"Stripe customer creation skipped: {stripe_err}")
            
            # Generate initial API key (unless skipped for IAM-based accounts)
            api_keys_list = []
            api_key = None
            if not skip_default_api_key:
                api_key = self.generate_api_key()
                api_key_data = {
                    'key': api_key,
                    'name': 'Default API Key',
                    'site_id': None,
                    'created_at': datetime.utcnow().isoformat(),
                    'last_used': None,
                    'usage_count': 0,
                    'status': 'active'
                }
                api_keys_list = [api_key_data]
            
            # Hash password if provided
            password_hash = None
            if password:
                password_hash = self.hash_password(password)
            
            # Create customer record
            customer = Customer(
                customer_id=customer_id,
                customer_did=customer_did,
                email=email,
                name=name or display_name,
                company=company,
                display_name=display_name,
                wallet_id=wallet_id,
                stripe_customer_id=stripe_customer_id,
                api_keys=api_keys_list,
                sites=[],
                created_at=datetime.utcnow(),
                status='active',
                subscription_status='none',
                monthly_usage={},
                billing_email=billing_email or email,
                password_hash=password_hash,
                role=role,
            )
            
            # Store customer in database
            db = None
            try:
                db = get_db()
                db_customer = DBCustomer(
                    customer_id=customer_id,
                    customer_did=customer_did,
                    email=email,
                    name=name or display_name,
                    company=company,
                    display_name=display_name,
                    wallet_id=wallet_id,
                    stripe_customer_id=stripe_customer_id,
                    api_keys=api_keys_list,
                    sites=[],
                    created_at=datetime.utcnow(),
                    status='active',
                    subscription_status='none',
                    monthly_usage={},
                    billing_email=billing_email or email,
                    password_hash=password_hash,
                    role=role,
                    permissions=[],
                    login_count=0
                )
                db.add(db_customer)
                db.commit()
                db.close()
            except Exception as e:
                logger.error(f"Failed to save customer to database: {e}")
                if db is not None:
                    db.rollback()
                    db.close()
                raise e
            
            # Map API key to customer if one was created
            if api_key:
                self.api_key_to_customer[api_key] = customer_id
            self._store_customer_in_memory(customer)
            
            logger.info(f"Created customer account: {customer_id} (DID: {customer_did[:30]}..., email: {email or 'none'})")
            
            return {
                'success': True,
                'customer_id': customer_id,
                'customer_did': customer_did,
                'stripe_customer_id': stripe_customer_id,
                'api_key': api_key,
                'customer': customer,
                'customer_data': asdict(customer)
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating customer: {e}")
            return {
                'success': False,
                'error': f'Payment setup failed: {str(e)}'
            }
        except Exception as e:
            logger.error(f"Error creating customer: {e}")
            return {
                'success': False,
                'error': 'Failed to create customer account'
            }
    
    def get_customer_by_api_key(self, api_key: str) -> Optional[Customer]:
        """Get customer by API key
        
        Checks both the in-memory cache and database.
        Supports both hashed keys (new) and plain-text keys (legacy).
        """
        # Check cache first (for plain-text legacy keys)
        customer_id = self.api_key_to_customer.get(api_key)
        if customer_id:
            return self.get_customer(customer_id)
        
        # Check cache by hash
        key_hash = self.hash_api_key(api_key)
        customer_id = self.api_key_to_customer.get(key_hash)
        if customer_id:
            return self.get_customer(customer_id)
        
        # Attempt to refresh cache and search DB if available
        if self.db_available:
            self._refresh_api_key_cache()
            
            # Check again after refresh
            customer_id = self.api_key_to_customer.get(api_key)
            if customer_id:
                return self.get_customer(customer_id)
            
            customer_id = self.api_key_to_customer.get(key_hash)
            if customer_id:
                return self.get_customer(customer_id)
        
        return None
    
    def generate_additional_api_key(self, customer_id: str, key_name: str, site_id: Optional[str] = None) -> Dict[str, Any]:
        """Generate an additional API key for a customer
        
        Security: We store only the hash of the key. The raw key is returned
        once to the user and should never be stored in plain text.
        """
        raw_api_key = self.generate_api_key()
        key_hash = self.hash_api_key(raw_api_key)
        key_hint = self.get_key_hint(raw_api_key)
        
        api_key_data = {
            'key_hash': key_hash,           # Stored: SHA-256 hash for validation
            'key_hint': key_hint,           # Stored: Last 8 chars for UI display
            'key': raw_api_key,             # TEMPORARY: For backward compat, will be removed
            'name': key_name,
            'site_id': site_id,
            'created_at': datetime.utcnow().isoformat(),
            'last_used': None,
            'usage_count': 0,
            'status': 'active'
        }
        
        if self.db_available:
            db = None
            try:
                db = get_db()
                db_customer = db.query(DBCustomer).filter(DBCustomer.customer_id == customer_id).first()
                if not db_customer:
                    return {'success': False, 'error': 'Customer not found'}
                
                # Create a new list to ensure SQLAlchemy detects the change
                keys = list(db_customer.api_keys or [])
                keys.append(api_key_data)
                db_customer.api_keys = keys
                
                # Flag the column as modified (SQLAlchemy doesn't auto-detect JSON mutations)
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(db_customer, 'api_keys')
                
                db.commit()
                logger.info(f"Stored API key with site_id={site_id} for customer {customer_id}")
            except Exception as e:
                logger.error(f"Failed to generate new API key for {customer_id}: {e}")
                if db is not None:
                    db.rollback()
                return {'success': False, 'error': 'Failed to generate API key'}
            finally:
                if db is not None:
                    db.close()
        else:
            customer = self.get_customer(customer_id)
            if not customer:
                return {'success': False, 'error': 'Customer not found'}
            customer.api_keys.append(api_key_data)
            self._store_customer_in_memory(customer)
        
        # Cache both the hash and the raw key (for backward compat during transition)
        self.api_key_to_customer[key_hash] = customer_id
        self.api_key_to_customer[raw_api_key] = customer_id
        
        # Also write to PostgreSQL api_keys table (dual-write for migration)
        if site_id:
            try:
                from api.storage_helpers import upsert_api_key_to_postgres
                upsert_api_key_to_postgres(
                    customer_id=customer_id,
                    site_id=site_id,
                    key_hash=key_hash,
                    key_hint=key_hint,
                    name=key_name
                )
                logger.info(f"✅ API key written to PostgreSQL api_keys table")
            except Exception as pg_err:
                logger.warning(f"⚠️ Could not write to PostgreSQL api_keys table: {pg_err}")
                # Don't fail - JSON write succeeded
        
        logger.info(f"Generated additional API key for customer: {customer_id}")
        
        return {
            'success': True,
            'api_key': raw_api_key,  # Return raw key to show user ONCE
            'key_data': api_key_data
        }
    
    def revoke_api_key(self, customer_id: str, api_key: str) -> Dict[str, Any]:
        """Revoke an API key"""
        revoked = False
        
        if self.db_available:
            db = None
            try:
                db = get_db()
                db_customer = db.query(DBCustomer).filter(DBCustomer.customer_id == customer_id).first()
                if not db_customer:
                    return {'success': False, 'error': 'Customer not found'}
                
                keys = db_customer.api_keys or []
                for key_data in keys:
                    if key_data.get('key') == api_key:
                        key_data['status'] = 'revoked'
                        key_data['revoked_at'] = datetime.utcnow().isoformat()
                        revoked = True
                        break
                
                if not revoked:
                    return {'success': False, 'error': 'API key not found'}
                
                db_customer.api_keys = keys
                db.commit()
            except Exception as e:
                logger.error(f"Failed to revoke API key for {customer_id}: {e}")
                if db is not None:
                    db.rollback()
                return {'success': False, 'error': 'Failed to revoke API key'}
            finally:
                if db is not None:
                    db.close()
        else:
            customer = self.get_customer(customer_id)
            if not customer:
                return {'success': False, 'error': 'Customer not found'}
            
            for key_data in customer.api_keys:
                if key_data['key'] == api_key:
                    key_data['status'] = 'revoked'
                    key_data['revoked_at'] = datetime.utcnow().isoformat()
                    revoked = True
                    break
            
            if not revoked:
                return {'success': False, 'error': 'API key not found'}
            
            self._store_customer_in_memory(customer)
        
        # Remove from active mapping
        self.api_key_to_customer.pop(api_key, None)
        
        logger.info(f"Revoked API key for customer: {customer_id}")
        return {'success': True}
    
    def revoke_api_key_by_hint(self, customer_id: str, site_id: str, key_hint: str) -> Dict[str, Any]:
        """Revoke an API key by site_id and key_hint (secure method)
        
        This is the preferred method since we don't expose full keys after creation.
        """
        revoked = False
        revoked_hash = None
        
        if self.db_available:
            db = None
            try:
                db = get_db()
                db_customer = db.query(DBCustomer).filter(DBCustomer.customer_id == customer_id).first()
                if not db_customer:
                    return {'success': False, 'error': 'Customer not found'}
                
                keys = list(db_customer.api_keys or [])
                for key_data in keys:
                    # Match by site_id and key_hint
                    stored_hint = key_data.get('key_hint') or (key_data.get('key', '')[-8:] if key_data.get('key') else '')
                    if key_data.get('site_id') == site_id and stored_hint == key_hint:
                        key_data['status'] = 'revoked'
                        key_data['revoked_at'] = datetime.utcnow().isoformat()
                        revoked = True
                        revoked_hash = key_data.get('key_hash')
                        break
                
                if not revoked:
                    return {'success': False, 'error': 'API key not found'}
                
                db_customer.api_keys = keys
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(db_customer, 'api_keys')
                db.commit()
            except Exception as e:
                logger.error(f"Failed to revoke API key for {customer_id}: {e}")
                if db is not None:
                    db.rollback()
                return {'success': False, 'error': 'Failed to revoke API key'}
            finally:
                if db is not None:
                    db.close()
        else:
            customer = self.get_customer(customer_id)
            if not customer:
                return {'success': False, 'error': 'Customer not found'}
            
            for key_data in customer.api_keys:
                stored_hint = key_data.get('key_hint') or (key_data.get('key', '')[-8:] if key_data.get('key') else '')
                if key_data.get('site_id') == site_id and stored_hint == key_hint:
                    key_data['status'] = 'revoked'
                    key_data['revoked_at'] = datetime.utcnow().isoformat()
                    revoked = True
                    revoked_hash = key_data.get('key_hash')
                    break
            
            if not revoked:
                return {'success': False, 'error': 'API key not found'}
            
            self._store_customer_in_memory(customer)
        
        # Remove from active mapping by hash if available
        if revoked_hash:
            self.api_key_to_customer.pop(revoked_hash, None)
        
        logger.info(f"Revoked API key (hint: {key_hint}) for customer: {customer_id}")
        return {'success': True}
    
    def rotate_api_key(self, customer_id: str, site_id: str, key_hint: str) -> Dict[str, Any]:
        """
        Rotate an API key: generate a new key for the same site and revoke the old one.
        
        This is a secure way to replace a potentially compromised key without
        losing the site association and configuration.
        
        Args:
            customer_id: The customer who owns the key
            site_id: The site the key is associated with
            key_hint: The hint of the key to rotate (last 8 chars)
        
        Returns:
            Dict with success status and new key details
        """
        # First, find the old key to get its name
        old_key_name = None
        old_key_found = False
        
        if self.db_available:
            db = None
            try:
                db = get_db()
                db_customer = db.query(DBCustomer).filter(DBCustomer.customer_id == customer_id).first()
                if not db_customer:
                    return {'success': False, 'error': 'Customer not found'}
                
                keys = list(db_customer.api_keys or [])
                
                # Find the old key
                for key_data in keys:
                    stored_hint = key_data.get('key_hint') or (key_data.get('key', '')[-8:] if key_data.get('key') else '')
                    if key_data.get('site_id') == site_id and stored_hint == key_hint and key_data.get('status') == 'active':
                        old_key_name = key_data.get('name', 'API Key')
                        old_key_found = True
                        break
                
                if not old_key_found:
                    return {'success': False, 'error': 'Active API key not found for rotation'}
                
                db.close()
            except Exception as e:
                logger.error(f"Failed to find key for rotation: {e}")
                if db is not None:
                    db.close()
                return {'success': False, 'error': 'Failed to rotate API key'}
        else:
            customer = self.get_customer(customer_id)
            if not customer:
                return {'success': False, 'error': 'Customer not found'}
            
            for key_data in customer.api_keys:
                stored_hint = key_data.get('key_hint') or (key_data.get('key', '')[-8:] if key_data.get('key') else '')
                if key_data.get('site_id') == site_id and stored_hint == key_hint and key_data.get('status') == 'active':
                    old_key_name = key_data.get('name', 'API Key')
                    old_key_found = True
                    break
            
            if not old_key_found:
                return {'success': False, 'error': 'Active API key not found for rotation'}
        
        # Generate the new key first (so we have it before revoking old one)
        new_key_name = f"{old_key_name} (rotated {datetime.utcnow().strftime('%Y-%m-%d')})"
        new_key_result = self.generate_additional_api_key(customer_id, new_key_name, site_id)
        
        if not new_key_result.get('success'):
            return {'success': False, 'error': 'Failed to generate new key during rotation'}
        
        # Now revoke the old key
        revoke_result = self.revoke_api_key_by_hint(customer_id, site_id, key_hint)
        
        if not revoke_result.get('success'):
            # Log but don't fail - new key is already created
            logger.warning(f"Failed to revoke old key during rotation for {customer_id}, site {site_id}")
        
        logger.info(f"Rotated API key for customer {customer_id}, site {site_id}")
        
        return {
            'success': True,
            'message': 'API key rotated successfully. The old key has been revoked.',
            'new_api_key': new_key_result.get('api_key'),
            'new_key_data': new_key_result.get('key_data'),
            'old_key_revoked': revoke_result.get('success', False)
        }
    
    def validate_api_key(self, api_key: str) -> Dict[str, Any]:
        """Validate an API key and return customer info
        
        Security: We hash the incoming key and compare against stored hashes.
        Also supports legacy plain-text keys for backward compatibility.
        """
        customer = self.get_customer_by_api_key(api_key)
        if not customer:
            return {'valid': False, 'error': 'Invalid API key'}
        
        if customer.status != 'active':
            return {'valid': False, 'error': 'Customer account suspended'}
        
        # Hash the incoming key for comparison
        incoming_hash = self.hash_api_key(api_key)
        
        # Find the specific key and update usage
        for key_data in customer.api_keys:
            if key_data.get('status') != 'active':
                continue
                
            # Check against hash (new secure method)
            if key_data.get('key_hash') == incoming_hash:
                key_data['last_used'] = datetime.utcnow().isoformat()
                key_data['usage_count'] = key_data.get('usage_count', 0) + 1
                
                return {
                    'valid': True,
                    'customer_id': customer.customer_id,
                    'customer_name': customer.name,
                    'company': customer.company,
                    'subscription_status': customer.subscription_status,
                    'site_id': key_data.get('site_id')
                }
            
            # Backward compatibility: check plain-text key (legacy)
            if key_data.get('key') == api_key:
                key_data['last_used'] = datetime.utcnow().isoformat()
                key_data['usage_count'] = key_data.get('usage_count', 0) + 1
                
                return {
                    'valid': True,
                    'customer_id': customer.customer_id,
                    'customer_name': customer.name,
                    'company': customer.company,
                    'subscription_status': customer.subscription_status,
                    'site_id': key_data.get('site_id')
                }
        
        return {'valid': False, 'error': 'API key revoked or inactive'}
    
    def create_admin_user(self, email: str, name: str, company: str = "Lemma Admin") -> Dict[str, Any]:
        """Create an admin user account"""
        try:
            # Check if user already exists
            existing_customer = self.get_customer_by_email(email)
            if existing_customer:
                # Upgrade existing user to admin
                existing_customer.role = 'admin'
                existing_customer.permissions = ['admin_access', 'user_management', 'system_config']
                # Set password if not already set
                if not existing_customer.password_hash:
                    existing_customer.password_hash = self.hash_password("admin123")
                
                # Update in database
                try:
                    db = get_db()
                    db_customer = db.query(DBCustomer).filter(DBCustomer.email == email).first()
                    if db_customer:
                        db_customer.role = 'admin'
                        db_customer.permissions = ['admin_access', 'user_management', 'system_config']
                        if not db_customer.password_hash:
                            db_customer.password_hash = self.hash_password("admin123")
                        db.commit()
                    db.close()
                except Exception as e:
                    logger.error(f"Failed to update admin in database: {e}")
                    db.rollback()
                    db.close()
                
                logger.info(f"Upgraded existing user to admin: {email}")
                return {
                    'success': True,
                    'message': 'User upgraded to admin',
                    'customer_id': existing_customer.customer_id
                }
            
            # Create new admin user with default password
            result = self.create_customer(email, name, company, password="admin123")
            if result['success']:
                # Upgrade to admin role
                customer = self.get_customer(result['customer_id'])
                if customer:
                    customer.role = 'admin'
                    customer.permissions = ['admin_access', 'user_management', 'system_config', 'analytics_access']
                    
                    # Update in database
                    try:
                        db = get_db()
                        db_customer = db.query(DBCustomer).filter(DBCustomer.customer_id == result['customer_id']).first()
                        if db_customer:
                            db_customer.role = 'admin'
                            db_customer.permissions = ['admin_access', 'user_management', 'system_config', 'analytics_access']
                            db.commit()
                        db.close()
                    except Exception as e:
                        logger.error(f"Failed to update new admin in database: {e}")
                        db.rollback()
                        db.close()
                    logger.info(f"Created new admin user: {email}")
                    
                return {
                    'success': True,
                    'message': 'Admin user created successfully',
                    'customer_id': result['customer_id'],
                    'api_key': result['api_key']
                }
            else:
                return result
                
        except Exception as e:
            logger.error(f"Error creating admin user: {e}")
            return {
                'success': False,
                'error': 'Failed to create admin user'
            }

# Global customer manager instance
customer_manager = CustomerAccountManager()

# API Routes

@customer_accounts_bp.route('/register', methods=['GET', 'POST'])
@cross_origin(origins=_public_cors_origins(), supports_credentials=True)
def register():
    """Customer registration page and handler - SECURE VERSION"""
    if request.method == 'GET':
        return render_template(
            'modern/register.html',
            invite_only_mode=_is_invite_only_mode_enabled()
        )
    
    # SECURITY: Redirect POST requests to secure registration
    elif request.method == 'POST':
        logger.warning("🚨 Insecure registration attempt blocked - redirecting to secure endpoint")
        return jsonify({
            'success': False,
            'error': 'Registration has been moved to secure endpoint',
            'secure_endpoint': '/api/customer/register-secure',
            'message': 'Please use the secure registration endpoint that requires email confirmation'
        }), 301
    
    try:
        data = request.get_json() if request.is_json else request.form
        
        email = data.get('email', '').strip().lower()
        name = data.get('name', '').strip()
        company = data.get('company', '').strip()
        billing_email = data.get('billing_email', '').strip().lower()
        
        # Validation
        if not all([email, name, company]):
            return jsonify({
                'success': False,
                'error': 'Email, name, and company are required'
            }), 400
        
        if '@' not in email:
            return jsonify({
                'success': False,
                'error': 'Invalid email address'
            }), 400
        
        # Create customer account
        result = customer_manager.create_customer(
            email=email,
            name=name,
            company=company,
            billing_email=billing_email or email
        )
        
        if result['success']:
            # Issue REAL permission lemma using Ed25519 crypto
            # (No session storage - client stores credential in wallet)
            permission_lemma_data = None
            user_did = None
            issuer_did = None
            
            try:
                from .real_iam_manager import get_or_create_site_manager
                from .ppid import derive_ppid_did
                
                # Get platform IAM manager with Ed25519 keypair
                manager = get_or_create_site_manager('lemma_platform', 'lemma.id')
                
                if manager:
                    # Ensure customer_access permission exists
                    if 'customer_access' not in manager.permissions:
                        manager.add_permission({
                            'permission_id': 'customer_access',
                            'display_name': 'Customer Access',
                            'scope': ['customer_dashboard', 'api_management'],
                            'conditions': [],
                            'priority': 50
                        })
                    
                    # Derive user DID from email
                    user_did = derive_ppid_did(email, 'lemma.id')
                    
                    # Issue permission lemma with REAL Ed25519 signature
                    permission_lemma_data = manager.issue_permission_lemma(
                        user_did,
                        'customer_access',
                        expiry_days=90,
                        custom_claims={
                            'siteId': 'lemma.id',
                            'accountType': 'customer',
                            'permissionId': 'customer_access',
                            'email': email,
                            'scope': ['customer_dashboard', 'api_management']
                        }
                    )
                    
                    # Add W3C type field
                    permission_lemma_data['type'] = ['VerifiableCredential', 'PermissionLemma']
                    permission_lemma_data['packageType'] = 'permission'
                    
                    if 'credentialSubject' in permission_lemma_data:
                        permission_lemma_data['credentialSubject']['packageType'] = 'permission'
                    if 'claims' in permission_lemma_data:
                        permission_lemma_data['claims']['packageType'] = 'permission'
                    
                    issuer_did = manager.issuer_did
                    logger.info(f"Issued customer permission lemma for {email} with Ed25519 signature")
                    
            except Exception as e:
                logger.warning(f"Failed to issue permission lemma for {email}: {e}")
                # Fallback: still return success but without lemma
                user_did = f"did:lemma:customer:{result['customer_id']}"
            
            return jsonify({
                'success': True,
                'customer_id': result['customer_id'],
                'api_key': result['api_key'],
                'user_did': user_did,
                'issuer_did': issuer_did,
                'permission_lemma_issued': permission_lemma_data is not None,
                'permission_lemma': permission_lemma_data,
                'redirect_url': '/wallet'
            })
        else:
            return jsonify(result), 400
            
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return jsonify({
            'success': False,
            'error': 'Registration failed'
        }), 500


@customer_accounts_bp.route('/api/customer/register-wallet-developer', methods=['POST'])
@cross_origin(origins=_public_cors_origins(), supports_credentials=True, allow_headers=['Content-Type', 'Authorization'])
def register_wallet_developer():
    """
    Wallet-first developer registration for lemma.id.

    Requires a person-root IDV wallet binding. Creates customer + platform
    membership and issues a signed developer_access credential for the wallet.
    """
    try:
        from api.platform_owner import enforce_platform_login_wallet

        data = request.get_json(silent=True) or {}
        email = (data.get('email') or '').strip().lower()
        name = (data.get('name') or '').strip()
        company = (data.get('company') or '').strip()
        billing_email = (data.get('billing_email') or '').strip().lower()
        invite_code = (data.get('invite_code') or '').strip()
        client_ppid = (data.get('ppid') or '').strip()
        wallet_id = (data.get('wallet_id') or '').strip()
        passkey_credential_id = (data.get('passkey_credential_id') or '').strip() or None

        if not all([email, name, company]):
            return jsonify({'success': False, 'error': 'Email, name, and company are required'}), 400
        if '@' not in email:
            return jsonify({'success': False, 'error': 'Invalid email address'}), 400
        if _is_invite_only_mode_enabled() and not _is_valid_invite_code(invite_code):
            return jsonify({'success': False, 'error': 'Invite code required or invalid'}), 403

        ppid, denied = enforce_platform_login_wallet(
            client_ppid=client_ppid or None,
            wallet_id=wallet_id or None,
            passkey_credential_id=passkey_credential_id,
        )
        if denied:
            return jsonify(denied[0]), denied[1]

        from api.services.wallet_service import (
            _has_platform_membership,
            _upsert_platform_membership,
            issue_permission_lemma,
        )

        if _has_platform_membership(ppid, site_id='lemma.id'):
            return jsonify(
                {
                    'success': False,
                    'error': 'platform_membership_exists',
                    'message': 'This wallet is already registered. Sign in instead.',
                }
            ), 409

        existing_email = customer_manager.get_customer_by_email(email)
        if existing_email and (existing_email.customer_did or '') not in ('', ppid):
            return jsonify(
                {
                    'success': False,
                    'error': 'email_in_use',
                    'message': 'An account with this email already exists.',
                }
            ), 400

        if existing_email and existing_email.customer_did == ppid:
            customer_id = existing_email.customer_id
            api_key = None
        else:
            result = customer_manager.create_customer(
                email=email,
                name=name,
                company=company,
                billing_email=billing_email or email,
                customer_did=ppid,
                wallet_id=wallet_id or None,
                display_name=name,
                role='developer',
            )
            if not result.get('success'):
                return jsonify(result), 400
            customer_id = result['customer_id']
            api_key = result.get('api_key')

        for site_key in ('lemma.id', 'lemma_platform'):
            _upsert_platform_membership(
                ppid,
                site_key,
                'developer',
                wallet_id=wallet_id or None,
                passkey_credential_id=passkey_credential_id,
            )

        try:
            from api.database import get_db, PlatformUser

            db = get_db()
            try:
                platform_user = db.query(PlatformUser).filter(PlatformUser.user_did == ppid).first()
                if platform_user:
                    platform_user.email = email
                    platform_user.display_name = name
                    platform_user.verification_level = 'human_verified'
                    db.commit()
            finally:
                db.close()
        except Exception as profile_err:
            logger.warning("Platform user profile update failed (non-fatal): %s", profile_err)

        permission_lemma = issue_permission_lemma(
            subject_ppid=ppid,
            site_id='lemma.id',
            permissions=['developer', 'write', 'read', 'access'],
            scope=['developer', 'write', 'read'],
            permission_id='developer_access',
            account_type='developer',
            granted_by='wallet_developer_registration',
            custom_claims={
                'email': email,
                'company': company,
                'accountType': 'developer',
                'permissionId': 'developer_access',
                'permission_level': 'developer',
                'permissionAliases': ['developer_access', 'developer'],
                'issued_via': 'wallet_developer_registration',
                'site_domain': 'lemma.id',
            },
        )
        permission_lemma['type'] = ['VerifiableCredential', 'PermissionLemma']
        permission_lemma['packageType'] = 'permission'

        logger.info("Wallet developer registered %s for %s", ppid[:24], email)
        return jsonify(
            {
                'success': True,
                'customer_id': customer_id,
                'ppid': ppid,
                'api_key': api_key,
                'permission_lemma': permission_lemma,
                'permission_level': 'developer',
                'message': 'Developer account created. Store your API key and wallet credential securely.',
            }
        ), 201
    except Exception as exc:
        logger.error("Wallet developer registration failed: %s", exc)
        return jsonify({'success': False, 'error': 'registration_failed', 'message': str(exc)}), 500


@customer_accounts_bp.route('/api/customer/register-secure', methods=['POST'])
@cross_origin(origins=_public_cors_origins(), supports_credentials=True, allow_headers=['Content-Type', 'Authorization'])
def register_secure():
    """
    Secure customer registration endpoint - requires email confirmation.
    This is the actual registration handler that creates customer accounts.
    """
    try:
        data = request.get_json() if request.is_json else request.form
        
        email = data.get('email', '').strip().lower()
        name = data.get('name', '').strip()
        company = data.get('company', '').strip()
        billing_email = data.get('billing_email', '').strip().lower()
        invite_code = data.get('invite_code', '').strip()
        
        # Validation
        if not all([email, name, company]):
            return jsonify({
                'success': False,
                'error': 'Email, name, and company are required'
            }), 400
        
        if '@' not in email:
            return jsonify({
                'success': False,
                'error': 'Invalid email address'
            }), 400

        if _is_invite_only_mode_enabled() and not _is_valid_invite_code(invite_code):
            return jsonify({
                'success': False,
                'error': 'Invite code required or invalid'
            }), 403
        
        # Check if customer already exists
        existing = customer_manager.get_customer_by_email(email)
        if existing:
            return jsonify({
                'success': False,
                'error': 'An account with this email already exists. Please sign in instead.'
            }), 400
        
        # Create customer account
        result = customer_manager.create_customer(
            email=email,
            name=name,
            company=company,
            billing_email=billing_email or email
        )
        
        if result['success']:
            # Create user DID for this customer
            # (No session storage - client receives permission lemma in response)
            user_did = f"did:lemma:customer:{result['customer_id']}"
            
            # Send email confirmation (in production)
            try:
                from .iam_email_confirmation import send_confirmation_email
                confirmation_result = send_confirmation_email(
                    email=email,
                    customer_id=result['customer_id'],
                    name=name
                )
                logger.info(f"Confirmation email sent to {email}: {confirmation_result}")
            except Exception as e:
                logger.warning(f"Failed to send confirmation email: {e}")
            
            logger.info(f"Customer registered: {email} -> {result['customer_id']}")
            
            return jsonify({
                'success': True,
                'customer_id': result['customer_id'],
                'message': 'Account created. Please check your email to confirm your account and receive your API keys.',
                'email_sent': True
            })
        else:
            return jsonify(result), 400
            
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return jsonify({
            'success': False,
            'error': 'Registration failed. Please try again.'
        }), 500


@customer_accounts_bp.route('/login', methods=['GET', 'POST'])
@cross_origin(origins=_public_cors_origins(), supports_credentials=True, allow_headers=['Content-Type', 'Authorization'])
def login():
    """Customer login page and handler"""
    if request.method == 'GET':
        return render_template('modern/login.html')
    
    try:
        data = request.get_json() if request.is_json else request.form
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        if not email:
            return jsonify({
                'success': False,
                'error': 'Email is required'
            }), 400
            
        if not password:
            return jsonify({
                'success': False,
                'error': 'Password is required'
            }), 400
        
        # Find customer
        customer = customer_manager.get_customer_by_email(email)
        if not customer:
            return jsonify({
                'success': False,
                'error': 'Invalid email or password'
            }), 401
            
        # Verify password
        if not customer.password_hash or not customer_manager.verify_password(password, customer.password_hash):
            return jsonify({
                'success': False,
                'error': 'Invalid email or password'
            }), 401
        
        # Update login tracking
        customer.last_login = datetime.utcnow()
        customer.login_count += 1
        
        # Issue REAL permission lemma using Ed25519 crypto
        permission_lemma_data = None
        user_did = None
        issuer_did = None
        
        try:
            from .real_iam_manager import get_or_create_site_manager
            from .ppid import derive_ppid_did
            
            # Get platform IAM manager with Ed25519 keypair
            manager = get_or_create_site_manager('lemma_platform', 'lemma.id')
            
            if manager:
                # Determine permission level based on role
                permission_id = 'admin_access' if customer.role == 'admin' else 'customer_access'
                scope = ['platform_admin', 'customer_management', 'site_management', 'billing_access'] if customer.role == 'admin' else ['customer_dashboard', 'api_management']

                from api.platform_owner import platform_owner_enforcement_enabled
                if customer.role == 'admin' and platform_owner_enforcement_enabled():
                    permission_id = 'customer_access'
                    scope = ['customer_dashboard', 'api_management']
                
                # Ensure permission type exists
                if permission_id not in manager.permissions:
                    manager.add_permission({
                        'permission_id': permission_id,
                        'display_name': 'Platform Admin' if customer.role == 'admin' else 'Customer Access',
                        'scope': scope,
                        'conditions': [],
                        'priority': 100 if customer.role == 'admin' else 50
                    })
                
                # Derive user DID from email
                user_did = derive_ppid_did(email, 'lemma.id')
                
                # Issue permission lemma with REAL Ed25519 signature
                permission_lemma_data = manager.issue_permission_lemma(
                    user_did,
                    permission_id,
                    expiry_days=90,
                    custom_claims={
                        'siteId': 'lemma.id',
                        'accountType': customer.role,
                        'permissionId': permission_id,
                        'email': email,
                        'scope': scope
                    }
                )
                
                # Add W3C type field
                permission_lemma_data['type'] = ['VerifiableCredential', 'PermissionLemma']
                permission_lemma_data['packageType'] = 'permission'
                
                if 'credentialSubject' in permission_lemma_data:
                    permission_lemma_data['credentialSubject']['packageType'] = 'permission'
                if 'claims' in permission_lemma_data:
                    permission_lemma_data['claims']['packageType'] = 'permission'
                
                issuer_did = manager.issuer_did
                logger.info(f"Issued {permission_id} lemma for {email} with Ed25519 signature")
                
        except Exception as e:
            logger.warning(f"Failed to issue permission lemma for {email}: {e}")
            # Fallback: still return success but without lemma
            user_did = f"did:lemma:customer:{customer.customer_id}"
        
        return jsonify({
            'success': True,
            'customer_id': customer.customer_id,
            'user_did': user_did,
            'issuer_did': issuer_did,
            'permission_lemma_active': permission_lemma_data is not None,
            'permission_lemma': permission_lemma_data,
            'role': customer.role,
            'redirect_url': '/dashboard'
        })
        
    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({
            'success': False,
            'error': 'Login failed'
        }), 500

# Dashboard route moved to app.py - using new permission lemma-based access control

@customer_accounts_bp.route('/api/customer/info')
def get_customer_info():
    """Get customer information (session-free: requires credential in request)"""
    customer_id = _extract_customer_id_from_request()
    if not customer_id:
        return jsonify({'error': 'Authentication required'}), 401
    
    customer = customer_manager.get_customer(customer_id)
    if not customer:
        return jsonify({'error': 'Customer not found'}), 404
    
    return jsonify({
        'success': True,
        'customer': asdict(customer)
    })

@customer_accounts_bp.route('/api/customer/api-keys', methods=['GET', 'POST', 'DELETE'])
@require_customer_or_admin
def manage_api_keys():
    """Manage customer API keys (session-free)"""
    customer_id = _extract_customer_id_from_request()
    if not customer_id:
        return jsonify({'error': 'Authentication required'}), 401
    
    if request.method == 'GET':
        # Get all API keys
        customer = customer_manager.get_customer(customer_id)
        if not customer:
            return jsonify({'error': 'Customer not found'}), 404
        
        # Filter out API keys that have no site_id (legacy default keys)
        # These were created before site registration was required
        raw_keys = [k for k in (customer.api_keys or []) if k.get('site_id')]
        
        # Sanitize API keys for response - never expose full keys or hashes
        sanitized_keys = []
        for key in raw_keys:
            sanitized_key = {
                'name': key.get('name', 'API Key'),
                'site_id': key.get('site_id'),
                'key_hint': key.get('key_hint') or (key.get('key', '')[-8:] if key.get('key') else ''),
                'created_at': key.get('created_at'),
                'last_used': key.get('last_used'),
                'usage_count': key.get('usage_count', 0),
                'status': key.get('status', 'active')
            }
            sanitized_keys.append(sanitized_key)
        
        return jsonify({
            'success': True,
            'api_keys': sanitized_keys,
            'sites': customer.sites or []
        })
    
    elif request.method == 'POST':
        # Generate new API key
        data = request.get_json() or {}
        key_name = data.get('name', 'API Key')
        site_id = data.get('site_id')
        
        result = customer_manager.generate_additional_api_key(customer_id, key_name, site_id=site_id)
        return jsonify(result)
    
    elif request.method == 'DELETE':
        # Revoke API key - supports both full key and hint-based revocation
        data = request.get_json() or {}
        api_key = data.get('api_key')
        site_id = data.get('site_id')
        key_hint = data.get('key_hint')
        
        if api_key:
            # Legacy: revoke by full key
            result = customer_manager.revoke_api_key(customer_id, api_key)
        elif site_id and key_hint:
            # New: revoke by site_id + key_hint (secure method)
            result = customer_manager.revoke_api_key_by_hint(customer_id, site_id, key_hint)
        else:
            return jsonify({'error': 'Either api_key or (site_id + key_hint) required'}), 400
        
        return jsonify(result)

@customer_accounts_bp.route('/api/customer/api-keys/rotate', methods=['POST'])
@cross_origin()
@require_customer_or_admin
def rotate_api_key():
    """
    Rotate an API key: generate a new key and revoke the old one.
    
    This is useful when:
    - A key may have been compromised
    - Regular security rotation policy
    - Team member with key access leaves
    
    Request body:
        site_id: The site the key belongs to
        key_hint: The hint (last 8 chars) of the key to rotate
    
    Returns:
        New API key (shown only once) and confirmation
    """
    customer_id = _extract_customer_id_from_request()
    if not customer_id:
        return jsonify({'error': 'Authentication required'}), 401
    
    data = request.get_json() or {}
    site_id = data.get('site_id')
    key_hint = data.get('key_hint')
    
    if not site_id or not key_hint:
        return jsonify({'error': 'site_id and key_hint are required'}), 400
    
    result = customer_manager.rotate_api_key(customer_id, site_id, key_hint)
    
    if result.get('success'):
        return jsonify(result)
    else:
        return jsonify(result), 400


@customer_accounts_bp.route('/api/validate-key', methods=['POST'])
def validate_api_key():
    """Validate an API key (for internal use)
    
    Rate limited to prevent brute-force attacks.
    """
    # Get client identifier for rate limiting (IP address)
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if client_ip and ',' in client_ip:
        client_ip = client_ip.split(',')[0].strip()
    
    # Check rate limit
    is_limited, reason = api_key_rate_limiter.is_rate_limited(client_ip)
    if is_limited:
        logger.warning(f"Rate limited API key validation from {client_ip}")
        return jsonify({
            'valid': False, 
            'error': reason,
            'rate_limited': True
        }), 429
    
    data = request.get_json()
    api_key = data.get('api_key')
    
    if not api_key:
        return jsonify({'valid': False, 'error': 'API key required'}), 400
    
    result = customer_manager.validate_api_key(api_key)
    
    # Record the attempt for rate limiting
    api_key_rate_limiter.record_attempt(client_ip, result.get('valid', False))
    
    return jsonify(result)


@customer_accounts_bp.route('/api/customer/register-site', methods=['POST'])
@require_customer_or_admin
def register_customer_site():
    """
    Register a new site for customer + auto-issue admin credential
    This is the developer platform flow for beta customers
    """
    customer_id = _extract_customer_id_from_request()
    if not customer_id:
        return jsonify({'error': 'Authentication required'}), 401
    
    try:
        customer = customer_manager.get_customer(customer_id)
        if not customer:
            return jsonify({'error': 'Customer not found'}), 404
        
        data = request.get_json() or {}
        site_domain = (data.get('site_domain') or '').strip().lower()
        if not site_domain:
            return jsonify({'error': 'site_domain required'}), 400
        
        # Clean site domain (remove protocol, path, trailing slash)
        site_domain = site_domain.replace('https://', '').replace('http://', '')
        site_domain = site_domain.split('/', 1)[0].rstrip('/')
        if not site_domain:
            return jsonify({'error': 'Invalid site_domain'}), 400
        
        site_label = (data.get('site_label') or site_domain).strip()
        environment = (data.get('environment') or 'production').lower()
        if environment not in {'production', 'staging', 'development', 'sandbox'}:
            environment = 'production'
        company_name = (data.get('company_name') or customer.company or '').strip()
        contact_email = (data.get('contact_email') or customer.email or '').strip()
        key_name = (data.get('key_name') or f"{site_label or site_domain} Key").strip() or 'API Key'
        
        # Generate site_id (deterministic from domain)
        site_id = f"site_{hashlib.sha256(site_domain.encode()).hexdigest()[:12]}"
        
        # Create site with IAM system (generates Ed25519 keypair)
        try:
            from api.real_iam_manager import RealIAMSubnetManager
            manager = RealIAMSubnetManager(site_id, site_domain)
        except Exception as e:
            logger.error(f"Failed to create IAM manager: {e}")
            return jsonify({'error': 'Failed to create site IAM system'}), 500
        
        if not manager:
            return jsonify({'error': 'Failed to create site'}), 500
        
        # Ensure admin permission exists
        if 'admin' not in manager.permissions:
            manager.add_permission({
                'permission_id': 'admin',
                'display_name': 'Administrator',
                'scope': ['*'],
                'conditions': [],
                'priority': 100
            })
        
        user_did = f"did:lemma:customer:{customer_id}"
        user_email = customer.email or ''
        
        # Issue admin credential
        admin_credential = manager.issue_permission_lemma(
            user_did,
            'admin',
            expiry_days=90,
            custom_claims={
                'email': user_email or None,  # Exclude if empty
                'site_domain': site_domain,
                'site_label': site_label,
                'environment': environment,
                'siteId': site_id,
                'accountType': 'admin',
                'permissionId': 'admin',
                'issued_via': 'developer_platform'
            }
        )
        admin_credential['type'] = ['VerifiableCredential', 'PermissionLemma']
        admin_credential['packageType'] = 'permission'
        
        # Persist site metadata
        sites = list(customer.sites or [])
        timestamp = datetime.utcnow().isoformat()
        site_entry = next((s for s in sites if s.get('site_id') == site_id), None)
        if site_entry:
            site_entry.update({
                'site_domain': site_domain,
                'site_label': site_label,
                'environment': environment,
                'company_name': company_name,
                'contact_email': contact_email,
                'status': 'active',
                'updated_at': timestamp,
                'issuer_did': manager.issuer.get_did()
            })
        else:
            site_entry = {
                'site_id': site_id,
                'site_domain': site_domain,
                'site_label': site_label,
                'environment': environment,
                'company_name': company_name,
                'contact_email': contact_email,
                'status': 'active',
                'created_at': timestamp,
                'updated_at': timestamp,
                'issuer_did': manager.issuer.get_did()
            }
            sites.append(site_entry)
        
        customer.sites = sites
        
        # Update database record - DUAL WRITE to both JSON column and normalized table
        if customer_manager.db_available:
            db = None
            try:
                db = get_db()
                db_customer = db.query(DBCustomer).filter(DBCustomer.customer_id == customer_id).first()
                if db_customer:
                    # Write to JSON column (legacy)
                    db_customer.sites = sites
                    db.commit()
                
                # Also write to normalized sites table (new)
                try:
                    from api.storage_helpers import upsert_site_to_postgres
                    upsert_site_to_postgres(
                        site_id=site_id,
                        site_domain=site_domain,
                        customer_id=customer_id,
                        company_name=company_name,
                        admin_email=contact_email,
                        environment=environment,
                        site_label=site_label
                    )
                    logger.info(f"✅ Site {site_id} written to PostgreSQL sites table")
                except Exception as pg_err:
                    logger.warning(f"⚠️ Could not write to PostgreSQL sites table: {pg_err}")
                    # Don't fail - JSON write succeeded
                
            except Exception as e:
                logger.error(f"Failed to persist site metadata for {customer_id}: {e}")
                if db is not None:
                    db.rollback()
                return jsonify({'error': 'Failed to store site metadata'}), 500
            finally:
                if db is not None:
                    db.close()
        else:
            customer_manager.cache_customer(customer)
        
        # Generate API key tied to this site
        key_result = customer_manager.generate_additional_api_key(customer_id, key_name, site_id=site_id)
        if not key_result.get('success'):
            return jsonify(key_result), 400
        
        site_entry['last_api_key_label'] = key_name
        site_entry['last_api_key_created_at'] = datetime.utcnow().isoformat()
        
        logger.info(f"✅ Customer {user_email or customer_id} registered site {site_domain} ({site_id}) and received API key")
        
        return jsonify({
            'success': True,
            'site_id': site_id,
            'site_domain': site_domain,
            'site': site_entry,
            'issuer_did': manager.issuer.get_did(),
            'admin_credential': admin_credential,
            'api_key': key_result.get('api_key'),
            'key_data': key_result.get('key_data'),
            'message': f'Site registered. Admin credential issued and API key generated for {site_domain}'
        })
    
    except Exception as e:
        logger.error(f"Site registration error: {e}", exc_info=True)
        return jsonify({'error': 'Failed to register site'}), 500


@customer_accounts_bp.route('/api/customer/sites', methods=['GET'])
def get_customer_sites():
    """Get all sites registered by customer
    
    Authentication: Wallet credential (Bearer token) or API key
    """
    try:
        customer_id = _extract_customer_id_from_request()
        
        if not customer_id:
            return jsonify({'error': 'Authentication required'}), 401
        
        customer = customer_manager.get_customer(customer_id)
        if not customer:
            return jsonify({'error': 'Customer not found'}), 404
        
        sites = getattr(customer, 'sites', []) or []
        
        return jsonify({
            'success': True,
            'sites': sites,
            'count': len(sites)
        })
    except Exception as e:
        logger.error(f"Get sites error: {e}")
        return jsonify({'error': str(e)}), 500

# Note: Admin lemma issuance moved to /api/admin/issue-admin-lemma in dashboard_api.py
# This keeps all admin-related endpoints in one place

@customer_accounts_bp.route('/create-test-accounts')
def create_test_accounts():
    """Create basic test accounts for development - REMOVE IN PRODUCTION"""
    try:
        results = []
        
        # Create admin account
        admin_result = customer_manager.create_admin_user(
            email="admin@lemma.id",
            name="Lemma Administrator", 
            company="Lemma Platform"
        )
        results.append({
            'type': 'admin',
            'email': 'admin@lemma.id',
            'result': admin_result
        })
        
        # Create test customer account
        customer_result = customer_manager.create_customer(
            email="customer@test.com",
            name="Test Customer",
            company="Test Company Inc",
            billing_email="billing@test.com",
            password="customer123"
        )
        results.append({
            'type': 'customer', 
            'email': 'customer@test.com',
            'result': customer_result
        })
        
        return jsonify({
            'success': True,
            'message': 'Test accounts created successfully',
            'accounts': results,
            'login_info': {
                'admin': {
                    'email': 'admin@lemma.id',
                    'password': 'admin123',
                    'login_url': '/login',
                    'dashboard_url': '/admin'
                },
                'customer': {
                    'email': 'customer@test.com',
                    'password': 'customer123',
                    'login_url': '/login',
                    'dashboard_url': '/dashboard',
                    'api_key': customer_result.get('api_key') if customer_result.get('success') else None
                }
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Failed to create test accounts: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@customer_accounts_bp.route('/logout')
def logout():
    """Customer logout — clear server session + wallet cookies + global session."""
    session.pop('customer_id', None)

    # Clear global wallet session so other devices detect the lock
    # Extract wallet_id from the session token (more reliable than CSRF cookie)
    session_token = request.cookies.get('lemma_wallet_session')
    wallet_id = None
    if session_token:
        try:
            from auth.session_manager import revoke_wallet_sessions
            # Parse wallet_id from token without full validation (we're revoking it anyway)
            parts = session_token.split(':')
            if len(parts) in (5, 7):
                wallet_id = parts[0]
        except Exception:
            pass

    if wallet_id:
        try:
            from api.wallet_session_sync import _clear_global_session
            _clear_global_session(wallet_id)
            # Server-side revocation: blacklist all sessions for this wallet
            from auth.session_manager import revoke_wallet_sessions
            revoke_wallet_sessions(wallet_id)
        except Exception:
            pass

    # Redirect to /app (always serves wallet_simple.html) with flag so
    # client-side can broadcast LOCK on BroadcastChannel.
    # Note: can't use / because smart router checks cookies we just deleted
    # and would serve the marketing page instead of wallet_simple.html.
    response = make_response(redirect('/app?logged_out=1'))
    response.delete_cookie('lemma_wallet_session', path='/')
    response.delete_cookie('lemma_wallet_csrf', path='/')
    return response

# Export the manager for use in other modules
__all__ = ['customer_accounts_bp', 'customer_manager']
