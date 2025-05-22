# PowerShell script to deploy OPRF service to Heroku
# Run this script with PowerShell from the project root directory

# Check if Heroku CLI is installed
if (-not (Get-Command heroku -ErrorAction SilentlyContinue)) {
    Write-Error "Heroku CLI is not installed. Please install it first."
    Exit 1
}

# Check if user is logged in
try {
    $whoami = heroku auth:whoami
    Write-Host "Logged in to Heroku as: $whoami"
}
catch {
    Write-Host "You are not logged in to Heroku. Please run 'heroku login' first."
    Exit 1
}

# Prompt for OPRF service Heroku app name
$oprfAppName = Read-Host "Enter your OPRF service Heroku app name (e.g. lemma-enterprise-oprf)"

if ([string]::IsNullOrWhiteSpace($oprfAppName)) {
    $oprfAppName = "lemma-enterprise-oprf"
}

# Check if the app exists, create it if needed
$appExists = $false
try {
    heroku apps:info --app $oprfAppName | Out-Null
    $appExists = $true
    Write-Host "Using existing Heroku app: $oprfAppName"
}
catch {
    Write-Host "App doesn't exist. Creating new app: $oprfAppName"
    heroku create --app $oprfAppName
}

# Make sure we're using the container stack
Write-Host "Setting stack to container..."
heroku stack:set container --app $oprfAppName

# Create a clean temporary directory for deployment
$tempDir = "oprf-deploy-temp"
if (Test-Path $tempDir) {
    Remove-Item -Path $tempDir -Recurse -Force
}
Write-Host "Creating temporary directory for deployment: $tempDir"
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null

# Copy OPRF service files to the temp directory
Write-Host "Copying OPRF service files to temporary directory..."
Copy-Item -Path "oprfservice\*" -Destination $tempDir -Recurse -Force

# Set up Git in the temp directory
Push-Location $tempDir
Write-Host "Initializing Git repository..."
git init
git config --local user.email "deployment@lemma-enterprise.com"
git config --local user.name "Deployment Script"

# Add all files and commit
Write-Host "Adding files to git repository..."
git add .
git commit -m "Deploy OPRF service"

# Set up Heroku remote and push
Write-Host "Deploying to Heroku..."
git remote add heroku "https://git.heroku.com/$oprfAppName.git"
git push heroku master --force

# Check if deployment was successful
if ($LASTEXITCODE -ne 0) {
    Write-Host "Deployment failed. Please check Heroku logs for details:" -ForegroundColor Red
    Write-Host "heroku logs --tail --app $oprfAppName" -ForegroundColor Yellow
    Pop-Location
    Exit 1
}

# Configure environment variables (for extra safety)
Write-Host "Configuring environment variables..."
heroku config:set OPRF_RATE_LIMIT=60 --app $oprfAppName
heroku config:set OPRF_ROTATION_DAYS=30 --app $oprfAppName 
heroku config:set OPRF_DEBUG=false --app $oprfAppName
heroku config:set OPRF_METRICS_ENABLED=true --app $oprfAppName

# Restart the app to apply changes
Write-Host "Restarting app to apply changes..."
heroku ps:restart --app $oprfAppName

# Clean up
Pop-Location
Write-Host "Cleaning up temporary directory..."
Remove-Item -Path $tempDir -Recurse -Force

Write-Host "OPRF Service deployment completed!" -ForegroundColor Green
Write-Host "Your OPRF service is available at: https://$oprfAppName.herokuapp.com" -ForegroundColor Cyan

# Also set the URL in the main app
$mainAppName = "lemma-enterprise"
try {
    Write-Host "Configuring main app to use the OPRF service..."
    heroku config:set OPRF_SERVICE_URL="https://$oprfAppName.herokuapp.com" --app $mainAppName
    Write-Host "Main app successfully configured to use the OPRF service" -ForegroundColor Green
}
catch {
    Write-Host "Could not configure main app. Please run manually:" -ForegroundColor Yellow
    Write-Host "heroku config:set OPRF_SERVICE_URL=https://$oprfAppName.herokuapp.com --app $mainAppName"
}

Write-Host "`nDeployment complete. Please check the OPRF service is running by visiting:"
Write-Host "https://$oprfAppName.herokuapp.com/pubkey" -ForegroundColor Cyan 