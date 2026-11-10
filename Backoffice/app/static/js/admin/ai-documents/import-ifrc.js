/**
 * External API (IFRC) import tab.
 * Type and country lists are cached. Choosing "all" again restores the cache
 * instead of leaving the other dropdown stuck on the previous filter.
 * In-flight responses are ignored when a newer selection has already been applied.
 */

import {
    cfg,
    escapeAttr,
    escapeHtml,
    formatImportFooterSummary,
    hideProcessingBanner,
    notifyDocs,
    page,
    sanitizeUrl,
    startIfrcImportJobPolling,
    syncUploadImportModalFooter,
} from './shared.js';

let ifrcDocumentsGridHelper = null;
let ifrcDocumentsGridApi = null;
let allIfrcTypes = null;
let allIfrcCountries = null;
let ifrcTypesRequest = 0;
let ifrcCountriesRequest = 0;

export function syncUploadImportModalIfrcCompactLayout() {
    const modal = document.getElementById('uploadImportModal');
    if (!modal) return;
    const ifrcContent = document.getElementById('ifrcApiContent');
    const shell = document.getElementById('ifrcDocumentsGridShell');
    const ifrcVisible = !!(ifrcContent && !ifrcContent.classList.contains('hidden'));
    const gridHidden = !shell || shell.classList.contains('hidden');
    modal.classList.toggle('upload-import-modal--ifrc-idle', ifrcVisible && gridHidden);
    if (ifrcContent) ifrcContent.classList.toggle('ifrc-api-tab--expanded', ifrcVisible && !gridHidden);
    syncUploadImportModalFooter();
}

function getIfrcTypeFilterListEl() {
    return document.getElementById('ifrcTypeFilterList');
}

function isIfrcTypeDropdownOpen() {
    const dd = document.getElementById('ifrcTypeFilterDropdown');
    return !!(dd && !dd.classList.contains('hidden'));
}

function clearIfrcTypeDropdownPosition() {
    const dd = document.getElementById('ifrcTypeFilterDropdown');
    if (!dd) return;
    dd.classList.remove('ifrc-type-dd--viewport');
    ['position', 'left', 'width', 'right', 'top', 'bottom', 'maxHeight', 'zIndex'].forEach(function (prop) {
        dd.style[prop] = '';
    });
}

function positionIfrcTypeDropdown() {
    const dd = document.getElementById('ifrcTypeFilterDropdown');
    const btn = document.getElementById('ifrcTypeFilterToggle');
    if (!dd || !btn || dd.classList.contains('hidden')) return;
    const narrow = window.matchMedia('(max-width: 767px), (max-height: 720px)').matches;
    if (!narrow) {
        clearIfrcTypeDropdownPosition();
        return;
    }
    const rect = btn.getBoundingClientRect();
    if (rect.bottom < 8 || rect.top > window.innerHeight - 8) {
        setIfrcTypeDropdownOpen(false);
        return;
    }
    const gap = 4;
    const margin = 8;
    const spaceBelow = window.innerHeight - rect.bottom - margin;
    const spaceAbove = rect.top - margin;
    const openUp = spaceBelow < 160 && spaceAbove > spaceBelow;
    const maxH = Math.max(140, Math.min(320, (openUp ? spaceAbove : spaceBelow) - gap));
    dd.classList.add('ifrc-type-dd--viewport');
    dd.style.position = 'fixed';
    dd.style.left = Math.max(margin, rect.left) + 'px';
    dd.style.width = Math.max(160, rect.width) + 'px';
    dd.style.right = 'auto';
    dd.style.zIndex = '11100';
    dd.style.maxHeight = maxH + 'px';
    if (openUp) {
        dd.style.top = 'auto';
        dd.style.bottom = (window.innerHeight - rect.top + gap) + 'px';
    } else {
        dd.style.bottom = 'auto';
        dd.style.top = (rect.bottom + gap) + 'px';
    }
}

function setIfrcTypeDropdownOpen(open) {
    const dd = document.getElementById('ifrcTypeFilterDropdown');
    const btn = document.getElementById('ifrcTypeFilterToggle');
    if (!dd || !btn) return;
    if (open) {
        dd.classList.remove('hidden');
        btn.setAttribute('aria-expanded', 'true');
        window.requestAnimationFrame(positionIfrcTypeDropdown);
    } else {
        dd.classList.add('hidden');
        btn.setAttribute('aria-expanded', 'false');
        clearIfrcTypeDropdownPosition();
    }
}

