/* UPR Analysis — PNS support flow map.
 *
 * Draws a Power BI-style flow map on the Analysis tab. For every Participating
 * National Society (the source) all its support lines merge into one thick trunk
 * at the society, split into grouped branches that head toward clusters of
 * nearby supported countries, and only separate into single lines close to each
 * country — a per-source flow tree, not independent arcs.
 *
 * How the bundling works (all client-side, from the server's nodes/edges):
 *   1. Group a source's destinations and hierarchically cluster them by
 *      geographic proximity (agglomerative, centroid linkage) into a binary tree.
 *   2. Give every cluster a "merge point" pulled from its parent toward the
 *      cluster centroid, so the tree fans out from the source.
 *   3. Emit one tapering segment per tree edge (width = downstream weight),
 *      smoothed with a Catmull-Rom spline. Shared tree edges are drawn once, so
 *      branches read as merged bundles.
 *
 * The year control shows one calendar year at a time. A plan and a report in
 * that year are a single link. Geometry and tiles come from the server
 * (plugins/upr/flow.py via /admin/data-exploration/upr-impact/flows). Leaflet
 * handles pan/zoom repositioning of the polylines natively. */
(function () {
    'use strict';

    var CFG = window.UprFlowConfig || {};
    var panel = document.getElementById('panel-upr-impact');
    var embed = document.getElementById('upri-flow-embed');
    var root = embed || panel;
    if (!root) return;

    var UI = (window.UprImpactConfig && window.UprImpactConfig.ui) || CFG.ui || {};
    if (embed && embed.getAttribute('data-ui')) {
        try { UI = JSON.parse(embed.getAttribute('data-ui')); } catch (e) { /* keep defaults */ }
    }
    var preset = {
        year: embed ? embed.getAttribute('data-year') : '',
        pns: embed ? (embed.getAttribute('data-pns') || '') : '',
        recipient: embed ? (embed.getAttribute('data-recipient') || '') : ''
    };

    var RED = '#f5333f';     // IFRC red
    var NAVY = '#011e41';    // IFRC navy
    var TRUNK = 0.4;         // how far the first merge point sits from the source (0..1)
    var SPLIT = 0.68;        // how far each branch merge point sits toward its cluster
    var CM_SAMPLES = 14;     // points sampled per tree edge

    function byId(id) { return document.getElementById(id); }

    var els = {
        host: byId('upri-flow-map'),
        loading: byId('upri-flow-loading'),
        error: byId('upri-flow-error'),
        empty: byId('upri-flow-empty'),
        note: byId('upri-flow-note'),
        reset: byId('upri-flow-reset'),
        year: byId('upri-flow-year'),
        pns: byId('upri-flow-pns'),
        recipient: byId('upri-flow-recipient'),
        filters: byId('upri-flow-filters'),
        clearFilters: byId('upri-flow-filters-clear'),
        region: byId('upri-region'),
        refresh: byId('upri-refresh')
    };
    if (!els.host) return;

    var map = null;
    var tileLayer = null;
    var edgesLayer = null;
    var nodesLayer = null;
    var state = {
        allNodes: [], allEdges: [], nodes: [], edges: [], byIso: {}, segments: [],
        years: [], year: preset.year ? parseInt(preset.year, 10) || null : null,
        figures: [], areaLabels: [], tiles: {}, nodeByIso: {}, filtersReady: false,
        focusKey: null, pinnedKey: null, pinnedLayer: null, applying: false, request: 0, loaded: false,
        tileToken: 0
    };
    var settleTimer = null;
    var resizeTimer = null;
    var settling = false;

    var clearTimer = null;

    function show(el, visible) { if (el) el.hidden = !visible; }

    function setState(name) {
        show(els.loading, name === 'loading');
        show(els.error, name === 'error');
        show(els.empty, name === 'empty');
        show(els.host, name === 'content');
        show(els.reset, name === 'content');
        show(els.filters, name === 'content' || name === 'empty');
    }

    function fill(text, values) {
        text = text || '';
        Object.keys(values || {}).forEach(function (k) {
            text = text.split('{' + k + '}').join(String(values[k]));
        });
        return text;
    }

    function plural(n, oneKey, manyKey, values) {
        var data = values || {};
        data.n = n;
        return fill(UI[Number(n) === 1 ? oneKey : manyKey], data);
    }

    function escapeHtml(s) {
        return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
        });
    }

    function nodeTotal(node) { return (node.out_weight || 0) + (node.in_weight || 0); }

    function roundYear(code) {
        var match = /^(?:P|MYR|AR)(\d{2})$/.exec(String(code || '').toUpperCase());
        return match ? 2000 + parseInt(match[1], 10) : null;
    }

    // One donor → host link for the selected year, even when that year has
    // both a plan and a report.
    function edgesForYear(year) {
        return state.allEdges.filter(function (edge) {
            return (edge.years || []).indexOf(year) !== -1;
        }).map(function (edge) {
            var rounds = (edge.rounds || []).filter(function (code) { return roundYear(code) === year; });
            return {
                from: edge.from,
                to: edge.to,
                weight: 1,
                rounds: rounds,
                latest_round: rounds.length ? rounds[rounds.length - 1] : null
            };
        });
    }

    function nodesForEdges(edges) {
        var weights = {};
        edges.forEach(function (edge) {
            if (!weights[edge.from]) weights[edge.from] = { out: 0, inn: 0 };
            if (!weights[edge.to]) weights[edge.to] = { out: 0, inn: 0 };
            weights[edge.from].out += edge.weight;
            weights[edge.to].inn += edge.weight;
        });
        return state.allNodes.filter(function (node) { return weights[node.iso3]; }).map(function (node) {
            var weight = weights[node.iso3];
            return {
                iso3: node.iso3,
                iso2: node.iso2,
                name: node.name,
                region: node.region,
                lat: node.lat,
                lng: node.lng,
                out_weight: weight.out,
                in_weight: weight.inn,
                role: weight.out && weight.inn ? 'both' : (weight.out ? 'donor' : 'host')
            };
        });
    }

    function partyIso(edges, key, iso) {
        if (!iso) return '';
        for (var i = 0; i < edges.length; i++) {
            if (edges[i][key] === iso) return iso;
        }
        return '';
    }

    function fillPartySelect(select, edges, key, previous) {
        if (!select) return;
        var seen = {};
        var rows = [];
        edges.forEach(function (edge) {
            var iso = edge[key];
            if (!iso || seen[iso]) return;
            seen[iso] = true;
            var node = state.nodeByIso[iso];
            rows.push({ iso: iso, name: (node && node.name) || iso });
        });
        rows.sort(function (a, b) { return a.name.localeCompare(b.name); });
        select.replaceChildren();
        var all = document.createElement('option');
        all.value = '';
        all.textContent = UI.flow_all || 'All';
        select.appendChild(all);
        rows.forEach(function (row) {
            var option = document.createElement('option');
            option.value = row.iso;
            option.textContent = row.name;
            select.appendChild(option);
        });
        select.value = previous && seen[previous] ? previous : '';
    }

    function chosenParty(select, fallback) {
        if (!state.filtersReady && fallback) return fallback;
        return (select && select.value) || '';
    }

    function refreshPartyFilters(pool) {
        var pnsPref = partyIso(pool, 'from', chosenParty(els.pns, preset.pns));
        var recipientPref = partyIso(pool, 'to', chosenParty(els.recipient, preset.recipient));
        var donorEdges = recipientPref ? pool.filter(function (edge) { return edge.to === recipientPref; }) : pool;
        var hostEdges = pnsPref ? pool.filter(function (edge) { return edge.from === pnsPref; }) : pool;
        fillPartySelect(els.pns, donorEdges, 'from', pnsPref);
        fillPartySelect(els.recipient, hostEdges, 'to', recipientPref);
        state.filtersReady = true;
    }

    function defaultYear() {
        var fromLink = preset.year ? parseInt(preset.year, 10) : null;
        if (fromLink && state.years.indexOf(fromLink) !== -1) return fromLink;
        return state.years[0] || null;
    }

    function filtersApplied() {
        var year = parseInt(els.year && els.year.value, 10);
        var pns = (els.pns && els.pns.value) || '';
        var recipient = (els.recipient && els.recipient.value) || '';
        var base = defaultYear();
        return !!(pns || recipient || (base && year && year !== base));
    }

    function updateClearFilters() {
        if (!els.clearFilters) return;
        els.clearFilters.hidden = !filtersApplied();
    }

    function clearFilters() {
        var year = defaultYear();
        var yearChanged = !!(els.year && year && String(els.year.value) !== String(year));
        if (els.year && year) {
            els.year.value = String(year);
            state.year = year;
        }
        if (els.pns) els.pns.value = '';
        if (els.recipient) els.recipient.value = '';
        if (yearChanged && els.year) els.year.dispatchEvent(new Event('change', { bubbles: true }));
        else if (state.loaded && state.allEdges.length) applyYear();
        else updateClearFilters();
    }

    function populateYears(years) {
        if (!els.year) return;
        var previous = state.year;
        var list = (years || []).slice().sort(function (a, b) { return b - a; });
        state.years = list;
        els.year.replaceChildren();
        list.forEach(function (year) {
            var option = document.createElement('option');
            option.value = String(year);
            option.textContent = String(year);
            els.year.appendChild(option);
        });
        var pick = list.indexOf(previous) !== -1 ? previous : list[0];
        state.year = pick == null ? null : pick;
        if (pick != null) els.year.value = String(pick);
        if (document.querySelector('[data-follow-year="upri-flow-year"]')) {
            els.year.dispatchEvent(new Event('change', { bubbles: true }));
        }
    }

    // Longitudes on a line should stay within 180° of each other, so a hop
    // across the date line (Australia → Tonga) does not travel the long way
    // around the world.
    function nearLng(lng, origin) {
        var x = lng;
        while (x - origin > 180) x -= 360;
        while (origin - x > 180) x += 360;
        return x;
    }

    function wrapLng(lng) {
        return ((lng + 180) % 360 + 360) % 360 - 180;
    }

    // --- Flow tree -------------------------------------------------------

    // Agglomerative clustering (weighted centroid linkage) of a source's
    // destinations into a binary tree of clusters.
    function clusterTree(leaves) {
        var nodes = leaves.map(function (l) {
            return {
                leaf: true, edge: l.edge, host: l.dest, weight: l.weight,
                clat: l.lat, clng: l.lng, destSet: [l.dest]
            };
        });
        while (nodes.length > 1) {
            var bi = 0, bj = 1, best = Infinity;
            for (var i = 0; i < nodes.length; i++) {
                for (var j = i + 1; j < nodes.length; j++) {
                    var dLat = nodes[i].clat - nodes[j].clat;
                    var dLng = nearLng(nodes[j].clng, nodes[i].clng) - nodes[i].clng;
                    var d = dLat * dLat + dLng * dLng;
                    if (d < best) { best = d; bi = i; bj = j; }
                }
            }
            var a = nodes[bi], b = nodes[bj], w = a.weight + b.weight;
            var bLng = nearLng(b.clng, a.clng);
            var parent = {
                leaf: false, children: [a, b], weight: w,
                clat: (a.clat * a.weight + b.clat * b.weight) / w,
                clng: (a.clng * a.weight + bLng * b.weight) / w,
                destSet: a.destSet.concat(b.destSet)
            };
            nodes.splice(bj, 1);
            nodes.splice(bi, 1);
            nodes.push(parent);
        }
        return nodes[0];
    }

    // Pull each cluster's merge point from its parent toward the cluster centroid.
    function assignMerge(node, up, isRoot) {
        if (node.leaf) { node.point = [node.clat, nearLng(node.clng, up[1])]; return; }
        var ratio = isRoot ? TRUNK : SPLIT;
        node.point = [
            up[0] + (node.clat - up[0]) * ratio,
            up[1] + (nearLng(node.clng, up[1]) - up[1]) * ratio
        ];
        node.children.forEach(function (c) { assignMerge(c, node.point, false); });
    }

    function heaviestChild(node) {
        return node.children[0].weight >= node.children[1].weight ? node.children[0] : node.children[1];
    }

    // One segment per tree edge, carrying the tangent neighbours for smoothing.
    function emit(node, parentPoint, grandPoint, source, out) {
        out.push({
            source: source.iso3,
            destSet: node.destSet,
            weight: node.weight,
            leaf: !!node.leaf,
            edge: node.leaf ? node.edge : null,
            host: node.leaf ? node.host : null,
            p0: grandPoint, p1: parentPoint, p2: node.point,
            p3: node.leaf ? node.point : heaviestChild(node).point
        });
        if (!node.leaf) {
            node.children.forEach(function (c) { emit(c, node.point, parentPoint, source, out); });
        }
    }

    function buildSegments() {
        var bySource = {};
        state.edges.forEach(function (e) {
            var from = state.byIso[e.from], to = state.byIso[e.to];
            if (!from || !to) return;
            if (!bySource[e.from]) bySource[e.from] = { source: from, leaves: [] };
            bySource[e.from].leaves.push({ dest: e.to, edge: e, weight: e.weight, lat: to.lat, lng: to.lng });
        });
        var segs = [];
        Object.keys(bySource).forEach(function (k) {
            var grp = bySource[k], S = grp.source, start = [S.lat, S.lng];
            var root = clusterTree(grp.leaves);
            assignMerge(root, start, true);
            emit(root, start, start, S, segs);
        });
        return segs;
    }

    // Catmull-Rom spline between p1 and p2, using p0/p3 as tangent neighbours.
    function catmullPoints(s) {
        var origin = s.p1[1];
        var p0 = [s.p0[0], nearLng(s.p0[1], origin)];
        var p1 = [s.p1[0], nearLng(s.p1[1], origin)];
        var p2 = [s.p2[0], nearLng(s.p2[1], p1[1])];
        var p3 = [s.p3[0], nearLng(s.p3[1], p2[1])];
        var out = [];
        for (var k = 0; k <= CM_SAMPLES; k++) {
            var t = k / CM_SAMPLES, t2 = t * t, t3 = t2 * t;
            out.push([
                0.5 * (2 * p1[0] + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3),
                0.5 * (2 * p1[1] + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            ]);
        }
        return out;
    }

    // A short path that crosses the date line is drawn as two pieces, one
    // leaving each edge of the map, instead of one line across every continent.
    function dateLineBetween(a, b) {
        var lo = Math.min(a, b), hi = Math.max(a, b);
        var boundary = 180 + 360 * Math.ceil((lo - 180) / 360);
        return boundary > lo && boundary <= hi ? boundary : null;
    }

    function splitAntimeridian(points) {
        var parts = [];
        var part = [];
        points.forEach(function (p, i) {
            if (!part.length) {
                part.push([p[0], wrapLng(p[1])]);
                return;
            }
            var prev = points[i - 1];
            var boundary = dateLineBetween(prev[1], p[1]);
            if (boundary == null) {
                part.push([p[0], wrapLng(p[1])]);
                return;
            }
            var east = p[1] > prev[1];
            var t = (boundary - prev[1]) / (p[1] - prev[1]);
            var latEdge = prev[0] + (p[0] - prev[0]) * t;
            part.push([latEdge, east ? 180 : -180]);
            parts.push(part);
            part = [[latEdge, east ? -180 : 180], [p[0], wrapLng(p[1])]];
        });
        if (part.length) parts.push(part);
        return parts.filter(function (piece) { return piece.length > 1; });
    }

    // --- Map -------------------------------------------------------------

    function addTiles(tiles) {
        var opts = {
            maxZoom: tiles.max_zoom || 19,
            attribution: tiles.attribution || ''
        };
        if (tiles.subdomains) opts.subdomains = tiles.subdomains;
        if (tiles.tile_size) opts.tileSize = tiles.tile_size;
        if (tiles.zoom_offset != null) opts.zoomOffset = tiles.zoom_offset;
        // One copy of the world. Without this, a wide map repeats the tiles.
        opts.noWrap = true;
        // A zoom that starts while the previous tiles are still fading leaves
        // those tiles transparent, so the gray map background shows through.
        opts.fadeAnimation = false;
        opts.updateWhenIdle = true;
        tileLayer = window.L.tileLayer(tiles.url, opts).addTo(map);
        tileLayer.on('load', function () { window.setTimeout(repairTiles, 0); });
    }

    function mapSized() {
        return !!(els.host && els.host.clientWidth > 1 && els.host.clientHeight > 1);
    }

    // The world is 256 * 2^zoom pixels wide. Keep zoom high enough that one
    // world covers the map, so zooming out cannot reveal a second copy.
    // ``allowZoom`` is false when a fit is about to choose the zoom itself.
    function keepSingleWorld(allowZoom) {
        if (!map || !mapSized()) return;
        var width = map.getSize().x;
        if (!width) return;
        var minZoom = Math.max(1, Math.ceil(Math.log(width / 256) / Math.LN2));
        if (map.getMinZoom() !== minZoom) map.setMinZoom(minZoom);
        if (allowZoom !== false && map.getZoom() < minZoom) map.setZoom(minZoom);
    }

    // True when loaded tiles reach every edge of the frame. A size change
    // mid-load leaves a gray band where tiles were never requested.
    function tilesCoverView() {
        if (!map) return true;
        var pane = map.getPane('tilePane');
        if (!pane) return false;
        var imgs = pane.querySelectorAll('img.leaflet-tile');
        if (!imgs.length) return false;
        var view = map.getContainer().getBoundingClientRect();
        var left = Infinity, top = Infinity, right = -Infinity, bottom = -Infinity;
        var pending = false;
        Array.prototype.forEach.call(imgs, function (img) {
            if (!img.complete || !img.naturalWidth) { pending = true; return; }
            var box = img.getBoundingClientRect();
            if (box.width < 2 || box.height < 2) return;
            left = Math.min(left, box.left);
            top = Math.min(top, box.top);
            right = Math.max(right, box.right);
            bottom = Math.max(bottom, box.bottom);
        });
        if (pending || left === Infinity) return true;
        var slack = 4;
        return left <= view.left + slack && top <= view.top + slack
            && right >= view.right - slack && bottom >= view.bottom - slack;
    }

    function repairTiles() {
        if (!map || !tileLayer || !mapSized() || tilesCoverView()) return;
        if (state.tileToken < 0 || state.tileToken >= 2) return;
        var token = state.tileToken;
        state.tileToken = -1;
        settling = true;
        try { map.invalidateSize({ animate: false, pan: false }); }
        finally { settling = false; }
        tileLayer.redraw();
        window.setTimeout(function () {
            state.tileToken = token + 1;
            if (token + 1 < 2 && !tilesCoverView()) repairTiles();
        }, 500);
    }

    function settleView(refit) {
        if (!map || !mapSized()) return false;
        settling = true;
        try {
            var size = map.getSize();
            var width = els.host.clientWidth;
            var height = els.host.clientHeight;
            if (Math.abs(size.x - width) > 1 || Math.abs(size.y - height) > 1) {
                map.invalidateSize({ animate: false, pan: false });
            }
            keepSingleWorld(!refit);
            if (refit) fitToNodes();
        } finally {
            settling = false;
        }
        return true;
    }

    function scheduleSettle(refit) {
        if (settleTimer) window.clearTimeout(settleTimer);
        var tries = 0;
        function attempt() {
            settleTimer = null;
            var created = !map;
            if (!map && window.L && mapSized()) ensureMap(state.tiles || {});
            if (map && created) draw();
            if (settleView(refit) || tries >= 24) return;
            tries += 1;
            settleTimer = window.setTimeout(attempt, 50);
        }
        settleTimer = window.setTimeout(attempt, 0);
    }

    function ensureMap(tiles) {
        if (map || !mapSized()) return;
        map = window.L.map(els.host, {
            center: [25, 10],
            zoom: 2,
            minZoom: 1,
            maxBounds: window.L.latLngBounds([[-85, -180], [85, 180]]),
            maxBoundsViscosity: 1,
            worldCopyJump: false,
            scrollWheelZoom: true,
            zoomControl: false,
            fadeAnimation: false,
            zoomAnimation: false,
            markerZoomAnimation: false
        });
        map.on('resize', function () {
            if (settling) return;
            if (resizeTimer) window.clearTimeout(resizeTimer);
            resizeTimer = window.setTimeout(function () { settleView(false); }, 80);
        });
        if (window.ResizeObserver) {
            var observer = new ResizeObserver(function () {
                if (settling) return;
                if (resizeTimer) window.clearTimeout(resizeTimer);
                resizeTimer = window.setTimeout(function () { settleView(false); }, 80);
            });
            observer.observe(els.host);
        }
        if (map.attributionControl) map.attributionControl.setPrefix(false);
        window.L.control.zoom({ position: 'bottomright' }).addTo(map);
        addTiles(tiles);
        edgesLayer = window.L.layerGroup().addTo(map);
        nodesLayer = window.L.layerGroup().addTo(map);
        // Hover preview clears when the pointer leaves a line. A click pins that
        // highlight until the next click on empty map.
        var container = map.getContainer();
        container.addEventListener('pointermove', function (ev) {
            if (state.pinnedKey) return;
            if (overFlowShape(ev.target)) cancelClear();
            else scheduleClear();
        });
        container.addEventListener('pointerleave', function () {
            cancelClear();
            if (!state.pinnedKey) clearFocus();
        });
        map.on('click', function () {
            if (swallowMapClick) return;
            if (state.pinnedKey) clearFocus();
        });
    }

    function overFlowShape(target) {
        return !!(target && target.closest && target.closest('.leaflet-interactive, .upri-flow-tip'));
    }

    function cancelClear() {
        if (!clearTimer) return;
        window.clearTimeout(clearTimer);
        clearTimer = null;
    }

    function scheduleClear() {
        if (state.pinnedKey || !state.focusKey || clearTimer) return;
        clearTimer = window.setTimeout(function () {
            clearTimer = null;
            clearFocus();
        }, 40);
    }

    // --- Drawing ---------------------------------------------------------

    function nodeColor(node) {
        return node.role === 'host' ? NAVY : RED;
    }

    function segOpacity(s) { return s.leaf ? 0.6 : 0.45; }

    function draw() {
        if (!edgesLayer || !nodesLayer) return;
        cancelClear();
        state.focusKey = null;
        state.pinnedKey = null;
        state.pinnedLayer = null;
        edgesLayer.clearLayers();
        nodesLayer.clearLayers();
        state.byIso = {};
        state.nodes.forEach(function (n) { state.byIso[n.iso3] = n; });

        state.segments = buildSegments();
        var maxSub = 1, maxNode = 1;
        state.segments.forEach(function (s) { if (s.weight > maxSub) maxSub = s.weight; });
        state.nodes.forEach(function (n) { var t = nodeTotal(n); if (t > maxNode) maxNode = t; });
        var width = function (w) { return 1.0 + 7 * Math.sqrt(w / maxSub); };
        var radius = function (t) { return 3.5 + 9 * Math.sqrt(t / maxNode); };

        // Thick trunks first so thin leaf lines sit on top.
        state.segments.sort(function (a, b) { return b.weight - a.weight; });
        state.segments.forEach(function (s) {
            var style = {
                color: RED, weight: width(s.weight), opacity: segOpacity(s),
                lineCap: 'round', lineJoin: 'round'
            };
            s.lines = splitAntimeridian(catmullPoints(s)).map(function (pts) {
                return window.L.polyline(pts, style);
            });
            s.poly = s.lines[0] || null;
            s.lines.forEach(function (line) {
                line.addTo(edgesLayer);
                line.bindTooltip(segTooltip(s), { sticky: true, direction: 'top', className: 'upri-flow-tip' });
                line.on('mouseover', function () {
                    if (state.pinnedKey) return;
                    cancelClear();
                    // A shared branch is only the countries that have not split off yet.
                    // Hovering it still shows the whole society: the trunk near the
                    // source and the same line farther on (for example past India)
                    // highlight the same set. A final single line highlights that link.
                    if (s.leaf) focusSegment(s, line);
                    else focusSource(s.source, line);
                });
                line.on('click', function (ev) {
                    stopMapClick(ev);
                    pinSegment(s, line);
                });
                line.on('mouseout', function () {
                    if (state.pinnedLayer === line) line.openTooltip();
                });
            });
        });

        state.nodes.forEach(function (n) {
            n.marker = window.L.circleMarker([n.lat, n.lng], {
                radius: radius(nodeTotal(n)),
                color: '#fff', weight: 1, fillColor: nodeColor(n), fillOpacity: 0.95
            }).addTo(nodesLayer);
            var lines = ['<strong>' + escapeHtml(n.name) + '</strong>'];
            if (n.out_weight) lines.push(escapeHtml(plural(countEdges(n.iso3, 'from'), 'flow_node_gives_one', 'flow_node_gives')));
            if (n.in_weight) lines.push(escapeHtml(plural(countEdges(n.iso3, 'to'), 'flow_node_gets_one', 'flow_node_gets')));
            n.marker.bindTooltip(lines.join('<br>'), { direction: 'top', className: 'upri-flow-tip' });
            n.marker.on('mouseover', function () {
                if (state.pinnedKey) return;
                cancelClear();
                if (n.out_weight) focusSource(n.iso3, n.marker);
                else focusHost(n.iso3, n.marker);
            });
            n.marker.on('click', function (ev) {
                stopMapClick(ev);
                if (n.out_weight) pinSource(n.iso3, n.marker);
                else pinHost(n.iso3, n.marker);
            });
            n.marker.on('mouseout', function () {
                if (state.pinnedLayer === n.marker) n.marker.openTooltip();
            });
        });
    }

    function segTooltip(s) {
        var donor = state.byIso[s.source];
        var donorName = donor ? donor.name : s.source;
        if (s.leaf) {
            var host = state.byIso[s.host];
            return '<strong>' + escapeHtml(fill(UI.flow_tooltip_supports, {
                donor: donorName, host: host ? host.name : s.host
            })) + '</strong>';
        }
        return '<strong>' + escapeHtml(donorName) + '</strong><br>'
            + escapeHtml(plural(countEdges(s.source, 'from'), 'flow_node_gives_one', 'flow_node_gives'));
    }

    function countEdges(iso3, key) {
        var n = 0;
        state.edges.forEach(function (e) { if (e[key] === iso3) n++; });
        return n;
    }

    // --- Focus / hover ---------------------------------------------------

    function segLines(s) {
        return s.lines || (s.poly ? [s.poly] : []);
    }

    function dimAll() {
        state.segments.forEach(function (s) {
            segLines(s).forEach(function (line) { line.setStyle({ opacity: 0.05 }); });
        });
        state.nodes.forEach(function (n) { if (n.marker) n.marker.setStyle({ fillOpacity: 0.2, opacity: 0.2 }); });
    }

    function hiSeg(s) {
        segLines(s).forEach(function (line) { line.setStyle({ opacity: 0.95 }); });
    }

    function hiNode(iso3) {
        var n = state.byIso[iso3];
        if (n && n.marker) n.marker.setStyle({ fillOpacity: 1, opacity: 1 });
    }

    function closeTipsExcept(keep) {
        state.segments.forEach(function (s) {
            segLines(s).forEach(function (line) { if (line !== keep) line.closeTooltip(); });
        });
        state.nodes.forEach(function (n) {
            if (n.marker && n.marker !== keep) n.marker.closeTooltip();
        });
    }

    var swallowMapClick = false;

    function stopMapClick(ev) {
        swallowMapClick = true;
        if (ev && ev.originalEvent) window.L.DomEvent.stopPropagation(ev.originalEvent);
        window.setTimeout(function () { swallowMapClick = false; }, 0);
    }

    function covers(group, member) {
        for (var i = 0; i < member.length; i++) {
            if (group.indexOf(member[i]) === -1) return false;
        }
        return true;
    }

    // A leaf is one support link. A thicker branch is the group of links that
    // split off it. Highlight that branch, the countries on it, and the trunk
    // back to the supporting society.
    function focusSegment(seg, layer) {
        var key = 'seg:' + seg.source + ':' + seg.destSet.join(',');
        if (state.focusKey !== key) {
            state.focusKey = key;
            dimAll();
            hiNode(seg.source);
            seg.destSet.forEach(hiNode);
            state.segments.forEach(function (s) {
                if (s.source !== seg.source) return;
                if (covers(seg.destSet, s.destSet) || covers(s.destSet, seg.destSet)) hiSeg(s);
            });
        }
        closeTipsExcept(layer);
    }

    function pinSegment(seg, layer) {
        state.pinnedKey = 'seg:' + seg.source + ':' + seg.destSet.join(',');
        state.pinnedLayer = layer;
        state.focusKey = null;
        focusSegment(seg, layer);
        if (layer) layer.openTooltip();
    }

    function pinSource(src, layer) {
        var root = null;
        state.segments.forEach(function (s) {
            if (s.source === src && (!root || s.destSet.length > root.destSet.length)) root = s;
        });
        if (root) pinSegment(root, layer);
    }

    function pinHost(host, layer) {
        state.pinnedKey = 'h:' + host;
        state.pinnedLayer = layer;
        state.focusKey = null;
        focusHost(host, layer);
        if (layer) layer.openTooltip();
    }

    function focusSource(src, layer) {
        var key = 's:' + src;
        if (state.focusKey !== key) {
            state.focusKey = key;
            dimAll();
            hiNode(src);
            state.segments.forEach(function (s) {
                if (s.source === src) { hiSeg(s); if (s.leaf) hiNode(s.host); }
            });
        }
        closeTipsExcept(layer);
    }

    function focusHost(host, layer) {
        var key = 'h:' + host;
        if (state.focusKey !== key) {
            state.focusKey = key;
            dimAll();
            hiNode(host);
            state.segments.forEach(function (s) {
                if (s.destSet.indexOf(host) !== -1) { hiSeg(s); hiNode(s.source); }
            });
        }
        closeTipsExcept(layer);
    }

    function clearFocus() {
        if (!state.focusKey && !state.pinnedKey) return;
        state.focusKey = null;
        state.pinnedKey = null;
        state.pinnedLayer = null;
        closeTipsExcept(null);
        state.segments.forEach(function (s) {
            segLines(s).forEach(function (line) { line.setStyle({ opacity: segOpacity(s) }); });
        });
        state.nodes.forEach(function (n) { if (n.marker) n.marker.setStyle({ fillOpacity: 0.95, opacity: 1 }); });
    }

    function money(value, digits) {
        var amount = Math.abs(Number(value) || 0);
        var sign = Number(value) < 0 ? '-' : '';
        if (amount >= 1e6) return sign + (amount / 1e6).toFixed(digits) + 'M';
        if (amount >= 1e3) return sign + (amount / 1e3).toFixed(digits) + 'K';
        return sign + String(Math.round(amount));
    }

    function figureRows(year, pns, recipient) {
        var wanted = Number(year);
        return (state.figures || []).filter(function (row) {
            if (Number(row.year) !== wanted) return false;
            if (pns && row.from !== pns) return false;
            if (recipient && row.to !== recipient) return false;
            return true;
        });
    }

    function sumMetric(rows, key) {
        var totals = rows.filter(function (row) { return !row.area; });
        var fromTotals = totals.reduce(function (sum, row) { return sum + (Number(row[key]) || 0); }, 0);
        if (fromTotals) return fromTotals;
        return rows.reduce(function (sum, row) {
            return row.area ? sum + (Number(row[key]) || 0) : sum;
        }, 0);
    }

    function renderAside(year, pns, recipient, edges) {
        var panel = document.getElementById('upri-flow-areas');
        var body = document.getElementById('upri-flow-areas-body');
        var title = document.getElementById('upri-flow-areas-title');
        var cards = document.getElementById('upri-flow-kpis');
        if (!panel || !body || !cards) return;
        var rows = figureRows(year, pns, recipient);
        panel.hidden = false;
        cards.hidden = false;
        if (title) title.textContent = UI.flow_area_title || '';
        var areas = {};
        (state.areaLabels || []).forEach(function (area) {
            areas[area.code] = { label: area.label, requirement: 0, expenditure: 0 };
        });
        rows.forEach(function (row) {
            if (!row.area || !areas[row.area]) return;
            areas[row.area].requirement += Number(row.requirement) || 0;
            areas[row.area].expenditure += Number(row.expenditure) || 0;
        });
        var list = Object.keys(areas).map(function (code) { return areas[code]; }).filter(function (area) {
            return area.requirement || area.expenditure;
        }).sort(function (a, b) {
            return b.requirement - a.requirement || b.expenditure - a.expenditure;
        });
        body.replaceChildren();
        var hasExpenditure = list.some(function (area) { return area.expenditure; });
        panel.classList.toggle('is-single', !hasExpenditure);
        var expenditureLegend = document.getElementById('upri-flow-areas-legend-expenditure');
        if (expenditureLegend) expenditureLegend.hidden = !hasExpenditure;
        if (!list.length) {
            var empty = document.createElement('p');
            empty.className = 'upri-flow-areas__empty';
            empty.textContent = fill(UI.flow_area_empty || '', { year: year || '' });
            body.appendChild(empty);
        } else {
            var max = 1;
            list.forEach(function (area) { max = Math.max(max, area.requirement, area.expenditure); });
            list.forEach(function (area) {
                var line = document.createElement('div');
                line.className = 'upri-flow-areas__row';
                var label = document.createElement('span');
                label.className = 'upri-flow-areas__label';
                label.textContent = area.label;
                var pair = document.createElement('div');
                pair.className = 'upri-flow-areas__pair';
                ['requirement', 'expenditure'].forEach(function (metric) {
                    if (metric === 'expenditure' && !area[metric]) return;
                    var item = document.createElement('div');
                    item.className = 'upri-flow-areas__line';
                    var track = document.createElement('span');
                    track.className = 'upri-flow-areas__track';
                    var fillBar = document.createElement('span');
                    fillBar.className = 'upri-flow-areas__fill upri-flow-areas__fill--' + metric;
                    fillBar.style.width = ((area[metric] / max) * 100) + '%';
                    if (!area[metric]) fillBar.style.minWidth = '0';
                    var value = document.createElement('span');
                    value.className = 'upri-flow-areas__value';
                    value.textContent = money(area[metric], 1);
                    track.appendChild(fillBar);
                    fillBar.appendChild(value);
                    item.appendChild(track);
                    pair.appendChild(item);
                });
                line.appendChild(label);
                line.appendChild(pair);
                body.appendChild(line);
            });
        }
        var donors = {};
        var hosts = {};
        (edges || []).forEach(function (edge) {
            if (edge.from) donors[edge.from] = true;
            if (edge.to) hosts[edge.to] = true;
        });
        cards.replaceChildren();
        [
            [UI.flow_kpi_donors, String(Object.keys(donors).length)],
            [UI.flow_kpi_hosts, String(Object.keys(hosts).length)],
            [UI.flow_kpi_requirement_total, money(sumMetric(rows, 'requirement'), 2)],
            [UI.flow_kpi_funding, money(sumMetric(rows, 'funding'), 2)],
            [UI.flow_kpi_expenditure_total, money(sumMetric(rows, 'expenditure'), 2)]
        ].forEach(function (item) {
            var card = document.createElement('div');
            card.className = 'upri-flow-kpi';
            var name = document.createElement('span');
            name.className = 'upri-flow-kpi__label';
            name.textContent = item[0] || '';
            var value = document.createElement('span');
            value.className = 'upri-flow-kpi__value';
            value.textContent = item[1];
            card.appendChild(name);
            card.appendChild(value);
            cards.appendChild(card);
        });
    }

    function fitToNodes() {
        if (!map || !state.nodes.length) return;
        var pts = state.nodes.map(function (n) { return [n.lat, n.lng]; });
        try {
            map.fitBounds(window.L.latLngBounds(pts).pad(0.15), { animate: false, maxZoom: 5 });
        } catch (e) { /* noop */ }
    }

    // --- Loading ---------------------------------------------------------

    function fetchJson(url, region) {
        if (region) url += (url.indexOf('?') === -1 ? '?' : '&') + 'region=' + encodeURIComponent(region);
        return fetch(url, { headers: { Accept: 'application/json' }, credentials: 'same-origin' })
            .then(function (resp) {
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                return resp.json();
            });
    }

    function applyYear() {
        if (state.applying) return;
        state.applying = true;
        var year = parseInt(els.year && els.year.value, 10);
        if (!year) year = state.years[0];
        state.year = year || null;
        var pool = year ? edgesForYear(year) : [];
        refreshPartyFilters(pool);
        var pns = els.pns ? els.pns.value : '';
        var recipient = els.recipient ? els.recipient.value : '';
        var edges = pool.filter(function (edge) {
            if (pns && edge.from !== pns) return false;
            if (recipient && edge.to !== recipient) return false;
            return true;
        });
        state.applying = false;
        updateClearFilters();
        renderAside(year, pns, recipient, edges);
        if (!edges.length) {
            state.edges = [];
            state.nodes = [];
            if (edgesLayer) edgesLayer.clearLayers();
            if (nodesLayer) nodesLayer.clearLayers();
            setState('empty');
            return;
        }
        if (!window.L) {
            setState('error');
            return;
        }
        state.edges = edges;
        state.nodes = nodesForEdges(edges);
        setState('content');
        ensureMap(state.tiles || {});
        if (map) draw();
        scheduleSettle(true);
    }

    function render(flows) {
        state.allNodes = flows.nodes || [];
        state.allEdges = flows.edges || [];
        state.nodeByIso = {};
        state.allNodes.forEach(function (node) { state.nodeByIso[node.iso3] = node; });
        state.figures = flows.figures || [];
        state.areaLabels = flows.areas || [];
        state.tiles = flows.tiles || {};
        state.filtersReady = false;
        if (!flows.has_data || !state.allEdges.length) {
            setState('empty');
            return;
        }
        var years = flows.years || [];
        if (!years.length) {
            var seen = {};
            state.allEdges.forEach(function (edge) {
                (edge.years || []).forEach(function (year) { seen[year] = true; });
            });
            years = Object.keys(seen).map(Number);
        }
        populateYears(years);
        renderNote(flows);
        applyYear();
    }

    function renderNote(flows) {
        if (!els.note) return;
        var count = (flows.unresolved_donors || []).length;
        if (count) {
            els.note.textContent = plural(count, 'flow_unresolved_one', 'flow_unresolved');
            els.note.hidden = false;
        } else {
            els.note.hidden = true;
        }
    }

    function load() {
        var url = CFG.flowUrl || root.getAttribute('data-flow-url');
        if (!url) {
            var section = els.host.closest('[data-flow-url]');
            url = section && section.getAttribute('data-flow-url');
        }
        if (!url) return;
        var region = els.region ? els.region.value : '';
        var ticket = ++state.request;
        setState('loading');
        fetchJson(url, region)
            .then(function (payload) {
                if (ticket !== state.request) return;
                render((payload && payload.flows) || {});
            })
            .catch(function (err) {
                if (ticket !== state.request) return;
                setState('error');
                if (window.console) console.error('UPR flow map load failed', err);
            });
    }

    // --- Wiring ----------------------------------------------------------

    if (els.reset) els.reset.addEventListener('click', fitToNodes);
    if (els.clearFilters) els.clearFilters.addEventListener('click', clearFilters);
    var filtersToggle = byId('upri-flow-filters-toggle');
    if (filtersToggle && els.filters) {
        filtersToggle.addEventListener('click', function () {
            var collapsed = els.filters.classList.toggle('is-collapsed');
            filtersToggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
            filtersToggle.setAttribute('aria-label', filtersToggle.getAttribute(collapsed ? 'data-label-show' : 'data-label-hide') || '');
        });
    }
    [els.year, els.pns, els.recipient].forEach(function (select) {
        if (!select) return;
        select.addEventListener('change', function () {
            if (state.loaded && state.allEdges.length) applyYear();
        });
    });
    if (els.region) els.region.addEventListener('change', function () { if (state.loaded) load(); });
    if (els.refresh) els.refresh.addEventListener('click', function () { if (state.loaded) load(); });

    function ensureLoaded() {
        if (state.loaded) return;
        state.loaded = true;
        load();
    }

    function flowPaneOpen() {
        var pane = document.getElementById('upri-pane-flow');
        return !pane || !pane.hidden;
    }

    function panelVisible() {
        if (embed) return true;
        return !panel.classList.contains('hidden') && panel.offsetParent !== null && flowPaneOpen();
    }

    function revealMap() {
        ensureLoaded();
        if (map) scheduleSettle(true);
    }

    if (panelVisible()) {
        ensureLoaded();
    } else if (panel) {
        var observer = new MutationObserver(function () {
            if (panelVisible()) revealMap();
        });
        observer.observe(panel, { attributes: true, attributeFilter: ['class'] });
        var flowPane = document.getElementById('upri-pane-flow');
        if (flowPane) observer.observe(flowPane, { attributes: true, attributeFilter: ['hidden'] });
        var tabBtn = byId('tab-upr-impact');
        if (tabBtn) tabBtn.addEventListener('click', function () { window.setTimeout(revealMap, 0); });
    }
})();
