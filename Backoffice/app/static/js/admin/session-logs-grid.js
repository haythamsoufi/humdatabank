/**
 * Admin Session Logs — AG Grid (loads rows from /admin/api/analytics/session-logs).
 */
(function() {
    'use strict';

    function esc(s) {
        if (s === null || s === undefined) return '';
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function getCsrfToken() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    function mapRow(item) {
        var u = item.user;
        return Object.assign({}, item, {
            user_id: u ? u.id : null,
            user_name: u ? (u.name || u.email || '') : '',
            user_email: u ? (u.email || '') : ''
        });
    }

    var PATH_COUNT_OTHER_KEY = '_other';

    /**
     * Sorted [{ path, count }] from session page_view_path_counts (descending by count).
     */
    function sortPathCountEntries(pvc) {
        if (!pvc || typeof pvc !== 'object') return [];
        var keys = Object.keys(pvc);
        var out = [];
        for (var i = 0; i < keys.length; i++) {
            var k = keys[i];
            var n = parseInt(pvc[k], 10);
            if (isNaN(n)) n = 0;
            out.push({ path: k, count: n });
        }
        out.sort(function(a, b) {
            return b.count - a.count || String(a.path).localeCompare(String(b.path));
        });
        return out;
    }

    function ensurePathBreakdownModal() {
        var id = 'session-logs-path-breakdown-modal';
        var el = document.getElementById(id);
        if (el) return el;
        el = document.createElement('div');
        el.id = id;
        el.className = 'fixed inset-0 z-50 hidden';
        el.setAttribute('role', 'dialog');
        el.setAttribute('aria-modal', 'true');
        el.innerHTML =
            '<div class="absolute inset-0 bg-black opacity-50" data-path-modal-backdrop></div>' +
            '<div class="relative z-10 flex min-h-full items-center justify-center p-4 pointer-events-none">' +
            '<div class="pointer-events-auto bg-white border border-gray-200 shadow-xl max-w-lg w-full max-h-[85vh] flex flex-col rounded-none">' +
            '<div class="px-4 py-3 border-b border-gray-200 flex justify-between items-center gap-3 shrink-0">' +
            '<h2 id="session-path-modal-title" class="text-base font-semibold text-gray-900 min-w-0"></h2>' +
            '<button type="button" class="btn btn-secondary btn-sm" data-path-modal-close>' +
            '<i class="fas fa-times mr-1" aria-hidden="true"></i><span data-path-modal-close-label></span>' +
            '</button></div>' +
            '<div id="session-path-modal-body" class="overflow-y-auto p-4 text-sm text-gray-800"></div>' +
            '</div></div>';
        document.body.appendChild(el);
        function closeModal() {
            el.classList.add('hidden');
            document.removeEventListener('keydown', onKey);
        }
        function onKey(ev) {
            if (ev.key === 'Escape') closeModal();
        }
        el.addEventListener('click', function(ev) {
            if (ev.target && ev.target.getAttribute && ev.target.getAttribute('data-path-modal-backdrop') !== null) {
                closeModal();
            }
            if (ev.target && ev.target.closest && ev.target.closest('[data-path-modal-close]')) {
                closeModal();
            }
        });
        el._openPathModal = function() {
            el.classList.remove('hidden');
            document.addEventListener('keydown', onKey);
        };
        el._closePathModal = closeModal;
        return el;
    }

    function openPathBreakdownModal(t, pvc, pageViewsTotal, sessionId) {
        var modal = ensurePathBreakdownModal();
        var titleEl = modal.querySelector('#session-path-modal-title');
        var bodyEl = modal.querySelector('#session-path-modal-body');
        var closeLbl = modal.querySelector('[data-path-modal-close-label]');
        if (closeLbl) closeLbl.textContent = t.close || 'Close';
        var title = (t.pathBreakdownTitle || 'Page views by path');
        if (sessionId) {
            var sidStr = String(sessionId);
            title += ' — ' + (sidStr.length > 24 ? sidStr.substring(0, 24) + '…' : sidStr);
        }
        if (titleEl) titleEl.textContent = title;

        var rows = sortPathCountEntries(pvc);
        var otherLabel = t.pathBucketOther || 'Other paths (aggregated)';
        if (!bodyEl) return;

        if (rows.length === 0) {
            var empty = t.pathBreakdownEmpty || 'No path breakdown recorded for this session.';
            if ((pageViewsTotal || 0) > 0) {
                bodyEl.innerHTML = '<p class="text-gray-600">' + esc(empty) + '</p>' +
                    '<p class="text-xs text-gray-500 mt-2">' + esc(t.pageViews || 'Page views') + ': ' + esc(String(pageViewsTotal)) + '</p>';
            } else {
                bodyEl.innerHTML = '<p class="text-gray-600">' + esc(empty) + '</p>';
            }
        } else {
            var buf = '<table class="w-full border-collapse text-xs"><thead><tr class="border-b border-gray-200 text-left text-gray-600">' +
                '<th class="py-2 pr-2 font-semibold">' + esc(t.pathColumn || 'Path') + '</th>' +
                '<th class="py-2 pl-2 font-semibold w-20 text-right">' + esc(t.viewCount || 'Count') + '</th></tr></thead><tbody>';
            for (var r = 0; r < rows.length; r++) {
                var row = rows[r];
                var pathLabel = row.path === PATH_COUNT_OTHER_KEY ? otherLabel : String(row.path);
                buf += '<tr class="border-b border-gray-100"><td class="py-1.5 pr-2 font-mono break-all">' + esc(pathLabel) +
                    '</td><td class="py-1.5 pl-2 text-right tabular-nums">' + esc(String(row.count)) + '</td></tr>';
            }
            buf += '</tbody></table>';
            bodyEl.innerHTML = buf;
        }
        if (modal._openPathModal) modal._openPathModal();
    }

    /**
     * Drill to audit trail: session_id + optional activity_type.
     * Omit activityType to use default Activity Type behaviour (exclude page views until user applies filters).
     */
    function sessionAuditHref(config, sessionId, activityType) {
        var base = (config && config.auditTrailUrl) || '/admin/analytics/audit-trail';
        try {
            var u = new URL(base, window.location.origin);
            u.searchParams.set('session_id', sessionId);
            if (activityType) {
                u.searchParams.set('activity_type', activityType);
            }
            return u.pathname + u.search + u.hash;
        } catch (e) {
            var q = 'session_id=' + encodeURIComponent(sessionId);
            if (activityType) {
                q += '&activity_type=' + encodeURIComponent(activityType);
            }
            return base + (base.indexOf('?') === -1 ? '?' : '&') + q;
        }
    }

    /** Canonical left-to-right order; ID column must stay before User (localStorage may restore old order). */
    var SESSION_LOGS_COLUMN_ORDER = [
        'session_log_id',
        'user_display',
        'device_type',
        'operating_system',
        'session_start',
        'duration_minutes',
        'active_duration_minutes',
        'page_views',
        'distinct_page_view_paths',
        'activity_count',
        'is_active',
        'last_activity',
        'ip_address',
        'actions'
    ];

    function applySessionLogsColumnOrder(api) {
        if (!api || typeof AgGridHelper === 'undefined' || typeof AgGridHelper.pinActionsColumn !== 'function') {
            return;
        }
        try {
            AgGridHelper.pinActionsColumn(api, SESSION_LOGS_COLUMN_ORDER);
        } catch (e) {
            if (window.__clientWarn) window.__clientWarn('session logs column order', e);
        }
    }

    function buildColumnDefs(t, config) {
        config = config || {};
        return [
            {
                field: 'session_log_id',
                headerName: t.shortSessionId || 'ID',
                width: 110,
                minWidth: 88,
                maxWidth: 140,
                filter: 'agNumberColumnFilter',
                sortable: true,
                cellClass: 'text-xs text-gray-800 tabular-nums',
                valueFormatter: function(p) {
                    if (p.value === null || p.value === undefined) return '—';
                    return String(p.value);
                }
            },
            {
                colId: 'user_display',
                headerName: t.user || 'User',
                flex: 1.2,
                minWidth: 280,
                filter: 'agTextColumnFilter',
                sortable: true,
                valueGetter: function(p) {
                    var d = p.data || {};
                    return [d.user_name, d.user_email].filter(Boolean).join(' ');
                },
                cellRenderer: function(params) {
                    var d = params.data || {};
                    var cls = String(d.device_icon_classes || 'fas fa-laptop text-gray-500')
                        .replace(/[<"']/g, '');
                    var tip = esc(d.operating_system || d.device_type || '');
                    var icon = '<i class="' + cls + '" style="flex-shrink:0;width:1.25rem;text-align:center;line-height:1;" title="' +
                        esc(tip) + '" aria-hidden="true"></i>';
                    if (typeof AgGridRenderers !== 'undefined' && AgGridRenderers.userHoverCellWithDeviceIcon) {
                        return AgGridRenderers.userHoverCellWithDeviceIcon(params, {
                            idField: 'user_id',
                            nameField: 'user_name',
                            emailField: 'user_email',
                            fallbackLabel: t.unknownUser || 'Unknown User'
                        }, icon);
                    }
                    return '<span class="text-sm text-gray-500">' + esc(t.unknownUser || 'Unknown User') + '</span>';
                }
            },
            {
                field: 'device_type',
                headerName: t.deviceType || 'Device',
                width: 120,
                minWidth: 100,
                filter: 'agTextColumnFilter',
                sortable: true,
                valueFormatter: function(p) { return p.value || '—'; }
            },
            {
                field: 'operating_system',
                headerName: t.operatingSystem || 'OS',
                width: 160,
                minWidth: 120,
                filter: 'agTextColumnFilter',
                sortable: true,
                hide: true,
                valueFormatter: function(p) { return p.value || '—'; }
            },
            {
                field: 'session_start',
                headerName: t.sessionStart || 'Session Start',
                width: 180,
                minWidth: 150,
                filter: 'agTextColumnFilter',
                sortable: true,
                cellRenderer: typeof AgGridRenderers !== 'undefined' ? AgGridRenderers.dateTime : undefined
            },
            {
                field: 'duration_minutes',
                headerName: t.duration || 'Session length',
                width: 120,
                minWidth: 100,
                filter: 'agNumberColumnFilter',
                sortable: true,
                cellRenderer: function(params) {
                    var v = params.data && params.data.duration_minutes;
                    if (v === null || v === undefined) {
                        return '<span class="text-sm text-gray-400">-</span>';
                    }
                    return '<span class="px-2 inline-flex items-center text-xs leading-5 font-semibold rounded-full bg-blue-100 text-blue-800">' +
                        esc(v) + ' ' + (t.minutesShort || 'min') + '</span>';
                }
            },
            {
                field: 'active_duration_minutes',
                headerName: t.activeDuration || 'Active time',
                width: 120,
                minWidth: 100,
                filter: 'agNumberColumnFilter',
                sortable: true,
                cellRenderer: function(params) {
                    var v = params.data && params.data.active_duration_minutes;
                    if (v === null || v === undefined) {
                        return '<span class="text-sm text-gray-400">-</span>';
                    }
                    return '<span class="px-2 inline-flex items-center text-xs leading-5 font-semibold rounded-full bg-slate-100 text-slate-800">' +
                        esc(v) + ' ' + (t.minutesShort || 'min') + '</span>';
                }
            },
            {
                field: 'page_views',
                headerName: t.pageViews || 'Page Views',
                width: 140,
                minWidth: 100,
                filter: 'agNumberColumnFilter',
                sortable: true,
                cellRenderer: function(params) {
                    var v = params.value != null ? params.value : 0;
                    var sid = params.data && params.data.session_id;
                    var pvc = (params.data && params.data.page_view_path_counts) || {};
                    if (typeof pvc !== 'object' || pvc === null) pvc = {};
                    var enc = '';
                    try {
                        enc = encodeURIComponent(JSON.stringify(pvc));
                    } catch (e0) {
                        enc = encodeURIComponent('{}');
                    }
                    var showBtn = (v > 0) || Object.keys(pvc).length > 0;
                    var badge = '<span class="px-2 inline-flex items-center text-xs leading-5 font-semibold rounded-full bg-gray-100 text-gray-800">' +
                        esc(v) + '</span>';
                    if (showBtn) {
                        var tip = esc(t.viewPathBreakdown || 'View path breakdown');
                        badge += '<button type="button" class="ml-1.5 inline-flex items-center justify-center session-path-breakdown-btn text-teal-700 hover:text-teal-900 p-0.5 border-0 bg-transparent cursor-pointer" ' +
                            'title="' + tip + '" aria-label="' + tip + '" data-path-counts="' + enc + '" data-page-views-total="' + esc(String(v)) + '" data-session-id="' + esc(sid || '') + '">' +
                            '<i class="fas fa-route text-xs" aria-hidden="true"></i></button>';
                    }
                    return '<span class="inline-flex items-center">' + badge + '</span>';
                }
            },
            {
                field: 'distinct_page_view_paths',
                headerName: t.distinctPaths || 'Distinct paths',
                width: 130,
                minWidth: 100,
                filter: 'agNumberColumnFilter',
                sortable: true,
                cellRenderer: function(params) {
                    var v = params.value != null ? params.value : 0;
                    return '<span class="px-2 inline-flex items-center text-xs leading-5 font-semibold rounded-full bg-slate-100 text-slate-800">' +
                        esc(v) + '</span>';
                }
            },
            {
                field: 'activity_count',
                headerName: t.activities || 'Activities',
                width: 140,
                minWidth: 100,
                filter: 'agNumberColumnFilter',
                sortable: true,
                cellRenderer: function(params) {
                    var v = params.value != null ? params.value : 0;
                    var sid = params.data && params.data.session_id;
                    var badge = '<span class="px-2 inline-flex items-center text-xs leading-5 font-semibold rounded-full bg-indigo-100 text-indigo-800">' +
                        esc(v) + '</span>';
                    if (sid && config.auditTrailUrl) {
                        var href = sessionAuditHref(config, String(sid), null);
                        var title = esc(t.openActivitiesInAudit || 'Audit trail');
                        badge += '<a href="' + esc(href) + '" class="ml-1.5 inline-flex text-teal-700 hover:text-teal-900" title="' + title +
                            '" aria-label="' + title + '"><i class="fas fa-list-ul text-xs"></i></a>';
                    }
                    return '<span class="inline-flex items-center">' + badge + '</span>';
                }
            },
            {
                field: 'is_active',
                headerName: t.status || 'Status',
                width: 130,
                minWidth: 110,
                filter: 'customSetFilter',
                sortable: true,
                cellRenderer: function(params) {
                    if (params.data && params.data.is_active) {
                        return '<span class="px-2 inline-flex items-center text-xs leading-5 font-semibold rounded-full bg-green-100 text-green-800">' +
                            '<i class="fas fa-circle text-green-500 mr-1 animate-pulse" style="line-height:1"></i>' +
                            esc(t.active || 'Active') + '</span>';
                    }
                    return '<span class="px-2 inline-flex items-center text-xs leading-5 font-semibold rounded-full bg-gray-100 text-gray-800">' +
                        esc(t.ended || 'Ended') + '</span>';
                }
            },
            {
                field: 'last_activity',
                headerName: t.lastActivity || 'Last Activity',
                width: 180,
                minWidth: 150,
                filter: 'agTextColumnFilter',
                sortable: true,
                cellRenderer: function(params) {
                    if (!params.value) {
                        return '<span class="text-sm text-gray-500">' + esc(t.noActivity || 'No activity') + '</span>';
                    }
                    return typeof AgGridRenderers !== 'undefined'
                        ? AgGridRenderers.dateTime(params)
                        : esc(params.value);
                }
            },
            {
                field: 'ip_address',
                headerName: t.ipAddress || 'IP',
                width: 130,
                minWidth: 110,
                filter: 'agTextColumnFilter',
                sortable: true,
                hide: true
            },
            {
                colId: 'actions',
                headerName: t.actions || 'Actions',
                width: 160,
                minWidth: 140,
                maxWidth: 200,
                pinned: 'right',
                sortable: false,
                filter: false,
                lockVisible: true,
                cellRenderer: function(params) {
                    if (!params.data || !params.data.is_active) {
                        return '<span class="text-xs text-gray-500">' + esc(t.sessionEnded || 'Session ended') + '</span>';
                    }
                    var sid = String(params.data.session_id || '');
                    return '<button type="button" class="btn btn-danger btn-sm session-force-logout-btn" data-session-id="' +
                        esc(sid) + '">' +
                        '<i class="fas fa-sign-out-alt mr-1"></i>' + esc(t.forceLogout || 'Force Logout') + '</button>';
                }
            }
        ];
    }

    function updatePaginationUi(state) {
        var el = document.getElementById('session-logs-pagination');
        if (!el) return;
        var prev = document.getElementById('session-logs-page-prev');
        var next = document.getElementById('session-logs-page-next');
        var label = document.getElementById('session-logs-page-label');
        var total = state.totalRows != null ? state.totalRows : 0;
        var pages = state.totalPages != null ? state.totalPages : 0;
        var page = state.currentPage != null ? state.currentPage : 1;

        if (label) {
            var tr = window.SESSION_LOGS_TRANSLATIONS || {};
            if (total === 0) {
                label.textContent = tr.noRows || '0 sessions';
            } else {
                label.textContent = (tr.pageOfTotal || 'Page {page} of {pages} ({total} total)')
                    .replace('{page}', String(page))
                    .replace('{pages}', String(Math.max(pages, 1)))
                    .replace('{total}', String(total));
            }
        }
        if (prev) {
            prev.disabled = page <= 1 || total === 0;
            prev.classList.toggle('opacity-50', page <= 1 || total === 0);
        }
        if (next) {
            next.disabled = total === 0 || pages <= 0 || page >= pages;
            next.classList.toggle('opacity-50', total === 0 || pages <= 0 || page >= pages);
        }
    }

    function replaceUrlPage(page) {
        try {
            var u = new URL(window.location.href);
            if (page <= 1) {
                u.searchParams.delete('page');
            } else {
                u.searchParams.set('page', String(page));
            }
            window.history.replaceState({}, '', u.pathname + u.search + u.hash);
        } catch (e) {
            if (window.__clientWarn) window.__clientWarn('session logs replaceState failed', e);
        }
    }

    async function fetchSessionPage(config, page) {
        var sp = new URLSearchParams(window.location.search);
        sp.set('page', String(page));
        sp.set('per_page', String(config.perPage));
        var base = config.apiUrl;
        if (base.indexOf('?') !== -1) {
            base = base.split('?')[0];
        }
        var url = base + '?' + sp.toString();

        var res = await fetch(url, {
            credentials: 'same-origin',
            headers: {
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            }
        });
        var data = await res.json();
        if (!data || data.success !== true) {
            throw new Error((data && data.message) || 'Request failed');
        }
        return data;
    }

    function submitForceLogout(sessionId, config) {
        var token = getCsrfToken();
        if (!token) {
            window.alert('CSRF token missing. Refresh the page and try again.');
            return;
        }
        var url = (config.endSessionUrlTemplate || '').split('SESSION_ID_PLACEHOLDER').join(encodeURIComponent(sessionId));
        var form = document.createElement('form');
        form.method = 'POST';
        form.action = url;
        var inp = document.createElement('input');
        inp.type = 'hidden';
        inp.name = 'csrf_token';
        inp.value = token;
        form.appendChild(inp);
        document.body.appendChild(form);
        form.submit();
    }

    function init() {
        var config = window.sessionLogsGridConfig;
        if (!config || !config.apiUrl) {
            if (window.__clientWarn) window.__clientWarn('sessionLogsGridConfig missing');
            return;
        }

        if (config.initialSessionId) {
            try {
                var uFix = new URL(window.location.href);
                if (!uFix.searchParams.get('session_id')) {
                    uFix.searchParams.set('session_id', String(config.initialSessionId));
                    window.history.replaceState({}, '', uFix.pathname + uFix.search + uFix.hash);
                }
            } catch (e1) {
                if (window.__clientWarn) window.__clientWarn('session logs session_id replaceState', e1);
            }
        }

        var t = window.SESSION_LOGS_TRANSLATIONS || {};
        var loadingEl = document.getElementById('sessionLogs-loading');
        var gridHost = document.getElementById('sessionLogsGrid');
        if (!gridHost) return;

        var sp = new URLSearchParams(window.location.search);
        var initialPage = parseInt(sp.get('page') || '1', 10);
        if (isNaN(initialPage) || initialPage < 1) initialPage = 1;

        var state = {
            currentPage: initialPage,
            totalPages: 0,
            totalRows: 0,
            gridHelper: null,
            gridApi: null,
            gridInitialized: false
        };

        function onPaginationClick(delta) {
            var next = state.currentPage + delta;
            if (next < 1 || (state.totalPages > 0 && next > state.totalPages)) return;
            state.currentPage = next;
            replaceUrlPage(next);
            loadAndRender();
        }

        var prevBtn = document.getElementById('session-logs-page-prev');
        var nextBtn = document.getElementById('session-logs-page-next');
        if (prevBtn) prevBtn.addEventListener('click', function() { onPaginationClick(-1); });
        if (nextBtn) nextBtn.addEventListener('click', function() { onPaginationClick(1); });

        gridHost.addEventListener('click', function(ev) {
            var pathBtn = ev.target && ev.target.closest ? ev.target.closest('.session-path-breakdown-btn') : null;
            if (pathBtn) {
                ev.preventDefault();
                ev.stopPropagation();
                var raw = pathBtn.getAttribute('data-path-counts') || '';
                var total = parseInt(pathBtn.getAttribute('data-page-views-total') || '0', 10);
                var sid = pathBtn.getAttribute('data-session-id') || '';
                var pvc = {};
                try {
                    if (raw) pvc = JSON.parse(decodeURIComponent(raw));
                } catch (ePb) {
                    if (window.__clientWarn) window.__clientWarn('session path breakdown parse', ePb);
                }
                openPathBreakdownModal(t, pvc, total, sid);
                return;
            }
            var btn = ev.target && ev.target.closest ? ev.target.closest('.session-force-logout-btn') : null;
            if (!btn) return;
            ev.preventDefault();
            var sid = btn.getAttribute('data-session-id');
            if (!sid) return;
            var msg = config.confirmForceLogout || 'Are you sure?';
            if (!window.confirm(msg)) return;
            submitForceLogout(sid, config);
        });

        async function loadAndRender() {
            if (loadingEl) loadingEl.style.display = 'flex';
            try {
                var payload = await fetchSessionPage(config, state.currentPage);
                var items = payload.items || [];
                state.totalPages = payload.pages != null ? payload.pages : 0;
                state.totalRows = payload.total != null ? payload.total : items.length;
                if (payload.page != null) state.currentPage = payload.page;

                var rowData = items.map(mapRow);

                if (state.gridInitialized) {
                    var api = state.gridApi || (state.gridHelper && state.gridHelper.gridApi);
                    if (api && typeof api.setGridOption === 'function') {
                        api.setGridOption('rowData', rowData);
                    }
                } else {
                    state.gridInitialized = true;
                    state.gridHelper = new AgGridHelper({
                        containerId: 'sessionLogsGrid',
                        templateId: 'admin-session-logs',
                        columnDefs: buildColumnDefs(t, config),
                        rowData: rowData,
                        options: {
                            pagination: false,
                            getRowClass: function(params) {
                                if (params.data && params.data.is_active) return 'session-log-row--active';
                                return '';
                            },
                            onGridSizeChanged: function(ev) {
                                if (ev && ev.api && typeof ev.api.sizeColumnsToFit === 'function') {
                                    ev.api.sizeColumnsToFit({ defaultMinWidth: 80 });
                                }
                            }
                        },
                        heightOptions: {
                            minHeight: 600,
                            maxHeight: 600,
                            minRowsToShow: 1,
                            viewportOffset: 0
                        },
                        columnVisibilityOptions: {
                            enableExport: false,
                            enableReset: true,
                            buttonPlaceholderId: 'session-logs-column-visibility-placeholder'
                        }
                    });
                    state.gridApi = state.gridHelper.initialize();
                    if (!state.gridApi && typeof state.gridHelper.initializeAsync === 'function') {
                        try {
                            state.gridApi = await state.gridHelper.initializeAsync(5000);
                        } catch (e2) {
                            console.error('Session logs grid async init failed', e2);
                        }
                    }
                    applySessionLogsColumnOrder(state.gridApi);
                }

                updatePaginationUi(state);
            } catch (err) {
                console.error('Session logs grid:', err);
                window.alert((t.loadError || 'Could not load session logs.') + (err && err.message ? ' ' + err.message : ''));
            } finally {
                if (loadingEl) loadingEl.style.display = 'none';
            }
        }

        loadAndRender();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
