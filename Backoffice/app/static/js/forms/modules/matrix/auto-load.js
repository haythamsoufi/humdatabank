/** Auto-load matrix rows from variable entity resolution. */
import { debugLog, debugError, debugWarn } from '../debug.js';
import { __configFlag } from './formatting.js';
import { mhFetch } from './api.js';

export const matrixAutoLoadMixin = {


/**
 * Auto-load entities from saved matrix data based on variable configurations
 */
async autoLoadEntities(fieldId) {
    // Mark that we're in a batch operation to prevent scheduled resolutions
    this.batchOperationsInProgress.add(fieldId);

    // Cancel any pending scheduled variable resolution immediately
    // We'll batch resolve all rows at the end
    if (this.variableResolutionDebounceTimers.has(fieldId)) {
        clearTimeout(this.variableResolutionDebounceTimers.get(fieldId));
        this.variableResolutionDebounceTimers.delete(fieldId);
    }
    this.pendingVariableResolution.delete(fieldId);

    const matrix = this.matrices.get(fieldId);
    if (!matrix || !matrix.config) {
        this.batchOperationsInProgress.delete(fieldId);
        debugWarn('matrix-handler', `Cannot auto-load entities: matrix ${fieldId} not found`);
        return;
    }

    // Get variable configurations from matrix columns
    const variableColumns = (matrix.config.columns || []).filter(col => col.is_variable === true);
    if (variableColumns.length === 0) {
        debugLog('matrix-handler', `No variable columns found for auto-load in matrix ${fieldId}`);
        return;
    }

    // Get variable configurations from template variables
    // Wait a bit for template variables to be available (they might load asynchronously)
    let templateVariables = window.templateVariables || {};
    let retries = 0;
    const maxRetries = 5;

    while ((!templateVariables || Object.keys(templateVariables).length === 0) && retries < maxRetries) {
        await new Promise(resolve => setTimeout(resolve, 100));
        templateVariables = window.templateVariables || {};
        retries++;
    }

    if (!templateVariables || Object.keys(templateVariables).length === 0) {
        debugWarn('matrix-handler', 'Template variables not available for auto-load after waiting');
        return;
    }

    // Resolve variable configs for all variable columns (used for entity scope and source)
    const variableConfigsByColumn = [];
    for (const col of variableColumns) {
        const colVariableName = col.variable || col.variable_name;
        if (!colVariableName) continue;
        const colVariableConfig = templateVariables[colVariableName];
        if (!colVariableConfig) continue;
        variableConfigsByColumn.push({ column: col, variableName: colVariableName, variableConfig: colVariableConfig });
    }
    if (variableConfigsByColumn.length === 0) {
        debugWarn('matrix-handler', `No variable configuration found for any column in matrix ${fieldId}`);
        return;
    }

    // Use first variable's entity_scope for lookup mode (reverse vs forward)
    const firstVariableColumn = variableConfigsByColumn[0];
    const variableName = firstVariableColumn.variableName;
    const variableConfig = firstVariableColumn.variableConfig;
    const entityScope = variableConfig.entity_scope;
    const isReverseLookup = entityScope === 'entities_containing';

    // Get assignment_entity_status_id from hidden input.
    // In template-preview mode there is no real AES, so fall back to the
    // entity context exposed by window.metadataContext (set by entry_form.html).
    const assignmentStatusInput = document.querySelector('input[name="assignment_entity_status_id"]');
    let assignmentEntityStatusId = null;
    let previewEntityCtx = null; // { entity_id, entity_type, period_name } when in preview

    if (assignmentStatusInput && assignmentStatusInput.value) {
        assignmentEntityStatusId = parseInt(assignmentStatusInput.value, 10);
        if (isNaN(assignmentEntityStatusId)) {
            debugWarn('matrix-handler', `Invalid assignment_entity_status_id: ${assignmentStatusInput.value}`);
            return;
        }
    } else {
        const meta = window.metadataContext || {};
        const pvEntityId = meta.entity_id ? parseInt(meta.entity_id) : null;
        const pvEntityType = meta.entity_type || null;
        if (pvEntityId && pvEntityType) {
            previewEntityCtx = {
                entity_id: pvEntityId,
                entity_type: pvEntityType,
                period_name: String(meta.assignment_period || '')
            };
            debugLog('matrix-handler', '[AUTO-LOAD] Preview mode — using entity context from metadataContext', previewEntityCtx);
        } else {
            debugWarn('matrix-handler', 'assignment_entity_status_id not found in form (no preview context either)');
            return;
        }
    }

    // Convenience helpers that build the entity-context portion of an API request body.
    // In preview mode we send preview_entity_id / preview_entity_type instead of AES id.
    const _mkAesBody = (extra) => {
        if (assignmentEntityStatusId !== null) {
            return Object.assign({ assignment_entity_status_id: assignmentEntityStatusId }, extra);
        }
        return Object.assign({
            preview_entity_id: previewEntityCtx.entity_id,
            preview_entity_type: previewEntityCtx.entity_type
        }, extra);
    };
    const _mkVarsBody = (extra) => {
        if (assignmentEntityStatusId !== null) {
            return Object.assign({ assignment_entity_status_id: assignmentEntityStatusId }, extra);
        }
        return Object.assign({
            preview_entity_id: previewEntityCtx.entity_id,
            preview_entity_type: previewEntityCtx.entity_type,
            preview_period_name: previewEntityCtx.period_name
        }, extra);
    };

    // Get template ID for variable resolution
    const templateId = this.getTemplateId();
    if (!templateId) {
        debugWarn('matrix-handler', 'template_id not found for variable resolution');
        return;
    }

    debugLog('matrix-handler', `Auto-loading entities for matrix ${fieldId}`, {
        variableColumnCount: variableConfigsByColumn.length,
        entityScope,
        isReverseLookup,
        assignmentEntityStatusId,
        previewEntityCtx,
        templateId
    });

    // Get tick variable column names for filtering (needed for both forward and reverse lookup)
    // Use matrix_column_name from variable config, not the column label
    const tickVariableColumns = variableColumns.filter(col => {
        const colType = typeof col === 'object' ? col.type : 'number';
        return colType === 'tick';
    });
    const tickColumnNames = tickVariableColumns.map(col => {
        // Get the variable name for this column
        const colVariableName = col.variable || col.variable_name;
        if (colVariableName && templateVariables[colVariableName]) {
            const colVariableConfig = templateVariables[colVariableName];
            // Use matrix_column_name from variable config if available, otherwise fall back to column name
            if (colVariableConfig.matrix_column_name) {
                return colVariableConfig.matrix_column_name;
            }
        }
        // Fallback to column name if no variable config or no matrix_column_name
        return typeof col === 'object' ? col.name : col;
    });

    let entities = [];
    let entityType = null;
    // True only when `entities`/`entityType` above were populated from entry-bootstrap.
    // Using this (rather than entities.length === 0) is required so that a bootstrap
    // entry with a genuinely empty entities array is NOT treated as "bootstrap had
    // nothing" and re-fetched via the legacy per-endpoint APIs below.
    let usedBootstrap = false;

    // Prefer entry-bootstrap auto_load (one round-trip with completion-rate) when available.
    try {
        if (window.__entryBootstrapPromise) {
            await window.__entryBootstrapPromise;
        }
        const bootPayload = window.__entryBootstrap
            && window.__entryBootstrap.auto_load
            && window.__entryBootstrap.auto_load[String(fieldId)];
        if (bootPayload && Array.isArray(bootPayload.entities)) {
            entities = bootPayload.entities;
            entityType = bootPayload.entity_type || null;
            usedBootstrap = true;
            debugLog('matrix-handler', `[AUTO-LOAD] Using entry-bootstrap entities for field ${fieldId}`, {
                count: entities.length,
                entityType,
            });
        }
    } catch (_) { /* fall through to per-endpoint path */ }

    try {
        if (!usedBootstrap && isReverseLookup) {
            // For reverse lookup (entities_containing), use variable resolution once and collect entities from ALL variable columns
            debugLog('matrix-handler', '[AUTO-LOAD] Using reverse lookup via variable resolution (all variable columns)');

            const response = await mhFetch('/api/v1/variables/resolve', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(_mkVarsBody({ template_id: templateId }))
            });

            if (!response.ok) {
                const errorText = await response.text();
                debugError('matrix-handler', `[AUTO-LOAD] Variable resolution failed: ${response.status}`, {
                    status: response.status,
                    errorText
                });
                return;
            }

            const data = await response.json();
            const resolvedVariables = data.variables || {};
            const entityMapById = new Map(); // entity_id -> { entity_id, entity_type } for deduplication

            for (const { variableName: colVarName } of variableConfigsByColumn) {
                const variableValue = resolvedVariables[colVarName];
                debugLog('matrix-handler', `[AUTO-LOAD] Variable ${colVarName} resolved to:`, variableValue);

                if (!variableValue) {
                    debugLog('matrix-handler', `[AUTO-LOAD] Variable ${colVarName} not found in resolved variables, skipping`);
                    continue;
                }

                try {
                    const parsed = typeof variableValue === 'string' ? JSON.parse(variableValue) : variableValue;
                    if (parsed && parsed.entities && Array.isArray(parsed.entities)) {
                        if (parsed.entity_type && !entityType) entityType = parsed.entity_type;
                        for (const ent of parsed.entities) {
                            const eid = ent.entity_id != null ? ent.entity_id : ent.id;
                            const etype = ent.entity_type || parsed.entity_type || entityType;
                            if (eid != null && etype) {
                                entityMapById.set(String(eid), { entity_id: eid, entity_type: etype });
                            }
                        }
                        debugLog('matrix-handler', `[AUTO-LOAD] Parsed ${parsed.entities.length} entities from variable ${colVarName}`);
                    } else {
                        debugLog('matrix-handler', `[AUTO-LOAD] Variable ${colVarName} value is not in auto_load_format, skipping`);
                    }
                } catch (parseError) {
                    debugWarn('matrix-handler', `[AUTO-LOAD] Failed to parse variable ${colVarName} as JSON:`, parseError);
                }
            }

            entities = Array.from(entityMapById.values());
            debugLog('matrix-handler', `[AUTO-LOAD] Merged ${entities.length} unique entities from ${variableConfigsByColumn.length} variable column(s)`);
        } else if (!usedBootstrap) {
            // For forward lookup (same, any, specific), collect all sub-requests and
            // send a single batch call instead of one call per variable column.
            // This reduces N HTTP round-trips to 1, cutting thread-slot consumption
            // on the server from N to 1 and eliminating N-1 network waits on the client.
            const entityMapById = new Map();
            const requireTickValue1 = tickColumnNames.length > 0;

            // Build sub-requests for columns that have complete configs.
            const subRequests = [];
            const subRequestColumnNames = [];
            for (const { variableName: colVarName, variableConfig: colVarConfig } of variableConfigsByColumn) {
                const sourceTemplateId = colVarConfig.source_template_id;
                const sourceAssignmentPeriod = colVarConfig.source_assignment_period;
                const sourceFormItemId = colVarConfig.source_form_item_id;

                if (!sourceTemplateId || !sourceAssignmentPeriod || !sourceFormItemId) {
                    debugLog('matrix-handler', `[AUTO-LOAD] Incomplete variable configuration for ${colVarName}, skipping`);
                    continue;
                }
                subRequests.push(_mkAesBody({
                    source_template_id: sourceTemplateId,
                    source_assignment_period: sourceAssignmentPeriod,
                    source_form_item_id: sourceFormItemId,
                    require_tick_value_1: requireTickValue1,
                    tick_column_names: tickColumnNames
                }));
                subRequestColumnNames.push(colVarName);
            }

            if (subRequests.length > 0) {
                const batchResponse = await mhFetch('/api/v1/matrix/auto-load-entities/batch', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCsrfToken()
                    },
                    body: JSON.stringify({ requests: subRequests })
                });

                if (!batchResponse.ok) {
                    debugWarn('matrix-handler', `[AUTO-LOAD] Batch request failed: ${batchResponse.status}`);
                } else {
                    const batchData = await batchResponse.json();
                    const results = batchData.results || [];
                    for (let i = 0; i < results.length; i++) {
                        const colVarName = subRequestColumnNames[i] || `col_${i}`;
                        const result = results[i];
                        const colEntities = result.entities || [];
                        if (result.entity_type && !entityType) entityType = result.entity_type;
                        for (const ent of colEntities) {
                            const eid = ent.entity_id != null ? ent.entity_id : ent.id;
                            const etype = ent.entity_type || result.entity_type || entityType;
                            if (eid != null && etype) {
                                entityMapById.set(String(eid), { entity_id: eid, entity_type: etype });
                            }
                        }
                        debugLog('matrix-handler', `[AUTO-LOAD] Got ${colEntities.length} entities from variable ${colVarName}`);
                    }
                }
            }

            entities = Array.from(entityMapById.values());
            debugLog('matrix-handler', `[AUTO-LOAD] Merged ${entities.length} unique entities from ${subRequests.length} sub-request(s) via batch (forward lookup)`);
        }

        if (entities.length === 0) {
            return;
        }

        // Filter entities: only include those with at least one tick variable column = 1
        // Skip when entities came from entry-bootstrap (already filtered server-side for forward
        // and reverse+tick — see _entry_bootstrap_matrix_candidates in forms_api.py). `usedBootstrap` reflects
        // whether `entities` currently holds bootstrap data specifically, not just whether a
        // bootstrap entry existed, so a legacy-fetch fallback is always re-filtered here.

        // For forward lookup, backend already filters entities by tick columns
        // For reverse lookup, we need to filter in the frontend
        if (!usedBootstrap && tickVariableColumns.length > 0 && isReverseLookup) {
            debugLog('matrix-handler', `[AUTO-LOAD] Filtering entities by tick columns (reverse lookup): ${tickVariableColumns.length} tick variable columns found`);

            // One batched resolve for all candidate entities (was N sequential POSTs).
            const originalCount = entities.length;
            const rowEntityIds = entities
                .map(ent => ent.entity_id)
                .filter(id => id != null);

            let resultsByEntityId = {};
            try {
                const resolveResponse = await mhFetch('/api/v1/variables/resolve', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(_mkVarsBody({
                        template_id: templateId,
                        row_entity_ids: rowEntityIds
                    }))
                });

                if (resolveResponse.ok) {
                    const resolveData = await resolveResponse.json();
                    resultsByEntityId = resolveData.results || {};
                } else {
                    debugWarn('matrix-handler', `[AUTO-LOAD] Batch tick resolve failed: ${resolveResponse.status}`);
                }
            } catch (error) {
                debugError('matrix-handler', '[AUTO-LOAD] Error batch-checking tick status for entities:', error);
            }

            const filteredEntities = [];
            for (const entity of entities) {
                const resolvedVariables = resultsByEntityId[String(entity.entity_id)]
                    || resultsByEntityId[entity.entity_id]
                    || {};
                const hasTickedBox = variableConfigsByColumn.some(({ variableName: vn }) => {
                    const v = resolvedVariables[vn];
                    return v === 1 || v === '1' || v === true;
                });
                if (hasTickedBox) {
                    filteredEntities.push(entity);
                } else {
                    debugLog('matrix-handler', `[AUTO-LOAD] Filtered out entity ${entity.entity_id} - no ticked boxes`);
                }
            }

            entities = filteredEntities;
            debugLog('matrix-handler', `[AUTO-LOAD] Filtered entities: ${entities.length} entities have at least one ticked box (from ${originalCount} total, 1 batch resolve)`);
        } else if (tickVariableColumns.length > 0 && !isReverseLookup) {
            debugLog('matrix-handler', `[AUTO-LOAD] Forward lookup - backend will filter entities by tick columns`);
        } else {
            debugLog('matrix-handler', `[AUTO-LOAD] No tick variable columns found, skipping tick filter`);
        }

        if (entities.length === 0) {
            debugLog('matrix-handler', '[AUTO-LOAD] No entities found after filtering by tick columns');
            return;
        }

        debugLog('matrix-handler', `Found ${entities.length} entities to auto-load`, { entities, entityType });

        // Auto-populate matrix rows with entities
        const lookupListId = matrix.config.lookup_list_id;
        const displayColumn = matrix.config.list_display_column || 'name';
        const filters = matrix.config.list_filters || [];
        const autoLoadEnabled = __configFlag(matrix.config.auto_load_entities, false);
        const highlightManualRows = __configFlag(matrix.config.highlight_manual_rows, autoLoadEnabled);

        if (!lookupListId) {
            debugWarn('matrix-handler', 'No lookup_list_id found in matrix config for auto-load');
            return;
        }

        // Verify entity types match (entities should all have the same entity_type)
        // The lookup_list_id should correspond to this entity_type (e.g., country_map for "country")
        const uniqueEntityTypes = [...new Set(entities.map(e => e.entity_type))];
        if (uniqueEntityTypes.length > 1) {
            debugWarn('matrix-handler', `[AUTO-LOAD] Multiple entity types found: ${uniqueEntityTypes.join(', ')}. All entities should have the same type.`);
        }
        debugLog('matrix-handler', `[AUTO-LOAD] Entity type: ${entityType || uniqueEntityTypes[0] || 'unknown'}. Lookup list ID: ${lookupListId}. The lookup list should contain entities of this type.`);

        // Fetch entity names from lookup list
        // The lookup list should match the entity_type (e.g., country_map for "country", national_society list for "national_society")
        // Normalize entity IDs to strings for consistent matching
        const entityIdSet = new Set(entities.map(e => String(e.entity_id)));
        const entityDataMap = new Map();

        debugLog('matrix-handler', '[AUTO-LOAD] Looking up entity names', {
            entityCount: entities.length,
            entityIds: Array.from(entityIdSet),
            entityTypes: uniqueEntityTypes,
            lookupListId,
            displayColumn,
            filters,
            note: `Lookup list ${lookupListId} should contain entities of type: ${entityType || uniqueEntityTypes[0] || 'unknown'}`
        });

        try {
            // Call search endpoint to get entity data with names
            // Request up to 200 options to reduce chance of missing entities
            const response = await mhFetch('/forms/matrix/search-rows', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCsrfToken()
                },
                body: JSON.stringify({
                    lookup_list_id: lookupListId,
                    display_column: displayColumn,
                    filters: filters,
                    search_term: '', // Empty search to get all
                    existing_rows: [],
                    limit: 200 // Request up to 200 options
                })
            });

            if (response.ok) {
                const data = await response.json();
                debugLog('matrix-handler', '[AUTO-LOAD] Lookup API response', {
                    success: data.success,
                    optionCount: data.options ? data.options.length : 0,
                    hasOptions: !!data.options
                });

                if (data.success && data.options) {
                    // Track which entity IDs are found in the options
                    const foundEntityIds = [];
                    const notFoundEntityIds = [];

                    // Map entity IDs to their data
                    for (const option of data.options) {
                        const entityId = option.id || option.data?.id || option.data?._id;
                        // Normalize to string for consistent matching
                        const normalizedEntityId = entityId ? String(entityId) : null;

                        if (normalizedEntityId && entityIdSet.has(normalizedEntityId)) {
                            foundEntityIds.push(normalizedEntityId);
                            entityDataMap.set(normalizedEntityId, {
                                id: entityId,
                                _id: entityId,
                                ...option.data,
                                name: option.value // Use the display value as name
                            });
                        }
                    }

                    // Find which entity IDs were not found
                    entityIdSet.forEach(id => {
                        if (!entityDataMap.has(id)) {
                            notFoundEntityIds.push(id);
                        }
                    });

                    debugLog('matrix-handler', '[AUTO-LOAD] Entity matching results', {
                        foundCount: foundEntityIds.length,
                        foundIds: foundEntityIds,
                        notFoundCount: notFoundEntityIds.length,
                        notFoundIds: notFoundEntityIds,
                        totalOptions: data.options.length,
                        sampleOptions: data.options.slice(0, 5).map(opt => ({
                            id: opt.id,
                            data_id: opt.data?.id,
                            data__id: opt.data?._id,
                            value: opt.value
                        }))
                    });

                    // Special logging for entity 192
                    if (notFoundEntityIds.includes('192')) {
                        debugLog('matrix-handler', '[AUTO-LOAD] Entity 192 not found - checking all options', {
                            lookingFor: '192',
                            entityIdSetHas192: entityIdSet.has('192'),
                            totalOptions: data.options.length,
                            optionsWith192: data.options.filter(opt => {
                                const optId = String(opt.id || opt.data?.id || opt.data?._id || '');
                                return optId === '192' || optId.includes('192');
                            }).map(opt => ({
                                id: opt.id,
                                data_id: opt.data?.id,
                                data__id: opt.data?._id,
                                value: opt.value,
                                fullOption: opt
                            }))
                        });
                    }

                    // Fetch missing entities individually (they might be beyond pagination limit)
                    if (notFoundEntityIds.length > 0) {
                        debugLog('matrix-handler', '[AUTO-LOAD] Fetching missing entities individually', {
                            missingCount: notFoundEntityIds.length,
                            missingIds: notFoundEntityIds
                        });

                        // Try to fetch each missing entity by filtering by ID
                        for (const missingId of notFoundEntityIds) {
                            debugLog('matrix-handler', `[AUTO-LOAD] Attempting to fetch missing entity ${missingId}`, {
                                missingId,
                                lookupListId,
                                displayColumn
                            });

                            try {
                                // Try filtering by ID - backend expects 'column' not 'field'
                                const idFilter = Array.isArray(filters) ? [...filters] : [];
                                // Add ID filter - backend expects column name in row_data
                                // For system lists, row_data has '_id' and 'id' keys
                                idFilter.push({
                                    column: '_id',  // Use 'column' not 'field'
                                    operator: 'equals',
                                    value: String(missingId)  // Backoffice does string comparison with .lower()
                                });

                                debugLog('matrix-handler', `[AUTO-LOAD] Fetching entity ${missingId} with filter:`, {
                                    filter: idFilter,
                                    requestBody: {
                                        lookup_list_id: lookupListId,
                                        display_column: displayColumn,
                                        filters: idFilter,
                                        search_term: '',
                                        existing_rows: []
                                    }
                                });

                                const searchResponse = await mhFetch('/forms/matrix/search-rows', {
                                    method: 'POST',
                                    headers: {
                                        'Content-Type': 'application/json',
                                        'X-CSRFToken': this.getCsrfToken()
                                    },
                                    body: JSON.stringify({
                                        lookup_list_id: lookupListId,
                                        display_column: displayColumn,
                                        filters: idFilter,
                                        search_term: '', // Empty search, rely on filter
                                        existing_rows: [],
                                        limit: 10  // Small limit since we're filtering by ID
                                    })
                                });

                                debugLog('matrix-handler', `[AUTO-LOAD] Fallback API response for ${missingId}:`, {
                                    status: searchResponse.status,
                                    ok: searchResponse.ok
                                });

                                if (searchResponse.ok) {
                                    const searchData = await searchResponse.json();
                                    debugLog('matrix-handler', `[AUTO-LOAD] Fallback API data for ${missingId}:`, {
                                        success: searchData.success,
                                        optionCount: searchData.options ? searchData.options.length : 0,
                                        options: searchData.options
                                    });

                                    if (searchData.success && searchData.options) {
                                        // Look for the exact entity ID in the search results
                                        for (const option of searchData.options) {
                                            const entityId = option.id || option.data?.id || option.data?._id;
                                            const normalizedEntityId = entityId ? String(entityId) : null;

                                            debugLog('matrix-handler', `[AUTO-LOAD] Checking option for ${missingId}:`, {
                                                optionId: entityId,
                                                normalizedId: normalizedEntityId,
                                                missingId,
                                                matches: normalizedEntityId === missingId,
                                                optionValue: option.value
                                            });

                                            if (normalizedEntityId === missingId) {
                                                entityDataMap.set(normalizedEntityId, {
                                                    id: entityId,
                                                    _id: entityId,
                                                    ...option.data,
                                                    name: option.value
                                                });
                                                debugLog('matrix-handler', `[AUTO-LOAD] ✓ Found missing entity ${missingId} via ID filter`, {
                                                    entityId: missingId,
                                                    name: option.value,
                                                    rowData: option.data
                                                });
                                                break; // Found it, move to next missing entity
                                            }
                                        }

                                        // If still not found, try alternative filter format with 'id' column
                                        if (!entityDataMap.has(missingId)) {
                                            debugLog('matrix-handler', `[AUTO-LOAD] Entity ${missingId} not found with _id filter, trying 'id' column`);

                                            const altFilter = Array.isArray(filters) ? [...filters] : [];
                                            altFilter.push({
                                                column: 'id',  // Use 'column' not 'field'
                                                operator: 'equals',
                                                value: String(missingId)  // Backoffice does string comparison
                                            });

                                            const altResponse = await mhFetch('/forms/matrix/search-rows', {
                                                method: 'POST',
                                                headers: {
                                                    'Content-Type': 'application/json',
                                                    'X-CSRFToken': this.getCsrfToken()
                                                },
                                                body: JSON.stringify({
                                                    lookup_list_id: lookupListId,
                                                    display_column: displayColumn,
                                                    filters: altFilter,
                                                    search_term: '',
                                                    existing_rows: [],
                                                    limit: 10
                                                })
                                            });

                                            if (altResponse.ok) {
                                                const altData = await altResponse.json();
                                                debugLog('matrix-handler', `[AUTO-LOAD] Alternative filter response for ${missingId}:`, {
                                                    success: altData.success,
                                                    optionCount: altData.options ? altData.options.length : 0,
                                                    options: altData.options
                                                });

                                                if (altData.success && altData.options) {
                                                    for (const option of altData.options) {
                                                        const entityId = option.id || option.data?.id || option.data?._id;
                                                        const normalizedEntityId = entityId ? String(entityId) : null;

                                                        if (normalizedEntityId === missingId) {
                                                            entityDataMap.set(normalizedEntityId, {
                                                                id: entityId,
                                                                _id: entityId,
                                                                ...option.data,
                                                                name: option.value
                                                            });
                                                            debugLog('matrix-handler', `[AUTO-LOAD] ✓ Found missing entity ${missingId} via alternative ID filter`, {
                                                                entityId: missingId,
                                                                name: option.value
                                                            });
                                                            break;
                                                        }
                                                    }
                                                }
                                            } else {
                                                debugWarn('matrix-handler', `[AUTO-LOAD] Alternative filter request failed for ${missingId}:`, {
                                                    status: altResponse.status,
                                                    statusText: altResponse.statusText
                                                });
                                            }
                                        }
                                    } else {
                                        debugWarn('matrix-handler', `[AUTO-LOAD] Fallback API did not return success or options for ${missingId}`, {
                                            success: searchData.success,
                                            hasOptions: !!searchData.options,
                                            responseData: searchData
                                        });
                                    }
                                } else {
                                    debugWarn('matrix-handler', `[AUTO-LOAD] Fallback API request failed for ${missingId}:`, {
                                        status: searchResponse.status,
                                        statusText: searchResponse.statusText
                                    });
                                }
                            } catch (error) {
                                debugError('matrix-handler', `[AUTO-LOAD] Error fetching entity ${missingId}:`, error);
                            }
                        }
                    }
                } else {
                    debugWarn('matrix-handler', '[AUTO-LOAD] Lookup API did not return success or options', {
                        success: data.success,
                        hasOptions: !!data.options,
                        responseData: data
                    });
                }
            } else {
                debugError('matrix-handler', '[AUTO-LOAD] Lookup API request failed', {
                    status: response.status,
                    statusText: response.statusText
                });
            }
        } catch (error) {
            debugError('matrix-handler', 'Error fetching entity names for auto-load:', error);
        }

        // Track which entity IDs were auto-loaded
        const autoLoadedEntityIds = new Set();

        // Add each entity as a row
        for (const entity of entities) {
            // Normalize entity ID to string for consistent lookup
            const normalizedEntityId = String(entity.entity_id);
            autoLoadedEntityIds.add(normalizedEntityId);

            // Check if row already exists (from restoration)
            const existingRow = matrix.container.querySelector(`tr[data-row-id="${normalizedEntityId}"]`);
            if (existingRow) {
                // Mark existing row as auto-loaded (it was restored but is actually an auto-loaded entity)
                existingRow.setAttribute('data-is-auto-loaded', 'true');
                const headerCell = existingRow.querySelector('td[role="rowheader"]');
                if (headerCell) {
                    headerCell.style.backgroundColor = '';
                    headerCell.classList.remove('matrix-manual-row-header');
                    // Remove remove button if it exists (auto-loaded rows shouldn't have remove button)
                    const removeButton = headerCell.querySelector('.remove-matrix-row-btn');
                    if (removeButton) {
                        removeButton.remove();
                    }
                }
                debugLog('matrix-handler', `Marked existing row ${normalizedEntityId} as auto-loaded`);
                continue;
            }

            // Get entity data from map, or create minimal data
            let rowData = entityDataMap.get(normalizedEntityId);
            if (!rowData) {
                // Fallback: create minimal row data if not found in lookup list
                debugLog('matrix-handler', '[AUTO-LOAD] Entity not found in map', {
                    entityId: entity.entity_id,
                    normalizedEntityId,
                    mapSize: entityDataMap.size,
                    mapKeys: Array.from(entityDataMap.keys()),
                    entityIdSetHas: entityIdSet.has(normalizedEntityId)
                });
                rowData = {
                    id: entity.entity_id,
                    _id: entity.entity_id,
                    entity_type: entity.entity_type,
                    name: `Entity ${entity.entity_id}`
                };
                debugWarn('matrix-handler', `Entity ${entity.entity_id} not found in lookup list, using fallback name`);
            } else {
                debugLog('matrix-handler', '[AUTO-LOAD] Entity found in map', {
                    entityId: entity.entity_id,
                    normalizedEntityId,
                    rowDataName: rowData.name
                });
            }

            // Use the display name from rowData, or fallback to entity_id
            const rowLabel = rowData[displayColumn] || rowData.name || `Entity ${entity.entity_id}`;
            const rowId = String(entity.entity_id);

            debugLog('matrix-handler', `Auto-adding entity row: ${rowLabel} (ID: ${rowId}, Type: ${entity.entity_type})`);

            // Add row using the existing addDynamicRow method (mark as auto-loaded)
            this.addDynamicRow(fieldId, rowLabel, rowData, rowId, true);
        }

        // Mark any other existing rows that match auto-loaded entities as auto-loaded
        // This handles the case where rows were restored before auto-load ran
        const allDataRows = matrix.container.querySelectorAll('tr.matrix-data-row');
        allDataRows.forEach(row => {
            const rowId = row.getAttribute('data-row-id');
            if (rowId && autoLoadedEntityIds.has(rowId)) {
                row.setAttribute('data-is-auto-loaded', 'true');
                const headerCell = row.querySelector('td[role="rowheader"]');
                if (headerCell) {
                    headerCell.style.backgroundColor = '';
                    headerCell.classList.remove('matrix-manual-row-header');
                    // Remove remove button if it exists (auto-loaded rows shouldn't have remove button)
                    const removeButton = headerCell.querySelector('.remove-matrix-row-btn');
                    if (removeButton) {
                        removeButton.remove();
                    }
                }
            }
        });

        // Recalculate totals after adding rows
        // Note: addDynamicRow already calls calculateMatrixTotals, but we call it again to be safe
        setTimeout(async () => {
            // Cancel any pending scheduled variable resolution (we'll batch resolve all at once)
            if (this.variableResolutionDebounceTimers.has(fieldId)) {
                clearTimeout(this.variableResolutionDebounceTimers.get(fieldId));
                this.variableResolutionDebounceTimers.delete(fieldId);
            }
            this.pendingVariableResolution.delete(fieldId);

            this.calculateMatrixTotals(fieldId);
            // Batch resolve variables for all auto-loaded rows (optimized)
            await this.resolveVariablesForAllRows(fieldId);
            // Sort rows alphabetically after auto-loading
            this.sortMatrixRows(fieldId);
            // Check for and highlight duplicates
            this.applyDuplicateEntityHighlighting(fieldId);
            // Update legend visibility after auto-load
            this.updateLegendVisibility(fieldId);
            this._lockMatrixContainerIfReadOnly(matrix.container);
        }, 100);

    } catch (error) {
        debugError('matrix-handler', 'Error auto-loading entities:', error);
    } finally {
        // Clear batch operation flag
        this.batchOperationsInProgress.delete(fieldId);
    }
}

/**
 * Sort matrix rows alphabetically by row label
 */,
};
