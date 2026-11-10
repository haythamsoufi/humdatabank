/**
 * Documents grid: fetch, columns, inline edits, and per-row actions.
 * The full filtered library is loaded once so AG Grid can paginate and filter
 * on the client. Geography editors stay one option until opened, so a long
 * country list is not copied into every visible row.
 */

import { annotateDuplicateRows, updateDocumentsDuplicatesBanner } from './duplicates.js';
import {
    DOCUMENT_CATEGORY_OPTIONS,
    cfg,
    confirmAction,
    escapeAttr,
    escapeHtml,
    geographyPayloadFromSelectValue,
    geographySelectValue,
    getCategoryLabel,
    getFileIcon,
    getStatusBadge,
    notifyDocs,
    page,
    removeTrackedProcessingDoc,
    scopeLabel,
    showProcessingBanner,
    startProcessingPoll,
    stopProcessingPoll,
    updateTrackedProcessingDoc,
} from './shared.js';

const DOCUMENTS_GRID_FETCH_PER_PAGE = 10000;
const documentsGridState = { gridInitialized: false };

let countryOptionsCache = null;
let countryOptionsPromise = null;
let geographyOptionsHtml = '';

export function mapDocToGridRow(doc) {
    let countries = doc.countries || [];
    if (!Array.isArray(countries)) countries = [];
    countries = countries.map(function (c) {
        if (c && typeof c === 'object') {
            return {
                id: c.id != null ? Number(c.id) : null,
                name: String(c.name || '').trim(),
                iso3: String(c.iso3 || '').trim(),
            };
        }
        return { name: String(c || '').trim(), iso3: '', id: null };
    });
    return {
        id: doc.id,
        title: doc.title || 'Untitled',
        filename: doc.filename || '',
        country_id: doc.country_id || (countries[0] && countries[0].id) || null,
        country_name: doc.country_name || '',
        country_iso3: doc.country_iso3 || '',
        geographic_scope: doc.geographic_scope || '',
        countries: countries,
        file_type: doc.file_type || '',
        processing_status: doc.processing_status || 'pending',
        processing_error: doc.processing_error || '',
        total_chunks: doc.total_chunks || 0,
        created_at: doc.created_at || null,
        is_public: doc.is_public || false,
        document_date: doc.document_date || null,
        document_language: doc.document_language || '',
        source_organization: doc.source_organization || '',
        document_category: doc.document_category || '',
        quality_score: (doc.quality_score !== null && doc.quality_score !== undefined) ? doc.quality_score : null,
        content_hash: doc.content_hash || '',
        source_url: doc.source_url || '',
        submitted_document_id: doc.submitted_document_id || null,
        guidance_document_id: doc.guidance_document_id || null,
        duplicate_group_id: doc.duplicate_group_id || null,
        duplicate_match: doc.duplicate_match || null,
        is_duplicate: !!doc.is_duplicate,
        duplicate_keeper_id: doc.duplicate_keeper_id || null,
        is_duplicate_keeper: !!doc.is_duplicate_keeper,
    };
}

function mapCountryOptions(list) {
    const rows = Array.isArray(list) ? list : [];
    return rows.map(function (c) {
        const id = c && c.id != null ? Number(c.id) : NaN;
        const name = String((c && (c.name || c.localized_name)) || '').trim();
        return {
            id: Number.isFinite(id) ? id : null,
            name: name,
            iso3: String((c && c.iso3) || '').trim(),
        };
    }).filter(function (c) { return c.id && c.name; })
        .sort(function (a, b) { return a.name.localeCompare(b.name); });
}

function rebuildGeographyOptionsHtml() {
    const options = countryOptionsCache || [];
    const scopeOpts = [
        { value: 'scope:', label: cfg.t.none_49bd59b9 },
        { value: 'scope:global', label: cfg.t.global_4cc6684d },
        { value: 'scope:regional', label: cfg.t.regional_9c1c6794 },
        { value: 'scope:cluster', label: cfg.t.cluster_249694a4 },
    ].map(function (o) {
        return '<option value="' + escapeAttr(o.value) + '">' + escapeHtml(o.label) + '</option>';
    }).join('');
    const countryOpts = options.map(function (c) {
        const label = c.iso3 ? (c.name + ' (' + c.iso3 + ')') : c.name;
        return '<option value="' + escapeAttr('country:' + c.id) + '">' + escapeHtml(label) + '</option>';
    }).join('');
    geographyOptionsHtml =
        '<optgroup label="' + escapeAttr(cfg.t.country_scope_281f8863 || '') + '">' + scopeOpts + '</optgroup>' +
        '<optgroup label="' + escapeAttr(cfg.t.countries_790d59ef || '') + '">' + countryOpts + '</optgroup>';
}

