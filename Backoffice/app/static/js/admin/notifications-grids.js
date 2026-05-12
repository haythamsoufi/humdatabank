/**
 * Admin Notifications Grids Module
 * Handles AG Grid initialization and management for notifications and campaigns
 */

/**
 * Utility function to enforce campaigns column layout
 * Ensures 'actions' column is always last and 'recipients_count' stays unpinned
 */
function enforceCampaignsColumnLayout(apiOrParams) {
    const gridApi = apiOrParams && apiOrParams.api ? apiOrParams.api : apiOrParams;
    const columnApi = apiOrParams && apiOrParams.columnApi ? apiOrParams.columnApi : (gridApi && gridApi.columnApi ? gridApi.columnApi : null);
    const applyApi = (columnApi && typeof columnApi.applyColumnState === 'function') ? columnApi : gridApi;

    if (!applyApi || typeof applyApi.applyColumnState !== 'function') return;

    try {
        // Get column IDs from the most reliable source available
        let colIds = [];
        if (columnApi && typeof columnApi.getAllColumns === 'function') {
            colIds = (columnApi.getAllColumns() || [])
                .map(col => (col && typeof col.getColId === 'function') ? col.getColId() : null)
                .filter(Boolean);
        } else if (gridApi && typeof gridApi.getColumns === 'function') {
            colIds = (gridApi.getColumns() || [])
                .map(col => (col && typeof col.getColId === 'function') ? col.getColId() : null)
                .filter(Boolean);
        }

        if (!colIds.length) return;

        // Desired order: everything except actions, then actions at the end.
        const orderedIds = colIds.filter(id => id !== 'actions');
        if (colIds.includes('actions')) orderedIds.push('actions');

        const state = orderedIds.map(function(id) {
            if (id === 'actions' || id === 'recipients_count') {
                return { colId: id, pinned: null };
            }
            return { colId: id };
        });

        applyApi.applyColumnState({ state: state, applyOrder: true });

        // Extra safety: explicitly move Actions to the last displayed position.
        // Some AG Grid versions/state restorers can ignore applyOrder in edge cases.
        if (columnApi && typeof columnApi.moveColumn === 'function' && colIds.includes('actions')) {
            columnApi.moveColumn('actions', orderedIds.length - 1);
        } else if (columnApi && typeof columnApi.moveColumns === 'function' && colIds.includes('actions')) {
            columnApi.moveColumns(['actions'], orderedIds.length - 1);
        }
    } catch (e) {
        console.warn('Failed to enforce campaigns column layout:', e);
    }
}

/**
 * Shared factory for AG Grid initialization with container-readiness retry,
 * sync/async AgGridHelper construction, and window export.
 *
 * Eliminates duplication between notifications and campaigns grid init.
 *
 * @param {Object}   cfg
 * @param {string}   cfg.label                     - Grid name for log messages
 * @param {string}   cfg.containerId               - DOM id of the ag-grid wrapper div
 * @param {string}   cfg.loadingId                 - DOM id of the loading spinner element
 * @param {string}   cfg.panelId                   - DOM id of the tab panel (visibility target)
 * @param {Function} cfg.shouldSetContainerDisplay  - () => boolean
 * @param {Function} cfg.getData                   - () => Array (current row data)
 * @param {Function} cfg.buildHelperConfig          - () => Object (AgGridHelper ctor config)
 * @param {Object}   [cfg.windowExportKey]          - { exportApiName, helperKey } window property names for export/debug
 * @param {Function} [cfg.onGridReady]              - (gridApi, gridHelper) => void
 * @param {Function} [cfg.beforeInit]               - (loadingEl, containerEl, gridEl) => false|void
 *                                                    Return false to abort current init attempt.
 * @param {number}   [cfg.maxRetries=10]
 * @param {number}   [cfg.checkDelay=100]           - ms before first dimension check
 * @param {number}   [cfg.retryInterval=300]        - ms between retry attempts
 * @returns {{ checkAndInitialize: Function, initializeGrid: Function, state: Object }}
 */
