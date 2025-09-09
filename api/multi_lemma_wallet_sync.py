"""
Multi-Lemma Wallet Sync API
Enables secure device sync using QR Authentication + Device Delegation lemmas
"""

from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
import logging
import json
import time
import qrcode
import io
import base64

logger = logging.getLogger(__name__)

# Create blueprint
multi_lemma_sync_bp = Blueprint('multi_lemma_sync', __name__)

# Import multi-lemma crypto engine
try:
    from lemma_crypto import PyQRSyncManager, PyDeviceDelegationManager, PyMinimalIssuer
    MULTI_LEMMA_AVAILABLE = True
    logger.info("✅ Multi-lemma wallet sync engine loaded")
except ImportError as e:
    MULTI_LEMMA_AVAILABLE = False
    logger.error(f"❌ Multi-lemma engine not available: {e}")

@multi_lemma_sync_bp.route('/api/wallet-sync/create-qr-auth', methods=['POST'])
@cross_origin()
def create_qr_auth_lemma():
    """
    Create QR Authentication Lemma for device sync
    
    POST /api/wallet-sync/create-qr-auth
    {
        "mobile_device_did": "did:lemma:{mobile_public_key}",
        "requesting_device_did": "did:lemma:{browser_public_key}",
        "requested_scope": ["federated_identity", "iam_permissions"],
        "requested_duration": 86400,
        "device_fingerprint": "browser_fingerprint_hash"
    }
    """
    try:
        if not MULTI_LEMMA_AVAILABLE:
            return jsonify({
                'success': False,
                'error': 'multi_lemma_engine_not_available',
                'message': 'Multi-lemma wallet sync engine not available'
            }), 500
        
        data = request.get_json()
        mobile_device_did = data.get('mobile_device_did')
        requesting_device_did = data.get('requesting_device_did')
        requested_scope = data.get('requested_scope', ['federated_identity'])
        requested_duration = data.get('requested_duration', 86400)  # 24 hours default
        device_fingerprint = data.get('device_fingerprint', 'unknown')
        
        if not all([mobile_device_did, requesting_device_did]):
            return jsonify({
                'success': False,
                'error': 'missing_required_fields',
                'message': 'mobile_device_did and requesting_device_did are required'
            }), 400
        
        # Create mobile device issuer (in production, would use stored key)
        mobile_issuer = PyMinimalIssuer()
        qr_sync_manager = PyQRSyncManager()
        
        # Create QR authentication lemma
        qr_start = time.perf_counter_ns()
        qr_lemma_json = qr_sync_manager.create_qr_auth_lemma(
            mobile_issuer,
            requesting_device_did,
            requested_scope,
            requested_duration,
            device_fingerprint
        )
        qr_time_ns = time.perf_counter_ns() - qr_start
        
        # Generate QR code data
        qr_data = qr_sync_manager.generate_qr_data(qr_lemma_json)
        
        # Create QR code image
        qr_img = qrcode.QRCode(version=1, box_size=10, border=5)
        qr_img.add_data(qr_data)
        qr_img.make(fit=True)
        
        # Convert to base64 image
        img = qr_img.make_image(fill_color="black", back_color="white")
        img_buffer = io.BytesIO()
        img.save(img_buffer, format='PNG')
        img_base64 = base64.b64encode(img_buffer.getvalue()).decode()
        
        qr_lemma = json.loads(qr_lemma_json)
        
        logger.info(f"✅ QR Authentication Lemma created: {qr_lemma['id']}")
        logger.info(f"⚡ QR creation time: {qr_time_ns / 1000:.3f}μs")
        
        return jsonify({
            'success': True,
            'qr_auth_lemma': qr_lemma,
            'qr_data': qr_data,
            'qr_image_base64': f"data:image/png;base64,{img_base64}",
            'creation_time_ns': qr_time_ns,
            'expires_at': qr_lemma['expirationDate'],
            'sync_scope': requested_scope,
            'multi_lemma_sync': True
        })
        
    except Exception as e:
        logger.error(f"❌ QR auth lemma creation failed: {e}")
        return jsonify({
            'success': False,
            'error': 'qr_auth_creation_failed',
            'message': str(e)
        }), 500

