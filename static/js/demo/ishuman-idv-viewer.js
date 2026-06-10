(function () {
  'use strict';

  const IDV_PREVIEW_SCENES = [
    { id: 'verify_once', label: 'Verify once — Create lemma.id' },
    { id: 'unlock_lemma', label: 'Wallet locked — Unlock lemma.id' },
    { id: 'claim_lemma', label: 'Master proof, no passkey — Claim lemma.id' },
    { id: 'loading_unlock', label: 'Unlocking wallet…' },
    { id: 'loading_idv', label: 'Opening identity check…' },
    { id: 'loading_finalize', label: 'Finalizing verification…' },
    { id: 'site_proof', label: 'Site proof — ready' },
    { id: 'site_proof_issuing', label: 'Site proof — issuing' },
    { id: 'site_proof_success', label: 'Site proof — success' },
    { id: 'fresh_idv_blocked', label: 'Fresh IDV — site blocked' },
    { id: 'fresh_idv_revoked', label: 'Fresh IDV — revoked' },
    { id: 'fresh_idv_success', label: 'Fresh IDV — success' },
    { id: 'mobile_handoff', label: 'Mobile handoff — complete' },
    { id: 'return_unlock', label: 'Return from IDV — unlock & finish' },
    { id: 'already_provisioned', label: 'Master already in wallet' },
    { id: 'master_stored', label: 'Master stored' },
    { id: 'error', label: 'Error state' },
  ];

  function $(id) {
    return document.getElementById(id);
  }

  function buildIdvPreviewUrl(sceneId, { redirect = false } = {}) {
    const siteSelect = $('ih-idv-preview-site');
    const siteId = (siteSelect && siteSelect.value) || 'tickets-demo.lemma.id';
    const url = new URL(`${window.location.origin}/wallet/ishuman-idv`);
    url.searchParams.set('ui_preview', sceneId);
    url.searchParams.set('origin', window.location.origin);
    url.searchParams.set('site_id', siteId);
    if (siteId !== 'lemma.id') {
      url.searchParams.set('issue_mode', 'site_proof');
      url.searchParams.set('session_nonce', 'preview_session');
      url.searchParams.set('request_nonce', 'preview_request');
      url.searchParams.set('bloom_sequence', '1');
      url.searchParams.set('session_ttl_sec', String(24 * 60 * 60));
    }
    if (redirect) {
      url.searchParams.set('flow_mode', 'redirect');
      url.searchParams.set('redirect_return', window.location.href);
    }
    return url;
  }

  function openIdvPreview(sceneId, { redirect = false, onOpen = null } = {}) {
    const url = buildIdvPreviewUrl(sceneId, { redirect });
    if (redirect) {
      window.location.assign(url.toString());
      return;
    }
    const width = 480;
    const height = 660;
    const left = Math.max(0, Math.round(window.screenX + (window.outerWidth - width) / 2));
    const top = Math.max(0, Math.round(window.screenY + (window.outerHeight - height) / 2));
    const popup = window.open(
      url.toString(),
      `lemma_ishuman_idv_preview_${sceneId}`,
      `popup=yes,width=${width},height=${height},left=${left},top=${top}`,
    );
    if (!popup) {
      if (typeof onOpen === 'function') onOpen('blocked', sceneId);
      return;
    }
    if (typeof onOpen === 'function') onOpen('popup', sceneId);
  }

  function initIdvPreviewPanel(options = {}) {
    const root = $(options.rootId || 'ishuman-idv-viewer-root');
    const grid = $('ih-idv-preview-grid');
    if (!grid) return;
    if (root && root.dataset.uiPreviewEnabled !== 'true') return;

    grid.innerHTML = '';
    for (const scene of IDV_PREVIEW_SCENES) {
      const row = document.createElement('div');
      row.className = 'idv-preview-row';

      const label = document.createElement('span');
      label.className = 'idv-preview-label';
      label.textContent = scene.label;

      const popupBtn = document.createElement('button');
      popupBtn.type = 'button';
      popupBtn.className = 'demo-btn demo-btn-secondary';
      popupBtn.textContent = 'Popup';
      popupBtn.addEventListener('click', () => {
        openIdvPreview(scene.id, { redirect: false, onOpen: options.onOpen });
      });

      const redirectBtn = document.createElement('button');
      redirectBtn.type = 'button';
      redirectBtn.className = 'demo-btn demo-btn-secondary';
      redirectBtn.textContent = 'Redirect';
      redirectBtn.addEventListener('click', () => {
        openIdvPreview(scene.id, { redirect: true, onOpen: options.onOpen });
      });

      row.appendChild(label);
      row.appendChild(popupBtn);
      row.appendChild(redirectBtn);
      grid.appendChild(row);
    }
  }

  window.LemmaIdvViewer = {
    IDV_PREVIEW_SCENES,
    buildIdvPreviewUrl,
    openIdvPreview,
    initIdvPreviewPanel,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => initIdvPreviewPanel());
  } else {
    initIdvPreviewPanel();
  }
})();
