/**
 * WYSIWYG report editor canvas — dotted slots, insert menus, dynamic indicator previews.
 */
import { renderWidget, appendSectionFootnote } from '../widget-renderer.js';

const INSERT_TYPES = [
    { type: 'indicator_dashboard', label: 'Dashboard', icon: 'fa-chart-area' },
    { type: 'kpi', label: 'KPI', icon: 'fa-hashtag' },
    { type: 'line', label: 'Line chart', icon: 'fa-chart-line' },
    { type: 'bar', label: 'Bar chart', icon: 'fa-chart-bar' },
    { type: 'pie', label: 'Pie chart', icon: 'fa-chart-pie' },
    { type: 'table', label: 'Table', icon: 'fa-table' },
    { type: 'text', label: 'Text block', icon: 'fa-align-left' }
];

const TYPE_LABELS = {
    indicator_dashboard: 'Dashboard',
    kpi: 'KPI',
    line: 'Line chart',
    bar: 'Bar chart',
    pie: 'Pie chart',
    table: 'Table',
    text: 'Text'
};

function groupIndicatorsBySpef(indicators) {
    const groups = new Map();
    (indicators || []).forEach(function (row) {
        const code = (row.spef_code || 'UNASSIGNED').toUpperCase();
        if (!groups.has(code)) {
            groups.set(code, {
                code: code,
                name: row.spef_name || code,
                indicators: []
            });
        }
        groups.get(code).indicators.push(row);
    });
    return Array.from(groups.values());
}

function dynamicWidgetId(sectionId, indicatorId) {
    return sectionId + '-dyn-' + indicatorId;
}

export class EditorCanvas {
    constructor(builder) {
        this.builder = builder;
        this._openMenu = null;
        this._loadingWidgets = new Set();
        this._slotPayloadCache = {};
        document.addEventListener('click', (e) => {
            if (this._openMenu && !e.target.closest('.rb-editor-insert-menu')) {
                this.closeMenus();
            }
        });
    }

    get host() {
        return document.getElementById('rb-editor-canvas');
    }

    closeMenus() {
        if (this._openMenu) {
            this._openMenu.remove();
            this._openMenu = null;
        }
    }

    invalidateCache(widgetId) {
        if (widgetId) delete this._slotPayloadCache[widgetId];
        else this._slotPayloadCache = {};
    }

    async render() {
        const host = this.host;
        if (!host) return;
        this.closeMenus();
        host.innerHTML = '';
        const sections = this.builder.definition.sections || [];
        if (!sections.length) {
            host.appendChild(this.createEmptyState());
            return;
        }
        for (let index = 0; index < sections.length; index += 1) {
            host.appendChild(await this.renderSectionBlock(sections[index], index));
        }
        host.appendChild(this.createAddSectionSlot());
        void this.autoLoadAllPreviews();
    }

    collectPreviewJobs() {
        const host = this.host;
        if (!host) return [];
        const jobs = [];
        host.querySelectorAll('.rb-editor-slot[data-widget-id]').forEach(function (slot) {
            if (slot.dataset.skipPreview === 'true') return;
            const widgetId = slot.dataset.widgetId;
            const preview = slot.querySelector('.rb-editor-slot-preview');
            if (!widgetId || !preview) return;
            jobs.push({
                widgetId: widgetId,
                preview: preview,
                titleEl: slot.querySelector('.report-widget-card-title') || null
            });
        });
        return jobs;
    }

    async autoLoadAllPreviews() {
        const jobs = this.collectPreviewJobs().filter(function (job) {
            return !this._slotPayloadCache[job.widgetId] && !this._loadingWidgets.has(job.widgetId);
        }.bind(this));
        if (!jobs.length) return;
        try {
            await this.builder.ensureSaved();
        } catch (_) {
            return;
        }
        await this.runPreviewPool(jobs, 4);
    }

    async runPreviewPool(jobs, concurrency) {
        let index = 0;
        const worker = async function () {
            while (index < jobs.length) {
                const job = jobs[index];
                index += 1;
                await this.loadWidgetPreview(job.widgetId, job.preview, job.titleEl);
            }
        }.bind(this);
        const workers = [];
        for (let i = 0; i < Math.min(concurrency, jobs.length); i += 1) {
            workers.push(worker());
        }
        await Promise.all(workers);
    }

    createEmptyState() {
        const wrap = document.createElement('div');
        wrap.className = 'rb-editor-empty';
        wrap.innerHTML = '<i class="fas fa-file-alt" aria-hidden="true"></i><p>Your report is empty. Add a section to begin building.</p>';
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn btn-secondary rb-editor-add-section-btn';
        btn.innerHTML = '<i class="fas fa-plus" aria-hidden="true"></i> Add section';
        btn.addEventListener('click', () => this.builder.addSection());
        wrap.appendChild(btn);
        return wrap;
    }

