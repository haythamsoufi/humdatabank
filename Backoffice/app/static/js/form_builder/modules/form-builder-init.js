/**
 * Form Builder Initialization Scripts
 * Handles initialization of various UI components in the form builder
 */

import { initExcelImportDropzone } from '../../components/excel-import-dropzone.js';
import { initExcelIoModal } from '../../components/excel-io-modal.js';

// Submit a builder form in the most reliable way:
// - Prefer the AJAX helper when available (covers cases where form.submit() bypasses submit events)
// - Fall back to requestSubmit (fires submit events + native validation)
// - Finally fall back to submit()
function submitBuilderForm(form) {
    if (!form) return;
    try {
        if (window.FormBuilderAjax && typeof window.FormBuilderAjax.submit === 'function') {
            return window.FormBuilderAjax.submit(form);
        }
    } catch (_e) {}
    try {
        if (typeof form.requestSubmit === 'function') {
            return form.requestSubmit();
        }
    } catch (_e) {}
    try { return form.submit(); } catch (_e) {}
}

async function buildDeployConfirmMessage(baseMessage, form) {
    const templateId = window.templateId;
    if (!templateId || !form) return { message: baseMessage, fieldMappingUrl: null };
    const versionInput = form.querySelector('input[name="version_id"]');
    const versionId = versionInput ? versionInput.value : null;
    if (!versionId) return { message: baseMessage, fieldMappingUrl: null };
    try {
        const url = `/admin/templates/${templateId}/deploy/preflight?version_id=${encodeURIComponent(versionId)}`;
        const resp = await fetch(url, { headers: { Accept: 'application/json' }, credentials: 'same-origin' });
        if (!resp.ok) return { message: baseMessage, fieldMappingUrl: null };
        const data = await resp.json();
        if (!data.success) return { message: baseMessage, fieldMappingUrl: null };
        const rows = data.estimate?.remappable_rows ?? 0;
        let message = baseMessage;
        if (rows > 0) {
            message += `\n\n~${Number(rows).toLocaleString()} submission row(s) will be remapped to the new version.`;
        }
        if (data.show_latency_warning) {
            message += '\n\nThis is a large migration and may take up to a minute to complete.';
        }
        const summary = data.mapping_summary || {};
        const suggested = summary.suggested_items ?? 0;
        const orphanedWithData = summary.orphaned_items_with_data ?? 0;
        if (suggested > 0 || orphanedWithData > 0) {
            message += `\n\n${suggested} field(s) have suggested matches`;
            if (orphanedWithData > 0) {
                message += `; ${orphanedWithData} published field(s) with data have no draft match`;
            }
            message += '.\nReview field mapping before deploying if unsure.';
        }
        return {
            message,
            fieldMappingUrl: data.field_mapping_url || null,
        };
    } catch (_e) {
        return { message: baseMessage, fieldMappingUrl: null };
    }
}

function confirmDeploy(form, baseMessage) {
    const doDeploy = () => { if (form) submitBuilderForm(form); };
    buildDeployConfirmMessage(baseMessage, form).then(({ message, fieldMappingUrl }) => {
        const onConfirm = () => {
            if (fieldMappingUrl && (message.includes('Review field mapping') || message.includes('suggested matches'))) {
                const reviewFirst = window.confirm(
                    message + '\n\nOpen the field mapping review page now? (Cancel to deploy anyway.)'
                );
                if (reviewFirst) {
                    window.location.href = fieldMappingUrl;
                    return;
                }
            }
            doDeploy();
        };
        if (window.showConfirmation) {
            window.showConfirmation(message, onConfirm, null, 'Deploy', 'Cancel', 'Deploy Version?');
        } else if (window.confirm(message)) {
            onConfirm();
        }
    });
}

/**
 * Wire version modal actions (idempotent — safe after AJAX DOM swaps).
 */
