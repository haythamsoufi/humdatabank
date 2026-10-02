/**
 * Validation Dashboard — Tracker tab (assignments, sections, documents, Mapbox choropleth).
 */
(function () {
    'use strict';

    var config = window.validationDashboardConfig || {};
    var t = window.VD_GRID_TRANSLATIONS || {};
    var TRACKER_STORAGE_KEY = 'humdb_validation_dashboard_tracker_v1';

    var state = {
        templateId: null,
        period: null,
        map: null,
        geoLayer: null,
        mapInitialized: false,
        statusChart: null,
        delegationReviewEnabled: false,
        allRows: [],
        allMapCountries: [],
        trackerMeta: null,
        loaded: false,
        sectionsMeta: [],
        documentsMeta: [],
        requiredDocumentKeys: [],
        sortKey: 'country',
        sortDir: 'asc',
        columnFilters: {},
        rebuildTrackerHead: true,
    };

    function el(id) { return document.getElementById(id); }

    var esc = window.esc || function (s) {
        if (s == null) return '';
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    };
    var scopeLoader = window.ValidationScopeLoader || {};

    function getTemplateId() {
        return el('vd-template')?.value || '';
    }

    function showFeedback(message, type) {
        if (window.validationDashboardShowFeedback) {
            window.validationDashboardShowFeedback(message, type);
        }
    }

    var STATUS_COLORS = {
        approved: '#16a34a',
        submitted: '#2563eb',
        sent_for_review: '#7c3aed',
        requires_revision: '#ea580c',
        in_progress: '#d97706',
        pending: '#94a3b8',
    };

    var STATUS_LABELS = {
        approved: 'Approved',
        submitted: 'Submitted',
        sent_for_review: 'Sent for review',
        requires_revision: 'Requires revision',
        in_progress: 'In progress',
        pending: 'Pending',
    };

    function statusLabel(status) {
        var map = {
            approved: t.statusApproved || STATUS_LABELS.approved,
            submitted: t.statusSubmitted || STATUS_LABELS.submitted,
            sent_for_review: t.statusSentForReview || STATUS_LABELS.sent_for_review,
            requires_revision: t.statusRequiresRevision || STATUS_LABELS.requires_revision,
            in_progress: t.statusInProgress || STATUS_LABELS.in_progress,
            pending: t.statusPending || STATUS_LABELS.pending,
        };
        return map[status] || status;
    }

    function statusBadge(status, label) {
        var text = label || statusLabel(status);
        if (window.StatusLabels) {
            return window.StatusLabels.renderAssignmentStatus(status, text);
        }
        return '<span class="status-label status-label--neutral">' + esc(text) + '</span>';
    }

    function sectionStatusLabel(fillStatus) {
        var labels = {
            not_started: t.sectionNotStarted || 'Not started',
            in_progress: t.sectionInProgress || 'In progress',
            complete: t.sectionComplete || 'Complete',
        };
        return labels[fillStatus] || fillStatus || labels.not_started;
    }

    function completionRateCell(rate) {
        if (rate == null || rate === '' || isNaN(Number(rate))) {
            return '<span class="vd-completion-rate vd-completion-none">—</span>';
        }
        var num = Number(rate);
        var cls = 'vd-completion-critical';
        if (num >= 80) cls = 'vd-completion-high';
        else if (num >= 50) cls = 'vd-completion-mid';
        else if (num >= 25) cls = 'vd-completion-low';
        return '<span class="vd-completion-rate ' + cls + '">' + esc(num.toFixed(1)) + '%</span>';
    }

    function sectionStatusIcon(fillStatus) {
        var key = fillStatus || 'not_started';
        var text = sectionStatusLabel(key);
        var icon = key === 'complete' ? 'fa-check-circle' : (key === 'in_progress' ? 'fa-circle-half-stroke' : 'far fa-circle');
        return '<span class="vd-icon-cell vd-section-icon is-' + esc(key) + '" title="' + esc(text) + '" aria-label="' + esc(text) + '">' +
            '<i class="' + (key === 'not_started' ? icon : 'fas ' + icon) + '" aria-hidden="true"></i></span>';
    }

    function sectionLabelForKey(key) {
        var meta = (state.sectionsMeta || []).find(function (m) { return m.key === key; });
        return (meta && meta.label) || key;
    }

    function renderTrackerLegend() {
        var legendEl = el('vd-tracker-legend');
        if (!legendEl) return;

        var sectionStates = ['complete', 'in_progress', 'not_started'];
        var sectionItems = sectionStates.map(function (key) {
            return '<li class="vd-tracker-legend-item">' + sectionStatusIcon(key) + esc(sectionStatusLabel(key)) + '</li>';
        }).join('');

        var docItems = '<li class="vd-tracker-legend-item">' + boolIcon(true) + esc(t.uploaded || 'Uploaded') + '</li>' +
            '<li class="vd-tracker-legend-item">' + boolIcon(false) + esc(t.missing || 'Missing') + '</li>';

        legendEl.innerHTML =
            '<div class="vd-tracker-legend-group">' +
            '<span class="vd-tracker-legend-title">' + esc(t.legendSections || 'Section progress') + '</span>' +
            '<ul class="vd-tracker-legend-items">' + sectionItems + '</ul>' +
            '</div>' +
            '<div class="vd-tracker-legend-group">' +
            '<span class="vd-tracker-legend-title">' + esc(t.legendDocuments || 'Documents') + '</span>' +
            '<ul class="vd-tracker-legend-items">' + docItems + '</ul>' +
            '</div>';
    }

    function boolIcon(uploaded) {
        if (uploaded) {
            return '<span class="vd-icon-cell vd-icon-yes" title="' + esc(t.uploaded || 'Uploaded') + '">' +
                '<i class="fas fa-check-circle" aria-hidden="true"></i></span>';
        }
        return '<span class="vd-icon-cell vd-icon-no" title="' + esc(t.missing || 'Missing') + '">' +
            '<i class="far fa-circle" aria-hidden="true"></i></span>';
    }

    var STATUS_ORDER_BASE = [
        'approved',
        'submitted',
        'sent_for_review',
        'requires_revision',
        'in_progress',
        'pending',
    ];

    function statusOrderForTracker() {
        if (state.delegationReviewEnabled) return STATUS_ORDER_BASE.slice();
        return STATUS_ORDER_BASE.filter(function (key) { return key !== 'sent_for_review'; });
    }

    function getApexCharts() {
        return (typeof window !== 'undefined' && window.ApexCharts) || null;
    }

    function destroyStatusChart() {
        if (state.statusChart) {
            try { state.statusChart.destroy(); } catch (err) { /* ignore */ }
            state.statusChart = null;
        }
        var chartEl = el('vd-tracker-status-chart');
        if (chartEl) chartEl.innerHTML = '';
    }

    function renderStatusChart(stats) {
        var chartEl = el('vd-tracker-status-chart');
        if (!chartEl) return;

        destroyStatusChart();

        if (!stats) {
            chartEl.innerHTML = '<div class="flex items-center justify-center h-full text-sm text-gray-400">—</div>';
            return;
        }

        var ApexCharts = getApexCharts();
        if (!ApexCharts) {
            chartEl.innerHTML = '<div class="flex items-center justify-center h-full text-sm text-gray-400">Chart unavailable</div>';
            return;
        }

        var byStatus = stats.by_status || {};
        var categories = [];
        var values = [];
        var colors = [];
        statusOrderForTracker().forEach(function (key) {
            var count = byStatus[key] || 0;
            if (key === 'requires_revision' && count === 0) return;
            categories.push(statusLabel(key));
            values.push(count);
            colors.push(STATUS_COLORS[key] || '#94a3b8');
        });

        var docsCount = stats.documents_both_required_count;
        var docsLabel = t.keyDocsUploaded || 'Key docs uploaded';
        var subtitle = stats.country_count != null
            ? (String(stats.country_count) + ' ' + (t.statusChartCountries || 'countries'))
            : '';

        state.statusChart = new ApexCharts(chartEl, {
            chart: {
                type: 'bar',
                height: 340,
                fontFamily: 'inherit',
                toolbar: { show: false },
                animations: { enabled: true, speed: 400 },
            },
            series: [{ name: t.statusChartCountries || 'Countries', data: values }],
            colors: colors,
            plotOptions: {
                bar: {
                    horizontal: true,
                    distributed: true,
                    barHeight: '68%',
                    borderRadius: 4,
                    dataLabels: { position: 'right' },
                },
            },
            dataLabels: {
                enabled: true,
                formatter: function (val) { return val > 0 ? String(val) : ''; },
                style: { fontSize: '11px', fontWeight: 600, colors: ['#374151'] },
                offsetX: 4,
            },
            legend: { show: false },
            xaxis: {
                categories: categories,
                labels: {
                    style: { fontSize: '11px', colors: '#4b5563' },
                    maxWidth: 160,
                },
                axisBorder: { show: false },
                axisTicks: { show: false },
            },
            yaxis: {
                labels: {
                    style: { fontSize: '11px', colors: '#6b7280' },
                },
            },
            grid: {
                borderColor: '#f3f4f6',
                xaxis: { lines: { show: false } },
                yaxis: { lines: { show: true } },
                padding: { left: 4, right: 20, top: -8, bottom: 0 },
            },
            tooltip: {
                y: {
                    formatter: function (val, opts) {
                        var label = categories[opts.dataPointIndex] || '';
                        return label + ': ' + val + ' ' + (t.statusChartCountries || 'countries');
                    },
                },
            },
            subtitle: subtitle ? {
                text: subtitle + (docsCount != null ? ' · ' + docsLabel + ': ' + docsCount : ''),
                style: { fontSize: '11px', color: '#6b7280' },
                offsetY: 4,
            } : undefined,
        });

        state.statusChart.render();
    }

    function refreshChartLayout() {
        if (state.statusChart) {
            try { state.statusChart.updateOptions({}, false, true); } catch (err) { /* ignore */ }
        }
    }

    var worldGeoJsonPromise = null;

    function fetchWorldGeoJson() {
        if (worldGeoJsonPromise) return worldGeoJsonPromise;
        var urls = [
            'https://cdn.jsdelivr.net/gh/datasets/geo-countries@master/data/countries.geojson',
            'https://cdn.jsdelivr.net/gh/holtzy/D3-graph-gallery@master/DATA/world.geojson',
        ];
        worldGeoJsonPromise = (async function () {
            for (var i = 0; i < urls.length; i++) {
                try {
                    var res = await fetch(urls[i], { cache: 'force-cache' });
                    if (!res.ok) continue;
                    var data = await res.json();
                    if (data && Array.isArray(data.features) && data.features.length) return data;
                } catch (err) { /* try next */ }
            }
            throw new Error('World GeoJSON unavailable');
        })();
        worldGeoJsonPromise.catch(function () { worldGeoJsonPromise = null; });
        return worldGeoJsonPromise;
    }

    function featureIso3(feature) {
        var p = (feature && feature.properties) || {};
        var v = p.ISO_A3 || p.ADM0_A3 || p.iso_a3 || p.ISO3 || p.ISO3_CODE || p['ISO3166-1-Alpha-3'];
        if (!v && p.iso3) v = p.iso3;
        var out = String(v || '').trim().toUpperCase();
        return /^[A-Z]{3}$/.test(out) ? out : '';
    }

    function addMapboxTiles(map) {
        var token = config.mapboxAccessToken || '';
        var styleId = config.mapboxStyleId || 'go-ifrc/ckrfe16ru4c8718phmckdfjh0';
        var hintEl = el('vd-tracker-map-hint');
        if (!token) {
            if (hintEl) {
                hintEl.textContent = t.mapNoToken || 'Set MAPBOX_ACCESS_TOKEN in environment secrets.';
                hintEl.classList.remove('hidden');
            }
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '&copy; OpenStreetMap',
                maxZoom: 6,
            }).addTo(map);
            return;
        }
        if (hintEl) hintEl.classList.add('hidden');
        L.tileLayer(
            'https://api.mapbox.com/styles/v1/' + styleId + '/tiles/{z}/{x}/{y}?access_token=' + encodeURIComponent(token),
            {
                attribution: '&copy; Mapbox &copy; OpenStreetMap',
                tileSize: 512,
                zoomOffset: -1,
                maxZoom: 6,
            }
        ).addTo(map);
    }

    function renderMapCountries(mapCountries) {
        var mapEl = el('vd-tracker-map');
        if (!mapEl || typeof L === 'undefined') return;

        var lookup = {};
        (mapCountries || []).forEach(function (row) {
            if (row.iso3) lookup[String(row.iso3).toUpperCase()] = row;
        });

        fetchWorldGeoJson().then(function (geo) {
            if (!state.map) {
                state.map = L.map(mapEl, {
                    zoomControl: true,
                    minZoom: 1,
                    maxZoom: 6,
                    worldCopyJump: true,
                }).setView([20, 0], 1.4);
                addMapboxTiles(state.map);
                state.mapInitialized = true;
            }

            if (state.geoLayer) {
                state.map.removeLayer(state.geoLayer);
                state.geoLayer = null;
            }

            state.geoLayer = L.geoJSON(geo, {
                style: function (feature) {
                    var iso3 = featureIso3(feature);
                    var row = iso3 ? lookup[iso3] : null;
                    var fill = row ? (STATUS_COLORS[row.status] || STATUS_COLORS.pending) : '#e5e7eb';
                    return {
                        color: '#ffffff',
                        weight: 0.6,
                        fillColor: fill,
                        fillOpacity: row ? 0.85 : 0.35,
                    };
                },
                onEachFeature: function (feature, layer) {
                    var iso3 = featureIso3(feature);
                    var row = iso3 ? lookup[iso3] : null;
                    if (!row) return;
                    layer.bindTooltip(
                        '<strong>' + esc(row.label || iso3) + '</strong><br>' +
                        esc(statusLabel(row.status)),
                        { sticky: true }
                    );
                },
            }).addTo(state.map);

            setTimeout(function () {
                try { state.map.invalidateSize(true); } catch (err) { /* ignore */ }
            }, 50);
        }).catch(function (err) {
            console.error(err);
        });
    }

    function renderMap(mapCountries) {
        renderMapCountries(mapCountries);
    }

    function countriesGroupedByRegion(rows) {
        var groups = {};
        (rows || []).forEach(function (row) {
            var region = (row.region && String(row.region).trim()) || (t.regionOther || 'Other');
            if (!groups[region]) groups[region] = [];
            groups[region].push(row);
        });
        return Object.keys(groups).sort(function (a, b) {
            return a.localeCompare(b);
        }).map(function (region) {
            return {
                region: region,
                countries: groups[region].sort(function (a, b) {
                    return String(a.country_name || '').localeCompare(String(b.country_name || ''));
                }),
            };
        });
    }

    function countrySlicerEl() {
        return el('vd-tracker-country-slicer');
    }

    function fdsMemberSlicerEl() {
        return el('vd-tracker-fds-member-slicer');
    }

    function buildFdsMemberSlicer(rows) {
        var fdsMemberEl = fdsMemberSlicerEl();
        if (!fdsMemberEl) return;

        if (!rows || !rows.length) {
            fdsMemberEl.innerHTML = '<option value="">' + esc(t.fdsMemberAll || 'All FDS members') + '</option>';
            fdsMemberEl.disabled = true;
            return;
        }

        var members = {};
        rows.forEach(function (row) {
            if (row.fds_member_user_id) {
                members[row.fds_member_user_id] = row.fds_member_name || ('User ' + row.fds_member_user_id);
            }
        });

        var memberOptions = Object.keys(members).map(function (userId) {
            return {
                id: userId,
                label: members[userId],
            };
        }).sort(function (a, b) {
            return String(a.label).localeCompare(String(b.label));
        });

        var optionsHtml = memberOptions.map(function (member) {
            return '<option value="' + esc(String(member.id)) + '">' + esc(member.label) + '</option>';
        }).join('');

        fdsMemberEl.innerHTML =
            '<option value="">' + esc(t.fdsMemberAll || 'All FDS members') + '</option>' +
            '<option value="__unassigned__">' + esc(t.fdsMemberUnassigned || 'Not assigned') + '</option>' +
            optionsHtml;
        fdsMemberEl.value = '';
        fdsMemberEl.disabled = false;
    }

    function buildCountrySlicer(rows) {
        var selectEl = countrySlicerEl();
        if (!selectEl) return;

        if (!rows || !rows.length) {
            selectEl.innerHTML = '<option value="">' + esc(t.slicerEmpty || 'Load a reporting period to filter countries.') + '</option>';
            selectEl.disabled = true;
            buildFdsMemberSlicer([]);
            return;
        }

        var groups = countriesGroupedByRegion(rows);
        var groupsHtml = groups.map(function (group) {
            var options = group.countries.map(function (c) {
                return '<option value="' + esc(String(c.country_id)) + '">' + esc(c.country_name) + '</option>';
            }).join('');
            return '<optgroup label="' + esc(group.region) + '">' + options + '</optgroup>';
        }).join('');
        selectEl.innerHTML = '<option value="">' + esc(t.allCountries || 'All countries') + '</option>' + groupsHtml;
        selectEl.value = '';
        selectEl.disabled = false;
        buildFdsMemberSlicer(rows);
    }

    function computeStatsFromRows(rows) {
        var statusCounts = {};
        var sectionComplete = {};
        state.sectionsMeta.forEach(function (spec) { sectionComplete[spec.key] = 0; });

        var docsBoth = 0;
        var submittedLike = 0;
        var approved = 0;
        var submittedStatuses = state.delegationReviewEnabled
            ? ['submitted', 'approved', 'sent_for_review']
            : ['submitted', 'approved'];

        rows.forEach(function (row) {
            var status = row.status || 'pending';
            statusCounts[status] = (statusCounts[status] || 0) + 1;
            if (submittedStatuses.indexOf(status) >= 0) submittedLike++;
            if (status === 'approved') approved++;

            var sections = row.sections || {};
            Object.keys(sectionComplete).forEach(function (key) {
                if (sections[key] === 'complete') sectionComplete[key]++;
            });

            var docs = row.documents || {};
            var requiredDocs = state.requiredDocumentKeys || [];
            if (requiredDocs.length && requiredDocs.every(function (key) { return !!docs[key]; })) docsBoth++;
        });

        return {
            country_count: rows.length,
            assigned_count: rows.length,
            by_status: statusCounts,
            delegation_review_enabled: state.delegationReviewEnabled,
            submitted_count: submittedLike,
            approved_count: approved,
            in_progress_count: statusCounts.in_progress || 0,
            pending_count: statusCounts.pending || 0,
            documents_both_required_count: docsBoth,
            section_complete_counts: sectionComplete,
            reporting_year: state.trackerMeta && state.trackerMeta.reporting_year,
        };
    }

    var STATUS_SORT_RANK = {
        approved: 5,
        submitted: 4,
        sent_for_review: 3,
        requires_revision: 3,
        in_progress: 2,
        pending: 1,
    };
    var SECTION_SORT_RANK = { not_started: 0, in_progress: 1, complete: 2 };

    function trackerColumns() {
        var meta = trackerColumnMeta();
        var cols = [
            {
                key: 'region',
                label: t.region || 'Region',
                className: 'vd-col-region',
                kind: 'text',
                value: function (row) { return row.region || ''; },
            },
            {
                key: 'country',
                label: t.country || 'Country',
                className: 'vd-col-country',
                kind: 'text',
                value: function (row) { return row.country_name || ''; },
            },
            {
                key: 'status',
                label: t.status || 'Status',
                kind: 'status',
                value: function (row) { return row.status || ''; },
                display: function (row) { return row.status_label || statusLabel(row.status); },
            },
        ];
        if (meta.sections.length) {
            cols.push({
                key: 'completion_rate',
                label: t.completionRate || 'Completion rate',
                className: 'vd-center vd-head-wrap',
                kind: 'number',
                value: function (row) { return row.completion_rate; },
            });
        }
        meta.sections.forEach(function (spec) {
            cols.push({
                key: 'section:' + spec.key,
                label: spec.label || sectionLabelForKey(spec.key),
                className: 'vd-center vd-head-wrap',
                kind: 'section',
                value: function (row) { return (row.sections || {})[spec.key] || 'not_started'; },
            });
        });
        meta.documents.forEach(function (doc) {
            cols.push({
                key: 'doc:' + doc.key,
                label: doc.label,
                className: 'vd-center vd-head-wrap',
                kind: 'document',
                value: function (row) { return !!(row.documents || {})[doc.key]; },
            });
        });
        return cols;
    }

    function columnByKey(key) {
        var cols = trackerColumns();
        for (var i = 0; i < cols.length; i++) {
            if (cols[i].key === key) return cols[i];
        }
        return null;
    }

    function slicerFilteredRows() {
        if (!state.allRows.length) return [];
        var selectEl = countrySlicerEl();
        var countryId = selectEl && selectEl.value;
        var fdsMemberEl = fdsMemberSlicerEl();
        var fdsMemberVal = fdsMemberEl && fdsMemberEl.value;

        return state.allRows.filter(function (row) {
            if (countryId && String(row.country_id) !== String(countryId)) return false;
            if (fdsMemberVal === '__unassigned__' && row.fds_member_user_id) return false;
            if (fdsMemberVal && fdsMemberVal !== '__unassigned__' &&
                String(row.fds_member_user_id) !== String(fdsMemberVal)) return false;
            return true;
        });
    }

    function rowMatchesColumnFilters(row) {
        var filters = state.columnFilters || {};
        var keys = Object.keys(filters);
        for (var i = 0; i < keys.length; i++) {
            var raw = filters[keys[i]];
            if (raw == null || raw === '') continue;
            var col = columnByKey(keys[i]);
            if (!col) continue;
            var value = col.value(row);
            if (col.kind === 'text') {
                if (String(value).toLowerCase().indexOf(String(raw).toLowerCase()) === -1) return false;
            } else if (col.kind === 'status' || col.kind === 'section') {
                if (String(value) !== String(raw)) return false;
            } else if (col.kind === 'document') {
                var uploaded = !!value;
                if (raw === 'yes' && !uploaded) return false;
                if (raw === 'no' && uploaded) return false;
            } else if (col.kind === 'number') {
                var num = Number(value);
                if (!Number.isFinite(num)) return false;
                if (raw === '80' && num < 80) return false;
                else if (raw === '50' && num < 50) return false;
                else if (raw === '25' && num < 25) return false;
                else if (raw === 'lt25' && num >= 25) return false;
                else if (raw === 'zero' && num !== 0) return false;
            }
        }
        return true;
    }

    function compareColumnValues(left, right, col, dir) {
        var a = col.value(left);
        var b = col.value(right);
        var result = 0;
        if (col.kind === 'number') {
            var an = Number(a);
            var bn = Number(b);
            if (!Number.isFinite(an)) an = -1;
            if (!Number.isFinite(bn)) bn = -1;
            result = an - bn;
        } else if (col.kind === 'status') {
            result = (STATUS_SORT_RANK[a] || 0) - (STATUS_SORT_RANK[b] || 0);
        } else if (col.kind === 'section') {
            result = (SECTION_SORT_RANK[a] || 0) - (SECTION_SORT_RANK[b] || 0);
        } else if (col.kind === 'document') {
            result = (a ? 1 : 0) - (b ? 1 : 0);
        } else {
            result = String(a).localeCompare(String(b), undefined, { sensitivity: 'base' });
        }
        if (result === 0) {
            result = String(left.country_name || '').localeCompare(String(right.country_name || ''), undefined, { sensitivity: 'base' });
        }
        return dir === 'desc' ? -result : result;
    }

    function sortTrackerRows(rows) {
        var col = columnByKey(state.sortKey) || columnByKey('country');
        if (!col) return rows.slice();
        var dir = state.sortDir === 'desc' ? 'desc' : 'asc';
        return rows.slice().sort(function (left, right) {
            return compareColumnValues(left, right, col, dir);
        });
    }

    function getFilteredRows() {
        return sortTrackerRows(slicerFilteredRows().filter(rowMatchesColumnFilters));
    }

    function filterOption(value, label) {
        return '<option value="' + esc(value) + '">' + esc(label) + '</option>';
    }

    function columnFilterControl(col, sourceRows) {
        var current = (state.columnFilters && state.columnFilters[col.key]) || '';
        var label = (t.filterAll || 'All');
        if (col.kind === 'text') {
            return '<input type="search" class="vd-col-filter" data-filter-key="' + esc(col.key) +
                '" value="' + esc(current) + '" placeholder="' + esc(label) + '" aria-label="' +
                esc(col.label) + '">';
        }
        var options = [filterOption('', label)];
        if (col.kind === 'status') {
            var seen = {};
            sourceRows.forEach(function (row) {
                var value = col.value(row);
                if (!value || seen[value]) return;
                seen[value] = true;
                options.push(filterOption(value, col.display ? col.display(row) : statusLabel(value)));
            });
        } else if (col.kind === 'section') {
            ['complete', 'in_progress', 'not_started'].forEach(function (key) {
                options.push(filterOption(key, sectionStatusLabel(key)));
            });
        } else if (col.kind === 'document') {
            options.push(filterOption('yes', t.uploaded || 'Uploaded'));
            options.push(filterOption('no', t.missing || 'Missing'));
        } else if (col.kind === 'number') {
            options.push(filterOption('80', t.completionAtLeast80 || '80% and above'));
            options.push(filterOption('50', t.completionAtLeast50 || '50% and above'));
            options.push(filterOption('25', t.completionAtLeast25 || '25% and above'));
            options.push(filterOption('lt25', t.completionBelow25 || 'Below 25%'));
            options.push(filterOption('zero', t.completionNone || '0%'));
        }
        return '<select class="vd-col-filter" data-filter-key="' + esc(col.key) + '" aria-label="' +
            esc(col.label) + '">' + options.join('') + '</select>';
    }

    function columnHeaderHtml(col) {
        var sorted = state.sortKey === col.key;
        var filtered = !!(state.columnFilters && state.columnFilters[col.key]);
        var sortMark = sorted
            ? '<i class="vd-sort-mark fas ' + (state.sortDir === 'desc' ? 'fa-sort-down' : 'fa-sort-up') + '" aria-hidden="true"></i>'
            : '';
        var btnClass = 'vd-col-menu-btn' + (sorted ? ' is-sorted' : '') + (filtered ? ' is-filtered' : '');
        return '<div class="vd-col-head">' +
            '<span class="vd-col-label">' + esc(col.label) + sortMark + '</span>' +
            '<button type="button" class="' + btnClass + '" data-col-key="' + esc(col.key) +
            '" aria-haspopup="dialog" aria-expanded="false" aria-label="' +
            esc((t.columnMenu || 'Sort and filter') + ': ' + col.label) + '">' +
            '<i class="fas fa-filter" aria-hidden="true"></i>' +
            '</button></div>';
    }

    function refreshMenuButtons() {
        var table = el('vd-tracker-table');
        if (!table) return;
        table.querySelectorAll('.vd-col-menu-btn').forEach(function (btn) {
            var key = btn.getAttribute('data-col-key');
            var sorted = key === state.sortKey;
            var filtered = !!(state.columnFilters && state.columnFilters[key]);
            btn.classList.toggle('is-sorted', sorted);
            btn.classList.toggle('is-filtered', filtered);
            var headerCell = btn.closest('th');
            var label = headerCell && headerCell.querySelector('.vd-col-label');
            if (label) {
                var name = label.childNodes[0] ? label.childNodes[0].textContent : '';
                label.textContent = name;
                if (sorted) {
                    var mark = document.createElement('i');
                    mark.className = 'vd-sort-mark fas ' + (state.sortDir === 'desc' ? 'fa-sort-down' : 'fa-sort-up');
                    mark.setAttribute('aria-hidden', 'true');
                    label.appendChild(mark);
                }
            }
            if (headerCell) {
                if (sorted) headerCell.setAttribute('aria-sort', state.sortDir === 'desc' ? 'descending' : 'ascending');
                else headerCell.removeAttribute('aria-sort');
            }
        });
    }

    function closeColumnMenu() {
        var pop = document.getElementById('vd-col-popover');
        if (pop) pop.remove();
        document.querySelectorAll('.vd-col-menu-btn[aria-expanded="true"]').forEach(function (btn) {
            btn.setAttribute('aria-expanded', 'false');
        });
    }

    function positionColumnPopover(pop, anchor) {
        var rect = anchor.getBoundingClientRect();
        var width = pop.offsetWidth;
        var height = pop.offsetHeight;
        var left = rect.right - width;
        if (left < 8) left = 8;
        if (left + width > window.innerWidth - 8) left = window.innerWidth - width - 8;
        var top = rect.bottom + 6;
        if (top + height > window.innerHeight - 8) top = Math.max(8, rect.top - height - 6);
        pop.style.top = top + 'px';
        pop.style.left = left + 'px';
    }

    function syncPopoverSortButtons(pop, key) {
        pop.querySelectorAll('[data-sort-dir]').forEach(function (btn) {
            var dir = btn.getAttribute('data-sort-dir');
            btn.classList.toggle('is-active', state.sortKey === key && state.sortDir === dir);
        });
    }

    function openColumnMenu(button) {
        var key = button.getAttribute('data-col-key');
        if (button.getAttribute('aria-expanded') === 'true') {
            closeColumnMenu();
            return;
        }
        closeColumnMenu();
        var col = columnByKey(key);
        if (!col) return;
        var pop = document.createElement('div');
        pop.id = 'vd-col-popover';
        pop.className = 'vd-col-popover';
        pop.setAttribute('role', 'dialog');
        pop.setAttribute('aria-label', col.label);
        pop.innerHTML =
            '<p class="vd-col-popover-title">' + esc(col.label) + '</p>' +
            '<div class="vd-col-popover-sort">' +
            '<button type="button" data-sort-dir="asc">' + esc(t.sortAscending || 'Ascending') + '</button>' +
            '<button type="button" data-sort-dir="desc">' + esc(t.sortDescending || 'Descending') + '</button>' +
            '</div>' +
            '<label class="vd-col-popover-label" for="vd-col-popover-filter">' + esc(t.columnFilter || 'Filter') + '</label>' +
            columnFilterControl(col, slicerFilteredRows()).replace(
                'class="vd-col-filter"',
                'class="vd-col-filter" id="vd-col-popover-filter"'
            );
        document.body.appendChild(pop);
        var select = pop.querySelector('select.vd-col-filter');
        if (select) select.value = (state.columnFilters && state.columnFilters[col.key]) || '';
        syncPopoverSortButtons(pop, key);
        positionColumnPopover(pop, button);
        button.setAttribute('aria-expanded', 'true');
        var field = pop.querySelector('.vd-col-filter');
        if (field) field.focus();

        pop.addEventListener('click', function (event) {
            var sortBtn = event.target.closest('[data-sort-dir]');
            if (!sortBtn) return;
            state.sortKey = key;
            state.sortDir = sortBtn.getAttribute('data-sort-dir') === 'desc' ? 'desc' : 'asc';
            refreshMenuButtons();
            syncPopoverSortButtons(pop, key);
            applyTrackerView();
            var still = document.querySelector('.vd-col-menu-btn[data-col-key="' + key + '"]');
            if (still) positionColumnPopover(pop, still);
        });
        pop.addEventListener('input', function (event) {
            if (event.target.tagName !== 'INPUT') return;
            onColumnFilter(event.target);
            var still = document.querySelector('.vd-col-menu-btn[data-col-key="' + key + '"]');
            if (still) positionColumnPopover(pop, still);
        });
        pop.addEventListener('change', function (event) {
            if (!event.target.classList.contains('vd-col-filter')) return;
            onColumnFilter(event.target);
        });
    }

    function onColumnFilter(control) {
        var key = control.getAttribute('data-filter-key');
        if (!key) return;
        state.columnFilters[key] = control.value || '';
        refreshMenuButtons();
        applyTrackerView();
    }

    function getFilteredMapCountries(rows) {
        var isoSet = {};
        rows.forEach(function (row) {
            if (row.country_iso3) isoSet[String(row.country_iso3).toUpperCase()] = true;
        });
        return (state.allMapCountries || []).filter(function (c) {
            return isoSet[String(c.iso3 || '').toUpperCase()];
        });
    }

    function applyTrackerView() {
        var filtered = getFilteredRows();
        var table = el('vd-tracker-table');
        var head = table && table.querySelector('thead');
        var rebuildHead = state.rebuildTrackerHead || !head || !head.children.length;
        state.rebuildTrackerHead = false;
        if (rebuildHead) closeColumnMenu();
        renderTrackerTable(filtered, rebuildHead);
        renderStatusChart(filtered.length ? computeStatsFromRows(filtered) : null);
        renderMapCountries(getFilteredMapCountries(filtered));
    }

    function trackerColumnMeta() {
        return {
            sections: state.sectionsMeta || [],
            documents: state.documentsMeta || [],
        };
    }

    function trackerHtmlCell(html, className) {
        return { html: html || '', className: className || '' };
    }

    function appendTrackerFragment(parent, html) {
        var parsed = new DOMParser().parseFromString('<div>' + (html || '') + '</div>', 'text/html');
        var wrapper = parsed.body.firstChild;
        if (!wrapper) return;
        while (wrapper.firstChild) parent.appendChild(wrapper.firstChild);
    }

    function appendTrackerCell(row, tag, spec) {
        var cell = document.createElement(tag);
        if (spec.className) cell.className = spec.className;
        if (spec.html) appendTrackerFragment(cell, spec.html);
        else cell.textContent = spec.text == null ? '' : String(spec.text);
        row.appendChild(cell);
    }

    function trackerBodyCells(row, cols) {
        return cols.map(function (col) {
            if (col.key === 'region') {
                return row.region
                    ? { text: row.region, className: 'vd-col-region' }
                    : trackerHtmlCell('<span class="vd-muted">—</span>', 'vd-col-region');
            }
            if (col.key === 'country') {
                return { text: row.country_name || '', className: 'vd-col-country' };
            }
            if (col.key === 'status') {
                return trackerHtmlCell(statusBadge(row.status, row.status_label));
            }
            if (col.kind === 'number') {
                return trackerHtmlCell(completionRateCell(row.completion_rate), 'vd-center');
            }
            if (col.kind === 'section') {
                return trackerHtmlCell(sectionStatusIcon(col.value(row)), 'vd-center');
            }
            if (col.kind === 'document') {
                return trackerHtmlCell(boolIcon(!!col.value(row)), 'vd-center');
            }
            return { text: String(col.value(row) || '') };
        });
    }

    function renderTrackerTable(rows, rebuildHead) {
        var table = el('vd-tracker-table');
        var empty = el('vd-tracker-empty');
        if (!table) return;
        var head = table.querySelector('thead');
        var body = table.querySelector('tbody');
        var list = rows || [];
        var scoped = slicerFilteredRows();
        var cols = trackerColumns();
        var scroll = table.closest('.vd-table-scroll');
        if (!scoped.length) {
            if (head) head.replaceChildren();
            if (body) body.replaceChildren();
            if (scroll) scroll.classList.add('hidden');
            if (empty) {
                empty.textContent = t.noAssignments || 'No country assignments for this period.';
                empty.classList.remove('hidden');
            }
            return;
        }
        if (rebuildHead && head) {
            head.replaceChildren();
            var headRow = document.createElement('tr');
            cols.forEach(function (col) {
                var th = document.createElement('th');
                if (col.className) th.className = col.className;
                if (state.sortKey === col.key) th.setAttribute('aria-sort', state.sortDir === 'desc' ? 'descending' : 'ascending');
                appendTrackerFragment(th, columnHeaderHtml(col));
                headRow.appendChild(th);
            });
            head.appendChild(headRow);
        } else {
            refreshMenuButtons();
        }
        if (body) {
            body.replaceChildren();
            list.forEach(function (row) {
                var tr = document.createElement('tr');
                trackerBodyCells(row, cols).forEach(function (spec) { appendTrackerCell(tr, 'td', spec); });
                body.appendChild(tr);
            });
        }
        if (scroll) scroll.classList.remove('hidden');
        if (empty) {
            if (!list.length) {
                empty.textContent = t.noFilterMatch || 'No countries match these column filters.';
                empty.classList.remove('hidden');
            } else {
                empty.classList.add('hidden');
            }
        }
    }

    async function loadTrackerPeriods(preferredPeriod) {
        var templateId = getTemplateId();
        var periodEl = el('vd-tracker-period');
        if (!periodEl) return;
        await scopeLoader.loadPeriodsIntoSelect({
            selectEl: periodEl,
            periodsUrl: config.periodsUrl,
            templateId: templateId,
            preferredPeriod: preferredPeriod,
            emptyLabel: t.selectTemplatePeriod || 'Select template first',
            chooseLabel: 'Choose period',
        });
    }

    async function loadTrackerData() {
        var templateId = getTemplateId();
        var period = el('vd-tracker-period')?.value;
        if (!templateId || !period) {
            state.allRows = [];
            state.allMapCountries = [];
            state.trackerMeta = null;
            state.sectionsMeta = [];
            state.documentsMeta = [];
            state.requiredDocumentKeys = [];
            state.columnFilters = {};
            state.sortKey = 'country';
            state.sortDir = 'asc';
            state.rebuildTrackerHead = true;
            buildCountrySlicer([]);
            renderTrackerTable([]);
            renderStatusChart(null);
            renderMapCountries([]);
            renderTrackerLegend();
            return;
        }
        state.templateId = templateId;
        state.period = period;
        try {
            var url = config.trackerUrl + '?template_id=' + encodeURIComponent(templateId) +
                '&period=' + encodeURIComponent(period);
            var data = await window.apiFetch(url, { headers: { Accept: 'application/json' }, credentials: 'same-origin' });
            state.sectionsMeta = data.sections_meta || [];
            state.documentsMeta = data.documents_meta || [];
            state.requiredDocumentKeys = data.required_document_keys || [];
            state.delegationReviewEnabled = !!data.delegation_review_enabled;
            state.allRows = data.rows || [];
            state.allMapCountries = (data.map && data.map.countries) || [];
            state.trackerMeta = {
                reporting_year: data.stats && data.stats.reporting_year,
            };
            state.columnFilters = {};
            state.sortKey = 'country';
            state.sortDir = 'asc';
            state.rebuildTrackerHead = true;
            buildCountrySlicer(state.allRows);
            renderTrackerLegend();
            applyTrackerView();
            state.loaded = true;
            saveTrackerScope();
        } catch (err) {
            console.error(err);
            showFeedback(t.trackerLoadFailed || 'Tracker load failed', 'error');
        }
    }

    function saveTrackerScope() {
        try {
            localStorage.setItem(TRACKER_STORAGE_KEY, JSON.stringify({
                templateId: getTemplateId(),
                period: el('vd-tracker-period')?.value || '',
            }));
        } catch (err) { /* ignore */ }
    }

    function readTrackerScope() {
        try {
            var raw = localStorage.getItem(TRACKER_STORAGE_KEY);
            return raw ? JSON.parse(raw) : null;
        } catch (err) {
            return null;
        }
    }

    function onTrackerTabVisible() {
        setTimeout(function () {
            try {
                if (state.map) state.map.invalidateSize(true);
            } catch (err) { /* ignore */ }
            refreshChartLayout();
        }, 80);
    }

    function bindEvents() {
        el('vd-tracker-period')?.addEventListener('change', function () {
            loadTrackerData().catch(function (err) { console.error(err); });
        });

        countrySlicerEl()?.addEventListener('change', function () {
            state.rebuildTrackerHead = true;
            applyTrackerView();
        });

        fdsMemberSlicerEl()?.addEventListener('change', function () {
            state.rebuildTrackerHead = true;
            applyTrackerView();
        });

        el('vd-tracker-table')?.addEventListener('click', function (event) {
            var button = event.target.closest('.vd-col-menu-btn');
            if (!button || !el('vd-tracker-table').contains(button)) return;
            event.stopPropagation();
            openColumnMenu(button);
        });

        document.addEventListener('click', function (event) {
            var pop = document.getElementById('vd-col-popover');
            if (!pop || pop.contains(event.target)) return;
            closeColumnMenu();
        });

        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') closeColumnMenu();
        });

        el('vd-tracker-table')?.closest('.vd-table-scroll')?.addEventListener('scroll', function () {
            var pop = document.getElementById('vd-col-popover');
            var button = document.querySelector('.vd-col-menu-btn[aria-expanded="true"]');
            if (pop && button) positionColumnPopover(pop, button);
        });

        document.addEventListener('vd-main-tab-activated', function (e) {
            if (e.detail && e.detail.tab === 'tracker') {
                onTrackerTabVisible();
                if (!state.loaded && el('vd-tracker-period')?.value) {
                    loadTrackerData().catch(function (err) { console.error(err); });
                }
            }
        });
    }

    window.validationDashboardTracker = {
        onTemplateChanged: async function (preferredPeriod) {
            state.loaded = false;
            var saved = readTrackerScope();
            var period = preferredPeriod || (saved && saved.templateId === getTemplateId() ? saved.period : null);
            await loadTrackerPeriods(period);
            if (el('vd-tracker-period')?.value) {
                await loadTrackerData();
            } else {
                state.allRows = [];
                state.allMapCountries = [];
                buildCountrySlicer([]);
                renderTrackerTable([]);
                renderStatusChart(null);
                renderMapCountries([]);
                renderTrackerLegend();
            }
        },
        refreshIfActive: function () {
            var trackerPanel = el('panel-tracker');
            if (trackerPanel && !trackerPanel.classList.contains('hidden') && el('vd-tracker-period')?.value) {
                loadTrackerData().catch(function (err) { console.error(err); });
            }
        },
        invalidateMapSize: onTrackerTabVisible,
    };

    bindEvents();
    buildCountrySlicer([]);
    renderTrackerLegend();
    renderTrackerTable([]);
    renderStatusChart(null);

    (async function initTracker() {
        var saved = readTrackerScope();
        if (getTemplateId()) {
            await loadTrackerPeriods(saved && saved.templateId === getTemplateId() ? saved.period : null);
            var trackerPanel = el('panel-tracker');
            if (trackerPanel && !trackerPanel.classList.contains('hidden') && el('vd-tracker-period')?.value) {
                await loadTrackerData();
            }
        }
    })().catch(function (err) { console.error(err); });
})();
