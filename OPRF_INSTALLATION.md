# OPRF-Cascaded Bloom Filter Installation Guide

This guide provides instructions for setting up the OPRF (Oblivious Pseudorandom Function) service and cascaded Bloom filter components for Lemma's privacy-preserving revocation system.

## Overview

The OPRF-cascaded Bloom filter implementation consists of several components:

1. **Go Microservice**: For OPRF evaluation using ristretto255 elliptic curves
2. **Python Libraries**: For cascaded Bloom filter creation and management
3. **Client-side JavaScript**: For wallet integration and witness management
4. **API Endpoints**: For serving cascade bundles
5. **Batch Job**: For periodic cascade rebuilding

## Prerequisites

- Go 1.18 or higher (for the OPRF service)
- Python 3.8 or higher
- Node.js 14 or higher (for client development)
- PostgreSQL (if using a database for revocation storage)
- Existing Lemma installation

## 1. Installing the OPRF Microservice

### 1.1 Install dependencies

First, make sure you have Go installed:

```bash
# Check Go version
go version

# Should output: go version go1.18 or higher
```

### 1.2 Build the OPRF service

```bash
# Navigate to the OPRF service directory
cd oprfservice

# Download dependencies
go mod download

# Build the service
go build -o oprf-service main.go

# Make the service executable
chmod +x oprf-service
```

### 1.3 Generate OPRF key

```bash
# Generate a new OPRF key
./oprf-service --generate
```

### 1.4 Test the service

```bash
# Start the service on port 8080
./oprf-service --port 8080
```

You should see output indicating the service is running. Test it with a simple HTTP request:

```bash
curl -X GET http://localhost:8080/health
```

This should return a JSON response like:
```json
{"status":"ok","service":"lemma-oprf-service","version":"1.0.0","timestamp":1623456789,"epoch":"2023-06-15"}
```

## 2. Installing Python Dependencies

### 2.1 Install required Python packages

```bash
# Install required packages
pip install numpy pybloom_live requests

# If you're not using pybloom_live, the implementation includes a fallback
```

### 2.2 Copy the cascaded Bloom filter implementation

Ensure the `lemma/core/cascaded_bloom.py` file is in the correct location in your Lemma installation.

### 2.3 Test the Python implementation

```python
from lemma.core.cascaded_bloom import CascadedBloomRevocation

# Create a cascade
cascade = CascadedBloomRevocation(issuer_id="did:lemma:test")

# Test revocation
cascade.revoke("test-credential-id")
print(f"Number of levels: {len(cascade.levels)}")
```

## 3. Setting Up the Batch Job

### 3.1 Configure the batch job

Create a configuration file `config.json` for the cascade builder:

```json
{
  "storage_dir": ".lemma_enterprise",
  "oprf_server_url": "http://localhost:8080",
  "cascade_levels": 3,
  "error_rate": 0.02,
  "issuer_id": "did:lemma:your-issuer-id",
  "keep_days": 7
}
```

### 3.2 Test the batch job

```bash
# Run the cascade builder
python build_cascade.py --config config.json
```

### 3.3 Schedule the batch job

Set up a daily cron job to rebuild the cascade:

```bash
# Edit crontab
crontab -e

# Add line to run at midnight every day
0 0 * * * cd /path/to/lemma && python build_cascade.py --config config.json >> /path/to/lemma/cascade_cron.log 2>&1
```

## 4. Integrating with Lemma

### 4.1 Add the JavaScript client to your frontend

Copy the `lemma-oprf-client.js` file to your `static/js` directory.

Include the script in your templates:

```html
<script src="{{ url_for('static', filename='js/lemma-oprf-client.js') }}"></script>
```

Initialize the client in your wallet code:

