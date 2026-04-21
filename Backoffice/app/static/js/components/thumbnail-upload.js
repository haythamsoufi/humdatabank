// Thumbnail upload component behavior (CSP-safe, no inline handlers)
// Requires: meta[name="csrf-token"], and (optionally) ActionRouter.

(function () {
  'use strict';

  function getCsrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
  }

  function getStrings(container) {
    const d = container?.dataset || {};
    return {
      generating: d.i18nGenerating || 'Generating...',
      generatingThumb: d.i18nGeneratingThumb || 'Generating thumbnail...',
      generatePdfThumb: d.i18nGeneratePdfThumb || 'Generate PDF Thumbnail',
      regenerateThumb: d.i18nRegenerateThumb || 'Regenerate Thumbnail',
      deleteConfirm: d.i18nDeleteConfirm || 'Are you sure you want to delete the thumbnail? This action cannot be undone.',
      deleting: d.i18nDeleting || 'Deleting...',
      deletingThumb: d.i18nDeletingThumb || 'Deleting thumbnail...',
      deletedSuccess: d.i18nDeletedSuccess || 'Thumbnail deleted successfully!',
      generatedSuccess: d.i18nGeneratedSuccess || 'Thumbnail generated successfully!',
      errorPrefix: d.i18nErrorPrefix || 'Error:',
      networkError: d.i18nNetworkError || 'Network error occurred',
      generatedAutomatically: d.i18nGeneratedAutomatically || 'Generated automatically',
      currentThumbnail: d.i18nCurrentThumbnail || 'Current thumbnail:',
      deleteLabel: d.i18nDeleteLabel || 'Delete',
      toReplace: d.i18nToReplace || 'To replace the current thumbnail, choose a new image below.',
    };
  }

  function getContainerFromEl(el) {
    return el.closest('.thumbnail-upload-container');
  }

  function endpointFor(entityType, entityId, action, languageCode) {
    const base =
      entityType === 'resource'
        ? `/admin/resources/${entityId}`
        : `/admin/documents/${entityId}`;
    if (action === 'generate') return `${base}/generate-thumbnail/${languageCode}`;
    if (action === 'delete') return `${base}/delete-thumbnail/${languageCode}`;
    return '';
  }

  function setStatus(statusEl, html) {
    if (!statusEl) return;
    // Parse HTML string safely using DOMParser
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');
    const fragment = document.createDocumentFragment();
    Array.from(doc.body.childNodes).forEach(node => {
      fragment.appendChild(node.cloneNode(true));
    });
    statusEl.replaceChildren();
    statusEl.appendChild(fragment);
  }

  function updateThumbnailDisplay(container, thumbnailUrl) {
    if (!container) return;
    const s = getStrings(container);
    const lang = container.dataset.languageCode || '';
    const entityId = container.dataset.entityId || '';
    const entityType = container.dataset.entityType || '';

    // Existing image?
    const existingImg = container.querySelector('img[data-thumbnail-preview="true"]');
    if (existingImg) {
      existingImg.src = `${thumbnailUrl}?t=${Date.now()}`;
      const filenameText = container.querySelector('[data-thumbnail-filename="true"]');
      if (filenameText) filenameText.textContent = s.generatedAutomatically;
      return;
    }

    // Build preview block (DOM APIs, no inline handlers)
    const previewWrapper = document.createElement('div');
    previewWrapper.className = 'mb-3';

    const header = document.createElement('div');
    header.className = 'flex justify-between items-start mb-1';

    const p = document.createElement('p');
    p.className = 'text-sm text-gray-600';
    p.textContent = s.currentThumbnail;

    const delBtn = document.createElement('button');
    delBtn.type = 'button';
    delBtn.id = `delete-thumb-btn-${lang}`;
    delBtn.className =
      'inline-flex items-center px-2 py-1 border border-red-300 shadow-sm text-xs leading-4 font-medium rounded text-red-700 bg-white hover:bg-red-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500';
    delBtn.title = 'Delete thumbnail';
    delBtn.setAttribute('data-action', 'thumbnail:delete');
    delBtn.setAttribute('data-language-code', lang);
    delBtn.setAttribute('data-entity-id', entityId);
    delBtn.setAttribute('data-entity-type', entityType);

    const delIcon = document.createElement('i');
    delIcon.className = 'fas fa-trash mr-1';
    const delText = document.createElement('span');
    delText.id = `delete-thumb-text-${lang}`;
    delText.textContent = s.deleteLabel;

    delBtn.appendChild(delIcon);
    delBtn.appendChild(delText);

    header.appendChild(p);
    header.appendChild(delBtn);

    const img = document.createElement('img');
    img.setAttribute('data-thumbnail-preview', 'true');
    img.src = `${thumbnailUrl}?t=${Date.now()}`;
    img.alt = 'Generated thumbnail';
    img.className = 'border rounded shadow-sm mb-2';
    img.style.cssText = 'max-height:4rem;max-width:5rem;object-fit:cover;';

    const filename = document.createElement('p');
    filename.className = 'text-xs text-gray-500 mt-1';
    filename.setAttribute('data-thumbnail-filename', 'true');
    filename.textContent = s.generatedAutomatically;

    const status = document.createElement('div');
    status.id = `delete-thumb-status-${lang}`;
    status.className = 'mt-2 text-sm';

    previewWrapper.appendChild(header);
    previewWrapper.appendChild(img);
    previewWrapper.appendChild(filename);
    previewWrapper.appendChild(status);

    const replaceHint = document.createElement('p');
    replaceHint.className = 'text-xs text-gray-500 mb-1';
    replaceHint.textContent = s.toReplace;

    // Insert after label
    const label = container.querySelector('label');
    if (label && label.parentNode) {
      const ref = label.nextSibling;
      label.parentNode.insertBefore(previewWrapper, ref);
      label.parentNode.insertBefore(replaceHint, ref);
    } else {
      container.insertBefore(previewWrapper, container.firstChild);
      container.insertBefore(replaceHint, previewWrapper.nextSibling);
    }
  }

  async function doGenerate(el) {
    const container = getContainerFromEl(el);
    if (!container) return;
    const s = getStrings(container);
    const entityId = el.getAttribute('data-entity-id') || container.dataset.entityId || '';
    const entityType = el.getAttribute('data-entity-type') || container.dataset.entityType || '';
    const lang = el.getAttribute('data-language-code') || container.dataset.languageCode || '';

    const btn =
      (lang ? document.getElementById(`generate-btn-${lang}`) : null) ||
      (el instanceof HTMLButtonElement ? el : el.closest('button'));
    const btnText =
      (lang ? document.getElementById(`generate-text-${lang}`) : null) ||
      container.querySelector('[data-thumbnail-btn-text="generate"]') ||
      (btn ? btn.querySelector('span') : null);
    const status =
      (lang ? document.getElementById(`generate-status-${lang}`) : null) ||
      container.querySelector('[data-thumbnail-status="generate"]');

    if (!entityId || !entityType || !lang) return;

    const endpoint = endpointFor(entityType, entityId, 'generate', lang);
    if (!endpoint) return;

    const csrf = getCsrfToken();
    if (!csrf) return;

    if (btn) btn.disabled = true;
    if (btnText) btnText.textContent = s.generating;
    if (btn) btn.classList.add('opacity-50', 'cursor-not-allowed');
    setStatus(
      status,
      `<i class="fas fa-spinner fa-spin text-blue-500"></i> <span class="text-blue-600">${s.generatingThumb}</span>`
    );

    try {
      const fn = (window.getFetch && window.getFetch()) || fetch;
      const resp = await fn(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
          'X-CSRFToken': csrf,
        },
      });
      if (!resp.ok) {
        let detail = `HTTP ${resp.status}`;
        try {
          const errData = await resp.json();
          if (errData && typeof errData.error === 'string' && errData.error.trim()) {
            detail = errData.error.trim();
          } else if (errData && typeof errData.message === 'string' && errData.message.trim()) {
            detail = errData.message.trim();
          }
        } catch (_) {
          /* ignore */
        }
        setStatus(
          status,
          `<i class="fas fa-exclamation-triangle text-red-500"></i> <span class="text-red-600">${s.errorPrefix} ${escapeHtml(
            detail
          )}</span>`
        );
        return;
      }
      const data = await resp.json();
      if (data?.success) {
        setStatus(
          status,
          `<i class="fas fa-check-circle text-green-500"></i> <span class="text-green-600">${s.generatedSuccess}</span>`
        );
        if (data.thumbnail_url) updateThumbnailDisplay(container, data.thumbnail_url);
        if (btnText) {
          setTimeout(() => {
            btnText.textContent = s.regenerateThumb;
          }, 3000);
        }
      } else {
        const msg = data?.message ? String(data.message) : '';
        setStatus(
          status,
          `<i class="fas fa-exclamation-triangle text-red-500"></i> <span class="text-red-600">${s.errorPrefix} ${escapeHtml(
            msg
          )}</span>`
        );
      }
    } catch (err) {
      console.error('Error generating thumbnail:', err);
      setStatus(
        status,
        `<i class="fas fa-exclamation-triangle text-red-500"></i> <span class="text-red-600">${s.networkError}</span>`
      );
    } finally {
      if (btn) btn.disabled = false;
      if (btn) btn.classList.remove('opacity-50', 'cursor-not-allowed');
      if (btnText && btnText.textContent === s.generating) {
        btnText.textContent = s.generatePdfThumb;
      }
    }
  }

  async function doDelete(el) {
    const container = getContainerFromEl(el);
    if (!container) return;
    const s = getStrings(container);
    const entityId = el.getAttribute('data-entity-id') || container.dataset.entityId || '';
    const entityType = el.getAttribute('data-entity-type') || container.dataset.entityType || '';
    const lang = el.getAttribute('data-language-code') || container.dataset.languageCode || '';

    const btn =
      (lang ? document.getElementById(`delete-thumb-btn-${lang}`) : null) ||
      (el instanceof HTMLButtonElement ? el : el.closest('button'));
    const btnText =
      (lang ? document.getElementById(`delete-thumb-text-${lang}`) : null) ||
      container.querySelector('[data-thumbnail-btn-text="delete"]') ||
      (btn ? btn.querySelector('span') : null);
    const status =
      (lang ? document.getElementById(`delete-thumb-status-${lang}`) : null) ||
      container.querySelector('[data-thumbnail-status="delete"]');

    if (!entityId || !entityType || !lang) return;

    // Avoid native confirm; use global styled dialogs.
    const proceed = async () => {
      const endpoint = endpointFor(entityType, entityId, 'delete', lang);
      if (!endpoint) return;

      const csrf = getCsrfToken();
      if (!csrf) return;

      if (btn) btn.disabled = true;
      if (btnText) btnText.textContent = s.deleting;
      if (btn) btn.classList.add('opacity-50', 'cursor-not-allowed');
      setStatus(
        status,
        `<i class="fas fa-spinner fa-spin text-blue-500"></i> <span class="text-blue-600">${s.deletingThumb}</span>`
      );

      try {
        const fn = (window.getFetch && window.getFetch()) || fetch;
        const resp = await fn(endpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
            'X-CSRFToken': csrf,
          },
        });
        if (!resp.ok) throw (window.httpErrorSync && window.httpErrorSync(resp)) || new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        if (data?.success) {
          setStatus(
            status,
            `<i class="fas fa-check-circle text-green-500"></i> <span class="text-green-600">${s.deletedSuccess}</span>`
          );
          // Remove preview block (documents modal: .mb-3 wrapper; fallback: img directly)
          const imgEl = container ? container.querySelector('[data-thumbnail-preview="true"]') : null;
          const preview =
            (btn && btn.closest('.mb-3')) ||
            (imgEl && imgEl.closest('.mb-3')) ||
            null;
          if (preview) {
            preview.remove();
          } else if (imgEl) {
            imgEl.remove();
          }
        } else {
          const msg = data?.message ? String(data.message) : '';
          setStatus(
            status,
            `<i class="fas fa-exclamation-triangle text-red-500"></i> <span class="text-red-600">${s.errorPrefix} ${escapeHtml(
              msg
            )}</span>`
          );
        }
      } catch (err) {
        console.error('Error deleting thumbnail:', err);
        setStatus(
          status,
          `<i class="fas fa-exclamation-triangle text-red-500"></i> <span class="text-red-600">${s.networkError}</span>`
        );
      } finally {
        if (btn && btn.parentNode) {
          btn.disabled = false;
          btn.classList.remove('opacity-50', 'cursor-not-allowed');
        }
        if (btnText && btnText.textContent === s.deleting) {
          btnText.textContent = s.deleteLabel;
        }
      }
    };

    const confirmText = s.deleteLabel || 'Delete';
    const cancelText = s.cancelLabel || 'Cancel';

    if (window.showDangerConfirmation) {
      window.showDangerConfirmation(s.deleteConfirm, () => { void proceed(); }, null, confirmText, cancelText, 'Confirm Delete');
      return;
    }
    if (window.showConfirmation) {
      window.showConfirmation(s.deleteConfirm, () => { void proceed(); }, null, confirmText, cancelText, 'Confirm Delete');
      return;
    }

    console.warn('Custom confirmation dialog not available:', s.deleteConfirm);
    return;
  }

  // Minimal HTML escaping for error messages we display via innerHTML
  function escapeHtml(value) {
    const div = document.createElement('div');
    div.textContent = value == null ? '' : String(value);
    return div.innerHTML;
  }

  function register() {
    if (!window.ActionRouter) return;
    if (window.__ThumbnailUploadActionsRegistered === true) return;
    window.__ThumbnailUploadActionsRegistered = true;

    window.ActionRouter.register('thumbnail:generate', (el, e) => {
      e?.preventDefault?.();
      doGenerate(el);
    });
    window.ActionRouter.register('thumbnail:delete', (el, e) => {
      e?.preventDefault?.();
      doDelete(el);
    });
  }

  // Register after load; ActionRouter is loaded globally for backoffice pages.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', register);
  } else {
    register();
  }
})();
