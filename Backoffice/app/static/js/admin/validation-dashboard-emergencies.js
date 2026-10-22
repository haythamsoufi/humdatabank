/**
 * Validation dashboard — UPR emergencies applicable to a round, marked covered or not.
 */
(function () {
    'use strict';

    var config = window.validationDashboardConfig || {};
    var t = window.VD_GRID_TRANSLATIONS || {};
    var scopeLoader = window.ValidationScopeLoader || {};
    var payload = null;
    var loadedKey = '';
    var loading = false;

    var MARK_LABEL = {
        covered: t.emergencyCovered || 'Covered',
        missing: t.emergencyMissing || 'Not covered',
        not_applicable: t.emergencyNotApplicable || 'Not applicable',
        no_longer: t.emergencyNoLonger || 'No longer applicable',
    };
    var MARK_VARIANT = {
        covered: 'success',
        missing: 'warning',
        not_applicable: 'neutral',
        no_longer: 'warning',
    };

    function el(id) { return document.getElementById(id); }

    var esc = window.esc || function (s) {
        if (s == null) return '';
        return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    };

    function selectedRound() {
        var selectEl = el('vd-em-period');
        var opt = selectEl && selectEl.selectedOptions && selectEl.selectedOptions[0];
        if (!opt) return null;
        var templateId = opt.getAttribute('data-template-id');
        var period = opt.getAttribute('data-period') || (scopeLoader.selectedPeriod ? scopeLoader.selectedPeriod(selectEl) : '');
        if (!templateId || !period) return null;
        return { templateId: templateId, period: period, key: templateId + '::' + period };
    }

    function badge(status) {
        if (!status || !MARK_LABEL[status]) return '<span class="vd-muted">—</span>';
        return '<span class="status-label status-label--' + MARK_VARIANT[status] + '">' + esc(MARK_LABEL[status]) + '</span>';
    }

    function emergencyTitle(row) {
        var bits = [row.name || row.code || ''];
        if (row.part_of) bits.push((t.partOf || 'part of') + ' ' + row.part_of);
        return bits.filter(Boolean).join(' · ');
    }

    function filteredRows() {
        var rows = (payload && payload.rows) || [];
        var status = el('vd-em-status')?.value || 'applicable';
        var search = (el('vd-em-search')?.value || '').trim().toLowerCase();
        return rows.filter(function (row) {
            if (status === 'applicable' && row.status !== 'covered' && row.status !== 'missing') return false;
            if (status === 'missing' && row.status !== 'missing') return false;
            if (status === 'covered' && row.status !== 'covered') return false;
            if (!search) return true;
            var haystack = [row.country_name, row.iso3, row.name, row.code, row.part_of].join(' ').toLowerCase();
            return haystack.indexOf(search) !== -1;
        });
    }

    function renderSummary() {
        var summary = (payload && payload.summary) || {};
        var applicable = el('vd-em-applicable');
        var covered = el('vd-em-covered');
        var missing = el('vd-em-missing');
        var countries = el('vd-em-countries');
        if (applicable) applicable.textContent = payload ? String(summary.applicable || 0) : '—';
        if (covered) covered.textContent = payload ? String(summary.covered || 0) : '—';
        if (missing) missing.textContent = payload ? String(summary.missing || 0) : '—';
        if (countries) countries.textContent = payload ? String(summary.countries || 0) : '—';
    }

    function renderTable() {
        var table = el('vd-em-table');
        var empty = el('vd-em-empty');
        if (!table) return;
        var head = table.querySelector('thead');
        var body = table.querySelector('tbody');
        var sections = (payload && payload.sections) || [];
        var rows = filteredRows();
        renderSummary();
        if (head) {
            head.innerHTML = '<tr>' +
                '<th class="vd-sticky">' + esc(t.emergencyCountry || 'Country') + '</th>' +
                '<th>' + esc(t.emergencyName || 'Emergency') + '</th>' +
                '<th>' + esc(t.emergencyCode || 'Code') + '</th>' +
                sections.map(function (section) {
                    return '<th class="vd-head-wrap">' + esc(section) + '</th>';
                }).join('') +
                '<th>' + esc(t.emergencyStatus || 'Coverage') + '</th>' +
                '</tr>';
        }
        if (body) {
            body.innerHTML = rows.map(function (row) {
                var marks = row.marks || {};
                return '<tr>' +
                    '<td class="vd-sticky">' + esc(row.country_name || '') + '</td>' +
                    '<td>' + esc(emergencyTitle(row)) + '</td>' +
                    '<td class="vd-em-code">' + esc(row.code || '—') + '</td>' +
                    sections.map(function (section) {
                        return '<td>' + badge(marks[section]) + '</td>';
                    }).join('') +
                    '<td>' + badge(row.status) + '</td>' +
                    '</tr>';
            }).join('');
        }
        if (!empty) return;
        if (!payload) {
            empty.textContent = t.emergenciesEmpty || 'Choose a round to see its emergencies.';
            empty.classList.remove('hidden');
            return;
        }
        if (payload.available === false && !rows.length) {
            empty.textContent = t.emergenciesUnavailable || 'The emergency list is not available yet.';
            empty.classList.remove('hidden');
            return;
        }
        if (!rows.length) {
            var hasRows = payload.rows && payload.rows.length;
            empty.textContent = hasRows
                ? (t.emergenciesEmptyFilter || 'No emergencies match this filter.')
                : (t.emergenciesEmpty || 'No emergencies apply to this round.');
            empty.classList.remove('hidden');
            return;
        }
        empty.classList.add('hidden');
    }

    async function ensureRounds() {
        var selectEl = el('vd-em-period');
        if (!selectEl || !scopeLoader.loadRoundsIntoSelect) return;
        if (selectEl.options.length > 1) return;
        var tracker = el('vd-tracker-period');
        var preferred = scopeLoader.selectedPeriod ? scopeLoader.selectedPeriod(tracker) : '';
        var trackerOpt = tracker && tracker.selectedOptions && tracker.selectedOptions[0];
        await scopeLoader.loadRoundsIntoSelect({
            selectEl: selectEl,
            roundsUrl: config.roundsUrl,
            preferredPeriod: preferred,
            preferredTemplateId: (trackerOpt && trackerOpt.getAttribute('data-template-id')) || (el('vd-template') && el('vd-template').value) || '',
        });
    }

    async function loadEmergencies() {
        var round = selectedRound();
        if (!round || !config.emergenciesUrl) {
            payload = null;
            loadedKey = '';
            renderTable();
            return;
        }
        if (loading && loadedKey === round.key) return;
        loading = true;
        loadedKey = round.key;
        var empty = el('vd-em-empty');
        if (empty) {
            empty.textContent = '…';
            empty.classList.remove('hidden');
        }
        try {
            var url = config.emergenciesUrl +
                '?template_id=' + encodeURIComponent(round.templateId) +
                '&period=' + encodeURIComponent(round.period);
            var data = await window.apiFetch(url, {
                headers: { Accept: 'application/json' },
                credentials: 'same-origin',
            });
            if (loadedKey !== round.key) return;
            payload = data || { rows: [], sections: [], summary: {} };
            renderTable();
        } catch (err) {
            if (loadedKey !== round.key) return;
            payload = null;
            if (window.validationDashboardShowFeedback) {
                window.validationDashboardShowFeedback(
                    (err && err.message) || (t.emergenciesLoadFailed || 'Failed to load emergencies'),
                    'error'
                );
            }
            renderTable();
        } finally {
            loading = false;
        }
    }

    function panelVisible() {
        var panel = el('panel-emergencies');
        return !!(panel && !panel.classList.contains('hidden'));
    }

    document.addEventListener('vd-main-tab-activated', function (event) {
        if (!event.detail || event.detail.tab !== 'emergencies') return;
        ensureRounds().then(loadEmergencies).catch(function (err) { console.error(err); });
    });

    el('vd-em-period')?.addEventListener('change', function () {
        if (scopeLoader.commitRoundSelection) scopeLoader.commitRoundSelection(this);
        if (window.validationDashboardTracker && window.validationDashboardTracker.markStale) {
            window.validationDashboardTracker.markStale();
        }
        loadEmergencies().catch(function (err) { console.error(err); });
    });

    el('vd-tracker-period')?.addEventListener('change', function () {
        if (!panelVisible()) {
            loadedKey = '';
            return;
        }
        loadEmergencies().catch(function (err) { console.error(err); });
    });

    el('vd-em-status')?.addEventListener('change', renderTable);
    el('vd-em-search')?.addEventListener('input', renderTable);
})();
