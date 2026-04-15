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

    function buildColumnDefs(t) {
        return [
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
                headerName: t.duration || 'Duration',
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
                field: 'page_views',
                headerName: t.pageViews || 'Page Views',
                width: 120,
                minWidth: 100,
                filter: 'agNumberColumnFilter',
                sortable: true,
                cellRenderer: function(params) {
                    var v = params.value != null ? params.value : 0;
                    return '<span class="px-2 inline-flex items-center text-xs leading-5 font-semibold rounded-full bg-gray-100 text-gray-800">' +
                        esc(v) + '</span>';
                }
            },
            {
                field: 'distinct_page_view_paths',
                headerName: t.distinctPaths || 'Distinct paths',
                width: 130,
                minWidth: 100,
                filter: 'agNumberColumnFilter',
                sortable: true,
                hide: true,
                cellRenderer: function(params) {
                    var v = params.value != null ? params.value : 0;
                    return '<span class="px-2 inline-flex items-center text-xs leading-5 font-semibold rounded-full bg-slate-100 text-slate-800">' +
                        esc(v) + '</span>';
                }
            },
            {
                field: 'activity_count',
                headerName: t.activities || 'Activities',
                width: 120,
                minWidth: 100,
                filter: 'agNumberColumnFilter',
                sortable: true,
                cellRenderer: function(params) {
                    var v = params.value != null ? params.value : 0;
                    return '<span class="px-2 inline-flex items-center text-xs leading-5 font-semibold rounded-full bg-indigo-100 text-indigo-800">' +
                        esc(v) + '</span>';
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
                        columnDefs: buildColumnDefs(t),
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