export function fillGeographySelect(sel) {
    if (!sel || sel.dataset.geoReady === '1') return;
    const selected = sel.value;
    const currentLabel = sel.selectedOptions && sel.selectedOptions[0] ? sel.selectedOptions[0].textContent : '';
    if (!geographyOptionsHtml) rebuildGeographyOptionsHtml();
    sel.innerHTML = geographyOptionsHtml;
    const known = Array.from(sel.options).some(function (opt) { return opt.value === selected; });
    if (selected && !known) {
        const extra = document.createElement('option');
        extra.value = selected;
        extra.textContent = currentLabel || selected;
        const countryGroup = sel.querySelector('optgroup:last-of-type');
        if (countryGroup && selected.indexOf('country:') === 0) countryGroup.appendChild(extra);
        else sel.appendChild(extra);
    }
    sel.value = selected;
    Array.from(sel.options).forEach(function (opt) {
        opt.defaultSelected = opt.value === selected;
    });
    sel.dataset.geoReady = '1';
}

function geographyClosedLabel(data) {
    const selected = geographySelectValue(data);
    if (selected === 'scope:' ) return cfg.t.none_49bd59b9 || '';
    if (selected.indexOf('scope:') === 0) return scopeLabel(selected.slice('scope:'.length));
    const countryId = Number(selected.slice('country:'.length));
    const cached = (countryOptionsCache || []).find(function (c) { return Number(c.id) === countryId; });
    if (cached) return cached.iso3 ? (cached.name + ' (' + cached.iso3 + ')') : cached.name;
    const name = (data && data.country_name) || String(countryId);
    const iso3 = data && data.country_iso3;
    return iso3 ? (name + ' (' + iso3 + ')') : name;
}

export function ensureCountryOptions() {
    if (countryOptionsCache) return Promise.resolve(countryOptionsCache);
    if (countryOptionsPromise) return countryOptionsPromise;
    const fetchImpl = (window.getFetch && window.getFetch()) || fetch;
    countryOptionsPromise = fetchImpl('/api/v1/countrymap', {
        method: 'GET',
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
    }).then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
    }).then(function (payload) {
        const raw = Array.isArray(payload) ? payload : (payload && payload.countries) || [];
        countryOptionsCache = mapCountryOptions(raw);
        rebuildGeographyOptionsHtml();
        if (page.documentsGridApi && typeof page.documentsGridApi.refreshCells === 'function') {
            page.documentsGridApi.refreshCells({ columns: ['country_name'], force: true });
        }
        return countryOptionsCache;
    }).catch(function (err) {
        countryOptionsPromise = null;
        if (window.__clientWarn) window.__clientWarn('Failed to load countries for editor', err);
        return [];
    });
    return countryOptionsPromise;
}

export function getRowNodeByDocId(docId) {
    const api = page.documentsGridApi;
    if (!api) return null;
    let found = null;
    api.forEachNode(function (node) {
        const nodeId = node && node.data ? node.data.id : null;
        if (nodeId != null && String(nodeId) === String(docId)) found = node;
    });
    return found;
}

export function updateDocumentInGrid(docId, patch) {
    try {
        const api = page.documentsGridApi;
        const node = getRowNodeByDocId(docId);
        if (!api || !node) return false;
        const next = Object.assign({}, node.data || {}, patch || {});
        node.setData(next);
        const cols = ['processing_status', 'total_chunks', 'is_public'];
        const p = patch || {};
        if (p.redetect_processing !== undefined || p.country_name !== undefined || p.country_iso3 !== undefined
            || p.geographic_scope !== undefined || p.country_id !== undefined || p.countries !== undefined) {
            cols.push('country_name', 'geographic_scope');
        }
        if (p.document_date !== undefined || p.document_language !== undefined || p.source_organization !== undefined
            || p.document_category !== undefined || p.quality_score !== undefined) {
            cols.push('document_date', 'document_language', 'source_organization', 'document_category', 'quality_score');
        }
        api.refreshCells({ rowNodes: [node], columns: cols, force: true });
        return true;
    } catch (e) {
        console.error('Failed updating grid row:', e);
        return false;
    }
}

export function removeDocumentFromGrid(docId) {
    try {
        const api = page.documentsGridApi;
        const node = getRowNodeByDocId(docId);
        if (!api || !node) return false;
        api.applyTransaction({ remove: [node.data] });
        return true;
    } catch (e) {
        console.error('Failed removing grid row:', e);
        return false;
    }
}

export function syncDuplicateAnnotation() {
    const api = page.documentsGridApi;
    if (!api) return;
    const rows = [];
    api.forEachNode(function (node) {
        if (node && node.data) rows.push(node.data);
    });
    const annotated = annotateDuplicateRows(rows);
    setDocumentRows(annotated, { preservePage: true });
    updateDocumentsDuplicatesBanner(annotated);
}

