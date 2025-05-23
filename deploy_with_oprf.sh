#!/bin/bash
set -e

echo "🚀 Deploying Lemma Enterprise with OPRF Cascade Revocation Layer"
echo "================================================================"

# Check if Heroku CLI is installed
if ! command -v heroku &> /dev/null; then
    echo "❌ Heroku CLI is not installed. Please install it first."
    echo "   Visit: https://devcenter.heroku.com/articles/heroku-cli"
    exit 1
fi

# Check if user is logged in to Heroku
if ! heroku auth:whoami &> /dev/null; then
    echo "❌ Not logged in to Heroku. Please run 'heroku login' first."
    exit 1
fi

# Get app name from user or use default
read -p "Enter your Heroku app name (or press Enter for auto-generated): " APP_NAME

if [ -z "$APP_NAME" ]; then
    echo "📝 Creating new Heroku app with auto-generated name..."
    APP_NAME=$(heroku create --json | jq -r '.name')
    echo "✅ Created app: $APP_NAME"
else
    echo "📝 Using existing app: $APP_NAME"
fi

echo ""
echo "🔧 Configuring environment variables..."

# Set required environment variables
heroku config:set \
    LEMMA_ADMIN_USER=admin \
    LEMMA_ADMIN_PASS=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25) \
    LEMMA_SECRET_KEY=$(openssl rand -base64 32) \
    LEMMA_API_KEY=$(openssl rand -base64 32) \
    DID=did:web:$APP_NAME.herokuapp.com \
    DID_METHOD=web \
    --app $APP_NAME

# Enable OPRF service
echo "🔐 Enabling OPRF cascade revocation layer..."
heroku config:set \
    OPRF_SERVICE_INTERNAL=true \
    OPRF_RATE_LIMIT=60 \
    OPRF_ROTATION_DAYS=30 \
    OPRF_DEBUG=false \
    --app $APP_NAME

# Set Stripe test keys (keeping them as test for development)
echo "💳 Configuring Stripe (test mode)..."
heroku config:set \
    STRIPE_PUBLISHABLE_KEY=pk_test_51234567890 \
    STRIPE_SECRET_KEY=sk_test_51234567890 \
    --app $APP_NAME

echo ""
echo "📦 Deploying application..."

# Deploy the application
git push heroku main

echo ""
echo "⚖️ Scaling processes..."

# Scale both web and OPRF processes
heroku ps:scale web=1 oprf=1 --app $APP_NAME

echo ""
echo "🔍 Checking deployment status..."

# Wait a moment for processes to start
sleep 10

# Check process status
echo "Process status:"
heroku ps --app $APP_NAME

echo ""
echo "📊 Testing OPRF integration..."

# Test the OPRF status endpoint
APP_URL="https://$APP_NAME.herokuapp.com"
echo "Testing: $APP_URL/api/oprf/status"

# Use curl to test the endpoint
if curl -s "$APP_URL/api/oprf/status" | grep -q "ok"; then
    echo "✅ OPRF integration test passed!"
else
    echo "⚠️  OPRF integration test failed - check logs"
fi

echo ""
echo "📋 Deployment Summary"
echo "===================="
echo "App Name: $APP_NAME"
echo "App URL: $APP_URL"
echo "Admin URL: $APP_URL/admin/login"
echo ""
echo "🔐 Admin Credentials:"
echo "Username: admin"
echo "Password: $(heroku config:get LEMMA_ADMIN_PASS --app $APP_NAME)"
echo ""
echo "🔧 Useful Commands:"
echo "View logs: heroku logs --tail --app $APP_NAME"
echo "View OPRF logs: heroku logs --tail --dyno=oprf --app $APP_NAME"
echo "Check processes: heroku ps --app $APP_NAME"
echo "Test OPRF: curl $APP_URL/api/oprf/status"
echo ""
echo "🎉 Deployment completed successfully!"
echo "Your OPRF cascade revocation layer is now operational on Heroku." 