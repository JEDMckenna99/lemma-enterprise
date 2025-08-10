"""
Ultra-Simple Site Federation Join API
====================================

Enables sites to join the Lemma federated network with just 3 lines of code:

1. Include the script tag
2. Add data-lemma-protect to elements  
3. That's it!

Example:
<script src="https://lemma.id/join?site=yoursite.com"></script>
<div data-lemma-protect>Protected Content</div>
"""

from flask import Blueprint, request, jsonify, Response, render_template_string
from .network_config import NETWORK_CONFIG, get_federation_endpoints, get_network_registry_url
import logging
import secrets
import time

logger = logging.getLogger(__name__)

# Simple join blueprint
simple_join_bp = Blueprint('simple_join', __name__)

@simple_join_bp.route('/join', methods=['GET'])
def auto_join_script():
    """
    Ultra-simple federation join - returns JavaScript that auto-configures everything
    
    Usage: <script src="https://lemma.id/join?site=yoursite.com"></script>
    """
    try:
        # Get site from query parameter
        site_origin = request.args.get('site', request.headers.get('Referer', 'unknown'))
        
        # Clean up site origin
        if not site_origin.startswith('http'):
            site_origin = f"https://{site_origin}"
        
        # Generate simple API key for this site
        api_key = f"lemma_auto_{secrets.token_hex(16)}"
        
        logger.info(f"🚀 Auto-join request from site: {site_origin}")
        
        # Auto-approve the site (in production, this could have validation)
        from .realtime_network_sync import sync_manager
        sync_manager.add_network_node(site_origin)
        
        # Generate the auto-configuration JavaScript
        js_code = f"""
// 🔐 LEMMA FEDERATED IDENTITY - AUTO-CONFIGURATION
// Generated for: {site_origin}
// API Key: {api_key}

(function() {{
    console.log('🔐 Lemma Federated Identity - Initializing...');
    
    // Auto-detect current origin
    const currentOrigin = window.location.origin;
    
    // Configuration
    const LEMMA_CONFIG = {{
        apiBase: '{get_network_registry_url().replace('/api/network/sync', '')}',
        networkRegistryUrl: '{get_network_registry_url()}',
        networkAuthKey: '{NETWORK_CONFIG["network_authority_key"]}',
        nodeId: 'auto_' + btoa(currentOrigin).replace(/[^a-zA-Z0-9]/g, '').substring(0, 12),
        federationEndpoints: {get_federation_endpoints()},
        apiKey: '{api_key}',
        debug: true
    }};
    
    // Load the federated wallet
    const walletScript = document.createElement('script');
    walletScript.src = LEMMA_CONFIG.apiBase + '/static/js/lemma-federated-wallet.js';
    walletScript.onload = function() {{
        // Initialize federated wallet
        window.lemmaWallet = new LemmaFederatedWallet({{
            networkRegistryUrl: LEMMA_CONFIG.networkRegistryUrl,
            networkAuthKey: LEMMA_CONFIG.networkAuthKey,
            debug: LEMMA_CONFIG.debug
        }});
        
        // Load the bot shield
        const shieldScript = document.createElement('script');
        shieldScript.src = LEMMA_CONFIG.apiBase + '/static/js/lemma-bot-shield-simple.js';
        shieldScript.onload = function() {{
            // Initialize bot shield
            window.lemmaShield = new LemmaBotShield({{
                apiBase: LEMMA_CONFIG.apiBase,
                apiKey: LEMMA_CONFIG.apiKey,
                debug: LEMMA_CONFIG.debug,
                securityLevel: 'medium'
            }});
            
            // Auto-protect elements with data-lemma-protect
            document.addEventListener('DOMContentLoaded', function() {{
                const protectedElements = document.querySelectorAll('[data-lemma-protect]');
                console.log(`🛡️ Auto-protecting ${{protectedElements.length}} elements`);
                
                protectedElements.forEach(function(element, index) {{
                    const elementId = element.id || 'lemma-protected-' + index;
                    if (!element.id) element.id = elementId;
                    
                    window.lemmaShield.protect('#' + elementId);
                }});
                
                console.log('✅ Lemma Federation Ready - Site joined network!');
                
                // Dispatch ready event
                window.dispatchEvent(new CustomEvent('lemma:ready', {{
                    detail: {{
                        config: LEMMA_CONFIG,
                        wallet: window.lemmaWallet,
                        shield: window.lemmaShield
                    }}
                }}));
            }});
            
            // If DOM already loaded, run immediately
            if (document.readyState === 'complete' || document.readyState === 'interactive') {{
                document.dispatchEvent(new Event('DOMContentLoaded'));
            }}
        }};
        document.head.appendChild(shieldScript);
    }};
    document.head.appendChild(walletScript);
    
    // Add some basic CSS for protected content
    const style = document.createElement('style');
    style.textContent = `
        [data-lemma-protect] {{
            position: relative;
        }}
        
        [data-lemma-protect].lemma-hidden {{
            display: none !important;
        }}
        
        .lemma-verification-overlay {{
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(255, 255, 255, 0.95);
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            z-index: 1000;
            border-radius: 8px;
        }}
        
        .lemma-verify-button {{
            background: linear-gradient(135deg, #6366f1, #8b5cf6);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        
        .lemma-verify-button:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 16px rgba(99, 102, 241, 0.4);
        }}
        
        .lemma-status {{
            position: fixed;
            top: 20px;
            right: 20px;
            background: white;
            padding: 12px 16px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
            font-size: 14px;
            z-index: 10000;
            border-left: 4px solid #10b981;
        }}
    `;
    document.head.appendChild(style);
    
    // Show federation status
    const statusDiv = document.createElement('div');
    statusDiv.className = 'lemma-status';
    statusDiv.innerHTML = '🔐 Joined Lemma Federation';
    document.body.appendChild(statusDiv);
    
    // Auto-remove status after 3 seconds
    setTimeout(() => statusDiv.remove(), 3000);
    
}})();

// Expose simple API for manual control
window.Lemma = {{
    protect: function(selector) {{
        if (window.lemmaShield) {{
            window.lemmaShield.protect(selector);
        }} else {{
            console.warn('Lemma shield not ready yet');
        }}
    }},
    
    verify: function() {{
        if (window.lemmaWallet) {{
            // Trigger verification flow
            window.location.href = '{get_network_registry_url().replace('/api/network/sync', '')}/templates/modern/onboarding/start.html';
        }} else {{
            console.warn('Lemma wallet not ready yet');
        }}
    }},
    
    status: function() {{
        return {{
            ready: !!(window.lemmaWallet && window.lemmaShield),
            wallet: !!window.lemmaWallet,
            shield: !!window.lemmaShield,
            origin: currentOrigin,
            nodeId: LEMMA_CONFIG.nodeId
        }};
    }}
}};

console.log('🔐 Lemma Auto-Join Script Loaded for:', '{site_origin}');
"""
        
        # Return JavaScript with proper content type
        response = Response(js_code, mimetype='application/javascript')
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        
        logger.info(f"✅ Generated auto-join script for {site_origin}")
        
        return response
        
    except Exception as e:
        logger.error(f"❌ Auto-join script generation failed: {e}")
        
        # Return error handling JavaScript
        error_js = f"""
console.error('Lemma Auto-Join Failed: {str(e)}');
alert('Lemma Federation join failed. Please contact support.');
"""
        return Response(error_js, mimetype='application/javascript', status=500)