export async function refreshAiDocumentGridRowFromApi(docId, opts) {
    if (!page.documentsGridApi) return;
    try {
        const response = await ((window.getFetch && window.getFetch()) || fetch)(
            '/api/ai/documents/' + encodeURIComponent(docId) + '?_=' + Date.now(),
            {
                credentials: 'same-origin',
                cache: 'no-store',
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
            }
        );
        if (!response.ok) return;
        const data = await response.json();
        if (!data.success || !data.document) return;
        const node = getRowNodeByDocId(docId);
        if (!node) return;
        const prev = node.data || {};
        const next = Object.assign({}, mapDocToGridRow(data.document), {
            redetect_processing: opts && opts.clearRedetect ? false : prev.redetect_processing === true,
        });
        node.setData(next);
        page.documentsGridApi.refreshCells({ rowNodes: [node], force: true });
    } catch (e) {
        console.error('refreshAiDocumentGridRowFromApi failed:', e);
    }
}

function getDocumentsPageFilterParams() {
    const sp = new URLSearchParams(window.location.search);
    const out = new URLSearchParams();
    ['status', 'file_type', 'category', 'language', 'q'].forEach(function (key) {
        const v = (sp.get(key) || '').trim();
        if (v) out.set(key, v);
    });
    return out;
}

function CountryScopeTooltip() {}
CountryScopeTooltip.prototype.init = function (params) {
    const rawValue = params && params.value ? String(params.value) : '';
    const countries = rawValue.split('\n').map(function (item) { return item.trim(); }).filter(Boolean);
    const container = document.createElement('div');
    container.style.maxWidth = '360px';
    container.style.padding = '8px 10px';
    container.style.background = '#111827';
    container.style.color = '#ffffff';
    container.style.borderRadius = '6px';
    container.style.boxShadow = '0 8px 18px rgba(0, 0, 0, 0.25)';
    container.style.fontSize = '12px';
    container.style.lineHeight = '1.4';
    if (countries.length === 0) {
        const empty = document.createElement('div');
        empty.textContent = cfg.t.no_countries_e1ba5c60 || '';
        container.appendChild(empty);
        this.eGui = container;
        return;
    }
    const title = document.createElement('div');
    title.textContent = (cfg.t.countries_790d59ef || '') + ' (' + countries.length + ')';
    title.style.fontWeight = '600';
    title.style.marginBottom = '6px';
    container.appendChild(title);
    const list = document.createElement('ul');
    list.style.margin = '0';
    list.style.paddingLeft = '16px';
    list.style.maxHeight = '220px';
    list.style.overflowY = 'auto';
    countries.forEach(function (country) {
        const li = document.createElement('li');
        li.textContent = country;
        list.appendChild(li);
    });
    container.appendChild(list);
    this.eGui = container;
};
CountryScopeTooltip.prototype.getGui = function () { return this.eGui; };

