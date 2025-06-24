# Lemma CloudFlare Security Level Fix
# Fixes the 403 "Just a moment..." errors by adjusting security settings

Write-Host "🔧 Lemma CloudFlare Security Fix" -ForegroundColor Green
Write-Host "=================================" -ForegroundColor Green

# Configuration
$ZONE_ID = "c4e8c3580c49fa6351a5d6c02bc79b4d"

# Get environment variables
$CF_API_TOKEN = $env:CLOUDFLARE_API_TOKEN
$CF_EMAIL = $env:CLOUDFLARE_EMAIL
$CF_API_KEY = $env:CLOUDFLARE_API_KEY

# Check authentication method
if ($CF_API_TOKEN) {
    $AUTH_METHOD = "token"
    Write-Host "📡 Using Custom API Token authentication" -ForegroundColor Cyan
} elseif ($CF_EMAIL -and $CF_API_KEY) {
    $AUTH_METHOD = "key"
    Write-Host "📧 Using Global API Key authentication" -ForegroundColor Cyan
    Write-Host "📧 Email: $CF_EMAIL" -ForegroundColor Cyan
} else {
    Write-Host "❌ Error: No valid authentication found" -ForegroundColor Red
    Write-Host ""
    Write-Host "Option 1 - Custom API Token (Recommended):" -ForegroundColor Yellow
    Write-Host "  `$env:CLOUDFLARE_API_TOKEN='your-custom-token'" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Option 2 - Global API Key:" -ForegroundColor Yellow
    Write-Host "  `$env:CLOUDFLARE_EMAIL='jedmckenna@lemma.id'" -ForegroundColor Gray
    Write-Host "  `$env:CLOUDFLARE_API_KEY='your-global-api-key'" -ForegroundColor Gray
    exit 1
}

Write-Host "🆔 Zone ID: $ZONE_ID" -ForegroundColor Cyan
Write-Host ""

# API endpoint
$API_URL = "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/settings/security_level"

Write-Host "📡 Making API call to update security level..." -ForegroundColor Yellow

# Prepare headers based on authentication method
if ($AUTH_METHOD -eq "token") {
    $headers = @{
        "Authorization" = "Bearer $CF_API_TOKEN"
        "Content-Type" = "application/json"
    }
} else {
    $headers = @{
        "X-Auth-Email" = $CF_EMAIL
        "X-Auth-Key" = $CF_API_KEY
        "Content-Type" = "application/json"
    }
}

# Prepare body
$body = @{
    value = "medium"
} | ConvertTo-Json

try {
    # Make the API call
    $response = Invoke-RestMethod -Uri $API_URL -Method PATCH -Headers $headers -Body $body
    
    Write-Host "📋 API Response:" -ForegroundColor Cyan
    $response | ConvertTo-Json -Depth 10
    Write-Host ""
    
    if ($response.success) {
        Write-Host "✅ SUCCESS: CloudFlare security level updated to MEDIUM" -ForegroundColor Green
        Write-Host "🚀 Your lemma.id site should now work properly!" -ForegroundColor Green
        Write-Host ""
        Write-Host "🔍 Test your site:" -ForegroundColor Cyan
        Write-Host "   curl -I https://lemma.id/api/health" -ForegroundColor Gray
        Write-Host ""
        
        # Test immediately
        Write-Host "🧪 Testing API health..." -ForegroundColor Yellow
        try {
            $testResponse = Invoke-RestMethod -Uri "https://lemma.id/api/health" -Method GET -TimeoutSec 10
            Write-Host "✅ API is working! Service: $($testResponse.service)" -ForegroundColor Green
        } catch {
            Write-Host "⚠️  API may need a few minutes to propagate" -ForegroundColor Yellow
        }
        
    } else {
        Write-Host "❌ FAILED: Could not update CloudFlare settings" -ForegroundColor Red
        if ($response.errors) {
            foreach ($error in $response.errors) {
                Write-Host "Error: $($error.message)" -ForegroundColor Red
            }
        }
        exit 1
    }
    
} catch {
    Write-Host "❌ ERROR: API call failed" -ForegroundColor Red
    Write-Host "Details: $($_.Exception.Message)" -ForegroundColor Red
    
    if ($_.Exception.Message -match "403") {
        Write-Host "⚠️  This might be a token permissions issue" -ForegroundColor Yellow
        Write-Host "   Make sure your token has 'Zone Settings:Edit' permission" -ForegroundColor Yellow
    }
    
    exit 1
}

Write-Host "🎉 CloudFlare security fix completed!" -ForegroundColor Green 