/* Auto-generated from manage_translations.html — DO NOT edit template inline JS */
/* Config is bootstrapped via window.manageTranslationsConfig in the template */

(function () {
    'use strict';
    var cfg = window.manageTranslationsConfig || {};

    // --- Export and utility logic ---
        (function() {
            const openBtn = document.getElementById('translations-io-btn');
            const modal = document.getElementById('translations-io-modal');
            const closeBtn = modal ? modal.querySelector('.close-translations-io-modal') : null;

            function openModal() {
                if (!modal) return;
                modal.classList.remove('hidden');
            }
            function closeModal() {
                if (!modal) return;
                modal.classList.add('hidden');
            }

            if (openBtn) openBtn.addEventListener('click', openModal);
            if (closeBtn) closeBtn.addEventListener('click', closeModal);
            if (modal) {
                modal.addEventListener('click', function(e) {
                    if (e.target === modal) closeModal();
                });
            }
            document.addEventListener('keydown', function(e) {
                if (e.key === 'Escape') closeModal();
            });

            // Tab switching
            const tabExport = document.getElementById('tab-export');
            const tabImport = document.getElementById('tab-import');
            const tabContentExport = document.getElementById('tab-content-export');
            const tabContentImport = document.getElementById('tab-content-import');

            function switchTab(tabName) {
                if (tabName === 'export') {
                    // Activate Export tab
                    tabExport.classList.add('active', 'border-blue-500', 'text-blue-600');
                    tabExport.classList.remove('border-transparent', 'text-gray-500', 'hover:text-gray-700', 'hover:border-gray-300');
                    tabImport.classList.remove('active', 'border-blue-500', 'text-blue-600');
                    tabImport.classList.add('border-transparent', 'text-gray-500', 'hover:text-gray-700', 'hover:border-gray-300');
                    tabContentExport.classList.remove('hidden');
                    tabContentImport.classList.add('hidden');
                } else if (tabName === 'import') {
                    // Activate Import tab
                    tabImport.classList.add('active', 'border-blue-500', 'text-blue-600');
                    tabImport.classList.remove('border-transparent', 'text-gray-500', 'hover:text-gray-700', 'hover:border-gray-300');
                    tabExport.classList.remove('active', 'border-blue-500', 'text-blue-600');
                    tabExport.classList.add('border-transparent', 'text-gray-500', 'hover:text-gray-700', 'hover:border-gray-300');
                    tabContentImport.classList.remove('hidden');
                    tabContentExport.classList.add('hidden');
                }
            }

            if (tabExport) tabExport.addEventListener('click', () => switchTab('export'));
            if (tabImport) tabImport.addEventListener('click', () => switchTab('import'));

            // Export PO link sync
            const exportPoLang = document.getElementById('export-po-lang');
            const exportPoLink = document.getElementById('export-po-link');
            const exportPoBase = cfg.urls.exportPo;
            function syncExportPoLink() {
                if (!exportPoLang || !exportPoLink) return;
                const lang = exportPoLang.value || 'en';
                exportPoLink.href = exportPoBase + "?format=po&lang=" + encodeURIComponent(lang);
            }
            if (exportPoLang) exportPoLang.addEventListener('change', syncExportPoLink);
            syncExportPoLink();

            // Import UI behavior - Safety toggles for Excel form
            const excelOnlyNonEmpty = document.getElementById('translations-excel-only-non-empty');
            const excelAllowClear = document.getElementById('translations-excel-allow-clear');

            function syncExcelSafetyToggles() {
                if (!excelOnlyNonEmpty || !excelAllowClear) return;
                if (excelOnlyNonEmpty.checked) {
                    excelAllowClear.checked = false;
                    excelAllowClear.disabled = true;
                    if (excelAllowClear.parentElement) excelAllowClear.parentElement.classList.add('opacity-60');
                } else {
                    excelAllowClear.disabled = false;
                    if (excelAllowClear.parentElement) excelAllowClear.parentElement.classList.remove('opacity-60');
                }
            }
            if (excelOnlyNonEmpty) excelOnlyNonEmpty.addEventListener('change', syncExcelSafetyToggles);
            syncExcelSafetyToggles();

            // Import UI behavior - Safety toggles for PO form
            const poOnlyNonEmpty = document.getElementById('translations-po-only-non-empty');
            const poAllowClear = document.getElementById('translations-po-allow-clear');

            function syncPoSafetyToggles() {
                if (!poOnlyNonEmpty || !poAllowClear) return;
                if (poOnlyNonEmpty.checked) {
                    poAllowClear.checked = false;
                    poAllowClear.disabled = true;
                    if (poAllowClear.parentElement) poAllowClear.parentElement.classList.add('opacity-60');
                } else {
                    poAllowClear.disabled = false;
                    if (poAllowClear.parentElement) poAllowClear.parentElement.classList.remove('opacity-60');
                }
            }
            if (poOnlyNonEmpty) poOnlyNonEmpty.addEventListener('change', syncPoSafetyToggles);
            syncPoSafetyToggles();

            // Import UI behavior - Safety toggles for PO ZIP form
            const pozipOnlyNonEmpty = document.getElementById('translations-pozip-only-non-empty');
            const pozipAllowClear = document.getElementById('translations-pozip-allow-clear');

            function syncPoZipSafetyToggles() {
                if (!pozipOnlyNonEmpty || !pozipAllowClear) return;
                if (pozipOnlyNonEmpty.checked) {
                    pozipAllowClear.checked = false;
                    pozipAllowClear.disabled = true;
                    if (pozipAllowClear.parentElement) pozipAllowClear.parentElement.classList.add('opacity-60');
                } else {
                    pozipAllowClear.disabled = false;
                    if (pozipAllowClear.parentElement) pozipAllowClear.parentElement.classList.remove('opacity-60');
                }
            }
            if (pozipOnlyNonEmpty) pozipOnlyNonEmpty.addEventListener('change', syncPoZipSafetyToggles);
            syncPoZipSafetyToggles();

            // PO Import sub-tabs (Single / ZIP)
            const poTabSingle = document.getElementById('po-import-tab-single');
            const poTabZip = document.getElementById('po-import-tab-zip');
            const poPanelSingle = document.getElementById('po-import-panel-single');
            const poPanelZip = document.getElementById('po-import-panel-zip');

            function switchPoImportTab(which) {
                if (!poTabSingle || !poTabZip || !poPanelSingle || !poPanelZip) return;
                const isSingle = which === 'single';

                poTabSingle.classList.toggle('active', isSingle);
                poTabZip.classList.toggle('active', !isSingle);

                // Keep Tailwind classes in sync
                if (isSingle) {
                    poTabSingle.classList.add('border-blue-500', 'text-blue-600');
                    poTabSingle.classList.remove('border-transparent', 'text-gray-500', 'hover:text-gray-700', 'hover:border-gray-300');
                    poTabZip.classList.add('border-transparent', 'text-gray-500', 'hover:text-gray-700', 'hover:border-gray-300');
                    poTabZip.classList.remove('border-blue-500', 'text-blue-600');
                } else {
                    poTabZip.classList.add('border-blue-500', 'text-blue-600');
                    poTabZip.classList.remove('border-transparent', 'text-gray-500', 'hover:text-gray-700', 'hover:border-gray-300');
                    poTabSingle.classList.add('border-transparent', 'text-gray-500', 'hover:text-gray-700', 'hover:border-gray-300');
                    poTabSingle.classList.remove('border-blue-500', 'text-blue-600');
                }

                poPanelSingle.classList.toggle('hidden', !isSingle);
                poPanelZip.classList.toggle('hidden', isSingle);
            }

            if (poTabSingle) poTabSingle.addEventListener('click', () => switchPoImportTab('single'));
            if (poTabZip) poTabZip.addEventListener('click', () => switchPoImportTab('zip'));
            switchPoImportTab('single');
        })();

    // --- Translations grid ---
    // AG Grid helper instance
    let gridHelper = null;
    let gridApi = null;
    let showRemovedOnly = false;

    function applyRemovedFilter() {
        if (!gridApi) return;
        if (typeof gridApi.onFilterChanged === 'function') {
            gridApi.onFilterChanged();
        } else if (typeof gridApi.refreshClientSideRowModel === 'function') {
            gridApi.refreshClientSideRowModel('filter');
        }
    }

    // Transform translations data for ag-grid.
    // Obsolete (removed) entries carry a source prefixed with \x00 so the renderer
    // can style them differently without a separate column.
    const REMOVED_PREFIX = '\x00';
        const translationsData = (function() {
            var el = document.getElementById('translations-grid-data');
            if (!el) return [];
            try { return JSON.parse(el.textContent || '[]'); } catch(e) { return []; }
        })();

    // Column definitions for ag-grid - dynamically generated
    const columnDefs = [
        {
            field: 'source',
            headerName: cfg.t.sourceCol,
            width: 200,
            minWidth: 150,
            maxWidth: 300,
            filter: 'agTextColumnFilter',
            sortable: true,
            wrapText: true,
            cellRenderer: function(params) {
                const removed = params.data && params.data.removed;
                // Strip the internal \x00 prefix used to mark removed entries
                const raw = (params.value || '').replace(/^\x00/, '');
                const isUnknown = !raw || raw === cfg.t.unknown;
                let display = raw.replace(/</g, '&lt;').replace(/>/g, '&gt;');

                if (removed) {
                    const sourceLabel = isUnknown ? '' : display;
                    const removedBadge = '<span style="display:inline-flex;align-items:center;padding:1px 6px;border-radius:3px;font-size:11px;font-weight:600;background:#fee2e2;color:#991b1b;margin-right:4px;" title="' + cfg.t.removedFromSource + '"><i class="fas fa-trash-alt" style="margin-right:3px;font-size:10px;"></i>' + cfg.t.removed + '</span>';
                    return '<div style="line-height:1.4">' + removedBadge + (sourceLabel ? '<span style="color:#6b7280;font-size:12px;">' + sourceLabel + '</span>' : '') + '</div>';
                }

                const hasPlaceholders = /%\([^)]+\)[sd]|%(?:[sd]|\.\d+[fd])/.test(raw);
                if (hasPlaceholders) {
                    display = '<span class="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-800 mr-1" title="' + cfg.t.containsPlaceholders + '"><i class="fas fa-code mr-1"></i>' + display + '</span>';
                }
                return '<div title="' + raw.replace(/"/g, '&quot;') + '">' + display + '</div>';
            },
            cellStyle: function(params) {
                const baseStyle = { 'white-space': 'normal', 'word-wrap': 'break-word', 'line-height': '1.4' };
                if (params.data && params.data.removed) {
                    baseStyle['background-color'] = '#fff7f7';
                }
                return baseStyle;
            },
            valueGetter: function(params) {
                // Strip internal prefix for filtering/sorting so users search by page name
                const v = (params.data && params.data.source) || '';
                return v.replace(/^\x00/, '');
            }
        },
        {
            field: 'msgid',
            headerName: cfg.t.msgIdCol,
            width: 250,
            minWidth: 200,
            maxWidth: 400,
            filter: 'agTextColumnFilter',
            sortable: true,
            wrapText: true,
            cellRenderer: function(params) {
                const value = params.value || '';
                const removed = params.data && params.data.removed;
                const hasPlaceholders = /%\([^)]+\)[sd]|%(?:[sd]|\.\d+[fd])/.test(value);
                let display = value.replace(/</g, '&lt;').replace(/>/g, '&gt;');
                if (hasPlaceholders) {
                    display = '<span class="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-800 mr-1" title="' + cfg.t.containsPlaceholders + '"><i class="fas fa-code mr-1"></i>' + display + '</span>';
                }
                const style = removed ? ' style="text-decoration:line-through;color:#9ca3af;"' : '';
                return '<div' + style + ' title="' + value.replace(/"/g, '&quot;') + '">' + display + '</div>';
            },
            cellStyle: function(params) {
                const baseStyle = { 'white-space': 'normal', 'word-wrap': 'break-word', 'line-height': '1.4' };
                const value = params.value || '';
                const removed = params.data && params.data.removed;
                const hasPlaceholders = /%\([^)]+\)[sd]|%(?:[sd]|\.\d+[fd])/.test(value);
                if (hasPlaceholders && !removed) {
                    baseStyle['background-color'] = '#fef3c7'; // yellow-100
                }
                if (removed) {
                    baseStyle['background-color'] = '#fff7f7';
                }
                return baseStyle;
            }
        }
    ].concat((cfg.languages || []).map(function(code) {
        var langName = (cfg.languageNames && cfg.languageNames[code]) || (cfg.allLanguageNames && cfg.allLanguageNames[code]) || code.toUpperCase();
        return {
            field: code,
            headerName: langName,
            width: 250,
            minWidth: 200,
            maxWidth: 400,
            filter: 'agTextColumnFilter',
            sortable: true,
            wrapText: true,
            cellRenderer: function(params) {
                const value = params.value || '';
                const hasPlaceholders = /%\([^)]+\)[sd]|%(?:[sd]|\.\d+[fd])/.test(value);
                let display = value.replace(/</g, '&lt;').replace(/>/g, '&gt;');
                if (hasPlaceholders) {
                    display = '<span class="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-800 mr-1" title="' + cfg.t.containsPlaceholders + '"><i class="fas fa-code mr-1"></i>' + display + '</span>';
                }
                return '<div title="' + value.replace(/"/g, '&quot;') + '">' + display + '</div>';
            },
            cellStyle: function(params) {
                const baseStyle = { 'white-space': 'normal', 'word-wrap': 'break-word', 'line-height': '1.4' };
                if (params.data && params.data.removed) {
                    baseStyle['background-color'] = '#fff7f7';
                    baseStyle['color'] = '#9ca3af';
                }
                return baseStyle;
            }
        };
    }))
    .concat([{
        field: 'actions',
        headerName: cfg.t.actionsCol,
        width: 130,
        minWidth: 100,
        maxWidth: 160,
        lockVisible: true,
        pinned: 'right',
        lockPinned: true,
        suppressMovable: true,
        sortable: false,
        filter: false,
        cellRenderer: function(params) {
            const msgid = params.data.msgid || '';
            const encodedMsgid = encodeURIComponent(msgid);
            const removed = params.data && params.data.removed;
            const editBtn = '<button type="button" class="text-blue-600 hover:text-blue-900 edit-translation-btn" data-msgid="' + encodedMsgid + '" title="' + cfg.t.editAllTranslations + '"><i class="fas fa-pen"></i></button>';
            const delBtn = removed
                ? '<button type="button" class="text-red-600 hover:text-red-900 transition-colors delete-removed-translation-btn" data-msgid="' + encodedMsgid + '" title="' + cfg.t.permanentlyDelete + '"><i class="fas fa-trash fa-fw"></i></button>'
                : '';
            return '<div class="flex items-center gap-1 flex-nowrap">' + editBtn + delBtn + '</div>';
        }
    }]);

    // Initialize grid using helper
    function initializeGrid() {
        var desiredOrder = ['source', 'msgid']
            .concat(cfg.languages || [])
            .concat(['actions']);

        var result = AgGridHelper.create('translationsGrid', 'translations', columnDefs, translationsData, {
            gridOptions: {
                isExternalFilterPresent: function() {
                    return showRemovedOnly;
                },
                doesExternalFilterPass: function(node) {
                    return !!(node.data && node.data.removed);
                }
            },
            onReady: function(api, helper) {
                AgGridHelper.pinActionsColumn(api, desiredOrder, helper && helper.columnVisibilityManager);
            }
        });
        gridHelper = result.helper;
        gridApi = result.api;
        window.gridApi = gridApi;
        window.gridHelper = gridHelper;
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeGrid);
    } else {
        initializeGrid();
    }

    // Removed-strings notice: filter grid or bulk-delete obsolete entries
    document.addEventListener('DOMContentLoaded', function() {
        var showBtn = document.getElementById('show-removed-translations-btn');
        var removeAllBtn = document.getElementById('remove-all-removed-translations-btn');

        if (showBtn) {
            showBtn.addEventListener('click', function() {
                var active = showBtn.getAttribute('data-active') === '1';
                var next = !active;
                showBtn.setAttribute('data-active', next ? '1' : '0');
                showBtn.innerHTML = next
                    ? '<i class="fas fa-list"></i> ' + cfg.t.showAll
                    : '<i class="fas fa-filter"></i> ' + cfg.t.showRemoved;
                showRemovedOnly = next;
                applyRemovedFilter();
            });
        }

        function performDeleteAllRemovedTranslations() {
            var csrfMeta = document.querySelector('meta[name=csrf-token]');
            var csrfToken = csrfMeta ? csrfMeta.getAttribute('content') : '';
            var fetchFn = (window.getFetch && window.getFetch()) || fetch;
            fetchFn(cfg.urls.deleteAllRemovedTranslations, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({ csrf_token: csrfToken })
            })
            .then(function(response) { return response.json().then(function(data) { return { ok: response.ok, data: data }; }); })
            .then(function(result) {
                if (result.ok && result.data && result.data.success) {
                    if (window.showAlert) window.showAlert(result.data.message || cfg.t.removedObsolete, 'success');
                    window.location.reload();
                    return;
                }
                var errMsg = (result.data && (result.data.message || result.data.error))
                    ? (result.data.message || result.data.error)
                    : cfg.t.deleteFailed;
                throw new Error(errMsg);
            })
            .catch(function(error) {
                console.error('delete-all-removed translations:', error);
                if (window.showAlert) window.showAlert(error.message || cfg.t.deleteFailed, 'error');
            });
        }

        if (removeAllBtn) {
            removeAllBtn.addEventListener('click', function() {
                var confirmMsg = cfg.t.deleteAllRemovedConfirm;
                var confirmTitle = cfg.t.deleteAllRemovedTitle;
                var doDelete = function() { performDeleteAllRemovedTranslations(); };
                if (window.showDangerConfirmation) {
                    window.showDangerConfirmation(confirmMsg, doDelete, null, cfg.t.removeAll, cfg.t.cancel, confirmTitle);
                } else if (window.showConfirmation) {
                    window.showConfirmation(confirmMsg, doDelete, null, cfg.t.removeAll, cfg.t.cancel, confirmTitle);
                } else if (window.confirm(confirmMsg)) {
                    doDelete();
                }
            });
        }
    });

    // Build & Apply dropdown toggle
    document.addEventListener('DOMContentLoaded', function() {
        const dropdownBtn = document.getElementById('build-apply-btn');
        const dropdownMenu = document.getElementById('build-apply-menu');
        if (dropdownBtn && dropdownMenu) {
            dropdownBtn.addEventListener('click', function(e) {
                e.stopPropagation();
                const isOpen = !dropdownMenu.classList.contains('hidden');
                dropdownMenu.classList.toggle('hidden', isOpen);
                dropdownBtn.setAttribute('aria-expanded', String(!isOpen));
            });
            document.addEventListener('click', function() {
                dropdownMenu.classList.add('hidden');
                dropdownBtn.setAttribute('aria-expanded', 'false');
            });
            dropdownMenu.addEventListener('click', function(e) {
                e.stopPropagation();
            });
        }
    });

    // Compile Translations with Confirmation
    document.addEventListener('DOMContentLoaded', function() {
        const compileBtn = document.getElementById('compile-translations-btn');
        if (compileBtn) {
            compileBtn.addEventListener('click', function(e) {
                e.preventDefault();

                const msg = cfg.t.compileWarning;
                function doCompile() {
                    // Show loading state
                    const originalText = compileBtn.innerHTML;
                    compileBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>' + cfg.t.compilingText;
                    compileBtn.disabled = true;

                    // Create and submit form
                    const form = document.createElement('form');
                    form.method = 'POST';
                    form.action = cfg.urls.compilePo;

                    // Add CSRF token
                    const csrfToken = document.querySelector('meta[name=csrf-token]');
                    if (csrfToken) {
                        const csrfInput = document.createElement('input');
                        csrfInput.type = 'hidden';
                        csrfInput.name = 'csrf_token';
                        csrfInput.value = csrfToken.getAttribute('content');
                        form.appendChild(csrfInput);
                    }

                    // Add restart parameter
                    const restartInput = document.createElement('input');
                    restartInput.type = 'hidden';
                    restartInput.name = 'restart';
                    restartInput.value = '1';
                    form.appendChild(restartInput);

                    document.body.appendChild(form);
                    form.submit();
                }
                if (window.showConfirmation) {
                    window.showConfirmation(msg, doCompile, null, cfg.t.continueBtn, cfg.t.cancel, cfg.t.compileTitle);
                } else {
                    doCompile();
                }
            });
        }
    });

    // Translation-specific auto-translate implementation
    // Wait for AG Grid to be initialized
    function waitForGridApi() {
        if (!window.gridApi) {
            setTimeout(waitForGridApi, 50);
            return;
        }
        initializeAutoTranslate();
    }

    // Start checking for grid API when DOM is ready
    document.addEventListener('DOMContentLoaded', function() {
        waitForGridApi();
    });

    // Also try to initialize when the page loads (in case DOMContentLoaded already fired)
    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        setTimeout(waitForGridApi, 100);
    }


    // Helper to lazily read the server-provided mapping of locale -> translation key
    function getTranslationLangMap() {
        if (!window.translationLangMap) {
            const mapEl = document.getElementById('translation-lang-map-json');
            const pairs = mapEl ? JSON.parse(mapEl.textContent) : [];
            window.translationLangMap = Object.fromEntries(pairs);
        }
        return window.translationLangMap;
    }

    function initializeAutoTranslate() {
        // Helper function to check if a string is PO file metadata
        function isMetadataString(str) {
            if (typeof str !== 'string') return false;
            const strLower = str.toLowerCase();
            const metadataKeys = [
                'project-id-version', 'report-msgid-bugs-to', 'pot-creation-date',
                'po-revision-date', 'last-translator', 'language-team', 'mime-version',
                'content-type', 'content-transfer-encoding', 'plural-forms', 'generated-by'
            ];
            // Check if string contains 3+ metadata keys (indicates it's the header block)
            const metadataKeyCount = metadataKeys.filter(key => strLower.includes(key)).length;
            return metadataKeyCount >= 3;
        }

        // Helper function to filter out metadata strings from an array or set
        function filterMetadata(collection) {
            if (Array.isArray(collection)) {
                return collection.filter(item => !isMetadataString(item));
            } else if (collection instanceof Set) {
                const filtered = new Set();
                collection.forEach(item => {
                    if (!isMetadataString(item)) {
                        filtered.add(item);
                    }
                });
                return filtered;
            }
            return collection;
        }

        // Function to get translation counts for the modal
        window.getPageSpecificTranslationCounts = function(overwriteExisting = false, selectedMsgids = null) {
            // Get selected rows from ag-grid if any
            // Only includes rows that are currently displayed (visible after filtering)
            let actualSelectedMsgids = selectedMsgids;
            if (!actualSelectedMsgids && window.gridHelper && typeof window.gridHelper.getSelectedRows === 'function') {
                const selectedRows = window.gridHelper.getSelectedRows();
                if (selectedRows && selectedRows.length > 0) {
                    const msgids = selectedRows.map(row => row.msgid).filter(msgid => msgid);
                    actualSelectedMsgids = new Set(filterMetadata(msgids));
                }
            } else if (!actualSelectedMsgids && window.gridApi) {
                // Fallback: filter selected nodes to only include displayed ones
                let selectedRows = [];
                if (typeof window.gridApi.getSelectedNodes === 'function') {
                    const nodes = window.gridApi.getSelectedNodes() || [];
                    selectedRows = nodes
                        .filter(function(node) {
                            return node && (node.displayed === true || node.displayed === undefined);
                        })
                        .map(function(node) { return node ? node.data : null; })
                        .filter(function(row) { return row !== null && row !== undefined; });
                } else if (typeof window.gridApi.getSelectedRows === 'function') {
                    selectedRows = window.gridApi.getSelectedRows();
                }
                if (selectedRows && selectedRows.length > 0) {
                    const msgids = selectedRows.map(row => row.msgid).filter(msgid => msgid);
                    actualSelectedMsgids = new Set(filterMetadata(msgids));
                }
            }

            // Filter out metadata from actualSelectedMsgids if it exists
            if (actualSelectedMsgids) {
                actualSelectedMsgids = filterMetadata(actualSelectedMsgids);
            }

            // Use server-side calculated counts for more reliability
            const etcEl = document.getElementById('empty-translation-counts-json');
            const serverCounts = etcEl ? JSON.parse(etcEl.textContent) : {};

            // Get all msgids count if overwrite is enabled
            const allMsgidsEl = document.getElementById('all-translation-msgids-json');
            let allMsgids = allMsgidsEl ? JSON.parse(allMsgidsEl.textContent) : [];
            // Filter out any metadata strings that might have slipped through
            allMsgids = filterMetadata(allMsgids);
            const totalMsgidsCount = allMsgids.length;

            // Get empty translation msgids for filtering
            const etmEl = document.getElementById('empty-translation-msgids-json');
            const emptyTranslationMsgidsRaw = etmEl ? JSON.parse(etmEl.textContent) : {};
            // Filter metadata from empty translation msgids
            const emptyTranslationMsgids = {};
            Object.keys(emptyTranslationMsgidsRaw).forEach(locale => {
                emptyTranslationMsgids[locale] = filterMetadata(emptyTranslationMsgidsRaw[locale] || []);
            });

            // Build counts object dynamically based on enabled languages with mapping to translation keys
            const counts = {};
            const langMap = getTranslationLangMap(); // locale -> key
            Object.entries(langMap).forEach(([locale, key]) => {
                // Skip if locale or key is a metadata string
                if (isMetadataString(locale) || isMetadataString(key)) {
                    counts[key] = 0;
                    return;
                }

                let count = 0;

                if (overwriteExisting) {
                    // If overwriting, count all msgids (or selected ones if any)
                    if (actualSelectedMsgids && actualSelectedMsgids.size > 0) {
                        count = actualSelectedMsgids.size;
                    } else {
                        // Ensure totalMsgidsCount is a number
                        count = typeof totalMsgidsCount === 'number' ? totalMsgidsCount : (parseInt(totalMsgidsCount) || 0);
                    }
                } else {
                    // Count empty translations (or selected empty ones if any)
                    const emptyMsgids = emptyTranslationMsgids[locale] || [];
                    if (actualSelectedMsgids && actualSelectedMsgids.size > 0) {
                        // Count only empty msgids that are in the selection (and not metadata)
                        count = emptyMsgids.filter(msgid =>
                            !isMetadataString(msgid) && actualSelectedMsgids.has(msgid)
                        ).length;
                    } else {
                        // Ensure serverCounts[locale] is a number
                        const serverCount = serverCounts[locale];
                        if (isMetadataString(serverCount)) {
                            count = 0;
                        } else {
                            count = typeof serverCount === 'number' ? serverCount : (parseInt(serverCount) || 0);
                        }
                    }
                }

                // Ensure count is always a number (defensive programming)
                const finalCount = typeof count === 'number' ? count : (parseInt(count) || 0);
                if (isNaN(finalCount) || finalCount < 0) {
                    counts[key] = 0;
                } else {
                    counts[key] = finalCount;
                }
            });

            return counts;
        };

        // Fallback method: Count translations by inspecting AG Grid data
        function getPageSpecificTranslationCountsFromGrid() {
            // Build counts object dynamically based on enabled languages
            const gridCounts = {};
            const languageKeys = Object.values(getTranslationLangMap());
            languageKeys.forEach((key) => { gridCounts[key] = 0; });

            try {
                if (!window.gridApi) {
                    console.error('Grid API not available');
                    return gridCounts;
                }

                // Get all row data from ag-grid
                const rowData = [];
                window.gridApi.forEachNode(function(node) {
                    if (node.data) {
                        rowData.push(node.data);
                    }
                });

                // Process each row
                rowData.forEach(function(row) {
                    if (!row.msgid) return;
                    if (row.removed) return;

                    // Check each language column
                    languageKeys.forEach(function(lang) {
                        const translation = row[lang] || '';
                        const hasTranslation = translation &&
                                              translation !== '' &&
                                              translation !== '-' &&
                                              translation !== 'undefined' &&
                                              translation !== 'null';

                        if (!hasTranslation) {
                            gridCounts[lang]++;
                        }
                    });
                });

            } catch (error) {
                console.error('Error in grid inspection method:', error);
            }

            return gridCounts;
        }

        // Override the generic translation function with translation-specific logic
        window.performPageSpecificTranslation = function(selectedLanguages, selectedService) {
            const translationsToTranslate = [];

            // Check if overwrite existing translations is enabled
            const overwriteExisting = jQuery('#overwrite-existing-translations').is(':checked');

            // Helper function to check if a string is PO file metadata (local to this function)
            function isMetadataStringLocal(str) {
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

            // Get selected rows from ag-grid if any
            // Only includes rows that are currently displayed (visible after filtering)
            let selectedMsgids = null;
            if (window.gridHelper && typeof window.gridHelper.getSelectedRows === 'function') {
                const selectedRows = window.gridHelper.getSelectedRows();
                if (selectedRows && selectedRows.length > 0) {
                    const msgids = selectedRows.map(row => row.msgid).filter(msgid => msgid && !isMetadataStringLocal(msgid));
                    selectedMsgids = new Set(msgids);
                }
            } else if (window.gridApi) {
                // Fallback: filter selected nodes to only include displayed ones
                let selectedRows = [];
                if (typeof window.gridApi.getSelectedNodes === 'function') {
                    const nodes = window.gridApi.getSelectedNodes() || [];
                    selectedRows = nodes
                        .filter(function(node) {
                            return node && (node.displayed === true || node.displayed === undefined);
                        })
                        .map(function(node) { return node ? node.data : null; })
                        .filter(function(row) { return row !== null && row !== undefined; });
                } else if (typeof window.gridApi.getSelectedRows === 'function') {
                    selectedRows = window.gridApi.getSelectedRows();
                }
                if (selectedRows && selectedRows.length > 0) {
                    const msgids = selectedRows.map(row => row.msgid).filter(msgid => msgid && !isMetadataStringLocal(msgid));
                    selectedMsgids = new Set(msgids);
                }
            }

            // Use server-side data for message IDs that need translation
            const etmEl = document.getElementById('empty-translation-msgids-json');
            const emptyTranslationMsgidsRaw = etmEl ? JSON.parse(etmEl.textContent) : {};
            // Filter metadata from empty translation msgids
            const emptyTranslationMsgids = {};
            Object.keys(emptyTranslationMsgidsRaw).forEach(locale => {
                emptyTranslationMsgids[locale] = (emptyTranslationMsgidsRaw[locale] || []).filter(msgid => !isMetadataStringLocal(msgid));
            });

            // Get all msgids if overwrite is enabled
            const allMsgidsEl = document.getElementById('all-translation-msgids-json');
            let allMsgids = allMsgidsEl ? JSON.parse(allMsgidsEl.textContent) : [];
            // Filter out any metadata strings that might have slipped through
            // Use the same filterMetadata function from getPageSpecificTranslationCounts scope
            allMsgids = allMsgids.filter(function(msgid) {
                if (typeof msgid !== 'string') return true;
                const strLower = msgid.toLowerCase();
                const metadataKeys = [
                    'project-id-version', 'report-msgid-bugs-to', 'pot-creation-date',
                    'po-revision-date', 'last-translator', 'language-team', 'mime-version',
                    'content-type', 'content-transfer-encoding', 'plural-forms', 'generated-by'
                ];
                const metadataKeyCount = metadataKeys.filter(key => strLower.includes(key)).length;
                return metadataKeyCount < 3; // Keep if less than 3 metadata keys (not a header block)
            });

            // First, get the actual counts to know which languages need translation
            const selectedCounts = window.getPageSpecificTranslationCounts(overwriteExisting, selectedMsgids);
            const languagesNeedingTranslation = overwriteExisting
                ? selectedLanguages  // If overwriting, translate all selected languages
                : selectedLanguages.filter(lang => selectedCounts[lang] > 0);

            // Derive mapping of language key -> locale from server-provided map
            const langToLocaleMap = Object.fromEntries(
                Object.entries(getTranslationLangMap()).map(([locale, key]) => [key, locale])
            );

            // Collect all translations that need translating using server-side data
            languagesNeedingTranslation.forEach(lang => {
                const localeCode = langToLocaleMap[lang];
                if (!localeCode) {
                    return;
                }

                // Use all msgids if overwrite is enabled, otherwise use only empty ones
                let msgidsForLang = overwriteExisting
                    ? allMsgids  // All msgids when overwriting (already filtered)
                    : (emptyTranslationMsgids[localeCode] || []);  // Only empty ones otherwise

                // Filter out any metadata strings that might have slipped through
                msgidsForLang = msgidsForLang.filter(msgid => !isMetadataStringLocal(msgid));

                // Filter to selected rows if any are selected
                if (selectedMsgids && selectedMsgids.size > 0) {
                    msgidsForLang = msgidsForLang.filter(msgid => selectedMsgids.has(msgid));
                }

                msgidsForLang.forEach(msgid => {
                    // Double-check it's not metadata before adding
                    if (!isMetadataStringLocal(msgid)) {
                        translationsToTranslate.push({
                            id: msgid,
                            text: msgid, // Use msgid as source text for translation
                            definition: '', // Translations don't have separate definitions
                            language: lang,
                            type: 'translation' // Use 'translation' type for the API
                        });
                    }
                });
            });

            if (translationsToTranslate.length === 0) {
                window.autoTranslateModal.logProgress(cfg.t.noFieldsNeedTranslation, 'info');
                window.autoTranslateModal.translationState.isRunning = false;
                jQuery('#auto-translate-pause-btn').addClass('hidden');
                jQuery('#auto-translate-resume-btn').addClass('hidden');
                jQuery('#auto-translate-stop-btn').addClass('hidden');
                jQuery('#auto-translate-close-btn').removeClass('hidden');
                return;
            }

            window.autoTranslateModal.translationState.totalItems = translationsToTranslate.length;
            window.autoTranslateModal.updateProgress();

            // Process translations one by one
            processNextTranslation(translationsToTranslate, 0, languagesNeedingTranslation, selectedService);
        };

        function processNextTranslation(translations, index, selectedLanguages, selectedService) {
            if (index >= translations.length || window.autoTranslateModal.translationState.shouldStop) {
                window.autoTranslateModal.translationState.isRunning = false;
                if (window.autoTranslateModal.translationState.shouldStop) {
                    window.autoTranslateModal.logProgress(cfg.t.translationStopped, 'info');
                } else {
                    window.autoTranslateModal.logProgress(cfg.t.translationCompleted, 'success');
                }
                jQuery('#auto-translate-pause-btn').addClass('hidden');
                jQuery('#auto-translate-resume-btn').addClass('hidden');
                jQuery('#auto-translate-stop-btn').addClass('hidden');
                jQuery('#auto-translate-close-btn').removeClass('hidden');
                if (window.autoTranslateModal.notifyCompletion) {
                    window.autoTranslateModal.notifyCompletion();
                }
                return;
            }

            // Check if translation is paused
            if (window.autoTranslateModal.translationState.isPaused) {
                // Wait a bit and check again
                setTimeout(() => processNextTranslation(translations, index, selectedLanguages, selectedService), 500);
                return;
            }

            const translation = translations[index];
            const service = selectedService || 'ifrc';

            // Call the translation API
            const translationPayload = {
                type: 'translation', // Use 'translation' type for translation API
                permission_context: (window.autoTranslateModal && window.autoTranslateModal.config && window.autoTranslateModal.config.permission_context) ? window.autoTranslateModal.config.permission_context : 'translations',
                permission_code: (window.autoTranslateModal && window.autoTranslateModal.config && window.autoTranslateModal.config.permission_code) ? window.autoTranslateModal.config.permission_code : 'admin.translations.manage',
                id: translation.id, // Message ID is required for translation type
                text: translation.text,
                definition: translation.definition,
                target_languages: [translation.language],
                translation_service: service
            };
            // Intentionally no payload debug logging here; can spam + may contain large strings.

            const translator = (window.AutoTranslateService && typeof window.AutoTranslateService.translate === 'function')
                ? window.AutoTranslateService
                : null;

            const reqPromise = translator
                // AutoTranslateService wraps payload (base64 JSON) to avoid WAF false positives on rich strings (HTML, --, etc.)
                ? translator.translate(translationPayload)
                : fetch(window.autoTranslateModal.config.endpoint, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest',
                        'X-CSRFToken': jQuery('meta[name=csrf-token]').attr('content')
                    },
                    body: JSON.stringify(translationPayload)
                }).then(r => r.json());

            Promise.resolve(reqPromise)
            .then(data => {
                window.autoTranslateModal.translationState.processedItems++;

                if (data.success && data.untranslated) {
                    // The service responded but returned the text unchanged — it is a proper
                    // noun or technical term that cannot be auto-translated. Count as skipped.
                    window.autoTranslateModal.translationState.skippedCount =
                        (window.autoTranslateModal.translationState.skippedCount || 0) + 1;
                    window.autoTranslateModal.logProgress(
                        `${cfg.t.skipped} ${translation.language} ${cfg.t.translationFor} ${translation.id} — ${cfg.t.properNounOrTech}`,
                        'warning'
                    );
                } else if (data.success && data.translations && data.updated_count > 0) {
                    // Update the grid cell with the new translation
                    if (window.gridApi && data.translations && data.translations.label_translations && data.translations.label_translations[translation.language]) {
                        window.gridApi.forEachNode(function(node) {
                            if (node.data && node.data.msgid === translation.id) {
                                // Get locale code for the language
                                const langToLocaleMap = Object.fromEntries(
                                    Object.entries(getTranslationLangMap()).map(([locale, key]) => [key, locale])
                                );
                                const localeCode = langToLocaleMap[translation.language];
                                if (localeCode) {
                                    node.setDataValue(localeCode, data.translations.label_translations[translation.language]);
                                }
                            }
                        });
                    }

                    window.autoTranslateModal.translationState.successCount++;
                    window.autoTranslateModal.logProgress(`${cfg.t.translated} ${translation.language} ${cfg.t.translationFor} ${translation.id}`, 'success');
                } else {
                    window.autoTranslateModal.translationState.errorCount++;
                    const unknownError = cfg.t.unknownError;
                    const errorMsg = `${cfg.t.failedToTranslate} ${translation.id} ${cfg.t.toText} ${translation.language}: ${data.message || unknownError}`;
                    window.autoTranslateModal.translationState.errors.push(errorMsg);
                    window.autoTranslateModal.logProgress(errorMsg, 'error');
                    console.error('Auto-translate: Translation failed:', data);
                }

                window.autoTranslateModal.updateProgress();
                // Skip scheduling the next iteration if stop was requested while this call was in-flight.
                if (!window.autoTranslateModal.translationState.shouldStop) {
                    setTimeout(() => processNextTranslation(translations, index + 1, selectedLanguages, selectedService), 100);
                } else {
                    processNextTranslation(translations, translations.length, selectedLanguages, selectedService);
                }
            })
            .catch(error => {
                window.autoTranslateModal.translationState.processedItems++;
                window.autoTranslateModal.translationState.errorCount++;
                const em = (error && error.message) ? String(error.message) : '';
                const looksLikeWaf = em.includes('403') || em.toLowerCase().includes('application-gateway') || em.toLowerCase().includes('waf');
                const prefix = looksLikeWaf
                    ? cfg.t.blockedByWaf
                    : cfg.t.networkError;
                const errorMsg = `${prefix} ${translation.id}: ${em || cfg.t.unknownError}`;
                window.autoTranslateModal.translationState.errors.push(errorMsg);
                window.autoTranslateModal.logProgress(errorMsg, 'error');
                window.autoTranslateModal.updateProgress();

                // Skip scheduling the next iteration if stop was requested while this call was in-flight.
                if (!window.autoTranslateModal.translationState.shouldStop) {
                    setTimeout(() => processNextTranslation(translations, index + 1, selectedLanguages, selectedService), 100);
                } else {
                    processNextTranslation(translations, translations.length, selectedLanguages, selectedService);
                }
            });
        }

        // Helper function to get language column index from header map
        function getLangColumnIndexFromHeaders(lang, headerMap) {
            // Map language names to display names in headers
            const langDisplayMap = {
                'fr': 'French',
                'es': 'Spanish',
                'ar': 'Arabic',
                'ru': 'Russian',
                'zh': 'Chinese',
                'hi': 'Hindi'
            };

            const displayName = langDisplayMap[lang.toLowerCase()] || lang;

            // Look for exact match first
            if (headerMap[displayName] !== undefined) {
                return headerMap[displayName];
            }

            // Look for partial match
            for (const [headerText, index] of Object.entries(headerMap)) {
                if (headerText.toLowerCase().includes(displayName.toLowerCase())) {
                    return index;
                }
            }

            return -1;
        }

        // Helper function to get the column index for a language
        function getLanguageColumnIndex(lang) {
            // Build language column map dynamically based on enabled languages
            const languageCodes = Object.values(getTranslationLangMap());

            const languageColumnMap = {};
            languageCodes.forEach((langCode, index) => {
                languageColumnMap[langCode] = 2 + index; // Column index starts at 2 (after Source and Message ID)
            });

            return languageColumnMap[lang] || -1;
        }
    }

    // --- Edit translation modal ---
    (function() {
        const modal = document.getElementById('edit-translation-modal');
        const closeBtns = document.querySelectorAll('.close-edit-translation-modal');
        const form = document.getElementById('edit-translation-form');
        const saveBtn = document.getElementById('edit-translation-save-btn');
        const saveBtnText = document.getElementById('edit-translation-save-btn-text');
        const languages = JSON.parse((document.getElementById('languages-json') || {}).textContent || '[]');
        const languageNames = JSON.parse((document.getElementById('language-names-json') || {}).textContent || '{}');
        const allLanguageNames = cfg.allLanguageNames || {};

        // Helper to get language display name
        function getLangDisplayName(code) {
            return languageNames[code] || allLanguageNames[code] || code.toUpperCase();
        }

        // Helper to check if language is RTL
        function isRTL(code) {
            return ['ar', 'fa', 'he', 'ur'].includes(code);
        }

        // Extract placeholders from a string
        function extractPlaceholders(str) {
            if (!str) return [];
            const placeholders = [];
            const namedMatches = str.match(/%\([^)]+\)[sd]/g) || [];
            placeholders.push(...namedMatches);
            const simpleMatches = str.match(/(?<!%\([^)]*)\%(?:[sd]|\.\d+[fd])/g) || [];
            placeholders.push(...simpleMatches);
            return [...new Set(placeholders)].sort();
        }

        // Validate placeholders
        function validatePlaceholders(sourceText, translationText) {
            const sourcePlaceholders = extractPlaceholders(sourceText);
            if (sourcePlaceholders.length === 0) return { valid: true };

            const translationPlaceholders = extractPlaceholders(translationText);
            const missing = sourcePlaceholders.filter(p => !translationPlaceholders.includes(p));

            if (missing.length > 0) {
                return {
                    valid: false,
                    message: cfg.t.missingPlaceholders + ': ' + missing.join(', ') + '. ' + cfg.t.allPlaceholdersMustBePreserved
                };
            }
            return { valid: true };
        }

        // Open modal and load translation data
        function openEditModal(msgid) {
            if (!msgid) return;

            // Set msgid in form
            document.getElementById('edit-translation-msgid').value = msgid;
            document.getElementById('edit-translation-msgid-display').value = msgid;

            // Check for placeholders
            const placeholders = extractPlaceholders(msgid);
            const warningDiv = document.getElementById('edit-translation-placeholder-warning');
            if (placeholders.length > 0) {
                warningDiv.classList.remove('hidden');
                document.getElementById('edit-translation-placeholder-text').textContent = msgid;
            } else {
                warningDiv.classList.add('hidden');
            }

            // Load translation data (base64 encode msgid to avoid WAF false positives on HTML/SQL-like gettext strings)
            var msgidB64 = btoa(unescape(encodeURIComponent(msgid)));
            fetch(cfg.urls.editTranslation + '?msgid_b64=' + encodeURIComponent(msgidB64), {
                method: 'GET',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
            .then(response => response.json())
            .then(data => {
                // Extract translations from JSON response
                const translations = (data && data.translations) || {};

                // Build translation fields
                const container = document.getElementById('edit-translation-fields-container');
                container.innerHTML = '';

                languages.forEach(langCode => {
                    const langBase = langCode.toLowerCase().split('_')[0];
                    const fieldId = 'msgstr_' + langBase;
                    const value = translations[langBase] || translations[langCode] || '';
                    const langDisplay = getLangDisplayName(langBase);
                    const rtl = isRTL(langBase);

                    const fieldDiv = document.createElement('div');

                    const label = document.createElement('label');
                    label.setAttribute('for', fieldId);
                    label.className = 'block text-sm font-medium text-gray-700 mb-2';
                    label.textContent = langDisplay + ' ' + cfg.t.translationLabel;

                    const textarea = document.createElement('textarea');
                    textarea.id = fieldId;
                    textarea.name = fieldId;
                    textarea.className = 'w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500';
                    textarea.rows = 4;
                    if (rtl) {
                        textarea.dir = 'rtl';
                        textarea.style.fontFamily = "'Tajawal', Arial, sans-serif";
                    }
                    textarea.value = value || '';

                    const errorDiv = document.createElement('div');
                    errorDiv.className = 'placeholder-error mt-1 text-xs text-red-600 hidden';

                    fieldDiv.appendChild(label);
                    fieldDiv.appendChild(textarea);
                    fieldDiv.appendChild(errorDiv);
                    container.appendChild(fieldDiv);
                });

                // Show modal
                modal.classList.remove('hidden');
            })
            .catch(error => {
                console.error('Error loading translation:', error);
                if (window.showAlert) window.showAlert(cfg.t.failedToLoadData, 'error');
                else console.error('Failed to load translation data');
            });
        }

        function setEditModalSaving(isSaving) {
            if (!saveBtn) return;
            saveBtn.disabled = isSaving;
            saveBtn.classList.toggle('btn-loading', isSaving);
            saveBtn.setAttribute('aria-busy', isSaving ? 'true' : 'false');
            if (saveBtnText) {
                if (isSaving) {
                    if (!saveBtnText.dataset.originalSaveLabel) {
                        saveBtnText.dataset.originalSaveLabel = saveBtnText.textContent;
                    }
                    saveBtnText.textContent = cfg.t.savingText;
                } else if (saveBtnText.dataset.originalSaveLabel) {
                    saveBtnText.textContent = saveBtnText.dataset.originalSaveLabel;
                    delete saveBtnText.dataset.originalSaveLabel;
                }
            }
            modal.setAttribute('aria-busy', isSaving ? 'true' : 'false');
            document.querySelectorAll('#edit-translation-modal .close-edit-translation-modal').forEach(function(b) {
                b.disabled = isSaving;
            });
            var autoB = document.getElementById('modal-auto-translate-btn');
            var clearB = document.getElementById('modal-clear-translations-btn');
            if (autoB) autoB.disabled = isSaving;
            if (clearB) clearB.disabled = isSaving;
        }

        // Close modal
        function closeEditModal() {
            if (modal.getAttribute('aria-busy') === 'true') return;
            modal.classList.add('hidden');
            form.reset();
            document.getElementById('edit-translation-fields-container').innerHTML = '';
        }

        function updateGridRowTranslations(msgid, payloadObj) {
            if (!window.gridApi || !msgid || !payloadObj) return;

            let updatedNode = null;
            window.gridApi.forEachNode(function(node) {
                if (updatedNode || !node.data || node.data.msgid !== msgid) return;

                (cfg.languages || languages || []).forEach(function(langCode) {
                    const langBase = String(langCode).toLowerCase().split('_')[0];
                    const fieldValue = payloadObj['msgstr_' + langCode] !== undefined
                        ? payloadObj['msgstr_' + langCode]
                        : payloadObj['msgstr_' + langBase];

                    if (fieldValue !== undefined) {
                        node.setDataValue(langCode, fieldValue || '');
                    }
                });
                updatedNode = node;
            });

            if (updatedNode && typeof window.gridApi.refreshCells === 'function') {
                window.gridApi.refreshCells({ rowNodes: [updatedNode], force: true });
            }
        }

        // Event listeners
        closeBtns.forEach(btn => {
            btn.addEventListener('click', closeEditModal);
        });

        modal.addEventListener('click', function(e) {
            if (e.target === modal && modal.getAttribute('aria-busy') !== 'true') closeEditModal();
        });

        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && !modal.classList.contains('hidden') && modal.getAttribute('aria-busy') !== 'true') {
                closeEditModal();
            }
        });

        // Handle edit button clicks (delegated event)
        document.addEventListener('click', function(e) {
            if (e.target.closest('.edit-translation-btn')) {
                e.preventDefault();
                const btn = e.target.closest('.edit-translation-btn');
                const msgid = decodeURIComponent(btn.getAttribute('data-msgid') || '');
                if (msgid) {
                    openEditModal(msgid);
                }
            }
        });

        function performDeleteRemovedTranslation(msgid) {
            const csrfMeta = document.querySelector('meta[name=csrf-token]');
            const csrfToken = csrfMeta ? csrfMeta.getAttribute('content') : '';
            const payloadObj = { msgid: msgid, csrf_token: csrfToken };
            var payloadB64;
            try {
                payloadB64 = btoa(unescape(encodeURIComponent(JSON.stringify(payloadObj))));
            } catch (err) {
                console.error('delete-removed: encode payload failed', err);
                if (window.showAlert) window.showAlert(cfg.t.couldNotPrepareDelete, 'error');
                return;
            }
            var fetchFn = (window.getFetch && window.getFetch()) || fetch;
            fetchFn(cfg.urls.deleteRemovedTranslation, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({ payload: payloadB64 })
            })
            .then(function(response) { return response.json().then(function(data) { return { ok: response.ok, data: data }; }); })
            .then(function(result) {
                if (result.ok && result.data && result.data.success) {
                    if (window.showAlert) window.showAlert(result.data.message || cfg.t.removedObsolete, 'success');
                    window.location.reload();
                    return;
                }
                var errMsg = (result.data && (result.data.message || result.data.error))
                    ? (result.data.message || result.data.error)
                    : cfg.t.deleteFailed;
                throw new Error(errMsg);
            })
            .catch(function(error) {
                console.error('delete-removed translation:', error);
                if (window.showAlert) window.showAlert(error.message || cfg.t.deleteFailed, 'error');
            });
        }

        document.addEventListener('click', function(e) {
            var delBtn = e.target.closest('.delete-removed-translation-btn');
            if (!delBtn) return;
            e.preventDefault();
            e.stopPropagation();
            var msgid = decodeURIComponent(delBtn.getAttribute('data-msgid') || '');
            if (!msgid) return;
            var confirmMsg = cfg.t.permanentDeleteConfirm;
            var confirmTitle = cfg.t.deleteRemovedTitle;
            var doDelete = function() { performDeleteRemovedTranslation(msgid); };
            if (window.showDangerConfirmation) {
                window.showDangerConfirmation(confirmMsg, doDelete, null, cfg.t.deleteBtn, cfg.t.cancel, confirmTitle);
            } else if (window.showConfirmation) {
                window.showConfirmation(confirmMsg, doDelete, null, cfg.t.deleteBtn, cfg.t.cancel, confirmTitle);
            } else if (window.confirm(confirmMsg)) {
                doDelete();
            }
        });

        // Form submission
        form.addEventListener('submit', function(e) {
            e.preventDefault();

            const msgid = document.getElementById('edit-translation-msgid').value;
            const sourcePlaceholders = extractPlaceholders(msgid);

            // Validate placeholders
            if (sourcePlaceholders.length > 0) {
                const translationFields = document.querySelectorAll('#edit-translation-modal [id^="msgstr_"]');
                let hasErrors = false;
                const errors = [];

                translationFields.forEach(field => {
                    const translationText = field.value.trim();
                    if (translationText) {
                        const validation = validatePlaceholders(msgid, translationText);
                        if (!validation.valid) {
                            hasErrors = true;
                            const langCode = field.id.replace('msgstr_', '');
                            errors.push(langCode.toUpperCase() + ': ' + validation.message);
                            field.classList.add('border-red-500');
                            const errorDiv = field.parentElement.querySelector('.placeholder-error');
                            if (errorDiv) {
                                errorDiv.textContent = validation.message;
                                errorDiv.classList.remove('hidden');
                            }
                        } else {
                            field.classList.remove('border-red-500');
                            const errorDiv = field.parentElement.querySelector('.placeholder-error');
                            if (errorDiv) errorDiv.classList.add('hidden');
                        }
                    }
                });

                if (hasErrors) {
                    var m = cfg.t.validationError + '\n\n' + errors.join('\n\n') + '\n\n' + cfg.t.fixErrorsBeforeSaving;
                    if (window.showAlert) window.showAlert(m, 'error');
                    else console.error(m);
                    return false;
                }
            }

            // Submit form using a base64-wrapped payload to avoid WAF false positives on msgid/msgstr content.
            var payloadObj = window.formDataToJson ? window.formDataToJson(form) : null;
            if (!payloadObj) throw new Error('JSON payload helper is not available');
            var csrfToken = (payloadObj && payloadObj.csrf_token) ? String(payloadObj.csrf_token) : '';
            var payloadB64 = btoa(unescape(encodeURIComponent(JSON.stringify(payloadObj))));
            var fetchFn = (window.getFetch && window.getFetch()) || fetch;

            setEditModalSaving(true);
            fetchFn(cfg.urls.editTranslation, {
                method: 'POST',
                body: JSON.stringify({ payload: payloadB64 }),
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken }
            })
            .then(response => {
                if (response.ok) {
                    return response.json();
                }
                throw new Error(cfg.t.failedToSave);
            })
            .then(data => {
                if (data.success) {
                    updateGridRowTranslations(msgid, payloadObj);
                    setEditModalSaving(false);
                    closeEditModal();
                    var flashCategory = data.updated_count > 0 ? 'success' : 'warning';
                    if (window.FlashMessages && typeof window.FlashMessages.add === 'function') {
                        window.FlashMessages.add(data.message || cfg.t.savedSuccessfully, flashCategory);
                    } else if (typeof window.showFlashMessage === 'function') {
                        window.showFlashMessage(data.message || cfg.t.savedSuccessfully, flashCategory);
                    }
                } else {
                    throw new Error(data.message || cfg.t.failedToSave);
                }
            })
            .catch(error => {
                console.error('Error saving translation:', error);
                var m = cfg.t.failedToSave + ': ' + error.message;
                if (window.showAlert) window.showAlert(m, 'error');
                else console.error(m);
            })
            .finally(function() {
                setEditModalSaving(false);
            });
        });

        // Auto-translate button
        const autoTranslateBtn = document.getElementById('modal-auto-translate-btn');
        if (autoTranslateBtn) {
            autoTranslateBtn.addEventListener('click', async function() {
                try {
                    const icon = document.getElementById('modal-auto-translate-icon');
                    const spinner = document.getElementById('modal-auto-translate-spinner');
                    const textEl = document.getElementById('modal-auto-translate-text');

                    autoTranslateBtn.disabled = true;
                    autoTranslateBtn.classList.add('opacity-70', 'cursor-not-allowed');
                    if (icon) icon.classList.add('hidden');
                    if (spinner) spinner.classList.remove('hidden');
                    if (textEl) {
                        textEl.dataset.original = textEl.textContent;
                        textEl.textContent = cfg.t.translatingText;
                    }

                    const msgid = document.getElementById('edit-translation-msgid').value;
                    const englishEl = document.getElementById('msgstr_en');
                    let baseText = (englishEl && englishEl.value.trim()) || msgid || '';

                    if (!baseText) {
                        if (window.showAlert) window.showAlert(cfg.t.noSourceText, 'warning');
                        return;
                    }

                    const targetLanguages = Array.from(document.querySelectorAll('#edit-translation-modal [id^="msgstr_"]'))
                        .map(el => el.id.replace(/^msgstr_/, '').trim())
                        .filter(code => code && code !== 'en')
                        .filter((code, idx, arr) => arr.indexOf(code) === idx)
                        .filter(code => {
                            const el = document.getElementById('msgstr_' + code);
                            return el && !el.value.trim();
                        });

                    if (!targetLanguages.length) {
                        if (window.showAlert) window.showAlert(cfg.t.nothingToTranslate, 'info');
                        return;
                    }

                    const data = await window.AutoTranslateService.translate({
                        type: 'section_name',
                        permission_context: 'translations',
                        permission_code: 'admin.translations.manage',
                        text: baseText,
                        target_languages: targetLanguages,
                        translation_service: 'ifrc'
                    });

                    if (data.translations) {
                        Object.entries(data.translations).forEach(([code, value]) => {
                            const field = document.getElementById('msgstr_' + code);
                            if (field && !field.value.trim()) {
                                field.value = value || '';
                                if (isRTL(code)) {
                                    field.setAttribute('dir', 'rtl');
                                }
                            }
                        });
                    }
                } catch (e) {
                    console.error(e);
                    var m = cfg.t.autoTranslateFailed + ' ' + (e && e.message ? e.message : '');
                    if (window.showAlert) window.showAlert(m, 'error');
                    else console.error(m);
                } finally {
                    const icon = document.getElementById('modal-auto-translate-icon');
                    const spinner = document.getElementById('modal-auto-translate-spinner');
                    const textEl = document.getElementById('modal-auto-translate-text');
                    if (spinner) spinner.classList.add('hidden');
                    if (icon) icon.classList.remove('hidden');
                    if (textEl && textEl.dataset.original) textEl.textContent = textEl.dataset.original;
                    autoTranslateBtn.disabled = false;
                    autoTranslateBtn.classList.remove('opacity-70', 'cursor-not-allowed');
                }
            });
        }

        // Clear translations button
        const clearBtn = document.getElementById('modal-clear-translations-btn');
        if (clearBtn) {
            clearBtn.addEventListener('click', function() {
                const msg = cfg.t.clearConfirm;
                function doClear() {
                    const translationFields = document.querySelectorAll('#edit-translation-modal textarea[id^="msgstr_"], #edit-translation-modal input[id^="msgstr_"]');
                    let clearedCount = 0;

                    translationFields.forEach(field => {
                        const fieldId = field.id;
                        if (fieldId === 'msgstr_en' || fieldId.startsWith('msgstr_en_')) return;

                        if (field.value && field.value.trim() !== '') {
                            field.value = '';
                            clearedCount++;
                            field.classList.remove('border-red-500', 'border-2', 'border-yellow-500');
                            const errorDiv = field.parentElement.querySelector('.placeholder-error');
                            if (errorDiv) errorDiv.remove();
                        }
                    });

                    if (clearedCount > 0) {
                        var m = clearedCount === 1
                            ? cfg.t.cleared1
                            : cfg.t.cleared + ' ' + clearedCount + ' ' + cfg.t.translationFields;
                        if (window.showAlert) window.showAlert(m, 'success');
                    } else {
                        if (window.showAlert) window.showAlert(cfg.t.noFieldsToClear, 'info');
                    }
                }
                if (window.showDangerConfirmation) {
                    window.showDangerConfirmation(msg, doClear, null, cfg.t.clearBtn, cfg.t.cancel, cfg.t.clearTitle);
                } else if (window.showConfirmation) {
                    window.showConfirmation(msg, doClear, null, cfg.t.clearBtn, cfg.t.cancel, cfg.t.clearTitle);
                } else {
                    doClear();
                }
            });
        }

        // Real-time placeholder validation
        document.addEventListener('blur', function(e) {
            if (e.target.matches('#edit-translation-modal [id^="msgstr_"]')) {
                const msgid = document.getElementById('edit-translation-msgid').value;
                const sourcePlaceholders = extractPlaceholders(msgid);
                if (sourcePlaceholders.length > 0) {
                    const translationText = e.target.value.trim();
                    if (translationText) {
                        const validation = validatePlaceholders(msgid, translationText);
                        if (!validation.valid) {
                            e.target.classList.add('border-red-500', 'border-2');
                            const errorDiv = e.target.parentElement.querySelector('.placeholder-error');
                            if (errorDiv) {
                                errorDiv.textContent = validation.message;
                                errorDiv.classList.remove('hidden');
                            }
                        } else {
                            e.target.classList.remove('border-red-500', 'border-2');
                            const errorDiv = e.target.parentElement.querySelector('.placeholder-error');
                            if (errorDiv) errorDiv.classList.add('hidden');
                        }
                    }
                }
            }
        }, true);
    })();

}());