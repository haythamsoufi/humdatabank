// Backoffice/plugins/interactive_map/static/js/map_field_renderer.js
/**
 * Shared HTML renderer for interactive map fields.
 * This is the single source of truth for the map field HTML structure.
 * Used by both:
 * - Client-side rendering (plugin-field-loader.js)
 * - Template rendering (field.html - via JavaScript)
 */

/**
 * Renders the complete HTML structure for an interactive map field.
 *
 * @param {Object} options - Configuration options
 * @param {string} options.fieldId - Unique field identifier
 * @param {Object} options.pluginConfig - Plugin configuration object
 * @param {Object} options.existingData - Existing field data
 * @param {boolean} options.canEdit - Whether the field is editable
 * @returns {string} Complete HTML string for the map field
 */
export function renderInteractiveMapFieldHTML({ fieldId, pluginConfig = {}, existingData = {}, canEdit = true }) {
    // Sanitize fieldId for safe use in HTML
    const safeFieldId = String(fieldId).replace(/[^a-zA-Z0-9_-]/g, '');

    // Calculate safe map height
    const mapHeightNum = Number(pluginConfig && pluginConfig.map_height);
    const safeMapHeight = (isFinite(mapHeightNum) && mapHeightNum >= 100 && mapHeightNum <= 2000)
        ? Math.round(mapHeightNum)
        : 400;

    // Helper to check boolean config values
    const isEnabled = (key) => {
        const value = pluginConfig && pluginConfig[key];
        return value === 'true' || value === true;
    };

    // Generate search input HTML
    const searchInputHTML = isEnabled('show_search_box') ? `
                <div class="map-controls mb-3">
                    <div class="row">
                        <div class="col-md-6">
                            <div class="search-input-wrapper">
                                <input type="text"
                                       class="form-control search-input-with-icons"
                                       id="address-search-${safeFieldId}"
                                       placeholder="Search for a location...">
                                <button class="btn btn-link search-icon-btn"
                                        type="button"
                                        data-action="map:search-location"
                                        data-field-id="${safeFieldId}"
                                        data-input-id="address-search-${safeFieldId}">
                                    <i class="fas fa-search"></i>
                                </button>
                                <button class="btn btn-link locate-icon-btn"
                                        type="button"
                                        data-action="map:go-to-current-location"
                                        data-field-id="${safeFieldId}"
                                        title="Locate me"
                                        aria-label="Locate me">
                                    <i class="fas fa-crosshairs"></i>
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
    ` : '';

    // Generate manual coordinates HTML
    const manualCoordinatesHTML = isEnabled('allow_markers') ? `
                <div class="manual-coordinates mb-3" style="display: none;">
                    <div class="flex flex-wrap items-end gap-3">
                        <div class="flex items-center gap-2">
                            <label for="manual-lat-${safeFieldId}" class="text-xs font-medium text-gray-600 mb-0">Latitude:</label>
                            <input type="number"
                                   id="manual-lat-${safeFieldId}"
                                   class="w-full md:w-40 px-2 py-1 text-sm border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                                   step="0.000001"
                                   placeholder="0.000000">
                        </div>
                        <div class="flex items-center gap-2">
                            <label for="manual-lng-${safeFieldId}" class="text-xs font-medium text-gray-600 mb-0">Longitude:</label>
                            <input type="number"
                                   id="manual-lng-${safeFieldId}"
                                   class="w-full md:w-40 px-2 py-1 text-sm border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                                   step="0.000001"
                                   placeholder="0.000000">
                        </div>
                        <div class="flex items-center">
                            <button type="button"
                                    class="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                                    data-action="map:add-manual-marker"
                                    data-field-id="${safeFieldId}">
                                + Add Marker
                            </button>
                        </div>
                    </div>
                </div>
    ` : '';

    // Generate map controls HTML
    const mapControlsHTML = `
                <div class="map-controls mt-3">
                    <div class="btn-group" role="group">
                        ${isEnabled('allow_markers') ? `
                        <button type="button"
                                id="add-marker-btn-${safeFieldId}"
                                class="btn btn-outline-primary btn-sm"
                                data-action="map:toggle-marker-mode"
                                data-field-id="${safeFieldId}">
                            <i class="fas fa-map-marker-alt"></i> Add Marker
                        </button>
                        ` : ''}
                        ${isEnabled('allow_markers') ? `
                        <button type="button"
                                class="btn btn-outline-secondary btn-sm"
                                data-action="map:clear-markers"
                                data-field-id="${safeFieldId}">
                            <i class="fas fa-trash"></i> Clear Markers
                        </button>
                        ` : ''}
                        <button type="button"
                                class="btn btn-outline-secondary btn-sm"
                                data-action="map:center-map"
                                data-field-id="${safeFieldId}">
                            <i class="fas fa-crosshairs"></i> Center Map
                        </button>
                    </div>
                </div>
    `;

    // Generate marker list HTML
    const markerListHTML = isEnabled('allow_markers') ? `
                <div class="mt-3">
                    <div class="card">
                        <div class="card-header">
                            <h6 class="mb-0">
                                <i class="fas fa-list text-success"></i>
                                Marker List
                            </h6>
                        </div>
                        <div class="card-body">
                            <div id="marker-list-${safeFieldId}" class="marker-list">
                                <p class="text-muted text-center mb-0">No markers added yet</p>
                            </div>
                        </div>
                    </div>
                </div>
    ` : '';

    // Generate data availability options HTML
    const dataAvailabilityHTML = (pluginConfig.allow_data_not_available || pluginConfig.allow_not_applicable) ? `
                <div class="mt-3 flex items-center justify-end gap-4 text-sm">
                    ${pluginConfig.allow_data_not_available ? `
                    <label class="inline-flex items-center">
                        <input type="checkbox" name="field_${safeFieldId}_data_not_available" value="1" class="form-checkbox h-4 w-4 text-gray-500 border-gray-300 rounded focus:ring-gray-500" ${existingData && existingData.data_not_available ? 'checked' : ''}>
                        <span class="ml-2 text-gray-600 font-medium">Applicable but data not available</span>
                    </label>
                    ` : ''}
                    ${pluginConfig.allow_not_applicable ? `
                    <label class="inline-flex items-center">
                        <input type="checkbox" name="field_${safeFieldId}_not_applicable" value="1" class="form-checkbox h-4 w-4 text-gray-500 border-gray-300 rounded focus:ring-gray-500" ${existingData && existingData.not_applicable ? 'checked' : ''}>
                        <span class="ml-2 text-gray-600 font-medium">Not applicable</span>
                    </label>
                    ` : ''}
                </div>
    ` : '';

    // Assemble complete HTML
    return `
        <div class="interactive-map-field" data-field-id="${safeFieldId}" data-can-edit="${canEdit ? 'true' : 'false'}" data-existing-data="${JSON.stringify(existingData).replace(/"/g, '&quot;')}">
            ${searchInputHTML}
            ${manualCoordinatesHTML}
            <div class="map-container">
                <div id="map-${safeFieldId}"
                     class="map-field"
                     style="height: ${safeMapHeight}px; width: 100%; border-radius: 8px; overflow: hidden; position: relative;">
                    <!-- Map will be rendered here by JavaScript -->

                    <!-- Loading overlay -->
                    <div id="map-loading-${safeFieldId}" class="map-loading-overlay" style="display: none;">
                        <div class="spinner-border text-primary" role="status">
                            <span class="sr-only">Loading...</span>
                        </div>
                    </div>

                    <!-- Error overlay -->
                    <div id="map-error-${safeFieldId}" class="map-error-overlay" style="display: none;">
                        <div class="alert alert-danger">
                            <i class="fas fa-exclamation-triangle"></i>
                            <span class="error-message">An error occurred while loading the map</span>
                        </div>
                    </div>
                </div>
            </div>
            ${mapControlsHTML}
            <!-- Coordinate and zoom display for real-time updates -->
            <div id="coordinate-display-${safeFieldId}" class="coordinate-display mb-2" style="display: none;">
                <small class="text-gray-600">
                    <i class="fas fa-crosshairs"></i>
                    Coordinates: <span class="coordinates-text">--</span>
                    <span class="mx-2">|</span>
                    Zoom: <span id="zoom-level-${safeFieldId}">--</span>
                </small>
            </div>
            ${markerListHTML}
            <!-- Hidden input for form submission -->
            <input type="hidden"
                   name="field_value[${safeFieldId}]"
                   id="map-data-${safeFieldId}"
                   value="${JSON.stringify(existingData).replace(/"/g, '&quot;')}">
            <!-- Field validation feedback -->
            <div class="invalid-feedback" id="map-validation-${safeFieldId}"></div>
            ${dataAvailabilityHTML}
            <!-- Map Configuration (Hidden) -->
            <div id="map-config-${safeFieldId}" class="hidden" aria-hidden="true"></div>
        </div>
    `;
}

// Export for use in Node.js-like environments if needed
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { renderInteractiveMapFieldHTML };
}
