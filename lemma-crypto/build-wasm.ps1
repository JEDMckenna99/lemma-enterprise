# Build Lemma OPRF module for WebAssembly (PowerShell script for Windows)

Write-Host "🦀 Building Lemma OPRF for WebAssembly..." -ForegroundColor Cyan
Write-Host "=========================================="

# Check if wasm-pack is installed
$wasmPackInstalled = Get-Command wasm-pack -ErrorAction SilentlyContinue
if (-not $wasmPackInstalled) {
    Write-Host "❌ wasm-pack not found! Installing..." -ForegroundColor Red
    cargo install wasm-pack
}

# Build for web (ES modules)
Write-Host "📦 Building WASM module for web..." -ForegroundColor Yellow

wasm-pack build `
    --target web `
    --out-dir ../static/wasm `
    --out-name lemma-oprf `
    --features wasm `
    --no-typescript `
    --release

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ WASM build successful!" -ForegroundColor Green
    Write-Host "📁 Output: static/wasm/lemma-oprf.js"
    Write-Host "📁 Output: static/wasm/lemma-oprf_bg.wasm"
    
    # Display file sizes
    Write-Host ""
    Write-Host "📊 File sizes:" -ForegroundColor Cyan
    $jsFile = Get-Item "../static/wasm/lemma-oprf.js" -ErrorAction SilentlyContinue
    $wasmFile = Get-Item "../static/wasm/lemma-oprf_bg.wasm" -ErrorAction SilentlyContinue
    
    if ($jsFile) {
        $jsSizeKB = [math]::Round($jsFile.Length / 1KB, 2)
        Write-Host "  lemma-oprf.js: $jsSizeKB KB"
    }
    
    if ($wasmFile) {
        $wasmSizeKB = [math]::Round($wasmFile.Length / 1KB, 2)
        Write-Host "  lemma-oprf_bg.wasm: $wasmSizeKB KB"
    }
    
    Write-Host ""
    Write-Host "🎉 WASM build complete! Ready for client-side OPRF." -ForegroundColor Green
} else {
    Write-Host "❌ WASM build failed!" -ForegroundColor Red
    exit 1
}

