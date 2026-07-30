(function () {
  'use strict';

  var configEl = document.getElementById('notification-registry-preview-config');
  if (!configEl) return;

  var config = {};
  try {
    config = JSON.parse(configEl.textContent || '{}');
  } catch (e) {
    console.error('[notification-registry-preview] invalid config JSON', e);
    return;
  }

  var modal = document.getElementById('notification-registry-preview-modal');
  var typeLabelEl = document.getElementById('notification-registry-preview-type');
  var variantSelect = document.getElementById('notification-registry-preview-variant');
  var localeSelect = document.getElementById('notification-registry-preview-locale');
  var refreshBtn = document.getElementById('notification-registry-preview-refresh');
  var loadingEl = document.getElementById('notification-registry-preview-loading');
  var errorEl = document.getElementById('notification-registry-preview-error');
  var titleEl = document.getElementById('notification-registry-preview-title');
  var messageEl = document.getElementById('notification-registry-preview-message');
  var noteEl = document.getElementById('notification-registry-preview-note');
  var emailFrame = document.getElementById('notification-registry-preview-email-frame');
  var emailUnavailableEl = document.getElementById('notification-registry-preview-email-unavailable');

  var currentTypeKey = null;

  function csrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
  }

  function showModal() {
    if (!modal) return;
    modal.classList.remove('hidden');
    modal.classList.add('flex');
  }

  function hideModal() {
    if (!modal) return;
    modal.classList.add('hidden');
    modal.classList.remove('flex');
  }

  function setLoading(isLoading) {
    if (loadingEl) loadingEl.classList.toggle('hidden', !isLoading);
    if (refreshBtn) refreshBtn.disabled = !!isLoading;
  }

  function setError(message) {
    if (!errorEl) return;
    if (message) {
      errorEl.textContent = message;
      errorEl.classList.remove('hidden');
    } else {
      errorEl.textContent = '';
      errorEl.classList.add('hidden');
    }
  }

  function populateVariants(typeKey) {
    if (!variantSelect) return;
    var variants = (config.variantsByType && config.variantsByType[typeKey]) || [];
    variantSelect.innerHTML = '';
    variants.forEach(function (variant) {
      var opt = document.createElement('option');
      opt.value = variant.id;
      opt.textContent = variant.label;
      variantSelect.appendChild(opt);
    });
  }

  function renderEmail(html) {
    if (!emailFrame || !emailUnavailableEl) return;
    if (html) {
      emailFrame.classList.remove('hidden');
      emailUnavailableEl.classList.add('hidden');
      emailFrame.srcdoc = html;
    } else {
      emailFrame.classList.add('hidden');
      emailFrame.removeAttribute('srcdoc');
      emailUnavailableEl.textContent = (config.labels && config.labels.emailUnavailable) || 'No email preview.';
      emailUnavailableEl.classList.remove('hidden');
    }
  }

  function loadPreview() {
    if (!currentTypeKey || !config.previewUrl) return;
    setError('');
    setLoading(true);

    var payload = {
      type_key: currentTypeKey,
      variant_id: variantSelect ? variantSelect.value : 'default',
      locale: localeSelect ? localeSelect.value : 'en',
    };

    var fetchFn = (window.getFetch && window.getFetch()) || fetch;
    fetchFn(config.previewUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken(),
      },
      body: JSON.stringify(payload),
    })
      .then(function (resp) {
        return resp.json().then(function (body) {
          return { ok: resp.ok, body: body };
        });
      })
      .then(function (result) {
        if (!result.ok || !result.body || !result.body.preview) {
          throw new Error((result.body && result.body.error) || (config.labels && config.labels.previewFailed) || 'Preview failed');
        }
        var preview = result.body.preview;
        if (titleEl) titleEl.textContent = preview.title || '';
        if (messageEl) messageEl.textContent = preview.message || '';
        if (noteEl) noteEl.textContent = preview.preview_note || '';
        renderEmail(preview.email_html || null);
      })
      .catch(function (err) {
        renderEmail(null);
        if (titleEl) titleEl.textContent = '';
        if (messageEl) messageEl.textContent = '';
        if (noteEl) noteEl.textContent = '';
        setError(err.message || ((config.labels && config.labels.previewFailed) || 'Preview failed'));
      })
      .finally(function () {
        setLoading(false);
      });
  }

  function openPreview(typeKey, typeLabel) {
    currentTypeKey = typeKey;
    if (typeLabelEl) {
      typeLabelEl.textContent = typeLabel ? (typeLabel + ' (' + typeKey + ')') : typeKey;
    }
    populateVariants(typeKey);
    showModal();
    loadPreview();
  }

  document.querySelectorAll('.notification-registry-preview-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      openPreview(btn.getAttribute('data-type-key'), btn.getAttribute('data-type-label'));
    });
  });

  if (refreshBtn) refreshBtn.addEventListener('click', loadPreview);
  if (variantSelect) variantSelect.addEventListener('change', loadPreview);
  if (localeSelect) localeSelect.addEventListener('change', loadPreview);

  if (modal) {
    modal.querySelectorAll('.close-modal').forEach(function (btn) {
      btn.addEventListener('click', hideModal);
    });
    modal.addEventListener('click', function (evt) {
      if (evt.target === modal) hideModal();
    });
  }
})();
