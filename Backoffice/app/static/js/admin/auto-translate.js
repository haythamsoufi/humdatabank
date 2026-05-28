(function() {
    'use strict';
    var cfg = window.autoTranslatePageConfig || {};

    function normalizeAutoTranslateConfig(config) {
        var c = config || {};
        if (!c.itemType && c.item_type) {
            c.itemType = c.item_type;
        }
        if (!c.itemType) {
            c.itemType = cfg.t.items_691d502c;
        }
        if (!c.permission_context && c.permissionContext) {
            c.permission_context = c.permissionContext;
        }
        if (!c.permission_code && c.permissionCode) {
            c.permission_code = c.permissionCode;
        }
        return c;
    }

    const autoTranslateConfig = normalizeAutoTranslateConfig(
        typeof window.autoTranslateConfigFromTemplate !== 'undefined'
            ? window.autoTranslateConfigFromTemplate
            : (cfg.runtimeConfig || {
                endpoint: null,
                itemType: cfg.t.items_691d502c,
                permission_context: null,
                permission_code: null
            })
    );

    // Debug logging (opt-in): we only log when formBuilderDebug explicitly enables it.
    // This template is shared across many pages; avoid noisy logs in normal usage.
    const configLabel = cfg.t.auto_translate_config_0e006338;
    const endpointLabel = cfg.t.auto_translate_config_endpoint_943baec2;
    const itemTypeLabel = cfg.t.auto_translate_config_itemtype_988ffa42;
    const configForLog = autoTranslateConfig;
    setTimeout(function() {
        if (window.formBuilderDebug && window.formBuilderDebug.isEnabled && window.formBuilderDebug.isEnabled('translation')) {
            window.formBuilderDebug.log('translation', configLabel + ':', configForLog);
            window.formBuilderDebug.log('translation', endpointLabel + ':', configForLog.endpoint);
            window.formBuilderDebug.log('translation', itemTypeLabel + ':', configForLog.itemType);
        }
    }, 0);

    // Translation state management
    let translationState = {
        isRunning: false,
        isPaused: false,
        shouldStop: false,
        totalItems: 0,
        processedItems: 0,
        successCount: 0,
        skippedCount: 0,
        errorCount: 0,
        errors: []
    };

    const languageDisplayNames = cfg.languageDisplayNames || {};

    // Initialize modal functionality
    function initializeAutoTranslateModal() {
        if (!autoTranslateConfig.endpoint) {
            const endpointNotConfiguredMsg = cfg.t.auto_translate_endpoint_not_configured_711f945a;
            console.error(endpointNotConfiguredMsg);
            return;
        }

        // Load available translation services
        function loadTranslationServices() {
            const _fetchFn = (window.getFetch && window.getFetch()) || fetch;
            _fetchFn(cfg.urls.translationServices)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        populateServiceDropdown(data.services, data.default_service);
                    } else {
                        const failedToLoadMsg = cfg.t.failed_to_load_translation_services_61e422b0;
                        console.error(failedToLoadMsg + ':', data.error || data.message);
                        const serviceMessage = document.getElementById('service-loading-message');
                        if (serviceMessage) serviceMessage.textContent = failedToLoadMsg;
                    }
                })
                .catch(error => {
                    const errorLoadingMsg = cfg.t.error_loading_translation_services_608b37e2;
                    console.error(errorLoadingMsg + ':', error);
                    const serviceMessage = document.getElementById('service-loading-message');
                    const select = document.getElementById('translation-service-select');
                    if (serviceMessage) serviceMessage.textContent = errorLoadingMsg;
                    if (select) {
                        select.innerHTML = '';
                        const option = document.createElement('option');
                        option.textContent = errorLoadingMsg;
                        option.disabled = true;
                        select.appendChild(option);
                    }
                    const startButton = document.getElementById('auto-translate-start-btn');
                    if (startButton) startButton.disabled = true;
                });
        }

        // Populate service dropdown
        function hasAvailableService() {
            const select = jQuery('#translation-service-select');
            if (!select.length) return false;
            const selectedOption = select.find('option:selected');
            if (selectedOption.length && !selectedOption.prop('disabled')) {
                return true;
            }
            return select.find('option:not(:disabled)').length > 0;
        }

        function updateStartButtonState() {
            const startBtn = jQuery('#auto-translate-start-btn');
            if (!startBtn.length) return;
            const hasService = hasAvailableService();
            const hasItems = translationState.totalItems > 0;
            startBtn.prop('disabled', !(hasService && hasItems));
        }

        function populateServiceDropdown(services, defaultService) {
            const select = document.getElementById('translation-service-select');
            const serviceMessage = document.getElementById('service-loading-message');
            const startButton = document.getElementById('auto-translate-start-btn');
            if (!select) return;

            // Clear existing options
            select.innerHTML = '';

            // Add options for each service
            services.forEach(service => {
                const option = document.createElement('option');
                option.value = service.value;

                // Add status indicator to label
                let label = service.label;
                if (!service.is_available) {
                    const offlineLabel = cfg.t.offline_f3d49e91;
                    label += ' ' + offlineLabel;
                    option.disabled = true;
                }

                option.textContent = label;

                // Select default service if it's available, otherwise select first available service
                if (service.is_default && service.is_available) {
                    option.selected = true;
                } else if (service.is_available && !select.value) {
                    // Select first available service if no default is selected
                    option.selected = true;
                }

                select.appendChild(option);
            });

            if (services.length === 0) {
                const noServicesMsg = cfg.t.no_translation_services_configured_55e73bd3;
                const option = document.createElement('option');
                option.textContent = noServicesMsg;
                option.disabled = true;
                select.appendChild(option);
                if (serviceMessage) serviceMessage.textContent = noServicesMsg;
                if (startButton) startButton.disabled = true;
                return;
            } else if (serviceMessage) {
                serviceMessage.textContent = cfg.t.select_a_translation_service_18793e6a;
            }

            // If no service is selected (all are unavailable), select the first available option
            if (!select.value) {
                const firstAvailable = Array.from(select.options).find(opt => !opt.disabled);
                if (firstAvailable) {
                    firstAvailable.selected = true;
                    if (startButton && translationState.totalItems > 0) {
                        startButton.disabled = false;
                    }
                } else if (startButton) {
                    startButton.disabled = true;
                }
            } else if (startButton && translationState.totalItems > 0) {
                startButton.disabled = false;
            }

            // Clear any stale warning that may have been shown before services finished loading
            const currentlySelected = Array.from(select.options).find(opt => opt.selected);
            if (currentlySelected && !currentlySelected.disabled) {
                jQuery('.service-warning').remove();
            }

            updateStartButtonState();
        }

        // Reset translation state
        // IMPORTANT: mutate in-place instead of reassigning so that
        // window.autoTranslateModal.translationState always refers to the same live object.
        // Reassigning the local variable breaks the reference held by page-specific loops
        // (e.g. processNextTranslation in manage_translations.html) and causes pause/stop
        // to be ignored on any run after the first modal close.
        function resetTranslationState() {
            translationState.isRunning = false;
            translationState.isPaused = false;
            translationState.shouldStop = false;
            translationState.totalItems = 0;
            translationState.processedItems = 0;
            translationState.successCount = 0;
            translationState.skippedCount = 0;
            translationState.errorCount = 0;
            translationState.errors = [];

            // Keep the shared reference in sync (safety net for any code path that may
            // have stored or re-exposed the state object through window.autoTranslateModal).
            if (window.autoTranslateModal) {
                window.autoTranslateModal.translationState = translationState;
            }

            // Reset button states
            jQuery('#auto-translate-pause-btn').addClass('hidden');
            jQuery('#auto-translate-resume-btn').addClass('hidden');
            jQuery('#auto-translate-stop-btn').removeClass('hidden');
            jQuery('#auto-translate-close-btn').addClass('hidden');
        }

        // Update estimated time based on selected languages
        function updateEstimatedTime() {
            const selectedLanguages = jQuery('.language-checkbox:checked:not(:disabled)').length;
            const totalItems = translationState.totalItems || 0;
            const estimatedSeconds = selectedLanguages * totalItems * 2; // 2 seconds per translation
            const minutes = Math.ceil(estimatedSeconds / 60);

            let timeText;
            if (minutes < 1) {
                timeText = cfg.t.less_than_1_minute_a4542540;
            } else if (minutes === 1) {
                timeText = cfg.t.about_1_minute_11785573;
            } else {
                const aboutLabel = cfg.t.about_8f7f4c1c;
                const minutesLabel = cfg.t.minutes_640fd0cc;
                timeText = `${aboutLabel} ${minutes} ${minutesLabel}`;
            }

            jQuery('#estimated-time').text(timeText);
        }

        // Update language counts in the modal - called by page-specific implementations
        function updateLanguageCounts(counts) {
            // Helper to check if a value is PO file metadata
            function isMetadataString(str) {
                if (typeof str !== 'string') return false;
                const strLower = str.toLowerCase();
                const metadataKeys = [
                    'project-id-version', 'report-msgid-bugs-to', 'pot-creation-date',
                    'po-revision-date', 'last-translator', 'language-team', 'mime-version',
                    'content-type', 'content-transfer-encoding', 'plural-forms', 'generated-by'
                ];
                const metadataKeyCount = metadataKeys.filter(key => strLower.includes(key)).length;
                return metadataKeyCount >= 3;
            }

            Object.keys(counts).forEach(lang => {
                // Skip if language key itself is metadata
                if (isMetadataString(lang)) {
                    delete counts[lang];
                    return;
                }

                // Ensure count is a number (defensive programming)
                let count = counts[lang];

                // Check if count value is a metadata string
                if (typeof count === 'string' && isMetadataString(count)) {
                    count = 0;
                } else if (typeof count !== 'number') {
                    // Try to parse as number
                    const parsed = parseInt(count);
                    if (isNaN(parsed) || isMetadataString(String(count))) {
                        count = 0;
                    } else {
                        count = parsed;
                    }
                }

                counts[lang] = count; // Update the counts object with numeric value

                const checkbox = jQuery(`input[value="${lang}"]`);
                const countElement = jQuery(`#${lang}-count`);

                // Update count display
                countElement.text(count);

                // Update checkbox state based on count
                if (count === 0) {
                    // Disable and uncheck if no translations needed
                    checkbox.prop('checked', false).prop('disabled', true);
                    checkbox.closest('label').addClass('opacity-50 cursor-not-allowed');
                } else {
                    // Enable and check by default if translations needed
                    checkbox.prop('disabled', false);
                    checkbox.closest('label').removeClass('opacity-50 cursor-not-allowed');
                    // Only check if it wasn't already checked (preserve user selection)
                    if (!checkbox.prop('checked')) {
                        checkbox.prop('checked', true);
                    }
                }
            });

            // Ensure all values are numbers before reducing
            const totalCount = Object.values(counts).reduce((sum, count) => {
                const numCount = typeof count === 'number' ? count : (parseInt(count) || 0);
                return sum + numCount;
            }, 0);
            translationState.totalItems = totalCount;

            // Update summary
            const overwriteExisting = jQuery('#overwrite-existing-translations').is(':checked');

            // Check if rows are selected
            let selectedMsgids = null;
            if (window.gridHelper && typeof window.gridHelper.getSelectedRows === 'function') {
                const selectedRows = window.gridHelper.getSelectedRows();
                if (selectedRows && selectedRows.length > 0) {
                    selectedMsgids = new Set(selectedRows.map(row => row.msgid).filter(msgid => msgid));
                }
            } else if (window.gridApi && typeof window.gridApi.getSelectedRows === 'function') {
                const selectedRows = window.gridApi.getSelectedRows();
                if (selectedRows && selectedRows.length > 0) {
                    selectedMsgids = new Set(selectedRows.map(row => row.msgid).filter(msgid => msgid));
                }
            }

            const hasSelection = selectedMsgids && selectedMsgids.size > 0;

            if (totalCount === 0) {
                const allLabel = cfg.t.all_b1c94ca2;
                const alreadyTranslatedLabel = cfg.t.are_already_translated_04d7029d;
                jQuery('#translation-summary').html(`<span class="text-green-600">${allLabel} ${autoTranslateConfig.itemType} ${alreadyTranslatedLabel}</span>`);
                jQuery('#auto-translate-start-btn').prop('disabled', true);
            } else {
                const foundLabel = cfg.t.found_5d695cc2;
                const blankLabel = overwriteExisting ? "" : cfg.t.blank_8e15625d;
                let readyForTranslationLabel = overwriteExisting
                    ? cfg.t.will_be_translated_overwriting_existing__7c6e6166
                    : cfg.t.ready_for_translation_4cf7ff20;

                // Add selection info if rows are selected
                if (hasSelection) {
                    const selectedLabel = cfg.t.from_selected_rows_e9b812b9;
                    readyForTranslationLabel = readyForTranslationLabel.replace('.', ' ' + selectedLabel + '.');
                }

                jQuery('#translation-summary').html(`${foundLabel} <strong>${totalCount}</strong> ${blankLabel} ${autoTranslateConfig.itemType} ${readyForTranslationLabel}`);
                updateStartButtonState();
            }

            updateEstimatedTime();
        }

        function notifyCompletion() {
            const state = (window.autoTranslateModal && window.autoTranslateModal.translationState)
                ? window.autoTranslateModal.translationState : translationState;
            const selectedLanguages = jQuery('.language-checkbox:checked:not(:disabled)').map(function() {
                return jQuery(this).val();
            }).get();
            const selectedService = jQuery('#translation-service-select').val() || '';
            const summaryUrl = cfg.urls.autoTranslateSummary;
            const _fetchFn = (window.getFetch && window.getFetch()) || fetch;
            try {
                _fetchFn(summaryUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': (document.querySelector('meta[name="csrf-token"]') || {}).content || '',
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: JSON.stringify({
                        total: state.processedItems || 0,
                        success_count: state.successCount || 0,
                        skipped_count: state.skippedCount || 0,
                        error_count: state.errorCount || 0,
                        languages: selectedLanguages,
                        context: autoTranslateConfig.permission_context || '',
                        service: selectedService
                    })
                });
            } catch (_e) { /* best-effort */ }
        }

        // Make functions and config available globally for page-specific implementations
        window.autoTranslateModal = {
            updateLanguageCounts: updateLanguageCounts,
            logProgress: logProgress,
            updateProgress: updateProgress,
            notifyCompletion: notifyCompletion,
            translationState: translationState,
            config: autoTranslateConfig,
            updateEstimatedTime: updateEstimatedTime,
            minimize: function() { minimizeModal(); },
            restore:  function() { restoreModal(); }
        };

        // Log translation progress
        function logProgress(message, type = 'info') {
            // Use DateTimeUtils for consistent formatting if available
            const timestamp = (typeof DateTimeUtils !== 'undefined')
                ? DateTimeUtils.format(new Date(), 'time')
                : new Date().toLocaleTimeString();
            const logClass = type === 'error' ? 'text-red-600'
                : type === 'success' ? 'text-green-600'
                : type === 'warning' ? 'text-amber-600'
                : 'text-gray-600';
            const logEntry = `<div class="${logClass}">[${timestamp}] ${message}</div>`;

            const logContainer = jQuery('#translation-log');
            logContainer.append(logEntry);
            logContainer.scrollTop(logContainer[0].scrollHeight);
        }

        // Update progress display
        function updateProgress() {
            // Use window.autoTranslateModal.translationState to ensure we're reading the current state
            // This is important because page-specific code may update the state directly
            const state = window.autoTranslateModal ? window.autoTranslateModal.translationState : translationState;
            const percentage = state.totalItems > 0
                ? Math.round((state.processedItems / state.totalItems) * 100)
                : 0;

            jQuery('#progress-bar').css('width', percentage + '%');
            jQuery('#progress-text').text(`${state.processedItems}/${state.totalItems}`);
            jQuery('#success-count').text(state.successCount);
            jQuery('#skipped-count').text(state.skippedCount || 0);
            jQuery('#error-count').text(state.errorCount);

            // Show error details if there are errors
            if (state.errorCount > 0) {
                jQuery('#error-details').removeClass('hidden');
                const errorList = state.errors.map(error =>
                    `<div class="py-1">${error}</div>`
                ).join('');
                jQuery('#error-list').html(errorList);
            }

            // Keep mini-banner in sync when running in background
            updateMiniBanner();
        }

        // ── Mini-banner helpers ──────────────────────────────────────────────
        function updateMiniBanner() {
            const miniBanner = document.getElementById('auto-translate-mini-banner');
            // offsetParent is always null for position:fixed elements — check display style only
            if (!miniBanner || miniBanner.style.display === 'none') return;
            const state = (window.autoTranslateModal && window.autoTranslateModal.translationState) || translationState;
            const pct = state.totalItems > 0
                ? Math.round((state.processedItems / state.totalItems) * 100) : 0;
            const miniBar    = document.getElementById('mini-banner-progress-bar');
            const miniPct    = document.getElementById('mini-banner-percent');
            const miniStatus = document.getElementById('mini-banner-status');
            const miniCounts = document.getElementById('mini-banner-counts');
            if (miniBar)    miniBar.style.width = pct + '%';
            if (miniPct)    miniPct.textContent  = pct + '%';
            if (miniCounts) miniCounts.textContent = state.processedItems + '/' + state.totalItems;
            if (miniStatus) {
                if (state.isRunning && !state.isPaused) {
                    miniStatus.textContent = cfg.t.translating_u2026_f91bab78;
                } else if (state.isPaused) {
                    miniStatus.textContent = cfg.t.paused_e99180ab;
                } else if (!state.isRunning && state.totalItems > 0 && state.processedItems >= state.totalItems) {
                    miniStatus.textContent = cfg.t.complete_u2014_click_u25b2_to_restore_d222bcf1;
                } else if (state.totalItems === 0) {
                    miniStatus.textContent = cfg.t.click_u25b2_to_restore_2c5b6894;
                } else {
                    miniStatus.textContent = cfg.t.stopped_c23e2b09;
                }
            }
        }

        function minimizeModal() {
            jQuery('#auto-translate-modal').addClass('hidden');
            jQuery('#auto-translate-mini-banner').show();
            updateMiniBanner();
        }

        function restoreModal() {
            jQuery('#auto-translate-mini-banner').hide();
            jQuery('#auto-translate-modal').removeClass('hidden');
        }

        // Perform translation
        function performTranslation() {
            const selectedLanguages = jQuery('.language-checkbox:checked:not(:disabled)').map(function() {
                return jQuery(this).val();
            }).get();

            if (selectedLanguages.length === 0) {
                const selectLanguageMsg = cfg.t.please_select_at_least_one_language_to_t_4f651e39;
                if (window.showAlert) window.showAlert(selectLanguageMsg, 'warning');
                return;
            }

            // Get selected translation service
            const selectedService = jQuery('#translation-service-select').val();

            translationState.isRunning = true;
            translationState.isPaused = false;
            translationState.shouldStop = false;

            // Re-anchor the shared reference so page-specific translation loops that
            // read window.autoTranslateModal.translationState always see the live object.
            if (window.autoTranslateModal) {
                window.autoTranslateModal.translationState = translationState;
            }

            // Switch to progress view
            jQuery('#confirmation-section').hide();
            jQuery('#progress-section').show();
            jQuery('#confirmation-buttons').hide();
            jQuery('#progress-buttons').show();

            // Show pause button, hide resume button
            jQuery('#auto-translate-pause-btn').removeClass('hidden');
            jQuery('#auto-translate-resume-btn').addClass('hidden');

            // Reset progress
            translationState.processedItems = 0;
            translationState.successCount = 0;
            translationState.skippedCount = 0;
            translationState.errorCount = 0;
            translationState.errors = [];

            const startingLabel = cfg.t.starting_translation_for_debed75c;
            const languagesLabel = cfg.t.languages_f3e334d4;
            const usingLabel = cfg.t.using_78cdeac4;
            logProgress(`${startingLabel} ${selectedLanguages.length} ${languagesLabel} ${usingLabel} ${selectedService}...`);

            // This is a placeholder - the actual implementation depends on the page type
            // Each page should override this function with its specific logic
            if (window.performPageSpecificTranslation) {
                window.performPageSpecificTranslation(selectedLanguages, selectedService);
            } else {
                const functionNotFoundMsg = cfg.t.page_specific_translation_function_not_f_2c4d3ed0;
                const notImplementedMsg = cfg.t.translation_function_not_implemented_for_c685aba8;
                console.error(functionNotFoundMsg);
                logProgress(notImplementedMsg, 'error');
                translationState.isRunning = false;
            }
        }

        // Process translation results
        function processTranslationResults(data) {
            if (data.results) {
                data.results.forEach(result => {
                    translationState.processedItems++;

                    if (result.success) {
                        translationState.successCount++;
                        const translatedLabel = cfg.t.translated_532220db;
                        const itemLabel = cfg.t.item_447b7147;
                        const toLabel = cfg.t.to_01b6e203;
                        logProgress(`${translatedLabel} ${result.item_type || itemLabel} ${result.item_id || ''} ${toLabel} ${languageDisplayNames[result.language] || result.language}`, 'success');
                    } else {
                        translationState.errorCount++;
                        const failedLabel = cfg.t.failed_to_translate_5ed999f0;
                        const itemLabel = cfg.t.item_447b7147;
                        const toLabel = cfg.t.to_01b6e203;
                        const errorMsg = `${failedLabel} ${result.item_type || itemLabel} ${result.item_id || ''} ${toLabel} ${languageDisplayNames[result.language] || result.language}: ${result.error}`;
                        translationState.errors.push(errorMsg);
                        logProgress(errorMsg, 'error');
                    }

                    updateProgress();
                });
            }

            // Check if translation is complete
            if (translationState.processedItems >= translationState.totalItems) {
                translationState.isRunning = false;
                const completedMsg = cfg.t.translation_completed_d0e4ab37;
                logProgress(completedMsg, 'success');
                $('#auto-translate-stop-btn').addClass('hidden');
                $('#auto-translate-close-btn').removeClass('hidden');
                notifyCompletion();
            }
        }

        // Event Handlers

        // Show modal button
        jQuery('#auto-translate-all-btn').on('click', function() {
            // Reset overwrite checkbox to unchecked by default
            jQuery('#overwrite-existing-translations').prop('checked', false);

            // Get selected rows from ag-grid if any
            let selectedMsgids = null;
            if (window.gridHelper && typeof window.gridHelper.getSelectedRows === 'function') {
                const selectedRows = window.gridHelper.getSelectedRows();
                if (selectedRows && selectedRows.length > 0) {
                    selectedMsgids = new Set(selectedRows.map(row => row.msgid).filter(msgid => msgid));
                }
            } else if (window.gridApi && typeof window.gridApi.getSelectedRows === 'function') {
                const selectedRows = window.gridApi.getSelectedRows();
                if (selectedRows && selectedRows.length > 0) {
                    selectedMsgids = new Set(selectedRows.map(row => row.msgid).filter(msgid => msgid));
                }
            }

            // Let page-specific implementation calculate and set counts
            if (window.getPageSpecificTranslationCounts) {
                const counts = window.getPageSpecificTranslationCounts(false, selectedMsgids);
                updateLanguageCounts(counts);
            } else {
                // Default to showing the modal without specific counts
                const fallbackMessage = cfg.t.click_start_translation_blank_6e8f4a2b || cfg.t.items_691d502c;
                jQuery('#translation-summary').html(`${fallbackMessage} ${autoTranslateConfig.itemType}.`);
                jQuery('#auto-translate-start-btn').prop('disabled', false);
            }

            updateEstimatedTime();

            // Show modal (reset drag position; hide any leftover mini-banner)
            if (window.autoTranslateModal && window.autoTranslateModal._resetDragPosition) {
                window.autoTranslateModal._resetDragPosition();
            }
            jQuery('#auto-translate-mini-banner').hide();
            jQuery('#auto-translate-modal').removeClass('hidden');
            jQuery('#confirmation-section').show();
            jQuery('#progress-section').hide();
            jQuery('#confirmation-buttons').show();
            jQuery('#progress-buttons').hide();
        });

        // Modal close handlers
        jQuery('#close-auto-translate-modal-btn, #auto-translate-cancel-btn').on('click', function() {
            if (translationState.isRunning) {
                const closeConfirmMsg = cfg.t.translation_is_in_progress_are_you_sure__c282caab;
                if (window.showConfirmation) {
                    window.showConfirmation(closeConfirmMsg, () => {
                        translationState.shouldStop = true;
                        jQuery('#auto-translate-mini-banner').hide();
                        jQuery('#auto-translate-modal').addClass('hidden');
                        resetTranslationState();
                    }, () => {}, cfg.t.close_d3d2e617, cfg.t.cancel_ea478870, cfg.t.close_modal_d800763e);
                    return;
                }
                translationState.shouldStop = true;
            }
            jQuery('#auto-translate-mini-banner').hide();
            jQuery('#auto-translate-modal').addClass('hidden');
            resetTranslationState();
        });

        // Language selection controls
        jQuery('#select-all-languages').on('click', function() {
            jQuery('.language-checkbox:not(:disabled)').prop('checked', true);
            updateEstimatedTime();
        });

        jQuery('#deselect-all-languages').on('click', function() {
            jQuery('.language-checkbox:not(:disabled)').prop('checked', false);
            updateEstimatedTime();
        });

        // Language checkbox change handler
        jQuery('.language-checkbox').on('change', function() {
            updateEstimatedTime();
        });

        // Overwrite existing translations checkbox change handler
        jQuery('#overwrite-existing-translations').on('change', function() {
            const overwriteExisting = jQuery(this).is(':checked');
            // Get selected rows from ag-grid if any
            let selectedMsgids = null;
            if (window.gridHelper && typeof window.gridHelper.getSelectedRows === 'function') {
                const selectedRows = window.gridHelper.getSelectedRows();
                if (selectedRows && selectedRows.length > 0) {
                    selectedMsgids = new Set(selectedRows.map(row => row.msgid).filter(msgid => msgid));
                }
            } else if (window.gridApi && typeof window.gridApi.getSelectedRows === 'function') {
                const selectedRows = window.gridApi.getSelectedRows();
                if (selectedRows && selectedRows.length > 0) {
                    selectedMsgids = new Set(selectedRows.map(row => row.msgid).filter(msgid => msgid));
                }
            }
            // Recalculate counts based on overwrite mode and selection
            if (window.getPageSpecificTranslationCounts) {
                const counts = window.getPageSpecificTranslationCounts(overwriteExisting, selectedMsgids);
                updateLanguageCounts(counts);
            }
            updateEstimatedTime();
        });

        // Service selector change handler
        jQuery('#translation-service-select').on('change', function() {
            const selectedValue = jQuery(this).val();
            const selectedOption = jQuery(this).find('option:selected');

            // Check if selected service is available
            if (selectedOption.prop('disabled')) {
                // Show warning for unavailable service
                const warningHtml = `<div class="bg-yellow-50 border border-yellow-200 rounded-lg p-3 mt-4 service-warning">
                    <div class="flex items-center">
                        <i class="fas fa-exclamation-triangle text-yellow-600 mr-2"></i>
                        <span class="text-sm text-yellow-800">${cfg.t.warning_selected_service_is_currently_un_e42e0e26}</span>
                    </div>
                </div>`;

                // Remove any existing warning
                jQuery('.service-warning').remove();

                // Add warning after the service selector
                jQuery(this).closest('.bg-gray-50').after(warningHtml);
            } else {
                // Remove warning if service is available
                jQuery('.service-warning').remove();
            }

            updateEstimatedTime();
            updateStartButtonState();
        });

        // Load translation services when modal is shown
        if (autoTranslateConfig.endpoint) {
            loadTranslationServices();
        }

        // Start translation
        jQuery('#auto-translate-start-btn').on('click', function() {
            performTranslation();
        });

        // Pause translation
        jQuery('#auto-translate-pause-btn').on('click', function() {
            translationState.isPaused = true;
            jQuery('#auto-translate-pause-btn').addClass('hidden');
            jQuery('#auto-translate-resume-btn').removeClass('hidden');
            const pausedMsg = cfg.t.translation_paused_by_user_4a244ebb;
            logProgress(pausedMsg, 'info');
        });

        // Resume translation
        jQuery('#auto-translate-resume-btn').on('click', function() {
            translationState.isPaused = false;
            jQuery('#auto-translate-pause-btn').removeClass('hidden');
            jQuery('#auto-translate-resume-btn').addClass('hidden');
            const resumedMsg = cfg.t.translation_resumed_by_user_50ed58fa;
            logProgress(resumedMsg, 'info');
        });

        // Stop translation
        jQuery('#auto-translate-stop-btn').on('click', function() {
            const stopConfirmMsg = cfg.t.are_you_sure_you_want_to_stop_the_transl_6b93c4d9;
            const doStop = () => {
                translationState.shouldStop = true;
                translationState.isRunning = false;
                translationState.isPaused = false;
                const stoppedMsg = cfg.t.translation_stopped_by_user_672425ee;
                logProgress(stoppedMsg, 'info');
            };
            if (window.showConfirmation) {
                window.showConfirmation(stopConfirmMsg, doStop, null, cfg.t.stop_11a755d5, cfg.t.cancel_ea478870, cfg.t.stop_translation_e1c12d0c);
            } else {
                doStop();
            }
        });

        // Close after completion
        jQuery('#auto-translate-close-btn').on('click', function() {
            jQuery('#auto-translate-mini-banner').hide();
            jQuery('#auto-translate-modal').addClass('hidden');
            resetTranslationState();
            // Reload the page to show updated translations
            window.location.reload();
        });

        // Minimize / restore buttons
        jQuery('#minimize-auto-translate-modal-btn').on('click', minimizeModal);
        jQuery('#restore-auto-translate-modal-btn').on('click', restoreModal);

        // ── Drag-to-move ─────────────────────────────────────────────────────
        (function setupDrag() {
            const panel  = document.getElementById('auto-translate-modal-panel');
            const header = document.getElementById('auto-translate-modal-header');
            if (!panel || !header) return;

            let isDragging = false;
            let originX = 0, originY = 0;
            let tx = 0, ty = 0;

            // Expose a reset so the open-button handler can re-centre for a fresh open.
            if (window.autoTranslateModal) {
                window.autoTranslateModal._resetDragPosition = function () {
                    tx = 0; ty = 0;
                    panel.style.transform = '';
                };
            }

            header.addEventListener('mousedown', function (e) {
                // Don't start drag when clicking an interactive element
                if (e.target.closest('button, input, select, a')) return;
                isDragging = true;
                originX = e.clientX - tx;
                originY = e.clientY - ty;
                panel.style.transition = 'none';       // disable animation while dragging
                header.style.cursor = 'grabbing';
                e.preventDefault();
            });

            document.addEventListener('mousemove', function (e) {
                if (!isDragging) return;
                tx = e.clientX - originX;
                ty = e.clientY - originY;
                panel.style.transform = 'translate(' + tx + 'px, ' + ty + 'px)';
            });

            document.addEventListener('mouseup', function () {
                if (!isDragging) return;
                isDragging = false;
                header.style.cursor = 'grab';
                panel.style.transition = '';            // restore animation
            });
        })();

        // ── Navigation guard while translation is running ────────────────────
        // NOTE: for true browser refresh / tab-close (F5, Ctrl-R, × button)
        // the browser MANDATES its own native dialog — custom HTML cannot replace it.
        // For in-app link clicks we intercept early and show the app's custom dialog.
        (function setupNavigationGuard() {
            const leaveLabel  = cfg.t.leave_page_ba532946;
            const stayLabel   = cfg.t.stay_89302eb6;
            const titleLabel  = cfg.t.leave_page_c5eba0f4;
            const warnMsg     = cfg.t.translation_is_running_navigating_away_w_6f6b3a4a;
            const refreshMsg  = cfg.t.translation_is_in_progress_leaving_will__5fb22684;

            // 1) Native guard for refresh / close / URL-bar navigation
            window.addEventListener('beforeunload', function (e) {
                const state = (window.autoTranslateModal && window.autoTranslateModal.translationState) || translationState;
                if (!state.isRunning) return;
                e.preventDefault();
                // Chrome requires returnValue to be set (ignores the string, shows generic message)
                e.returnValue = refreshMsg;
                return refreshMsg;
            });

            // 2) Custom dialog for in-app anchor clicks (sidebar, header nav, breadcrumbs…)
            document.addEventListener('click', function (e) {
                const state = (window.autoTranslateModal && window.autoTranslateModal.translationState) || translationState;
                if (!state.isRunning) return;

                const anchor = e.target.closest('a[href]');
                if (!anchor) return;

                const href = anchor.getAttribute('href') || '';
                // Skip fragment-only, javascript:, and _blank (new tab) links
                if (!href || href === '#' || href.startsWith('#') ||
                    href.startsWith('javascript:') || anchor.target === '_blank') return;

                e.preventDefault();
                e.stopImmediatePropagation();

                if (window.showConfirmation) {
                    window.showConfirmation(warnMsg, function () {
                        state.shouldStop = true;
                        state.isRunning  = false;
                        window.location.href = anchor.href;   // follow the original link
                    }, null, leaveLabel, stayLabel, titleLabel);
                } else {
                    // Fallback if custom confirmation is unavailable
                    if (window.confirm(warnMsg)) {
                        state.shouldStop = true;
                        state.isRunning  = false;
                        window.location.href = anchor.href;
                    }
                }
            }, true /* capture phase — runs before other handlers */);
        })();
    }

    // Initialize when DOM is ready and jQuery is available
    function waitForjQueryAndInitialize() {
        if (typeof jQuery === 'undefined') {
            setTimeout(waitForjQueryAndInitialize, 50);
            return;
        }
        jQuery(document).ready(function() {
            initializeAutoTranslateModal();
        });
    }

    // Start checking for jQuery when DOM is ready
    document.addEventListener('DOMContentLoaded', function() {
        waitForjQueryAndInitialize();
    });
})();
