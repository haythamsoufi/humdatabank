(function() {
'use strict';
var cfg = window.aiDocumentsConfig || {};

function importSystemBulkUrl(suffix, jobId) {
    const urls = (cfg.urls || {});
    const tpl = suffix === 'status'
        ? urls.importSystemBulkStatus
        : (suffix === 'cancel' ? urls.importSystemBulkCancel : urls.importSystemBulk);
    if (tpl && jobId) {
        return String(tpl).replace('__JOB__', encodeURIComponent(String(jobId)));
    }
    return tpl || ('/admin/ai/documents/import-system-bulk' + (suffix && jobId ? '/' + encodeURIComponent(String(jobId)) + '/' + suffix : ''));
}
// Included by admin/ai/documents.html. Single source of truth for the documents grid and all AI documents page JS.
// AG Grid helper instance
let documentsGridHelper = null;
let documentsGridApi = null;

// Resume polling for in-flight documents (lightweight id list from SSR).
const processingDocIdsFromPage = (function() {
    var el = document.getElementById('ai-documents-processing-ids');
    if (!el) return [];
    try {
        var parsed = JSON.parse(el.textContent || '[]');
        return Array.isArray(parsed) ? parsed : [];
    } catch (e) {
        return [];
    }
})();

// Helper function to get file icon HTML
function getFileIcon(fileType) {
    const iconMap = {
        'pdf': '<i class="fas fa-file-pdf text-red-500 text-xl"></i>',
        'docx': '<i class="fas fa-file-word text-blue-500 text-xl"></i>',
        'doc': '<i class="fas fa-file-word text-blue-500 text-xl"></i>',
        'xlsx': '<i class="fas fa-file-excel text-green-500 text-xl"></i>',
        'xls': '<i class="fas fa-file-excel text-green-500 text-xl"></i>',
        'md': '<i class="fab fa-markdown text-gray-600 text-xl"></i>'
    };
    return iconMap[fileType] || '<i class="fas fa-file-alt text-gray-500 text-xl"></i>';
}

// Helper function to get status badge HTML
function getStatusBadge(status, error) {
    const variantMap = {
        completed: 'success',
        pending: 'pending',
        processing: 'active',
        failed: 'danger',
    };
    const textMap = {
        completed: cfg.t.completed_07ca5050,
        pending: cfg.t.pending_2d13df6f,
        processing: cfg.t.processing_643562a9,
        failed: cfg.t.failed_d7c8c85b,
    };
    const key = status || 'failed';
    const variant = variantMap[key] || 'danger';
    const text = textMap[key] || textMap.failed;
    const titleAttr = error ? ' title="' + escapeAttr(error) + '"' : '';
    if (window.StatusLabels) {
        return window.StatusLabels.render(text, variant).replace('<span ', '<span' + titleAttr + ' ');
    }
    return '<span class="status-label status-label--' + variant + '"' + titleAttr + '>' + text + '</span>';
}

// Document category taxonomy (must match ai_metadata_extractor.DOCUMENT_CATEGORIES / CATEGORY_LABELS)
const DOCUMENT_CATEGORY_OPTIONS = [
    { value: '',               label: cfg.t.none_49bd59b9 },
    { value: 'country_plan',   label: cfg.t.country_plan_137beb42 },
    { value: 'country_report', label: cfg.t.country_report_6316677c },
    { value: 'strategic_plan', label: cfg.t.strategic_plan_13a00ea1 },
    { value: 'work_plan',      label: cfg.t.work_plan_2a21b46b },
    { value: 'plan',           label: cfg.t.plan_0b6cbdf7 },
    { value: 'sitrep',         label: cfg.t.situation_report_eb2802e8 },
    { value: 'report',         label: cfg.t.report_4b1b4dc8 },
    { value: 'assessment',     label: cfg.t.assessment_29a99298 },
    { value: 'policy',         label: cfg.t.policy_51359e8b },
    { value: 'guideline',      label: cfg.t.guideline_a3928106 },
    { value: 'resolution',     label: cfg.t.resolution_b5a4b64b },
    { value: 'data_sheet',     label: cfg.t.data_sheet_063b405d },
    { value: 'training',       label: cfg.t.training_cf270e40 },
    { value: 'other',          label: cfg.t.other_6311ae17 },
];

function getCategoryLabel(value) {
    if (!value) return '';
    const opt = DOCUMENT_CATEGORY_OPTIONS.find(function(o) { return o.value === value; });
    return opt ? opt.label : value.replace(/_/g, ' ');
}

// Processing status — server-backed jobs via ai-documents-job-progress.js
var jobProgress = window.AiDocsJobProgress;
const AI_DOCS_DEBUG = !!(cfg.debug);
function aiDocsLog() {
    if (!AI_DOCS_DEBUG) return;
    try {
        window.__clientLog && window.__clientLog.apply(null, ['[AI Docs]'].concat(Array.from(arguments)));
    } catch (e) { /* ignore */ }
}


var processingCancelWrap = document.getElementById('processingStatusCancelWrap');

function showProcessingBanner(title, detail, progress) {
    if (jobProgress && jobProgress.setStandaloneMode) jobProgress.setStandaloneMode(true);
    if (jobProgress && jobProgress.showBanner) jobProgress.showBanner(title, detail, progress);
}

function hideProcessingBanner() {
    if (jobProgress && jobProgress.hideBanner) jobProgress.hideBanner();
}

function trackProcessingDoc(docId) {
    if (jobProgress && jobProgress.trackDoc) jobProgress.trackDoc(docId);
}

function updateTrackedProcessingDoc(docId, patch) {
    if (jobProgress && jobProgress.updateDoc) jobProgress.updateDoc(docId, patch);
}

function clearTrackedProcessing() {
    if (jobProgress && jobProgress.clearAll) jobProgress.clearAll();
}

function startProcessingPoll(docId) {
    if (jobProgress && jobProgress.startDocPoll) jobProgress.startDocPoll(docId);
}

function stopProcessingPoll(docId) {
    if (jobProgress && jobProgress.stopDocPoll) jobProgress.stopDocPoll(docId);
}

function startIfrcImportJobPolling(jobId, total) {
    if (jobProgress && jobProgress.startJob) jobProgress.startJob('ifrc_api_bulk', jobId, total || 0);
}

function startSystemImportJobPolling(jobId, total) {
    if (jobProgress && jobProgress.startJob) jobProgress.startJob('docs.bulk_import_system', jobId, total || 0);
}

function startBulkReprocessJobPolling(jobId, total) {
    if (jobProgress && jobProgress.activateJob) {
        jobProgress.activateJob(jobId, 'docs.bulk_reprocess', total || 0);
        return;
    }
    if (jobProgress && jobProgress.startJob) jobProgress.startJob('docs.bulk_reprocess', jobId, total || 0);
}

function beginBulkReprocessJob(total, docIds, requestTs) {
    if (jobProgress && jobProgress.beginOptimisticJob) {
        jobProgress.beginOptimisticJob('docs.bulk_reprocess', total || 0, docIds || [], { requestTs: requestTs || null });
    }
}

function failBulkReprocessJob(docIds, errorMsg) {
    if (jobProgress && jobProgress.failOptimisticJob) jobProgress.failOptimisticJob(docIds || [], errorMsg || '');
}

function startBulkMetaReprocessJobPolling(jobId, total) {
    if (jobProgress && jobProgress.startJob) jobProgress.startJob('docs.bulk_reprocess_metadata', jobId, total || 0);
}

function registerAiDocsJobSpecs() {
    if (!jobProgress || typeof jobProgress.registerJobSpec !== 'function') return;
    jobProgress.registerJobSpec('ifrc_api_bulk', {
        storageKey: 'ai_docs_external_api_import_job',
        statusUrl: function (jobId) {
            return '/api/ai/documents/ifrc-api/import-bulk/' + encodeURIComponent(jobId) + '/status';
        },
        cancelUrl: function (jobId) {
            return '/api/ai/documents/ifrc-api/import-bulk/' + encodeURIComponent(jobId) + '/cancel';
        },
        titleImport: true,
    });
    jobProgress.registerJobSpec('docs_b_bulk_import_system', {
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
    });
    jobProgress.registerJobSpec('docs_bulk_reprocess', {
        storageKey: 'ai_docs_bulk_reprocess_job',
        statusUrl: function (jobId) {
            return '/admin/ai/documents/bulk-reprocess/' + encodeURIComponent(jobId) + '/status';
        },
        cancelUrl: function (jobId) {
            return '/admin/ai/documents/bulk-reprocess/' + encodeURIComponent(jobId) + '/cancel';
        },
        titleImport: false,
    });
    jobProgress.registerJobSpec('docs_bulk_reprocess_metadata', {
        storageKey: 'ai_docs_bulk_reprocess_metadata_job',
        statusUrl: function (jobId) {
            return '/admin/ai/documents/bulk-reprocess-metadata/' + encodeURIComponent(jobId) + '/status';
        },
        cancelUrl: function (jobId) {
            return '/admin/ai/documents/bulk-reprocess-metadata/' + encodeURIComponent(jobId) + '/cancel';
        },
        titleImport: false,
        metadataOnly: true,
    });
}

function initAiDocsJobProgress() {
    if (!jobProgress || typeof jobProgress.init !== 'function') return;
    registerAiDocsJobSpecs();
    jobProgress.init({
        cfg: cfg,
        csrfFetchFn: (typeof csrfFetch === 'function') ? csrfFetch : null,
        fetchFn: window.apiFetch || null,
        hooks: {
            onDocGridPatch: function (docId, patch) { updateDocumentInGrid(docId, patch); },
            onDocRefresh: function (docId) { void refreshAiDocumentGridRowFromApi(docId); },
            onDocRemove: function (docId) { removeDocumentFromGrid(docId); },
            onJobComplete: function (jobType) {
                setTimeout(function () {
                    try { reloadDocumentsGrid(); } catch (e) { /* ignore */ }
                    if (jobType === 'ifrc_api_bulk') {
                        try { loadIfrcApiDocuments(); } catch (e2) { /* ignore */ }
                    }
                }, 800);
            },
        },
    });
}

function getRowNodeByDocId(docId) {
    if (!documentsGridApi) return null;
    let found = null;
    documentsGridApi.forEachNode((node) => {
        const nodeId = node?.data?.id;
        if (nodeId !== null && nodeId !== undefined && String(nodeId) === String(docId)) {
            found = node;
        }
    });
    return found;
}

function updateDocumentInGrid(docId, patch) {
    try {
        const node = getRowNodeByDocId(docId);
        if (!node) return false;
        const next = { ...(node.data || {}), ...(patch || {}) };
        node.setData(next);
        const cols = ['processing_status', 'total_chunks', 'is_public'];
        const p = patch || {};
        if (p.redetect_processing !== undefined || p.country_name !== undefined || p.country_iso3 !== undefined || p.geographic_scope !== undefined) {
            cols.push('country_name', 'geographic_scope');
        }
        if (p.document_date !== undefined || p.document_language !== undefined || p.source_organization !== undefined
            || p.document_category !== undefined || p.quality_score !== undefined) {
            cols.push('document_date', 'document_language', 'source_organization', 'document_category', 'quality_score');
        }
        documentsGridApi.refreshCells({
            rowNodes: [node],
            columns: cols,
            force: true
        });
        return true;
    } catch (e) {
        console.error('Failed updating grid row:', e);
        return false;
    }
}

function removeDocumentFromGrid(docId) {
    try {
        const node = getRowNodeByDocId(docId);
        if (!node) return false;
        documentsGridApi.applyTransaction({ remove: [node.data] });
        return true;
    } catch (e) {
        console.error('Failed removing grid row:', e);
        return false;
    }
}

/**
 * Map API document to grid row shape (same as server-rendered documentsData).
 */
function mapDocToGridRow(doc) {
    let countries = doc.countries || [];
    if (!Array.isArray(countries)) countries = [];
    countries = countries.map(function(c) {
        if (c && typeof c === 'object') {
            return { name: String(c.name || '').trim(), iso3: String(c.iso3 || '').trim() };
        }
        return { name: String(c || '').trim(), iso3: '' };
    });
    return {
        id: doc.id,
        title: doc.title || 'Untitled',
        filename: doc.filename || '',
        country_name: doc.country_name || '',
        country_iso3: doc.country_iso3 || '',
        geographic_scope: doc.geographic_scope || '',
        countries: countries,
        file_type: doc.file_type || '',
        processing_status: doc.processing_status || 'pending',
        processing_error: doc.processing_error || '',
        total_chunks: doc.total_chunks || 0,
        created_at: doc.created_at || null,
        is_public: doc.is_public || false,
        document_date: doc.document_date || null,
        document_language: doc.document_language || '',
        source_organization: doc.source_organization || '',
        document_category: doc.document_category || '',
        quality_score: (doc.quality_score !== null && doc.quality_score !== undefined) ? doc.quality_score : null
    };
}

/**
 * Reload one grid row from GET /api/ai/documents/:id so country/scope/metadata match the DB
 * after reprocess or metadata enrichment (status poll only returns processing fields).
 */
async function refreshAiDocumentGridRowFromApi(docId) {
    if (!documentsGridApi) return;
    try {
        const response = await ((window.getFetch && window.getFetch()) || fetch)('/api/ai/documents/' + encodeURIComponent(docId) + '?_=' + Date.now(), {
            credentials: 'same-origin',
            cache: 'no-store',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });
        if (!response.ok) return;
        const data = await response.json();
        if (!data.success || !data.document) return;
        const node = getRowNodeByDocId(docId);
        if (!node) return;
        const prev = node.data || {};
        const next = Object.assign({}, mapDocToGridRow(data.document), {
            redetect_processing: prev.redetect_processing === true
        });
        node.setData(next);
        documentsGridApi.refreshCells({ rowNodes: [node], force: true });
    } catch (e) {
        console.error('refreshAiDocumentGridRowFromApi failed:', e);
    }
}

/**
 * Read Knowledge Base URL filter params for API reloads (mirrors the GET filter form).
 */
function getDocumentsPageFilterParams() {
    const sp = new URLSearchParams(window.location.search);
    const out = new URLSearchParams();
    ['status', 'file_type', 'category', 'language', 'q'].forEach(function(key) {
        const v = (sp.get(key) || '').trim();
        if (v) out.set(key, v);
    });
    return out;
}

// Custom tooltip for Country/Scope when scope is Regional or Cluster (full country list on hover)
function CountryScopeTooltip() {}
CountryScopeTooltip.prototype.init = function(params) {
    const rawValue = params && params.value ? String(params.value) : '';
    const countries = rawValue
        .split('\n')
        .map(function(item) { return item.trim(); })
        .filter(Boolean);

    const container = document.createElement('div');
    container.style.maxWidth = '360px';
    container.style.padding = '8px 10px';
    container.style.background = '#111827';
    container.style.color = '#ffffff';
    container.style.borderRadius = '6px';
    container.style.boxShadow = '0 8px 18px rgba(0, 0, 0, 0.25)';
    container.style.fontSize = '12px';
    container.style.lineHeight = '1.4';

    if (countries.length === 0) {
        const empty = document.createElement('div');
        empty.textContent = cfg.t.no_countries_e1ba5c60;
        container.appendChild(empty);
        this.eGui = container;
        return;
    }

    const title = document.createElement('div');
    title.textContent = cfg.t.countries_790d59ef + ' (' + countries.length + ')';
    title.style.fontWeight = '600';
    title.style.marginBottom = '6px';
    container.appendChild(title);

    const list = document.createElement('ul');
    list.style.margin = '0';
    list.style.paddingLeft = '16px';
    list.style.maxHeight = '220px';
    list.style.overflowY = 'auto';

    countries.forEach(function(country) {
        const li = document.createElement('li');
        li.textContent = country;
        list.appendChild(li);
    });

    container.appendChild(list);
    this.eGui = container;
};
CountryScopeTooltip.prototype.getGui = function() {
    return this.eGui;
};

// Column definitions for ag-grid
const columnDefs = [
    {
        field: 'title',
        headerName: cfg.t.document_09453598,
        width: 350,
        minWidth: 250,
        maxWidth: 500,
        filter: 'agTextColumnFilter',
        sortable: true,
        cellRenderer: function(params) {
            const data = params.data;
            const icon = getFileIcon(data.file_type);
            const downloadUrl = '/api/ai/documents/' + data.id + '/download';
            const title = escapeHtml(data.title || 'Untitled');
            const filename = escapeHtml(data.filename || '');
            return '<div class="flex items-center" style="height: 100%; padding: 8px 0;">' +
                   '<div class="flex-shrink-0 h-12 w-12 flex items-center justify-center bg-gray-50 rounded-lg border border-gray-200 mr-3">' +
                   icon + '</div>' +
                   '<div><div class="text-sm font-semibold text-gray-900">' +
                   '<a href="' + downloadUrl + '" class="text-blue-600 hover:text-blue-800 hover:underline" download>' +
                   title + '</a></div>' +
                   '<div class="text-xs text-gray-500 mt-0.5">' + filename + '</div></div></div>';
        },
        cellStyle: { 'white-space': 'normal', 'line-height': '1.4', 'display': 'flex', 'align-items': 'center' }
    },
    {
        field: 'file_type',
        headerName: cfg.t.type_a1fa2777,
        width: 120,
        minWidth: 100,
        maxWidth: 150,
        filter: 'customSetFilter',
        sortable: true,
        cellRenderer: function(params) {
            const fileType = params.value || '';
            return '<span class="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium bg-gray-100 text-gray-700 uppercase">' +
                   fileType.toUpperCase() + '</span>';
        },
        cellStyle: { 'text-align': 'center' }
    },
    {
        field: 'country_name',
        headerName: cfg.t.country_scope_281f8863,
        width: 220,
        minWidth: 160,
        maxWidth: 360,
        filter: 'agTextColumnFilter',
        sortable: true,
        wrapText: true,
        autoHeight: true,
        tooltipComponent: 'countryScopeTooltip',
        tooltipValueGetter: function(params) {
            const data = params.data || {};
            const scope = String(data.geographic_scope || '').trim().toLowerCase();
            let countries = Array.isArray(data.countries) ? data.countries : [];
            if (!countries.length && data.country_name && (scope === 'regional' || scope === 'cluster')) {
                countries = String(data.country_name)
                    .split(',')
                    .map(function(name) { return { name: name.trim(), iso3: '' }; })
                    .filter(function(c) { return c.name; });
            }
            if ((scope !== 'regional' && scope !== 'cluster') || !countries.length) {
                return null;
            }
            return countries.map(function(c) {
                const name = c && c.name ? String(c.name).trim() : '';
                const iso3 = c && c.iso3 ? String(c.iso3).trim() : '';
                return iso3 ? (name + ' (' + iso3 + ')') : name;
            }).filter(Boolean).join('\n');
        },
        cellRenderer: function(params) {
            const data = params.data || {};
            if (data.redetect_processing) {
                return '<span class="inline-flex items-center gap-2 text-indigo-600 text-sm">' +
                    '<span class="animate-spin inline-block w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full" aria-hidden="true"></span>' +
                    '<span>' + cfg.t.redetecting_aa72bb32 + '</span></span>';
            }
            const scope = (data.geographic_scope || '').trim().toLowerCase();
            let countries = Array.isArray(data.countries) ? data.countries : [];
            if (!countries.length && data.country_name && (scope === 'regional' || scope === 'cluster')) {
                countries = String(data.country_name)
                    .split(',')
                    .map(function(name) { return { name: name.trim(), iso3: '' }; })
                    .filter(function(c) { return c.name; });
            }

            // Scope pills: FA webfont glyphs need explicit box + line-height. Use inline styles here so
            // alignment works even when Tailwind arbitrary classes (e.g. h-[1em]) are missing from output.css.
            const _scopeIcon = function(iconClass) {
                return '<span class="inline-flex shrink-0 items-center justify-center" style="width:1em;height:1em;line-height:1" aria-hidden="true">' +
                    '<i class="' + iconClass + '" style="display:block;line-height:1;font-size:0.95em"></i></span>';
            };
            const _scopePill = function(twColorClasses, iconClass, labelHtml) {
                return '<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ' + twColorClasses + '" style="line-height:1">' +
                    _scopeIcon(iconClass) + '<span style="line-height:1">' + labelHtml + '</span></span>';
            };
            const _countryNameWrap = 'white-space:normal;overflow-wrap:anywhere;word-break:break-word;min-width:0';

            // Global scope badge
            if (scope === 'global') {
                return _scopePill('bg-blue-100 text-blue-800', 'fas fa-globe', cfg.t.global_4cc6684d);
            }

            // Regional scope badge (no country list)
            if (scope === 'regional' && countries.length === 0) {
                return _scopePill('bg-purple-100 text-purple-800', 'fas fa-map', cfg.t.regional_9c1c6794);
            }

            // Regional with countries: badge only; full list on hover via tooltip
            if (scope === 'regional' && countries.length > 0) {
                return _scopePill('bg-purple-100 text-purple-800', 'fas fa-map', cfg.t.regional_9c1c6794);
            }

            // Cluster (multi-country / NS set, not a platform region label)
            // Note: theme maps `blue` and `teal` to the same palette — do not use teal here or Cluster matches Global.
            if (scope === 'cluster') {
                return _scopePill('bg-amber-100 text-amber-800', 'fas fa-layer-group', cfg.t.cluster_249694a4);
            }

            // No countries at all
            if (countries.length === 0) {
                const name = (params.value || '').trim();
                if (!name) {
                    return '<span class="text-xs text-gray-400">' + cfg.t.n_a_382b0f51 + '</span>';
                }
                const iso3 = (data.country_iso3 ? String(data.country_iso3).trim() : '');
                const suffix = iso3 ? ' <span class="text-xs text-gray-400">(' + escapeHtml(iso3) + ')</span>' : '';
                return '<span class="text-sm font-medium text-gray-900" style="' + _countryNameWrap + '">' + escapeHtml(name) + '</span>' + suffix;
            }

            // Single country
            if (countries.length === 1) {
                const c = countries[0];
                const iso = c.iso3 ? ' <span class="text-xs text-gray-400">(' + escapeHtml(c.iso3) + ')</span>' : '';
                return '<span class="text-sm font-medium text-gray-900" style="' + _countryNameWrap + '">' + escapeHtml(c.name || '') + '</span>' + iso;
            }

            // Multiple countries, non-regional (e.g. multi-country doc)
            const scopeBadge = '<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium bg-indigo-100 text-indigo-800 mr-1" style="line-height:1">' +
                '<span class="inline-flex shrink-0 items-center justify-center" style="width:1em;height:1em;line-height:1" aria-hidden="true">' +
                '<i class="fas fa-globe-americas" style="display:block;line-height:1;font-size:0.95em"></i></span>' +
                '<span style="line-height:1">' + countries.length + ' ' + cfg.t.countries_71bee43a + '</span></span>';
            const names = countries.map(function(c) { return c.name + (c.iso3 ? ' (' + c.iso3 + ')' : ''); }).join(', ');
            return scopeBadge + '<span class="text-xs text-gray-600" style="' + _countryNameWrap + '" title="' + escapeAttr(names) + '">' + escapeHtml(names) + '</span>';
        },
        valueGetter: function(params) {
            const data = params.data || {};
            const scope = (data.geographic_scope || '').trim().toLowerCase();
            const countries = Array.isArray(data.countries) ? data.countries : [];
            if (scope === 'global') return 'Global';
            if (scope === 'regional') return 'Regional';
            if (scope === 'cluster') return 'Cluster';
            if (countries.length > 1) return countries.map(function(c) { return c.name; }).join(', ');
            return data.country_name || '';
        },
        cellStyle: {
            'display': 'flex',
            'white-space': 'normal',
            'line-height': '1.4',
            'align-items': 'flex-start',
            'padding-top': '6px',
            'padding-bottom': '6px'
        }
    },
    {
        field: 'is_public',
        headerName: cfg.t.public_3d067bed,
        width: 100,
        minWidth: 90,
        maxWidth: 120,
        filter: 'agTextColumnFilter',
        sortable: true,
        cellRenderer: function(params) {
            const data = params.data;
            const isPublic = data && (data.is_public === true || data.is_public === 'true' || data.is_public === 1);
            const docId = data && data.id;
            const label = isPublic ? cfg.t.public_3d067bed : cfg.t.not_public_20257be8;
            const titleAttr = isPublic ? cfg.t.click_to_make_not_public_1466b6c5 : cfg.t.click_to_make_public_f00ad0b7;
            const btnClass = 'status-label status-label--' + (isPublic ? 'success' : 'neutral') +
                ' cursor-pointer hover:opacity-90 transition-opacity border-0';
            return '<button type="button" class="' + btnClass + '" data-ai-doc-action="toggle-public" data-doc-id="' + (docId || '') + '" data-is-public="' + (isPublic ? 'true' : 'false') + '" title="' + escapeAttr(titleAttr) + '">' +
                   label + '</button>';
        },
        valueGetter: function(params) {
            const v = params.data && params.data.is_public;
            return v === true || v === 'true' || v === 1;
        },
        filterValueGetter: function(params) {
            const v = params.data && params.data.is_public;
            const isPublic = v === true || v === 'true' || v === 1;
            return isPublic ? cfg.t.public_3d067bed : cfg.t.not_public_20257be8;
        },
        cellStyle: { 'text-align': 'center', 'white-space': 'nowrap' }
    },
    {
        field: 'processing_status',
        headerName: cfg.t.status_ec53a8c4,
        width: 150,
        minWidth: 120,
        maxWidth: 200,
        filter: 'customSetFilter',
        sortable: true,
        cellRenderer: function(params) {
            return getStatusBadge(params.value, params.data.processing_error);
        },
        cellStyle: { 'text-align': 'center', 'white-space': 'nowrap' }
    },
    {
        field: 'total_chunks',
        headerName: cfg.t.chunks_58fce280,
        width: 120,
        minWidth: 100,
        maxWidth: 150,
        filter: 'agNumberColumnFilter',
        sortable: true,
        cellRenderer: function(params) {
            return '<span class="text-sm font-medium text-gray-900">' + (params.value || 0) + '</span>';
        },
        cellStyle: { 'text-align': 'center' }
    },
    {
        field: 'created_at',
        headerName: cfg.t.created_0eceeb45,
        width: 180,
        minWidth: 150,
        maxWidth: 250,
        filter: 'agDateColumnFilter',
        sortable: true,
        cellRenderer: AgGridRenderers.dateTime,
        cellStyle: { 'white-space': 'nowrap' }
    },
    {
        field: 'document_date',
        headerName: cfg.t.doc_date_8c62d999,
        width: 140,
        minWidth: 110,
        maxWidth: 180,
        filter: 'agDateColumnFilter',
        sortable: true,
        cellRenderer: function(params) {
            const v = params.value;
            if (!v) return '<span class="text-xs text-gray-400">—</span>';
            return '<span class="text-sm text-gray-700">' + escapeHtml(v.substring(0, 10)) + '</span>';
        },
        cellStyle: { 'white-space': 'nowrap' }
    },
    {
        field: 'document_language',
        headerName: cfg.t.language_4994a8ff,
        width: 110,
        minWidth: 90,
        maxWidth: 140,
        filter: 'customSetFilter',
        sortable: true,
        cellRenderer: function(params) {
            const v = (params.value || '').toUpperCase();
            if (!v) return '<span class="text-xs text-gray-400">—</span>';
            return '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-indigo-50 text-indigo-700">' + escapeHtml(v) + '</span>';
        },
        cellStyle: { 'text-align': 'center' }
    },
    {
        field: 'source_organization',
        headerName: cfg.t.source_org_83a6d807,
        width: 160,
        minWidth: 120,
        maxWidth: 220,
        filter: 'agTextColumnFilter',
        sortable: true,
        cellRenderer: function(params) {
            const v = params.value || '';
            if (!v) return '<span class="text-xs text-gray-400">—</span>';
            const short = v.length > 40 ? v.substring(0, 37) + '…' : v;
            return '<span class="text-sm text-gray-700" title="' + escapeAttr(v) + '">' + escapeHtml(short) + '</span>';
        },
        cellStyle: { 'white-space': 'nowrap', 'overflow': 'hidden', 'text-overflow': 'ellipsis' }
    },
    {
        field: 'document_category',
        headerName: cfg.t.category_3adbdb3a,
        width: 160,
        minWidth: 130,
        maxWidth: 200,
        filter: 'customSetFilter',
        sortable: true,
        cellRenderer: function(params) {
            const v = params.value || '';
            const docId = params.data && params.data.id;
            const label = v ? getCategoryLabel(v) : cfg.t.none_49bd59b9;
            const opts = DOCUMENT_CATEGORY_OPTIONS.map(function(o) {
                return '<option value="' + escapeAttr(o.value) + '"' + (o.value === v ? ' selected' : '') + '>' + escapeHtml(o.label) + '</option>';
            }).join('');
            return '<select class="ai-doc-category-select text-xs border-0 bg-transparent focus:ring-1 focus:ring-blue-400 rounded cursor-pointer w-full py-0.5 text-emerald-700 font-medium" ' +
                   'data-ai-doc-action="change-category" data-doc-id="' + (docId || '') + '" ' +
                   'title="' + cfg.t.click_to_change_category_a21f96b3 + '">' + opts + '</select>';
        },
        filterValueGetter: function(params) {
            return getCategoryLabel(params.data && params.data.document_category);
        },
        cellStyle: { 'text-align': 'center', 'padding': '2px 4px' }
    },
    {
        field: 'quality_score',
        headerName: cfg.t.quality_571094bb,
        width: 110,
        minWidth: 90,
        maxWidth: 130,
        filter: 'agNumberColumnFilter',
        sortable: true,
        cellRenderer: function(params) {
            const v = params.value;
            if (v === null || v === undefined) return '<span class="text-xs text-gray-400">—</span>';
            const pct = Math.round(v * 100);
            const color = pct >= 80 ? 'text-green-700 bg-green-50' : pct >= 50 ? 'text-yellow-700 bg-yellow-50' : 'text-red-700 bg-red-50';
            return '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold ' + color + '">' + pct + '%</span>';
        },
        cellStyle: { 'text-align': 'center' }
    }
];

const documentsGridState = {
    gridInitialized: false,
};

/** Matches AgGridHelper paginationPageSizeSelector max; fetch all rows for client-side pagination. */
const DOCUMENTS_GRID_FETCH_PER_PAGE = 10000;

function getDocumentsGridListUrl() {
    return (cfg.urls && cfg.urls.documentsList) || '/api/ai/documents/';
}

function getDocumentsGridFetchHeaders() {
    return {
        'Accept': 'application/json',
        'X-Requested-With': 'XMLHttpRequest'
    };
}

async function fetchDocumentsGridPageFromApi(page, perPage) {
    const sp = getDocumentsPageFilterParams();
    sp.set('page', String(page));
    sp.set('per_page', String(perPage));
    let base = getDocumentsGridListUrl();
    if (base.indexOf('?') !== -1) {
        base = base.split('?')[0];
    }
    const response = await ((window.getFetch && window.getFetch()) || fetch)(base + '?' + sp.toString(), {
        credentials: 'same-origin',
        headers: getDocumentsGridFetchHeaders()
    });
    const data = await response.json();
    if (!data || data.success !== true || !Array.isArray(data.documents)) {
        throw new Error((data && data.error) || cfg.t.load_documents_error_2d8f4b1a || 'Could not load documents.');
    }
    return data;
}

async function fetchAllDocumentsForGrid() {
    const first = await fetchDocumentsGridPageFromApi(1, DOCUMENTS_GRID_FETCH_PER_PAGE);
    let documents = (first.documents || []).slice();
    const total = first.total != null ? first.total : documents.length;
    const pages = first.pages != null ? first.pages : 1;
    for (let page = 2; page <= pages; page++) {
        const next = await fetchDocumentsGridPageFromApi(page, DOCUMENTS_GRID_FETCH_PER_PAGE);
        documents = documents.concat(next.documents || []);
    }
    if (total > documents.length) {
        console.warn('documents grid: fetched', documents.length, 'of', total, 'rows');
    }
    return documents.map(mapDocToGridRow);
}

function getDocumentsGridOptions() {
    return {
        tooltipShowDelay: 200,
        tooltipHideDelay: 12000,
        components: {
            countryScopeTooltip: CountryScopeTooltip
        }
    };
}

function ensureDocumentsGrid(rows) {
    if (documentsGridState.gridInitialized && documentsGridHelper) {
        documentsGridHelper.setRowData(rows);
        if (documentsGridApi && typeof documentsGridApi.setGridOption === 'function') {
            documentsGridApi.setGridOption('rowData', rows);
        }
        if (documentsGridApi && typeof documentsGridApi.paginationGoToFirstPage === 'function') {
            documentsGridApi.paginationGoToFirstPage();
        }
        return;
    }

    documentsGridState.gridInitialized = true;
    documentsGridHelper = new AgGridHelper({
        containerId: 'documentsGrid',
        templateId: 'ai-documents',
        columnDefs: columnDefs,
        rowData: rows,
        options: getDocumentsGridOptions(),
        columnVisibilityOptions: {
            enableExport: false,
            enableReset: true
        }
    });
    documentsGridApi = documentsGridHelper.initialize();
    window.documentsGridApi = documentsGridApi;
    window.documentsGridHelper = documentsGridHelper;
}

async function loadDocumentsGrid() {
    const loadingEl = document.getElementById('documentsGrid-loading');
    const emptyEl = document.getElementById('documentsGrid-empty');
    const containerEl = document.getElementById('documentsGrid-container');
    if (loadingEl) loadingEl.style.display = 'flex';

    try {
        const rows = await fetchAllDocumentsForGrid();
        ensureDocumentsGrid(rows);

        if (loadingEl) loadingEl.style.display = 'none';
        if (rows.length > 0) {
            if (containerEl) containerEl.style.display = 'block';
            if (emptyEl) emptyEl.style.display = 'none';
        } else {
            if (containerEl) containerEl.style.display = 'none';
            if (emptyEl) emptyEl.style.display = 'block';
        }
    } catch (err) {
        console.error('loadDocumentsGrid failed:', err);
        if (loadingEl) loadingEl.style.display = 'none';
        if (containerEl) containerEl.style.display = 'none';
        if (emptyEl) {
            const safeErrorMsg = escapeHtml((err && err.message) || cfg.t.load_documents_error_2d8f4b1a || 'Could not load documents.');
            emptyEl.innerHTML = '<i class="fas fa-exclamation-triangle text-5xl text-red-300 mb-4"></i><p class="text-red-600 font-medium mb-1">' +
                escapeHtml(cfg.t.error_3d9f514d || 'Error:') + '</p><p class="text-sm text-gray-500">' + safeErrorMsg + '</p>';
            emptyEl.style.display = 'block';
        }
    }
}

async function reloadDocumentsGrid() {
    return loadDocumentsGrid();
}

function initializeDocumentsGrid() {
    loadDocumentsGrid();
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeDocumentsGrid);
} else {
    initializeDocumentsGrid();
}

// Bulk actions (Reprocess/Delete) driven by AG Grid selection
function initializeDocumentsBulkActions() {
    const bulkContainer = document.getElementById('documentsBulkActions');
    const downloadBtn = document.getElementById('bulkDownloadBtn');
    const reprocessBtn = document.getElementById('bulkReprocessBtn');
    const redetectCountryBtn = document.getElementById('bulkRedetectCountryBtn');
    const reprocessMetaBtn = document.getElementById('bulkReprocessMetaBtn');
    const deleteBtn = document.getElementById('bulkDeleteBtn');
    const downloadLabel = document.getElementById('bulkDownloadBtnLabel');
    const reprocessLabel = document.getElementById('bulkReprocessBtnLabel');
    const redetectCountryLabel = document.getElementById('bulkRedetectCountryBtnLabel');
    const reprocessMetaLabel = document.getElementById('bulkReprocessMetaBtnLabel');
    const deleteLabel = document.getElementById('bulkDeleteBtnLabel');

    if (!bulkContainer || !downloadBtn || !reprocessBtn || !deleteBtn || !downloadLabel || !reprocessLabel || !deleteLabel) {
        return;
    }

    const isProcessingStatus = function(status) {
        return status === 'processing' || status === 'pending';
    };

    const getSelectedDocs = function() {
        if (!documentsGridHelper) return [];
        return documentsGridHelper.getSelectedRows() || [];
    };

    const deselectAll = function() {
        try {
            if (documentsGridApi && typeof documentsGridApi.deselectAll === 'function') {
                documentsGridApi.deselectAll();
            }
        } catch (e) {
            // ignore
        }
    };

    const updateButtons = function(selectedRows) {
        const selectedCount = Array.isArray(selectedRows) ? selectedRows.length : 0;
        const eligibleReprocess = (selectedRows || []).filter(function(r) {
            return r && !isProcessingStatus(r.processing_status);
        });

        if (selectedCount > 0) {
            bulkContainer.classList.remove('hidden');
            bulkContainer.classList.add('flex');
        } else {
            bulkContainer.classList.add('hidden');
            bulkContainer.classList.remove('flex');
        }

        downloadBtn.disabled = selectedCount === 0;
        reprocessBtn.disabled = eligibleReprocess.length === 0;
        deleteBtn.disabled = selectedCount === 0;
        if (redetectCountryBtn) redetectCountryBtn.disabled = eligibleReprocess.length === 0;
        if (redetectCountryLabel) redetectCountryLabel.textContent = selectedCount > 0
            ? cfg.t.redetect_country_2f20e028 + ' (' + eligibleReprocess.length + ')'
            : cfg.t.redetect_country_2f20e028;
        if (reprocessMetaBtn) reprocessMetaBtn.disabled = eligibleReprocess.length === 0;
        if (reprocessMetaLabel) reprocessMetaLabel.textContent = selectedCount > 0
            ? cfg.t.reprocess_metadata_4a7b1eab + ' (' + eligibleReprocess.length + ')'
            : cfg.t.reprocess_metadata_4a7b1eab;

        downloadLabel.textContent = selectedCount > 0
            ? cfg.t.download_801ab246 + ' (' + selectedCount + ')'
            : cfg.t.download_801ab246;
        reprocessLabel.textContent = selectedCount > 0
            ? cfg.t.reprocess_3f20034f + ' (' + eligibleReprocess.length + ')'
            : cfg.t.reprocess_3f20034f;
        deleteLabel.textContent = selectedCount > 0
            ? cfg.t.delete_f2a6c498 + ' (' + selectedCount + ')'
            : cfg.t.delete_f2a6c498;
    };

    const bulkDownloadSelected = function() {
        const selectedRows = getSelectedDocs();
        const targets = selectedRows.filter(function(r) {
            return r && r.id !== null && r.id !== undefined;
        });
        if (!targets.length) return;

        const ids = targets.map(function(r) { return r.id; });

        // Submit a hidden form so the browser downloads the ZIP normally (no large in-memory blob).
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = '/admin/ai/documents/bulk-download';
        form.style.display = 'none';

        const csrfInput = document.createElement('input');
        csrfInput.type = 'hidden';
        csrfInput.name = 'csrf_token';
        try {
            csrfInput.value = (typeof getCSRFToken === 'function')
                ? (getCSRFToken() || '')
                : ((document.querySelector('meta[name="csrf-token"]') || {}).content || '');
        } catch (e) {
            csrfInput.value = ((document.querySelector('meta[name="csrf-token"]') || {}).content || '');
        }
        form.appendChild(csrfInput);

        const idsInput = document.createElement('input');
        idsInput.type = 'hidden';
        idsInput.name = 'ids';
        idsInput.value = ids.join(',');
        form.appendChild(idsInput);

        document.body.appendChild(form);
        form.submit();
        setTimeout(function() {
            try { form.remove(); } catch (e) {}
        }, 1500);
    };

    const bulkReprocessSelected = async function() {
        const selectedRows = getSelectedDocs();
        const targets = selectedRows.filter(function(r) {
            return r && r.id !== null && r.id !== undefined && !isProcessingStatus(r.processing_status);
        });
        if (!targets.length) return;

        aiDocsLog('bulkReprocessSelected', {
            selectedCount: selectedRows.length,
            targetsCount: targets.length,
            ids: targets.map(function(r) { return r.id; })
        });

        const confirmMsg = cfg.t.reprocess_selected_documents_95e21554 + ' (' + targets.length + ')';
        const proceed = async function() {
            // IMPORTANT: Pre-register ALL docs first so the banner shows 0/N immediately (not 0/1 then 0/2...).
            const requestTs = Date.now();
            const ids = targets.map(function(r) { return r.id; });

            aiDocsLog('bulkReprocessSelected:begin', { targets: ids });

            beginBulkReprocessJob(ids.length, ids, requestTs);
            ids.forEach(function(id) {
                updateDocumentInGrid(id, { processing_status: 'pending', processing_error: '' });
            });

            // Start server-side bulk job (avoids per-document rate limits and survives reload).
            try {
                const response = await csrfFetch('/admin/ai/documents/bulk-reprocess', {
                    method: 'POST',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest',
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ ids: ids })
                });
                const result = await response.json();
                if (!result.success || !result.job_id) {
                    throw new Error(result.error || 'Failed to start bulk reprocess');
                }
                if (processingCancelWrap) processingCancelWrap.classList.remove('hidden');
                startBulkReprocessJobPolling(result.job_id, result.total || ids.length);
            } catch (error) {
                aiDocsLog('bulkReprocessSelected:startError', { error: error && (error.message || String(error)) });
                failBulkReprocessJob(ids, error && (error.message || String(error)));
                ids.forEach(function(id) {
                    updateDocumentInGrid(id, { processing_status: 'failed', processing_error: error.message || '' });
                });
            }

            // Clear selection so the bulk bar hides
            deselectAll();
        };

        if (window.showConfirmation) {
            window.showConfirmation(
                confirmMsg,
                proceed,
                null,
                cfg.t.reprocess_3f20034f,
                cfg.t.cancel_ea478870,
                cfg.t.reprocess_documents_fa766fbe
            );
        } else {
            proceed();
        }
    };

    const bulkReprocessMetaSelected = async function() {
        if (!reprocessMetaBtn) return;
        const selectedRows = getSelectedDocs();
        const targets = selectedRows.filter(function(r) {
            return r && r.id != null && r.id !== undefined && !isProcessingStatus(r.processing_status);
        });
        if (!targets.length) return;

        const confirmMsg = cfg.t.re_run_metadata_enrichment_date_language_abe06685 + ' (' + targets.length + ')';
        const proceed = async function() {
            const ids = targets.map(function(r) { return r.id; });
            showProcessingBanner(cfg.t.reprocessing_metadata_e6c7cf5c, cfg.t.starting_8c6ce9f8, 0);
            if (processingCancelWrap) processingCancelWrap.classList.remove('hidden');
            try {
                const response = await csrfFetch('/admin/ai/documents/bulk-reprocess-metadata', {
                    method: 'POST',
                    headers: { 'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ids: ids })
                });
                const result = await response.json();
                if (!result.success || !result.job_id) {
                    throw new Error(result.error || 'Failed to start metadata reprocess');
                }
                startBulkMetaReprocessJobPolling(result.job_id, result.total || ids.length);
            } catch (error) {
                hideProcessingBanner();
                if (processingCancelWrap) processingCancelWrap.classList.add('hidden');
                if (window.showAlert) window.showAlert(cfg.t.error_3d9f514d + ' ' + ((error && error.message) || cfg.t.failed_to_start_metadata_reprocess_801da98c), 'error');
            }
            deselectAll();
        };

        if (window.showConfirmation) {
            window.showConfirmation(
                confirmMsg,
                proceed,
                null,
                cfg.t.reprocess_metadata_4a7b1eab,
                cfg.t.cancel_ea478870,
                cfg.t.reprocess_metadata_d2fa3648
            );
        } else {
            proceed();
        }
    };

    const bulkDeleteSelected = async function() {
        const selectedRows = getSelectedDocs();
        const targets = selectedRows.filter(function(r) {
            return r && r.id !== null && r.id !== undefined;
        });
        if (!targets.length) return;

        const confirmMsg = cfg.t.delete_selected_documents_54681267 + ' (' + targets.length + ')';
        const proceed = async function() {
            for (let i = 0; i < targets.length; i++) {
                const row = targets[i];
                const id = row.id;
                const title = row.title || row.filename || 'Untitled';

                try {
                    const response = await csrfFetch(`/admin/ai/documents/${id}/delete`, {
                        method: 'POST',
                        headers: { 'X-Requested-With': 'XMLHttpRequest' }
                    });
                    const result = await response.json();

                    if (result.success) {
                        stopProcessingPoll(id);
                        removeTrackedProcessingDoc(id);
                        removeDocumentFromGrid(id);
                    } else {
                        const msg = cfg.t.error_3d9f514d + ' ' + (result.error || cfg.t.failed_to_delete_document_94ab7a09) + ' (' + title + ')';
                        if (window.showAlert) window.showAlert(msg, 'error'); else console.error(msg);
                    }
                } catch (error) {
                    const msg = cfg.t.error_3d9f514d + ' ' + (error.message || cfg.t.failed_to_delete_document_94ab7a09) + ' (' + title + ')';
                    if (window.showAlert) window.showAlert(msg, 'error'); else console.error(msg);
                }
            }

            deselectAll();
        };

        if (window.showDangerConfirmation) {
            window.showDangerConfirmation(
                confirmMsg,
                proceed,
                null,
                cfg.t.delete_f2a6c498,
                cfg.t.cancel_ea478870,
                cfg.t.delete_documents_13b47e67
            );
        } else if (window.showConfirmation) {
            window.showConfirmation(
                confirmMsg,
                proceed,
                null,
                cfg.t.delete_f2a6c498,
                cfg.t.cancel_ea478870,
                cfg.t.delete_documents_13b47e67
            );
        } else {
            proceed();
        }
    };

    const bulkRedetectCountrySelected = async function() {
        if (!redetectCountryBtn) return;
        const selectedRows = getSelectedDocs();
        const targets = selectedRows.filter(function(r) {
            return r && r.id != null && r.id !== undefined && !isProcessingStatus(r.processing_status);
        });
        if (!targets.length) return;

        const confirmMsg = cfg.t.re_run_country_detection_for_selected_do_01bf58fb + ' (' + targets.length + ')';
        const proceed = function() {
            const total = targets.length;
            showProcessingBanner(cfg.t.detecting_countries_c3ff26ba + ' (0/' + total + ')', cfg.t.starting_8c6ce9f8, 0);

            (async function() {
                let done = 0;
                let failed = 0;
                for (let i = 0; i < targets.length; i++) {
                    const row = targets[i];
                    const id = row.id;
                    const title = row.title || row.filename || 'Untitled';
                    const pct = Math.round(((i) / total) * 100);
                    showProcessingBanner(
                        cfg.t.detecting_countries_c3ff26ba + ' (' + (i + 1) + '/' + total + ')',
                        '#' + id + ' \u2022 ' + title,
                        pct
                    );
                    updateDocumentInGrid(id, { redetect_processing: true });
                    try {
                        const response = await csrfFetch('/admin/ai/documents/' + id + '/redetect-country', {
                            method: 'POST',
                            headers: { 'X-Requested-With': 'XMLHttpRequest' }
                        });
                        const result = await response.json();
                        if (result.success) {
                            updateDocumentInGrid(id, {
                                redetect_processing: false,
                                country_name: result.country_name || '',
                                country_iso3: result.country_iso3 || '',
                                geographic_scope: result.geographic_scope || ''
                            });
                            done++;
                        } else {
                            failed++;
                            updateDocumentInGrid(id, { redetect_processing: false });
                        }
                    } catch (error) {
                        failed++;
                        updateDocumentInGrid(id, { redetect_processing: false });
                    }
                }
                const summaryMsg = failed > 0
                    ? (done + ' ' + cfg.t.document_s_updated_15f428a2 + ' ' + failed + ' ' + cfg.t.failed_53cc4f54)
                    : (done + ' ' + cfg.t.document_s_updated_15f428a2);
                showProcessingBanner(cfg.t.detecting_countries_c3ff26ba + ' (' + total + '/' + total + ')', summaryMsg, 100);
                if (window.showAlert) window.showAlert(summaryMsg, failed > 0 ? 'warning' : 'success');
                setTimeout(hideProcessingBanner, 3000);
                deselectAll();
            })();
        };

        if (window.showConfirmation) {
            window.showConfirmation(
                confirmMsg,
                proceed,
                null,
                cfg.t.redetect_country_2f20e028,
                cfg.t.cancel_ea478870,
                cfg.t.redetect_country_f2f630d6
            );
        } else {
            proceed();
        }
    };

    downloadBtn.addEventListener('click', function() {
        bulkDownloadSelected();
    });
    reprocessBtn.addEventListener('click', function() {
        bulkReprocessSelected();
    });
    if (redetectCountryBtn) redetectCountryBtn.addEventListener('click', function() {
        bulkRedetectCountrySelected();
    });
    if (reprocessMetaBtn) reprocessMetaBtn.addEventListener('click', function() {
        bulkReprocessMetaSelected();
    });
    deleteBtn.addEventListener('click', function() {
        bulkDeleteSelected();
    });

    // Listen to shared selection-change event from AgGridHelper
    document.addEventListener('ag-grid-selection-changed', function(e) {
        if (!e || !e.detail || e.detail.gridId !== 'documentsGrid') {
            return;
        }
        updateButtons(e.detail.selectedRows || []);
    });

    // Initial UI state
    updateButtons([]);
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeDocumentsBulkActions);
} else {
    initializeDocumentsBulkActions();
}