function getIfrcTypeIdsChecked() {
    const list = getIfrcTypeFilterListEl();
    if (!list) return [];
    return Array.from(list.querySelectorAll('input[type="checkbox"][name="ifrc_type_option"]:checked')).map(function (cb) {
        return String(cb.value || '').trim();
    }).filter(Boolean);
}

function getIfrcTypeCheckboxCount() {
    const list = getIfrcTypeFilterListEl();
    if (!list) return 0;
    return list.querySelectorAll('input[type="checkbox"][name="ifrc_type_option"]').length;
}

function updateIfrcTypeFilterSummary() {
    const summary = document.getElementById('ifrcTypeFilterSummary');
    if (!summary) return;
    const checked = getIfrcTypeIdsChecked();
    const total = getIfrcTypeCheckboxCount();
    if (total === 0) {
        summary.textContent = cfg.t.no_types_loaded_62ef2d48 || '';
        return;
    }
    if (checked.length === 0 || checked.length === total) summary.textContent = cfg.t.all_types_134353eb || '';
    else summary.textContent = (cfg.t.selected_91b442d3 || '') + ': ' + checked.length + ' / ' + total;
}

function getIfrcSelectedAppealsTypeIdsForCountryFilter() {
    const ids = getIfrcTypeIdsChecked();
    const total = getIfrcTypeCheckboxCount();
    if (total === 0 || ids.length === 0 || ids.length === total) return '';
    return ids.join(',');
}

function getIfrcAppealsTypeIdsParamForList() {
    const ids = getIfrcTypeIdsChecked();
    const total = getIfrcTypeCheckboxCount();
    if (total === 0 || ids.length === 0 || ids.length === total) return 'all';
    return ids.join(',');
}

function renderIfrcTypes(types) {
    const listEl = getIfrcTypeFilterListEl();
    if (!listEl) return;
    const previousChecked = new Set(getIfrcTypeIdsChecked());
    listEl.replaceChildren();
    const hasGroups = types.some(function (t) { return t.group; });
    let lastGroupKey = null;
    types.forEach(function (t) {
        const id = String(t.id != null ? t.id : '').trim();
        const name = t.name || id;
        if (!id) return;
        if (hasGroups) {
            const raw = (t.group || '').trim();
            const gKey = raw || '__other__';
            if (gKey !== lastGroupKey) {
                lastGroupKey = gKey;
                const gh = document.createElement('div');
                gh.className = 'text-xs font-semibold text-gray-500 pt-2 first:pt-0 pb-1';
                gh.textContent = raw || cfg.t.other_6311ae17 || '';
                listEl.appendChild(gh);
            }
        }
        const label = document.createElement('label');
        label.className = 'flex items-center gap-2 cursor-pointer hover:bg-gray-50 rounded px-1 py-0.5';
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.name = 'ifrc_type_option';
        cb.value = id;
        cb.className = 'rounded border-gray-300 text-blue-600 focus:ring-blue-500';
        if (previousChecked.size) cb.checked = previousChecked.has(id);
        const span = document.createElement('span');
        span.className = 'text-sm text-gray-800';
        span.textContent = name;
        label.appendChild(cb);
        label.appendChild(span);
        listEl.appendChild(label);
    });
    updateIfrcTypeFilterSummary();
}

