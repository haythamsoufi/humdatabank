// Matrix item logic extracted from item-modal.js
// Depends on global Utils and standard DOM APIs

const truthyMatrixValues = new Set(['true', '1', 'yes', 'on']);
const falsyMatrixValues = new Set(['false', '0', 'no', 'off', '']);

const isTruthyMatrixValue = (value) => {
    if (typeof value === 'boolean') return value;
    if (typeof value === 'number') return value !== 0;
    if (typeof value === 'string') {
        const normalized = value.trim().toLowerCase();
        if (truthyMatrixValues.has(normalized)) return true;
        if (falsyMatrixValues.has(normalized)) return false;
    }
    if (value === null || value === undefined) return false;
    return Boolean(value);
};

const shouldCheckMatrixCheckbox = (configValue, optionValue) => {
    if (Array.isArray(configValue)) {
        return configValue.some(val => String(val) === String(optionValue));
    }
    if (typeof configValue === 'string') {
        const normalized = configValue.trim().toLowerCase();
        if (optionValue !== undefined && optionValue !== null && optionValue !== '') {
            if (String(configValue) === String(optionValue)) {
                return true;
            }
            if (truthyMatrixValues.has(normalized)) return true;
            if (falsyMatrixValues.has(normalized)) return false;
            return false;
        }
        if (truthyMatrixValues.has(normalized)) return true;
        if (falsyMatrixValues.has(normalized)) return false;
    }
    return isTruthyMatrixValue(configValue);
};

