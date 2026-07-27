# Subprocessor List (Draft)

**Status:** Draft pending counsel review  
**Last updated:** 2026-07-27  
**Version:** 2026-07-27.1

Lemma.id uses the following subprocessors to deliver the service. This list
supplements the privacy policy §5.1 and the DPA draft.

| Subprocessor | Purpose | Data processed | Location (typical) | Notes |
|---|---|---|---|---|
| **Stripe, Inc.** | Payment processing, billing meters | Customer billing identity, payment method (PCI via Stripe) | US / global | PCI DSS Level 1 |
| **Salesforce Heroku / Amazon Web Services** | Application hosting, Postgres, Redis | All platform data at rest/in transit | US (us-east-1 typical) | Infrastructure processor |
| **Amazon Web Services (KMS)** | Key management, encryption | KMS ciphertext for person roots, OAuth secrets | Region matches key ARN | Encryption processor |
| **Didit** | Identity verification (IDV) | Document verification, liveness (provider-hosted) | Provider regions | Lemma receives outcome only; raw docs not persisted |
| **Sentry** | Error monitoring | Stack traces, request metadata (anonymized where configured) | US | Error telemetry |
| **Mailgun / SendGrid** | Transactional email | Email addresses, message content | US | Whichever provider is configured |
| **UptimeRobot** | Status page monitoring | Public endpoint availability | EU/US | No end-user PII |

## Change notification

Material subprocessor changes will be announced via:

- Updated version date on this document
- Email to enterprise customers with DPA notice periods
- Privacy policy update when appropriate

## Enterprise requests

For a signed subprocessor appendix or data residency questions:
**privacy@lemma.id**

## Related documents

- [`DPA_DRAFT.md`](DPA_DRAFT.md)
- [`DATA_FLOW_INVENTORY.md`](DATA_FLOW_INVENTORY.md)
- Public privacy policy: `https://lemma.id/privacy`
