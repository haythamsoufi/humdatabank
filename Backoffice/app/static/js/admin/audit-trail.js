(function() {
  'use strict';
  var cfg = window.auditTrailConfig || {};
  /* block 1 */
const EMPTY_VALUE_PLACEHOLDER = '-';

    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function isNilOrEmpty(value) {
        return value === null || value === undefined || String(value).trim() === '';
    }

    function humanizeToken(value) {
        if (isNilOrEmpty(value)) return EMPTY_VALUE_PLACEHOLDER;
        return String(value)
            .replace(/[_\-]+/g, ' ')
            .replace(/\s+/g, ' ')
            .trim()
            .replace(/\b\w/g, c => c.toUpperCase());
    }

    function renderTextCell(value, options = {}) {
        const {
            mono = false,
            mutedWhenEmpty = true,
            extraClasses = ''
        } = options;
        if (isNilOrEmpty(value)) {
            const emptyClass = mutedWhenEmpty ? 'text-gray-500' : 'text-gray-900';
            return '<span class="text-sm ' + emptyClass + '">' + EMPTY_VALUE_PLACEHOLDER + '</span>';
        }
        const classes = ['text-sm', 'text-gray-900'];
        if (mono) classes.push('font-mono');
        if (extraClasses) classes.push(extraClasses);
        return '<span class="' + classes.join(' ') + '">' + escapeHtml(String(value)) + '</span>';
    }

    function renderUserUpdateDetailsHtml(d) {
        function ulList(items, liClass) {
            if (!items || !items.length) {
                return '<p class="text-xs text-gray-500 italic">' + cfg.t.none_6adf97f8 + '</p>';
            }
            var cls = liClass ? (' ' + liClass) : '';
            return '<ul class="list-disc list-inside text-gray-800 space-y-0.5 text-xs">' +
                items.map(function(x) { return '<li class="' + cls + '">' + escapeHtml(String(x)) + '</li>'; }).join('') +
                '</ul>';
        }
        function section(title, inner) {
            return '<div class="audit-detail-section"><div class="audit-detail-h">' + escapeHtml(title) + '</div>' + inner + '</div>';
        }
        function subBlock(label, content) {
            return '<div class="mb-2 last:mb-0"><div class="audit-detail-sub">' + escapeHtml(label) + '</div>' + content + '</div>';
        }
        function profileBlock(obj) {
            if (!obj) return '';
            var rows = [
                [cfg.t.email_ce8ae9da, obj.email || ''],
                [cfg.t.name_49ee3087, obj.name || ''],
                [cfg.t.title_b78a3223, obj.title || '']
            ];
            /* Stack label above value so values use full column width (avoids nested grid squeezing dd to ~0) */
            var h = '<dl class="text-xs space-y-2 text-gray-800">';
            rows.forEach(function(r) {
                h += '<div class="min-w-0">';
                h += '<dt class="text-gray-500">' + escapeHtml(r[0]) + '</dt>';
                h += '<dd class="m-0 mt-0.5 text-gray-900 min-w-0 break-words hyphens-none">' + escapeHtml(r[1]) + '</dd>';
                h += '</div>';
            });
            h += '</dl>';
            return h;
        }
        var parts = [];
        var pb = d['Profile (before)'];
        var pa = d['Profile (after)'];
        if (pb && pa) {
            var inner = '<div class="audit-detail-compare">' +
                '<div class="min-w-0"><div class="audit-detail-sub mb-1">' + cfg.t.before_9060587e + '</div>' + profileBlock(pb) + '</div>' +
                '<div class="min-w-0"><div class="audit-detail-sub mb-1">' + cfg.t.after_7bfcadb5 + '</div>' + profileBlock(pa) + '</div></div>';
            parts.push(section(cfg.t.profile_cce99c59, inner));
        }
        var cAdd = d['Countries added'];
        var cRem = d['Countries removed'];
        var cBefore = d['Countries (before)'];
        var cAfter = d['Countries (after)'];
        var cDiff = cBefore && cAfter && JSON.stringify(cBefore) !== JSON.stringify(cAfter);
        var hasCAdd = cAdd && cAdd.length;
        var hasCRem = cRem && cRem.length;
        if (hasCAdd || hasCRem) {
            var cInner = '';
            if (hasCAdd) cInner += subBlock(cfg.t.added_f29ddbfb, ulList(cAdd, 'text-green-800'));
            if (hasCRem) cInner += subBlock(cfg.t.removed_93f07b72, ulList(cRem, 'text-amber-800'));
            if (cAfter && cAfter.length) cInner += subBlock(cfg.t.current_222a267c, ulList(cAfter));
            parts.push(section(cfg.t.countries_790d59ef, cInner));
        } else if (cDiff) {
            parts.push(section(cfg.t.countries_790d59ef,
                '<div class="audit-detail-compare">' +
                '<div class="min-w-0"><div class="audit-detail-sub mb-1">' + cfg.t.before_9060587e + '</div>' + ulList(cBefore) + '</div>' +
                '<div class="min-w-0"><div class="audit-detail-sub mb-1">' + cfg.t.after_7bfcadb5 + '</div>' + ulList(cAfter) + '</div></div>'));
        }

        var rAdd = d['Roles added'];
        var rRem = d['Roles removed'];
        var rBefore = d['Roles (before)'];
        var rAfter = d['Roles (after)'];
        var rDiff = rBefore && rAfter && JSON.stringify(rBefore) !== JSON.stringify(rAfter);
        var hasRAdd = rAdd && rAdd.length;
        var hasRRem = rRem && rRem.length;
        if (hasRAdd || hasRRem) {
            var rInner = '';
            if (hasRAdd) rInner += subBlock(cfg.t.added_f29ddbfb, ulList(rAdd, 'text-green-800'));
            if (hasRRem) rInner += subBlock(cfg.t.removed_93f07b72, ulList(rRem, 'text-amber-800'));
            if (rAfter && rAfter.length) rInner += subBlock(cfg.t.current_222a267c, ulList(rAfter));
            parts.push(section(cfg.t.roles_a5cd3ed1, rInner));
        } else if (rDiff) {
            parts.push(section(cfg.t.roles_a5cd3ed1,
                '<div class="audit-detail-compare">' +
                '<div class="min-w-0"><div class="audit-detail-sub mb-1">' + cfg.t.before_9060587e + '</div>' + ulList(rBefore) + '</div>' +
                '<div class="min-w-0"><div class="audit-detail-sub mb-1">' + cfg.t.after_7bfcadb5 + '</div>' + ulList(rAfter) + '</div></div>'));
        } else if (rAfter && rAfter.length) {
            parts.push(section(cfg.t.roles_a5cd3ed1, ulList(rAfter)));
        }

        var perms = d['Permissions via assigned roles (after change)'];
        var permNote = d['Permissions (truncated note)'];
        if (perms && perms.length) {
            var pInner = '<div class="max-h-48 overflow-y-auto border border-gray-200 bg-white p-2">' + ulList(perms) + '</div>';
            if (permNote) pInner += '<p class="text-xs text-gray-500 mt-1">' + escapeHtml(permNote) + '</p>';
            parts.push(section(cfg.t.permissions_from_assigned_roles_343ea82a, pInner));
        }

        if (d['Password']) {
            parts.push(section(cfg.t.password_dc647eb6, '<p class="text-xs text-amber-800 font-medium">' + cfg.t.password_was_changed_7717ad0a + '</p>'));
        }

        var ent = d['Non-country entity access (after)'];
        if (ent && ent.length) {
            parts.push(section(cfg.t.other_entity_access_ba9f54e8, ulList(ent)));
        }

        if (!parts.length) {
            return '<pre class="text-xs text-gray-700 details-pre">' + escapeHtml(JSON.stringify(d, null, 2)) + '</pre>';
        }
        return '<div class="audit-details-user-update">' + parts.join('') + '</div>';
    }

    function renderFormItemUpdateDetailsHtml(d) {
        var MAX_DEPTH = 8;
        var MAX_STR_PRE = 8000;

        function humanizeKey(key) {
            if (key === null || key === undefined) return '';
            return String(key)
                .replace(/_/g, ' ')
                .replace(/\s+/g, ' ')
                .trim()
                .replace(/\b\w/g, function (c) { return c.toUpperCase(); });
        }

        function tryParseJsonString(s) {
            if (typeof s !== 'string') return null;
            var t = s.trim();
            if (!t.length) return null;
            var c0 = t.charAt(0);
            if (c0 !== '{' && c0 !== '[') return null;
            try {
                return JSON.parse(t);
            } catch (e) {
                return null;
            }
        }

        function isLogicConditionsShape(o) {
            return o && typeof o === 'object' && !Array.isArray(o) && Array.isArray(o.conditions);
        }

        function isTokenLikeString(s) {
            return typeof s === 'string' && s.length > 0 && s.length < 256 && !/\s/.test(s);
        }

        function renderLogicConditionsBlock(o, depth) {
            var parts = [];
            if (o.logic !== undefined && o.logic !== null && String(o.logic).length) {
                parts.push(
                    '<p class="audit-form-item-cond-line audit-form-item-cond-line-top"><span class="audit-form-item-kv-label">' + cfg.t.logic_35ba1271 + ':</span> ' +
                    '<code class="audit-form-item-code">' + escapeHtml(String(o.logic)) + '</code></p>'
                );
            }
            var conds = o.conditions;
            if (Array.isArray(conds) && conds.length) {
                conds.forEach(function (c, i) {
                    var inner;
                    if (c && typeof c === 'object' && !Array.isArray(c)) {
                        var keys = Object.keys(c).sort();
                        inner = keys.map(function (ck) {
                            return '<p class="audit-form-item-cond-line"><span class="audit-form-item-kv-label">' +
                                escapeHtml(humanizeKey(ck)) + ':</span> ' + renderValuePretty(c[ck], depth + 1) + '</p>';
                        }).join('');
                    } else {
                        inner = '<p class="audit-form-item-cond-line">' + renderValuePretty(c, depth + 1) + '</p>';
                    }
                    parts.push(
                        '<div class="audit-form-item-cond-box"><p class="audit-form-item-cond-title">' + cfg.t.condition_9e2941b3 + ' ' + (i + 1) + '</p>' + inner + '</div>'
                    );
                });
            }
            return '<div class="audit-form-item-condition-simple">' + parts.join('') + '</div>';
        }

        function renderValuePretty(v, depth) {
            depth = depth || 0;
            if (v === null || v === undefined) {
                return '<span class="text-sm text-gray-500">' + EMPTY_VALUE_PLACEHOLDER + '</span>';
            }
            if (depth > MAX_DEPTH) {
                try {
                    return '<pre class="text-xs text-gray-800 details-pre whitespace-pre-wrap break-words max-h-40 overflow-y-auto">' +
                        escapeHtml(JSON.stringify(v, null, 2)) + '</pre>';
                } catch (e) {
                    return '<span class="text-sm text-gray-900">' + escapeHtml(String(v)) + '</span>';
                }
            }
            if (typeof v === 'boolean') {
                return '<span class="text-sm font-semibold ' + (v ? 'text-emerald-700' : 'text-gray-600') + '">' +
                    (v ? cfg.t.yes_93cba074 : cfg.t.no_bafd7322) + '</span>';
            }
            if (typeof v === 'number' && isFinite(v)) {
                return '<span class="text-sm font-mono text-gray-900">' + escapeHtml(String(v)) + '</span>';
            }
            if (typeof v === 'string') {
                var parsed = tryParseJsonString(v);
                if (parsed !== null && typeof parsed === 'object') {
                    return renderValuePretty(parsed, depth);
                }
                if (v.length > MAX_STR_PRE || v.indexOf('\n') >= 0) {
                    return '<pre class="text-xs text-gray-800 details-pre whitespace-pre-wrap break-words max-h-56 overflow-y-auto">' +
                        escapeHtml(v) + '</pre>';
                }
                if (isTokenLikeString(v)) {
                    return '<code class="audit-form-item-code">' + escapeHtml(v) + '</code>';
                }
                return '<span class="text-sm text-gray-900 break-words">' + escapeHtml(v) + '</span>';
            }
            if (Array.isArray(v)) {
                if (!v.length) {
                    return '<span class="text-xs text-gray-500 italic">' + cfg.t.empty_list_07e1a7a2 + '</span>';
                }
                var hasObjects = v.some(function (x) {
                    return x !== null && typeof x === 'object' && !Array.isArray(x);
                });
                if (hasObjects) {
                    return '<div class="audit-form-item-array-simple">' +
                        v.map(function (item, idx) {
                            return '<div class="audit-form-item-array-simple-row">' +
                                '<span class="audit-form-item-array-simple-n">' + (idx + 1) + '.</span>' +
                                '<div class="audit-form-item-array-simple-body">' + renderValuePretty(item, depth + 1) + '</div>' +
                                '</div>';
                        }).join('') + '</div>';
                }
                var allSimple = v.every(function (x) {
                    return x === null || typeof x === 'boolean' || typeof x === 'number' ||
                        (typeof x === 'string' && x.length < 120);
                });
                if (allSimple && JSON.stringify(v).length < 400) {
                    return '<ul class="list-disc pl-4 text-xs text-gray-900 space-y-0.5">' +
                        v.map(function (item) {
                            return '<li class="pl-0.5">' + renderValuePretty(item, depth + 1) + '</li>';
                        }).join('') + '</ul>';
                }
                return '<ul class="list-disc pl-4 text-xs text-gray-900 space-y-1">' +
                    v.map(function (item) {
                        return '<li class="pl-0.5">' + renderValuePretty(item, depth + 1) + '</li>';
                    }).join('') + '</ul>';
            }
            if (typeof v === 'object') {
                if (isLogicConditionsShape(v)) {
                    return renderLogicConditionsBlock(v, depth);
                }
                var keys = Object.keys(v);
                if (!keys.length) {
                    return '<span class="text-xs text-gray-500 italic">' + cfg.t.empty_ce2c8aed + '</span>';
                }
                keys.sort();
                var rows = keys.map(function (key) {
                    var raw = v[key];
                    return '<p class="audit-form-item-kv-line"><span class="audit-form-item-kv-label">' +
                        escapeHtml(humanizeKey(key)) + ':</span> ' + renderValuePretty(raw, depth + 1) + '</p>';
                }).join('');
                var nestClass = depth > 0 ? ' audit-form-item-nested' : '';
                return '<div class="audit-form-item-kv-stack' + nestClass + '">' + rows + '</div>';
            }
            return '<span class="text-sm text-gray-900 break-words">' + escapeHtml(String(v)) + '</span>';
        }

        function valBlock(v) {
            if (v === null || v === undefined) {
                return '<span class="text-sm text-gray-500">' + EMPTY_VALUE_PLACEHOLDER + '</span>';
            }
            if (typeof v === 'object') {
                return '<div class="audit-form-item-value-box">' + renderValuePretty(v, 0) + '</div>';
            }
            var inner = renderValuePretty(v, 0);
            if (typeof v === 'string') {
                var p = tryParseJsonString(v);
                if (p !== null && typeof p === 'object') {
                    return '<div class="audit-form-item-value-box">' + inner + '</div>';
                }
            }
            return inner;
        }

        function isFormItemAuditValueEmpty(v) {
            if (v === null || v === undefined) return true;
            if (typeof v === 'string') {
                if (!v.trim()) return true;
                var parsed = tryParseJsonString(v);
                if (parsed !== null && typeof parsed === 'object') {
                    if (Array.isArray(parsed)) return parsed.length === 0;
                    return Object.keys(parsed).length === 0;
                }
                return false;
            }
            if (Array.isArray(v)) return v.length === 0;
            if (typeof v === 'object') return Object.keys(v).length === 0;
            return false;
        }

        function pairSection(title, beforeVal, afterVal) {
            var emptyBefore = isFormItemAuditValueEmpty(beforeVal);
            var emptyAfter = isFormItemAuditValueEmpty(afterVal);
            if (emptyBefore && emptyAfter) {
                return '';
            }
            var head = '<div class="audit-detail-section"><div class="audit-detail-h">' + escapeHtml(title) + '</div>';
            if (emptyBefore && !emptyAfter) {
                return head + '<div><div class="audit-detail-sub mb-1 text-emerald-800">' + cfg.t.added_f29ddbfb + '</div>' +
                    valBlock(afterVal) + '</div></div>';
            }
            if (!emptyBefore && emptyAfter) {
                return head + '<div><div class="audit-detail-sub mb-1 text-amber-800">' + cfg.t.removed_93f07b72 + '</div>' +
                    valBlock(beforeVal) + '</div></div>';
            }
            return head + '<div class="space-y-3">' +
                '<div><div class="audit-detail-sub mb-1">' + cfg.t.before_9060587e + '</div>' + valBlock(beforeVal) + '</div>' +
                '<div><div class="audit-detail-sub mb-1">' + cfg.t.after_7bfcadb5 + '</div>' + valBlock(afterVal) + '</div>' +
                '</div></div>';
        }
        var parts = [];
        if (d.Note) {
            parts.push('<p class="text-xs text-gray-600 mb-2">' + escapeHtml(String(d.Note)) + '</p>');
        }
        for (var k in d) {
            if (!Object.prototype.hasOwnProperty.call(d, k)) continue;
            if (k === 'Note') continue;
            if (k.endsWith(' (before)')) {
                var base = k.slice(0, -9);
                var ak = base + ' (after)';
                if (Object.prototype.hasOwnProperty.call(d, ak)) {
                    var block = pairSection(base, d[k], d[ak]);
                    if (block) parts.push(block);
                }
            }
        }
        if (!parts.length) {
            return '<pre class="text-xs text-gray-700 details-pre">' + escapeHtml(JSON.stringify(d, null, 2)) + '</pre>';
        }
        return '<div class="audit-details-user-update audit-details-form-item">' + parts.join('') + '</div>';
    }

    /** Flat key–value admin details (RBAC, API keys, etc.) */
    function renderSimpleStructuredAuditHtml(d) {
        var keys = Object.keys(d).filter(function (k) {
            return Object.prototype.hasOwnProperty.call(d, k) && d[k] !== undefined && d[k] !== null && d[k] !== '';
        });
        keys.sort();
        if (!keys.length) {
            try {
                return '<pre class="text-xs text-gray-700 details-pre">' + escapeHtml(JSON.stringify(d, null, 2)) + '</pre>';
            } catch (e) {
                return renderTextCell(String(d));
            }
        }
        var rows = keys.map(function (k) {
            var v = d[k];
            var vs = typeof v === 'object' ? JSON.stringify(v) : String(v);
            return '<p class="text-xs text-gray-900 audit-form-item-kv-line"><span class="audit-form-item-kv-label">' +
                escapeHtml(k) + ':</span> <span class="break-words">' + escapeHtml(vs) + '</span></p>';
        }).join('');
        return '<div class="audit-details-user-update">' + rows + '</div>';
    }

    function renderDetailsValue(details, entry) {
        if (details === null || details === undefined) {
            return '<span class="text-sm text-gray-500">' + EMPTY_VALUE_PLACEHOLDER + '</span>';
        }
        if (typeof details === 'object' && details !== null && !Array.isArray(details)) {
            if (entry && entry.type === 'admin_action' && entry.action_type === 'user_update') {
                return renderUserUpdateDetailsHtml(details);
            }
            if (entry && entry.type === 'admin_action' && entry.action_type === 'form_item_update') {
                return renderFormItemUpdateDetailsHtml(details);
            }
            var at = entry && entry.action_type ? String(entry.action_type) : '';
            if (at.indexOf('rbac_') === 0 || at === 'api_key_create' || at === 'api_key_revoke') {
                return renderSimpleStructuredAuditHtml(details);
            }
            try {
                return '<pre class="text-xs text-gray-700 details-pre">' + escapeHtml(JSON.stringify(details, null, 2)) + '</pre>';
            } catch (e) {
                return renderTextCell(String(details));
            }
        }
        if (typeof details === 'boolean') {
            return renderTextCell(details ? 'true' : 'false');
        }
        return renderTextCell(String(details));
    }

    // Function to toggle details display
    function toggleDetails(elementId) {
        const element = document.getElementById(elementId);
        if (element.classList.contains('hidden')) {
            element.classList.remove('hidden');
        } else {
            element.classList.add('hidden');
        }
    }


    // Initialize multiselect dropdowns when DOM is loaded
    let userMultiselect, activityTypeMultiselect, riskLevelMultiselect, countryMultiselect, requiresReviewMultiselect, sessionLogMultiselect;

    document.addEventListener('DOMContentLoaded', function() {
        // Wait for the MultiselectDropdown class to be available
        if (typeof MultiselectDropdown !== 'undefined') {
            initializeMultiselectDropdowns();
        } else {
            // Retry after a short delay if the class isn't loaded yet
            setTimeout(function() {
                if (typeof MultiselectDropdown !== 'undefined') {
                    initializeMultiselectDropdowns();
                } else {
                    console.error('MultiselectDropdown class not found. Please ensure the script is loaded.');
                }
            }, 100);
        }
    });

    function initializeMultiselectDropdowns() {
        var ms = (cfg.pageData && cfg.pageData.multiselect) || {};

        userMultiselect = new MultiselectDropdown({
            containerId: 'user-multiselect-container',
            name: 'user',
            placeholder: cfg.t.select_users_a739a144,
            searchPlaceholder: cfg.t.search_users_f5e8b59c,
            data: ms.users || [],
            selectedValues: ms.selectedUsers || []
        });

        countryMultiselect = new MultiselectDropdown({
            containerId: 'country-multiselect-container',
            name: 'country',
            placeholder: cfg.t.select_countries_751771bc,
            searchPlaceholder: cfg.t.search_countries_275f127b,
            data: ms.countries || [],
            selectedValues: ms.selectedCountries || []
        });

        activityTypeMultiselect = new MultiselectDropdown({
            containerId: 'activity-type-multiselect-container',
            name: 'activity_type',
            placeholder: cfg.t.select_activity_types_3b7e53b5,
            searchPlaceholder: cfg.t.search_activity_types_25243ce7,
            data: ms.activityTypes || [],
            selectedValues: ms.selectedActivityTypes || [],
            searchable: false
        });

        var riskLevelData = [
            { value: 'low', label: cfg.t.low_28d0edd0 },
            { value: 'medium', label: cfg.t.medium_87f8a6ab },
            { value: 'high', label: cfg.t.high_655d20c1 },
            { value: 'critical', label: cfg.t.critical_278d01e5 }
        ];

        riskLevelMultiselect = new MultiselectDropdown({
            containerId: 'risk-level-multiselect-container',
            name: 'risk_level',
            placeholder: cfg.t.select_risk_levels_0acb0465,
            searchPlaceholder: cfg.t.search_risk_levels_c0054b56,
            data: riskLevelData,
            selectedValues: ms.selectedRiskLevels || [],
            searchable: false
        });

        requiresReviewMultiselect = new MultiselectDropdown({
            containerId: 'requires-review-multiselect-container',
            name: 'requires_review',
            placeholder: cfg.t.any_ed36a1ef,
            searchPlaceholder: '',
            data: [{ value: '1', label: cfg.t.needs_review_only_1c40e9d0 }],
            selectedValues: ms.requiresReviewSelected || [],
            searchable: false,
            showSelectAll: false
        });

        sessionLogMultiselect = new MultiselectDropdown({
            containerId: 'session-log-id-multiselect-container',
            name: 'session_id',
            placeholder: cfg.t.select_session_25b22add,
            searchPlaceholder: cfg.t.filter_by_id_user_or_date_a85cee7b,
            data: ms.sessionLogs || [],
            selectedValues: ms.selectedSessionLogIds || [],
            searchable: true,
            showSelectAll: false,
            singleSelect: true
        });
    }

  /* block 2 */
$(document).ready(function() {
    var filtersPane = document.getElementById('auditTrailFiltersPane');
    var toggleBtn = document.getElementById('auditTrailFiltersToggle');
    var toggleLabel = document.getElementById('auditTrailFiltersToggleLabel');
    var toggleIcon = document.getElementById('auditTrailFiltersToggleIcon');

    function setAuditFiltersCollapsed(collapsed) {
        if (!filtersPane || !toggleBtn) return;
        filtersPane.classList.toggle('hidden', collapsed);
        toggleBtn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
        if (toggleLabel) {
            toggleLabel.textContent = collapsed
                ? cfg.t.show_filters_d95c6bb0
                : cfg.t.hide_filters_32a92e51;
        }
        if (toggleIcon) {
            toggleIcon.classList.toggle('rotate-180', !collapsed);
        }
    }

    if (toggleBtn && filtersPane) {
        toggleBtn.addEventListener('click', function() {
            var nextCollapsed = !filtersPane.classList.contains('hidden');
            setAuditFiltersCollapsed(nextCollapsed);
        });
    }

    // Handle form submission
    $('#auditTrailFiltersForm').on('submit', function(e) {
        e.preventDefault();
        const formData = new FormData(this);

        // Get selected values from multiselect components
        const activityTypes = activityTypeMultiselect ? activityTypeMultiselect.getSelectedValues() : [];
        const users = userMultiselect ? userMultiselect.getSelectedValues() : [];
        const riskLevels = riskLevelMultiselect ? riskLevelMultiselect.getSelectedValues() : [];
        const countries = countryMultiselect ? countryMultiselect.getSelectedValues() : [];

        // Remove any existing values from formData
        formData.delete('activity_type');
        formData.delete('user');
        formData.delete('risk_level');
        formData.delete('country');
        formData.delete('session_id');
        formData.delete('requires_review');

        // Add multiselect values
        activityTypes.forEach(function(type) {
            formData.append('activity_type', type);
        });

        users.forEach(function(user) {
            formData.append('user', user);
        });

        riskLevels.forEach(function(level) {
            formData.append('risk_level', level);
        });

        countries.forEach(function(country) {
            formData.append('country', country);
        });

        const sessionLogIds = sessionLogMultiselect ? sessionLogMultiselect.getSelectedValues() : [];
        sessionLogIds.forEach(function(v) {
            formData.append('session_id', v);
        });

        const requiresReviewVals = requiresReviewMultiselect ? requiresReviewMultiselect.getSelectedValues() : [];
        requiresReviewVals.forEach(function(v) {
            formData.append('requires_review', v);
        });

        const queryParams = new URLSearchParams(formData).toString();
        window.location.href = (cfg.urls.auditTrail || '') + '?' + queryParams;
    });
});

  /* block 3 */
// Function to toggle details display
    function toggleDetails(elementId) {
        const element = document.getElementById(elementId);
        if (element.classList.contains('hidden')) {
            element.classList.remove('hidden');
        } else {
            element.classList.add('hidden');
        }
    }

    // Helper function to render activity badge
    function renderActivityBadge(activityType) {
        const activityMap = {
            // ── Session ────────────────────────────────────────────────────
            'page_view':   { icon: 'fa-eye',          bg: 'bg-blue-100',   text: 'text-blue-800',   label: cfg.t.page_view_ba53c448 },
            // Generic POST / non-submit HTTP actions (APIs, AJAX, dashboard widgets)
            'request':     { icon: 'fa-bolt',         bg: 'bg-slate-100',  text: 'text-slate-800',  label: cfg.t.back_office_action_512545c1 },
            'backoffice_action': { icon: 'fa-bolt', bg: 'bg-slate-100',  text: 'text-slate-800',  label: cfg.t.back_office_action_512545c1 },
            'admin_ai':       { icon: 'fa-microchip',   bg: 'bg-violet-100', text: 'text-violet-800', label: cfg.t.ai_admin_e5830a89 },
            'admin_content':  { icon: 'fa-folder-open', bg: 'bg-amber-100',  text: 'text-amber-800',  label: cfg.t.content_f15c1cae },
            'admin_embed':    { icon: 'fa-code',        bg: 'bg-cyan-100',    text: 'text-cyan-800',   label: cfg.t.embed_f210e321 },
            'admin_assignments': { icon: 'fa-tasks',    bg: 'bg-blue-100',    text: 'text-blue-800',   label: cfg.t.assignments_56c4b82e },
            'admin_organization': { icon: 'fa-sitemap', bg: 'bg-indigo-100', text: 'text-indigo-800', label: cfg.t.organization_d6b25879 },
            'admin_system':   { icon: 'fa-database',    bg: 'bg-gray-100',    text: 'text-gray-800',   label: cfg.t.system_a45da96d },
            'admin_users':    { icon: 'fa-users',       bg: 'bg-teal-100',    text: 'text-teal-800',   label: cfg.t.users_f9aae5fd },
            'admin_forms':    { icon: 'fa-wpforms',     bg: 'bg-blue-50',     text: 'text-blue-800',   label: cfg.t.forms_64502425 },
            'admin_analytics': { icon: 'fa-chart-line', bg: 'bg-emerald-100', text: 'text-emerald-800', label: cfg.t.analytics_a768caa9 },
            'admin_utilities': { icon: 'fa-tools',     bg: 'bg-orange-100',  text: 'text-orange-800', label: cfg.t.utilities_ceba282b },
            'admin_settings': { icon: 'fa-cog',         bg: 'bg-slate-100',   text: 'text-slate-800',  label: cfg.t.settings_f4f70727 },
            'admin_plugin':   { icon: 'fa-puzzle-piece', bg: 'bg-pink-100',   text: 'text-pink-800',   label: cfg.t.plugins_bb38096a },
            'admin_notifications': { icon: 'fa-bell',   bg: 'bg-yellow-100',  text: 'text-yellow-800', label: cfg.t.notifications_a274f4d4 },
            'admin_monitoring': { icon: 'fa-heartbeat',  bg: 'bg-red-50',      text: 'text-red-800',    label: cfg.t.monitoring_423e555c },
            'admin_portal':   { icon: 'fa-compass',     bg: 'bg-sky-100',     text: 'text-sky-800',    label: cfg.t.portal_3e9b3ac6 },
            'admin_other':    { icon: 'fa-ellipsis-h', bg: 'bg-gray-100',    text: 'text-gray-700',   label: cfg.t.other_6311ae17 },
            'login':       { icon: 'fa-sign-in-alt',  bg: 'bg-green-100',  text: 'text-green-800',  label: cfg.t.logged_in_e63b69d4 },
            'logout':      { icon: 'fa-sign-out-alt', bg: 'bg-orange-100', text: 'text-orange-800', label: cfg.t.logged_out_730f878b },
            'profile_update': { icon: 'fa-user-edit', bg: 'bg-teal-100',   text: 'text-teal-800',   label: cfg.t.profile_updated_e914c893 },

            // ── Form / Entry actions (new canonical types) ─────────────────
            'form_saved':      { icon: 'fa-save',        bg: 'bg-blue-100',   text: 'text-blue-800',   label: cfg.t.form_saved_850f782d },
            'form_submitted':  { icon: 'fa-paper-plane', bg: 'bg-green-100',  text: 'text-green-800',  label: cfg.t.form_submitted_e387d331 },
            'form_approved':   { icon: 'fa-check-double',bg: 'bg-green-100',  text: 'text-green-800',  label: cfg.t.form_approved_86f1cce6 },
            'form_reopened':   { icon: 'fa-lock-open',   bg: 'bg-amber-100',  text: 'text-amber-800',  label: cfg.t.form_reopened_ffeed7eb },
            'form_validated':  { icon: 'fa-check-circle',bg: 'bg-teal-100',   text: 'text-teal-800',   label: cfg.t.form_validated_1f75d79d },

            // ── Legacy form types (old DB rows) ───────────────────────────
            'form_submit': { icon: 'fa-paper-plane', bg: 'bg-green-100',  text: 'text-green-800',  label: cfg.t.form_submitted_e387d331 },
            'form_save':   { icon: 'fa-save',        bg: 'bg-blue-100',   text: 'text-blue-800',   label: cfg.t.form_saved_850f782d },

            // ── Data actions ───────────────────────────────────────────────
            'data_modified': { icon: 'fa-pen',      bg: 'bg-yellow-100', text: 'text-yellow-800', label: cfg.t.data_modified_83ae0c1a },
            'data_deleted':  { icon: 'fa-trash',    bg: 'bg-red-100',    text: 'text-red-800',    label: cfg.t.data_deleted_dd3aefaa },
            'data_update':   { icon: 'fa-pen',      bg: 'bg-yellow-100', text: 'text-yellow-800', label: cfg.t.data_modified_83ae0c1a },
            'data_delete':   { icon: 'fa-trash',    bg: 'bg-red-100',    text: 'text-red-800',    label: cfg.t.data_deleted_dd3aefaa },
            'data_export':   { icon: 'fa-download', bg: 'bg-orange-100', text: 'text-orange-800', label: cfg.t.data_exported_6d0c1179 },

            // ── File ───────────────────────────────────────────────────────
            'file_uploaded': { icon: 'fa-upload', bg: 'bg-purple-100', text: 'text-purple-800', label: cfg.t.file_uploaded_358afefc },
            'file_upload':   { icon: 'fa-upload', bg: 'bg-purple-100', text: 'text-purple-800', label: cfg.t.file_uploaded_358afefc },

            // ── Generic admin verbs ────────────────────────────────────────
            'create': { icon: 'fa-plus',  bg: 'bg-green-100',  text: 'text-green-800',  label: cfg.t.created_0eceeb45 },
            'update': { icon: 'fa-pen',   bg: 'bg-yellow-100', text: 'text-yellow-800', label: cfg.t.updated_ff0a3b7f },
            'delete': { icon: 'fa-trash', bg: 'bg-red-100',    text: 'text-red-800',    label: cfg.t.deleted_5fe6005b },

            // ── Account ───────────────────────────────────────────────────
            'account_created': { icon: 'fa-user-plus', bg: 'bg-green-100', text: 'text-green-800', label: cfg.t.account_created_6d4030a6 },

            // ── User management ───────────────────────────────────────────
            'user_create': { icon: 'fa-user-plus',  bg: 'bg-green-100',  text: 'text-green-800',  label: cfg.t.user_added_ed373f2b },
            'user_update': { icon: 'fa-user-edit',  bg: 'bg-yellow-100', text: 'text-yellow-800', label: cfg.t.user_modified_d122cb8f },
            'user_delete': { icon: 'fa-user-times', bg: 'bg-red-100',    text: 'text-red-800',    label: cfg.t.user_deleted_a6b3c3f0 },
            'access_request_approve': { icon: 'fa-user-check', bg: 'bg-green-100',  text: 'text-green-800',  label: cfg.t.access_approved_0ea30785 },
            'access_request_reject':  { icon: 'fa-user-slash', bg: 'bg-red-100',    text: 'text-red-800',    label: cfg.t.access_rejected_1722c8f4 },
            'kickout_device':  { icon: 'fa-sign-out-alt', bg: 'bg-orange-100', text: 'text-orange-800', label: cfg.t.device_kicked_cccaa389 },
            'remove_device':   { icon: 'fa-times',        bg: 'bg-red-100',    text: 'text-red-800',    label: cfg.t.device_removed_1e6dc98e },

            // ── Template actions ───────────────────────────────────────────
            'template_create':         { icon: 'fa-plus-square', bg: 'bg-indigo-100', text: 'text-indigo-800', label: cfg.t.template_created_a5d10e13 },
            'template_update':         { icon: 'fa-pen',         bg: 'bg-indigo-100', text: 'text-indigo-800', label: cfg.t.template_modified_b654f948 },
            'template_delete':         { icon: 'fa-trash',       bg: 'bg-red-100',    text: 'text-red-800',    label: cfg.t.template_deleted_25af8733 },
            'template_duplicate':      { icon: 'fa-copy',        bg: 'bg-indigo-100', text: 'text-indigo-800', label: cfg.t.template_duplicated_64d23766 },
            'template_export':         { icon: 'fa-download',    bg: 'bg-indigo-100', text: 'text-indigo-800', label: cfg.t.template_exported_545e8e01 },
            'template_import':         { icon: 'fa-upload',      bg: 'bg-indigo-100', text: 'text-indigo-800', label: cfg.t.template_imported_4a0a2447 },
            'template_import_excel':   { icon: 'fa-file-excel',  bg: 'bg-green-100',  text: 'text-green-800',  label: cfg.t.excel_imported_87e4f08b },
            'template_variables_update': { icon: 'fa-code',      bg: 'bg-indigo-100', text: 'text-indigo-800', label: cfg.t.variables_updated_03104b41 },
            'template_sharing_update': { icon: 'fa-share-alt',   bg: 'bg-pink-100',   text: 'text-pink-800',   label: cfg.t.sharing_updated_b8526729 },

            // ── Version actions ────────────────────────────────────────────
            'template_version_deploy':  { icon: 'fa-rocket',       bg: 'bg-purple-100', text: 'text-purple-800', label: cfg.t.version_deployed_e425c923 },
            'template_version_create':  { icon: 'fa-plus-circle',  bg: 'bg-blue-100',   text: 'text-blue-800',   label: cfg.t.version_created_8d45bbe1 },
            'template_version_delete':  { icon: 'fa-trash',        bg: 'bg-red-100',    text: 'text-red-800',    label: cfg.t.version_deleted_53217371 },
            'template_version_discard': { icon: 'fa-times-circle', bg: 'bg-orange-100', text: 'text-orange-800', label: cfg.t.version_discarded_3813a86e },
            'template_version_comment': { icon: 'fa-comment-alt',  bg: 'bg-gray-100',   text: 'text-gray-600',   label: cfg.t.version_note_added_e7f184ff },

            // ── Section actions ────────────────────────────────────────────
            'form_section_create':    { icon: 'fa-plus',      bg: 'bg-blue-50',  text: 'text-blue-700',  label: cfg.t.section_added_873a0653 },
            'form_section_update':    { icon: 'fa-pen',       bg: 'bg-blue-50',  text: 'text-blue-700',  label: cfg.t.section_modified_e2d05579 },
            'form_section_delete':    { icon: 'fa-minus-circle', bg: 'bg-red-50', text: 'text-red-700',  label: cfg.t.section_deleted_0bd57f07 },
            'form_section_duplicate': { icon: 'fa-copy',      bg: 'bg-blue-50',  text: 'text-blue-700',  label: cfg.t.section_duplicated_a5d840bc },
            'form_section_configure': { icon: 'fa-sliders-h', bg: 'bg-blue-50',  text: 'text-blue-700',  label: cfg.t.section_configured_29c0d36e },
            'form_section_unarchive': { icon: 'fa-box-open',  bg: 'bg-green-50', text: 'text-green-700', label: cfg.t.section_restored_71461172 },

            // ── Item actions ───────────────────────────────────────────────
            'form_item_create':    { icon: 'fa-plus-circle', bg: 'bg-gray-100', text: 'text-gray-800', label: cfg.t.item_added_eaaef0b7 },
            'form_item_update':    { icon: 'fa-pen',         bg: 'bg-gray-100', text: 'text-gray-800', label: cfg.t.item_modified_8d7d29b8 },
            'form_item_delete':    { icon: 'fa-times',       bg: 'bg-red-50',   text: 'text-red-700',  label: cfg.t.item_deleted_13b8ca97 },
            'form_item_duplicate': { icon: 'fa-copy',        bg: 'bg-gray-100', text: 'text-gray-800', label: cfg.t.item_duplicated_ec6eedaa },
            'form_item_unarchive': { icon: 'fa-box-open',    bg: 'bg-green-50', text: 'text-green-700',label: cfg.t.item_restored_30bd7bd6 },

            // ── Session / security ─────────────────────────────────────────
            'cleanup_sessions':      { icon: 'fa-broom',    bg: 'bg-gray-100',   text: 'text-gray-800',   label: cfg.t.sessions_cleaned_8cc3b21d },
            'end_user_session':      { icon: 'fa-stop',     bg: 'bg-orange-100', text: 'text-orange-800', label: cfg.t.session_ended_e73100f6 },
            'resolve_security_event':{ icon: 'fa-shield-alt',bg: 'bg-green-100', text: 'text-green-800',  label: cfg.t.security_event_resolved_7ea8f60f },

            // ── API keys ───────────────────────────────────────────────────
            'api_key_create': { icon: 'fa-key',       bg: 'bg-teal-100',  text: 'text-teal-800',  label: cfg.t.api_key_created_46906edf },
            'api_key_revoke': { icon: 'fa-key',       bg: 'bg-red-100',   text: 'text-red-800',   label: cfg.t.api_key_revoked_5f00912c },

            // ── RBAC ───────────────────────────────────────────────────────
            'rbac_role_create':  { icon: 'fa-user-shield', bg: 'bg-violet-100', text: 'text-violet-800', label: cfg.t.role_created_2a762b85 },
            'rbac_role_update':  { icon: 'fa-user-shield', bg: 'bg-violet-100', text: 'text-violet-800', label: cfg.t.role_modified_2bda5ba8 },
            'rbac_role_delete':  { icon: 'fa-user-shield', bg: 'bg-red-100',    text: 'text-red-800',    label: cfg.t.role_deleted_16b4ba89 },
            'rbac_grant_create': { icon: 'fa-lock-open',   bg: 'bg-violet-100', text: 'text-violet-800', label: cfg.t.permission_granted_1614f198 },
            'rbac_grant_delete': { icon: 'fa-lock',        bg: 'bg-red-100',    text: 'text-red-800',    label: cfg.t.permission_removed_116c5fa3 },

            // ── Endpoint-specific app / admin POSTs ───────────────────────
            'device_registered':   { icon: 'fa-mobile-alt', bg: 'bg-cyan-100',   text: 'text-cyan-800',   label: cfg.t.device_registration_db2d1915 },
            'device_unregistered': { icon: 'fa-mobile-alt', bg: 'bg-gray-100',   text: 'text-gray-700',   label: cfg.t.device_unregistered_5e3026f8 },
            'settings_updated':    { icon: 'fa-cog',        bg: 'bg-slate-100',  text: 'text-slate-800',  label: cfg.t.system_settings_d4529e13 },
            'email_templates_updated': { icon: 'fa-envelope-open-text', bg: 'bg-slate-100', text: 'text-slate-800', label: cfg.t.email_templates_e2925290 },
            'country_access_requested': { icon: 'fa-globe', bg: 'bg-blue-50',   text: 'text-blue-800',   label: cfg.t.country_access_ca116168 },
            'country_selected':    { icon: 'fa-flag',       bg: 'bg-blue-50',    text: 'text-blue-800',   label: cfg.t.country_selection_cd8e66c6 },

            // ── AI chat (DELETE on /api/ai/v2/...) ──────────────────────────
            'ai_conversation_deleted':      { icon: 'fa-comments', bg: 'bg-red-50',    text: 'text-red-800',    label: cfg.t.ai_chat_deleted_9c30a335 },
            'ai_conversations_deleted_all': { icon: 'fa-comments', bg: 'bg-red-100',   text: 'text-red-900',   label: cfg.t.all_ai_chats_deleted_9546c247 },
        };

        const activity = activityMap[activityType] || {
            icon: 'fa-cog',
            bg: 'bg-gray-100',
            text: 'text-gray-800',
            label: humanizeToken(activityType)
        };
        return '<span class="px-2 inline-flex items-center text-xs leading-5 font-semibold rounded-full ' + activity.bg + ' ' + activity.text + '"><i class="fas ' + activity.icon + ' mr-1"></i> ' + activity.label + '</span>';
    }

    // Helper function to render risk level badge
    function renderRiskBadge(riskLevel) {
        if (isNilOrEmpty(riskLevel)) {
            return '<span class="text-sm text-gray-500">' + EMPTY_VALUE_PLACEHOLDER + '</span>';
        }
        const riskMap = {
            'critical': { bg: 'bg-red-200', text: 'text-red-900', icon: '<i class="fas fa-exclamation-triangle mr-1"></i>' },
            'high': { bg: 'bg-red-100', text: 'text-red-800', icon: '' },
            'medium': { bg: 'bg-yellow-100', text: 'text-yellow-800', icon: '' },
            'low': { bg: 'bg-green-100', text: 'text-green-800', icon: '' }
        };
        const risk = riskMap[riskLevel] || { bg: 'bg-gray-100', text: 'text-gray-800', icon: '' };
        const label = humanizeToken(riskLevel);
        return '<span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full ' + risk.bg + ' ' + risk.text + '">' + risk.icon + label + '</span>';
    }

    function getHttpStatusCategory(statusCode) {
        if (statusCode === null || statusCode === undefined || statusCode === '') return 'normal';
        const numericStatus = Number(statusCode);
        if (!Number.isFinite(numericStatus)) return 'normal';
        if (numericStatus >= 500) return 'server_error';
        if (numericStatus >= 400) return 'error';
        if (numericStatus >= 300) return 'redirect';
        if (numericStatus >= 200) return 'success';
        if (numericStatus >= 100) return 'informational';
        return 'other';
    }

    // Helper function to render status badge
    function renderStatusBadge(entry) {
        const successBadge = '<span class="px-2 inline-flex items-center text-xs leading-5 font-semibold rounded-full bg-green-100 text-green-800"><i class="fas fa-check-circle mr-1"></i> ' + cfg.t.success_505a83f2 + '</span>';

        if (entry.type === 'admin_action' && entry.requires_review) {
            return '<span class="px-2 inline-flex items-center text-xs leading-5 font-semibold rounded-full bg-orange-100 text-orange-800"><i class="fas fa-exclamation-circle mr-1"></i> ' + cfg.t.needs_review_994f197b + '</span>';
        } else if (entry.type === 'activity' && entry.response_status_code !== null && entry.response_status_code !== undefined) {
            const statusCode = Number(entry.response_status_code);
            const statusCategory = getHttpStatusCategory(statusCode);
            if (statusCategory === 'server_error' || statusCategory === 'error') {
                return '<span class="px-2 inline-flex items-center text-xs leading-5 font-semibold rounded-full bg-red-100 text-red-800" title="HTTP ' + statusCode + '"><i class="fas fa-times-circle mr-1"></i>' + cfg.t.error_902b0d55 + '</span>';
            }
            if (statusCategory === 'success') {
                return '<span class="px-2 inline-flex items-center text-xs leading-5 font-semibold rounded-full bg-green-100 text-green-800" title="HTTP ' + statusCode + '"><i class="fas fa-check-circle mr-1"></i>' + cfg.t.success_505a83f2 + '</span>';
            }
            if (statusCategory === 'redirect') {
                return '<span class="px-2 inline-flex items-center text-xs leading-5 font-semibold rounded-full bg-blue-100 text-blue-800" title="HTTP ' + statusCode + '"><i class="fas fa-random mr-1"></i>' + cfg.t.redirect_4202ef11 + '</span>';
            }
            if (statusCategory === 'informational') {
                return '<span class="px-2 inline-flex items-center text-xs leading-5 font-semibold rounded-full bg-gray-100 text-gray-700" title="HTTP ' + statusCode + '"><i class="fas fa-info-circle mr-1"></i>' + cfg.t.info_4059b025 + '</span>';
            }
            return successBadge;
        }

        // Non-reviewed admin actions and activity rows without status code
        // are treated as successful outcomes for visual consistency.
        return successBadge;
    }

    // AG Grid helper instance
    let gridHelper = null;
    let gridApi = null;

    const auditTrailData = (cfg.pageData && cfg.pageData.gridRows) || [];
    const sessionLogsListUrl = cfg.urls.sessionLogs || '';

    // Column definitions for ag-grid
    const columnDefs = [
        {
            field: 'timestamp',
            headerName: cfg.t.timestamp_a3d5de3e,
            width: 180,
            minWidth: 150,
            maxWidth: 250,
            filter: 'agDateColumnFilter',
            sortable: true,
            cellRenderer: function(params) {
                // Use DateTimeUtils for proper timezone conversion
                if (typeof DateTimeUtils !== 'undefined') {
                    return DateTimeUtils.agGridDualLineRenderer(params, { showTimezone: true });
                }
                // Fallback
                return '<div class="text-sm text-gray-900">' + (params.data.timestamp || '') + '</div>';
            },
            cellStyle: { 'white-space': 'normal', 'line-height': '1.4' }
        },
        {
            field: 'user_name',
            headerName: cfg.t.user_8f9bfe9d,
            width: 200,
            minWidth: 150,
            maxWidth: 300,
            filter: 'agTextColumnFilter',
            sortable: true,
            cellRenderer: function(params) {
                return AgGridRenderers.userHoverCell(params, {
                    idField: 'user_id',
                    nameField: 'user_name',
                    emailField: 'user_email',
                    titleField: 'user_title',
                    activeField: 'user_active',
                    profileColorField: 'user_profile_color',
                    fallbackLabel: cfg.t.unknown_user_bd4de0d0,
                    showEmail: true
                });
            },
            cellStyle: AgGridRenderers.userHoverCellStyle
        },
        {
            field: 'entity_name',
            headerName: cfg.t.entity_1a434bef,
            width: 160,
            minWidth: 120,
            maxWidth: 260,
            filter: 'customSetFilter',
            sortable: true,
            cellRenderer: function(params) {
                if (isNilOrEmpty(params.value)) return '<span class="text-sm text-gray-500">' + EMPTY_VALUE_PLACEHOLDER + '</span>';
                const typeLabels = {
                    'country':        cfg.t.country_59716c97,
                    'ns_branch':      cfg.t.ns_branch_6b17aba2,
                    'ns_subbranch':   cfg.t.ns_sub_branch_2c961d34,
                    'ns_localunit':   cfg.t.local_unit_4f6a34f5,
                    'division':       cfg.t.division_3025cdaa,
                    'department':     cfg.t.department_1d17cb99,
                };
                const entityType = params.data.entity_type || '';
                const typeLabel = typeLabels[entityType] || humanizeToken(entityType);
                const badge = typeLabel && entityType !== 'country'
                    ? ' <span class="ml-1 px-1 py-0.5 text-xs bg-gray-100 text-gray-500 rounded">' + escapeHtml(typeLabel) + '</span>'
                    : '';
                return '<span class="text-sm text-gray-900">' + escapeHtml(params.value) + '</span>' + badge;
            },
            cellStyle: { 'white-space': 'normal', 'line-height': '1.4' }
        },
        {
            field: 'activity_type',
            headerName: cfg.t.activity_ecfc2dff,
            width: 180,
            minWidth: 150,
            maxWidth: 250,
            filter: 'customSetFilter',
            sortable: true,
            cellRenderer: function(params) {
                return renderActivityBadge(params.value);
            },
            cellStyle: { 'white-space': 'nowrap' }
        },
        {
            field: 'description',
            headerName: cfg.t.description_b5a7adde,
            width: 320,
            minWidth: 250,
            maxWidth: 520,
            filter: 'agTextColumnFilter',
            sortable: true,
            cellRenderer: function(params) {
                const valueText = isNilOrEmpty(params.value) ? EMPTY_VALUE_PLACEHOLDER : String(params.value);
                let html = '<div class="text-sm text-gray-900" style="word-wrap: break-word; overflow-wrap: break-word; white-space: normal;" title="' + escapeHtml(valueText) + '">' + escapeHtml(valueText) + '</div>';
                if (params.data.details !== null && params.data.details !== undefined) {
                    const detailsId = 'details-' + params.data.id;
                    html += '<button class="text-xs text-blue-500 hover:text-blue-700 mt-1 toggle-details-btn" type="button" data-details-id="' + detailsId + '">' + cfg.t.view_details_5d5cd268 + '</button>';
                    html += '<div class="hidden mt-2 p-3 bg-gray-100 rounded-md border border-gray-200 min-w-0 max-w-full overflow-x-auto" id="' + detailsId + '">';
                    html += renderDetailsValue(params.data.details, params.data);
                    html += '</div>';
                }
                return html;
            },
            cellStyle: { 'white-space': 'normal', 'word-wrap': 'break-word', 'overflow-wrap': 'break-word', 'line-height': '1.4' },
            autoHeight: true,
            wrapText: true
        },
        {
            field: 'risk_level',
            headerName: cfg.t.risk_level_f9bf0a9d,
            width: 150,
            minWidth: 120,
            maxWidth: 200,
            filter: 'customSetFilter',
            sortable: true,
            cellRenderer: function(params) {
                return renderRiskBadge(params.value);
            }
        },
        {
            field: 'ip_address',
            headerName: cfg.t.ip_address_5b8c99da,
            width: 150,
            minWidth: 120,
            maxWidth: 200,
            filter: 'agTextColumnFilter',
            sortable: true,
            cellRenderer: function(params) {
                return renderTextCell(params.value, { mono: true });
            }
        },
        {
            field: 'user_session_id',
            headerName: cfg.t.session_71c7ae29,
            width: 130,
            minWidth: 100,
            maxWidth: 220,
            filter: 'agTextColumnFilter',
            sortable: true,
            hide: true,
            cellRenderer: function(params) {
                var sid = params.value;
                if (isNilOrEmpty(sid)) {
                    return '<span class="text-sm text-gray-500">' + EMPTY_VALUE_PLACEHOLDER + '</span>';
                }
                var url = sessionLogsListUrl + '?session_id=' + encodeURIComponent(String(sid));
                var shortId = String(sid).length > 14 ? String(sid).slice(0, 12) + '…' : String(sid);
                return '<a href="' + escapeHtml(url) + '" class="text-xs font-mono text-teal-800 hover:underline" title="' + escapeHtml(String(sid)) + '">' +
                    escapeHtml(shortId) + '</a>';
            }
        },
        {
            field: 'status',
            headerName: cfg.t.status_ec53a8c4,
            width: 180,
            minWidth: 150,
            maxWidth: 250,
            filter: 'customSetFilter',
            sortable: true,
            valueGetter: function(params) {
                // Return a value for filtering/sorting
                if (params.data.type === 'admin_action' && params.data.requires_review) {
                    return 'needs_review';
                } else if (params.data.type === 'activity' && params.data.response_status_code !== null && params.data.response_status_code !== undefined) {
                    return getHttpStatusCategory(params.data.response_status_code);
                }
                return 'success';
            },
            cellRenderer: function(params) {
                return renderStatusBadge(params.data);
            },
            cellStyle: { 'white-space': 'nowrap' }
        },

        // ── Optional technical detail columns (hidden by default) ──────────
        {
            field: 'http_method',
            headerName: cfg.t.method_4c3880bb,
            width: 100,
            minWidth: 80,
            maxWidth: 120,
            filter: 'customSetFilter',
            sortable: true,
            hide: true,
            cellRenderer: function(params) {
                if (isNilOrEmpty(params.value)) return '<span class="text-sm text-gray-500">' + EMPTY_VALUE_PLACEHOLDER + '</span>';
                const colors = {
                    'GET':    'bg-blue-100 text-blue-800',
                    'POST':   'bg-green-100 text-green-800',
                    'PUT':    'bg-yellow-100 text-yellow-800',
                    'PATCH':  'bg-amber-100 text-amber-800',
                    'DELETE': 'bg-red-100 text-red-800',
                };
                const cls = colors[params.value] || 'bg-gray-100 text-gray-800';
                return '<span class="px-2 py-0.5 text-xs font-mono font-semibold rounded ' + cls + '">' + escapeHtml(params.value) + '</span>';
            },
            cellStyle: { 'white-space': 'nowrap' }
        },
        {
            field: 'endpoint',
            headerName: cfg.t.endpoint_2a6ba72e,
            width: 260,
            minWidth: 180,
            maxWidth: 400,
            filter: 'agTextColumnFilter',
            sortable: true,
            hide: true,
            cellRenderer: function(params) {
                return renderTextCell(params.value, { mono: true, extraClasses: 'break-all text-xs text-gray-700' });
            },
            cellStyle: { 'white-space': 'normal', 'line-height': '1.4' },
            wrapText: true,
            autoHeight: true
        }
    ];

    const auditTrailGridEl = document.getElementById('auditTrailGrid');

    // Initialize grid using helper
    function initializeGrid() {
        if (!auditTrailGridEl) return;

        var result = AgGridHelper.create('auditTrailGrid', 'audit-trail', columnDefs, auditTrailData, {
            gridOptions: {
                getRowStyle: function(params) {
                    var riskLevel = params.data.risk_level;
                    if (riskLevel === 'high' || riskLevel === 'critical') {
                        return { 'background-color': '#fef2f2' };
                    } else if (riskLevel === 'medium') {
                        return { 'background-color': '#fefce8' };
                    }
                    return null;
                }
            }
        });
        gridHelper = result.helper;
        gridApi = result.api;
        window.gridApi = gridApi;
        window.gridHelper = gridHelper;
    }

    if (auditTrailGridEl) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initializeGrid);
        } else {
            initializeGrid();
        }
    }

    // Multiselect dropdown initialization (kept for filters)

    // Event delegation for toggle details buttons (AG Grid renders cells dynamically,
    // so we must use delegation on the grid container instead of direct binding)
    if (auditTrailGridEl) {
        auditTrailGridEl.addEventListener('click', function(e) {
            const btn = e.target.closest('.toggle-details-btn');
            if (btn) {
                e.preventDefault();
                e.stopPropagation();
                const detailsId = btn.getAttribute('data-details-id');
                const detailsEl = document.getElementById(detailsId);
                if (detailsEl) {
                    const isHidden = detailsEl.classList.contains('hidden');
                    detailsEl.classList.toggle('hidden');
                    btn.textContent = isHidden ? cfg.t.hide_details_7c5fb72b : cfg.t.view_details_5d5cd268;
                    // Tell AG Grid to recalculate row heights after expanding/collapsing
                    if (gridApi) {
                        gridApi.resetRowHeights();
                    }
                }
            }
        });
    }


})();
