# OPRF-Cascaded Bloom Filter Revocation Layer

This document outlines the implementation plan for enhancing Lemma with the OPRF-cascaded-Bloom layer for credential revocation.

## Current State Assessment

The current Lemma codebase already implements:

1. **Basic credential service:** Issues and verifies credentials with Ed25519 signatures
2. **DID resolution:** Supports multiple DID methods
3. **Basic revocation:** Simple bitstring-based revocation with Bloom filters
4. **P2P network:** For broadcasting revocation information 
5. **Zero-knowledge proofs:** Basic implementation for selective disclosure
6. **Client-side wallet:** For storing credentials in browser local storage

However, the current revocation system has limitations:
- No privacy guarantees - credential IDs are directly used in the Bloom filter
- No oblivious evaluation - the service learns which credentials are being checked
- Limited efficiency for large-scale deployment
- No witness-based approach for offline verification

## OPRF-Cascaded Bloom Enhancement Plan

The OPRF (Oblivious Pseudorandom Function) Cascaded Bloom filter implementation will provide:

1. **Privacy-preserving revocation checks:** Verifiers can check credential status without revealing which credential is being checked
2. **Compact synchronization:** Cascaded Bloom filters reduce size requirements
3. **Offline verification:** Credentials can include witnesses proving non-revocation
4. **Zero metadata leakage:** Service learns nothing about user credentials

## Implementation Components

### 1. OPRF Service (New)

```go
// GO Microservice (oprfservice/main.go)
package main

import (
    "net/http"
    "github.com/cloudflare/circl/oprf"
    "github.com/gin-gonic/gin"
)

func main() {
    r := gin.Default()
    
    // Initialize OPRF with ristretto255 suite
    suite := oprf.SuiteRistretto255
    server, _ := oprf.NewServer(suite, nil)
    
    // Endpoint for OPRF evaluation
    r.POST("/oprfeval", func(c *gin.Context) {
        var request struct {
            Alpha []string `json:"alpha"` // Base64-encoded blinded elements
        }
        
        if err := c.BindJSON(&request); err != nil {
            c.JSON(400, gin.H{"error": "Invalid request"})
            return
        }
        
        // Convert string to evaluation elements
        elements := make([]oprf.Element, len(request.Alpha))
        for i, alpha := range request.Alpha {
            // Decode base64 to Element
            // ...
        }
        
        // Evaluate the OPRF function
        evaluations, err := server.Evaluate(elements)
        if err != nil {
            c.JSON(500, gin.H{"error": "OPRF evaluation failed"})
            return
        }
        
        // Convert evaluations to response format
        var response struct {
            Beta []string `json:"beta"` // Base64-encoded evaluated elements
        }
        
        // Populate response
        // ...
        
        c.JSON(200, response)
    })
    
    r.Run(":8080")
}
```

### 2. Updated Revocation System (Modified)

The existing `revocation.py` needs to be enhanced to use OPRF evaluations instead of raw hashes:

```python
class CascadedBloomRevocation:
    """
    Enhanced revocation system using OPRF evaluations and cascaded Bloom filters.
    """
    
    def __init__(self, issuer_id, cascade_levels=3, error_rate=0.02):
        self.issuer_id = issuer_id
        self.cascade_levels = cascade_levels
        self.error_rate = error_rate
        self.levels = []  # List of Bloom filters with decreasing precision
        
        # Initialize the cascade
        self._init_cascade()
        
    def _init_cascade(self):
        """Initialize the bloom filter cascade with increasing sizes."""
        # Initial size based on expected number of revoked credentials
        expected_size = 10000  # Can be parameterized based on expected revocations
        
        for level in range(self.cascade_levels):
            # Each level uses a different size and error rate
            level_size = expected_size * (10 ** level)
            level_error = self.error_rate / (10 ** level)
            
            # Create a Bloom filter for this level
            bloom = BloomFilter(
                capacity=level_size,
                error_rate=level_error
            )
            
            self.levels.append(bloom)
            
    def revoke(self, credential_id):
        """
        Revoke a credential by adding its OPRF evaluation to the cascade.
        
        Args:
            credential_id: ID of the credential to revoke
        """
        # Get the OPRF evaluation for this ID
        evaluation = self._get_oprf_evaluation(credential_id)
        
        # Add to all levels of the cascade
        for bloom in self.levels:
            bloom.add(evaluation)
            
    def is_revoked(self, oprf_evaluation):
        """
        Check if a credential is revoked using its OPRF evaluation.
        
        Args:
            oprf_evaluation: The OPRF evaluation to check
            
        Returns:
            (bool, int): (is_revoked, level_matched) - the level is useful for confidence
        """
        # Check each level, starting from the most precise
        for level, bloom in enumerate(self.levels):
            if oprf_evaluation in bloom:
                return True, level
                
        # Not found in any level
        return False, -1
        
    def _get_oprf_evaluation(self, credential_id):
        """Get the OPRF evaluation for a credential ID."""
        # In a real implementation, this would call the OPRF service
        # For now, we'll use a hash as a placeholder
        return f"oprf_{hashlib.sha256(credential_id.encode()).hexdigest()}"
        
    def generate_witness(self, credential_id, epoch):
        """
        Generate a witness proving that a credential is not revoked.
        
        Args:
            credential_id: ID of the credential
            epoch: Current epoch (e.g., date)
            
        Returns:
            dict: A witness that can be verified offline
        """
        # In a real implementation, this would:
        # 1. Generate random blinding factor r
        # 2. Compute alpha = r·H₁(credential_id)
        # 3. Get beta from OPRF service 
        # 4. Return {alpha, beta, r, epoch}
        
        # Placeholder implementation
        return {
            "epoch": epoch,
            "alpha": f"alpha_{credential_id}_{epoch}",
            "beta": f"beta_{credential_id}_{epoch}",
            "r": f"r_{credential_id}_{epoch}"
        }
        
    def verify_witness(self, witness, cascade_hash):
        """
        Verify a non-revocation witness without connecting to the service.
        
        Args:
            witness: The witness to verify
            cascade_hash: Hash of the cascade for the witness's epoch
            
        Returns:
            bool: True if the witness is valid
        """
        # In a real implementation, this would:
        # 1. Verify the cascade hash matches the expected value for the epoch
        # 2. Compute y = β^(r⁻¹) using values from witness
        # 3. Check if y is in the cascade
        
        # Placeholder implementation
        return True
```

