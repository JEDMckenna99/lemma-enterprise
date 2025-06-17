# 🛡️ Lemma Human Verification for Shopify

**Protect your Shopify store from bots while providing a seamless customer experience**

This Shopify app integrates with the Lemma Verification Network to provide enterprise-grade bot protection with privacy-first human verification.

## 🎯 Key Features

- **🤖 Bot Protection**: Block automated accounts and fraudulent orders
- **💰 Network Pricing**: $2.50 one-time verification + $0.045-0.10/month (decreases as network grows)
- **🔒 Privacy First**: No personal data stored - only verifies humanity
- **⚡ Seamless UX**: Background verification with conditional UI
- **🌐 Network Benefits**: One verification works across all Lemma-integrated stores
- **📊 Real-time Analytics**: Track verified customers, blocked bots, and costs

## 🚀 Quick Start

### 1. Prerequisites

- Node.js 16+ and npm 8+
- Shopify Partner account
- Lemma API key (get one at [lemma.network](https://lemma-enterprise-0f6ba17076c1.herokuapp.com))

### 2. Installation

```bash
# Clone the repository
git clone https://github.com/lemma-network/shopify-app.git
cd shopify-app

# Install dependencies
npm install

# Copy environment configuration
cp env.example .env

# Configure your environment variables
nano .env
```

### 3. Configuration

Update your `.env` file with your credentials:

```bash
# Shopify App Configuration
SHOPIFY_API_KEY=your_shopify_api_key
SHOPIFY_API_SECRET=your_shopify_api_secret
SHOPIFY_APP_URL=https://your-app-domain.com

# Lemma Configuration
LEMMA_API_KEY=your_lemma_api_key
LEMMA_BASE_URL=https://lemma-enterprise-0f6ba17076c1.herokuapp.com
LEMMA_ONBOARDING_FEE=2.50

# App Configuration
PORT=3000
NODE_ENV=development
```

### 4. Development

```bash
# Start development server
npm run dev

# The app will be available at http://localhost:3000
```

### 5. Shopify App Setup

1. Create a new app in your Shopify Partner dashboard
2. Set the app URL to your deployed domain
3. Configure the following scopes:
   - `read_customers`, `write_customers`
   - `read_orders`, `write_orders`
   - `read_products`, `write_products`
   - `read_script_tags`, `write_script_tags`

## 🏗️ Architecture

### Backend Components

- **`app.js`**: Main Express server with Shopify integration
- **`services/lemma-verification-service.js`**: Core Lemma API integration
- **`public/scripts/lemma-shield.js`**: Frontend Shield integration

### Frontend Integration

The app automatically installs a script tag on the storefront that:

1. **Background Monitoring**: Checks verification status continuously
2. **Conditional UI**: Only shows verification prompt when needed
3. **Bot Detection**: Monitors for suspicious behavior patterns
4. **Checkout Protection**: Prevents unverified users from completing orders

### API Integration

```javascript
// Example: Check customer verification
const verificationStatus = await lemmaService.checkCustomerVerification(
  customer.email, 
  shop.domain
);

if (!verificationStatus.verified) {
  // Customer needs verification
  await lemmaService.createCustomerVerificationEntry(customer, shop);
}
```

## 📊 Dashboard Features

The app provides a comprehensive dashboard showing:

- **✅ Setup Status**: Integration health and configuration
- **📈 Statistics**: Verified customers, blocked bots, monthly costs
- **💰 Pricing**: Real-time network pricing with cost predictions
- **🔧 Actions**: Setup check, verification testing, log viewing

## 🔌 API Endpoints

### Customer Management
- `POST /webhooks/customers/create` - Handle new customer creation
- `POST /webhooks/orders/create` - Verify customers during order creation

### Dashboard API
- `GET /api/dashboard` - Get shop statistics and metrics
- `POST /api/check-setup` - Verify integration setup
- `POST /api/test-verification` - Test verification workflow

### Lemma Integration
- `POST /lemma-callback` - Handle completed verifications
- Automatic integration with Lemma Shield API endpoints

## 🛡️ Security Features

### Bot Detection
- Rapid clicking detection
- Mouse movement analysis
- Suspicious user agent identification
- Behavioral pattern monitoring

### Privacy Protection
- Email-to-userID hashing (SHA-256)
- No personal data storage
- GDPR/CCPA compliant
- Zero-knowledge verification

### Verification Workflow
1. Customer visits store
2. Shield checks verification status
3. If unverified, shows optional verification prompt
4. Customer pays $2.50 one-time fee for network access
5. Verification works across all Lemma-integrated stores

## 💰 Pricing Model

### Network Effect Pricing
- **One-time fee**: $2.50 per new customer to the network
- **Monthly rate**: $0.045-0.10 per verified customer
- **Rate decreases** as more businesses join the network
- **Cost projection**: 1000 customers = ~$45-100/month

### Comparison to Alternatives
- **reCAPTCHA Enterprise**: $1-3 per 1,000 verifications
- **Arkose Labs**: $0.50-2.00 per challenge
- **Lemma advantage**: 95%+ cost reduction with better UX

## 🚀 Deployment

### Heroku (Recommended)

```bash
# Create Heroku app
heroku create your-lemma-shopify-app

# Set environment variables
heroku config:set SHOPIFY_API_KEY=your_key
heroku config:set LEMMA_API_KEY=your_lemma_key
# ... (set all required variables)

# Deploy
git push heroku main

# Scale
heroku ps:scale web=1
```

### Other Platforms

The app is compatible with:
- **Vercel**: Add environment variables and deploy
- **Railway**: Connect repository and configure environment
- **DigitalOcean**: Use App Platform or Droplets
- **AWS/Azure**: Deploy via container or traditional hosting

## 🔧 Customization

### Styling the Verification Modal

Edit `public/scripts/lemma-shield.js` to customize the verification prompt:

```javascript
// Customize modal appearance
content.innerHTML = `
  <div style="background: your-brand-color;">
    <h2>Your Store Name - Human Verification</h2>
    <!-- Custom content -->
  </div>
`;
```

### Custom Event Handling

```javascript
window.LemmaShield = new LemmaShield({
  onVerified: function(proof) {
    // Customer verified - enable store features
    console.log('Customer verified!');
    showPremiumFeatures();
  },
  onUnverified: function() {
    // Customer needs verification
    console.log('Customer needs verification');
    showBasicFeatures();
  }
});
```

## 📈 Analytics & Monitoring

### Built-in Metrics
- Verified customer count
- Bot detection events
- Monthly cost tracking
- Verification success rates

### External Integration
- Compatible with Google Analytics
- Shopify Analytics integration
- Custom event tracking available

## 🆘 Troubleshooting

### Common Issues

**1. Verification not working**
```bash
# Check setup status
npm run test
# Or visit /api/check-setup in your app
```

**2. Script not loading**
- Verify script tag installation in Shopify admin
- Check browser console for errors
- Ensure API key is correct

**3. Webhook not receiving data**
- Verify webhook URLs in Shopify partner dashboard
- Check webhook secret configuration
- Review server logs for errors

### Support

- **Documentation**: [lemma.network/docs](https://lemma-enterprise-0f6ba17076c1.herokuapp.com/docs)
- **API Reference**: [lemma.network/api](https://lemma-enterprise-0f6ba17076c1.herokuapp.com/api/docs)
- **Support Email**: support@lemma.network
- **GitHub Issues**: [Report issues here](https://github.com/lemma-network/shopify-app/issues)

## 🤝 Contributing

We welcome contributions! Please see our [contributing guidelines](CONTRIBUTING.md) for details.

### Development Setup

```bash
# Fork the repository
git clone https://github.com/your-username/shopify-app.git

# Create feature branch
git checkout -b feature/your-feature

# Make changes and test
npm run test

# Submit pull request
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🏢 About Lemma

Lemma is building the foundational verification layer for the digital economy. Our privacy-first approach enables:

- **One verification** works everywhere
- **Network effects** reduce costs for everyone  
- **Zero personal data** collection
- **Enterprise-grade** security and compliance

**Join the network**: [lemma.network](https://lemma-enterprise-0f6ba17076c1.herokuapp.com)

---

**Made with ❤️ by the Lemma team** 