// Mirrors csrf.js's responseIndicatesCsrfFailure(), but operates on an already-parsed
// XHR JSON payload (xhr.onload parses the body itself, so there's no Response to clone/re-read).
function isCsrfFailureResponse(status, payload) {
    if (status !== 400 && status !== 403) return false;
    if (!payload) return false;
    if (payload.csrf_refresh_required || payload.error === 'CSRF validation failed') return true;
    const message = String(payload.message || payload.error || '').toLowerCase();
    return message.includes('csrf');
}

// Upload form handling
function initializeUploadForm() {
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');
    const uploadBtn = document.getElementById('uploadBtn');
    const uploadForm = document.getElementById('uploadForm');
    const uploadProgress = document.getElementById('uploadProgress');
    const progressBar = document.getElementById('progressBar');
    const uploadStatus = document.getElementById('uploadStatus');

    if (!dropZone || !fileInput || !uploadBtn || !uploadForm) {
        console.error('Upload form elements not found');
        return;
    }

    // Update file name and enable upload button
    function updateFileName() {
        if (fileInput.files && fileInput.files.length > 0) {
            const file = fileInput.files[0];
            const textElements = dropZone.querySelectorAll('p');
            if (textElements.length > 0) {
                textElements[0].textContent = file.name;
            }
            uploadBtn.disabled = false;
            window.__clientLog && window.__clientLog('File selected:', file.name);
        } else {
            uploadBtn.disabled = true;
        }
    }

    // Keyboard support for the drop zone
    dropZone.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            fileInput.click();
        }
    });

    // Drag and drop
    dropZone.addEventListener('dragover', function(e) {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', function() {
        dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', function(e) {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        if (e.dataTransfer.files.length) {
            fileInput.files = e.dataTransfer.files;
            updateFileName();
        }
    });

    // File selected
    fileInput.addEventListener('change', updateFileName);

    // Upload form submit
    uploadForm.addEventListener('submit', async function(e) {
        e.preventDefault();

        if (uploadForm.dataset.uploading === '1') return;

        if (!fileInput.files || !fileInput.files.length) {
            if (window.showAlert) {
                window.showAlert(cfg.t.please_select_a_file_b3d4e2bc, 'warning');
            } else {
                if (window.showAlert) window.showAlert(cfg.t.please_select_a_file_b3d4e2bc, 'warning');
                else window.__clientWarn && window.__clientWarn('Please select a file');
            }
            return;
        }

        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        formData.append('title', document.getElementById('docTitle').value);
        formData.append('is_public', uploadForm.querySelector('[name="is_public"]').checked);

        uploadForm.dataset.uploading = '1';
        uploadBtn.disabled = true;
        uploadProgress.classList.remove('hidden');
        progressBar.style.width = '0%';
        uploadStatus.textContent = cfg.t.uploading_f2870421;

        try {
            window.__clientLog && window.__clientLog('Uploading file:', fileInput.files[0].name);

            // Mirror csrfFetch's pre-flight: don't race an in-flight refresh, and
            // proactively refresh an aging token before a (potentially long) upload
            // starts rather than only discovering it's stale after the server rejects it.
            if (typeof waitForPendingCsrfRefresh === 'function') {
                await waitForPendingCsrfRefresh();
            }
            if (typeof refreshCSRFTokenIfStale === 'function') {
                await refreshCSRFTokenIfStale().catch(function () { return null; });
            }

            function performUploadXhr(csrfToken) {
                if (csrfToken) {
                    formData.set('csrf_token', csrfToken);
                }
                return new Promise(function (resolve, reject) {
                    const xhr = new XMLHttpRequest();
                    xhr.open('POST', '/api/ai/documents/upload', true);
                    xhr.withCredentials = true;
                    xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
                    if (csrfToken) {
                        xhr.setRequestHeader('X-CSRFToken', csrfToken);
                    }
                    xhr.upload.onprogress = function (evt) {
                        if (!evt.lengthComputable) return;
                        const pct = Math.round((evt.loaded / evt.total) * 100);
                        progressBar.style.width = pct + '%';
                        uploadStatus.textContent = cfg.t.uploading_f2870421 + ' (' + pct + '%)';
                    };
                    xhr.onerror = function () {
                        reject(new Error('Upload failed'));
                    };
                    xhr.onload = function () {
                        let payload = null;
                        try {
                            payload = JSON.parse(xhr.responseText || '{}');
                        } catch (parseErr) {
                            reject(parseErr);
                            return;
                        }
                        resolve({ status: xhr.status, result: payload });
                    };
                    xhr.send(formData);
                });
            }

            const token = (typeof getCSRFToken === 'function') ? getCSRFToken() : null;
            let result = await performUploadXhr(token);

            // Retry once with a freshly-refreshed token if the server rejected this one as
            // stale/invalid — csrfFetch does the same for regular fetch-based requests.
            if (isCsrfFailureResponse(result.status, result.result) && typeof refreshCSRFToken === 'function') {
                const newToken = await refreshCSRFToken();
                if (newToken) {
                    result = await performUploadXhr(newToken);
                }
            }

            const response = { status: result.status };
            const uploadResult = result.result;
            window.__clientLog && window.__clientLog('Upload response:', uploadResult);

            if (response.status === 202 && uploadResult.success && uploadResult.document_id) {
                uploadProgress.classList.add('hidden');
                const docId = uploadResult.document_id;
                showProcessingBanner(cfg.t.processing_upload_9cb556a5, cfg.t.starting_8c6ce9f8, 0);
                updateTrackedProcessingDoc(docId, { resetProgress: true, status: 'pending', stage: cfg.t.starting_8c6ce9f8, progress: 0 });
                startProcessingPoll(docId);
                await new Promise(function (resolve) {
                    function check() {
                        const t = (jobProgress && jobProgress.getDocState ? jobProgress.getDocState(docId) : null);
                        if (t && (t.status === 'completed' || t.status === 'failed' || t.status === 'not_found')) {
                            resolve();
                        } else {
                            setTimeout(check, 500);
                        }
                    }
                    check();
                });
                const t = (jobProgress && jobProgress.getDocState ? jobProgress.getDocState(docId) : null);
                stopProcessingPoll(docId);
                if (t && t.status === 'completed') {
                    showProcessingBanner(cfg.t.upload_complete_f79598ab, cfg.t.done_f92965e2, 100);
                closeUploadModal();
                reloadDocumentsGrid();
                setTimeout(function() { hideProcessingBanner(); uploadForm.dataset.uploading = '0'; uploadBtn.disabled = false; }, 2000);
                } else {
                    uploadStatus.textContent = cfg.t.error_3d9f514d + ' ' + ((t && t.error) || uploadResult.error || 'Unknown error');
                    hideProcessingBanner();
                    uploadForm.dataset.uploading = '0';
                    uploadBtn.disabled = false;
                }
            } else if (uploadResult.success) {
                uploadStatus.textContent = cfg.t.upload_complete_635c737d;
                progressBar.style.width = '100%';
                closeUploadModal();
                reloadDocumentsGrid();
                setTimeout(function() {
                    uploadProgress.classList.add('hidden');
                    uploadForm.dataset.uploading = '0';
                    uploadBtn.disabled = false;
                }, 1500);
            } else {
                progressBar.style.width = '100%';
                uploadStatus.textContent = cfg.t.error_3d9f514d + ' ' + (uploadResult.error || 'Unknown error');
                uploadForm.dataset.uploading = '0';
                uploadBtn.disabled = false;
            }
        } catch (error) {
            console.error('Upload error:', error);
            uploadProgress.classList.remove('hidden');
            uploadStatus.textContent = cfg.t.upload_failed_0e76390e + ' ' + error.message;
            uploadForm.dataset.uploading = '0';
            uploadBtn.disabled = false;
        }
    });
}

