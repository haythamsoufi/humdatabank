/**
 * UPR Analysis presentation and A4 report: the shared outline
 * (upr-analysis-pages.js), the block renderer they both use
 * (UprAnalysis.dom.renderBlock), and the slide deck / report shells.
 *
 * Views come from the server contract fixture, so these tests exercise the real
 * view shapes. ApexCharts and page layout are stubbed (jsdom has neither).
 */
import { describe, it, expect, beforeAll, beforeEach, afterEach, vi } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE = path.resolve(here, '../../../plugins/upr/tests/fixtures/analysis_views.json');
const STATIC = '../../../plugins/upr/static/js/';

const UI = {
    export_generated: 'Generated {date}',
    export_region: 'Region: {region}',
    export_all_regions: 'All regions',
    export_page: 'Page {n} of {total}',
    export_notes: 'Notes',
    export_tables_heading: 'Data tables',
    export_more: 'and {n} more',
    export_print: 'Download PDF',
    export_print_hint: 'Saves an A4 PDF of these pages.',
    export_pdf_working: 'Preparing PDF…',
    export_pdf_failed: 'Could not create the PDF. Try again.',
    export_prev: 'Previous slide',
    export_next: 'Next slide',
    export_fullscreen: 'Full screen',
    gaps_select: 'Select a list to see the countries.',
    section_data: 'Data trends',
    track_ALL: 'Overview',
    track_P: 'Plans',
    track_MYR: 'Mid-year reports',
    track_AR: 'Annual reports',
    close: 'Close',
    findings_title: 'Key findings',
    export_findings: 'Show or hide findings',
    export_finding: 'Finding {n}',
};

const FINDINGS = [
    { id: 'a', title: 'Growing', text: 'Requirement doubled.', tone: 'positive', focus: { categories: ['2025 *'] } },
    { id: 'b', title: null, text: 'Funding fell.', tone: 'attention', focus: { categories: ['2025 *', '2024'] } },
    { id: 'c', title: null, text: 'No expenditure yet.', tone: 'info', focus: null },
];

// A copy of the data view whose funding visual carries findings.
function withFindings() {
    const impact = JSON.parse(JSON.stringify(fixture.impact));
    impact.visuals.find((v) => v.id === 'funding').findings = FINDINGS;
    return impact;
}

let A;
let fixture;

beforeAll(async () => {
    await import(`${STATIC}upr-analysis-format.js`);
    await import(`${STATIC}upr-analysis-charts.js`);
    await import(`${STATIC}upr-analysis-dom.js`);
    await import(`${STATIC}upr-analysis-pages.js`);
    await import(`${STATIC}upr-analysis-slides.js`);
    await import(`${STATIC}upr-analysis-report.js`);
    A = window.UprAnalysis;
    fixture = JSON.parse(fs.readFileSync(FIXTURE, 'utf8'));
});

function outline(extra = {}) {
    return A.pages.buildOutline({
        impact: fixture.impact,
        narrative: fixture.narrative,
        ui: UI,
        region: '',
        generatedAt: new Date(2026, 9, 13),
        selected: ['data', 'track:ALL'],
        includeTables: false,
        ...extra,
    });
}

const types = (blocks) => blocks.map((b) => b.type);

