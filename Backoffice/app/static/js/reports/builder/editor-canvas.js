/**
 * WYSIWYG report editor canvas — GridStack layout + live previews.
 */
import { renderWidget, appendSectionFootnote } from '../widget-renderer.js';
import { GridEngine } from './grid-engine.js';
import { localizedWidget, resolveTranslation } from './v2-compat.js';

const INSERT_TYPES = [
    { type: 'indicator_dashboard', label: 'Dashboard', icon: 'fa-chart-area' },
    { type: 'kpi', label: 'KPI', icon: 'fa-hashtag' },
    { type: 'line', label: 'Line chart', icon: 'fa-chart-line' },
    { type: 'area', label: 'Area chart', icon: 'fa-chart-area' },
    { type: 'bar', label: 'Bar chart', icon: 'fa-chart-bar' },
    { type: 'map', label: 'Map', icon: 'fa-map' },
    { type: 'pie', label: 'Pie chart', icon: 'fa-chart-pie' },
    { type: 'gauge', label: 'Gauge', icon: 'fa-tachometer-alt' },
    { type: 'table', label: 'Table', icon: 'fa-table' },
    { type: 'text', label: 'Text block', icon: 'fa-align-left' },
    { type: 'image', label: 'Image', icon: 'fa-image' },
    { type: 'embed', label: 'Embed', icon: 'fa-code' },
    { type: 'divider', label: 'Divider', icon: 'fa-minus' }
];

function groupIndicatorsBySpef(indicators) {
    const groups = new Map();
    (indicators || []).forEach(function (row) {
        const code = (row.spef_code || 'UNASSIGNED').toUpperCase();
        if (!groups.has(code)) groups.set(code, { code: code, name: row.spef_name || code, indicators: [] });
        groups.get(code).indicators.push(row);
    });
    return Array.from(groups.values());
}

export function dynamicWidgetId(sectionId, indicatorId) {
    return sectionId + '-dyn-' + indicatorId;
}

export class EditorCanvas {
    constructor(builder) {
        this.builder = builder;
        this.gridEngine = new GridEngine({ rtl: builder.activeLanguage === 'ar' });
        this._openMenu = null;
        this._loadingWidgets = new Set();
        this._slotPayloadCache = {};
        document.addEventListener('click', (e) => {
            if (this._openMenu && !e.target.closest('.rb-editor-insert-menu')) this.closeMenus();
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
        this.gridEngine.destroyAll();
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
            jobs.push({ widgetId: widgetId, preview: preview, titleEl: slot.querySelector('.report-widget-card-title') || null });
        });
        return jobs;
    }

    async autoLoadAllPreviews() {
        const jobs = this.collectPreviewJobs().filter(function (job) {
            return !this._slotPayloadCache[job.widgetId] && !this._loadingWidgets.has(job.widgetId);
        }.bind(this));
        if (!jobs.length) return;
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
        for (let i = 0; i < Math.min(concurrency, jobs.length); i += 1) workers.push(worker());
        await Promise.all(workers);
    }

    createEmptyState() {
        const wrap = document.createElement('div');
        wrap.className = 'rb-editor-empty';
        wrap.innerHTML = '<i class="fas fa-file-alt" aria-hidden="true"></i><p>Your report is empty. Add a section or choose a template to begin.</p>';
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn btn-secondary rb-editor-add-section-btn';
        btn.innerHTML = '<i class="fas fa-plus" aria-hidden="true"></i> Add section';
        btn.addEventListener('click', () => this.builder.addSection());
        wrap.appendChild(btn);
        const galleryBtn = document.createElement('button');
        galleryBtn.type = 'button';
        galleryBtn.className = 'btn btn-secondary rb-editor-add-section-btn mt-2';
        galleryBtn.textContent = 'Browse templates';
        galleryBtn.addEventListener('click', () => this.builder.openTemplateGallery());
        wrap.appendChild(galleryBtn);
        return wrap;
    }

