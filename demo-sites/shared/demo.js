// === LEMMA.ID DEMO ===
// This is the SAME integration code a real developer would use.
// No custom solutions. Just the SDK.

const wallet = new LemmaWallet();
let startTime = 0, keystrokes = 0, tradSteps = 0;

// =============================================
// LEMMA INTEGRATION (what every developer does)
// =============================================

// Sign in with Lemma - the ENTIRE integration
async function signInWithLemma() {
    startTime = performance.now();
    document.getElementById('lemma-status').innerHTML = 'Authenticating...';

    const result = await wallet.getAuthenticatedPPID();

    if (result.authenticated) {
        // Send PPID to YOUR backend (replaces email/password)
        await fetch('/api/auth/lemma', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ppid: result.ppid })
        });
        showSuccess('Lemma User', 'lemma', ((performance.now() - startTime) / 1000).toFixed(1), 0, '1 tap');
    } else {
        // Redirect to lemma.id (user creates/unlocks wallet there)
        wallet.unlockWithRedirect({ returnUrl: window.location.href });
    }
}

// Check auth on page load - also standard SDK usage
async function checkLemmaAuth() {
    const result = await wallet.getAuthenticatedPPID();
    if (result.authenticated) {
        await fetch('/api/auth/lemma', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ppid: result.ppid })
        });
        return true;
    }
    return false;
}

// =============================================
// INTERSTITIAL (loading state between views)
// =============================================

function showInterstitial(message) {
    // Hide auth and success views
    document.getElementById('auth-view').classList.add('hidden');
    document.getElementById('success-view').classList.add('hidden');

    let el = document.getElementById('lemma-interstitial');
    if (!el) {
        el = document.createElement('div');
        el.id = 'lemma-interstitial';
        // Insert before success-view's parent or at end of container
        const container = document.getElementById('auth-view').parentNode;
        container.appendChild(el);
    }
    el.innerHTML =
        '<div style="width:40px;height:40px;border:3px solid rgba(102,126,234,0.3);' +
        'border-radius:50%;border-top-color:#667eea;animation:lemma-demo-spin 0.8s linear infinite;' +
        'margin-bottom:16px;"></div>' +
        '<div style="font-size:1.1rem;font-weight:500;opacity:0.8;">' + (message || 'Loading...') + '</div>';
    el.classList.remove('hidden');

    // Inject keyframe if not already present
    if (!document.getElementById('lemma-demo-spin-style')) {
        const style = document.createElement('style');
        style.id = 'lemma-demo-spin-style';
        style.textContent = '@keyframes lemma-demo-spin{to{transform:rotate(360deg)}}';
        document.head.appendChild(style);
    }
}

function hideInterstitial() {
    const el = document.getElementById('lemma-interstitial');
    if (el) el.classList.add('hidden');
}

// =============================================
// DEMO UI (form helpers, password comparison)
// =============================================

function toggleTrad() { const panel = document.getElementById('trad-panel'); const arrow = document.getElementById('trad-arrow'); if (panel) panel.classList.toggle('open'); if (arrow) arrow.classList.toggle('open'); }
function switchTab() {}
function checkPassword() {}
function checkConfirm() {}
function checkPasswordValid() { return false; }
function handleCreate(e) { if (e) e.preventDefault(); return false; }
function completeVerification() {}
function handleSignIn(e) { if (e) e.preventDefault(); return false; }

function showSuccess(u, m, t, k, s) {
    hideInterstitial();

    const authView = document.getElementById('auth-view');
    const successView = document.getElementById('success-view');

    // Set up success content
    document.getElementById('success-user').textContent = u;
    document.getElementById('stat-time').textContent = t + 's';
    document.getElementById('stat-keys').textContent = k;
    document.getElementById('stat-steps').textContent = s;
    const tag = document.getElementById('success-method');
    tag.textContent = m === 'lemma' ? 'Signed in with Lemma.id' : 'Signed in with password';
    tag.className = 'method-tag ' + (m === 'lemma' ? 'method-lm' : 'method-pw');
    renderSignoutActions(m);

    // Fade out auth-view, fade in success-view
    authView.style.transition = 'opacity 250ms ease-out';
    authView.style.opacity = '0';
    setTimeout(() => {
        authView.classList.add('hidden');
        authView.style.opacity = '';
        authView.style.transition = '';

        successView.style.opacity = '0';
        successView.classList.remove('hidden');
        successView.style.transition = 'opacity 300ms ease-in';
        requestAnimationFrame(() => { successView.style.opacity = '1'; });
    }, 250);

    // Update links to pass via=lemma for cross-site demo
    document.querySelectorAll('.j-other').forEach(link => {
        const url = new URL(link.href);
        if (m === 'lemma') { url.searchParams.set('via', 'lemma'); } else { url.searchParams.delete('via'); }
        link.href = url.toString();
    });
}