function createGridInitializer(cfg) {
    var label          = cfg.label;
    var containerId    = cfg.containerId;
    var loadingId      = cfg.loadingId;
    var panelId        = cfg.panelId;
    var shouldSetDisp  = cfg.shouldSetContainerDisplay;
    var getData        = cfg.getData;
    var buildConfig    = cfg.buildHelperConfig;
    var exportKey      = cfg.windowExportKey;
    var onGridReady    = cfg.onGridReady;
    var beforeInit     = cfg.beforeInit;
    var MAX_RETRIES    = cfg.maxRetries    || 10;
    var CHECK_DELAY    = cfg.checkDelay    || 100;
    var RETRY_INTERVAL = cfg.retryInterval || 300;

    var state = {
        gridHelper:   null,
        gridApi:      null,
        initialized:  false,
        initializing: false,
        retryCount:   0
    };

    function log()  { if (window.__clientLog)  window.__clientLog.apply(null, arguments); }
    function warn() { if (window.__clientWarn) window.__clientWarn.apply(null, arguments); }

    function showGrid() {
        var ld = document.getElementById(loadingId);
        var ct = document.getElementById(panelId);
        if (ld) ld.style.display = 'none';
        if (ct && shouldSetDisp()) ct.style.display = 'block';
    }

    function exposeToWindow() {
        if (!exportKey) return;
        if (exportKey.exportApiName) window[exportKey.exportApiName] = state.gridApi;
        if (exportKey.helperKey) window[exportKey.helperKey] = state.gridHelper;
    }

    function initializeGrid() {
        var data = getData();
        log('Initializing ' + label + ' grid (' + (data ? data.length : 0) + ' rows)');

        var loadingEl       = document.getElementById(loadingId);
        var containerEl     = document.getElementById(panelId);
        var gridContainerEl = document.getElementById(containerId);

        if (beforeInit && beforeInit(loadingEl, containerEl, gridContainerEl) === false) {
            return;
        }

        if (!data || data.length === 0) {
            log('No ' + label + ' data');
            showGrid();
            return;
        }

        try {
            state.gridHelper = new AgGridHelper(buildConfig());
            state.gridApi    = state.gridHelper.initialize();

            if (!state.gridApi) {
                log('Trying async initialization for ' + label + ' grid...');
                state.gridHelper.initializeAsync(3000).then(function(api) {
                    log(label + ' grid initialized (async)');
                    state.gridApi = api;
                    exposeToWindow();
                    if (onGridReady) onGridReady(state.gridApi, state.gridHelper);
                    showGrid();
                }).catch(function(error) {
                    console.error('Failed to initialize ' + label + ' grid:', error);
                    showGrid();
                });
            } else {
                log(label + ' grid initialized (sync)');
                exposeToWindow();
                if (onGridReady) onGridReady(state.gridApi, state.gridHelper);
                showGrid();
            }
        } catch (error) {
            console.error('Error initializing ' + label + ' grid:', error);
            showGrid();
        }
    }

    function checkAndInitialize() {
        var panelEl = document.getElementById(panelId);

        if (state.initialized || state.initializing) return;

        if (!panelEl || panelEl.classList.contains('hidden')) {
            state.initializing = false;
            return;
        }

        state.initializing = true;

        if (shouldSetDisp()) {
            var ct = document.getElementById(panelId);
            if (ct) ct.style.display = 'block';
        }
        var ld = document.getElementById(loadingId);
        if (ld) ld.style.display = 'none';

        var gridContainer = document.getElementById(containerId);
        if (gridContainer) {
            setTimeout(function() {
                var rect = gridContainer.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    log('Initializing ' + label + ' grid - container ready');
                    initializeGrid();
                    state.initialized  = true;
                    state.initializing = false;
                    state.retryCount   = 0;
                } else if (state.retryCount < MAX_RETRIES) {
                    state.retryCount++;
                    state.initializing = false;
                    warn(label + ' grid container not ready (attempt ' +
                         state.retryCount + '/' + MAX_RETRIES + '), retrying...');
                    setTimeout(function() { checkAndInitialize(); }, RETRY_INTERVAL);
                } else {
                    warn('Max retries reached for ' + label + ' grid, initializing anyway');
                    initializeGrid();
                    state.initialized  = true;
                    state.initializing = false;
                }
            }, CHECK_DELAY);
        } else {
            setTimeout(function() {
                initializeGrid();
                state.initialized  = true;
                state.initializing = false;
            }, CHECK_DELAY + 100);
        }
    }

    return {
        checkAndInitialize: checkAndInitialize,
        initializeGrid:     initializeGrid,
        state:              state
    };
}

