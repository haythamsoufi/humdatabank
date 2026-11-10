/**
 * Shared state and helpers for the AI Knowledge Base page modules.
 * Config is injected by knowledge_base.html before this module runs.
 */

export const cfg = window.aiDocumentsConfig || {};
if (!cfg.t) cfg.t = {};
if (!cfg.urls) cfg.urls = {};

export const page = {
    documentsGridApi: null,
    documentsGridHelper: null,
    closeUploadModal: function () {},
    importTabHasRows: false,
    ifrcTabHasRows: false,
    guidanceTabHasRows: false,
    selectedDocuments: new Set(),
    selectedIfrcDocuments: new Set(),
    selectedGuidanceIds: new Set(),
    guidanceDocumentsCache: [],
};

const AI_DOCS_DEBUG = !!cfg.debug;

export function onReady(fn) {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', fn);
    } else {
        fn();
    }
}

export function aiDocsLog() {
    if (!AI_DOCS_DEBUG) return;
    try {
        const args = ['[AI Docs]'].concat(Array.from(arguments));
        if (window.__clientLog) window.__clientLog.apply(null, args);
    } catch (e) { /* ignore */ }
}

export function escapeHtml(value) {
    if (typeof window.escapeHtml === 'function') return window.escapeHtml(value);
    return String(value == null ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

export function escapeAttr(value) {
    return String(value == null ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

export function sanitizeUrl(url) {
    if (!url) return '#';
    let decoded = url;
    try { decoded = decodeURIComponent(url); } catch (e) { /* ignore */ }
    const lower = String(decoded).toLowerCase().replace(/[\s\x00-\x1f]/g, '');
    if (/^(javascript|vbscript|data):/i.test(lower)) return '#';
    return String(url);
}

export function notifyDocs(msg, type) {
    if (window.showAlert) window.showAlert(msg, type || 'info');
    else window.alert(msg);
}

/**
 * Always ask before a destructive action. Falls back to window.confirm when
 * the shared dialog script did not load, and never runs onConfirm silently.
 */
export function confirmAction(message, onConfirm, options) {
    const opts = options || {};
    if (opts.danger && typeof window.showDangerConfirmation === 'function') {
        window.showDangerConfirmation(message, onConfirm, null, opts.confirmText, opts.cancelText, opts.title);
        return;
    }
    if (typeof window.showConfirmation === 'function') {
        window.showConfirmation(message, onConfirm, null, opts.confirmText, opts.cancelText, opts.title);
        return;
    }
    if (window.confirm(message)) {
        Promise.resolve().then(onConfirm).catch(function (err) {
            notifyDocs((err && err.message) ? err.message : String(err), 'error');
        });
    }
}

export function isCsrfFailureResponse(status, payload) {
    if (status !== 400 && status !== 403) return false;
    if (!payload) return false;
    if (payload.csrf_refresh_required || payload.error === 'CSRF validation failed') return true;
    const message = String(payload.message || payload.error || '').toLowerCase();
    return message.includes('csrf');
}

export function importSystemBulkUrl(suffix, jobId) {
    const urls = cfg.urls || {};
    const tpl = suffix === 'status'
        ? urls.importSystemBulkStatus
        : (suffix === 'cancel' ? urls.importSystemBulkCancel : urls.importSystemBulk);
    if (tpl && jobId) {
        return String(tpl).replace('__JOB__', encodeURIComponent(String(jobId)));
    }
    return tpl || ('/admin/ai/knowledge-base/import-system-bulk' + (suffix && jobId ? '/' + encodeURIComponent(String(jobId)) + '/' + suffix : ''));
}

function jobProgress() {
    return window.AiDocsJobProgress || null;
}

export function showProcessingBanner(title, detail, progress) {
    const jp = jobProgress();
    if (jp && jp.setStandaloneMode) jp.setStandaloneMode(true);
    if (jp && jp.showBanner) jp.showBanner(title, detail, progress);
}

export function hideProcessingBanner() {
    const jp = jobProgress();
    if (jp && jp.hideBanner) jp.hideBanner();
}

export function updateTrackedProcessingDoc(docId, patch) {
    const jp = jobProgress();
    if (jp && jp.updateDoc) jp.updateDoc(docId, patch);
}

export function startProcessingPoll(docId) {
    const jp = jobProgress();
    if (jp && jp.startDocPoll) jp.startDocPoll(docId);
}

export function stopProcessingPoll(docId) {
    const jp = jobProgress();
    if (jp && jp.stopDocPoll) jp.stopDocPoll(docId);
}

export function removeTrackedProcessingDoc(docId) {
    const jp = jobProgress();
    if (jp && jp.untrackDoc) jp.untrackDoc(docId);
    else stopProcessingPoll(docId);
}

export function startIfrcImportJobPolling(jobId, total) {
    const jp = jobProgress();
    if (jp && jp.startJob) jp.startJob('ifrc_api_bulk', jobId, total || 0);
}

export function startSystemImportJobPolling(jobId, total) {
    const jp = jobProgress();
    if (jp && jp.startJob) jp.startJob('docs.bulk_import_system', jobId, total || 0);
}

export function startBulkReprocessJobPolling(jobId, total) {
    const jp = jobProgress();
    if (jp && jp.activateJob) {
        jp.activateJob(jobId, 'docs.bulk_reprocess', total || 0);
        return;
    }
    if (jp && jp.startJob) jp.startJob('docs.bulk_reprocess', jobId, total || 0);
}

export function beginBulkReprocessJob(total, docIds, requestTs) {
    const jp = jobProgress();
    if (jp && jp.beginOptimisticJob) {
        jp.beginOptimisticJob('docs.bulk_reprocess', total || 0, docIds || [], { requestTs: requestTs || null });
    }
}

export function failBulkReprocessJob(docIds, errorMsg) {
    const jp = jobProgress();
    if (jp && jp.failOptimisticJob) jp.failOptimisticJob(docIds || [], errorMsg || '');
}

export function startBulkMetaReprocessJobPolling(jobId, total) {
    const jp = jobProgress();
    if (jp && jp.startJob) jp.startJob('docs.bulk_reprocess_metadata', jobId, total || 0);
}

export function getDocState(docId) {
    const jp = jobProgress();
    if (jp && jp.getDocState) return jp.getDocState(docId);
    return null;
}

export const DOCUMENT_CATEGORY_OPTIONS = [
    { value: '', label: cfg.t.none_49bd59b9 },
    { value: 'country_plan', label: cfg.t.country_plan_137beb42 },
    { value: 'country_report', label: cfg.t.country_report_6316677c },
    { value: 'strategic_plan', label: cfg.t.strategic_plan_13a00ea1 },
    { value: 'work_plan', label: cfg.t.work_plan_2a21b46b },
    { value: 'plan', label: cfg.t.plan_0b6cbdf7 },
    { value: 'dref', label: cfg.t.dref || 'DREF' },
    { value: 'emergency_appeal', label: cfg.t.emergency_appeal || 'Emergency Appeal' },
    { value: 'operations_update', label: cfg.t.operations_update || 'Operations Update' },
    { value: 'emergency_operation', label: cfg.t.emergency_operation || 'Emergency operation' },
    { value: 'sitrep', label: cfg.t.situation_report_eb2802e8 },
    { value: 'report', label: cfg.t.report_4b1b4dc8 },
    { value: 'assessment', label: cfg.t.assessment_29a99298 },
    { value: 'policy', label: cfg.t.policy_51359e8b },
    { value: 'guideline', label: cfg.t.guideline_a3928106 },
    { value: 'resolution', label: cfg.t.resolution_b5a4b64b },
    { value: 'data_sheet', label: cfg.t.data_sheet_063b405d },
    { value: 'training', label: cfg.t.training_cf270e40 },
    { value: 'other', label: cfg.t.other_6311ae17 },
];

export function getCategoryLabel(value) {
    if (!value) return '';
    const opt = DOCUMENT_CATEGORY_OPTIONS.find(function (o) { return o.value === value; });
    return opt ? opt.label : value.replace(/_/g, ' ');
}

export function geographySelectValue(data) {
    const scope = String((data && data.geographic_scope) || '').trim().toLowerCase();
    if (scope === 'global' || scope === 'regional' || scope === 'cluster') return 'scope:' + scope;
    const countryId = data && data.country_id != null ? Number(data.country_id) : NaN;
    if (Number.isFinite(countryId) && countryId > 0) return 'country:' + countryId;
    return 'scope:';
}

export function geographyPayloadFromSelectValue(value) {
    const raw = String(value || '');
    if (raw.indexOf('country:') === 0) {
        const countryId = Number(raw.slice('country:'.length));
        if (Number.isFinite(countryId) && countryId > 0) {
            return { geographic_scope: null, country_id: countryId };
        }
        return { geographic_scope: null, country_id: null };
    }
    const scope = raw.indexOf('scope:') === 0 ? raw.slice('scope:'.length) : raw;
    if (scope === 'global' || scope === 'regional' || scope === 'cluster') {
        return { geographic_scope: scope };
    }
    return { geographic_scope: null, country_id: null };
}

export function scopeLabel(scope) {
    const key = String(scope || '').trim().toLowerCase();
    if (key === 'global') return cfg.t.global_4cc6684d || 'Global';
    if (key === 'regional') return cfg.t.regional_9c1c6794 || 'Regional';
    if (key === 'cluster') return cfg.t.cluster_249694a4 || 'Cluster';
    return '';
}

export function getFileIcon(fileType) {
    const iconMap = {
        pdf: '<i class="fas fa-file-pdf text-red-500 text-xl"></i>',
        docx: '<i class="fas fa-file-word text-blue-500 text-xl"></i>',
        doc: '<i class="fas fa-file-word text-blue-500 text-xl"></i>',
        xlsx: '<i class="fas fa-file-excel text-green-500 text-xl"></i>',
        xls: '<i class="fas fa-file-excel text-green-500 text-xl"></i>',
        md: '<i class="fab fa-markdown text-gray-600 text-xl"></i>',
    };
    return iconMap[fileType] || '<i class="fas fa-file-alt text-gray-500 text-xl"></i>';
}

export function getFileTypeIcon(filename) {
    const ext = String(filename || '').split('.').pop().toLowerCase();
    const iconMap = {
        pdf: '<i class="fas fa-file-pdf text-red-500 text-xl"></i>',
        doc: '<i class="fas fa-file-word text-blue-500 text-xl"></i>',
        docx: '<i class="fas fa-file-word text-blue-500 text-xl"></i>',
        xls: '<i class="fas fa-file-excel text-green-500 text-xl"></i>',
        xlsx: '<i class="fas fa-file-excel text-green-500 text-xl"></i>',
        txt: '<i class="fas fa-file-alt text-gray-500 text-xl"></i>',
        md: '<i class="fab fa-markdown text-gray-600 text-xl"></i>',
        html: '<i class="fas fa-file-code text-orange-500 text-xl"></i>',
        htm: '<i class="fas fa-file-code text-orange-500 text-xl"></i>',
    };
    return iconMap[ext] || '<i class="fas fa-file text-gray-500 text-xl"></i>';
}

export function formatFileSize(bytes) {
    const size = Number(bytes);
    if (!Number.isFinite(size) || size <= 0) return '';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.min(sizes.length - 1, Math.floor(Math.log(size) / Math.log(k)));
    return Math.round(size / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

export function getStatusBadge(status, error) {
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
    const text = textMap[key] || textMap.failed || key;
    const titleAttr = error ? ' title="' + escapeAttr(error) + '"' : '';
    if (window.StatusLabels && typeof window.StatusLabels.render === 'function') {
        return window.StatusLabels.render(text, variant).replace('<span ', '<span' + titleAttr + ' ');
    }
    return '<span class="status-label status-label--' + variant + '"' + titleAttr + '>' + escapeHtml(text) + '</span>';
}

export function formatImportFooterSummary(count) {
    const n = Number(count) || 0;
    if (n <= 0) return cfg.t.import_footer_none_selected_a4c8e2b1 || 'Select documents in the grid';
    const tpl = cfg.t.import_footer_selected_count_b7d3f9a2 || '{count} selected';
    return tpl.replace('{count}', String(n));
}

export function syncUploadImportModalFooter() {
    const footer = document.getElementById('uploadImportModalFooter');
    const importFooter = document.getElementById('importTabFooter');
    const ifrcFooter = document.getElementById('ifrcTabFooter');
    const guidanceFooter = document.getElementById('guidanceTabFooter');
    const importContent = document.getElementById('importContent');
    const ifrcContent = document.getElementById('ifrcApiContent');
    const guidanceContent = document.getElementById('guidanceContent');
    const importVisible = !!(importContent && !importContent.classList.contains('hidden'));
    const ifrcVisible = !!(ifrcContent && !ifrcContent.classList.contains('hidden'));
    const guidanceVisible = !!(guidanceContent && !guidanceContent.classList.contains('hidden'));
    const showImportFooter = importVisible && page.importTabHasRows;
    const showIfrcFooter = ifrcVisible && page.ifrcTabHasRows;
    const showGuidanceFooter = guidanceVisible && page.guidanceTabHasRows;

    if (footer) footer.classList.toggle('hidden', !showImportFooter && !showIfrcFooter && !showGuidanceFooter);
    if (importFooter) importFooter.classList.toggle('hidden', !showImportFooter);
    if (ifrcFooter) ifrcFooter.classList.toggle('hidden', !showIfrcFooter);
    if (guidanceFooter) guidanceFooter.classList.toggle('hidden', !showGuidanceFooter);
}

export function countriesFromRedetect(result) {
    const scope = String((result && result.geographic_scope) || '').trim().toLowerCase();
    if (scope === 'global') return [];
    const countryId = result && result.country_id != null ? Number(result.country_id) : NaN;
    if (Number.isFinite(countryId) && countryId > 0) {
        return [{
            id: countryId,
            name: String((result && result.country_name) || '').trim(),
            iso3: String((result && result.country_iso3) || '').trim(),
        }];
    }
    if ((scope === 'regional' || scope === 'cluster') && result && result.country_name) {
        return String(result.country_name).split(',').map(function (name) {
            return { id: null, name: name.trim(), iso3: '' };
        }).filter(function (c) { return c.name; });
    }
    return [];
}
