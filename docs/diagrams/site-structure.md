# Lemma Enterprise - Main Site Structure

This diagram shows the complete page structure and navigation flow of the Lemma Enterprise application.

```mermaid
graph TD
    %% Main Entry Points
    A["/"] --> B["Landing Page<br/>index.html"]
    B --> C["Verify Lemma"]
    B --> D["Access Protected Content"]
    B --> E["Customer Onboarding"]
    
    %% Customer Onboarding Flow
    E --> F["/onboarding<br/>start.html"]
    F --> G["/onboarding/register<br/>register.html"]
    G --> H["/onboarding/verify<br/>verify.html"]
    H --> I["/onboarding/dashboard<br/>dashboard.html"]
    
    %% Customer Dashboard Sections
    I --> J["/onboarding/api-keys<br/>api_keys.html"]
    I --> K["/onboarding/usage<br/>usage.html"]
    I --> L["/onboarding/integration<br/>integration.html"]
    
    %% Core Verification Flow
    C --> M["/verify<br/>verify.html"]
    M --> N["/protected<br/>protected content"]
    D --> N
    
    %% Admin Section
    O["/admin/login<br/>admin_login.html"] --> P["/admin<br/>admin.html"]
    P --> Q["Issue Credentials"]
    P --> R["Manage Users"]
    
    %% Billing System
    S["/billing"] --> T["/billing/invoices<br/>invoices.html"]
    S --> U["/billing/payment-methods<br/>payment_methods.html"]
    S --> V["/billing/identity-complete<br/>identity_complete.html"]
    
    %% Demo & Testing
    W["/gate-demo<br/>gate_demo.html"] --> X["Agent Network Demo"]
    Y["/widget-test"] --> Z["Widget Integration Test"]
    
    %% API Documentation
    AA["/api-docs"] --> BB["OpenAPI Documentation"]
    
    %% Error Handling
    CC["/error<br/>error.html"] --> DD["Error Pages"]
    
    %% Styling
    classDef customer fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    classDef admin fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef api fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef demo fill:#e8f5e8,stroke:#1b5e20,stroke-width:2px
    
    class F,G,H,I,J,K,L customer
    class O,P,Q,R admin
    class AA,BB api
    class W,X,Y,Z demo
```

## Page Categories

- **🔵 Customer Pages** - Business onboarding and management
- **🟠 Admin Pages** - System administration
- **🟣 API Pages** - Developer documentation
- **🟢 Demo Pages** - Testing and demonstration

## Key Navigation Flows

1. **Customer Journey**: Landing → Onboarding → Registration → Verification → Dashboard
2. **End User Journey**: Landing → Verification → Protected Content
3. **Admin Journey**: Admin Login → Admin Dashboard → Management
4. **Developer Journey**: Landing → API Docs → Demo Pages 