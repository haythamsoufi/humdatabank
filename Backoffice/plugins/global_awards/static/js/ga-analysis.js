/* Global Awards Data Explorer tab: filters, KPIs, ApexCharts, tables. */
(function (global) {
    'use strict';

    var CFG = global.GaAnalysisConfig || {};
    var UI = CFG.ui || {};
    var panel = document.getElementById('panel-global-awards');
    if (!panel) return;

    var state = {
        analysis: null,
        charts: [],
        loaded: false,
        loading: false
    };

    function byId(id) { return document.getElementById(id); }
    function node(tag, className, text) {
        var el = document.createElement(tag);
        if (className) el.className = className;
        if (text != null) el.textContent = text;
        return el;
    }
    function show(el, on) {
        if (!el) return;
        el.hidden = !on;
    }
    function destroyCharts() {
        state.charts.forEach(function (chart) {
            try { chart.destroy(); } catch (e) { /* noop */ }
        });
        state.charts = [];
    }

    var GaCharts = {
        mount: function (host, spec, size) {
            if (!global.ApexCharts || !host || !spec) return null;
            host.innerHTML = '';
            var height = (size && size.height) || 280;
            var width = size && size.width;
            var options = this.options(spec, height, width);
            var chart = new global.ApexCharts(host, options);
            try {
                chart.render();
            } catch (e) {
                host.textContent = spec.title || 'Chart unavailable';
                return null;
            }
            return chart;
        },
        options: function (spec, height, width) {
            var kind = spec.kind || 'bar';
            var categories = spec.categories || [];
            var stacked = kind === 'stacked_bar';
            var grouped = kind === 'grouped_bar';
            var donut = kind === 'donut';
            var palette = spec.colors || (spec.series || []).map(function (s) { return s.color; }).filter(Boolean);
            var chart = {
                type: donut ? 'donut' : 'bar',
                height: height,
                stacked: stacked,
                toolbar: { show: false },
                fontFamily: 'inherit',
                animations: { enabled: !width }
            };
            if (width) chart.width = width;
            var base = {
                chart: chart,
                legend: { position: donut ? 'bottom' : 'top', fontSize: '12px' },
                dataLabels: { enabled: donut },
                plotOptions: {
                    bar: { horizontal: false, columnWidth: stacked || grouped ? '55%' : '45%', borderRadius: 2 },
                    pie: { donut: { size: '62%' } }
                },
                grid: { strokeDashArray: 3, padding: { left: 8, right: 8 } },
                noData: { text: '—' }
            };
            if (palette.length) base.colors = palette;
            if (donut) {
                base.series = ((spec.series || [])[0] && (spec.series || [])[0].data) || [];
                base.labels = categories.map(function (label) { return label == null ? '' : String(label); });
                return base;
            }
            base.series = (spec.series || []).map(function (s) {
                return {
                    name: s.name,
                    data: (s.data || []).map(function (value) { return value == null ? 0 : value; })
                };
            });
            base.xaxis = {
                categories: categories.map(function (label) { return label == null ? '' : String(label); }),
                labels: { rotate: categories.length > 8 ? -35 : 0, trim: true }
            };
            base.yaxis = {
                labels: {
                    formatter: function (value) {
                        if (value == null) return '';
                        if (Math.abs(value) >= 1000) return Math.round(value).toLocaleString();
                        return String(value);
                    }
                }
            };
            base.stroke = { show: grouped || stacked, width: grouped ? 2 : 0, colors: ['transparent'] };
            base.tooltip = { shared: stacked || grouped, intersect: !(stacked || grouped) };
            return base;
        }
    };

    global.GaAnalysis = global.GaAnalysis || {};
    global.GaAnalysis.charts = GaCharts;

    function chartCard(spec) {
        var card = node('article', 'gai-card' + (spec.kind === 'grouped_bar' || spec.kind === 'stacked_bar' ? ' gai-card--wide' : ''));
        card.setAttribute('data-gai-chart', spec.id || '');
        var head = node('div', 'gai-card__text');
        head.appendChild(node('h3', 'gai-card__title', spec.title || ''));
        if (spec.hint) head.appendChild(node('p', 'gai-card__hint', spec.hint));
        card.appendChild(head);
        var plot = node('div', 'gai-chart');
        card.appendChild(plot);
        return { element: card, plot: plot, spec: spec };
    }

    function renderKpis(kpis) {
        var host = byId('gai-kpis');
        if (!host) return;
        host.replaceChildren();
        (kpis || []).forEach(function (kpi) {
            var card = node('div', 'gai-kpi');
            card.appendChild(node('p', 'gai-kpi__label', kpi.label || ''));
            card.appendChild(node('p', 'gai-kpi__value', kpi.value == null ? '—' : String(kpi.value)));
            if (kpi.meta) card.appendChild(node('p', 'gai-kpi__meta', kpi.meta));
            host.appendChild(card);
        });
    }

    function renderCalendar(cycles) {
        var host = byId('gai-calendar');
        if (!host) return;
        host.replaceChildren();
        if (!cycles || !cycles.length) {
            host.hidden = true;
            return;
        }
        host.hidden = false;
        cycles.forEach(function (cycle) {
            var card = node('div', 'gai-cycle');
            card.appendChild(node('p', 'gai-cycle__slot', cycle.slot || ''));
            var due = cycle.country_due ? (UI.due || 'Country due') + ' ' + cycle.country_due : '';
            card.appendChild(node('p', 'gai-cycle__meta', due));
            var total = cycle.total || 0;
            var bar = node('div', 'gai-cycle__bar');
            [['approved', '#6ba543'], ['submitted', '#3d7ea6'], ['progress', '#f39200'], ['pending', '#d1d5db']].forEach(function (pair) {
                var count = cycle[pair[0]] || 0;
                if (!total || !count) return;
                var seg = node('span', 'gai-cycle__seg');
                seg.style.width = (100 * count / total) + '%';
                seg.style.background = pair[1];
                bar.appendChild(seg);
            });
            card.appendChild(bar);
            card.appendChild(node('p', 'gai-cycle__counts',
                (cycle.approved || 0) + ' approved · ' + (cycle.submitted || 0) + ' submitted · ' + (cycle.progress || 0) + ' in progress'));
            host.appendChild(card);
        });
    }

    function renderTable(host, table) {
        if (!host) return;
        host.replaceChildren();
        if (!table || !(table.rows || []).length) return;
        var wrap = node('div');
        if (table.title) wrap.appendChild(node('h3', 'gai-card__title', table.title));
        var el = node('table', 'gai-table');
        var thead = node('thead');
        var tr = node('tr');
        (table.columns || []).forEach(function (col) {
            tr.appendChild(node('th', '', col.label || col.key));
        });
        thead.appendChild(tr);
        el.appendChild(thead);
        var tbody = node('tbody');
        table.rows.forEach(function (row) {
            var line = node('tr');
            (table.columns || []).forEach(function (col) {
                var cell = node('td');
                var value = row[col.key];
                if (col.key === 'latest_status' && row.latest_status) {
                    var tone = node('span', 'gai-tone gai-tone--' + (row.latest_tone || 'grey'));
                    cell.appendChild(tone);
                }
                cell.appendChild(document.createTextNode(value == null ? '—' : String(value)));
                line.appendChild(cell);
            });
            tbody.appendChild(line);
        });
        el.appendChild(tbody);
        wrap.appendChild(el);
        host.appendChild(wrap);
    }

    function fillSelect(select, items, allLabel, valueKey, labelKey) {
        if (!select) return;
        var current = select.value;
        select.replaceChildren();
        select.appendChild(new Option(allLabel, ''));
        (items || []).forEach(function (item) {
            if (typeof item === 'string') {
                select.appendChild(new Option(item, item));
                return;
            }
            select.appendChild(new Option(item[labelKey], String(item[valueKey])));
        });
        if (current && Array.prototype.some.call(select.options, function (opt) { return opt.value === current; })) {
            select.value = current;
        }
    }

    function applyFilters(analysis) {
        var filters = (analysis && analysis.filters) || {};
        fillSelect(byId('gai-region'), filters.regions, UI.all_regions || 'All regions');
        fillSelect(byId('gai-country'), filters.countries, UI.all_countries || 'All countries', 'id', 'name');
        fillSelect(byId('gai-cycle'), (filters.cycles || []).map(function (c) { return c.slot; }), UI.all_cycles || 'All cycles');
        var region = (analysis.meta || {}).region || '';
        var countryId = (analysis.meta || {}).country_id;
        var cycle = (analysis.meta || {}).cycle || '';
        if (region) byId('gai-region').value = region;
        if (countryId) byId('gai-country').value = String(countryId);
        if (cycle) byId('gai-cycle').value = cycle;
    }

    function chartsFor(section, analysis) {
        return (analysis.charts || []).filter(function (chart) {
            return (chart.section || 'overview') === section;
        });
    }

    function renderSection(section, analysis) {
        var host = byId('gai-grid-' + section);
        if (!host) return;
        host.replaceChildren();
        chartsFor(section, analysis).forEach(function (spec) {
            var made = chartCard(spec);
            host.appendChild(made.element);
            var chart = GaCharts.mount(made.plot, spec);
            if (chart) state.charts.push(chart);
        });
    }

    function render(analysis) {
        destroyCharts();
        state.analysis = analysis;
        if (!analysis || !analysis.ready) {
            show(byId('gai-content'), false);
            show(byId('gai-empty'), true);
            var empty = byId('gai-empty-text');
            if (empty && analysis && analysis.message) empty.textContent = analysis.message;
            return;
        }
        show(byId('gai-empty'), false);
        show(byId('gai-content'), true);
        var note = byId('gai-note');
        if (note) {
            var text = (analysis.meta && analysis.meta.note) || '';
            note.textContent = text;
            note.hidden = !text;
        }
        applyFilters(analysis);
        renderKpis(analysis.kpis);
        renderCalendar(analysis.cycles);
        renderSection('overview', analysis);
        renderSection('logframe', analysis);
        renderSection('countries', analysis);
        renderTable(byId('gai-country-table'), (analysis.tables || {}).countries);
        renderTable(byId('gai-indicator-table'), (analysis.tables || {}).indicators);
    }

    function query() {
        var params = new URLSearchParams();
        var region = byId('gai-region') && byId('gai-region').value;
        var country = byId('gai-country') && byId('gai-country').value;
        var cycle = byId('gai-cycle') && byId('gai-cycle').value;
        if (region) params.set('region', region);
        if (country) params.set('country_id', country);
        if (cycle) params.set('cycle', cycle);
        var qs = params.toString();
        return (CFG.dataUrl || panel.getAttribute('data-analysis-url')) + (qs ? '?' + qs : '');
    }

    function load() {
        if (state.loading) return;
        state.loading = true;
        show(byId('gai-loading'), true);
        show(byId('gai-error'), false);
        show(byId('gai-empty'), false);
        fetch(query(), { credentials: 'same-origin', headers: { Accept: 'application/json' } })
            .then(function (response) {
                if (!response.ok) throw new Error('request failed');
                return response.json();
            })
            .then(function (payload) {
                state.loading = false;
                state.loaded = true;
                show(byId('gai-loading'), false);
                render(payload.analysis || payload);
            })
            .catch(function () {
                state.loading = false;
                show(byId('gai-loading'), false);
                show(byId('gai-content'), false);
                show(byId('gai-error'), true);
            });
    }

    function showPane(id) {
        document.querySelectorAll('#gai-subtabs [data-gai-pane]').forEach(function (btn) {
            var on = btn.getAttribute('data-gai-pane') === id;
            btn.setAttribute('aria-selected', on ? 'true' : 'false');
            if (global.AdminUnderlineTabs) global.AdminUnderlineTabs.setStripButtonActive(btn, on);
        });
        ['overview', 'logframe', 'countries'].forEach(function (pane) {
            var el = byId('gai-pane-' + pane);
            if (el) el.hidden = pane !== id;
        });
        state.charts.forEach(function (chart) {
            try { chart.resize(); } catch (e) { /* noop */ }
        });
    }

    function panelVisible() {
        return !panel.classList.contains('hidden') && panel.offsetParent !== null;
    }

    function ensureLoaded() {
        if (!state.loaded && !state.loading) load();
    }

    document.querySelectorAll('#gai-subtabs [data-gai-pane]').forEach(function (btn) {
        btn.addEventListener('click', function () {
            showPane(btn.getAttribute('data-gai-pane'));
        });
    });
    ['gai-region', 'gai-country', 'gai-cycle'].forEach(function (id) {
        var el = byId(id);
        if (el) el.addEventListener('change', load);
    });
    var refresh = byId('gai-refresh');
    if (refresh) refresh.addEventListener('click', load);

    var exportDialog = byId('gai-export-dialog');
    panel.addEventListener('click', function (event) {
        var close = event.target.closest('[data-gai-close]');
        if (close && exportDialog) {
            exportDialog.close();
            return;
        }
        var button = event.target.closest('[data-gai-export]');
        if (!button) return;
        if (!state.analysis) {
            ensureLoaded();
            return;
        }
        if (global.GaAnalysis.export) global.GaAnalysis.export.open(button, state.analysis, CFG);
    });
    if (exportDialog) {
        exportDialog.addEventListener('click', function (event) {
            if (event.target === exportDialog) exportDialog.close();
        });
    }

    if (panelVisible()) {
        ensureLoaded();
    } else {
        var observer = new MutationObserver(function () {
            if (panelVisible()) {
                ensureLoaded();
                state.charts.forEach(function (chart) {
                    try { chart.resize(); } catch (e) { /* noop */ }
                });
            }
        });
        observer.observe(panel, { attributes: true, attributeFilter: ['class'] });
        var tabBtn = byId('tab-global-awards');
        if (tabBtn) tabBtn.addEventListener('click', function () { window.setTimeout(ensureLoaded, 0); });
    }
})(window);
