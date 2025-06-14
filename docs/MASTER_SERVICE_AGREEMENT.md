# 📋 **Lemma Enterprise Master Service Agreement (MSA)**

**Comprehensive Service Agreement with Pricing, SLA, Data Processing & Audit Terms**

---

## 🏢 **PARTIES & EFFECTIVE DATE**

**Service Provider:** Lemma Enterprise Inc.  
**Address:** [To be completed with registered business address]  
**Contact:** legal@lemma.network  

**Customer:** [Customer Name]  
**Effective Date:** [Agreement Date]  
**Agreement Version:** 1.0  

---

## 📋 **1. SERVICE DESCRIPTION**

### **1.1 Lemma Human Verification Services**

Lemma provides enterprise-grade human verification services through:

- **Core Verification API:** W3C-compliant verifiable credentials for human verification
- **Decentralized Identity:** Privacy-preserving verification without central data storage
- **Revocation Management:** Real-time credential revocation with OPRF privacy protection
- **Integration Support:** SDKs, documentation, and technical support per selected tier

### **1.2 Service Levels**

Services are provided according to the selected tier:
- **Standard Tier:** $0.10 per Monthly Active Human (MAH) + $2.00 per new human
- **Enterprise Tier:** $0.08 per MAH + $1.50 per new human (minimum $500/month)
- **Network Pricing:** Rates decrease as network grows (detailed in Section 3)

---

## 💰 **2. PRICING SCHEDULE**

### **2.1 Network-Effect Pricing Model**

**Base Rates:**
```
Standard Tier:
• Monthly Active Humans (MAH): $0.10 per human per month
• New Human Onboarding: $2.00 per new human (one-time)

Enterprise Tier:
• Monthly Active Humans (MAH): $0.08 per human per month  
• New Human Onboarding: $1.50 per new human (one-time)
• Minimum Monthly Commitment: $500
```

**Network Discount Schedule:**
```
Network Size → Monthly Rate Reduction:
• 10-49 businesses: 2% discount
• 50-99 businesses: 10% discount
• 100-499 businesses: 18% discount
• 500-999 businesses: 45% discount
• 1000+ businesses: 55% maximum discount
```

### **2.2 Volume Discounts (Enterprise Tier)**

Additional volume discounts apply to Enterprise customers:
```
Monthly Usage → Additional Discount:
• 1,000-9,999 MAH: 5% additional discount
• 10,000-49,999 MAH: 10% additional discount
• 50,000+ MAH: 15% additional discount
```

### **2.3 Billing Terms**

- **Billing Cycle:** Monthly in arrears
- **Payment Terms:** Net 30 days from invoice date
- **Late Fees:** 1.5% per month on overdue amounts
- **Currency:** USD unless otherwise specified
- **Taxes:** Customer responsible for applicable taxes

---

## 🎯 **3. SERVICE LEVEL AGREEMENT (SLA)**

### **3.1 Uptime Commitment**

**Service Availability:** 99.9% monthly uptime  
**Measurement Period:** Calendar month  
**Exclusions:** Scheduled maintenance (max 4 hours/month with 48-hour notice)

**SLA Credits:**
```
Monthly Uptime → Service Credit:
• 99.0% - 99.8%: 10% monthly fee credit
• 95.0% - 98.9%: 25% monthly fee credit
• Below 95.0%: 50% monthly fee credit
```

### **3.2 Performance Commitments**

**API Response Times:**
- **P95 Latency:** ≤ 500ms for verification requests
- **P99 Latency:** ≤ 1000ms for verification requests
- **Throughput:** 1000+ requests per second sustained

**Support Response Times:**
```
Tier → Critical → High → Medium → Low
Standard: 4h → 8h → 24h → 48h
Premium: 2h → 4h → 8h → 24h  
Enterprise: 30min → 1h → 4h → 8h
```

### **3.3 Security Commitments**

- **Data Encryption:** AES-256 encryption at rest, TLS 1.3 in transit
- **Access Controls:** Multi-factor authentication for all admin access
- **Audit Logging:** Complete audit trails for all data access
- **Incident Response:** 24×7 security monitoring with 1-hour breach notification

---

## 🛡️ **4. DATA PROCESSING TERMS**

### **4.1 Data Controller/Processor Relationship**

- **Customer:** Data Controller for end-user verification data
- **Lemma:** Data Processor acting on Customer's documented instructions
- **Processing Purpose:** Human verification and fraud prevention only

### **4.2 Data Categories & Retention**

**Personal Data Processed:**
- **Identity Verification:** Temporary processing during KYC (deleted after verification)
- **Usage Analytics:** Pseudonymized verification events (31-day retention)
- **Billing Data:** Customer usage metrics (7-year retention for tax compliance)

**Data Minimization:**
- No storage of biometric data or identity documents
- No central database of verified users
- Client-side credential storage only

### **4.3 Data Subject Rights**

Lemma will assist Customer in responding to data subject requests:
- **Access:** Provide data processing records within 72 hours
- **Rectification:** Correct inaccurate data within 5 business days
- **Erasure:** Delete personal data within 30 days of valid request
- **Portability:** Provide data in machine-readable format

### **4.4 International Data Transfers**

**Standard Contractual Clauses:** EU Commission SCCs (2021/914) apply to all EU data transfers  
**Adequacy Decisions:** Transfers to countries with EU adequacy decisions permitted  
**Additional Safeguards:** Encryption, access controls, and audit logging for all transfers

---

## 🔍 **5. AUDIT RIGHTS**

### **5.1 Customer Audit Rights**