    createAddSectionSlot() {
        const slot = document.createElement('button');
        slot.type = 'button';
        slot.className = 'rb-editor-add-section-slot';
        slot.innerHTML = '<i class="fas fa-plus" aria-hidden="true"></i><span>Add section</span>';
        slot.addEventListener('click', () => this.builder.addSection());
        return slot;
    }

    isSectionSelected(sectionId) {
        return this.builder.selectedSectionId === sectionId && !this.builder.selectedWidgetId && !this.builder.selectedDynamicIndicatorId;
    }

    isWidgetSelected(widgetId) {
        return this.builder.selectedWidgetId === widgetId;
    }

    isDynamicSelected(sectionId, indicatorId) {
        return this.builder.selectedSectionId === sectionId
            && this.builder.selectedDynamicIndicatorId === indicatorId;
    }

    selectSection(sectionId) {
        this.builder.selectedSectionId = sectionId;
        this.builder.selectedWidgetId = null;
        this.builder.selectedDynamicIndicatorId = null;
        this.builder.renderEditor();
        this.builder.renderPropertiesPanel();
    }

    selectWidget(sectionId, widgetId) {
        this.builder.selectedSectionId = sectionId;
        this.builder.selectedWidgetId = widgetId;
        this.builder.selectedDynamicIndicatorId = null;
        this.builder.renderEditor();
        this.builder.renderPropertiesPanel();
    }

    selectDynamicIndicator(sectionId, indicatorId) {
        this.builder.selectedSectionId = sectionId;
        this.builder.selectedWidgetId = null;
        this.builder.selectedDynamicIndicatorId = indicatorId;
        this.builder.renderEditor();
        this.builder.renderPropertiesPanel();
        this.builder.focusDynamicIndicatorFootnote(indicatorId);
    }

    async renderSectionBlock(section, index) {
        const block = document.createElement('section');
        block.className = 'report-section rb-editor-section'
            + (this.isSectionSelected(section.id) ? ' is-selected' : '');
        block.dataset.sectionId = section.id;

        block.appendChild(this.createSectionHeader(section, index));

        const body = document.createElement('div');
        body.className = 'rb-editor-section-body';

        const dyn = section.dynamic_indicators || {};
        if (dyn.enabled) {
            await this.renderDynamicSection(section, body);
        } else {
            this.renderManualSection(section, body);
        }

        if (section.footnote) {
            body.appendChild(this.createFootnotePreview(section.footnote, 'section'));
        } else {
            body.appendChild(this.createFootnotePlaceholder(section));
        }

        block.appendChild(body);
        block.addEventListener('click', (e) => {
            if (e.target.closest('.rb-editor-slot, .rb-editor-insert-slot, .rb-editor-insert-menu, .rb-editor-section-title, button')) return;
            this.selectSection(section.id);
        });
        return block;
    }

    createSectionHeader(section, index) {
        const head = document.createElement('div');
        head.className = 'rb-editor-section-header';

        const title = document.createElement('input');
        title.type = 'text';
        title.className = 'rb-editor-section-title';
        title.value = section.title || 'Untitled section';
        title.placeholder = 'Section title';
        title.addEventListener('click', (e) => e.stopPropagation());
        title.addEventListener('input', () => {
            section.title = title.value;
            const inspectorTitle = document.getElementById('rb-section-title');
            if (inspectorTitle && inspectorTitle.value !== title.value) inspectorTitle.value = title.value;
        });
        title.addEventListener('focus', () => this.selectSection(section.id));

        const meta = document.createElement('span');
        meta.className = 'rb-editor-section-meta';
        meta.textContent = this.builder.describeSection(section);

        head.appendChild(title);
        head.appendChild(meta);
        return head;
    }

