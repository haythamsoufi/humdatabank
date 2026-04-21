/**
 * Document Upload Modal Manager
 * Handles document upload and edit functionality with period/year selection
 */

class DocumentModalManager {
    constructor() {
        this.isEditMode = false;
        this.isSubmitting = false;  // Prevent double submissions
        this.currentDocumentId = null;
        this.currentDocumentThumbnail = false;
        this.currentDocumentThumbnailFilename = null;
        this.currentDocumentFilename = null;
        this.currentDocumentDownloadUrl = '';

        // Month names for display
        this.monthNames = {
            '01': 'Jan', '02': 'Feb', '03': 'Mar', '04': 'Apr',
            '05': 'May', '06': 'Jun', '07': 'Jul', '08': 'Aug',
            '09': 'Sep', '10': 'Oct', '11': 'Nov', '12': 'Dec'
        };

        this.initializeElements();
        this.ensureYearSelectOptions();
        this.attachEventListeners();
        this.syncDocumentModalEntityFromSelect();
    }

    initializeElements() {
        // Modal elements
        this.modal = document.getElementById('documentModal');
        this.modalOverlay = this.modal?.querySelector('.fixed.inset-0.bg-gray-500');
        this.modalTitle = this.modal?.querySelector('#modal-title');
        this.submitButton = this.modal?.querySelector('#submitButton');
        this.form = this.modal?.querySelector('#documentForm');
        this.fileUploadSection = this.modal?.querySelector('#fileUploadSection');
        this.documentDropZone = document.getElementById('documentFileDropZone');
        this.documentUploadEmptyState = document.getElementById('documentUploadEmptyState');
        this.documentCurrentFileState = document.getElementById('documentCurrentFileState');
        this.currentDocumentFileLink = document.getElementById('currentDocumentFileLink');
        this.currentDocumentFileNamePlain = document.getElementById('currentDocumentFileNamePlain');
        this.documentPendingReplaceRow = document.getElementById('documentPendingReplaceRow');
        this.documentPendingReplaceName = document.getElementById('documentPendingReplaceName');
        this.documentClearReplaceBtn = document.getElementById('documentClearReplaceBtn');
        this.documentUploadTriggerLabel = document.getElementById('documentUploadTriggerLabel');
        this.fileInput = this.modal?.querySelector('#document');

        // Form sections
        this.documentTypeSelect = document.getElementById('documentType');
        this.languageSection = document.getElementById('languageSection');
        this.yearSection = document.getElementById('yearSection');
        this.isPublicCheckbox = document.getElementById('is_public');
        this.publicHelpText = document.getElementById('publicHelpText');
        this.languageSelect = document.getElementById('language');
        this.thumbnailSection = document.getElementById('thumbnailSection');

        // Period type elements
        this.periodTypeSelect = document.getElementById('period-type');
        this.singleYearField = document.getElementById('single-year');
        this.startYearField = document.getElementById('start-year');
        this.endYearField = document.getElementById('end-year');
        this.startMonthYearField = document.getElementById('start-month-year');
        this.startMonthSelect = document.getElementById('start-month');
        this.endMonthYearField = document.getElementById('end-month-year');
        this.endMonthSelect = document.getElementById('end-month');
        this.hiddenYearField = document.getElementById('year');

        this.linkedEntityTypeSelect = document.getElementById('linkedEntityType');
        this.linkedEntityIdSelect = document.getElementById('linkedEntityId');
        this.countrySelectWrap = document.getElementById('countrySelectWrap');
        this.linkedEntityIdWrap = document.getElementById('linkedEntityIdWrap');
        this.countrySelect = document.getElementById('country');
        this.lockEntityToNav = Boolean(
            typeof window !== 'undefined' && window.documentsModalLockEntityToNav
        );
        this.documentModalEntitySelect = document.getElementById('documentModalEntitySelect');
        this.useDocumentModalEntityDropdown = Boolean(this.documentModalEntitySelect);

        this.uploadText = this.documentUploadTriggerLabel;
        this.defaultUploadLabelText =
            (this.documentUploadTriggerLabel?.textContent || 'Upload a file').trim();
        this.defaultText = this.defaultUploadLabelText;
    }

