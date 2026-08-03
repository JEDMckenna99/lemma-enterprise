# ⏱️ Uptime Monitoring - Quick Setup Guide

## Why You Need This

Know immediately when your site goes down:
- Get email/SMS alerts within 5 minutes
- Track uptime percentage (need 99.9% for SLA)
- Historical downtime reports
- Status page for customers

---

## Setup (10 minutes)

### Option 1: UptimeRobot (Recommended - Free)

**1. Sign Up**
- Go to https://uptimerobot.com
- Sign up for free account
- Free tier: 50 monitors, 5-minute checks

**2. Create Monitors**

**Monitor 1: Liveness (`/health`)**
- Monitor Type: HTTP(S)
- Friendly Name: "Lemma IAM - Liveness"
- URL: `https://lemma.id/health`
- Monitoring Interval: 5 minutes
- Monitor Timeout: 30 seconds
- Alert When Down For: 5 minutes (1 check)
- Expected: HTTP 200, body contains `"status":"healthy"` (no dependency probes)

**Monitor 2: Readiness (`/ready`)**
- Monitor Type: HTTP(S)
- Friendly Name: "Lemma IAM - Readiness"
- URL: `https://lemma.id/ready`
- Monitoring Interval: 5 minutes
- Alert When Down For: 10 minutes (2 checks)
- Expected: HTTP 200 with `"ready":true` when dependencies healthy

**Monitor 3: Revocation bloom**
- Monitor Type: HTTP(S)
- Friendly Name: "Lemma IAM - Bloom Filter"
- URL: `https://lemma.id/api/revocation/bloom-filter`
- Monitoring Interval: 15 minutes

**3. Set Up Alerts**
- Email: Your email address
- SMS: Optional (5 SMS/month on free tier)
- Slack: Optional (webhook integration)
- Webhook: Optional (for PagerDuty, etc.)

**4. Create Status Page**
- Public status page: `https://status.lemma.id`
- Shows current uptime for liveness + readiness monitors
- Incident history
- Required for Section 9 customer-facing status commitment

---

### Option 2: Pingdom (Alternative)

- Go to https://www.pingdom.com
- Free trial, then $10/month for basic
- Similar setup to UptimeRobot
- Better reporting features

---

## Health Check Endpoint

These endpoints already exist in `app.py`:

- `GET /health` — process liveness probe, no dependency checks (`api/operational_readiness.liveness_payload`)
- `GET /ready` — dependency-aware readiness probe (`api/operational_readiness.readiness_report`)
- `GET /api/health` — detailed system health (`api/health_check.get_health_status`; 503 critical, 206 degraded)

Point uptime monitors at `/health` for liveness and `/ready` for dependency checks.

<details>
<summary>Historical example (superseded by the real endpoints above)</summary>

```python
@app.route('/health')
def health_check():
    """
    Health check endpoint for uptime monitoring
    Returns 200 if everything is working
    """
    try:
        # Check database connection
        from api.database import SessionLocal
        SessionLocal().execute('SELECT 1')
        
        # Check Redis connection
        import redis
        redis_client = redis.from_url(os.getenv('REDIS_URL'))
        redis_client.ping()
        
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'version': os.getenv('HEROKU_SLUG_COMMIT', 'unknown')[:8]
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500


@app.route('/ready')
def readiness_check():
    """
    Readiness check - is the app ready to serve traffic?
    More detailed than health check
    """
    checks = {
        'database': False,
        'redis': False,
        'crypto_engine': False
    }
    
    try:
        # Check database
        from api.database import SessionLocal
        SessionLocal().execute('SELECT 1')
        checks['database'] = True
    except:
        pass
    
    try:
        # Check Redis
        import redis
        redis_client = redis.from_url(os.getenv('REDIS_URL'))
        redis_client.ping()
        checks['redis'] = True
    except:
        pass
    
    try:
        # Check Rust crypto engine
        from lemma_crypto import PyMinimalVerifier
        verifier = PyMinimalVerifier()
        checks['crypto_engine'] = True
    except:
        pass
    
    all_healthy = all(checks.values())
    status_code = 200 if all_healthy else 503
    
    return jsonify({
        'ready': all_healthy,
        'checks': checks,
        'timestamp': datetime.now().isoformat()
    }), status_code
```

