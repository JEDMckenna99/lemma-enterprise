# Lemma Shield Integration - Simple as Copy & Paste

**Add human verification to your site in under 2 minutes.**

## 🚀 **Quickest Integration (2 Lines)**

```html
<!-- 1. Add Lemma Shield Widget -->
<script src="https://lemma-enterprise-0f6ba17076c1.herokuapp.com/static/js/lemma-shield-widget.js"></script>

<!-- 2. Mark content as protected -->
<div data-lemma-protected="true">
  <h1>Protected Content</h1>
  <p>Only verified humans can see this!</p>
</div>
```

**Done!** Your content is now protected by Lemma Shield.

## 📋 **Step-by-Step Integration**

### **Step 1: Add the Script Tag**
Add this anywhere in your HTML (preferably before closing `</body>`):

```html
<script src="https://lemma-enterprise-0f6ba17076c1.herokuapp.com/static/js/lemma-shield-widget.js"></script>
```

### **Step 2: Mark Protected Content**
Add `data-lemma-protected="true"` to any element you want to protect:

```html
<!-- Protect a section -->
<section data-lemma-protected="true">
  <h2>Members Only Content</h2>
  <p>This content requires human verification.</p>
</section>

<!-- Protect a div -->
<div class="premium-content" data-lemma-protected="true">
  <h3>Premium Features</h3>
  <ul>
    <li>Advanced analytics</li>
    <li>Priority support</li>
    <li>Custom integrations</li>
  </ul>
</div>

<!-- Protect entire page content -->
<main data-lemma-protected="true">
  <!-- All your page content -->
</main>
```

### **Step 3: Test It**
1. Open your page in a browser
2. You'll see the Lemma Shield verification widget
3. Complete verification once
4. Content is revealed and stays accessible

## ⚙️ **Advanced Configuration (Optional)**

If you want more control, you can customize the widget:

```html
<script src="https://lemma-enterprise-0f6ba17076c1.herokuapp.com/static/js/lemma-shield-widget.js"></script>
<script>
// Initialize with custom options
const shield = new LemmaShieldWidget({
    protectedContent: '[data-lemma-protected="true"]',
    securityLevel: 'standard', // basic, standard, high, maximum
    apiBase: 'https://lemma-enterprise-0f6ba17076c1.herokuapp.com',
    
    // Event callbacks (optional)
    onVerified: function(data) {
        console.log('User verified!', data);
        // Track verification event
        gtag('event', 'lemma_verification_complete');
    },
    
    onError: function(error) {
        console.error('Verification failed:', error);
    }
});
</script>
```

## 🎯 **What Happens for Users**

### **First-Time Visitors:**
1. See "Human Verification Required" message
2. Click "Verify Human Identity"
3. Read privacy disclaimer about Lemma
4. Complete Stripe Identity verification (ID + selfie)
5. Content is revealed immediately
6. Verification is stored locally

### **Returning Visitors:**
1. Content appears immediately (background verification)
2. No interruption or additional steps needed
3. Seamless experience across all Lemma-protected sites

## 🔒 **Security Levels**

Choose the right security level for your needs:

- **`basic`**: Verification valid for 7 days, checks every 24 hours
- **`standard`**: Verification valid for 3 days, checks every hour *(recommended)*
- **`high`**: Verification valid for 1 day, checks every 30 minutes
- **`maximum`**: Verification valid for 1 hour, checks every 5 minutes

## 🌐 **Network Benefits**

Once users verify with Lemma:
- ✅ **Cross-Site Access**: Works on all Lemma-integrated sites
- ✅ **No Re-verification**: One verification, access everywhere
- ✅ **Privacy Protected**: Sites only learn user is human, nothing else
- ✅ **Offline Capable**: Verification works without constant internet

## 📊 **Integration Examples**

### **Blog/Content Site**
```html
<!-- Protect premium articles -->
<article data-lemma-protected="true">
  <h1>Premium Article: Advanced SEO Strategies</h1>
  <p>This content is available to verified humans only...</p>
</article>
```

### **E-commerce**
```html
<!-- Protect member pricing -->
<div class="member-pricing" data-lemma-protected="true">
  <h3>Member Price: $49.99</h3>
  <p class="savings">Save 50% with human verification!</p>
  <button>Add to Cart</button>
</div>
```

### **Community/Forum**
```html
<!-- Protect posting ability -->
<div class="post-form" data-lemma-protected="true">
  <h3>Create New Post</h3>
  <form>
    <textarea placeholder="Share your thoughts..."></textarea>
    <button type="submit">Post</button>
  </form>
</div>
```

### **SaaS Dashboard**
```html
<!-- Protect entire dashboard -->
<div id="dashboard" data-lemma-protected="true">
  <nav><!-- Navigation --></nav>
  <main><!-- Dashboard content --></main>
  <aside><!-- Sidebar --></aside>
</div>
```

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