function columnDefs() {
    return [
        {
            field: 'id',
            headerName: cfg.t.document_id_7f3a2b1c,
            width: 100,
            minWidth: 80,
            maxWidth: 130,
            filter: 'agNumberColumnFilter',
            sortable: true,
            cellRenderer: function (params) {
                const id = params.value;
                if (id == null || id === '') return '<span class="text-xs text-gray-400">—</span>';
                return '<span class="text-sm font-mono text-gray-700">' + escapeHtml(String(id)) + '</span>';
            },
            cellStyle: { 'text-align': 'center', 'white-space': 'nowrap' },
        },
        {
            field: 'title',
            headerName: cfg.t.document_09453598,
            width: 350,
            minWidth: 250,
            maxWidth: 500,
            filter: 'agTextColumnFilter',
            sortable: true,
            cellRenderer: function (params) {
                const data = params.data || {};
                const icon = getFileIcon(data.file_type);
                const downloadUrl = '/api/ai/documents/' + encodeURIComponent(data.id == null ? '' : data.id) + '/download';
                const title = escapeHtml(data.title || 'Untitled');
                const filename = escapeHtml(data.filename || '');
                let badge = '';
                if (data.is_duplicate) {
                    const isKeeper = !!data.is_duplicate_keeper;
                    const label = isKeeper
                        ? (cfg.t.duplicate_keeper_badge_3b7e1d9a || 'Keep')
                        : (cfg.t.duplicate_badge_1e9a4c2b || 'Duplicate');
                    const matchHint = data.duplicate_match === 'url' ? 'URL' : 'hash';
                    badge = '<span class="ai-doc-duplicate-badge' + (isKeeper ? ' is-keeper' : '') +
                        '" title="' + escapeAttr(matchHint) + '">' + escapeHtml(label) + '</span>';
                }
                return '<div class="flex items-center" style="height: 100%; padding: 8px 0;">' +
                    '<div class="flex-shrink-0 h-12 w-12 flex items-center justify-center bg-gray-50 rounded-lg border border-gray-200 mr-3">' +
                    icon + '</div>' +
                    '<div><div class="text-sm font-semibold text-gray-900">' +
                    '<a href="' + escapeAttr(downloadUrl) + '" class="text-blue-600 hover:text-blue-800 hover:underline" download>' +
                    title + '</a>' + badge + '</div>' +
                    '<div class="text-xs text-gray-500 mt-0.5">' + filename + '</div></div></div>';
            },
            cellStyle: { 'white-space': 'normal', 'line-height': '1.4', 'display': 'flex', 'align-items': 'center' },
        },
        {
            field: 'file_type',
            headerName: cfg.t.type_a1fa2777,
            width: 120,
            minWidth: 100,
            maxWidth: 150,
            filter: 'customSetFilter',
            sortable: true,
            cellRenderer: function (params) {
                const fileType = escapeHtml(String(params.value || '').toUpperCase());
                return '<span class="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium bg-gray-100 text-gray-700 uppercase">' +
                    fileType + '</span>';
            },
            cellStyle: { 'text-align': 'center' },
        },
        {
            field: 'country_name',
            headerName: cfg.t.country_scope_281f8863,
            width: 220,
            minWidth: 160,
            maxWidth: 360,
            filter: 'agTextColumnFilter',
            sortable: true,
            wrapText: true,
            autoHeight: true,
            tooltipComponent: 'countryScopeTooltip',
            tooltipValueGetter: function (params) {
                const data = params.data || {};
                const scope = String(data.geographic_scope || '').trim().toLowerCase();
                let countries = Array.isArray(data.countries) ? data.countries : [];
                if (!countries.length && data.country_name && (scope === 'regional' || scope === 'cluster')) {
                    countries = String(data.country_name).split(',').map(function (name) {
                        return { name: name.trim(), iso3: '' };
                    }).filter(function (c) { return c.name; });
                }
                if ((scope !== 'regional' && scope !== 'cluster') || !countries.length) return null;
                return countries.map(function (c) {
                    const name = c && c.name ? String(c.name).trim() : '';
                    const iso3 = c && c.iso3 ? String(c.iso3).trim() : '';
                    return iso3 ? (name + ' (' + iso3 + ')') : name;
                }).filter(Boolean).join('\n');
            },
            cellRenderer: function (params) {
                const data = params.data || {};
                if (data.redetect_processing) {
                    return '<span class="inline-flex items-center gap-2 text-indigo-600 text-sm">' +
                        '<span class="animate-spin inline-block w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full" aria-hidden="true"></span>' +
                        '<span>' + escapeHtml(cfg.t.redetecting_aa72bb32 || '') + '</span></span>';
                }
                const selected = geographySelectValue(data);
                const title = cfg.t.click_to_change_country_or_scope_39b04e99 || '';
                return '<select class="ai-doc-geography-select text-xs border-0 bg-transparent focus:ring-1 focus:ring-blue-400 rounded cursor-pointer w-full py-0.5 font-medium text-gray-800" ' +
                    'data-ai-doc-action="change-geography" data-doc-id="' + escapeAttr(String(data.id || '')) + '" ' +
                    'data-geo-ready="0" title="' + escapeAttr(title) + '">' +
                    '<option value="' + escapeAttr(selected) + '" selected>' + escapeHtml(geographyClosedLabel(data)) + '</option>' +
                    '</select>';
            },
            valueGetter: function (params) {
                const data = params.data || {};
                const scope = String(data.geographic_scope || '').trim().toLowerCase();
                const countries = Array.isArray(data.countries) ? data.countries : [];
                if (scope === 'global' || scope === 'regional' || scope === 'cluster') return scopeLabel(scope);
                if (countries.length > 1) return countries.map(function (c) { return c.name; }).join(', ');
                return data.country_name || '';
            },
            cellStyle: {
                display: 'flex',
                'white-space': 'normal',
                'line-height': '1.4',
                'align-items': 'flex-start',
                'padding-top': '6px',
                'padding-bottom': '6px',
            },
        },
        {
            field: 'is_public',
            headerName: cfg.t.public_3d067bed,
            width: 100,
            minWidth: 90,
            maxWidth: 120,
            filter: 'agTextColumnFilter',
            sortable: true,
            cellRenderer: function (params) {
                const data = params.data || {};
                const isPublic = data.is_public === true || data.is_public === 'true' || data.is_public === 1;
                const label = isPublic ? cfg.t.public_3d067bed : cfg.t.not_public_20257be8;
                const titleAttr = isPublic ? cfg.t.click_to_make_not_public_1466b6c5 : cfg.t.click_to_make_public_f00ad0b7;
                const btnClass = 'status-label status-label--' + (isPublic ? 'success' : 'neutral') +
                    ' cursor-pointer hover:opacity-90 transition-opacity border-0';
                return '<button type="button" class="' + btnClass + '" data-ai-doc-action="toggle-public" data-doc-id="' +
                    escapeAttr(String(data.id || '')) + '" data-is-public="' + (isPublic ? 'true' : 'false') +
                    '" title="' + escapeAttr(titleAttr || '') + '">' + escapeHtml(label || '') + '</button>';
            },
            valueGetter: function (params) {
                const v = params.data && params.data.is_public;
                return v === true || v === 'true' || v === 1;
            },
            filterValueGetter: function (params) {
                const v = params.data && params.data.is_public;
                const isPublic = v === true || v === 'true' || v === 1;
                return isPublic ? cfg.t.public_3d067bed : cfg.t.not_public_20257be8;
            },
            cellStyle: { 'text-align': 'center', 'white-space': 'nowrap' },
        },
        {
            field: 'processing_status',
            headerName: cfg.t.status_ec53a8c4,
            width: 150,
            minWidth: 120,
            maxWidth: 200,
            filter: 'customSetFilter',
            sortable: true,
            cellRenderer: function (params) {
                const data = params && params.data ? params.data : {};
                return getStatusBadge(params && params.value, data.processing_error);
            },
            cellStyle: { 'text-align': 'center', 'white-space': 'nowrap' },
        },
        {
            field: 'total_chunks',
            headerName: cfg.t.chunks_58fce280,
            width: 120,
            minWidth: 100,
            maxWidth: 150,
            filter: 'agNumberColumnFilter',
            sortable: true,
            cellRenderer: function (params) {
                return '<span class="text-sm font-medium text-gray-900">' + escapeHtml(String(params.value || 0)) + '</span>';
            },
            cellStyle: { 'text-align': 'center' },
        },
        {
            field: 'created_at',
            headerName: cfg.t.created_0eceeb45,
            width: 180,
            minWidth: 150,
            maxWidth: 250,
            filter: 'agDateColumnFilter',
            sortable: true,
            cellRenderer: AgGridRenderers.dateTime,
            cellStyle: { 'white-space': 'nowrap' },
        },
        {
            field: 'document_date',
            headerName: cfg.t.doc_date_8c62d999,
            width: 140,
            minWidth: 110,
            maxWidth: 180,
            filter: 'agDateColumnFilter',
            sortable: true,
            cellRenderer: function (params) {
                const v = params.value;
                if (!v) return '<span class="text-xs text-gray-400">—</span>';
                return '<span class="text-sm text-gray-700">' + escapeHtml(String(v).substring(0, 10)) + '</span>';
            },
            cellStyle: { 'white-space': 'nowrap' },
        },
        {
            field: 'document_language',
            headerName: cfg.t.language_4994a8ff,
            width: 110,
            minWidth: 90,
            maxWidth: 140,
            filter: 'customSetFilter',
            sortable: true,
            cellRenderer: function (params) {
                const v = String(params.value || '').toUpperCase();
                if (!v) return '<span class="text-xs text-gray-400">—</span>';
                return '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-indigo-50 text-indigo-700">' + escapeHtml(v) + '</span>';
            },
            cellStyle: { 'text-align': 'center' },
        },
        {
            field: 'source_organization',
            headerName: cfg.t.source_org_83a6d807,
            width: 160,
            minWidth: 120,
            maxWidth: 220,
            filter: 'agTextColumnFilter',
            sortable: true,
            cellRenderer: function (params) {
                const v = params.value || '';
                if (!v) return '<span class="text-xs text-gray-400">—</span>';
                const short = v.length > 40 ? v.substring(0, 37) + '…' : v;
                return '<span class="text-sm text-gray-700" title="' + escapeAttr(v) + '">' + escapeHtml(short) + '</span>';
            },
            cellStyle: { 'white-space': 'nowrap', overflow: 'hidden', 'text-overflow': 'ellipsis' },
        },
        {
            field: 'document_category',
            headerName: cfg.t.category_3adbdb3a,
            width: 160,
            minWidth: 130,
            maxWidth: 200,
            filter: 'customSetFilter',
            sortable: true,
            cellRenderer: function (params) {
                const data = params.data || {};
                const v = params.value || '';
                const opts = DOCUMENT_CATEGORY_OPTIONS.map(function (o) {
                    return '<option value="' + escapeAttr(o.value) + '"' + (o.value === v ? ' selected' : '') + '>' + escapeHtml(o.label) + '</option>';
                }).join('');
                return '<select class="ai-doc-category-select text-xs border-0 bg-transparent focus:ring-1 focus:ring-blue-400 rounded cursor-pointer w-full py-0.5 text-emerald-700 font-medium" ' +
                    'data-ai-doc-action="change-category" data-doc-id="' + escapeAttr(String(data.id || '')) + '" ' +
                    'title="' + escapeAttr(cfg.t.click_to_change_category_a21f96b3 || '') + '">' + opts + '</select>';
            },
            filterValueGetter: function (params) {
                return getCategoryLabel(params.data && params.data.document_category);
            },
            cellStyle: { 'text-align': 'center', padding: '2px 4px' },
        },
        {
            field: 'quality_score',
            headerName: cfg.t.quality_571094bb,
            width: 110,
            minWidth: 90,
            maxWidth: 130,
            filter: 'agNumberColumnFilter',
            sortable: true,
            cellRenderer: function (params) {
                const v = params.value;
                if (v == null || v === '') return '<span class="text-xs text-gray-400">—</span>';
                const pct = Math.round(Number(v) * 100);
                const color = pct >= 80 ? 'text-green-700 bg-green-50' : pct >= 50 ? 'text-yellow-700 bg-yellow-50' : 'text-red-700 bg-red-50';
                return '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold ' + color + '">' + escapeHtml(String(pct)) + '%</span>';
            },
            cellStyle: { 'text-align': 'center' },
        },
    ];
}

