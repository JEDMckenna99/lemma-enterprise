(function () {
  'use strict';

  const INTRO_VERIFY_ONCE =
    'Create or unlock your browser wallet, complete a one-time identity check, and reuse the proof on any Lemma-enabled site.';
  const INTRO_SITE_PROOF =
    'Lemma issues a site-scoped human proof from your wallet. Passkey unlock is once per day; IDV runs only if you have no master proof yet.';
  const INTRO_CLAIM =
    'Identity verified. Your lemma.id is saved on this device. Passkey setup happens automatically the first time you verify on a site.';
  const INTRO_FRESH_REVOKED =
    'Your previous verification was revoked. Complete a fresh identity check to regain access. The site never sees your documents.';
  const INTRO_FRESH_BLOCKED =
    'This site asked you to re-verify before continuing. Complete a fresh identity check to regain access. The site never sees your documents.';

  /** @type {Record<string, object>} */
  const SCENES = {
    verify_once: {
      intro: INTRO_VERIFY_ONCE,
      status: { message: 'Ready when you are.', tone: 'info' },
      primary: { text: 'Create lemma.id', visible: true },
      cancel: 'Cancel',
    },
    unlock_lemma: {
      intro: INTRO_VERIFY_ONCE,
      status: { message: 'Ready when you are.', tone: 'info' },
      primary: { text: 'Unlock lemma.id', visible: true },
      cancel: 'Cancel',
    },
    claim_lemma: {
      intro: INTRO_CLAIM,
      status: { message: 'Your lemma.id is ready to claim on this device.', tone: 'info' },
      primary: { text: 'Claim lemma.id', visible: true },
      cancel: 'Cancel',
    },
    verify_ready: {
      intro: INTRO_VERIFY_ONCE,
      status: { message: 'Ready when you are.', tone: 'info' },
      primary: { text: 'Unlock wallet & verify', visible: true },
      cancel: 'Cancel',
    },
    loading_check_wallet: {
      intro: INTRO_VERIFY_ONCE,
      status: { message: 'Checking wallet…', tone: 'loading' },
      primary: { visible: false },
      cancel: 'Cancel',
    },
    loading_unlock: {
      intro: INTRO_VERIFY_ONCE,
      status: { message: 'Unlocking lemma.id…', tone: 'loading' },
      primary: { visible: false },
      cancel: 'Cancel',
    },
    loading_idv: {
      intro: INTRO_VERIFY_ONCE,
      status: { message: 'Opening identity check…', tone: 'loading' },
      primary: { visible: false },
      cancel: 'Cancel',
    },
    loading_finalize: {
      intro: INTRO_VERIFY_ONCE,
      status: { message: 'Finalizing your verification…', tone: 'loading' },
      primary: { visible: false },
      cancel: 'Cancel',
    },
    site_proof: {
      intro: INTRO_SITE_PROOF,
      status: { message: 'Ready when you are.', tone: 'info' },
      primary: { visible: false },
      cancel: 'Cancel',
    },
    site_proof_needs_idv: {
      intro: INTRO_SITE_PROOF,
      status: { message: 'Complete identity verification once, then we issue your site proof.', tone: 'info' },
      primary: { text: 'Create lemma.id', visible: true },
      cancel: 'Cancel',
    },
    site_proof_unlock: {
      intro: INTRO_SITE_PROOF,
      status: { message: 'Complete identity verification once, then we issue your site proof.', tone: 'info' },
      primary: { text: 'Unlock lemma.id', visible: true },
      cancel: 'Cancel',
    },
    site_proof_claim: {
      intro: INTRO_SITE_PROOF,
      status: { message: 'Complete identity verification once, then we issue your site proof.', tone: 'info' },
      primary: { text: 'Claim lemma.id', visible: true },
      cancel: 'Cancel',
    },
    site_proof_verify: {
      intro: INTRO_SITE_PROOF,
      status: { message: 'Complete identity verification once, then we issue your site proof.', tone: 'info' },
      primary: { text: 'Unlock wallet & verify', visible: true },
      cancel: 'Cancel',
    },
    site_proof_issuing: {
      intro: INTRO_SITE_PROOF,
      status: { message: 'Issuing site proof…', tone: 'loading' },
      primary: { visible: false },
      cancel: 'Cancel',
    },
    site_proof_success: {
      intro: INTRO_SITE_PROOF,
      status: { message: 'Site proof ready.', tone: 'success' },
      primary: { visible: false },
      cancel: 'Cancel',
    },
    fresh_idv_blocked: {
      intro: INTRO_FRESH_BLOCKED,
      status: { message: 'Ready when you are.', tone: 'info' },
      primary: { visible: false },
      cancel: 'Cancel',
    },
    fresh_idv_revoked: {
      intro: INTRO_FRESH_REVOKED,
      status: { message: 'Ready when you are.', tone: 'info' },
      primary: { visible: false },
      cancel: 'Cancel',
    },
    fresh_idv_success: {
      intro: INTRO_FRESH_REVOKED,
      status: { message: 'Fresh verification complete. Re-entry granted.', tone: 'success' },
      primary: { visible: false },
      cancel: 'Cancel',
    },
    mobile_handoff: {
      intro: INTRO_CLAIM,
      status: { message: 'Your lemma.id is ready on this phone.', tone: 'success' },
      primary: { visible: false },
      cancel: 'Close tab',
    },
    return_unlock: {
      intro: INTRO_VERIFY_ONCE,
      status: { message: 'Unlock wallet to finish verification…', tone: 'info' },
      primary: { text: 'Unlock & finish', visible: true },
      cancel: 'Cancel',
    },
    already_provisioned: {
      intro: INTRO_VERIFY_ONCE,
      status: { message: 'Human proof already in wallet.', tone: 'success' },
      primary: { visible: false },
      cancel: 'Cancel',
    },
    master_stored: {
      intro: INTRO_VERIFY_ONCE,
      status: { message: 'Human proof stored in wallet.', tone: 'success' },
      primary: { visible: false },
      cancel: 'Cancel',
    },
    error: {
      intro: INTRO_VERIFY_ONCE,
      status: { message: 'Verification failed — try again or contact support.', tone: 'error' },
      primary: { text: 'Try again', visible: true },
      cancel: 'Cancel',
    },
  };

  const SECTIONS = [
    {
      title: 'Primary action — verify once',
      description: 'Button label depends on wallet + master proof state.',
      scenes: [
        { id: 'verify_once', label: 'New user — Create lemma.id' },
        { id: 'unlock_lemma', label: 'Wallet locked — Unlock lemma.id' },
        { id: 'claim_lemma', label: 'Master proof, no passkey — Claim lemma.id' },
        { id: 'verify_ready', label: 'Unlocked, needs IDV — Unlock wallet & verify' },
      ],
    },
    {
      title: 'Loading',
      scenes: [
        { id: 'loading_check_wallet', label: 'Checking wallet…' },
        { id: 'loading_unlock', label: 'Unlocking lemma.id…' },
        { id: 'loading_idv', label: 'Opening identity check…' },
        { id: 'loading_finalize', label: 'Finalizing verification…' },
      ],
    },
    {
      title: 'Site proof (customer site popup)',
      scenes: [
        { id: 'site_proof', label: 'Ready — auto issue' },
        { id: 'site_proof_needs_idv', label: 'Needs IDV — Create lemma.id' },
        { id: 'site_proof_unlock', label: 'Needs IDV — Unlock lemma.id' },
        { id: 'site_proof_claim', label: 'Needs IDV — Claim lemma.id' },
        { id: 'site_proof_verify', label: 'Needs IDV — Unlock wallet & verify' },
        { id: 'site_proof_issuing', label: 'Issuing site proof…' },
        { id: 'site_proof_success', label: 'Site proof ready' },
      ],
    },
    {
      title: 'Fresh IDV (re-verify)',
      scenes: [
        { id: 'fresh_idv_blocked', label: 'Site blocked — intro' },
        { id: 'fresh_idv_revoked', label: 'Network revoked — intro' },
        { id: 'fresh_idv_success', label: 'Fresh verification complete' },
      ],
    },
    {
      title: 'Mobile & return paths',
      scenes: [
        { id: 'mobile_handoff', label: 'Mobile handoff complete' },
        { id: 'return_unlock', label: 'Return from IDV — Unlock & finish' },
        { id: 'already_provisioned', label: 'Master already in wallet' },
        { id: 'master_stored', label: 'Master stored' },
        { id: 'error', label: 'Error + Try again' },
      ],
    },
  ];

  window.LemmaIdvPreviewScenes = SCENES;
  window.LemmaIdvPreviewSections = SECTIONS;
})();
