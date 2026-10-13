/**
 * UPR Analysis renderers: formatting, view-chart -> Apex options, and DOM cards
 * built from the server views (plugins/upr/analysis_spec.py).
 *
 * The fixture is produced by the Python view builders
 * (plugins/upr/tests/test_analysis_views.py regenerates and checks it), so these
 * tests exercise the real server <-> browser contract.
 */
import { describe, it, expect, beforeAll, beforeEach } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE = path.resolve(here, '../../../plugins/upr/tests/fixtures/analysis_views.json');
const STATIC = '../../../plugins/upr/static/js/';

let A;
let fixture;

beforeAll(async () => {
    await import(`${STATIC}upr-analysis-format.js`);
    await import(`${STATIC}upr-analysis-charts.js`);
    await import(`${STATIC}upr-analysis-dom.js`);
    A = window.UprAnalysis;
    fixture = JSON.parse(fs.readFileSync(FIXTURE, 'utf8'));
});

function everyChart(view) {
    const charts = [];
    view.visuals.forEach((visual) => {
        if (visual.chart) charts.push({ id: visual.id, chart: visual.chart });
        (visual.panels || []).forEach((panel) => charts.push({ id: `${visual.id}/${panel.id}`, chart: panel.chart }));
    });
    return charts;
}

describe('format', () => {
    it('formats integers, money, percentages and absolute values', () => {
        expect(A.format.int(1234.4)).toBe((1234).toLocaleString());
        expect(A.format.int(null)).toBe('—');
        expect(A.format.money(1_250_000)).toBe('1.3M');
        expect(A.format.money(2_000_000)).toBe('2M');
        expect(A.format.money(45_000)).toBe('45K');
        expect(A.format.money(1_500_000_000)).toBe('1.5B');
        expect(A.format.money(950)).toBe('950');
        expect(A.format.pct(12.34)).toBe('12.3%');
        expect(A.format.pct(12)).toBe('12%');
        expect(A.format.absInt(-7)).toBe('7');
        expect(A.format.format(5, 'unknown')).toBe('5');
    });

    it('renders table cells from numbers, text and mid-year markers', () => {
        expect(A.format.cellText(null)).toBe('—');
        expect(A.format.cellText('')).toBe('—');
        expect(A.format.cellText('AR25')).toBe('AR25');
        expect(A.format.cellText({ value: 1500, midyear: true })).toBe((1500).toLocaleString());
    });
});

