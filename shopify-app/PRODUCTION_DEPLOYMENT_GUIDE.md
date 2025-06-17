# Lemma Shopify App - Production Deployment Guide

## 📋 Overview
This guide covers deploying the Lemma Human Verification Shopify app to production, ready for real merchant use.

## 🚀 Production Checklist

### ✅ Prerequisites Completed
- [x] Lemma API operational at `https://lemma-enterprise-0f6ba17076c1.herokuapp.com`
- [x] Core verification endpoints tested and working
- [x] Basic merchant dashboard created
- [x] Verification widget functional
- [x] End-to-end flow tested

### 🔧 Pre-Deployment Requirements

#### 1. Environment Configuration
```bash
# Required environment variables
LEMMA_API_KEY=your_api_key_here
LEMMA_BASE_URL=https://lemma-enterprise-0f6ba17076c1.herokuapp.com
SHOPIFY_API_KEY=your_shopify_partner_app_key
SHOPIFY_API_SECRET=your_shopify_partner_app_secret
SHOPIFY_APP_URL=https://your-deployed-app.herokuapp.com
NODE_ENV=production
PORT=3000
```

#### 2. Shopify Partner Configuration
- [x] Create Shopify Partner account
- [x] Register new Shopify app
- [x] Configure OAuth scopes: `read_customers`, `write_customers`, `read_orders`, `write_orders`
- [x] Set app URL to your deployed domain
- [x] Configure webhook endpoints

## 🌐 Deployment Options

### Option 1: Heroku Deployment (Recommended)

#### Step 1: Prepare App for Heroku
```bash
# Ensure package.json has start script
{
  "scripts": {
    "start": "node simple-app.js"
  }
}

# Create Procfile
echo "web: node simple-app.js" > Procfile
```

#### Step 2: Deploy to Heroku
```bash
# Login to Heroku
heroku login

# Create new app
heroku create your-lemma-shopify-app

# Set environment variables
heroku config:set LEMMA_API_KEY=your_api_key
heroku config:set LEMMA_BASE_URL=https://lemma-enterprise-0f6ba17076c1.herokuapp.com
heroku config:set SHOPIFY_API_KEY=your_shopify_key
heroku config:set SHOPIFY_API_SECRET=your_shopify_secret
heroku config:set SHOPIFY_APP_URL=https://your-lemma-shopify-app.herokuapp.com
heroku config:set NODE_ENV=production

# Deploy
git add .
git commit -m "Production deployment"
git push heroku main
```

### Option 2: Alternative Hosting

#### Vercel
```bash
npm install -g vercel
vercel --prod
```

#### Railway
```bash
npm install -g @railway/cli
railway login
railway deploy
```

## 🧪 Production Testing

### Essential Endpoint Tests
```bash
# Health check
curl https://your-app.herokuapp.com/health

# Dashboard
curl https://your-app.herokuapp.com/

# Widget
curl https://your-app.herokuapp.com/widget

# API status
curl https://your-app.herokuapp.com/api/status
```

### Integration Testing
```bash
# Run production test suite
cd shopify-app
npm test

# Test Lemma connectivity
node -e "
const fetch = require('node-fetch');
fetch('https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/health')
  .then(r => r.json())
  .then(d => console.log('Lemma Status:', d))
  .catch(e => console.error('Error:', e));
"
```

## 📊 Production Monitoring

### Health Checks
- **App Health**: `GET /health`
  - Should return 200 with `{"status": "healthy"}`
- **Lemma Connectivity**: `GET /api/status`
  - Should return `{"lemma_healthy": true}`

### Key Metrics to Monitor
1. **Uptime**: App availability (target: >99.5%)
2. **Response Time**: API endpoints (target: <2s)
3. **Error Rate**: Failed requests (target: <1%)
4. **Verification Success**: Widget completion rate

