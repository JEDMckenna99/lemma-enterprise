(function () {
  'use strict';

  const SITE_SLUGS = ['tickets', 'trials'];
  const SITE_IDS = {
    tickets: 'tickets-demo.lemma.id',
    trials: 'trials-demo.lemma.id',
  };
  const WIZARD_TOTAL = 7;

  const state = {
    config: null,
    wallet: null,
    walletId: null,
    walletSecret: null,
    sessionId: localStorage.getItem('ishuman_demo_session_id') || '',
    masterCredential: null,
    masterCredentialId: localStorage.getItem('ishuman_demo_master_id') || '',
    results: {},
    localBlocks: { tickets: new Set(), trials: new Set() },
    wizardRunning: false,
    lastVerifyMs: { tickets: null, trials: null },
    serverTestToken: '',
    serverAdminToken: '',
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
    const logEl = $('ih-log');
    if (!logEl) return;
    const row = document.createElement('div');
    const time = new Date().toLocaleTimeString();
    row.textContent = `[${time}] ${message}${detail ? `: ${detail}` : ''}`;
    logEl.prepend(row);
  }

  function setPill(id, label, tone) {
    const el = $(id);
    if (!el) return;
    el.textContent = label;
    el.className = `pill${tone ? ` ${tone}` : ''}`;
  }

  function setWizardStep(n, statusText) {
    const stepEl = $('ih-wizard-step');
    const statusEl = $('ih-wizard-status');
    if (stepEl) stepEl.textContent = n > WIZARD_TOTAL ? 'Complete' : `Step ${n}/${WIZARD_TOTAL}`;
    if (statusEl && statusText) statusEl.textContent = statusText;
  }

  function setDemoReady(visible) {
    const banner = $('ih-demo-ready');
    if (banner) banner.classList.toggle('visible', !!visible);
  }

  function setWizardBusy(running) {
    state.wizardRunning = running;
    const ids = [
      'ih-run-guided-demo',
      'ih-wallet-btn',
      'ih-verify-sites-btn',
      'ih-block-tickets-btn',
      'ih-network-request-btn',
      'ih-verify-tickets-btn',
      'ih-verify-trials-btn',
      'ih-unblock-tickets-btn',
      'ih-abuse-block-btn',
      'ih-abuse-verify-trials-btn',
      'ih-abuse-network-btn',
      'ih-force-reverify-btn',
    ];
    for (const id of ids) {
      const el = $(id);
      if (el) el.disabled = running;
    }
    const runBtn = $('ih-run-guided-demo');
    if (runBtn) runBtn.textContent = running ? 'Running demo…' : 'Run 3-minute demo';
  }

  function demoHeaders() {
    const headers = {};
    const testToken = ($('ih-test-token') && $('ih-test-token').value.trim()) || state.serverTestToken;
    const adminToken = ($('ih-admin-token') && $('ih-admin-token').value.trim()) || state.serverAdminToken;
    if (testToken) headers['X-Demo-Test-Token'] = testToken;
    if (adminToken) headers['X-Demo-Admin-Token'] = adminToken;
    return headers;
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
      err.status = res.status;
      throw err;
    }
    return data;
  }

  async function loadConfig() {
    state.config = await requestJson('/api/demo/ishuman/config');
    const root = $('ishuman-demo');
    if (root) {
      state.serverTestToken = root.dataset.serverTestToken || '';
      state.serverAdminToken = root.dataset.serverAdminToken || '';
    }
    const netJson = $('ih-network-json');
    if (netJson) netJson.textContent = pretty(state.config);
    log('Demo config loaded', `${state.config.sites.length} sites`);
    updatePpidCompare();
    await loadStats();
  }

  async function loadStats() {
    try {
      const stats = await requestJson('/api/ishuman/stats');
      const el = $('ih-stats-body');
      if (!el) return;
      el.textContent = [
        `Verifications: ${stats.total_verifications ?? 0}`,
        `Active site blocks: ${stats.active_site_blocks ?? 0}`,
        `Network revocations: ${stats.network_revocations ?? 0}`,
        `IDV cost: $${stats.verification_cost_usd ?? 2}`,
      ].join(' · ');
    } catch (err) {
      const el = $('ih-stats-body');
      if (el) el.textContent = 'Stats unavailable';
    }
  }

  function updateIntegrationLatency() {
    const el = $('ih-integration-latency');
    if (!el) return;
    const parts = [];
    if (state.lastVerifyMs.tickets != null) parts.push(`tickets ${state.lastVerifyMs.tickets.toFixed(0)}ms`);
    if (state.lastVerifyMs.trials != null) parts.push(`trials ${state.lastVerifyMs.trials.toFixed(0)}ms`);
    el.textContent = parts.length ? `Last verify: ${parts.join(' · ')}` : 'Last verify: —';
  }

  function updatePpidCompare() {
    const t = $('ih-tickets-ppid') && $('ih-tickets-ppid').textContent;
    const r = $('ih-trials-ppid') && $('ih-trials-ppid').textContent;
    const tCmp = $('ih-tickets-ppid-compare');
    const rCmp = $('ih-trials-ppid-compare');
    if (tCmp && t) tCmp.textContent = t;
    if (rCmp && r) rCmp.textContent = r;
    const diff = $('ih-ppid-diff');
    if (!diff || !t || !r || t === '-' || r === '-') {
      if (diff) diff.textContent = 'Verify both sites to compare';
      return;
    }
    diff.textContent = t !== r ? 'Different site IDs ✓' : 'Same (unexpected)';
    diff.className = t !== r ? 'ppid-diff' : 'ppid-diff deny';
  }

  async function copyText(text) {
    if (!text || text === '-') return;
    try {
      await navigator.clipboard.writeText(text);
      log('Copied', short(text));
    } catch (err) {
      log('Copy failed', err.message);
    }
  }

  async function initWallet() {
    if (!window.LemmaWallet) throw new Error('LemmaWallet SDK not loaded');
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

    const wid = $('ih-wallet-id');
    if (wid) wid.textContent = short(state.walletId);
    setPill('ih-wallet-pill', state.walletId ? 'UNLOCKED' : 'LOCKED', state.walletId ? 'ok' : 'deny');
    log('Wallet ready', short(state.walletId));
    return auth;
  }

  async function getWalletContext() {
    if (!state.wallet) await initWallet();
    if (!state.walletId) {
      const walletIdRecord = await state.wallet._get('passkey', 'walletId');
      state.walletId = walletIdRecord?.value || state.wallet.session?.walletId || '';
    }
    if (!state.walletSecret) {
      const secretRecord = await state.wallet._get('secrets', 'master');
      state.walletSecret = secretRecord?.secret || state.wallet.session?.walletSecret || '';
    }
    if (!state.walletId) throw new Error('Create or unlock the wallet first');
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
    const netJson = $('ih-network-json');
    if (netJson) netJson.textContent = pretty(payload);
  }

  async function pollAndStoreMaster() {
    if (!state.sessionId) throw new Error('No demo verification session. Start Stripe Identity first.');
    if (!state.wallet) await initWallet();

    const payload = await requestJson(`/api/ishuman/verification-status/${encodeURIComponent(state.sessionId)}`);
    const netJson = $('ih-network-json');
    if (netJson) netJson.textContent = pretty(payload);
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
    setDemoReady(true);
    await refreshStatus();
    return payload;
  }

  async function verifyOnceTestMode() {
    const { walletId, walletSecret } = await getWalletContext();
    const payload = await requestJson('/api/demo/ishuman/verify-once-test-mode', {
      method: 'POST',
      headers: demoHeaders(),
      body: JSON.stringify({ wallet_id: walletId, wallet_secret: walletSecret }),
    });

    state.sessionId = payload.session_id;
    localStorage.setItem('ishuman_demo_session_id', state.sessionId);
    state.masterCredentialId = payload.credential_id;
    localStorage.setItem('ishuman_demo_master_id', state.masterCredentialId);
    state.masterCredential = payload.credential;

    if (state.wallet && payload.credential) {
      await state.wallet.storeCredential(payload.credential);
    }
    renderMaster(payload.credential);
    setDemoReady(true);
    log('One-click test verify complete', short(payload.credential_id));
    const netJson = $('ih-network-json');
    if (netJson) netJson.textContent = pretty(payload);
    return payload;
  }

  async function completeTestModeVerification() {
    if (!state.sessionId) throw new Error('No demo verification session. Start Stripe Identity first.');
    await requestJson('/api/demo/ishuman/test-complete-verification', {
      method: 'POST',
      headers: demoHeaders(),
      body: JSON.stringify({ session_id: state.sessionId }),
    });
    log('Stripe test-mode session completed');
    await pollAndStoreMaster();
  }

  function renderMaster(credential) {
    const claims = credential?.claims || credential?.credentialSubject || {};
    const mid = $('ih-master-id');
    if (mid) mid.textContent = short(credential?.id);
    const iss = $('ih-master-issuer');
    if (iss) iss.textContent = short(credential?.issuer || credential?.issuerInfo?.did);
    const exp = $('ih-master-expiry');
    if (exp) exp.textContent = claims.expiresAt || credential?.expiresAt || '-';
    const json = $('ih-master-json');
    if (json) {
      json.textContent = pretty({
        id: credential?.id,
        issuer: credential?.issuer || credential?.issuerInfo?.did,
        subject: credential?.subject,
        claims,
      });
    }
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
    if (!window.IsHumanVerifier) throw new Error('IsHumanVerifier SDK not loaded');
    if (!state.walletId && !state.masterCredentialId) {
      throw new Error('Create wallet and complete verification first');
    }
    const verifier = verifierFor(slug);
    const result = await verifier.verify();
    verifier.destroy();
    state.results[slug] = result;
    if (Number.isFinite(result.timeMs)) state.lastVerifyMs[slug] = result.timeMs;
    renderSite(slug, result);
    updateIntegrationLatency();
    updatePpidCompare();
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
    const ppidEl = $(`ih-${slug}-ppid`);
    if (ppidEl) ppidEl.textContent = result.ppid || '-';
    const reasonEl = $(`ih-${slug}-reason`);
    if (reasonEl) reasonEl.textContent = result.reason || '-';
    const latEl = $(`ih-${slug}-latency`);
    if (latEl) latEl.textContent = Number.isFinite(result.timeMs) ? `${result.timeMs.toFixed(1)}ms` : '-';
    updatePpidCompare();
  }

  async function fetchCheck(ppid, siteId) {
    const params = new URLSearchParams({ ppid });
    if (siteId) params.set('site_id', siteId);
    return requestJson(`/api/ishuman/check?${params.toString()}`);
  }

  async function refreshAbuseChecks() {
    const ppid = state.results.tickets?.ppid;
    const siteCheck = $('ih-abuse-site-check');
    const globalCheck = $('ih-abuse-global-check');
    if (!ppid) {
      if (siteCheck) siteCheck.textContent = 'Run verify on ticketing first';
      if (globalCheck) globalCheck.textContent = '';
      return;
    }
    try {
      const withSite = await fetchCheck(ppid, 'site_demo_tickets');
      if (siteCheck) {
        siteCheck.textContent = withSite.blocked
          ? `check(site_id): blocked — ${withSite.reason}`
          : 'check(site_id): not blocked';
        siteCheck.className = `abuse-outcome${withSite.blocked ? ' deny' : ''}`;
      }
      const noSite = await fetchCheck(ppid, '');
      if (globalCheck) {
        globalCheck.textContent = noSite.blocked
          ? `check(global): blocked — ${noSite.reason}`
          : 'check(global): not blocked';
        globalCheck.className = `abuse-outcome${noSite.blocked ? ' deny' : ''}`;
      }
    } catch (err) {
      if (siteCheck) siteCheck.textContent = `Check failed: ${err.message}`;
    }
  }

  async function probeDerive(slug) {
    const { walletId, walletSecret } = await getWalletContext();
    const payload = await requestJson('/api/demo/ishuman/probe-derive', {
      method: 'POST',
      body: JSON.stringify({
        site_slug: slug,
        wallet_id: walletId,
        wallet_secret: walletSecret,
        master_credential_id: state.masterCredentialId,
      }),
    });
    const el = $('ih-abuse-derive');
    if (el) {
      if (payload.allowed) {
        el.textContent = 'Server derive: allowed';
        el.className = 'abuse-outcome';
      } else {
        el.textContent = `Server derive: blocked (${payload.error})`;
        el.className = 'abuse-outcome deny';
      }
    }
    return payload;
  }

  async function blockTickets() {
    const result = state.results.tickets || await verifySite('tickets');
    if (!result.ppid) throw new Error('Ticketing PPID unavailable');

    const payload = await requestJson('/api/demo/ishuman/site-block', {
      method: 'POST',
      body: JSON.stringify({
        site_slug: 'tickets',
        ppid: result.ppid,
        reason: 'Demo block: automated ticketing behavior detected',
      }),
    });
    state.localBlocks.tickets.add(result.ppid);
    const netJson = $('ih-network-json');
    if (netJson) netJson.textContent = pretty(payload);
    log('Ticketing site block applied', short(result.ppid));

    const outcome = $('ih-abuse-block-outcome');
    if (outcome) {
      outcome.textContent = `tickets DENY · revocation_synced: ${payload.revocation_synced}`;
      outcome.className = 'abuse-outcome deny';
    }

    await verifySite('tickets');
    await refreshAbuseChecks();
    await probeDerive('tickets');
  }

  async function unblockTickets() {
    const ppid = state.results.tickets?.ppid;
    if (!ppid) throw new Error('Ticketing PPID unavailable');
    const payload = await requestJson('/api/demo/ishuman/site-unblock', {
      method: 'POST',
      body: JSON.stringify({ site_slug: 'tickets', ppid }),
    });
    state.localBlocks.tickets.delete(ppid);
    const netJson = $('ih-network-json');
    if (netJson) netJson.textContent = pretty(payload);
    log('Ticketing site block removed', short(ppid));
    await verifySite('tickets');
    await refreshAbuseChecks();
  }

  async function requestNetworkReview() {
    const result = state.results.tickets || await verifySite('tickets');
    if (!result.ppid) throw new Error('Ticketing PPID unavailable');
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
    const netJson = $('ih-network-json');
    if (netJson) netJson.textContent = pretty(payload);
    log('Network revocation review requested', short(result.ppid));
    const outcome = $('ih-abuse-network-outcome');
    if (outcome) outcome.textContent = 'Network review: pending';
    await refreshStatus();
  }

  async function approveNetworkRevocation() {
    if (!state.walletId && !state.masterCredentialId) {
      throw new Error('Create wallet and complete verification first');
    }
    const payload = await requestJson('/api/demo/ishuman/approve-network-revocation', {
      method: 'POST',
      headers: demoHeaders(),
      body: JSON.stringify({
        wallet_id: state.walletId,
        master_credential_id: state.masterCredentialId,
        reason: 'Demo network revocation approved after evidence review',
      }),
    });
    setPill('ih-network-pill', 'REVOKED', 'deny');
    const netJson = $('ih-network-json');
    if (netJson) netJson.textContent = pretty(payload);
    log('Network revocation approved', `${payload.total_revoked} IDs`);
    const outcome = $('ih-abuse-network-outcome');
    if (outcome) {
      outcome.textContent = `Both sites DENY · revoked (${payload.total_revoked} IDs)`;
      outcome.className = 'abuse-outcome deny';
    }
    await verifyBothSites();
  }

  async function forceFreshIdv() {
    const result = state.results.tickets || await verifySite('tickets');
    if (!result.ppid) throw new Error('Ticketing PPID unavailable');
    const { walletId } = await getWalletContext();

    const payload = await requestJson('/api/demo/ishuman/force-reverify', {
      method: 'POST',
      body: JSON.stringify({
        ppid: result.ppid,
        wallet_id: walletId,
        master_credential_id: state.masterCredentialId,
      }),
    });

    for (const credId of payload.cleared_derived_credential_ids || []) {
      try {
        if (state.wallet && state.wallet.removeCredential) {
          await state.wallet.removeCredential(credId);
        }
      } catch (err) {
        log('Could not clear derived credential locally', err.message);
      }
    }
    state.localBlocks.tickets.add(result.ppid);
    log('Force reverify: ticketing blocked', short(result.ppid));
    await verifySite('tickets');

    const reverifyPayload = await verifyOnceTestMode();
    await verifySite('tickets');
    log('Force reverify complete', short(reverifyPayload.credential_id));
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async function runGuidedDemo() {
    if (state.wizardRunning) return;
    setWizardBusy(true);
    try {
      setWizardStep(1, 'Unlocking wallet…');
      await initWallet();

      setWizardStep(2, 'One-click human proof (test mode)…');
      await verifyOnceTestMode();

      setWizardStep(3, 'Verifying both customer sites…');
      await verifyBothSites();

      setWizardStep(4, 'Blocking abusive ticketing PPID…');
      await blockTickets();

      setWizardStep(5, 'Pause — site block is scoped to ticketing only…');
      await sleep(2000);
      const trials = await verifySite('trials');
      const trialsOutcome = $('ih-abuse-scoped-outcome');
      if (trialsOutcome) {
        trialsOutcome.textContent = trials.human
          ? 'trials still HUMAN after ticketing block ✓'
          : `trials unexpected: ${trials.reason}`;
        trialsOutcome.className = trials.human ? 'abuse-outcome' : 'abuse-outcome deny';
      }

      setWizardStep(6, 'Requesting network review…');
      await requestNetworkReview();

      setWizardStep(7, 'Approving network revocation…');
      await approveNetworkRevocation();

      setWizardStep(8, 'Demo complete — both sites denied at network layer.');
      const summary = $('ih-wizard-summary');
      if (summary) {
        summary.textContent = 'Guided demo finished: verify once → two PPIDs → site block → trials still human → network revoke → both DENY.';
        summary.style.display = 'block';
      }
      log('Guided demo complete');
    } catch (err) {
      log('Wizard stopped', err.message);
      setWizardStep(0, `Stopped: ${err.message}. Open Operator console or Demo log for details.`);
      const netJson = $('ih-network-json');
      if (netJson) netJson.textContent = pretty(err.payload || { error: err.message });
      throw err;
    } finally {
      setWizardBusy(false);
    }
  }

  async function refreshStatus() {
    const params = new URLSearchParams();
    if (state.walletId) params.set('wallet_id', state.walletId);
    if (state.masterCredentialId) params.set('master_credential_id', state.masterCredentialId);
    const payload = await requestJson(`/api/demo/ishuman/status?${params.toString()}`);
    for (const slug of SITE_SLUGS) state.localBlocks[slug].clear();
    const siteIdToSlug = { site_demo_tickets: 'tickets', site_demo_trials: 'trials' };
    for (const block of payload.site_blocks || []) {
      const slug = siteIdToSlug[block.site_id];
      if (slug && block.ppid) state.localBlocks[slug].add(block.ppid);
    }
    const netJson = $('ih-network-json');
    if (netJson) netJson.textContent = pretty(payload);
    if (state.masterCredentialId) setDemoReady(true);
    return payload;
  }

  function bind(id, fn) {
    const el = $(id);
    if (!el) return;
    el.addEventListener('click', async () => {
      if (state.wizardRunning && id !== 'ih-run-guided-demo') return;
      el.disabled = true;
      try {
        await fn();
      } catch (err) {
        log('Error', err.message);
        const netJson = $('ih-network-json');
        if (netJson) netJson.textContent = pretty(err.payload || { error: err.message });
      } finally {
        if (!state.wizardRunning) el.disabled = false;
      }
    });
  }

  async function boot() {
    await loadConfig();
    bind('ih-run-guided-demo', runGuidedDemo);
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
    bind('ih-abuse-block-btn', blockTickets);
    bind('ih-abuse-verify-trials-btn', () => verifySite('trials'));
    bind('ih-abuse-network-btn', async () => {
      await requestNetworkReview();
      await approveNetworkRevocation();
    });
    bind('ih-force-reverify-btn', forceFreshIdv);
    bind('ih-stats-refresh-btn', loadStats);

    const copyTickets = $('ih-copy-tickets-ppid');
    const copyTrials = $('ih-copy-trials-ppid');
    if (copyTickets) {
      copyTickets.addEventListener('click', () => {
        const el = $('ih-tickets-ppid');
        if (el) copyText(el.textContent);
      });
    }
    if (copyTrials) {
      copyTrials.addEventListener('click', () => {
        const el = $('ih-trials-ppid');
        if (el) copyText(el.textContent);
      });
    }

    try {
      if (state.masterCredentialId || state.sessionId) await initWallet();
      if (state.sessionId && new URLSearchParams(window.location.search).has('verification_return')) {
        await pollAndStoreMaster();
      } else if (state.walletId || state.masterCredentialId) {
        await refreshStatus();
        if (state.masterCredentialId) setDemoReady(true);
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
