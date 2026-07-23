/**
 * Collapsible analytics filter cards (macros/filter_card.html).
 * Collapsed by default; auto-expands when the form has active filter values.
 */
(function() {
    'use strict';

    if (window.__analyticsFilterCardInit) {
        return;
    }
    window.__analyticsFilterCardInit = true;

    function getCardBody(card) {
        if (!card) return null;
        return card.querySelector('.analytics-filter-card-body');
    }

    function getToggleButton(card) {
        if (!card) return null;
        return card.querySelector('.analytics-filter-card-toggle');
    }

    function setFilterCardCollapsed(card, collapsed) {
        var body = getCardBody(card);
        var toggle = getToggleButton(card);
        if (!body || !toggle) return;

        body.classList.toggle('hidden', collapsed);
        toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');

        var label = toggle.querySelector('.analytics-filter-card-toggle-label');
        var icon = toggle.querySelector('.analytics-filter-card-toggle-icon');
        var showLabel = toggle.getAttribute('data-show-label') || 'Show filters';
        var hideLabel = toggle.getAttribute('data-hide-label') || 'Hide filters';

        if (label) {
            label.textContent = collapsed ? showLabel : hideLabel;
        }
        if (icon) {
            icon.classList.toggle('rotate-180', !collapsed);
        }
    }

    function formHasActiveFilters(form) {
        if (!form) return false;

        var fields = form.querySelectorAll('input, select, textarea');
        for (var i = 0; i < fields.length; i++) {
            var el = fields[i];
            if (!el.name || el.disabled) continue;
            if (el.type === 'submit' || el.type === 'button' || el.type === 'reset') continue;

            if (el.type === 'checkbox' || el.type === 'radio') {
                if (el.checked) return true;
                continue;
            }

            if (el.tagName === 'SELECT') {
                if (el.value && String(el.value).trim() !== '') return true;
                continue;
            }

            if (el.value && String(el.value).trim() !== '') return true;
        }

        return false;
    }

    function initFilterCards() {
        document.querySelectorAll('.analytics-filter-card').forEach(function(card) {
            if (card.getAttribute('data-filter-card-ready') === 'true') return;
            card.setAttribute('data-filter-card-ready', 'true');

            var forceExpanded = card.getAttribute('data-filter-card-expanded') === 'true';
            var form = card.querySelector('form');
            var collapsed = forceExpanded ? false : !formHasActiveFilters(form);
            setFilterCardCollapsed(card, collapsed);
        });
    }

    document.addEventListener('click', function(ev) {
        var toggle = ev.target && ev.target.closest
            ? ev.target.closest('.analytics-filter-card-toggle')
            : null;
        if (!toggle) return;

        var card = toggle.closest('.analytics-filter-card');
        var body = getCardBody(card);
        if (!body) return;

        setFilterCardCollapsed(card, !body.classList.contains('hidden'));
    });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initFilterCards);
    } else {
        initFilterCards();
    }
})();