export function wireVersionsModal() {
    const versionsModalBtn = document.getElementById('versions-modal-btn');
    const versionsModal = document.getElementById('versions-modal');

    if (versionsModalBtn && versionsModalBtn.dataset.fbWired !== '1') {
        versionsModalBtn.dataset.fbWired = '1';
        versionsModalBtn.addEventListener('click', function() {
            // Resolve modal at click time — #versions-modal is replaced after AJAX refreshes.
            const modal = document.getElementById('versions-modal');
            if (modal) modal.classList.remove('hidden');
        });
    }

    if (versionsModal && versionsModal.dataset.fbBackdropWired !== '1') {
        versionsModal.dataset.fbBackdropWired = '1';
        versionsModal.querySelectorAll('.close-modal').forEach(btn => {
            btn.addEventListener('click', function() {
                versionsModal.classList.add('hidden');
            });
        });
        versionsModal.addEventListener('click', function(e) {
            if (e.target === versionsModal) {
                versionsModal.classList.add('hidden');
            }
        });
    }

    document.querySelectorAll('[class*="deploy-version-btn-"]').forEach(btn => {
        if (btn.dataset.fbWired === '1') return;
        btn.dataset.fbWired = '1';
        btn.addEventListener('click', function() {
            const form = this.closest('form');
            const deployMessage = window.formBuilderMessages?.deployVersion ||
                'Deploy this version? This will publish it as the live version.';
            if (form) {
                confirmDeploy(form, deployMessage);
            }
        });
    });

    document.querySelectorAll('[class*="delete-version-btn-"]').forEach(btn => {
        if (btn.dataset.fbWired === '1') return;
        btn.dataset.fbWired = '1';
        btn.addEventListener('click', function() {
            const form = this.closest('form');
            const deleteMessage = window.formBuilderMessages?.deleteVersion ||
                'Delete this version? This cannot be undone.';
            const doDelete = () => { if (form) submitBuilderForm(form); };
            if (window.showDangerConfirmation) {
                window.showDangerConfirmation(deleteMessage, doDelete, null, 'Delete', 'Cancel', 'Delete Version?');
            } else if (window.showConfirmation) {
                window.showConfirmation(deleteMessage, doDelete, null, 'Delete', 'Cancel', 'Delete Version?');
            }
        });
    });

    document.querySelectorAll('.version-note-input').forEach(input => {
        if (input.dataset.fbWired === '1') return;
        input.dataset.fbWired = '1';
        const versionId = input.getAttribute('data-version-id');
        const saveBtn = document.getElementById('version-note-save-btn-' + versionId);
        const originalValue = input.getAttribute('data-original-value') || '';

        if (saveBtn) {
            input.addEventListener('input', function() {
                if (this.value !== originalValue) {
                    saveBtn.classList.remove('hidden');
                } else {
                    saveBtn.classList.add('hidden');
                }
            });

            input.addEventListener('focus', function() {
                setTimeout(() => {
                    if (this.value !== originalValue) {
                        saveBtn.classList.remove('hidden');
                    }
                }, 100);
            });

            input.addEventListener('blur', function() {
                if (this.value === originalValue) {
                    saveBtn.classList.add('hidden');
                }
            });
        }
    });

    document.querySelectorAll('.version-datetime').forEach(element => {
        const utcDatetimeStr = element.getAttribute('data-datetime');
        if (!utcDatetimeStr) return;
        try {
            let isoString = utcDatetimeStr.trim();
            if (!isoString.endsWith('Z') && !isoString.match(/[+-]\d{2}:\d{2}$/)) {
                isoString = isoString + (isoString.includes('T') ? 'Z' : 'T00:00:00Z');
            }
            const date = new Date(isoString);
            if (!isNaN(date.getTime())) {
                const year = date.getFullYear();
                const month = String(date.getMonth() + 1).padStart(2, '0');
                const day = String(date.getDate()).padStart(2, '0');
                const hours = String(date.getHours()).padStart(2, '0');
                const minutes = String(date.getMinutes()).padStart(2, '0');
                element.textContent = `${year}-${month}-${day} ${hours}:${minutes}`;
            }
        } catch (e) {
            console.warn('Failed to convert datetime to local timezone:', e);
        }
    });
}

/**
 * Initialize versions modal functionality
 */
export function initVersionsModal() {
    document.addEventListener('DOMContentLoaded', wireVersionsModal);
}

/**
 * Initialize page sections toggle functionality
 */
export function initPageSectionsToggle() {
    document.addEventListener('DOMContentLoaded', function() {
        // Initialize page toggle buttons
        const pageToggleButtons = document.querySelectorAll('.page-toggle-btn');

        const runPageToggle = function(button) {
            const pageId = button.getAttribute('data-page-id');
            const sectionsContainer = document.querySelector(`.page-sections-container[data-page-id="${pageId}"]`);
            const icon = button.querySelector('i');
            const text = button.querySelector('span');
            if (sectionsContainer) {
                const isHidden = sectionsContainer.style.display === 'none';
                if (isHidden) {
                    sectionsContainer.style.display = 'block';
                    sectionsContainer.style.opacity = '1';
                    sectionsContainer.style.maxHeight = 'none';
                    if (icon) icon.style.transform = 'rotate(0deg)';
                    if (text) text.textContent = 'Hide Sections';
                } else {
                    sectionsContainer.style.display = 'none';
                    sectionsContainer.style.opacity = '0';
                    sectionsContainer.style.maxHeight = '0';
                    if (icon) icon.style.transform = 'rotate(-90deg)';
                    if (text) text.textContent = 'Show Sections';
                }
            }
        };

        pageToggleButtons.forEach(button => {
            button.addEventListener('click', function() {
                runPageToggle(this);
            });
        });

        // Click on page banner (title area) also toggles; avoid double-fire when clicking the button
        document.querySelectorAll('.page-banner-row').forEach(row => {
            row.addEventListener('click', function(e) {
                if (e.target.closest('.page-toggle-btn')) return;
                const btn = this.querySelector('.page-toggle-btn');
                if (btn) runPageToggle(btn);
            });
        });
    });
}

/**
 * Keep Excel import target radios in sync with the active template version.
 */
