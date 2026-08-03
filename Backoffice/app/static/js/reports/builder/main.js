/**
 * Report builder — WYSIWYG editor canvas + inspector panels.
 */
import { EditorCanvas, dynamicWidgetId } from './editor-canvas.js';

const WIDGET_KINDS = {
    kpi: ['assignment_status_counts', 'indicator_aggregate'],
    line: ['indicator_timeseries'],
    indicator_dashboard: ['indicator_dashboard'],
    bar: ['indicator_by_country', 'indicator_by_dimension'],
    pie: ['assignment_status_counts', 'categorical_counts'],
    table: ['indicator_values', 'indicator_set_aggregate', 'assignment_list', 'raw_data'],
    text: []
};

const DATA_SOURCE_LABELS = {
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

const DYNAMIC_KIND_BY_TYPE = {
    indicator_dashboard: 'indicator_dashboard',
    line: 'indicator_timeseries',
    kpi: 'indicator_aggregate',
    table: 'indicator_set_aggregate'
};

const WIDGET_TYPE_LABELS = {
    kpi: 'KPI',
    line: 'Line chart',
    indicator_dashboard: 'Dashboard',
    bar: 'Bar chart',
    pie: 'Pie chart',
    table: 'Table',
    text: 'Text'
};

const INDICATOR_DATA_SOURCE_KINDS = new Set([
    'indicator_aggregate',
    'indicator_timeseries',
    'indicator_dashboard',
    'indicator_by_country',
    'indicator_by_dimension',
    'indicator_values',
    'indicator_set_aggregate'
]);

function debounce(fn, ms) {
    let timer = null;
    return function (...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), ms);
    };
}

function uid(prefix) {
    return prefix + '-' + Math.random().toString(36).slice(2, 9);
}

function readBootstrap() {
    const el = document.getElementById('report-builder-bootstrap');
    if (!el) return {};
    try { return JSON.parse(el.textContent || '{}'); } catch (_) { return {}; }
}

class ChipPicker {
    constructor(containerId, options, onChange) {
        this.root = document.getElementById(containerId);
        if (!this.root) return;
        this.options = options || [];
        this.selected = new Set();
        this.onChange = onChange;
        this.input = document.createElement('input');
        this.input.type = 'text';
        this.input.className = 'rb-chip-input form-control';
        this.input.placeholder = 'Type and press Enter…';
        this.chipsEl = document.createElement('div');
        this.chipsEl.className = 'rb-chip-list';
        this.suggestionsEl = document.createElement('div');
        this.suggestionsEl.className = 'rb-chip-suggestions hidden';
        this.root.innerHTML = '';
        this.root.appendChild(this.chipsEl);
        this.root.appendChild(this.input);
        this.root.appendChild(this.suggestionsEl);
        this.input.addEventListener('input', () => this.renderSuggestions());
        this.input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                this.addValue(this.input.value.trim());
                this.input.value = '';
                this.renderSuggestions();
            }
        });
        this.input.addEventListener('focus', () => this.renderSuggestions());
        this.input.addEventListener('blur', () => {
            setTimeout(() => this.suggestionsEl.classList.add('hidden'), 150);
        });
    }

    setOptions(options) {
        this.options = options || [];
        this.renderSuggestions();
    }

    setValues(values) {
        this.selected = new Set((values || []).filter(Boolean));
        this.render();
    }

    getValues() {
        return Array.from(this.selected);
    }

    addValue(value) {
        if (!value) return;
        this.selected.add(value);
        this.render();
        this.onChange?.();
    }

    removeValue(value) {
        this.selected.delete(value);
        this.render();
        this.onChange?.();
    }

    render() {
        if (!this.chipsEl) return;
        this.chipsEl.innerHTML = '';
        this.getValues().forEach((value) => {
            const chip = document.createElement('button');
            chip.type = 'button';
            chip.className = 'rb-chip';
            chip.innerHTML = '<span>' + value + '</span><i class="fas fa-times" aria-hidden="true"></i>';
            chip.addEventListener('click', () => this.removeValue(value));
            this.chipsEl.appendChild(chip);
        });
    }

    renderSuggestions() {
        if (!this.suggestionsEl) return;
        const query = (this.input.value || '').trim().toLowerCase();
        const available = this.options.filter((opt) => {
            return !this.selected.has(opt) && (!query || opt.toLowerCase().includes(query));
        }).slice(0, 8);
        this.suggestionsEl.innerHTML = '';
        if (!available.length) {
            this.suggestionsEl.classList.add('hidden');
            return;
        }
        available.forEach((value) => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'rb-chip-suggestion';
            btn.textContent = value;
            btn.addEventListener('mousedown', (e) => {
                e.preventDefault();
                this.addValue(value);
                this.input.value = '';
            });
            this.suggestionsEl.appendChild(btn);
        });
        this.suggestionsEl.classList.remove('hidden');
    }
}

