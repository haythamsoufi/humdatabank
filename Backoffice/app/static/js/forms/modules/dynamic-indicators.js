/**
 * Dynamic Indicators Module
 *
 * Provides unified handling of dynamic indicator sections regardless of whether they are:
 * - Main sections or subsections
 * - Located in different parts of the form hierarchy
 * - Using different styling contexts
 *
 * All dynamic indicator sections are treated identically using the same:
 * - Setup logic
 * - Button handling
 * - Interface recreation
 * - State management
 *
 * This eliminates code duplication and ensures consistent behavior across all contexts.
 */

import { debugLog, debugWarn, debugError } from './debug.js';
import { initializeFieldListeners } from './form-item-utils.js';
import { applyLayoutToSection } from './layout.js';

let isInitialized = false;

function toString(value) {
    if (value === null || value === undefined) return '';
    return String(value);
}

// For safe interpolation into HTML text nodes (e.g. <div>TEXT</div>)
function escapeHtmlText(value) {
    return toString(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

// For safe interpolation into HTML attribute values (e.g. value="ATTR")
function escapeHtmlAttr(value) {
    return toString(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

export function initDynamicIndicators() {
    if (isInitialized) {
        return;
    }

    setupDynamicIndicatorManagement();
    setupDynamicIndicatorDeletion();

    isInitialized = true;

    // Add a delayed check to refresh button states after page load
    setTimeout(() => {
        refreshDynamicIndicatorButtonStates();
    }, 100);
}

function setupDynamicIndicatorManagement() {
    // Load global data once
    loadIndicatorData();

    // Set up all dynamic indicator sections uniformly
    setupAllDynamicSections();
}

function loadIndicatorData() {
    let availableIndicatorsData = {};
    let sectionDisplayFilters = {};

    try {
        const availableIndicatorsScript = document.getElementById('available-indicators-data');
        if (availableIndicatorsScript) {
            availableIndicatorsData = JSON.parse(availableIndicatorsScript.textContent);
        }

        const sectionFiltersScript = document.getElementById('section-display-filters-data');
        if (sectionFiltersScript) {
            sectionDisplayFilters = JSON.parse(sectionFiltersScript.textContent);
        }
    } catch (error) {
        debugError('dynamic-indicators', 'Error loading indicators data:', error);
    }

    // Make data globally available
    window.availableIndicatorsData = availableIndicatorsData;
    window.sectionDisplayFilters = sectionDisplayFilters;
}

function setupAllDynamicSections() {
    // Find ALL dynamic indicator sections (main and sub) and treat them identically
    const dynamicSections = document.querySelectorAll('[data-section-type="dynamic_indicators"]');

    debugLog('dynamic-indicators', `Found ${dynamicSections.length} dynamic indicator sections`);

    dynamicSections.forEach(sectionContainer => {
        setupSingleDynamicSection(sectionContainer);
    });
}

function setupSingleDynamicSection(sectionContainer) {
    const sectionId = sectionContainer.id.replace('section-container-', '');
    const addBtn = document.getElementById(`add-indicator-row-btn-${sectionId}`);

    debugLog('dynamic-indicators', `Setting up dynamic section ${sectionId}`);

    // Set up Add Indicator button
    if (addBtn) {
        addBtn.addEventListener('click', () => handleAddIndicator(sectionContainer, sectionId));
    }
}

function handleAddIndicator(sectionContainer, sectionId) {
    // Check maximum indicators limit (same logic for all sections)
    const maxIndicators = sectionContainer.getAttribute('data-max-dynamic-indicators');
    if (maxIndicators && exceedsMaximumLimit(sectionContainer, sectionId, maxIndicators)) {
        return; // Exit if limit exceeded
    }

    // Add indicator row
    const availableIndicators = window.availableIndicatorsData[sectionId] || [];
    addIndicatorRow(sectionId, availableIndicators);
}

function exceedsMaximumLimit(sectionContainer, sectionId, maxIndicators) {
    const currentIndicatorCount = sectionContainer.querySelectorAll('.form-item-block[data-item-type="indicator"]').length;
    const pendingRowsCount = document.getElementById(`dynamic-indicator-rows-${sectionId}`)?.querySelectorAll('[id^="indicator-row-"]').length || 0;

    if (currentIndicatorCount + pendingRowsCount >= parseInt(maxIndicators)) {
        const templates = window.DYNAMIC_INDICATORS_TEMPLATES || {};
        const message = templates.maximumAllowed ?
            templates.maximumAllowed.replace('%(max)s', maxIndicators) :
            `Maximum of ${maxIndicators} indicators allowed for this section.`;
        if (window.showAlert) window.showAlert(message, 'warning');
        else console.warn(message);
        return true;
    }
    return false;
}

function setupDynamicIndicatorDeletion() {
    document.addEventListener('click', (e) => {
        if (e.target.matches('.delete-dynamic-indicator-btn') ||
            e.target.closest('.delete-dynamic-indicator-btn')) {

            const button = e.target.matches('.delete-dynamic-indicator-btn') ?
                          e.target : e.target.closest('.delete-dynamic-indicator-btn');

            const assignmentId = button.getAttribute('data-assignment-id');
            const indicatorName = button.getAttribute('data-indicator-name');

            if (assignmentId) {
                // Check if this is a pending indicator (not yet saved to DB)
                const indicatorElement = button.closest('[data-pending-assignment-id]');
                const pendingId = indicatorElement?.getAttribute('data-pending-assignment-id');

                if (pendingId || assignmentId.startsWith('pending_')) {
                    // Pending indicator - just remove from DOM without API call
                    const displayName = indicatorName || `Indicator`;
                    const templates = window.DYNAMIC_INDICATORS_TEMPLATES || {};
                    const confirmMessage = templates.confirmRemovePending ?
                        templates.confirmRemovePending.replace('%(name)s', displayName) :
                        `Are you sure you want to remove the indicator "${displayName}"?`;

                    const removePending = () => {
                        const formItemBlock = button.closest('.form-item-block');
                        if (formItemBlock) {
                            // Find the section container before removing
                            const sectionContainer = formItemBlock.closest('[data-section-type="dynamic_indicators"]');

                            // Remove hidden input tracking this pending indicator
                            const form = document.querySelector('form#focalDataEntryForm');
                            if (form) {
                                const pendingInputs = form.querySelectorAll(`input[data-temp-assignment-id="${pendingId || assignmentId}"]`);
                                pendingInputs.forEach(input => input.remove());
                            }

                            formItemBlock.remove();

                            // Refresh just this section for faster update
                            if (sectionContainer) {
                                refreshSingleSectionButtonState(sectionContainer);
                            } else {
                                refreshDynamicIndicatorButtonStates();
                            }
                        }
                    };

                    if (window.showDangerConfirmation) {
                        window.showDangerConfirmation(
                            confirmMessage,
                            removePending,
                            null,
                            'Remove',
                            'Cancel',
                            'Remove Indicator?'
                        );
                    } else if (window.showConfirmation) {
                        window.showConfirmation(confirmMessage, removePending, null, 'Remove', 'Cancel', 'Remove Indicator?');
                    } else {
                        console.warn('Confirmation dialog not available:', confirmMessage);
                    }
                    return;
                }

                // Saved indicator - use API to delete
                const displayName = indicatorName || `Indicator ${assignmentId}`;
                const templates = window.DYNAMIC_INDICATORS_TEMPLATES || {};
                const confirmMessage = templates.confirmRemove ?
                    templates.confirmRemove.replace('%(name)s', displayName) :
                    `Are you sure you want to remove the indicator "${displayName}"? This action cannot be undone.`;
                if (window.showDangerConfirmation) {
                    window.showDangerConfirmation(
                        confirmMessage,
                        () => deleteDynamicIndicator(assignmentId, displayName),
                        null,
                        'Remove',
                        'Cancel',
                        'Remove Indicator?'
                    );
                } else if (window.showConfirmation) {
                    window.showConfirmation(
                        confirmMessage,
                        () => deleteDynamicIndicator(assignmentId, displayName),
                        null,
                        'Remove',
                        'Cancel',
                        'Remove Indicator?'
                    );
                } else {
                    console.warn('Confirmation dialog not available:', confirmMessage);
                }
            } else {
                debugError('dynamic-indicators', `Missing assignment ID: assignmentId=${assignmentId}, indicatorName=${indicatorName}`);
            }
        }
    });

    // Handle propose changes button clicks
    document.addEventListener('click', (e) => {
        if (e.target.matches('.propose-changes-btn') ||
            e.target.closest('.propose-changes-btn')) {

            const button = e.target.matches('.propose-changes-btn') ?
                          e.target : e.target.closest('.propose-changes-btn');

            const indicatorId = button.getAttribute('data-indicator-id');
            const indicatorName = button.getAttribute('data-indicator-name');

            if (indicatorId) {
                openIndicatorProposalFormForExisting(indicatorId, indicatorName);
            } else {
                debugError('dynamic-indicators', `Missing indicator ID: indicatorId=${indicatorId}, indicatorName=${indicatorName}`);
            }
        }
    });
}

function deleteDynamicIndicator(assignmentId, indicatorName) {
    // Get CSRF token
    const csrfToken = document.querySelector('input[name="csrf_token"]')?.value ||
                     document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');

    if (!csrfToken) {
        debugError('dynamic-indicators', 'CSRF token not found');
        const labels = window.DYNAMIC_INDICATORS_LABELS || {};
        const errorMessage = labels.securityTokenNotFound || 'Security token not found. Please refresh the page and try again.';
        if (window.showAlert) window.showAlert(errorMessage, 'error');
        else console.warn(errorMessage);
        return;
    }

    const _dfetch = (window.getFetch && window.getFetch()) || fetch;
    _dfetch(`/api/forms/dynamic-indicators/${assignmentId}/remove`, {
        method: 'DELETE',
        headers: {
            'X-CSRFToken': csrfToken,
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(data => {
                const labels = window.DYNAMIC_INDICATORS_LABELS || {};
                const errorMessage = labels.failedToDelete || 'Failed to delete indicator';
                throw new Error(data.error || errorMessage);
            });
        }
        return response.json();
    })
    .then(data => {
        if (data.success) {
            // Remove the indicator from the page
            const indicatorElement = document.querySelector(`[data-assignment-id="${assignmentId}"]`);

            if (indicatorElement) {
                // Find the parent form-item-block and get its section container
                const formItemBlock = indicatorElement.closest('.form-item-block');
                const sectionContainer = indicatorElement.closest('[data-section-type="dynamic_indicators"]');

                if (formItemBlock) {
                    formItemBlock.remove();
                } else {
                    indicatorElement.remove();
                }

                // Refresh button states and count immediately after removal
                if (sectionContainer) {
                    // Refresh just this section for faster update
                    refreshSingleSectionButtonState(sectionContainer);
                } else {
                    // Fallback: refresh all if section container not found
                    refreshDynamicIndicatorButtonStates();
                }
            } else {
                debugError('dynamic-indicators', `Could not find element with data-assignment-id="${assignmentId}"`);
                // Reload the page as fallback
                window.location.reload();
            }

        } else {
            const labels = window.DYNAMIC_INDICATORS_LABELS || {};
            const errorMessage = labels.failedToDelete || 'Failed to delete indicator';
            throw new Error(data.error || errorMessage);
        }
    })
    .catch(error => {
        debugError('dynamic-indicators', 'Failed to delete dynamic indicator:', error);
        const labels = window.DYNAMIC_INDICATORS_LABELS || {};
        const errorMessage = labels.failedToDelete || 'Failed to delete indicator';
        const msg = `${errorMessage}: ${error.message}`;
        if (window.showAlert) window.showAlert(msg, 'error');
        else console.warn(msg);
    });
}

function addIndicatorRow(sectionId, availableIndicators) {
    const rowsContainer = document.getElementById(`dynamic-indicator-rows-${sectionId}`);
    if (!rowsContainer) {
        debugError('dynamic-indicators', `Container not found: dynamic-indicator-rows-${sectionId}`);
        return;
    }

    const rowId = Date.now(); // Unique ID for this row
    const indicators = availableIndicators || [];
    const labels = window.DYNAMIC_INDICATORS_LABELS || {};
    const frontendConfig = window.FRONTEND_CONFIG || {};
    const proposeOverrideUrl = (frontendConfig.proposeNewIndicatorUrl || '').trim();
    const showProposeLink = !!proposeOverrideUrl;

    if (indicators.length === 0) {
        const errorMessage = labels.noMoreIndicators || 'No more indicators available for this section.';
        if (window.showAlert) window.showAlert(errorMessage, 'warning');
        else console.warn(errorMessage);
        return;
    }

    // Get display filters configuration
    let displayFilters = ['sector']; // Default to sector only
    if (window.sectionDisplayFilters && window.sectionDisplayFilters[sectionId]) {
        displayFilters = window.sectionDisplayFilters[sectionId];
    }

    debugLog('dynamic-indicators', `Creating filters for section ${sectionId}:`, displayFilters);

    // Generate filter dropdowns HTML based on configuration
    let filterDropdownsHtml = '';
    const filterData = {};
    const hasOnlyOneFilter = displayFilters.length === 1;

    displayFilters.forEach(filterKey => {
        const uniqueValues = [...new Set(indicators.map(ind => ind[filterKey]).filter(val => val))].sort();
        filterData[filterKey] = uniqueValues;

        const filterLabel = filterKey.charAt(0).toUpperCase() + filterKey.slice(1);
        const labels = window.DYNAMIC_INDICATORS_LABELS || {};
        filterDropdownsHtml += `
            <div class="${hasOnlyOneFilter ? 'w-48' : 'flex-1 min-w-[200px]'}">
                <label class="block text-xs font-medium text-gray-600 mb-1">${escapeHtmlText(filterLabel)}</label>
                <select class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-green-500 ${filterKey}-select"
                        data-row-id="${rowId}"
                        data-filter-key="${filterKey}">
                    <option value="">${escapeHtmlText(labels.all || 'All')} ${escapeHtmlText(filterLabel)}s</option>
                    ${uniqueValues.map(value => `<option value="${escapeHtmlAttr(value)}">${escapeHtmlText(value)}</option>`).join('')}
                </select>
            </div>
        `;
    });

    const indicatorDropdownHtml = `
        <div class="${hasOnlyOneFilter ? 'flex-1' : 'w-full'}">
            <label class="block text-xs font-medium text-gray-600 mb-1">${escapeHtmlText(labels.selectIndicator || 'Select Indicator')}</label>
            <div class="searchable-dropdown relative" data-row-id="${rowId}">
                <input type="text"
                       class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-green-500 indicator-search-input"
                       placeholder="${escapeHtmlAttr(labels.typeToSearch || 'Type to search indicators...')}"
                       data-row-id="${rowId}"
                       data-section-id="${sectionId}"
                       autocomplete="off">
                <div class="absolute z-50 w-full bg-white border border-gray-300 rounded-md shadow-lg mt-1 max-h-60 overflow-y-auto hidden indicator-dropdown-list"
                     data-row-id="${rowId}">
                    <div class="p-2 text-sm text-gray-500 border-b indicator-count">
                        ${indicators.length} ${escapeHtmlText(labels.indicatorsAvailable || 'indicators available')}
                    </div>
                    <div class="indicator-options-container"></div>
                </div>
            </div>
        </div>
    `;

    const rowHtml = `
        <div class="flex flex-col gap-3 p-4 bg-white border border-gray-200 rounded-lg" id="indicator-row-${rowId}">
            <div class="flex items-center justify-between">
                <h4 class="text-sm font-medium text-gray-700">${escapeHtmlText(labels.addNewIndicator || 'Add New Indicator')}</h4>
                <div class="flex items-center gap-3">
                    ${showProposeLink ? `
                        <a href="${escapeHtmlAttr(proposeOverrideUrl)}" target="_blank" rel="noopener noreferrer" class="text-blue-600 hover:text-blue-800 text-sm underline propose-indicator-row-link"
                           data-row-id="${rowId}"
                           data-section-id="${sectionId}"
                           title="${escapeHtmlAttr(labels.proposeIndicatorTooltip || 'Open indicator bank to propose new indicators or review existing ones')}">
                            ${escapeHtmlText(labels.proposeNewIndicatorLink || "Can't find an indicator? Propose a new one here")}
                        </a>
                    ` : ''}
                    <button type="button" class="text-red-600 hover:text-red-800 px-2 py-1 rounded remove-indicator-row"
                            data-row-id="${rowId}">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            </div>

            <div class="flex flex-col gap-3">
                ${hasOnlyOneFilter ? `
                    <!-- Single filter and indicator on same line -->
                    <div class="flex gap-3 items-end">
                        ${filterDropdownsHtml}
                        ${indicatorDropdownHtml}
                    </div>
                ` : `
                    <!-- Multiple filters on separate line -->
                    <div class="flex flex-wrap gap-3">
                        ${filterDropdownsHtml}
                    </div>
                    ${indicatorDropdownHtml}
                `}
            </div>
        </div>
    `;

    // Use DOMParser for CSP-safe HTML parsing
    const parser = new DOMParser();
    const doc = parser.parseFromString(rowHtml.trim(), 'text/html');
    const rowElement = doc.body.firstElementChild;
    if (rowElement) {
        rowsContainer.appendChild(rowElement);
    }

    // Set up indicator selection functionality
    setupIndicatorSelection(rowId, sectionId, indicators, filterData, displayFilters);

    // Add event listener for remove button
    const removeBtn = document.querySelector(`button[data-row-id="${rowId}"].remove-indicator-row`);
    if (removeBtn) {
        removeBtn.addEventListener('click', function() {
            document.getElementById(`indicator-row-${rowId}`).remove();
        });
    }
}

function setupIndicatorSelection(rowId, sectionId, indicators, filterData, displayFilters) {
    debugLog('dynamic-indicators', `Setting up indicator selection for row ${rowId}`);

    const searchInput = document.querySelector(`input[data-row-id="${rowId}"]`);
    const dropdownList = document.querySelector(`.indicator-dropdown-list[data-row-id="${rowId}"]`);
    const countDisplay = dropdownList?.querySelector('.indicator-count');
    const optionsContainer = dropdownList?.querySelector('.indicator-options-container');

    if (!searchInput || !dropdownList || !optionsContainer) {
        debugError('dynamic-indicators', 'Required elements not found for indicator selection');
        return;
    }

    let currentFilters = {};
    let currentIndicators = [...indicators];
    let selectedIndicatorId = null;
    let isDropdownOpen = false;

    // Initialize with all indicators
    updateIndicatorOptions(currentIndicators);
    updateCountDisplay('');
    updateAllFilterOptions();

    // Handle filter changes
    displayFilters.forEach(filterKey => {
        const filterSelect = document.querySelector(`select[data-row-id="${rowId}"][data-filter-key="${filterKey}"]`);
        if (filterSelect) {
            filterSelect.addEventListener('change', function() {
                const selectedValue = this.value;
                currentFilters[filterKey] = selectedValue;

                debugLog('dynamic-indicators', `Filter ${filterKey} changed to: ${selectedValue}`);

                // Apply all current filters to get filtered indicators
                currentIndicators = indicators.filter(indicator => {
                    return Object.entries(currentFilters).every(([key, value]) => {
                        if (!value) return true;
                        return indicator[key] === value;
                    });
                });

                // Update all other filter options based on the new filtered indicators
                updateAllFilterOptions();

                searchInput.value = "";
                updateIndicatorOptions(currentIndicators);
                updateCountDisplay(filterKey);
                hideDropdown();
            });
        }
    });

    // Handle search input
    searchInput.addEventListener('focus', showDropdown);
    searchInput.addEventListener('input', function() {
        const searchTerm = this.value.toLowerCase().trim();

        let visibleIndicators = currentIndicators;
        if (searchTerm) {
            visibleIndicators = currentIndicators.filter(indicator => {
                return indicator.name.toLowerCase().includes(searchTerm);
            });
        }

        updateIndicatorOptions(visibleIndicators);
        updateCountDisplay('', searchTerm);

        if (!isDropdownOpen) {
            showDropdown();
        }
    });

    function updateAllFilterOptions() {
        displayFilters.forEach(filterKey => {
            const filterSelect = document.querySelector(`select[data-row-id="${rowId}"][data-filter-key="${filterKey}"]`);
            if (!filterSelect) return;

            const currentValue = currentFilters[filterKey] || '';

            // Get all unique values for this filter from currently filtered indicators
            const availableValues = [...new Set(
                currentIndicators
                    .map(indicator => indicator[filterKey])
                    .filter(value => value && typeof value === 'string' && value.trim())
            )].sort();

            // Save current selection
            const selectedValue = filterSelect.value;

            // Update options using DOM construction
            const filterLabel = filterKey.charAt(0).toUpperCase() + filterKey.slice(1);
            const labels = window.DYNAMIC_INDICATORS_LABELS || {};
            filterSelect.replaceChildren();
            const allOption = document.createElement('option');
            allOption.value = '';
            allOption.textContent = `${labels.all || 'All'} ${filterLabel}s`;
            filterSelect.appendChild(allOption);
            availableValues.forEach(value => {
                const option = document.createElement('option');
                option.value = value;
                option.textContent = value;
                if (value === selectedValue) {
                    option.selected = true;
                }
                filterSelect.appendChild(option);
            });

            // If the previously selected value is no longer available, clear it
            if (selectedValue && !availableValues.includes(selectedValue)) {
                filterSelect.value = '';
                currentFilters[filterKey] = '';
            }
        });
    }

    function updateIndicatorOptions(indicatorsToShow) {
        optionsContainer.replaceChildren();
        indicatorsToShow.forEach(indicator => {
            const optionDiv = document.createElement('div');
            optionDiv.className = 'px-3 py-2 hover:bg-gray-100 cursor-pointer indicator-option border-b border-gray-100';
            optionDiv.setAttribute('data-indicator-id', indicator.id.toString());
            optionDiv.setAttribute('data-indicator-name', indicator.name);
            const nameDiv = document.createElement('div');
            nameDiv.className = 'font-medium text-gray-900';
            nameDiv.textContent = indicator.name;
            optionDiv.appendChild(nameDiv);
            optionsContainer.appendChild(optionDiv);
        });
        setupOptionClickHandlers();
    }

    function setupOptionClickHandlers() {
        const allOptions = optionsContainer.querySelectorAll('.indicator-option');
        allOptions.forEach(option => {
            option.addEventListener('click', function() {
                const indicatorId = this.getAttribute('data-indicator-id');
                const indicatorName = this.getAttribute('data-indicator-name');

                if (isIndicatorAlreadyAdded(sectionId, indicatorId)) {
                    const labels = window.DYNAMIC_INDICATORS_LABELS || {};
                    const message = labels.indicatorAlreadyAdded || 'This indicator is already added to this section.';
                    if (window.showAlert) window.showAlert(message, 'warning');
                    else console.warn(message);
                    hideDropdown();
                    return;
                }

                // Update the input with selected indicator name only
                searchInput.value = indicatorName;
                selectedIndicatorId = indicatorId;

                hideDropdown();

                // Show loading spinner immediately
                showIndicatorLoadingState(rowId, indicatorName);

                // Add the dynamic indicator without reloading the page
                addDynamicIndicator(sectionId, indicatorId, rowId);
            });
        });
    }

    function updateCountDisplay(filterName, searchTerm = '') {
        if (!countDisplay) return;

        const visibleCount = optionsContainer.querySelectorAll('.indicator-option').length;
        const labels = window.DYNAMIC_INDICATORS_LABELS || {};

        let message = `${visibleCount} ${labels.indicators || 'indicators'}`;

        if (searchTerm) {
            message += ` ${labels.found || 'found'}`;
        } else {
            // Build a description of active filters
            const activeFilters = Object.entries(currentFilters).filter(([key, value]) => value);

            if (activeFilters.length === 0) {
                message += ` ${labels.available || 'available'}`;
            } else if (activeFilters.length === 1) {
                const [key, value] = activeFilters[0];
                message += ` ${labels.availableIn || 'available in'} ${value}`;
            } else {
                // Multiple filters active
                const filterDescriptions = activeFilters.map(([key, value]) => `${key}: ${value}`);
                message += ` ${labels.available || 'available'} (${labels.filteredBy || 'filtered by'} ${filterDescriptions.join(', ')})`;
            }
        }

        countDisplay.textContent = message;
    }

    function showDropdown() {
        dropdownList.classList.remove('hidden');
        isDropdownOpen = true;
    }

    function hideDropdown() {
        dropdownList.classList.add('hidden');
        isDropdownOpen = false;
    }

    // Hide dropdown when clicking outside
    document.addEventListener('click', function(event) {
        if (!event.target.closest(`[data-row-id="${rowId}"]`)) {
            hideDropdown();
        }
    });
}

function showIndicatorLoadingState(rowId, indicatorName) {
    const addRow = document.getElementById(`indicator-row-${rowId}`);
    if (!addRow) return;

    // Replace row content with loading state immediately
    addRow.replaceChildren();
    addRow.className = 'flex items-center justify-between p-4 bg-blue-50 border border-blue-200 rounded-lg';

    const loadingContent = document.createElement('div');
    loadingContent.className = 'flex items-center gap-3 w-full';

    // Create spinner with inline animation for better compatibility
    const spinner = document.createElement('div');
    spinner.className = 'rounded-full h-5 w-5 border-2 border-gray-300 border-t-green-600';
    spinner.style.animation = 'spin 1s linear infinite';

    // Add keyframes if not already present
    if (!document.getElementById('dynamic-indicator-spinner-style')) {
        const style = document.createElement('style');
        style.id = 'dynamic-indicator-spinner-style';
        style.textContent = '@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }';
        document.head.appendChild(style);
    }

    const loadingText = document.createElement('div');
    loadingText.className = 'text-sm text-gray-700 font-medium';
    loadingText.textContent = `Adding "${indicatorName}"...`;

    loadingContent.appendChild(spinner);
    loadingContent.appendChild(loadingText);
    addRow.appendChild(loadingContent);

    // Force a reflow to ensure the loading state is visible
    addRow.offsetHeight;
}

function removeIndicatorLoadingState(rowId) {
    const addRow = document.getElementById(`indicator-row-${rowId}`);
    if (addRow) {
        addRow.remove();
    }
}

function addDynamicIndicator(sectionId, indicatorId, rowId) {
    debugLog('dynamic-indicators', `Adding dynamic indicator ${indicatorId} to section ${sectionId}`);

    const sectionContainer = document.getElementById(`section-container-${sectionId}`);
    const aesId = sectionContainer?.getAttribute('data-aes-id');

    if (!aesId) {
        debugError('dynamic-indicators', 'Assignment entity status ID not found');
        removeIndicatorLoadingState(rowId);
        return;
    }

    // Preview mode uses a mock ACS ID of 0. In that mode, we allow users to explore
    // the picker UX without attempting to persist anything server-side.
    if (String(aesId) === '0') {
        const labels = window.DYNAMIC_INDICATORS_LABELS || {};
        const message = labels.previewModeNotSaved || 'Preview mode: this will not be saved. Assign this template to a country to test saving dynamic indicators.';
        if (window.showAlert) window.showAlert(message, 'info');
        else console.warn(message);

        // Remove the loading state
        removeIndicatorLoadingState(rowId);

        // Add a lightweight preview-only placeholder so users can see something appear.
        try {
            const indicator = (window.availableIndicatorsData?.[sectionId] || []).find(i => String(i.id) === String(indicatorId));
            const name = indicator?.name || `Indicator ${indicatorId}`;

            const placeholder = document.createElement('div');
            placeholder.className = 'form-group form-item-block border p-4 rounded-md bg-white border-l-4 border-l-green-300 bg-green-50';
            placeholder.setAttribute('data-item-type', 'indicator');
            placeholder.setAttribute('data-preview-indicator', 'true');

            const flexDiv = document.createElement('div');
            flexDiv.className = 'flex items-start justify-between';

            const leftDiv = document.createElement('div');
            leftDiv.className = 'flex-1 pr-2';
            const labelEl = document.createElement('label');
            labelEl.className = 'block text-md font-semibold text-gray-800 mb-1';
            labelEl.appendChild(document.createTextNode(name));
            labelEl.appendChild(document.createTextNode(' '));
            const previewSpan = document.createElement('span');
            previewSpan.className = 'text-xs text-gray-500';
            previewSpan.textContent = '(preview)';
            labelEl.appendChild(previewSpan);
            const descDiv = document.createElement('div');
            descDiv.className = 'text-xs text-gray-600';
            descDiv.textContent = 'This is a preview-only placeholder. Dynamic indicators are persisted only on real assignments.';
            leftDiv.appendChild(labelEl);
            leftDiv.appendChild(descDiv);

            const removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.className = 'text-red-600 hover:text-red-800';
            removeBtn.setAttribute('title', 'Remove');
            const trashIcon = document.createElement('i');
            trashIcon.className = 'fas fa-trash';
            removeBtn.appendChild(trashIcon);

            flexDiv.appendChild(leftDiv);
            flexDiv.appendChild(removeBtn);
            placeholder.appendChild(flexDiv);

            // Add event listener to remove button
            removeBtn.addEventListener('click', () => placeholder.remove());

            const interfaceEl = document.getElementById(`dynamic-indicator-interface-${sectionId}`);
            if (interfaceEl && interfaceEl.parentElement) {
                interfaceEl.parentElement.insertBefore(placeholder, interfaceEl);
            } else if (sectionContainer) {
                sectionContainer.appendChild(placeholder);
            }
        } catch (e) {
            debugWarn('dynamic-indicators', 'Failed to add preview placeholder indicator:', e);
        }

        return;
    }


    // Generate a temporary assignment ID for pending indicators
    const tempAssignmentId = `pending_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

    // Get indicator data from available indicators
    const indicator = (window.availableIndicatorsData?.[sectionId] || []).find(i => String(i.id) === String(indicatorId));
    if (!indicator) {
        debugError('dynamic-indicators', `Indicator ${indicatorId} not found in available indicators`);
        removeIndicatorLoadingState(rowId);
        const labels = window.DYNAMIC_INDICATORS_LABELS || {};
        const errorMessage = labels.failedToAdd || 'Failed to add indicator';
        if (window.showAlert) window.showAlert(errorMessage, 'error');
        else console.warn(errorMessage);
        return;
    }

    // Fetch rendered HTML for pending indicator (without creating DB record)
    const formData = new FormData();
    formData.append('section_id', sectionId);
    formData.append('indicator_bank_id', indicatorId);
    formData.append('assignment_entity_status_id', aesId);
    formData.append('temp_assignment_id', tempAssignmentId);

    // Get CSRF token
    const csrfToken = document.querySelector('input[name="csrf_token"]')?.value ||
                     document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');

    const _dfetch = (window.getFetch && window.getFetch()) || fetch;
    _dfetch('/api/forms/dynamic-indicators/render-pending', {
        method: 'POST',
        body: formData,
        headers: {
            'X-CSRFToken': csrfToken,
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(data => {
                const labels = window.DYNAMIC_INDICATORS_LABELS || {};
                const errorMessage = labels.failedToAdd || 'Failed to add indicator';
                throw new Error(data.error || errorMessage);
            });
        }
        return response.json();
    })
    .then(data => {
        if (!data.success || !data.html) {
            throw new Error(data.error || 'Failed to render indicator');
        }

        // Remove loading state before inserting
        removeIndicatorLoadingState(rowId);

        try {
            const interfaceEl = document.getElementById(`dynamic-indicator-interface-${sectionId}`);
            const insertionPoint = interfaceEl?.parentElement || sectionContainer;

            const parser = new DOMParser();
            const doc = parser.parseFromString(data.html.trim(), 'text/html');
            const indicatorElement = doc.body.firstElementChild;

            if (!indicatorElement) {
                throw new Error('Failed to parse indicator HTML');
            }

            if (!insertionPoint) {
                throw new Error('Insertion point not found');
            }

            // Add hidden input to track pending indicator for form submission
            const form = document.querySelector('form#focalDataEntryForm');
            if (form) {
                const pendingInput = document.createElement('input');
                pendingInput.type = 'hidden';
                pendingInput.name = `pending_dynamic_indicator_${sectionId}`;
                pendingInput.value = `${indicatorId}:${tempAssignmentId}`;
                pendingInput.setAttribute('data-temp-assignment-id', tempAssignmentId);
                form.appendChild(pendingInput);
            }

            // Mark the indicator element as pending
            indicatorElement.setAttribute('data-pending-assignment-id', tempAssignmentId);

            if (interfaceEl) {
                insertionPoint.insertBefore(indicatorElement, interfaceEl);
            } else {
                insertionPoint.appendChild(indicatorElement);
            }

            applyLayoutToSection(sectionContainer);
            initializeFieldListeners(indicatorElement);

            if (window.reinitializeDisaggregationCalculator) {
                window.reinitializeDisaggregationCalculator();
            }

            if (window.cleanupInputValues) {
                window.cleanupInputValues();
            }

            refreshDynamicIndicatorButtonStates();
        } catch (insertError) {
            debugError('dynamic-indicators', 'Error inserting indicator:', insertError);
            throw new Error('Failed to insert indicator into page');
        }
    })
    .catch(error => {
        debugError('dynamic-indicators', 'Failed to add dynamic indicator:', error);
        removeIndicatorLoadingState(rowId);
        const labels = window.DYNAMIC_INDICATORS_LABELS || {};
        const errorMessage = labels.failedToAdd || 'Failed to add indicator';
        const msg = `${errorMessage}: ${error.message}`;
        if (window.showAlert) window.showAlert(msg, 'error');
        else console.warn(msg);
    });
}

function isIndicatorAlreadyAdded(sectionId, indicatorId) {
    const sectionContainer = document.getElementById(`section-container-${sectionId}`);

    if (sectionContainer) {
        const existing = sectionContainer.querySelector(`.propose-changes-btn[data-indicator-id="${indicatorId}"]`);
        if (existing) {
            return true;
        }
    }
    return false;
}

function openIndicatorProposalForm(sectionId) {
    debugLog('dynamic-indicators', `Opening indicator proposal form for section ${sectionId}`);

    // Get frontend configuration
    const frontendConfig = window.FRONTEND_CONFIG || {};
    const proposeOverrideUrl = (frontendConfig.proposeNewIndicatorUrl || '').trim();

    // If organization branding provides an explicit proposal URL, use it as-is.
    // (No extra query params are appended to avoid breaking external destinations.)
    if (proposeOverrideUrl) {
        const newWindow = window.open(proposeOverrideUrl, '_blank');
        if (!newWindow) {
            window.location.href = proposeOverrideUrl;
        }
        return;
    }

    // Not configured: link should be hidden, but keep a safe message if called programmatically.
    debugError('dynamic-indicators', 'Propose new indicator URL not configured');
    const msg = 'Propose new indicator URL not configured. Please contact an administrator.';
    if (window.showAlert) window.showAlert(msg, 'error');
    else console.warn(msg);
}

function openIndicatorProposalFormForExisting(indicatorId, indicatorName) {
    debugLog('dynamic-indicators', `Opening indicator proposal form for existing indicator ${indicatorId}: ${indicatorName}`);

    // Get frontend configuration
    const frontendConfig = window.FRONTEND_CONFIG || {};
    const detailsUrlTemplate = (frontendConfig.indicatorDetailsUrlTemplate || '').trim();
    const baseUrl = frontendConfig.baseUrl || '';
    const indicatorBankPath = frontendConfig.indicatorBankPath || '/indicator-bank';

    // If organization branding provides an explicit details URL template, use it.
    // (No extra query params are appended to avoid breaking external destinations.)
    if (detailsUrlTemplate) {
        const url = detailsUrlTemplate.replace('{id}', encodeURIComponent(String(indicatorId)));
        const newWindow = window.open(url, '_blank');
        if (!newWindow) {
            window.location.href = url;
        }
        return;
    }

    if (!baseUrl) {
        debugError('dynamic-indicators', 'Website base URL not configured');
        const msg = 'Website URL not configured. Please contact an administrator.';
        if (window.showAlert) window.showAlert(msg, 'error');
        else console.warn(msg);
        return;
    }

    // Create a URL to the existing indicator's detail page with proposal form
    const proposalUrl = new URL(`${baseUrl}${indicatorBankPath}/${indicatorId}`, window.location.origin);
    proposalUrl.searchParams.set('proposal_source', 'form');
    proposalUrl.searchParams.set('proposal_type', 'changes');
    proposalUrl.searchParams.set('return_to', encodeURIComponent(window.location.href));

    // Open the frontend page in a new tab/window
    const newWindow = window.open(proposalUrl.toString(), '_blank');

    if (!newWindow) {
        // If popup was blocked, redirect in the same window
        const msg = 'Please allow popups for this site to open the indicator proposal form in a new tab. Redirecting in the same window instead.';
        if (window.showAlert) window.showAlert(msg, 'info');
        else console.warn(msg);
        window.location.href = proposalUrl.toString();
    }
}

function getSectionName(sectionId) {
    const sectionContainer = document.getElementById(`section-container-${sectionId}`);
    if (sectionContainer) {
        // Find section heading regardless of level (h3, h4, etc.)
        const heading = sectionContainer.querySelector('h1, h2, h3, h4, h5, h6');
        if (heading) {
            // Clean up heading text by removing prefixes and icons
            return heading.textContent.trim()
                .replace(/^[\d\.]+\s*/, '')     // Remove numbering like "1.2."
                .replace(/^↳\s*/, '')           // Remove subsection arrow
                .replace(/^\s*[\w\s]*?\s*/, '') // Remove any remaining prefixes
                .trim() || `Section ${sectionId}`;
        }
    }
    return `Section ${sectionId}`;
}

function refreshDynamicIndicatorButtonStates() {
    debugLog('dynamic-indicators', '🔄 Refreshing all button states...');

    const dynamicSections = document.querySelectorAll('[data-section-type="dynamic_indicators"]');

    dynamicSections.forEach(sectionContainer => {
        refreshSingleSectionButtonState(sectionContainer);
    });

    debugLog('dynamic-indicators', '✅ All button states refreshed');
}

function refreshSingleSectionButtonState(sectionContainer) {
    const sectionId = sectionContainer.id.replace('section-container-', '');
    const context = getSectionContext(sectionContainer, sectionId);

    // Handle missing interface
    if (shouldRecreateInterface(context)) {
        recreateInterfaceIfNeeded(sectionContainer, sectionId, context);
    }

    // Update button visibility (this also updates the count display)
    updateButtonVisibility(context);

    // Also update count display directly if max indicators is set (in case button visibility didn't update it)
    if (context.maxIndicators) {
        const maxCount = parseInt(context.maxIndicators);
        updateMaxIndicatorsCount(sectionId, context.currentIndicatorCount, maxCount);
    }

    // Log diagnostics if button is missing
    if (!context.addBtn) {
        logButtonDiagnostics(sectionId, context);
    }
}

function getSectionContext(sectionContainer, sectionId) {
    const addBtn = document.getElementById(`add-indicator-row-btn-${sectionId}`);
    const maxIndicators = sectionContainer.getAttribute('data-max-dynamic-indicators');

    // Count only indicators within this section container (including dynamic indicators)
    // Dynamic indicators have data-assignment-id attribute, regular indicators don't
    // But for dynamic indicator sections, all indicators should be dynamic
    const allIndicators = sectionContainer.querySelectorAll('.form-item-block[data-item-type="indicator"]');
    // Filter out preview indicators if any
    const currentIndicatorCount = Array.from(allIndicators).filter(el =>
        !el.hasAttribute('data-preview-indicator')
    ).length;

    const dynamicIndicatorInterface = sectionContainer.querySelector('#dynamic-indicator-interface-' + sectionId);
    const form = document.querySelector('form#focalDataEntryForm');
    const isFormEditable = form && document.querySelectorAll('button[name="action"]').length > 0;
    const availableIndicators = window.availableIndicatorsData?.[sectionId];

    return {
        sectionId,
        addBtn,
        maxIndicators,
        currentIndicatorCount,
        dynamicIndicatorInterface,
        isFormEditable,
        availableIndicators
    };
}

function shouldRecreateInterface(context) {
    return !context.dynamicIndicatorInterface &&
           context.isFormEditable &&
           context.availableIndicators &&
           context.availableIndicators.length > 0;
}

function recreateInterfaceIfNeeded(sectionContainer, sectionId, context) {
    debugLog('dynamic-indicators', `🔧 Recreating missing interface for section ${sectionId}`);

    const maxCount = context.maxIndicators ? parseInt(context.maxIndicators) : null;

    if (!maxCount || context.currentIndicatorCount < maxCount) {
        recreateDynamicIndicatorInterface(sectionContainer, sectionId, context.maxIndicators, context.currentIndicatorCount);

        // Update button reference after recreation
        setTimeout(() => {
            context.addBtn = document.getElementById(`add-indicator-row-btn-${sectionId}`);
            debugLog('dynamic-indicators', `Button reference updated: ${!!context.addBtn}`);
        }, 10);
    } else {
        debugLog('dynamic-indicators', `Interface not recreated: max limit reached (${context.currentIndicatorCount}/${maxCount})`);
    }
}

function updateButtonVisibility(context) {
    if (!context.addBtn) return;

    if (context.maxIndicators) {
        const maxCount = parseInt(context.maxIndicators);
        const isVisible = context.currentIndicatorCount < maxCount;

        context.addBtn.style.display = isVisible ? '' : 'none';

        // Update the max indicators count text
        updateMaxIndicatorsCount(context.sectionId, context.currentIndicatorCount, maxCount);

        debugLog('dynamic-indicators',
            `Button ${isVisible ? 'visible' : 'hidden'} for section ${context.sectionId}: ${context.currentIndicatorCount}/${maxCount} indicators`);
    } else {
        // No limit - always show
        context.addBtn.style.display = '';
        debugLog('dynamic-indicators',
            `Button visible for section ${context.sectionId}: no limit (${context.currentIndicatorCount} indicators)`);
    }
}

function updateMaxIndicatorsCount(sectionId, currentCount, maxCount) {
    const interfaceEl = document.getElementById(`dynamic-indicator-interface-${sectionId}`);
    if (!interfaceEl) return;

    // Find the max indicators text span (it's a span with text-sm text-gray-500 mr-4)
    const maxIndicatorsSpan = interfaceEl.querySelector('.text-sm.text-gray-500.mr-4');
    if (maxIndicatorsSpan) {
        const templates = window.DYNAMIC_INDICATORS_TEMPLATES || {};
        const text = templates.maxIndicators ?
            templates.maxIndicators.replace('%(current)s', currentCount).replace('%(max)s', maxCount) :
            `Max indicators: ${currentCount}/${maxCount}`;
        maxIndicatorsSpan.textContent = text;
    }
}

function logButtonDiagnostics(sectionId, context) {
    debugLog('dynamic-indicators', `🔍 Missing button for section ${sectionId}:`);
    debugLog('dynamic-indicators', `  - Form editable: ${context.isFormEditable}`);
    debugLog('dynamic-indicators', `  - Available indicators: ${context.availableIndicators?.length || 0}`);
    debugLog('dynamic-indicators', `  - Max indicators: ${context.maxIndicators || 'unlimited'}`);
    debugLog('dynamic-indicators', `  - Current count: ${context.currentIndicatorCount}`);

    if (!context.isFormEditable) {
        debugLog('dynamic-indicators', `  - ⚠️ Form appears to be read-only or in preview mode`);
    }
}

function recreateDynamicIndicatorInterface(sectionContainer, sectionId, maxIndicators, currentCount) {
    debugLog('dynamic-indicators', `🏗️ Recreating interface for section ${sectionId}`);

    // Check if interface already exists to prevent duplicates
    const existingInterface = document.getElementById(`dynamic-indicator-interface-${sectionId}`);
    if (existingInterface) {
        debugLog('dynamic-indicators', `Interface already exists for section ${sectionId}, skipping recreation`);
        return;
    }

    // Create interface HTML uniformly for all sections
    const interfaceHtml = createInterfaceHTML(sectionId, sectionContainer, maxIndicators, currentCount);

    // Find insertion point uniformly
    const insertionPoint = findInsertionPoint(sectionContainer);

    if (insertionPoint) {
        // Use DOMParser for CSP-safe HTML parsing
        const parser = new DOMParser();
        const doc = parser.parseFromString(interfaceHtml.trim(), 'text/html');
        const interfaceElement = doc.body.firstElementChild;
        if (interfaceElement) {
            insertionPoint.appendChild(interfaceElement);
        }

        // Set up event listeners uniformly
        setupRecreatedButtons(sectionContainer, sectionId);
    }
}

function createInterfaceHTML(sectionId, sectionContainer, maxIndicators, currentCount) {
    const labels = window.DYNAMIC_INDICATORS_LABELS || {};
    const templates = window.DYNAMIC_INDICATORS_TEMPLATES || {};

    // Determine spacing class based on collapsible content indentation rather than brittle space-y-* classes
    // (layout.js can replace space-y-6 -> space-y-3, space-y-4 -> space-y-2).
    const directContent =
        sectionContainer.querySelector(':scope > [data-collapsible-content]') ||
        sectionContainer.querySelector('[data-collapsible-content]');
    const spacingClass = (directContent && directContent.classList.contains('pl-6')) ? 'mt-4' : 'mt-6';

    const maxIndicatorsText = maxIndicators ? `
        <span class="text-sm text-gray-500 mr-4">
            ${escapeHtmlText(templates.maxIndicators ? templates.maxIndicators.replace('%(current)s', currentCount).replace('%(max)s', maxIndicators) : `Max indicators: ${currentCount}/${maxIndicators}`)}
        </span>
    ` : '';

    return `
        <div class="${spacingClass}" id="dynamic-indicator-interface-${sectionId}" data-aes-id="${escapeHtmlAttr(sectionContainer.getAttribute('data-aes-id'))}">
            <div class="flex items-center justify-between mb-4">
                <div class="flex-1">
                    <p class="text-sm text-gray-600 italic">${escapeHtmlText(labels.useButtonToAdd || 'Use the button to add indicators to this section.')}</p>
                </div>
                <div class="flex items-center gap-3">
                    ${maxIndicatorsText}
                    <button type="button" id="add-indicator-row-btn-${sectionId}"
                            class="bg-green-600 hover:bg-green-700 text-white px-3 py-2 rounded-md text-sm font-medium transition-colors duration-200 flex items-center">
                        <i class="fas fa-plus mr-2"></i>
                        ${escapeHtmlText(labels.addIndicator || 'Add Indicator')}
                    </button>
                </div>
            </div>

            <div id="dynamic-indicator-rows-${sectionId}" class="space-y-3">
                <!-- Dynamic indicator selection rows will be added here -->
            </div>
        </div>
    `;
}

function findInsertionPoint(sectionContainer) {
    // Always prefer the collapsible content container so the interface hides when the section is collapsed.
    // Note: layout.js may change space-y-* classes; do not rely on them here.
    const directContent =
        sectionContainer.querySelector(':scope > [data-collapsible-content]') ||
        sectionContainer.querySelector('[data-collapsible-content]');
    if (directContent) {
        return directContent;
    }

    // Fallback: look for any content area that's not inside a form item
    const contentAreas = sectionContainer.querySelectorAll('.space-y-2, .space-y-3, .space-y-4, .space-y-6');
    for (const area of contentAreas) {
        if (!area.closest('.form-item-block')) {
            return area;
        }
    }

    // Final fallback to section container itself
    return sectionContainer;
}

function setupRecreatedButtons(sectionContainer, sectionId) {
    const addBtn = document.getElementById(`add-indicator-row-btn-${sectionId}`);

    if (addBtn) {
        addBtn.addEventListener('click', () => handleAddIndicator(sectionContainer, sectionId));
    }
}
