/* UPR Analysis — A4 report. Lays the export outline (upr-analysis-pages.js) out
 * on A4 pages with the same renderers as the tab (UprAnalysis.dom / .charts).
 * Download draws those pages into an A4 PDF (html2canvas + jsPDF, already
 * vendored) and saves the file. No print dialog.
 *
 * Pages are fixed-size (210x297mm) so the charts get an explicit width, and
 * blocks move to a new page as soon as they no longer fit. On a narrow screen
 * the preview is scaled down to the phone. The download captures each page at
 * full A4 size, so the file does not inherit that shrink. */
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
        var hintEl = node('span', 'upri-report__hint', ui.export_print_hint || '');
        var hintText = hintEl.textContent;
        copy.appendChild(hintEl);
        toolbar.appendChild(copy);
        var actions = node('div', 'upri-report__actions');
        var printBtn = node('button', 'upri-btn upri-btn--primary');
        printBtn.type = 'button';
        var printIcon = node('i', 'fas fa-download');
        printIcon.setAttribute('aria-hidden', 'true');
        printBtn.appendChild(printIcon);
        var label = node('span', null, ui.export_print || 'Download PDF');
        printBtn.appendChild(label);
        var closeBtn = node('button', 'upri-btn');
        closeBtn.type = 'button';
        closeBtn.appendChild(node('span', null, ui.close || 'Close'));
        actions.appendChild(printBtn);
        actions.appendChild(closeBtn);
        toolbar.appendChild(actions);
        overlay.appendChild(toolbar);

        var frame = node('div', 'upri-report__frame');
        var pagesEl = node('div', 'upri-report__pages');
        frame.appendChild(pagesEl);
        overlay.appendChild(frame);

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

        // The pages stay 210mm wide so pagination does not change. A transform
        // only shrinks the preview; print CSS and beforeprint remove it.
        var GUTTER = 16;

        function fit() {
            var page = pagesEl.querySelector('.upri-page');
            if (!page) return;
            var natural = page.offsetWidth;
            var avail = overlay.clientWidth - GUTTER;
            if (!natural || avail <= 0) return;
            var scale = Math.min(1, avail / natural);
            var height = pagesEl.offsetHeight;
            pagesEl.style.width = natural + 'px';
            pagesEl.style.transform = 'translateX(-50%) scale(' + scale + ')';
            frame.style.height = Math.ceil(height * scale) + 'px';
        }

        function settle() {
            if (current !== api) return;
            reflow(pagesEl);
            addFooters(pagesEl, options.title || '', ui);
            fit();
        }
        if (document.fonts && document.fonts.ready) document.fonts.ready.then(settle);

        function beforePrint() {
            pagesEl.style.transform = 'none';
            frame.style.height = 'auto';
        }

        var loadingLibs = null;

        function loadScript(src) {
            return new Promise(function (resolve, reject) {
                if (!src) { reject(new Error('missing pdf library')); return; }
                var script = document.createElement('script');
                script.src = src;
                script.async = true;
                if (options.pdf && options.pdf.nonce) script.nonce = options.pdf.nonce;
                script.onload = function () { resolve(); };
                script.onerror = function () { reject(new Error('pdf library failed')); };
                document.head.appendChild(script);
            });
        }

        // html2canvas and jsPDF ship with the Backoffice. Load them on demand.
        function ensureLibs() {
            if (typeof global.html2canvas === 'function' && global.jspdf && global.jspdf.jsPDF) {
                return Promise.resolve();
            }
            if (!loadingLibs) {
                var urls = options.pdf || {};
                var jobs = [];
                if (typeof global.html2canvas !== 'function') jobs.push(loadScript(urls.html2canvas));
                if (!global.jspdf || !global.jspdf.jsPDF) jobs.push(loadScript(urls.jspdf));
                loadingLibs = Promise.all(jobs).then(function () {
                    if (typeof global.html2canvas !== 'function' || !global.jspdf || !global.jspdf.jsPDF) {
                        throw new Error('pdf library missing');
                    }
                });
            }
            return loadingLibs;
        }

        // The on-screen pages may be CSS-scaled to the phone. A clone at the
        // real 210mm size is what gets drawn, so the PDF stays sharp.
        function capturePage(pageEl) {
            var host = node('div');
            host.setAttribute('aria-hidden', 'true');
            host.style.cssText = 'position:fixed;left:0;top:0;width:210mm;z-index:-1;pointer-events:none;';
            var clone = pageEl.cloneNode(true);
            host.appendChild(clone);
            document.body.appendChild(host);
            return global.html2canvas(clone, {
                scale: 2,
                backgroundColor: '#ffffff',
                logging: false
            }).then(function (canvas) {
                host.remove();
                return canvas;
            }, function (error) {
                host.remove();
                throw error;
            });
        }

        function buildPdf(pages) {
            var pdf = new global.jspdf.jsPDF({ unit: 'mm', format: 'a4', orientation: 'portrait', compress: true });
            var index = 0;
            function next() {
                if (index >= pages.length) return Promise.resolve(pdf);
                var pageEl = pages[index];
                var first = index === 0;
                index += 1;
                return capturePage(pageEl).then(function (canvas) {
                    if (!first) pdf.addPage();
                    var height = 210 * canvas.height / canvas.width;
                    pdf.addImage(canvas.toDataURL('image/jpeg', 0.92), 'JPEG', 0, 0, 210, Math.min(height, 297));
                    canvas.width = 0;
                    canvas.height = 0;
                    return next();
                });
            }
            return next();
        }

        function fileName() {
            var raw = (options.title || 'analysis').trim();
            var safe = raw.replace(/[\\/:*?"<>|]+/g, '').replace(/\s+/g, ' ').slice(0, 80).trim();
            return (safe || 'analysis') + '.pdf';
        }

        function download() {
            if (printBtn.disabled) return;
            printBtn.disabled = true;
            printBtn.setAttribute('aria-busy', 'true');
            label.textContent = ui.export_pdf_working || 'Preparing PDF…';
            if (hintEl) hintEl.textContent = '';
            var pages = Array.prototype.slice.call(pagesEl.querySelectorAll('.upri-page'));
            ensureLibs().then(function () {
                return buildPdf(pages);
            }).then(function (pdf) {
                pdf.save(fileName());
            }).catch(function () {
                if (hintEl) hintEl.textContent = ui.export_pdf_failed || 'Could not create the PDF. Try again.';
            }).then(function () {
                printBtn.disabled = false;
                printBtn.removeAttribute('aria-busy');
                label.textContent = ui.export_print || 'Download PDF';
                if (hintEl && !hintEl.textContent) hintEl.textContent = hintText;
            });
        }

        function onKey(event) {
            if (event.key !== 'Escape') return;
            event.preventDefault();
            event.stopPropagation();
            api.close();
        }

        printBtn.addEventListener('click', download);
        closeBtn.addEventListener('click', function () { api.close(); });
        document.addEventListener('keydown', onKey, true);
        global.addEventListener('resize', fit);
        global.addEventListener('beforeprint', beforePrint);
        global.addEventListener('afterprint', fit);
        fit();

        var api = {
            download: download,
            get pageCount() {
                return pagesEl.children.length;
            },
            close: function () {
                document.removeEventListener('keydown', onKey, true);
                global.removeEventListener('resize', fit);
                global.removeEventListener('beforeprint', beforePrint);
                global.removeEventListener('afterprint', fit);
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
