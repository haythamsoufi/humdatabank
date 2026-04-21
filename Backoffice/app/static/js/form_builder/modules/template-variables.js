/**
 * Template Variables Management Module
 * Handles creation, editing, deletion, and display of template variables
 */

const _fetchJson = (window.getApiFetch && window.getApiFetch()) || window.apiFetch || fetch;

export class TemplateVariablesManager {
    constructor(config) {
        this.templateId = config.templateId;
        this.versionId = config.versionId;
        this.variables = config.templateVariables || {};
        this.allTemplates = [];
        this.assignmentsByTemplate = {};
        this.formItemsByTemplate = {};

        // Make variables globally available for use in item modal and matrix
        window.templateVariables = this.variables;

        if (!this.versionId) {
            console.error('Variables: active_version_id is not set');
        }
    }

    /**
     * Load variable options on page load
     */
    async loadVariableOptions() {
        try {
            const data = await _fetchJson(`/admin/templates/${this.templateId}/variables/options?version_id=${this.versionId}`);
            if (data.success) {
                this.allTemplates = data.templates || [];
                this.assignmentsByTemplate = data.assignments_by_template || {};
            }
        } catch (error) {
            console.error('Error loading variable options:', error);
        }
    }

    /**
     * Load form items for a template
     */
    async loadFormItemsForTemplate(sourceTemplateId) {
        if (this.formItemsByTemplate[sourceTemplateId]) {
            return this.formItemsByTemplate[sourceTemplateId];
        }
        try {
            const data = await _fetchJson(`/admin/templates/${this.templateId}/variables/options?version_id=${this.versionId}&source_template_id=${sourceTemplateId}`);
            if (data.success) {
                this.formItemsByTemplate[sourceTemplateId] = data.form_items || [];
                return this.formItemsByTemplate[sourceTemplateId];
            }
        } catch (error) {
            console.error('Error loading form items:', error);
        }
        return [];
    }

    /**
     * Update template variables button count and styling
     */
    updateVariablesButton() {
        const btn = document.getElementById('template-variables-btn');
        const countSpan = document.getElementById('template-variables-count');
        if (!btn || !countSpan) return;

        const count = Object.keys(this.variables).length;

        countSpan.textContent = count > 0 ? `(${count})` : '(0)';
        countSpan.classList.remove('hidden');

        // Grey when no variables; purple when any exist (semantic .btn only)
        if (count === 0) {
            btn.classList.remove('btn-purple');
            btn.classList.add('template-variables-btn--empty');
            btn.disabled = false;
        } else {
            btn.classList.remove('template-variables-btn--empty');
            btn.classList.add('btn-purple');
            btn.disabled = false;
        }
    }

    /**
     * Render variables list
     */
    renderVariablesList() {
        const container = document.getElementById('variables-list-container');
        if (!container) return;

        container.replaceChildren();

        if (Object.keys(this.variables).length === 0) {
            const tr = document.createElement('tr');
            const td = document.createElement('td');
            td.colSpan = 6;
            td.className = 'px-4 py-8 text-center text-gray-500 text-sm italic';
            td.textContent = 'No variables defined. Click "Add Variable" to create one.';
            tr.appendChild(td);
            container.appendChild(tr);
            return;
        }

        for (const [varName, varConfig] of Object.entries(this.variables)) {
            const row = this.createVariableRow(varName, varConfig);
            container.appendChild(row);
        }
    }

    /**
     * Create variable table row
     */
    createVariableRow(varName, varConfig) {
        const row = document.createElement('tr');
        row.className = 'hover:bg-gray-50';
        row.dataset.variableName = varName;

        const variableType = varConfig.variable_type || 'lookup'; // Default to 'lookup' for backward compatibility

        // Format display based on type
        let typeDisplay = '';
        let sourceInfo = '';
        let entityScopeDisplay = '';

        if (variableType === 'metadata') {
            typeDisplay = 'Metadata';
            const metadataType = varConfig.metadata_type || 'N/A';
            const metadataTypeLabels = {
                'entity_name': 'Entity Name',
                'entity_name_hierarchy': 'Entity Name (with hierarchy)',
                'entity_id': 'Entity ID',
                'entity_type': 'Entity Type',
                'template_name': 'Template Name',
                'assignment_period': 'Assignment Period'
            };
            sourceInfo = metadataTypeLabels[metadataType] || metadataType;
        } else {
            typeDisplay = 'Lookup';
            const sourceTemplate = this.allTemplates.find(t => t.id === varConfig.source_template_id);
            const sourceTemplateName = sourceTemplate ? sourceTemplate.name : (varConfig.source_template_id ? `Template ${varConfig.source_template_id}` : 'N/A');
            sourceInfo = sourceTemplateName;

            // Format entity scope display
            entityScopeDisplay = varConfig.entity_scope || 'same';
            if (varConfig.entity_scope === 'specific' && varConfig.specific_entity_type && varConfig.specific_entity_id) {
                entityScopeDisplay = `Specific (${varConfig.specific_entity_type}: ${varConfig.specific_entity_id})`;
            } else if (varConfig.entity_scope === 'entities_containing') {
                entityScopeDisplay = `Find Entities That Reference This Entity`;
            }
        }

        // Format additional info (default value, formatting, matrix column)
        const additionalInfo = [];
        if (varConfig.default_value) {
            additionalInfo.push(`Default: ${varConfig.default_value}`);
        }
        if (varConfig.matrix_column_name) {
            additionalInfo.push(varConfig.matrix_column_name === '_row_total'
                ? 'Matrix: Row total (sum of all columns)'
                : `Matrix Column: ${varConfig.matrix_column_name}`);
        }
        if (varConfig.format_thousands_separator || varConfig.format_decimal_places) {
            const formatParts = [];
            if (varConfig.format_thousands_separator) {
                formatParts.push('Thousands separator');
            }
            if (varConfig.format_decimal_places && varConfig.format_decimal_places !== 'auto') {
                if (varConfig.format_decimal_places === 'whole') {
                    formatParts.push('Whole number');
                } else {
                    formatParts.push(`${varConfig.format_decimal_places} decimal places`);
                }
            }
            if (formatParts.length > 0) {
                additionalInfo.push(`Format: ${formatParts.join(', ')}`);
            }
        }

        const td1 = document.createElement('td');
        td1.className = 'px-4 py-3 whitespace-nowrap';
        const vName = document.createElement('div');
        vName.className = 'text-sm font-semibold text-gray-900';
        vName.textContent = `[${varName}]`;
        const vType = document.createElement('div');
        vType.className = 'text-xs text-gray-500 mt-1';
        vType.textContent = `Type: ${typeDisplay}`;
        td1.append(vName, vType);
        if (additionalInfo.length > 0) {
            const info = document.createElement('div');
            info.className = 'text-xs text-gray-500 mt-1';
            info.textContent = additionalInfo.join(' | ');
            td1.appendChild(info);
        }

        const td2 = document.createElement('td');
        td2.className = 'px-4 py-3 whitespace-nowrap';
        {
            const div = document.createElement('div');
            div.className = 'text-sm text-gray-900';
            div.textContent = String(varConfig.display_name || varName);
            td2.appendChild(div);
        }

        const td3 = document.createElement('td');
        td3.className = 'px-4 py-3 whitespace-nowrap';
        {
            const div = document.createElement('div');
            div.className = 'text-sm text-gray-900';
            div.textContent = String(sourceInfo || '');
            td3.appendChild(div);
        }

        const td4 = document.createElement('td');
        td4.className = 'px-4 py-3 whitespace-nowrap';
        {
            const div = document.createElement('div');
            div.className = 'text-sm text-gray-900';
            div.textContent = String(variableType === 'metadata' ? 'N/A' : (varConfig.source_assignment_period || 'N/A'));
            td4.appendChild(div);
        }

        const td5 = document.createElement('td');
        td5.className = 'px-4 py-3 whitespace-nowrap';
        {
            const div = document.createElement('div');
            div.className = 'text-sm text-gray-900';
            div.textContent = String(variableType === 'metadata' ? 'N/A' : entityScopeDisplay);
            td5.appendChild(div);
        }

        const td6 = document.createElement('td');
        td6.className = 'px-4 py-3 whitespace-nowrap text-sm font-medium';
        const btnWrap = document.createElement('div');
        btnWrap.className = 'flex space-x-2';

        const editBtn = document.createElement('button');
        editBtn.type = 'button';
        editBtn.className = 'edit-variable-btn inline-flex items-center px-2 py-1 bg-blue-600 hover:bg-blue-700 text-white text-xs rounded';
        editBtn.dataset.variableName = String(varName);
        {
            const icon = document.createElement('i');
            icon.className = 'fas fa-pen w-3 h-3 mr-1';
            editBtn.append(icon, document.createTextNode(' Edit'));
        }

        const duplicateBtn = document.createElement('button');
        duplicateBtn.type = 'button';
        duplicateBtn.className = 'duplicate-variable-btn inline-flex items-center px-2 py-1 bg-gray-600 hover:bg-gray-700 text-white text-xs rounded';
        duplicateBtn.dataset.variableName = String(varName);
        duplicateBtn.title = 'Duplicate this variable';
        {
            const icon = document.createElement('i');
            icon.className = 'fas fa-copy w-3 h-3 mr-1';
            duplicateBtn.append(icon, document.createTextNode(' Duplicate'));
        }

        const deleteBtn = document.createElement('button');
        deleteBtn.type = 'button';
        deleteBtn.className = 'delete-variable-btn inline-flex items-center px-2 py-1 bg-red-600 hover:bg-red-700 text-white text-xs rounded';
        deleteBtn.dataset.variableName = String(varName);
        {
            const icon = document.createElement('i');
            icon.className = 'fas fa-trash w-3 h-3 mr-1';
            deleteBtn.append(icon, document.createTextNode(' Delete'));
        }

        btnWrap.append(editBtn, duplicateBtn, deleteBtn);
        td6.appendChild(btnWrap);

        row.append(td1, td2, td3, td4, td5, td6);

        return row;
    }

