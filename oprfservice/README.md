# OPRF Service for Lemma Human Verification System

This microservice provides an endpoint for evaluating Oblivious Pseudorandom Functions (OPRFs) according to RFC 9497 using the ristretto255 elliptic curve. The service is a core component of the Lemma privacy-preserving revocation system.

## Overview

The OPRF service maintains private keys securely and evaluates blinded inputs without learning the original values, providing privacy-preserving revocation checks for the Lemma ecosystem. It is designed to be secure, scalable, and production-ready with:

- **Rate limiting**: Configurable per-IP rate limiting to prevent abuse
- **Metrics**: Prometheus-compatible metrics for monitoring
- **Key rotation**: Automatic key rotation for enhanced security
- **High performance**: Optimized for high throughput and low latency

## Features

- OPRF evaluation using the ristretto255 curve (RFC 9497)
- Automated key management and rotation
- Multiple key support for graceful transitions
- Prometheus metrics for monitoring
- Client-side blinding/unblinding for privacy
- Configurable rate limiting
- Proper error handling and logging

## Getting Started

### Prerequisites

- Go 1.18 or later
- Git

### Building

```bash
git clone [repository URL]
cd oprfservice
go build -o oprf-service
```

### Running

```bash
# Basic usage
./oprf-service

# With custom port
./oprf-service --port 9090

# With custom key file
./oprf-service --keyfile /path/to/my/key.hex

# With custom key directory (for rotation)
./oprf-service --keydir /path/to/keys

# Generate a new key and exit
./oprf-service --generate

# Enable debug mode
./oprf-service --debug

# Configure rate limiting (requests per minute, 0 to disable)
./oprf-service --ratelimit 60

# Configure key rotation (days, 0 to disable)
./oprf-service --rotationdays 30

# Disable metrics
./oprf-service --metrics=false
```

### Docker Support

A Dockerfile is included for easy containerization:

```bash
# Build the Docker image
docker build -t lemma/oprf-service .

# Run the container
docker run -p 8080:8080 lemma/oprf-service

# With volume mounted keys
docker run -p 8080:8080 -v /path/to/keys:/keys lemma/oprf-service --keydir /keys
```

## API Reference

### Endpoints

#### POST `/oprfeval`

Evaluates blinded inputs using the OPRF protocol.

**Request:**

```json
{
  "alpha": ["base64_blinded_element1", "base64_blinded_element2"],
  "key_id": "optional_key_id_for_specific_key"
}
```

**Response:**

```json
{
  "beta": ["base64_evaluated_element1", "base64_evaluated_element2"],
  "epoch": "2023-09-01",
  "publicKey": "hex_encoded_public_key",
  "key_id": "id_of_key_used"
}
```

#### GET `/pubkey`

Retrieves the public key for verification.

**Query Parameters:**
- `key_id` (optional): Specific key ID to retrieve

**Response:**

```json
{
  "publicKey": "hex_encoded_public_key",
  "epoch": "2023-09-01",
  "algorithm": "ristretto255",
  "key_id": "id_of_key"
}
```

#### GET `/keys`

Lists all available keys and their metadata.

**Response:**

```json
{
  "keys": [
    {
      "key_id": "abcdef1234567890",
      "created_at": "2023-09-01T12:00:00Z",
      "expires_at": "2023-10-01T12:00:00Z",
      "is_active": true,
      "description": "OPRF key generated on 2023-09-01"
    }
  ],
  "active_key": "abcdef1234567890",
  "total_keys": 1,
  "epoch": "2023-09-01"
}
```

#### GET `/health`

Health check endpoint.

**Response:**

```json
{
  "status": "ok",
  "service": "lemma-oprf-service",
  "version": "1.0.0",
  "timestamp": 1630000000,
  "epoch": "2023-09-01"
}
```

#### GET `/metrics`

Prometheus metrics endpoint.

#### GET `/status`

Service status and metrics summary for non-Prometheus consumers.

**Response:**

```json
{
  "uptime": 1630000000,
  "epochs_served": 1,
  "evaluations": 1000,
  "epoch": "2023-09-01",
  "rateLimit": 60,
  "metrics": true,
  "keys": 1,
  "active_key": "abcdef1234567890"
}
```

## Monitoring

The service exports Prometheus metrics that can be scraped from the `/metrics` endpoint. A Grafana dashboard is included in the `dashboard.json` file, which can be imported into Grafana for visualization.

Key metrics:

- `oprf_requests_total` - Total number of OPRF evaluation requests
- `oprf_evaluations_total` - Total number of individual OPRF evaluations
- `oprf_request_duration_seconds` - Request duration histograms
- `oprf_rate_limit_exceeded_total` - Count of rate limit exceeded events
- `oprf_key_rotations_total` - Count of key rotation events

## Key Management

Keys are stored in the directory specified by `--keydir` (default: `./keys`).

### Key Files

For each key, three files are created:
- `<key_id>.key`: The private key (hex-encoded)
- `<key_id>.pub`: The public key (hex-encoded)
- `<key_id>.json`: Key metadata (JSON)

### Key Rotation

Keys are automatically rotated based on the `--rotationdays` parameter (default: 30 days). When a key is rotated:

1. A new key is generated
2. The new key becomes the active key
3. The old key is marked as inactive
4. The old key remains valid for verification
5. The `oprf_key_rotations_total` metric is incremented

## Security Considerations

- The server is designed to be deployed behind a reverse proxy like Nginx or Traefik
- TLS should be enabled in production
- Private keys are stored with 0600 permissions
- Rate limiting helps prevent DoS attacks
- Key rotation enhances forward secrecy

## Production Deployment

For production deployment, consider the following:

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: oprf-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: oprf-service
  template:
    metadata:
      labels:
        app: oprf-service
    spec:
      containers:
      - name: oprf-service
        image: lemma/oprf-service:latest
        args:
          - "--port=8080"
          - "--keydir=/keys"
          - "--ratelimit=120"
          - "--rotationdays=30"
        ports:
        - containerPort: 8080
        volumeMounts:
        - name: oprf-keys
          mountPath: /keys
      volumes:
      - name: oprf-keys
        persistentVolumeClaim:
          claimName: oprf-keys-pvc
```

### Environment Variables

The following environment variables are supported for container-friendly configuration:

- `OPRF_PORT`: Port to run the service on
- `OPRF_KEY_DIR`: Directory for key storage
- `OPRF_RATE_LIMIT`: Rate limit in requests per minute
- `OPRF_ROTATION_DAYS`: Days between key rotations
- `OPRF_METRICS_ENABLED`: Enable Prometheus metrics (true/false)
- `OPRF_DEBUG`: Enable debug mode (true/false)

## Client Integration

To integrate with the OPRF service, clients need to:

1. Generate a random blinding factor
2. Blind their input (credential ID)
3. Send the blinded value to the service
4. Receive the evaluated value
5. Unblind the result

A JavaScript client is available in `lemma-oprf-client.js` and a Python client is available in `cascaded_bloom.py`.

## License

This project is licensed under the MIT License. 