@multi_lemma_sync_bp.route('/api/wallet-sync/verify-qr-auth', methods=['POST'])
@cross_origin()
def verify_qr_auth_lemma():
    """
    Verify QR Authentication Lemma and create device delegation
    
    POST /api/wallet-sync/verify-qr-auth
    {
        "qr_data": "base64_encoded_qr_lemma"
    }
    """
    try:
        if not MULTI_LEMMA_AVAILABLE:
            return jsonify({
                'success': False,
                'error': 'multi_lemma_engine_not_available'
            }), 500
        
        data = request.get_json()
        qr_data = data.get('qr_data')
        
        if not qr_data:
            return jsonify({
                'success': False,
                'error': 'qr_data_required',
                'message': 'QR data is required'
            }), 400
        
        qr_sync_manager = PyQRSyncManager()
        
        # Parse QR data into lemma
        qr_parse_start = time.perf_counter_ns()
        qr_lemma_json = qr_sync_manager.parse_qr_data(qr_data)
        qr_parse_time = time.perf_counter_ns() - qr_parse_start
        
        # Verify QR authentication lemma
        qr_verify_start = time.perf_counter_ns()
        qr_result = qr_sync_manager.verify_qr_auth_lemma(qr_lemma_json)
        qr_verify_time = time.perf_counter_ns() - qr_verify_start
        
        qr_lemma = json.loads(qr_lemma_json)
        
        logger.info(f"🔍 QR Auth Lemma verification: {qr_lemma['id']}")
        logger.info(f"⚡ Parse time: {qr_parse_time / 1000:.3f}μs")
        logger.info(f"⚡ Verify time: {qr_verify_time / 1000:.3f}μs")
        logger.info(f"✅ QR Valid: {qr_result.valid}, Sync Authorized: {qr_result.sync_authorized}")
        
        if qr_result.valid and qr_result.sync_authorized:
            delegation_lemma = None
            if qr_result.delegation_lemma_json:
                delegation_lemma = json.loads(qr_result.delegation_lemma_json)
            
            return jsonify({
                'success': True,
                'qr_verification': {
                    'valid': qr_result.valid,
                    'reason': qr_result.reason,
                    'sync_authorized': qr_result.sync_authorized
                },
                'delegation_lemma': delegation_lemma,
                'qr_auth_lemma': qr_lemma,
                'performance': {
                    'qr_parse_time_ns': qr_parse_time,
                    'qr_verify_time_ns': qr_verify_time,
                    'total_time_ns': qr_parse_time + qr_verify_time
                },
                'multi_lemma_sync': True,
                'lemma_types_used': ['qr_authentication', 'device_delegation']
            })
        else:
            return jsonify({
                'success': False,
                'error': 'qr_verification_failed',
                'reason': qr_result.reason,
                'qr_valid': qr_result.valid,
                'sync_authorized': qr_result.sync_authorized
            }), 401
        
    except Exception as e:
        logger.error(f"❌ QR auth verification failed: {e}")
        return jsonify({
            'success': False,
            'error': 'qr_verification_error',
            'message': str(e)
        }), 500

