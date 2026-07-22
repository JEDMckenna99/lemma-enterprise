"""
SRI (Subresource Integrity) Hash API

Provides endpoints for customers to verify SDK integrity:
- GET /api/sdk/integrity - Returns current SRI hashes for all SDK files
- GET /api/sdk/integrity/<filename> - Returns hash for specific file

Usage by customers:
    fetch('https://lemma.id/api/sdk/integrity')
        .then(r => r.json())
        .then(data => console.log(data.files['lemma-wallet.js'].integrity));
"""

from flask import Blueprint, jsonify, request
import hashlib
import base64
import os
import re
from datetime import datetime
from functools import lru_cache
import time

sri_hashes_bp = Blueprint('sri_hashes', __name__)

# SDK files and their public URLs
SDK_FILES = {
    'lemma-wallet.js': {
        'path': 'static/js/lemma-wallet.js',
        'url': '/sdk/lemma-wallet.js',
        'description': 'Main Lemma Wallet SDK'
    },
    'lemma-shield.js': {
        'path': 'static/js/lemma-shield.js',
        'url': '/sdk/lemma-shield.js',
        'description': 'Lemma Shield (inline verification)'
    },
    'proof-verifier.js': {
        'path': 'static/js/ishuman-verifier.js',
        'url': '/sdk/proof-verifier.js',
        'description': 'Browser proof verifier (isHuman / passkey)'
    },
    'proof-verifier.mjs': {
        'path': 'static/js/proof-verifier.mjs',
        'url': '/sdk/proof-verifier.mjs',
        'description': 'Backend proof verifier (Node/Edge)'
    }
}

# Cache hashes for 60 seconds (balance between freshness and performance)
_hash_cache = {}
_cache_time = 0
CACHE_TTL = 60


def _generate_sri_hash(file_path: str, algorithm: str = 'sha384') -> str | None:
    """Generate SRI hash for a file."""
    try:
        with open(file_path, 'rb') as f:
            content = f.read()
        
        if algorithm == 'sha384':
            hash_obj = hashlib.sha384(content)
        elif algorithm == 'sha256':
            hash_obj = hashlib.sha256(content)
        elif algorithm == 'sha512':
            hash_obj = hashlib.sha512(content)
        else:
            return None
        
        hash_base64 = base64.b64encode(hash_obj.digest()).decode('utf-8')
        return f"{algorithm}-{hash_base64}"
    except Exception:
        return None


def _get_file_info(file_path: str) -> dict | None:
    """Get file metadata."""
    try:
        stat = os.stat(file_path)
        return {
            'size_bytes': stat.st_size,
            'modified': datetime.fromtimestamp(stat.st_mtime).isoformat() + 'Z'
        }
    except Exception:
        return None


def _get_sdk_version() -> str:
    """Extract SDK version from lemma-wallet.js."""
    try:
        with open('static/js/lemma-wallet.js', 'r', encoding='utf-8') as f:
            content = f.read(5000)  # Version is near the top
        
        match = re.search(r"static VERSION\s*=\s*['\"]([^'\"]+)['\"]", content)
        if match:
            return match.group(1)
    except Exception:
        pass
    
    return 'unknown'


def _get_all_hashes(algorithm: str = 'sha384') -> dict:
    """Get hashes for all SDK files with caching."""
    global _hash_cache, _cache_time
    
    cache_key = algorithm
    current_time = time.time()
    
    # Check cache
    if cache_key in _hash_cache and (current_time - _cache_time) < CACHE_TTL:
        return _hash_cache[cache_key]
    
    # Generate fresh hashes
    result = {
        'sdk_version': _get_sdk_version(),
        'algorithm': algorithm,
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'files': {}
    }
    
    for filename, config in SDK_FILES.items():
        file_path = config['path']
        sri_hash = _generate_sri_hash(file_path, algorithm)
        file_info = _get_file_info(file_path)
        
        if sri_hash and file_info:
            result['files'][filename] = {
                'integrity': sri_hash,
                'url': f"https://lemma.id{config['url']}",
                'size_bytes': file_info['size_bytes'],
                'modified': file_info['modified'],
                'description': config['description']
            }
    
    # Update cache
    _hash_cache[cache_key] = result
    _cache_time = current_time
    
    return result