function renderSignoutActions(m) {
    const el = document.getElementById('signout-actions');
    if (m === 'lemma') {
        el.innerHTML = '<div style="margin-top:16px;padding:14px;background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.2);border-radius:8px;"><div style="font-weight:600;color:#34d399;font-size:0.85rem;margin-bottom:6px;">You control your identity</div><p style="font-size:0.8rem;color:#94a3b8;margin-bottom:10px;">Sign out everywhere from <a href="https://lemma.id/app" target="_blank" style="color:#34d399;">lemma.id</a>. No credentials stored on this server.</p><button class="btn-out" onclick="doLogout()">Sign Out of This Site</button></div>';
    } else {
        el.innerHTML = '<div style="margin-top:16px;padding:14px;background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.2);border-radius:8px;"><div style="font-weight:600;color:#f87171;font-size:0.85rem;margin-bottom:6px;">Limited control</div><p style="font-size:0.8rem;color:#94a3b8;margin-bottom:10px;">This only signs you out here. Your data remains on this server.</p><button class="btn-out" onclick="doLogout()">Sign Out of This Site</button><p style="font-size:0.7rem;color:#475569;margin-top:6px;">Still signed in on other sites.</p></div>';
    }
}

async function doLogout() { await fetch('/api/auth/logout', { method: 'POST' }); resetUI(); }
function resetUI() { keystrokes=0; startTime=0; tradSteps=0; hideInterstitial(); document.getElementById('auth-view').classList.remove('hidden'); document.getElementById('success-view').classList.add('hidden'); document.getElementById('lemma-status').innerHTML = 'Click to sign in with Lemma.id'; }

// =============================================
// PAGE LOAD
// =============================================
async function init() {
    const params = new URLSearchParams(window.location.search);

    // 1. Check server session (persists across tabs)
    try {
        const res = await fetch('/api/auth/session');
        const data = await res.json();
        if (data.authenticated) {
            showSuccess(data.user?.display_name || 'User', data.user?.ppid ? 'lemma' : 'password', '0', 0, 'session');
            return;
        }
    } catch(e) {}

    // 2. Returning from a redirect the USER initiated (has encrypted data)
    if (params.get('lemma_unlocked') === '1' || params.get('lemma_data')) {
        showInterstitial('Completing sign-in...');
        if (await checkLemmaAuth()) {
            window.history.replaceState({}, '', window.location.pathname);
            showSuccess('Lemma User', 'lemma', '2.5', 0, '1 tap');
            return;
        }
        window.history.replaceState({}, '', window.location.pathname);
        hideInterstitial();
    }

    // 3. Silent auto-auth: try to authenticate without user interaction
    const isViaLemma = params.get('via') === 'lemma';
    if (isViaLemma) {
        showInterstitial('Signing you in...');
        window.history.replaceState({}, '', window.location.pathname);
    }
    try {
        const silentResult = await wallet.getAuthenticatedPPID();
        if (silentResult.authenticated) {
            if (!isViaLemma) showInterstitial('Signing you in...');
            await fetch('/api/auth/lemma', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ppid: silentResult.ppid })
            });
            showSuccess('Lemma User', 'lemma', '0.2', 0, 'auto');
            return;
        }
    } catch(e) {}

    // 4. Show login - user must click to authenticate
    hideInterstitial();
    document.getElementById('auth-view').classList.remove('hidden');
    document.getElementById('lemma-status').innerHTML = 'Click to sign in with Lemma.id';
}

// Lock detection (standard SDK event)
document.addEventListener('visibilitychange', async () => {
    if (document.visibilityState !== 'visible') return;
    try {
        const res = await fetch('/api/auth/session');
        const data = await res.json();
        if (!data.authenticated || !data.user?.ppid) return;
        const auth = await wallet.autoAuthenticate();
        if (!auth.authenticated) { await fetch('/api/auth/logout', { method: 'POST' }); resetUI(); }
    } catch(e) {}
});
window.addEventListener('lemma-wallet-locked', async () => { await fetch('/api/auth/logout', { method: 'POST' }); resetUI(); });

init();
