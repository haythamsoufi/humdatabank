// ai-documents-job-progress.js
// Unified server-backed job progress + per-document stage polling for AI documents page.

(function () {
  'use strict';

  var TERMINAL_DOC_STATUSES = ['completed', 'failed', 'not_found'];
  var TERMINAL_JOB_STATUSES = ['completed', 'failed', 'cancelled'];
  var POLL_MS = 2000;

  var JOB_SPECS = {
    ifrc_api_bulk: {
      storageKey: 'ai_docs_external_api_import_job',
      statusUrl: function (jobId) {
        return '/api/ai/documents/ifrc-api/import-bulk/' + encodeURIComponent(jobId) + '/status';
      },
      cancelUrl: function (jobId) {
        return '/api/ai/documents/ifrc-api/import-bulk/' + encodeURIComponent(jobId) + '/cancel';
      },
      titleImport: true,
    },
    docs_b_bulk_import_system: {
      storageKey: 'ai_docs_system_import_job',
      statusUrl: function (jobId, urls) {
        var tpl = urls && urls.importSystemBulkStatus;
        if (tpl) return String(tpl).replace('__JOB__', encodeURIComponent(jobId));
        return '/admin/ai/documents/import-system-bulk/' + encodeURIComponent(jobId) + '/status';
      },
      cancelUrl: function (jobId, urls) {
        var tpl = urls && urls.importSystemBulkCancel;
        if (tpl) return String(tpl).replace('__JOB__', encodeURIComponent(jobId));
        return '/admin/ai/documents/import-system-bulk/' + encodeURIComponent(jobId) + '/cancel';
      },
      titleImport: true,
    },
    docs_bulk_reprocess: {
      storageKey: 'ai_docs_bulk_reprocess_job',
      statusUrl: function (jobId) {
        return '/admin/ai/documents/bulk-reprocess/' + encodeURIComponent(jobId) + '/status';
      },
      cancelUrl: function (jobId) {
        return '/admin/ai/documents/bulk-reprocess/' + encodeURIComponent(jobId) + '/cancel';
      },
      titleImport: false,
    },
    docs_bulk_reprocess_metadata: {
      storageKey: 'ai_docs_bulk_reprocess_metadata_job',
      statusUrl: function (jobId) {
        return '/admin/ai/documents/bulk-reprocess-metadata/' + encodeURIComponent(jobId) + '/status';
      },
      cancelUrl: function (jobId) {
        return '/admin/ai/documents/bulk-reprocess-metadata/' + encodeURIComponent(jobId) + '/cancel';
      },
      titleImport: false,
      metadataOnly: true,
    },
  };

  function normalizeJobType(jobType) {
    var raw = String(jobType || '').trim();
    if (JOB_SPECS[raw]) return raw;
    var underscored = raw.replace(/\./g, '_');
    if (JOB_SPECS[underscored]) return underscored;
    if (raw === 'ifrc_api_bulk') return 'ifrc_api_bulk';
    if (raw === 'docs.bulk_import_system') return 'docs_b_bulk_import_system';
    if (raw === 'docs.bulk_reprocess') return 'docs_bulk_reprocess';
    if (raw === 'docs.bulk_reprocess_metadata') return 'docs_bulk_reprocess_metadata';
    return raw;
  }

  function getSpec(jobType) {
    return JOB_SPECS[normalizeJobType(jobType)] || null;
  }

  function clampPercent(value) {
    var n = Number(value);
    if (!Number.isFinite(n)) return 0;
    return Math.max(0, Math.min(100, Math.round(n)));
  }

  function readJsonScript(id, fallback) {
    var el = document.getElementById(id);
    if (!el) return fallback;
    try {
      return JSON.parse(el.textContent || 'null') || fallback;
    } catch (e) {
      return fallback;
    }
  }

  var state = {
    cfg: null,
    t: {},
    urls: {},
    bannerUI: null,
    bannerEls: {},
    hooks: {},
    fetchFn: null,
    csrfFetchFn: null,
    debug: false,
    activeJob: null,
    masterTimer: null,
    trackedDocs: new Map(),
    docPollers: new Map(),
    hideTimer: null,
    standaloneMode: false,
    docListExpanded: false,
    optimisticJob: false,
  };

  function clearBannerHideTimer() {
    if (state.hideTimer) {
      clearTimeout(state.hideTimer);
      state.hideTimer = null;
    }
  }

  function isJobTerminalDisplay() {
    var job = state.activeJob;
    return !!(job && !state.standaloneMode && TERMINAL_JOB_STATUSES.indexOf(String(job.status || '')) >= 0);
  }

  function stopAllDocPolls() {
    state.docPollers.forEach(function (timer) {
      clearInterval(timer);
    });
    state.docPollers.clear();
  }

  function log() {
    if (!state.debug) return;
    try {
      var args = ['[AI Docs Progress]'].concat(Array.prototype.slice.call(arguments));
      window.__clientLog && window.__clientLog.apply(null, args);
    } catch (e) { /* ignore */ }
  }

  function readStorage(key) {
    try {
      var raw = localStorage.getItem(key) || sessionStorage.getItem(key);
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  }

  function writeStorage(key, data) {
    try {
      localStorage.setItem(key, JSON.stringify(data));
      sessionStorage.removeItem(key);
      return true;
    } catch (e) {
      return false;
    }
  }

  function clearStorage(key) {
    try {
      localStorage.removeItem(key);
      sessionStorage.removeItem(key);
    } catch (e) { /* ignore */ }
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function itemImportStatus(it) {
    return String((it && (it.import_status || it.reprocess_status || it.status)) || 'queued');
  }

  function resolveItemDocId(it) {
    if (!it) return null;
    var docId = it.ai_document_id;
    if (docId == null && it.requested_document_id != null) docId = it.requested_document_id;
    if (docId == null && it.document && it.document.id != null) docId = it.document.id;
    if (docId == null && it.entity_id != null) docId = it.entity_id;
    if (docId == null && it.payload && it.payload.document_id != null) docId = it.payload.document_id;
    if (docId == null || !Number.isFinite(Number(docId))) return null;
    return Number(docId);
  }

  function defaultStageForItemStatus(status, t) {
    if (status === 'downloading') return t.downloading_ae314963 || 'Downloading';
    if (status === 'processing') return t.processing_643562a9 || 'Processing';
    if (status === 'completed') return t.completed_07ca5050 || 'Done';
    if (status === 'failed') return t.failed_d7c8c85b || 'Failed';
    if (status === 'cancelled') return t.cancel_ea478870 || 'Cancelled';
    return t.pending_2d13df6f || 'Queued';
  }

  function defaultProgressForItemStatus(status, tracked) {
    if (tracked && typeof tracked.progress === 'number') return clampPercent(tracked.progress);
    if (status === 'completed' || status === 'failed' || status === 'cancelled') return 100;
    if (status === 'downloading') return 12;
    if (status === 'processing') return 20;
    return 0;
  }

  function isTerminalItemStatus(status) {
    var st = String(status || '');
    return st === 'completed' || st === 'failed' || st === 'cancelled' || st === 'not_found';
  }

  function isInFlightDocRow(row) {
    if (!row) return false;
    var itemSt = String(row.itemStatus || '');
    var st = String(row.status || '');
    if (isTerminalItemStatus(itemSt) || isTerminalItemStatus(st)) return false;
    if (itemSt === 'downloading' || itemSt === 'processing') return true;
    if (itemSt === 'queued') return false;
    return st === 'downloading' || st === 'processing' || st === 'pending';
  }

  function filterInFlightDocRows(rows) {
    return (rows || []).filter(isInFlightDocRow);
  }

  function resolveJobItemForDoc(docId) {
    var job = state.activeJob;
    if (!job || !Array.isArray(job.items)) return null;
    var id = Number(docId);
    if (!Number.isFinite(id)) return null;
    for (var i = 0; i < job.items.length; i += 1) {
      if (resolveItemDocId(job.items[i]) === id) return job.items[i];
    }
    return null;
  }

  function syncTrackedDocFromJobItem(it, opts) {
    opts = opts || {};
    var docId = resolveItemDocId(it);
    if (docId == null) return;
    var st = itemImportStatus(it);
    var t = state.t;
    if (st === 'completed') {
      updateDocEntry(docId, {
        silent: !!opts.silent,
        status: 'completed',
        stage: t.completed_07ca5050 || 'Done',
        progress: 100,
        error: '',
      });
      stopDocPoll(docId);
      return;
    }
    if (st === 'failed') {
      updateDocEntry(docId, {
        silent: !!opts.silent,
        status: 'failed',
        stage: t.failed_d7c8c85b || 'Failed',
        progress: 100,
        error: (it && (it.reprocess_error || it.import_error || it.error)) || '',
      });
      stopDocPoll(docId);
      return;
    }
    if (st === 'cancelled' || st === 'not_found') {
      updateDocEntry(docId, {
        silent: !!opts.silent,
        status: st,
        stage: defaultStageForItemStatus(st, t),
        progress: 100,
      });
      stopDocPoll(docId);
    }
  }

  function resolveJobTotal(job) {
    if (!job) return 0;
    return Number(job.total) || Number(job.snapshot && job.snapshot.total_items) || 0;
  }

  function isSingleDocContext(job, totalDocsFallback) {
    if (job && !state.standaloneMode) {
      return resolveJobTotal(job) === 1;
    }
    var n = Number(totalDocsFallback);
    return Number.isFinite(n) && n === 1;
  }

  function resolveSingleDocStage(job, trackedDocs, t) {
    if (trackedDocs && trackedDocs.size) {
      var entries = Array.from(trackedDocs.entries());
      for (var i = 0; i < entries.length; i += 1) {
        var data = entries[i][1] || {};
        if (data.stage && !isTerminalItemStatus(data.status)) return data.stage;
      }
      if (entries[0][1] && entries[0][1].stage) return entries[0][1].stage;
    }
    if (job && Array.isArray(job.items) && job.items.length) {
      var it = job.items[0];
      var docId = resolveItemDocId(it);
      var tracked = docId != null ? trackedDocs.get(docId) : null;
      if (tracked && tracked.stage) return tracked.stage;
      return defaultStageForItemStatus(itemImportStatus(it), t);
    }
    return t.preparing_0862f67f || 'Preparing...';
  }

  function docListToggleLabel(expanded, count, t) {
    if (expanded) return t.hide_details_6c4e8b91 || 'Hide details';
    var base = t.show_details_3f7a2d18 || 'Show details';
    return count > 0 ? (base + ' (' + count + ')') : base;
  }

  function resolveItemLabel(it, idx, t) {
    var docId = resolveItemDocId(it);
    if (docId != null) return '#' + docId;
    var submittedId = it && it.submitted_document_id;
    if (submittedId != null && String(submittedId).trim() !== '') {
      return 'Import #' + submittedId;
    }
    return (t.document_09453598 || 'Document') + ' ' + (Number(it.index != null ? it.index : idx) + 1);
  }

  function formatJobOverallText(prog, t) {
    var done = Number(prog.done) || 0;
    var total = Number(prog.total) || 0;
    var active = Number(prog.inFlight) || 0;
    if (total <= 0) return '';
    if (done >= total) return done + '/' + total;
    if (active > 0) {
      return done + '/' + total + ' · ' + active + ' ' + (t.in_progress_8b6e4a2c || 'in progress');
    }
    return done + '/' + total;
  }
  function buildDocRowsFromJob(job, trackedDocs, t) {
    var items = Array.isArray(job && job.items) ? job.items.slice() : [];
    items.sort(function (a, b) {
      return (Number(a.index) || 0) - (Number(b.index) || 0);
    });
    if (!items.length) {
      if (trackedDocs.size) return buildDocRowsFromTracked(trackedDocs);
      if (job && Number(job.total) > 0) {
        items = [];
        for (var i = 0; i < Number(job.total); i += 1) {
          items.push({ index: i, import_status: 'queued' });
        }
      } else {
        return [];
      }
    }
    return items.map(function (it, idx) {
      var docId = resolveItemDocId(it);
      var itemStatus = itemImportStatus(it);
      var tracked = (docId != null && trackedDocs.has(docId)) ? trackedDocs.get(docId) : null;
      var status = itemStatus;
      var stage = defaultStageForItemStatus(itemStatus, t);
      var progress = defaultProgressForItemStatus(itemStatus, null);
      if (!isTerminalItemStatus(itemStatus) && tracked) {
        if (tracked.stage) stage = tracked.stage;
        progress = defaultProgressForItemStatus(itemStatus, tracked);
        if (tracked.status && !isTerminalItemStatus(tracked.status)) {
          status = tracked.status;
        }
      }
      var label = docId != null
        ? ('#' + docId)
        : ((t.document_09453598 || 'Document') + ' ' + (Number(it.index != null ? it.index : idx) + 1));
      return { label: label, stage: stage, progress: progress, status: status, itemStatus: itemStatus };
    });
  }

  function buildDocRowsFromTracked(trackedDocs) {
    return Array.from(trackedDocs.entries())
      .map(function (pair) {
        var data = pair[1] || {};
        return {
          docId: Number(pair[0]),
          label: '#' + pair[0],
          stage: data.stage || '',
          progress: clampPercent(data.progress || 0),
          status: data.status || 'pending',
          itemStatus: data.status || 'pending',
        };
      })
      .sort(function (a, b) {
        return Number(a.docId) - Number(b.docId);
      });
  }

  function trackedDocCountsAsDone(row) {
    if (TERMINAL_DOC_STATUSES.indexOf(row.status) < 0) return false;
    var tracked = state.trackedDocs.get(Number(row.docId));
    if (
      tracked &&
      tracked.reprocessRequestedAt &&
      !tracked.seenNonCompletedSinceRequest &&
      (Date.now() - Number(tracked.reprocessRequestedAt)) < 120000
    ) {
      return false;
    }
    return true;
  }

  function buildOptimisticJobItems(docIds, status) {
    status = status || 'queued';
    return (docIds || []).map(function (id, idx) {
      var docId = Number(id);
      return {
        index: idx,
        ai_document_id: docId,
        reprocess_status: status,
        import_status: status,
        status: status,
      };
    });
  }

  function beginOptimisticJob(jobType, total, docIds, opts) {
    opts = opts || {};
    clearBannerHideTimer();
    state.standaloneMode = false;
    state.docListExpanded = false;
    state.optimisticJob = true;
    var requestTs = opts.requestTs || null;
    var ids = (docIds || []).map(Number).filter(function (n) { return Number.isFinite(n); });
    ids.forEach(function (id) {
      trackDoc(id, { silent: true });
      updateDocEntry(id, {
        silent: true,
        status: 'pending',
        stage: state.t.pending_2d13df6f || 'Queued',
        progress: 0,
        reprocessRequestedAt: requestTs,
        seenNonCompletedSinceRequest: false,
      });
    });
    var n = Number(total) || ids.length || 0;
    var normalizedType = normalizeJobType(jobType);
    state.activeJob = {
      jobId: '',
      jobType: normalizedType,
      status: 'running',
      total: n,
      snapshot: {
        total_items: n,
        counts: { completed: 0, failed: 0, cancelled: 0, in_progress: n },
      },
      items: buildOptimisticJobItems(ids, 'queued'),
      startedAt: Date.now(),
    };
    renderFromState();
  }

  function activateJob(jobId, jobType, total) {
    clearBannerHideTimer();
    state.optimisticJob = false;
    var normalizedType = normalizeJobType(jobType);
    if (!state.activeJob || normalizeJobType(state.activeJob.jobType) !== normalizedType) {
      startJob(normalizedType, jobId, total);
      return;
    }
    state.activeJob.jobId = String(jobId);
    state.activeJob.status = 'running';
    state.activeJob.total = Number(total) || state.activeJob.total || 0;
    if (state.activeJob.snapshot) {
      state.activeJob.snapshot.total_items = state.activeJob.total;
    }
    state.standaloneMode = false;
    persistActiveJob(state.activeJob);
    ensureMasterPoll();
    renderFromState();
  }

  function failOptimisticJob(docIds, errorMsg) {
    clearBannerHideTimer();
    state.optimisticJob = false;
    var msg = errorMsg || '';
    (docIds || []).forEach(function (id) {
      var docId = Number(id);
      if (!Number.isFinite(docId)) return;
      updateDocEntry(docId, {
        silent: true,
        status: 'failed',
        stage: state.t.failed_d7c8c85b || 'Failed',
        progress: 100,
        error: msg,
      });
      stopDocPoll(docId);
    });
    state.activeJob = null;
    stopMasterPoll();
    renderFromState();
  }

  function renderDocListHtml(rows) {
    if (!rows || !rows.length) return '';
    return rows.map(function (row) {
      var pct = clampPercent(row.progress);
      var rowClass = 'ai-docs-progress-doc-row';
      if (row.status === 'completed' || row.itemStatus === 'completed') rowClass += ' is-done';
      if (row.status === 'failed' || row.itemStatus === 'failed') rowClass += ' is-failed';
      return '<div class="' + rowClass + '">' +
        '<span class="ai-docs-progress-doc-label">' + escapeHtml(row.label) + '</span>' +
        '<span class="ai-docs-progress-doc-stage">' + escapeHtml(row.stage) + '</span>' +
        '<span class="ai-docs-progress-doc-pct">' + pct + '%</span>' +
        '<div class="ai-docs-progress-doc-bar"><span style="width:' + pct + '%"></span></div>' +
        '</div>';
    }).join('');
  }

  function renderBannerState(opts) {
    opts = opts || {};
    if (!opts.preserveHideTimer && !isJobTerminalDisplay() && !opts.terminalComplete) {
      clearBannerHideTimer();
    }
    var title = opts.title || '';
    var overallText = opts.overallText || '';
    var detailText = opts.detailText || '';
    var pct = clampPercent(opts.percent || 0);
    var docRows = opts.docRows || [];
    var singleDoc = !!opts.singleDocMode;
    var showDocList = !singleDoc && docRows.length > 0;
    var docListExpanded = !!opts.docListExpanded;
    var docListHtml = showDocList && docListExpanded ? renderDocListHtml(docRows) : '';
    var t = state.t;

    if (state.bannerUI && state.bannerUI.exists && state.bannerUI.exists()) {
      state.bannerUI.update({
        title: title,
        detail: singleDoc ? detailText : overallText,
        progress: pct,
        showPercent: true,
        percentText: pct + '%',
      });
      if (opts.showCancel) state.bannerUI.setCancelVisible(true);
      if (opts.hideCancel) state.bannerUI.setCancelVisible(false);
      if (typeof opts.showSpinner === 'boolean') {
        state.bannerUI.setSpinnerVisible(opts.showSpinner);
      } else if (isJobTerminalDisplay() || opts.terminalComplete) {
        state.bannerUI.setSpinnerVisible(false);
      }
    }

    var b = state.bannerEls;
    if (b.banner) b.banner.classList.remove('hidden');
    if (b.title) b.title.textContent = title;
    if (b.overall) {
      if (singleDoc || !overallText) {
        b.overall.textContent = '';
        b.overall.classList.add('hidden');
      } else {
        b.overall.textContent = overallText;
        b.overall.classList.remove('hidden');
      }
    }
    if (b.detail) {
      if (singleDoc) {
        b.detail.textContent = detailText;
        b.detail.classList.toggle('hidden', !detailText);
      } else {
        b.detail.textContent = overallText;
        b.detail.classList.add('hidden');
      }
    }
    if (b.percent) b.percent.textContent = pct + '%';
    if (b.bar) b.bar.style.width = pct + '%';
    var showSpinner = opts.showSpinner;
    if (showSpinner === undefined) {
      showSpinner = !(isJobTerminalDisplay() || opts.terminalComplete);
    }
    if (b.spinner) b.spinner.classList.toggle('hidden', !showSpinner);
    if (opts.showCancel && b.cancelWrap) b.cancelWrap.classList.remove('hidden');
    if (opts.hideCancel && b.cancelWrap) b.cancelWrap.classList.add('hidden');

    var toggleEl = state.bannerEls.docListToggle;
    if (toggleEl) {
      if (showDocList) {
        toggleEl.textContent = docListToggleLabel(docListExpanded, docRows.length, t);
        toggleEl.setAttribute('aria-expanded', docListExpanded ? 'true' : 'false');
        toggleEl.classList.remove('hidden');
      } else {
        toggleEl.classList.add('hidden');
      }
    }

    var listEl = state.bannerEls.docList;
    if (listEl) {
      if (docListHtml) {
        listEl.innerHTML = docListHtml;
        listEl.classList.remove('hidden');
      } else {
        listEl.innerHTML = '';
        listEl.classList.add('hidden');
      }
    }
  }

  function showBanner(title, detail, progress, opts) {
    opts = opts || {};
    renderBannerState({
      title: title,
      overallText: detail,
      percent: progress,
      docRows: opts.docRows || [],
      showCancel: opts.showCancel,
      hideCancel: opts.hideCancel,
    });
  }

  function hideBanner() {
    if (state.hideTimer) {
      clearTimeout(state.hideTimer);
      state.hideTimer = null;
    }
    if (state.bannerEls.docList) {
      state.bannerEls.docList.innerHTML = '';
      state.bannerEls.docList.classList.add('hidden');
    }
    if (state.bannerEls.docListToggle) {
      state.bannerEls.docListToggle.classList.add('hidden');
    }
    if (state.bannerUI && state.bannerUI.hide) {
      state.bannerUI.hide();
      if (state.bannerUI.setSpinnerVisible) state.bannerUI.setSpinnerVisible(true);
      return;
    }
    if (state.bannerEls.banner) state.bannerEls.banner.classList.add('hidden');
    if (state.bannerEls.cancelWrap) state.bannerEls.cancelWrap.classList.add('hidden');
    if (state.bannerEls.spinner) state.bannerEls.spinner.classList.remove('hidden');
  }

  function jobDoneCount(counts) {
    counts = counts || {};
    return (Number(counts.completed) || 0) + (Number(counts.failed) || 0) + (Number(counts.cancelled) || 0);
  }

  function computeJobProgress(job, items, trackedDocs) {
    var total = Number(job && job.total_items) || 0;
    if (total <= 0) return { percent: 0, done: 0, total: 0, inFlight: 0, counts: {} };

    var counts = (job && job.counts) || {};
    var terminal = jobDoneCount(counts);
    var inFlight = Number(counts.in_progress) || 0;
    var partial = 0;

    if (Array.isArray(items)) {
      items.forEach(function (it) {
        var st = itemImportStatus(it);
        if (isTerminalItemStatus(st)) return;
        var docId = resolveItemDocId(it);
        if (docId != null && trackedDocs.has(Number(docId))) {
          partial += (trackedDocs.get(Number(docId)).progress || 0) / 100;
        } else if (st === 'downloading') {
          partial += 0.15;
        } else if (st === 'processing' || st === 'queued') {
          partial += 0.05;
        }
      });
    } else {
      partial = inFlight * 0.1;
    }

    var effective = Math.min(total, terminal + partial);
    return {
      percent: clampPercent((effective / total) * 100),
      done: Math.min(total, terminal),
      total: total,
      inFlight: inFlight,
      counts: counts,
    };
  }

  function jobTitle(spec, t) {
    if (spec && spec.metadataOnly) return t.reprocessing_metadata_e6c7cf5c;
    if (spec && spec.titleImport) return t.importing_documents_8a49fe5a;
    return t.reprocessing_documents_d4993939;
  }

  function renderFromState() {
    var t = state.t;
    var job = state.activeJob;

    if (job && !state.standaloneMode) {
      var spec = getSpec(job.jobType);
      var prog = computeJobProgress(job.snapshot, job.items, state.trackedDocs);
      var title = jobTitle(spec, t);
      var overallText = prog.done + '/' + prog.total;
      var docRows = filterInFlightDocRows(buildDocRowsFromJob(job, state.trackedDocs, t));
      var singleDoc = isSingleDocContext(job, prog.total);

      if (TERMINAL_JOB_STATUSES.indexOf(String(job.status || '')) >= 0) {
        if (job.status === 'cancelled') {
          title = spec && spec.titleImport ? t.import_cancelled_2a8b4482 : t.reprocess_cancelled_97d2acd3;
        } else if (spec && spec.metadataOnly) {
          title = t.metadata_reprocess_complete_87ff8292;
        } else if (spec && spec.titleImport) {
          title = t.import_complete_a218495a;
        } else {
          title = t.reprocess_complete_f1001d0e;
        }
        overallText = singleDoc ? '' : (prog.done + '/' + prog.total);
        if ((Number(prog.counts.failed) || 0) > 0) {
          overallText += singleDoc ? '' : (' · ' + t.some_documents_failed_2221bc0e);
        }
        renderBannerState({
          title: title,
          overallText: overallText,
          detailText: singleDoc ? (t.done_f92965e2 || 'Done') : '',
          singleDocMode: singleDoc,
          percent: 100,
          docRows: docRows,
          docListExpanded: state.docListExpanded,
          hideCancel: true,
          terminalComplete: true,
          showSpinner: false,
        });
        return;
      }

      renderBannerState({
        title: title,
        overallText: singleDoc ? '' : overallText,
        detailText: singleDoc ? resolveSingleDocStage(job, state.trackedDocs, t) : '',
        singleDocMode: singleDoc,
        percent: prog.percent,
        docRows: docRows,
        docListExpanded: state.docListExpanded,
        showCancel: job.status === 'running' || job.status === 'queued' || job.status === 'cancel_requested',
      });
      return;
    }

    var allDocRows = buildDocRowsFromTracked(state.trackedDocs);
    if (!allDocRows.length) {
      hideBanner();
      return;
    }

    var docRows = filterInFlightDocRows(allDocRows);
    var singleDoc = isSingleDocContext(null, totalDocs);
    var doneDocs = allDocRows.filter(function (row) {
      return trackedDocCountsAsDone(row);
    }).length;
    var failedDocs = allDocRows.filter(function (row) { return row.status === 'failed'; }).length;
    var totalDocs = allDocRows.length;
    var overallText = doneDocs + '/' + totalDocs;
    var inProg = allDocRows.find(function (row) { return TERMINAL_DOC_STATUSES.indexOf(row.status) < 0; });
    var perDocPct = totalDocs === 1 && inProg
      ? clampPercent(inProg.progress || 0)
      : clampPercent(totalDocs > 0 ? (doneDocs / totalDocs) * 100 : 0);

    if (doneDocs >= totalDocs) {
      renderBannerState({
        title: failedDocs > 0 ? t.processing_finished_1b8f5c57 : t.processing_complete_930a1b79,
        overallText: singleDoc ? '' : (overallText + (failedDocs > 0 ? (' · ' + failedDocs + ' ' + t.failed_26934eb3) : '')),
        detailText: singleDoc ? (failedDocs > 0 ? t.failed_d7c8c85b : (t.done_f92965e2 || 'Done')) : '',
        singleDocMode: singleDoc,
        percent: 100,
        docRows: docRows,
        docListExpanded: state.docListExpanded,
        hideCancel: true,
        terminalComplete: true,
        showSpinner: false,
      });
      if (!state.hideTimer) {
        state.hideTimer = setTimeout(function () {
          state.hideTimer = null;
          state.trackedDocs.clear();
          hideBanner();
        }, 1500);
      }
      return;
    }

    if (state.hideTimer) {
      clearTimeout(state.hideTimer);
      state.hideTimer = null;
    }

    renderBannerState({
      title: t.processing_documents_4c764ed2,
      overallText: singleDoc ? '' : overallText,
      detailText: singleDoc ? resolveSingleDocStage(null, state.trackedDocs, t) : '',
      singleDocMode: singleDoc,
      percent: perDocPct,
      docRows: docRows,
      docListExpanded: state.docListExpanded,
    });
  }

  async function fetchJobStatus(job) {
    var spec = getSpec(job.jobType);
    if (!spec || !job.jobId) return null;
    var url = spec.statusUrl(job.jobId, state.urls) + '?_=' + Date.now();
    var fetchImpl = state.fetchFn || window.apiFetch || fetch;
    if (fetchImpl === fetch) {
      var resp = await fetch(url, { credentials: 'same-origin', cache: 'no-store', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
      return resp.json();
    }
    return fetchImpl(url, { credentials: 'same-origin', cache: 'no-store', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
  }

  function persistActiveJob(job) {
    var spec = getSpec(job.jobType);
    if (!spec || !spec.storageKey) return;
    writeStorage(spec.storageKey, {
      jobId: job.jobId,
      jobType: job.jobType,
      total: Number(job.snapshot && job.snapshot.total_items) || job.total || 0,
      startedAt: job.startedAt || Date.now(),
    });
  }

  function clearPersistedJob(jobType) {
    var spec = getSpec(jobType);
    if (spec && spec.storageKey) clearStorage(spec.storageKey);
  }

  function finishJob(jobType) {
    var job = state.activeJob;
    if (!job || normalizeJobType(job.jobType) !== normalizeJobType(jobType)) return;
    if (job.finishHandled) return;
    job.finishHandled = true;

    stopMasterPoll();
    stopAllDocPolls();
    clearPersistedJob(jobType);
    renderFromState();
    if (state.hooks.onJobComplete) {
      try { state.hooks.onJobComplete(jobType, job); } catch (e) { /* ignore */ }
    }
    clearBannerHideTimer();
    state.hideTimer = setTimeout(function () {
      state.hideTimer = null;
      if (state.activeJob && normalizeJobType(state.activeJob.jobType) === normalizeJobType(jobType)) {
        state.activeJob = null;
      }
      hideBanner();
    }, 2500);
  }

  function applyJobPayload(jobType, payload) {
    if (!payload || !payload.success || !payload.job) return;
    var job = payload.job;
    var items = Array.isArray(payload.items) ? payload.items : [];
    var jobTerminal = TERMINAL_JOB_STATUSES.indexOf(String(job.status || '')) >= 0;
    state.activeJob = {
      jobId: String(job.id),
      jobType: jobType,
      status: job.status,
      total: Number(job.total_items) || 0,
      snapshot: job,
      items: items,
      startedAt: (state.activeJob && state.activeJob.startedAt) || Date.now(),
      finishHandled: !!(state.activeJob && state.activeJob.finishHandled),
    };
    state.standaloneMode = false;

    items.forEach(function (it) {
      var docId = resolveItemDocId(it);
      if (docId == null) return;
      var st = itemImportStatus(it);
      if (!jobTerminal && (st === 'downloading' || st === 'processing')) {
        trackDoc(docId, { silent: true });
        startDocPoll(docId);
      } else if (isTerminalItemStatus(st)) {
        syncTrackedDocFromJobItem(it, { silent: true });
      }
    });

    if (jobTerminal) {
      finishJob(jobType);
      return;
    }

    persistActiveJob(state.activeJob);
    renderFromState();
  }

  async function pollMaster() {
    if (!state.activeJob) return;
    var current = state.activeJob;
    try {
      var data = await fetchJobStatus(current);
      if (!data || !data.success || !data.job) {
        renderFromState();
        return;
      }
      applyJobPayload(current.jobType, data);
    } catch (e) {
      log('jobPollError', e && e.message ? e.message : e);
      renderFromState();
    }
  }

  function ensureMasterPoll() {
    if (state.masterTimer) return;
    pollMaster();
    state.masterTimer = setInterval(function () { pollMaster(); }, POLL_MS);
  }

  function stopMasterPoll() {
    if (state.masterTimer) {
      clearInterval(state.masterTimer);
      state.masterTimer = null;
    }
  }

  async function fetchDocStatus(docId) {
    var fetchImpl = (window.getFetch && window.getFetch()) || fetch;
    var response = await fetchImpl('/admin/ai/documents/' + docId + '/status?_=' + Date.now(), {
      credentials: 'same-origin',
      cache: 'no-store',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    });
    if (response.status === 404) {
      return { success: false, error: 'not_found', document: { id: docId }, stage: 'Not Found', progress: 100 };
    }
    try {
      return await response.json();
    } catch (e) {
      return { success: false, error: 'invalid_response', document: { id: docId }, stage: 'Error', progress: 0 };
    }
  }

  function updateDocEntry(docId, patch) {
    var id = Number(docId);
    if (!Number.isFinite(id)) return;
    var prev = state.trackedDocs.get(id) || {};
    var next = Object.assign({}, prev, patch || {}, { updatedAt: Date.now() });
    if (typeof next.progress === 'number') next.progress = clampPercent(next.progress);
    state.trackedDocs.set(id, next);
    if (!patch || !patch.silent) renderFromState();
  }

  function trackDoc(docId, opts) {
    opts = opts || {};
    var id = Number(docId);
    if (!Number.isFinite(id)) return;
    if (!state.trackedDocs.has(id)) {
      state.trackedDocs.set(id, {
        status: 'pending',
        stage: state.t.preparing_0862f67f,
        progress: 0,
        error: '',
        updatedAt: Date.now(),
        reprocessRequestedAt: null,
        seenNonCompletedSinceRequest: false,
      });
    }
    if (!opts.silent) renderFromState();
  }

  function stopDocPoll(docId) {
    var key = String(docId);
    var timer = state.docPollers.get(key);
    if (timer) {
      clearInterval(timer);
      state.docPollers.delete(key);
    }
  }

  function startDocPoll(docId) {
    var key = String(docId);
    if (state.docPollers.has(key)) return;
    trackDoc(docId, { silent: true });

    var poll = async function () {
      try {
        var jobItem = resolveJobItemForDoc(docId);
        if (jobItem && isTerminalItemStatus(itemImportStatus(jobItem))) {
          syncTrackedDocFromJobItem(jobItem, { silent: true });
          renderFromState();
          return;
        }

        var data = await fetchDocStatus(docId);
        if (!data.success) {
          if (data.error === 'not_found') {
            stopDocPoll(key);
            updateDocEntry(docId, { status: 'not_found', stage: 'Not Found', progress: 100 });
            if (state.hooks.onDocRemove) state.hooks.onDocRemove(docId);
          }
          return;
        }

        var status = data.document.processing_status;
        var stage = data.stage || 'Processing';
        var progress = typeof data.progress === 'number' ? data.progress : 0;

        if (status === 'processing' || status === 'pending') {
          updateDocEntry(docId, {
            status: status,
            stage: stage,
            progress: progress,
            error: data.document.processing_error || '',
            seenNonCompletedSinceRequest: true,
          });
          if (state.hooks.onDocGridPatch) {
            state.hooks.onDocGridPatch(docId, {
              processing_status: status,
              processing_error: data.document.processing_error || '',
              total_chunks: data.document.total_chunks || 0,
            });
          }
        } else if (status === 'completed') {
          var tracked = state.trackedDocs.get(Number(docId));
          var requestedAt = tracked && tracked.reprocessRequestedAt;
          var seenNonCompleted = tracked && tracked.seenNonCompletedSinceRequest;
          if (requestedAt && !seenNonCompleted && (Date.now() - requestedAt) < 8000) {
            updateDocEntry(docId, { status: 'pending', stage: 'Starting...', progress: 0 });
          } else {
            updateDocEntry(docId, { status: 'completed', stage: 'Done', progress: 100, error: '' });
            if (state.hooks.onDocGridPatch) {
              state.hooks.onDocGridPatch(docId, {
                processing_status: 'completed',
                processing_error: '',
                total_chunks: data.document.total_chunks || 0,
              });
            }
            stopDocPoll(key);
            if (state.hooks.onDocRefresh) state.hooks.onDocRefresh(docId);
          }
        } else if (status === 'failed') {
          var errorMsg = data.document.processing_error || state.t.processing_failed_ad62fd55;
          updateDocEntry(docId, { status: 'failed', stage: 'Failed', progress: 100, error: errorMsg });
          if (state.hooks.onDocGridPatch) {
            state.hooks.onDocGridPatch(docId, {
              processing_status: 'failed',
              processing_error: errorMsg,
              total_chunks: data.document.total_chunks || 0,
            });
          }
          stopDocPoll(key);
          if (state.hooks.onDocRefresh) state.hooks.onDocRefresh(docId);
        }
      } catch (e) {
        console.error('Status polling error:', e);
      }
    };

    poll();
    state.docPollers.set(key, setInterval(poll, POLL_MS));
  }

  function startJob(jobType, jobId, total) {
    clearBannerHideTimer();
    state.standaloneMode = false;
    state.optimisticJob = false;
    state.docListExpanded = false;
    state.activeJob = {
      jobId: String(jobId),
      jobType: jobType,
      status: 'running',
      total: Number(total) || 0,
      snapshot: {
        total_items: Number(total) || 0,
        counts: { completed: 0, failed: 0, cancelled: 0, in_progress: Number(total) || 0 },
      },
      items: [],
      startedAt: Date.now(),
    };
    persistActiveJob(state.activeJob);
    ensureMasterPoll();
    renderFromState();
  }

  function resumeStoredJobs(activeFromServer) {
    var serverJobs = Array.isArray(activeFromServer) ? activeFromServer : [];
    if (serverJobs.length) {
      var first = serverJobs[0];
      startJob(first.job_type || first.jobType, first.job_id, first.total_items || first.total || 0);
      return;
    }

    Object.keys(JOB_SPECS).some(function (key) {
      var spec = JOB_SPECS[key];
      var stored = readStorage(spec.storageKey);
      if (!stored || !(stored.jobId || stored.job_id)) return false;
      var jobType = stored.jobType;
      if (!jobType) {
        if (key === 'docs_b_bulk_import_system') jobType = 'docs.bulk_import_system';
        else if (key === 'docs_bulk_reprocess') jobType = 'docs.bulk_reprocess';
        else if (key === 'docs_bulk_reprocess_metadata') jobType = 'docs.bulk_reprocess_metadata';
        else jobType = key;
      }
      startJob(jobType, stored.jobId || stored.job_id, stored.total || 0);
      return true;
    });
  }

  function clearAll() {
    stopMasterPoll();
    state.docPollers.forEach(function (timer) { clearInterval(timer); });
    state.docPollers.clear();
    state.trackedDocs.clear();
    state.activeJob = null;
    state.standaloneMode = false;
    state.docListExpanded = false;
    hideBanner();
  }

  async function cancelActiveJob() {
    var job = state.activeJob;
    if (!job) return;
    var spec = getSpec(job.jobType);
    if (!spec) return;
    showBanner(state.t.cancelling_ef5ba1f8, '', 0, { hideCancel: true });
    try {
      var url = spec.cancelUrl(job.jobId, state.urls);
      var fetchImpl = state.csrfFetchFn || fetch;
      await fetchImpl(url, { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
    } catch (e) { /* ignore */ }
    clearPersistedJob(job.jobType);
    stopMasterPoll();
    state.activeJob = null;
    clearAll();
  }

  function init(options) {
    options = options || {};
    state.cfg = options.cfg || window.aiDocumentsConfig || {};
    state.t = state.cfg.t || {};
    state.urls = state.cfg.urls || {};
    state.debug = !!(state.cfg.debug);
    state.hooks = options.hooks || {};
    state.fetchFn = options.fetchFn || null;
    state.csrfFetchFn = options.csrfFetchFn || null;

    if (window.FloatingProgressBanner && typeof window.FloatingProgressBanner.fromIds === 'function') {
      state.bannerUI = window.FloatingProgressBanner.fromIds({
        bannerId: 'processingStatusBanner',
        titleId: 'processingStatusTitle',
        detailId: 'processingStatusDetail',
        percentId: 'processingStatusPercent',
        barId: 'processingStatusBar',
        spinnerId: 'processingStatusSpinner',
        cancelWrapId: 'processingStatusCancelWrap',
        cancelBtnId: 'processingStatusCancelBtn',
      });
    }
    state.bannerEls = {
      banner: document.getElementById('processingStatusBanner'),
      title: document.getElementById('processingStatusTitle'),
      detail: document.getElementById('processingStatusDetail'),
      overall: document.getElementById('processingStatusOverall'),
      docList: document.getElementById('processingStatusDocList'),
      docListToggle: document.getElementById('processingStatusDocListToggle'),
      percent: document.getElementById('processingStatusPercent'),
      bar: document.getElementById('processingStatusBar'),
      spinner: document.getElementById('processingStatusSpinner'),
      cancelWrap: document.getElementById('processingStatusCancelWrap'),
      cancelBtn: document.getElementById('processingStatusCancelBtn'),
    };

    var cancelBtn = state.bannerEls.cancelBtn;
    if (cancelBtn && !cancelBtn.dataset.aiDocsProgressBound) {
      cancelBtn.dataset.aiDocsProgressBound = '1';
      cancelBtn.addEventListener('click', function () {
        if (state.activeJob) cancelActiveJob();
      });
    }

    var docListToggle = state.bannerEls.docListToggle;
    if (docListToggle && !docListToggle.dataset.aiDocsProgressBound) {
      docListToggle.dataset.aiDocsProgressBound = '1';
      docListToggle.addEventListener('click', function () {
        state.docListExpanded = !state.docListExpanded;
        renderFromState();
      });
    }

    var activeFromServer = options.activeJobs || readJsonScript('ai-documents-active-jobs', []);
    resumeStoredJobs(activeFromServer);

    if (!state.activeJob) {
      var processingIds = options.processingDocIds || readJsonScript('ai-documents-processing-ids', []);
      processingIds.forEach(function (docId) { startDocPoll(docId); });
      if (processingIds.length) {
        state.standaloneMode = true;
        renderFromState();
      }
    }
  }

  window.AiDocsJobProgress = {
    init: init,
    startJob: startJob,
    beginOptimisticJob: beginOptimisticJob,
    activateJob: activateJob,
    failOptimisticJob: failOptimisticJob,
    trackDoc: trackDoc,
    updateDoc: updateDocEntry,
    startDocPoll: startDocPoll,
    stopDocPoll: stopDocPoll,
    showBanner: showBanner,
    hideBanner: hideBanner,
    render: renderFromState,
    clearAll: clearAll,
    hasActiveJob: function () { return !!state.activeJob; },
    setStandaloneMode: function (flag) { state.standaloneMode = !!flag; },
    getDocState: function (docId) {
      var id = Number(docId);
      return Number.isFinite(id) ? (state.trackedDocs.get(id) || null) : null;
    },
  };
})();
