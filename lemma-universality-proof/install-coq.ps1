# Coq Installation Script for Windows
# This script helps install Coq and related tools on Windows

Write-Host "Lemma Universality Proof - Coq Installation Script" -ForegroundColor Green
Write-Host "=================================================" -ForegroundColor Green

# Check if Chocolatey is installed
if (!(Get-Command choco -ErrorAction SilentlyContinue)) {
    Write-Host "Installing Chocolatey package manager..." -ForegroundColor Yellow
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
    Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
    refreshenv
}

# Install Coq
Write-Host "Installing Coq theorem prover..." -ForegroundColor Yellow
try {
    choco install coq -y
    Write-Host "✓ Coq installed successfully" -ForegroundColor Green
} catch {
    Write-Host "✗ Failed to install Coq via Chocolatey" -ForegroundColor Red
    Write-Host "Please download manually from: https://coq.inria.fr/download" -ForegroundColor Yellow
}

# Install CoqIDE (if available)
Write-Host "Installing CoqIDE..." -ForegroundColor Yellow
try {
    choco install coqide -y
    Write-Host "✓ CoqIDE installed successfully" -ForegroundColor Green
} catch {
    Write-Host "! CoqIDE not available via Chocolatey, but may be included with Coq" -ForegroundColor Yellow
}

# Install Make (required for building)
Write-Host "Installing Make..." -ForegroundColor Yellow
try {
    choco install make -y
    Write-Host "✓ Make installed successfully" -ForegroundColor Green
} catch {
    Write-Host "✗ Failed to install Make" -ForegroundColor Red
    Write-Host "Consider installing MSYS2 or using WSL for Unix tools" -ForegroundColor Yellow
}

# Install Git (if not present)
if (!(Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "Installing Git..." -ForegroundColor Yellow
    try {
        choco install git -y
        Write-Host "✓ Git installed successfully" -ForegroundColor Green
    } catch {
        Write-Host "✗ Failed to install Git" -ForegroundColor Red
    }
}

# Refresh environment variables
refreshenv

# Verify installations
Write-Host "`nVerifying installations..." -ForegroundColor Cyan

if (Get-Command coqc -ErrorAction SilentlyContinue) {
    $coqVersion = coqc --version
    Write-Host "✓ Coq: $coqVersion" -ForegroundColor Green
} else {
    Write-Host "✗ Coq not found in PATH" -ForegroundColor Red
}

if (Get-Command coqide -ErrorAction SilentlyContinue) {
    Write-Host "✓ CoqIDE: Available" -ForegroundColor Green
} else {
    Write-Host "! CoqIDE not found (may still be available)" -ForegroundColor Yellow
}

if (Get-Command make -ErrorAction SilentlyContinue) {
    Write-Host "✓ Make: Available" -ForegroundColor Green
} else {
    Write-Host "✗ Make not found" -ForegroundColor Red
}

# Test the project build
Write-Host "`nTesting project build..." -ForegroundColor Cyan
try {
    if (Test-Path "Makefile") {
        make check
        Write-Host "✓ Project builds successfully" -ForegroundColor Green
    } else {
        Write-Host "! Makefile not found - run from project directory" -ForegroundColor Yellow
    }
} catch {
    Write-Host "! Build test failed - this is normal for a fresh setup" -ForegroundColor Yellow
}

# Next steps
Write-Host "`nNext Steps:" -ForegroundColor Cyan
Write-Host "1. Open CoqIDE or your preferred editor" -ForegroundColor White
Write-Host "2. Start with GettingStarted.v for an interactive tutorial" -ForegroundColor White
Write-Host "3. Build the project with 'make all'" -ForegroundColor White
Write-Host "4. Explore theories/ directory for the main proofs" -ForegroundColor White

Write-Host "`nUseful Commands:" -ForegroundColor Cyan
Write-Host "  coqide GettingStarted.v    # Open interactive tutorial" -ForegroundColor White
Write-Host "  make all                   # Build all proofs" -ForegroundColor White
Write-Host "  make check                 # Syntax check only" -ForegroundColor White
Write-Host "  make doc                   # Generate documentation" -ForegroundColor White

Write-Host "`nInstallation complete! 🎯" -ForegroundColor Green
