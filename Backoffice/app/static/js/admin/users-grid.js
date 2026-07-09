(function () {
    'use strict';
    var cfg = window.usersGridConfig || {};
    var t = cfg.t || {};

    var usersData = (function () {
        var el = document.getElementById('users-grid-data');
        if (!el) return [];
        try { return JSON.parse(el.textContent || '[]'); } catch (e) { return []; }
    })();

    var escapeHtml = AgGridRenderers.escapeHtml;
    var escapeHtmlAttr = AgGridRenderers.escapeHtmlAttr;

    function getTotalCountriesInRegions(user) {
        return Object.values(user.countries_by_region || {}).reduce(function (sum, countries) {
            return sum + (countries ? countries.length : 0);
        }, 0);
    }

    function getCompleteRegionNames(user) {
        var regions = [];
        var assigned = user.countries || [];
        for (var region in user.countries_by_region || {}) {
            if (!Object.prototype.hasOwnProperty.call(user.countries_by_region, region)) continue;
            var countries = user.countries_by_region[region] || [];
            if (!countries.length) continue;
            var regionUserCount = countries.filter(function (c) { return assigned.indexOf(c) !== -1; }).length;
            if (regionUserCount === countries.length) {
                regions.push(region);
            }
        }
        return regions;
    }

    /** Display/export summary (may use counts like "3 countries"). */
    function getEntitiesPlainText(user) {
        if (!user) return '';
        if (user.is_system_manager) {
            return t.global_f2a89e71 || 'Global';
        }
        var parts = [];
        if (user.country_count > 0) {
            if (user.country_count === 1 && user.countries && user.countries.length) {
                parts.push(user.countries[0]);
            } else {
                var totalCountries = getTotalCountriesInRegions(user);
                if (user.country_count === totalCountries) {
                    parts.push(t.global_f2a89e71 || 'Global');
                } else {
                    var completeRegions = getCompleteRegionNames(user);
                    if (!completeRegions.length) {
                        parts.push(user.country_count + ' ' + (t.countries_790d59ef || 'countries'));
                    } else {
                        parts = parts.concat(completeRegions);
                        var completeRegionsTotal = completeRegions.reduce(function (sum, region) {
                            var countries = (user.countries_by_region || {})[region] || [];
                            return sum + countries.length;
                        }, 0);
                        if (user.country_count > completeRegionsTotal) {
                            parts.push('+' + (user.country_count - completeRegionsTotal) + ' ' + (t.other_countries_b1e7b76a || 'other countries'));
                        }
                    }
                }
            }
        }
        if (user.branch_count > 0) parts.push(user.branch_count + ' ' + (t.branches_7cddf5f4 || 'branches'));
        if (user.subbranch_count > 0) parts.push(user.subbranch_count + ' ' + (t.sub_branches_2d3b75e2 || 'sub-branches'));
        if (user.localunit_count > 0) parts.push(user.localunit_count + ' ' + (t.local_units_4a0dc5ea || 'local units'));
        if (user.division_count > 0) parts.push(user.division_count + ' ' + (t.divisions_8b9c5a88 || 'divisions'));
        if (user.department_count > 0) parts.push(user.department_count + ' ' + (t.departments_6a7e3c44 || 'departments'));
        if (user.regional_count > 0) parts.push(user.regional_count + ' ' + (t.regional_offices_a5bf1c32 || 'regional offices'));
        if (user.cluster_count > 0) parts.push(user.cluster_count + ' ' + (t.clusters_f8d4c77a || 'clusters'));
        return parts.length ? parts.join('; ') : '-';
    }

    /**
     * Filter checklist values: real entity names (Global, regions, countries, entity types),
     * never summary counts like "3 countries".
     */
    function getEntitiesFilterItems(user) {
        if (!user) return [];
        var items = [];
        var seen = {};
        function add(value) {
            if (!value) return;
            var key = String(value);
            if (seen[key]) return;
            seen[key] = true;
            items.push(key);
        }

        if (user.is_system_manager) {
            add(t.global_f2a89e71 || 'Global');
            return items;
        }

        if (user.country_count > 0) {
            var totalCountries = getTotalCountriesInRegions(user);
            if (user.country_count === totalCountries && totalCountries > 0) {
                add(t.global_f2a89e71 || 'Global');
            } else {
                getCompleteRegionNames(user).forEach(add);
                (user.countries || []).forEach(add);
            }
        }

        if (user.branch_count > 0) add(t.branches_7cddf5f4 || 'branches');
        if (user.subbranch_count > 0) add(t.sub_branches_2d3b75e2 || 'sub-branches');
        if (user.localunit_count > 0) add(t.local_units_4a0dc5ea || 'local units');
        if (user.division_count > 0) add(t.divisions_8b9c5a88 || 'divisions');
        if (user.department_count > 0) add(t.departments_6a7e3c44 || 'departments');
        if (user.regional_count > 0) add(t.regional_offices_a5bf1c32 || 'regional offices');
        if (user.cluster_count > 0) add(t.clusters_f8d4c77a || 'clusters');

        return items.length ? items : ['-'];
    }

    function renderEntities(user) {
        if (user.is_system_manager) {
            return '<span class="font-medium text-blue-600">' + escapeHtml(t.global_f2a89e71 || 'Global') + '</span>';
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
                    html += '<span class="font-medium text-blue-600">' + escapeHtml(t.global_f2a89e71 || 'Global') + '</span>';
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
                        html += '<span class="cursor-help" title="' + escapeHtmlAttr(user.countries.join(', ')) + '">' + user.country_count + ' ' + escapeHtml(t.countries_790d59ef || 'countries') + '</span>';
                    } else {
                        var completeRegionsTotal = Object.values(regions).reduce(function (sum, r) { return sum + (r.user === r.total ? r.total : 0); }, 0);
                        if (user.country_count > completeRegionsTotal) {
                            html += '<div class="text-gray-500 text-xs mt-1">+' + (user.country_count - completeRegionsTotal) + ' ' + escapeHtml(t.other_countries_b1e7b76a || 'other countries') + '</div>';
                        }
                    }
                }
            }
        }
        if (user.branch_count > 0) { displayedAny = true; html += '<div class="text-gray-700 text-xs">' + user.branch_count + ' ' + escapeHtml(t.branches_7cddf5f4 || 'branches') + '</div>'; }
        if (user.subbranch_count > 0) { displayedAny = true; html += '<div class="text-gray-700 text-xs">' + user.subbranch_count + ' ' + escapeHtml(t.sub_branches_2d3b75e2 || 'sub-branches') + '</div>'; }
        if (user.localunit_count > 0) { displayedAny = true; html += '<div class="text-gray-700 text-xs">' + user.localunit_count + ' ' + escapeHtml(t.local_units_4a0dc5ea || 'local units') + '</div>'; }
        if (user.division_count > 0) { displayedAny = true; html += '<div class="text-gray-700 text-xs">' + user.division_count + ' ' + escapeHtml(t.divisions_8b9c5a88 || 'divisions') + '</div>'; }
        if (user.department_count > 0) { displayedAny = true; html += '<div class="text-gray-700 text-xs">' + user.department_count + ' ' + escapeHtml(t.departments_6a7e3c44 || 'departments') + '</div>'; }
        if (user.regional_count > 0) { displayedAny = true; html += '<div class="text-gray-700 text-xs">' + user.regional_count + ' ' + escapeHtml(t.regional_offices_a5bf1c32 || 'regional offices') + '</div>'; }
        if (user.cluster_count > 0) { displayedAny = true; html += '<div class="text-gray-700 text-xs">' + user.cluster_count + ' ' + escapeHtml(t.clusters_f8d4c77a || 'clusters') + '</div>'; }
        return displayedAny ? html : '-';
    }

    // Precompute searchable/exportable entities text and filterable entity names.
    usersData.forEach(function (user) {
        user.entities = getEntitiesPlainText(user);
        user.entities_filter_items = getEntitiesFilterItems(user);
        user.status_label = user.active
            ? (t.active_4d3d769b || 'Active')
            : (t.inactive_3cab7a0a || 'Inactive');
        user.fds_member_label = user.is_fds_member
            ? (t.yes_93cba074 || 'Yes')
            : (t.no_bafd7328 || 'No');
        if (!user.fds_member_countries) {
            user.fds_member_countries = [];
        }
        user.fds_member_countries_text = user.fds_member_countries.length
            ? user.fds_member_countries.join('; ')
            : '';
    });

    var columnDefs = [
        {
            field: 'id',
            headerName: t.id_e369853d,
            width: 80, minWidth: 80, maxWidth: 120,
            lockVisible: true,
            filter: 'agNumberColumnFilter', sortable: true,
            sort: 'asc', sortIndex: 0,
            wrapText: false, autoHeight: false,
            cellStyle: { 'white-space': 'nowrap' }
        },
        {
            field: 'name',
            headerName: t.user_8f9bfe9d,
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
            headerName: t.email_ce8ae9da,
            width: 250, minWidth: 200, maxWidth: 350,
            filter: 'agTextColumnFilter', sortable: true
        },
        {
            field: 'title',
            headerName: t.title_b78a3223,
            width: 200, minWidth: 150, maxWidth: 300,
            hide: true,
            filter: 'agTextColumnFilter', sortable: true,
            cellRenderer: function (params) { return params.value || '-'; }
        },
        {
            field: 'role_display',
            headerName: t.role_2e083440,
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
            headerName: t.status_ec53a8c4,
            width: 120, minWidth: 100, maxWidth: 150,
            filter: 'customSetFilter', sortable: true,
            filterValueGetter: function (params) {
                return params.data ? params.data.status_label : '';
            },
            exportValueGetter: function (params) {
                return params.data ? params.data.status_label : '';
            },
            cellRenderer: AgGridRenderers.statusBadge,
            cellStyle: { 'white-space': 'nowrap' }
        },
        {
            field: 'is_fds_member',
            headerName: t.fds_member_7a2c91e4,
            width: 140, minWidth: 120, maxWidth: 180,
            hide: true,
            filter: 'customSetFilter', sortable: true,
            filterValueGetter: function (params) {
                return params.data ? params.data.fds_member_label : '';
            },
            valueGetter: function (params) {
                return params.data ? params.data.fds_member_label : '';
            },
            exportValueGetter: function (params) {
                if (!params.data) return '';
                if (!params.data.is_fds_member) return params.data.fds_member_label || (t.no_bafd7328 || 'No');
                var countries = params.data.fds_member_countries_text;
                return countries
                    ? (params.data.fds_member_label + ' (' + countries + ')')
                    : params.data.fds_member_label;
            },
            cellRenderer: function (params) {
                if (!params.data || !params.data.is_fds_member) {
                    return '<span class="text-gray-400">-</span>';
                }
                var label = escapeHtml(t.yes_93cba074 || 'Yes');
                var countries = params.data.fds_member_countries || [];
                if (!countries.length) {
                    return '<span class="font-medium text-green-700">' + label + '</span>';
                }
                var title = escapeHtmlAttr(countries.join(', '));
                var countLabel = countries.length === 1
                    ? escapeHtml(countries[0])
                    : (countries.length + ' ' + escapeHtml(t.countries_790d59ef || 'countries'));
                return '<div class="leading-tight">'
                    + '<span class="font-medium text-green-700">' + label + '</span>'
                    + '<div class="text-gray-500 text-xs cursor-help" title="' + title + '">' + countLabel + '</div>'
                    + '</div>';
            },
            cellStyle: { 'white-space': 'normal', 'line-height': '1.3' }
        },
        {
            field: 'entities',
            headerName: t.entities_3b4d9c2e,
            width: 300, minWidth: 200, maxWidth: 400,
            filter: 'customSetFilter',
            sortable: false,
            valueGetter: function (params) {
                return params.data ? (params.data.entities || '') : '';
            },
            filterValueGetter: function (params) {
                return params.data ? (params.data.entities_filter_items || []) : [];
            },
            exportValueGetter: function (params) {
                return params.data ? (params.data.entities || '') : '';
            },
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
        var result = AgGridHelper.create('usersGrid', 'users-v3', columnDefs, usersData, {
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
                },
                processCellForClipboard: function (params) {
                    if (!params || !params.column || !params.node || !params.node.data) {
                        return params && params.value != null ? params.value : '';
                    }
                    var colId = params.column.getColId ? params.column.getColId() : '';
                    if (colId === 'entities') {
                        return params.node.data.entities || '';
                    }
                    if (colId === 'active') {
                        return params.node.data.status_label || '';
                    }
                    if (colId === 'is_fds_member') {
                        return params.node.data.fds_member_label || '';
                    }
                    return params.value != null ? params.value : '';
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