    attachEventListeners() {
        // Modal control buttons
        const uploadBtn = document.querySelector('[data-action="open-modal"]');
        if (uploadBtn) {
            uploadBtn.addEventListener('click', () => {
                void this.openModal('upload');
            });
        }

        // Only buttons inside the upload/edit modal — never global `[data-action="close-modal"]`
        // (other dialogs, e.g. delete confirm, reuse that attribute and must not call this.closeModal).
        this.modal?.querySelectorAll('[data-action="close-modal"]').forEach((button) => {
            button.addEventListener('click', () => this.closeModal());
        });

        // Close on overlay click
        if (this.modalOverlay) {
            this.modalOverlay.addEventListener('click', (e) => {
                if (e.target === this.modalOverlay) {
                    this.closeModal();
                }
            });
        }

        // Close on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && !this.modal?.classList.contains('hidden')) {
                this.closeModal();
            }
        });

        if (this.linkedEntityTypeSelect) {
            this.linkedEntityTypeSelect.addEventListener('change', () => {
                this.onLinkedEntityTypeChange();
            });
        }

        if (this.documentModalEntitySelect) {
            this.documentModalEntitySelect.addEventListener('change', () => {
                this.syncDocumentModalEntityFromSelect();
            });
        }

        // Edit document buttons
        $(document).on('click', '.edit-document', async (e) => {
            e.preventDefault();
            const $el = $(e.currentTarget);
            const docData = {
                docId: $el.data('doc-id'),
                countryId: $el.data('country-id'),
                linkedEntityType: $el.data('linked-entity-type') || 'country',
                linkedEntityId: $el.data('linked-entity-id'),
                documentType: $el.data('document-type'),
                language: $el.data('language'),
                year: $el.data('year'),
                isPublic: $el.data('is-public'),
                status: $el.data('status'),
                filename: $el.data('filename'),
                downloadUrl: $el.data('download-url') || '',
                hasThumbnail: $el.data('has-thumbnail') || false,
                thumbnailFilename: $el.data('thumbnail-filename') || null
            };
            await this.openModal('edit', docData);
        });

        // File input change
        if (this.fileInput) {
            this.fileInput.addEventListener('change', (e) => {
                if (e.target.files && e.target.files[0]) {
                    this.updateFileDisplay(e.target.files[0].name);
                } else {
                    this.updateFileDisplay(null);
                }
                // Update thumbnail availability when file selection changes
                this.updateThumbnailAvailability();
            });
        }

        // Document type change
        if (this.documentTypeSelect) {
            this.documentTypeSelect.addEventListener('change', () => this.handleDocumentTypeChange());
        }

        // Public checkbox change
        if (this.isPublicCheckbox) {
            this.isPublicCheckbox.addEventListener('change', () => this.handleThumbnailVisibility());
        }

        // Period type change
        if (this.periodTypeSelect) {
            this.periodTypeSelect.addEventListener('change', () => this.togglePeriodFields());

            // Period field inputs with validation
            const validateAndGenerate = () => {
                this.validateDateRanges();
                this.generatePeriodName();
            };

            const bind = (el) => {
                if (!el) return;
                const eventType = el.tagName === 'SELECT' ? 'change' : 'input';
                el.addEventListener(eventType, validateAndGenerate);
            };

            bind(this.singleYearField);
            bind(this.startYearField);
            bind(this.endYearField);
            bind(this.startMonthYearField);
            bind(this.startMonthSelect);
            bind(this.endMonthYearField);
            bind(this.endMonthSelect);
        }

        // Form submission validation and double-submit prevention
        if (this.form) {
            this.form.addEventListener('submit', (e) => {
                this.syncDocumentModalEntityFromSelect();
                // Prevent double submission
                if (this.isSubmitting) {
                    e.preventDefault();
                    return false;
                }

                // Validate date ranges
                if (!this.validateDateRanges()) {
                    e.preventDefault();
                    if (window.showAlert) window.showAlert('Please correct the date range errors before submitting.', 'warning');
                    return false;
                }

                // Mark as submitting and disable button
                this.isSubmitting = true;
                this.setSubmitButtonLoading(true);
            });
        }

        // Drag and drop
        this.setupDragAndDrop();

        if (this.documentClearReplaceBtn) {
            this.documentClearReplaceBtn.addEventListener('click', () => {
                if (this.fileInput) {
                    this.fileInput.value = '';
                }
                this.updateFileDisplay(null);
            });
        }
    }

    async openModal(mode, docData = {}) {
        this.isEditMode = mode === 'edit';

        if (this.isEditMode) {
            await this.populateEditMode(docData);
        } else {
            this.populateUploadMode();
        }

        this.modal?.classList.remove('hidden');
    }

    syncDocumentModalEntityFromSelect() {
        if (!this.documentModalEntitySelect) {
            return;
        }
        if (!this.documentModalEntitySelect.value) {
            const lt = document.getElementById('linkedEntityTypeHidden');
            const leid = document.getElementById('linkedEntityIdHidden');
            const cid = document.getElementById('countryIdHidden');
            if (lt) {
                lt.value = '';
            }
            if (leid) {
                leid.value = '';
            }
            if (cid) {
                cid.value = '';
                cid.disabled = true;
            }
            return;
        }
        const opt = this.documentModalEntitySelect.selectedOptions[0];
        if (!opt) {
            return;
        }
        const et = (opt.dataset.entityType || '').trim();
        const eidRaw = opt.dataset.entityId;
        const lt = document.getElementById('linkedEntityTypeHidden');
        const leid = document.getElementById('linkedEntityIdHidden');
        const cid = document.getElementById('countryIdHidden');
        if (lt) {
            lt.value = et;
        }
        if (leid) {
            leid.value = eidRaw != null && eidRaw !== '' ? String(eidRaw) : '';
        }
        if (cid) {
            if (et.toLowerCase() === 'country' && eidRaw != null && eidRaw !== '') {
                cid.disabled = false;
                cid.value = String(eidRaw);
            } else {
                cid.value = '';
                cid.disabled = true;
            }
        }
    }

    async onLinkedEntityTypeChange() {
        if (!this.linkedEntityTypeSelect) {
            return;
        }
        const t = (this.linkedEntityTypeSelect.value || 'country').toLowerCase();
        if (t === 'country') {
            this.countrySelectWrap?.classList.remove('hidden');
            this.linkedEntityIdWrap?.classList.add('hidden');
            if (this.countrySelect) {
                this.countrySelect.required = true;
            }
            if (this.linkedEntityIdSelect) {
                this.linkedEntityIdSelect.required = false;
                this.linkedEntityIdSelect.innerHTML = `<option value="">${'Select an entity'}</option>`;
            }
            return;
        }
        this.countrySelectWrap?.classList.add('hidden');
        this.linkedEntityIdWrap?.classList.remove('hidden');
        if (this.countrySelect) {
            this.countrySelect.required = false;
            this.countrySelect.value = '';
        }
        if (this.linkedEntityIdSelect) {
            this.linkedEntityIdSelect.required = true;
        }
        await this.loadStandaloneEntityOptions(t);
    }

    async loadStandaloneEntityOptions(entityType) {
        if (!this.linkedEntityIdSelect) {
            return;
        }
        const base = (window.standaloneEntityOptionsUrl || '').trim();
        if (!base) {
            this.linkedEntityIdSelect.innerHTML = `<option value="">${'Configure standaloneEntityOptionsUrl'}</option>`;
            return;
        }
        const url = `${base}${base.includes('?') ? '&' : '?'}entity_type=${encodeURIComponent(entityType)}`;
        const fetchFn = (window.getApiFetch && window.getApiFetch()) || window.apiFetch || fetch;
        this.linkedEntityIdSelect.innerHTML = `<option value="">${'Loading…'}</option>`;
        try {
            const res = await fetchFn(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
            const data = await res.json().catch(() => ({}));
            const list = (data && data.entities) || [];
            const _escAttr = v => String(v == null ? '' : v).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            const opts = [`<option value="">${'Select an entity'}</option>`];
            for (let i = 0; i < list.length; i += 1) {
                const row = list[i];
                opts.push(`<option value="${_escAttr(row.id)}">${_escAttr(row.name || row.id)}</option>`);
            }
            this.linkedEntityIdSelect.innerHTML = opts.join('');
        } catch (err) {
            console.error('Entity options load failed', err);
            this.linkedEntityIdSelect.innerHTML = `<option value="">${'Failed to load entities'}</option>`;
        }
    }

    async populateEditMode(docData) {
        this.currentDocumentId = docData.docId;
        this.currentDocumentThumbnail = docData.hasThumbnail || false;
        this.currentDocumentThumbnailFilename = docData.thumbnailFilename || null;
        this.currentDocumentFilename = docData.filename || null;
        this.currentDocumentDownloadUrl = (docData.downloadUrl && String(docData.downloadUrl).trim()) || '';

        this.modalTitle.textContent = this.modalTitle.dataset.editText || 'Edit Document';
        this.submitButton.textContent = this.submitButton.dataset.updateText || 'Update';
        this.fileUploadSection.style.display = 'block';
        this.fileInput.required = false;
        if (this.fileInput) {
            this.fileInput.value = '';
        }
        this.syncDocumentFilePanelForEdit();

        // Set form action
        const nextUrl = (window.documentsNextUrl || '').trim();
        this.form.action = `/admin/documents/edit/${docData.docId}${nextUrl ? '?next=' + encodeURIComponent(nextUrl) : ''}`;

        if (this.useDocumentModalEntityDropdown) {
            const entityLinkType = (docData.linkedEntityType || 'country').toLowerCase();
            const leid = docData.linkedEntityId != null && docData.linkedEntityId !== ''
                ? String(docData.linkedEntityId)
                : (docData.countryId != null && docData.countryId !== '' ? String(docData.countryId) : '');
            const v = leid ? `${entityLinkType}:${leid}` : '';
            if (v && this.documentModalEntitySelect) {
                const has = Array.from(this.documentModalEntitySelect.options || []).some((o) => o.value === v);
                if (has) {
                    this.documentModalEntitySelect.value = v;
                }
            }
            this.syncDocumentModalEntityFromSelect();
        } else if (!this.lockEntityToNav) {
            const entityLinkType = (docData.linkedEntityType || 'country').toLowerCase();
            if (this.linkedEntityTypeSelect) {
                this.linkedEntityTypeSelect.value = entityLinkType;
            }
            await this.onLinkedEntityTypeChange();
            if (entityLinkType === 'country') {
                const countrySelect = document.getElementById('country');
                const cid = docData.linkedEntityId != null && docData.linkedEntityId !== ''
                    ? docData.linkedEntityId
                    : docData.countryId;
                if (countrySelect && cid != null && cid !== '') {
                    countrySelect.value = String(cid);
                }
            } else if (this.linkedEntityIdSelect && docData.linkedEntityId != null && docData.linkedEntityId !== '') {
                this.linkedEntityIdSelect.value = String(docData.linkedEntityId);
            }
        }
        this.documentTypeSelect.value = docData.documentType;

        // Add document type if not in list
        if (this.documentTypeSelect.value !== docData.documentType) {
            const newOption = document.createElement('option');
            newOption.value = docData.documentType;
            newOption.textContent = docData.documentType;
            newOption.selected = true;
            this.documentTypeSelect.appendChild(newOption);
        }

        // Handle document type specific behavior
        this.handleDocumentTypeChange();

        // Set language if not Cover Image
        if (docData.documentType !== 'Cover Image') {
            this.languageSelect.value = docData.language || '';
        }

        // Parse and set year/period
        if (docData.documentType !== 'Cover Image' && docData.year) {
            this.parseExistingPeriod(String(docData.year));
        }

        // Set public checkbox
        this.isPublicCheckbox.checked = String(docData.isPublic).toLowerCase() === 'true';

        // Show status section for admins
        const statusSection = document.getElementById('statusSection');
        if (window.isAdmin) {
            statusSection?.classList.remove('hidden');
            const statusSelect = document.getElementById('status');
            if (statusSelect) statusSelect.value = docData.status || 'Pending';
        } else {
            statusSection?.classList.add('hidden');
        }

        // Handle thumbnail visibility
        this.handleThumbnailVisibility();

        // Update thumbnail availability (in edit mode, file exists so enable it)
        this.updateThumbnailAvailability();

        // Ensure grid layout is correct
        this.updateFileUploadGridLayout();
        this.updateFileDisplay(null);
    }

    populateUploadMode() {
        this.modalTitle.textContent = this.modalTitle.dataset.uploadText || 'Upload New Document';
        this.submitButton.textContent = this.submitButton.dataset.uploadBtnText || 'Upload';
        this.fileUploadSection.style.display = 'block';
        document.getElementById('statusSection')?.classList.add('hidden');
        this.fileInput.required = true;
        this.form.action = this.form.dataset.uploadAction || '/admin/documents/upload';

        // Reset form
        this.form.reset();
        this.documentTypeSelect.value = '';
        this.handleDocumentTypeChange();

        // Ensure year selectors are populated and defaulted (form.reset() clears selects)
        this.ensureYearSelectOptions();
        this.setDefaultYearsIfEmpty();
        this.generatePeriodName();

        if (this.useDocumentModalEntityDropdown) {
            const dv = (this.form?.dataset?.defaultEntityValue || '').trim();
            if (dv) {
                const has = Array.from(this.documentModalEntitySelect.options || []).some((o) => o.value === dv);
                if (has) {
                    this.documentModalEntitySelect.value = dv;
                }
            } else if (!this.lockEntityToNav) {
                this.documentModalEntitySelect.value = '';
            }
            this.syncDocumentModalEntityFromSelect();
        } else if (!this.lockEntityToNav) {
            if (this.linkedEntityTypeSelect) {
                this.linkedEntityTypeSelect.value = 'country';
            }
            void this.onLinkedEntityTypeChange();
        }

        // Disable thumbnail section initially (no file selected yet)
        this.updateThumbnailAvailability();

        // Ensure grid layout is correct (thumbnail hidden initially)
        this.updateFileUploadGridLayout();
        this.syncDocumentFilePanelForUpload();
    }

    syncDocumentFilePanelForEdit() {
        this.documentUploadEmptyState?.classList.add('hidden');
        this.documentCurrentFileState?.classList.remove('hidden');
        const displayName = this.currentDocumentFilename || '—';
        const url = (this.currentDocumentDownloadUrl || '').trim();
        if (this.currentDocumentFileLink && this.currentDocumentFileNamePlain) {
            if (url) {
                this.currentDocumentFileLink.setAttribute('href', url);
                this.currentDocumentFileLink.textContent = displayName;
                this.currentDocumentFileLink.classList.remove('hidden');
                this.currentDocumentFileNamePlain.classList.add('hidden');
            } else {
                this.currentDocumentFileNamePlain.textContent = displayName;
                this.currentDocumentFileNamePlain.classList.remove('hidden');
                this.currentDocumentFileLink.classList.add('hidden');
                this.currentDocumentFileLink.setAttribute('href', '#');
            }
        }
        this.documentPendingReplaceRow?.classList.add('hidden');
        if (this.documentPendingReplaceName) {
            this.documentPendingReplaceName.textContent = '';
        }
    }

    syncDocumentFilePanelForUpload() {
        this.documentUploadEmptyState?.classList.remove('hidden');
        this.documentCurrentFileState?.classList.add('hidden');
        this.documentPendingReplaceRow?.classList.add('hidden');
        if (this.documentPendingReplaceName) {
            this.documentPendingReplaceName.textContent = '';
        }
        if (this.documentUploadTriggerLabel) {
            this.documentUploadTriggerLabel.textContent = this.defaultUploadLabelText;
        }
        this.currentDocumentDownloadUrl = '';
    }

    closeModal() {
        this.modal?.classList.add('hidden');
        this.form?.reset();
        this.updateFileDisplay(null);
        this.isEditMode = false;

        // Reset submission state
        this.isSubmitting = false;
        this.setSubmitButtonLoading(false);

        // Clear date validation errors
        this.clearDateValidationErrors();

        // Reset period fields
        if (this.periodTypeSelect) {
            this.periodTypeSelect.value = 'single-year';
            this.togglePeriodFields();
        }

        // Reset thumbnail availability
        this.updateThumbnailAvailability();

        // Reset to upload state
        this.populateUploadMode();
    }

    /**
     * Populate year <select> elements with a scrollable year list.
     * Keeps any existing placeholder option and avoids double-population.
     */
    ensureYearSelectOptions() {
        const yearSelects = [
            this.singleYearField,
            this.startYearField,
            this.endYearField,
            this.startMonthYearField,
            this.endMonthYearField
        ].filter(Boolean);

        const currentYear = new Date().getFullYear();

        yearSelects.forEach((el) => {
            if (!el || el.tagName !== 'SELECT') return;

            // If it already contains numeric year options, don't repopulate.
            const hasYearOptions = Array.from(el.options || []).some(o => /^\d{4}$/.test(String(o.value || '')));
            if (hasYearOptions) return;

            const minYearAttr = parseInt(el.getAttribute('data-year-min') || el.getAttribute('min') || '2000', 10);
            const maxYearAttr = parseInt(el.getAttribute('data-year-max') || el.getAttribute('max') || '2100', 10);
            const minYear = Number.isFinite(minYearAttr) ? minYearAttr : 2000;
            const hardMax = Number.isFinite(maxYearAttr) ? maxYearAttr : 2100;
            const maxYear = Math.min(hardMax, currentYear + 5);

            // Preserve first option if it's an empty placeholder
            const placeholderOption = (el.options && el.options.length > 0 && !el.options[0].value)
                ? el.options[0].cloneNode(true)
                : null;

            el.innerHTML = '';
            if (placeholderOption) el.appendChild(placeholderOption);

            for (let y = maxYear; y >= minYear; y -= 1) {
                const opt = document.createElement('option');
                opt.value = String(y);
                opt.textContent = String(y);
                el.appendChild(opt);
            }
        });
    }

    /**
     * Default year selectors to current year when empty.
     * Does not override edit-mode populated values.
     */
    setDefaultYearsIfEmpty() {
        const currentYear = String(new Date().getFullYear());
        const setIfEmpty = (el) => {
            if (!el) return;
            if (String(el.value || '').trim()) return;
            el.value = currentYear;
        };

        setIfEmpty(this.singleYearField);
        setIfEmpty(this.startYearField);
        setIfEmpty(this.endYearField);
        setIfEmpty(this.startMonthYearField);
        setIfEmpty(this.endMonthYearField);
    }

    /**
     * Set submit button loading state
     * @param {boolean} loading - Whether to show loading state
     */
    setSubmitButtonLoading(loading) {
        if (!this.submitButton) return;

        if (loading) {
            // Store original text for restoration
            if (!this.submitButton.dataset.originalText) {
                this.submitButton.dataset.originalText = this.submitButton.textContent;
            }
            this.submitButton.disabled = true;
            this.submitButton.classList.add('opacity-50', 'cursor-not-allowed');

            // Create loading content
            const spinner = document.createElement('i');
            spinner.className = 'fas fa-spinner fa-spin mr-2';
            this.submitButton.textContent = '';
            this.submitButton.appendChild(spinner);
            this.submitButton.appendChild(document.createTextNode(
                this.isEditMode ? 'Updating...' : 'Uploading...'
            ));
        } else {
            this.submitButton.disabled = false;
            this.submitButton.classList.remove('opacity-50', 'cursor-not-allowed');

            // Restore original text
            const originalText = this.submitButton.dataset.originalText;
            if (originalText) {
                this.submitButton.textContent = originalText;
                delete this.submitButton.dataset.originalText;
            }
        }
    }

    applyDocumentFileSizeHelp(useImage) {
        ['documentFileSizeHelp', 'documentFileSizeHelpEdit'].forEach((id) => {
            const el = document.getElementById(id);
            if (!el) return;
            el.textContent = useImage
                ? (el.dataset.imageText || 'Image files only (PNG, JPG, etc.) up to 10MB')
                : (el.dataset.defaultText || 'Any file up to 10MB');
        });
    }

    handleDocumentTypeChange() {
        const selectedType = this.documentTypeSelect?.value;

        if (selectedType === 'Cover Image') {
            // Hide Year and Language sections
            if (this.languageSection) this.languageSection.style.display = 'none';
            if (this.yearSection) this.yearSection.style.display = 'none';

            // Make language and year not required
            if (this.languageSelect) this.languageSelect.required = false;
            if (this.hiddenYearField) this.hiddenYearField.required = false;

            // Set public checkbox to checked and disabled
            if (this.isPublicCheckbox) {
                this.isPublicCheckbox.checked = true;
                this.isPublicCheckbox.disabled = true;
            }

            // Update help text
            if (this.publicHelpText) {
                this.publicHelpText.textContent = this.publicHelpText.dataset.coverText || 'Cover images are always public and visible on country pages';
            }

            // Clear values
            if (this.languageSelect) this.languageSelect.value = '';
            if (this.hiddenYearField) this.hiddenYearField.value = '';

            // Hide thumbnail section
            this.thumbnailSection?.classList.add('hidden');

            // Set file input to only accept images
            if (this.fileInput) this.fileInput.setAttribute('accept', 'image/*');
            this.applyDocumentFileSizeHelp(true);
        } else {
            // Show Year and Language sections
            if (this.languageSection) this.languageSection.style.display = 'block';
            if (this.yearSection) this.yearSection.style.display = 'block';

            // Make language and year required
            if (this.languageSelect) this.languageSelect.required = true;
            if (this.hiddenYearField) this.hiddenYearField.required = true;

            // Make public checkbox editable
            if (this.isPublicCheckbox) this.isPublicCheckbox.disabled = false;

            // Reset help text
            if (this.publicHelpText) {
                this.publicHelpText.textContent = this.publicHelpText.dataset.defaultText || 'Check this box to make the document publicly accessible';
            }

            // Remove file type restriction
            if (this.fileInput) this.fileInput.removeAttribute('accept');
            this.applyDocumentFileSizeHelp(false);

            // Handle thumbnail section
            this.handleThumbnailVisibility();
        }
    }

    togglePeriodFields() {
        const periodType = this.periodTypeSelect?.value;

        // Clear validation errors when switching period types
        this.clearDateValidationErrors();

        // Hide all period fields
        document.querySelectorAll('.period-fields').forEach(field => {
            field.classList.add('hidden');
        });

        // Show relevant fields
        if (periodType === 'single-year') {
            document.getElementById('single-year-fields')?.classList.remove('hidden');
        } else if (periodType === 'year-range') {
            document.getElementById('year-range-fields')?.classList.remove('hidden');
        } else if (periodType === 'month-range') {
            document.getElementById('month-range-fields')?.classList.remove('hidden');
        }

        this.generatePeriodName();
    }

    validateDateRanges() {
        const periodType = this.periodTypeSelect?.value;
        let isValid = true;
        let errorMessage = '';

        // Clear previous errors
        this.clearDateValidationErrors();

        if (periodType === 'year-range') {
            const startYear = parseInt(this.startYearField?.value);
            const endYear = parseInt(this.endYearField?.value);

            if (startYear && endYear && startYear > endYear) {
                isValid = false;
                errorMessage = 'Start year cannot be later than end year.';
                this.markDateFieldInvalid('start-year');
                this.markDateFieldInvalid('end-year');
                this.showCombinedDateValidationError('year-range-fields', errorMessage);
            }
        } else if (periodType === 'month-range') {
            const startYear = parseInt(this.startMonthYearField?.value);
            const startMonth = parseInt(this.startMonthSelect?.value);
            const endYear = parseInt(this.endMonthYearField?.value);
            const endMonth = parseInt(this.endMonthSelect?.value);

            if (startYear && startMonth && endYear && endMonth) {
                // Create date objects for comparison
                const startDate = new Date(startYear, startMonth - 1, 1);
                const endDate = new Date(endYear, endMonth - 1, 1);

                if (startDate > endDate) {
                    isValid = false;
                    errorMessage = 'Start period cannot be later than end period.';
                    this.showDateValidationError('start-month-year', errorMessage);
                    this.showDateValidationError('start-month', errorMessage);
                    this.showDateValidationError('end-month-year', errorMessage);
                    this.showDateValidationError('end-month', errorMessage);
                }
            }
        }

        return isValid;
    }

    showDateValidationError(fieldId, message) {
        const field = document.getElementById(fieldId);
        if (!field) return;

        // Add error styling
        field.classList.add('border-red-500', 'ring-2', 'ring-red-200');

        // Find or create error message element
        let errorDiv = field.parentElement.querySelector('.date-validation-error');
        if (!errorDiv) {
            errorDiv = document.createElement('div');
            errorDiv.className = 'date-validation-error text-red-600 text-xs mt-1';
            field.parentElement.appendChild(errorDiv);
        }
        errorDiv.textContent = message;
    }

    /**
     * Highlight a field as invalid without adding duplicate error text.
     * Used when a single error message should span multiple fields.
     */
    markDateFieldInvalid(fieldId) {
        const field = document.getElementById(fieldId);
        if (!field) return;
        field.classList.add('border-red-500', 'ring-2', 'ring-red-200');
    }

    /**
     * Show a single validation message under a whole section (e.g. year range).
     * The message spans the full width of the section, under both fields.
     */
    showCombinedDateValidationError(sectionId, message) {
        const section = document.getElementById(sectionId);
        if (!section) return;

        let errorDiv = section.querySelector('.date-validation-error.date-validation-error-combined');
        if (!errorDiv) {
            errorDiv = document.createElement('div');
            errorDiv.className = 'date-validation-error date-validation-error-combined text-red-600 text-xs mt-1';
            section.appendChild(errorDiv);
        }
        errorDiv.textContent = message;
    }

    clearDateValidationErrors() {
        // Remove error styling from all period fields
        const periodFields = [
            'start-year', 'end-year',
            'start-month-year', 'start-month',
            'end-month-year', 'end-month'
        ];

        periodFields.forEach(fieldId => {
            const field = document.getElementById(fieldId);
            if (field) {
                field.classList.remove('border-red-500', 'ring-2', 'ring-red-200');
            }
        });

        // Remove error messages
        document.querySelectorAll('.date-validation-error').forEach(el => el.remove());
    }

    generatePeriodName() {
        // Validate dates before generating period name
        if (!this.validateDateRanges()) {
            // Don't generate period name if validation fails
            return;
        }

        const periodType = this.periodTypeSelect?.value;
        let periodName = '';

        if (periodType === 'single-year') {
            const year = this.singleYearField?.value;
            if (year) periodName = year;
        } else if (periodType === 'year-range') {
            const startYear = this.startYearField?.value;
            const endYear = this.endYearField?.value;
            if (startYear && endYear) {
                periodName = startYear === endYear ? startYear : `${startYear}-${endYear}`;
            } else if (startYear) {
                periodName = startYear;
            }
        } else if (periodType === 'month-range') {
            const startYear = this.startMonthYearField?.value;
            const startMonth = this.startMonthSelect?.value;
            const endYear = this.endMonthYearField?.value;
            const endMonth = this.endMonthSelect?.value;

            if (startYear && startMonth && endYear && endMonth) {
                const startMonthName = this.monthNames[startMonth];
                const endMonthName = this.monthNames[endMonth];

                if (startYear === endYear && startMonth === endMonth) {
                    periodName = `${startMonthName} ${startYear}`;
                } else if (startYear === endYear) {
                    periodName = `${startMonthName}-${endMonthName} ${startYear}`;
                } else {
                    periodName = `${startMonthName} ${startYear}-${endMonthName} ${endYear}`;
                }
            }
        }

        // Update hidden field
        if (this.hiddenYearField) {
            this.hiddenYearField.value = periodName || '';
        }
    }

    parseExistingPeriod(periodName) {
        if (!periodName || periodName === 'None' || periodName === '' || periodName === 'null') return;

        const yearPattern = /^(\d{4})$/;
        const yearRangePattern = /^(\d{4})-(\d{4})$/;
        const monthPattern = /^([A-Za-z]{3})\s+(\d{4})$/;
        const monthRangePattern = /^([A-Za-z]{3})\s+(\d{4})-([A-Za-z]{3})\s+(\d{4})$/;
        const monthYearRangePattern = /^([A-Za-z]{3})-([A-Za-z]{3})\s+(\d{4})$/;

        const monthToNumber = {
            'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
            'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
            'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
        };

        if (yearPattern.test(periodName)) {
            // Single year: "2024"
            const match = periodName.match(yearPattern);
            this.periodTypeSelect.value = 'single-year';
            this.singleYearField.value = match[1];
        } else if (yearRangePattern.test(periodName)) {
            // Year range: "2024-2025"
            const match = periodName.match(yearRangePattern);
            this.periodTypeSelect.value = 'year-range';
            this.startYearField.value = match[1];
            this.endYearField.value = match[2];
        } else if (monthRangePattern.test(periodName)) {
            // Month range: "Jan 2024-Dec 2025"
            const match = periodName.match(monthRangePattern);
            this.periodTypeSelect.value = 'month-range';
            this.startMonthSelect.value = monthToNumber[match[1]];
            this.startMonthYearField.value = match[2];
            this.endMonthSelect.value = monthToNumber[match[3]];
            this.endMonthYearField.value = match[4];
        } else if (monthYearRangePattern.test(periodName)) {
            // Month range same year: "Jan-Dec 2024"
            const match = periodName.match(monthYearRangePattern);
            this.periodTypeSelect.value = 'month-range';
            this.startMonthSelect.value = monthToNumber[match[1]];
            this.startMonthYearField.value = match[3];
            this.endMonthSelect.value = monthToNumber[match[2]];
            this.endMonthYearField.value = match[3];
        } else if (monthPattern.test(periodName)) {
            // Single month: "Jan 2024"
            const match = periodName.match(monthPattern);
            this.periodTypeSelect.value = 'month-range';
            this.startMonthSelect.value = monthToNumber[match[1]];
            this.startMonthYearField.value = match[2];
            this.endMonthSelect.value = monthToNumber[match[1]];
            this.endMonthYearField.value = match[2];
        }

        this.togglePeriodFields();

        // Validate the parsed dates
        this.validateDateRanges();
    }

    handleThumbnailVisibility() {
        // Never show thumbnails for Cover Image type
        if (this.documentTypeSelect?.value === 'Cover Image') {
            this.thumbnailSection?.classList.add('hidden');
            this.updateFileUploadGridLayout();
            return;
        }

        if (this.isPublicCheckbox?.checked) {
            this.thumbnailSection?.classList.remove('hidden');
            this.updateThumbnailComponent();
            // Update availability based on file selection
            this.updateThumbnailAvailability();
        } else {
            this.thumbnailSection?.classList.add('hidden');
        }

        // Update grid layout based on thumbnail visibility
        this.updateFileUploadGridLayout();
    }

    /**
     * Update the grid layout for file upload and thumbnail sections.
     * When thumbnail is hidden, file upload takes full width.
     * When thumbnail is visible, they share the width equally.
     */
    updateFileUploadGridLayout() {
        if (!this.fileUploadSection || !this.thumbnailSection) return;

        // Find the parent grid container
        const gridContainer = this.fileUploadSection.parentElement;
        if (!gridContainer || !gridContainer.classList.contains('grid')) return;

        const isThumbnailVisible = !this.thumbnailSection.classList.contains('hidden');

        if (isThumbnailVisible) {
            // Thumbnail visible: use two columns
            gridContainer.classList.remove('md:grid-cols-1');
            gridContainer.classList.add('md:grid-cols-2');
        } else {
            // Thumbnail hidden: use single column (full width for file upload)
            gridContainer.classList.remove('md:grid-cols-2');
            gridContainer.classList.add('md:grid-cols-1');
        }
    }

    /**
     * Enable/disable thumbnail section based on whether a file is selected.
     * In upload mode: disable if no file selected
     * In edit mode: always enable (file already exists)
     */
    updateThumbnailAvailability() {
        if (!this.thumbnailSection) return;

        // Don't do anything if thumbnail section is hidden
        if (this.thumbnailSection.classList.contains('hidden')) {
            // Update grid layout when thumbnail is hidden
            this.updateFileUploadGridLayout();
            return;
        }

        // In edit mode, always enable (document already exists)
        if (this.isEditMode) {
            this.enableThumbnailSection();
            return;
        }

        // In upload mode, check if file is selected
        const hasFile = this.fileInput?.files && this.fileInput.files.length > 0;

        if (hasFile) {
            this.enableThumbnailSection();
        } else {
            this.disableThumbnailSection();
        }

        // Update grid layout based on thumbnail visibility
        this.updateFileUploadGridLayout();
    }

    /**
     * Enable thumbnail section (make it interactive)
     */
    enableThumbnailSection() {
        if (!this.thumbnailSection) return;
        this.thumbnailSection.classList.remove('opacity-50', 'pointer-events-none');
        this.thumbnailSection.style.cursor = '';

        // Enable all inputs and buttons within
        const inputs = this.thumbnailSection.querySelectorAll('input, button');
        inputs.forEach(el => {
            el.disabled = false;
            el.style.pointerEvents = '';
        });
    }

    /**
     * Disable thumbnail section (make it visually disabled and non-interactive)
     */
    disableThumbnailSection() {
        if (!this.thumbnailSection) return;
        this.thumbnailSection.classList.add('opacity-50', 'pointer-events-none');
        this.thumbnailSection.style.cursor = 'not-allowed';

        // Disable all inputs and buttons within
        const inputs = this.thumbnailSection.querySelectorAll('input, button');
        inputs.forEach(el => {
            el.disabled = true;
            el.style.pointerEvents = 'none';
        });
    }

    updateThumbnailComponent() {
        if (!this.isEditMode) return;

        const entityId = this.currentDocumentId;
        const entityType = 'document';
        const languageCode = this.languageSelect?.value || 'en';

        const currentThumbnailUrl = this.currentDocumentThumbnail ?
            `/admin/documents/${entityId}/thumbnail` : null;
        const currentThumbnailFilename = this.currentDocumentThumbnailFilename;

        const canGenerate = this.currentDocumentFilename &&
            this.currentDocumentFilename.toLowerCase().endsWith('.pdf');

        // Update current thumbnail display
        const currentThumbnailDisplay = document.getElementById('currentThumbnailDisplay');
        const currentThumbnailImg = document.getElementById('currentThumbnailImg');
        const currentThumbnailFilenameEl = document.getElementById('currentThumbnailFilename');
        const thumbnailHelpText = document.getElementById('thumbnailHelpText');

        if (currentThumbnailUrl) {
            if (currentThumbnailDisplay) currentThumbnailDisplay.style.display = 'block';
            if (currentThumbnailImg) currentThumbnailImg.src = currentThumbnailUrl;
            if (currentThumbnailFilenameEl) {
                currentThumbnailFilenameEl.textContent = `${currentThumbnailFilenameEl.dataset.prefix || 'Original name:'} ${currentThumbnailFilename || 'Generated automatically'}`;
            }
            if (thumbnailHelpText) {
                thumbnailHelpText.textContent = thumbnailHelpText.dataset.replaceText || 'To replace the current thumbnail, choose a new image below.';
            }

            // Update delete button onclick
            const deleteBtn = document.getElementById('delete-thumb-btn');
            if (deleteBtn) {
                deleteBtn.setAttribute('data-action', 'thumbnail:delete');
                deleteBtn.setAttribute('data-entity-id', entityId);
                deleteBtn.setAttribute('data-entity-type', entityType);
                deleteBtn.setAttribute('data-language-code', languageCode);
            }
        } else {
            if (currentThumbnailDisplay) currentThumbnailDisplay.style.display = 'none';
            if (thumbnailHelpText) {
                thumbnailHelpText.textContent = thumbnailHelpText.dataset.defaultText || 'Upload an image to serve as the thumbnail (optional).';
            }
        }

        // Update generate button
        const generateSection = document.getElementById('generateThumbnailSection');
        const generateBtn = document.getElementById('generate-btn');

        if (canGenerate) {
            if (generateSection) generateSection.style.display = 'block';
            if (generateBtn) {
                generateBtn.setAttribute('data-action', 'thumbnail:generate');
                generateBtn.setAttribute('data-entity-id', entityId);
                generateBtn.setAttribute('data-entity-type', entityType);
                generateBtn.setAttribute('data-language-code', languageCode);
            }
        } else {
            if (generateSection) generateSection.style.display = 'none';
        }
    }

    updateFileDisplay(fileName) {
        if (this.isEditMode) {
            if (fileName) {
                this.documentPendingReplaceRow?.classList.remove('hidden');
                if (this.documentPendingReplaceName) {
                    this.documentPendingReplaceName.textContent = fileName;
                }
            } else {
                this.documentPendingReplaceRow?.classList.add('hidden');
                if (this.documentPendingReplaceName) {
                    this.documentPendingReplaceName.textContent = '';
                }
            }
            return;
        }
        if (this.documentUploadTriggerLabel) {
            this.documentUploadTriggerLabel.textContent = fileName || this.defaultUploadLabelText;
        }
    }

    setupDragAndDrop() {
        const dropZone = this.documentDropZone;
        if (!dropZone) return;

        const preventDefaults = (e) => {
            e.preventDefault();
            e.stopPropagation();
        };

        const highlight = () => {
            dropZone.classList.add('border-red-300', 'bg-red-50');
        };

        const unhighlight = () => {
            dropZone.classList.remove('border-red-300', 'bg-red-50');
        };

        const handleDrop = (e) => {
            const dt = e.dataTransfer;
            const files = dt.files;

            if (files && files[0]) {
                this.fileInput.files = files;
                this.updateFileDisplay(files[0].name);
            }
        };

        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, preventDefaults, false);
        });

        ['dragenter', 'dragover'].forEach(eventName => {
            dropZone.addEventListener(eventName, highlight, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, unhighlight, false);
        });

        dropZone.addEventListener('drop', handleDrop, false);
    }
}

