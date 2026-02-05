# Lemma.id Demo Sites Deployment Script
# Run from the demo-sites folder

param(
    [string]$Site1Name = "lemma-demo-news",
    [string]$Site2Name = "lemma-demo-shop",
    [string]$Site3Name = "lemma-demo-bank"
)

$ErrorActionPreference = "Stop"

Write-Host "=== Lemma.id Demo Sites Deployment ===" -ForegroundColor Cyan
Write-Host ""

# Step 1: Create Heroku apps
Write-Host "Step 1: Creating Heroku apps..." -ForegroundColor Yellow

$apps = @(
    @{ Name = $Site1Name; Folder = "site1-news" },
    @{ Name = $Site2Name; Folder = "site2-shop" },
    @{ Name = $Site3Name; Folder = "site3-bank" }
)

foreach ($app in $apps) {
    Write-Host "  Creating $($app.Name)..." -ForegroundColor Gray
    heroku create $app.Name 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "    (App may already exist, continuing...)" -ForegroundColor DarkYellow
    }
}

# Get the URLs
$Site1Url = "https://$Site1Name.herokuapp.com"
$Site2Url = "https://$Site2Name.herokuapp.com"
$Site3Url = "https://$Site3Name.herokuapp.com"

Write-Host ""
Write-Host "Step 2: Setting environment variables..." -ForegroundColor Yellow

foreach ($app in $apps) {
    Write-Host "  Configuring $($app.Name)..." -ForegroundColor Gray
    heroku config:set `
        SITE1_URL=$Site1Url `
        SITE2_URL=$Site2Url `
        SITE3_URL=$Site3Url `
        --app $app.Name
}

Write-Host ""
Write-Host "Step 3: Deploying each site..." -ForegroundColor Yellow

foreach ($app in $apps) {
    Write-Host "  Deploying $($app.Folder) to $($app.Name)..." -ForegroundColor Gray
    
    Push-Location $app.Folder
    
    # Initialize git if needed
    if (-not (Test-Path ".git")) {
        git init
        git add .
        git commit -m "Initial commit"
    }
    
    # Add heroku remote
    heroku git:remote -a $app.Name 2>$null
    
    # Deploy
    git push heroku main --force
    
    Pop-Location
}

Write-Host ""
Write-Host "=== Deployment Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Demo sites are available at:" -ForegroundColor Cyan
Write-Host "  TechPulse (News):  $Site1Url" -ForegroundColor White
Write-Host "  ShopFlow (Shop):   $Site2Url" -ForegroundColor White
Write-Host "  SecureBank (Bank): $Site3Url" -ForegroundColor White
Write-Host ""
Write-Host "IMPORTANT: Register these domains with Lemma.id at https://lemma.id/developer" -ForegroundColor Yellow