class ReportBuilder {
    constructor(config) {
        this.config = config;
        this.definition = JSON.parse(JSON.stringify(config.definition || { schema_version: 1, filters: {}, sections: [] }));
        if (!this.definition.filters) this.definition.filters = {};
        if (!this.definition.sections) this.definition.sections = [];
        this.selectedSectionId = this.definition.sections[0]?.id || null;
        this.selectedWidgetId = null;
        this.selectedDynamicIndicatorId = null;
        this.activeInspectorTab = 'setup';
        this._sectionRuleCounts = {};
        this._sectionRuleMatches = {};
        this.editorCanvas = new EditorCanvas(this);
        this.metadataBase = (config.apiBase || '').replace(/\/api\/?$/, '') + '/api/metadata';
        this._indicatorCatalog = [];
        this._indicatorCatalogTemplateId = null;
        this._indicatorSearchQuery = '';
        this._ruleFieldOptions = { related_programmes: [], tags: [] };
        this._chipPickers = {};
        this.bindUi();
        this.initChipPickers();
        this.loadTemplates();
        this.loadRuleFieldOptions().then(async () => {
            for (const section of this.definition.sections) {
                if (section.dynamic_indicators?.enabled) {
                    await this.prefetchSectionMatches(section);
                }
            }
            this.renderEditor();
            this.renderPropertiesPanel();
            this.updateEditorHints();
            if (this.selectedSectionId) {
                this.setInspectorTab('section');
                this.refreshSectionRuleSummary();
            }
        });
    }

    initChipPickers() {
        const onSectionChange = () => {
            this.syncSectionFromForm();
            delete this._sectionRuleMatches[this.getSelectedSection()?.id || ''];
            this.refreshSectionRuleSummary();
        };
        const onWidgetChange = () => {
            this.syncWidgetFromForm();
            this.previewWidgetRule(true);
        };
        this._chipPickers.sectionProgrammes = new ChipPicker('rb-section-programmes-picker', [], onSectionChange);
        this._chipPickers.sectionTags = new ChipPicker('rb-section-tags-picker', [], onSectionChange);
        this._chipPickers.widgetProgrammes = new ChipPicker('rb-widget-programmes-picker', [], onWidgetChange);
        this._chipPickers.widgetTags = new ChipPicker('rb-widget-tags-picker', [], onWidgetChange);
    }

    bindUi() {
        document.getElementById('rb-add-section')?.addEventListener('click', () => this.addSection());
        document.getElementById('rb-delete-section')?.addEventListener('click', () => this.deleteSection());
        document.getElementById('rb-save')?.addEventListener('click', () => this.save());
        document.getElementById('rb-publish')?.addEventListener('click', () => this.publish());
        document.getElementById('rb-refresh-data')?.addEventListener('click', () => this.refreshPreviewData());
        document.getElementById('rb-refresh-data-toolbar')?.addEventListener('click', () => this.refreshPreviewData());
        document.getElementById('rb-preview-widget')?.addEventListener('click', () => this.refreshSelectedWidgetPreview());
        document.getElementById('rb-delete-widget')?.addEventListener('click', () => this.deleteWidget());
        document.getElementById('rb-template')?.addEventListener('change', (e) => this.onTemplateChange(e.target.value));
        document.getElementById('rb-title')?.addEventListener('input', () => this.updateEditorHints());
        document.getElementById('rb-description')?.addEventListener('input', () => {});
        document.querySelectorAll('[data-widget-type]').forEach(function (btn) {
            btn.addEventListener('click', () => this.addWidget(btn.dataset.widgetType));
        }.bind(this));
        document.querySelectorAll('[data-inspector-tab]').forEach(function (btn) {
            btn.addEventListener('click', () => this.setInspectorTab(btn.dataset.inspectorTab));
        }.bind(this));
        document.getElementById('rb-section-title')?.addEventListener('input', () => this.syncSectionFromForm(false));
        document.querySelectorAll('input[name="rb-section-mode"]').forEach(function (radio) {
            radio.addEventListener('change', () => {
                this.syncSectionFromForm();
                this.renderSectionForm();
                this.refreshSectionRuleSummary();
            });
        }.bind(this));
        document.getElementById('rb-widget-title')?.addEventListener('input', () => this.syncWidgetFromForm());
        document.getElementById('rb-widget-kind')?.addEventListener('change', () => {
            this.syncWidgetFromForm();
            this.renderWidgetForm();
        });
        document.getElementById('rb-indicator-id')?.addEventListener('change', () => this.syncWidgetFromForm());
        document.getElementById('rb-widget-metric')?.addEventListener('change', () => this.syncWidgetFromForm());
        document.getElementById('rb-widget-content')?.addEventListener('input', () => this.syncWidgetFromForm());
        this._debouncedIndicatorSearch = debounce(function (value) {
            this._indicatorSearchQuery = value || '';
            this.renderIndicatorOptions(this.getSelectedWidget()?.data_source?.indicator_bank_id || null);
        }.bind(this), 200);
        document.getElementById('rb-indicator-search')?.addEventListener('input', (e) => {
            this._debouncedIndicatorSearch(e.target.value);
        });
        document.getElementById('rb-indicator-clear')?.addEventListener('click', () => {
            const select = document.getElementById('rb-indicator-id');
            const search = document.getElementById('rb-indicator-search');
            if (select) select.value = '';
            if (search) search.value = '';
            this._indicatorSearchQuery = '';
            this.syncWidgetFromForm();
            this.renderIndicatorOptions(null);
        });
        document.getElementById('rb-indicator-mode')?.addEventListener('change', () => {
            this.syncWidgetFromForm();
            this.updateIndicatorModePanels();
        });
        document.getElementById('rb-section-dynamic-widget-type')?.addEventListener('change', () => this.syncSectionFromForm());
        document.getElementById('rb-section-dynamic-group-by')?.addEventListener('change', () => {
            this.syncSectionFromForm();
            this.refreshSectionRuleSummary();
        });
        document.getElementById('rb-section-footnote')?.addEventListener('input', () => this.syncSectionFromForm());
        document.getElementById('rb-section-include-bank-guidance')?.addEventListener('change', () => {
            this.syncSectionFromForm();
            this.editorCanvas.invalidateCache();
        });
        document.getElementById('rb-widget-footnote')?.addEventListener('input', () => this.syncWidgetFromForm());
        document.getElementById('rb-statuses')?.addEventListener('change', () => {
            this.syncFiltersFromForm();
            this.editorCanvas.invalidateCache();
            this.renderEditor();
        });
        document.getElementById('rb-period')?.addEventListener('change', () => {
            this.syncFiltersFromForm();
            this.editorCanvas.invalidateCache();
            this.renderEditor();
        });
    }

