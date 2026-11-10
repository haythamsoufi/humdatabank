/**
 * Knowledge Base upload form. Processing waits are bounded so a stuck
 * document cannot leave the form permanently locked.
 */

import { reloadDocumentsGrid } from './grid.js';
import {
    cfg,
    getDocState,
    hideProcessingBanner,
    isCsrfFailureResponse,
    page,
    showProcessingBanner,
    startProcessingPoll,
    stopProcessingPoll,
    updateTrackedProcessingDoc,
} from './shared.js';

const UPLOAD_PROCESSING_TIMEOUT_MS = 10 * 60 * 1000;

function waitForDocTerminal(docId) {
    return new Promise(function (resolve) {
        const started = Date.now();
        function check() {
            const tracked = getDocState(docId);
            if (tracked && (tracked.status === 'completed' || tracked.status === 'failed' || tracked.status === 'not_found')) {
                resolve(tracked);
                return;
            }
            if (Date.now() - started >= UPLOAD_PROCESSING_TIMEOUT_MS) {
                resolve({
                    status: 'failed',
                    error: cfg.t.processing_failed_ad62fd55 || 'Timed out waiting for processing',
                });
                return;
            }
            setTimeout(check, 500);
        }
        check();
    });
}

function performUploadXhr(formData, csrfToken, onProgress) {
    if (csrfToken) formData.set('csrf_token', csrfToken);
    return new Promise(function (resolve, reject) {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/api/ai/documents/upload', true);
        xhr.withCredentials = true;
        xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
        if (csrfToken) xhr.setRequestHeader('X-CSRFToken', csrfToken);
        xhr.upload.onprogress = function (evt) {
            if (typeof onProgress === 'function') onProgress(evt);
        };
        xhr.onerror = function () { reject(new Error('Upload failed')); };
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

async function uploadOneFile(file, title, isPublic, onProgress) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('title', title || '');
    formData.append('is_public', isPublic);
    const token = (typeof getCSRFToken === 'function') ? getCSRFToken() : null;
    let result = await performUploadXhr(formData, token, onProgress);
    if (isCsrfFailureResponse(result.status, result.result) && typeof refreshCSRFToken === 'function') {
        const newToken = await refreshCSRFToken();
        if (newToken) result = await performUploadXhr(formData, newToken, onProgress);
    }
    return result;
}

function notifyUpload(message, type) {
    if (window.showAlert) window.showAlert(message, type || 'error');
    else if (window.__clientWarn) window.__clientWarn(message);
}

function bannerUploadProgress(index, total, fileName, fileFrac) {
    const ofTotalTpl = cfg.t.uploading_current_of_total_a2e8f4f8 || 'Uploading {current} of {total}';
    const title = total === 1
        ? cfg.t.uploading_f2870421
        : ofTotalTpl.replace('{current}', String(index + 1)).replace('{total}', String(total));
    const pct = Math.round(((index + (fileFrac || 0)) / total) * 100);
    showProcessingBanner(title, fileName || cfg.t.starting_8c6ce9f8, pct);
}

export function initUploadForm() {
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');
    const uploadBtn = document.getElementById('uploadBtn');
    const uploadForm = document.getElementById('uploadForm');
    const selectedFilesList = document.getElementById('selectedFilesList');
    const docTitle = document.getElementById('docTitle');
    if (!dropZone || !fileInput || !uploadBtn || !uploadForm) {
        console.error('Upload form elements not found');
        return;
    }

    function selectedFiles() {
        return fileInput.files ? Array.from(fileInput.files) : [];
    }

    function escapeFileName(name) {
        return String(name == null ? '' : name)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function updateFileName() {
        const files = selectedFiles();
        const textElements = dropZone.querySelectorAll('p');
        const defaultDropText = cfg.t.drag_and_drop_files_here_or_click_to_sel_d56c91ec;
        if (files.length > 0) {
            if (textElements.length > 0) {
                if (files.length === 1) textElements[0].textContent = files[0].name;
                else {
                    const tpl = cfg.t.count_files_selected_305e0882 || '{count} files selected';
                    textElements[0].textContent = tpl.replace('{count}', String(files.length));
                }
            }
            if (selectedFilesList) {
                selectedFilesList.innerHTML = files.map(function (file) {
                    return '<li class="truncate">' + escapeFileName(file.name) + '</li>';
                }).join('');
                selectedFilesList.classList.toggle('hidden', files.length < 2);
            }
            if (docTitle) {
                const multi = files.length > 1;
                docTitle.disabled = multi;
                if (multi) docTitle.title = cfg.t.title_applies_to_a_single_file_only_a075be65 || '';
                else docTitle.removeAttribute('title');
            }
            uploadBtn.disabled = false;
        } else {
            if (textElements.length > 0 && defaultDropText) textElements[0].textContent = defaultDropText;
            if (selectedFilesList) {
                selectedFilesList.innerHTML = '';
                selectedFilesList.classList.add('hidden');
            }
            if (docTitle) {
                docTitle.disabled = false;
                docTitle.removeAttribute('title');
            }
            uploadBtn.disabled = true;
        }
    }

    dropZone.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            fileInput.click();
        }
    });
    dropZone.addEventListener('dragover', function (e) {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });
    dropZone.addEventListener('dragleave', function () {
        dropZone.classList.remove('dragover');
    });
    dropZone.addEventListener('drop', function (e) {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        if (e.dataTransfer.files.length) {
            fileInput.files = e.dataTransfer.files;
            updateFileName();
        }
    });
    fileInput.addEventListener('change', updateFileName);

    uploadForm.addEventListener('submit', async function (e) {
        e.preventDefault();
        if (uploadForm.dataset.uploading === '1') return;
        const files = selectedFiles();
        if (!files.length) {
            notifyUpload(cfg.t.please_select_a_file_b3d4e2bc, 'warning');
            return;
        }
        const titleValue = docTitle ? docTitle.value : '';
        const publicBox = uploadForm.querySelector('[name="is_public"]');
        const isPublic = !!(publicBox && publicBox.checked);
        uploadForm.dataset.uploading = '1';
        page.closeUploadModal();
        bannerUploadProgress(0, files.length, files[0].name, 0);
        try {
            if (typeof waitForPendingCsrfRefresh === 'function') await waitForPendingCsrfRefresh();
            if (typeof refreshCSRFTokenIfStale === 'function') {
                await refreshCSRFTokenIfStale().catch(function () { return null; });
            }
            const processingDocIds = [];
            const immediateSuccesses = [];
            const uploadErrors = [];
            for (let i = 0; i < files.length; i++) {
                const file = files[i];
                const fileTitle = files.length === 1 ? titleValue : '';
                bannerUploadProgress(i, files.length, file.name, 0);
                const result = await uploadOneFile(file, fileTitle, isPublic, function (evt) {
                    if (!evt.lengthComputable) return;
                    bannerUploadProgress(i, files.length, file.name, evt.loaded / evt.total);
                });
                const uploadResult = result.result || {};
                if (result.status === 202 && uploadResult.success && uploadResult.document_id) {
                    processingDocIds.push(uploadResult.document_id);
                } else if (uploadResult.success) {
                    immediateSuccesses.push(file.name);
                } else {
                    uploadErrors.push(file.name + ': ' + (uploadResult.error || uploadResult.message || 'Unknown error'));
                }
            }
            if (!processingDocIds.length && !immediateSuccesses.length) {
                hideProcessingBanner();
                notifyUpload((cfg.t.error_3d9f514d || 'Error') + ' ' + uploadErrors.join('; '), 'error');
                return;
            }
            if (processingDocIds.length) {
                showProcessingBanner(cfg.t.processing_upload_9cb556a5, cfg.t.starting_8c6ce9f8, 0);
                processingDocIds.forEach(function (docId) {
                    updateTrackedProcessingDoc(docId, { resetProgress: true, status: 'pending', stage: cfg.t.starting_8c6ce9f8, progress: 0 });
                    startProcessingPoll(docId);
                });
                const outcomes = await Promise.all(processingDocIds.map(waitForDocTerminal));
                processingDocIds.forEach(stopProcessingPoll);
                const completed = outcomes.filter(function (tracked) { return tracked && tracked.status === 'completed'; }).length;
                const failed = outcomes.length - completed;
                reloadDocumentsGrid();
                if (failed === 0 && uploadErrors.length === 0) {
                    showProcessingBanner(cfg.t.upload_complete_f79598ab, cfg.t.done_f92965e2, 100);
                    setTimeout(hideProcessingBanner, 2000);
                } else {
                    const parts = [];
                    if (completed) parts.push((cfg.t.successfully_processed_count_97c0ea56 || 'Successfully processed: {count}').replace('{count}', String(completed)));
                    if (failed) parts.push((cfg.t.failed_count_bc24793b || 'Failed: {count}').replace('{count}', String(failed)));
                    if (uploadErrors.length) parts.push(uploadErrors.join('; '));
                    showProcessingBanner(cfg.t.some_documents_failed_2221bc0e, parts.join(' · '), 100);
                    notifyUpload(parts.join(' · '), 'warning');
                    setTimeout(hideProcessingBanner, 2500);
                }
            } else if (uploadErrors.length) {
                hideProcessingBanner();
                reloadDocumentsGrid();
                notifyUpload((cfg.t.some_documents_failed_2221bc0e || '') + ' ' + uploadErrors.join('; '), 'warning');
            } else {
                showProcessingBanner(cfg.t.upload_complete_f79598ab, cfg.t.done_f92965e2, 100);
                reloadDocumentsGrid();
                setTimeout(hideProcessingBanner, 1500);
            }
        } catch (error) {
            console.error('Upload error:', error);
            hideProcessingBanner();
            notifyUpload((cfg.t.upload_failed_0e76390e || 'Upload failed:') + ' ' + error.message, 'error');
        } finally {
            uploadForm.dataset.uploading = '0';
        }
    });
}