    createAddSectionSlot() {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'rb-editor-add-section-slot';
        btn.innerHTML = '<i class="fas fa-plus" aria-hidden="true"></i> Add section';
        btn.addEventListener('click', () => this.builder.addSection());
        return btn;
    }

    async renderSectionBlock(section, index) {
        const lang = this.builder.activeLanguage || 'en';
        const title = resolveTranslation(section.title_translations, lang, section.title || 'Untitled section');
        const block = document.createElement('article');
        block.className = 'rb-editor-section' + (this.builder.selectedSectionId === section.id ? ' is-selected' : '');
        block.dataset.sectionId = section.id;

        const header = document.createElement('div');
        header.className = 'rb-editor-section-header';
        header.innerHTML = '<div class="rb-editor-section-title">' + title + '</div><div class="rb-editor-section-meta">' + this.builder.describeSection(section) + '</div>';
        header.addEventListener('click', (e) => {
            if (e.target.closest('.rb-editor-slot')) return;
            this.builder.selectSection(section.id);
        });
        block.appendChild(header);

        const body = document.createElement('div');
        body.className = 'rb-editor-section-body';

        if (section.dynamic_indicators?.enabled) {
            body.appendChild(await this.renderDynamicSection(section));
        } else {
            const gridHost = document.createElement('div');
            gridHost.className = 'rb-section-grid';
            gridHost.dataset.sectionId = section.id;
            body.appendChild(gridHost);
            body.appendChild(this.createInsertSlot(section.id, (section.widgets || []).length));
            await this.gridEngine.mount(gridHost, section, {
                renderSlotContent: (container, widget, sec) => this.renderSlotShell(container, widget, sec),
                onLayoutChange: (sectionId, items) => this.builder.applyGridLayout(sectionId, items)
            });
        }

        block.appendChild(body);
        appendSectionFootnote(block, resolveTranslation(section.footnote_translations, lang, section.footnote));
        return block;
    }

    renderSlotShell(container, widget, section) {
        const lang = this.builder.activeLanguage || 'en';
        const localized = localizedWidget(widget, lang, this.builder.definition.default_language || 'en');
        container.innerHTML = '';
        const slot = document.createElement('div');
        slot.className = 'rb-editor-slot' + (this.builder.selectedWidgetId === widget.id ? ' is-selected' : '');
        slot.dataset.widgetId = widget.id;
        slot.dataset.sectionId = section.id;

        const toolbar = document.createElement('div');
        toolbar.className = 'rb-editor-slot-toolbar';
        toolbar.innerHTML = '<span class="rb-editor-slot-type">' + (localized.type || 'widget') + '</span><button type="button" class="rb-editor-slot-action" data-action="delete" title="Delete"><i class="fas fa-trash"></i></button>';
        toolbar.addEventListener('click', (e) => {
            e.stopPropagation();
            if (e.target.closest('[data-action="delete"]')) this.builder.deleteWidgetById(widget.id);
        });
        slot.appendChild(toolbar);

        const preview = document.createElement('div');
        preview.className = 'rb-editor-slot-preview rb-editor-slot-content';
        slot.appendChild(preview);

        slot.addEventListener('click', (e) => {
            e.stopPropagation();
            this.builder.selectWidget(section.id, widget.id);
        });

        container.appendChild(slot);
        const cached = this._slotPayloadCache[widget.id];
        if (cached) {
            void renderWidget(preview, cached);
        }
    }