/**
 * Notifications Grid Manager
 * Handles initialization and management of the notifications AG Grid
 */
class NotificationsGridManager {
    constructor(options = {}) {
        this.data = options.data || window.notificationsData || [];
        this.translations = options.translations || window.NOTIFICATION_TRANSLATIONS || {};
        this.columnDefs = options.columnDefs || this.buildColumnDefs();
        this.containerId = options.containerId || 'notificationsGrid';
        this.templateId = options.templateId || 'notifications';
        this.loadingId = options.loadingId || 'notifications-loading';
        this.containerSelector = options.containerSelector || 'panel-view-all';

        var self = this;
        this._gridInit = createGridInitializer({
            label: 'notifications',
            containerId: this.containerId,
            loadingId: this.loadingId,
            panelId: this.containerSelector,
            shouldSetContainerDisplay: function() { return self._shouldSetContainerDisplay(); },
            getData: function() { return self.data; },
            buildHelperConfig: function() {
                return {
                    containerId: self.containerId,
                    templateId: self.templateId,
                    columnDefs: self.columnDefs,
                    rowData: self.data,
                    options: {
                        getRowHeight: function() { return null; }
                    },
                    columnVisibilityOptions: {
                        enableExport: false,
                        enableReset: true
                    }
                };
            },
            windowExportKey: {
                exportApiName: 'notificationsGridApi',
                helperKey: 'notificationsGridHelper'
            },
            checkDelay: 100,
            retryInterval: 300
        });

        // Expose to window for backward compatibility
        window.notificationsGridManager = this;
    }

    /**
     * When the grid "container" is the tab panel (#panel-view-all), do not set inline display — that would
     * fight AdminUnderlineTabs' .hidden toggle on the same element.
     */
    _shouldSetContainerDisplay() {
        return this.containerSelector !== 'panel-view-all';
    }

    get gridApi()     { return this._gridInit ? this._gridInit.state.gridApi     : null; }
    get gridHelper()  { return this._gridInit ? this._gridInit.state.gridHelper  : null; }
    get initialized() { return this._gridInit ? this._gridInit.state.initialized : false; }

