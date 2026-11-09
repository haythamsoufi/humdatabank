/**
 * Shared AI chat chart helpers (floating + immersive).
 * Normalize payloads, load ApexCharts once, and mount compact charts.
 * @module chatbot/chart-payloads
 */

let apexLoadPromise = null;

export function formatChartNumber(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return String(value == null ? '' : value);
    const isInt = Math.abs(n - Math.round(n)) < 1e-9;
    try {
        return new Intl.NumberFormat(undefined, {
            maximumFractionDigits: isInt ? 0 : 2,
            minimumFractionDigits: 0,
        }).format(n);
    } catch (_) {
        const s = isInt ? String(Math.round(n)) : String(n);
        return s.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    }
}

/** Load ApexCharts once for both floating and immersive chat. */
export function ensureApexCharts() {
    if (typeof window !== 'undefined' && typeof window.ApexCharts === 'function') {
        return Promise.resolve(window.ApexCharts);
    }
    if (apexLoadPromise) return apexLoadPromise;
    apexLoadPromise = new Promise((resolve, reject) => {
        const finish = (ok) => {
            if (ok && typeof window.ApexCharts === 'function') {
                resolve(window.ApexCharts);
                return;
            }
            apexLoadPromise = null;
            reject(new Error('ApexCharts failed to load'));
        };
        const existing = document.querySelector('script[data-humdb-chat-apex]');
        if (existing) {
            // load may already have fired before we attached listeners.
            if (existing.dataset.humdbChatApexReady === '1' || existing.readyState === 'complete') {
                finish(true);
                return;
            }
            existing.addEventListener('load', () => {
                existing.dataset.humdbChatApexReady = '1';
                finish(true);
            }, { once: true });
            existing.addEventListener('error', () => finish(false), { once: true });
            // Late-join: script finished but readyState not exposed on all browsers.
            if (typeof window.ApexCharts === 'function') finish(true);
            return;
        }
        const script = document.createElement('script');
        script.src = '/static/libs/apexcharts.min.js';
        script.defer = true;
        script.setAttribute('data-humdb-chat-apex', '1');
        script.onload = () => {
            script.dataset.humdbChatApexReady = '1';
            finish(true);
        };
        script.onerror = () => finish(false);
        document.head.appendChild(script);
    });
    return apexLoadPromise;
}

function chartRoot(payload) {
    if (!payload || typeof payload !== 'object') return null;
    if (payload.chart_payload && typeof payload.chart_payload === 'object') return payload.chart_payload;
    return payload;
}

/** Line / timeseries payload (keeps data_status for immersive status legends). */
export function normalizeLineChartPayload(payload) {
    const root = chartRoot(payload);
    if (!root) return null;
    const type = String(root.type || root.chart_type || '').trim().toLowerCase();
    const lineTypes = { '': true, line: true, linechart: true, timeseries: true };
    if (!(type in lineTypes)) return null;
    const rows = Array.isArray(root.series)
        ? root.series
        : (Array.isArray(root.data) ? root.data : (Array.isArray(root.points) ? root.points : []));
    if (!rows.length) return null;
    const pts = rows.map((r) => {
        if (!r || typeof r !== 'object') return null;
        const x = r.x != null ? r.x : (r.year != null ? r.year : r.period);
        const y = r.y != null ? r.y : r.value;
        const xx = Number(x);
        const yy = Number(y);
        if (!Number.isFinite(xx) || !Number.isFinite(yy)) return null;
        const year = Math.round(xx);
        if (year < 1900 || year > 2100) return null;
        return {
            x: year,
            y: yy,
            data_status: r.data_status || null,
            period_name: r.period_name || null,
        };
    }).filter(Boolean);
    if (!pts.length) return null;
    pts.sort((a, b) => (a.x || 0) - (b.x || 0));
    const metric = String(root.metric || root.y_label || 'value').trim() || 'value';
    const title = String(root.title || (`${metric} over time`)).trim() || (`${metric} over time`);
    return {
        type: 'line',
        title,
        metric,
        country: String(root.country || '').trim() || null,
        series: pts,
    };
}

