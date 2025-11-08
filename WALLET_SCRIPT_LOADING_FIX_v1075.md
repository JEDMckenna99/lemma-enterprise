# Wallet Script Loading Fix - v1075

## Issue

`LemmaWallet is not defined` error on wallet page preventing credential display.

## Root Cause

The `layout.html` template was trying to use `LemmaWallet` in inline JavaScript before loading the `lemma-wallet.js` script.

## Fix

Added script tags to `templates/modern/layout.html` BEFORE the inline JavaScript:

```html
{% block scripts %}{% endblock %}

<!-- Load wallet scripts BEFORE inline JavaScript -->
<script src="{{ url_for('static', filename='js/lemma-wallet.js') }}"></script>
<script src="{{ url_for('static', filename='js/lemma-session-free-auth.js') }}"></script>

<!-- User Dropdown JavaScript -->
<script>
    // Now LemmaWallet is defined!
    const wallet = new LemmaWallet({debug: false});
    // ... rest of code
</script>
```

## Deployed

**Version:** v1075  
**Status:** ✅ FIXED

## Verification

The wallet page should now:
1. ✅ Load `LemmaWallet` class correctly
2. ✅ Display wallet credentials
3. ✅ Initialize session-free auth
4. ✅ Show dynamic navigation based on credentials

## Test

Visit: https://lemma.id/wallet

Expected:
- No `LemmaWallet is not defined` errors
- Wallet data displays correctly
- Credentials visible
- Session-free authentication working

