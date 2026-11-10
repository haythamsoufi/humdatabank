/**
 * Selection toolbar: download, reprocess, metadata, country redetect,
 * terminology mining, translation groups, dedupe, and delete.
 */

import { summarizeDuplicateRows } from './duplicates.js';
import {
    refreshAiDocumentGridRowFromApi,
    reloadDocumentsGrid,
    removeDocumentFromGrid,
    syncDuplicateAnnotation,
    updateDocumentInGrid,
} from './grid.js';
import {
    aiDocsLog,
    beginBulkReprocessJob,
    cfg,
    confirmAction,
    countriesFromRedetect,
    failBulkReprocessJob,
    hideProcessingBanner,
    notifyDocs,
    page,
    removeTrackedProcessingDoc,
    showProcessingBanner,
    startBulkMetaReprocessJobPolling,
    startBulkReprocessJobPolling,
    stopProcessingPoll,
} from './shared.js';

function processingCancelWrap() {
    return document.getElementById('processingStatusCancelWrap');
}

function isProcessingStatus(status) {
    return status === 'processing' || status === 'pending';
}

function getSelectedDocs() {
    if (!page.documentsGridHelper) return [];
    return page.documentsGridHelper.getSelectedRows() || [];
}

function deselectAll() {
    try {
        if (page.documentsGridApi && typeof page.documentsGridApi.deselectAll === 'function') {
            page.documentsGridApi.deselectAll();
        }
    } catch (e) { /* ignore */ }
}

function docLanguage(row) {
    return String((row && (row.document_language || row.language)) || 'en').toLowerCase().slice(0, 10);
}

async function runDedupeRequest(payload) {
    const response = await csrfFetch('/api/ai/documents/dedupe', {
        method: 'POST',
        headers: { 'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/json' },
        body: JSON.stringify(payload || {}),
    });
    const result = await response.json();
    if (!response.ok || !result.success) {
        throw new Error(result.error || (cfg.t.deduplicate_failed_8b3d1e6a || 'Deduplication failed'));
    }
    return result;
}