    setInspectorTab(tab) {
        this.activeInspectorTab = tab;
        document.querySelectorAll('.report-inspector-tab').forEach(function (btn) {
            btn.classList.toggle('is-active', btn.dataset.inspectorTab === tab);
        });
        document.getElementById('rb-inspector-setup')?.classList.toggle('is-active', tab === 'setup');
        document.getElementById('rb-inspector-section')?.classList.toggle('is-active', tab === 'section');
        document.getElementById('rb-inspector-widget')?.classList.toggle('is-active', tab === 'widget');
    }

    renderEditor() {
        return this.editorCanvas.render();
    }

    renderSections() {
        return this.renderEditor();
    }

    async loadTemplates() {
        const res = await fetch(this.metadataBase + '/templates');
        const data = await res.json();
        const select = document.getElementById('rb-template');
        if (!select) return;
        (data.templates || []).forEach(function (t) {
            const opt = document.createElement('option');
            opt.value = t.id;
            opt.textContent = t.name;
            select.appendChild(opt);
        });
        const tpl = (this.definition.filters.template_ids || [])[0];
        if (tpl) {
            select.value = String(tpl);
            await this.onTemplateChange(String(tpl));
            this.restoreFilterSelections();
        }
    }

    restoreFilterSelections() {
        const f = this.definition.filters || {};
        const periodSelect = document.getElementById('rb-period');
        if (periodSelect && f.period_names?.length) {
            Array.from(periodSelect.options).forEach(function (opt) {
                opt.selected = f.period_names.includes(opt.value);
            });
        }
        const statusSelect = document.getElementById('rb-statuses');
        if (statusSelect && f.assignment_statuses?.length) {
            Array.from(statusSelect.options).forEach(function (opt) {
                opt.selected = f.assignment_statuses.includes(opt.value);
            });
        }
    }

    async onTemplateChange(templateId) {
        this.definition.filters.template_ids = templateId ? [Number(templateId)] : [];
        this._indicatorCatalog = [];
        this._indicatorCatalogTemplateId = null;
        const periodSelect = document.getElementById('rb-period');
        if (!periodSelect || !templateId) return;
        const res = await fetch(this.metadataBase + '/periods?template_id=' + encodeURIComponent(templateId));
        const data = await res.json();
        periodSelect.innerHTML = '';
        (data.periods || []).forEach(function (p) {
            const opt = document.createElement('option');
            opt.value = p;
            opt.textContent = p;
            periodSelect.appendChild(opt);
        });
        const widget = this.getSelectedWidget();
        if (widget && this.widgetNeedsIndicator(widget)) {
            await this.refreshIndicatorPicker(widget.data_source?.indicator_bank_id || null);
        }
    }

    getSelectedTemplateId() {
        const select = document.getElementById('rb-template');
        const fromSelect = select?.value ? Number(select.value) : null;
        if (fromSelect) return fromSelect;
        const fromDefinition = (this.definition.filters?.template_ids || [])[0];
        return fromDefinition ? Number(fromDefinition) : null;
    }

    widgetNeedsIndicator(widget) {
        if (!widget || widget.type === 'text') return false;
        if (widget.type === 'indicator_dashboard') return true;
        const kind = widget.data_source?.kind;
        return !!kind && INDICATOR_DATA_SOURCE_KINDS.has(kind);
    }

    setIndicatorHint(message) {
        const hint = document.getElementById('rb-indicator-hint');
        if (hint) hint.textContent = message;
    }

    async loadIndicatorCatalog(templateId, selectedId) {
        if (!templateId) {
            this._indicatorCatalog = [];
            this._indicatorCatalogTemplateId = null;
            return [];
        }
        if (this._indicatorCatalogTemplateId === templateId && this._indicatorCatalog.length) {
            return this._indicatorCatalog;
        }
        const res = await fetch(this.metadataBase + '/indicators?template_id=' + encodeURIComponent(templateId));
        const data = await res.json();
        this._indicatorCatalog = data.indicators || [];
        this._indicatorCatalogTemplateId = templateId;
        return this._indicatorCatalog;
    }

