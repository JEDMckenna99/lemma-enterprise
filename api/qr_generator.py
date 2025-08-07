"""
Lemma QR Code Generator API
"""

import json
import hashlib
import hmac
import time
from datetime import datetime
from flask import Blueprint, request, jsonify
import logging

logger = logging.getLogger(__name__)
qr_generator_bp = Blueprint('qr_generator', __name__)

class LemmaQRGenerator:
    def __init__(self):
        self.demo_key = "lemma_demo_key_2024"
    
    def generate_demo_signature(self, claims):
        """Generate demo signature for QR codes"""
        claims_json = json.dumps(claims, sort_keys=True)
        timestamp = str(int(time.time()))
        message = f"{claims_json}:{timestamp}"
        signature = hmac.new(
            self.demo_key.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()[:32]
        return f"lemma:sig:{signature}:{timestamp}"
    
    def create_qr_data(self, qr_type, claims, metadata=None):
        """Create QR code data with Lemma signature"""
        claims['timestamp'] = datetime.utcnow().isoformat() + 'Z'
        claims['qr_id'] = hashlib.sha256(
            f"{qr_type}:{json.dumps(claims, sort_keys=True)}:{time.time()}"
            .encode()
        ).hexdigest()[:16]
        
        lemma_signature = self.generate_demo_signature(claims)
        
        verification_times = {
            'ticket': 4.2, 'product': 3.8, 'access': 5.1
        }
        
        return {
            'type': 'lemma_verification',
            'qr_type': qr_type,
            'claims': claims,
            'lemma_signature': lemma_signature,
            'offline_verification': True,
            'verification_time_us': verification_times.get(qr_type, 5.0)
        }

qr_generator = LemmaQRGenerator()

@qr_generator_bp.route('/api/qr/demo-codes', methods=['GET'])
def get_demo_qr_codes():
    """Get demo QR codes for the demo page"""
    try:
        demo_codes = []
        
        # Event Ticket
        ticket_data = qr_generator.create_qr_data(
            'ticket',
            {
                'event_name': 'Tech Conference 2024',
                'ticket_id': 'TC2024-001',
                'seat': 'A-15',
                'date': '2024-12-15'
            }
        )
        demo_codes.append({
            'id': 'ticket',
            'title': 'Event Ticket',
            'data': json.dumps(ticket_data, separators=(',', ':'))
        })
        
        # Product Authentication
        product_data = qr_generator.create_qr_data(
            'product',
            {
                'product_name': 'Premium Headphones',
                'serial_number': 'PH-2024-789',
                'manufacturer': 'AudioTech Inc'
            }
        )
        demo_codes.append({
            'id': 'product',
            'title': 'Product Authentication',
            'data': json.dumps(product_data, separators=(',', ':'))
        })
        
        # Access Control
        access_data = qr_generator.create_qr_data(
            'access',
            {
                'access_level': 'Level 3',
                'building': 'Main Office',
                'room': 'Conference Room B',
                'user_id': 'emp_001'
            }
        )
        demo_codes.append({
            'id': 'access',
            'title': 'Access Control',
            'data': json.dumps(access_data, separators=(',', ':'))
        })
        
        return jsonify({
            'success': True,
            'demo_codes': demo_codes
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500