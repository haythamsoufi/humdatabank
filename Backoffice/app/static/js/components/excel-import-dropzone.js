/**
 * Shared Excel import dropzone — drag/drop, two-state UI, optional async validation.
 *
 * initExcelImportDropzone(root, options) — see macro data-* attrs in excel_import_dropzone.html
 */

const DEFAULT_ACCEPT = ['.xlsx', '.xls'];

const CLASS_PREFIX = 'excel-io-dropzone';

function escapeHtml(text) {
    return String(text || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function resolveElement(el) {
    if (!el) return null;
    if (typeof el === 'string') return document.querySelector(el);
    return el;
}

function readDataOptions(root) {
    const dataset = root.dataset || {};
    return {
        validateUrl: dataset.validateUrl || null,
        fileFieldName: dataset.fileFieldName || null,
        maxSizeBytes: dataset.maxSizeBytes ? parseInt(dataset.maxSizeBytes, 10) : null,
        autoSubmit: dataset.autoSubmit === 'true',
        variant: dataset.variant || 'excel',
    };
}

function getDropzoneStatusEl(dropzone) {
    return dropzone ? dropzone.querySelector(`.${CLASS_PREFIX}__status`) : null;
}

function clearDropzoneStatus(dropzone) {
    const statusEl = getDropzoneStatusEl(dropzone);
    if (statusEl) {
        statusEl.className = `${CLASS_PREFIX}__status`;
        statusEl.innerHTML = '';
    }
}

function renderDropzoneStatus(dropzone, state, html) {
    const statusEl = getDropzoneStatusEl(dropzone);
    if (!statusEl) return;
    statusEl.className = `${CLASS_PREFIX}__status ${CLASS_PREFIX}__status--${state}`;
    statusEl.innerHTML = html;
}

function updateImportDropzone(dropzone, fileInput, validationState) {
    if (!dropzone || !fileInput) return;
    const emptyContent = dropzone.querySelector(`.${CLASS_PREFIX}__content--empty`);
    const selectedContent = dropzone.querySelector(`.${CLASS_PREFIX}__content--selected`);
    const filenameEl = dropzone.querySelector(`.${CLASS_PREFIX}__filename`);
    const hasFile = fileInput.files && fileInput.files.length > 0;

    dropzone.classList.remove(
        `${CLASS_PREFIX}--has-file`,
        `${CLASS_PREFIX}--validating`,
        `${CLASS_PREFIX}--valid`,
        `${CLASS_PREFIX}--invalid`
    );

    if (!hasFile) {
        if (emptyContent) emptyContent.hidden = false;
        if (selectedContent) selectedContent.hidden = true;
        if (filenameEl) filenameEl.textContent = '';
        clearDropzoneStatus(dropzone);
        return;
    }

    if (emptyContent) emptyContent.hidden = true;
    if (selectedContent) selectedContent.hidden = false;
    if (filenameEl) filenameEl.textContent = fileInput.files[0].name;
    dropzone.classList.add(`${CLASS_PREFIX}--has-file`);
    if (validationState) {
        dropzone.classList.add(`${CLASS_PREFIX}--${validationState}`);
    }
}

function defaultBuildValidPreviewHtml(preview, dropzone, labels) {
    const isKobo = dropzone && dropzone.classList.contains(`${CLASS_PREFIX}--kobo`);
    const summaryParts = [];
    if (!isKobo && preview.pages != null && labels.pagesLabel) {
        summaryParts.push(`${preview.pages} ${labels.pagesLabel.toLowerCase()}`);
    }
    if (preview.sections != null && labels.sectionsLabel) {
        summaryParts.push(`${preview.sections} ${labels.sectionsLabel.toLowerCase()}`);
    }
    if (preview.items != null && labels.itemsLabel) {
        summaryParts.push(`${preview.items} ${labels.itemsLabel.toLowerCase()}`);
    }

    let html = `<div class="${CLASS_PREFIX}__preview">`;
    if (labels.extractedDetailsLabel) {
        html += `<p class="${CLASS_PREFIX}__preview-heading">${escapeHtml(labels.extractedDetailsLabel)}</p>`;
    }
    const validLabel = isKobo ? labels.validXlsformLabel : labels.validExportLabel;
    html += `<p class="${CLASS_PREFIX}__preview-line ${CLASS_PREFIX}__preview-line--success">`
        + `<i class="fas fa-check-circle" aria-hidden="true"></i><span>${escapeHtml(validLabel || 'Valid file')}</span></p>`;
    if (summaryParts.length) {
        html += `<p class="${CLASS_PREFIX}__preview-line">${escapeHtml(summaryParts.join(' · '))}</p>`;
    }
    if (preview.name && labels.templateNameLabel) {
        html += `<p class="${CLASS_PREFIX}__preview-line ${CLASS_PREFIX}__preview-line--name">`
            + `<span class="${CLASS_PREFIX}__preview-meta-label">${escapeHtml(labels.templateNameLabel)}</span>`
            + `<span class="${CLASS_PREFIX}__preview-meta-value">${escapeHtml(preview.name)}</span></p>`;
    }
    html += '</div>';
    return html;
}

function defaultBuildInvalidPreviewHtml(data, labels) {
    const message = data.message || labels.validationFailedLabel || 'Validation failed';
    const errors = (data.errors && data.errors.length) ? data.errors : [message];
    const showAllErrors = errors.length > 1 || (errors.length === 1 && errors[0] !== message);
    let html = `<div class="${CLASS_PREFIX}__preview">`;
    html += `<p class="${CLASS_PREFIX}__preview-line ${CLASS_PREFIX}__preview-line--error">`
        + `<i class="fas fa-exclamation-circle" aria-hidden="true"></i><span>${escapeHtml(message)}</span></p>`;
    if (showAllErrors) {
        html += `<ul class="${CLASS_PREFIX}__preview-errors">${errors.map((err) => `<li>${escapeHtml(err)}</li>`).join('')}</ul>`;
    } else if (errors.length === 1 && errors[0].length > message.length) {
        html += `<p class="${CLASS_PREFIX}__preview-detail">${escapeHtml(errors[0])}</p>`;
    }
    html += '</div>';
    return html;
}

function isAcceptedFile(file, acceptExtensions) {
    if (!file) return false;
    const name = file.name.toLowerCase();
    return acceptExtensions.some((ext) => name.endsWith(ext.toLowerCase()));
}

function bindDragDrop(dropzone, fileInput, activeClass) {
    if (!dropzone || !fileInput) return;

    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach((eventName) => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
        });
    });

    ['dragenter', 'dragover'].forEach((eventName) => {
        dropzone.addEventListener(eventName, () => {
            dropzone.classList.add(activeClass);
        });
    });

    ['dragleave', 'drop'].forEach((eventName) => {
        dropzone.addEventListener(eventName, () => {
            dropzone.classList.remove(activeClass);
        });
    });

    dropzone.addEventListener('drop', (e) => {
        const file = e.dataTransfer?.files?.[0];
        if (!file) return;
        const acceptExtensions = dropzone._excelIoAccept || DEFAULT_ACCEPT;
        if (!isAcceptedFile(file, acceptExtensions)) return;
        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(file);
        fileInput.files = dataTransfer.files;
        fileInput.dispatchEvent(new Event('change', { bubbles: true }));
    });
}

