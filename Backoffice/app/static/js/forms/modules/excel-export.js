/**
 * Excel Export Module
 * Handles Excel import/export functionality including modal management
 */

import { debugLog } from './debug.js';
import { initExcelImportDropzone } from '../../components/excel-import-dropzone.js';

export class ExcelExportManager {
    constructor(config = {}) {
        this.modalId = config.modalId || 'excel-options-modal';
        this.buttonId = config.buttonId || 'excel-options-btn';
        this.importFormId = config.importFormId || 'modalImportExcelForm';
        this.fileInputId = config.fileInputId || 'modal_excel_file';
        this.dropzoneSelector = config.dropzoneSelector || '.excel-io-dropzone';

        this.modal = null;
        this.exportButton = null;
        this.closeButtons = [];
        this.importForm = null;
        this.overlay = null;
        this.instanceId = Math.random().toString(36).slice(2, 8);
        this.debug = (window.DEBUG_EXCEL_EXPORT === true) || (localStorage.getItem('DEBUG_EXCEL_EXPORT') === '1');
        this._importValidationPassed = false;
        this._importHasWarnings = false;
        this._warningsAcknowledged = false;

        // Store bound methods for proper cleanup
        this.boundShowModal = null;
        this.boundHideModal = null;
        this.boundHandleEscape = null;
        this.boundHandleImportSubmission = null;
        this.boundHandleExportClick = null;
        this.boundModalClick = null;

        this.init();
    }

    log(...args) {
        if (!this.debug) return;
        (window.__clientLog || console.log)('[ExcelExport]', `#${this.instanceId}`, ...args);
    }

    init() {
        // Find DOM elements
        this.modal = document.getElementById(this.modalId);
        this.exportButton = document.getElementById(this.buttonId);
        this.importForm = document.getElementById(this.importFormId);
        this.overlay = document.querySelector(`#${this.modalId}`);

        if (!this.modal || !this.exportButton) {
            debugLog('excel-export', 'Excel export elements not found - feature may not be available');
            return;
        }

        // Scope close buttons to this modal only to avoid interfering with other modals on the page.
        this.closeButtons = this.modal.querySelectorAll('.close-modal-btn');

        this.bindEvents();
        this.setupFormValidation();
        this.log('initialized');
    }

    bindEvents() {
        // Bind methods for proper cleanup
        this.boundShowModal = (e) => {
            e.preventDefault();
            this.showModal();
        };
        this.boundHideModal = (e) => {
            e.preventDefault();
            this.hideModal();
        };
        this.boundHandleEscape = (e) => {
            if (e.key === 'Escape' && this.isModalVisible()) {
                this.hideModal();
            }
        };
        this.boundHandleImportSubmission = (e) => {
            this.handleImportSubmission(e);
        };
        this.boundModalClick = (e) => {
            if (e.target === this.modal) {
                this.hideModal();
            }
        };

        // Show modal when Excel Options button is clicked
        this.exportButton.addEventListener('click', this.boundShowModal);

        // Close modal when close buttons inside this modal are clicked
        this.closeButtons.forEach(button => {
            button.addEventListener('click', this.boundHideModal);
        });

        // Close modal when clicking outside (on overlay)
        this.modal.addEventListener('click', this.boundModalClick);

        // Handle escape key
        document.addEventListener('keydown', this.boundHandleEscape);

        // Handle import form submission
        if (this.importForm) {
            this.importForm.addEventListener('submit', this.boundHandleImportSubmission);
        }

        // Handle export links and export buttons (tabs layout)
        const exportTriggers = this.modal.querySelectorAll(
            'a[href*="/excel/"], .excel-io-modal__export-btn[data-export-url]'
        );
        exportTriggers.forEach(link => {
            link.addEventListener('click', (e) => {
                this.handleExportClick(e, link);
            });
        });

        this._bindExcelIoTabs();
    }

    _bindExcelIoTabs() {
        if (!this.modal) return;
        const layout = this.modal.querySelector('[data-excel-io-layout]');
        if (!layout || layout.dataset.excelIoLayout !== 'tabs') return;
        this.modal.querySelectorAll('[data-excel-io-tab]').forEach((btn) => {
            btn.addEventListener('click', () => {
                this._setExcelIoTab(btn.dataset.excelIoTab);
            });
        });
    }

    _setExcelIoTab(tabName) {
        if (!this.modal || !tabName) return;
        this.modal.querySelectorAll('[data-excel-io-tab]').forEach((btn) => {
            const active = btn.dataset.excelIoTab === tabName;
            btn.classList.toggle('excel-io-tabs__btn--active', active);
            btn.setAttribute('aria-selected', active ? 'true' : 'false');
        });
        this.modal.querySelectorAll('[data-excel-io-panel]').forEach((panel) => {
            panel.hidden = panel.dataset.excelIoPanel !== tabName;
        });
    }

