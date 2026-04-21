// Backoffice/plugins/interactive_map/static/js/map_field.js
import { debugPluginLog, debugPluginError, debugPluginWarn } from '/static/js/forms/modules/debug.js';

// --- Optional generic host integration hook ---------------------------------
// The host app's generic plugin loader will call `registerActions(ActionRouter)`
// if this function is exported. This lets the plugin register its own
// `data-action="..."` handlers without any plugin-specific host code.
export function registerActions(ActionRouter) {
    if (!ActionRouter) return;
    if (window.__InteractiveMapActionsRegistered === true) return;
    window.__InteractiveMapActionsRegistered = true;

    const getFieldId = (el) => el?.getAttribute?.('data-field-id') || '';

    ActionRouter.register('map:search-location', (el, e) => {
        e?.preventDefault?.();
        const fieldId = getFieldId(el);
        const inputId = el.getAttribute('data-input-id') || '';
        const input = inputId ? document.getElementById(inputId) : null;
        const query = input && 'value' in input ? input.value : '';
        if (window.searchLocation && fieldId) window.searchLocation(fieldId, query);
    });

    ActionRouter.register('map:toggle-marker-mode', (el, e) => {
        e?.preventDefault?.();
        const fieldId = getFieldId(el);
        if (window.toggleMarkerMode && fieldId) window.toggleMarkerMode(fieldId);
    });

    ActionRouter.register('map:clear-markers', (el, e) => {
        e?.preventDefault?.();
        const fieldId = getFieldId(el);
        if (window.clearMarkers && fieldId) window.clearMarkers(fieldId);
    });

    ActionRouter.register('map:center-map', (el, e) => {
        e?.preventDefault?.();
        const fieldId = getFieldId(el);
        if (window.centerMap && fieldId) window.centerMap(fieldId);
    });

    ActionRouter.register('map:go-to-current-location', (el, e) => {
        e?.preventDefault?.();
        const fieldId = getFieldId(el);
        if (window.goToCurrentLocation && fieldId) window.goToCurrentLocation(fieldId);
    });

    ActionRouter.register('map:add-manual-marker', (el, e) => {
        e?.preventDefault?.();
        const fieldId = getFieldId(el);
        if (window.addManualMarker && fieldId) window.addManualMarker(fieldId);
    });

    ActionRouter.register('map:edit-marker', (el, e) => {
        e?.preventDefault?.();
        const fieldId = getFieldId(el);
        const markerId = el.getAttribute('data-marker-id') || '';
        if (window.editMarker && fieldId && markerId) window.editMarker(fieldId, markerId);
    });

    ActionRouter.register('map:remove-marker', (el, e) => {
        e?.preventDefault?.();
        const fieldId = getFieldId(el);
        const markerId = el.getAttribute('data-marker-id') || '';
        if (window.removeMarker && fieldId && markerId) window.removeMarker(fieldId, markerId);
    });

    ActionRouter.register('map:hide-modal', (el, e) => {
        e?.preventDefault?.();
        const fieldId = getFieldId(el);
        if (window.hideModal && fieldId) window.hideModal(fieldId);
    });

    ActionRouter.register('map:save-marker-edit', (el, e) => {
        e?.preventDefault?.();
        const fieldId = getFieldId(el);
        if (window.saveMarkerEdit && fieldId) window.saveMarkerEdit(fieldId);
    });
}

export class InteractiveMapField {
    constructor(fieldId) {
        this.fieldId = fieldId;
        this.pluginName = 'InteractiveMap'; // Set plugin name for debugging
        this.map = null;
        this.markers = [];
        this.shapes = [];
        this.config = {};
        this.existingData = {};
        this.canEdit = false;
        this.markerMode = false;
        this.drawingMode = false;
        this.currentDrawing = null;
        this.drawingLayer = null;
        this._clickListenerAttached = false;
        this._userLocationMarker = null;
        this._userAccuracyCircle = null;
        this._defaultMarkerIcon = null;
        this._userLocationIcon = null;
        this.pendingAutocompleteSelection = null;

        // DOM elements
        this.mapContainer = null;
        this.loadingOverlay = null;
        this.errorOverlay = null;
        this.coordinateDisplay = null;
        this.manualCoordinatesContainer = null;
        this.markersContainer = null;
        this.markerCount = null;
        this.hiddenInput = null;

        // Bind methods
        this.onMapClick = this.onMapClick.bind(this);
        this.onMarkerClick = this.onMarkerClick.bind(this);
        this.onShapeClick = this.onShapeClick.bind(this);
        this.onMapMove = this.onMapMove.bind(this);
    }

    /**
     * Host-owned lifecycle (preferred).
     * The host calls mount(container, context) when DOM is ready.
     */
    async mount(container, context = {}) {
        try {
            this._hostContainer = container || null;
            this._hostContext = context || {};
            if (context && typeof context.fieldId !== 'undefined' && context.fieldId !== null) {
                this.fieldId = String(context.fieldId);
            }
            if (context && typeof context.canEdit === 'boolean') {
                this.canEdit = context.canEdit;
            }
        } catch (e) {
            // ignore
        }
        return await this.initialize();
    }

    unmount() {
        try {
            // Clean up modal event listeners
            if (this._modalEscapeHandler) {
                document.removeEventListener('keydown', this._modalEscapeHandler);
                this._modalEscapeHandler = null;
            }
            const modal = document.getElementById(`marker-edit-modal-${this.fieldId}`);
            if (modal && this._modalBackdropHandler) {
                modal.removeEventListener('click', this._modalBackdropHandler);
                this._modalBackdropHandler = null;
            }

            // Clean up map
            if (this.map) {
                try {
                    this.map.off();
                } catch (e) { /* ignore */ }
                try {
                    this.map.remove();
                } catch (e) { /* ignore */ }
            }
        } finally {
            this.map = null;
        }
    }

    serialize() {
        // Ensure hidden input is up-to-date before submit
        try {
            this.updateHiddenInput();
        } catch (e) {
            // ignore
        }
        return this.hiddenInput?.value || null;
    }

    async initialize() {
        debugPluginLog(this.pluginName, `Initializing field ${this.fieldId}`);
        try {
            debugPluginLog(this.pluginName, 'Loading configuration...');
            this.loadConfiguration();
            debugPluginLog(this.pluginName, 'Loading plugin settings...');
            await this.loadPluginSettings();
            debugPluginLog(this.pluginName, 'Setting up DOM elements...');
            await this.setupDOMElements();
            debugPluginLog(this.pluginName, 'Loading existing data...');
            this.loadExistingData();
            debugPluginLog(this.pluginName, 'Initializing map...');
            this.showLoading();
            await this.initializeMap();
            debugPluginLog(this.pluginName, 'Setting up event listeners...');
            this.setupEventListeners();
            if (this.config.allow_markers) {
                debugPluginLog(this.pluginName, 'Rendering markers list...');
                this.renderMarkersList();
            }
            debugPluginLog(this.pluginName, 'Hiding loading state...');
            this.hideLoading();
            debugPluginLog(this.pluginName, 'Initialization complete!');
            // Ensure UI reflects initial marker mode state
            this.updateMarkerModeUI();
        } catch (error) {
            debugPluginError(this.pluginName, 'Failed to initialize interactive map field:', error);
            debugPluginError(this.pluginName, 'Error details:', error.stack);
            this.showError();
        }
    }

    async setupDOMElements() {
        debugPluginLog(this.pluginName, `Setting up DOM elements for field ${this.fieldId}`);

        const ensureClientRenderedTemplate = async () => {
            try {
                const host = document.querySelector(`.plugin-field-container[data-field-id="${this.fieldId}"]`);
                if (!host) return false;

                // If already rendered, nothing to do
                if (host.querySelector(`#map-${this.fieldId}`) || host.querySelector(`.interactive-map-field[data-field-id="${this.fieldId}"]`)) {
                    return true;
                }

                debugPluginWarn(this.pluginName, `Host template missing for field ${this.fieldId}; attempting client-side render into plugin-field-container`);

                const mod = await import('/plugins/static/interactive_map/js/map_field_renderer.js');
                const render = mod?.renderInteractiveMapFieldHTML;
                if (typeof render !== 'function') return false;

                let pluginConfig = {};
                let existingData = {};
                try { pluginConfig = JSON.parse(host.dataset.pluginConfig || '{}'); } catch (e) { pluginConfig = {}; }
                try { existingData = JSON.parse(host.dataset.existingData || '{}'); } catch (e) { existingData = {}; }
                const canEdit = host.dataset.canEdit === 'true';

                const html = render({ fieldId: String(this.fieldId), pluginConfig, existingData, canEdit });
                if (typeof html !== 'string' || !html.trim()) return false;

                // Inject without using innerHTML assignment (CSP/XSS-friendly).
                const doc = new DOMParser().parseFromString(html, 'text/html');
                const root = doc.body;
                const fragment = document.createDocumentFragment();
                while (root.firstChild) fragment.appendChild(root.firstChild);
                host.replaceChildren(fragment);

                return !!host.querySelector(`#map-${this.fieldId}`);
            } catch (e) {
                debugPluginError(this.pluginName, 'Client-side render fallback failed', e);
                return false;
            }
        };

        // Wait for the map container to be available (retry mechanism for timing issues)
        let retries = 0;
        const maxRetries = 10;
        const retryDelay = 50;

        while (retries < maxRetries) {
            this.mapContainer = document.getElementById(`map-${this.fieldId}`);
            if (this.mapContainer) {
                break;
            }
            retries++;
            if (retries < maxRetries) {
                debugPluginLog(this.pluginName, `Map container not found, retrying (${retries}/${maxRetries})...`);
                await new Promise(resolve => setTimeout(resolve, retryDelay));
            }
        }

        if (!this.mapContainer) {
            // Last attempt: try to find it within the wrapper
            const wrapper = document.querySelector(`.interactive-map-field[data-field-id="${this.fieldId}"]`);
            debugPluginLog(this.pluginName, `Wrapper element:`, wrapper);
            if (wrapper) {
                this.mapContainer = wrapper.querySelector(`#map-${this.fieldId}`) || wrapper.querySelector('.map-field');
                debugPluginLog(this.pluginName, `Found map container in wrapper:`, this.mapContainer);
            } else {
                // Debug: check what's actually in the DOM
                const allMapFields = document.querySelectorAll('.interactive-map-field');
                debugPluginWarn(this.pluginName, `Wrapper not found. Found ${allMapFields.length} interactive-map-field elements:`,
                    Array.from(allMapFields).map(el => ({
                        fieldId: el.getAttribute('data-field-id'),
                        hasMapContainer: !!el.querySelector('.map-field'),
                        innerHTML: el.innerHTML.substring(0, 200)
                    }))
                );
            }
        }

        if (!this.mapContainer) {
            // If the host did not inject the plugin template, render the plugin HTML client-side.
            const injected = await ensureClientRenderedTemplate();
            if (injected) {
                this.mapContainer = document.getElementById(`map-${this.fieldId}`);
                if (!this.mapContainer) {
                    const wrapper2 = document.querySelector(`.interactive-map-field[data-field-id="${this.fieldId}"]`);
                    if (wrapper2) {
                        this.mapContainer = wrapper2.querySelector(`#map-${this.fieldId}`) || wrapper2.querySelector('.map-field');
                    }
                }
            }
        }

        if (!this.mapContainer) {
            // Final debug: check the container that should hold the template
            const container = document.querySelector(`.plugin-field-container[data-field-id="${this.fieldId}"]`);
            debugPluginError(this.pluginName, `Map container not found for field ${this.fieldId}. Container:`, container);
            debugPluginError(this.pluginName, `Container HTML (first 500 chars):`, container?.innerHTML?.substring(0, 500));
            throw new Error(`Map container not found for field ${this.fieldId} after ${maxRetries} retries. Please ensure the template HTML is properly rendered. Expected element: #map-${this.fieldId}`);
        }

        debugPluginLog(this.pluginName, `Map container found after ${retries} retries:`, this.mapContainer);

        // Debug: Check for search input and buttons
        const searchInput = document.getElementById(`address-search-${this.fieldId}`);
        const searchWrapper = document.querySelector(`.interactive-map-field[data-field-id="${this.fieldId}"] .search-input-wrapper`);
        const searchIconBtn = document.querySelector(`.interactive-map-field[data-field-id="${this.fieldId}"] .search-icon-btn`);
        const locateIconBtn = document.querySelector(`.interactive-map-field[data-field-id="${this.fieldId}"] .locate-icon-btn`);

        debugPluginLog(this.pluginName, '=== SEARCH INPUT DEBUG ===');
        debugPluginLog(this.pluginName, `Search input element:`, searchInput);
        debugPluginLog(this.pluginName, `Search wrapper element:`, searchWrapper);
        debugPluginLog(this.pluginName, `Search icon button:`, searchIconBtn);
        debugPluginLog(this.pluginName, `Locate icon button:`, locateIconBtn);

        if (searchWrapper) {
            debugPluginLog(this.pluginName, `Search wrapper classes:`, searchWrapper.className);
            debugPluginLog(this.pluginName, `Search wrapper children:`, Array.from(searchWrapper.children).map(el => ({
                tag: el.tagName,
                classes: el.className,
                id: el.id
            })));
        }

        if (!locateIconBtn) {
            debugPluginWarn(this.pluginName, '⚠️ LOCATE ICON BUTTON NOT FOUND IN DOM!');
            debugPluginWarn(this.pluginName, 'Checking for alternative structure...');
            const allButtons = document.querySelectorAll(`.interactive-map-field[data-field-id="${this.fieldId}"] button`);
            debugPluginLog(this.pluginName, `All buttons found:`, Array.from(allButtons).map(btn => ({
                classes: btn.className,
                dataAction: btn.getAttribute('data-action'),
                innerHTML: btn.innerHTML.trim()
            })));
        } else {
            debugPluginLog(this.pluginName, `✅ Locate icon button found!`);
            debugPluginLog(this.pluginName, `Locate button computed styles:`, {
                display: window.getComputedStyle(locateIconBtn).display,
                visibility: window.getComputedStyle(locateIconBtn).visibility,
                opacity: window.getComputedStyle(locateIconBtn).opacity,
                position: window.getComputedStyle(locateIconBtn).position,
                zIndex: window.getComputedStyle(locateIconBtn).zIndex
            });
        }

        this.loadingOverlay = document.getElementById(`map-loading-${this.fieldId}`);
        this.errorOverlay = document.getElementById(`map-error-${this.fieldId}`);
        this.coordinateDisplay = document.getElementById(`coordinate-display-${this.fieldId}`);

        // Locate the manual coordinates container within the field wrapper
        try {
            const wrapper = document.querySelector(`.interactive-map-field[data-field-id="${this.fieldId}"]`);
            if (wrapper) {
                this.manualCoordinatesContainer = wrapper.querySelector('.manual-coordinates');
            }
        } catch (e) { /* no-op */ }

        // Only look for marker-related elements if markers are allowed
        if (this.config.allow_markers) {
            this.markersContainer = document.getElementById(`marker-list-${this.fieldId}`);
            this.markerCount = document.getElementById(`marker-count-${this.fieldId}`);
        } else {
            this.markersContainer = null;
            this.markerCount = null;
        }

        this.hiddenInput = document.getElementById(`map-data-${this.fieldId}`);

        debugPluginLog(this.pluginName, `All DOM elements:`, {
            mapContainer: this.mapContainer,
            loadingOverlay: this.loadingOverlay,
            errorOverlay: this.errorOverlay,
            coordinateDisplay: this.coordinateDisplay,
            manualCoordinatesContainer: this.manualCoordinatesContainer,
            markersContainer: this.markersContainer,
            markerCount: this.markerCount,
            hiddenInput: this.hiddenInput
        });

        // Log warning if hidden input is missing
        if (!this.hiddenInput) {
            debugPluginWarn(this.pluginName, `Hidden input not found for field ${this.fieldId} - form submission may not work properly`);
        }

        // Hide manual coordinate inputs until Add Marker mode is activated
        if (this.manualCoordinatesContainer) {
            this.manualCoordinatesContainer.style.display = 'none';
        }
    }

