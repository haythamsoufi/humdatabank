/**
 * Excel Export Module
 * Handles Excel import/export functionality including modal management
 */

import { debugLog } from './debug.js';

export class ExcelExportManager {
    constructor() {
        this.modal = null;
        this.exportButton = null;
        this.closeButtons = [];
        this.importForm = null;
        this.overlay = null;
        this.instanceId = Math.random().toString(36).slice(2, 8);
        this.debug = (window.DEBUG_EXCEL_EXPORT === true) || (localStorage.getItem('DEBUG_EXCEL_EXPORT') === '1');

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
        // eslint-disable-next-line no-console
        console.info('[ExcelExport]', `#${this.instanceId}`, ...args);
    }

    init() {
        // Find DOM elements
        this.modal = document.getElementById('excel-options-modal');
        this.exportButton = document.getElementById('excel-options-btn');
        this.closeButtons = document.querySelectorAll('.close-modal-btn');
        this.importForm = document.getElementById('modalImportExcelForm');
        this.overlay = document.querySelector('#excel-options-modal');

        if (!this.modal || !this.exportButton) {
            debugLog('excel-export', 'Excel export elements not found - feature may not be available');
            return;
        }

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

        // Close modal when close buttons are clicked
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

        // Handle export links
        const exportLinks = this.modal.querySelectorAll('a[href*="/excel/"]');
        exportLinks.forEach(link => {
            this.boundHandleExportClick = (e) => {
                this.handleExportClick(e, link);
            };
            link.addEventListener('click', this.boundHandleExportClick);
        });
    }