### Logging
```javascript
// Production logging setup
const winston = require('winston');
const logger = winston.createLogger({
  level: 'info',
  format: winston.format.json(),
  transports: [
    new winston.transports.File({ filename: 'error.log', level: 'error' }),
    new winston.transports.File({ filename: 'combined.log' })
  ]
});
```

## 🔒 Security Considerations

### Required Security Measures
- [x] HTTPS enforcement
- [x] Environment variables for secrets
- [x] CORS configuration
- [x] Rate limiting on API endpoints
- [x] Input validation and sanitization

### Security Headers
```javascript
app.use((req, res, next) => {
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('X-Frame-Options', 'DENY');
  res.setHeader('X-XSS-Protection', '1; mode=block');
  next();
});
```

## 📈 Performance Optimization

### Caching Strategy
```javascript
// Cache static assets
app.use(express.static('public', {
  maxAge: '1d',
  etag: true
}));

// Cache API responses where appropriate
const cache = new Map();
app.get('/api/dashboard', async (req, res) => {
  const cacheKey = `dashboard-${req.shop}`;
  if (cache.has(cacheKey)) {
    return res.json(cache.get(cacheKey));
  }
  // ... fetch fresh data and cache
});
```

### Database Connection Pooling
```javascript
// For production database integration
const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  max: 20,
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 2000,
});
```

## 🛡️ Disaster Recovery

### Backup Strategy
1. **Environment Variables**: Store in secure password manager
2. **Configuration**: Version controlled in git
3. **Data**: Leverage Lemma's data redundancy
4. **Logs**: Centralized logging service

### Rollback Plan
```bash
# Quick rollback to previous version
heroku rollback v123

# Or redeploy from specific commit
git checkout <previous-commit>
git push heroku main --force
```

## 📞 Support and Maintenance

### Monitoring Tools
- **Heroku Metrics**: Built-in app metrics
- **New Relic**: Application performance monitoring
- **Sentry**: Error tracking and reporting
- **UptimeRobot**: External uptime monitoring

### Maintenance Schedule
- **Daily**: Check error logs and uptime metrics
- **Weekly**: Review performance metrics and optimization opportunities
- **Monthly**: Security updates and dependency updates
- **Quarterly**: Full system health review

## 🎯 Success Criteria

### Launch Readiness Checklist
- [x] ✅ App deployed and accessible
- [x] ✅ All endpoints returning correct responses
- [x] ✅ Widget loads and functions properly
- [x] ✅ Lemma API integration working
- [x] ✅ Environment variables configured
- [x] ✅ Security headers implemented
- [x] ✅ Monitoring in place

### Post-Launch Metrics (First 30 Days)
- **Target Uptime**: >99.5%
- **Average Response Time**: <2 seconds
- **Widget Load Success**: >95%
- **Verification Completion**: >80%
- **Merchant Satisfaction**: >4.5/5 stars

## 🚨 Troubleshooting

### Common Issues

#### App Won't Start
```bash
# Check logs
heroku logs --tail

# Common fixes
heroku config:set NODE_ENV=production
heroku restart
```

#### Widget Not Loading
```bash
# Check CORS settings
# Verify LEMMA_BASE_URL is correct
# Test widget endpoint directly
curl https://your-app.herokuapp.com/widget
```

#### Lemma API Connection Issues
```bash
# Test connectivity
curl https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/health

# Check API key
heroku config:get LEMMA_API_KEY
```

## 📝 Final Notes

This deployment guide ensures the Lemma Shopify app is production-ready with:
- ✅ Simple but robust architecture
- ✅ Essential monitoring and logging
- ✅ Security best practices
- ✅ Scalable infrastructure
- ✅ Clear maintenance procedures

The app is designed to be **simple and reliable** - focusing on the core human verification functionality without over-engineering.

---

📞 **Support**: For deployment issues, contact the development team
📚 **Documentation**: [API Reference](https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/docs)
🔍 **Monitoring**: [Status Page](https://status.lemma.network) 