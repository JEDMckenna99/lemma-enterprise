(function () {
  'use strict';

  const SITE_SLUGS = ['tickets', 'trials'];
  const SITE_IDS = {
    tickets: 'tickets-demo.lemma.id',
    trials: 'trials-demo.lemma.id',
  };
  const WIZARD_TOTAL = 6;
  const LEGACY_WIZARD_TOTAL = 7;

  const PPID_PLACEHOLDER = {
    tickets: 'ppid_ticketing_••••',
    trials: 'ppid_trials_••••',
  };

  const state = {
    config: null,
    demoMode: null,
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
    passkeyPpids: {},
    assuranceStatus: null,
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
    const display = id === 'ih-lemma-status' ? formatLemmaStatus(label) : label;
    el.textContent = display;
    el.className = `demo-pill${tone ? ` ${tone}` : ''}`;
  }

  function assuranceDemoMode() {
    return !!(state.config && state.config.assurance_demo_mode);
  }

  function workflowStepCount() {
    return assuranceDemoMode() ? 5 : 3;
  }

  function isMasterReady() {
    return !!(state.masterCredentialId || state.masterCredential);
  }

  function isStep1Ready() {
    if (assuranceDemoMode()) {
      return !!state.walletId;
    }
    return isMasterReady();
  }

  function bothSitesVerified() {
    return SITE_SLUGS.every((slug) => {
      const r = state.results[slug];
      return !!(r && r.human && r.ppid);
    });
  }

  function updateStepLocks() {
    const ready = isStep1Ready();
    const bothVerified = bothSitesVerified();
    const blockStepId = assuranceDemoMode() ? 4 : 4;
    for (let i = 1; i <= 5; i += 1) {
      const el = $(`ih-step-${i}`);
      if (!el) continue;
      if (assuranceDemoMode() && i === 3 && el.hidden) continue;
      if (assuranceDemoMode() && i === 5 && el.hidden) continue;
      if (!assuranceDemoMode() && (i === 3 || i === 5)) continue;
      if (i === 1) el.classList.remove('is-locked');
      else if (i === 2) el.classList.toggle('is-locked', !ready);
      else if (i === 3 && assuranceDemoMode()) el.classList.toggle('is-locked', !bothVerified);
      else if (i === blockStepId) el.classList.toggle('is-locked', !bothVerified);
      else if (i === 5 && assuranceDemoMode()) {
        const blocked = state.results.tickets && !state.results.tickets.human
          && state.results.tickets.reason === 'site_blocked';
        el.classList.toggle('is-locked', !blocked);
      }
    }
  }

  function setWorkflowHighlight(workflowStep) {
    for (let i = 1; i <= 5; i += 1) {
      const el = $(`ih-step-${i}`);
      if (!el) continue;
      if (!assuranceDemoMode() && (i === 3 || i === 5)) continue;
      el.classList.remove('is-active', 'is-done');
      if (workflowStep > 0 && i < workflowStep) el.classList.add('is-done');
      else if (i === workflowStep) el.classList.add('is-active');
    }
    if (workflowStep === 0) {
      for (let i = 1; i <= 5; i += 1) {
        const el = $(`ih-step-${i}`);
        if (!el) continue;
        if (!assuranceDemoMode() && (i === 3 || i === 5)) continue;
        el.classList.add('is-done');
      }
    }
    updateStepLocks();
  }

  function applyAssuranceModeUI() {
    const on = assuranceDemoMode();
    document.querySelectorAll('.assurance-only').forEach((el) => {
      el.hidden = !on;
    });
    const blockTitle = $('ih-block-step-title');
    if (blockTitle) {
      blockTitle.textContent = on
        ? 'Step 4 — Block abuse on one site'
        : 'Step 3 — Block abuse on one site';
    }
    const step1Title = $('ih-step1-title');
    const step1Desc = $('ih-step1-desc');
    const step2Title = $('ih-step2-title');
    const step2Desc = $('ih-step2-desc');
    const intro = $('ih-intro-lead');
    const createBtn = $('ih-create-lemma-btn');
    if (!on) {
      if (step1Title) step1Title.textContent = 'Step 1 — Create or unlock your lemma.id';
      if (step1Desc) step1Desc.textContent = 'Use an existing lemma.id or complete a one-time identity check.';
      if (step2Title) step2Title.textContent = 'Step 2 — Use the same lemma.id on two sites';
      if (step2Desc) step2Desc.textContent = 'Each site receives its own private ID from the same verified-human proof.';
      if (intro) intro.textContent = 'Verify once, then test two demo sites. Both sites can know you are a verified human, but neither receives your real identity or the same identifier as the other.';
      if (createBtn) createBtn.textContent = 'Create lemma.id';
    } else {
      if (createBtn) createBtn.textContent = 'Create passkey wallet';
    }
    const urls = (state.config && state.config.customer_site_urls) || {};
    const ticketsLink = $('ih-link-tickets-site');
    const trialsLink = $('ih-link-trials-site');
    if (ticketsLink && urls.tickets) {
      ticketsLink.href = `${urls.tickets}?from=demo`;
    }
    if (trialsLink && urls.trials) {
      trialsLink.href = `${urls.trials}?from=demo`;
    }
    const personCard = $('ih-person-status-card');
    if (personCard) personCard.hidden = !on;
    updateStepLocks();
  }

  function maskPpid(slug, ppid) {
    if (!ppid) return PPID_PLACEHOLDER[slug] || '—';
    const text = String(ppid);
    if (text.length <= 16) return text;
    return `${text.slice(0, 10)}••••${text.slice(-4)}`;
  }

  function formatLemmaStatus(label) {
    const map = {
      CHECKING: 'Checking…',
      READY: 'Ready',
      NONE: 'Not started',
      LOCKED: 'Locked',
      UNLOCKED: 'Unlocked',
      VERIFYING: 'Verifying…',
      CLEARING: 'Clearing…',
      CLEARED: 'Cleared',
      'POPUP BLOCKED': 'Popup blocked',
    };
    return map[label] || label;
  }

  function formatSiteStatus(result) {
    if (!result) return 'Pending';
    if (result.human) {
      return result.assurance ? `Human (${result.assurance})` : 'Human verified';
    }
    if (result.reason === 'site_blocked' || result.reason === 'revoked') return 'Blocked';
    return 'Not verified';
  }

  function setDemoMode(mode) {
    state.demoMode = mode;
    const banner = $('ih-simulation-banner');
    if (banner) banner.hidden = mode !== 'simulated';
    const createBtn = $('ih-create-lemma-btn');
    if (createBtn) createBtn.hidden = mode === 'simulated';
    updateStepLocks();
  }

  function workflowStepForWizard(wizardStep) {
    if (wizardStep <= 0) return 0;
    if (assuranceDemoMode()) {
      if (wizardStep <= 2) return 1;
      if (wizardStep === 3) return 2;
      if (wizardStep === 4) return 3;
      if (wizardStep === 5) return 4;
      if (wizardStep === 6) return 5;
      return 5;
    }
    if (wizardStep <= 2) return 1;
    if (wizardStep === 3) return 2;
    return 4;
  }

  function setWizardStep(step, statusText) {
    const statusEl = $('ih-wizard-status');
    const labelEl = $('ih-wizard-step-label');
    const shell = $('ih-wizard-shell');
    const total = assuranceDemoMode() ? WIZARD_TOTAL : LEGACY_WIZARD_TOTAL;
    if (shell) shell.hidden = false;
    if (statusEl && statusText) statusEl.textContent = statusText;
    if (labelEl) {
      labelEl.textContent = step > 0 ? `Step ${step} of ${total}` : 'Demo complete';
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
      if (!(await initWalletPassive())) return;

      let master = null;
      try {
        master = await findLocalMasterCredential();
      } catch (err) {
        if (isEncryptedWalletLockedError(err) && state.masterCredentialId) {
          setPill('ih-lemma-status', 'READY', 'ok');
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
        updateStepLocks();
        return;
      }

      if (state.masterCredentialId) {
        setPill('ih-lemma-status', 'READY', 'ok');
        setDemoReadyBanner(true);
        updateStepLocks();
        return;
      }

      // No proof yet. Distinguish a usable wallet (walletId known, possibly with
      // a restored 24h session) from a brand-new/locked one. We do NOT prompt a
      // passkey here — that only happens when the user issues a proof.
      if (!state.walletId) {
        setPill('ih-lemma-status', 'NONE', 'warn');
      } else {
        const unlocked = !!(state.wallet?.isUnlocked && state.wallet.isUnlocked());
        setPill('ih-lemma-status', unlocked ? 'UNLOCKED' : 'LOCKED', unlocked ? 'ok' : 'deny');
      }
    } catch (err) {
      setPill('ih-lemma-status', 'NONE', 'warn');
      log('Wallet status check skipped', err.message);
    }
  }

  function setWizardBusy(running) {
    state.wizardRunning = running;
    const ids = [
      'ih-start-live-demo',
      'ih-start-simulated-demo',
      'ih-unlock-lemma-btn',
      'ih-create-lemma-btn',
      'ih-verify-sites-btn',
      'ih-verify-tickets-btn',
      'ih-verify-trials-btn',
      'ih-unblock-tickets-btn',
      'ih-abuse-block-btn',
      'ih-abuse-recheck-btn',
      'ih-require-ishuman-btn',
      'ih-complete-ishuman-btn',
      'ih-reverify-tickets-ishuman-btn',
      'ih-force-reverify-btn',
      'ih-run-guided-demo',
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

  async function startLiveDemo() {
    setDemoMode('live');
    setWorkflowHighlight(1);
    scrollToPanel('ih-step-1');
    log('Live demo started', 'create or unlock your lemma.id');
  }

  async function startSimulatedDemo() {
    if (!state.config?.test_verify_enabled) {
      log('Simulated demo unavailable', 'use Start live demo on this environment');
      return;
    }
    setDemoMode('simulated');
    setWorkflowHighlight(1);
    scrollToPanel('ih-step-1');
    log('Simulated demo started', 'no real lemma.id will be created');
    try {
      await initWallet();
      await verifyOnceTestMode();
      setWorkflowHighlight(2);
      scrollToPanel('ih-step-2');
    } catch (err) {
      log('Simulated demo failed', err.message);
    }
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
    const simBtn = $('ih-start-simulated-demo');
    const operatorConsole = $('ih-operator-console');
    const testIds = [
      'ih-start-idv-btn',
      'ih-test-complete-btn',
      'ih-force-reverify-btn',
      'ih-poll-btn',
      'ih-run-guided-demo',
    ];
    if (simBtn) {
      simBtn.disabled = !enabled;
      simBtn.title = enabled ? '' : 'Simulated demo is available on staging environments only';
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
    applyAssuranceModeUI();
    log('Demo config loaded', `${state.config.sites.length} sites`);
    updatePpidCompare();
    updateStepLocks();
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
    const tResult = state.results.tickets;
    const rResult = state.results.trials;
    const t = tResult?.ppid ? maskPpid('tickets', tResult.ppid) : null;
    const r = rResult?.ppid ? maskPpid('trials', rResult.ppid) : null;
    const tCmp = $('ih-tickets-ppid-compare');
    const rCmp = $('ih-trials-ppid-compare');
    if (tCmp) tCmp.textContent = t || '—';
    if (rCmp) rCmp.textContent = r || '—';
    const diff = $('ih-ppid-diff');
    if (!diff || !t || !r) {
      if (diff) diff.textContent = 'Verify both sites';
      return;
    }
    diff.textContent = t !== r ? 'Result: different site-private IDs' : 'Result: same ID (unexpected)';
    diff.className = t !== r ? 'ppid-diff' : 'ppid-diff deny';
  }

  function updateBlockResultsTable() {
    const table = $('ih-block-results-table');
    const ticketsCell = $('ih-block-result-tickets');
    const trialsCell = $('ih-block-result-trials');
    const unblockBtn = $('ih-unblock-tickets-btn');
    const tickets = state.results.tickets;
    const trials = state.results.trials;
    if (!table || !ticketsCell || !trialsCell) return;
    if (!tickets && !trials) {
      table.hidden = true;
      if (unblockBtn) unblockBtn.hidden = true;
      return;
    }
    table.hidden = false;
    ticketsCell.textContent = tickets?.human ? 'Still verified' : 'Blocked';
    ticketsCell.className = tickets?.human ? 'result-ok' : 'result-deny';
    trialsCell.textContent = trials?.human ? 'Still verified' : 'Blocked';
    trialsCell.className = trials?.human ? 'result-ok' : 'result-deny';
    if (unblockBtn) {
      unblockBtn.hidden = !(tickets && !tickets.human && tickets.reason === 'site_blocked');
    }
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
      setPill('ih-lemma-status', 'UNLOCKED', 'ok');
      log('Wallet ready', `${source} · ${short(state.walletId)}`);
    } else {
      setPill('ih-lemma-status', 'LOCKED', 'deny');
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

  // Passive wallet bootstrap for STATUS DISPLAY only. This must never prompt a
  // passkey: it opens IndexedDB, silently restores a valid 24h unlock bundle
  // (init() does this on lemma.id), and resolves walletId/secret from the
  // session + plaintext stores. The passkey is reserved for issuing a
  // PPID-derived proof from the wallet secret, and is reused for 24h once done.
  async function initWalletPassive() {
    if (!window.LemmaWallet) return false;
    state.wallet = state.wallet || new window.LemmaWallet();
    await state.wallet.init();
    let walletId = state.wallet.session?.walletId || '';
    if (!walletId) {
      try {
        const rec = await state.wallet._get('passkey', 'walletId');
        walletId = rec?.value || '';
      } catch (err) {
        if (!isEncryptedWalletLockedError(err)) log('Wallet id read skipped', err.message);
      }
    }
    if (walletId) {
      state.walletId = walletId;
      const wid = $('ih-wallet-id');
      if (wid) wid.textContent = short(state.walletId);
    }
    if (!state.walletSecret && state.wallet.session?.walletSecret) {
      state.walletSecret = state.wallet.session.walletSecret;
    }
    return true;
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
    const startBody = {
      wallet_id: walletId,
      return_url: returnUrl,
      wallet_assertion: walletAssertion,
    };
    try {
      startBody.ppid = await state.wallet.derivePPID('lemma.id');
    } catch (err) {
      console.warn('[isHuman demo] provisional PPID not sent:', err?.message || err);
    }
    const payload = await requestJson('/api/ishuman/start-verification', {
      method: 'POST',
      body: JSON.stringify(startBody),
    });

    state.sessionId = payload.session_id;
    localStorage.setItem('ishuman_demo_session_id', state.sessionId);
    log('Identity verification session started', short(payload.provider_session_id || payload.stripe_session_id));

    if (payload.url) {
      window.location.href = payload.url;
      return;
    }
    const netJson = $('ih-master-json');
    if (netJson) netJson.textContent = pretty(payload);
  }

  // Open the Lemma IDV popup ON lemma.id (treating lemma.id as the requesting
  // site) to create the master human proof — the user's "lemma.id" — in the
  // lemma.id wallet via the identity check flow. This is the exact same popup
  // customer sites use; here the demo page itself is the opener, which is why
  // the popup must work for an origin of lemma.id. The per-site PPIDs (tickets,
  // trials, lemma.id) are all derived from this one master proof.
  async function syncMasterFromServer() {
    if (!state.walletId) return false;
    const status = await refreshStatus().catch(() => null);
    if (status?.master?.status === 'verified' && status.master.credential_id) {
      state.masterCredentialId = status.master.credential_id;
      localStorage.setItem('ishuman_demo_master_id', state.masterCredentialId);
      setPill('ih-lemma-status', 'READY', 'ok');
      setDemoReadyBanner(true);
      return true;
    }
    return false;
  }

  let _demoIdvPopup = null;

  function broadcastIdvPopupSupersede(flow, token) {
    try {
      const ch = new BroadcastChannel('lemma-ishuman-popup');
      ch.postMessage({
        type: 'ISHUMAN_POPUP_SUPERSEDE',
        flow,
        token,
        ts: Date.now(),
      });
      ch.close();
    } catch (_) { /* non-fatal */ }
  }

  function randomPopupToken() {
    const bytes = crypto.getRandomValues(new Uint8Array(12));
    let str = '';
    for (let i = 0; i < bytes.length; i += 1) str += String.fromCharCode(bytes[i]);
    return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
  }

  function openIdvPopup({ demoQr = false } = {}) {
    if (_demoIdvPopup && !_demoIdvPopup.closed) {
      try { _demoIdvPopup.focus(); } catch (_) { /* non-fatal */ }
      return _demoIdvPopup;
    }

    const popupToken = randomPopupToken();
    broadcastIdvPopupSupersede(demoQr ? 'demo_qr' : 'idv', popupToken);

    const popupUrl = new URL(`${window.location.origin}/wallet/ishuman-idv`);
    popupUrl.searchParams.set('origin', window.location.origin);
    popupUrl.searchParams.set('site_id', 'lemma.id');
    popupUrl.searchParams.set('popup_token', popupToken);
    if (demoQr) {
      popupUrl.searchParams.set('flow_mode', 'demo_qr');
    }

    const width = 480;
    const height = demoQr ? 760 : 660;
    const left = Math.max(0, Math.round(window.screenX + (window.outerWidth - width) / 2));
    const top = Math.max(0, Math.round(window.screenY + (window.outerHeight - height) / 2));
    const popup = window.open(
      popupUrl.toString(),
      demoQr ? 'lemma_ishuman_demo_qr' : 'lemma_ishuman_idv',
      `popup=yes,width=${width},height=${height},left=${left},top=${top}`,
    );
    if (!popup) {
      setPill('ih-lemma-status', 'POPUP BLOCKED', 'warn');
      log('Identity popup blocked', 'Allow popups for lemma.id and retry');
      _demoIdvPopup = null;
      return null;
    }

    _demoIdvPopup = popup;

    setPill('ih-lemma-status', demoQr ? 'DEMO POPUP' : 'VERIFYING', 'warn');
    log(demoQr ? 'Opened demo QR popup' : 'Opened identity check popup for lemma.id');

    let settled = false;
    const finish = async (outcome) => {
      if (settled) return;
      settled = true;
      _demoIdvPopup = null;
      window.removeEventListener('message', onMessage);
      clearInterval(closedTimer);
      log(demoQr ? 'Demo QR popup closed' : 'Identity check popup closed', outcome);
      await refreshWalletStatus().catch(() => {});
      await syncMasterFromServer().catch(() => {});
      await hydrateSiteVerificationFromCache().catch(() => {});
      if (outcome === 'completed') {
        setWorkflowHighlight(2);
        setDemoReadyBanner(true);
        updateStepLocks();
        scrollToPanel('ih-step-2');
      }
    };
    const onMessage = (event) => {
      if (event.origin !== window.location.origin) return;
      const type = event.data && event.data.type;
      if (type === 'ISHUMAN_IDV_COMPLETE' || type === 'ISHUMAN_SITE_PROOF_ISSUED') {
        finish('completed');
      } else if (type === 'ISHUMAN_IDV_CANCELLED') {
        finish('cancelled');
      }
    };
    const closedTimer = setInterval(() => {
      if (popup.closed) finish('closed');
    }, 800);
    window.addEventListener('message', onMessage);
    return popup;
  }

  function createLemmaIdViaPopup() {
    setDemoMode('live');
    if (assuranceDemoMode()) {
      return createPasskeyWallet();
    }
    return openIdvPopup({ demoQr: false });
  }

  async function createPasskeyWallet() {
    await initWallet();
    await refreshAssuranceStatus();
    setPill('ih-lemma-status', 'UNLOCKED', 'ok');
    setDemoReadyBanner(true);
    setWorkflowHighlight(2);
    scrollToPanel('ih-step-2');
    log('Passkey wallet ready', short(state.walletId));
  }

  async function refreshAssuranceStatus() {
    if (!state.walletId || !assuranceDemoMode()) return null;
    const payload = await requestJson(
      `/api/demo/ishuman/assurance-status?wallet_id=${encodeURIComponent(state.walletId)}`,
    );
    state.assuranceStatus = payload;
    if (payload.provisional) {
      setPill('ih-person-status', 'Provisional', 'warn');
    } else if (payload.anchored) {
      setPill('ih-person-status', 'Anchored (IDV)', 'ok');
    } else if (payload.person_bound) {
      setPill('ih-person-status', payload.person_status || 'Bound', 'ok');
    } else {
      setPill('ih-person-status', 'Unbound', 'warn');
    }
    return payload;
  }

  // Cross-origin storage wipe for the customer demo sites. lemma.id JS cannot
  // reach another origin's IndexedDB/localStorage, so for each site we mount a
  // hidden iframe of its /lemma-clear page (served from that origin); the page
  // clears its own storage and posts LEMMA_CLEAR_DONE back. We resolve on that
  // signal or a timeout so a missing/old site never hangs the reset.
  async function clearCustomerSiteCaches() {
    const urls = (state.config && state.config.customer_site_urls) || {};
    const origins = SITE_SLUGS.map((slug) => urls[slug]).filter(Boolean);
    if (!origins.length) {
      log('Customer-site clear skipped', 'no customer_site_urls in config');
      return;
    }
    await Promise.all(origins.map((origin) => new Promise((resolve) => {
      let settled = false;
      const iframe = document.createElement('iframe');
      iframe.style.display = 'none';
      iframe.setAttribute('aria-hidden', 'true');
      const finish = (note) => {
        if (settled) return;
        settled = true;
        window.removeEventListener('message', onMessage);
        try { iframe.remove(); } catch { /* ignore */ }
        if (note) log('Customer site cache cleared', note);
        resolve();
      };
      const onMessage = (event) => {
        if (event.origin !== origin) return;
        if (event.data && event.data.type === 'LEMMA_CLEAR_DONE') {
          finish(`${origin.replace('https://', '')} (${event.data.cleared || 0} keys)`);
        }
      };
      window.addEventListener('message', onMessage);
      iframe.src = `${origin}/lemma-clear`;
      iframe.onerror = () => finish(`${origin} (load error)`);
      document.body.appendChild(iframe);
      setTimeout(() => finish(`${origin} (timeout)`), 3000);
    })));
  }

  // Full demo reset: wipe the lemma.id (master human proof) and every
  // site-derived proof from this browser's lemma.id wallet, clear the demo +
  // SDK caches, and signal any open customer-site tabs to drop their cached
  // sessions. After this the user re-runs "Create my lemma.id" from scratch.
  async function clearLemmaId() {
    const confirmed = window.confirm(
      'Clear your lemma.id?\n\n'
      + 'This wipes the master human proof and every site-derived ID from this '
      + 'browser (the lemma.id wallet) and tells open customer-site tabs to drop '
      + 'their cached sessions. You will need to run "Create my lemma.id" again.',
    );
    if (!confirmed) return;

    setPill('ih-lemma-status', 'CLEARING', 'warn');
    log('Clearing lemma.id', 'wiping local wallet + signaling customer sites');

    // 1. Best-effort server reset of this wallet's revocation state so a
    //    re-created lemma.id starts clean. Needs a wallet assertion while the
    //    wallet is still live, so do it before wiping IndexedDB.
    try {
      if (state.walletId && state.wallet && state.wallet.buildWalletAssertion) {
        const assertion = await state.wallet
          .buildWalletAssertion(['wallet_id'], { wallet_id: state.walletId })
          .catch(() => null);
        if (assertion) {
          await requestJson('/api/demo/ishuman/self-reset', {
            method: 'POST',
            body: JSON.stringify({ wallet_id: state.walletId, wallet_assertion: assertion }),
          }).catch((err) => log('Server self-reset skipped', err.message));
        }
      }
    } catch (err) {
      log('Server reset skipped', err.message);
    }

    // 2a. Tell open tabs on the same origin to invalidate cached sessions.
    //     NOTE: BroadcastChannel is
    //     origin-scoped, so this only reaches lemma.id tabs, not the customer
    //     demo origins — those are handled by the cross-origin iframe wipe below.
    if (window.IsHumanVerifier && window.IsHumanVerifier.broadcastBlockUpdate) {
      for (const slug of SITE_SLUGS) {
        window.IsHumanVerifier.broadcastBlockUpdate({
          type: 'CREDENTIAL_RESET',
          siteId: SITE_IDS[slug],
          walletId: state.walletId,
          reason: 'demo_clear_lemma_id',
        });
      }
    }

    // 2b. Clear the cached site proof / session that the demo tickets + trials
    //     sites stored in THEIR OWN origin storage. Same-origin policy forbids
    //     lemma.id from touching another origin's IndexedDB/localStorage, so we
    //     embed each site's /lemma-clear page in a hidden iframe — it runs in
    //     that origin and wipes its own storage, then posts confirmation back.
    await clearCustomerSiteCaches();

    // 3. Wipe the lemma.id wallet IndexedDB (master proof, derived site proofs,
    //    passkey, wallet secret, at-rest key material, isHuman cache). Close the
    //    live connection first so deleteDatabase isn't blocked.
    try {
      if (state.wallet && state.wallet.db && typeof state.wallet.db.close === 'function') {
        state.wallet.db.close();
      }
    } catch { /* ignore */ }
    await new Promise((resolve) => {
      try {
        const req = indexedDB.deleteDatabase('LemmaWallet');
        req.onsuccess = resolve;
        req.onerror = resolve;
        req.onblocked = resolve;
      } catch {
        resolve();
      }
    });

    // 4. Clear lemma.id-origin localStorage tied to the proof, the demo, and
    //    the SDK (daily-unlock bundle, master id, popup session, provisioned
    //    flag, bloom + trust caches, and any per-site session/VC caches).
    try {
      const prefixes = ['ishuman_session_v1:', 'ishuman_site_vc:v1:'];
      for (let i = localStorage.length - 1; i >= 0; i -= 1) {
        const key = localStorage.key(i);
        if (key && prefixes.some((p) => key.startsWith(p))) localStorage.removeItem(key);
      }
      [
        'lemma_ishuman_lock:v1',
        'ishuman_demo_master_id',
        'ishuman_demo_session_id',
        'ishuman_idv_popup_session_id',
        'ishuman_master_provisioned_v1',
        'ishuman_bloom',
        'ishuman_trust_list',
      ].forEach((k) => localStorage.removeItem(k));
    } catch (err) {
      log('Local storage clear partial', err.message);
    }

    // 5. Reset in-memory demo state + UI.
    state.wallet = null;
    state.walletId = null;
    state.walletSecret = null;
    state.masterCredential = null;
    state.masterCredentialId = '';
    state.sessionId = '';
    state.results = {};
    for (const slug of SITE_SLUGS) state.localBlocks[slug].clear();

    const wid = $('ih-wallet-id');
    if (wid) wid.textContent = '-';
    setDemoReadyBanner(false);
    setPill('ih-lemma-status', 'CLEARED', 'warn');
    setDemoMode(null);
    updateStepLocks();
    for (const slug of SITE_SLUGS) {
      setPill(`ih-${slug}-pill`, 'Pending', '');
      const ppidEl = $(`ih-${slug}-ppid`);
      if (ppidEl) ppidEl.textContent = PPID_PLACEHOLDER[slug];
    }
    updatePpidCompare();
    updateBlockResultsTable();
    log('lemma.id cleared', 'start the live or simulated demo again');
  }

  async function claimVerifiedMaster(activeSessionId) {
    const { walletId } = await getWalletContext();
    const walletAssertion = await state.wallet.buildWalletAssertion(
      ['session_id'],
      { session_id: activeSessionId },
    );
    return requestJson(
      `/api/ishuman/verification-status/${encodeURIComponent(activeSessionId)}/claim`,
      {
        method: 'POST',
        body: JSON.stringify({
          wallet_id: walletId,
          session_id: activeSessionId,
          wallet_assertion: walletAssertion,
        }),
      },
    );
  }

  async function pollAndStoreMaster() {
    if (!state.sessionId) throw new Error('No demo verification session. Start the identity check first.');
    if (!state.wallet) await initWallet();

    let payload = await requestJson(`/api/ishuman/verification-status/${encodeURIComponent(state.sessionId)}`);
    if (payload.status === 'verified' && payload.credential_ready) {
      payload = await claimVerifiedMaster(state.sessionId);
    }
    const netJson = $('ih-master-json');
    if (netJson) netJson.textContent = pretty(payload);
    log('Verification status checked', payload.status);

    if (payload.status !== 'verified' || !payload.credential) {
      setPill('ih-lemma-status', String(payload.status || 'PENDING').toUpperCase(), 'warn');
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
    if (!state.sessionId) throw new Error('No demo verification session. Start the identity check first.');
    await requestJson('/api/demo/ishuman/test-complete-verification', {
      method: 'POST',
      headers: demoHeaders(),
      body: JSON.stringify({ session_id: state.sessionId }),
    });
    log('Test-mode verification session completed');
    await pollAndStoreMaster();
  }

  function renderMaster(credential) {
    const claims = credential?.claims || credential?.credentialSubject || {};
    const json = $('ih-master-json');
    if (json) {
      json.textContent = pretty({
        id: credential?.id,
        issuer: credential?.issuer || credential?.issuerInfo?.did,
        subject: credential?.subject,
        claims,
      });
    }
    setPill('ih-lemma-status', 'READY', 'ok');
    setDemoReadyBanner(true);
    updateStepLocks();
  }

  function verifierFor(slug, options = {}) {
    if (!window.IsHumanVerifier) throw new Error('IsHumanVerifier SDK not loaded');
    const requiredAssurance = options.requiredAssurance
      || (assuranceDemoMode() ? 'passkey' : 'ishuman');
    const cacheKey = `${slug}:${requiredAssurance}`;
    if (!state.verifiers) state.verifiers = {};
    if (state.verifiers[cacheKey]) return state.verifiers[cacheKey];
    state.verifiers[cacheKey] = new window.IsHumanVerifier({
      siteId: SITE_IDS[slug],
      lemmaOrigin: window.location.origin,
      debug: true,
      autoProvision: true,
      requiredAssurance,
      isBlockedLocally: (ppid) => state.localBlocks[slug].has(ppid),
    });
    return state.verifiers[cacheKey];
  }

  async function verifySite(slug, options = {}) {
    if (!window.IsHumanVerifier) throw new Error('IsHumanVerifier SDK not loaded');
    const requiredAssurance = options.requiredAssurance
      || (assuranceDemoMode() ? 'passkey' : 'ishuman');
    const verifier = verifierFor(slug, { requiredAssurance });
    let result;
    if (assuranceDemoMode() || options.useBackend) {
      const backend = await verifier.verifyForBackend({
        autoProvision: true,
        requiredAssurance,
        ...options,
      });
      result = {
        human: !!backend.human,
        ppid: backend.ppid,
        assurance: backend.assurance,
        presentation: backend.presentation,
        reason: backend.reason,
        timeMs: backend.timeMs || 0,
      };
    } else {
      result = await verifier.verify();
    }
    state.results[slug] = result;
    if (Number.isFinite(result.timeMs)) state.lastVerifyMs[slug] = result.timeMs;
    if (assuranceDemoMode() && requiredAssurance === 'passkey' && result.ppid) {
      state.passkeyPpids[slug] = result.ppid;
    }
    renderSite(slug, result);
    updateIntegrationLatency();
    updatePpidCompare();
    log(
      `${SITE_IDS[slug]} verifier result`,
      `${result.reason}${result.assurance ? ` · ${result.assurance}` : ''} in ${(result.timeMs || 0).toFixed(1)}ms`,
    );
    await refreshStatus();
    return result;
  }

  async function verifyBothSites() {
    await verifySite('tickets');
    await verifySite('trials');
    if (bothSitesVerified()) {
      if (assuranceDemoMode()) {
        setWorkflowHighlight(3);
        scrollToPanel('ih-demo-sites-panel');
      } else {
        setWorkflowHighlight(4);
        scrollToPanel('ih-abuse-panel');
      }
    }
  }

  async function recheckBothSitesAfterBlock() {
    await verifySite('tickets');
    await verifySite('trials');
    updateBlockResultsTable();
  }

  function renderSite(slug, result) {
    const tone = result.human ? 'ok' : (result.reason === 'site_blocked' || result.reason === 'revoked' ? 'deny' : 'warn');
    setPill(`ih-${slug}-pill`, formatSiteStatus(result), tone);
    const card = $(`ih-${slug}-card`);
    if (card) {
      card.classList.remove('is-human', 'is-deny', 'is-pending');
      if (result.human) card.classList.add('is-human');
      else if (result.reason === 'site_blocked' || result.reason === 'revoked') card.classList.add('is-deny');
      else card.classList.add('is-pending');
    }
    const ppidEl = $(`ih-${slug}-ppid`);
    if (ppidEl) ppidEl.textContent = maskPpid(slug, result.ppid);
    const assuranceEl = $(`ih-${slug}-assurance`);
    if (assuranceEl) assuranceEl.textContent = result.assurance || '—';
    const reasonEl = $(`ih-${slug}-reason`);
    if (reasonEl) reasonEl.textContent = result.reason || '—';
    const latEl = $(`ih-${slug}-latency`);
    if (latEl) latEl.textContent = Number.isFinite(result.timeMs) ? `${result.timeMs.toFixed(1)}ms` : '—';
    updatePpidCompare();
    updateStepLocks();
    updateBlockResultsTable();
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
    // Instant cross-tab propagation: any IsHumanVerifier on the same origin
    // listening on the 'lemma-ishuman-blocks' BroadcastChannel will drop its
    // cached session and re-check on next verify().
    if (window.IsHumanVerifier && window.IsHumanVerifier.broadcastBlockUpdate) {
      window.IsHumanVerifier.broadcastBlockUpdate({
        type: 'SITE_BLOCK_UPDATE',
        siteId: SITE_IDS.tickets,
        ppid: result.ppid,
        reason: 'demo_site_block',
      });
    }
    const netJson = $('ih-master-json');
    if (netJson) netJson.textContent = pretty(payload);
    log('Ticketing site block applied', short(result.ppid));

    await verifySite('tickets');
    await verifySite('trials');
    await refreshAbuseChecks();
    await probeDerive('tickets');
    if (assuranceDemoMode()) {
      setWorkflowHighlight(5);
      scrollToPanel('ih-stepup-panel');
    } else {
      setWorkflowHighlight(4);
      scrollToPanel('ih-abuse-panel');
    }
    updateBlockResultsTable();
  }

  async function requireIsHumanOnTickets() {
    const result = state.results.tickets
      || await verifySite('tickets', { requiredAssurance: 'passkey' });
    if (!result.ppid) throw new Error('Ticketing PPID unavailable');
    if (result.ppid) state.passkeyPpids.tickets = result.ppid;

    await requestJson('/api/demo/ishuman/require-ishuman', {
      method: 'POST',
      body: JSON.stringify({
        site_slug: 'tickets',
        ppid: result.ppid,
        reason: 'Demo: ticketing requires isHuman assurance',
      }),
    });
    log('Site doubt created', 'ticketing requires isHuman step-up');
    setWorkflowHighlight(5);
    scrollToPanel('ih-stepup-panel');
  }

  async function completeIsHumanVerification() {
    if (state.config?.test_verify_enabled) {
      await verifyOnceTestMode();
    } else {
      await openIdvPopup({ demoQr: false });
    }
    await refreshAssuranceStatus();
    log('isHuman verification complete', 're-verify ticketing with ishuman assurance');
  }

  function updateStepUpCompare(beforePpid, afterResult) {
    const panel = $('ih-stepup-compare');
    const beforeEl = $('ih-ppid-before-stepup');
    const afterEl = $('ih-ppid-after-stepup');
    const diffEl = $('ih-stepup-diff');
    const flipEl = $('ih-assurance-flip');
    if (!panel || !beforeEl || !afterEl || !diffEl) return;
    panel.hidden = false;
    beforeEl.textContent = maskPpid('tickets', beforePpid);
    afterEl.textContent = maskPpid('tickets', afterResult?.ppid);
    const same = beforePpid && afterResult?.ppid && beforePpid === afterResult.ppid;
    diffEl.textContent = same ? 'Same PPID ✓' : 'PPID mismatch (unexpected)';
    diffEl.className = same ? 'ppid-diff' : 'ppid-diff deny';
    if (flipEl) {
      flipEl.textContent = `Assurance: passkey → ${afterResult?.assurance || '?'}`;
    }
  }

  async function reverifyTicketsIshuman() {
    const before = state.passkeyPpids.tickets || state.results.tickets?.ppid;
    if (!before) throw new Error('No passkey ticketing PPID snapshot — verify step 2 first');
    const result = await verifySite('tickets', { requiredAssurance: 'ishuman' });
    updateStepUpCompare(before, result);
    if (result.ppid === before && result.assurance === 'ishuman') {
      log('Step-up success', 'same PPID with ishuman assurance');
      setWorkflowHighlight(0);
    } else {
      log('Step-up check', `ppid match=${result.ppid === before} assurance=${result.assurance}`);
    }
    return result;
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
    await verifySite('trials');
    await refreshAbuseChecks();
    updateBlockResultsTable();
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
      setPill('ih-lemma-status', 'READY', 'ok');
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

    throw new Error('No verified master proof yet. Complete verification on a demo site, or start an identity check from the operator console.');
  }

  async function runGuidedDemo() {
    if (state.wizardRunning) return;
    setWizardBusy(true);
    scrollToPanel('ih-demo-cockpit');
    try {
      setWizardStep(1, 'Unlocking wallet…');
      await initWallet();

      if (assuranceDemoMode()) {
        await refreshAssuranceStatus();
        setWizardStep(2, 'Passkey proof on both demo sites…');
        await verifyBothSites();

        setWizardStep(3, 'Open demo sites to stamp actions (optional pause)…');
        await sleep(1500);

        setWizardStep(4, 'Blocking abusive ticketing PPID…');
        scrollToPanel('ih-abuse-panel');
        await blockTickets();

        setWizardStep(5, 'Requiring isHuman on ticketing…');
        await requireIsHumanOnTickets();

        setWizardStep(6, 'Complete isHuman verification…');
        if (state.config?.test_verify_enabled) {
          await verifyOnceTestMode();
        } else {
          log('Complete IDV manually', 'use Complete isHuman verification button');
        }

        setWizardStep(0, 'Demo complete — same ticketing PPID with ishuman assurance.');
        setDemoReadyBanner(true);
        log('Assurance guided demo complete');
        return;
      }

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

      setWizardStep(6, 'Confirming persistent site enforcement…');
      log('Network-wide revocation is retired; the site block remains authoritative.');

      setWizardStep(7, 'Rechecking both site-private decisions…');
      await verifyBothSites();

      setWizardStep(0, 'Demo complete — ticketing denied; trials remains valid.');
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

  async function hydrateSiteVerificationFromCache() {
    if (!window.IsHumanVerifier) return;
    for (const slug of SITE_SLUGS) {
      try {
        const verifier = verifierFor(slug);
        const result = await verifier.checkStatus();
        state.results[slug] = result;
        if (Number.isFinite(result.timeMs)) state.lastVerifyMs[slug] = result.timeMs;
        renderSite(slug, result);
      } catch (err) {
        log(`Site cache check skipped (${slug})`, err.message);
      }
    }
    updateIntegrationLatency();
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
      if (state.wizardRunning && id !== 'ih-run-guided-demo') return;
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
    bind('ih-start-live-demo', startLiveDemo);
    bind('ih-start-simulated-demo', startSimulatedDemo);
    bind('ih-unlock-lemma-btn', initWallet);
    bind('ih-create-lemma-btn', createLemmaIdViaPopup);
    bind('ih-clear-lemma-id-btn', clearLemmaId);
    bind('ih-start-idv-btn', startIdentityVerification);
    bind('ih-test-complete-btn', completeTestModeVerification);
    bind('ih-poll-btn', pollAndStoreMaster);
    bind('ih-verify-sites-btn', verifyBothSites);
    bind('ih-refresh-status-btn', refreshStatus);
    bind('ih-verify-tickets-btn', () => verifySite('tickets'));
    bind('ih-verify-trials-btn', () => verifySite('trials'));
    bind('ih-unblock-tickets-btn', unblockTickets);
    bind('ih-abuse-block-btn', blockTickets);
    bind('ih-abuse-recheck-btn', recheckBothSitesAfterBlock);
    bind('ih-require-ishuman-btn', requireIsHumanOnTickets);
    bind('ih-complete-ishuman-btn', completeIsHumanVerification);
    bind('ih-reverify-tickets-ishuman-btn', reverifyTicketsIshuman);
    bind('ih-run-guided-demo', runGuidedDemo);
    bind('ih-force-reverify-btn', forceFreshIdv);

    try {
      await refreshWalletStatus();
      await hydrateSiteVerificationFromCache();
      if (state.walletId) await refreshAssuranceStatus().catch(() => {});
      if (state.masterCredentialId || state.sessionId) {
        await refreshStatus();
        setPill('ih-lemma-status', 'READY', 'ok');
        updateStepLocks();
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
