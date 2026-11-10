/**
 * Registers Knowledge Base job specs and resumes in-flight work.
 * Per-document ids from the page are read by AiDocsJobProgress itself.
 */

import { loadIfrcApiDocuments } from './import-ifrc.js';
import {
    refreshAiDocumentGridRowFromApi,
    reloadDocumentsGrid,
    removeDocumentFromGrid,
    syncDuplicateAnnotation,
    updateDocumentInGrid,
} from './grid.js';
import { cfg } from './shared.js';

function registerAiDocsJobSpecs(jobProgress) {
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
            const tpl = urls && urls.importSystemBulkStatus;
            if (tpl) return String(tpl).replace('__JOB__', encodeURIComponent(jobId));
            return '/admin/ai/knowledge-base/import-system-bulk/' + encodeURIComponent(jobId) + '/status';
        },
        cancelUrl: function (jobId, urls) {
            const tpl = urls && urls.importSystemBulkCancel;
            if (tpl) return String(tpl).replace('__JOB__', encodeURIComponent(jobId));
            return '/admin/ai/knowledge-base/import-system-bulk/' + encodeURIComponent(jobId) + '/cancel';
        },
        titleImport: true,
    });
    jobProgress.registerJobSpec('docs_bulk_reprocess', {
        storageKey: 'ai_docs_bulk_reprocess_job',
        statusUrl: function (jobId) {
            return '/admin/ai/knowledge-base/bulk-reprocess/' + encodeURIComponent(jobId) + '/status';
        },
        cancelUrl: function (jobId) {
            return '/admin/ai/knowledge-base/bulk-reprocess/' + encodeURIComponent(jobId) + '/cancel';
        },
        titleImport: false,
    });
    jobProgress.registerJobSpec('docs_bulk_reprocess_metadata', {
        storageKey: 'ai_docs_bulk_reprocess_metadata_job',
        statusUrl: function (jobId) {
            return '/admin/ai/knowledge-base/bulk-reprocess-metadata/' + encodeURIComponent(jobId) + '/status';
        },
        cancelUrl: function (jobId) {
            return '/admin/ai/knowledge-base/bulk-reprocess-metadata/' + encodeURIComponent(jobId) + '/cancel';
        },
        titleImport: false,
        metadataOnly: true,
    });
}

export function initAiDocsJobProgress() {
    const jobProgress = window.AiDocsJobProgress;
    if (!jobProgress || typeof jobProgress.init !== 'function') return;
    registerAiDocsJobSpecs(jobProgress);
    jobProgress.init({
        cfg: cfg,
        csrfFetchFn: (typeof csrfFetch === 'function') ? csrfFetch : null,
        fetchFn: window.apiFetch || null,
        hooks: {
            onDocGridPatch: function (docId, patch) { updateDocumentInGrid(docId, patch); },
            onDocRefresh: function (docId) { void refreshAiDocumentGridRowFromApi(docId); },
            onDocRemove: function (docId) {
                removeDocumentFromGrid(docId);
                syncDuplicateAnnotation();
            },
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
