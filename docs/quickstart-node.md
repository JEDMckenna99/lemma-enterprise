# Lemma Shield API - Node.js Quick Start

Get up and running with Lemma Shield in under 15 lines of code.

## Installation

```bash
npm install axios
```

## Basic Usage

```javascript
const axios = require('axios');

// Configure the API client
const lemmaAPI = axios.create({
      baseURL: 'https://lemma.id/api/v1',
  headers: {
    'Authorization': 'Bearer YOUR_API_KEY_HERE',
    'Content-Type': 'application/json'
  }
});

// Start KYC verification
async function startVerification(userId) {
  const response = await lemmaAPI.post('/kyc/start', {
    user_id: userId,
    callback_url: 'https://your-site.com/callback'
  });
  return response.data.verification_url;
}

// Verify a credential presentation
async function verifyUser(presentation, challenge) {
  const response = await lemmaAPI.post('/verify', {
    presentation,
    challenge
  });
  return response.data.verified;
}

// Generate a challenge for verification
async function getChallenge() {
  const response = await lemmaAPI.get('/challenge');
  return response.data.challenge;
}

// Example: Complete verification flow
async function verifyHuman(userId, userPresentation) {
  try {
    // 1. Get a fresh challenge
    const challenge = await getChallenge();
    
    // 2. Verify the presentation
    const isVerified = await verifyUser(userPresentation, challenge);
    
    console.log(`User ${userId} verification:`, isVerified);
    return isVerified;
  } catch (error) {
    console.error('Verification failed:', error.response?.data || error.message);
    return false;
  }
}
```

## Express.js Integration

```javascript
const express = require('express');
const app = express();

app.use(express.json());

// Protect a route with Lemma verification
app.post('/protected', async (req, res) => {
  const { presentation } = req.body;
  
  if (!presentation) {
    return res.status(400).json({ error: 'Presentation required' });
  }
  
  const challenge = await getChallenge();
  const isVerified = await verifyUser(presentation, challenge);
  
  if (isVerified) {
    res.json({ message: 'Access granted to verified human!' });
  } else {
    res.status(403).json({ error: 'Human verification required' });
  }
});
```

## Error Handling

```javascript
// Robust error handling
async function safeVerification(userId, presentation) {
  try {
    const challenge = await getChallenge();
    const result = await verifyUser(presentation, challenge);
    return { success: true, verified: result };
  } catch (error) {
    if (error.response?.status === 401) {
      return { success: false, error: 'Invalid API key' };
    }
    if (error.response?.status === 429) {
      return { success: false, error: 'Rate limit exceeded' };
    }
    return { success: false, error: 'Verification failed' };
  }
}
```

That's it! You now have human verification in your Node.js application with just a few lines of code. 