export function syncExcelImportVersionOptions() {
    const config = document.getElementById('excel-import-version-config');
    const importForm = document.getElementById('import-excel-form');
    if (!config || !importForm) return;

    const labels = window.formBuilderMessages?.excelImport || {};
    const isDraft = config.dataset.isDraft === '1';
    const hasDraft = config.dataset.hasDraft === '1';
    const versionNumber = config.dataset.versionNumber || '';
    const draftVersionNumber = config.dataset.draftVersionNumber || '';
    const versionStatus = config.dataset.versionStatus || '';
    const versionId = config.dataset.versionId || '';

    const versionInput = importForm.querySelector('input[name="version_id"]');
    if (versionInput && versionId) {
        versionInput.value = versionId;
    }

    const createDraftRadio = importForm.querySelector('#excel-import-mode-create-draft');
    const currentVersionRadio = importForm.querySelector('#excel-import-mode-current-version');
    const createDraftLabel = importForm.querySelector('#excel-import-create-draft-label');
    const currentVersionLabel = importForm.querySelector('#excel-import-current-version-label');
    const draftNote = importForm.querySelector('#excel-import-draft-exists-note');

    const formatLabel = (template, num) => String(template || '').replace('%(num)s', num);

    if (createDraftLabel) {
        const template = hasDraft && !isDraft
            ? (labels.labelImportExistingDraft || '')
            : (labels.labelCreateDraft || '');
        createDraftLabel.textContent = formatLabel(template, draftVersionNumber || versionNumber);
    }

    if (createDraftRadio) {
        createDraftRadio.disabled = isDraft;
    }

    if (draftNote) {
        draftNote.hidden = !isDraft;
        if (isDraft && labels.labelDraftNote) {
            draftNote.textContent = labels.labelDraftNote;
        }
    }

    if (currentVersionLabel) {
        const template = labels.labelCurrentVersion || '';
        let html = formatLabel(template, versionNumber);
        if (!isDraft && versionStatus === 'published' && labels.labelPublishedWarning) {
            html += `<span class="excel-io-modal__import-target-warning">${labels.labelPublishedWarning}</span>`;
        }
        currentVersionLabel.innerHTML = html;
    }

    if (createDraftRadio && currentVersionRadio) {
        if (isDraft) {
            currentVersionRadio.checked = true;
            createDraftRadio.checked = false;
        } else {
            createDraftRadio.checked = true;
            currentVersionRadio.checked = false;
        }
    }
}

function getExcelImportLabels() {
    const labels = window.formBuilderMessages?.excelImport || {};
    return {
        validatingLabel: labels.validatingLabel || 'Validating file…',
        validationFailedLabel: labels.validationFailedLabel || 'Validation failed. Please fix the file and try again.',
        networkErrorLabel: labels.networkErrorLabel || 'Could not validate the file. Please try again.',
        extractedDetailsLabel: labels.extractedDetailsLabel || 'Extracted details',
        validExportLabel: labels.validExportLabel || 'Valid export',
        pagesLabel: labels.pagesLabel || 'Pages',
        sectionsLabel: labels.sectionsLabel || 'Sections',
        itemsLabel: labels.itemsLabel || 'Items',
        templateNameLabel: labels.templateNameLabel || 'Template name',
        invalidFileTypeLabel: labels.invalidFileTypeLabel || 'Please upload a valid Excel file (.xlsx or .xls).',
        maxSizeLabel: labels.maxSizeLabel || 'File size must be less than 10MB.',
        importingLabel: labels.importingLabel || 'Importing template…',
    };
}

/**
 * Initialize Excel modal functionality
 */
