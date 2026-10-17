/* Bilateral funding rankings: societies that sent funding, and countries that received it.
 * Separate from the support map. Used by the Analysis sub-tab and the public embed. */
(function () {
    'use strict';

    var root = document.getElementById('upri-funding');
    if (!root) return;

    var UI = (window.UprImpactConfig && window.UprImpactConfig.ui) || {};
    if (root.getAttribute('data-ui')) {
        try {
            var parsed = JSON.parse(root.getAttribute('data-ui'));
            if (parsed && parsed.flow_sent) UI = parsed;
        } catch (e) { /* keep the page catalogue */ }
    }
    var BAR_LIMIT = 15;
    var funding = [];
    var loaded = false;
    var ready = false;

    function byId(id) { return document.getElementById(id); }

    function fill(text, values) {
        text = text || '';
        Object.keys(values || {}).forEach(function (key) {
            text = text.split('{' + key + '}').join(String(values[key]));
        });
        return text;
    }

    function compactMoney(value) {
        var amount = Math.abs(Number(value) || 0);
        var sign = Number(value) < 0 ? '-' : '';
        if (amount >= 1e9) return sign + Math.round(amount / 1e8) / 10 + 'B';
        if (amount >= 1e6) return sign + Math.round(amount / 1e6) + 'M';
        if (amount >= 1e3) return sign + Math.round(amount / 1e3) + 'K';
        return sign + String(Math.round(amount));
    }

    function show(el, visible) { if (el) el.hidden = !visible; }

    function rank(links, nameKey) {
        var grouped = {};
        links.forEach(function (link) {
            var name = link[nameKey] || '';
            if (!name) return;
            grouped[name] = (grouped[name] || 0) + (Number(link.value) || 0);
        });
        return Object.keys(grouped).map(function (name) {
            return { name: name, value: grouped[name] };
        }).sort(function (a, b) { return b.value - a.value; }).slice(0, BAR_LIMIT);
    }

    function renderColumn(host, title, rows, tone) {
        host.replaceChildren();
        var heading = document.createElement('h4');
        heading.className = 'upri-flow-bars__title';
        heading.textContent = title;
        host.appendChild(heading);
        if (!rows.length) return;
        var max = rows[0].value || 1;
        rows.forEach(function (row) {
            var line = document.createElement('div');
            line.className = 'upri-flow-bars__row';
            var label = document.createElement('span');
            label.className = 'upri-flow-bars__label';
            label.textContent = row.name;
            label.title = row.name;
            var track = document.createElement('span');
            track.className = 'upri-flow-bars__track';
            var bar = document.createElement('span');
            bar.className = 'upri-flow-bars__fill upri-flow-bars__fill--' + tone;
            bar.style.width = Math.max(0, Math.min(100, (row.value / max) * 100)) + '%';
            var value = document.createElement('span');
            value.className = 'upri-flow-bars__value';
            value.textContent = compactMoney(row.value);
            track.appendChild(bar);
            bar.appendChild(value);
            line.appendChild(label);
            line.appendChild(track);
            host.appendChild(line);
        });
        var axis = document.createElement('div');
        axis.className = 'upri-flow-bars__axis';
        ['0', compactMoney(max / 2), compactMoney(max)].forEach(function (tick) {
            var span = document.createElement('span');
            span.textContent = tick;
            axis.appendChild(span);
        });
        host.appendChild(axis);
    }

    function followedSelect() {
        var id = root.getAttribute('data-follow-year');
        return id ? document.getElementById(id) : null;
    }

    function selectedYear() {
        var select = byId('upri-funding-year');
        var year = parseInt(select && select.value, 10);
        if (!year) year = parseInt(root.getAttribute('data-year') || '', 10);
        return year || null;
    }

    function ensureYearOption(select, year) {
        var value = String(year);
        var exists = Array.prototype.some.call(select.options, function (option) {
            return option.value === value;
        });
        if (exists) return;
        var option = document.createElement('option');
        option.value = value;
        option.textContent = value;
        select.appendChild(option);
    }

    function draw() {
        var year = selectedYear();
        var links = funding.filter(function (link) {
            return Number(link.year) === Number(year) && link.value;
        });
        var board = byId('upri-funding-bars');
        var empty = byId('upri-funding-empty');
        show(board, !!links.length);
        show(empty, !links.length);
        if (!links.length) {
            if (empty) empty.textContent = fill(UI.flow_funding_empty || '', { year: year || '' });
            return;
        }
        renderColumn(byId('upri-funding-sent'), UI.flow_sent || '', rank(links, 'from_name'), 'sent');
        renderColumn(byId('upri-funding-received'), UI.flow_received || '', rank(links, 'to_name'), 'received');
    }

    function fillYears(links) {
        var select = byId('upri-funding-year');
        if (!select) return;
        var seen = {};
        links.forEach(function (link) { if (link.year) seen[link.year] = true; });
        var years = Object.keys(seen).map(Number).sort(function (a, b) { return b - a; });
        var preset = parseInt(root.getAttribute('data-year') || '', 10);
        var previous = parseInt(select.value, 10);
        select.replaceChildren();
        years.forEach(function (year) {
            var option = document.createElement('option');
            option.value = String(year);
            option.textContent = String(year);
            select.appendChild(option);
        });
        var pick = years.indexOf(previous) !== -1 ? previous : (years.indexOf(preset) !== -1 ? preset : years[0]);
        if (pick) select.value = String(pick);
    }

    function readFlowCache(url) {
        try {
            var raw = window.sessionStorage && sessionStorage.getItem('upr-flow-cache:' + url);
            return raw ? JSON.parse(raw) : null;
        } catch (e) {
            return null;
        }
    }

    function writeFlowCache(url, payload) {
        try {
            if (window.sessionStorage) sessionStorage.setItem('upr-flow-cache:' + url, JSON.stringify(payload));
        } catch (e) { /* quota or private mode */ }
    }

    function applyFundingPayload(payload) {
        funding = (payload && payload.flows && payload.flows.funding) || [];
        show(byId('upri-funding-loading'), false);
        show(byId('upri-funding-error'), false);
        fillYears(funding);
        ready = true;
        applyFollowedYear();
        draw();
    }

    function load() {
        var url = root.getAttribute('data-flow-url');
        if (!url) return;
        var regionSelect = byId('upri-region');
        var region = regionSelect ? regionSelect.value : '';
        if (region) url += (url.indexOf('?') === -1 ? '?' : '&') + 'region=' + encodeURIComponent(region);
        var cached = readFlowCache(url);
        if (cached && cached.flows) applyFundingPayload(cached);
        else show(byId('upri-funding-loading'), true);
        show(byId('upri-funding-error'), false);
        fetch(url, { headers: { Accept: 'application/json' }, credentials: 'same-origin' })
            .then(function (resp) {
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                return resp.json();
            })
            .then(function (payload) {
                writeFlowCache(url, payload);
                applyFundingPayload(payload);
            })
            .catch(function (err) {
                show(byId('upri-funding-loading'), false);
                if (!funding.length) show(byId('upri-funding-error'), true);
                if (window.console) console.error('UPR funding rankings failed', err);
            });
    }

    function hostingPane() {
        var pane = byId('upri-pane-funding') || byId('upri-pane-flow');
        var rootPane = root && root.closest ? root.closest('.upri-pane') : null;
        return rootPane || pane;
    }

    function paneOpen() {
        var pane = hostingPane();
        if (!pane) return true;
        var panel = byId('panel-upr-impact');
        return pane && !pane.hidden && panel && !panel.classList.contains('hidden') && panel.offsetParent !== null;
    }

    function ensureLoaded() {
        if (!paneOpen()) return;
        if (!loaded) {
            loaded = true;
            load();
            return;
        }
    }

    function applyFollowedYear() {
        var source = followedSelect();
        var select = byId('upri-funding-year');
        if (!source || !select || !source.value) return;
        ensureYearOption(select, source.value);
        if (select.value !== source.value) select.value = source.value;
    }

    function syncFollowedYear(year) {
        var source = followedSelect();
        if (!source || !year) return;
        var value = String(year);
        var exists = Array.prototype.some.call(source.options, function (option) {
            return option.value === value;
        });
        if (!exists || source.value === value) return;
        source.value = value;
        source.dispatchEvent(new Event('change', { bubbles: true }));
    }

    var yearSelect = byId('upri-funding-year');
    if (yearSelect) {
        yearSelect.addEventListener('change', function () {
            syncFollowedYear(yearSelect.value);
            draw();
        });
    }
    var followed = followedSelect();
    if (followed) {
        followed.addEventListener('change', function () {
            if (!ready) return;
            applyFollowedYear();
            draw();
        });
    }
    var regionSelect = byId('upri-region');
    if (regionSelect) regionSelect.addEventListener('change', function () { if (loaded) load(); });
    var refresh = byId('upri-refresh');
    if (refresh) refresh.addEventListener('click', function () { if (loaded) load(); });

    if (paneOpen()) {
        ensureLoaded();
    } else {
        var pane = hostingPane();
        var panel = byId('panel-upr-impact');
        if (pane && panel && window.MutationObserver) {
            var observer = new MutationObserver(function () { ensureLoaded(); });
            observer.observe(pane, { attributes: true, attributeFilter: ['hidden'] });
            observer.observe(panel, { attributes: true, attributeFilter: ['class'] });
        }
    }
})();
