#!/bin/bash
# Script to deploy Lemma Enterprise with OPRF service to Heroku
# Run this script from the project root directory

# Check if Heroku CLI is installed
if ! command -v heroku &> /dev/null; then
    echo "Heroku CLI is not installed. Please install it first."
    exit 1
fi

# Check if user is logged in
if ! heroku auth:whoami &> /dev/null; then
    echo "You are not logged in to Heroku. Please run 'heroku login' first."
    exit 1
fi

# Prompt for Heroku app name
read -p "Enter your Heroku app name (leave blank to create a new app): " APP_NAME

if [ -z "$APP_NAME" ]; then
    # Create a new Heroku app
    echo "Creating a new Heroku app..."
    APP_NAME=$(heroku create | grep -o 'https://[^ ]*\.herokuapp\.com' | sed 's/https:\/\///' | sed 's/\.herokuapp\.com//')
    echo "Created new Heroku app: $APP_NAME"
else
    # Check if the app exists
    if ! heroku apps:info --app "$APP_NAME" &> /dev/null; then
        echo "App '$APP_NAME' does not exist. Please check the name or leave blank to create a new app."
        exit 1
    fi
    echo "Using existing Heroku app: $APP_NAME"
fi

# Set up Heroku for container deployment
echo "Setting up Heroku for container deployment..."
heroku stack:set container --app "$APP_NAME"

# Configure environment variables
echo "Configuring environment variables..."
heroku config:set FLASK_APP=app.py --app "$APP_NAME"
heroku config:set FLASK_ENV=production --app "$APP_NAME"
heroku config:set PYTHONUNBUFFERED=1 --app "$APP_NAME"
heroku config:set WEB_CONCURRENCY=3 --app "$APP_NAME"

# OPRF service configuration
heroku config:set OPRF_RATE_LIMIT=60 --app "$APP_NAME"
heroku config:set OPRF_ROTATION_DAYS=30 --app "$APP_NAME"
heroku config:set OPRF_DEBUG=false --app "$APP_NAME"
heroku config:set OPRF_METRICS=true --app "$APP_NAME"
heroku config:set OPRF_KEY_DIR="./instance/data/keys" --app "$APP_NAME"
heroku config:set OPRF_SERVICE_INTERNAL=true --app "$APP_NAME"

# Lemma configuration
echo "Configuring Lemma Enterprise..."

# Generate a secure random key for Flask
FLASK_SECRET_KEY=$(openssl rand -hex 24)
heroku config:set LEMMA_SECRET_KEY="$FLASK_SECRET_KEY" --app "$APP_NAME"

# Set up admin credentials (prompt for security)
read -p "Enter admin username for Lemma (default: admin): " ADMIN_USER
ADMIN_USER=${ADMIN_USER:-admin}

read -s -p "Enter admin password for Lemma: " ADMIN_PASS
echo ""
if [ -z "$ADMIN_PASS" ]; then
    ADMIN_PASS=$(openssl rand -hex 8)
    echo "Generated random admin password: $ADMIN_PASS"
fi

heroku config:set LEMMA_ADMIN_USER="$ADMIN_USER" --app "$APP_NAME"
heroku config:set LEMMA_ADMIN_PASS="$ADMIN_PASS" --app "$APP_NAME"

# Generate API key
API_KEY=$(openssl rand -hex 16)
heroku config:set LEMMA_API_KEY="$API_KEY" --app "$APP_NAME"

# Set DID configuration
heroku config:set DID="did:lemma:heroku:$APP_NAME" --app "$APP_NAME"
heroku config:set DID_METHOD="key" --app "$APP_NAME"
heroku config:set LEMMA_ENABLE_P2P=true --app "$APP_NAME"

# Configure PostgreSQL
echo "Adding PostgreSQL add-on..."
heroku addons:create heroku-postgresql:hobby-dev --app "$APP_NAME"

# Configure dyno formation
echo "Configuring dyno formation..."
heroku ps:scale web=1 oprf=1 --app "$APP_NAME"

# Deploy to Heroku
echo "Deploying to Heroku..."
git push https://git.heroku.com/$APP_NAME.git HEAD:main

echo "Deployment completed!"
echo "Your Lemma Enterprise app is available at: https://$APP_NAME.herokuapp.com"
echo ""
echo "Admin credentials:"
echo "Username: $ADMIN_USER"
echo "Password: $ADMIN_PASS"
echo ""
echo "API Key: $API_KEY"
echo ""
echo "IMPORTANT: Save these credentials securely. They will not be shown again."