// Initialize upload form when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeUploadForm);
} else {
    initializeUploadForm();
}

/**
 * IFRC tab layout: while the grid shell is hidden, shrink .modal-content + tab stack (no flex-1 dead zone).
 * When the grid is shown, expand #ifrcApiContent so the grid + clamp min-height behave like Import from System.
 */
function syncUploadImportModalIfrcCompactLayout() {
    const modal = document.getElementById('uploadImportModal');
    if (!modal) return;
    const ifrcContent = document.getElementById('ifrcApiContent');
    const shell = document.getElementById('ifrcDocumentsGridShell');
    const ifrcVisible = !!(ifrcContent && !ifrcContent.classList.contains('hidden'));
    const gridHidden = !shell || shell.classList.contains('hidden');
    if (ifrcVisible && gridHidden) {
        modal.classList.add('upload-import-modal--ifrc-idle');
    } else {
        modal.classList.remove('upload-import-modal--ifrc-idle');
    }
    if (ifrcContent) {
        if (ifrcVisible && !gridHidden) {
            ifrcContent.classList.add('ifrc-api-tab--expanded');
        } else {
            ifrcContent.classList.remove('ifrc-api-tab--expanded');
        }
    }
    syncUploadImportModalFooter();
}

let importTabHasRows = false;
let ifrcTabHasRows = false;