    loadConfiguration() {
        let parsedOk = false;
        const configElement = document.getElementById(`map-config-${this.fieldId}`);
        if (configElement) {
            try {
                const raw = (configElement.textContent || '').trim();
                if (raw) {
                    this.config = JSON.parse(raw);
                    parsedOk = true;
                    debugPluginLog(this.pluginName, `Raw config from HTML:`, this.config);
                }
            } catch (error) {
                debugPluginWarn(this.pluginName, 'Failed to parse map config from HTML, will try container dataset', error);
            }
        }

        // Fallback for entry-form rendering:
        // The host container carries plugin config in data-plugin-config.
        if (!parsedOk) {
            try {
                const host = document.querySelector(`.plugin-field-container[data-field-id="${this.fieldId}"]`);
                const rawCfg = host?.dataset?.pluginConfig;
                if (rawCfg) {
                    this.config = JSON.parse(rawCfg);
                    parsedOk = true;
                    debugPluginLog(this.pluginName, `Raw config from container dataset:`, this.config);
                }
            } catch (e) {
                debugPluginWarn(this.pluginName, 'Failed to parse map config from container dataset, using defaults', e);
            }
        }

        if (!parsedOk) {
            this.config = {};
        }

        // Track which values were explicitly configured per-field (from the builder)
        // so plugin-level defaults don't overwrite them.
        // NOTE: This flag is evaluated before we merge in defaults below.
        this._hasExplicitDefaultZoom = Object.prototype.hasOwnProperty.call(this.config || {}, 'default_zoom');

        // Merge with defaults, but respect saved config values
        this.config = {
            // Default values
            map_type: 'mapbox',
            default_zoom: 10,
            // Auto-center map on the user's current location on first load.
            // If the field already has saved data (markers/map_center), we will NOT override.
            // IMPORTANT: keep this default OFF to avoid triggering browser permission prompts
            // just by opening the form. Enable explicitly per-field if needed.
            auto_center_on_load: false,
            allow_markers: true,
            max_markers: 10,
            map_center_lat: 0,
            map_center_lng: 0,
            allow_drawing: false,
            allowed_geometry_types: ['Point'],
            coordinate_precision: 6,
            map_height: 400,
            allow_multiple_markers: true,
            show_search_box: true,
            show_coordinates: true,
            show_locate_control: false, // Disabled - locate button is now in search input
            show_user_location_marker: true,
            min_markers: 0,
            field_type: 'interactive_map',
            plugin_name: 'interactive_map',

            // Override with saved config (this ensures saved values take precedence)
            ...this.config
        };

        debugPluginLog(this.pluginName, `Final merged config:`, this.config);
        debugPluginLog(this.pluginName, `allow_markers = ${this.config.allow_markers} (type: ${typeof this.config.allow_markers})`);
        debugPluginLog(this.pluginName, `show_search_box = ${this.config.show_search_box} (type: ${typeof this.config.show_search_box})`);
        debugPluginLog(this.pluginName, `show_coordinates = ${this.config.show_coordinates} (type: ${typeof this.config.show_coordinates})`);

        // Convert string values to appropriate types
        this.config.default_zoom = parseInt(this.config.default_zoom) || 10;
        this.config.map_center_lat = parseFloat(this.config.map_center_lat) || 0;
        this.config.map_center_lng = parseFloat(this.config.map_center_lng) || 0;
        this.config.max_markers = parseInt(this.config.max_markers) || 10;
        this.config.min_markers = parseInt(this.config.min_markers) || 0;
        this.config.coordinate_precision = parseInt(this.config.coordinate_precision) || 6;
        this.config.map_height = parseInt(this.config.map_height) || 400;
        this.config.allow_markers = this.config.allow_markers === 'true' || this.config.allow_markers === true;
        this.config.allow_drawing = this.config.allow_drawing === 'true' || this.config.allow_drawing === true;
        this.config.allow_multiple_markers = this.config.allow_multiple_markers === 'true' || this.config.allow_multiple_markers === true;
        this.config.show_search_box = this.config.show_search_box === 'true' || this.config.show_search_box === true;
        this.config.show_coordinates = this.config.show_coordinates === 'true' || this.config.show_coordinates === true;
        this.config.show_locate_control = this.config.show_locate_control === 'true' || this.config.show_locate_control === true;
        this.config.show_user_location_marker = this.config.show_user_location_marker === 'true' || this.config.show_user_location_marker === true;
        this.config.auto_center_on_load = this.config.auto_center_on_load === 'true' || this.config.auto_center_on_load === true;
    }

    async loadPluginSettings() {
        try {
            const response = await fetch('/admin/plugins/interactive_map/api/config/field');
            if (response.ok) {
                const data = await response.json();
                if (data.success && data.config) {
                    // Override field config with plugin settings where appropriate
                    const pluginSettings = data.config;

                    // Use plugin settings as defaults if not explicitly set in field config
                    if (pluginSettings.default_map_provider && !this.config.map_type_override) {
                        this.config.map_type = pluginSettings.default_map_provider;
                    }
                    // IMPORTANT: do not overwrite per-field builder zoom if it was explicitly configured
                    if (pluginSettings.default_zoom_level && !this.config.zoom_override && !this._hasExplicitDefaultZoom) {
                        this.config.default_zoom = pluginSettings.default_zoom_level;
                    }
                    if (pluginSettings.max_markers_per_field && !this.config.max_markers_override) {
                        this.config.max_markers = pluginSettings.max_markers_per_field;
                    }
                    if (pluginSettings.allow_marker_editing !== undefined && !this.config.marker_editing_override) {
                        this.config.allow_marker_editing = pluginSettings.allow_marker_editing;
                    }

                    // Store Mapbox token if available
                    if (pluginSettings.mapbox_token || pluginSettings.api_keys?.mapbox) {
                        this.config.mapbox_token = pluginSettings.mapbox_token || pluginSettings.api_keys?.mapbox;
                    }

                    debugPluginLog(this.pluginName, 'Plugin settings applied:', pluginSettings);
                }
            } else {
                debugPluginWarn(this.pluginName, 'Failed to load plugin settings, using defaults');
            }
        } catch (error) {
            debugPluginWarn(this.pluginName, 'Error loading plugin settings:', error);
        }
    }

    loadExistingData() {
        const fieldElement = document.querySelector(`[data-field-id="${this.fieldId}"]`);
        if (fieldElement) {
            try {
                const existingDataStr = fieldElement.dataset.existingData;
                this.existingData = existingDataStr ? JSON.parse(existingDataStr) : {};
                this.canEdit = fieldElement.dataset.canEdit === 'true';
            } catch (error) {
                debugPluginWarn(this.pluginName, 'Failed to parse existing data');
                this.existingData = {};
                this.canEdit = false;
            }
        }

        // Load markers and shapes from existing data
        if (this.existingData.markers) {
            // Clean up existing markers by removing priority field
            this.markers = this.existingData.markers.map(marker => {
                const { priority, ...cleanMarker } = marker;
                return cleanMarker;
            });
        }
        if (this.existingData.shapes) {
            this.shapes = [...this.existingData.shapes];
        }

        // Restore data availability options
        if (this.existingData.data_not_available !== undefined) {
            const dataNotAvailableCheckbox = document.querySelector(`input[name="field_${this.fieldId}_data_not_available"]`);
            if (dataNotAvailableCheckbox) {
                dataNotAvailableCheckbox.checked = this.existingData.data_not_available;
            }
        }

        if (this.existingData.not_applicable !== undefined) {
            const notApplicableCheckbox = document.querySelector(`input[name="field_${this.fieldId}_not_applicable"]`);
            if (notApplicableCheckbox) {
                notApplicableCheckbox.checked = this.existingData.not_applicable;
            }
        }
    }

