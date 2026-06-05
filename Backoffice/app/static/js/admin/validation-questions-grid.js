/**
 * Validation Questions — AG Grid (all questions + country summary tab).
 */
(function () {
    'use strict';

    var config = window.validationQuestionsGridConfig || {};
    var t = window.VQ_GRID_TRANSLATIONS || {};
    var csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
    var feedbackEl = document.getElementById('vq-feedback');
    var gridApi = null;
    var gridHelper = null;
    var summaryApi = null;

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
        if (type === 'error') {
            feedbackEl.classList.add('bg-red-50', 'border-red-200', 'text-red-800');
        } else if (type === 'success') {
            feedbackEl.classList.add('bg-green-50', 'border-green-200', 'text-green-800');
        } else {
            feedbackEl.classList.add('bg-blue-50', 'border-blue-200', 'text-blue-800');
        }
        feedbackEl.classList.remove('hidden');
    }

    function badge(text, cls) {
        return '<span class="inline-flex px-2 py-0.5 rounded-full text-xs font-medium ' + cls + '">' + esc(text) + '</span>';
    }

    function severityRenderer(params) {
        var map = { error: 'bg-red-100 text-red-800', warning: 'bg-amber-100 text-amber-800', info: 'bg-blue-100 text-blue-800' };
        var sev = params.value || '';
        return badge(sev, map[sev] || 'bg-gray-100 text-gray-800');
    }

    function statusRenderer(params) {
        var map = {
            open: 'bg-orange-100 text-orange-800',
            answered: 'bg-green-100 text-green-800',
            waived: 'bg-gray-100 text-gray-700',
            resolved: 'bg-slate-100 text-slate-700',
        };
        var st = params.value || '';
        return badge(st, map[st] || 'bg-gray-100 text-gray-800');
    }

    function buildColumnDefs() {
        return [
            { field: 'entity_name', headerName: t.country || 'Country', flex: 1, minWidth: 140, filter: 'customSetFilter' },
            { field: 'template_name', headerName: t.template || 'Template', flex: 1, minWidth: 120, filter: 'customSetFilter' },
            { field: 'period_name', headerName: t.period || 'Period', width: 110, filter: 'customSetFilter' },
            { field: 'rule_code', headerName: t.rule || 'Rule', width: 150, filter: 'agTextColumnFilter' },
            { field: 'severity', headerName: t.severity || 'Severity', width: 110, filter: 'customSetFilter', cellRenderer: severityRenderer },
            { field: 'status', headerName: t.status || 'Status', width: 110, filter: 'customSetFilter', cellRenderer: statusRenderer },
            {
                field: 'question_text',
                headerName: t.question || 'Question',
                flex: 1.4,
                minWidth: 200,
                filter: 'agTextColumnFilter',
                wrapText: true,
                autoHeight: true,
            },
            {
                field: 'answer_text',
                headerName: t.answer || 'Answer',
                flex: 1.2,
                minWidth: 160,
                filter: 'agTextColumnFilter',
                wrapText: true,
                autoHeight: true,
            },
            { field: 'sent_at', headerName: t.sent || 'Sent', width: 110, valueFormatter: function (p) { return p.value ? String(p.value).slice(0, 10) : '—'; } },
            { field: 'source', headerName: t.source || 'Source', width: 90, filter: 'customSetFilter' },
            {
                colId: 'actions',
                headerName: t.actions || 'Actions',
                width: 130,
                pinned: 'right',
                sortable: false,
                filter: false,
                cellRenderer: function (params) {
                    var d = params.data || {};
                    if (!d.id) return '';
                    if (d.status === 'open') {
                        return '<button type="button" class="text-sm text-ifrc-navy hover:underline vq-waive" data-id="' + d.id + '">' + esc(t.waive || 'Waive') + '</button>';
                    }
                    if (d.status === 'waived' || d.status === 'answered') {
                        return '<button type="button" class="text-sm text-ifrc-navy hover:underline vq-reopen" data-id="' + d.id + '">' + esc(t.reopen || 'Reopen') + '</button>';
                    }
                    return '';
                },
            },
        ];
    }

    function buildSummaryColumnDefs() {
        return [
            { field: 'country_name', headerName: t.country || 'Country', flex: 1, minWidth: 180, filter: 'customSetFilter' },
            { field: 'period_name', headerName: t.period || 'Period', width: 120, filter: 'customSetFilter' },
            { field: 'open_questions', headerName: t.openQuestions || 'Open questions', width: 130, filter: 'agNumberColumnFilter' },
            { field: 'answered_questions', headerName: t.answered || 'Answered', width: 110, filter: 'agNumberColumnFilter' },
            { field: 'waived_questions', headerName: t.waived || 'Waived', width: 100, filter: 'agNumberColumnFilter' },
            { field: 'resolved_questions', headerName: t.resolved || 'Resolved', width: 110, filter: 'agNumberColumnFilter' },
            { field: 'total_questions', headerName: t.totalQuestions || 'Total questions', width: 130, filter: 'agNumberColumnFilter' },
        ];
    }

    function activateTab(tabId) {
        var tabs = document.querySelectorAll('#vq-tabs [role="tab"]');
        var A = window.AdminUnderlineTabs;
        tabs.forEach(function (btn) {
            var active = btn.getAttribute('data-tab') === tabId;
            if (A) A.setStripButtonActive(btn, active);
            btn.setAttribute('aria-selected', active ? 'true' : 'false');
        });
        document.querySelectorAll('.vq-panel').forEach(function (panel) {
            panel.classList.toggle('hidden', panel.id !== 'panel-' + tabId);
        });
    }

    async function loadRows() {
        try {
            var resp = await fetch(config.listUrl, { headers: { Accept: 'application/json' }, credentials: 'same-origin' });
            var data = await resp.json();
            if (!resp.ok) throw new Error(data.error || t.loadFailed);
            var rows = data.rows || [];
            if (gridHelper) {
                gridHelper.setRowData(rows);
                gridHelper.refresh();
            }
            return rows;
        } catch (err) {
            console.error(err);
            showFeedback(t.loadFailed || 'Failed to load', 'error');
            return [];
        }
    }

    async function loadSummaryPeriods() {
        var templateId = document.getElementById('vqs-template')?.value;
        var periodEl = document.getElementById('vqs-period');
        if (!periodEl) return;
        if (!templateId) {
            periodEl.innerHTML = '<option value="">' + esc('Select template first') + '</option>';
            periodEl.disabled = true;
            return;
        }
        periodEl.disabled = true;
        try {
            var resp = await fetch(config.periodsUrl + '?template_id=' + encodeURIComponent(templateId), {
                headers: { Accept: 'application/json' },
                credentials: 'same-origin',
            });
            var data = await resp.json();
            var periods = data.periods || [];
            periodEl.innerHTML = '<option value="">' + esc('Choose period') + '</option>' +
                periods.map(function (p) { return '<option value="' + esc(p) + '">' + esc(p) + '</option>'; }).join('');
            periodEl.disabled = !periods.length;
        } catch (err) {
            console.error(err);
        }
    }

    async function loadCountrySummary() {
        var templateId = document.getElementById('vqs-template')?.value;
        var period = document.getElementById('vqs-period')?.value;
        if (!templateId || !period) {
            showFeedback(t.selectTemplatePeriod || 'Select template and period.', 'error');
            return;
        }
        try {
            var url = config.countriesUrl + '?template_id=' + encodeURIComponent(templateId) + '&period=' + encodeURIComponent(period);
            var resp = await fetch(url, { headers: { Accept: 'application/json' }, credentials: 'same-origin' });
            var data = await resp.json();
            if (!resp.ok) throw new Error(data.error || t.summaryFailed);
            var rows = data.countries || [];
            if (summaryApi) {
                summaryApi.setGridOption('rowData', rows);
            }
            showFeedback('Loaded summary for ' + rows.length + ' countries.', 'info');
        } catch (err) {
            console.error(err);
            showFeedback(t.summaryFailed || 'Summary failed', 'error');
        }
    }

    async function updateStatus(id, status) {
        var url = (config.statusUrlTemplate || '').replace('{id}', id);
        var resp = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf, Accept: 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ status: status }),
        });
        var data = await resp.json();
        if (!resp.ok) throw new Error(data.error || 'Update failed');
        showFeedback(t.updated || 'Status updated', 'success');
        await loadRows();
    }

    function initQuestionsGrid(rows) {
        var result = AgGridHelper.create(
            'validationQuestionsGrid',
            'admin-validation-questions',
            buildColumnDefs(),
            rows,
            {
                gridOptions: { pagination: true, paginationPageSize: 50, paginationPageSizeSelector: [25, 50, 100, 200] },
                columnVisibilityOptions: { buttonPlaceholderId: 'vq-col-vis-placeholder', enableExport: true, enableReset: true },
                onReady: function (api) {
                    gridApi = api;
                    AgGridHelper.pinActionsColumn(api, null, result.helper && result.helper.columnVisibilityManager);
                },
            }
        );
        gridHelper = result.helper;
        gridApi = result.api;
    }

    function initSummaryGrid() {
        var result = AgGridHelper.create(
            'validationCountrySummaryGrid',
            'admin-validation-country-summary',
            buildSummaryColumnDefs(),
            [],
            {
                gridOptions: { pagination: true, paginationPageSize: 50 },
                columnVisibilityOptions: { buttonPlaceholderId: 'vqs-col-vis-placeholder', enableExport: true },
            }
        );
        summaryApi = result.api;
    }

    document.querySelectorAll('#vq-tabs [role="tab"]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            activateTab(btn.getAttribute('data-tab'));
        });
    });

    document.getElementById('vqs-template')?.addEventListener('change', loadSummaryPeriods);
    document.getElementById('vqs-load')?.addEventListener('click', loadCountrySummary);
    document.getElementById('vq-refresh')?.addEventListener('click', loadRows);
    document.getElementById('vq-export')?.addEventListener('click', function () {
        window.location.href = config.exportUrl;
    });
    document.getElementById('vq-import')?.addEventListener('click', function () {
        document.getElementById('vq-import-file')?.click();
    });
    document.getElementById('vq-import-file')?.addEventListener('change', async function (e) {
        var file = e.target.files && e.target.files[0];
        if (!file) return;
        var formData = new FormData();
        formData.append('excel_file', file);
        formData.append('csrf_token', csrf);
        try {
            var resp = await fetch(config.importUrl, { method: 'POST', body: formData, credentials: 'same-origin', headers: { Accept: 'application/json' } });
            var data = await resp.json();
            if (!resp.ok) throw new Error(data.error || t.importFailed);
            showFeedback('Import complete — updated: ' + (data.updated || 0), data.has_errors ? 'error' : 'success');
            await loadRows();
        } catch (err) {
            showFeedback(t.importFailed || 'Import failed', 'error');
        } finally {
            e.target.value = '';
        }
    });

    document.addEventListener('click', function (e) {
        var waive = e.target.closest('.vq-waive');
        var reopen = e.target.closest('.vq-reopen');
        if (waive) {
            updateStatus(waive.dataset.id, 'waived').catch(function (err) { showFeedback(err.message, 'error'); });
        }
        if (reopen) {
            updateStatus(reopen.dataset.id, 'open').catch(function (err) { showFeedback(err.message, 'error'); });
        }
    });

    initSummaryGrid();
    loadRows().then(initQuestionsGrid);
})();