function gridPageIndex() {
    const api = page.documentsGridApi;
    if (api && typeof api.paginationGetCurrentPage === 'function') return api.paginationGetCurrentPage() || 0;
    return 0;
}

function restoreGridPage(pageIndex) {
    const api = page.documentsGridApi;
    if (!api || !pageIndex || typeof api.paginationGoToPage !== 'function') return;
    const total = typeof api.paginationGetTotalPages === 'function' ? api.paginationGetTotalPages() : 1;
    api.paginationGoToPage(Math.min(pageIndex, Math.max(0, total - 1)));
}

function setDocumentRows(rows, options) {
    const preserve = options && options.preservePage;
    const pageIndex = preserve ? gridPageIndex() : 0;
    if (documentsGridState.gridInitialized && page.documentsGridHelper) {
        page.documentsGridHelper.setRowData(rows);
        if (preserve) {
            restoreGridPage(pageIndex);
            window.requestAnimationFrame(function () { restoreGridPage(pageIndex); });
        }
        return;
    }
    documentsGridState.gridInitialized = true;
    page.documentsGridHelper = new AgGridHelper({
        containerId: 'documentsGrid',
        templateId: 'ai-documents',
        columnDefs: columnDefs(),
        rowData: rows,
        options: {
            tooltipShowDelay: 200,
            tooltipHideDelay: 12000,
            components: { countryScopeTooltip: CountryScopeTooltip },
            getRowClass: function (params) {
                const data = params && params.data;
                if (!data || !data.is_duplicate) return '';
                return data.is_duplicate_keeper
                    ? 'ai-doc-row-duplicate ai-doc-row-duplicate-keeper'
                    : 'ai-doc-row-duplicate';
            },
        },
        columnVisibilityOptions: { enableExport: false, enableReset: true },
    });
    page.documentsGridApi = page.documentsGridHelper.initialize();
    window.documentsGridApi = page.documentsGridApi;
    window.documentsGridHelper = page.documentsGridHelper;
}