function formatImportFooterSummary(count) {
    const n = Number(count) || 0;
    if (n <= 0) {
        return cfg.t.import_footer_none_selected_a4c8e2b1 || 'Select documents in the grid';
    }
    const tpl = cfg.t.import_footer_selected_count_b7d3f9a2 || '{count} selected';
    return tpl.replace('{count}', String(n));
}

function syncUploadImportModalFooter() {
    const footer = document.getElementById('uploadImportModalFooter');
    const importFooter = document.getElementById('importTabFooter');
    const ifrcFooter = document.getElementById('ifrcTabFooter');
    const importContent = document.getElementById('importContent');
    const ifrcContent = document.getElementById('ifrcApiContent');
    const importVisible = !!(importContent && !importContent.classList.contains('hidden'));
    const ifrcVisible = !!(ifrcContent && !ifrcContent.classList.contains('hidden'));
    const showImportFooter = importVisible && importTabHasRows;
    const showIfrcFooter = ifrcVisible && ifrcTabHasRows;

    if (footer) {
        footer.classList.toggle('hidden', !showImportFooter && !showIfrcFooter);
    }
    if (importFooter) {
        importFooter.classList.toggle('hidden', !showImportFooter);
    }
    if (ifrcFooter) {
        ifrcFooter.classList.toggle('hidden', !showIfrcFooter);
    }
}

// Tab switching functionality
function initializeTabs() {
    const uploadTab = document.getElementById('uploadTab');
    const importTab = document.getElementById('importTab');
    const ifrcApiTab = document.getElementById('ifrcApiTab');
    const uploadContent = document.getElementById('uploadContent');
    const importContent = document.getElementById('importContent');
    const ifrcApiContent = document.getElementById('ifrcApiContent');
    const importRefreshBtn = document.getElementById('importRefreshBtn');

    if (!uploadTab || !importTab || !ifrcApiTab || !uploadContent || !importContent || !ifrcApiContent) return;

    function setActiveTab(activeTab, activeContent) {
        // Reset all tabs
        [uploadTab, importTab, ifrcApiTab].forEach(tab => {
            tab.classList.remove('active');
            tab.classList.remove('border-blue-500', 'text-blue-600');
            tab.classList.add('border-transparent', 'text-gray-600');
            tab.setAttribute('aria-selected', 'false');
            tab.setAttribute('tabindex', '-1');
        });

        // Reset all content
        [uploadContent, importContent, ifrcApiContent].forEach(content => {
            content.classList.add('hidden');
            content.setAttribute('aria-hidden', 'true');
        });

        // Set active tab
        activeTab.classList.add('active');
        activeTab.classList.remove('border-transparent', 'text-gray-600');
        activeTab.classList.add('border-blue-500', 'text-blue-600');
        activeTab.setAttribute('aria-selected', 'true');
        activeTab.setAttribute('tabindex', '0');

        // Show active content
        activeContent.classList.remove('hidden');
        activeContent.setAttribute('aria-hidden', 'false');
        syncUploadImportModalIfrcCompactLayout();
    }

    function activateTabByIndex(idx) {
        const tabs = [uploadTab, importTab, ifrcApiTab];
        const panels = [uploadContent, importContent, ifrcApiContent];
        const nextIdx = Math.max(0, Math.min(tabs.length - 1, idx));
        const tab = tabs[nextIdx];
        const panel = panels[nextIdx];
        if (!tab || !panel) return;
        setActiveTab(tab, panel);
        try { tab.focus(); } catch (e) { /* ignore */ }
    }

    [uploadTab, importTab, ifrcApiTab].forEach((tab, idx) => {
        tab.addEventListener('keydown', function(e) {
            if (!e) return;
            const key = e.key;
            if (key === 'ArrowRight') { e.preventDefault(); activateTabByIndex(idx + 1); }
            else if (key === 'ArrowLeft') { e.preventDefault(); activateTabByIndex(idx - 1); }
            else if (key === 'Home') { e.preventDefault(); activateTabByIndex(0); }
            else if (key === 'End') { e.preventDefault(); activateTabByIndex(2); }
            else if (key === 'Enter' || key === ' ') { e.preventDefault(); activateTabByIndex(idx); }
        });
    });

    uploadTab.addEventListener('click', function() {
        setActiveTab(uploadTab, uploadContent);
    });

    importTab.addEventListener('click', function() {
        setActiveTab(importTab, importContent);

        // Load documents when tab is opened for the first time
        if (!importTab.dataset.loaded) {
            loadSystemDocuments();
            importTab.dataset.loaded = 'true';
        } else if (importDocumentsGridHelper && typeof importDocumentsGridHelper.setDynamicHeight === 'function') {
            window.requestAnimationFrame(function() {
                try {
                    importDocumentsGridHelper.setDynamicHeight();
                } catch (e) { /* ignore */ }
            });
        }
    });

    ifrcApiTab.addEventListener('click', async function() {
        setActiveTab(ifrcApiTab, ifrcApiContent);
        if (!ifrcApiTab.dataset.loaded) {
            ifrcApiTab.dataset.loaded = 'true';
            try {
                // Populate type + country filters only; document list loads when user clicks Search or Refresh.
                await ensureIfrcFilterDropdowns();
            } catch (err) {
                console.error('External API tab load:', err);
            }
        }
    });

    // When country changes, filter type dropdown to applicable types for that country
    const ifrcCountryNameFilterEl = document.getElementById('ifrcCountryNameFilter');
    if (ifrcCountryNameFilterEl) {
        ifrcCountryNameFilterEl.addEventListener('change', function() {
            loadIfrcTypes(this.value.trim() || '');
        });
    }
    // When type selection changes, filter country dropdown to applicable countries for those types
    const ifrcTypeFilterWrap = document.getElementById('ifrcTypeFilter');
    if (ifrcTypeFilterWrap) {
        ifrcTypeFilterWrap.addEventListener('change', function(e) {
            if (e.target && e.target.name === 'ifrc_type_option') {
                updateIfrcTypeFilterSummary();
                loadIfrcCountries(getIfrcSelectedAppealsTypeIdsForCountryFilter());
            }
        });
        document.addEventListener('mousedown', function(e) {
            if (!isIfrcTypeDropdownOpen()) return;
            if (ifrcTypeFilterWrap.contains(e.target)) return;
            setIfrcTypeDropdownOpen(false);
        });
        document.addEventListener('keydown', function(e) {
            if (e.key !== 'Escape') return;
            if (!isIfrcTypeDropdownOpen()) return;
            setIfrcTypeDropdownOpen(false);
        });
    }
    const ifrcTypeSelectAllBtn = document.getElementById('ifrcTypeSelectAll');
    if (ifrcTypeSelectAllBtn) {
        ifrcTypeSelectAllBtn.addEventListener('click', function(e) {
            e.preventDefault();
            const list = getIfrcTypeFilterListEl();
            if (!list) return;
            list.querySelectorAll('input[name="ifrc_type_option"]').forEach(function(cb) { cb.checked = true; });
            updateIfrcTypeFilterSummary();
            loadIfrcCountries(getIfrcSelectedAppealsTypeIdsForCountryFilter());
        });
    }
    const ifrcTypeClearAllBtn = document.getElementById('ifrcTypeClearAll');
    if (ifrcTypeClearAllBtn) {
        ifrcTypeClearAllBtn.addEventListener('click', function(e) {
            e.preventDefault();
            const list = getIfrcTypeFilterListEl();
            if (!list) return;
            list.querySelectorAll('input[name="ifrc_type_option"]').forEach(function(cb) { cb.checked = false; });
            updateIfrcTypeFilterSummary();
            loadIfrcCountries(getIfrcSelectedAppealsTypeIdsForCountryFilter());
        });
    }
    const ifrcTypeFilterToggle = document.getElementById('ifrcTypeFilterToggle');
    if (ifrcTypeFilterToggle) {
        ifrcTypeFilterToggle.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            setIfrcTypeDropdownOpen(!isIfrcTypeDropdownOpen());
        });
    }

    if (importRefreshBtn) {
        importRefreshBtn.addEventListener('click', function(e) {
            e.preventDefault();
            loadSystemDocuments();
        });
    }

    // External API search and refresh buttons
    const ifrcSearchBtn = document.getElementById('ifrcSearchBtn');
    const ifrcRefreshBtn = document.getElementById('ifrcRefreshBtn');

    if (ifrcSearchBtn) {
        ifrcSearchBtn.addEventListener('click', async function(e) {
            e.preventDefault();
            try {
                await ensureIfrcFilterDropdowns();
                await loadIfrcApiDocuments();
            } catch (err) {
                console.error('External API search:', err);
            }
        });
    }

    if (ifrcRefreshBtn) {
        ifrcRefreshBtn.addEventListener('click', async function(e) {
            e.preventDefault();
            try {
                await ensureIfrcFilterDropdowns();
                await loadIfrcApiDocuments();
            } catch (err) {
                console.error('External API refresh:', err);
            }
        });
    }
}

// Initialize tabs
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeTabs);
} else {
    initializeTabs();
}

// Modal functionality for Upload/Import
// Expose closeUploadModal globally so upload/import handlers can close it
var closeUploadModal = function() {};

function initializeUploadModal() {
    const modal = document.getElementById('uploadImportModal');
    const openBtn = document.getElementById('openUploadModalBtn');
    const closeBtn = document.getElementById('closeUploadModalBtn');

    if (!modal || !openBtn) return;

    function openModal() {
        modal.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
        syncUploadImportModalIfrcCompactLayout();
    }

    function closeModal() {
        modal.classList.add('hidden');
        modal.classList.remove('upload-import-modal--ifrc-idle');
        const ifrcPanel = document.getElementById('ifrcApiContent');
        if (ifrcPanel) ifrcPanel.classList.remove('ifrc-api-tab--expanded');
        document.body.style.overflow = '';
        // Reset the upload form when closing
        const fileInput = document.getElementById('fileInput');
        const uploadBtn = document.getElementById('uploadBtn');
        const uploadProgress = document.getElementById('uploadProgress');
        const dropZone = document.getElementById('dropZone');
        const docTitle = document.getElementById('docTitle');
        if (fileInput) fileInput.value = '';
        if (uploadBtn) uploadBtn.disabled = true;
        if (uploadProgress) uploadProgress.classList.add('hidden');
        if (docTitle) docTitle.value = '';
        if (dropZone) {
            const textElements = dropZone.querySelectorAll('p');
            if (textElements.length > 0) {
                textElements[0].textContent = cfg.t.drag_and_drop_files_here_or_click_to_sel_d56c91ec;
            }
        }
    }

    // Expose globally
    closeUploadModal = closeModal;

    if (openBtn) {
        openBtn.addEventListener('click', openModal);
    }

    if (closeBtn) {
        closeBtn.addEventListener('click', closeModal);
    }

    const importTabCancelBtn = document.getElementById('importTabCancelBtn');
    const ifrcTabCancelBtn = document.getElementById('ifrcTabCancelBtn');
    if (importTabCancelBtn) {
        importTabCancelBtn.addEventListener('click', closeModal);
    }
    if (ifrcTabCancelBtn) {
        ifrcTabCancelBtn.addEventListener('click', closeModal);
    }

    // Backdrop click (modal_shell: outer div is the overlay)
    modal.addEventListener('click', function(e) {
        if (e.target === modal) closeModal();
    });

    // Close on Escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && !modal.classList.contains('hidden')) {
            closeModal();
        }
    });
}

// Initialize modal when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeUploadModal);
} else {
    initializeUploadModal();
}

// System documents import functionality (AG Grid in Upload/Import modal → Import from System)
let selectedDocuments = new Set();
let importDocumentsGridHelper = null;
let importDocumentsGridApi = null;

function mapSystemDocumentToRow(doc) {
    if (!doc) return null;
    return {
        id: doc.id,
        filename: doc.filename || '',
        document_type: doc.document_type || '',
        country_name: doc.country_name || '',
        source: doc.source || '',
        assignment_name: doc.assignment_name || '',
        template_name: doc.template_name || '',
        period: doc.period || '',
        language: doc.language || '',
        language_display: doc.language_display || doc.language || '',
        uploaded_by: doc.uploaded_by || '',
        status: doc.status || '',
        is_public: !!doc.is_public,
        file_size: (typeof doc.file_size === 'number' && doc.file_size > 0) ? doc.file_size : null,
        file_pending: !!doc.file_pending,
        source_url: doc.source_url || null,
        source_url_http_status: doc.source_url_http_status != null ? doc.source_url_http_status : null,
        source_url_unreachable: !!doc.source_url_unreachable,
        uploaded_at: doc.uploaded_at || null,
        ai_processed: !!doc.ai_processed,
        ai_document_id: doc.ai_document_id != null ? doc.ai_document_id : null,
        ai_status: doc.ai_status || null
    };
}

function importGridTextCell(value) {
    const v = (value == null ? '' : String(value)).trim();
    if (!v) return '<span class="text-xs text-gray-400">\u2014</span>';
    return '<span class="text-sm text-gray-700">' + escapeHtml(v) + '</span>';
}

function importGridSourceLabel(source) {
    const key = String(source || '').trim().toLowerCase();
    if (key === 'assignment') return cfg.t.source_assignment_5c1a8f3d;
    if (key === 'public') return cfg.t.source_public_7b2e4c9a;
    if (key === 'standalone') return cfg.t.source_standalone_3f8d1e6b;
    return '';
}

function importGridSourceUrlStatusLabel(data) {
    if (!data || !data.source_url_unreachable) {
        return cfg.t.file_url_available_8e4f2a1b || 'Available';
    }
    const status = data.source_url_http_status;
    if (status === 0) {
        return cfg.t.file_url_empty_9c3d1e7a || 'No URL';
    }
    if (status === 403) {
        return cfg.t.file_url_forbidden_7b2a9c4d || 'URL blocked (403)';
    }
    if (status === 404) {
        return cfg.t.file_url_not_found_6a1b8e3c || 'URL not found (404)';
    }
    if (status === -1) {
        return cfg.t.file_url_error_5d0c7f2e || 'URL error';
    }
    if (status != null) {
        return (cfg.t.file_url_http_status_4e9a6b1d || 'HTTP {status}').replace('{status}', String(status));
    }
    return cfg.t.file_url_unavailable_3f8e2d0c || 'URL unavailable';
}

function getImportSystemDocumentsGridOptions() {
    return {
        rowSelection: {
            mode: 'multiRow',
            enableClickSelection: true,
            selectAll: 'filtered'
        },
        isRowSelectable: function(node) {
            const data = node && node.data;
            return !!(data && !data.ai_processed && !data.source_url_unreachable);
        },
        onSelectionChanged: function() {
            syncImportSelectionFromGrid();
        },
        paginationPageSize: 25,
        defaultColDef: {
            wrapText: false,
            autoHeight: false,
            sortable: true,
            resizable: true,
            cellStyle: {
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'flex-start'
            }
        }
    };
}

function importFileSizeMeta(data, wrapStyle) {
    const size = data && data.file_size;
    if (typeof size !== 'number' || size <= 0) {
        return '';
    }
    return '<div class="text-xs text-gray-500" style="' + (wrapStyle || '') + '">' + formatFileSize(size) + '</div>';
}

