// Indicator item logic extracted from item-modal.js

import { DataManager } from '../data-manager.js';
import { SelectHelper } from './shared.js';

export const IndicatorItem = {
    setup(modalElement) {
        this.populateDropdowns(modalElement);
        this.setupEventListeners(modalElement);
    },

    teardown(modalElement) {
        if (!modalElement) return;
        if (modalElement._indicatorChangeHandler) {
            document.removeEventListener('change', modalElement._indicatorChangeHandler);
            modalElement._indicatorChangeHandler = null;
        }
    },

    setupEventListeners(modalElement) {
        if (modalElement._indicatorChangeHandler) {
            document.removeEventListener('change', modalElement._indicatorChangeHandler);
        }
        modalElement._indicatorChangeHandler = (e) => {
            const id = e.target.id;
            if (id === 'item-indicator-bank-select' || id === 'edit_indicator_modal_bank_id_select') {
                const selectedIndicatorId = e.target.value;
                if (selectedIndicatorId) {
                    const indicator = DataManager.getIndicatorById(parseInt(selectedIndicatorId));
                    if (indicator) {
                        // Update UI hint text (placeholders) for custom overrides when switching indicators.
                        // Do NOT overwrite any user-entered custom values.
                        this.updateCustomLabelAndDefinitionHints(modalElement, indicator);
                        if (id === 'item-indicator-bank-select') {
                            this.updateFilterDropdownsFromIndicator(modalElement, indicator);
                        }
                        // Preserve disaggregation selections when re-rendering options.
                        // In the form builder item modal, the user may tick multiple options and then
                        // other UI updates (select2/filter sync) can trigger re-render; we must not wipe checks.
                        const preserveSelections = true;
                        this.updateDisaggregationOptions(modalElement, indicator, preserveSelections);
                        this.updateAgeGroupsVisibility(modalElement, indicator);
                        this.updateIndirectReachVisibility(modalElement, indicator);
                    }
                } else {
                    // Reset hint text when no indicator is selected.
                    this.updateCustomLabelAndDefinitionHints(modalElement, null);
                    if (id === 'item-indicator-bank-select') {
                        this.resetFilterDropdowns(modalElement);
                    }
                }
            } else if (id === 'item-indicator-type-select' || id === 'item-indicator-unit-select') {
                if (!this._updatingFilters) {
                    this.updateBankOptions(modalElement);
                }
            }
        };
        document.addEventListener('change', modalElement._indicatorChangeHandler);
    },

    /**
     * Keep the "custom label" and "definition" override fields' hint text in sync with the selected indicator.
     * This controls placeholder text only (values are never overwritten).
     */
    updateCustomLabelAndDefinitionHints(modalElement, indicator) {
        const labelInput = modalElement?.querySelector?.('#item-indicator-label') || document.getElementById('item-indicator-label');
        const definitionInput = modalElement?.querySelector?.('#item-indicator-definition') || document.getElementById('item-indicator-definition');

        const toSafeString = (v) => (v === null || v === undefined) ? '' : (typeof v === 'string' ? v : String(v));

        // Prefer explicit `name` / `definition` fields (provided by backend JSON embedding).
        // Fall back to parsing `label` (which includes Type/Unit) when needed.
        const rawOptionLabel = toSafeString(indicator?.label || '');
        const parsedNameFromLabel = (() => {
            // Example: "Some Indicator (Type: number, Unit: People)" -> "Some Indicator"
            const idx = rawOptionLabel.indexOf(' (Type:');
            return idx > 0 ? rawOptionLabel.slice(0, idx) : rawOptionLabel;
        })();

        const bankName = toSafeString(indicator?.name || indicator?.bank_label || parsedNameFromLabel).trim();
        const bankDefinition = toSafeString(indicator?.definition || indicator?.bank_definition || indicator?.description || '').trim();

        if (labelInput) {
            labelInput.placeholder = bankName || '';
        }
        if (definitionInput) {
            definitionInput.placeholder = bankDefinition || '';
        }
    },

    populateDropdowns(modalElement) {
        const bankSelect = document.getElementById('item-indicator-bank-select');
        if (!bankSelect) return;
        const indicators = DataManager.getData('indicatorBankChoices') || [];
        const placeholder = bankSelect.querySelector('option[value=""]') || document.createElement('option');
        if (!placeholder.value) {
            placeholder.value = '';
            placeholder.textContent = 'Select Indicator...';
        }
        bankSelect.replaceChildren();
        bankSelect.appendChild(placeholder);
        indicators.forEach(indicator => {
            let id, label;
            if (Array.isArray(indicator)) {
                [id, label] = indicator;
            } else if (typeof indicator === 'object') {
                id = indicator.id ?? indicator.value;
                label = indicator.label || indicator.text || indicator.name;
            }
            if (id === undefined) return;
            if (!label) label = `Indicator ${id}`;
            const optionEl = document.createElement('option');
            optionEl.value = id;
            optionEl.textContent = label;
            bankSelect.appendChild(optionEl);
        });
        if (window.jQuery && window.jQuery.fn.select2) {
            if ($(bankSelect).hasClass('select2-hidden-accessible')) {
                $(bankSelect).trigger('change.select2');
            } else {
                $(bankSelect).select2({ dropdownParent: $('#item-modal'), width: '100%', theme: 'default' });
            }
        }
        const typeSelect = document.getElementById('item-indicator-type-select');
        const unitSelect = document.getElementById('item-indicator-unit-select');
        if (typeSelect || unitSelect) {
            const uniqueTypes = new Set();
            const uniqueUnits = new Set();
            indicators.forEach(ind => {
                let type = ind.type || (Array.isArray(ind) ? ind[2] : null);
                let unit = ind.unit || (Array.isArray(ind) ? ind[3] : null);
                if (type) uniqueTypes.add(type);
                if (unit) uniqueUnits.add(unit);
            });
            if (typeSelect) {
                const current = typeSelect.value;
                typeSelect.replaceChildren();
                {
                    const opt0 = document.createElement('option');
                    opt0.value = '';
                    opt0.textContent = 'All Types';
                    typeSelect.appendChild(opt0);
                }
                Array.from(uniqueTypes).sort().forEach(t => {
                    const opt = document.createElement('option');
                    opt.value = t;
                    opt.textContent = t;
                    typeSelect.appendChild(opt);
                });
                typeSelect.value = current;
            }
            if (unitSelect) {
                const currentU = unitSelect.value;
                unitSelect.replaceChildren();
                {
                    const opt0 = document.createElement('option');
                    opt0.value = '';
                    opt0.textContent = 'All Units';
                    unitSelect.appendChild(opt0);
                }
                Array.from(uniqueUnits).sort().forEach(u => {
                    const opt = document.createElement('option');
                    opt.value = u;
                    opt.textContent = u;
                    unitSelect.appendChild(opt);
                });
                unitSelect.value = currentU;
            }
        }
        this.updateBankOptions(modalElement);
        // Ensure hint text matches the currently selected indicator (if any).
        try {
            const selectedId = bankSelect.value ? parseInt(bankSelect.value) : null;
            const indicator = selectedId ? DataManager.getIndicatorById(selectedId) : null;
            this.updateCustomLabelAndDefinitionHints(modalElement, indicator || null);
        } catch (_) {
            // no-op
        }
        const filterTypeSelect = document.getElementById('item-indicator-type-select');
        const filterUnitSelect = document.getElementById('item-indicator-unit-select');
        if (filterTypeSelect && filterUnitSelect && (filterTypeSelect.value || filterUnitSelect.value)) {
            const indicatorsAll = DataManager.getData('indicatorBankChoices') || [];
            const sampleIndicator = indicatorsAll.find(ind => {
                const type = Array.isArray(ind) ? ind[2] : ind.type;
                const unit = Array.isArray(ind) ? ind[3] : ind.unit;
                const typeMatch = !filterTypeSelect.value || type === filterTypeSelect.value;
                const unitMatch = !filterUnitSelect.value || unit === filterUnitSelect.value;
                return typeMatch && unitMatch;
            });
            if (sampleIndicator) {
                const indicatorData = {
                    type: Array.isArray(sampleIndicator) ? sampleIndicator[2] : sampleIndicator.type,
                    unit: Array.isArray(sampleIndicator) ? sampleIndicator[3] : sampleIndicator.unit
                };
                this.updateDisaggregationOptions(modalElement, indicatorData, false);
                this.updateAgeGroupsVisibility(modalElement, indicatorData);
                this.updateIndirectReachVisibility(modalElement, indicatorData);
            }
        }
    },

    updateBankOptions(modalElement) {
        const typeSelect = document.getElementById('item-indicator-type-select');
        const unitSelect = document.getElementById('item-indicator-unit-select');
        const bankSelect = document.getElementById('item-indicator-bank-select');
        if (!bankSelect) return;
        const selectedType = typeSelect ? typeSelect.value : '';
        const selectedUnit = unitSelect ? unitSelect.value : '';
        const indicators = DataManager.getData('indicatorBankChoices') || [];
        const filtered = indicators.filter(ind => {
            const type = Array.isArray(ind) ? ind[2] : ind.type;
            const unit = Array.isArray(ind) ? ind[3] : ind.unit;
            if (selectedType && type !== selectedType) return false;
            if (selectedUnit && unit !== selectedUnit) return false;
            return true;
        });
        const currentVal = bankSelect.value;
        const placeholder = bankSelect.querySelector('option[value=""]') || document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = 'Select Indicator...';
        bankSelect.replaceChildren();
        bankSelect.appendChild(placeholder);
        filtered.forEach(ind => {
            let id, label;
            if (Array.isArray(ind)) {
                [id, label] = ind;
            } else {
                id = ind.id ?? ind.value;
                label = ind.label || ind.text || ind.name;
            }
            const opt = document.createElement('option');
            opt.value = id;
            opt.textContent = label;
            bankSelect.appendChild(opt);
        });
        bankSelect.value = filtered.some(f => (Array.isArray(f) ? f[0] : (f.id ?? f.value)) == currentVal) ? currentVal : '';
        if (window.jQuery && window.jQuery.fn.select2 && $(bankSelect).hasClass('select2-hidden-accessible')) {
            $(bankSelect).trigger('change.select2');
        }
        // Keep hint text in sync when selection changes programmatically (e.g. due to filtering).
        try {
            const selectedId = bankSelect.value ? parseInt(bankSelect.value) : null;
            const indicator = selectedId ? DataManager.getIndicatorById(selectedId) : null;
            this.updateCustomLabelAndDefinitionHints(modalElement, indicator || null);
        } catch (_) {
            // no-op
        }
        const availableTypesSet = new Set();
        const availableUnitsSet = new Set();
        indicators.forEach(ind => {
            const type = Array.isArray(ind) ? ind[2] : ind.type;
            const unit = Array.isArray(ind) ? ind[3] : ind.unit;
            if (!selectedUnit || unit === selectedUnit) {
                if (type) availableTypesSet.add(type);
            }
            if (!selectedType || type === selectedType) {
                if (unit) availableUnitsSet.add(unit);
            }
        });
        if (typeSelect) {
            const prevTypeVal = typeSelect.value;
            typeSelect.replaceChildren();
            {
                const opt0 = document.createElement('option');
                opt0.value = '';
                opt0.textContent = 'All Types';
                typeSelect.appendChild(opt0);
            }
            Array.from(availableTypesSet).sort().forEach(t => {
                const opt = document.createElement('option');
                opt.value = t;
                opt.textContent = t;
                typeSelect.appendChild(opt);
            });
            typeSelect.value = availableTypesSet.has(prevTypeVal) ? prevTypeVal : '';
        }
        if (unitSelect) {
            const prevUnitVal = unitSelect.value;
            unitSelect.replaceChildren();
            {
                const opt0 = document.createElement('option');
                opt0.value = '';
                opt0.textContent = 'All Units';
                unitSelect.appendChild(opt0);
            }
            Array.from(availableUnitsSet).sort().forEach(u => {
                const opt = document.createElement('option');
                opt.value = u;
                opt.textContent = u;
                unitSelect.appendChild(opt);
            });
            unitSelect.value = availableUnitsSet.has(prevUnitVal) ? prevUnitVal : '';
        }
        if (selectedType || selectedUnit) {
            const indicatorsAll = DataManager.getData('indicatorBankChoices') || [];
            const sampleIndicator = indicatorsAll.find(ind => {
                const type = Array.isArray(ind) ? ind[2] : ind.type;
                const unit = Array.isArray(ind) ? ind[3] : ind.unit;
                const typeMatch = !selectedType || type === selectedType;
                const unitMatch = !selectedUnit || unit === selectedUnit;
                return typeMatch && unitMatch;
            });
            if (sampleIndicator) {
                const indicatorData = {
                    type: Array.isArray(sampleIndicator) ? sampleIndicator[2] : sampleIndicator.type,
                    unit: Array.isArray(sampleIndicator) ? sampleIndicator[3] : sampleIndicator.unit
                };
                this.updateDisaggregationOptions(modalElement, indicatorData, false);
                this.updateAgeGroupsVisibility(modalElement, indicatorData);
                this.updateIndirectReachVisibility(modalElement, indicatorData);
            }
        }
    },

    populateDisaggregationCheckboxes(container, disaggregationChoices, preserveSelections = false) {
        if (!container || !disaggregationChoices) return;
        let currentSelections = [];
        if (preserveSelections) {
            const existingCheckboxes = container.querySelectorAll('input[type="checkbox"]:checked');
            currentSelections = Array.from(existingCheckboxes).map(cb => cb.value);
        }
        container.replaceChildren();
        disaggregationChoices.forEach(choice => {
            const [value, label] = choice;
            const checkboxDiv = document.createElement('div');
            checkboxDiv.className = 'flex items-center';
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.id = `disagg-${value}`;
            checkbox.value = value;
            // Do not submit checkbox inputs directly.
            // We submit a canonical hidden representation instead (see syncToHidden) to keep POSTs deterministic
            // even if the checkbox UI is re-rendered or temporarily disabled.
            checkbox.name = '';
            checkbox.className = 'form-checkbox h-4 w-4 text-purple-600 border-gray-300 rounded focus:ring-purple-500';
            if (preserveSelections && currentSelections.includes(value)) {
                checkbox.checked = true;
            }
            const labelElement = document.createElement('label');
            labelElement.htmlFor = checkbox.id;
            labelElement.className = 'ml-2 text-sm text-gray-700';
            labelElement.textContent = label;
            checkboxDiv.appendChild(checkbox);
            checkboxDiv.appendChild(labelElement);
            container.appendChild(checkboxDiv);
        });

        // Keep a canonical hidden representation in the item modal form so submits are deterministic.
        // This guards against edge cases where checkboxes get re-rendered/disabled and the browser
        // omits them from FormData.
        const syncToHidden = () => {
            try {
                const form = document.getElementById('item-modal-form');
                if (!form) return;
                // Remove prior hidden representations (this name is reserved for our generated inputs in the item modal).
                Array.from(form.querySelectorAll('input[type="hidden"][name="allowed_disaggregation_options"]'))
                    .forEach((n) => n.remove());
                const checked = Array.from(container.querySelectorAll('input[type="checkbox"]:checked'))
                    .map(cb => cb.value)
                    .filter(Boolean);
                checked.forEach((v) => {
                    const input = document.createElement('input');
                    input.type = 'hidden';
                    input.name = 'allowed_disaggregation_options';
                    input.value = v;
                    input.dataset.fbGenerated = 'disagg';
                    form.appendChild(input);
                });
            } catch (_e) {}
        };

        try {
            if (!container.dataset.fbDisaggSerializeWired) {
                container.dataset.fbDisaggSerializeWired = '1';
                container.addEventListener('change', () => syncToHidden());
            }
        } catch (_e) {}
        // Initial sync (covers edit-mode prepopulation)
        syncToHidden();
    },

    updateDisaggregationOptions(modalElement, indicator, preserveSelections = false) {
        const container = document.getElementById('add_item_indicator_disaggregation_options_wrapper');
        if (!container) return;
        let supportsDisagg = false;
        if (indicator) {
            if (typeof indicator === 'object') {
                const unit = indicator.unit;
                const type = indicator.type;
                const allowedUnits = ['People', 'Volunteers', 'Staff'];
                supportsDisagg = type && type.toLowerCase() === 'number' && unit && allowedUnits.some(allowedUnit => allowedUnit.toLowerCase() === unit.toLowerCase());
            } else if (Array.isArray(indicator)) {
                supportsDisagg = indicator[4] !== undefined ? !!indicator[4] : true;
            }
        }
        if (supportsDisagg) {
            Utils.showElement(container);
            const checkboxContainer = container.querySelector('#add_item_indicator_allowed_disaggregation_options_container');
            if (checkboxContainer) {
                const disaggregationChoices = DataManager.getData('disaggregationChoices');
                this.populateDisaggregationCheckboxes(checkboxContainer, disaggregationChoices, preserveSelections);
            }
        } else {
            Utils.hideElement(container);
        }
    },

    updateAgeGroupsVisibility(modalElement, indicator) {
        const ageGroupsContainer = document.getElementById('add_item_indicator_age_groups_config_wrapper');
        if (!ageGroupsContainer) return;
        const shouldShow = indicator.unit?.toLowerCase() === 'people' && indicator.type && indicator.type.toLowerCase() === 'number';
        if (shouldShow) {
            Utils.showElement(ageGroupsContainer);
        } else {
            Utils.hideElement(ageGroupsContainer);
        }
    },

    updateIndirectReachVisibility(modalElement, indicator) {
        const indirectReachRow = document.getElementById('indirect-reach-row');
        if (!indirectReachRow) return;
        const checkbox = indirectReachRow.querySelector('#item-indirect-reach');
        const shouldShow = indicator.type?.toLowerCase() === 'number' && ['volunteers', 'staff', 'people'].includes(indicator.unit?.toLowerCase());
        if (shouldShow) {
            Utils.showElement(indirectReachRow);
            if (checkbox) checkbox.disabled = false;
        } else {
            Utils.hideElement(indirectReachRow);
            // IMPORTANT: Hidden checkboxes still submit if checked.
            // If indirect reach isn't supported for this indicator, force-clear it so users don't get stuck
            // with an enabled value they can't see/untick.
            if (checkbox) {
                checkbox.checked = false;
                checkbox.disabled = true;
            }
        }
    },

    updateFilterDropdownsFromIndicator(modalElement, indicator) {
        this._updatingFilters = true;
        try {
            const typeSelect = document.getElementById('item-indicator-type-select');
            const unitSelect = document.getElementById('item-indicator-unit-select');
            if (!typeSelect || !unitSelect) {
                this.populateDropdowns(modalElement);
                const newTypeSelect = document.getElementById('item-indicator-type-select');
                const newUnitSelect = document.getElementById('item-indicator-unit-select');
                if (!newTypeSelect || !newUnitSelect) {
                    return;
                }
            }
            const finalTypeSelect = typeSelect || document.getElementById('item-indicator-type-select');
            const finalUnitSelect = unitSelect || document.getElementById('item-indicator-unit-select');
            if (finalTypeSelect && indicator.type) {
                const typeOption = finalTypeSelect.querySelector(`option[value="${indicator.type}"]`);
                if (typeOption) {
                    finalTypeSelect.value = indicator.type;
                }
            }
            if (finalUnitSelect && indicator.unit) {
                const unitOption = finalUnitSelect.querySelector(`option[value="${indicator.unit}"]`);
                if (unitOption) {
                    finalUnitSelect.value = indicator.unit;
                }
            }
            this.updateBankOptions(modalElement);
        } finally {
            this._updatingFilters = false;
        }
    },

    resetFilterDropdowns(modalElement) {
        const typeSelect = document.getElementById('item-indicator-type-select');
        const unitSelect = document.getElementById('item-indicator-unit-select');
        if (typeSelect) typeSelect.value = '';
        if (unitSelect) unitSelect.value = '';
        this.updateBankOptions(modalElement);
    },

    populateForm(modalElement, itemData) {
        this.populateDropdowns(modalElement);
        setTimeout(() => {
            const bankSelect = modalElement.querySelector('#item-indicator-bank-select');
            const ageGroupsInput = modalElement.querySelector('#add_item_modal_indicator_age_groups_input');
            const defaultValueInput = modalElement.querySelector('#item-indicator-default-value') || document.getElementById('item-indicator-default-value');
            if (bankSelect && itemData.indicator_bank_id) {
                let existingOption = bankSelect.querySelector(`option[value="${itemData.indicator_bank_id}"]`);
                if (!existingOption) {
                    const indicatorObj = DataManager.getIndicatorById(parseInt(itemData.indicator_bank_id)) || {};
                    existingOption = document.createElement('option');
                    existingOption.value = itemData.indicator_bank_id;
                    existingOption.textContent = indicatorObj.label || `Indicator #${itemData.indicator_bank_id}`;
                    bankSelect.appendChild(existingOption);
                }
                bankSelect.value = itemData.indicator_bank_id;
                if (window.jQuery && window.jQuery.fn.select2 && $(bankSelect).hasClass('select2-hidden-accessible')) {
                    $(bankSelect).val(itemData.indicator_bank_id).trigger('change.select2');
                }
                const selectedIndicator = DataManager.getIndicatorById(parseInt(itemData.indicator_bank_id));
                if (selectedIndicator) {
                    const typeSelectFilter = document.getElementById('item-indicator-type-select');
                    const unitSelectFilter = document.getElementById('item-indicator-unit-select');
                    if (typeSelectFilter && selectedIndicator.type) {
                        typeSelectFilter.value = selectedIndicator.type;
                    }
                    if (unitSelectFilter && selectedIndicator.unit) {
                        unitSelectFilter.value = selectedIndicator.unit;
                    }
                    this.updateBankOptions(modalElement);
                    const disaggContainer = modalElement.querySelector('#add_item_indicator_allowed_disaggregation_options_container');
                    if (!disaggContainer || disaggContainer.children.length === 0) {
                        this.updateDisaggregationOptions(modalElement, selectedIndicator, true);
                    }
                    this.updateAgeGroupsVisibility(modalElement, selectedIndicator);
                    this.updateIndirectReachVisibility(modalElement, selectedIndicator);
                }
            }
            // Populate custom label/definition overrides and translations if present
            try {
                const sharedLabelHidden = document.getElementById('item-modal-shared-label');
                const uiLabel = document.getElementById('item-indicator-label');
                const uiDefinition = document.getElementById('item-indicator-definition');
                if (itemData && typeof itemData === 'object') {
                    const toSafeString = (value) => {
                        if (value === null || value === undefined) {
                            return '';
                        }
                        return typeof value === 'string' ? value : String(value);
                    };
                    const labelRaw = toSafeString(itemData.label || itemData.display_label || '');
                    const bankLabelRaw = toSafeString(itemData.bank_label || itemData.indicator_bank_label || '');
                    const definitionRaw = toSafeString(itemData.definition || itemData.description || '');
                    const bankDefinitionRaw = toSafeString(itemData.bank_definition || itemData.indicator_bank_definition || '');
                    const hasLabelTranslations = itemData.label_translations && Object.keys(itemData.label_translations).length > 0;
                    const hasDefinitionTranslations = itemData.definition_translations && Object.keys(itemData.definition_translations).length > 0;
                    const labelTrimmed = labelRaw.trim();
                    const bankLabelTrimmed = bankLabelRaw.trim();
                    const definitionTrimmed = definitionRaw.trim();
                    const bankDefinitionTrimmed = bankDefinitionRaw.trim();
                    const hasCustomLabel = (labelTrimmed.length > 0 && (!bankLabelTrimmed || labelTrimmed !== bankLabelTrimmed)) || hasLabelTranslations;
                    const hasCustomDefinition = (definitionTrimmed.length > 0 && (!bankDefinitionTrimmed || definitionTrimmed !== bankDefinitionTrimmed)) || hasDefinitionTranslations;

                    if (sharedLabelHidden) {
                        sharedLabelHidden.value = hasCustomLabel ? labelRaw : '';
                    }
                    if (uiLabel) {
                        uiLabel.value = hasCustomLabel ? labelRaw : '';
                        uiLabel.placeholder = bankLabelRaw || '';
                    }
                    if (uiDefinition) {
                        uiDefinition.value = hasCustomDefinition ? definitionRaw : '';
                        uiDefinition.placeholder = bankDefinitionRaw || '';
                    }
                    const labelTrHidden = document.getElementById('item-modal-shared-label-translations');
                    if (labelTrHidden && itemData.label_translations) {
                        try { labelTrHidden.value = JSON.stringify(itemData.label_translations); } catch(_) {}
                    }
                    const defTrHidden = document.getElementById('item-modal-definition-translations');
                    if (defTrHidden && itemData.definition_translations) {
                        try { defTrHidden.value = JSON.stringify(itemData.definition_translations); } catch(_) {}
                    }
                }
            } catch (e) { /* no-op */ }
            if (ageGroupsInput && itemData.age_groups_config) {
                ageGroupsInput.value = itemData.age_groups_config;
            }
            if (defaultValueInput) {
                const dv = (itemData && typeof itemData === 'object')
                    ? (itemData.default_value ?? itemData?.config?.default_value ?? '')
                    : '';
                defaultValueInput.value = (dv === null || dv === undefined) ? '' : String(dv);
            }
            if (itemData.allowed_disaggregation_options && itemData.allowed_disaggregation_options.length > 0) {
                setTimeout(() => {
                    const disaggContainer = modalElement.querySelector('#add_item_indicator_allowed_disaggregation_options_container');
                    if (disaggContainer) {
                        const checkboxes = disaggContainer.querySelectorAll('input[type="checkbox"]');
                        checkboxes.forEach(checkbox => {
                            if (itemData.allowed_disaggregation_options.includes(checkbox.value)) {
                                checkbox.checked = true;
                            } else {
                                checkbox.checked = false;
                            }
                        });
                    }
                }, 100);
            }
        }, 100);
    }
};
