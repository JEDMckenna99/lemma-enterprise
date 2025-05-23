# This script deploys a simplified OPRF service as a separate Heroku app

# Configuration
$OPRF_APP_NAME = "lemma-oprf-service"
$MAIN_APP_NAME = "lemma-enterprise"

# Create a temporary directory for the OPRF service
Write-Host "Creating temporary directory for OPRF service..."
$tempDir = "simple-oprf-temp"
if (Test-Path $tempDir) {
    Remove-Item -Recurse -Force $tempDir
}
New-Item -ItemType Directory -Path $tempDir | Out-Null
Set-Location $tempDir

# Initialize git repository
git init

# Copy the simple OPRF service file
Write-Host "Setting up simple OPRF service..."
Copy-Item -Path ..\simple_oprf_service.go -Destination main.go

# Create a Procfile
"web: ./bin/app" | Out-File -FilePath "Procfile" -Encoding ascii

# Create a go.mod file
@"
module github.com/lemma/simple-oprf-service

go 1.18
"@ | Out-File -FilePath "go.mod" -Encoding utf8

# Create a heroku.yml file
@"
build:
  languages:
    - go
"@ | Out-File -FilePath "heroku.yml" -Encoding utf8

# Add all files to git
git add .
git commit -m "Deploy simple OPRF service"

# Create the OPRF app if it doesn't exist
try {
    heroku apps:info $OPRF_APP_NAME | Out-Null
    Write-Host "OPRF app $OPRF_APP_NAME already exists"
} catch {
    Write-Host "Creating OPRF app $OPRF_APP_NAME..."
    heroku apps:create $OPRF_APP_NAME
}

# Set the stack to heroku-22
heroku stack:set heroku-22 --app $OPRF_APP_NAME

# Add the Go buildpack
heroku buildpacks:set heroku/go --app $OPRF_APP_NAME

# Push to Heroku
Write-Host "Pushing to Heroku..."
git push https://git.heroku.com/$OPRF_APP_NAME.git HEAD:main -f

# Scale the app
Write-Host "Scaling the app..."
heroku ps:scale web=1 --app $OPRF_APP_NAME

# Configure the main app to use the OPRF service
Write-Host "Configuring main app to use OPRF service..."
heroku config:set OPRF_SERVICE_INTERNAL=https://$OPRF_APP_NAME.herokuapp.com --app $MAIN_APP_NAME

Write-Host "OPRF service deployed successfully!"
Write-Host "OPRF service URL: https://$OPRF_APP_NAME.herokuapp.com"

# Return to the original directory
Set-Location ..