    async renderDynamicSection(section) {
        const wrap = document.createElement('div');
        wrap.className = 'rb-editor-dynamic-wrap';
        const matches = this.builder._sectionRuleMatches[section.id] || [];
        const dyn = section.dynamic_indicators || {};
        if (!matches.length) {
            wrap.innerHTML = '<div class="rb-editor-config-prompt">Configure programmes or tags in the Section panel to preview indicators here.</div>';
            return wrap;
        }
        const grouped = dyn.group_by === 'spef_section' ? groupIndicatorsBySpef(matches) : [{ code: 'all', name: '', indicators: matches }];
        for (const group of grouped) {
            if (group.name) {
                const h = document.createElement('div');
                h.className = 'rb-editor-spef-title';
                h.textContent = group.name;
                wrap.appendChild(h);
            }
            for (const row of group.indicators) {
                const widgetId = dynamicWidgetId(section.id, row.id);
                const slot = document.createElement('div');
                slot.className = 'rb-editor-slot rb-editor-dynamic-slot' + (this.builder.selectedDynamicIndicatorId === row.id ? ' is-selected' : '');
                slot.dataset.widgetId = widgetId;
                slot.dataset.skipPreview = 'false';
                slot.innerHTML = '<div class="rb-editor-slot-toolbar"><span class="rb-editor-slot-type">Dashboard</span><span class="rb-editor-slot-auto">auto</span></div><div class="rb-editor-slot-preview"></div>';
                slot.addEventListener('click', () => this.builder.selectDynamicIndicator(section.id, row.id));
                wrap.appendChild(slot);
            }
        }
        return wrap;
    }

    createInsertSlot(sectionId, index) {
        const slot = document.createElement('button');
        slot.type = 'button';
        slot.className = 'rb-editor-insert-slot';
        slot.innerHTML = '<i class="fas fa-plus" aria-hidden="true"></i> Add widget';
        slot.addEventListener('click', (e) => {
            e.stopPropagation();
            this.openInsertMenu(slot, sectionId, index);
        });
        return slot;
    }

    openInsertMenu(anchor, sectionId, index) {
        this.closeMenus();
        const menu = document.createElement('div');
        menu.className = 'rb-editor-insert-menu';
        INSERT_TYPES.forEach(function (item) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'rb-editor-insert-option';
            btn.innerHTML = '<i class="fas ' + item.icon + '" aria-hidden="true"></i> ' + item.label;
            btn.addEventListener('click', () => {
                this.closeMenus();
                this.builder.insertWidgetAt(sectionId, item.type, index);
            });
            menu.appendChild(btn);
        }.bind(this));
        anchor.parentNode.appendChild(menu);
        this._openMenu = menu;
    }

    async loadWidgetPreview(widgetId, previewHost, titleEl) {
        if (this._loadingWidgets.has(widgetId)) return;
        this._loadingWidgets.add(widgetId);
        previewHost.innerHTML = '<div class="rb-editor-loading">Loading preview…</div>';
        try {
            const payload = await this.fetchPreviewPayload(widgetId);
            this._slotPayloadCache[widgetId] = payload;
            previewHost.innerHTML = '';
            await renderWidget(previewHost, payload);
            if (titleEl && payload.title) titleEl.textContent = payload.title;
        } catch (err) {
            previewHost.innerHTML = '<div class="rb-editor-slot-error">' + (err.message || 'Preview failed') + '</div>';
        } finally {
            this._loadingWidgets.delete(widgetId);
        }
    }

    async fetchPreviewPayload(widgetId) {
        const widget = this.builder.findWidgetById(widgetId);
        if (!widget) throw new Error('Widget not found');
        const lang = this.builder.activeLanguage || 'en';
        const res = await fetch(this.builder.config.apiBase.replace(/\/api\/?$/, '') + '/api/preview', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.builder.config.csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify({
                definition: this.builder.definition,
                widget: widget,
                language: lang,
                report_id: this.builder.config.reportId || null,
                filters: this.builder.definition.filters
            })
        });
        const data = await res.json().catch(function () { return {}; });
        if (!res.ok) throw new Error(data.message || data.error || 'Preview failed');
        return data.widget || (data.widgets || {})[widgetId] || data;
    }

    async refreshAllPreviews() {
        this.invalidateCache();
        await this.render();
    }
}