@multi_lemma_sync_bp.route('/api/wallet-sync/verify-delegation', methods=['POST'])
@cross_origin()
def verify_device_delegation():
    """
    Verify device delegation lemma for ongoing access
    
    POST /api/wallet-sync/verify-delegation
    {
        "delegation_lemma": {...}
    }
    """
    try:
        if not MULTI_LEMMA_AVAILABLE:
            return jsonify({
                'success': False,
                'error': 'multi_lemma_engine_not_available'
            }), 500
        
        data = request.get_json()
        delegation_lemma = data.get('delegation_lemma')
        
        if not delegation_lemma:
            return jsonify({
                'success': False,
                'error': 'delegation_lemma_required'
            }), 400
        
        delegation_manager = PyDeviceDelegationManager()
        
        # Verify delegation lemma
        verify_start = time.perf_counter_ns()
        is_valid = delegation_manager.verify_device_delegation(json.dumps(delegation_lemma))
        verify_time = time.perf_counter_ns() - verify_start
        
        logger.info(f"🔐 Device Delegation verification: {delegation_lemma['id']}")
        logger.info(f"⚡ Verification time: {verify_time / 1000:.3f}μs")
        logger.info(f"✅ Delegation Valid: {is_valid}")
        
        return jsonify({
            'success': True,
            'delegation_valid': is_valid,
            'delegation_id': delegation_lemma['id'],
            'expires_at': delegation_lemma.get('expirationDate'),
            'scope': delegation_lemma.get('credentialSubject', {}).get('delegationScope', []),
            'verification_time_ns': verify_time,
            'multi_lemma_sync': True
        })
        
    except Exception as e:
        logger.error(f"❌ Delegation verification failed: {e}")
        return jsonify({
            'success': False,
            'error': 'delegation_verification_error',
            'message': str(e)
        }), 500

@multi_lemma_sync_bp.route('/api/wallet-sync/complete-sync', methods=['POST'])
@cross_origin()
def complete_wallet_sync():
    """
    Complete multi-lemma wallet sync process
    
    Verifies both QR authentication and device delegation lemmas
    Returns success only if both lemma verifications pass
    """
    try:
        if not MULTI_LEMMA_AVAILABLE:
            return jsonify({
                'success': False,
                'error': 'multi_lemma_engine_not_available'
            }), 500
        
        data = request.get_json()
        qr_data = data.get('qr_data')
        delegation_lemma = data.get('delegation_lemma')
        
        if not qr_data or not delegation_lemma:
            return jsonify({
                'success': False,
                'error': 'missing_lemmas',
                'message': 'Both QR data and delegation lemma required'
            }), 400
        
        total_start = time.perf_counter_ns()
        
        # Step 1: Verify QR authentication lemma
        qr_sync_manager = PyQRSyncManager()
        qr_lemma_json = qr_sync_manager.parse_qr_data(qr_data)
        qr_result = qr_sync_manager.verify_qr_auth_lemma(qr_lemma_json)
        
        # Step 2: Verify device delegation lemma
        delegation_manager = PyDeviceDelegationManager()
        delegation_valid = delegation_manager.verify_device_delegation(json.dumps(delegation_lemma))
        
        total_time = time.perf_counter_ns() - total_start
        
        # Both lemmas must be valid for successful sync
        sync_successful = qr_result.valid and delegation_valid
        
        logger.info(f"🔄 Multi-lemma wallet sync complete")
        logger.info(f"   QR Auth Lemma: {qr_result.valid}")
        logger.info(f"   Delegation Lemma: {delegation_valid}")
        logger.info(f"   Overall Success: {sync_successful}")
        logger.info(f"⚡ Total verification time: {total_time / 1000:.3f}μs")
        
        return jsonify({
            'success': sync_successful,
            'sync_result': {
                'qr_authentication': {
                    'valid': qr_result.valid,
                    'reason': qr_result.reason
                },
                'device_delegation': {
                    'valid': delegation_valid
                },
                'overall_valid': sync_successful
            },
            'performance': {
                'total_verification_time_ns': total_time,
                'lemmas_verified': 2,
                'verification_method': 'multi_lemma_cryptographic'
            },
            'sync_details': {
                'qr_lemma_id': json.loads(qr_lemma_json)['id'],
                'delegation_lemma_id': delegation_lemma['id'],
                'scope': delegation_lemma.get('credentialSubject', {}).get('delegationScope', []),
                'expires_at': delegation_lemma.get('expirationDate')
            },
            'multi_lemma_sync': True
        })
        
    except Exception as e:
        logger.error(f"❌ Multi-lemma wallet sync failed: {e}")
        return jsonify({
            'success': False,
            'error': 'multi_lemma_sync_failed',
            'message': str(e)
        }), 500

