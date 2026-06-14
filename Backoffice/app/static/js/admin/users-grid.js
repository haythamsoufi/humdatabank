(function () {
    'use strict';
    var cfg = window.usersGridConfig || {};

    var usersData = (function () {
        var el = document.getElementById('users-grid-data');
        if (!el) return [];
        try { return JSON.parse(el.textContent || '[]'); } catch (e) { return []; }
    })();

    var escapeHtml = AgGridRenderers.escapeHtml;
    var escapeHtmlAttr = AgGridRenderers.escapeHtmlAttr;

    function renderEntities(user) {
        if (user.is_system_manager) {
            return '<span class="font-medium text-blue-600">' + cfg.t.global_f2a89e71 + '</span>';
        }
        var html = '';
        var displayedAny = false;
        if (user.country_count > 0) {
            displayedAny = true;
            if (user.country_count === 1) {
                html += escapeHtml(user.countries[0]);
            } else {
                var totalCountries = Object.values(user.countries_by_region || {}).reduce(function (sum, countries) { return sum + (countries ? countries.length : 0); }, 0);
                if (user.country_count === totalCountries) {
                    html += '<span class="font-medium text-blue-600">' + cfg.t.global_f2a89e71 + '</span>';
                } else {
                    var hasCompleteRegion = false;
                    var regions = {};
                    for (var region in user.countries_by_region || {}) {
                        var countries = user.countries_by_region[region];
                        var regionTotal = countries ? countries.length : 0;
                        var regionUserCount = countries ? countries.filter(function (c) { return user.countries.includes(c); }).length : 0;
                        if (regionTotal > 0) {
                            regions[region] = { total: regionTotal, user: regionUserCount };
                            if (regionUserCount === regionTotal) {
                                hasCompleteRegion = true;
                                html += '<div class="font-medium text-green-600">' + escapeHtml(region) + '</div>';
                            }
                        }
                    }
                    if (!hasCompleteRegion) {
                        html += '<span class="cursor-help" title="' + escapeHtmlAttr(user.countries.join(', ')) + '">' + user.country_count + ' ' + cfg.t.countries_790d59ef + '</span>';
                    } else {
                        var completeRegionsTotal = Object.values(regions).reduce(function (sum, r) { return sum + (r.user === r.total ? r.total : 0); }, 0);
                        if (user.country_count > completeRegionsTotal) {
                            html += '<div class="text-gray-500 text-xs mt-1">+' + (user.country_count - completeRegionsTotal) + ' ' + cfg.t.other_countries_b1e7b76a + '</div>';
                        }
                    }
                }
            }
        }
        if (user.branch_count > 0) { displayedAny = true; html += '<div class="text-gray-700 text-xs">' + user.branch_count + ' ' + cfg.t.branches_7cddf5f4 + '</div>'; }
        if (user.subbranch_count > 0) { displayedAny = true; html += '<div class="text-gray-700 text-xs">' + user.subbranch_count + ' ' + cfg.t.sub_branches_2d3b75e2 + '</div>'; }
        if (user.localunit_count > 0) { displayedAny = true; html += '<div class="text-gray-700 text-xs">' + user.localunit_count + ' ' + cfg.t.local_units_4a0dc5ea + '</div>'; }
        if (user.division_count > 0) { displayedAny = true; html += '<div class="text-gray-700 text-xs">' + user.division_count + ' ' + cfg.t.divisions_8b9c5a88 + '</div>'; }
        if (user.department_count > 0) { displayedAny = true; html += '<div class="text-gray-700 text-xs">' + user.department_count + ' ' + cfg.t.departments_6a7e3c44 + '</div>'; }
        if (user.regional_count > 0) { displayedAny = true; html += '<div class="text-gray-700 text-xs">' + user.regional_count + ' ' + cfg.t.regional_offices_a5bf1c32 + '</div>'; }
        if (user.cluster_count > 0) { displayedAny = true; html += '<div class="text-gray-700 text-xs">' + user.cluster_count + ' ' + cfg.t.clusters_f8d4c77a + '</div>'; }
        return displayedAny ? html : '-';
    }

    var columnDefs = [
        {
            field: 'id',
            headerName: cfg.t.id_e369853d,
            width: 80, minWidth: 80, maxWidth: 120,
            lockVisible: true,
            filter: 'agNumberColumnFilter', sortable: true,
            sort: 'asc', sortIndex: 0,
            wrapText: false, autoHeight: false,
            cellStyle: { 'white-space': 'nowrap' }
        },
        {
            field: 'name',
            headerName: cfg.t.user_8f9bfe9d,
            width: 250, minWidth: 200, maxWidth: 350,
            filter: 'agTextColumnFilter', sortable: true,
            cellRenderer: function (params) {
                var inner = AgGridRenderers.userHoverCell(
                    { value: params.data, data: params.data },
                    { showEmail: false, countriesCountField: 'country_count' }
                );
                var editUrl = params.data.edit_url || '';
                var deniedMessage = params.data.edit_denied_message || '';
                if (editUrl) {
                    return '<a href="' + escapeHtmlAttr(editUrl) + '" class="block hover:bg-gray-50 rounded -mx-1 px-1" style="text-decoration:none;color:inherit;">' + inner + '</a>';
                }
                if (deniedMessage) {
                    return '<span class="block rounded -mx-1 px-1 users-grid-name-denied cursor-pointer hover:bg-gray-50" role="button" tabindex="0">' + inner + '</span>';
                }
                return inner;
            },
            cellStyle: { 'white-space': 'normal', 'word-wrap': 'break-word', 'overflow-wrap': 'break-word', 'line-height': '1.4', 'overflow': 'hidden', 'max-width': '100%' }
        },
        {
            field: 'email',
            headerName: cfg.t.email_ce8ae9da,
            width: 250, minWidth: 200, maxWidth: 350,
            filter: 'agTextColumnFilter', sortable: true
        },
        {
            field: 'title',
            headerName: cfg.t.title_b78a3223,
            width: 200, minWidth: 150, maxWidth: 300,
            hide: true,
            filter: 'agTextColumnFilter', sortable: true,
            cellRenderer: function (params) { return params.value || '-'; }
        },
        {
            field: 'role_display',
            headerName: cfg.t.role_2e083440,
            width: 180, minWidth: 150, maxWidth: 250,
            filter: 'customSetFilter', sortable: true,
            cellRenderer: function (params) {
                var text = params.value || '-';
                var tooltip = (params && params.data && params.data.role_tooltip) || '';
                if (!tooltip) return escapeHtml(text);
                return '<span class="cursor-help" title="' + escapeHtmlAttr(tooltip) + '">' + escapeHtml(text) + '</span>';
            },
            cellStyle: { 'white-space': 'pre-line', 'word-wrap': 'break-word', 'overflow-wrap': 'break-word', 'line-height': '1.4' }
        },
        {
            field: 'active',
            headerName: cfg.t.status_ec53a8c4,
            width: 120, minWidth: 100, maxWidth: 150,
            filter: 'customSetFilter', sortable: true,
            cellRenderer: AgGridRenderers.statusBadge,
            cellStyle: { 'white-space': 'nowrap' }
        },
        {
            field: 'entities',
            headerName: cfg.t.entities_3b4d9c2e,
            width: 300, minWidth: 200, maxWidth: 400,
            filter: 'agTextColumnFilter', sortable: false,
            cellRenderer: function (params) { return renderEntities(params.data); },
            cellStyle: { 'white-space': 'normal', 'word-wrap': 'break-word', 'line-height': '1.4' }
        }
    ];

    var gridHelper = null;
    var gridApi = null;

    function showEditDeniedMessage(message) {
        if (!message) return;
        if (window.FlashMessages && typeof window.FlashMessages.add === 'function') {
            window.FlashMessages.add(message, 'danger');
        } else if (typeof window.showFlashMessage === 'function') {
            window.showFlashMessage(message, 'danger');
        }
    }

    function handleNameCellActivation(data) {
        if (!data || data.edit_url) return;
        showEditDeniedMessage(data.edit_denied_message);
    }

    function initializeGrid() {
        var result = AgGridHelper.create('usersGrid', 'users', columnDefs, usersData, {
            gridOptions: {
                getRowClass: function (params) {
                    return (!params.data.active) ? 'inactive-user-row' : null;
                },
                onCellClicked: function (params) {
                    if (!params || params.colDef.field !== 'name') return;
                    handleNameCellActivation(params.data);
                },
                onCellKeyDown: function (params) {
                    if (!params || params.colDef.field !== 'name') return;
                    if (params.event && params.event.key === 'Enter') {
                        handleNameCellActivation(params.data);
                    }
                }
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
})();
