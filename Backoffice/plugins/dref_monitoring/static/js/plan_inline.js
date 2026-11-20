(function () {
    'use strict';

    function attrValue(value) {
        var text = String(value || '');
        if (window.CSS && CSS.escape) return CSS.escape(text);
        return text.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
    }

    function initPlanFolds(root) {
        var table = root.querySelector('.dref-plan-table');
        if (!table) return;

        function setToggle(button, expanded) {
            button.setAttribute('aria-expanded', expanded ? 'true' : 'false');
            var label = button.getAttribute(expanded ? 'data-label-open' : 'data-label-closed');
            if (label) {
                button.setAttribute('aria-label', label);
                button.title = label;
            }
        }

        function paint(body) {
            var sectorToggle = body.querySelector('[data-dref-fold="sector"]');
            var sectorOpen = !sectorToggle || sectorToggle.getAttribute('aria-expanded') !== 'false';
            var indicatorOpen = {};
            body.querySelectorAll('[data-dref-fold="indicator"]').forEach(function (button) {
                var host = button.closest('tr');
                var key = host ? host.getAttribute('data-dref-indicator') || '' : '';
                indicatorOpen[key] = button.getAttribute('aria-expanded') !== 'false';
            });
            body.querySelectorAll('tr').forEach(function (row) {
                if (row.querySelector('[data-dref-fold="sector"]')) {
                    row.classList.remove('is-folded');
                    return;
                }
                if (!sectorOpen) {
                    row.classList.add('is-folded');
                    return;
                }
                var key = row.getAttribute('data-dref-indicator');
                if (!key || row.hasAttribute('data-dref-indicator-row')) {
                    row.classList.remove('is-folded');
                    return;
                }
                row.classList.toggle('is-folded', indicatorOpen[key] === false);
            });
        }

        function flip(button) {
            setToggle(button, button.getAttribute('aria-expanded') === 'false');
            var body = button.closest('tbody[data-dref-sector-body]');
            if (body) paint(body);
        }

        function expandRow(row) {
            if (!row) return;
            var body = row.closest('tbody[data-dref-sector-body]');
            if (!body) return;
            var sectorToggle = body.querySelector('[data-dref-fold="sector"]');
            if (sectorToggle) setToggle(sectorToggle, true);
            if (!row.hasAttribute('data-dref-indicator-row')) {
                var key = row.getAttribute('data-dref-indicator') || '';
                if (key) {
                    var indicator = body.querySelector('tr[data-dref-indicator-row][data-dref-indicator="' + attrValue(key) + '"]');
                    var indicatorToggle = indicator && indicator.querySelector('[data-dref-fold="indicator"]');
                    if (indicatorToggle) setToggle(indicatorToggle, true);
                }
            }
            paint(body);
        }

        table.addEventListener('click', function (event) {
            var target = event.target;
            if (!target || !target.closest) return;
            var toggle = target.closest('[data-dref-fold]');
            if (toggle && table.contains(toggle)) {
                event.preventDefault();
                flip(toggle);
                return;
            }
            if (target.closest('a, button, input, select, textarea, label')) return;
            var row = target.closest('tr');
            var cell = target.closest('td');
            if (!row || !cell || cell.cellIndex !== 0 || !row.contains(cell)) return;
            if (row.classList.contains('dref-plan-extra')) return;
            toggle = row.querySelector('[data-dref-fold]');
            if (toggle) flip(toggle);
        });

        root.drefExpandPlanRow = expandRow;
    }

    var root = document.querySelector('[data-dref-plan-edit]');
    if (!root) return;
    initPlanFolds(root);
    var form = root.querySelector('[data-dref-plan-form]');
    var start = root.querySelector('[data-dref-plan-start]');
    if (!form || !start) return;

    var dateMessage = form.getAttribute('data-dref-date-order') || 'The end date must be on or after the start date.';
    var notice = form.querySelector('[data-dref-plan-date-error]');
    var draftKey = 'dref-plan-draft:' + (form.getAttribute('data-dref-operation') || '');
    var activitySeq = 0;

    function rowFields(box) {
        var row = box.closest('[data-dref-add-row]');
        if (!row) return [];
        var next = row.nextElementSibling;
        if (next && next.hasAttribute('data-dref-add-fields')) return next.querySelectorAll('[data-add-field]');
        return row.querySelectorAll('[data-add-field]');
    }

    function setEditing(on) {
        if (!on) {
            clearNewActivities();
            form.reset();
        }
        root.classList.toggle('is-editing', on);
        form.querySelectorAll('.dref-plan-field').forEach(function (field) {
            field.disabled = field.hasAttribute('data-add-field') ? true : !on;
        });
        form.querySelectorAll('[data-dref-add]').forEach(function (box) {
            box.disabled = !on;
            if (!on) box.checked = false;
        });
        if (!on) clearDateErrors();
    }

    function named(name) {
        if (window.CSS && CSS.escape) return form.querySelector('[name="' + CSS.escape(name) + '"]');
        return form.querySelector('[name="' + name + '"]');
    }

    function namedAll(name) {
        if (window.CSS && CSS.escape) return form.querySelectorAll('[name="' + CSS.escape(name) + '"]');
        return form.querySelectorAll('[name="' + name + '"]');
    }

    function endFor(startField) {
        var name = startField.getAttribute('name') || '';
        if (name.indexOf('start_date-') === 0) return named('end_date-' + name.slice('start_date-'.length));
        if (name.indexOf('add_activity_start-') === 0) return named('add_activity_end-' + name.slice('add_activity_start-'.length));
        if (name.indexOf('add_start-') === 0) return named('add_end-' + name.slice('add_start-'.length));
        return null;
    }

    function titleFor(startField) {
        var name = startField.getAttribute('name') || '';
        var titleName = '';
        if (name.indexOf('start_date-') === 0) titleName = 'title-' + name.slice('start_date-'.length);
        else if (name.indexOf('add_activity_start-') === 0) titleName = 'add_activity_title-' + name.slice('add_activity_start-'.length);
        else if (name.indexOf('add_start-') === 0) titleName = 'add_title-' + name.slice('add_start-'.length);
        var title = titleName ? named(titleName) : null;
        return title && title.value ? title.value.trim() : '';
    }

    function clearDateErrors() {
        form.querySelectorAll('.dref-invalid').forEach(function (field) {
            field.classList.remove('dref-invalid');
            if (field.setCustomValidity) field.setCustomValidity('');
        });
        if (notice) {
            notice.hidden = true;
            notice.textContent = '';
        }
    }

    function dateProblems() {
        var problems = [];
        form.querySelectorAll('input[type="date"][name^="start_date-"], input[type="date"][name^="add_start-"], input[type="date"][name^="add_activity_start-"]').forEach(function (startField) {
            var endField = endFor(startField);
            if (!endField || startField.disabled || endField.disabled) return;
            if (!startField.value || !endField.value || endField.value >= startField.value) return;
            problems.push({ field: endField, title: titleFor(startField), message: dateMessage });
        });
        return problems;
    }

    function amountValue(raw) {
        var text = String(raw || '').replace(/,/g, '').trim();
        if (!text) return null;
        var value = Number(text);
        return Number.isFinite(value) ? value : null;
    }

    function amountProblems() {
        var message = form.getAttribute('data-dref-amount') || 'Amounts cannot be negative.';
        var problems = [];
        form.querySelectorAll('input[name^="budget_chf-"], input[name^="target-"], input[name^="activity_target-"], input[name^="add_budget-"], input[name^="add_target-"], input[name^="add_activity_budget-"], input[name^="add_activity_target-"]').forEach(function (field) {
            if (field.disabled) return;
            var value = amountValue(field.value);
            if (value === null || value >= 0) return;
            var row = field.closest('tr');
            var titleField = row && row.querySelector('textarea[name^="title-"], textarea[name^="add_title-"], textarea[name^="add_activity_title-"]');
            problems.push({
                field: field,
                title: titleField && titleField.value ? titleField.value.trim() : '',
                message: message,
            });
        });
        return problems;
    }

    function showProblems(problems) {
        clearDateErrors();
        var lines = [];
        problems.forEach(function (item) {
            item.field.classList.add('dref-invalid');
            if (item.field.setCustomValidity) item.field.setCustomValidity(item.message);
            lines.push(item.title ? item.title + ': ' + item.message : item.message);
        });
        if (notice) {
            notice.hidden = false;
            notice.textContent = lines.join(' ');
        }
        problems.forEach(function (item) {
            if (root.drefExpandPlanRow) root.drefExpandPlanRow(item.field.closest('tr'));
        });
        if (problems[0]) {
            problems[0].field.scrollIntoView({ block: 'center' });
            problems[0].field.focus();
            if (problems[0].field.reportValidity) problems[0].field.reportValidity();
        }
    }

    function snapshot() {
        var rows = [];
        form.querySelectorAll('input[name], textarea[name], select[name]').forEach(function (field) {
            if (!field.name || field.disabled || field.name === 'csrf_token' || field.name === 'tab') return;
            if ((field.type === 'checkbox' || field.type === 'radio') && !field.checked) return;
            rows.push({ name: field.name, value: field.value, check: field.type === 'checkbox' || field.type === 'radio' });
        });
        try {
            sessionStorage.setItem(draftKey, JSON.stringify(rows));
        } catch (err) {
            /* The page can still save. A rejected save will not be able to restore this draft. */
        }
    }

    function restore() {
        var raw = null;
        try {
            raw = sessionStorage.getItem(draftKey);
        } catch (err) {
            return;
        }
        if (!raw) return;
        var rows = [];
        try {
            rows = JSON.parse(raw);
        } catch (err) {
            return;
        }
        setEditing(true);
        restoreNewActivities(rows);
        rows.forEach(function (item) {
            if (!item.check) return;
            namedAll(item.name).forEach(function (field) {
                if (field.value === item.value) {
                    field.checked = true;
                    field.dispatchEvent(new Event('change', { bubbles: true }));
                }
            });
        });
        var seen = {};
        rows.forEach(function (item) {
            if (item.check) return;
            var index = seen[item.name] || 0;
            seen[item.name] = index + 1;
            var field = namedAll(item.name)[index];
            if (field && !field.disabled) field.value = item.value;
        });
    }

    function rememberKey(key) {
        var match = /^n(\d+)$/.exec(key || '');
        if (match) activitySeq = Math.max(activitySeq, parseInt(match[1], 10));
    }

    function nextKey() {
        activitySeq += 1;
        return 'n' + activitySeq;
    }

    function activityRows(indicatorKey) {
        return form.querySelectorAll('tr[data-dref-activity][data-dref-indicator="' + attrValue(indicatorKey) + '"]');
    }

    function emptyRow(indicatorKey) {
        return form.querySelector('tr[data-dref-indicator-empty][data-dref-indicator="' + attrValue(indicatorKey) + '"]');
    }

    function showEmpty(indicatorKey) {
        var empty = emptyRow(indicatorKey);
        var rows = activityRows(indicatorKey);
        if (empty) empty.hidden = rows.length > 0;
    }

    function activityHost(row, key) {
        return row.querySelector('textarea[name="add_activity_title-' + key + '"]');
    }

    function insertActivity(button, key, focus) {
        var template = form.querySelector('[data-dref-activity-template]');
        if (!template || !button) return null;
        var groupId = button.getAttribute('data-group-id') || '';
        var indicatorId = button.getAttribute('data-indicator-id') || '';
        var indicatorKey = button.getAttribute('data-indicator-key') || indicatorId;
        key = key || nextKey();
        rememberKey(key);
        var source = template.content && template.content.querySelector('tr');
        if (!source) return null;
        var html = source.outerHTML
            .replace(/__KEY__/g, key)
            .replace(/__INDICATOR_KEY__/g, indicatorKey)
            .replace(/__INDICATOR__/g, indicatorId)
            .replace(/__GROUP__/g, groupId)
            .replace(/__START__/g, button.getAttribute('data-start') || '')
            .replace(/__END__/g, button.getAttribute('data-end') || '');
        var holder = document.createElement('tbody');
        holder.innerHTML = html.trim();
        var row = holder.querySelector('tr');
        if (!row) return null;
        var rows = activityRows(indicatorKey);
        var anchor = rows.length ? rows[rows.length - 1] : button.closest('tr');
        if (!anchor || !anchor.parentNode) return null;
        anchor.parentNode.insertBefore(row, anchor.nextSibling);
        showEmpty(indicatorKey);
        if (root.drefExpandPlanRow) root.drefExpandPlanRow(row);
        var title = activityHost(row, key);
        if (focus && title) title.focus();
        return row;
    }

    function discardActivity(row) {
        if (!row) return;
        var indicatorKey = row.getAttribute('data-dref-indicator') || '';
        row.remove();
        showEmpty(indicatorKey);
    }

    function clearNewActivities() {
        form.querySelectorAll('tr[data-dref-new-activity]').forEach(function (row) {
            row.remove();
        });
        form.querySelectorAll('tr[data-dref-indicator-empty]').forEach(function (row) {
            showEmpty(row.getAttribute('data-dref-indicator') || '');
        });
    }

    function newActivityUnused(row) {
        var title = row.querySelector('textarea[name^="add_activity_title-"]');
        var budget = row.querySelector('input[name^="add_activity_budget-"]');
        var target = row.querySelector('input[name^="add_activity_target-"]');
        var status = row.querySelector('select[name^="add_activity_status-"]');
        var kind = row.querySelector('select[name^="add_activity_type-"]');
        var who = row.querySelector('select[name^="add_activity_by-"]');
        var start = row.querySelector('input[name^="add_activity_start-"]');
        var end = row.querySelector('input[name^="add_activity_end-"]');
        var indicatorKey = row.getAttribute('data-dref-indicator') || '';
        var button = indicatorKey ? form.querySelector('[data-dref-add-activity][data-indicator-key="' + attrValue(indicatorKey) + '"]') : null;
        if (title && title.value.trim()) return false;
        if (budget && budget.value.trim()) return false;
        if (target && target.value.trim()) return false;
        if (status && status.value && status.value !== 'planned') return false;
        if (kind && kind.value) return false;
        if (who && who.value) return false;
        if (start && button && start.value !== (button.getAttribute('data-start') || '')) return false;
        if (end && button && end.value !== (button.getAttribute('data-end') || '')) return false;
        return true;
    }

    function dropUnusedNewActivities() {
        Array.prototype.slice.call(form.querySelectorAll('tr[data-dref-new-activity]')).forEach(function (row) {
            if (row.isConnected && newActivityUnused(row)) discardActivity(row);
        });
    }

    function postedValue(items, name) {
        var found = '';
        items.forEach(function (item) {
            if (!item.check && item.name === name) found = item.value || '';
        });
        return found;
    }

    function restoreNewActivities(items) {
        items.forEach(function (item) {
            if (item.check || item.name !== 'add_activity') return;
            var key = item.value || '';
            if (!key) return;
            var group = postedValue(items, 'add_activity_group-' + key);
            var indicator = postedValue(items, 'add_activity_indicator-' + key);
            var button = indicator
                ? form.querySelector('[data-dref-add-activity][data-indicator-id="' + attrValue(indicator) + '"]')
                : null;
            if (!button && group) {
                button = form.querySelector('[data-dref-add-activity][data-indicator-key="' + attrValue('other-' + group) + '"]');
            }
            if (button) insertActivity(button, key, false);
        });
    }

    start.addEventListener('click', function () {
        setEditing(true);
        var reason = form.querySelector('[name="justification"]');
        if (reason) reason.focus();
    });

    var cancel = form.querySelector('[data-dref-plan-cancel]');
    if (cancel) {
        cancel.addEventListener('click', function () {
            setEditing(false);
            try {
                sessionStorage.removeItem(draftKey);
            } catch (err) {
                /* Leaving edit mode still discards the fields on the page. */
            }
        });
    }

    form.querySelectorAll('[data-dref-add]').forEach(function (box) {
        box.addEventListener('change', function () {
            rowFields(box).forEach(function (field) {
                field.disabled = !box.checked;
            });
        });
    });

    form.addEventListener('click', function (event) {
        var target = event.target;
        if (!target || !target.closest) return;
        var add = target.closest('[data-dref-add-activity]');
        if (add) {
            event.preventDefault();
            insertActivity(add, '', true);
            return;
        }
        var discard = target.closest('[data-dref-discard-activity]');
        if (discard) discardActivity(discard.closest('tr'));
    });

    form.addEventListener('input', function (event) {
        var target = event.target;
        if (!target) return;
        var watched = target.type === 'date' || /^(budget_chf-|target-|activity_target-|add_budget-|add_target-|add_activity_budget-|add_activity_target-)/.test(target.name || '');
        if (!watched) return;
        if (!dateProblems().length && !amountProblems().length) clearDateErrors();
    });

    form.addEventListener('submit', function (event) {
        dropUnusedNewActivities();
        var problems = dateProblems().concat(amountProblems());
        if (problems.length) {
            event.preventDefault();
            showProblems(problems);
            return;
        }
        clearDateErrors();
        snapshot();
    });

    if (form.getAttribute('data-dref-plan-draft') === '1') {
        restore();
        try {
            var url = new URL(window.location.href);
            url.searchParams.delete('plan_draft');
            window.history.replaceState(null, '', url.pathname + url.search + url.hash);
        } catch (err) {
            /* The restored fields stay either way. */
        }
    } else {
        try {
            sessionStorage.removeItem(draftKey);
        } catch (err) {
            /* Nothing stored to clear. */
        }
    }
})();
