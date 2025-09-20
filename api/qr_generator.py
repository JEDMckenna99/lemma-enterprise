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
import gzip
import hashlib

qr_generator_bp = Blueprint('qr_generator', __name__)

# In-memory storage for compressed sync data (in production, use Redis)
compressed_sync_cache = {}

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
        
        # Create QR code with settings optimized for large data
        qr = qrcode.QRCode(
            version=None,  # Auto-detect version based on data size
            error_correction=qrcode.constants.ERROR_CORRECT_L,  # Lowest error correction for max data
            box_size=8,    # Smaller box size for higher density
            border=2,      # Smaller border for more space
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
    Generate QR code as base64 data URL with compression for large URLs
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
        
        print(f"📊 Original URL length: {len(sync_url)}")
        
        # For very long URLs, create a short URL using our own shortening service
        if len(sync_url) > 2000:
            # Extract the sync parameter
            if '?sync=' in sync_url:
                sync_param = sync_url.split('?sync=')[1]
                
                # Create a short hash for this sync data
                sync_hash = hashlib.sha256(sync_param.encode()).hexdigest()[:12]
                
                # Store the full sync data temporarily (in production, use Redis/database)
                # For now, create a shorter URL by compressing the sync parameter
                try:
                    # Compress the sync parameter
                    compressed_data = gzip.compress(sync_param.encode())
                    compressed_b64 = base64.b64encode(compressed_data).decode()
                    
                    # Create compressed URL
                    base_url = sync_url.split('?')[0]
                    short_url = f"{base_url}?c={compressed_b64}"
                    
                    print(f"📊 Compressed URL length: {len(short_url)}")
                    
                    if len(short_url) < len(sync_url):
                        sync_url = short_url
                        print(f"✅ Using compressed URL (saved {len(data['sync_url']) - len(short_url)} characters)")
                except Exception as e:
                    print(f"⚠️ Compression failed, using original URL: {e}")
        
        # Check if URL is still too long for QR codes
        if len(sync_url) > 2950:  # QR version 40 limit with low error correction
            return jsonify({
                'success': False,
                'error': f'URL too long for QR code: {len(sync_url)} characters (max ~2950)'
            }), 400
        
        # Create QR code with settings optimized for large data
        qr = qrcode.QRCode(
            version=None,  # Auto-detect version based on data size
            error_correction=qrcode.constants.ERROR_CORRECT_L,  # Lowest error correction for max data
            box_size=8,    # Smaller box size for higher density
            border=2,      # Smaller border for more space
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

@qr_generator_bp.route('/api/qr/expand-compressed', methods=['POST'])
@cross_origin()
def expand_compressed_url():
    """
    Expand a compressed sync URL back to original format
    """
    try:
        data = request.get_json()
        
        if not data or 'compressed_param' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing compressed_param in request body'
            }), 400
        
        compressed_param = data['compressed_param']
        
        try:
            # Decompress the parameter
            compressed_data = base64.b64decode(compressed_param.encode())
            original_param = gzip.decompress(compressed_data).decode()
            
            return jsonify({
                'success': True,
                'original_sync_param': original_param
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'Decompression failed: {str(e)}'
            }), 400
            
    except Exception as e:
        print(f"❌ URL expansion failed: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500