#!/bin/bash
# Build WebAssembly module for client-side verification

echo "🦀 Building Lemma Crypto WASM module..."

# Install wasm-pack if needed
if ! command -v wasm-pack &> /dev/null; then
    echo "📦 Installing wasm-pack..."
    cargo install wasm-pack
fi

# Build WASM with optimizations
echo "⚙️  Compiling Rust to WebAssembly..."
cd lemma-crypto
wasm-pack build \
    --target web \
    --out-dir ../static/wasm \
    --features wasm \
    --release

echo "✅ WASM build complete!"
echo "📁 Files created in static/wasm/:"
ls -lh ../static/wasm/

echo ""
echo "🎯 To use in browser:"
echo "   import init, { verify_signature_bytes } from '/static/wasm/lemma_crypto.js';"
echo "   await init();"
echo "   const isValid = verify_signature_bytes(publicKey, message, signature);"