export function normalizeBarChartPayload(payload) {
    const root = chartRoot(payload);
    if (!root) return null;
    const type = String(root.type || root.chart_type || '').trim().toLowerCase();
    if (type !== 'bar' && type !== 'barchart') return null;
    const cats = Array.isArray(root.categories) ? root.categories : [];
    if (!cats.length) return null;
    const categories = cats.map((c) => {
        if (!c || typeof c !== 'object') return null;
        const label = String(c.label || c.name || '').trim();
        const value = Number(c.value);
        if (!label || !Number.isFinite(value)) return null;
        return { label, value };
    }).filter(Boolean);
    if (categories.length < 2) return null;
    const metric = String(root.metric || 'Value').trim() || 'Value';
    const title = String(root.title || (`${metric} comparison`)).trim();
    let orientation = String(root.orientation || '').toLowerCase();
    if (orientation !== 'horizontal' && orientation !== 'vertical') {
        orientation = categories.length > 6 ? 'horizontal' : 'vertical';
    }
    return { type: 'bar', title, metric, categories, orientation };
}

export function normalizePieChartPayload(payload) {
    const root = chartRoot(payload);
    if (!root) return null;
    const type = String(root.type || root.chart_type || '').trim().toLowerCase();
    if (type !== 'pie' && type !== 'donut') return null;
    const raw = Array.isArray(root.slices) ? root.slices : (Array.isArray(root.data) ? root.data : []);
    if (raw.length < 2) return null;
    const slices = raw.map((s) => {
        if (!s || typeof s !== 'object') return null;
        const label = String(s.label || s.name || '').trim();
        const value = Number(s.value);
        if (!label || !Number.isFinite(value) || value < 0) return null;
        return { label, value };
    }).filter(Boolean);
    if (slices.length < 2) return null;
    return { type: 'pie', title: String(root.title || 'Distribution').trim(), slices };
}

/** @deprecated Prefer normalizeLineChartPayload — alias kept for immersive call sites. */
export function normalizeChartPayload(payload) {
    return normalizeLineChartPayload(payload);
}

const FONT = 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';

export function buildCompactLineChartOptions(normalized, opts = {}) {
    const height = opts.height != null ? opts.height : 210;
    const years = normalized.series.map((p) => p.x);
    const values = normalized.series.map((p) => p.y);
    return {
        chart: {
            type: 'area',
            height,
            fontFamily: FONT,
            toolbar: { show: false },
            background: 'transparent',
            animations: { enabled: true, easing: 'easeinout', speed: 500 },
            parentHeightOffset: 0,
        },
        series: [{ name: normalized.metric || 'Value', data: values }],
        stroke: { curve: 'smooth', width: 2.5 },
        fill: {
            type: 'gradient',
            gradient: {
                shade: 'light',
                type: 'vertical',
                shadeIntensity: 0.35,
                opacityFrom: 0.45,
                opacityTo: 0.05,
            },
        },
        markers: { size: 4, strokeWidth: 2, strokeColors: '#ffffff', hover: { size: 6 } },
        colors: ['#475569'],
        dataLabels: { enabled: false },
        grid: {
            borderColor: 'rgba(148, 163, 184, 0.2)',
            padding: { left: 6, right: 8, top: 4, bottom: 0 },
        },
        xaxis: {
            categories: years,
            axisBorder: { show: false },
            axisTicks: { show: false },
            labels: { style: { fontSize: '10px', colors: '#64748b' } },
        },
        yaxis: {
            labels: {
                style: { fontSize: '10px', colors: '#64748b' },
                formatter: (val) => formatChartNumber(val),
            },
        },
        tooltip: { y: { formatter: (val) => formatChartNumber(val) } },
        legend: { show: false },
    };
}

