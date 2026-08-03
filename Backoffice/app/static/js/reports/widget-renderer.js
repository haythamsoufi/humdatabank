/**
 * Dispatch widget payloads to chart/table renderers.
 */
import { renderLineChart, renderBarChart, renderPieChart } from './chart-renderer.js';
import { renderTable } from './table-renderer.js';
import { renderYearDataGrid } from './dashboard-renderer.js';

const chartInstances = new WeakMap();

function appendFootnote(card, payload) {
    if (!payload?.footnote) return;
    const footnote = document.createElement('div');
    footnote.className = 'report-widget-footnote';
    footnote.textContent = payload.footnote;
    card.appendChild(footnote);
}

function mountCard(container, card, payload) {
    appendFootnote(card, payload);
    container.appendChild(card);
}

export async function renderWidget(container, payload) {
    container.innerHTML = '';
    const card = document.createElement('div');
    card.className = 'report-widget-card';
    const title = document.createElement('h3');
    title.className = 'report-widget-card-title';
    title.textContent = payload.title || payload.widget_id || 'Widget';
    card.appendChild(title);

    if (payload.error) {
        const err = document.createElement('p');
        err.className = 'text-red-600 text-sm';
        err.textContent = payload.error;
        card.appendChild(err);
        mountCard(container, card, payload);
        return { chart: null };
    }

    if (payload.type === 'text') {
        const body = document.createElement('div');
        body.innerHTML = payload.content || '';
        card.appendChild(body);
        mountCard(container, card, payload);
        return { chart: null };
    }

    if (payload.type === 'kpi') {
        const val = document.createElement('div');
        val.className = 'report-kpi-value';
        val.textContent = payload.value != null ? String(payload.value) : '—';
        card.appendChild(val);
        if (payload.metric) {
            const sub = document.createElement('div');
            sub.className = 'text-sm text-gray-600';
            sub.textContent = payload.metric;
            card.appendChild(sub);
        }
        mountCard(container, card, payload);
        return { chart: null };
    }

    if (payload.type === 'table' || payload.rows) {
        const tableHost = document.createElement('div');
        card.appendChild(tableHost);
        renderTable(tableHost, payload);
        mountCard(container, card, payload);
        return { chart: null };
    }

    const chartHost = document.createElement('div');
    card.appendChild(chartHost);
    container.appendChild(card);

    let chart = null;
    if (payload.type === 'indicator_dashboard') {
        chart = await renderLineChart(chartHost, payload);
        if (payload.dashboard) {
            renderYearDataGrid(card, payload.dashboard);
        }
    } else if (payload.type === 'line') {
        chart = await renderLineChart(chartHost, payload);
    } else if (payload.type === 'bar') {
        chart = await renderBarChart(chartHost, payload);
    } else if (payload.type === 'pie') {
        chart = await renderPieChart(chartHost, payload);
    } else if (payload.chart_payload) {
        const t = String(payload.chart_payload.type || '').toLowerCase();
        if (t === 'line') chart = await renderLineChart(chartHost, payload);
        else if (t === 'bar') chart = await renderBarChart(chartHost, payload);
        else if (t === 'pie' || t === 'donut') chart = await renderPieChart(chartHost, payload);
    }

    appendFootnote(card, payload);

    if (chart) chartInstances.set(container, chart);
    return { chart: chart };
}

export function getWidgetChart(container) {
    return chartInstances.get(container) || null;
}

export function appendSectionFootnote(sectionEl, footnote) {
    if (!footnote || !sectionEl) return;
    const el = document.createElement('div');
    el.className = 'report-section-footnote';
    el.textContent = footnote;
    sectionEl.appendChild(el);
}
