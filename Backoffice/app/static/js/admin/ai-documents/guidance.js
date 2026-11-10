/**
 * Guidance-document tab inside the upload/import modal.
 */

import {
    cfg,
    confirmAction,
    formatImportFooterSummary,
    hideProcessingBanner,
    notifyDocs,
    page,
    startSystemImportJobPolling,
    syncUploadImportModalFooter,
} from './shared.js';

function guidanceDeleteUrl(docId) {
    const tpl = (cfg.urls || {}).deleteGuidanceDocument || '/admin/ai/knowledge-base/guidance-documents/0/delete';
    return String(tpl).replace(/0(?=\/delete$)/, encodeURIComponent(String(docId)));
}

function syncGuidanceFooter() {
    const btn = document.getElementById('guidanceImportSelectedBtn');
    const summary = document.getElementById('guidanceSelectedSummary');
    const count = page.selectedGuidanceIds.size;
    page.guidanceTabHasRows = page.guidanceDocumentsCache.length > 0;
    if (btn) btn.disabled = count === 0;
    if (summary) summary.textContent = formatImportFooterSummary(count);
    syncUploadImportModalFooter();
}

export function renderGuidanceRows(documents) {
    const tbody = document.getElementById('guidanceTbody');
    const empty = document.getElementById('guidanceEmptyHint');
    const wrap = document.getElementById('guidanceTableWrap');
    if (!tbody || !empty || !wrap) return;
    tbody.replaceChildren();
    const q = ((document.getElementById('guidanceSearch') || {}).value || '').trim().toLowerCase();
    const filtered = (documents || []).filter(function (doc) {
        if (!q) return true;
        return String(doc.title || '').toLowerCase().includes(q) ||
            String(doc.filename || '').toLowerCase().includes(q) ||
            String(doc.owner_key || '').toLowerCase().includes(q);
    });
    if (!filtered.length) {
        empty.classList.remove('hidden');
        wrap.classList.add('hidden');
        page.guidanceTabHasRows = false;
        syncGuidanceFooter();
        return;
    }
    empty.classList.add('hidden');
    wrap.classList.remove('hidden');
    filtered.forEach(function (doc) {
        const tr = document.createElement('tr');
        const selectTd = document.createElement('td');
        selectTd.className = 'px-3 py-2';
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.className = 'rounded border-gray-300 text-blue-600';
        cb.checked = page.selectedGuidanceIds.has(doc.id);
        cb.addEventListener('change', function () {
            if (cb.checked) page.selectedGuidanceIds.add(doc.id);
            else page.selectedGuidanceIds.delete(doc.id);
            syncGuidanceFooter();
        });
        selectTd.appendChild(cb);
        const titleTd = document.createElement('td');
        titleTd.className = 'px-3 py-2 text-gray-900';
        titleTd.textContent = doc.title || doc.filename || '';
        const ownerTd = document.createElement('td');
        ownerTd.className = 'px-3 py-2';
        const badge = document.createElement('span');
        badge.className = 'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-50 text-indigo-800';
        badge.textContent = String(doc.owner_key || 'system').toUpperCase();
        ownerTd.appendChild(badge);
        const statusTd = document.createElement('td');
        statusTd.className = 'px-3 py-2 text-gray-600';
        statusTd.textContent = doc.ai_processed
            ? (doc.ai_status || cfg.t.imported_fe8d588f || 'Imported')
            : (cfg.t.not_processed_0fe381df || 'Not Processed');
        const actionsTd = document.createElement('td');
        actionsTd.className = 'px-3 py-2 text-right';
        const del = document.createElement('button');
        del.type = 'button';
        del.className = 'text-red-700 hover:underline bg-transparent border-0 p-0 cursor-pointer';
        del.textContent = cfg.t.delete_f2a6c498 || 'Delete';
        del.addEventListener('click', function () { deleteGuidanceDocument(doc.id); });
        actionsTd.appendChild(del);
        tr.append(selectTd, titleTd, ownerTd, statusTd, actionsTd);
        tbody.appendChild(tr);
    });
    syncGuidanceFooter();
}

export async function loadGuidanceDocuments() {
    const loading = document.getElementById('guidanceLoading');
    if (loading) loading.classList.remove('hidden');
    try {
        const url = (cfg.urls || {}).listGuidanceDocuments || '/admin/ai/knowledge-base/list-guidance-documents';
        const res = await fetch(url, { credentials: 'same-origin' });
        const data = await res.json();
        if (!res.ok) throw new Error((data && (data.error || data.message)) || 'Failed to load');
        page.guidanceDocumentsCache = data.documents || [];
        renderGuidanceRows(page.guidanceDocumentsCache);
    } catch (err) {
        const empty = document.getElementById('guidanceEmptyHint');
        if (empty) {
            empty.classList.remove('hidden');
            empty.textContent = cfg.t.failed_to_load_documents_94b93867 || 'Failed to load documents';
        }
    } finally {
        if (loading) loading.classList.add('hidden');
    }
}

async function deleteGuidanceDocument(docId) {
    const confirmMsg = cfg.t.delete_document_137e0e00 || 'Delete document';
    confirmAction(confirmMsg, async function () {
        const res = await csrfFetch(guidanceDeleteUrl(docId), { method: 'POST' });
        const data = await res.json();
        if (!res.ok) throw new Error((data && (data.error || data.message)) || 'Delete failed');
        page.selectedGuidanceIds.delete(docId);
        await loadGuidanceDocuments();
    }, {
        danger: true,
        confirmText: cfg.t.delete_f2a6c498,
        cancelText: cfg.t.cancel_ea478870,
        title: cfg.t.delete_document_616cd122,
    });
}

