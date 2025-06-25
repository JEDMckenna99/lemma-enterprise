"""
Lemma Enterprise - Self-Serve Onboarding Routes
Enables customers to register domains, verify ownership, get API keys, and track usage.
"""

import os
import json
import uuid
import hashlib
import requests
import logging
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, jsonify, session, flash, redirect, url_for, current_app
from functools import wraps
import secrets
import math

# Optional DNS resolver import
try:
    import dns.resolver
    DNS_AVAILABLE = True
except ImportError:
    DNS_AVAILABLE = False

# Import billing manager
try:
    from lemma.billing.stripe_manager import get_stripe_manager
    BILLING_AVAILABLE = True
except ImportError:
    BILLING_AVAILABLE = False
    get_stripe_manager = lambda: None

onboarding_bp = Blueprint('onboarding', __name__)
logger = logging.getLogger(__name__)

# Pricing configuration
PRICING = {
    # Network-Effect Pricing Model
    'verification_fee': 2.00,  # $2.00 per new user verification
    'base_rate_per_user_per_month': 0.10,  # $0.10 starting rate
    'minimum_rate_floor': 0.045,  # $0.045 minimum rate (55% discount)
    'network_decay_rate': 0.0003217,  # Calculated so price is halfway between original and floor at 1000 sites
}

# API Key Security Functions
def hash_api_key(api_key: str) -> str:
    """
    Hash an API key for secure storage.
    
    Args:
        api_key: The plain text API key
        
    Returns:
        Hashed API key for storage
    """
    # Use SHA-256 with a salt for hashing
    salt = "lemma_api_key_salt_2024"  # In production, use environment variable
    return hashlib.sha256(f"{salt}{api_key}".encode()).hexdigest()

def verify_api_key(provided_key: str, stored_hash: str = None, stored_plain: str = None) -> bool:
    """
    Verify an API key against stored hash or plain text (for backwards compatibility).
    If no specific hash/plain is provided, check against all customer API keys.
    
    Args:
        provided_key: The API key provided by the user
        stored_hash: The hashed API key from storage (new format)
        stored_plain: The plain text API key from storage (legacy format)
        
    Returns:
        True if the key is valid, False otherwise
    """
    # If specific hash or plain provided, use original logic
    if stored_hash or stored_plain:
        if stored_hash:
            # New format: compare against hash
            return hash_api_key(provided_key) == stored_hash
        elif stored_plain:
            # Legacy format: direct comparison (will be migrated)
            return provided_key == stored_plain
        else:
            return False
    
    # NEW: Check against all customer API keys
    try:
        # Get all customer files
        from flask import current_app
        customers_dir = os.path.join(current_app.config.get('STORAGE_DIR', 'instance/data'), 'customers')
        
        if not os.path.exists(customers_dir):
            return False
        
        # Check each customer's API key
        for customer_file in os.listdir(customers_dir):
            if customer_file.endswith('.json'):
                customer_path = os.path.join(customers_dir, customer_file)
                try:
                    with open(customer_path, 'r') as f:
                        customer_data = json.load(f)
                    
                    # Check hashed format first
                    if customer_data.get('api_key_hash'):
                        if hash_api_key(provided_key) == customer_data['api_key_hash']:
                            logger.info(f"Valid API key matched for customer {customer_data.get('customer_id', 'unknown')}")
                            return True
                    
                    # Check legacy plain format
                    elif customer_data.get('api_key'):
                        if provided_key == customer_data['api_key']:
                            logger.info(f"Valid legacy API key matched for customer {customer_data.get('customer_id', 'unknown')}")
                            return True
                    
                    # Check legacy field (for migration)
                    elif customer_data.get('api_key_legacy'):
                        if provided_key == customer_data['api_key_legacy']:
                            logger.info(f"Valid legacy API key matched for customer {customer_data.get('customer_id', 'unknown')}")
                            return True
                            
                except Exception as e:
                    logger.warning(f"Error reading customer file {customer_file}: {e}")
                    continue
        
        return False
        
    except Exception as e:
        logger.error(f"Error checking customer API keys: {e}")
        return False

def migrate_api_key_to_hash(customer_data: dict) -> dict:
    """
    Migrate a customer's API key from plain text to hashed format.
    
    Args:
        customer_data: Customer data dictionary
        
    Returns:
        Updated customer data with hashed API key
    """
    plain_api_key = customer_data.get('api_key')
    
    if plain_api_key and not customer_data.get('api_key_hash'):
        # Migrate to hashed format
        customer_data['api_key_hash'] = hash_api_key(plain_api_key)
        customer_data['api_key_migrated_at'] = datetime.now().isoformat()
        
        # Keep plain key for a transition period (can be removed later)
        customer_data['api_key_legacy'] = plain_api_key
        
        # Remove the plain text key from main storage
        del customer_data['api_key']
        
        logger.info(f"Migrated API key to hashed format for customer {customer_data.get('customer_id')}")
    
    return customer_data

