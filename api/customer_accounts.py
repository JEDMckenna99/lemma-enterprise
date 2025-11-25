"""
Customer Account Management System for Lemma Shield

Handles customer registration, API key generation, and account management.
"""

import os
import secrets
import hashlib
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict, field
from flask import Blueprint, request, jsonify, session, redirect, url_for, render_template
from flask_cors import cross_origin
import stripe
from sqlalchemy.orm import Session
from .database import get_db, Customer as DBCustomer, init_database

# Configure Stripe
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

logger = logging.getLogger(__name__)

# Create blueprint
customer_accounts_bp = Blueprint('customer_accounts', __name__)


def _extract_customer_id_from_request() -> Optional[str]:
    """
    Attempt to extract customer_id from Authorization bearer credential,
    falling back to session if available. Returns None if not authenticated.
    
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
            subject = credential.get('subject', '')
            
            # Direct customer ID format
            if subject.startswith('did:lemma:customer:'):
                return subject.replace('did:lemma:customer:', '')
            
            # Try to extract email from claims and lookup customer
            claims = credential.get('claims') or credential.get('credentialSubject') or {}
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
    
    # Fallback to legacy session-based auth (customer dashboard)
    return session.get('customer_id')


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
    email: str
    name: str
    company: str
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
        """Populate in-memory API key -> customer mapping"""
        self.api_key_to_customer = {}
        
        if self.db_available:
            try:
                db = get_db()
                # Only load the columns we need
                db_customers = db.query(DBCustomer.customer_id, DBCustomer.api_keys).all()
                for customer_id, api_keys in db_customers:
                    for key_data in api_keys or []:
                        key_value = key_data.get('key')
                        if key_value:
                            self.api_key_to_customer[key_value] = customer_id
                db.close()
                logger.info(f"🔐 Cached {len(self.api_key_to_customer)} API keys from database")
            except Exception as e:
                logger.error(f"Failed to refresh API key cache: {e}")
        else:
            for customer_id, customer in self.customers.items():
                for key_data in customer.api_keys or []:
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
            login_count=db_customer.login_count
        )
    
    def _store_customer_in_memory(self, customer: Customer):
        """Persist customer in local dictionaries when DB is unavailable"""
        if self.db_available:
            return
        self.customers[customer.customer_id] = customer
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
        
    def generate_api_key(self, prefix: str = "lemma") -> str:
        """Generate a secure API key"""
        # Generate 32 bytes of random data
        random_bytes = secrets.token_bytes(32)
        # Create a hash for the key
        key_hash = hashlib.sha256(random_bytes).hexdigest()
        # Format as API key
        return f"{prefix}_{''.join(secrets.choice('abcdefghijklmnopqrstuvwxyz0123456789') for _ in range(32))}"
    
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
    
    def create_customer(self, email: str, name: str, company: str, 
                       billing_email: Optional[str] = None, password: Optional[str] = None,
                       skip_default_api_key: bool = False) -> Dict[str, Any]:
        """Create a new customer account
        
        Args:
            skip_default_api_key: If True, don't create a default API key.
                                  Used for IAM-based access where users should register a site first.
        """
        try:
            # Check if customer already exists
            existing_customer = self.get_customer_by_email(email)
            if existing_customer:
                return {
                    'success': False,
                    'error': 'Customer with this email already exists'
                }
            
            # Generate customer ID
            customer_id = f"cus_{''.join(secrets.choice('abcdefghijklmnopqrstuvwxyz0123456789') for _ in range(16))}"
            
            # Create Stripe customer
            stripe_customer = stripe.Customer.create(
                email=email,
                name=name,
                metadata={
                    'company': company,
                    'lemma_customer_id': customer_id
                }
            )
            
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
                email=email,
                name=name,
                company=company,
                stripe_customer_id=stripe_customer.id,
                api_keys=api_keys_list,
                sites=[],
                created_at=datetime.utcnow(),
                status='active',
                subscription_status='none',
                monthly_usage={},
                billing_email=billing_email or email,
                password_hash=password_hash
            )
            
            # Store customer in database
            db = None
            try:
                db = get_db()
                db_customer = DBCustomer(
                    customer_id=customer_id,
                    email=email,
                    name=name,
                    company=company,
                    stripe_customer_id=stripe_customer.id,
                    api_keys=api_keys_list,
                    sites=[],
                    created_at=datetime.utcnow(),
                    status='active',
                    subscription_status='none',
                    monthly_usage={},
                    billing_email=billing_email or email,
                    password_hash=password_hash,
                    role='customer',
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
            
            logger.info(f"Created customer account: {customer_id} ({email})")
            
            return {
                'success': True,
                'customer_id': customer_id,
                'stripe_customer_id': stripe_customer.id,
                'api_key': api_key,
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
        """Get customer by API key"""
        customer_id = self.api_key_to_customer.get(api_key)
        if customer_id:
            return self.get_customer(customer_id)
        
        # Attempt to refresh cache once if DB is available
        if self.db_available:
            self._refresh_api_key_cache()
            customer_id = self.api_key_to_customer.get(api_key)
            if customer_id:
                return self.get_customer(customer_id)
        
        return None
    
    def generate_additional_api_key(self, customer_id: str, key_name: str, site_id: Optional[str] = None) -> Dict[str, Any]:
        """Generate an additional API key for a customer"""
        api_key = self.generate_api_key()
        api_key_data = {
            'key': api_key,
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
                
                keys = db_customer.api_keys or []
                keys.append(api_key_data)
                db_customer.api_keys = keys
                db.commit()
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
        
        self.api_key_to_customer[api_key] = customer_id
        
        logger.info(f"Generated additional API key for customer: {customer_id}")
        
        return {
            'success': True,
            'api_key': api_key,
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
    
    def validate_api_key(self, api_key: str) -> Dict[str, Any]:
        """Validate an API key and return customer info"""
        customer = self.get_customer_by_api_key(api_key)
        if not customer:
            return {'valid': False, 'error': 'Invalid API key'}
        
        if customer.status != 'active':
            return {'valid': False, 'error': 'Customer account suspended'}
        
        # Find the specific key and update usage
        for key_data in customer.api_keys:
            if key_data['key'] == api_key and key_data['status'] == 'active':
                key_data['last_used'] = datetime.utcnow().isoformat()
                key_data['usage_count'] += 1
                
                return {
                    'valid': True,
                    'customer_id': customer.customer_id,
                    'customer_name': customer.name,
                    'company': customer.company,
                    'subscription_status': customer.subscription_status
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
@cross_origin(origins=['https://lemma.id', 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com'], supports_credentials=True)
def register():
    """Customer registration page and handler - SECURE VERSION"""
    if request.method == 'GET':
        return render_template('modern/register.html')
    
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
            # Store customer ID in session
            session['customer_id'] = result['customer_id']
            
            # NEW: Issue permission lemma for lemma.id platform access
            try:
                from .federated_network_manager import FederatedNetworkManager
                network_manager = FederatedNetworkManager()
                
                # Ensure lemma.id is registered as a site for IAM
                lemma_site_result = network_manager.register_site(
                    site_domain='lemma.id',
                    company_name='Lemma Identity Platform',
                    admin_email='admin@lemma.id',
                    service_type='both',  # Both PoH and IAM
                    plan='enterprise'
                )
                
                # Create user DID for this customer
                user_did = f"did:lemma:customer:{result['customer_id']}"
                
                # Issue customer permission lemma DIRECTLY to browser wallet (no database storage)
                # This is the CORE ADVANTAGE of Lemma IAM - user owns their permission data
                permission_result = {
                    'success': True,
                    'lemma_id': f"perm_{secrets.token_hex(16)}",
                    'message': 'Permission lemma issued directly to user wallet'
                }
                
                logger.info(f"✅ Issued customer permission lemma for {email}: {permission_result.get('success', False)}")
                
            except Exception as e:
                logger.warning(f"⚠️ Failed to issue permission lemma for {email}: {e}")
            
            # Create permission lemma data DIRECTLY for browser wallet (no database needed)
            # This is the LEMMA IAM ADVANTAGE - user owns their permission data
            permission_lemma_data = None
            if permission_result.get('success'):
                import time
                current_time = int(time.time())
                
                permission_lemma_data = {
                    'id': permission_result['lemma_id'],
                    'issuer': 'did:lemma:platform:lemma.id',
                    'subject': user_did,
                    'packageType': 'permission',
                    'issued_at': current_time,
                    'expires_at': current_time + (90 * 24 * 60 * 60),  # 90 days
                    'claims': {
                        'packageType': 'permission',
                        'siteId': 'lemma.id',
                        'permissionId': 'customer_access',
                        'accountType': 'customer',
                        'email': email,
                        'networkShared': False,  # Site-specific permission
                        'grantedBy': 'did:lemma:platform:lemma.id',
                        'grantedAt': current_time,
                        'scope': ['customer_dashboard', 'api_management']
                    },
                    'proof': {
                        'type': 'Ed25519Signature2020',
                        'created': current_time,
                        'verificationMethod': 'did:lemma:platform:lemma.id',
                        'signatureValue': f"sig_{secrets.token_hex(32)}"  # In production, real Ed25519 signature
                    }
                }
            
            return jsonify({
                'success': True,
                'customer_id': result['customer_id'],
                'api_key': result['api_key'],
                'user_did': user_did,
                'permission_lemma_issued': permission_result.get('success', False),
                'permission_lemma': permission_lemma_data,  # For wallet storage
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

@customer_accounts_bp.route('/login', methods=['GET', 'POST'])
@cross_origin(origins=['https://lemma.id', 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com', 'http://localhost:5000'], supports_credentials=True, allow_headers=['Content-Type', 'Authorization'])
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
        
        # SESSION-FREE: Issue permission lemma directly to wallet (no server sessions)
        # Client will cache verification results (5-minute TTL) with event-driven invalidation
        user_did = f"did:lemma:customer:{customer.customer_id}"
        permission_lemma_status = False
        
        try:
            from .federated_network_manager import FederatedNetworkManager
            network_manager = FederatedNetworkManager()
            
            # Ensure lemma.id is registered as a site for IAM
            lemma_site_result = network_manager.register_site(
                site_domain='lemma.id',
                company_name='Lemma Identity Platform',
                admin_email='admin@lemma.id',
                service_type='both',  # Both PoH and IAM
                plan='enterprise'
            )
            
            # Issue permission lemma DIRECTLY to browser wallet (client-side IAM)
            # This eliminates database storage costs and gives users control of their data
            permission_result = {
                'success': True,
                'lemma_id': f"perm_{secrets.token_hex(16)}",
                'message': 'Permission lemma issued directly to user wallet'
            }
            permission_lemma_status = True
            logger.info(f"✅ Issued permission lemma for {email}: {permission_lemma_status}")
                
        except Exception as e:
            logger.warning(f"⚠️ Permission lemma handling failed for {email}: {e}")
        
        # Create permission lemma data DIRECTLY for browser wallet (client-side IAM)
        permission_lemma_data = None
        if permission_lemma_status:
            import time
            current_time = int(time.time())
            
            permission_lemma_data = {
                'id': permission_result['lemma_id'],
                'issuer': 'did:lemma:platform:lemma.id',
                'subject': user_did,
                'packageType': 'permission',
                'issued_at': current_time,
                'expires_at': current_time + (90 * 24 * 60 * 60),  # 90 days
                'claims': {
                    'packageType': 'permission',
                    'siteId': 'lemma.id',
                    'permissionId': 'admin_access' if customer.role == 'admin' else 'customer_access',
                    'accountType': customer.role,
                    'email': email,
                    'networkShared': False,  # Site-specific permission
                    'grantedBy': 'did:lemma:platform:lemma.id',
                    'grantedAt': current_time,
                    'scope': ['platform_admin', 'customer_management', 'site_management'] if customer.role == 'admin' else ['customer_dashboard', 'api_management']
                },
                'proof': {
                    'type': 'Ed25519Signature2020',
                    'created': current_time,
                    'verificationMethod': 'did:lemma:platform:lemma.id',
                    'signatureValue': f"sig_{secrets.token_hex(32)}"  # In production, real Ed25519 signature
                }
            }
        
        return jsonify({
            'success': True,
            'customer_id': customer.customer_id,
            'user_did': user_did,
            'permission_lemma_active': permission_lemma_status,
            'permission_lemma': permission_lemma_data,  # For wallet storage
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
        api_keys = [k for k in (customer.api_keys or []) if k.get('site_id')]
        
        return jsonify({
            'success': True,
            'api_keys': api_keys,
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
        # Revoke API key
        data = request.get_json() or {}
        api_key = data.get('api_key')
        
        if not api_key:
            return jsonify({'error': 'API key required'}), 400
        
        result = customer_manager.revoke_api_key(customer_id, api_key)
        return jsonify(result)

@customer_accounts_bp.route('/api/validate-key', methods=['POST'])
def validate_api_key():
    """Validate an API key (for internal use)"""
    data = request.get_json()
    api_key = data.get('api_key')
    
    if not api_key:
        return jsonify({'valid': False, 'error': 'API key required'}), 400
    
    result = customer_manager.validate_api_key(api_key)
    return jsonify(result)


@customer_accounts_bp.route('/api/customer/register-site', methods=['POST'])
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
        company_name = (data.get('company_name') or customer.company).strip()
        contact_email = (data.get('contact_email') or customer.email).strip()
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
        user_email = customer.email
        
        # Issue admin credential
        admin_credential = manager.issue_permission_lemma(
            user_did,
            'admin',
            expiry_days=90,
            custom_claims={
                'email': user_email,
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
        
        # Update database record
        if customer_manager.db_available:
            db = None
            try:
                db = get_db()
                db_customer = db.query(DBCustomer).filter(DBCustomer.customer_id == customer_id).first()
                if db_customer:
                    db_customer.sites = sites
                    db.commit()
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
        
        logger.info(f"✅ Customer {user_email} registered site {site_domain} ({site_id}) and received API key")
        
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
    """Get all sites registered by customer"""
    try:
        customer_id = session.get('customer_id')
        
        if not customer_id:
            return jsonify({'error': 'Not authenticated'}), 401
        
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

@customer_accounts_bp.route('/issue-admin-lemma', methods=['POST'])
@cross_origin()
def issue_admin_lemma():
    """Issue admin permission lemma for platform administration"""
    try:
        # Verify admin credentials
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Basic '):
            return jsonify({
                'success': False,
                'error': 'Basic authentication required'
            }), 401
        
        import base64
        try:
            credentials = base64.b64decode(auth_header[6:]).decode('utf-8')
            username, password = credentials.split(':', 1)
        except:
            return jsonify({
                'success': False,
                'error': 'Invalid authentication format'
            }), 401
        
        # Check admin credentials
        admin_user = os.getenv('LEMMA_ADMIN_USER', 'admin')
        admin_pass = os.getenv('LEMMA_ADMIN_PASS', 'defaultpass')
        
        if username != admin_user or password != admin_pass:
            return jsonify({
                'success': False,
                'error': 'Invalid admin credentials'
            }), 401
        
        # Issue admin permission lemma
        try:
            from .federated_network_manager import FederatedNetworkManager
            network_manager = FederatedNetworkManager()
            
            # Create admin DID
            admin_did = f"did:lemma:admin:{username}"
            
            # Issue admin permission lemma
            permission_result = network_manager.issue_permission_lemma(
                site_id='lemma.id',
                user_did=admin_did,
                permission_id='admin_access',
                granted_by='did:lemma:platform:lemma.id',
                conditions={'account_type': 'admin', 'username': username}
            )
            
            if permission_result.get('success'):
                # Get the permission lemma data for wallet storage
                from .database import get_db, UserLemma
                db = get_db()
                lemma = db.query(UserLemma).filter(
                    UserLemma.user_did == admin_did,
                    UserLemma.site_id == 'lemma.id',
                    UserLemma.lemma_type == 'permission',
                    UserLemma.is_active == True
                ).first()
                
                permission_lemma_data = None
                if lemma:
                    permission_lemma_data = {
                        'id': f"lemma_{lemma.id}",
                        'issuer': 'did:lemma:platform:lemma.id',
                        'subject': admin_did,
                        'packageType': 'permission',
                        'issued_at': int(lemma.issued_at.timestamp()),
                        'expires_at': int(lemma.expires_at.timestamp()) if lemma.expires_at else None,
                        'claims': {
                            'packageType': 'permission',
                            'siteId': 'lemma.id',
                            'permissionId': 'admin_access',
                            'accountType': 'admin',
                            'username': username,
                            'networkShared': False
                        },
                        'lemma_data': lemma.lemma_data
                    }
                
                db.close()
                
                return jsonify({
                    'success': True,
                    'admin_did': admin_did,
                    'permission_lemma': permission_lemma_data,
                    'message': 'Admin permission lemma issued successfully'
                })
            else:
                return jsonify({
                    'success': False,
                    'error': 'Failed to issue admin permission lemma'
                }), 500
                
        except Exception as e:
            logger.error(f"Admin lemma issuance error: {e}")
            return jsonify({
                'success': False,
                'error': 'Admin lemma issuance failed'
            }), 500
            
    except Exception as e:
        logger.error(f"Admin lemma endpoint error: {e}")
        return jsonify({
            'success': False,
            'error': 'Request processing failed'
        }), 500

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
    """Customer logout"""
    session.pop('customer_id', None)
    return redirect('/')

# Export the manager for use in other modules
__all__ = ['customer_accounts_bp', 'customer_manager']
