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

    var ignoreCountriesForGlobal = {};
    (cfg.ignoreCountriesForGlobal && cfg.ignoreCountriesForGlobal.length
        ? cfg.ignoreCountriesForGlobal
        : ['Testland']
    ).forEach(function (name) {
        if (name) ignoreCountriesForGlobal[name] = true;
    });

    function isIgnoredCountryForGlobal(name) {
        return !!(name && ignoreCountriesForGlobal[name]);
    }

    function countriesForGlobal(list) {
        return (list || []).filter(function (name) { return !isIgnoredCountryForGlobal(name); });
    }

    function getCountriesByRegionForGlobal(user) {
        var source = user.countries_by_region || {};
        var filtered = {};
        for (var region in source) {
            if (!Object.prototype.hasOwnProperty.call(source, region)) continue;
            var countries = countriesForGlobal(source[region]);
            if (countries.length) filtered[region] = countries;
        }
        return filtered;
    }

    function getAssignedCountriesForGlobal(user) {
        return countriesForGlobal(user && user.countries);
    }

    /** True when the user has every real country (Testland / sandbox countries do not count). */
    function hasAllCountries(user) {
        var catalog = getCountriesByRegionForGlobal(user);
        var catalogNames = [];
        for (var region in catalog) {
            if (!Object.prototype.hasOwnProperty.call(catalog, region)) continue;
            catalogNames = catalogNames.concat(catalog[region]);
        }
        if (!catalogNames.length) return false;
        var assignedSet = {};
        getAssignedCountriesForGlobal(user).forEach(function (name) {
            assignedSet[name] = true;
        });
        return catalogNames.every(function (name) { return assignedSet[name]; });
    }

    function getCompleteRegionNames(user) {
        var regions = [];
        var assigned = getAssignedCountriesForGlobal(user);
        var catalog = getCountriesByRegionForGlobal(user);
        for (var region in catalog) {
            if (!Object.prototype.hasOwnProperty.call(catalog, region)) continue;
            var countries = catalog[region];
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
            } else if (hasAllCountries(user)) {
                parts.push(t.global_f2a89e71 || 'Global');
            } else {
                var completeRegions = getCompleteRegionNames(user);
                if (!completeRegions.length) {
                    parts.push(user.country_count + ' ' + (t.countries_790d59ef || 'countries'));
                } else {
                    var catalog = getCountriesByRegionForGlobal(user);
                    parts = parts.concat(completeRegions);
                    var completeRegionsTotal = completeRegions.reduce(function (sum, region) {
                        var countries = catalog[region] || [];
                        return sum + countries.length;
                    }, 0);
                    var assignedCount = getAssignedCountriesForGlobal(user).length;
                    if (assignedCount > completeRegionsTotal) {
                        parts.push('+' + (assignedCount - completeRegionsTotal) + ' ' + (t.other_countries_b1e7b76a || 'other countries'));
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

    /** Export every assigned country by name while retaining non-country entity counts. */
    function getEntitiesExportText(user) {
        if (!user) return '';
        if (user.is_system_manager) {
            return t.global_f2a89e71 || 'Global';
        }
        var parts = [];
        var countries = user.countries || [];
        if (countries.length) {
            parts.push(countries.join(', '));
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
            if (hasAllCountries(user)) {
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
            } else if (hasAllCountries(user)) {
                html += '<span class="font-medium text-blue-600">' + escapeHtml(t.global_f2a89e71 || 'Global') + '</span>';
            } else {
                var completeRegions = getCompleteRegionNames(user);
                if (!completeRegions.length) {
                    html += '<span class="cursor-help" title="' + escapeHtmlAttr(user.countries.join(', ')) + '">' + user.country_count + ' ' + escapeHtml(t.countries_790d59ef || 'countries') + '</span>';
                } else {
                    completeRegions.forEach(function (region) {
                        html += '<div class="font-medium text-green-600">' + escapeHtml(region) + '</div>';
                    });
                    var catalog = getCountriesByRegionForGlobal(user);
                    var completeRegionsTotal = completeRegions.reduce(function (sum, region) {
                        return sum + ((catalog[region] || []).length);
                    }, 0);
                    var assignedCount = getAssignedCountriesForGlobal(user).length;
                    if (assignedCount > completeRegionsTotal) {
                        html += '<div class="text-gray-500 text-xs mt-1">+' + (assignedCount - completeRegionsTotal) + ' ' + escapeHtml(t.other_countries_b1e7b76a || 'other countries') + '</div>';
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
        user.fds_members = user.fds_members || [];
        user.fds_member_names = user.fds_members.map(function (member) {
            return member.name || member.email || '';
        }).filter(Boolean);
        user.fds_member_names_text = user.fds_member_names.join(', ');
        user.fds_member_export_text = user.fds_members.map(function (member) {
            var name = member.name || member.email || '';
            var countries = member.countries || [];
            return countries.length ? name + ' (' + countries.join(', ') + ')' : name;
        }).filter(Boolean).join('; ');
    });

    var columnDefs = [
        {
            field: 'id',
            headerName: t.id_e369853d,
            width: 80, minWidth: 80, maxWidth: 120,
            hide: true,
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
            cellStyle: AgGridRenderers.userHoverCellStyle,
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
            }
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
            field: 'fds_member_names_text',
            headerName: t.fds_member_7a2c91e4,
            width: 220, minWidth: 160, maxWidth: 320,
            hide: true,
            filter: 'customSetFilter', sortable: true,
            filterValueGetter: function (params) {
                return params.data && params.data.fds_member_names.length
                    ? params.data.fds_member_names
                    : ['-'];
            },
            valueGetter: function (params) {
                return params.data ? params.data.fds_member_names_text : '';
            },
            exportValueGetter: function (params) {
                return params.data ? params.data.fds_member_export_text : '';
            },
            cellRenderer: function (params) {
                if (!params.data || !params.data.fds_members.length) {
                    return '<span class="text-gray-400">-</span>';
                }
                var coverage = params.data.fds_members.map(function (member) {
                    var name = member.name || member.email || '';
                    var countries = member.countries || [];
                    return name + (countries.length ? ': ' + countries.join(', ') : '');
                }).join('; ');
                return '<span class="cursor-help" title="' + escapeHtmlAttr(coverage) + '">'
                    + escapeHtml(params.data.fds_member_names_text)
                    + '</span>';
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
                return getEntitiesExportText(params.data);
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
                    if (colId === 'fds_member_names_text') {
                        return params.node.data.fds_member_export_text || '';
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
