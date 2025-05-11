# Lemma Development Guidelines

## Project Vision
- **"Verify once, everywhere"** — Lemma is like Stripe for digital identity
- Core flow: User verifies once, receives a portable credential (lemma), and uses it across partner sites
- No PII stored in the system, only verifies humanness

## Architecture

### Core Components
- **Routes/API**: `/lemma/routes/` - HTTP endpoints for user-facing features
- **Core**: `/lemma/core/` - Business logic and credential services
- **Auth**: `/lemma/auth/` - Authentication and security logic
- **Utils**: `/lemma/utils/` - Utility functions and helpers
- **Models**: `/lemma/models/` - Data models and schemas

### Key Features
1. **Identity Verification**: Stripe Identity for user verification
2. **W3C Verifiable Credentials (Lemmas)**: Issues credentials that follow W3C VC data model
3. **Decentralized Identifiers (DIDs)**: `did:lemma` method for credential subjects
4. **Browser Wallet**: Stores and presents credentials
5. **OIDC4VP**: For third-party site integration
6. **Privacy-First Design**: No PII storage

## Development Rules

### Code Style
- **Python**: Follow PEP 8 guidelines
- **Comments**: Add docstrings to all functions and classes
- **Naming**:
  - Classes: `CamelCase`
  - Functions/Methods: `snake_case`
  - Constants: `UPPER_CASE`
- **Imports**: Organize imports (standard lib, third-party, local)

### Security First
1. **No PII Storage**: Ensure no personal data is stored anywhere
2. **Secure Key Management**: Use environment variables for secrets
3. **Input Validation**: Validate all user inputs
4. **CSRF Protection**: Ensure all forms have CSRF protection
5. **XSS Prevention**: Escape all user-generated content
6. **Rate Limiting**: Apply rate limits to all API endpoints

### Testing
- **Unit Tests**: Required for all new code
- **Integration Tests**: Required for API endpoints
- **Test Coverage**: Maintain >80% coverage
- **Run tests**: `python run_tests.py` before commits

### User Flow
1. **Verification**: User completes Stripe Identity ➝ Receives lemma
2. **Storage**: Lemma stored in browser wallet (localStorage or wallet app)
3. **Presentation**: User presents lemma to partner sites
4. **Verification**: Partner sites verify lemma using Lemma's DID

### DID/VC Implementation
- **DID Format**: `did:lemma:<uuid>`
- **VC Structure**:
  - Issuer: Lemma's DID
  - Subject: User's identifier (not PII)
  - Type: `["VerifiableCredential", "LemmaCredential", "HumanCredential"]`
  - Proof: Ed25519 signature

### Deployment
- **Environment Variables**:
  - `ED25519_PRIVATE_KEY`: Base64-encoded private key
  - `DID`: (Optional) Custom DID
  - `LEMMA_ADMIN_USER`: Admin username
  - `LEMMA_ADMIN_PASS`: Admin password
- **Heroku Deployment**:
  - Set all env vars securely
  - Use `heroku restart` after config changes
  - Set up custom domain with proper DNS

## Priorities for Now
1. **Core verification flow** working on main site
2. **W3C VC issuance** after successful verification
3. **Browser wallet storage** of lemmas
4. **Presentation/verification** of credentials
5. **Session management** after verification

## Future Extensions
1. **Partner API documentation**
2. **OIDC4VP full integration**
3. **Partner analytics and billing**
4. **Advanced wallet integrations**
5. **Mobile wallet support**

## Development Workflow
1. **Feature branches**: Create a branch for each feature
2. **Testing**: Run tests before creating PRs
3. **Deployment**: Test locally, then deploy to staging before production
4. **Documentation**: Update docs with any API or flow changes 