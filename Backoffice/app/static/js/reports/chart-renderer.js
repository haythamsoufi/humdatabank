/**
 * ApexCharts rendering for report widgets.
 */
import { normalizeChartPayload, normalizeBarChartPayload, normalizePieChartPayload } from './chart-payload-normalize.js';

let apexPromise = null;

export function ensureApexCharts() {
    if (window.ApexCharts) return Promise.resolve(window.ApexCharts);
    if (apexPromise) return apexPromise;
    apexPromise = new Promise(function (resolve, reject) {
        var existing = document.querySelector('script[src*="apexcharts"]');
        if (existing && window.ApexCharts) {
            resolve(window.ApexCharts);
            return;
        }
        if (window.ApexCharts) {
            resolve(window.ApexCharts);
            return;
        }
        reject(new Error('ApexCharts not loaded'));
    });
    return apexPromise;
}

function formatAxisNumber(value) {
    if (value == null || !Number.isFinite(Number(value))) return '';
    return Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });
}

export async function renderLineChart(container, payload) {
    const normalized = normalizeChartPayload(payload);
    if (!normalized) return null;

    container.innerHTML = '';
    container.className = 'report-line-chart-host';

    const categories = normalized.series.map(function (p) { return String(p.x); });
    const values = normalized.series.map(function (p) { return p.y; });

    const ApexCharts = await ensureApexCharts();
    const chart = new ApexCharts(container, {
        chart: {
            type: 'line',
            height: 280,
            toolbar: { show: false },
            zoom: { enabled: false },
            animations: { enabled: true, speed: 400 }
        },
        series: [{ name: normalized.metric || 'Value', data: values }],
        colors: ['#0d9488'],
        stroke: { curve: 'smooth', width: 2.5 },
        markers: {
            size: 5,
            strokeWidth: 2,
            strokeColors: '#ffffff',
            hover: { size: 7 }
        },
        grid: {
            borderColor: '#e5e7eb',
            strokeDashArray: 4,
            xaxis: { lines: { show: false } },
            padding: { left: 12, right: 16, top: 8, bottom: 0 }
        },
        xaxis: {
            categories: categories,
            title: {
                text: 'Year',
                style: { fontSize: '12px', fontWeight: 600, color: '#64748b' }
            },
            axisBorder: { show: false },
            axisTicks: { show: false },
            labels: { style: { fontSize: '11px', colors: '#64748b' } }
        },
        yaxis: {
            labels: {
                style: { fontSize: '11px', colors: '#64748b' },
                formatter: formatAxisNumber
            },
            axisBorder: { show: false },
            axisTicks: { show: false }
        },
        dataLabels: { enabled: false },
        tooltip: {
            x: { show: true },
            y: { formatter: formatAxisNumber }
        },
        legend: { show: false }
    });
    await chart.render();
    return chart;
}

export async function renderBarChart(container, payload) {
    const normalized = normalizeBarChartPayload(payload);
    if (!normalized) return null;
    const ApexCharts = await ensureApexCharts();
    const horizontal = normalized.orientation === 'horizontal';
    const chart = new ApexCharts(container, {
        chart: { type: 'bar', height: 300, toolbar: { show: false } },
        plotOptions: { bar: { horizontal: horizontal } },
        series: [{ name: normalized.metric, data: normalized.categories.map(function (c) { return c.value; }) }],
        xaxis: { categories: normalized.categories.map(function (c) { return c.label; }) }
    });
    await chart.render();
    return chart;
}

export async function renderPieChart(container, payload) {
    const normalized = normalizePieChartPayload(payload);
    if (!normalized) return null;
    const ApexCharts = await ensureApexCharts();
    const colors = payload.chart_options?.colors;
    const chart = new ApexCharts(container, {
        chart: { type: 'pie', height: 300 },
        colors: colors,
        labels: normalized.slices.map(function (s) { return s.label; }),
        series: normalized.slices.map(function (s) { return s.value; }),
        legend: { show: payload.chart_options?.show_legend !== false }
    });
    await chart.render();
    return chart;
}

export async function renderAreaChart(container, payload) {
    const normalized = normalizeChartPayload(payload);
    if (!normalized) return null;
    container.innerHTML = '';
    container.className = 'report-line-chart-host';
    const categories = normalized.series.map(function (p) { return String(p.x); });
    const values = normalized.series.map(function (p) { return p.y; });
    const ApexCharts = await ensureApexCharts();
    const chart = new ApexCharts(container, {
        chart: { type: 'area', height: 280, toolbar: { show: false } },
        series: [{ name: normalized.metric || 'Value', data: values }],
        colors: payload.chart_options?.colors || ['#0d9488'],
        xaxis: { categories: categories },
        stroke: { curve: 'smooth', width: 2 },
        dataLabels: { enabled: false }
    });
    await chart.render();
    return chart;
}

export async function renderScatterChart(container, payload) {
    const chartPayload = payload.chart_payload || {};
    const points = chartPayload.points || (chartPayload.series || []).map(function (p) { return { x: p.x, y: p.y }; });
    if (!points.length) return null;
    const ApexCharts = await ensureApexCharts();
    const chart = new ApexCharts(container, {
        chart: { type: 'scatter', height: 300, toolbar: { show: false } },
        series: [{ name: chartPayload.metric || 'Value', data: points.map(function (p) { return [p.x, p.y]; }) }],
        colors: payload.chart_options?.colors || ['#0d9488']
    });
    await chart.render();
    return chart;
}

export async function renderComboChart(container, payload) {
    const chartPayload = payload.chart_payload || {};
    const bars = chartPayload.bars || chartPayload.categories || [];
    const line = chartPayload.line || chartPayload.series || [];
    if (!bars.length && !line.length) return renderBarChart(container, payload);
    const ApexCharts = await ensureApexCharts();
    const chart = new ApexCharts(container, {
        chart: { height: 320, toolbar: { show: false } },
        series: [
            { name: 'Bars', type: 'column', data: bars.map(function (c) { return c.value; }) },
            { name: 'Line', type: 'line', data: line.map(function (p) { return p.y; }) }
        ],
        labels: bars.map(function (c) { return c.label || c.x; }),
        colors: payload.chart_options?.colors || ['#0d9488', '#6366f1'],
        stroke: { width: [0, 3] }
    });
    await chart.render();
    return chart;
}

export async function renderGaugeChart(container, payload) {
    const value = Number(payload.value ?? payload.chart_payload?.value ?? 0);
    const ApexCharts = await ensureApexCharts();
    const chart = new ApexCharts(container, {
        chart: { type: 'radialBar', height: 280 },
        series: [Math.max(0, Math.min(100, value))],
        plotOptions: {
            radialBar: {
                hollow: { size: '55%' },
                dataLabels: { value: { formatter: function (v) { return Math.round(v) + '%'; } } }
            }
        },
        colors: payload.chart_options?.colors || ['#0d9488']
    });
    await chart.render();
    return chart;
}

export async function chartToPng(chart) {
    if (!chart || typeof chart.dataURI !== 'function') return null;
    const result = await chart.dataURI();
    return result && result.imgURI ? result.imgURI : null;
}