    /**
     * Build column definitions for notifications grid
     */
    buildColumnDefs() {
        const t = this.translations;
        return [
            {
                field: 'user_name',
                headerName: t.user || 'User',
                width: 300,
                minWidth: 220,
                maxWidth: 440,
                filter: 'agTextColumnFilter',
                sortable: true,
                cellRenderer: (params) => {
                    const iconHtml = this.renderNotificationPreview(params);
                    const userHtml = AgGridRenderers.userHoverCell(params, {
                        idField: 'user_id',
                        nameField: 'user_name',
                        emailField: 'user_email',
                        titleField: 'user_title',
                        activeField: 'user_active',
                        profileColorField: 'user_profile_color',
                        fallbackLabel: 'Unknown User',
                        showEmail: true
                    });
                    return '<div class="notification-user-cell flex items-center gap-2" style="width:100%;min-width:0;overflow:hidden">'
                        + '<div class="flex-shrink-0 flex items-center justify-center">' + iconHtml + '</div>'
                        + '<div class="min-w-0 flex-1 overflow-hidden">' + userHtml + '</div>'
                        + '</div>';
                },
                cellStyle: { overflow: 'hidden', 'line-height': '1.4' }
            },
            {
                field: 'user_email',
                headerName: t.email || 'Email',
                width: 250,
                minWidth: 200,
                maxWidth: 350,
                filter: 'agTextColumnFilter',
                sortable: true
            },
            {
                field: 'notification_type',
                headerName: t.type || 'Type',
                width: 180,
                minWidth: 150,
                maxWidth: 250,
                filter: 'customSetFilter',
                sortable: true,
                cellRenderer: (params) => this.renderNotificationType(params)
            },
            {
                field: 'title',
                headerName: t.title || 'Title',
                width: 250,
                minWidth: 200,
                maxWidth: 400,
                filter: 'agTextColumnFilter',
                sortable: true,
                cellStyle: { 'white-space': 'normal', 'word-wrap': 'break-word', 'line-height': '1.4' }
            },
            {
                field: 'message',
                headerName: t.message || 'Message',
                width: 450,
                minWidth: 300,
                maxWidth: 700,
                filter: 'agTextColumnFilter',
                sortable: true,
                hide: true,
                cellStyle: { 'white-space': 'normal', 'word-wrap': 'break-word', 'line-height': '1.4' }
            },
            {
                field: 'priority',
                headerName: t.priority || 'Priority',
                width: 120,
                minWidth: 100,
                maxWidth: 150,
                filter: 'customSetFilter',
                sortable: true,
                cellRenderer: (params) => this.renderPriority(params)
            },
            {
                field: 'is_read',
                headerName: t.status || 'Status',
                width: 120,
                minWidth: 100,
                maxWidth: 150,
                filter: 'customSetFilter',
                sortable: true,
                cellRenderer: (params) => this.renderStatus(params)
            },
            {
                field: 'created_at',
                headerName: t.createdAt || 'Created At',
                width: 180,
                minWidth: 150,
                maxWidth: 250,
                filter: 'agTextColumnFilter',
                sortable: true,
                cellRenderer: AgGridRenderers.dateTime
            },
            {
                field: 'related_url',
                headerName: t.actions || 'Actions',
                width: 100,
                minWidth: 80,
                maxWidth: 150,
                lockVisible: true,
                sortable: false,
                filter: false,
                cellRenderer: (params) => this.renderActions(params)
            }
        ];
    }