// Thumbnail management functions (keep as global functions for onclick attributes)
function generateThumbnail(entityId, languageCode, entityType) {
    const button = document.getElementById('generate-btn');
    const buttonText = document.getElementById('generate-text');
    const statusDiv = document.getElementById('generate-status');

    // Update button to loading state
    button.disabled = true;
    buttonText.textContent = buttonText.dataset.generatingText || 'Generating...';
    button.classList.add('opacity-50', 'cursor-not-allowed');
    statusDiv.replaceChildren();
    {
        const icon = document.createElement('i');
        icon.className = 'fas fa-spinner fa-spin text-blue-500';
        const text = document.createElement('span');
        text.className = 'text-blue-600';
        text.textContent = statusDiv.dataset.generatingText || 'Generating thumbnail...';
        statusDiv.append(icon, document.createTextNode(' '), text);
    }

    // Determine endpoint
    const endpoint = entityType === 'resource'
        ? `/admin/resources/${entityId}/generate-thumbnail/${languageCode}`
        : `/admin/documents/${entityId}/generate-thumbnail`;

    const apiFn = (window.getApiFetch && window.getApiFetch()) || null;
    const fetchPromise = apiFn
        ? apiFn(endpoint, { method: 'POST' })
        : ((window.getFetch && window.getFetch()) || fetch)(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': (window.getCSRFToken && window.getCSRFToken()) || (document.querySelector('input[name="csrf_token"]') || {}).value || ''
            }
        }).then(r => r.ok ? r.json() : Promise.reject((window.httpErrorSync && window.httpErrorSync(r)) || new Error(`HTTP error! status: ${r.status}`)));

    fetchPromise.then(data => {
        if (data.success) {
            statusDiv.replaceChildren();
            {
                const icon = document.createElement('i');
                icon.className = 'fas fa-check-circle text-green-500';
                const text = document.createElement('span');
                text.className = 'text-green-600';
                text.textContent = statusDiv.dataset.successText || 'Thumbnail generated successfully!';
                statusDiv.append(icon, document.createTextNode(' '), text);
            }

            // Update thumbnail display
            const currentThumbnailDisplay = document.getElementById('currentThumbnailDisplay');
            const currentThumbnailImg = document.getElementById('currentThumbnailImg');
            const currentThumbnailFilenameEl = document.getElementById('currentThumbnailFilename');
            const thumbnailHelpText = document.getElementById('thumbnailHelpText');

            currentThumbnailDisplay.style.display = 'block';
            currentThumbnailImg.src = data.thumbnail_url + '?t=' + Date.now();
            currentThumbnailFilenameEl.textContent = currentThumbnailFilenameEl.dataset.generatedText || 'Generated automatically';
            thumbnailHelpText.textContent = thumbnailHelpText.dataset.replaceText || 'To replace the current thumbnail, choose a new image below.';

            // Update delete button
            const deleteBtn = document.getElementById('delete-thumb-btn');
            deleteBtn.setAttribute('data-action', 'thumbnail:delete');
            deleteBtn.setAttribute('data-entity-id', entityId);
            deleteBtn.setAttribute('data-entity-type', entityType);
            deleteBtn.setAttribute('data-language-code', languageCode);

            // Update button text after delay
            setTimeout(() => {
                buttonText.textContent = buttonText.dataset.regenerateText || 'Regenerate Thumbnail';
            }, 3000);
        } else {
            statusDiv.replaceChildren();
            const icon = document.createElement('i');
            icon.className = 'fas fa-exclamation-triangle text-red-500';
            const text = document.createElement('span');
            text.className = 'text-red-600';
            text.textContent = `${statusDiv.dataset.errorPrefix || 'Error:'} ${data?.message || ''}`;
            statusDiv.append(icon, document.createTextNode(' '), text);
        }
    })
    .catch(error => {
        console.error('Error generating thumbnail:', error);
        statusDiv.replaceChildren();
        const icon = document.createElement('i');
        icon.className = 'fas fa-exclamation-triangle text-red-500';
        const text = document.createElement('span');
        text.className = 'text-red-600';
        text.textContent = statusDiv.dataset.networkError || 'Network error occurred';
        statusDiv.append(icon, document.createTextNode(' '), text);
    })
    .finally(() => {
        button.disabled = false;
        button.classList.remove('opacity-50', 'cursor-not-allowed');
        if (buttonText.textContent === (buttonText.dataset.generatingText || 'Generating...')) {
            buttonText.textContent = buttonText.dataset.defaultText || 'Generate PDF Thumbnail';
        }
    });
}

