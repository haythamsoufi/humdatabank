/*
 * NSD report forms (plugin nsd_report_forms).
 *
 * 1. The prefilled "Expected spending" cell and the project information are read-only.
 * 2. Repeat sections (action points) start with no entry: only "Add Entry" shows.
 *    The first click reveals the first entry instead of creating a second one.
 *
 * 3. The implementation selectors show as green / amber / red cards (as in MOMO).
 *    The original select stays in the page (hidden) and keeps holding the answer.
 * 4. Dates in the read-only project information show as dd/mm/yyyy.
 *
 * Runs on top of the core entry form; it only touches the DOM and adds no data.
 */
(function () {
    'use strict';

    var LOCKED_COLUMNS = ['Expected spending (CHF)'];
    // project information written by the importer; shown as plain, locked text
    var LOCKED_LABELS = ['National Society', 'Title', 'Reference', 'Funding Modality', 'Categories/Thematics', 'Start Date',
        'End Date', 'Amount Granted (in CHF)', 'NS Focal Person', 'IFRC Project Manager', 'Level of implementation',
        'Current Year', 'Sub-Thematic', 'Annual approved budget', 'ICRC Liaison', 'Overview of the initiative as planned'];

    function existingData() {
        try {
            var el = document.getElementById('existing-data');
            return el ? JSON.parse(el.textContent) || {} : {};
        } catch (e) {
            return {};
        }
    }

    function sectionHasSavedEntries(sectionId, data) {
        var prefix = 'repeat_' + sectionId + '_';
        return Object.keys(data).some(function (k) {
            var v = data[k];
            return k.indexOf(prefix) === 0 && v !== null && v !== '' && !(Array.isArray(v) && !v.length);
        });
    }

    // ---- 1. read-only carried-forward cells ---------------------------------
    function lockCarriedCells() {
        LOCKED_COLUMNS.forEach(function (col) {
            document.querySelectorAll('input[data-column="' + col + '"]').forEach(function (input) {
                if (input.dataset.nsdLocked) return;
                input.dataset.nsdLocked = '1';
                input.readOnly = true;
                input.tabIndex = -1;
                input.title = 'Filled in from the approved budget';
                input.style.backgroundColor = '#f3f4f6';
                input.style.cursor = 'not-allowed';
            });
        });
    }

    function lockInfoFields() {
        document.querySelectorAll('.form-item-block').forEach(function (block) {
            var label = block.querySelector('label');
            if (!label || LOCKED_LABELS.indexOf(label.textContent.replace('*', '').trim()) === -1) return;
            block.querySelectorAll('input[type="text"],textarea').forEach(function (el) {
                el.readOnly = true;
                el.tabIndex = -1;
                el.classList.add('nsd-info-value');
                if (el.tagName === 'TEXTAREA') {
                    el.rows = 1;
                    el.style.height = 'auto';
                    if (el.scrollHeight) el.style.height = el.scrollHeight + 'px';
                }
            });
        });
    }

    // ---- 2. repeat sections start empty -------------------------------------
    function setupRepeatSection(section, data) {
        var id = section.id.replace('section-container-', '');
        if (section.dataset.nsdRepeatReady) return;
        var entries = document.getElementById('repeat-entries-' + id);
        if (!entries || !entries.querySelector('.repeat-entry')) return; // core not ready yet
        section.dataset.nsdRepeatReady = '1';

        // Core leaves a duplicate copy of the first entry's fields above the entries;
        // hide it and keep it out of the submitted form.
        // (works for top-level sections and for sub-sections, which have no collapsible-content wrapper)
        Array.prototype.forEach.call(section.querySelectorAll('[data-layout-row]'), function (row) {
            if (row.closest('.repeat-entry')) return;
            if (row.closest('[data-section-type]') !== section) return;
            row.style.setProperty('display', 'none', 'important');
            row.querySelectorAll('input,textarea,select').forEach(function (i) { i.disabled = true; });
        });

        if (sectionHasSavedEntries(id, data)) return;
        var first = entries.querySelector('.repeat-entry');
        if (entries.querySelectorAll('.repeat-entry').length === 1 && first) {
            first.style.setProperty('display', 'none', 'important');
            section.dataset.nsdCollapsed = '1';
        }
    }

    function onAddEntryClick(e) {
        var btn = e.target instanceof Element ? e.target.closest('[id^="add-repeat-entry-btn-"]') : null;
        if (!btn) return;
        var section = document.getElementById('section-container-' + btn.id.replace('add-repeat-entry-btn-', ''));
        if (!section || !section.dataset.nsdCollapsed) return;
        e.preventDefault();
        e.stopImmediatePropagation();
        delete section.dataset.nsdCollapsed;
        var first = section.querySelector('.repeat-entry');
        if (first) {
            first.style.removeProperty('display');
            var field = first.querySelector('textarea,input');
            if (field) field.focus();
        }
    }

    // ---- 3. traffic-light selectors -----------------------------------------
    // Quarterly ratings (3 options) get green / amber / red; the final-report
    // assessments (any option count) get the neutral grey cards MOMO uses there.
    var TRAFFIC_LABELS = ['Overall implementation assessment', "Activities' implementation according to the plan"];
    var NEUTRAL_LABELS = ['Overall implementation assessment', "Activities' implementation"];
    var TRAFFIC_CLASSES = ['green', 'amber', 'red']; // option order: best to worst

    // The core layout step clones form blocks (dropping listeners), so the cards are
    // plain markup and all behaviour is delegated from the document.
    function groupSelect(group) {
        var block = group.closest('.form-item-block');
        return block ? block.querySelector('select[name^="field_value["]') : null;
    }

    function realOptions(select) {
        return Array.prototype.filter.call(select.options, function (o) { return o.value; });
    }

    function syncGroup(group) {
        var select = groupSelect(group);
        if (!select) return;
        var options = realOptions(select);
        group.classList.toggle('is-disabled', select.disabled);
        Array.prototype.forEach.call(group.querySelectorAll('.nsd-tl-card'), function (card, i) {
            var on = !!options[i] && select.value === options[i].value;
            var radio = card.querySelector('input');
            radio.checked = on;
            radio.disabled = select.disabled;
            card.classList.toggle('is-selected', on);
        });
    }

    function syncAllGroups() {
        document.querySelectorAll('.nsd-tl-group').forEach(syncGroup);
    }

    function buildTrafficLight(block, label) {
        var select = block.querySelector('select[name^="field_value["]');
        if (!select || block.querySelector('.nsd-tl-group')) return;
        var options = realOptions(select);
        if (options.length < 2) return;
        var colored = options.length === 3 && TRAFFIC_LABELS.indexOf(label) !== -1;

        var group = document.createElement('div');
        group.className = 'nsd-tl-group';
        group.setAttribute('role', 'radiogroup');
        options.forEach(function (opt, i) {
            var card = document.createElement('label');
            card.className = 'nsd-tl-card nsd-tl-card--' + (colored ? TRAFFIC_CLASSES[i] : 'neutral');
            var radio = document.createElement('input');
            radio.type = 'radio'; // no name: never submitted, the select carries the answer
            var text = document.createElement('span');
            text.textContent = opt.text;
            card.appendChild(radio);
            card.appendChild(text);
            group.appendChild(card);
        });
        select.style.setProperty('display', 'none', 'important');
        select.parentNode.insertBefore(group, select);
        syncGroup(group);
    }

    document.addEventListener('change', function (e) {
        var radio = e.target;
        if (!(radio instanceof HTMLInputElement) || radio.type !== 'radio') return;
        var group = radio.closest('.nsd-tl-group');
        if (!group) return;
        var select = groupSelect(group);
        if (!select || select.disabled) { syncGroup(group); return; }
        var idx = Array.prototype.indexOf.call(group.querySelectorAll('input'), radio);
        var opt = realOptions(select)[idx];
        if (opt) {
            select.value = opt.value;
            select.dispatchEvent(new Event('input', { bubbles: true }));
            select.dispatchEvent(new Event('change', { bubbles: true }));
        }
        syncGroup(group);
    });
    document.addEventListener('change', function (e) {
        if (e.target instanceof HTMLSelectElement) syncAllGroups();
    });
    setInterval(syncAllGroups, 700); // draft restore / programmatic changes

    function setupTrafficLights() {
        document.querySelectorAll('.form-item-block').forEach(function (block) {
            var label = block.querySelector('label');
            var text = label ? label.textContent.replace(/\s+/g, ' ').replace('*', '').trim() : '';
            if (TRAFFIC_LABELS.indexOf(text) !== -1 || NEUTRAL_LABELS.indexOf(text) !== -1) buildTrafficLight(block, text);
        });
    }

    // ---- 4. dd/mm/yyyy for dates in the project information -----------------
    function formatInfoDates() {
        document.querySelectorAll('.form-item-block[data-item-type="blank"] strong').forEach(function (el) {
            var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(el.textContent.trim());
            if (m) el.textContent = m[3] + '/' + m[2] + '/' + m[1];
        });
    }

    // ---- 5. mount our own plugin fields immediately ---------------------------
    // The core mounts plugin fields one after the other, late in the page load. Ours do not
    // need to wait: mount them as soon as their container is in the page.
    var OWN_FIELDS = {
        nsd_logframe: ['/plugins/static/nsd_report_forms/js/nsd-logframe-field.js', 'NsdLogframeField'],
        nsd_list: ['/plugins/static/nsd_report_forms/js/nsd-list-field.js', 'NsdListField']
    };

    function parseJson(raw, fallback) {
        try { return raw ? JSON.parse(raw) : fallback; } catch (e) { return fallback; }
    }

    function mountOwnFields() {
        document.querySelectorAll('.plugin-field-container').forEach(function (container) {
            var spec = OWN_FIELDS[container.dataset.pluginType];
            if (!spec || container.__nsdMounted || container.__nsdMounting) return;
            container.__nsdMounting = true;
            import(spec[0]).then(function (mod) {
                var Ctor = mod[spec[1]] || mod.default;
                var instance = new Ctor(container.dataset.fieldId);
                container.pluginInstance = instance;
                return instance.mount(container, {
                    fieldId: String(container.dataset.fieldId),
                    canEdit: container.dataset.canEdit === 'true',
                    pluginConfig: parseJson(container.dataset.pluginConfig, {}),
                    existingData: parseJson(container.dataset.existingData, {}),
                    container: container
                });
            }).catch(function (e) {
                container.__nsdMounting = false;
                if (window.console) console.error('nsd_report_forms: could not mount field', e);
            });
        });
    }

    // ---- 6. "My projects" link for IFRC project managers -----------------------
    // /nsd-funds/links answers {"pm_overview": url} only for holders of the PM permission. Asked once per page;
    // any failure leaves the page untouched.
    var pmLinkAsked = false;

    function addPmLink() {
        if (pmLinkAsked || !window.fetch) return;
        var group = document.querySelector('.title-text-group');
        if (!group) return;
        pmLinkAsked = true;
        fetch('/nsd-funds/links', { credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
            .then(function (r) { return r.ok ? r.json() : {}; })
            .then(function (links) {
                var url = links && links.pm_overview;
                if (!url || typeof url !== 'string' || url.charAt(0) !== '/' || document.getElementById('nsd-pm-link')) return;
                var a = document.createElement('a');
                a.id = 'nsd-pm-link';
                a.className = 'nsd-pm-link';
                a.href = url;
                a.textContent = 'My projects';
                var icon = document.createElement('i');
                icon.className = 'fas fa-user-tie';
                icon.setAttribute('aria-hidden', 'true');
                a.insertBefore(icon, a.firstChild);
                group.appendChild(a);
            })
            .catch(function () { /* optional link: ignore */ });
    }

    function run() {
        addPmLink();
        mountOwnFields();
        var data = existingData();
        document.querySelectorAll('[data-section-type="repeat"]').forEach(function (s) {
            setupRepeatSection(s, data);
        });
        lockCarriedCells();
        lockInfoFields();
        setupTrafficLights();
        formatInfoDates();
    }

    // window capture runs before the core's own Add Entry handler
    window.addEventListener('click', onAddEntryClick, true);

    var timer = null;
    function schedule() {
        clearTimeout(timer);
        timer = setTimeout(run, 150);
    }
    new MutationObserver(schedule).observe(document.documentElement, { childList: true, subtree: true });
    document.addEventListener('DOMContentLoaded', schedule);
    window.addEventListener('load', schedule);
    schedule();
})();
