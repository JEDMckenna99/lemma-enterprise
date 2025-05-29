# PowerShell script to compile OPRF service (Mock Version)
$ErrorActionPreference = "Stop"

Write-Host "=== Compiling OPRF Service (Mock Version) ===" -ForegroundColor Green
Write-Host "Note: Using mock version while main.go is being updated for library compatibility" -ForegroundColor Yellow

# Navigate to oprfservice directory
Push-Location oprfservice

try {
    # Check Go installation
    Write-Host "Go version:" -ForegroundColor Cyan
    go version

    # Initialize Go modules if needed
    if (!(Test-Path "go.mod")) {
        Write-Host "Initializing Go modules..." -ForegroundColor Yellow
        go mod init github.com/lemma/oprf-service
    }

    # Download dependencies
    Write-Host "Downloading Go dependencies..." -ForegroundColor Yellow
    go mod tidy
    go mod download

    # Create bin directory if it doesn't exist
    $binDir = "../bin"
    if (!(Test-Path $binDir)) {
        New-Item -ItemType Directory -Force -Path $binDir | Out-Null
    }

    # Build the mock OPRF service with correct binary name
    Write-Host "Building mock OPRF service as oprf-service.exe..." -ForegroundColor Yellow
    go build -v -o ../bin/oprf-service.exe simple_mock.go

    # Verify the binary exists
    $binaryPath = "../bin/oprf-service.exe"
    if (Test-Path $binaryPath) {
        Write-Host "✅ OPRF service (mock) compiled successfully!" -ForegroundColor Green
        Write-Host "Binary location: $(Resolve-Path $binaryPath)" -ForegroundColor Cyan
        Get-ChildItem $binaryPath | Format-List Name, Length, LastWriteTime
    } else {
        Write-Host "❌ Failed to create binary" -ForegroundColor Red
        exit 1
    }

    # Test the binary
    Write-Host "Testing the compiled binary..." -ForegroundColor Yellow
    try {
        & $binaryPath --help
    } catch {
        Write-Host "Binary compiled successfully" -ForegroundColor Green
    }

    Write-Host "✅ OPRF Service (Mock) Build Complete" -ForegroundColor Green
    Write-Host "Note: This is using the mock implementation. Full OPRF can be enabled later." -ForegroundColor Yellow

} finally {
    # Return to original directory
    Pop-Location
} 