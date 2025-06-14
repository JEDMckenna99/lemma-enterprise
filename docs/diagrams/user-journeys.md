# Lemma Enterprise - User Journey Flows

This diagram shows the different user paths and workflows through the Lemma Enterprise application.

```mermaid
graph TD
    %% User Entry Points
    A["New Visitor"] --> B{{"Landing Page<br/>/index.html"}}
    
    %% Customer Journey
    B --> C["Customer Onboarding"]
    C --> C1["Start Registration<br/>/onboarding/"]
    C1 --> C2["Register Account<br/>/onboarding/register"]
    C2 --> C3["Verify Domain<br/>/onboarding/verify"]
    C3 --> C4["Customer Dashboard<br/>/onboarding/dashboard"]
    
    %% Dashboard Actions
    C4 --> C5["Manage API Keys<br/>/onboarding/api-keys"]
    C4 --> C6["View Usage Analytics<br/>/onboarding/usage"]
    C4 --> C7["Integration Guide<br/>/onboarding/integration"]
    
    %% End User Journey
    B --> D["End User Verification"]
    D --> D1["Verify Human<br/>/verify"]
    D1 --> D2["Access Protected Content<br/>/protected"]
    
    %% Admin Journey
    B --> E["Admin Access"]
    E --> E1["Admin Login<br/>/admin/login"]
    E1 --> E2["Admin Dashboard<br/>/admin"]
    E2 --> E3["Issue Credentials"]
    E2 --> E4["Manage System"]
    
    %% Developer Journey
    B --> F["Developer Resources"]
    F --> F1["API Documentation<br/>/api-docs"]
    F --> F2["Widget Demo<br/>/gate-demo"]
    F --> F3["Integration Test<br/>/widget-test"]
    
    %% Billing Journey
    G["Billing Events"] --> G1["Invoice Generation<br/>/billing/invoices"]
    G --> G2["Payment Methods<br/>/billing/payment-methods"]
    G --> G3["Identity Verification<br/>/billing/identity-complete"]
    
    %% Error Handling
    H["Errors"] --> H1["Error Page<br/>/error"]
    
    %% Styling
    classDef customer fill:#e1f5fe,stroke:#01579b,stroke-width:3px
    classDef enduser fill:#e8f5e8,stroke:#2e7d32,stroke-width:3px
    classDef admin fill:#fff3e0,stroke:#e65100,stroke-width:3px
    classDef developer fill:#f3e5f5,stroke:#4a148c,stroke-width:3px
    classDef billing fill:#fff8e1,stroke:#f9a825,stroke-width:3px
    classDef error fill:#ffebee,stroke:#c62828,stroke-width:3px
    
    class C,C1,C2,C3,C4,C5,C6,C7 customer
    class D,D1,D2 enduser
    class E,E1,E2,E3,E4 admin
    class F,F1,F2,F3 developer
    class G,G1,G2,G3 billing
    class H,H1 error
```

## User Journey Types

- **🔵 Customer Journey** - Business onboarding and management workflow
- **🟢 End User Journey** - Human verification and content access
- **🟠 Admin Journey** - System administration and management
- **🟣 Developer Journey** - API integration and testing
- **🟡 Billing Journey** - Payment and invoice management
- **🔴 Error Journey** - Error handling and recovery

## Journey Details

### 🔵 Business Customer Journey (7 Steps)
1. **Discovery** → Landing page introduction
2. **Registration** → Account creation and setup
3. **Domain Verification** → Ownership confirmation
4. **Dashboard Access** → Main control panel
5. **API Integration** → Key management and setup
6. **Usage Monitoring** → Analytics and tracking
7. **Ongoing Management** → Continuous operations

### 🟢 End User Journey (3 Steps)
1. **Entry** → Customer's integrated website
2. **Verification** → Human verification process
3. **Access** → Protected content and features

### 🟠 Admin Journey (4 Steps)
1. **Authentication** → Secure admin login
2. **Dashboard** → System overview and controls
3. **Management** → User and credential operations
4. **Monitoring** → System health and metrics

### 🟣 Developer Journey (3 Steps)
1. **Documentation** → API reference and guides
2. **Testing** → Demo environments and widgets
3. **Integration** → Live implementation and testing

## Key Decision Points

- **Landing Page** → Multiple user type routing
- **Customer Dashboard** → Feature access branching
- **Admin Dashboard** → Management function selection
- **Error Handling** → Recovery and support routing 