async function uploadGuidanceDocument(ev) {
    if (ev) ev.preventDefault();
    const input = document.getElementById('guidanceFileInput');
    const btn = document.getElementById('guidanceUploadBtn');
    const files = input && input.files ? Array.from(input.files) : [];
    if (!files.length) return;
    const title = ((document.getElementById('guidanceDocTitle') || {}).value || '').trim();
    if (btn) btn.disabled = true;
    const failures = [];
    let uploaded = 0;
    try {
        const url = (cfg.urls || {}).uploadGuidanceDocument || '/admin/ai/knowledge-base/guidance-documents/upload';
        for (const file of files) {
            const form = new FormData();
            form.append('file', file);
            if (files.length === 1 && title) form.append('title', title);
            const res = await csrfFetch(url, { method: 'POST', body: form });
            const data = await res.json();
            if (!res.ok) failures.push(file.name + ': ' + ((data && (data.error || data.message)) || cfg.t.upload_failed_0e76390e));
            else uploaded += 1;
        }
        input.value = '';
        const titleEl = document.getElementById('guidanceDocTitle');
        if (titleEl) {
            titleEl.value = '';
            titleEl.disabled = false;
        }
        const selected = document.getElementById('guidanceSelectedFile');
        if (selected) selected.classList.add('hidden');
        await loadGuidanceDocuments();
        if (!uploaded) throw new Error(failures.join(' '));
        if (failures.length) {
            notifyDocs(
                (cfg.t.uploaded_ok_of_total_files_9c1e4a70 || 'Uploaded {ok} of {total} files. Failed: {failed}')
                    .replace('{ok}', String(uploaded))
                    .replace('{total}', String(files.length))
                    .replace('{failed}', failures.join('; ')),
                'warning'
            );
        } else {
            notifyDocs(cfg.t.upload_complete_f79598ab || 'Upload complete', 'success');
        }
    } catch (err) {
        notifyDocs(err.message || cfg.t.upload_failed_0e76390e, 'error');
    } finally {
        if (btn) btn.disabled = !(input.files && input.files[0]);
    }
}

async function importSelectedGuidance() {
    const ids = Array.from(page.selectedGuidanceIds);
    if (!ids.length) {
        notifyDocs(cfg.t.please_select_at_least_one_document_db0de074, 'warning');
        return;
    }
    const confirmMsg = (cfg.t.process_count_document_s_with_ai_this_wi_b44c5b13 || 'Process {count} document(s) with AI?').replace('{count}', ids.length);
    confirmAction(confirmMsg, async function () {
        const btn = document.getElementById('guidanceImportSelectedBtn');
        page.closeUploadModal();
        try {
            const url = (cfg.urls || {}).importGuidanceBulk || '/admin/ai/knowledge-base/import-guidance-bulk';
            const response = await csrfFetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                body: JSON.stringify({ guidance_document_ids: ids }),
            });
            const result = await response.json();
            if (!response.ok || !result || !result.job_id) {
                throw new Error((result && (result.error || result.message)) || cfg.t.failed_to_start_import_d9e1bb79);
            }
            startSystemImportJobPolling(result.job_id, Number(result.total) || ids.length);
        } catch (error) {
            hideProcessingBanner();
            notifyDocs((cfg.t.failed_to_start_import_d9e1bb79 || 'Failed to start import') + ': ' + (error.message || error), 'error');
        } finally {
            if (btn) btn.disabled = page.selectedGuidanceIds.size === 0;
        }
    }, {
        confirmText: cfg.t.process_b6ec7abe,
        cancelText: cfg.t.cancel_ea478870,
        title: cfg.t.process_documents_056842a0,
    });
}

export function initGuidanceDocumentsTab() {
    const form = document.getElementById('guidanceUploadForm');
    const input = document.getElementById('guidanceFileInput');
    const btn = document.getElementById('guidanceUploadBtn');
    const refresh = document.getElementById('guidanceRefreshBtn');
    const search = document.getElementById('guidanceSearch');
    const importBtn = document.getElementById('guidanceImportSelectedBtn');
    const cancelBtn = document.getElementById('guidanceTabCancelBtn');
    if (form) form.addEventListener('submit', uploadGuidanceDocument);
    if (input && btn) {
        input.addEventListener('change', function () {
            const files = input.files ? Array.from(input.files) : [];
            btn.disabled = files.length === 0;
            const selected = document.getElementById('guidanceSelectedFile');
            if (selected) {
                selected.textContent = files.map(function (file) { return file.name; }).join(', ');
                selected.classList.toggle('hidden', files.length === 0);
            }
            const titleEl = document.getElementById('guidanceDocTitle');
            if (titleEl) titleEl.disabled = files.length > 1;
        });
        const moduleUrl = (cfg.urls && cfg.urls.excelImportDropzone) || '/static/js/components/excel-import-dropzone.js';
        import(moduleUrl).then(function (mod) {
            mod.initExcelImportDropzone('#kb-guidance-dropzone', {
                multiple: true,
                acceptExtensions: ['.pdf', '.docx', '.doc', '.xlsx', '.xls', '.txt', '.md', '.html', '.markdown', '.htm'],
                submitBtn: btn,
                requireValidation: false,
            });
        }).catch(function () { /* native file input still works */ });
    }
    if (refresh) refresh.addEventListener('click', loadGuidanceDocuments);
    if (search) search.addEventListener('input', function () { renderGuidanceRows(page.guidanceDocumentsCache); });
    if (importBtn) importBtn.addEventListener('click', importSelectedGuidance);
    if (cancelBtn) cancelBtn.addEventListener('click', function () { page.closeUploadModal(); });
}
