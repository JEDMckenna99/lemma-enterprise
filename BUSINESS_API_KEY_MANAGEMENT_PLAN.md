# 🔐 Business API Key Management Implementation Plan

## 🚨 **Current Security Gap**

**Problem**: Auto-generated API keys (`lemma_auto_*`) are NOT suitable for business customers.

**Solution**: Implement proper business API key management using the existing production-grade system.

---

## 🏗️ **Implementation Plan**

### **Phase 1: Customer Onboarding System**

#### **A. Business Customer Registration**
```python
# New endpoint: /api/business/register
@business_bp.route('/api/business/register', methods=['POST'])
def register_business_customer():
    """Register a new business customer with proper API key management"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['company_name', 'contact_email', 'contact_name', 'use_case']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field} is required'}), 400
        
        # Create customer account
        customer = customer_manager.create_customer(
            email=data['contact_email'],
            name=data['contact_name'], 
            company=data['company_name']
        )
        
        # Create initial API key with appropriate scopes
        api_key_manager = get_api_key_manager()
        key_id, api_key = api_key_manager.create_api_key(
            scopes=[APIKeyScope.VERIFY, APIKeyScope.READONLY],  # Start with basic permissions
            description=f"Initial API key for {data['company_name']}",
            created_by="business_registration",
            expires_days=365,
            rate_limit=1000  # 1000 requests per minute
        )
        
        # Store customer-key relationship
        customer_manager.link_api_key(customer['customer_id'], key_id)
        
        # Send welcome email with integration instructions
        send_welcome_email(customer, api_key, key_id)
        
        return jsonify({
            'success': True,
            'customer_id': customer['customer_id'],
            'api_key': api_key,  # Only returned once!
            'key_id': key_id,
            'scopes': ['verify', 'readonly'],
            'rate_limit': 1000,
            'expires_at': (datetime.now() + timedelta(days=365)).isoformat(),
            'documentation_url': 'https://lemma.id/docs/api',
            'dashboard_url': f'https://lemma.id/dashboard?customer={customer["customer_id"]}'
        })
        
    except Exception as e:
        logger.error(f"Business registration failed: {e}")
        return jsonify({'error': 'Registration failed'}), 500
```

#### **B. Customer Dashboard**
```python
@business_bp.route('/dashboard')
def customer_dashboard():
    """Business customer dashboard"""
    customer_id = session.get('customer_id')
    if not customer_id:
        return redirect('/login')
    
    customer = customer_manager.get_customer(customer_id)
    api_keys = api_key_manager.list_customer_keys(customer_id)
    usage_stats = billing_manager.get_usage_stats(customer_id)
    
    return render_template('business/dashboard.html', 
                         customer=customer,
                         api_keys=api_keys,
                         usage_stats=usage_stats)
```

### **Phase 2: Tiered API Access Plans**

#### **A. API Access Tiers**
```python
class APITier(Enum):
    """Business API access tiers"""
    STARTER = "starter"      # 10K requests/month, verify only
    PROFESSIONAL = "professional"  # 100K requests/month, verify + issue
    ENTERPRISE = "enterprise"      # Unlimited, all scopes + priority support
    CUSTOM = "custom"              # Custom limits and scopes

API_TIER_LIMITS = {
    APITier.STARTER: {
        'monthly_requests': 10000,
        'rate_limit': 100,  # per minute
        'scopes': [APIKeyScope.VERIFY, APIKeyScope.READONLY],
        'price_per_month': 29,
        'overage_price': 0.001  # $0.001 per extra request
    },
    APITier.PROFESSIONAL: {
        'monthly_requests': 100000,
        'rate_limit': 1000,
        'scopes': [APIKeyScope.VERIFY, APIKeyScope.ISSUE, APIKeyScope.READONLY],
        'price_per_month': 99,
        'overage_price': 0.0005
    },
    APITier.ENTERPRISE: {
        'monthly_requests': -1,  # Unlimited
        'rate_limit': 10000,
        'scopes': [APIKeyScope.VERIFY, APIKeyScope.ISSUE, APIKeyScope.BILLING, APIKeyScope.READONLY],
        'price_per_month': 499,
        'overage_price': 0
    }
}
```

#### **B. Scope-Based Pricing**
```python
@business_bp.route('/api/business/upgrade-plan', methods=['POST'])
def upgrade_api_plan():
    """Upgrade customer's API plan"""
    customer_id = session.get('customer_id')
    data = request.get_json()
    
    new_tier = APITier(data['tier'])
    tier_config = API_TIER_LIMITS[new_tier]
    
    # Create new API key with upgraded scopes
    api_key_manager = get_api_key_manager()
    key_id, api_key = api_key_manager.create_api_key(
        scopes=tier_config['scopes'],
        description=f"{new_tier.value.title()} plan API key",
        created_by=f"customer_{customer_id}",
        rate_limit=tier_config['rate_limit']
    )
    
    # Update customer's subscription
    billing_manager.update_subscription(customer_id, new_tier, tier_config)
    
    return jsonify({
        'success': True,
        'new_api_key': api_key,
        'tier': new_tier.value,
        'monthly_limit': tier_config['monthly_requests'],
        'scopes': [scope.value for scope in tier_config['scopes']]
    })
```