export async function loadIfrcTypes(countryName, options) {
    const opts = options || {};
    const listEl = getIfrcTypeFilterListEl();
    if (!listEl) return;
    if (!countryName && !opts.restoreAll && allIfrcTypes) return;
    const req = ++ifrcTypesRequest;
    if (!countryName && opts.restoreAll && allIfrcTypes) {
        renderIfrcTypes(allIfrcTypes);
        return;
    }
    try {
        const url = countryName
            ? '/api/ai/documents/ifrc-api/filter-options?country_name=' + encodeURIComponent(countryName)
            : '/api/ai/documents/ifrc-api/types';
        const response = await csrfFetch(url, { method: 'GET', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
        const result = await response.json();
        if (req !== ifrcTypesRequest) return;
        if (result.success && Array.isArray(result.types)) {
            if (!countryName) allIfrcTypes = result.types;
            renderIfrcTypes(result.types);
        }
    } catch (error) {
        console.error('Error loading external API document types:', error);
    }
}

function renderIfrcCountries(countries) {
    const countrySelect = document.getElementById('ifrcCountryNameFilter');
    if (!countrySelect) return;
    const currentCountry = countrySelect.value;
    const sorted = countries.slice().sort(function (a, b) {
        const nameA = (a.name || a.localized_name || '').toLowerCase();
        const nameB = (b.name || b.localized_name || '').toLowerCase();
        return nameA.localeCompare(nameB);
    });
    countrySelect.replaceChildren();
    const allOpt = document.createElement('option');
    allOpt.value = '';
    allOpt.textContent = cfg.t.all_countries_74202da6 || '';
    countrySelect.appendChild(allOpt);
    sorted.forEach(function (country) {
        const countryName = country.name || country.localized_name;
        if (!countryName) return;
        const option = document.createElement('option');
        option.value = countryName;
        option.textContent = countryName;
        countrySelect.appendChild(option);
    });
    if (currentCountry && Array.from(countrySelect.options).some(function (o) { return o.value === currentCountry; })) {
        countrySelect.value = currentCountry;
    } else {
        countrySelect.value = '';
    }
}

export async function loadIfrcCountries(appealsTypeIds, options) {
    const opts = options || {};
    const countrySelect = document.getElementById('ifrcCountryNameFilter');
    if (!countrySelect) return;
    if (!appealsTypeIds && !opts.restoreAll && allIfrcCountries) return;
    const req = ++ifrcCountriesRequest;
    if (!appealsTypeIds && opts.restoreAll && allIfrcCountries) {
        renderIfrcCountries(allIfrcCountries);
        return;
    }
    try {
        let countries = [];
        if (appealsTypeIds) {
            const response = await csrfFetch(
                '/api/ai/documents/ifrc-api/filter-options?appeals_type_ids=' + encodeURIComponent(appealsTypeIds),
                { method: 'GET', headers: { 'X-Requested-With': 'XMLHttpRequest' } }
            );
            const result = await response.json();
            if (result.success && Array.isArray(result.countries)) countries = result.countries;
        } else {
            const response = await ((window.getFetch && window.getFetch()) || fetch)('/api/v1/countrymap', {
                method: 'GET',
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
            });
            if (!response.ok) throw new Error('HTTP error! status: ' + response.status);
            const countriesData = await response.json();
            if (Array.isArray(countriesData)) countries = countriesData;
            else if (countriesData && Array.isArray(countriesData.countries)) countries = countriesData.countries;
        }
        if (req !== ifrcCountriesRequest) return;
        if (!appealsTypeIds) allIfrcCountries = countries;
        renderIfrcCountries(countries);
    } catch (error) {
        console.error('Error loading countries:', error);
        if (req !== ifrcCountriesRequest) return;
        countrySelect.replaceChildren();
        const option = document.createElement('option');
        option.value = '';
        option.textContent = cfg.t.error_loading_countries_b47e1f6f || '';
        countrySelect.appendChild(option);
    }
}

export async function ensureIfrcFilterDropdowns() {
    await Promise.all([loadIfrcTypes(''), loadIfrcCountries('')]);
}

function onTypeSelectionChanged() {
    updateIfrcTypeFilterSummary();
    const ids = getIfrcSelectedAppealsTypeIdsForCountryFilter();
    loadIfrcCountries(ids, { restoreAll: !ids });
}

function mapIfrcDocumentToRow(doc, importedSet) {
    if (!doc) return null;
    const url = String(doc.url || '');
    return {
        url: url,
        title: doc.title || doc.base_filename || '',
        type: doc.type || '',
        year: doc.year != null && doc.year !== '' ? String(doc.year) : '',
        date: doc.date ? String(doc.date).substring(0, 10) : '',
        country_name: doc.country_name || '',
        country_code: doc.country_code || '',
        country_id: doc.country_id != null ? doc.country_id : null,
        already_imported: !!(url && importedSet.has(url)),
    };
}

const wrappedCell = {
    'white-space': 'normal',
    'line-height': '1.4',
    display: 'flex',
    'align-items': 'flex-start',
    'padding-top': '6px',
    'padding-bottom': '6px',
};

function columnDefs() {
    return [
        {
            field: 'title',
            headerName: cfg.t.document_09453598,
            flex: 1,
            minWidth: 220,
            filter: 'agTextColumnFilter',
            wrapText: true,
            autoHeight: true,
            valueGetter: function (params) { return ((params.data || {}).title || '').trim(); },
            cellRenderer: function (params) {
                const d = params.data || {};
                const title = escapeHtml(d.title || '');
                const wrap = 'white-space:normal;overflow-wrap:anywhere;word-break:break-word;max-width:100%';
                const safeHref = sanitizeUrl(d.url || '');
                const canLink = !!(safeHref && safeHref !== '#');
                const titleLine = canLink
                    ? '<a href="' + escapeAttr(safeHref) + '" class="ifrc-doc-title-link text-sm font-medium text-blue-600 hover:text-blue-800 hover:underline" style="' + wrap + '" target="_blank" rel="noopener noreferrer" title="' + escapeAttr(cfg.t.open_document_18c0765a || '') + '">' + title + '</a>'
                    : '<div class="text-sm font-medium text-gray-900" style="' + wrap + '">' + title + '</div>';
                return '<div class="flex items-start gap-2 min-w-0" style="width:100%"><div class="flex-shrink-0 text-red-500" style="padding-top:2px"><i class="fas fa-file-pdf text-xl"></i></div><div class="min-w-0 flex-1" style="' + wrap + '">' + titleLine + '</div></div>';
            },
            cellStyle: wrappedCell,
        },
        {
            field: 'type',
            headerName: cfg.t.type_a1fa2777,
            width: 200,
            minWidth: 140,
            maxWidth: 320,
            filter: 'customSetFilter',
            cellRenderer: function (params) {
                const v = String(params.value || '').trim();
                if (!v) return '<span class="text-xs text-gray-400">\u2014</span>';
                return '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-50 text-blue-800">' + escapeHtml(v) + '</span>';
            },
        },
        {
            field: 'year',
            headerName: cfg.t.year_537c66b2,
            width: 100,
            minWidth: 80,
            maxWidth: 120,
            filter: 'agTextColumnFilter',
            cellRenderer: function (params) {
                if (params.value == null || params.value === '') return '<span class="text-xs text-gray-400">\u2014</span>';
                return '<span class="text-sm text-gray-700">' + escapeHtml(String(params.value)) + '</span>';
            },
        },
        {
            field: 'date',
            headerName: cfg.t.date_4e8a1c90,
            width: 130,
            minWidth: 110,
            maxWidth: 160,
            filter: 'agDateColumnFilter',
            filterParams: (typeof AgGridRenderers !== 'undefined' && AgGridRenderers.dateFilterParams) ? AgGridRenderers.dateFilterParams : undefined,
            sortable: true,
            cellRenderer: function (params) {
                if (params.value == null || params.value === '') return '<span class="text-xs text-gray-400">\u2014</span>';
                return '<span class="text-sm text-gray-700">' + escapeHtml(String(params.value).substring(0, 10)) + '</span>';
            },
        },
        {
            field: 'country_name',
            headerName: cfg.t.country_59716c97,
            width: 160,
            minWidth: 120,
            maxWidth: 220,
            filter: 'agTextColumnFilter',
            wrapText: true,
            autoHeight: true,
            valueGetter: function (params) {
                const d = params.data || {};
                return (d.country_name || '').trim() || (d.country_code || '').trim();
            },
            cellRenderer: function (params) {
                const d = params.data || {};
                if (d.country_name) return '<span class="text-sm text-gray-700">' + escapeHtml(d.country_name) + '</span>';
                if (d.country_code) return '<span class="text-sm text-gray-700">' + escapeHtml(d.country_code) + '</span>';
                return '<span class="text-xs text-gray-400">\u2014</span>';
            },
            cellStyle: wrappedCell,
        },
    ];
}

function syncIfrcSelectionFromGrid() {
    page.selectedIfrcDocuments.clear();
    if (ifrcDocumentsGridHelper) {
        ifrcDocumentsGridHelper.getSelectedRows().forEach(function (row) {
            if (row && row.url && !row.already_imported) page.selectedIfrcDocuments.add(row.url);
        });
    }
    updateIfrcSelectedSummary();
}

function updateIfrcSelectedSummary() {
    const summaryEl = document.getElementById('ifrcSelectedSummary');
    const importBtn = document.getElementById('ifrcImportSelectedBtn');
    const count = page.selectedIfrcDocuments.size;
    if (importBtn) importBtn.disabled = count === 0;
    if (summaryEl) summaryEl.textContent = formatImportFooterSummary(count);
}

function updateIfrcActionsVisibility(rowCount) {
    page.ifrcTabHasRows = (Number(rowCount) || 0) > 0;
    syncUploadImportModalFooter();
    if (page.ifrcTabHasRows) updateIfrcSelectedSummary();
}

function layoutIfrcGrid() {
    window.requestAnimationFrame(function () {
        window.requestAnimationFrame(function () {
            if (ifrcDocumentsGridHelper && typeof ifrcDocumentsGridHelper.setDynamicHeight === 'function') {
                try { ifrcDocumentsGridHelper.setDynamicHeight(); } catch (e) { /* ignore */ }
            }
            if (ifrcDocumentsGridApi && typeof ifrcDocumentsGridApi.doLayout === 'function') {
                try { ifrcDocumentsGridApi.doLayout(); } catch (e) { /* ignore */ }
            }
        });
    });
}

function ensureIfrcDocumentsGrid(rowData) {
    const loadingEl = document.getElementById('ifrcDocumentsGrid-loading');
    const emptyEl = document.getElementById('ifrcDocumentsGrid-empty');
    const containerEl = document.getElementById('ifrcDocumentsGrid-container');
    const rows = rowData || [];
    if (!ifrcDocumentsGridHelper) {
        try {
            ifrcDocumentsGridHelper = new AgGridHelper({
                containerId: 'ifrcDocumentsGrid',
                templateId: 'ai-ifrc-api-documents',
                columnDefs: columnDefs(),
                rowData: rows,
                options: {
                    rowSelection: { mode: 'multiRow', enableClickSelection: true, selectAll: 'filtered' },
                    isRowSelectable: function (node) { return !!(node && node.data && !node.data.already_imported); },
                    onSelectionChanged: syncIfrcSelectionFromGrid,
                    paginationPageSize: 25,
                    defaultColDef: {
                        wrapText: false,
                        autoHeight: false,
                        sortable: true,
                        resizable: true,
                        cellStyle: { display: 'flex', alignItems: 'center', justifyContent: 'flex-start' },
                    },
                },
                columnVisibilityOptions: { showPanelButton: false, enableExport: false, enableReset: true },
                heightOptions: {
                    useParentContainerHeight: true,
                    minHeight: 280,
                    maxHeight: 520,
                    absoluteMinHeight: 240,
                    viewportOffset: 140,
                },
            });
            ifrcDocumentsGridApi = ifrcDocumentsGridHelper.initialize();
            const gridEl = document.getElementById('ifrcDocumentsGrid');
            if (gridEl && gridEl.dataset.ifrcLinkGuard !== '1') {
                gridEl.dataset.ifrcLinkGuard = '1';
                gridEl.addEventListener('click', function (ev) {
                    if (ev.target.closest && ev.target.closest('a.ifrc-doc-title-link')) ev.stopPropagation();
                }, true);
            }
            if (page.documentsGridApi) window.gridApi = page.documentsGridApi;
            if (page.documentsGridHelper) window.gridHelper = page.documentsGridHelper;
            window.ifrcDocumentsGridApi = ifrcDocumentsGridApi;
            window.ifrcDocumentsGridHelper = ifrcDocumentsGridHelper;
        } catch (e) {
            console.error('IFRC documents grid init failed:', e);
            ifrcDocumentsGridHelper = null;
            ifrcDocumentsGridApi = null;
            if (loadingEl) loadingEl.style.display = 'none';
            if (containerEl) containerEl.style.display = 'none';
            if (emptyEl) emptyEl.style.display = 'block';
            const initErr = document.getElementById('ifrcDocumentsFetchError');
            if (initErr) {
                initErr.textContent = cfg.t.failed_to_load_documents_from_external_a_6a7d9a35 || '';
                initErr.classList.remove('hidden');
            }
            updateIfrcActionsVisibility(0);
            return;
        }
    } else {
        ifrcDocumentsGridHelper.setRowData(rows);
        if (ifrcDocumentsGridApi && typeof ifrcDocumentsGridApi.deselectAll === 'function') ifrcDocumentsGridApi.deselectAll();
        syncIfrcSelectionFromGrid();
    }
    if (loadingEl) loadingEl.style.display = 'none';
    if (containerEl) containerEl.style.display = 'block';
    if (emptyEl) emptyEl.style.display = 'none';
    updateIfrcActionsVisibility(rows.length);
    layoutIfrcGrid();
}

export async function loadIfrcApiDocuments() {
    const loading = document.getElementById('ifrcLoading');
    const yearFilter = document.getElementById('ifrcYearFilter');
    const countryNameFilter = document.getElementById('ifrcCountryNameFilter');
    const shell = document.getElementById('ifrcDocumentsGridShell');
    const hint = document.getElementById('ifrcDocumentsEmptyHint');
    const errEl = document.getElementById('ifrcDocumentsFetchError');
    if (!loading) return;
    if (hint) hint.classList.add('hidden');
    if (shell) shell.classList.remove('hidden');
    syncUploadImportModalIfrcCompactLayout();
    if (errEl) {
        errEl.textContent = '';
        errEl.classList.add('hidden');
    }
    loading.classList.remove('hidden');
    page.selectedIfrcDocuments.clear();
    if (ifrcDocumentsGridApi && typeof ifrcDocumentsGridApi.deselectAll === 'function') ifrcDocumentsGridApi.deselectAll();
    updateIfrcSelectedSummary();
    try {
        const params = new URLSearchParams();
        params.append('appeals_type_ids', getIfrcAppealsTypeIdsParamForList());
        if (yearFilter && yearFilter.value.trim()) params.append('year_filter', yearFilter.value.trim());
        if (countryNameFilter && countryNameFilter.value.trim()) params.append('country_name', countryNameFilter.value.trim());
        const response = await csrfFetch('/api/ai/documents/ifrc-api/list?' + params.toString(), {
            method: 'GET',
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
        });
        const result = await response.json();
        if (!response.ok || !result.success) {
            if (errEl) {
                errEl.textContent = String((result && result.error) || cfg.t.error_loading_documents_a708c41e || '');
                errEl.classList.remove('hidden');
            }
            if (ifrcDocumentsGridHelper) ifrcDocumentsGridHelper.setRowData([]);
            else if (shell) ensureIfrcDocumentsGrid([]);
            syncIfrcSelectionFromGrid();
            updateIfrcActionsVisibility(0);
            return;
        }
        const importedSet = new Set(result.already_imported_urls || []);
        const docs = Array.isArray(result.documents) ? result.documents : [];
        const rows = docs.slice().sort(function (a, b) {
            return (importedSet.has(a && a.url) ? 1 : 0) - (importedSet.has(b && b.url) ? 1 : 0);
        }).map(function (doc) { return mapIfrcDocumentToRow(doc, importedSet); }).filter(Boolean);
        ensureIfrcDocumentsGrid(rows);
        syncIfrcSelectionFromGrid();
    } catch (error) {
        console.error('Error loading external API documents:', error);
        if (errEl) {
            errEl.textContent = cfg.t.failed_to_load_documents_from_external_a_6a7d9a35 || '';
            errEl.classList.remove('hidden');
        }
        if (ifrcDocumentsGridHelper) ifrcDocumentsGridHelper.setRowData([]);
        syncIfrcSelectionFromGrid();
        updateIfrcActionsVisibility(0);
    } finally {
        loading.classList.add('hidden');
        syncUploadImportModalIfrcCompactLayout();
    }
}

async function importIfrcDocuments() {
    const importBtn = document.getElementById('ifrcImportSelectedBtn');
    if (!importBtn) return;
    let items = [];
    if (ifrcDocumentsGridHelper && typeof ifrcDocumentsGridHelper.getSelectedRows === 'function') {
        items = ifrcDocumentsGridHelper.getSelectedRows()
            .filter(function (row) { return row && row.url && !row.already_imported; })
            .map(function (row) {
                const countryId = row.country_id != null ? Number(row.country_id) : null;
                return {
                    url: row.url,
                    title: row.title || '',
                    document_type: row.type || '',
                    is_public: true,
                    country_id: Number.isFinite(countryId) ? countryId : null,
                    country_name: row.country_name || null,
                };
            });
    }
    if (items.length === 0 && page.selectedIfrcDocuments.size > 0) {
        items = Array.from(page.selectedIfrcDocuments).map(function (url) {
            return { url: url, title: '', is_public: true, country_id: null, country_name: null };
        });
    }
    if (items.length === 0) return;
    importBtn.disabled = true;
    const originalText = importBtn.innerHTML;
    importBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>' + escapeHtml(cfg.t.importing_fa072aec || '');
    const jobApi = window.AiDocsJobProgress;
    if (jobApi && jobApi.setStandaloneMode) jobApi.setStandaloneMode(false);
    try {
        const payload = JSON.stringify({ items: items });
        const payloadB64 = btoa(unescape(encodeURIComponent(payload)));
        const response = await csrfFetch('/api/ai/documents/ifrc-api/import-bulk', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
            body: JSON.stringify({ payload: payloadB64 }),
        });
        const result = await response.json();
        if (!response.ok || !result || !result.success || !result.job_id) {
            throw new Error((result && result.error) ? result.error : 'Failed to start bulk import');
        }
        page.closeUploadModal();
        startIfrcImportJobPolling(result.job_id, items.length);
        page.selectedIfrcDocuments.clear();
        updateIfrcSelectedSummary();
    } catch (e) {
        hideProcessingBanner();
        notifyDocs((cfg.t.failed_to_start_import_d9e1bb79 || 'Failed to start import') + ': ' + (e && e.message ? e.message : String(e)), 'error');
    } finally {
        importBtn.disabled = false;
        importBtn.innerHTML = originalText;
    }
}

export function initIfrcImport() {
    const importBtn = document.getElementById('ifrcImportSelectedBtn');
    if (importBtn) importBtn.addEventListener('click', importIfrcDocuments);
    const countryEl = document.getElementById('ifrcCountryNameFilter');
    if (countryEl) {
        countryEl.addEventListener('change', function () {
            const name = this.value.trim();
            loadIfrcTypes(name, { restoreAll: !name });
        });
    }
    const typeWrap = document.getElementById('ifrcTypeFilter');
    if (typeWrap) {
        typeWrap.addEventListener('change', function (e) {
            if (e.target && e.target.name === 'ifrc_type_option') onTypeSelectionChanged();
        });
        document.addEventListener('mousedown', function (e) {
            if (!isIfrcTypeDropdownOpen()) return;
            if (typeWrap.contains(e.target)) return;
            setIfrcTypeDropdownOpen(false);
        });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && isIfrcTypeDropdownOpen()) setIfrcTypeDropdownOpen(false);
        });
    }
    const selectAll = document.getElementById('ifrcTypeSelectAll');
    if (selectAll) {
        selectAll.addEventListener('click', function (e) {
            e.preventDefault();
            const list = getIfrcTypeFilterListEl();
            if (!list) return;
            list.querySelectorAll('input[name="ifrc_type_option"]').forEach(function (cb) { cb.checked = true; });
            onTypeSelectionChanged();
        });
    }
    const clearAll = document.getElementById('ifrcTypeClearAll');
    if (clearAll) {
        clearAll.addEventListener('click', function (e) {
            e.preventDefault();
            const list = getIfrcTypeFilterListEl();
            if (!list) return;
            list.querySelectorAll('input[name="ifrc_type_option"]').forEach(function (cb) { cb.checked = false; });
            onTypeSelectionChanged();
        });
    }
    const toggle = document.getElementById('ifrcTypeFilterToggle');
    if (toggle) {
        toggle.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            setIfrcTypeDropdownOpen(!isIfrcTypeDropdownOpen());
        });
    }
    const scrollPanel = document.getElementById('ifrcApiContent');
    if (scrollPanel) {
        scrollPanel.addEventListener('scroll', function () {
            if (isIfrcTypeDropdownOpen()) positionIfrcTypeDropdown();
        }, { passive: true });
    }
    window.addEventListener('resize', function () {
        if (isIfrcTypeDropdownOpen()) positionIfrcTypeDropdown();
    });
    const searchBtn = document.getElementById('ifrcSearchBtn');
    const refreshBtn = document.getElementById('ifrcRefreshBtn');
    async function search() {
        await ensureIfrcFilterDropdowns();
        await loadIfrcApiDocuments();
    }
    if (searchBtn) {
        searchBtn.addEventListener('click', function (e) {
            e.preventDefault();
            search().catch(function (err) { console.error('External API search:', err); });
        });
    }
    if (refreshBtn) {
        refreshBtn.addEventListener('click', function (e) {
            e.preventDefault();
            search().catch(function (err) { console.error('External API refresh:', err); });
        });
    }
}
