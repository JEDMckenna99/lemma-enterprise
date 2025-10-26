# Simple WebAssembly Build (Without C Dependencies)
# Excludes ring and other C-dependent crates for easy WASM compilation

$ErrorActionPreference = "Stop"

Write-Host "🚀 Building Lemma Crypto WebAssembly (Simple Mode)..." -ForegroundColor Green

# Check if wasm-pack is installed
try {
    wasm-pack --version | Out-Null
} catch {
    Write-Host "❌ wasm-pack not found. Installing via cargo..." -ForegroundColor Red
    cargo install wasm-pack
}

Write-Host "📦 Installing WebAssembly target..." -ForegroundColor Cyan
rustup target add wasm32-unknown-unknown

Write-Host "🔧 Building WebAssembly module (no C dependencies)..." -ForegroundColor Cyan

# Create output directory
if (-not (Test-Path "../static/wasm")) {
    New-Item -ItemType Directory -Path "../static/wasm" -Force | Out-Null
}

# Build with minimal features (no ring, no C dependencies)
wasm-pack build `
    --target web `
    --out-dir ../static/wasm `
    --release `
    --no-default-features `
    --features wasm

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ WebAssembly build successful!" -ForegroundColor Green
    
    Write-Host "`n📁 Generated files:" -ForegroundColor Cyan
    Get-ChildItem "../static/wasm" | Format-Table Name, Length
    
    Write-Host "`n📊 WASM module size:" -ForegroundColor Cyan
    $wasmFile = Get-ChildItem "../static/wasm/*.wasm"
    $sizeKB = [math]::Round($wasmFile.Length / 1KB, 2)
    Write-Host "   $sizeKB KB" -ForegroundColor White
    
    Write-Host "`n✅ Client-side verification ready!" -ForegroundColor Green
    Write-Host "   • Ed25519 signature verification in browser" -ForegroundColor White
    Write-Host "   • Expected: 10-100µs per verification" -ForegroundColor White
    Write-Host "   • Cost: `$0.00 per verification" -ForegroundColor White
    Write-Host "   • Server calls: 0" -ForegroundColor White
    
    Write-Host "`n🌐 Test at: https://lemma.id/test-client-verification" -ForegroundColor Yellow
} else {
    Write-Host "❌ Build failed. Check errors above." -ForegroundColor Red
    exit 1
}

