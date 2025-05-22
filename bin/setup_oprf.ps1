Write-Host "Setting up OPRF service..."

# Create the keys directory if it doesn't exist
if (-not (Test-Path "instance/data/keys")) {
    New-Item -Path "instance/data/keys" -ItemType Directory -Force
}

# Check if we already have keys
if (-not (Test-Path "instance/data/keys/oprf_key.json")) {
    Write-Host "Generating OPRF keys..."
    Push-Location oprfservice
    go run keygen/keygen.go -keyfile ../instance/data/keys/oprf_key.json
    Pop-Location
} else {
    Write-Host "OPRF keys already exist"
}

# Build the OPRF service binary
Write-Host "Building OPRF service binary..."
Push-Location oprfservice
go build -o ../bin/oprfservice.exe
Pop-Location

Write-Host "OPRF service setup complete!" 