export const MatrixItem = {
    /**
     * Sanitize server-provided HTML before inserting into the DOM.
     * - Removes <script> and other active content
     * - Strips inline event handler attributes (on*)
     * - Strips dangerous URL schemes (javascript:, data:, vbscript:, file:, about:)
     *
     * NOTE: Prefer DOM construction whenever possible; this is a defensive fallback
     * for backend-provided configuration UIs.
     */
    setSanitizedHtml(container, html) {
        if (!container) return;
        container.replaceChildren();

        if (typeof html !== 'string' || !html.trim()) return;

        // Parse HTML into a detached document without assigning innerHTML
        const doc = new DOMParser().parseFromString(html, 'text/html');
        const root = doc.body;
        if (!root) return;

        // Remove script-like elements
        root.querySelectorAll('script, iframe, object, embed').forEach((el) => el.remove());

        // Strip dangerous attributes
        root.querySelectorAll('*').forEach((el) => {
            // Remove inline event handlers
            [...el.attributes].forEach((attr) => {
                const name = attr.name.toLowerCase();
                const value = String(attr.value || '').trim();
                const lower = value.toLowerCase();

                if (name.startsWith('on')) {
                    el.removeAttribute(attr.name);
                    return;
                }

                // Remove dangerous URLs in common URL-bearing attributes
                if (name === 'href' || name === 'src' || name === 'xlink:href' || name === 'formaction') {
                    if (
                        lower.startsWith('javascript:') ||
                        lower.startsWith('data:') ||
                        lower.startsWith('vbscript:') ||
                        lower.startsWith('file:') ||
                        lower.startsWith('about:')
                    ) {
                        el.removeAttribute(attr.name);
                    }
                }
            });
        });

        const fragment = document.createDocumentFragment();
        while (root.firstChild) fragment.appendChild(root.firstChild);
        container.appendChild(fragment);
    },
    setup(modalElement) {
        this.setupRowModeListeners(modalElement);
        this.initializeDefault(modalElement);
        this.setupEventListeners(modalElement);
        this.setupDisplayOptions(modalElement);
        this.setupListLibrary(modalElement);
        this.showVariableOptionsForAllColumns(modalElement);
    },

    teardown(modalElement) {
        if (!modalElement) return;
        if (modalElement._matrixChangeHandler) {
            document.removeEventListener('change', modalElement._matrixChangeHandler);
            modalElement._matrixChangeHandler = null;
        }
        if (modalElement._matrixClickHandler) {
            document.removeEventListener('click', modalElement._matrixClickHandler);
            modalElement._matrixClickHandler = null;
        }
    },

    initializeDefault(modalElement) {
        const rowsContainer = Utils.getElementById('matrix-rows-container');
        const columnsContainer = Utils.getElementById('matrix-columns-container');
        if (!rowsContainer || !columnsContainer) {
            console.error('Matrix containers not found');
            return;
        }
        if (rowsContainer.children.length === 0) {
            this.addRow(modalElement, 'Row 1');
            this.addRow(modalElement, 'Row 2');
        }
        if (columnsContainer.children.length === 0) {
            this.addColumn(modalElement, 'Column 1', 'number');
            this.addColumn(modalElement, 'Column 2', 'number');
        }
    },

    showVariableOptionsForAllColumns(modalElement) {
        // Check if template has variables or built-in metadata tokens
        const templateVariables = window.templateVariables || {};
        const metadata = Array.isArray(window.builtInMetadataVariables) ? window.builtInMetadataVariables : [];
        const hasVariables = Object.keys(templateVariables).length > 0 || metadata.length > 0;

        if (!hasVariables) {
            return; // No variables, so don't show options
        }

        // Show variable options for all existing columns
        const columnsContainer = Utils.getElementById('matrix-columns-container');
        if (columnsContainer) {
            columnsContainer.querySelectorAll('.matrix-column').forEach(columnDiv => {
                const variableOptions = columnDiv.querySelector('.column-variable-options');
                if (variableOptions) {
                    variableOptions.style.display = 'flex';
                    variableOptions.classList.remove('hidden');
                }
            });
        }
    },

    setupEventListeners(modalElement) {
        // Remove existing handlers if present
        if (modalElement._matrixChangeHandler) {
            document.removeEventListener('change', modalElement._matrixChangeHandler);
            document.removeEventListener('click', modalElement._matrixClickHandler);
        }

        modalElement._matrixChangeHandler = (e) => {
            if (
                e.target.classList.contains('row-text') ||
                e.target.classList.contains('column-text') ||
                e.target.classList.contains('column-type') ||
                e.target.classList.contains('column-variable-select') ||
                e.target.classList.contains('column-is-variable')
            ) {
                // Handle "Is Variable" checkbox change to show/hide variable selector and save/readonly options
                if (e.target.classList.contains('column-is-variable')) {
                    const columnDiv = e.target.closest('.matrix-column');
                    if (columnDiv) {
                        const variableSelect = columnDiv.querySelector('.column-variable-select');
                        const saveValueLabel = columnDiv.querySelector('.column-variable-save-value-label');
                        const readonlyLabel = columnDiv.querySelector('.column-variable-readonly-label');

                        if (e.target.checked) {
                            if (variableSelect) {
                                variableSelect.style.display = '';
                                variableSelect.classList.remove('hidden');
                                // Populate variable options if not already populated
                                if (variableSelect.options.length <= 1) {
                                    this.populateVariableOptions(variableSelect, modalElement);
                                }
                            }
                            // Show save value and readonly checkboxes
                            if (saveValueLabel) {
                                saveValueLabel.style.display = 'flex';
                            }
                            if (readonlyLabel) {
                                readonlyLabel.style.display = 'flex';
                            }
                        } else {
                            if (variableSelect) {
                                variableSelect.style.display = 'none';
                                variableSelect.classList.add('hidden');
                            }
                            // Hide save value and readonly checkboxes
                            if (saveValueLabel) {
                                saveValueLabel.style.display = 'none';
                            }
                            if (readonlyLabel) {
                                readonlyLabel.style.display = 'none';
                            }
                        }
                    }
                }
                // Update auto-load visibility when column variable status changes
                if (e.target.classList.contains('column-is-variable')) {
                    this.updateAutoLoadVisibility(modalElement);
                }
                this.updateConfig(modalElement);
            }
        };

        modalElement._matrixClickHandler = (e) => {
            const target = e.target.closest('button');
            if (!target) return;


            if (target.id === 'add-matrix-row-btn') {
                e.preventDefault();
                this.addRow(modalElement);
                this.updateConfig(modalElement);
            } else if (target.classList.contains('remove-row-btn')) {
                e.preventDefault();
                this.removeRow(target);
                this.updateConfig(modalElement);
            } else if (target.classList.contains('move-row-up-btn')) {
                e.preventDefault();
                this.moveRow(target, 'up');
                this.updateConfig(modalElement);
            } else if (target.classList.contains('move-row-down-btn')) {
                e.preventDefault();
                this.moveRow(target, 'down');
                this.updateConfig(modalElement);
            } else if (target.id === 'add-matrix-column-btn') {
                e.preventDefault();
                this.addColumn(modalElement);
                this.updateConfig(modalElement);
            } else if (target.classList.contains('remove-column-btn')) {
                e.preventDefault();
                this.removeColumn(target);
                this.updateConfig(modalElement);
            } else if (target.classList.contains('move-column-up-btn')) {
                e.preventDefault();
                this.moveColumn(target, 'up');
                this.updateConfig(modalElement);
            } else if (target.classList.contains('move-column-down-btn')) {
                e.preventDefault();
                this.moveColumn(target, 'down');
                this.updateConfig(modalElement);
            }
        };

        document.addEventListener('change', modalElement._matrixChangeHandler);
        document.addEventListener('click', modalElement._matrixClickHandler);
    },

    addRow(modalElement, text = '') {
        const rowsContainer = Utils.getElementById('matrix-rows-container');
        const template = Utils.getElementById('matrix-row-template');
        if (!rowsContainer || !template) {
            console.error('Matrix row container or template not found');
            return;
        }
        const clone = template.content.cloneNode(true);
        const input = clone.querySelector('.row-text');
        if (input) input.value = text || '';
        rowsContainer.appendChild(clone);
    },

    addColumn(modalElement, text = '', type = 'number', isVariable = false, variableName = '', variableSaveValue = true, variableReadonly = true, nameTranslations = {}) {
        const columnsContainer = Utils.getElementById('matrix-columns-container');
        const template = Utils.getElementById('matrix-column-template');
        if (!columnsContainer || !template) {
            console.error('Matrix column container or template not found');
            return;
        }
        const clone = template.content.cloneNode(true);
        const input = clone.querySelector('.column-text');
        const translationsInput = clone.querySelector('.column-name-translations');
        const translateBtn = clone.querySelector('.matrix-column-translate-btn');
        const typeSelect = clone.querySelector('.column-type');
        const variableSelect = clone.querySelector('.column-variable-select');
        const variableOptions = clone.querySelector('.column-variable-options');
        const isVariableCheckbox = clone.querySelector('.column-is-variable');
        const saveValueCheckbox = clone.querySelector('.column-variable-save-value');
        const readonlyCheckbox = clone.querySelector('.column-variable-readonly');

        if (input) input.value = text || '';
        if (translationsInput) {
            try {
                const normalized = (nameTranslations && typeof nameTranslations === 'object') ? nameTranslations : {};
                translationsInput.value = JSON.stringify(normalized);
                const hasAny = Object.values(normalized).some(v => String(v || '').trim());
                if (translateBtn) {
                    if (hasAny) translateBtn.classList.add('text-green-600');
                    else translateBtn.classList.remove('text-green-600');
                }
            } catch (_e) {
                translationsInput.value = '{}';
            }
        }
        if (typeSelect) {
            // Set type (number or tick) - but don't use 'variable' as type anymore
            typeSelect.value = (type === 'variable') ? 'number' : (type || 'number');
        }

        // Check if template has variables defined
        const templateVariables = window.templateVariables || {};
        const metadata = Array.isArray(window.builtInMetadataVariables) ? window.builtInMetadataVariables : [];
        const hasVariables = Object.keys(templateVariables).length > 0 || metadata.length > 0;

        // Show/hide variable options based on whether template has variables
        if (variableOptions) {
            if (hasVariables) {
                variableOptions.style.display = 'flex';
                variableOptions.classList.remove('hidden');
            } else {
                variableOptions.style.display = 'none';
                variableOptions.classList.add('hidden');
            }
        }

        // Handle variable checkbox
        if (isVariableCheckbox) {
            isVariableCheckbox.checked = isVariable;
            // Show/hide variable selector and save/readonly options based on checkbox state
            const saveValueLabel = clone.querySelector('.column-variable-save-value-label');
            const readonlyLabel = clone.querySelector('.column-variable-readonly-label');

            if (isVariable) {
                if (variableSelect) {
                    variableSelect.style.display = '';
                    variableSelect.classList.remove('hidden');
                    this.populateVariableOptions(variableSelect, modalElement);
                    if (variableName) {
                        variableSelect.value = variableName;
                    }
                }
                // Show save value and readonly checkboxes
                if (saveValueLabel) {
                    saveValueLabel.style.display = 'flex';
                }
                if (readonlyLabel) {
                    readonlyLabel.style.display = 'flex';
                }
                if (saveValueCheckbox) {
                    saveValueCheckbox.checked = variableSaveValue !== false;
                }
                if (readonlyCheckbox) {
                    readonlyCheckbox.checked = variableReadonly !== false;
                }
            } else {
                if (variableSelect) {
                    variableSelect.style.display = 'none';
                    variableSelect.classList.add('hidden');
                }
                // Hide save value and readonly checkboxes
                if (saveValueLabel) {
                    saveValueLabel.style.display = 'none';
                }
                if (readonlyLabel) {
                    readonlyLabel.style.display = 'none';
                }
            }
        }
        columnsContainer.appendChild(clone);
        // Bind custom tooltips on newly added column (e.g. Save value ?)
        if (typeof window.initTooltips === 'function') {
            window.initTooltips();
        }
        // Update auto-load visibility after adding column
        this.updateAutoLoadVisibility(modalElement);
    },

    populateVariableOptions(variableSelect, modalElement) {
        // Get template variables from global scope (set in form_builder.html)
        const templateVariables = window.templateVariables || {};
        const metadata = Array.isArray(window.builtInMetadataVariables) ? window.builtInMetadataVariables : [];
        variableSelect.replaceChildren();
        {
            const placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.textContent = 'Select Variable...';
            variableSelect.appendChild(placeholder);
        }

        // Metadata group (built-in tokens)
        if (metadata.length > 0) {
            const og = document.createElement('optgroup');
            og.label = 'Metadata';
            metadata.forEach((m) => {
                const key = String(m.key || '').trim();
                if (!key) return;
                const label = String(m.label || '').trim();
                const option = document.createElement('option');
                option.value = key;
                option.textContent = label ? `[${key}] — ${label}` : `[${key}]`;
                og.appendChild(option);
            });
            variableSelect.appendChild(og);
        }

        // Template variables group
        const variableNames = Object.keys(templateVariables);
        if (variableNames.length > 0) {
            const og = document.createElement('optgroup');
            og.label = 'Template Variables';
            variableNames.forEach((varName) => {
                const option = document.createElement('option');
                option.value = varName;
                option.textContent = `[${varName}]`;
                og.appendChild(option);
            });
            variableSelect.appendChild(og);
        }
    },

    removeRow(button) {
        const row = button.closest('.matrix-row');
        if (row) row.remove();
    },

    removeColumn(button) {
        const column = button.closest('.matrix-column');
        const modalElement = column?.closest('.modal') || document.querySelector('.item-modal');
        if (column) column.remove();
        // Update auto-load visibility after removing column
        if (modalElement) {
            this.updateAutoLoadVisibility(modalElement);
        }
    },

    moveRow(button, direction) {
        const row = button.closest('.matrix-row');
        const container = row ? row.parentElement : null;
        if (!row || !container) return;
        if (direction === 'up' && row.previousElementSibling) {
            container.insertBefore(row, row.previousElementSibling);
        } else if (direction === 'down' && row.nextElementSibling) {
            container.insertBefore(row.nextElementSibling, row);
        }
    },

    moveColumn(button, direction) {
        const column = button.closest('.matrix-column');
        const container = column ? column.parentElement : null;
        if (!column || !container) return;
        if (direction === 'up' && column.previousElementSibling) {
            container.insertBefore(column, column.previousElementSibling);
        } else if (direction === 'down' && column.nextElementSibling) {
            container.insertBefore(column.nextElementSibling, column);
        }
    },

    setupDisplayOptions(modalElement) {
        const rowTotalsCheckbox = Utils.getElementById('matrix-show-row-totals');
        const columnTotalsCheckbox = Utils.getElementById('matrix-show-column-totals');
        const autoLoadCheckbox = Utils.getElementById('matrix-auto-load-entities');
        const autoLoadWrapper = Utils.getElementById('matrix-auto-load-entities-wrapper');
        const highlightManualRowsCheckbox = Utils.getElementById('matrix-highlight-manual-rows');
        const legendTextInput = Utils.getElementById('matrix-legend-text');
        const legendTextWrapper = Utils.getElementById('matrix-legend-text-wrapper');
        const legendHideBtn = Utils.getElementById('matrix-legend-hide-btn');
        const legendHideInput = Utils.getElementById('matrix-legend-hide');

        if (rowTotalsCheckbox) {
            rowTotalsCheckbox.addEventListener('change', () => this.updateConfig(modalElement));
        }
        if (columnTotalsCheckbox) {
            columnTotalsCheckbox.addEventListener('change', () => this.updateConfig(modalElement));
        }
        if (autoLoadCheckbox) {
            autoLoadCheckbox.addEventListener('change', () => this.updateConfig(modalElement));
        }
        if (highlightManualRowsCheckbox) {
            highlightManualRowsCheckbox.addEventListener('change', () => {
                // Show/hide legend text input based on checkbox state
                this.updateLegendTextVisibility(modalElement);
                this.updateConfig(modalElement);
            });
        }
        if (legendTextInput) {
            legendTextInput.addEventListener('input', () => this.updateConfig(modalElement));
            legendTextInput.addEventListener('change', () => this.updateConfig(modalElement));
        }
        if (legendHideBtn) {
            legendHideBtn.addEventListener('click', () => {
                this.toggleLegendHide(modalElement);
            });
        }

        // Check if any column is a variable and show/hide auto-load checkbox
        this.updateAutoLoadVisibility(modalElement);

        // Update legend text visibility on initial load
        this.updateLegendTextVisibility(modalElement);

        // Initialize legend hide button state
        this.initializeLegendHideButton(modalElement);
    },

    /**
     * Initialize legend hide button state on load
     */
    initializeLegendHideButton(modalElement) {
        const legendHideInput = Utils.getElementById('matrix-legend-hide');
        const legendTextInput = Utils.getElementById('matrix-legend-text');

        if (legendHideInput) {
            const isHidden = legendHideInput.value === 'true';

            // Update text input state
            if (legendTextInput) {
                if (isHidden) {
                    legendTextInput.disabled = true;
                    legendTextInput.classList.add('bg-gray-100', 'cursor-not-allowed');
                } else {
                    legendTextInput.disabled = false;
                    legendTextInput.classList.remove('bg-gray-100', 'cursor-not-allowed');
                }
            }
        }
    },

    /**
     * Show/hide legend text input based on highlight manual rows checkbox
     */
    updateLegendTextVisibility(modalElement) {
        const highlightManualRowsCheckbox = Utils.getElementById('matrix-highlight-manual-rows');
        const legendTextWrapper = Utils.getElementById('matrix-legend-text-wrapper');

        if (highlightManualRowsCheckbox && legendTextWrapper) {
            if (highlightManualRowsCheckbox.checked) {
                legendTextWrapper.classList.remove('hidden');
            } else {
                legendTextWrapper.classList.add('hidden');
            }
        }
    },

    /**
     * Toggle legend hide/show state
     */
    toggleLegendHide(modalElement) {
        const legendHideBtn = Utils.getElementById('matrix-legend-hide-btn');
        const legendHideInput = Utils.getElementById('matrix-legend-hide');
        const legendTextInput = Utils.getElementById('matrix-legend-text');

        if (!legendHideBtn || !legendHideInput) return;

        const isHidden = legendHideInput.value === 'true';
        const newState = !isHidden;
        legendHideInput.value = String(newState);

        // Update button icon, text, and title
        const icon = legendHideBtn.querySelector('i');
        const textSpan = legendHideBtn.querySelector('span');

        if (newState) {
            // Legend is hidden
            if (icon) {
                icon.className = 'fas fa-eye-slash w-4 h-4 mr-1';
            }
            if (textSpan) {
                textSpan.textContent = 'Legend hidden';
            } else {
                const span = document.createElement('span');
                span.textContent = 'Legend hidden';
                legendHideBtn.appendChild(span);
            }
            legendHideBtn.title = 'Legend is hidden - click to show';
            legendHideBtn.classList.remove('text-gray-600');
            legendHideBtn.classList.add('text-gray-500');

            // Grey out the text input
            if (legendTextInput) {
                legendTextInput.disabled = true;
                legendTextInput.classList.add('bg-gray-100', 'cursor-not-allowed');
            }
        } else {
            // Legend is shown
            if (icon) {
                icon.className = 'fas fa-eye w-4 h-4 mr-1';
            }
            if (textSpan) {
                textSpan.textContent = 'Legend shown';
            } else {
                const span = document.createElement('span');
                span.textContent = 'Legend shown';
                legendHideBtn.appendChild(span);
            }
            legendHideBtn.title = 'Legend is shown - click to hide';
            legendHideBtn.classList.remove('text-gray-500');
            legendHideBtn.classList.add('text-gray-600');

            // Enable the text input
            if (legendTextInput) {
                legendTextInput.disabled = false;
                legendTextInput.classList.remove('bg-gray-100', 'cursor-not-allowed');
            }
        }

        this.updateConfig(modalElement);
    },

    /**
     * Check if at least one column is a variable and show/hide auto-load checkbox
     */
    updateAutoLoadVisibility(modalElement) {
        const autoLoadWrapper = Utils.getElementById('matrix-auto-load-entities-wrapper');
        if (!autoLoadWrapper) return;

        const columnsContainer = Utils.getElementById('matrix-columns-container');
        if (!columnsContainer) {
            autoLoadWrapper.classList.add('hidden');
            return;
        }

        // Check if at least one column has is_variable checked
        const columns = columnsContainer.querySelectorAll('.matrix-column');
        let hasVariableColumn = false;

        columns.forEach(columnDiv => {
            const isVariableCheckbox = columnDiv.querySelector('.column-is-variable');
            if (isVariableCheckbox && isVariableCheckbox.checked) {
                hasVariableColumn = true;
            }
        });

        // Show/hide the auto-load checkbox based on whether any column is a variable
        if (hasVariableColumn) {
            autoLoadWrapper.classList.remove('hidden');
        } else {
            autoLoadWrapper.classList.add('hidden');
            // Also uncheck the checkbox if hidden
            const autoLoadCheckbox = Utils.getElementById('matrix-auto-load-entities');
            if (autoLoadCheckbox) {
                autoLoadCheckbox.checked = false;
            }
        }
    },

    setupRowModeListeners(modalElement) {
        const rowModeRadios = modalElement.querySelectorAll('input[name="matrix_row_mode"]');
        const manualSection = modalElement.querySelector('#matrix-manual-rows-section');
        const listLibrarySection = modalElement.querySelector('#matrix-list-library-section');
        const updateRowModeVisibility = () => {
            const selectedMode = modalElement.querySelector('input[name="matrix_row_mode"]:checked')?.value;
            if (selectedMode === 'manual') {
                Utils.showElement(manualSection);
                Utils.hideElement(listLibrarySection);
            } else if (selectedMode === 'list_library') {
                Utils.hideElement(manualSection);
                Utils.showElement(listLibrarySection);
            }
            this.updateConfig(modalElement);
        };
        rowModeRadios.forEach(radio => {
            radio.addEventListener('change', updateRowModeVisibility);
        });
        updateRowModeVisibility();
    },

    setupListLibrary(modalElement) {
        const listSelect = modalElement.querySelector('#matrix-list-select');
        const displayColumnSelect = modalElement.querySelector('#matrix-list-display-column');
        const groupBySelect = modalElement.querySelector('#matrix-group-by-column');
        const groupDropdownEnabled = modalElement.querySelector('#matrix-group-dropdown-enabled');
        const groupTableEnabled = modalElement.querySelector('#matrix-group-table-enabled');
        const addFilterBtn = modalElement.querySelector('#matrix-list-add-filter-btn');
        if (listSelect && displayColumnSelect) {
            listSelect.addEventListener('change', (e) => {
                this.handleListSelection(modalElement, e.target.value);
            });
        }
        if (displayColumnSelect) {
            displayColumnSelect.addEventListener('change', () => this.updateConfig(modalElement));
        }
        if (groupBySelect) {
            groupBySelect.addEventListener('change', () => {
                this.updateGroupingControlsVisibility(modalElement);
                this.updateConfig(modalElement);
            });
        }
        if (groupDropdownEnabled) {
            groupDropdownEnabled.addEventListener('change', () => this.updateConfig(modalElement));
        }
        if (groupTableEnabled) {
            groupTableEnabled.addEventListener('change', () => this.updateConfig(modalElement));
        }
        if (addFilterBtn) {
            addFilterBtn.addEventListener('click', () => {
                this.addListFilter(modalElement);
            });
        }
    },

    async handleListSelection(modalElement, listId) {
        const displayColumnWrapper = modalElement.querySelector('#matrix-display-column-wrapper');
        const displayColumnSelect = modalElement.querySelector('#matrix-list-display-column');
        const configContainer = modalElement.querySelector('#matrix-plugin-config-container');

        if (!listId) {
            Utils.hideElement(displayColumnWrapper);
            const groupByWrapper = modalElement.querySelector('#matrix-group-by-wrapper');
            if (groupByWrapper) Utils.hideElement(groupByWrapper);
            this.updateGroupingControlsVisibility(modalElement);
            if (configContainer) {
                configContainer.replaceChildren();
                configContainer.style.display = 'none';
            }
            return;
        }
        const selectedOption = modalElement.querySelector(`#matrix-list-select option[value="${listId}"]`);
        if (!selectedOption) return;
        const columnsConfig = JSON.parse(selectedOption.dataset.columns || '[]');
        displayColumnSelect.replaceChildren();
        {
            const placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.textContent = 'Select Column...';
            displayColumnSelect.appendChild(placeholder);
        }
        columnsConfig.forEach(column => {
            // Skip name_translations field
            if (column.name === 'name_translations') {
                return;
            }

            const option = document.createElement('option');
            option.value = column.name;

            // Check if column is multilingual (has name_translations)
            const isMultilingual = column.multilingual === true ||
                                  (column.name === 'name' &&
                                   (listId === 'country_map' ||
                                    listId === 'national_society'));

            // Create display text with translation icon if multilingual
            let displayText = column.label || column.name;
            if (isMultilingual) {
                // Use Unicode translation icon (🌐) with tooltip
                displayText = `${displayText} 🌐`;
                option.dataset.multilingual = 'true';
                option.title = 'This field supports multiple languages and will display in the user\'s selected language';
            }

            option.textContent = displayText;
            displayColumnSelect.appendChild(option);
        });
        Utils.showElement(displayColumnWrapper);

        // Populate group-by column dropdown with same columns
        const groupByWrapper = modalElement.querySelector('#matrix-group-by-wrapper');
        const groupBySelect = modalElement.querySelector('#matrix-group-by-column');
        if (groupBySelect && groupByWrapper) {
            groupBySelect.replaceChildren();
            const noGroup = document.createElement('option');
            noGroup.value = '';
            noGroup.textContent = 'No grouping';
            groupBySelect.appendChild(noGroup);
            columnsConfig.forEach(column => {
                if (column.name === 'name_translations') return;
                const opt = document.createElement('option');
                opt.value = column.name;
                opt.textContent = column.label || column.name;
                groupBySelect.appendChild(opt);
            });
            Utils.showElement(groupByWrapper);
            this.updateGroupingControlsVisibility(modalElement);
        }

        // Check if this lookup list has configuration UI
        const hasConfigUI = selectedOption.dataset.hasConfigUi === 'true';
        if (hasConfigUI && configContainer) {
            try {
                // Get existing config from matrix config if editing
                const configInput = Utils.getElementById('item-matrix-config');
                let existingConfig = {};
                if (configInput && configInput.value) {
                    try {
                        const matrixConfig = JSON.parse(configInput.value);
                        existingConfig = matrixConfig.plugin_config || {};
                    } catch (e) {
                        // Ignore parse errors
                    }
                }

                // Fetch config UI from API
                const fetchFn = (window.getApiFetch && window.getApiFetch()) || ((url, opts) => ((window.getFetch && window.getFetch()) || fetch)(url, opts).then(r => r.ok ? r.json() : Promise.reject((window.httpErrorSync && window.httpErrorSync(r)) || new Error(`HTTP ${r.status}`))));
                const data = await fetchFn(`/api/forms/lookup-lists/${encodeURIComponent(listId)}/config-ui?config=${encodeURIComponent(JSON.stringify(existingConfig))}`).catch(() => null);

                if (data && data.success && data.html) {
                    this.setSanitizedHtml(configContainer, data.html);
                    configContainer.style.display = 'block';
                    this.setupPluginConfigListeners(modalElement, configContainer, listId);
                } else {
                    configContainer.replaceChildren();
                    configContainer.style.display = 'none';
                }
            } catch (error) {
                console.error('Error loading plugin config UI:', error);
                configContainer.replaceChildren();
                configContainer.style.display = 'none';
            }
        } else if (configContainer) {
            configContainer.replaceChildren();
            configContainer.style.display = 'none';
        }

        this.updateConfig(modalElement);
    },

    updateGroupingControlsVisibility(modalElement) {
        const groupBySelect = modalElement.querySelector('#matrix-group-by-column');
        const controlsWrapper = modalElement.querySelector('#matrix-group-controls-wrapper');
        const dropdownCheckbox = modalElement.querySelector('#matrix-group-dropdown-enabled');
        const tableCheckbox = modalElement.querySelector('#matrix-group-table-enabled');
        const hasGroupingColumn = !!groupBySelect?.value;

        if (controlsWrapper) {
            if (hasGroupingColumn) {
                controlsWrapper.classList.remove('hidden');
            } else {
                controlsWrapper.classList.add('hidden');
            }
        }
        if (dropdownCheckbox) dropdownCheckbox.disabled = !hasGroupingColumn;
        if (tableCheckbox) tableCheckbox.disabled = !hasGroupingColumn;
    },

    async setupPluginConfigListeners(modalElement, configContainer, listId) {
        // Get the lookup list data to find the plugin's JavaScript handler
        const listSelect = modalElement.querySelector(`#matrix-list-select`);
        if (!listSelect) return;

        const selectedOption = listSelect.querySelector(`option[value="${listId}"]`);
        if (!selectedOption) return;

        // Check if the lookup list has a JavaScript handler specified
        const jsHandlerName = selectedOption.dataset.configJsHandler;
        if (!jsHandlerName) {
            // Fallback: setup basic listeners if no plugin handler is provided
            const inputs = configContainer.querySelectorAll('input, select, textarea');
            inputs.forEach(input => {
                input.addEventListener('change', () => this.updateConfig(modalElement));
                input.addEventListener('input', () => this.updateConfig(modalElement));
            });
            return;
        }

        // Try to load and call the plugin's JavaScript handler
        try {
            // Check if handler is already available globally
            let handler = window[jsHandlerName];

            // If not available, try to load it from the plugin's static directory
            if (!handler || typeof handler !== 'function') {
                // Try to import from the plugin's static JS directory
                // Plugin static files: /plugins/static/{plugin_name}/{path-under-plugin/static/}
                // e.g. /plugins/static/emergency_operations/js/matrix_config_handler.js
                const pluginName = this.getPluginNameFromListId(listId);
                if (pluginName) {
                    try {
                        const module = await import(`/plugins/static/${pluginName}/js/matrix_config_handler.js`);
                        handler = module[jsHandlerName] || module.default;
                    } catch (importError) {
                        console.warn(`Failed to import plugin handler for ${listId}:`, importError);
                    }
                }
            }

            // Call the plugin handler if found
            if (handler && typeof handler === 'function') {
                handler(configContainer, () => this.updateConfig(modalElement));
            } else {
                console.warn(`Plugin config UI handler "${jsHandlerName}" not found for list ${listId}`);
                // Fallback to basic listeners
                const inputs = configContainer.querySelectorAll('input, select, textarea');
                inputs.forEach(input => {
                    input.addEventListener('change', () => this.updateConfig(modalElement));
                    input.addEventListener('input', () => this.updateConfig(modalElement));
                });
            }
        } catch (error) {
            console.error(`Error setting up plugin config listeners for ${listId}:`, error);
            // Fallback to basic listeners on error
            const inputs = configContainer.querySelectorAll('input, select, textarea');
            inputs.forEach(input => {
                input.addEventListener('change', () => this.updateConfig(modalElement));
                input.addEventListener('input', () => this.updateConfig(modalElement));
            });
        }
    },

    /**
     * Get plugin name from lookup list ID (for loading plugin-specific JS handlers)
     */
    getPluginNameFromListId(listId) {
        // Map known lookup list IDs to plugin names
        const pluginMap = {
            'emergency_operations': 'emergency_operations'
            // Add more mappings as needed
        };
        return pluginMap[listId] || null;
    },

    addListFilter(modalElement) {
        const filtersContainer = Utils.getElementById('matrix-list-filters-container');
        if (!filtersContainer) return;
        const filterDiv = document.createElement('div');
        filterDiv.className = 'matrix-filter-row flex items-center space-x-2 p-2 bg-gray-50 rounded border';
        const columnSelect = document.createElement('select');
        columnSelect.className = 'filter-column block w-1/3 py-1 px-2 border border-gray-300 bg-white rounded text-sm';
        columnSelect.replaceChildren();
        {
            const placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.textContent = 'Column...';
            columnSelect.appendChild(placeholder);
        }
        const listSelect = Utils.getElementById('matrix-list-select');
        const selectedListId = listSelect?.value;
        if (selectedListId) {
            const selectedOption = document.querySelector(`#matrix-list-select option[value="${selectedListId}"]`);
            if (selectedOption) {
                const columnsConfig = JSON.parse(selectedOption.dataset.columns || '[]');
                columnsConfig.forEach(column => {
                    const option = document.createElement('option');
                    option.value = column.name;
                    option.textContent = column.label || column.name;
                    columnSelect.appendChild(option);
                });
            }
        }
        const operatorSelect = document.createElement('select');
        operatorSelect.className = 'filter-operator block w-1/4 py-1 px-2 border border-gray-300 bg-white rounded text-sm';
        operatorSelect.replaceChildren();
        [
            ['equals', 'Equals'],
            ['not_equals', 'Not Equals'],
            ['contains', 'Contains'],
            ['not_contains', 'Not Contains']
        ].forEach(([value, label]) => {
            const opt = document.createElement('option');
            opt.value = value;
            opt.textContent = label;
            operatorSelect.appendChild(opt);
        });
        const valueInput = document.createElement('input');
        valueInput.type = 'text';
        valueInput.className = 'filter-value block w-1/3 py-1 px-2 border border-gray-300 rounded text-sm';
        valueInput.placeholder = 'Value...';
        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'text-red-600 hover:text-red-800 p-1';
        removeBtn.replaceChildren();
        {
            const icon = document.createElement('i');
            icon.className = 'fas fa-times w-3 h-3';
            removeBtn.appendChild(icon);
        }
        removeBtn.addEventListener('click', () => {
            filterDiv.remove();
            this.updateConfig(modalElement);
        });
        [columnSelect, operatorSelect, valueInput].forEach(element => {
            element.addEventListener('change', () => this.updateConfig(modalElement));
            element.addEventListener('input', () => this.updateConfig(modalElement));
        });
        filterDiv.appendChild(columnSelect);
        filterDiv.appendChild(operatorSelect);
        filterDiv.appendChild(valueInput);
        filterDiv.appendChild(removeBtn);
        filtersContainer.appendChild(filterDiv);
        this.updateConfig(modalElement);
    },

    updateConfig(modalElement) {
        const rowsContainer = Utils.getElementById('matrix-rows-container');
        const columnsContainer = Utils.getElementById('matrix-columns-container');
        const configInput = Utils.getElementById('item-matrix-config');
        if (!columnsContainer || !configInput) return;
        const columns = [];
        columnsContainer.querySelectorAll('.matrix-column').forEach(columnDiv => {
            const textInput = columnDiv.querySelector('.column-text');
            const translationsInput = columnDiv.querySelector('.column-name-translations');
            const typeSelect = columnDiv.querySelector('.column-type');
            const isVariableCheckbox = columnDiv.querySelector('.column-is-variable');
            const variableSelect = columnDiv.querySelector('.column-variable-select');
            const columnName = textInput?.value?.trim();
            const columnType = typeSelect?.value || 'number';
            const isVariable = isVariableCheckbox?.checked || false;

            if (columnName || isVariable) {
                const columnConfig = {
                    name: columnName || '',
                    type: columnType  // This is now number or tick, not variable
                };

                // Column header translations (optional)
                if (translationsInput && translationsInput.value) {
                    try {
                        const parsed = JSON.parse(translationsInput.value) || {};
                        const hasAny = parsed && typeof parsed === 'object'
                            ? Object.values(parsed).some(v => String(v || '').trim())
                            : false;
                        if (hasAny) {
                            columnConfig.name_translations = parsed;
                        }
                    } catch (_e) {
                        // ignore parse errors
                    }
                }

                // If variable checkbox is checked, include variable configuration
                if (isVariable && variableSelect?.value) {
                    columnConfig.is_variable = true;
                    columnConfig.variable = variableSelect.value;
                    columnConfig.variable_name = variableSelect.value;  // Keep for backward compatibility

                    // Get variable options
                    const variableOptions = columnDiv.querySelector('.column-variable-options');
                    const saveValueCheckbox = variableOptions?.querySelector('.column-variable-save-value');
                    const readonlyCheckbox = variableOptions?.querySelector('.column-variable-readonly');

                    columnConfig.variable_save_value = saveValueCheckbox ? saveValueCheckbox.checked : true;
                    columnConfig.variable_readonly = readonlyCheckbox ? readonlyCheckbox.checked : true;
                }
                columns.push(columnConfig);
            }
        });
        const showRowTotals = Utils.getElementById('matrix-show-row-totals')?.checked !== false;
        const showColumnTotals = Utils.getElementById('matrix-show-column-totals')?.checked !== false;
        const autoLoadEntities = Utils.getElementById('matrix-auto-load-entities')?.checked === true;
        const highlightManualRows = Utils.getElementById('matrix-highlight-manual-rows')?.checked === true;
        const legendText = Utils.getElementById('matrix-legend-text')?.value?.trim() || 'Manually added row';
        const legendTextTranslationsInput = Utils.getElementById('matrix-legend-text-translations');
        const legendHideInput = Utils.getElementById('matrix-legend-hide');
        const legendHide = legendHideInput?.value === 'true';
        const selectedMode = modalElement.querySelector('input[name="matrix_row_mode"]:checked')?.value || 'manual';
        const config = {
            type: 'matrix',
            columns: columns,
            show_row_totals: showRowTotals,
            show_column_totals: showColumnTotals,
            row_mode: selectedMode,
            highlight_manual_rows: highlightManualRows
        };

        // Add legend text and translations only if highlighting is enabled
        if (highlightManualRows) {
            config.legend_text = legendText;
            config.legend_hide = legendHide;
            if (legendTextTranslationsInput && legendTextTranslationsInput.value) {
                try {
                    const translations = JSON.parse(legendTextTranslationsInput.value);
                    if (Object.keys(translations).length > 0) {
                        config.legend_text_translations = translations;
                    }
                } catch (e) {
                    console.warn('Failed to parse legend text translations:', e);
                }
            }
        }

        // Add auto_load_entities only if at least one column is a variable
        const hasVariableColumn = columns.some(col => col.is_variable === true);
        if (hasVariableColumn) {
            config.auto_load_entities = autoLoadEntities;
        }
        if (selectedMode === 'manual') {
            if (rowsContainer) {
                const rows = Array.from(rowsContainer.querySelectorAll('.row-text')).map(input => input.value.trim()).filter(text => text);
                config.rows = rows;
            }
        } else if (selectedMode === 'list_library') {
            const listSelect = Utils.getElementById('matrix-list-select');
            const displayColumnSelect = Utils.getElementById('matrix-list-display-column');
            const filtersContainer = Utils.getElementById('matrix-list-filters-container');
            const pluginConfigContainer = modalElement.querySelector('#matrix-plugin-config-container');

            if (listSelect?.value) {
                // Handle both numeric IDs and string IDs (for system lists like 'country_map')
                const listId = listSelect.value;
                const parsedId = parseInt(listId);
                // If it's a valid number, use it; otherwise use the string (for system lists)
                config.lookup_list_id = isNaN(parsedId) ? listId : parsedId;
            }
            if (displayColumnSelect?.value) {
                config.list_display_column = displayColumnSelect.value;
            }
            const groupByColumnSelect = Utils.getElementById('matrix-group-by-column');
            if (groupByColumnSelect?.value) {
                config.group_by_column = groupByColumnSelect.value;
                config.group_dropdown_enabled = Utils.getElementById('matrix-group-dropdown-enabled')?.checked !== false;
                config.group_table_enabled = Utils.getElementById('matrix-group-table-enabled')?.checked !== false;
            }
            const searchPlaceholderInput = Utils.getElementById('matrix-search-placeholder');
            if (searchPlaceholderInput?.value) {
                config.search_placeholder = searchPlaceholderInput.value;
            }
            if (filtersContainer) {
                const filters = [];
                filtersContainer.querySelectorAll('.matrix-filter-row').forEach(filterRow => {
                    const column = filterRow.querySelector('.filter-column')?.value;
                    const operator = filterRow.querySelector('.filter-operator')?.value;
                    const value = filterRow.querySelector('.filter-value')?.value;
                    if (column && operator && value) {
                        filters.push({ column, operator, value });
                    }
                });
                config.list_filters = filters;
            }

            // Collect plugin-specific configuration generically
            if (pluginConfigContainer && pluginConfigContainer.style.display !== 'none') {
                const pluginConfig = {};

                const inputsByName = new Map();
                pluginConfigContainer.querySelectorAll('input, select, textarea').forEach(input => {
                    const name = input.name;
                    if (!name) return;
                    if (!inputsByName.has(name)) {
                        inputsByName.set(name, []);
                    }
                    inputsByName.get(name).push(input);
                });

                inputsByName.forEach((inputs, name) => {
                    const sample = inputs[0];
                    if (sample.type === 'checkbox') {
                        if (inputs.length === 1) {
                            pluginConfig[name] = inputs[0].checked;
                        } else {
                            pluginConfig[name] = inputs
                                .filter(inp => inp.checked)
                                .map(inp => inp.value || true);
                        }
                    } else if (sample.type === 'radio') {
                        const checked = inputs.find(inp => inp.checked);
                        if (checked) {
                            pluginConfig[name] = checked.value;
                        }
                    } else if (sample.tagName === 'SELECT' && sample.multiple) {
                        pluginConfig[name] = Array.from(sample.selectedOptions).map(opt => opt.value);
                    } else if (sample.value) {
                        pluginConfig[name] = sample.value;
                    }
                });

                if (Object.keys(pluginConfig).length > 0) {
                    config.plugin_config = pluginConfig;
                }
            }

            config.rows = [];
        }
        configInput.value = JSON.stringify(config);
        console.log('Updated matrix config:', config);
    },

    populateForm(modalElement, itemData) {
        // Translations
        const labelTranslationsInput = modalElement.querySelector('#item-matrix-label-translations');
        const descriptionTranslationsInput = modalElement.querySelector('#item-matrix-description-translations');
        if (labelTranslationsInput && itemData.label_translations) {
            labelTranslationsInput.value = JSON.stringify(itemData.label_translations);
        }
        if (descriptionTranslationsInput && itemData.description_translations) {
            descriptionTranslationsInput.value = JSON.stringify(itemData.description_translations);
        }
        if (itemData.config) {
            try {
                const matrixConfig = typeof itemData.config === 'string' ? JSON.parse(itemData.config) : itemData.config;
                const rowMode = matrixConfig.row_mode || 'manual';
                const rowModeRadio = modalElement.querySelector(`input[name="matrix_row_mode"][value="${rowMode}"]`);
                if (rowModeRadio) {
                    rowModeRadio.checked = true;
                    rowModeRadio.dispatchEvent(new Event('change'));
                }
                const rowsContainer = Utils.getElementById('matrix-rows-container');
                const columnsContainer = Utils.getElementById('matrix-columns-container');
                if (rowsContainer) rowsContainer.replaceChildren();
                if (columnsContainer) columnsContainer.replaceChildren();
                if (rowMode === 'manual') {
                    if (Array.isArray(matrixConfig.rows)) {
                        matrixConfig.rows.forEach(rowText => this.addRow(modalElement, rowText));
                    }
                } else if (rowMode === 'list_library') {
                    if (matrixConfig.lookup_list_id) {
                        const listSelect = Utils.getElementById('matrix-list-select');
                        if (listSelect) {
                            listSelect.value = matrixConfig.lookup_list_id;
                            // handleListSelection is now async, wait for it to complete
                            this.handleListSelection(modalElement, matrixConfig.lookup_list_id).then(() => {
                                if (matrixConfig.list_display_column) {
                                    const displayColumnSelect = Utils.getElementById('matrix-list-display-column');
                                    if (displayColumnSelect) {
                                        displayColumnSelect.value = matrixConfig.list_display_column;
                                    }
                                }
                                if (matrixConfig.search_placeholder) {
                                    const searchPlaceholderInput = Utils.getElementById('matrix-search-placeholder');
                                    if (searchPlaceholderInput) {
                                        searchPlaceholderInput.value = matrixConfig.search_placeholder;
                                    }
                                }
                                if (matrixConfig.group_by_column) {
                                    const groupBySelect = Utils.getElementById('matrix-group-by-column');
                                    if (groupBySelect) {
                                        groupBySelect.value = matrixConfig.group_by_column;
                                    }
                                }
                                const groupDropdownEnabled = Utils.getElementById('matrix-group-dropdown-enabled');
                                const groupTableEnabled = Utils.getElementById('matrix-group-table-enabled');
                                if (groupDropdownEnabled) {
                                    groupDropdownEnabled.checked = matrixConfig.group_dropdown_enabled !== false;
                                }
                                if (groupTableEnabled) {
                                    groupTableEnabled.checked = matrixConfig.group_table_enabled !== false;
                                }
                                this.updateGroupingControlsVisibility(modalElement);

                                // Restore plugin configuration generically if present
                                if (matrixConfig.plugin_config) {
                                    const pluginConfigContainer = modalElement.querySelector('#matrix-plugin-config-container');
                                    if (pluginConfigContainer) {
                                        // Restore all plugin config values generically
                                        Object.keys(matrixConfig.plugin_config).forEach(key => {
                                            const value = matrixConfig.plugin_config[key];
                                            const inputs = pluginConfigContainer.querySelectorAll(`[name="${key}"]`);

                                            inputs.forEach(input => {
                                                if (input.type === 'checkbox') {
                                                    input.checked = shouldCheckMatrixCheckbox(value, input.value || true);
                                                } else if (input.type === 'radio') {
                                                    input.checked = input.value === value;
                                                } else if (input.tagName === 'SELECT' && input.multiple) {
                                                    // For multi-select, set selected options
                                                    if (Array.isArray(value)) {
                                                        Array.from(input.options).forEach(opt => {
                                                            opt.selected = value.includes(opt.value);
                                                        });
                                                    }
                                                } else {
                                                    // For text inputs, textareas, and single selects
                                                    input.value = Array.isArray(value) ? value[0] : value;
                                                }
                                            });
                                        });
                                    }
                                }
                            });
                        }
                    }
                    if (Array.isArray(matrixConfig.list_filters)) {
                        const filtersContainer = Utils.getElementById('matrix-list-filters-container');
                        if (filtersContainer) {
                            filtersContainer.replaceChildren();
                            matrixConfig.list_filters.forEach(filter => {
                                this.addListFilter(modalElement);
                                const filterRow = filtersContainer.lastElementChild;
                                if (filterRow) {
                                    filterRow.querySelector('.filter-column').value = filter.column || '';
                                    filterRow.querySelector('.filter-operator').value = filter.operator || 'equals';
                                    filterRow.querySelector('.filter-value').value = filter.value || '';
                                }
                            });
                        }
                    }
                }
                if (Array.isArray(matrixConfig.columns)) {
                    matrixConfig.columns.forEach(columnData => {
                        if (typeof columnData === 'string') {
                            this.addColumn(modalElement, columnData, 'number');
                        } else if (columnData && typeof columnData === 'object' && (columnData.name || columnData.is_variable || columnData.type === 'variable')) {
                            const columnName = columnData.name || '';
                            // Handle both new structure (is_variable) and legacy (type === 'variable')
                            const isVariable = columnData.is_variable || columnData.type === 'variable';
                            const columnType = (columnData.type === 'variable') ? 'number' : (columnData.type || 'number');
                            const variableName = columnData.variable || columnData.variable_name || '';
                            const variableSaveValue = columnData.variable_save_value !== undefined ? columnData.variable_save_value : true;
                            const variableReadonly = columnData.variable_readonly !== undefined ? columnData.variable_readonly : true;
                            const nameTranslations = columnData.name_translations || {};
                            this.addColumn(modalElement, columnName, columnType, isVariable, variableName, variableSaveValue, variableReadonly, nameTranslations);
                        }
                    });
                }
                const rowTotalsCheckbox = Utils.getElementById('matrix-show-row-totals');
                const columnTotalsCheckbox = Utils.getElementById('matrix-show-column-totals');
                const autoLoadCheckbox = Utils.getElementById('matrix-auto-load-entities');
                const highlightManualRowsCheckbox = Utils.getElementById('matrix-highlight-manual-rows');
                const legendTextInput = Utils.getElementById('matrix-legend-text');
                const legendTextTranslationsInput = Utils.getElementById('matrix-legend-text-translations');
                const legendHideInput = Utils.getElementById('matrix-legend-hide');
                const legendHideBtn = Utils.getElementById('matrix-legend-hide-btn');
                if (rowTotalsCheckbox) rowTotalsCheckbox.checked = matrixConfig.show_row_totals !== false;
                if (columnTotalsCheckbox) columnTotalsCheckbox.checked = matrixConfig.show_column_totals !== false;
                if (autoLoadCheckbox) autoLoadCheckbox.checked = matrixConfig.auto_load_entities === true;
                if (highlightManualRowsCheckbox) highlightManualRowsCheckbox.checked = matrixConfig.highlight_manual_rows === true;
                if (legendTextInput) {
                    legendTextInput.value = matrixConfig.legend_text || 'Manually added row';
                }
                if (legendTextTranslationsInput && matrixConfig.legend_text_translations) {
                    legendTextTranslationsInput.value = JSON.stringify(matrixConfig.legend_text_translations);
                }
                if (legendHideInput) {
                    const legendHide = matrixConfig.legend_hide === true;
                    legendHideInput.value = String(legendHide);
                    const legendTextInput = Utils.getElementById('matrix-legend-text');

                    // Update button icon, text, and input state based on saved state
                    if (legendHideBtn) {
                        const icon = legendHideBtn.querySelector('i');
                        const textSpan = legendHideBtn.querySelector('span');

                        if (legendHide) {
                            // Legend is hidden
                            if (icon) {
                                icon.className = 'fas fa-eye-slash w-4 h-4 mr-1';
                            }
                            if (textSpan) {
                                textSpan.textContent = 'Legend hidden';
                            } else {
                                const span = document.createElement('span');
                                span.textContent = 'Legend hidden';
                                legendHideBtn.appendChild(span);
                            }
                            legendHideBtn.title = 'Legend is hidden - click to show';
                            legendHideBtn.classList.remove('text-gray-600');
                            legendHideBtn.classList.add('text-gray-500');

                            // Grey out the text input
                            if (legendTextInput) {
                                legendTextInput.disabled = true;
                                legendTextInput.classList.add('bg-gray-100', 'cursor-not-allowed');
                            }
                        } else {
                            // Legend is shown
                            if (icon) {
                                icon.className = 'fas fa-eye w-4 h-4 mr-1';
                            }
                            if (textSpan) {
                                textSpan.textContent = 'Legend shown';
                            } else {
                                const span = document.createElement('span');
                                span.textContent = 'Legend shown';
                                legendHideBtn.appendChild(span);
                            }
                            legendHideBtn.title = 'Legend is shown - click to hide';
                            legendHideBtn.classList.remove('text-gray-500');
                            legendHideBtn.classList.add('text-gray-600');

                            // Enable the text input
                            if (legendTextInput) {
                                legendTextInput.disabled = false;
                                legendTextInput.classList.remove('bg-gray-100', 'cursor-not-allowed');
                            }
                        }
                    }
                }

                // Update auto-load visibility after columns are populated
                this.updateAutoLoadVisibility(modalElement);
                // Update legend text visibility after checkbox is set
                this.updateLegendTextVisibility(modalElement);
                this.updateConfig(modalElement);
            } catch (e) {
                console.error('Error parsing matrix config:', e);
                this.initializeDefault(modalElement);
            }
        } else {
            this.initializeDefault(modalElement);
        }
    }
};