    showModal() {
        if (this.modal) {
            this.modal.classList.remove('hidden');
            this.modal.classList.add('flex');

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
            const fileInput = document.getElementById('modal_excel_file');
            if (fileInput) {
                fileInput.value = '';
                this.updateFileUploadBox(null);
            }

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
        // Get the href from the link element if not provided
        const exportUrl = originalHref || (link ? link.getAttribute('href') : null);

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

            const exportSignal = response.headers.get('X-NGO-Databank-Export-Completed');
            this.log('fetch response', { status: response.status, exportSignal });
            if (!response.ok || exportSignal !== '1') {
                const contentType = response.headers.get('content-type') || '';
                let msg = `Export failed (HTTP ${response.status}). Please try again.`;
                if (contentType.includes('application/json')) {
                    try {
                        const data = await response.json();
                        msg = data?.message || msg;
                    } catch (_e) {
                        // ignore JSON parse errors
                    }
                }
                throw (window.httpErrorSync && window.httpErrorSync(response, msg)) || new Error(msg);
            }

            const blob = await response.blob();
            const filename = response.headers.get('X-NGO-Databank-Export-Filename') || 'export.xlsx';
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

        const fileInput = document.getElementById('modal_excel_file');
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
        .then(data => {
            if (data && data.reload) {
                // HTML redirect response - reload page
                this.hideImportLoading(submitButton);
                this.hideModal();
                window.location.reload();
                return;
            }

            if (data && data.success === false) {
                throw new Error(data.message || 'Import failed');
            }

            // Success - show message and reload
            if (data && data.success) {
                this.hideImportLoading(submitButton);
                this.hideModal();

                // Show success message briefly before reload
                this.showSuccess(data.message || `Import completed: ${data.updated_count || 0} values saved.`);

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

    // Update file upload box UI when file is selected
    updateFileUploadBox(file) {
        const fileUploadBox = this.modal?.querySelector('.file-upload-box');
        if (!fileUploadBox) return;

        const icon = fileUploadBox.querySelector('i');
        const text = fileUploadBox.querySelector('p');
        const dropZone = this.modal?.querySelector('.file-upload-wrapper');

        if (file) {
            // Update icon to file icon
            if (icon) {
                icon.classList.remove('fa-cloud-upload-alt', 'text-gray-400');
                icon.classList.add('fa-file-excel', 'text-green-600');
            }

            // Update text to show filename
            if (text) {
                text.textContent = file.name;
                text.classList.remove('text-gray-500');
                text.classList.add('text-green-700', 'font-medium');
            }

            // Update border to indicate file selected
            if (dropZone) {
                dropZone.classList.remove('border-gray-300');
                dropZone.classList.add('border-green-500', 'bg-green-50');
            }
        } else {
            // Reset to default state
            if (icon) {
                icon.classList.remove('fa-file-excel', 'text-green-600');
                icon.classList.add('fa-cloud-upload-alt', 'text-gray-400');
            }

            if (text) {
                // Restore original text
                const originalText = text.dataset.originalText || 'Click or drag Excel file here to import';
                text.textContent = originalText;
                text.classList.remove('text-green-700', 'font-medium');
                text.classList.add('text-gray-500');
            }

            if (dropZone) {
                dropZone.classList.remove('border-green-500', 'bg-green-50');
                dropZone.classList.add('border-gray-300');
            }
        }
    }

    setupFormValidation() {
        const fileInput = document.getElementById('modal_excel_file');
        if (!fileInput) return;

        // Store original text on initialization
        const fileUploadBox = this.modal?.querySelector('.file-upload-box');
        const originalTextElement = fileUploadBox?.querySelector('p');
        if (originalTextElement && !originalTextElement.dataset.originalText) {
            originalTextElement.dataset.originalText = originalTextElement.textContent;
        }

        fileInput.addEventListener('change', (e) => {
            const file = e.target.files[0];

            // Reset UI if no file
            if (!file) {
                this.updateFileUploadBox(null);
                return;
            }

            // Clear previous errors
            const errorElement = this.modal.querySelector('.excel-error-message');
            if (errorElement) {
                errorElement.remove();
            }

            // Validate file type
            if (!this.isValidExcelFile(file)) {
                this.showError('Please select a valid Excel file (.xlsx).');
                fileInput.value = '';
                this.updateFileUploadBox(null);
                return;
            }

            // Validate file size
            const maxSize = 10 * 1024 * 1024; // 10MB
            if (file.size > maxSize) {
                this.showError('File size must be less than 10MB.');
                fileInput.value = '';
                this.updateFileUploadBox(null);
                return;
            }

            // Update UI to show selected file
            this.updateFileUploadBox(file);

            // Show file info
            this.showFileInfo(file);
        });

        // Drag and drop handling
        const dropZone = this.modal?.querySelector('.file-upload-wrapper');
        if (dropZone) {
            ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
                dropZone.addEventListener(eventName, function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                }, false);
            });

            ['dragenter', 'dragover'].forEach(eventName => {
                dropZone.addEventListener(eventName, function() {
                    dropZone.classList.add('border-blue-500', 'bg-blue-50');
                }, false);
            });

            ['dragleave', 'drop'].forEach(eventName => {
                dropZone.addEventListener(eventName, function() {
                    dropZone.classList.remove('border-blue-500', 'bg-blue-50');
                }, false);
            });

            dropZone.addEventListener('drop', (e) => {
                const dt = e.dataTransfer;
                const file = dt.files[0];

                if (file) {
                    const allowedExtensions = ['.xlsx'];
                    const fileName = file.name.toLowerCase();
                    const isValidFile = allowedExtensions.some(ext => fileName.endsWith(ext));

                    if (isValidFile) {
                        const dataTransfer = new DataTransfer();
                        dataTransfer.items.add(file);
                        fileInput.files = dataTransfer.files;
                        fileInput.dispatchEvent(new Event('change', { bubbles: true }));
                    } else {
                        this.showError('Please select a valid Excel file (.xlsx).');
                    }
                }
            }, false);
        }
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
        const fileInput = document.getElementById('modal_excel_file');
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

// Initialize the Excel export manager when DOM is ready
let excelExportManager;

function initializeExcelExport() {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            excelExportManager = new ExcelExportManager();
        });
    } else {
        excelExportManager = new ExcelExportManager();
    }
}

// Auto-initialize
initializeExcelExport();

// Export for external use
export { excelExportManager };
export default ExcelExportManager;