def get_customer_api_key_info(customer_data: dict, provided_key: str = None) -> dict:
    """
    Get API key information for a customer, handling both old and new formats.
    
    Args:
        customer_data: Customer data dictionary
        provided_key: API key provided for verification (optional)
        
    Returns:
        Dictionary with API key status and verification info
    """
    # Check if customer has new hashed format
    if customer_data.get('api_key_hash'):
        return {
            'format': 'hashed',
            'hash': customer_data['api_key_hash'],
            'migrated_at': customer_data.get('api_key_migrated_at'),
            'valid': verify_api_key(provided_key, stored_hash=customer_data['api_key_hash']) if provided_key else None,
            'display_key': None  # Never show the actual key for hashed format
        }
    
    # Legacy plain text format
    elif customer_data.get('api_key'):
        plain_key = customer_data['api_key']
        return {
            'format': 'plain_text',
            'hash': None,
            'migrated_at': None,
            'valid': verify_api_key(provided_key, stored_plain=plain_key) if provided_key else None,
            'display_key': plain_key,  # Show for legacy format (will be migrated)
            'needs_migration': True
        }
    
    else:
        return {
            'format': 'none',
            'hash': None,
            'migrated_at': None,
            'valid': False,
            'display_key': None,
            'needs_migration': False
        }

def customer_required(f):
    """Decorator to require customer authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'customer_id' not in session:
            flash('Please complete onboarding first.', 'warning')
            return redirect(url_for('onboarding.start'))
        return f(*args, **kwargs)
    return decorated_function

def get_customer_data(customer_id):
    """Get customer data from storage."""
    customer_file = os.path.join(current_app.config['STORAGE_DIR'], 'customers', f'{customer_id}.json')
    if os.path.exists(customer_file):
        with open(customer_file, 'r') as f:
            return json.load(f)
    return None

def save_customer_data(customer_id, data):
    """Save customer data to storage."""
    customers_dir = os.path.join(current_app.config['STORAGE_DIR'], 'customers')
    os.makedirs(customers_dir, exist_ok=True)
    
    customer_file = os.path.join(customers_dir, f'{customer_id}.json')
    with open(customer_file, 'w') as f:
        json.dump(data, f, indent=2)

def get_usage_analytics(customer_id, days=30):
    """Get usage analytics for a customer using network-effect pricing."""
    analytics_dir = os.path.join(current_app.config['STORAGE_DIR'], 'analytics')
    usage_data = {'total_verifications': 0, 'daily_usage': {}, 'monthly_cost': 0}
    
    if not os.path.exists(analytics_dir):
        return usage_data
    
    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    # Read usage files for the date range
    current_date = start_date
    total_verifications = 0
    
    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        usage_file = os.path.join(analytics_dir, f'{date_str}.json')
        
        if os.path.exists(usage_file):
            with open(usage_file, 'r') as f:
                daily_data = json.load(f)
                customer_usage = daily_data.get(customer_id, 0)
                usage_data['daily_usage'][date_str] = customer_usage
                total_verifications += customer_usage
        else:
            usage_data['daily_usage'][date_str] = 0
            
        current_date += timedelta(days=1)
    
    usage_data['total_verifications'] = total_verifications
    
    # Calculate monthly cost using network pricing model
    network_pricing = calculate_network_pricing()
    monthly_rate = network_pricing['current_rate']
    usage_data['monthly_cost'] = monthly_rate * total_verifications
    usage_data['pricing_tier'] = network_pricing['tier']['name']
    usage_data['current_rate'] = monthly_rate
    usage_data['verification_fee'] = network_pricing['verification_fee']
    
    return usage_data

def verify_domain_ownership(domain, verification_token):
    """Verify domain ownership via DNS TXT record or meta tag."""
    methods_tried = []
    
    # Method 1: DNS TXT Record verification (only if DNS resolver is available)
    if DNS_AVAILABLE:
        try:
            dns_records = dns.resolver.resolve(f'_lemma-verification.{domain}', 'TXT')
            for record in dns_records:
                if verification_token in str(record):
                    return True, 'dns'
            methods_tried.append('DNS TXT record')
        except Exception as e:
            logger.debug(f"DNS verification failed for {domain}: {e}")
            methods_tried.append('DNS TXT record (failed)')
    else:
        methods_tried.append('DNS TXT record (unavailable)')
    
    # Method 2: HTTP meta tag verification
    try:
        response = requests.get(f'https://{domain}', timeout=10)
        if verification_token in response.text:
            return True, 'meta'
        methods_tried.append('HTTP meta tag')
    except Exception as e:
        logger.debug(f"HTTP verification failed for {domain}: {e}")
        methods_tried.append('HTTP meta tag (failed)')
    
    # Method 3: Try HTTP without SSL
    try:
        response = requests.get(f'http://{domain}', timeout=10)
        if verification_token in response.text:
            return True, 'meta'
        methods_tried.append('HTTP meta tag (insecure)')
    except Exception as e:
        logger.debug(f"HTTP insecure verification failed for {domain}: {e}")
        methods_tried.append('HTTP meta tag (insecure, failed)')
    
    return False, methods_tried

@onboarding_bp.route('/')
def start():
    """Start the onboarding process."""
    return render_template('onboarding/start.html')

@onboarding_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Register a new customer and domain."""
    if request.method == 'GET':
        return render_template('onboarding/register.html')
    
    # Handle POST request
    data = request.get_json() if request.is_json else request.form
    
    email = data.get('email', '').strip().lower()
    company = data.get('company', '').strip()
    domain = data.get('domain', '').strip().lower()
    
    # Basic validation
    if not email or '@' not in email:
        return jsonify({'success': False, 'error': 'Valid email is required'}), 400
    
    if not domain or '.' not in domain:
        return jsonify({'success': False, 'error': 'Valid domain is required'}), 400
    
    # Remove protocol if provided
    domain = domain.replace('https://', '').replace('http://', '').replace('www.', '')
    
    # Generate customer ID and verification token
    customer_id = str(uuid.uuid4())
    verification_token = secrets.token_hex(16)
    api_key = f"lemma_{secrets.token_hex(24)}"
    
    # Create customer record with secure API key storage
    customer_data = {
        'customer_id': customer_id,
        'email': email,
        'company': company,
        'domain': domain,
        'verification_token': verification_token,
        'api_key_hash': hash_api_key(api_key),  # Store hashed API key
        'api_key_created_at': datetime.now().isoformat(),
        'verified': False,
        'created_at': datetime.now().isoformat(),
        # Billing fields - will be populated when billing is set up
        'stripe_customer_id': None,
        'stripe_subscription_id': None,
        'billing_status': 'not_setup',
        'billing_email': email,
        'current_rate': PRICING['base_rate_per_user_per_month']
    }
    
    save_customer_data(customer_id, customer_data)
    
    # Set session
    session['customer_id'] = customer_id
    
    # Return response with the plain API key (only time it's shown)
    return jsonify({
        'success': True,
        'customer_id': customer_id,
        'verification_token': verification_token,
        'domain': domain,
        'api_key': api_key,  # Show API key only once during registration
        'api_key_warning': 'Please save this API key securely. It will not be shown again.',
        'next_step': '/onboarding/verify'
    })

