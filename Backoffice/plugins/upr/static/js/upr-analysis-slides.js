/* UPR Analysis — presentation. Lays the export outline (upr-analysis-pages.js)
 * out as a 16:9 slide deck: one slide per KPI strip and per visual, drawn by
 * the same renderers as the tab (UprAnalysis.dom / .charts), only larger.
 *
 * Slides live on a fixed 1280x720 stage that is scaled to the screen with a CSS
 * transform. ApexCharts cannot measure a scaled container, so every chart is
 * given an explicit size instead. */
(function (global) {
    'use strict';

    var root = global.UprAnalysis = global.UprAnalysis || {};

    var STAGE = { width: 1280, height: 720 };
    var CHART_SIZE = { width: 1150, height: 470, panelWidth: 540, panelHeight: 170 };
    var current = null;

    function node(tag, className, text) {
        var el = document.createElement(tag);
        if (className) el.className = className;
        if (text != null) el.textContent = text;
        return el;
    }

    function iconButton(className, iconName, label) {
        var btn = node('button', 'upri-deck__btn ' + className);
        btn.type = 'button';
        btn.title = label;
        btn.setAttribute('aria-label', label);
        var i = node('i', 'fas ' + iconName);
        i.setAttribute('aria-hidden', 'true');
        btn.appendChild(i);
        return btn;
    }

    // One slide per block; tables are report-only.
    function buildSlides(blocks, options) {
        var titles = {};
        blocks.forEach(function (block) {
            if (block.type === 'section') titles[block.id] = block.title;
        });
        var slides = [];
        blocks.forEach(function (block) {
            if (block.type === 'table') return;
            var made = root.dom.renderBlock(block, { ui: options.ui, logoUrl: options.logoUrl, size: CHART_SIZE, maxNames: 18 });
            var slide = node('section', 'upri-slide upri-slide--' + block.type);
            slide.setAttribute('aria-roledescription', 'slide');
            if (block.type !== 'cover' && block.type !== 'section' && titles[block.section]) {
                slide.appendChild(node('p', 'upri-slide__tag', titles[block.section]));
            }
            slide.appendChild(made.element);
            slides.push({ element: slide, plots: made.plots });
        });
        return slides;
    }

    function close() {
        if (current) current.close();
    }

    /**
     * Open the deck. ``options``: ``{ui, logoUrl, title}``. Returns
     * ``{close}``; only one deck exists at a time.
     */
    function open(blocks, options) {
        options = options || {};
        var ui = options.ui || {};
        close();

        var slides = buildSlides(blocks, options);
        if (!slides.length) return null;

        var overlay = node('div', 'upri-overlay upri-deck');
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');
        overlay.setAttribute('aria-label', options.title || '');
        overlay.tabIndex = -1;

        var viewport = node('div', 'upri-deck__viewport');
        var stage = node('div', 'upri-deck__stage');
        stage.style.width = STAGE.width + 'px';
        stage.style.height = STAGE.height + 'px';
        slides.forEach(function (slide) { stage.appendChild(slide.element); });
        viewport.appendChild(stage);
        overlay.appendChild(viewport);

        var bar = node('div', 'upri-deck__bar');
        var prev = iconButton('upri-deck__prev', 'fa-chevron-left', ui.export_prev || 'Previous slide');
        var next = iconButton('upri-deck__next', 'fa-chevron-right', ui.export_next || 'Next slide');
        var counter = node('span', 'upri-deck__counter');
        counter.setAttribute('aria-live', 'polite');
        var full = iconButton('upri-deck__full', 'fa-expand', ui.export_fullscreen || 'Full screen');
        var closeBtn = iconButton('upri-deck__close', 'fa-times', ui.close || 'Close');
        var nav = node('div', 'upri-deck__nav');
        nav.appendChild(prev);
        nav.appendChild(counter);
        nav.appendChild(next);
        bar.appendChild(nav);
        var tools = node('div', 'upri-deck__tools');
        if (typeof overlay.requestFullscreen === 'function') tools.appendChild(full);
        tools.appendChild(closeBtn);
        bar.appendChild(tools);
        overlay.appendChild(bar);

        var progress = node('div', 'upri-deck__progress');
        var progressFill = node('span');
        progress.appendChild(progressFill);
        overlay.appendChild(progress);

        var opener = document.activeElement;
        document.body.appendChild(overlay);
        document.body.classList.add('upri-locked');

        var index = 0;
        function go(to) {
            index = Math.max(0, Math.min(slides.length - 1, to));
            slides.forEach(function (slide, i) {
                var active = i === index;
                slide.element.classList.toggle('is-active', active);
                slide.element.setAttribute('aria-hidden', active ? 'false' : 'true');
            });
            counter.textContent = (index + 1) + ' / ' + slides.length;
            prev.disabled = index === 0;
            next.disabled = index === slides.length - 1;
            progressFill.style.width = ((index + 1) / slides.length * 100) + '%';
        }

        function fit() {
            var scale = Math.min(viewport.clientWidth / STAGE.width, viewport.clientHeight / STAGE.height);
            stage.style.transform = 'translate(-50%, -50%) scale(' + scale + ')';
        }

        function onKey(event) {
            var onButton = event.target && event.target.tagName === 'BUTTON';
            switch (event.key) {
                case 'ArrowRight':
                case 'PageDown':
                    go(index + 1);
                    break;
                case 'ArrowLeft':
                case 'PageUp':
                    go(index - 1);
                    break;
                case ' ':
                case 'Enter':
                    if (onButton) return;
                    go(index + 1);
                    break;
                case 'Home':
                    go(0);
                    break;
                case 'End':
                    go(slides.length - 1);
                    break;
                case 'f':
                case 'F':
                    toggleFullscreen();
                    break;
                case 'Escape':
                    api.close();
                    break;
                default:
                    return;
            }
            event.preventDefault();
            event.stopPropagation();
        }

        function toggleFullscreen() {
            if (document.fullscreenElement) {
                document.exitFullscreen();
            } else if (typeof overlay.requestFullscreen === 'function') {
                overlay.requestFullscreen().catch(function () { /* the browser refused; stay windowed */ });
            }
        }

        prev.addEventListener('click', function () { go(index - 1); });
        next.addEventListener('click', function () { go(index + 1); });
        full.addEventListener('click', toggleFullscreen);
        closeBtn.addEventListener('click', function () { api.close(); });
        document.addEventListener('keydown', onKey, true);
        global.addEventListener('resize', fit);
        document.addEventListener('fullscreenchange', fit);

        fit();
        go(0);

        var charts = [];
        slides.forEach(function (slide) {
            charts = charts.concat(root.charts.mountAll(slide.plots, { animate: false }));
        });
        overlay.focus();

        var api = {
            close: function () {
                document.removeEventListener('keydown', onKey, true);
                global.removeEventListener('resize', fit);
                document.removeEventListener('fullscreenchange', fit);
                charts.forEach(function (chart) {
                    try { chart.destroy(); } catch (e) { /* noop */ }
                });
                if (document.fullscreenElement) document.exitFullscreen();
                overlay.remove();
                document.body.classList.remove('upri-locked');
                if (opener && typeof opener.focus === 'function') opener.focus();
                if (current === api) current = null;
            },
            go: go,
            count: slides.length
        };
        current = api;
        return api;
    }

    root.slides = { open: open, close: close, STAGE: STAGE, CHART_SIZE: CHART_SIZE };
})(typeof window !== 'undefined' ? window : globalThis);
