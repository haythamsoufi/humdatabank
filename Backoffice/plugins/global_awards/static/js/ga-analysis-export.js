/* Global Awards presentation (16:9) and A4 PDF report. */
(function (global) {
    'use strict';

    var root = global.GaAnalysis = global.GaAnalysis || {};
    var STAGE = { width: 1280, height: 720 };
    var SLIDE_CHART = { width: 1150, height: 430 };
    var PAGE_CHART = { width: 640, height: 280 };
    var currentDeck = null;
    var currentReport = null;

    function node(tag, className, text) {
        var el = document.createElement(tag);
        if (className) el.className = className;
        if (text != null) el.textContent = text;
        return el;
    }
    function iconButton(className, iconName, label) {
        var btn = node('button', className);
        btn.type = 'button';
        btn.title = label;
        btn.setAttribute('aria-label', label);
        var i = node('i', 'fas ' + iconName);
        i.setAttribute('aria-hidden', 'true');
        btn.appendChild(i);
        return btn;
    }

    function coverBlock(analysis, options) {
        var meta = analysis.meta || {};
        var cover = node('div', 'gai-cover');
        if (options.logoUrl) {
            var logo = node('img', 'gai-cover__logo');
            logo.src = options.logoUrl;
            logo.alt = 'IFRC';
            cover.appendChild(logo);
        }
        cover.appendChild(node('h1', 'gai-cover__title', 'Global Awards'));
        cover.appendChild(node('p', 'gai-cover__line', meta.award_label || ''));
        var filterBits = [];
        if (meta.region) filterBits.push(meta.region);
        if (meta.cycle) filterBits.push(meta.cycle);
        if (filterBits.length) cover.appendChild(node('p', 'gai-cover__line', filterBits.join(' · ')));
        cover.appendChild(node('p', 'gai-cover__lead', (options.ui && options.ui.export_cover_lead) || ''));
        return { type: 'cover', title: 'Global Awards', element: cover };
    }

    function kpisBlock(analysis) {
        var wrap = node('div', 'gai-kpis');
        (analysis.kpis || []).forEach(function (kpi) {
            var card = node('div', 'gai-kpi');
            card.appendChild(node('p', 'gai-kpi__label', kpi.label || ''));
            card.appendChild(node('p', 'gai-kpi__value', kpi.value == null ? '—' : String(kpi.value)));
            if (kpi.meta) card.appendChild(node('p', 'gai-kpi__meta', kpi.meta));
            wrap.appendChild(card);
        });
        return { type: 'kpis', title: (analysis && analysis.kpis && 'Headline figures') || '', element: wrap };
    }

    function calendarBlock(analysis, ui) {
        var wrap = node('div', 'gai-calendar');
        (analysis.cycles || []).forEach(function (cycle) {
            var card = node('div', 'gai-cycle');
            card.appendChild(node('p', 'gai-cycle__slot', cycle.slot || ''));
            card.appendChild(node('p', 'gai-cycle__meta', (ui.due || 'Country due') + ' ' + (cycle.country_due || '')));
            var total = cycle.total || 0;
            var bar = node('div', 'gai-cycle__bar');
            [['approved', '#6ba543'], ['submitted', '#3d7ea6'], ['progress', '#f39200'], ['pending', '#d1d5db']].forEach(function (pair) {
                var count = cycle[pair[0]] || 0;
                if (!total || !count) return;
                var seg = node('span', 'gai-cycle__seg');
                seg.style.width = (100 * count / total) + '%';
                seg.style.background = pair[1];
                bar.appendChild(seg);
            });
            card.appendChild(bar);
            wrap.appendChild(card);
        });
        return { type: 'calendar', title: ui.calendar || 'Reporting calendar', element: wrap };
    }

    function chartBlock(spec) {
        var card = node('article', 'gai-card');
        var head = node('div', 'gai-card__text');
        head.appendChild(node('h3', 'gai-card__title', spec.title || ''));
        if (spec.hint) head.appendChild(node('p', 'gai-card__hint', spec.hint));
        card.appendChild(head);
        var plot = node('div', 'gai-chart');
        card.appendChild(plot);
        return { type: 'visual', id: spec.id, title: spec.title, spec: spec, element: card, plot: plot, section: spec.section };
    }

    function tableBlock(table) {
        if (!table || !(table.rows || []).length) return null;
        var wrap = node('div', 'gai-table-wrap');
        wrap.appendChild(node('h3', 'gai-card__title', table.title || ''));
        var el = node('table', 'gai-table');
        var thead = node('thead');
        var tr = node('tr');
        (table.columns || []).forEach(function (col) {
            tr.appendChild(node('th', '', col.label || col.key));
        });
        thead.appendChild(tr);
        el.appendChild(thead);
        var tbody = node('tbody');
        table.rows.slice(0, 28).forEach(function (row) {
            var line = node('tr');
            (table.columns || []).forEach(function (col) {
                line.appendChild(node('td', '', row[col.key] == null ? '—' : String(row[col.key])));
            });
            tbody.appendChild(line);
        });
        el.appendChild(tbody);
        wrap.appendChild(el);
        return { type: 'table', title: table.title, element: wrap };
    }

    function sectionHead(title, lead) {
        var head = node('div', 'gai-section-head');
        head.appendChild(node('h2', 'gai-section-head__title', title));
        if (lead) head.appendChild(node('p', 'gai-section-head__lead', lead));
        return { type: 'section', title: title, element: head };
    }

    function buildOutline(analysis, options) {
        var selected = options.selected || [];
        var include = function (id) { return !selected.length || selected.indexOf(id) !== -1; };
        var blocks = [];
        if (include('cover')) blocks.push(coverBlock(analysis, options));
        if (include('overview')) {
            blocks.push(sectionHead(options.ui.overview || 'Overview', analysis.meta && analysis.meta.goal));
            blocks.push(kpisBlock(analysis));
            if ((analysis.cycles || []).length) blocks.push(calendarBlock(analysis, options.ui || {}));
        }
        (analysis.charts || []).forEach(function (spec) {
            var section = spec.section || 'overview';
            if (include(section) || include(spec.id)) blocks.push(chartBlock(spec));
        });
        if (options.includeTables) {
            if (include('countries')) {
                var countries = tableBlock((analysis.tables || {}).countries);
                if (countries) blocks.push(countries);
            }
            if (include('logframe')) {
                var indicators = tableBlock((analysis.tables || {}).indicators);
                if (indicators) blocks.push(indicators);
            }
        }
        return blocks;
    }

    function exportSections(analysis, ui) {
        var charts = analysis.charts || [];
        return [
            { id: 'cover', label: 'Cover', available: true },
            { id: 'overview', label: ui.overview || 'Overview', available: true },
            { id: 'logframe', label: ui.logframe || 'Logframe', available: charts.some(function (c) { return c.section === 'logframe'; }) },
            { id: 'countries', label: ui.countries || 'Countries', available: !!(analysis.tables && analysis.tables.countries && analysis.tables.countries.rows && analysis.tables.countries.rows.length) }
        ];
    }

    function mountCharts(blocks, size) {
        var charts = [];
        blocks.forEach(function (block) {
            if (block.type !== 'visual' || !block.plot || !root.charts) return;
            var chart = root.charts.mount(block.plot, block.spec, size);
            if (chart) charts.push(chart);
        });
        return charts;
    }

    function openDeck(blocks, options) {
        if (currentDeck) currentDeck.close();
        var ui = options.ui || {};
        var overlay = node('div', 'gai-overlay gai-deck');
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');
        overlay.tabIndex = -1;
        var viewport = node('div', 'gai-deck__viewport');
        var stage = node('div', 'gai-deck__stage');
        stage.style.width = STAGE.width + 'px';
        stage.style.height = STAGE.height + 'px';
        var slides = [];
        blocks.forEach(function (block) {
            if (block.type === 'table') return;
            var slide = node('section', 'gai-slide gai-slide--' + block.type);
            slide.setAttribute('aria-roledescription', 'slide');
            if (block.section) slide.appendChild(node('p', 'gai-slide__tag', block.section));
            slide.appendChild(block.element);
            stage.appendChild(slide);
            slides.push(slide);
        });
        viewport.appendChild(stage);
        overlay.appendChild(viewport);

        var bar = node('div', 'gai-deck__bar');
        var prev = iconButton('gai-deck__btn', 'fa-chevron-left', ui.export_prev || 'Previous slide');
        var next = iconButton('gai-deck__btn', 'fa-chevron-right', ui.export_next || 'Next slide');
        var counter = node('span', 'gai-deck__counter');
        var nav = node('div', 'gai-deck__nav');
        nav.appendChild(prev);
        nav.appendChild(counter);
        nav.appendChild(next);
        bar.appendChild(nav);
        var tools = node('div', 'gai-deck__tools');
        var full = iconButton('gai-deck__btn', 'fa-expand', ui.export_fullscreen || 'Full screen');
        var closeBtn = iconButton('gai-deck__btn', 'fa-times', ui.close || 'Close');
        if (typeof overlay.requestFullscreen === 'function') tools.appendChild(full);
        tools.appendChild(closeBtn);
        bar.appendChild(tools);
        stage.appendChild(bar);
        var progress = node('div', 'gai-deck__progress');
        var fill = node('span');
        progress.appendChild(fill);
        stage.appendChild(progress);

        document.body.appendChild(overlay);
        document.body.classList.add('gai-locked');
        var charts = mountCharts(blocks, SLIDE_CHART);
        var index = 0;

        function go(to) {
            index = Math.max(0, Math.min(slides.length - 1, to));
            slides.forEach(function (slide, i) {
                slide.classList.toggle('is-active', i === index);
            });
            overlay.classList.toggle('is-on-cover', slides[index] && slides[index].classList.contains('gai-slide--cover'));
            counter.textContent = (index + 1) + ' / ' + slides.length;
            prev.disabled = index === 0;
            next.disabled = index === slides.length - 1;
            fill.style.width = ((index + 1) / slides.length * 100) + '%';
        }
        function fit() {
            var w = viewport.clientWidth;
            var h = viewport.clientHeight;
            if (!w || !h) return;
            var scale = Math.min(w / STAGE.width, h / STAGE.height);
            stage.style.transform = 'translate(-50%, -50%) scale(' + scale + ')';
        }
        function onKey(event) {
            if (event.key === 'Escape') { event.preventDefault(); api.close(); }
            if (event.key === 'ArrowRight' || event.key === 'PageDown') { event.preventDefault(); go(index + 1); }
            if (event.key === 'ArrowLeft' || event.key === 'PageUp') { event.preventDefault(); go(index - 1); }
        }
        var api = {
            close: function () {
                document.removeEventListener('keydown', onKey, true);
                global.removeEventListener('resize', fit);
                charts.forEach(function (chart) { try { chart.destroy(); } catch (e) { /* noop */ } });
                overlay.remove();
                document.body.classList.remove('gai-locked');
                if (currentDeck === api) currentDeck = null;
            }
        };
        prev.addEventListener('click', function () { go(index - 1); });
        next.addEventListener('click', function () { go(index + 1); });
        closeBtn.addEventListener('click', api.close);
        if (full) {
            full.addEventListener('click', function () {
                if (document.fullscreenElement === overlay) document.exitFullscreen();
                else overlay.requestFullscreen();
            });
        }
        document.addEventListener('keydown', onKey, true);
        global.addEventListener('resize', fit);
        go(0);
        fit();
        currentDeck = api;
        overlay.focus();
        return api;
    }

    function overflows(body) {
        return body.scrollHeight > body.clientHeight + 1;
    }

    function openReport(blocks, options) {
        if (currentReport) currentReport.close();
        var ui = options.ui || {};
        var overlay = node('div', 'gai-overlay gai-report');
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');
        var bar = node('div', 'gai-report__bar');
        var copy = node('div', 'gai-report__copy');
        copy.appendChild(node('div', 'gai-report__title', options.title || 'Global Awards'));
        var hint = node('p', 'gai-report__hint', ui.export_cover_lead || '');
        copy.appendChild(hint);
        bar.appendChild(copy);
        var actions = node('div', 'gai-report__actions');
        var printBtn = node('button', 'gai-btn gai-btn--primary', ui.export_print || 'Download PDF');
        printBtn.type = 'button';
        var closeBtn = node('button', 'gai-btn', ui.close || 'Close');
        closeBtn.type = 'button';
        actions.appendChild(printBtn);
        actions.appendChild(closeBtn);
        bar.appendChild(actions);
        overlay.appendChild(bar);
        var frame = node('div', 'gai-report__frame');
        var pagesEl = node('div', 'gai-report__pages');
        frame.appendChild(pagesEl);
        overlay.appendChild(frame);
        document.body.appendChild(overlay);
        document.body.classList.add('gai-locked');

        function newPage(extra) {
            var page = node('div', 'gai-page' + (extra ? ' ' + extra : ''));
            var body = node('div', 'gai-page__body');
            page.appendChild(body);
            if (!extra) {
                var foot = node('footer', 'gai-page__foot');
                foot.appendChild(node('span'));
                foot.appendChild(node('span'));
                page.appendChild(foot);
            }
            pagesEl.appendChild(page);
            return { page: page, body: body };
        }

        var charts = [];
        var cur = null;
        blocks.forEach(function (block) {
            if (block.type === 'cover') {
                var cover = newPage('gai-page--cover');
                cover.body.appendChild(block.element);
                cur = null;
                return;
            }
            if (!cur || (block.type === 'section' && cur.body.children.length)) {
                cur = newPage();
            }
            cur.body.appendChild(block.element);
            if (cur.body.children.length > 1 && overflows(cur.body)) {
                cur.body.removeChild(block.element);
                cur = newPage();
                cur.body.appendChild(block.element);
            }
        });
        charts = mountCharts(blocks, PAGE_CHART);

        var contentPages = Array.prototype.filter.call(pagesEl.children, function (page) {
            return !page.classList.contains('gai-page--cover');
        });
        contentPages.forEach(function (page, i) {
            var spans = page.querySelectorAll('.gai-page__foot span');
            if (spans[0]) spans[0].textContent = options.title || 'Global Awards';
            if (spans[1]) spans[1].textContent = (ui.page || 'Page') + ' ' + (i + 1) + ' ' + (ui.of || 'of') + ' ' + contentPages.length;
        });

        function fit() {
            var first = pagesEl.querySelector('.gai-page');
            if (!first) return;
            var natural = first.offsetWidth;
            var avail = overlay.clientWidth - 32;
            if (!natural || avail <= 0) return;
            var scale = Math.min(1, avail / natural);
            pagesEl.style.width = natural + 'px';
            pagesEl.style.transform = 'translateX(-50%) scale(' + scale + ')';
            frame.style.height = Math.ceil(pagesEl.offsetHeight * scale) + 'px';
        }

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
        function ensureLibs() {
            var urls = options.pdf || {};
            var jobs = [];
            if (typeof global.html2canvas !== 'function') jobs.push(loadScript(urls.html2canvas));
            if (!global.jspdf || !global.jspdf.jsPDF) jobs.push(loadScript(urls.jspdf));
            return jobs.length ? Promise.all(jobs) : Promise.resolve();
        }
        function capturePage(pageEl) {
            var host = node('div');
            host.setAttribute('aria-hidden', 'true');
            host.style.cssText = 'position:fixed;left:0;top:0;width:210mm;z-index:-1;pointer-events:none;';
            var clone = pageEl.cloneNode(true);
            host.appendChild(clone);
            document.body.appendChild(host);
            return global.html2canvas(clone, { scale: 2, backgroundColor: '#ffffff', logging: false }).then(function (canvas) {
                host.remove();
                return canvas;
            }, function (error) {
                host.remove();
                throw error;
            });
        }
        function download() {
            printBtn.disabled = true;
            ensureLibs().then(function () {
                var pdf = new global.jspdf.jsPDF({ unit: 'mm', format: 'a4', orientation: 'portrait', compress: true });
                var pages = Array.prototype.slice.call(pagesEl.querySelectorAll('.gai-page'));
                var index = 0;
                function next() {
                    if (index >= pages.length) {
                        pdf.save('Global Awards.pdf');
                        return;
                    }
                    var first = index === 0;
                    var pageEl = pages[index];
                    index += 1;
                    return capturePage(pageEl).then(function (canvas) {
                        if (!first) pdf.addPage();
                        var height = 210 * canvas.height / canvas.width;
                        pdf.addImage(canvas.toDataURL('image/jpeg', 0.92), 'JPEG', 0, 0, 210, Math.min(height, 297));
                        return next();
                    });
                }
                return next();
            }).catch(function () {
                hint.textContent = ui.export_pdf_failed || 'Could not create the PDF. Try again.';
            }).then(function () {
                printBtn.disabled = false;
            });
        }

        var api = {
            close: function () {
                global.removeEventListener('resize', fit);
                document.removeEventListener('keydown', onKey, true);
                charts.forEach(function (chart) { try { chart.destroy(); } catch (e) { /* noop */ } });
                overlay.remove();
                document.body.classList.remove('gai-locked');
                if (currentReport === api) currentReport = null;
            }
        };
        function onKey(event) {
            if (event.key === 'Escape') { event.preventDefault(); api.close(); }
        }
        printBtn.addEventListener('click', download);
        closeBtn.addEventListener('click', api.close);
        document.addEventListener('keydown', onKey, true);
        global.addEventListener('resize', fit);
        fit();
        currentReport = api;
        return api;
    }

    function open(button, analysis, cfg) {
        var ui = (cfg && cfg.ui) || {};
        var dialog = document.getElementById('gai-export-dialog');
        var list = document.getElementById('gai-export-list');
        var title = document.getElementById('gai-export-title');
        var go = document.getElementById('gai-export-go');
        var tablesRow = document.getElementById('gai-export-tables-row');
        var tables = document.getElementById('gai-export-tables');
        var empty = document.getElementById('gai-export-empty');
        var form = document.getElementById('gai-export-form');
        if (!dialog || !list || !form) return;
        var mode = button.getAttribute('data-gai-export');
        var entries = exportSections(analysis, ui);
        list.replaceChildren();
        entries.forEach(function (entry) {
            var label = node('label', 'gai-check' + (entry.available ? '' : ' is-disabled'));
            var input = document.createElement('input');
            input.type = 'checkbox';
            input.value = entry.id;
            input.checked = entry.available;
            input.disabled = !entry.available;
            label.appendChild(input);
            label.appendChild(node('span', '', entry.label));
            list.appendChild(label);
        });
        title.textContent = button.textContent.trim();
        go.textContent = button.getAttribute('data-go-label') || '';
        tablesRow.hidden = mode !== 'report';
        empty.hidden = true;
        dialog.showModal();
        form.onsubmit = function (event) {
            event.preventDefault();
            var selected = Array.prototype.map.call(list.querySelectorAll('input:checked'), function (box) { return box.value; });
            var blocks = buildOutline(analysis, {
                ui: ui,
                logoUrl: cfg.logoUrl,
                selected: selected,
                includeTables: mode === 'report' && tables && tables.checked
            });
            dialog.close();
            if (!blocks.length) return;
            var options = { ui: ui, logoUrl: cfg.logoUrl, title: 'Global Awards', pdf: cfg.pdf };
            if (mode === 'present') openDeck(blocks, options);
            else openReport(blocks, options);
        };
    }

    root.export = { open: open, buildOutline: buildOutline };
})(window);
