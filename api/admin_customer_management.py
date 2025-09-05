"""
Admin Customer Management
Provides admin functions for managing customer accounts, including removal
"""

from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
import logging
import os
from .database import get_db, Customer

logger = logging.getLogger(__name__)

admin_customer_bp = Blueprint('admin_customer', __name__)

@admin_customer_bp.route('/api/admin/customers/<email>/delete', methods=['DELETE'])
@cross_origin()
def delete_customer_account(email):
    """
    Delete a customer account (admin only)
    
    DELETE /api/admin/customers/{email}/delete
    """
    try:
        # Get admin password for security
        admin_password = request.headers.get('X-Admin-Password', '')
        expected_admin_pass = os.getenv('LEMMA_ADMIN_PASS', '.511MeV/c^2')
        
        if admin_password != expected_admin_pass:
            return jsonify({
                'success': False,
                'error': 'Invalid admin password'
            }), 401
        
        # Find and delete customer
        db = get_db()
        customer = db.query(Customer).filter(Customer.email == email).first()
        
        if not customer:
            db.close()
            return jsonify({
                'success': False,
                'error': 'Customer not found'
            }), 404
        
        # Store info for logging before deletion
        customer_id = customer.customer_id
        company = customer.company
        
        # Delete customer
        db.delete(customer)
        db.commit()
        db.close()
        
        logger.info(f"🗑️ Admin deleted customer account: {email} ({company}) - ID: {customer_id}")
        
        return jsonify({
            'success': True,
            'message': f'Customer account deleted: {email}',
            'deleted_customer': {
                'email': email,
                'customer_id': customer_id,
                'company': company
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Admin customer deletion error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

@admin_customer_bp.route('/api/admin/customers/list', methods=['GET'])
@cross_origin()
def list_all_customers():
    """
    List all customer accounts (admin only)
    """
    try:
        # Get admin password for security
        admin_password = request.headers.get('X-Admin-Password', '')
        expected_admin_pass = os.getenv('LEMMA_ADMIN_PASS', '.511MeV/c^2')
        
        if admin_password != expected_admin_pass:
            return jsonify({
                'success': False,
                'error': 'Invalid admin password'
            }), 401
        
        # Get all customers
        db = get_db()
        customers = db.query(Customer).all()
        
        customer_list = []
        for customer in customers:
            customer_list.append({
                'customer_id': customer.customer_id,
                'email': customer.email,
                'company': customer.company,
                'status': customer.status,
                'role': customer.role,
                'created_at': customer.created_at.isoformat(),
                'last_login': customer.last_login.isoformat() if customer.last_login else None,
                'api_keys_count': len(customer.api_keys or [])
            })
        
        db.close()
        
        return jsonify({
            'success': True,
            'customers': customer_list,
            'total_customers': len(customer_list)
        })
        
    except Exception as e:
        logger.error(f"❌ Admin customer list error: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500