    /**
     * Avatar / action icon column (matches user notifications center UI)
     */
    renderNotificationPreview(params) {
        const d = params.data || {};
        const actor = d.actor;
        const actionSuffix = (d.actor_action_icon || '').replace(/[^a-zA-Z0-9\-]/g, '');
        const iconRaw = (d.icon || '').replace(/[^a-zA-Z0-9\-\s]/g, '').trim();
        const actionClass = actionSuffix ? `fas ${actionSuffix}` : (iconRaw || 'fas fa-bell');
        const priority = (d.priority || 'normal').toString().toLowerCase();
        const isRead = d.is_read;
        let colorClass = 'text-gray-500';
        if (!isRead) {
            if (priority === 'urgent') colorClass = 'text-red-600';
            else if (priority === 'high') colorClass = 'text-orange-600';
            else colorClass = 'text-blue-600';
        }
        const esc = (s) => String(s == null ? '' : s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
        if (actor && actor.initials) {
            const bg = esc(actor.profile_color || '#64748b');
            const initials = esc(String(actor.initials).slice(0, 2));
            const badge = actionSuffix
                ? `<span class="notification-grid-actor-badge" aria-hidden="true"><i class="fas ${actionSuffix} notification-grid-actor-badge-icon"></i></span>`
                : '';
            return `<div class="notification-grid-actor relative flex-shrink-0" style="width:2.25rem;height:2.25rem" aria-hidden="true">
                <div class="notification-grid-actor-circle rounded-full flex items-center justify-center text-white text-xs font-semibold" style="width:2.25rem;height:2.25rem;background-color:${bg}">${initials}</div>${badge}
            </div>`;
        }
        return `<div class="notification-grid-action-circle rounded-full flex items-center justify-center" style="width:2.25rem;height:2.25rem;background-color:#f3f4f6" aria-hidden="true">
            <i class="${actionClass} text-sm ${colorClass}"></i>
        </div>`;
    }

    /**
     * Render notification type cell
     */
    renderNotificationType(params) {
        if (!params.value) return '';
        // Use formatted display value from backend if available
        return params.data.notification_type_display || params.value.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    }

    /**
     * Render priority cell
     */
    renderPriority(params) {
        if (!params.value) return '';
        const priority = params.value.toLowerCase();
        const colors = {
            'normal': 'text-blue-600',
            'high': 'text-orange-600',
            'urgent': 'text-red-600'
        };
        const color = colors[priority] || 'text-gray-600';
        const display = params.data.priority_display || params.value.charAt(0).toUpperCase() + params.value.slice(1);
        return `<span class="${color} font-medium">${display}</span>`;
    }

    /**
     * Render status cell
     */
    renderStatus(params) {
        const t = this.translations;
        if (params.data.is_archived) {
            return `<span class="text-gray-500"><i class="fas fa-archive mr-1"></i>${t.archived || 'Archived'}</span>`;
        } else if (params.value) {
            return `<span class="text-green-600"><i class="fas fa-check-circle mr-1"></i>${t.read || 'Read'}</span>`;
        } else {
            return `<span class="text-blue-600"><i class="fas fa-circle mr-1"></i>${t.unread || 'Unread'}</span>`;
        }
    }

    /**
     * Render actions cell
     */
    renderActions(params) {
        const t = this.translations;
        const data = params.data;
        let html = '<div class="flex items-center justify-center gap-2">';
        if (data.related_url) {
            html += `<a href="${data.related_url}" class="text-blue-600 hover:text-blue-900" title="${t.view || 'View'}"><i class="fas fa-external-link-alt fa-fw"></i></a>`;
        }
        html += '</div>';
        return html;
    }

    initializeGrid() {
        this._gridInit.initializeGrid();
    }

    checkAndInitialize() {
        this._gridInit.checkAndInitialize();
    }

    /**
     * Initialize tab observers and event listeners
     */
    init() {
        // Wait for DOM to be ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this._setupTabObservers());
        } else {
            this._setupTabObservers();
        }
    }

    /**
     * Set up tab visibility observers
     */
    _setupTabObservers() {
        const viewAllContent = document.getElementById('panel-view-all');

        // Initialize immediately if tab is already visible
        if (viewAllContent && !viewAllContent.classList.contains('hidden')) {
            this.checkAndInitialize();
        }

        // Panel visibility is toggled by AdminUnderlineTabs (same pattern as manage_settings)
        if (viewAllContent) {
            let observerTimeout = null;
            const observer = new MutationObserver((mutations) => {
                mutations.forEach((mutation) => {
                    if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
                        // Debounce observer calls to prevent multiple rapid initializations
                        clearTimeout(observerTimeout);
                        observerTimeout = setTimeout(() => {
                            this.checkAndInitialize();
                        }, 100);
                    }
                });
            });
            observer.observe(viewAllContent, { attributes: true, attributeFilter: ['class'] });
        }
    }
}

/**
 * Campaigns Grid Manager
 * Handles initialization and management of the campaigns AG Grid
 */
