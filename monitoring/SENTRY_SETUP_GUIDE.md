# 🔍 Sentry Error Monitoring - Setup Guide

## Quick Setup (5 minutes)

### 1. Sign Up for Sentry

1. Go to https://sentry.io
2. Sign up (free tier: 5,000 errors/month)
3. Create new project:
   - Platform: **Flask**
   - Project name: **lemma-iam**

### 2. Get Your DSN

After creating the project, Sentry will show you a DSN like:
```
https://abc123def456@o123456.ingest.sentry.io/7890123
```

### 3. Add to Heroku

```bash
heroku config:set SENTRY_DSN=https://abc123def456@o123456.ingest.sentry.io/7890123
```

### 4. Deploy & Test

```bash
# Deploy to Heroku
git add .
git commit -m "Add Sentry error monitoring"
git push heroku heroku-deploy:main

# Test error tracking
curl https://your-app.herokuapp.com/test-error

# Check Sentry dashboard - you should see the error!
```

---

## What Sentry Captures

### Automatic Capture:
- ✅ **Uncaught exceptions** (500 errors)
- ✅ **Stack traces** with full context
- ✅ **Request data** (URL, method, headers)
- ✅ **User context** (IP, user agent)
- ✅ **Performance data** (slow requests)

### Manual Capture:
```python
from monitoring.sentry_config import capture_exception, capture_message

try:
    risky_operation()
except Exception as e:
    capture_exception(e, context={
        'user_email': 'user@example.com',
        'site_id': 'site_123'
    })
    raise

# Or capture custom messages
capture_message('Suspicious activity detected', level='warning')
```

---

## Alerts & Notifications

### Set Up Email Alerts

1. Go to Sentry project settings
2. Navigate to **Alerts** → **Create Alert Rule**
3. Configure:
   - **When**: An event is seen
   - **Conditions**: Is first seen OR seen more than 10 times
   - **Then**: Send email to your@email.com

### Slack Integration (Optional)

1. In Sentry: **Settings** → **Integrations** → **Slack**
2. Authorize Slack workspace
3. Create alert rule to post to #alerts channel

---

## Monitoring Dashboard

### Key Metrics to Watch:

1. **Error Rate**: Should be <1% of requests
2. **Response Time**: p95 should be <200ms
3. **Throughput**: Requests per second
4. **Top Errors**: Most frequent issues

### Access Dashboard:
https://sentry.io/organizations/your-org/issues/

---

## Performance Monitoring

Sentry captures 10% of requests for performance tracking:

```python
# In app.py, this is already configured:
traces_sample_rate=0.1  # 10% of requests
```

View performance data:
- **Performance** tab in Sentry
- See slowest endpoints
- Database query performance
- External API calls

---

## Filtering Noise

Already configured to ignore:
- Missing API key errors (user error, not bug)
- Rate limit errors (expected behavior)
- Common user mistakes

Add more filters in `monitoring/sentry_config.py`:
```python
def before_send_handler(event, hint):
    # Filter out specific errors
    if 'some_noisy_error' in str(exc_value):
        return None  # Don't send to Sentry
    return event
```

---

## Cost Management

**Free Tier Limits:**
- 5,000 errors/month
- 10,000 performance events/month

**If you exceed:**
- Upgrade to paid plan ($26/month for 50K errors)
- Or adjust sample rate:
  ```python
  traces_sample_rate=0.05  # 5% instead of 10%
  ```

---

## Troubleshooting

### No Errors Appearing?

1. Check DSN is set:
   ```bash
   heroku config:get SENTRY_DSN
   ```

2. Check logs for initialization message:
   ```bash
   heroku logs --tail | grep Sentry
   ```
   Should see: `✅ Sentry initialized successfully`

3. Test manually:
   ```python
   from monitoring.sentry_config import capture_message
   capture_message('Test message from Heroku')
   ```

### Too Many Errors?

1. Check if same error repeating
2. Fix the root cause first
3. Or use "Ignore" button in Sentry to silence

---

## Best Practices

### DO:
- ✅ Check Sentry daily during launch week
- ✅ Set up email alerts for critical errors
- ✅ Fix errors with >10 occurrences first
- ✅ Use custom context for debugging

### DON'T:
- ❌ Ignore all errors (defeats the purpose)
- ❌ Send PII (user passwords, credit cards)
- ❌ Spam Sentry with expected errors

---

## Success Checklist

- [ ] Sentry account created
- [ ] Project created for lemma-iam
- [ ] DSN added to Heroku config
- [ ] Code deployed
- [ ] Test error captured in Sentry
- [ ] Email alerts configured
- [ ] Checked dashboard daily

**Estimated Setup Time: 5-10 minutes**

Once this is done, you'll know immediately when something breaks in production! 🚀

