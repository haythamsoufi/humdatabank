/* UPR Analysis tab — Data Explorer. Fetches the Analysis views and hands them to
 * the shared renderers (upr-analysis-*.js). Everything about *what* is shown
 * (titles, series, tables, notes) comes from the server view; this file only
 * owns the page: loading states, region and round-type controls, and the table
 * dialog. Lazy-initialises when the panel first becomes visible so hidden-tab
 * charts size correctly. */
(function () {
    'use strict';

    var CFG = window.UprImpactConfig || {};
    var UI = CFG.ui || {};
    var A = window.UprAnalysis || {};

    var panel = document.getElementById('panel-upr-impact');
    if (!panel || !A.dom || !A.charts) return;

    function byId(id) {
        return document.getElementById(id);
    }

    var els = {
        region: byId('upri-region'),
        refresh: byId('upri-refresh'),
        loading: byId('upri-loading'),
        error: byId('upri-error'),
        errorText: byId('upri-error-text'),
        empty: byId('upri-empty'),
        content: byId('upri-content'),
        dialog: byId('upri-table-dialog'),
        exportDialog: byId('upri-export-dialog'),
        exportForm: byId('upri-export-form'),
        exportTitle: byId('upri-export-title'),
        exportList: byId('upri-export-list'),
        exportFields: byId('upri-export-fields'),
        exportTables: byId('upri-export-tables'),
        exportTablesRow: byId('upri-export-tables-row'),
        exportEmpty: byId('upri-export-empty'),
        exportGo: byId('upri-export-go')
    };

    // Each section (data / participation) owns its containers, its drawn charts
    // and the view it is showing, so one can reload without disturbing the other.
    function section(prefix) {
        return {
            kpis: byId(prefix + 'kpis'),
            grid: byId(prefix + 'grid'),
            notes: byId(prefix + 'notes'),
            warning: byId(prefix + 'warning'),
            charts: [],
            view: null,
            request: 0
        };
    }

    var data = section('upri-');
    var narr = section('upri-narr-');
    narr.stale = true;
    narr.views = null;
    narr.track = 'ALL';
    narr.loading = byId('upri-narr-loading');
    narr.error = byId('upri-narr-error');
    narr.content = byId('upri-narr-content');
    narr.root = byId('upri-narrative');

    var initialised = false;
    var regionsPopulated = false;

    function show(el, visible) {
        if (el) el.hidden = !visible;
    }

    function setState(state) {
        show(els.loading, state === 'loading');
        show(els.error, state === 'error');
        show(els.empty, state === 'empty');
        show(els.content, state === 'content');
    }

    function setNarrState(state) {
        show(narr.loading, state === 'loading');
        show(narr.error, state === 'error');
        show(narr.content, state === 'content');
    }

    function fetchJson(url, region) {
        if (region) url += (url.indexOf('?') === -1 ? '?' : '&') + 'region=' + encodeURIComponent(region);
        return fetch(url, { headers: { 'Accept': 'application/json' }, credentials: 'same-origin' })
            .then(function (resp) {
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                return resp.json();
            });
    }

    function destroyCharts(sec) {
        sec.charts.forEach(function (chart) {
            try { chart.destroy(); } catch (e) { /* noop */ }
        });
        sec.charts = [];
    }

    // Draw every visual of a view into the section's grid.
    function renderSection(sec, view) {
        destroyCharts(sec);
        sec.view = view;
        A.dom.renderKpis(sec.kpis, view.kpis);
        A.dom.renderNotes(sec.notes, view.notes);
        A.dom.renderWarnings(sec.warning, view.warnings);
        sec.grid.replaceChildren();
        (view.visuals || []).forEach(function (visual) {
            var card = A.dom.renderCard(visual, { ui: UI });
            sec.grid.appendChild(card.element);
            card.plots.forEach(function (plot) {
                var chart = A.charts.mount(plot.host, plot.chart);
                if (chart) sec.charts.push(chart);
            });
        });
    }

    // --- Data section ----------------------------------------------------

    function populateRegions(regions) {
        if (regionsPopulated || !els.region) return;
        (regions || []).forEach(function (r) {
            var opt = document.createElement('option');
            opt.value = r;
            opt.textContent = r;
            els.region.appendChild(opt);
        });
        regionsPopulated = true;
    }

    function load(region) {
        setState('loading');
        destroyCharts(data);
        data.view = null;
        var ticket = ++data.request;
        var url = CFG.dataUrl || panel.getAttribute('data-impact-url');
        fetchJson(url, region)
            .then(function (payload) {
                if (ticket !== data.request) return;
                var raw = (payload && payload.impact) || {};
                populateRegions(raw.regions);
                var view = payload && payload.view;
                if (!view || !view.has_data) {
                    setState('empty');
                    return;
                }
                setState('content');
                renderSection(data, view);
            })
            .catch(function (err) {
                if (ticket !== data.request) return;
                if (els.errorText) els.errorText.textContent = UI.load_failed || '';
                setState('error');
                if (window.console) console.error('UPR Analysis load failed', err);
            });
    }

    // --- Participation section -------------------------------------------

    function renderNarrative() {
        var view = narr.views && narr.views[narr.track];
        if (!view) return;
        setNarrState('content');
        renderSection(narr, view);
    }

    function loadNarrative(region) {
        if (!narr.root) return;
        var url = CFG.narrativeUrl || narr.root.getAttribute('data-narrative-url');
        if (!url) return;
        var ticket = ++narr.request;
        setNarrState('loading');
        destroyCharts(narr);
        narr.views = null;
        fetchJson(url, region)
            .then(function (payload) {
                if (ticket !== narr.request) return; // a newer request superseded this one
                narr.views = (payload && payload.views) || null;
                renderNarrative();
            })
            .catch(function (err) {
                if (ticket !== narr.request) return;
                setNarrState('error');
                if (window.console) console.error('UPR narrative participation load failed', err);
            });
    }

    function setTrack(track) {
        narr.track = track;
        var buttons = document.querySelectorAll('#upri-narr-tracks [data-upri-track]');
        Array.prototype.forEach.call(buttons, function (b) {
            var on = b.getAttribute('data-upri-track') === track;
            b.classList.toggle('is-active', on);
            b.setAttribute('aria-pressed', on ? 'true' : 'false');
        });
        renderNarrative();
    }

    // --- Table dialog ----------------------------------------------------

    function findVisual(sec, id) {
        var visuals = (sec.view && sec.view.visuals) || [];
        for (var i = 0; i < visuals.length; i++) {
            if (visuals[i].id === id) return visuals[i];
        }
        return null;
    }

    function sectionOf(el) {
        return narr.root && narr.root.contains(el) ? narr : data;
    }

    function openVisualTable(btn) {
        var visual = findVisual(sectionOf(btn), btn.getAttribute('data-upri-table'));
        if (visual) A.dom.openTable(els.dialog, visual.table, { ui: UI });
    }

    function openGapTable(btn) {
        var card = btn.closest('[data-upri-visual]');
        var visual = card && findVisual(sectionOf(btn), card.getAttribute('data-upri-visual'));
        var key = btn.getAttribute('data-upri-gap');
        var gap = visual && (visual.gaps || []).filter(function (g) { return g.id === key; })[0];
        if (gap) A.dom.openTable(els.dialog, gap.table, { ui: UI });
    }

    // --- Presentation and A4 report ----------------------------------------
    // Both are built from the views already on the page (no new request), so they
    // show exactly what the tab shows for the current region.

    var exporting = { mode: null, selected: ['data', 'track:ALL'] };

    function exportSections() {
        return A.pages.sections({ impact: data.view, narrative: narr.views }, UI);
    }

    function sectionCheckbox(entry) {
        var label = document.createElement('label');
        label.className = 'upri-check' + (entry.available ? '' : ' is-disabled');
        var input = document.createElement('input');
        input.type = 'checkbox';
        input.value = entry.id;
        input.disabled = !entry.available;
        input.checked = entry.available && exporting.selected.indexOf(entry.id) !== -1;
        label.appendChild(input);
        var text = document.createElement('span');
        text.textContent = entry.label;
        if (!entry.available) {
            var hint = document.createElement('span');
            hint.className = 'upri-check__hint';
            hint.textContent = UI.export_unavailable || '';
            text.appendChild(hint);
        }
        label.appendChild(text);
        return label;
    }

    function openExport(button) {
        if (!els.exportDialog || !A.pages) return;
        exporting.mode = button.getAttribute('data-upri-export');
        var entries = exportSections();
        var ready = entries.some(function (entry) { return entry.available; });
        els.exportList.replaceChildren();
        entries.forEach(function (entry) { els.exportList.appendChild(sectionCheckbox(entry)); });
        els.exportTitle.textContent = button.textContent.trim();
        els.exportGo.textContent = button.getAttribute('data-go-label') || '';
        els.exportGo.disabled = !ready;
        els.exportFields.hidden = !ready;
        els.exportEmpty.textContent = ready ? '' : (UI.export_nothing || '');
        els.exportEmpty.hidden = ready;
        els.exportTablesRow.hidden = !ready || exporting.mode !== 'report';
        els.exportDialog.showModal();
    }

    function regionName() {
        var select = els.region;
        if (!select || !select.value) return '';
        var chosen = select.options[select.selectedIndex];
        return chosen ? chosen.textContent : select.value;
    }

    function runExport() {
        var boxes = els.exportList.querySelectorAll('input[type="checkbox"]:checked');
        var selected = Array.prototype.map.call(boxes, function (box) { return box.value; });
        exporting.selected = selected;
        var blocks = A.pages.buildOutline({
            impact: data.view,
            narrative: narr.views,
            ui: UI,
            region: regionName(),
            generatedAt: new Date(),
            selected: selected,
            includeTables: exporting.mode === 'report' && els.exportTables.checked
        });
        els.exportDialog.close();
        if (!blocks.length) return;
        var options = { ui: UI, logoUrl: CFG.logoUrl, title: blocks[0].title, pdf: CFG.pdf };
        if (exporting.mode === 'present') A.slides.open(blocks, options);
        else A.report.open(blocks, options);
    }

    // --- Wiring ----------------------------------------------------------

    var subtab = 'data';

    function narrativePaneOpen() {
        var pane = byId('upri-pane-participation');
        return pane && !pane.hidden;
    }

    function showSubtab(name) {
        ['data', 'flow', 'participation'].forEach(function (id) {
            var pane = byId('upri-pane-' + id);
            var button = byId('upri-subtab-' + id);
            var on = id === name;
            if (pane) pane.hidden = !on;
            if (button) {
                button.classList.toggle('is-active', on);
                button.setAttribute('aria-selected', on ? 'true' : 'false');
            }
        });
        subtab = name;
        if (name === 'participation' && narr.stale) {
            narr.stale = false;
            loadNarrative(els.region ? els.region.value : '');
        }
        if (name === 'data' || name === 'participation') resizeCharts();
    }

    function reloadAll() {
        var region = els.region ? els.region.value : '';
        load(region);
        if (narrativePaneOpen()) loadNarrative(region);
        else narr.stale = true;
    }

    function ensureLoaded() {
        if (initialised) return;
        initialised = true;
        reloadAll();
    }

    if (els.region) els.region.addEventListener('change', reloadAll);
    if (els.refresh) els.refresh.addEventListener('click', reloadAll);

    panel.addEventListener('click', function (event) {
        var target = event.target;
        if (!target || !target.closest) return;
        var paneBtn = target.closest('[data-upri-pane]');
        if (paneBtn) showSubtab(paneBtn.getAttribute('data-upri-pane'));
        var trackBtn = target.closest('[data-upri-track]');
        if (trackBtn) setTrack(trackBtn.getAttribute('data-upri-track'));
        var gapBtn = target.closest('[data-upri-gap]');
        if (gapBtn) openGapTable(gapBtn);
        var tableBtn = target.closest('[data-upri-table]');
        if (tableBtn) openVisualTable(tableBtn);
        var exportBtn = target.closest('[data-upri-export]');
        if (exportBtn) openExport(exportBtn);
        var closer = target.closest('[data-upri-close]');
        var dialog = closer && closer.closest('dialog');
        if (dialog && dialog.open) dialog.close();
    });
    [els.dialog, els.exportDialog].forEach(function (dialog) {
        if (!dialog) return;
        dialog.addEventListener('click', function (event) {
            if (event.target === dialog) dialog.close();
        });
    });
    if (els.exportForm) {
        els.exportForm.addEventListener('submit', function (event) {
            event.preventDefault();
            runExport();
        });
    }

    // Lazy-init the first time the panel becomes visible. ApexCharts needs a
    // laid-out (non-hidden) container to size correctly.
    function panelVisible() {
        return !panel.classList.contains('hidden') && panel.offsetParent !== null;
    }

    function resizeCharts() {
        data.charts.concat(narr.charts).forEach(function (chart) {
            try { chart.resize(); } catch (e) { /* noop */ }
        });
    }

    if (panelVisible()) {
        ensureLoaded();
    } else {
        var observer = new MutationObserver(function () {
            if (panelVisible()) {
                ensureLoaded();
                resizeCharts();
            }
        });
        observer.observe(panel, { attributes: true, attributeFilter: ['class'] });
        // Fallback: the tab button toggles visibility via a sibling handler.
        var tabBtn = byId('tab-upr-impact');
        if (tabBtn) {
            tabBtn.addEventListener('click', function () {
                window.setTimeout(ensureLoaded, 0);
            });
        }
    }
})();
