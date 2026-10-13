/* UPR Analysis — DOM renderers for a view (plugins/upr/analysis_spec.py):
 * KPI cards, visual cards, notes and the drill-down table dialog. They only
 * read the view they are given, so a browser presentation can reuse the same
 * cards on its slides. Charts are not drawn here: renderCard reports where each
 * one goes ({host, chart}) and the caller mounts it with UprAnalysis.charts. */
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

    // -- visual cards --------------------------------------------------------

    function panelBlock(panel, plots) {
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
        plots.push({ host: host, chart: panel.chart });
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

    /**
     * One visual as a card. Returns ``{element, plots}`` where ``plots`` lists
     * the ``{host, chart}`` pairs the caller still has to draw.
     */
    function renderCard(visual, options) {
        var text = ui(options);
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
        copy.appendChild(node('p', 'upri-card__hint', visual.hint || ''));
        head.appendChild(copy);

        if (visual.table) {
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
            (visual.panels || []).forEach(function (panel) { grid.appendChild(panelBlock(panel, plots)); });
            section.appendChild(grid);
        } else if (visual.kind === 'gaps') {
            section.appendChild(gapButtons(visual.gaps));
        } else {
            var host = node('div', 'upri-chart');
            section.appendChild(host);
            if (visual.chart) plots.push({ host: host, chart: visual.chart });
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
        var details = row.countries || [];
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
        if (head) head.textContent = '';
        if (body) body.textContent = '';
        var headRow = document.createElement('tr');
        (spec.columns || []).forEach(function (label) {
            var th = node('th', null, label);
            th.scope = 'col';
            headRow.appendChild(th);
        });
        if (head) head.appendChild(headRow);
        if (body) (spec.rows || []).forEach(function (row) { appendRow(body, row, options); });
    }

    function openTable(dialog, spec, options) {
        if (!dialog || !spec) return;
        fillTable(dialog, spec, options);
        if (typeof dialog.showModal === 'function' && !dialog.open) dialog.showModal();
    }

    root.dom = {
        renderKpis: renderKpis,
        renderNotes: renderNotes,
        renderWarnings: renderWarnings,
        renderCard: renderCard,
        fillTable: fillTable,
        openTable: openTable
    };
})(typeof window !== 'undefined' ? window : globalThis);
