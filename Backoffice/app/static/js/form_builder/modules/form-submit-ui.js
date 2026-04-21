// form-submit-ui.js
// - Global "saving" banner for the Form Builder
// - AJAX submit + partial DOM refresh to avoid full page reloads

export const FormSubmitUI = {
  init() {
    if (this._initialized) return;
    this._initialized = true;

    // Banner elements (lazy resolved)
    this._banner = null;
    this._bannerText = null;
    this._bannerDetail = null;
    this._bannerSpinner = null;
    this._bannerPercent = null;
    this._bannerBar = null;
    this._bannerRetry = null;
    this._bannerClose = null;
    this._bannerUI = null;
    this._lastRetry = null;
    // Concurrency guards
    // - Per-form in-flight controller + request id
    // - Only the latest request for a form may update the DOM / banner
    this._inflightByForm = this._inflightByForm || new WeakMap();
    this._reqSeq = this._reqSeq || 0;

    const ensureBanner = () => {
      if (this._banner) return true;
      const el = document.getElementById('form-builder-save-banner');
      if (!el) return false;
      this._banner = el;
      this._bannerText = document.getElementById('form-builder-save-banner-text');
      this._bannerDetail = document.getElementById('form-builder-save-banner-detail');
      this._bannerSpinner = document.getElementById('form-builder-save-banner-spinner');
      this._bannerPercent = document.getElementById('form-builder-save-banner-percent');
      this._bannerBar = document.getElementById('form-builder-save-banner-bar');
      this._bannerRetry = document.getElementById('form-builder-save-banner-retry');
      this._bannerClose = document.getElementById('form-builder-save-banner-close');
      // Shared banner controller (provided by /static/js/floating-progress-banner.js)
      try {
        if (window.FloatingProgressBanner && typeof window.FloatingProgressBanner.fromIds === 'function') {
          this._bannerUI = window.FloatingProgressBanner.fromIds({
            bannerId: 'form-builder-save-banner',
            titleId: 'form-builder-save-banner-text',
            detailId: 'form-builder-save-banner-detail',
            percentId: 'form-builder-save-banner-percent',
            barId: 'form-builder-save-banner-bar',
            spinnerId: 'form-builder-save-banner-spinner',
            buttons: [{ id: 'form-builder-save-banner-retry' }, { id: 'form-builder-save-banner-close' }],
          });
        }
      } catch (_e) {
        this._bannerUI = null;
      }

      if (this._bannerRetry) {
        this._bannerRetry.addEventListener('click', () => {
          if (typeof this._lastRetry === 'function') {
            try { this._lastRetry(); } catch (e) { console.error('[FormBuilderAjax] retry failed', e); }
          }
        });
      }
      if (this._bannerClose) {
        this._bannerClose.addEventListener('click', () => {
          this.hideBanner();
        });
      }
      return true;
    };

    this.showSaving = (text = 'Saving…', detail = '') => {
      if (!ensureBanner()) return;
      if (this._bannerUI && this._bannerUI.update) {
        this._bannerUI.show();
        this._bannerUI.setSpinnerVisible(true);
        this._bannerUI.setButtonVisible('form-builder-save-banner-retry', false);
        this._bannerUI.setTitle(text);
        this._bannerUI.setDetail(detail, { autoHideIfEmpty: true });
        this._bannerUI.setPercent(0, { visible: false });
        this._bannerUI.setBar('35%', { barColor: 'rgba(255,255,255,0.95)' });
      } else {
        this._banner.classList.remove('hidden');
        if (this._bannerSpinner) this._bannerSpinner.classList.remove('hidden');
        if (this._bannerRetry) this._bannerRetry.classList.add('hidden');
        if (this._bannerText) this._bannerText.textContent = text;
        if (this._bannerDetail) {
          const has = !!(detail && String(detail).trim());
          this._bannerDetail.textContent = has ? String(detail) : '';
          this._bannerDetail.classList.toggle('hidden', !has);
        }
        if (this._bannerPercent) this._bannerPercent.classList.add('hidden');
        if (this._bannerBar) {
          this._bannerBar.style.background = 'rgba(255,255,255,0.95)';
          // Indeterminate-ish: jump to a partial width while saving.
          this._bannerBar.style.width = '35%';
        }
      }
      clearTimeout(this._bannerHideTimer);
    };

    this.showSuccess = (text = 'Saved', detail = '') => {
      if (!ensureBanner()) return;
      if (this._bannerUI && this._bannerUI.update) {
        this._bannerUI.show();
        this._bannerUI.setSpinnerVisible(false);
        this._bannerUI.setButtonVisible('form-builder-save-banner-retry', false);
        this._bannerUI.setTitle(text);
        this._bannerUI.setDetail(detail, { autoHideIfEmpty: true });
        this._bannerUI.setPercent(100, { visible: false });
        this._bannerUI.setBar('100%', { barColor: 'rgba(255,255,255,0.95)' });
      } else {
        this._banner.classList.remove('hidden');
        if (this._bannerSpinner) this._bannerSpinner.classList.add('hidden');
        if (this._bannerRetry) this._bannerRetry.classList.add('hidden');
        if (this._bannerText) this._bannerText.textContent = text;
        if (this._bannerDetail) {
          const has = !!(detail && String(detail).trim());
          this._bannerDetail.textContent = has ? String(detail) : '';
          this._bannerDetail.classList.toggle('hidden', !has);
        }
        if (this._bannerPercent) this._bannerPercent.classList.add('hidden');
        if (this._bannerBar) {
          this._bannerBar.style.background = 'rgba(255,255,255,0.95)';
          this._bannerBar.style.width = '100%';
        }
      }
      // Auto-hide success quickly (keeps UI clean)
      clearTimeout(this._bannerHideTimer);
      this._bannerHideTimer = setTimeout(() => this.hideBanner(), 1800);
    };

    this.showError = (text = 'Save failed', detail = '', retryFn = null) => {
      if (!ensureBanner()) return;
      this._lastRetry = typeof retryFn === 'function' ? retryFn : null;
      if (this._bannerUI && this._bannerUI.update) {
        this._bannerUI.show();
        this._bannerUI.setSpinnerVisible(false);
        this._bannerUI.setTitle(text);
        this._bannerUI.setDetail(detail, { autoHideIfEmpty: true });
        this._bannerUI.setButtonVisible('form-builder-save-banner-retry', !!this._lastRetry);
        this._bannerUI.setPercent(100, { visible: false });
        this._bannerUI.setBar('100%', { barColor: 'rgba(255,120,120,0.95)' });
      } else {
        this._banner.classList.remove('hidden');
        if (this._bannerSpinner) this._bannerSpinner.classList.add('hidden');
        if (this._bannerText) this._bannerText.textContent = text;
        if (this._bannerDetail) {
          const has = !!(detail && String(detail).trim());
          this._bannerDetail.textContent = has ? String(detail) : '';
          this._bannerDetail.classList.toggle('hidden', !has);
        }
        if (this._bannerRetry) {
          this._bannerRetry.classList.toggle('hidden', !this._lastRetry);
        }
        if (this._bannerPercent) this._bannerPercent.classList.add('hidden');
        if (this._bannerBar) {
          this._bannerBar.style.background = 'rgba(255,120,120,0.95)';
          this._bannerBar.style.width = '100%';
        }
      }
      clearTimeout(this._bannerHideTimer);
    };

    this.hideBanner = () => {
      if (!ensureBanner()) return;
      if (this._bannerUI && this._bannerUI.hide) {
        this._bannerUI.hide();
        this._bannerUI.setButtonVisible('form-builder-save-banner-retry', false);
        this._bannerUI.setSpinnerVisible(false);
        this._bannerUI.setPercent(0, { visible: false });
        this._bannerUI.setBar('0%', { barColor: 'rgba(255,255,255,0.95)' });
      } else {
        this._banner.classList.add('hidden');
        if (this._bannerRetry) this._bannerRetry.classList.add('hidden');
        if (this._bannerSpinner) this._bannerSpinner.classList.add('hidden');
        if (this._bannerPercent) this._bannerPercent.classList.add('hidden');
        if (this._bannerBar) {
          this._bannerBar.style.width = '0%';
          this._bannerBar.style.background = 'rgba(255,255,255,0.95)';
        }
      }
      this._lastRetry = null;
    };

    const shouldAjaxifyForm = (form) => {
      if (!form || !(form instanceof HTMLFormElement)) return false;
      if (!form.closest('#form-builder-ui')) return false;
      if ((form.dataset && form.dataset.fbNoAjax === '1') || form.classList.contains('fb-no-ajax')) return false;
      const method = (form.getAttribute('method') || 'GET').toUpperCase();
      if (method !== 'POST') return false;
      const action = (form.getAttribute('action') || '').trim();
      // If action is empty, it submits to current page; still OK in builder context.
      // Avoid hijacking forms that explicitly target another browsing context.
      if (form.getAttribute('target') && form.getAttribute('target') !== '_self') return false;
      // Avoid download-y forms if any (hard to detect perfectly; allow explicit opt-out)
      if (action.includes('export') || action.includes('download')) return false;
      return true;
    };

    const refreshFromHtml = (htmlText) => {
      if (!htmlText || typeof htmlText !== 'string') return;
      const doc = new DOMParser().parseFromString(htmlText, 'text/html');
      if (!doc) return;

      const idsToReplace = [
        // Main builder list
        'sections-container',
        // Template details + pages editor
        'template-details-display',
        'edit-template-details-form-container',
        'manage-pages-fields-container',
        'pages-list-container',
        // Data blobs consumed by JS
        'csrf-token-data',
        'indicator-bank-choices-data',
        'disaggregation-choices-data',
        'all-template-items-data',
        'sections-with-items-data',
        'question-type-choices-data',
        'all-template-sections-data',
        'all-template-pages-data',
        'indicator-fields-config-data',
        'custom-field-types-data'
      ];

      idsToReplace.forEach((id) => {
        const nextEl = doc.getElementById(id);
        const curEl = document.getElementById(id);
        if (!nextEl || !curEl) return;
        curEl.replaceWith(nextEl);
      });

      try {
        document.dispatchEvent(new CustomEvent('formBuilder:domUpdated'));
      } catch (_e) {}

      // Keep data manager in sync with updated JSON blobs.
      try {
        if (window.DataManager && typeof window.DataManager.init === 'function') {
          window.DataManager.init();
        }
      } catch (e) {
        console.warn('[FormBuilderAjax] DataManager re-init failed', e);
      }

      // Recompute human-readable rule summaries (relevance/validation) in the refreshed DOM.
      // Without this, rule display placeholders like "Loading..." can stick after AJAX swaps.
      try {
        if (typeof window.initializeRuleDisplays === 'function') {
          window.initializeRuleDisplays();
        }
      } catch (e) {
        console.warn('[FormBuilderAjax] initializeRuleDisplays failed', e);
      }

      // Re-initialise dynamic sections (idempotent; will wire new forms).
      try {
        if (window.DynamicSections && typeof window.DynamicSections.init === 'function') {
          window.DynamicSections.init();
        }
      } catch (e) {
        console.warn('[FormBuilderAjax] DynamicSections re-init failed', e);
      }

      // Re-bind any UI handlers that are element-attached (toggles, etc.)
      try {
        if (window.FormBuilderEnhance && typeof window.FormBuilderEnhance.enhance === 'function') {
          window.FormBuilderEnhance.enhance();
        }
      } catch (e) {
        console.warn('[FormBuilderAjax] enhance failed', e);
      }
    };

    const submitViaAjax = async (form) => {
      const action = (form.getAttribute('action') || window.location.href).trim() || window.location.href;
      const method = (form.getAttribute('method') || 'POST').toUpperCase();
      // Allow modules to serialize UI state into hidden inputs before we snapshot FormData.
      // This removes reliance on event-listener registration order.
      try {
        document.dispatchEvent(new CustomEvent('formBuilder:beforeAjaxSubmit', { detail: { form } }));
      } catch (_e) {}

      // Safety net: if a UI section is hidden, disable its non-hidden controls so they don't submit.
      // We restore immediately after snapshotting FormData.
      const tempDisabled = [];
      try {
        const isActuallyHidden = (el) => {
          if (!el) return true;
          try {
            if (el.closest && el.closest('.hidden')) return true;
            if (el.offsetParent === null) return true;
            const style = window.getComputedStyle(el);
            return style.display === 'none' || style.visibility === 'hidden';
          } catch (_e) {
            return false;
          }
        };
        form.querySelectorAll('input, select, textarea, button').forEach((el) => {
          if (!el) return;
          if (el.tagName.toLowerCase() === 'input' && el.type === 'hidden') return;
          if (el.type === 'submit') return;
          if (el.disabled) return;
          if (!isActuallyHidden(el)) return;
          el.disabled = true;
          try { el.dataset.fbTempDisabled = '1'; } catch (_e) {}
          tempDisabled.push(el);
        });
      } catch (_e) {}

      // Abort any previous in-flight request for this form.
      try {
        const prev = this._inflightByForm.get(form);
        if (prev && prev.controller) {
          try { prev.controller.abort(); } catch (_e) {}
        }
      } catch (_e) {}

      // New request id for this submit attempt
      const reqId = ++this._reqSeq;
      const controller = (typeof AbortController !== 'undefined') ? new AbortController() : null;
      try {
        this._inflightByForm.set(form, { reqId, controller });
      } catch (_e) {}

      const fd = new FormData(form);
      // Restore any controls we temporarily disabled for snapshot correctness.
      try {
        tempDisabled.forEach((el) => {
          try {
            if (el && el.dataset && el.dataset.fbTempDisabled === '1') {
              el.disabled = false;
              delete el.dataset.fbTempDisabled;
            }
          } catch (_e) {}
        });
      } catch (_e) {}
      const isItemModalForm = !!(form && form.id === 'item-modal-form');

      // For retry: snapshot entries (FormData is iterable, but cloning is safer)
      const snapshot = Array.from(fd.entries());

      const closeContainingModal = () => {
        try {
          // Our modals use a full-screen overlay container with fixed/inset-0.
          const modal = form && form.closest ? form.closest('.fixed.inset-0') : null;
          if (modal && modal.classList && !modal.classList.contains('hidden')) {
            modal.classList.add('hidden');
          }
        } catch (_e) {}
        // IMPORTANT:
        // Do NOT fully teardown/reset the ItemModal before the server confirms success.
        // If the save fails, we want to preserve the user's edits so they can retry/fix validation.
      };

      const doSubmit = async () => {
        // If a newer request replaced this one, stop early.
        try {
          const cur = this._inflightByForm.get(form);
          if (cur && cur.reqId !== reqId) return;
        } catch (_e) {}

        // Close any edit modal immediately so the user can see changes behind the banner.
        closeContainingModal();
        this.showSaving('Saving…');
        const fetchFn = (window.getFetch && window.getFetch()) || fetch;
        const jsonBody = window.snapshotToJson ? JSON.stringify(window.snapshotToJson(snapshot)) : null;
        const resp = await fetchFn(action, {
          method,
          body: jsonBody || (() => {
            const f = new FormData();
            snapshot.forEach(([k, v]) => f.append(k, v));
            return f;
          })(),
          credentials: 'same-origin',
          headers: jsonBody
            ? { 'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/json' }
            : { 'X-Requested-With': 'XMLHttpRequest' },
          signal: controller ? controller.signal : undefined
        });

        const ct = (resp.headers.get('content-type') || '').toLowerCase();

        // If server returns JSON, respect it (used by some endpoints).
        if (ct.includes('application/json')) {
          const data = await resp.json().catch(() => null);
          if (!resp.ok || !data || data.success !== true) {
            const msg = (data && (data.error || data.message)) ? (data.error || data.message) : `HTTP ${resp.status}`;
            const err = new Error(msg);
            // Attach server payload for validation UX
            err.__fbData = data;
            err.__fbStatus = resp.status;
            throw err;
          }
          // Some endpoints return JSON + a redirect_url or html payload for DOM refresh.
          try {
            if (data && typeof data.html === 'string' && data.html.trim()) {
              // Only latest request may mutate DOM
              const cur = this._inflightByForm.get(form);
              if (cur && cur.reqId !== reqId) return;
              refreshFromHtml(data.html);
            } else if (data && typeof data.redirect_url === 'string' && data.redirect_url.trim()) {
              const url = data.redirect_url.trim();
              const r2 = await ((window.getFetch && window.getFetch()) || fetch)(url, {
                method: 'GET',
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                signal: controller ? controller.signal : undefined
              });
              const t2 = await r2.text();
              if (!r2.ok) throw (window.httpErrorSync && window.httpErrorSync(r2)) || new Error(`HTTP ${r2.status}`);
              // Keep URL in sync
              try { window.history.replaceState({}, document.title, url); } catch (_e) {}
              const cur = this._inflightByForm.get(form);
              if (cur && cur.reqId !== reqId) return;
              refreshFromHtml(t2);
            }
          } catch (e) {
            // If refresh fails, surface as error (avoid "Saved" with stale UI).
            throw e;
          }
          // Only latest request should show success
          try {
            const cur = this._inflightByForm.get(form);
            if (cur && cur.reqId !== reqId) return;
          } catch (_e) {}
          this.showSuccess(data.message || 'Saved');
          if (form && form.id === 'template-details-form') {
            try {
              if (typeof window.exitTemplateDetailsEditMode === 'function') {
                window.exitTemplateDetailsEditMode();
              }
            } catch (e) {
              console.warn('[FormBuilderAjax] exitTemplateDetailsEditMode failed', e);
            }
          }
          return;
        }

        const text = await resp.text();
        if (!resp.ok) {
          throw (window.httpErrorSync && window.httpErrorSync(resp)) || new Error(`HTTP ${resp.status}`);
        }

        // If the server followed a redirect to a new version_id, keep URL in sync.
        try {
          if (resp.url && typeof resp.url === 'string' && resp.url.includes('version_id=')) {
            window.history.replaceState({}, document.title, resp.url);
          }
        } catch (_e) {}

        // Only latest request may mutate DOM
        try {
          const cur = this._inflightByForm.get(form);
          if (cur && cur.reqId !== reqId) return;
        } catch (_e) {}
        refreshFromHtml(text);
        this.showSuccess('Saved');

        // Template details form: exit edit mode (hide Save/Cancel, show Edit Details) since we don't reload
        if (form && form.id === 'template-details-form') {
          try {
            if (typeof window.exitTemplateDetailsEditMode === 'function') {
              window.exitTemplateDetailsEditMode();
            }
          } catch (e) {
            console.warn('[FormBuilderAjax] exitTemplateDetailsEditMode failed', e);
          }
        }

        // For the item modal, now that the save succeeded and the DOM has been refreshed,
        // it's safe to teardown/reset the modal state to avoid leakage into the next edit.
        if (isItemModalForm) {
          try {
            if (window.ItemModal && typeof window.ItemModal.closeModal === 'function') {
              window.ItemModal.closeModal();
            }
          } catch (_e) {}
        }
      };

      const retryFn = () => {
        // Retry should become a new request (abort old + new reqId) by re-submitting the form.
        submitViaAjax(form).catch((err) => {
          // Error banner handled by inner call
        });
      };

      try {
        await doSubmit();
      } catch (err) {
        // If aborted due to a newer submit, don't show an error.
        if (err && (err.name === 'AbortError' || String(err.message || '').toLowerCase().includes('aborted'))) {
          return;
        }
        // If a newer request replaced this one, ignore this error.
        try {
          const cur = this._inflightByForm.get(form);
          if (cur && cur.reqId !== reqId) return;
        } catch (_e) {}
        console.error('[FormBuilderAjax] submit failed', err);
        // If the item modal was hidden, restore it so the user can retry without losing inputs.
        if (isItemModalForm) {
          try {
            const modal = form && form.closest ? form.closest('.fixed.inset-0') : null;
            if (modal && modal.classList) modal.classList.remove('hidden');
          } catch (_e) {}
          // Show inline validation errors if the server provided them (e.g. WTForms errors).
          try {
            const data = err && err.__fbData ? err.__fbData : null;
            const errors = data && data.errors ? data.errors : null;
            if (errors && window.ItemModal) {
              // Ensure modal references are current (DOM may have been swapped previously)
              try { window.ItemModal.modalElement = window.ItemModal.modalElement || document.getElementById('item-modal'); } catch (_e) {}
              try { window.ItemModal.formElement = form; } catch (_e) {}
              if (typeof window.ItemModal.clearValidationErrors === 'function') {
                window.ItemModal.clearValidationErrors();
              }
              if (typeof window.ItemModal.displayValidationErrors === 'function') {
                window.ItemModal.displayValidationErrors(errors, '');
              }
            }
          } catch (_e) {}
        }
        this.showError('Save failed', err?.message || 'Please try again.', retryFn);
        throw err;
      } finally {
        // Clear in-flight state if this is still the latest request.
        try {
          const cur = this._inflightByForm.get(form);
          if (cur && cur.reqId === reqId) {
            this._inflightByForm.delete(form);
          }
        } catch (_e) {}
      }
    };

    // Expose a small helper for inline confirmation scripts (they call form.submit()).
    window.FormBuilderAjax = {
      submit: (form) => submitViaAjax(form),
      showSaving: (t, d) => this.showSaving(t, d),
      showSuccess: (t, d) => this.showSuccess(t, d),
      showError: (t, d, r) => this.showError(t, d, r)
    };

    // Global submit interception (bubble) for POST forms in builder UI.
    // IMPORTANT: must run after other submit handlers (e.g. ItemModal.setupFormSubmission)
    // so they can serialize UI state into hidden fields before we snapshot FormData.
    document.addEventListener('submit', (event) => {
      const form = event.target;
      if (!shouldAjaxifyForm(form)) return;
      // If another handler prevented submission (confirm flows), don't interfere.
      if (event.defaultPrevented) return;
      event.preventDefault();
      // We are handling this submit via AJAX, so any capture-phase "double submit"
      // guards must be reset immediately. Otherwise they can leave the submit button
      // disabled (and the form marked as "submitting") even though we never navigate.
      try {
        if (window.FormSubmitGuard && typeof window.FormSubmitGuard.reset === 'function') {
          window.FormSubmitGuard.reset(form);
        }
      } catch (_e) {}
      submitViaAjax(form).catch(() => { /* banner already shows error */ });
    }, false);

    // Keep legacy "disable submit button + spinner" behavior for any native submits
    // we *didn't* ajaxify (or if JS is disabled).
    document.addEventListener('submit', (event) => {
      const form = event.target;
      if (!(form instanceof HTMLFormElement)) return;
      // If another handler (e.g., inline onsubmit confirm) prevented submission, skip UI changes
      if (event.defaultPrevented) return;
      const submitButton = form.querySelector('button[type="submit"], input[type="submit"]');
      if (!submitButton) return;
      if (submitButton.dataset.loadingApplied === '1') return;
      submitButton.dataset.loadingApplied = '1';
      submitButton.disabled = true;
      if (submitButton.tagName.toLowerCase() === 'button') {
        // Store original content as a DocumentFragment for restoration
        const originalFragment = document.createDocumentFragment();
        Array.from(submitButton.childNodes).forEach(node => {
          originalFragment.appendChild(node.cloneNode(true));
        });
        submitButton.dataset.originalText = submitButton.innerHTML;

        // Build loading state with DOM construction
        submitButton.replaceChildren();
        const spinner = document.createElement('i');
        spinner.className = 'fas fa-spinner fa-spin mr-2';
        submitButton.appendChild(spinner);
        submitButton.appendChild(document.createTextNode('Saving...'));
      }
    });
  }
};

// NOTE:
// This module should be explicitly initialised by the form builder entrypoint (`js/form_builder/main.js`).
// Auto-initialising here can register submit interceptors before other modules' submit handlers,
// causing FormData snapshots to miss last-moment serialization (e.g. ItemModal shared fields).