function getDocumentsGridListUrl() {
    return (cfg.urls && cfg.urls.documentsList) || '/api/ai/documents/';
}

async function fetchDocumentsGridPageFromApi(pageNumber, perPage) {
    const sp = getDocumentsPageFilterParams();
    sp.set('page', String(pageNumber));
    sp.set('per_page', String(perPage));
    let base = getDocumentsGridListUrl();
    if (base.indexOf('?') !== -1) base = base.split('?')[0];
    const response = await ((window.getFetch && window.getFetch()) || fetch)(base + '?' + sp.toString(), {
        credentials: 'same-origin',
        headers: { Accept: 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    });
    const data = await response.json();
    if (!response.ok || !data || data.success !== true || !Array.isArray(data.documents)) {
        throw new Error((data && data.error) || cfg.t.load_documents_error_2d8f4b1a || 'Could not load documents.');
    }
    return data;
}

async function fetchAllDocumentsForGrid() {
    const first = await fetchDocumentsGridPageFromApi(1, DOCUMENTS_GRID_FETCH_PER_PAGE);
    let documents = (first.documents || []).slice();
    const total = first.total != null ? first.total : documents.length;
    const pages = first.pages != null ? first.pages : 1;
    for (let pageNumber = 2; pageNumber <= pages; pageNumber++) {
        const next = await fetchDocumentsGridPageFromApi(pageNumber, DOCUMENTS_GRID_FETCH_PER_PAGE);
        documents = documents.concat(next.documents || []);
    }
    if (total > documents.length) {
        console.warn('documents grid: fetched', documents.length, 'of', total, 'rows');
    }
    return annotateDuplicateRows(documents.map(mapDocToGridRow));
}

export async function loadDocumentsGrid() {
    const loadingEl = document.getElementById('documentsGrid-loading');
    const emptyEl = document.getElementById('documentsGrid-empty');
    const containerEl = document.getElementById('documentsGrid-container');
    if (loadingEl) loadingEl.style.display = 'flex';
    try {
        const rows = await fetchAllDocumentsForGrid();
        setDocumentRows(rows, { preservePage: documentsGridState.gridInitialized });
        ensureCountryOptions();
        updateDocumentsDuplicatesBanner(rows);
        if (loadingEl) loadingEl.style.display = 'none';
        if (rows.length > 0) {
            if (containerEl) containerEl.style.display = 'block';
            if (emptyEl) emptyEl.style.display = 'none';
        } else {
            if (containerEl) containerEl.style.display = 'none';
            if (emptyEl) emptyEl.style.display = 'block';
        }
    } catch (err) {
        console.error('loadDocumentsGrid failed:', err);
        updateDocumentsDuplicatesBanner([]);
        if (loadingEl) loadingEl.style.display = 'none';
        if (containerEl) containerEl.style.display = 'none';
        if (emptyEl) {
            const safeErrorMsg = escapeHtml((err && err.message) || cfg.t.load_documents_error_2d8f4b1a || 'Could not load documents.');
            emptyEl.innerHTML = '<i class="fas fa-exclamation-triangle text-5xl text-red-300 mb-4"></i><p class="text-red-600 font-medium mb-1">' +
                escapeHtml(cfg.t.error_3d9f514d || 'Error:') + '</p><p class="text-sm text-gray-500">' + safeErrorMsg + '</p>';
            emptyEl.style.display = 'block';
        }
    }
}

export function reloadDocumentsGrid() {
    return loadDocumentsGrid();
}

function selectedOptionDefault(sel) {
    for (let i = 0; i < sel.options.length; i++) {
        if (sel.options[i].defaultSelected) return sel.options[i].value;
    }
    return '';
}

function markSelectedDefault(sel, value) {
    for (let i = 0; i < sel.options.length; i++) {
        sel.options[i].defaultSelected = sel.options[i].value === value;
    }
}

async function toggleDocumentPublic(docId, actionBtn) {
    const currentVal = actionBtn.getAttribute('data-is-public') === 'true';
    const newVal = !currentVal;
    actionBtn.disabled = true;
    try {
        const response = await csrfFetch('/api/ai/documents/' + docId, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
            body: JSON.stringify({ is_public: newVal }),
        });
        const result = await response.json();
        if (!response.ok || !result.success) {
            notifyDocs((result && result.error) ? result.error : cfg.t.failed_to_update_0ff78b34, 'error');
            return;
        }
        updateDocumentInGrid(docId, { is_public: newVal });
    } catch (err) {
        notifyDocs(err && err.message ? err.message : cfg.t.failed_to_update_0ff78b34, 'error');
    } finally {
        actionBtn.disabled = false;
    }
}

