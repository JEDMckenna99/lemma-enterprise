# Lemma

**Passwordless authentication with client-side credential verification.**

Lemma is an authentication platform that stores cryptographic credentials in users' browsers and verifies them locally - no server calls, no sessions, no passwords.

**Live at:** [lemma.id](https://lemma.id)

---

## What Lemma Does

1. **Issues credentials** via email confirmation (passwordless sign-up/sign-in)
2. **Stores credentials** in the user's browser wallet (encrypted IndexedDB)
3. **Verifies credentials** client-side using Ed25519 signatures (no server round-trips)
4. **Revokes credentials** via OPRF + bloom filter (privacy-preserving)

Users authenticate once, and their credential works across all Lemma-enabled sites without repeated logins or server verification calls.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         USER'S BROWSER                               │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                      LEMMA WALLET                               │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │ │
│  │  │   Passkey    │  │  Credentials │  │  Issuer Public Keys  │  │ │
│  │  │  (WebAuthn)  │  │   (Lemmas)   │  │      (cached)        │  │ │
│  │  └──────────────┘  └──────────────┘  └──────────────────────┘  │ │
│  │                                                                 │ │
│  │  LOCAL VERIFICATION (no server calls)                           │ │
│  │  • Ed25519 signature check (Web Crypto API)                     │ │
│  │  • Expiration check                                             │ │
│  │  • Revocation check (bloom filter)                              │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 │ (only for issuance/revocation sync)
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          LEMMA.ID SERVER                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │
│  │ Issue Credentials│ │ Revoke Credentials│ │ Publish Revocation  │  │
│  │   (KMS-backed)   │ │  (network-wide)   │ │     Filter          │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Properties

- **Session-free:** No server-side sessions. Verification happens in the browser.
- **Offline-capable:** After initial credential issuance, verification works without network access.
- **Privacy-preserving:** Sites verify credentials locally; Lemma doesn't see per-verification traffic.

---

## Credential Structure (Lemma)

A lemma is a signed credential with the following structure:

```json
{
  "id": "cred_abc123",
  "issuer": "did:lemma:<64-char-ed25519-public-key-hex>",
  "subject": "did:lemma:<64-char-subject-public-key-hex>",
  "issued_at": 1705000000,
  "expires_at": 1736536000,
  "claims": {
    "packageType": "identity",
    "email": "user@example.com",
    "permissionId": "developer",
    "siteId": "site_xyz"
  },
  "proof": {
    "type": "Ed25519Signature2020",
    "signatureValue": "<128-char-ed25519-signature-hex>"
  }
}
```

### Verification Flow

1. Extract issuer public key from DID
2. Verify Ed25519 signature against credential content
3. Check expiration timestamp
4. Check revocation status (bloom filter lookup)

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Python/Flask |
| Database | PostgreSQL |
| Crypto Engine | Rust (lemma-crypto) → Python bindings + WebAssembly |
| Key Storage | AWS KMS (HSM-backed) |
| Hosting | Heroku |
| Payments | Stripe |
| Passkeys | WebAuthn |

---

## Project Structure

```
lemma-rebuild/
├── app.py                  # Flask application entry point
├── api/                    # API blueprints
│   ├── lemma_shield.py     # Core credential verification
│   ├── wallet_first_auth.py # Wallet-based authentication
│   ├── passkey_auth.py     # WebAuthn passkey handling
│   ├── permission_management_api.py
│   ├── revocation_api.py   # Credential revocation
│   ├── kms_manager.py      # AWS KMS integration
│   └── ...
├── lemma-crypto/           # Rust crypto engine
│   ├── src/
│   │   ├── lib.rs
│   │   ├── minimal_core.rs     # Ed25519 verification
│   │   ├── oprf.rs             # OPRF operations
│   │   ├── bloom.rs            # Revocation bloom filter
│   │   └── wasm_bindings.rs    # WebAssembly exports
│   └── Cargo.toml
├── static/js/              # Client-side JavaScript
│   ├── lemma-wallet.js     # Browser wallet SDK
│   ├── lemma-passkey.js    # Passkey handling
│   └── lemma-client-verifier.js
├── templates/              # HTML templates
│   ├── modern/             # Main site pages
│   └── developer/          # Developer platform
├── sdk/                    # NPM SDK package
└── docs/                   # Documentation
```

---

## Local Development

### Prerequisites

- Python 3.11+
- Rust (for crypto engine compilation)
- PostgreSQL

### Setup

```bash
# Clone repository
git clone <repo-url>
cd lemma-rebuild

# Python environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt

# Build Rust crypto engine
cd lemma-crypto
cargo build --release
maturin develop  # builds Python bindings
cd ..

# Environment variables (see Configuration section)
# Set in Heroku config vars or local .env file

# Run development server
python app.py
```

### Building WebAssembly

```bash
cd lemma-crypto
wasm-pack build --target web --out-dir ../static/wasm
```

---

## Configuration

All configuration is stored in Heroku environment variables [[memory:8227205]].

### Required Secrets

```bash
# Core authentication secrets
LEMMA_OAUTH_JWT_SECRET=<64-char-random>
LEMMA_NETWORK_AUTH_KEY=<64-char-random>
LEMMA_PPID_ROOT_KEY=<64-char-random>
LEMMA_BILLING_HMAC_SECRET=<64-char-random>
LEMMA_HPKE_SERVER_KEY=<64-char-random>
LEMMA_WALLET_SALT=<64-char-random>
SECRET_KEY=<flask-secret>

# Database
DATABASE_URL=<postgres-connection-string>
```

### Optional Services

```bash
# AWS KMS (for HSM-backed key storage)
AWS_ACCESS_KEY_ID=<key>
AWS_SECRET_ACCESS_KEY=<secret>
LEMMA_KMS_KEY_ID=<kms-key-id>

# Stripe (for billing)
STRIPE_SECRET_KEY=<key>
STRIPE_PUBLISHABLE_KEY=<key>
STRIPE_WEBHOOK_SECRET=<secret>

# Redis (for pub/sub revocation sync)
REDIS_URL=<redis-connection-string>

# Email
SENDGRID_API_KEY=<key>
```

Generate secrets with:
```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

---

## API Overview

### Authentication Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/wallet/session-sync` | POST | Get wallet session for cross-site auth |
| `/api/passkey/register/start` | POST | Start passkey registration |
| `/api/passkey/authenticate/start` | POST | Start passkey authentication |
| `/api/v1/auth/verify` | POST | Verify user permissions |

### Credential Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/sdk/issue-credential` | POST | Issue a new credential |
| `/api/revocation/revoke` | POST | Revoke a credential |
| `/api/revocation/filter` | GET | Get current bloom filter |

### Site Management (Developer Platform)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/sites/register` | POST | Register a site |
| `/api/v1/sites/<id>/permissions` | POST | Create permission type |
| `/api/sdk/config/<site_id>` | GET | Get SDK configuration |

---

## SDK Integration

### Browser (Script Tag)

```html
<script src="https://lemma.id/static/js/lemma-wallet.js"></script>
<script>
  const wallet = new LemmaWallet();
  
  // Check if user has valid credential
  const credential = await wallet.getValidCredential('your_site_id');
  
  if (credential) {
    // User is authenticated
    console.log('Authenticated:', credential.claims.email);
  } else {
    // Redirect to login
    window.location.href = 'https://lemma.id/login?site=your_site_id';
  }
</script>
```

### Cross-Site Authentication (Bridge)

Sites can embed the Lemma wallet bridge to access credentials:

```html
<iframe 
  id="lemma-bridge" 
  src="https://lemma.id/wallet/bridge"
  style="display: none;">
</iframe>

<script>
  const bridge = document.getElementById('lemma-bridge');
  
  // Request credential from bridge
  bridge.contentWindow.postMessage({
    type: 'GET_CREDENTIAL',
    siteId: 'your_site_id'
  }, 'https://lemma.id');
  
  // Handle response
  window.addEventListener('message', (event) => {
    if (event.origin !== 'https://lemma.id') return;
    if (event.data.type === 'CREDENTIAL_RESPONSE') {
      // Verify credential locally
      const valid = verifyCredential(event.data.credential);
    }
  });
</script>
```

---

## Deployment

The platform is deployed to Heroku with the following buildpacks:

1. `heroku/python`
2. `emk/rust` (for lemma-crypto compilation)

### Deploy to Heroku

```bash
git push heroku main
```

### Deploy to lemma.id

```bash
git push lemma main
```

[[memory:5489359]]

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `app.py` | Flask app factory, route registration |
| `api/config.py` | Centralized secrets management |
| `api/lemma_shield.py` | Core verification logic |
| `api/wallet_first_auth.py` | Wallet-based auth flow |
| `api/passkey_auth.py` | WebAuthn implementation |
| `api/kms_manager.py` | AWS KMS key encryption |
| `api/revocation_api.py` | Credential revocation |
| `lemma-crypto/src/minimal_core.rs` | Ed25519 verification |
| `lemma-crypto/src/oprf.rs` | OPRF operations |
| `lemma-crypto/src/bloom.rs` | Bloom filter |
| `static/js/lemma-wallet.js` | Browser wallet SDK |

---

## Documentation

- [Architecture: Wallet-First Authentication](docs/ARCHITECTURE_WALLET_FIRST.md)
- [Simple Integration Guide](docs/SIMPLE_INTEGRATION_GUIDE.md)
- [IAM API Reference](docs/IAM_API_REFERENCE.md)
- [KMS Setup Guide](docs/KMS_SETUP_GUIDE.md)
- [Privacy Architecture](docs/PRIVACY_ARCHITECTURE.md)

---

## Status

**Currently in beta.** Free access during beta period.

Production deployed at [lemma.id](https://lemma.id).

---

## License

Proprietary. All rights reserved.
