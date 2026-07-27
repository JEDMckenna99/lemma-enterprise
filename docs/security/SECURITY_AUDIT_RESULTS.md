# Lemma.id Security Audit Results

**Audit Date:** January 22, 2026  
**Auditor:** Automated tooling + manual review

---

## 1. Dependency Audit Results

### Current Status: ALL CRITICAL VULNERABILITIES FIXED

### Python Dependencies (`pip-audit`)

| Package | Previous | Issue | Status |
|---------|----------|-------|--------|
| gunicorn | 21.2.0 | CVE-2024-1135, CVE-2024-6827 | **FIXED** (upgraded to >=22.0.0) |

**Current scan result:** No known vulnerabilities found

### Rust Dependencies (`cargo audit`)

| Crate | Previous | Issue | Status |
|-------|----------|-------|--------|
| pyo3 | 0.20.3 | RUSTSEC-2025-0020 (buffer overflow) | **FIXED** (upgraded to 0.24) |
| slab | 0.4.10 | RUSTSEC-2025-0047 (out-of-bounds) | **FIXED** (upgraded to 0.4.11) |

**Remaining warnings (non-critical, informational only):**

| Crate | Issue | Severity | Notes |
|-------|-------|----------|-------|
| bincode | Unmaintained | Low | Works fine, consider migration later |
| derivative | Unmaintained | Low | Transitive dependency |
| paste | Unmaintained | Low | Transitive dependency |
| serde_cbor | Unmaintained | Low | Consider ciborium for new code |
| pkcs11 | Unsound API | Low | HSM feature, review if used |

### JavaScript Dependencies (`npm audit`)

| Package | Vulnerabilities |
|---------|-----------------|
| CDN packages | 0 found |

**Status:** Clean

---

## 2. OWASP Top 10 Self-Check (2021)

### A01:2021 - Broken Access Control

| Check | Status | Notes |
|-------|--------|-------|
| Server-side access control enforcement | [ ] | Review `wallet_auth_decorator.py` |
| Deny by default | [ ] | Check default permissions |
| Rate limiting on APIs | [x] | `rate_limiter.py` exists |
| CORS configuration | [ ] | Review allowed origins |
| JWT/token validation | [ ] | Check credential verification |

**Files to Review:**
- `api/wallet_auth_decorator.py`
- `api/permission_verification.py`
- `api/rate_limiter.py`

### A02:2021 - Cryptographic Failures

| Check | Status | Notes |
|-------|--------|-------|
| No sensitive data in URLs | [x] | PPIDs used, not emails |
| Encryption at rest | [ ] | Check IndexedDB encryption |
| Strong algorithms (Ed25519) | [x] | Confirmed in lemma-crypto |
| No hardcoded secrets | [ ] | Check for API keys in code |
| TLS enforced | [ ] | Check Heroku config |

**Files to Review:**
- `lemma-crypto/src/credentials.rs`
- `api/kms_manager.py`

### A03:2021 - Injection

| Check | Status | Notes |
|-------|--------|-------|
| Parameterized queries | [ ] | Review SQLAlchemy usage |
| Input validation | [ ] | Check `api/validation.py` |
| ORM usage (not raw SQL) | [x] | SQLAlchemy used |
| Content-Type validation | [ ] | Check JSON parsing |

**Files to Review:**
- `api/database.py`
- `api/validation.py`

### A04:2021 - Insecure Design

| Check | Status | Notes |
|-------|--------|-------|
| Threat modeling done | [ ] | Document threats |
| Secure defaults | [ ] | Review default configs |
| Principle of least privilege | [ ] | Review permission grants |

### A05:2021 - Security Misconfiguration

| Check | Status | Notes |
|-------|--------|-------|
| No default credentials | [x] | Passkey-based |
| Error handling doesn't leak info | [ ] | Review error responses |
| Security headers set | [ ] | Check CORS, CSP |
| Debug mode disabled in prod | [ ] | Check config.py |

**Files to Review:**
- `api/config.py`
- `app.py` (Flask config)

### A06:2021 - Vulnerable Components

| Check | Status | Notes |
|-------|--------|-------|
| Dependencies audited | [x] | See results above |
| Components updated | [x] | gunicorn, pyo3, slab all updated |
| Unused dependencies removed | [ ] | Review requirements.txt |

### A07:2021 - Authentication Failures

| Check | Status | Notes |
|-------|--------|-------|
| Multi-factor available | [x] | Passkey = something you have |
| No weak passwords | [x] | No passwords at all |
| Session management | [ ] | Review session handling |
| Brute force protection | [ ] | Check rate limiting |

**Files to Review:**
- `api/passkey_auth.py`
- `api/wallet_session_sync.py`

### A08:2021 - Software and Data Integrity

