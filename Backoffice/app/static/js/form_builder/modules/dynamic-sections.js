// dynamic-sections.js - All builder-side logic for Dynamic Indicator sections
// Covers: filter management, live indicator count, auto-save, section-type UI toggles, etc.

// Utils is available globally from utils.js
import { DataManager } from './data-manager.js';
import { CsrfHandler } from './csrf-handler.js';

export const DynamicSections = {
    indicatorFieldsConfig: {},

    init() {
        Utils.setDebugModule('dynamic-sections');
        this.indicatorFieldsConfig = DataManager.getData('indicatorFieldsConfig') || {};
        if (Object.keys(this.indicatorFieldsConfig).length === 0) {
            Utils.debugLog('[DynamicSections] No indicator field config found – skipping initialisation.');
            return;
        }

        this.initializeExistingFilters();
        this.setupAddFilterButtons();
        this.setupSaveButtons();
        this.setupSummaryListeners();
        this.setupToggleHeaders();
        this.setupFilterValueMenusCloseOnOutsideClick();
        Utils.debugLog('[DynamicSections] Initialised');
    },


    /***********************
     * INITIAL RENDERING  *
     ***********************/
    initializeExistingFilters() {
        const sectionsWithItems = DataManager.getData('sectionsWithItems') || [];
        document.querySelectorAll('[id^="filters-container-"]').forEach(container => {
            const sectionId = container.id.split('-').pop();
            container.replaceChildren();
            const sectionData = sectionsWithItems.find(s => (s.id ?? s.section_id) == sectionId);
            if (sectionData && Array.isArray(sectionData.existing_filters)) {
                sectionData.existing_filters.forEach(filterData => {
                    const row = this.createFilterRow(sectionId, filterData);
                    container.appendChild(row);
                });
            }
            this.updateIndicatorCountDisplay(sectionId);
        });
    },

    /***********************
     * FILTER ROW HANDLING *
     ***********************/
    createFilterRow(sectionId, filterData = null) {
        const existingFilters = document.querySelectorAll(`[name="filter_field_${sectionId}[]"]`);
        const filterIndex = existingFilters.length;
        const filterRow = document.createElement('div');
        filterRow.className = 'filter-row flex items-center gap-2 p-2 border border-gray-200 rounded bg-gray-50';
        filterRow.dataset.filterIndex = filterIndex;

        // Field select
        const fieldSelect = document.createElement('select');
        fieldSelect.name = `filter_field_${sectionId}[]`;
        fieldSelect.className = 'filter-field-select bg-white border border-gray-300 rounded-md px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 w-28';

        const defaultOption = document.createElement('option');
        defaultOption.value = '';
        defaultOption.textContent = 'Select Field';
        fieldSelect.appendChild(defaultOption);

        Object.keys(this.indicatorFieldsConfig).forEach(key => {
            const opt = document.createElement('option');
            opt.value = key;
            opt.textContent = this.indicatorFieldsConfig[key].label;
            if (filterData && filterData.field === key) opt.selected = true;
            fieldSelect.appendChild(opt);
        });

        // Values container
        const valuesContainer = document.createElement('div');
        valuesContainer.className = 'filter-values-container flex-1';

        // Primary-only checkbox (only sector / subsector)
        const primaryOnlyContainer = document.createElement('div');
        primaryOnlyContainer.className = 'primary-only-container flex items-center ml-2 hidden';

        const primaryCheckbox = document.createElement('input');
        primaryCheckbox.type = 'checkbox';
        primaryCheckbox.id = `primary_only_${sectionId}_${filterIndex}`;
        primaryCheckbox.name = `filter_primary_only_${sectionId}_${filterIndex}`;
        primaryCheckbox.value = '1';
        primaryCheckbox.className = 'h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500 mr-2';

        const primaryLabel = document.createElement('label');
        primaryLabel.htmlFor = primaryCheckbox.id;
        primaryLabel.className = 'text-sm text-blue-700 cursor-pointer whitespace-nowrap';
        primaryLabel.textContent = 'Primary only';

        primaryOnlyContainer.appendChild(primaryCheckbox);
        primaryOnlyContainer.appendChild(primaryLabel);

        // Remove button
        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'remove-filter-btn text-red-600 hover:text-red-800 p-1 flex-shrink-0';
        removeBtn.replaceChildren();
        {
            const icon = document.createElement('i');
            icon.className = 'fas fa-trash w-4 h-4';
            removeBtn.appendChild(icon);
        }

        // Listeners
        fieldSelect.addEventListener('change', () => {
            const selectedField = fieldSelect.value;
            if (['sector', 'subsector'].includes(selectedField)) {
                primaryOnlyContainer.classList.remove('hidden');
                if (filterData && filterData.primary_only) primaryCheckbox.checked = true;
            } else {
                primaryOnlyContainer.classList.add('hidden');
                primaryCheckbox.checked = false;
            }
            this.updateFilterValues(sectionId, filterIndex, selectedField, valuesContainer, filterData);
            this.updateIndicatorCountDisplay(sectionId);
            this.triggerAutoSave(fieldSelect);
        });

        removeBtn.addEventListener('click', () => {
            // Capture form reference BEFORE removing the row
            const formRef = removeBtn.closest('.configure-dynamic-section-form');
            filterRow.remove();
            this.updateFilterIndices(sectionId);
            this.updateIndicatorCountDisplay(sectionId);
            // Mark dirty manually because removeBtn is no longer in DOM
            if (formRef) {
                const saveBtn = formRef.querySelector('.save-dynamic-config-btn');
                this.setBtnDisabled(saveBtn, false);
                Utils.debugLog('[DynamicSections] Filter row removed – Save enabled', formRef.id);
            }
        });

        primaryCheckbox.addEventListener('change', () => {
            this.updateIndicatorCountDisplay(sectionId);
            this.triggerAutoSave(primaryCheckbox);
        });

        // Assemble row
        filterRow.appendChild(fieldSelect);
        filterRow.appendChild(valuesContainer);
        filterRow.appendChild(primaryOnlyContainer);
        filterRow.appendChild(removeBtn);

        if (filterData && filterData.field) {
            if (['sector', 'subsector'].includes(filterData.field)) {
                primaryOnlyContainer.classList.remove('hidden');
                if (filterData.primary_only) primaryCheckbox.checked = true;
            }
            this.updateFilterValues(sectionId, filterIndex, filterData.field, valuesContainer, filterData);
        }

        return filterRow;
    },

    updateFilterIndices(sectionId) {
        document.querySelectorAll(`#filters-container-${sectionId} .filter-row`).forEach((row, idx) => {
            row.dataset.filterIndex = idx;
            row.querySelectorAll('input[name^="filter_values_"]').forEach(cb => {
                cb.name = `filter_values_${sectionId}_${idx}[]`;
            });
        });
    },

    updateFilterValues(sectionId, filterIndex, fieldKey, container, existingData = null) {
        container.replaceChildren();
        if (!fieldKey || !this.indicatorFieldsConfig[fieldKey]) return;

        const fieldConfig = this.indicatorFieldsConfig[fieldKey];
        const wrapper = document.createElement('div');
        wrapper.className = 'relative flex-1 min-w-0';

        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'w-full bg-white border border-gray-300 rounded-md px-2 py-1 text-left text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 hover:bg-gray-50';
        btn.textContent = 'Select values...';

        const menu = document.createElement('div');
        menu.className = 'filter-values-menu absolute top-full left-0 right-0 mt-1 bg-white border border-gray-300 rounded-md shadow-lg max-h-60 overflow-y-auto z-50 hidden';

        fieldConfig.values.forEach((valObj, idx) => {
            const row = document.createElement('div');
            row.className = 'flex items-center px-2 py-1 hover:bg-gray-50 cursor-pointer';

            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.id = `checkbox_${sectionId}_${filterIndex}_${idx}`;
            cb.name = `filter_values_${sectionId}_${filterIndex}[]`;
            cb.value = valObj.value;
            cb.className = 'h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500 mr-3';
            if (existingData && Array.isArray(existingData.values) && existingData.values.includes(valObj.value)) cb.checked = true;

            const label = document.createElement('label');
            label.htmlFor = cb.id;
            label.className = 'text-sm font-medium text-gray-900 cursor-pointer flex-1';
            label.textContent = valObj.label;

            row.appendChild(cb);
            row.appendChild(label);
            menu.appendChild(row);
        });

        const updateText = () => {
            const checked = menu.querySelectorAll('input:checked');
            btn.textContent = checked.length === 0 ? 'Select values...' : Array.from(checked).map(c => c.nextElementSibling.textContent).join(', ');
        };

        btn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            menu.classList.toggle('hidden');
            document.querySelectorAll('.filter-values-container .absolute').forEach(el => {
                if (el !== menu) el.classList.add('hidden');
            });
        });

        menu.addEventListener('change', () => {
            updateText();
            this.updateIndicatorCountDisplay(sectionId);
            this.triggerAutoSave(menu);
        });

        updateText();

        wrapper.appendChild(btn);
        wrapper.appendChild(menu);
        container.appendChild(wrapper);
    },

    /**
     * Close any open filter value menus when the user clicks outside the filter-values UI.
     * This is attached once globally to avoid one document click handler per filter row.
     */
    setupFilterValueMenusCloseOnOutsideClick() {
        if (this._filterValueMenuCloseHandlerAttached) return;
        this._filterValueMenuCloseHandlerAttached = true;

        document.addEventListener('click', (e) => {
            // If click is within any filter-values container, keep menus as-is.
            if (e.target && e.target.closest && e.target.closest('.filter-values-container')) {
                return;
            }
            document.querySelectorAll('.filter-values-menu:not(.hidden)').forEach(menu => {
                menu.classList.add('hidden');
            });
        });
    },

    /*********************
     * COUNTER & SAVE    *
     *********************/
    updateIndicatorCountDisplay(sectionId) {
        const display = document.getElementById(`indicator-count-display-${sectionId}`);
        if (!display) return;

        const filterRows = document.querySelectorAll(`#filters-container-${sectionId} .filter-row`);
        const activeFilters = [];
        filterRows.forEach(row => {
            const fieldSelect = row.querySelector(`select[name^="filter_field_${sectionId}"]`);
            const checked = row.querySelectorAll('input[type="checkbox"]:checked');
            if (fieldSelect && fieldSelect.value && checked.length > 0) {
                activeFilters.push({ field: fieldSelect.value, values: Array.from(checked).map(cb => cb.value) });
            }
        });

        if (activeFilters.length === 0) {
            display.replaceChildren();
            {
                const span = document.createElement('span');
                span.className = 'font-medium';
                span.textContent = 'All indicators from the bank will be included';
                display.appendChild(span);
            }
            return;
        }

        display.replaceChildren();
        {
            const span = document.createElement('span');
            span.className = 'font-medium';
            span.textContent = 'Calculating filtered indicators...';

            const meta = document.createElement('span');
            meta.className = 'text-gray-500 text-xs';
            const icon = document.createElement('i');
            icon.className = 'fas fa-spinner fa-spin';
            meta.appendChild(icon);

            display.append(span, document.createTextNode(' '), meta);
        }

        CsrfHandler.safeFetch('/admin/api/indicator-count', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filters: activeFilters })
        })
            .then(r => { if (!r.ok) throw (window.httpErrorSync && window.httpErrorSync(r)) || new Error(`HTTP ${r.status}`); return r.json(); })
            .then(d => {
                const count = d.count ?? 0;
                const plural = count === 1 ? 'indicator' : 'indicators';
                display.replaceChildren();
                {
                    const span = document.createElement('span');
                    span.className = 'font-medium';
                    span.textContent = `${count} filtered ${plural} will be included`;
                    display.appendChild(span);
                }
            })
            .catch(err => {
                console.error('[DynamicSections] indicator-count error', err);
                display.replaceChildren();
                {
                    const span = document.createElement('span');
                    span.className = 'font-medium text-red-600';
                    span.textContent = 'Error calculating filtered count';
                    const meta = document.createElement('span');
                    meta.className = 'text-gray-500 text-xs';
                    meta.textContent = `(${err?.message || ''})`;
                    display.append(span, document.createTextNode(' '), meta);
                }
            });
    },

    setupAddFilterButtons() {
        if (this._addFilterHandlerAttached) return;
        this._addFilterHandlerAttached = true;
        document.addEventListener('click', (e) => {
            const btn = e.target.closest('.add-filter-btn');
            if (!btn) return;
            const sectionId = btn.dataset.sectionId;
            const container = document.getElementById(`filters-container-${sectionId}`);
            if (!container) return;
            const row = this.createFilterRow(sectionId);
            container.appendChild(row);
            this.updateFilterIndices(sectionId);
            this.updateIndicatorCountDisplay(sectionId);
            this.triggerAutoSave(btn);
        });
    },

    setupSaveButtons() {
        document.querySelectorAll('.configure-dynamic-section-form').forEach(form => {
            if (form.dataset && form.dataset.dynamicSaveWired === 'true') {
                return;
            }
            if (form.dataset) form.dataset.dynamicSaveWired = 'true';
            // If template already has a save button, use it; else inject one after header row
            let saveBtn = form.querySelector('.save-dynamic-config-btn');
            if (!saveBtn) {
                saveBtn = document.createElement('button');
                saveBtn.type = 'button';
                saveBtn.className = 'save-dynamic-config-btn bg-indigo-600 hover:bg-indigo-700 text-white font-medium px-3 py-1 rounded text-xs disabled:opacity-50';
                saveBtn.textContent = 'Save';
                this.setBtnDisabled(saveBtn, true);
                Utils.debugLog('[DynamicSections] Injected Save button (new) for form', form.id);

                // Try to insert after the header div (.flex justify-between)
                const header = form.querySelector('.flex.items-center.justify-between');
                if (header) {
                    header.appendChild(saveBtn);
                } else {
                    form.prepend(saveBtn);
                }
            } else {
                // Ensure existing button starts disabled
                this.setBtnDisabled(saveBtn, true);
                Utils.debugLog('[DynamicSections] Found existing Save button; disabled it', saveBtn);
            }

            // Keep reference on form for debugging
            form._saveButton = saveBtn;

            // Enable on change within form
            form.addEventListener('change', () => {
                Utils.debugLog('[DynamicSections] Form change detected; enabling Save', form.id);
                this.setBtnDisabled(saveBtn, false);
            });

            saveBtn.addEventListener('click', () => {
                Utils.debugLog('[DynamicSections] Save clicked', form.id);
                this.setBtnDisabled(saveBtn, true);
                this.saveForm(form)
                    .catch(() => { this.setBtnDisabled(saveBtn, false); });
            });
        });
    },

    saveForm(form) {
        Utils.debugLog('[DynamicSections] Saving dynamic config via AJAX', form.id);

        const saveBtn = form.querySelector('.save-dynamic-config-btn');
        const originalText = saveBtn ? (saveBtn.textContent || 'Save') : 'Save';

        // Show loading state
        if (saveBtn) {
            saveBtn.disabled = true;
            saveBtn.textContent = 'Saving...';
        }

        const body = new FormData(form);

        return CsrfHandler.safeFetch(form.action, {
            method: 'POST',
            body,
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
            .then(async (resp) => {
                const ct = (resp.headers.get('content-type') || '').toLowerCase();
                const data = ct.includes('application/json') ? await resp.json() : null;

                if (!resp.ok) {
                    const msg = (data && (data.error || data.message)) ? (data.error || data.message) : `HTTP ${resp.status}`;
                    throw new Error(msg);
                }
                if (!data || data.success !== true) {
                    const msg = (data && (data.error || data.message)) ? (data.error || data.message) : 'Save failed';
                    throw new Error(msg);
                }

                try {
                    Utils.showSuccess(data.message || 'Saved');
                } catch (_e) { /* no-op */ }

                if (saveBtn) {
                    saveBtn.textContent = 'Saved';
                    // Keep it disabled until another change occurs.
                    this.setBtnDisabled(saveBtn, true);
                    setTimeout(() => {
                        // Only restore if it still shows "Saved" (avoid clobbering future saves)
                        if (saveBtn.textContent === 'Saved') {
                            saveBtn.textContent = originalText;
                        }
                    }, 1200);
                }

                return data;
            })
            .catch((err) => {
                console.error('[DynamicSections] Failed to save dynamic config', err);
                try {
                    Utils.showError(err?.message || 'Failed to save');
                } catch (_e) { /* no-op */ }
                // Re-enable so user can retry
                if (saveBtn) {
                    saveBtn.textContent = originalText;
                    this.setBtnDisabled(saveBtn, false);
                }
                throw err;
            });
    },

    triggerAutoSave(el) {
        const form = el.closest('.configure-dynamic-section-form');
        if (!form) return;
        const btn = form.querySelector('.save-dynamic-config-btn');
        if (btn) {
            Utils.debugLog('[DynamicSections] triggerAutoSave enabling Save for form', form.id);
            this.setBtnDisabled(btn, false);
        }
    },

    setBtnDisabled(btn, disabled = true) {
        if (!btn) return;
        if (disabled) {
            btn.setAttribute('disabled', '');
            btn.classList.add('opacity-50', 'cursor-not-allowed');
        } else {
            btn.removeAttribute('disabled');
            btn.classList.remove('opacity-50', 'cursor-not-allowed');
        }
    },

    debounce(fn, delay) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn.apply(this, a), delay); }; },

    /***********************
     * SUMMARY FUNCTIONALITY *
     ***********************/
    setupSummaryListeners() {
        // Safe to call multiple times; listeners are attached per element and aren't duplicated by idempotent wiring below.
        // Set up summary listeners for all existing dynamic config sections
        document.querySelectorAll('[id^="dynamic-indicators-config-"]').forEach(configElement => {
            const sectionId = configElement.id.replace('dynamic-indicators-config-', '');
            setupDynamicConfigSummaryListeners(sectionId);

            // Generate initial summary for collapsed sections
            const content = document.getElementById(`dynamic-config-content-${sectionId}`);
            const summary = document.getElementById(`dynamic-config-summary-${sectionId}`);
            if (content && summary && content.classList.contains('hidden')) {
                // Section is collapsed, show summary
                summary.classList.remove('hidden');
                updateDynamicConfigSummary(sectionId);
            }
        });
    },

    /**
     * Setup click handlers for dynamic config headers without using inline event handlers
     */
    setupToggleHeaders() {
        if (this._toggleHeaderHandlerAttached) return;
        this._toggleHeaderHandlerAttached = true;
        document.addEventListener('click', (e) => {
            const header = e.target.closest('.dynamic-config-header');
            if (!header) return;

            const sectionId = header.dataset.sectionId
                || (header.id && header.id.startsWith('dynamic-indicators-config-')
                    ? header.id.replace('dynamic-indicators-config-', '')
                    : null);

            if (!sectionId || typeof window.toggleDynamicConfig !== 'function') {
                return;
            }

            window.toggleDynamicConfig(sectionId);
        });
    }
};