    async initializeMap() {
        // Check if Leaflet is available
        if (typeof L === 'undefined') {
            await this.loadLeaflet();
        }

        // Initialize map
        const center = this.existingData.map_center || {
            lat: this.config.map_center_lat,
            lng: this.config.map_center_lng
        };

        this.map = L.map(`map-${this.fieldId}`, {
            center: [center.lat, center.lng],
            zoom: center.zoom || this.config.default_zoom,
            zoomControl: true,
            attributionControl: false
        });

        if (this.pendingAutocompleteSelection) {
            const pendingSelection = this.pendingAutocompleteSelection;
            this.pendingAutocompleteSelection = null;
            this.applyAutocompleteSelection(
                pendingSelection.lat,
                pendingSelection.lng,
                pendingSelection.displayName
            );
        }

        // Add tile layer based on map type
        this.addTileLayer();

        // Add locate control if configured
        if (this.config.show_locate_control) {
            this.addLocateControl();
        }

        // Add drawing layer if drawing is enabled
        if (this.config.allow_drawing) {
            this.setupDrawingTools();
        }

        // Add existing markers and shapes
        if (this.config.allow_markers) {
            this.addExistingMarkers();
        }
        if (this.config.allow_drawing) {
            this.addExistingShapes();
        }

        // Auto-center on the current user's location on first load.
        // This is intended for assignment-filling UX: open directly where the user is.
        // Do not override previously-entered field data.
        try {
            const hasSavedCenter = !!(this.existingData && this.existingData.map_center);
            const hasSavedMarkers = !!(this.existingData && Array.isArray(this.existingData.markers) && this.existingData.markers.length > 0);
            const shouldAutoCenter =
                this.config.auto_center_on_load === true &&
                !hasSavedCenter &&
                !hasSavedMarkers &&
                typeof navigator !== 'undefined' &&
                !!navigator.geolocation;

            if (shouldAutoCenter) {
                debugPluginLog(this.pluginName, 'Auto-centering map on user location (first load)');
                // Don't block initialization; if user denies permission, map stays at configured center.
                setTimeout(() => {
                    try {
                        // Keep the configured zoom when auto-centering on load
                        this.goToCurrentLocation({ zoom: this.config.default_zoom });
                    } catch (e) {
                        // ignore
                    }
                }, 150);
            } else {
                debugPluginLog(this.pluginName, 'Auto-center skipped', { hasSavedCenter, hasSavedMarkers, auto_center_on_load: this.config.auto_center_on_load });
            }
        } catch (e) {
            // ignore
        }

        // Update coordinate display on map move
        this.map.on('mousemove', this.onMapMove.bind(this));

        // Update coordinate display when map view changes
        this.map.on('moveend', () => {
            this.updateCoordinateDisplay();
        });

        this.map.on('zoomend', () => {
            this.updateCoordinateDisplay();
        });

        // Update the coordinate display with current center and marker count after a short delay
        setTimeout(() => {
            this.updateCoordinateDisplay();
            if (this.config.allow_markers) {
                this.updateMarkerCount();
            }
        }, 100);
    }

    async loadLeaflet() {
        debugPluginLog(this.pluginName, 'Loading Leaflet...');
        return new Promise((resolve, reject) => {
            // Load Leaflet CSS
            if (!document.querySelector('link[href*="leaflet.css"]')) {
                debugPluginLog(this.pluginName, 'Loading Leaflet CSS...');
                const cssLink = document.createElement('link');
                cssLink.rel = 'stylesheet';
                cssLink.href = '/static/vendor/leaflet/leaflet.css';
                document.head.appendChild(cssLink);
            }

            // Load Leaflet JS
            if (typeof L === 'undefined') {
                debugPluginLog(this.pluginName, 'Loading Leaflet JS...');
                const script = document.createElement('script');
                script.src = '/static/vendor/leaflet/leaflet.js';
                script.onload = () => {
                    debugPluginLog(this.pluginName, 'Leaflet JS loaded successfully');
                    resolve();
                };
                script.onerror = (error) => {
                    debugPluginError(this.pluginName, 'Failed to load Leaflet JS', error);
                    reject(error);
                };
                document.head.appendChild(script);
            } else {
                resolve();
            }
        });
    }

    /**
     * Return a self-contained marker icon that doesn't fetch external PNG assets.
     * This avoids browser tracking-prevention noise for Leaflet's default marker images.
     */
    getDefaultMarkerIcon() {
        if (this._defaultMarkerIcon) return this._defaultMarkerIcon;
        if (typeof L === 'undefined') return null;

        this._defaultMarkerIcon = L.divIcon({
            className: 'ifrc-leaflet-marker-icon',
            html: '<div class="ifrc-leaflet-marker-dot" aria-hidden="true"></div>',
            iconSize: [16, 16],
            iconAnchor: [8, 8],
            popupAnchor: [0, -8]
        });
        return this._defaultMarkerIcon;
    }

    getUserLocationIcon() {
        if (this._userLocationIcon) return this._userLocationIcon;
        if (typeof L === 'undefined') return null;

        this._userLocationIcon = L.divIcon({
            className: 'ifrc-leaflet-user-location-icon',
            html: '<div class="ifrc-leaflet-user-location-dot" aria-hidden="true"></div>',
            iconSize: [14, 14],
            iconAnchor: [7, 7],
            popupAnchor: [0, -7]
        });
        return this._userLocationIcon;
    }

    addTileLayer() {
        switch (this.config.map_type) {
            case 'mapbox':
                this.addMapboxTiles();
                break;
            case 'google_maps':
                // Note: Google Maps requires API key and different implementation
                this.addOpenStreetMapTiles();
                break;
            case 'custom_tiles':
                // Custom tile implementation would go here
                this.addOpenStreetMapTiles();
                break;
            default:
                this.addMapboxTiles();
                break;
        }
    }

    addMapboxTiles() {
        // Use the same Mapbox style as CountryMapboxMap.js
        // Style URL: mapbox://styles/go-ifrc/ckrfe16ru4c8718phmckdfjh0
        // Convert to Leaflet tile URL format
        const mapboxToken = this.config.mapbox_token || window.MAPBOX_TOKEN;
        const styleId = 'go-ifrc/ckrfe16ru4c8718phmckdfjh0';

        if (!mapboxToken) {
            debugPluginWarn(this.pluginName, 'Mapbox token not found, falling back to OpenStreetMap');
            this.addOpenStreetMapTiles();
            return;
        }

        // Mapbox tile URL format for Leaflet
        const tileUrl = `https://api.mapbox.com/styles/v1/${styleId}/tiles/{z}/{x}/{y}?access_token=${mapboxToken}`;

        L.tileLayer(tileUrl, {
            attribution: '© Mapbox © OpenStreetMap',
            maxZoom: 22,
            tileSize: 512,
            zoomOffset: -1
        }).addTo(this.map);
    }