export function buildCompactBarChartOptions(normalized, opts = {}) {
    const height = opts.height != null
        ? opts.height
        : Math.min(320, Math.max(200, normalized.categories.length * 28));
    const labels = normalized.categories.map((c) => c.label);
    const values = normalized.categories.map((c) => c.value);
    const isHorizontal = normalized.orientation === 'horizontal';
    return {
        height,
        options: {
            chart: {
                type: 'bar',
                height,
                fontFamily: FONT,
                toolbar: { show: false },
                background: 'transparent',
                animations: { enabled: true, easing: 'easeinout', speed: 500 },
            },
            plotOptions: {
                bar: {
                    horizontal: isHorizontal,
                    borderRadius: 4,
                    columnWidth: '55%',
                    barHeight: '60%',
                },
            },
            series: [{ name: normalized.metric, data: values }],
            xaxis: {
                categories: labels,
                labels: { style: { fontSize: '10px', colors: '#64748b' } },
            },
            yaxis: {
                labels: {
                    style: { fontSize: '10px', colors: '#64748b' },
                    formatter: (v) => formatChartNumber(v),
                },
            },
            colors: ['#2563eb'],
            dataLabels: { enabled: normalized.categories.length <= 10 },
            grid: { borderColor: 'rgba(148,163,184,0.2)' },
            tooltip: { y: { formatter: (v) => formatChartNumber(v) } },
            legend: { show: false },
        },
    };
}

export function buildCompactPieChartOptions(normalized, opts = {}) {
    const height = opts.height != null ? opts.height : 230;
    const labels = normalized.slices.map((s) => s.label);
    const values = normalized.slices.map((s) => s.value);
    return {
        chart: {
            type: 'donut',
            height,
            fontFamily: FONT,
            toolbar: { show: false },
            background: 'transparent',
            animations: { enabled: true, easing: 'easeinout', speed: 500 },
        },
        series: values,
        labels,
        colors: ['#2563eb', '#059669', '#d97706', '#dc2626', '#7c3aed', '#0891b2', '#be185d', '#65a30d'],
        legend: { position: 'bottom', fontSize: '11px' },
        dataLabels: {
            enabled: true,
            formatter: (val) => (typeof val === 'number' ? `${val.toFixed(0)}%` : val),
        },
        tooltip: { y: { formatter: (v) => formatChartNumber(v) } },
    };
}

/**
 * Mount a compact line chart into chartEl. Returns the ApexCharts instance (or null).
 */
export async function mountCompactLineChart(chartEl, normalized, opts = {}) {
    if (!chartEl || !normalized) return null;
    const ApexCharts = await ensureApexCharts();
    if (!ApexCharts || !chartEl.isConnected) return null;
    const chart = new ApexCharts(chartEl, buildCompactLineChartOptions(normalized, opts));
    await chart.render();
    return chart;
}

export async function mountCompactBarChart(chartEl, normalized, opts = {}) {
    if (!chartEl || !normalized) return null;
    const ApexCharts = await ensureApexCharts();
    if (!ApexCharts || !chartEl.isConnected) return null;
    const built = buildCompactBarChartOptions(normalized, opts);
    chartEl.style.height = `${built.height}px`;
    const chart = new ApexCharts(chartEl, built.options);
    await chart.render();
    return chart;
}

export async function mountCompactPieChart(chartEl, normalized, opts = {}) {
    if (!chartEl || !normalized) return null;
    const ApexCharts = await ensureApexCharts();
    if (!ApexCharts || !chartEl.isConnected) return null;
    const chart = new ApexCharts(chartEl, buildCompactPieChartOptions(normalized, opts));
    await chart.render();
    return chart;
}

/** Expose helpers for classic scripts (immersive.js). */
export function installChatChartHelpers(target = typeof window !== 'undefined' ? window : null) {
    if (!target) return;
    target.HumdbChatCharts = {
        formatChartNumber,
        ensureApexCharts,
        normalizeLineChartPayload,
        normalizeChartPayload,
        normalizeBarChartPayload,
        normalizePieChartPayload,
        buildCompactLineChartOptions,
        buildCompactBarChartOptions,
        buildCompactPieChartOptions,
        mountCompactLineChart,
        mountCompactBarChart,
        mountCompactPieChart,
    };
}
