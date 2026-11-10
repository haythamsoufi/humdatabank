/**
 * "Import from System" grid inside the upload/import modal.
 */

import {
    cfg,
    confirmAction,
    escapeAttr,
    escapeHtml,
    formatFileSize,
    formatImportFooterSummary,
    getFileTypeIcon,
    hideProcessingBanner,
    importSystemBulkUrl,
    notifyDocs,
    page,
    startSystemImportJobPolling,
    syncUploadImportModalFooter,
} from './shared.js';

let importDocumentsGridHelper = null;
let importDocumentsGridApi = null;

function mapSystemDocumentToRow(doc) {
    if (!doc) return null;
    return {
        id: doc.id,
        filename: doc.filename || '',
        document_type: doc.document_type || '',
        country_name: doc.country_name || '',
        source: doc.source || '',
        assignment_name: doc.assignment_name || '',
        template_name: doc.template_name || '',
        period: doc.period || '',
        language: doc.language || '',
        language_display: doc.language_display || doc.language || '',
        uploaded_by: doc.uploaded_by || '',
        status: doc.status || '',
        is_public: !!doc.is_public,
        file_size: (typeof doc.file_size === 'number' && doc.file_size > 0) ? doc.file_size : null,
        file_pending: !!doc.file_pending,
        source_url: doc.source_url || null,
        source_url_http_status: doc.source_url_http_status != null ? doc.source_url_http_status : null,
        source_url_unreachable: !!doc.source_url_unreachable,
        uploaded_at: doc.uploaded_at || null,
        ai_processed: !!doc.ai_processed,
        ai_document_id: doc.ai_document_id != null ? doc.ai_document_id : null,
        ai_status: doc.ai_status || null,
    };
}

function importGridTextCell(value) {
    const v = (value == null ? '' : String(value)).trim();
    if (!v) return '<span class="text-xs text-gray-400">\u2014</span>';
    return '<span class="text-sm text-gray-700">' + escapeHtml(v) + '</span>';
}

function importGridSourceLabel(source) {
    const key = String(source || '').trim().toLowerCase();
    if (key === 'assignment') return cfg.t.source_assignment_5c1a8f3d;
    if (key === 'public') return cfg.t.source_public_7b2e4c9a;
    if (key === 'standalone') return cfg.t.source_standalone_3f8d1e6b;
    return '';
}

function importGridSourceUrlStatusLabel(data) {
    if (!data || !data.source_url_unreachable) return cfg.t.file_url_available_8e4f2a1b || 'Available';
    const status = data.source_url_http_status;
    if (status === 0) return cfg.t.file_url_empty_9c3d1e7a || 'No URL';
    if (status === 403) return cfg.t.file_url_forbidden_7b2a9c4d || 'URL blocked (403)';
    if (status === 404) return cfg.t.file_url_not_found_6a1b8e3c || 'URL not found (404)';
    if (status === -1) return cfg.t.file_url_error_5d0c7f2e || 'URL error';
    if (status != null) return (cfg.t.file_url_http_status_4e9a6b1d || 'HTTP {status}').replace('{status}', String(status));
    return cfg.t.file_url_unavailable_3f8e2d0c || 'URL unavailable';
}

const wrappedCell = {
    'white-space': 'normal',
    'line-height': '1.4',
    display: 'flex',
    'align-items': 'flex-start',
    'padding-top': '6px',
    'padding-bottom': '6px',
};

function textColumn(field, header, width, extra) {
    return Object.assign({
        field: field,
        headerName: header,
        width: width,
        minWidth: Math.max(80, width - 40),
        filter: 'agTextColumnFilter',
        wrapText: true,
        autoHeight: true,
        cellRenderer: function (params) { return importGridTextCell(params.value); },
        cellStyle: wrappedCell,
    }, extra || {});
}

function importFileSizeMeta(data) {
    const size = data && data.file_size;
    if (typeof size !== 'number' || size <= 0) return '';
    return '<div class="text-xs text-gray-500">' + escapeHtml(formatFileSize(size)) + '</div>';
}

