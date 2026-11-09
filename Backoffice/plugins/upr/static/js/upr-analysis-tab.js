/* UPR Analysis tab — Data Explorer. Fetches the Analysis views and hands them to
 * the shared renderers (upr-analysis-*.js). Everything about *what* is shown
 * (titles, series, tables, notes) comes from the server view; this file only
 * owns the page: loading states, region and round-type controls, and the table
 * dialog. Lazy-initialises when the panel first becomes visible so hidden-tab
 * charts size correctly. */
(function () {
    'use strict';

    var CFG = window.UprAnalysisConfig || {};
    var UI = CFG.ui || {};
    var A = window.UprAnalysis || {};

    var panel = document.getElementById('panel-upr-analysis');
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

    var gp = section('upri-gp-');
    gp.stale = true;
    gp.views = null;
    gp.payload = null;
    gp.sectionId = 'overview';
    gp.year = '';
    gp.yearsPopulated = false;
    gp.loading = byId('upri-gp-loading');
    gp.error = byId('upri-gp-error');
    gp.empty = byId('upri-gp-empty');
    gp.content = byId('upri-gp-content');
    gp.root = byId('upri-global-plan');
    gp.yearSelect = byId('upri-gp-year');

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

    function fetchJson(url, region, year) {
        if (region) url += (url.indexOf('?') === -1 ? '?' : '&') + 'region=' + encodeURIComponent(region);
        if (year) url += (url.indexOf('?') === -1 ? '?' : '&') + 'year=' + encodeURIComponent(year);
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
                if (chart) {
                    plot.host._upriChart = chart;
                    sec.charts.push(chart);
                }
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
        var url = CFG.dataUrl || panel.getAttribute('data-analysis-url');
        fetchJson(url, region)
            .then(function (payload) {
                if (ticket !== data.request) return;
                var raw = (payload && payload.analysis) || {};
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

    // --- Global Plan section ---------------------------------------------

    function setGpState(state) {
        show(gp.loading, state === 'loading');
        show(gp.error, state === 'error');
        show(gp.empty, state === 'empty');
        show(gp.content, state === 'content');
    }

    function populateGpYears(years, selected) {
        if (!gp.yearSelect) return;
        gp.yearSelect.replaceChildren();
        (years || []).forEach(function (y) {
            var opt = document.createElement('option');
            opt.value = String(y);
            opt.textContent = String(y);
            if (String(y) === String(selected)) opt.selected = true;
            gp.yearSelect.appendChild(opt);
        });
        gp.yearsPopulated = true;
        gp.year = gp.yearSelect.value || '';
    }

    function renderGlobalPlan() {
        var view = gp.views && gp.views[gp.sectionId];
        if (!view || !view.has_data) {
            setGpState('empty');
            return;
        }
        setGpState('content');
        renderSection(gp, view);
    }

    function loadGlobalPlan(region, year) {
        if (!gp.root) return;
        var url = CFG.globalPlanUrl || gp.root.getAttribute('data-global-plan-url');
        if (!url) return;
        var ticket = ++gp.request;
        setGpState('loading');
        destroyCharts(gp);
        gp.views = null;
        gp.payload = null;
        fetchJson(url, region, year)
            .then(function (payload) {
                if (ticket !== gp.request) return;
                gp.payload = (payload && payload.global_plan) || null;
                gp.views = (payload && payload.views) || null;
                if (gp.payload) {
                    populateGpYears(
                        gp.payload.years,
                        gp.payload.year || gp.payload.immediate_year
                    );
                }
                renderGlobalPlan();
            })
            .catch(function (err) {
                if (ticket !== gp.request) return;
                setGpState('error');
                if (window.console) console.error('UPR Global Plan load failed', err);
            });
    }

    function setGpSection(sectionId) {
        gp.sectionId = sectionId;
        var buttons = document.querySelectorAll('#upri-gp-sections [data-upri-gp-section]');
        Array.prototype.forEach.call(buttons, function (b) {
            var on = b.getAttribute('data-upri-gp-section') === sectionId;
            b.classList.toggle('is-active', on);
            b.setAttribute('aria-pressed', on ? 'true' : 'false');
        });
        renderGlobalPlan();
        writeExploreUrl();
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
        if (gp.root && gp.root.contains(el)) return gp;
        if (narr.root && narr.root.contains(el)) return narr;
        return data;
    }

    function applySource(button) {
        var card = button.closest('[data-upri-visual]');
        var visual = card && findVisual(sectionOf(button), card.getAttribute('data-upri-visual'));
        if (!visual) return;
        var sourceId = button.getAttribute('data-upri-source');
        var source = null;
        (visual.sources || []).forEach(function (item) {
            if (item.id === sourceId) source = item;
        });
        if (!source) return;
        visual.chart = source.chart;
        visual.table = source.table;
        card.querySelectorAll('[data-upri-source]').forEach(function (item) {
            var on = item === button;
            item.classList.toggle('is-active', on);
            item.setAttribute('aria-pressed', on ? 'true' : 'false');
        });
        var host = card.querySelector('.upri-chart');
        var sec = sectionOf(button);
        if (host && host._upriChart) {
            try { host._upriChart.destroy(); } catch (e) { /* noop */ }
            sec.charts = sec.charts.filter(function (chart) { return chart !== host._upriChart; });
        }
        var chart = host && A.charts.mount(host, source.chart);
        if (host) host._upriChart = chart || null;
        if (chart) sec.charts.push(chart);
    }

    function applyMode(button) {
        if (button.classList.contains('is-active')) return;
        var card = button.closest('[data-upri-visual]');
        var visual = card && findVisual(sectionOf(button), card.getAttribute('data-upri-visual'));
        if (!visual) return;
        var modeId = button.getAttribute('data-upri-mode');
        var mode = null;
        (visual.modes || []).forEach(function (item) {
            if (item.id === modeId) mode = item;
        });
        if (!mode || !mode.chart) return;
        visual.chart = mode.chart;
        card.querySelectorAll('[data-upri-mode]').forEach(function (item) {
            var on = item === button;
            item.classList.toggle('is-active', on);
            item.setAttribute('aria-pressed', on ? 'true' : 'false');
        });
        var host = card.querySelector('.upri-chart');
        var sec = sectionOf(button);
        if (host && host._upriChart) {
            try { host._upriChart.destroy(); } catch (e) { /* noop */ }
            sec.charts = sec.charts.filter(function (chart) { return chart !== host._upriChart; });
        }
        var chart = host && A.charts.mount(host, mode.chart);
        if (host) host._upriChart = chart || null;
        if (chart) sec.charts.push(chart);
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

    var exporting = { mode: null, selected: ['data', 'track:ALL', 'global_plan:overview'] };

    function exportSections() {
        return A.pages.sections({ impact: data.view, narrative: narr.views, globalPlan: gp.views }, UI);
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
            globalPlan: gp.views,
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

    var TAB_ID = 'upr-analysis';
    var SUBTABS = ['data', 'flow', 'participation', 'global-plan'];
    var GP_SECTIONS = ['overview', 'secretariat', 'pns', 'yearly', 'regional', 'divisional', 'geo', 'people_reached', 'emergencies', 'countries', 'prioritisation'];
    var subtab = 'data';

    function queryValue(name) {
        try {
            return new URLSearchParams(window.location.search).get(name) || '';
        } catch (e) {
            return '';
        }
    }

    function subtabFromLocation() {
        var name = queryValue('subtab');
        return SUBTABS.indexOf(name) === -1 ? 'data' : name;
    }

    function sectionFromLocation() {
        var name = queryValue('section');
        return GP_SECTIONS.indexOf(name) === -1 ? 'overview' : name;
    }

    function writeExploreUrl() {
        if (typeof window.applyExploreParamsToUrl === 'function') {
            window.applyExploreParamsToUrl();
        }
    }

    window.exploreTabQueryExtras = window.exploreTabQueryExtras || {};
    window.exploreTabQueryExtras[TAB_ID] = function () {
        var extras = { subtab: subtab || 'data' };
        if ((subtab || 'data') === 'global-plan' && gp.sectionId && gp.sectionId !== 'overview') {
            extras.section = gp.sectionId;
        }
        return extras;
    };

    function narrativePaneOpen() {
        var pane = byId('upri-pane-participation');
        return pane && !pane.hidden;
    }

    function globalPlanPaneOpen() {
        var pane = byId('upri-pane-global-plan');
        return pane && !pane.hidden;
    }

    function showSubtab(name, options) {
        if (SUBTABS.indexOf(name) === -1) name = 'data';
        var syncUrl = !options || options.syncUrl !== false;
        var load = !options || options.load !== false;
        SUBTABS.forEach(function (id) {
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
        if (load && name === 'participation' && narr.stale) {
            narr.stale = false;
            loadNarrative(els.region ? els.region.value : '');
        }
        if (load && name === 'global-plan' && gp.stale) {
            gp.stale = false;
            loadGlobalPlan(els.region ? els.region.value : '', gp.yearSelect ? gp.yearSelect.value : '');
        }
        if (load && (name === 'data' || name === 'participation' || name === 'global-plan')) resizeCharts();
        if (syncUrl) writeExploreUrl();
    }

    function reloadAll() {
        var region = els.region ? els.region.value : '';
        load(region);
        if (narrativePaneOpen()) loadNarrative(region);
        else narr.stale = true;
        if (globalPlanPaneOpen()) loadGlobalPlan(region, gp.yearSelect ? gp.yearSelect.value : '');
        else gp.stale = true;
    }

    function ensureLoaded() {
        if (initialised) return;
        initialised = true;
        reloadAll();
    }

    if (els.region) els.region.addEventListener('change', reloadAll);
    if (els.refresh) els.refresh.addEventListener('click', reloadAll);
    if (gp.yearSelect) {
        gp.yearSelect.addEventListener('change', function () {
            gp.year = gp.yearSelect.value || '';
            if (globalPlanPaneOpen()) {
                loadGlobalPlan(els.region ? els.region.value : '', gp.year);
            } else {
                gp.stale = true;
            }
        });
    }

    panel.addEventListener('click', function (event) {
        var target = event.target;
        if (!target || !target.closest) return;
        var paneBtn = target.closest('[data-upri-pane]');
        if (paneBtn) showSubtab(paneBtn.getAttribute('data-upri-pane'));
        var trackBtn = target.closest('[data-upri-track]');
        if (trackBtn) setTrack(trackBtn.getAttribute('data-upri-track'));
        var gpSectionBtn = target.closest('[data-upri-gp-section]');
        if (gpSectionBtn) setGpSection(gpSectionBtn.getAttribute('data-upri-gp-section'));
        var sourceBtn = target.closest('[data-upri-source]');
        if (sourceBtn) applySource(sourceBtn);
        var modeBtn = target.closest('[data-upri-mode]');
        if (modeBtn) applyMode(modeBtn);
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
        data.charts.concat(narr.charts).concat(gp.charts).forEach(function (chart) {
            try { chart.resize(); } catch (e) { /* noop */ }
        });
    }

    var initialSubtab = subtabFromLocation();
    if (initialSubtab === 'global-plan') gp.sectionId = sectionFromLocation();
    showSubtab(initialSubtab, { syncUrl: false, load: false });

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
        var tabBtn = byId('tab-upr-analysis');
        if (tabBtn) {
            tabBtn.addEventListener('click', function () {
                window.setTimeout(ensureLoaded, 0);
            });
        }
    }
})();
