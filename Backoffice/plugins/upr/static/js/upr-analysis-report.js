/* UPR Analysis — A4 report. Lays the export outline (upr-analysis-pages.js) out
 * on A4 pages with the same renderers as the tab (UprAnalysis.dom / .charts), then
 * hands the pages to the browser's print dialog ("Save as PDF").
 *
 * Printing the live DOM rather than rasterising it keeps the ApexCharts SVG
 * sharp and the text selectable, and the report looks exactly like the tab. Pages
 * are fixed-size (210x297mm) so the charts get an explicit width, and blocks are
 * moved to a new page as soon as they no longer fit. */
(function (global) {
    'use strict';

    var root = global.UprAnalysis = global.UprAnalysis || {};

    // Matches the page and card paddings in upr-analysis-export.css.
    var CHART_SIZE = { width: 640, height: 300, panelWidth: 296, panelHeight: 150 };
    var current = null;

    function node(tag, className, text) {
        var el = document.createElement(tag);
        if (className) el.className = className;
        if (text != null) el.textContent = text;
        return el;
    }

    function overflows(body) {
        return body.scrollHeight > body.clientHeight + 1;
    }

    // A section heading stays with the KPI strip that follows it.
    function group(blocks, options) {
        var items = [];
        blocks.forEach(function (block, i) {
            var made = root.dom.renderBlock(block, { ui: options.ui, logoUrl: options.logoUrl, size: CHART_SIZE, maxNames: 40 });
            var prev = items[items.length - 1];
            if (block.type === 'kpis' && prev && prev.block.type === 'section' && !prev.kept) {
                var keep = node('div', 'upri-keep');
                keep.appendChild(prev.element);
                keep.appendChild(made.element);
                prev.element = keep;
                prev.kept = true;
                return;
            }
            items.push({ block: block, element: made.element, plots: made.plots, index: i });
        });
        return items;
    }

    // The footer exists from the start so its height is part of every measurement.
    function newPage(pages, extra) {
        var page = node('div', 'upri-page' + (extra ? ' ' + extra : ''));
        var body = node('div', 'upri-page__body');
        page.appendChild(body);
        if (!extra) {
            var foot = node('footer', 'upri-page__foot');
            foot.appendChild(node('span'));
            foot.appendChild(node('span'));
            page.appendChild(foot);
        }
        pages.appendChild(page);
        return { page: page, body: body };
    }

    function layout(pagesEl, items) {
        var cur = null;
        var all = [];
        items.forEach(function (item) {
            if (item.block.type === 'cover') {
                var cover = newPage(pagesEl, 'upri-page--cover');
                cover.body.appendChild(item.element);
                all.push(cover.page);
                cur = null;
                return;
            }
            var startsSection = item.block.type === 'section';
            if (!cur || (startsSection && cur.body.children.length)) {
                cur = newPage(pagesEl);
                all.push(cur.page);
            }
            cur.body.appendChild(item.element);
            if (cur.body.children.length > 1 && overflows(cur.body)) {
                cur.body.removeChild(item.element);
                cur = newPage(pagesEl);
                all.push(cur.page);
                cur.body.appendChild(item.element);
            }
        });
        return all;
    }

    function startsSection(page) {
        var first = page.querySelector('.upri-page__body').firstElementChild;
        return !!first && (first.classList.contains('upri-keep') || first.getAttribute('data-upri-block') === 'section');
    }

    // Text can re-wrap after pagination (web fonts arrive late), so push whatever
    // no longer fits onto the next page, opening a new one where needed.
    function reflow(pagesEl) {
        var pages = Array.prototype.slice.call(pagesEl.children);
        for (var i = 0; i < pages.length; i++) {
            if (pages[i].classList.contains('upri-page--cover')) continue;
            var body = pages[i].querySelector('.upri-page__body');
            while (body.children.length > 1 && overflows(body)) {
                var next = pages[i + 1];
                if (!next || next.classList.contains('upri-page--cover') || startsSection(next)) {
                    next = newPage(pagesEl).page;
                    pagesEl.insertBefore(next, pages[i].nextSibling);
                    pages.splice(i + 1, 0, next);
                }
                var target = next.querySelector('.upri-page__body');
                target.insertBefore(body.lastElementChild, target.firstChild);
            }
        }
    }

    function addFooters(pagesEl, title, ui) {
        var pages = Array.prototype.slice.call(pagesEl.children);
        var content = pages.filter(function (page) { return !page.classList.contains('upri-page--cover'); });
        content.forEach(function (page, i) {
            var spans = page.querySelectorAll('.upri-page__foot span');
            spans[0].textContent = title;
            spans[1].textContent = root.format.fill(ui.export_page || 'Page {n} of {total}', { n: i + 1, total: content.length });
        });
    }

    function close() {
        if (current) current.close();
    }

    // The @page / hide-the-app rules apply only while a report is open.
    function setPrintRules(on) {
        var sheet = document.getElementById('upri-report-print-css');
        if (sheet) sheet.media = on ? 'print' : 'not all';
    }

    /**
     * Open the report preview. ``options``: ``{ui, logoUrl, title}``. Returns
     * ``{close, print, pageCount}``; only one report exists at a time.
     */
    function open(blocks, options) {
        options = options || {};
        var ui = options.ui || {};
        close();
        if (!blocks.length) return null;

        var overlay = node('div', 'upri-overlay upri-report');
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');
        overlay.setAttribute('aria-label', options.title || '');
        overlay.tabIndex = -1;

        var toolbar = node('div', 'upri-report__bar');
        var copy = node('div', 'upri-report__copy');
        copy.appendChild(node('strong', 'upri-report__title', options.title || ''));
        copy.appendChild(node('span', 'upri-report__hint', ui.export_print_hint || ''));
        toolbar.appendChild(copy);
        var actions = node('div', 'upri-report__actions');
        var printBtn = node('button', 'upri-btn upri-btn--primary');
        printBtn.type = 'button';
        var printIcon = node('i', 'fas fa-print');
        printIcon.setAttribute('aria-hidden', 'true');
        printBtn.appendChild(printIcon);
        printBtn.appendChild(node('span', null, ui.export_print || 'Print'));
        var closeBtn = node('button', 'upri-btn');
        closeBtn.type = 'button';
        closeBtn.appendChild(node('span', null, ui.close || 'Close'));
        actions.appendChild(printBtn);
        actions.appendChild(closeBtn);
        toolbar.appendChild(actions);
        overlay.appendChild(toolbar);

        var pagesEl = node('div', 'upri-report__pages');
        overlay.appendChild(pagesEl);

        var opener = document.activeElement;
        document.body.appendChild(overlay);
        document.body.classList.add('upri-locked', 'upri-report-open');
        setPrintRules(true);

        var items = group(blocks, options);
        layout(pagesEl, items);
        addFooters(pagesEl, options.title || '', ui);

        var plots = [];
        items.forEach(function (item) { plots = plots.concat(item.plots); });
        var charts = root.charts.mountAll(plots, { animate: false });
        overlay.focus();

        function settle() {
            if (current !== api) return;
            reflow(pagesEl);
            addFooters(pagesEl, options.title || '', ui);
        }
        if (document.fonts && document.fonts.ready) document.fonts.ready.then(settle);

        function print() {
            global.print();
        }

        function onKey(event) {
            if (event.key !== 'Escape') return;
            event.preventDefault();
            event.stopPropagation();
            api.close();
        }

        printBtn.addEventListener('click', print);
        closeBtn.addEventListener('click', function () { api.close(); });
        document.addEventListener('keydown', onKey, true);

        var api = {
            print: print,
            get pageCount() {
                return pagesEl.children.length;
            },
            close: function () {
                document.removeEventListener('keydown', onKey, true);
                charts.forEach(function (chart) {
                    try { chart.destroy(); } catch (e) { /* noop */ }
                });
                overlay.remove();
                document.body.classList.remove('upri-locked', 'upri-report-open');
                setPrintRules(false);
                if (opener && typeof opener.focus === 'function') opener.focus();
                if (current === api) current = null;
            }
        };
        current = api;
        return api;
    }

    root.report = { open: open, close: close, CHART_SIZE: CHART_SIZE };
})(typeof window !== 'undefined' ? window : globalThis);
