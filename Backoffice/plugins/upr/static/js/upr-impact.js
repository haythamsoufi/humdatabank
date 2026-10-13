/* UPR Analysis tab — Data Explorer. Renders coverage, funding, reach, partner
 * and capacity trends with ApexCharts. Self-contained: lazy-initialises when
 * its panel first becomes visible so hidden-tab charts size correctly. */
(function () {
    'use strict';

    var CFG = window.UprImpactConfig || {};
    var I18N = CFG.i18n || {};
    var COLORS = {
        navy: '#011e41',
        red: '#f5333f',
        amber: '#f39200',
        teal: '#2a9d8f',
        green: '#6ba543',
        blue: '#3d7edb',
        purple: '#8b5a9e',
        grey: '#58595b'
    };

    var panel = document.getElementById('panel-upr-impact');
    if (!panel) return;

    var els = {
        region: document.getElementById('upri-region'),
        refresh: document.getElementById('upri-refresh'),
        loading: document.getElementById('upri-loading'),
        error: document.getElementById('upri-error'),
        errorText: document.getElementById('upri-error-text'),
        empty: document.getElementById('upri-empty'),
        content: document.getElementById('upri-content'),
        kpis: document.getElementById('upri-kpis')
    };

    var charts = {};
    var initialised = false;
    var loadedRegion = null;
    var regionsPopulated = false;

    function t(key, fallback) {
        return I18N[key] != null ? I18N[key] : (fallback != null ? fallback : key);
    }

    function show(el, visible) {
        if (el) el.hidden = !visible;
    }

    function setState(state) {
        show(els.loading, state === 'loading');
        show(els.error, state === 'error');
        show(els.empty, state === 'empty');
        show(els.content, state === 'content');
    }

    function fmtInt(n) {
        if (n == null || isNaN(n)) return '—';
        return Math.round(n).toLocaleString();
    }

    function fmtMoney(n) {
        if (n == null || isNaN(n)) return '—';
        var abs = Math.abs(n);
        if (abs >= 1e9) return (n / 1e9).toFixed(1).replace(/\.0$/, '') + 'B';
        if (abs >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, '') + 'M';
        if (abs >= 1e3) return (n / 1e3).toFixed(0) + 'K';
        return Math.round(n).toLocaleString();
    }

    function getApex() {
        return window.ApexCharts || null;
    }

    // Narrative charts are loaded separately, so each loader only clears its own.
    function destroyCharts(narrative) {
        Object.keys(charts).forEach(function (k) {
            var isNarrative = k.indexOf('upri-chart-narr-') === 0;
            if (isNarrative !== !!narrative) return;
            try { charts[k].destroy(); } catch (e) { /* noop */ }
            delete charts[k];
        });
    }

    function mount(id, options) {
        var Apex = getApex();
        var container = document.getElementById(id);
        if (!Apex || !container) return;
        if (charts[id]) { try { charts[id].destroy(); } catch (e) { /* noop */ } }
        var base = {
            chart: {
                fontFamily: 'inherit',
                toolbar: { show: false },
                animations: { enabled: true, easing: 'easeinout', speed: 500 }
            },
            grid: { borderColor: '#eef0f2', strokeDashArray: 3 },
            dataLabels: { enabled: false },
            legend: { position: 'top', horizontalAlign: 'left', fontSize: '12px' },
            tooltip: { shared: true, intersect: false }
        };
        var merged = Object.assign({}, base, options);
        merged.chart = Object.assign({}, base.chart, options.chart || {});
        var chart = new Apex(container, merged);
        chart.render();
        charts[id] = chart;
    }

    // --- KPI cards -------------------------------------------------------
    function deltaMeta(delta, isMoney) {
        if (!delta || delta.latest == null) return '';
        if (delta.note) {
            return '<span class="upri-kpi__meta upri-kpi__delta--flat">' + delta.note + '</span>';
        }
        var cls = 'upri-kpi__delta--flat';
        var icon = 'fa-minus';
        var text;
        if (delta.change_abs != null) {
            // Small counts / rates where a % change is meaningless: show the raw change.
            if (delta.change_abs > 0) { cls = 'upri-kpi__delta--up'; icon = 'fa-arrow-up'; }
            else if (delta.change_abs < 0) { cls = 'upri-kpi__delta--down'; icon = 'fa-arrow-down'; }
            text = (delta.change_abs > 0 ? '+' : '') + delta.change_abs + (delta.change_unit || '');
        } else if (delta.change_pct == null) {
            text = t('noPrevious', 'first round');
        } else {
            if (delta.change_pct > 0) { cls = 'upri-kpi__delta--up'; icon = 'fa-arrow-up'; }
            else if (delta.change_pct < 0) { cls = 'upri-kpi__delta--down'; icon = 'fa-arrow-down'; }
            text = (delta.change_pct > 0 ? '+' : '') + delta.change_pct + '%';
        }
        var ctx = '';
        if (delta.previous_year != null) {
            ctx = ' <span class="upri-kpi__context">' +
                t('vsPrevious', 'vs {year}').replace('{year}', delta.previous_year) + '</span>';
        }
        return '<span class="upri-kpi__meta ' + cls + '"><i class="fas ' + icon +
            '" aria-hidden="true"></i>' + text + '</span>' + ctx;
    }

    function kpiCard(label, value, delta, isMoney) {
        var el = document.createElement('div');
        el.className = 'upri-kpi';
        var year = delta && delta.latest_year != null ? (' <span class="upri-kpi__context">(' + delta.latest_year + ')</span>') : '';
        el.innerHTML =
            '<p class="upri-kpi__label">' + label + '</p>' +
            '<div class="upri-kpi__value">' + value + year + '</div>' +
            deltaMeta(delta, isMoney);
        return el;
    }

    function renderKpis(h) {
        els.kpis.innerHTML = '';
        if (!h) return;
        var cards = [
            kpiCard(t('kpiCoverage'), fmtInt(h.coverage && h.coverage.latest), h.coverage, false),
            kpiCard(t('kpiRequirement'), fmtMoney(h.plan_requirement && h.plan_requirement.latest), h.plan_requirement, true),
            kpiCard(t('kpiReach'), fmtInt(h.reach && h.reach.latest), h.reach, false),
            kpiCard(t('kpiPartners'), fmtInt(h.partners && h.partners.latest), h.partners, false),
            kpiCard(t('kpiPartnerFunding'), fmtMoney(h.partner_funding && h.partner_funding.latest), h.partner_funding, true)
        ];
        cards.forEach(function (c) { els.kpis.appendChild(c); });
    }

    // --- Charts ----------------------------------------------------------
    // Everything is plotted on a calendar-year axis. Planning and reporting are
    // never mixed as separate round positions; reporting series carry one figure
    // per year (annual report, or mid-year report as a fall-back).
    var ipYears = {};
    function yearLabel(year) {
        return ipYears[year] ? (year + ' *') : String(year);
    }
    function yearCats(years) {
        return (years || []).map(yearLabel);
    }
    function yearsOf(points) {
        return (points || []).map(function (p) { return p.year; });
    }
    function col(points, key) {
        return (points || []).map(function (p) { return p[key] == null ? null : Math.round(p[key]); });
    }
    // Project a year-keyed series onto a shared list of years (gaps -> null).
    function along(years, points, key) {
        var m = {};
        (points || []).forEach(function (p) { m[p.year] = p[key]; });
        return (years || []).map(function (y) {
            return m[y] == null ? null : Math.round(m[y]);
        });
    }

    function renderCoverage(data) {
        var pts = (data.coverage && data.coverage.by_year) || [];
        var years = yearsOf(pts);
        mount('upri-chart-coverage', {
            chart: { type: 'bar', height: 300, stacked: false },
            colors: [COLORS.navy, COLORS.teal],
            series: [
                { name: t('planSubmitted', 'Plans submitted'), data: col(pts, 'plan_submitted') },
                { name: t('reportSubmitted', 'Reports submitted'), data: col(pts, 'report_submitted') }
            ],
            plotOptions: { bar: { columnWidth: '60%', borderRadius: 3 } },
            xaxis: { categories: yearCats(years) },
            yaxis: { labels: { formatter: fmtInt } }
        });
    }

    function renderFunding(data) {
        var f = data.funding || {};
        var years = (data.years || []).slice();
        mount('upri-chart-funding', {
            chart: { type: 'line', height: 300 },
            colors: [COLORS.navy, COLORS.amber, COLORS.red],
            stroke: { width: [3, 3, 3], curve: 'smooth', dashArray: [0, 0, 5] },
            markers: { size: 4 },
            series: [
                { name: t('planRequirement'), data: along(years, f.plan_requirement, 'value') },
                { name: t('reportFunding'), data: along(years, f.report_funding, 'value') },
                { name: t('reportExpenditure'), data: along(years, f.report_expenditure, 'value') }
            ],
            xaxis: { categories: yearCats(years) },
            yaxis: { labels: { formatter: fmtMoney } },
            tooltip: { y: { formatter: fmtMoney } }
        });
    }

    function renderReach(data) {
        var pts = (data.reach && data.reach.by_year) || [];
        mount('upri-chart-reach', {
            chart: { type: 'area', height: 300 },
            colors: [COLORS.teal],
            stroke: { width: 3, curve: 'smooth' },
            fill: { type: 'gradient', gradient: { shadeIntensity: 0.4, opacityFrom: 0.5, opacityTo: 0.05 } },
            markers: { size: 4 },
            series: [{ name: t('peopleReached'), data: col(pts, 'value') }],
            xaxis: { categories: yearCats(yearsOf(pts)) },
            yaxis: { labels: { formatter: fmtMoney } },
            tooltip: { y: { formatter: fmtInt } }
        });
    }

    function renderPartners(data) {
        var pts = (data.partners && data.partners.by_year) || [];
        mount('upri-chart-partners', {
            chart: { type: 'line', height: 300 },
            colors: [COLORS.purple, COLORS.amber],
            stroke: { width: [0, 3], curve: 'smooth' },
            markers: { size: [0, 4] },
            series: [
                { name: t('partners'), type: 'column', data: col(pts, 'partners') },
                { name: t('partnerFunding'), type: 'line', data: col(pts, 'funding') }
            ],
            plotOptions: { bar: { columnWidth: '45%', borderRadius: 3 } },
            xaxis: { categories: yearCats(yearsOf(pts)) },
            yaxis: [
                { seriesName: t('partners'), labels: { formatter: fmtInt } },
                { opposite: true, seriesName: t('partnerFunding'), labels: { formatter: fmtMoney } }
            ],
            tooltip: {
                y: {
                    formatter: function (val, opts) {
                        return opts.seriesIndex === 1 ? fmtMoney(val) : fmtInt(val);
                    }
                }
            }
        });
    }

    function renderCapacity(data) {
        var cap = data.capacity || {};
        // Reporting years, taken from the volunteers series (all capacity series
        // share the same reporting-year axis).
        var host = document.getElementById('upri-chart-capacity');
        if (!host) return;
        // One shared axis cannot show millions of volunteers next to thousands
        // of branches. Four charts, each scaled to its own counts.
        var specs = [
            { key: 'volunteers', name: t('volunteers'), color: COLORS.green },
            { key: 'staff', name: t('staff'), color: COLORS.red },
            { key: 'branches', name: t('branches'), color: COLORS.navy },
            { key: 'local_units', name: t('localUnits'), color: COLORS.blue }
        ];
        specs.forEach(function (spec) {
            var id = 'upri-cap-' + spec.key;
            if (charts[id]) {
                try { charts[id].destroy(); } catch (e) { /* noop */ }
                delete charts[id];
            }
        });
        host.textContent = '';
        host.classList.add('upri-cap-grid');
        specs.forEach(function (spec) {
            var points = cap[spec.key] || [];
            var years = yearsOf(points);
            var latest = null;
            points.forEach(function (p) { if (p.value) latest = p; });
            var block = document.createElement('div');
            block.className = 'upri-cap';
            var heading = document.createElement('p');
            heading.className = 'upri-cap__name';
            heading.textContent = spec.name;
            var figure = document.createElement('p');
            figure.className = 'upri-cap__value';
            figure.style.color = spec.color;
            figure.textContent = latest ? fmtInt(latest.value) : '—';
            if (latest) {
                var when = document.createElement('span');
                when.className = 'upri-cap__year';
                when.textContent = ' ' + latest.year;
                figure.appendChild(when);
            }
            var plot = document.createElement('div');
            plot.id = 'upri-cap-' + spec.key;
            block.appendChild(heading);
            block.appendChild(figure);
            block.appendChild(plot);
            host.appendChild(block);
            mount(plot.id, {
                chart: { type: 'area', height: 240, sparkline: { enabled: false }, toolbar: { show: false } },
                colors: [spec.color],
                stroke: { width: 2, curve: 'straight' },
                fill: { type: 'gradient', gradient: { shadeIntensity: 0.3, opacityFrom: 0.35, opacityTo: 0.02 } },
                markers: { size: 4 },
                series: [{ name: spec.name, data: along(years, points, 'value').map(function (v) { return v > 0 ? v : null; }) }],
                xaxis: { categories: yearCats(years), labels: { style: { fontSize: '12px' } } },
                yaxis: {
                    tickAmount: 4,
                    labels: {
                        formatter: function (v) { return fmtMoney(v); },
                        style: { fontSize: '12px' }
                    }
                },
                grid: { padding: { left: 12, right: 16 } },
                legend: { show: false },
                tooltip: { y: { formatter: function (val) { return val == null ? '—' : fmtInt(val); } } }
            });
        });
    }

    // --- Table view ------------------------------------------------------
    var tables = {};
    var narrTables = {};

    function headingText(id) {
        var el = document.getElementById(id);
        return el ? el.textContent : '';
    }

    function atYear(points, year) {
        for (var i = 0; i < (points || []).length; i++) {
            if (points[i].year === year) return points[i];
        }
        return null;
    }

    function numOrNull(point, key) {
        if (!point || point[key] == null) return null;
        return point[key];
    }

    function latestFirst(rows) {
        return rows.slice().sort(function (a, b) { return (b.year || 0) - (a.year || 0); });
    }

    function rawValue(value) {
        if (value && typeof value === 'object' && Object.prototype.hasOwnProperty.call(value, 'value')) return value.value;
        return value;
    }

    function midyearCell(value, on) {
        if (!on || value == null) return value;
        return { value: value, midyear: true };
    }

    function hasFigure(cells) {
        return (cells || []).some(function (value, index) {
            var number = rawValue(value);
            return index > 0 && typeof number === 'number' && number !== 0;
        });
    }

    function rankCells(cells) {
        var best = 0;
        (cells || []).forEach(function (value) {
            var number = rawValue(value);
            if (typeof number === 'number' && Math.abs(number) > best) best = Math.abs(number);
        });
        return best;
    }

    // Country rows under a year: drop all-zero lines, largest figure first.
    function countryCells(list, mapFn) {
        return (list || []).map(mapFn).filter(function (row) {
            return hasFigure(row.cells);
        }).sort(function (a, b) {
            return rankCells(b.cells) - rankCells(a.cells) ||
                String(a.cells[0]).localeCompare(String(b.cells[0]));
        });
    }

    function buildTables(data) {
        var years = (data.years || []).slice();
        var midyearYears = {};
        (data.midyear_fallback_years || []).forEach(function (y) { midyearYears[y] = 1; });
        var coverage = (data.coverage && data.coverage.by_year) || [];
        var funding = data.funding || {};
        var reach = (data.reach && data.reach.by_year) || [];
        var partners = (data.partners && data.partners.by_year) || [];
        var cap = data.capacity || {};
        var capYears = yearsOf(cap.volunteers || []);

        tables = {
            coverage: {
                title: headingText('upri-coverage-h'),
                note: '',
                columns: [t('year', 'Year'), t('planSubmitted', 'Plans submitted'), t('reportSubmitted', 'Reports submitted')],
                rows: latestFirst(coverage.map(function (p) {
                    return {
                        year: p.year,
                        cells: [yearLabel(p.year), numOrNull(p, 'plan_submitted'), numOrNull(p, 'report_submitted')],
                        countries: countryCells(p.countries, function (c) {
                            return { cells: [c.country, c.plan_submitted || null, c.report_submitted || null] };
                        })
                    };
                }))
            },
            funding: {
                title: headingText('upri-funding-h'),
                note: t('fundingSourceNote', ''),
                legend: t('midyearLegend', 'Mid-year report, shown where the annual report is not yet available'),
                columns: [
                    t('year', 'Year'),
                    t('planRequirement', 'Planned requirement'),
                    t('reportFunding', 'Reported funding'),
                    t('reportExpenditure', 'Reported expenditure')
                ],
                rows: latestFirst(years.map(function (y) {
                    var plan = atYear(funding.plan_requirement, y);
                    var reported = atYear(funding.report_funding, y);
                    var spent = atYear(funding.report_expenditure, y);
                    var midyear = !!midyearYears[y];
                    return {
                        year: y,
                        cells: [
                            yearLabel(y),
                            numOrNull(plan, 'value'),
                            midyearCell(numOrNull(reported, 'value'), midyear),
                            midyearCell(numOrNull(spent, 'value'), midyear)
                        ],
                        countries: countryCells(joinFundingCountries(plan, reported, spent, midyear), function (c) { return c; })
                    };
                }))
            },
            reach: {
                title: headingText('upri-reach-h'),
                note: '',
                columns: [t('year', 'Year'), t('planRound', 'Plan round'), t('peopleReached', 'People to be reached')],
                rows: latestFirst(reach.map(function (p) {
                    return {
                        year: p.year,
                        cells: [yearLabel(p.year), p.round, numOrNull(p, 'value')],
                        countries: countryCells(p.countries, function (c) {
                            return { cells: [c.country, null, c.value || null] };
                        })
                    };
                }))
            },
            partners: {
                title: headingText('upri-partners-h'),
                note: t('partnersSourceNote', ''),
                columns: [t('year', 'Year'), t('reportRound', 'Report round'), t('partners', 'Partners (PNS)'), t('partnerFunding', 'Partner funding (CHF)')],
                rows: latestFirst(partners.map(function (p) {
                    return {
                        year: p.year,
                        cells: [yearLabel(p.year), p.round, numOrNull(p, 'partners'), numOrNull(p, 'funding')],
                        countries: countryCells(p.countries, function (c) {
                            return { cells: [c.country, null, c.partners || null, c.funding || null] };
                        })
                    };
                }))
            },
            capacity: {
                title: headingText('upri-capacity-h'),
                note: '',
                columns: [t('year', 'Year'), t('reportRound', 'Report round'), t('volunteers', 'Volunteers'), t('staff', 'Staff'), t('branches', 'Branches'), t('localUnits', 'Local units')],
                rows: latestFirst(capYears.map(function (y) {
                    var vol = atYear(cap.volunteers, y);
                    var staff = atYear(cap.staff, y);
                    var branches = atYear(cap.branches, y);
                    var units = atYear(cap.local_units, y);
                    return {
                        year: y,
                        cells: [
                            yearLabel(y),
                            vol && vol.round,
                            numOrNull(vol, 'value'),
                            numOrNull(staff, 'value'),
                            numOrNull(branches, 'value'),
                            numOrNull(units, 'value')
                        ],
                        countries: countryCells(
                            joinCapacityCountries(vol, staff, branches, units),
                            function (c) { return c; }
                        )
                    };
                }))
            }
        };
    }

    function joinFundingCountries(plan, reported, spent, midyear) {
        var map = {};
        function take(list, field) {
            (list || []).forEach(function (c) {
                if (!c || !c.iso3) return;
                var row = map[c.iso3] || { country: c.country || c.iso3 };
                if (c.country) row.country = c.country;
                row[field] = c.value;
                map[c.iso3] = row;
            });
        }
        take(plan && plan.countries, 'plan');
        take(reported && reported.countries, 'funding');
        take(spent && spent.countries, 'expenditure');
        return Object.keys(map).map(function (iso) {
            var c = map[iso];
            return {
                cells: [
                    c.country,
                    c.plan == null ? null : c.plan,
                    midyearCell(c.funding == null ? null : c.funding, midyear),
                    midyearCell(c.expenditure == null ? null : c.expenditure, midyear)
                ]
            };
        });
    }

    function joinCapacityCountries(vol, staff, branches, units) {
        var map = {};
        function take(list, field) {
            (list || []).forEach(function (c) {
                if (!c || !c.iso3) return;
                var row = map[c.iso3] || { country: c.country || c.iso3 };
                if (c.country) row.country = c.country;
                row[field] = c.value;
                map[c.iso3] = row;
            });
        }
        take(vol && vol.countries, 'volunteers');
        take(staff && staff.countries, 'staff');
        take(branches && branches.countries, 'branches');
        take(units && units.countries, 'units');
        return Object.keys(map).map(function (iso) {
            var c = map[iso];
            return {
                cells: [c.country, null, c.volunteers || null, c.staff || null, c.branches || null, c.units || null]
            };
        });
    }

    function formatCell(value) {
        value = rawValue(value);
        if (typeof value === 'number') return Math.round(value).toLocaleString();
        if (value == null || value === '') return '—';
        return String(value);
    }

    function paintCell(td, value) {
        td.textContent = formatCell(value);
        if (value && value.midyear) {
            td.classList.add('upri-cell--midyear');
            td.title = t('midyearCell', 'Mid-year report — the annual report is not yet available');
        }
    }

    function openTable(key) {
        var spec = tables[key] || narrTables[key];
        var dialog = document.getElementById('upri-table-dialog');
        if (!spec || !dialog) return;
        var title = document.getElementById('upri-table-title');
        var note = document.getElementById('upri-table-note');
        var legend = document.getElementById('upri-table-legend');
        var legendText = document.getElementById('upri-table-legend-text');
        var head = document.getElementById('upri-table-head');
        var body = document.getElementById('upri-table-body');
        if (title) title.textContent = spec.title || '';
        if (note) {
            note.textContent = spec.note || '';
            note.hidden = !spec.note;
        }
        if (legend) {
            if (legendText) legendText.textContent = spec.legend || '';
            legend.hidden = !spec.legend;
        }
        if (head) head.textContent = '';
        if (body) body.textContent = '';
        var headRow = document.createElement('tr');
        (spec.columns || []).forEach(function (label) {
            var th = document.createElement('th');
            th.scope = 'col';
            th.textContent = label;
            headRow.appendChild(th);
        });
        if (head) head.appendChild(headRow);
        (spec.rows || []).forEach(function (row) {
            appendTableRow(body, Array.isArray(row) ? { cells: row } : row);
        });
        if (typeof dialog.showModal === 'function' && !dialog.open) dialog.showModal();
    }

    function appendTableRow(body, row) {
        if (!body) return;
        var cells = row.cells || [];
        var details = row.countries || [];
        var tr = document.createElement('tr');
        cells.forEach(function (value, index) {
            var td = document.createElement('td');
            if (index === 0 && details.length) {
                var btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'upri-expand';
                btn.setAttribute('aria-expanded', 'false');
                btn.setAttribute('aria-label', t('showCountries', 'Show countries') + ' ' + formatCell(value));
                var icon = document.createElement('i');
                icon.className = 'fas fa-chevron-right';
                icon.setAttribute('aria-hidden', 'true');
                btn.appendChild(icon);
                btn.appendChild(document.createTextNode(formatCell(value)));
                btn.addEventListener('click', function () {
                    var open = btn.getAttribute('aria-expanded') === 'true';
                    btn.setAttribute('aria-expanded', open ? 'false' : 'true');
                    icon.className = open ? 'fas fa-chevron-right' : 'fas fa-chevron-down';
                    var sibling = tr.nextElementSibling;
                    while (sibling && sibling.classList.contains('upri-table__detail')) {
                        sibling.hidden = open;
                        sibling = sibling.nextElementSibling;
                    }
                });
                td.appendChild(btn);
            } else {
                paintCell(td, value);
            }
            tr.appendChild(td);
        });
        body.appendChild(tr);
        details.forEach(function (detail) {
            var child = document.createElement('tr');
            child.className = 'upri-table__detail';
            child.hidden = true;
            (detail.cells || []).forEach(function (value) {
                var td = document.createElement('td');
                paintCell(td, value);
                child.appendChild(td);
            });
            body.appendChild(child);
        });
    }

    function hasAnyData(data) {
        var cov = (data.coverage && data.coverage.by_year) || [];
        return cov.some(function (p) { return p.plan_submitted > 0 || p.report_submitted > 0; });
    }

    function render(data) {
        if (!data || !hasAnyData(data)) {
            setState('empty');
            return;
        }
        setState('content');
        ipYears = {};
        (data.in_progress_years || []).forEach(function (y) { ipYears[y] = 1; });
        var note = document.getElementById('upri-inprogress-note');
        if (note) {
            var ipYrs = data.in_progress_years || [];
            var myYrs = data.midyear_fallback_years || [];
            if (ipYrs.length || myYrs.length) {
                var parts = [];
                if (ipYrs.length) {
                    parts.push(t('inProgressNote', '* Year still open — submissions are still coming in, so the most recent point understates the final total. Headline figures use the latest completed year.')
                        .replace('{years}', ipYrs.join(', ')));
                }
                if (myYrs.length) {
                    parts.push(t('midyearNote', 'Reporting figures use the annual report where available, otherwise the mid-year report (years: {years}).')
                        .replace('{years}', myYrs.join(', ')));
                }
                note.textContent = parts.join(' ');
                note.hidden = false;
            } else {
                note.hidden = true;
            }
        }
        renderKpis(data.headline);
        buildTables(data);
        renderCoverage(data);
        renderFunding(data);
        renderReach(data);
        renderPartners(data);
        renderCapacity(data);
    }

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
        destroyCharts();
        var url = (CFG.dataUrl || panel.getAttribute('data-impact-url'));
        if (region) url += (url.indexOf('?') === -1 ? '?' : '&') + 'region=' + encodeURIComponent(region);
        fetch(url, { headers: { 'Accept': 'application/json' }, credentials: 'same-origin' })
            .then(function (resp) {
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                return resp.json();
            })
            .then(function (payload) {
                var data = (payload && payload.impact) || payload;
                populateRegions(data.regions);
                loadedRegion = region || '';
                render(data);
            })
            .catch(function (err) {
                if (els.errorText) els.errorText.textContent = t('loadFailed');
                setState('error');
                if (window.console) console.error('UPR Analysis load failed', err);
            });
    }

    // --- Narrative participation ----------------------------------------
    // Data (assignments), internal narrative and public narrative per round,
    // one track (plans / mid-year / annual) at a time so rounds stay comparable.
    // ``ALL`` is the overview (every round type on one chronological axis) and
    // the default; P / MYR / AR drill into one round type.
    var narr = { data: null, track: 'ALL', gap: null };
    var nEls = {
        section: document.getElementById('upri-narrative'),
        loading: document.getElementById('upri-narr-loading'),
        error: document.getElementById('upri-narr-error'),
        content: document.getElementById('upri-narr-content'),
        warning: document.getElementById('upri-narr-warning'),
        kpis: document.getElementById('upri-narr-kpis'),
        gaps: document.getElementById('upri-narr-gaps'),
        gapsHint: document.getElementById('upri-narr-gaps-hint'),
        note: document.getElementById('upri-narr-note')
    };
    var narrRequest = 0;

    function narrState(state) {
        show(nEls.loading, state === 'loading');
        show(nEls.error, state === 'error');
        show(nEls.content, state === 'content');
    }

    function pctText(v) {
        return v == null || isNaN(v) ? '—' : (Math.round(v * 10) / 10) + '%';
    }

    function isOverview() {
        return narr.track === 'ALL';
    }

    function trackPoints() {
        var tracks = (narr.data && narr.data.tracks) || {};
        if (isOverview()) {
            // Every round, oldest first, so plans / mid-year / annual interleave by date.
            return [].concat(tracks.P || [], tracks.MYR || [], tracks.AR || [])
                .sort(function (a, b) { return (a.order || 0) - (b.order || 0); });
        }
        return tracks[narr.track] || [];
    }

    function nCats(pts) {
        return pts.map(function (p) {
            return (isOverview() ? String(p.round) : String(p.year)) + (p.in_progress ? ' *' : '');
        });
    }

    function nCol(pts, key, onlyWithData) {
        return pts.map(function (p) {
            if (onlyWithData && !p.data_available) return null;
            return p[key] == null ? null : p[key];
        });
    }

    function renderOverviewKpis() {
        var data = narr.data || {};
        var headline = data.headline || {};
        var overview = data.overview || {};
        var cycle = overview.cycle;
        var settled = (overview.settled_rounds || []).length;
        var always = ((overview.gaps || {}).always || []).length;
        var cards = [
            kpiCard(t('narrKpiPlans'), fmtInt(headline.P && headline.P.any && headline.P.any.latest), headline.P && headline.P.any, false),
            kpiCard(t('narrKpiMidyear'), fmtInt(headline.MYR && headline.MYR.any && headline.MYR.any.latest), headline.MYR && headline.MYR.any, false),
            kpiCard(t('narrKpiAnnual'), fmtInt(headline.AR && headline.AR.any && headline.AR.any.latest), headline.AR && headline.AR.any, false),
            kpiCard(
                t('narrKpiCycle'),
                cycle ? pctText(cycle.completion_pct) : '—',
                cycle ? {
                    latest: cycle.completion_pct, latest_year: cycle.year,
                    note: t('narrKpiCycleNote').replace('{both}', fmtInt(cycle.both)).replace('{plan}', fmtInt(cycle.plan))
                } : null,
                false
            ),
            kpiCard(
                t('narrKpiAlways'),
                settled ? fmtInt(always) : '—',
                settled ? { latest: always, note: t('narrKpiAlwaysNote').replace('{n}', fmtInt(settled)) } : null,
                false
            )
        ];
        cards.forEach(function (c) { nEls.kpis.appendChild(c); });
    }

    function renderNarrKpis() {
        nEls.kpis.innerHTML = '';
        if (isOverview()) {
            renderOverviewKpis();
            return;
        }
        var h = ((narr.data && narr.data.headline) || {})[narr.track] || {};
        var pub = h.publication_pct || {};
        // A rate and a tiny count change from 0 are better read as raw differences.
        function absDelta(src, unit) {
            var d = Object.assign({}, src || {});
            if (d.latest != null && d.previous != null) {
                d.change_abs = Math.round((d.latest - d.previous) * 10) / 10;
                d.change_unit = unit || '';
            }
            return d;
        }
        var pubDelta = absDelta(pub, ' pts');
        var hiddenDelta = absDelta(h.narrative_only, '');
        var cards = [
            kpiCard(t('narrKpiAny'), fmtInt(h.any && h.any.latest), h.any, false),
            kpiCard(t('narrKpiInternal'), fmtInt(h.internal && h.internal.latest), h.internal, false),
            kpiCard(t('narrKpiPublic'), fmtInt(h.public && h.public.latest), h.public, false),
            kpiCard(t('narrKpiHidden'), fmtInt(h.narrative_only && h.narrative_only.latest), hiddenDelta, false),
            kpiCard(t('narrKpiPublication'), pctText(pub.latest), pubDelta, false)
        ];
        cards.forEach(function (c) { nEls.kpis.appendChild(c); });
    }

    function renderNarrStage(pts) {
        mount('upri-chart-narr-stage', {
            chart: { type: 'line', height: 320 },
            colors: [COLORS.navy, COLORS.amber, COLORS.teal, COLORS.red],
            stroke: { width: [0, 0, 0, 3], curve: 'smooth' },
            markers: { size: [0, 0, 0, 4] },
            series: [
                { name: t('narrDataSubmitted'), type: 'column', data: nCol(pts, 'data_submitted', true) },
                { name: t('narrInternal'), type: 'column', data: nCol(pts, 'internal') },
                { name: t('narrPublic'), type: 'column', data: nCol(pts, 'public') },
                { name: t('narrEither'), type: 'line', data: nCol(pts, 'any') }
            ],
            plotOptions: { bar: { columnWidth: '65%', borderRadius: 3 } },
            xaxis: { categories: nCats(pts) },
            yaxis: { labels: { formatter: fmtInt } }
        });
    }

    function renderNarrMix(pts) {
        mount('upri-chart-narr-mix', {
            chart: { type: 'bar', height: 300, stacked: true },
            colors: [COLORS.green, COLORS.amber, COLORS.navy],
            series: [
                { name: t('narrBoth'), data: nCol(pts, 'both') },
                { name: t('narrNarrativeOnly'), data: nCol(pts, 'narrative_only') },
                { name: t('narrDataOnly'), data: nCol(pts, 'data_only') }
            ],
            plotOptions: { bar: { columnWidth: '55%', borderRadius: 2 } },
            xaxis: { categories: nCats(pts) },
            yaxis: { labels: { formatter: fmtInt } }
        });
    }

    function renderNarrPub(pts) {
        mount('upri-chart-narr-pub', {
            chart: { type: 'line', height: 300 },
            colors: [COLORS.amber, COLORS.teal, COLORS.purple],
            stroke: { width: [0, 0, 3], curve: 'smooth' },
            markers: { size: [0, 0, 4] },
            series: [
                { name: t('narrInternal'), type: 'column', data: nCol(pts, 'internal') },
                { name: t('narrPublished'), type: 'column', data: nCol(pts, 'published') },
                { name: t('narrPublicationRate'), type: 'line', data: nCol(pts, 'publication_pct') }
            ],
            plotOptions: { bar: { columnWidth: '60%', borderRadius: 3 } },
            xaxis: { categories: nCats(pts) },
            yaxis: [
                { seriesName: t('narrInternal'), labels: { formatter: fmtInt } },
                { seriesName: t('narrInternal'), show: false },
                { opposite: true, min: 0, max: 100, seriesName: t('narrPublicationRate'), labels: { formatter: function (v) { return Math.round(v) + '%'; } } }
            ],
            tooltip: {
                y: {
                    formatter: function (val, opts) {
                        return opts.seriesIndex === 2 ? pctText(val) : fmtInt(val);
                    }
                }
            }
        });
    }

    // Overview replacement for the retention card: how many settled rounds each
    // National Society took part in (core participants vs occasional ones).
    function renderNarrEngagement() {
        var eng = ((narr.data && narr.data.overview) || {}).engagement || [];
        mount('upri-chart-narr-ret', {
            chart: { type: 'bar', height: 300 },
            colors: [COLORS.teal],
            series: [{ name: t('narrEngSeries'), data: eng.map(function (e) { return e.countries; }) }],
            plotOptions: { bar: { columnWidth: '60%', borderRadius: 3 } },
            dataLabels: { enabled: true, style: { fontSize: '11px' } },
            legend: { show: false },
            xaxis: {
                categories: eng.map(function (e) { return String(e.rounds); }),
                title: { text: t('narrEngRounds'), style: { fontSize: '11px', color: '#6b7280' } }
            },
            yaxis: { labels: { formatter: fmtInt } }
        });
    }

    function renderNarrRetention(pts) {
        if (isOverview()) {
            renderNarrEngagement();
            return;
        }
        mount('upri-chart-narr-ret', {
            chart: { type: 'bar', height: 300, stacked: true },
            colors: [COLORS.grey, COLORS.green, COLORS.teal, COLORS.red],
            series: [
                { name: t('narrBaseline'), data: nCol(pts, 'baseline') },
                { name: t('narrRetained'), data: nCol(pts, 'retained') },
                { name: t('narrNew'), data: nCol(pts, 'new') },
                { name: t('narrLapsed'), data: pts.map(function (p) { return p.lapsed == null ? null : -p.lapsed; }) }
            ],
            plotOptions: { bar: { columnWidth: '55%', borderRadius: 2 } },
            xaxis: { categories: nCats(pts) },
            yaxis: { labels: { formatter: function (v) { return fmtInt(Math.abs(v)); } } },
            tooltip: { y: { formatter: function (v) { return v == null ? '—' : fmtInt(Math.abs(v)); } } }
        });
    }

    var GAP_LISTS = [
        { key: 'narrative_only', label: 'narrNarrativeOnly' },
        { key: 'data_only', label: 'narrDataOnly' },
        { key: 'unpublished', label: 'narrNotPublic' },
        { key: 'lapsed', label: 'narrLapsedTitle' }
    ];

    function countryRows(list) {
        return (list || []).map(function (c) { return [c.name, c.region]; });
    }

    var OVERVIEW_GAP_LISTS = [
        { key: 'always', label: 'narrGapAlways' },
        { key: 'intermittent', label: 'narrGapIntermittent' },
        { key: 'planned_not_reported', label: 'narrGapPlannedNotReported' },
        { key: 'never', label: 'narrGapNever' }
    ];

    // The lists behind the "Gaps to follow up" card: per round type they refer to
    // its latest settled round; in the overview they span all settled rounds.
    function gapSource() {
        var data = narr.data || {};
        if (isOverview()) {
            var overview = data.overview || {};
            var lists = Object.assign({}, overview.gaps || {});
            if (overview.cycle) lists.planned_not_reported = overview.cycle.planned_not_reported || [];
            var cycleLabel = overview.cycle ? overview.cycle.year : '';
            return {
                defs: OVERVIEW_GAP_LISTS,
                lists: lists,
                suffix: String((overview.settled_rounds || []).length),
                hint: t('narrGapsHintAll', 'Across {n} completed rounds.')
                    .replace('{n}', fmtInt((overview.settled_rounds || []).length))
                    .replace('{year}', cycleLabel),
                titleSuffix: ''
            };
        }
        var gap = (data.gaps || {})[narr.track];
        if (!gap) return null;
        return {
            defs: GAP_LISTS,
            lists: gap,
            hint: t('narrGapsHint', 'Latest completed round: {round}.').replace('{round}', gap.round),
            titleSuffix: ' — ' + gap.round
        };
    }

    function renderNarrGaps() {
        nEls.gaps.innerHTML = '';
        var source = gapSource();
        if (!source) {
            nEls.gapsHint.textContent = '';
            return;
        }
        nEls.gapsHint.textContent = source.hint;
        var gap = source.lists;
        source.defs.forEach(function (def) {
            var list = gap[def.key] || [];
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'upri-gap' + (list.length ? '' : ' is-empty');
            btn.setAttribute('data-upri-gap', def.key);
            var count = document.createElement('span');
            count.className = 'upri-gap__count';
            count.textContent = fmtInt(list.length);
            var label = document.createElement('span');
            label.className = 'upri-gap__label';
            label.textContent = t(def.label);
            btn.appendChild(count);
            btn.appendChild(label);
            nEls.gaps.appendChild(btn);
        });
    }

    function narrTable(headingId, pts, columns, cellsOf, countryKeys) {
        return {
            title: headingText(headingId),
            note: '',
            columns: columns,
            rows: latestFirst((pts || []).map(function (p) {
                return {
                    // ``order`` keeps plan / mid-year / annual rounds of one year in date order.
                    year: p.order != null ? p.order : p.year,
                    cells: cellsOf(p),
                    countries: countryCells(p.countries, function (c) {
                        var cells = [c.country, ''];
                        countryKeys.forEach(function (key) {
                            if (!key) { cells.push(null); return; }
                            var value = c[key];
                            cells.push(value ? value : null);
                        });
                        return { cells: cells };
                    })
                };
            }))
        };
    }

    function buildNarrTables() {
        var pts = trackPoints();
        var data = narr.data || {};
        var rounds = data.rounds || [];
        narrTables = {
            narr_stage: narrTable('upri-narr-part-h', pts, [
                t('year', 'Year'), t('narrRound'), t('narrDataSubmitted'), t('narrInternal'), t('narrPublic'), t('narrEither'), t('narrParticipationPct')
            ], function (p) {
                return [String(p.year) + (p.in_progress ? ' *' : ''), p.round,
                    p.data_available ? p.data_submitted : null, p.internal, p.public, p.any, pctText(p.participation_pct)];
            }, ['data_submitted', 'internal', 'public', 'any', null]),
            narr_mix: narrTable('upri-narr-mix-h', pts, [
                t('year', 'Year'), t('narrRound'), t('narrBoth'), t('narrNarrativeOnly'), t('narrDataOnly')
            ], function (p) {
                return [String(p.year) + (p.in_progress ? ' *' : ''), p.round, p.both, p.narrative_only, p.data_only];
            }, ['both', 'narrative_only', 'data_only']),
            narr_pub: narrTable('upri-narr-pub-h', pts, [
                t('year', 'Year'), t('narrRound'), t('narrInternal'), t('narrPublished'), t('narrNotPublic'), t('narrPublicOnly'), t('narrPublicationRate')
            ], function (p) {
                return [String(p.year) + (p.in_progress ? ' *' : ''), p.round, p.internal, p.published, p.unpublished, p.public_only, pctText(p.publication_pct)];
            }, ['internal', 'published', 'unpublished', 'public_only', null]),
            narr_ret: isOverview() ? {
                title: headingText('upri-narr-ret-h'),
                note: t('narrEngHint', ''),
                columns: [t('narrEngRounds'), t('narrEngSeries')],
                rows: (((data.overview || {}).engagement) || []).map(function (e) { return [String(e.rounds), e.countries]; })
            } : narrTable('upri-narr-ret-h', pts, [
                t('year', 'Year'), t('narrRound'), t('narrBaseline'), t('narrRetained'), t('narrNew'), t('narrLapsed')
            ], function (p) {
                return [String(p.year) + (p.in_progress ? ' *' : ''), p.round, p.baseline, p.retained, p.new, p.lapsed];
            }, ['baseline', 'retained', 'new', 'lapsed']),
            narr_matrix: {
                title: t('narrMatrixTitle', 'Country by round'),
                note: t('narrMatrixNote', ''),
                columns: [t('narrCountry'), t('narrRegion')].concat(rounds),
                rows: (data.matrix || []).map(function (m) {
                    return [m.name, m.region].concat(rounds.map(function (r) { return (m.rounds && m.rounds[r]) || ''; }));
                })
            }
        };
    }

    function openGap(key) {
        var source = gapSource();
        if (!source) return;
        var def = source.defs.filter(function (d) { return d.key === key; })[0];
        var list = source.lists[key] || [];
        narrTables.narr_gap = {
            title: t(def ? def.label : key) + source.titleSuffix,
            note: list.length ? '' : t('narrNone', ''),
            columns: [t('narrCountry'), t('narrRegion')],
            rows: countryRows(list)
        };
        openTable('narr_gap');
    }

    function renderNarrNote() {
        var data = narr.data || {};
        var parts = [];
        var open = (data.in_progress || []).filter(function (r) { return isOverview() || r.indexOf(narr.track) === 0; });
        if (open.length) parts.push(t('narrNoteInProgress').replace('{years}', open.join(', ')));
        var noData = [];
        trackPoints().forEach(function (p) { if (!p.data_available) noData.push(p.round); });
        if (noData.length) parts.push(t('narrNoteNoData').replace('{rounds}', noData.join(', ')));
        var src = data.sources || {};
        parts.push(t('narrNoteSources')
            .replace('{internal}', fmtInt(src.internal && src.internal.documents))
            .replace('{public}', fmtInt(src.public && src.public.documents)));
        if (data.universe) parts.push(t('narrNoteUniverse').replace('{n}', fmtInt(data.universe)));
        nEls.note.textContent = parts.join(' ');
    }

    function renderNarrWarning() {
        var src = (narr.data && narr.data.sources) || {};
        var msgs = [];
        if (src.internal && src.internal.available === false) msgs.push(t('narrInternal') + ': ' + (src.internal.message || ''));
        if (src.public && src.public.available === false) msgs.push(t('narrPublic') + ': ' + (src.public.message || ''));
        nEls.warning.textContent = msgs.join(' ');
        nEls.warning.hidden = !msgs.length;
    }

    // The fourth card is retention for one round type, but only makes sense
    // across rounds as an engagement-depth histogram, so title and hint swap.
    function renderRetentionHeading() {
        var title = document.getElementById('upri-narr-ret-h');
        var hint = document.getElementById('upri-narr-ret-hint');
        if (title) title.textContent = isOverview() ? t('narrEngTitle') : t('narrRetTitle');
        if (hint) hint.textContent = isOverview() ? t('narrEngHint') : t('narrRetHint');
    }

    function renderNarrative() {
        if (!narr.data) return;
        var pts = trackPoints();
        narrState('content');
        renderRetentionHeading();
        renderNarrWarning();
        renderNarrKpis();
        renderNarrGaps();
        buildNarrTables();
        renderNarrNote();
        renderNarrStage(pts);
        renderNarrMix(pts);
        renderNarrPub(pts);
        renderNarrRetention(pts);
    }

    function loadNarrative(region) {
        if (!nEls.section) return;
        var ticket = ++narrRequest;
        narrState('loading');
        destroyCharts(true);
        var url = CFG.narrativeUrl || nEls.section.getAttribute('data-narrative-url');
        if (!url) return;
        if (region) url += (url.indexOf('?') === -1 ? '?' : '&') + 'region=' + encodeURIComponent(region);
        fetch(url, { headers: { 'Accept': 'application/json' }, credentials: 'same-origin' })
            .then(function (resp) {
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                return resp.json();
            })
            .then(function (payload) {
                if (ticket !== narrRequest) return; // a newer request superseded this one
                narr.data = (payload && payload.narrative) || payload;
                renderNarrative();
            })
            .catch(function (err) {
                if (ticket !== narrRequest) return;
                narrState('error');
                if (window.console) console.error('UPR narrative participation load failed', err);
            });
    }

    function setTrack(track) {
        narr.track = track;
        var btns = document.querySelectorAll('#upri-narr-tracks [data-upri-track]');
        Array.prototype.forEach.call(btns, function (b) {
            var on = b.getAttribute('data-upri-track') === track;
            b.classList.toggle('is-active', on);
            b.setAttribute('aria-pressed', on ? 'true' : 'false');
        });
        renderNarrative();
    }

    function ensureLoaded() {
        if (initialised) return;
        initialised = true;
        var region = els.region ? els.region.value : '';
        load(region);
        loadNarrative(region);
    }

    function reloadAll() {
        var region = els.region ? els.region.value : '';
        load(region);
        loadNarrative(region);
    }

    // Region change + manual refresh.
    if (els.region) {
        els.region.addEventListener('change', reloadAll);
    }
    if (els.refresh) {
        els.refresh.addEventListener('click', reloadAll);
    }

    panel.addEventListener('click', function (event) {
        var trackBtn = event.target.closest && event.target.closest('[data-upri-track]');
        if (trackBtn) setTrack(trackBtn.getAttribute('data-upri-track'));
        var gapBtn = event.target.closest && event.target.closest('[data-upri-gap]');
        if (gapBtn) openGap(gapBtn.getAttribute('data-upri-gap'));
        var tableBtn = event.target.closest && event.target.closest('[data-upri-table]');
        if (tableBtn) openTable(tableBtn.getAttribute('data-upri-table'));
        if (event.target.closest && event.target.closest('[data-upri-close]')) {
            var dialog = document.getElementById('upri-table-dialog');
            if (dialog && dialog.open) dialog.close();
        }
    });
    var tableDialog = document.getElementById('upri-table-dialog');
    if (tableDialog) {
        tableDialog.addEventListener('click', function (event) {
            if (event.target === tableDialog) tableDialog.close();
        });
    }

    // Lazy-init the first time the panel becomes visible. ApexCharts needs a
    // laid-out (non-hidden) container to size correctly.
    function panelVisible() {
        return !panel.classList.contains('hidden') && panel.offsetParent !== null;
    }

    if (panelVisible()) {
        ensureLoaded();
    } else {
        var observer = new MutationObserver(function () {
            if (panelVisible()) {
                ensureLoaded();
                // Charts already mounted may need a resize once shown.
                Object.keys(charts).forEach(function (k) {
                    try { charts[k].resize(); } catch (e) { /* noop */ }
                });
            }
        });
        observer.observe(panel, { attributes: true, attributeFilter: ['class'] });
        // Fallback: the tab button toggles visibility via a sibling handler.
        var tabBtn = document.getElementById('tab-upr-impact');
        if (tabBtn) {
            tabBtn.addEventListener('click', function () {
                window.setTimeout(ensureLoaded, 0);
            });
        }
    }
})();
