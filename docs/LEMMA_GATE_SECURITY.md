# Lemma Gate Security Guide

## 🔒 **Critical Security Principle**

**The Lemma Gate is a UX enhancement layer, NOT a security boundary.**

Any sensitive content or operations MUST be protected by server-side verification. Never trust client-side verification status for security decisions.

---

## ⚠️ **Security Vulnerabilities to Avoid**

### **1. CLIENT-SIDE SECURITY BOUNDARY (CRITICAL)**

❌ **NEVER DO THIS:**
```html
<!-- VULNERABLE: Sensitive content in initial HTML -->
<div id="protected-content" style="display: none;">
    <h1>Secret API Key: sk_live_1234567890</h1>
    <p>Classified information here...</p>
</div>

<script>
// VULNERABLE: Trusting client-side verification
if (lemmaGate.isVerified) {
    showProtectedContent(); // Content already in DOM!
}
</script>
```

**Why this is dangerous:**
- Users can view page source and see hidden content
- JavaScript can be disabled or manipulated
- Browser dev tools can unhide elements
- Content is accessible before verification

### **2. SESSION-ONLY SECURITY (DANGEROUS)**

❌ **NEVER DO THIS:**
```python
# VULNERABLE: Only checking session, not re-verifying
@app.route('/api/sensitive-data')
def get_sensitive_data():
    if session.get('verified_human'):  # Not enough!
        return {"secret": "classified data"}
    return {"error": "Unauthorized"}, 401
```

**Why this is dangerous:**
- Session can be hijacked
- No verification of current credential status
- Revoked credentials still work
- No protection against replay attacks

---

## ✅ **Secure Implementation Patterns**

### **1. Server-Delivered Content After Verification**

```html
<!-- SECURE: No sensitive content in initial HTML -->
<div id="lemma-gate"></div>
<div id="protected-content">
    <div class="loading">Verifying access...</div>
</div>

<script src="/static/js/lemma-gate-secure.js"></script>
```

```python
# SECURE: Always verify before delivering content
@app.route('/api/protected-content')
def get_protected_content():
    # 1. Check session
    if not session.get('verified_human'):
        return {"error": "Not verified"}, 401
    
    # 2. Re-verify credential is still valid
    credential_id = session.get('credential_id')
    if not verify_credential_still_valid(credential_id):
        session.clear()
        return {"error": "Credential invalid"}, 401
    
    # 3. Check revocation status
    if is_credential_revoked(credential_id):
        session.clear()
        return {"error": "Credential revoked"}, 401
    
    # 4. Return content
    return render_template('protected_content.html')
```

### **2. Multi-Layer Verification**

```python
# SECURE: Comprehensive verification endpoint
@app.route('/api/verify-human', methods=['POST'])
def verify_human():
    data = request.get_json()
    presentation = data.get('presentation')
    challenge = data.get('challenge')
    security_token = data.get('securityToken')
    
    # 1. Validate request format
    if not presentation or not challenge:
        log_security_event('invalid_verification_request', request.remote_addr)
        return {"error": "Invalid request"}, 400
    
    # 2. Verify security token (prevent replay)
    if not verify_security_token(security_token):
        log_security_event('invalid_security_token', request.remote_addr)
        return {"error": "Invalid security token"}, 400
    
    # 3. Cryptographically verify presentation
    verification_result = verify_lemma_presentation(presentation, challenge)
    
    if not verification_result.valid:
        log_security_event('verification_failed', {
            'ip': request.remote_addr,
            'reason': verification_result.reason
        })
        return {"error": "Verification failed"}, 401
    
    # 4. Check credential is not revoked
    if is_credential_revoked(verification_result.credential_id):
        log_security_event('revoked_credential_used', {
            'credential_id': verification_result.credential_id,
            'ip': request.remote_addr
        })
        return {"error": "Credential revoked"}, 401
    
    # 5. Set secure session
    session.regenerate()  # Prevent session fixation
    session['verified_human'] = True
    session['credential_id'] = verification_result.credential_id
    session['verification_time'] = time.time()
    session['verification_ip'] = request.remote_addr
    
    # 6. Log successful verification
    log_security_event('verification_success', {
        'credential_id': verification_result.credential_id,
        'user_id': verification_result.user_id,
        'ip': request.remote_addr
    })
    
    return {"success": True, "verified": True}
```

### **3. Secure API Endpoints**

```python
# SECURE: Verification decorator for API endpoints
def require_lemma_verification(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. Check session exists
        if not session.get('verified_human'):
            return {"error": "Verification required"}, 401
        
        # 2. Check session age (prevent stale sessions)
        verification_time = session.get('verification_time', 0)
        if time.time() - verification_time > 3600:  # 1 hour max
            session.clear()
            return {"error": "Session expired"}, 401
        
        # 3. Check IP consistency (prevent session hijacking)
        if session.get('verification_ip') != request.remote_addr:
            session.clear()
            log_security_event('session_hijacking_attempt', request.remote_addr)
            return {"error": "Session invalid"}, 401
        
        # 4. Re-verify credential on sensitive operations
        if request.method in ['POST', 'PUT', 'DELETE']:
            credential_id = session.get('credential_id')
            if not verify_credential_still_valid(credential_id):
                session.clear()
                return {"error": "Credential no longer valid"}, 401
        
        return f(*args, **kwargs)
    return decorated_function

# Usage
@app.route('/api/sensitive-operation', methods=['POST'])
@require_lemma_verification
def sensitive_operation():
    # This will only execute if verification passes all checks
    return {"result": "success"}
```