describe('outline', () => {
    it('lists the sections that can be exported and which are loaded', () => {
        const sections = A.pages.sections({ impact: fixture.impact, narrative: fixture.narrative }, UI);
        expect(sections.map((s) => s.id)).toEqual(['data', 'track:ALL', 'track:P', 'track:MYR', 'track:AR']);
        expect(sections[0].label).toBe('Data trends');
        expect(sections[1].label).toBe(`${fixture.narrative.ALL.title} — Overview`);
        expect(sections.every((s) => s.available)).toBe(true);

        const partial = A.pages.sections({ impact: null, narrative: { ALL: fixture.narrative.ALL } }, UI);
        expect(partial.map((s) => s.available)).toEqual([false, true, false, false, false]);
    });

    it('starts with a cover and puts each section in order: heading, KPIs, visuals, notes', () => {
        const blocks = outline();
        expect(blocks[0].type).toBe('cover');
        expect(blocks[0].title).toBe(fixture.impact.title);
        expect(blocks[0].lines).toEqual(['Region: All regions', expect.stringContaining('Generated ')]);

        const data = blocks.filter((b) => b.section === 'data' || (b.type === 'section' && b.id === 'data'));
        expect(types(data)).toEqual([
            'section',
            'kpis',
            ...fixture.impact.visuals.map(() => 'visual'),
            'notes',
        ]);
        expect(data.filter((b) => b.type === 'visual').map((b) => b.visual.id)).toEqual(fixture.impact.visuals.map((v) => v.id));
        expect(blocks.filter((b) => b.type === 'section').map((b) => b.id)).toEqual(['data', 'track:ALL']);
    });

    it('points at the very same views the tab shows instead of copying them', () => {
        const blocks = outline();
        const kpis = blocks.find((b) => b.type === 'kpis');
        expect(kpis.kpis).toBe(fixture.impact.kpis);
        expect(blocks.find((b) => b.type === 'visual').visual).toBe(fixture.impact.visuals[0]);
    });

    it('names the selected region on the cover', () => {
        expect(outline({ region: 'Africa' })[0].lines[0]).toBe('Region: Africa');
    });

    it('keeps only the selected, available sections', () => {
        const onlyPlans = outline({ selected: ['track:P'] });
        expect(onlyPlans.filter((b) => b.type === 'section').map((b) => b.id)).toEqual(['track:P']);

        const missing = outline({ narrative: null, selected: ['track:P', 'track:ALL'] });
        expect(missing).toEqual([]);
        expect(outline({ selected: [] })).toEqual([]);
    });

    it('adds data tables on request, skipping gap lists that the card already spells out', () => {
        const withTables = outline({ includeTables: true, selected: ['track:ALL'] });
        const tables = withTables.filter((b) => b.type === 'table');
        const expected = fixture.narrative.ALL.visuals.filter((v) => v.table && v.kind !== 'gaps');
        expect(tables.map((b) => b.visual.id)).toEqual(expected.map((v) => v.id));
        expect(tables.map((b) => b.first)).toEqual(tables.map((_, i) => i === 0));
        expect(outline({ selected: ['track:ALL'] }).some((b) => b.type === 'table')).toBe(false);
    });
});