async function saveDocumentCategory(sel) {
    const docId = sel.getAttribute('data-doc-id');
    if (!docId) return;
    const newCat = sel.value;
    const prevCat = selectedOptionDefault(sel);
    sel.disabled = true;
    try {
        const response = await csrfFetch('/api/ai/documents/' + docId, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
            body: JSON.stringify({ document_category: newCat }),
        });
        const result = await response.json();
        if (!response.ok || !result.success) {
            sel.value = prevCat;
            notifyDocs((result && result.error) ? result.error : cfg.t.failed_to_update_category_e480510f, 'error');
            return;
        }
        markSelectedDefault(sel, newCat);
        updateDocumentInGrid(docId, { document_category: newCat });
    } catch (err) {
        sel.value = prevCat;
        notifyDocs(err && err.message ? err.message : cfg.t.failed_to_update_category_e480510f, 'error');
    } finally {
        sel.disabled = false;
    }
}

async function saveDocumentGeography(sel) {
    const docId = sel.getAttribute('data-doc-id');
    if (!docId) return;
    const prev = selectedOptionDefault(sel);
    if (sel.value === prev) return;
    sel.disabled = true;
    try {
        const response = await csrfFetch('/api/ai/documents/' + docId, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
            body: JSON.stringify(geographyPayloadFromSelectValue(sel.value)),
        });
        const result = await response.json();
        if (!response.ok || !result.success) {
            sel.value = prev;
            notifyDocs((result && result.error) ? result.error : cfg.t.failed_to_update_country_or_scope_d89f7be8, 'error');
            return;
        }
        markSelectedDefault(sel, sel.value);
        if (result.document) {
            const mapped = mapDocToGridRow(result.document);
            updateDocumentInGrid(docId, {
                country_id: mapped.country_id,
                country_name: mapped.country_name,
                country_iso3: mapped.country_iso3,
                geographic_scope: mapped.geographic_scope,
                countries: mapped.countries,
            });
        }
    } catch (err) {
        sel.value = prev;
        notifyDocs(err && err.message ? err.message : cfg.t.failed_to_update_country_or_scope_d89f7be8, 'error');
    } finally {
        sel.disabled = false;
    }
}

