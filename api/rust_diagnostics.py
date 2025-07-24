"""
Rust Engine Diagnostics - Debug endpoint for Heroku deployment
"""

import os
import sys
import json
import glob
import importlib.util
from flask import Blueprint, jsonify
import logging

logger = logging.getLogger(__name__)

rust_diagnostics_bp = Blueprint('rust_diagnostics', __name__)

@rust_diagnostics_bp.route('/api/rust-diagnostics')
def rust_diagnostics():
    """
    Comprehensive diagnostics for Rust engine issues on Heroku
    """
    diagnostics = {
        'timestamp': int(time.time()) if 'time' in globals() else 'unknown',
        'python_info': {
            'version': sys.version,
            'executable': sys.executable,
            'path': sys.path[:5],  # First 5 entries
            'platform': sys.platform
        },
        'environment': {
            'pwd': os.getcwd(),
            'home': os.environ.get('HOME', 'unknown'),
            'path': os.environ.get('PATH', 'unknown')[:200],  # First 200 chars
        },
        'rust_engine_status': {
            'import_attempted': False,
            'import_successful': False,
            'initialization_successful': False,
            'error': None
        },
        'file_search': {
            'lemma_files': [],
            'wheel_files': [],
            'so_files': []
        },
        'package_info': {
            'installed_packages': [],
            'lemma_packages': []
        }
    }
    
    # Search for relevant files
    try:
        diagnostics['file_search']['lemma_files'] = glob.glob('**/*lemma*', recursive=True)[:10]
        diagnostics['file_search']['wheel_files'] = glob.glob('**/*.whl', recursive=True)[:5]
        diagnostics['file_search']['so_files'] = glob.glob('**/*.so', recursive=True)[:5]
    except Exception as e:
        diagnostics['file_search']['error'] = str(e)
    
    # Check installed packages
    try:
        import pkg_resources
        installed = [str(d) for d in pkg_resources.working_set]
        diagnostics['package_info']['installed_packages'] = [p for p in installed if 'lemma' in p.lower()][:5]
        diagnostics['package_info']['total_packages'] = len(installed)
    except Exception as e:
        diagnostics['package_info']['error'] = str(e)
    
    # Test Rust engine import
    diagnostics['rust_engine_status']['import_attempted'] = True
    try:
        import lemma_crypto
        diagnostics['rust_engine_status']['import_successful'] = True
        diagnostics['rust_engine_status']['module_file'] = getattr(lemma_crypto, '__file__', 'unknown')
        
        try:
            from lemma_crypto import PyLemmaCore
            core = PyLemmaCore()
            diagnostics['rust_engine_status']['initialization_successful'] = True
            diagnostics['rust_engine_status']['core_type'] = str(type(core))
        except Exception as init_error:
            diagnostics['rust_engine_status']['initialization_error'] = str(init_error)
            
    except ImportError as import_error:
        diagnostics['rust_engine_status']['import_error'] = str(import_error)
        diagnostics['rust_engine_status']['import_error_type'] = 'ImportError'
    except Exception as other_error:
        diagnostics['rust_engine_status']['import_error'] = str(other_error)
        diagnostics['rust_engine_status']['import_error_type'] = type(other_error).__name__
    
    # Check success markers
    try:
        if os.path.exists('.rust_engine_success'):
            with open('.rust_engine_success', 'r') as f:
                diagnostics['build_markers'] = {'local': f.read()}
        if os.path.exists('/app/.rust_engine_success'):
            with open('/app/.rust_engine_success', 'r') as f:
                diagnostics['build_markers'] = diagnostics.get('build_markers', {})
                diagnostics['build_markers']['app'] = f.read()
    except Exception as e:
        diagnostics['build_markers'] = {'error': str(e)}
    
    return jsonify(diagnostics)

# Add import at top of file
import time 