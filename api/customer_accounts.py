"""
Customer Account Management System for Lemma Shield

Handles customer registration, API key generation, and account management.
"""

import os
import secrets
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict, field
from flask import Blueprint, request, jsonify, session, redirect, url_for, render_template
import stripe

# Configure Stripe
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

logger = logging.getLogger(__name__)

# Create blueprint
customer_accounts_bp = Blueprint('customer_accounts', __name__)

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
    billing_email: Optional[str]
    password_hash: Optional[str] = None  # Hashed password for authentication
    role: str = 'customer'  # 'customer' or 'admin'
    permissions: List[str] = field(default_factory=list)
    last_login: Optional[datetime] = None
    login_count: int = 0

class CustomerAccountManager:
    """Manages customer accounts and API keys"""
    
    def __init__(self):
        # In production, this should be a proper database
        self.customers = {}  # customer_id -> Customer
        self.email_to_customer = {}  # email -> customer_id
        self.api_key_to_customer = {}  # api_key -> customer_id
        
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
                       billing_email: Optional[str] = None, password: Optional[str] = None) -> Dict[str, Any]:
        """Create a new customer account"""
        try:
            # Check if customer already exists
            if email in self.email_to_customer:
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
            
            # Generate initial API key
            api_key = self.generate_api_key()
            api_key_data = {
                'key': api_key,
                'name': 'Default API Key',
                'created_at': datetime.utcnow().isoformat(),
                'last_used': None,
                'usage_count': 0,
                'status': 'active'
            }
            
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
                api_keys=[api_key_data],
                created_at=datetime.utcnow(),
                status='active',
                subscription_status='none',
                monthly_usage={},
                billing_email=billing_email or email,
                password_hash=password_hash
            )
            
            # Store customer
            self.customers[customer_id] = customer
            self.email_to_customer[email] = customer_id
            self.api_key_to_customer[api_key] = customer_id
            
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
    
    def get_customer(self, customer_id: str) -> Optional[Customer]:
        """Get customer by ID"""
        return self.customers.get(customer_id)
    
    def get_customer_by_email(self, email: str) -> Optional[Customer]:
        """Get customer by email"""
        customer_id = self.email_to_customer.get(email)
        if customer_id:
            return self.customers.get(customer_id)
        return None
    
    def get_customer_by_api_key(self, api_key: str) -> Optional[Customer]:
        """Get customer by API key"""
        customer_id = self.api_key_to_customer.get(api_key)
        if customer_id:
            return self.customers.get(customer_id)
        return None
    
    def generate_additional_api_key(self, customer_id: str, key_name: str) -> Dict[str, Any]:
        """Generate an additional API key for a customer"""
        customer = self.get_customer(customer_id)
        if not customer:
            return {'success': False, 'error': 'Customer not found'}
        
        # Generate new API key
        api_key = self.generate_api_key()
        api_key_data = {
            'key': api_key,
            'name': key_name,
            'created_at': datetime.utcnow().isoformat(),
            'last_used': None,
            'usage_count': 0,
            'status': 'active'
        }
        
        # Add to customer's API keys
        customer.api_keys.append(api_key_data)
        self.api_key_to_customer[api_key] = customer_id
        
        logger.info(f"Generated additional API key for customer: {customer_id}")
        
        return {
            'success': True,
            'api_key': api_key,
            'key_data': api_key_data
        }
    
    def revoke_api_key(self, customer_id: str, api_key: str) -> Dict[str, Any]:
        """Revoke an API key"""
        customer = self.get_customer(customer_id)
        if not customer:
            return {'success': False, 'error': 'Customer not found'}
        
        # Find and revoke the key
        for key_data in customer.api_keys:
            if key_data['key'] == api_key:
                key_data['status'] = 'revoked'
                key_data['revoked_at'] = datetime.utcnow().isoformat()
                
                # Remove from active mapping
                if api_key in self.api_key_to_customer:
                    del self.api_key_to_customer[api_key]
                
                logger.info(f"Revoked API key for customer: {customer_id}")
                return {'success': True}
        
        return {'success': False, 'error': 'API key not found'}
    
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
            if email in self.email_to_customer:
                existing_customer = self.get_customer_by_email(email)
                if existing_customer:
                    # Upgrade existing user to admin
                    existing_customer.role = 'admin'
                    existing_customer.permissions = ['admin_access', 'user_management', 'system_config']
                    # Set password if not already set
                    if not existing_customer.password_hash:
                        existing_customer.password_hash = self.hash_password("admin123")
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
def register():
    """Customer registration page and handler"""
    if request.method == 'GET':
        return render_template('modern/register.html')
    
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
            
            return jsonify({
                'success': True,
                'customer_id': result['customer_id'],
                'api_key': result['api_key'],
                'redirect_url': '/dashboard'
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
        
        # Store customer ID and role in session
        session['customer_id'] = customer.customer_id
        session['user_role'] = customer.role
        
        return jsonify({
            'success': True,
            'customer_id': customer.customer_id,
            'redirect_url': '/dashboard'
        })
        
    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({
            'success': False,
            'error': 'Login failed'
        }), 500

@customer_accounts_bp.route('/dashboard')
def dashboard():
    """Customer dashboard - redirect to proper route"""
    from auth.decorators import require_authenticated
    
    @require_authenticated()
    def _dashboard():
        customer_id = session.get('customer_id')
        customer = customer_manager.get_customer(customer_id)
        if not customer:
            return redirect('/login')
        
        # Add current month for template
        current_month = datetime.now().strftime('%Y-%m')
        customer_data = asdict(customer)
        customer_data['current_month'] = current_month
        
        return render_template('modern/dashboard.html', customer=customer_data)
    
    return _dashboard()

@customer_accounts_bp.route('/api/customer/info')
def get_customer_info():
    """Get customer information"""
    customer_id = session.get('customer_id')
    if not customer_id:
        return jsonify({'error': 'Not authenticated'}), 401
    
    customer = customer_manager.get_customer(customer_id)
    if not customer:
        return jsonify({'error': 'Customer not found'}), 404
    
    return jsonify({
        'success': True,
        'customer': asdict(customer)
    })

@customer_accounts_bp.route('/api/customer/api-keys', methods=['GET', 'POST', 'DELETE'])
def manage_api_keys():
    """Manage customer API keys"""
    customer_id = session.get('customer_id')
    if not customer_id:
        return jsonify({'error': 'Not authenticated'}), 401
    
    if request.method == 'GET':
        # Get all API keys
        customer = customer_manager.get_customer(customer_id)
        if not customer:
            return jsonify({'error': 'Customer not found'}), 404
        
        return jsonify({
            'success': True,
            'api_keys': customer.api_keys
        })
    
    elif request.method == 'POST':
        # Generate new API key
        data = request.get_json()
        key_name = data.get('name', 'API Key')
        
        result = customer_manager.generate_additional_api_key(customer_id, key_name)
        return jsonify(result)
    
    elif request.method == 'DELETE':
        # Revoke API key
        data = request.get_json()
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