    addOpenStreetMapTiles() {
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '',
            maxZoom: 19
        }).addTo(this.map);
    }

    addLocateControl() {
        const self = this;
        const LocateControl = L.Control.extend({
            options: { position: 'topleft' },
            onAdd() {
                const container = L.DomUtil.create('div', 'leaflet-bar leaflet-control');
                const link = L.DomUtil.create('a', 'leaflet-control-locate', container);
                link.href = '#';
                link.title = 'Locate me';
                link.setAttribute('aria-label', 'Locate me');
                link.style.textAlign = 'center';
                link.style.width = '28px';
                link.style.height = '28px';
                link.style.lineHeight = '28px';
                link.innerHTML = '📍';
                L.DomEvent.on(link, 'click', L.DomEvent.stopPropagation)
                    .on(link, 'click', L.DomEvent.preventDefault)
                    .on(link, 'click', () => self.goToCurrentLocation());
                return container;
            }
        });
        this.map.addControl(new LocateControl());
    }

    async goToCurrentLocation(options = {}) {
        if (!navigator.geolocation) {
            if (window.showAlert) window.showAlert('Geolocation is not supported by your browser.', 'warning');
            else console.warn('Geolocation not supported');
            return;
        }
        try {
            if (!window.isSecureContext && !(location.hostname === 'localhost' || location.hostname === '127.0.0.1')) {
                debugPluginWarn(this.pluginName, 'Geolocation may be blocked on non-HTTPS origins. Use HTTPS or localhost.');
            }
        } catch (e) { /* no-op */ }

        const applyPosition = (coords) => {
            const latitude = coords.latitude;
            const longitude = coords.longitude;
            const accuracy = coords.accuracy;

            // Respect caller-specified zoom; otherwise preserve current zoom; otherwise fall back to configured default.
            // Do not force a minimum zoom here (previously min 14) because callers may want
            // to keep the template/plugin-configured default zoom.
            const currentZoom = (this.map && typeof this.map.getZoom === 'function') ? (this.map.getZoom() || 0) : 0;
            const configuredZoom = (typeof this.config?.default_zoom === 'number' && !Number.isNaN(this.config.default_zoom))
                ? this.config.default_zoom
                : 10;
            const requestedZoom = (options && options.zoom !== undefined && options.zoom !== null)
                ? parseInt(options.zoom, 10)
                : null;
            const targetZoom = Math.max(1, Math.min(22, requestedZoom || currentZoom || configuredZoom));

            this.map.setView([latitude, longitude], targetZoom, { animate: true });
            this.updateCoordinateDisplay({ lat: latitude, lng: longitude });
            if (this.config.show_user_location_marker) {
                if (this._userLocationMarker) {
                    this.map.removeLayer(this._userLocationMarker);
                    this._userLocationMarker = null;
                }
                if (this._userAccuracyCircle) {
                    this.map.removeLayer(this._userAccuracyCircle);
                    this._userAccuracyCircle = null;
                }
                this._userLocationMarker = L.marker([latitude, longitude], {
                    title: 'Your location',
                    icon: this.getUserLocationIcon()
                }).addTo(this.map);
                if (typeof accuracy === 'number' && accuracy > 0) {
                    this._userAccuracyCircle = L.circle([latitude, longitude], {
                        radius: accuracy,
                        color: '#3b82f6',
                        weight: 1,
                        fillColor: '#3b82f6',
                        fillOpacity: 0.15
                    }).addTo(this.map);
                }
            }
        };

        const attempt = (opts) => new Promise((resolve, reject) => {
            navigator.geolocation.getCurrentPosition(resolve, reject, opts);
        });

        const handleError = (error) => {
            debugPluginError(this.pluginName, 'Geolocation error', error);
            let message = 'Unable to determine your location. Please try again.';
            if (error && typeof error.code === 'number') {
                if (error.code === 1) {
                    message = 'Location permission denied. Please allow access and try again.';
                } else if (error.code === 2) {
                    message = 'Location unavailable. Check your connection/GPS and try again.';
                } else if (error.code === 3) {
                    message = 'Location request timed out. Try again from an open area.';
                }
            }
            if (window.showAlert) window.showAlert(message, 'error');
            else console.warn(message);
        };

        try {
            const pos = await attempt({ enableHighAccuracy: true, timeout: 10000, maximumAge: 0 });
            applyPosition(pos.coords);
            return;
        } catch (e1) {
            // retry with lower accuracy and allow cached value up to 5 minutes
        }
        try {
            const pos2 = await attempt({ enableHighAccuracy: false, timeout: 12000, maximumAge: 300000 });
            applyPosition(pos2.coords);
            return;
        } catch (e2) {
            // Fallback to Leaflet locate
            try {
                const ev = await new Promise((resolve, reject) => {
                    const onFound = (e) => { this.map.off('locationfound', onFound); this.map.off('locationerror', onErr); resolve(e); };
                    const onErr = (e) => { this.map.off('locationfound', onFound); this.map.off('locationerror', onErr); reject(e); };
                    this.map.on('locationfound', onFound);
                    this.map.on('locationerror', onErr);
                    this.map.locate({ setView: false, maxZoom: 14, enableHighAccuracy: false, timeout: 12000, watch: false });
                });
                const latlng = ev.latlng || { lat: ev.latitude, lng: ev.longitude };
                applyPosition({ latitude: latlng.lat, longitude: latlng.lng, accuracy: ev.accuracy });
                return;
            } catch (e3) {
                // Last-resort: approximate IP-based geolocation (may be coarse)
                try {
                    const resp = await fetch('https://ipapi.co/json/');
                    if (resp.ok) {
                        const data = await resp.json();
                        if (data && typeof data.latitude === 'number' && typeof data.longitude === 'number') {
                            applyPosition({ latitude: data.latitude, longitude: data.longitude, accuracy: 50000 });
                            return;
                        }
                    }
                } catch (ipErr) { /* ignore */ }
                handleError(e2);
                return;
            }
        }
    }

    setupDrawingTools() {
        // Initialize drawing layer
        this.drawingLayer = L.featureGroup().addTo(this.map);

        // Add drawing controls
        const drawControl = new L.Control.Draw({
            draw: {
                polygon: this.config.allowed_geometry_types.includes('Polygon'),
                polyline: this.config.allowed_geometry_types.includes('LineString'),
                circle: false,
                rectangle: false,
                circlemarker: false,
                marker: false
            },
            edit: {
                featureGroup: this.drawingLayer,
                remove: true
            }
        });

        this.map.addControl(drawControl);

        // Handle drawing events
        this.map.on(L.Draw.Event.CREATED, (event) => {
            const layer = event.layer;
            this.addShape(layer);
        });

        this.map.on(L.Draw.Event.EDITED, (event) => {
            const layers = event.layers;
            layers.eachLayer((layer) => {
                this.updateShape(layer);
            });
        });

        this.map.on(L.Draw.Event.DELETED, (event) => {
            const layers = event.layers;
            layers.eachLayer((layer) => {
                this.removeShape(layer);
            });
        });
    }

    addExistingMarkers() {
        if (!this.config.allow_markers) return;

        this.markers.forEach(markerData => {
            // Create Leaflet marker directly without calling addMarker to avoid duplication
            // (no title attribute - we use custom popup instead)
            const leafletMarker = L.marker([markerData.lat, markerData.lng], {
                draggable: this.canEdit,
                icon: this.getDefaultMarkerIcon()
                // Note: We don't set 'title' option to avoid native browser tooltip
                // Custom popup shows the marker information instead
            });

            // Store reference to Leaflet marker in our data
            markerData.leafletMarker = leafletMarker;

            // Store reference to marker data in Leaflet marker (for click events)
            leafletMarker.markerData = markerData;

            // Use custom tooltip that renders outside map container
            this.setupCustomTooltip(leafletMarker, markerData);

            // Add to map
            leafletMarker.addTo(this.map);

            // Add event listeners
            leafletMarker.on('click', this.onMarkerClick);
            if (this.canEdit) {
                leafletMarker.on('dragend', (event) => {
                    this.updateMarkerPosition(markerData.id, event.target.getLatLng());
                });
            }
        });
    }

    addExistingShapes() {
        if (!this.config.allow_drawing) return;

        this.shapes.forEach(shapeData => {
            this.addShapeFromData(shapeData, false);
        });
    }

    setupEventListeners() {
        // ------------------------------------------------------------------
        // Resilient click handling:
        // This plugin uses data-action="map:*" buttons. Normally those are routed
        // through the host ActionRouter, but we also attach a local delegated
        // handler so controls keep working even if ActionRouter is unavailable
        // or if actions weren't registered due to timing.
        // ------------------------------------------------------------------
        try {
            const wrapper = document.querySelector(`.interactive-map-field[data-field-id="${this.fieldId}"]`);
            if (wrapper && !wrapper.__ifrcMapDelegatedActionsBound) {
                wrapper.__ifrcMapDelegatedActionsBound = true;
                wrapper.addEventListener('click', (e) => {
                    const target = e.target && typeof e.target.closest === 'function'
                        ? e.target.closest('[data-action^="map:"]')
                        : null;
                    if (!target) return;

                    const action = target.getAttribute('data-action') || '';
                    const fieldId = target.getAttribute('data-field-id') || this.fieldId;
                    if (String(fieldId) !== String(this.fieldId)) return;

                    // Prevent default for buttons/links
                    e.preventDefault();
                    e.stopPropagation();

                    try {
                        if (action === 'map:toggle-marker-mode') return this.toggleMarkerMode();
                        if (action === 'map:clear-markers') return this.clearMarkers();
                        if (action === 'map:center-map') return this.centerMap();
                        if (action === 'map:go-to-current-location') return this.goToCurrentLocation();
                        if (action === 'map:add-manual-marker') return this.addManualMarker();
                        if (action === 'map:save-marker-edit') return this.saveMarkerEdit();
                        if (action === 'map:hide-modal') return this.hideModal();

                        if (action === 'map:search-location') {
                            const inputId = target.getAttribute('data-input-id') || '';
                            const input = inputId ? document.getElementById(inputId) : null;
                            const query = input && 'value' in input ? input.value : '';
                            return this.searchLocation(query);
                        }

                        if (action === 'map:edit-marker') {
                            const markerId = target.getAttribute('data-marker-id') || '';
                            if (markerId) return this.editMarker(markerId);
                        }

                        if (action === 'map:remove-marker') {
                            const markerId = target.getAttribute('data-marker-id') || '';
                            if (markerId) return this.removeMarker(markerId);
                        }
                    } catch (err) {
                        debugPluginWarn(this.pluginName, `Action handler failed: ${action}`, err);
                    }
                }, true);
            }

            // Also add direct listeners to clear button in marker list header as fallback
            const clearBtn = document.querySelector(`.marker-list-container [data-action="map:clear-markers"][data-field-id="${this.fieldId}"]`);
            if (clearBtn && !clearBtn.__clearMarkersBound) {
                clearBtn.__clearMarkersBound = true;
                clearBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    this.clearMarkers();
                });
            }
        } catch (e) {
            // ignore
        }

        // Map click event for adding markers
        if (!this._clickListenerAttached) {
        this.map.on('click', this.onMapClick);
            this._clickListenerAttached = true;
        }

        // Manual coordinate input (only if markers are allowed)
        if (this.config.allow_markers) {
            const manualLatInput = document.getElementById(`manual-lat-${this.fieldId}`);
            const manualLngInput = document.getElementById(`manual-lng-${this.fieldId}`);

            if (manualLatInput && manualLngInput) {
                manualLatInput.addEventListener('change', () => this.updateCoordinateDisplay());
                manualLngInput.addEventListener('change', () => this.updateCoordinateDisplay());
            }
        }

        // Search input autocomplete handler
        const searchInput = document.getElementById(`address-search-${this.fieldId}`);
        if (searchInput && !searchInput.__autocompleteHandlerBound) {
            searchInput.__autocompleteHandlerBound = true;

            // Create autocomplete dropdown container
            this.autocompleteDropdown = document.createElement('div');
            this.autocompleteDropdown.className = 'map-autocomplete-dropdown';
            this.autocompleteDropdown.id = `autocomplete-dropdown-${this.fieldId}`;
            this.autocompleteDropdown.style.display = 'none';
            const searchWrapper = searchInput.closest('.search-input-wrapper');
            if (searchWrapper) {
                searchWrapper.style.position = 'relative';
                searchWrapper.appendChild(this.autocompleteDropdown);
            }

            // Input event for autocomplete suggestions
            searchInput.addEventListener('input', (e) => {
                const query = e.target.value.trim();
                if (query.length >= 2) {
                    this.fetchAutocompleteSuggestions(query);
                } else {
                    this.hideAutocomplete();
                }
            });

            // Keyboard navigation
            searchInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.keyCode === 13) {
                    e.preventDefault();
                    e.stopPropagation();
                    if (this.autocompleteSelectedIndex >= 0 && this.autocompleteSuggestions.length > 0) {
                        // Select highlighted suggestion
                        this.selectAutocompleteSuggestion(this.autocompleteSelectedIndex);
                    } else {
                        // Perform search with current input
                        const query = searchInput.value.trim();
                        if (query) {
                            this.hideAutocomplete();
                            this.searchLocation(query);
                        }
                    }
                } else if (e.key === 'ArrowDown' || e.keyCode === 40) {
                    e.preventDefault();
                    this.navigateAutocomplete(1);
                } else if (e.key === 'ArrowUp' || e.keyCode === 38) {
                    e.preventDefault();
                    this.navigateAutocomplete(-1);
                } else if (e.key === 'Escape' || e.keyCode === 27) {
                    this.hideAutocomplete();
                }
            });

            // Hide autocomplete when clicking outside
            // Use a field-specific handler to avoid conflicts
            const fieldClickHandler = (e) => {
                // Don't hide if clicking on an autocomplete item or dropdown
                if (e.target.closest('.map-autocomplete-item') ||
                    e.target.closest('.map-autocomplete-dropdown') ||
                    e.target === this.autocompleteDropdown) {
                    return;
                }

                // Don't hide if clicking on the search input
                if (searchInput && (searchInput.contains(e.target) || searchInput === e.target)) {
                    return;
                }

                // Hide dropdown for this field
                if (this.autocompleteDropdown && this.autocompleteDropdown.style.display === 'block') {
                    this.hideAutocomplete();
                }
            };

            // Use capture phase and a small delay to ensure autocomplete item clicks fire first
            setTimeout(() => {
                document.addEventListener('click', fieldClickHandler, true);
            }, 0);

            // Focus event to show suggestions if there's a query
            searchInput.addEventListener('focus', () => {
                const query = searchInput.value.trim();
                if (query.length >= 2 && this.autocompleteSuggestions.length > 0) {
                    this.showAutocomplete();
                }
            });
        }
    }

    onMapClick(event) {
        if (!this.canEdit) return;

        if (this.markerMode && this.config.allow_markers) {
            // Check if we can add more markers
            if (this.config.max_markers > 0 && this.markers.length >= this.config.max_markers) {
                if (window.showAlert) window.showAlert(`Maximum number of markers (${this.config.max_markers}) reached.`, 'warning');
                else console.warn('Max markers reached');
                this.toggleMarkerMode(); // Exit marker mode
                return;
            }

            this.addMarker(event.latlng.lat, event.latlng.lng);
            this.toggleMarkerMode(); // Exit marker mode
        }

        // Update coordinate display
        this.updateCoordinateDisplay(event.latlng);
    }

    onMarkerClick(event) {
        const marker = event.target;
        // Custom tooltip handles click via setupCustomTooltip
        // This handler is kept for compatibility but custom tooltip manages its own display
    }

    onShapeClick(event) {
        const shape = event.target;
        const shapeData = shape.shapeData;

        // Show shape info popup
        if (shapeData.properties && (shapeData.properties.title || shapeData.properties.description)) {
            let popupContent = '';
            if (shapeData.properties.title) {
                popupContent += `<h4 class="font-medium">${shapeData.properties.title}</h4>`;
            }
            if (shapeData.properties.description) {
                popupContent += `<p class="text-sm text-gray-600">${shapeData.properties.description}</p>`;
            }

            shape.bindPopup(popupContent).openPopup();
        }
    }



    onMapMove(event) {
        // Update coordinate display with current mouse position
        if (event.latlng) {
            this.updateCoordinateDisplay(event.latlng);
        }
    }

    updateCoordinateDisplay(latlng = null) {
        if (!this.map) return;
        const precision = this.config.coordinate_precision || 6;
        const point = (latlng && typeof latlng.lat === 'number' && typeof latlng.lng === 'number')
            ? latlng
            : this.map.getCenter();

        // Server-rendered: input field for coordinates
        if (this.coordinateDisplay && this.coordinateDisplay.tagName === 'INPUT') {
            this.coordinateDisplay.value = `${point.lat.toFixed(precision)}, ${point.lng.toFixed(precision)}`;
        }

        // Client-rendered: coordinates text inside container and show it
        if (this.coordinateDisplay && typeof this.coordinateDisplay.querySelector === 'function') {
            const coordinatesText = this.coordinateDisplay.querySelector('.coordinates-text');
            if (coordinatesText) {
                coordinatesText.textContent = `${point.lat.toFixed(precision)}, ${point.lng.toFixed(precision)}`;
                this.coordinateDisplay.style.display = 'block';
            }
        }

        // Update manual inputs only when an explicit latlng is provided (e.g., on click)
        if (latlng) {
            const manualLatInput = document.getElementById(`manual-lat-${this.fieldId}`);
            const manualLngInput = document.getElementById(`manual-lng-${this.fieldId}`);
            if (manualLatInput) manualLatInput.value = point.lat.toFixed(precision);
            if (manualLngInput) manualLngInput.value = point.lng.toFixed(precision);
        }

        // Update zoom level display if present
        const zoomLevelEl = document.getElementById(`zoom-level-${this.fieldId}`);
        if (zoomLevelEl) {
            zoomLevelEl.textContent = this.map.getZoom();
        }

        // Optional: update center lat/lng elements if present
        const centerLatEl = document.getElementById(`center-lat-${this.fieldId}`);
        const centerLngEl = document.getElementById(`center-lng-${this.fieldId}`);
        if (centerLatEl) centerLatEl.textContent = this.map.getCenter().lat.toFixed(precision);
        if (centerLngEl) centerLngEl.textContent = this.map.getCenter().lng.toFixed(precision);
    }

    toggleMarkerMode() {
        if (!this.canEdit || !this.config.allow_markers) return;

        // Check if we can add more markers
        if (this.markerMode && this.config.max_markers > 0 && this.markers.length >= this.config.max_markers) {
            if (window.showAlert) window.showAlert(`Maximum number of markers (${this.config.max_markers}) reached.`, 'warning');
            else console.warn('Max markers reached');
            return;
        }

        this.markerMode = !this.markerMode;
        this.updateMarkerModeUI();

        // Update the button text and style
        const button = document.getElementById(`add-marker-btn-${this.fieldId}`);
        if (button) {
            if (this.markerMode) {
                button.classList.remove('btn-outline-primary');
                button.classList.add('btn-primary');
                button.innerHTML = '<i class="fas fa-map-marker-alt"></i> Click Map to Add Marker';
            } else {
                button.classList.remove('btn-primary');
                button.classList.add('btn-outline-primary');
                button.innerHTML = '<i class="fas fa-map-marker-alt"></i> Add Marker';
            }
        }

    }

    toggleDrawingMode() {
        if (!this.canEdit || !this.config.allow_drawing) return;

        this.drawingMode = !this.drawingMode;
        const button = document.getElementById(`draw-shape-btn-${this.fieldId}`);
        const buttonText = button.querySelector('.draw-shape-text');

        if (this.drawingMode) {
            button.classList.add('bg-yellow-600', 'hover:bg-yellow-700');
            button.classList.remove('bg-green-600', 'hover:bg-green-700');
            buttonText.textContent = 'Drawing mode active';
        } else {
            button.classList.remove('bg-yellow-600', 'hover:bg-yellow-700');
            button.classList.add('bg-green-600', 'hover:bg-green-700');
            buttonText.textContent = 'Draw Shape';
        }
    }

    addMarker(lat, lng, markerData = null, updateData = true) {
        if (!this.canEdit && updateData) return;
        if (!this.config.allow_markers) return;

        // Check if multiple markers are allowed
        if (!this.config.allow_multiple_markers && this.markers.length > 0 && !markerData) {
            if (window.showAlert) window.showAlert('Only one marker is allowed. Please remove the existing marker first.', 'warning');
            else console.warn('Only one marker allowed');
            return;
        }

        // Check marker limit
        if (this.markers.length >= this.config.max_markers) {
            if (window.showAlert) window.showAlert(`Maximum number of markers (${this.config.max_markers}) reached.`, 'warning');
            else console.warn('Max markers reached');
            return;
        }

        // Create marker data
        const newMarker = {
            id: markerData?.id || this.generateId(),
            lat: parseFloat(lat),
            lng: parseFloat(lng),
            title: markerData?.title || '',
            description: markerData?.description || ''
        };

        // Create Leaflet marker (no title attribute - we use custom popup instead)
        const leafletMarker = L.marker([lat, lng], {
            draggable: this.canEdit,
            icon: this.getDefaultMarkerIcon()
            // Note: We don't set 'title' option to avoid native browser tooltip
            // Custom popup shows the marker information instead
        });

        // Store reference to Leaflet marker in our data
        newMarker.leafletMarker = leafletMarker;

        // Store reference to marker data in Leaflet marker (for click events)
        leafletMarker.markerData = newMarker;

        // Use custom tooltip that renders outside map container
        this.setupCustomTooltip(leafletMarker, newMarker);

        // Add to map
        leafletMarker.addTo(this.map);

        // Add event listeners
        leafletMarker.on('click', this.onMarkerClick);
        if (this.canEdit) {
            leafletMarker.on('dragend', (event) => {
                this.updateMarkerPosition(newMarker.id, event.target.getLatLng());
            });
        }

        // Add to markers array
        this.markers.push(newMarker);

        // Update hidden input
        if (updateData) {
            this.updateHiddenInput();
            this.renderMarkersList();

            // Automatically open edit modal for new markers so users can add title/description
            // Use a longer delay to ensure DOM is ready
            setTimeout(() => {
                this.editMarker(newMarker.id);
            }, 500);
        }

        return newMarker;
    }

    addManualMarker() {
        if (!this.canEdit || !this.config.allow_markers) return;

        const latInput = document.getElementById(`manual-lat-${this.fieldId}`);
        const lngInput = document.getElementById(`manual-lng-${this.fieldId}`);

        if (!latInput || !lngInput) return;

        const lat = parseFloat(latInput.value);
        const lng = parseFloat(lngInput.value);

        // Validate coordinates
        if (isNaN(lat) || isNaN(lng)) {
            if (window.showAlert) window.showAlert('Please enter valid latitude and longitude values', 'warning');
            else console.warn('Invalid coordinates');
            return;
        }

        if (lat < -90 || lat > 90) {
            if (window.showAlert) window.showAlert('Latitude must be between -90 and 90', 'warning');
            else console.warn('Invalid latitude');
            return;
        }

        if (lng < -180 || lng > 180) {
            if (window.showAlert) window.showAlert('Longitude must be between -180 and 180', 'warning');
            else console.warn('Invalid longitude');
            return;
        }

        // Check if we can add more markers
        if (this.config.max_markers > 0 && this.markers.length >= this.config.max_markers) {
            if (window.showAlert) window.showAlert(`Maximum number of markers (${this.config.max_markers}) reached.`, 'warning');
            else console.warn('Max markers reached');
            return;
        }

        // Add marker at specified coordinates
        const newMarker = this.addMarker(lat, lng);

        // Clear inputs
        latInput.value = '';
        lngInput.value = '';
    }

    addShape(layer, updateData = true) {
        if (!this.canEdit || !this.config.allow_drawing) return;

        // Extract shape data from Leaflet layer
        const shapeData = this.extractShapeData(layer);

        // Store reference to shape data
        layer.shapeData = shapeData;

        // Add to shapes array
        this.shapes.push(shapeData);

        // Update hidden input
        if (updateData) {
            this.updateHiddenInput();
        }
    }

    addShapeFromData(shapeData, updateData = true) {
        if (!this.canEdit || !this.config.allow_drawing) return;

        // Create Leaflet layer from shape data
        const layer = this.createShapeLayer(shapeData);

        // Store reference to shape data
        layer.shapeData = shapeData;

        // Add to map
        layer.addTo(this.map);

        // Add to shapes array
        this.shapes.push(shapeData);

        // Update hidden input
        if (updateData) {
            this.updateHiddenInput();
        }
    }

    extractShapeData(layer) {
        const coords = layer.getLatLngs ? layer.getLatLngs() : [layer.getLatLng()];
        const coordinates = coords.map(coord => [coord.lat, coord.lng]);

        return {
            id: this.generateId(),
            type: this.getShapeType(layer),
            coordinates: coordinates,
            properties: {
                title: '',
                description: '',
                color: '#4444ff',
                opacity: 0.7
            }
        };
    }

    createShapeLayer(shapeData) {
        const coords = shapeData.coordinates.map(coord => [coord[0], coord[1]]);

        switch (shapeData.type) {
            case 'Point':
                return L.marker(coords[0], { icon: this.getDefaultMarkerIcon() });
            case 'LineString':
                return L.polyline(coords, {
                    color: shapeData.properties.color || '#4444ff',
                    weight: 2,
                    opacity: shapeData.properties.opacity || 0.7
                });
            case 'Polygon':
                return L.polygon(coords, {
                    color: shapeData.properties.color || '#4444ff',
                    weight: 2,
                    fillColor: shapeData.properties.color || '#4444ff',
                    fillOpacity: shapeData.properties.opacity || 0.3
                });
            default:
                return L.marker(coords[0], { icon: this.getDefaultMarkerIcon() });
        }
    }

    getShapeType(layer) {
        if (layer instanceof L.Marker) return 'Point';
        if (layer instanceof L.Polyline) return 'LineString';
        if (layer instanceof L.Polygon) return 'Polygon';
        return 'Point';
    }

    updateMarkerPosition(markerId, latlng) {
        const marker = this.markers.find(m => m.id === markerId);
        if (marker) {
            marker.lat = latlng.lat;
            marker.lng = latlng.lng;
            this.updateHiddenInput();
        }
    }

    updateShape(layer) {
        const shapeData = layer.shapeData;
        if (shapeData) {
            const coords = layer.getLatLngs ? layer.getLatLngs() : [layer.getLatLng()];
            shapeData.coordinates = coords.map(coord => [coord.lat, coord.lng]);
            this.updateHiddenInput();
        }
    }

    removeShape(layer) {
        const shapeData = layer.shapeData;
        if (shapeData) {
            const index = this.shapes.findIndex(s => s.id === shapeData.id);
            if (index > -1) {
                this.shapes.splice(index, 1);
                this.updateHiddenInput();
            }
        }
    }

    addMarkerAtLocation(latlng) {
        if (!this.canEdit || !this.config.allow_markers) return;

        // Check marker limit
        if (this.markers.length >= this.config.max_markers) {
            if (window.showAlert) window.showAlert(`Maximum of ${this.config.max_markers} markers allowed`, 'warning');
            else console.warn('Max markers reached');
            return;
        }

        // Create marker data
        const markerData = {
            id: this.generateId(),
            lat: parseFloat(latlng.lat.toFixed(this.config.coordinate_precision || 6)),
            lng: parseFloat(latlng.lng.toFixed(this.config.coordinate_precision || 6)),
            title: `Marker ${this.markers.length + 1}`,
            description: ''
        };

        // Add to markers array
        this.markers.push(markerData);

        // Add to map
        const marker = L.marker([markerData.lat, markerData.lng], { icon: this.getDefaultMarkerIcon() }).addTo(this.map);

        // Add tooltip (for both hover and click)
        const tooltipContent = this.buildMarkerTooltipContent(markerData);
        marker.bindTooltip(tooltipContent, {
            permanent: false,
            direction: 'top',
            offset: [0, -10],
            interactive: true, // Allow interaction with tooltip content
            className: 'marker-tooltip', // Add class for styling
            pane: 'tooltipPane', // Use Leaflet's tooltip pane
            sticky: true // Keep tooltip open when hovering over it
        });

        // Update UI
        this.updateHiddenInput();
        this.renderMarkersList();

        // Turn off marker mode
        this.markerMode = false;
        this.updateMarkerModeUI();
    }

    updateMarkerModeUI() {
        const button = document.getElementById(`add-marker-btn-${this.fieldId}`);
        const buttonText = button?.querySelector('.add-marker-text');

        if (this.markerMode) {
            // Active marker mode: use filled primary button style
            button?.classList.remove('btn-outline-primary');
            button?.classList.add('btn-primary');
            if (buttonText) buttonText.textContent = 'Click map to add marker';
            this.map.getContainer().style.cursor = 'crosshair';
        } else {
            // Inactive marker mode: use outline button style
            button?.classList.remove('btn-primary');
            button?.classList.add('btn-outline-primary');
            if (buttonText) buttonText.textContent = 'Add Marker';
            this.map.getContainer().style.cursor = '';
        }

        // Toggle visibility of manual coordinate inputs
        const manualCoordsContainer = document.getElementById(`manual-coordinates-${this.fieldId}`);
        if (manualCoordsContainer) {
            manualCoordsContainer.style.display = this.markerMode ? 'block' : 'none';
        }

        // Legacy support
        if (this.manualCoordinatesContainer) {
            this.manualCoordinatesContainer.style.display = this.markerMode ? '' : 'none';
        }
    }

    // Helper function to build tooltip content for a marker (used for both hover and click)
    buildMarkerTooltipContent(markerData) {
        const title = markerData.title || `Marker at ${markerData.lat.toFixed(6)}, ${markerData.lng.toFixed(6)}`;
        const description = markerData.description ? `<div class="text-gray-600 text-xs mt-1">${markerData.description}</div>` : '';

        const actionButtons = this.canEdit ? `
            <div class="flex gap-2 mt-2 pt-2 border-t border-gray-200">
                <button type="button"
                        class="tooltip-edit-btn px-2 py-1 text-xs bg-blue-500 text-white rounded hover:bg-blue-600 transition-colors"
                        data-action="map:edit-marker"
                        data-field-id="${this.fieldId}"
                        data-marker-id="${markerData.id}"
                        title="Edit marker">
                    <i class="fas fa-pen"></i> Edit
                </button>
                <button type="button"
                        class="tooltip-delete-btn px-2 py-1 text-xs bg-red-500 text-white rounded hover:bg-red-600 transition-colors"
                        data-action="map:remove-marker"
                        data-field-id="${this.fieldId}"
                        data-marker-id="${markerData.id}"
                        title="Remove marker">
                    <i class="fas fa-trash"></i> Delete
                </button>
            </div>
        ` : '';

        return `
            <div class="text-sm">
                <div class="font-medium">${title}</div>
                <div class="text-gray-600 text-xs">${markerData.lat.toFixed(6)}, ${markerData.lng.toFixed(6)}</div>
                ${description}
                ${actionButtons}
            </div>
        `;
    }

    // Custom tooltip implementation that renders outside map container
    setupCustomTooltip(marker, markerData) {
        let tooltipElement = null;
        let hideTimeout = null;

        const showTooltip = (event) => {
            if (hideTimeout) {
                clearTimeout(hideTimeout);
                hideTimeout = null;
            }

            if (tooltipElement) {
                tooltipElement.remove();
            }

            const content = this.buildMarkerTooltipContent(markerData);
            tooltipElement = document.createElement('div');
            tooltipElement.className = 'custom-marker-tooltip marker-tooltip';
            tooltipElement.innerHTML = content;
            tooltipElement.style.display = 'block';
            document.body.appendChild(tooltipElement);

            // Position tooltip relative to marker (after adding to DOM to get dimensions)
            const markerPoint = this.map.latLngToContainerPoint(marker.getLatLng());
            const mapRect = this.map.getContainer().getBoundingClientRect();

            const tooltipRect = tooltipElement.getBoundingClientRect();
            let left = mapRect.left + markerPoint.x - (tooltipRect.width / 2);
            let top = mapRect.top + markerPoint.y - tooltipRect.height - 10;

            // Adjust if tooltip would go off screen
            if (top < mapRect.top) {
                top = mapRect.top + markerPoint.y + 30; // Show below marker instead
            }
            if (left + tooltipRect.width > window.innerWidth) {
                left = window.innerWidth - tooltipRect.width - 10;
            }
            if (left < 0) {
                left = 10;
            }

            tooltipElement.style.left = `${left}px`;
            tooltipElement.style.top = `${top}px`;

            // Add event listeners for edit and delete buttons in tooltip
            const editBtn = tooltipElement.querySelector('[data-action="map:edit-marker"]');
            if (editBtn) {
                editBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    hideTooltip();
                    const markerId = editBtn.getAttribute('data-marker-id');
                    if (markerId) {
                        this.editMarker(markerId);
                    }
                });
            }

            const deleteBtn = tooltipElement.querySelector('[data-action="map:remove-marker"]');
            if (deleteBtn) {
                deleteBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    hideTooltip();
                    const markerId = deleteBtn.getAttribute('data-marker-id');
                    if (markerId) {
                        this.removeMarker(markerId);
                    }
                });
            }

            // Keep tooltip visible when hovering over it
            tooltipElement.addEventListener('mouseenter', () => {
                if (hideTimeout) {
                    clearTimeout(hideTimeout);
                    hideTimeout = null;
                }
            });

            tooltipElement.addEventListener('mouseleave', () => {
                hideTooltip();
            });
        };

        const hideTooltip = () => {
            if (hideTimeout) {
                clearTimeout(hideTimeout);
            }
            // Small delay before hiding to allow moving mouse to tooltip
            hideTimeout = setTimeout(() => {
                if (tooltipElement) {
                    tooltipElement.remove();
                    tooltipElement = null;
                }
            }, 100);
        };

        marker.on('mouseover', showTooltip);
        marker.on('mouseout', hideTooltip);
        marker.on('click', (e) => {
            if (tooltipElement && tooltipElement.style.display === 'none') {
                showTooltip(e);
            } else {
                hideTooltip();
            }
        });

        // Clean up on marker remove
        marker.on('remove', () => {
            if (hideTimeout) {
                clearTimeout(hideTimeout);
            }
            if (tooltipElement) {
                tooltipElement.remove();
                tooltipElement = null;
            }
        });
    }

    clearAllMapData() {
        if (!this.canEdit) return;

        const doClear = () => {
            // Clear markers
            this.markers = [];
            this.map.eachLayer((layer) => {
                if (layer instanceof L.Marker) {
                    this.map.removeLayer(layer);
                }
            });

            // Clear shapes
            this.shapes = [];
            if (this.drawingLayer) {
                this.drawingLayer.clearLayers();
            }

            // Update hidden input
            this.updateHiddenInput();
            this.renderMarkersList();
        };

        if (typeof window.showDangerConfirmation === 'function') {
            window.showDangerConfirmation('Are you sure you want to clear all markers and shapes?', doClear, null, 'Clear All', 'Cancel', 'Clear Map Data');
        } else if (typeof window.showConfirmation === 'function') {
            window.showConfirmation('Are you sure you want to clear all markers and shapes?', doClear, null, 'Clear All', 'Cancel', 'Clear Map Data');
        } else {
            if (confirm('Are you sure you want to clear all markers and shapes?')) doClear();
        }
    }

    updateHiddenInput() {
        if (!this.hiddenInput) return;

        // Create clean copies of markers and shapes without circular references and timestamps
        const cleanMarkers = this.config.allow_markers ? this.markers.map(marker => {
            const { leafletMarker, created_at, updated_at, ...cleanMarker } = marker;
            return cleanMarker;
        }) : [];

        const cleanShapes = this.config.allow_drawing ? this.shapes.map(shape => {
            const { leafletLayer, created_at, updated_at, ...cleanShape } = shape;
            return cleanShape;
        }) : [];

        // Get data availability options
        const dataNotAvailable = document.querySelector(`input[name="field_${this.fieldId}_data_not_available"]`);
        const notApplicable = document.querySelector(`input[name="field_${this.fieldId}_not_applicable"]`);

        const mapData = {
            _schema_version: '1.0.0',
            markers: cleanMarkers,
            shapes: cleanShapes,
            metadata: {
                total_markers: this.config.allow_markers ? this.markers.length : 0,
                total_shapes: this.config.allow_drawing ? this.shapes.length : 0,
                last_modified: new Date().toISOString(),
                user_id: null, // Would be set by backend
                session_id: null // Would be set by backend
            },
            // Include data availability options
            data_not_available: dataNotAvailable ? dataNotAvailable.checked : false,
            not_applicable: notApplicable ? notApplicable.checked : false
        };

        this.hiddenInput.value = JSON.stringify(mapData);

        // Trigger change event for form validation
        this.hiddenInput.dispatchEvent(new Event('change', { bubbles: true }));
    }

    renderMarkersList() {
        if (!this.config.allow_markers) return;

        const container = document.getElementById(`marker-list-${this.fieldId}`);
        if (!container) return;

        if (this.markers.length === 0) {
            container.innerHTML = '<p class="text-muted text-center mb-0">No markers added yet</p>';
            return;
        }

        const markersHtml = this.markers.map((marker, index) => `
            <div class="marker-item d-flex justify-content-between align-items-start p-2 border-bottom">
                <div class="flex-grow-1">
                    <div class="mb-1">
                        <strong>${marker.title || `Marker ${index + 1}`}</strong>
                    </div>
                    <div class="text-muted small mb-1">
                        <i class="fas fa-map-marker-alt"></i> Lat: ${marker.lat.toFixed(6)}, Lng: ${marker.lng.toFixed(6)}
                    </div>
                    ${marker.description ? `<div class="text-sm text-muted"><em>${marker.description}</em></div>` : '<div class="text-sm text-muted"><em>No description</em></div>'}
                </div>
                ${this.canEdit ? `
                    <div class="btn-group btn-group-sm ml-2">
                        <button type="button"
                                class="btn btn-outline-primary btn-sm"
                                data-action="map:edit-marker"
                                data-field-id="${this.fieldId}"
                                data-marker-id="${marker.id}"
                                title="Edit marker">
                            <i class="fas fa-pen"></i>
                        </button>
                        <button type="button"
                                class="btn btn-outline-danger btn-sm"
                                data-action="map:remove-marker"
                                data-field-id="${this.fieldId}"
                                data-marker-id="${marker.id}"
                                title="Remove marker">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                ` : ''}
            </div>
        `).join('');

        container.innerHTML = markersHtml;

        // Re-bind clear button event listener after rendering (in case it was re-rendered)
        const clearBtn = document.querySelector(`.marker-list-container [data-action="map:clear-markers"][data-field-id="${this.fieldId}"]`);
        if (clearBtn && !clearBtn.__clearMarkersBound) {
            clearBtn.__clearMarkersBound = true;
            clearBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.clearMarkers();
            });
        }

        // Re-bind edit and remove button event listeners after rendering
        const editButtons = container.querySelectorAll(`[data-action="map:edit-marker"][data-field-id="${this.fieldId}"]`);
        editButtons.forEach(btn => {
            if (!btn.__editMarkerBound) {
                btn.__editMarkerBound = true;
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const markerId = btn.getAttribute('data-marker-id');
                    if (markerId) {
                        this.editMarker(markerId);
                    }
                });
            }
        });

        const removeButtons = container.querySelectorAll(`[data-action="map:remove-marker"][data-field-id="${this.fieldId}"]`);
        removeButtons.forEach(btn => {
            if (!btn.__removeMarkerBound) {
                btn.__removeMarkerBound = true;
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const markerId = btn.getAttribute('data-marker-id');
                    if (markerId) {
                        this.removeMarker(markerId);
                    }
                });
            }
        });
    }

    generateId() {
        return 'marker_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }

    showLoading() {
        if (this.loadingOverlay) {
            this.loadingOverlay.style.display = 'flex';
        }
    }

    hideLoading() {
        if (this.loadingOverlay) {
            this.loadingOverlay.style.display = 'none';
        }
    }

    showError() {
        if (this.errorOverlay) {
            this.errorOverlay.classList.remove('hidden');
        }
        if (this.loadingOverlay) {
            this.loadingOverlay.style.display = 'none';
        }
    }

    // Method to search for a location
    async searchLocation(query) {
        if (!query || !query.trim()) {
            debugPluginWarn(this.pluginName, 'Search query is empty');
            return;
        }
        try {
            const url = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}&limit=1`;
            const response = await fetch(url, {
                headers: {
                    'Accept': 'application/json'
                }
            });
            if (!response.ok) {
                throw new Error(`Geocoding request failed with status ${response.status}`);
            }
            const results = await response.json();
            if (!Array.isArray(results) || results.length === 0) {
                if (window.showAlert) window.showAlert('No results found for that query', 'warning');
                else console.warn('No geocoding results');
                return;
            }
            const result = results[0];
            const lat = parseFloat(result.lat);
            const lng = parseFloat(result.lon);
            const targetZoom = Math.max(this.map.getZoom() || 0, 13);
            this.map.setView([lat, lng], targetZoom);
            this.updateCoordinateDisplay({ lat, lng });
            if (this.config.allow_markers && this.markerMode) {
                this.addMarker(lat, lng);
                this.toggleMarkerMode();
            }
        } catch (error) {
            debugPluginError(this.pluginName, 'Geocoding search failed', error);
            if (window.showAlert) window.showAlert('Failed to search for that location. Please try again.', 'error');
            else console.warn('Geocoding search failed');
        }
    }

    // Method to fetch autocomplete suggestions
    async fetchAutocompleteSuggestions(query) {
        // Clear existing debounce timer
        if (this.autocompleteDebounceTimer) {
            clearTimeout(this.autocompleteDebounceTimer);
        }

        // Debounce API calls (wait 300ms after user stops typing)
        this.autocompleteDebounceTimer = setTimeout(async () => {
            if (!query || query.length < 2) {
                this.hideAutocomplete();
                return;
            }

            try {
                const url = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}&limit=5&addressdetails=1`;
                const response = await fetch(url, {
                    headers: {
                        'Accept': 'application/json',
                        'User-Agent': 'IFRC-Network-Databank/1.0'
                    }
                });

                if (!response.ok) {
                    throw new Error(`Autocomplete request failed with status ${response.status}`);
                }

                const results = await response.json();
                if (Array.isArray(results) && results.length > 0) {
                    this.autocompleteSuggestions = results;
                    this.autocompleteSelectedIndex = -1;
                    this.renderAutocompleteDropdown();
                    this.showAutocomplete();
                } else {
                    this.hideAutocomplete();
                }
            } catch (error) {
                debugPluginError(this.pluginName, 'Autocomplete fetch failed', error);
                this.hideAutocomplete();
            }
        }, 300);
    }

    // Method to render autocomplete dropdown
    renderAutocompleteDropdown() {
        if (!this.autocompleteDropdown || this.autocompleteSuggestions.length === 0) {
            return;
        }

        const searchInput = document.getElementById(`address-search-${this.fieldId}`);
        if (!searchInput) return;

        let html = '<ul class="map-autocomplete-list">';
        this.autocompleteSuggestions.forEach((suggestion, index) => {
            const displayName = suggestion.display_name || suggestion.name || 'Unknown location';
            const isSelected = index === this.autocompleteSelectedIndex ? 'selected' : '';
            html += `
                <li class="map-autocomplete-item ${isSelected}"
                    data-index="${index}"
                    data-lat="${suggestion.lat}"
                    data-lng="${suggestion.lon}"
                    data-display-name="${displayName.replace(/"/g, '&quot;')}">
                    <div class="map-autocomplete-item-name">${this.highlightMatch(displayName, searchInput.value)}</div>
                    ${suggestion.address ? `<div class="map-autocomplete-item-details">${this.formatAddress(suggestion.address)}</div>` : ''}
                </li>
            `;
        });
        html += '</ul>';

        this.autocompleteDropdown.innerHTML = html;

        // Use event delegation on the dropdown container
        // Remove existing handlers to avoid duplicates
        if (this.autocompleteDropdown.__clickHandlerBound) {
            this.autocompleteDropdown.removeEventListener('click', this.autocompleteDropdown.__clickHandlerBound);
            this.autocompleteDropdown.removeEventListener('pointerdown', this.autocompleteDropdown.__pointerdownHandlerBound, true);
        }

        // Add click handler using event delegation
        const clickHandler = (e) => {
            const item = e.target.closest('.map-autocomplete-item');
            if (!item) return;

            e.preventDefault();
            e.stopPropagation();
            e.stopImmediatePropagation();

            const index = parseInt(item.getAttribute('data-index'), 10);
            debugPluginLog(this.pluginName, `Click on autocomplete item ${index}`);
            this.selectAutocompleteItemElement(item);
        };

        // Also handle pointerdown to catch it before document click handler
        const pointerdownHandler = (e) => {
            const item = e.target.closest('.map-autocomplete-item');
            if (!item) return;

            e.preventDefault();
            e.stopPropagation();
            e.stopImmediatePropagation();

            const index = parseInt(item.getAttribute('data-index'), 10);
            debugPluginLog(this.pluginName, `Pointerdown on autocomplete item ${index}`);
            this.selectAutocompleteItemElement(item);
        };

        this.autocompleteDropdown.addEventListener('click', clickHandler);
        this.autocompleteDropdown.addEventListener('pointerdown', pointerdownHandler, true); // Use capture phase
        this.autocompleteDropdown.__clickHandlerBound = clickHandler;
        this.autocompleteDropdown.__pointerdownHandlerBound = pointerdownHandler;

        // Add mouseenter handlers for highlighting
        const items = this.autocompleteDropdown.querySelectorAll('.map-autocomplete-item');
        items.forEach((item, index) => {
            item.addEventListener('mouseenter', () => {
                this.autocompleteSelectedIndex = index;
                this.renderAutocompleteDropdown();
            });
        });
    }

    // Method to highlight matching text in suggestions
    highlightMatch(text, query) {
        if (!query) return text;
        const regex = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
        return text.replace(regex, '<strong>$1</strong>');
    }

    // Method to format address for display
    formatAddress(address) {
        if (!address) return '';
        const parts = [];
        if (address.city || address.town || address.village) {
            parts.push(address.city || address.town || address.village);
        }
        if (address.state || address.region) {
            parts.push(address.state || address.region);
        }
        if (address.country) {
            parts.push(address.country);
        }
        return parts.join(', ');
    }

    // Method to show autocomplete dropdown
    showAutocomplete() {
        if (this.autocompleteDropdown && this.autocompleteSuggestions.length > 0) {
            this.autocompleteDropdown.style.display = 'block';
            const searchWrapper = this.autocompleteDropdown.parentElement;
            if (searchWrapper) {
                searchWrapper.classList.add('has-autocomplete');
            }
        }
    }

    // Method to hide autocomplete dropdown
    hideAutocomplete() {
        if (this.autocompleteDropdown) {
            this.autocompleteDropdown.style.display = 'none';
            this.autocompleteSelectedIndex = -1;
            const searchWrapper = this.autocompleteDropdown.parentElement;
            if (searchWrapper) {
                searchWrapper.classList.remove('has-autocomplete');
            }
        }
    }

    // Method to navigate autocomplete with arrow keys
    navigateAutocomplete(direction) {
        if (this.autocompleteSuggestions.length === 0) return;

        this.autocompleteSelectedIndex += direction;

        if (this.autocompleteSelectedIndex < -1) {
            this.autocompleteSelectedIndex = this.autocompleteSuggestions.length - 1;
        } else if (this.autocompleteSelectedIndex >= this.autocompleteSuggestions.length) {
            this.autocompleteSelectedIndex = -1;
        }

        this.renderAutocompleteDropdown();

        // Scroll selected item into view
        if (this.autocompleteSelectedIndex >= 0) {
            const selectedItem = this.autocompleteDropdown.querySelector(`.map-autocomplete-item[data-index="${this.autocompleteSelectedIndex}"]`);
            if (selectedItem) {
                selectedItem.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
            }
        }
    }

    // Method to select an autocomplete suggestion
    selectAutocompleteSuggestion(index) {
        if (index < 0 || index >= this.autocompleteSuggestions.length) {
            debugPluginWarn(this.pluginName, `Invalid autocomplete index: ${index}`);
            return;
        }

        const suggestion = this.autocompleteSuggestions[index];
        if (!suggestion) {
            debugPluginWarn(this.pluginName, `No suggestion at index: ${index}`);
            return;
        }

        const lat = parseFloat(suggestion.lat);
        const lng = parseFloat(suggestion.lon);
        const displayName = suggestion.display_name || suggestion.name || '';
        this.applyAutocompleteSelection(lat, lng, displayName);
    }

    selectAutocompleteItemElement(item) {
        if (!item) return;

        const index = parseInt(item.getAttribute('data-index'), 10);
        if (!isNaN(index) && this.autocompleteSuggestions[index]) {
            this.selectAutocompleteSuggestion(index);
            return;
        }

        const lat = parseFloat(item.getAttribute('data-lat'));
        const lng = parseFloat(item.getAttribute('data-lng'));
        const displayName = item.getAttribute('data-display-name') || item.textContent?.trim() || '';
        this.applyAutocompleteSelection(lat, lng, displayName);
    }

    applyAutocompleteSelection(lat, lng, displayName) {
        if (isNaN(lat) || isNaN(lng)) {
            debugPluginError(this.pluginName, `Invalid coordinates: lat=${lat}, lng=${lng}`);
            return;
        }

        debugPluginLog(this.pluginName, `Selecting autocomplete suggestion: ${displayName} at ${lat}, ${lng}`);

        // Update input value
        const searchInput = document.getElementById(`address-search-${this.fieldId}`);
        if (searchInput) {
            searchInput.value = displayName;
        }

        // Hide autocomplete first
        this.hideAutocomplete();

        // Check if map is initialized
        if (!this.map) {
            debugPluginWarn(this.pluginName, 'Map not initialized yet, deferring autocomplete selection');
            this.pendingAutocompleteSelection = { lat, lng, displayName };
            return;
        }

        // Center map on selected location
        try {
            const targetZoom = Math.max(this.map.getZoom() || 0, 13);
            this.map.setView([lat, lng], targetZoom);
            this.updateCoordinateDisplay({ lat, lng });

            // Add marker if in marker mode
            if (this.config.allow_markers && this.markerMode) {
                this.addMarker(lat, lng);
                this.toggleMarkerMode();
            }
        } catch (error) {
            debugPluginError(this.pluginName, 'Error centering map on selected location', error);
        }
    }

    // Method to check if modal exists
    hasModal() {
        const modal = document.getElementById(`marker-edit-modal-${this.fieldId}`);
        debugPluginLog(this.pluginName, `Checking for modal with id: marker-edit-modal-${this.fieldId}, found:`, modal !== null);
        return modal !== null;
    }

    // Method to create modal dynamically if it doesn't exist
    createModal() {
        if (this.hasModal()) return;

        debugPluginLog(this.pluginName, `Creating modal dynamically for field ${this.fieldId}`);

        const modalHtml = `
            <div id="marker-edit-modal-${this.fieldId}" class="fixed inset-0 bg-gray-800 bg-opacity-75 overflow-y-auto h-full w-full hidden z-[9999] flex items-center justify-center px-4">
                <div class="relative p-6 border w-full max-w-lg shadow-xl rounded-lg bg-white transition-all duration-300">
                    <button type="button" class="absolute top-3 right-3 text-gray-400 hover:text-gray-600 close-modal" data-action="map:hide-modal" data-field-id="${this.fieldId}" aria-label="Close modal">
                        <i class="fas fa-times w-6 h-6"></i>
                    </button>
                    <h3 class="text-xl font-semibold mb-5 text-gray-800 flex items-center">
                        <i class="fas fa-pen w-6 h-6 mr-2 text-blue-600"></i>
                        Edit Marker
                    </h3>
                    <form id="marker-edit-form-${this.fieldId}">
                        <div class="mb-4">
                            <label for="marker-title-${this.fieldId}" class="block text-gray-700 text-sm font-semibold mb-2">Marker Title</label>
                            <input type="text"
                                   class="mt-1 block w-full py-2 px-3 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                                   id="marker-title-${this.fieldId}"
                                   placeholder="Enter marker title...">
                        </div>
                        <div class="mb-4">
                            <label for="marker-description-${this.fieldId}" class="block text-gray-700 text-sm font-semibold mb-2">Description</label>
                            <textarea class="mt-1 block w-full py-2 px-3 border border-gray-300 bg-white rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                                      id="marker-description-${this.fieldId}"
                                      rows="3"
                                      placeholder="Enter marker description..."></textarea>
                        </div>
                        <div class="mb-6">
                            <label class="block text-gray-700 text-sm font-semibold mb-2">Coordinates</label>
                            <div class="grid grid-cols-2 gap-4">
                                <div>
                                    <input type="text"
                                           class="mt-1 block w-full py-2 px-3 border border-gray-300 bg-gray-100 rounded-md shadow-sm sm:text-sm"
                                           id="marker-lat-${this.fieldId}"
                                           readonly
                                           placeholder="Latitude">
                                </div>
                                <div>
                                    <input type="text"
                                           class="mt-1 block w-full py-2 px-3 border border-gray-300 bg-gray-100 rounded-md shadow-sm sm:text-sm"
                                           id="marker-lng-${this.fieldId}"
                                           readonly
                                           placeholder="Longitude">
                                </div>
                            </div>
                        </div>
                        <div class="flex justify-end space-x-3">
                            <button type="button" class="px-4 py-2 bg-gray-200 hover:bg-gray-300 text-gray-700 font-semibold rounded-lg shadow-sm text-sm" data-action="map:hide-modal" data-field-id="${this.fieldId}">Cancel</button>
                            <button type="button" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-lg shadow-sm text-sm" data-action="map:save-marker-edit" data-field-id="${this.fieldId}">
                                <i class="fas fa-save mr-1"></i> Save Changes
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        `;

        // Add modal to the end of the body (avoid insertAdjacentHTML)
        const modalTemplate = document.createElement('template');
        modalTemplate.innerHTML = modalHtml.trim();
        document.body.appendChild(modalTemplate.content);

        // Attach direct event listeners to modal buttons (they're in document.body, not the wrapper)
        const modal = document.getElementById(`marker-edit-modal-${this.fieldId}`);
        if (modal) {
            // Store handler references for cleanup
            this._modalEscapeHandler = (e) => {
                if (e.key === 'Escape' && modal && !modal.classList.contains('hidden')) {
                    this.hideModal();
                }
            };
            this._modalBackdropHandler = (e) => {
                if (e.target === modal) {
                    this.hideModal();
                }
            };

            // Save button
            const saveBtn = modal.querySelector('[data-action="map:save-marker-edit"]');
            if (saveBtn) {
                saveBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    this.saveMarkerEdit();
                });
            }

            // Cancel/Close buttons (X button and Cancel button)
            const closeBtns = modal.querySelectorAll('[data-action="map:hide-modal"], .close-modal');
            closeBtns.forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    this.hideModal();
                });
            });

            // Backdrop click to close
            modal.addEventListener('click', this._modalBackdropHandler);

            // Escape key to close (document-level, but scoped to this modal)
            document.addEventListener('keydown', this._modalEscapeHandler);
        }
    }

    // Method to hide modal properly
    hideModal() {
        const modal = document.getElementById(`marker-edit-modal-${this.fieldId}`);

        if (modal) {
            modal.classList.add('hidden');
            modal.classList.remove('flex');
        }

        // Clear the editing marker ID
        this.currentEditingMarkerId = null;
    }

    // Method to edit a marker
    editMarker(markerId) {
        debugPluginLog(this.pluginName, `editMarker called for markerId: ${markerId}, fieldId: ${this.fieldId}`);

        const marker = this.markers.find(m => m.id === markerId);
        if (!marker) {
            debugPluginError(this.pluginName, `Marker not found with id: ${markerId}`);
            return;
        }

        // Store the current marker ID for saving
        this.currentEditingMarkerId = markerId;

        // Check if modal exists first, create it if it doesn't
        if (!this.hasModal()) {
            debugPluginLog(this.pluginName, 'Modal not found. Creating modal dynamically.');
            this.createModal();

            // Wait a bit for the modal to be added to the DOM
            setTimeout(() => {
                this.editMarker(markerId);
            }, 100);
            return;
        }

        // Check if modal elements exist before trying to populate them
        const titleEl = document.getElementById(`marker-title-${this.fieldId}`);
        const descriptionEl = document.getElementById(`marker-description-${this.fieldId}`);
        const latEl = document.getElementById(`marker-lat-${this.fieldId}`);
        const lngEl = document.getElementById(`marker-lng-${this.fieldId}`);

        if (!titleEl || !descriptionEl || !latEl || !lngEl) {
            debugPluginError(this.pluginName, 'Modal elements not found. Falling back to prompt method.');
            this.editMarkerWithPrompt(marker);
            return;
        }

        // Populate the modal with current marker data
        titleEl.value = marker.title || '';
        descriptionEl.value = marker.description || '';
        latEl.value = marker.lat.toFixed(6);
        lngEl.value = marker.lng.toFixed(6);

        // Show the modal
        const modal = document.getElementById(`marker-edit-modal-${this.fieldId}`);
        if (modal) {
            // Show modal using Tailwind classes (createModal already attached event listeners)
            modal.classList.remove('hidden');
            modal.classList.add('flex');

            // Focus the first input field for accessibility
            setTimeout(() => {
                const firstInput = modal.querySelector('input[type="text"]:not([readonly])');
                if (firstInput) {
                    firstInput.focus();
                }
            }, 100);
        }
    }

    // Fallback method using prompts
    editMarkerWithPrompt(marker) {
        const title = prompt('Enter marker title:', marker.title || '');
            if (title !== null) {
                marker.title = title;
                const description = prompt('Enter marker description:', marker.description || '');
                if (description !== null) {
                    marker.description = description;

                    // Tooltip will be updated automatically on next hover since it reads from marker data
                    // No need to manually update custom tooltip

                // Update hidden input and display
                this.updateHiddenInput();
                this.renderMarkersList();
            }
        }
    }

    // Method to save marker edit
    saveMarkerEdit() {
        if (!this.currentEditingMarkerId) return;

        const marker = this.markers.find(m => m.id === this.currentEditingMarkerId);
        if (!marker) return;

        // Get values from the modal with null checks
        const titleEl = document.getElementById(`marker-title-${this.fieldId}`);
        const descriptionEl = document.getElementById(`marker-description-${this.fieldId}`);

        if (!titleEl || !descriptionEl) {
            debugPluginError(this.pluginName, 'Modal elements not found for saving.');
            return;
        }

        const title = titleEl.value.trim();
        const description = descriptionEl.value.trim();

        // Update marker data
        marker.title = title;
        marker.description = description;

        // Tooltip will be updated automatically on next hover since it reads from marker data
        // No need to manually update custom tooltip

        // Update hidden input and display
        this.updateHiddenInput();
        this.renderMarkersList();

        // Hide the modal
        this.hideModal();
    }

    // Method to remove a specific marker
    removeMarker(markerId) {
        const markerIndex = this.markers.findIndex(m => m.id === markerId);
        if (markerIndex === -1) return;

        const marker = this.markers[markerIndex];

        // Check minimum markers requirement
        if (this.config.min_markers > 0 && this.markers.length <= this.config.min_markers) {
            if (window.showAlert) window.showAlert(`Minimum of ${this.config.min_markers} marker(s) required. Cannot remove more markers.`, 'warning');
            else console.warn('Min markers required');
            return;
        }

        // Remove from map if it exists
        if (marker.leafletMarker && this.map) {
            this.map.removeLayer(marker.leafletMarker);
        }

        // Remove from markers array
        this.markers.splice(markerIndex, 1);

        // Update hidden input and display
        this.updateHiddenInput();
        this.renderMarkersList();
        this.updateMarkerCount();
    }

    // Method to clear all markers
    clearMarkers() {
        // Check minimum markers requirement
        if (this.config.min_markers > 0 && this.markers.length <= this.config.min_markers) {
            if (window.showAlert) window.showAlert(`Minimum of ${this.config.min_markers} marker(s) required. Cannot remove more markers.`, 'warning');
            else console.warn('Min markers required');
            return;
        }

        const markerCount = this.markers.length;
        if (markerCount === 0) {
            return; // Nothing to clear
        }

        // Use custom confirmation dialog
        const confirmMessage = markerCount === 1
            ? 'Are you sure you want to remove this marker?'
            : `Are you sure you want to remove all ${markerCount} markers?`;

        // Check if custom confirmation function is available
        if (typeof window.showDangerConfirmation === 'function') {
            window.showDangerConfirmation(
                confirmMessage,
                () => {
                    // User confirmed - clear markers
                    this.markers.forEach(marker => {
                        if (marker.leafletMarker && this.map) {
                            this.map.removeLayer(marker.leafletMarker);
                        }
                    });
                    this.markers = [];
                    this.updateHiddenInput();
                    this.renderMarkersList();
                    this.updateMarkerCount();
                },
                null, // onCancel - no action needed
                'Clear All',
                'Cancel',
                'Clear All Markers'
            );
        } else if (typeof window.showConfirmation === 'function') {
            // Fallback to regular confirmation if danger version not available
            window.showConfirmation(
                confirmMessage,
                () => {
                    // User confirmed - clear markers
                    this.markers.forEach(marker => {
                        if (marker.leafletMarker && this.map) {
                            this.map.removeLayer(marker.leafletMarker);
                        }
                    });
                    this.markers = [];
                    this.updateHiddenInput();
                    this.renderMarkersList();
                    this.updateMarkerCount();
                },
                null, // onCancel - no action needed
                'Clear All',
                'Cancel',
                'Clear All Markers'
            );
        } else {
            // Ultimate fallback: native confirm when custom dialogs not loaded
            if (confirm(confirmMessage)) {
                this.markers.forEach(marker => {
                    if (marker.leafletMarker && this.map) {
                        this.map.removeLayer(marker.leafletMarker);
                    }
                });
                this.markers = [];
                this.updateHiddenInput();
                this.renderMarkersList();
                this.updateMarkerCount();
            }
        }
    }

    // Method to center the map
    centerMap() {
        if (this.map) {
            const center = {
                lat: this.config.map_center_lat || 0,
                lng: this.config.map_center_lng || 0
            };
            const zoom = this.config.default_zoom || 10;
            this.map.setView([center.lat, center.lng], zoom);
            debugPluginLog(this.pluginName, `Map centered to ${center.lat}, ${center.lng} at zoom ${zoom}`);
        }
    }

    // Keep a legacy no-op method name out of the way to avoid overriding
    updateCenterDisplayLegacy() {}

    // Update marker count display
    updateMarkerCount() {
        if (!this.config.allow_markers) return;

        const markerCountEl = document.getElementById(`marker-count-${this.fieldId}`);
        if (markerCountEl) {
            markerCountEl.textContent = this.markers.length;
        }
    }
}