describe('charts.buildOptions', () => {
    const base = {
        categories: ['2024', '2025'],
        height: 300,
        column_width: '60%',
        border_radius: 3,
        curve: 'smooth',
        stroke_width: 3,
        legend: true,
        data_labels: false,
        x_title: null,
        gradient: null,
        stacked: false,
        axes: { primary: { format: 'int' } },
    };
    const col = (name, axis = 'primary', format = 'int') => ({ name, kind: 'column', data: [1, 2], color: '#111', axis, format, dashed: false });
    const line = (name, axis = 'primary', format = 'int', dashed = false) => ({ name, kind: 'line', data: [1, 2], color: '#222', axis, format, dashed });

    it('draws a column-only chart as a bar chart without line styling', () => {
        const o = A.charts.buildOptions({ ...base, series: [col('A'), col('B')] });
        expect(o.chart.type).toBe('bar');
        expect(o.plotOptions.bar).toEqual({ columnWidth: '60%', borderRadius: 3 });
        expect(o.stroke).toBeUndefined();
        expect(o.series[0].type).toBeUndefined();
        expect(o.colors).toEqual(['#111', '#111']);
        expect(o.yaxis.labels.formatter(1500)).toBe((1500).toLocaleString());
    });

    it('mixes columns and lines on one chart, with per-series types and widths', () => {
        const o = A.charts.buildOptions({ ...base, series: [col('A'), line('B')] });
        expect(o.chart.type).toBe('line');
        expect(o.series.map((s) => s.type)).toEqual(['column', 'line']);
        expect(o.stroke.width).toEqual([0, 3]);
        expect(o.markers.size).toEqual([0, 4]);
    });

    it('dashes the series flagged as dashed', () => {
        const o = A.charts.buildOptions({ ...base, series: [line('A'), line('B', 'primary', 'int', true)] });
        expect(o.chart.type).toBe('line');
        expect(o.stroke.dashArray).toEqual([0, 5]);
    });

    it('creates one y-axis per axis id and hides axes shared by later series', () => {
        const o = A.charts.buildOptions({
            ...base,
            axes: { primary: { format: 'int' }, secondary: { format: 'pct', opposite: true, min: 0, max: 100 } },
            series: [col('A'), col('B'), line('Rate', 'secondary', 'pct')],
        });
        expect(Array.isArray(o.yaxis)).toBe(true);
        expect(o.yaxis[0].seriesName).toBe('A');
        expect(o.yaxis[1]).toEqual({ seriesName: 'A', show: false });
        expect(o.yaxis[2].opposite).toBe(true);
        expect([o.yaxis[2].min, o.yaxis[2].max]).toEqual([0, 100]);
        expect(o.yaxis[2].labels.formatter(50)).toBe('50%');
    });

    it('formats tooltips per series', () => {
        const o = A.charts.buildOptions({
            ...base,
            axes: { primary: { format: 'int' }, secondary: { format: 'money', opposite: true } },
            series: [col('Count'), line('Funding', 'secondary', 'money')],
        });
        const f = o.tooltip.y.formatter;
        expect(f(2_000_000, { seriesIndex: 1 })).toBe('2M');
        expect(f(1500, { seriesIndex: 0 })).toBe((1500).toLocaleString());
        expect(f(null, { seriesIndex: 0 })).toBe('—');
    });

    it('supports stacked bars with an absolute-value axis and negative series', () => {
        const o = A.charts.buildOptions({
            ...base,
            stacked: true,
            axes: { primary: { format: 'abs_int' } },
            series: [{ ...col('Lapsed', 'primary', 'abs_int'), data: [-3, null] }],
        });
        expect(o.chart.stacked).toBe(true);
        expect(o.yaxis.labels.formatter(-3)).toBe('3');
        expect(o.tooltip.y.formatter(-3, { seriesIndex: 0 })).toBe('3');
    });

    it('applies gradient fills to area series and honours legend, labels and titles', () => {
        const o = A.charts.buildOptions({
            ...base,
            legend: false,
            data_labels: true,
            x_title: 'Rounds',
            gradient: [0.4, 0.5, 0.05],
            axes: { primary: { format: 'money', tick_amount: 4 } },
            series: [{ name: 'Reach', kind: 'area', data: [1, 2], color: '#0a0', axis: 'primary', format: 'int', dashed: false }],
        });
        expect(o.chart.type).toBe('area');
        expect(o.fill.gradient).toEqual({ shadeIntensity: 0.4, opacityFrom: 0.5, opacityTo: 0.05 });
        expect(o.legend).toEqual({ show: false });
        expect(o.dataLabels.enabled).toBe(true);
        expect(o.xaxis.title.text).toBe('Rounds');
        expect(o.yaxis.tickAmount).toBe(4);
    });

    it('merges the house style without losing chart options', () => {
        const merged = A.charts.withBaseStyle({ chart: { type: 'bar', height: 240 }, tooltip: { y: { formatter: () => 'x' } } });
        expect(merged.chart.fontFamily).toBe('inherit');
        expect(merged.chart.height).toBe(240);
        expect(merged.tooltip.shared).toBe(true);
        expect(merged.tooltip.y.formatter()).toBe('x');
    });

    it('mounts through ApexCharts and returns the instance', () => {
        const calls = [];
        window.ApexCharts = class {
            constructor(el, options) { calls.push({ el, options }); }
            render() { calls.push('render'); }
        };
        const host = document.createElement('div');
        const chart = A.charts.mount(host, { ...base, series: [col('A')] });
        expect(chart).toBeInstanceOf(window.ApexCharts);
        expect(calls[0].el).toBe(host);
        expect(calls[0].options.chart.fontFamily).toBe('inherit');
        expect(calls[1]).toBe('render');
        delete window.ApexCharts;
        expect(A.charts.mount(host, { ...base, series: [col('A')] })).toBeNull();
    });
});