describe('block rendering', () => {
    it('renders every block type with the tab\'s own classes', () => {
        const blocks = outline({ includeTables: true, selected: ['data', 'track:ALL'] });
        const rendered = blocks.map((block) => A.dom.renderBlock(block, { ui: UI, logoUrl: '/logo.svg' }));
        rendered.forEach(({ element }, i) => expect(element.getAttribute('data-upri-block')).toBe(blocks[i].type));

        const byType = (type) => rendered.filter((_, i) => blocks[i].type === type).map((r) => r.element);
        expect(byType('cover')[0].querySelector('img').getAttribute('src')).toBe('/logo.svg');
        expect(byType('section')[0].querySelector('h2').textContent).toBe('Data trends');
        expect(byType('kpis')[0].querySelectorAll('.upri-kpi')).toHaveLength(fixture.impact.kpis.length);
        expect(byType('visual')[0].classList.contains('upri-card')).toBe(true);
        expect(byType('notes')[0].querySelector('h4').textContent).toBe('Notes');
        expect(byType('table')[0].querySelector('table.upri-table')).not.toBeNull();
    });

    it('drops the controls that only work on the tab', () => {
        fixture.narrative.ALL.visuals.forEach((visual) => {
            const { element } = A.dom.renderBlock({ type: 'visual', visual }, { ui: UI });
            expect(element.querySelector('[data-upri-table]')).toBeNull();
            expect(element.querySelector('[data-upri-gap]')).toBeNull();
            expect(element.querySelector('button')).toBeNull();
        });
    });

    it('spells out each gap with its countries and truncates long lists', () => {
        const gaps = fixture.narrative.ALL.visuals.find((v) => v.id === 'narr_gaps');
        const { element } = A.dom.renderBlock({ type: 'visual', visual: gaps }, { ui: UI });
        const lists = element.querySelectorAll('.upri-gap-list');
        expect(lists).toHaveLength(gaps.gaps.length);
        gaps.gaps.forEach((gap, i) => {
            expect(lists[i].querySelector('.upri-gap__label').textContent).toBe(gap.label);
            gap.table.rows.forEach((row) => expect(lists[i].textContent).toContain(row.cells[0]));
        });

        const crowded = {
            ...gaps,
            gaps: [{ id: 'g', label: 'Many', count: 5, table: { rows: [1, 2, 3, 4, 5].map((n) => ({ cells: [`C${n}`, 'R'] })) } }],
        };
        const short = A.dom.renderBlock({ type: 'visual', visual: crowded }, { ui: UI, maxNames: 2 }).element;
        expect(short.querySelector('.upri-gap-list__names').textContent).toBe('C1, C2, and 3 more');
    });

    it('draws charts at the requested fixed size and reserves their room', () => {
        const funding = fixture.impact.visuals.find((v) => v.id === 'funding');
        const size = { width: 640, height: 280 };
        const { element, plots } = A.dom.renderBlock({ type: 'visual', visual: funding }, { ui: UI, size });
        expect(plots).toHaveLength(1);
        expect(plots[0].chart.width).toBe(640);
        expect(plots[0].chart.height).toBe(280);
        expect(funding.chart.width).toBeUndefined();
        expect(funding.chart.height).not.toBe(280);
        expect(plots[0].host.style.minHeight).toBe('295px');
        expect(element.contains(plots[0].host)).toBe(true);
        expect(A.charts.buildOptions(plots[0].chart).chart.width).toBe(640);
    });

    it('sizes the capacity panels separately', () => {
        const capacity = fixture.impact.visuals.find((v) => v.id === 'capacity');
        const { plots } = A.dom.renderBlock({ type: 'visual', visual: capacity }, { ui: UI, size: { panelWidth: 300, panelHeight: 150 } });
        expect(plots).toHaveLength(capacity.panels.length);
        plots.forEach((plot) => {
            expect(plot.chart.width).toBe(300);
            expect(plot.chart.height).toBe(150);
        });
    });

    it('prints a table without drill-down controls or hidden rows', () => {
        const table = fixture.impact.visuals.find((v) => v.id === 'funding').table;
        const wrap = A.dom.renderTable(table, { ui: UI });
        expect(wrap.querySelectorAll('thead th')).toHaveLength(table.columns.length);
        expect(wrap.querySelectorAll('tbody tr')).toHaveLength(table.rows.length);
        expect(wrap.querySelector('button')).toBeNull();
        expect(wrap.querySelector('.upri-table__detail')).toBeNull();
    });

    it('tells the tab (only) how to open a gap list', () => {
        const gaps = fixture.narrative.ALL.visuals.find((v) => v.id === 'narr_gaps');
        const tab = A.dom.renderCard(gaps, { ui: UI }).element;
        expect(tab.querySelector('.upri-card__hint').textContent).toBe(`${gaps.hint} ${UI.gaps_select}`);
        const printed = A.dom.renderCard(gaps, { ui: UI, interactive: false }).element;
        expect(printed.querySelector('.upri-card__hint').textContent).toBe(gaps.hint);
    });
});