    async renderDynamicSection(section, body) {
        const dyn = section.dynamic_indicators || {};
        const rule = dyn.rule || {};
        const hasRule = (rule.related_programs_any || []).length || (rule.tags_any || []).length;

        if (!hasRule) {
            body.appendChild(this.createConfigPrompt(
                'Configure programmes or tags in the Section panel to list matching indicators here.'
            ));
            return;
        }

        let matches = this.builder._sectionRuleMatches[section.id];
        if (!matches) {
            body.appendChild(this.createLoadingRow('Loading indicators…'));
            const preview = await this.builder.previewRule(rule, null, { full_list: true, silent: true });
            matches = preview.matches || preview.sample || [];
            this.builder._sectionRuleMatches[section.id] = matches;
            this.builder._sectionRuleCounts[section.id] = preview.count || matches.length;
            body.innerHTML = '';
        }

        if (!matches.length) {
            body.appendChild(this.createConfigPrompt('No indicators match the current rule.'));
            return;
        }

        const widgetType = dyn.widget_type || 'indicator_dashboard';
        const badge = document.createElement('div');
        badge.className = 'rb-editor-dynamic-badge';
        badge.innerHTML = '<i class="fas fa-magic" aria-hidden="true"></i> Auto-generated · '
            + matches.length + ' indicator' + (matches.length === 1 ? '' : 's')
            + ' · ' + (TYPE_LABELS[widgetType] || widgetType);
        body.appendChild(badge);

        if (dyn.group_by === 'spef_section') {
            const groups = groupIndicatorsBySpef(matches);
            groups.forEach((group) => {
                const sub = document.createElement('div');
                sub.className = 'rb-editor-spef-group';
                const subTitle = document.createElement('h3');
                subTitle.className = 'rb-editor-spef-title';
                subTitle.textContent = group.name || group.code;
                sub.appendChild(subTitle);
                group.indicators.forEach((indicator) => {
                    sub.appendChild(this.createDynamicSlot(section, indicator, widgetType));
                });
                body.appendChild(sub);
            });
        } else {
            matches.forEach((indicator) => {
                body.appendChild(this.createDynamicSlot(section, indicator, widgetType));
            });
        }
    }

    renderManualSection(section, body) {
        const widgets = section.widgets || [];
        widgets.forEach((widget, index) => {
            body.appendChild(this.createWidgetSlot(section, widget));
            body.appendChild(this.createInsertSlot(section, index));
        });
        if (!widgets.length) {
            body.appendChild(this.createInsertSlot(section, -1));
        }
    }

    createConfigPrompt(message) {
        const el = document.createElement('div');
        el.className = 'rb-editor-config-prompt';
        el.textContent = message;
        return el;
    }

    createLoadingRow(message) {
        const el = document.createElement('div');
        el.className = 'rb-editor-loading';
        el.innerHTML = '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i> ' + message;
        return el;
    }

    createInsertSlot(section, afterIndex) {
        const slot = document.createElement('button');
        slot.type = 'button';
        slot.className = 'rb-editor-insert-slot';
        slot.title = 'Add element';
        slot.innerHTML = '<i class="fas fa-plus" aria-hidden="true"></i>';
        slot.addEventListener('click', (e) => {
            e.stopPropagation();
            this.showInsertMenu(slot, section, afterIndex);
        });
        return slot;
    }

