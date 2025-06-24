#!/bin/bash

# Lemma CloudFlare Security Level Fix
# Fixes the 403 "Just a moment..." errors by adjusting security settings

set -e

echo "🔧 Lemma CloudFlare Security Fix"
echo "================================="

# Configuration
ZONE_ID="c4e8c3580c49fa6351a5d6c02bc79b4d"

# Check authentication method
if [ -n "$CLOUDFLARE_API_TOKEN" ]; then
    AUTH_METHOD="token"
    echo "📡 Using Custom API Token authentication"
elif [ -n "$CLOUDFLARE_EMAIL" ] && [ -n "$CLOUDFLARE_API_KEY" ]; then
    AUTH_METHOD="key"
    echo "📧 Using Global API Key authentication"
    echo "📧 Email: $CLOUDFLARE_EMAIL"
else
    echo "❌ Error: No valid authentication found"
    echo ""
    echo "Option 1 - Custom API Token (Recommended):"
    echo "  export CLOUDFLARE_API_TOKEN=your-custom-token"
    echo ""
    echo "Option 2 - Global API Key:"
    echo "  export CLOUDFLARE_EMAIL=jedmckenna@lemma.id"
    echo "  export CLOUDFLARE_API_KEY=your-global-api-key"
    exit 1
fi

echo "🆔 Zone ID: $ZONE_ID"
echo ""

# API endpoint
API_URL="https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/settings/security_level"

echo "📡 Making API call to update security level..."

# Make the API call based on authentication method
if [ "$AUTH_METHOD" = "token" ]; then
    response=$(curl -s -X PATCH "$API_URL" \
      -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
      -H "Content-Type: application/json" \
      --data '{"value": "medium"}')
else
    response=$(curl -s -X PATCH "$API_URL" \
      -H "X-Auth-Email: $CLOUDFLARE_EMAIL" \
      -H "X-Auth-Key: $CLOUDFLARE_API_KEY" \
      -H "Content-Type: application/json" \
      --data '{"value": "medium"}')
fi

echo "📋 API Response:"
echo "$response" | python3 -m json.tool 2>/dev/null || echo "$response"
echo ""

# Check if successful
if echo "$response" | grep -q '"success":true'; then
    echo "✅ SUCCESS: CloudFlare security level updated to MEDIUM"
    echo "🚀 Your lemma.id site should now work properly!"
    echo ""
    echo "🔍 Test your site:"
    echo "   curl -I https://lemma.id/api/health"
    echo ""
    
    # Test immediately
    echo "🧪 Testing API health..."
    if curl -s -I https://lemma.id/api/health | head -1 | grep -q "200 OK"; then
        echo "✅ API is working!"
    else
        echo "⚠️  API may need a few minutes to propagate"
    fi
    
else
    echo "❌ FAILED: Could not update CloudFlare settings"
    if echo "$response" | grep -q "403"; then
        echo "⚠️  This might be a token permissions issue"
        echo "   Make sure your token has 'Zone Settings:Edit' permission"
    fi
    echo "Please check your API credentials and try again"
    exit 1
fi

echo "🎉 CloudFlare security fix completed!" 