---

## 🛡️ **Security Hardening Measures**

### **1. Content Security Policy (CSP)**

```python
# Add CSP headers to prevent XSS and injection
@app.after_request
def add_security_headers(response):
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'"
    )
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response
```

### **2. Rate Limiting and Abuse Prevention**

```python
from flask_limiter import Limiter

limiter = Limiter(
    app,
    key_func=lambda: request.remote_addr,
    default_limits=["100 per hour"]
)

@app.route('/api/verify-human', methods=['POST'])
@limiter.limit("5 per minute")  # Strict limit on verification attempts
def verify_human():
    # ... verification logic
```

### **3. Security Event Logging**

```python
def log_security_event(event_type, data):
    """Log security events for monitoring and alerting."""
    event = {
        'timestamp': datetime.utcnow().isoformat(),
        'event_type': event_type,
        'ip_address': request.remote_addr if request else None,
        'user_agent': request.headers.get('User-Agent') if request else None,
        'data': data
    }
    
    # Store in secure log file
    with open('/var/log/lemma/security.log', 'a') as f:
        f.write(json.dumps(event) + '\n')
    
    # Send critical events to monitoring system
    if event_type in ['verification_failed', 'session_hijacking_attempt', 'revoked_credential_used']:
        send_security_alert(event)
```

### **4. Credential Revocation Checking**

```python
def verify_credential_still_valid(credential_id):
    """Verify credential is still valid and not revoked."""
    try:
        # 1. Check local revocation cache
        if is_in_revocation_cache(credential_id):
            return False
        
        # 2. Check with OPRF service
        revocation_status = check_oprf_revocation(credential_id)
        if revocation_status.revoked:
            cache_revocation(credential_id)
            return False
        
        # 3. Verify credential format and signature
        credential = get_credential(credential_id)
        if not verify_credential_signature(credential):
            return False
        
        # 4. Check expiration
        if is_credential_expired(credential):
            return False
        
        return True
        
    except Exception as e:
        log_security_event('credential_verification_error', str(e))
        return False  # Fail secure
```

---

## 🚨 **Security Monitoring and Alerting**

### **1. Real-Time Monitoring**

```python
# Monitor for suspicious patterns
def monitor_verification_patterns():
    """Monitor for suspicious verification patterns."""
    
    # Check for rapid verification attempts from same IP
    recent_attempts = get_recent_verification_attempts(
        minutes=5, 
        ip=request.remote_addr
    )
    
    if len(recent_attempts) > 10:
        log_security_event('rapid_verification_attempts', {
            'ip': request.remote_addr,
            'attempts': len(recent_attempts)
        })
        return False
    
    # Check for revoked credentials being repeatedly used
    if is_using_revoked_credential_repeatedly(request.remote_addr):
        log_security_event('repeated_revoked_credential_use', {
            'ip': request.remote_addr
        })
        return False
    
    return True
```

### **2. Automated Response**

```python
# Automatic security responses
def handle_security_threat(threat_type, data):
    """Automatically respond to security threats."""
    
    if threat_type == 'session_hijacking_attempt':
        # Invalidate all sessions for this user
        invalidate_user_sessions(data.get('user_id'))
        
    elif threat_type == 'rapid_verification_attempts':
        # Temporarily block IP
        block_ip_temporarily(data.get('ip'), minutes=30)
        
    elif threat_type == 'revoked_credential_used':
        # Alert security team
        send_security_alert(f"Revoked credential {data.get('credential_id')} used")
```

---

## 📋 **Security Checklist**

### **Pre-Deployment Security Checklist**

- [ ] **No sensitive content in initial HTML**
- [ ] **All protected endpoints verify server-side**
- [ ] **Session management is secure (regeneration, expiration, IP checking)**
- [ ] **CSRF protection enabled**
- [ ] **Rate limiting implemented**
- [ ] **Security headers configured**
- [ ] **Logging and monitoring in place**
- [ ] **Credential revocation checking enabled**
- [ ] **Error handling doesn't leak information**
- [ ] **Security testing completed**

### **Runtime Security Monitoring**

- [ ] **Monitor verification failure rates**
- [ ] **Alert on rapid verification attempts**
- [ ] **Track session hijacking attempts**
- [ ] **Monitor for revoked credential usage**
- [ ] **Watch for unusual access patterns**
- [ ] **Regular security log reviews**

---

## 🎯 **Summary: Secure Gate Implementation**

**The Lemma Gate provides excellent UX when implemented securely:**

1. **Gate handles UX flow** - Seamless verification experience
2. **Server enforces security** - All access control decisions made server-side
3. **Content delivered after verification** - No sensitive data in client until verified
4. **Comprehensive monitoring** - Track and respond to security events
5. **Defense in depth** - Multiple layers of verification and validation

**Remember: The gate is a door, not a vault. The vault is your server-side verification.** 