const importSystemDocumentsColumnDefs = [
    {
        field: 'filename',
        headerName: cfg.t.filename_1351017a,
        flex: 1,
        minWidth: 220,
        filter: 'agTextColumnFilter',
        wrapText: true,
        autoHeight: true,
        cellRenderer: function(params) {
            const data = params.data || {};
            const icon = getFileTypeIcon(data.filename);
            const name = escapeHtml(data.filename || '');
            const wrap = 'white-space:normal;overflow-wrap:anywhere;word-break:break-word;max-width:100%';
            const docId = data.id != null ? parseInt(data.id, 10) : 0;
            const nameLine = docId ?
                '<a href="/admin/ai/documents/download-system-document/' + docId + '" class="import-system-doc-filename-link text-sm font-medium text-blue-600 hover:text-blue-800 hover:underline" style="' + wrap + '" ' +
                'target="_blank" rel="noopener noreferrer" title="' + escapeAttr(cfg.t.view_or_download_9e34181d) + '">' + name + '</a>' :
                '<div class="text-sm font-medium text-gray-900" style="' + wrap + '" title="' + escapeAttr(data.filename || '') + '">' + name + '</div>';
            return '<div class="flex items-start gap-2 min-w-0" style="width:100%">' +
                '<div class="flex-shrink-0 text-gray-500" style="padding-top:2px">' + icon + '</div>' +
                '<div class="min-w-0 flex-1" style="' + wrap + '">' +
                nameLine +
                importFileSizeMeta(data, wrap) + '</div></div>';
        },
        cellStyle: {
            'white-space': 'normal',
            'line-height': '1.4',
            'display': 'flex',
            'align-items': 'flex-start',
            'padding-top': '6px',
            'padding-bottom': '6px'
        }
    },
    {
        field: 'country_name',
        headerName: cfg.t.entity_2a6f8c3e,
        width: 160,
        minWidth: 120,
        maxWidth: 240,
        filter: 'customSetFilter',
        wrapText: true,
        autoHeight: true,
        cellRenderer: function(params) {
            return importGridTextCell(params.value);
        },
        cellStyle: {
            'white-space': 'normal',
            'line-height': '1.4',
            'display': 'flex',
            'align-items': 'flex-start',
            'padding-top': '6px',
            'padding-bottom': '6px'
        }
    },
    {
        field: 'assignment_name',
        headerName: cfg.t.assignment_8b3f1a2c,
        width: 200,
        minWidth: 160,
        maxWidth: 320,
        filter: 'agTextColumnFilter',
        wrapText: true,
        autoHeight: true,
        cellRenderer: function(params) {
            return importGridTextCell(params.value);
        },
        cellStyle: {
            'white-space': 'normal',
            'line-height': '1.4',
            'display': 'flex',
            'align-items': 'flex-start',
            'padding-top': '6px',
            'padding-bottom': '6px'
        }
    },
    {
        field: 'template_name',
        headerName: cfg.t.template_1d7b5e8c,
        width: 180,
        minWidth: 140,
        maxWidth: 280,
        filter: 'customSetFilter',
        wrapText: true,
        autoHeight: true,
        cellRenderer: function(params) {
            return importGridTextCell(params.value);
        },
        cellStyle: {
            'white-space': 'normal',
            'line-height': '1.4',
            'display': 'flex',
            'align-items': 'flex-start',
            'padding-top': '6px',
            'padding-bottom': '6px'
        }
    },
    {
        field: 'document_type',
        headerName: cfg.t.document_type_4e7c9d1b,
        width: 160,
        minWidth: 120,
        maxWidth: 240,
        filter: 'customSetFilter',
        wrapText: true,
        autoHeight: true,
        cellRenderer: function(params) {
            return importGridTextCell(params.value);
        },
        cellStyle: {
            'white-space': 'normal',
            'line-height': '1.4',
            'display': 'flex',
            'align-items': 'flex-start',
            'padding-top': '6px',
            'padding-bottom': '6px'
        }
    },
    {
        field: 'period',
        headerName: cfg.t.period_9d4e2b7a,
        width: 120,
        minWidth: 90,
        maxWidth: 160,
        filter: 'agTextColumnFilter',
        cellRenderer: function(params) {
            return importGridTextCell(params.value);
        }
    },
    {
        field: 'source',
        headerName: cfg.t.source_type_6a4c9e2f,
        width: 170,
        minWidth: 140,
        maxWidth: 220,
        filter: 'customSetFilter',
        filterValueGetter: function(params) {
            return importGridSourceLabel(params.data && params.data.source);
        },
        cellRenderer: function(params) {
            return importGridTextCell(importGridSourceLabel(params.data && params.data.source));
        }
    },
    {
        field: 'language_display',
        headerName: cfg.t.language_4994a8ff,
        width: 100,
        minWidth: 80,
        maxWidth: 140,
        filter: 'customSetFilter',
        valueGetter: function(params) {
            const d = params.data || {};
            return (d.language_display || d.language || '').trim();
        },
        cellRenderer: function(params) {
            return importGridTextCell(params.value);
        }
    },
    {
        field: 'uploaded_by',
        headerName: cfg.t.uploaded_by_8e3c7a2d,
        width: 160,
        minWidth: 120,
        maxWidth: 220,
        filter: 'agTextColumnFilter',
        wrapText: true,
        autoHeight: true,
        cellRenderer: function(params) {
            return importGridTextCell(params.value);
        },
        cellStyle: {
            'white-space': 'normal',
            'line-height': '1.4',
            'display': 'flex',
            'align-items': 'flex-start',
            'padding-top': '6px',
            'padding-bottom': '6px'
        }
    },
    {
        field: 'status',
        headerName: cfg.t.status_ec53a8c4,
        width: 120,
        minWidth: 100,
        maxWidth: 160,
        filter: 'customSetFilter',
        cellRenderer: function(params) {
            const v = (params.value || '').trim();
            if (!v) return '<span class="text-xs text-gray-400">\u2014</span>';
            return '<span class="text-sm text-gray-700 capitalize">' + escapeHtml(v) + '</span>';
        }
    },
    {
        field: 'is_public',
        headerName: cfg.t.public_3d067bed,
        width: 100,
        minWidth: 90,
        maxWidth: 120,
        filter: 'customSetFilter',
        sortable: true,
        filterValueGetter: function(params) {
            const isPublic = params.data && (params.data.is_public === true || params.data.is_public === 'true' || params.data.is_public === 1);
            return isPublic ? cfg.t.public_3d067bed : cfg.t.not_public_20257be8;
        },
        cellRenderer: function(params) {
            const isPublic = params.data && (params.data.is_public === true || params.data.is_public === 'true' || params.data.is_public === 1);
            if (isPublic) {
                return '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">' +
                    escapeHtml(cfg.t.public_3d067bed) + '</span>';
            }
            return '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-700">' +
                escapeHtml(cfg.t.not_public_20257be8) + '</span>';
        },
        cellStyle: { 'white-space': 'nowrap' }
    },
    {
        field: 'uploaded_at',
        headerName: cfg.t.upload_date_4f2a9c1e,
        width: 160,
        minWidth: 140,
        maxWidth: 200,
        filter: 'agDateColumnFilter',
        sortable: true,
        cellRenderer: AgGridRenderers.dateTime,
        cellStyle: { 'white-space': 'nowrap' }
    },
    {
        field: 'source_url_unreachable',
        headerName: cfg.t.file_url_status_2a7c9e4b || 'File URL',
        width: 170,
        minWidth: 140,
        maxWidth: 220,
        filter: 'customSetFilter',
        sortable: true,
        filterValueGetter: function(params) {
            return importGridSourceUrlStatusLabel(params.data || {});
        },
        cellRenderer: function(params) {
            const data = params.data || {};
            const label = importGridSourceUrlStatusLabel(data);
            if (!data.source_url_unreachable) {
                if (data.file_pending) {
                    return '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-800">' +
                        '<i class="fas fa-clock mr-1"></i>' + escapeHtml(cfg.t.pending_2d13df6f) + '</span>';
                }
                return '<span class="text-xs text-gray-400">\u2014</span>';
            }
            return '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800" title="' +
                escapeAttr(cfg.t.file_url_unavailable_hint_1d6e8a3f || 'Excluded from AI import until IFRC fixes the document URL. Re-run FDRS sync to refresh.') + '">' +
                '<i class="fas fa-link-slash mr-1"></i>' + escapeHtml(label) + '</span>';
        },
        cellStyle: { 'white-space': 'nowrap' }
    },
    {
        field: 'ai_processed',
        headerName: cfg.t.ai_import_eca697b5,
        width: 200,
        minWidth: 160,
        maxWidth: 260,
        filter: 'customSetFilter',
        sortable: true,
        filterValueGetter: function(params) {
            return params.data && params.data.ai_processed ? cfg.t.processed_e6f641ae : cfg.t.not_processed_0fe381df;
        },
        cellRenderer: function(params) {
            const data = params.data || {};
            const processed = !!data.ai_processed;
            const badge = processed ?
                '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">' +
                '<i class="fas fa-check-circle mr-1"></i>' + escapeHtml(cfg.t.processed_e6f641ae) + '</span>' :
                '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-700">' +
                '<i class="fas fa-clock mr-1"></i>' + escapeHtml(cfg.t.not_processed_0fe381df) + '</span>';
            return '<div class="flex items-center flex-wrap gap-1">' + badge + '</div>';
        },
        cellStyle: { 'white-space': 'nowrap' }
    }
];

function syncImportSelectionFromGrid() {
    if (!importDocumentsGridHelper) {
        selectedDocuments.clear();
        updateSelectedCount();
        return;
    }
    const rows = importDocumentsGridHelper.getSelectedRows();
    selectedDocuments.clear();
    rows.forEach(function(row) {
        if (row && row.id != null && !row.ai_processed && !row.source_url_unreachable) {
            selectedDocuments.add(row.id);
        }
    });
    updateSelectedCount();
}

function restoreDocumentsPageGridGlobals() {
    try {
        if (typeof documentsGridApi !== 'undefined' && documentsGridApi) {
            window.gridApi = documentsGridApi;
        }
        if (typeof documentsGridHelper !== 'undefined' && documentsGridHelper) {
            window.gridHelper = documentsGridHelper;
            if (documentsGridHelper.columnVisibilityManager) {
                window.columnVisibilityManager = documentsGridHelper.columnVisibilityManager;
            }
        }
    } catch (e) { /* ignore */ }
}

function attachImportDocumentsGridLinkGuard() {
    const gridEl = document.getElementById('importDocumentsGrid');
    if (!gridEl || gridEl.dataset.importLinkGuard === '1') return;
    gridEl.dataset.importLinkGuard = '1';
    gridEl.addEventListener('click', function(ev) {
        if (ev.target.closest && ev.target.closest('a.import-system-doc-filename-link')) {
            ev.stopPropagation();
        }
    }, true);
}

function ensureImportDocumentsGrid(rowData) {
    const loadingEl = document.getElementById('importDocumentsGrid-loading');
    const emptyEl = document.getElementById('importDocumentsGrid-empty');
    const containerEl = document.getElementById('importDocumentsGrid-container');

    if (!importDocumentsGridHelper) {
        try {
            importDocumentsGridHelper = new AgGridHelper({
                containerId: 'importDocumentsGrid',
                templateId: 'ai-import-system-docs',
                columnDefs: importSystemDocumentsColumnDefs,
                rowData: rowData || [],
                options: getImportSystemDocumentsGridOptions(),
                columnVisibilityOptions: {
                    showPanelButton: true,
                    buttonPlaceholderId: 'importDocumentsGrid-colvis-placeholder',
                    enableExport: false,
                    enableReset: true
                },
                heightOptions: {
                    useParentContainerHeight: true,
                    minHeight: 280,
                    maxHeight: 520,
                    absoluteMinHeight: 240,
                    viewportOffset: 140
                }
            });
            importDocumentsGridApi = importDocumentsGridHelper.initialize();
            attachImportDocumentsGridLinkGuard();
            restoreDocumentsPageGridGlobals();
            window.importDocumentsGridApi = importDocumentsGridApi;
            window.importDocumentsGridHelper = importDocumentsGridHelper;
        } catch (e) {
            console.error('Import system documents grid init failed:', e);
            importDocumentsGridHelper = null;
            importDocumentsGridApi = null;
            if (loadingEl) loadingEl.style.display = 'none';
            if (containerEl) containerEl.style.display = 'none';
            if (emptyEl) emptyEl.style.display = 'block';
            var initErr = document.getElementById('importDocumentsFetchError');
            if (initErr) {
                initErr.textContent = cfg.t.failed_to_load_documents_94b93867;
                initErr.classList.remove('hidden');
            }
            updateImportActionsVisibility(0);
            return;
        }
    } else {
        importDocumentsGridHelper.setRowData(rowData || []);
        if (importDocumentsGridApi && typeof importDocumentsGridApi.deselectAll === 'function') {
            importDocumentsGridApi.deselectAll();
        }
        syncImportSelectionFromGrid();
    }

    if (loadingEl) loadingEl.style.display = 'none';
    if (containerEl) containerEl.style.display = 'block';
    if (emptyEl) emptyEl.style.display = 'none';
    updateImportActionsVisibility((rowData || []).length);
    if (typeof window.requestAnimationFrame === 'function') {
        window.requestAnimationFrame(function() {
            window.requestAnimationFrame(function() {
                if (importDocumentsGridHelper && typeof importDocumentsGridHelper.setDynamicHeight === 'function') {
                    try {
                        importDocumentsGridHelper.setDynamicHeight();
                    } catch (e) { /* ignore */ }
                }
                var api = importDocumentsGridApi;
                if (api && typeof api.doLayout === 'function') {
                    try {
                        api.doLayout();
                    } catch (e) { /* ignore */ }
                }
            });
        });
    }
}

function updateImportActionsVisibility(rowCount) {
    importTabHasRows = (Number(rowCount) || 0) > 0;
    syncUploadImportModalFooter();
    if (importTabHasRows) {
        updateImportSelectedSummary();
    }
}

function updateImportSelectedSummary() {
    const summaryEl = document.getElementById('importSelectedSummary');
    const processBtn = document.getElementById('processSelectedBtn');
    const count = selectedDocuments.size;
    if (processBtn) {
        processBtn.disabled = count === 0;
    }
    if (summaryEl) {
        summaryEl.textContent = formatImportFooterSummary(count);
    }
}

async function loadSystemDocuments() {
    const loading = document.getElementById('importLoading');
    const errEl = document.getElementById('importDocumentsFetchError');
    const searchInput = document.getElementById('importSearch');

    if (!loading) return;

    if (errEl) {
        errEl.textContent = '';
        errEl.classList.add('hidden');
    }

    loading.classList.remove('hidden');
    selectedDocuments.clear();
    if (importDocumentsGridApi && typeof importDocumentsGridApi.deselectAll === 'function') {
        importDocumentsGridApi.deselectAll();
    }
    updateSelectedCount();

    try {
        const searchQuery = searchInput ? searchInput.value : '';
        const response = await ((window.getFetch && window.getFetch()) || fetch)('/admin/ai/documents/list-system-documents?q=' + encodeURIComponent(searchQuery) + '&limit=5000', {
            credentials: 'same-origin',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        });

        const result = await response.json();

        if (result.success) {
            const docs = Array.isArray(result.documents) ? result.documents : [];
            const sorted = docs.slice().sort(function(a, b) {
                return (a.ai_processed ? 1 : 0) - (b.ai_processed ? 1 : 0);
            });
            const rows = sorted.map(mapSystemDocumentToRow).filter(Boolean);
            ensureImportDocumentsGrid(rows);
            syncImportSelectionFromGrid();

            const totalMatching = Number(result.total);
            const returned = Number.isFinite(Number(result.returned)) ? Number(result.returned) : rows.length;
            if (importDocumentsGridHelper && typeof importDocumentsGridHelper.setResultCountTotal === 'function' && Number.isFinite(totalMatching)) {
                importDocumentsGridHelper.setResultCountTotal(totalMatching);
            }
            const truncEl = document.getElementById('importDocumentsTruncationHint');
            if (truncEl) {
                if (Number.isFinite(totalMatching) && totalMatching > returned) {
                    const msg = (cfg.t.showing_count_of_total_8f3c1a2b || 'Showing {returned} of {total} matching documents. Refine search to see more.')
                        .replace('{returned}', String(returned))
                        .replace('{total}', String(totalMatching));
                    truncEl.textContent = msg;
                    truncEl.classList.remove('hidden');
                } else {
                    truncEl.textContent = '';
                    truncEl.classList.add('hidden');
                }
            }
        } else {
            var errorMsg = result.error || cfg.t.error_loading_documents_a708c41e;
            if (errEl) {
                errEl.textContent = String(errorMsg || '');
                errEl.classList.remove('hidden');
            }
            if (importDocumentsGridHelper) {
                importDocumentsGridHelper.setRowData([]);
            }
            const truncEl = document.getElementById('importDocumentsTruncationHint');
            if (truncEl) {
                truncEl.textContent = '';
                truncEl.classList.add('hidden');
            }
            if (importDocumentsGridApi && typeof importDocumentsGridApi.deselectAll === 'function') {
                importDocumentsGridApi.deselectAll();
            }
            syncImportSelectionFromGrid();
            updateImportActionsVisibility(0);
        }
    } catch (error) {
        console.error('Error loading system documents:', error);
        if (errEl) {
            errEl.textContent = cfg.t.failed_to_load_documents_94b93867;
            errEl.classList.remove('hidden');
        }
        if (importDocumentsGridHelper) {
            importDocumentsGridHelper.setRowData([]);
        }
        const truncElCatch = document.getElementById('importDocumentsTruncationHint');
        if (truncElCatch) {
            truncElCatch.textContent = '';
            truncElCatch.classList.add('hidden');
        }
        if (importDocumentsGridApi && typeof importDocumentsGridApi.deselectAll === 'function') {
            importDocumentsGridApi.deselectAll();
        }
        syncImportSelectionFromGrid();
        updateImportActionsVisibility(0);
    } finally {
        loading.classList.add('hidden');
    }
}

function updateSelectedCount() {
    updateImportSelectedSummary();
}

// External API documents import functionality
let selectedIfrcDocuments = new Set();
let ifrcDocumentsGridHelper = null;
let ifrcDocumentsGridApi = null;
let ifrcImportInProgress = false;
let ifrcImportCancelled = false;

function onBeforeUnloadIfrcImport(e) {
    if (!ifrcImportInProgress) return;
    e.preventDefault();
    e.returnValue = cfg.t.import_is_in_progress_are_you_sure_you_w_bf66d0d2;
    return e.returnValue;
}
let ifrcCountriesLoaded = false;
let ifrcTypesLoaded = false;

function getIfrcTypeFilterListEl() {
    return document.getElementById('ifrcTypeFilterList');
}

function isIfrcTypeDropdownOpen() {
    const dd = document.getElementById('ifrcTypeFilterDropdown');
    return !!(dd && !dd.classList.contains('hidden'));
}

function setIfrcTypeDropdownOpen(open) {
    const dd = document.getElementById('ifrcTypeFilterDropdown');
    const btn = document.getElementById('ifrcTypeFilterToggle');
    if (!dd || !btn) return;
    if (open) {
        dd.classList.remove('hidden');
        btn.setAttribute('aria-expanded', 'true');
    } else {
        dd.classList.add('hidden');
        btn.setAttribute('aria-expanded', 'false');
    }
}

/** Checked AppealsTypeId values from the Type multiselect. */
function getIfrcTypeIdsChecked() {
    const list = getIfrcTypeFilterListEl();
    if (!list) return [];
    return Array.from(list.querySelectorAll('input[type="checkbox"][name="ifrc_type_option"]:checked')).map(function(cb) {
        return String(cb.value || '').trim();
    }).filter(Boolean);
}

function getIfrcTypeCheckboxCount() {
    const list = getIfrcTypeFilterListEl();
    if (!list) return 0;
    return list.querySelectorAll('input[type="checkbox"][name="ifrc_type_option"]').length;
}

function updateIfrcTypeFilterSummary() {
    const summary = document.getElementById('ifrcTypeFilterSummary');
    if (!summary) return;
    const checked = getIfrcTypeIdsChecked();
    const total = getIfrcTypeCheckboxCount();
    if (total === 0) {
        summary.textContent = cfg.t.no_types_loaded_62ef2d48;
        return;
    }
    if (checked.length === 0 || checked.length === total) {
        summary.textContent = cfg.t.all_types_134353eb;
    } else {
        summary.textContent = cfg.t.selected_91b442d3 + ': ' + checked.length + ' / ' + total;
    }
}

/** Comma-separated type IDs for country filter API, or '' when equivalent to all types. */
function getIfrcSelectedAppealsTypeIdsForCountryFilter() {
    const ids = getIfrcTypeIdsChecked();
    const total = getIfrcTypeCheckboxCount();
    if (total === 0) return '';
    if (ids.length === 0 || ids.length === total) return '';
    return ids.join(',');
}

/** appeals_type_ids query value for document list: 'all' or comma-separated IDs. */
function getIfrcAppealsTypeIdsParamForList() {
    const ids = getIfrcTypeIdsChecked();
    const total = getIfrcTypeCheckboxCount();
    if (total === 0) return 'all';
    if (ids.length === 0 || ids.length === total) return 'all';
    return ids.join(',');
}

// Load document types into the Type multiselect. When countryName is set, filter to types applicable for that country.
async function loadIfrcTypes(countryName) {
    if (!countryName && ifrcTypesLoaded) return;

    const listEl = getIfrcTypeFilterListEl();
    if (!listEl) return;

    const previousChecked = new Set(getIfrcTypeIdsChecked());

    try {
        const url = countryName
            ? '/api/ai/documents/ifrc-api/filter-options?country_name=' + encodeURIComponent(countryName)
            : '/api/ai/documents/ifrc-api/types';
        const response = await csrfFetch(url, {
            method: 'GET',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });

        const result = await response.json();

        if (result.success && Array.isArray(result.types)) {
            listEl.innerHTML = '';

            const hasGroups = result.types.some(function(t) { return t.group; });
            let lastGroupKey = null;

            result.types.forEach(function(t) {
                const id = String(t.id != null ? t.id : '').trim();
                const name = t.name || id;
                if (!id) return;

                if (hasGroups) {
                    const raw = (t.group || '').trim();
                    const gKey = raw || '__other__';
                    const gLabel = raw || cfg.t.other_6311ae17;
                    if (gKey !== lastGroupKey) {
                        lastGroupKey = gKey;
                        const gh = document.createElement('div');
                        gh.className = 'text-xs font-semibold text-gray-500 pt-2 first:pt-0 pb-1';
                        gh.textContent = gLabel;
                        listEl.appendChild(gh);
                    }
                }

                const label = document.createElement('label');
                label.className = 'flex items-center gap-2 cursor-pointer hover:bg-gray-50 rounded px-1 py-0.5';
                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.name = 'ifrc_type_option';
                cb.value = id;
                cb.className = 'rounded border-gray-300 text-blue-600 focus:ring-blue-500';
                const span = document.createElement('span');
                span.className = 'text-sm text-gray-800';
                span.textContent = name;
                label.appendChild(cb);
                label.appendChild(span);
                listEl.appendChild(label);
            });

            if (!countryName) ifrcTypesLoaded = true;

            if (previousChecked.size) {
                listEl.querySelectorAll('input[name="ifrc_type_option"]').forEach(function(cb) {
                    cb.checked = previousChecked.has(String(cb.value));
                });
            }
            updateIfrcTypeFilterSummary();
        }
    } catch (error) {
        console.error('Error loading external API document types:', error);
    }
}