class CampaignsGridManager {
    constructor(options = {}) {
        this.data = options.data || window.campaignsData || [];
        this.translations = options.translations || window.NOTIFICATION_TRANSLATIONS || {};
        this.columnDefs = options.columnDefs || this.buildColumnDefs();
        this.containerId = options.containerId || 'campaignsGrid';
        this.templateId = options.templateId || 'campaigns';
        this.loadingId = options.loadingId || 'campaigns-loading';
        this.containerSelector = options.containerSelector || 'panel-campaigns';

        var self = this;
        this._gridInit = createGridInitializer({
            label: 'campaigns',
            containerId: this.containerId,
            loadingId: this.loadingId,
            panelId: this.containerSelector,
            shouldSetContainerDisplay: function() { return self._shouldSetContainerDisplay(); },
            getData: function() { return self.data; },
            buildHelperConfig: function() {
                return {
                    containerId: self.containerId,
                    templateId: self.templateId,
                    columnDefs: self.columnDefs,
                    rowData: self.data,
                    options: {
                        getRowHeight: function() { return null; },
                        suppressColumnMoveAnimation: false,
                        suppressMovableColumns: false,
                        onFirstDataRendered: function(params) {
                            setTimeout(function() { self.enforceColumnLayout(params); }, 0);
                            setTimeout(function() { self.enforceColumnLayout(params); }, 250);
                        }
                    },
                    columnVisibilityOptions: {
                        enableExport: false,
                        enableReset: true
                    }
                };
            },
            windowExportKey: {
                exportApiName: 'campaignsGridApi',
                helperKey: 'campaignsGridHelper'
            },
            onGridReady: function(gridApi) {
                setTimeout(function() { self.enforceColumnLayout(gridApi); }, 50);
            },
            beforeInit: function(loadingEl, containerEl, gridContainerEl) {
                // Campaigns-specific: show container and set minHeight before data check
                if (loadingEl) loadingEl.style.display = 'none';
                if (containerEl && self._shouldSetContainerDisplay()) {
                    containerEl.style.display = 'block';
                    if (containerEl.style.height === '' || containerEl.style.height === 'auto') {
                        containerEl.style.minHeight = '400px';
                    }
                }
                // Campaigns-specific: ensure grid container has dimensions
                if (gridContainerEl) {
                    var rect = gridContainerEl.getBoundingClientRect();
                    if (rect.width === 0 || rect.height === 0) {
                        var _log = window.__clientLog || function() {};
                        _log('Grid container has no dimensions, waiting...');
                        setTimeout(function() { self._gridInit.initializeGrid(); }, 200);
                        return false;
                    }
                    if (!gridContainerEl.style.height || gridContainerEl.style.height === 'auto') {
                        gridContainerEl.style.height = '600px';
                    }
                }
            },
            checkDelay: 200,
            retryInterval: 300
        });

        // Expose to window for backward compatibility
        window.campaignsGridManager = this;
    }

    _shouldSetContainerDisplay() {
        return this.containerSelector !== 'panel-campaigns';
    }

    get gridApi()     { return this._gridInit ? this._gridInit.state.gridApi     : null; }
    get gridHelper()  { return this._gridInit ? this._gridInit.state.gridHelper  : null; }
    get initialized() { return this._gridInit ? this._gridInit.state.initialized : false; }

