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
        trackerApi: null,
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
    };

    function el(id) { return document.getElementById(id); }

    function esc(s) {
        if (s == null) return '';
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

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
        var map = {
            governance: t.governance || 'Governance',
            finance: t.finance || 'Finance',
            reach: t.reach || 'Reach',
        };
        var meta = (state.sectionsMeta || []).find(function (m) { return m.key === key; });
        return (meta && meta.label) || map[key] || key;
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
        (state.sectionsMeta.length ? state.sectionsMeta : [{ key: 'governance' }, { key: 'finance' }, { key: 'reach' }])
            .forEach(function (spec) { sectionComplete[spec.key] = 0; });

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
            if (docs.annual_report && docs.audited_financial) docsBoth++;
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

    function getFilteredRows() {
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
        initTrackerGrid(filtered);
        renderStatusChart(filtered.length ? computeStatsFromRows(filtered) : null);
        renderMapCountries(getFilteredMapCountries(filtered));
    }

    function trackerColumnDefs() {
        var cols = [
            { field: 'region', headerName: t.region || 'Region', width: 125, minWidth: 115, filter: 'agTextColumnFilter', pinned: 'left' },
            { field: 'country_name', headerName: t.country || 'Country', flex: 1, minWidth: 175, filter: 'agTextColumnFilter', pinned: 'left' },
            {
                field: 'status',
                headerName: t.status || 'Status',
                width: 140,
                minWidth: 130,
                filter: 'customSetFilter',
                valueGetter: function (p) {
                    var d = p.data || {};
                    return d.status_label || statusLabel(d.status) || d.status || '';
                },
                cellRenderer: function (p) {
                    var d = p.data || {};
                    return statusBadge(d.status, d.status_label);
                },
            },
            {
                field: 'completion_rate',
                headerName: t.completionRate || 'Completion rate',
                width: 118,
                minWidth: 108,
                maxWidth: 140,
                filter: 'agNumberColumnFilter',
                cellClass: 'compliance-cell-center',
                headerClass: 'compliance-header-center',
                valueGetter: function (p) {
                    var rate = p.data && p.data.completion_rate;
                    return rate == null || rate === '' ? null : Number(rate);
                },
                cellRenderer: function (p) {
                    return completionRateCell(p.data && p.data.completion_rate);
                },
            },
        ];

        var sectionMeta = state.sectionsMeta.length ? state.sectionsMeta : [
            { key: 'governance', label: t.governance || 'Governance' },
            { key: 'finance', label: t.finance || 'Finance' },
            { key: 'reach', label: t.reach || 'Reach' },
        ];
        sectionMeta.forEach(function (spec) {
            var isGovernance = spec.key === 'governance';
            cols.push({
                colId: 'section_' + spec.key,
                headerName: spec.label || sectionLabelForKey(spec.key),
                width: isGovernance ? 126 : 108,
                minWidth: isGovernance ? 118 : 100,
                maxWidth: isGovernance ? 152 : 136,
                filter: 'customSetFilter',
                cellClass: 'compliance-cell-center',
                headerClass: 'compliance-header-center',
                valueGetter: function (p) {
                    var sections = (p.data && p.data.sections) || {};
                    return sectionStatusLabel(sections[spec.key]);
                },
                cellRenderer: function (p) {
                    var sections = (p.data && p.data.sections) || {};
                    return sectionStatusIcon(sections[spec.key]);
                },
            });
        });

        var docMeta = state.documentsMeta.length ? state.documentsMeta : [
            { key: 'annual_report', label: 'Annual Report' },
            { key: 'audited_financial', label: 'Audited Financial Statement' },
            { key: 'strategic_plan', label: 'Strategic Plan' },
            { key: 'unaudited_financial', label: 'Unaudited Financial Statement' },
        ];
        docMeta.forEach(function (doc) {
            var isFinancialStatement = doc.key === 'audited_financial' || doc.key === 'unaudited_financial';
            var isStrategicPlan = doc.key === 'strategic_plan';
            var width = isFinancialStatement ? 120 : (isStrategicPlan ? 112 : 100);
            var minWidth = isFinancialStatement ? 112 : (isStrategicPlan ? 104 : 92);
            var maxWidth = isFinancialStatement ? 152 : (isStrategicPlan ? 148 : 140);
            cols.push({
                colId: 'doc_' + doc.key,
                headerName: doc.label,
                width: width,
                minWidth: minWidth,
                maxWidth: maxWidth,
                filter: 'customSetFilter',
                cellClass: 'compliance-cell-center',
                headerClass: 'compliance-header-center',
                valueGetter: function (p) {
                    var docs = (p.data && p.data.documents) || {};
                    return docs[doc.key] ? (t.uploaded || 'Uploaded') : (t.missing || 'Missing');
                },
                cellRenderer: function (p) {
                    var docs = (p.data && p.data.documents) || {};
                    return boolIcon(!!docs[doc.key]);
                },
            });
        });

        return cols;
    }

    function initTrackerGrid(rows) {
        if (state.trackerApi) {
            state.trackerApi.setGridOption('columnDefs', trackerColumnDefs());
            state.trackerApi.setGridOption('rowData', rows);
            state.trackerApi.setGridOption('pagination', false);
            if (typeof state.trackerApi.refreshHeader === 'function') {
                state.trackerApi.refreshHeader();
            }
            return;
        }
        var result = AgGridHelper.create('validationTrackerGrid', 'admin-validation-tracker', trackerColumnDefs(), rows, {
            showResultCount: false,
            columnVisibilityOptions: { buttonPlaceholderId: 'vd-tracker-col-vis', enableExport: true },
            sizeColumnsToFitOnInit: false,
            gridOptions: {
                pagination: false,
                defaultColDef: {
                    suppressSizeToFit: true,
                    wrapHeaderText: true,
                    autoHeaderHeight: true,
                },
                onFirstDataRendered: function (params) {
                    AgGridHelper.enforceColumnMinWidths(params.api);
                },
            },
        });
        state.trackerApi = result.api;
    }

    async function loadTrackerPeriods(preferredPeriod) {
        var templateId = getTemplateId();
        var periodEl = el('vd-tracker-period');
        if (!periodEl) return;
        if (!templateId) {
            periodEl.innerHTML = '<option value="">' + esc(t.selectTemplatePeriod || 'Select template first') + '</option>';
            periodEl.disabled = true;
            return;
        }
        periodEl.disabled = true;
        try {
            var data = await window.apiFetch(config.periodsUrl + '?template_id=' + encodeURIComponent(templateId), {
                headers: { Accept: 'application/json' },
                credentials: 'same-origin',
            });
            var periods = data.periods || [];
            periodEl.innerHTML = '<option value="">' + esc('Choose period') + '</option>' +
                periods.map(function (p) { return '<option value="' + esc(p) + '">' + esc(p) + '</option>'; }).join('');
            periodEl.disabled = !periods.length;
            if (preferredPeriod) {
                var found = Array.prototype.some.call(periodEl.options, function (opt) {
                    if (opt.value === String(preferredPeriod)) {
                        periodEl.value = preferredPeriod;
                        return true;
                    }
                    return false;
                });
                if (!found && periods.length) periodEl.value = periods[0];
            } else if (!periodEl.value && periods.length) {
                periodEl.value = periods[0];
            }
        } catch (err) {
            console.error(err);
        }
    }

    async function loadTrackerData() {
        var templateId = getTemplateId();
        var period = el('vd-tracker-period')?.value;
        if (!templateId || !period) {
            state.allRows = [];
            state.allMapCountries = [];
            state.trackerMeta = null;
            buildCountrySlicer([]);
            initTrackerGrid([]);
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
            state.delegationReviewEnabled = !!data.delegation_review_enabled;
            state.allRows = data.rows || [];
            state.allMapCountries = (data.map && data.map.countries) || [];
            state.trackerMeta = {
                reporting_year: data.stats && data.stats.reporting_year,
            };
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
            applyTrackerView();
        });

        fdsMemberSlicerEl()?.addEventListener('change', function () {
            applyTrackerView();
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
                initTrackerGrid([]);
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
    initTrackerGrid([]);
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
