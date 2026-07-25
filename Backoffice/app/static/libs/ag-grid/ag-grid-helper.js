/**
 * AG Grid Helper — entry shim (backward-compatible script URL).
 * Implementation is split across ag-grid-helper-*.js; see ag_grid_includes.html load order.
 */
(function(global) {
    'use strict';
    if (!global.AgGridHelper) {
        throw new Error('ag-grid-helper.js: AgGridHelper not loaded. Include ag-grid-helper-core.js and extension modules.');
    }
})(typeof window !== 'undefined' ? window : this);
