/* UPR Analysis — DOM renderers for a view (plugins/upr/analysis_spec.py):
 * KPI cards, visual cards, notes and the drill-down table dialog. They only
 * read the view they are given, so the presentation and the A4 report reuse the
 * very same cards (renderBlock). Charts are not drawn here: renderCard reports
 * where each one goes ({host, chart}) and the caller mounts it with
 * UprAnalysis.charts. */
(function (global) {
    'use strict';

    var root = global.UprAnalysis = global.UprAnalysis || {};

    function node(tag, className, text) {
        var el = document.createElement(tag);
        if (className) el.className = className;
        if (text != null) el.textContent = text;
        return el;
    }

    function icon(name) {
        var i = node('i', 'fas ' + name);
        i.setAttribute('aria-hidden', 'true');
        return i;
    }

    function ui(options) {
        return (options && options.ui) || {};
    }

    // -- KPI cards -----------------------------------------------------------

    var DELTA_ICON = { up: 'fa-arrow-up', down: 'fa-arrow-down', flat: 'fa-minus' };

    function kpiCard(kpi) {
        var card = node('div', 'upri-kpi');
        card.setAttribute('data-upri-kpi', kpi.id);
        card.appendChild(node('p', 'upri-kpi__label', kpi.label));

        var value = node('div', 'upri-kpi__value', root.format.format(kpi.value, kpi.format));
        if (kpi.year != null) {
            value.appendChild(document.createTextNode(' '));
            value.appendChild(node('span', 'upri-kpi__context', '(' + kpi.year + ')'));
        }
        card.appendChild(value);

        var delta = kpi.delta;
        if (delta) {
            var meta = node('span', 'upri-kpi__meta upri-kpi__delta--' + delta.direction);
            if (!delta.note) meta.appendChild(icon(DELTA_ICON[delta.direction] || DELTA_ICON.flat));
            meta.appendChild(document.createTextNode(delta.text));
            card.appendChild(meta);
            if (delta.context) {
                card.appendChild(document.createTextNode(' '));
                card.appendChild(node('span', 'upri-kpi__context', delta.context));
            }
        }
        return card;
    }

    function renderKpis(container, kpis) {
        if (!container) return;
        container.replaceChildren();
        (kpis || []).forEach(function (kpi) { container.appendChild(kpiCard(kpi)); });
    }

    // -- notes ---------------------------------------------------------------

    function renderNotes(container, notes) {
        if (!container) return;
        container.replaceChildren();
        (notes || []).forEach(function (text) {
            container.appendChild(node('p', 'upri-footnote', text));
        });
        container.hidden = !(notes && notes.length);
    }

    function renderWarnings(container, warnings) {
        if (!container) return;
        container.textContent = (warnings || []).join(' ');
        container.hidden = !(warnings && warnings.length);
    }

    // -- findings ------------------------------------------------------------

    /** Show or hide one finding of a ``steps`` list (the presentation reveals them). */
    function setFindingRevealed(item, revealed) {
        item.classList.toggle('is-revealed', revealed);
        item.classList.toggle('is-pending', !revealed);
        var toggle = item.querySelector('.upri-finding__toggle');
        if (toggle) toggle.setAttribute('aria-expanded', revealed ? 'true' : 'false');
    }

    /**
     * What the data says about a visual. ``mode`` is ``visible`` (the tab and the
     * report: all text shown) or ``steps`` (the presentation: each finding starts
     * hidden behind a numbered button and is revealed in turn).
     */
    function renderFindings(findings, mode, options) {
        var text = ui(options);
        var wrap = node('div', 'upri-findings-wrap');
        wrap.appendChild(node('h5', 'upri-findings__heading', text.findings_title || ''));
        var list = node('ul', 'upri-findings upri-findings--' + mode);
        findings.forEach(function (found, i) {
            var item = node('li', 'upri-finding upri-finding--' + (found.tone || 'info'));
            item.setAttribute('data-upri-finding', found.id);
            if (mode === 'steps') {
                var toggle = node('button', 'upri-finding__toggle', String(i + 1));
                toggle.type = 'button';
                toggle.setAttribute('aria-label', root.format.fill(text.export_finding || 'Finding {n}', { n: i + 1 }));
                item.appendChild(toggle);
            }
            var body = node('div', 'upri-finding__body');
            if (found.title) body.appendChild(node('p', 'upri-finding__title', found.title));
            body.appendChild(node('p', 'upri-finding__text', found.text));
            item.appendChild(body);
            list.appendChild(item);
            if (mode === 'steps') setFindingRevealed(item, false);
        });
        wrap.appendChild(list);
        return wrap;
    }

    // -- visual cards --------------------------------------------------------

    // A chart spec drawn at a fixed size (slides and A4 pages). ApexCharts pads its
    // host to the chart height plus this much, so the host reserves the same up
    // front and a page can be measured before its charts exist.
    var APEX_HOST_PADDING = 15;

    function sized(chart, width, height) {
        if (!chart || (!width && !height)) return chart;
        var copy = Object.assign({}, chart);
        if (width) copy.width = width;
        if (height) copy.height = height;
        return copy;
    }

    function reserve(host, chart) {
        if (chart && chart.height) host.style.minHeight = (chart.height + APEX_HOST_PADDING) + 'px';
    }

    function panelBlock(panel, plots, size) {
        var block = node('div', 'upri-cap');
        block.appendChild(node('p', 'upri-cap__name', panel.name));
        var figure = node('p', 'upri-cap__value', panel.value != null ? root.format.int(panel.value) : '—');
        figure.style.color = panel.color;
        if (panel.value != null && panel.year != null) {
            figure.appendChild(node('span', 'upri-cap__year', ' ' + panel.year));
        }
        block.appendChild(figure);
        var host = node('div');
        block.appendChild(host);
        var chart = sized(panel.chart, size.panelWidth, size.panelHeight);
        reserve(host, chart);
        plots.push({ host: host, chart: chart });
        return block;
    }

    function gapButtons(gaps) {
        var wrap = node('div', 'upri-gaps');
        (gaps || []).forEach(function (gap) {
            var btn = node('button', 'upri-gap' + (gap.count ? '' : ' is-empty'));
            btn.type = 'button';
            btn.setAttribute('data-upri-gap', gap.id);
            btn.appendChild(node('span', 'upri-gap__count', root.format.int(gap.count)));
            btn.appendChild(node('span', 'upri-gap__label', gap.label));
            wrap.appendChild(btn);
        });
        return wrap;
    }

    // Printed and projected cards cannot click through to a list, so each gap
    // is spelled out with the countries it names.
    function gapLists(gaps, options) {
        var wrap = node('div', 'upri-gap-lists');
        var limit = (options && options.maxNames) || 30;
        (gaps || []).forEach(function (gap) {
            var box = node('div', 'upri-gap-list' + (gap.count ? '' : ' is-empty'));
            var head = node('p', 'upri-gap-list__head');
            head.appendChild(node('span', 'upri-gap__count', root.format.int(gap.count)));
            head.appendChild(node('span', 'upri-gap__label', gap.label));
            box.appendChild(head);
            var rows = (gap.table && gap.table.rows) || [];
            var names = rows.slice(0, limit).map(function (row) { return root.format.cellText((row.cells || [])[0]); });
            var more = rows.length - names.length;
            var text = names.join(', ');
            if (more > 0) text += ', ' + root.format.fill(ui(options).export_more || 'and {n} more', { n: root.format.int(more) });
            box.appendChild(node('p', 'upri-gap-list__names', text));
            wrap.appendChild(box);
        });
        return wrap;
    }

    /**
     * One visual as a card. Returns ``{element, plots}`` where ``plots`` lists
     * the ``{host, chart}`` pairs the caller still has to draw.
     *
     * ``options.interactive === false`` drops the table button and spells the
     * gaps out; ``options.size`` ({width, height, panelWidth, panelHeight})
     * draws the charts at a fixed size; ``options.findings`` is ``visible``
     * (default) or ``steps`` (see renderFindings).
     */
    function renderCard(visual, options) {
        var text = ui(options);
        var interactive = !options || options.interactive !== false;
        var size = (options && options.size) || {};
        var plots = [];
        var section = node('section', 'upri-card' + (visual.wide ? ' upri-card--wide' : ''));
        var headingId = 'upri-vis-' + visual.id + '-h';
        section.setAttribute('data-upri-visual', visual.id);
        section.setAttribute('aria-labelledby', headingId);

        var head = node('div', 'upri-card__head');
        var copy = node('div', 'upri-card__text');
        var title = node('h4', 'upri-card__title', visual.title);
        title.id = headingId;
        copy.appendChild(title);
        var hint = visual.hint || '';
        if (interactive && visual.kind === 'gaps' && text.gaps_select) hint = (hint ? hint + ' ' : '') + text.gaps_select;
        copy.appendChild(node('p', 'upri-card__hint', hint));
        head.appendChild(copy);

        if (visual.table && interactive) {
            var label = visual.table_label || ((text.view_table || 'View as table') + ': ' + visual.title);
            var btn = node('button', 'upri-table-btn');
            btn.type = 'button';
            btn.setAttribute('data-upri-table', visual.id);
            btn.title = visual.table_label || text.view_table || 'View as table';
            btn.setAttribute('aria-label', label);
            btn.appendChild(icon(visual.kind === 'gaps' ? 'fa-border-all' : 'fa-table'));
            head.appendChild(btn);
        }
        section.appendChild(head);

        if (visual.kind === 'panels') {
            var grid = node('div', 'upri-chart upri-cap-grid');
            (visual.panels || []).forEach(function (panel) { grid.appendChild(panelBlock(panel, plots, size)); });
            section.appendChild(grid);
        } else if (visual.kind === 'gaps') {
            section.appendChild(interactive ? gapButtons(visual.gaps) : gapLists(visual.gaps, options));
        } else {
            var host = node('div', 'upri-chart');
            section.appendChild(host);
            if (visual.chart) {
                var chart = sized(visual.chart, size.width, size.height);
                reserve(host, chart);
                plots.push({ host: host, chart: chart });
            }
        }
        if (visual.findings && visual.findings.length) {
            section.appendChild(renderFindings(visual.findings, (options && options.findings) || 'visible', options));
        }
        return { element: section, plots: plots };
    }

    // -- table dialog --------------------------------------------------------

    function paintCell(td, value, options) {
        td.textContent = root.format.cellText(value);
        if (value && value.midyear) {
            td.classList.add('upri-cell--midyear');
            td.title = ui(options).midyear_cell || '';
        }
    }

    function appendRow(body, row, options) {
        var cells = row.cells || [];
        var expandable = !(options && options.static);
        var details = expandable ? (row.countries || []) : [];
        var tr = document.createElement('tr');
        cells.forEach(function (value, index) {
            var td = document.createElement('td');
            if (index === 0 && details.length) {
                var btn = node('button', 'upri-expand');
                btn.type = 'button';
                btn.setAttribute('aria-expanded', 'false');
                btn.setAttribute('aria-label', (ui(options).show_countries || '') + ' ' + root.format.cellText(value));
                var chevron = icon('fa-chevron-right');
                btn.appendChild(chevron);
                btn.appendChild(document.createTextNode(root.format.cellText(value)));
                btn.addEventListener('click', function () {
                    var open = btn.getAttribute('aria-expanded') === 'true';
                    btn.setAttribute('aria-expanded', open ? 'false' : 'true');
                    chevron.className = 'fas ' + (open ? 'fa-chevron-right' : 'fa-chevron-down');
                    var sibling = tr.nextElementSibling;
                    while (sibling && sibling.classList.contains('upri-table__detail')) {
                        sibling.hidden = open;
                        sibling = sibling.nextElementSibling;
                    }
                });
                td.appendChild(btn);
            } else {
                paintCell(td, value, options);
            }
            tr.appendChild(td);
        });
        body.appendChild(tr);
        details.forEach(function (detail) {
            var child = node('tr', 'upri-table__detail');
            child.hidden = true;
            (detail.cells || []).forEach(function (value) {
                var td = document.createElement('td');
                paintCell(td, value, options);
                child.appendChild(td);
            });
            body.appendChild(child);
        });
    }

    function setText(el, text) {
        if (!el) return;
        el.textContent = text || '';
        el.hidden = !text;
    }

    function fillHead(head, columns) {
        head.textContent = '';
        var headRow = document.createElement('tr');
        (columns || []).forEach(function (label) {
            var th = node('th', null, label);
            th.scope = 'col';
            headRow.appendChild(th);
        });
        head.appendChild(headRow);
    }

    /** A view table as a static ``<table>`` (no drill-down) for the printed report. */
    function renderTable(spec, options) {
        var wrap = node('div', 'upri-table-static');
        if (spec.note) wrap.appendChild(node('p', 'upri-dialog__note', spec.note));
        var table = node('table', 'upri-table');
        var head = node('thead');
        var body = node('tbody');
        fillHead(head, spec.columns);
        (spec.rows || []).forEach(function (row) { appendRow(body, row, Object.assign({}, options, { static: true })); });
        table.appendChild(head);
        table.appendChild(body);
        wrap.appendChild(table);
        if (spec.legend) {
            var legend = node('p', 'upri-legend');
            legend.appendChild(node('span', 'upri-legend__swatch'));
            legend.appendChild(node('span', null, spec.legend));
            wrap.appendChild(legend);
        }
        return wrap;
    }

    /** Fill the table dialog with ``spec`` (a view table); does not open it. */
    function fillTable(dialog, spec, options) {
        var title = dialog.querySelector('#upri-table-title');
        var head = dialog.querySelector('#upri-table-head');
        var body = dialog.querySelector('#upri-table-body');
        if (title) title.textContent = spec.title || '';
        setText(dialog.querySelector('#upri-table-note'), spec.note);
        var legend = dialog.querySelector('#upri-table-legend');
        if (legend) {
            var legendText = dialog.querySelector('#upri-table-legend-text');
            if (legendText) legendText.textContent = spec.legend || '';
            legend.hidden = !spec.legend;
        }
        if (head) fillHead(head, spec.columns);
        if (body) body.textContent = '';
        if (body) (spec.rows || []).forEach(function (row) { appendRow(body, row, options); });
    }

    function openTable(dialog, spec, options) {
        if (!dialog || !spec) return;
        fillTable(dialog, spec, options);
        if (typeof dialog.showModal === 'function' && !dialog.open) dialog.showModal();
    }

    // -- export blocks (slides and A4 report) --------------------------------

    function coverBlock(block, options) {
        var el = node('div', 'upri-cover');
        if (options.logoUrl) {
            var logo = node('img', 'upri-cover__logo');
            logo.src = options.logoUrl;
            logo.alt = '';
            el.appendChild(logo);
        }
        el.appendChild(node('h1', 'upri-cover__title', block.title));
        (block.lines || []).forEach(function (line) { el.appendChild(node('p', 'upri-cover__line', line)); });
        if (block.lead) el.appendChild(node('p', 'upri-cover__lead', block.lead));
        return el;
    }

    function sectionBlock(block) {
        var el = node('header', 'upri-section-head');
        el.appendChild(node('h2', 'upri-section-head__title', block.title));
        if (block.lead) el.appendChild(node('p', 'upri-section-head__lead', block.lead));
        return el;
    }

    function notesBlock(block, options) {
        var el = node('div', 'upri-notes-block');
        el.appendChild(node('h4', 'upri-notes-block__title', ui(options).export_notes || ''));
        (block.warnings || []).forEach(function (text) { el.appendChild(node('p', 'upri-warning', text)); });
        (block.notes || []).forEach(function (text) { el.appendChild(node('p', 'upri-footnote', text)); });
        return el;
    }

    function tableBlock(block, options) {
        var el = node('div', 'upri-table-block');
        if (block.first) el.appendChild(node('h3', 'upri-table-block__heading', ui(options).export_tables_heading || ''));
        el.appendChild(node('h4', 'upri-table-block__title', block.visual.title));
        el.appendChild(renderTable(block.visual.table, options));
        return el;
    }

    /**
     * One block of an export outline (UprAnalysis.pages) as DOM: ``{element,
     * plots}``. ``options.size`` sizes its charts; the rest of the look comes
     * from the same classes the tab uses.
     */
    function renderBlock(block, options) {
        options = options || {};
        var plots = [];
        var element;
        switch (block.type) {
            case 'cover':
                element = coverBlock(block, options);
                break;
            case 'section':
                element = sectionBlock(block);
                break;
            case 'kpis':
                element = node('div', 'upri-kpis');
                renderKpis(element, block.kpis);
                break;
            case 'visual':
                var card = renderCard(block.visual, { ui: options.ui, interactive: false, size: options.size, maxNames: options.maxNames, findings: options.findings });
                element = card.element;
                plots = card.plots;
                break;
            case 'notes':
                element = notesBlock(block, options);
                break;
            case 'table':
                element = tableBlock(block, options);
                break;
            default:
                element = node('div');
        }
        element.setAttribute('data-upri-block', block.type);
        return { element: element, plots: plots };
    }

    root.dom = {
        renderBlock: renderBlock,
        renderTable: renderTable,
        renderKpis: renderKpis,
        renderNotes: renderNotes,
        renderWarnings: renderWarnings,
        renderCard: renderCard,
        renderFindings: renderFindings,
        setFindingRevealed: setFindingRevealed,
        fillTable: fillTable,
        openTable: openTable
    };
})(typeof window !== 'undefined' ? window : globalThis);