</details>

---

## Alert Configuration

### Email Alerts
- **Always On:** Get email for every downtime
- **Threshold:** Alert after 1 failed check (5 minutes down)
- **Recipients:** Your email + team email

### SMS Alerts (Optional)
- **Critical Only:** Only for >15 minute outages
- **Limit:** Free tier = 5 SMS/month
- **Use For:** Nighttime/weekend alerts

### Slack Integration (Recommended)
1. Create Slack app
2. Add incoming webhook
3. Paste webhook URL in UptimeRobot
4. Alerts posted to #alerts channel

---

## What to Monitor

### Critical (Must Monitor)
- `/health` - Overall system health
- Main domain loading
- Database connectivity

### Important (Should Monitor)
- `/api/v1/auth/verify` - Core functionality
- `/dashboard` - Customer-facing UI
- `/oauth/authorize` - OAuth flow

### Nice to Have
- API response time (keyword monitoring)
- Geographic checks (multi-region)
- SSL certificate expiry

---

## Response Time SLA

**Your Uptime Goals:**

| Tier | Uptime SLA | Max Downtime/Month | Max Downtime/Year |
|------|------------|-------------------|------------------|
| **Free** | Best effort | N/A | N/A |
| **Starter** | 99.5% | 3.6 hours | 43.8 hours |
| **Pro** | 99.9% | 43 minutes | 8.7 hours |
| **Enterprise** | 99.95% | 21 minutes | 4.4 hours |

**Current Heroku Standard Dyno:** ~99.95% uptime

---

## Incident Response Plan

### When You Get an Alert:

**1. Immediate (< 5 minutes):**
- Check Heroku status: https://status.heroku.com
- Check app logs: `heroku logs --tail`
- Check Sentry for recent errors

**2. Investigation (5-15 minutes):**
- Is it a real outage or monitoring issue?
- Check database: Is PostgreSQL up?
- Check Redis: Is it responding?
- Recent deploys: Did something break?

**3. Resolution:**
- Quick fix: Restart dyno (`heroku restart`)
- Rollback: `heroku rollback` (if recent deploy broke it)
- Emergency: Scale down/up (`heroku ps:scale web=0` then `web=1`)

**4. Post-Incident:**
- Update status page
- Write incident report
- Fix root cause
- Update monitoring to catch it earlier next time

---

## Status Page (Optional but Recommended)

**Why:**
- Transparency with customers
- Reduces support tickets ("Is it down?")
- Shows reliability over time

**How:**
1. UptimeRobot: Settings → Public Status Pages
2. Create page
3. Add all monitors
4. Customize branding
5. Get URL: `https://status-lemmaiam.uptime.com`
6. Add to your docs: "Status: https://status.lemma.id"

**Or use custom domain:**
- Create CNAME: `status.lemma.id` → `stats.uptimerobot.com`
- Configure in UptimeRobot settings

---

## Testing

### Test Your Monitoring:

**1. Test health check locally:**
```bash
curl http://localhost:5000/health
# Should return: {"status": "healthy", ...}
```

**2. Test on Heroku:**
```bash
curl https://your-app.herokuapp.com/health
# Should return 200 with healthy status
```

**3. Trigger a test alert:**
- In UptimeRobot, click monitor → "Force Down"
- Wait 5 minutes
- You should get an email alert
- Mark as "Force Up" to clear

---

## Success Checklist

- [ ] UptimeRobot account created
- [ ] `/health` endpoint deployed
- [ ] `/ready` endpoint deployed
- [ ] 3 monitors configured (health, API, dashboard)
- [ ] Email alerts set up
- [ ] Slack integration (optional)
- [ ] Test alert received
- [ ] Status page created (optional)
- [ ] Incident response plan documented

**Setup Time: 10-15 minutes**

**Once done, you'll know within 5 minutes if your site goes down!** ⏱️

