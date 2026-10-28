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
    var cacheByKey = {};
    var emergenciesAbort = null;
    var sectionOpen = { single: true, grouped: true };
    var groupOpen = {};

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
        return row.name || row.code || '';
    }

    function organise(rows) {
        var parentNames = {};
        rows.forEach(function (row) {
            var parent = row.group_code || row.part_of || '';
            if (parent && row.code !== parent) parentNames[parent] = row.group_name || parentNames[parent] || '';
            if ((row.appeal_kind === 'group' || (!parent && parentNames[row.code])) && row.code) {
                parentNames[row.code] = row.group_name || row.name || parentNames[row.code] || '';
            }
        });
        rows.forEach(function (row) {
            var parent = row.group_code || row.part_of || '';
            if (parent && row.code !== parent) parentNames[parent] = row.group_name || parentNames[parent] || parent;
        });
        var singles = [];
        var groups = {};
        rows.forEach(function (row) {
            var parent = row.group_code || row.part_of || '';
            var isParent = row.appeal_kind === 'group' || (!!row.code && Object.prototype.hasOwnProperty.call(parentNames, row.code) && row.code !== parent);
            if (!parent && !isParent) {
                singles.push(row);
                return;
            }
            var key = isParent ? row.code : parent;
            var group = groups[key];
            if (!group) {
                group = groups[key] = { code: key, name: parentNames[key] || key, parents: [], children: [] };
            }
            if (row.group_name) group.name = row.group_name;
            else if (isParent && row.name) group.name = row.name;
            if (isParent) group.parents.push(row);
            else group.children.push(row);
        });
        var grouped = Object.keys(groups).map(function (key) { return groups[key]; });
        grouped.sort(function (a, b) { return String(a.name).localeCompare(String(b.name)); });
        return { singles: singles, groups: grouped };
    }

    function filteredRows() {
        var rows = (payload && payload.rows) || [];
        var status = el('vd-em-status')?.value || 'applicable';
        var search = (el('vd-em-search')?.value || '').trim().toLowerCase();
        return rows.filter(function (row) {
            if (status === 'funding_gap' && row.funding_check !== 'not_entered' && row.funding_check !== 'not_annualised') return false;
            if (status === 'applicable' && row.status !== 'covered' && row.status !== 'missing') return false;
            if (status === 'missing' && row.status !== 'missing') return false;
            if (status === 'covered' && row.status !== 'covered') return false;
            if (!search) return true;
            var haystack = [row.country_name, row.iso3, row.name, row.code, row.part_of, row.group_name, row.group_code].join(' ').toLowerCase();
            return haystack.indexOf(search) !== -1;
        });
    }

    function statEls() {
        return [
            el('vd-em-applicable'),
            el('vd-em-covered'),
            el('vd-em-missing'),
            el('vd-em-countries'),
        ].filter(Boolean);
    }

    function setLoadingUi(active) {
        var panel = el('panel-emergencies');
        var skeleton = el('vd-em-skeleton');
        var status = el('vd-em-loading-status');
        if (panel) panel.classList.toggle('is-loading-emergencies', !!active);
        if (skeleton) skeleton.classList.toggle('hidden', !active);
        statEls().forEach(function (node) {
            node.classList.toggle('is-loading', !!active);
        });
        if (status) {
            status.textContent = active ? (t.emergenciesLoading || 'Loading emergencies…') : '';
        }
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
        if (!loading) {
            statEls().forEach(function (node) { node.classList.remove('is-loading'); });
        }
    }

    function renderTable() {
        var table = el('vd-em-table');
        var empty = el('vd-em-empty');
        if (!table) return;
        var head = table.querySelector('thead');
        var body = table.querySelector('tbody');
        var sections = orderedSections((payload && payload.sections) || []);
        var plan = !!(payload && payload.plan_columns);
        var rows = filteredRows();
        renderSummary();
        if (head) {
            head.innerHTML = '<tr>' +
                columnHead(t.emergencyCountry || 'Country', 'databank', 'vd-sticky') +
                columnHead(t.emergencyName || 'Emergency', 'erp') +
                columnHead(t.emergencyCode || 'Code', 'erp') +
                columnHead(t.emergencyStatus || 'Coverage', 'databank', 'vd-em-flag') +
                sections.map(function (section) {
                    return columnHead(section, 'databank', 'vd-head-wrap vd-em-figure');
                }).join('') +
                (plan ? columnHead(t.emergencyRequested || 'Total Multiyear Requested', 'erp', 'vd-num vd-em-request') : '') +
                (plan ? columnHead(t.emergencyDuration || 'Duration', 'erp') : '') +
                (plan ? columnHead(t.emergencyFundingCheck || 'Annualised funding', ['databank', 'erp'], 'vd-em-flag') : '') +
                '</tr>';
        }
        if (body) body.innerHTML = renderBody(rows, sections, plan);
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

    function orderedSections(sections) {
        return sections.slice().sort(function (a, b) {
            return sectionRank(a) - sectionRank(b);
        });
    }

    function sectionRank(name) {
        var text = String(name || '').toLowerCase();
        if (text.indexOf('people to be reached') !== -1 || text.indexOf('emergency appeal') !== -1) return 0;
        if (text.indexOf('funding requirement') !== -1) return 1;
        return 2;
    }

    function sourceLabel(source) {
        if (source === 'erp') return t.sourceErp || 'ERP';
        if (source === 'go') return t.sourceGo || 'GO';
        return t.sourceDatabank || 'Databank';
    }

    function columnHead(label, source, className) {
        var sources = Array.isArray(source) ? source : [source];
        var chips = sources.map(function (item) {
            return '<span class="vd-em-source is-' + item + '">' + esc(sourceLabel(item)) + '</span>';
        }).join('');
        return '<th' + (className ? ' class="' + className + '"' : '') + '>' +
            '<span class="vd-em-head-label">' + esc(label) + '</span>' +
            '<span class="vd-em-sources">' + chips + '</span>' +
            '</th>';
    }

    function durationText(row) {
        var years = Number(row.duration_years);
        if (!Number.isFinite(years) || years <= 0) return '<span class="vd-muted">—</span>';
        var label = years === 1
            ? (t.emergencyOneYear || '1 year')
            : String(years) + ' ' + (t.emergencyYears || 'years');
        var from = row.duration_from;
        var to = row.duration_to;
        if (from && to && String(from) !== String(to)) {
            label += ' · ' + from + '–' + to;
        } else if (from) {
            label += ' · ' + from;
        }
        return esc(label);
    }

    function money(value) {
        if (value == null || value === '') return '<span class="vd-muted">—</span>';
        var num = Number(value);
        if (!Number.isFinite(num)) return '<span class="vd-muted">—</span>';
        return num.toLocaleString(undefined, { maximumFractionDigits: 0 });
    }

    function fundingBadge(status) {
        var spec = {
            not_annualised: ['warning', t.fundingNotAnnualised || 'Not annualised'],
            not_entered: ['warning', t.fundingNotEntered || 'Not reported'],
            entered: ['neutral', t.fundingEntered || 'Entered'],
        }[status];
        if (!spec) return '<span class="vd-muted">—</span>';
        return '<span class="status-label status-label--' + spec[0] + '">' + esc(spec[1]) + '</span>';
    }

    function foldAttrs(fold) {
        if (!fold) return '';
        var hidden = sectionOpen[fold.section] === false || (fold.group && groupOpen[fold.group] === false);
        return ' data-em-section="' + esc(fold.section) + '"' +
            (fold.group ? ' data-em-group="' + esc(fold.group) + '"' : '') +
            (hidden ? ' class="vd-em-collapsed"' : '');
    }

    function foldButton(label, kind, key) {
        var open = kind === 'section' ? sectionOpen[key] !== false : groupOpen[key] !== false;
        return '<button type="button" class="vd-em-fold" data-em-fold="' + kind + '" data-em-key="' + esc(key) +
            '" aria-expanded="' + (open ? 'true' : 'false') + '">' +
            '<i class="fas fa-chevron-right" aria-hidden="true"></i>' +
            '<span>' + label + '</span></button>';
    }

    function coverageState(row) {
        var marks = row.marks || {};
        var covered = false;
        var missing = false;
        Object.keys(marks).forEach(function (key) {
            if (marks[key] === 'covered') covered = true;
            if (marks[key] === 'missing') missing = true;
        });
        if (covered && missing) return 'partial';
        return row.status;
    }

    function coverageIcon(row) {
        var state = coverageState(row);
        var spec = {
            covered: ['fa-check', t.emergencyCovered || 'Covered'],
            missing: ['fa-times', t.emergencyMissing || 'Not covered'],
            partial: ['fa-minus', t.emergencyPartial || 'Partial'],
        }[state];
        if (!spec) return badge(state);
        return '<span class="vd-em-mark is-' + state + '" title="' + esc(spec[1]) + '" aria-label="' + esc(spec[1]) + '">' +
            '<i class="fas ' + spec[0] + '" aria-hidden="true"></i></span>';
    }

    function sectionCell(row, section) {
        var marks = row.marks || {};
        var figures = row.figures;
        var mark = marks[section];
        if (figures && Object.prototype.hasOwnProperty.call(figures, section) && (mark === 'covered' || mark === 'missing')) {
            var amount = figures[section];
            if (amount != null && Number(amount) > 0) return '<td class="vd-num">' + money(amount) + '</td>';
            return '<td class="vd-em-flag">' + fundingBadge('not_entered') + '</td>';
        }
        return '<td class="vd-em-flag">' + badge(mark) + '</td>';
    }

    function dataCells(row, sections, plan, child, fold) {
        var nameClass = child ? ' class="vd-em-child"' : '';
        var funding = '';
        if (plan) {
            funding = '<td class="vd-num">' + money(row.requested) + '</td>' +
                '<td>' + durationText(row) + '</td>' +
                '<td class="vd-em-flag">' + fundingBadge(row.funding_check) + '</td>';
        }
        return '<tr' + foldAttrs(fold) + '>' +
            '<td class="vd-sticky">' + esc(row.country_name || '') + '</td>' +
            '<td' + nameClass + '>' + esc(emergencyTitle(row)) + '</td>' +
            '<td class="vd-em-code">' + esc(row.code || '—') + '</td>' +
            '<td class="vd-em-flag">' + coverageIcon(row) + '</td>' +
            sections.map(function (section) {
                return sectionCell(row, section);
            }).join('') +
            funding +
            '</tr>';
    }

    function groupRequested(group) {
        var members = group.parents.concat(group.children);
        for (var i = 0; i < members.length; i++) {
            if (members[i].group_requested) return members[i].group_requested;
            if (members[i].appeal_kind === 'group' && members[i].requested) return members[i].requested;
        }
        return null;
    }

    function appealCount(count) {
        return count + ' ' + (count === 1 ? (t.emergencyOne || 'appeal') : (t.emergencyMany || 'appeals'));
    }

    function groupCount(count) {
        return count + ' ' + (count === 1 ? (t.emergencyGroup || 'group') : (t.emergencyGroups || 'groups'));
    }

    function bandRow(label, meta, span, key) {
        var count = meta ? '<span class="vd-em-band-count">' + esc(meta) + '</span>' : '';
        return '<tr class="vd-em-band"><td colspan="' + span + '">' +
            foldButton(esc(label) + count, 'section', key) + '</td></tr>';
    }

    function groupHeader(group, sections, plan) {
        var title = group.name || group.code;
        var hidden = sectionOpen.grouped === false ? ' vd-em-collapsed' : '';
        var funding = '';
        if (plan) {
            funding = '<td class="vd-num vd-em-group-amount">' + money(groupRequested(group)) + '</td><td></td><td></td>';
        }
        return '<tr class="vd-em-group' + hidden + '" data-em-section="grouped">' +
            '<td class="vd-sticky"></td>' +
            '<td>' + foldButton(
                '<span class="vd-em-group-name">' + esc(title) + '</span>',
                'group',
                group.code
            ) + '</td>' +
            '<td class="vd-em-code">' + esc(group.code || '') + '</td>' +
            '<td></td>' +
            sections.map(function () { return '<td></td>'; }).join('') +
            funding +
            '</tr>';
    }

    function renderBody(rows, sections, plan) {
        var span = 4 + sections.length + (plan ? 3 : 0);
        var organised = organise(rows);
        var html = '';
        if (organised.singles.length) {
            html += bandRow(
                t.emergencySingles || 'Single appeals',
                appealCount(organised.singles.length),
                span,
                'single'
            );
            organised.singles.forEach(function (row) {
                html += dataCells(row, sections, plan, false, { section: 'single' });
            });
        }
        if (organised.groups.length) {
            var groupedAppeals = organised.groups.reduce(function (sum, group) {
                return sum + group.parents.length + group.children.length;
            }, 0);
            html += bandRow(
                t.emergencyGrouped || 'Grouped appeals',
                groupCount(organised.groups.length) + ' · ' + appealCount(groupedAppeals),
                span,
                'grouped'
            );
            organised.groups.forEach(function (group) {
                html += groupHeader(group, sections, plan);
                group.parents.concat(group.children).forEach(function (row) {
                    html += dataCells(row, sections, plan, true, { section: 'grouped', group: group.code });
                });
            });
        }
        return html;
    }

    async function exportExcel() {
        var button = el('vd-em-export');
        if (!payload || !config.emergenciesExportUrl || !button) return;
        var round = selectedRound();
        var option = el('vd-em-period') && el('vd-em-period').selectedOptions && el('vd-em-period').selectedOptions[0];
        var roundLabel = (option && option.text) || (round && round.period) || '';
        button.disabled = true;
        try {
            var response = await window.apiFetch(config.emergenciesExportUrl, {
                method: 'POST',
                parseJson: false,
                headers: { 'Content-Type': 'application/json', Accept: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' },
                body: JSON.stringify({
                    round_label: roundLabel,
                    period: round && round.period,
                    sections: payload.sections || [],
                    plan_columns: !!payload.plan_columns,
                    rows: filteredRows(),
                }),
            });
            var blob = await response.blob();
            var slug = String(roundLabel || 'round').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
            var link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = 'upr-emergencies-' + (slug || 'round') + '.xlsx';
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(link.href);
        } catch (err) {
            if (window.validationDashboardShowFeedback) {
                window.validationDashboardShowFeedback(
                    (err && err.message) || (t.emergenciesExportFailed || 'Failed to export emergencies'),
                    'error'
                );
            }
        } finally {
            button.disabled = false;
        }
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

    async function loadEmergencies(options) {
        var force = !!(options && options.force);
        var round = selectedRound();
        if (!round || !config.emergenciesUrl) {
            payload = null;
            loadedKey = '';
            setLoadingUi(false);
            renderTable();
            return;
        }
        if (!force && cacheByKey[round.key]) {
            payload = cacheByKey[round.key];
            loadedKey = round.key;
            setLoadingUi(false);
            renderTable();
            return;
        }
        if (loading && loadedKey === round.key) return;
        if (emergenciesAbort) emergenciesAbort.abort();
        var controller = new AbortController();
        emergenciesAbort = controller;
        loading = true;
        loadedKey = round.key;
        var empty = el('vd-em-empty');
        if (empty) empty.classList.add('hidden');
        setLoadingUi(true);
        try {
            var url = config.emergenciesUrl +
                '?template_id=' + encodeURIComponent(round.templateId) +
                '&period=' + encodeURIComponent(round.period);
            var data = await window.apiFetch(url, {
                headers: { Accept: 'application/json' },
                credentials: 'same-origin',
                signal: controller.signal,
            });
            if (emergenciesAbort !== controller || loadedKey !== round.key) return;
            payload = data || { rows: [], sections: [], summary: {} };
            cacheByKey[round.key] = payload;
            renderTable();
        } catch (err) {
            if (controller.signal.aborted || (err && err.name === 'AbortError')) return;
            if (emergenciesAbort !== controller || loadedKey !== round.key) return;
            payload = null;
            if (window.validationDashboardShowFeedback) {
                window.validationDashboardShowFeedback(
                    (err && err.message) || (t.emergenciesLoadFailed || 'Failed to load emergencies'),
                    'error'
                );
            }
            renderTable();
        } finally {
            if (emergenciesAbort === controller) {
                loading = false;
                setLoadingUi(false);
            }
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
        if (window.validationDashboardSyncTemplate) window.validationDashboardSyncTemplate();
        if (window.validationDashboardTracker && window.validationDashboardTracker.markStale) {
            window.validationDashboardTracker.markStale();
        }
        loadEmergencies({ force: true }).catch(function (err) { console.error(err); });
    });

    el('vd-tracker-period')?.addEventListener('change', function () {
        if (!panelVisible()) {
            loadedKey = '';
            return;
        }
        loadEmergencies({ force: true }).catch(function (err) { console.error(err); });
    });

    el('vd-em-status')?.addEventListener('change', renderTable);
    el('vd-em-search')?.addEventListener('input', renderTable);
    el('vd-em-export')?.addEventListener('click', function () {
        exportExcel().catch(function (err) { console.error(err); });
    });
    el('vd-em-table')?.addEventListener('click', function (event) {
        var button = event.target.closest('.vd-em-fold');
        if (!button || !el('vd-em-table').contains(button)) return;
        var key = button.getAttribute('data-em-key');
        var open = button.getAttribute('aria-expanded') !== 'true';
        if (button.getAttribute('data-em-fold') === 'section') sectionOpen[key] = open;
        else groupOpen[key] = open;
        applyFolds();
    });

    function applyFolds() {
        var table = el('vd-em-table');
        if (!table) return;
        table.querySelectorAll('.vd-em-fold').forEach(function (button) {
            var key = button.getAttribute('data-em-key');
            var open = button.getAttribute('data-em-fold') === 'section'
                ? sectionOpen[key] !== false
                : groupOpen[key] !== false;
            button.setAttribute('aria-expanded', open ? 'true' : 'false');
        });
        table.querySelectorAll('[data-em-section]').forEach(function (row) {
            var section = row.getAttribute('data-em-section');
            var group = row.getAttribute('data-em-group');
            var hidden = sectionOpen[section] === false || (group && groupOpen[group] === false);
            row.classList.toggle('vd-em-collapsed', hidden);
        });
    }
})();
