(function () {
  'use strict';

  const SITE_SLUGS = ['tickets', 'trials'];
  const DEFAULT_DEMO_SITE_ASSURANCE = 'passkey';
  const PASSKEY_OK_REASONS = new Set(['valid', 'session_valid', 'vc_valid']);
  const SITE_IDS = {
    tickets: 'tickets-demo.lemma.id',
    trials: 'trials-demo.lemma.id',
  };
  const WIZARD_TOTAL = 7;
  const LEGACY_WIZARD_TOTAL = 7;

  const OPERATION_DEFS = [
    { id: 'preflight', label: 'Preflight: SDK, config, demo sites' },
    { id: 'wallet', label: 'lemma.id ready' },
    { id: 'site_proofs', label: 'Two distinct site PPIDs' },
    { id: 'relying_sites', label: 'Relying-site endpoints reachable' },
    { id: 'escalation', label: 'Require human proofs on ticketing' },
    { id: 'step_up', label: 'Complete human proof step-up' },
    { id: 'same_ppid', label: 'Same PPID after step-up' },
    { id: 'site_block', label: 'Block ticketing PPID' },
    { id: 'scoped_revocation', label: 'Trials still allowed after block' },
    { id: 'reset', label: 'Reset demo state' },
  ];

  const operationResults = {};
  let operationsRunning = false;

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
    hasLocalWallet: false,
    sessionId: localStorage.getItem('ishuman_demo_session_id') || '',
    masterCredential: null,
    masterCredentialId: localStorage.getItem('ishuman_demo_master_id') || '',
    results: {},
    localBlocks: { tickets: new Set(), trials: new Set() },
    localDoubts: { tickets: new Set(), trials: new Set() },
    wizardRunning: false,
    blockToggleBusy: false,
    lastVerifyMs: { tickets: null, trials: null },
    passkeyPpids: {},
    assuranceStatus: null,
    serverTestToken: '',
    serverAdminToken: '',
    ticketsRequiresIshuman: false,
    trialsRequiresIshuman: false,
    presentationSlug: 'tickets',
    lastPopupIssueMode: null,
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
    if (id === 'ih-lemma-status') {
      const top = $('ih-topbar-status');
      if (top) {
        top.textContent = display;
        top.className = el.className;
      }
      renderStep1Action();
    }
  }

  const MAIN_WORKFLOW_STEPS = [
    { id: 1, chapter: 1 },
    { id: 2, chapter: 2 },
    { id: 3, chapter: 3 },
    { id: 4, chapter: 4 },
    { id: 5, chapter: 5 },
  ];

  function chapterForAct(act) {
    if (act <= 0) return 0;
    if (act >= 6) return 6;
    return act;
  }

  function workflowToQuickAct(workflowStep) {
    if (workflowStep <= 0) return 0;
    return Math.min(workflowStep, 5);
  }

  function showQuickInsight(visible) {
    const el = $('ih-quick-insight');
    if (el) el.hidden = !visible;
  }

  function setQuickInsight(label, text, options = {}) {
    const labelEl = $('ih-quick-insight-label');
    const textEl = $('ih-quick-insight-text');
    if (labelEl || textEl) showQuickInsight(true);
    const retryBtn = $('ih-popup-retry-btn');
    if (labelEl && label) labelEl.textContent = label;
    if (textEl && text) textEl.textContent = text;
    if (retryBtn) {
      const showRetry = !!(options.showPopupRetry && state.lastPopupIssueMode);
      retryBtn.hidden = !showRetry;
    }
  }

  function renderProofReceipt() {
    const panel = $('ih-proof-receipt');
    const rowsEl = $('ih-proof-receipt-rows');
    if (!panel || !rowsEl) return;
    const slugs = ['tickets', 'trials'];
    const lines = slugs
      .map((slug) => {
        const result = state.results[slug];
        if (!result || !result.reason) return null;
        const site = SITE_IDS[slug] || slug;
        const assurance = result.assurance || '—';
        const reason = result.reason || '—';
        const ms = Number.isFinite(result.timeMs) ? `${result.timeMs.toFixed(1)}ms` : '—';
        return `<div class="demo-proof-receipt-row"><span class="demo-proof-receipt-site">${site}</span><span class="demo-proof-receipt-assurance">${assurance}</span><span class="demo-proof-receipt-reason">${reason}</span><span class="demo-proof-receipt-ms">${ms}</span></div>`;
      })
      .filter(Boolean);
    if (!lines.length) {
      panel.hidden = true;
      rowsEl.innerHTML = '';
      return;
    }
    panel.hidden = false;
    rowsEl.innerHTML = lines.join('');
  }

  function updateQuickProgress(act) {
    const progress = $('ih-quick-progress');
    if (!progress) return;
    const chapter = chapterForAct(act);
    progress.querySelectorAll('.demo-progress-item').forEach((item) => {
      const step = Number(item.dataset.quickAct || 0);
      item.classList.remove('is-active', 'is-done');
      if (chapter >= 6 || (chapter > 0 && step < chapter)) item.classList.add('is-done');
      else if (step === chapter) item.classList.add('is-active');
    });
  }

  async function waitForWalletId({ timeoutMs = 90000 } = {}) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      await initWalletPassive().catch(() => {});
      await refreshWalletStatus().catch(() => {});
      if (state.walletId) return true;
      await sleep(400);
    }
    return !!state.walletId;
  }

  async function ensureRealLemmaId() {
    setDemoMode('live');
    await initWalletPassive().catch(() => {});
    await refreshWalletStatus().catch(() => {});
    if (state.walletId) {
      try {
        await initWallet();
        return true;
      } catch (err) {
        log('Wallet unlock needed', err.message);
        openIdvPopup({ issueMode: 'unlock' });
        return waitForWalletId();
      }
    }
    setQuickInsight('Act 1 — Create', 'Opening passkey setup to create your lemma.id…');
    const popup = openIdvPopup({ issueMode: 'passkey_setup' });
    if (!popup) {
      setQuickInsight('Act 1 — Create', 'Allow popups for lemma.id, then tap Get started again.');
      return false;
    }
    const ready = await waitForWalletId();
    if (!ready) {
      setQuickInsight('Act 1 — Create', 'Finish passkey setup in the popup, then continue the demo.');
      return false;
    }
    try {
      await initWallet();
    } catch (err) {
      log('Wallet unlock after setup skipped', err.message);
    }
    return true;
  }

  async function runQuickDemo() {
    // Deprecated: passkey/IDV cannot be automated. Kept for console/back-compat only.
    setDemoMode('live');
    setWizardBusy(true);
    try {
      setQuickInsight('Act 1 — Create', 'Create your passkey-controlled lemma.id…');
      setWorkflowHighlight(1);
      scrollToPanel('ih-step-1');

      const walletReady = await ensureRealLemmaId();
      if (!walletReady) return;

      updateQuickProgress(1);
      setQuickInsight('Act 2 — Verify', 'Minting passkey proof on ticketing demo site…');
      setWorkflowHighlight(2);
      scrollToPanel('ih-step-2');
      await verifySite('tickets');

      updateQuickProgress(2);
      setQuickInsight('Act 2 — Verify', 'Same lemma.id — minting a different private ID on trials…');
      await verifySite('trials');

      updateQuickProgress(3);
      setQuickInsight('Act 3 — Enforce', 'Blocking on ticketing only. Trials should stay valid.');
      setWorkflowHighlight(5);
      scrollToPanel('ih-step-5');
      await blockTickets();
      await recheckBothSitesAfterBlock();

      setQuickInsight('Done', 'Ticketing blocked; trials still works. Add a human proof below when your policy needs bans that stick.');
      setWorkflowHighlight(0);
      log('Quick demo complete');
    } catch (err) {
      setQuickInsight('Paused', err.message);
      log('Quick demo stopped', err.message);
      throw err;
    } finally {
      setWizardBusy(false);
    }
  }

  function assuranceDemoMode() {
    return !!(state.config && state.config.assurance_demo_mode);
  }

  function demoRequiredAssurance(slug, options = {}) {
    if (options.requiredAssurance) return options.requiredAssurance;
    if (slug === 'tickets' && state.ticketsRequiresIshuman) return 'ishuman';
    if (slug === 'trials' && state.trialsRequiresIshuman) return 'ishuman';
    return DEFAULT_DEMO_SITE_ASSURANCE;
  }

  function siteDecisionLocally(slug, ppid) {
    if (!ppid) return { blocked: false, doubt_required: false };
    const blocked = state.localBlocks[slug]?.has(ppid) || false;
    const doubtRequired = !blocked && (state.localDoubts[slug]?.has(ppid) || false);
    return { blocked, doubt_required: doubtRequired };
  }

  function syncTicketsPolicyToggle() {
    setSegToggleActive('ih-tickets-assurance-seg', !!state.ticketsRequiresIshuman);
  }

  function setTicketsRequiresIshuman(enabled) {
    state.ticketsRequiresIshuman = !!enabled;
    clearVerifierCache('tickets');
    syncTicketsPolicyToggle();
    checkPolicyDenials();
    renderLifecyclePanel();
    log('Ticketing assurance policy', state.ticketsRequiresIshuman ? 'human proof required' : 'passkey');
  }

  async function onTicketsPolicyToggleChange(enabled) {
    setTicketsRequiresIshuman(enabled);
    const panel = $('ih-policy-deny-grid');
    if (panel) panel.hidden = !enabled;
    if (state.results.tickets?.ppid) {
      await verifySite('tickets').catch((err) => log('Ticketing re-verify skipped', err.message));
    }
  }

  function setSegToggleActive(rootId, activeIndex) {
    const root = $(rootId);
    if (!root) return;
    const index = activeIndex ? 1 : 0;
    root.dataset.active = String(index);
    root.querySelectorAll('.demo-seg-toggle-btn').forEach((btn, i) => {
      const on = i === index;
      btn.classList.toggle('is-active', on);
      btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
  }

  function syncTrialsPolicyToggle() {
    setSegToggleActive('ih-trials-assurance-seg', !!state.trialsRequiresIshuman);
  }

  function syncBlockSegToggle() {
    const tickets = state.results.tickets;
    const blocked = isSiteBlocked('tickets', tickets);
    // Unblock is index 0 (default); Block is index 1.
    setSegToggleActive('ih-block-seg', blocked);
  }

  function setTrialsRequiresIshuman(enabled) {
    state.trialsRequiresIshuman = !!enabled;
    clearVerifierCache('trials');
    syncTrialsPolicyToggle();
    checkPolicyDenials();
    log(
      'Trials assurance policy',
      state.trialsRequiresIshuman ? 'human proof required' : 'passkey',
    );
  }

  async function onTrialsPolicyToggleChange(enabled) {
    setTrialsRequiresIshuman(enabled);
    if (state.results.trials?.ppid) {
      await verifySite('trials').catch((err) => log('Trials re-verify skipped', err.message));
      updateBlockResultsTable();
    }
  }

  function isSiteVerified(result) {
    if (!result) return false;
    if (result.human) return true;
    return !!(result.ppid
      && result.assurance === DEFAULT_DEMO_SITE_ASSURANCE
      && PASSKEY_OK_REASONS.has(result.reason));
  }

  async function acquireWallet() {
    if (!window.LemmaWallet) throw new Error('LemmaWallet SDK not loaded');
    const deadline = Date.now() + 8000;
    while (!window.globalLemmaWallet && Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
    if (window.globalLemmaWallet) {
      state.wallet = window.globalLemmaWallet;
      return state.wallet;
    }
    state.wallet = state.wallet || new window.LemmaWallet();
    window.globalLemmaWallet = state.wallet;
    return state.wallet;
  }

  function workflowStepCount() {
    return assuranceDemoMode() ? 6 : 3;
  }

  function stepUpComplete() {
    const tickets = state.results.tickets;
    return !!(tickets && tickets.assurance === 'ishuman' && isSiteVerified(tickets));
  }

  function makeOperationResult(id, status, detail, evidence) {
    const def = OPERATION_DEFS.find((row) => row.id === id) || { id, label: id };
    return {
      id,
      label: def.label,
      status,
      detail: detail || '',
      evidence: evidence || {},
    };
  }

  function initOperationsUI() {
    const list = $('ih-operations-list');
    if (!list || list.childElementCount) return;
    for (const def of OPERATION_DEFS) {
      const item = document.createElement('li');
      item.className = 'demo-operations-item';
      item.id = `ih-op-${def.id}`;
      item.innerHTML = `
        <span class="demo-operations-status">pending</span>
        <span class="demo-operations-label">${def.label}</span>
        <span class="demo-operations-detail">Waiting</span>`;
      list.appendChild(item);
    }
  }

  function setOperationResult(result) {
    operationResults[result.id] = result;
    const item = $(`ih-op-${result.id}`);
    if (!item) return;
    item.className = `demo-operations-item is-${result.status}`;
    const statusEl = item.querySelector('.demo-operations-status');
    const detailEl = item.querySelector('.demo-operations-detail');
    if (statusEl) statusEl.textContent = result.status;
    if (detailEl) detailEl.textContent = result.detail || result.status;
    const evidenceEl = $('ih-operations-evidence');
    if (evidenceEl) evidenceEl.textContent = pretty(operationResults);
  }

  function setOperationsSummary(status, detail) {
    const summary = $('ih-operations-summary');
    if (!summary) return;
    summary.textContent = detail || status;
    summary.className = `demo-pill${status === 'pass' ? ' ok' : status === 'fail' ? ' deny' : ''}`;
  }

  function markOperationRunning(id) {
    setOperationResult(makeOperationResult(id, 'run', 'Running…'));
  }

  function isMasterReady() {
    return !!(state.masterCredentialId || state.masterCredential);
  }

  function isWalletUnlocked() {
    return !!(state.wallet?.isUnlocked && state.wallet.isUnlocked());
  }

  function isStep1Ready() {
    if (assuranceDemoMode()) {
      return isWalletUnlocked();
    }
    return isMasterReady();
  }

  function step1NeedsUnlock() {
    if (isStep1Ready()) return false;
    return !!(state.walletId || state.hasLocalWallet);
  }

  async function syncWalletPresence() {
    state.hasLocalWallet = false;
    if (!state.wallet) return;
    try {
      const info = await state.wallet.getWalletInfo({ lite: true });
      state.hasLocalWallet = !!info?.hasWallet;
      if (info?.walletId && !state.walletId) {
        state.walletId = info.walletId;
        const wid = $('ih-wallet-id');
        if (wid) wid.textContent = short(state.walletId);
      }
      if (!state.walletId && info?.isUnlocked && state.wallet?.session?.walletId) {
        state.walletId = state.wallet.session.walletId;
        const wid = $('ih-wallet-id');
        if (wid) wid.textContent = short(state.walletId);
      }
    } catch (err) {
      if (!isEncryptedWalletLockedError(err)) {
        log('Wallet presence check skipped', err.message);
      } else {
        state.hasLocalWallet = true;
      }
    }
  }

  function renderStep1Action() {
    const root = $('ih-step1-action');
    const btn = $('ih-step1-primary-btn');
    const banner = $('ih-step1-continue-banner');
    if (!root || !btn || !banner) return;

    const ready = isStep1Ready();
    root.classList.toggle('is-ready', ready);
    banner.hidden = !ready;
    btn.hidden = ready;

    if (ready) {
      setQuickInsight('Act 1 — Create', 'lemma.id ready — verify on the two demo sites below.');
      updateQuickProgress(1);
      return;
    }

    if (step1NeedsUnlock()) {
      btn.textContent = 'Unlock lemma.id';
      btn.dataset.action = 'unlock';
    } else {
      btn.textContent = 'Create a lemma.id';
      btn.dataset.action = 'create';
    }
  }

  function bothSitesVerified() {
    return SITE_SLUGS.every((slug) => isSiteVerified(state.results[slug]));
  }

  function resolveSitePpid(slug) {
    if (state.results[slug]?.ppid) return state.results[slug].ppid;
    if (state.passkeyPpids[slug]) return state.passkeyPpids[slug];
    if (state.localBlocks[slug]?.size) return [...state.localBlocks[slug]][0];
    return null;
  }

  function clearVerifierCache(slug) {
    if (!state.verifiers) return;
    for (const key of Object.keys(state.verifiers)) {
      if (key.startsWith(`${slug}:`)) delete state.verifiers[key];
    }
  }

  function isSiteBlocked(slug, result = null) {
    // localBlocks (hydrated from demo status / block actions) is the source of
    // truth for the Block|Unblock control. Do not treat a stale verify reason
    // alone as blocked — that leaves the toggle stuck after a successful unblock
    // when the last result still says site_blocked.
    const ppid = result?.ppid || resolveSitePpid(slug);
    if (ppid && state.localBlocks[slug]?.has(ppid)) return true;
    return !!(state.localBlocks[slug]?.size);
  }

  function formatBlockResult(slug, result) {
    const ppid = result?.ppid || resolveSitePpid(slug);
    if (!ppid) return { text: 'Not verified yet', className: '' };
    if (isSiteBlocked(slug, result)) return { text: 'Blocked', className: 'result-deny' };
    if (result?.reason === 'doubt_required') return { text: 'Doubted', className: 'result-warn' };
    if (result?.human || isSiteVerified(result)) return { text: 'Still verified', className: 'result-ok' };
    if (result && !result.human && ['site_blocked', 'site_block', 'revoked'].includes(result.reason)) {
      return { text: 'Blocked', className: 'result-deny' };
    }
    if (['assurance_insufficient', 'not_ishuman'].includes(result?.reason)) {
      return { text: 'Insufficient assurance', className: 'result-warn' };
    }
    return { text: 'Not verified', className: 'result-warn' };
  }

  function updateStepLocks() {
    // No step is ever locked — every act stays explorable. We only pause
    // action buttons while the guided wizard is mid-run to avoid re-entrancy.
    const stepIds = ['ih-step-1', 'ih-step-2', 'ih-step-3', 'ih-step-4', 'ih-step-5'];
    for (const id of stepIds) {
      const el = $(id);
      if (el) el.classList.remove('is-locked');
    }

    const actionButtons = [
      'ih-verify-sites-btn',
      'ih-complete-human-main-btn',
      'ih-reverify-human-main-btn',
    ];
    for (const id of actionButtons) {
      const el = $(id);
      if (!el) continue;
      el.disabled = !!state.wizardRunning;
      el.classList.remove('is-gated');
    }
  }

  function setWorkflowHighlight(workflowStep) {
    const quickAct = workflowStep === 0 ? 6 : workflowToQuickAct(workflowStep);
    const currentChapter = chapterForAct(quickAct);
    for (const { id, chapter } of MAIN_WORKFLOW_STEPS) {
      const el = $(`ih-step-${id}`);
      if (!el) continue;
      el.classList.remove('is-active', 'is-done');
      if (currentChapter >= 6 || chapter < currentChapter) el.classList.add('is-done');
      else if (chapter === currentChapter) el.classList.add('is-active');
    }
    updateQuickProgress(quickAct);
    updateStepLocks();
    renderWalletSlots();
  }

  function applyAssuranceModeUI() {
    const on = assuranceDemoMode();
    document.querySelectorAll('.assurance-only').forEach((el) => {
      el.hidden = !on;
    });
    // Copy lives in the template — no runtime rewrites of titles/descriptions.
    const urls = (state.config && state.config.customer_site_urls) || {};
    const ticketsLink = $('ih-link-tickets-site');
    const trialsLink = $('ih-link-trials-site');
    const ticketsMain = $('ih-link-tickets-main');
    const trialsInline = $('ih-link-trials-inline');
    const ticketsStep2 = $('ih-link-tickets-step2');
    const trialsStep2 = $('ih-link-trials-step2');
    if (ticketsLink && urls.tickets) {
      ticketsLink.href = `${urls.tickets}?from=demo`;
    }
    if (trialsLink && urls.trials) {
      trialsLink.href = `${urls.trials}?from=demo`;
    }
    if (ticketsMain && urls.tickets) {
      ticketsMain.href = `${urls.tickets}?from=demo`;
    }
    if (trialsInline && urls.trials) {
      trialsInline.href = `${urls.trials}?from=demo`;
    }
    if (ticketsStep2 && urls.tickets) {
      ticketsStep2.href = `${urls.tickets}?from=demo`;
    }
    if (trialsStep2 && urls.trials) {
      trialsStep2.href = `${urls.trials}?from=demo`;
    }
    const personCard = $('ih-person-status-card');
    if (personCard) personCard.hidden = !on;
    renderWalletSlots();
    renderStep1Action();
    updateStepLocks();
  }

  function renderWalletSlots() {
    const passkeySlot = $('ih-wallet-slot-passkey');
    const humanSlot = $('ih-wallet-slot-human');
    const passkeyPill = $('ih-wallet-slot-passkey-pill');
    const humanPill = $('ih-wallet-slot-human-pill');
    const passkeyLabel = $('ih-wallet-slot-passkey-label');
    if (!passkeySlot || !humanSlot) return;

    const unlocked = isWalletUnlocked();
    const hasHuman = isMasterReady() || stepUpComplete();

    passkeySlot.classList.toggle('is-filled', unlocked);
    humanSlot.classList.toggle('is-filled', hasHuman);
    humanSlot.classList.toggle('is-empty', !hasHuman);

    if (passkeyPill) {
      passkeyPill.textContent = unlocked ? 'Ready' : 'Not created';
      passkeyPill.className = `demo-pill${unlocked ? ' ok' : ''}`;
    }
    if (humanPill) {
      humanPill.textContent = hasHuman ? 'Verified' : 'Available';
      humanPill.className = `demo-pill${hasHuman ? ' ok' : ' warn'}`;
    }
    if (passkeyLabel) {
      passkeyLabel.textContent = unlocked ? 'On this device' : 'Create your lemma.id to fill';
    }
  }

  async function checkPolicyDenials() {
    const panel = $('ih-policy-deny-grid');
    if (panel) panel.hidden = !state.ticketsRequiresIshuman;

    const yoursEl = $('ih-policy-deny-yours');
    const afterEl = $('ih-policy-deny-abuser');
    const hasHuman = stepUpComplete() || isMasterReady();
    const tickets = state.results.tickets;
    const insufficient = tickets
      && state.ticketsRequiresIshuman
      && !isSiteVerified(tickets)
      && ['assurance_insufficient', 'not_ishuman'].includes(tickets.reason);

    if (yoursEl) {
      yoursEl.textContent = hasHuman ? 'Has human proof' : (insufficient ? 'Deny: passkey only' : 'Awaiting policy check');
      yoursEl.className = `demo-pill${hasHuman ? ' ok' : ' deny'}`;
    }
    if (afterEl) {
      afterEl.textContent = hasHuman && tickets?.assurance === 'ishuman' ? 'Would accept' : 'Needs human proof';
      afterEl.className = `demo-pill${hasHuman && tickets?.assurance === 'ishuman' ? ' ok' : ' deny'}`;
    }

    const humanBanner = $('ih-human-outcome-banner');
    if (humanBanner) humanBanner.hidden = !(hasHuman && tickets?.assurance === 'ishuman');
    renderWalletSlots();
    renderLifecyclePanel();
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
    if (isSiteVerified(result)) {
      if (result.assurance === 'passkey') return 'Verified — passkey';
      if (result.assurance === 'ishuman') return 'Verified human — ishuman';
      return result.assurance ? `Verified (${result.assurance})` : 'Verified';
    }
    if (result.reason === 'site_blocked' || result.reason === 'revoked') return 'Blocked';
    if (result.reason === 'doubt_required') return 'Doubt — fresh proof required';
    if (result.reason === 'assurance_insufficient' || result.reason === 'not_ishuman') {
      return 'Insufficient assurance';
    }
    return 'Not verified';
  }

  function presentationFields(result, slug) {
    const presentation = result?.presentation || {};
    const credential = presentation.credential || {};
    const claims = credential.claims || credential.credentialSubject || {};
    const expiresAt = parseInt(credential.expiresAt || claims.expiresAt || '0', 10);
    return [
      ['Hostname binding', SITE_IDS[slug] || slug],
      ['PPID', result?.ppid || '—'],
      ['Assurance', result?.assurance || claims.assurance || '—'],
      ['SDK reason', result?.reason || '—'],
      ['Signature check', presentation.credential ? 'verified locally' : 'no presentation'],
      ['Revocation check', result?.reason === 'site_blocked' ? 'blocked' : 'passed locally'],
      ['Verify latency', Number.isFinite(result?.timeMs) ? `${result.timeMs.toFixed(1)}ms` : '—'],
      ['Credential expiry', expiresAt ? new Date(expiresAt * 1000).toLocaleString() : '—'],
      ['Backend decision', isSiteVerified(result) ? 'accept' : 'deny'],
    ];
  }

  function renderPresentationInspector(slug = state.presentationSlug) {
    state.presentationSlug = slug || 'tickets';
    const empty = $('ih-presentation-empty');
    const fieldsEl = $('ih-presentation-fields');
    const rawWrap = $('ih-presentation-raw-wrap');
    const rawEl = $('ih-presentation-raw');
    document.querySelectorAll('.demo-presentation-tab').forEach((tab) => {
      const active = tab.dataset.slug === state.presentationSlug;
      tab.classList.toggle('is-active', active);
      tab.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
    const result = state.results[state.presentationSlug];
    if (!result?.presentation) {
      if (empty) empty.hidden = false;
      if (fieldsEl) {
        fieldsEl.hidden = true;
        fieldsEl.innerHTML = '';
      }
      if (rawWrap) rawWrap.hidden = true;
      return;
    }
    if (empty) empty.hidden = true;
    if (fieldsEl) {
      fieldsEl.hidden = false;
      fieldsEl.innerHTML = presentationFields(result, state.presentationSlug)
        .map(([label, value]) => `<dt>${label}</dt><dd>${value}</dd>`)
        .join('');
    }
    if (rawWrap) rawWrap.hidden = false;
    if (rawEl) rawEl.textContent = pretty(result.presentation);
  }

  function renderLifecyclePanel() {
    const walletLabel = isWalletUnlocked() ? 'Unlocked' : (state.hasLocalWallet ? 'Locked' : 'Not started');
    const walletAssurance = stepUpComplete() || isMasterReady() ? 'ishuman' : 'passkey';
    const ticketsPolicy = state.ticketsRequiresIshuman ? 'ishuman' : 'passkey';
    const tickets = state.results.tickets;
    const trials = state.results.trials;
    let enforcement = 'none';
    if (tickets && isSiteBlocked('tickets', tickets)) enforcement = 'ticketing revoked';
    else if (tickets && state.localDoubts.tickets?.size) enforcement = 'ticketing doubt';
    const setText = (id, value) => {
      const el = $(id);
      if (el) el.textContent = value;
    };
    setText('ih-lifecycle-wallet', walletLabel);
    setText('ih-lifecycle-wallet-assurance', walletAssurance);
    setText('ih-lifecycle-tickets-ppid', maskPpid('tickets', tickets?.ppid));
    setText('ih-lifecycle-trials-ppid', maskPpid('trials', trials?.ppid));
    setText('ih-lifecycle-tickets-policy', ticketsPolicy);
    setText('ih-lifecycle-tickets-verdict', tickets ? formatSiteStatus(tickets) : '—');
    setText('ih-lifecycle-trials-verdict', trials ? formatSiteStatus(trials) : '—');
    setText('ih-lifecycle-enforcement', enforcement);
    const doubtStatus = $('ih-doubt-status');
    if (doubtStatus) {
      const ppid = resolveSitePpid('tickets');
      const active = ppid && state.localDoubts.tickets?.has(ppid);
      doubtStatus.textContent = active
        ? `Active doubt on ticketing PPID ${maskPpid('tickets', ppid)}`
        : 'No active doubt on ticketing.';
    }
  }

  function setDemoMode(mode) {
    state.demoMode = mode === 'simulated' ? 'live' : (mode || 'live');
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
      if (wizardStep === 7) return 6;
      return 6;
    }
    if (wizardStep <= 2) return 1;
    if (wizardStep === 3) return 2;
    return 5;
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
      await syncWalletPresence();

      let master = null;
      try {
        master = await findLocalMasterCredential();
      } catch (err) {
        if (isEncryptedWalletLockedError(err)) {
          if (!state.walletId && state.hasLocalWallet) {
            setPill('ih-lemma-status', 'LOCKED', 'deny');
          }
          return;
        }
        throw err;
      }

      if (master) {
        state.masterCredential = master;
        state.masterCredentialId = master.id;
        localStorage.setItem('ishuman_demo_master_id', state.masterCredentialId);
        renderMaster(master);
        if (assuranceDemoMode()) {
          const unlocked = !!(state.wallet?.isUnlocked && state.wallet.isUnlocked());
          setPill('ih-lemma-status', unlocked ? 'UNLOCKED' : 'LOCKED', unlocked ? 'ok' : 'deny');
        } else {
          setPill('ih-lemma-status', 'READY', 'ok');
        }
        return;
      }

      if (state.masterCredentialId && !assuranceDemoMode()) {
        setPill('ih-lemma-status', 'READY', 'ok');
        return;
      }

      if (!state.walletId) {
        setPill('ih-lemma-status', state.hasLocalWallet ? 'LOCKED' : 'NONE', state.hasLocalWallet ? 'deny' : 'warn');
      } else {
        const unlocked = !!(state.wallet?.isUnlocked && state.wallet.isUnlocked());
        setPill('ih-lemma-status', unlocked ? 'UNLOCKED' : 'LOCKED', unlocked ? 'ok' : 'deny');
      }
    } catch (err) {
      setPill('ih-lemma-status', 'NONE', 'warn');
      log('Wallet status check skipped', err.message);
    } finally {
      renderStep1Action();
      updateStepLocks();
    }
  }

  function setWizardBusy(running) {
    state.wizardRunning = running;
    const ids = [
      'ih-get-started',
      'ih-step1-primary-btn',
      'ih-verify-sites-btn',
      'ih-verify-tickets-step2',
      'ih-verify-trials-step2',
      'ih-verify-sites-advanced-btn',
      'ih-verify-tickets-btn',
      'ih-verify-trials-btn',
      'ih-unblock-tickets-btn',
      'ih-abuse-block-btn',
      'ih-abuse-recheck-btn',
      'ih-complete-human-main-btn',
      'ih-reverify-human-main-btn',
      'ih-require-ishuman-btn',
      'ih-complete-ishuman-btn',
      'ih-reverify-tickets-ishuman-btn',
      'ih-force-reverify-btn',
      'ih-run-all-operations',
      'ih-reset-demo-btn',
    ];
    for (const id of ids) {
      const el = $(id);
      if (el) el.disabled = running;
    }
    const shell = $('ih-wizard-shell');
    if (shell && !running && !state.masterCredentialId) shell.hidden = true;
  }

  async function startPrimaryDemo() {
    return runQuickDemo();
  }

  async function startLiveDemo() {
    setDemoMode('live');
    setWorkflowHighlight(1);
    updateQuickProgress(1);
    setQuickInsight('Act 1 — Create', 'Create or unlock your lemma.id, then verify on the two sites.');
    scrollToPanel('ih-step-1');
    log('Demo started', 'create or unlock your lemma.id');
  }

  function demoHeaders() {
    const headers = {};
    const testToken = ($('ih-test-token') && $('ih-test-token').value.trim()) || state.serverTestToken;
    const adminToken = ($('ih-admin-token') && $('ih-admin-token').value.trim()) || state.serverAdminToken;
    if (testToken) headers['X-Demo-Test-Token'] = testToken;
    if (adminToken) headers['X-Demo-Admin-Token'] = adminToken;
    return headers;
  }

  function getCsrfToken() {
    const names = ['lemma_wallet_csrf', 'lemma_csrf_token'];
    const cookies = String(document.cookie || '').split(';');
    for (const name of names) {
      const prefix = `${name}=`;
      for (const part of cookies) {
        const trimmed = part.trim();
        if (trimmed.startsWith(prefix)) {
          const value = decodeURIComponent(trimmed.slice(prefix.length));
          if (value) return value;
        }
      }
    }
    return null;
  }

  async function requestJson(url, options) {
    const headers = {
      'Content-Type': 'application/json',
      ...(options && options.headers ? options.headers : {}),
    };
    const csrf = getCsrfToken();
    if (csrf && !headers['X-Lemma-CSRF'] && !headers['X-CSRF-Token']) {
      headers['X-Lemma-CSRF'] = csrf;
    }
    const res = await fetch(url, {
      credentials: 'include',
      ...options,
      headers,
    });
    const raw = await res.text();
    let data = {};
    if (raw) {
      try {
        data = JSON.parse(raw);
      } catch (_) {
        const err = new Error(res.ok ? 'invalid_json_response' : `HTTP ${res.status}`);
        err.status = res.status;
        throw err;
      }
    }
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
    const operatorConsole = $('ih-operator-console');
    const testIds = [
      'ih-start-idv-btn',
      'ih-test-complete-btn',
      'ih-force-reverify-btn',
      'ih-poll-btn',
    ];
    if (operatorConsole) operatorConsole.hidden = !enabled;
    for (const id of testIds) {
      const el = $(id);
      if (el) el.hidden = !enabled;
    }
  }

  async function loadConfig() {
    state.config = await requestJson('/api/demo/ishuman/config');
    const root = $('lemma-demo') || $('ishuman-demo');
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
    const ticketsReasonCell = $('ih-block-reason-tickets');
    const trialsReasonCell = $('ih-block-reason-trials');
    const outcomeBanner = $('ih-control-outcome-banner');
    const outcomeTitle = $('ih-control-outcome-title');
    const outcomeText = $('ih-control-outcome-text');
    const tickets = state.results.tickets;
    const trials = state.results.trials;
    if (!table || !ticketsCell || !trialsCell) return;
    if (!tickets && !trials) {
      if (outcomeBanner) outcomeBanner.hidden = true;
      syncBlockSegToggle();
      renderLifecyclePanel();
      return;
    }
    const ticketsFmt = formatBlockResult('tickets', tickets);
    const trialsFmt = formatBlockResult('trials', trials);
    ticketsCell.textContent = ticketsFmt.text;
    ticketsCell.className = ticketsFmt.className;
    trialsCell.textContent = trialsFmt.text;
    trialsCell.className = trialsFmt.className;
    if (ticketsReasonCell) ticketsReasonCell.textContent = tickets?.reason || '—';
    if (trialsReasonCell) trialsReasonCell.textContent = trials?.reason || '—';
    syncBlockSegToggle();
    if (outcomeBanner && outcomeText) {
      const ticketsBlocked = isSiteBlocked('tickets', tickets);
      const ticketsDoubt = tickets?.reason === 'doubt_required'
        || (tickets?.ppid && state.localDoubts.tickets?.has(tickets.ppid));
      const trialsVerified = isSiteVerified(trials);
      if (ticketsBlocked && trialsVerified) {
        outcomeBanner.hidden = false;
        outcomeBanner.classList.remove('is-warn');
        if (outcomeTitle) outcomeTitle.textContent = 'Revocation is site-scoped';
        outcomeText.textContent = 'Ticketing is blocked. Trials remains verified.';
      } else if (ticketsDoubt && !ticketsBlocked) {
        outcomeBanner.hidden = false;
        outcomeBanner.classList.remove('is-warn');
        if (outcomeTitle) outcomeTitle.textContent = 'Doubt is temporary';
        outcomeText.textContent = 'Ticketing requires a fresh proof. Resolve doubt without affecting trials.';
      } else if (ticketsBlocked && trialsBlocked) {
        outcomeBanner.hidden = false;
        outcomeBanner.classList.add('is-warn');
        if (outcomeTitle) outcomeTitle.textContent = 'Both sites affected';
        outcomeText.textContent = 'Both sites are blocked. Unblock ticketing to reset the demo.';
      } else {
        outcomeBanner.hidden = true;
        outcomeBanner.classList.remove('is-warn');
      }
    }
    renderLifecyclePanel();
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
    await acquireWallet();

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
    await acquireWallet();
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
    await syncWalletPresence();
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
      renderStep1Action();
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

  function openIdvPopup({ demoQr = false, issueMode = '' } = {}) {
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
    popupUrl.searchParams.set('redirect_return', window.location.href);
    if (issueMode) {
      popupUrl.searchParams.set('issue_mode', issueMode);
    }
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
      state.lastPopupIssueMode = issueMode || 'passkey_setup';
      setPill('ih-lemma-status', 'POPUP BLOCKED', 'warn');
      log('Identity popup blocked', 'Allow popups for lemma.id and retry');
      setQuickInsight(
        'Popup blocked',
        'Allow popups for lemma.id, then click Retry popup or try Create again.',
        { showPopupRetry: true },
      );
      _demoIdvPopup = null;
      return null;
    }

    state.lastPopupIssueMode = issueMode || null;

    _demoIdvPopup = popup;

    setPill('ih-lemma-status', demoQr ? 'DEMO POPUP' : (issueMode === 'passkey_setup' ? 'POPUP' : 'VERIFYING'), 'warn');
    log(
      demoQr ? 'Opened demo QR popup'
        : (issueMode === 'passkey_setup' ? 'Opened passkey setup popup' : 'Opened identity check popup for lemma.id'),
    );

    let settled = false;
    const finish = async (outcome) => {
      if (settled) return;
      settled = true;
      _demoIdvPopup = null;
      window.removeEventListener('message', onMessage);
      clearInterval(closedTimer);
      log(demoQr ? 'Demo QR popup closed' : 'Lemma popup closed', outcome);
      await refreshWalletStatus().catch(() => {});
      await syncMasterFromServer().catch(() => {});
      await refreshAssuranceStatus().catch(() => {});
      await hydrateSiteVerificationFromCache().catch(() => {});
      if (outcome === 'completed') {
        setWorkflowHighlight(2);
        renderStep1Action();
        renderWalletSlots();
        updateStepLocks();
        scrollToPanel('ih-step-2');
        setQuickInsight('Act 2 — Verify', 'lemma.id ready — verify on the two demo sites below.');
      }
    };
    const onMessage = (event) => {
      if (event.origin !== window.location.origin) return;
      const type = event.data && event.data.type;
      if (type === 'ISHUMAN_IDV_COMPLETE'
        || type === 'ISHUMAN_SITE_PROOF_ISSUED'
        || type === 'LEMMA_WALLET_READY'
        || type === 'LEMMA_UNLOCK_SUCCESS') {
        finish('completed');
      } else if (type === 'ISHUMAN_IDV_CANCELLED'
        || type === 'LEMMA_WALLET_SETUP_CANCELLED'
        || type === 'LEMMA_UNLOCK_CANCELLED') {
        finish('cancelled');
      }
    };
    const closedTimer = setInterval(() => {
      if (popup.closed) finish('closed');
    }, 800);
    window.addEventListener('message', onMessage);
    return popup;
  }

  async function createLemmaIdViaPopup() {
    setDemoMode('live');
    if (assuranceDemoMode()) {
      setPill('ih-lemma-status', 'POPUP', 'warn');
      log('Opening lemma.id popup', 'passkey setup — same mechanism as demo sites');
      openIdvPopup({ issueMode: 'passkey_setup' });
      return;
    }
    return openIdvPopup({ demoQr: false });
  }

  async function createPasskeyWallet() {
    return createLemmaIdViaPopup();
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

  // Optional cross-origin demo-site wipe via hidden iframe (demo-only legacy).
  // Phase 2.1 removed the wallet *bridge* iframe; this is a separate hack for
  // clearing Heroku demo origins and is NOT used on the main clear path anymore.
  async function clearCustomerSiteCaches({ timeoutMs = 1500 } = {}) {
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
      setTimeout(() => finish(`${origin} (timeout)`), timeoutMs);
    })));
  }

  async function demoServerSelfReset() {
    if (!state.walletId || !state.wallet?.buildWalletAssertion) return;
    const assertion = await state.wallet
      .buildWalletAssertion(['wallet_id'], { wallet_id: state.walletId })
      .catch(() => null);
    if (!assertion) return;
    await requestJson('/api/demo/ishuman/self-reset', {
      method: 'POST',
      body: JSON.stringify({ wallet_id: state.walletId, wallet_assertion: assertion }),
    }).catch((err) => log('Server self-reset skipped', err.message));
  }

  // Full demo reset: wipe the lemma.id (master human proof) and every
  // site-derived proof from this browser's lemma.id wallet, clear the demo +
  // SDK caches, and signal any open customer-site tabs to drop their cached
  // sessions. After this the user re-runs "Create my lemma.id" from scratch.
  async function clearLemmaId() {
    const confirmed = window.confirm(
      'Clear your lemma.id?\n\n'
      + 'This wipes your passkey wallet and lemma.id caches in this browser. '
      + 'Demo site tabs (ticketing/trials) keep their own cache — close those tabs '
      + 'or hard-refresh them before re-running the demo.',
    );
    if (!confirmed) return;

    const clearBtns = ['ih-clear-lemma-id-top-btn'].map($).filter(Boolean);
    clearBtns.forEach((btn) => { btn.disabled = true; });

    setPill('ih-lemma-status', 'CLEARING', 'warn');
    log('Clearing lemma.id', 'wiping local wallet on lemma.id');

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

    try {
      await demoServerSelfReset().catch((err) => log('Server reset skipped', err.message));
    } catch (err) {
      log('Server reset skipped', err.message);
    }

    // Wipe the lemma.id wallet IndexedDB (master proof, derived site proofs,
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
    window.globalLemmaWallet = null;
    state.walletId = null;
    state.walletSecret = null;
    state.hasLocalWallet = false;
    state.masterCredential = null;
    state.masterCredentialId = '';
    state.sessionId = '';
    state.results = {};
    state.passkeyPpids = {};
    state.assuranceStatus = null;
    state.trialsRequiresIshuman = false;
    state.lastPopupIssueMode = null;
    state.verifiers = {};
    state.lastVerifyMs = { tickets: null, trials: null };
    for (const slug of SITE_SLUGS) state.localBlocks[slug].clear();

    const wid = $('ih-wallet-id');
    if (wid) wid.textContent = '-';
    renderStep1Action();
    setPill('ih-lemma-status', 'CLEARED', 'warn');
    setPill('ih-person-status', '—', '');
    setDemoMode('live');
    setWorkflowHighlight(1);
    for (const slug of SITE_SLUGS) {
      setPill(`ih-${slug}-pill`, 'Pending', '');
      const ppidEl = $(`ih-${slug}-ppid`);
      if (ppidEl) ppidEl.textContent = PPID_PLACEHOLDER[slug];
      const assuranceEl = $(`ih-${slug}-assurance`);
      if (assuranceEl) assuranceEl.textContent = '—';
      const card = $(`ih-${slug}-card`);
      if (card) card.classList.remove('is-human', 'is-deny', 'is-pending');
    }
    updatePpidCompare();
    updateBlockResultsTable();
    const stepupCompare = $('ih-stepup-compare');
    if (stepupCompare) stepupCompare.hidden = true;
    const policyGrid = $('ih-policy-deny-grid');
    if (policyGrid) policyGrid.hidden = true;
    syncTrialsPolicyToggle();
    const humanBanner = $('ih-human-outcome-banner');
    if (humanBanner) humanBanner.hidden = true;
    const retryBtn = $('ih-popup-retry-btn');
    if (retryBtn) retryBtn.hidden = true;
    if (window.LemmaPlatformAuth && typeof window.LemmaPlatformAuth.applyNavButtons === 'function') {
      window.LemmaPlatformAuth.applyNavButtons({ mode: 'none' });
    }
    renderWalletSlots();
    scrollToPanel('lemma-demo');
    log('lemma.id cleared', 'click Get started to begin again');
    clearBtns.forEach((btn) => { btn.disabled = false; });
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
    renderStep1Action();
    updateStepLocks();
  }

  function verifierFor(slug, options = {}) {
    if (!window.IsHumanVerifier) throw new Error('IsHumanVerifier SDK not loaded');
    const requiredAssurance = demoRequiredAssurance(slug, options);
    const cacheKey = `${slug}:${requiredAssurance}`;
    if (!state.verifiers) state.verifiers = {};
    if (state.verifiers[cacheKey]) return state.verifiers[cacheKey];
    state.verifiers[cacheKey] = new window.IsHumanVerifier({
      siteId: SITE_IDS[slug],
      lemmaOrigin: window.location.origin,
      debug: true,
      autoProvision: true,
      requiredAssurance,
      isBlockedLocally: (ppid) => siteDecisionLocally(slug, ppid),
    });
    return state.verifiers[cacheKey];
  }

  async function resolveDisplayedPpid(verifier, backend, slug, options, requiredAssurance) {
    const raw = await verifier.verify({
      autoProvision: false,
      requiredAssurance,
      ...options,
    });
    if (raw?.ppid) return raw.ppid;
    if (backend?.ppid) return backend.ppid;
    return resolveSitePpid(slug);
  }

  async function verifySite(slug, options = {}) {
    if (!window.IsHumanVerifier) throw new Error('IsHumanVerifier SDK not loaded');
    const requiredAssurance = demoRequiredAssurance(slug, options);
    const verifier = verifierFor(slug, { requiredAssurance });
    const backend = await verifier.verifyForBackend({
      autoProvision: true,
      requiredAssurance,
      ...options,
    });
    const ppid = await resolveDisplayedPpid(verifier, backend, slug, options, requiredAssurance);
    const verified = !!(backend.ok || backend.human);
    const result = {
      human: verified,
      ppid: ppid || resolveSitePpid(slug),
      assurance: backend.assurance,
      presentation: backend.presentation,
      reason: backend.reason,
      timeMs: backend.timeMs || 0,
    };
    state.results[slug] = result;
    if (Number.isFinite(result.timeMs)) state.lastVerifyMs[slug] = result.timeMs;
    if (assuranceDemoMode() && requiredAssurance === 'passkey' && result.ppid) {
      state.passkeyPpids[slug] = result.ppid;
    }
    renderSite(slug, result);
    renderProofReceipt();
    renderPresentationInspector(slug);
    renderLifecyclePanel();
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
    setQuickInsight('Act 2 — Verify', 'Minting site-private stamps for ticketing and trials…');
    updateQuickProgress(2);
    await verifySite('tickets');
    await verifySite('trials');
    if (bothSitesVerified()) {
      setQuickInsight('Act 2 — PPIDs', 'Same lemma.id — different private IDs. Next: inspect presentations.');
      setWorkflowHighlight(3);
      scrollToPanel('ih-step-3');
    }
  }

  async function recheckBothSitesAfterBlock() {
    await verifySite('tickets');
    await verifySite('trials');
    updateBlockResultsTable();
  }

  function renderSite(slug, result) {
    const verified = isSiteVerified(result);
    const tone = verified
      ? 'ok'
      : (result.reason === 'site_blocked' || result.reason === 'revoked' ? 'deny' : '');
    setPill(`ih-${slug}-pill`, formatSiteStatus(result), tone);
    const card = $(`ih-${slug}-card`);
    if (card) {
      card.classList.remove('is-human', 'is-deny', 'is-pending');
      if (verified) card.classList.add('is-human');
      else if (result.reason === 'site_blocked' || result.reason === 'revoked') card.classList.add('is-deny');
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
    clearVerifierCache('tickets');
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
    setWorkflowHighlight(5);
    scrollToPanel('ih-step-5');
    updateBlockResultsTable();
    updateQuickProgress(5);
    setQuickInsight(
      'Act 5 — Revocation',
      'Ticketing blocked; trials untouched. Fresh verification cannot clear a site block.',
    );
  }

  async function createTicketingDoubt() {
    const result = state.results.tickets || await verifySite('tickets');
    if (!result.ppid) throw new Error('Ticketing PPID unavailable');
    await requestJson('/api/demo/ishuman/site-doubt', {
      method: 'POST',
      body: JSON.stringify({
        site_slug: 'tickets',
        ppid: result.ppid,
        reason: 'Demo doubt: require fresh proof on ticketing',
      }),
    });
    state.localDoubts.tickets.add(result.ppid);
    clearVerifierCache('tickets');
    log('Ticketing doubt created', short(result.ppid));
    await verifySite('tickets');
    await verifySite('trials');
    setWorkflowHighlight(5);
    scrollToPanel('ih-step-5');
    setQuickInsight('Act 5 — Doubt', 'Ticketing returned doubt_required. Resolve with a deliberate fresh proof.');
  }

  async function resolveTicketingDoubt() {
    const result = state.results.tickets || await verifySite('tickets');
    if (!result.ppid) throw new Error('Ticketing PPID unavailable');
    if (result.reason !== 'doubt_required' && !state.localDoubts.tickets.has(result.ppid)) {
      throw new Error('No active doubt on ticketing — create one first');
    }
    const verifier = verifierFor('tickets');
    const fresh = await verifier.verifyFreshForBackend({
      requiredAssurance: demoRequiredAssurance('tickets'),
    });
    if (!fresh.ok) {
      throw new Error(fresh.reason || 'fresh_verification_failed');
    }
    await requestJson('/api/demo/ishuman/clear-site-doubt', {
      method: 'POST',
      body: JSON.stringify({ site_slug: 'tickets', ppid: result.ppid }),
    });
    state.localDoubts.tickets.delete(result.ppid);
    clearVerifierCache('tickets');
    await verifySite('tickets');
    await verifySite('trials');
    setQuickInsight('Act 5 — Doubt cleared', 'Fresh proof resolved the ticketing doubt. Trials was unaffected.');
  }

  async function requireIsHumanOnTickets() {
    const result = state.results.tickets
      || await verifySite('tickets', { requiredAssurance: 'passkey' });
    if (!result.ppid) throw new Error('Ticketing PPID unavailable');
    if (result.ppid) state.passkeyPpids.tickets = result.ppid;

    await requestJson('/api/demo/ishuman/require-ishuman', {
      method: 'POST',
      headers: demoHeaders(),
      body: JSON.stringify({
        site_slug: 'tickets',
        ppid: result.ppid,
        reason: 'Demo: ticketing requires human proof assurance',
      }),
    });
    log('Site doubt created', 'ticketing requires human proof step-up');
    setWorkflowHighlight(5);
    scrollToPanel('ih-control-escalation');
  }

  async function completeIsHumanVerification() {
    if (state.config?.test_verify_enabled) {
      await verifyOnceTestMode();
    } else {
      await openIdvPopup({ demoQr: false });
    }
    await refreshAssuranceStatus();
    await checkPolicyDenials();
    log('Human proof verification complete', 're-verify ticketing with human proof assurance');
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
    if (!before) throw new Error('No passkey ticketing PPID snapshot — verify in act 2 first');
    const result = await verifySite('tickets', { requiredAssurance: 'ishuman' });
    updateStepUpCompare(before, result);
    await checkPolicyDenials();
    if (result.ppid === before && result.assurance === 'ishuman') {
      log('Step-up success', 'same PPID with human proof assurance');
      setWorkflowHighlight(5);
      scrollToPanel('ih-step-5');
      setQuickInsight('Act 4 — Escalation', 'Same private ID, human proof assurance — ready for doubt/revocation.');
      const humanBanner = $('ih-human-outcome-banner');
      if (humanBanner) humanBanner.hidden = false;
    } else {
      log('Step-up check', `ppid match=${result.ppid === before} assurance=${result.assurance}`);
    }
    return result;
  }

  async function unblockTickets() {
    const ppids = new Set([
      resolveSitePpid('tickets'),
      ...state.localBlocks.tickets,
    ].filter(Boolean));
    if (!ppids.size) {
      throw new Error('Ticketing PPID unavailable — verify in act 2 first');
    }

    let unblockedAny = false;
    for (const ppid of ppids) {
      const payload = await requestJson('/api/demo/ishuman/site-unblock', {
        method: 'POST',
        body: JSON.stringify({ site_slug: 'tickets', ppid }),
      });
      if (payload?.unblocked !== false) unblockedAny = true;
      state.localBlocks.tickets.delete(ppid);
    }
    // Drop stale blocked verify results immediately so the Block control can
    // fire again even if the follow-up verify is slow or fails.
    if (state.results.tickets && ['site_blocked', 'site_block', 'revoked'].includes(state.results.tickets.reason)) {
      state.results.tickets = {
        ...state.results.tickets,
        human: true,
        reason: 'unblocked',
      };
    }
    clearVerifierCache('tickets');
    if (window.IsHumanVerifier?.broadcastBlockUpdate) {
      for (const ppid of ppids) {
        window.IsHumanVerifier.broadcastBlockUpdate({
          type: 'SITE_BLOCK_UPDATE',
          siteId: SITE_IDS.tickets,
          ppid,
          reason: 'demo_site_unblock',
        });
      }
    }

    const netJson = $('ih-master-json');
    if (netJson) netJson.textContent = pretty({ unblocked: unblockedAny, ppids: [...ppids] });
    log('Ticketing site block removed', [...ppids].map(short).join(', '));
    try {
      await refreshStatus().catch(() => {});
      await verifySite('tickets');
      await verifySite('trials');
      await refreshAbuseChecks();
    } finally {
      syncBlockSegToggle();
      updateBlockResultsTable();
      updateStepLocks();
    }
    setQuickInsight('Act 3 — Enforce', unblockedAny
      ? 'Ticketing unblocked — block again anytime to retry the demo.'
      : 'No active ticketing block found — both sites rechecked.');
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
      renderStep1Action();
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

  async function runPreflightCheck() {
    markOperationRunning('preflight');
    if (!window.IsHumanVerifier) {
      return makeOperationResult('preflight', 'fail', 'IsHumanVerifier SDK not loaded');
    }
    if (!state.config) {
      await loadConfig();
    }
    const sites = state.config?.sites || [];
    const domains = new Set(sites.map((site) => site.site_domain));
    const ok = domains.has(SITE_IDS.tickets) && domains.has(SITE_IDS.trials);
    return makeOperationResult(
      'preflight',
      ok ? 'pass' : 'fail',
      ok ? `${sites.length} demo sites seeded` : 'Demo sites missing from config',
      { sites: domains, sdkLoaded: true },
    );
  }

  async function ensureLemmaWallet() {
    markOperationRunning('wallet');
    await initWalletPassive();
    if (!state.walletId) {
      return makeOperationResult(
        'wallet',
        'fail',
        'Create or unlock lemma.id first (Run 3-minute demo)',
        { walletId: state.walletId, masterCredentialId: state.masterCredentialId },
      );
    }
    const ready = !!state.walletId || isMasterReady();
    return makeOperationResult(
      'wallet',
      ready ? 'pass' : 'fail',
      ready ? `Wallet ${short(state.walletId)}` : 'Create or unlock lemma.id first',
      { walletId: state.walletId, masterCredentialId: state.masterCredentialId },
    );
  }

  async function verifyDemoSites() {
    markOperationRunning('site_proofs');
    await verifySite('tickets');
    await verifySite('trials');
    const tickets = state.results.tickets;
    const trials = state.results.trials;
    const bothOk = isSiteVerified(tickets) && isSiteVerified(trials);
    const distinct = !!(tickets?.ppid && trials?.ppid && tickets.ppid !== trials.ppid);
    const status = bothOk && distinct ? 'pass' : 'fail';
    return makeOperationResult(
      'site_proofs',
      status,
      status === 'pass'
        ? 'Distinct PPIDs on ticketing and trials'
        : 'Both sites must verify with different PPIDs',
      { tickets: { ppid: tickets?.ppid, assurance: tickets?.assurance }, trials: { ppid: trials?.ppid, assurance: trials?.assurance } },
    );
  }

  async function verifyRelyingSiteActions() {
    markOperationRunning('relying_sites');
    const payload = await requestJson('/api/demo/ishuman/relying-site-preflight');
    const sites = payload.sites || {};
    const ticketsOk = sites.tickets?.success === true;
    const trialsOk = sites.trials?.success === true;
    const ok = ticketsOk && trialsOk;
    return makeOperationResult(
      'relying_sites',
      ok ? 'pass' : 'fail',
      ok ? 'Ticketing and trials demo apps reachable' : 'One or more relying-site health checks failed',
      sites,
    );
  }

  async function requireIsHumanOnTicketing() {
    markOperationRunning('escalation');
    await requireIsHumanOnTickets();
    return makeOperationResult(
      'escalation',
      'pass',
      'Site doubt created on ticketing',
      { ppid: state.results.tickets?.ppid },
    );
  }

  async function completeIsHumanStepUp() {
    markOperationRunning('step_up');
    if (state.config?.test_verify_enabled) {
      await verifyOnceTestMode();
    } else if (!isMasterReady()) {
      return makeOperationResult(
        'step_up',
        'skip',
        'Complete human proof verification manually, then re-run checks',
        {},
      );
    }
    const result = await reverifyTicketsIshuman();
    const ok = result.assurance === 'ishuman' && isSiteVerified(result);
    return makeOperationResult(
      'step_up',
      ok ? 'pass' : 'fail',
      ok ? 'Ticketing verified with human proof assurance' : `Unexpected assurance: ${result.assurance || 'none'}`,
      { ppid: result.ppid, assurance: result.assurance },
    );
  }

  async function assertSamePpidAfterStepUp() {
    markOperationRunning('same_ppid');
    const before = state.passkeyPpids.tickets;
    const after = state.results.tickets?.ppid;
    const ok = !!(before && after && before === after && state.results.tickets?.assurance === 'ishuman');
    return makeOperationResult(
      'same_ppid',
      ok ? 'pass' : 'fail',
      ok ? 'Same PPID before and after step-up' : 'PPID changed or assurance is not human proof',
      { beforePpid: before, afterPpid: after, assurance: state.results.tickets?.assurance },
    );
  }

  async function blockTicketingPpid() {
    markOperationRunning('site_block');
    await blockTickets();
    const tickets = state.results.tickets;
    const blocked = !!(tickets && !tickets.human && tickets.reason === 'site_blocked');
    return makeOperationResult(
      'site_block',
      blocked ? 'pass' : 'fail',
      blocked ? 'Ticketing denied after site block' : `Ticketing result: ${tickets?.reason || 'unknown'}`,
      { tickets: { human: tickets?.human, reason: tickets?.reason } },
    );
  }

  async function assertSiteScopedRevocation() {
    markOperationRunning('scoped_revocation');
    const tickets = state.results.tickets;
    const trials = state.results.trials;
    const ok = !!(tickets && !tickets.human && isSiteVerified(trials));
    return makeOperationResult(
      'scoped_revocation',
      ok ? 'pass' : 'fail',
      ok ? 'Ticketing blocked; trials still verified' : 'Trials should remain verified after ticketing block',
      {
        tickets: { human: tickets?.human, reason: tickets?.reason },
        trials: { human: trials?.human, reason: trials?.reason },
      },
    );
  }

  async function resetDemoState() {
    markOperationRunning('reset');
    const ppid = state.results.tickets?.ppid;
    let unblocked = false;
    if (ppid && state.results.tickets?.reason === 'site_blocked') {
      await unblockTickets();
      unblocked = true;
    }
    await refreshStatus().catch(() => {});
    return makeOperationResult(
      'reset',
      'pass',
      unblocked ? 'Ticketing unblocked for next run' : 'Demo state refreshed',
      { unblocked },
    );
  }

  async function runAllOperations() {
    if (operationsRunning) return operationResults;
    operationsRunning = true;
    initOperationsUI();
    setOperationsSummary('run', 'Running checks…');
    const runBtn = $('ih-run-all-operations');
    if (runBtn) runBtn.disabled = true;

    const steps = [
      runPreflightCheck,
      ensureLemmaWallet,
      verifyDemoSites,
      verifyRelyingSiteActions,
      requireIsHumanOnTicketing,
      completeIsHumanStepUp,
      assertSamePpidAfterStepUp,
      blockTicketingPpid,
      assertSiteScopedRevocation,
      resetDemoState,
    ];

    try {
      for (const step of steps) {
        const result = await step();
        setOperationResult(result);
        if (result.status === 'fail') {
          setOperationsSummary('fail', `Failed: ${result.label}`);
          return operationResults;
        }
        if (result.status === 'skip') {
          setOperationsSummary('fail', `Skipped: ${result.label}`);
          return operationResults;
        }
      }
      setOperationsSummary('pass', `${steps.length} checks passed`);
      setWorkflowHighlight(0);
      log('Operations check complete', `${steps.length} checks passed`);
    } catch (err) {
      setOperationsSummary('fail', err.message);
      log('Operations check stopped', err.message);
    } finally {
      operationsRunning = false;
      if (runBtn) runBtn.disabled = false;
    }
    return operationResults;
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
        scrollToPanel('ih-step-3');
        await sleep(1500);

        setWizardStep(4, 'Requiring human proofs on ticketing…');
        scrollToPanel('ih-step-4');
        await requireIsHumanOnTickets();

        setWizardStep(5, 'Complete human proof verification…');
        if (state.config?.test_verify_enabled) {
          await verifyOnceTestMode();
          await reverifyTicketsIshuman();
        } else {
          log('Complete IDV manually', 'use Complete human proof verification button');
        }

        setWizardStep(6, 'Blocking abusive ticketing PPID…');
        scrollToPanel('ih-abuse-panel');
        await blockTickets();

        setWizardStep(7, 'Demo complete — same ticketing PPID with human proof assurance, then site-scoped revoke.');
        renderStep1Action();
        log('Assurance guided demo complete');
        return;
      }

      setWizardStep(2, 'Confirming passkey proofs…');
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
      renderStep1Action();
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
        const requiredAssurance = demoRequiredAssurance(slug);
        const raw = await verifier.checkStatus({ requiredAssurance });
        const ppid = raw.ppid || state.passkeyPpids[slug] || null;
        const verified = isSiteVerified({ ...raw, ppid });
        const result = {
          ...raw,
          ppid,
          human: verified,
        };
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
    for (const slug of SITE_SLUGS) {
      state.localBlocks[slug].clear();
      state.localDoubts[slug].clear();
    }
    const siteIdToSlug = { site_demo_tickets: 'tickets', site_demo_trials: 'trials' };
    for (const block of payload.site_blocks || []) {
      const slug = siteIdToSlug[block.site_id];
      if (slug && block.ppid) state.localBlocks[slug].add(block.ppid);
    }
    for (const doubt of payload.site_doubts || []) {
      const slug = siteIdToSlug[doubt.site_id];
      if (slug && doubt.ppid) state.localDoubts[slug].add(doubt.ppid);
    }
    const netJson = $('ih-master-json');
    if (netJson) netJson.textContent = pretty(payload);
    if (state.masterCredentialId) {
      renderStep1Action();
    }
    updateBlockResultsTable();
    updateStepLocks();
    return payload;
  }

  function bindClear(id) {
    const el = $(id);
    if (!el) return;
    el.addEventListener('click', async () => {
      el.disabled = true;
      try {
        await clearLemmaId();
      } catch (err) {
        log('Clear failed', err.message);
        setPill('ih-lemma-status', 'ERROR', 'deny');
      } finally {
        el.disabled = false;
      }
    });
  }

  function bind(id, fn) {
    const el = $(id);
    if (!el) return;
      el.addEventListener('click', async () => {
      if (state.wizardRunning) return;
      el.disabled = true;
      try {
        await fn();
      } catch (err) {
        log('Error', err.message);
        setQuickInsight('Heads up', err.message);
        const netJson = $('ih-master-json');
        if (netJson) netJson.textContent = pretty(err.payload || { error: err.message });
      } finally {
        if (!state.wizardRunning) el.disabled = false;
      }
    });
  }

  function initHeroDiagramWires() {
    const stage = document.querySelector('.demo-diagram-stage');
    const svg = stage && stage.querySelector('.demo-diagram-wires');
    if (!stage || !svg) return;

    const pathWalletPasskey = svg.querySelector('#demo-wire-wallet-passkey');
    const pathPasskeyTicketing = svg.querySelector('#demo-wire-passkey-ticketing');
    const pathPasskeySaas = svg.querySelector('#demo-wire-passkey-saas');
    const walletAnchor = stage.querySelector('.demo-diagram-wallet .demo-diagram-icon-square');
    const passkeyAnchor = stage.querySelector('.demo-diagram-passkey .demo-diagram-shield');
    const ticketingAnchor = stage.querySelector('.demo-diagram-site-square--ticketing');
    const saasAnchor = stage.querySelector('.demo-diagram-site-square--saas');
    if (
      !pathWalletPasskey ||
      !pathPasskeyTicketing ||
      !pathPasskeySaas ||
      !walletAnchor ||
      !passkeyAnchor ||
      !ticketingAnchor ||
      !saasAnchor
    ) {
      return;
    }

    function anchorPoint(el, side) {
      const stageRect = stage.getBoundingClientRect();
      const rect = el.getBoundingClientRect();
      const y = rect.top + rect.height / 2 - stageRect.top;
      let x;
      if (side === 'right') x = rect.right - stageRect.left;
      else if (side === 'left') x = rect.left - stageRect.left;
      else x = rect.left + rect.width / 2 - stageRect.left;
      return { x, y };
    }

    function insetToward(start, end, amount) {
      const dx = end.x - start.x;
      const dy = end.y - start.y;
      const length = Math.hypot(dx, dy);
      if (length <= amount) return { x: start.x, y: start.y };
      const ratio = (length - amount) / length;
      return { x: start.x + dx * ratio, y: start.y + dy * ratio };
    }

    function layout() {
      const width = stage.clientWidth;
      const height = stage.clientHeight;
      if (width < 1 || height < 1) return;

      svg.setAttribute('viewBox', `0 0 ${width} ${height}`);

      const walletOut = anchorPoint(walletAnchor, 'right');
      const passkeyIn = anchorPoint(passkeyAnchor, 'left');
      const passkeyOut = anchorPoint(passkeyAnchor, 'right');
      const ticketingIn = anchorPoint(ticketingAnchor, 'left');
      const saasIn = anchorPoint(saasAnchor, 'left');
      const ticketingEnd = insetToward(passkeyOut, ticketingIn, 10);
      const saasEnd = insetToward(passkeyOut, saasIn, 10);

      pathWalletPasskey.setAttribute('d', `M${walletOut.x} ${walletOut.y} H${passkeyIn.x}`);
      pathPasskeyTicketing.setAttribute(
        'd',
        `M${passkeyOut.x} ${passkeyOut.y} L${ticketingEnd.x} ${ticketingEnd.y}`,
      );
      pathPasskeySaas.setAttribute(
        'd',
        `M${passkeyOut.x} ${passkeyOut.y} L${saasEnd.x} ${saasEnd.y}`,
      );
    }

    function scheduleLayout() {
      window.requestAnimationFrame(layout);
    }

    scheduleLayout();
    if (typeof ResizeObserver !== 'undefined') {
      const observer = new ResizeObserver(scheduleLayout);
      observer.observe(stage);
      const hero = stage.closest('.demo-hero');
      if (hero) observer.observe(hero);
      [walletAnchor, passkeyAnchor, ticketingAnchor, saasAnchor].forEach((el) => observer.observe(el));
    }
    window.addEventListener('resize', scheduleLayout);
  }

  async function boot() {
    setDemoMode('live');
    setWorkflowHighlight(1);
    showQuickInsight(true);
    bind('ih-get-started', startLiveDemo);
    bind('ih-step1-primary-btn', async () => {
      setDemoMode('live');
      const action = $('ih-step1-primary-btn')?.dataset.action;
      if (action === 'unlock') {
        try {
          await initWallet();
          await refreshWalletStatus();
        } catch (err) {
          log('Wallet unlock needed', err.message);
          openIdvPopup({ issueMode: 'unlock' });
        }
        return;
      }
      createLemmaIdViaPopup();
    });
    bindClear('ih-clear-lemma-id-top-btn');
    bind('ih-start-idv-btn', startIdentityVerification);
    bind('ih-test-complete-btn', completeTestModeVerification);
    bind('ih-poll-btn', pollAndStoreMaster);
    bind('ih-verify-sites-btn', verifyBothSites);
    bind('ih-verify-sites-advanced-btn', verifyBothSites);
    bind('ih-verify-tickets-step2', () => verifySite('tickets'));
    bind('ih-verify-trials-step2', () => verifySite('trials'));
    bind('ih-refresh-status-btn', refreshStatus);
    bind('ih-verify-tickets-btn', () => verifySite('tickets'));
    bind('ih-verify-trials-btn', () => verifySite('trials'));
    bind('ih-abuse-recheck-btn', recheckBothSitesAfterBlock);
    const blockBtn = $('ih-abuse-block-btn');
    const unblockBtn = $('ih-unblock-tickets-btn');
    if (blockBtn) {
      blockBtn.addEventListener('click', () => {
        if (state.wizardRunning || state.blockToggleBusy) return;
        if (isSiteBlocked('tickets', state.results.tickets)) {
          syncBlockSegToggle();
          return;
        }
        state.blockToggleBusy = true;
        setSegToggleActive('ih-block-seg', true);
        blockTickets()
          .catch((err) => {
            log('Error', err.message);
            setQuickInsight('Heads up', err.message);
          })
          .finally(() => {
            state.blockToggleBusy = false;
            syncBlockSegToggle();
            updateBlockResultsTable();
          });
      });
    }
    if (unblockBtn) {
      unblockBtn.addEventListener('click', () => {
        if (state.wizardRunning || state.blockToggleBusy) return;
        if (!isSiteBlocked('tickets', state.results.tickets)) {
          syncBlockSegToggle();
          return;
        }
        state.blockToggleBusy = true;
        setSegToggleActive('ih-block-seg', false);
        unblockTickets()
          .catch((err) => {
            log('Error', err.message);
            setQuickInsight('Heads up', err.message);
          })
          .finally(() => {
            state.blockToggleBusy = false;
            syncBlockSegToggle();
            updateBlockResultsTable();
          });
      });
    }
    const trialsPasskeyBtn = $('ih-trials-passkey-btn');
    const trialsIshumanBtn = $('ih-trials-ishuman-toggle');
    if (trialsPasskeyBtn) {
      trialsPasskeyBtn.addEventListener('click', () => {
        if (!state.trialsRequiresIshuman) {
          syncTrialsPolicyToggle();
          return;
        }
        onTrialsPolicyToggleChange(false).catch((err) => log('Error', err.message));
      });
    }
    if (trialsIshumanBtn) {
      trialsIshumanBtn.addEventListener('click', () => {
        if (state.trialsRequiresIshuman) {
          syncTrialsPolicyToggle();
          return;
        }
        onTrialsPolicyToggleChange(true).catch((err) => log('Error', err.message));
      });
    }
    const ticketsPasskeyBtn = $('ih-tickets-passkey-btn');
    const ticketsIshumanBtn = $('ih-tickets-ishuman-toggle');
    if (ticketsPasskeyBtn) {
      ticketsPasskeyBtn.addEventListener('click', () => {
        if (!state.ticketsRequiresIshuman) {
          syncTicketsPolicyToggle();
          return;
        }
        onTicketsPolicyToggleChange(false).catch((err) => log('Error', err.message));
      });
    }
    if (ticketsIshumanBtn) {
      ticketsIshumanBtn.addEventListener('click', () => {
        if (state.ticketsRequiresIshuman) {
          syncTicketsPolicyToggle();
          return;
        }
        onTicketsPolicyToggleChange(true).catch((err) => log('Error', err.message));
      });
    }
    bind('ih-escalation-recheck-btn', () => verifySite('tickets'));
    bind('ih-create-doubt-btn', createTicketingDoubt);
    bind('ih-resolve-doubt-btn', resolveTicketingDoubt);
    document.querySelectorAll('.demo-presentation-tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        renderPresentationInspector(tab.dataset.slug);
      });
    });
    syncTrialsPolicyToggle();
    syncTicketsPolicyToggle();
    syncBlockSegToggle();
    bind('ih-require-ishuman-btn', requireIsHumanOnTickets);
    bind('ih-complete-ishuman-btn', completeIsHumanVerification);
    bind('ih-reverify-tickets-ishuman-btn', reverifyTicketsIshuman);
    bind('ih-complete-human-main-btn', completeIsHumanVerification);
    bind('ih-reverify-human-main-btn', reverifyTicketsIshuman);
    bind('ih-popup-retry-btn', () => {
      const mode = state.lastPopupIssueMode || 'passkey_setup';
      openIdvPopup({ issueMode: mode === 'unlock' ? 'unlock' : mode });
    });
    bind('ih-run-all-operations', runAllOperations);
    bind('ih-reset-demo-btn', clearLemmaId);
    bind('ih-force-reverify-btn', forceFreshIdv);

    initOperationsUI();
    initHeroDiagramWires();

    // Config failure must not leave the page dead — buttons are already bound.
    await loadConfig().catch((err) => log('Demo config load failed', err.message));

    try {
      await refreshWalletStatus();
      await hydrateSiteVerificationFromCache();
      if (state.walletId) await refreshAssuranceStatus().catch(() => {});
      await refreshStatus().catch(() => {});
      updateBlockResultsTable();
      updateStepLocks();
      renderWalletSlots();
      renderLifecyclePanel();
      renderPresentationInspector();
    } catch (err) {
      log('Startup check skipped', err.message);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  window.runAllOperations = runAllOperations;
  window.runQuickDemo = runQuickDemo;
})();