// Load countries into the dropdown. When appealsTypeIds is set, filter to countries with docs of that type.
async function loadIfrcCountries(appealsTypeIds) {
    if (!appealsTypeIds && ifrcCountriesLoaded) return;

    const countrySelect = document.getElementById('ifrcCountryNameFilter');
    if (!countrySelect) return;

    const currentCountry = countrySelect ? countrySelect.value : '';

    try {
        let countries = [];
        if (appealsTypeIds) {
            const url = '/api/ai/documents/ifrc-api/filter-options?appeals_type_ids=' + encodeURIComponent(appealsTypeIds);
            const response = await csrfFetch(url, {
                method: 'GET',
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
            const result = await response.json();
            if (result.success && Array.isArray(result.countries)) {
                countries = result.countries;
            }
        } else {
            const baseUrl = window.location.origin || 'http://localhost:5000';
            const countrymapUrl = baseUrl + '/api/v1/countrymap';
            const response = await ((window.getFetch && window.getFetch()) || fetch)(countrymapUrl, {
                method: 'GET',
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
            if (!response.ok) throw new Error('HTTP error! status: ' + response.status);
            const countriesData = await response.json();
            if (Array.isArray(countriesData)) {
                countries = countriesData;
            } else if (countriesData && Array.isArray(countriesData.countries)) {
                countries = countriesData.countries;
            }
        }

        countries.sort((a, b) => {
            const nameA = (a.name || a.localized_name || '').toLowerCase();
            const nameB = (b.name || b.localized_name || '').toLowerCase();
            return nameA.localeCompare(nameB);
        });

        countrySelect.innerHTML = '<option value="">' + escapeHtml(cfg.t.all_countries_74202da6) + '</option>';
        countries.forEach(country => {
            const countryName = country.name || country.localized_name;
            if (countryName) {
                const option = document.createElement('option');
                option.value = countryName;
                option.textContent = countryName;
                countrySelect.appendChild(option);
            }
        });

        if (!appealsTypeIds) ifrcCountriesLoaded = true;

        if (currentCountry && Array.from(countrySelect.options).some(o => o.value === currentCountry)) {
            countrySelect.value = currentCountry;
        } else {
            countrySelect.value = '';
        }
    } catch (error) {
        console.error('Error loading countries:', error);
        if (countrySelect) {
            countrySelect.innerHTML = '<option value="">' + escapeHtml(cfg.t.error_loading_countries_b47e1f6f) + '</option>';
        }
    }
}

/** Populate document-type multiselect and country dropdown (first tab visit, Search, Refresh). */
async function ensureIfrcFilterDropdowns() {
    await Promise.all([loadIfrcTypes(''), loadIfrcCountries('')]);
}

function mapIfrcDocumentToRow(doc, importedSet) {
    if (!doc) return null;
    const url = String(doc.url || '');
    return {
        url: url,
        title: doc.title || doc.base_filename || '',
        type: doc.type || '',
        year: doc.year != null && doc.year !== '' ? String(doc.year) : '',
        country_name: doc.country_name || '',
        country_code: doc.country_code || '',
        country_id: doc.country_id != null ? doc.country_id : null,
        already_imported: !!(url && importedSet.has(url))
    };
}

function getIfrcDocumentsGridOptions() {
    return {
        rowSelection: {
            mode: 'multiRow',
            enableClickSelection: true,
            selectAll: 'filtered'
        },
        isRowSelectable: function(node) {
            return !!(node && node.data && !node.data.already_imported);
        },
        onSelectionChanged: function() {
            syncIfrcSelectionFromGrid();
        },
        paginationPageSize: 25,
        defaultColDef: {
            wrapText: false,
            autoHeight: false,
            sortable: true,
            resizable: true,
            cellStyle: {
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'flex-start'
            }
        }
    };
}

const ifrcDocumentsColumnDefs = [
    {
        field: 'title',
        headerName: cfg.t.document_09453598,
        flex: 1,
        minWidth: 220,
        filter: 'agTextColumnFilter',
        wrapText: true,
        autoHeight: true,
        valueGetter: function(params) {
            const d = params.data || {};
            return (d.title || '').trim();
        },
        cellRenderer: function(params) {
            const d = params.data || {};
            const title = escapeHtml(d.title || '');
            const wrap = 'white-space:normal;overflow-wrap:anywhere;word-break:break-word;max-width:100%';
            const safeHref = sanitizeUrl(d.url || '');
            const canLink = !!(safeHref && safeHref !== '#');
            const titleLine = canLink ?
                '<a href="' + escapeAttr(safeHref) + '" class="ifrc-doc-title-link text-sm font-medium text-blue-600 hover:text-blue-800 hover:underline" style="' + wrap + '" ' +
                'target="_blank" rel="noopener noreferrer" title="' + escapeAttr(cfg.t.open_document_18c0765a) + '">' + title + '</a>' :
                '<div class="text-sm font-medium text-gray-900" style="' + wrap + '" title="' + escapeAttr(d.title || '') + '">' + title + '</div>';
            return '<div class="flex items-start gap-2 min-w-0" style="width:100%">' +
                '<div class="flex-shrink-0 text-red-500" style="padding-top:2px"><i class="fas fa-file-pdf text-xl"></i></div>' +
                '<div class="min-w-0 flex-1" style="' + wrap + '">' + titleLine + '</div></div>';
        },
        cellStyle: {
            'white-space': 'normal',
            'line-height': '1.4',
            'display': 'flex',
            'align-items': 'flex-start',
            'padding-top': '6px',
            'padding-bottom': '6px'
        }
    },
    {
        field: 'type',
        headerName: cfg.t.type_a1fa2777,
        width: 200,
        minWidth: 140,
        maxWidth: 320,
        filter: 'customSetFilter',
        cellRenderer: function(params) {
            const v = (params.value || '').trim();
            if (!v) return '<span class="text-xs text-gray-400">\u2014</span>';
            return '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-50 text-blue-800">' + escapeHtml(v) + '</span>';
        }
    },
    {
        field: 'year',
        headerName: cfg.t.year_537c66b2,
        width: 100,
        minWidth: 80,
        maxWidth: 120,
        filter: 'agTextColumnFilter',
        cellRenderer: function(params) {
            const v = params.value;
            if (v === '' || v == null) return '<span class="text-xs text-gray-400">\u2014</span>';
            return '<span class="text-sm text-gray-700">' + escapeHtml(String(v)) + '</span>';
        }
    },
    {
        field: 'country_name',
        headerName: cfg.t.country_59716c97,
        width: 160,
        minWidth: 120,
        maxWidth: 220,
        filter: 'agTextColumnFilter',
        wrapText: true,
        autoHeight: true,
        valueGetter: function(params) {
            const d = params.data || {};
            const name = (d.country_name || '').trim();
            const code = (d.country_code || '').trim();
            return name || code || '';
        },
        cellRenderer: function(params) {
            const d = params.data || {};
            const wrap = 'white-space:normal;overflow-wrap:anywhere;word-break:break-word;max-width:100%';
            if (d.country_name) {
                return '<span class="text-sm text-gray-700" style="' + wrap + '">' + escapeHtml(d.country_name) + '</span>';
            }
            if (d.country_code) {
                return '<span class="text-sm text-gray-700" style="' + wrap + '">' + escapeHtml(d.country_code) + '</span>';
            }
            return '<span class="text-xs text-gray-400">\u2014</span>';
        },
        cellStyle: {
            'white-space': 'normal',
            'line-height': '1.4',
            'display': 'flex',
            'align-items': 'flex-start',
            'padding-top': '6px',
            'padding-bottom': '6px'
        }
    }
];

function syncIfrcSelectionFromGrid() {
    selectedIfrcDocuments.clear();
    if (ifrcDocumentsGridHelper) {
        ifrcDocumentsGridHelper.getSelectedRows().forEach(function(row) {
            if (row && row.url && !row.already_imported) {
                selectedIfrcDocuments.add(row.url);
            }
        });
    }
    updateIfrcSelectedCount();
}

function attachIfrcDocumentsGridLinkGuard() {
    const gridEl = document.getElementById('ifrcDocumentsGrid');
    if (!gridEl || gridEl.dataset.ifrcLinkGuard === '1') return;
    gridEl.dataset.ifrcLinkGuard = '1';
    gridEl.addEventListener('click', function(ev) {
        if (ev.target.closest && ev.target.closest('a.ifrc-doc-title-link')) {
            ev.stopPropagation();
        }
    }, true);
}

function updateIfrcActionsVisibility(rowCount) {
    ifrcTabHasRows = (Number(rowCount) || 0) > 0;
    syncUploadImportModalFooter();
    if (ifrcTabHasRows) {
        updateIfrcSelectedSummary();
    }
}

function updateIfrcSelectedSummary() {
    const summaryEl = document.getElementById('ifrcSelectedSummary');
    const importBtn = document.getElementById('ifrcImportSelectedBtn');
    const count = selectedIfrcDocuments.size;
    if (importBtn) {
        importBtn.disabled = count === 0;
    }
    if (summaryEl) {
        summaryEl.textContent = formatImportFooterSummary(count);
    }
}

function ensureIfrcDocumentsGrid(rowData) {
    const loadingEl = document.getElementById('ifrcDocumentsGrid-loading');
    const emptyEl = document.getElementById('ifrcDocumentsGrid-empty');
    const containerEl = document.getElementById('ifrcDocumentsGrid-container');
    const rows = rowData || [];

    if (!ifrcDocumentsGridHelper) {
        try {
            ifrcDocumentsGridHelper = new AgGridHelper({
                containerId: 'ifrcDocumentsGrid',
                templateId: 'ai-ifrc-api-documents',
                columnDefs: ifrcDocumentsColumnDefs,
                rowData: rows,
                options: getIfrcDocumentsGridOptions(),
                columnVisibilityOptions: {
                    showPanelButton: false,
                    enableExport: false,
                    enableReset: true
                },
                heightOptions: {
                    useParentContainerHeight: true,
                    minHeight: 280,
                    maxHeight: 520,
                    absoluteMinHeight: 240,
                    viewportOffset: 140
                }
            });
            ifrcDocumentsGridApi = ifrcDocumentsGridHelper.initialize();
            attachIfrcDocumentsGridLinkGuard();
            restoreDocumentsPageGridGlobals();
            window.ifrcDocumentsGridApi = ifrcDocumentsGridApi;
            window.ifrcDocumentsGridHelper = ifrcDocumentsGridHelper;
        } catch (e) {
            console.error('IFRC documents grid init failed:', e);
            ifrcDocumentsGridHelper = null;
            ifrcDocumentsGridApi = null;
            if (loadingEl) loadingEl.style.display = 'none';
            if (containerEl) containerEl.style.display = 'none';
            if (emptyEl) emptyEl.style.display = 'block';
            var initErr = document.getElementById('ifrcDocumentsFetchError');
            if (initErr) {
                initErr.textContent = cfg.t.failed_to_load_documents_from_external_a_6a7d9a35;
                initErr.classList.remove('hidden');
            }
            updateIfrcActionsVisibility(0);
            return;
        }
    } else {
        ifrcDocumentsGridHelper.setRowData(rows);
        if (ifrcDocumentsGridApi && typeof ifrcDocumentsGridApi.deselectAll === 'function') {
            ifrcDocumentsGridApi.deselectAll();
        }
        syncIfrcSelectionFromGrid();
    }

    if (loadingEl) loadingEl.style.display = 'none';
    if (containerEl) containerEl.style.display = 'block';
    if (emptyEl) emptyEl.style.display = 'none';
    updateIfrcActionsVisibility(rows.length);
    if (typeof window.requestAnimationFrame === 'function') {
        window.requestAnimationFrame(function() {
            window.requestAnimationFrame(function() {
                if (ifrcDocumentsGridHelper && typeof ifrcDocumentsGridHelper.setDynamicHeight === 'function') {
                    try {
                        ifrcDocumentsGridHelper.setDynamicHeight();
                    } catch (e) { /* ignore */ }
                }
                var api = ifrcDocumentsGridApi;
                if (api && typeof api.doLayout === 'function') {
                    try {
                        api.doLayout();
                    } catch (e) { /* ignore */ }
                }
            });
        });
    }
}

async function loadIfrcApiDocuments() {
    const loading = document.getElementById('ifrcLoading');
    const yearFilter = document.getElementById('ifrcYearFilter');
    const countryNameFilter = document.getElementById('ifrcCountryNameFilter');
    const shell = document.getElementById('ifrcDocumentsGridShell');
    const hint = document.getElementById('ifrcDocumentsEmptyHint');
    const errEl = document.getElementById('ifrcDocumentsFetchError');

    if (!loading) return;

    if (hint) hint.classList.add('hidden');
    if (shell) shell.classList.remove('hidden');
    syncUploadImportModalIfrcCompactLayout();
    if (errEl) {
        errEl.textContent = '';
        errEl.classList.add('hidden');
    }

    loading.classList.remove('hidden');
    selectedIfrcDocuments.clear();
    if (ifrcDocumentsGridApi && typeof ifrcDocumentsGridApi.deselectAll === 'function') {
        ifrcDocumentsGridApi.deselectAll();
    }
    updateIfrcSelectedCount();

    try {
        const params = new URLSearchParams();
        params.append('appeals_type_ids', getIfrcAppealsTypeIdsParamForList());
        if (yearFilter && yearFilter.value.trim()) {
            params.append('year_filter', yearFilter.value.trim());
        }
        if (countryNameFilter && countryNameFilter.value.trim()) {
            params.append('country_name', countryNameFilter.value.trim());
        }

        const response = await csrfFetch('/api/ai/documents/ifrc-api/list?' + params.toString(), {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        });

        const result = await response.json();

        if (result.success) {
            const importedSet = new Set(result.already_imported_urls || []);
            const docs = Array.isArray(result.documents) ? result.documents : [];
            const sorted = docs.slice().sort(function(a, b) {
                const au = a && a.url;
                const bu = b && b.url;
                return (importedSet.has(au) ? 1 : 0) - (importedSet.has(bu) ? 1 : 0);
            });
            const rows = sorted.map(function(doc) { return mapIfrcDocumentToRow(doc, importedSet); }).filter(Boolean);
            ensureIfrcDocumentsGrid(rows);
            syncIfrcSelectionFromGrid();
        } else {
            var errorMsg = result.error || cfg.t.error_loading_documents_a708c41e;
            if (errEl) {
                errEl.textContent = String(errorMsg || '');
                errEl.classList.remove('hidden');
            }
            if (ifrcDocumentsGridHelper) {
                ifrcDocumentsGridHelper.setRowData([]);
            } else if (shell) {
                ensureIfrcDocumentsGrid([]);
            }
            if (ifrcDocumentsGridApi && typeof ifrcDocumentsGridApi.deselectAll === 'function') {
                ifrcDocumentsGridApi.deselectAll();
            }
            syncIfrcSelectionFromGrid();
            updateIfrcActionsVisibility(0);
        }
    } catch (error) {
        console.error('Error loading external API documents:', error);
        if (errEl) {
            errEl.textContent = cfg.t.failed_to_load_documents_from_external_a_6a7d9a35;
            errEl.classList.remove('hidden');
        }
        if (ifrcDocumentsGridHelper) {
            ifrcDocumentsGridHelper.setRowData([]);
        } else if (shell) {
            ensureIfrcDocumentsGrid([]);
        }
        if (ifrcDocumentsGridApi && typeof ifrcDocumentsGridApi.deselectAll === 'function') {
            ifrcDocumentsGridApi.deselectAll();
        }
        syncIfrcSelectionFromGrid();
        updateIfrcActionsVisibility(0);
    } finally {
        loading.classList.add('hidden');
        syncUploadImportModalIfrcCompactLayout();
    }
}

function updateIfrcSelectedCount() {
    updateIfrcSelectedSummary();
}

// Import selected documents from external API (server-side bulk job; parallel)
async function importIfrcDocuments() {
    const importBtn = document.getElementById('ifrcImportSelectedBtn');
    if (!importBtn) return;

    let items = [];
    if (ifrcDocumentsGridHelper && typeof ifrcDocumentsGridHelper.getSelectedRows === 'function') {
        items = ifrcDocumentsGridHelper.getSelectedRows()
            .filter(function(row) { return row && row.url && !row.already_imported; })
            .map(function(row) {
                const countryId = row.country_id != null ? Number(row.country_id) : null;
                return {
                    url: row.url,
                    title: row.title || '',
                    is_public: true,
                    country_id: Number.isFinite(countryId) ? countryId : null,
                    country_name: row.country_name || null,
                };
            });
    }
    if (items.length === 0 && selectedIfrcDocuments.size > 0) {
        items = Array.from(selectedIfrcDocuments).map(function(url) {
            return {
                url: url,
                title: '',
                is_public: true,
                country_id: null,
                country_name: null,
            };
        });
    }
    if (items.length === 0) return;

    importBtn.disabled = true;
    const originalText = importBtn.innerHTML;
    importBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>' + escapeHtml(cfg.t.importing_fa072aec);

    const total = items.length;
    if (jobProgress && jobProgress.setStandaloneMode) jobProgress.setStandaloneMode(false);

    try {
        // Encode the payload as base64 so WAF content-inspection rules do not
        // false-positive on external URLs (go-api.ifrc.org/api/DownloadFile/…)
        // inside the request body. Backend decodes before reading items.
        const _importPayload = JSON.stringify({ items: items });
        const _importPayloadB64 = btoa(unescape(encodeURIComponent(_importPayload)));
        const response = await csrfFetch('/api/ai/documents/ifrc-api/import-bulk', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify({ payload: _importPayloadB64 })
        });
        const result = await response.json();
        if (!response.ok || !result || !result.success || !result.job_id) {
            throw new Error((result && result.error) ? result.error : 'Failed to start bulk import');
        }

        // Close modal and start server-backed job polling.
        const uploadModal = document.getElementById('uploadImportModal');
        if (uploadModal) {
            uploadModal.classList.add('hidden');
            document.body.style.overflow = '';
        }

        startIfrcImportJobPolling(result.job_id, total);

        // Reset UI selection
        selectedIfrcDocuments.clear();
        updateIfrcSelectedCount();
    } catch (e) {
        hideProcessingBanner();
        if (window.showAlert) {
            window.showAlert(cfg.t.failed_to_start_import_d9e1bb79 + ': ' + (e && e.message ? e.message : String(e)), 'error');
        } else {
            if (window.showAlert) window.showAlert(cfg.t.failed_to_start_import_d9e1bb79 + ': ' + (e && e.message ? e.message : String(e)), 'error');
            else console.error('Failed to start import:', e);
        }
    } finally {
        importBtn.disabled = false;
        importBtn.innerHTML = originalText;
    }
}

// Add event listener for import button; restore job after reload
function initImportJobs() {
    const importBtn = document.getElementById('ifrcImportSelectedBtn');
    if (importBtn) {
        importBtn.addEventListener('click', importIfrcDocuments);
    }
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initImportJobs);
} else {
    initImportJobs();
}

async function processSelectedDocuments() {
    if (selectedDocuments.size === 0) {
        if (window.showAlert) {
            window.showAlert(cfg.t.please_select_at_least_one_document_db0de074, 'warning');
        } else {
            if (window.showAlert) window.showAlert(cfg.t.please_select_at_least_one_document_db0de074, 'warning');
            else window.__clientWarn && window.__clientWarn('Please select at least one document');
        }
        return;
    }

    const docIds = Array.from(selectedDocuments);
    const confirmMsg = cfg.t.process_count_document_s_with_ai_this_wi_b44c5b13.replace('{count}', docIds.length);

    const proceedWithProcessing = async () => {
        const processBtn = document.getElementById('processSelectedBtn');
        const originalText = processBtn ? processBtn.innerHTML : '';
        if (processBtn) {
            processBtn.disabled = true;
            processBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>' + escapeHtml(cfg.t.processing_21d104a5);
        }

        if (typeof closeUploadModal === 'function') {
            closeUploadModal();
        }

        try {
            const response = await csrfFetch(importSystemBulkUrl(null), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({ submitted_document_ids: docIds })
            });

            let result = null;
            try {
                result = await response.json();
            } catch (parseError) {
                throw new Error('Invalid response from server');
            }

            if (!response.ok || !result || !result.success || !result.job_id) {
                const errMsg = (result && (result.error || result.message)) || ('HTTP ' + response.status);
                throw new Error(errMsg);
            }

            const total = Number(result.total) || docIds.length;
            startSystemImportJobPolling(result.job_id, total);
        } catch (error) {
            hideProcessingBanner();
            const errorMsg = error && error.message ? error.message : String(error);
            if (window.showAlert) {
                window.showAlert(cfg.t.failed_to_start_import_d9e1bb79 + ': ' + errorMsg, 'error');
            } else {
                console.error('Failed to start system import:', errorMsg);
            }
        } finally {
            if (processBtn) {
                processBtn.disabled = false;
                processBtn.innerHTML = originalText || ('<i class="fas fa-robot mr-2"></i>' + escapeHtml(cfg.t.process_selected_0401d5a2));
            }
        }
    };

    if (window.showConfirmation) {
        window.showConfirmation(
            confirmMsg,
            proceedWithProcessing,
            null,
            cfg.t.process_b6ec7abe,
            cfg.t.cancel_ea478870,
            cfg.t.process_documents_056842a0
        );
    } else {
        proceedWithProcessing();
    }
}

// Action handlers
const processBtn = document.getElementById('processSelectedBtn');
if (processBtn) {
    processBtn.addEventListener('click', function(e) {
        e.preventDefault();
        processSelectedDocuments();
    });
}

document.addEventListener('click', function(e) {
    const actionBtn = e.target.closest('[data-ai-doc-action]');
    if (!actionBtn) return;
    e.preventDefault();
    e.stopPropagation();
    const action = actionBtn.getAttribute('data-ai-doc-action');
    const docId = parseInt(actionBtn.getAttribute('data-doc-id') || '0');
    if (!docId) return;
    if (action === 'delete') {
        const title = actionBtn.getAttribute('data-doc-title') || 'Untitled';
        deleteDocument(docId, title);
    } else if (action === 'reprocess') {
        reprocessDocument(docId);
    } else if (action === 'toggle-public') {
        toggleDocumentPublic(docId, actionBtn);
    }
});

async function toggleDocumentPublic(docId, actionBtn) {
    const currentVal = actionBtn.getAttribute('data-is-public') === 'true';
    const newVal = !currentVal;
    actionBtn.disabled = true;
    try {
        const response = await csrfFetch('/api/ai/documents/' + docId, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify({ is_public: newVal })
        });
        const result = await response.json();
        if (!response.ok || !result.success) {
            const msg = (result && result.error) ? result.error : cfg.t.failed_to_update_0ff78b34;
            if (window.showAlert) window.showAlert(msg, 'error'); else console.error(msg);
            return;
        }
        updateDocumentInGrid(docId, { is_public: newVal });
    } catch (err) {
        const msg = err && err.message ? err.message : cfg.t.failed_to_update_0ff78b34;
        if (window.showAlert) window.showAlert(msg, 'error'); else console.error(msg);
    } finally {
        actionBtn.disabled = false;
    }
}

