# PowerShell script to deploy Lemma Enterprise with OPRF service to Heroku
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

# Prompt for Heroku app name
$appName = Read-Host "Enter your Heroku app name (leave blank to create a new app)"

if ([string]::IsNullOrWhiteSpace($appName)) {
    # Create a new Heroku app
    Write-Host "Creating a new Heroku app..."
    $result = heroku create
    
    # Extract app name from the output
    $appName = $result -split ' ' | Select-Object -Last 2 | Select-Object -First 1
    Write-Host "Created new Heroku app: $appName"
}
else {
    # Check if the app exists
    try {
        heroku apps:info --app $appName | Out-Null
        Write-Host "Using existing Heroku app: $appName"
    }
    catch {
        Write-Error "App '$appName' does not exist. Please check the name or leave blank to create a new app."
        Exit 1
    }
}

# Configure buildpacks (Python for main app, Go for OPRF service)
Write-Host "Setting up buildpacks..."
heroku buildpacks:clear --app $appName
heroku buildpacks:add heroku/python --app $appName
heroku buildpacks:add heroku/go --app $appName

# Configure Heroku app
Write-Host "Configuring Heroku app..."
heroku config:set FLASK_APP=app.py --app $appName
heroku config:set FLASK_ENV=production --app $appName
heroku config:set PYTHONUNBUFFERED=1 --app $appName
heroku config:set WEB_CONCURRENCY=3 --app $appName
heroku config:set OPRF_RATE_LIMIT=60 --app $appName
heroku config:set OPRF_ROTATION_DAYS=30 --app $appName
heroku config:set OPRF_DEBUG=false --app $appName

# Ensure Go module files are properly set up
Write-Host "Checking Go module configuration..."
if (-not (Test-Path "go.mod")) {
    # Create a go.mod file at the root to satisfy Heroku's Go buildpack
    Write-Host "Creating go.mod file at root..."
    @"
module lemma-enterprise

go 1.18

require (
	github.com/gorilla/mux v1.8.0
)
"@ | Out-File -FilePath "go.mod" -Encoding UTF8
}

# Configure Heroku Dynos
Write-Host "Configuring Heroku dynos..."
heroku ps:scale web=1 oprf=1 --app $appName

# Add PostgreSQL add-on if needed
Write-Host "Adding PostgreSQL add-on..."
heroku addons:create heroku-postgresql:hobby-dev --app $appName

# Deploy to Heroku
Write-Host "Deploying to Heroku..."
git add .
git commit -m "Deploy Lemma with OPRF service to Heroku"
git push heroku main

Write-Host "Deployment completed!"
Write-Host "Your app is available at: https://$appName.herokuapp.com"
Write-Host "OPRF service will be running inside the same Heroku app" 