**Annual Audit:** Customer may conduct one on-site or virtual audit per year with 30-day notice  
**SOC 2 Reports:** Lemma will provide current SOC 2 Type II reports upon request  
**Compliance Certifications:** ISO 27001, GDPR compliance documentation available

### **5.2 Third-Party Audits**

**Regulatory Audits:** Customer may request third-party security audits (Customer pays costs)  
**Penetration Testing:** Annual penetration testing reports available upon request  
**Compliance Monitoring:** Real-time compliance dashboard access for Enterprise customers

### **5.3 Audit Cooperation**

Lemma will:
- Provide reasonable access to systems and documentation
- Make personnel available for interviews during business hours
- Remediate any identified security or compliance issues within agreed timeframes
- Provide written responses to audit findings within 30 days

---

## 📋 **6. INTELLECTUAL PROPERTY**

### **6.1 Service IP**

- **Lemma Technology:** All rights reserved to Lemma Enterprise Inc.
- **Customer Data:** Customer retains all rights to their data and configurations
- **Improvements:** Lemma retains rights to service improvements and enhancements

### **6.2 Trademark Usage**

- **Lemma Marks:** Customer may use "Verified by Lemma" branding per brand guidelines
- **Customer Marks:** Lemma may reference Customer as a customer with prior approval
- **Co-Marketing:** Joint marketing activities require separate written agreement

---

## ⚖️ **7. LIABILITY & INDEMNIFICATION**

### **7.1 Limitation of Liability**

**Liability Cap:** Lemma's total liability limited to 12 months of fees paid by Customer  
**Excluded Damages:** No liability for indirect, consequential, or punitive damages  
**Exceptions:** No limitation for data breaches, IP infringement, or gross negligence

### **7.2 Indemnification**

**Lemma Indemnifies Customer for:**
- Third-party IP infringement claims related to Lemma service
- Data breaches caused by Lemma's security failures
- Regulatory fines due to Lemma's non-compliance

**Customer Indemnifies Lemma for:**
- Customer's misuse of the service
- Customer's violation of applicable laws
- Third-party claims related to Customer's data or business

---

## 🔄 **8. TERM & TERMINATION**

### **8.1 Agreement Term**

**Initial Term:** 12 months from Effective Date  
**Renewal:** Automatic 12-month renewals unless terminated with 90-day notice  
**Pricing Updates:** 60-day notice for pricing changes (existing customers grandfathered for 12 months)

### **8.2 Termination Rights**

**For Convenience:** Either party with 90-day written notice  
**For Cause:** Immediate termination for material breach (30-day cure period)  
**Non-Payment:** Lemma may suspend service after 15-day notice for non-payment

### **8.3 Data Return & Deletion**

**Data Export:** Customer may export data for 90 days after termination  
**Data Deletion:** Lemma will delete all Customer data within 30 days of termination  
**Backup Retention:** Encrypted backups retained for 12 months for legal compliance

---

## 📞 **9. SUPPORT & ESCALATION**

### **9.1 Technical Support**

**Standard Support:** Email and documentation (24-hour response)  
**Premium Support:** Email, phone, and priority escalation (4-hour response)  
**Enterprise Support:** Dedicated support engineer and 24×7 coverage (1-hour response)

### **9.2 Account Management**

**Customer Success:** Quarterly business reviews for Enterprise customers  
**Technical Account Manager:** Dedicated TAM for customers >$10K annual spend  
**Executive Escalation:** Direct access to VP Engineering for critical issues

---

## 📋 **10. COMPLIANCE & CERTIFICATIONS**

### **10.1 Security Certifications**

- **SOC 2 Type II:** Annual certification with continuous monitoring
- **ISO 27001:** Information Security Management System certification
- **GDPR Compliance:** Full compliance with EU data protection regulations

### **10.2 Industry Standards**

- **W3C Standards:** Full compliance with Verifiable Credentials and DID standards
- **NIST Framework:** Cybersecurity framework implementation
- **OWASP:** Secure development practices following OWASP guidelines

---

## ⚖️ **11. GOVERNING LAW & DISPUTES**

### **11.1 Governing Law**

This Agreement is governed by the laws of [Jurisdiction] without regard to conflict of law principles.

### **11.2 Dispute Resolution**

**Informal Resolution:** 30-day good faith negotiation period required  
**Mediation:** Binding mediation if informal resolution fails  
**Arbitration:** Final binding arbitration for disputes >$50,000  
**Jurisdiction:** [Court jurisdiction] for disputes <$50,000

---

## 📋 **12. GENERAL PROVISIONS**

### **12.1 Entire Agreement**

This MSA, together with any executed Order Forms and SOWs, constitutes the entire agreement between the parties.

### **12.2 Amendments**

Amendments must be in writing and signed by both parties, except for pricing updates per Section 8.1.

### **12.3 Severability**

If any provision is deemed invalid, the remainder of the Agreement remains in full force and effect.

### **12.4 Force Majeure**

Neither party liable for delays due to circumstances beyond reasonable control (natural disasters, government actions, etc.).

---

## ✍️ **SIGNATURE BLOCK**

**LEMMA ENTERPRISE INC.**

Signature: _________________________  
Name: [Name]  
Title: [Title]  
Date: _____________

**CUSTOMER**

Signature: _________________________  
Name: [Name]  
Title: [Title]  
Date: _____________

---

**For questions about this agreement, contact:** legal@lemma.network  
**For technical support, contact:** support@lemma.network  
**For billing inquiries, contact:** billing@lemma.network

**Agreement Version:** 1.0  
**Last Updated:** [Date]  
**Next Review:** [Date + 12 months] 