/* Auto-generated from manage_assignment.html - DO NOT edit template inline JS */
/* Config is bootstrapped via window.manageAssignmentConfig in the template */

(function () {
    'use strict';
    var cfg = window.manageAssignmentConfig || {};

    $(document).ready(function() {
        var scheduleNotifBannerRefresh = null;
        var notifBannerRefreshTimer = null;

        function collectSelectedCountryIdsForPreview() {
            const seen = new Set();
            const ids = [];
            function addId(value) {
                if (!value || seen.has(value)) return;
                seen.add(value);
                ids.push(value);
            }
            document.querySelectorAll('.country-checkbox-entity:checked:not([disabled])').forEach(function(el) {
                addId(el.value);
            });
            if (!ids.length) {
                document.querySelectorAll('#country-selections-container input[type="hidden"][name="countries"]').forEach(function(el) {
                    addId(el.value);
                });
            }
            return ids;
        }

        function resolvePreviewEmailBatchCount(preview) {
            if (preview && typeof preview.email_batch_count === 'number') {
                return preview.email_batch_count;
            }
            return 0;
        }

        function formatNoFocalCountriesSuffix(preview) {
            if (!preview || !preview.countries_without_focal_count) return '';
            return (cfg.t.notifyNoFocalCountriesSuffix || '')
                .replace('{no_focal}', preview.countries_without_focal_count);
        }

        function buildNotifPreviewQueryParams(countryIds) {
            const params = new URLSearchParams();
            (countryIds || []).forEach(function(id) {
                params.append('country_ids[]', id);
            });
            const notifyAdminsEl = document.getElementById('notify_admins');
            if (notifyAdminsEl && notifyAdminsEl.checked) {
                params.set('notify_admins', '1');
            }
            return params;
        }

        function formatAdminInAppSuffix(preview) {
            if (!preview || !preview.admins_enabled) return '';
            if (preview.admin_users) {
                return (cfg.t.notifyAdminInAppLine || '')
                    .replace('{admin_users}', preview.admin_users);
            }
            if (preview.admin_total_users) {
                return (cfg.t.notifyAdminInAppAllFocal || '')
                    .replace('{admin_total}', preview.admin_total_users);
            }
            return cfg.t.notifyAdminInAppNone || '';
        }

        function formatAdminCcSuffix(preview, includeAdminCc) {
            if (!preview || !preview.admins_enabled) return '';
            if (includeAdminCc && preview.admin_email_users) {
                return (cfg.t.notifyAdminCcLine || '')
                    .replace('{admin_email_users}', preview.admin_email_users);
            }
            if (preview.admin_users) {
                return cfg.t.notifyAdminCcPrompt || '';
            }
            return '';
        }

        function formatNotifRecipientsSummary(preview, includeAdminCc, localCountryIds) {
            if (!preview) return '';
            const emailBatches = resolvePreviewEmailBatchCount(preview);
            let text = (cfg.t.notifyRecipientsSummary || '')
                .replace('{users}', preview.total_focal_users)
                .replace('{email_users}', preview.email_users)
                .replace('{entities}', emailBatches)
                .replace('{no_focal_suffix}', formatNoFocalCountriesSuffix(preview))
                .replace('{admin_suffix}', formatAdminInAppSuffix(preview))
                .replace('{admin_cc_suffix}', formatAdminCcSuffix(preview, includeAdminCc));
            if (!preview.admins_enabled) {
                text += cfg.t.notifyAdminsDisabledHint || '';
            }
            return text;
        }

        // --- Period Name Generation and Parsing ---
        const periodTypeSelect = document.getElementById('period-type');
        const singleYearField = document.getElementById('single-year');
        const startYearField = document.getElementById('start-year');
        const endYearField = document.getElementById('end-year');
        const startMonthYearField = document.getElementById('start-month-year');
        const startMonthSelect = document.getElementById('start-month');
        const endMonthYearField = document.getElementById('end-month-year');
        const endMonthSelect = document.getElementById('end-month');
        const hiddenPeriodNameField = document.querySelector('input[name="period_name"]');

        // Month names for display
        const monthNames = {
            '01': 'Jan', '02': 'Feb', '03': 'Mar', '04': 'Apr',
            '05': 'May', '06': 'Jun', '07': 'Jul', '08': 'Aug',
            '09': 'Sep', '10': 'Oct', '11': 'Nov', '12': 'Dec'
        };

        const yearFields = [
            singleYearField,
            startYearField,
            endYearField,
            startMonthYearField,
            endMonthYearField
        ].filter(Boolean);

        function initYearPickers(scope) {
            if (window.YearPicker && typeof window.YearPicker.init === 'function') {
                window.YearPicker.init(scope || document);
            }
        }

        function setDefaultYearsIfEmpty() {
            const currentYear = String(new Date().getFullYear());
            yearFields.forEach(function(el) {
                if (!el) return;
                if (String(el.value || '').trim()) return;
                el.value = currentYear;
            });
            initYearPickers();
        }

        function bindYearFieldListeners(field) {
            if (!field) return;
            field.addEventListener('input', generatePeriodName);
            field.addEventListener('change', generatePeriodName);
        }

        // Function to show/hide period fields based on type
        function togglePeriodFields() {
            const periodType = periodTypeSelect.value;

            // Hide all period fields
            document.querySelectorAll('.period-fields').forEach(field => {
                field.classList.add('hidden');
            });

            // Show relevant fields
            if (periodType === 'single-year') {
                document.getElementById('single-year-fields').classList.remove('hidden');
            } else if (periodType === 'year-range') {
                document.getElementById('year-range-fields').classList.remove('hidden');
            } else if (periodType === 'month-range') {
                document.getElementById('month-range-fields').classList.remove('hidden');
            }

            setDefaultYearsIfEmpty();
            generatePeriodName();
        }

        // Function to generate period name based on current values
        function generatePeriodName() {
            const periodType = periodTypeSelect.value;
            let periodName = '';

            if (periodType === 'single-year') {
                const year = singleYearField.value;
                if (year) {
                    periodName = year;
                }
            } else if (periodType === 'year-range') {
                const startYear = startYearField.value;
                const endYear = endYearField.value;
                if (startYear && endYear) {
                    if (startYear === endYear) {
                        periodName = startYear;
                    } else {
                        periodName = `${startYear}-${endYear}`;
                    }
                } else if (startYear) {
                    periodName = startYear;
                }
            } else if (periodType === 'month-range') {
                const startYear = startMonthYearField.value;
                const startMonth = startMonthSelect.value;
                const endYear = endMonthYearField.value;
                const endMonth = endMonthSelect.value;

                if (startYear && startMonth && endYear && endMonth) {
                    const startMonthName = monthNames[startMonth];
                    const endMonthName = monthNames[endMonth];

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
            hiddenPeriodNameField.value = periodName || '';

            // Hide error message if period name is now valid
            const errorContainer = document.getElementById('period-name-error');
            if (periodName && errorContainer) {
                errorContainer.classList.add('hidden');
            }
        }

        // Function to parse existing period name and populate fields
        function parseExistingPeriodName(periodName) {
            if (!periodName) return;

            // Try to detect the format and populate fields accordingly
        const yearPattern = /^(\d{4})$/;
        const yearRangePattern = /^(\d{4})-(\d{4})$/;
        const monthPattern = /^([A-Za-z]{3})\s+(\d{4})$/;
        // "Jan 2024-Dec 2025" — different-year month range
        const monthRangePattern = /^([A-Za-z]{3})\s+(\d{4})-([A-Za-z]{3})\s+(\d{4})$/;
        // "Jan-Dec 2024" — same-year month range (generated by generatePeriodName)
        const sameYearMonthRangePattern = /^([A-Za-z]{3})-([A-Za-z]{3})\s+(\d{4})$/;

            if (yearPattern.test(periodName)) {
                // Single year: "2024"
                const match = periodName.match(yearPattern);
                periodTypeSelect.value = 'single-year';
                singleYearField.value = match[1];
            } else if (yearRangePattern.test(periodName)) {
                // Year range: "2024-2025"
                const match = periodName.match(yearRangePattern);
                periodTypeSelect.value = 'year-range';
                startYearField.value = match[1];
                endYearField.value = match[2];
            } else if (sameYearMonthRangePattern.test(periodName)) {
                // Same-year month range: "Jan-Dec 2024"
                const match = periodName.match(sameYearMonthRangePattern);
                periodTypeSelect.value = 'month-range';

                const monthToNumber = {
                    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
                    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
                    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
                };

                startMonthSelect.value = monthToNumber[match[1]];
                startMonthYearField.value = match[3];
                endMonthSelect.value = monthToNumber[match[2]];
                endMonthYearField.value = match[3];
            } else if (monthRangePattern.test(periodName)) {
                // Different-year month range: "Jan 2024-Dec 2025"
                const match = periodName.match(monthRangePattern);
                periodTypeSelect.value = 'month-range';

                const monthToNumber = {
                    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
                    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
                    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
                };

                startMonthSelect.value = monthToNumber[match[1]];
                startMonthYearField.value = match[2];
                endMonthSelect.value = monthToNumber[match[3]];
                endMonthYearField.value = match[4];
            } else if (monthPattern.test(periodName)) {
                // Single month: "Jan 2024"
                const match = periodName.match(monthPattern);
                periodTypeSelect.value = 'month-range';

                const monthToNumber = {
                    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
                    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
                    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
                };

                startMonthSelect.value = monthToNumber[match[1]];
                startMonthYearField.value = match[2];
                endMonthSelect.value = monthToNumber[match[1]];
                endMonthYearField.value = match[2];
            }

            togglePeriodFields();
        }

        // Event listeners
        periodTypeSelect.addEventListener('change', togglePeriodFields);
        yearFields.forEach(bindYearFieldListeners);
        startMonthSelect.addEventListener('change', generatePeriodName);
        endMonthSelect.addEventListener('change', generatePeriodName);

        // Remove required attribute from hidden period_name field to prevent browser validation
        // (we handle validation with JavaScript instead)
        if (hiddenPeriodNameField) {
            hiddenPeriodNameField.removeAttribute('required');
        }

        initYearPickers();

        // Initialize with existing period name if editing
        const existingPeriodName = cfg.periodName;
        if (existingPeriodName) {
            parseExistingPeriodName(existingPeriodName);
            initYearPickers();
        } else {
            setDefaultYearsIfEmpty();
            if (startMonthSelect) startMonthSelect.value = '01';
            if (endMonthSelect) endMonthSelect.value = '12';
            togglePeriodFields();
            generatePeriodName();
        }

        // --- Modal Handling ---
        const editStatusModal = document.getElementById('edit-status-modal');
        const editStatusActualForm = document.getElementById('edit-status-actual-form');
        const editStatusModalEntityNameSpan = document.getElementById('edit-status-modal-entity-name');
        const editStatusModalAesIdInput = document.getElementById('edit-status-modal-aes-id');
        const editStatusModalEntityTypeInput = document.getElementById('edit-status-modal-entity-type');
        const editStatusModalStatusSelect = document.getElementById('status');
        const editStatusModalDueDateInput = document.getElementById('due_date');

        const allModals = document.querySelectorAll('[role="dialog"]');
        const closeModalButtons = document.querySelectorAll('.close-modal');

        function openModal(modalElement) { if(modalElement) modalElement.classList.remove('hidden'); }
        function closeModal(modalElement) { if(modalElement) modalElement.classList.add('hidden'); }

        closeModalButtons.forEach(btn => btn.addEventListener('click', function() {
            closeModal(this.closest('[role="dialog"]'));
        }));
        window.addEventListener('click', e => {
            allModals.forEach(modal => { if (e.target === modal) closeModal(modal); });
        });

        // --- Edit Entity Status Button Click Handler (using event delegation) ---
        // Use event delegation so it works with AG Grid
        document.addEventListener('click', function(e) {
            // Check if the clicked element or its parent is an edit button
            const editButton = e.target.closest('.edit-entity-status-btn');
            if (editButton) {
                e.preventDefault();
                e.stopPropagation();

                const aesId = editButton.dataset.aesId;
                const entityName = editButton.dataset.entityName;
                const entityType = editButton.dataset.entityType;
                const currentStatus = editButton.dataset.currentStatus;
                const currentDueDate = editButton.dataset.currentDueDate;

                // Populate modal fields (single-entity mode)
                const bulkModeInput = document.getElementById('edit-status-modal-bulk-mode');
                if (bulkModeInput) bulkModeInput.value = '0';
                if(editStatusModalEntityNameSpan) editStatusModalEntityNameSpan.textContent = entityName;
                if(editStatusModalAesIdInput) editStatusModalAesIdInput.value = aesId;
                if(editStatusModalEntityTypeInput) editStatusModalEntityTypeInput.value = entityType || '';
                if(editStatusModalStatusSelect) editStatusModalStatusSelect.value = currentStatus;
                if(editStatusModalDueDateInput) editStatusModalDueDateInput.value = currentDueDate;

                // Set the form action URL dynamically - use entity status update endpoint
                if(editStatusActualForm) {
                    editStatusActualForm.action = cfg.urls.editEntityStatusBase + aesId;
                    editStatusActualForm.method = 'POST';
                }

                // Open the modal
                openModal(editStatusModal);
            }
        });

        // --- Edit Status Button Click Handler (legacy - for backward compatibility, using event delegation) ---
        document.addEventListener('click', function(e) {
            // Check if the clicked element or its parent is a legacy edit button
            const editButton = e.target.closest('.edit-status-btn');
            if (editButton) {
                e.preventDefault();
                e.stopPropagation();

                const aesId = editButton.dataset.aesId;
                const countryName = editButton.dataset.countryName;
                const currentStatus = editButton.dataset.currentStatus;
                const currentDueDate = editButton.dataset.currentDueDate;

                // Populate modal fields (single-entity mode)
                const bulkModeInputLegacy = document.getElementById('edit-status-modal-bulk-mode');
                if (bulkModeInputLegacy) bulkModeInputLegacy.value = '0';
                if(editStatusModalEntityNameSpan) editStatusModalEntityNameSpan.textContent = countryName;
                if(editStatusModalAesIdInput) editStatusModalAesIdInput.value = aesId;
                if(editStatusModalEntityTypeInput) editStatusModalEntityTypeInput.value = 'country';
                if(editStatusModalStatusSelect) editStatusModalStatusSelect.value = currentStatus;
                if(editStatusModalDueDateInput) editStatusModalDueDateInput.value = currentDueDate;

                // Set the form action URL dynamically
                if(editStatusActualForm) {
                    editStatusActualForm.action = cfg.urls.editEntityStatusBase + aesId;
                    editStatusActualForm.method = 'POST';
                }

                // Open the modal
                openModal(editStatusModal);
            }
        });

        // --- Initialize AG Grid for entity management (LAZY INITIALIZATION) ---
        window.__clientLog && window.__clientLog('[SETUP] Defining initializeEntityGrid function');
        let entityGridInitialized = false;
        let entityGridHelper = null;
        let entityGridApi = null;

        const entityManagementData = (function() {
            var el = document.getElementById('entity-management-data');
            if (!el) return [];
            try { return JSON.parse(el.textContent || '[]'); } catch(e) { return []; }
        })();

        const hasPublicColumn = cfg.hasPublicUrl;
        const statusChoices = cfg.statusChoices || [];

        function getStatusDisplayLabel(status) {
            const match = statusChoices.find(function(c) { return c.value === status; });
            if (match) return match.label;
            return String(status || '')
                .replace(/_/g, ' ')
                .trim()
                .replace(/\s+/g, ' ')
                .replace(/\b\w/g, function(chr) { return chr.toUpperCase(); });
        }

        function getStatusVariant(status) {
            const key = String(status || '').toLowerCase().replace(/\s+/g, '_');
            if (window.StatusLabels) {
                return window.StatusLabels.assignmentStatusVariant(key) !== 'neutral'
                    ? window.StatusLabels.assignmentStatusVariant(key)
                    : window.StatusLabels.genericStatusVariant(key);
            }
            return 'neutral';
        }

        function applyStatusChip(chipBtn, status) {
            if (!chipBtn) return;
            const variant = getStatusVariant(status);
            chipBtn.classList.remove('entity-status-chip--loading');
            chipBtn.removeAttribute('aria-busy');
            chipBtn.className = 'entity-status-chip status-label status-label--' + variant +
                ' inline-flex items-center gap-1 border-0';
            chipBtn.dataset.status = status || '';
            chipBtn.setAttribute('aria-label', 'Change status: ' + getStatusDisplayLabel(status));
            chipBtn.setAttribute('aria-haspopup', 'listbox');
            while (chipBtn.firstChild) chipBtn.removeChild(chipBtn.firstChild);
            const label = document.createElement('span');
            label.className = 'entity-status-chip-label';
            label.textContent = getStatusDisplayLabel(status);
            const caret = document.createElement('i');
            caret.className = 'fas fa-caret-down entity-status-chip-caret';
            caret.setAttribute('aria-hidden', 'true');
            chipBtn.appendChild(label);
            chipBtn.appendChild(caret);
        }

        function setStatusChipLoading(chipBtn) {
            if (!chipBtn) return;
            const status = chipBtn.dataset.status || '';
            const variant = getStatusVariant(status);
            chipBtn.disabled = true;
            chipBtn.classList.add('entity-status-chip--loading');
            chipBtn.setAttribute('aria-busy', 'true');
            chipBtn.setAttribute('aria-label', 'Saving status');
            chipBtn.removeAttribute('aria-haspopup');
            chipBtn.className = 'entity-status-chip status-label status-label--' + variant +
                ' inline-flex items-center justify-center gap-1 border-0';
            while (chipBtn.firstChild) chipBtn.removeChild(chipBtn.firstChild);
            const spinner = document.createElement('i');
            spinner.className = 'fas fa-spinner fa-spin entity-status-chip-spinner';
            spinner.setAttribute('aria-hidden', 'true');
            chipBtn.appendChild(spinner);
        }

        function buildStatusMenuPill(statusValue, labelText) {
            const variant = getStatusVariant(statusValue);
            const pill = document.createElement('span');
            pill.className = 'entity-status-menu-pill status-label status-label--' + variant;
            pill.textContent = labelText;
            return pill;
        }

        let entityStatusMenuEl = null;
        let entityStatusMenuAnchor = null;
        let entityStatusMenuRenderer = null;
        let entityStatusMenuListenersBound = false;

        function closeEntityStatusMenu() {
            if (entityStatusMenuEl) entityStatusMenuEl.classList.add('hidden');
            if (entityStatusMenuAnchor) entityStatusMenuAnchor.setAttribute('aria-expanded', 'false');
            entityStatusMenuAnchor = null;
            entityStatusMenuRenderer = null;
        }

        function ensureEntityStatusMenu() {
            if (entityStatusMenuEl) return entityStatusMenuEl;
            entityStatusMenuEl = document.createElement('div');
            entityStatusMenuEl.id = 'entity-status-menu';
            entityStatusMenuEl.className = 'entity-status-menu hidden';
            entityStatusMenuEl.setAttribute('role', 'listbox');
            document.body.appendChild(entityStatusMenuEl);

            if (!entityStatusMenuListenersBound) {
                entityStatusMenuListenersBound = true;
                document.addEventListener('click', function(e) {
                    if (!entityStatusMenuEl || entityStatusMenuEl.classList.contains('hidden')) return;
                    if (entityStatusMenuEl.contains(e.target)) return;
                    if (e.target.closest && e.target.closest('.entity-status-chip')) return;
                    closeEntityStatusMenu();
                });
                document.addEventListener('keydown', function(e) {
                    if (e.key === 'Escape') closeEntityStatusMenu();
                });
                window.addEventListener('resize', closeEntityStatusMenu);
                document.addEventListener('scroll', closeEntityStatusMenu, true);
            }
            return entityStatusMenuEl;
        }

        function positionEntityStatusMenu(anchorEl) {
            const menu = entityStatusMenuEl;
            if (!menu || !anchorEl) return;
            const rect = anchorEl.getBoundingClientRect();
            const gap = 4;
            let left = rect.left;
            menu.classList.remove('hidden');
            menu.style.left = left + 'px';
            menu.style.top = (rect.bottom + gap) + 'px';
            let menuRect = menu.getBoundingClientRect();
            if (menuRect.bottom > window.innerHeight - 8) {
                menu.style.top = Math.max(8, rect.top - menuRect.height - gap) + 'px';
                menuRect = menu.getBoundingClientRect();
            }
            if (menuRect.right > window.innerWidth - 8) {
                left = Math.max(8, window.innerWidth - menuRect.width - 8);
                menu.style.left = left + 'px';
            }
        }

        function openEntityStatusMenu(chipBtn, renderer, params) {
            if (entityStatusMenuAnchor === chipBtn && entityStatusMenuEl && !entityStatusMenuEl.classList.contains('hidden')) {
                closeEntityStatusMenu();
                return;
            }
            closeEntityStatusMenu();
            const menu = ensureEntityStatusMenu();
            while (menu.firstChild) menu.removeChild(menu.firstChild);

            const current = params.value || '';
            const choices = statusChoices.slice();
            if (current && !choices.some(function(c) { return c.value === current; })) {
                choices.unshift({ value: current, label: getStatusDisplayLabel(current) });
            }

            choices.forEach(function(choice) {
                const item = document.createElement('button');
                item.type = 'button';
                item.className = 'entity-status-menu-item';
                item.setAttribute('role', 'option');
                if (choice.value === current) item.setAttribute('aria-selected', 'true');
                item.appendChild(buildStatusMenuPill(choice.value, choice.label));
                item.addEventListener('click', function(e) {
                    e.stopPropagation();
                    closeEntityStatusMenu();
                    const newStatus = choice.value;
                    const oldStatus = (params.data && params.data.status) || params.value || '';
                    if (newStatus === oldStatus) return;
                    updateEntityStatusInline(params.data && params.data.id, newStatus, chipBtn, oldStatus, params, renderer);
                });
                menu.appendChild(item);
            });

            entityStatusMenuAnchor = chipBtn;
            entityStatusMenuRenderer = renderer;
            chipBtn.setAttribute('aria-expanded', 'true');
            positionEntityStatusMenu(chipBtn);
        }

        function updateEntityStatusInline(statusId, newStatus, chipBtn, previousStatus, params, renderer) {
            const url = cfg.urls && cfg.urls.assignmentBulkUpdateStatus;
            const numericId = Number(statusId);
            if (!url || !numericId) {
                applyStatusChip(chipBtn, previousStatus);
                return;
            }
            setStatusChipLoading(chipBtn);
            const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
            fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'X-CSRFToken': csrfToken || '',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({ status_ids: [numericId], status: newStatus })
            })
                .then(function(res) {
                    return res.json()
                        .then(function(data) { return { ok: res.ok, data: data }; })
                        .catch(function() {
                            return { ok: false, data: { error: res.status === 404 ? 'Not found.' : 'Invalid server response.' } };
                        });
                })
                .then(function(result) {
                    if (result.ok && result.data && result.data.success && result.data.updated > 0) {
                        if (params && params.data) params.data.status = newStatus;
                        if (renderer) {
                            renderer.params = params;
                            applyStatusChip(chipBtn, newStatus);
                        }
                    } else {
                        if (params && params.data) params.data.status = previousStatus;
                        if (renderer) applyStatusChip(chipBtn, previousStatus);
                        var m = (result.data && (result.data.error || result.data.message)) ||
                            (result.data && result.data.updated === 0 ? 'Entity assignment not found.' : null) ||
                            'Failed to update status.';
                        if (window.showAlert) window.showAlert(m, 'error');
                    }
                })
                .catch(function() {
                    if (params && params.data) params.data.status = previousStatus;
                    if (renderer) applyStatusChip(chipBtn, previousStatus);
                    if (window.showAlert) window.showAlert('Request failed.', 'error');
                })
                .finally(function() {
                    chipBtn.disabled = false;
                });
        }

        function StatusDropdownCellRenderer() {}
        StatusDropdownCellRenderer.prototype.init = function(params) {
            const self = this;
            const chipBtn = document.createElement('button');
            chipBtn.type = 'button';
            applyStatusChip(chipBtn, params.value || '');

            const stopGrid = function(e) { e.stopPropagation(); };
            chipBtn.addEventListener('click', function(e) {
                stopGrid(e);
                if (chipBtn.disabled) return;
                openEntityStatusMenu(chipBtn, self, params);
            });
            chipBtn.addEventListener('mousedown', stopGrid);

            this.eGui = chipBtn;
            this.chipBtn = chipBtn;
            this.params = params;
        };
        StatusDropdownCellRenderer.prototype.getGui = function() { return this.eGui; };
        StatusDropdownCellRenderer.prototype.refresh = function(params) {
            this.params = params;
            applyStatusChip(this.chipBtn, params.value || '');
            if (entityStatusMenuAnchor === this.chipBtn) closeEntityStatusMenu();
            return true;
        };
        StatusDropdownCellRenderer.prototype.destroy = function() {
            if (entityStatusMenuAnchor === this.chipBtn) closeEntityStatusMenu();
        };

        // Helper function to render public reporting badge
        function renderPublicBadge(isAvailable) {
            if (isAvailable) {
                return window.StatusLabels
                    ? window.StatusLabels.render('Available', 'success')
                    : '<span class="status-label status-label--success">Available</span>';
            } else {
                return window.StatusLabels
                    ? window.StatusLabels.render('Not Available', 'neutral')
                    : '<span class="status-label status-label--neutral">Not Available</span>';
            }
        }

        // Column definitions for ag-grid (ag-grid adds its own checkbox column when rowSelection is used; do not add a second one)
        const entityColumnDefs = [
            {
                field: 'entity_type_label',
                headerName: 'Entity Type',
                width: 150,
                minWidth: 120,
                maxWidth: 200,
                hide: true,
                filter: 'customSetFilter',
                sortable: true,
                cellRenderer: function(params) {
                    return '<span class="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-blue-100 text-blue-800">' + (params.value || '') + '</span>';
                }
            },
            {
                field: 'entity_name',
                headerName: 'Entity Name',
                width: 300,
                minWidth: 200,
                maxWidth: 500,
                filter: 'agTextColumnFilter',
                sortable: true,
                cellRenderer: AgGridRenderers.link('assignment_url')
            },
            {
                field: 'fds_member_name',
                headerName: 'FDS Member',
                width: 220,
                minWidth: 180,
                maxWidth: 300,
                filter: 'agTextColumnFilter',
                sortable: true,
                cellStyle: AgGridRenderers.userHoverCellStyle,
                valueGetter: function(params) {
                    return params.data && params.data.fds_member_name ? params.data.fds_member_name : '';
                },
                cellRenderer: function(params) {
                    if (!params.data || !params.data.fds_member_user_id) {
                        return '<span class="text-gray-400">-</span>';
                    }
                    if (typeof AgGridRenderers !== 'undefined' && AgGridRenderers.userHoverCell) {
                        return AgGridRenderers.userHoverCell(params, {
                            idField: 'fds_member_user_id',
                            nameField: 'fds_member_name',
                            emailField: 'fds_member_email',
                            activeField: 'fds_member_active',
                            profileColorField: 'fds_member_profile_color',
                            fallbackLabel: 'Unknown User',
                            showEmail: true
                        });
                    }
                    return params.data.fds_member_name || '-';
                }
            },
            {
                field: 'status',
                headerName: 'Assignment Status',
                width: 200,
                minWidth: 170,
                maxWidth: 280,
                filter: 'customSetFilter',
                sortable: true,
                cellRenderer: StatusDropdownCellRenderer,
                valueFormatter: function(params) {
                    const match = statusChoices.find(function(c) { return c.value === params.value; });
                    if (match) return match.label;
                    return String(params.value || '').replace(/_/g, ' ').replace(/\b\w/g, function(chr) { return chr.toUpperCase(); });
                },
                filterValueGetter: function(params) {
                    const match = statusChoices.find(function(c) { return c.value === params.data.status; });
                    return match ? match.label : params.data.status;
                }
            },
            {
                field: 'completion_rate',
                headerName: (cfg.t && cfg.t.completionRate) || 'Completion Rate',
                width: 150,
                minWidth: 120,
                maxWidth: 180,
                filter: 'agNumberColumnFilter',
                sortable: true,
                type: 'numericColumn',
                valueGetter: function(params) {
                    var rate = params.data && params.data.completion_rate;
                    return rate == null || rate === '' ? 0 : Number(rate);
                },
                valueFormatter: function(params) {
                    var num = Number(params.value);
                    if (!isFinite(num)) return '';
                    return num.toFixed(1) + '%';
                },
                cellRenderer: function(params) {
                    var num = Number(params.value);
                    if (!isFinite(num)) {
                        return '<span class="text-gray-400">—</span>';
                    }
                    // Color tiers match dashboard / entry-form completion rate.
                    var cls = 'text-red-600 font-semibold';
                    if (num >= 80) cls = 'text-green-700 font-semibold';
                    else if (num >= 25) cls = 'text-amber-600 font-semibold';
                    return '<span class="tabular-nums ' + cls + '">' + num.toFixed(1) + '%</span>';
                }
            },
            {
                field: 'due_date',
                headerName: 'Due Date',
                width: 150,
                minWidth: 120,
                maxWidth: 200,
                filter: 'agDateColumnFilter',
                filterParams: AgGridRenderers.dateFilterParams,
                sortable: true,
                cellRenderer: function(params) {
                    if (!params.value) return '<span class="text-gray-400 italic">Not set</span>';
                    try {
                        const d = new Date(params.value);
                        if (isNaN(d.getTime())) return params.value;
                        return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
                    } catch(e) { return params.value; }
                }
            }
        ].concat(cfg.hasPublicUrl ? [{
                field: 'is_public_available',
                headerName: 'Public Reporting',
                width: 180,
                minWidth: 150,
                maxWidth: 250,
                filter: 'customSetFilter',
                sortable: true,
                cellRenderer: function(params) {
                    return renderPublicBadge(params.value);
                }
            }] : []
        );

        function scheduleEntityGridInit() {
            if (entityGridInitialized) {
                return;
            }
            if (typeof AgGridHelper !== 'undefined' && AgGridHelper.showGridLoadingOverlay) {
                AgGridHelper.showGridLoadingOverlay('entityManagementGrid-loading');
            }
            var containerEl = document.getElementById('entityManagementGrid-container');
            if (containerEl) {
                containerEl.style.display = 'none';
            }
            requestAnimationFrame(function() {
                requestAnimationFrame(function() {
                    if (typeof initializeEntityGrid === 'function') {
                        initializeEntityGrid();
                    }
                });
            });
        }

        function initializeEntityGrid() {
            window.__clientLog && window.__clientLog('[INIT-FUNC] initializeEntityGrid function called');
            if (entityGridInitialized) {
                window.__clientLog && window.__clientLog('[INIT] Already initialized, returning');
                return;
            }

            const gridContainer = document.getElementById('entityManagementGrid');
            if (!gridContainer) {
                window.__clientLog && window.__clientLog('[INIT] Grid container not found');
                return;
            }

            window.__clientLog && window.__clientLog('[INIT] Initializing AG Grid for entity management');

            entityGridHelper = new AgGridHelper({
                containerId: 'entityManagementGrid',
                templateId: 'entity-management-v2',
                columnDefs: entityColumnDefs,
                rowData: entityManagementData,
                options: {
                    onSelectionChanged: function() {
                        const bulkBar = document.getElementById('entity-grid-bulk-actions');
                        const countEl = document.getElementById('entity-grid-selected-count');
                        const api = window.entityGridApi;
                        const selected = api ? (api.getSelectedRows && api.getSelectedRows()) : [];
                        if (bulkBar && countEl) {
                            if (selected && selected.length > 0) {
                                bulkBar.classList.remove('hidden');
                                bulkBar.classList.add('flex');
                                countEl.textContent = selected.length + ' selected';
                            } else {
                                bulkBar.classList.add('hidden');
                                bulkBar.classList.remove('flex');
                                countEl.textContent = '0 selected';
                            }
                        }
                    }
                },
                columnVisibilityOptions: {
                    enableExport: false,
                    enableReset: true
                }
            });

            entityGridApi = entityGridHelper.initialize();
            window.entityGridApi = entityGridApi;
            window.entityGridHelper = entityGridHelper;

            entityGridInitialized = true;
            window.__clientLog && window.__clientLog('[INIT] Entity management grid initialized');
        }

        // --- Bulk actions for entity grid selection ---
        function getEntityGridSelectedIds() {
            const api = window.entityGridApi;
            if (!api || typeof api.getSelectedRows !== 'function') return [];
            const rows = api.getSelectedRows();
            return (rows || []).map(function(r) { return r.id; }).filter(Boolean);
        }

        document.getElementById('entity-grid-bulk-delete-btn')?.addEventListener('click', function() {
            const ids = getEntityGridSelectedIds();
            if (ids.length === 0) return;
            const msg = 'Are you sure you want to remove ' + ids.length + ' selected entit' + (ids.length === 1 ? 'y' : 'ies') + ' from this assignment? This will delete their data.';
            function doRemove() {
                const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
                fetch(cfg.urls.assignmentBulkRemove, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken || '' },
                    body: JSON.stringify({ status_ids: ids })
                }).then(function(res) {
                    return window.responseAsResult(res);
                })
                  .then(function(result) {
                      if (result.ok && result.data.success) { window.location.reload(); }
                      else {
                        var m = result.data.error || 'Failed to remove entities.';
                        if (window.showAlert) window.showAlert(m, 'error');
                      }
                  })
                  .catch(function() {
                    if (window.showAlert) window.showAlert('Request failed.', 'error');
                  });
            }
            if (window.showConfirmation) {
                window.showConfirmation(msg, doRemove, function() {}, cfg.t.remove, cfg.t.cancel, cfg.t.removeEntities);
            } else {
                if (window.confirm(msg)) doRemove();
            }
        });

        // Bulk enable/disable public reporting for selected entities
        function bulkUpdatePublicAvailability(enable) {
            const ids = getEntityGridSelectedIds();
            if (ids.length === 0) return;
            const action = enable ? 'enable' : 'disable';
            const msg = 'Are you sure you want to ' + action + ' public reporting for ' + ids.length + ' selected entit' + (ids.length === 1 ? 'y' : 'ies') + '?';
            function doUpdate() {
                const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
                fetch(cfg.urls.assignmentBulkUpdatePublic, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken || '' },
                    body: JSON.stringify({ status_ids: ids, enable: enable })
                }).then(function(res) {
                    return window.responseAsResult(res);
                })
                  .then(function(result) {
                      if (result.ok && result.data.success) {
                          if (typeof Utils !== 'undefined' && Utils.showSuccess) Utils.showSuccess(result.data.message);
                          window.location.reload();
                      } else {
                          var m = result.data.error || result.data.message || 'Failed to update public reporting.';
                          if (window.showAlert) window.showAlert(m, 'error');
                      }
                  })
                  .catch(function() {
                    if (window.showAlert) window.showAlert('Request failed.', 'error');
                  });
            }
            if (window.showConfirmation) {
                window.showConfirmation(msg, doUpdate, function() {}, cfg.t.confirm, cfg.t.cancel, cfg.t.publicReporting);
            } else {
                doUpdate();
            }
        }
        document.getElementById('entity-grid-bulk-public-enable-btn')?.addEventListener('click', function() { bulkUpdatePublicAvailability(true); });
        document.getElementById('entity-grid-bulk-public-disable-btn')?.addEventListener('click', function() { bulkUpdatePublicAvailability(false); });

        // "Change status" opens the bulk-status-modal (status only)
        const bulkStatusModal = document.getElementById('bulk-status-modal');
        document.getElementById('entity-grid-bulk-status-btn')?.addEventListener('click', function() {
            const ids = getEntityGridSelectedIds();
            if (ids.length === 0) return;
            const select = document.getElementById('bulk-status-select');
            if (select) select.value = '';
            openModal(bulkStatusModal);
        });

        // Bulk status form submit
        document.getElementById('bulk-status-form')?.addEventListener('submit', function(e) {
            e.preventDefault();
            const form = e.currentTarget;
            if (form && form.dataset.submitting === '1') return;
            const ids = getEntityGridSelectedIds();
            const status = document.getElementById('bulk-status-select')?.value;
            if (ids.length === 0 || !status) {
                if (!status) {
                    if (window.showAlert) window.showAlert('Please select a status.', 'warning');
                }
                return;
            }
            const submitBtn = form ? form.querySelector('[type="submit"]') : null;
            if (form) form.dataset.submitting = '1';
            if (submitBtn) submitBtn.disabled = true;
            const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
            fetch(cfg.urls.assignmentBulkUpdateStatus, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken || '' },
                body: JSON.stringify({ status_ids: ids, status: status })
            }).then(function(res) {
                return window.responseAsResult(res);
            })
              .then(function(result) {
                  if (result.ok && result.data.success) { closeModal(bulkStatusModal); window.location.reload(); }
                  else {
                    if (form) form.dataset.submitting = '0';
                    if (submitBtn) submitBtn.disabled = false;
                    var m = result.data.error || 'Failed to update status.';
                    if (window.showAlert) window.showAlert(m, 'error');
                  }
              })
              .catch(function() {
                if (form) form.dataset.submitting = '0';
                if (submitBtn) submitBtn.disabled = false;
                if (window.showAlert) window.showAlert('Request failed.', 'error'); else window.__clientWarn && window.__clientWarn('Request failed.');
              });
        });

        // "Change due date" opens the bulk-duedate-selected-modal
        const bulkDuedateSelectedModal = document.getElementById('bulk-duedate-selected-modal');
        document.getElementById('entity-grid-bulk-duedate-btn')?.addEventListener('click', function() {
            const ids = getEntityGridSelectedIds();
            if (ids.length === 0) return;
            const input = document.getElementById('bulk-duedate-selected-input');
            if (input) input.value = '';
            openModal(bulkDuedateSelectedModal);
        });

        // Bulk due date form submit
        document.getElementById('bulk-duedate-selected-form')?.addEventListener('submit', function(e) {
            e.preventDefault();
            const form = e.currentTarget;
            if (form && form.dataset.submitting === '1') return;
            const ids = getEntityGridSelectedIds();
            const dueDate = document.getElementById('bulk-duedate-selected-input')?.value;
            if (ids.length === 0 || !dueDate) {
                if (!dueDate) {
                    if (window.showAlert) window.showAlert('Please select a date.', 'warning');
                }
                return;
            }
            const submitBtn = form ? form.querySelector('[type="submit"]') : null;
            if (form) form.dataset.submitting = '1';
            if (submitBtn) submitBtn.disabled = true;
            const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
            fetch(cfg.urls.assignmentBulkUpdateDueDate, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken || '' },
                body: JSON.stringify({ status_ids: ids, due_date: dueDate })
            }).then(function(res) {
                return window.responseAsResult(res);
            })
              .then(function(result) {
                  if (result.ok && result.data.success) { closeModal(bulkDuedateSelectedModal); window.location.reload(); }
                  else {
                    if (form) form.dataset.submitting = '0';
                    if (submitBtn) submitBtn.disabled = false;
                    var m = result.data.error || 'Failed to update due date.';
                    if (window.showAlert) window.showAlert(m, 'error');
                  }
              })
              .catch(function() {
                if (form) form.dataset.submitting = '0';
                if (submitBtn) submitBtn.disabled = false;
                if (window.showAlert) window.showAlert('Request failed.', 'error'); else window.__clientWarn && window.__clientWarn('Request failed.');
              });
        });

        // Initialize Select2 for the status dropdown within the modal
        if (typeof $ !== 'undefined' && $.fn.select2) {
             $('#status').select2({
                 dropdownParent: $('#edit-status-modal'),
                 width: '100%',
                 theme: "default",
                 minimumResultsForSearch: -1
             });
         } else {
             window.__clientWarn && window.__clientWarn("jQuery or Select2 is not loaded. Select2 functionality for status dropdown will be unavailable.");
         }

        // --- Copy Public URL Functionality ---
        const copyPublicUrlBtn = document.getElementById('copy-public-url-btn');
        if (copyPublicUrlBtn) {
            copyPublicUrlBtn.addEventListener('click', function() {
                const url = this.getAttribute('data-url');
                navigator.clipboard.writeText(url).then(function() {
                    // Show success feedback
                    const originalText = copyPublicUrlBtn.innerHTML;
                    copyPublicUrlBtn.innerHTML = '<i class="fas fa-check mr-1"></i> Copied!';
                    copyPublicUrlBtn.classList.remove('bg-blue-600', 'hover:bg-blue-700');
                    copyPublicUrlBtn.classList.add('bg-green-600');

                    setTimeout(function() {
                        copyPublicUrlBtn.innerHTML = originalText;
                        copyPublicUrlBtn.classList.remove('bg-green-600');
                        copyPublicUrlBtn.classList.add('bg-blue-600', 'hover:bg-blue-700');
                    }, 2000);
                }).catch(function(err) {
                    if (window.showAlert) window.showAlert('Failed to copy URL. Please try again.', 'error');
                    else if (typeof Utils !== 'undefined' && Utils.showError) Utils.showError('Failed to copy URL. Please try again.');
                });
            });
        }

        // --- Public URL Options for New Assignments ---
        const generatePublicUrlCheckbox = document.getElementById('generate_public_url');
        const publicUrlActiveContainer = document.getElementById('public-url-active-container');

        if (generatePublicUrlCheckbox && publicUrlActiveContainer) {
            function togglePublicUrlActive() {
                publicUrlActiveContainer.classList.toggle('hidden', !generatePublicUrlCheckbox.checked);
            }

            // Initial state
            togglePublicUrlActive();

            // Listen for changes
            generatePublicUrlCheckbox.addEventListener('change', togglePublicUrlActive);
        }

        // --- Toggle Public Access (avoid nested form submission) ---
        const togglePublicAccessBtn = document.getElementById('toggle-public-access-btn');
        if (togglePublicAccessBtn) {
            togglePublicAccessBtn.addEventListener('click', function() {
                const form = document.createElement('form');
                form.method = 'POST';
                form.action = cfg.urls.assignmentTogglePublicAccess;

                const csrfInput = document.createElement('input');
                csrfInput.type = 'hidden';
                csrfInput.name = 'csrf_token';
                const csrfField = document.querySelector('input[name="csrf_token"]');
                csrfInput.value = csrfField ? csrfField.value : '';
                form.appendChild(csrfInput);

                const nextInput = document.createElement('input');
                nextInput.type = 'hidden';
                nextInput.name = 'next';
                nextInput.value = window.location.href;
                form.appendChild(nextInput);

                document.body.appendChild(form);
                HTMLFormElement.prototype.submit.call(form);
            });
        }

        // --- Generate Public URL (avoid nested form submission) ---
        const generatePublicUrlBtn = document.getElementById('generate-public-url-btn');
        if (generatePublicUrlBtn) {
            generatePublicUrlBtn.addEventListener('click', function() {
                const form = document.createElement('form');
                form.method = 'POST';
                form.action = this.dataset.action;

                const csrfInput = document.createElement('input');
                csrfInput.type = 'hidden';
                csrfInput.name = 'csrf_token';
                const csrfField = document.querySelector('input[name="csrf_token"]');
                csrfInput.value = csrfField ? csrfField.value : '';
                form.appendChild(csrfInput);

                const nextInput = document.createElement('input');
                nextInput.type = 'hidden';
                nextInput.name = 'next';
                nextInput.value = this.dataset.next;
                form.appendChild(nextInput);

                document.body.appendChild(form);
                HTMLFormElement.prototype.submit.call(form);
            });
        }


        // Initialize tab switching functionality for Entity Assignments
        let entityTabButtons = null;
        let entityTabPanels = null;

        function getEntityTabElements() {
            // Re-query elements each time to ensure we get them even if section was initially hidden
            entityTabButtons = document.querySelectorAll('#assignment-main-tabs button[role="tab"]');

            // Use ID-based lookup as primary method since it's more reliable
            // This ensures we find panels even if they're conditionally rendered or nested
            const foundPanels = [];
            entityTabButtons.forEach(btn => {
                const targetPanelId = btn.getAttribute('data-tabs-target');
                if (targetPanelId) {
                    const panelId = targetPanelId.replace('#', '');
                    const panel = document.getElementById(panelId);
                    if (panel) {
                        foundPanels.push(panel);
                    }
                }
            });

            // Fallback to querySelectorAll if ID-based lookup didn't find all panels
            if (foundPanels.length < entityTabButtons.length) {
                const queryPanels = document.querySelectorAll('#assignment-main-tabs-content > [role="tabpanel"]');
                // Merge any panels found by query that weren't found by ID
                queryPanels.forEach(panel => {
                    if (!foundPanels.includes(panel)) {
                        foundPanels.push(panel);
                    }
                });
            }

            entityTabPanels = foundPanels;

            // Only log warnings if there's a mismatch after all attempts
            if (entityTabPanels.length < entityTabButtons.length) {
                window.__clientWarn && window.__clientWarn('[DEBUG] getEntityTabElements: Mismatch detected - Found', entityTabPanels.length, 'panels but', entityTabButtons.length, 'buttons');
            }

            window.__clientLog && window.__clientLog('[DEBUG] getEntityTabElements: Found', entityTabButtons.length, 'buttons and', entityTabPanels.length, 'panels');
            if (entityTabButtons.length > 0) {
                window.__clientLog && window.__clientLog('[DEBUG] Tab buttons:', Array.from(entityTabButtons).map(btn => ({
                    id: btn.id,
                    target: btn.getAttribute('data-tabs-target'),
                    text: btn.textContent.trim()
                })));
            }
            if (entityTabPanels.length > 0) {
                window.__clientLog && window.__clientLog('[DEBUG] Tab panels:', Array.from(entityTabPanels).map(panel => ({
                    id: panel.id,
                    hidden: panel.classList.contains('hidden'),
                    display: window.getComputedStyle(panel).display
                })));
            } else if (entityTabButtons.length > 0) {
                window.__clientWarn && window.__clientWarn('[DEBUG] getEntityTabElements: NO PANELS FOUND! Checking DOM structure...');
                const tabsContent = document.getElementById('assignment-main-tabs-content');
                if (tabsContent) {
                    window.__clientLog && window.__clientLog('[DEBUG] assignment-main-tabs-content exists, children:', tabsContent.children.length);
                    window.__clientLog && window.__clientLog('[DEBUG] assignment-main-tabs-content HTML:', tabsContent.innerHTML.substring(0, 500));
                } else {
                    window.__clientWarn && window.__clientWarn('[DEBUG] assignment-main-tabs-content does not exist!');
                }
            }
        }

        // Load category filters only when a panel that uses them becomes visible
        // (Add Entities → Countries, or Manage Existing Entities) — not on every page load.
        //
        // Defined here (before activateEntityTab / activateAddEntitiesSubTab, and before
        // page-load tab restoration runs below) so those functions can call it directly
        // when the relevant panel actually becomes visible — via click OR via
        // localStorage-restored state (e.g. expanding a collapsed section that then
        // auto-selects "Manage Existing Entities" or "Countries" without ever firing a
        // button `click` event, which a click-listener-only approach would miss).
        // `loadCategoriesAndMapping` is a hoisted function declaration (defined further
        // below in this scope), so calling it here ahead of its textual definition is safe.
        // Category state must be declared here too — page-load tab restoration can call
        // loadCategoriesOnce → bootstrapPartOfCategoriesFromConfig before later lines run.
        let availableCategories = [];
        let categoryToCountriesMap = {}; // Maps category name to array of country IDs
        let categoriesLoaded = false;
        function loadCategoriesOnce() {
            if (categoriesLoaded) return;
            categoriesLoaded = true;
            if (typeof bootstrapPartOfCategoriesFromConfig === 'function' && bootstrapPartOfCategoriesFromConfig()) {
                return;
            }
            loadCategoriesAndMapping();
        }

        function loadCategoriesForAssignCountriesIfPresent() {
            if (document.getElementById('category-filters-entity')) {
                loadCategoriesOnce();
            }
        }

        function onEntityTabPanelShown(panel) {
            if (!panel) return;
            if (panel.id === 'manage-entities-panel') {
                loadCategoriesOnce();
                scheduleEntityGridInit();
            } else if (panel.id === 'add-entities-panel') {
                setTimeout(initializeAddEntitiesSubTabs, 50);
                // Countries-only layout has no sub-tab nav; initializeAddEntitiesSubTabs
                // returns early and would never load Part of filters otherwise.
                loadCategoriesForAssignCountriesIfPresent();
            }
        }

        function activateEntityTab(tabId) {
            window.__clientLog && window.__clientLog('[DEBUG] activateEntityTab called with tabId:', tabId);
            if (!tabId) {
                window.__clientWarn && window.__clientWarn('[DEBUG] activateEntityTab: No tabId provided!');
                return;
            }

            // Ensure we have fresh references to elements
            getEntityTabElements();

            // Update tab buttons
            if (entityTabButtons) {
                window.__clientLog && window.__clientLog('[DEBUG] activateEntityTab: Updating', entityTabButtons.length, 'tab buttons');
                entityTabButtons.forEach(btn => {
                    const targetPanelId = btn.getAttribute('data-tabs-target');
                    // Remove # prefix for comparison
                    const panelId = targetPanelId ? targetPanelId.replace('#', '') : '';
                    const isActive = panelId === tabId;
                    window.__clientLog && window.__clientLog('[DEBUG] activateEntityTab: Button', btn.id, 'targets panel', panelId, 'comparing with', tabId);
                    if (window.AdminUnderlineTabs) {
                        window.AdminUnderlineTabs.setStripButtonActive(btn, isActive);
                    } else if (isActive) {
                        btn.classList.add('text-blue-600', 'border-blue-500');
                        btn.classList.remove('border-transparent', 'text-gray-500');
                    } else {
                        btn.classList.remove('text-blue-600', 'border-blue-500');
                        btn.classList.add('border-transparent', 'text-gray-500');
                    }
                    btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
                    if (isActive) {
                        window.__clientLog && window.__clientLog('[DEBUG] activateEntityTab: Activated button', btn.id);
                    }
                });
            } else {
                window.__clientWarn && window.__clientWarn('[DEBUG] activateEntityTab: No tab buttons found!');
            }

            // Use panels already found by getEntityTabElements()
            // If not available, fallback to direct lookup
            let allPanels = entityTabPanels && entityTabPanels.length > 0
                ? Array.from(entityTabPanels)
                : [];

            // Fallback: if panels weren't found, try direct ID lookup
            if (allPanels.length === 0 && entityTabButtons) {
                entityTabButtons.forEach(btn => {
                    const targetPanelId = btn.getAttribute('data-tabs-target');
                    if (targetPanelId) {
                        const panelId = targetPanelId.replace('#', '');
                        const panel = document.getElementById(panelId);
                        if (panel && !allPanels.includes(panel)) {
                            allPanels.push(panel);
                        }
                    }
                });
            }

            window.__clientLog && window.__clientLog('[DEBUG] activateEntityTab: Found', allPanels.length, 'panels to update');

            let targetPanelFound = false;
            allPanels.forEach(panel => {
                const beforeHidden = panel.classList.contains('hidden');
                const beforeDisplay = window.getComputedStyle(panel).display;
                window.__clientLog && window.__clientLog('[DEBUG] activateEntityTab: Panel', panel.id, 'before - hidden:', beforeHidden, 'display:', beforeDisplay);

                if (panel.id === tabId) {
                    // Remove hidden class and explicitly show the panel
                    panel.classList.remove('hidden');
                    // Use block display to ensure visibility (Tailwind's hidden uses display: none)
                    panel.style.display = 'block';
                    targetPanelFound = true;
                    const afterHidden = panel.classList.contains('hidden');
                    const afterDisplay = window.getComputedStyle(panel).display;
                    window.__clientLog && window.__clientLog('[DEBUG] activateEntityTab: SHOWING panel', panel.id, 'after - hidden:', afterHidden, 'display:', afterDisplay);

                    onEntityTabPanelShown(panel);
                } else {
                    // Add hidden class and explicitly hide
                    panel.classList.add('hidden');
                    panel.style.display = 'none';
                    const afterHidden = panel.classList.contains('hidden');
                    const afterDisplay = window.getComputedStyle(panel).display;
                    window.__clientLog && window.__clientLog('[DEBUG] activateEntityTab: HIDING panel', panel.id, 'after - hidden:', afterHidden, 'display:', afterDisplay);
                }
            });

            // If still not found, try finding the target panel directly by ID
            if (!targetPanelFound) {
                window.__clientWarn && window.__clientWarn('[DEBUG] activateEntityTab: Target panel not found in query results, trying direct ID lookup...');
                const targetPanel = document.getElementById(tabId);
                if (targetPanel) {
                    window.__clientLog && window.__clientLog('[DEBUG] activateEntityTab: Found target panel by direct ID lookup!', tabId);
                    targetPanel.classList.remove('hidden');
                    targetPanel.style.display = 'block';
                    targetPanelFound = true;
                    onEntityTabPanelShown(targetPanel);

                    // Hide all other panels
                    allPanels.forEach(panel => {
                        if (panel.id !== tabId) {
                            panel.classList.add('hidden');
                            panel.style.display = 'none';
                        }
                    });
                } else {
                    window.__clientWarn && window.__clientWarn('[DEBUG] activateEntityTab: Target panel with id', tabId, 'NOT FOUND even with direct ID lookup!');
                    window.__clientLog && window.__clientLog('[DEBUG] Available panel IDs from query:', Array.from(allPanels).map(p => p.id));
                    // Check what panels actually exist in the DOM
                    const allDivsInContent = document.querySelectorAll('#assignment-main-tabs-content > [role="tabpanel"]');
                    window.__clientLog && window.__clientLog('[DEBUG] All tabpanels in assignment-main-tabs-content:', Array.from(allDivsInContent).map(d => ({
                        id: d.id,
                        role: d.getAttribute('role'),
                        classes: d.className
                    })));
                }
            }

            // Store selected tab in localStorage
            localStorage.setItem('selectedAssignmentMainTab', tabId);
            window.__clientLog && window.__clientLog('[DEBUG] activateEntityTab: Completed for tabId', tabId);
        }

        // Function to attach click handlers to tab buttons
        function attachTabHandlers() {
            window.__clientLog && window.__clientLog('[DEBUG] attachTabHandlers: Starting');
            getEntityTabElements();
            if (entityTabButtons) {
                window.__clientLog && window.__clientLog('[DEBUG] attachTabHandlers: Processing', entityTabButtons.length, 'buttons');
                entityTabButtons.forEach((btn, index) => {
                    // Check if handler already attached (using data attribute)
                    if (btn.dataset.tabHandlerAttached === 'true') {
                        window.__clientLog && window.__clientLog('[DEBUG] attachTabHandlers: Button', btn.id, 'already has handler, skipping');
                        return; // Skip if already attached
                    }

                    // Mark as attached
                    btn.dataset.tabHandlerAttached = 'true';
                    window.__clientLog && window.__clientLog('[DEBUG] attachTabHandlers: Attaching handler to button', btn.id, 'at index', index);

                    // Attach click handler
                    btn.addEventListener('click', function(e) {
                        window.__clientLog && window.__clientLog('[DEBUG] Tab button clicked!', this.id);
                        window.__clientLog && window.__clientLog('[DEBUG] Event target:', e.target);
                        window.__clientLog && window.__clientLog('[DEBUG] Event currentTarget:', e.currentTarget);
                        e.preventDefault();
                        e.stopPropagation();
                        const targetPanelId = this.getAttribute('data-tabs-target');
                        window.__clientLog && window.__clientLog('[DEBUG] Click handler: targetPanelId from attribute:', targetPanelId);
                        if (targetPanelId) {
                            // Remove # prefix
                            const panelId = targetPanelId.replace('#', '');
                            window.__clientLog && window.__clientLog('[DEBUG] Click handler: Calling activateEntityTab with panelId:', panelId);
                            activateEntityTab(panelId);
                        } else {
                            window.__clientWarn && window.__clientWarn('[DEBUG] Click handler: No data-tabs-target attribute found on button', this.id);
                        }
                    });
                    window.__clientLog && window.__clientLog('[DEBUG] attachTabHandlers: Handler attached to button', btn.id);
                });
                window.__clientLog && window.__clientLog('[DEBUG] attachTabHandlers: Completed, attached handlers to', entityTabButtons.length, 'buttons');
            } else {
                window.__clientWarn && window.__clientWarn('[DEBUG] attachTabHandlers: No tab buttons found!');
            }
        }

        // Attach handlers initially and when section expands
        attachTabHandlers();

        // Handle sub-tabs within "Add entities" panel
        function initializeAddEntitiesSubTabs() {
            const addEntitiesSubTabButtons = document.querySelectorAll('#add-entities-subtabs button[role="tab"]');
            const addEntitiesSubTabPanels = document.querySelectorAll('#add-entities-subtabs-content > div[role="tabpanel"]');

            if (addEntitiesSubTabButtons.length === 0) {
                loadCategoriesForAssignCountriesIfPresent();
                return;
            }

            function activateAddEntitiesSubTab(panelId) {
                // Update buttons
                addEntitiesSubTabButtons.forEach(btn => {
                    const targetPanelId = btn.getAttribute('data-tabs-target');
                    const btnPanelId = targetPanelId ? targetPanelId.replace('#', '') : '';
                    if (btnPanelId === panelId) {
                        btn.classList.add('text-blue-600', 'border-blue-600');
                        btn.classList.remove('border-transparent', 'hover:text-gray-600', 'hover:border-gray-300');
                        btn.setAttribute('aria-selected', 'true');
                    } else {
                        btn.classList.remove('text-blue-600', 'border-blue-600');
                        btn.classList.add('border-transparent', 'hover:text-gray-600', 'hover:border-gray-300');
                        btn.setAttribute('aria-selected', 'false');
                    }
                });

                // Update panels
                addEntitiesSubTabPanels.forEach(panel => {
                    if (panel.id === panelId) {
                        panel.classList.remove('hidden');
                        panel.style.display = 'block';
                        if (panelId === 'add-entities-countries-panel') {
                            loadCategoriesOnce();
                        }
                    } else {
                        panel.classList.add('hidden');
                        panel.style.display = 'none';
                    }
                });
            }

            // Attach click handlers
            addEntitiesSubTabButtons.forEach(btn => {
                if (btn.dataset.addEntitiesSubTabHandlerAttached === 'true') return;
                btn.dataset.addEntitiesSubTabHandlerAttached = 'true';

                btn.addEventListener('click', function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    const targetPanelId = this.getAttribute('data-tabs-target');
                    if (targetPanelId) {
                        const panelId = targetPanelId.replace('#', '');
                        activateAddEntitiesSubTab(panelId);
                    }
                });
            });

            // Initialize with first visible sub-tab if add-entities panel is active
            const addEntitiesPanel = document.getElementById('add-entities-panel');
            if (addEntitiesPanel && !addEntitiesPanel.classList.contains('hidden')) {
                const firstSubTab = addEntitiesSubTabButtons[0];
                if (firstSubTab) {
                    const targetPanelId = firstSubTab.getAttribute('data-tabs-target');
                    if (targetPanelId) {
                        const panelId = targetPanelId.replace('#', '');
                        activateAddEntitiesSubTab(panelId);
                    }
                }
            }
        }

        // Initialize on page load if add-entities panel is visible (incl. new assignments
        // with no top-level entity tabs — only the Assign Countries block is shown).
        setTimeout(function() {
            const addEntitiesPanel = document.getElementById('add-entities-panel');
            if (addEntitiesPanel && !addEntitiesPanel.classList.contains('hidden')) {
                initializeAddEntitiesSubTabs();
                loadCategoriesForAssignCountriesIfPresent();
            }
        }, 100);

        function getDefaultAssignmentEntityTab() {
            window.__clientLog && window.__clientLog('[DEBUG] getDefaultAssignmentEntityTab: Returning assignment-details-panel');
            if (document.getElementById('assignment-details-panel')) {
                return 'assignment-details-panel';
            }
            window.__clientLog && window.__clientLog('[DEBUG] getDefaultAssignmentEntityTab: No default tab found, returning null');
            return null;
        }

        // Initialize with stored tab or default to assignment details
        function initializeEntityTabs(useStoredTab = true) {
            window.__clientLog && window.__clientLog('[DEBUG] initializeEntityTabs: Starting, useStoredTab:', useStoredTab);
            // Ensure elements are available
            getEntityTabElements();

            if (!entityTabButtons || entityTabButtons.length === 0) {
                window.__clientWarn && window.__clientWarn('[DEBUG] initializeEntityTabs: No tabs available yet, returning');
                return; // No tabs available yet
            }

            const storedMainTab = localStorage.getItem('selectedAssignmentMainTab')
                || localStorage.getItem('selectedAssignmentEntityTab');
            window.__clientLog && window.__clientLog('[DEBUG] initializeEntityTabs: Stored tab from localStorage:', storedMainTab);

            if (useStoredTab && storedMainTab && document.getElementById(storedMainTab)) {
                window.__clientLog && window.__clientLog('[DEBUG] initializeEntityTabs: Activating stored tab', storedMainTab);
                activateEntityTab(storedMainTab);
                return;
            }

            window.__clientLog && window.__clientLog('[DEBUG] initializeEntityTabs: No valid stored tab, using default');
            const fallbackAssignmentTab = getDefaultAssignmentEntityTab();
            if (fallbackAssignmentTab && document.getElementById(fallbackAssignmentTab)) {
                window.__clientLog && window.__clientLog('[DEBUG] initializeEntityTabs: Activating default tab', fallbackAssignmentTab);
                activateEntityTab(fallbackAssignmentTab);
                return;
            }

            // Fallback: activate first visible tab button
            if (entityTabButtons.length > 0) {
                const firstButton = entityTabButtons[0];
                const targetPanelId = firstButton.getAttribute('data-tabs-target');
                window.__clientLog && window.__clientLog('[DEBUG] initializeEntityTabs: First button', firstButton.id, 'targets', targetPanelId);
                if (targetPanelId) {
                    const panelId = targetPanelId.replace('#', '');
                    window.__clientLog && window.__clientLog('[DEBUG] initializeEntityTabs: Activating first tab', panelId);
                    activateEntityTab(panelId);
                }
            }
            window.__clientLog && window.__clientLog('[DEBUG] initializeEntityTabs: Completed');
        }

        // Initialize on page load
        window.__clientLog && window.__clientLog('[DEBUG] Page load: Initializing main assignment tabs');
        if (document.getElementById('assignment-main-tabs')) {
            initializeEntityTabs(true);

            // Initialize grid if "Manage Existing Entities" tab is active by default
            requestAnimationFrame(function() {
                const managePanel = document.getElementById('manage-entities-panel');
                if (managePanel && !managePanel.classList.contains('hidden') && typeof scheduleEntityGridInit === 'function') {
                    window.__clientLog && window.__clientLog('[DEBUG] Page load: Manage entities panel is visible, initializing grid');
                    scheduleEntityGridInit();
                }
            });
        } else {
            window.__clientLog && window.__clientLog('[DEBUG] Page load: No main tabs on page (details only)');
        }

        // ---------------------------------------------------------------------
        // Freeze hierarchy columns (NS Structure and Secretariat tabs)
        // Distribute top-level items into fixed columns once, based on initial
        // viewport width, and never reshuffle columns on expansion.
        // ---------------------------------------------------------------------
        function computeInitialColumnCount() {
            const w = window.innerWidth || document.documentElement.clientWidth || 0;
            if (w >= 1280) return 5; // xl
            if (w >= 1024) return 4; // lg
            if (w >= 768) return 3;  // md
            if (w >= 640) return 2;  // sm
            return 1;
        }

        function freezeHierarchyColumns(container) {
            if (!container) return;
            // Avoid re-freezing if grid already exists
            if (container.querySelector(':scope > .fc-grid')) return;

            const topLevelUl = container.querySelector(':scope > ul');
            if (!topLevelUl) return;
            const items = Array.from(topLevelUl.children).filter(node => node && node.nodeName === 'LI');
            if (items.length === 0) return;

            const colCount = computeInitialColumnCount();
            const grid = document.createElement('div');
            grid.className = 'fc-grid';
            grid.style.setProperty('--fc-col-count', String(colCount));

            const columns = [];
            for (let i = 0; i < colCount; i++) {
                const colUl = document.createElement('ul');
                colUl.className = 'fc-col';
                columns.push(colUl);
                grid.appendChild(colUl);
            }

            items.forEach((li, index) => {
                const targetCol = columns[index % colCount];
                targetCol.appendChild(li);
            });

            // Remove original UL and attach the frozen grid
            topLevelUl.remove();
            container.appendChild(grid);
        }

        function initFixedColumnsObserver(containerId) {
            const container = document.getElementById(containerId);
            if (!container) return;

            // Try immediately if content already present
            freezeHierarchyColumns(container);

            // Observe for first-time hierarchy load/reload
            const observer = new MutationObserver(() => {
                // If a direct UL appears and we haven't frozen yet, freeze now
                const hasGrid = !!container.querySelector(':scope > .fc-grid');
                const hasTopUl = !!container.querySelector(':scope > ul');
                if (!hasGrid && hasTopUl) {
                    freezeHierarchyColumns(container);
                }
            });
            observer.observe(container, { childList: true });
        }

        // Attach to all hierarchical containers used on this page
        initFixedColumnsObserver('ns-structure-hierarchy-container');
        initFixedColumnsObserver('secretariat-hierarchy-container');
        initFixedColumnsObserver('secretariat-regions-container');

        // Predeclare hierarchical selector refs so they're available before first save-state update
        var nsStructureSelector = null;
        var secretariatSelector = null;
        var secretariatRegionsSelector = null;

        // --- Entity Countries Tab Checkbox Handling ---
        const entityRegionSelectAllCheckboxes = document.querySelectorAll('.region-select-all-entity');
        const entityCountryCheckboxes = document.querySelectorAll('.country-checkbox-entity:not([disabled])');
        const entityGlobalSelectAllCheckbox = document.getElementById('select-all-countries-entity');

        // --- Category-based Country Selection ---

        // Load categories and build mapping
        function loadCategoriesAndMapping() {
            if (bootstrapPartOfCategoriesFromConfig()) {
                return;
            }

            const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

            // Load categories list
            fetch(cfg.urls.apiPartOfPrograms, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                credentials: 'same-origin'
            })
            .then(response => response.json())
            .then(data => {
                if (data.success && (data.categories || data.programs)) {
                    availableCategories = data.categories || data.programs;
                    renderCategoryFilters();
                    loadCategoryToCountriesMapping();
                }
            })
            .catch(error => {
                console.error('Error loading categories:', error);
            });
        }

        // Load mapping of categories to countries (via NSs)
        function loadCategoryToCountriesMapping() {
            // Fetch NSs data with part_of information
            // Use the organization index API endpoint
            const url = cfg.urls.organizationIndex + "?tab=nss";
            window.__clientLog && window.__clientLog('Fetching NSs data from:', url);

            ((window.getFetch && window.getFetch()) || fetch)(url, {
                method: 'GET',
                headers: {
                    'Accept': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                credentials: 'same-origin'
            })
            .then(response => response.json())
            .then(data => {
                if (data.success && data.national_societies) {
                    // Build mapping: category -> [country_ids]
                    categoryToCountriesMap = {};

                    window.__clientLog && window.__clientLog('NSs data received:', data.national_societies.length, 'NSs');

                    data.national_societies.forEach(ns => {
                        // Handle both array and string formats for part_of
                        let partOfArray = [];
                        if (ns.part_of) {
                            if (Array.isArray(ns.part_of)) {
                                partOfArray = ns.part_of;
                            } else if (typeof ns.part_of === 'string') {
                                try {
                                    partOfArray = JSON.parse(ns.part_of);
                                    if (!Array.isArray(partOfArray)) {
                                        partOfArray = [];
                                    }
                                } catch (e) {
                                    window.__clientWarn && window.__clientWarn('Failed to parse part_of for NS', ns.id, ':', e);
                                    partOfArray = [];
                                }
                            }
                        }

                        if (partOfArray.length > 0 && ns.country_id) {
                            partOfArray.forEach(category => {
                                if (category && typeof category === 'string') {
                                    if (!categoryToCountriesMap[category]) {
                                        categoryToCountriesMap[category] = new Set();
                                    }
                                    categoryToCountriesMap[category].add(ns.country_id);
                                }
                            });
                        }
                    });

                    // Convert Sets to Arrays
                    for (let category in categoryToCountriesMap) {
                        categoryToCountriesMap[category] = Array.from(categoryToCountriesMap[category]);
                    }

                    window.__clientLog && window.__clientLog('Category to countries mapping:', categoryToCountriesMap);
                } else {
                    window.__clientWarn && window.__clientWarn('Failed to load NSs data or no data returned');
                }
            })
            .catch(error => {
                console.error('Error loading category to countries mapping:', error);
            });
        }

        // Render category filter checkboxes into a container with a given change handler
        function renderCategoryFiltersTo(containerId, onChange) {
            const container = document.getElementById(containerId);
            if (!container) return;

            // Keep server-rendered checkboxes — only build dynamically when the container is empty.
            if (container.querySelector('.category-filter-checkbox')) {
                return;
            }

            container.innerHTML = '';

            if (availableCategories.length === 0) {
                container.innerHTML = '<span class="text-xs text-gray-500">No categories available</span>';
                return;
            }

            availableCategories.forEach(category => {
                const label = document.createElement('label');
                label.className = 'flex items-center gap-2 cursor-pointer';

                const checkbox = document.createElement('input');
                checkbox.type = 'checkbox';
                checkbox.className = 'category-filter-checkbox h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500';
                checkbox.value = category;
                checkbox.dataset.category = category;
                if (containerId === 'category-filters-manage') {
                    checkbox.classList.add('category-filter-manage');
                }

                const span = document.createElement('span');
                span.className = 'text-sm text-gray-700';
                span.textContent = category;

                label.appendChild(checkbox);
                label.appendChild(span);
                container.appendChild(label);
            });
        }

        function bindCategoryFilterDelegation() {
            const entityContainer = document.getElementById('category-filters-entity');
            if (entityContainer && entityContainer.dataset.filterDelegationBound !== 'true') {
                entityContainer.dataset.filterDelegationBound = 'true';
                entityContainer.addEventListener('change', function (event) {
                    const checkbox = event.target;
                    if (!checkbox.classList.contains('category-filter-checkbox') || checkbox.classList.contains('category-filter-manage')) {
                        return;
                    }
                    const category = checkbox.dataset.category || checkbox.value;
                    handleCategoryFilterChange(category, checkbox.checked);
                });
            }

            const manageContainer = document.getElementById('category-filters-manage');
            if (manageContainer && manageContainer.dataset.filterDelegationBound !== 'true') {
                manageContainer.dataset.filterDelegationBound = 'true';
                manageContainer.addEventListener('change', function (event) {
                    const checkbox = event.target;
                    if (!checkbox.classList.contains('category-filter-manage')) {
                        return;
                    }
                    const category = checkbox.dataset.category || checkbox.value;
                    handleManageCategoryFilterChange(category, checkbox.checked);
                });
            }
        }

        // Render category filters in both Add Entities and Manage Existing Entities panels
        function renderCategoryFilters() {
            renderCategoryFiltersTo('category-filters-entity', handleCategoryFilterChange);
            renderCategoryFiltersTo('category-filters-manage', handleManageCategoryFilterChange);
            bindCategoryFilterDelegation();
        }

        function bootstrapPartOfCategoriesFromConfig() {
            const categories = cfg.partOfCategories;
            const mapping = cfg.partOfCategoryToCountries;
            const hasServerRenderedFilters = !!document.querySelector(
                '#category-filters-entity .category-filter-checkbox, #category-filters-manage .category-filter-checkbox'
            );

            if (Array.isArray(categories) && categories.length > 0) {
                availableCategories = categories;
            } else if (hasServerRenderedFilters) {
                availableCategories = Array.from(
                    document.querySelectorAll('#category-filters-entity .category-filter-checkbox')
                ).map(function (cb) {
                    return cb.dataset.category || cb.value;
                }).filter(Boolean);
            } else {
                return false;
            }

            if (mapping && typeof mapping === 'object') {
                categoryToCountriesMap = mapping;
            }

            renderCategoryFilters();
            bindCategoryFilterDelegation();
            return true;
        }

        function bootstrapVisiblePartOfFiltersIfNeeded() {
            const entityFilters = document.getElementById('category-filters-entity');
            const manageFilters = document.getElementById('category-filters-manage');
            if (!entityFilters && !manageFilters) return;

            const addEntitiesPanel = document.getElementById('add-entities-panel');
            const managePanel = document.getElementById('manage-entities-panel');
            const assignCountriesVisible = entityFilters && addEntitiesPanel && !addEntitiesPanel.classList.contains('hidden');
            const manageVisible = manageFilters && managePanel && !managePanel.classList.contains('hidden');
            const hasServerRenderedFilters = !!document.querySelector(
                '#category-filters-entity .category-filter-checkbox, #category-filters-manage .category-filter-checkbox'
            );

            if (assignCountriesVisible || manageVisible || hasServerRenderedFilters) {
                if (bootstrapPartOfCategoriesFromConfig()) {
                    categoriesLoaded = true;
                } else {
                    bindCategoryFilterDelegation();
                }
            }
        }

        // Handle category filter checkbox change
        function handleCategoryFilterChange(category, isChecked) {
            // Wait a bit if mapping is still being built
            if (Object.keys(categoryToCountriesMap).length === 0) {
                window.__clientLog && window.__clientLog('Category mapping not ready yet, waiting...');
                setTimeout(() => handleCategoryFilterChange(category, isChecked), 500);
                return;
            }

            const countryIds = categoryToCountriesMap[category] || [];

            if (countryIds.length === 0) {
                window.__clientWarn && window.__clientWarn(`No countries found for category: ${category}`);
                window.__clientLog && window.__clientLog('Available categories in mapping:', Object.keys(categoryToCountriesMap));
                window.__clientLog && window.__clientLog('Full mapping:', categoryToCountriesMap);
                return;
            }

            // Select/deselect countries that have NSs part of this category
            countryIds.forEach(countryId => {
                const countryCheckbox = document.getElementById(`country-entity-${countryId}`);
                if (countryCheckbox && !countryCheckbox.disabled) {
                    countryCheckbox.checked = isChecked;
                }
            });

            // Update region and global select all checkboxes (entity-specific)
            const regions = new Set();
            countryIds.forEach(countryId => {
                const countryCheckbox = document.getElementById(`country-entity-${countryId}`);
                if (countryCheckbox) {
                    const regionContainer = countryCheckbox.closest('.region-countries-entity');
                    if (regionContainer && regionContainer.dataset.region) {
                        regions.add(regionContainer.dataset.region);
                    }
                }
            });
            regions.forEach(region => {
                if (typeof updateEntityRegionSelectAll === 'function') {
                    updateEntityRegionSelectAll(region);
                }
            });

            if (typeof updateEntityGlobalSelectAll === 'function') {
                updateEntityGlobalSelectAll();
            }

            // Sync hidden country inputs so the main form reflects the updated checkbox state
            syncCountriesToMainForm();
        }

        // Handle category filter change in Manage Existing Entities: filter grid by Part of selection
        function handleManageCategoryFilterChange(category, isChecked) {
            if (Object.keys(categoryToCountriesMap).length === 0) {
                setTimeout(() => handleManageCategoryFilterChange(category, isChecked), 500);
                return;
            }
            const manageContainer = document.getElementById('category-filters-manage');
            if (!manageContainer) return;
            const checkedBoxes = manageContainer.querySelectorAll('.category-filter-manage:checked');
            const selectedCountryIds = new Set();
            checkedBoxes.forEach(cb => {
                const cat = cb.value || cb.dataset.category;
                (categoryToCountriesMap[cat] || []).forEach(id => selectedCountryIds.add(Number(id)));
            });
            const gridApi = window.entityGridApi;
            if (!gridApi || typeof entityManagementData === 'undefined') return;
            if (selectedCountryIds.size === 0) {
                gridApi.setGridOption('rowData', entityManagementData);
                return;
            }
            const filtered = entityManagementData.filter(row => {
                if (row.entity_type !== 'country') return false;
                const eid = row.entity_id != null ? Number(row.entity_id) : null;
                return eid != null && selectedCountryIds.has(eid);
            });
            gridApi.setGridOption('rowData', filtered);
        }

        bootstrapVisiblePartOfFiltersIfNeeded();

        // Category filters are now loaded directly from activateEntityTab /
        // activateAddEntitiesSubTab (see loadCategoriesOnce above) whenever the Manage
        // Existing Entities or Add Entities → Countries panel actually becomes visible —
        // covering click, page-load, and localStorage-restored activation uniformly.

        // Function to update the state of a region "Select All" checkbox
        function updateEntityRegionSelectAll(region) {
            const regionSelectAllCheckbox = document.querySelector(`.region-select-all-entity[data-region="${region}"]`);
            // Only count enabled checkboxes
            const countriesInRegion = document.querySelectorAll(`.region-countries-entity[data-region="${region}"] .country-checkbox-entity:not([disabled])`);
            const allChecked = countriesInRegion.length > 0 && Array.from(countriesInRegion).every(cb => cb.checked);
            if (regionSelectAllCheckbox) {
                regionSelectAllCheckbox.checked = allChecked;
            }
        }

        // Function to update the state of the global "Select All" checkbox
        function updateEntityGlobalSelectAll() {
            // Only count enabled checkboxes
            const allCountryCheckboxes = document.querySelectorAll('.country-checkbox-entity:not([disabled])');
            const allChecked = allCountryCheckboxes.length > 0 && Array.from(allCountryCheckboxes).every(cb => cb.checked);
            if (entityGlobalSelectAllCheckbox) {
                entityGlobalSelectAllCheckbox.checked = allChecked;
            }
        }

        // Add event listener to the global "Select All" checkbox
        if (entityGlobalSelectAllCheckbox) {
            entityGlobalSelectAllCheckbox.addEventListener('change', function() {
                const isChecked = this.checked;
                // Only update enabled checkboxes
                document.querySelectorAll('.country-checkbox-entity:not([disabled])').forEach(countryCheckbox => {
                    countryCheckbox.checked = isChecked;
                });
                entityRegionSelectAllCheckboxes.forEach(regionCheckbox => {
                    regionCheckbox.checked = isChecked;
                });
            });
        }

        // Add event listener to each region "Select All" checkbox
        entityRegionSelectAllCheckboxes.forEach(regionCheckbox => {
            regionCheckbox.addEventListener('change', function() {
                const region = this.dataset.region;
                const isChecked = this.checked;
                // Only update enabled checkboxes
                const countriesInRegion = document.querySelectorAll(`.region-countries-entity[data-region="${region}"] .country-checkbox-entity:not([disabled])`);
                countriesInRegion.forEach(countryCheckbox => {
                    countryCheckbox.checked = isChecked;
                });
                updateEntityGlobalSelectAll();
            });
        });

        // Add event listener to individual country checkboxes
        entityCountryCheckboxes.forEach(countryCheckbox => {
            countryCheckbox.addEventListener('change', function() {
                const regionContainer = this.closest('.region-countries-entity');
                if (regionContainer) {
                    const region = regionContainer.dataset.region;
                    updateEntityRegionSelectAll(region);
                }
                updateEntityGlobalSelectAll();
            });
        });

        // Initial state on page load
        updateEntityGlobalSelectAll();
        entityRegionSelectAllCheckboxes.forEach(regionCheckbox => {
            const region = regionCheckbox.dataset.region;
            updateEntityRegionSelectAll(region);
        });

        // Sync country selections to main form.
        // Safe to call at any time: no-op when the container is absent (e.g. edit pages).
        function syncCountriesToMainForm() {
            const container = document.getElementById('country-selections-container');
            if (!container) return;

            // Clear existing hidden inputs
            container.innerHTML = '';

            // Get all checked country checkboxes
            const checkedCountries = document.querySelectorAll('.country-checkbox-entity:checked:not([disabled])');
            checkedCountries.forEach(checkbox => {
                const hiddenInput = document.createElement('input');
                hiddenInput.type = 'hidden';
                hiddenInput.name = 'countries'; // Match the form field name (form.countries.data)
                hiddenInput.value = checkbox.value;
                container.appendChild(hiddenInput);
            });

            if (scheduleNotifBannerRefresh) {
                scheduleNotifBannerRefresh();
            }
        }

        // Register change-event listeners and run initial sync only for new assignments
        if (!cfg.assignmentId) {
        // Sync on checkbox change
        entityCountryCheckboxes.forEach(countryCheckbox => {
            countryCheckbox.addEventListener('change', syncCountriesToMainForm);
        });
        if (entityGlobalSelectAllCheckbox) {
            entityGlobalSelectAllCheckbox.addEventListener('change', syncCountriesToMainForm);
        }
        entityRegionSelectAllCheckboxes.forEach(regionCheckbox => {
            regionCheckbox.addEventListener('change', syncCountriesToMainForm);
        });

        // Initial sync
        syncCountriesToMainForm();
        }

        // Initialize Hierarchical Entity Selectors for NS Structure and Secretariat

        // Global save button state helpers (cumulative adds across all tabs)
        function computeAddsCountAll() {
            let totalAdds = 0;
            // Countries (entity tab)
            const countryAdds = document.querySelectorAll('.country-checkbox-entity:not([disabled]):checked').length;
            totalAdds += countryAdds;
            // NS Structure
            if (nsStructureSelector && nsStructureSelector.pendingAdditions) {
                totalAdds += nsStructureSelector.pendingAdditions.size;
            }
            // Secretariat Divisions & Departments
            if (secretariatSelector && secretariatSelector.pendingAdditions) {
                totalAdds += secretariatSelector.pendingAdditions.size;
            }
            // Secretariat Regions
            if (secretariatRegionsSelector && secretariatRegionsSelector.pendingAdditions) {
                totalAdds += secretariatRegionsSelector.pendingAdditions.size;
            }
            return totalAdds;
        }

        function hasAnyChanges() {
            // Adds in countries
            if (document.querySelectorAll('.country-checkbox-entity:not([disabled]):checked').length > 0) return true;
            // Any pending adds/removals in hierarchical selectors
            const selectors = [nsStructureSelector, secretariatSelector, secretariatRegionsSelector];
            for (const sel of selectors) {
                if (!sel) continue;
                if (sel.pendingAdditions && sel.pendingAdditions.size > 0) return true;
                if (sel.pendingRemovals && sel.pendingRemovals.size > 0) return true;
            }
            return false;
        }

        // Function to save all entity changes (used before form submission)
        async function saveAllEntityChanges() {
            let totalAdded = 0;
            let hadError = false;
            const tasks = [];

            // Save NS Structure pending changes
            if (nsStructureSelector) {
                tasks.push(
                    nsStructureSelector.savePendingChanges()
                        .then(res => { if (res) { totalAdded += (res.added || 0); if (!res.success) hadError = true; } })
                        .catch(() => { hadError = true; })
                );
            }

            // Save Secretariat Divisions & Departments pending changes
            if (secretariatSelector) {
                tasks.push(
                    secretariatSelector.savePendingChanges()
                        .then(res => { if (res) { totalAdded += (res.added || 0); if (!res.success) hadError = true; } })
                        .catch(() => { hadError = true; })
                );
            }

            // Save Secretariat Regions pending changes
            if (secretariatRegionsSelector) {
                tasks.push(
                    secretariatRegionsSelector.savePendingChanges()
                        .then(res => { if (res) { totalAdded += (res.added || 0); if (!res.success) hadError = true; } })
                        .catch(() => { hadError = true; })
                );
            }

            // Add Countries (entity tab) selections
            const countryAdds = document.querySelectorAll('.country-checkbox-entity:not([disabled]):checked').length;
            const addCountriesForm = document.getElementById('add-countries-form');
            if (addCountriesForm && countryAdds > 0) {
                const fd = new FormData(addCountriesForm);
                tasks.push(
                    fetch(addCountriesForm.action, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                        body: new URLSearchParams(fd)
                    })
                    .then(() => { totalAdded += countryAdds; })
                    .catch(() => { hadError = true; })
                );
            }

            try {
                await Promise.all(tasks);
            } catch (_) {
                hadError = true;
            }

            return { success: !hadError, totalAdded };
        }

        // Create a custom class that extends HierarchicalEntitySelector functionality for assignments
        class AssignmentHierarchicalEntitySelector extends HierarchicalEntitySelector {
            constructor(config) {
                // Call parent constructor FIRST before accessing 'this'
                // Override targetUserId to null since we're using targetAssignmentId instead
                super({...config, targetUserId: null});
                // Now we can safely access 'this'
                // Store targetAssignmentId instead of targetUserId
                this.targetAssignmentId = config.targetAssignmentId;
                // Store status_id mapping separately
                this.statusIdMap = new Map(); // Maps "entityType:entityId" to status_id
                // Track pending changes
                this.pendingAdditions = new Set();
                this.pendingRemovals = new Set();
                // Save button element ID
                this.saveButtonId = config.saveButtonId || null;
            }

            async loadAssignedEntities() {
                if (!this.targetAssignmentId) return;

                try {
                    const response = await fetch(cfg.urls.assignmentGetEntities);
                    const data = await response.json();

                    // Clear pending changes when reloading
                    this.pendingAdditions = new Set();
                    this.pendingRemovals = new Set();

                    // Filter to only entity types we're displaying
                    const entities = data.entities || [];
                    for (const entity of entities) {
                        if (this.entityTypes.includes(entity.entity_type)) {
                            const entityKey = `${entity.entity_type}:${entity.entity_id}`;
                            // Store in assignedEntities for checkbox checking
                            this.assignedEntities.add(entityKey);
                            // Store status_id separately for removal
                            this.statusIdMap.set(entityKey, entity.status_id);
                        }
                    }

                    // Initialize hidden form fields with existing permissions
                    this.updateHiddenFormFields();
                    // Update save button state
                    this.updateSaveButtonState();
                    // Mark as loaded so callers can avoid duplicate fetches
                    this._assignedLoaded = true;
                } catch (error) {
                    console.error('Error loading assigned entities:', error);
                }
            }

            async addEntity(entityType, entityId) {
                if (!this.targetAssignmentId) return;

                try {
                    const response = await fetch(cfg.urls.assignmentAddEntity, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': this.getCSRFToken()
                        },
                        body: JSON.stringify({
                            entity_type: entityType,
                            entity_id: entityId
                        })
                    });

                    const data = await response.json();
                    if (data.success) {
                        const entityKey = `${entityType}:${entityId}`;
                        this.assignedEntities.add(entityKey);
                        this.statusIdMap.set(entityKey, data.status_id);
                        this.updateHiddenFormFields();
                        this.render();
                        if (this.onChange) this.onChange({type: 'add', entityType, entityId});
                    }
                    return data;
                } catch (error) {
                    console.error('Error adding entity:', error);
                    return {success: false, error: error.message};
                }
            }

            async removeEntity(entityType, entityId, statusId) {
                if (!this.targetAssignmentId) return;

                try {
                    const response = await fetch(cfg.urls.assignmentRemoveEntityBase + statusId, {
                        method: 'DELETE',
                        headers: {
                            'X-CSRFToken': this.getCSRFToken()
                        }
                    });

                    const data = await response.json();
                    if (data.success) {
                        const entityKey = `${entityType}:${entityId}`;
                        this.assignedEntities.delete(entityKey);
                        this.statusIdMap.delete(entityKey);
                        this.updateHiddenFormFields();
                        this.render();
                        if (this.onChange) this.onChange({type: 'remove', entityType, entityId});
                    }
                    return data;
                } catch (error) {
                    console.error('Error removing entity:', error);
                    return {success: false, error: error.message};
                }
            }

            getStatusId(entityType, entityId) {
                const entityKey = `${entityType}:${entityId}`;
                return this.statusIdMap.get(entityKey) || null;
            }

            toggleEntityPermission(entityType, entityId, entityName, isChecked, checkboxElement) {
                const entityKey = `${entityType}:${entityId}`;

                // Ensure checkbox state matches what the user clicked
                if (checkboxElement) {
                    checkboxElement.checked = isChecked;
                }

                // Track pending changes instead of saving immediately
                // Initialize pending changes sets if they don't exist
                if (!this.pendingAdditions) {
                    this.pendingAdditions = new Set();
                }
                if (!this.pendingRemovals) {
                    this.pendingRemovals = new Set();
                }

                if (isChecked) {
                    // Mark as pending addition
                    // Remove from pending removals if it was there
                    this.pendingRemovals.delete(entityKey);
                    // Add to pending additions if not already assigned
                    if (!this.assignedEntities.has(entityKey)) {
                        this.pendingAdditions.add(entityKey);
                    } else {
                        // If already assigned, remove from pending additions
                        this.pendingAdditions.delete(entityKey);
                    }
                } else {
                    // Mark as pending removal
                    // Remove from pending additions if it was there
                    this.pendingAdditions.delete(entityKey);
                    // Add to pending removals if currently assigned
                    if (this.assignedEntities.has(entityKey)) {
                        this.pendingRemovals.add(entityKey);
                    } else {
                        // If not assigned, remove from pending removals
                        this.pendingRemovals.delete(entityKey);
                    }
                }

                // Update hidden form fields
                this.updateHiddenFormFields();

                // Call onChange callback if provided (for UI updates)
                if (this.onChange) {
                    this.onChange({
                        entity_type: entityType,
                        entity_id: entityId,
                        action: isChecked ? 'pending_add' : 'pending_remove'
                    });
                }

                // Update save button state
                this.updateSaveButtonState();
            }

            updateSaveButtonState() {
                // Update save button enabled/disabled state
                if (this.saveButtonId) {
                    const saveButton = document.getElementById(this.saveButtonId);
                    if (saveButton) {
                        const hasChanges = (this.pendingAdditions && this.pendingAdditions.size > 0) ||
                                         (this.pendingRemovals && this.pendingRemovals.size > 0);
                        saveButton.disabled = !hasChanges;
                        const addCount = this.pendingAdditions ? this.pendingAdditions.size : 0;
                        const removeCount = this.pendingRemovals ? this.pendingRemovals.size : 0;
                        let label = '<i class="fas fa-save mr-1"></i> Save Changes';
                        if (hasChanges && (addCount > 0 || removeCount > 0)) {
                            const parts = [];
                            if (addCount > 0) parts.push(`${addCount} to add`);
                            if (removeCount > 0) parts.push(`${removeCount} to remove`);
                            label = `<i class="fas fa-save mr-1"></i> Save Changes (${parts.join(', ')})`;
                        }
                        saveButton.innerHTML = label;
                    }
                }
            }

            async savePendingChanges() {
                if (!this.pendingAdditions && !this.pendingRemovals) {
                    return {success: true, message: 'No changes to save'};
                }

                const results = {
                    added: 0,
                    removed: 0,
                    errors: []
                };

                // Process removals first
                if (this.pendingRemovals && this.pendingRemovals.size > 0) {
                    for (const entityKey of this.pendingRemovals) {
                        const [entityType, entityId] = entityKey.split(':');
                        const statusId = this.getStatusId(entityType, parseInt(entityId));
                        if (statusId) {
                            try {
                                const result = await this.removeEntity(entityType, parseInt(entityId), statusId);
                                if (result.success) {
                                    results.removed++;
                                    this.pendingRemovals.delete(entityKey);
                                    // Update assigned entities state
                                    this.assignedEntities.delete(entityKey);
                                    this.statusIdMap.delete(entityKey);
                                } else {
                                    results.errors.push(`Failed to remove ${entityType}:${entityId}`);
                                }
                            } catch (error) {
                                results.errors.push(`Error removing ${entityType}:${entityId}: ${error.message}`);
                            }
                        }
                    }
                }

                // Process additions
                if (this.pendingAdditions && this.pendingAdditions.size > 0) {
                    for (const entityKey of this.pendingAdditions) {
                        const [entityType, entityId] = entityKey.split(':');
                            try {
                                const result = await this.addEntity(entityType, parseInt(entityId));
                                if (result.success) {
                                    results.added++;
                                    this.pendingAdditions.delete(entityKey);
                                    // Update assigned entities state
                                    this.assignedEntities.add(entityKey);
                                    if (result.status_id) {
                                        this.statusIdMap.set(entityKey, result.status_id);
                                    }
                                } else {
                                    results.errors.push(`Failed to add ${entityType}:${entityId}`);
                                }
                            } catch (error) {
                                results.errors.push(`Error adding ${entityType}:${entityId}: ${error.message}`);
                            }
                    }
                }

                // Update save button state
                this.updateSaveButtonState();

                return {
                    success: results.errors.length === 0,
                    added: results.added,
                    removed: results.removed,
                    errors: results.errors
                };
            }
        }

        // Initialize NS Structure hierarchical selector
        if (document.getElementById('ns-structure-hierarchy-container')) {
            if (cfg.assignmentId) {
            nsStructureSelector = new AssignmentHierarchicalEntitySelector({
                containerId: 'ns-structure-hierarchy-container',
                apiBaseUrl: '', // Empty since blueprint already has /admin prefix
                targetAssignmentId: cfg.assignmentId,
                entityTypes: ['ns_branch', 'ns_subbranch', 'ns_localunit'],
                saveButtonId: 'save-ns-structure-changes-btn',
                onChange: function(data) {}
            });


            } else {
            // For new assignments, use regular HierarchicalEntitySelector (no assigned entities yet)
            nsStructureSelector = new HierarchicalEntitySelector({
                containerId: 'ns-structure-hierarchy-container',
                apiBaseUrl: '',
                targetUserId: null,
                entityTypes: ['ns_branch', 'ns_subbranch', 'ns_localunit'],
                onChange: function(data) {
                    // Just update hidden form fields - no need to reload from server
                    // Changes will be saved when form is submitted
                }
            });
            }

            // Country select wiring for NS Structure
            const nsCountrySelect = document.getElementById('ns-country-select');
            const nsContainer = document.getElementById('ns-structure-hierarchy-container');
            function loadNsForCountry(countryId) {
                if (!countryId) {
                    nsContainer.innerHTML = `
                        <div class="text-center py-4">
                            <i class="fas fa-info-circle text-gray-400"></i>
                            <p class="text-sm text-gray-500 mt-2">Select a country to view NS structure.</p>
                        </div>`;
                    return;
                }
                nsContainer.innerHTML = `
                    <div class="text-center py-4">
                        <i class="fas fa-spinner fa-spin text-gray-400"></i>
                        <p class="text-sm text-gray-500 mt-2">Loading NS structure...</p>
                    </div>`;
                // Ensure assigned entities are loaded before rendering hierarchy so checkboxes reflect current state
                const ensureAssignedLoaded = (nsStructureSelector && nsStructureSelector._assignedLoaded)
                    ? Promise.resolve()
                    : nsStructureSelector.loadAssignedEntities();
                ensureAssignedLoaded
                    .then(() => {
                        nsStructureSelector.loadHierarchy(cfg.urls.nsHierarchyBase + '?country_id=' + countryId);
                    })
                    .catch(function(err) { console.error('[manage-assignment] Failed to load NS hierarchy:', err); });
            }
            if (nsCountrySelect) {
                nsCountrySelect.addEventListener('change', function() {
                    loadNsForCountry(this.value);
                });
                // If editing an assignment and it has countries, preselect the first country
                // but defer the hierarchy fetch until the NS Structure tab is opened.
                if (cfg.assignmentId) {
                const assignmentCountryIds = new Set(cfg.assignmentCountryIds || []);
                const firstCountryId = Array.from(assignmentCountryIds)[0];
                if (firstCountryId) {
                    nsCountrySelect.value = String(firstCountryId);
                }
                }
            }

            // Add search functionality
            const nsSearchInput = document.getElementById('ns-structure-search');
            if (nsSearchInput && nsStructureSelector) {
                let searchTimeout;
                nsSearchInput.addEventListener('input', (e) => {
                    clearTimeout(searchTimeout);
                    searchTimeout = setTimeout(() => {
                        nsStructureSelector.filterHierarchy(e.target.value);
                    }, 300);
                });
            }

            // Defer NS hierarchy fetch until the NS Structure tab is first shown.
            let nsHierarchyLoaded = false;
            function loadNsHierarchyOnce() {
                if (nsHierarchyLoaded) return;
                if (!nsCountrySelect || !nsCountrySelect.value) return;
                nsHierarchyLoaded = true;
                loadNsForCountry(nsCountrySelect.value);
            }
            const nsStructureTabBtn = document.getElementById('ns-structure-tab');
            if (nsStructureTabBtn) {
                nsStructureTabBtn.addEventListener('click', loadNsHierarchyOnce);
            }
            if (document.querySelector('#ns-structure-panel:not(.hidden)')) {
                loadNsHierarchyOnce();
            }
        }

        // Hoisted so activateSecretariatSubtab can trigger lazy loads.
        let loadSecretariatHierarchyOnce = function () {};
        let loadSecretariatRegionsHierarchyOnce = function () {};

        // Initialize Secretariat hierarchical selector (Divisions & Departments)
        // Hierarchy fetch is deferred until the secretariat panel/tab is first shown.
        if (document.getElementById('secretariat-hierarchy-container')) {
            if (cfg.assignmentId) {
            secretariatSelector = new AssignmentHierarchicalEntitySelector({
                containerId: 'secretariat-hierarchy-container',
                apiBaseUrl: '', // Empty since blueprint already has /admin prefix
                targetAssignmentId: cfg.assignmentId,
                entityTypes: ['division', 'department'],
                saveButtonId: 'save-secretariat-changes-btn',
                onChange: function(data) {}
            });
            } else {
            // For new assignments, use regular HierarchicalEntitySelector (no assigned entities yet)
            secretariatSelector = new HierarchicalEntitySelector({
                containerId: 'secretariat-hierarchy-container',
                apiBaseUrl: '',
                targetUserId: null,
                entityTypes: ['division', 'department'],
                onChange: function(data) {
                    // Just update hidden form fields - no need to reload from server
                    // Changes will be saved when form is submitted
                }
            });
            }

            let secretariatHierarchyLoaded = false;
            loadSecretariatHierarchyOnce = function () {
                if (secretariatHierarchyLoaded || !secretariatSelector) return;
                secretariatHierarchyLoaded = true;
                if (cfg.assignmentId) {
                    const ensureSecretariatAssignedLoaded = secretariatSelector._assignedLoaded
                        ? Promise.resolve()
                        : secretariatSelector.loadAssignedEntities();
                    ensureSecretariatAssignedLoaded
                        .then(() => {
                            secretariatSelector.loadHierarchy(cfg.urls.secretariatHierarchy);
                        })
                        .catch(function(err) { console.error('[manage-assignment] Failed to load secretariat hierarchy:', err); });
                } else {
                    secretariatSelector.loadHierarchy(cfg.urls.secretariatHierarchy);
                }
            };
            const addEntitiesSecretariatTab = document.getElementById('add-entities-secretariat-tab');
            const secretariatDivisionsTab = document.getElementById('secretariat-divisions-tab');
            if (addEntitiesSecretariatTab) addEntitiesSecretariatTab.addEventListener('click', loadSecretariatHierarchyOnce);
            if (secretariatDivisionsTab) secretariatDivisionsTab.addEventListener('click', loadSecretariatHierarchyOnce);
            // Also when Add Entities is opened and secretariat is the (only/default) visible sub-panel
            const addEntitiesTabBtn = document.getElementById('add-entities-tab');
            if (addEntitiesTabBtn) {
                addEntitiesTabBtn.addEventListener('click', function () {
                    if (document.querySelector('#add-entities-secretariat-panel:not(.hidden)') ||
                        !document.getElementById('add-entities-countries-panel')) {
                        loadSecretariatHierarchyOnce();
                    }
                });
            }
            // If the secretariat panel is already the default-visible add-entities sub-tab, load now.
            const secretariatPanel = document.getElementById('add-entities-secretariat-panel');
            if (secretariatPanel && !secretariatPanel.classList.contains('hidden')) {
                loadSecretariatHierarchyOnce();
            }

            // Add search functionality
            const secretariatSearchInput = document.getElementById('secretariat-search');
            if (secretariatSearchInput && secretariatSelector) {
                let searchTimeout;
                secretariatSearchInput.addEventListener('input', (e) => {
                    clearTimeout(searchTimeout);
                    searchTimeout = setTimeout(() => {
                        secretariatSelector.filterHierarchy(e.target.value);
                    }, 300);
                });
            }
        }

        // Initialize Secretariat Regions hierarchical selector
        if (document.getElementById('secretariat-regions-container')) {
            if (cfg.assignmentId) {
            secretariatRegionsSelector = new AssignmentHierarchicalEntitySelector({
                containerId: 'secretariat-regions-container',
                apiBaseUrl: '',
                targetAssignmentId: cfg.assignmentId,
                entityTypes: ['regional_office', 'cluster_office'],
                saveButtonId: 'save-secretariat-regions-changes-btn',
                onChange: function(data) {}
            });
            } else {
            // For new assignments, use regular HierarchicalEntitySelector (no assigned entities yet)
            secretariatRegionsSelector = new HierarchicalEntitySelector({
                containerId: 'secretariat-regions-container',
                apiBaseUrl: '',
                targetUserId: null,
                entityTypes: ['regional_office', 'cluster_office'],
                onChange: function(data) {
                    // Just update hidden form fields - no need to reload from server
                    // Changes will be saved when form is submitted
                }
            });
            }

            let secretariatRegionsHierarchyLoaded = false;
            loadSecretariatRegionsHierarchyOnce = function () {
                if (secretariatRegionsHierarchyLoaded || !secretariatRegionsSelector) return;
                secretariatRegionsHierarchyLoaded = true;
                if (cfg.assignmentId) {
                    const ensureRegionsAssignedLoaded = secretariatRegionsSelector._assignedLoaded
                        ? Promise.resolve()
                        : secretariatRegionsSelector.loadAssignedEntities();
                    ensureRegionsAssignedLoaded
                        .then(() => {
                            secretariatRegionsSelector.loadHierarchy(cfg.urls.secretariatRegionsHierarchy);
                        })
                        .catch(function(err) { console.error('[manage-assignment] Failed to load secretariat regions hierarchy:', err); });
                } else {
                    secretariatRegionsSelector.loadHierarchy(cfg.urls.secretariatRegionsHierarchy);
                }
            };
            const secretariatRegionsTab = document.getElementById('secretariat-regions-tab');
            if (secretariatRegionsTab) {
                secretariatRegionsTab.addEventListener('click', loadSecretariatRegionsHierarchyOnce);
            }
            if (
                document.querySelector('#secretariat-regions-panel') &&
                !document.querySelector('#secretariat-regions-panel').classList.contains('hidden')
            ) {
                loadSecretariatRegionsHierarchyOnce();
            }

            const secretariatRegionsSearchInput = document.getElementById('secretariat-regions-search');
            if (secretariatRegionsSearchInput && secretariatRegionsSelector) {
                let searchTimeout;
                secretariatRegionsSearchInput.addEventListener('input', (e) => {
                    clearTimeout(searchTimeout);
                    searchTimeout = setTimeout(() => {
                        secretariatRegionsSelector.filterHierarchy(e.target.value);
                    }, 300);
                });
            }
        }

        // Secretariat sub-tabs behavior
        const secretariatSubtabButtons = document.querySelectorAll('#secretariat-subtabs button[role="tab"]');
        const secretariatSubtabPanels = document.querySelectorAll('#secretariat-subtabs-content > div[role="tabpanel"]');
        function activateSecretariatSubtab(panelId) {
            secretariatSubtabButtons.forEach(btn => {
                const target = btn.getAttribute('data-tabs-target');
                if (target === '#' + panelId) {
                    btn.classList.add('text-blue-600', 'border-blue-600');
                    btn.classList.remove('border-transparent', 'hover:text-gray-600', 'hover:border-gray-300');
                    btn.setAttribute('aria-selected', 'true');
                } else {
                    btn.classList.remove('text-blue-600', 'border-blue-600');
                    btn.classList.add('border-transparent', 'hover:text-gray-600', 'hover:border-gray-300');
                    btn.setAttribute('aria-selected', 'false');
                }
            });
            secretariatSubtabPanels.forEach(panel => {
                if (panel.id === panelId) {
                    panel.classList.remove('hidden');
                } else {
                    panel.classList.add('hidden');
                }
            });
            localStorage.setItem('selectedAssignmentSecretariatSubtab', panelId);
            // Lazy-load hierarchy for the newly visible secretariat sub-tab — but only when
            // the ancestor Add Entities → Secretariat panel is actually visible. This function
            // also runs on page init to restore the last-selected sub-tab's button/panel
            // classes even when the whole Secretariat section is hidden (e.g. Add Entities →
            // Countries is the active sub-tab, or "Manage Existing Entities" is the active
            // top-level tab); network loads must not fire in that case.
            const addEntitiesPanelForSecretariat = document.getElementById('add-entities-panel');
            const addEntitiesSecretariatPanel = document.getElementById('add-entities-secretariat-panel');
            const secretariatSectionVisible =
                (!addEntitiesPanelForSecretariat || !addEntitiesPanelForSecretariat.classList.contains('hidden')) &&
                (!addEntitiesSecretariatPanel || !addEntitiesSecretariatPanel.classList.contains('hidden'));
            if (secretariatSectionVisible) {
                if (panelId === 'secretariat-divisions-panel') {
                    loadSecretariatHierarchyOnce();
                } else if (panelId === 'secretariat-regions-panel') {
                    loadSecretariatRegionsHierarchyOnce();
                }
            }
        }
        secretariatSubtabButtons.forEach(btn => {
            btn.addEventListener('click', function() {
                const targetPanelId = this.getAttribute('data-tabs-target').substring(1);
                activateSecretariatSubtab(targetPanelId);
            });
        });
        const storedAssignmentSecretariatSubtab = localStorage.getItem('selectedAssignmentSecretariatSubtab');
        if (storedAssignmentSecretariatSubtab && document.getElementById(storedAssignmentSecretariatSubtab)) {
            activateSecretariatSubtab(storedAssignmentSecretariatSubtab);
        } else {
            activateSecretariatSubtab('secretariat-divisions-panel');
        }

        // Function to validate period name before form submission
        function validatePeriodName(form) {
            if (typeof window.syncCustomNameTranslationsToForm === 'function') {
                window.syncCustomNameTranslationsToForm();
            }
            const periodNameField = document.querySelector('input[name="period_name"]');
            const errorContainer = document.getElementById('period-name-error');

            if (!periodNameField) {
                return true; // No period name field, skip validation
            }

            const periodName = periodNameField.value.trim();

            if (!periodName) {
                // Show error message
                if (errorContainer) {
                    errorContainer.classList.remove('hidden');
                    // Scroll to error message
                    errorContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                }

                return false;
            } else {
                // Hide error message if it was shown
                if (errorContainer) {
                    errorContainer.classList.add('hidden');
                }
                return true;
            }
        }

        // Intercept form submission to save entity changes first (for existing assignments)
        if (cfg.assignmentId) {
        const mainForm = document.getElementById('manageAssignmentForm') ||
                        document.querySelector('form[action*="edit_assignment"]') ||
                        document.querySelector('form[method="POST"]');

        if (mainForm) {
            // Change submit button to type="button" to prevent automatic disabling
            // We'll submit the form programmatically only if validation passes
            const submitButton = mainForm.querySelector('button[type="submit"], input[type="submit"]') ||
                document.getElementById('manageAssignmentSubmitBtn');
            if (submitButton) {
                // Store original type and change to button to prevent auto-disable
                submitButton.type = 'button';

                // Handle button click
                submitButton.addEventListener('click', async function(e) {
                    e.preventDefault();
                    e.stopPropagation();

                    // Validate period name first
                    if (!validatePeriodName(mainForm)) {
                        return false;
                    }

                    // If validation passes, create a temporary submit button and click it
                    // This triggers form submission without disabling our main button
                    const tempSubmit = document.createElement('button');
                    tempSubmit.type = 'submit';
                    tempSubmit.style.display = 'none';
                    mainForm.appendChild(tempSubmit);
                    tempSubmit.click();
                    mainForm.removeChild(tempSubmit);
                });
            }

            function resetEditSubmitGuard() {
                try {
                    if (window.FormSubmitGuard && typeof window.FormSubmitGuard.reset === 'function') {
                        window.FormSubmitGuard.reset(mainForm);
                    }
                } catch (_) { /* no-op */ }
            }

            // Use capture phase to ensure we run before any other handlers
            mainForm.addEventListener('submit', async function(e) {
                // Validate period name first - prevent default immediately if validation fails
                if (!validatePeriodName(mainForm)) {
                    e.preventDefault();
                    e.stopPropagation();
                    e.stopImmediatePropagation();
                    resetEditSubmitGuard();
                    return false;
                }

                // Check if there are any entity changes to save
                const hasEntityChanges = hasAnyChanges() ||
                    document.querySelectorAll('.country-checkbox-entity:not([disabled]):checked').length > 0;

                if (hasEntityChanges) {
                    e.preventDefault();
                    e.stopPropagation();
                    resetEditSubmitGuard();

                    const submitBtn = mainForm.querySelector('button[type="submit"], input[type="submit"]') ||
                        document.getElementById('manageAssignmentSubmitBtn');
                    const originalHTML = submitBtn ? submitBtn.innerHTML : '';
                    const originalDisabled = submitBtn ? submitBtn.disabled : false;

                    if (submitBtn) {
                        submitBtn.disabled = true;
                        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i> Saving...';
                    }

                    // Save entity changes first
                    const result = await saveAllEntityChanges();

                    if (result.success) {
                        // Now submit the form
                        if (submitBtn) {
                            submitBtn.innerHTML = originalHTML;
                            submitBtn.disabled = originalDisabled;
                        }
                        // Use prototype method to avoid shadowing by form elements named "submit"
                        HTMLFormElement.prototype.submit.call(mainForm);
                    } else {
                        Utils.showError('Some entity changes could not be saved. Please try again.');
                        if (submitBtn) {
                            submitBtn.innerHTML = originalHTML;
                            submitBtn.disabled = originalDisabled;
                        }
                        resetEditSubmitGuard();
                    }
                }
                // If no entity changes, let form submit normally
            });
        }
        }

        // Store selectors globally for debugging
        window.nsStructureSelector = nsStructureSelector;
        window.secretariatSelector = secretariatSelector;

        // Sync all entity selections to form before submission (for new assignments only)
        if (!cfg.assignmentId) {
        // Find the main assignment form - try multiple selectors to be sure we get it
        const mainForm = document.getElementById('manageAssignmentForm') ||
                        document.querySelector('form[action*="new_assignment"]') ||
                        document.querySelector('form[method="POST"]') ||
                        document.querySelector('form');

        if (mainForm) {
            // Change submit button to type="button" to prevent automatic disabling
            // We'll submit the form programmatically only if validation passes
            const submitButton = mainForm.querySelector('button[type="submit"], input[type="submit"]') ||
                document.getElementById('manageAssignmentSubmitBtn');
            if (submitButton) {
                // Store original type and change to button to prevent auto-disable
                submitButton.type = 'button';

                // Handle button click
                submitButton.addEventListener('click', function(e) {
                    e.preventDefault();
                    e.stopPropagation();

                    // Validate period name first
                    if (!validatePeriodName(mainForm)) {
                        return false;
                    }

                    // If validation passes, create a temporary submit button and click it
                    // This triggers form submission without disabling our main button
                    const tempSubmit = document.createElement('button');
                    tempSubmit.type = 'submit';
                    tempSubmit.style.display = 'none';
                    mainForm.appendChild(tempSubmit);
                    tempSubmit.click();
                    mainForm.removeChild(tempSubmit);
                });
            }

            // Duplicate preflight (avoid losing JS selections by round-tripping the page)
            const DUPLICATE_CHECK_URL = cfg.urls.checkDuplicate;

            async function preflightDuplicateIfNeeded() {
                const confirmField = mainForm.querySelector('input[name="confirm_duplicate"]');
                const alreadyConfirmed = confirmField && (confirmField.value === '1');
                if (alreadyConfirmed) {
                    return { ok: true };
                }

                const templateSelect = mainForm.querySelector('select[name="template_id"]');
                const periodNameField = mainForm.querySelector('input[name="period_name"]');
                const templateId = templateSelect ? parseInt(templateSelect.value, 10) : null;
                const periodName = periodNameField ? (periodNameField.value || '').trim() : '';

                if (!templateId || !periodName) {
                    return { ok: true };
                }

                try {
                    const url = `${DUPLICATE_CHECK_URL}?template_id=${encodeURIComponent(templateId)}&period_name=${encodeURIComponent(periodName)}`;
                    const resp = await fetch(url, { headers: { 'Accept': 'application/json' } });
                    const data = await resp.json();
                    if (!data || !data.success || !data.exists) {
                        return { ok: true };
                    }

                    const a = data.assignment || {};
                    const statusBits = [];
                    if (a.is_effectively_closed) statusBits.push('closed/expired');
                    if (a.is_closed) statusBits.push('closed');
                    if (a.is_active === false) statusBits.push('inactive');
                    const statusText = statusBits.length ? statusBits.join(', ') : 'active';

                    const msg =
                        `An assignment already exists for this template and period.\n\n` +
                        `Existing ID: ${a.id}\n` +
                        `Template: ${a.template_name || ''}\n` +
                        `Period: ${a.period_name || ''}\n` +
                        `Status: ${statusText}\n\n` +
                        `Create a NEW duplicate assignment anyway?`;

                    return new Promise(function(resolve) {
                        if (window.showConfirmation) {
                            window.showConfirmation(
                                msg,
                                function() {
                                    if (confirmField) confirmField.value = '1';
                                    resolve({ ok: true });
                                },
                                function() { resolve({ ok: false }); },
                                cfg.t.createAnyway,
                                cfg.t.cancel,
                                cfg.t.duplicateAssignment
                            );
                        } else {
                            if (window.showConfirmation) {
                                window.showConfirmation(msg, function() { if (confirmField) confirmField.value = '1'; resolve({ ok: true }); }, function() { resolve({ ok: false }); }, cfg.t.createAnyway, cfg.t.cancel, cfg.t.duplicateAssignment);
                            } else {
                                resolve({ ok: false });
                            }
                        }
                    });
                } catch (err) {
                    // If the check fails, don't block creation (server-side guard still exists)
                    return { ok: true };
                }
            }

            function resetSubmitGuard() {
                try {
                    if (window.FormSubmitGuard && typeof window.FormSubmitGuard.reset === 'function') {
                        window.FormSubmitGuard.reset(mainForm);
                    }
                } catch (_) { /* no-op */ }
                mainForm.dataset.maSubmitting = '0';
            }

            // Use capture phase to ensure we run before any other handlers
            mainForm.addEventListener('submit', async function(e) {
                // Validate period name first - prevent default immediately if validation fails
                if (!validatePeriodName(mainForm)) {
                    e.preventDefault();
                    e.stopPropagation();
                    e.stopImmediatePropagation();
                    resetSubmitGuard();
                    return false;
                }

                // Prevent re-entry while preflight/confirmation dialog is open
                if (mainForm.dataset.maSubmitting === '1') {
                    e.preventDefault();
                    e.stopPropagation();
                    e.stopImmediatePropagation();
                    return false;
                }
                mainForm.dataset.maSubmitting = '1';

                // We'll submit programmatically after syncing hidden inputs + duplicate preflight.
                e.preventDefault();
                e.stopPropagation();
                e.stopImmediatePropagation();
                // stopPropagation blocks FormSubmitGuard's bubble-phase reset; clear stale state now.
                resetSubmitGuard();

                window.__clientLog && window.__clientLog('[DEBUG] Form submit event triggered');

                // Collect all selected entities from checked checkboxes (primary source of truth)
                const allSelectedEntities = new Set();

                // Get selected entities from NS Structure selector
                const nsContainer = document.getElementById('ns-structure-hierarchy-container');
                if (nsContainer) {
                    // Check all checkboxes, even in hidden containers
                    const checkedBoxes = nsContainer.querySelectorAll('.entity-checkbox:checked');
                    window.__clientLog && window.__clientLog('[DEBUG] NS Structure: Found', checkedBoxes.length, 'checked checkboxes');
                    checkedBoxes.forEach(checkbox => {
                        const entityType = checkbox.dataset.entityType;
                        const entityId = checkbox.dataset.entityId;
                        if (entityType && entityId) {
                            const entityKey = `${entityType}:${entityId}`;
                            allSelectedEntities.add(entityKey);
                            window.__clientLog && window.__clientLog('[DEBUG] NS Structure: Added', entityKey);
                        }
                    });
                    // Also check assignedEntities Set as fallback
                    if (nsStructureSelector && nsStructureSelector.assignedEntities) {
                        nsStructureSelector.assignedEntities.forEach(entityKey => {
                            allSelectedEntities.add(entityKey);
                            window.__clientLog && window.__clientLog('[DEBUG] NS Structure: Added from assignedEntities', entityKey);
                        });
                    }
                }

                // Get selected entities from Secretariat Divisions & Departments selector
                const secretariatContainer = document.getElementById('secretariat-hierarchy-container');
                if (secretariatContainer) {
                    const checkedBoxes = secretariatContainer.querySelectorAll('.entity-checkbox:checked');
                    window.__clientLog && window.__clientLog('[DEBUG] Secretariat: Found', checkedBoxes.length, 'checked checkboxes');
                    checkedBoxes.forEach(checkbox => {
                        const entityType = checkbox.dataset.entityType;
                        const entityId = checkbox.dataset.entityId;
                        if (entityType && entityId) {
                            const entityKey = `${entityType}:${entityId}`;
                            allSelectedEntities.add(entityKey);
                            window.__clientLog && window.__clientLog('[DEBUG] Secretariat: Added', entityKey);
                        }
                    });
                    // Also check assignedEntities Set as fallback
                    if (secretariatSelector && secretariatSelector.assignedEntities) {
                        secretariatSelector.assignedEntities.forEach(entityKey => {
                            allSelectedEntities.add(entityKey);
                            window.__clientLog && window.__clientLog('[DEBUG] Secretariat: Added from assignedEntities', entityKey);
                        });
                    }
                }

                // Get selected entities from Secretariat Regions selector
                const regionsContainer = document.getElementById('secretariat-regions-container');
                if (regionsContainer) {
                    const checkedBoxes = regionsContainer.querySelectorAll('.entity-checkbox:checked');
                    window.__clientLog && window.__clientLog('[DEBUG] Secretariat Regions: Found', checkedBoxes.length, 'checked checkboxes');
                    checkedBoxes.forEach(checkbox => {
                        const entityType = checkbox.dataset.entityType;
                        const entityId = checkbox.dataset.entityId;
                        if (entityType && entityId) {
                            const entityKey = `${entityType}:${entityId}`;
                            allSelectedEntities.add(entityKey);
                            window.__clientLog && window.__clientLog('[DEBUG] Secretariat Regions: Added', entityKey);
                        }
                    });
                    // Also check assignedEntities Set as fallback
                    if (secretariatRegionsSelector && secretariatRegionsSelector.assignedEntities) {
                        secretariatRegionsSelector.assignedEntities.forEach(entityKey => {
                            allSelectedEntities.add(entityKey);
                            window.__clientLog && window.__clientLog('[DEBUG] Secretariat Regions: Added from assignedEntities', entityKey);
                        });
                    }
                }

                // Remove any existing entity_permissions fields from the form
                mainForm.querySelectorAll('input[name="entity_permissions"]').forEach(input => {
                    input.remove();
                });

                // Create hidden inputs for each selected entity and add directly to form
                allSelectedEntities.forEach(entityKey => {
                    const hiddenInput = document.createElement('input');
                    hiddenInput.type = 'hidden';
                    hiddenInput.name = 'entity_permissions';
                    hiddenInput.value = entityKey;
                    mainForm.appendChild(hiddenInput);
                    window.__clientLog && window.__clientLog('[DEBUG] Added hidden input:', entityKey);
                });

                window.__clientLog && window.__clientLog('[DEBUG] Form submit: Total entities collected:', allSelectedEntities.size, Array.from(allSelectedEntities));

                // Verify the fields are in the form before submission
                const finalFields = mainForm.querySelectorAll('input[name="entity_permissions"]');
                window.__clientLog && window.__clientLog('[DEBUG] Final entity_permissions fields in form:', finalFields.length);
                finalFields.forEach(field => {
                    window.__clientLog && window.__clientLog('[DEBUG]   -', field.value);
                });

                const dup = await preflightDuplicateIfNeeded();
                if (!dup.ok) {
                    resetSubmitGuard();
                    return false;
                }

                // Notification confirmation: fetch recipient preview, then ask for confirm
                const sendNotifCheckbox = mainForm.querySelector('input[name="send_notifications"]');
                const sendNotifications = sendNotifCheckbox ? sendNotifCheckbox.checked : true;

                function doSubmit() {
                    // Re-sync country checkboxes → hidden inputs right before submission
                    // (guards against the category-filter path that sets .checked without
                    // firing a change event, and any other programmatic checkbox changes)
                    syncCountriesToMainForm();
                    HTMLFormElement.prototype.submit.call(mainForm);
                }

                // Collect country IDs currently selected for the assignment
                function getSelectedCountryIds() {
                    return collectSelectedCountryIdsForPreview();
                }

                async function fetchNotifPreview(countryIds) {
                    if (!cfg.urls || !cfg.urls.notificationPreview) return null;
                    try {
                        const params = buildNotifPreviewQueryParams(countryIds);
                        const resp = await fetch(cfg.urls.notificationPreview + '?' + params.toString(), {
                            headers: { 'X-Requested-With': 'XMLHttpRequest' }
                        });
                        if (!resp.ok) return null;
                        return await resp.json();
                    } catch (e) {
                        return null;
                    }
                }

                function _formatNotifSummary(preview, includeAdminCc, localCountryIds) {
                    return formatNotifRecipientsSummary(preview, includeAdminCc, localCountryIds);
                }

                function buildConfirmMsg(sendNotifications, preview, localCountryIds) {
                    if (!sendNotifications) return cfg.t.noNotifyMsg;
                    if (!preview) return cfg.t.notifyMsg;
                    // Admins are a separate audience bucket from focal points, so
                    // focal_points_enabled=false doesn't necessarily mean no one is notified.
                    const hasAdminRecipients = !!(preview.admins_enabled && preview.admin_users);
                    if (!preview.focal_points_enabled && !hasAdminRecipients) {
                        return cfg.t.notifyMsgDisabled;
                    }
                    if (!preview.total_focal_users && !hasAdminRecipients) {
                        return cfg.t.notifyMsg + '\n\n⚠ ' + cfg.t.notifyNoRecipients;
                    }
                    const notifyAdminsCheckbox = document.getElementById('notify_admins');
                    const includeAdminCc = notifyAdminsCheckbox ? notifyAdminsCheckbox.checked : false;
                    const summary = _formatNotifSummary(preview, includeAdminCc, localCountryIds);
                    return cfg.t.notifyMsg + '\n\n' + summary;
                }

                // Sync countries into the form first so we can read them
                syncCountriesToMainForm();
                const selectedCountryIds = getSelectedCountryIds();

                const preview = sendNotifications ? await fetchNotifPreview(selectedCountryIds) : null;
                const confirmMsg = buildConfirmMsg(sendNotifications, preview, selectedCountryIds);
                const confirmTitle = cfg.t.createAssignment;
                const confirmContinue = cfg.t.continueBtn;
                const confirmCancel = cfg.t.cancel;

                if (window.showConfirmation) {
                    window.showConfirmation(
                        confirmMsg,
                        doSubmit,
                        resetSubmitGuard,
                        confirmContinue,
                        confirmCancel,
                        confirmTitle
                    );
                } else {
                    doSubmit();
                }
            });
        } else {
            window.__clientWarn && window.__clientWarn('[DEBUG] Could not find main form element!');
        }
        }

        window.__clientLog && window.__clientLog('[SCRIPT] Document ready function completed - all initialization code executed');
        window.__clientLog && window.__clientLog('[SCRIPT] You can now call window.testLogging() or window.logColumnWidths() from console');

        // --- Notification audience warning banner (new-assignment page only) ---
        if (cfg.isNew && cfg.urls && cfg.urls.notificationPreview) {
            const audienceWarningEl = document.getElementById('notif-audience-warning');
            const audienceWarningTextEl = document.getElementById('notif-audience-warning-text');
            const recipientPreviewEl = document.getElementById('notif-recipient-preview');
            const recipientPreviewTextEl = document.getElementById('notif-recipient-preview-text');
            const sendNotifCheckbox = document.getElementById('send_notifications');
            const notifDetailsPanel = document.getElementById('notif-details-panel');
            const notifyAdminsRow = document.getElementById('notify-admins-row');
            const notifyAdminsCheckbox = document.getElementById('notify_admins');
            const notifyAdminsHint = document.getElementById('notify-admins-hint');

            let _lastPreview = null;
            let _lastPreviewCountryIds = [];

            function _formatBannerSummary(preview) {
                const includeAdminCc = notifyAdminsCheckbox ? notifyAdminsCheckbox.checked : false;
                return formatNotifRecipientsSummary(preview, includeAdminCc, _lastPreviewCountryIds);
            }

            function _updateNotifyAdminsRow(preview) {
                if (!notifyAdminsRow) return;
                // Admins are a separate audience bucket from focal points, so this row can
                // stay available even when focal_points_enabled is false (admins may still
                // be notified — see admins_enabled check below).
                if (!sendNotifCheckbox || !sendNotifCheckbox.checked || !preview) {
                    notifyAdminsRow.classList.add('hidden');
                    return;
                }
                if (!preview.admins_enabled) {
                    notifyAdminsRow.classList.add('hidden');
                    if (notifyAdminsCheckbox) {
                        notifyAdminsCheckbox.checked = false;
                    }
                    return;
                }
                notifyAdminsRow.classList.remove('hidden');
                if (notifyAdminsCheckbox) {
                    notifyAdminsCheckbox.disabled = false;
                    if (notifyAdminsHint) {
                        if (preview.admin_users) {
                            notifyAdminsHint.textContent = (cfg.t.notifyAdminsHint || '')
                                .replace('{admin_users}', preview.admin_users);
                        } else if (preview.admin_total_users) {
                            notifyAdminsHint.textContent = (cfg.t.notifyAdminInAppAllFocal || '')
                                .replace('{admin_total}', preview.admin_total_users);
                        } else {
                            notifyAdminsHint.textContent = cfg.t.notifyAdminInAppNone || '';
                        }
                    }
                }
            }

            async function _fetchAndUpdateNotifBanner() {
                if (!sendNotifCheckbox || !sendNotifCheckbox.checked) {
                    if (notifDetailsPanel) notifDetailsPanel.classList.add('hidden');
                    if (audienceWarningEl) audienceWarningEl.classList.add('hidden');
                    if (recipientPreviewEl) recipientPreviewEl.classList.add('hidden');
                    if (notifyAdminsRow) notifyAdminsRow.classList.add('hidden');
                    return;
                }

                if (notifDetailsPanel) notifDetailsPanel.classList.remove('hidden');

                // Show loading state
                if (recipientPreviewEl && recipientPreviewTextEl) {
                    recipientPreviewTextEl.textContent = cfg.t.notifyPreviewLoading || 'Checking…';
                    recipientPreviewEl.classList.remove('hidden');
                }
                if (audienceWarningEl) audienceWarningEl.classList.add('hidden');

                // Collect selected countries from checkboxes (primary) or synced hidden inputs
                _lastPreviewCountryIds = collectSelectedCountryIdsForPreview();

                try {
                    const params = buildNotifPreviewQueryParams(_lastPreviewCountryIds);
                    const resp = await fetch(cfg.urls.notificationPreview + '?' + params.toString(), {
                        headers: { 'X-Requested-With': 'XMLHttpRequest' }
                    });
                    if (!resp.ok) throw new Error('preview fetch failed');
                    _lastPreview = await resp.json();
                } catch (e) {
                    _lastPreview = null;
                }

                if (!_lastPreview) {
                    if (recipientPreviewEl) recipientPreviewEl.classList.add('hidden');
                    if (notifyAdminsRow) notifyAdminsRow.classList.add('hidden');
                    return;
                }

                if (!_lastPreview.focal_points_enabled) {
                    // Focal-points bucket disabled — always show the warning (focal points truly get
                    // nothing), but admins are a separate bucket and may still be notified, so keep
                    // showing their controls/counts instead of hiding everything.
                    if (audienceWarningEl && audienceWarningTextEl) {
                        audienceWarningTextEl.textContent = cfg.t.notifyAudienceDisabled || 'Notifications are disabled in platform settings.';
                        audienceWarningEl.classList.remove('hidden');
                    }
                    _updateNotifyAdminsRow(_lastPreview);
                    if (recipientPreviewEl && recipientPreviewTextEl) {
                        const hasRecipients = _lastPreview.admin_users || _lastPreview.email_batch_count;
                        if (hasRecipients) {
                            recipientPreviewTextEl.textContent = _formatBannerSummary(_lastPreview);
                            recipientPreviewEl.classList.remove('hidden');
                        } else {
                            recipientPreviewEl.classList.add('hidden');
                        }
                    }
                    return;
                }

                // Audience enabled — show recipient count
                if (audienceWarningEl) audienceWarningEl.classList.add('hidden');
                _updateNotifyAdminsRow(_lastPreview);
                if (recipientPreviewEl && recipientPreviewTextEl) {
                    const hasRecipients = _lastPreview.total_focal_users
                        || _lastPreview.email_batch_count
                        || _lastPreview.admin_users;
                    if (!hasRecipients) {
                        recipientPreviewTextEl.textContent = cfg.t.notifyNoRecipients || 'No focal points configured for selected countries.';
                    } else {
                        recipientPreviewTextEl.textContent = _formatBannerSummary(_lastPreview);
                    }
                    recipientPreviewEl.classList.remove('hidden');
                }
            }

            scheduleNotifBannerRefresh = function() {
                clearTimeout(notifBannerRefreshTimer);
                notifBannerRefreshTimer = setTimeout(_fetchAndUpdateNotifBanner, 150);
            };

            // Run on load and whenever the checkbox changes
            _fetchAndUpdateNotifBanner();
            if (sendNotifCheckbox) {
                sendNotifCheckbox.addEventListener('change', _fetchAndUpdateNotifBanner);
            }
            if (notifyAdminsCheckbox) {
                notifyAdminsCheckbox.addEventListener('change', function() {
                    scheduleNotifBannerRefresh();
                });
            }

            // Re-run when country selection changes via individual checkboxes, Select All,
            // region Select All, or Part of filters (all paths call syncCountriesToMainForm).
            document.addEventListener('change', function(e) {
                const target = e.target;
                if (!target) return;
                if (target.classList.contains('country-checkbox-entity')) {
                    scheduleNotifBannerRefresh();
                    return;
                }
                if (target.id === 'select-all-countries-entity' || target.classList.contains('region-select-all-entity')) {
                    scheduleNotifBannerRefresh();
                    return;
                }
                if (target.classList.contains('category-filter-checkbox') && !target.classList.contains('category-filter-manage')) {
                    scheduleNotifBannerRefresh();
                }
            });
        }

        // --- Notification email preview modal (new-assignment page only) ---
        if (cfg.isNew && cfg.urls && cfg.urls.notificationEmailPreview) {
            const emailPreviewBtn = document.getElementById('notif-email-preview-btn');
            const emailPreviewModal = document.getElementById('assignment-notif-email-preview-modal');
            const emailPreviewCountrySelect = document.getElementById('notif-email-preview-country');
            const emailPreviewLoading = document.getElementById('notif-email-preview-loading');
            const emailPreviewEmpty = document.getElementById('notif-email-preview-empty');
            const emailPreviewContent = document.getElementById('notif-email-preview-content');
            const emailPreviewSubject = document.getElementById('notif-email-preview-subject');
            const emailPreviewTo = document.getElementById('notif-email-preview-to');
            const emailPreviewCc = document.getElementById('notif-email-preview-cc');
            const emailPreviewCcWrap = document.getElementById('notif-email-preview-cc-wrap');
            const emailPreviewToWrap = document.getElementById('notif-email-preview-to-wrap');
            const emailPreviewFrame = document.getElementById('notif-email-preview-frame');

            function collectSelectedCountriesWithNames() {
                const seen = new Set();
                const out = [];
                document.querySelectorAll('.country-checkbox-entity:checked:not([disabled])').forEach(function(cb) {
                    if (!cb.value || seen.has(cb.value)) return;
                    seen.add(cb.value);
                    const label = cb.id
                        ? document.querySelector('label[for="' + String(cb.id).replace(/\\/g, '\\\\').replace(/"/g, '\\"') + '"]')
                        : null;
                    let name = cb.value;
                    if (label) {
                        name = label.textContent.replace(/\s*\(assigned\)\s*$/i, '').trim();
                    }
                    out.push({ id: cb.value, name: name });
                });
                out.sort(function(a, b) { return a.name.localeCompare(b.name); });
                return out;
            }

            function getAssignmentFormPreviewParams() {
                const form = document.getElementById('manageAssignmentForm') ||
                    document.querySelector('form[action*="assignments"]') ||
                    document.querySelector('form[method="POST"]');
                const notifyAdminsEl = document.getElementById('notify_admins');
                return {
                    templateId: form && form.querySelector('select[name="template_id"]')
                        ? form.querySelector('select[name="template_id"]').value : '',
                    periodName: form && form.querySelector('input[name="period_name"]')
                        ? (form.querySelector('input[name="period_name"]').value || '').trim() : '',
                    customName: form && form.querySelector('input[name="custom_name"]')
                        ? (form.querySelector('input[name="custom_name"]').value || '').trim() : '',
                    dueDate: form && form.querySelector('input[name="due_date"]')
                        ? (form.querySelector('input[name="due_date"]').value || '').trim() : '',
                    notifyAdmins: notifyAdminsEl ? notifyAdminsEl.checked : false,
                };
            }

            function renderRecipientList(container, recipients, emptyText) {
                if (!container) return;
                container.innerHTML = '';
                if (!recipients || !recipients.length) {
                    const empty = document.createElement('span');
                    empty.className = 'text-xs text-gray-400 italic';
                    empty.textContent = emptyText;
                    container.appendChild(empty);
                    return;
                }
                recipients.forEach(function(r) {
                    const chip = document.createElement('span');
                    chip.className = 'inline-flex max-w-full items-center gap-1 rounded-full border border-gray-200 bg-white px-2.5 py-1 text-xs text-gray-700 shadow-sm';
                    chip.title = r.email || '';
                    const nameEl = document.createElement('span');
                    nameEl.className = 'truncate font-medium';
                    nameEl.textContent = r.name || r.email;
                    chip.appendChild(nameEl);
                    if (r.name && r.email && r.name !== r.email) {
                        const emailEl = document.createElement('span');
                        emailEl.className = 'hidden truncate text-gray-400 sm:inline';
                        emailEl.textContent = r.email;
                        chip.appendChild(emailEl);
                    }
                    container.appendChild(chip);
                });
            }

            function setEmailPreviewFrameHtml(htmlBody) {
                if (!emailPreviewFrame) return;
                const html = htmlBody || '';
                requestAnimationFrame(function() {
                    emailPreviewFrame.srcdoc = html;
                });
            }

            async function loadNotifEmailPreview(countryId) {
                if (!countryId) return;
                const params = getAssignmentFormPreviewParams();
                if (emailPreviewLoading) emailPreviewLoading.classList.remove('hidden');
                if (emailPreviewContent) emailPreviewContent.classList.add('hidden');
                if (emailPreviewEmpty) emailPreviewEmpty.classList.add('hidden');
                if (emailPreviewFrame) emailPreviewFrame.srcdoc = '';

                const qs = new URLSearchParams({
                    country_id: countryId,
                    template_id: params.templateId || '',
                    period_name: params.periodName || '',
                    notify_admins: params.notifyAdmins ? '1' : '0',
                });
                if (params.customName) qs.set('custom_name', params.customName);
                if (params.dueDate) qs.set('due_date', params.dueDate);

                try {
                    const resp = await fetch(cfg.urls.notificationEmailPreview + '?' + qs.toString(), {
                        headers: { 'X-Requested-With': 'XMLHttpRequest' }
                    });
                    const data = await resp.json();
                    if (emailPreviewLoading) emailPreviewLoading.classList.add('hidden');

                    if (!resp.ok || !data || data.success === false) {
                        if (emailPreviewEmpty) {
                            emailPreviewEmpty.textContent = (data && data.message) || 'Preview failed.';
                            emailPreviewEmpty.classList.remove('hidden');
                        }
                        return;
                    }

                    if (data.empty_reason) {
                        if (emailPreviewEmpty) {
                            emailPreviewEmpty.textContent = data.empty_reason;
                            emailPreviewEmpty.classList.remove('hidden');
                        }
                        return;
                    }

                    if (emailPreviewSubject) emailPreviewSubject.textContent = data.subject || '';
                    renderRecipientList(
                        emailPreviewTo,
                        data.to,
                        cfg.t.notifyEmailPreviewNoRecipients || 'No To recipients.'
                    );
                    const hasCc = data.cc && data.cc.length;
                    if (emailPreviewCcWrap) {
                        emailPreviewCcWrap.classList.toggle('hidden', !hasCc);
                    }
                    if (emailPreviewToWrap) {
                        emailPreviewToWrap.classList.toggle('md:col-span-2', !hasCc);
                    }
                    if (hasCc) {
                        renderRecipientList(
                            emailPreviewCc,
                            data.cc,
                            cfg.t.notifyEmailPreviewNoRecipients || 'No CC recipients.'
                        );
                    } else if (emailPreviewCc) {
                        emailPreviewCc.innerHTML = '';
                    }
                    if (emailPreviewContent) emailPreviewContent.classList.remove('hidden');
                    setEmailPreviewFrameHtml(data.html_body || '');
                } catch (e) {
                    if (emailPreviewLoading) emailPreviewLoading.classList.add('hidden');
                    if (emailPreviewEmpty) {
                        emailPreviewEmpty.textContent = 'Preview failed.';
                        emailPreviewEmpty.classList.remove('hidden');
                    }
                }
            }

            function openNotifEmailPreviewModal() {
                if (!emailPreviewModal) return;
                const countries = collectSelectedCountriesWithNames();
                const formParams = getAssignmentFormPreviewParams();

                if (!formParams.templateId || !formParams.periodName) {
                    if (window.showAlert) {
                        window.showAlert(
                            cfg.t.notifyEmailPreviewNeedTemplate || 'Select template and period first.',
                            'warning'
                        );
                    }
                    return;
                }
                if (!countries.length) {
                    if (window.showAlert) {
                        window.showAlert(
                            cfg.t.notifyEmailPreviewNoCountries || 'Select countries first.',
                            'warning'
                        );
                    }
                    return;
                }

                if (emailPreviewCountrySelect) {
                    emailPreviewCountrySelect.innerHTML = '';
                    countries.forEach(function(c) {
                        const opt = document.createElement('option');
                        opt.value = c.id;
                        opt.textContent = c.name;
                        emailPreviewCountrySelect.appendChild(opt);
                    });
                }

                if (emailPreviewContent) emailPreviewContent.classList.add('hidden');
                if (emailPreviewEmpty) emailPreviewEmpty.classList.add('hidden');
                if (emailPreviewLoading) emailPreviewLoading.classList.remove('hidden');

                emailPreviewModal.classList.remove('hidden');
                requestAnimationFrame(function() {
                    loadNotifEmailPreview(countries[0].id);
                });
            }

            if (emailPreviewBtn) {
                emailPreviewBtn.addEventListener('click', openNotifEmailPreviewModal);
            }
            if (emailPreviewCountrySelect) {
                emailPreviewCountrySelect.addEventListener('change', function() {
                    loadNotifEmailPreview(this.value);
                });
            }
            const notifyAdminsForPreview = document.getElementById('notify_admins');
            if (notifyAdminsForPreview) {
                notifyAdminsForPreview.addEventListener('change', function() {
                    if (!emailPreviewModal || emailPreviewModal.classList.contains('hidden')) {
                        return;
                    }
                    const countryId = emailPreviewCountrySelect && emailPreviewCountrySelect.value;
                    if (countryId) {
                        loadNotifEmailPreview(countryId);
                    }
                });
            }
        }

        // Event delegation for remove public and remove entity buttons (use custom confirmation)
        $(document).on('click', '.remove-public-btn, .remove-entity-btn', function(e) {
            const confirmMsg = $(this).data('confirm');
            if (!confirmMsg) return;
            e.preventDefault();
            const form = $(this).closest('form')[0];
            if (window.showConfirmation) {
                window.showConfirmation(
                    confirmMsg,
                    function() { if (form) HTMLFormElement.prototype.submit.call(form); },
                    function() {},
                    cfg.t.confirm,
                    cfg.t.cancel,
                    cfg.t.confirmAction
                );
            } else if (form && window.confirm(confirmMsg)) {
                HTMLFormElement.prototype.submit.call(form);
            }
            return false;
        });
    });

