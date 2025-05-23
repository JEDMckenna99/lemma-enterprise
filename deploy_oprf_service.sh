#!/bin/bash
set -e

# This script deploys the OPRF service as a separate Heroku app

# Configuration
OPRF_APP_NAME="lemma-oprf-service"
MAIN_APP_NAME="lemma-enterprise"

# Check if the OPRF app already exists
if heroku apps:info $OPRF_APP_NAME &> /dev/null; then
  echo "OPRF app $OPRF_APP_NAME already exists"
else
  echo "Creating OPRF app $OPRF_APP_NAME..."
  heroku apps:create $OPRF_APP_NAME
fi

# Set the stack to heroku-22
heroku stack:set heroku-22 --app $OPRF_APP_NAME

# Add the Go buildpack
heroku buildpacks:set heroku/go --app $OPRF_APP_NAME

# Create a temporary directory for the OPRF service
echo "Creating temporary directory for OPRF service..."
mkdir -p oprf-deploy-temp
cd oprf-deploy-temp

# Initialize git repository
git init

# Copy OPRF service files
echo "Copying OPRF service files..."
cp -r ../oprfservice/* .

# Create a Procfile
echo "web: ./oprfservice --port=\$PORT --keydir=./keys" > Procfile

# Create a go.mod file if it doesn't exist
if [ ! -f go.mod ]; then
  echo "module github.com/lemma/oprf-service" > go.mod
  echo "" >> go.mod
  echo "go 1.18" >> go.mod
fi

# Create the keys directory
mkdir -p keys

# Add all files to git
git add .
git commit -m "Deploy OPRF service"

# Push to Heroku
echo "Pushing to Heroku..."
git push https://git.heroku.com/$OPRF_APP_NAME.git HEAD:main -f

# Scale the app
echo "Scaling the app..."
heroku ps:scale web=1 --app $OPRF_APP_NAME

# Configure the main app to use the OPRF service
echo "Configuring main app to use OPRF service..."
heroku config:set OPRF_SERVICE_INTERNAL=https://$OPRF_APP_NAME.herokuapp.com --app $MAIN_APP_NAME

echo "OPRF service deployed successfully!"
echo "OPRF service URL: https://$OPRF_APP_NAME.herokuapp.com"