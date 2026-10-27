/**
 * Emergency Operations — Snapshot Preview tab (AG Grid + filter pane).
 */
(function (global) {
  'use strict';

  var state = {
    loaded: false,
    allRows: [],
    gridHelper: null,
    gridApi: null,
    updatingFacets: false,
    yearBounds: {
      startMin: 2000,
      startMax: 2030,
      endMin: 2000,
      endMax: 2050,
    },
  };

  // Preview catalogue is scoped to this year floor (not a partial slider selection).
  var PREVIEW_YEAR_FLOOR = 2001;

  var FILTER_SELECT_IDS = [
    'snapshot-filter-region',
    'snapshot-filter-country',
    'snapshot-filter-appeal',
    'snapshot-filter-disaster',
  ];

  function rowInPreviewYearScope(row) {
    if (row.start_year != null && row.start_year < PREVIEW_YEAR_FLOOR) return false;
    if (row.end_year != null && row.end_year < PREVIEW_YEAR_FLOOR) return false;
    return true;
  }

  function $(id) {
    return document.getElementById(id);
  }

  function setText(id, val) {
    var el = $(id);
    if (el) el.textContent = val;
  }

  function uniqueSorted(values) {
    var seen = {};
    var out = [];
    (values || []).forEach(function (v) {
      var s = String(v == null ? '' : v).trim();
      if (!s || seen[s]) return;
      seen[s] = true;
      out.push(s);
    });
    out.sort(function (a, b) {
      return a.localeCompare(b, undefined, { sensitivity: 'base' });
    });
    return out;
  }

  function formatAmount(value) {
    if (value == null || value === '') return '—';
    var n = Number(value);
    if (!Number.isFinite(n)) return '—';
    return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
  }

  function fillSelect(selectEl, values, blankLabel, selected) {
    if (!selectEl) return;
    var keep = selected == null ? selectEl.value : selected;
    var html = '<option value="">' + (blankLabel || 'All') + '</option>';
    values.forEach(function (v) {
      html += '<option value="' + escapeAttr(v) + '">' + escapeHtml(v) + '</option>';
    });
    selectEl.innerHTML = html;
    if (keep && values.indexOf(keep) !== -1) selectEl.value = keep;
    else selectEl.value = '';
  }

  function fillMultiSelect(selectEl, values, selectedList) {
    if (!selectEl) return;
    var selected = {};
    (selectedList || []).forEach(function (v) {
      selected[v] = true;
    });
    var html = '';
    values.forEach(function (v) {
      html +=
        '<option value="' +
        escapeAttr(v) +
        '"' +
        (selected[v] ? ' selected' : '') +
        '>' +
        escapeHtml(v) +
        '</option>';
    });
    selectEl.innerHTML = html;
  }

  function escapeHtml(value) {
    if (global.SafeDom && typeof global.SafeDom.escapeHtml === 'function') {
      return global.SafeDom.escapeHtml(String(value == null ? '' : value));
    }
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function escapeAttr(value) {
    if (global.AgGridRenderers && typeof global.AgGridRenderers.escapeHtmlAttr === 'function') {
      return global.AgGridRenderers.escapeHtmlAttr(String(value == null ? '' : value));
    }
    return escapeHtml(value).replace(/`/g, '&#96;');
  }

  function selectedMultiValues(selectEl) {
    if (!selectEl) return [];
    if (global.jQuery && global.jQuery(selectEl).data('select2')) {
      var v = global.jQuery(selectEl).val();
      return Array.isArray(v) ? v.filter(Boolean) : v ? [v] : [];
    }
    return Array.prototype.slice
      .call(selectEl.selectedOptions || [])
      .map(function (o) {
        return o.value;
      })
      .filter(Boolean);
  }

  function computeYearBounds(rows) {
    var startYears = [];
    var endYears = [];
    rows.forEach(function (r) {
      if (r.start_year) startYears.push(r.start_year);
      if (r.end_year) endYears.push(r.end_year);
    });
    var startMin = startYears.length ? Math.min.apply(null, startYears) : 2000;
    var startMax = startYears.length ? Math.max.apply(null, startYears) : 2030;
    var endMin = endYears.length ? Math.min.apply(null, endYears) : startMin;
    var endMax = endYears.length ? Math.max.apply(null, endYears) : Math.max(startMax, 2050);
    if (startMin > startMax) startMax = startMin;
    if (endMin > endMax) endMax = endMin;
    state.yearBounds = { startMin: startMin, startMax: startMax, endMin: endMin, endMax: endMax };
  }

  function initYearRange(prefix, minBound, maxBound, selectedMin, selectedMax) {
    var minInput = $(prefix + '-min');
    var maxInput = $(prefix + '-max');
    var minRange = $(prefix + '-min-range');
    var maxRange = $(prefix + '-max-range');
    if (!minInput || !maxInput || !minRange || !maxRange) return;

    [minInput, maxInput, minRange, maxRange].forEach(function (el) {
      el.min = String(minBound);
      el.max = String(maxBound);
    });
    var lo = selectedMin == null ? minBound : selectedMin;
    var hi = selectedMax == null ? maxBound : selectedMax;
    lo = Math.max(minBound, Math.min(maxBound, lo));
    hi = Math.max(minBound, Math.min(maxBound, hi));
    if (lo > hi) lo = hi;
    minInput.value = String(lo);
    maxInput.value = String(hi);
    minRange.value = String(lo);
    maxRange.value = String(hi);
    syncYearRangeTrack(prefix);
  }

  function syncYearRangeTrack(prefix) {
    var wrap = document.querySelector('[data-eo-year-range="' + prefix.replace('snapshot-', '') + '"]');
    var minRange = $(prefix + '-min-range');
    var maxRange = $(prefix + '-max-range');
    if (!wrap || !minRange || !maxRange) return;
    var min = Number(minRange.min);
    var max = Number(maxRange.max);
    var lo = Number(minRange.value);
    var hi = Number(maxRange.value);
    if (max <= min) {
      wrap.style.setProperty('--eo-range-start', '0%');
      wrap.style.setProperty('--eo-range-end', '100%');
      return;
    }
    var startPct = ((lo - min) / (max - min)) * 100;
    var endPct = ((hi - min) / (max - min)) * 100;
    wrap.style.setProperty('--eo-range-start', startPct + '%');
    wrap.style.setProperty('--eo-range-end', endPct + '%');
  }

  function readYearRange(prefix) {
    var minInput = $(prefix + '-min');
    var maxInput = $(prefix + '-max');
    return {
      min: Number(minInput && minInput.value),
      max: Number(maxInput && maxInput.value),
    };
  }

  function bindYearRange(prefix) {
    var minInput = $(prefix + '-min');
    var maxInput = $(prefix + '-max');
    var minRange = $(prefix + '-min-range');
    var maxRange = $(prefix + '-max-range');
    if (!minInput || !maxInput || !minRange || !maxRange) return;

    function clampPair(lo, hi, boundMin, boundMax) {
      lo = Math.max(boundMin, Math.min(boundMax, lo));
      hi = Math.max(boundMin, Math.min(boundMax, hi));
      if (lo > hi) {
        var t = lo;
        lo = hi;
        hi = t;
      }
      return { lo: lo, hi: hi };
    }

    function fromInputs() {
      var boundMin = Number(minRange.min);
      var boundMax = Number(maxRange.max);
      var pair = clampPair(Number(minInput.value) || boundMin, Number(maxInput.value) || boundMax, boundMin, boundMax);
      minInput.value = String(pair.lo);
      maxInput.value = String(pair.hi);
      minRange.value = String(pair.lo);
      maxRange.value = String(pair.hi);
      syncYearRangeTrack(prefix);
      applyFilters();
    }

    function fromRanges(which) {
      var boundMin = Number(minRange.min);
      var boundMax = Number(maxRange.max);
      var lo = Number(minRange.value);
      var hi = Number(maxRange.value);
      if (which === 'min' && lo > hi) lo = hi;
      if (which === 'max' && hi < lo) hi = lo;
      var pair = clampPair(lo, hi, boundMin, boundMax);
      minInput.value = String(pair.lo);
      maxInput.value = String(pair.hi);
      minRange.value = String(pair.lo);
      maxRange.value = String(pair.hi);
      syncYearRangeTrack(prefix);
      applyFilters();
    }

    minInput.addEventListener('change', fromInputs);
    maxInput.addEventListener('change', fromInputs);
    minRange.addEventListener('input', function () {
      fromRanges('min');
    });
    maxRange.addEventListener('input', function () {
      fromRanges('max');
    });
  }

  function currentFilters() {
    return {
      region: ($('snapshot-filter-region') || {}).value || '',
      country: ($('snapshot-filter-country') || {}).value || '',
      appeal: ($('snapshot-filter-appeal') || {}).value || '',
      types: selectedMultiValues($('snapshot-filter-type')),
      disaster: ($('snapshot-filter-disaster') || {}).value || '',
      start: readYearRange('snapshot-start-year'),
      end: readYearRange('snapshot-end-year'),
    };
  }

  function rowMatches(row, f) {
    if (f.region && (row.region || '') !== f.region) return false;
    if (f.country && (row.country || '') !== f.country) return false;
    if (f.appeal && (row.code || '') !== f.appeal) return false;
    if (f.types && f.types.length && f.types.indexOf(row.type || '') === -1) return false;
    if (f.disaster && (row.disaster_type || '') !== f.disaster) return false;
    if (row.start_year != null) {
      if (Number.isFinite(f.start.min) && row.start_year < f.start.min) return false;
      if (Number.isFinite(f.start.max) && row.start_year > f.start.max) return false;
    }
    if (row.end_year != null) {
      if (Number.isFinite(f.end.min) && row.end_year < f.end.min) return false;
      if (Number.isFinite(f.end.max) && row.end_year > f.end.max) return false;
    }
    return true;
  }

  function filteredRows() {
    var f = currentFilters();
    return state.allRows.filter(function (row) {
      return rowMatches(row, f);
    });
  }

  function rowsForFacet(excludeKey) {
    var f = currentFilters();
    return state.allRows.filter(function (row) {
      var local = {
        region: excludeKey === 'region' ? '' : f.region,
        country: excludeKey === 'country' ? '' : f.country,
        appeal: excludeKey === 'appeal' ? '' : f.appeal,
        types: excludeKey === 'types' ? [] : f.types,
        disaster: excludeKey === 'disaster' ? '' : f.disaster,
        start: f.start,
        end: f.end,
      };
      return rowMatches(row, local);
    });
  }

  function destroySelect2Filters() {
    if (!global.jQuery || !global.jQuery.fn || !global.jQuery.fn.select2) return;
    var $ = global.jQuery;
    FILTER_SELECT_IDS.concat(['snapshot-filter-type']).forEach(function (id) {
      var $el = $('#' + id);
      if ($el.length && $el.data('select2')) {
        $el.off('change.eoSnapshot');
        $el.select2('destroy');
      }
    });
  }

  function refreshFacetOptions() {
    state.updatingFacets = true;

    var regionSelect = $('snapshot-filter-region');
    var countrySelect = $('snapshot-filter-country');
    var appealSelect = $('snapshot-filter-appeal');
    var typeSelect = $('snapshot-filter-type');
    var disasterSelect = $('snapshot-filter-disaster');
    var keepRegion = regionSelect && regionSelect.value;
    var keepCountry = countrySelect && countrySelect.value;
    var keepAppeal = appealSelect && appealSelect.value;
    var keepDisaster = disasterSelect && disasterSelect.value;
    var selectedTypes = selectedMultiValues(typeSelect);

    destroySelect2Filters();

    var regionRows = rowsForFacet('region');
    fillSelect(regionSelect, uniqueSorted(regionRows.map(function (r) { return r.region; })), 'All', keepRegion);

    var countryRows = rowsForFacet('country');
    fillSelect(countrySelect, uniqueSorted(countryRows.map(function (r) { return r.country; })), 'All', keepCountry);

    var appealRows = rowsForFacet('appeal');
    if (appealSelect) {
      var codes = [];
      var labels = {};
      appealRows.forEach(function (r) {
        if (!r.code || labels[r.code]) return;
        labels[r.code] = r.label || r.code + ' ' + (r.name || '');
        codes.push(r.code);
      });
      codes.sort(function (a, b) {
        return labels[a].localeCompare(labels[b], undefined, { sensitivity: 'base' });
      });
      var html = '<option value="">All</option>';
      codes.forEach(function (code) {
        html += '<option value="' + escapeAttr(code) + '">' + escapeHtml(labels[code]) + '</option>';
      });
      appealSelect.innerHTML = html;
      if (keepAppeal && labels[keepAppeal]) appealSelect.value = keepAppeal;
    }

    var typeRows = rowsForFacet('types');
    fillMultiSelect(typeSelect, uniqueSorted(typeRows.map(function (r) { return r.type; })), selectedTypes);

    var disasterRows = rowsForFacet('disaster');
    fillSelect(
      disasterSelect,
      uniqueSorted(disasterRows.map(function (r) { return r.disaster_type; })),
      'All',
      keepDisaster
    );

    initSelect2Filters();
    state.updatingFacets = false;
  }

  function initSelect2Filters() {
    if (!global.jQuery || !global.jQuery.fn || !global.jQuery.fn.select2) return;
    var $ = global.jQuery;
    var parent = $('.eo-snapshot-filters');
    FILTER_SELECT_IDS.forEach(function (id) {
      var el = $('#' + id);
      if (!el.length) return;
      if (el.data('select2')) el.select2('destroy');
      el.select2({
        width: '100%',
        allowClear: true,
        placeholder: 'All',
        dropdownParent: parent.length ? parent : $(document.body),
      });
    });
    var $type = $('#snapshot-filter-type');
    if ($type.length) {
      if ($type.data('select2')) $type.select2('destroy');
      $type.select2({
        width: '100%',
        closeOnSelect: false,
        placeholder: 'All',
        allowClear: true,
        dropdownParent: parent.length ? parent : $(document.body),
      });
    }
  }

  function applyFilters(opts) {
    opts = opts || {};
    if (state.updatingFacets) return;
    if (!opts.skipFacetRefresh) refreshFacetOptions();
    var rows = filteredRows();
    setText('snapshot-filtered-count', rows.length.toLocaleString());
    if (state.gridApi) {
      if (typeof state.gridApi.setGridOption === 'function') {
        state.gridApi.setGridOption('rowData', rows);
      } else if (typeof state.gridApi.setRowData === 'function') {
        state.gridApi.setRowData(rows);
      }
    }
    if (state.gridHelper && typeof state.gridHelper.setResultCountTotal === 'function') {
      state.gridHelper.setResultCountTotal(rows.length);
    }
    updateFiltersSummary();
  }

  function columnDefs() {
    return [
      { field: 'code', headerName: 'Code', minWidth: 110, width: 120, filter: 'agTextColumnFilter' },
      { field: 'name', headerName: 'Name', flex: 2, minWidth: 220, filter: 'agTextColumnFilter' },
      { field: 'type', headerName: 'Appeal Type', minWidth: 140, filter: 'customSetFilter' },
      { field: 'status', headerName: 'Status', minWidth: 110, width: 120, filter: 'customSetFilter' },
      { field: 'region', headerName: 'Region', minWidth: 140, filter: 'customSetFilter' },
      { field: 'country', headerName: 'Country', minWidth: 140, filter: 'customSetFilter' },
      { field: 'disaster_type', headerName: 'Disaster Type', minWidth: 140, filter: 'customSetFilter' },
      { field: 'start_date', headerName: 'Start', minWidth: 110, width: 120, filter: 'agTextColumnFilter' },
      {
        field: 'end_date',
        headerName: 'End',
        minWidth: 130,
        width: 140,
        filter: 'agTextColumnFilter',
        cellRenderer: function (p) {
          const end = p.value || '';
          if (!end) return '';
          if (p.data && p.data.end_date_overridden) {
            const src = p.data.source_end_date || '—';
            return (
              '<span title="Manual override (source: ' +
              String(src).replace(/"/g, '&quot;') +
              ')">' +
              String(end) +
              ' <span class="text-amber-600 text-xs font-semibold">*</span></span>'
            );
          }
          return String(end);
        },
      },
      {
        field: 'amount_requested',
        headerName: 'Requested',
        minWidth: 120,
        type: 'numericColumn',
        valueFormatter: function (p) {
          return formatAmount(p.value);
        },
      },
      {
        field: 'amount_funded',
        headerName: 'Funded',
        minWidth: 120,
        type: 'numericColumn',
        valueFormatter: function (p) {
          return formatAmount(p.value);
        },
      },
    ];
  }

  function ensureGrid(rows) {
    if (state.gridHelper) {
      applyFilters({ skipFacetRefresh: true });
      return;
    }
    if (typeof AgGridHelper === 'undefined' || typeof AgGridHelper.create !== 'function') {
      console.error('AgGridHelper is not loaded');
      return;
    }
    var created = AgGridHelper.create('eoSnapshotGrid', 'eo-snapshot-preview', columnDefs(), rows, {
      columnVisibility: { buttonPlaceholderId: 'eoSnapshotGrid-colvis' },
      height: { minHeight: 560, maxHeight: 560 },
      emptyMessage: 'No emergencies match these filters.',
      gridOptions: {
        pagination: true,
        paginationPageSize: 50,
        paginationPageSizeSelector: [25, 50, 100, 250],
        animateRows: true,
        defaultColDef: {
          sortable: true,
          resizable: true,
          filter: true,
        },
      },
    });
    state.gridHelper = created.helper;
    state.gridApi = created.api;
  }

  function loadSnapshotPreview() {
    var icon = $('snapshot-reload-icon');
    var emptyEl = $('snapshot-empty');
    var filtersEl = $('snapshot-filters');
    var gridWrap = $('snapshot-grid-wrap');
    if (icon) icon.classList.add('fa-spin');

    fetch('/admin/plugins/emergency_operations/api/data-cache/preview?all=1')
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        if (!data.success) {
          setText('snapshot-filtered-count', '—');
          return;
        }
        setText('snapshot-source', data.exists ? data.source || '—' : '—');
        setText('snapshot-fetched-at', data.exists ? data.fetched_at_display || '—' : 'Never');
        setText('snapshot-record-count', data.exists ? Number(data.record_count || 0).toLocaleString() : '—');

        if (!data.exists) {
          if (emptyEl) emptyEl.classList.remove('hidden');
          if (filtersEl) filtersEl.classList.add('hidden');
          if (gridWrap) gridWrap.classList.add('hidden');
          state.allRows = [];
          state.loaded = true;
          return;
        }

        if (emptyEl) emptyEl.classList.add('hidden');
        if (filtersEl) filtersEl.classList.remove('hidden');
        if (gridWrap) gridWrap.classList.remove('hidden');

        state.allRows = (data.rows || []).filter(rowInPreviewYearScope);
        computeYearBounds(state.allRows);
        // Slider full range = preview scope (handles at both ends).
        initYearRange(
          'snapshot-start-year',
          state.yearBounds.startMin,
          state.yearBounds.startMax
        );
        initYearRange(
          'snapshot-end-year',
          state.yearBounds.endMin,
          state.yearBounds.endMax
        );
        refreshFacetOptions();
        ensureGrid(filteredRows());
        applyFilters({ skipFacetRefresh: true });
        state.loaded = true;
      })
      .catch(function (err) {
        console.error('Snapshot preview load failed', err);
      })
      .finally(function () {
        if (icon) icon.classList.remove('fa-spin');
      });
  }

  function onFilterControlChange() {
    if (state.updatingFacets) return;
    applyFilters({ skipFacetRefresh: false });
  }

  function updateFiltersSummary() {
    var el = $('snapshot-filters-summary');
    if (!el) return;
    var f = currentFilters();
    var parts = [];
    if (f.region) parts.push(f.region);
    if (f.country) parts.push(f.country);
    if (f.appeal) parts.push(f.appeal);
    if (f.types && f.types.length) parts.push(f.types.length === 1 ? f.types[0] : f.types.length + ' types');
    if (f.disaster) parts.push(f.disaster);
    el.textContent = parts.length ? '· ' + parts.join(' · ') : '';
  }

  function setFiltersExpanded(expanded) {
    var toggle = $('snapshot-filters-toggle');
    var body = $('snapshot-filters-body');
    var chevron = $('snapshot-filters-chevron');
    if (!toggle || !body) return;
    toggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    body.classList.toggle('hidden', !expanded);
    if (chevron) chevron.classList.toggle('rotate-180', expanded);
  }

  function bindStaticFilters() {
    bindYearRange('snapshot-start-year');
    bindYearRange('snapshot-end-year');
    FILTER_SELECT_IDS.concat(['snapshot-filter-type']).forEach(function (id) {
      var el = $(id);
      if (!el || el.dataset.eoFilterBound === '1') return;
      el.dataset.eoFilterBound = '1';
      el.addEventListener('change', onFilterControlChange);
    });
    var toggle = $('snapshot-filters-toggle');
    if (toggle && toggle.dataset.eoFilterBound !== '1') {
      toggle.dataset.eoFilterBound = '1';
      toggle.addEventListener('click', function () {
        var open = toggle.getAttribute('aria-expanded') === 'true';
        setFiltersExpanded(!open);
      });
      setFiltersExpanded(false);
    }
    var reload = $('snapshot-reload-btn');
    if (reload) {
      reload.addEventListener('click', function () {
        state.loaded = false;
        loadSnapshotPreview();
      });
    }
  }

  function onSnapshotTabShown() {
    if (!state.loaded) loadSnapshotPreview();
    else if (state.gridApi && typeof state.gridApi.sizeColumnsToFit === 'function') {
      setTimeout(function () {
        try {
          state.gridApi.sizeColumnsToFit();
        } catch (e) {
          /* ignore */
        }
      }, 50);
    }
  }

  function markStale() {
    state.loaded = false;
  }

  global.EoSnapshotPreview = {
    load: loadSnapshotPreview,
    onTabShown: onSnapshotTabShown,
    markStale: markStale,
    init: function () {
      bindStaticFilters();
    },
  };
})(typeof window !== 'undefined' ? window : this);
