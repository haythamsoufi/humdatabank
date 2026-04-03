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
        this.containerSelector = options.containerSelector || 'notifications-table-container';

        this.gridHelper = null;
        this.gridApi = null;
        this.initialized = false;
        this.initializing = false;
        this.retryCount = 0;
        this.MAX_RETRIES = 10;

        // Expose to window for backward compatibility
        window.notificationsGridManager = this;
    }

    /**
     * Build column definitions for notifications grid
     */
    buildColumnDefs() {
        const t = this.translations;
        return [
            {
                field: 'user_name',
                headerName: t.user || 'User',
                width: 200,
                minWidth: 150,
                maxWidth: 300,
                filter: 'agTextColumnFilter',
                sortable: true,
                cellRenderer: function(params) {
                    return AgGridRenderers.userHoverCell(params, {
                        idField: 'user_id',
                        nameField: 'user_name',
                        emailField: 'user_email',
                        titleField: 'user_title',
                        activeField: 'user_active',
                        profileColorField: 'user_profile_color',
                        fallbackLabel: 'Unknown User',
                        showEmail: true
                    });
                },
                cellStyle: { 'white-space': 'normal', 'line-height': '1.4' }
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

    /**
     * Initialize the grid
     */
    initializeGrid() {
        console.log('Initializing notifications grid...');
        console.log('Notifications data:', this.data);
        console.log('Data length:', this.data ? this.data.length : 0);

        // Always hide loading and show container, even if no data
        const loadingEl = document.getElementById(this.loadingId);
        const containerEl = document.getElementById(this.containerSelector);

        if (!this.data || this.data.length === 0) {
            console.log('No notifications data, hiding loading...');
            if (loadingEl) loadingEl.style.display = 'none';
            if (containerEl) containerEl.style.display = 'block';
            return;
        }

        try {
            this.gridHelper = new AgGridHelper({
                containerId: this.containerId,
                templateId: this.templateId,
                columnDefs: this.columnDefs,
                rowData: this.data,
                options: {
                    getRowHeight: function(params) {
                        return null; // Auto-height
                    }
                },
                columnVisibilityOptions: {
                    enableExport: false,
                    enableReset: true
                }
            });

            // Try synchronous initialization first
            this.gridApi = this.gridHelper.initialize();

            // If that failed, try async initialization
            if (!this.gridApi) {
                console.log('Trying async initialization...');
                this.gridHelper.initializeAsync(3000).then((api) => {
                    console.log('Grid initialized successfully (async)');
                    this.gridApi = api;
                    this._exposeToWindow();
                    this._showGrid(loadingEl, containerEl);
                }).catch((error) => {
                    console.error('AgGridHelper: Failed to initialize notifications grid:', error);
                    this._showGrid(loadingEl, containerEl);
                });
            } else {
                console.log('Grid initialized successfully (sync)');
                this._exposeToWindow();
                this._showGrid(loadingEl, containerEl);
            }
        } catch (error) {
            console.error('Error initializing grid:', error);
            this._showGrid(loadingEl, containerEl);
        }
    }

    /**
     * Show grid and hide loading indicator
     */
    _showGrid(loadingEl, containerEl) {
        if (loadingEl) loadingEl.style.display = 'none';
        if (containerEl) containerEl.style.display = 'block';
    }

    /**
     * Expose grid API to window for backward compatibility
     */
    _exposeToWindow() {
        window.notificationsGridApi = this.gridApi;
        window.notificationsGridHelper = this.gridHelper;
    }

    /**
     * Check and initialize grid if tab is visible
     */
    checkAndInitialize() {
        const viewAllContent = document.getElementById('tab-content-view-all');

        // Prevent multiple simultaneous initializations
        if (this.initialized || this.initializing) {
            return;
        }

        if (viewAllContent && !viewAllContent.classList.contains('hidden')) {
            // Set flag immediately to prevent concurrent calls
            this.initializing = true;

            // Show the container first
            const containerEl = document.getElementById(this.containerSelector);
            const loadingEl = document.getElementById(this.loadingId);

            if (containerEl) {
                containerEl.style.display = 'block';
            }
            if (loadingEl) {
                loadingEl.style.display = 'none';
            }

            // Check if grid container exists
            const gridContainer = document.getElementById(this.containerId);
            if (gridContainer) {
                // Wait a moment for the container to be laid out, then initialize
                setTimeout(() => {
                    const rect = gridContainer.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        console.log('Initializing notifications grid - container ready');
                        this.initializeGrid();
                        this.initialized = true;
                        this.initializing = false;
                        this.retryCount = 0;
                    } else if (this.retryCount < this.MAX_RETRIES) {
                        this.retryCount++;
                        this.initializing = false; // Allow retry
                        console.log(`Notifications grid container not ready (attempt ${this.retryCount}/${this.MAX_RETRIES}), retrying...`);
                        setTimeout(() => this.checkAndInitialize(), 300);
                    } else {
                        console.log('Max retries reached for notifications grid, initializing anyway');
                        this.initializeGrid();
                        this.initialized = true;
                        this.initializing = false;
                    }
                }, 100);
            } else {
                // Container not found, initialize anyway after a short delay
                setTimeout(() => {
                    this.initializeGrid();
                    this.initialized = true;
                    this.initializing = false;
                }, 200);
            }
        } else {
            // Tab not visible, reset flag
            this.initializing = false;
        }
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
        const viewAllTab = document.getElementById('tab-view-all');
        const viewAllContent = document.getElementById('tab-content-view-all');

        // Initialize immediately if tab is already visible
        if (viewAllContent && !viewAllContent.classList.contains('hidden')) {
            this.checkAndInitialize();
        }

        // Listen for tab clicks
        if (viewAllTab) {
            viewAllTab.addEventListener('click', () => {
                // Wait a bit for the tab content to be shown
                setTimeout(() => this.checkAndInitialize(), 300);
            });
        }

        // Observe tab content visibility changes (with debouncing)
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
        this.containerSelector = options.containerSelector || 'campaigns-table-container';

        this.gridHelper = null;
        this.gridApi = null;
        this.initialized = false;
        this.retryCount = 0;
        this.MAX_RETRIES = 10;

        // Expose to window for backward compatibility
        window.campaignsGridManager = this;
    }

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
                }
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
     * Initialize the grid
     */
    initializeGrid() {
        console.log('Initializing campaigns grid...');
        console.log('Campaigns data:', this.data);
        console.log('Data length:', this.data ? this.data.length : 0);

        // Always hide loading and show container, even if no data
        const loadingEl = document.getElementById(this.loadingId);
        const containerEl = document.getElementById(this.containerSelector);
        const gridContainer = document.getElementById(this.containerId);

        // Show container first
        if (loadingEl) loadingEl.style.display = 'none';
        if (containerEl) {
            containerEl.style.display = 'block';
            // Ensure container has explicit dimensions
            if (containerEl.style.height === '' || containerEl.style.height === 'auto') {
                containerEl.style.minHeight = '400px';
            }
        }

        if (!this.data || this.data.length === 0) {
            console.log('No campaigns data');
            return;
        }

        // Ensure grid container has dimensions before initializing
        if (gridContainer) {
            const rect = gridContainer.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) {
                console.log('Grid container has no dimensions, waiting...');
                setTimeout(() => {
                    this.initializeGrid();
                }, 200);
                return;
            }
            // Set explicit height to prevent zero-width issues
            if (!gridContainer.style.height || gridContainer.style.height === 'auto') {
                gridContainer.style.height = '600px';
            }
        }

        try {
            this.gridHelper = new AgGridHelper({
                containerId: this.containerId,
                templateId: this.templateId,
                columnDefs: this.columnDefs,
                rowData: this.data,
                options: {
                    getRowHeight: function(params) {
                        return null; // Auto-height
                    },
                    suppressColumnMoveAnimation: false,
                    suppressMovableColumns: false,
                    // Enforce Actions-last AFTER the grid is rendered and AFTER any persisted state is applied.
                    onFirstDataRendered: (params) => {
                        // Run immediately, then again shortly after to beat any late state restore.
                        setTimeout(() => { this.enforceColumnLayout(params); }, 0);
                        setTimeout(() => { this.enforceColumnLayout(params); }, 250);
                    }
                },
                columnVisibilityOptions: {
                    enableExport: false,
                    enableReset: true
                }
            });

            // Try synchronous initialization first
            this.gridApi = this.gridHelper.initialize();

            // If that failed, try async initialization
            if (!this.gridApi) {
                console.log('Trying async initialization for campaigns grid...');
                this.gridHelper.initializeAsync(3000).then((api) => {
                    console.log('Campaigns grid initialized successfully (async)');
                    this.gridApi = api;
                    this._exposeToWindow();

                    // Force Actions to be last (pinned right) and Recipients to stay unpinned.
                    // Run after helper + ColumnVisibilityManager apply persisted state.
                    setTimeout(() => {
                        this.enforceColumnLayout(this.gridApi);
                    }, 50);
                }).catch((error) => {
                    console.error('AgGridHelper: Failed to initialize campaigns grid:', error);
                });
            } else {
                console.log('Campaigns grid initialized successfully (sync)');
                this._exposeToWindow();

                // Force Actions to be last (pinned right) and Recipients to stay unpinned.
                // Run after helper + ColumnVisibilityManager apply persisted state.
                setTimeout(() => {
                    this.enforceColumnLayout(this.gridApi);
                }, 50);
            }
        } catch (error) {
            console.error('Error initializing campaigns grid:', error);
        }
    }

    /**
     * Enforce column layout (actions column last)
     */
    enforceColumnLayout(apiOrParams) {
        enforceCampaignsColumnLayout(apiOrParams);
    }

    /**
     * Expose grid API to window for backward compatibility
     */
    _exposeToWindow() {
        window.campaignsGridApi = this.gridApi;
        window.campaignsGridHelper = this.gridHelper;
    }

    /**
     * Check and initialize grid if tab is visible
     */
    checkAndInitialize() {
        const campaignsContent = document.getElementById('tab-content-campaigns');

        // Prevent multiple initializations
        if (this.initialized) {
            return;
        }

        if (campaignsContent && !campaignsContent.classList.contains('hidden')) {
            // Mark as initializing to prevent concurrent calls
            this.initialized = true;

            // Show the container first
            const containerEl = document.getElementById(this.containerSelector);
            const loadingEl = document.getElementById(this.loadingId);

            if (containerEl) {
                containerEl.style.display = 'block';
            }
            if (loadingEl) {
                loadingEl.style.display = 'none';
            }

            // Check if grid container exists
            const gridContainer = document.getElementById(this.containerId);
            if (gridContainer) {
                // Wait longer for the container to be fully laid out, then initialize
                setTimeout(() => {
                    const rect = gridContainer.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        console.log('Initializing campaigns grid - container ready');
                        // Additional small delay to ensure layout is stable
                        setTimeout(() => {
                            this.initializeGrid();
                            this.retryCount = 0;
                        }, 100);
                    } else if (this.retryCount < this.MAX_RETRIES) {
                        this.retryCount++;
                        this.initialized = false; // Allow retry
                        console.log(`Campaigns grid container not ready (attempt ${this.retryCount}/${this.MAX_RETRIES}), retrying...`);
                        setTimeout(() => this.checkAndInitialize(), 300);
                    } else {
                        console.log('Max retries reached for campaigns grid, initializing anyway');
                        setTimeout(() => {
                            this.initializeGrid();
                        }, 200);
                    }
                }, 200);
            } else {
                // Container not found, initialize anyway after a short delay
                setTimeout(() => {
                    this.initializeGrid();
                }, 300);
            }
        } else {
            // Tab not visible, reset initialization flag
            this.initialized = false;
        }
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
        const campaignsTab = document.getElementById('tab-campaigns');
        const campaignsContent = document.getElementById('tab-content-campaigns');

        // Initialize immediately if tab is already visible
        if (campaignsContent && !campaignsContent.classList.contains('hidden')) {
            this.checkAndInitialize();
        }

        // Listen for campaigns tab clicks
        if (campaignsTab) {
            campaignsTab.addEventListener('click', () => {
                // Only initialize if not already initialized
                if (!this.initialized) {
                    this.retryCount = 0;
                    setTimeout(() => this.checkAndInitialize(), 300);
                }
            });
        }

        // Observe campaigns tab content visibility changes
        if (campaignsContent) {
            const campaignsObserver = new MutationObserver((mutations) => {
                mutations.forEach((mutation) => {
                    if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
                        // Only initialize if tab is visible and grid not already initialized
                        if (!campaignsContent.classList.contains('hidden') && !this.initialized) {
                            this.retryCount = 0;
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