export function initExcelModal() {
    const run = () => {
        const excelBtn = document.getElementById('excel-options-btn');
        const excelModal = document.getElementById('excel-options-modal');
        const importForm = document.getElementById('import-excel-form');

        syncExcelImportVersionOptions();
        document.addEventListener('formBuilder:domUpdated', syncExcelImportVersionOptions);

        if (excelBtn && excelModal) {
            initExcelIoModal(excelModal, {
                openTrigger: excelBtn,
                onOpen: syncExcelImportVersionOptions,
                onClose: function() {
                    if (importForm?.dataset?.excelImportSubmitting === '1') {
                        return;
                    }
                    if (importForm) {
                        importForm.reset();
                        delete importForm.dataset.excelPreflightDone;
                        delete importForm.dataset.excelImportSubmitting;
                        syncExcelImportVersionOptions();
                    }
                },
            });

            initExcelImportDropzone('#excel-import-dropzone', {
                validateUrl: document.getElementById('excel-import-dropzone')?.dataset?.validateUrl,
                fileFieldName: 'excel_file',
                submitBtn: importForm?.querySelector('.excel-io-modal__import-submit, button[type="submit"]'),
                requireValidation: true,
                resetOnModalClose: excelModal,
                maxSizeBytes: 10 * 1024 * 1024,
                acceptExtensions: ['.xlsx', '.xls'],
                ...getExcelImportLabels(),
            });

            if (importForm) {
                const preflightUrl = document.getElementById('excel-import-preflight-url')?.value || null;
                const uiLabels = window.formBuilderMessages?.excelImport || {};

                importForm.addEventListener('submit', async (e) => {
                    const submitBtn = importForm.querySelector('button[type="submit"]');

                    // Preflight already passed, or user confirmed deletion — allow real submit.
                    if (
                        importForm.dataset.excelPreflightDone === '1'
                        || importForm.querySelector('input[name="confirm_deletion"]')
                    ) {
                        importForm.dataset.excelImportSubmitting = '1';
                        if (submitBtn) {
                            submitBtn.disabled = true;
                            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Importing template\u2026';
                        }
                        return;
                    }

                    // No preflight URL available — just submit normally.
                    if (!preflightUrl) {
                        importForm.dataset.excelImportSubmitting = '1';
                        if (submitBtn) {
                            submitBtn.disabled = true;
                            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Importing template\u2026';
                        }
                        return;
                    }

                    // Intercept and run the preflight check first.
                    e.preventDefault();
                    const originalBtnHtml = submitBtn?.innerHTML || '';
                    if (submitBtn) {
                        submitBtn.disabled = true;
                        submitBtn.innerHTML = `<i class="fas fa-spinner fa-spin mr-2"></i> ${uiLabels.checkingLabel || 'Checking\u2026'}`;
                    }

                    try {
                        const versionId = importForm.querySelector('input[name="version_id"]')?.value;
                        const importMode = importForm.querySelector('input[name="import_version_mode"]:checked')?.value;
                        const params = new URLSearchParams();
                        if (versionId) params.set('version_id', versionId);
                        if (importMode) params.set('import_version_mode', importMode);
                        const url = params.toString() ? `${preflightUrl}?${params.toString()}` : preflightUrl;
                        const resp = await fetch(url, { credentials: 'same-origin' });
                        const data = await resp.json();

                        if (data.has_data) {
                            // Build a human-readable summary of what would be lost.
                            const c = data.counts || {};
                            const lines = [];
                            if (c.form_data > 0) lines.push(`${c.form_data} form data entr${c.form_data !== 1 ? 'ies' : 'y'}`);
                            if (c.repeat_instances > 0) lines.push(`${c.repeat_instances} repeat-group row${c.repeat_instances !== 1 ? 's' : ''}`);
                            if (c.repeat_data > 0) lines.push(`${c.repeat_data} repeat data entr${c.repeat_data !== 1 ? 'ies' : 'y'}`);
                            if (c.dynamic_indicators > 0) lines.push(`${c.dynamic_indicators} dynamic indicator record${c.dynamic_indicators !== 1 ? 's' : ''}`);
                            if (c.dynamic_contexts > 0) lines.push(`${c.dynamic_contexts} section context binding${c.dynamic_contexts !== 1 ? 's' : ''}`);
                            const summary = lines.join(', ');

                            // Inject a warning banner with confirm / cancel actions above the submit button.
                            importForm.querySelector('.excel-import-deletion-warning')?.remove();
                            const warning = document.createElement('div');
                            warning.className = 'excel-import-deletion-warning excel-io-modal__preflight-warning';
                            warning.innerHTML = `
                                <div class="excel-io-modal__preflight-warning-body">
                                    <i class="fas fa-exclamation-triangle excel-io-modal__preflight-warning-icon" aria-hidden="true"></i>
                                    <div class="excel-io-modal__preflight-warning-text">
                                        <p class="excel-io-modal__preflight-warning-title">${uiLabels.deleteDataTitle || 'This import will permanently delete existing submission data:'}</p>
                                        <p class="excel-io-modal__preflight-warning-summary">${summary}</p>
                                        <p class="excel-io-modal__preflight-warning-detail">${uiLabels.deleteDataUndo || 'This action cannot be undone.'}</p>
                                    </div>
                                </div>
                                <div class="excel-io-modal__preflight-warning-actions">
                                    <button type="button" class="btn btn-danger btn-sm excel-import-confirm-btn flex-1">
                                        <i class="fas fa-trash mr-1"></i> ${uiLabels.deleteDataConfirm || 'Delete data & import'}
                                    </button>
                                    <button type="button" class="btn btn-secondary btn-sm excel-import-cancel-btn flex-1">
                                        ${uiLabels.cancelLabel || 'Cancel'}
                                    </button>
                                </div>`;

                            submitBtn.insertAdjacentElement('beforebegin', warning);
                            submitBtn.style.display = 'none';

                            warning.querySelector('.excel-import-confirm-btn').addEventListener('click', () => {
                                const confirmInput = document.createElement('input');
                                confirmInput.type = 'hidden';
                                confirmInput.name = 'confirm_deletion';
                                confirmInput.value = '1';
                                importForm.appendChild(confirmInput);
                                warning.remove();
                                submitBtn.style.display = '';
                                importForm.dataset.excelImportSubmitting = '1';
                                submitBtn.disabled = true;
                                submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Importing template\u2026';
                                try { importForm.requestSubmit(submitBtn); } catch (_) { importForm.submit(); }
                            });

                            warning.querySelector('.excel-import-cancel-btn').addEventListener('click', () => {
                                warning.remove();
                                submitBtn.style.display = '';
                                if (submitBtn) {
                                    submitBtn.disabled = false;
                                    submitBtn.innerHTML = originalBtnHtml;
                                }
                            });
                        } else {
                            // No data at risk — submit immediately (skip preflight on re-entry).
                            importForm.dataset.excelPreflightDone = '1';
                            importForm.dataset.excelImportSubmitting = '1';
                            if (submitBtn) {
                                submitBtn.disabled = true;
                                submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Importing template\u2026';
                            }
                            try { importForm.requestSubmit(submitBtn); } catch (_) { importForm.submit(); }
                        }
                    } catch (_err) {
                        // Preflight request failed — restore the button and inform the user.
                        if (submitBtn) {
                            submitBtn.disabled = false;
                            submitBtn.innerHTML = originalBtnHtml;
                        }
                        importForm.querySelector('.excel-import-deletion-warning')?.remove();
                        const errBanner = document.createElement('div');
                        errBanner.className = 'excel-import-deletion-warning excel-io-modal__preflight-warning excel-io-modal__preflight-warning--error';
                        errBanner.innerHTML = `
                            <div class="excel-io-modal__preflight-warning-body">
                                <i class="fas fa-exclamation-triangle excel-io-modal__preflight-warning-icon" aria-hidden="true"></i>
                                <div class="excel-io-modal__preflight-warning-text">
                                    <p class="excel-io-modal__preflight-warning-title">${uiLabels.preflightErrorLabel || 'Could not check for existing data. Please try again.'}</p>
                                </div>
                            </div>`;
                        submitBtn.insertAdjacentElement('beforebegin', errBanner);
                        setTimeout(() => errBanner.remove(), 6000);
                    }
                });
            }
        }
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', run);
    } else {
        run();
    }
}

/**
 * Initialize archived items toggle functionality
 */
