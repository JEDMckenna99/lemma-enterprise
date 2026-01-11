# Lemma Documentation

## 🔐 **Core Concept**

Lemma is a **wallet-first authentication system**:

1. **Passkey** (biometric) unlocks the wallet locally
2. **Credentials** are stored in the user's browser
3. **Verification** happens client-side in microseconds
4. **No passwords, no sessions, no server-side state**

---

## 📖 **Getting Started**

| Document | Description | Time |
|----------|-------------|------|
| [Quick Start](QUICK_START_SIMPLE_LOGIN.md) | Add login to your site | 5 min |
| [SDK Reference](../sdk/README.md) | LemmaWallet API docs | Reference |
| [IAM API Reference](IAM_API_REFERENCE.md) | Server endpoints | Reference |

---

## 🏗️ **Architecture**

| Document | Description |
|----------|-------------|
| [Wallet-First Architecture](ARCHITECTURE_WALLET_FIRST.md) | How wallet-first differs from OAuth |
| [Whitepaper](WHITEPAPER_DIGITAL_LEMMAS.md) | Complete technical specification |
| [Protocol Design](protocol/PROTOCOL_DESIGN.md) | Core verification protocol |

---

## 🔧 **Integration Guides**

| Document | Use Case |
|----------|----------|
| [Simple Integration](SIMPLE_INTEGRATION_GUIDE.md) | Step-by-step walkthrough |
| [IAM-Only Integration](IAM_ONLY_INTEGRATION_GUIDE.md) | IAM without Proof-of-Human |
| [Permission Lemmas Guide](PERMISSION_LEMMAS_IAM_DEVELOPER_GUIDE.md) | Complete IAM developer reference |

---

## 🔐 **Security**

| Document | Description |
|----------|-------------|
| [Threat Model](security/THREAT_MODEL.md) | Security analysis and mitigations |
| [Security Review Package](security/SECURITY_REVIEW_PACKAGE.md) | Comprehensive security documentation |
| [Error Codes](ERROR_CODES.md) | Error handling reference |

---

## ⚙️ **Operations**

| Document | Description |
|----------|-------------|
| [KMS Setup Guide](KMS_SETUP_GUIDE.md) | AWS KMS configuration for key management |

---

## 🚀 **Quick Links**

| Resource | URL |
|----------|-----|
| **Live Platform** | https://lemma.id |
| **Dashboard** | https://lemma.id/platform |
| **Wallet Demo** | https://lemma.id/wallet |
| **API Status** | https://status.lemma.id |

---

## 📂 **Documentation Structure**

```
docs/
├── README.md                              # This file
├── QUICK_START_SIMPLE_LOGIN.md            # 5-minute quickstart
├── ARCHITECTURE_WALLET_FIRST.md           # Wallet-first vs OAuth
├── WHITEPAPER_DIGITAL_LEMMAS.md           # Technical foundation
├── IAM_API_REFERENCE.md                   # API documentation
├── SIMPLE_INTEGRATION_GUIDE.md            # Integration walkthrough
├── IAM_ONLY_INTEGRATION_GUIDE.md          # IAM-specific integration
├── PERMISSION_LEMMAS_IAM_DEVELOPER_GUIDE.md # Full IAM reference
├── ERROR_CODES.md                         # Error handling
├── KMS_SETUP_GUIDE.md                     # Key management setup
├── protocol/
│   └── PROTOCOL_DESIGN.md                 # Protocol specification
└── security/
    ├── THREAT_MODEL.md                    # Security analysis
    └── SECURITY_REVIEW_PACKAGE.md         # Security overview

sdk/
└── README.md                              # LemmaWallet SDK reference
```

---

## 🔑 **Key Concepts**

### Passkey (WebAuthn)

Passkeys are cryptographic credentials stored on your device, protected by biometrics (Touch ID, Face ID, Windows Hello). They replace passwords.

### Wallet

The wallet is an encrypted store in the user's browser (IndexedDB) that holds:
- Passkey reference for authentication
- Permission credentials from sites
- Wallet secret for PPID derivation

### PPID (Pairwise Pseudonymous Identifier)

Each site gets a **different identifier** for the same user:

```
User at site-a.com → did:lemma:ppid_abc123...
User at site-b.com → did:lemma:ppid_def456...

Sites CANNOT correlate these identifiers!
```

### Permission Lemma

A cryptographically signed credential that grants access to a site:

```json
{
    "issuer": "did:lemma:site_public_key...",
    "subject": "did:lemma:ppid_user_identifier...",
    "claims": {
        "siteId": "example.com",
        "permissions": "read,write,access"
    },
    "proof": { /* Ed25519 signature */ }
}
```

---

## 💬 **Support**

- **Email**: support@lemma.id
- **Documentation**: https://lemma.id/docs
