# CloudFlare Security Fix - Heroku Setup Guide

This guide shows how to fix the CloudFlare 403 "Just a moment..." errors by running the security level update directly from Heroku.

## Current Status ✅

- **Email Set**: `jedmckenna@lemma.id` ✅ (already configured in Heroku)
- **API Key**: ❓ (you need to add this manually)

## Step 1: Get Your CloudFlare Global API Key

1. Go to [CloudFlare Dashboard](https://dash.cloudflare.com/profile/api-tokens)
2. Scroll down to "API Keys" section
3. Click "View" next to "Global API Key"
4. Enter your password
5. Copy the API key

## Step 2: Set the API Key in Heroku

```bash
heroku config:set CLOUDFLARE_API_KEY=your-global-api-key-here --app lemma-enterprise
```

Replace `your-global-api-key-here` with the actual key from step 1.

## Step 3: Run the Fix

### Option A: Run from Heroku (Recommended)

```bash
heroku run python heroku_cloudflare_fix.py --app lemma-enterprise
```

### Option B: Run Locally (if you set environment variables)

**PowerShell:**
```powershell
$env:CLOUDFLARE_EMAIL="jedmckenna@lemma.id"
$env:CLOUDFLARE_API_KEY="your-api-key-here"
.\fix_cloudflare_security.ps1
```

**Bash:**
```bash
export CLOUDFLARE_EMAIL="jedmckenna@lemma.id"
export CLOUDFLARE_API_KEY="your-api-key-here"
./fix_cloudflare_security.sh
```

## What the Fix Does

- **Current Problem**: CloudFlare security level is set to "High", causing 403 errors
- **Solution**: Changes security level to "Medium" via API
- **Result**: lemma.id will be accessible without 403 errors

## Testing the Fix

After running the fix, test your site:

```bash
curl -I https://lemma.id/api/health
```

You should see:
- Status: `200 OK` (instead of `403 Forbidden`)
- No more "Just a moment..." screens

## Verification Commands

Check if the API key is set (don't worry, it won't show the actual key):
```bash
heroku config --app lemma-enterprise | findstr CLOUDFLARE
```

Should show:
```
CLOUDFLARE_EMAIL:       jedmckenna@lemma.id
CLOUDFLARE_API_KEY:     [REDACTED]
```

## Security Notes

- The Global API Key has full access to your CloudFlare account
- Never commit it to git or share it publicly
- Store it only in Heroku environment variables
- Consider using CloudFlare API tokens for more granular access in the future

## Troubleshooting

### Error: "Invalid API key"
- Double-check you copied the Global API Key correctly
- Make sure you're using the Global API Key, not an API token

### Error: "Invalid email"
- Verify the email matches your CloudFlare account
- Check for typos in the environment variable

### Still getting 403 errors
- CloudFlare changes can take 5-10 minutes to propagate
- Try clearing your browser cache
- Test with curl to bypass browser cache

## Files Created

- `heroku_cloudflare_fix.py` - Main script for Heroku
- `fix_cloudflare_security.sh` - Bash version (uses env vars)
- `fix_cloudflare_security.ps1` - PowerShell version (uses env vars)

## Next Steps

Once the fix is applied:
1. Your lemma.id domain will be fully accessible
2. API endpoints will work without 403 errors
3. The bot shield system will function properly
4. All documentation links can use lemma.id instead of the Heroku URL

---

**Current Configuration:**
- Zone ID: `c4e8c3580c49fa6351a5d6c02bc79b4d`
- Email: `jedmckenna@lemma.id` ✅
- API Key: ❓ (add manually)

**Ready to run:** Once you add the API key! 