// Category inline select — change event (delegated on the grid container)
document.addEventListener('change', async function(e) {
    const sel = e.target && e.target.closest
        ? e.target.closest('select[data-ai-doc-action="change-category"]')
        : null;
    if (!sel) return;
    const docId = sel.getAttribute('data-doc-id');
    if (!docId) return;
    const newCat = sel.value;
    const prevCat = (function() {
        // find the previously selected option before the user changed it
        for (let i = 0; i < sel.options.length; i++) {
            if (sel.options[i].defaultSelected) return sel.options[i].value;
        }
        return '';
    })();
    sel.disabled = true;
    try {
        const response = await csrfFetch('/api/ai/documents/' + docId, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
            body: JSON.stringify({ document_category: newCat })
        });
        const result = await response.json();
        if (!response.ok || !result.success) {
            sel.value = prevCat; // revert
            const msg = (result && result.error) ? result.error : cfg.t.failed_to_update_category_e480510f;
            if (window.showAlert) window.showAlert(msg, 'error'); else console.error(msg);
            return;
        }
        // Mark new selection as default so revert works correctly next time
        for (let i = 0; i < sel.options.length; i++) {
            sel.options[i].defaultSelected = sel.options[i].value === newCat;
        }
        updateDocumentInGrid(docId, { document_category: newCat });
    } catch (err) {
        sel.value = prevCat; // revert on network error
        const msg = err && err.message ? err.message : cfg.t.failed_to_update_category_e480510f;
        if (window.showAlert) window.showAlert(msg, 'error'); else console.error(msg);
    } finally {
        sel.disabled = false;
    }
});

// Markdown rendering function
function renderMarkdown(text) {
    if (!text) return '';

    // Split into lines for processing
    const lines = text.split('\n');
    const result = [];
    let inCodeBlock = false;
    let codeBlockContent = [];
    let listStack = []; // Stack of {type, items, indent}

    function flushList() {
        if (listStack.length === 0) return;

        // Build nested lists from bottom up
        let current = null;
        while (listStack.length > 0) {
            const list = listStack.pop();
            const tag = list.type === 'ol' ? 'ol' : 'ul';
            const html = `<${tag}>${list.items.join('')}</${tag}>`;

            if (current) {
                // Nest the previous list inside the last item of current list
                const lastIdx = list.items.length - 1;
                if (lastIdx >= 0) {
                    list.items[lastIdx] = list.items[lastIdx].replace('</li>', current + '</li>');
                }
            }
            current = html;
        }

        if (current) {
            result.push(current);
        }
    }

    function addListItem(content, indent, type) {
        // Close lists with greater or equal indentation
        while (listStack.length > 0 && listStack[listStack.length - 1].indent >= indent) {
            const popped = listStack.pop();
            const tag = popped.type === 'ol' ? 'ol' : 'ul';
            const html = `<${tag}>${popped.items.join('')}</${tag}>`;

            if (listStack.length > 0) {
                // Nest into previous level's last item
                const prev = listStack[listStack.length - 1];
                const lastIdx = prev.items.length - 1;
                if (lastIdx >= 0) {
                    prev.items[lastIdx] = prev.items[lastIdx].replace('</li>', html + '</li>');
                }
            } else {
                result.push(html);
            }
        }

        // Add to current level or create new level
        if (listStack.length > 0 && listStack[listStack.length - 1].indent === indent) {
            // Same indentation level - add to existing list
            listStack[listStack.length - 1].items.push('<li>' + processInline(content) + '</li>');
        } else {
            // New indentation level - create new list
            listStack.push({
                type: type,
                items: ['<li>' + processInline(content) + '</li>'],
                indent: indent
            });
        }
    }

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const trimmed = line.trim();

        // Code blocks
        if (trimmed.startsWith('```')) {
            if (inCodeBlock) {
                // End code block
                result.push('<pre><code>' + escapeHtml(codeBlockContent.join('\n')) + '</code></pre>');
                codeBlockContent = [];
                inCodeBlock = false;
            } else {
                // Start code block
                flushList();
                inCodeBlock = true;
            }
            continue;
        }

        if (inCodeBlock) {
            codeBlockContent.push(line);
            continue;
        }

        // Headers
        if (trimmed.startsWith('### ')) {
            flushList();
            result.push('<h3>' + processInline(trimmed.substring(4)) + '</h3>');
            continue;
        }
        if (trimmed.startsWith('## ')) {
            flushList();
            result.push('<h2>' + processInline(trimmed.substring(3)) + '</h2>');
            continue;
        }
        if (trimmed.startsWith('# ')) {
            flushList();
            result.push('<h1>' + processInline(trimmed.substring(2)) + '</h1>');
            continue;
        }

        // Horizontal rule
        if (trimmed === '---' || trimmed === '***') {
            flushList();
            result.push('<hr>');
            continue;
        }

        // Blockquote
        if (trimmed.startsWith('> ')) {
            flushList();
            result.push('<blockquote>' + processInline(trimmed.substring(2)) + '</blockquote>');
            continue;
        }

        // Unordered list - handle indentation for nested lists
        const ulMatch = line.match(/^(\s*)([\*\-\+]\s+)(.+)$/);
        if (ulMatch) {
            const indent = ulMatch[1].length;
            const content = ulMatch[3];
            addListItem(content, indent, 'ul');
            continue;
        }

        // Ordered list - handle indentation for nested lists
        const olMatch = line.match(/^(\s*)(\d+[\.\)]\s+)(.+)$/);
        if (olMatch) {
            const indent = olMatch[1].length;
            const content = olMatch[3];
            addListItem(content, indent, 'ol');
            continue;
        }

        // Empty line - flush lists if we have any
        if (trimmed === '') {
            flushList();
            if (result.length > 0 && !result[result.length - 1].endsWith('</p>') &&
                !result[result.length - 1].endsWith('</ul>') &&
                !result[result.length - 1].endsWith('</ol>')) {
                result.push('<br>');
            }
            continue;
        }

        // Regular paragraph
        flushList();
        result.push('<p>' + processInline(trimmed) + '</p>');
    }

    flushList();
    if (inCodeBlock && codeBlockContent.length > 0) {
        result.push('<pre><code>' + escapeHtml(codeBlockContent.join('\n')) + '</code></pre>');
    }

    return result.join('');

    function processInline(text) {
        // Escape HTML first
        let html = escapeHtml(text);

        // Links [text](url) - process first to avoid conflicts with citations
        // XSS fix: validate URLs before creating links
        html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, function(match, linkText, url) {
            const safeHref = escapeAttr(sanitizeUrl(url));
            return '<a href="' + safeHref + '" target="_blank" rel="noopener noreferrer">' + linkText + '</a>';
        });

        // Citations [1], [2], etc. - only match numeric citations that aren't part of links
        // Match [number] where number is 1-3 digits, not followed by (
        html = html.replace(/\[(\d{1,3})\](?!\()/g, '<span class="citation">[$1]</span>');

        // Code blocks should already be handled, but handle inline code
        html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

        // Bold (**text** or __text__) - do this first to avoid conflicts with italic
        html = html.replace(/\*\*([^*]+?)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/__([^_]+?)__/g, '<strong>$1</strong>');

        // Italic (*text* or _text_) - process after bold
        // Match single asterisk/underscore not part of double
        html = html.replace(/(^|[^*])\*([^*\n]+?)\*([^*]|$)/g, '$1<em>$2</em>$3');
        html = html.replace(/(^|[^_])_([^_\n]+?)_([^_]|$)/g, '$1<em>$2</em>$3');

        return html;
    }
}