// Global function for toggling dynamic config sections
window.toggleDynamicConfig = function(sectionId) {
    const content = document.getElementById(`dynamic-config-content-${sectionId}`);
    const icon = document.getElementById(`dynamic-config-icon-${sectionId}`);
    const summary = document.getElementById(`dynamic-config-summary-${sectionId}`);

    if (!content || !icon) return;

    if (content.classList.contains('hidden')) {
        // Expand
        content.classList.remove('hidden');
        icon.classList.remove('fa-chevron-down');
        icon.classList.add('fa-chevron-up');
        // Hide summary when expanded
        if (summary) {
            summary.classList.add('hidden');
        }
    } else {
        // Collapse
        content.classList.add('hidden');
        icon.classList.remove('fa-chevron-up');
        icon.classList.add('fa-chevron-down');
        // Show summary when collapsed
        if (summary) {
            summary.classList.remove('hidden');
            updateDynamicConfigSummary(sectionId);
        }
    }
};

// Function to generate and update the summary for dynamic config sections
function updateDynamicConfigSummary(sectionId) {
    const summaryElement = document.getElementById(`dynamic-config-summary-${sectionId}`);
    if (!summaryElement) return;

    const maxIndicators = document.getElementById(`max_dynamic_indicators_${sectionId}`);
    const addNote = document.getElementById(`add_indicator_note_${sectionId}`);
    const filtersContainer = document.getElementById(`filters-container-${sectionId}`);

    let summaryParts = [];

    // Max indicators
    if (maxIndicators && maxIndicators.value) {
        summaryParts.push(`Max: ${maxIndicators.value}`);
    } else {
        summaryParts.push('Max: No limit');
    }

    // Filters count
    if (filtersContainer) {
        const filterRows = filtersContainer.querySelectorAll('.filter-row');
        if (filterRows.length > 0) {
            summaryParts.push(`${filterRows.length} filter${filterRows.length !== 1 ? 's' : ''}`);
        } else {
            summaryParts.push('No filters');
        }
    }

    // Data availability options
    const dataNotAvailable = document.querySelector(`input[name="allow_data_not_available"]`);
    const notApplicable = document.querySelector(`input[name="allow_not_applicable"]`);
    const dataOptions = [];
    if (dataNotAvailable && dataNotAvailable.checked) dataOptions.push('Data not available');
    if (notApplicable && notApplicable.checked) dataOptions.push('Not applicable');
    if (dataOptions.length > 0) {
        summaryParts.push(`Options: ${dataOptions.join(', ')}`);
    }

    // Disaggregation options
    const disaggCheckboxes = document.querySelectorAll(`input[name="allowed_disaggregation_options"]:checked`);
    if (disaggCheckboxes.length > 0) {
        const disaggLabels = Array.from(disaggCheckboxes).map(cb => {
            const label = document.querySelector(`label:has(input[value="${cb.value}"])`);
            return label ? label.textContent.trim() : cb.value;
        });
        summaryParts.push(`Disaggregation: ${disaggLabels.join(', ')}`);
    }

    // Display filters
    const displayFilterCheckboxes = document.querySelectorAll(`input[name="data_entry_display_filters"]:checked`);
    if (displayFilterCheckboxes.length > 0) {
        const displayFilterLabels = Array.from(displayFilterCheckboxes).map(cb => {
            const label = document.querySelector(`label:has(input[value="${cb.value}"])`);
            return label ? label.textContent.trim() : cb.value;
        });
        summaryParts.push(`Display filters: ${displayFilterLabels.join(', ')}`);
    }

    // Update summary text
    summaryElement.textContent = summaryParts.join(' • ');
}