export function initArchivedItemsToggle() {
    document.addEventListener('DOMContentLoaded', function() {
        const toggleBtn = document.getElementById('toggle-archived-items-btn');
        const toggleText = document.getElementById('toggle-archived-text');
        const toggleIcon = document.getElementById('toggle-archived-icon');
        const toggleIndicator = document.getElementById('toggle-archived-indicator');
        const toggleSlider = document.getElementById('toggle-archived-slider');
        const toggleRipple = document.getElementById('toggle-archived-ripple');

        if (toggleBtn && toggleText && toggleIcon && toggleIndicator && toggleSlider) {
            let archivedVisible = false; // Default: hide archived items

            // Hide archived items and sections by default on page load
            const archivedRows = document.querySelectorAll('tr.archived-item-row[data-archived="true"]');
            archivedRows.forEach(function(row) {
                row.style.display = 'none';
            });

            const archivedSections = document.querySelectorAll('.archived-section-container[data-archived="true"]');
            archivedSections.forEach(function(section) {
                section.style.display = 'none';
            });

            // Function to update toggle visual state
            function updateToggleState(isVisible) {
                if (isVisible) {
                    // Toggle ON state - active blue theme
                    toggleBtn.classList.remove('from-gray-50', 'to-gray-100');
                    toggleBtn.classList.add('from-blue-50', 'to-indigo-50');

                    // Icon changes to eye (visible)
                    toggleIcon.classList.remove('fa-eye-slash', 'text-gray-500');
                    toggleIcon.classList.add('fa-eye', 'text-blue-600');

                    // Indicator turns blue
                    toggleIndicator.classList.remove('bg-gray-300');
                    toggleIndicator.classList.add('bg-blue-500');

                    // Slider moves to right
                    toggleSlider.style.transform = 'translateX(1.125rem)';

                    // Update text
                    toggleText.textContent = 'Archived Shown';
                    toggleText.classList.remove('text-gray-700');
                    toggleText.classList.add('text-blue-700');
                } else {
                    // Toggle OFF state - inactive gray theme
                    toggleBtn.classList.remove('from-blue-50', 'to-indigo-50');
                    toggleBtn.classList.add('from-gray-50', 'to-gray-100');

                    // Icon changes to eye-slash (hidden)
                    toggleIcon.classList.remove('fa-eye', 'text-blue-600');
                    toggleIcon.classList.add('fa-eye-slash', 'text-gray-500');

                    // Indicator turns gray
                    toggleIndicator.classList.remove('bg-blue-500');
                    toggleIndicator.classList.add('bg-gray-300');

                    // Slider moves to left
                    toggleSlider.style.transform = 'translateX(0)';

                    // Update text
                    toggleText.textContent = 'Archived Hidden';
                    toggleText.classList.remove('text-blue-700');
                    toggleText.classList.add('text-gray-700');
                }
            }

            // Ripple effect on click
            function createRipple(event) {
                if (toggleRipple) {
                    toggleRipple.style.opacity = '0.3';
                    toggleRipple.style.transform = 'scale(0)';

                    // Trigger reflow
                    toggleRipple.offsetHeight;

                    // Animate
                    requestAnimationFrame(function() {
                        toggleRipple.style.transition = 'all 0.4s cubic-bezier(0.4, 0, 0.2, 1)';
                        toggleRipple.style.opacity = '0';
                        toggleRipple.style.transform = 'scale(1.5)';

                        setTimeout(function() {
                            toggleRipple.style.transition = 'all 0.3s ease-in-out';
                        }, 400);
                    });
                }
            }

            toggleBtn.addEventListener('click', function(e) {
                archivedVisible = !archivedVisible;
                const archivedRows = document.querySelectorAll('tr.archived-item-row[data-archived="true"]');
                const archivedSections = document.querySelectorAll('.archived-section-container[data-archived="true"]');

                // Create ripple effect
                createRipple(e);

                archivedRows.forEach(function(row) {
                    if (archivedVisible) {
                        row.style.display = ''; // Show
                    } else {
                        row.style.display = 'none'; // Hide
                    }
                });

                archivedSections.forEach(function(section) {
                    if (archivedVisible) {
                        section.style.display = ''; // Show
                    } else {
                        section.style.display = 'none'; // Hide
                    }
                });

                // Update toggle visual state
                updateToggleState(archivedVisible);
            });
        }
    });
}

/**
 * Initialize section and subsection expand/collapse toggles
 */
export function initSectionSubsectionToggle() {
    document.addEventListener('DOMContentLoaded', function() {
        // Section toggle: collapse/expand section body
        document.querySelectorAll('.section-toggle').forEach(btn => {
            btn.addEventListener('click', function() {
                const sectionItem = this.closest('.section-item');
                if (!sectionItem) return;
                const icon = this.querySelector('i');
                const isCollapsed = sectionItem.classList.toggle('section-collapsed');
                if (icon) icon.style.transform = isCollapsed ? 'rotate(-90deg)' : '';
                btn.setAttribute('aria-expanded', isCollapsed ? 'false' : 'true');
                btn.setAttribute('title', isCollapsed ? 'Expand section' : 'Collapse section');
            });
        });

        // Section banner (title + chevron): click toggles; don't toggle when clicking action buttons
        document.querySelectorAll('.section-header-banner').forEach(banner => {
            banner.addEventListener('click', function(e) {
                if (e.target.closest('.section-toggle')) return;
                const btn = this.querySelector('.section-toggle');
                if (btn) btn.click();
            });
        });

        // Subsection toggle: collapse/expand subsection content rows
        document.querySelectorAll('.subsection-toggle').forEach(btn => {
            btn.addEventListener('click', function() {
                const headerRow = this.closest('tr.subsection-header-row');
                if (!headerRow) return;
                const subsectionId = headerRow.getAttribute('data-subsection-id');
                const table = headerRow.closest('table');
                if (!subsectionId || !table) return;
                const contentRows = table.querySelectorAll(`tr.subsection-content-row[data-parent-subsection-id="${subsectionId}"]`);
                const icon = this.querySelector('i');
                const isCollapsed = headerRow.classList.toggle('subsection-collapsed');
                contentRows.forEach(row => {
                    row.style.display = isCollapsed ? 'none' : '';
                });
                if (icon) icon.style.transform = isCollapsed ? 'rotate(-90deg)' : '';
                btn.setAttribute('aria-expanded', isCollapsed ? 'false' : 'true');
                btn.setAttribute('title', isCollapsed ? 'Expand subsection' : 'Collapse subsection');
            });
        });

        // Subsection banner row: click toggles except when clicking action buttons (last cell)
        document.querySelectorAll('tr.subsection-header-row').forEach(row => {
            row.addEventListener('click', function(e) {
                if (e.target.closest('td:last-child')) return;
                if (e.target.closest('.subsection-toggle')) return;
                const btn = this.querySelector('.subsection-toggle');
                if (btn) btn.click();
            });
        });
    });
}

