/**
 * Admin Login Logs — AG Grid (loads rows from /admin/api/analytics/login-logs).
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

    function truncate(str, maxLen) {
        var s = str == null ? '' : String(str);
        if (s.length <= maxLen) return s;
        return s.slice(0, Math.max(0, maxLen - 1)) + '…';
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
                flex: 1.1,
                minWidth: 240,
                filter: 'agTextColumnFilter',
                sortable: true,
                valueGetter: function(p) {
                    var d = p.data || {};
                    if (d.user_id) {
                        return [d.user_name, d.user_email].filter(Boolean).join(' ');
                    }
                    return d.email_attempted || '';
                },
                cellRenderer: function(params) {
                    var d = params.data || {};
                    var cls = String(d.device_icon_classes || 'fas fa-laptop text-gray-500')
                        .replace(/[<"']/g, '');
                    var tip = esc(d.operating_system || d.device_type || '');
                    var icon = '<i class="' + cls + '" style="flex-shrink:0;width:1.25rem;text-align:center;line-height:1;" title="' +
                        esc(tip) + '" aria-hidden="true"></i>';
                    if (d.user_id && typeof AgGridRenderers !== 'undefined' && AgGridRenderers.userHoverCellWithDeviceIcon) {
                        return AgGridRenderers.userHoverCellWithDeviceIcon(params, {
                            idField: 'user_id',
                            nameField: 'user_name',
                            emailField: 'user_email',
                            fallbackLabel: t.unknownUser || 'Unknown User'
                        }, icon);
                    }
                    var email = esc(d.email_attempted || '');
                    var sub = esc(t.userNotFound || 'User not found');
                    return '<div class="ag-user-hover-cell" style="display:flex;width:100%;min-width:0;">' +
                        '<div style="display:flex;flex-direction:column;gap:4px;min-width:0;flex:1;">' +
                        '<div style="display:flex;flex-direction:row;align-items:center;gap:0.5rem;min-width:0;">' +
                        icon +
                        '<span class="text-sm font-medium text-gray-900" style="line-height:1.3;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' +
                        email + '</span></div>' +
                        '<div style="padding-left:1.75rem;font-size:0.75rem;line-height:1.3;color:#9ca3af;">' + sub + '</div>' +
                        '</div></div>';
                }
            },
            {
                field: 'event_type',
                headerName: t.event || 'Event',
                width: 200,
                minWidth: 160,
                filter: 'customSetFilter',
                sortable: true,
                cellRenderer: function(params) {
                    var d = params.data || {};
                    var et = d.event_type;
                    var fr = d.failure_reason_display;
                    var html = '';
                    if (et === 'login_success') {
                        html = '<span class="px-2 inline-flex items-center text-xs leading-5 font-semibold rounded-full bg-green-100 text-green-800">' +
                            '<i class="fas fa-check-circle mr-1" style="line-height:1"></i>' + esc(t.eventLogin || 'Login') + '</span>';
                    } else if (et === 'logout') {
                        html = '<span class="px-2 inline-flex items-center text-xs leading-5 font-semibold rounded-full bg-blue-100 text-blue-800">' +
                            '<i class="fas fa-door-open mr-1" style="line-height:1"></i>' + esc(t.eventLogout || 'Logout') + '</span>';
                    } else if (et === 'login_failed') {
                        html = '<span class="px-2 inline-flex items-center text-xs leading-5 font-semibold rounded-full bg-red-100 text-red-800">' +
                            '<i class="fas fa-times-circle mr-1" style="line-height:1"></i>' + esc(t.eventFailed || 'Failed login') + '</span>';
                        if (fr) {
                            html += '<div class="text-xs text-red-600 mt-1">' + esc(fr) + '</div>';
                        }
                    } else {
                        html = '<span class="text-sm text-gray-700">' + esc(et || '') + '</span>';
                    }
                    return html;
                }
            },
            {
                field: 'timestamp',
                headerName: t.timestamp || 'Timestamp',
                width: 180,
                minWidth: 150,
                filter: 'agTextColumnFilter',
                sortable: true,
                cellRenderer: typeof AgGridRenderers !== 'undefined' ? AgGridRenderers.dateTime : undefined
            },
            {
                colId: 'ip_block',
                headerName: t.ipAddress || 'IP address',
                width: 200,
                minWidth: 140,
                filter: 'agTextColumnFilter',
                sortable: true,
                valueGetter: function(p) {
                    var d = p.data || {};
                    return [d.ip_address, d.location].filter(Boolean).join(' ');
                },
                cellRenderer: function(params) {
                    var d = params.data || {};
                    var ip = esc(d.ip_address || '');
                    var loc = d.location ? '<div class="text-xs text-gray-500">' + esc(d.location) + '</div>' : '';
                    var failLine = '';
                    if (d.event_type === 'login_failed' && d.failed_attempts_count > 1) {
                        failLine = '<div class="text-xs text-red-500 mt-1"><i class="fas fa-exclamation-triangle mr-1"></i>' +
                            esc(String(d.failed_attempts_count)) + ' ' + esc(t.recentFailures || 'recent failures') + '</div>';
                    }
                    return '<div class="text-sm text-gray-900 font-mono">' + ip + '</div>' + loc + failLine;
                }
            },
            {
                colId: 'device_block',
                headerName: t.device || 'Device',
                width: 150,
                minWidth: 120,
                filter: 'agTextColumnFilter',
                sortable: true,
                valueGetter: function(p) {
                    var d = p.data || {};
                    return [d.device_type, d.operating_system].filter(Boolean).join(' ');
                },
                cellRenderer: function(params) {
                    var d = params.data || {};
                    var dt = d.device_type;
                    var line1 = dt
                        ? '<div class="text-sm text-gray-900">' + esc(String(dt).replace(/\w\S*/g, function(x) {
                            return x.charAt(0).toUpperCase() + x.substr(1).toLowerCase();
                        })) + '</div>'
                        : '<span class="text-sm text-gray-500">' + esc(t.unknown || 'Unknown') + '</span>';
                    var dn = d.device_name && d.device_name !== dt
                        ? '<div class="text-xs text-gray-500">' + esc(d.device_name) + '</div>'
                        : '';
                    var botTip = d.bot_detection_detail || t.botDetectedHoverFallback || '';
                    var bot = d.is_bot_detected
                        ? '<div class="text-xs text-orange-600 mt-1" title="' + esc(botTip) + '">' +
                            '<i class="fas fa-robot mr-1" aria-hidden="true"></i>' +
                            esc(t.botDetected || 'Bot detected') + '</div>'
                        : '';
                    return line1 + dn + bot;
                }
            },
            {
                colId: 'browser_block',
                headerName: t.browser || 'Browser',
                width: 220,
                minWidth: 160,
                maxWidth: 320,
                filter: 'agTextColumnFilter',
                sortable: true,
                cellStyle: {
                    overflow: 'hidden',
                    minWidth: 0
                },
                valueGetter: function(p) {
                    var d = p.data || {};
                    return [d.browser_name, d.browser, d.referrer_url].filter(Boolean).join(' ');
                },
                cellRenderer: function(params) {
                    var d = params.data || {};
                    var name = d.browser_name || (d.browser ? String(d.browser) : '');
                    var ver = d.browser_version;
                    var row = 'min-width:0;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
                    var line1 = name
                        ? '<div class="text-sm text-gray-900" style="' + row + '">' + esc(name) + '</div>'
                        : '<span class="text-sm text-gray-500" style="' + row + '">' + esc(t.unknown || 'Unknown') + '</span>';
                    var line2 = ver
                        ? '<div class="text-xs text-gray-500" style="' + row + '">v' + esc(ver) + '</div>'
                        : '';
                    var ref = '';
                    if (d.referrer_url) {
                        var full = esc(d.referrer_url);
                        var shown = esc(truncate(d.referrer_url, 48));
                        ref = '<div class="text-xs text-gray-400" style="margin-top:4px;min-width:0;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="' +
                            full + '"><i class="fas fa-external-link-alt mr-1"></i>' + shown + '</div>';
                    }
                    return '<div class="login-logs-browser-cell-inner" style="min-width:0;max-width:100%;width:100%;overflow:hidden;box-sizing:border-box;">' +
                        line1 + line2 + ref + '</div>';
                }
            },
            {
                colId: 'status_block',
                headerName: t.status || 'Status',
                width: 160,
                minWidth: 130,
                filter: 'customSetFilter',
                sortable: true,
                cellStyle: {
                    overflow: 'hidden',
                    minWidth: 0
                },
                cellRenderer: function(params) {
                    var d = params.data || {};
                    if (d.event_type === 'login_failed' && d.risk) {
                        var r = d.risk;
                        var bcls = String(r.badge_class || 'bg-gray-100 text-gray-800').replace(/[^\w\-\s]/g, '');
                        var ric = String(r.icon || 'fas fa-info-circle').replace(/[^\w\-\s]/g, '');
                        return '<span class="px-2 inline-flex items-center text-xs leading-5 font-semibold rounded-full ' + bcls + '">' +
                            '<i class="' + ric + ' mr-1" style="line-height:1"></i>' + esc(r.text || '') + '</span>';
                    }
                    if (d.is_suspicious) {
                        return '<span class="px-2 inline-flex items-center text-xs leading-5 font-semibold rounded-full bg-yellow-100 text-yellow-800">' +
                            '<i class="fas fa-exclamation-triangle mr-1" style="line-height:1"></i>' + esc(t.suspicious || 'Suspicious') + '</span>';
                    }
                    if (d.event_type === 'login_success') {
                        return '<span class="px-2 inline-flex items-center text-xs leading-5 font-semibold rounded-full bg-green-100 text-green-800">' +
                            esc(t.success || 'Success') + '</span>';
                    }
                    if (d.event_type === 'logout') {
                        return '<span class="px-2 inline-flex items-center text-xs leading-5 font-semibold rounded-full bg-blue-100 text-blue-800">' +
                            esc(t.completed || 'Completed') + '</span>';
                    }
                    return '<span class="px-2 inline-flex items-center text-xs leading-5 font-semibold rounded-full bg-red-100 text-red-800">' +
                        esc(t.failed || 'Failed') + '</span>';
                }
            },
            {
                field: 'operating_system',
                headerName: t.operatingSystem || 'OS',
                width: 140,
                minWidth: 100,
                filter: 'agTextColumnFilter',
                hide: true
            },
            {
                field: 'email_attempted',
                headerName: t.emailAttempted || 'Email attempted',
                width: 200,
                minWidth: 160,
                filter: 'agTextColumnFilter',
                hide: true
            }
        ];
    }

    function updatePaginationUi(state) {
        var el = document.getElementById('login-logs-pagination');
        if (!el) return;
        var prev = document.getElementById('login-logs-page-prev');
        var next = document.getElementById('login-logs-page-next');
        var label = document.getElementById('login-logs-page-label');
        var total = state.totalRows != null ? state.totalRows : 0;
        var pages = state.totalPages != null ? state.totalPages : 0;
        var page = state.currentPage != null ? state.currentPage : 1;

        var tr = window.LOGIN_LOGS_TRANSLATIONS || {};
        if (label) {
            if (total === 0) {
                label.textContent = tr.noRows || '0 events';
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
            if (window.__clientWarn) window.__clientWarn('login logs replaceState failed', e);
        }
    }

    async function fetchLoginPage(config, page) {
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

    function init() {
        var config = window.loginLogsGridConfig;
        if (!config || !config.apiUrl) {
            if (window.__clientWarn) window.__clientWarn('loginLogsGridConfig missing');
            return;
        }

        var t = window.LOGIN_LOGS_TRANSLATIONS || {};
        var loadingEl = document.getElementById('loginLogs-loading');
        var gridHost = document.getElementById('loginLogsGrid');
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
            var n = state.currentPage + delta;
            if (n < 1 || (state.totalPages > 0 && n > state.totalPages)) return;
            state.currentPage = n;
            replaceUrlPage(n);
            loadAndRender();
        }

        var prevBtn = document.getElementById('login-logs-page-prev');
        var nextBtn = document.getElementById('login-logs-page-next');
        if (prevBtn) prevBtn.addEventListener('click', function() { onPaginationClick(-1); });
        if (nextBtn) nextBtn.addEventListener('click', function() { onPaginationClick(1); });

        async function loadAndRender() {
            if (loadingEl) loadingEl.style.display = 'flex';
            try {
                var payload = await fetchLoginPage(config, state.currentPage);
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
                        containerId: 'loginLogsGrid',
                        templateId: 'admin-login-logs',
                        columnDefs: buildColumnDefs(t),
                        rowData: rowData,
                        options: {
                            pagination: false,
                            getRowClass: function(params) {
                                if (params.data && params.data.is_suspicious) return 'login-log-row--suspicious';
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
                            buttonPlaceholderId: 'login-logs-column-visibility-placeholder'
                        }
                    });
                    state.gridApi = state.gridHelper.initialize();
                    if (!state.gridApi && typeof state.gridHelper.initializeAsync === 'function') {
                        try {
                            state.gridApi = await state.gridHelper.initializeAsync(5000);
                        } catch (e2) {
                            console.error('Login logs grid async init failed', e2);
                        }
                    }
                }

                updatePaginationUi(state);
            } catch (err) {
                console.error('Login logs grid:', err);
                window.alert((t.loadError || 'Could not load login logs.') + (err && err.message ? ' ' + err.message : ''));
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