```javascript
// Initialize OPRF client
const oprfClient = new LemmaOPRFClient({
  serverUrl: '/oprfeval',
  pubkeyEndpoint: '/pubkey',
  cascadeEndpoint: '/cascade/'
});

// Initialize the client
await oprfClient.initialize();

// Later, when checking credential status:
const result = await oprfClient.checkRevocationStatus(credentialId);
if (result.revoked) {
  console.log(`Credential is revoked (confidence level: ${result.level})`);
} else {
  console.log("Credential is valid");
  console.log("Witness:", result.witness);
}
```

### 4.2 Update your credential verification code

Modify your credential verification logic to check the revocation status using the OPRF cascade:

```python
from lemma.core.cascaded_bloom import OPRFClient, CascadedBloomRevocation

# During verification
def verify_with_witness(credential, witness):
    # Load the cascade for the witness epoch
    cascade_file = os.path.join(
        app.config['STORAGE_DIR'],
        'revocation',
        'cascades',
        f"cascade_{witness['epoch']}.json"
    )
    
    with open(cascade_file, 'r') as f:
        cascade_data = json.load(f)
    
    # Recreate cascade from the data
    cascade = CascadedBloomRevocation.from_dict(cascade_data['cascade'])
    
    # Verify the witness
    is_valid = cascade.verify_witness(witness, cascade_data['metadata']['hash'])
    
    return is_valid
```

## 5. Running in Production

### 5.1 Set up a systemd service for the OPRF microservice

Create a systemd service file `/etc/systemd/system/lemma-oprf.service`:

```ini
[Unit]
Description=Lemma OPRF Service
After=network.target

[Service]
User=lemma
WorkingDirectory=/opt/lemma/oprfservice
ExecStart=/opt/lemma/oprfservice/oprf-service --port 8080
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl enable lemma-oprf
sudo systemctl start lemma-oprf
```

### 5.2 Configure Nginx for OPRF service proxy

Add to your Nginx configuration:

```nginx
location /oprfeval {
    proxy_pass http://localhost:8080/oprfeval;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}

location /pubkey {
    proxy_pass http://localhost:8080/pubkey;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

### 5.3 Set up CDN for cascade distribution

For optimal performance, configure a CDN to serve the cascade bundles:

```nginx
location /cascade/ {
    alias /opt/lemma/.lemma_enterprise/revocation/cascades/;
    add_header Cache-Control "public, max-age=3600";
    add_header Content-Type "application/json";
}
```

## 6. Monitoring and Maintenance

### 6.1 Logs

Check the OPRF service logs:

```bash
sudo journalctl -u lemma-oprf
```

Check the cascade builder logs:

```bash
cat cascade_builder.log
```

### 6.2 Metrics to monitor

- OPRF service response time (should be < 1ms)
- Cascade file size (should be < 100KB per 1M revoked credentials)
- Daily cascade build success/failure
- Client-side verification latency

## 7. Troubleshooting

### OPRF service not responding

Check if the service is running:

```bash
ps aux | grep oprf-service
```

Restart the service:

```bash
sudo systemctl restart lemma-oprf
```

### Cascade not building properly

Check the cascade builder logs:

```bash
cat cascade_builder.log
```

Try running the builder manually with verbose logging:

```bash
python build_cascade.py --config config.json --force
```

### Client-side errors

Check browser console for JavaScript errors related to the OPRF client. Common issues include:

- Network connectivity to the OPRF service
- Missing or outdated cascade bundle
- Malformed witness data

## 8. Conclusion

The OPRF-cascaded Bloom filter revocation system provides a privacy-preserving way to check credential status without revealing which credential is being checked. By following this guide, you've set up all the components needed for this system to work effectively.

Remember to regularly monitor the system's performance and update the OPRF keys periodically for maximum security.

## Additional Resources

- [RFC 9497 - OPRF Protocol](https://datatracker.ietf.org/doc/rfc9497/)
- [Cloudflare's circl library](https://github.com/cloudflare/circl)
- [Bloom Filter Mathematics](https://en.wikipedia.org/wiki/Bloom_filter)
- [Lemma Documentation](https://lemma.com/docs) 

For questions or support, please contact the Lemma team. 