    showModal() {
        if (this.modal) {
            this.modal.classList.remove('hidden');
            this.modal.classList.add('flex');

            const layout = this.modal.querySelector('[data-excel-io-layout]');
            if (layout && layout.dataset.excelIoLayout === 'tabs') {
                const defaultTab = layout.dataset.excelIoDefaultTab || 'export';
                this._setExcelIoTab(defaultTab);
            }

            // Prevent body scrolling when modal is open
            document.body.style.overflow = 'hidden';

            // Focus the modal for accessibility
            this.modal.focus();

            // Trigger custom event
            this.dispatchEvent('excel-modal-opened');
        }
    }

    hideModal() {
        if (this.modal) {
            this.modal.classList.add('hidden');
            this.modal.classList.remove('flex');

            // Restore body scrolling
            document.body.style.overflow = '';

            // Reset file input and UI
            this._importValidationPassed = false;
            this._importHasWarnings = false;
            this._warningsAcknowledged = false;
            this.restoreGuidePanelDefault();
            if (this._dropzoneController?.reset) {
                this._dropzoneController.reset();
            } else {
                const fileInput = document.getElementById(this.fileInputId);
                if (fileInput) fileInput.value = '';
            }
            const existingInfo = this.modal?.querySelector('.file-info');
            if (existingInfo) existingInfo.remove();

            // Return focus to the button that opened the modal
            if (this.exportButton) {
                this.exportButton.focus();
            }

            // Trigger custom event
            this.dispatchEvent('excel-modal-closed');
        }
    }

    isModalVisible() {
        return this.modal && !this.modal.classList.contains('hidden');
    }

    async handleExportClick(event, link, originalHref) {
        // Get the href from the link/button element if not provided
        const exportUrl = originalHref
            || (link ? link.getAttribute('href') : null)
            || (link?.dataset?.exportUrl ?? null);

        // Validate that we have a valid URL
        if (!exportUrl || exportUrl.includes('undefined')) {
            console.error('Invalid export URL:', exportUrl);
            this.showError('Unable to export: Invalid assignment ID. Please refresh the page and try again.');
            event.preventDefault();
            event.stopPropagation();
            return;
        }

        this.log('export click', { exportUrl });

        // Show loading state immediately
        this.showExportLoading(link);

        let cleanupDone = false;

        const cleanup = () => {
            if (cleanupDone) return;
            cleanupDone = true;

            // Hide loading state
            this.hideExportLoading(link);
        };

        // Trigger custom event (kept for backwards compatibility)
        this.dispatchEvent('excel-export-started', { url: exportUrl });

        // Prevent default to avoid page navigation
        event.preventDefault();
        event.stopPropagation();

        // Download via fetch so we can reliably restore UI when the response is ready.
        // (Anchor-download behavior varies by browser/OS and can prevent our cleanup from firing.)
        const controller = new AbortController();
        const abortTimeout = setTimeout(() => controller.abort(), 120000); // 2 minutes

        try {
            this.log('fetch start');
            const fetchFn = (window.getFetch && window.getFetch()) || fetch;
            const response = await fetchFn(exportUrl, {
                method: 'GET',
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                signal: controller.signal
            });

            const exportSignal = response.headers.get('X-hum-databank-Export-Completed');
            this.log('fetch response', { status: response.status, exportSignal });
            if (!response.ok || exportSignal !== '1') {
                const contentType = response.headers.get('content-type') || '';
                let msg = `Export failed (HTTP ${response.status}). Please try again.`;
                if (contentType.includes('application/json')) {
                    try {
                        const data = await response.json();
                        msg = data?.message || data?.error || msg;
                    } catch (_e) {
                        // ignore JSON parse errors
                    }
                }
                throw (window.httpErrorSync && window.httpErrorSync(response, msg)) || new Error(msg);
            }

            const blob = await response.blob();
            const filename = response.headers.get('X-hum-databank-Export-Filename') || 'export.xlsx';
            this.log('download ready', { filename, size: blob.size });

            const blobUrl = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = blobUrl;
            a.download = filename;
            a.style.display = 'none';
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(blobUrl);

            this.dispatchEvent('excel-export-completed', { url: exportUrl, filename });
        } catch (error) {
            console.error('Export error:', error);
            this.showError(`Unable to export: ${error?.message || 'Unknown error occurred. Please try again.'}`);
        } finally {
            clearTimeout(abortTimeout);
            this.log('cleanup');
            cleanup();
        }
    }

