#!/usr/bin/env python3
"""
QR Code Generation API for Lemma Wallet Sync
"""

from flask import Blueprint, request, jsonify, send_file
from flask_cors import cross_origin
import qrcode
import io
import base64
import json

qr_generator_bp = Blueprint('qr_generator', __name__)

@qr_generator_bp.route('/api/qr/generate', methods=['POST'])
@cross_origin()
def generate_qr_code():
    """
    Generate QR code image for wallet sync
    Accepts sync data in POST body to avoid URL length limits
    """
    try:
        data = request.get_json()
        
        if not data or 'sync_url' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing sync_url in request body'
            }), 400
        
        sync_url = data['sync_url']
        size = data.get('size', 250)  # Default 250x250
        
        # Create QR code
        qr = qrcode.QRCode(
            version=1,  # Auto-adjust version based on data
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        
        qr.add_data(sync_url)
        qr.make(fit=True)
        
        # Create image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Resize to requested size
        img = img.resize((size, size))
        
        # Convert to bytes
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        # Return image directly
        return send_file(
            img_buffer,
            mimetype='image/png',
            as_attachment=False
        )
        
    except Exception as e:
        print(f"❌ QR generation failed: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@qr_generator_bp.route('/api/qr/generate-base64', methods=['POST'])
@cross_origin()
def generate_qr_base64():
    """
    Generate QR code as base64 data URL
    """
    try:
        data = request.get_json()
        
        if not data or 'sync_url' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing sync_url in request body'
            }), 400
        
        sync_url = data['sync_url']
        size = data.get('size', 250)
        
        # Create QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        
        qr.add_data(sync_url)
        qr.make(fit=True)
        
        # Create image
        img = qr.make_image(fill_color="black", back_color="white")
        img = img.resize((size, size))
        
        # Convert to base64
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        img_base64 = base64.b64encode(img_buffer.getvalue()).decode()
        data_url = f"data:image/png;base64,{img_base64}"
        
        return jsonify({
            'success': True,
            'qr_image_data_url': data_url,
            'url_length': len(sync_url),
            'qr_version': qr.version
        })
        
    except Exception as e:
        print(f"❌ QR base64 generation failed: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500