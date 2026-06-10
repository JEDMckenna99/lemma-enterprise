(function () {
  'use strict';

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

  function appendSceneRow(grid, scene, options) {
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

  function initIdvPreviewPanel(options = {}) {
    const root = $(options.rootId || 'ishuman-idv-viewer-root');
    const grid = $('ih-idv-preview-grid');
    if (!grid) return;
    if (root && root.dataset.uiPreviewEnabled !== 'true') return;

    const sections = window.LemmaIdvPreviewSections || [];
    grid.innerHTML = '';

    for (const section of sections) {
      const block = document.createElement('div');
      block.className = 'idv-preview-section';

      const heading = document.createElement('h3');
      heading.className = 'idv-preview-section-title';
      heading.textContent = section.title;
      block.appendChild(heading);

      if (section.description) {
        const desc = document.createElement('p');
        desc.className = 'demo-muted idv-preview-section-desc';
        desc.textContent = section.description;
        block.appendChild(desc);
      }

      const sectionGrid = document.createElement('div');
      sectionGrid.className = 'idv-preview-grid';
      for (const scene of section.scenes) {
        appendSceneRow(sectionGrid, scene, options);
      }
      block.appendChild(sectionGrid);
      grid.appendChild(block);
    }
  }

  function bootViewerPanel() {
    const grid = $('ih-idv-preview-grid');
    if (!grid) return;
    const root = $('ishuman-idv-viewer-root') || $('ishuman-demo');
    if (root && root.dataset.uiPreviewEnabled !== 'true') return;
    initIdvPreviewPanel({ rootId: root ? root.id : 'ishuman-idv-viewer-root' });
  }

  window.LemmaIdvViewer = {
    get scenes() {
      return window.LemmaIdvPreviewScenes || {};
    },
    get sections() {
      return window.LemmaIdvPreviewSections || [];
    },
    buildIdvPreviewUrl,
    openIdvPreview,
    initIdvPreviewPanel,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootViewerPanel);
  } else {
    bootViewerPanel();
  }
})();