### **Phase 3: Usage-Based Billing Integration**

#### **A. Request Tracking**
```python
def track_api_usage(api_key_obj: APIKey, endpoint: str, success: bool):
    """Track API usage for billing purposes"""
    usage_manager.record_request(
        customer_id=api_key_obj.customer_id,
        api_key_id=api_key_obj.key_id,
        endpoint=endpoint,
        timestamp=datetime.now(timezone.utc),
        success=success
    )
    
    # Check if customer is approaching limits
    monthly_usage = usage_manager.get_monthly_usage(api_key_obj.customer_id)
    customer_tier = billing_manager.get_customer_tier(api_key_obj.customer_id)
    tier_limit = API_TIER_LIMITS[customer_tier]['monthly_requests']
    
    if tier_limit > 0 and monthly_usage > tier_limit * 0.8:  # 80% warning
        send_usage_warning_email(api_key_obj.customer_id, monthly_usage, tier_limit)
```

#### **B. Automatic Billing**
```python
@celery.task
def process_monthly_billing():
    """Process monthly billing for all business customers"""
    for customer_id in customer_manager.get_active_customers():
        usage_stats = usage_manager.get_monthly_usage(customer_id)
        customer_tier = billing_manager.get_customer_tier(customer_id)
        tier_config = API_TIER_LIMITS[customer_tier]
        
        # Calculate bill
        base_cost = tier_config['price_per_month']
        overage_cost = 0
        
        if tier_config['monthly_requests'] > 0:  # Not unlimited
            overage_requests = max(0, usage_stats - tier_config['monthly_requests'])
            overage_cost = overage_requests * tier_config['overage_price']
        
        total_cost = base_cost + overage_cost
        
        # Create Stripe invoice
        stripe_manager.create_invoice(customer_id, {
            'base_plan': base_cost,
            'overage': overage_cost,
            'total': total_cost,
            'usage': usage_stats
        })
```

---

## 🔒 **Security Implementation**

### **A. Replace Auto-Generated Keys**
```python
# REPLACE this in simple_join.py:
api_key = f"lemma_auto_{secrets.token_hex(16)}"

# WITH this:
def create_site_integration_key(site_origin: str) -> str:
    """Create a proper API key for site integration"""
    
    # Check if site already has integration
    existing_integration = integration_manager.get_site_integration(site_origin)
    if existing_integration:
        return existing_integration['api_key_id']  # Don't return actual key
    
    # Create new integration with limited scope
    api_key_manager = get_api_key_manager()
    key_id, api_key = api_key_manager.create_api_key(
        scopes=[APIKeyScope.VERIFY],  # Only verification, no issuing
        description=f"Site integration for {site_origin}",
        created_by="site_integration_system",
        expires_days=30,  # Short expiration for security
        rate_limit=100,   # Conservative limit
        ip_whitelist=None  # Could add IP restrictions
    )
    
    # Store integration record
    integration_manager.create_site_integration(
        site_origin=site_origin,
        api_key_id=key_id,
        integration_type="federated_shield",
        status="active"
    )
    
    # Return key ID only (not actual key) for tracking
    return key_id
```

### **B. Enhanced Validation**
```python
@validate_api_key_enhanced
def verify_credential_endpoint():
    """Enhanced API key validation for business endpoints"""
    
    def validate_api_key_enhanced(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Get API key from header
            auth_header = request.headers.get('Authorization', '')
            if not auth_header.startswith('Bearer '):
                return jsonify({'error': 'Bearer token required'}), 401
            
            api_key = auth_header[7:]  # Remove 'Bearer '
            client_ip = request.remote_addr
            endpoint = request.endpoint
            method = request.method
            
            # Use production API key manager
            api_key_manager = get_api_key_manager()
            is_valid, key_obj, error = api_key_manager.validate_api_key(
                api_key, endpoint, method, client_ip
            )
            
            if not is_valid:
                return jsonify({'error': error}), 401
            
            # Add key info to request context
            g.api_key = key_obj
            g.customer_id = key_obj.customer_id
            
            # Track usage for billing
            track_api_usage(key_obj, endpoint, True)
            
            return f(*args, **kwargs)
        
        return decorated_function
    
    return validate_api_key_enhanced
```

---

## 📊 **Business Dashboard Features**