    renderIndicatorOptions(selectedId) {
        const select = document.getElementById('rb-indicator-id');
        const clearBtn = document.getElementById('rb-indicator-clear');
        if (!select) return;
        const query = (this._indicatorSearchQuery || '').trim().toLowerCase();
        const rows = (this._indicatorCatalog || []).filter(function (row) {
            if (!query) return true;
            const haystack = [row.display, row.name, row.type, row.unit].filter(Boolean).join(' ').toLowerCase();
            return haystack.includes(query);
        });
        select.innerHTML = '';
        if (!this.getSelectedTemplateId()) {
            this.setIndicatorHint('Choose a form template under Setup first.');
            clearBtn?.classList.add('hidden');
            return;
        }
        if (!rows.length) {
            this.setIndicatorHint(query ? 'No indicators match your search.' : 'No indicator fields on this template.');
        } else {
            this.setIndicatorHint(rows.length + ' indicator' + (rows.length === 1 ? '' : 's') + ' available.');
        }
        rows.forEach(function (row) {
            const opt = document.createElement('option');
            opt.value = String(row.id);
            let text = row.display || row.name || ('Indicator ' + row.id);
            if (row.type || row.unit) text += ' (' + [row.type, row.unit].filter(Boolean).join(' · ') + ')';
            opt.textContent = text;
            if (selectedId && Number(row.id) === Number(selectedId)) opt.selected = true;
            select.appendChild(opt);
        });
        if (selectedId) select.value = String(selectedId);
        clearBtn?.classList.toggle('hidden', !select.value);
    }

    async refreshIndicatorPicker(selectedId) {
        const templateId = this.getSelectedTemplateId();
        if (!this.widgetNeedsIndicator(this.getSelectedWidget())) return;
        await this.loadIndicatorCatalog(templateId, selectedId);
        this.renderIndicatorOptions(selectedId);
    }

    async loadRuleFieldOptions() {
        const res = await fetch(this.metadataBase + '/indicator-rule/fields');
        const data = await res.json().catch(function () { return {}; });
        this._ruleFieldOptions = {
            related_programmes: data.related_programmes || [],
            tags: data.tags || []
        };
        this.populateHiddenRuleSelect('rb-section-rule-programmes', this._ruleFieldOptions.related_programmes);
        this.populateHiddenRuleSelect('rb-section-rule-tags', this._ruleFieldOptions.tags);
        this.populateHiddenRuleSelect('rb-widget-rule-programmes', this._ruleFieldOptions.related_programmes);
        this.populateHiddenRuleSelect('rb-widget-rule-tags', this._ruleFieldOptions.tags);
        this._chipPickers.sectionProgrammes?.setOptions(this._ruleFieldOptions.related_programmes);
        this._chipPickers.sectionTags?.setOptions(this._ruleFieldOptions.tags);
        this._chipPickers.widgetProgrammes?.setOptions(this._ruleFieldOptions.related_programmes);
        this._chipPickers.widgetTags?.setOptions(this._ruleFieldOptions.tags);
    }

    populateHiddenRuleSelect(elementId, values) {
        const select = document.getElementById(elementId);
        if (!select) return;
        select.innerHTML = '';
        (values || []).forEach(function (value) {
            const opt = document.createElement('option');
            opt.value = value;
            opt.textContent = value;
            select.appendChild(opt);
        });
    }

    readRuleFromWidgetForm() {
        return {
            related_programs_any: this._chipPickers.widgetProgrammes?.getValues() || [],
            tags_any: this._chipPickers.widgetTags?.getValues() || []
        };
    }

    readRuleFromSectionForm() {
        return {
            related_programs_any: this._chipPickers.sectionProgrammes?.getValues() || [],
            tags_any: this._chipPickers.sectionTags?.getValues() || []
        };
    }

    updateIndicatorModePanels() {
        const mode = document.getElementById('rb-indicator-mode')?.value || 'manual';
        document.getElementById('rb-indicator-manual-panel')?.classList.toggle('hidden', mode !== 'manual');
        document.getElementById('rb-indicator-rule-panel')?.classList.toggle('hidden', mode !== 'rule');
    }

