(() => {
  function $(id) {
    return document.getElementById(id);
  }

  // AI validation sources (persisted in browser; also mirrored to URL as ai_sources=...)
  const AI_VALIDATION_SOURCES_STORAGE_KEY = 'ifrc_ai_validation_sources_v1';
  const AI_VALIDATION_SOURCES_ALLOWED = ['historical', 'system_documents', 'upr_documents'];
  const AI_VALIDATION_SOURCES_DEFAULT = ['historical', 'system_documents'];

  function uniq(arr) {
    const out = [];
    const seen = new Set();
    for (const v of (arr || [])) {
      const s = String(v || '').trim();
      if (!s || seen.has(s)) continue;
      seen.add(s);
      out.push(s);
    }
    return out;
  }

  function loadAiValidationSources() {
    try {
      const raw = localStorage.getItem(AI_VALIDATION_SOURCES_STORAGE_KEY);
      if (!raw) return AI_VALIDATION_SOURCES_DEFAULT.slice();
      const parsed = JSON.parse(raw);
      const arr = Array.isArray(parsed) ? parsed : [];
      const norm = uniq(arr).filter((v) => AI_VALIDATION_SOURCES_ALLOWED.includes(v));
      return norm.length ? norm : AI_VALIDATION_SOURCES_DEFAULT.slice();
    } catch {
      return AI_VALIDATION_SOURCES_DEFAULT.slice();
    }
  }

  function saveAiValidationSources(arr) {
    try {
      const norm = uniq(arr).filter((v) => AI_VALIDATION_SOURCES_ALLOWED.includes(v));
      localStorage.setItem(AI_VALIDATION_SOURCES_STORAGE_KEY, JSON.stringify(norm));
    } catch {
      // ignore
    }
  }

  function sourcesFromUiOrStorage() {
    const cbHist = $('ai-src-historical');
    const cbSys = $('ai-src-system');
    const cbUpr = $('ai-src-upr');
    if (!(cbHist && cbSys && cbUpr)) return loadAiValidationSources();
    const sel = [];
    if (cbHist.checked) sel.push('historical');
    if (cbSys.checked) sel.push('system_documents');
    if (cbUpr.checked) sel.push('upr_documents');
    return sel.length ? sel : AI_VALIDATION_SOURCES_DEFAULT.slice();
  }

  function normalizeSourcesFromUrlParam(raw) {
    if (!raw) return null;
    const parts = String(raw)
      .split(',')
      .map((s) => String(s || '').trim())
      .filter(Boolean);
    const norm = uniq(parts).filter((v) => AI_VALIDATION_SOURCES_ALLOWED.includes(v));
    return norm.length ? norm : null;
  }

  function arraysEqual(a, b) {
    const aa = Array.isArray(a) ? a : [];
    const bb = Array.isArray(b) ? b : [];
    if (aa.length !== bb.length) return false;
    for (let i = 0; i < aa.length; i += 1) {
      if (aa[i] !== bb[i]) return false;
    }
    return true;
  }

  function getAppEl() {
    return document.getElementById('validation-summary-app');
  }

  function safeJsonParse(s) {
    try { return JSON.parse(s || '{}'); } catch { return {}; }
  }

  function init() {
    const app = getAppEl();
    if (!app) return;

    // Ensure URL carries ai_sources from localStorage so server-side generated SSE/PDF URLs use it.
    // Do a one-time replace reload if missing/mismatched (guarded by _ai_src_sync=1).
    try {
      const desired = loadAiValidationSources();
      const u = new URL(window.location.href);
      const cur = normalizeSourcesFromUrlParam(u.searchParams.get('ai_sources'));
      const alreadySynced = u.searchParams.get('_ai_src_sync') === '1';
      if (!alreadySynced && (!cur || !arraysEqual(cur, desired))) {
        u.searchParams.set('ai_sources', desired.join(','));
        u.searchParams.set('_ai_src_sync', '1');
        window.location.replace(u.toString());
        return;
      }
    } catch {
      // ignore
    }

    const cfg = {
      sseUrl: app.dataset.sseUrl || '',
      pdfUrl: app.dataset.pdfUrl || '',
      cancelUrl: app.dataset.cancelUrl || '',
      runId: app.dataset.runId || '',
      csrfToken: app.dataset.csrfToken || '',
      labels: {
        notRun: app.dataset.labelNotRun || 'not run',
        failed: app.dataset.labelFailed || 'failed',
        good: app.dataset.labelGood || 'good',
        discrepancy: app.dataset.labelDiscrepancy || 'discrepancy',
        uncertain: app.dataset.labelUncertain || 'uncertain',
        running: app.dataset.labelRunning || 'running',
        done: app.dataset.labelDone || 'Done',
        cancelling: app.dataset.labelCancelling || 'Cancelling…',
        cancelled: app.dataset.labelCancelled || 'Cancelled',
        cancelFailed: app.dataset.labelCancelFailed || 'Cancel failed',
        connectionLost: app.dataset.labelConnectionLost || 'Connection lost.',
      },
    };

    function capitalizeFirst(s) {
      const t = String(s ?? '').trim();
      if (!t) return '';
      // Locale-aware uppercasing of the first character only
      return t.charAt(0).toLocaleUpperCase() + t.slice(1);
    }

    const els = {
      good: $('count-good'),
      discrepancy: $('count-discrepancy'),
      uncertain: $('count-uncertain'),
      failed: $('count-failed'),
      missing: $('count-missing'),
      completed: $('completed-count'),
      toRun: $('to-run-count'),
      statusDot: $('status-dot'),
      statusText: $('status-text'),
      openPdf: $('open-pdf-btn'),
      cancelBtn: $('cancel-btn'),
      closeBtn: $('close-btn'),
      includeNonReported: $('include-non-reported'),
      runMissingBtn: $('run-missing-btn'),
    };

    // Initialize sources UI (if present on this page)
    (function initAiSourcesUi() {
      const cbHist = $('ai-src-historical');
      const cbSys = $('ai-src-system');
      const cbUpr = $('ai-src-upr');
      if (!(cbHist && cbSys && cbUpr)) return;

      const selected = loadAiValidationSources();
      cbHist.checked = selected.includes('historical');
      cbSys.checked = selected.includes('system_documents');
      cbUpr.checked = selected.includes('upr_documents');

      function persistAndReflectUrl() {
        // Enforce at least one selection (fallback to defaults)
        if (!cbHist.checked && !cbSys.checked && !cbUpr.checked) {
          cbHist.checked = true;
          cbSys.checked = true;
          cbUpr.checked = false;
        }
        const sel = sourcesFromUiOrStorage();
        saveAiValidationSources(sel);
        // Update current URL param for shareability; do not reload or re-run.
        try {
          const u = new URL(window.location.href);
          u.searchParams.set('ai_sources', sel.join(','));
          window.history.replaceState(null, '', u.toString());
        } catch {
          // ignore
        }
      }
      cbHist.addEventListener('change', persistAndReflectUrl);
      cbSys.addEventListener('change', persistAndReflectUrl);
      cbUpr.addEventListener('change', persistAndReflectUrl);

      // Close <details> when clicking outside
      const details = document.getElementById('ai-validation-sources-details');
      if (details && details.tagName && details.tagName.toLowerCase() === 'details') {
        document.addEventListener('click', (ev) => {
          const t = ev && ev.target ? ev.target : null;
          if (!t) return;
          if (details.contains(t)) return;
          details.open = false;
        });
      }
    })();

    function escapeHtml(input) {
      const s = String(input ?? '');
      return s
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
    }

    function normalizeText(v) {
      if (v === null || v === undefined) return '';
      const s = String(v).trim();
      if (!s) return '';
      const lo = s.toLowerCase();
      if (lo === 'none' || lo === 'null' || lo === 'undefined') return '';
      return s;
    }

    function formatSourcesHtml(srcs) {
      if (!Array.isArray(srcs) || srcs.length === 0) return '';
      const items = srcs.slice(0, 5).map((s) => {
        if (!s || typeof s !== 'object') return '';
        const title = normalizeText(s.document_title) || (s.document_id ? `Document ${String(s.document_id)}` : 'Document');
        const url = normalizeText(s.document_url);
        const page = (s.page_number !== null && s.page_number !== undefined && Number.isFinite(Number(s.page_number))) ? Number(s.page_number) : null;
        const quote = normalizeText(s.quote);
        const pageTxt = (page !== null && page > 0) ? ` (p. ${page})` : '';
        const quoteTxt = quote ? ` — “${quote}”` : '';
        const titleHtml = url
          ? `<a class="src-link" href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(title)}</a>`
          : `<span class="src-link">${escapeHtml(title)}</span>`;
        return `<li>${titleHtml}${escapeHtml(pageTxt)}${quoteTxt ? `<span>${escapeHtml(quoteTxt)}</span>` : ''}</li>`;
      }).filter(Boolean).join('');
      if (!items) return '';
      return `<div class="src-block"><div class="src-title">Sources</div><ul class="src-list">${items}</ul></div>`;
    }

    function formatOpinionHtml(validation) {
      const summary = normalizeText(validation?.opinion_summary || validation?.opinion_text);
      const details = normalizeText(validation?.opinion_details);
      const decision = normalizeText(validation?.decision);
      const basis = Array.isArray(validation?.opinion_basis) ? validation.opinion_basis.filter(Boolean) : [];
      const sources = Array.isArray(validation?.opinion_sources) ? validation.opinion_sources : [];

      if (!summary && !details && !decision && basis.length === 0 && sources.length === 0) return '-';

      const hasExpandable = !!(details || decision || basis.length || sources.length);

      if (!hasExpandable) return escapeHtml(summary || '-');

      const popupPayload = encodeURIComponent(JSON.stringify({ summary, details, decision, basis, sources }));

      return `
        <div class="op-wrap">
          ${summary ? `<div class="op-summary">${escapeHtml(summary)}</div>` : ''}
          <button class="op-more-btn ai-popup-trigger" data-ai-popup="${escapeHtml(popupPayload)}" type="button">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="flex-shrink:0" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M12 8v4m0 4h.01"/></svg>
            More details
          </button>
        </div>
      `.trim();
    }

    function setCounts(counts) {
      if (!counts) return;
      if (els.good) els.good.textContent = String(counts.good ?? 0);
      if (els.discrepancy) els.discrepancy.textContent = String(counts.discrepancy ?? 0);
      if (els.uncertain) els.uncertain.textContent = String(counts.uncertain ?? 0);
      if (els.failed) els.failed.textContent = String(counts.failed ?? 0);
      if (els.missing) els.missing.textContent = String(counts.missing ?? 0);
    }

    function renderBadge(fid, validation) {
      const badge = $(`badge-${fid}`);
      if (!badge) return;
      const status = String(validation?.status || '').toLowerCase();
      const verdict = String(validation?.verdict || '').toLowerCase();

      badge.className = 'badge';
      if (!verdict) {
        badge.classList.add('miss');
        badge.textContent = capitalizeFirst(cfg.labels.notRun);
        return;
      }
      if (status === 'failed') {
        badge.classList.add('fail');
        badge.textContent = capitalizeFirst(cfg.labels.failed);
        return;
      }
      if (verdict === 'good') { badge.classList.add('good'); badge.textContent = capitalizeFirst(cfg.labels.good); return; }
      if (verdict === 'discrepancy') { badge.classList.add('disc'); badge.textContent = capitalizeFirst(cfg.labels.discrepancy); return; }
      badge.classList.add('unc');
      badge.textContent = capitalizeFirst(cfg.labels.uncertain);
    }

    function renderRowUpdate(fid, validation) {
      renderBadge(fid, validation);
      const confEl = $(`conf-${fid}`);
      if (confEl) {
        const c = validation?.confidence;
        const n = (c !== null && c !== undefined) ? Number(c) : NaN;
        confEl.textContent = Number.isFinite(n) ? `${Math.round(n * 100)}%` : '-';
      }
      const opEl = $(`op-${fid}`);
      if (opEl) {
        opEl.innerHTML = formatOpinionHtml(validation);
      }
    }

    function markRunning(fid) {
      const badge = $(`badge-${fid}`);
      if (!badge) return;
      badge.className = 'badge run';
      badge.textContent = capitalizeFirst(cfg.labels.running);
    }

    let es = null;

    if (els.openPdf) {
      els.openPdf.addEventListener('click', () => {
        if (cfg.pdfUrl) window.open(cfg.pdfUrl, '_blank');
      });
    }
    if (els.includeNonReported) {
      els.includeNonReported.addEventListener('change', () => {
        try {
          const u = new URL(window.location.href);
          const checked = !!els.includeNonReported.checked;
          u.searchParams.set('include_non_reported', checked ? '1' : '0');
          u.searchParams.set('ai_sources', sourcesFromUiOrStorage().join(','));
          // Show/hide rows only; do NOT auto-run when toggling.
          u.searchParams.set('run', '0');
          u.searchParams.set('run_mode', 'missing');
          u.searchParams.delete('run_id');
          window.location.assign(u.toString());
        } catch (e) {
          // fallback: hard reload
          window.location.reload();
        }
      });
    }
    if (els.runMissingBtn) {
      els.runMissingBtn.addEventListener('click', () => {
        try {
          const u = new URL(window.location.href);
          u.searchParams.set('run', '1');
          u.searchParams.set('run_mode', 'missing');
          u.searchParams.set('ai_sources', sourcesFromUiOrStorage().join(','));
          u.searchParams.delete('run_id');
          window.location.assign(u.toString());
        } catch (e) {
          window.location.reload();
        }
      });
    }
    if (els.closeBtn) {
      els.closeBtn.addEventListener('click', () => window.close());
    }
    if (els.cancelBtn) {
      els.cancelBtn.addEventListener('click', async () => {
        try {
          els.cancelBtn.disabled = true;
          if (els.statusText) els.statusText.textContent = cfg.labels.cancelling;
          if (es) es.close();
          const fn = (window.getFetch && window.getFetch()) || fetch;
          await fn(cfg.cancelUrl, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': cfg.csrfToken,
              'X-Requested-With': 'XMLHttpRequest',
            },
            credentials: 'same-origin',
            body: JSON.stringify({ run_id: cfg.runId }),
          });
          if (els.statusDot) els.statusDot.classList.remove('running');
          if (els.statusText) els.statusText.textContent = cfg.labels.cancelled;
          if (els.openPdf) els.openPdf.disabled = false;
        } catch (e) {
          if (els.statusText) els.statusText.textContent = cfg.labels.cancelFailed;
        }
      });
    }

    // Start SSE
    if (!cfg.sseUrl) return;
    es = new EventSource(cfg.sseUrl, { withCredentials: true });

    es.addEventListener('init', (ev) => {
      const data = safeJsonParse(ev.data);
      setCounts(data.counts);
      const total = data.total_items != null ? data.total_items : (data.to_run || []).length;
      if (els.toRun) els.toRun.textContent = String(total);
      if (els.completed) els.completed.textContent = String(data.completed ?? 0);
    });

    es.addEventListener('snapshot', (ev) => {
      const data = safeJsonParse(ev.data);
      const items = data.items || [];
      for (const it of items) {
        if (!it || !it.form_data_id) continue;
        if (it.validation) renderRowUpdate(it.form_data_id, it.validation);
      }
    });

    es.addEventListener('started', (ev) => {
      const data = safeJsonParse(ev.data);
      if (data.form_data_id) markRunning(data.form_data_id);
    });

    es.addEventListener('item', (ev) => {
      const data = safeJsonParse(ev.data);
      const fid = data.form_data_id;
      if (fid) renderRowUpdate(fid, data.validation || {});
      setCounts(data.counts);
      if (data.completed != null && els.completed) els.completed.textContent = String(data.completed);
      if (data.total_items != null && els.toRun) els.toRun.textContent = String(data.total_items);
    });

    es.addEventListener('done', (ev) => {
      const data = safeJsonParse(ev.data);
      setCounts(data.counts);
      if (data.total_items != null && els.toRun) els.toRun.textContent = String(data.total_items);
      if (data.completed != null && els.completed) els.completed.textContent = String(data.completed);
      if (els.statusDot) {
        els.statusDot.classList.remove('running');
        els.statusDot.classList.add('done');
      }
      if (els.statusText) els.statusText.textContent = cfg.labels.done;
      if (els.openPdf) els.openPdf.disabled = false;
      if (els.cancelBtn) els.cancelBtn.disabled = true;
      es.close();
    });

    es.addEventListener('cancelled', (ev) => {
      const data = safeJsonParse(ev.data);
      setCounts(data.counts);
      if (data.total_items != null && els.toRun) els.toRun.textContent = String(data.total_items);
      if (data.completed != null && els.completed) els.completed.textContent = String(data.completed);
      if (els.statusDot) els.statusDot.classList.remove('running');
      if (els.statusText) els.statusText.textContent = cfg.labels.cancelled;
      if (els.openPdf) els.openPdf.disabled = false;
      if (els.cancelBtn) els.cancelBtn.disabled = true;
      es.close();
    });

    es.addEventListener('error', () => {
      if (els.statusDot) els.statusDot.classList.remove('running');
      if (els.statusText) els.statusText.textContent = cfg.labels.connectionLost;
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