### **A. API Key Management**
```html
<!-- Customer Dashboard - API Key Management -->
<div class="api-key-management">
    <h2>API Key Management</h2>
    
    <div class="current-plan">
        <h3>Current Plan: {{ customer.plan.title() }}</h3>
        <p>Monthly Limit: {{ customer.monthly_limit | format_number }} requests</p>
        <p>Rate Limit: {{ customer.rate_limit }} requests/minute</p>
        <p>This Month Usage: {{ usage_stats.current_month | format_number }} requests</p>
        
        <div class="usage-bar">
            <div class="usage-fill" style="width: {{ usage_percentage }}%"></div>
        </div>
    </div>
    
    <div class="api-keys-list">
        <h3>Your API Keys</h3>
        {% for key in api_keys %}
        <div class="api-key-card">
            <div class="key-info">
                <h4>{{ key.description }}</h4>
                <p><strong>Key ID:</strong> {{ key.key_id }}</p>
                <p><strong>Scopes:</strong> {{ key.scopes | join(', ') }}</p>
                <p><strong>Created:</strong> {{ key.created_at | format_date }}</p>
                <p><strong>Last Used:</strong> {{ key.last_used_at | format_date }}</p>
                <p><strong>Usage:</strong> {{ key.usage_count | format_number }} requests</p>
            </div>
            
            <div class="key-actions">
                <button onclick="rotateKey('{{ key.key_id }}')" class="btn-warning">
                    🔄 Rotate Key
                </button>
                <button onclick="revokeKey('{{ key.key_id }}')" class="btn-danger">
                    🚫 Revoke Key
                </button>
            </div>
        </div>
        {% endfor %}
        
        <button onclick="createNewKey()" class="btn-primary">
            ➕ Create New API Key
        </button>
    </div>
</div>
```

### **B. Usage Analytics**
```html
<div class="usage-analytics">
    <h2>Usage Analytics</h2>
    
    <div class="metrics-grid">
        <div class="metric-card">
            <h3>This Month</h3>
            <p class="metric-value">{{ usage_stats.current_month | format_number }}</p>
            <p class="metric-label">API Requests</p>
        </div>
        
        <div class="metric-card">
            <h3>Success Rate</h3>
            <p class="metric-value">{{ usage_stats.success_rate }}%</p>
            <p class="metric-label">Successful Requests</p>
        </div>
        
        <div class="metric-card">
            <h3>Avg Response Time</h3>
            <p class="metric-value">{{ usage_stats.avg_response_time }}ms</p>
            <p class="metric-label">Response Time</p>
        </div>
    </div>
    
    <div class="usage-chart">
        <canvas id="usageChart" width="800" height="400"></canvas>
    </div>
    
    <div class="endpoint-breakdown">
        <h3>Most Used Endpoints</h3>
        <table class="usage-table">
            <thead>
                <tr>
                    <th>Endpoint</th>
                    <th>Requests</th>
                    <th>Success Rate</th>
                    <th>Avg Response Time</th>
                </tr>
            </thead>
            <tbody>
                {% for endpoint in usage_stats.endpoint_breakdown %}
                <tr>
                    <td>{{ endpoint.path }}</td>
                    <td>{{ endpoint.requests | format_number }}</td>
                    <td>{{ endpoint.success_rate }}%</td>
                    <td>{{ endpoint.avg_response_time }}ms</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
```

---

## 💰 **Pricing Strategy**

### **Recommended Business Plans:**

#### **🚀 Starter Plan - $29/month**
- ✅ 10,000 API requests/month
- ✅ Basic verification endpoints
- ✅ Standard support
- ✅ Dashboard analytics
- ✅ $0.001 per extra request

#### **💼 Professional Plan - $99/month**
- ✅ 100,000 API requests/month  
- ✅ Verification + credential issuance
- ✅ Priority support
- ✅ Advanced analytics
- ✅ Custom webhooks
- ✅ $0.0005 per extra request

#### **🏢 Enterprise Plan - $499/month**
- ✅ Unlimited API requests
- ✅ All API endpoints
- ✅ Dedicated support
- ✅ Custom integrations
- ✅ SLA guarantees
- ✅ White-label options

---

## ✅ **Implementation Checklist**

### **Phase 1: Security (Critical)**
- [ ] Replace auto-generated keys with proper API key management
- [ ] Implement business customer registration
- [ ] Add API key validation to all endpoints
- [ ] Create customer dashboard for key management

### **Phase 2: Billing (High Priority)**
- [ ] Implement usage tracking
- [ ] Create tiered pricing plans
- [ ] Integrate Stripe billing automation
- [ ] Add usage analytics dashboard

### **Phase 3: Business Features (Medium Priority)**
- [ ] Add API key rotation capabilities
- [ ] Implement IP whitelisting
- [ ] Create detailed usage reports
- [ ] Add webhook notifications

### **Phase 4: Enterprise Features (Low Priority)**
- [ ] Custom rate limiting per customer
- [ ] Advanced analytics and reporting
- [ ] White-label API documentation
- [ ] Priority support system

---

## 🎯 **Expected Business Impact**

### **Revenue Potential:**
- **100 Starter customers**: $2,900/month = $34,800/year
- **50 Professional customers**: $4,950/month = $59,400/year  
- **10 Enterprise customers**: $4,990/month = $59,880/year
- **Total potential**: $12,840/month = **$154,080/year**

### **Security Benefits:**
- ✅ **SOC 2 Compliance** ready for enterprise sales
- ✅ **Audit trails** for all API usage
- ✅ **Key rotation** for security incidents
- ✅ **Usage monitoring** prevents abuse
- ✅ **Scope limitations** reduce attack surface

**Bottom Line**: Proper API key management is **essential** for selling to businesses and will significantly increase your revenue potential while maintaining security!