    async previewRule(rule, resultElementId, options) {
        options = options || {};
        const el = document.getElementById(resultElementId);
        if (el) {
            el.classList.remove('hidden');
            el.textContent = 'Checking matching indicators…';
        }
        const res = await fetch(this.metadataBase + '/indicator-rule/preview', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.config.csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify({
                rule: rule,
                full_list: !!options.full_list,
                sample_limit: options.sample_limit || 8
            })
        });
        const data = await res.json().catch(function () { return {}; });
        const preview = data.preview || {};
        if (!preview.count) {
            if (el) el.textContent = 'No indicators match yet — add a programme or tag above.';
            return preview;
        }
        if (!options.silent && el) {
            const names = (preview.sample || []).slice(0, 3).map(function (row) { return row.name; }).join(', ');
            const suffix = preview.count > 3 ? '…' : '';
            el.textContent = preview.count + ' indicator(s) will be included. Examples: ' + names + suffix;
        }
        return preview;
    }

    async previewWidgetRule(silent) {
        this.syncWidgetFromForm();
        const preview = await this.previewRule(this.readRuleFromWidgetForm(), 'rb-widget-rule-preview-result');
        return preview;
    }

    async refreshSectionRuleSummary() {
        const section = this.getSelectedSection();
        const summary = document.getElementById('rb-section-rule-summary');
        const summaryText = document.getElementById('rb-section-rule-summary-text');
        if (!section?.dynamic_indicators?.enabled) {
            summary?.classList.add('hidden');
            return;
        }
        this.syncSectionFromForm();
        const rule = this.readRuleFromSectionForm();
        if (!rule.related_programs_any.length && !rule.tags_any.length) {
            summary?.classList.add('hidden');
            this._sectionRuleCounts[section.id] = null;
            delete this._sectionRuleMatches[section.id];
            this.renderEditor();
            this.updateEditorHints();
            return;
        }
        const preview = await this.previewRule(rule, 'rb-section-rule-summary-text');
        summary?.classList.remove('hidden');
        this._sectionRuleCounts[section.id] = preview.count || 0;
        if (preview.matches?.length) {
            this._sectionRuleMatches[section.id] = preview.matches;
        } else {
            const fullPreview = await this.previewRule(rule, null, { full_list: true, silent: true });
            this._sectionRuleMatches[section.id] = fullPreview.matches || fullPreview.sample || [];
        }
        await this.renderIndicatorFootnotesEditor(section, preview);
        this.renderEditor();
        this.updateEditorHints();
    }

    async renderIndicatorFootnotesEditor(section, preview) {
        const host = document.getElementById('rb-indicator-footnotes-list');
        if (!host) return;
        const dyn = section.dynamic_indicators || {};
        if (!dyn.enabled) {
            host.innerHTML = '';
            return;
        }
        if (!preview?.count) {
            host.innerHTML = '<p class="report-field-hint">Add programmes or tags above to configure per-indicator footnotes.</p>';
            return;
        }
        let matches = preview.matches || [];
        if (!matches.length) {
            const fullPreview = await this.previewRule(dyn.rule || {}, null, { full_list: true, silent: true });
            matches = fullPreview.matches || fullPreview.sample || [];
        }
        if (!dyn.indicator_footnotes) dyn.indicator_footnotes = {};
        host.innerHTML = '';
        matches.forEach(function (row) {
            const wrap = document.createElement('details');
            wrap.className = 'report-indicator-footnote-item';
            wrap.dataset.indicatorId = String(row.id);
            if ((dyn.indicator_footnotes[String(row.id)] || '').trim()) {
                wrap.open = true;
            }
            const summary = document.createElement('summary');
            summary.textContent = row.name || ('Indicator ' + row.id);
            wrap.appendChild(summary);
            if (row.disaggregation_guidance) {
                const hint = document.createElement('p');
                hint.className = 'report-field-hint';
                hint.textContent = 'Bank guidance: ' + row.disaggregation_guidance;
                wrap.appendChild(hint);
            }
            const textarea = document.createElement('textarea');
            textarea.className = 'form-control';
            textarea.rows = 2;
            textarea.placeholder = 'Custom footnote for this indicator (optional)';
            textarea.value = dyn.indicator_footnotes[String(row.id)] || '';
            textarea.addEventListener('input', function () {
                const value = textarea.value.trim();
                if (value) dyn.indicator_footnotes[String(row.id)] = value;
                else delete dyn.indicator_footnotes[String(row.id)];
                this.renderEditor();
            }.bind(this));
            wrap.appendChild(textarea);
            host.appendChild(wrap);
        }.bind(this));
    }

    getSelectedSection() {
        return this.definition.sections.find(function (s) { return s.id === this.selectedSectionId; }.bind(this)) || null;
    }

    ensureSectionDynamic(section) {
        if (!section.dynamic_indicators) {
            section.dynamic_indicators = {
                enabled: false,
                rule: { related_programs_any: [], tags_any: [] },
                widget_type: 'indicator_dashboard',
                data_source_kind: 'indicator_dashboard',
                metric: 'sum'
            };
        }
        return section.dynamic_indicators;
    }

    async prefetchSectionMatches(section) {
        const dyn = section.dynamic_indicators || {};
        if (!dyn.enabled) return;
        const rule = dyn.rule || {};
        if (!(rule.related_programs_any || []).length && !(rule.tags_any || []).length) return;
        const preview = await this.previewRule(rule, null, { full_list: true, silent: true });
        this._sectionRuleMatches[section.id] = preview.matches || preview.sample || [];
        this._sectionRuleCounts[section.id] = preview.count || 0;
    }

    renderPropertiesPanel() {
        if (this.selectedWidgetId) {
            this.setInspectorTab('widget');
            this.renderWidgetForm();
            return;
        }
        if (this.selectedSectionId || this.selectedDynamicIndicatorId) {
            this.setInspectorTab('section');
        }
        this.renderSectionForm();
        this.updateEditorHints();
    }

    renderSectionForm() {
        const section = this.getSelectedSection();
        const empty = document.getElementById('rb-section-props-empty');
        const form = document.getElementById('rb-section-props-form');
        if (!section) {
            empty?.classList.remove('hidden');
            form?.classList.add('hidden');
            return;
        }
        empty?.classList.add('hidden');
        form?.classList.remove('hidden');
        const dyn = this.ensureSectionDynamic(section);
        document.getElementById('rb-section-title').value = section.title || '';
        const isDynamic = !!dyn.enabled;
        document.querySelectorAll('input[name="rb-section-mode"]').forEach(function (radio) {
            radio.checked = (radio.value === 'dynamic') === isDynamic;
        });
        document.getElementById('rb-section-dynamic-fields')?.classList.toggle('hidden', !isDynamic);
        document.getElementById('rb-section-manual-tools')?.classList.toggle('hidden', isDynamic);
        document.getElementById('rb-section-dynamic-footnotes')?.classList.toggle('hidden', !isDynamic);
        document.getElementById('rb-section-dynamic-widget-type').value = dyn.widget_type || 'indicator_dashboard';
        document.getElementById('rb-section-dynamic-group-by').checked = dyn.group_by === 'spef_section';
        document.getElementById('rb-section-footnote').value = section.footnote || '';
        document.getElementById('rb-section-include-bank-guidance').checked = !!dyn.include_bank_guidance_footnotes;
        this._chipPickers.sectionProgrammes?.setValues(dyn.rule?.related_programs_any || []);
        this._chipPickers.sectionTags?.setValues(dyn.rule?.tags_any || []);
    }

    syncSectionFromForm(rerender) {
        if (rerender === undefined) rerender = true;
        const section = this.getSelectedSection();
        if (!section) return;
        section.title = document.getElementById('rb-section-title')?.value || section.title;
        section.footnote = document.getElementById('rb-section-footnote')?.value || '';
        if (!section.footnote) delete section.footnote;
        const dyn = this.ensureSectionDynamic(section);
        const mode = document.querySelector('input[name="rb-section-mode"]:checked')?.value || 'manual';
        dyn.enabled = mode === 'dynamic';
        dyn.widget_type = document.getElementById('rb-section-dynamic-widget-type')?.value || 'indicator_dashboard';
        dyn.data_source_kind = DYNAMIC_KIND_BY_TYPE[dyn.widget_type] || 'indicator_aggregate';
        dyn.group_by = document.getElementById('rb-section-dynamic-group-by')?.checked ? 'spef_section' : undefined;
        if (!dyn.group_by) delete dyn.group_by;
        dyn.include_bank_guidance_footnotes = !!document.getElementById('rb-section-include-bank-guidance')?.checked;
        if (!dyn.include_bank_guidance_footnotes) delete dyn.include_bank_guidance_footnotes;
        dyn.rule = this.readRuleFromSectionForm();
        if (dyn.indicator_footnotes && !Object.keys(dyn.indicator_footnotes).length) {
            delete dyn.indicator_footnotes;
        }
        document.getElementById('rb-section-dynamic-enabled').checked = dyn.enabled;
        if (rerender) this.renderEditor();
    }

    syncFiltersFromForm() {
        const periodSelect = document.getElementById('rb-period');
        const statusSelect = document.getElementById('rb-statuses');
        this.definition.filters.period_names = periodSelect
            ? Array.from(periodSelect.selectedOptions).map(function (o) { return o.value; })
            : [];
        this.definition.filters.assignment_statuses = statusSelect
            ? Array.from(statusSelect.selectedOptions).map(function (o) { return o.value; })
            : ['submitted', 'approved'];
    }

    addSection() {
        const section = {
            id: uid('sec'),
            title: 'New section',
            order: this.definition.sections.length,
            widgets: []
        };
        this.definition.sections.push(section);
        this.selectedSectionId = section.id;
        this.selectedWidgetId = null;
        this.selectedDynamicIndicatorId = null;
        this.renderEditor();
        this.renderPropertiesPanel();
    }

    deleteSection() {
        const section = this.getSelectedSection();
        if (!section) return;
        if (!window.confirm('Delete this section?')) return;
        this.definition.sections = this.definition.sections.filter(function (s) { return s.id !== section.id; });
        this.selectedSectionId = this.definition.sections[0]?.id || null;
        this.selectedWidgetId = null;
        this.selectedDynamicIndicatorId = null;
        delete this._sectionRuleCounts[section.id];
        delete this._sectionRuleMatches[section.id];
        this.editorCanvas.invalidateCache();
        this.renderEditor();
        this.renderPropertiesPanel();
    }

    insertWidgetAt(sectionId, type, index) {
        const section = this.definition.sections.find(function (s) { return s.id === sectionId; });
        if (!section) return;
        if (section.dynamic_indicators?.enabled) {
            alert('Switch this section to manual widgets to add individual elements.');
            return;
        }
        const kinds = WIDGET_KINDS[type] || [];
        const widget = {
            id: uid('w'),
            type: type,
            title: (WIDGET_TYPE_LABELS[type] || type) + ' widget',
            chart_options: {}
        };
        if (type === 'text') {
            widget.content = '';
        } else {
            widget.data_source = { kind: kinds[0] || 'assignment_status_counts' };
        }
        if (!section.widgets) section.widgets = [];
        const insertAt = Math.max(0, Math.min(index, section.widgets.length));
        section.widgets.splice(insertAt, 0, widget);
        this.selectedSectionId = section.id;
        this.selectedWidgetId = widget.id;
        this.selectedDynamicIndicatorId = null;
        this.renderEditor();
        this.renderPropertiesPanel();
    }

    addWidget(type) {
        const section = this.getSelectedSection();
        if (!section) {
            alert('Select a section first.');
            return;
        }
        this.insertWidgetAt(section.id, type, (section.widgets || []).length);
    }

    deleteWidget() {
        if (!this.selectedWidgetId) return;
        this.deleteWidgetById(this.selectedWidgetId);
    }

    deleteWidgetById(widgetId) {
        const section = this.definition.sections.find(function (s) {
            return s.widgets.some(function (w) { return w.id === widgetId; });
        });
        if (!section) return;
        section.widgets = section.widgets.filter(function (w) { return w.id !== widgetId; });
        this.editorCanvas.invalidateCache(widgetId);
        this.selectedWidgetId = null;
        this.renderEditor();
        this.renderPropertiesPanel();
    }

    getSelectedWidget() {
        for (const section of this.definition.sections) {
            const w = section.widgets.find(function (x) { return x.id === this.selectedWidgetId; }.bind(this));
            if (w) return w;
        }
        return null;
    }

    describeSection(section) {
        if (section.dynamic_indicators?.enabled) {
            const programmes = (section.dynamic_indicators.rule?.related_programs_any || []).join(', ');
            const count = this._sectionRuleCounts[section.id];
            const countLabel = count != null ? count + ' indicators' : 'Indicator Bank rule';
            const style = WIDGET_TYPE_LABELS[section.dynamic_indicators.widget_type] || section.dynamic_indicators.widget_type;
            const spef = section.dynamic_indicators.group_by === 'spef_section' ? ' · split by SPEF' : '';
            return (programmes ? programmes + ' · ' : '') + countLabel + ' · ' + style + spef;
        }
        const n = (section.widgets || []).length;
        return n ? n + ' manual widget' + (n === 1 ? '' : 's') : 'Empty — add widgets or use an Indicator Bank rule';
    }

    focusDynamicIndicatorFootnote(indicatorId) {
        this.setInspectorTab('section');
        const item = document.querySelector('#rb-indicator-footnotes-list [data-indicator-id="' + indicatorId + '"]');
        if (item) {
            item.open = true;
            item.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
            item.querySelector('textarea')?.focus();
        }
    }

    renderWidgetForm() {
        const empty = document.getElementById('rb-widget-props-empty');
        const form = document.getElementById('rb-widget-props-form');
        const widget = this.getSelectedWidget();
        if (!widget) {
            empty?.classList.remove('hidden');
            form?.classList.add('hidden');
            return;
        }
        empty?.classList.add('hidden');
        form?.classList.remove('hidden');
        document.getElementById('rb-widget-title').value = widget.title || '';
        document.getElementById('rb-widget-footnote').value = widget.footnote || '';
        const kindSelect = document.getElementById('rb-widget-kind');
        kindSelect.innerHTML = '';
        const kinds = WIDGET_KINDS[widget.type] || ['assignment_status_counts'];
        kinds.forEach(function (k) {
            const opt = document.createElement('option');
            opt.value = k;
            opt.textContent = DATA_SOURCE_LABELS[k] || k;
            if (widget.data_source?.kind === k) opt.selected = true;
            kindSelect.appendChild(opt);
        });
        document.getElementById('rb-widget-metric').value = widget.data_source?.metric || 'sum';
        document.getElementById('rb-widget-content').value = widget.content || '';
        document.querySelector('.rb-text-field')?.classList.toggle('hidden', widget.type !== 'text');
        const needsIndicator = this.widgetNeedsIndicator(widget);
        document.querySelector('.rb-indicator-field')?.classList.toggle('hidden', !needsIndicator);
        document.querySelector('.rb-metric-field')?.classList.toggle('hidden', !['bar', 'kpi', 'table'].includes(widget.type) || !needsIndicator);
        if (needsIndicator) {
            const selection = widget.data_source?.indicator_selection || { mode: 'manual' };
            document.getElementById('rb-indicator-mode').value = selection.mode || 'manual';
            this.updateIndicatorModePanels();
            if ((selection.mode || 'manual') === 'rule') {
                this._chipPickers.widgetProgrammes?.setValues(selection.rule?.related_programs_any || []);
                this._chipPickers.widgetTags?.setValues(selection.rule?.tags_any || []);
            } else {
                this._indicatorSearchQuery = '';
                const search = document.getElementById('rb-indicator-search');
                if (search) search.value = '';
                this.refreshIndicatorPicker(widget.data_source?.indicator_bank_id || null);
            }
        }
    }

    syncWidgetFromForm(rerender) {
        if (rerender === undefined) rerender = true;
        const widget = this.getSelectedWidget();
        if (!widget) return;
        widget.title = document.getElementById('rb-widget-title').value;
        widget.footnote = document.getElementById('rb-widget-footnote')?.value || '';
        if (!widget.footnote) delete widget.footnote;
        if (widget.type === 'text') {
            widget.content = document.getElementById('rb-widget-content').value;
            if (rerender) this.renderEditor();
            return;
        }
        if (!widget.data_source) widget.data_source = {};
        widget.data_source.kind = document.getElementById('rb-widget-kind').value;
        if (this.widgetNeedsIndicator(widget)) {
            widget.data_source.metric = document.getElementById('rb-widget-metric').value;
            const mode = document.getElementById('rb-indicator-mode')?.value || 'manual';
            if (mode === 'rule') {
                widget.data_source.indicator_selection = {
                    mode: 'rule',
                    rule: this.readRuleFromWidgetForm()
                };
                delete widget.data_source.indicator_bank_id;
                delete widget.data_source.indicator_bank_ids;
            } else {
                widget.data_source.indicator_selection = { mode: 'manual' };
                const ind = document.getElementById('rb-indicator-id').value;
                widget.data_source.indicator_bank_id = ind ? Number(ind) : null;
            }
        } else {
            delete widget.data_source.indicator_bank_id;
            delete widget.data_source.indicator_bank_ids;
            delete widget.data_source.indicator_selection;
        }
        if (rerender) {
            this.editorCanvas.invalidateCache(widget.id);
            this.renderEditor();
        }
    }

    updateEditorHints() {
        const section = this.getSelectedSection();
        const widget = this.getSelectedWidget();
        const hint = document.getElementById('rb-editor-hint');
        if (!hint) return;
        if (widget) {
            hint.textContent = 'Editing widget: ' + (widget.title || widget.type) + '.';
        } else if (this.selectedDynamicIndicatorId && section) {
            hint.textContent = 'Editing indicator footnote in section “' + (section.title || 'Untitled') + '”.';
        } else if (section?.dynamic_indicators?.enabled) {
            const count = this._sectionRuleCounts[section.id];
            hint.textContent = count != null
                ? 'Live preview — ' + count + ' indicator(s). Click one to edit its footnote.'
                : 'Configure programmes/tags in the Section panel to list indicators here.';
        } else if (section) {
            hint.textContent = 'Editing section “' + (section.title || 'Untitled') + '”. Use + slots to add elements.';
        } else {
            hint.textContent = 'Live preview of your report. Click elements to configure them, or use + slots to add widgets.';
        }
    }

    async refreshPreviewData() {
        await this.editorCanvas.refreshAllPreviews();
    }

    async refreshSelectedWidgetPreview() {
        const widget = this.getSelectedWidget();
        if (widget) {
            this.editorCanvas.invalidateCache(widget.id);
            await this.renderEditor();
            return;
        }
        if (this.selectedDynamicIndicatorId && this.selectedSectionId) {
            const widgetId = dynamicWidgetId(this.selectedSectionId, this.selectedDynamicIndicatorId);
            this.editorCanvas.invalidateCache(widgetId);
            await this.renderEditor();
        }
    }

    async ensureSaved() {
        if (this.config.reportId) return this.config.reportId;
        await this.save();
        return this.config.reportId;
    }

    normalizeDefinitionBeforeSave() {
        this.syncFiltersFromForm();
        this.syncSectionFromForm(false);
        this.syncWidgetFromForm(false);
        if (!this.definition.schema_version) this.definition.schema_version = 1;
        const f = this.definition.filters || (this.definition.filters = {});
        if (!Array.isArray(f.template_ids)) f.template_ids = [];
        if (!Array.isArray(f.period_names)) f.period_names = [];
        if (!Array.isArray(f.country_ids)) f.country_ids = [];
        if (!Array.isArray(f.assignment_statuses)) f.assignment_statuses = ['submitted', 'approved'];
        if (f.include_public_submissions == null) f.include_public_submissions = false;
        (this.definition.sections || []).forEach(function (section, idx) {
            section.order = idx;
            if (section.dynamic_indicators && !section.dynamic_indicators.enabled) {
                delete section.dynamic_indicators;
            } else if (section.dynamic_indicators?.enabled) {
                const dyn = section.dynamic_indicators;
                if (!dyn.include_bank_guidance_footnotes) delete dyn.include_bank_guidance_footnotes;
                if (!dyn.indicator_footnotes || !Object.keys(dyn.indicator_footnotes).length) {
                    delete dyn.indicator_footnotes;
                }
            }
            if (!section.footnote) delete section.footnote;
            (section.widgets || []).forEach(function (widget) {
                if (widget.type !== 'text') {
                    widget.data_source = widget.data_source || { kind: 'assignment_status_counts' };
                    const selection = widget.data_source.indicator_selection;
                    if (selection?.mode === 'rule') {
                        delete widget.data_source.indicator_bank_id;
                        delete widget.data_source.indicator_bank_ids;
                    } else if (widget.data_source.indicator_bank_id == null) {
                        delete widget.data_source.indicator_bank_id;
                    }
                    widget.chart_options = widget.chart_options || {};
                }
                if (!widget.footnote) delete widget.footnote;
            });
        });
    }

    buildPayload() {
        this.normalizeDefinitionBeforeSave();
        return {
            title: document.getElementById('rb-title')?.value || 'Untitled report',
            description: document.getElementById('rb-description')?.value || '',
            definition: this.definition
        };
    }

    async save() {
        const payload = this.buildPayload();
        const url = this.config.reportId
            ? this.config.apiBase + '/' + this.config.reportId
            : this.config.apiBase;
        const method = this.config.reportId ? 'PUT' : 'POST';
        const res = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.config.csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify(payload)
        });
        const data = await res.json().catch(function () { return {}; });
        if (!res.ok) {
            alert(data.error || data.message || 'Save failed');
            throw new Error(data.error || 'Save failed');
        }
        if (!this.config.reportId && data.report?.id) {
            this.config.reportId = data.report.id;
            const editUrl = this.config.apiBase.replace('/api', '') + '/' + data.report.id + '/edit';
            window.history.replaceState({}, '', editUrl);
        }
        const statusEl = document.getElementById('rb-save-status');
        if (statusEl) {
            statusEl.textContent = 'Saved';
            setTimeout(function () { statusEl.textContent = ''; }, 2500);
        }
    }

    async publish() {
        await this.save();
        if (!this.config.reportId) return;
        const statusRes = await fetch(this.config.apiBase + '/' + this.config.reportId, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.config.csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify({ status: 'published' })
        });
        const statusData = await statusRes.json().catch(function () { return {}; });
        if (!statusRes.ok) {
            alert(statusData.error || statusData.message || 'Publish failed');
            return;
        }
        await fetch(this.config.apiBase + '/' + this.config.reportId + '/publish', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.config.csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: '{}'
        });
    }
}

document.addEventListener('DOMContentLoaded', function () {
    new ReportBuilder(readBootstrap());
});
