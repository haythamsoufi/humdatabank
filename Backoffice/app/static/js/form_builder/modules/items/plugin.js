// Plugin item logic extracted from item-modal.js

const truthyStrings = new Set(['true', '1', 'yes', 'on']);
const falsyStrings = new Set(['false', '0', 'no', 'off', '']);

const isTruthyConfigValue = (value) => {
    if (typeof value === 'boolean') return value;
    if (typeof value === 'number') return value !== 0;
    if (typeof value === 'string') {
        const normalized = value.trim().toLowerCase();
        if (truthyStrings.has(normalized)) return true;
        if (falsyStrings.has(normalized)) return false;
    }
    if (value === null || value === undefined) return false;
    return Boolean(value);
};

const shouldCheckCheckbox = (configValue, optionValue) => {
    if (Array.isArray(configValue)) {
        return configValue.some(val => String(val) === String(optionValue));
    }
    if (typeof configValue === 'string') {
        const normalized = configValue.trim().toLowerCase();
        if (optionValue !== undefined && optionValue !== null && optionValue !== '') {
            if (String(configValue) === String(optionValue)) {
                return true;
            }
            if (truthyStrings.has(normalized)) return true;
            if (falsyStrings.has(normalized)) return false;
            return false;
        }
        if (truthyStrings.has(normalized)) return true;
        if (falsyStrings.has(normalized)) return false;
    }
    return isTruthyConfigValue(configValue);
};