// --- Template Data Owner Prefill ---
(function () {
    // Pre-fill data owner from template's owned_by when template selection changes
    const templateSelect = document.querySelector('select[name="template_id"]');
    const dataOwnerSelect = document.getElementById('data_owner_id_select');
    const exportExcelCheckbox = document.getElementById('enable_export_excel');
    const importExcelCheckbox = document.getElementById('enable_import_excel');
    const exportPdfCheckbox = document.getElementById('enable_export_pdf');
    if (!templateSelect) return;

    let exportExcelUserTouched = exportExcelCheckbox ? exportExcelCheckbox.checked : false;
    let importExcelUserTouched = importExcelCheckbox ? importExcelCheckbox.checked : false;
    let exportPdfUserTouched = exportPdfCheckbox ? exportPdfCheckbox.checked : false;
    if (exportExcelCheckbox) {
        exportExcelCheckbox.addEventListener('change', function () {
            exportExcelUserTouched = true;
        });
    }
    if (importExcelCheckbox) {
        importExcelCheckbox.addEventListener('change', function () {
            importExcelUserTouched = true;
        });
    }
    if (exportPdfCheckbox) {
        exportPdfCheckbox.addEventListener('change', function () {
            exportPdfUserTouched = true;
        });
    }

    function syncGenericExcelDefaults(templateMeta) {
        if (cfg.isNew !== true && cfg.isNew !== 'true') {
            return;
        }
        if (exportPdfCheckbox && !exportPdfUserTouched) {
            exportPdfCheckbox.checked = Boolean(templateMeta && templateMeta.enable_export_pdf);
        }
        if (exportExcelCheckbox && !exportExcelUserTouched) {
            exportExcelCheckbox.checked = Boolean(templateMeta && templateMeta.enable_export_excel);
        }
        if (importExcelCheckbox && !importExcelUserTouched) {
            importExcelCheckbox.checked = Boolean(templateMeta && templateMeta.enable_import_excel);
        }
    }

    const TEMPLATES_API = cfg.urls.adminBase;

    async function prefillDataOwnerFromTemplate(templateId) {
        // Runs even without a data-owner field on this form: the fetched template
        // metadata also drives syncGenericExcelDefaults (Export/Import Excel, PDF).
        if (!templateId) return;
        try {
            const resp = await fetch(cfg.urls.templateOwnedByBase + '/' + templateId + '/owned-by', {
                headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }
            });
            if (!resp.ok) return;
            const data = await resp.json();
            syncGenericExcelDefaults(data);
            if (dataOwnerSelect && data && data.owned_by_user_id) {
                // Only pre-fill if data owner is not already set
                if (!dataOwnerSelect.value || dataOwnerSelect.value === '') {
                    dataOwnerSelect.value = data.owned_by_user_id;
                }
            }
        } catch (e) {
            // Non-critical: silently ignore if API fails
        }
    }

    // On template change (new assignment form)
    templateSelect.addEventListener('change', function () {
        prefillDataOwnerFromTemplate(this.value);
    });

    // Auto-trigger on page load for new assignments with a pre-selected template: keeps
    // Excel/PDF defaults in sync regardless of whether a data-owner field is present.
    if (!cfg.assignmentId) {
        if (templateSelect.value) {
            prefillDataOwnerFromTemplate(templateSelect.value);
        }
    }
})();