describe('findings', () => {
    const funding = () => withFindings().visuals.find((v) => v.id === 'funding');

    it('lists them under the chart on the tab, all visible and without controls', () => {
        const { element } = A.dom.renderCard(funding(), { ui: UI });
        const items = element.querySelectorAll('.upri-findings .upri-finding');
        expect(element.querySelector('.upri-findings__heading').textContent).toBe('Key findings');
        expect([...items].map((li) => li.getAttribute('data-upri-finding'))).toEqual(['a', 'b', 'c']);
        expect(items[0].classList.contains('upri-finding--positive')).toBe(true);
        expect(items[0].querySelector('.upri-finding__title').textContent).toBe('Growing');
        expect(items[1].querySelector('.upri-finding__title')).toBeNull();
        expect(element.querySelector('.upri-finding__toggle')).toBeNull();
        expect(element.querySelector('.is-pending')).toBeNull();
    });

    it('adds nothing to a visual without findings', () => {
        fixture.impact.visuals.forEach((visual) => {
            expect(A.dom.renderCard(visual, { ui: UI }).element.querySelector('.upri-findings-wrap')).toBeNull();
        });
    });

    it('starts every finding hidden behind a numbered button in steps mode', () => {
        const list = A.dom.renderFindings(FINDINGS, 'steps', { ui: UI }).querySelector('.upri-findings');
        const items = [...list.children];
        expect(items.every((li) => li.classList.contains('is-pending'))).toBe(true);
        const toggles = list.querySelectorAll('.upri-finding__toggle');
        expect([...toggles].map((t) => t.textContent)).toEqual(['1', '2', '3']);
        expect(toggles[1].getAttribute('aria-label')).toBe('Finding 2');
        expect(toggles[1].getAttribute('aria-expanded')).toBe('false');

        A.dom.setFindingRevealed(items[1], true);
        expect(items[1].classList.contains('is-revealed')).toBe(true);
        expect(items[1].classList.contains('is-pending')).toBe(false);
        expect(toggles[1].getAttribute('aria-expanded')).toBe('true');
    });

    it('outline blocks keep pointing at the visual that carries its findings', () => {
        const impact = withFindings();
        const blocks = A.pages.buildOutline({
            impact, narrative: fixture.narrative, ui: UI, region: '', selected: ['data'],
        });
        expect(blocks.find((b) => b.type === 'visual' && b.visual.id === 'funding').visual.findings).toHaveLength(3);
    });
});