async function deleteDocument(id, title) {
    const safeTitle = String(title || '').replace(/\s+/g, ' ').trim();
    const confirmMsg = (cfg.t.delete_document_137e0e00 || 'Delete document') + ' "' + safeTitle + '"?';
    confirmAction(confirmMsg, async function () {
        const response = await csrfFetch('/admin/ai/knowledge-base/' + id + '/delete', {
            method: 'POST',
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
        });
        const result = await response.json();
        if (!response.ok || !result.success) {
            throw new Error((result && result.error) || cfg.t.failed_to_delete_document_94ab7a09 || 'Failed to delete document');
        }
        stopProcessingPoll(id);
        removeTrackedProcessingDoc(id);
        removeDocumentFromGrid(id);
        syncDuplicateAnnotation();
        notifyDocs(cfg.t.document_deleted_369422de || 'Document deleted', 'success');
    }, {
        danger: true,
        confirmText: cfg.t.delete_f2a6c498,
        cancelText: cfg.t.cancel_ea478870,
        title: cfg.t.delete_document_616cd122,
    });
}

async function reprocessDocument(id) {
    const confirmMsg = cfg.t.reprocess_this_document_6e5046e8 || 'Reprocess this document?';
    confirmAction(confirmMsg, async function () {
        updateDocumentInGrid(id, { processing_status: 'pending', processing_error: '' });
        const requestTs = Date.now();
        updateTrackedProcessingDoc(id, {
            resetProgress: true,
            status: 'pending',
            stage: cfg.t.starting_8c6ce9f8,
            progress: 0,
            reprocessRequestedAt: requestTs,
            seenNonCompletedSinceRequest: false,
        });
        showProcessingBanner(cfg.t.reprocessing_started_5259d906, cfg.t.preparing_0862f67f, 0);
        startProcessingPoll(id);
        try {
            const response = await csrfFetch('/admin/ai/knowledge-base/' + id + '/reprocess', {
                method: 'POST',
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
            });
            const result = await response.json();
            if (response.status === 202 || result.success) return;
            updateDocumentInGrid(id, { processing_status: 'failed', processing_error: result.error || '' });
            updateTrackedProcessingDoc(id, { status: 'failed', stage: 'Failed', progress: 100, error: result.error || '' });
            stopProcessingPoll(id);
            notifyDocs((cfg.t.error_3d9f514d || 'Error') + ' ' + (result.error || ''), 'error');
        } catch (error) {
            console.error('Reprocess request error (polling continues):', error);
        }
    }, {
        confirmText: cfg.t.reprocess_3f20034f,
        cancelText: cfg.t.cancel_ea478870,
        title: cfg.t.reprocess_document_f2729c9f,
    });
}

function bindRowActions() {
    document.addEventListener('pointerdown', function (e) {
        const sel = e.target && e.target.closest
            ? e.target.closest('select[data-ai-doc-action="change-geography"]')
            : null;
        if (!sel) return;
        fillGeographySelect(sel);
    }, true);

    document.addEventListener('click', function (e) {
        const actionBtn = e.target && e.target.closest ? e.target.closest('[data-ai-doc-action]') : null;
        if (!actionBtn || actionBtn.tagName === 'SELECT') return;
        const action = actionBtn.getAttribute('data-ai-doc-action');
        if (action !== 'delete' && action !== 'reprocess' && action !== 'toggle-public') return;
        e.preventDefault();
        e.stopPropagation();
        const docId = parseInt(actionBtn.getAttribute('data-doc-id') || '0', 10);
        if (!docId) return;
        if (action === 'delete') deleteDocument(docId, actionBtn.getAttribute('data-doc-title') || 'Untitled');
        else if (action === 'reprocess') reprocessDocument(docId);
        else toggleDocumentPublic(docId, actionBtn);
    });

    document.addEventListener('change', function (e) {
        const category = e.target && e.target.closest
            ? e.target.closest('select[data-ai-doc-action="change-category"]')
            : null;
        if (category) {
            saveDocumentCategory(category);
            return;
        }
        const geography = e.target && e.target.closest
            ? e.target.closest('select[data-ai-doc-action="change-geography"]')
            : null;
        if (geography) saveDocumentGeography(geography);
    });
}

export function initDocumentsGrid() {
    bindRowActions();
    loadDocumentsGrid();
}
