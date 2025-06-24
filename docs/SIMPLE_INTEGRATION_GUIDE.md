# Lemma Shield Integration Guide

## Quick Start (2 Minutes)

```html
<!DOCTYPE html>
<html>
<head>
    <title>Protected Site</title>
    <script src="https://lemma.id/static/js/lemma-shield-widget.js"></script>
</head>
<body>
    <h1>This content is protected by Lemma Shield</h1>
    <script>
        // Lemma will automatically handle verification
        // No additional code needed for basic protection
    </script>
</body>
</html>
```

## Basic Integration

```html
<!DOCTYPE html>
<html>
<head>
    <script src="https://lemma.id/static/js/lemma-shield-widget.js"></script>
</head>
<body>
    <div id="protected-content" style="display: none;">
        <h1>Welcome! You are verified as human.</h1>
        <p>This content is only visible to verified humans.</p>
    </div>

    <script>
        // Initialize Lemma Shield
        Lemma.init({
            onVerified: function(proof) {
                // User is verified as human
                document.getElementById('protected-content').style.display = 'block';
                console.log('User verified:', proof);
            },
            onBlocked: function(reason) {
                // User was blocked (bot detected, etc.)
                console.log('User blocked:', reason);
            }
        });
    </script>
</body>
</html>
```

## Advanced Integration

```html
<!DOCTYPE html>
<html>
<head>
    <title>Advanced Lemma Integration</title>
    <script src="https://lemma.id/static/js/lemma-shield-widget.js"></script>
</head>
<body>
    <div id="app">
        <div id="loading">Checking verification status...</div>
        <div id="verified-content" style="display: none;">
            <h1>Welcome, verified human!</h1>
            <button onclick="performSecureAction()">Secure Action</button>
        </div>
    </div>

    <script>
        const config = {
            apiBase: 'https://lemma.id',
            verificationTypes: ['human'],
            onVerified: handleVerified,
            onPending: handlePending,
            onBlocked: handleBlocked
        };

        function handleVerified(proof) {
            document.getElementById('loading').style.display = 'none';
            document.getElementById('verified-content').style.display = 'block';
        }

        function handlePending() {
            document.getElementById('loading').innerHTML = 'Verification in progress...';
        }

        function handleBlocked(reason) {
            document.getElementById('loading').innerHTML = 'Access denied: ' + reason;
        }

        function performSecureAction() {
            // This action is only available to verified humans
            console.log('Performing secure action...');
        }

        // Initialize Lemma with advanced config
        Lemma.init(config);
    </script>
</body>
</html>
```

## Node.js Backend Integration

```javascript
const express = require('express');
const axios = require('axios');
const app = express();

app.use(express.json());

// Middleware to verify Lemma credentials
async function verifyLemmaCredential(req, res, next) {
    const credential = req.headers['x-lemma-credential'];
    
    if (!credential) {
        return res.status(401).json({ error: 'Lemma credential required' });
    }

    try {
        const response = await axios.post('https://lemma.id/api/verify-credential', {
            credential: credential,
            challenge: req.headers['x-lemma-challenge']
        }, {
            headers: {
                'X-API-Key': process.env.LEMMA_API_KEY
            }
        });

        if (response.data.verified) {
            req.lemmaProof = response.data;
            next();
        } else {
            res.status(403).json({ error: 'Verification failed' });
        }
    } catch (error) {
        res.status(500).json({ error: 'Verification service unavailable' });
    }
}

// Protected endpoint
app.post('/api/secure-action', verifyLemmaCredential, (req, res) => {
    // This endpoint is only accessible to verified humans
    res.json({
        success: true,
        message: 'Secure action completed',
        userProof: req.lemmaProof
    });
});

app.listen(3000, () => {
    console.log('Server running on port 3000');
});
```

## Configuration Options

```javascript
Lemma.init({
    // Required: Your API key from Lemma
    apiKey: 'your-api-key-here',
    
    // Optional: Types of verification to require
    verificationTypes: ['human'], // 'human', 'age18+', 'location:US'
    
    // Optional: Custom styling
    theme: {
        primaryColor: '#007bff',
        borderRadius: '8px',
        fontFamily: 'Inter, sans-serif'
    },
    
    // Optional: Callbacks
    onVerified: (proof) => {
        console.log('User verified:', proof);
    },
    
    onBlocked: (reason) => {
        console.log('User blocked:', reason);
    },
    
    onError: (error) => {
        console.error('Lemma error:', error);
    }
});
```

## Testing Your Integration

1. Open your page in a browser
2. You should see the Lemma Shield appear
3. Complete the verification process
4. Your protected content should become visible

For more examples and detailed documentation, visit: https://lemma.id/docs

## 🚀 **Why It's So Simple**

1. **No Backend Changes**: Pure frontend integration
2. **No Database**: No user data to store or manage
3. **No Authentication System**: Lemma handles everything
4. **No API Keys**: Public widget works out of the box
5. **No Configuration**: Works with sensible defaults
6. **No Maintenance**: Auto-updates and self-healing

## 📞 **Need Help?**

- **Documentation**: Full API docs at `/api/docs`
- **Live Example**: See it working at `/join-network`
- **Support**: Contact us for integration assistance

---

**That's it!** Add one script tag, add one data attribute, and your content is protected by enterprise-grade human verification. 