describe('with a stubbed ApexCharts', () => {
    let instances;

    beforeEach(() => {
        instances = [];
        window.ApexCharts = class {
            constructor(host, config) {
                this.host = host;
                this.config = config;
                this.destroyed = false;
                instances.push(this);
            }
            render() {}
            destroy() {
                this.destroyed = true;
            }
            clearAnnotations() {
                this.annotations = [];
            }
            addXaxisAnnotation(annotation) {
                this.annotations = (this.annotations || []).concat(annotation);
            }
        };
    });

    afterEach(() => {
        A.slides.close();
        A.report.close();
        delete window.ApexCharts;
        document.body.innerHTML = '';
        document.body.className = '';
    });

    it('mounts every plot without animation when asked', () => {
        const host = document.createElement('div');
        const charts = A.charts.mountAll([{ host, chart: fixture.impact.visuals[0].chart }], { animate: false });
        expect(charts).toHaveLength(1);
        expect(instances[0].config.chart.animations.enabled).toBe(false);
        A.charts.mount(document.createElement('div'), fixture.impact.visuals[0].chart);
        expect(instances[1].config.chart.animations.enabled).toBe(true);
    });

    it('highlights each focused category once and clears with no focus', () => {
        const chart = A.charts.mount(document.createElement('div'), fixture.impact.visuals[0].chart);
        A.charts.focus(chart, { categories: ['2025 *', '2024', '2025 *'] });
        expect(chart.annotations.map((a) => a.x)).toEqual(['2025 *', '2024']);
        A.charts.focus(chart, { categories: ['2024'] });
        expect(chart.annotations.map((a) => a.x)).toEqual(['2024']);
        A.charts.focus(chart, null);
        expect(chart.annotations).toEqual([]);
        expect(() => A.charts.focus(null, { categories: ['x'] })).not.toThrow();
        expect(() => A.charts.focus({}, { categories: ['x'] })).not.toThrow();
    });

    describe('findings in the presentation', () => {
        const press = (key) => document.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }));
        const deckOpts = { ui: UI, title: 'Deck' };
        const counter = () => document.querySelector('.upri-deck__counter').textContent;
        const activeItems = () => [...document.querySelectorAll('.upri-slide.is-active .upri-finding')];
        const shown = () => activeItems().filter((li) => li.classList.contains('is-revealed')).length;
        const funded = () => instances.find((c) => c.config.series.some((s) => s.name === 'Planned requirement'));

        function openOnFunding() {
            const blocks = A.pages.buildOutline({
                impact: withFindings(), narrative: fixture.narrative, ui: UI, selected: ['data'],
            });
            const deck = A.slides.open(blocks, deckOpts);
            const target = blocks.filter((b) => b.type !== 'table').findIndex((b) => b.type === 'visual' && b.visual.id === 'funding');
            deck.go(target);
            return { deck, target };
        }

        it('reveals one finding per step before moving on, then continues', () => {
            const { deck, target } = openOnFunding();
            expect(counter()).toBe(`${target + 1} / ${deck.count} · 0/3`);
            expect(shown()).toBe(0);
            press('ArrowRight');
            press(' ');
            expect(shown()).toBe(2);
            expect(counter()).toContain('· 2/3');
            press('Enter');
            expect(shown()).toBe(3);
            expect(counter()).toBe(`${target + 1} / ${deck.count} · 3/3`);
            press('ArrowRight');
            expect(counter()).toBe(`${target + 2} / ${deck.count}`);
        });

        it('steps back through the findings before leaving the slide', () => {
            const { deck, target } = openOnFunding();
            press('i');
            expect(shown()).toBe(3);
            press('ArrowLeft');
            expect(shown()).toBe(2);
            press('ArrowLeft');
            press('ArrowLeft');
            expect(shown()).toBe(0);
            press('ArrowLeft');
            expect(counter()).toBe(`${target} / ${deck.count}`);
        });

        it('keeps revealed findings when you come back to the slide', () => {
            const { deck, target } = openOnFunding();
            press('ArrowRight');
            press('ArrowRight');
            deck.go(0);
            deck.go(target);
            expect(shown()).toBe(2);
            expect(counter()).toContain('· 2/3');
        });

        it('starts every finding hidden again when the presentation reopens', () => {
            openOnFunding();
            press('i');
            A.slides.close();
            openOnFunding();
            expect(shown()).toBe(0);
        });

        it('shows or hides a single finding with its numbered button, and all with I', () => {
            openOnFunding();
            document.querySelectorAll('.upri-slide.is-active .upri-finding__toggle')[1].click();
            expect(activeItems().map((li) => li.classList.contains('is-revealed'))).toEqual([false, true, false]);
            document.querySelectorAll('.upri-slide.is-active .upri-finding__toggle')[1].click();
            expect(shown()).toBe(0);
            press('i');
            expect(shown()).toBe(3);
            press('i');
            expect(shown()).toBe(0);
            document.querySelector('.upri-deck__findings').click();
            expect(shown()).toBe(3);
        });

        it('highlights the categories of the findings that are showing', () => {
            openOnFunding();
            const chart = funded();
            expect(chart.annotations || []).toEqual([]);
            press('ArrowRight');
            expect(chart.annotations.map((a) => a.x)).toEqual(['2025 *']);
            press('ArrowRight');
            expect(chart.annotations.map((a) => a.x)).toEqual(['2025 *', '2024']);
            press('ArrowRight');
            expect(chart.annotations.map((a) => a.x)).toEqual(['2025 *', '2024']);
            press('ArrowLeft');
            press('ArrowLeft');
            press('ArrowLeft');
            expect(chart.annotations).toEqual([]);
        });

        it('only offers the findings control on slides that have findings', () => {
            const { deck, target } = openOnFunding();
            const button = document.querySelector('.upri-deck__findings');
            expect(button.hidden).toBe(false);
            deck.go(0);
            expect(button.hidden).toBe(true);
            press('i');
            expect(counter()).toBe(`1 / ${deck.count}`);
            deck.go(target);
            expect(button.hidden).toBe(false);
        });

        it('leaves room for the findings under the chart', () => {
            openOnFunding();
            const chart = funded();
            expect(chart.config.chart.height).toBe(A.slides.FINDINGS_SIZE.height);
            instances.length = 0;
            A.slides.close();
            A.slides.open(outline(), deckOpts);
            const plain = instances.find((c) => c.config.series.some((s) => s.name === 'Planned requirement'));
            expect(plain.config.chart.height).toBe(A.slides.CHART_SIZE.height);
        });
    });

    describe('presentation', () => {
        const press = (key) => document.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }));
        const active = () => document.querySelector('.upri-slide.is-active');

        it('makes one slide per block, leaving the tables to the report', () => {
            const blocks = outline({ includeTables: true });
            const deck = A.slides.open(blocks, { ui: UI, title: 'Deck' });
            expect(deck.count).toBe(blocks.filter((b) => b.type !== 'table').length);
            expect(document.querySelectorAll('.upri-slide')).toHaveLength(deck.count);
            expect(document.querySelector('.upri-deck').getAttribute('aria-label')).toBe('Deck');
            expect(active().classList.contains('upri-slide--cover')).toBe(true);
            expect(document.querySelector('.upri-deck__counter').textContent).toBe(`1 / ${deck.count}`);
            expect(document.querySelector('.upri-deck').classList.contains('is-on-cover')).toBe(true);
            expect(document.body.classList.contains('upri-locked')).toBe(true);
        });

        it('draws every chart of the outline once, at the slide size', () => {
            const blocks = outline();
            A.slides.open(blocks, { ui: UI });
            const expected = blocks
                .filter((b) => b.type === 'visual')
                .reduce((n, b) => n + (b.visual.kind === 'panels' ? b.visual.panels.length : b.visual.chart ? 1 : 0), 0);
            expect(instances).toHaveLength(expected);
            expect(instances.every((c) => c.config.chart.width > 0)).toBe(true);
        });

        it('titles content slides with their section', () => {
            A.slides.open(outline(), { ui: UI });
            const tags = [...document.querySelectorAll('.upri-slide__tag')].map((t) => t.textContent);
            expect(tags[0]).toBe('Data trends');
            expect(tags).toContain(`${fixture.narrative.ALL.title} — Overview`);
        });

        it('moves with the keyboard and the buttons and stays within the deck', () => {
            const deck = A.slides.open(outline(), { ui: UI });
            const prev = document.querySelector('.upri-deck__prev');
            const next = document.querySelector('.upri-deck__next');
            expect(prev.disabled).toBe(true);
            press('ArrowRight');
            expect(document.querySelector('.upri-deck').classList.contains('is-on-cover')).toBe(false);
            press(' ');
            expect(document.querySelector('.upri-deck__counter').textContent).toBe(`3 / ${deck.count}`);
            press('ArrowLeft');
            expect(document.querySelector('.upri-deck__counter').textContent).toBe(`2 / ${deck.count}`);
            press('End');
            expect(next.disabled).toBe(true);
            press('ArrowRight');
            expect(document.querySelector('.upri-deck__counter').textContent).toBe(`${deck.count} / ${deck.count}`);
            press('Home');
            expect(prev.disabled).toBe(true);
            next.click();
            expect(document.querySelector('.upri-deck__counter').textContent).toBe(`2 / ${deck.count}`);
            expect(document.querySelectorAll('.upri-slide.is-active')).toHaveLength(1);
            expect(document.querySelectorAll('.upri-slide[aria-hidden="false"]')).toHaveLength(1);
        });

        it('closes on Escape, destroying its charts and releasing the page', () => {
            A.slides.open(outline(), { ui: UI });
            press('Escape');
            expect(document.querySelector('.upri-deck')).toBeNull();
            expect(instances.every((c) => c.destroyed)).toBe(true);
            expect(document.body.classList.contains('upri-locked')).toBe(false);
            press('ArrowRight');
        });

        it('keeps a single deck open', () => {
            A.slides.open(outline(), { ui: UI });
            A.slides.open(outline(), { ui: UI });
            expect(document.querySelectorAll('.upri-deck')).toHaveLength(1);
        });

        it('opens nothing for an empty outline', () => {
            expect(A.slides.open([], { ui: UI })).toBeNull();
        });
    });

    describe('A4 report', () => {
        // jsdom has no layout: model a body that holds 1000px and blocks of 400px.
        let scrollHeight;
        let clientHeight;

        beforeEach(() => {
            scrollHeight = Object.getOwnPropertyDescriptor(Element.prototype, 'scrollHeight');
            clientHeight = Object.getOwnPropertyDescriptor(Element.prototype, 'clientHeight');
            Object.defineProperty(Element.prototype, 'scrollHeight', {
                configurable: true,
                get() {
                    return this.classList.contains('upri-page__body') ? this.children.length * 400 : 0;
                },
            });
            Object.defineProperty(Element.prototype, 'clientHeight', {
                configurable: true,
                get() {
                    return this.classList.contains('upri-page__body') ? 1000 : 0;
                },
            });
            const link = document.createElement('link');
            link.id = 'upri-report-print-css';
            link.media = 'not all';
            document.head.appendChild(link);
        });

        afterEach(() => {
            Object.defineProperty(Element.prototype, 'scrollHeight', scrollHeight || { configurable: true, value: 0 });
            Object.defineProperty(Element.prototype, 'clientHeight', clientHeight || { configurable: true, value: 0 });
            document.getElementById('upri-report-print-css').remove();
        });

        const pageBlocks = (page) => [...page.querySelectorAll('.upri-page__body > *')].map((el) => el.getAttribute('data-upri-block') || 'keep');

        it('puts the cover alone on the first page and starts each section on a new page', () => {
            const report = A.report.open(outline(), { ui: UI, title: 'Report' });
            const pages = [...document.querySelectorAll('.upri-page')];
            expect(report.pageCount).toBe(pages.length);
            expect(pages[0].classList.contains('upri-page--cover')).toBe(true);
            expect(pageBlocks(pages[0])).toEqual(['cover']);
            pages.slice(1).forEach((page) => {
                const first = pageBlocks(page)[0];
                // A page opens either with a section heading (kept with its KPIs) or continues one.
                expect(['keep', 'visual', 'notes']).toContain(first);
            });
            const headings = pages.filter((p) => p.querySelector('.upri-keep'));
            expect(headings).toHaveLength(2);
        });

        it('moves a block to the next page once the page is full', () => {
            A.report.open(outline(), { ui: UI });
            const pages = [...document.querySelectorAll('.upri-page')].slice(1);
            pages.forEach((page) => {
                expect(page.querySelector('.upri-page__body').children.length).toBeLessThanOrEqual(2);
            });
            const all = pages.flatMap(pageBlocks);
            expect(all.filter((b) => b === 'visual')).toHaveLength(
                fixture.impact.visuals.length + fixture.narrative.ALL.visuals.length,
            );
        });

        it('numbers the pages after the cover', () => {
            A.report.open(outline(), { ui: UI, title: 'Report' });
            const feet = [...document.querySelectorAll('.upri-page__foot')];
            const total = document.querySelectorAll('.upri-page').length - 1;
            expect(feet).toHaveLength(total);
            expect(feet[0].textContent).toContain('Report');
            expect(feet[0].textContent).toContain(`Page 1 of ${total}`);
            expect(feet[total - 1].textContent).toContain(`Page ${total} of ${total}`);
            expect(document.querySelector('.upri-page--cover .upri-page__foot')).toBeNull();
        });

        it('re-flows pages when text re-wraps after the fonts load, and renumbers them', async () => {
            let fontsLoaded;
            document.fonts = { ready: new Promise((resolve) => { fontsLoaded = resolve; }) };
            try {
                const report = A.report.open(outline(), { ui: UI, title: 'Report' });
                const before = report.pageCount;
                // Late-loading fonts make every block taller: only one now fits per page.
                Object.defineProperty(Element.prototype, 'scrollHeight', {
                    configurable: true,
                    get() {
                        return this.classList.contains('upri-page__body') ? this.children.length * 600 : 0;
                    },
                });
                fontsLoaded();
                await document.fonts.ready;
                await Promise.resolve();
                const bodies = [...document.querySelectorAll('.upri-page:not(.upri-page--cover) .upri-page__body')];
                expect(report.pageCount).toBeGreaterThan(before);
                bodies.forEach((body) => expect(body.children.length).toBeLessThanOrEqual(1));
                const feet = [...document.querySelectorAll('.upri-page__foot')];
                expect(feet.at(-1).textContent).toContain(`Page ${feet.length} of ${feet.length}`);
                const order = bodies.flatMap((body) => [...body.children].map((c) => c.getAttribute('data-upri-block') || 'keep'));
                expect(order.filter((b) => b === 'visual')).toHaveLength(
                    fixture.impact.visuals.length + fixture.narrative.ALL.visuals.length,
                );
            } finally {
                delete document.fonts;
            }
        });

        it('includes the data tables when asked', () => {
            A.report.open(outline({ includeTables: true }), { ui: UI });
            expect(document.querySelectorAll('[data-upri-block="table"]').length).toBeGreaterThan(0);
            expect(document.querySelector('.upri-table-block__heading').textContent).toBe('Data tables');
        });

        it('switches the print rules on while a report is open', () => {
            const sheet = document.getElementById('upri-report-print-css');
            const report = A.report.open(outline(), { ui: UI });
            expect(sheet.media).toBe('print');
            expect(document.body.classList.contains('upri-report-open')).toBe(true);
            expect(document.querySelector('.upri-report__bar .upri-btn--primary').textContent).toContain('Download PDF');
            report.close();
            expect(sheet.media).toBe('not all');
            expect(document.body.classList.contains('upri-report-open')).toBe(false);
            expect(instances.every((c) => c.destroyed)).toBe(true);
        });

        it('downloads one A4 image per page instead of opening the print dialog', async () => {
            const print = vi.spyOn(window, 'print').mockImplementation(() => {});
            const saved = [];
            const images = [];
            window.html2canvas = () => Promise.resolve({
                width: 200,
                height: 282,
                toDataURL: () => 'data:image/jpeg;base64,xx',
            });
            window.jspdf = {
                jsPDF: class {
                    addPage() { images.push('page'); }
                    addImage() { images.push('image'); }
                    save(name) { saved.push(name); }
                },
            };
            try {
                A.report.open(outline(), { ui: UI, title: 'Unified Plans' });
                const count = document.querySelectorAll('.upri-page').length;
                document.querySelector('.upri-report__bar .upri-btn--primary').click();
                expect(document.querySelector('.upri-report__bar .upri-btn--primary').textContent).toContain('Preparing PDF…');
                await vi.waitFor(() => { expect(saved).toEqual(['Unified Plans.pdf']); });
                expect(print).not.toHaveBeenCalled();
                expect(images.filter((item) => item === 'image')).toHaveLength(count);
                expect(images.filter((item) => item === 'page')).toHaveLength(count - 1);
                expect(document.querySelector('.upri-report__bar .upri-btn--primary').textContent).toContain('Download PDF');
            } finally {
                print.mockRestore();
                delete window.html2canvas;
                delete window.jspdf;
            }
        });

        it('scales the preview to a phone without shrinking the pages themselves', () => {
            const offsetWidth = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetWidth');
            const offsetHeight = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetHeight');
            const clientWidth = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'clientWidth');
            const box = (el) => {
                if (el.classList.contains('upri-page')) return { w: 794, h: 1123 };
                if (el.classList.contains('upri-report__pages')) return { w: 794, h: 4000 };
                return { w: 0, h: 0 };
            };
            Object.defineProperty(HTMLElement.prototype, 'offsetWidth', { configurable: true, get() { return box(this).w; } });
            Object.defineProperty(HTMLElement.prototype, 'offsetHeight', { configurable: true, get() { return box(this).h; } });
            Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
                configurable: true,
                get() { return this.classList.contains('upri-report') ? 390 : 0; },
            });
            try {
                A.report.open(outline(), { ui: UI });
                const pages = document.querySelector('.upri-report__pages');
                const frame = document.querySelector('.upri-report__frame');
                const scale = (390 - 16) / 794;
                expect(pages.style.width).toBe('794px');
                expect(Number(pages.style.transform.match(/scale\(([^)]+)\)/)[1])).toBeCloseTo(scale, 4);
                expect(Number(frame.style.height.replace('px', ''))).toBe(Math.ceil(4000 * scale));
                expect(document.querySelector('.upri-page').style.width).toBe('');
                document.querySelector('.upri-report__bar .upri-btn--primary').click();
                expect(pages.style.transform).toContain(`scale(${scale})`);
            } finally {
                if (offsetWidth) Object.defineProperty(HTMLElement.prototype, 'offsetWidth', offsetWidth);
                if (offsetHeight) Object.defineProperty(HTMLElement.prototype, 'offsetHeight', offsetHeight);
                if (clientWidth) Object.defineProperty(HTMLElement.prototype, 'clientWidth', clientWidth);
            }
        });

        it('closes on Escape and from the toolbar', () => {
            A.report.open(outline(), { ui: UI });
            document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
            expect(document.querySelector('.upri-report')).toBeNull();
            A.report.open(outline(), { ui: UI });
            document.querySelector('.upri-report__actions .upri-btn:not(.upri-btn--primary)').click();
            expect(document.querySelector('.upri-report')).toBeNull();
        });
    });
});