@simple_join_bp.route('/join-guide', methods=['GET'])
def join_guide():
    """Show the simple integration guide"""
    
    base_url = get_network_registry_url().replace('/api/network/sync', '')
    
    guide_html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Join Lemma Federation - 3 Lines of Code</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 40px 20px;
            line-height: 1.6;
            color: #333;
        }}
        
        .hero {{
            text-align: center;
            margin-bottom: 60px;
        }}
        
        .hero h1 {{
            font-size: 3rem;
            background: linear-gradient(135deg, #6366f1, #8b5cf6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 20px;
        }}
        
        .hero p {{
            font-size: 1.3rem;
            color: #666;
        }}
        
        .step {{
            background: white;
            border-radius: 12px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
            border-left: 5px solid #10b981;
        }}
        
        .step h2 {{
            color: #10b981;
            margin-bottom: 15px;
        }}
        
        pre {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            overflow-x: auto;
            border: 1px solid #e9ecef;
        }}
        
        code {{
            color: #e83e8c;
            font-weight: 600;
        }}
        
        .demo {{
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            padding: 30px;
            border-radius: 12px;
            text-align: center;
            margin: 40px 0;
        }}
        
        .demo h3 {{
            margin-bottom: 20px;
        }}
        
        .demo button {{
            background: rgba(255, 255, 255, 0.2);
            color: white;
            border: 2px solid rgba(255, 255, 255, 0.3);
            padding: 12px 24px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 16px;
            transition: all 0.3s;
        }}
        
        .demo button:hover {{
            background: rgba(255, 255, 255, 0.3);
            transform: translateY(-2px);
        }}
        
        .benefits {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 40px 0;
        }}
        
        .benefit {{
            text-align: center;
            padding: 20px;
        }}
        
        .benefit-icon {{
            font-size: 3rem;
            margin-bottom: 15px;
        }}
    </style>
