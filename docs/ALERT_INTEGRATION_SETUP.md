# Alert Integration Setup Guide

This guide explains how to configure PagerDuty, Slack, and Status Page integrations for Lemma's automated monitoring and alerting system.

## Overview

Lemma's monitoring system implements 5 critical alerts with automated actions:

| Alert | Threshold | Auto-action |
|-------|-----------|-------------|
| Verify error-rate ≥ 1% for 5 min | Notify SRE-OnCall | Create status-page incident |
| P95 latency > 250ms for 15 min | Scale pods / CDN purge | |
| Bloom filter download fail or size > 4× median | Roll back to previous epoch | |
| Billing roll-up misses 02:00 UTC | Page Billing-Ops | |
| Secrets overdue rotation (> 90 d) | Slack #sec-ops | |

## PagerDuty Integration

### 1. Create PagerDuty Service

1. Log into your PagerDuty account
2. Go to **Services** → **Service Directory**
3. Click **+ New Service**
4. Configure:
   - **Name**: `Lemma Enterprise Monitoring`
   - **Description**: `Automated alerts from Lemma verification platform`
   - **Escalation Policy**: Select your SRE on-call policy
   - **Alert Grouping**: `Intelligent` (recommended)
   - **Integration Type**: `Events API v2`

### 2. Get Integration Key

1. After creating the service, go to the **Integrations** tab
2. Find the **Events API v2** integration
3. Copy the **Integration Key** (starts with a long alphanumeric string)

### 3. Configure Environment Variables

```bash
# PagerDuty Configuration
export PAGERDUTY_INTEGRATION_KEY="your_integration_key_here"
export PAGERDUTY_API_TOKEN="your_api_token_here"  # Optional: for advanced features
export PAGERDUTY_SERVICE_ID="your_service_id_here"  # Optional: for service management
```

### 4. Test Integration

```bash
# Test PagerDuty integration
curl -X POST https://your-lemma-instance.com/api/sre/alerts/test-pagerduty \
  -H "X-API-Key: your_api_key"
```

## Slack Integration

### 1. Create Slack Webhooks

#### General Alerts Webhook
1. Go to your Slack workspace
2. Navigate to **Apps** → **Incoming Webhooks**
3. Click **Add to Slack**
4. Select channel: `#sre-alerts` (or your preferred channel)
5. Copy the webhook URL

#### Security Operations Webhook
1. Repeat the process for security alerts
2. Select channel: `#sec-ops`
3. Copy the webhook URL

#### Billing Operations Webhook
1. Repeat the process for billing alerts
2. Select channel: `#billing-ops`
3. Copy the webhook URL

### 2. Configure Environment Variables

```bash
# Slack Configuration
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/GENERAL/WEBHOOK"
export SLACK_SEC_OPS_WEBHOOK="https://hooks.slack.com/services/YOUR/SECOPS/WEBHOOK"
export SLACK_BILLING_OPS_WEBHOOK="https://hooks.slack.com/services/YOUR/BILLING/WEBHOOK"
```

## Status Page Integration

### 1. Create Status Page

1. Sign up for a status page service (e.g., Atlassian Statuspage, StatusPage.io)
2. Create a new status page for your service
3. Note your **Page ID** from the URL or settings

### 2. Generate API Key

1. Go to **API** settings in your status page dashboard
2. Generate a new API key with permissions:
   - Create incidents
   - Update incidents
   - Manage components
3. Copy the API key

### 3. Configure Environment Variables

```bash
# Status Page Configuration
export STATUSPAGE_API_KEY="your_api_key_here"
export STATUSPAGE_PAGE_ID="your_page_id_here"
```

## Complete Environment Configuration

Here's a complete example of all environment variables for alert integrations:

```bash
# Alert Monitoring Configuration
export ALERT_CHECK_INTERVAL=60  # Check interval in seconds (default: 60)

# PagerDuty Integration
export PAGERDUTY_INTEGRATION_KEY="your_pagerduty_integration_key"
export PAGERDUTY_API_TOKEN="your_pagerduty_api_token"
export PAGERDUTY_SERVICE_ID="your_pagerduty_service_id"

# Slack Integration
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/GENERAL/WEBHOOK"
export SLACK_SEC_OPS_WEBHOOK="https://hooks.slack.com/services/YOUR/SECOPS/WEBHOOK"
export SLACK_BILLING_OPS_WEBHOOK="https://hooks.slack.com/services/YOUR/BILLING/WEBHOOK"

# Status Page Integration
export STATUSPAGE_API_KEY="your_statuspage_api_key"
export STATUSPAGE_PAGE_ID="your_statuspage_page_id"
```