function columnDefs() {
    return [
        {
            field: 'filename',
            headerName: cfg.t.filename_1351017a,
            flex: 1,
            minWidth: 220,
            filter: 'agTextColumnFilter',
            wrapText: true,
            autoHeight: true,
            cellRenderer: function (params) {
                const data = params.data || {};
                const icon = getFileTypeIcon(data.filename);
                const name = escapeHtml(data.filename || '');
                const wrap = 'white-space:normal;overflow-wrap:anywhere;word-break:break-word;max-width:100%';
                const docId = data.id != null ? parseInt(data.id, 10) : 0;
                const nameLine = docId
                    ? '<a href="/admin/ai/knowledge-base/download-system-document/' + docId + '" class="import-system-doc-filename-link text-sm font-medium text-blue-600 hover:text-blue-800 hover:underline" style="' + wrap + '" target="_blank" rel="noopener noreferrer" title="' + escapeAttr(cfg.t.view_or_download_9e34181d || '') + '">' + name + '</a>'
                    : '<div class="text-sm font-medium text-gray-900" style="' + wrap + '" title="' + escapeAttr(data.filename || '') + '">' + name + '</div>';
                return '<div class="flex items-start gap-2 min-w-0" style="width:100%"><div class="flex-shrink-0 text-gray-500" style="padding-top:2px">' +
                    icon + '</div><div class="min-w-0 flex-1" style="' + wrap + '">' + nameLine + importFileSizeMeta(data) + '</div></div>';
            },
            cellStyle: wrappedCell,
        },
        textColumn('country_name', cfg.t.entity_2a6f8c3e, 160, { filter: 'customSetFilter', maxWidth: 240 }),
        textColumn('assignment_name', cfg.t.assignment_8b3f1a2c, 200, { maxWidth: 320 }),
        textColumn('template_name', cfg.t.template_1d7b5e8c, 180, { filter: 'customSetFilter', maxWidth: 280 }),
        textColumn('document_type', cfg.t.document_type_4e7c9d1b, 160, { filter: 'customSetFilter', maxWidth: 240 }),
        textColumn('period', cfg.t.period_9d4e2b7a, 120, { wrapText: false, autoHeight: false, cellStyle: null, maxWidth: 160 }),
        {
            field: 'source',
            headerName: cfg.t.source_type_6a4c9e2f,
            width: 170,
            minWidth: 140,
            maxWidth: 220,
            filter: 'customSetFilter',
            filterValueGetter: function (params) { return importGridSourceLabel(params.data && params.data.source); },
            cellRenderer: function (params) { return importGridTextCell(importGridSourceLabel(params.data && params.data.source)); },
        },
        {
            field: 'language_display',
            headerName: cfg.t.language_4994a8ff,
            width: 100,
            minWidth: 80,
            maxWidth: 140,
            filter: 'customSetFilter',
            valueGetter: function (params) {
                const d = params.data || {};
                return (d.language_display || d.language || '').trim();
            },
            cellRenderer: function (params) { return importGridTextCell(params.value); },
        },
        textColumn('uploaded_by', cfg.t.uploaded_by_8e3c7a2d, 160, { maxWidth: 220 }),
        {
            field: 'status',
            headerName: cfg.t.status_ec53a8c4,
            width: 120,
            minWidth: 100,
            maxWidth: 160,
            filter: 'customSetFilter',
            cellRenderer: function (params) {
                const v = String(params.value || '').trim();
                if (!v) return '<span class="text-xs text-gray-400">\u2014</span>';
                return '<span class="text-sm text-gray-700 capitalize">' + escapeHtml(v) + '</span>';
            },
        },
        {
            field: 'is_public',
            headerName: cfg.t.public_3d067bed,
            width: 100,
            minWidth: 90,
            maxWidth: 120,
            filter: 'customSetFilter',
            sortable: true,
            filterValueGetter: function (params) {
                const isPublic = params.data && (params.data.is_public === true || params.data.is_public === 'true' || params.data.is_public === 1);
                return isPublic ? cfg.t.public_3d067bed : cfg.t.not_public_20257be8;
            },
            cellRenderer: function (params) {
                const isPublic = params.data && (params.data.is_public === true || params.data.is_public === 'true' || params.data.is_public === 1);
                const label = escapeHtml(isPublic ? cfg.t.public_3d067bed : cfg.t.not_public_20257be8);
                const cls = isPublic ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-700';
                return '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ' + cls + '">' + label + '</span>';
            },
        },
        {
            field: 'uploaded_at',
            headerName: cfg.t.upload_date_4f2a9c1e,
            width: 160,
            minWidth: 140,
            maxWidth: 200,
            filter: 'agDateColumnFilter',
            sortable: true,
            cellRenderer: AgGridRenderers.dateTime,
            cellStyle: { 'white-space': 'nowrap' },
        },
        {
            field: 'source_url_unreachable',
            headerName: cfg.t.file_url_status_2a7c9e4b || 'File URL',
            width: 170,
            minWidth: 140,
            maxWidth: 220,
            filter: 'customSetFilter',
            sortable: true,
            filterValueGetter: function (params) { return importGridSourceUrlStatusLabel(params.data || {}); },
            cellRenderer: function (params) {
                const data = params.data || {};
                if (!data.source_url_unreachable) {
                    if (data.file_pending) {
                        return '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-800"><i class="fas fa-clock mr-1"></i>' +
                            escapeHtml(cfg.t.pending_2d13df6f || '') + '</span>';
                    }
                    return '<span class="text-xs text-gray-400">\u2014</span>';
                }
                return '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800" title="' +
                    escapeAttr(cfg.t.file_url_unavailable_hint_1d6e8a3f || '') + '"><i class="fas fa-link-slash mr-1"></i>' +
                    escapeHtml(importGridSourceUrlStatusLabel(data)) + '</span>';
            },
        },
        {
            field: 'ai_processed',
            headerName: cfg.t.ai_import_eca697b5,
            width: 200,
            minWidth: 160,
            maxWidth: 260,
            filter: 'customSetFilter',
            sortable: true,
            filterValueGetter: function (params) {
                return params.data && params.data.ai_processed ? cfg.t.processed_e6f641ae : cfg.t.not_processed_0fe381df;
            },
            cellRenderer: function (params) {
                const processed = !!(params.data && params.data.ai_processed);
                const label = escapeHtml(processed ? cfg.t.processed_e6f641ae : cfg.t.not_processed_0fe381df);
                const cls = processed ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-700';
                const icon = processed ? 'fa-check-circle' : 'fa-clock';
                return '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ' + cls + '"><i class="fas ' + icon + ' mr-1"></i>' + label + '</span>';
            },
        },
    ];
}