</head>
<body>
    <div class="hero">
        <h1>🔐 Join Lemma Federation</h1>
        <p>Add human verification and bot protection to your site with just <strong>3 lines of code</strong></p>
    </div>
    
    <div class="step">
        <h2>Step 1: Include the Script</h2>
        <p>Add this single script tag to your HTML head:</p>
        <pre><code>&lt;script src="{base_url}/join?site=yoursite.com"&gt;&lt;/script&gt;</code></pre>
        <p><small>Replace <code>yoursite.com</code> with your actual domain</small></p>
    </div>
    
    <div class="step">
        <h2>Step 2: Protect Your Content</h2>
        <p>Add the <code>data-lemma-protect</code> attribute to any element you want to protect:</p>
        <pre><code>&lt;div data-lemma-protect&gt;
    &lt;h2&gt;Members Only Content&lt;/h2&gt;
    &lt;p&gt;This content is only visible to verified humans!&lt;/p&gt;
&lt;/div&gt;</code></pre>
    </div>
    
    <div class="step">
        <h2>Step 3: That's It!</h2>
        <p>Your site is now part of the Lemma federated network. Users who verify once on any Lemma site can access your protected content instantly.</p>
        <pre><code>// Optional: Listen for ready event
window.addEventListener('lemma:ready', function(event) {{
    console.log('Lemma Federation Ready!', event.detail);
}});

// Optional: Manual control
Lemma.protect('#my-element');  // Protect specific elements
Lemma.verify();                // Trigger verification
Lemma.status();                // Check status</code></pre>
    </div>
    
    <div class="demo">
        <h3>🚀 Live Demo</h3>
        <p>See it in action - this button is protected by Lemma:</p>
        <div data-lemma-protect>
            <button onclick="alert('You are verified!')">Protected Button</button>
        </div>
    </div>
    
    <div class="benefits">
        <div class="benefit">
            <div class="benefit-icon">⚡</div>
            <h3>Microsecond Verification</h3>
            <p>1-50 microsecond verification using Rust cryptography</p>
        </div>
        
        <div class="benefit">
            <div class="benefit-icon">🌐</div>
            <h3>Cross-Site Recognition</h3>
            <p>Users verify once, access everywhere in the network</p>
        </div>
        
        <div class="benefit">
            <div class="benefit-icon">🔒</div>
            <h3>Privacy-Preserving</h3>
            <p>Zero-knowledge proofs and minimal data storage</p>
        </div>
        
        <div class="benefit">
            <div class="benefit-icon">🛡️</div>
            <h3>Bot Protection</h3>
            <p>Automatic protection against bots and automated attacks</p>
        </div>
    </div>
    
    <script src="{base_url}/join?site={{{{ window.location.hostname }}}}"></script>
</body>
</html>
"""
    
    return render_template_string(guide_html)

@simple_join_bp.route('/api/simple-join/status', methods=['GET'])
def join_status():
    """Check if a site has successfully joined the federation"""
    try:
        site_origin = request.args.get('site', request.headers.get('Referer', 'unknown'))
        
        # Check if site is in the federation
        from .realtime_network_sync import sync_manager
        is_member = site_origin in sync_manager.network_nodes
        
        return jsonify({
            'success': True,
            'site': site_origin,
            'is_federation_member': is_member,
            'network_name': NETWORK_CONFIG['network_name'],
            'node_count': len(sync_manager.network_nodes),
            'endpoints': list(sync_manager.network_nodes)[:5]  # Show first 5
        })
        
    except Exception as e:
        logger.error(f"❌ Join status check failed: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