## Heroku Deployment

If deploying to Heroku, set these environment variables using the Heroku CLI:

```bash
# PagerDuty
heroku config:set PAGERDUTY_INTEGRATION_KEY="your_integration_key"
heroku config:set PAGERDUTY_API_TOKEN="your_api_token"

# Slack
heroku config:set SLACK_WEBHOOK_URL="your_general_webhook"
heroku config:set SLACK_SEC_OPS_WEBHOOK="your_secops_webhook"
heroku config:set SLACK_BILLING_OPS_WEBHOOK="your_billing_webhook"

# Status Page
heroku config:set STATUSPAGE_API_KEY="your_api_key"
heroku config:set STATUSPAGE_PAGE_ID="your_page_id"

# Alert Configuration
heroku config:set ALERT_CHECK_INTERVAL=60
```

## Testing Your Setup

### 1. Check Monitor Status

```bash
curl https://your-lemma-instance.com/api/sre/alerts/monitor-status \
  -H "X-API-Key: your_api_key"
```

Expected response:
```json
{
  "success": true,
  "monitor_status": {
    "is_running": true,
    "check_interval": 60,
    "active_alerts": 0,
    "thread_alive": true
  },
  "integrations": {
    "pagerduty_configured": true,
    "slack_configured": true,
    "statuspage_configured": true
  }
}
```

### 2. Test PagerDuty Integration

```bash
curl -X POST https://your-lemma-instance.com/api/sre/alerts/test-pagerduty \
  -H "X-API-Key: your_api_key"
```

### 3. View Current Alert Rules

```bash
curl https://your-lemma-instance.com/api/sre/alerts/rules \
  -H "X-API-Key: your_api_key"
```

### 4. Check Active Alerts

```bash
curl https://your-lemma-instance.com/api/sre/alerts/current \
  -H "X-API-Key: your_api_key"
```

## Alert Workflow

### When an Alert Triggers

1. **Detection**: Background monitor detects threshold breach
2. **PagerDuty**: Incident created automatically with details
3. **Auto-Action**: Appropriate automated response executed
4. **Slack**: Team notification sent to relevant channel
5. **Status Page**: Public incident created (for customer-facing issues)

### Alert Resolution

Alerts automatically resolve when conditions return to normal. You can also manually resolve alerts:

```bash
curl -X POST https://your-lemma-instance.com/api/sre/alerts/resolve/alert_id \
  -H "X-API-Key: your_api_key"
```

## Troubleshooting

### Common Issues

1. **PagerDuty incidents not creating**
   - Verify `PAGERDUTY_INTEGRATION_KEY` is correct
   - Check service is active in PagerDuty
   - Review logs for API errors

2. **Slack notifications not sending**
   - Verify webhook URLs are correct
   - Check channel permissions
   - Test webhooks manually with curl

3. **Background monitor not running**
   - Check application logs for startup errors
   - Verify no import errors in monitoring modules
   - Check `/api/sre/alerts/monitor-status` endpoint

### Log Monitoring

Monitor application logs for alert activity:

```bash
# Heroku
heroku logs --tail --app your-app-name | grep -i alert

# Local
tail -f logs/app.log | grep -i alert
```

### Manual Alert Testing

Trigger specific alert conditions for testing:

```bash
# Manually run monitoring cycle
curl -X POST https://your-lemma-instance.com/api/sre/alerts/run-check \
  -H "X-API-Key: your_api_key"
```

## Security Considerations

1. **API Keys**: Store all integration keys securely as environment variables
2. **Webhook URLs**: Treat Slack webhook URLs as secrets
3. **Access Control**: Limit who can access alert management endpoints
4. **Audit Trail**: All alert actions are logged for security auditing

## Support

For issues with alert integrations:

1. Check the troubleshooting section above
2. Review application logs for error messages
3. Test individual integrations using the provided curl commands
4. Contact your SRE team for PagerDuty/Slack configuration issues 