// Global namespaced API and instance registry to align with template usage
(() => {
    const instances = new Map();
    const getWrapperForField = (fieldId) => document.querySelector(`.interactive-map-field[data-field-id="${fieldId}"]`);
    const getInstance = (fieldId) => {
        if (instances.has(fieldId)) return instances.get(fieldId);
        const el = getWrapperForField(fieldId);
        return el && el.mapField ? el.mapField : null;
    };

    function initField(fieldType, fieldId) {
        try {
            const wrapper = getWrapperForField(fieldId) || document.querySelector(`.interactive-map-field`);
            if (!wrapper) {
                console.error(`InteractiveMapField: wrapper not found for field ${fieldId}`);
                return;
            }
            if (wrapper.mapField) {
                // Already initialized
                return;
            }
            const instance = new InteractiveMapField(fieldId);
            wrapper.mapField = instance;
            instances.set(fieldId, instance);
            instance.initialize();
        } catch (e) {
            console.error('InteractiveMapField.initField failed', e);
        }
    }

    function setupInfoUpdates(fieldId) {
        const inst = getInstance(fieldId);
        if (!inst) return;
        // Ensure info panel reflects current state
        inst.updateCoordinateDisplay();
        if (inst.config?.allow_markers) {
            inst.updateMarkerCount();
            inst.renderMarkersList();
        }
    }

    function searchLocation(query, fieldId) {
        const inst = getInstance(fieldId);
        if (!inst) return;
        inst.searchLocation(query);
    }

    function clearMarkers(fieldId) {
        const inst = getInstance(fieldId);
        if (!inst) return;
        inst.clearMarkers();
    }

    function centerMap(fieldId) {
        const inst = getInstance(fieldId);
        if (!inst) return;
        inst.centerMap();
    }

    function goToCurrentLocation(fieldId) {
        const inst = getInstance(fieldId);
        if (!inst) return;
        inst.goToCurrentLocation();
    }

    // Expose API on window under the expected namespace
    window.InteractiveMapField = window.InteractiveMapField || {};
    window.InteractiveMapField.initField = initField;
    window.InteractiveMapField.setupInfoUpdates = setupInfoUpdates;
    window.InteractiveMapField.searchLocation = searchLocation;
    window.InteractiveMapField.clearMarkers = clearMarkers;
    window.InteractiveMapField.centerMap = centerMap;
    window.InteractiveMapField.goToCurrentLocation = goToCurrentLocation;
    window.InteractiveMapField.saveMarkerEdit = function(fieldId) {
        const inst = getInstance(fieldId);
        if (!inst) return;
        inst.saveMarkerEdit();
    };

    window.InteractiveMapField.hideModal = function(fieldId) {
        const inst = getInstance(fieldId);
        if (!inst) return;
        inst.hideModal();
    };
})();