    /**
     * Build column definitions for campaigns grid
     */
    buildColumnDefs() {
        const t = this.translations;
        return [
            {
                field: 'name',
                headerName: t.campaignName || 'Campaign Name',
                width: 250,
                minWidth: 200,
                maxWidth: 400,
                filter: 'agTextColumnFilter',
                sortable: true,
                cellStyle: { 'white-space': 'normal', 'line-height': '1.4' }
            },
            {
                field: 'title',
                headerName: t.title || 'Title',
                width: 250,
                minWidth: 200,
                maxWidth: 400,
                filter: 'agTextColumnFilter',
                sortable: true,
                cellStyle: { 'white-space': 'normal', 'word-wrap': 'break-word', 'line-height': '1.4' }
            },
            {
                field: 'status',
                headerName: t.status || 'Status',
                width: 150,
                minWidth: 130,
                maxWidth: 200,
                filter: 'customSetFilter',
                sortable: true,
                cellRenderer: (params) => this.renderStatus(params)
            },
            {
                field: 'priority',
                headerName: t.priority || 'Priority',
                width: 120,
                minWidth: 100,
                maxWidth: 150,
                filter: 'customSetFilter',
                sortable: true,
                cellRenderer: (params) => this.renderPriority(params)
            },
            {
                field: 'scheduled_for',
                headerName: t.scheduledFor || 'Scheduled For',
                width: 220,
                minWidth: 180,
                maxWidth: 300,
                filter: 'agTextColumnFilter',
                sortable: true,
                cellRenderer: (params) => this.renderScheduledFor(params)
            },
            {
                field: 'created_by_name',
                headerName: t.createdBy || 'Created By',
                width: 200,
                minWidth: 150,
                maxWidth: 300,
                filter: 'agTextColumnFilter',
                sortable: true,
                cellRenderer: function(params) {
                    return AgGridRenderers.userHoverCell(params, {
                        idField: 'created_by_id',
                        nameField: 'created_by_name',
                        emailField: 'created_by_email',
                        titleField: 'created_by_title',
                        activeField: 'created_by_active',
                        profileColorField: 'created_by_profile_color',
                        fallbackLabel: 'Unknown User',
                        showEmail: false
                    });
                },
                cellStyle: { overflow: 'hidden', 'line-height': '1.4' }
            },
            {
                field: 'sent_count',
                headerName: t.sent || 'Sent',
                width: 100,
                minWidth: 80,
                maxWidth: 120,
                filter: 'agNumberColumnFilter',
                sortable: true,
                cellRenderer: (params) => params.value || 0
            },
            {
                field: 'created_at',
                headerName: t.createdAt || 'Created At',
                width: 220,
                minWidth: 180,
                maxWidth: 300,
                filter: 'agTextColumnFilter',
                sortable: true,
                cellRenderer: AgGridRenderers.dateTime
            },
            {
                field: 'recipients_count',
                headerName: t.recipients || 'Recipients',
                width: 150,
                minWidth: 120,
                maxWidth: 200,
                filter: 'agNumberColumnFilter',
                sortable: true,
                cellRenderer: (params) => this.renderRecipientsCount(params)
            },
            {
                field: 'actions',
                headerName: t.actions || 'Actions',
                width: 200,
                minWidth: 150,
                maxWidth: 250,
                lockVisible: true,
                sortable: false,
                filter: false,
                cellRenderer: (params) => this.renderActions(params)
            }
        ];
    }

    /**
     * Render status cell
     */
    renderStatus(params) {
        if (!params.value) return '';
        const status = params.value.toLowerCase();
        const badges = {
            'draft': '<span class="px-2 py-1 text-xs font-medium rounded bg-gray-100 text-gray-800">Draft</span>',
            'scheduled': '<span class="px-2 py-1 text-xs font-medium rounded bg-blue-100 text-blue-800">Scheduled</span>',
            'sent': '<span class="px-2 py-1 text-xs font-medium rounded bg-green-100 text-green-800">Sent</span>',
            'cancelled': '<span class="px-2 py-1 text-xs font-medium rounded bg-red-100 text-red-800">Cancelled</span>'
        };
        return badges[status] || `<span class="px-2 py-1 text-xs font-medium rounded bg-gray-100 text-gray-800">${params.data.status_display || params.value}</span>`;
    }

    /**
     * Render priority cell
     */
    renderPriority(params) {
        if (!params.value) return '';
        const priority = params.value.toLowerCase();
        const colors = {
            'normal': 'text-blue-600',
            'high': 'text-orange-600',
            'urgent': 'text-red-600'
        };
        const color = colors[priority] || 'text-gray-600';
        const display = params.data.priority_display || params.value.charAt(0).toUpperCase() + params.value.slice(1);
        return `<span class="${color} font-medium">${display}</span>`;
    }

    /**
     * Render scheduled for cell
     */
    renderScheduledFor(params) {
        if (!params.value) {
            return '<span class="text-gray-400">Not scheduled</span>';
        }
        return params.value;
    }

