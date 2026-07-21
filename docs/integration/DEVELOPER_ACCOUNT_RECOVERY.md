# Developer Account Recovery

If you lose access to your Lemma.id developer dashboard, you can recover your account using your API key.

## Prerequisites

To recover your account, you need:
- Your **Site ID** (e.g., `site_abc123`)
- A valid **API Key** for that site (live or test)

If you don't have access to your API key, contact support@lemma.id.

## Recovery Process

### 1. Go to Recovery Page

Navigate to: **https://lemma.id/recover**

### 2. Enter Credentials

- **Site ID**: Your site's unique identifier
- **API Key**: Any active API key for that site

### 3. Check Email

A recovery link will be sent to the **admin email** on file for your site.

> The email contains a time-limited link (15 minutes) that can only be used once.

### 4. Register New Passkey

Click the link in the email to register a new passkey and regain access to your account.

## Security

This recovery method is secure because it requires two factors:

| Factor | What It Proves |
|--------|----------------|
| **API Key** | You own/control the site |
| **Email Access** | You control the admin email |

An attacker would need both your API key AND access to your email to compromise your account.

## API Reference

If you need to trigger recovery programmatically:

### Initiate Recovery

```bash
POST https://lemma.id/api/recovery/initiate
Content-Type: application/json

{
  "site_id": "site_abc123",
  "api_key": "sk_live_..."
}
```

**Response:**
```json
{
  "success": true,
  "message": "If the API key is valid, a recovery link has been sent to the admin email."
}
```

> Note: The response is intentionally vague to prevent information leakage about valid site IDs or API keys.

### Complete Recovery

After opening the email link, register or unlock a **replacement passkey** in the
browser. The completion call must include the wallet-derived PPID and passkey
credential id — email token alone is not sufficient.

```bash
POST https://lemma.id/api/recovery/complete
Content-Type: application/json

{
  "token": "<token from email link>",
  "ppid": "did:lemma:ppid_...",
  "passkey_credential_id": "<base64url credential id from WebAuthn>"
}
```

**Errors:** `replacement_passkey_required`, `replacement_ppid_required`,
`Invalid, expired, or already used token`, `admin_record_not_found`.

The legacy `/api/recovery/complete-wallet` path is disabled; use passkey recovery.

## Best Practices

1. **Store API keys securely** - Use a password manager or secrets vault
2. **Keep admin email current** - Update it if your email changes
3. **Enable multiple devices** - Link your wallet across devices to avoid lockout
4. **Rotate keys periodically** - If you suspect a key was compromised

## If You Can't Recover

If you don't have access to your API key or admin email:

1. Contact **support@lemma.id**
2. Provide proof of site ownership (domain verification, DNS records, etc.)
3. Our team will manually verify and assist with recovery

## End-User Recovery (For Your Customers)

This recovery system is for **developer accounts** on Lemma.id.

For end-users on your platform who lose their passkeys:

1. **Primary recovery**: Users link wallets across multiple devices (passkeys sync automatically)
2. **Custom recovery**: Build your own email-based recovery using your internal user IDs

### Building Custom Recovery

If you want email recovery for your users:

```
1. User requests recovery on your site
2. You verify the user via email (your system)
3. Create a recovery claim with user's PPID
4. Call Lemma to sign the claim
5. User proves ownership → re-authenticates
6. Same PPID returned (identity preserved)
```

This keeps you in control of the recovery flow while Lemma provides cryptographic proof.