    /**
     * Show variable form modal
     */
    async showVariableForm(editVarName = null) {
        const existingVar = editVarName ? this.variables[editVarName] : null;
        const escAttr = (value) => {
            if (value === null || value === undefined) return '';
            return String(value)
                .replace(/&/g, '&amp;')
                .replace(/"/g, '&quot;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;');
        };

        // Create modal using centralized createModalShell (from confirm-dialogs.js)
        const modalTitle = editVarName ? 'Edit Variable' : 'Add Variable';
        const { modal, contentDiv, closeModal } = window.createModalShell(modalTitle, { iconType: 'info', maxWidth: '2xl' });
        modal.id = 'variable-form-modal';

        const formHtml = `
            <form id="variable-form" class="space-y-4">
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">
                                    Variable Name *
                                    <span class="custom-info-tooltip cursor-help w-5 h-5 inline-flex items-center justify-center ml-1">
                                        <i class="fas fa-info-circle text-gray-400"></i>
                                        <span class="tooltip-text">Use in fields as [variable_name]. Only letters, numbers, and underscores.${editVarName ? ' Note: Changing the variable name will require updating all references to it in your template.' : ''}</span>
                                    </span>
                                </label>
                                <input type="text" name="variable_name" value="${escAttr(editVarName || '')}" required
                                       pattern="[a-zA-Z_][a-zA-Z0-9_]*"
                                       class="w-full px-3 py-2 border border-gray-300 rounded-md"
                                       placeholder="e.g., planned_funding">
                            </div>

                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Display Name</label>
                                <input type="text" name="display_name" value="${escAttr(existingVar?.display_name || '')}"
                                       class="w-full px-3 py-2 border border-gray-300 rounded-md"
                                       placeholder="Human-readable name">
                            </div>
                        </div>

                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">
                                Variable Type *
                                <span class="custom-info-tooltip cursor-help w-5 h-5 inline-flex items-center justify-center ml-1">
                                    <i class="fas fa-info-circle text-gray-400"></i>
                                    <span class="tooltip-text">Choose whether this variable looks up data from other forms or returns metadata about the current form/entity.</span>
                                </span>
                            </label>
                            <select name="variable_type" required class="w-full px-3 py-2 border border-gray-300 rounded-md" id="variable-type-select">
                                <option value="lookup" ${existingVar?.variable_type === 'lookup' || !existingVar?.variable_type ? 'selected' : ''}>Lookup (from other form submissions)</option>
                                <option value="metadata" ${existingVar?.variable_type === 'metadata' ? 'selected' : ''}>Metadata (entity name, template name, etc.)</option>
                            </select>
                        </div>

                        <div id="metadata-type-fields" class="hidden space-y-2">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">
                                    Metadata Type *
                                    <span class="custom-info-tooltip cursor-help w-5 h-5 inline-flex items-center justify-center ml-1">
                                        <i class="fas fa-info-circle text-gray-400"></i>
                                        <span class="tooltip-text">Select what metadata this variable should return.</span>
                                    </span>
                                </label>
                                <select name="metadata_type" class="w-full px-3 py-2 border border-gray-300 rounded-md" id="metadata-type-select">
                                    <option value="">Select metadata type...</option>
                                    <option value="entity_name" ${existingVar?.metadata_type === 'entity_name' ? 'selected' : ''}>Entity Name</option>
                                    <option value="entity_name_hierarchy" ${existingVar?.metadata_type === 'entity_name_hierarchy' ? 'selected' : ''}>Entity Name (with hierarchy)</option>
                                    <option value="entity_id" ${existingVar?.metadata_type === 'entity_id' ? 'selected' : ''}>Entity ID</option>
                                    <option value="entity_type" ${existingVar?.metadata_type === 'entity_type' ? 'selected' : ''}>Entity Type</option>
                                    <option value="template_name" ${existingVar?.metadata_type === 'template_name' ? 'selected' : ''}>Template Name</option>
                                    <option value="assignment_period" ${existingVar?.metadata_type === 'assignment_period' ? 'selected' : ''}>Assignment Period</option>
                                </select>
                            </div>
                        </div>

                        <div id="lookup-type-fields" class="space-y-4">

                        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Source Template *</label>
                                <select name="source_template_id" class="w-full px-3 py-2 border border-gray-300 rounded-md" id="source-template-select">
                                    <option value="">Select template...</option>
                                    ${this.allTemplates.map(t => `<option value="${escAttr(t.id)}" ${existingVar?.source_template_id == t.id ? 'selected' : ''}>${escAttr(t.name)}</option>`).join('')}
                                </select>
                            </div>

                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Source Assignment Period *</label>
                                <select name="source_assignment_period" class="w-full px-3 py-2 border border-gray-300 rounded-md" id="source-assignment-select">
                                    <option value="">Select assignment period...</option>
                                </select>
                            </div>
                        </div>

                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Source Form Item *</label>
                            <select name="source_form_item_id" class="w-full px-3 py-2 border border-gray-300 rounded-md" id="source-form-item-select">
                                <option value="">Select form item...</option>
                            </select>
                            <label class="flex items-center mt-2 text-sm text-gray-700">
                                <input type="checkbox"
                                       name="match_by_indicator_bank"
                                       id="match-by-indicator-bank-checkbox"
                                       ${existingVar?.match_by_indicator_bank ? 'checked' : ''}
                                       class="mr-2">
                                <span>
                                    Match by indicator bank (auto-map the source item)
                                    <span class="custom-info-tooltip cursor-help w-5 h-5 inline-flex items-center justify-center ml-1">
                                        <i class="fas fa-info-circle text-gray-400"></i>
                                        <span class="tooltip-text">
                                            When enabled, you do not need to select a specific Source Form Item.
                                            If you use this variable inside an indicator in the current template, the system will read that indicator’s Indicator Bank ID,
                                            find the matching indicator (same Indicator Bank ID) in the source template, and lookup its value.
                                            If used outside an indicator, the variable will resolve to blank/default.
                                        </span>
                                    </span>
                                </span>
                            </label>
                        </div>

                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">
                                Lookup Type *
                                <span class="custom-info-tooltip cursor-help w-5 h-5 inline-flex items-center justify-center ml-1">
                                    <i class="fas fa-info-circle text-gray-400"></i>
                                    <span class="tooltip-text">Standard Lookup: Lookup a value from a specific form item in another submission. Find Entities That Reference This Entity: Find all entities whose matrix data mentions/references the current assignment's entity ID. Only works with matrix form items. Returns a list of matching entities.</span>
                                </span>
                            </label>
                            <select name="lookup_type" class="w-full px-3 py-2 border border-gray-300 rounded-md" id="lookup-type-select">
                                <option value="standard" ${existingVar?.entity_scope !== 'entities_containing' ? 'selected' : ''}>Standard Lookup</option>
                                <option value="reverse" ${existingVar?.entity_scope === 'entities_containing' ? 'selected' : ''}>Find Entities That Reference This Entity</option>
                            </select>
                        </div>

                        <div id="standard-lookup-fields" class="space-y-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">
                                Entity Scope *
                                <span class="custom-info-tooltip cursor-help w-5 h-5 inline-flex items-center justify-center ml-1" id="entity-scope-tooltip">
                                    <i class="fas fa-info-circle text-gray-400"></i>
                                    <span class="tooltip-text">Same Entity: Use data from the same entity as the current form (e.g., if filling a form for Country A, use Country A's previous submission). Most common for standard lookups. Any Entity: Use data from any entity's submission. The system will use the most recent submission from any entity. Useful for aggregated/central data. Specific Entity: Use data from a specific entity's submission (e.g., always use Country B's data regardless of current form). Useful for cross-entity lookups.</span>
                                </span>
                            </label>
                            <select name="entity_scope" class="w-full px-3 py-2 border border-gray-300 rounded-md" id="entity-scope-select">
                                <option value="same" ${existingVar?.entity_scope === 'same' ? 'selected' : ''}>Same Entity</option>
                                <option value="any" ${existingVar?.entity_scope === 'any' ? 'selected' : ''}>Any Entity</option>
                                <option value="specific" ${existingVar?.entity_scope === 'specific' ? 'selected' : ''}>Specific Entity</option>
                            </select>
                        </div>
                        </div>

                        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">
                                    Matrix Column (for matrix lookups)
                                    <span class="custom-info-tooltip cursor-help w-5 h-5 inline-flex items-center justify-center ml-1" id="matrix-column-help-icon">
                                        <i class="fas fa-info-circle text-gray-400"></i>
                                        <span class="tooltip-text" id="matrix-column-tooltip-text">Optional: If the source form item is a matrix, specify which column to lookup (e.g., 'Planned' for '61_Planned'), or use Row total to read the sum of all columns for each row.</span>
                                    </span>
                                </label>
                                <label class="flex items-center mb-2">
                                    <input type="checkbox" name="use_row_total" id="use-row-total-checkbox"
                                           ${existingVar?.matrix_column_name === '_row_total' ? 'checked' : ''}
                                           class="mr-2">
                                    <span class="text-sm text-gray-700">Use row total (sum of all columns for each row)</span>
                                </label>
                                <input type="text" name="matrix_column_name" value="${escAttr(existingVar?.matrix_column_name && existingVar.matrix_column_name !== '_row_total' ? existingVar.matrix_column_name : '')}"
                                       class="w-full px-3 py-2 border border-gray-300 rounded-md"
                                       placeholder="e.g., Planned, Supported (or use Row total above)"
                                       id="matrix-column-name-input">
                            </div>

                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">
                                    Default Value
                                    <span class="custom-info-tooltip cursor-help w-5 h-5 inline-flex items-center justify-center ml-1">
                                        <i class="fas fa-info-circle text-gray-400"></i>
                                        <span class="tooltip-text">Optional: This value will be used if the variable cannot be resolved or returns blank.</span>
                                    </span>
                                </label>
                                <input type="text" name="default_value" value="${escAttr(existingVar?.default_value || '')}"
                                       class="w-full px-3 py-2 border border-gray-300 rounded-md"
                                       placeholder="Value to use if lookup returns blank/not found">
                            </div>
                        </div>

                        <div id="specific-entity-fields" class="hidden mt-2 p-3 bg-gray-50 rounded-md border border-gray-200">
                            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div>
                                    <label class="block text-sm font-medium text-gray-700 mb-1">
                                        Entity Type *
                                        <span class="custom-info-tooltip cursor-help w-5 h-5 inline-flex items-center justify-center ml-1">
                                            <i class="fas fa-info-circle text-gray-400"></i>
                                            <span class="tooltip-text">The type of entity to lookup. This determines which entity's submission will be used as the data source.</span>
                                        </span>
                                    </label>
                                    <select name="specific_entity_type" id="specific-entity-type-select"
                                           class="w-full px-3 py-2 border border-gray-300 rounded-md">
                                        <option value="">Select entity type...</option>
                                        <option value="country" ${existingVar?.specific_entity_type === 'country' ? 'selected' : ''}>Country</option>
                                        <option value="ns_branch" ${existingVar?.specific_entity_type === 'ns_branch' ? 'selected' : ''}>NS Branch</option>
                                        <option value="ns_subbranch" ${existingVar?.specific_entity_type === 'ns_subbranch' ? 'selected' : ''}>NS Sub-branch</option>
                                        <option value="ns_localunit" ${existingVar?.specific_entity_type === 'ns_localunit' ? 'selected' : ''}>NS Local Unit</option>
                                        <option value="division" ${existingVar?.specific_entity_type === 'division' ? 'selected' : ''}>Secretariat Division</option>
                                        <option value="department" ${existingVar?.specific_entity_type === 'department' ? 'selected' : ''}>Secretariat Department</option>
                                        <option value="regional_office" ${existingVar?.specific_entity_type === 'regional_office' ? 'selected' : ''}>Regional Office</option>
                                        <option value="cluster_office" ${existingVar?.specific_entity_type === 'cluster_office' ? 'selected' : ''}>Cluster Office</option>
                                    </select>
                                </div>
                                <div>
                                    <label class="block text-sm font-medium text-gray-700 mb-1">
                                        Entity ID *
                                        <span class="custom-info-tooltip cursor-help w-5 h-5 inline-flex items-center justify-center ml-1">
                                            <i class="fas fa-info-circle text-gray-400"></i>
                                            <span class="tooltip-text">The numeric ID of the specific entity (e.g., country ID 61 for Afghanistan)</span>
                                        </span>
                                    </label>
                                    <input type="number" name="specific_entity_id" id="specific-entity-id-input"
                                           value="${escAttr(existingVar?.specific_entity_id || '')}"
                                           class="w-full px-3 py-2 border border-gray-300 rounded-md"
                                           placeholder="Enter entity ID (e.g., 61)"
                                           min="1"
                                           step="1">
                                </div>
                            </div>
                        </div>

                        <div id="reverse-lookup-fields" class="hidden space-y-4">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">
                                    Return Format *
                                    <span class="custom-info-tooltip cursor-help w-5 h-5 inline-flex items-center justify-center ml-1">
                                        <i class="fas fa-info-circle text-gray-400"></i>
                                        <span class="tooltip-text">Auto-load Format: Returns JSON in the same format as the matrix auto-load endpoint. Use this when the variable is used in a matrix column with auto_load_entities enabled. Comma-separated names: Returns a simple list of entity names separated by commas (e.g., 'France, Germany, Italy') for display purposes. This finds all entities whose matrix data mentions/references the current assignment's entity ID. For example, if this template is assigned to NS 88, it will find all countries that mention NS 88 in their matrix data keys (e.g., '88_SP2', '88_SP3'). Requirements: The source form item must be a matrix type. The lookup entity ID is automatically set to the entity ID of the assignment being filled out - no manual configuration needed.</span>
                                    </span>
                                </label>
                                <select name="return_format" id="return-format-select"
                                       class="w-full px-3 py-2 border border-gray-300 rounded-md">
                                    <option value="auto_load_format" ${existingVar?.return_format === 'auto_load_format' || !existingVar?.return_format ? 'selected' : ''}>Auto-load Format (JSON for matrix auto-load)</option>
                                    <option value="names_comma" ${existingVar?.return_format === 'names_comma' ? 'selected' : ''}>Comma-separated names (e.g., "France, Germany, Italy")</option>
                                </select>
                            </div>
                        </div>

                        <div class="pt-4 border-t">
                            <h4 class="text-sm font-semibold text-gray-700 mb-3">Number Formatting (for numeric values)</h4>

                            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div>
                                    <label class="flex items-center">
                                        <input type="checkbox" name="format_thousands_separator" ${existingVar?.format_thousands_separator ? 'checked' : ''}
                                               class="mr-2">
                                        <span class="text-sm text-gray-700">Use thousands separator (e.g., 29,908 instead of 29908)</span>
                                    </label>
                                </div>

                                <div>
                                    <label class="block text-sm font-medium text-gray-700 mb-1">Decimal Places</label>
                                    <select name="format_decimal_places" class="w-full px-3 py-2 border border-gray-300 rounded-md">
                                        <option value="auto" ${existingVar?.format_decimal_places === 'auto' || !existingVar?.format_decimal_places ? 'selected' : ''}>Auto (keep original decimals)</option>
                                        <option value="whole" ${existingVar?.format_decimal_places === 'whole' ? 'selected' : ''}>Whole number (round, no decimals)</option>
                                        <option value="0" ${existingVar?.format_decimal_places === '0' || existingVar?.format_decimal_places === 0 ? 'selected' : ''}>0 decimal places</option>
                                        <option value="1" ${existingVar?.format_decimal_places === '1' || existingVar?.format_decimal_places === 1 ? 'selected' : ''}>1 decimal place</option>
                                        <option value="2" ${existingVar?.format_decimal_places === '2' || existingVar?.format_decimal_places === 2 ? 'selected' : ''}>2 decimal places</option>
                                    </select>
                                </div>
                            </div>
                        </div>
                        </div>

                        <div class="flex justify-end space-x-3 pt-4 border-t">
                            <button type="button" class="cancel-variable-form px-4 py-2 bg-gray-300 hover:bg-gray-400 text-gray-700 rounded">Cancel</button>
                            <button type="button" class="variable-form-submit px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded">${editVarName ? 'Update' : 'Create'} Variable</button>
                        </div>
                    </form>
        `;

        contentDiv.innerHTML = '<div class="max-h-[75vh] overflow-y-auto">' + formHtml + '</div>';

        // Attach tooltip positioning handlers (CSP-safe: no inline mouse handlers)
        this.attachTooltipHandlers(modal);

        // Setup form handlers
        const form = modal.querySelector('#variable-form');
        const variableTypeSelect = modal.querySelector('#variable-type-select');
        const metadataTypeFields = modal.querySelector('#metadata-type-fields');
        const lookupTypeFields = modal.querySelector('#lookup-type-fields');
        const lookupTypeSelect = modal.querySelector('#lookup-type-select');
        const standardLookupFields = modal.querySelector('#standard-lookup-fields');
        const reverseLookupFields = modal.querySelector('#reverse-lookup-fields');
        const sourceTemplateSelect = modal.querySelector('#source-template-select');
        const sourceAssignmentSelect = modal.querySelector('#source-assignment-select');
        const sourceFormItemSelect = modal.querySelector('#source-form-item-select');
        const matchByIndicatorBankCheckbox = modal.querySelector('#match-by-indicator-bank-checkbox');
        const entityScopeSelect = form.querySelector('[name="entity_scope"]');
        const specificEntityFields = modal.querySelector('#specific-entity-fields');

        // Show/hide fields based on variable type
        const updateVariableTypeUI = () => {
            const variableType = variableTypeSelect.value;
            if (variableType === 'metadata') {
                metadataTypeFields.classList.remove('hidden');
                lookupTypeFields.classList.add('hidden');
                // Remove required from lookup fields
                sourceTemplateSelect.removeAttribute('required');
                sourceAssignmentSelect.removeAttribute('required');
                sourceFormItemSelect.removeAttribute('required');
                entityScopeSelect.removeAttribute('required');
                // Add required to metadata type
                const metadataTypeSelect = modal.querySelector('#metadata-type-select');
                if (metadataTypeSelect) {
                    metadataTypeSelect.setAttribute('required', 'required');
                }
            } else {
                metadataTypeFields.classList.add('hidden');
                lookupTypeFields.classList.remove('hidden');
                // Add required to lookup fields
                sourceTemplateSelect.setAttribute('required', 'required');
                sourceAssignmentSelect.setAttribute('required', 'required');
                sourceFormItemSelect.setAttribute('required', 'required');
                entityScopeSelect.setAttribute('required', 'required');
                // Remove required from metadata type
                const metadataTypeSelect = modal.querySelector('#metadata-type-select');
                if (metadataTypeSelect) {
                    metadataTypeSelect.removeAttribute('required');
                }
            }
        };

        variableTypeSelect.addEventListener('change', updateVariableTypeUI);

        // Toggle: match by indicator bank -> disable/clear explicit item selection
        const updateSourceItemMappingUi = () => {
            const matchByBank = !!(matchByIndicatorBankCheckbox && matchByIndicatorBankCheckbox.checked);
            if (!sourceFormItemSelect) return;
            if (matchByBank) {
                sourceFormItemSelect.value = '';
                sourceFormItemSelect.disabled = true;
                sourceFormItemSelect.classList.add('opacity-60', 'cursor-not-allowed');
                try { sourceFormItemSelect.removeAttribute('required'); } catch (_e) {}
            } else {
                sourceFormItemSelect.disabled = false;
                sourceFormItemSelect.classList.remove('opacity-60', 'cursor-not-allowed');
                // Only re-add required when in lookup mode; updateVariableTypeUI handles that too.
                try { sourceFormItemSelect.setAttribute('required', 'required'); } catch (_e) {}
            }
        };
        if (matchByIndicatorBankCheckbox) {
            matchByIndicatorBankCheckbox.addEventListener('change', updateSourceItemMappingUi);
        }

        // Show/hide fields based on lookup type (standard vs reverse)
        const updateLookupTypeUI = () => {
            const lookupType = lookupTypeSelect.value;
            if (lookupType === 'reverse') {
                standardLookupFields.classList.add('hidden');
                reverseLookupFields.classList.remove('hidden');
                // Remove required from entity scope
                entityScopeSelect.removeAttribute('required');
                // Add required to return format
                const returnFormatSelect = modal.querySelector('#return-format-select');
                if (returnFormatSelect) {
                    returnFormatSelect.setAttribute('required', 'required');
                }
            } else {
                standardLookupFields.classList.remove('hidden');
                reverseLookupFields.classList.add('hidden');
                // Add required to entity scope
                entityScopeSelect.setAttribute('required', 'required');
                // Remove required from return format
                const returnFormatSelect = modal.querySelector('#return-format-select');
                if (returnFormatSelect) {
                    returnFormatSelect.removeAttribute('required');
                }
            }
            // Update entity scope UI when switching lookup types
            updateEntityScopeUI();
        };

        lookupTypeSelect.addEventListener('change', updateLookupTypeUI);

        // Initialize lookup type if editing existing variable
        if (existingVar && existingVar.entity_scope === 'entities_containing') {
            lookupTypeSelect.value = 'reverse';
        }

        // Initialize UI - use setTimeout to ensure DOM is ready
        setTimeout(() => {
            updateVariableTypeUI();
            updateLookupTypeUI();
            updateSourceItemMappingUi();
            if (typeof updateMatrixColumnValidation === 'function') {
                updateMatrixColumnValidation();
            }
            if (useRowTotalCheckbox) {
                updateRowTotalUI();
            }
        }, 0);

        // Update assignments when template changes
        sourceTemplateSelect.addEventListener('change', async () => {
            const templateId = sourceTemplateSelect.value;
            sourceAssignmentSelect.replaceChildren();
            {
                const opt = document.createElement('option');
                opt.value = '';
                opt.textContent = 'Select assignment period...';
                sourceAssignmentSelect.appendChild(opt);
            }
            sourceFormItemSelect.replaceChildren();
            {
                const opt = document.createElement('option');
                opt.value = '';
                opt.textContent = 'Select form item...';
                sourceFormItemSelect.appendChild(opt);
            }

            if (templateId && this.assignmentsByTemplate[templateId]) {
                this.assignmentsByTemplate[templateId].forEach(assignment => {
                    const option = document.createElement('option');
                    option.value = assignment.period_name;
                    option.textContent = assignment.period_name;
                    if (existingVar?.source_assignment_period === assignment.period_name) {
                        option.selected = true;
                    }
                    sourceAssignmentSelect.appendChild(option);
                });
            }

            // Load form items
            if (templateId) {
                const items = await this.loadFormItemsForTemplate(parseInt(templateId));
                sourceFormItemSelect.replaceChildren();
                {
                    const opt = document.createElement('option');
                    opt.value = '';
                    opt.textContent = 'Select form item...';
                    sourceFormItemSelect.appendChild(opt);
                }
                items.forEach(item => {
                    const option = document.createElement('option');
                    option.value = item.id;
                    option.textContent = `${item.id}: ${item.label} (${item.item_type})`;
                    option.dataset.itemType = item.item_type || '';
                    if (existingVar?.source_form_item_id == item.id) {
                        option.selected = true;
                    }
                    sourceFormItemSelect.appendChild(option);
                });

                // Check if selected form item is a matrix when matrix column is set (after matrixColumnInput is defined)
                if (typeof updateMatrixColumnValidation === 'function') {
                    updateMatrixColumnValidation();
                }
            }
        });

        // Show/hide specific entity fields
        const specificEntityTypeSelect = modal.querySelector('#specific-entity-type-select');
        const specificEntityIdInput = modal.querySelector('#specific-entity-id-input');

        const updateEntityScopeUI = () => {
            const scope = entityScopeSelect.value;
            const previousScope = entityScopeSelect.dataset.previousScope || '';

            // Hide all conditional fields first
            specificEntityFields.classList.add('hidden');

            if (scope === 'specific') {
                specificEntityFields.classList.remove('hidden');
                // Make fields required
                if (specificEntityTypeSelect) {
                    specificEntityTypeSelect.setAttribute('required', 'required');
                    // Only clear values if switching FROM a different scope (not if already on 'specific')
                    if (previousScope && previousScope !== 'specific') {
                        // Preserve existing values if editing and they exist
                        if (!existingVar?.specific_entity_type) {
                            specificEntityTypeSelect.value = '';
                        }
                    }
                }
                if (specificEntityIdInput) {
                    specificEntityIdInput.setAttribute('required', 'required');
                    // Only clear values if switching FROM a different scope (not if already on 'specific')
                    if (previousScope && previousScope !== 'specific') {
                        // Preserve existing values if editing and they exist
                        if (!existingVar?.specific_entity_id) {
                            specificEntityIdInput.value = '';
                        }
                    }
                }

                // Update tooltip for specific scope
                const entityScopeTooltip = document.getElementById('entity-scope-tooltip');
                if (entityScopeTooltip) {
                    const tooltipText = entityScopeTooltip.querySelector('.tooltip-text');
                    if (tooltipText) {
                        tooltipText.textContent = 'Same Entity: Use data from the same entity as the current form. Any Entity: Use data from any entity\'s submission. The system will use the most recent submission from any entity. Specific Entity: Use data from a specific entity\'s submission. Required: You must specify the entity type and ID below.';
                    }
                }
            } else {
                // Remove required attributes from all fields
                if (specificEntityTypeSelect) {
                    specificEntityTypeSelect.removeAttribute('required');
                    // Only clear if switching away from 'specific'
                    if (previousScope === 'specific') {
                        specificEntityTypeSelect.value = '';
                    }
                }
                if (specificEntityIdInput) {
                    specificEntityIdInput.removeAttribute('required');
                    // Only clear if switching away from 'specific'
                    if (previousScope === 'specific') {
                        specificEntityIdInput.value = '';
                    }
                }
            }

            // Store current scope for next change
            entityScopeSelect.dataset.previousScope = scope;

            // Update tooltip for entity scope based on selected scope
            if (lookupTypeSelect && lookupTypeSelect.value === 'standard') {
                const entityScopeTooltip = document.getElementById('entity-scope-tooltip');
                if (entityScopeTooltip) {
                    const tooltipTextSpan = entityScopeTooltip.querySelector('.tooltip-text');
                    if (tooltipTextSpan) {
                        let tooltipText = '';
                        if (scope === 'same') {
                            tooltipText = 'Same Entity: Use data from the same entity as the current form (e.g., if filling a form for Country A, use Country A\'s previous submission). Most common for standard lookups. Any Entity: Use data from any entity\'s submission. The system will use the most recent submission from any entity. Useful for aggregated/central data. Specific Entity: Use data from a specific entity\'s submission (e.g., always use Country B\'s data regardless of current form). Useful for cross-entity lookups.';
                        } else if (scope === 'any') {
                            tooltipText = 'Same Entity: Use data from the same entity as the current form (e.g., if filling a form for Country A, use Country A\'s previous submission). Most common for standard lookups. Any Entity: Use data from any entity\'s submission. The system will use the most recent submission from any entity. Useful for aggregated/central data where multiple entities have submitted to the source assignment. Specific Entity: Use data from a specific entity\'s submission (e.g., always use Country B\'s data regardless of current form). Useful for cross-entity lookups.';
                        } else {
                            tooltipText = 'Same Entity: Use data from the same entity as the current form (e.g., if filling a form for Country A, use Country A\'s previous submission). Most common for standard lookups. Any Entity: Use data from any entity\'s submission. The system will use the most recent submission from any entity. Useful for aggregated/central data. Specific Entity: Use data from a specific entity\'s submission (e.g., always use Country B\'s data regardless of current form). Useful for cross-entity lookups.';
                        }
                        tooltipTextSpan.textContent = tooltipText;
                    }
                }
            }
        };

        entityScopeSelect.addEventListener('change', updateEntityScopeUI);

        // Remove validation error styling when fields are filled
        if (specificEntityTypeSelect) {
            specificEntityTypeSelect.addEventListener('change', function() {
                this.classList.remove('border-red-500');
            });
        }
        if (specificEntityIdInput) {
            specificEntityIdInput.addEventListener('input', function() {
                this.classList.remove('border-red-500');
            });
        }

        // Trigger template change if editing
        if (existingVar?.source_template_id) {
            sourceTemplateSelect.value = existingVar.source_template_id;
            sourceTemplateSelect.dispatchEvent(new Event('change'));
        }

        // Initialize entity scope UI (triggers if editing with specific or entities_containing scope)
        updateEntityScopeUI();

        // Update help text based on matrix column name
        const matrixColumnInput = modal.querySelector('#matrix-column-name-input');
        const matrixColumnHelpIcon = modal.querySelector('#matrix-column-help-icon');
        const useRowTotalCheckbox = modal.querySelector('#use-row-total-checkbox');

        // Define updateMatrixHelpText first (used by updateRowTotalUI and updateMatrixColumnValidation)
        const updateMatrixHelpText = () => {
            const useRowTotal = useRowTotalCheckbox && useRowTotalCheckbox.checked;
            const hasMatrixColumn = useRowTotal || (matrixColumnInput && matrixColumnInput.value.trim() !== '');
            const currentScope = entityScopeSelect.value;
            const selectedOption = sourceFormItemSelect.options[sourceFormItemSelect.selectedIndex];
            const itemType = selectedOption ? selectedOption.dataset.itemType : '';
            const isMatrix = itemType === 'matrix' || itemType === 'matrix_table';

            if (!matrixColumnHelpIcon) return;

            const tooltipTextSpan = matrixColumnHelpIcon.querySelector('.tooltip-text');
            if (!tooltipTextSpan) return;

            let tooltipText = 'Optional: If the source form item is a matrix, specify which column to lookup (e.g., "Planned" for "61_Planned"), or use Row total to read the sum of all columns for each row.';

            if (useRowTotal) {
                tooltipText = 'Row total: The variable will return the sum of all column values for each row in the source matrix (same as the row total when row totals are enabled).';
            } else if (hasMatrixColumn) {
                let scopeGuidance = '';
                let warningText = '';

                if (currentScope === 'same') {
                    scopeGuidance = 'Same Entity: The source matrix is stored in the same entity\'s submission (most common for matrix lookups). Example: If your matrix row is for Country B (ID: 61), and entity_scope is same, it will lookup 61_' + matrixColumnInput.value + ' in Country B\'s previous submission. The row_entity_id (61) from your current matrix row is used to find the specific cell in the source matrix.';
                } else if (currentScope === 'any') {
                    scopeGuidance = 'Any Entity: The source matrix is from a central/aggregated submission containing data about multiple entities. The variable will lookup values from any entity\'s row in the source matrix. Example: If your matrix row is for Country B (ID: 61), it will lookup 61_' + matrixColumnInput.value + ' in the source matrix from any entity\'s submission. The row_entity_id (61) from your current matrix row is used to find the specific cell.';
                    warningText = ' ⚠️ WARNING: When using Any Entity scope with matrix lookups, ensure the source matrix contains rows for all entities that appear in your current matrix. If a row_entity_id doesn\'t exist in the source matrix, the lookup will fail.';
                } else if (currentScope === 'specific') {
                    scopeGuidance = 'Specific Entity: The source matrix is from a specific entity\'s submission. Important: For matrix lookups with specific scope, the variable uses the specific entity\'s ID (not the current row\'s entity ID) to find the cell. Example: If configured for Country C (ID: 62), and your current matrix row is for Country B (ID: 61), it will lookup 62_' + matrixColumnInput.value + ' (using Country C\'s ID) in Country C\'s submission, not 61_' + matrixColumnInput.value + '. This means all rows in your current matrix will get the same value from the specific entity\'s row.';
                }

                tooltipText = 'Matrix lookup configured. The variable will lookup values from the "' + matrixColumnInput.value + '" column in the source matrix. How it works: entity_scope determines which entity\'s submission contains the source matrix. row_entity_id (from the current matrix row) is used to find the specific cell (e.g., "61_' + matrixColumnInput.value + '"). Entity Scope for matrix lookups: ' + scopeGuidance + (warningText || '');
            } else if (isMatrix && selectedOption && selectedOption.value) {
                tooltipText = 'Matrix Column Name: Since the selected form item is a matrix, you can optionally specify a column name to lookup specific values per row. Example: If you enter "Planned", the variable will lookup values like "61_Planned", "62_Planned" etc., where the number is the row entity ID from your current matrix row. Leave empty if you want to lookup the entire matrix row data or if this is not a matrix lookup.';
            }

            tooltipTextSpan.textContent = tooltipText;
        };

        // Validate matrix column name against selected form item type; show/hide row total option for matrix
        const updateMatrixColumnValidation = () => {
            const selectedOption = sourceFormItemSelect.options[sourceFormItemSelect.selectedIndex];
            const itemType = selectedOption ? selectedOption.dataset.itemType : '';
            const isMatrix = itemType === 'matrix' || itemType === 'matrix_table';
            const useRowTotal = useRowTotalCheckbox && useRowTotalCheckbox.checked;
            const matrixColumnName = (useRowTotal ? '_row_total' : (matrixColumnInput ? matrixColumnInput.value.trim() : ''));

            // Show/hide "Use row total" option only when source form item is a matrix
            const rowTotalLabel = useRowTotalCheckbox && useRowTotalCheckbox.closest('label');
            if (rowTotalLabel) {
                rowTotalLabel.style.display = isMatrix && selectedOption && selectedOption.value ? '' : 'none';
            }

            if (matrixColumnName && !isMatrix && selectedOption && selectedOption.value) {
                // Update tooltip to include warning
                if (matrixColumnHelpIcon) {
                    const tooltipTextSpan = matrixColumnHelpIcon.querySelector('.tooltip-text');
                    if (tooltipTextSpan) {
                        const currentText = tooltipTextSpan.textContent || '';
                        const warningText = ' ⚠️ WARNING: Matrix column name is set, but the selected form item is not a matrix type. Matrix column names only work with matrix form items.';
                        if (!currentText.includes('WARNING')) {
                            tooltipTextSpan.textContent = currentText + warningText;
                            const icon = matrixColumnHelpIcon.querySelector('i');
                            if (icon) icon.classList.add('text-yellow-600');
                        }
                    }
                }
            } else {
                // Remove warning from tooltip
                if (matrixColumnHelpIcon) {
                    const tooltipTextSpan = matrixColumnHelpIcon.querySelector('.tooltip-text');
                    if (tooltipTextSpan) {
                        let text = tooltipTextSpan.textContent || '';
                        text = text.replace(/ ⚠️ WARNING:.*$/, '');
                        tooltipTextSpan.textContent = text;
                        const icon = matrixColumnHelpIcon.querySelector('i');
                        if (icon) icon.classList.remove('text-yellow-600');
                    }
                }
            }
        };

        // Toggle matrix column input vs row total: when "Use row total" is checked, disable text input
        const updateRowTotalUI = () => {
            if (!useRowTotalCheckbox || !matrixColumnInput) return;
            const useRowTotal = useRowTotalCheckbox.checked;
            matrixColumnInput.disabled = useRowTotal;
            if (useRowTotal) {
                matrixColumnInput.value = '';
                matrixColumnInput.placeholder = 'Using row total (sum of all columns)';
            } else {
                matrixColumnInput.placeholder = 'e.g., Planned, Supported (or use Row total above)';
            }
            updateMatrixHelpText();
        };
        if (useRowTotalCheckbox) {
            useRowTotalCheckbox.addEventListener('change', updateRowTotalUI);
            updateRowTotalUI(); // Initial state when opening modal
        }

        // Listen for form item changes to validate matrix column
        sourceFormItemSelect.addEventListener('change', updateMatrixColumnValidation);

        if (matrixColumnInput) {
            matrixColumnInput.addEventListener('input', () => {
                updateMatrixHelpText();
                updateMatrixColumnValidation();
            });
            // Also update when entity scope changes
            entityScopeSelect.addEventListener('change', updateMatrixHelpText);
            updateMatrixHelpText();
        }

        // Form submission
        // Use button click to submit so we never trigger a native form submit (which would reload the page)
        const submitBtn = form.querySelector('.variable-form-submit');
        if (submitBtn) {
            submitBtn.addEventListener('click', () => {
                form.requestSubmit();
            });
        }
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(form);
            const varName = formData.get('variable_name');
            const variableType = formData.get('variable_type');
            const lookupType = formData.get('lookup_type');
            const entityScope = lookupType === 'reverse' ? 'entities_containing' : formData.get('entity_scope');

            // Validate metadata type
            if (variableType === 'metadata') {
                const metadataType = formData.get('metadata_type');
                if (!metadataType) {
                    window.showAlert('Please select a metadata type.', 'warning');
                    const metadataTypeSelect = modal.querySelector('#metadata-type-select');
                    if (metadataTypeSelect) {
                        metadataTypeSelect.focus();
                        metadataTypeSelect.classList.add('border-red-500');
                    }
                    return;
                }
            }

            // Validate lookup fields when type is 'lookup'
            if (variableType === 'lookup') {
                const sourceTemplateId = formData.get('source_template_id');
                const sourceAssignmentPeriod = formData.get('source_assignment_period');
                const sourceFormItemId = formData.get('source_form_item_id');
                const matchByBank = formData.get('match_by_indicator_bank') === 'on';
                const useRowTotal = formData.get('use_row_total') === 'on';
                const matrixColumnName = useRowTotal ? '_row_total' : (formData.get('matrix_column_name') || '').trim();

                if (!sourceTemplateId || !sourceAssignmentPeriod || (!matchByBank && !sourceFormItemId)) {
                    window.showAlert('Please fill in all required lookup fields (Source Template, Source Assignment Period, and Source Form Item — or enable indicator bank matching).', 'warning');
                    return;
                }

                // Validate matrix column / row total is only used with matrix form items
                if (matrixColumnName) {
                    const selectedOption = sourceFormItemSelect.options[sourceFormItemSelect.selectedIndex];
                    const itemType = selectedOption ? selectedOption.dataset.itemType : '';
                    const isMatrix = itemType === 'matrix' || itemType === 'matrix_table';

                    if (!isMatrix) {
                        const msg = 'Warning: ' + (useRowTotal
                                ? 'Row total is only available for matrix form items.'
                                : 'You have specified a matrix column name, but the selected form item is not a matrix type.') +
                            '\n\nMatrix column / row total only work with matrix form items. The variable may not work as expected.\n\nDo you want to continue anyway?';
                        const confirmed = await new Promise((resolve) => {
                        if (window.showConfirmation) {
                            window.showConfirmation(msg, () => resolve(true), () => resolve(false), 'Continue', 'Cancel', 'Continue anyway?');
                        } else {
                            resolve(false);
                        }
                        });
                        if (!confirmed) return;
                    }
                }
            }

            // Validate specific entity fields when scope is 'specific'
            if (variableType === 'lookup' && entityScope === 'specific') {
                const specificEntityType = formData.get('specific_entity_type');
                const specificEntityId = formData.get('specific_entity_id');

                if (!specificEntityType || !specificEntityId) {
                    window.showAlert('Please specify both Entity Type and Entity ID when using "Specific Entity" scope.', 'warning');
                    // Highlight missing fields
                    if (!specificEntityType && specificEntityTypeSelect) {
                        specificEntityTypeSelect.focus();
                        specificEntityTypeSelect.classList.add('border-red-500');
                    }
                    if (!specificEntityId && specificEntityIdInput) {
                        specificEntityIdInput.focus();
                        specificEntityIdInput.classList.add('border-red-500');
                    }
                    return;
                }

                // Validate entity ID is a positive integer
                const entityIdNum = parseInt(specificEntityId);
                if (isNaN(entityIdNum) || entityIdNum <= 0 || !Number.isInteger(parseFloat(specificEntityId))) {
                    window.showAlert('Entity ID must be a positive whole number (integer).', 'warning');
                    if (specificEntityIdInput) {
                        specificEntityIdInput.focus();
                        specificEntityIdInput.classList.add('border-red-500');
                    }
                    return;
                }
            }

            // Validate return_format for reverse lookup
            if (variableType === 'lookup' && lookupType === 'reverse') {
                const returnFormat = formData.get('return_format');
                if (!returnFormat) {
                    window.showAlert('Please select a return format for reverse lookup.', 'warning');
                    const returnFormatSelect = modal.querySelector('#return-format-select');
                    if (returnFormatSelect) {
                        returnFormatSelect.focus();
                        returnFormatSelect.classList.add('border-red-500');
                    }
                    return;
                }

                // Warn if source form item is not a matrix (entities_containing only works with matrices)
                const selectedOption = sourceFormItemSelect.options[sourceFormItemSelect.selectedIndex];
                const itemType = selectedOption ? selectedOption.dataset.itemType : '';
                const isMatrix = itemType === 'matrix' || itemType === 'matrix_table';

                if (!isMatrix || !selectedOption || !selectedOption.value) {
                    const msg = 'Warning: Reverse lookup is designed to work with matrix form items.\n\nIt searches through matrix data to find entities that contain the current assignment\'s entity ID in their matrix keys.\n\nIf the source form item is not a matrix, this variable may not work as expected.\n\nDo you want to continue anyway?';
                    const confirmed = await new Promise((resolve) => {
                        if (window.showConfirmation) {
                            window.showConfirmation(msg, () => resolve(true), () => resolve(false), 'Continue', 'Cancel', 'Continue anyway?');
                        } else {
                            resolve(false);
                        }
                    });
                    if (!confirmed) return;
                }
            }

            // Warn about entity_scope='any' with matrix lookups
            if (variableType === 'lookup') {
                const matrixColumnName = formData.get('matrix_column_name');
                if (entityScope === 'any' && matrixColumnName && matrixColumnName.trim() !== '') {
                    const msg = 'Warning: Using "Any Entity" scope with matrix lookups requires that the source matrix contains rows for all entities that appear in your current matrix.\n\nIf a row_entity_id from your current matrix doesn\'t exist in the source matrix, the lookup will fail for that row.\n\nAre you sure you want to continue?';
                    const confirmed = await new Promise((resolve) => {
                        if (window.showConfirmation) {
                            window.showConfirmation(msg, () => resolve(true), () => resolve(false), 'Continue', 'Cancel', 'Continue anyway?');
                        } else {
                            resolve(false);
                        }
                    });
                    if (!confirmed) return;
                }
            }

            // If editing and the name changed, delete the old variable entry
            if (editVarName && varName !== editVarName) {
                delete this.variables[editVarName];
            }

            // Build variable config based on type
            const variableConfig = {
                variable_type: variableType,
                display_name: formData.get('display_name') || varName,
                default_value: formData.get('default_value') || null,
            };

            if (variableType === 'metadata') {
                variableConfig.metadata_type = formData.get('metadata_type');
            } else {
                // Lookup type - include all lookup-specific fields
                variableConfig.source_template_id = parseInt(formData.get('source_template_id'));
                variableConfig.source_assignment_period = formData.get('source_assignment_period');
                variableConfig.match_by_indicator_bank = (formData.get('match_by_indicator_bank') === 'on');
                variableConfig.source_form_item_id = variableConfig.match_by_indicator_bank
                    ? null
                    : (formData.get('source_form_item_id') ? parseInt(formData.get('source_form_item_id')) : null);
                variableConfig.entity_scope = entityScope;
                variableConfig.specific_entity_type = formData.get('specific_entity_type') || null;
                variableConfig.specific_entity_id = formData.get('specific_entity_id') ? parseInt(formData.get('specific_entity_id')) : null;
                // lookup_entity_id is not stored - it's automatically set from assignment context at resolution time
                variableConfig.return_format = formData.get('return_format') || (entityScope === 'entities_containing' ? 'auto_load_format' : null);
                // Use row total: reserved value _row_total so variable reads sum of all columns for each row
                variableConfig.matrix_column_name = (formData.get('use_row_total') === 'on')
                    ? '_row_total'
                    : (formData.get('matrix_column_name') || null);
                variableConfig.format_thousands_separator = formData.get('format_thousands_separator') === 'on';
                variableConfig.format_decimal_places = formData.get('format_decimal_places') || 'auto';
            }

            this.variables[varName] = variableConfig;

            await this.saveVariables();
            closeModal();
            this.renderVariablesList(); // Refresh the table
            this.updateVariablesButton(); // Update button count
        });

