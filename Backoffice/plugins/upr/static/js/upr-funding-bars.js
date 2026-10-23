/* Bilateral funding rankings: societies that sent funding, and countries that received it.
 * Separate from the support map. Used by the Analysis sub-tab and the public embed.
 *
 * Click a sent bar to filter the received ranking to that PNS's partners, and the
 * other way around. The selection is shared with the map and coverage iframes. */
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
    var DEFAULT_YEAR = 2026;
    var funding = [];
    var loaded = false;
    var ready = false;
    var applyingSync = false;
    var selection = { from: '', to: '', fromName: '', toName: '' };

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

    function yearLinks() {
        var year = selectedYear();
        return funding.filter(function (link) {
            return Number(link.year) === Number(year) && link.value;
        });
    }

    function matchesFrom(link) {
        if (selection.from) return String(link.from || '').toUpperCase() === selection.from;
        if (selection.fromName) return String(link.from_name || '') === selection.fromName;
        return true;
    }

    function matchesTo(link) {
        if (selection.to) return String(link.to || '').toUpperCase() === selection.to;
        if (selection.toName) return String(link.to_name || '') === selection.toName;
        return true;
    }

    function rank(links, nameKey, codeKey) {
        var grouped = {};
        links.forEach(function (link) {
            var name = link[nameKey] || '';
            var code = String(link[codeKey] || '').toUpperCase();
            if (!name && !code) return;
            var key = code || name;
            if (!grouped[key]) grouped[key] = { name: name || code, code: code, value: 0 };
            grouped[key].value += Number(link.value) || 0;
            if (name) grouped[key].name = name;
            if (code) grouped[key].code = code;
        });
        return Object.keys(grouped).map(function (key) {
            return grouped[key];
        }).sort(function (a, b) { return b.value - a.value; }).slice(0, BAR_LIMIT);
    }

    function snapshotWidths(host) {
        var widths = {};
        if (!host) return widths;
        host.querySelectorAll('.upri-flow-bars__row[data-key]').forEach(function (row) {
            var fillEl = row.querySelector('.upri-flow-bars__fill');
            widths[row.getAttribute('data-key')] = fillEl ? fillEl.style.width : '';
        });
        return widths;
    }

    function ensureFilterBar() {
        var bar = byId('upri-funding-filter');
        if (!bar) return null;
        var clear = bar.querySelector('.upri-flow-bars__filter-clear');
        if (clear && !clear.getAttribute('data-wired')) {
            clear.setAttribute('data-wired', '1');
            clear.textContent = UI.flow_filters_clear || clear.textContent || 'Clear filters';
            clear.addEventListener('click', function () {
                setSelection({ from: '', to: '', fromName: '', toName: '' }, true);
            });
        }
        return bar;
    }

    function updateFilterBar() {
        var bar = ensureFilterBar();
        var toolbar = byId('upri-funding-toolbar');
        if (!bar) return;
        var label = bar.querySelector('.upri-flow-bars__filter-label');
        var active = !!(selection.from || selection.to || selection.fromName || selection.toName);
        bar.hidden = !active;
        if (toolbar) {
            var yearField = toolbar.querySelector('.upri-funding__year');
            var yearHidden = !!(yearField && yearField.hidden);
            toolbar.hidden = yearHidden && !active;
            toolbar.classList.toggle('has-filter', active);
        }
        if (!label || !active) return;
        if (selection.from || selection.fromName) {
            label.textContent = fill(UI.flow_filter_pns || 'Showing countries funded by {name}', {
                name: selection.fromName || selection.from
            });
        } else {
            label.textContent = fill(UI.flow_filter_host || 'Showing societies funding {name}', {
                name: selection.toName || selection.to
            });
        }
    }

    function publishSelection() {
        if (applyingSync || !window.UprPartySync) return;
        UprPartySync.publish({
            from: selection.from,
            to: selection.to,
            fromName: selection.fromName,
            toName: selection.toName
        });
    }

    function setSelection(next, redraw) {
        selection = {
            from: String(next.from || '').toUpperCase(),
            to: String(next.to || '').toUpperCase(),
            fromName: String(next.fromName || ''),
            toName: String(next.toName || '')
        };
        publishSelection();
        if (redraw) draw(true);
    }

    function toggleRow(role, row) {
        var code = row.code || '';
        var name = row.name || '';
        if (role === 'from') {
            var sameFrom = (code && code === selection.from) || (!code && name && name === selection.fromName);
            if (sameFrom) {
                setSelection({ from: '', to: '', fromName: '', toName: '' }, true);
                return;
            }
            setSelection({ from: code, to: '', fromName: name, toName: '' }, true);
            return;
        }
        var sameTo = (code && code === selection.to) || (!code && name && name === selection.toName);
        if (sameTo) {
            setSelection({ from: '', to: '', fromName: '', toName: '' }, true);
            return;
        }
        setSelection({ from: '', to: code, fromName: '', toName: name }, true);
    }

    function renderColumn(host, title, rows, tone, role, previousWidths) {
        host.replaceChildren();
        var heading = document.createElement('h4');
        heading.className = 'upri-flow-bars__title';
        heading.textContent = title;
        host.appendChild(heading);
        if (!rows.length) {
            var empty = document.createElement('p');
            empty.className = 'upri-flow-bars__col-empty';
            empty.textContent = UI.flow_bar_empty || 'No partners for this filter.';
            host.appendChild(empty);
            return;
        }
        var max = rows[0].value || 1;
        var selectedKey = role === 'from'
            ? (selection.from || selection.fromName)
            : (selection.to || selection.toName);
        rows.forEach(function (row, index) {
            var key = row.code || row.name;
            var line = document.createElement('div');
            line.className = 'upri-flow-bars__row is-interactive';
            line.setAttribute('data-key', key);
            line.setAttribute('role', 'button');
            line.tabIndex = 0;
            line.style.setProperty('--row-index', String(index));
            if (selectedKey && key === selectedKey) line.classList.add('is-selected');
            else if (selectedKey) line.classList.add('is-dimmed');
            var label = document.createElement('span');
            label.className = 'upri-flow-bars__label';
            label.textContent = row.name;
            label.title = row.name;
            var track = document.createElement('span');
            track.className = 'upri-flow-bars__track';
            var bar = document.createElement('span');
            bar.className = 'upri-flow-bars__fill upri-flow-bars__fill--' + tone;
            var target = Math.max(0, Math.min(100, (row.value / max) * 100)) + '%';
            var prior = previousWidths && previousWidths[key];
            bar.style.width = prior || '0%';
            var value = document.createElement('span');
            value.className = 'upri-flow-bars__value';
            value.textContent = compactMoney(row.value);
            track.appendChild(bar);
            bar.appendChild(value);
            line.appendChild(label);
            line.appendChild(track);
            line.addEventListener('click', function () { toggleRow(role, row); });
            line.addEventListener('keydown', function (event) {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    toggleRow(role, row);
                }
            });
            host.appendChild(line);
            requestAnimationFrame(function () {
                requestAnimationFrame(function () {
                    bar.style.width = target;
                });
            });
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
        var links = yearLinks();
        var board = byId('upri-funding-bars');
        var empty = byId('upri-funding-empty');
        show(board, !!links.length);
        show(empty, !links.length);
        if (!links.length) {
            if (empty) empty.textContent = fill(UI.flow_funding_empty || '', { year: selectedYear() || '' });
            updateFilterBar();
            return;
        }
        var sentHost = byId('upri-funding-sent');
        var recvHost = byId('upri-funding-received');
        var prevSent = snapshotWidths(sentHost);
        var prevRecv = snapshotWidths(recvHost);
        var sentLinks = (selection.to || selection.toName) ? links.filter(matchesTo) : links;
        var recvLinks = (selection.from || selection.fromName) ? links.filter(matchesFrom) : links;
        renderColumn(sentHost, UI.flow_sent || '', rank(sentLinks, 'from_name', 'from'), 'sent', 'from', prevSent);
        renderColumn(recvHost, UI.flow_received || '', rank(recvLinks, 'to_name', 'to'), 'received', 'to', prevRecv);
        updateFilterBar();
        var hint = byId('upri-funding-hint');
        if (!hint && board) {
            hint = document.createElement('p');
            hint.id = 'upri-funding-hint';
            hint.className = 'upri-flow-bars__hint';
            hint.textContent = UI.flow_bar_hint || 'Click a society or country bar to filter the other ranking.';
            board.appendChild(hint);
        }
    }

    function fillYears(links) {
        var select = byId('upri-funding-year');
        if (!select) return;
        var seen = {};
        links.forEach(function (link) { if (link.year) seen[link.year] = true; });
        var years = Object.keys(seen).map(Number).sort(function (a, b) { return b - a; });
        var preset = parseInt(root.getAttribute('data-year') || '', 10);
        var previous = parseInt(select.value, 10);
        var shared = window.UprYearSync ? parseInt(UprYearSync.read(), 10) : NaN;
        select.replaceChildren();
        years.forEach(function (year) {
            var option = document.createElement('option');
            option.value = String(year);
            option.textContent = String(year);
            select.appendChild(option);
        });
        var pick = years.indexOf(shared) !== -1 ? shared
            : (years.indexOf(previous) !== -1 ? previous
            : (years.indexOf(preset) !== -1 ? preset
            : (years.indexOf(DEFAULT_YEAR) !== -1 ? DEFAULT_YEAR : years[0])));
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

    function applyStoredParty() {
        if (!window.UprPartySync) return;
        var party = UprPartySync.read();
        if (!party) return;
        selection = {
            from: String(party.from || '').toUpperCase(),
            to: String(party.to || '').toUpperCase(),
            fromName: String(party.fromName || ''),
            toName: String(party.toName || '')
        };
    }

    function applyFundingPayload(payload) {
        funding = (payload && payload.flows && payload.flows.funding) || [];
        show(byId('upri-funding-loading'), false);
        show(byId('upri-funding-error'), false);
        fillYears(funding);
        ready = true;
        applyFollowedYear();
        applyStoredParty();
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
            if (window.UprYearSync) UprYearSync.publish(yearSelect.value);
            syncFollowedYear(yearSelect.value);
            setSelection({ from: '', to: '', fromName: '', toName: '' }, false);
            draw();
        });
    }
    if (window.UprYearSync && yearSelect && !followedSelect()) {
        UprYearSync.subscribe(function (year) {
            if (String(yearSelect.value) === String(year)) return;
            var has = Array.prototype.some.call(yearSelect.options, function (option) {
                return option.value === String(year);
            });
            if (!has) return;
            yearSelect.value = String(year);
            setSelection({ from: '', to: '', fromName: '', toName: '' }, false);
            draw();
        });
    }
    if (window.UprPartySync) {
        UprPartySync.subscribe(function (party) {
            applyingSync = true;
            selection = {
                from: String(party.from || '').toUpperCase(),
                to: String(party.to || '').toUpperCase(),
                fromName: String(party.fromName || ''),
                toName: String(party.toName || '')
            };
            applyingSync = false;
            if (ready) draw(true);
        });
    }
    var followed = followedSelect();
    if (followed) {
        followed.addEventListener('change', function () {
            if (!ready) return;
            applyFollowedYear();
            setSelection({ from: '', to: '', fromName: '', toName: '' }, false);
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
