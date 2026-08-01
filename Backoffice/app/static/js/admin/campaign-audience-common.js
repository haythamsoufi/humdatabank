/**
 * Shared audience / template filter helpers for admin communication & notification UIs.
 */
(function (global) {
    'use strict';

    const RBAC_ROLE_LABELS = {
        system_manager: 'System Manager',
        admin_core: 'Admin',
        assignment_editor_submitter: 'Focal Point',
        assignment_viewer: 'Viewer',
    };

    const ENTITY_ICONS = {
        country: 'fa-flag',
        national_society: 'fa-hand-holding-heart',
        ns_branch: 'fa-sitemap',
        ns_subbranch: 'fa-code-branch',
        ns_localunit: 'fa-map-marker-alt',
        division: 'fa-building',
        department: 'fa-briefcase',
        regional_office: 'fa-globe-americas',
        cluster_office: 'fa-map-pin',
    };

    const ENTITY_TYPE_NAMES = {
        country: 'Country',
        national_society: 'National Society',
        ns_branch: 'NS Branch',
        ns_subbranch: 'NS Sub-branch',
        ns_localunit: 'NS Local Unit',
        division: 'Secretariat Division',
        department: 'Secretariat Department',
        regional_office: 'Regional Office',
        cluster_office: 'Cluster Office',
    };

    function esc(text) {
        if (text == null || text === '') return '';
        const div = document.createElement('div');
        div.textContent = String(text);
        return div.innerHTML;
    }

    function getMultiSelectValues(selectEl) {
        if (!selectEl) return [];
        if (global.jQuery && global.jQuery.fn.select2 && global.jQuery(selectEl).hasClass('select2-hidden-accessible')) {
            const selected = global.jQuery(selectEl).val();
            return selected ? (Array.isArray(selected) ? selected : [selected]) : [];
        }
        return Array.from(selectEl.selectedOptions).map((opt) => opt.value).filter((v) => v);
    }

    function getMultiSelectIntValues(selectEl) {
        return getMultiSelectValues(selectEl)
            .map((id) => parseInt(id, 10))
            .filter((v) => !Number.isNaN(v));
    }

    function getMultiSelectCount(selectEl) {
        if (!selectEl) return 0;
        if (global.jQuery && global.jQuery.fn.select2 && global.jQuery(selectEl).hasClass('select2-hidden-accessible')) {
            const val = global.jQuery(selectEl).val();
            if (!val) return 0;
            return Array.isArray(val) ? val.length : 1;
        }
        return selectEl.selectedOptions.length;
    }

    function appendTemplateIdParams(params, templateIds) {
        (templateIds || []).forEach((tid) => {
            if (tid != null && tid !== '') {
                params.append('template_id', String(tid));
            }
        });
    }

    function appendBulkTemplateFiltersToParams(params, assignmentStatuses) {
        const statuses = assignmentStatuses || [];
        if (statuses.length > 0) {
            const templateSelect = document.getElementById('bulk-select-template');
            if (templateSelect) {
                appendTemplateIdParams(params, getMultiSelectValues(templateSelect));
            }
        }

        const templateFilterSelect = document.getElementById('bulk-select-template-filter');
        if (templateFilterSelect) {
            const selectedTemplates = getMultiSelectValues(templateFilterSelect);
            if (selectedTemplates.length > 0 && statuses.length === 0) {
                appendTemplateIdParams(params, selectedTemplates);
            }
        }
    }

    function buildBulkAudienceFilterParams(excludeUserIds) {
        const params = new URLSearchParams();

        const search = document.getElementById('bulk-search-users')?.value.trim();
        if (search) {
            params.append('search', search);
        }

        const selectedRoles = Array.from(document.querySelectorAll('.bulk-role-checkbox:checked')).map((cb) => cb.value);
        if (selectedRoles.length > 0) {
            selectedRoles.forEach((role) => params.append('role', role));
        }

        const activeStatuses = Array.from(document.querySelectorAll('.bulk-account-status-checkbox:checked')).map((cb) => cb.value);
        if (activeStatuses.length === 1) {
            params.append('active', activeStatuses[0]);
        }

        const countrySelect = document.getElementById('bulk-select-country');
        const selectedCountries = getMultiSelectValues(countrySelect);
        if (selectedCountries.length > 0) {
            selectedCountries.forEach((cid) => params.append('country_id', cid));
        }

        const entityType = document.getElementById('bulk-select-entity')?.value;
        if (entityType) {
            params.append('entity_type', entityType);
        }

        const assignmentStatuses = Array.from(document.querySelectorAll('.bulk-assignment-status-checkbox:checked')).map((cb) => cb.value);
        if (assignmentStatuses.length > 0) {
            assignmentStatuses.forEach((status) => {
                params.append('assignment_status', status);
            });
        }
        appendBulkTemplateFiltersToParams(params, assignmentStatuses);

        const assignmentFormSelect = document.getElementById('bulk-select-assignment-form');
        const selectedAssignments = getMultiSelectValues(assignmentFormSelect);
        if (selectedAssignments.length > 0) {
            selectedAssignments.forEach((afid) => params.append('assigned_form_id', afid));
        }

        const excludeSelected = document.getElementById('bulk-exclude-selected')?.checked;
        if (excludeSelected && Array.isArray(excludeUserIds)) {
            excludeUserIds.forEach((uid) => {
                params.append('exclude_user_id', uid);
            });
        }

        return params;
    }

    function getSelectedTemplateFilterIds() {
        const templateFilterSelect = document.getElementById('bulk-select-template-filter');
        return getMultiSelectIntValues(templateFilterSelect);
    }

    function filterAssignmentsByTemplateIds(allAssignments, selectedTemplateIds) {
        if (!Array.isArray(allAssignments)) return [];
        if (!selectedTemplateIds || selectedTemplateIds.length === 0) {
            return allAssignments;
        }
        return allAssignments.filter((assignment) => selectedTemplateIds.includes(assignment.template_id));
    }

    function formatRbacRoleCodes(codes) {
        const list = Array.isArray(codes) ? codes.filter(Boolean).map(String) : [];
        if (list.length === 0) return '—';
        return list.map((c) => RBAC_ROLE_LABELS[c] || c).join(', ');
    }

    function getEntityIcon(entityType) {
        return ENTITY_ICONS[entityType] || 'fa-folder';
    }

    function formatEntityType(entityType) {
        return ENTITY_TYPE_NAMES[entityType] || entityType;
    }

    function safeDomId(value) {
        return String(value || '')
            .toLowerCase()
            .trim()
            .replace(/\s+/g, '-')
            .replace(/[^a-z0-9_-]/g, '');
    }

    function updateMultiSelectCountDisplay(selectEl, countEl, labels) {
        if (!selectEl || !countEl) return;
        const selected = getMultiSelectCount(selectEl);
        if (selected > 0) {
            const unit = selected === 1 ? labels.singular : labels.plural;
            countEl.textContent = `${selected} ${unit} selected`;
            countEl.className = 'text-xs text-blue-600 font-medium mt-1';
        } else {
            countEl.textContent = labels.none;
            countEl.className = 'text-xs text-gray-500 mt-1';
        }
    }

    global.CampaignAudienceCommon = {
        esc,
        escapeHtml: esc,
        getMultiSelectValues,
        getMultiSelectIntValues,
        getMultiSelectCount,
        appendTemplateIdParams,
        appendBulkTemplateFiltersToParams,
        buildBulkAudienceFilterParams,
        getSelectedTemplateFilterIds,
        filterAssignmentsByTemplateIds,
        formatRbacRoleCodes,
        getEntityIcon,
        formatEntityType,
        safeDomId,
        updateMultiSelectCountDisplay,
    };
}(typeof window !== 'undefined' ? window : this));