function deleteThumbnail(entityId, languageCode, entityType) {
    const button = document.getElementById('delete-thumb-btn');
    const buttonText = document.getElementById('delete-thumb-text');
    const statusDiv = document.getElementById('delete-thumb-status');
    const confirmMsg = statusDiv.dataset.confirmText || 'Are you sure you want to delete the thumbnail? This action cannot be undone.';

    const performDelete = () => {
    // Update button to loading state
    button.disabled = true;
    buttonText.textContent = buttonText.dataset.deletingText || 'Deleting...';
    button.classList.add('opacity-50', 'cursor-not-allowed');
    statusDiv.replaceChildren();
    {
        const icon = document.createElement('i');
        icon.className = 'fas fa-spinner fa-spin text-blue-500';
        const text = document.createElement('span');
        text.className = 'text-blue-600';
        text.textContent = statusDiv.dataset.deletingText || 'Deleting thumbnail...';
        statusDiv.append(icon, document.createTextNode(' '), text);
    }

    // Determine endpoint
    const endpoint = entityType === 'resource'
        ? `/admin/resources/${entityId}/delete-thumbnail/${languageCode}`
        : `/admin/documents/${entityId}/delete-thumbnail`;

    const apiFn = (window.getApiFetch && window.getApiFetch()) || null;
    const fetchPromise = apiFn
        ? apiFn(endpoint, { method: 'POST' })
        : ((window.getFetch && window.getFetch()) || fetch)(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': (window.getCSRFToken && window.getCSRFToken()) || (document.querySelector('input[name="csrf_token"]') || {}).value || ''
            }
        }).then(r => r.ok ? r.json() : Promise.reject((window.httpErrorSync && window.httpErrorSync(r)) || new Error(`HTTP error! status: ${r.status}`)));

    fetchPromise.then(data => {
        if (data.success) {
            statusDiv.replaceChildren();
            {
                const icon = document.createElement('i');
                icon.className = 'fas fa-check-circle text-green-500';
                const text = document.createElement('span');
                text.className = 'text-green-600';
                text.textContent = statusDiv.dataset.successText || 'Thumbnail deleted successfully!';
                statusDiv.append(icon, document.createTextNode(' '), text);
            }

            // Hide thumbnail display
            const currentThumbnailDisplay = document.getElementById('currentThumbnailDisplay');
            const thumbnailHelpText = document.getElementById('thumbnailHelpText');

            currentThumbnailDisplay.style.display = 'none';
            thumbnailHelpText.textContent = thumbnailHelpText.dataset.defaultText || 'Upload an image to serve as the thumbnail (optional).';
        } else {
            statusDiv.replaceChildren();
            const icon = document.createElement('i');
            icon.className = 'fas fa-exclamation-triangle text-red-500';
            const text = document.createElement('span');
            text.className = 'text-red-600';
            text.textContent = `${statusDiv.dataset.errorPrefix || 'Error:'} ${data?.message || ''}`;
            statusDiv.append(icon, document.createTextNode(' '), text);
        }
    })
    .catch(error => {
        console.error('Error deleting thumbnail:', error);
        statusDiv.replaceChildren();
        const icon = document.createElement('i');
        icon.className = 'fas fa-exclamation-triangle text-red-500';
        const text = document.createElement('span');
        text.className = 'text-red-600';
        text.textContent = statusDiv.dataset.networkError || 'Network error occurred';
        statusDiv.append(icon, document.createTextNode(' '), text);
    })
    .finally(() => {
        if (button.parentNode) {
            button.disabled = false;
            button.classList.remove('opacity-50', 'cursor-not-allowed');
            if (buttonText.textContent === (buttonText.dataset.deletingText || 'Deleting...')) {
                buttonText.textContent = buttonText.dataset.defaultText || 'Delete';
            }
        }
    });
    };
    if (window.showDangerConfirmation) {
        window.showDangerConfirmation(confirmMsg, performDelete, null, 'Delete', 'Cancel', 'Confirm Delete');
    } else if (window.showConfirmation) {
        window.showConfirmation(confirmMsg, performDelete, null, 'Delete', 'Cancel', 'Confirm Delete');
    }
}

// Initialize on DOM ready
$(document).ready(function() {
    window.documentModalManager = new DocumentModalManager();
});
