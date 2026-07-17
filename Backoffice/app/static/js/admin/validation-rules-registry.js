/**
 * Validation Rules Registry — rule catalog, thresholds, check types, question templates.
 */
(function () {
    'use strict';

    var config = window.validationRulesConfig || {};
    var t = window.VR_GRID_TRANSLATIONS || {};
    var csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
    var feedbackEl = document.getElementById('vr-feedback');

    var state = {
        catalogApi: null,
        thresholdsApi: null,
        checkTypesApi: null,
        qtApi: null,
        activeTab: 'catalog',
    };

    function el(id) { return document.getElementById(id); }

    function esc(s) {
        if (s == null) return '';
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function showFeedback(message, type) {
        if (!feedbackEl) return;
        feedbackEl.textContent = message;
        feedbackEl.className = 'mb-4 rounded-md px-4 py-3 text-sm border ';
        var classes = type === 'error'
            ? ['bg-red-50', 'border-red-200', 'text-red-800']
            : type === 'success'
                ? ['bg-green-50', 'border-green-200', 'text-green-800']
                : ['bg-blue-50', 'border-blue-200', 'text-blue-800'];
        feedbackEl.classList.add.apply(feedbackEl.classList, classes);
        feedbackEl.classList.remove('hidden');
    }

    function getTemplateId() {
        var v = el('vr-template')?.value;
        return v ? parseInt(v, 10) : null;
    }

    function getRulePack() {
        return el('vr-rule-pack')?.value || '';
    }

    function templateQuery() {
        var tid = getTemplateId();
        return tid ? ('?template_id=' + encodeURIComponent(String(tid))) : '';
    }

    function rulePackQuery() {
        var pack = getRulePack();
        return pack ? ('?rule_pack=' + encodeURIComponent(pack)) : '';
    }

    function fetchJson(url, options) {
        return window.apiFetch(url, options || {});
    }

    function severityBadge(value) {
        if (!value) return '';
        var variant = value === 'error' ? 'danger' : (value === 'warning' ? 'warning' : (value === 'info' ? 'info' : 'neutral'));
        if (window.StatusLabels) {
            return window.StatusLabels.render(value, variant);
        }
        return '<span class="status-label status-label--' + variant + '">' + esc(value) + '</span>';
    }

    function actionsRenderer(kind) {
        return function (params) {
            if (!params.data) return '';
            return (
                '<button type="button" class="text-blue-600 hover:underline text-xs mr-3" data-vr-edit="' + kind + '" data-id="' + esc(params.data.id) + '">' +
                esc(t.edit || 'Edit') +
                '</button>' +
                '<button type="button" class="text-red-600 hover:underline text-xs" data-vr-delete="' + kind + '" data-id="' + esc(params.data.id) + '">' +
                esc(t.delete || 'Delete') +
                '</button>'
            );
        };
    }

    function catalogColumnDefs() {
        return [
            { field: 'code', headerName: t.code || 'Code', width: 180, minWidth: 160, filter: 'agTextColumnFilter' },
            { field: 'label', headerName: t.label || 'Label', flex: 1, minWidth: 180, filter: 'agTextColumnFilter' },
            {
                field: 'severity',
                headerName: t.severity || 'Severity',
                width: 110,
                minWidth: 100,
                filter: 'customSetFilter',
                cellRenderer: function (p) { return severityBadge(p.value); },
            },
            { field: 'category', headerName: t.category || 'Category', width: 130, minWidth: 110, filter: 'customSetFilter' },
            {
                field: 'configurable',
                headerName: t.configurable || 'Configurable',
                width: 120,
                minWidth: 110,
                filter: 'customSetFilter',
                valueFormatter: function (p) { return p.value ? (t.yes || 'Yes') : (t.no || 'No'); },
            },
            { field: 'description', headerName: t.description || 'Description', flex: 1.2, minWidth: 220, filter: 'agTextColumnFilter', wrapText: true, autoHeight: true },
        ];
    }

    function thresholdsColumnDefs() {
        return [
            { field: 'country_name', headerName: t.country || 'Country', flex: 1, minWidth: 160, filter: 'agTextColumnFilter' },
            { field: 'kpi_code', headerName: t.kpiCode || 'KPI code', width: 180, minWidth: 150, filter: 'agTextColumnFilter' },
            {
                field: 'threshold_percent',
                headerName: t.thresholdPercent || 'Threshold %',
                width: 130,
                minWidth: 110,
                filter: 'agNumberColumnFilter',
                valueFormatter: function (p) {
                    if (p.value == null) return '';
                    return String(p.value) + '%';
                },
            },
            {
                field: 'template_id',
                headerName: t.templateId || 'Template ID',
                width: 120,
                minWidth: 100,
                filter: 'agNumberColumnFilter',
                valueFormatter: function (p) { return p.value == null ? '—' : String(p.value); },
            },
            {
                colId: 'actions',
                headerName: t.actions || 'Actions',
                width: 130,
                minWidth: 120,
                sortable: false,
                filter: false,
                cellRenderer: actionsRenderer('threshold'),
            },
        ];
    }

    function checkTypesColumnDefs() {
        return [
            { field: 'kpi_code', headerName: t.kpiCode || 'KPI code', flex: 1, minWidth: 180, filter: 'agTextColumnFilter' },
            { field: 'check_type', headerName: t.checkType || 'Check type', flex: 1.2, minWidth: 220, filter: 'agTextColumnFilter' },
            {
                field: 'template_id',
                headerName: t.templateId || 'Template ID',
                width: 120,
                minWidth: 100,
                filter: 'agNumberColumnFilter',
                valueFormatter: function (p) { return p.value == null ? '—' : String(p.value); },
            },
            {
                colId: 'actions',
                headerName: t.actions || 'Actions',
                width: 130,
                minWidth: 120,
                sortable: false,
                filter: false,
                cellRenderer: actionsRenderer('check-type'),
            },
        ];
    }

    function qtColumnDefs() {
        return [
            { field: 'question_code', headerName: t.questionCode || 'Question code', width: 180, minWidth: 150, filter: 'agTextColumnFilter' },
            { field: 'language', headerName: t.language || 'Language', width: 90, minWidth: 80, filter: 'customSetFilter' },
            { field: 'template_text', headerName: t.templateText || 'Template text', flex: 1.4, minWidth: 240, filter: 'agTextColumnFilter', wrapText: true, autoHeight: true },
            {
                field: 'needs_ending_value',
                headerName: t.needsSuffix || 'Needs suffix',
                width: 110,
                minWidth: 100,
                filter: 'customSetFilter',
                valueFormatter: function (p) { return p.value ? (t.yes || 'Yes') : (t.no || 'No'); },
            },
            { field: 'rule_pack', headerName: t.rulePack || 'Rule pack', width: 140, minWidth: 120, filter: 'agTextColumnFilter' },
            {
                colId: 'actions',
                headerName: t.actions || 'Actions',
                width: 90,
                minWidth: 80,
                sortable: false,
                filter: false,
                cellRenderer: function (params) {
                    if (!params.data) return '';
                    return '<button type="button" class="text-blue-600 hover:underline text-xs" data-vr-edit="qt" data-id="' + esc(params.data.id) + '">' + esc(t.edit || 'Edit') + '</button>';
                },
            },
        ];
    }

    function createGrid(gridId, templateKey, columnDefs, rows, placeholderId, stateKey) {
        if (state[stateKey]) {
            state[stateKey].setGridOption('rowData', rows);
            return;
        }
        var result = AgGridHelper.create(gridId, templateKey, columnDefs, rows, {
            columnVisibilityOptions: { buttonPlaceholderId: placeholderId, enableExport: true },
            sizeColumnsToFitOnInit: false,
            gridOptions: {
                defaultColDef: { suppressSizeToFit: true, wrapHeaderText: true, autoHeaderHeight: true },
                onFirstDataRendered: function (params) { AgGridHelper.enforceColumnMinWidths(params.api); },
            },
        });
        state[stateKey] = result.api;
    }

    function initCatalogGrid(rows) {
        createGrid('validationRulesCatalogGrid', 'admin-validation-rules-catalog', catalogColumnDefs(), rows, 'vr-catalog-col-vis', 'catalogApi');
    }

    function initThresholdsGrid(rows) {
        createGrid('validationThresholdsGrid', 'admin-validation-thresholds', thresholdsColumnDefs(), rows, 'vr-threshold-col-vis', 'thresholdsApi');
    }

    function initCheckTypesGrid(rows) {
        createGrid('validationCheckTypesGrid', 'admin-validation-check-types', checkTypesColumnDefs(), rows, 'vr-check-type-col-vis', 'checkTypesApi');
    }

    function initQtGrid(rows) {
        createGrid('validationQuestionTemplatesGrid', 'admin-validation-question-templates', qtColumnDefs(), rows, 'vr-qt-col-vis', 'qtApi');
    }

    function loadCatalog() {
        var url = (config.catalogUrl || '') + rulePackQuery();
        return fetchJson(url).then(function (data) {
            var rows = data.rules || config.initialCatalog || [];
            if (state.catalogApi) {
                state.catalogApi.setGridOption('rowData', rows);
            } else {
                initCatalogGrid(rows);
            }
        }).catch(function (err) {
            showFeedback(err.message || t.loadFailed, 'error');
            initCatalogGrid(config.initialCatalog || []);
        });
    }

    function loadThresholds() {
        return fetchJson((config.thresholdsUrl || '') + templateQuery()).then(function (data) {
            var rows = data.rows || [];
            if (state.thresholdsApi) {
                state.thresholdsApi.setGridOption('rowData', rows);
            } else {
                initThresholdsGrid(rows);
            }
        }).catch(function (err) {
            showFeedback(err.message || t.loadFailed, 'error');
            initThresholdsGrid([]);
        });
    }

    function loadCheckTypes() {
        return fetchJson((config.checkTypesUrl || '') + templateQuery()).then(function (data) {
            var rows = data.rows || [];
            if (state.checkTypesApi) {
                state.checkTypesApi.setGridOption('rowData', rows);
            } else {
                initCheckTypesGrid(rows);
            }
        }).catch(function (err) {
            showFeedback(err.message || t.loadFailed, 'error');
            initCheckTypesGrid([]);
        });
    }

    function loadQuestionTemplates() {
        return fetchJson((config.questionTemplatesUrl || '') + rulePackQuery()).then(function (data) {
            var rows = data.rows || [];
            if (state.qtApi) {
                state.qtApi.setGridOption('rowData', rows);
            } else {
                initQtGrid(rows);
            }
        }).catch(function (err) {
            showFeedback(err.message || t.loadFailed, 'error');
            initQtGrid([]);
        });
    }

    function reloadActiveTab() {
        if (state.activeTab === 'catalog') return loadCatalog();
        if (state.activeTab === 'thresholds') return loadThresholds();
        if (state.activeTab === 'check-types') return loadCheckTypes();
        if (state.activeTab === 'question-templates') return loadQuestionTemplates();
        return Promise.resolve();
    }

    function switchTab(tab) {
        state.activeTab = tab;
        document.querySelectorAll('#vr-tabs [role="tab"]').forEach(function (btn) {
            var active = btn.getAttribute('data-tab') === tab;
            if (window.AdminUnderlineTabs) window.AdminUnderlineTabs.setStripButtonActive(btn, active);
            btn.setAttribute('aria-selected', active ? 'true' : 'false');
        });
        ['catalog', 'thresholds', 'check-types', 'question-templates'].forEach(function (name) {
            var panel = el('panel-' + name);
            if (panel) panel.classList.toggle('hidden', name !== tab);
        });
        reloadActiveTab();
    }

    function openModal(id) { el(id)?.classList.remove('hidden'); }
    function closeModal(id) { el(id)?.classList.add('hidden'); }

    function findRow(api, rowId) {
        var found = null;
        if (!api) return null;
        api.forEachNode(function (node) {
            if (node.data && String(node.data.id) === String(rowId)) found = node.data;
        });
        return found;
    }

    function openThresholdModal(row) {
        el('vr-threshold-id').value = row ? row.id : '';
        el('vr-threshold-country').value = row ? String(row.country_id) : '';
        el('vr-threshold-kpi').value = row ? row.kpi_code : (el('vr-threshold-kpi').options[0]?.value || '');
        el('vr-threshold-percent').value = row && row.threshold_percent != null ? row.threshold_percent : '';
        el('vr-threshold-modal-title').textContent = row ? (t.edit || 'Edit') : (t.add || 'Add threshold');
        openModal('vr-threshold-modal');
    }

    function openCheckTypeModal(row) {
        el('vr-check-type-id').value = row ? row.id : '';
        el('vr-check-type-kpi').value = row ? row.kpi_code : (el('vr-check-type-kpi').options[0]?.value || '');
        el('vr-check-type-value').value = row ? row.check_type : (el('vr-check-type-value').options[0]?.value || '');
        el('vr-check-type-modal-title').textContent = row ? (t.edit || 'Edit') : (t.add || 'Add check type');
        openModal('vr-check-type-modal');
    }

    function openQtModal(row) {
        if (!row) return;
        el('vr-qt-id').value = row.id;
        el('vr-qt-text').value = row.template_text || '';
        el('vr-qt-needs-suffix').checked = !!row.needs_ending_value;
        el('vr-qt-meta').textContent = (row.question_code || '') + ' · ' + (row.language || '') + ' · ' + (row.rule_pack || '');
        openModal('vr-qt-modal');
    }

    function saveThreshold() {
        var percent = parseFloat(el('vr-threshold-percent').value, 10);
        if (Number.isNaN(percent) || percent < 0) {
            showFeedback(t.saveFailed || 'Save failed', 'error');
            return;
        }
        var payload = {
            id: el('vr-threshold-id').value || null,
            country_id: parseInt(el('vr-threshold-country').value, 10),
            kpi_code: el('vr-threshold-kpi').value,
            threshold_fraction: percent / 100,
            template_id: getTemplateId(),
        };
        fetchJson(config.thresholdsUpsertUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
            body: JSON.stringify(payload),
        }).then(function () {
            closeModal('vr-threshold-modal');
            showFeedback(t.saved || 'Saved', 'success');
            return loadThresholds();
        }).catch(function (err) {
            showFeedback(err.message || t.saveFailed, 'error');
        });
    }

    function saveCheckType() {
        var payload = {
            id: el('vr-check-type-id').value || null,
            kpi_code: el('vr-check-type-kpi').value,
            check_type: el('vr-check-type-value').value,
            template_id: getTemplateId(),
        };
        fetchJson(config.checkTypesUpsertUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
            body: JSON.stringify(payload),
        }).then(function () {
            closeModal('vr-check-type-modal');
            showFeedback(t.saved || 'Saved', 'success');
            return loadCheckTypes();
        }).catch(function (err) {
            showFeedback(err.message || t.saveFailed, 'error');
        });
    }

    function saveQt() {
        var rowId = el('vr-qt-id').value;
        fetchJson((config.questionTemplateUpdateBase || '') + rowId, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
            body: JSON.stringify({
                template_text: el('vr-qt-text').value,
                needs_ending_value: el('vr-qt-needs-suffix').checked,
            }),
        }).then(function () {
            closeModal('vr-qt-modal');
            showFeedback(t.saved || 'Saved', 'success');
            return loadQuestionTemplates();
        }).catch(function (err) {
            showFeedback(err.message || t.saveFailed, 'error');
        });
    }

    function deleteRow(kind, rowId) {
        if (!window.confirm(t.confirmDelete || 'Delete this row?')) return;
        var base = kind === 'threshold' ? config.thresholdsDeleteBase : config.checkTypesDeleteBase;
        var url = (base || '') + rowId;
        fetchJson(url, {
            method: 'DELETE',
            headers: { 'X-CSRFToken': csrf },
        }).then(function () {
            showFeedback(t.deleted || 'Deleted', 'success');
            return kind === 'threshold' ? loadThresholds() : loadCheckTypes();
        }).catch(function (err) {
            showFeedback(err.message || t.saveFailed, 'error');
        });
    }

    function bindGridActions(containerId, apiGetter) {
        var container = el(containerId);
        if (!container) return;
        container.addEventListener('click', function (evt) {
            var editBtn = evt.target.closest('[data-vr-edit]');
            var deleteBtn = evt.target.closest('[data-vr-delete]');
            if (editBtn) {
                var kind = editBtn.getAttribute('data-vr-edit');
                var row = findRow(apiGetter(), editBtn.getAttribute('data-id'));
                if (kind === 'threshold') openThresholdModal(row);
                else if (kind === 'check-type') openCheckTypeModal(row);
                else if (kind === 'qt') openQtModal(row);
            }
            if (deleteBtn) {
                deleteRow(deleteBtn.getAttribute('data-vr-delete'), deleteBtn.getAttribute('data-id'));
            }
        });
    }

    function init() {
        document.querySelectorAll('#vr-tabs [role="tab"]').forEach(function (btn) {
            btn.addEventListener('click', function () { switchTab(btn.getAttribute('data-tab')); });
        });

        el('vr-template')?.addEventListener('change', function () {
            if (state.activeTab === 'thresholds') loadThresholds();
            if (state.activeTab === 'check-types') loadCheckTypes();
        });
        el('vr-rule-pack')?.addEventListener('change', function () {
            if (state.activeTab === 'catalog') loadCatalog();
            if (state.activeTab === 'question-templates') loadQuestionTemplates();
        });

        el('vr-threshold-add')?.addEventListener('click', function () { openThresholdModal(null); });
        el('vr-check-type-add')?.addEventListener('click', function () { openCheckTypeModal(null); });
        el('vr-threshold-save')?.addEventListener('click', saveThreshold);
        el('vr-check-type-save')?.addEventListener('click', saveCheckType);
        el('vr-qt-save')?.addEventListener('click', saveQt);

        document.querySelectorAll('[data-vr-close]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var kind = btn.getAttribute('data-vr-close');
                if (kind === 'threshold') closeModal('vr-threshold-modal');
                else if (kind === 'check-type') closeModal('vr-check-type-modal');
                else if (kind === 'qt') closeModal('vr-qt-modal');
            });
        });

        bindGridActions('validationThresholdsGrid-container', function () { return state.thresholdsApi; });
        bindGridActions('validationCheckTypesGrid-container', function () { return state.checkTypesApi; });
        bindGridActions('validationQuestionTemplatesGrid-container', function () { return state.qtApi; });

        loadCatalog();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
}());