/**
 * @returns {{ reset: Function, fileInput: HTMLInputElement }}
 */
export function initExcelImportDropzone(root, options = {}) {
    const dropzone = resolveElement(root);
    if (!dropzone) {
        return { reset() {}, fileInput: null };
    }

    const dataOpts = readDataOptions(dropzone);
    const fileInput = dropzone.querySelector('input[type="file"]');
    const variant = options.variant || dataOpts.variant || 'excel';
    const acceptExtensions = options.acceptExtensions || DEFAULT_ACCEPT;
    const activeClass = variant === 'kobo'
        ? `${CLASS_PREFIX}--active-kobo`
        : (variant === 'neutral' ? `${CLASS_PREFIX}--active-neutral` : `${CLASS_PREFIX}--active`);

    dropzone._excelIoAccept = acceptExtensions;

    const labels = {
        validatingLabel: options.validatingLabel || 'Validating file…',
        validationFailedLabel: options.validationFailedLabel || 'Validation failed. Please fix the file and try again.',
        networkErrorLabel: options.networkErrorLabel || 'Could not validate the file. Please try again.',
        extractedDetailsLabel: options.extractedDetailsLabel || 'Extracted details',
        validExportLabel: options.validExportLabel || 'Valid export',
        validXlsformLabel: options.validXlsformLabel || 'Valid XLSForm',
        pagesLabel: options.pagesLabel || 'Pages',
        sectionsLabel: options.sectionsLabel || 'Sections',
        itemsLabel: options.itemsLabel || 'Items',
        templateNameLabel: options.templateNameLabel || 'Template name',
        invalidFileTypeLabel: options.invalidFileTypeLabel || 'Please upload a valid Excel file (.xlsx or .xls)',
        maxSizeLabel: options.maxSizeLabel || 'File is too large',
        importingLabel: options.importingLabel || 'Importing template…',
    };

    const validateUrl = options.validateUrl ?? dataOpts.validateUrl;
    const fileFieldName = options.fileFieldName ?? dataOpts.fileFieldName ?? fileInput?.name ?? 'excel_file';
    const maxSizeBytes = options.maxSizeBytes ?? dataOpts.maxSizeBytes;
    const submitBtn = resolveElement(options.submitBtn);
    const requireValidation = options.requireValidation ?? Boolean(validateUrl);
    const autoSubmitOnSelect = options.autoSubmitOnSelect ?? dataOpts.autoSubmit;
    const buildValidPreviewHtml = options.buildValidPreviewHtml
        || ((preview, dz) => defaultBuildValidPreviewHtml(preview, dz, labels));
    const buildInvalidPreviewHtml = options.buildInvalidPreviewHtml
        || ((data) => defaultBuildInvalidPreviewHtml(data, labels));
    const csrfToken = options.csrfToken
        || document.querySelector('input[name="csrf_token"]')?.value
        || '';

    function reset() {
        if (fileInput) fileInput.value = '';
        updateImportDropzone(dropzone, fileInput, null);
        if (submitBtn && requireValidation) submitBtn.disabled = true;
        if (typeof options.onReset === 'function') options.onReset();
    }

    function renderValidationStatus(data) {
        if (data.valid) {
            updateImportDropzone(dropzone, fileInput, 'valid');
            renderDropzoneStatus(dropzone, 'valid', buildValidPreviewHtml(data.preview || {}, dropzone));
            if (submitBtn) submitBtn.disabled = false;
        } else {
            updateImportDropzone(dropzone, fileInput, 'invalid');
            renderDropzoneStatus(dropzone, 'invalid', buildInvalidPreviewHtml(data));
            if (submitBtn) submitBtn.disabled = true;
        }
        if (typeof options.onValidated === 'function') options.onValidated(data);
    }

    async function runValidation() {
        if (!fileInput?.files?.length) {
            reset();
            return;
        }

        const file = fileInput.files[0];

        if (maxSizeBytes && file.size > maxSizeBytes) {
            renderValidationStatus({
                valid: false,
                message: labels.maxSizeLabel,
                errors: [labels.maxSizeLabel],
            });
            if (typeof options.onValidated === 'function') {
                options.onValidated({ valid: false, message: labels.maxSizeLabel });
            }
            return;
        }

        if (!isAcceptedFile(file, acceptExtensions)) {
            renderValidationStatus({
                valid: false,
                message: labels.invalidFileTypeLabel,
                errors: [labels.invalidFileTypeLabel],
            });
            fileInput.value = '';
            updateImportDropzone(dropzone, fileInput, null);
            if (typeof options.onValidated === 'function') {
                options.onValidated({ valid: false, message: labels.invalidFileTypeLabel });
            }
            return;
        }

        if (typeof options.onFileSelected === 'function') {
            options.onFileSelected(file, { dropzone, fileInput, reset, renderValidationStatus });
            updateImportDropzone(dropzone, fileInput, 'valid');
            if (submitBtn && !requireValidation) submitBtn.disabled = false;
            return;
        }

        if (!validateUrl) {
            updateImportDropzone(dropzone, fileInput, 'valid');
            if (submitBtn) submitBtn.disabled = false;
            if (autoSubmitOnSelect && fileInput.form) {
                fileInput.form.requestSubmit?.() || fileInput.form.submit();
            }
            return;
        }

        updateImportDropzone(dropzone, fileInput, 'validating');
        renderDropzoneStatus(
            dropzone,
            'pending',
            `<div class="${CLASS_PREFIX}__preview">`
                + `<p class="${CLASS_PREFIX}__preview-line ${CLASS_PREFIX}__preview-line--pending">`
                + `<i class="fas fa-spinner fa-spin" aria-hidden="true"></i><span>${escapeHtml(labels.validatingLabel)}</span></p></div>`
        );
        if (submitBtn) submitBtn.disabled = true;

        const formData = new FormData();
        if (csrfToken) formData.append('csrf_token', csrfToken);
        formData.append(fileFieldName, fileInput.files[0]);

        try {
            const response = await fetch(validateUrl, {
                method: 'POST',
                body: formData,
                credentials: 'same-origin',
            });
            const data = await response.json();
            if (!response.ok) {
                renderValidationStatus({
                    valid: false,
                    message: data.message || labels.validationFailedLabel,
                    errors: data.errors || [data.message || labels.validationFailedLabel],
                });
                return;
            }
            renderValidationStatus(data);
            if (data.valid && autoSubmitOnSelect && fileInput.form) {
                if (fileInput.form.dataset.excelImportSubmitting === '1') {
                    return;
                }
                fileInput.form.dataset.excelImportSubmitting = '1';
                renderDropzoneStatus(
                    dropzone,
                    'pending',
                    `<div class="${CLASS_PREFIX}__preview">`
                        + `<p class="${CLASS_PREFIX}__preview-line ${CLASS_PREFIX}__preview-line--pending">`
                        + `<i class="fas fa-spinner fa-spin" aria-hidden="true"></i>`
                        + `<span>${escapeHtml(labels.importingLabel || 'Importing template…')}</span></p></div>`
                );
                if (submitBtn) submitBtn.disabled = true;
                fileInput.form.requestSubmit?.() || fileInput.form.submit();
            }
        } catch (err) {
            updateImportDropzone(dropzone, fileInput, 'invalid');
            renderDropzoneStatus(
                dropzone,
                'invalid',
                `<div class="${CLASS_PREFIX}__preview">`
                    + `<p class="${CLASS_PREFIX}__preview-line ${CLASS_PREFIX}__preview-line--error">`
                    + `<i class="fas fa-exclamation-circle" aria-hidden="true"></i><span>${escapeHtml(labels.networkErrorLabel)}</span></p></div>`
            );
            if (submitBtn) submitBtn.disabled = true;
        }
    }

    if (fileInput) {
        fileInput.addEventListener('change', () => {
            if (submitBtn && requireValidation) submitBtn.disabled = true;
            runValidation();
        });
    }

    const filePanel = dropzone.querySelector(`.${CLASS_PREFIX}__file-panel`);
    if (filePanel && fileInput) {
        filePanel.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            fileInput.click();
        });
    }

    bindDragDrop(dropzone, fileInput, activeClass);

    if (options.resetOnModalClose) {
        const modal = resolveElement(options.resetOnModalClose);
        if (modal) {
            modal.addEventListener('excel-io-modal-closed', reset);
        }
    }

    if (submitBtn && requireValidation) submitBtn.disabled = true;

    dropzone._excelIoReset = reset;

    return { reset, fileInput, dropzone, runValidation };
}

export function resetExcelImportDropzones(container) {
    const root = container ? resolveElement(container) : document;
    if (!root) return;
    root.querySelectorAll(`.${CLASS_PREFIX}`).forEach((dz) => {
        if (typeof dz._excelIoReset === 'function') dz._excelIoReset();
    });
}

export { escapeHtml, updateImportDropzone, isAcceptedFile, CLASS_PREFIX };
