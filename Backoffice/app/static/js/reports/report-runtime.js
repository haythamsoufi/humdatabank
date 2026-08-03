/**
 * Interactive report viewer — loads definition, runs widgets, renders sections.
 */
import { renderWidget, getWidgetChart, appendSectionFootnote } from './widget-renderer.js';
import { chartToPng } from './chart-renderer.js';

function readBootstrap() {
    const el = document.getElementById('report-runtime-bootstrap');
    if (!el) return {};
    try { return JSON.parse(el.textContent || '{}'); } catch (_) { return {}; }
}

async function apiPost(url, body, csrfToken) {
    const res = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken,
            'X-Requested-With': 'XMLHttpRequest'
        },
        body: JSON.stringify(body || {})
    });
    const data = await res.json().catch(function () { return {}; });
    if (!res.ok) throw new Error(data.message || data.error || 'Request failed');
    return data;
}

async function collectChartImages(root) {
    const images = {};
    const hosts = root.querySelectorAll('[data-widget-id]');
    for (const host of hosts) {
        const chart = getWidgetChart(host);
        if (!chart) continue;
        const png = await chartToPng(chart);
        if (png) images[host.dataset.widgetId] = png;
    }
    return images;
}

async function runReport(config) {
    const result = await apiPost(config.apiBase + '/run', {}, config.csrfToken);
    return {
        widgets: result.widgets || {},
        sections: result.sections || (config.definition || {}).sections || []
    };
}

async function renderSections(definition, widgets) {
    const root = document.getElementById('report-runtime-sections');
    if (!root) return;
    root.innerHTML = '';
    for (const section of definition.sections || []) {
        const sec = document.createElement('section');
        sec.className = 'report-section';
        const h2 = document.createElement('h2');
        h2.textContent = section.title || section.id;
        sec.appendChild(h2);
        for (const widget of section.widgets || []) {
            const host = document.createElement('div');
            host.dataset.widgetId = widget.id;
            sec.appendChild(host);
            const payload = widgets[widget.id] || { title: widget.title, error: 'No data' };
            await renderWidget(host, payload);
        }
        appendSectionFootnote(sec, section.footnote);
        root.appendChild(sec);
    }
}

async function init() {
    const config = readBootstrap();
    if (!config.reportId) return;
    const definition = config.definition || { sections: [] };
    try {
        const runResult = await runReport(config);
        await renderSections({ sections: runResult.sections }, runResult.widgets);
    } catch (err) {
        const root = document.getElementById('report-runtime-sections');
        if (root) root.textContent = err.message || 'Failed to load report';
    }

    const excelBtn = document.getElementById('report-export-excel');
    if (excelBtn) {
        excelBtn.addEventListener('click', async function () {
            const res = await fetch(config.apiBase + '/export', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': config.csrfToken,
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({ format: 'excel' })
            });
            if (!res.ok) return;
            const blob = await res.blob();
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = 'report.xlsx';
            a.click();
        });
    }

    const pdfBtn = document.getElementById('report-export-pdf');
    if (pdfBtn) {
        pdfBtn.addEventListener('click', async function () {
            const root = document.getElementById('report-runtime-sections');
            const chartImages = root ? await collectChartImages(root) : {};
            const res = await fetch(config.apiBase + '/export', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': config.csrfToken,
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({ format: 'pdf', chart_images: chartImages })
            });
            if (!res.ok) return;
            const blob = await res.blob();
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = 'report.pdf';
            a.click();
        });
    }
}

document.addEventListener('DOMContentLoaded', init);
