#!/usr/bin/env pwsh
# PowerShell script to test the OPRF service on Heroku

Write-Host "===== Testing OPRF Service on Heroku =====" -ForegroundColor Cyan

# Get the Heroku app name
if ($args.Count -gt 0) {
    $herokuApp = $args[0]
    Write-Host "Using provided Heroku app: $herokuApp" -ForegroundColor Cyan
}
else {
    Write-Host "No Heroku app name provided" -ForegroundColor Yellow
    
    # Try to get app name from git remote
    try {
        $remote = git remote -v | Select-String "heroku"
        if ($remote) {
            $herokuApp = $remote -split "/" | Select-Object -Last 1 | ForEach-Object { $_ -replace '\.git.*$', '' }
            Write-Host "Using app name from git remote: $herokuApp" -ForegroundColor Cyan
        }
        else {
            Write-Host "No Heroku remote found." -ForegroundColor Yellow
            $herokuApp = Read-Host "Enter your Heroku app name"
        }
    }
    catch {
        Write-Host "Error getting Heroku remote" -ForegroundColor Red
        $herokuApp = Read-Host "Enter your Heroku app name"
    }
}

# Check if the app exists
try {
    $appInfo = heroku apps:info --app $herokuApp
    if (-not $appInfo) {
        Write-Error "Heroku app $herokuApp not found."
        exit 1
    }
}
catch {
    Write-Error "Heroku app $herokuApp not found or error connecting to Heroku."
    exit 1
}

Write-Host "Checking if app is running..." -ForegroundColor Yellow
$dynos = heroku ps --app $herokuApp

# Check if web dyno is running
if (-not ($dynos -match "web.*up")) {
    Write-Host "Warning: Web dyno may not be running." -ForegroundColor Yellow
    Write-Host "Starting web dyno..." -ForegroundColor Yellow
    heroku ps:scale web=1 --app $herokuApp
}

# Check if OPRF dyno is running
if (-not ($dynos -match "oprf.*up")) {
    Write-Host "Warning: OPRF dyno may not be running." -ForegroundColor Yellow
    Write-Host "Starting OPRF dyno..." -ForegroundColor Yellow
    heroku ps:scale oprf=1 --app $herokuApp
}

Write-Host "Running OPRF integration test..." -ForegroundColor Cyan
python test_oprf_service.py "https://$herokuApp.herokuapp.com"

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n===== OPRF Service Test Completed Successfully =====" -ForegroundColor Green
}
else {
    Write-Host "`n===== OPRF Service Test Failed =====" -ForegroundColor Red
    Write-Host "`nDisplaying last 50 log entries to help diagnose issues:" -ForegroundColor Yellow
    heroku logs -n 50 --app $herokuApp
}

Write-Host "`nDone." -ForegroundColor Cyan 