    /**
     * Render recipients count cell
     */
    renderRecipientsCount(params) {
        const t = this.translations;
        const count = params.value || 0;
        if (count === 0) {
            return '<span class="text-gray-400">0</span>';
        }
        return `<button type="button" class="text-blue-600 hover:text-blue-800 hover:underline font-medium cursor-pointer" data-campaign-id="${params.data.id}" data-action="view-recipients">${count}</button>`;
    }

    /**
     * Render actions cell
     */
    renderActions(params) {
        const t = this.translations;
        const data = params.data;
        let html = '<div class="flex items-center justify-center gap-2">';

        if (data.status === 'draft' || data.status === 'scheduled') {
            html += `<button type="button" data-action="send" data-campaign-id="${data.id}" class="text-blue-600 hover:text-blue-800 text-sm font-medium" title="${t.sendNow || 'Send Now'}"><i class="fas fa-paper-plane fa-fw"></i></button>`;
            html += `<button type="button" data-action="edit" data-campaign-id="${data.id}" class="text-gray-600 hover:text-gray-800 text-sm font-medium" title="${t.edit || 'Edit'}"><i class="fas fa-pen fa-fw"></i></button>`;
        }
        if (data.status === 'draft') {
            html += `<button type="button" data-action="delete" data-campaign-id="${data.id}" class="text-red-600 hover:text-red-800 text-sm font-medium" title="${t.delete || 'Delete'}"><i class="fas fa-trash fa-fw"></i></button>`;
        }

        html += '</div>';
        return html;
    }

    /**
     * Enforce column layout (actions column last)
     */
    enforceColumnLayout(apiOrParams) {
        enforceCampaignsColumnLayout(apiOrParams);
    }

    initializeGrid() {
        this._gridInit.initializeGrid();
    }

    checkAndInitialize() {
        this._gridInit.checkAndInitialize();
    }

    /**
     * Initialize tab observers and event listeners
     */
    init() {
        // Wait for DOM to be ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this._setupTabObservers());
        } else {
            this._setupTabObservers();
        }
    }

    /**
     * Set up tab visibility observers
     */
    _setupTabObservers() {
        const campaignsContent = document.getElementById('panel-campaigns');

        // Initialize immediately if tab is already visible
        if (campaignsContent && !campaignsContent.classList.contains('hidden')) {
            this.checkAndInitialize();
        }

        if (campaignsContent) {
            const campaignsObserver = new MutationObserver((mutations) => {
                mutations.forEach((mutation) => {
                    if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
                        // Only initialize if tab is visible and grid not already initialized
                        if (!campaignsContent.classList.contains('hidden') && !this.initialized) {
                            this._gridInit.state.retryCount = 0;
                            this.checkAndInitialize();
                        }
                    }
                });
            });
            campaignsObserver.observe(campaignsContent, { attributes: true, attributeFilter: ['class'] });
        }

        // Set up event delegation for campaign action buttons in AG Grid
        // Use document-level delegation since grid content is dynamic
        document.addEventListener('click', (e) => {
            const button = e.target.closest('button[data-action]');
            if (!button || !button.hasAttribute('data-campaign-id')) return;

            const campaignsGrid = document.getElementById(this.containerId);
            if (!campaignsGrid || !campaignsGrid.contains(button)) return;

            const action = button.getAttribute('data-action');
            const campaignId = parseInt(button.getAttribute('data-campaign-id'));

            if (window.adminNotifications) {
                if (action === 'send') {
                    window.adminNotifications.sendCampaign(campaignId);
                } else if (action === 'edit') {
                    window.adminNotifications.editCampaign(campaignId);
                } else if (action === 'delete') {
                    window.adminNotifications.deleteCampaign(campaignId);
                } else if (action === 'view-recipients') {
                    window.adminNotifications.viewCampaignRecipients(campaignId);
                }
            }
        });
    }
}

// Expose classes to window for backward compatibility
window.NotificationsGridManager = NotificationsGridManager;
window.CampaignsGridManager = CampaignsGridManager;

// Expose utility function
window.enforceCampaignsColumnLayout = enforceCampaignsColumnLayout;