// Function to set up summary update listeners for a dynamic config section
function setupDynamicConfigSummaryListeners(sectionId) {
    const configContainer = document.getElementById(`dynamic-indicators-config-${sectionId}`);
    if (!configContainer) return;

    // Listen for changes to form inputs that affect the summary
    const inputsToWatch = [
        `max_dynamic_indicators_${sectionId}`,
        `add_indicator_note_${sectionId}`
    ];

    inputsToWatch.forEach(inputId => {
        const input = document.getElementById(inputId);
        if (input) {
            input.addEventListener('input', () => {
                const summary = document.getElementById(`dynamic-config-summary-${sectionId}`);
                if (summary && !summary.classList.contains('hidden')) {
                    updateDynamicConfigSummary(sectionId);
                }
            });
        }
    });

    // Listen for changes to checkboxes
    const checkboxesToWatch = [
        'allow_data_not_available',
        'allow_not_applicable',
        'allowed_disaggregation_options',
        'data_entry_display_filters'
    ];

    checkboxesToWatch.forEach(name => {
        const checkboxes = configContainer.querySelectorAll(`input[name="${name}"]`);
        checkboxes.forEach(checkbox => {
            checkbox.addEventListener('change', () => {
                const summary = document.getElementById(`dynamic-config-summary-${sectionId}`);
                if (summary && !summary.classList.contains('hidden')) {
                    updateDynamicConfigSummary(sectionId);
                }
            });
        });
    });

    // Listen for filter changes (add/remove filters)
    const filtersContainer = document.getElementById(`filters-container-${sectionId}`);
    if (filtersContainer) {
        // Use MutationObserver to watch for filter additions/removals
        const observer = new MutationObserver(() => {
            const summary = document.getElementById(`dynamic-config-summary-${sectionId}`);
            if (summary && !summary.classList.contains('hidden')) {
                updateDynamicConfigSummary(sectionId);
            }
        });

        observer.observe(filtersContainer, {
            childList: true,
            subtree: true
        });
    }
}