export function initDocumentsBulkActions() {
    const bulkContainer = document.getElementById('documentsBulkActions');
    const downloadBtn = document.getElementById('bulkDownloadBtn');
    const reprocessBtn = document.getElementById('bulkReprocessBtn');
    const redetectCountryBtn = document.getElementById('bulkRedetectCountryBtn');
    const reprocessMetaBtn = document.getElementById('bulkReprocessMetaBtn');
    const mineTerminologyBtn = document.getElementById('bulkMineTerminologyBtn');
    const markSamePublicationBtn = document.getElementById('bulkMarkSamePublicationBtn');
    const dedupeBtn = document.getElementById('bulkDedupeBtn');
    const deleteBtn = document.getElementById('bulkDeleteBtn');
    const downloadLabel = document.getElementById('bulkDownloadBtnLabel');
    const reprocessLabel = document.getElementById('bulkReprocessBtnLabel');
    const redetectCountryLabel = document.getElementById('bulkRedetectCountryBtnLabel');
    const reprocessMetaLabel = document.getElementById('bulkReprocessMetaBtnLabel');
    const mineTerminologyLabel = document.getElementById('bulkMineTerminologyBtnLabel');
    const markSamePublicationLabel = document.getElementById('bulkMarkSamePublicationBtnLabel');
    const dedupeLabel = document.getElementById('bulkDedupeBtnLabel');
    const deleteLabel = document.getElementById('bulkDeleteBtnLabel');
    const dedupeAllBtn = document.getElementById('dedupeAllDuplicatesBtn');

    if (!bulkContainer || !downloadBtn || !reprocessBtn || !deleteBtn || !downloadLabel || !reprocessLabel || !deleteLabel) {
        return;
    }

    const updateButtons = function (selectedRows) {
        const selectedCount = Array.isArray(selectedRows) ? selectedRows.length : 0;
        const eligibleReprocess = (selectedRows || []).filter(function (r) {
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
        if (redetectCountryLabel) {
            redetectCountryLabel.textContent = selectedCount > 0
                ? cfg.t.redetect_country_2f20e028 + ' (' + eligibleReprocess.length + ')'
                : cfg.t.redetect_country_2f20e028;
        }
        if (reprocessMetaBtn) reprocessMetaBtn.disabled = eligibleReprocess.length === 0;
        if (mineTerminologyBtn) mineTerminologyBtn.disabled = eligibleReprocess.length === 0;
        if (mineTerminologyLabel) {
            mineTerminologyLabel.textContent = selectedCount > 0
                ? (cfg.t.mine_terminology_8c2f1a4d || 'Mine terminology') + ' (' + eligibleReprocess.length + ')'
                : (cfg.t.mine_terminology_8c2f1a4d || 'Mine terminology');
        }
        if (markSamePublicationBtn) markSamePublicationBtn.disabled = selectedCount < 2;
        if (markSamePublicationLabel) {
            markSamePublicationLabel.textContent = selectedCount >= 2
                ? (cfg.t.mark_as_same_publication_c4e8a1b2 || 'Mark as same publication') + ' (' + selectedCount + ')'
                : (cfg.t.mark_as_same_publication_c4e8a1b2 || 'Mark as same publication');
        }
        if (reprocessMetaLabel) {
            reprocessMetaLabel.textContent = selectedCount > 0
                ? cfg.t.reprocess_metadata_4a7b1eab + ' (' + eligibleReprocess.length + ')'
                : cfg.t.reprocess_metadata_4a7b1eab;
        }
        const selectedDuplicates = (selectedRows || []).filter(function (r) { return r && r.is_duplicate; });
        const selectedDupSummary = summarizeDuplicateRows(selectedDuplicates);
        if (dedupeBtn) dedupeBtn.disabled = selectedDupSummary.extras < 1;
        if (dedupeLabel) {
            dedupeLabel.textContent = selectedDupSummary.extras > 0
                ? (cfg.t.deduplicate_3c8f1a2b || 'Deduplicate') + ' (' + selectedDupSummary.extras + ')'
                : (cfg.t.deduplicate_3c8f1a2b || 'Deduplicate');
        }
        downloadLabel.textContent = selectedCount > 0 ? cfg.t.download_801ab246 + ' (' + selectedCount + ')' : cfg.t.download_801ab246;
        reprocessLabel.textContent = selectedCount > 0 ? cfg.t.reprocess_3f20034f + ' (' + eligibleReprocess.length + ')' : cfg.t.reprocess_3f20034f;
        deleteLabel.textContent = selectedCount > 0 ? cfg.t.delete_f2a6c498 + ' (' + selectedCount + ')' : cfg.t.delete_f2a6c498;
    };

    downloadBtn.addEventListener('click', function () {
        const targets = getSelectedDocs().filter(function (r) { return r && r.id != null; });
        if (!targets.length) return;
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = '/admin/ai/knowledge-base/bulk-download';
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
        idsInput.value = targets.map(function (r) { return r.id; }).join(',');
        form.appendChild(idsInput);
        document.body.appendChild(form);
        form.submit();
        setTimeout(function () { try { form.remove(); } catch (e) { /* ignore */ } }, 1500);
    });

    reprocessBtn.addEventListener('click', function () {
        const targets = getSelectedDocs().filter(function (r) {
            return r && r.id != null && !isProcessingStatus(r.processing_status);
        });
        if (!targets.length) return;
        const ids = targets.map(function (r) { return r.id; });
        confirmAction(cfg.t.reprocess_selected_documents_95e21554 + ' (' + targets.length + ')', async function () {
            const requestTs = Date.now();
            aiDocsLog('bulkReprocessSelected:begin', { targets: ids });
            beginBulkReprocessJob(ids.length, ids, requestTs);
            ids.forEach(function (id) {
                updateDocumentInGrid(id, { processing_status: 'pending', processing_error: '' });
            });
            try {
                const response = await csrfFetch('/admin/ai/knowledge-base/bulk-reprocess', {
                    method: 'POST',
                    headers: { 'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ids: ids }),
                });
                const result = await response.json();
                if (!response.ok || !result.success || !result.job_id) {
                    throw new Error(result.error || 'Failed to start bulk reprocess');
                }
                const wrap = processingCancelWrap();
                if (wrap) wrap.classList.remove('hidden');
                startBulkReprocessJobPolling(result.job_id, result.total || ids.length);
            } catch (error) {
                aiDocsLog('bulkReprocessSelected:startError', { error: error && (error.message || String(error)) });
                failBulkReprocessJob(ids, error && (error.message || String(error)));
                ids.forEach(function (id) {
                    updateDocumentInGrid(id, { processing_status: 'failed', processing_error: error.message || '' });
                });
            }
            deselectAll();
        }, {
            confirmText: cfg.t.reprocess_3f20034f,
            cancelText: cfg.t.cancel_ea478870,
            title: cfg.t.reprocess_documents_fa766fbe,
        });
    });

    if (reprocessMetaBtn) {
        reprocessMetaBtn.addEventListener('click', function () {
            const targets = getSelectedDocs().filter(function (r) {
                return r && r.id != null && !isProcessingStatus(r.processing_status);
            });
            if (!targets.length) return;
            const ids = targets.map(function (r) { return r.id; });
            confirmAction((cfg.t.re_run_metadata_enrichment_date_language_abe06685 || '') + ' (' + targets.length + ')', async function () {
                showProcessingBanner(cfg.t.reprocessing_metadata_e6c7cf5c, cfg.t.starting_8c6ce9f8, 0);
                const wrap = processingCancelWrap();
                if (wrap) wrap.classList.remove('hidden');
                try {
                    const response = await csrfFetch('/admin/ai/knowledge-base/bulk-reprocess-metadata', {
                        method: 'POST',
                        headers: { 'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/json' },
                        body: JSON.stringify({ ids: ids }),
                    });
                    const result = await response.json();
                    if (!response.ok || !result.success || !result.job_id) {
                        throw new Error(result.error || 'Failed to start metadata reprocess');
                    }
                    startBulkMetaReprocessJobPolling(result.job_id, result.total || ids.length);
                } catch (error) {
                    hideProcessingBanner();
                    if (wrap) wrap.classList.add('hidden');
                    notifyDocs((cfg.t.error_3d9f514d || 'Error') + ' ' + ((error && error.message) || cfg.t.failed_to_start_metadata_reprocess_801da98c), 'error');
                }
                deselectAll();
            }, {
                confirmText: cfg.t.reprocess_metadata_4a7b1eab,
                cancelText: cfg.t.cancel_ea478870,
                title: cfg.t.reprocess_metadata_d2fa3648,
            });
        });
    }

    if (redetectCountryBtn) {
        redetectCountryBtn.addEventListener('click', function () {
            const targets = getSelectedDocs().filter(function (r) {
                return r && r.id != null && !isProcessingStatus(r.processing_status);
            });
            if (!targets.length) return;
            confirmAction((cfg.t.re_run_country_detection_for_selected_do_01bf58fb || '') + ' (' + targets.length + ')', function () {
                const total = targets.length;
                showProcessingBanner(cfg.t.detecting_countries_c3ff26ba + ' (0/' + total + ')', cfg.t.starting_8c6ce9f8, 0);
                (async function () {
                    let done = 0;
                    let failed = 0;
                    for (let i = 0; i < targets.length; i++) {
                        const row = targets[i];
                        const id = row.id;
                        const title = row.title || row.filename || 'Untitled';
                        showProcessingBanner(
                            cfg.t.detecting_countries_c3ff26ba + ' (' + (i + 1) + '/' + total + ')',
                            '#' + id + ' \u2022 ' + title,
                            Math.round((i / total) * 100)
                        );
                        updateDocumentInGrid(id, { redetect_processing: true });
                        try {
                            const response = await csrfFetch('/admin/ai/knowledge-base/' + id + '/redetect-country', {
                                method: 'POST',
                                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                            });
                            const result = await response.json();
                            if (response.status === 429) {
                                failed += targets.length - i;
                                updateDocumentInGrid(id, { redetect_processing: false });
                                notifyDocs(cfg.t.error_3d9f514d + ' ' + (result.error || 'Too many requests'), 'warning');
                                break;
                            }
                            if (response.ok && result.success) {
                                updateDocumentInGrid(id, {
                                    redetect_processing: false,
                                    country_id: result.country_id != null ? result.country_id : null,
                                    country_name: result.country_name || '',
                                    country_iso3: result.country_iso3 || '',
                                    geographic_scope: result.geographic_scope || '',
                                    countries: countriesFromRedetect(result),
                                });
                                void refreshAiDocumentGridRowFromApi(id, { clearRedetect: true });
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
                    notifyDocs(summaryMsg, failed > 0 ? 'warning' : 'success');
                    setTimeout(hideProcessingBanner, 3000);
                    deselectAll();
                })();
            }, {
                confirmText: cfg.t.redetect_country_2f20e028,
                cancelText: cfg.t.cancel_ea478870,
                title: cfg.t.redetect_country_f2f630d6,
            });
        });
    }

    if (mineTerminologyBtn) {
        mineTerminologyBtn.addEventListener('click', async function () {
            const targets = getSelectedDocs().filter(function (r) {
                return r && r.id != null && !isProcessingStatus(r.processing_status);
            });
            const ids = targets.map(function (r) { return r.id; });
            if (!ids.length) {
                notifyDocs(cfg.t.please_select_at_least_one_document_db0de074 || 'Please select at least one document', 'warning');
                return;
            }
            const url = (cfg.urls && cfg.urls.mineTerminology) || '/admin/ai/knowledge-base/mine-terminology';
            const title = cfg.t.mining_terminology_4d8e2a11 || 'Mining terminology';
            const scanning = cfg.t.mining_scanning_chunks_7b1c9e02 || 'Reading chunks and comparing languages...';
            const failedText = cfg.t.mining_failed_e5f6a7b8 || 'Terminology mining failed';
            mineTerminologyBtn.disabled = true;
            mineTerminologyBtn.setAttribute('aria-busy', 'true');
            if (mineTerminologyLabel) mineTerminologyLabel.textContent = title + '...';
            showProcessingBanner(title + ' (0/' + ids.length + ')', cfg.t.starting_8c6ce9f8 || 'Starting...', 8);
            let pulse = 12;
            const pulseTimer = window.setInterval(function () {
                pulse = Math.min(90, pulse + 6);
                showProcessingBanner(title + ' (' + ids.length + ')', scanning, pulse);
            }, 700);
            try {
                const res = await csrfFetch(url, {
                    method: 'POST',
                    headers: { 'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ids: ids }),
                });
                let data = {};
                try {
                    data = await res.json();
                } catch (parseErr) {
                    throw new Error(failedText + ' (HTTP ' + res.status + ')');
                }
                if (!res.ok || data.success === false) {
                    throw new Error(data.message || data.error || (failedText + ' (HTTP ' + res.status + ')'));
                }
                const candidates = data.candidates || 0;
                const documents = data.documents || 0;
                showProcessingBanner(
                    (cfg.t.mining_complete_3a6f8c14 || 'Terminology mining complete') + ' (' + documents + '/' + ids.length + ')',
                    candidates + ' candidates',
                    100
                );
                notifyDocs(data.message || (cfg.t.mining_complete_3a6f8c14 || 'Terminology mining complete'), candidates > 0 ? 'success' : 'warning');
                window.setTimeout(hideProcessingBanner, 3500);
            } catch (e) {
                hideProcessingBanner();
                notifyDocs(failedText + ': ' + ((e && e.message) || e), 'error');
            } finally {
                window.clearInterval(pulseTimer);
                mineTerminologyBtn.removeAttribute('aria-busy');
                updateButtons(getSelectedDocs());
            }
        });
    }

    if (markSamePublicationBtn) {
        markSamePublicationBtn.addEventListener('click', function () {
            const targets = getSelectedDocs().filter(function (r) { return r && r.id != null; });
            if (targets.length < 2) {
                notifyDocs(cfg.t.select_at_least_two_documents_b8d1e4c3 || 'Select at least two documents', 'warning');
                return;
            }
            const uniqueLangs = Array.from(new Set(targets.map(docLanguage)));
            const listing = targets.map(function (r) {
                return (r.title || r.filename || ('#' + r.id)) + ' (' + docLanguage(r) + ')';
            }).join('\n');
            let confirmMsg = (cfg.t.mark_same_publication_confirm_d7f2c9e1 || 'Mark these documents as the same publication in different languages?') + '\n\n' + listing;
            if (uniqueLangs.length < 2) {
                confirmMsg += '\n\n' + (cfg.t.same_language_warning_a9c3d2e1 || 'Every selected file has the same detected language. Reprocess metadata first if these are different language versions.');
            }
            confirmAction(confirmMsg, async function () {
                const url = (cfg.urls && cfg.urls.markTranslationGroup) || '/admin/ai/knowledge-base/translation-group';
                const res = await csrfFetch(url, {
                    method: 'POST',
                    headers: { 'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ids: targets.map(function (r) { return r.id; }) }),
                });
                const data = await res.json();
                notifyDocs(
                    data.message || data.error || (cfg.t.mark_same_publication_failed_f1a2b3c4 || 'Could not mark documents as the same publication'),
                    res.ok && data.success ? 'success' : 'error'
                );
            }, {
                confirmText: cfg.t.mark_as_same_publication_c4e8a1b2 || 'Mark as same publication',
                cancelText: cfg.t.cancel_ea478870,
                title: cfg.t.mark_as_same_publication_c4e8a1b2 || 'Mark as same publication',
            });
        });
    }

    if (dedupeBtn) {
        dedupeBtn.addEventListener('click', function () {
            const selectedDuplicates = getSelectedDocs().filter(function (r) { return r && r.is_duplicate; });
            const summary = summarizeDuplicateRows(selectedDuplicates);
            if (summary.extras < 1) {
                notifyDocs(cfg.t.deduplicate_nothing_4a7c2e9b || 'No duplicates in the current selection', 'info');
                return;
            }
            const ids = selectedDuplicates.map(function (r) { return r.id; });
            const confirmMsg = (cfg.t.deduplicate_confirm_7a1d9e3c || 'Deduplicate selected documents? The best copy in each group is kept; extras are deleted.') + ' (' + summary.extras + ')';
            confirmAction(confirmMsg, async function () {
                const result = await runDedupeRequest({ document_ids: ids });
                notifyDocs((cfg.t.deduplicate_complete_5c9e2a1f || 'Deduplication complete') + ' (' + (result.removed || []).length + ')', 'success');
                deselectAll();
                await reloadDocumentsGrid();
            }, {
                danger: true,
                confirmText: cfg.t.deduplicate_3c8f1a2b || 'Deduplicate',
                cancelText: cfg.t.cancel_ea478870,
                title: cfg.t.deduplicate_3c8f1a2b || 'Deduplicate',
            });
        });
    }

    if (dedupeAllBtn) {
        dedupeAllBtn.addEventListener('click', function () {
            const confirmMsg = cfg.t.deduplicate_all_confirm_2f6b8c4d
                || 'Deduplicate all duplicate groups in the knowledge base? The best copy in each group is kept; extras are deleted.';
            confirmAction(confirmMsg, async function () {
                const result = await runDedupeRequest({ all: true });
                notifyDocs((cfg.t.deduplicate_complete_5c9e2a1f || 'Deduplication complete') + ' — ' + (result.removed || []).length, 'success');
                deselectAll();
                await reloadDocumentsGrid();
            }, {
                danger: true,
                confirmText: cfg.t.deduplicate_all_9e2b4c1a || 'Deduplicate all',
                cancelText: cfg.t.cancel_ea478870,
                title: cfg.t.deduplicate_all_9e2b4c1a || 'Deduplicate all',
            });
        });
    }

    deleteBtn.addEventListener('click', function () {
        const targets = getSelectedDocs().filter(function (r) { return r && r.id != null; });
        if (!targets.length) return;
        confirmAction((cfg.t.delete_selected_documents_54681267 || 'Delete selected documents') + ' (' + targets.length + ')', async function () {
            let removed = 0;
            for (let i = 0; i < targets.length; i++) {
                const row = targets[i];
                const title = row.title || row.filename || 'Untitled';
                showProcessingBanner(
                    (cfg.t.delete_f2a6c498 || 'Delete') + ' (' + (i + 1) + '/' + targets.length + ')',
                    title,
                    Math.round((i / targets.length) * 100)
                );
                try {
                    const response = await csrfFetch('/admin/ai/knowledge-base/' + row.id + '/delete', {
                        method: 'POST',
                        headers: { 'X-Requested-With': 'XMLHttpRequest' },
                    });
                    const result = await response.json();
                    if (response.ok && result.success) {
                        stopProcessingPoll(row.id);
                        removeTrackedProcessingDoc(row.id);
                        removeDocumentFromGrid(row.id);
                        removed++;
                    } else {
                        notifyDocs((cfg.t.error_3d9f514d || 'Error') + ' ' + (result.error || cfg.t.failed_to_delete_document_94ab7a09) + ' (' + title + ')', 'error');
                    }
                } catch (error) {
                    notifyDocs((cfg.t.error_3d9f514d || 'Error') + ' ' + (error.message || cfg.t.failed_to_delete_document_94ab7a09) + ' (' + title + ')', 'error');
                }
            }
            hideProcessingBanner();
            if (removed) syncDuplicateAnnotation();
            deselectAll();
        }, {
            danger: true,
            confirmText: cfg.t.delete_f2a6c498,
            cancelText: cfg.t.cancel_ea478870,
            title: cfg.t.delete_documents_13b47e67,
        });
    });

    document.addEventListener('ag-grid-selection-changed', function (e) {
        if (!e || !e.detail || e.detail.gridId !== 'documentsGrid') return;
        updateButtons(e.detail.selectedRows || []);
    });
    updateButtons([]);
}