// Helper functions
function getFileTypeIcon(filename) {
    const ext = filename.split('.').pop().toLowerCase();
    const iconMap = {
        'pdf': '<i class="fas fa-file-pdf text-red-500 text-xl"></i>',
        'doc': '<i class="fas fa-file-word text-blue-500 text-xl"></i>',
        'docx': '<i class="fas fa-file-word text-blue-500 text-xl"></i>',
        'xls': '<i class="fas fa-file-excel text-green-500 text-xl"></i>',
        'xlsx': '<i class="fas fa-file-excel text-green-500 text-xl"></i>',
        'txt': '<i class="fas fa-file-alt text-gray-500 text-xl"></i>',
        'md': '<i class="fab fa-markdown text-gray-600 text-xl"></i>',
        'html': '<i class="fas fa-file-code text-orange-500 text-xl"></i>'
    };
    return iconMap[ext] || '<i class="fas fa-file text-gray-500 text-xl"></i>';
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

// Escape for HTML attribute context (e.g. title="", data-*)
function escapeAttr(value) {
    return String(value === null || value === undefined ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// XSS fix: sanitize URLs for href/src contexts
function sanitizeUrl(url) {
    if (!url) return '#';
    let decoded = url;
    try { decoded = decodeURIComponent(url); } catch(e) { /* ignore */ }
    const lower = String(decoded).toLowerCase().replace(/[\s\x00-\x1f]/g, '');
    if (/^(javascript|vbscript|data):/i.test(lower)) {
        return '#';
    }
    return String(url);
}

/**
 * XSS fix: Sanitize HTML to remove dangerous elements and attributes.
 * Allows safe tags for markdown rendering while blocking XSS vectors.
 */
function sanitizeHtml(html) {
    if (!html) return '';
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');

    // Allowed tags for markdown content
    const allowedTags = new Set([
        'p', 'br', 'strong', 'b', 'em', 'i', 'u', 's', 'strike',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'ul', 'ol', 'li', 'blockquote', 'pre', 'code',
        'a', 'span', 'div', 'table', 'thead', 'tbody', 'tr', 'th', 'td',
        'hr', 'sup', 'sub', 'mark'
    ]);

    // Allowed attributes per tag
    const allowedAttrs = {
        'a': ['href', 'target', 'rel', 'class'],
        'span': ['class'],
        'div': ['class'],
        'code': ['class'],
        'pre': ['class'],
        '*': ['class']  // class is allowed on all elements
    };

    // Dangerous protocols for href
    const dangerousProtocols = /^(javascript|vbscript|data):/i;

    function sanitizeNode(node) {
        if (node.nodeType === Node.TEXT_NODE) return;
        if (node.nodeType !== Node.ELEMENT_NODE) {
            node.remove();
            return;
        }

        const tagName = node.tagName.toLowerCase();

        // Remove disallowed tags but keep their text content
        if (!allowedTags.has(tagName)) {
            const text = document.createTextNode(node.textContent);
            node.replaceWith(text);
            return;
        }

        // Remove dangerous attributes
        const attrs = Array.from(node.attributes);
        for (const attr of attrs) {
            const attrName = attr.name.toLowerCase();
            const tagAllowed = allowedAttrs[tagName] || [];
            const globalAllowed = allowedAttrs['*'] || [];

            // Remove event handlers and dangerous attributes
            if (attrName.startsWith('on') ||
                (!tagAllowed.includes(attrName) && !globalAllowed.includes(attrName))) {
                node.removeAttribute(attr.name);
                continue;
            }

            // Sanitize href attributes (strip whitespace/control chars before testing)
            if (attrName === 'href') {
                var hrefVal = (attr.value || '').replace(/[\s\x00-\x1f]/g, '');
                if (dangerousProtocols.test(hrefVal)) {
                    node.removeAttribute('href');
                }
            }
        }

        // Recursively sanitize children
        Array.from(node.childNodes).forEach(sanitizeNode);
    }

    Array.from(doc.body.childNodes).forEach(sanitizeNode);
    return doc.body.innerHTML;
}

// Shared content area toggle functionality
const toggleAdvancedBtn = document.getElementById('toggleAdvancedOptions');
const toggleSourcesBtn = document.getElementById('toggleSources');
const sharedContentArea = document.getElementById('sharedContentArea');
const advancedOptionsContent = document.getElementById('advancedOptionsContent');
const sourcesContent = document.getElementById('sourcesContent');
const advancedChevron = document.getElementById('advancedChevron');
const sourcesChevron = document.getElementById('sourcesChevron');

function closeAllSections() {
    if (sharedContentArea) sharedContentArea.classList.add('hidden');
    if (advancedOptionsContent) advancedOptionsContent.classList.add('hidden');
    if (sourcesContent) sourcesContent.classList.add('hidden');
    if (advancedChevron) advancedChevron.style.transform = 'rotate(0deg)';
    if (sourcesChevron) sourcesChevron.style.transform = 'rotate(0deg)';
}

function openAdvancedOptions() {
    closeAllSections();
    if (sharedContentArea) sharedContentArea.classList.remove('hidden');
    if (advancedOptionsContent) advancedOptionsContent.classList.remove('hidden');
    if (advancedChevron) advancedChevron.style.transform = 'rotate(180deg)';
}

function openSources() {
    closeAllSections();
    if (sharedContentArea) sharedContentArea.classList.remove('hidden');
    if (sourcesContent) sourcesContent.classList.remove('hidden');
    if (sourcesChevron) sourcesChevron.style.transform = 'rotate(180deg)';
}

if (toggleAdvancedBtn) {
    toggleAdvancedBtn.addEventListener('click', function() {
        const isAdvancedOpen = !advancedOptionsContent?.classList.contains('hidden');
        if (isAdvancedOpen) {
            closeAllSections();
        } else {
            openAdvancedOptions();
        }
    });
}

if (toggleSourcesBtn) {
    toggleSourcesBtn.addEventListener('click', function() {
        const isSourcesOpen = !sourcesContent?.classList.contains('hidden');
        if (isSourcesOpen) {
            closeAllSections();
        } else {
            openSources();
        }
    });
}

// AI query (ask AI using document library)
const aiSearchForm = document.getElementById('aiSearchForm');
const aiSearchQuery = document.getElementById('aiSearchQuery');
const aiSearchMode = document.getElementById('aiSearchMode');
const aiSearchTopK = document.getElementById('aiSearchTopK');
const aiSearchMinScore = document.getElementById('aiSearchMinScore');
const aiSearchFileType = document.getElementById('aiSearchFileType');
const aiSearchStatus = document.getElementById('aiSearchStatus');
const aiSearchBtn = document.getElementById('aiSearchBtn');
const aiAnswerStatus = document.getElementById('aiAnswerStatus');
const aiAnswerOutput = document.getElementById('aiAnswerOutput');
const aiSearchBtnInitialHtml = aiSearchBtn ? aiSearchBtn.innerHTML : '';

function setAnswerStatus({ transport, model, issues } = {}) {
    if (!aiAnswerStatus) return;
    const parts = [];
    // XSS fix: escape all user-controlled values before inserting into innerHTML
    if (transport) parts.push(`<i class="fas fa-exchange-alt mr-1"></i>${escapeHtml(transport)}`);
    if (model) parts.push(`<i class="fas fa-brain mr-1"></i>${escapeHtml(model)}`);
    if (Array.isArray(issues) && issues.length) {
        const safeIssues = issues.map(issue => escapeHtml(issue)).join(' • ');
        parts.push(`<i class="fas fa-exclamation-triangle mr-1"></i>${safeIssues}`);
    }
    const html = parts.join(' <span class="mx-2 text-gray-300">|</span> ') || '';
    if (html) {
        aiAnswerStatus.innerHTML = html;
        aiAnswerStatus.classList.remove('hidden');
    } else {
        aiAnswerStatus.innerHTML = '';
        aiAnswerStatus.classList.add('hidden');
    }
}

function classifyModel(modelName) {
    const m = String(modelName || '').trim();
    if (!m) return { kind: 'unknown', label: null };
    if (m === 'table_records') return { kind: 'local', label: 'Local (table_records)' };
    if (m === 'upr_visual') return { kind: 'local', label: 'Local (upr_visual)' };
    if (m === 'metric_blocks') return { kind: 'local', label: 'Local (metric_blocks)' };
    if (m === 'people_reached_blocks') return { kind: 'local', label: 'Local (people_reached_blocks)' };
    if (m === 'people_to_be_reached_blocks') return { kind: 'local', label: 'Local (people_to_be_reached_blocks)' };
    if (m === 'participating_national_societies_blocks') return { kind: 'local', label: 'Local (participating_national_societies_blocks)' };
    if (m === 'financial_overview_blocks') return { kind: 'local', label: 'Local (financial_overview_blocks)' };
    if (m === 'none') return { kind: 'local', label: 'Local (no model used)' };
    if (m === 'error') return { kind: 'error', label: 'Error (backend)' };
    return { kind: 'model', label: m };
}

function normalizeSources(rawSources) {
    return Array.isArray(rawSources) ? rawSources : [];
}

function ensureAnswerShown(answerText, answerHtml) {
    if (!aiAnswerOutput) return;

    // Show the answer section when we have content
    const answerSection = document.getElementById('aiAnswerSection');
    if (answerSection && (answerText || answerHtml)) {
        answerSection.classList.remove('hidden');
    }

    if (answerHtml) {
        // XSS fix: sanitize HTML from external sources before inserting
        aiAnswerOutput.innerHTML = sanitizeHtml(answerHtml);
        return;
    }
    // renderMarkdown already escapes HTML, but sanitize for defense-in-depth
    aiAnswerOutput.innerHTML = sanitizeHtml(renderMarkdown(answerText || ''));
}

async function askViaWebSocket(payload) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/ai/documents/ws`;
    const ws = new WebSocket(wsUrl);

    let buffer = '';
    let receivedAny = false;
    let sources = [];
    let model = null;

    return await new Promise((resolve, reject) => {
        let settled = false;
        const timeoutMs = 120000;
        const timeoutId = setTimeout(() => {
            if (settled) return;
            settled = true;
            try { ws.close(); } catch (e) {}
            reject(new Error('WebSocket timeout'));
        }, timeoutMs);

        const cleanup = () => {
            clearTimeout(timeoutId);
            try { ws.onopen = null; ws.onmessage = null; ws.onerror = null; ws.onclose = null; } catch (e) {}
        };

        const safeResolve = (result) => {
            if (settled) return;
            settled = true;
            cleanup();
            try { ws.close(); } catch (e) {}
            resolve(result);
        };

        const safeReject = (err) => {
            if (settled) return;
            settled = true;
            cleanup();
            try { ws.close(); } catch (e) {}
            reject(err instanceof Error ? err : new Error(String(err || 'WebSocket failed')));
        };

        ws.onopen = function() {
            try {
                ws.send(JSON.stringify(payload));
            } catch (e) {
                safeReject(e);
            }
        };

        ws.onmessage = function(ev) {
            let msg;
            try { msg = JSON.parse(ev.data); } catch (e) { return; }
            if (!msg || !msg.type) return;

            if (msg.type === 'sources') {
                sources = normalizeSources(msg.sources);
                receivedAny = true;
                return;
            }

            if (msg.type === 'delta') {
                buffer += (msg.text || '');
                receivedAny = true;
                // Show answer section when streaming starts
                const answerSection = document.getElementById('aiAnswerSection');
                if (answerSection && buffer) {
                    answerSection.classList.remove('hidden');
                    // Show Sources button when answer starts streaming
                    const toggleSourcesBtn = document.getElementById('toggleSources');
                    if (toggleSourcesBtn) {
                        toggleSourcesBtn.classList.remove('hidden');
                    }
                }
                // While streaming, show plain text to avoid broken partial markdown rendering.
                if (aiAnswerOutput) aiAnswerOutput.textContent = buffer;
                return;
            }

            if (msg.type === 'done') {
                const answer = msg.answer || buffer || '';
                model = msg.model || null;
                safeResolve({ answer, sources: normalizeSources(msg.sources || sources), model });
                return;
            }

            if (msg.type === 'error') {
                const message = msg.message || 'Failed to generate answer.';
                safeReject(new Error(message));
            }
        };

        ws.onerror = function() {
            safeReject(new Error('WebSocket connection error'));
        };

        ws.onclose = function() {
            if (!receivedAny) {
                safeReject(new Error('WebSocket closed before response'));
            } else {
                // If we already received deltas/sources but didn't get "done", return what we have.
                safeResolve({ answer: buffer || '', sources: normalizeSources(sources), model });
            }
        };
    });
}

function renderAnswerSources(sources) {
    const sourcesContentEl = document.getElementById('sourcesContent');
    if (!sourcesContentEl) return;
    const sourcesContainer = sourcesContentEl.querySelector('.space-y-2');
    if (!sourcesContainer) return;

    // Show the sources container if there are sources
    if (sources && sources.length > 0) {
        openSources();
    }

    if (!sources || sources.length === 0) {
        sourcesContainer.innerHTML = '<div class="text-sm text-gray-500 italic flex items-center gap-2"><i class="fas fa-info-circle"></i>' + escapeHtml(cfg.t.no_sources_found_1203fa96) + '</div>';
        return;
    }

    sourcesContainer.innerHTML = sources.map((s, index) => {
        const filename = escapeHtml(s.filename || s.title || cfg.t.document_09453598);
        const pageInfo = s.page_label
            ? escapeHtml(s.page_label)
            : (s.page_number ? `${cfg.t.page_193cfc9b} ${s.page_number}` : `${cfg.t.page_193cfc9b} ${cfg.t.n_a_382b0f51}`);
        const score = typeof s.score === 'number' ? s.score.toFixed(3) : '';
        const fileIcon = getFileTypeIcon(s.filename || s.title || '');
        return `
            <div class="flex items-center gap-2 p-2 bg-white rounded border border-gray-200 hover:border-blue-300 hover:shadow-sm transition-all">
                <span class="flex-shrink-0 w-6 h-6 bg-blue-100 text-blue-700 rounded-full flex items-center justify-center text-xs font-semibold">${index + 1}</span>
                <div class="flex-shrink-0">${fileIcon}</div>
                <div class="flex-1 min-w-0 flex items-center gap-2 text-sm text-gray-800">
                    <span class="font-medium truncate">${filename}</span>
                    <span class="text-gray-500">•</span>
                    <span class="text-xs text-gray-600 whitespace-nowrap">${pageInfo}</span>
                    ${score ? `<span class="text-gray-500">•</span><span class="text-xs text-gray-600 whitespace-nowrap"><i class="fas fa-star text-yellow-500 mr-1"></i>${score}</span>` : ''}
                </div>
            </div>
        `;
    }).join('');
}

// AI search form handler
if (aiSearchForm) {
    aiSearchForm.addEventListener('submit', async function(e) {
        e.preventDefault();

        const query = (aiSearchQuery?.value || '').trim();
        if (!query) {
            if (aiSearchStatus) {
                const statusSpan = aiSearchStatus.querySelector('span');
                if (statusSpan) {
                    statusSpan.textContent = cfg.t.please_enter_a_query_4ad9a6c1;
                } else {
                    aiSearchStatus.innerHTML = '<i class="fas fa-exclamation-circle text-yellow-600"></i><span>' + escapeHtml(cfg.t.please_enter_a_query_4ad9a6c1) + '</span>';
                }
                aiSearchStatus.classList.remove('hidden');
                aiSearchStatus.classList.remove('bg-blue-50', 'border-blue-200', 'text-blue-700');
                aiSearchStatus.classList.add('bg-yellow-50', 'border-yellow-200', 'text-yellow-700');
            }
            return;
        }

        // Reset status styling
        if (aiSearchStatus) {
            aiSearchStatus.classList.remove('bg-yellow-50', 'border-yellow-200', 'text-yellow-700', 'bg-red-50', 'border-red-200', 'text-red-700');
            aiSearchStatus.classList.add('bg-blue-50', 'border-blue-200', 'text-blue-700');
        }

        // Store button reference
        const submitBtn = aiSearchBtn;
        if (!submitBtn) return;

        // Disable button and show loading
        submitBtn.disabled = true;
        // Keep the send button icon-only; just swap to a spinner while waiting.
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin text-lg" style="color: #2563eb !important;"></i>';

        const sourcesContentEl = document.getElementById('sourcesContent');
        const sourcesContainer = sourcesContentEl?.querySelector('.space-y-2');
        if (sourcesContainer) sourcesContainer.innerHTML = '';
        // Clear source count
        const sourcesCountEl = document.getElementById('sourcesCount');
        if (sourcesCountEl) {
            sourcesCountEl.textContent = '';
            sourcesCountEl.classList.add('hidden');
        }
        // Hide Sources button when starting new query
        const toggleSourcesBtn = document.getElementById('toggleSources');
        if (toggleSourcesBtn) {
            toggleSourcesBtn.classList.add('hidden');
        }
        // Close sources section when starting new query
        if (sourcesContentEl && !sourcesContentEl.classList.contains('hidden')) {
            closeAllSections();
        }
        // Show answer section with typing indicator
        const answerSection = document.getElementById('aiAnswerSection');
        if (answerSection) {
            answerSection.classList.remove('hidden');
        }
        if (aiAnswerOutput) {
            aiAnswerOutput.innerHTML = '<div class="flex items-center gap-2 text-gray-500"><span>' + escapeHtml(cfg.t.typing_066182d6) + '</span><span class="ai-typing-indicator" aria-hidden="true"><span></span><span></span><span></span></span></div>';
        }
        setAnswerStatus({ transport: null, model: null, issues: [] });

        const issues = [];
        const requestPayload = {
            type: 'answer',
            query,
            top_k: parseInt(aiSearchTopK?.value || '5', 10),
            min_score: parseFloat(aiSearchMinScore?.value || '0.35'),
            file_type: aiSearchFileType?.value || '',
            search_mode: aiSearchMode?.value || 'hybrid'
        };

        try {
            // Try WebSocket first (streaming), fallback to HTTP.
            if (typeof WebSocket === 'undefined') {
                issues.push('Using standard connection');
                throw new Error('WebSocket not supported');
            }

            const wsResult = await askViaWebSocket(requestPayload);
            const wsModelInfo = classifyModel(wsResult.model);
            // Temporarily disabled: Answered locally message
            // if (wsModelInfo.kind === 'local') {
            //     issues.push('Answered locally (no LLM call)');
            // } else
            if (wsModelInfo.kind === 'error') {
                issues.push('Backend reported an error model');
            } else if (wsModelInfo.kind === 'unknown') {
                issues.push('Model not reported');
            }

            ensureAnswerShown(wsResult.answer, null);
            renderAnswerSources(wsResult.sources);

            // Update source count in sources section
            const sourcesCountEl = document.getElementById('sourcesCount');
            const sourceCount = wsResult.sources?.length || 0;
            if (sourcesCountEl) {
                if (sourceCount > 0) {
                    sourcesCountEl.textContent = cfg.t.found_5d695cc2 + ' ' + sourceCount + ' ' + cfg.t.source_s_b7dcde0d;
                    sourcesCountEl.classList.remove('hidden');
                } else {
                    sourcesCountEl.textContent = '';
                    sourcesCountEl.classList.add('hidden');
                }
            }
            setAnswerStatus({
                transport: 'WebSocket',
                model: wsModelInfo.label,
                issues
            });
        } catch (error) {
            // HTTP fallback
            try {
                if (!issues.includes('Using standard connection')) {
                    issues.push('Using standard connection');
                }
                const response = await csrfFetch('/api/ai/documents/answer', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: JSON.stringify({
                        query: requestPayload.query,
                        top_k: requestPayload.top_k,
                        min_score: requestPayload.min_score,
                        file_type: requestPayload.file_type,
                        search_mode: requestPayload.search_mode
                    })
                });

                const result = await response.json();
                if (result.success) {
                    const httpModelInfo = classifyModel(result.model);
                    // Temporarily disabled: Answered locally message
                    // if (httpModelInfo.kind === 'local') {
                    //     issues.push('Answered locally (no LLM call)');
                    // } else
                    if (httpModelInfo.kind === 'error') {
                        issues.push('Backend reported an error model');
                    } else if (httpModelInfo.kind === 'unknown') {
                        // Older backend responses may omit model on "no results" paths
                        issues.push('Model not reported');
                    }

                    ensureAnswerShown(result.answer || '', result.answer_html);
                    renderAnswerSources(normalizeSources(result.sources));

                    // Update source count in sources section
                    const sourcesCountEl = document.getElementById('sourcesCount');
                    const sourceCount = Array.isArray(result.sources) ? result.sources.length : 0;
                    if (sourcesCountEl) {
                        if (sourceCount > 0) {
                            sourcesCountEl.textContent = cfg.t.found_5d695cc2 + ' ' + sourceCount + ' ' + cfg.t.source_s_b7dcde0d;
                            sourcesCountEl.classList.remove('hidden');
                        } else {
                            sourcesCountEl.textContent = '';
                            sourcesCountEl.classList.add('hidden');
                        }
                    }
                    setAnswerStatus({
                        transport: 'HTTP',
                        model: httpModelInfo.label,
                        issues
                    });
                } else if (aiSearchStatus) {
                    const errorMsg = result.error || cfg.t.failed_to_generate_answer_9c78619e;
                    const statusSpan = aiSearchStatus.querySelector('span');
                    // XSS fix: escape error message before inserting
                    const safeErrorMsg = escapeHtml(errorMsg);
                    if (statusSpan) {
                        statusSpan.textContent = cfg.t.error_3d9f514d + ' ' + errorMsg;
                    } else {
                        aiSearchStatus.innerHTML = '<i class="fas fa-exclamation-triangle text-red-600"></i><span>' + escapeHtml(cfg.t.error_3d9f514d) + ' ' + safeErrorMsg + '</span>';
                    }
                    aiSearchStatus.classList.remove('hidden');
                    aiSearchStatus.classList.remove('bg-blue-50', 'border-blue-200', 'text-blue-700');
                    aiSearchStatus.classList.add('bg-red-50', 'border-red-200', 'text-red-700');
                    issues.push(result.error || 'Request failed');
                    setAnswerStatus({ transport: 'HTTP', model: null, issues });
                }
            } catch (e2) {
                console.error('AI query error:', e2);
                if (aiSearchStatus) {
                    const errorMsg = e2.message || cfg.t.failed_to_process_request_df530c1a;
                    const statusSpan = aiSearchStatus.querySelector('span');
                    // XSS fix: escape error message before inserting
                    const safeErrorMsg = escapeHtml(errorMsg);
                    if (statusSpan) {
                        statusSpan.textContent = cfg.t.error_3d9f514d + ' ' + errorMsg;
                    } else {
                        aiSearchStatus.innerHTML = '<i class="fas fa-exclamation-triangle text-red-600"></i><span>' + escapeHtml(cfg.t.error_3d9f514d) + ' ' + safeErrorMsg + '</span>';
                    }
                    aiSearchStatus.classList.remove('hidden');
                    aiSearchStatus.classList.remove('bg-blue-50', 'border-blue-200', 'text-blue-700');
                    aiSearchStatus.classList.add('bg-red-50', 'border-red-200', 'text-red-700');
                }
                issues.push(e2.message || 'HTTP request failed');
                setAnswerStatus({ transport: 'HTTP', model: null, issues });
            }
        } finally {
            // Re-enable button
            if (submitBtn) {
                submitBtn.disabled = false;
                // Restore original send button content (paper plane icon).
                submitBtn.innerHTML = aiSearchBtnInitialHtml || '<i class="fas fa-paper-plane text-lg" style="color: #2563eb !important;"></i>';
            }
        }
    });
}

// Add search functionality
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
        const searchInput = document.getElementById('importSearch');
        if (searchInput) {
            let searchTimeout;
            searchInput.addEventListener('input', function() {
                clearTimeout(searchTimeout);
                searchTimeout = setTimeout(loadSystemDocuments, 500);
            });
        }
    });
} else {
    const searchInput = document.getElementById('importSearch');
    if (searchInput) {
        let searchTimeout;
        searchInput.addEventListener('input', function() {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(loadSystemDocuments, 500);
        });
    }
}

async function deleteDocument(id, title) {
    const safeTitle = String(title || '').replace(/\s+/g, ' ').trim();
    const confirmMsg = cfg.t.delete_document_137e0e00 + ' "' + safeTitle + '"?';
    const proceedWithDelete = async () => {
        try {
            const response = await csrfFetch(`/admin/ai/documents/${id}/delete`, {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            const result = await response.json();

            if (result.success) {
                // Stop polling if it was running (prevents 404 spam after delete)
                stopProcessingPoll(id);
                removeTrackedProcessingDoc(id);
                removeDocumentFromGrid(id);
                if (window.showAlert) {
                    window.showAlert(cfg.t.document_deleted_369422de, 'success');
                }
            } else {
                if (window.showAlert) {
                    window.showAlert(cfg.t.error_3d9f514d + ' ' + result.error, 'error');
                } else {
                    if (window.showAlert) window.showAlert(cfg.t.error_3d9f514d + ' ' + result.error, 'error');
                    else console.error(result.error);
                }
            }
        } catch (error) {
            if (window.showAlert) {
                window.showAlert(cfg.t.error_3d9f514d + ' ' + error.message, 'error');
            } else {
                if (window.showAlert) window.showAlert(cfg.t.error_3d9f514d + ' ' + error.message, 'error');
                else console.error(error.message);
            }
        }
    };

    if (window.showDangerConfirmation) {
        window.showDangerConfirmation(
            confirmMsg,
            proceedWithDelete,
            null,
            cfg.t.delete_f2a6c498,
            cfg.t.cancel_ea478870,
            cfg.t.delete_document_616cd122
        );
    } else if (window.showConfirmation) {
        window.showConfirmation(
            confirmMsg,
            proceedWithDelete,
            null,
            cfg.t.delete_f2a6c498,
            cfg.t.cancel_ea478870,
            cfg.t.delete_document_616cd122
        );
    } else {
        if (window.confirm(confirmMsg)) proceedWithDelete();
    }
}

async function reprocessDocument(id) {
    const confirmMsg = cfg.t.reprocess_this_document_6e5046e8;
    const proceedWithReprocess = async () => {
        // Optimistically update the row UI immediately (spinner in Actions, status badge updates on poll)
        updateDocumentInGrid(id, { processing_status: 'pending', processing_error: '' });
        const requestTs = Date.now();
        updateTrackedProcessingDoc(id, { resetProgress: true, status: 'pending', stage: cfg.t.starting_8c6ce9f8, progress: 0, reprocessRequestedAt: requestTs, seenNonCompletedSinceRequest: false });
        showProcessingBanner(cfg.t.reprocessing_started_5259d906, cfg.t.preparing_0862f67f, 0);
        startProcessingPoll(id);

        try {
            const response = await csrfFetch(`/admin/ai/documents/${id}/reprocess`, {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            const result = await response.json();

            if (response.status === 202 || result.success) {
                // Background reprocess started; status polling reflects DB truth.
            } else {
                updateDocumentInGrid(id, { processing_status: 'failed', processing_error: result.error || '' });
                updateTrackedProcessingDoc(id, { status: 'failed', stage: 'Failed', progress: 100, error: result.error || '' });
                stopProcessingPoll(id);
                if (window.showAlert) {
                    window.showAlert(cfg.t.error_3d9f514d + ' ' + result.error, 'error');
                } else {
                    if (window.showAlert) window.showAlert(cfg.t.error_3d9f514d + ' ' + result.error, 'error');
                    else console.error(result.error);
                }
            }
        } catch (error) {
            console.error('Reprocess request error (polling continues):', error);
        }
    };

    if (window.showConfirmation) {
        window.showConfirmation(
            confirmMsg,
            proceedWithReprocess,
            null,
            cfg.t.reprocess_3f20034f,
            cfg.t.cancel_ea478870,
            cfg.t.reprocess_document_f2729c9f
        );
    } else {
        proceedWithReprocess();
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAiDocsJobProgress);
} else {
    initAiDocsJobProgress();
}

})();