### 3. OPRF Client Wallet Integration

The client-side wallet (`lemma-wallet.js`) needs to be updated to handle OPRF operations:

```javascript
class LemmaWalletOPRF {
    constructor() {
        // Initialize OPRF client
        this.oprfClient = new OPRFClient();
        this.credentials = [];
        this.oprfCache = {};  // Cache for OPRF evaluations
    }
    
    async refreshOPRFEvaluations(epoch) {
        // For each credential, obtain a fresh OPRF evaluation for the current epoch
        for (const credential of this.credentials) {
            const cid = credential.id;
            
            // Generate random blinding factor
            const r = this.generateRandomScalar();
            
            // Compute blinded element
            const alpha = this.oprfClient.blind(cid, r);
            
            // Get evaluation from server
            const response = await fetch('/oprfeval', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({alpha: [alpha]})
            });
            
            const result = await response.json();
            const beta = result.beta[0];
            
            // Unblind the result
            const y = this.oprfClient.unblind(beta, r);
            
            // Store in cache
            this.oprfCache[cid] = {
                epoch,
                evaluation: y,
                witness: {alpha, beta, r, epoch}
            };
        }
    }
    
    async verifyRevocationStatus(credentialId) {
        // Check if we have a cached evaluation
        const cached = this.oprfCache[credentialId];
        if (!cached) {
            return {valid: false, reason: "No OPRF evaluation available"};
        }
        
        // Get the latest cascade
        const response = await fetch(`/cascade/${cached.epoch}`);
        const cascade = await response.json();
        
        // Check locally if the credential is revoked
        // This is a privacy-preserving local check using the cascade
        const bloomTest = this.testAgainstCascade(cached.evaluation, cascade);
        
        if (bloomTest.revoked) {
            return {valid: false, reason: `Credential revoked (level ${bloomTest.level})`};
        }
        
        return {valid: true, witness: cached.witness};
    }
    
    createPresentationWithWitness(credential, challenge) {
        // Get the witness
        const witness = this.oprfCache[credential.id]?.witness;
        if (!witness) {
            throw new Error("No revocation witness available");
        }
        
        // Create the presentation with the witness
        const presentation = {
            "@context": ["https://www.w3.org/2018/credentials/v1"],
            "type": ["VerifiablePresentation"],
            "verifiableCredential": [credential],
            "proof": {
                "type": "Ed25519Signature2020",
                "challenge": challenge,
                "created": new Date().toISOString(),
                // Other proof properties
            },
            "revocationWitness": witness
        };
        
        return presentation;
    }
}
```

### 4. Batch Job for Cascade Building (New)

A new batch job is needed to periodically rebuild the cascade and publish it:

```python
def build_revocation_cascade(revoked_list, k_priv, epoch):
    """
    Build a cascaded Bloom filter for revoked credentials.
    
    Args:
        revoked_list: List of revoked credential IDs
        k_priv: OPRF private key
        epoch: Current epoch
        
    Returns:
        dict: The cascade bundle ready for distribution
    """
    # Create the cascade
    cascade = CascadedBloomRevocation(f"did:lemma:{k_priv.public_key_hash}")
    
    # Process each revoked credential
    for cid in revoked_list:
        # Evaluate the OPRF function
        y = oprf_eval(k_priv, cid)
        
        # Add to cascade
        cascade.revoke(y)
    
    # Build the bundle
    bundle = {
        "cascade": cascade.to_dict(),
        "issuer": f"did:lemma:{k_priv.public_key_hash}",
        "epoch": epoch,
        "created": datetime.now().isoformat(),
        "expires": (datetime.now() + timedelta(days=1)).isoformat(),
        "k_pub": k_priv.public_key_bytes.hex(),
        "padding_info": {
            "min_size": 10000,
            "pad_to": 100000  # For size privacy
        }
    }
    
    # Sign the bundle
    signature = sign_with_key(k_priv, json.dumps(bundle).encode())
    bundle["signature"] = signature.hex()
    
    return bundle
```