    handleImportSubmission(event) {
        event.preventDefault();

        const fileInput = document.getElementById(this.fileInputId);
        const submitButton = event.target.querySelector('button[type="submit"]');

        if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
            this.showError('Please select an Excel file to import.');
            return;
        }

        const file = fileInput.files[0];

        // Validate file type (xlsx only)
        if (!this.isValidExcelFile(file)) {
            this.showError('Please select a valid Excel file (.xlsx).');
            return;
        }

        // Validate file size (e.g., max 10MB)
        const maxSize = 10 * 1024 * 1024; // 10MB
        if (file.size > maxSize) {
            this.showError('File size must be less than 10MB.');
            return;
        }

        // Check for CSRF token
        const csrfToken = this.importForm.querySelector('input[name="csrf_token"]');
        if (!csrfToken || !csrfToken.value) {
            this.showError('Security token missing. Please refresh the page and try again.');
            return;
        }

        const dropzoneEl = this.modal?.querySelector(this.dropzoneSelector);
        const validateUrl = dropzoneEl?.dataset?.validateUrl || null;
        const requiresValidation = Boolean(
            validateUrl && /validate-upr-country-reporting|validate-myr/.test(validateUrl)
        );
        if (requiresValidation) {
            if (dropzoneEl?.classList.contains('excel-io-dropzone--validating')) {
                this.showError('Please wait for workbook validation to finish.');
                return;
            }
            if (dropzoneEl?.classList.contains('excel-io-dropzone--invalid') || !this._importValidationPassed) {
                this.showError('This workbook failed validation. Choose a compatible file before loading.');
                return;
            }
            if (!dropzoneEl?.classList.contains('excel-io-dropzone--valid')) {
                this.showError('Please wait for workbook validation to finish.');
                return;
            }
            if (this._importHasWarnings && !this._warningsAcknowledged) {
                this.showError('Please review and acknowledge the warnings on the left before loading.');
                return;
            }
        }

        // Show loading state
        this.showImportLoading(submitButton);

        // Trigger custom event
        this.dispatchEvent('excel-import-started', {
            fileName: file.name,
            fileSize: file.size
        });

