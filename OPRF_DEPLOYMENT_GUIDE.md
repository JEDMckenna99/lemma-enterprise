# OPRF Cascade Revocation Layer - Heroku Deployment Guide

## Overview

The OPRF (Oblivious Pseudorandom Function) cascade revocation layer provides privacy-preserving credential revocation checking for the Lemma system. This guide covers deploying the complete system to Heroku with both the Python web application and the Go OPRF service.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Heroku Dyno                             │
├─────────────────────────────────────────────────────────────┤
│  Web Process (Python)          OPRF Process (Go)           │
│  ┌─────────────────────┐      ┌─────────────────────┐      │
│  │ Flask App           │      │ OPRF Service        │      │
│  │ Port: $PORT         │◄────►│ Port: 8080          │      │
│  │ (Dynamic)           │      │ (Fixed)             │      │
│  └─────────────────────┘      └─────────────────────┘      │
│                                                             │
│  Shared Storage:                                            │
│  ├── instance/data/keys/       (OPRF keys)                 │
│  └── instance/data/revocation/ (Cascade data)              │
└─────────────────────────────────────────────────────────────┘
```

## Current Status

✅ **Configured**: Multi-buildpack deployment (Python + Go)
✅ **Configured**: OPRF service process in Procfile
✅ **Configured**: Environment variables for OPRF integration
✅ **Configured**: Cascade manager initialization
✅ **Configured**: Offline fallback mode for development

## Deployment Steps

### 1. Verify Configuration Files

The following files are already configured for OPRF deployment:

- **`.buildpacks`**: Multi-buildpack configuration
- **`Procfile`**: Both web and OPRF processes
- **`app.json`**: Environment variables and formation
- **`.godir`**: Go build directory specification

### 2. Deploy to Heroku

```bash
# Create Heroku app (if not already created)
heroku create your-lemma-app

# Set required environment variables
heroku config:set LEMMA_ADMIN_USER=admin
heroku config:set LEMMA_ADMIN_PASS=your_secure_password
heroku config:set LEMMA_SECRET_KEY=your_secret_key
heroku config:set LEMMA_API_KEY=your_api_key
heroku config:set DID=did:web:your-lemma-app.herokuapp.com

# Enable OPRF service
heroku config:set OPRF_SERVICE_INTERNAL=true

# Deploy the application
git push heroku main

# Scale both processes
heroku ps:scale web=1 oprf=1
```

### 3. Verify Deployment

```bash
# Check process status
heroku ps

# Check logs for both processes
heroku logs --tail

# Test OPRF service specifically
heroku logs --tail --dyno=oprf
```

### 4. Test OPRF Integration

You can test the OPRF integration using the provided test script:

```bash
# Run the integration test locally (will show offline mode)
python test_oprf_integration.py

# Or test via the deployed API endpoints
curl https://your-lemma-app.herokuapp.com/api/oprf/status
```

## Environment Variables

### Required for OPRF

- **`OPRF_SERVICE_INTERNAL=true`**: Enables internal OPRF service
- **`OPRF_RATE_LIMIT=60`**: Rate limiting (requests per minute)
- **`OPRF_ROTATION_DAYS=30`**: Key rotation interval
- **`OPRF_DEBUG=false`**: Debug mode (set to false for production)

### Optional for Advanced Configuration

- **`OPRF_SERVICE_URL`**: External OPRF service URL (if not using internal)
- **`LEMMA_ENABLE_OPRF=false`**: Disable OPRF entirely (fallback option)

## API Endpoints

The OPRF service provides the following endpoints:

### OPRF Service (Port 8080)
- **`GET /pubkey`**: Get OPRF public key
- **`POST /oprfeval`**: Evaluate blinded inputs
- **`GET /status`**: Service health check
- **`GET /metrics`**: Prometheus metrics

### Main App Integration
- **`GET /api/oprf/status`**: OPRF integration status
- **`POST /api/oprf/evaluate`**: Evaluate via cascade manager
- **`GET /cascade/<epoch>`**: Get cascade data for epoch

## Monitoring and Troubleshooting

### Check OPRF Service Status

```bash
# Check if OPRF process is running
heroku ps:scale

# View OPRF service logs
heroku logs --tail --dyno=oprf

# Test OPRF service directly
curl https://your-app.herokuapp.com:8080/status
```

### Common Issues

1. **OPRF Service Not Starting**
   - Check Go buildpack is configured
   - Verify `.godir` file points to `oprfservice`
   - Check OPRF process logs: `heroku logs --dyno=oprf`

2. **Connection Refused Errors**
   - Ensure `OPRF_SERVICE_INTERNAL=true`
   - Verify both processes are scaled: `heroku ps:scale web=1 oprf=1`
   - Check port configuration in Procfile

3. **Offline Mode in Production**
   - This indicates OPRF service is not accessible
   - Check process status and logs
   - Verify environment variables

### Performance Monitoring

The OPRF service includes Prometheus metrics:

- `oprf_requests_total`: Total OPRF requests
- `oprf_evaluations_total`: Total evaluations performed
- `oprf_request_duration_seconds`: Request latency
- `oprf_rate_limit_exceeded_total`: Rate limit violations

## Security Considerations

1. **Key Management**: OPRF keys are automatically generated and stored in `instance/data/keys/`
2. **Rate Limiting**: Configured to 60 requests per minute per IP
3. **Key Rotation**: Automatic rotation every 30 days
4. **Secure Communication**: All OPRF communication is over HTTPS in production

## Fallback Behavior

If the OPRF service is unavailable, the system automatically falls back to:

1. **Mock OPRF Implementation**: Uses deterministic hashing for testing
2. **Offline Mode**: Credentials are not checked against revocation lists
3. **Graceful Degradation**: Core functionality continues to work

## Testing the Deployment

After deployment, you can verify the OPRF system is working:

```bash
# Test the main application
curl https://your-app.herokuapp.com/api/oprf/status

# Expected response:
{
  "status": "ok",
  "oprf_service": "internal",
  "oprf_response": {
    "status": "ok",
    "service": "oprf",
    "version": "1.0.0"
  }
}
```

## Next Steps

1. **Deploy to Heroku** using the steps above
2. **Monitor logs** to ensure both processes start correctly
3. **Test OPRF integration** using the provided endpoints
4. **Set up monitoring** for the OPRF metrics
5. **Configure alerts** for service availability

The OPRF cascade revocation layer is now ready for production deployment on Heroku! 