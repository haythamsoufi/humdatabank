/**
 * Floating chatbot structured-payload renderer
 * @module chatbot/structured-payloads
 */

export function registerStructuredPayloadListener() {
    function isImmersivePage() {
        return !!(document.body && document.body.classList.contains('chat-immersive'));
    }

    // Find the .chat-message-content element to inject the card into.
    function resolveContentEl(messageElement, wrapperElement) {
        if (messageElement && messageElement.querySelector) {
            var c = messageElement.querySelector('.chat-message-content');
            if (c) return c;
        }
        if (wrapperElement && wrapperElement.querySelector) {
            var c2 = wrapperElement.querySelector('.chat-message.bot .chat-message-content');
            if (c2) return c2;
            // Fallback: last bot message in #chatMessages
            var msgs = document.querySelectorAll('#chatMessages .chat-message-wrapper:not(.is-user)');
            if (msgs.length) {
                var last = msgs[msgs.length - 1];
                var c3 = last.querySelector('.chat-message-content');
                if (c3) return c3;
            }
        }
        return null;
    }

    // Card shell shared by all types
    function makeCard(extraClass) {
        var card = document.createElement('div');
        card.className = 'chat-floating-payload-card' + (extraClass ? ' ' + extraClass : '');
        card.style.cssText = [
            'margin:10px 0 4px',
            'border:1px solid var(--humdb-border,#e2e8f0)',
            'border-radius:10px',
            'overflow:hidden',
            'background:var(--humdb-card-bg,#fff)',
            'font-size:13px'
        ].join(';');
        return card;
    }

    function makeCardHeader(titleText, extraContent) {
        var header = document.createElement('div');
        header.style.cssText = [
            'padding:8px 12px',
            'display:flex',
            'align-items:center',
            'justify-content:space-between',
            'gap:8px',
            'border-bottom:1px solid var(--humdb-border,#e2e8f0)',
            'background:var(--humdb-card-header-bg,#f8fafc)'
        ].join(';');
        var titleEl = document.createElement('span');
        titleEl.style.cssText = 'font-weight:600;font-size:13px;color:var(--humdb-text,#1e293b);flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
        titleEl.textContent = titleText || '';
        header.appendChild(titleEl);
        if (extraContent) header.appendChild(extraContent);
        return { header: header, titleEl: titleEl };
    }

    function buildFloatingTableExportRows(columns, rows) {
        var safeColumns = Array.isArray(columns) ? columns : [];
        var safeRows = Array.isArray(rows) ? rows : [];
        if (!safeColumns.length || !safeRows.length) return [];
        var out = [];
        out.push(safeColumns.map(function (c) {
            return String((c && (c.label || c.key)) || '').trim();
        }));
        safeRows.forEach(function (row) {
            out.push(safeColumns.map(function (c) {
                var key = c && c.key ? c.key : '';
                var value = row && key ? row[key] : '';
                return value == null ? '' : String(value);
            }));
        });
        return out;
    }

    async function downloadFloatingTableAsExcel(columns, rows, fileBase) {
        var exportRows = buildFloatingTableExportRows(columns, rows);
        if (!exportRows.length) return false;
        var exportFetch = (window.getFetch && window.getFetch()) || fetch;
        var filename = (fileBase || 'data-table') + '.xlsx';
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
            if (!res.ok) throw new Error('Excel export failed: ' + res.status);
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

    // Render a compact data table card inside the floating chatbot.
    function renderFloatingTableCard(payload, contentEl) {
        if (!payload || !Array.isArray(payload.rows) || !payload.rows.length) return;
        if (contentEl.querySelector('.chat-floating-payload-card')) return; // dedup

        var columns = Array.isArray(payload.columns) ? payload.columns : [];
        var allRows = payload.rows.slice();
        var sortBy = payload.sort_by || (columns.length ? columns[0].key : '');
        var sortOrder = payload.sort_order || 'desc';
        var columnWidthByKey = {};
        (function computeColumnWidths() {
            var sampleRows = allRows.slice(0, 180);
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
                var weighted = Math.max(labelLen, Math.min(70, Math.round((avgLen * 1.2) + (maxLen * 0.35))));
                var isNumericCol = col.type === 'number' || col.type === 'percent';
                var baseMin = isNumericCol ? 86 : (isLinkishCol ? 92 : 100);
                var baseMax = isNumericCol ? 170 : (isLinkishCol ? 180 : 250);
                var minWidth = Math.round(Math.max(baseMin, Math.min(baseMax, 50 + (weighted * (isNumericCol ? 2.7 : 3.8)))));
                var maxWidth = Math.round(Math.max(minWidth + 24, Math.min(isLinkishCol ? 210 : 300, minWidth + (isNumericCol ? 40 : (isLinkishCol ? 40 : 85)))));
                columnWidthByKey[key] = {
                    min: minWidth,
                    max: maxWidth
                };
            });
        })();

        var card = makeCard('chat-floating-table-card');

        // Search + export controls
        var searchInput = document.createElement('input');
        searchInput.type = 'search';
        searchInput.placeholder = 'Filter\u2026';
        searchInput.style.cssText = 'padding:3px 7px;border:1px solid var(--humdb-border,#cbd5e1);border-radius:5px;font-size:12px;width:120px;outline:none;flex-shrink:0;';
        var downloadBtn = document.createElement('button');
        downloadBtn.type = 'button';
        downloadBtn.className = 'chat-floating-table-export-btn';
        downloadBtn.textContent = 'Excel';
        downloadBtn.setAttribute('aria-label', 'Download table as Excel');
        downloadBtn.title = 'Download table as Excel';
        downloadBtn.style.cssText = 'padding:3px 8px;border:1px solid var(--humdb-border,#cbd5e1);border-radius:5px;font-size:12px;background:#fff;color:var(--humdb-text,#1e293b);cursor:pointer;flex-shrink:0;';
        var controls = document.createElement('div');
        controls.style.cssText = 'display:flex;align-items:center;gap:6px;';
        controls.appendChild(searchInput);
        controls.appendChild(downloadBtn);

        var hObj = makeCardHeader((payload.title || 'Data Table') + ' (' + allRows.length + ' rows)', controls);
        var titleEl = hObj.titleEl;
        card.appendChild(hObj.header);

        var tableWrap = document.createElement('div');
        tableWrap.style.cssText = 'overflow-x:auto;max-height:300px;overflow-y:auto;';
        var table = document.createElement('table');
        table.style.cssText = 'min-width:100%;border-collapse:collapse;font-size:12px;';

        var thead = document.createElement('thead');
        var headRow = document.createElement('tr');
        headRow.style.cssText = 'position:sticky;top:0;background:var(--humdb-card-header-bg,#f1f5f9);z-index:1;';
        columns.forEach(function (col) {
            var th = document.createElement('th');
            th.dataset.key = col.key;
            var w = columnWidthByKey[col.key] || { min: 100, max: 280 };
            th.style.cssText = 'padding:6px 8px;text-align:left;font-weight:600;font-size:11px;color:var(--humdb-text-muted,#64748b);border-bottom:2px solid var(--humdb-border,#e2e8f0);cursor:pointer;user-select:none;white-space:normal;word-wrap:break-word;overflow-wrap:anywhere;word-break:break-word;min-width:' + w.min + 'px;max-width:' + w.max + 'px;';
            th.textContent = col.label || col.key;
            if (col.sortable !== false) {
                var arrow = document.createElement('span');
                arrow.className = 'sort-arrow';
                arrow.style.cssText = 'margin-left:3px;font-size:9px;opacity:0.4;';
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
        contentEl.appendChild(card);

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
                if (isNum) { va = Number(va) || 0; vb = Number(vb) || 0; }
                else { va = String(va).toLowerCase(); vb = String(vb).toLowerCase(); }
                var cmp = va < vb ? -1 : va > vb ? 1 : 0;
                return sortOrder === 'asc' ? cmp : -cmp;
            });
            tbody.innerHTML = '';
            var even = false;
            filtered.forEach(function (row) {
                var tr = document.createElement('tr');
                tr.style.cssText = even ? 'background:var(--humdb-row-alt,#f8fafc);' : '';
                even = !even;
                columns.forEach(function (col) {
                    var td = document.createElement('td');
                    var w = columnWidthByKey[col.key] || { min: 100, max: 280 };
                    td.style.cssText = 'padding:5px 8px;border-bottom:1px solid var(--humdb-border,#f1f5f9);white-space:normal;word-wrap:break-word;overflow-wrap:anywhere;word-break:break-word;min-width:' + w.min + 'px;max-width:' + w.max + 'px;';
                    var val = row[col.key];
                    var isNumeric = (col.type === 'number' || col.type === 'percent') && val != null && Number.isFinite(Number(val));
                    if (col.type === 'link' && val) {
                        var urlKey = col.url_key || (col.key + '_url');
                        var href = row[urlKey];
                        if (href) {
                            var a = document.createElement('a');
                            a.href = href; a.target = '_blank'; a.rel = 'noopener';
                            a.textContent = String(val);
                            a.style.cssText = 'color:var(--humdb-link,#2563eb);text-decoration:none;display:inline-block;max-width:100%;white-space:normal;word-wrap:break-word;overflow-wrap:anywhere;word-break:break-word;';
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

        downloadBtn.addEventListener('click', async function () {
            var base = ((payload.title || 'data-table') + '-table')
                .toLowerCase()
                .replace(/[^a-z0-9]+/g, '-')
                .replace(/^-+|-+$/g, '') || 'data-table';
            downloadBtn.disabled = true;
            var original = downloadBtn.textContent;
            var ok = await downloadFloatingTableAsExcel(columns, allRows, base);
            downloadBtn.textContent = ok ? 'Done' : 'Failed';
            setTimeout(function () {
                downloadBtn.textContent = original;
                downloadBtn.disabled = false;
            }, 1200);
        });
        renderRows();
    }

    // Render a summary card for maps and charts (need full page to show interactive viz).
    function renderFloatingVizSummaryCard(payload, contentEl, type) {
        if (contentEl.querySelector('.chat-floating-payload-card')) return; // dedup

        var typeLabels = {
            worldmap: 'World Map', world_map: 'World Map', choropleth: 'World Map',
            line: 'Line Chart', linechart: 'Line Chart', timeseries: 'Line Chart',
            bar: 'Bar Chart', barchart: 'Bar Chart',
            pie: 'Pie Chart', donut: 'Donut Chart'
        };
        var typeIcons = {
            worldmap: 'fa-globe', world_map: 'fa-globe', choropleth: 'fa-globe',
            line: 'fa-chart-line', linechart: 'fa-chart-line', timeseries: 'fa-chart-line',
            bar: 'fa-chart-bar', barchart: 'fa-chart-bar',
            pie: 'fa-chart-pie', donut: 'fa-chart-pie'
        };
        var label = typeLabels[type] || 'Visualization';
        var icon = typeIcons[type] || 'fa-chart-bar';
        var title = payload.title || label;

        var card = makeCard('chat-floating-viz-card');

        var hObj = makeCardHeader(title);
        card.appendChild(hObj.header);

        var body = document.createElement('div');
        body.style.cssText = 'padding:10px 12px;display:flex;flex-direction:column;gap:8px;';

        // Brief metadata line
        var meta = document.createElement('div');
        meta.style.cssText = 'display:flex;align-items:center;gap:6px;color:var(--humdb-text-muted,#64748b);font-size:12px;';
        var iconEl = document.createElement('i');
        iconEl.className = 'fas ' + icon;
        iconEl.setAttribute('aria-hidden', 'true');
        meta.appendChild(iconEl);

        var metaText = document.createTextNode(label);
        meta.appendChild(metaText);

        if (payload.metric) {
            var sep = document.createTextNode(' \u00B7 ');
            meta.appendChild(sep);
            var metricSpan = document.createElement('span');
            metricSpan.textContent = payload.metric;
            meta.appendChild(metricSpan);
        }

        if (type === 'worldmap' || type === 'world_map' || type === 'choropleth') {
            var countries = Array.isArray(payload.countries) ? payload.countries : [];
            if (countries.length) {
                var countEl = document.createTextNode(' \u00B7 ' + countries.length + ' countries');
                meta.appendChild(countEl);
            }
        } else if (Array.isArray(payload.series)) {
            var pts = document.createTextNode(' \u00B7 ' + payload.series.length + ' data points');
            meta.appendChild(pts);
        }

        body.appendChild(meta);

        // "Open in full view" hint
        var immersiveUrl = (function () {
            try {
                var el = document.querySelector('#aiChatWidget');
                return el ? el.getAttribute('data-immersive-url') : null;
            } catch (_) { return null; }
        })();

        var hint = document.createElement('div');
        hint.style.cssText = 'font-size:12px;color:var(--humdb-text-muted,#64748b);';
        if (immersiveUrl) {
            hint.appendChild(document.createTextNode('Interactive visualization available in '));
            var fullViewLink = document.createElement('a');
            fullViewLink.href = immersiveUrl;
            fullViewLink.target = '_blank';
            fullViewLink.rel = 'noopener';
            fullViewLink.textContent = 'full view';
            fullViewLink.style.cssText = 'color:var(--humdb-link,#2563eb);text-decoration:underline;';
            hint.appendChild(fullViewLink);
            hint.appendChild(document.createTextNode('.'));
        } else {
            hint.textContent = 'Open the full view to see the interactive visualization.';
        }
        body.appendChild(hint);

        card.appendChild(body);
        contentEl.appendChild(card);
    }

    window.addEventListener('chatbot-structured-response', function (event) {
        try {
            if (isImmersivePage()) return; // chatbot/immersive.js handles this
            var detail = event && event.detail ? event.detail : null;
            if (!detail || !detail.payload) return;
            var payload = detail.payload;
            var type = String(payload.type || '').toLowerCase();
            var contentEl = resolveContentEl(detail.messageElement, detail.wrapperElement);
            if (!contentEl) return;

            if (type === 'data_table') {
                renderFloatingTableCard(payload, contentEl);
            } else if (
                type === 'worldmap' || type === 'world_map' || type === 'choropleth' ||
                type === 'line' || type === 'linechart' || type === 'timeseries' ||
                type === 'bar' || type === 'barchart' ||
                type === 'pie' || type === 'donut'
            ) {
                renderFloatingVizSummaryCard(payload, contentEl, type);
            }
        } catch (e) { /* never break the chatbot */ }
    });

}
