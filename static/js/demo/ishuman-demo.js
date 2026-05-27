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
    el.className = `demo-pill${tone ? ` ${tone}` : ''}`;
  }

  function setWorkflowHighlight(workflowStep) {
    for (let i = 1; i <= 3; i += 1) {
      const el = $(`ih-step-${i}`);
      if (!el) continue;
      el.classList.remove('is-active', 'is-done');
      if (workflowStep > 0 && i < workflowStep) el.classList.add('is-done');
      else if (i === workflowStep) el.classList.add('is-active');
    }
    if (workflowStep === 0) {
      for (let i = 1; i <= 3; i += 1) {
        const el = $(`ih-step-${i}`);
        if (el) el.classList.add('is-done');
      }
    }
  }

  function workflowStepForWizard(wizardStep) {
    if (wizardStep <= 0) return 0;
    if (wizardStep <= 2) return 1;
    if (wizardStep === 3) return 2;
    return 3;
  }

  function setWizardStep(step, statusText) {
    const statusEl = $('ih-wizard-status');
    const labelEl = $('ih-wizard-step-label');
    const shell = $('ih-wizard-shell');
    if (shell) shell.hidden = false;
    if (statusEl && statusText) statusEl.textContent = statusText;
    if (labelEl) {
      labelEl.textContent = step > 0 ? `Step ${step} of ${WIZARD_TOTAL}` : 'Demo complete';
    }
    document.querySelectorAll('.wizard-dot').forEach((dot) => {
      const dotStep = Number(dot.dataset.step || 0);
      dot.classList.remove('active', 'done');
      if (step > 0 && dotStep < step) dot.classList.add('done');
      else if (dotStep === step) dot.classList.add('active');
    });
    setWorkflowHighlight(workflowStepForWizard(step));
  }

  function setDemoReadyBanner(visible) {
    const banner = $('ih-demo-ready-banner');
    if (banner) banner.hidden = !visible;
  }

  function scrollToPanel(id) {
    const el = $(id);
    if (el && el.scrollIntoView) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }

  function setDebugJson(payload) {
    const json = $('ih-master-json');
    if (json) json.textContent = pretty(payload);
  }

  async function findLocalMasterCredential() {
    if (!state.wallet) return null;
    if (typeof state.wallet.getIsHumanCredentialsFromCache === 'function') {
      const cached = await state.wallet.getIsHumanCredentialsFromCache();
      const fromCache = cached.find((c) => {
        const cl = c.claims || c.credentialSubject || {};
        const site = cl.siteId || cl.site_id || cl.siteDomain || cl.site_domain || '';
        return cl.isHuman && (site === 'lemma.id' || !site);
      });
      if (fromCache) return fromCache;
    }
    const creds = await state.wallet.getCredentials();
    return creds.find((c) => {
      const cl = c.claims || c.credentialSubject || {};
      const site = cl.siteId || cl.site_id || cl.siteDomain || cl.site_domain || '';
      return cl.isHuman && (site === 'lemma.id' || !site);
    }) || null;
  }

  function isEncryptedWalletLockedError(err) {
    const message = String(err?.message || err || '');
    return message === 'envelope_invalid'
      || message === 'storage_key_unavailable'
      || message === 'prf_required_for_encrypted_storage';
  }

  async function refreshWalletStatus() {
    try {
      await initWallet({ force: false });
      if (!state.wallet) return;

      let master = null;
      try {
        master = await findLocalMasterCredential();
      } catch (err) {
        if (isEncryptedWalletLockedError(err) && state.masterCredentialId) {
          setPill('ih-wallet-pill', 'PROOF ON SERVER', 'ok');
          setDemoReadyBanner(true);
          return;
        }
        throw err;
      }

      if (master) {
        state.masterCredential = master;
        state.masterCredentialId = master.id;
        localStorage.setItem('ishuman_demo_master_id', state.masterCredentialId);
        renderMaster(master);
        return;
      }

      if (state.masterCredentialId) {
        setPill('ih-wallet-pill', 'PROOF ON SERVER', 'ok');
        setDemoReadyBanner(true);
        return;
      }

      setPill('ih-wallet-pill', state.walletId ? 'NO PROOF YET' : 'LOCKED', state.walletId ? 'warn' : 'deny');
    } catch (err) {
      setPill('ih-wallet-pill', 'NOT READY', 'warn');
      log('Wallet status check skipped', err.message);
    }
  }

  function setWizardBusy(running) {
    state.wizardRunning = running;
    const ids = [
      'ih-run-guided-demo',
      'ih-run-guided-demo-hero',
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
    const label = running ? 'Running demo…' : 'Run full demo';
    for (const id of ['ih-run-guided-demo', 'ih-run-guided-demo-hero']) {
      const runBtn = $(id);
      if (runBtn) runBtn.textContent = label;
    }
    const shell = $('ih-wizard-shell');
    if (shell && !running && !state.masterCredentialId) shell.hidden = true;
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

  function applyTestVerifyGate() {
    const enabled = !!(state.config && state.config.test_verify_enabled);
    const notice = $('ih-test-verify-disabled');
    const guidedIds = ['ih-run-guided-demo', 'ih-run-guided-demo-hero'];
    const operatorConsole = $('ih-operator-console');
    const testIds = [
      'ih-start-idv-btn',
      'ih-test-complete-btn',
      'ih-force-reverify-btn',
      'ih-poll-btn',
    ];
    if (notice) notice.hidden = enabled;
    for (const id of guidedIds) {
      const el = $(id);
      if (el) el.hidden = !enabled;
    }
    if (operatorConsole) operatorConsole.hidden = !enabled;
    for (const id of testIds) {
      const el = $(id);
      if (el) el.hidden = !enabled;
    }
  }

  async function loadConfig() {
    state.config = await requestJson('/api/demo/ishuman/config');
    const root = $('ishuman-demo');
    if (root) {
      state.serverTestToken = root.dataset.serverTestToken || '';
      state.serverAdminToken = root.dataset.serverAdminToken || '';
    }
    applyTestVerifyGate();
    log('Demo config loaded', `${state.config.sites.length} sites`);
    updatePpidCompare();
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

  async function adoptCurrentWalletState(source) {
    let walletIdRecord = null;
    try {
      walletIdRecord = await state.wallet._get('passkey', 'walletId');
    } catch (err) {
      log('Wallet id read skipped', err.message);
    }
    state.walletId = walletIdRecord?.value || state.wallet.session?.walletId || '';
    state.walletSecret = state.wallet.session?.walletSecret || '';
    if (!state.walletSecret) {
      try {
        const secretRecord = await state.wallet._get('secrets', 'master');
        state.walletSecret = secretRecord?.secret || '';
      } catch (err) {
        if (!isEncryptedWalletLockedError(err)) throw err;
      }
    }
    const wid = $('ih-wallet-id');
    if (wid) wid.textContent = short(state.walletId);
    if (state.walletId) {
      setPill('ih-wallet-pill', 'UNLOCKED', 'ok');
      log('Wallet ready', `${source} · ${short(state.walletId)}`);
    } else {
      setPill('ih-wallet-pill', 'LOCKED', 'deny');
    }
  }

  async function initWallet({ force = false } = {}) {
    if (!window.LemmaWallet) throw new Error('LemmaWallet SDK not loaded');
    state.wallet = state.wallet || new window.LemmaWallet();

    let readyMethod = 'passkey';
    if (typeof state.wallet.ensureIsHumanIssuanceReady === 'function') {
      const ready = await state.wallet.ensureIsHumanIssuanceReady({
        isHumanIssuance: true,
        force,
      });
      if (!ready.ready) {
        throw new Error('Wallet unlock failed');
      }
      readyMethod = ready.method || readyMethod;
    } else {
      await state.wallet.init();
      const existingPasskey = await state.wallet._get('passkey', 'primary');
      let auth;
      if (existingPasskey && existingPasskey.credentialId) {
        auth = await state.wallet.unlock({ force, isHumanIssuance: true });
      } else {
        try {
          auth = await state.wallet.registerPasskey({ isHumanIssuance: true });
        } catch (err) {
          log('Wallet registration failed, trying unlock', err.message);
          auth = await state.wallet.unlock({ force, isHumanIssuance: true });
        }
      }
      if (!auth?.success && auth?.needsRedirect) {
        throw new Error(auth.message || 'Wallet unlock failed');
      }
    }

    await adoptCurrentWalletState(readyMethod);
    const authWalletId = state.wallet.session?.walletId;
    const authSecret = state.wallet.session?.walletSecret;
    if (!state.walletId && authWalletId) {
      state.walletId = authWalletId;
      const wid = $('ih-wallet-id');
      if (wid) wid.textContent = short(state.walletId);
    }
    if (!state.walletSecret && authSecret) {
      state.walletSecret = authSecret;
    }
    return { success: true, walletId: state.walletId, method: readyMethod };
  }

  async function getWalletContext() {
    if (!state.wallet) await initWallet();
    if (!state.walletId) {
      try {
        const walletIdRecord = await state.wallet._get('passkey', 'walletId');
        state.walletId = walletIdRecord?.value || state.wallet.session?.walletId || '';
      } catch (err) {
        if (!isEncryptedWalletLockedError(err)) throw err;
        state.walletId = state.wallet.session?.walletId || '';
      }
    }
    if (!state.walletSecret) {
      state.walletSecret = state.wallet.session?.walletSecret || '';
      if (!state.walletSecret) {
        try {
          const secretRecord = await state.wallet._get('secrets', 'master');
          state.walletSecret = secretRecord?.secret || '';
        } catch (err) {
          if (!isEncryptedWalletLockedError(err)) throw err;
        }
      }
    }
    if (!state.walletId) throw new Error('Create or unlock the wallet first');
    return { walletId: state.walletId, walletSecret: state.walletSecret };
  }

  async function startIdentityVerification() {
    const { walletId, walletSecret } = await getWalletContext();
    if (!state.wallet) await initWallet();
    const returnUrl = `${window.location.origin}${window.location.pathname}?verification_return=true`;
    const walletAssertion = await state.wallet.buildWalletAssertion(['return_url'], { return_url: returnUrl });
    const payload = await requestJson('/api/ishuman/start-verification', {
      method: 'POST',
      body: JSON.stringify({
        wallet_id: walletId,
        wallet_secret: walletSecret,
        return_url: returnUrl,
        wallet_assertion: walletAssertion,
      }),
    });

    state.sessionId = payload.session_id;
    localStorage.setItem('ishuman_demo_session_id', state.sessionId);
    log('Stripe Identity session started', short(payload.stripe_session_id));

    if (payload.url) {
      window.location.href = payload.url;
      return;
    }
    const netJson = $('ih-master-json');
    if (netJson) netJson.textContent = pretty(payload);
  }

  async function pollAndStoreMaster() {
    if (!state.sessionId) throw new Error('No demo verification session. Start Stripe Identity first.');
    if (!state.wallet) await initWallet();

    const payload = await requestJson(`/api/ishuman/verification-status/${encodeURIComponent(state.sessionId)}`);
    const netJson = $('ih-master-json');
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
    await refreshStatus();
    return payload;
  }

  async function verifyOnceTestMode() {
    const { walletId, walletSecret } = await getWalletContext();
    if (!state.wallet) await initWallet();
    const returnUrl = `${window.location.origin}${window.location.pathname}?verification_return=true`;
    const walletAssertion = await state.wallet.buildWalletAssertion(['return_url'], { return_url: returnUrl });
    const payload = await requestJson('/api/demo/ishuman/verify-once-test-mode', {
      method: 'POST',
      headers: demoHeaders(),
      body: JSON.stringify({
        wallet_id: walletId,
        wallet_secret: walletSecret,
        return_url: returnUrl,
        wallet_assertion: walletAssertion,
      }),
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
    log('One-click test verify complete', short(payload.credential_id));
    setDebugJson(payload);
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
    const json = $('ih-master-json');
    if (json) {
      json.textContent = pretty({
        id: credential?.id,
        issuer: credential?.issuer || credential?.issuerInfo?.did,
        subject: credential?.subject,
        claims,
      });
    }
    setPill('ih-wallet-pill', 'PROOF READY', 'ok');
    setDemoReadyBanner(true);
  }

  function verifierFor(slug) {
    return new window.IsHumanVerifier({
      siteId: SITE_IDS[slug],
      lemmaOrigin: window.location.origin,
      debug: true,
      autoProvision: true,
      isBlockedLocally: (ppid) => state.localBlocks[slug].has(ppid),
    });
  }

  async function verifySite(slug) {
    if (!window.IsHumanVerifier) throw new Error('IsHumanVerifier SDK not loaded');
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
    const card = $(`ih-${slug}-card`);
    if (card) {
      card.classList.remove('is-human', 'is-deny', 'is-pending');
      if (result.human) card.classList.add('is-human');
      else if (result.reason === 'site_blocked' || result.reason === 'revoked') card.classList.add('is-deny');
      else card.classList.add('is-pending');
    }
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
    if (!ppid) return;
    try {
      const withSite = await fetchCheck(ppid, 'site_demo_tickets');
      const deriveEl = $('ih-abuse-derive');
      if (deriveEl && withSite.blocked) {
        deriveEl.textContent = `check(site_id): blocked — ${withSite.reason}`;
        deriveEl.className = 'abuse-outcome deny';
      }
    } catch (err) {
      log('Abuse check failed', err.message);
    }
  }

  async function probeDerive(slug) {
    const { walletId, walletSecret } = await getWalletContext();
    if (!state.wallet) await initWallet();
    const walletAssertion = await state.wallet.buildWalletAssertion(
      ['site_slug', 'master_credential_id'],
      { site_slug: slug, master_credential_id: state.masterCredentialId },
    );
    const payload = await requestJson('/api/demo/ishuman/probe-derive', {
      method: 'POST',
      body: JSON.stringify({
        site_slug: slug,
        wallet_id: walletId,
        wallet_secret: walletSecret,
        master_credential_id: state.masterCredentialId,
        wallet_assertion: walletAssertion,
      }),
    });
    const el = $('ih-abuse-derive');
    if (el) {
      if (payload.allowed) {
        el.textContent = 'Server enforcement: allowed';
        el.className = 'abuse-outcome';
      } else {
        el.textContent = `Server enforcement: blocked (${payload.error})`;
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
    const netJson = $('ih-master-json');
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
    const netJson = $('ih-master-json');
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
    const netJson = $('ih-master-json');
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
    const netJson = $('ih-master-json');
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

    if (!state.wallet) await initWallet();
    const walletAssertion = await state.wallet.buildWalletAssertion(
      ['ppid', 'master_credential_id'],
      { ppid: result.ppid, master_credential_id: state.masterCredentialId },
    );
    const payload = await requestJson('/api/demo/ishuman/force-reverify', {
      method: 'POST',
      body: JSON.stringify({
        ppid: result.ppid,
        wallet_id: walletId,
        master_credential_id: state.masterCredentialId,
        wallet_assertion: walletAssertion,
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

  async function ensureMasterForDemo() {
    const status = await refreshStatus();
    if (status.master?.status === 'verified') {
      state.masterCredentialId = status.master.credential_id || state.masterCredentialId;
      if (state.masterCredentialId) {
        localStorage.setItem('ishuman_demo_master_id', state.masterCredentialId);
      }
      setPill('ih-wallet-pill', 'PROOF READY', 'ok');
      setDemoReadyBanner(true);
      log('Using verified master proof from server', short(state.masterCredentialId));
      return status;
    }

    try {
      const localMaster = await findLocalMasterCredential();
      if (localMaster) {
        state.masterCredential = localMaster;
        state.masterCredentialId = localMaster.id;
        localStorage.setItem('ishuman_demo_master_id', state.masterCredentialId);
        renderMaster(localMaster);
        return { master: { status: 'verified', credential_id: localMaster.id } };
      }
    } catch (err) {
      if (!isEncryptedWalletLockedError(err)) throw err;
    }

    if (state.config?.test_verify_enabled) {
      return verifyOnceTestMode();
    }

    throw new Error('No verified master proof yet. Complete verification on a demo site, or use Stripe Identity from the operator console.');
  }

  async function runGuidedDemo() {
    if (state.wizardRunning) return;
    setWizardBusy(true);
    scrollToPanel('ih-demo-cockpit');
    try {
      setWizardStep(1, 'Unlocking wallet…');
      await initWallet();

      setWizardStep(2, 'Confirming human proof…');
      await ensureMasterForDemo();

      setWizardStep(3, 'Verifying both customer sites…');
      await verifyBothSites();

      setWizardStep(4, 'Blocking abusive ticketing ID…');
      scrollToPanel('ih-abuse-panel');
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

      setWizardStep(0, 'Demo complete — both sites denied at network layer.');
      setDemoReadyBanner(true);
      log('Guided demo complete');
    } catch (err) {
      log('Wizard stopped', err.message);
      setWizardStep(0, `Stopped: ${err.message}. Open Operator console or Demo log for details.`);
      const netJson = $('ih-master-json');
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
    const netJson = $('ih-master-json');
    if (netJson) netJson.textContent = pretty(payload);
    if (state.masterCredentialId) {
      setDemoReadyBanner(true);
    }
    return payload;
  }

  function bind(id, fn) {
    const el = $(id);
    if (!el) return;
    el.addEventListener('click', async () => {
      if (state.wizardRunning && id !== 'ih-run-guided-demo' && id !== 'ih-run-guided-demo-hero') return;
      el.disabled = true;
      try {
        await fn();
      } catch (err) {
        log('Error', err.message);
        const netJson = $('ih-master-json');
        if (netJson) netJson.textContent = pretty(err.payload || { error: err.message });
      } finally {
        if (!state.wizardRunning) el.disabled = false;
      }
    });
  }

  async function boot() {
    setWorkflowHighlight(1);
    await loadConfig();
    bind('ih-run-guided-demo', runGuidedDemo);
    bind('ih-run-guided-demo-hero', runGuidedDemo);
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

    try {
      const isVerificationReturn =
        state.sessionId && new URLSearchParams(window.location.search).has('verification_return');
      if (isVerificationReturn) {
        await initWallet();
        await pollAndStoreMaster();
      } else {
        await refreshWalletStatus();
        if (state.masterCredentialId || state.sessionId) {
          await refreshStatus();
          setPill('ih-wallet-pill', 'CACHED', 'ok');
        }
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
