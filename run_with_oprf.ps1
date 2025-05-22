Write-Host "Starting Lemma with integrated OPRF service..."

# Set up OPRF service first
if (-not (Test-Path "bin/oprfservice.exe")) {
    Write-Host "OPRF service binary not found, building it now..."
    & .\bin\setup_oprf.ps1
}

# Check for key directory
if (-not (Test-Path "instance/data/keys")) {
    New-Item -Path "instance/data/keys" -ItemType Directory -Force
}

# Set up environment
$Env:OPRF_SERVICE_INTERNAL = "true"
$Env:FLASK_APP = "app.py"
$Env:FLASK_DEBUG = "true"

# Get a free port for the web app
$webPort = 5000
# Get a free port for the OPRF service
$oprfPort = 8080

Write-Host "Starting services:"
Write-Host "* Web app on port: $webPort"
Write-Host "* OPRF service on port: $oprfPort"

# Start both services
Start-Process -FilePath "bin\oprfservice.exe" -ArgumentList "--port=$oprfPort", "--keydir=instance/data/keys" -NoNewWindow
Start-Sleep -Seconds 2  # Give the OPRF service time to start
Write-Host "OPRF service started."

Write-Host "Starting web app..."
python app.py

# Note: When you kill this script, you'll need to manually kill the OPRF service process 