// Global functions for HTML onclick handlers
window.toggleMarkerMode = function(fieldId) {
    const fieldElement = document.querySelector(`[data-field-id="${fieldId}"]`);
    if (fieldElement && fieldElement.mapField) {
        fieldElement.mapField.toggleMarkerMode();
    }
};

window.toggleDrawingMode = function(fieldId) {
    const fieldElement = document.querySelector(`[data-field-id="${fieldId}"]`);
    if (fieldElement && fieldElement.mapField) {
        fieldElement.mapField.toggleDrawingMode();
    }
};

window.clearAllMapData = function(fieldId) {
    const fieldElement = document.querySelector(`[data-field-id="${fieldId}"]`);
    if (fieldElement && fieldElement.mapField) {
        fieldElement.mapField.clearAllMapData();
    }
};

window.addManualMarker = function(fieldId) {
    const fieldElement = document.querySelector(`[data-field-id="${fieldId}"]`);
    if (fieldElement && fieldElement.mapField) {
        fieldElement.mapField.addManualMarker();
    }
};

window.removeMarker = function(fieldId, markerId) {
    const fieldElement = document.querySelector(`[data-field-id="${fieldId}"]`);
    if (fieldElement && fieldElement.mapField) {
        fieldElement.mapField.removeMarker(markerId);
    }
};