        // Submit via AJAX for better UX
        this.submitImportForm(file, csrfToken.value);
    }

    isValidExcelFile(file) {
        // Only accept .xlsx files (not .xls)
        const validTypes = [
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        ];
        const validExtensions = ['.xlsx'];

        return validTypes.includes(file.type) ||
               validExtensions.some(ext => file.name.toLowerCase().endsWith(ext));
    }

    submitImportForm(file, csrfToken) {
        const formData = new FormData();
        formData.append('excel_file', file);
        formData.append('csrf_token', csrfToken);

        const submitButton = this.importForm.querySelector('button[type="submit"]');
        const formAction = this.importForm.action;

        const _efetch = (window.getFetch && window.getFetch()) || fetch;
        _efetch(formAction, {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => {
            const contentType = response.headers.get('content-type') || '';

            // Handle JSON responses
            if (contentType.includes('application/json')) {
                return response.json().then(data => {
                    if (!response.ok) {
                        throw (window.httpErrorSync && window.httpErrorSync(response, data.message || `HTTP error! status: ${response.status}`)) || new Error(data.message || `HTTP error! status: ${response.status}`);
                    }
                    return data;
                });
            }

            // Handle non-OK responses (HTML error pages)
            if (!response.ok) {
                return response.text().then(() => {
                    throw (window.httpErrorSync && window.httpErrorSync(response, `Server error (${response.status}). Please try again.`)) || new Error(`Server error (${response.status}). Please try again.`);
                });
            }

            // HTML response (redirect) - reload page
            return response.text().then(() => {
                return { success: true, reload: true };
            });
        })
        .then(async (data) => {
            if (data && data.reload) {
                // HTML redirect response - reload page
                this.hideImportLoading(submitButton);
                this.hideModal();
                window.location.reload();
                return;
            }

            if (data && data.success === false) {
                throw new Error(data.message || data.error || 'Import failed');
            }

            // Stage-only UPR import — apply to form DOM, do not reload
            if (data && data.success && data.stage_only && data.payload) {
                this.hideImportLoading(submitButton);
                try {
                    const { applyUprExcelImportPayload } = await import('./upr-excel-import-apply.js');
                    const applyResult = await applyUprExcelImportPayload(data.payload);
                    const allWarnings = this._dedupeImportWarnings([
                        ...(data.warnings || []),
                        ...(applyResult.warnings || []),
                    ]);
                    this.hideModal();
                    this.showPageImportNotice({
                        message: data.message,
                        warnings: allWarnings,
                        updatedCount: data.updated_count ?? applyResult.applied,
                        type: allWarnings.length ? 'warning' : 'success',
                    });
                } catch (applyError) {
                    console.error('Import apply error:', applyError);
                    this.showError(`Import parsed but failed to apply to the form: ${applyError.message || 'Unknown error'}`);
                }
                return;
            }

            // Success - show message and reload (legacy direct-to-DB import)
            if (data && data.success) {
                this.hideImportLoading(submitButton);
                this.hideModal();

                // Show warning when import partially succeeded with per-field errors
                if (data.errors && data.errors.length > 0) {
                    this.showWarning(data.message || `Import completed with warnings: ${data.updated_count || 0} values saved.`);
                } else {
                    this.showSuccess(data.message || `Import completed: ${data.updated_count || 0} values saved.`);
                }

                setTimeout(() => {
                    window.location.reload();
                }, 1500);
            }
        })
        .catch(error => {
            console.error('Import error:', error);
            this.hideImportLoading(submitButton);
            this.showError(`Import failed: ${error.message || 'Unknown error occurred. Please try again.'}`);
        });
    }

    _escapeNoticeHtml(text) {
        return String(text || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    _stripEmbeddedWarningsFromMessage(message) {
        const text = String(message || '').trim();
        const idx = text.search(/\bWarnings:\s/i);
        if (idx >= 0) {
            return text.slice(0, idx).trim();
        }
        return text;
    }

    _dedupeImportWarnings(warnings) {
        const seen = new Set();
        const out = [];
        let periodNoted = false;
        for (const raw of warnings || []) {
            const text = String(raw || '').trim();
            if (!text || seen.has(text)) continue;
            const lower = text.toLowerCase();
            if (lower.includes('period') && (lower.includes('does not match') || lower.includes('differs from'))) {
                if (periodNoted) continue;
                periodNoted = true;
            }
            seen.add(text);
            out.push(text);
        }
        return out;
    }

    clearPageImportNotice() {
        const anchor = document.getElementById('entry-form-excel-import-notice');
        if (!anchor) return;
        anchor.classList.add('hidden');
        anchor.hidden = true;
        anchor.replaceChildren();
    }

    /**
     * Show import result as an inline notice at the top of the entry form (not a flash toast).
     */
    showPageImportNotice({ message, warnings = [], type = 'success', updatedCount = null }) {
        const anchor = document.getElementById('entry-form-excel-import-notice');
        if (!anchor) return;

        const dedupedWarnings = this._dedupeImportWarnings(warnings);
        const hasWarnings = dedupedWarnings.length > 0;
        const isWarning = type === 'warning' || hasWarnings;
        anchor.className = isWarning
            ? 'bg-amber-50 border-l-4 border-amber-500 text-amber-900 p-4 mb-6 rounded-r-lg'
            : 'bg-green-50 border-l-4 border-green-500 text-green-900 p-4 mb-6 rounded-r-lg';
        anchor.hidden = false;
        anchor.classList.remove('hidden');

        const iconClass = isWarning ? 'fas fa-exclamation-triangle text-amber-600' : 'fas fa-check-circle text-green-600';
        const title = isWarning ? 'Excel import loaded with warnings' : 'Excel import loaded';
        const summary = this._stripEmbeddedWarningsFromMessage(message)
            || (updatedCount != null
                ? `Loaded ${updatedCount} values into the form. Review your data and click Save to persist.`
                : 'Import loaded into the form. Review your data and click Save to persist.');

        let warningsHtml = '';
        if (hasWarnings) {
            const items = dedupedWarnings
                .map((w) => (
                    `<li class="excel-io-page-notice__warning-item">${this._escapeNoticeHtml(w)}</li>`
                ))
                .join('');
            warningsHtml = `
                <p class="text-sm font-medium mt-3 mb-1 m-0">Warnings (${dedupedWarnings.length})</p>
                <ul class="excel-io-page-notice__warnings text-sm mt-1 mb-0">${items}</ul>`;
        }

        anchor.innerHTML = `
            <div class="flex items-start justify-between gap-4">
                <div class="flex items-start min-w-0">
                    <div class="flex-shrink-0">
                        <i class="${iconClass} mt-1" aria-hidden="true"></i>
                    </div>
                    <div class="ml-3 min-w-0">
                        <p class="font-medium m-0">${this._escapeNoticeHtml(title)}</p>
                        <p class="text-sm mt-1 mb-0">${this._escapeNoticeHtml(summary)}</p>
                        ${warningsHtml}
                    </div>
                </div>
                <button type="button"
                        class="btn btn-icon btn-sm flex-shrink-0 text-gray-500 hover:text-gray-700"
                        data-excel-import-notice-dismiss
                        aria-label="Dismiss notice">
                    <i class="fas fa-times" aria-hidden="true"></i>
                </button>
            </div>`;

        const dismissBtn = anchor.querySelector('[data-excel-import-notice-dismiss]');
        if (dismissBtn) {
            dismissBtn.addEventListener('click', () => this.clearPageImportNotice(), { once: true });
        }

        anchor.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    _getGuidePanel() {
        return this.modal?.querySelector('[data-excel-io-guide-panel]') || null;
    }

    captureGuidePanelDefault() {
        const panel = this._getGuidePanel();
        if (!panel || this._guidePanelDefaultHtml != null) return;
        this._guidePanelDefaultHtml = panel.innerHTML;
    }

    restoreGuidePanelDefault() {
        const panel = this._getGuidePanel();
        if (!panel || this._guidePanelDefaultHtml == null) return;
        panel.innerHTML = this._guidePanelDefaultHtml;
    }

    _getImportSubmitBtn() {
        return this.importForm?.querySelector('.excel-io-modal__import-submit, button[type="submit"]') || null;
    }

    updateImportSubmitState() {
        const btn = this._getImportSubmitBtn();
        if (!btn) return;
        if (btn.dataset.importPermanentlyDisabled === 'true') {
            btn.disabled = true;
            return;
        }
        if (!this._importValidationPassed) {
            btn.disabled = true;
            return;
        }
        if (this._importHasWarnings && !this._warningsAcknowledged) {
            btn.disabled = true;
            return;
        }
        btn.disabled = false;
    }

    showGuidePanelValidation({ type = 'warning', title, message, items = [], requireAck = false }) {
        const panel = this._getGuidePanel();
        if (!panel) return;
        this.captureGuidePanelDefault();

        const normalizedMessage = (message || '').trim();
        const uniqueItems = [...new Set((items || []).filter(Boolean))]
            .filter((item) => item.trim() !== normalizedMessage);

        const iconClass = type === 'error'
            ? 'fas fa-exclamation-circle excel-io-guide-validation__icon'
            : 'fas fa-exclamation-triangle excel-io-guide-validation__icon';

        const itemsHtml = uniqueItems.length
            ? `<div class="excel-io-guide-validation__items">${uniqueItems
                .map((item) => (
                    `<div class="excel-io-guide-validation__item">`
                    + `<i class="fas fa-circle excel-io-guide-validation__item-icon" aria-hidden="true"></i>`
                    + `<span>${this._escapeNoticeHtml(item)}</span>`
                    + `</div>`
                ))
                .join('')}</div>`
            : '';

        const ackHtml = requireAck
            ? `<label class="excel-io-guide-validation__ack">`
                + `<input type="checkbox" data-excel-io-warnings-ack />`
                + `<span>I have reviewed these warnings and understand the data will load into this assignment.</span>`
                + `</label>`
            : '';

        panel.innerHTML = `
            <div class="excel-io-guide-validation excel-io-guide-validation--${type}" role="alert">
                <div class="excel-io-guide-validation__header">
                    <i class="${iconClass}" aria-hidden="true"></i>
                    <div>
                        <p class="excel-io-guide-validation__title">${this._escapeNoticeHtml(title)}</p>
                        ${normalizedMessage ? `<p class="excel-io-guide-validation__lead">${this._escapeNoticeHtml(normalizedMessage)}</p>` : ''}
                    </div>
                </div>
                ${itemsHtml}
                ${ackHtml}
            </div>`;

        if (requireAck) {
            const ackBox = panel.querySelector('[data-excel-io-warnings-ack]');
            if (ackBox) {
                ackBox.addEventListener('change', () => {
                    this._warningsAcknowledged = ackBox.checked;
                    this.updateImportSubmitState();
                });
            }
        }
    }

    _clearModalTransientMessages() {
        this.modal?.querySelectorAll('.excel-warning-message, .excel-error-message').forEach((el) => {
            el.remove();
        });
    }

    showWarning(message) {
        let warningElement = this.modal.querySelector('.excel-warning-message');
        if (!warningElement) {
            warningElement = document.createElement('div');
            warningElement.className = 'excel-warning-message bg-yellow-50 border border-yellow-400 text-yellow-800 px-4 py-3 rounded mb-4';
            warningElement.setAttribute('role', 'alert');
            const modalContent = this.modal.querySelector('.relative');
            if (modalContent) {
                modalContent.insertBefore(warningElement, modalContent.firstChild.nextSibling);
            }
        }
        const inner = document.createElement('div');
        inner.className = 'flex items-center';
        const icon = document.createElement('i');
        icon.className = 'fas fa-exclamation-triangle mr-2';
        const span = document.createElement('span');
        span.textContent = message;
        inner.appendChild(icon);
        inner.appendChild(span);
        warningElement.replaceChildren();
        warningElement.appendChild(inner);
        setTimeout(() => { if (warningElement.parentNode) warningElement.remove(); }, 4000);
    }

    showSuccess(message) {
        // Create or update success message element
        let successElement = this.modal.querySelector('.excel-success-message');

        if (!successElement) {
            successElement = document.createElement('div');
            successElement.className = 'excel-success-message bg-green-100 border border-green-400 text-green-700 px-4 py-3 rounded mb-4';
            successElement.setAttribute('role', 'alert');

            // Insert at the top of the modal content
            const modalContent = this.modal.querySelector('.relative');
            if (modalContent) {
                modalContent.insertBefore(successElement, modalContent.firstChild.nextSibling);
            }
        }

        const successInner = document.createElement('div');
        successInner.className = 'flex items-center';

        const successIcon = document.createElement('i');
        successIcon.className = 'fas fa-check-circle mr-2';

        const successSpan = document.createElement('span');
        successSpan.textContent = message;

        successInner.appendChild(successIcon);
        successInner.appendChild(successSpan);
        successElement.replaceChildren();
        successElement.appendChild(successInner);

        // Auto-remove after 3 seconds (will be reloaded anyway)
        setTimeout(() => {
            if (successElement.parentNode) {
                successElement.remove();
            }
        }, 3000);
    }

    showExportLoading(link) {
        // Guard: if multiple handlers fire (or module is initialized twice), don't overwrite the true original label.
        if (link.dataset && link.dataset.excelExportLoading === '1') {
            this.log('showExportLoading skipped (already loading)');
            return;
        }
        if (link.dataset) link.dataset.excelExportLoading = '1';

        // Store original child nodes as a DocumentFragment
        const originalNodes = document.createDocumentFragment();
        Array.from(link.childNodes).forEach(node => {
            originalNodes.appendChild(node.cloneNode(true));
        });
        // Store reference to original nodes (we'll use a WeakMap or store on the element)
        link._originalNodes = originalNodes;
        link.replaceChildren();
        const spinner = document.createElement('i');
        spinner.className = 'fas fa-spinner fa-spin mr-2';
        link.appendChild(spinner);
        link.appendChild(document.createTextNode(' Preparing Export...'));
        link.classList.add('opacity-75', 'cursor-wait');
        link.style.pointerEvents = 'none';
    }

    hideExportLoading(link) {
        if (link._originalNodes) {
            link.replaceChildren();
            // Clone and append original nodes
            Array.from(link._originalNodes.childNodes).forEach(node => {
                link.appendChild(node.cloneNode(true));
            });
            delete link._originalNodes;
        }
        if (link.dataset) delete link.dataset.excelExportLoading;
        link.classList.remove('opacity-75', 'cursor-wait');
        link.style.pointerEvents = '';
    }

    showImportLoading(button) {
        // Store original child nodes as a DocumentFragment
        const originalNodes = document.createDocumentFragment();
        Array.from(button.childNodes).forEach(node => {
            originalNodes.appendChild(node.cloneNode(true));
        });
        button._originalNodes = originalNodes;
        button.replaceChildren();
        const spinner = document.createElement('i');
        spinner.className = 'fas fa-spinner fa-spin mr-2';
        button.appendChild(spinner);
        button.appendChild(document.createTextNode(' Importing...'));
        button.disabled = true;
        button.classList.add('opacity-75', 'cursor-wait');
    }

    hideImportLoading(button) {
        if (button._originalNodes) {
            button.replaceChildren();
            // Clone and append original nodes
            Array.from(button._originalNodes.childNodes).forEach(node => {
                button.appendChild(node.cloneNode(true));
            });
            delete button._originalNodes;
        }
        button.disabled = false;
        button.classList.remove('opacity-75', 'cursor-wait');
    }

    showError(message) {
        // Create or update error message element
        let errorElement = this.modal.querySelector('.excel-error-message');

        if (!errorElement) {
            errorElement = document.createElement('div');
            errorElement.className = 'excel-error-message bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4';
            errorElement.setAttribute('role', 'alert');

            // Insert at the top of the modal content
            const modalContent = this.modal.querySelector('.relative');
            if (modalContent) {
                modalContent.insertBefore(errorElement, modalContent.firstChild.nextSibling);
            }
        }

        const errorInner = document.createElement('div');
        errorInner.className = 'flex items-center';

        const errorIcon = document.createElement('i');
        errorIcon.className = 'fas fa-exclamation-circle mr-2';

        const errorSpan = document.createElement('span');
        errorSpan.textContent = message;

        const errorCloseBtn = document.createElement('button');
        errorCloseBtn.type = 'button';
        errorCloseBtn.className = 'ml-auto text-red-500 hover:text-red-700';
        errorCloseBtn.setAttribute('data-action', 'ui:dismiss');
        errorCloseBtn.setAttribute('data-dismiss-target', 'parent:2');
        const closeIcon = document.createElement('i');
        closeIcon.className = 'fas fa-times';
        errorCloseBtn.appendChild(closeIcon);

        errorInner.appendChild(errorIcon);
        errorInner.appendChild(errorSpan);
        errorInner.appendChild(errorCloseBtn);
        errorElement.replaceChildren();
        errorElement.appendChild(errorInner);

        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (errorElement.parentNode) {
                errorElement.remove();
            }
        }, 5000);
    }

    setupFormValidation() {
        const dropzoneEl = this.modal?.querySelector(this.dropzoneSelector);
        if (!dropzoneEl) return;

        const validateUrl = dropzoneEl.dataset.validateUrl || null;
        const isUprReportingValidate = Boolean(
            validateUrl && /validate-upr-country-reporting|validate-myr/.test(validateUrl)
        );
        const layoutEl = this.modal?.querySelector('[data-excel-io-layout]');
        const useGuidePanelForValidation = isUprReportingValidate
            && layoutEl?.dataset.excelIoLayout === 'guide-split';

        if (useGuidePanelForValidation) {
            this.captureGuidePanelDefault();
        }

        const submitBtn = this.importForm?.querySelector('.excel-io-modal__import-submit, button[type="submit"]');
        if (submitBtn?.disabled) {
            submitBtn.dataset.importPermanentlyDisabled = 'true';
        }

        const dropzoneOptions = {
            acceptExtensions: ['.xlsx'],
            maxSizeBytes: 10 * 1024 * 1024,
            invalidFileTypeLabel: 'Please select a valid Excel file (.xlsx).',
            maxSizeLabel: 'File size must be less than 10MB.',
            resetOnModalClose: this.modal,
            validatingLabel: 'Validating workbook…',
            validationFailedLabel: 'This file is not compatible with UPR Country Reporting import.',
            validExportLabel: 'Compatible UPR Country Reporting workbook',
            submitBtn,
            requireValidation: isUprReportingValidate,
            onReset: () => {
                this._importHasWarnings = false;
                this._warningsAcknowledged = false;
                if (useGuidePanelForValidation) {
                    this.restoreGuidePanelDefault();
                }
                this.updateImportSubmitState();
            },
            onValidated: (data) => {
                this._importValidationPassed = Boolean(data && data.valid);
                this._importHasWarnings = Boolean(data?.valid && data.warnings?.length);
                this._warningsAcknowledged = false;
                this._clearModalTransientMessages();

                if (useGuidePanelForValidation) {
                    if (!data || data.valid === false) {
                        this._importHasWarnings = false;
                        const errors = [...new Set([...(data?.errors || []), data?.message].filter(Boolean))];
                        const errMessage = data?.message || 'This file is not compatible with UPR Country Reporting import.';
                        this.showGuidePanelValidation({
                            type: 'error',
                            title: 'Workbook cannot be imported',
                            message: errMessage,
                            items: errors.filter((e) => e !== errMessage),
                        });
                    } else if (data.warnings?.length) {
                        this.showGuidePanelValidation({
                            type: 'warning',
                            title: 'Review before loading',
                            message: 'You can still load this workbook into the form.',
                            items: [...new Set(data.warnings.filter(Boolean))],
                            requireAck: true,
                        });
                    } else {
                        this._importHasWarnings = false;
                        this.restoreGuidePanelDefault();
                    }
                    this.updateImportSubmitState();
                    return;
                }

                this.updateImportSubmitState();

                if (data && data.valid === false) {
                    this.showError(data.message || 'This file is not compatible with UPR Country Reporting import.');
                } else if (data && data.valid && data.warnings && data.warnings.length > 0) {
                    this.showWarning(data.warnings.join(' '));
                }
            },
        };

        if (isUprReportingValidate) {
            dropzoneOptions.validateUrl = validateUrl;
            dropzoneOptions.buildValidPreviewHtml = (preview) => {
                const lines = [];
                if (preview?.country) {
                    lines.push(`Country: ${preview.country}`);
                }
                if (preview?.period) {
                    lines.push(`Period: ${preview.period}`);
                }
                if (preview?.kpi_count != null) {
                    lines.push(`Indicator mappings: ${preview.kpi_count}`);
                }
                const summary = lines.length ? lines.join(' · ') : '';
                return `<div class="excel-io-dropzone__preview">`
                    + `<p class="excel-io-dropzone__preview-line excel-io-dropzone__preview-line--success">`
                    + `<i class="fas fa-check-circle" aria-hidden="true"></i>`
                    + `<span>Compatible UPR Country Reporting workbook</span></p>`
                    + (summary
                        ? `<p class="excel-io-dropzone__preview-line">${summary.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')}</p>`
                        : '')
                    + `</div>`;
            };
            dropzoneOptions.buildInvalidPreviewHtml = (data) => {
                const shortMessage = useGuidePanelForValidation
                    ? 'See details in the panel on the left.'
                    : (data.message || 'Validation failed');
                return `<div class="excel-io-dropzone__preview">`
                    + `<p class="excel-io-dropzone__preview-line excel-io-dropzone__preview-line--error">`
                    + `<i class="fas fa-exclamation-circle" aria-hidden="true"></i>`
                    + `<span>${this._escapeNoticeHtml(shortMessage)}</span></p></div>`;
            };
        } else {
            dropzoneOptions.onFileSelected = (file) => {
                const errorElement = this.modal.querySelector('.excel-error-message');
                if (errorElement) errorElement.remove();
                if (file) this.showFileInfo(file);
            };
        }

        this._importValidationPassed = false;
        this._importHasWarnings = false;
        this._warningsAcknowledged = false;
        this._dropzoneController = initExcelImportDropzone(dropzoneEl, dropzoneOptions);
        this.updateImportSubmitState();
    }

    showFileInfo(file) {
        // Remove existing file info
        const existingInfo = this.modal.querySelector('.file-info');
        if (existingInfo) {
            existingInfo.remove();
        }

        // Create file info element
        const fileInfo = document.createElement('div');
        fileInfo.className = 'file-info bg-blue-50 border border-blue-200 text-blue-700 px-3 py-2 rounded text-sm mt-2';

        const fileInfoInner = document.createElement('div');
        fileInfoInner.className = 'flex items-center';

        const fileIcon = document.createElement('i');
        fileIcon.className = 'fas fa-file-excel mr-2';

        const fileNameSpan = document.createElement('span');
        fileNameSpan.textContent = file.name;

        const fileSizeSpan = document.createElement('span');
        fileSizeSpan.className = 'ml-auto text-xs';
        fileSizeSpan.textContent = this.formatFileSize(file.size);

        fileInfoInner.appendChild(fileIcon);
        fileInfoInner.appendChild(fileNameSpan);
        fileInfoInner.appendChild(fileSizeSpan);
        fileInfo.appendChild(fileInfoInner);

        // Insert after file input
        const fileInput = document.getElementById(this.fileInputId);
        if (fileInput && fileInput.parentNode) {
            fileInput.parentNode.insertBefore(fileInfo, fileInput.nextSibling);
        }
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    dispatchEvent(eventName, detail = {}) {
        const event = new CustomEvent(eventName, {
            detail: detail,
            bubbles: true,
            cancelable: true
        });

        if (this.modal) {
            this.modal.dispatchEvent(event);
        } else {
            document.dispatchEvent(event);
        }
    }

    // Public methods for external control
    open() {
        this.showModal();
    }

    close() {
        this.hideModal();
    }

    isOpen() {
        return this.isModalVisible();
    }

    destroy() {
        // Clean up event listeners using bound methods
        if (this.closeButtons && this.boundHideModal) {
            this.closeButtons.forEach(button => {
                button.removeEventListener('click', this.boundHideModal);
            });
        }

        if (this.exportButton && this.boundShowModal) {
            this.exportButton.removeEventListener('click', this.boundShowModal);
        }

        if (this.modal && this.boundModalClick) {
            this.modal.removeEventListener('click', this.boundModalClick);
        }

        if (this.importForm && this.boundHandleImportSubmission) {
            this.importForm.removeEventListener('submit', this.boundHandleImportSubmission);
        }

        if (this.boundHandleEscape) {
            document.removeEventListener('keydown', this.boundHandleEscape);
        }

        // Clean up export link listeners
        if (this.modal) {
            const exportLinks = this.modal.querySelectorAll('a[href*="/excel/"]');
            exportLinks.forEach(link => {
                if (this.boundHandleExportClick) {
                    link.removeEventListener('click', this.boundHandleExportClick);
                }
            });
        }

        // Restore body scrolling if modal was open
        if (this.isModalVisible()) {
            document.body.style.overflow = '';
        }

        // Clear bound method references
        this.boundShowModal = null;
        this.boundHideModal = null;
        this.boundHandleEscape = null;
        this.boundHandleImportSubmission = null;
        this.boundHandleExportClick = null;
        this.boundModalClick = null;
    }
}

// Export for external use
export default ExcelExportManager;