### 5. Cascade Distribution Endpoint (New)

A new API endpoint to serve the latest cascade:

```python
@api_bp.route('/cascade/<epoch>')
@rate_limit
def get_cascade(epoch):
    """
    Get the revocation cascade for a specific epoch.
    
    Args:
        epoch: The epoch identifier (e.g., "2023-06-15")
        
    Returns:
        The cascade bundle for the specified epoch
    """
    try:
        # Get the cascade from storage
        cascade_file = os.path.join(
            current_app.config['STORAGE_DIR'], 
            'revocation', 
            f'cascade_{epoch}.json'
        )
        
        if not os.path.exists(cascade_file):
            return jsonify({
                "error": "No cascade available for this epoch"
            }), 404
            
        with open(cascade_file, 'r') as f:
            cascade = json.load(f)
            
        return jsonify(cascade)
    except Exception as e:
        return jsonify({
            "error": f"Error retrieving cascade: {str(e)}"
        }), 500
```

### 6. Wallet Integration for OPRF (Modified)

Updates to `lemma/utils/wallet.py`:

```python
class LemmaWallet:
    """Enhanced Lemma wallet with OPRF revocation support."""
    
    @staticmethod
    def format_for_wallet(credential, user_id):
        """Format a credential for wallet storage with OPRF witness."""
        # Get current epoch
        current_epoch = time.strftime("%Y-%m-%d")
        
        # Generate a witness for this credential
        revocation_service = get_revocation_service()
        witness = revocation_service.generate_witness(credential["id"], current_epoch)
        
        # Add to the wallet metadata
        return {
            "credential": credential,
            "wallet_metadata": {
                "added_at": credential.get('issuanceDate', datetime.now().isoformat()),
                "holder_id": user_id,
                "status": "active",
                "display_name": "Lemma Human Verification",
                "fingerprint": credential.get('id', f"credential-{user_id}"),
                "revocation_witness": witness,
                "witness_epoch": current_epoch
            }
        }
```

## Integration Strategy

The implementation will follow these phases:

### Phase 1: Prototype Development (1-2 weeks)

1. Develop Go microservice for OPRF evaluation using Cloudflare's circl/oprf library
2. Modify `revocation.py` to implement the cascaded Bloom filter structure
3. Create basic OPRF client implementation in JavaScript

### Phase 2: Backend Integration (1 week)

1. Integrate OPRF microservice with Lemma backend
2. Implement cascade building and distribution endpoints
3. Create scheduled job for regular cascade rebuilding

### Phase 3: Frontend Integration (1 week)

1. Enhance wallet.js to support OPRF operations and witness management
2. Update presentation creation to include revocation witnesses
3. Implement offline verification of witnesses

### Phase 4: Testing and Benchmarking (1 week)

1. Measure performance metrics (lookup speed, cascade size)
2. Test with large-scale revocation data
3. Analyze privacy properties

## Deployment Considerations

1. **Go Microservice Deployment**: The OPRF service should be deployed alongside the main Lemma service, either:
   - As a separate container in the same pod (Kubernetes)
   - As a process managed by supervisord (traditional servers)
   - As a separate serverless function (AWS Lambda/Azure Functions)

2. **Key Management**: The OPRF private key must be securely stored and managed:
   - Hardware Security Module (HSM) integration for production
   - Environment variables or secure key storage for development

3. **Scalability**: The OPRF service should be horizontally scalable to handle high loads

4. **Caching**: Implement caching at multiple levels:
   - Client-side caching of evaluations
   - CDN for cascade distribution
   - Server-side caching for frequent OPRF evaluations

## Metrics for Success

1. **Performance**:
   - OPRF evaluation time: <1ms per credential
   - Cascade size: <100KB per 1M revoked credentials
   - False positive rate: <0.02% (adjustable with cascade parameters)

2. **Privacy**:
   - Zero knowledge of credential ID during revocation check
   - No metadata leakage from cascade lookups
   - No ability to track users across sites

3. **User Experience**:
   - Seamless integration with existing verification flow
   - No perceived latency for users
   - Offline verification capabilities

## Next Steps

1. Start with implementing the Go OPRF microservice
2. Setup development environment and testing framework
3. Enhance revocation system with cascaded bloom filter implementation
4. Create the client-side OPRF libraries
5. Integrate all components and run end-to-end tests 