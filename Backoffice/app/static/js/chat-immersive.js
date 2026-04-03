/**
 * Immersive chat page – sidebar chat list and New chat.
 * Runs only on the immersive chat page (body.chat-immersive).
 * Depends on chatbot.js (window.ngodbChatbot) being initialized first.
 */
(function () {
    'use strict';

    if (!document.body || !document.body.classList.contains('chat-immersive')) {
        return;
    }

    const LIST_ID = 'chatImmersiveChatList';
    const NEW_CHAT_ID = 'chatImmersiveNewChat';
    const TITLE_ID = 'chatImmersiveCurrentTitle';
    const SEARCH_ID = 'chatImmersiveSearch';
    const SIDEBAR_TOGGLE_ID = 'chatImmersiveSidebarToggle';
    const PAGE_ID = 'chatImmersivePage';
    const SIDEBAR_STORAGE_KEY = 'chatImmersiveSidebarCollapsed';
    const WORLDMAP_PROMPT_BTN_ID = 'chatImmersiveGenerateWorldmapQuery';

    /** Log only when sidebar-running debug is explicitly enabled. */
    function sidebarRunningLog() {
        if (window.CHAT_SIDEBAR_RUNNING_DEBUG) {
            try {
                console.log.apply(console, ['[Immersive sidebar running]'].concat(Array.prototype.slice.call(arguments)));
            } catch (e) { /* ignore */ }
        }
    }

    var lastConversations = [];
    var leafletLoadPromise = null;
    var worldGeoJsonPromise = null;
    var apexLoadPromise = null;
    var pendingMapRenderRetries = [];
    var hasLoadedConversationsOnce = false;
    var isRefreshingConversations = false;

    /** Resolve a UI string: prefer server-injected CHAT_UI_STRINGS, then chatbot _uiString, then fallback */
    function t(key, fallback) {
        var s = window.CHAT_UI_STRINGS;
        if (s && s[key] != null) return s[key];
        var bot = getChatbot();
        if (bot && bot._uiString) {
            var v = bot._uiString(key);
            if (v != null) return v;
        }
        return fallback || key;
    }

    function getSidebarCollapsed() {
        try {
            return localStorage.getItem(SIDEBAR_STORAGE_KEY) === 'true';
        } catch (e) {
            return false;
        }
    }

    function setSidebarCollapsed(collapsed) {
        try {
            if (collapsed) {
                localStorage.setItem(SIDEBAR_STORAGE_KEY, 'true');
            } else {
                localStorage.removeItem(SIDEBAR_STORAGE_KEY);
            }
        } catch (e) { /* ignore */ }
    }

    function setSidebarCollapsedUI(collapsed) {
        var page = document.getElementById(PAGE_ID);
        if (page) {
            if (collapsed) {
                page.classList.add('chat-immersive-sidebar-collapsed');
            } else {
                page.classList.remove('chat-immersive-sidebar-collapsed');
            }
        }
    }

    function getChatbot() {
        return window.ngodbChatbot || null;
    }

    function normalizeMapPayload(payload) {
        if (!payload || typeof payload !== 'object') return null;
        var root = (payload.map_payload && typeof payload.map_payload === 'object') ? payload.map_payload : payload;
        if (!root || typeof root !== 'object') return null;
        var rows = Array.isArray(root.countries) ? root.countries : (Array.isArray(root.locations) ? root.locations : (Array.isArray(root.data) ? root.data : []));
        if (!rows.length) return null;
        if (window.ngodbChatImmersiveMapDebug) {
            try {
                var sample = rows.slice(0, 3);
                console.log('[Immersive map] normalizeMapPayload: rows count', rows.length, 'sample[0] keys', sample[0] ? Object.keys(sample[0]) : [], 'sample', JSON.stringify(sample));
            } catch (e) { /* ignore */ }
        }
        function extractYear(v) {
            if (v == null) return null;
            if (typeof v === 'number' && isFinite(v)) {
                var y = Math.round(v);
                if (y >= 1900 && y <= 2100) return y;
            }
            try {
                var s = String(v || '');
                var m = s.match(/\b(19\d{2}|20\d{2})\b/g);
                if (!m || !m.length) return null;
                var max = null;
                for (var i = 0; i < m.length; i++) {
                    var n = parseInt(m[i], 10);
                    if (!isFinite(n)) continue;
                    if (max === null || n > max) max = n;
                }
                return max;
            } catch (e) {
                return null;
            }
        }
        var countries = rows.map(function (row) {
            if (!row || typeof row !== 'object') return null;
            var iso3 = String(row.iso3 || row.country_iso3 || row.code || '').trim().toUpperCase();
            var rawValue = row.value;
            if (typeof rawValue === 'string') rawValue = rawValue.replace(/,/g, '').trim();
            var value = Number(rawValue);
            if (!/^[A-Z]{3}$/.test(iso3) || !isFinite(value)) return null;
            var year = extractYear(row.year || row.period_used || row.period);
            var out = {
                iso3: iso3,
                value: value,
                label: String(row.label || row.name || iso3).trim() || iso3,
                year: year
            };
            ['region', 'sector', 'category', 'status', 'type', 'group'].forEach(function (k) {
                var v = row[k];
                if (v != null && v !== '') { out[k] = String(v).trim(); }
            });
            return out;
        }).filter(Boolean);
        if (!countries.length) return null;
        return {
            type: 'worldmap',
            title: String(root.title || 'World map').trim() || 'World map',
            metric: String(root.metric || root.value_field || 'value').trim() || 'value',
            countries: countries
        };
    }

    function formatNumber(value) {
        var n = Number(value);
        if (!isFinite(n)) return String(value == null ? '' : value);
        var isInt = Math.abs(n - Math.round(n)) < 1e-9;
        try {
            return new Intl.NumberFormat(undefined, {
                maximumFractionDigits: isInt ? 0 : 2,
                minimumFractionDigits: 0
            }).format(n);
        } catch (e) {
            // Fallback with commas (integer-ish)
            var s = isInt ? String(Math.round(n)) : String(n);
            return s.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
        }
    }

    function escapeHtml(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    /**
     * Smart table display limits by size: ranges + minimum hidden count (absolute and % of total) before showing "Show more".
     * Returns { initialVisible, showExpand }.
     */
    function getDataTableDisplayLimit(total) {
        if (total <= 0) return { initialVisible: 0, showExpand: false };
        var cap;
        var minHidden;
        if (total <= 20) {
            return { initialVisible: total, showExpand: false };
        }
        if (total <= 50) {
            cap = 20;
            minHidden = 5;
        } else if (total <= 120) {
            cap = 30;
            minHidden = Math.max(5, Math.ceil(total * 0.1));
        } else if (total <= 300) {
            cap = 50;
            minHidden = Math.max(8, Math.ceil(total * 0.08));
        } else {
            cap = 75;
            minHidden = Math.max(12, Math.ceil(total * 0.05));
        }
        var initialVisible = Math.min(cap, total);
        var hidden = total - initialVisible;
        var showExpand = hidden >= minHidden;
        if (!showExpand) initialVisible = total;
        return { initialVisible: initialVisible, showExpand: showExpand };
    }

    /** Build data table from the same payload used for the chart/map (one source of truth). */
    function buildDataTableFromPayload(normalized) {
        if (!normalized || typeof normalized !== 'object') return null;
        var type = String(normalized.type || '').toLowerCase();
        var wrapper = document.createElement('div');
        wrapper.className = 'chat-immersive-data-table';
        wrapper.style.marginTop = '1rem';
        wrapper.style.borderTop = '1px solid #e2e8f0';
        wrapper.style.paddingTop = '0.75rem';

        if (type === 'line' || type === 'linechart' || type === 'timeseries') {
            var series = Array.isArray(normalized.series) ? normalized.series : [];
            if (!series.length) return null;
            var hasStatus = series.some(function (p) { return p && (p.data_status != null && String(p.data_status).trim() !== ''); });

            function normalizeStatusLabel(raw) {
                var st = (raw != null && String(raw).trim() !== '') ? String(raw).trim() : '';
                if (!st) return '';
                if (st.toLowerCase() === 'saved') return 'Saved';
                if (st.toLowerCase() === 'submitted') return 'Submitted';
                if (st.toLowerCase() === 'approved') return 'Approved';
                return st.charAt(0).toUpperCase() + st.slice(1);
            }

            var rows = series.reduce(function (acc, p) {
                if (!p) return acc;
                var yearRaw = (p.x != null) ? p.x : p.year;
                var yearNum = Number(yearRaw);
                var year = Number.isFinite(yearNum) ? String(Math.round(yearNum)) : String(yearRaw == null ? '' : yearRaw);
                var valRaw = (p.y != null) ? p.y : p.value;
                var valueNum = Number(valRaw);
                var valueText = Number.isFinite(valueNum) ? formatNumber(valueNum) : String(valRaw == null ? '' : valRaw);
                var statusText = hasStatus ? normalizeStatusLabel(p.data_status) : '';
                acc.push({
                    year: year,
                    yearNum: Number.isFinite(yearNum) ? yearNum : null,
                    valueText: valueText,
                    valueNum: Number.isFinite(valueNum) ? valueNum : null,
                    statusText: statusText
                });
                return acc;
            }, []);

            if (!rows.length) return null;

            var rowData = rows.map(function (r) {
                return {
                    year: r.year,
                    yearNum: r.yearNum,
                    value: r.valueNum != null ? r.valueNum : r.valueText,
                    valueNum: r.valueNum,
                    status: r.statusText || ''
                };
            });

            var table = document.createElement('table');
            table.setAttribute('role', 'table');
            table.style.width = '100%';
            table.style.fontSize = '0.8125rem';
            table.style.borderCollapse = 'collapse';
            table.style.border = '1px solid #e2e8f0';
            table.style.borderRadius = '0.5rem';
            table.style.overflow = 'hidden';
            var thead = document.createElement('thead');
            var headerRow = document.createElement('tr');
            ['Year', 'Value'].concat(hasStatus ? ['Status'] : []).forEach(function (label) {
                var th = document.createElement('th');
                th.textContent = label;
                th.style.textAlign = 'left';
                th.style.padding = '0.4rem 0.5rem';
                th.style.borderBottom = '1px solid #e2e8f0';
                th.style.fontWeight = '600';
                th.style.color = '#475569';
                headerRow.appendChild(th);
            });
            thead.appendChild(headerRow);
            table.appendChild(thead);
            var tbody = document.createElement('tbody');
            var totalRows = rowData.length;
            var limit = getDataTableDisplayLimit(totalRows);
            var initialVisible = limit.initialVisible;
            var hiddenRows = [];
            function buildRow(row, idx) {
                var tr = document.createElement('tr');
                tr.style.background = idx % 2 === 1 ? 'rgba(248, 250, 252, 0.6)' : 'transparent';
                var cells = [row.year, row.valueNum != null ? formatNumber(row.valueNum) : row.value];
                if (hasStatus) cells.push(row.status || '');
                cells.forEach(function (cell) {
                    var td = document.createElement('td');
                    td.textContent = String(cell == null ? '' : cell);
                    td.style.padding = '0.35rem 0.5rem';
                    td.style.borderBottom = '1px solid #f1f5f9';
                    td.style.color = '#334155';
                    tr.appendChild(td);
                });
                return tr;
            }
            for (var i = 0; i < initialVisible; i++) {
                tbody.appendChild(buildRow(rowData[i], i));
            }
            for (var j = initialVisible; j < totalRows; j++) {
                hiddenRows.push({ row: rowData[j], idx: j });
            }
            table.appendChild(tbody);
            wrapper.appendChild(table);
            if (hiddenRows.length > 0) {
                var btn = document.createElement('button');
                btn.type = 'button';
                btn.textContent = 'Show more rows (' + hiddenRows.length + ')';
                btn.style.marginTop = '0.5rem';
                btn.style.padding = '0.35rem 0.65rem';
                btn.style.border = '1px solid #cbd5e1';
                btn.style.borderRadius = '0.375rem';
                btn.style.background = '#fff';
                btn.style.color = '#334155';
                btn.style.cursor = 'pointer';
                btn.addEventListener('click', function () {
                    hiddenRows.forEach(function (entry) {
                        tbody.appendChild(buildRow(entry.row, entry.idx));
                    });
                    hiddenRows = [];
                    btn.remove();
                });
                wrapper.appendChild(btn);
            }
            return wrapper;
        }

        if (type === 'worldmap' || type === 'world_map' || type === 'choropleth') {
            var countries = Array.isArray(normalized.countries) ? normalized.countries : [];
            if (!countries.length) return null;
            var hasYear = countries.some(function (r) { return r && (r.year != null && r.year !== ''); });
            var hasRegion = countries.some(function (r) { return r && (r.region != null && r.region !== ''); });
            var table = document.createElement('table');
            table.setAttribute('role', 'table');
            table.style.width = '100%';
            table.style.fontSize = '0.8125rem';
            table.style.borderCollapse = 'collapse';
            var thead = document.createElement('thead');
            var headerRow = document.createElement('tr');
            var mapHeaders = ['Country', 'Value'];
            if (hasYear) mapHeaders.push('Year');
            if (hasRegion) mapHeaders.push('Region');
            mapHeaders.forEach(function (label) {
                var th = document.createElement('th');
                th.textContent = label;
                th.style.textAlign = 'left';
                th.style.padding = '0.4rem 0.5rem';
                th.style.borderBottom = '1px solid #e2e8f0';
                th.style.fontWeight = '600';
                th.style.color = '#475569';
                headerRow.appendChild(th);
            });
            thead.appendChild(headerRow);
            table.appendChild(thead);
            var tbody = document.createElement('tbody');
            var totalMap = countries.length;
            var limitMap = getDataTableDisplayLimit(totalMap);
            var initialVisibleMap = limitMap.initialVisible;
            var hiddenMapRows = [];
            function buildMapRow(row, idx) {
                if (!row) return null;
                var tr = document.createElement('tr');
                tr.style.background = idx % 2 === 1 ? 'rgba(248, 250, 252, 0.6)' : 'transparent';
                var label = String(row.label || row.name || row.iso3 || '').trim() || row.iso3 || '';
                var valueText = (row.value != null && Number.isFinite(Number(row.value))) ? formatNumber(Number(row.value)) : String(row.value == null ? '' : row.value);
                var yearText = (row.year != null && row.year !== '') ? String(row.year) : '';
                var regionText = (row.region != null && row.region !== '') ? String(row.region).trim() : '';
                var cells = [label, valueText];
                if (hasYear) cells.push(yearText);
                if (hasRegion) cells.push(regionText);
                cells.forEach(function (text) {
                    var td = document.createElement('td');
                    td.textContent = text;
                    td.style.padding = '0.35rem 0.5rem';
                    td.style.borderBottom = '1px solid #f1f5f9';
                    td.style.color = '#334155';
                    tr.appendChild(td);
                });
                return tr;
            }
            for (var i = 0; i < initialVisibleMap; i++) {
                var row = countries[i];
                var tr = buildMapRow(row, i);
                if (tr) tbody.appendChild(tr);
            }
            for (var j = initialVisibleMap; j < totalMap; j++) {
                hiddenMapRows.push({ row: countries[j], idx: j });
            }
            table.appendChild(tbody);
            wrapper.appendChild(table);
            if (limitMap.showExpand && hiddenMapRows.length > 0) {
                var expandBtnMap = document.createElement('button');
                expandBtnMap.type = 'button';
                expandBtnMap.textContent = 'Show ' + hiddenMapRows.length + ' more';
                expandBtnMap.style.cssText = 'marginTop:0.5rem;padding:0.35rem 0.6rem;fontSize:0.8rem;border:1px solid #e2e8f0;borderRadius:0.375rem;cursor:pointer;background:#f8fafc;color:#475569;';
                expandBtnMap.addEventListener('click', function () {
                    hiddenMapRows.forEach(function (item) {
                        var tr = buildMapRow(item.row, item.idx);
                        if (tr) tbody.appendChild(tr);
                    });
                    hiddenMapRows.length = 0;
                    expandBtnMap.style.display = 'none';
                });
                wrapper.appendChild(expandBtnMap);
            }
            return wrapper;
        }

        return null;
    }

    /** Build a view switch (e.g. Map|Table or Chart|Table) and two containers. Toggle shows one at a time. */
    function createViewSwitch(visualLabel, tableLabel) {
        visualLabel = visualLabel || 'Chart';
        tableLabel = tableLabel || 'Table';
        var wrap = document.createElement('div');
        wrap.style.display = 'inline-flex';
        wrap.style.alignItems = 'center';
        wrap.style.gap = '0.25rem';
        var viewVisual = document.createElement('div');
        viewVisual.className = 'chat-immersive-view-visual';
        viewVisual.style.width = '100%';
        var viewTable = document.createElement('div');
        viewTable.className = 'chat-immersive-view-table';
        viewTable.style.display = 'none';
        viewTable.style.width = '100%';

        var btnStyle = 'padding:0.25rem 0.5rem;font-size:0.75rem;border:1px solid #e2e8f0;border-radius:0.375rem;cursor:pointer;background:#f8fafc;color:#475569;';
        var btnActiveStyle = 'background:#2563eb;color:#fff;border-color:#2563eb;';

        var btnVisual = document.createElement('button');
        btnVisual.type = 'button';
        btnVisual.setAttribute('aria-label', visualLabel);
        btnVisual.textContent = visualLabel;
        btnVisual.style.cssText = btnStyle + btnActiveStyle;
        var btnTable = document.createElement('button');
        btnTable.type = 'button';
        btnTable.setAttribute('aria-label', tableLabel);
        btnTable.textContent = tableLabel;
        btnTable.style.cssText = btnStyle;

        function setActive(which) {
            if (which === 'visual') {
                viewVisual.style.display = '';
                viewTable.style.display = 'none';
                btnVisual.style.cssText = btnStyle + btnActiveStyle;
                btnTable.style.cssText = btnStyle;
            } else {
                viewVisual.style.display = 'none';
                viewTable.style.display = '';
                btnTable.style.cssText = btnStyle + btnActiveStyle;
                btnVisual.style.cssText = btnStyle;
                try { viewTable.dispatchEvent(new CustomEvent('chat-immersive-table-shown', { bubbles: true })); } catch (e) { /* ignore */ }
            }
        }
        btnVisual.addEventListener('click', function () { setActive('visual'); });
        btnTable.addEventListener('click', function () { setActive('table'); });
        wrap.appendChild(btnVisual);
        wrap.appendChild(btnTable);
        return { switchContainer: wrap, viewVisual: viewVisual, viewTable: viewTable };
    }

    function ensureLeaflet() {
        if (window.L && typeof window.L.map === 'function') return Promise.resolve(window.L);
        if (leafletLoadPromise) return leafletLoadPromise;
        leafletLoadPromise = new Promise(function (resolve, reject) {
            var cssHref = '/static/vendor/leaflet/leaflet.css';
            if (!document.querySelector('link[data-chat-immersive-leaflet]')) {
                var css = document.createElement('link');
                css.rel = 'stylesheet';
                css.href = cssHref;
                css.setAttribute('data-chat-immersive-leaflet', '1');
                document.head.appendChild(css);
            }
            var existing = document.querySelector('script[data-chat-immersive-leaflet]');
            if (existing) {
                existing.addEventListener('load', function () { resolve(window.L); }, { once: true });
                existing.addEventListener('error', function () { reject(new Error('Leaflet failed to load')); }, { once: true });
                return;
            }
            var script = document.createElement('script');
            script.src = '/static/vendor/leaflet/leaflet.js';
            script.defer = true;
            script.setAttribute('data-chat-immersive-leaflet', '1');
            script.onload = function () { resolve(window.L); };
            script.onerror = function () { reject(new Error('Leaflet failed to load')); };
            document.head.appendChild(script);
        });
        return leafletLoadPromise;
    }

    function ensureApexCharts() {
        if (window.ApexCharts && typeof window.ApexCharts === 'function') return Promise.resolve(window.ApexCharts);
        if (apexLoadPromise) return apexLoadPromise;
        apexLoadPromise = new Promise(function (resolve, reject) {
            var existing = document.querySelector('script[data-chat-immersive-apex]');
            if (existing) {
                existing.addEventListener('load', function () { resolve(window.ApexCharts); }, { once: true });
                existing.addEventListener('error', function () { reject(new Error('ApexCharts failed to load')); }, { once: true });
                return;
            }
            var script = document.createElement('script');
            script.src = '/static/libs/apexcharts.min.js';
            script.defer = true;
            script.setAttribute('data-chat-immersive-apex', '1');
            script.onload = function () { resolve(window.ApexCharts); };
            script.onerror = function () { reject(new Error('ApexCharts failed to load')); };
            document.head.appendChild(script);
        });
        return apexLoadPromise;
    }

    function normalizeChartPayload(payload) {
        if (!payload || typeof payload !== 'object') return null;
        var root = (payload.chart_payload && typeof payload.chart_payload === 'object') ? payload.chart_payload : payload;
        if (!root || typeof root !== 'object') return null;
        var type = String(root.type || root.chart_type || '').trim().toLowerCase();
        var lineTypes = { '': true, 'line': true, 'linechart': true, 'timeseries': true };
        if (!(type in lineTypes)) return null;
        var rows = Array.isArray(root.series) ? root.series : (Array.isArray(root.data) ? root.data : (Array.isArray(root.points) ? root.points : []));
        if (!rows.length) return null;
        var pts = rows.map(function (r) {
            if (!r || typeof r !== 'object') return null;
            var x = r.x != null ? r.x : (r.year != null ? r.year : r.period);
            var y = r.y != null ? r.y : r.value;
            var xx = Number(x);
            var yy = Number(y);
            if (!isFinite(xx) || !isFinite(yy)) return null;
            var year = Math.round(xx);
            if (year < 1900 || year > 2100) return null;
            return { x: year, y: yy, data_status: r.data_status || null, period_name: r.period_name || null };
        }).filter(Boolean);
        if (!pts.length) return null;
        pts.sort(function (a, b) { return (a.x || 0) - (b.x || 0); });
        var metric = String(root.metric || root.y_label || 'value').trim() || 'value';
        var title = String(root.title || (metric + ' over time')).trim() || (metric + ' over time');
        return {
            type: 'line',
            title: title,
            metric: metric,
            country: String(root.country || '').trim() || null,
            series: pts
        };
    }

    function normalizeBarChartPayload(payload) {
        if (!payload || typeof payload !== 'object') return null;
        var root = (payload.chart_payload && typeof payload.chart_payload === 'object') ? payload.chart_payload : payload;
        if (!root || typeof root !== 'object') return null;
        var type = String(root.type || root.chart_type || '').trim().toLowerCase();
        if (type !== 'bar' && type !== 'barchart') return null;
        var cats = Array.isArray(root.categories) ? root.categories : [];
        if (!cats.length) return null;
        var categories = cats.map(function (c) {
            if (!c || typeof c !== 'object') return null;
            var label = String(c.label || c.name || '').trim();
            var value = Number(c.value);
            if (!label || !isFinite(value)) return null;
            return { label: label, value: value };
        }).filter(Boolean);
        if (categories.length < 2) return null;
        var metric = String(root.metric || 'Value').trim() || 'Value';
        var title = String(root.title || (metric + ' comparison')).trim();
        var orientation = String(root.orientation || '').toLowerCase();
        if (orientation !== 'horizontal' && orientation !== 'vertical') {
            orientation = categories.length > 6 ? 'horizontal' : 'vertical';
        }
        return {
            type: 'bar',
            title: title,
            metric: metric,
            categories: categories,
            orientation: orientation
        };
    }

    function normalizePieChartPayload(payload) {
        if (!payload || typeof payload !== 'object') return null;
        var root = (payload.chart_payload && typeof payload.chart_payload === 'object') ? payload.chart_payload : payload;
        if (!root || typeof root !== 'object') return null;
        var type = String(root.type || root.chart_type || '').trim().toLowerCase();
        if (type !== 'pie' && type !== 'donut') return null;
        var raw = Array.isArray(root.slices) ? root.slices : (Array.isArray(root.data) ? root.data : []);
        if (raw.length < 2) return null;
        var slices = raw.map(function (s) {
            if (!s || typeof s !== 'object') return null;
            var label = String(s.label || s.name || '').trim();
            var value = Number(s.value);
            if (!label || !isFinite(value) || value < 0) return null;
            return { label: label, value: value };
        }).filter(Boolean);
        if (slices.length < 2) return null;
        var title = String(root.title || 'Distribution').trim();
        return { type: 'pie', title: title, slices: slices };
    }

    function fetchWorldGeoJson() {
        if (worldGeoJsonPromise) return worldGeoJsonPromise;
        var urls = [
            // jsDelivr is allow-listed in CSP (connect-src), unlike raw.githubusercontent.com.
            'https://cdn.jsdelivr.net/gh/datasets/geo-countries@master/data/countries.geojson',
            'https://cdn.jsdelivr.net/gh/holtzy/D3-graph-gallery@master/DATA/world.geojson'
        ];
        worldGeoJsonPromise = (async function () {
            for (var i = 0; i < urls.length; i++) {
                try {
                    var res = await fetch(urls[i], { cache: 'force-cache' });
                    if (!res.ok) continue;
                    var data = await res.json();
                    if (data && Array.isArray(data.features) && data.features.length) return data;
                } catch (e) { /* try next source */ }
            }
            throw new Error('World GeoJSON unavailable');
        })();
        return worldGeoJsonPromise;
    }

    function featureIso3(feature) {
        var p = (feature && feature.properties) || {};
        var v = p.ISO_A3 || p.ADM0_A3 || p.iso_a3 || p.ISO3 || p.ISO3_CODE || p['ISO3166-1-Alpha-3'];
        if (!v && p.iso3) v = p.iso3;
        if (!v && p.id && typeof p.id === 'string' && p.id.length === 3) v = p.id;
        var out = String(v || '').trim().toUpperCase();
        return /^[A-Z]{3}$/.test(out) ? out : '';
    }

    function colorFor(value, min, max) {
        if (!isFinite(value)) return '#e5e7eb';
        if (!isFinite(min) || !isFinite(max) || max <= min) return '#1d4ed8';
        var t = (value - min) / (max - min);
        if (t < 0) t = 0;
        if (t > 1) t = 1;
        if (t < 0.2) return '#dbeafe';
        if (t < 0.4) return '#93c5fd';
        if (t < 0.6) return '#60a5fa';
        if (t < 0.8) return '#3b82f6';
        return '#1d4ed8';
    }

    // Generic categorical palette for any category (region, sector, status, type, etc.).
    // Colors are assigned by sorted category value so each category gets a unique color.
    var CATEGORY_PALETTE = ['#0ea5e9', '#22c55e', '#eab308', '#a855f7', '#ef4444', '#f97316', '#06b6d4', '#84cc16', '#ec4899', '#6366f1', '#14b8a6', '#f43f5e'];
    var CATEGORY_FIELD_CANDIDATES = ['region', 'sector', 'category', 'status', 'type', 'group'];
    function colorForCategory(field, value) {
        if (!field || !value || !String(value).trim()) return '#94a3b8';
        var key = String(field) + '\x00' + String(value).trim();
        if (!colorForCategory._cache) colorForCategory._cache = {};
        if (colorForCategory._cache[key]) return colorForCategory._cache[key];
        var orderedKey = field;
        if (!colorForCategory._ordered) colorForCategory._ordered = {};
        var ordered = colorForCategory._ordered[orderedKey] || (colorForCategory._ordered[orderedKey] = []);
        var val = String(value).trim();
        if (ordered.indexOf(val) === -1) {
            ordered.push(val);
            ordered.sort();
            for (var i = 0; i < ordered.length; i++) {
                var c = CATEGORY_PALETTE[i % CATEGORY_PALETTE.length];
                colorForCategory._cache[String(field) + '\x00' + ordered[i]] = c;
                if (typeof colorForCategory._log === 'function') colorForCategory._log('assign category -> color', field, ordered[i], c);
            }
        }
        return colorForCategory._cache[key];
    }
    function humanizeCategoryField(field) {
        if (!field) return 'Category';
        var s = String(field).trim();
        return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
    }
    function detectCategoryField(normalized, values, min, max) {
        if (!normalized || !Array.isArray(normalized.countries) || !values.length || min !== max) return null;
        var hint = (normalized.color_by || normalized.category_field || '').trim().toLowerCase();
        var candidates = hint ? [hint].concat(CATEGORY_FIELD_CANDIDATES.filter(function (f) { return f !== hint; })) : CATEGORY_FIELD_CANDIDATES;
        for (var c = 0; c < candidates.length; c++) {
            var field = candidates[c];
            var seen = {};
            var list = [];
            normalized.countries.forEach(function (r) {
                var v = r && String(r[field] || '').trim();
                if (v && !seen[v]) { seen[v] = true; list.push(v); }
            });
            list.sort();
            if (list.length >= 2) return { field: field, values: list };
        }
        return null;
    }
    function buildWorldmapCategoryLegendSpec(normalized, categoryField, categoryValues) {
        if (!normalized || !categoryField || !Array.isArray(categoryValues) || !categoryValues.length) return null;
        var items = categoryValues.map(function (val) {
            return {
                color: colorForCategory(categoryField, val),
                label: val,
                filter: { kind: 'category', categoryField: categoryField, categoryValue: val }
            };
        });
        if (typeof buildWorldmapCategoryLegendSpec._log === 'function') {
            buildWorldmapCategoryLegendSpec._log('category legend:', categoryField, items.length, items.map(function (i) { return i.label + ':' + i.color; }));
        }
        return { title: humanizeCategoryField(categoryField), items: items };
    }

    function isLikelyYearValues(values) {
        if (!values || !values.length) return false;
        var n = 0;
        var yearish = 0;
        for (var i = 0; i < values.length; i++) {
            var v = Number(values[i]);
            if (!isFinite(v)) continue;
            n++;
            var y = Math.round(v);
            if (Math.abs(v - y) < 1e-9 && y >= 1900 && y <= 2100) yearish++;
        }
        if (!n) return false;
        return (yearish / n) >= 0.7;
    }

    function formatLegendNumber(value, opts) {
        opts = opts || {};
        var yearish = !!opts.yearish;
        var n = Number(value);
        if (!isFinite(n)) return String(value == null ? '' : value);
        if (yearish) return String(Math.round(n));
        var abs = Math.abs(n);
        var maxFrac = (opts.maxFractionDigits != null) ? Number(opts.maxFractionDigits) : (abs < 10 ? 2 : 0);
        try {
            return new Intl.NumberFormat(undefined, {
                maximumFractionDigits: isFinite(maxFrac) ? maxFrac : 0,
                minimumFractionDigits: 0
            }).format(n);
        } catch (e) {
            return String(n);
        }
    }

    function buildWorldmapLegendSpec(normalized, values, min, max, geo, lookup) {
        if (!normalized || !values || !values.length) return null;
        if (!isFinite(min) || !isFinite(max)) return null;
        var uniq = {};
        for (var i = 0; i < values.length; i++) {
            var v = Number(values[i]);
            if (!isFinite(v)) continue;
            uniq[String(v)] = true;
        }
        var uniqueCount = Object.keys(uniq).length;
        // Hide legend when there is no meaningful scale (all values identical).
        if (uniqueCount <= 1 || max <= min) return null;

        var yearish = isLikelyYearValues(values);

        var hasMissing = true;
        try {
            if (geo && Array.isArray(geo.features)) {
                var total = 0;
                var have = 0;
                for (var j = 0; j < geo.features.length; j++) {
                    var iso3 = featureIso3(geo.features[j]);
                    if (!iso3) continue;
                    total++;
                    if (lookup && lookup[iso3]) have++;
                }
                hasMissing = total > have;
            }
        } catch (e) { /* ignore */ }

        var items = [];
        if (yearish) {
            // Prefer a discrete year legend when possible (more readable than bins).
            var yearsUniq = {};
            for (var k = 0; k < values.length; k++) {
                var yv = Number(values[k]);
                if (!isFinite(yv)) continue;
                var yy = Math.round(yv);
                if (yy >= 1900 && yy <= 2100) yearsUniq[String(yy)] = true;
            }
            var years = Object.keys(yearsUniq).map(function (s) { return parseInt(s, 10); }).filter(function (n) { return isFinite(n); });
            years.sort(function (a, b) { return a - b; });
            if (years.length && years.length <= 10) {
                for (var yi = 0; yi < years.length; yi++) {
                    var y = years[yi];
                    items.push({ color: colorFor(y, min, max), label: String(y), filter: { kind: 'value', value: y, yearish: true } });
                }
            } else {
                // Fall back to 5 bins.
                var spanY = max - min;
                for (var bi = 0; bi < 5; bi++) {
                    var aY = min + (bi / 5) * spanY;
                    var bY = min + ((bi + 1) / 5) * spanY;
                    var loY = Math.floor(aY);
                    var hiY = Math.ceil(bY);
                    if (hiY < loY) hiY = loY;
                    var labelY = (loY === hiY) ? String(loY) : (String(loY) + '–' + String(hiY));
                    var midY = (aY + bY) / 2;
                    items.push({ color: colorFor(midY, min, max), label: labelY, filter: { kind: 'range', lo: loY, hi: hiY, yearish: true } });
                }
            }
        } else {
            // For very small datasets (few distinct values), show a discrete legend instead of
            // 5-range bins. This avoids confusing empty ranges (e.g. 2 values -> 5 brackets).
            if (uniqueCount <= 5) {
                var uniqNums = Object.keys(uniq)
                    .map(function (s) { return Number(s); })
                    .filter(function (n) { return isFinite(n); });
                uniqNums.sort(function (a, b) { return a - b; });
                for (var ui = 0; ui < uniqNums.length; ui++) {
                    var vv = uniqNums[ui];
                    items.push({
                        color: colorFor(vv, min, max),
                        label: formatLegendNumber(vv, { maxFractionDigits: 2 }),
                        filter: { kind: 'value', value: vv, yearish: false }
                    });
                }
            } else {
                // Bin for readability when many distinct values.
                var bins = Math.min(5, Math.max(2, uniqueCount));
                var span = max - min;
                for (var b = 0; b < bins; b++) {
                    var a = min + (b / bins) * span;
                    var z = min + ((b + 1) / bins) * span;
                    var mid = (a + z) / 2;
                    items.push({
                        color: colorFor(mid, min, max),
                        label: formatLegendNumber(a, { maxFractionDigits: 2 }) + '–' + formatLegendNumber(z, { maxFractionDigits: 2 }),
                        filter: { kind: 'range', lo: a, hi: z, yearish: false }
                    });
                }
            }
        }

        if (!items.length) return null;
        if (hasMissing) {
            items.unshift({ color: '#e5e7eb', label: 'No data', filter: { kind: 'missing' } });
        }

        return {
            title: String(normalized.metric || 'Value').trim() || 'Value',
            items: items
        };
    }

    function addLeafletLegendControl(L, map, spec, opts) {
        if (!L || !map || !spec || !spec.items || !spec.items.length) return;
        opts = opts || {};
        try {
            var legend = L.control({ position: 'bottomleft' });
            legend.onAdd = function () {
                var div = L.DomUtil.create('div', 'chat-immersive-map-legend');
                // Inline styles to avoid needing CSS changes
                div.style.background = 'rgba(255,255,255,0.95)';
                div.style.border = '1px solid #e5e7eb';
                div.style.borderRadius = '0.5rem';
                div.style.boxShadow = '0 8px 20px rgba(15, 23, 42, 0.12)';
                div.style.padding = '0.5rem 0.6rem';
                div.style.fontSize = '12px';
                div.style.color = '#0f172a';
                div.style.lineHeight = '1.25';
                div.style.maxWidth = '220px';
                div.style.pointerEvents = 'auto';
                div.style.position = 'relative';

                var titleWrap = document.createElement('div');
                titleWrap.style.position = 'relative';
                titleWrap.style.marginBottom = '0.35rem';

                var title = document.createElement('div');
                title.style.fontWeight = '600';
                title.textContent = spec.title || 'Legend';
                titleWrap.appendChild(title);

                var closeBtn = document.createElement('button');
                closeBtn.type = 'button';
                closeBtn.setAttribute('aria-label', 'Hide legend');
                closeBtn.title = 'Hide legend';
                closeBtn.textContent = '\u00D7';
                closeBtn.style.cssText = 'position:absolute;top:0;right:0;display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;padding:0;border:none;border-radius:4px;background:rgba(255,255,255,0.95);color:#475569;cursor:pointer;font-size:18px;line-height:1;opacity:0;transition:opacity 0.15s ease;box-shadow:0 1px 3px rgba(0,0,0,0.1)';
                closeBtn.addEventListener('click', function (e) {
                    try { e.preventDefault(); e.stopPropagation(); } catch (err) { /* ignore */ }
                    div.style.display = 'none';
                });
                div.addEventListener('mouseenter', function () { closeBtn.style.opacity = '1'; });
                div.addEventListener('mouseleave', function () { closeBtn.style.opacity = '0'; });
                titleWrap.appendChild(closeBtn);
                div.appendChild(titleWrap);

                var activeIndex = null;

                function setActive(nextIndex) {
                    if (activeIndex === nextIndex) nextIndex = null;
                    activeIndex = nextIndex;
                    // Update UI selection
                    try {
                        var rows = div.querySelectorAll('[data-legend-index]');
                        rows.forEach(function (el) {
                            var idx = Number(el.getAttribute('data-legend-index'));
                            var isActive = (activeIndex != null && idx === activeIndex);
                            el.style.background = isActive ? 'rgba(37,99,235,0.08)' : 'transparent';
                            el.style.borderColor = isActive ? 'rgba(37,99,235,0.45)' : 'transparent';
                        });
                    } catch (e) { /* ignore */ }
                    // Notify consumer
                    try {
                        var item = (activeIndex != null) ? spec.items[activeIndex] : null;
                        var filter = item && item.filter ? item.filter : null;
                        if (typeof opts.onSelect === 'function') opts.onSelect(filter);
                    } catch (e) { /* ignore */ }
                }

                for (var i = 0; i < spec.items.length; i++) {
                    var it = spec.items[i];
                    var row = document.createElement('div');
                    row.style.display = 'flex';
                    row.style.alignItems = 'center';
                    row.style.gap = '0.4rem';
                    row.style.margin = '0.18rem 0';
                    row.style.cursor = 'pointer';
                    row.style.padding = '0.18rem 0.25rem';
                    row.style.borderRadius = '0.35rem';
                    row.style.border = '1px solid transparent';
                    row.setAttribute('role', 'button');
                    row.setAttribute('tabindex', '0');
                    row.setAttribute('data-legend-index', String(i));

                    var sw = document.createElement('span');
                    sw.style.display = 'inline-block';
                    sw.style.width = '14px';
                    sw.style.height = '10px';
                    sw.style.borderRadius = '3px';
                    sw.style.border = '1px solid rgba(15, 23, 42, 0.15)';
                    sw.style.background = String(it.color || '#e5e7eb');
                    row.appendChild(sw);

                    var lab = document.createElement('span');
                    lab.style.whiteSpace = 'nowrap';
                    lab.style.overflow = 'hidden';
                    lab.style.textOverflow = 'ellipsis';
                    lab.textContent = String(it.label || '');
                    row.appendChild(lab);

                    (function (idx) {
                        row.addEventListener('click', function (e) {
                            try { e.preventDefault(); } catch (err) { /* ignore */ }
                            setActive(idx);
                        });
                        row.addEventListener('keydown', function (e) {
                            var key = e && (e.key || e.code);
                            if (key === 'Enter' || key === ' ') {
                                try { e.preventDefault(); } catch (err) { /* ignore */ }
                                setActive(idx);
                            }
                        });
                    })(i);

                    div.appendChild(row);
                }

                // Prevent legend interactions from panning/zooming the map
                try {
                    L.DomEvent.disableClickPropagation(div);
                    L.DomEvent.disableScrollPropagation(div);
                } catch (e) { /* ignore */ }
                return div;
            };
            legend.addTo(map);
        } catch (e) { /* ignore */ }
    }

    function applyWorldmapLegendFilter(L, layer, feature, row, lookup, filter, normalized, min, max, colorByCategory, categoryField) {
        if (!L || !layer) return;
        function getFill() {
            if (!row) return '#e5e7eb';
            if (colorByCategory && categoryField && row[categoryField]) return colorForCategory(categoryField, row[categoryField]);
            return colorFor(Number(row.value), min, max);
        }
        if (!filter) {
            try {
                layer.setStyle({
                    color: '#ffffff',
                    weight: 0.6,
                    fillOpacity: row ? 0.85 : 0.35,
                    fillColor: getFill()
                });
            } catch (e) { /* ignore */ }
            return;
        }

        var iso3 = featureIso3(feature);
        var hasRow = !!(iso3 && lookup && lookup[iso3]);
        var match = false;
        if (filter.kind === 'category') {
            match = hasRow && row && String(row[filter.categoryField] || '').trim() === String(filter.categoryValue || '').trim();
        } else if (filter.kind === 'region') {
            match = hasRow && row && String(row.region || '').trim() === String(filter.region || '').trim();
        } else if (filter.kind === 'missing') {
            match = !hasRow;
        } else if (hasRow) {
            var v = Number((row || {}).value);
            if (isFinite(v)) {
                if (filter.kind === 'value') {
                    if (filter.yearish) {
                        match = Math.round(v) === Math.round(Number(filter.value));
                    } else {
                        match = Math.abs(v - Number(filter.value)) < 1e-9;
                    }
                } else if (filter.kind === 'range') {
                    var lo = Number(filter.lo);
                    var hi = Number(filter.hi);
                    if (filter.yearish) {
                        v = Math.round(v);
                        lo = Math.round(lo);
                        hi = Math.round(hi);
                    }
                    match = isFinite(lo) && isFinite(hi) && v >= lo && v <= hi;
                }
            }
        }

        try {
            var fillColor = getFill();
            if (match) {
                layer.setStyle({
                    color: '#0f172a',
                    weight: 1.2,
                    fillOpacity: 0.95,
                    fillColor: fillColor
                });
                try { layer.bringToFront(); } catch (e) { /* ignore */ }
            } else {
                layer.setStyle({
                    color: '#ffffff',
                    weight: 0.4,
                    fillOpacity: hasRow ? 0.12 : 0.06,
                    fillColor: fillColor
                });
            }
        } catch (e) { /* ignore */ }
    }

    function slugifyFileName(value) {
        var s = String(value || 'worldmap').trim().toLowerCase();
        s = s.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
        return s || 'worldmap';
    }

    function normalizeComparableText(value) {
        return String(value || '')
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, ' ')
            .trim();
    }

    function formatMapCardTitle(title, metric) {
        var cleanTitle = String(title || 'World map').trim() || 'World map';
        var cleanMetric = String(metric || '').trim();
        if (!cleanMetric) return cleanTitle;
        var normalizedTitle = normalizeComparableText(cleanTitle);
        var normalizedMetric = normalizeComparableText(cleanMetric);
        if (normalizedMetric && (normalizedTitle === normalizedMetric || normalizedTitle.indexOf(normalizedMetric) !== -1)) {
            return cleanTitle;
        }
        return cleanTitle + ' (' + cleanMetric + ')';
    }

    function downloadBlobFile(filename, blob) {
        try {
            if (!blob) return false;
            var nav = window.navigator;
            if (nav && typeof nav.msSaveOrOpenBlob === 'function') {
                nav.msSaveOrOpenBlob(blob, filename);
                return true;
            }
            var url = URL.createObjectURL(blob);
            var a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            setTimeout(function () { URL.revokeObjectURL(url); }, 3000);
            return true;
        } catch (e) {
            return false;
        }
    }

    function downloadTextFile(filename, content, mimeType) {
        try {
            var blob = new Blob([String(content || '')], { type: mimeType || 'text/plain;charset=utf-8' });
            return downloadBlobFile(filename, blob);
        } catch (e) {
            return false;
        }
    }

    function getMapSvgString(mapEl) {
        if (!mapEl) return null;
        var svg = mapEl.querySelector('.leaflet-overlay-pane svg');
        if (!svg) return null;
        var clone = svg.cloneNode(true);
        var box = mapEl.getBoundingClientRect();
        var width = Math.max(1, Math.round(box.width || 900));
        var height = Math.max(1, Math.round(box.height || 450));
        clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
        clone.setAttribute('xmlns:xlink', 'http://www.w3.org/1999/xlink');
        clone.setAttribute('width', String(width));
        clone.setAttribute('height', String(height));
        if (!clone.getAttribute('viewBox')) clone.setAttribute('viewBox', '0 0 ' + width + ' ' + height);
        var xml = new XMLSerializer().serializeToString(clone);
        if (!/^<svg[^>]+xmlns=/.test(xml)) {
            xml = xml.replace('<svg', '<svg xmlns="http://www.w3.org/2000/svg"');
        }
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml;
    }

    function saveMapAsSvg(mapEl, fileBase) {
        var svgText = getMapSvgString(mapEl);
        if (!svgText) return false;
        return downloadTextFile(fileBase + '.svg', svgText, 'image/svg+xml;charset=utf-8');
    }

    function saveMapAsPng(mapEl, fileBase) {
        var svgText = getMapSvgString(mapEl);
        if (!svgText) return false;
        try {
            var blob = new Blob([svgText], { type: 'image/svg+xml;charset=utf-8' });
            var url = URL.createObjectURL(blob);
            var image = new Image();
            image.onload = function () {
                try {
                    var canvas = document.createElement('canvas');
                    canvas.width = image.width || 1000;
                    canvas.height = image.height || 500;
                    var ctx = canvas.getContext('2d');
                    if (!ctx) {
                        URL.revokeObjectURL(url);
                        return;
                    }
                    ctx.fillStyle = '#ffffff';
                    ctx.fillRect(0, 0, canvas.width, canvas.height);
                    ctx.drawImage(image, 0, 0);
                    canvas.toBlob(function (pngBlob) {
                        if (!pngBlob) {
                            URL.revokeObjectURL(url);
                            return;
                        }
                        var pngUrl = URL.createObjectURL(pngBlob);
                        var a = document.createElement('a');
                        a.href = pngUrl;
                        a.download = fileBase + '.png';
                        document.body.appendChild(a);
                        a.click();
                        a.remove();
                        setTimeout(function () { URL.revokeObjectURL(pngUrl); }, 3000);
                        URL.revokeObjectURL(url);
                    }, 'image/png');
                } catch (e) {
                    URL.revokeObjectURL(url);
                }
            };
            image.onerror = function () { URL.revokeObjectURL(url); };
            image.src = url;
            return true;
        } catch (e) {
            return false;
        }
    }

    async function saveMapAsExcel(normalized, fileBase) {
        if (!normalized || !normalized.countries || !normalized.countries.length) return false;
        var metric = String(normalized.metric || 'value').trim() || 'value';
        var filename = (fileBase || 'worldmap') + '.xlsx';
        var rows = [];
        rows.push(['ISO3', 'Country', 'Year', metric]);
        for (var i = 0; i < normalized.countries.length; i++) {
            var r = normalized.countries[i];
            if (!r) continue;
            rows.push([String(r.iso3 || '').trim(), String(r.label || '').trim(), (r.year != null ? String(r.year) : ''), String(r.value)]);
        }

        var exportFetch = (window.getFetch && window.getFetch()) || fetch;
        try {
            var res = await exportFetch('/api/ai/v2/table/export', {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({ rows: rows })
            });
            if (!res.ok) throw (window.httpErrorSync && window.httpErrorSync(res, 'Excel export failed: ' + res.status)) || new Error('Excel export failed: ' + res.status);
            var blob = await res.blob();
            var url = URL.createObjectURL(blob);
            var a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            setTimeout(function () { URL.revokeObjectURL(url); }, 3000);
            return true;
        } catch (e) {
            // Fallback: at least export CSV locally if the server export isn't available.
            try {
                var csv = rows.map(function (r) {
                    return r.map(function (cell) {
                        var s = String(cell == null ? '' : cell);
                        if (/[",\n]/.test(s)) s = '"' + s.replace(/"/g, '""') + '"';
                        return s;
                    }).join(',');
                }).join('\n');
                return downloadTextFile((fileBase || 'worldmap') + '.csv', csv, 'text/csv;charset=utf-8');
            } catch (_) {
                return false;
            }
        }
    }

    function createExportDropdown(actionsEl, items) {
        if (!actionsEl) return null;
        actionsEl.style.position = 'relative';
        // Ensure dropdown stacks above Leaflet panes/tiles.
        actionsEl.style.zIndex = '5000';

        var btn = document.createElement('button');
        btn.type = 'button';
        btn.textContent = 'Export ▾';
        btn.style.fontSize = '0.75rem';
        btn.style.padding = '0.22rem 0.55rem';
        btn.style.border = '1px solid #cbd5e1';
        btn.style.borderRadius = '0.4rem';
        btn.style.background = '#fff';
        btn.style.cursor = 'pointer';
        btn.setAttribute('aria-haspopup', 'menu');
        btn.setAttribute('aria-expanded', 'false');
        actionsEl.appendChild(btn);

        var menu = document.createElement('div');
        menu.style.position = 'absolute';
        menu.style.right = '0';
        menu.style.top = 'calc(100% + 6px)';
        menu.style.minWidth = '160px';
        menu.style.zIndex = '6000';
        menu.style.border = '1px solid #e5e7eb';
        menu.style.borderRadius = '0.6rem';
        menu.style.background = '#fff';
        menu.style.boxShadow = '0 10px 25px rgba(0,0,0,0.08)';
        menu.style.padding = '0.25rem';
        menu.style.display = 'none';
        menu.setAttribute('role', 'menu');
        actionsEl.appendChild(menu);

        function closeMenu() {
            menu.style.display = 'none';
            btn.setAttribute('aria-expanded', 'false');
        }
        function openMenu() {
            menu.style.display = 'block';
            btn.setAttribute('aria-expanded', 'true');
        }
        function toggleMenu() {
            if (menu.style.display === 'none') openMenu(); else closeMenu();
        }

        btn.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            toggleMenu();
        });

        // Close on outside interaction. Use CAPTURE so it still fires even if
        // other handlers stopPropagation() on the bubble.
        function onOutsideEvent(e) {
            try {
                var t = e && e.target;
                if (t && actionsEl.contains(t)) return;
            } catch (_) { /* ignore */ }
            closeMenu();
        }
        function onKeydown(e) {
            var key = e && (e.key || e.code);
            if (key === 'Escape' || key === 'Esc') closeMenu();
        }
        try {
            document.addEventListener('pointerdown', onOutsideEvent, true);
            document.addEventListener('click', onOutsideEvent, true);
            document.addEventListener('keydown', onKeydown, true);
        } catch (e) {
            // Fallback for older browsers without pointer events / capture support.
            document.addEventListener('mousedown', onOutsideEvent);
            document.addEventListener('click', onOutsideEvent);
            document.addEventListener('keydown', onKeydown);
        }

        (items || []).forEach(function (it) {
            var itemBtn = document.createElement('button');
            itemBtn.type = 'button';
            itemBtn.textContent = String(it && it.label ? it.label : '').trim();
            itemBtn.style.display = 'block';
            itemBtn.style.width = '100%';
            itemBtn.style.textAlign = 'left';
            itemBtn.style.fontSize = '0.8rem';
            itemBtn.style.padding = '0.42rem 0.55rem';
            itemBtn.style.border = '0';
            itemBtn.style.borderRadius = '0.45rem';
            itemBtn.style.background = 'transparent';
            itemBtn.style.cursor = 'pointer';
            itemBtn.setAttribute('role', 'menuitem');
            itemBtn.addEventListener('mouseenter', function () { itemBtn.style.background = '#f1f5f9'; });
            itemBtn.addEventListener('mouseleave', function () { itemBtn.style.background = 'transparent'; });
            itemBtn.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();
                closeMenu();
                try { if (it && typeof it.onClick === 'function') it.onClick(); } catch (_) { /* ignore */ }
            });
            if (itemBtn.textContent) menu.appendChild(itemBtn);
        });

        return { button: btn, menu: menu, close: closeMenu };
    }

    function findLatestBotWrapper() {
        var wrappers = document.querySelectorAll('#chatMessages .chat-message-wrapper');
        if (!wrappers || !wrappers.length) return null;
        for (var i = wrappers.length - 1; i >= 0; i--) {
            var w = wrappers[i];
            if (w && w.querySelector && w.querySelector('.chat-message.bot')) return w;
        }
        return wrappers[wrappers.length - 1] || null;
    }

    function resolveTargetWrapper(wrapperElement) {
        if (wrapperElement && wrapperElement.parentElement) return wrapperElement;
        return findLatestBotWrapper();
    }

    function resolveTargetMessageContent(wrapperElement) {
        var wrapper = resolveTargetWrapper(wrapperElement);
        if (!wrapper || !wrapper.querySelector) return null;
        return wrapper.querySelector('.chat-message.bot .chat-message-content');
    }

    function addCompactZoomControl(L, map) {
        if (!L || !map) return;
        var ZoomControl = L.Control.extend({
            options: { position: 'topleft' },
            onAdd: function () {
                var container = L.DomUtil.create('div', 'leaflet-bar leaflet-control chat-immersive-zoom-control');
                // Inline styles so this looks good without extra CSS.
                container.style.background = '#ffffff';
                container.style.border = '1px solid #e2e8f0';
                container.style.borderRadius = '0.75rem';
                container.style.overflow = 'hidden';
                container.style.boxShadow = '0 8px 18px rgba(15, 23, 42, 0.14)';

                var addButton = function (label, title, onClick) {
                    var btn = L.DomUtil.create('a', '', container);
                    btn.href = '#';
                    btn.textContent = label;
                    btn.title = title;
                    btn.setAttribute('role', 'button');
                    btn.setAttribute('aria-label', title);
                    btn.style.textDecoration = 'none';
                    btn.style.width = '38px';
                    btn.style.height = '38px';
                    btn.style.display = 'flex';
                    btn.style.alignItems = 'center';
                    btn.style.justifyContent = 'center';
                    btn.style.fontSize = '20px';
                    btn.style.fontWeight = '700';
                    btn.style.lineHeight = '1';
                    btn.style.color = '#0f172a';
                    btn.style.background = '#ffffff';
                    btn.style.userSelect = 'none';
                    btn.style.webkitUserSelect = 'none';
                    L.DomEvent.on(btn, 'click', L.DomEvent.stopPropagation)
                        .on(btn, 'click', L.DomEvent.preventDefault)
                        .on(btn, 'click', onClick);

                    // Hover + focus styles (accessible, keyboard-friendly)
                    var setHover = function (on) {
                        btn.style.background = on ? '#f1f5f9' : '#ffffff';
                    };
                    btn.addEventListener('mouseenter', function () { setHover(true); });
                    btn.addEventListener('mouseleave', function () { setHover(false); });
                    btn.addEventListener('focus', function () {
                        btn.style.outline = '2px solid #2563eb';
                        btn.style.outlineOffset = '-2px';
                        setHover(true);
                    });
                    btn.addEventListener('blur', function () {
                        btn.style.outline = 'none';
                        setHover(false);
                    });
                    return btn;
                };
                var btnIn = addButton('+', 'Zoom in', function () { map.zoomIn(); });
                btnIn.style.borderBottom = '1px solid #e2e8f0';
                addButton('−', 'Zoom out', function () { map.zoomOut(); });
                return container;
            }
        });
        map.addControl(new ZoomControl());
    }

    function renderMapCard(payload, wrapperElement, messageElement) {
        var normalized = normalizeMapPayload(payload);
        var targetWrapper = resolveTargetWrapper(wrapperElement);
        if (!normalized || (!targetWrapper && !messageElement)) return false;
        if (targetWrapper && !targetWrapper.parentElement && !messageElement) return false;
        var targetContent = null;
        if (messageElement && messageElement.querySelector) {
            targetContent = messageElement.querySelector('.chat-message-content');
        }
        if (!targetContent) {
            targetContent = resolveTargetMessageContent(targetWrapper);
        }
        var MAP_LOG = function () {
            try {
                if (window.CHATBOT_DEBUG || window.ngodbChatImmersiveMapDebug) {
                    console.log.apply(console, ['[Immersive map]'].concat(Array.prototype.slice.call(arguments)));
                }
            } catch (e) { /* ignore */ }
        };

        // If a map card already exists (e.g. restored DOM on reload), only treat it as "rendered"
        // when Leaflet has actually initialized inside it. Otherwise remove and re-render.
        try {
            var existingCard = null;
            if (targetContent) {
                existingCard = targetContent.querySelector('.chat-immersive-map-card');
            } else if (targetWrapper && targetWrapper.nextElementSibling && targetWrapper.nextElementSibling.classList.contains('chat-immersive-map-card')) {
                existingCard = targetWrapper.nextElementSibling;
            }
            if (existingCard) {
                var hasLeaflet = !!existingCard.querySelector('.leaflet-container, .leaflet-pane, .leaflet-map-pane');
                if (hasLeaflet) {
                    MAP_LOG('existing map card present; leaflet already initialized');
                    return true;
                }
                MAP_LOG('existing map card present but empty; re-rendering');
                try { existingCard.remove(); } catch (_) { /* ignore */ }
            }
        } catch (e) { /* ignore */ }

        var card = document.createElement('div');
        card.className = 'chat-immersive-map-card';
        card.style.position = 'relative';
        card.style.border = '1px solid #e5e7eb';
        card.style.borderRadius = '0.75rem';
        card.style.padding = '0.75rem';
        card.style.marginTop = '0.75rem';
        card.style.background = '#fff';

        var title = document.createElement('div');
        title.style.position = 'relative';
        title.style.zIndex = '10';
        title.style.display = 'flex';
        title.style.alignItems = 'center';
        title.style.justifyContent = 'space-between';
        title.style.gap = '0.5rem';
        title.style.marginBottom = '0.5rem';

        var titleText = document.createElement('div');
        titleText.style.fontWeight = '600';
        titleText.style.fontSize = '0.9rem';
        titleText.textContent = formatMapCardTitle(normalized.title, normalized.metric);
        title.appendChild(titleText);

        var mapSwitch = createViewSwitch('Map', 'Table');
        title.appendChild(mapSwitch.switchContainer);

        var actions = document.createElement('div');
        actions.style.display = 'inline-flex';
        actions.style.gap = '0.35rem';

        title.appendChild(actions);
        card.appendChild(title);

        mapSwitch.viewVisual.style.marginTop = '0';
        var mapEl = document.createElement('div');
        mapEl.style.position = 'relative';
        mapEl.style.zIndex = '1';
        mapEl.style.height = '320px';
        mapEl.style.width = '100%';
        mapEl.style.borderRadius = '0.5rem';
        mapEl.style.overflow = 'hidden';
        mapEl.style.background = '#f8fafc';
        mapSwitch.viewVisual.appendChild(mapEl);

        var mapTableEl = buildDataTableFromPayload(normalized);
        if (mapTableEl) mapSwitch.viewTable.appendChild(mapTableEl);
        mapSwitch.viewTable.style.marginTop = '0.5rem';

        card.appendChild(mapSwitch.viewVisual);
        card.appendChild(mapSwitch.viewTable);

        var fileBase = slugifyFileName((normalized.title || 'worldmap') + '-' + (normalized.metric || 'value'));
        createExportDropdown(actions, [
            { label: 'Save PNG', onClick: function () { saveMapAsPng(mapEl, fileBase); } },
            { label: 'Save SVG', onClick: function () { saveMapAsSvg(mapEl, fileBase); } },
            { label: 'Save Excel', onClick: function () { saveMapAsExcel(normalized, fileBase); } }
        ]);

        if (targetContent) {
            targetContent.appendChild(card);
        } else if (targetWrapper) {
            targetWrapper.insertAdjacentElement('afterend', card);
        } else {
            return false;
        }

        var lookup = {};
        normalized.countries.forEach(function (row) {
            lookup[row.iso3] = row;
        });
        var values = normalized.countries.map(function (r) { return Number(r.value); }).filter(function (v) { return isFinite(v); });
        var min = values.length ? Math.min.apply(null, values) : 0;
        var max = values.length ? Math.max.apply(null, values) : 0;
        var yearishMap = isLikelyYearValues(values);
        var categoryInfo = detectCategoryField(normalized, values, min, max);
        var colorByCategory = !!categoryInfo;
        var categoryField = categoryInfo ? categoryInfo.field : null;
        var categoryValues = categoryInfo ? categoryInfo.values : [];
        if (colorByCategory) {
            colorForCategory._cache = {};
            colorForCategory._ordered = {};
            categoryValues.forEach(function (val) {
                colorForCategory(categoryField, val);
            });
        }
        MAP_LOG('map colouring decision:', {
            valuesCount: values.length,
            min: min,
            max: max,
            allSameValue: min === max,
            colorByCategory: colorByCategory,
            categoryField: categoryField,
            categoryValues: categoryValues
        });
        colorForCategory._log = MAP_LOG;
        buildWorldmapCategoryLegendSpec._log = MAP_LOG;

        Promise.all([ensureLeaflet(), fetchWorldGeoJson()])
            .then(function (results) {
                var L = results[0];
                var geo = results[1];
                // Leaflet needs a real layout box. If the message/card is still hidden/collapsed
                // (width/height == 0), delay init instead of throwing and leaving dangling handlers.
                function _containerReady() {
                    try {
                        if (!mapEl || !mapEl.isConnected) return false;
                        var box = mapEl.getBoundingClientRect();
                        return !!(box && box.width >= 40 && box.height >= 40);
                    } catch (e) {
                        return false;
                    }
                }

                // If we already created a map in this container (e.g. retry), remove it first.
                try {
                    if (mapEl.__ngodbLeafletMap && typeof mapEl.__ngodbLeafletMap.remove === 'function') {
                        mapEl.__ngodbLeafletMap.remove();
                    }
                } catch (e) { /* ignore */ }
                mapEl.__ngodbLeafletMap = null;

                var attempts = 0;
                function initWhenReady() {
                    attempts++;
                    if (!_containerReady()) {
                        if (attempts < 60) {
                            if (attempts % 10 === 0) MAP_LOG('waiting for map container layout… attempt', attempts);
                            setTimeout(initWhenReady, Math.min(800, 60 + attempts * 40));
                            return;
                        }
                        throw new Error('map_container_not_ready');
                    }

                    var map = L.map(mapEl, {
                        zoomControl: false,
                        minZoom: 1,
                        maxZoom: 6,
                        worldCopyJump: true
                    }).setView([20, 0], 1.4);
                    mapEl.__ngodbLeafletMap = map;
                    addCompactZoomControl(L, map);
                    // Ensure Leaflet recalculates size after insertion/layout.
                    try { setTimeout(function () { try { map.invalidateSize(true); } catch (_) { /* ignore */ } }, 0); } catch (_) { /* ignore */ }

                    var geoLayer = L.geoJSON(geo, {
                        style: function (feature) {
                            var iso3 = featureIso3(feature);
                            var row = iso3 ? lookup[iso3] : null;
                            var fill = row
                                ? (colorByCategory && categoryField && row[categoryField] ? colorForCategory(categoryField, row[categoryField]) : colorFor(Number(row.value), min, max))
                                : '#e5e7eb';
                            return {
                                color: '#ffffff',
                                weight: 0.6,
                                fillOpacity: row ? 0.85 : 0.35,
                                fillColor: fill
                            };
                        },
                        onEachFeature: function (feature, layer) {
                            var iso3 = featureIso3(feature);
                            var row = iso3 ? lookup[iso3] : null;
                            if (!row) return;
                            var rowYear = (row.year != null && isFinite(row.year)) ? Math.round(Number(row.year)) : null;
                            var valueNum = Number(row.value);
                            var valueYear = isFinite(valueNum) ? Math.round(valueNum) : null;
                            // Year-like maps: show the year once (no thousands separators), avoid "(2026): 2,026"
                            var showAsYear = !!(yearishMap && rowYear != null && (valueYear == null || rowYear === valueYear));
                            var yr = (rowYear != null && isFinite(rowYear)) ? String(rowYear) : '';
                            var metricLabel = escapeHtml(normalized.metric);
                            var countryLabel = escapeHtml(row.label);
                            var valueLabel = showAsYear ? (yr || (isFinite(valueYear) ? String(valueYear) : '')) : formatNumber(row.value);
                            var label = '<strong>' + countryLabel + '</strong><br>' + metricLabel + (showAsYear ? '' : (yr ? ' (' + escapeHtml(yr) + ')' : '')) + ': ' + escapeHtml(valueLabel);
                            layer.bindTooltip(label, { sticky: true, direction: 'top', opacity: 0.95 });
                            layer.on('mouseover', function () {
                                try {
                                    layer.setStyle({ weight: 1.2, color: '#0f172a', fillOpacity: 0.95 });
                                } catch (e) { /* ignore */ }
                                layer.openTooltip();
                            });
                            layer.on('mouseout', function () {
                                try {
                                    layer.setStyle({ weight: 0.6, color: '#ffffff', fillOpacity: 0.85 });
                                } catch (e) { /* ignore */ }
                                layer.closeTooltip();
                            });
                            layer.bindPopup('<strong>' + countryLabel + '</strong><br>' + metricLabel + (yr ? ' (' + escapeHtml(yr) + ')' : '') + ': ' + escapeHtml(valueLabel));
                        }
                    });
                    geoLayer.addTo(map);

                    // Ensure tooltips don't get "stuck" if the pointer moves quickly between layers.
                    // Clear all tooltips/popups when leaving the map area.
                    try {
                        mapEl.addEventListener('mouseleave', function () {
                            try { map.closePopup(); } catch (e) { /* ignore */ }
                            try {
                                geoLayer.eachLayer(function (lyr) {
                                    try { if (lyr && typeof lyr.closeTooltip === 'function') lyr.closeTooltip(); } catch (_) { /* ignore */ }
                                });
                            } catch (e) { /* ignore */ }
                        });
                    } catch (e) { /* ignore */ }

                    // Legend: when colouring by category show category legend; else show value scale when meaningful.
                    var legendSpec = colorByCategory
                        ? buildWorldmapCategoryLegendSpec(normalized, categoryField, categoryValues)
                        : buildWorldmapLegendSpec(normalized, values, min, max, geo, lookup);
                    (function logColouringSample() {
                        try {
                            var mode = colorByCategory ? ('by ' + categoryField) : ('by value (min=' + min + ', max=' + max + ')');
                            MAP_LOG('map colouring mode:', mode, '| countries with data:', normalized.countries.length);
                            var sample = normalized.countries.slice(0, 8);
                            sample.forEach(function (r) {
                                var fill = r
                                    ? (colorByCategory && categoryField && r[categoryField] ? colorForCategory(categoryField, r[categoryField]) : colorFor(Number(r.value), min, max))
                                    : '#e5e7eb';
                                MAP_LOG('  ', r.iso3, colorByCategory ? (categoryField + '=' + (r[categoryField] || '-')) : ('value=' + r.value), '-> fill', fill);
                            });
                        } catch (e) { /* ignore */ }
                    })();
                    if (legendSpec) {
                        var activeFilter = null;
                        function applyFilterToAll() {
                            try {
                                try {
                                    geoLayer.eachLayer(function (lyr) {
                                        try { if (lyr && typeof lyr.closeTooltip === 'function') lyr.closeTooltip(); } catch (_) { /* ignore */ }
                                    });
                                } catch (_) { /* ignore */ }
                                geoLayer.eachLayer(function (layer) {
                                    try {
                                        var feat = layer && layer.feature ? layer.feature : null;
                                        var iso3 = feat ? featureIso3(feat) : '';
                                        var row = iso3 ? lookup[iso3] : null;
                                        applyWorldmapLegendFilter(L, layer, feat, row, lookup, activeFilter, normalized, min, max, colorByCategory, categoryField);
                                    } catch (e) { /* ignore */ }
                                });
                            } catch (e) { /* ignore */ }
                        }
                        addLeafletLegendControl(L, map, legendSpec, {
                            onSelect: function (filter) {
                                activeFilter = filter || null;
                                MAP_LOG('legend filter applied:', activeFilter ? (activeFilter.kind + (activeFilter.categoryField ? ' ' + activeFilter.categoryField + '=' + activeFilter.categoryValue : '') + (activeFilter.region ? ' region=' + activeFilter.region : '') + (activeFilter.value != null ? ' value=' + activeFilter.value : '')) : 'none (show all)');
                                applyFilterToAll();
                            }
                        });
                    }
                }

                initWhenReady();
            })
            .catch(function (err) {
                MAP_LOG('map render failed', err && (err.message || err));
                // If Leaflet partially initialized, remove it to avoid dangling handlers and offsetWidth null crashes.
                try {
                    if (mapEl && mapEl.__ngodbLeafletMap && typeof mapEl.__ngodbLeafletMap.remove === 'function') {
                        mapEl.__ngodbLeafletMap.remove();
                    }
                } catch (e) { /* ignore */ }
                try { if (mapEl) mapEl.__ngodbLeafletMap = null; } catch (e) { /* ignore */ }
                mapEl.innerHTML = '';
                var fallback = document.createElement('div');
                fallback.style.fontSize = '0.82rem';
                fallback.style.color = '#334155';
                fallback.textContent = 'Map preview unavailable. Data points: ' + normalized.countries.length;
                mapEl.appendChild(fallback);
            });
        return true;
    }

    async function saveChartAsExcel(normalized, fileBase) {
        if (!normalized || !normalized.series || !normalized.series.length) return false;
        var metric = String(normalized.metric || 'value').trim() || 'value';
        var filename = (fileBase || 'trend') + '.xlsx';
        var rows = [];
        rows.push(['Year', metric]);
        for (var i = 0; i < normalized.series.length; i++) {
            var p = normalized.series[i];
            if (!p) continue;
            rows.push([String(p.x), String(p.y)]);
        }

        var exportFetch = (window.getFetch && window.getFetch()) || fetch;
        try {
            var res = await exportFetch('/api/ai/v2/table/export', {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({ rows: rows })
            });
            if (!res.ok) throw (window.httpErrorSync && window.httpErrorSync(res, 'Excel export failed: ' + res.status)) || new Error('Excel export failed: ' + res.status);
            var blob = await res.blob();
            var url = URL.createObjectURL(blob);
            var a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            setTimeout(function () { URL.revokeObjectURL(url); }, 3000);
            return true;
        } catch (e) {
            return false;
        }
    }

    function buildDataTableExportRows(columns, rows) {
        var safeColumns = Array.isArray(columns) ? columns : [];
        var safeRows = Array.isArray(rows) ? rows : [];
        if (!safeColumns.length || !safeRows.length) return [];
        var exportRows = [];
        exportRows.push(safeColumns.map(function (c) {
            return String((c && (c.label || c.key)) || '').trim();
        }));
        safeRows.forEach(function (row) {
            exportRows.push(safeColumns.map(function (c) {
                var key = c && c.key ? c.key : '';
                var value = row && key ? row[key] : '';
                return value == null ? '' : String(value);
            }));
        });
        return exportRows;
    }

    async function saveDataTableAsExcel(columns, rows, fileBase) {
        var exportRows = buildDataTableExportRows(columns, rows);
        if (!exportRows.length) return false;
        var filename = (fileBase || 'data-table') + '.xlsx';
        var exportFetch = (window.getFetch && window.getFetch()) || fetch;
        try {
            var res = await exportFetch('/api/ai/v2/table/export', {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({ rows: exportRows })
            });
            if (!res.ok) throw (window.httpErrorSync && window.httpErrorSync(res, 'Excel export failed: ' + res.status)) || new Error('Excel export failed: ' + res.status);
            var blob = await res.blob();
            var url = URL.createObjectURL(blob);
            var a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            setTimeout(function () { URL.revokeObjectURL(url); }, 3000);
            return true;
        } catch (e) {
            try {
                var csv = exportRows.map(function (r) {
                    return r.map(function (cell) {
                        var s = String(cell == null ? '' : cell);
                        if (/[",\n]/.test(s)) s = '"' + s.replace(/"/g, '""') + '"';
                        return s;
                    }).join(',');
                }).join('\n');
                return downloadTextFile((fileBase || 'data-table') + '.csv', csv, 'text/csv;charset=utf-8');
            } catch (_) {
                return false;
            }
        }
    }

    async function saveApexChartAsImage(chart, fileBase, kind, chartSwitch) {
        var restoreTableView = false;
        try {
            function getChartSvgText() {
                var host = null;
                try {
                    host = (chart && chart.el) || (chartSwitch && chartSwitch.viewVisual) || null;
                } catch (e) { host = (chartSwitch && chartSwitch.viewVisual) || null; }
                if (!host || !host.querySelector) return null;
                var svgEl = host.querySelector('svg');
                if (!svgEl) return null;
                var clone = svgEl.cloneNode(true);
                var box = host.getBoundingClientRect ? host.getBoundingClientRect() : null;
                var width = Math.max(1, Math.round((box && box.width) || Number(clone.getAttribute('width')) || 900));
                var height = Math.max(1, Math.round((box && box.height) || Number(clone.getAttribute('height')) || 400));
                clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
                clone.setAttribute('xmlns:xlink', 'http://www.w3.org/1999/xlink');
                clone.setAttribute('width', String(width));
                clone.setAttribute('height', String(height));
                if (!clone.getAttribute('viewBox')) clone.setAttribute('viewBox', '0 0 ' + width + ' ' + height);
                var xml = new XMLSerializer().serializeToString(clone);
                if (!/^<svg[^>]+xmlns=/.test(xml)) {
                    xml = xml.replace('<svg', '<svg xmlns="http://www.w3.org/2000/svg"');
                }
                return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml;
            }

            async function renderSvgToPngBlob(svgText) {
                return await new Promise(function (resolve) {
                    try {
                        var svgBlob = new Blob([svgText], { type: 'image/svg+xml;charset=utf-8' });
                        var svgUrl = URL.createObjectURL(svgBlob);
                        var img = new Image();
                        img.onload = function () {
                            try {
                                var canvas = document.createElement('canvas');
                                canvas.width = img.width || 1000;
                                canvas.height = img.height || 500;
                                var ctx = canvas.getContext('2d');
                                if (!ctx) {
                                    URL.revokeObjectURL(svgUrl);
                                    resolve(null);
                                    return;
                                }
                                ctx.fillStyle = '#ffffff';
                                ctx.fillRect(0, 0, canvas.width, canvas.height);
                                ctx.drawImage(img, 0, 0);
                                canvas.toBlob(function (blob) {
                                    URL.revokeObjectURL(svgUrl);
                                    resolve(blob || null);
                                }, 'image/png');
                            } catch (e) {
                                URL.revokeObjectURL(svgUrl);
                                resolve(null);
                            }
                        };
                        img.onerror = function () {
                            URL.revokeObjectURL(svgUrl);
                            resolve(null);
                        };
                        img.src = svgUrl;
                    } catch (e) {
                        resolve(null);
                    }
                });
            }

            // First try direct DOM extraction (works even when table tab is active).
            var domSvgText = null;
            try { domSvgText = getChartSvgText(); } catch (e) { domSvgText = null; }
            if (kind === 'svg' && domSvgText) {
                if (downloadTextFile((fileBase || 'chart') + '.svg', domSvgText, 'image/svg+xml;charset=utf-8')) return true;
            }
            if (kind === 'png' && domSvgText) {
                var pngFromDom = await renderSvgToPngBlob(domSvgText);
                if (pngFromDom && downloadBlobFile((fileBase || 'chart') + '.png', pngFromDom)) return true;
            }

            if (
                chartSwitch &&
                chartSwitch.viewVisual &&
                chartSwitch.viewTable &&
                chartSwitch.viewVisual.style &&
                chartSwitch.viewVisual.style.display === 'none'
            ) {
                restoreTableView = true;
                chartSwitch.viewVisual.style.display = '';
                chartSwitch.viewTable.style.display = 'none';
                // Let layout settle before taking image snapshot.
                await new Promise(function (resolve) {
                    requestAnimationFrame(function () {
                        requestAnimationFrame(resolve);
                    });
                });
                try { window.dispatchEvent(new Event('resize')); } catch (e) { /* ignore */ }
                await new Promise(function (resolve) { setTimeout(resolve, 40); });
            }
            // Retry DOM extraction after forcing chart tab visible.
            try { domSvgText = getChartSvgText(); } catch (e) { domSvgText = null; }
            if (kind === 'svg' && domSvgText) {
                if (downloadTextFile((fileBase || 'chart') + '.svg', domSvgText, 'image/svg+xml;charset=utf-8')) return true;
            }
            if (kind === 'png' && domSvgText) {
                var pngBlob = await renderSvgToPngBlob(domSvgText);
                if (pngBlob && downloadBlobFile((fileBase || 'chart') + '.png', pngBlob)) return true;
            }

            if (!chart || typeof chart.dataURI !== 'function') return false;
            var out = await chart.dataURI();
            var uri = null;
            if (kind === 'svg') uri = out && (out.svgURI || out.svgUri || out.svg);
            if (kind === 'png') uri = out && (out.imgURI || out.imgUri || out.pngURI || out.pngUri || out.img);
            if (!uri) return false;
            var a = document.createElement('a');
            a.href = uri;
            a.download = (fileBase || 'chart') + (kind === 'svg' ? '.svg' : '.png');
            document.body.appendChild(a);
            a.click();
            a.remove();
            return true;
        } catch (e) {
            return false;
        } finally {
            if (restoreTableView && chartSwitch && chartSwitch.viewVisual && chartSwitch.viewTable) {
                chartSwitch.viewVisual.style.display = 'none';
                chartSwitch.viewTable.style.display = '';
            }
        }
    }

    function renderChartCard(payload, wrapperElement, messageElement) {
        var normalized = normalizeChartPayload(payload);
        var targetWrapper = resolveTargetWrapper(wrapperElement);
        if (!normalized || (!targetWrapper && !messageElement)) return false;
        if (targetWrapper && !targetWrapper.parentElement && !messageElement) return false;

        var targetContent = null;
        if (messageElement && messageElement.querySelector) {
            targetContent = messageElement.querySelector('.chat-message-content');
        }
        if (!targetContent) {
            targetContent = resolveTargetMessageContent(targetWrapper);
        }
        if (targetContent && targetContent.querySelector('.chat-immersive-chart-card')) return true;
        if (!targetContent && targetWrapper && targetWrapper.nextElementSibling && targetWrapper.nextElementSibling.classList.contains('chat-immersive-chart-card')) return true;

        var card = document.createElement('div');
        card.className = 'chat-immersive-chart-card';
        card.style.position = 'relative';
        card.style.border = '1px solid #e2e8f0';
        card.style.borderRadius = '0.875rem';
        card.style.padding = '1rem';
        card.style.marginTop = '0.75rem';
        card.style.background = '#ffffff';
        card.style.boxShadow = '0 1px 3px rgba(15, 23, 42, 0.06)';

        var title = document.createElement('div');
        title.style.position = 'relative';
        title.style.zIndex = '10';
        title.style.display = 'flex';
        title.style.alignItems = 'center';
        title.style.justifyContent = 'space-between';
        title.style.gap = '0.5rem';
        title.style.marginBottom = '0.5rem';

        var titleText = document.createElement('div');
        titleText.style.fontWeight = '600';
        titleText.style.fontSize = '0.9375rem';
        titleText.style.color = '#0f172a';
        titleText.style.letterSpacing = '-0.01em';
        titleText.textContent = normalized.title || (normalized.metric + ' over time');
        title.appendChild(titleText);

        var chartSwitch = createViewSwitch('Chart', 'Table');
        title.appendChild(chartSwitch.switchContainer);

        var actions = document.createElement('div');
        actions.style.display = 'inline-flex';
        actions.style.alignItems = 'center';
        actions.style.gap = '0.5rem';
        title.appendChild(actions);

        var dataLabelsToggle = document.createElement('label');
        dataLabelsToggle.style.display = 'inline-flex';
        dataLabelsToggle.style.alignItems = 'center';
        dataLabelsToggle.style.gap = '0.35rem';
        dataLabelsToggle.style.fontSize = '0.8rem';
        dataLabelsToggle.style.color = '#64748b';
        dataLabelsToggle.style.cursor = 'pointer';
        dataLabelsToggle.style.userSelect = 'none';
        var dataLabelsCheckbox = document.createElement('input');
        dataLabelsCheckbox.type = 'checkbox';
        dataLabelsCheckbox.checked = false;
        dataLabelsCheckbox.setAttribute('aria-label', 'Show data labels on chart');
        dataLabelsToggle.appendChild(dataLabelsCheckbox);
        dataLabelsToggle.appendChild(document.createTextNode('Show data labels'));
        var dataLabelsHint = document.createElement('span');
        dataLabelsHint.textContent = '— drag labels to reposition';
        dataLabelsHint.style.color = '#94a3b8';
        dataLabelsHint.style.fontSize = '0.75rem';
        dataLabelsHint.style.display = 'none';
        dataLabelsToggle.appendChild(dataLabelsHint);
        function dataLabelsFormatter(val, opts) {
            var text = formatNumber(val);
            if (text === '' || (val == null && opts == null)) return '';
            return text;
        }
        function updateDataLabelsHint() {
            dataLabelsHint.style.display = dataLabelsCheckbox.checked ? 'inline' : 'none';
        }
        dataLabelsCheckbox.addEventListener('change', function () {
            updateDataLabelsHint();
            if (chartRef.current) {
                chartRef.current.updateOptions({
                    dataLabels: {
                        enabled: dataLabelsCheckbox.checked,
                        offsetY: -4,
                        formatter: dataLabelsFormatter
                    }
                }, false, false);
                scheduleLabelDragInstall();
            }
        });

        card.appendChild(title);

        function normalizeStatusKey(value) {
            var s = String(value == null ? '' : value).trim().toLowerCase();
            if (!s) return null;
            if (s === 'draft') return 'saved';
            if (s === 'final') return 'submitted';
            return s;
        }

        function statusLabel(key) {
            if (key === 'saved') return 'Saved';
            if (key === 'submitted') return 'Submitted';
            if (key === 'approved') return 'Approved';
            return key ? (key.charAt(0).toUpperCase() + key.slice(1)) : '';
        }

        function colorForStatus(key) {
            // Keep colors stable and recognizable across charts
            if (key === 'saved') return '#f59e0b';     // amber
            if (key === 'approved') return '#10b981';   // green
            if (key === 'submitted') return '#2563eb';  // blue
            return '#64748b'; // fallback neutral (slate)
        }

        function buildChartStatusLegend(normalizedSeries) {
            if (!normalizedSeries || !normalizedSeries.length) return null;
            var counts = {};
            for (var i = 0; i < normalizedSeries.length; i++) {
                var s = normalizedSeries[i];
                if (!s) continue;
                var k = normalizeStatusKey(s.data_status);
                if (!k) continue;
                counts[k] = (counts[k] || 0) + 1;
            }
            var keys = Object.keys(counts);
            if (keys.length <= 1) return null;
            var order = { approved: 0, submitted: 1, saved: 2 };
            keys.sort(function (a, b) {
                var oa = (order[a] != null) ? order[a] : 999;
                var ob = (order[b] != null) ? order[b] : 999;
                if (oa !== ob) return oa - ob;
                return String(a).localeCompare(String(b));
            });
            return {
                title: 'Status',
                items: keys.map(function (k) {
                    return { key: k, label: statusLabel(k), color: colorForStatus(k) };
                })
            };
        }

        function addChartLegend(spec, onSelect) {
            if (!spec || !spec.items || !spec.items.length) return null;
            var wrap = document.createElement('div');
            wrap.style.display = 'flex';
            wrap.style.flexWrap = 'wrap';
            wrap.style.gap = '0.4rem';
            wrap.style.margin = '0.35rem 0 0.5rem 0';
            wrap.style.alignItems = 'center';
            wrap.style.color = '#0f172a';
            wrap.style.fontSize = '12px';

            var label = document.createElement('span');
            label.textContent = (spec.title || 'Legend') + ':';
            label.style.color = '#64748b';
            label.style.fontWeight = '600';
            wrap.appendChild(label);

            var activeKeys = [];
            function toggleKey(key) {
                var k = String(key || '');
                var idx = activeKeys.indexOf(k);
                if (idx === -1) {
                    activeKeys.push(k);
                } else {
                    activeKeys.splice(idx, 1);
                }
                try {
                    var btns = wrap.querySelectorAll('[data-legend-key]');
                    btns.forEach(function (b) {
                        var bk = b.getAttribute('data-legend-key');
                        var isActive = activeKeys.indexOf(bk) !== -1;
                        b.style.background = isActive ? 'rgba(37,99,235,0.10)' : 'rgba(15, 23, 42, 0.04)';
                        b.style.borderColor = isActive ? 'rgba(37,99,235,0.55)' : 'rgba(15, 23, 42, 0.12)';
                        b.style.color = isActive ? '#1d4ed8' : '#0f172a';
                        try { b.setAttribute('aria-pressed', isActive ? 'true' : 'false'); } catch (_) { /* ignore */ }
                    });
                } catch (e) { /* ignore */ }
                try { if (typeof onSelect === 'function') onSelect(activeKeys.slice()); } catch (e) { /* ignore */ }
            }

            for (var i = 0; i < spec.items.length; i++) {
                var it = spec.items[i];
                var pill = document.createElement('button');
                pill.type = 'button';
                pill.style.display = 'inline-flex';
                pill.style.alignItems = 'center';
                pill.style.gap = '0.35rem';
                pill.style.border = '1px solid rgba(148, 163, 184, 0.35)';
                pill.style.borderRadius = '999px';
                pill.style.padding = '0.2rem 0.5rem';
                pill.style.background = 'rgba(248, 250, 252, 0.9)';
                pill.style.fontSize = '11px';
                pill.style.lineHeight = '1.2';
                pill.style.cursor = 'pointer';
                pill.setAttribute('data-legend-key', String(it.key || ''));
                pill.setAttribute('aria-pressed', 'false');
                pill.addEventListener('click', (function (k, el) {
                    return function (e) {
                        try { e.preventDefault(); } catch (_) { /* ignore */ }
                        toggleKey(k);
                        try { el.blur(); } catch (_) { /* ignore */ }
                    };
                })(it.key, pill));

                var dot = document.createElement('span');
                dot.style.width = '8px';
                dot.style.height = '8px';
                dot.style.borderRadius = '999px';
                dot.style.background = it.color || '#2563eb';
                dot.style.display = 'inline-block';
                dot.style.boxShadow = '0 0 0 1px rgba(15, 23, 42, 0.12)';

                var txt = document.createElement('span');
                txt.textContent = it.label || it.key || '';

                pill.appendChild(dot);
                pill.appendChild(txt);
                wrap.appendChild(pill);
            }

            return wrap;
        }

        function buildDiscreteMarkers(seriesPoints) {
            var discrete = [];
            if (!seriesPoints || !seriesPoints.length) return discrete;
            for (var i = 0; i < seriesPoints.length; i++) {
                var p = seriesPoints[i] || {};
                var k = normalizeStatusKey(p.data_status);
                discrete.push({
                    seriesIndex: 0,
                    dataPointIndex: i,
                    fillColor: k ? colorForStatus(k) : '#64748b',
                    strokeColor: '#ffffff',
                    size: 5
                });
            }
            return discrete;
        }

        var lineGradientId = 'ngodb-line-grad-' + (Date.now().toString(36) + Math.random().toString(36).slice(2));
        var LOG = function () {
            if (window.ngodbChartGradientDebug) {
                console.log.apply(console, ['[Chart gradient]'].concat(Array.prototype.slice.call(arguments)));
            }
        };
        function applyLineGradient() {
            try {
                var svg = chartEl.querySelector('svg');
                if (!svg) return;
                if (!viewSeries || !viewSeries.length) return;
                var paths = svg.querySelectorAll('path[d]');
                var linePath = null;
                var maxLen = 0;
                var pathWithFill = null;
                var maxLenWithFill = 0;
                for (var i = 0; i < paths.length; i++) {
                    var p = paths[i];
                    var d = (p.getAttribute('d') || '').trim();
                    if (d.length < 20) continue;
                    var fill = (p.getAttribute('fill') || '').trim().toLowerCase();
                    var hasFill = fill && fill !== 'none';
                    if (hasFill) {
                        if (d.length > maxLenWithFill) {
                            maxLenWithFill = d.length;
                            pathWithFill = p;
                        }
                    } else {
                        if (d.length > maxLen) {
                            maxLen = d.length;
                            linePath = p;
                        }
                    }
                }
                if (!linePath && pathWithFill) {
                    linePath = pathWithFill;
                    maxLen = maxLenWithFill;
                }
                if (!linePath) return;
                LOG('applyLineGradient called');
                LOG('line path selected, d.length=', maxLen, 'stroke=', linePath.getAttribute('stroke'), 'fill=', linePath.getAttribute('fill'));
                var n = viewSeries.length;
                var colors = [];
                for (var j = 0; j < n; j++) {
                    var k = normalizeStatusKey((viewSeries[j] || {}).data_status);
                    colors.push(k ? colorForStatus(k) : '#64748b');
                }
                if (colors.length === 0) {
                    LOG('no colors');
                    return;
                }
                LOG('gradient stops:', n, 'colors:', colors.slice(0, 5).join(',') + (colors.length > 5 ? '...' : ''));
                var defs = svg.querySelector('defs') || (function () { var d = document.createElementNS('http://www.w3.org/2000/svg', 'defs'); svg.insertBefore(d, svg.firstChild); return d; })();
                var old = defs.querySelector('#' + lineGradientId);
                if (old) old.remove();
                var lg = document.createElementNS('http://www.w3.org/2000/svg', 'linearGradient');
                lg.setAttribute('id', lineGradientId);
                try {
                    var bbox = linePath.getBBox();
                    lg.setAttribute('gradientUnits', 'userSpaceOnUse');
                    lg.setAttribute('x1', String(bbox.x));
                    lg.setAttribute('x2', String(bbox.x + bbox.width));
                    lg.setAttribute('y1', String(bbox.y));
                    lg.setAttribute('y2', String(bbox.y));
                    LOG('gradient userSpaceOnUse bbox:', bbox.x, bbox.y, bbox.width, bbox.height);
                } catch (_) {
                    lg.setAttribute('gradientUnits', 'objectBoundingBox');
                    lg.setAttribute('x1', '0');
                    lg.setAttribute('x2', '1');
                    lg.setAttribute('y1', '0');
                    lg.setAttribute('y2', '0');
                    LOG('gradient objectBoundingBox (getBBox failed)');
                }
                if (n === 1) {
                    lg.appendChild((function (c) { var s = document.createElementNS('http://www.w3.org/2000/svg', 'stop'); s.setAttribute('offset', '0%'); s.setAttribute('stop-color', c); return s; })(colors[0]));
                    lg.appendChild((function (c) { var s = document.createElementNS('http://www.w3.org/2000/svg', 'stop'); s.setAttribute('offset', '100%'); s.setAttribute('stop-color', c); return s; })(colors[0]));
                } else {
                    for (var j = 0; j < n; j++) {
                        var s = document.createElementNS('http://www.w3.org/2000/svg', 'stop');
                        s.setAttribute('offset', (100 * j / (n - 1)) + '%');
                        s.setAttribute('stop-color', colors[j]);
                        lg.appendChild(s);
                    }
                }
                defs.appendChild(lg);
                var gradientUrl = 'url(#' + lineGradientId + ')';
                linePath.setAttribute('stroke', gradientUrl);
                linePath.style.stroke = gradientUrl;
                linePath.setAttribute('data-ngodb-line-path', '1');
                LOG('gradient applied id=', lineGradientId, 'path.stroke=', linePath.getAttribute('stroke'), 'path.style.stroke=', linePath.style.stroke);
            } catch (e) {
                LOG('error:', e && e.message, e);
            }
        }

        function getLinePathElement() {
            try {
                var svg = chartEl && chartEl.querySelector ? chartEl.querySelector('svg') : null;
                if (!svg) return null;
                var marked = svg.querySelector('path[data-ngodb-line-path="1"]');
                if (marked) return marked;
                var paths = svg.querySelectorAll('path[d]');
                var linePath = null;
                var maxLen = 0;
                var pathWithFill = null;
                var maxLenWithFill = 0;
                for (var i = 0; i < paths.length; i++) {
                    var p = paths[i];
                    var d = (p.getAttribute('d') || '').trim();
                    if (d.length < 20) continue;
                    var fill = (p.getAttribute('fill') || '').trim().toLowerCase();
                    var hasFill = fill && fill !== 'none';
                    if (hasFill) {
                        if (d.length > maxLenWithFill) { maxLenWithFill = d.length; pathWithFill = p; }
                    } else {
                        if (d.length > maxLen) { maxLen = d.length; linePath = p; }
                    }
                }
                if (!linePath && pathWithFill) linePath = pathWithFill;
                return linePath;
            } catch (e) { return null; }
        }

        var lineDrawDurationMs = 800;
        function applyLineDrawAnimation() {
            try {
                var linePath = getLinePathElement();
                if (!linePath) return;
                var len = linePath.getTotalLength();
                linePath.setAttribute('stroke-dasharray', String(len));
                linePath.style.strokeDasharray = String(len);
                linePath.style.strokeDashoffset = String(len);
                var start = null;
                function step(t) {
                    if (start == null) start = t;
                    var elapsed = t - start;
                    var progress = Math.min(elapsed / lineDrawDurationMs, 1);
                    var ease = 1 - Math.pow(1 - progress, 2);
                    var offset = len * (1 - ease);
                    linePath.style.strokeDashoffset = String(offset);
                    if (progress < 1) requestAnimationFrame(step);
                }
                requestAnimationFrame(step);
            } catch (e) { /* ignore */ }
        }

        var resizeTimeout = null;
        function scheduleGradientOnResize() {
            if (resizeTimeout) clearTimeout(resizeTimeout);
            resizeTimeout = setTimeout(function () {
                resizeTimeout = null;
                applyLineGradient();
            }, 150);
        }

        // ---------------------------------------------------------------------
        // Draggable data labels (SVG) - allows manual nudging without callouts.
        // ---------------------------------------------------------------------
        var labelDragOffsets = {}; // key: x/category label -> { dx, dy }
        var labelDragInstallTimeout = null;
        function scheduleLabelDragInstall() {
            try {
                if (!dataLabelsCheckbox || !dataLabelsCheckbox.checked) return;
                if (labelDragInstallTimeout) clearTimeout(labelDragInstallTimeout);
                labelDragInstallTimeout = setTimeout(function () {
                    labelDragInstallTimeout = null;
                    installDraggableDataLabels();
                }, 80);
            } catch (e) { /* ignore */ }
        }
        function installDraggableDataLabels() {
            try {
                if (!dataLabelsCheckbox || !dataLabelsCheckbox.checked) return;
                if (!chartEl || !chartEl.querySelector) return;
                var svg = chartEl.querySelector('svg');
                if (!svg) return;

                var chart = chartRef && chartRef.current ? chartRef.current : null;
                var categories = null;
                try {
                    categories = chart && chart.w && chart.w.globals ? chart.w.globals.categoryLabels : null;
                } catch (e) { categories = null; }
                if (!categories || !categories.length) {
                    // Fallback to current viewSeries if globals aren't ready yet.
                    categories = (viewSeries || []).map(function (p) { return p && p.x != null ? p.x : ''; });
                }

                // ApexCharts data labels can have a few class names depending on version.
                var selector = 'text.apexcharts-datalabel, text.apexcharts-data-label, .apexcharts-datalabels text';
                var nodeList = svg.querySelectorAll(selector);
                if (!nodeList || !nodeList.length) return;

                function asKey(v) {
                    if (v == null) return '';
                    try { return String(v); } catch (e) { return '' + v; }
                }
                function setTransformWithOffset(g, base, off) {
                    var dx = (off && isFinite(off.dx)) ? Number(off.dx) : 0;
                    var dy = (off && isFinite(off.dy)) ? Number(off.dy) : 0;
                    var tr = base || '';
                    if (dx || dy) tr = (tr ? (tr + ' ') : '') + ('translate(' + dx + ',' + dy + ')');
                    g.setAttribute('transform', tr);
                }

                for (var i = 0; i < nodeList.length; i++) {
                    var t = nodeList[i];
                    if (!t) continue;
                    var g = (t.parentElement && t.parentElement.tagName && t.parentElement.tagName.toLowerCase() === 'g')
                        ? t.parentElement
                        : t;

                    var xKey = asKey(categories[i]);
                    if (!xKey && viewSeries && viewSeries[i] && viewSeries[i].x != null) xKey = asKey(viewSeries[i].x);

                    // Store baseline transform from ApexCharts so offsets stack on top.
                    var base = g.getAttribute('data-ngodb-label-base-transform');
                    if (base == null) {
                        base = g.getAttribute('transform') || '';
                        g.setAttribute('data-ngodb-label-base-transform', base);
                    }
                    g.setAttribute('data-ngodb-label-xkey', xKey);

                    // Apply stored offset (if any).
                    var off = labelDragOffsets[xKey] || { dx: 0, dy: 0 };
                    setTransformWithOffset(g, base, off);

                    // Install handlers once per element instance.
                    if (g.getAttribute('data-ngodb-label-draggable') === '1') continue;
                    g.setAttribute('data-ngodb-label-draggable', '1');

                    try { g.style.cursor = 'grab'; } catch (e) { /* ignore */ }
                    try { g.style.pointerEvents = 'all'; } catch (e) { /* ignore */ }
                    try { t.style.pointerEvents = 'all'; } catch (e) { /* ignore */ }
                    try { t.style.userSelect = 'none'; } catch (e) { /* ignore */ }

                    g.addEventListener('pointerdown', function (ev) {
                        try {
                            if (!dataLabelsCheckbox || !dataLabelsCheckbox.checked) return;
                            if (!ev || ev.button !== 0) return; // left click only
                            ev.preventDefault();
                            ev.stopPropagation();

                            var targetG = ev.currentTarget;
                            if (!targetG) return;
                            var key = targetG.getAttribute('data-ngodb-label-xkey') || '';
                            var baseTr = targetG.getAttribute('data-ngodb-label-base-transform') || (targetG.getAttribute('transform') || '');
                            var startX = ev.clientX;
                            var startY = ev.clientY;
                            var startOff = labelDragOffsets[key] || { dx: 0, dy: 0 };
                            var pointerId = ev.pointerId;

                            try { targetG.setPointerCapture(pointerId); } catch (e) { /* ignore */ }
                            try { targetG.style.cursor = 'grabbing'; } catch (e) { /* ignore */ }

                            function onMove(e2) {
                                try {
                                    if (!e2 || e2.pointerId !== pointerId) return;
                                    e2.preventDefault();
                                    var dx = Number(startOff.dx || 0) + (Number(e2.clientX) - Number(startX));
                                    var dy = Number(startOff.dy || 0) + (Number(e2.clientY) - Number(startY));
                                    labelDragOffsets[key] = { dx: dx, dy: dy };
                                    setTransformWithOffset(targetG, baseTr, labelDragOffsets[key]);
                                } catch (e) { /* ignore */ }
                            }
                            function onUp(e3) {
                                try {
                                    if (!e3 || e3.pointerId !== pointerId) return;
                                    try { targetG.releasePointerCapture(pointerId); } catch (e) { /* ignore */ }
                                    try { targetG.style.cursor = 'grab'; } catch (e) { /* ignore */ }
                                    window.removeEventListener('pointermove', onMove, true);
                                    window.removeEventListener('pointerup', onUp, true);
                                    window.removeEventListener('pointercancel', onUp, true);
                                } catch (e) { /* ignore */ }
                            }

                            window.addEventListener('pointermove', onMove, true);
                            window.addEventListener('pointerup', onUp, true);
                            window.addEventListener('pointercancel', onUp, true);
                        } catch (e) { /* ignore */ }
                    }, { passive: false });
                }
            } catch (e) { /* ignore */ }
        }

        chartSwitch.viewVisual.style.marginTop = '0';
        var chartEl = document.createElement('div');
        chartEl.className = 'chat-immersive-chart-inner';
        chartEl.style.position = 'relative';
        chartEl.style.zIndex = '1';
        chartEl.style.height = '320px';
        chartEl.style.width = '100%';
        chartEl.style.borderRadius = '0.625rem';
        chartEl.style.overflow = 'hidden';
        chartEl.style.background = 'linear-gradient(180deg, #fafbfc 0%, #ffffff 100%)';
        chartSwitch.viewVisual.appendChild(chartEl);
        dataLabelsToggle.style.marginTop = '0.5rem';
        chartSwitch.viewVisual.appendChild(dataLabelsToggle);

        var chartTableEl = buildDataTableFromPayload(normalized);
        if (chartTableEl) chartSwitch.viewTable.appendChild(chartTableEl);
        chartSwitch.viewTable.style.marginTop = '0.5rem';

        card.appendChild(chartSwitch.viewVisual);
        card.appendChild(chartSwitch.viewTable);

        var fileBase = slugifyFileName((normalized.title || 'trend') + '-' + (normalized.metric || 'value'));
        var chartRef = { current: null };
        createExportDropdown(actions, [
            { label: 'Save PNG', onClick: function () { saveApexChartAsImage(chartRef.current, fileBase, 'png', chartSwitch); } },
            { label: 'Save SVG', onClick: function () { saveApexChartAsImage(chartRef.current, fileBase, 'svg', chartSwitch); } },
            { label: 'Save Excel', onClick: function () { saveChartAsExcel(normalized, fileBase); } }
        ]);

        if (targetContent) {
            targetContent.appendChild(card);
        } else if (targetWrapper) {
            targetWrapper.insertAdjacentElement('afterend', card);
        } else {
            return false;
        }

        var baseSeries = normalized.series.slice();
        var viewSeries = baseSeries.slice();
        var years = viewSeries.map(function (p) { return p.x; });
        var values = viewSeries.map(function (p) { return p.y; });

        var legendSpec = buildChartStatusLegend(baseSeries);
        var activeStatusKeys = [];
        function applyStatusFilter() {
            try {
                if (!chartRef.current) return;
                viewSeries = (activeStatusKeys.length === 0)
                    ? baseSeries.slice()
                    : baseSeries.filter(function (p) {
                        var k = p && normalizeStatusKey(p.data_status);
                        return k && activeStatusKeys.indexOf(String(k)) !== -1;
                    });
                var y = viewSeries.map(function (p) { return p.x; });
                var v = viewSeries.map(function (p) { return p.y; });

                // Update without ApexCharts animation so shadow stays static; line draw runs in updated event.
                chartRef.current.updateOptions({ xaxis: { categories: y } }, false);
                chartRef.current.updateSeries([{ name: normalized.metric || 'Value', data: v }], false);
                chartRef.current.updateOptions({
                    markers: {
                        size: 5,
                        strokeWidth: 2,
                        strokeColors: '#ffffff',
                        hover: { size: 7 },
                        discrete: buildDiscreteMarkers(viewSeries)
                    }
                }, false);
                setTimeout(applyLineGradient, 50);
                scheduleLabelDragInstall();
            } catch (e) { /* ignore */ }
        }

        var legendEl = legendSpec ? addChartLegend(legendSpec, function (selectedKeys) {
            activeStatusKeys = selectedKeys || [];
            applyStatusFilter();
        }) : null;
        if (legendEl) {
            // Insert legend between title and chart view
            card.insertBefore(legendEl, chartSwitch.viewVisual);
        }

        Promise.resolve()
            .then(function () { return ensureApexCharts(); })
            .then(function (ApexCharts) {
                if (!ApexCharts) throw new Error('ApexCharts unavailable');
                var chart = new ApexCharts(chartEl, {
                    chart: {
                        type: 'area',
                        height: 320,
                        fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
                        toolbar: { show: false },
                        background: 'transparent',
                        animations: { enabled: false },
                        dropShadow: { enabled: false },
                        events: {
                            mounted: function () {
                                chartEl.classList.add('chat-immersive-chart-mounted');
                                setTimeout(applyLineGradient, 80);
                                setTimeout(applyLineGradient, 350);
                                setTimeout(function () { applyLineGradient(); applyLineDrawAnimation(); }, 450);
                                window.addEventListener('resize', scheduleGradientOnResize);
                                setTimeout(scheduleLabelDragInstall, 140);
                            },
                            updated: function () {
                                setTimeout(applyLineGradient, 50);
                                setTimeout(applyLineGradient, 280);
                                setTimeout(function () { applyLineGradient(); applyLineDrawAnimation(); }, 350);
                                setTimeout(scheduleLabelDragInstall, 80);
                            }
                        }
                    },
                    series: [{ name: normalized.metric || 'Value', data: values }],
                    stroke: { curve: 'smooth', width: 2.5 },
                    fill: {
                        type: 'gradient',
                        gradient: {
                            shade: 'light',
                            type: 'vertical',
                            shadeIntensity: 0.4,
                            opacityFrom: 0.5,
                            opacityTo: 0.06
                        }
                    },
                    markers: {
                        size: 5,
                        strokeWidth: 2,
                        strokeColors: '#ffffff',
                        hover: { size: 7 },
                        discrete: buildDiscreteMarkers(viewSeries)
                    },
                    colors: ['#475569'],
                    dataLabels: {
                        enabled: false,
                        offsetY: -4,
                        formatter: dataLabelsFormatter
                    },
                    grid: {
                        borderColor: 'rgba(148, 163, 184, 0.2)',
                        strokeDashArray: 0,
                        xaxis: { lines: { show: false } },
                        yaxis: { lines: { show: true } },
                        padding: { left: 12, right: 16, top: 8, bottom: 0 }
                    },
                    xaxis: {
                        categories: years,
                        axisBorder: { show: false },
                        axisTicks: { show: false },
                        labels: {
                            style: { fontSize: '11px', colors: '#64748b' }
                        }
                    },
                    yaxis: {
                        axisBorder: { show: false },
                        axisTicks: { show: false },
                        labels: {
                            style: { fontSize: '11px', colors: '#64748b' },
                            formatter: function (val) {
                                if (val == null) return '';
                                try { return Number(val).toLocaleString(); } catch (e) { return String(val); }
                            }
                        }
                    },
                    tooltip: {
                        theme: 'light',
                        custom: function (ctx) {
                            try {
                                var seriesIndex = ctx.seriesIndex || 0;
                                var dataPointIndex = ctx.dataPointIndex;
                                var year = (ctx.w && ctx.w.globals && ctx.w.globals.categoryLabels)
                                    ? ctx.w.globals.categoryLabels[dataPointIndex]
                                    : '';
                                var rawVal = (ctx.series && ctx.series[seriesIndex]) ? ctx.series[seriesIndex][dataPointIndex] : null;
                                var p = viewSeries && viewSeries[dataPointIndex] ? viewSeries[dataPointIndex] : null;
                                var stKey = p ? normalizeStatusKey(p.data_status) : null;
                                var stLabel = stKey ? statusLabel(stKey) : '';
                                var stColor = stKey ? colorForStatus(stKey) : '#64748b';
                                var valText = formatNumber(rawVal);

                                var statusRow = stLabel
                                    ? ('<div style="margin-top:4px;color:#64748b;font-size:11px;">' +
                                        '<span style="display:inline-block;width:6px;height:6px;border-radius:999px;background:' + escapeHtml(stColor) + ';margin-right:6px;vertical-align:middle;"></span>' +
                                        escapeHtml(stLabel) +
                                      '</div>')
                                    : '';

                                return (
                                    '<div style="padding:10px 12px;min-width:130px;border-radius:8px;background:#ffffff;border:1px solid #e2e8f0;box-shadow:0 4px 12px rgba(15,23,42,0.08);">' +
                                      '<div style="font-weight:600;color:#0f172a;font-size:12px;margin-bottom:4px;">' + escapeHtml(String(year)) + '</div>' +
                                      '<div style="color:#334155;font-size:13px;font-weight:500;">' + escapeHtml(valText) + '</div>' +
                                      statusRow +
                                    '</div>'
                                );
                            } catch (e) {
                                return '';
                            }
                        },
                        y: {
                            formatter: function (val) {
                                if (val == null) return '';
                                try { return Number(val).toLocaleString(); } catch (e) { return String(val); }
                            }
                        }
                    }
                });
                chart.render();
                chartRef.current = chart;
                applyStatusFilter();
                setTimeout(applyLineGradient, 150);
            })
            .catch(function () {
                chartEl.innerHTML = '';
                var fallback = document.createElement('div');
                fallback.style.fontSize = '0.82rem';
                fallback.style.color = '#334155';
                fallback.textContent = 'Chart preview unavailable. Data points: ' + normalized.series.length;
                chartEl.appendChild(fallback);
            });

        return true;
    }

    function scheduleMapRenderRetry(payload, wrapper, attempt, messageElement) {
        var n = Number(attempt || 0);
        if (n >= 8) return;
        var timer = setTimeout(function () {
            var ok = renderMapCard(payload, wrapper, messageElement);
            if (!ok) scheduleMapRenderRetry(payload, wrapper, n + 1, messageElement);
        }, 120);
        pendingMapRenderRetries.push(timer);
    }

    function apiFetch(url) {
        return ((window.getFetch && window.getFetch()) || fetch)(url);
    }

    function renderChatListItems(conversations, listEl, bot, searchQuery) {
        if (!listEl || !bot) return;
        const activeId = (bot.getActiveConversationId && bot.getActiveConversationId()) || null;

        try { listEl.replaceChildren(); } catch (_) { listEl.innerHTML = ''; }

        if (!conversations.length) {
            var msg = (searchQuery && lastConversations.length > 0)
                ? t('noConversationsMatch', 'No conversations match your search.')
                : '';
            if (msg) {
                var emptyLi = document.createElement('li');
                emptyLi.className = 'chat-immersive-chat-list-empty';
                emptyLi.textContent = msg;
                listEl.appendChild(emptyLi);
            }
            return;
        }

        var newChatLabel = t('newChat', 'New chat');
        var deleteChatLabel = t('deleteChat', 'Delete chat');
        var runningLabel = t('running', 'Running…');

        sidebarRunningLog('renderChatListItems start', { conversationCount: conversations.length, activeId: activeId || null });
        conversations.forEach(function (chat) {
            if (!chat || !chat.id) return;
            var chatId = String(chat.id);
            var title = String(chat.title || newChatLabel || '');
            var isActive = String(chat.id) === String(activeId || '');
            var isRunning = false;
            var isRunningFromBot = false;
            try {
                if (bot && typeof bot.isConversationRunning === 'function') {
                    isRunningFromBot = !!bot.isConversationRunning(chatId);
                    isRunning = isRunningFromBot;
                }
            } catch (_) { /* ignore */ }
            // Only use cached chat.inflight for non-active conversations (e.g. other tabs).
            // For the active conversation, trust the bot so the spinner stops as soon as the stream completes.
            var isRunningFromCache = false;
            if (!isRunning && !isActive) {
                isRunningFromCache = !!(chat && chat.inflight && String(chat.inflight.status || '') === 'in_progress');
                isRunning = isRunningFromCache;
            }
            sidebarRunningLog('conversation', { chatId: chatId, isActive: isActive, isRunningFromBot: isRunningFromBot, isRunningFromCache: isRunningFromCache, isRunning: isRunning, cacheInflight: chat && chat.inflight ? String(chat.inflight.status || '') : null });

            var li = document.createElement('li');
            li.className = 'chat-immersive-chat-item' + (isActive ? ' is-active' : '') + (isRunning ? ' is-running' : '');
            li.setAttribute('data-chat-id', chatId);

            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'chat-immersive-chat-item-btn';
            btn.addEventListener('click', function () {
                bot.switchChat(chatId);
            });

            var icon = document.createElement('i');
            icon.className = 'fas fa-message chat-immersive-chat-item-icon';
            icon.setAttribute('aria-hidden', 'true');

            var spinnerIcon = document.createElement('i');
            spinnerIcon.className = 'fas fa-spinner fa-spin chat-immersive-chat-item-icon-spinner';
            spinnerIcon.setAttribute('aria-label', runningLabel);
            spinnerIcon.title = runningLabel;

            var titleSpan = document.createElement('span');
            titleSpan.className = 'chat-immersive-chat-item-title';
            titleSpan.textContent = title;

            btn.appendChild(icon);
            btn.appendChild(spinnerIcon);
            btn.appendChild(titleSpan);

            var del = document.createElement('button');
            del.type = 'button';
            del.className = 'chat-immersive-chat-item-delete';
            del.setAttribute('aria-label', deleteChatLabel);
            del.title = deleteChatLabel;
            del.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();
                var message = t('deleteConversationConfirm', 'Delete this conversation? This cannot be undone.');
                var title2 = t('deleteConversationTitle', 'Delete conversation?');
                var deleteLabel = t('delete', 'Delete');
                var cancelLabel = t('cancel', 'Cancel');
                if (typeof window.showDangerConfirmation === 'function') {
                    window.showDangerConfirmation(
                        message,
                        function () { if (bot.deleteChat) bot.deleteChat(chatId); },
                        null,
                        deleteLabel,
                        cancelLabel,
                        title2
                    );
                } else if (window.showConfirmation) {
                    window.showConfirmation(message, () => { if (bot.deleteChat) bot.deleteChat(chatId); }, null, deleteLabel, cancelLabel, title2);
                }
            });

            var delIcon = document.createElement('i');
            delIcon.className = 'fas fa-trash';
            delIcon.setAttribute('aria-hidden', 'true');
            del.appendChild(delIcon);

            li.appendChild(btn);
            li.appendChild(del);
            listEl.appendChild(li);
        });
    }

    function updateClearAllVisibility() {
        var btn = document.getElementById('chatImmersiveClearAll');
        if (!btn) return;
        if (lastConversations.length > 0) {
            btn.classList.remove('is-hidden');
        } else {
            btn.classList.add('is-hidden');
        }
    }

    function applySearchFilter() {
        const listEl = document.getElementById(LIST_ID);
        const bot = getChatbot();
        const searchEl = document.getElementById(SEARCH_ID);
        const query = (searchEl && searchEl.value) ? searchEl.value.trim().toLowerCase() : '';
        var filtered = lastConversations;
        if (query) {
            var ncLabel = t('newChat', 'New chat');
            filtered = lastConversations.filter(function (c) {
                const title = (c.title || ncLabel).toLowerCase();
                return title.indexOf(query) !== -1;
            });
        }
        renderChatListItems(filtered, listEl, bot, query);
        updateClearAllVisibility();
    }

    function renderChatList() {
        const listEl = document.getElementById(LIST_ID);
        const titleEl = document.getElementById(TITLE_ID);
        const bot = getChatbot();
        if (!listEl || !bot) return;

        // Only show "Loading…" on the initial page load.
        // Subsequent background refreshes should be silent to avoid flicker.
        if (!hasLoadedConversationsOnce) {
            try { listEl.replaceChildren(); } catch (_) { listEl.innerHTML = ''; }
            var loadingLi = document.createElement('li');
            loadingLi.className = 'chat-immersive-chat-list-loading';
            loadingLi.textContent = t('loading', 'Loading…');
            listEl.appendChild(loadingLi);
        } else {
            try { listEl.setAttribute('aria-busy', 'true'); } catch (e) { /* ignore */ }
        }

        var newChatFallback = t('newChat', 'New chat');
        if (isRefreshingConversations) return;
        isRefreshingConversations = true;
        apiFetch('/api/ai/v2/conversations')
            .then(function (res) { return res.ok ? res.json() : { conversations: [] }; })
            .then(function (data) {
                lastConversations = data.conversations || [];
                hasLoadedConversationsOnce = true;
                try {
                    if (bot && typeof bot._setServerInflightIndex === 'function') {
                        bot._setServerInflightIndex(lastConversations);
                    }
                } catch (e) { /* ignore */ }
                const activeId = (bot.getActiveConversationId && bot.getActiveConversationId()) || null;
                const activeChat = lastConversations.find(function (c) { return c.id === activeId; });
                if (titleEl) {
                    titleEl.textContent = (activeChat && activeChat.title) ? activeChat.title : newChatFallback;
                }
                applySearchFilter();

            })
            .catch(function () {
                // If we already have a list rendered, keep it (silent refresh failure).
                if (!hasLoadedConversationsOnce) {
                    lastConversations = [];
                    listEl.innerHTML = '';
                    if (titleEl) titleEl.textContent = newChatFallback;
                    updateClearAllVisibility();
                }
            })
            .finally(function () {
                isRefreshingConversations = false;
                try { listEl.removeAttribute('aria-busy'); } catch (e) { /* ignore */ }
            });
    }

    function escapeAttr(s) {
        if (s == null) return '';
        const str = String(s);
        return str
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function init() {
        const newChatBtn = document.getElementById(NEW_CHAT_ID);
        const listEl = document.getElementById(LIST_ID);
        const searchEl = document.getElementById(SEARCH_ID);
        if (!listEl) return;

        var collapsed = getSidebarCollapsed();
        setSidebarCollapsedUI(collapsed);

        const bot = getChatbot();
        if (bot) {
            renderChatList();
        }

        if (newChatBtn) {
            newChatBtn.addEventListener('click', function () {
                const b = getChatbot();
                if (b && b.startNewChat) b.startNewChat();
            });
        }

        function handleSidebarToggle() {
            collapsed = getSidebarCollapsed();
            collapsed = !collapsed;
            setSidebarCollapsed(collapsed);
            setSidebarCollapsedUI(collapsed);
        }
        document.querySelectorAll('.chat-immersive-sidebar-toggle').forEach(function (btn) {
            btn.addEventListener('click', handleSidebarToggle);
        });

        var scrim = document.getElementById('chatImmersiveSidebarScrim');
        if (scrim) {
            scrim.addEventListener('click', function () {
                setSidebarCollapsed(true);
                setSidebarCollapsedUI(true);
            });
        }

        // Auto-scroll: scroll to bottom on send and while receiving; stop when user scrolls up; re-enable on new send
        window.ngodbChatImmersiveAutoScroll = true;
        var scrollContainer = document.querySelector('.chat-immersive-messages-scroll');
        var messagesEl = document.getElementById('chatMessages');
        var autoScrollThreshold = 80;
        if (scrollContainer) {
            scrollContainer.addEventListener('scroll', function () {
                var el = scrollContainer;
                var atBottom = el.scrollHeight - el.scrollTop - el.clientHeight <= autoScrollThreshold;
                if (!atBottom) window.ngodbChatImmersiveAutoScroll = false;
            }, { passive: true });
        }
        if (scrollContainer && messagesEl) {
            var scrollObserver = new MutationObserver(function (mutations) {
                for (var i = 0; i < mutations.length; i++) {
                    var added = mutations[i].addedNodes;
                    for (var j = 0; j < added.length; j++) {
                        var node = added[j];
                        if (node.nodeType !== 1) continue;
                        var wrapper = node.classList && node.classList.contains('chat-message-wrapper') && node.classList.contains('is-user') ? node : node.querySelector && node.querySelector('.chat-message-wrapper.is-user');
                        if (wrapper) {
                            window.ngodbChatImmersiveAutoScroll = true;
                            scrollContainer.scrollTop = scrollContainer.scrollHeight;
                            break;
                        }
                    }
                }
            });
            scrollObserver.observe(messagesEl, { childList: true, subtree: true });
        }

        var clearAllBtn = document.getElementById('chatImmersiveClearAll');
        if (clearAllBtn) {
            clearAllBtn.addEventListener('click', function () {
                var b = getChatbot();
                if (!b) return;
                // Hide button if no conversations
                if (!lastConversations.length) return;
                var message = t('clearAllConversationsConfirm', 'Delete all conversations? This cannot be undone.');
                var title = t('clearAllConversationsTitle', 'Clear all conversations?');
                var deleteLabel = t('clearAll', 'Clear all');
                var cancelLabel = t('cancel', 'Cancel');
                if (typeof window.showDangerConfirmation === 'function') {
                    window.showDangerConfirmation(
                        message,
                        function () { if (b.deleteAllChats) b.deleteAllChats(); },
                        null,
                        deleteLabel,
                        cancelLabel,
                        title
                    );
                } else if (window.showConfirmation) {
                    window.showConfirmation(message, () => { if (b.deleteAllChats) b.deleteAllChats(); }, null, deleteLabel, cancelLabel, title);
                }
            });
        }

        if (searchEl) {
            searchEl.addEventListener('input', applySearchFilter);
            searchEl.addEventListener('search', applySearchFilter);
        }

        var worldmapBtn = document.getElementById(WORLDMAP_PROMPT_BTN_ID);
        if (worldmapBtn) {
            worldmapBtn.addEventListener('click', function () {
                var b = getChatbot();
                var prompt = (worldmapBtn.getAttribute('data-prompt') || worldmapBtn.textContent || '').trim();
                if (!b || !prompt || !b.elements || !b.elements.input) return;
                b.elements.input.value = prompt;
                if (typeof b.handleSendMessage === 'function') b.handleSendMessage();
            });
        }

        function renderBarChartCard(payload, wrapperElement, messageElement) {
            var normalized = normalizeBarChartPayload(payload);
            var targetWrapper = resolveTargetWrapper(wrapperElement);
            if (!normalized || (!targetWrapper && !messageElement)) return false;
            if (targetWrapper && !targetWrapper.parentElement && !messageElement) return false;
            var targetContent = null;
            if (messageElement && messageElement.querySelector) {
                targetContent = messageElement.querySelector('.chat-message-content');
            }
            if (!targetContent) {
                targetContent = resolveTargetMessageContent(targetWrapper);
            }
            if (targetContent && targetContent.querySelector('.chat-immersive-bar-card')) return true;

            var card = document.createElement('div');
            card.className = 'chat-immersive-bar-card';
            card.style.cssText = 'position:relative;border:1px solid #e2e8f0;border-radius:0.875rem;padding:1rem;margin-top:0.75rem;background:#fff;box-shadow:0 1px 3px rgba(15,23,42,0.06);';

            var titleEl = document.createElement('div');
            titleEl.style.cssText = 'font-weight:600;font-size:0.9375rem;color:#0f172a;letter-spacing:-0.01em;margin-bottom:0.5rem;';
            titleEl.textContent = normalized.title;
            card.appendChild(titleEl);

            var chartEl = document.createElement('div');
            chartEl.style.cssText = 'position:relative;height:' + Math.max(260, normalized.categories.length * 36) + 'px;width:100%;border-radius:0.625rem;overflow:hidden;background:linear-gradient(180deg,#fafbfc 0%,#fff 100%);';
            card.appendChild(chartEl);

            if (targetContent) { targetContent.appendChild(card); }
            else if (targetWrapper) { targetWrapper.insertAdjacentElement('afterend', card); }
            else { return false; }

            var labels = normalized.categories.map(function (c) { return c.label; });
            var values = normalized.categories.map(function (c) { return c.value; });
            var isHorizontal = normalized.orientation === 'horizontal';

            Promise.resolve()
                .then(function () { return ensureApexCharts(); })
                .then(function (ApexCharts) {
                    if (!ApexCharts) return;
                    var opts = {
                        chart: {
                            type: 'bar',
                            height: Math.max(260, normalized.categories.length * 36),
                            fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
                            toolbar: { show: false },
                            background: 'transparent',
                            animations: { enabled: true, easing: 'easeinout', speed: 600 }
                        },
                        plotOptions: {
                            bar: {
                                horizontal: isHorizontal,
                                borderRadius: 4,
                                columnWidth: '55%',
                                barHeight: '60%'
                            }
                        },
                        series: [{ name: normalized.metric, data: values }],
                        xaxis: {
                            categories: labels,
                            axisBorder: { show: false },
                            axisTicks: { show: false },
                            labels: { style: { fontSize: '11px', colors: '#64748b' } }
                        },
                        yaxis: {
                            axisBorder: { show: false },
                            axisTicks: { show: false },
                            labels: {
                                style: { fontSize: '11px', colors: '#64748b' },
                                formatter: function (v) { return typeof v === 'number' ? v.toLocaleString(undefined, { maximumFractionDigits: 0 }) : v; }
                            }
                        },
                        colors: ['#2563eb'],
                        dataLabels: {
                            enabled: normalized.categories.length <= 12,
                            formatter: function (v) { return typeof v === 'number' ? v.toLocaleString(undefined, { maximumFractionDigits: 0 }) : v; },
                            style: { fontSize: '11px', colors: ['#334155'] }
                        },
                        grid: {
                            borderColor: 'rgba(148,163,184,0.2)',
                            xaxis: { lines: { show: isHorizontal } },
                            yaxis: { lines: { show: !isHorizontal } },
                            padding: { left: 8, right: 16, top: 4, bottom: 0 }
                        },
                        tooltip: {
                            y: { formatter: function (v) { return typeof v === 'number' ? v.toLocaleString(undefined, { maximumFractionDigits: 2 }) : v; } }
                        }
                    };
                    var chart = new ApexCharts(chartEl, opts);
                    chart.render();
                })
                .catch(function (e) { /* ignore */ });

            return true;
        }

        function renderPieChartCard(payload, wrapperElement, messageElement) {
            var normalized = normalizePieChartPayload(payload);
            var targetWrapper = resolveTargetWrapper(wrapperElement);
            if (!normalized || (!targetWrapper && !messageElement)) return false;
            if (targetWrapper && !targetWrapper.parentElement && !messageElement) return false;
            var targetContent = null;
            if (messageElement && messageElement.querySelector) {
                targetContent = messageElement.querySelector('.chat-message-content');
            }
            if (!targetContent) {
                targetContent = resolveTargetMessageContent(targetWrapper);
            }
            if (targetContent && targetContent.querySelector('.chat-immersive-pie-card')) return true;

            var card = document.createElement('div');
            card.className = 'chat-immersive-pie-card';
            card.style.cssText = 'position:relative;border:1px solid #e2e8f0;border-radius:0.875rem;padding:1rem;margin-top:0.75rem;background:#fff;box-shadow:0 1px 3px rgba(15,23,42,0.06);';

            var titleEl = document.createElement('div');
            titleEl.style.cssText = 'font-weight:600;font-size:0.9375rem;color:#0f172a;letter-spacing:-0.01em;margin-bottom:0.5rem;';
            titleEl.textContent = normalized.title;
            card.appendChild(titleEl);

            var chartEl = document.createElement('div');
            chartEl.style.cssText = 'position:relative;height:340px;width:100%;border-radius:0.625rem;overflow:hidden;background:linear-gradient(180deg,#fafbfc 0%,#fff 100%);';
            card.appendChild(chartEl);

            if (targetContent) { targetContent.appendChild(card); }
            else if (targetWrapper) { targetWrapper.insertAdjacentElement('afterend', card); }
            else { return false; }

            var labels = normalized.slices.map(function (s) { return s.label; });
            var values = normalized.slices.map(function (s) { return s.value; });

            Promise.resolve()
                .then(function () { return ensureApexCharts(); })
                .then(function (ApexCharts) {
                    if (!ApexCharts) return;
                    var opts = {
                        chart: {
                            type: 'donut',
                            height: 340,
                            fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
                            toolbar: { show: false },
                            background: 'transparent',
                            animations: { enabled: true, easing: 'easeinout', speed: 600 }
                        },
                        series: values,
                        labels: labels,
                        colors: ['#2563eb', '#059669', '#d97706', '#dc2626', '#7c3aed', '#0891b2', '#be185d', '#65a30d', '#c2410c', '#4338ca'],
                        legend: {
                            position: 'bottom',
                            fontSize: '12px',
                            fontFamily: 'Inter, -apple-system, sans-serif',
                            labels: { colors: '#334155' },
                            markers: { width: 10, height: 10, radius: 3 },
                            itemMargin: { horizontal: 8, vertical: 4 }
                        },
                        dataLabels: {
                            enabled: true,
                            formatter: function (val) { return typeof val === 'number' ? val.toFixed(1) + '%' : val; },
                            style: { fontSize: '12px', fontWeight: 600 },
                            dropShadow: { enabled: false }
                        },
                        plotOptions: {
                            pie: {
                                donut: {
                                    size: '55%',
                                    labels: {
                                        show: true,
                                        name: { fontSize: '13px', color: '#334155' },
                                        value: {
                                            fontSize: '18px',
                                            fontWeight: 700,
                                            color: '#0f172a',
                                            formatter: function (v) { return Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 }); }
                                        },
                                        total: {
                                            show: true,
                                            label: 'Total',
                                            fontSize: '13px',
                                            color: '#64748b',
                                            formatter: function (w) {
                                                var sum = 0;
                                                for (var i = 0; i < w.globals.seriesTotals.length; i++) sum += w.globals.seriesTotals[i];
                                                return sum.toLocaleString(undefined, { maximumFractionDigits: 0 });
                                            }
                                        }
                                    }
                                }
                            }
                        },
                        stroke: { width: 2, colors: ['#ffffff'] },
                        tooltip: {
                            y: { formatter: function (v) { return typeof v === 'number' ? v.toLocaleString(undefined, { maximumFractionDigits: 0 }) : v; } }
                        }
                    };
                    var chart = new ApexCharts(chartEl, opts);
                    chart.render();
                })
                .catch(function (e) { /* ignore */ });

            return true;
        }

        function renderDataTableCard(payload, wrapperElement, messageElement) {
            if (!payload || !Array.isArray(payload.rows) || !payload.rows.length) return;
            // Prefer finding targetContent directly from messageElement to avoid the
            // resolveTargetWrapper fallback routing all tables into the last bot message.
            var targetContent = null;
            if (messageElement && messageElement.querySelector) {
                targetContent = messageElement.querySelector('.chat-message-content');
            }
            var targetWrapper = resolveTargetWrapper(wrapperElement);
            tableDebugLog('renderDataTableCard resolve', {
                title: (payload && payload.title) || 'no title',
                rowCount: (payload && payload.rows) ? payload.rows.length : 0,
                fromMessageEl: !!targetContent && !!(messageElement && messageElement.querySelector),
                targetWrapperUsed: !!targetWrapper,
                targetWrapperInDOM: !!(targetWrapper && targetWrapper.parentElement),
                targetContentFound: !!targetContent
            });
            if (!targetWrapper && !targetContent) {
                tableDebugLog('renderDataTableCard early return: no target');
                return;
            }
            if (!targetContent) {
                targetContent = resolveTargetMessageContent(targetWrapper);
            }
            // Prevent duplicate table cards on the same message (e.g. from structured+done double-dispatch).
            var checkEl = targetContent || targetWrapper;
            if (checkEl && checkEl.querySelector('.chat-immersive-table-card')) {
                tableDebugLog('renderDataTableCard early return: duplicate card already present');
                return;
            }

            var columns = Array.isArray(payload.columns) ? payload.columns : [];
            var allRows = payload.rows.slice();
            var sortBy = payload.sort_by || (columns.length ? columns[0].key : '');
            var sortOrder = payload.sort_order || 'desc';
            var tableId = 'dt-' + Math.random().toString(36).slice(2, 9);

            var columnWidthByKey = {};
            (function computeColumnWidths() {
                var sampleRows = allRows.slice(0, 250);
                columns.forEach(function (col) {
                    var key = col && col.key ? col.key : '';
                    if (!key) return;
                    var keyLabel = ((col && (col.label || '')) + ' ' + key).toLowerCase();
                    var isLinkishCol = col.type === 'link' || /\b(document|source|file|url|link)\b/.test(keyLabel);
                    var labelLen = String((col.label || key) || '').trim().length;
                    var maxLen = labelLen;
                    var sumLen = 0;
                    var seen = 0;
                    sampleRows.forEach(function (row) {
                        var raw = row ? row[key] : '';
                        if (raw == null) return;
                        var len = String(raw).trim().length;
                        if (!len) return;
                        if (len > maxLen) maxLen = len;
                        sumLen += len;
                        seen += 1;
                    });
                    var avgLen = seen ? (sumLen / seen) : labelLen;
                    var weighted = Math.max(labelLen, Math.min(90, Math.round((avgLen * 1.3) + (maxLen * 0.45))));
                    var isNumericCol = col.type === 'number' || col.type === 'percent';
                    var baseMin = isNumericCol ? 110 : (isLinkishCol ? 120 : 130);
                    var baseMax = isNumericCol ? 220 : (isLinkishCol ? 220 : 320);
                    var minWidth = Math.round(Math.max(baseMin, Math.min(baseMax, 58 + (weighted * (isNumericCol ? 3.1 : 4.2)))));
                    var maxWidth = Math.round(Math.max(minWidth + 30, Math.min(isLinkishCol ? 260 : 380, minWidth + (isNumericCol ? 55 : (isLinkishCol ? 55 : 110)))));
                    columnWidthByKey[key] = {
                        min: minWidth,
                        max: maxWidth
                    };
                });
            })();

            var card = document.createElement('div');
            card.className = 'chat-immersive-table-card';
            card.style.cssText = 'margin:12px 0;border:1px solid var(--ngodb-border,#e2e8f0);border-radius:10px;overflow:hidden;background:var(--ngodb-card-bg,#fff);';

            var header = document.createElement('div');
            header.style.cssText = 'padding:10px 14px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--ngodb-border,#e2e8f0);background:var(--ngodb-card-header-bg,#f8fafc);';
            var titleEl = document.createElement('span');
            titleEl.style.cssText = 'font-weight:600;font-size:14px;color:var(--ngodb-text,#1e293b);';
            titleEl.textContent = (payload.title || 'Data Table') + ' (' + allRows.length + ' rows)';
            header.appendChild(titleEl);

            var searchInput = document.createElement('input');
            searchInput.type = 'search';
            searchInput.placeholder = 'Filter\u2026';
            searchInput.style.cssText = 'padding:4px 8px;border:1px solid var(--ngodb-border,#cbd5e1);border-radius:6px;font-size:12px;width:160px;outline:none;';
            var controls = document.createElement('div');
            controls.style.cssText = 'display:flex;align-items:center;gap:8px;flex-shrink:0;';
            controls.appendChild(searchInput);
            var actions = document.createElement('div');
            actions.style.display = 'inline-flex';
            controls.appendChild(actions);
            header.appendChild(controls);
            card.appendChild(header);

            var tableWrap = document.createElement('div');
            tableWrap.style.cssText = 'overflow-x:auto;max-height:520px;overflow-y:auto;';
            var table = document.createElement('table');
            table.id = tableId;
            table.style.cssText = 'min-width:100%;border-collapse:collapse;font-size:13px;';

            var thead = document.createElement('thead');
            var headRow = document.createElement('tr');
            headRow.style.cssText = 'position:sticky;top:0;background:var(--ngodb-card-header-bg,#f1f5f9);z-index:1;';
            columns.forEach(function (col) {
                var th = document.createElement('th');
                th.dataset.key = col.key;
                var w = columnWidthByKey[col.key] || { min: 130, max: 360 };
                var thStyle = 'padding:8px 10px;text-align:left;font-weight:600;font-size:12px;color:var(--ngodb-text-muted,#64748b);border-bottom:2px solid var(--ngodb-border,#e2e8f0);cursor:pointer;user-select:none;white-space:normal;word-wrap:break-word;overflow-wrap:anywhere;word-break:break-word;min-width:' + w.min + 'px;max-width:' + w.max + 'px;';
                th.style.cssText = thStyle;
                th.textContent = col.label || col.key;
                if (col.sortable !== false) {
                    var arrow = document.createElement('span');
                    arrow.className = 'sort-arrow';
                    arrow.style.cssText = 'margin-left:4px;font-size:10px;opacity:0.4;';
                    arrow.textContent = col.key === sortBy ? (sortOrder === 'asc' ? '\u25B2' : '\u25BC') : '\u25BC';
                    if (col.key === sortBy) arrow.style.opacity = '1';
                    th.appendChild(arrow);
                    th.addEventListener('click', function () {
                        if (sortBy === col.key) {
                            sortOrder = sortOrder === 'asc' ? 'desc' : 'asc';
                        } else {
                            sortBy = col.key;
                            sortOrder = (col.type === 'number' || col.type === 'percent') ? 'desc' : 'asc';
                        }
                        renderRows();
                        thead.querySelectorAll('.sort-arrow').forEach(function (a) { a.style.opacity = '0.4'; a.textContent = '\u25BC'; });
                        arrow.style.opacity = '1';
                        arrow.textContent = sortOrder === 'asc' ? '\u25B2' : '\u25BC';
                    });
                }
                headRow.appendChild(th);
            });
            thead.appendChild(headRow);
            table.appendChild(thead);

            var tbody = document.createElement('tbody');
            table.appendChild(tbody);
            tableWrap.appendChild(table);
            card.appendChild(tableWrap);
            if (targetContent) {
                targetContent.appendChild(card);
                tableDebugLog('renderDataTableCard appended to targetContent', { title: (payload && payload.title) || '' });
            } else if (targetWrapper) {
                targetWrapper.appendChild(card);
                tableDebugLog('renderDataTableCard appended to targetWrapper', { title: (payload && payload.title) || '' });
            } else {
                tableDebugLog('renderDataTableCard no append target');
                return;
            }

            var filterText = '';

            function renderRows() {
                var filtered = allRows;
                if (filterText) {
                    var ft = filterText.toLowerCase();
                    filtered = allRows.filter(function (r) {
                        return columns.some(function (c) {
                            var v = r[c.key];
                            return v != null && String(v).toLowerCase().indexOf(ft) >= 0;
                        });
                    });
                }
                var col = columns.find(function (c) { return c.key === sortBy; });
                var isNum = col && (col.type === 'number' || col.type === 'percent');
                filtered.sort(function (a, b) {
                    var va = a[sortBy], vb = b[sortBy];
                    if (va == null && vb == null) return 0;
                    if (va == null) return 1;
                    if (vb == null) return -1;
                    if (isNum) {
                        va = Number(va) || 0; vb = Number(vb) || 0;
                    } else {
                        va = String(va).toLowerCase(); vb = String(vb).toLowerCase();
                    }
                    var cmp = va < vb ? -1 : va > vb ? 1 : 0;
                    return sortOrder === 'asc' ? cmp : -cmp;
                });

                tbody.innerHTML = '';
                var even = false;
                filtered.forEach(function (row) {
                    var tr = document.createElement('tr');
                    tr.style.cssText = even ? 'background:var(--ngodb-row-alt,#f8fafc);' : '';
                    even = !even;
                    columns.forEach(function (col) {
                        var td = document.createElement('td');
                        var w = columnWidthByKey[col.key] || { min: 130, max: 360 };
                        td.style.cssText = 'padding:6px 10px;border-bottom:1px solid var(--ngodb-border,#f1f5f9);white-space:normal;word-wrap:break-word;overflow-wrap:anywhere;word-break:break-word;min-width:' + w.min + 'px;max-width:' + w.max + 'px;';
                        var val = row[col.key];
                        var isNumeric = (col.type === 'number' || col.type === 'percent') && val != null && Number.isFinite(Number(val));
                        if (col.type === 'link' && val) {
                            var urlKey = col.url_key || (col.key + '_url');
                            var href = row[urlKey];
                            if (href) {
                                var a = document.createElement('a');
                                a.href = href;
                                a.target = '_blank';
                                a.rel = 'noopener';
                                a.textContent = String(val);
                                a.style.cssText = 'color:var(--ngodb-link,#2563eb);text-decoration:none;display:inline-block;max-width:100%;white-space:normal;word-wrap:break-word;overflow-wrap:anywhere;word-break:break-word;';
                                a.addEventListener('mouseenter', function () { a.style.textDecoration = 'underline'; });
                                a.addEventListener('mouseleave', function () { a.style.textDecoration = 'none'; });
                                td.appendChild(a);
                            } else {
                                td.textContent = String(val);
                            }
                        } else if (isNumeric) {
                            td.style.textAlign = 'right';
                            var formatted = Number(val).toLocaleString(undefined, { maximumFractionDigits: 2 });
                            td.textContent = col.type === 'percent' ? formatted + '%' : formatted;
                        } else {
                            td.textContent = val != null ? String(val) : '';
                        }
                        tr.appendChild(td);
                    });
                    tbody.appendChild(tr);
                });
                titleEl.textContent = (payload.title || 'Data Table') + ' (' + filtered.length + (filtered.length !== allRows.length ? ' of ' + allRows.length : '') + ' rows)';
            }

            searchInput.addEventListener('input', function () {
                filterText = (searchInput.value || '').trim();
                renderRows();
            });

            renderRows();
            var fileBase = slugifyFileName((payload.title || 'data-table') + '-table');
            createExportDropdown(actions, [
                {
                    label: 'Save Excel',
                    onClick: function () {
                        saveDataTableAsExcel(columns, allRows, fileBase);
                    }
                }
            ]);
        }

        function tableDebugLog() {
            try {
                if (window.debug && window.debug.getConfig && window.debug.getConfig().modules.chatbot) {
                    console.log.apply(console, ['[Chatbot tables]'].concat(Array.prototype.slice.call(arguments)));
                }
            } catch (e) { /* debug not loaded */ }
        }

        window.addEventListener('chatbot-structured-response', function (event) {
            try {
                var detail = event && event.detail ? event.detail : null;
                tableDebugLog('listener fired', { hasDetail: !!detail, hasPayload: !!(detail && detail.payload), type: detail && detail.payload ? (detail.payload.type || 'unknown') : '-' });
                if (!detail || !detail.payload) {
                    tableDebugLog('event skipped: no detail or payload');
                    return;
                }
                var onImmersivePage = document.body && document.body.classList.contains('chat-immersive');
                if (!detail.immersive && !onImmersivePage) {
                    tableDebugLog('event skipped: not immersive', { detailImmersive: !!detail.immersive, onImmersivePage: !!onImmersivePage });
                    return;
                }
                var wrapper = detail.wrapperElement;
                var messageEl = detail.messageElement;
                var payload = detail.payload;
                var ttype = payload && payload.type ? String(payload.type).toLowerCase() : '';
                tableDebugLog('event received', {
                    ttype: ttype,
                    hasWrapper: !!wrapper,
                    wrapperInDOM: !!(wrapper && wrapper.parentElement),
                    wrapperIndex: wrapper && wrapper.getAttribute ? wrapper.getAttribute('data-message-index') : null,
                    hasMessageEl: !!messageEl,
                    messageElInDOM: !!(messageEl && messageEl.parentElement),
                    botWrappersInPage: document.querySelectorAll('#chatMessages .chat-message-wrapper').length
                });
                if (ttype === 'data_table') {
                    renderDataTableCard(payload, wrapper, messageEl);
                } else if (ttype === 'worldmap' || ttype === 'world_map' || ttype === 'choropleth') {
                    if (window.ngodbChatImmersiveMapDebug) {
                        try {
                            var pCountries = payload && Array.isArray(payload.countries) ? payload.countries : [];
                            var sampleC = pCountries.slice(0, 3);
                            var withReg = pCountries.filter(function (r) { return r && r.region; }).length;
                            console.log('[Immersive map] received payload type=', ttype, 'countries=', pCountries.length, 'withRegion=', withReg, 'sample', JSON.stringify(sampleC));
                        } catch (e) { /* ignore */ }
                    }
                    var rendered = renderMapCard(payload, wrapper, messageEl);
                    if (!rendered) scheduleMapRenderRetry(payload, wrapper, 0, messageEl);
                } else if (ttype === 'line' || ttype === 'linechart' || ttype === 'timeseries') {
                    renderChartCard(payload, wrapper, messageEl);
                } else if (ttype === 'bar' || ttype === 'barchart') {
                    renderBarChartCard(payload, wrapper, messageEl);
                } else if (ttype === 'pie' || ttype === 'donut') {
                    renderPieChartCard(payload, wrapper, messageEl);
                }
            } catch (e) { /* ignore */ }
        });
        try {
            if (window.debug && window.debug.getConfig && window.debug.getConfig().modules.chatbot) {
                console.log('[Chatbot tables] chat-immersive.js loaded; chatbot-structured-response listener registered');
            }
        } catch (e) { /* debug not loaded */ }

        window.addEventListener('chatbot-immersive-updated', function () {
            sidebarRunningLog('chatbot-immersive-updated received, re-rendering sidebar');
            applySearchFilter();
            renderChatList();
        });

        document.addEventListener('visibilitychange', function () {
            if (document.visibilityState === 'visible' && getChatbot()) {
                renderChatList();
            }
        });

        // Re-render when chatbot might have just initialized (e.g. after a short delay)
        setTimeout(function () {
            if (getChatbot()) renderChatList();
        }, 100);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
