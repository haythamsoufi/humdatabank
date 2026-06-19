(function () {
    'use strict';
    var cfg = window.securityEventsConfig || {};

    var eventsData = (function () {
        var el = document.getElementById('security-events-data');
        if (!el) return [];
        try { return JSON.parse(el.textContent || '[]'); } catch (e) { return []; }
    })();

    var escapeHtml = AgGridRenderers.escapeHtml;
    var escapeHtmlAttr = AgGridRenderers.escapeHtmlAttr;

    function severityVariant(severity) {
        if (severity === 'critical') return 'danger';
        if (severity === 'high') return 'warning';
        if (severity === 'medium') return 'info';
        if (severity === 'low') return 'success';
        return 'neutral';
    }

    function eventTypeVariant(eventType) {
        if (eventType === 'suspicious_login') return 'warning';
        if (eventType === 'brute_force') return 'danger';
        if (eventType === 'unusual_access') return 'info';
        if (eventType === 'data_breach') return 'danger';
        if (eventType === 'privilege_escalation') return 'review';
        return 'neutral';
    }

    var securityEventRenderers = {
        severityBadge: function (params) {
            var severity = (params.value || '').toLowerCase();
            var severityText = severity.charAt(0).toUpperCase() + severity.slice(1);
            return StatusLabels.render(severityText, severityVariant(severity), 'whitespace-nowrap max-w-full');
        },

        eventTypeBadge: function (params) {
            var eventType = (params.value || '').toLowerCase();
            var eventTypeText = eventType.replace(/_/g, ' ').replace(/\b\w/g, function (l) { return l.toUpperCase(); });
            return StatusLabels.render(eventTypeText, eventTypeVariant(eventType), 'whitespace-nowrap max-w-full');
        },

        statusBadge: function (params) {
            var data = params.data;
            if (!data) return '';
            if (data.is_resolved) {
                var html = '<div style="overflow:hidden;width:100%;">';
                html += StatusLabels.render('Resolved', 'success', 'whitespace-nowrap max-w-full');
                if (data.resolved_by_name || data.resolved_by_email) {
                    html += '<div class="text-xs text-gray-500 mt-1" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">by ' + escapeHtml(data.resolved_by_name || data.resolved_by_email) + '</div>';
                }
                if (data.resolved_at) {
                    html += '<div class="text-xs text-gray-500">' + escapeHtml(data.resolved_at) + '</div>';
                }
                html += '</div>';
                return html;
            }
            return StatusLabels.render('Pending', 'pending', 'whitespace-nowrap max-w-full');
        },

        descriptionCell: function (params) {
            var data = params.data;
            if (!data) return '';
            var html = '<div class="text-sm text-gray-900" title="' + escapeHtmlAttr(data.description) + '">' +
                escapeHtml(data.description.length > 80 ? data.description.substring(0, 80) + '...' : data.description) + '</div>';
            if (data.context_data && Object.keys(data.context_data).length > 0) {
                var detailsId = 'details-' + data.id;
                var contextText = JSON.stringify(data.context_data, null, 2);
                html += '<button class="text-xs text-blue-500 hover:text-blue-700 mt-1 toggle-details-btn" type="button" data-details-id="' + detailsId + '">View Context</button>';
                html += '<div class="hidden mt-2 p-3 bg-gray-100 rounded-md border border-gray-200" id="' + detailsId + '">';
                html += '<div class="flex justify-end mb-2">';
                html += '<button class="text-xs text-gray-600 hover:text-blue-700 copy-context-btn inline-flex items-center" type="button" data-context-text="' + escapeHtmlAttr(contextText) + '" title="Copy context">';
                html += '<i class="fas fa-copy mr-1 copy-context-icon"></i><span class="copy-context-label">Copy</span></button>';
                html += '</div>';
                html += '<pre class="text-xs text-gray-700 details-pre">' + escapeHtml(contextText) + '</pre>';
                html += '</div>';
            }
            return html;
        },

        userCell: function (params) {
            return AgGridRenderers.userHoverCell(params, {
                idField: 'user_id',
                nameField: 'user_name',
                emailField: 'user_email',
                titleField: 'user_title',
                activeField: 'user_active',
                profileColorField: 'user_profile_color',
                fallbackLabel: cfg.t.unknown_user_bd4de0d0,
                showEmail: true
            });
        },

        actionsCell: function (params) {
            var data = params.data;
            if (!data) return '';
            if (!data.is_resolved) {
                return '<button class="btn btn-success btn-sm resolve-event-btn" ' +
                    'data-event-id="' + data.id + '" data-event-description="' + escapeHtmlAttr(data.description) + '">' +
                    '<i class="fas fa-check mr-1"></i> Resolve</button>';
            } else if (data.resolution_notes) {
                var resolutionId = 'resolution-' + data.id;
                return '<button class="text-xs text-blue-500 hover:text-blue-700 toggle-details-btn" type="button" data-details-id="' + resolutionId + '">View Resolution</button>' +
                    '<div class="hidden mt-2 p-3 bg-gray-100 rounded-md border border-gray-200 max-w-xs" id="' + resolutionId + '">' +
                    '<p class="text-xs text-gray-700 details-pre">' + escapeHtml(data.resolution_notes) + '</p></div>';
            }
            return '';
        }
    };

    function formatDescriptionForClipboard(data) {
        if (!data) return '';
        var description = data.description || '';
        var contextData = data.context_data;
        if (!contextData || Object.keys(contextData).length === 0) return description;
        return description + '\n\nContext:\n' + JSON.stringify(contextData, null, 2);
    }

    function fallbackCopyText(text) {
        var textArea = document.createElement('textarea');
        textArea.value = text;
        textArea.setAttribute('readonly', '');
        textArea.style.position = 'fixed';
        textArea.style.opacity = '0';
        document.body.appendChild(textArea);
        textArea.select();
        try { document.execCommand('copy'); } catch (err) {
            window.__clientWarn && window.__clientWarn('Failed to copy context text', err);
        } finally { document.body.removeChild(textArea); }
    }

    function showCopySuccess(buttonEl) {
        if (!buttonEl) return;
        var iconEl = buttonEl.querySelector('.copy-context-icon');
        var labelEl = buttonEl.querySelector('.copy-context-label');
        if (!iconEl || !labelEl) return;
        if (!buttonEl.dataset.originalIconClass) buttonEl.dataset.originalIconClass = iconEl.className;
        if (!buttonEl.dataset.originalLabel) buttonEl.dataset.originalLabel = labelEl.textContent || 'Copy';
        iconEl.className = 'fas fa-check mr-1 copy-context-icon';
        labelEl.textContent = 'Copied!';
        buttonEl.classList.remove('text-gray-600', 'hover:text-blue-700');
        buttonEl.classList.add('text-green-600');
        if (buttonEl._copyResetTimer) clearTimeout(buttonEl._copyResetTimer);
        buttonEl._copyResetTimer = setTimeout(function () {
            iconEl.className = buttonEl.dataset.originalIconClass || 'fas fa-copy mr-1 copy-context-icon';
            labelEl.textContent = buttonEl.dataset.originalLabel || 'Copy';
            buttonEl.classList.remove('text-green-600');
            buttonEl.classList.add('text-gray-600', 'hover:text-blue-700');
            buttonEl._copyResetTimer = null;
        }, 1500);
    }

    function copyTextToClipboard(text, onSuccess) {
        if (!text) return;
        if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
            navigator.clipboard.writeText(text).then(function () {
                if (typeof onSuccess === 'function') onSuccess();
            }).catch(function () {
                fallbackCopyText(text);
                if (typeof onSuccess === 'function') onSuccess();
            });
        } else {
            fallbackCopyText(text);
            if (typeof onSuccess === 'function') onSuccess();
        }
    }

    var columnDefs = [
        {
            field: 'timestamp',
            headerName: cfg.t.timestamp_a3d5de3e,
            width: 170,
            minWidth: 160,
            cellRenderer: AgGridRenderers.dateTimeDual,
            filter: 'agDateColumnFilter',
            sortable: true,
            lockVisible: true
        },
        {
            field: 'event_type',
            headerName: cfg.t.event_type_8a29d87b,
            width: 190,
            minWidth: 160,
            cellRenderer: securityEventRenderers.eventTypeBadge,
            filter: 'customSetFilter',
            sortable: true
        },
        {
            field: 'severity',
            headerName: cfg.t.severity_5a1caa0f,
            width: 110,
            minWidth: 100,
            cellRenderer: securityEventRenderers.severityBadge,
            filter: 'customSetFilter',
            sortable: true,
            comparator: function (a, b) {
                var order = { 'critical': 0, 'high': 1, 'medium': 2, 'low': 3 };
                return (order[a] || 99) - (order[b] || 99);
            }
        },
        {
            field: 'description',
            headerName: cfg.t.description_b5a7adde,
            flex: 1,
            minWidth: 220,
            cellRenderer: securityEventRenderers.descriptionCell,
            filter: 'agTextColumnFilter',
            sortable: true,
            tooltipValueGetter: function (params) { return params.data ? params.data.description : ''; }
        },
        {
            field: 'ip_address',
            headerName: cfg.t.ip_address_5b8c99da,
            width: 170,
            minWidth: 150,
            hide: true,
            filter: 'agTextColumnFilter',
            sortable: true,
            cellRenderer: function (params) {
                if (params.value) return '<div class="text-sm text-gray-900 font-mono" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + escapeHtml(params.value) + '</div>';
                return '<span class="text-sm text-gray-500">N/A</span>';
            }
        },
        {
            field: 'user_email',
            headerName: cfg.t.user_8f9bfe9d,
            width: 190,
            minWidth: 160,
            cellRenderer: securityEventRenderers.userCell,
            cellStyle: { overflow: 'hidden' },
            filter: 'agTextColumnFilter',
            sortable: true,
            valueGetter: function (params) {
                return params.data ? (params.data.user_name || params.data.user_email || 'Unknown') : '';
            }
        },
        {
            field: 'is_resolved',
            headerName: cfg.t.status_ec53a8c4,
            width: 160,
            minWidth: 140,
            cellRenderer: securityEventRenderers.statusBadge,
            cellStyle: { overflow: 'hidden' },
            filter: 'customSetFilter',
            sortable: true
        },
        {
            field: 'actions',
            headerName: cfg.t.actions_9f36b7c9,
            width: 140,
            minWidth: 120,
            cellRenderer: securityEventRenderers.actionsCell,
            sortable: false,
            filter: false,
            pinned: 'right',
            lockPinned: true
        }
    ];

    var resolveUrlBase = cfg.urls.resolveUrlBase;
    var loadingEl = document.getElementById('securityEventsGrid-loading');
    var emptyEl = document.getElementById('securityEventsGrid-empty');
    var containerEl = document.getElementById('securityEventsGrid-container');

    if (!eventsData || eventsData.length === 0) {
        if (loadingEl) loadingEl.style.display = 'none';
        if (emptyEl) emptyEl.style.display = 'block';
        if (containerEl) containerEl.style.display = 'none';
        window.securityEventsGridApi = null;
        window.securityEventsGridHelper = null;
    } else {
        var gridHelper = new AgGridHelper({
            containerId: 'securityEventsGrid',
            templateId: (cfg.templateId || 'security-events-analytics') + '-v2',
            columnDefs: columnDefs,
            rowData: eventsData,
            columnVisibilityOptions: {
                persistOnChange: true,
                showPanelButton: true,
                enableExport: true,
                enableReset: true
            },
            options: {
                pagination: true,
                paginationPageSize: 25,
                paginationPageSizeSelector: [10, 25, 50, 100],
                rowHeight: 80,
                sizeColumnsToFitOnInit: false,
                sizeColumnsToFitOnColumnChange: false,
                processCellForClipboard: function (params) {
                    if (!params || !params.column || !params.node || !params.node.data) {
                        return params && params.value != null ? params.value : '';
                    }
                    if (params.column.getColId() === 'description') {
                        return formatDescriptionForClipboard(params.node.data);
                    }
                    return params.value != null ? params.value : '';
                },
                getRowClass: function (params) {
                    if (params.data) {
                        if (params.data.severity === 'critical') return 'ag-row-severity-critical';
                        if (params.data.severity === 'high') return 'ag-row-severity-high';
                    }
                    return '';
                }
            }
        });

        var gridApi = gridHelper.initialize();
        if (loadingEl) loadingEl.style.display = 'none';
        if (containerEl) containerEl.style.display = 'block';
        if (emptyEl) emptyEl.style.display = 'none';

        window.securityEventsGridApi = gridApi;
        window.securityEventsGridHelper = gridHelper;

        // Modal wiring via ModalUtils
        var resolveForm = document.getElementById('resolveForm');
        var eventDescriptionModalInput = document.getElementById('eventDescriptionModal');
        var resolveModalCtrl = window.ModalUtils
            ? window.ModalUtils.makeModal('#resolveModal')
            : { openModal: function() {}, closeModal: function() {} };

        function openResolveModal(eventId, description) {
            if (resolveForm) {
                resolveForm.action = resolveUrlBase.replace(/\/0\/resolve$/, '/' + String(eventId) + '/resolve');
            }
            if (eventDescriptionModalInput) eventDescriptionModalInput.value = description;
            resolveModalCtrl.openModal();
        }

        function toggleDetails(elementId) {
            var element = document.getElementById(elementId);
            if (element) element.classList.toggle('hidden');
        }

        document.addEventListener('click', function (event) {
            if (event.target.closest('.resolve-event-btn')) {
                var btn = event.target.closest('.resolve-event-btn');
                openResolveModal(btn.getAttribute('data-event-id'), btn.getAttribute('data-event-description') || '');
            } else if (event.target.closest('.copy-context-btn')) {
                var btn2 = event.target.closest('.copy-context-btn');
                copyTextToClipboard(btn2.getAttribute('data-context-text') || '', function () { showCopySuccess(btn2); });
            } else if (event.target.closest('.toggle-details-btn')) {
                var btn3 = event.target.closest('.toggle-details-btn');
                toggleDetails(btn3.getAttribute('data-details-id'));
            }
        });
    }
})();