(function initSubmissionReviewRecipientPicker() {
    var reviewCfg = cfg.submissionReviewRecipient || {};
    var searchInput = document.getElementById('submission-review-user-search');
    var resultsBox = document.getElementById('submission-review-user-results');
    var selectedWrap = document.getElementById('submission-review-selected-users');
    var hiddenInput = document.getElementById('submission_review_recipient_user_ids');
    var picker = document.getElementById('submission-review-user-picker');
    if (!searchInput || !resultsBox || !selectedWrap || !hiddenInput || !picker) {
        return;
    }

    var searchUrl = (cfg.urls && cfg.urls.reviewRecipientSearch) || '';
    var modeRadios = document.querySelectorAll('input[name="submission_review_recipient_mode"]');
    var searchTimer = null;
    var selectedUsers = Array.isArray(reviewCfg.users) ? reviewCfg.users.slice() : [];

    function currentMode() {
        var checked = document.querySelector('input[name="submission_review_recipient_mode"]:checked');
        return checked ? checked.value : 'fds_member';
    }

    function togglePickerVisibility() {
        var show = currentMode() === 'specific_admin';
        picker.classList.toggle('hidden', !show);
        if (!show) {
            resultsBox.classList.add('hidden');
        }
    }

    function isSelected(userId) {
        return selectedUsers.some(function (user) {
            return String(user.id) === String(userId);
        });
    }

    function syncHiddenInput() {
        hiddenInput.value = selectedUsers.map(function (user) {
            return String(user.id);
        }).join(',');
    }

    function removeSelectedUser(userId) {
        selectedUsers = selectedUsers.filter(function (user) {
            return String(user.id) !== String(userId);
        });
        renderSelectedUsers();
    }

    function renderSelectedUsers() {
        selectedWrap.innerHTML = '';
        syncHiddenInput();
        if (!selectedUsers.length) {
            return;
        }
        selectedUsers.forEach(function (user) {
            var chip = document.createElement('div');
            chip.className = 'inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-blue-50 border border-blue-200 text-sm text-gray-800';
            chip.innerHTML = '<span><strong>' + (user.name || user.email) + '</strong>'
                + (user.email ? ' <span class="text-gray-500">(' + user.email + ')</span>' : '')
                + '</span>';
            var removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.className = 'text-red-600 hover:text-red-800 text-xs font-medium';
            removeBtn.textContent = (cfg.t && cfg.t.clearReviewer) || 'Remove';
            removeBtn.addEventListener('click', function () {
                removeSelectedUser(user.id);
            });
            chip.appendChild(removeBtn);
            selectedWrap.appendChild(chip);
        });
    }

    function hideResults() {
        resultsBox.classList.add('hidden');
        resultsBox.innerHTML = '';
    }

    function renderResults(users) {
        resultsBox.innerHTML = '';
        var availableUsers = (users || []).filter(function (user) {
            return !isSelected(user.id);
        });
        if (!availableUsers.length) {
            var empty = document.createElement('div');
            empty.className = 'p-3 text-sm text-gray-500';
            empty.textContent = (cfg.t && cfg.t.noUsersFound) || 'No users found.';
            resultsBox.appendChild(empty);
            resultsBox.classList.remove('hidden');
            return;
        }
        availableUsers.forEach(function (user) {
            var row = document.createElement('button');
            row.type = 'button';
            row.className = 'w-full text-left p-3 hover:bg-gray-100 border-b border-gray-200 last:border-b-0';
            row.innerHTML = '<div class="text-sm font-medium text-gray-900">' + (user.name || user.email) + '</div>'
                + '<div class="text-xs text-gray-500">' + user.email + '</div>';
            row.addEventListener('click', function () {
                if (!isSelected(user.id)) {
                    selectedUsers.push(user);
                    renderSelectedUsers();
                }
                searchInput.value = '';
                hideResults();
            });
            resultsBox.appendChild(row);
        });
        resultsBox.classList.remove('hidden');
    }

    function searchUsers(query) {
        if (!searchUrl) {
            return;
        }
        fetch(searchUrl + '?q=' + encodeURIComponent(query), {
            headers: { 'Accept': 'application/json' }
        })
            .then(function (resp) { return resp.json(); })
            .then(function (data) {
                renderResults((data && data.users) || []);
            })
            .catch(function () {
                hideResults();
            });
    }

    modeRadios.forEach(function (radio) {
        radio.addEventListener('change', togglePickerVisibility);
    });

    searchInput.addEventListener('input', function () {
        var query = (searchInput.value || '').trim();
        clearTimeout(searchTimer);
        if (query.length < 2) {
            hideResults();
            return;
        }
        searchTimer = setTimeout(function () {
            searchUsers(query);
        }, 250);
    });

    document.addEventListener('click', function (evt) {
        if (!picker.contains(evt.target)) {
            hideResults();
        }
    });

    togglePickerVisibility();
    renderSelectedUsers();
})();
}());