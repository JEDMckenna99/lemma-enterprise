#!/bin/bash

# Lemma Crypto WebAssembly Build Script
# Phase 3 - Client-side QR verification with 0.36µs performance

set -e

echo "🚀 Building Lemma Crypto WebAssembly Module..."

# Check if wasm-pack is installed
if ! command -v wasm-pack &> /dev/null; then
    echo "❌ wasm-pack not found. Installing wasm-pack..."
    curl https://rustwasm.github.io/wasm-pack/installer/init.sh -sSf | sh
fi

# Check if cargo is installed
if ! command -v cargo &> /dev/null; then
    echo "❌ cargo not found. Please install Rust first."
    exit 1
fi

echo "📦 Installing WebAssembly target..."
rustup target add wasm32-unknown-unknown

echo "🔧 Building WebAssembly module with optimizations..."

# Build for web with maximum optimizations
wasm-pack build \
    --target web \
    --out-dir ../static/pkg \
    --release \
    --scope lemma \
    -- \
    --features wasm-qr,qr-verification \
    -Z build-std=std,panic_abort \
    -Z build-std-features=panic_immediate_abort

echo "📁 Checking output directory..."
ls -la ../static/pkg/

echo "🎯 WebAssembly build completed successfully!"
echo "📊 Module size:"
ls -lh ../static/pkg/*.wasm

echo ""
echo "✅ Ready for Phase 3 client-side QR verification!"
echo "   • Target performance: 0.36µs verification"
echo "   • Full offline capability"
echo "   • Zero server requests"
echo ""
echo "🌐 Test the WebAssembly demo at: /demo/qr/wasm" 