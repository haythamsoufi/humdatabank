/** v2 schema helpers for the report builder frontend. */

export const DEFAULT_LANGUAGES = ['en', 'fr', 'es', 'ar'];
export const DEFAULT_GRID = { columns: 12, row_height: 80 };

export const WIDGET_KINDS = {
    kpi: ['manual', 'assignment_status_counts', 'indicator_aggregate'],
    line: ['manual', 'indicator_timeseries'],
    area: ['manual', 'indicator_timeseries'],
    combo: ['manual', 'indicator_timeseries'],
    scatter: ['manual', 'indicator_timeseries'],
    gauge: ['manual', 'indicator_aggregate'],
    indicator_dashboard: ['indicator_dashboard'],
    bar: ['manual', 'indicator_by_country', 'indicator_by_dimension'],
    map: ['indicator_by_country'],
    pie: ['manual', 'assignment_status_counts', 'categorical_counts'],
    table: ['manual', 'indicator_values', 'indicator_set_aggregate', 'assignment_list', 'raw_data'],
    text: [],
    image: [],
    embed: [],
    divider: []
};

export const DATA_SOURCE_LABELS = {
    manual: 'Manual values',
    assignment_status_counts: 'Assignment status counts',
    indicator_aggregate: 'Single-period indicator total',
    indicator_timeseries: 'Indicator values over time',
    indicator_dashboard: 'Progress dashboard (chart + table)',
    indicator_by_country: 'Breakdown by country',
    indicator_by_dimension: 'Breakdown by dimension',
    indicator_values: 'Raw indicator values',
    indicator_set_aggregate: 'Multiple indicators summary',
    assignment_list: 'Assignment list',
    raw_data: 'Raw form data',
    categorical_counts: 'Category counts'
};

export const WIDGET_TYPE_LABELS = {
    kpi: 'KPI',
    line: 'Line chart',
    area: 'Area chart',
    combo: 'Combo chart',
    scatter: 'Scatter chart',
    gauge: 'Gauge',
    indicator_dashboard: 'Dashboard',
    bar: 'Bar chart',
    map: 'Map',
    pie: 'Pie chart',
    table: 'Table',
    text: 'Text',
    image: 'Image',
    embed: 'Embed',
    divider: 'Divider'
};

export function normalizeLanguage(language) {
    return (language || 'en').toLowerCase().split(/[-_]/)[0] || 'en';
}

export function resolveTranslation(translations, language, fallback) {
    if (!translations || typeof translations !== 'object') return fallback || '';
    const lang = normalizeLanguage(language);
    return translations[lang] || translations.en || Object.values(translations).find(Boolean) || fallback || '';
}

export function setTranslation(obj, field, language, value) {
    const key = field + '_translations';
    if (!obj[key] || typeof obj[key] !== 'object') obj[key] = {};
    const lang = normalizeLanguage(language);
    if (value && String(value).trim()) obj[key][lang] = String(value).trim();
    else delete obj[key][lang];
}

export function ensureV2Definition(definition) {
    const out = JSON.parse(JSON.stringify(definition || {}));
    out.schema_version = 2;
    out.languages = out.languages?.length ? out.languages.map(normalizeLanguage) : ['en'];
    out.default_language = normalizeLanguage(out.default_language || out.languages[0]);
    if (!out.theme) out.theme = { primary_color: '#0d9488', font_family: 'Inter, system-ui, sans-serif' };
    if (!out.filters) out.filters = { template_ids: [], period_names: [], country_ids: [], assignment_statuses: ['submitted', 'approved'], include_public_submissions: false };
    out.sections = (out.sections || []).map(function (section, idx) {
        return ensureV2Section(section, idx, out.default_language);
    });
    return out;
}

export function ensureV2Section(section, order, language) {
    const sec = { ...section };
    sec.order = order;
    sec.grid = sec.grid || { ...DEFAULT_GRID };
    if (!sec.title_translations && sec.title) sec.title_translations = { [language]: sec.title };
    if (!sec.title_translations) sec.title_translations = {};
    if (sec.footnote && !sec.footnote_translations) sec.footnote_translations = { [language]: sec.footnote };
    sec.widgets = (sec.widgets || []).map(function (widget, widgetIdx) {
        return ensureV2Widget(widget, widgetIdx, sec.grid.columns, language);
    });
    return sec;
}

export function defaultWidgetLayout(columns, y, type) {
    const h = { kpi: 2, divider: 1, text: 3, image: 4, embed: 4, map: 5, indicator_dashboard: 6, table: 4 }[type] || 4;
    return { x: 0, y: y || 0, w: columns || 12, h: h };
}

export function ensureV2Widget(widget, index, columns, language) {
    const w = { ...widget };
    if (!w.title_translations && w.title) w.title_translations = { [language]: w.title };
    if (!w.title_translations) w.title_translations = {};
    if (w.content && !w.content_translations) w.content_translations = { [language]: w.content };
    if (w.footnote && !w.footnote_translations) w.footnote_translations = { [language]: w.footnote };
    if (!w.layout) w.layout = defaultWidgetLayout(columns, index * 4, w.type);
    if (!w.chart_options) w.chart_options = {};
    return w;
}

export function localizedSection(section, language, defaultLanguage) {
    const out = { ...section };
    out.title = resolveTranslation(section.title_translations, language, section.title);
    out.footnote = resolveTranslation(section.footnote_translations, language, section.footnote);
    out.widgets = (section.widgets || []).map(function (widget) {
        return localizedWidget(widget, language, defaultLanguage);
    });
    return out;
}

export function localizedWidget(widget, language, defaultLanguage) {
    const out = { ...widget };
    out.title = resolveTranslation(widget.title_translations, language, widget.title);
    out.content = resolveTranslation(widget.content_translations, language, widget.content);
    out.footnote = resolveTranslation(widget.footnote_translations, language, widget.footnote);
    return out;
}

export function translationCompleteness(translations, languages) {
    const result = {};
    (languages || []).forEach(function (lang) {
        const key = normalizeLanguage(lang);
        result[key] = !!(translations && translations[key] && String(translations[key]).trim());
    });
    return result;
}
