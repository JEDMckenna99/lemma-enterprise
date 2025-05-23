#!/bin/bash
set -e

echo "=== Starting Heroku build process ==="

# Make scripts executable
chmod +x bin/*.sh

# Compile OPRF service
echo "=== Compiling OPRF service ==="
./bin/compile-oprf.sh

# Ensure directories exist
mkdir -p instance/data/keys
mkdir -p instance/data/revocation/cascades

echo "=== Build completed successfully ===" 