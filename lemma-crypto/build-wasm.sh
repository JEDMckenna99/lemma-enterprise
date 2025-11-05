#!/bin/bash
# Build Lemma OPRF module for WebAssembly

echo "🦀 Building Lemma OPRF for WebAssembly..."
echo "=========================================="

# Check if wasm-pack is installed
if ! command -v wasm-pack &> /dev/null; then
    echo "❌ wasm-pack not found! Installing..."
    cargo install wasm-pack
fi

# Build for web (ES modules)
echo "📦 Building WASM module for web..."
wasm-pack build \
    --target web \
    --out-dir ../static/wasm \
    --out-name lemma-oprf \
    --features wasm \
    --no-typescript \
    --release

if [ $? -eq 0 ]; then
    echo "✅ WASM build successful!"
    echo "📁 Output: static/wasm/lemma-oprf.js"
    echo "📁 Output: static/wasm/lemma-oprf_bg.wasm"
    
    # Display file sizes
    echo ""
    echo "📊 File sizes:"
    ls -lh ../static/wasm/lemma-oprf* | awk '{print "  " $9 ": " $5}'
    
    # Gzip sizes (for production)
    echo ""
    echo "📦 Gzipped sizes:"
    gzip -c ../static/wasm/lemma-oprf_bg.wasm | wc -c | awk '{print "  WASM (gzipped): " $1 " bytes"}'
    gzip -c ../static/wasm/lemma-oprf.js | wc -c | awk '{print "  JS (gzipped): " $1 " bytes"}'
else
    echo "❌ WASM build failed!"
    exit 1
fi

echo ""
echo "🎉 WASM build complete! Ready for client-side OPRF."

