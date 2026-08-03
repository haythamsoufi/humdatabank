/**
 * Shared chart payload normalization for reports and chatbot.
 */

export function normalizeChartPayload(payload) {
    if (!payload || typeof payload !== 'object') return null;
    const rootPayload = (payload.chart_payload && typeof payload.chart_payload === 'object')
        ? payload.chart_payload
        : payload;
    if (!rootPayload || typeof rootPayload !== 'object') return null;
    const type = String(rootPayload.type || rootPayload.chart_type || '').trim().toLowerCase();
    const lineTypes = { '': true, line: true, linechart: true, timeseries: true };
    if (!(type in lineTypes)) return null;
    const rows = Array.isArray(rootPayload.series)
        ? rootPayload.series
        : (Array.isArray(rootPayload.data) ? rootPayload.data : (Array.isArray(rootPayload.points) ? rootPayload.points : []));
    if (!rows.length) return null;
    const pts = rows.map((r) => {
        if (!r || typeof r !== 'object') return null;
        const x = r.x != null ? r.x : (r.year != null ? r.year : r.period);
        const y = r.y != null ? r.y : r.value;
        const xx = Number(x);
        const yy = Number(y);
        if (!Number.isFinite(xx) || !Number.isFinite(yy)) return null;
        return { x: Math.round(xx), y: yy };
    }).filter(Boolean);
    if (!pts.length) return null;
    pts.sort((a, b) => (a.x || 0) - (b.x || 0));
    const metric = String(rootPayload.metric || rootPayload.y_label || 'value').trim() || 'value';
    return {
        type: 'line',
        title: String(rootPayload.title || `${metric} over time`).trim(),
        metric,
        series: pts
    };
}

export function normalizeBarChartPayload(payload) {
    if (!payload || typeof payload !== 'object') return null;
    const rootPayload = (payload.chart_payload && typeof payload.chart_payload === 'object')
        ? payload.chart_payload
        : payload;
    if (!rootPayload || typeof rootPayload !== 'object') return null;
    if (String(rootPayload.type || '').toLowerCase() !== 'bar') return null;
    const cats = Array.isArray(rootPayload.categories) ? rootPayload.categories : [];
    const categories = cats.map((c) => {
        if (!c || typeof c !== 'object') return null;
        const label = String(c.label || c.name || '').trim();
        const value = Number(c.value);
        if (!label || !Number.isFinite(value)) return null;
        return { label, value };
    }).filter(Boolean);
    if (categories.length < 1) return null;
    return {
        type: 'bar',
        title: String(rootPayload.title || 'Comparison').trim(),
        metric: String(rootPayload.metric || 'Value').trim(),
        categories,
        orientation: rootPayload.orientation || (categories.length > 6 ? 'horizontal' : 'vertical')
    };
}

export function normalizePieChartPayload(payload) {
    if (!payload || typeof payload !== 'object') return null;
    const rootPayload = (payload.chart_payload && typeof payload.chart_payload === 'object')
        ? payload.chart_payload
        : payload;
    if (!rootPayload || typeof rootPayload !== 'object') return null;
    const type = String(rootPayload.type || '').toLowerCase();
    if (type !== 'pie' && type !== 'donut') return null;
    const raw = Array.isArray(rootPayload.slices) ? rootPayload.slices : (Array.isArray(rootPayload.data) ? rootPayload.data : []);
    const slices = raw.map((s) => {
        if (!s || typeof s !== 'object') return null;
        const label = String(s.label || s.name || '').trim();
        const value = Number(s.value);
        if (!label || !Number.isFinite(value)) return null;
        return { label, value };
    }).filter(Boolean);
    if (slices.length < 1) return null;
    return {
        type: 'pie',
        title: String(rootPayload.title || 'Distribution').trim(),
        slices
    };
}
