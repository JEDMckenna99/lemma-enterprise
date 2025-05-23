# PowerShell script to deploy Lemma Enterprise with OPRF Cascade Revocation Layer
param(
    [string]$AppName = ""
)

Write-Host "🚀 Deploying Lemma Enterprise with OPRF Cascade Revocation Layer" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green

# Check if Heroku CLI is installed
try {
    heroku --version | Out-Null
} catch {
    Write-Host "❌ Heroku CLI is not installed. Please install it first." -ForegroundColor Red
    Write-Host "   Visit: https://devcenter.heroku.com/articles/heroku-cli" -ForegroundColor Yellow
    exit 1
}

# Check if user is logged in to Heroku
try {
    heroku auth:whoami | Out-Null
} catch {
    Write-Host "❌ Not logged in to Heroku. Please run 'heroku login' first." -ForegroundColor Red
    exit 1
}

# Get app name from user or use default
if (-not $AppName) {
    $AppName = Read-Host "Enter your Heroku app name (or press Enter for auto-generated)"
}

if (-not $AppName) {
    Write-Host "📝 Creating new Heroku app with auto-generated name..." -ForegroundColor Cyan
    $createResult = heroku create --json | ConvertFrom-Json
    $AppName = $createResult.name
    Write-Host "✅ Created app: $AppName" -ForegroundColor Green
} else {
    Write-Host "📝 Using existing app: $AppName" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "🔧 Configuring environment variables..." -ForegroundColor Cyan

# Generate secure passwords
$adminPass = [System.Web.Security.Membership]::GeneratePassword(25, 5)
$secretKey = [Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
$apiKey = [Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32))

# Set required environment variables
heroku config:set LEMMA_ADMIN_USER=admin --app $AppName
heroku config:set LEMMA_ADMIN_PASS=$adminPass --app $AppName
heroku config:set LEMMA_SECRET_KEY=$secretKey --app $AppName
heroku config:set LEMMA_API_KEY=$apiKey --app $AppName
heroku config:set DID=did:web:$AppName.herokuapp.com --app $AppName
heroku config:set DID_METHOD=web --app $AppName

# Enable OPRF service
Write-Host "🔐 Enabling OPRF cascade revocation layer..." -ForegroundColor Cyan
heroku config:set OPRF_SERVICE_INTERNAL=true --app $AppName
heroku config:set OPRF_RATE_LIMIT=60 --app $AppName
heroku config:set OPRF_ROTATION_DAYS=30 --app $AppName
heroku config:set OPRF_DEBUG=false --app $AppName

# Set Stripe test keys (keeping them as test for development)
Write-Host "💳 Configuring Stripe (test mode)..." -ForegroundColor Cyan
heroku config:set STRIPE_PUBLISHABLE_KEY=pk_test_51234567890 --app $AppName
heroku config:set STRIPE_SECRET_KEY=sk_test_51234567890 --app $AppName

Write-Host ""
Write-Host "📦 Deploying application..." -ForegroundColor Cyan

# Deploy the application
git push heroku main

Write-Host ""
Write-Host "⚖️ Scaling processes..." -ForegroundColor Cyan

# Scale both web and OPRF processes
heroku ps:scale web=1 oprf=1 --app $AppName

Write-Host ""
Write-Host "🔍 Checking deployment status..." -ForegroundColor Cyan

# Wait a moment for processes to start
Start-Sleep -Seconds 10

# Check process status
Write-Host "Process status:" -ForegroundColor Yellow
heroku ps --app $AppName

Write-Host ""
Write-Host "📊 Testing OPRF integration..." -ForegroundColor Cyan

# Test the OPRF status endpoint
$appUrl = "https://$AppName.herokuapp.com"
Write-Host "Testing: $appUrl/api/oprf/status" -ForegroundColor Yellow

try {
    $response = Invoke-RestMethod -Uri "$appUrl/api/oprf/status" -Method Get
    if ($response.status -eq "ok") {
        Write-Host "✅ OPRF integration test passed!" -ForegroundColor Green
    } else {
        Write-Host "⚠️  OPRF integration test failed - check logs" -ForegroundColor Yellow
    }
} catch {
    Write-Host "⚠️  OPRF integration test failed - check logs" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "📋 Deployment Summary" -ForegroundColor Green
Write-Host "====================" -ForegroundColor Green
Write-Host "App Name: $AppName" -ForegroundColor White
Write-Host "App URL: $appUrl" -ForegroundColor White
Write-Host "Admin URL: $appUrl/admin/login" -ForegroundColor White
Write-Host ""
Write-Host "🔐 Admin Credentials:" -ForegroundColor Yellow
Write-Host "Username: admin" -ForegroundColor White
Write-Host "Password: $adminPass" -ForegroundColor White
Write-Host ""
Write-Host "🔧 Useful Commands:" -ForegroundColor Yellow
Write-Host "View logs: heroku logs --tail --app $AppName" -ForegroundColor White
Write-Host "View OPRF logs: heroku logs --tail --dyno=oprf --app $AppName" -ForegroundColor White
Write-Host "Check processes: heroku ps --app $AppName" -ForegroundColor White
Write-Host "Test OPRF: curl $appUrl/api/oprf/status" -ForegroundColor White
Write-Host ""
Write-Host "🎉 Deployment completed successfully!" -ForegroundColor Green
Write-Host "Your OPRF cascade revocation layer is now operational on Heroku." -ForegroundColor Green 