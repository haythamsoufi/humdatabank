/**
 * Validation dashboard — NS capacity discrepancies between planning and reporting.
 */
(function () {
    'use strict';

    var config = window.validationDashboardConfig || {};
    var t = window.VD_GRID_TRANSLATIONS || {};
    var payload = null;
    var loading = false;
    var failed = false;

    var MEASURE_LABELS = {
        volunteers: t.volunteers || 'Volunteers',
        staff: t.staff || 'Staff',
        branches: t.branches || 'Branches',
        local_units: t.localUnits || 'Local units',
    };

    var SEVERITY_BADGE = {
        attention: { variant: 'danger', label: t.capacityNeedsAttention || 'Needs attention' },
        review: { variant: 'warning', label: t.capacityReview || 'Variation' },
        aligned: { variant: 'success', label: t.capacityAligned || 'Aligned' },
        single: { variant: 'neutral', label: t.capacitySingle || 'One source' },
    };

    function el(id) { return document.getElementById(id); }

    var esc = window.esc || function (s) {
        if (s == null) return '';
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    };

    function formatCount(value) {
        if (value == null || value === '') return '—';
        var num = Number(value);
        if (!Number.isFinite(num)) return '—';
        return Math.round(num).toLocaleString(undefined, { maximumFractionDigits: 0 });
    }

    function badge(severity) {
        var spec = SEVERITY_BADGE[severity] || SEVERITY_BADGE.single;
        return '<span class="status-label status-label--' + spec.variant + '">' + esc(spec.label) + '</span>';
    }

    function numberCell(value, source, row) {
        var hot = row.hot || [];
        var flagged = hot.indexOf(source) !== -1;
        var cls = 'vd-num';
        if (flagged && row.severity === 'attention') cls += ' vd-cap-num-hot';
        else if (flagged) cls += ' vd-cap-num-review';
        return '<td class="' + cls + '">' + esc(formatCount(value)) + '</td>';
    }

    function measureLabel(row) {
        return MEASURE_LABELS[row.measure] || row.measure_label || row.measure;
    }

    function flaggedOnly() {
        return !!(el('vd-cap-flagged') && el('vd-cap-flagged').checked);
    }

    function filteredRows() {
        if (!payload) return [];
        var year = el('vd-cap-year')?.value || '';
        var measure = el('vd-cap-measure')?.value || '';
        var search = (el('vd-cap-search')?.value || '').trim().toLowerCase();
        var flagged = flaggedOnly();
        return (payload.rows || []).filter(function (row) {
            if (year && String(row.year) !== year) return false;
            if (measure && row.measure !== measure) return false;
            if (search) {
                var haystack = [row.country_name, row.iso3, row.region].join(' ').toLowerCase();
                if (haystack.indexOf(search) === -1) return false;
            }
            if (flagged && row.severity !== 'attention' && row.severity !== 'review') return false;
            return true;
        });
    }

    function renderSummary(rows) {
        var attention = 0;
        var review = 0;
        var discrepancies = 0;
        var variations = 0;
        var missing = 0;
        rows.forEach(function (row) {
            if (row.severity === 'attention') attention += 1;
            if (row.severity === 'review') review += 1;
            (row.flags || []).forEach(function (flag) {
                if (flag.kind === 'discrepancy') discrepancies += 1;
                else if (flag.kind === 'variation') variations += 1;
                else if (flag.kind === 'missing') missing += 1;
            });
        });
        if (el('vd-cap-attention')) el('vd-cap-attention').textContent = String(attention);
        if (el('vd-cap-discrepancies')) el('vd-cap-discrepancies').textContent = String(discrepancies);
        if (el('vd-cap-variations')) el('vd-cap-variations').textContent = String(variations);
        if (el('vd-cap-missing')) el('vd-cap-missing').textContent = String(missing);
        var sub = el('vd-cap-attention-sub');
        if (sub) {
            sub.textContent = review
                ? (String(review) + ' ' + (t.capacityReviewMore || 'more to review'))
                : '';
        }
    }

    function renderTable() {
        var body = document.querySelector('#vd-cap-table tbody');
        var empty = el('vd-cap-empty');
        if (!body || !empty) return;
        var rows = filteredRows();
        renderSummary(scopeRows());
        if (!payload) {
            body.innerHTML = '';
            empty.textContent = failed
                ? (t.capacityLoadFailed || 'Failed to load the capacity comparison')
                : (t.capacityEmpty || 'No capacity figures have been reported.');
            empty.classList.remove('hidden');
            return;
        }
        if (!rows.length) {
            body.innerHTML = '';
            var any = (payload.rows || []).length;
            var scoped = scopeRows();
            if (!any) {
                empty.textContent = t.capacityEmpty || 'No capacity figures have been reported.';
            } else if (flaggedOnly() && scoped.length) {
                empty.textContent = t.capacityEmptyFilter || 'No figures need attention for this filter.';
            } else {
                empty.textContent = t.capacityNoMatch || 'No figures match this filter.';
            }
            empty.classList.remove('hidden');
            return;
        }
        empty.classList.add('hidden');
        body.innerHTML = rows.map(function (row) {
            var rowClass = row.severity === 'attention'
                ? 'vd-row-flagged'
                : (row.severity === 'review' ? 'vd-row-review' : '');
            var flags = (row.flags || []).map(function (flag) {
                return '<li>' + esc(flag.text) + '</li>';
            }).join('');
            var country = esc(row.country_name || '');
            if (row.iso3) country += ' <span class="text-ifrc-gray-500">' + esc(row.iso3) + '</span>';
            return '<tr class="' + rowClass + '">' +
                '<td class="vd-sticky">' + country + '</td>' +
                '<td>' + esc(measureLabel(row)) + '</td>' +
                '<td class="vd-num">' + esc(row.year) + '</td>' +
                numberCell(row.plan, 'plan', row) +
                numberCell(row.annual, 'annual', row) +
                numberCell(row.midyear, 'midyear', row) +
                '<td class="vd-cell-wrap">' + badge(row.severity) +
                    (flags ? '<ul class="vd-cap-flags">' + flags + '</ul>' : '') +
                '</td></tr>';
        }).join('');
    }

    function scopeRows() {
        if (!payload) return [];
        var year = el('vd-cap-year')?.value || '';
        var measure = el('vd-cap-measure')?.value || '';
        var search = (el('vd-cap-search')?.value || '').trim().toLowerCase();
        return (payload.rows || []).filter(function (row) {
            if (year && String(row.year) !== year) return false;
            if (measure && row.measure !== measure) return false;
            if (search) {
                var haystack = [row.country_name, row.iso3, row.region].join(' ').toLowerCase();
                if (haystack.indexOf(search) === -1) return false;
            }
            return true;
        });
    }

    function fillSelect(selectEl, values, current, allLabel) {
        if (!selectEl) return;
        var html = '<option value="">' + esc(allLabel) + '</option>' + values.map(function (item) {
            var value = typeof item === 'object' ? item.key : item;
            var label = typeof item === 'object' ? (MEASURE_LABELS[item.key] || item.label) : item;
            return '<option value="' + esc(value) + '">' + esc(label) + '</option>';
        }).join('');
        selectEl.innerHTML = html;
        if (current && Array.prototype.some.call(selectEl.options, function (opt) { return opt.value === current; })) {
            selectEl.value = current;
        }
    }

    function populateFilters() {
        var year = el('vd-cap-year');
        var measure = el('vd-cap-measure');
        fillSelect(
            year,
            (payload && payload.years) || [],
            year ? year.value : '',
            t.capacityAllYears || 'All years'
        );
        fillSelect(
            measure,
            (payload && payload.measures) || [],
            measure ? measure.value : '',
            t.capacityAllFigures || 'All figures'
        );
    }

    async function loadCapacity() {
        if (loading || payload || !config.capacityUrl) return;
        loading = true;
        failed = false;
        var empty = el('vd-cap-empty');
        if (empty) {
            empty.textContent = '…';
            empty.classList.remove('hidden');
        }
        try {
            var data = await window.apiFetch(config.capacityUrl, {
                headers: { Accept: 'application/json' },
                credentials: 'same-origin',
            });
            payload = data || { rows: [], years: [], measures: [] };
            populateFilters();
            renderTable();
        } catch (err) {
            failed = true;
            payload = null;
            if (window.validationDashboardShowFeedback) {
                window.validationDashboardShowFeedback(
                    (err && err.message) || (t.capacityLoadFailed || 'Failed to load the capacity comparison'),
                    'error'
                );
            }
            renderTable();
        } finally {
            loading = false;
        }
    }

    function onTab(event) {
        if (!event.detail || event.detail.tab !== 'capacity') return;
        loadCapacity().catch(function (err) { console.error(err); });
    }

    document.addEventListener('vd-main-tab-activated', onTab);
    ['vd-cap-year', 'vd-cap-measure', 'vd-cap-flagged'].forEach(function (id) {
        el(id)?.addEventListener('change', renderTable);
    });
    el('vd-cap-search')?.addEventListener('input', renderTable);
})();