export const PluginItem = {
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

        const doc = new DOMParser().parseFromString(html, 'text/html');
        const root = doc.body;
        if (!root) return;

        // Remove script-like elements
        root.querySelectorAll('script, iframe, object, embed').forEach((el) => el.remove());

        // Strip dangerous attributes
        root.querySelectorAll('*').forEach((el) => {
            [...el.attributes].forEach((attr) => {
                const name = String(attr.name || '').toLowerCase();
                const value = String(attr.value || '').trim();
                const lower = value.toLowerCase();

                if (name.startsWith('on')) {
                    el.removeAttribute(attr.name);
                    return;
                }

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

    setup(modalElement, itemType, pendingPluginData) {
        console.log('[PluginItem] setup called', {
            itemType,
            hasPendingData: !!pendingPluginData,
            modalElement: modalElement ? 'found' : 'missing'
        });

        this.currentItemType = itemType;
        this.pendingPluginData = pendingPluginData || null;
        this.loadBaseTemplate(modalElement)
            .then(() => {
                console.log('[PluginItem] setup: Base template loaded');
                const customFieldTypesData = document.getElementById('custom-field-types-data');
                if (!customFieldTypesData) {
                    console.error('[PluginItem] setup: custom-field-types-data element not found');
                    return;
                }
                const fieldTypeId = itemType.replace('plugin_', '');
                console.log('[PluginItem] setup: Looking for field type', { fieldTypeId });
                const customFieldTypes = JSON.parse(customFieldTypesData.textContent);
                const fieldType = customFieldTypes.find(ft => ft.type_id === fieldTypeId);
                if (!fieldType) {
                    console.error('[PluginItem] setup: Field type not found', {
                        fieldTypeId,
                        availableTypes: customFieldTypes.map(ft => ft.type_id)
                    });
                    return;
                }
                console.log('[PluginItem] setup: Field type found', {
                    typeId: fieldType.type_id,
                    displayName: fieldType.display_name
                });

                let existingConfig = null;
                if (this.pendingPluginData) {
                    if (this.pendingPluginData.config && this.pendingPluginData.config.plugin_config) {
                        existingConfig = this.pendingPluginData.config.plugin_config;
                    } else if (this.pendingPluginData.plugin_config) {
                        existingConfig = this.pendingPluginData.plugin_config;
                    }
                    console.log('[PluginItem] setup: Extracted existing config', {
                        configKeys: existingConfig ? Object.keys(existingConfig) : [],
                        config: existingConfig
                    });
                } else {
                    console.log('[PluginItem] setup: No pending plugin data, using defaults');
                }

                this.loadConfiguration(modalElement, fieldType, existingConfig);
                this.setupEventListeners(modalElement, fieldType);
            })
            .catch((err) => {
                console.error('[PluginItem] setup: Error loading base template', err);
            });
    },

    teardown(modalElement) {
        if (!modalElement) return;
        if (modalElement._pluginChangeHandler) {
            document.removeEventListener('change', modalElement._pluginChangeHandler);
            modalElement._pluginChangeHandler = null;
        }
    },

    loadBaseTemplate(modalElement) {
        return new Promise((resolve, reject) => {
            const container = document.getElementById('item-plugin-fields-container');
            if (!container) return reject('Plugin fields container not found');
            const _pfetch = (window.getFetch && window.getFetch()) || fetch;
            _pfetch('/admin/api/plugins/base-template', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                }
            })
            .then(r => r.text())
            .then(html => {
                this.setSanitizedHtml(container, html);
                const pluginFields = document.getElementById('item-plugin-fields');
                if (pluginFields) {
                    Utils.showElement(pluginFields);
                    const pluginLabel = pluginFields.querySelector('#item-plugin-label');
                    if (pluginLabel) pluginLabel.setAttribute('required', 'required');
                }
                if (this.pendingPluginData) this.populateBasicFields(modalElement, this.pendingPluginData);
                resolve();
            })
            .catch(err => {
                console.error('Error loading base plugin template:', err);
                container.replaceChildren();
                const fallbackDoc = new DOMParser().parseFromString(`
                    <div id="item-plugin-fields" class="hidden">
                        <div class="mb-4">
                            <div class="flex items-center justify-between mb-2">
                                <label for="item-plugin-label" class="block text-gray-700 text-sm font-semibold">Field Label</label>
                                <button type="button" id="plugin-translations-btn" class="inline-flex items-center text-blue-600 hover:text-blue-800 text-sm font-medium" title="Add translations">
                                    <i class="fas fa-language w-4 h-4 mr-1"></i>
                                    Translations
                                </button>
                            </div>
                            <textarea name="label" id="item-plugin-label" class="shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full sm:text-sm border-gray-300 rounded-md" rows="3" placeholder="Field Label" required autocomplete="off"></textarea>
                        </div>
                        <div class="mb-4">
                            <label for="item-plugin-description" class="block text-gray-700 text-sm font-semibold mb-2">Description (Optional)</label>
                            <textarea name="description" id="item-plugin-description" class="shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full sm:text-sm border-gray-300 rounded-md" rows="3" placeholder="Description (Optional)" autocomplete="off"></textarea>
                        </div>
                        <div id="plugin-configuration-container" class="mb-4"></div>
                        <input type="hidden" name="label_translations" id="item-plugin-label-translations" value="{}">
                        <input type="hidden" name="description_translations" id="item-plugin-description-translations" value="{}">
                        <input type="hidden" name="plugin_config" id="item-plugin-config" value="{}">
                    </div>
                `, 'text/html');
                if (fallbackDoc.body) {
                    const fragment = document.createDocumentFragment();
                    while (fallbackDoc.body.firstChild) fragment.appendChild(fallbackDoc.body.firstChild);
                    container.appendChild(fragment);
                }
                const pluginFields = document.getElementById('item-plugin-fields');
                if (pluginFields) {
                    Utils.showElement(pluginFields);
                    const pluginLabel = pluginFields.querySelector('#item-plugin-label');
                    if (pluginLabel) pluginLabel.setAttribute('required', 'required');
                }
                if (this.pendingPluginData) this.populateBasicFields(modalElement, this.pendingPluginData);
                resolve();
            });
        });
    },

    loadConfiguration(modalElement, fieldType, existingConfig = null) {
        console.log('[PluginItem] loadConfiguration called', {
            fieldType: fieldType?.type_id || fieldType,
            hasExistingConfig: !!existingConfig,
            modalElement: modalElement ? 'found' : 'missing'
        });

        const container = document.getElementById('plugin-configuration-container');
        if (!container) {
            console.error('[PluginItem] loadConfiguration: plugin-configuration-container not found');
            return;
        }
        console.log('[PluginItem] loadConfiguration: Container found', {
            containerId: container.id,
            currentContent: container.innerHTML.substring(0, 100) + '...'
        });

        container.replaceChildren();
        {
            const loading = document.createElement('div');
            loading.className = 'text-gray-500 text-sm';
            loading.textContent = 'Loading configuration...';
            container.appendChild(loading);
        }
        const requestData = {
            method: existingConfig ? 'POST' : 'GET',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
            }
        };
        if (existingConfig) requestData.body = JSON.stringify({ existing_config: existingConfig });
        const apiUrl = `/admin/api/plugins/field-types/${fieldType.type_id}/render-builder`;
        console.log('[PluginItem] loadConfiguration: Fetching configuration', {
            url: apiUrl,
            method: requestData.method,
            hasBody: !!requestData.body
        });

        const _pfetch = (window.getFetch && window.getFetch()) || fetch;
        _pfetch(apiUrl, requestData)
            .then(r => {
                console.log('[PluginItem] loadConfiguration: API response received', {
                    status: r.status,
                    statusText: r.statusText,
                    ok: r.ok
                });
                return r.json();
            })
            .then(data => {
                console.log('[PluginItem] loadConfiguration: API data parsed', {
                    success: data.success,
                    hasHtml: !!data.html,
                    htmlLength: data.html?.length || 0,
                    error: data.error || 'none'
                });

                if (!data.success) {
                    console.error('[PluginItem] loadConfiguration: API returned error', data.error);
                    container.replaceChildren();
                    const err = document.createElement('div');
                    err.className = 'text-red-500 text-sm';
                    err.textContent = `Error loading configuration: ${data && data.error ? data.error : ''}`;
                    container.appendChild(err);
                    return;
                }

                console.log('[PluginItem] loadConfiguration: Setting sanitized HTML', {
                    htmlPreview: data.html.substring(0, 200) + '...',
                    hasPluginOptions: data.html.includes('plugin-option-to-properties'),
                    hasPluginFieldBuilder: data.html.includes('plugin-field-builder'),
                    hasCustomFieldConfig: data.html.includes('custom-field-config'),
                    fullHtml: data.html
                });

                // Check if we got the custom template or fallback
                if (data.html.includes('custom-field-config') && !data.html.includes('plugin-option-to-properties')) {
                    console.error('[PluginItem] loadConfiguration: WARNING - Received fallback HTML instead of custom template!', {
                        htmlLength: data.html.length,
                        html: data.html
                    });
                }

                this.setSanitizedHtml(container, data.html);

                // Log what was actually inserted
                const insertedOptions = container.querySelectorAll('.plugin-option-to-properties');
                const insertedBuilder = container.querySelector('.plugin-field-builder');
                const insertedCustomConfig = container.querySelector('.custom-field-config');
                console.log('[PluginItem] loadConfiguration: After setSanitizedHtml', {
                    insertedOptionsCount: insertedOptions.length,
                    containerChildren: container.children.length,
                    hasPluginFieldBuilder: !!insertedBuilder,
                    hasCustomFieldConfig: !!insertedCustomConfig,
                    containerHTML: container.innerHTML.substring(0, 500) + '...'
                });
                if (data.script) {
                    // DEPRECATED: Inline script execution is a CSP blocker and is deprecated.
                    // The backend currently returns script: None, so this code path is inactive.
                    // Future plugins should use static JS files loaded via <script src="..."> or ES modules.
                    // See: Backoffice/docs/PLUGIN_SCRIPT_MIGRATION_PLAN.md
                    console.warn('[PluginItem] Plugin returned script text, which is deprecated and will be removed. Use static JS files instead.');
                    const script = document.createElement('script');
                    script.textContent = data.script;
                    container.appendChild(script);
                }
                if (data.script_url) {
                    const script = document.createElement('script');
                    script.src = data.script_url;
                    script.type = data.script_type || 'text/javascript';
                    script.async = false;
                    container.appendChild(script);
                }
                this.loadDependencies(fieldType);
                console.log('[PluginItem] loadConfiguration: Starting integration', {
                    fieldType: fieldType?.type_id || fieldType,
                    hasExistingConfig: !!existingConfig,
                    existingConfigKeys: existingConfig ? Object.keys(existingConfig) : []
                });

                // Integrate options into properties section - use setTimeout to ensure DOM is ready
                // The function itself uses requestAnimationFrame for additional safety
                // Populate config fields AFTER integration so cloned fields in Properties are also populated
                setTimeout(() => {
                    console.log('[PluginItem] loadConfiguration: setTimeout callback executing');
                    this.integrateOptionsIntoProperties(modalElement, fieldType).then(() => {
                        console.log('[PluginItem] loadConfiguration: Integration promise resolved');
                        // Populate config fields after integration completes
                        if (existingConfig) {
                            console.log('[PluginItem] loadConfiguration: Populating config fields', {
                                configKeys: Object.keys(existingConfig)
                            });
                            this.populateConfigFields(modalElement, existingConfig);
                        } else {
                            console.log('[PluginItem] loadConfiguration: No existing config to populate');
                        }
                    }).catch(err => {
                        console.error('[PluginItem] loadConfiguration: Integration promise rejected', err);
                    });
                }, 0);
                setTimeout(() => window.ItemModal && window.ItemModal.checkModalScroll && window.ItemModal.checkModalScroll(), 100);
            })
            .catch(() => {
                container.replaceChildren();
                const err = document.createElement('div');
                err.className = 'text-red-500 text-sm';
                err.textContent = 'Error loading configuration';
                container.appendChild(err);
            });
    },

    populateBasicFields(modalElement, itemData) {
        const labelInput = document.getElementById('item-plugin-label');
        const descriptionInput = document.getElementById('item-plugin-description');
        if (labelInput && itemData.label) labelInput.value = itemData.label;
        if (descriptionInput && itemData.description) descriptionInput.value = itemData.description;
        const labelTranslationsInput = document.getElementById('item-plugin-label-translations');
        const descriptionTranslationsInput = document.getElementById('item-plugin-description-translations');
        if (labelTranslationsInput && itemData.label_translations) labelTranslationsInput.value = JSON.stringify(itemData.label_translations);
        if (descriptionTranslationsInput && itemData.description_translations) descriptionTranslationsInput.value = JSON.stringify(itemData.description_translations);
    },

    populateConfigFields(modalElement, config) {
        console.log('[PluginItem] populateConfigFields called', {
            configKeys: Object.keys(config),
            config: config
        });

        const container = document.getElementById('plugin-configuration-container');
        if (!container) {
            console.error('[PluginItem] populateConfigFields: Container not found');
            return;
        }

        const configFields = container.querySelectorAll('input, select, textarea');
        console.log('[PluginItem] populateConfigFields: Found fields in container', {
            fieldCount: configFields.length,
            fieldNames: Array.from(configFields).map(f => f.name || 'unnamed')
        });

        // Special handling for operation_types FIRST (before general population)
        // This prevents the general logic from incorrectly setting checkboxes
        if (config.operation_types) {
            let operationTypesList = [];
            if (Array.isArray(config.operation_types)) {
                operationTypesList = config.operation_types;
            } else if (typeof config.operation_types === 'string') {
                operationTypesList = [config.operation_types];
            } else if (typeof config.operation_types === 'boolean' && config.operation_types) {
                // Legacy: if it's just true, default to All
                operationTypesList = ['All'];
            }

            console.log('[PluginItem] populateConfigFields: Populating operation_types FIRST', {
                rawValue: config.operation_types,
                normalizedList: operationTypesList
            });

            // First, uncheck all operation_types checkboxes
            container.querySelectorAll('[name="operation_types"]').forEach(cb => {
                cb.checked = false;
            });

            // Then check only the ones in the list
            operationTypesList.forEach(operationType => {
                const checkbox = container.querySelector(`[name="operation_types"][value="${operationType}"]`);
                if (checkbox) {
                    checkbox.checked = true;
                    checkbox.dispatchEvent(new Event('change', { bubbles: true }));
                    console.log('[PluginItem] populateConfigFields: Checked operation_type checkbox', {
                        value: operationType,
                        checkbox: checkbox
                    });
                } else {
                    console.warn('[PluginItem] populateConfigFields: operation_type checkbox not found', {
                        value: operationType,
                        availableCheckboxes: Array.from(container.querySelectorAll('[name="operation_types"]')).map(cb => cb.value)
                    });
                }
            });
        }

        // Special handling for allowed_geometry_types array field
        if (config.allowed_geometry_types && Array.isArray(config.allowed_geometry_types)) {
            config.allowed_geometry_types.forEach(geometryType => {
                const checkbox = container.querySelector(`[name="allowed_geometry_types_${geometryType}"]`);
                if (checkbox) checkbox.checked = true;
            });
        }

        // Now populate all other fields (excluding operation_types since we already handled it)
        let populatedCount = 0;
        configFields.forEach(field => {
            // Skip operation_types checkboxes - we already handled them
            if (field.name === 'operation_types') {
                return;
            }

            if (field.name && field.name.trim() && Object.prototype.hasOwnProperty.call(config, field.name)) {
                const value = config[field.name];
                const oldValue = field.type === 'checkbox' ? field.checked : field.value;

                if (field.type === 'checkbox') {
                    field.checked = shouldCheckCheckbox(value, field.value);
                } else if (field.type === 'radio') {
                    field.checked = String(field.value) === String(value);
                } else {
                    field.value = value ?? '';
                }

                const newValue = field.type === 'checkbox' ? field.checked : field.value;
                console.log('[PluginItem] populateConfigFields: Populated field', {
                    name: field.name,
                    type: field.type,
                    oldValue,
                    newValue,
                    configValue: value
                });

                field.dispatchEvent(new Event('change', { bubbles: true }));
                populatedCount++;
            }
        });

        console.log('[PluginItem] populateConfigFields: Populated fields in container', {
            populatedCount,
            totalFields: configFields.length
        });
        const propertiesSection = modalElement.querySelector('.mb-3.border-t.border-gray-200.pt-4');
        if (propertiesSection) {
            const propertiesContent = propertiesSection.querySelector('.grid.grid-cols-2.gap-6.items-center');
            if (propertiesContent) {
                const propertiesPluginOptions = propertiesContent.querySelectorAll('.plugin-option-to-properties input, .plugin-option-to-properties select, .plugin-option-to-properties textarea');
                console.log('[PluginItem] populateConfigFields: Found cloned fields in Properties', {
                    clonedFieldCount: propertiesPluginOptions.length,
                    clonedFieldNames: Array.from(propertiesPluginOptions).map(f => f.name || 'unnamed')
                });

                let clonedPopulatedCount = 0;
                propertiesPluginOptions.forEach(field => {
                    // Skip operation_types - we handle them separately below
                    if (field.name === 'operation_types') {
                        return;
                    }

                    if (field.name && field.name.trim() && Object.prototype.hasOwnProperty.call(config, field.name)) {
                        const value = config[field.name];
                        const oldValue = field.type === 'checkbox' ? field.checked : field.value;

                        if (field.type === 'checkbox') {
                            field.checked = shouldCheckCheckbox(value, field.value);
                        } else if (field.type === 'radio') {
                            field.checked = String(field.value) === String(value);
                        } else {
                            field.value = value ?? '';
                        }

                        const newValue = field.type === 'checkbox' ? field.checked : field.value;
                        console.log('[PluginItem] populateConfigFields: Populated cloned field', {
                            name: field.name,
                            type: field.type,
                            oldValue,
                            newValue,
                            configValue: value
                        });

                        const originalField = container.querySelector(`[name="${field.name}"]`);
                        if (originalField) {
                            if (originalField.type === 'checkbox') {
                                originalField.checked = shouldCheckCheckbox(value, originalField.value);
                            } else if (originalField.type === 'radio') {
                                originalField.checked = String(originalField.value) === String(value);
                            } else {
                                originalField.value = value ?? '';
                            }
                            console.log('[PluginItem] populateConfigFields: Synced original field', {
                                name: field.name,
                                clonedValue: newValue,
                                originalValue: originalField.type === 'checkbox' ? originalField.checked : originalField.value
                            });
                        } else {
                            console.warn('[PluginItem] populateConfigFields: Original field not found for cloned field', {
                                name: field.name
                            });
                        }
                        clonedPopulatedCount++;
                    }
                });

                // Special handling for operation_types in cloned fields
                if (config.operation_types) {
                    let operationTypesList = [];
                    if (Array.isArray(config.operation_types)) {
                        operationTypesList = config.operation_types;
                    } else if (typeof config.operation_types === 'string') {
                        operationTypesList = [config.operation_types];
                    } else if (typeof config.operation_types === 'boolean' && config.operation_types) {
                        operationTypesList = ['All'];
                    }

                    console.log('[PluginItem] populateConfigFields: Populating cloned operation_types', {
                        rawValue: config.operation_types,
                        normalizedList: operationTypesList
                    });

                    // First, uncheck all cloned operation_types checkboxes
                    propertiesContent.querySelectorAll('[name="operation_types"]').forEach(cb => {
                        cb.checked = false;
                    });

                    // Then check only the ones in the list
                    operationTypesList.forEach(operationType => {
                        const clonedCheckbox = propertiesContent.querySelector(`[name="operation_types"][value="${operationType}"]`);
                        if (clonedCheckbox) {
                            clonedCheckbox.checked = true;
                            clonedCheckbox.dispatchEvent(new Event('change', { bubbles: true }));
                            console.log('[PluginItem] populateConfigFields: Checked cloned operation_type checkbox', {
                                value: operationType
                            });
                        } else {
                            console.warn('[PluginItem] populateConfigFields: Cloned operation_type checkbox not found', {
                                value: operationType,
                                availableCheckboxes: Array.from(propertiesContent.querySelectorAll('[name="operation_types"]')).map(cb => cb.value)
                            });
                        }
                    });
                }
                console.log('[PluginItem] populateConfigFields: Populated cloned fields in Properties', {
                    clonedPopulatedCount,
                    totalClonedFields: propertiesPluginOptions.length
                });
            } else {
                console.warn('[PluginItem] populateConfigFields: Properties content grid not found');
            }
        } else {
            console.warn('[PluginItem] populateConfigFields: Properties section not found');
        }

        console.log('[PluginItem] populateConfigFields: Complete', {
            totalPopulated: populatedCount,
            configKeys: Object.keys(config)
        });
    },

    loadDependencies(fieldType) {
        if (fieldType.css_dependencies) {
            fieldType.css_dependencies.forEach(cssUrl => {
                if (!document.querySelector(`link[href="${cssUrl}"]`)) {
                    const link = document.createElement('link');
                    link.rel = 'stylesheet';
                    link.href = cssUrl;
                    document.head.appendChild(link);
                }
            });
        }
        if (fieldType.js_dependencies) {
            fieldType.js_dependencies.forEach(jsUrl => {
                if (!document.querySelector(`script[src="${jsUrl}"]`)) {
                    const script = document.createElement('script');
                    script.src = jsUrl;
                    script.async = true;
                    document.head.appendChild(script);
                }
            });
        }
    },

    integrateOptionsIntoProperties(modalElement, fieldType) {
        console.log('[PluginItem] integrateOptionsIntoProperties called', {
            fieldType: fieldType?.type_id || fieldType,
            modalElement: modalElement ? 'found' : 'missing',
            timestamp: new Date().toISOString()
        });

        // Use requestAnimationFrame to ensure DOM is fully updated after setSanitizedHtml
        return new Promise((resolve) => {
            requestAnimationFrame(() => {
                console.log('[PluginItem] requestAnimationFrame callback executing');
                this._doIntegrateOptionsIntoProperties(modalElement, fieldType, 0, resolve);
            });
        });
    },

    _doIntegrateOptionsIntoProperties(modalElement, fieldType, retryCount = 0, resolve = null) {
        const maxRetries = 3;
        const debugPrefix = `[PluginItem] [Retry ${retryCount}/${maxRetries}]`;

        console.log(`${debugPrefix} Starting integration check`, {
            modalElement: modalElement ? 'found' : 'missing',
            fieldType: fieldType?.type_id || fieldType
        });

        const propertiesSection = modalElement.querySelector('.mb-3.border-t.border-gray-200.pt-4');
        if (!propertiesSection) {
            console.warn(`${debugPrefix} Properties section not found`, {
                selector: '.mb-3.border-t.border-gray-200.pt-4',
                modalClasses: modalElement?.className || 'N/A',
                availableSections: Array.from(modalElement?.querySelectorAll('.mb-3') || []).map(el => el.className)
            });
            if (retryCount < maxRetries) {
                console.log(`${debugPrefix} Retrying in 50ms...`);
                setTimeout(() => this._doIntegrateOptionsIntoProperties(modalElement, fieldType, retryCount + 1, resolve), 50);
            } else {
                console.error('[PluginItem] Properties section not found after max retries');
                if (resolve) resolve();
            }
            return;
        }
        console.log(`${debugPrefix} Properties section found`);

        const pluginContainer = document.getElementById('plugin-configuration-container');
        if (!pluginContainer) {
            console.warn(`${debugPrefix} Plugin configuration container not found`, {
                containerId: 'plugin-configuration-container',
                availableContainers: Array.from(document.querySelectorAll('[id*="plugin"]') || []).map(el => el.id)
            });
            if (retryCount < maxRetries) {
                console.log(`${debugPrefix} Retrying in 50ms...`);
                setTimeout(() => this._doIntegrateOptionsIntoProperties(modalElement, fieldType, retryCount + 1, resolve), 50);
            } else {
                console.error('[PluginItem] Plugin configuration container not found after max retries');
                if (resolve) resolve();
            }
            return;
        }
        console.log(`${debugPrefix} Plugin configuration container found`, {
            containerHTML: pluginContainer.innerHTML.substring(0, 200) + '...'
        });

        const pluginOptions = pluginContainer.querySelectorAll('.plugin-option-to-properties');
        console.log(`${debugPrefix} Plugin options found`, {
            count: pluginOptions.length,
            options: Array.from(pluginOptions).map(opt => ({
                className: opt.className,
                hasInput: !!opt.querySelector('input, select, textarea'),
                inputName: opt.querySelector('input, select, textarea')?.name || 'N/A'
            }))
        });

        if (pluginOptions.length === 0) {
            console.log(`${debugPrefix} No plugin options to integrate (this is OK for plugins without options)`);
            if (resolve) resolve();
            return;
        }

        const propertiesContent = propertiesSection.querySelector('.grid.grid-cols-2.gap-6.items-center');
        if (!propertiesContent) {
            console.warn(`${debugPrefix} Properties content grid not found`, {
                selector: '.grid.grid-cols-2.gap-6.items-center',
                propertiesSectionHTML: propertiesSection.innerHTML.substring(0, 300) + '...',
                availableGrids: Array.from(propertiesSection.querySelectorAll('.grid') || []).map(el => el.className)
            });
            if (retryCount < maxRetries) {
                console.log(`${debugPrefix} Retrying in 50ms...`);
                setTimeout(() => this._doIntegrateOptionsIntoProperties(modalElement, fieldType, retryCount + 1, resolve), 50);
            } else {
                console.error('[PluginItem] Properties content grid not found after max retries');
                if (resolve) resolve();
            }
            return;
        }
        console.log(`${debugPrefix} Properties content grid found`);

        // Remove any existing cloned options to prevent duplicates
        const existingClones = propertiesContent.querySelectorAll('.plugin-option-to-properties.plugin-cloned');
        console.log(`${debugPrefix} Removing existing clones`, { count: existingClones.length });
        existingClones.forEach(el => el.remove());

        // Hide the plugin-field-builder heading since fields are moved to Properties section
        const pluginBuilderContainer = pluginContainer.querySelector('.plugin-field-builder');
        if (pluginBuilderContainer) {
            const heading = pluginBuilderContainer.querySelector('h4');
            if (heading) {
                heading.style.display = 'none';
                console.log(`${debugPrefix} Hidden plugin-field-builder heading`);
            }
            // Also check if container should be hidden (if all content is hidden)
            const visibleChildren = Array.from(pluginBuilderContainer.children).filter(child => {
                if (child === heading) return false;
                const style = window.getComputedStyle(child);
                return style.display !== 'none' && style.visibility !== 'hidden' && style.position !== 'absolute';
            });
            if (visibleChildren.length === 0) {
                pluginBuilderContainer.style.display = 'none';
                console.log(`${debugPrefix} Hidden entire plugin-field-builder container (no visible content)`);
            }
        }

        let clonedCount = 0;
        pluginOptions.forEach((option, index) => {
            const clonedOption = option.cloneNode(true);
            clonedOption.classList.add('plugin-cloned');
            const originalInput = option.querySelector('input, select, textarea');
            const clonedInput = clonedOption.querySelector('input, select, textarea');

            console.log(`${debugPrefix} Processing option ${index + 1}/${pluginOptions.length}`, {
                hasOriginalInput: !!originalInput,
                hasClonedInput: !!clonedInput,
                inputName: originalInput?.name || 'N/A',
                inputType: originalInput?.type || 'N/A'
            });

            if (originalInput && clonedInput && originalInput.name) {
                clonedInput.name = originalInput.name;
                if (clonedInput.id) clonedInput.id = clonedInput.id + '-cloned-' + Date.now();
                const clonedLabel = clonedOption.querySelector('label[for]');
                if (clonedLabel && clonedInput.id) clonedLabel.setAttribute('for', clonedInput.id);
                if (originalInput.type === 'checkbox') clonedInput.checked = originalInput.checked;
                else clonedInput.value = originalInput.value;

                propertiesContent.appendChild(clonedOption);
                clonedCount++;
                console.log(`${debugPrefix} Successfully cloned option ${index + 1}`, {
                    name: originalInput.name,
                    type: originalInput.type,
                    value: originalInput.type === 'checkbox' ? originalInput.checked : originalInput.value
                });
            } else {
                console.warn(`${debugPrefix} Skipping option ${index + 1} - missing input or name`, {
                    hasOriginalInput: !!originalInput,
                    hasClonedInput: !!clonedInput,
                    hasName: !!originalInput?.name
                });
            }

            // Hide original option
            option.style.visibility = 'hidden';
            option.style.position = 'absolute';
            option.style.left = '-9999px';
        });

        console.log(`${debugPrefix} Integration complete`, {
            totalOptions: pluginOptions.length,
            clonedCount: clonedCount,
            propertiesContentChildren: propertiesContent.children.length
        });

        this.setupOptionSync(modalElement);
        setTimeout(() => window.ItemModal && window.ItemModal.checkModalScroll && window.ItemModal.checkModalScroll(), 100);

        // Resolve promise when integration is complete
        if (resolve) {
            console.log(`${debugPrefix} Resolving promise`);
            resolve();
        }
    },

    setupOptionSync(modalElement) {
        const pluginContainer = document.getElementById('plugin-configuration-container');
        const propertiesSection = modalElement.querySelector('.mb-3.border-t.border-gray-200.pt-4');
        if (!pluginContainer || !propertiesSection) return;
        const propertiesContent = propertiesSection.querySelector('.grid.grid-cols-2.gap-6.items-center');
        if (!propertiesContent) return;
        const originalOptions = pluginContainer.querySelectorAll('.plugin-option-to-properties input, .plugin-option-to-properties select, .plugin-option-to-properties textarea');
        const clonedOptions = propertiesContent.querySelectorAll('.plugin-option-to-properties input, .plugin-option-to-properties select, .plugin-option-to-properties textarea');
        originalOptions.forEach((originalField, index) => {
            const clonedField = clonedOptions[index];
            if (!clonedField || originalField.name !== clonedField.name) return;
            originalField.addEventListener('change', () => {
                if (clonedField.type === 'checkbox') clonedField.checked = originalField.checked;
                else clonedField.value = originalField.value;
            });
            clonedField.addEventListener('change', () => {
                if (originalField.type === 'checkbox') originalField.checked = clonedField.checked;
                else originalField.value = clonedField.value;
            });
        });
    },

    setupEventListeners(modalElement, fieldType) {
        if (modalElement._pluginChangeHandler) document.removeEventListener('change', modalElement._pluginChangeHandler);
        modalElement._pluginChangeHandler = (e) => {
            // Extend as needed per plugin field specifics
        };
        document.addEventListener('change', modalElement._pluginChangeHandler);
    },

    collectConfigFields(modalElement, formElement) {
        console.log('[PluginItem] collectConfigFields called');
        const pluginConfigContainer = document.getElementById('plugin-configuration-container');
        if (!pluginConfigContainer) {
            console.warn('[PluginItem] collectConfigFields: Container not found');
            return;
        }
        const existingField = formElement.querySelector('input[name="plugin_config"]');
        if (existingField) existingField.remove();
        const pluginConfig = {};
        const configFields = pluginConfigContainer.querySelectorAll('input, select, textarea');

        console.log('[PluginItem] collectConfigFields: Found fields in container', {
            fieldCount: configFields.length,
            fieldNames: Array.from(configFields).map(f => ({ name: f.name, type: f.type, value: f.value, checked: f.checked }))
        });

        const arrayFieldGroups = {};
        const groupedFields = new Map();

        configFields.forEach(field => {
            if (!field.name || !field.name.trim()) return;

            // Skip form fields that shouldn't be in plugin config
            if (field.name === 'field_type' || field.name === 'plugin_name') {
                return;
            }

            const arrayFieldMatch = field.name.match(/^(.+)_([A-Za-z0-9_]+)$/);
            if (arrayFieldMatch && field.type === 'checkbox') {
                const [, prefix, value] = arrayFieldMatch;
                if (!arrayFieldGroups[prefix]) {
                    arrayFieldGroups[prefix] = [];
                }
                if (field.checked) {
                    arrayFieldGroups[prefix].push(value);
                }
                return;
            }

            if (!groupedFields.has(field.name)) {
                groupedFields.set(field.name, []);
            }
            groupedFields.get(field.name).push(field);
        });

        groupedFields.forEach((fields, name) => {
            const sample = fields[0];
            if (sample.type === 'checkbox') {
                if (fields.length === 1) {
                    pluginConfig[name] = fields[0].checked;
                    console.log('[PluginItem] collectConfigFields: Single checkbox', { name, value: fields[0].checked });
                } else {
                    // Multiple checkboxes with same name - collect as array
                    const checkedValues = fields
                        .filter(f => f.checked)
                        .map(f => f.value || true);
                    pluginConfig[name] = checkedValues;
                    console.log('[PluginItem] collectConfigFields: Multiple checkboxes', {
                        name,
                        checkedValues,
                        totalFields: fields.length,
                        checkedFields: fields.filter(f => f.checked).map(f => ({ value: f.value, checked: f.checked }))
                    });
                }
            } else if (sample.type === 'radio') {
                const checked = fields.find(f => f.checked);
                if (checked) {
                    pluginConfig[name] = checked.value || true;
                    console.log('[PluginItem] collectConfigFields: Radio button', { name, value: checked.value });
                }
            } else if (sample.tagName === 'SELECT' && sample.multiple) {
                pluginConfig[name] = Array.from(sample.selectedOptions).map(opt => opt.value);
                console.log('[PluginItem] collectConfigFields: Multi-select', { name, values: pluginConfig[name] });
            } else {
                const value = sample.value;
                pluginConfig[name] = (value === '') ? null : value;
                console.log('[PluginItem] collectConfigFields: Text/other field', { name, value });
            }
        });

        Object.keys(arrayFieldGroups).forEach(prefix => {
            const values = arrayFieldGroups[prefix];
            if (values.length > 0) {
                pluginConfig[prefix] = values;
            }
        });

        // Also collect any plugin options that were moved to the Properties section
        // This ensures we get values from cloned fields if user edited them there
        const propertiesSection = modalElement.querySelector('.mb-3.border-t.border-gray-200.pt-4');
        if (propertiesSection) {
            const propertiesContent = propertiesSection.querySelector('.grid.grid-cols-2.gap-6.items-center');
            if (propertiesContent) {
                const propertiesPluginOptions = propertiesContent.querySelectorAll('.plugin-option-to-properties input, .plugin-option-to-properties select, .plugin-option-to-properties textarea');
                console.log('[PluginItem] collectConfigFields: Collecting from Properties section', {
                    clonedFieldCount: propertiesPluginOptions.length
                });

                // Group cloned fields by name (similar to original fields)
                const clonedGroupedFields = new Map();
                propertiesPluginOptions.forEach(field => {
                    if (!field.name || !field.name.trim()) return;

                    // Skip form fields that shouldn't be in plugin config
                    if (field.name === 'field_type' || field.name === 'plugin_name') {
                        return;
                    }

                    if (!clonedGroupedFields.has(field.name)) {
                        clonedGroupedFields.set(field.name, []);
                    }
                    clonedGroupedFields.get(field.name).push(field);
                });

                // Merge cloned field values, giving priority to cloned fields (user may have edited them)
                clonedGroupedFields.forEach((fields, name) => {
                    const sample = fields[0];
                    if (sample.type === 'checkbox') {
                        if (fields.length === 1) {
                            // Single checkbox - use cloned value
                            pluginConfig[name] = fields[0].checked;
                            console.log('[PluginItem] collectConfigFields: Override from cloned single checkbox', { name, value: fields[0].checked });
                        } else {
                            // Multiple checkboxes with same name (like operation_types) - collect as array
                            const checkedValues = fields
                                .filter(f => f.checked)
                                .map(f => f.value || true);
                            pluginConfig[name] = checkedValues;
                            console.log('[PluginItem] collectConfigFields: Override from cloned multiple checkboxes', {
                                name,
                                checkedValues,
                                totalFields: fields.length
                            });
                        }
                    } else if (sample.type === 'radio') {
                        const checked = fields.find(f => f.checked);
                        if (checked) {
                            pluginConfig[name] = checked.value || true;
                            console.log('[PluginItem] collectConfigFields: Override from cloned radio', { name, value: checked.value });
                        }
                    } else if (sample.tagName === 'SELECT' && sample.multiple) {
                        pluginConfig[name] = Array.from(sample.selectedOptions).map(opt => opt.value);
                        console.log('[PluginItem] collectConfigFields: Override from cloned multi-select', { name, values: pluginConfig[name] });
                    } else {
                        const value = sample.value;
                        pluginConfig[name] = (value === '') ? null : value;
                        console.log('[PluginItem] collectConfigFields: Override from cloned text/other', { name, value });
                    }
                });
            }
        }

        // Create hidden input with plugin configuration
        console.log('[PluginItem] collectConfigFields: Final plugin config', {
            config: pluginConfig,
            configString: JSON.stringify(pluginConfig)
        });

        const pluginConfigInput = document.createElement('input');
        pluginConfigInput.type = 'hidden';
        pluginConfigInput.name = 'plugin_config';
        pluginConfigInput.value = JSON.stringify(pluginConfig);
        formElement.appendChild(pluginConfigInput);

        console.log('[PluginItem] collectConfigFields: Config saved to hidden input', {
            inputValue: pluginConfigInput.value
        });
    }
};