        // Cancel button
        modal.querySelector('.cancel-variable-form').addEventListener('click', () => {
            closeModal();
        });
    }

    /**
     * Attach handlers for custom info tooltips within a container.
     */
    attachTooltipHandlers(container) {
        if (!container) return;
        const tooltips = container.querySelectorAll('.custom-info-tooltip');
        tooltips.forEach((el) => {
            el.addEventListener('mouseenter', () => {
                if (window.positionTooltip) window.positionTooltip(el);
            });
            el.addEventListener('mouseleave', () => {
                if (window.hideTooltip) window.hideTooltip(el);
            });
        });
    }

    /**
     * Save variables
     */
    async saveVariables() {
        try {
            if (!this.versionId) {
                throw new Error('Version ID is required. Please refresh the page and try again.');
            }

            const fetchFn = (window.getApiFetch && window.getApiFetch()) || null;
            const data = fetchFn
                ? await fetchFn(`/admin/templates/${this.templateId}/variables?version_id=${this.versionId}`, {
                    method: 'POST',
                    body: JSON.stringify({ variables: this.variables })
                })
                : await (async () => {
                    const r = await ((window.getFetch && window.getFetch()) || fetch)(`/admin/templates/${this.templateId}/variables?version_id=${this.versionId}`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ variables: this.variables })
                    });
                    if (!r.ok) throw (window.httpErrorSync && window.httpErrorSync(r)) || new Error(`HTTP ${r.status}`);
                    return r.json();
                })();
            if (data.success) {
                // Show success message
                const alert = document.createElement('div');
                alert.className = 'fixed top-4 right-4 bg-green-500 text-white px-4 py-2 rounded shadow-lg z-50';
                alert.textContent = 'Variables saved successfully';
                document.body.appendChild(alert);
                setTimeout(() => alert.remove(), 3000);
            } else {
                window.showAlert('Error saving variables: ' + (data.message || 'Unknown error'), 'error');
            }
        } catch (error) {
            console.error('Error saving variables:', error);
            window.showAlert('Error saving variables: ' + error.message, 'error');
        }
    }

    /**
     * Duplicate variable: create a copy with a unique name
     */
    async duplicateVariable(varName) {
        const sourceConfig = this.variables[varName];
        if (!sourceConfig) return;

        const baseName = varName + '_copy';
        let newName = baseName;
        let n = 1;
        while (Object.prototype.hasOwnProperty.call(this.variables, newName)) {
            n += 1;
            newName = baseName + (n > 1 ? '_' + n : '');
        }

        const copy = JSON.parse(JSON.stringify(sourceConfig));
        if (copy.display_name) {
            copy.display_name = (copy.display_name || varName) + ' (copy)';
        }
        this.variables[newName] = copy;
        await this.saveVariables();
        this.renderVariablesList();
        this.updateVariablesButton();
    }

    /**
     * Delete variable
     */
    async deleteVariable(varName) {
        const msg = `Are you sure you want to delete the variable [${varName}]?`;
        const doDelete = async () => {
            delete this.variables[varName];
            await this.saveVariables();
            this.renderVariablesList();
            this.updateVariablesButton();
        };
        if (window.showDangerConfirmation) {
            window.showDangerConfirmation(msg, () => { void doDelete(); }, null, 'Delete', 'Cancel', 'Confirm Delete');
        } else if (window.showConfirmation) {
            window.showConfirmation(msg, () => { void doDelete(); }, null, 'Delete', 'Cancel', 'Confirm Delete');
        } else {
            console.warn('Confirmation dialog not available:', msg);
        }
    }

    /**
     * Initialize the variables manager
     */
    async init() {
        await this.loadVariableOptions();
        this.renderVariablesList();
        this.updateVariablesButton(); // Initialize button count and styling

        // Template Variables Modal handlers
        const templateVariablesBtn = document.getElementById('template-variables-btn');
        const templateVariablesModal = document.getElementById('template-variables-modal');

        if (templateVariablesBtn && templateVariablesModal) {
            const modalController = (window.ModalUtils && window.ModalUtils.makeModal(templateVariablesModal, { closeSelector: '.close-modal' })) || {
                openModal: () => templateVariablesModal.classList.remove('hidden'),
                closeModal: () => templateVariablesModal.classList.add('hidden')
            };

            templateVariablesBtn.addEventListener('click', () => {
                modalController.openModal();
                this.renderVariablesList(); // Refresh the list when opening
            });
        }

        // Add variable button (inside modal)
        document.getElementById('add-variable-btn')?.addEventListener('click', () => {
            this.showVariableForm();
        });

        // Edit/Duplicate/Delete buttons (delegated)
        document.getElementById('variables-list-container')?.addEventListener('click', (e) => {
            if (e.target.closest('.edit-variable-btn')) {
                const varName = e.target.closest('.edit-variable-btn').dataset.variableName;
                this.showVariableForm(varName);
            } else if (e.target.closest('.duplicate-variable-btn')) {
                const varName = e.target.closest('.duplicate-variable-btn').dataset.variableName;
                this.duplicateVariable(varName);
            } else if (e.target.closest('.delete-variable-btn')) {
                const varName = e.target.closest('.delete-variable-btn').dataset.variableName;
                this.deleteVariable(varName);
            }
        });
    }
}
