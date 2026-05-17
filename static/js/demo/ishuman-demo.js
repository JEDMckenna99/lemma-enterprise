(function () {
  'use strict';

  const SITE_SLUGS = ['tickets', 'trials'];
  const SITE_IDS = {
    tickets: 'tickets-demo.lemma.id',
    trials: 'trials-demo.lemma.id',
  };

  const state = {
    config: null,
    wallet: null,
    walletId: null,
    walletSecret: null,
    sessionId: localStorage.getItem('ishuman_demo_session_id') || '',
    masterCredential: null,
    masterCredentialId: localStorage.getItem('ishuman_demo_master_id') || '',
    results: {},
    localBlocks: {
      tickets: new Set(),
      trials: new Set(),
    },
  };

  function $(id) {
    return document.getElementById(id);
  }

  function short(value) {
    const text = String(value || '');
    if (!text) return '-';
    if (text.length <= 24) return text;
    return `${text.slice(0, 14)}...${text.slice(-8)}`;
  }

  function pretty(value) {
    return JSON.stringify(value || {}, null, 2);
  }

  function log(message, detail) {
    const row = document.createElement('div');
    const time = new Date().toLocaleTimeString();
    row.textContent = `[${time}] ${message}${detail ? `: ${detail}` : ''}`;
    $('ih-log').prepend(row);
  }

  function setPill(id, label, tone) {
    const el = $(id);
    if (!el) return;
    el.textContent = label;
    el.className = `ih-pill ${tone || ''}`.trim();
  }

  async function requestJson(url, options) {
    const res = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(options && options.headers ? options.headers : {}),
      },
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err = new Error(data.error || data.message || `HTTP ${res.status}`);
      err.payload = data;
      throw err;
    }
    return data;
  }

  async function loadConfig() {
    state.config = await requestJson('/api/demo/ishuman/config');
    $('ih-network-json').textContent = pretty(state.config);
    log('Demo config loaded', `${state.config.sites.length} sites`);
  }

  async function initWallet() {
    if (!window.LemmaWallet) {
      throw new Error('LemmaWallet SDK not loaded');
    }
    state.wallet = state.wallet || new window.LemmaWallet();
    await state.wallet.init();

    let auth;
    try {
      auth = await state.wallet.registerPasskey();
    } catch (err) {
      log('Wallet registration failed, trying unlock', err.message);
      auth = await state.wallet.unlock();
    }

    const walletIdRecord = await state.wallet._get('passkey', 'walletId');
    const secretRecord = await state.wallet._get('secrets', 'master');
    state.walletId = auth?.walletId || walletIdRecord?.value || state.wallet.session?.walletId || '';
    state.walletSecret = auth?.walletSecret || secretRecord?.secret || state.wallet.session?.walletSecret || '';

    $('ih-wallet-id').textContent = short(state.walletId);
    setPill('ih-wallet-pill', state.walletId ? 'UNLOCKED' : 'LOCKED', state.walletId ? 'ok' : 'deny');
    log('Wallet ready', short(state.walletId));
    return auth;
  }

  async function getWalletContext() {
    if (!state.wallet) {
      await initWallet();
    }
    if (!state.walletId) {
      const walletIdRecord = await state.wallet._get('passkey', 'walletId');
      state.walletId = walletIdRecord?.value || state.wallet.session?.walletId || '';
    }
    if (!state.walletSecret) {
      const secretRecord = await state.wallet._get('secrets', 'master');
      state.walletSecret = secretRecord?.secret || state.wallet.session?.walletSecret || '';
    }
    if (!state.walletId) {
      throw new Error('Create or unlock the wallet first');
    }
    return { walletId: state.walletId, walletSecret: state.walletSecret };
  }

  async function startIdentityVerification() {
    const { walletId, walletSecret } = await getWalletContext();
    const payload = await requestJson('/api/ishuman/start-verification', {
      method: 'POST',
      body: JSON.stringify({
        wallet_id: walletId,
        wallet_secret: walletSecret,
        return_url: `${window.location.origin}${window.location.pathname}?verification_return=true`,
      }),
    });

    state.sessionId = payload.session_id;
    localStorage.setItem('ishuman_demo_session_id', state.sessionId);
    log('Stripe Identity session started', short(payload.stripe_session_id));

    if (payload.url) {
      window.location.href = payload.url;
      return;
    }
    $('ih-network-json').textContent = pretty(payload);
  }

  async function pollAndStoreMaster() {
    if (!state.sessionId) {
      throw new Error('No demo verification session. Start Stripe Identity first.');
    }
    if (!state.wallet) {
      await initWallet();
    }

    const payload = await requestJson(`/api/ishuman/verification-status/${encodeURIComponent(state.sessionId)}`);
    $('ih-network-json').textContent = pretty(payload);
    log('Verification status checked', payload.status);

    if (payload.status !== 'verified' || !payload.credential) {
      setPill('ih-wallet-pill', String(payload.status || 'PENDING').toUpperCase(), 'warn');
      return payload;
    }

    state.masterCredential = payload.credential;
    state.masterCredentialId = payload.credential_id || payload.credential.id;
    localStorage.setItem('ishuman_demo_master_id', state.masterCredentialId);
    await state.wallet.storeCredential(payload.credential);
    renderMaster(payload.credential);
    await refreshStatus();
    return payload;
  }

  async function completeTestModeVerification() {
    if (!state.sessionId) {
      throw new Error('No demo verification session. Start Stripe Identity first.');
    }
    const token = $('ih-test-token').value.trim();
    const payload = await requestJson('/api/demo/ishuman/test-complete-verification', {
      method: 'POST',
      headers: token ? { 'X-Demo-Test-Token': token } : {},
      body: JSON.stringify({ session_id: state.sessionId }),
    });
    $('ih-network-json').textContent = pretty(payload);
    log('Stripe test-mode session completed', short(payload.credential_id));
    await pollAndStoreMaster();
  }

  function renderMaster(credential) {
    const claims = credential?.claims || credential?.credentialSubject || {};
    $('ih-master-id').textContent = short(credential?.id);
    $('ih-master-issuer').textContent = short(credential?.issuer || credential?.issuerInfo?.did);
    $('ih-master-expiry').textContent = claims.expiresAt || credential?.expiresAt || '-';
    $('ih-master-json').textContent = pretty({
      id: credential?.id,
      issuer: credential?.issuer || credential?.issuerInfo?.did,
      subject: credential?.subject,
      claims,
    });
    setPill('ih-wallet-pill', 'MASTER READY', 'ok');
  }

  function verifierFor(slug) {
    return new window.IsHumanVerifier({
      siteId: SITE_IDS[slug],
      lemmaOrigin: window.location.origin,
      debug: true,
      isBlockedLocally: (ppid) => state.localBlocks[slug].has(ppid),
    });
  }

  async function verifySite(slug) {
    if (!window.IsHumanVerifier) {
      throw new Error('IsHumanVerifier SDK not loaded');
    }
    const verifier = verifierFor(slug);
    const result = await verifier.verify();
    verifier.destroy();
    state.results[slug] = result;
    renderSite(slug, result);
    log(`${SITE_IDS[slug]} verifier result`, `${result.reason} in ${result.timeMs.toFixed(1)}ms`);
    await refreshStatus();
    return result;
  }

  async function verifyBothSites() {
    await verifySite('tickets');
    await verifySite('trials');
  }

  function renderSite(slug, result) {
    const tone = result.human ? 'ok' : (result.reason === 'site_blocked' || result.reason === 'revoked' ? 'deny' : 'warn');
    setPill(`ih-${slug}-pill`, result.human ? 'HUMAN' : 'DENY', tone);
    $(`ih-${slug}-ppid`).textContent = short(result.ppid);
    $(`ih-${slug}-reason`).textContent = result.reason || '-';
    $(`ih-${slug}-latency`).textContent = Number.isFinite(result.timeMs) ? `${result.timeMs.toFixed(1)}ms` : '-';
  }

  async function blockTickets() {
    const result = state.results.tickets || await verifySite('tickets');
    if (!result.ppid) {
      throw new Error('Ticketing PPID unavailable');
    }
    const payload = await requestJson('/api/demo/ishuman/site-block', {
      method: 'POST',
      body: JSON.stringify({
        site_slug: 'tickets',
        ppid: result.ppid,
        reason: 'Demo block: automated ticketing behavior detected',
      }),
    });
    state.localBlocks.tickets.add(result.ppid);
    $('ih-network-json').textContent = pretty(payload);
    log('Ticketing site block applied', short(result.ppid));
    await verifySite('tickets');
  }

  async function unblockTickets() {
    const ppid = state.results.tickets?.ppid;
    if (!ppid) {
      throw new Error('Ticketing PPID unavailable');
    }
    const payload = await requestJson('/api/demo/ishuman/site-unblock', {
      method: 'POST',
      body: JSON.stringify({ site_slug: 'tickets', ppid }),
    });
    state.localBlocks.tickets.delete(ppid);
    $('ih-network-json').textContent = pretty(payload);
    log('Ticketing site block removed', short(ppid));
    await verifySite('tickets');
  }

  async function requestNetworkReview() {
    const result = state.results.tickets || await verifySite('tickets');
    if (!result.ppid) {
      throw new Error('Ticketing PPID unavailable');
    }
    const payload = await requestJson('/api/demo/ishuman/network-revoke-request', {
      method: 'POST',
      body: JSON.stringify({
        site_slug: 'tickets',
        ppid: result.ppid,
        credential_id: state.masterCredentialId,
        reason: 'Demo evidence: site-level block escalated for network review',
      }),
    });
    setPill('ih-network-pill', 'PENDING REVIEW', 'warn');
    $('ih-network-json').textContent = pretty(payload);
    log('Network revocation review requested', short(result.ppid));
    await refreshStatus();
  }

  async function approveNetworkRevocation() {
    const token = $('ih-admin-token').value.trim();
    const payload = await requestJson('/api/demo/ishuman/approve-network-revocation', {
      method: 'POST',
      headers: token ? { 'X-Demo-Admin-Token': token } : {},
      body: JSON.stringify({
        wallet_id: state.walletId,
        master_credential_id: state.masterCredentialId,
        reason: 'Demo network revocation approved after evidence review',
      }),
    });
    setPill('ih-network-pill', 'REVOKED', 'deny');
    $('ih-network-json').textContent = pretty(payload);
    log('Network revocation approved', `${payload.total_revoked} IDs`);
    await verifyBothSites();
  }

  async function refreshStatus() {
    const params = new URLSearchParams();
    if (state.walletId) params.set('wallet_id', state.walletId);
    if (state.masterCredentialId) params.set('master_credential_id', state.masterCredentialId);
    const payload = await requestJson(`/api/demo/ishuman/status?${params.toString()}`);
    for (const slug of SITE_SLUGS) {
      state.localBlocks[slug].clear();
    }
    const siteIdToSlug = {
      site_demo_tickets: 'tickets',
      site_demo_trials: 'trials',
    };
    for (const block of payload.site_blocks || []) {
      const slug = siteIdToSlug[block.site_id];
      if (slug && block.ppid) {
        state.localBlocks[slug].add(block.ppid);
      }
    }
    $('ih-network-json').textContent = pretty(payload);
    return payload;
  }

  function bind(id, fn) {
    const el = $(id);
    if (!el) return;
    el.addEventListener('click', async () => {
      el.disabled = true;
      try {
        await fn();
      } catch (err) {
        log('Error', err.message);
        $('ih-network-json').textContent = pretty(err.payload || { error: err.message });
      } finally {
        el.disabled = false;
      }
    });
  }

  async function boot() {
    await loadConfig();
    bind('ih-wallet-btn', initWallet);
    bind('ih-start-idv-btn', startIdentityVerification);
    bind('ih-test-complete-btn', completeTestModeVerification);
    bind('ih-poll-btn', pollAndStoreMaster);
    bind('ih-verify-sites-btn', verifyBothSites);
    bind('ih-refresh-status-btn', refreshStatus);
    bind('ih-verify-tickets-btn', () => verifySite('tickets'));
    bind('ih-verify-trials-btn', () => verifySite('trials'));
    bind('ih-block-tickets-btn', blockTickets);
    bind('ih-unblock-tickets-btn', unblockTickets);
    bind('ih-network-request-btn', requestNetworkReview);
    bind('ih-network-approve-btn', approveNetworkRevocation);

    try {
      if (state.masterCredentialId || state.sessionId) {
        await initWallet();
      }
      if (state.sessionId && new URLSearchParams(window.location.search).has('verification_return')) {
        await pollAndStoreMaster();
      } else if (state.walletId || state.masterCredentialId) {
        await refreshStatus();
      }
    } catch (err) {
      log('Startup check skipped', err.message);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
