(function () {
    'use strict';
    var cfg = window.assignmentsConfig || {};
    var csrfToken = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';

    var gridHelper = null;
    var gridApi = null;

    var assignmentsData = (function () {
        var el = document.getElementById('assignments-data');
        if (!el) return [];
        try { return JSON.parse(el.textContent || '[]'); } catch (e) { return []; }
    })();

    var columnDefs = [
        {
            field: 'display_name',
            headerName: cfg.t.name_d4a1c2b3,
            width: 260, minWidth: 180, maxWidth: 400,
            filter: 'agTextColumnFilter', sortable: true,
            cellRenderer: function (params) {
                var displayName = params.value || '';
                var escapedName = displayName.replace(/</g, '&lt;').replace(/>/g, '&gt;');
                var editUrl = params.data.edit_url || '';
                var isActive = params.data.is_active !== false;
                var hasCustomName = !!(params.data.custom_name);
                var periodName = (params.data.period_name || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');

                var innerHtml = escapedName;
                if (hasCustomName && periodName) {
                    innerHtml += ' <span class="ml-1 text-gray-400 text-xs font-normal">(' + periodName + ')</span>';
                }

                var nameHtml = editUrl
                    ? '<a href="' + editUrl + '" class="text-blue-600 hover:text-blue-800 hover:underline font-medium">' + innerHtml + '</a>'
                    : innerHtml;

                if (!isActive) {
                    var inactiveInner = escapedName;
                    if (hasCustomName && periodName) {
                        inactiveInner += ' <span class="ml-1 text-gray-400 text-xs font-normal">(' + periodName + ')</span>';
                    }
                    return '<span class="text-gray-500">' + (editUrl
                        ? '<a href="' + editUrl + '" class="text-gray-500 hover:text-gray-700 hover:underline">' + inactiveInner + '</a>'
                        : inactiveInner) + '</span> <span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-gray-100 text-gray-600">' + cfg.t.inactive_6d6fe6a0 + '</span>';
                }
                return nameHtml;
            }
        },
        {
            field: 'template_name',
            headerName: cfg.t.template_fe21f1e3,
            width: 350, minWidth: 250, maxWidth: 500,
            filter: 'agTextColumnFilter', sortable: true,
            cellRenderer: function (params) {
                var name = (params.value || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                if (params.data.has_public_url && params.data.is_public_active) {
                    return '<span class="inline-flex items-center gap-1.5"><i class="fas fa-globe text-green-500" title="' + cfg.t.public_url_active_5aef5e94 + '"></i>' + name + '</span>';
                }
                return name;
            }
        },
        {
            field: 'data_owner_name',
            headerName: cfg.t.data_owner_eba18e59,
            width: 180, minWidth: 120, maxWidth: 280,
            filter: 'agTextColumnFilter', sortable: true,
            cellStyle: AgGridRenderers.userHoverCellStyle,
            cellRenderer: function (params) {
                return AgGridRenderers.userHoverCell(params, {
                    idField: 'data_owner_user_id',
                    nameField: 'data_owner_name',
                    emailField: 'data_owner_email',
                    titleField: 'data_owner_title',
                    activeField: 'data_owner_active',
                    profileColorField: 'data_owner_profile_color',
                    fallbackLabel: cfg.t.not_assigned_40c92dcf,
                    showEmail: false
                });
            }
        },
        {
            field: 'due_date',
            headerName: cfg.t.due_date_4e61d8e3,
            width: 140, minWidth: 110, maxWidth: 180,
            filter: 'agDateColumnFilter', sortable: true,
            comparator: AgGridRenderers.safeStringComparator,
            cellRenderer: function (params) {
                if (!params.value) return '<span class="text-gray-400 italic text-xs">' + cfg.t.not_set_7c05e7e1 + '</span>';
                var d = new Date(params.value + 'T00:00:00');
                return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
            }
        },
        {
            field: 'expiry_date',
            headerName: cfg.t.expiry_date_3f553f31,
            width: 140, minWidth: 110, maxWidth: 180,
            filter: 'agDateColumnFilter', sortable: true,
            comparator: AgGridRenderers.safeStringComparator,
            cellRenderer: function (params) {
                if (!params.value) return '<span class="text-gray-400 italic text-xs">' + cfg.t.not_set_7c05e7e1 + '</span>';
                var d = new Date(params.value + 'T00:00:00');
                var today = new Date();
                today.setHours(0, 0, 0, 0);
                var label = d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
                if (d < today) return '<span class="text-red-600 font-medium">' + label + '</span>';
                return label;
            }
        },
        {
            field: 'actions',
            headerName: cfg.t.actions_9f36b7c9,
            width: 120, minWidth: 100, maxWidth: 150,
            pinned: 'right', lockPinned: true, lockVisible: true,
            sortable: false, filter: false,
            cellRenderer: function (params) {
                var editUrl = params.data.edit_url || '';
                var deleteUrl = params.data.delete_url || '';
                var deleteConfirm = params.data.delete_confirm || '';
                var toggleActiveUrl = params.data.toggle_active_url || '';
                var closeUrl = params.data.close_url || '';
                var reopenClosedUrl = params.data.reopen_closed_url || '';
                var isActive = params.data.is_active !== false;
                var isClosed = params.data.is_closed === true;
                var html = '<div class="flex items-center justify-center gap-2">';
                if (toggleActiveUrl) {
                    html += '<form action="' + toggleActiveUrl + '" method="POST" class="inline-block">';
                    html += '<input type="hidden" name="csrf_token" value="' + csrfToken + '">';
                    html += '<button type="submit" class="' + (isActive ? 'text-amber-600 hover:text-amber-900' : 'text-green-600 hover:text-green-900') + '" title="' + (isActive ? cfg.t.deactivate_a69a5bbb : cfg.t.activate_7de8b7d4) + '" data-loading-text=""><i class="fas fa-fw ' + (isActive ? 'fa-pause-circle' : 'fa-play-circle') + '"></i></button>';
                    html += '</form>';
                }
                if (isClosed && reopenClosedUrl) {
                    html += '<form action="' + reopenClosedUrl + '" method="POST" class="inline-block">';
                    html += '<input type="hidden" name="csrf_token" value="' + csrfToken + '">';
                    html += '<button type="submit" class="text-orange-600 hover:text-orange-900" title="' + cfg.t.reopen_e5aae0b1 + '" data-loading-text=""><i class="fas fa-fw fa-undo"></i></button>';
                    html += '</form>';
                } else if (closeUrl) {
                    var closeConfirm = (params.data.close_confirm || '').replace(/'/g, "\\'");
                    html += '<form action="' + closeUrl + '" method="POST" class="inline-block close-assignment-form" data-confirm="' + closeConfirm + '">';
                    html += '<input type="hidden" name="csrf_token" value="' + csrfToken + '">';
                    html += '<button type="submit" class="close-assignment-btn text-slate-600 hover:text-slate-900" title="' + cfg.t.close_dce5c6fe + '" data-loading-text=""><i class="fas fa-fw fa-lock"></i></button>';
                    html += '</form>';
                }
                if (editUrl) {
                    html += '<a href="' + editUrl + '" class="text-blue-600 hover:text-blue-900" title="' + cfg.t.edit_21ec7a3d + '"><i class="fas fa-pen fa-fw"></i></a>';
                }
                if (deleteUrl) {
                    html += '<form action="' + deleteUrl + '" method="POST" class="inline-block" data-confirm="' + deleteConfirm.replace(/'/g, "\\'") + '" data-confirm-danger="true">';
                    html += '<input type="hidden" name="csrf_token" value="' + csrfToken + '">';
                    html += '<button type="submit" class="text-red-600 hover:text-red-900 delete-assignment-btn" title="' + cfg.t.delete_21f2d0f8 + '" data-loading-text="" data-confirm="' + deleteConfirm.replace(/'/g, "\\'") + '"><i class="fas fa-trash fa-fw"></i></button>';
                    html += '</form>';
                }
                html += '</div>';
                return html;
            }
        }
    ];

    function pinInactiveAssignmentsToBottom(nodes) {
        if (!nodes || !nodes.length) return;
        var active = [];
        var inactive = [];
        for (var i = 0; i < nodes.length; i++) {
            var node = nodes[i];
            if (node.data && node.data.is_active === false) {
                inactive.push(node);
            } else {
                active.push(node);
            }
        }
        nodes.length = 0;
        Array.prototype.push.apply(nodes, active);
        Array.prototype.push.apply(nodes, inactive);
    }

    function initializeGrid() {
        var result = AgGridHelper.create('assignmentsGrid', 'assignments', columnDefs, assignmentsData, {
            gridOptions: {
                postSortRows: function (params) {
                    pinInactiveAssignmentsToBottom(params.nodes);
                }
            },
            onReady: function (api, helper) {
                AgGridHelper.pinActionsColumn(api, null, helper && helper.columnVisibilityManager);
                var urlParams = new URLSearchParams(window.location.search);
                if (urlParams.get('no_data_owner') === '1' && api) {
                    var ownerCol = api.getColumn('data_owner_name');
                    if (ownerCol) {
                        api.setFilterModel({ data_owner_name: { filterType: 'text', type: 'blank' } });
                        api.onFilterChanged();
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

    // Copy public URL handler
    $(document).on('click', '.copy-url-btn', function () {
        var url = $(this).data('copy-url');
        var successMessage = $(this).data('success-message') || cfg.t.copy_success_5b68a4ee;
        var errorMessage = $(this).data('error-message') || cfg.t.copy_error_2b40b24b;
        navigator.clipboard.writeText(url).then(function () {
            if (typeof Utils !== 'undefined' && Utils.showSuccess) {
                Utils.showSuccess(successMessage);
            } else if (window.showAlert) {
                window.showAlert(successMessage, 'success');
            }
        }).catch(function (err) {
            if (typeof Utils !== 'undefined' && Utils.showError) {
                Utils.showError(errorMessage);
            } else if (window.showAlert) {
                window.showAlert(errorMessage, 'error');
            }
        });
    });
})();
