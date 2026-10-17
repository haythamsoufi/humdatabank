/* Bilateral funding-requirement coverage by INFORM risk class.
 * X is the requirement on a log scale, Y is reported funding as a percent of
 * that requirement, and colour is the INFORM risk class. */
(function () {
    'use strict';

    var root = document.getElementById('upri-coverage');
    if (!root) return;

    var UI = (window.UprImpactConfig && window.UprImpactConfig.ui) || {};
    if (root.getAttribute('data-ui')) {
        try {
            var parsed = JSON.parse(root.getAttribute('data-ui'));
            if (parsed && parsed.flow_coverage_x) UI = parsed;
        } catch (e) { /* keep the page catalogue */ }
    }

    var CLASSES = [
        { id: 'low', label: 'flow_coverage_low', color: '#e7a0a6' },
        { id: 'medium', label: 'flow_coverage_medium', color: '#c44955' },
        { id: 'high', label: 'flow_coverage_high', color: '#8d2a36' },
        { id: 'very_high', label: 'flow_coverage_very_high', color: '#5c1c24' }
    ];
    var DOMAIN_MIN = 1e4;
    var DOMAIN_MAX = 1e8;
    var X_TICKS = [1e4, 1e5, 1e6, 1e7, 1e8];
    var points = [];
    var edition = '';
    var activeUrl = '';
    var xLo = DOMAIN_MIN;
    var xHi = DOMAIN_MAX;
    var drag = null;
    var layout = { left: 64, plotW: 800, width: 920 };

    function byId(id) { return document.getElementById(id); }
    function show(el, visible) { if (el) el.hidden = !visible; }
    function text(key, fallback) { return UI[key] || fallback || ''; }

    function fill(template, values) {
        template = template || '';
        Object.keys(values || {}).forEach(function (key) {
            template = template.split('{' + key + '}').join(String(values[key]));
        });
        return template;
    }

    function money(value) {
        var millions = Number(value) / 1e6;
        return millions.toFixed(2) + 'M';
    }

    function readCache(url) {
        try {
            var raw = window.sessionStorage && sessionStorage.getItem('upr-flow-cache:' + url);
            return raw ? JSON.parse(raw) : null;
        } catch (e) {
            return null;
        }
    }

    function followedSelect() {
        var id = root.getAttribute('data-follow-year');
        return id ? document.getElementById(id) : null;
    }

    function selectedYear() {
        var source = followedSelect();
        if (source && source.value) return parseInt(source.value, 10) || null;
        var pressed = root.querySelector('.upri-coverage__year.is-active');
        var year = parseInt(pressed && pressed.getAttribute('data-year'), 10);
        if (!year) year = parseInt(root.getAttribute('data-year') || '', 10);
        return year || null;
    }

    function yearHasFunding(year) {
        return points.some(function (row) {
            return Number(row.year) === Number(year) && Number(row.funding) > 0;
        });
    }

    function renderYears(rows) {
        var host = byId('upri-coverage-years');
        if (!host) return;
        var seen = {};
        rows.forEach(function (row) { if (row.year) seen[row.year] = true; });
        var years = Object.keys(seen).map(Number).sort(function (a, b) { return a - b; });
        var preset = parseInt(root.getAttribute('data-year') || '', 10);
        var current = selectedYear();
        host.replaceChildren();
        years.forEach(function (year) {
            var button = document.createElement('button');
            button.type = 'button';
            button.className = 'upri-coverage__year';
            button.setAttribute('data-year', String(year));
            button.textContent = String(year);
            button.addEventListener('click', function () {
                host.querySelectorAll('.upri-coverage__year').forEach(function (item) {
                    item.classList.toggle('is-active', item === button);
                });
                draw();
            });
            host.appendChild(button);
        });
        var funded = years.filter(yearHasFunding);
        var fallback = funded.length ? funded[funded.length - 1] : years[years.length - 1];
        var pick = years.indexOf(current) !== -1 ? current : (years.indexOf(preset) !== -1 ? preset : fallback);
        host.querySelectorAll('.upri-coverage__year').forEach(function (button) {
            button.classList.toggle('is-active', Number(button.getAttribute('data-year')) === pick);
        });
    }

    function draw() {
        var year = selectedYear();
        var rows = points.filter(function (row) { return Number(row.year) === Number(year) && row.requirement > 0; });
        var plot = byId('upri-coverage-plot');
        var empty = byId('upri-coverage-empty');
        var note = byId('upri-coverage-note');
        show(plot, !!rows.length);
        show(empty, !rows.length);
        show(note, !!rows.length);
        if (!rows.length) {
            show(byId('upri-coverage-legend'), false);
            if (empty) empty.textContent = fill(text('flow_coverage_empty'), { year: year || '' });
            return;
        }
        if (note) {
            var noteText = text('flow_coverage_note');
            if (edition) noteText = noteText.replace('INFORM Risk 2026', edition);
            note.textContent = noteText;
        }
        renderLegend();
        plot.replaceChildren();
        plot.appendChild(chart(rows));
    }

    function renderLegend() {
        var host = byId('upri-coverage-legend');
        if (!host || host.childElementCount) {
            show(host, true);
            return;
        }
        var title = document.createElement('span');
        title.className = 'upri-coverage__key-title';
        title.textContent = text('flow_coverage_risk', 'Risk class');
        host.appendChild(title);
        CLASSES.forEach(function (item) {
            var entry = document.createElement('span');
            entry.className = 'upri-coverage__key-item';
            var mark = document.createElement('span');
            mark.className = 'upri-coverage__diamond';
            mark.style.background = item.color;
            var caption = document.createElement('span');
            caption.textContent = text(item.label, item.id);
            entry.appendChild(mark);
            entry.appendChild(caption);
            host.appendChild(entry);
        });
        show(host, true);
    }

    function chart(rows) {
        var width = 920;
        var height = 560;
        var left = 64;
        var right = 56;
        var top = 18;
        var bottom = 96;
        var plotW = width - left - right;
        var plotH = height - top - bottom;
        var xMin = xLo;
        var xMax = xHi;
        layout = { left: left, plotW: plotW, width: width };
        var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('viewBox', '0 0 ' + width + ' ' + height);
        svg.setAttribute('class', 'upri-coverage__svg');
        svg.setAttribute('role', 'group');
        svg.setAttribute('aria-label', text('flow_coverage_x', 'Funding Requirement (CHF)'));

        function xOf(value) {
            var amount = Math.min(xMax, Math.max(xMin, Number(value) || xMin));
            return left + (Math.log10(amount) - Math.log10(xMin)) / (Math.log10(xMax) - Math.log10(xMin)) * plotW;
        }
        function yOf(met) {
            var value = Math.min(100, Math.max(0, Number(met) || 0));
            return top + (1 - value / 100) * plotH;
        }
        function xOfDomain(value) {
            var amount = Math.min(DOMAIN_MAX, Math.max(DOMAIN_MIN, Number(value) || DOMAIN_MIN));
            return left + (Math.log10(amount) - Math.log10(DOMAIN_MIN)) / (Math.log10(DOMAIN_MAX) - Math.log10(DOMAIN_MIN)) * plotW;
        }

        [0, 20, 40, 60, 80, 100].forEach(function (tick) {
            var y = yOf(tick);
            svg.appendChild(line(left, y, left + plotW, y, 'upri-coverage__grid'));
            svg.appendChild(label(left - 10, y + 4, String(tick), 'upri-coverage__tick upri-coverage__tick--y'));
        });
        svg.appendChild(line(left, yOf(0), left + plotW, yOf(0), 'upri-coverage__baseline'));
        var handleMinX = xOfDomain(xLo);
        var handleMaxX = xOfDomain(xHi);
        windowTicks(xMin, xMax).forEach(function (tick) {
            var x = xOf(tick);
            if (Math.abs(x - left) < 22 || Math.abs(x - (left + plotW)) < 22) return;
            svg.appendChild(line(x, top, x, top + plotH, 'upri-coverage__grid'));
            svg.appendChild(label(x, top + plotH + 16, money(tick), 'upri-coverage__tick'));
        });
        svg.appendChild(label(xOf(xMin), top + plotH + 16, money(xMin), 'upri-coverage__tick'));
        svg.appendChild(label(xOf(xMax), top + plotH + 16, money(xMax), 'upri-coverage__tick'));
        svg.appendChild(label(left + plotW / 2, height - 10, text('flow_coverage_x', 'Funding Requirement (CHF)'), 'upri-coverage__axis'));
        if (drag) svg.classList.add('is-grabbing');
        var yTitle = label(16, top + plotH / 2, text('flow_coverage_y', 'Funding Met (%)'), 'upri-coverage__axis');
        yTitle.setAttribute('transform', 'rotate(-90 16 ' + (top + plotH / 2) + ')');
        svg.appendChild(yTitle);

        var placed = [];
        rows.slice().sort(function (a, b) { return b.requirement - a.requirement; }).forEach(function (row) {
            if (row.requirement < xMin || row.requirement > xMax) return;
            var x = xOf(row.requirement);
            var y = yOf(row.met);
            var color = (CLASSES.filter(function (item) { return item.id === row.inform_class; })[0] || {}).color || '#9ca3af';
            var point = document.createElementNS('http://www.w3.org/2000/svg', 'g');
            point.setAttribute('class', 'upri-coverage__point');
            var tip = fill(text('flow_coverage_tooltip'), {
                name: row.name,
                requirement: money(row.requirement),
                met: row.met
            });
            point.appendChild(diamond(x, y, color));
            placeName(point, row.name, x, y, left, top, plotW, plotH, placed);
            var title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
            title.textContent = tip;
            point.appendChild(title);
            svg.appendChild(point);
        });
        svg.appendChild(scale(left, top + plotH + 40, handleMinX, handleMaxX));
        return svg;
    }

    function windowTicks(min, max) {
        var span = Math.log10(max) - Math.log10(min);
        var steps = span < 1.4 ? [1, 2, 5] : [1];
        var start = Math.floor(Math.log10(min));
        var end = Math.ceil(Math.log10(max));
        var ticks = [];
        for (var exp = start; exp <= end; exp += 1) {
            steps.forEach(function (step) {
                var value = step * Math.pow(10, exp);
                if (value > min * 1.05 && value < max / 1.05) ticks.push(value);
            });
        }
        return ticks;
    }

    function scale(left, y, handleMinX, handleMaxX) {
        var group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        group.setAttribute('class', 'upri-coverage__scale');
        group.appendChild(line(left, y, left + layout.plotW, y, 'upri-coverage__scale-track'));
        var range = line(handleMinX, y, handleMaxX, y, 'upri-coverage__scale-range');
        var grab = line(handleMinX, y, handleMaxX, y, 'upri-coverage__scale-pan');
        grab.setAttribute('stroke', '#000');
        grab.setAttribute('stroke-opacity', '0');
        grab.setAttribute('stroke-width', '18');
        grab.setAttribute('pointer-events', 'stroke');
        grab.setAttribute('role', 'slider');
        grab.setAttribute('tabindex', '0');
        grab.setAttribute('aria-label', text('flow_coverage_scale_pan', 'Drag to move the range. Double-click to reset.'));
        grab.setAttribute('aria-orientation', 'horizontal');
        bindDrag(grab, 'pan');
        grab.addEventListener('dblclick', resetScale);
        group.appendChild(range);
        group.appendChild(grab);
        group.appendChild(knob(handleMinX, y, 'min'));
        group.appendChild(knob(handleMaxX, y, 'max'));
        return group;
    }

    function knob(x, y, kind) {
        var group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        group.setAttribute('class', 'upri-coverage__scale-knob');
        group.setAttribute('data-scale', kind);
        group.setAttribute('role', 'slider');
        group.setAttribute('tabindex', '0');
        group.setAttribute('aria-orientation', 'horizontal');
        group.setAttribute('aria-valuemin', String(DOMAIN_MIN));
        group.setAttribute('aria-valuemax', String(DOMAIN_MAX));
        group.setAttribute('aria-valuenow', String(Math.round(kind === 'min' ? xLo : xHi)));
        group.setAttribute('aria-valuetext', money(kind === 'min' ? xLo : xHi));
        group.setAttribute('aria-label', text(
            kind === 'min' ? 'flow_coverage_scale_min' : 'flow_coverage_scale_max',
            kind === 'min' ? 'Smallest funding requirement shown' : 'Largest funding requirement shown'
        ));
        var hit = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        hit.setAttribute('cx', String(x));
        hit.setAttribute('cy', String(y));
        hit.setAttribute('r', '14');
        hit.setAttribute('class', 'upri-coverage__scale-hit');
        var dot = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        dot.setAttribute('cx', String(x));
        dot.setAttribute('cy', String(y));
        dot.setAttribute('r', '7');
        dot.setAttribute('class', 'upri-coverage__scale-handle');
        group.appendChild(hit);
        group.appendChild(dot);
        bindDrag(group, kind);
        group.addEventListener('dblclick', resetScale);
        group.addEventListener('keydown', function (event) { nudge(event, kind); });
        return group;
    }

    function bindDrag(node, kind) {
        node.addEventListener('pointerdown', function (event) {
            if (event.button !== 0) return;
            event.preventDefault();
            event.stopPropagation();
            drag = { kind: kind, startX: pointerX(event), startLo: xLo, startHi: xHi };
            var svg = root.querySelector('.upri-coverage__svg');
            if (svg) svg.classList.add('is-grabbing');
            window.addEventListener('pointermove', onDragMove);
            window.addEventListener('pointerup', endDrag);
            window.addEventListener('pointercancel', endDrag);
        });
    }

    function pointerX(event) {
        var svg = root.querySelector('.upri-coverage__svg');
        if (!svg) return 0;
        var rect = svg.getBoundingClientRect();
        if (!rect.width) return 0;
        return (event.clientX - rect.left) / rect.width * layout.width;
    }

    function valueFromX(x) {
        var t = (x - layout.left) / layout.plotW;
        t = Math.min(1, Math.max(0, t));
        var span = Math.log10(DOMAIN_MAX) - Math.log10(DOMAIN_MIN);
        return Math.pow(10, Math.log10(DOMAIN_MIN) + t * span);
    }

    function applyWindow(lo, hi, edge) {
        var minRatio = Math.pow(10, 0.25);
        lo = Math.max(DOMAIN_MIN, Math.min(DOMAIN_MAX, lo));
        hi = Math.max(DOMAIN_MIN, Math.min(DOMAIN_MAX, hi));
        if (hi / lo < minRatio) {
            if (edge === 'min') lo = Math.max(DOMAIN_MIN, hi / minRatio);
            else hi = Math.min(DOMAIN_MAX, lo * minRatio);
        }
        if (hi / lo < minRatio) {
            if (edge === 'min') hi = Math.min(DOMAIN_MAX, lo * minRatio);
            else lo = Math.max(DOMAIN_MIN, hi / minRatio);
        }
        xLo = lo;
        xHi = hi;
    }

    function onDragMove(event) {
        if (!drag) return;
        event.preventDefault();
        var x = pointerX(event);
        if (drag.kind === 'pan') {
            var span = Math.log10(drag.startHi) - Math.log10(drag.startLo);
            var domain = Math.log10(DOMAIN_MAX) - Math.log10(DOMAIN_MIN);
            var shift = (x - drag.startX) / layout.plotW * domain;
            var nextLo = Math.log10(drag.startLo) + shift;
            var nextHi = nextLo + span;
            if (nextLo < Math.log10(DOMAIN_MIN)) {
                nextHi += Math.log10(DOMAIN_MIN) - nextLo;
                nextLo = Math.log10(DOMAIN_MIN);
            }
            if (nextHi > Math.log10(DOMAIN_MAX)) {
                nextLo -= nextHi - Math.log10(DOMAIN_MAX);
                nextHi = Math.log10(DOMAIN_MAX);
            }
            xLo = Math.pow(10, nextLo);
            xHi = Math.pow(10, nextHi);
        } else if (drag.kind === 'min') {
            applyWindow(valueFromX(x), drag.startHi, 'min');
        } else {
            applyWindow(drag.startLo, valueFromX(x), 'max');
        }
        draw();
    }

    function endDrag() {
        drag = null;
        window.removeEventListener('pointermove', onDragMove);
        window.removeEventListener('pointerup', endDrag);
        window.removeEventListener('pointercancel', endDrag);
        var svg = root.querySelector('.upri-coverage__svg');
        if (svg) svg.classList.remove('is-grabbing');
    }

    function resetScale(event) {
        event.preventDefault();
        event.stopPropagation();
        xLo = DOMAIN_MIN;
        xHi = DOMAIN_MAX;
        draw();
    }

    function nudge(event, kind) {
        var dir = event.key === 'ArrowRight' || event.key === 'ArrowUp' ? 1
            : (event.key === 'ArrowLeft' || event.key === 'ArrowDown' ? -1 : 0);
        if (event.key === 'Home' || event.key === 'End') {
            event.preventDefault();
            if (kind === 'min') xLo = event.key === 'Home' ? DOMAIN_MIN : xHi / Math.pow(10, 0.25);
            else xHi = event.key === 'End' ? DOMAIN_MAX : xLo * Math.pow(10, 0.25);
            draw();
            focusHandle(kind);
            return;
        }
        if (!dir) return;
        event.preventDefault();
        var factor = Math.pow(10, 0.08 * dir);
        if (kind === 'min') applyWindow(xLo * factor, xHi, 'min');
        else applyWindow(xLo, xHi * factor, 'max');
        draw();
        focusHandle(kind);
    }

    function focusHandle(kind) {
        var next = root.querySelector('[data-scale="' + kind + '"]');
        if (next) next.focus();
    }

    function placeName(point, name, x, y, left, top, plotW, plotH, placed) {
        var caption = String(name || '');
        if (caption.length > 26) caption = caption.slice(0, 24) + '…';
        var width = Math.min(168, caption.length * 5.7 + 14);
        var height = 16;
        var candidates = [
            { x: x + 10, y: y - 18 },
            { x: x + 10, y: y + 6 },
            { x: x - width - 10, y: y - 18 },
            { x: x - width - 10, y: y + 6 }
        ];
        var spot = null;
        candidates.some(function (candidate) {
            if (candidate.x < left + 4 || candidate.x + width > left + plotW - 2) return false;
            if (candidate.y < top || candidate.y + height > top + plotH - 2) return false;
            var hit = placed.some(function (other) {
                return candidate.x < other.x + other.w && candidate.x + width > other.x
                    && candidate.y < other.y + other.h && candidate.y + height > other.y;
            });
            if (hit) return false;
            spot = candidate;
            return true;
        });
        if (!spot) return;
        var pill = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        pill.setAttribute('x', String(spot.x));
        pill.setAttribute('y', String(spot.y));
        pill.setAttribute('width', String(width));
        pill.setAttribute('height', String(height));
        pill.setAttribute('rx', '8');
        pill.setAttribute('class', 'upri-coverage__pill');
        var textNode = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        textNode.setAttribute('x', String(spot.x + 7));
        textNode.setAttribute('y', String(spot.y + 11.5));
        textNode.setAttribute('class', 'upri-coverage__name');
        textNode.textContent = caption;
        point.appendChild(pill);
        point.appendChild(textNode);
        placed.push({ x: spot.x, y: spot.y, w: width, h: height });
    }

    function diamond(x, y, color) {
        var shape = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
        shape.setAttribute('points', [
            [x, y - 6], [x + 6, y], [x, y + 6], [x - 6, y]
        ].map(function (pair) { return pair.join(','); }).join(' '));
        shape.setAttribute('fill', color);
        return shape;
    }

    function line(x1, y1, x2, y2, className) {
        var node = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        node.setAttribute('x1', String(x1));
        node.setAttribute('y1', String(y1));
        node.setAttribute('x2', String(x2));
        node.setAttribute('y2', String(y2));
        node.setAttribute('class', className);
        return node;
    }

    function label(x, y, value, className) {
        var node = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        node.setAttribute('x', String(x));
        node.setAttribute('y', String(y));
        node.setAttribute('class', className);
        node.textContent = value;
        return node;
    }

    function applyPayload(payload) {
        var flows = (payload && payload.flows) || payload || {};
        points = flows.coverage || [];
        edition = (flows.inform && flows.inform.edition) || '';
        show(byId('upri-coverage-loading'), false);
        show(byId('upri-coverage-error'), false);
        renderYears(points);
        draw();
        try {
            if (activeUrl && window.sessionStorage && payload) {
                sessionStorage.setItem('upr-flow-cache:' + activeUrl, JSON.stringify(payload));
            }
        } catch (e) { /* a full cache must not block the chart */ }
    }

    function load() {
        var url = root.getAttribute('data-flow-url');
        if (!url) return;
        var regionSelect = byId('upri-region');
        var region = regionSelect ? regionSelect.value : '';
        if (region) url += (url.indexOf('?') === -1 ? '?' : '&') + 'region=' + encodeURIComponent(region);
        activeUrl = url;
        var cached = readCache(url);
        if (!(cached && ((cached.flows && cached.flows.coverage) || cached.coverage))) {
            show(byId('upri-coverage-loading'), true);
        } else {
            applyPayload(cached);
        }
        show(byId('upri-coverage-error'), false);
        fetch(url, { headers: { Accept: 'application/json' }, credentials: 'same-origin' })
            .then(function (resp) {
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                return resp.json();
            })
            .then(applyPayload)
            .catch(function (err) {
                show(byId('upri-coverage-loading'), false);
                if (!points.length) show(byId('upri-coverage-error'), true);
                if (window.console) console.error('UPR coverage chart failed', err);
            });
    }

    var followed = followedSelect();
    if (followed) {
        followed.addEventListener('change', function () {
            if (points.length) draw();
        });
    }
    var regionSelect = byId('upri-region');
    if (regionSelect) regionSelect.addEventListener('change', load);
    var refresh = byId('upri-refresh');
    if (refresh) refresh.addEventListener('click', load);
    load();
})();