@onboarding_bp.route('/verify')
@customer_required
def verify():
    """Show domain verification instructions."""
    customer_data = get_customer_data(session['customer_id'])
    if not customer_data:
        flash('Customer data not found. Please start over.', 'error')
        return redirect(url_for('onboarding.start'))
    
    if customer_data.get('verified'):
        return redirect(url_for('onboarding.dashboard'))
    
    return render_template('onboarding/verify.html', customer=customer_data)

@onboarding_bp.route('/verify/check', methods=['POST'])
@customer_required
def verify_check():
    """Check domain verification status."""
    customer_data = get_customer_data(session['customer_id'])
    if not customer_data:
        return jsonify({'success': False, 'error': 'Customer not found'}), 404
    
    domain = customer_data['domain']
    verification_token = customer_data['verification_token']
    
    # Attempt verification
    verified, method = verify_domain_ownership(domain, verification_token)
    
    if verified:
        # Update customer data
        customer_data['verified'] = True
        customer_data['verified_at'] = datetime.now().isoformat()
        customer_data['verification_method'] = method
        save_customer_data(session['customer_id'], customer_data)
        
        # Attempt to set up billing with proper error handling
        billing_setup_result = attempt_billing_setup_with_retry(customer_data)
        
        # Prepare success response
        response_data = {
            'success': True,
            'verified': True,
            'method': method,
            'message': f'Domain verified successfully via {method}!',
            'billing_status': billing_setup_result['status'],
            'billing_message': billing_setup_result['message']
        }
        
        # Add billing warnings if needed
        if not billing_setup_result['success']:
            response_data['billing_warning'] = billing_setup_result['message']
            response_data['billing_retry_available'] = billing_setup_result.get('retry_available', False)
        
        return jsonify(response_data)
    else:
        return jsonify({
            'success': False,
            'verified': False,
            'methods_tried': method,
            'message': 'Domain verification failed. Please check your DNS record or meta tag.'
        })

