/**
 * Shared plain-language translations for the lemma.id demo surfaces.
 * Loaded from the hub origin; consumed by the demo hub and relying-site demos.
 */
(function () {
  'use strict';

  var REASON = {
    valid: 'Verified on this device.',
    session_valid: "You're signed in.",
    vc_valid: 'Credential verified.',
    ok: 'Success.',
    site_proof_required: "This site wants proof it's really you before letting you in.",
    idv_cancelled: 'Identity check was cancelled. Nothing was shared.',
    popup_closed: 'Sign-in window closed before finishing.',
    doubt_required: 'This site wants a fresh check that it is still you.',
    site_ppid_revoked: 'This site has banned this account.',
    site_ppid_blocked: 'This site has banned this account.',
    site_blocked: 'This site has banned this account.',
    site_block: 'This site has banned this account.',
    revoked: 'This account is no longer valid on this site.',
    assurance_insufficient: 'This action needs stronger proof than a passkey alone.',
    not_ishuman: 'This action requires verified human proof.',
    no_credential: 'No lemma.id found on this device yet.',
    wallet_locked: 'Unlock your lemma.id with your passkey to continue.',
    expired: 'Your session expired. Sign in again.',
    untrusted_issuer: 'This site does not trust the credential issuer.',
    allocation_already_claimed: "You already got your code. It's one per person.",
    trial_already_used: 'You already activated your free workspace. Free trials are one per person.',
    registration_required: 'Sign up for the drop first.',
    action_nonce_reused: 'Blocked: someone tried to reuse an old approval.',
    rate_limited: 'Too many attempts. Wait a moment and try again.',
    fresh_passkey_missing: 'Unlock with Face ID, Touch ID, or Windows Hello to claim your code.',
    fresh_passkey_expired: 'Your passkey check timed out. Try again.',
    fresh_passkey_too_old: 'Your passkey check timed out. Try again.',
    fresh_passkey_invalid_signature: 'Passkey check failed. Try again.',
    fresh_passkey_signature_missing: 'Passkey check failed. Try again.',
    fresh_passkey_server_nonce_missing: 'Server security check failed. Refresh and try again.',
    passkey_not_registered_on_server: 'Set up your lemma.id passkey first, then try again.',
    passkey_server_binding_failed: 'Passkey setup incomplete. Unlock your lemma.id and try again.',
    fresh_passkey_webauthn_invalid: 'Passkey check failed. Unlock your lemma.id and try again.',
    redirect_started: 'Continuing on lemma.id. You will return here automatically.',
    session_bloom_sequence_mismatch: 'Session sync hiccup. Try once more.',
    verify_error: 'Verification failed. Try again.',
    drop_id_missing: 'Drop not found.',
    ppid_missing: 'Sign in first so this site knows who you are.',
    unknown: 'Something went wrong. Try again.',
  };

  var ASSURANCE = {
    passkey: 'Signed in with a passkey.',
    ishuman: 'Verified human. One account per person.',
  };

  var FIELD_LABELS = {
    ppid: 'What this site sees',
    assurance: 'Proof level',
    reason: 'Status',
    latency: 'Speed',
  };

  var SITE_STATUS = {
    pending: 'Not signed in yet',
    banned: 'Banned on this site',
    humanity_doubted: 'This site wants fresh human proof',
    fresh_presence: 'This site wants you to confirm it is still you',
    verified_passkey: 'Signed in',
    verified_ishuman: 'Verified human',
    verified: 'Signed in',
    doubt: 'Fresh check required',
    insufficient: 'Needs stronger proof',
    not_verified: 'Not signed in yet',
  };

  function reason(code) {
    var key = String(code || '').trim();
    if (!key) return '-';
    if (REASON[key]) return REASON[key];
    if (key.indexOf('fresh_passkey_') === 0) {
      return 'Passkey check failed. Try again.';
    }
    return key.replace(/_/g, ' ');
  }

  function assurance(tier) {
    var key = String(tier || '').trim().toLowerCase();
    if (!key) return '-';
    return ASSURANCE[key] || ('Proof level: ' + key);
  }

  function fieldLabel(key) {
    return FIELD_LABELS[key] || key;
  }

  function siteStatus(result, opts) {
    opts = opts || {};
    if (!result) return SITE_STATUS.pending;
    if (opts.banned) return SITE_STATUS.banned;
    if (opts.humanityDoubted) return SITE_STATUS.humanity_doubted;
    if (opts.doubted) return SITE_STATUS.fresh_presence;
    if (result.human || opts.verified) {
      if (result.assurance === 'passkey') return SITE_STATUS.verified_passkey;
      if (result.assurance === 'ishuman') return SITE_STATUS.verified_ishuman;
      return SITE_STATUS.verified;
    }
    if (result.reason === 'doubt_required') return SITE_STATUS.doubt;
    if (result.reason === 'assurance_insufficient' || result.reason === 'not_ishuman') {
      return SITE_STATUS.insufficient;
    }
    return SITE_STATUS.not_verified;
  }

  function blockResult(opts) {
    opts = opts || {};
    if (!opts.ppid) return { text: 'Not signed in yet', className: '' };
    if (opts.banned) return { text: 'Banned on this site', className: 'result-deny' };
    if (opts.doubted) return { text: 'Under review', className: 'result-warn' };
    if (opts.verified) return { text: 'Signed in', className: 'result-ok' };
    if (opts.insufficient) return { text: 'Needs stronger proof', className: 'result-warn' };
    return { text: 'Not signed in yet', className: 'result-warn' };
  }

  window.LemmaDemoPlain = {
    reason: reason,
    assurance: assurance,
    fieldLabel: fieldLabel,
    siteStatus: siteStatus,
    blockResult: blockResult,
    REASON: REASON,
    ASSURANCE: ASSURANCE,
    FIELD_LABELS: FIELD_LABELS,
  };
})();
