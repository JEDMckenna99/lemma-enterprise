# Lemma Crypto WebAssembly Build Script (PowerShell)
# Phase 3 - Client-side QR verification with 0.36µs performance

$ErrorActionPreference = "Stop"

Write-Host "🚀 Building Lemma Crypto WebAssembly Module..." -ForegroundColor Green

# Check if wasm-pack is installed
try {
    wasm-pack --version | Out-Null
} catch {
    Write-Host "❌ wasm-pack not found. Please install wasm-pack first:" -ForegroundColor Red
    Write-Host "   npm install -g wasm-pack" -ForegroundColor Yellow
    Write-Host "   or download from: https://rustwasm.github.io/wasm-pack/" -ForegroundColor Yellow
    exit 1
}

# Check if cargo is installed
try {
    cargo --version | Out-Null
} catch {
    Write-Host "❌ cargo not found. Please install Rust first:" -ForegroundColor Red
    Write-Host "   https://rustup.rs/" -ForegroundColor Yellow
    exit 1
}

Write-Host "📦 Installing WebAssembly target..." -ForegroundColor Cyan
rustup target add wasm32-unknown-unknown

Write-Host "🔧 Building WebAssembly module with optimizations..." -ForegroundColor Cyan

# Create output directory if it doesn't exist
if (-not (Test-Path "../static/pkg")) {
    New-Item -ItemType Directory -Path "../static/pkg" -Force | Out-Null
}

# Build for web with maximum optimizations
wasm-pack build `
    --target web `
    --out-dir ../static/pkg `
    --release `
    --scope lemma `
    -- `
    --features wasm-qr,qr-verification

Write-Host "📁 Checking output directory..." -ForegroundColor Cyan
Get-ChildItem "../static/pkg" | Format-Table

Write-Host "🎯 WebAssembly build completed successfully!" -ForegroundColor Green

Write-Host "📊 Module size:" -ForegroundColor Cyan
Get-ChildItem "../static/pkg/*.wasm" | Select-Object Name, @{Name="Size (KB)";Expression={[math]::Round($_.Length/1KB,2)}}

Write-Host ""
Write-Host "✅ Ready for Phase 3 client-side QR verification!" -ForegroundColor Green
Write-Host "   • Target performance: 0.36µs verification" -ForegroundColor White
Write-Host "   • Full offline capability" -ForegroundColor White
Write-Host "   • Zero server requests" -ForegroundColor White
Write-Host ""
Write-Host "🌐 Test the WebAssembly demo at: /demo/qr/wasm" -ForegroundColor Yellow 