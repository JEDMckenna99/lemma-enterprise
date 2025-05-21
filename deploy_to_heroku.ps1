# PowerShell script to deploy Lemma Enterprise to Heroku
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

# Prepare the deployment
Write-Host "Preparing deployment..."
python prepare_deployment.py --prod --test-flow-4

# Check if preparation was successful
if ($LASTEXITCODE -ne 0) {
    Write-Error "Deployment preparation failed. Please fix the issues and try again."
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

# Configure Heroku app
Write-Host "Configuring Heroku app..."
heroku config:set FLASK_APP=app.py --app $appName
heroku config:set FLASK_ENV=production --app $appName
heroku config:set PYTHONUNBUFFERED=1 --app $appName
heroku config:set WEB_CONCURRENCY=3 --app $appName

# Set production environment variables from .env.production
if (Test-Path .env.production) {
    Write-Host "Setting environment variables from .env.production..."
    Get-Content .env.production | ForEach-Object {
        if (-not [string]::IsNullOrWhiteSpace($_) -and -not $_.StartsWith('#')) {
            $key, $value = $_ -split '=', 2
            if (-not [string]::IsNullOrWhiteSpace($key)) {
                heroku config:set "$key=$value" --app $appName
            }
        }
    }
}

# Add PostgreSQL add-on
Write-Host "Adding PostgreSQL add-on..."
heroku addons:create heroku-postgresql:hobby-dev --app $appName

# Add Redis add-on
Write-Host "Adding Redis add-on..."
heroku addons:create heroku-redis:hobby-dev --app $appName

# Deploy to Heroku
Write-Host "Deploying to Heroku..."
git add .
git commit -m "Deploy to Heroku"
git push heroku main

Write-Host "Deployment completed successfully!"
Write-Host "Your app is available at: https://$appName.herokuapp.com" 