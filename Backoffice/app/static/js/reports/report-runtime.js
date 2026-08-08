/**
 * Interactive report viewer — loads definition, runs widgets, renders sections.
 */
import { renderWidget, getWidgetChart, appendSectionFootnote } from './widget-renderer.js';
import { chartToPng } from './chart-renderer.js';
import { resolveTranslation } from './builder/v2-compat.js';

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

async function runReport(config, language) {
    const result = await apiPost(config.apiBase + '/run', { language: language || config.language }, config.csrfToken);
    return {
        widgets: result.widgets || {},
        sections: result.sections || (config.definition || {}).sections || [],
        theme: result.theme || {},
        languages: result.languages || config.definition?.languages || ['en']
    };
}

async function renderSections(definition, widgets, language) {
    const root = document.getElementById('report-runtime-sections');
    if (!root) return;
    root.innerHTML = '';
    const defaultLanguage = definition.default_language || 'en';
    for (const section of definition.sections || []) {
        const sec = document.createElement('section');
        sec.className = 'report-section';
        sec.dataset.sectionId = section.id;
        const h2 = document.createElement('h2');
        h2.textContent = resolveTranslation(section.title_translations, language, section.title || section.id);
        sec.appendChild(h2);

        const grid = document.createElement('div');
        grid.className = 'report-runtime-grid';
        grid.style.display = 'grid';
        grid.style.gridTemplateColumns = 'repeat(' + (section.grid?.columns || 12) + ', minmax(0, 1fr))';
        grid.style.gap = '1rem';

        for (const widget of section.widgets || []) {
            const layout = widget.layout || { x: 0, y: 0, w: 12, h: 4 };
            const host = document.createElement('div');
            host.dataset.widgetId = widget.id;
            host.style.gridColumn = 'span ' + layout.w;
            grid.appendChild(host);
            const payload = widgets[widget.id] || { title: widget.title, error: 'No data' };
            await renderWidget(host, payload);
            attachCrossFilter(host, payload, section, configRef);
        }
        sec.appendChild(grid);
        appendSectionFootnote(sec, resolveTranslation(section.footnote_translations, language, section.footnote));
        root.appendChild(sec);
    }
}

let configRef = null;
let activeLanguage = 'en';

function attachCrossFilter(host, payload, section, config) {
    const interactions = section.interactions || [];
    if (!interactions.length || !config) return;
    host.addEventListener('click', async function () {
        const sourceId = host.dataset.widgetId;
        const interaction = interactions.find(function (item) { return item.source_widget_id === sourceId; });
        if (!interaction) return;
        const filterValue = payload?.chart_payload?.categories?.[0]?.label || payload?.value;
        const result = await apiPost(config.apiBase + '/run', {
            language: activeLanguage,
            filters: { adhoc_filters: { country_id: filterValue } }
        }, config.csrfToken);
        for (const targetId of interaction.target_widget_ids || []) {
            const targetHost = document.querySelector('[data-widget-id="' + targetId + '"]');
            if (!targetHost) continue;
            await renderWidget(targetHost, result.widgets[targetId] || { error: 'No data' });
        }
    });
}

function renderLanguageSwitcher(config, languages, onChange) {
    const toolbar = document.getElementById('report-runtime-toolbar');
    if (!toolbar || languages.length <= 1) return;
    toolbar.innerHTML = '';
    const select = document.createElement('select');
    select.className = 'form-control report-language-switcher';
    languages.forEach(function (lang) {
        const opt = document.createElement('option');
        opt.value = lang;
        opt.textContent = lang.toUpperCase();
        if (lang === activeLanguage) opt.selected = true;
        select.appendChild(opt);
    });
    select.addEventListener('change', function () { onChange(select.value); });
    toolbar.appendChild(select);
}

async function init() {
    configRef = readBootstrap();
    if (!configRef.reportId) return;
    const definition = configRef.definition || { sections: [] };
    activeLanguage = configRef.language || definition.default_language || 'en';
    document.documentElement.dir = activeLanguage === 'ar' ? 'rtl' : 'ltr';
    const theme = definition.theme || {};
    if (theme.primary_color) {
        document.documentElement.style.setProperty('--rb-accent', theme.primary_color);
    }

    async function load(language) {
        activeLanguage = language;
        document.documentElement.dir = language === 'ar' ? 'rtl' : 'ltr';
        try {
            const runResult = await runReport(configRef, language);
            renderLanguageSwitcher(configRef, runResult.languages, load);
            await renderSections({ ...definition, sections: runResult.sections }, runResult.widgets, language);
        } catch (err) {
            const root = document.getElementById('report-runtime-sections');
            if (root) root.textContent = err.message || 'Failed to load report';
        }
    }

    await load(activeLanguage);

    const excelBtn = document.getElementById('report-export-excel');
    if (excelBtn) {
        excelBtn.addEventListener('click', async function () {
            const res = await fetch(configRef.apiBase + '/export', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': configRef.csrfToken,
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({ format: 'excel', language: activeLanguage })
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
            const res = await fetch(configRef.apiBase + '/export', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': configRef.csrfToken,
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({ format: 'pdf', chart_images: chartImages, language: activeLanguage })
            });
            if (!res.ok) return;
            const blob = await res.blob();
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = 'report-' + activeLanguage + '.pdf';
            a.click();
        });
    }

    const docxBtn = document.getElementById('report-export-docx');
    if (docxBtn) {
        docxBtn.addEventListener('click', async function () {
            const root = document.getElementById('report-runtime-sections');
            const chartImages = root ? await collectChartImages(root) : {};
            const res = await fetch(configRef.apiBase + '/export', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': configRef.csrfToken,
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({ format: 'docx', chart_images: chartImages, language: activeLanguage })
            });
            if (!res.ok) return;
            const blob = await res.blob();
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = 'report-' + activeLanguage + '.docx';
            a.click();
        });
    }

    const publishStatus = document.getElementById('report-publish-status');
    if (publishStatus && configRef.reportId) {
        fetch(configRef.apiBase.replace(/\/api\/\d+$/, '') + '/api/runs?report_id=' + configRef.reportId).catch(function () {});
    }
}

document.addEventListener('DOMContentLoaded', init);