@sri_hashes_bp.route('/api/sdk/integrity', methods=['GET'])
def get_sdk_integrity():
    """
    Get SRI hashes for all SDK files.
    
    Query params:
        algorithm: sha256, sha384 (default), or sha512
        format: json (default) or html
    
    Returns:
        JSON with integrity hashes for all SDK files
    """
    algorithm = request.args.get('algorithm', 'sha384')
    output_format = request.args.get('format', 'json')
    
    if algorithm not in ('sha256', 'sha384', 'sha512'):
        return jsonify({'error': 'Invalid algorithm. Use sha256, sha384, or sha512'}), 400
    
    hashes = _get_all_hashes(algorithm)
    
    if output_format == 'html':
        # Return HTML snippet for easy copy-paste
        html_parts = [
            f"<!-- Lemma SDK v{hashes['sdk_version']} -->",
            f"<!-- Generated: {hashes['generated_at']} -->",
            ""
        ]
        
        for filename, info in hashes['files'].items():
            html_parts.append(f'<script src="{info["url"]}"')
            html_parts.append(f'        integrity="{info["integrity"]}"')
            html_parts.append('        crossorigin="anonymous"></script>')
            html_parts.append('')
        
        response = '\n'.join(html_parts)
        return response, 200, {'Content-Type': 'text/html; charset=utf-8'}
    
    return jsonify(hashes)


@sri_hashes_bp.route('/api/sdk/integrity/<filename>', methods=['GET'])
def get_file_integrity(filename: str):
    """
    Get SRI hash for a specific SDK file.
    
    Path params:
        filename: e.g., lemma-wallet.js
    
    Query params:
        algorithm: sha256, sha384 (default), or sha512
    
    Returns:
        JSON with integrity hash for the specified file
    """
    algorithm = request.args.get('algorithm', 'sha384')
    
    if algorithm not in ('sha256', 'sha384', 'sha512'):
        return jsonify({'error': 'Invalid algorithm'}), 400
    
    if filename not in SDK_FILES:
        return jsonify({
            'error': 'File not found',
            'available_files': list(SDK_FILES.keys())
        }), 404
    
    config = SDK_FILES[filename]
    sri_hash = _generate_sri_hash(config['path'], algorithm)
    file_info = _get_file_info(config['path'])
    
    if not sri_hash or not file_info:
        return jsonify({'error': 'Could not generate hash'}), 500
    
    return jsonify({
        'filename': filename,
        'integrity': sri_hash,
        'algorithm': algorithm,
        'url': f"https://lemma.id{config['url']}",
        'size_bytes': file_info['size_bytes'],
        'modified': file_info['modified'],
        'sdk_version': _get_sdk_version(),
        'usage': f'<script src="https://lemma.id{config["url"]}" integrity="{sri_hash}" crossorigin="anonymous"></script>'
    })


@sri_hashes_bp.route('/api/sdk/verify', methods=['POST'])
def verify_integrity():
    """
    Verify that a provided hash matches the current SDK.
    
    Useful for CI/CD pipelines to detect SDK updates.
    
    Request body:
        {
            "filename": "lemma-wallet.js",
            "expected_hash": "sha384-..."
        }
    
    Returns:
        { "valid": true/false, "current_hash": "...", "message": "..." }
    """
    data = request.get_json() or {}
    filename = data.get('filename', 'lemma-wallet.js')
    expected_hash = data.get('expected_hash', '')
    
    if not expected_hash:
        return jsonify({'error': 'expected_hash required'}), 400
    
    if filename not in SDK_FILES:
        return jsonify({'error': 'File not found'}), 404
    
    # Extract algorithm from expected hash
    if expected_hash.startswith('sha256-'):
        algorithm = 'sha256'
    elif expected_hash.startswith('sha384-'):
        algorithm = 'sha384'
    elif expected_hash.startswith('sha512-'):
        algorithm = 'sha512'
    else:
        return jsonify({'error': 'Invalid hash format. Expected sha256-..., sha384-..., or sha512-...'}), 400
    
    config = SDK_FILES[filename]
    current_hash = _generate_sri_hash(config['path'], algorithm)
    
    if not current_hash:
        return jsonify({'error': 'Could not generate current hash'}), 500
    
    is_valid = current_hash == expected_hash
    
    return jsonify({
        'valid': is_valid,
        'filename': filename,
        'expected_hash': expected_hash,
        'current_hash': current_hash,
        'sdk_version': _get_sdk_version(),
        'message': 'Hash matches - SDK integrity verified' if is_valid else 'Hash mismatch - SDK may have been updated'
    })
