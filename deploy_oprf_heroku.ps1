#!/usr/bin/env pwsh
# Deployment script for Lemma with OPRF service on Heroku

Write-Host "===== Lemma Enterprise with OPRF Service - Heroku Deployment =====" -ForegroundColor Green

# Check for Heroku CLI
if (-not (Get-Command heroku -ErrorAction SilentlyContinue)) {
    Write-Error "Heroku CLI not found. Please install it first: https://devcenter.heroku.com/articles/heroku-cli"
    exit 1
}

# Check login status
try {
    $whoami = heroku auth:whoami
    Write-Host "Logged in to Heroku as: $whoami" -ForegroundColor Cyan
}
catch {
    Write-Host "Please log in to Heroku first" -ForegroundColor Yellow
    heroku login
}

# Prompt for app name
$appName = Read-Host "Enter your Heroku app name (leave blank to use existing git remote)"

if ([string]::IsNullOrWhiteSpace($appName)) {
    # Get the app name from the git remote
    try {
        $remote = git remote -v | Select-String "heroku"
        if ($remote) {
            $appName = $remote -split "/" | Select-Object -Last 1 | ForEach-Object { $_ -replace '\.git.*$', '' }
            Write-Host "Using app name from git remote: $appName" -ForegroundColor Cyan
        }
        else {
            Write-Error "No Heroku remote found. Please specify an app name."
            exit 1
        }
    }
    catch {
        Write-Error "Failed to get app name from git remote. Please specify an app name."
        exit 1
    }
}

# Ensure heroku.yml is properly configured
Write-Host "Checking heroku.yml configuration..." -ForegroundColor Cyan
$herokuYml = Get-Content "heroku.yml" -Raw

if (-not ($herokuYml -match "go")) {
    Write-Error "heroku.yml missing Go buildpack configuration. Please update it first."
    exit 1
}

if (-not ($herokuYml -match "oprf:")) {
    Write-Error "heroku.yml missing OPRF process configuration. Please update it first."
    exit 1
}

# Make sure scripts are executable
Write-Host "Making scripts executable..." -ForegroundColor Cyan
git update-index --chmod=+x bin/compile-oprf.sh
git update-index --chmod=+x bin/heroku-build.sh

# Set required environment variables if not already set
Write-Host "Checking required environment variables..." -ForegroundColor Cyan
$envVars = heroku config --app $appName

if (-not ($envVars -match "OPRF_SERVICE_INTERNAL")) {
    Write-Host "Setting OPRF_SERVICE_INTERNAL=true" -ForegroundColor Yellow
    heroku config:set OPRF_SERVICE_INTERNAL=true --app $appName
}

if (-not ($envVars -match "OPRF_RATE_LIMIT")) {
    Write-Host "Setting OPRF_RATE_LIMIT=60" -ForegroundColor Yellow
    heroku config:set OPRF_RATE_LIMIT=60 --app $appName
}

if (-not ($envVars -match "OPRF_ROTATION_DAYS")) {
    Write-Host "Setting OPRF_ROTATION_DAYS=30" -ForegroundColor Yellow
    heroku config:set OPRF_ROTATION_DAYS=30 --app $appName
}

# Set stack to container
Write-Host "Setting Heroku stack to container..." -ForegroundColor Cyan
heroku stack:set container --app $appName

# Configure dynos for both web and OPRF
Write-Host "Configuring dynos for web and OPRF..." -ForegroundColor Cyan
heroku ps:scale web=1 oprf=1 --app $appName

# Commit changes if needed
$status = git status --porcelain
if ($status) {
    Write-Host "Committing changes..." -ForegroundColor Cyan
    git add .
    git commit -m "Configure for Heroku deployment with OPRF service"
}

# Deploy to Heroku
Write-Host "Deploying to Heroku..." -ForegroundColor Cyan
git push heroku main

# Check if both processes are running
Write-Host "Checking dyno status..." -ForegroundColor Cyan
heroku ps --app $appName

# Test OPRF service
Write-Host "Testing OPRF service..." -ForegroundColor Cyan
try {
    $response = Invoke-RestMethod -Uri "https://$appName.herokuapp.com/api/oprf/status" -Method GET
    Write-Host "OPRF service status: " -NoNewline
    Write-Host "OK" -ForegroundColor Green
    $response | ConvertTo-Json
}
catch {
    Write-Host "OPRF service test failed: $_" -ForegroundColor Red
    Write-Host "You may need to check the logs: heroku logs --tail --app $appName"
}

Write-Host "===== Deployment Complete =====" -ForegroundColor Green
Write-Host "Your app is available at: https://$appName.herokuapp.com"
Write-Host "View logs with: heroku logs --tail --app $appName" 