function restoreDocumentsPageGridGlobals() {
    try {
        if (page.documentsGridApi) window.gridApi = page.documentsGridApi;
        if (page.documentsGridHelper) {
            window.gridHelper = page.documentsGridHelper;
            if (page.documentsGridHelper.columnVisibilityManager) {
                window.columnVisibilityManager = page.documentsGridHelper.columnVisibilityManager;
            }
        }
    } catch (e) { /* ignore */ }
}

function syncImportSelectionFromGrid() {
    page.selectedDocuments.clear();
    if (importDocumentsGridHelper) {
        importDocumentsGridHelper.getSelectedRows().forEach(function (row) {
            if (row && row.id != null && !row.ai_processed && !row.source_url_unreachable) {
                page.selectedDocuments.add(row.id);
            }
        });
    }
    updateImportSelectedSummary();
}

function updateImportSelectedSummary() {
    const summaryEl = document.getElementById('importSelectedSummary');
    const processBtn = document.getElementById('processSelectedBtn');
    const count = page.selectedDocuments.size;
    if (processBtn) processBtn.disabled = count === 0;
    if (summaryEl) summaryEl.textContent = formatImportFooterSummary(count);
}

function updateImportActionsVisibility(rowCount) {
    page.importTabHasRows = (Number(rowCount) || 0) > 0;
    syncUploadImportModalFooter();
    if (page.importTabHasRows) updateImportSelectedSummary();
}

function layoutImportGrid() {
    window.requestAnimationFrame(function () {
        window.requestAnimationFrame(function () {
            if (importDocumentsGridHelper && typeof importDocumentsGridHelper.setDynamicHeight === 'function') {
                try { importDocumentsGridHelper.setDynamicHeight(); } catch (e) { /* ignore */ }
            }
            if (importDocumentsGridApi && typeof importDocumentsGridApi.doLayout === 'function') {
                try { importDocumentsGridApi.doLayout(); } catch (e) { /* ignore */ }
            }
        });
    });
}