/**
 * Enhance (re-bind) DOM interactions after an AJAX partial refresh.
 * Uses per-element dataset flags to avoid duplicating handlers.
 */
function enhance() {
    // Page toggle buttons
    document.querySelectorAll('.page-toggle-btn').forEach((button) => {
        if (button.dataset.fbWired === '1') return;
        button.dataset.fbWired = '1';
        button.addEventListener('click', function() {
            const pageId = button.getAttribute('data-page-id');
            const sectionsContainer = document.querySelector(`.page-sections-container[data-page-id="${pageId}"]`);
            const icon = button.querySelector('i');
            const text = button.querySelector('span');
            if (sectionsContainer) {
                const isHidden = sectionsContainer.style.display === 'none';
                if (isHidden) {
                    sectionsContainer.style.display = 'block';
                    sectionsContainer.style.opacity = '1';
                    sectionsContainer.style.maxHeight = 'none';
                    if (icon) icon.style.transform = 'rotate(0deg)';
                    if (text) text.textContent = 'Hide Sections';
                } else {
                    sectionsContainer.style.display = 'none';
                    sectionsContainer.style.opacity = '0';
                    sectionsContainer.style.maxHeight = '0';
                    if (icon) icon.style.transform = 'rotate(-90deg)';
                    if (text) text.textContent = 'Show Sections';
                }
            }
        });
    });

    // Click on page banner also toggles (wire once)
    document.querySelectorAll('.page-banner-row').forEach((row) => {
        if (row.dataset.fbWired === '1') return;
        row.dataset.fbWired = '1';
        row.addEventListener('click', function(e) {
            if (e.target.closest('.page-toggle-btn')) return;
            const btn = row.querySelector('.page-toggle-btn');
            if (btn) btn.click();
        });
    });

    // Section toggle + banner toggle
    document.querySelectorAll('.section-toggle').forEach((btn) => {
        if (btn.dataset.fbWired === '1') return;
        btn.dataset.fbWired = '1';
        btn.addEventListener('click', function() {
            const sectionItem = btn.closest('.section-item');
            if (!sectionItem) return;
            const icon = btn.querySelector('i');
            const isCollapsed = sectionItem.classList.toggle('section-collapsed');
            if (icon) icon.style.transform = isCollapsed ? 'rotate(-90deg)' : '';
            btn.setAttribute('aria-expanded', isCollapsed ? 'false' : 'true');
            btn.setAttribute('title', isCollapsed ? 'Expand section' : 'Collapse section');
        });
    });

    document.querySelectorAll('.section-header-banner').forEach((banner) => {
        if (banner.dataset.fbWired === '1') return;
        banner.dataset.fbWired = '1';
        banner.addEventListener('click', function(e) {
            if (e.target.closest('.section-toggle')) return;
            if (e.target.closest('button, a, form')) return;
            const btn = banner.querySelector('.section-toggle');
            if (btn) btn.click();
        });
    });

    // Subsection toggle + row click toggle
    document.querySelectorAll('.subsection-toggle').forEach((btn) => {
        if (btn.dataset.fbWired === '1') return;
        btn.dataset.fbWired = '1';
        btn.addEventListener('click', function() {
            const headerRow = btn.closest('tr.subsection-header-row');
            if (!headerRow) return;
            const subsectionId = headerRow.getAttribute('data-subsection-id');
            const table = headerRow.closest('table');
            if (!subsectionId || !table) return;
            const contentRows = table.querySelectorAll(`tr.subsection-content-row[data-parent-subsection-id="${subsectionId}"]`);
            const icon = btn.querySelector('i');
            const isCollapsed = headerRow.classList.toggle('subsection-collapsed');
            contentRows.forEach(row => {
                row.style.display = isCollapsed ? 'none' : '';
            });
            if (icon) icon.style.transform = isCollapsed ? 'rotate(-90deg)' : '';
            btn.setAttribute('aria-expanded', isCollapsed ? 'false' : 'true');
            btn.setAttribute('title', isCollapsed ? 'Expand subsection' : 'Collapse subsection');
        });
    });

    document.querySelectorAll('tr.subsection-header-row').forEach((row) => {
        if (row.dataset.fbWired === '1') return;
        row.dataset.fbWired = '1';
        row.addEventListener('click', function(e) {
            if (e.target.closest('td:last-child')) return;
            if (e.target.closest('.subsection-toggle')) return;
            if (e.target.closest('button, a, form')) return;
            const btn = row.querySelector('.subsection-toggle');
            if (btn) btn.click();
        });
    });

    // Re-wire banner action buttons after AJAX replacement of form-builder-status-banners.
    // On first page load these are already wired by inline DOMContentLoaded scripts
    // (which also set dataset.fbWired = '1'), so this block is a no-op on initial load.

    const deployFromBanner = document.getElementById('deploy-version-from-banner');
    if (deployFromBanner && !deployFromBanner.dataset.fbWired) {
        deployFromBanner.dataset.fbWired = '1';
        deployFromBanner.addEventListener('click', function() {
            const form = this.closest('form');
            if (!form) return;
            const message = (window.formBuilderMessages && window.formBuilderMessages.deployVersion)
                || 'Deploy this version? This will publish it as the live version.';
            const doSubmit = () => {
                form.dataset.confirmed = 'true';
                if (window.FormBuilderAjax && typeof window.FormBuilderAjax.submit === 'function') {
                    window.FormBuilderAjax.submit(form);
                } else if (typeof form.requestSubmit === 'function') {
                    form.requestSubmit();
                } else {
                    form.submit();
                }
            };
            buildDeployConfirmMessage(message, form).then((fullMessage) => {
                if (window.showConfirmation) {
                    window.showConfirmation(fullMessage, doSubmit, null, 'Deploy', 'Cancel', 'Deploy Version?');
                } else if (window.confirm(fullMessage)) {
                    doSubmit();
                }
            });
        });
    }

    const discardFromBanner = document.getElementById('discard-draft-from-banner');
    if (discardFromBanner && !discardFromBanner.dataset.fbWired) {
        discardFromBanner.dataset.fbWired = '1';
        discardFromBanner.addEventListener('click', function() {
            const form = this.closest('form');
            if (!form) return;
            const message = (window.formBuilderMessages && window.formBuilderMessages.discardDraft)
                || 'Discard this draft? All changes will be lost and cannot be undone.';
            const doSubmit = () => {
                form.dataset.confirmed = 'true';
                if (window.FormBuilderAjax && typeof window.FormBuilderAjax.submit === 'function') {
                    window.FormBuilderAjax.submit(form);
                } else if (typeof form.requestSubmit === 'function') {
                    form.requestSubmit();
                } else {
                    form.submit();
                }
            };
            if (window.showDangerConfirmation) {
                window.showDangerConfirmation(message, doSubmit, null, 'Discard', 'Cancel', 'Discard Draft?');
            } else if (window.showConfirmation) {
                window.showConfirmation(message, doSubmit, null, 'Discard', 'Cancel', 'Discard Draft?');
            } else {
                if (window.confirm(message)) doSubmit();
            }
        });
    }

    const openVersionsFromBanner = document.getElementById('open-versions-from-banner');
    if (openVersionsFromBanner && !openVersionsFromBanner.dataset.fbWired) {
        openVersionsFromBanner.dataset.fbWired = '1';
        openVersionsFromBanner.addEventListener('click', function() {
            const trigger = document.getElementById('versions-modal-btn');
            if (trigger) trigger.click();
        });
    }

    wireVersionsModal();
}