describe('server views (contract fixture)', () => {
    it('turns every chart of every view into well-formed Apex options', () => {
        const views = [fixture.impact, ...Object.values(fixture.narrative)];
        let count = 0;
        views.forEach((view) => {
            everyChart(view).forEach(({ id, chart }) => {
                const o = A.charts.buildOptions(chart);
                expect(o.series.length, id).toBe(chart.series.length);
                o.series.forEach((s) => expect(s.data.length, id).toBe(chart.categories.length));
                expect(o.xaxis.categories, id).toEqual(chart.categories);
                count += 1;
            });
        });
        expect(count).toBeGreaterThan(10);
    });

    it('renders KPI cards with value, year and change', () => {
        const host = document.createElement('div');
        A.dom.renderKpis(host, fixture.impact.kpis);
        const cards = host.querySelectorAll('.upri-kpi');
        expect(cards.length).toBe(fixture.impact.kpis.length);
        cards.forEach((card, i) => {
            expect(card.querySelector('.upri-kpi__label').textContent).toBe(fixture.impact.kpis[i].label);
        });
        host.querySelectorAll('.upri-kpi__meta').forEach((meta) => {
            expect(meta.className).toMatch(/upri-kpi__delta--(up|down|flat)/);
        });
    });

    it('renders a note-style delta without an arrow', () => {
        const host = document.createElement('div');
        A.dom.renderKpis(host, [
            { id: 'a', label: 'A', value: 50, format: 'pct', year: 2025, delta: { direction: 'flat', text: '3 of 6', context: null, note: true } },
            { id: 'b', label: 'B', value: 5, format: 'int', year: null, delta: { direction: 'up', text: '+20%', context: 'vs 2024', note: false } },
        ]);
        const [a, b] = host.querySelectorAll('.upri-kpi');
        expect(a.querySelector('.upri-kpi__value').textContent).toContain('50%');
        expect(a.querySelector('.upri-kpi__value').textContent).toContain('(2025)');
        expect(a.querySelector('i')).toBeNull();
        expect(b.querySelector('i.fa-arrow-up')).not.toBeNull();
        expect(b.textContent).toContain('vs 2024');
    });

    it('builds a card per visual with the title, hint and table button', () => {
        const visuals = [...fixture.impact.visuals, ...fixture.narrative.ALL.visuals];
        visuals.forEach((visual) => {
            const { element, plots } = A.dom.renderCard(visual, { ui: { view_table: 'View as table' } });
            expect(element.getAttribute('data-upri-visual')).toBe(visual.id);
            expect(element.querySelector('.upri-card__title').textContent).toBe(visual.title);
            expect(element.classList.contains('upri-card--wide')).toBe(!!visual.wide);
            expect(element.querySelector('[data-upri-table]').getAttribute('data-upri-table')).toBe(visual.id);
            if (visual.kind === 'chart') expect(plots).toHaveLength(1);
            if (visual.kind === 'panels') expect(plots).toHaveLength(visual.panels.length);
            if (visual.kind === 'gaps') {
                expect(plots).toHaveLength(0);
                expect(element.querySelectorAll('[data-upri-gap]')).toHaveLength(visual.gaps.length);
            }
        });
    });

    it('shows each capacity panel with its latest figure', () => {
        const capacity = fixture.impact.visuals.find((v) => v.id === 'capacity');
        const { element } = A.dom.renderCard(capacity, { ui: {} });
        const blocks = element.querySelectorAll('.upri-cap');
        expect(blocks).toHaveLength(4);
        expect(blocks[0].querySelector('.upri-cap__name').textContent).toBe(capacity.panels[0].name);
        expect(blocks[0].querySelector('.upri-cap__value').textContent).toContain(A.format.int(capacity.panels[0].value));
    });

    it('marks empty gap lists', () => {
        const gaps = fixture.narrative.P.visuals.find((v) => v.id === 'narr_gaps');
        const { element } = A.dom.renderCard(gaps, { ui: {} });
        gaps.gaps.forEach((gap) => {
            const btn = element.querySelector(`[data-upri-gap="${gap.id}"]`);
            expect(btn.classList.contains('is-empty')).toBe(gap.count === 0);
        });
    });
});

describe('table dialog', () => {
    let dialog;
    beforeEach(() => {
        document.body.innerHTML = `
            <dialog id="d">
                <h3 id="upri-table-title"></h3>
                <p id="upri-table-note" hidden></p>
                <p id="upri-table-legend" hidden><span id="upri-table-legend-text"></span></p>
                <table><thead id="upri-table-head"></thead><tbody id="upri-table-body"></tbody></table>
            </dialog>`;
        dialog = document.getElementById('d');
    });

    const spec = {
        title: 'Funding',
        note: 'A note',
        legend: 'Mid-year',
        columns: ['Year', 'Funding'],
        rows: [
            {
                cells: ['2025 *', { value: 300, midyear: true }],
                countries: [{ cells: ['Aland', 120] }, { cells: ['Bland', null] }],
            },
            { cells: ['2024', 800], countries: [] },
        ],
    };

    it('fills headings, note, legend and rows', () => {
        A.dom.fillTable(dialog, spec, { ui: { show_countries: 'Show countries', midyear_cell: 'Mid-year report' } });
        expect(document.getElementById('upri-table-title').textContent).toBe('Funding');
        expect(document.getElementById('upri-table-note').hidden).toBe(false);
        expect(document.getElementById('upri-table-legend').hidden).toBe(false);
        expect(dialog.querySelectorAll('thead th')).toHaveLength(2);
        const midyear = dialog.querySelector('.upri-cell--midyear');
        expect(midyear.title).toBe('Mid-year report');
        expect(midyear.textContent).toBe((300).toLocaleString());
    });

    it('keeps country lines hidden until their year is expanded', () => {
        A.dom.fillTable(dialog, spec, { ui: { show_countries: 'Show countries' } });
        const details = [...dialog.querySelectorAll('.upri-table__detail')];
        expect(details).toHaveLength(2);
        expect(details.every((d) => d.hidden)).toBe(true);
        const toggle = dialog.querySelector('.upri-expand');
        expect(toggle.getAttribute('aria-label')).toBe('Show countries 2025 *');
        toggle.click();
        expect(toggle.getAttribute('aria-expanded')).toBe('true');
        expect(details.every((d) => !d.hidden)).toBe(true);
        toggle.click();
        expect(details.every((d) => d.hidden)).toBe(true);
    });

    it('hides the note and legend when the spec has none and shows a dash for gaps', () => {
        A.dom.fillTable(dialog, { title: 'T', note: '', legend: '', columns: ['A'], rows: [{ cells: [null], countries: [] }] }, {});
        expect(document.getElementById('upri-table-note').hidden).toBe(true);
        expect(document.getElementById('upri-table-legend').hidden).toBe(true);
        expect(dialog.querySelector('tbody td').textContent).toBe('—');
    });
});