def attempt_billing_setup_with_retry(customer_data, max_retries=3):
    """
    Attempt billing setup with retry logic and proper error handling.
    
    Args:
        customer_data: Customer data dictionary
        max_retries: Maximum number of retry attempts
        
    Returns:
        dict: Result with success status, message, and retry info
    """
    if not BILLING_AVAILABLE:
        return {
            'success': False,
            'status': 'billing_unavailable',
            'message': 'Billing integration not available. Customer can proceed without billing setup.',
            'retry_available': False
        }
    
    stripe_manager = get_stripe_manager()
    if not stripe_manager.is_enabled():
        return {
            'success': False,
            'status': 'stripe_disabled',
            'message': 'Stripe not configured. Billing setup can be completed later.',
            'retry_available': True
        }
    
    # Get or initialize retry count
    retry_count = customer_data.get('billing_setup_retry_count', 0)
    
    if retry_count >= max_retries:
        # Mark for manual setup after max retries
        customer_data.update({
            'billing_status': 'manual_setup_required',
            'billing_setup_failed_at': datetime.now().isoformat(),
            'billing_failure_reason': 'max_retries_exceeded'
        })
        save_customer_data(customer_data['customer_id'], customer_data)
        
        return {
            'success': False,
            'status': 'manual_setup_required',
            'message': 'Automatic billing setup failed. Please contact support or set up billing manually.',
            'retry_available': False
        }
    
    try:
        # Attempt billing setup
        billing_success = auto_setup_billing(customer_data)
        
        if billing_success:
            # Reset retry count on success
            customer_data['billing_setup_retry_count'] = 0
            save_customer_data(customer_data['customer_id'], customer_data)
            
            return {
                'success': True,
                'status': 'billing_active',
                'message': 'Billing setup completed successfully.',
                'retry_available': False
            }
        else:
            # Increment retry count and schedule retry
            customer_data['billing_setup_retry_count'] = retry_count + 1
            customer_data['billing_status'] = 'setup_pending'
            customer_data['billing_last_retry_at'] = datetime.now().isoformat()
            save_customer_data(customer_data['customer_id'], customer_data)
            
            return {
                'success': False,
                'status': 'setup_pending',
                'message': f'Billing setup failed (attempt {retry_count + 1}/{max_retries}). Will retry automatically.',
                'retry_available': True,
                'retry_count': retry_count + 1,
                'max_retries': max_retries
            }
            
    except Exception as e:
        logger.error(f"Exception during billing setup for customer {customer_data['customer_id']}: {e}")
        
        # Increment retry count
        customer_data['billing_setup_retry_count'] = retry_count + 1
        customer_data['billing_status'] = 'setup_error'
        customer_data['billing_last_error'] = str(e)
        customer_data['billing_last_retry_at'] = datetime.now().isoformat()
        save_customer_data(customer_data['customer_id'], customer_data)
        
        return {
            'success': False,
            'status': 'setup_error',
            'message': f'Billing setup error (attempt {retry_count + 1}/{max_retries}): {str(e)}',
            'retry_available': retry_count + 1 < max_retries,
            'retry_count': retry_count + 1,
            'max_retries': max_retries
        }

@onboarding_bp.route('/dashboard')
@customer_required
def dashboard():
    """Show customer dashboard with API keys, usage, and network pricing."""
    customer_data = get_customer_data(session['customer_id'])
    if not customer_data:
        flash('Customer data not found. Please start over.', 'error')
        return redirect(url_for('onboarding.start'))
    
    if not customer_data.get('verified'):
        return redirect(url_for('onboarding.verify'))
    
    # Get usage analytics
    from lemma.core.analytics_service import get_analytics_service
    analytics_service = get_analytics_service()
    customer_analytics = analytics_service.get_customer_analytics(session['customer_id'], 30)
    monthly_users = customer_analytics.get('usage', {}).get('total_verifications', 0)
    
    # Get network pricing information
    network_pricing = calculate_network_pricing()
    customer_pricing = calculate_customer_pricing(session['customer_id'], monthly_users)
    network_metrics = get_network_metrics()
    
    # Legacy pricing for comparison
    legacy_usage_data = get_usage_analytics(session['customer_id'])
    
    return render_template('onboarding/dashboard.html', 
                         customer=customer_data, 
                         usage=legacy_usage_data,  # Keep for backward compatibility
                         customer_analytics=customer_analytics,
                         network_pricing=network_pricing,
                         customer_pricing=customer_pricing,
                         network_metrics=network_metrics,
                         pricing=PRICING)

@onboarding_bp.route('/api-keys')
@customer_required
def api_keys():
    """Manage API keys with automatic migration from legacy format."""
    customer_data = get_customer_data(session['customer_id'])
    if not customer_data:
        flash('Customer data not found. Please start over.', 'error')
        return redirect(url_for('onboarding.start'))
    
    # Automatically migrate legacy API keys
    original_data = customer_data.copy()
    customer_data = migrate_api_key_to_hash(customer_data)
    
    # Save if migration occurred
    if customer_data != original_data:
        save_customer_data(session['customer_id'], customer_data)
        logger.info(f"Auto-migrated API key for customer {session['customer_id']}")
    
    # Get API key info for display
    api_key_info = get_customer_api_key_info(customer_data)
    
    return render_template('onboarding/api_keys.html', 
                         customer=customer_data,
                         api_key_info=api_key_info)