// Expose for AJAX refresh calls
window.FormBuilderEnhance = window.FormBuilderEnhance || {};
window.FormBuilderEnhance.enhance = enhance;

/**
 * Initialize "Collapse all / Expand all" controls for pages and sections.
 * - Pages: toggles visibility of `.page-sections-container` (same behavior as `.page-toggle-btn`)
 * - Sections: toggles `.section-collapsed` on `.section-item` AND hides/shows subsection content rows
 */
export function initBulkCollapseExpandControls() {
    function run() {
        const pagesBtn = document.getElementById('toggle-all-pages-btn');
        const sectionsBtn = document.getElementById('toggle-all-sections-btn');

        const getIsHidden = (el) => {
            if (!el) return true;
            try {
                // Prefer inline style (fast path), fallback to computed.
                if (el.style && el.style.display) return el.style.display === 'none';
                return window.getComputedStyle(el).display === 'none';
            } catch (_e) {
                return false;
            }
        };

        const setButtonState = ({ btn, mode, iconUp = true }) => {
            if (!btn) return;
            const collapseText = btn.getAttribute('data-collapse-text') || 'Collapse';
            const expandText = btn.getAttribute('data-expand-text') || 'Expand';
            const textEl = btn.querySelector('span');
            const iconEl = btn.querySelector('i');

            const isCollapseMode = mode === 'collapse';
            if (textEl) textEl.textContent = isCollapseMode ? collapseText : expandText;
            if (iconEl) {
                // Keep it minimal: up arrow for collapse, down arrow for expand.
                iconEl.classList.toggle('fa-angle-double-up', isCollapseMode);
                iconEl.classList.toggle('fa-angle-double-down', !isCollapseMode);
            }
            btn.dataset.mode = isCollapseMode ? 'collapse' : 'expand';
            btn.setAttribute('aria-pressed', isCollapseMode ? 'false' : 'true');
        };

        const setAllPagesCollapsed = (collapsed) => {
            const pageToggles = Array.from(document.querySelectorAll('.page-toggle-btn'));
            if (pageToggles.length === 0) return;

            pageToggles.forEach((toggle) => {
                const pageId = toggle.getAttribute('data-page-id');
                const container = document.querySelector(`.page-sections-container[data-page-id="${pageId}"]`);
                const icon = toggle.querySelector('i');
                const text = toggle.querySelector('span');
                if (!container) return;

                if (collapsed) {
                    container.style.display = 'none';
                    container.style.opacity = '0';
                    container.style.maxHeight = '0';
                    if (icon) icon.style.transform = 'rotate(-90deg)';
                    if (text) text.textContent = 'Show Sections';
                } else {
                    container.style.display = 'block';
                    container.style.opacity = '1';
                    container.style.maxHeight = 'none';
                    if (icon) icon.style.transform = 'rotate(0deg)';
                    if (text) text.textContent = 'Hide Sections';
                }
            });
        };

        const setAllSectionsCollapsed = (collapsed) => {
            // Collapse/expand main section bodies.
            document.querySelectorAll('.section-item').forEach((sectionItem) => {
                if (!sectionItem) return;
                sectionItem.classList.toggle('section-collapsed', !!collapsed);

                const toggleBtn = sectionItem.querySelector('.section-toggle');
                const icon = toggleBtn ? toggleBtn.querySelector('i') : null;
                if (icon) icon.style.transform = collapsed ? 'rotate(-90deg)' : '';
                if (toggleBtn) {
                    toggleBtn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
                    toggleBtn.setAttribute('title', collapsed ? 'Expand section' : 'Collapse section');
                }
            });

            // Collapse/expand all subsections (header + content rows).
            document.querySelectorAll('tr.subsection-header-row').forEach((headerRow) => {
                const subsectionId = headerRow.getAttribute('data-subsection-id');
                const table = headerRow.closest('table');
                if (!subsectionId || !table) return;

                headerRow.classList.toggle('subsection-collapsed', !!collapsed);
                const contentRows = table.querySelectorAll(`tr.subsection-content-row[data-parent-subsection-id="${subsectionId}"]`);
                contentRows.forEach((row) => {
                    row.style.display = collapsed ? 'none' : '';
                });

                const toggleBtn = headerRow.querySelector('.subsection-toggle');
                const icon = toggleBtn ? toggleBtn.querySelector('i') : null;
                if (icon) icon.style.transform = collapsed ? 'rotate(-90deg)' : '';
                if (toggleBtn) {
                    toggleBtn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
                    toggleBtn.setAttribute('title', collapsed ? 'Expand subsection' : 'Collapse subsection');
                }
            });
        };

        const syncButtons = () => {
            // Pages button: only relevant if there are paginated page toggles.
            if (pagesBtn) {
                const pageToggles = Array.from(document.querySelectorAll('.page-toggle-btn'));
                if (pageToggles.length === 0) {
                    pagesBtn.disabled = true;
                    pagesBtn.setAttribute('title', 'No pages to collapse/expand');
                } else {
                    pagesBtn.disabled = false;
                    const allHidden = pageToggles.every((toggle) => {
                        const pageId = toggle.getAttribute('data-page-id');
                        const container = document.querySelector(`.page-sections-container[data-page-id="${pageId}"]`);
                        return container ? getIsHidden(container) : true;
                    });
                    setButtonState({ btn: pagesBtn, mode: allHidden ? 'expand' : 'collapse' });
                }
            }

            if (sectionsBtn) {
                const sectionItems = Array.from(document.querySelectorAll('.section-item'));
                if (sectionItems.length === 0) {
                    sectionsBtn.disabled = true;
                    sectionsBtn.setAttribute('title', 'No sections to collapse/expand');
                } else {
                    sectionsBtn.disabled = false;
                    const allCollapsed = sectionItems.every((s) => s.classList.contains('section-collapsed'));

                    // Also consider subsections: if any subsection header isn't collapsed, treat as not fully collapsed.
                    const subsectionHeaders = Array.from(document.querySelectorAll('tr.subsection-header-row'));
                    const allSubCollapsed = subsectionHeaders.every((r) => r.classList.contains('subsection-collapsed'));
                    const everythingCollapsed = allCollapsed && allSubCollapsed;

                    setButtonState({ btn: sectionsBtn, mode: everythingCollapsed ? 'expand' : 'collapse' });
                }
            }
        };

        if (pagesBtn) {
            pagesBtn.addEventListener('click', function () {
                const mode = (pagesBtn.dataset.mode || 'collapse');
                const shouldCollapse = mode === 'collapse';
                setAllPagesCollapsed(shouldCollapse);
                syncButtons();
            });
        }

        if (sectionsBtn) {
            sectionsBtn.addEventListener('click', function () {
                const mode = (sectionsBtn.dataset.mode || 'collapse');
                const shouldCollapse = mode === 'collapse';
                setAllSectionsCollapsed(shouldCollapse);
                syncButtons();
            });
        }

        // Keep bulk buttons in sync when the user toggles individual items.
        document.addEventListener('click', function (e) {
            if (
                e.target.closest('.page-toggle-btn') ||
                e.target.closest('.section-toggle') ||
                e.target.closest('.subsection-toggle')
            ) {
                setTimeout(syncButtons, 0);
            }
        });

        // Initial state.
        syncButtons();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', run);
    } else {
        run();
    }
}

/**
 * Initialize all form builder components
 */
export function initFormBuilder() {
    initVersionsModal();
    initPageSectionsToggle();
    initSectionSubsectionToggle();
    initBulkCollapseExpandControls();
    initExcelModal();
    initArchivedItemsToggle();
    initStableKeyCopyButton();
}

function initStableKeyCopyButton() {
    document.addEventListener('click', (event) => {
        const btn = event.target.closest('#item-modal-stable-key-copy');
        if (!btn) return;
        const input = document.getElementById('item-modal-stable-key');
        if (!input || !input.value) return;
        navigator.clipboard.writeText(input.value).catch(() => {
            input.select();
            document.execCommand('copy');
        });
    });
}