window.retryMapLoad = function(fieldId) {
    const fieldElement = document.querySelector(`[data-field-id="${fieldId}"]`);
    if (fieldElement && fieldElement.mapField) {
        fieldElement.mapField.initialize();
    }
};

// Global functions for the new methods
window.searchLocation = function(fieldId, query) {
    const fieldElement = document.querySelector(`[data-field-id="${fieldId}"]`);
    if (fieldElement && fieldElement.mapField) {
        fieldElement.mapField.searchLocation(query);
    }
};

window.clearMarkers = function(fieldId) {
    const fieldElement = document.querySelector(`[data-field-id="${fieldId}"]`);
    if (fieldElement && fieldElement.mapField) {
        fieldElement.mapField.clearMarkers();
    }
};

window.centerMap = function(fieldId) {
    const fieldElement = document.querySelector(`[data-field-id="${fieldId}"]`);
    if (fieldElement && fieldElement.mapField) {
        fieldElement.mapField.centerMap();
    }
};

window.editMarker = function(fieldId, markerId) {
    const fieldElement = document.querySelector(`[data-field-id="${fieldId}"]`);
    if (fieldElement && fieldElement.mapField) {
        fieldElement.mapField.editMarker(markerId);
    }
};

window.removeMarker = function(fieldId, markerId) {
    const fieldElement = document.querySelector(`[data-field-id="${fieldId}"]`);
    if (fieldElement && fieldElement.mapField) {
        fieldElement.mapField.removeMarker(markerId);
    }
};

window.goToCurrentLocation = function(fieldId) {
    const fieldElement = document.querySelector(`[data-field-id="${fieldId}"]`);
    if (fieldElement && fieldElement.mapField) {
        fieldElement.mapField.goToCurrentLocation();
    }
};

window.hideModal = function(fieldId) {
    const fieldElement = document.querySelector(`[data-field-id="${fieldId}"]`);
    if (fieldElement && fieldElement.mapField) {
        fieldElement.mapField.hideModal();
    }
};

window.saveMarkerEdit = function(fieldId) {
    const fieldElement = document.querySelector(`[data-field-id="${fieldId}"]`);
    if (fieldElement && fieldElement.mapField) {
        fieldElement.mapField.saveMarkerEdit();
    }
};