@multi_lemma_sync_bp.route('/api/wallet-sync/health', methods=['GET'])
@cross_origin()
def wallet_sync_health():
    """Health check for multi-lemma wallet sync system"""
    
    health_status = {
        'status': 'ready' if MULTI_LEMMA_AVAILABLE else 'unavailable',
        'multi_lemma_engine': MULTI_LEMMA_AVAILABLE,
        'lemma_types_supported': [
            'qr_authentication',
            'device_delegation',
            'federated_identity',
            'iam_permissions'
        ] if MULTI_LEMMA_AVAILABLE else [],
        'sync_capabilities': {
            'qr_auth_creation': MULTI_LEMMA_AVAILABLE,
            'qr_verification': MULTI_LEMMA_AVAILABLE,
            'device_delegation': MULTI_LEMMA_AVAILABLE,
            'complete_sync': MULTI_LEMMA_AVAILABLE
        },
        'performance_targets': {
            'qr_auth_creation': '~33μs',
            'qr_verification': '~33μs',
            'delegation_verification': '~33μs',
            'complete_sync': '~100μs'
        },
        'storage_overhead': 'zero_lemma_platform_storage',
        'privacy_model': 'oprf_encrypted_user_controlled'
    }
    
    return jsonify(health_status)

@multi_lemma_sync_bp.route('/api/wallet-sync/demo', methods=['GET'])
@cross_origin()
def wallet_sync_demo():
    """Demo page for multi-lemma wallet sync"""
    
    demo_html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Multi-Lemma Wallet Sync Demo</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        .lemma {{ border: 1px solid #ccc; padding: 20px; margin: 20px 0; }}
        .success {{ background: #e8f5e8; }}
        .error {{ background: #ffe8e8; }}
        button {{ padding: 10px 20px; margin: 10px 0; }}
    </style>
</head>
<body>
    <h1>🔄 Multi-Lemma Wallet Sync Demo</h1>
    <p>Strategic application of atomic lemma principle to device sync</p>
    
    <div class="lemma">
        <h3>📱 Step 1: Create QR Authentication Lemma</h3>
        <p>Mobile device creates cryptographically signed QR code</p>
        <button onclick="createQRAuth()">Create QR Auth Lemma</button>
        <div id="qr-result"></div>
    </div>
    
    <div class="lemma">
        <h3>🔐 Step 2: Verify QR & Create Delegation</h3>
        <p>Browser verifies QR authenticity and receives delegation lemma</p>
        <button onclick="verifyQRAuth()">Verify QR Auth Lemma</button>
        <div id="verify-result"></div>
    </div>
    
    <div class="lemma">
        <h3>✅ Step 3: Complete Multi-Lemma Sync</h3>
        <p>Verify both lemmas for complete wallet sync authorization</p>
        <button onclick="completeSync()">Complete Multi-Lemma Sync</button>
        <div id="sync-result"></div>
    </div>
    
    <script>
        let qrData = null;
        let delegationLemma = null;
        
        async function createQRAuth() {{
            const result = document.getElementById('qr-result');
            result.innerHTML = '🔄 Creating QR Authentication Lemma...';
            
            try {{
                const response = await fetch('/api/wallet-sync/create-qr-auth', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        mobile_device_did: 'did:lemma:mobile_test_device',
                        requesting_device_did: 'did:lemma:browser_test_device',
                        requested_scope: ['federated_identity', 'iam_permissions'],
                        requested_duration: 86400,
                        device_fingerprint: 'demo_browser_fingerprint'
                    }})
                }});
                
                const data = await response.json();
                
                if (data.success) {{
                    qrData = data.qr_data;
                    result.className = 'lemma success';
                    result.innerHTML = `
                        <h4>✅ QR Authentication Lemma Created</h4>
                        <p><strong>Lemma ID:</strong> ${{data.qr_auth_lemma.id}}</p>
                        <p><strong>Creation Time:</strong> ${{(data.creation_time_ns / 1000).toFixed(3)}}μs</p>
                        <p><strong>Expires:</strong> ${{new Date(data.expires_at * 1000).toLocaleString()}}</p>
                        <img src="${{data.qr_image_base64}}" alt="QR Code" style="max-width: 200px;">
                    `;
                }} else {{
                    result.className = 'lemma error';
                    result.innerHTML = `❌ Error: ${{data.message}}`;
                }}
            }} catch (error) {{
                result.className = 'lemma error';
                result.innerHTML = `❌ Error: ${{error.message}}`;
            }}
        }}
        
        async function verifyQRAuth() {{
            if (!qrData) {{
                alert('Please create QR Auth Lemma first');
                return;
            }}
            
            const result = document.getElementById('verify-result');
            result.innerHTML = '🔄 Verifying QR Authentication Lemma...';
            
            try {{
                const response = await fetch('/api/wallet-sync/verify-qr-auth', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ qr_data: qrData }})
                }});
                
                const data = await response.json();
                
                if (data.success) {{
                    delegationLemma = data.delegation_lemma;
                    result.className = 'lemma success';
                    result.innerHTML = `
                        <h4>✅ QR Verified & Delegation Created</h4>
                        <p><strong>QR Valid:</strong> ${{data.qr_verification.valid}}</p>
                        <p><strong>Sync Authorized:</strong> ${{data.qr_verification.sync_authorized}}</p>
                        <p><strong>Delegation ID:</strong> ${{data.delegation_lemma?.id}}</p>
                        <p><strong>Verification Time:</strong> ${{(data.performance.total_time_ns / 1000).toFixed(3)}}μs</p>
                        <p><strong>Lemma Types:</strong> ${{data.lemma_types_used.join(', ')}}</p>
                    `;
                }} else {{
                    result.className = 'lemma error';
                    result.innerHTML = `❌ Error: ${{data.reason}}`;
                }}
            }} catch (error) {{
                result.className = 'lemma error';
                result.innerHTML = `❌ Error: ${{error.message}}`;
            }}
        }}
        
        async function completeSync() {{
            if (!qrData || !delegationLemma) {{
                alert('Please complete previous steps first');
                return;
            }}
            
            const result = document.getElementById('sync-result');
            result.innerHTML = '🔄 Completing Multi-Lemma Sync...';
            
            try {{
                const response = await fetch('/api/wallet-sync/complete-sync', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        qr_data: qrData,
                        delegation_lemma: delegationLemma
                    }})
                }});
                
                const data = await response.json();
                
                if (data.success) {{
                    result.className = 'lemma success';
                    result.innerHTML = `
                        <h4>🎉 Multi-Lemma Wallet Sync Complete!</h4>
                        <p><strong>Sync Successful:</strong> ${{data.sync_result.overall_valid}}</p>
                        <p><strong>Lemmas Verified:</strong> ${{data.performance.lemmas_verified}}</p>
                        <p><strong>Total Time:</strong> ${{(data.performance.total_verification_time_ns / 1000).toFixed(3)}}μs</p>
                        <p><strong>QR Lemma:</strong> ${{data.sync_details.qr_lemma_id}}</p>
                        <p><strong>Delegation Lemma:</strong> ${{data.sync_details.delegation_lemma_id}}</p>
                        <p><strong>Scope:</strong> ${{data.sync_details.scope.join(', ')}}</p>
                        <h4>🏆 Strategic Evolution of Atomic Verification!</h4>
                    `;
                }} else {{
                    result.className = 'lemma error';
                    result.innerHTML = `❌ Sync Failed: ${{data.message}}`;
                }}
            }} catch (error) {{
                result.className = 'lemma error';
                result.innerHTML = `❌ Error: ${{error.message}}`;
            }}
        }}
    </script>
</body>
</html>
    """
    
    return demo_html