    showInsertMenu(anchor, section, afterIndex) {
        this.closeMenus();
        const menu = document.createElement('div');
        menu.className = 'rb-editor-insert-menu';
        menu.setAttribute('role', 'menu');
        INSERT_TYPES.forEach((item) => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'rb-editor-insert-option';
            btn.setAttribute('role', 'menuitem');
            btn.innerHTML = '<i class="fas ' + item.icon + '" aria-hidden="true"></i><span>' + item.label + '</span>';
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.closeMenus();
                this.builder.insertWidgetAt(section.id, item.type, afterIndex + 1);
            });
            menu.appendChild(btn);
        });
        anchor.appendChild(menu);
        this._openMenu = menu;
    }

    createWidgetSlot(section, widget) {
        const slot = document.createElement('article');
        slot.className = 'rb-editor-slot rb-editor-slot-widget'
            + (this.isWidgetSelected(widget.id) ? ' is-selected' : '');
        slot.dataset.widgetId = widget.id;

        const toolbar = document.createElement('div');
        toolbar.className = 'rb-editor-slot-toolbar';
        toolbar.innerHTML = '<span class="rb-editor-slot-type">' + (TYPE_LABELS[widget.type] || widget.type) + '</span>'
            + '<button type="button" class="rb-editor-slot-action" title="Delete" data-action="delete"><i class="fas fa-trash" aria-hidden="true"></i></button>';

        const content = document.createElement('div');
        content.className = 'rb-editor-slot-content';

        const preview = document.createElement('div');
        preview.className = 'rb-editor-slot-preview';

        if (widget.type === 'text') {
            slot.dataset.skipPreview = 'true';
            preview.className = 'rb-editor-slot-preview rb-editor-text-preview';
            preview.textContent = widget.content || '';
        } else if (this._slotPayloadCache[widget.id]) {
            renderWidget(preview, this._slotPayloadCache[widget.id]);
        } else {
            preview.appendChild(this.createLoadingRow('Loading…'));
        }
        content.appendChild(preview);

        if (widget.footnote) {
            content.appendChild(this.createFootnotePreview(widget.footnote, 'widget'));
        }

        slot.appendChild(toolbar);
        slot.appendChild(content);

        slot.addEventListener('click', (e) => {
            if (e.target.closest('[data-action]')) return;
            this.selectWidget(section.id, widget.id);
        });

        toolbar.querySelector('[data-action="delete"]')?.addEventListener('click', (e) => {
            e.stopPropagation();
            if (!window.confirm('Delete this widget?')) return;
            this.builder.deleteWidgetById(widget.id);
        });

        return slot;
    }

    createDynamicSlot(section, indicator, widgetType) {
        const widgetId = dynamicWidgetId(section.id, indicator.id);
        const slot = document.createElement('article');
        slot.className = 'rb-editor-slot rb-editor-slot-dynamic'
            + (this.isDynamicSelected(section.id, indicator.id) ? ' is-selected' : '');
        slot.dataset.indicatorId = String(indicator.id);
        slot.dataset.widgetId = widgetId;

        const toolbar = document.createElement('div');
        toolbar.className = 'rb-editor-slot-toolbar';
        toolbar.innerHTML = '<span class="rb-editor-slot-type">' + (TYPE_LABELS[widgetType] || widgetType) + '</span>'
            + '<span class="rb-editor-slot-auto"><i class="fas fa-magic" aria-hidden="true"></i> Auto</span>';

        const content = document.createElement('div');
        content.className = 'rb-editor-slot-content';

        const title = document.createElement('h3');
        title.className = 'report-widget-card-title';
        title.textContent = indicator.name || ('Indicator ' + indicator.id);
        content.appendChild(title);

        const preview = document.createElement('div');
        preview.className = 'rb-editor-slot-preview';

        if (this._slotPayloadCache[widgetId]) {
            renderWidget(preview, this._slotPayloadCache[widgetId]);
        } else {
            preview.appendChild(this.createLoadingRow('Loading…'));
        }
        content.appendChild(preview);

        const dyn = section.dynamic_indicators || {};
        const footnote = (dyn.indicator_footnotes || {})[String(indicator.id)]
            || (dyn.include_bank_guidance_footnotes && indicator.disaggregation_guidance ? indicator.disaggregation_guidance : '');
        if (footnote) {
            content.appendChild(this.createFootnotePreview(footnote, 'widget'));
        }

        slot.appendChild(toolbar);
        slot.appendChild(content);

        slot.addEventListener('click', (e) => {
            if (e.target.closest('[data-action]')) return;
            this.selectDynamicIndicator(section.id, indicator.id);
        });

        return slot;
    }

    createFootnotePreview(text, kind) {
        const el = document.createElement('div');
        el.className = kind === 'section' ? 'report-section-footnote rb-editor-footnote-preview' : 'report-widget-footnote rb-editor-footnote-preview';
        el.textContent = text;
        return el;
    }

    createFootnotePlaceholder(section) {
        const el = document.createElement('button');
        el.type = 'button';
        el.className = 'rb-editor-footnote-slot';
        el.innerHTML = '<i class="fas fa-sticky-note" aria-hidden="true"></i> Add section footnote';
        el.addEventListener('click', (e) => {
            e.stopPropagation();
            this.selectSection(section.id);
            this.builder.setInspectorTab('section');
            document.getElementById('rb-section-footnote')?.focus();
        });
        return el;
    }

    async loadWidgetPreview(widgetId, previewHost, titleEl) {
        if (this._loadingWidgets.has(widgetId)) return;
        if (this._slotPayloadCache[widgetId]) {
            previewHost.innerHTML = '';
            if (titleEl) titleEl.remove();
            await renderWidget(previewHost, this._slotPayloadCache[widgetId]);
            return;
        }
        this._loadingWidgets.add(widgetId);
        previewHost.innerHTML = '';
        previewHost.appendChild(this.createLoadingRow('Loading…'));
        try {
            const reportId = await this.builder.ensureSaved();
            if (!reportId) return;
            const res = await fetch(this.builder.config.apiBase + '/' + reportId + '/widgets/' + encodeURIComponent(widgetId) + '/run', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.builder.config.csrfToken,
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({})
            });
            const data = await res.json().catch(function () { return {}; });
            if (!res.ok) throw new Error(data.error || data.message || 'Preview failed');
            const payload = data.widget || data;
            this._slotPayloadCache[widgetId] = payload;
            previewHost.innerHTML = '';
            if (titleEl) titleEl.remove();
            await renderWidget(previewHost, payload);
        } catch (err) {
            previewHost.innerHTML = '';
            const error = document.createElement('div');
            error.className = 'rb-editor-slot-error';
            error.textContent = err.message || 'Preview failed';
            previewHost.appendChild(error);
        } finally {
            this._loadingWidgets.delete(widgetId);
        }
    }

    async refreshAllPreviews() {
        this.invalidateCache();
        await this.render();
    }
}

export { INSERT_TYPES, TYPE_LABELS, dynamicWidgetId, groupIndicatorsBySpef };
