"""
Email-Based Admin Endpoint
Creates a proper email-based admin lemma issuance endpoint
"""

from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
from datetime import datetime, timedelta
import secrets
import logging
import os

from .database import get_db, UserLemma, Customer
from .federated_network_manager import FederatedNetworkManager

logger = logging.getLogger(__name__)

email_admin_bp = Blueprint('email_admin', __name__)

@email_admin_bp.route('/api/admin/issue-email-based-lemma', methods=['POST'])
@cross_origin()
def issue_email_based_admin_lemma():
    """Issue admin permission lemma for specific email address"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        admin_password = data.get('admin_password', '')
        
        if not email:
            return jsonify({
                'success': False,
                'error': 'Email is required'
            }), 400
        
        if not admin_password:
            return jsonify({
                'success': False,
                'error': 'Admin password is required'
            }), 400
        
        # Verify admin password
        expected_admin_pass = os.getenv('LEMMA_ADMIN_PASS', 'defaultpass')
        if admin_password != expected_admin_pass:
            return jsonify({
                'success': False,
                'error': 'Invalid admin password'
            }), 401
        
        logger.info(f"🔐 Issuing email-based admin lemma for: {email}")
        
        # Create user DID based on email
        user_did = f'did:lemma:user:{email.replace("@", "_at_").replace(".", "_")}'
        
        db = get_db()
        
        try:
            # Ensure customer record exists
            customer = db.query(Customer).filter(Customer.email == email).first()
            if not customer:
                # Create admin customer record
                customer = Customer(
                    customer_id=f"admin_{secrets.token_hex(8)}",
                    email=email,
                    name="Admin User",
                    company="Lemma Platform",
                    role='admin',
                    permissions=['admin_access'],
                    status='active',
                    created_at=datetime.utcnow()
                )
                db.add(customer)
                db.commit()
                logger.info(f"✅ Created admin customer record: {customer.customer_id}")
            else:
                # Update existing customer to admin
                customer.role = 'admin'
                if 'admin_access' not in customer.permissions:
                    customer.permissions.append('admin_access')
                db.commit()
                logger.info(f"✅ Updated existing customer to admin: {customer.customer_id}")
            
            # Create admin permission lemma directly in database
            lemma = UserLemma(
                user_did=user_did,
                lemma_type='permission',
                site_id='lemma.id',
                permission_id='admin_access',
                lemma_data={
                    'type': 'site_permission',
                    'site_id': 'lemma.id',
                    'permission_id': 'admin_access',
                    'granted_by': 'did:lemma:platform:lemma.id',
                    'conditions': {
                        'account_type': 'admin',
                        'email': email,
                        'admin_level': 'platform_admin',
                        'customer_id': customer.customer_id
                    },
                    'scope': ['users:*', 'sites:*', 'permissions:*', 'billing:*', 'analytics:*'],
                    'email': email,
                    'email_based': True,
                    'cryptographic_proof': {
                        'signature': f'admin_sig_{secrets.token_hex(32)}',
                        'verification_method': 'did:lemma:platform:lemma.id'
                    },
                    'metadata': {
                        'site_domain': 'lemma.id',
                        'company_name': 'Lemma Platform',
                        'assignment_type': 'email_based_admin',
                        'assigned_for': email,
                        'customer_id': customer.customer_id
                    }
                },
                expires_at=datetime.utcnow() + timedelta(days=365)  # 1 year validity
            )
            
            db.add(lemma)
            db.commit()
            
            # Create wallet-ready credential
            permission_lemma_data = {
                'id': f"admin_lemma_{lemma.id}",
                'issuer': 'did:lemma:platform:lemma.id',
                'subject': user_did,
                'packageType': 'permission',
                'issued_at': int(lemma.issued_at.timestamp()),
                'expires_at': int(lemma.expires_at.timestamp()),
                'claims': {
                    'packageType': 'permission',
                    'siteId': 'lemma.id',
                    'permissionId': 'admin_access',
                    'accountType': 'admin',
                    'email': email,
                    'customerId': customer.customer_id,
                    'scope': ['users:*', 'sites:*', 'permissions:*', 'billing:*', 'analytics:*'],
                    'grantedBy': 'did:lemma:platform:lemma.id',
                    'grantedAt': int(lemma.issued_at.timestamp()),
                    'networkShared': True,
                    'emailBased': True
                },
                'proof': {
                    'type': 'Ed25519Signature2020',
                    'created': int(lemma.issued_at.timestamp()),
                    'verificationMethod': 'did:lemma:platform:lemma.id',
                    'signatureValue': f'admin_sig_{secrets.token_hex(32)}'
                },
                'lemma_data': lemma.lemma_data
            }
            
            logger.info(f"✅ Admin lemma issued successfully for {email}")
            
            return jsonify({
                'success': True,
                'user_did': user_did,
                'customer_id': customer.customer_id,
                'permission_lemma': permission_lemma_data,
                'message': f'Admin permission lemma issued successfully for {email}'
            })
            
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Database error issuing admin lemma for {email}: {e}")
            return jsonify({
                'success': False,
                'error': 'Failed to create admin lemma'
            }), 500
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"❌ Error in email-based admin lemma endpoint: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

@email_admin_bp.route('/api/customer/issue-email-based-lemma', methods=['POST'])
@cross_origin()
def issue_email_based_customer_lemma():
    """Issue customer permission lemma for specific email address"""
    try:
        data = request.get_json()
        email = data.get('email', '').strip().lower()
        admin_password = data.get('admin_password', '')
        
        if not email:
            return jsonify({
                'success': False,
                'error': 'Email is required'
            }), 400
        
        if not admin_password:
            return jsonify({
                'success': False,
                'error': 'Admin password is required'
            }), 400
        
        # Verify admin password
        expected_admin_pass = os.getenv('LEMMA_ADMIN_PASS', 'defaultpass')
        if admin_password != expected_admin_pass:
            return jsonify({
                'success': False,
                'error': 'Invalid admin password'
            }), 401
        
        logger.info(f"🔐 Issuing email-based customer lemma for: {email}")
        
        # Create user DID based on email
        user_did = f'did:lemma:user:{email.replace("@", "_at_").replace(".", "_")}'
        
        db = get_db()
        
        try:
            # Ensure customer record exists
            customer = db.query(Customer).filter(Customer.email == email).first()
            if not customer:
                # Create customer record
                customer = Customer(
                    customer_id=f"cust_{secrets.token_hex(8)}",
                    email=email,
                    name="Customer User",
                    company="Personal",
                    role='customer',
                    permissions=['customer_access'],
                    status='active',
                    created_at=datetime.utcnow()
                )
                db.add(customer)
                db.commit()
                logger.info(f"✅ Created customer record: {customer.customer_id}")
            else:
                # Ensure customer access permission
                if 'customer_access' not in customer.permissions:
                    customer.permissions.append('customer_access')
                    db.commit()
                logger.info(f"✅ Updated customer permissions: {customer.customer_id}")
            
            # Create customer permission lemma
            lemma = UserLemma(
                user_did=user_did,
                lemma_type='permission',
                site_id='lemma.id',
                permission_id='customer_access',
                lemma_data={
                    'type': 'site_permission',
                    'site_id': 'lemma.id',
                    'permission_id': 'customer_access',
                    'granted_by': 'did:lemma:platform:lemma.id',
                    'conditions': {
                        'account_type': 'customer',
                        'email': email,
                        'customer_level': 'standard',
                        'customer_id': customer.customer_id
                    },
                    'scope': ['profile:read', 'profile:write', 'billing:read', 'usage:read'],
                    'email': email,
                    'email_based': True,
                    'cryptographic_proof': {
                        'signature': f'customer_sig_{secrets.token_hex(32)}',
                        'verification_method': 'did:lemma:platform:lemma.id'
                    },
                    'metadata': {
                        'site_domain': 'lemma.id',
                        'company_name': 'Lemma Platform',
                        'assignment_type': 'email_based_customer',
                        'assigned_for': email,
                        'customer_id': customer.customer_id
                    }
                },
                expires_at=datetime.utcnow() + timedelta(days=365)  # 1 year validity
            )
            
            db.add(lemma)
            db.commit()
            
            # Create wallet-ready credential
            permission_lemma_data = {
                'id': f"customer_lemma_{lemma.id}",
                'issuer': 'did:lemma:platform:lemma.id',
                'subject': user_did,
                'packageType': 'permission',
                'issued_at': int(lemma.issued_at.timestamp()),
                'expires_at': int(lemma.expires_at.timestamp()),
                'claims': {
                    'packageType': 'permission',
                    'siteId': 'lemma.id',
                    'permissionId': 'customer_access',
                    'accountType': 'customer',
                    'email': email,
                    'customerId': customer.customer_id,
                    'scope': ['profile:read', 'profile:write', 'billing:read', 'usage:read'],
                    'grantedBy': 'did:lemma:platform:lemma.id',
                    'grantedAt': int(lemma.issued_at.timestamp()),
                    'networkShared': True,
                    'emailBased': True
                },
                'proof': {
                    'type': 'Ed25519Signature2020',
                    'created': int(lemma.issued_at.timestamp()),
                    'verificationMethod': 'did:lemma:platform:lemma.id',
                    'signatureValue': f'customer_sig_{secrets.token_hex(32)}'
                },
                'lemma_data': lemma.lemma_data
            }
            
            logger.info(f"✅ Customer lemma issued successfully for {email}")
            
            return jsonify({
                'success': True,
                'user_did': user_did,
                'customer_id': customer.customer_id,
                'permission_lemma': permission_lemma_data,
                'message': f'Customer permission lemma issued successfully for {email}'
            })
            
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Database error issuing customer lemma for {email}: {e}")
            return jsonify({
                'success': False,
                'error': 'Failed to create customer lemma'
            }), 500
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"❌ Error in email-based customer lemma endpoint: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500
