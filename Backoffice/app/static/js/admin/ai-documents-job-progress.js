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
  };

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

  function showBanner(title, detail, progress, opts) {
    opts = opts || {};
    var pct = clampPercent(progress);
    if (state.bannerUI && state.bannerUI.exists && state.bannerUI.exists()) {
      state.bannerUI.update({
        title: title,
        detail: detail,
        progress: pct,
        showPercent: true,
        percentText: pct + '%',
      });
      if (opts.showCancel) state.bannerUI.setCancelVisible(true);
      if (opts.hideCancel) state.bannerUI.setCancelVisible(false);
      return;
    }
    var b = state.bannerEls;
    if (!b.banner) return;
    b.banner.classList.remove('hidden');
    if (b.title) b.title.textContent = title || '';
    if (b.detail) b.detail.textContent = detail || '';
    if (b.percent) b.percent.textContent = pct + '%';
    if (b.bar) b.bar.style.width = pct + '%';
    if (opts.showCancel && b.cancelWrap) b.cancelWrap.classList.remove('hidden');
    if (opts.hideCancel && b.cancelWrap) b.cancelWrap.classList.add('hidden');
  }

  function hideBanner() {
    if (state.hideTimer) {
      clearTimeout(state.hideTimer);
      state.hideTimer = null;
    }
    if (state.bannerUI && state.bannerUI.hide) {
      state.bannerUI.hide();
      return;
    }
    if (state.bannerEls.banner) state.bannerEls.banner.classList.add('hidden');
    if (state.bannerEls.cancelWrap) state.bannerEls.cancelWrap.classList.add('hidden');
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
        var st = it.import_status || it.status;
        if (st === 'completed' || st === 'failed' || st === 'cancelled') return;
        var docId = it.ai_document_id || (it.document && it.document.id);
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
      var current = Math.min(prog.total, prog.done + (prog.inFlight > 0 ? 1 : 0));
      var title = jobTitle(spec, t) + ' (' + current + '/' + prog.total + ')';

      var entries = Array.from(state.trackedDocs.entries()).map(function (pair) {
        return { id: pair[0], data: pair[1] || {} };
      });
      entries.sort(function (a, b) { return (b.data.updatedAt || 0) - (a.data.updatedAt || 0); });
      var focus = entries.find(function (x) { return TERMINAL_DOC_STATUSES.indexOf(x.data.status) < 0; }) || entries[0];

      var detail;
      if (focus && focus.data) {
        detail = '#' + focus.id + ' • ' + t.stage_5f483ab8 + ' ' + (focus.data.stage || t.preparing_0862f67f) + ' • ' + clampPercent(focus.data.progress || 0) + '%';
      } else if (prog.inFlight > 0 && prog.done === 0) {
        detail = '0/' + prog.total + ' ' + t.starting_8c6ce9f8;
      } else if (prog.inFlight > 0) {
        detail = prog.done + '/' + prog.total + ' – ' + t.working_9c8a77ee;
      } else {
        detail = prog.done + '/' + prog.total;
      }

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
        detail = (Number(prog.counts.failed) || 0) > 0 ? t.some_documents_failed_2221bc0e : t.done_f92965e2;
        showBanner(title, detail, 100, { hideCancel: true });
        return;
      }

      showBanner(title, detail, prog.percent, {
        showCancel: job.status === 'running' || job.status === 'queued' || job.status === 'cancel_requested',
      });
      return;
    }

    var docEntries = Array.from(state.trackedDocs.entries()).map(function (pair) {
      return { id: pair[0], data: pair[1] || {} };
    });
    if (!docEntries.length) {
      hideBanner();
      return;
    }

    var doneDocs = docEntries.filter(function (x) { return TERMINAL_DOC_STATUSES.indexOf(x.data.status) >= 0; }).length;
    var failedDocs = docEntries.filter(function (x) { return x.data.status === 'failed'; }).length;
    var inProg = docEntries.find(function (x) { return TERMINAL_DOC_STATUSES.indexOf(x.data.status) < 0; }) || docEntries[0];
    var totalDocs = docEntries.length;

    if (doneDocs >= totalDocs) {
      showBanner(
        failedDocs > 0 ? t.processing_finished_1b8f5c57 : t.processing_complete_930a1b79,
        failedDocs > 0 ? t.some_documents_failed_aaa3128a + ' (' + failedDocs + '/' + totalDocs + ')' : t.done_f5940523,
        100,
        { hideCancel: true }
      );
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

    var displayCurrent = Math.min(doneDocs + (inProg ? 1 : 0), totalDocs);
    var perDocPct = totalDocs === 1 && inProg
      ? clampPercent(inProg.data.progress || 0)
      : clampPercent(totalDocs > 0 ? (doneDocs / totalDocs) * 100 : 0);
    var detailLine = inProg
      ? '#' + inProg.id + ' • ' + t.stage_5f483ab8 + ' ' + (inProg.data.stage || t.preparing_0862f67f) + ' • ' + clampPercent(inProg.data.progress || 0) + '%'
      : t.working_9c8a77ee;
    showBanner(t.processing_documents_4c764ed2 + ' (' + displayCurrent + '/' + totalDocs + ')', detailLine, perDocPct);
  }

  async function fetchJobStatus(job) {
    var spec = getSpec(job.jobType);
    if (!spec) return null;
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
    renderFromState();
    clearPersistedJob(jobType);
    if (state.hooks.onJobComplete) {
      try { state.hooks.onJobComplete(jobType, state.activeJob); } catch (e) { /* ignore */ }
    }
    state.hideTimer = setTimeout(function () {
      state.hideTimer = null;
      if (state.activeJob && state.activeJob.jobType === jobType) {
        state.activeJob = null;
      }
      hideBanner();
    }, 2500);
  }

  function applyJobPayload(jobType, payload) {
    if (!payload || !payload.success || !payload.job) return;
    var job = payload.job;
    var items = Array.isArray(payload.items) ? payload.items : [];
    state.activeJob = {
      jobId: String(job.id),
      jobType: jobType,
      status: job.status,
      total: Number(job.total_items) || 0,
      snapshot: job,
      items: items,
      startedAt: (state.activeJob && state.activeJob.startedAt) || Date.now(),
    };
    state.standaloneMode = false;

    items.forEach(function (it) {
      var docId = it.ai_document_id;
      if (docId == null && it.document && it.document.id != null) docId = it.document.id;
      if (docId == null || !Number.isFinite(Number(docId))) return;
      trackDoc(Number(docId), { silent: true });
      startDocPoll(Number(docId));
    });

    if (TERMINAL_JOB_STATUSES.indexOf(String(job.status || '')) >= 0) {
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
    state.standaloneMode = false;
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
    showBanner(state.t.starting_import_b06c80dc, state.t.resuming_09136a9d, 0, { showCancel: true });
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
        cancelWrapId: 'processingStatusCancelWrap',
        cancelBtnId: 'processingStatusCancelBtn',
      });
    }
    state.bannerEls = {
      banner: document.getElementById('processingStatusBanner'),
      title: document.getElementById('processingStatusTitle'),
      detail: document.getElementById('processingStatusDetail'),
      percent: document.getElementById('processingStatusPercent'),
      bar: document.getElementById('processingStatusBar'),
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