function ensureImportDocumentsGrid(rowData) {
    const loadingEl = document.getElementById('importDocumentsGrid-loading');
    const emptyEl = document.getElementById('importDocumentsGrid-empty');
    const containerEl = document.getElementById('importDocumentsGrid-container');
    if (!importDocumentsGridHelper) {
        try {
            importDocumentsGridHelper = new AgGridHelper({
                containerId: 'importDocumentsGrid',
                templateId: 'ai-import-system-docs',
                columnDefs: columnDefs(),
                rowData: rowData || [],
                options: {
                    rowSelection: { mode: 'multiRow', enableClickSelection: true, selectAll: 'filtered' },
                    isRowSelectable: function (node) {
                        const data = node && node.data;
                        return !!(data && !data.ai_processed && !data.source_url_unreachable);
                    },
                    onSelectionChanged: syncImportSelectionFromGrid,
                    paginationPageSize: 25,
                    defaultColDef: {
                        wrapText: false,
                        autoHeight: false,
                        sortable: true,
                        resizable: true,
                        cellStyle: { display: 'flex', alignItems: 'center', justifyContent: 'flex-start' },
                    },
                },
                columnVisibilityOptions: {
                    showPanelButton: true,
                    buttonPlaceholderId: 'importDocumentsGrid-colvis-placeholder',
                    enableExport: false,
                    enableReset: true,
                },
                heightOptions: {
                    useParentContainerHeight: true,
                    minHeight: 280,
                    maxHeight: 520,
                    absoluteMinHeight: 240,
                    viewportOffset: 140,
                },
            });
            importDocumentsGridApi = importDocumentsGridHelper.initialize();
            const gridEl = document.getElementById('importDocumentsGrid');
            if (gridEl && gridEl.dataset.importLinkGuard !== '1') {
                gridEl.dataset.importLinkGuard = '1';
                gridEl.addEventListener('click', function (ev) {
                    if (ev.target.closest && ev.target.closest('a.import-system-doc-filename-link')) ev.stopPropagation();
                }, true);
            }
            restoreDocumentsPageGridGlobals();
            window.importDocumentsGridApi = importDocumentsGridApi;
            window.importDocumentsGridHelper = importDocumentsGridHelper;
        } catch (e) {
            console.error('Import system documents grid init failed:', e);
            importDocumentsGridHelper = null;
            importDocumentsGridApi = null;
            if (loadingEl) loadingEl.style.display = 'none';
            if (containerEl) containerEl.style.display = 'none';
            if (emptyEl) emptyEl.style.display = 'block';
            const initErr = document.getElementById('importDocumentsFetchError');
            if (initErr) {
                initErr.textContent = cfg.t.failed_to_load_documents_94b93867 || '';
                initErr.classList.remove('hidden');
            }
            updateImportActionsVisibility(0);
            return;
        }
    } else {
        importDocumentsGridHelper.setRowData(rowData || []);
        if (importDocumentsGridApi && typeof importDocumentsGridApi.deselectAll === 'function') importDocumentsGridApi.deselectAll();
        syncImportSelectionFromGrid();
    }
    if (loadingEl) loadingEl.style.display = 'none';
    if (containerEl) containerEl.style.display = 'block';
    if (emptyEl) emptyEl.style.display = 'none';
    updateImportActionsVisibility((rowData || []).length);
    layoutImportGrid();
}

export function resizeImportDocumentsGrid() {
    layoutImportGrid();
}

