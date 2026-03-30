#!/bin/bash
# Build optimized WASM for browser deployment

echo "🦀 Building Optimized Lemma Crypto WASM"
echo "Target: 5-15μs browser authentication"
echo "========================================"

# Install wasm-pack if not available
if ! command -v wasm-pack &> /dev/null; then
    echo "📦 Installing wasm-pack..."
    curl https://rustwasm.github.io/wasm-pack/installer/init.sh -sSf | sh
fi

# Build WASM with optimizations
echo "🔧 Building WASM with maximum optimizations..."
wasm-pack build --target web --release --features wasm \
    --out-dir pkg-wasm \
    -- --features wasm

if [ $? -eq 0 ]; then
    echo "✅ WASM build successful!"
    
    # Check file sizes
    echo ""
    echo "📊 WASM Bundle Sizes:"
    ls -lh pkg-wasm/*.wasm | awk '{print "   " $5 " - " $9}'
    
    # Generate browser integration
    echo ""
    echo "📝 Generating browser integration..."
    
    cat > pkg-wasm/lemma-browser-crypto.js << 'EOF'
/**
 * Lemma Browser Crypto - Ultra-Fast WASM Authentication
 * 
 * Provides 5-15μs authentication directly in the browser
 * No network calls required for verification
 */

import init, { 
    MinimalIssuer, 
    MinimalCore, 
    OptimizedVerifier,
    UltraOptimizedVerifier 
} from './lemma_crypto.js';

class LemmaBrowserCrypto {
    constructor() {
        this.initialized = false;
        this.verifier = null;
        this.issuer = null;
    }
    
    async init() {
        if (this.initialized) return;
        
        console.log('🔐 Initializing Lemma Browser Crypto (WASM)...');
        
        // Initialize WASM module
        await init();
        
        // Create optimized verifier for browser
        this.verifier = new UltraOptimizedVerifier();
        this.issuer = new MinimalIssuer();
        
        this.initialized = true;
        console.log('✅ Lemma Browser Crypto ready - ultra-fast authentication enabled');
        console.log(`✅ Expected performance: 5-15μs per verification`);
    }
    
    async verifyCredential(credential) {
        if (!this.initialized) await this.init();
        
        const start = performance.now();
        const result = this.verifier.verify_credential(JSON.stringify(credential));
        const end = performance.now();
        
        const timeUs = (end - start) * 1000; // Convert ms to μs
        
        return {
            verified: result.verified,
            signature_valid: result.signature_valid,
            not_revoked: result.not_revoked,
            confidence: result.confidence,
            verification_time_us: timeUs,
            cache_hit: result.cache_hit,
            engine: 'wasm_ultra_optimized',
            offline: true
        };
    }
    
    async createCredential(subject, claims) {
        if (!this.initialized) await this.init();
        
        return this.issuer.issue_credential(subject, claims);
    }
    
    getPerformanceStats() {
        if (!this.verifier) return null;
        return this.verifier.get_ultra_stats();
    }
}

// Global instance
window.LemmaBrowserCrypto = new LemmaBrowserCrypto();

// Auto-initialize
window.addEventListener('load', async () => {
    try {
        await window.LemmaBrowserCrypto.init();
        console.log('🚀 Lemma Browser Crypto auto-initialized');
    } catch (error) {
        console.error('❌ Lemma Browser Crypto initialization failed:', error);
    }
});

export default LemmaBrowserCrypto;
EOF
    
    echo "✅ Browser integration generated: pkg-wasm/lemma-browser-crypto.js"
    
    # Generate usage example
    cat > pkg-wasm/example.html << 'EOF'
<!DOCTYPE html>
<html>
<head>
    <title>Lemma Browser Crypto Demo</title>
</head>
<body>
    <h1>🔐 Lemma Ultra-Fast Browser Authentication</h1>
    <p>Target: 5-15μs verification in browser</p>
    
    <button onclick="testAuthentication()">Test Authentication</button>
    <div id="results"></div>
    
    <script type="module">
        import LemmaBrowserCrypto from './lemma-browser-crypto.js';
        
        window.testAuthentication = async function() {
            const results = document.getElementById('results');
            results.innerHTML = '🔄 Testing...';
            
            try {
                // Create test credential
                const credential = await window.LemmaBrowserCrypto.createCredential(
                    'did:lemma:browser_test_user',
                    { packageType: 'identity', isHuman: 'true' }
                );
                
                // Verify credential (should be 5-15μs)
                const verification = await window.LemmaBrowserCrypto.verifyCredential(credential);
                
                results.innerHTML = `
                    <h3>✅ Browser Authentication Results:</h3>
                    <p><strong>Verified:</strong> ${verification.verified}</p>
                    <p><strong>Time:</strong> ${verification.verification_time_us.toFixed(3)} μs</p>
                    <p><strong>Engine:</strong> ${verification.engine}</p>
                    <p><strong>Offline:</strong> ${verification.offline}</p>
                `;
                
            } catch (error) {
                results.innerHTML = `❌ Error: ${error.message}`;
            }
        };
    </script>
</body>
</html>
EOF
    
    echo "✅ Demo page generated: pkg-wasm/example.html"
    echo ""
    echo "🚀 WASM build complete!"
    echo "📁 Files ready for CDN deployment in pkg-wasm/"
    
else
    echo "❌ WASM build failed"
    exit 1
fi
