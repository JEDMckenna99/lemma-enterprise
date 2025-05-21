#!/bin/bash
# Run script for OPRF Service with environment variable configuration

# Define defaults
DEFAULT_PORT=8080
DEFAULT_KEY_DIR="./keys"
DEFAULT_RATE_LIMIT=60
DEFAULT_ROTATION_DAYS=30
DEFAULT_METRICS_ENABLED=true
DEFAULT_DEBUG=false

# Allow environment variables to override defaults
PORT=${OPRF_PORT:-$DEFAULT_PORT}
KEY_DIR=${OPRF_KEY_DIR:-$DEFAULT_KEY_DIR}
RATE_LIMIT=${OPRF_RATE_LIMIT:-$DEFAULT_RATE_LIMIT}
ROTATION_DAYS=${OPRF_ROTATION_DAYS:-$DEFAULT_ROTATION_DAYS}
METRICS_ENABLED=${OPRF_METRICS_ENABLED:-$DEFAULT_METRICS_ENABLED}
DEBUG=${OPRF_DEBUG:-$DEFAULT_DEBUG}

# Create key directory if it doesn't exist
mkdir -p "$KEY_DIR"

# Convert boolean strings to actual boolean values
if [ "$METRICS_ENABLED" = "false" ] || [ "$METRICS_ENABLED" = "0" ]; then
    METRICS_FLAG="--metrics=false"
else
    METRICS_FLAG="--metrics=true"
fi

if [ "$DEBUG" = "true" ] || [ "$DEBUG" = "1" ]; then
    DEBUG_FLAG="--debug"
else
    DEBUG_FLAG=""
fi

# Display configuration
echo "Starting OPRF Service with configuration:"
echo "  Port:           $PORT"
echo "  Key Directory:  $KEY_DIR"
echo "  Rate Limit:     $RATE_LIMIT req/min"
echo "  Key Rotation:   $ROTATION_DAYS days"
echo "  Metrics:        $METRICS_ENABLED"
echo "  Debug:          $DEBUG"
echo "-------------------------------------"

# Run the service
exec ./oprf-service \
    --port="$PORT" \
    --keydir="$KEY_DIR" \
    --ratelimit="$RATE_LIMIT" \
    --rotationdays="$ROTATION_DAYS" \
    $METRICS_FLAG \
    $DEBUG_FLAG \
    "$@" 