export async function loadSystemDocuments() {
    const loading = document.getElementById('importLoading');
    const errEl = document.getElementById('importDocumentsFetchError');
    const searchInput = document.getElementById('importSearch');
    if (!loading) return;
    if (errEl) {
        errEl.textContent = '';
        errEl.classList.add('hidden');
    }
    loading.classList.remove('hidden');
    page.selectedDocuments.clear();
    if (importDocumentsGridApi && typeof importDocumentsGridApi.deselectAll === 'function') importDocumentsGridApi.deselectAll();
    updateImportSelectedSummary();
    try {
        const searchQuery = searchInput ? searchInput.value : '';
        const response = await ((window.getFetch && window.getFetch()) || fetch)(
            '/admin/ai/knowledge-base/list-system-documents?q=' + encodeURIComponent(searchQuery) + '&limit=5000',
            { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } }
        );
        const result = await response.json();
        const truncEl = document.getElementById('importDocumentsTruncationHint');
        if (!response.ok || !result.success) {
            if (errEl) {
                errEl.textContent = String((result && result.error) || cfg.t.error_loading_documents_a708c41e || '');
                errEl.classList.remove('hidden');
            }
            if (importDocumentsGridHelper) importDocumentsGridHelper.setRowData([]);
            if (truncEl) {
                truncEl.textContent = '';
                truncEl.classList.add('hidden');
            }
            syncImportSelectionFromGrid();
            updateImportActionsVisibility(0);
            return;
        }
        const docs = Array.isArray(result.documents) ? result.documents : [];
        const rows = docs.slice().sort(function (a, b) {
            return (a.ai_processed ? 1 : 0) - (b.ai_processed ? 1 : 0);
        }).map(mapSystemDocumentToRow).filter(Boolean);
        ensureImportDocumentsGrid(rows);
        syncImportSelectionFromGrid();
        const totalMatching = Number(result.total);
        const returned = Number.isFinite(Number(result.returned)) ? Number(result.returned) : rows.length;
        if (importDocumentsGridHelper && typeof importDocumentsGridHelper.setResultCountTotal === 'function' && Number.isFinite(totalMatching)) {
            importDocumentsGridHelper.setResultCountTotal(totalMatching);
        }
        if (truncEl) {
            if (Number.isFinite(totalMatching) && totalMatching > returned) {
                truncEl.textContent = (cfg.t.showing_count_of_total_8f3c1a2b || 'Showing {returned} of {total} matching documents. Refine search to see more.')
                    .replace('{returned}', String(returned))
                    .replace('{total}', String(totalMatching));
                truncEl.classList.remove('hidden');
            } else {
                truncEl.textContent = '';
                truncEl.classList.add('hidden');
            }
        }
    } catch (error) {
        console.error('Error loading system documents:', error);
        if (errEl) {
            errEl.textContent = cfg.t.failed_to_load_documents_94b93867 || '';
            errEl.classList.remove('hidden');
        }
        if (importDocumentsGridHelper) importDocumentsGridHelper.setRowData([]);
        syncImportSelectionFromGrid();
        updateImportActionsVisibility(0);
    } finally {
        loading.classList.add('hidden');
    }
}

async function processSelectedDocuments() {
    if (page.selectedDocuments.size === 0) {
        notifyDocs(cfg.t.please_select_at_least_one_document_db0de074, 'warning');
        return;
    }
    const docIds = Array.from(page.selectedDocuments);
    const confirmMsg = (cfg.t.process_count_document_s_with_ai_this_wi_b44c5b13 || 'Process {count} document(s) with AI?').replace('{count}', docIds.length);
    confirmAction(confirmMsg, async function () {
        const processBtn = document.getElementById('processSelectedBtn');
        const originalText = processBtn ? processBtn.innerHTML : '';
        if (processBtn) {
            processBtn.disabled = true;
            processBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>' + escapeHtml(cfg.t.processing_21d104a5 || '');
        }
        page.closeUploadModal();
        try {
            const response = await csrfFetch(importSystemBulkUrl(null), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                body: JSON.stringify({ submitted_document_ids: docIds }),
            });
            let result = null;
            try { result = await response.json(); } catch (parseError) { throw new Error('Invalid response from server'); }
            if (!response.ok || !result || !result.success || !result.job_id) {
                throw new Error((result && (result.error || result.message)) || ('HTTP ' + response.status));
            }
            startSystemImportJobPolling(result.job_id, Number(result.total) || docIds.length);
        } catch (error) {
            hideProcessingBanner();
            notifyDocs((cfg.t.failed_to_start_import_d9e1bb79 || 'Failed to start import') + ': ' + (error && error.message ? error.message : String(error)), 'error');
        } finally {
            if (processBtn) {
                processBtn.disabled = page.selectedDocuments.size === 0;
                processBtn.innerHTML = originalText;
            }
        }
    }, {
        confirmText: cfg.t.process_b6ec7abe,
        cancelText: cfg.t.cancel_ea478870,
        title: cfg.t.process_documents_056842a0,
    });
}

export function initImportSystem() {
    const processBtn = document.getElementById('processSelectedBtn');
    if (processBtn) {
        processBtn.addEventListener('click', function (e) {
            e.preventDefault();
            processSelectedDocuments();
        });
    }
    const refresh = document.getElementById('importRefreshBtn');
    if (refresh) {
        refresh.addEventListener('click', function (e) {
            e.preventDefault();
            loadSystemDocuments();
        });
    }
    const searchInput = document.getElementById('importSearch');
    if (searchInput) {
        let searchTimeout;
        searchInput.addEventListener('input', function () {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(loadSystemDocuments, 500);
        });
    }
}