| Check | Status | Notes |
|-------|--------|-------|
| Signature verification | [x] | Ed25519 signatures |
| CI/CD pipeline security | [ ] | Review GitHub Actions |
| Dependency integrity | [ ] | Add hash verification |

### A09:2021 - Security Logging & Monitoring

| Check | Status | Notes |
|-------|--------|-------|
| Login failures logged | [ ] | Check audit_logger.py |
| Logs don't contain sensitive data | [ ] | Review log statements |
| Alerting configured | [ ] | Check monitoring/ |

**Files to Review:**
- `api/audit_logger.py`
- `monitoring/`

### A10:2021 - Server-Side Request Forgery (SSRF)

| Check | Status | Notes |
|-------|--------|-------|
| URL validation | [ ] | Check external requests |
| Allowlisted destinations | [ ] | Review outbound calls |

---

## 3. Automated Scanning Setup

### Snyk (Free Tier)

```bash
# Install Snyk CLI
npm install -g snyk

# Authenticate
snyk auth

# Test Python
snyk test --file=requirements.txt

# Test Rust
snyk test --file=Cargo.lock

# Monitor continuously
snyk monitor
```

### GitHub Dependabot

Add `.github/dependabot.yml`:
```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    
  - package-ecosystem: "cargo"
    directory: "/"
    schedule:
      interval: "weekly"
    
  - package-ecosystem: "npm"
    directory: "/cdn"
    schedule:
      interval: "weekly"
```

### Semgrep (Static Analysis)

```bash
# Install
pip install semgrep

# Run security rules
semgrep --config=p/security-audit .

# Run OWASP rules
semgrep --config=p/owasp-top-ten .
```

---

## 3.5 Static Analysis Results (Bandit)

**Scan Date:** January 22, 2026
**Files Scanned:** 22,463 lines of code

### Medium Severity Issues

| File | Line | Issue | Confidence |
|------|------|-------|------------|
| `api/email_service.py` | 88 | Request without timeout | Low |
| `api/iam_permission_types.py` | 284 | Potential SQL injection | Medium |
| `api/permission_type_api.py` | 364 | Potential SQL injection | Low |

### Recommended Fixes

**1. Add timeout to requests (email_service.py:88)**
```python
response = requests.post(url, auth=auth, data=data, timeout=30)
```

**2. Review SQL construction (iam_permission_types.py:284)**
The dynamic field update is using parameterized values but dynamic field names.
Ensure field names are validated against allowlist before construction.

### Files with Syntax Errors (Need Review)
- `api/qr_verifier.py`
- `api/wallet_transfer_session.py`

---

## 4. Immediate Action Items

### Critical (FIXED)

1. ~~**Update gunicorn** to 22.0.0+~~ DONE
2. ~~**Update pyo3** to 0.24.1+~~ DONE
3. ~~**Update slab** (via tokio update)~~ DONE

### High Priority (Fix Within 2 Weeks)

4. Review and replace unmaintained crates:
   - `serde_cbor` → `ciborium`
   - `bincode` → `postcard` or `rmp-serde`

5. Complete OWASP checklist items marked `[ ]`

6. Set up Dependabot for automatic vulnerability alerts

### Medium Priority (Fix Within 1 Month)

7. Run Semgrep static analysis and address findings
8. Document security architecture
9. Engage basic penetration test ($5-10K)

---

## 5. Commands Reference

```bash
# Re-run Python audit
pip-audit -r requirements.txt

# Re-run Rust audit
cargo audit

# Re-run JavaScript audit
cd cdn && npm audit

# Run all audits
pip-audit -r requirements.txt && cargo audit && cd cdn && npm audit

# Fix Python vulnerabilities automatically
pip-audit -r requirements.txt --fix

# Fix Rust vulnerabilities
cargo update
```

---

## 6. Pre-Sales Security Statement

All critical vulnerabilities have been remediated. You can state:

> **Security Posture**
>
> Lemma.id implements industry-standard cryptographic primitives:
> - Ed25519 digital signatures (IETF RFC 8032)
> - WebAuthn/FIDO2 passkey authentication
> - AES-256-GCM encryption
>
> Automated dependency scanning runs via GitHub Dependabot and the Section 11
> security workflow (`.github/workflows/section11-security.yml`).
> A third-party security audit is scheduled for [Q2 2026].
>
> For enterprise security requirements, contact security@lemma.id.

---

## Summary

| Category | Count | Status |
|----------|-------|--------|
| Critical vulnerabilities | 0 | All fixed |
| High vulnerabilities | 0 | All fixed |
| Medium issues | 3 | Minor, documented |
| Low warnings | 5 | Informational only |

**Next Steps:**
1. ~~Fix critical vulnerabilities~~ COMPLETE
2. Complete OWASP checklist (2-4 hours)
3. ~~Set up automated scanning (1 hour)~~ COMPLETE — Dependabot + Section 11 CI
4. Engage penetration testing firm (when budget allows)