@onboarding_bp.route('/api-keys/regenerate', methods=['POST'])
@customer_required
def regenerate_api_key():
    """Regenerate API key with secure hashing."""
    customer_data = get_customer_data(session['customer_id'])
    if not customer_data:
        return jsonify({'success': False, 'error': 'Customer not found'}), 404
    
    # Generate new API key
    new_api_key = f"lemma_{secrets.token_hex(24)}"
    
    # Store the hashed version
    customer_data['api_key_hash'] = hash_api_key(new_api_key)
    customer_data['api_key_regenerated_at'] = datetime.now().isoformat()
    
    # Remove any legacy plain text key
    if 'api_key' in customer_data:
        del customer_data['api_key']
    if 'api_key_legacy' in customer_data:
        del customer_data['api_key_legacy']
    
    save_customer_data(session['customer_id'], customer_data)
    
    return jsonify({
        'success': True,
        'api_key': new_api_key,  # Show the new key only once
        'api_key_warning': 'Please save this API key securely. It will not be shown again.',
        'message': 'API key regenerated successfully!'
    })

@onboarding_bp.route('/api-keys/verify', methods=['POST'])
@customer_required
def verify_api_key_endpoint():
    """Verify an API key for testing purposes."""
    try:
        data = request.get_json()
        if not data or not data.get('api_key'):
            return jsonify({'success': False, 'error': 'API key is required'}), 400
        
        provided_key = data['api_key']
        customer_data = get_customer_data(session['customer_id'])
        
        if not customer_data:
            return jsonify({'success': False, 'error': 'Customer not found'}), 404
        
        # Automatically migrate if needed
        original_data = customer_data.copy()
        customer_data = migrate_api_key_to_hash(customer_data)
        
        if customer_data != original_data:
            save_customer_data(session['customer_id'], customer_data)
        
        # Get API key info and verify
        api_key_info = get_customer_api_key_info(customer_data, provided_key)
        
        if api_key_info['valid']:
            return jsonify({
                'success': True,
                'valid': True,
                'message': 'API key is valid',
                'key_format': api_key_info['format'],
                'migrated_at': api_key_info.get('migrated_at')
            })
        else:
            return jsonify({
                'success': True,
                'valid': False,
                'message': 'API key is invalid',
                'key_format': api_key_info['format']
            })
        
    except Exception as e:
        logger.error(f"Error verifying API key: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@onboarding_bp.route('/usage')
@customer_required
def usage():
    """Show detailed usage analytics."""
    customer_data = get_customer_data(session['customer_id'])
    if not customer_data:
        flash('Customer data not found. Please start over.', 'error')
        return redirect(url_for('onboarding.start'))
    
    # Get usage data for different periods
    usage_30d = get_usage_analytics(session['customer_id'], 30)
    usage_7d = get_usage_analytics(session['customer_id'], 7)
    usage_1d = get_usage_analytics(session['customer_id'], 1)
    
    return render_template('onboarding/usage.html',
                         customer=customer_data,
                         usage_30d=usage_30d,
                         usage_7d=usage_7d,
                         usage_1d=usage_1d,
                         pricing=PRICING)

@onboarding_bp.route('/integration')
@customer_required
def integration():
    """Show integration guide and code examples."""
    customer_data = get_customer_data(session['customer_id'])
    if not customer_data:
        flash('Customer data not found. Please start over.', 'error')
        return redirect(url_for('onboarding.start'))
    
    # Get the current app's base URL for examples
    base_url = request.url_root.rstrip('/')
    
    return render_template('onboarding/integration.html',
                         customer=customer_data,
                         base_url=base_url)

@onboarding_bp.route('/logout')
def logout():
    """Logout customer."""
    session.pop('customer_id', None)
    flash('Logged out successfully.', 'info')
    return redirect(url_for('onboarding.start'))

# Analytics logging helper function
def log_verification_event(customer_id, event_type='verification'):
    """Log a verification event for analytics."""
    try:
        analytics_dir = os.path.join(current_app.config['STORAGE_DIR'], 'analytics')
        os.makedirs(analytics_dir, exist_ok=True)
        
        today = datetime.now().strftime('%Y-%m-%d')
        usage_file = os.path.join(analytics_dir, f'{today}.json')
        
        # Load existing data
        if os.path.exists(usage_file):
            with open(usage_file, 'r') as f:
                daily_data = json.load(f)
        else:
            daily_data = {}
        
        # Increment counter
        if customer_id not in daily_data:
            daily_data[customer_id] = 0
        daily_data[customer_id] += 1
        
        # Save updated data
        with open(usage_file, 'w') as f:
            json.dump(daily_data, f, indent=2)
            
    except Exception as e:
        logger.error(f"Failed to log verification event: {e}")

def get_network_metrics():
    """Get current network metrics for pricing calculations."""
    try:
        # Count verified sites from customer records
        customers_dir = os.path.join(current_app.config['STORAGE_DIR'], 'customers')
        verified_sites = 0
        total_users = 0
        active_customers = 0
        
        if os.path.exists(customers_dir):
            for customer_file in os.listdir(customers_dir):
                if customer_file.endswith('.json'):
                    try:
                        with open(os.path.join(customers_dir, customer_file), 'r') as f:
                            customer_data = json.load(f)
                            if customer_data.get('verified', False):
                                verified_sites += 1
                                # Get usage data for this customer
                                from lemma.core.analytics_service import get_analytics_service
                                analytics = get_analytics_service()
                                customer_analytics = analytics.get_customer_analytics(
                                    customer_data['customer_id'], 30
                                )
                                monthly_users = customer_analytics.get('usage', {}).get('total_verifications', 0)
                                total_users += monthly_users
                                if monthly_users > 0:
                                    active_customers += 1
                    except Exception as e:
                        logger.warning(f"Error reading customer file {customer_file}: {e}")
        
        return {
            'verified_sites': verified_sites,
            'total_network_users': total_users,
            'active_customers': active_customers,
            'last_updated': datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting network metrics: {e}")
        return {
            'verified_sites': 0,
            'total_network_users': 0,
            'active_customers': 0,
            'last_updated': datetime.now().isoformat()
        }

def calculate_network_pricing(network_sites: int = None) -> dict:
    """
    Calculate current network pricing based on number of integrated sites.
    
    Args:
        network_sites: Number of verified sites in network (auto-calculated if None)
        
    Returns:
        dict: Comprehensive pricing information including rates, discounts, and tiers
    """
    try:
        # Get current network metrics if not provided
        if network_sites is None:
            network_metrics = get_network_metrics()
            network_sites = network_metrics['verified_sites']
        
        base_rate = PRICING['base_rate_per_user_per_month']
        floor_rate = PRICING['minimum_rate_floor']
        decay_rate = PRICING['network_decay_rate']
        verification_fee = PRICING['verification_fee']
        
        # Calculate current rate using exponential decay model
        # Formula: rate = max(base_rate * e^(-decay_rate * sites), floor_rate)
        current_rate = max(
            base_rate * math.exp(-decay_rate * network_sites),
            floor_rate
        )
        
        # Calculate discount percentage
        discount_percentage = ((base_rate - current_rate) / base_rate) * 100
        
        # Determine pricing tier
        tier_info = get_pricing_tier_info(network_sites)
        
        # Calculate next milestone
        next_milestone = get_next_pricing_milestone(network_sites)
        
        return {
            'network_sites': network_sites,
            'verification_fee': verification_fee,
            'current_rate': round(current_rate, 4),
            'base_rate': base_rate,
            'floor_rate': floor_rate,
            'discount_percentage': round(discount_percentage, 1),
            'tier': tier_info,
            'next_milestone': next_milestone,
            'last_updated': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error calculating network pricing: {e}")
        # Return safe defaults
        return {
            'network_sites': 0,
            'verification_fee': PRICING['verification_fee'],
            'current_rate': PRICING['base_rate_per_user_per_month'],
            'base_rate': PRICING['base_rate_per_user_per_month'],
            'floor_rate': PRICING['minimum_rate_floor'],
            'discount_percentage': 0,
            'tier': {'name': 'starter', 'description': 'Starter Network'},
            'next_milestone': {'sites': 10, 'rate': 0.095, 'discount': 5},
            'last_updated': datetime.now().isoformat()
        }

def get_pricing_tier_info(network_sites: int) -> dict:
    """Get tier information based on number of network sites."""
    if network_sites >= 500:
        return {
            'name': 'maximum_network',
            'description': 'Maximum Network Discount',
            'emoji': '🌐',
            'color': 'gold'
        }
    elif network_sites >= 100:
        return {
            'name': 'enterprise_network',
            'description': 'Enterprise Network',
            'emoji': '🏢',
            'color': 'purple'
        }
    elif network_sites >= 50:
        return {
            'name': 'growing_network',
            'description': 'Growing Network',
            'emoji': '📈',
            'color': 'blue'
        }
    elif network_sites >= 10:
        return {
            'name': 'early_network',
            'description': 'Early Network',
            'emoji': '🚀',
            'color': 'green'
        }
    else:
        return {
            'name': 'starter_network',
            'description': 'Starter Network',
            'emoji': '🌱',
            'color': 'gray'
        }

def get_next_pricing_milestone(current_sites: int) -> dict:
    """Calculate the next pricing milestone and potential savings."""
    base_rate = PRICING['base_rate_per_user_per_month']
    floor_rate = PRICING['minimum_rate_floor']
    decay_rate = PRICING['network_decay_rate']
    
    milestones = [10, 25, 50, 100, 250, 500, 1000]
    
    for milestone in milestones:
        if current_sites < milestone:
            milestone_rate = max(
                base_rate * math.exp(-decay_rate * milestone),
                floor_rate
            )
            current_rate = max(
                base_rate * math.exp(-decay_rate * current_sites),
                floor_rate
            )
            
            discount_improvement = ((current_rate - milestone_rate) / base_rate) * 100
            
            return {
                'sites': milestone,
                'rate': round(milestone_rate, 4),
                'discount_improvement': round(discount_improvement, 1),
                'sites_needed': milestone - current_sites
            }
    
    # Already at maximum
    return {
        'sites': 'Maximum',
        'rate': floor_rate,
        'discount_improvement': 0,
        'sites_needed': 0
    }

def calculate_customer_pricing(customer_id: str, monthly_users: int) -> dict:
    """
    Calculate comprehensive pricing for a specific customer.
    
    Args:
        customer_id: Customer identifier
        monthly_users: Number of monthly active users
        
    Returns:
        dict: Detailed pricing breakdown including network effects
    """
    try:
        # Get current network pricing
        network_pricing = calculate_network_pricing()
        
        # Calculate monthly costs
        monthly_rate = network_pricing['current_rate']
        monthly_cost = monthly_rate * monthly_users
        verification_fee = network_pricing['verification_fee']
        
        # Calculate potential savings vs base rate
        base_monthly_cost = PRICING['base_rate_per_user_per_month'] * monthly_users
        monthly_savings = base_monthly_cost - monthly_cost
        
        # Get customer-specific metrics
        customer_data = get_customer_data(customer_id)
        
        return {
            'customer_id': customer_id,
            'monthly_users': monthly_users,
            'pricing': {
                'verification_fee': verification_fee,
                'monthly_rate_per_user': monthly_rate,
                'monthly_total': round(monthly_cost, 2),
                'base_rate_comparison': PRICING['base_rate_per_user_per_month'],
                'monthly_savings': round(monthly_savings, 2),
                'discount_percentage': network_pricing['discount_percentage']
            },
            'network': {
                'current_sites': network_pricing['network_sites'],
                'tier': network_pricing['tier'],
                'next_milestone': network_pricing['next_milestone']
            },
            'customer': {
                'domain': customer_data.get('domain', '') if customer_data else '',
                'verified': customer_data.get('verified', False) if customer_data else False,
                'member_since': customer_data.get('created_at', '') if customer_data else ''
            },
            'last_updated': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error calculating customer pricing for {customer_id}: {e}")
        return {
            'customer_id': customer_id,
            'monthly_users': monthly_users,
            'error': str(e),
            'last_updated': datetime.now().isoformat()
        }

# ============================================================================
# NETWORK PRICING API ENDPOINTS
# ============================================================================

@onboarding_bp.route('/api/network-pricing', methods=['GET'])
@customer_required
def get_network_pricing_api():
    """API endpoint to get current network pricing information."""
    try:
        network_pricing = calculate_network_pricing()
        return jsonify({
            'success': True,
            'network_pricing': network_pricing,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error getting network pricing: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@onboarding_bp.route('/api/customer-pricing', methods=['GET'])
@customer_required
def get_customer_pricing_api():
    """API endpoint to get customer-specific pricing information."""
    try:
        # Get monthly users from query parameter or calculate from analytics
        monthly_users = request.args.get('monthly_users', type=int)
        
        if monthly_users is None:
            # Calculate from analytics
            from lemma.core.analytics_service import get_analytics_service
            analytics_service = get_analytics_service()
            customer_analytics = analytics_service.get_customer_analytics(session['customer_id'], 30)
            monthly_users = customer_analytics.get('usage', {}).get('total_verifications', 0)
        
        customer_pricing = calculate_customer_pricing(session['customer_id'], monthly_users)
        
        return jsonify({
            'success': True,
            'customer_pricing': customer_pricing,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error getting customer pricing: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@onboarding_bp.route('/api/network-metrics', methods=['GET'])
def get_network_metrics_api():
    """API endpoint to get current network metrics (public endpoint)."""
    try:
        network_metrics = get_network_metrics()
        network_pricing = calculate_network_pricing()
        
        # Combine metrics with pricing for public display
        public_metrics = {
            'network': {
                'verified_sites': network_metrics['verified_sites'],
                'total_network_users': network_metrics['total_network_users'],
                'active_customers': network_metrics['active_customers']
            },
            'pricing': {
                'current_rate': network_pricing['current_rate'],
                'discount_percentage': network_pricing['discount_percentage'],
                'tier': network_pricing['tier'],
                'verification_fee': network_pricing['verification_fee']
            },
            'last_updated': network_metrics['last_updated']
        }
        
        return jsonify({
            'success': True,
            'metrics': public_metrics,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error getting network metrics: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@onboarding_bp.route('/api/pricing-calculator', methods=['POST'])
def pricing_calculator_api():
    """API endpoint to calculate pricing for different scenarios."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        monthly_users = data.get('monthly_users', 0)
        network_sites = data.get('network_sites')  # Optional, will auto-calculate if not provided
        
        if monthly_users < 0:
            return jsonify({'success': False, 'error': 'Monthly users must be non-negative'}), 400
        
        # Calculate pricing for the scenario
        network_pricing = calculate_network_pricing(network_sites)
        
        # Calculate costs
        monthly_rate = network_pricing['current_rate']
        monthly_cost = monthly_rate * monthly_users
        verification_fee = network_pricing['verification_fee']
        
        # Calculate savings vs base rate
        base_cost = PRICING['base_rate_per_user_per_month'] * monthly_users
        savings = base_cost - monthly_cost
        
        pricing_calculation = {
            'scenario': {
                'monthly_users': monthly_users,
                'network_sites': network_pricing['network_sites']
            },
            'pricing': {
                'verification_fee': verification_fee,
                'monthly_rate_per_user': monthly_rate,
                'monthly_total': round(monthly_cost, 2),
                'base_rate_comparison': PRICING['base_rate_per_user_per_month'],
                'monthly_savings': round(savings, 2),
                'discount_percentage': network_pricing['discount_percentage']
            },
            'network': {
                'tier': network_pricing['tier'],
                'next_milestone': network_pricing['next_milestone']
            }
        }
        
        return jsonify({
            'success': True,
            'calculation': pricing_calculation,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error in pricing calculator: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def auto_setup_billing(customer_data):
    """Automatically set up billing for a verified customer."""
    if not BILLING_AVAILABLE:
        logger.info("Billing not available, skipping auto-setup")
        return False
        
    stripe_manager = get_stripe_manager()
    if not stripe_manager.is_enabled():
        logger.info("Stripe not enabled, skipping auto-setup")
        return False
    
    try:
        # Create Stripe customer
        stripe_customer_data = stripe_manager.create_stripe_customer(customer_data)
        
        if not stripe_customer_data:
            logger.warning(f"Failed to create Stripe customer for {customer_data.get('email')}")
            return False
        
        # Update customer data with Stripe information
        customer_data.update({
            'stripe_customer_id': stripe_customer_data['stripe_customer_id'],
            'billing_email': stripe_customer_data['billing_email'],
            'billing_setup_at': datetime.now().isoformat(),
            'billing_status': 'active'
        })
        
        # Create initial subscription with current network pricing
        network_pricing = calculate_network_pricing()
        subscription_data = stripe_manager.create_subscription(
            stripe_customer_data['stripe_customer_id'], 
            network_pricing
        )
        
        if subscription_data:
            customer_data.update({
                'stripe_subscription_id': subscription_data['stripe_subscription_id'],
                'current_rate': subscription_data['current_rate'],
                'subscription_status': subscription_data['status']
            })
        
        # Save updated customer data
        save_customer_data(customer_data['customer_id'], customer_data)
        
        logger.info(f"Successfully set up billing for customer {customer_data['customer_id']}")
        return True
        
    except Exception as e:
        logger.error(f"Error auto-setting up billing: {e}")
        return False

@onboarding_bp.route('/billing/retry', methods=['POST'])
@customer_required
def retry_billing_setup():
    """Allow customers to manually retry billing setup."""
    try:
        customer_data = get_customer_data(session['customer_id'])
        if not customer_data:
            return jsonify({'success': False, 'error': 'Customer not found'}), 404
        
        if not customer_data.get('verified'):
            return jsonify({
                'success': False, 
                'error': 'Domain must be verified before setting up billing'
            }), 400
        
        # Check if billing is already active
        if customer_data.get('billing_status') == 'active':
            return jsonify({
                'success': True,
                'message': 'Billing is already active',
                'billing_status': 'active'
            })
        
        # Force retry by resetting retry count
        customer_data['billing_setup_retry_count'] = 0
        customer_data['billing_manual_retry_at'] = datetime.now().isoformat()
        save_customer_data(session['customer_id'], customer_data)
        
        # Attempt billing setup with retry logic
        billing_result = attempt_billing_setup_with_retry(customer_data)
        
        return jsonify({
            'success': billing_result['success'],
            'billing_status': billing_result['status'],
            'message': billing_result['message'],
            'retry_available': billing_result.get('retry_available', False)
        })
        
    except Exception as e:
        logger.error(f"Error during manual billing retry: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@onboarding_bp.route('/billing/status', methods=['GET'])
@customer_required
def get_billing_status():
    """Get current billing status for the customer."""
    try:
        customer_data = get_customer_data(session['customer_id'])
        if not customer_data:
            return jsonify({'success': False, 'error': 'Customer not found'}), 404
        
        billing_status = {
            'verified': customer_data.get('verified', False),
            'billing_available': BILLING_AVAILABLE,
            'billing_status': customer_data.get('billing_status', 'not_setup'),
            'stripe_customer_id': customer_data.get('stripe_customer_id'),
            'billing_setup_at': customer_data.get('billing_setup_at'),
            'retry_count': customer_data.get('billing_setup_retry_count', 0),
            'last_retry_at': customer_data.get('billing_last_retry_at'),
            'last_error': customer_data.get('billing_last_error'),
            'manual_setup_required': customer_data.get('billing_status') == 'manual_setup_required'
        }
        
        # Add user-friendly status messages
        status_messages = {
            'active': 'Billing is active and working properly',
            'setup_pending': 'Billing setup is pending - automatic retry in progress',
            'setup_error': 'Billing setup encountered an error - retry available',
            'manual_setup_required': 'Automatic setup failed - manual setup required',
            'not_setup': 'Billing has not been set up yet',
            'billing_unavailable': 'Billing integration is not available',
            'stripe_disabled': 'Stripe integration is disabled'
        }
        
        billing_status['status_message'] = status_messages.get(
            billing_status['billing_status'], 
            'Unknown billing status'
        )
        
        return jsonify({
            'success': True,
            'billing_status': billing_status,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error getting billing status: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500 