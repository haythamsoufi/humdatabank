/**
 * Indicator Bank Template Wizard — multi-step template creation from indicator bank.
 */

import { scrollElementIntoViewIfNeeded, stabilizeScrollAfterLayoutChange } from '../core/scroll-container.js';

const DEFAULT_LABELS = {
    loading: 'Loading…',
    loadingIndicators: 'Loading indicators…',
    noIndicators: 'No indicators match your filters.',
    selectAtLeastOne: 'Select at least one indicator to continue.',
    templateNameRequired: 'Template name is required.',
    createFailed: 'Could not create the template. Please try again.',
    creating: 'Creating template…',
    selectedCount: '{count} selected',
    matchCount: '{count} indicators',
    generalSection: 'General',
    unassignedSector: 'Other',
    unassignedArea: 'Other areas',
    unassignedProgram: 'Other programs',
    sharedPrograms: 'Shared across programs',
    clearFilters: 'Clear filters',
    activeFilters: 'Active filters:',
    programGroupNote: 'Indicators linked to multiple programs are placed in “Shared across programs”. Each indicator still appears only once in the template.',
    noFilterOptions: 'No options available',
    filterCount: '{count} selected',
    disaggEligibleSummary: 'Applies to {eligible} of {selected} selected indicators with units that support sex/age disaggregation.',
    disaggAgeGroupsHint: 'Leave empty to use platform defaults when age breakdown is allowed.',
};

const DISAGGREGATION_PRESETS = {
    total: ['total'],
    all: ['total', 'sex', 'age', 'sex_age'],
};

const FILTER_FIELDS = ['sector', 'subsector', 'programs', 'area', 'type'];

function getCsrfToken(config) {
    return config.csrfToken
        || document.querySelector('meta[name="csrf-token"]')?.getAttribute('content')
        || document.querySelector('input[name="csrf_token"]')?.value
        || '';
}

function formatLabel(template, values) {
    let text = template || '';
    Object.keys(values || {}).forEach((key) => {
        text = text.replace(`{${key}}`, String(values[key]));
    });
    return text;
}

function normalizePrograms(programs) {
    if (!Array.isArray(programs)) {
        return [];
    }
    return programs
        .map((program) => String(program || '').trim())
        .filter(Boolean);
}

function setButtonVisible(button, visible) {
    if (!button) return;
    button.hidden = !visible;
    button.classList.toggle('hidden', !visible);
    if (visible) {
        button.removeAttribute('aria-hidden');
        button.removeAttribute('tabindex');
    } else {
        button.setAttribute('aria-hidden', 'true');
        button.setAttribute('tabindex', '-1');
    }
}

export function initIndicatorBankWizard(config) {
    const labels = { ...DEFAULT_LABELS, ...(config.labels || {}) };
    const root = document.getElementById(config.rootId || 'indicator-bank-wizard');
    if (!root) return null;

    const state = {
        currentStep: 1,
        filterOptions: null,
        indicators: [],
        selectedIds: new Set(),
        sections: [],
        groupBy: 'sector',
        isLoading: false,
        isSubmitting: false,
        disaggregationModes: {},
        disaggregationPreset: 'total',
        customDisaggregationOptions: ['total'],
    };

    const els = {
        stepIndicators: root.querySelectorAll('[data-wizard-step-indicator]'),
        steps: root.querySelectorAll('[data-wizard-step]'),
        prevBtn: root.querySelector('[data-wizard-prev]'),
        nextBtn: root.querySelector('[data-wizard-next]'),
        submitBtn: root.querySelector('[data-wizard-submit]'),
        statusEl: root.querySelector('[data-wizard-status]'),
        filterEmergency: root.querySelector('#ibw-filter-emergency'),
        filterSearch: root.querySelector('#ibw-filter-search'),
        filterOptionContainers: {
            sector: root.querySelector('[data-filter-options="sector"]'),
            subsector: root.querySelector('[data-filter-options="subsector"]'),
            programs: root.querySelector('[data-filter-options="programs"]'),
            area: root.querySelector('[data-filter-options="area"]'),
            type: root.querySelector('[data-filter-options="type"]'),
        },
        filterCountEls: {
            sector: root.querySelector('[data-filter-count="sector"]'),
            subsector: root.querySelector('[data-filter-count="subsector"]'),
            programs: root.querySelector('[data-filter-count="programs"]'),
            area: root.querySelector('[data-filter-count="area"]'),
            type: root.querySelector('[data-filter-count="type"]'),
        },
        activeFiltersWrap: root.querySelector('[data-active-filters]'),
        activeFilterChips: root.querySelector('[data-active-filter-chips]'),
        clearFiltersBtn: root.querySelector('[data-clear-filters]'),
        indicatorList: root.querySelector('[data-indicator-list]'),
        indicatorLoading: root.querySelector('[data-indicator-loading]'),
        indicatorEmpty: root.querySelector('[data-indicator-empty]'),
        indicatorCount: root.querySelector('[data-indicator-count]'),
        selectAllBtn: root.querySelector('[data-select-all]'),
        clearSelectionBtn: root.querySelector('[data-clear-selection]'),
        groupByRadios: root.querySelectorAll('input[name="ibw-group-by"]'),
        groupByOptions: root.querySelector('[data-wizard-step="3"] .nt-group-options'),
        groupByNote: root.querySelector('[data-group-by-note]'),
        sectionBuckets: root.querySelector('[data-section-buckets]'),
        templateName: root.querySelector('#ibw-template-name'),
        templateDescription: root.querySelector('#ibw-template-description'),
        templateSelfReport: root.querySelector('#ibw-add-to-self-report'),
        templateAccessBtn: root.querySelector('#ibw-template-access-btn'),
        templateAccessSummary: root.querySelector('#ibw-template-access-summary'),
        templateOwnerField: root.querySelector('#ibw-template-owner-field'),
        templateSharedFields: root.querySelector('#ibw-template-shared-fields'),
        disaggSettings: root.querySelector('[data-disagg-settings]'),
        disaggPresets: root.querySelector('[data-wizard-step="4"] .nt-disagg-presets'),
        disaggEligibleSummary: root.querySelector('[data-disagg-eligible-summary]'),
        disaggPresetRadios: root.querySelectorAll('input[name="ibw-disagg-preset"]'),
        disaggOptionsContainer: root.querySelector('[data-disagg-options]'),
        disaggAgeGroupsWrap: root.querySelector('[data-disagg-age-groups]'),
        ageGroupsConfig: root.querySelector('#ibw-age-groups-config'),
    };

    function preventFocusScrollOnCards(selector) {
        root.querySelectorAll(selector).forEach((card) => {
            card.addEventListener('mousedown', (event) => {
                event.preventDefault();
            });
        });
    }

    function getStepScrollAnchor(step) {
        if (step === 3) {
            return els.groupByOptions || root.querySelector('[data-wizard-step="3"]');
        }
        if (step === 4) {
            return els.disaggPresets || els.disaggSettings || root.querySelector('[data-wizard-step="4"]');
        }
        return null;
    }

    function setStatus(message, isError) {
        if (!els.statusEl) return;
        els.statusEl.textContent = message || '';
        els.statusEl.classList.toggle('nt-wizard-status--error', Boolean(isError));
    }

    function updateStepUi() {
        els.stepIndicators.forEach((indicator) => {
            const step = Number(indicator.getAttribute('data-wizard-step-indicator'));
            indicator.classList.toggle('nt-wizard__step-indicator--active', step === state.currentStep);
            indicator.classList.toggle('nt-wizard__step-indicator--done', step < state.currentStep);
        });

        els.steps.forEach((stepEl) => {
            const step = Number(stepEl.getAttribute('data-wizard-step'));
            stepEl.classList.toggle('nt-wizard-step--active', step === state.currentStep);
        });

        if (els.prevBtn) {
            els.prevBtn.disabled = state.currentStep <= 1 || state.isSubmitting;
        }

        const onLastStep = state.currentStep >= 4;
        setButtonVisible(els.nextBtn, !onLastStep);
        if (els.nextBtn) {
            els.nextBtn.disabled = state.isLoading || state.isSubmitting;
        }

        setButtonVisible(els.submitBtn, onLastStep);
        if (els.submitBtn) {
            els.submitBtn.disabled = state.isSubmitting;
        }

        updateGroupByNote();
    }

    function updateGroupByNote() {
        if (!els.groupByNote) return;
        const showProgramNote = state.currentStep === 3 && state.groupBy === 'program';
        els.groupByNote.classList.toggle('hidden', !showProgramNote);
        if (showProgramNote) {
            els.groupByNote.textContent = labels.programGroupNote;
        }
    }

    function scrollActiveStepIntoView(delayMs = 0) {
        const activeStep = root.querySelector('.nt-wizard-step--active');
        const target = activeStep?.querySelector('.nt-wizard-step__title') || activeStep;
        if (!target) return;

        const run = () => {
            scrollElementIntoViewIfNeeded(target);
        };

        if (delayMs > 0) {
            setTimeout(run, delayMs);
            return;
        }
        requestAnimationFrame(run);
    }

    async function goToStep(step) {
        state.currentStep = Math.max(1, Math.min(4, step));
        setStatus('');
        updateStepUi();

        if (state.currentStep === 2 && !state.indicators.length) {
            fetchIndicators();
        }
        if (state.currentStep === 3) {
            try {
                await loadFilterOptions();
            } catch (error) {
                setStatus(labels.createFailed, true);
                return;
            }
            refreshSectionGrouping();
        }
        if (state.currentStep === 4) {
            refreshDisaggregationUi();
        }

        if (state.currentStep !== 3 && state.currentStep !== 4) {
            scrollActiveStepIntoView(0);
        }
    }

    function getCheckedValues(field) {
        const container = els.filterOptionContainers[field];
        if (!container) return [];
        return Array.from(container.querySelectorAll('input[type="checkbox"]:checked'))
            .map((input) => input.value)
            .filter(Boolean);
    }

    function getCheckedLabels(field) {
        const container = els.filterOptionContainers[field];
        if (!container) return [];
        return Array.from(container.querySelectorAll('input[type="checkbox"]:checked'))
            .map((input) => ({
                value: input.value,
                label: input.dataset.label || input.value,
                field,
            }));
    }

    function updateFilterCounts() {
        FILTER_FIELDS.forEach((field) => {
            const countEl = els.filterCountEls[field];
            if (!countEl) return;
            const count = getCheckedValues(field).length;
            countEl.textContent = count ? formatLabel(labels.filterCount, { count }) : '';
        });
    }

    function updateActiveFilterPills() {
        if (!els.activeFiltersWrap || !els.activeFilterChips) return;

        const selections = FILTER_FIELDS.flatMap((field) => getCheckedLabels(field));
        const hasEmergency = Boolean(els.filterEmergency?.checked);
        const search = (els.filterSearch?.value || '').trim();

        els.activeFilterChips.innerHTML = '';

        selections.forEach((selection) => {
            const pill = document.createElement('span');
            pill.className = 'nt-filter-active-chip';
            pill.innerHTML = '<span></span>';
            pill.querySelector('span').textContent = selection.label;

            const removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.setAttribute('aria-label', `Remove ${selection.label}`);
            removeBtn.innerHTML = '<i class="fas fa-times" aria-hidden="true"></i>';
            removeBtn.addEventListener('click', () => {
                const input = els.filterOptionContainers[selection.field]?.querySelector(
                    `input[type="checkbox"][value="${CSS.escape(selection.value)}"]`,
                );
                if (input) {
                    input.checked = false;
                    onFilterChange();
                }
            });
            pill.appendChild(removeBtn);
            els.activeFilterChips.appendChild(pill);
        });

        if (hasEmergency) {
            const pill = document.createElement('span');
            pill.className = 'nt-filter-active-chip';
            pill.textContent = labels.emergencyOnly || 'Emergency only';
            els.activeFilterChips.appendChild(pill);
        }

        if (search) {
            const pill = document.createElement('span');
            pill.className = 'nt-filter-active-chip';
            pill.textContent = `"${search}"`;
            els.activeFilterChips.appendChild(pill);
        }

        const hasActive = selections.length > 0 || hasEmergency || Boolean(search);
        els.activeFiltersWrap.hidden = !hasActive;
    }

    function renderFilterOptions(field, options, configOptions = {}) {
        const container = els.filterOptionContainers[field];
        if (!container) return;

        const valueKey = configOptions.valueKey || 'id';
        const labelKey = configOptions.labelKey || 'name';
        const previous = new Set(getCheckedValues(field));

        container.innerHTML = '';
        if (!options || !options.length) {
            const empty = document.createElement('p');
            empty.className = 'nt-filter-empty';
            empty.textContent = labels.noFilterOptions;
            container.appendChild(empty);
            return;
        }

        options.forEach((option) => {
            const value = typeof option === 'string' ? option : String(option[valueKey]);
            const label = typeof option === 'string' ? option : option[labelKey];
            const sectorId = typeof option === 'object' && option.sector_id != null
                ? String(option.sector_id)
                : '';

            const chip = document.createElement('label');
            chip.className = 'nt-filter-chip';
            chip.innerHTML = `
                <input type="checkbox" value="">
                <span></span>
            `;
            const input = chip.querySelector('input');
            const text = chip.querySelector('span');
            input.value = value;
            input.dataset.label = label;
            input.dataset.filterField = field;
            if (sectorId) {
                input.dataset.sectorId = sectorId;
            }
            input.checked = previous.has(value);
            text.textContent = label;
            input.addEventListener('change', onFilterChange);
            container.appendChild(chip);
        });
    }

    function filterSubsectorsBySector() {
        if (!els.filterOptionContainers.subsector || !state.filterOptions) return;
        const selectedSectors = new Set(getCheckedValues('sector'));
        const inputs = els.filterOptionContainers.subsector.querySelectorAll('input[type="checkbox"]');

        inputs.forEach((input) => {
            const chip = input.closest('.nt-filter-chip');
            if (!chip) return;
            const sectorId = input.dataset.sectorId || '';
            const visible = !selectedSectors.size || selectedSectors.has(sectorId);
            chip.classList.toggle('nt-filter-chip--hidden', !visible);
            if (!visible && input.checked) {
                input.checked = false;
            }
        });
    }

    function onFilterChange() {
        if (state.filterOptions) {
            filterSubsectorsBySector();
        }
        updateFilterCounts();
        updateActiveFilterPills();
    }

    function clearAllFilters() {
        FILTER_FIELDS.forEach((field) => {
            const container = els.filterOptionContainers[field];
            if (!container) return;
            container.querySelectorAll('input[type="checkbox"]').forEach((input) => {
                input.checked = false;
            });
        });
        if (els.filterEmergency) {
            els.filterEmergency.checked = false;
        }
        if (els.filterSearch) {
            els.filterSearch.value = '';
        }
        onFilterChange();
    }

    async function loadFilterOptions() {
        if (state.filterOptions) {
            onFilterChange();
            return state.filterOptions;
        }

        const response = await fetch(config.urls.wizardOptions, {
            headers: { Accept: 'application/json' },
            credentials: 'same-origin',
        });
        if (!response.ok) {
            throw new Error('Failed to load filter options');
        }
        const payload = await response.json();
        state.filterOptions = payload;
        spefCatalog = null;
        state.disaggregationModes = payload.disaggregation_modes || {};

        renderFilterOptions('sector', payload.sectors || [], { valueKey: 'id', labelKey: 'name' });
        renderFilterOptions('subsector', payload.subsectors || [], { valueKey: 'id', labelKey: 'name' });
        renderFilterOptions('programs', payload.programs || []);
        renderFilterOptions(
            'area',
            (payload.areas || []).map((area) => ({ id: area.code, name: area.label || area.code })),
            { valueKey: 'id', labelKey: 'name' },
        );
        renderFilterOptions('type', payload.types || []);

        onFilterChange();
        return state.filterOptions;
    }

    function buildFiltersPayload() {
        const filters = [
            { field: 'archived', values: ['false'] },
        ];

        const sectors = getCheckedValues('sector');
        if (sectors.length) {
            filters.push({ field: 'sector', values: sectors, primary_only: true });
        }

        const subsectors = getCheckedValues('subsector');
        if (subsectors.length) {
            filters.push({ field: 'subsector', values: subsectors, primary_only: true });
        }

        const programs = getCheckedValues('programs');
        if (programs.length) {
            filters.push({ field: 'related_programs', values: programs });
        }

        const areas = getCheckedValues('area');
        if (areas.length) {
            filters.push({ field: 'area', values: areas });
        }

        const types = getCheckedValues('type');
        if (types.length) {
            filters.push({ field: 'type', values: types });
        }

        if (els.filterEmergency?.checked) {
            filters.push({ field: 'emergency', values: ['true'] });
        }

        const search = (els.filterSearch?.value || '').trim();
        return { filters, search };
    }

    function indicatorSupportsDisaggregation(indicator) {
        if (typeof indicator?.supports_disaggregation === 'boolean') {
            return indicator.supports_disaggregation;
        }
        const type = (indicator?.type || '').toLowerCase();
        const unit = (indicator?.unit || '').trim().toLowerCase();
        const allowedUnits = ['people', 'volunteers', 'staff'];
        return type === 'number' && allowedUnits.includes(unit);
    }

    function getEligibleDisaggregationIndicators() {
        return getSelectedIndicators().filter((indicator) => indicatorSupportsDisaggregation(indicator));
    }

    function renderDisaggregationOptionCheckboxes() {
        if (!els.disaggOptionsContainer) return;

        const modes = state.disaggregationModes || {};
        const entries = Object.entries(modes);
        const previous = new Set(state.customDisaggregationOptions);

        els.disaggOptionsContainer.innerHTML = '';
        if (!entries.length) {
            return;
        }

        entries.forEach(([value, label]) => {
            const option = document.createElement('label');
            option.className = 'nt-disagg-option';
            option.innerHTML = `
                <input type="checkbox" value="">
                <span></span>
            `;
            const input = option.querySelector('input');
            const text = option.querySelector('span');
            input.value = value;
            input.checked = previous.has(value);
            text.textContent = label;
            input.addEventListener('change', () => {
                state.customDisaggregationOptions = Array.from(
                    els.disaggOptionsContainer.querySelectorAll('input[type="checkbox"]:checked'),
                ).map((checkbox) => checkbox.value);
                updateDisaggregationAgeGroupsVisibility();
                stabilizeScrollAfterLayoutChange(getStepScrollAnchor(4));
            });
            option.addEventListener('mousedown', (event) => {
                event.preventDefault();
            });
            els.disaggOptionsContainer.appendChild(option);
        });
    }

    function getCurrentDisaggregationPreset() {
        const checked = Array.from(els.disaggPresetRadios || []).find((radio) => radio.checked);
        return checked?.value || state.disaggregationPreset || 'total';
    }

    function getSelectedDisaggregationOptions() {
        const preset = getCurrentDisaggregationPreset();
        if (preset === 'custom') {
            const selected = Array.from(
                els.disaggOptionsContainer?.querySelectorAll('input[type="checkbox"]:checked') || [],
            ).map((input) => input.value);
            return selected.length ? selected : ['total'];
        }
        return DISAGGREGATION_PRESETS[preset] || ['total'];
    }

    function updateDisaggregationAgeGroupsVisibility() {
        if (!els.disaggAgeGroupsWrap) return;
        const options = getSelectedDisaggregationOptions();
        const showAgeGroups = options.some((option) => option === 'age' || option === 'sex_age');
        els.disaggAgeGroupsWrap.classList.toggle('hidden', !showAgeGroups);
    }

    function updateDisaggregationPanel() {
        if (!els.disaggSettings) return;

        const selectedIndicators = getSelectedIndicators();
        const eligibleIndicators = getEligibleDisaggregationIndicators();
        const eligibleCount = eligibleIndicators.length;
        const selectedCount = selectedIndicators.length;

        if (!eligibleCount) {
            els.disaggSettings.hidden = true;
            return;
        }

        els.disaggSettings.hidden = false;
        if (els.disaggEligibleSummary) {
            els.disaggEligibleSummary.textContent = formatLabel(labels.disaggEligibleSummary, {
                eligible: eligibleCount,
                selected: selectedCount,
            });
        }

        const preset = getCurrentDisaggregationPreset();
        if (els.disaggOptionsContainer) {
            els.disaggOptionsContainer.classList.toggle('hidden', preset !== 'custom');
        }
        if (preset === 'custom' && !els.disaggOptionsContainer?.children.length) {
            renderDisaggregationOptionCheckboxes();
        }
        updateDisaggregationAgeGroupsVisibility();
    }

    function onDisaggregationPresetChange() {
        state.disaggregationPreset = getCurrentDisaggregationPreset();
        if (state.disaggregationPreset === 'custom') {
            renderDisaggregationOptionCheckboxes();
        }
        updateDisaggregationPanel();
        stabilizeScrollAfterLayoutChange(getStepScrollAnchor(4));
    }

    let spefCatalog = null;

    function normalizeSpefCode(code) {
        return String(code || '').trim().toUpperCase();
    }

    function getSpefCatalog() {
        if (spefCatalog) {
            return spefCatalog;
        }

        const areas = state.filterOptions?.areas || [];
        const byId = new Map();
        const byCode = new Map();

        areas.forEach((area, index) => {
            const code = normalizeSpefCode(area.code);
            if (area.id != null) {
                byId.set(Number(area.id), { index, area });
            }
            if (code) {
                byCode.set(code, { index, area });
            }
        });

        spefCatalog = { areas, byId, byCode };
        return spefCatalog;
    }

    function resolveAreaGroupMeta(indicator) {
        const catalog = getSpefCatalog();
        const spefId = indicator.indicator_spef_id;
        const rawCode = normalizeSpefCode(indicator.area);
        let catalogIndex = Number.MAX_SAFE_INTEGER;
        let code = '';
        let name = labels.unassignedArea;

        if (spefId != null && catalog.byId.has(Number(spefId))) {
            const entry = catalog.byId.get(Number(spefId));
            catalogIndex = entry.index;
            code = normalizeSpefCode(entry.area.code);
            name = indicator.area_label || entry.area.label || code;
        } else if (rawCode && catalog.byCode.has(rawCode)) {
            const entry = catalog.byCode.get(rawCode);
            catalogIndex = entry.index;
            code = rawCode;
            name = indicator.area_label || entry.area.label || code;
        } else if (rawCode) {
            catalogIndex = Number.MAX_SAFE_INTEGER - 1;
            code = rawCode;
            name = indicator.area_label || code;
        }

        return {
            key: code ? `area:${code}` : 'area:__unassigned__',
            name,
            sortOrder: catalogIndex,
            areaCode: code || null,
            spefId: spefId != null ? Number(spefId) : null,
        };
    }

    function sectorSortOrderById(sectorId) {
        if (!sectorId) {
            return Number.MAX_SAFE_INTEGER;
        }
        const sectors = state.filterOptions?.sectors || [];
        const match = sectors.find((sector) => String(sector.id) === String(sectorId));
        return match?.display_order ?? Number.MAX_SAFE_INTEGER - 1;
    }

    function sectorNameById(sectorId) {
        const sectors = state.filterOptions?.sectors || [];
        const match = sectors.find((sector) => String(sector.id) === String(sectorId));
        return match?.name || labels.unassignedSector;
    }

    function appendBadge(meta, className, text) {
        if (!text) return;
        const badge = document.createElement('span');
        badge.className = `nt-indicator-badge ${className}`;
        badge.textContent = text;
        meta.appendChild(badge);
    }

    function renderIndicatorCard(indicator) {
        const isSelected = state.selectedIds.has(indicator.id);
        const sectorId = indicator.sector?.primary;
        const sectorName = sectorId ? sectorNameById(sectorId) : '';
        const programs = normalizePrograms(indicator.related_programs);
        const areaLabel = indicator.area_label || indicator.area || '';

        const card = document.createElement('button');
        card.type = 'button';
        card.className = `nt-indicator-card${isSelected ? ' nt-indicator-card--selected' : ''}`;
        card.dataset.indicatorId = String(indicator.id);
        card.innerHTML = `
            <input type="checkbox" class="nt-indicator-card__checkbox" ${isSelected ? 'checked' : ''} aria-hidden="true" tabindex="-1">
            <span class="nt-indicator-card__body">
                <span class="nt-indicator-card__name"></span>
                <span class="nt-indicator-card__meta"></span>
            </span>
        `;
        card.querySelector('.nt-indicator-card__name').textContent = indicator.name || '';
        const meta = card.querySelector('.nt-indicator-card__meta');
        appendBadge(meta, 'nt-indicator-badge--type', indicator.type);
        appendBadge(meta, 'nt-indicator-badge--sector', sectorName);
        programs.forEach((program) => appendBadge(meta, 'nt-indicator-badge--program', program));
        appendBadge(meta, 'nt-indicator-badge--area', areaLabel);

        card.addEventListener('click', () => toggleIndicatorSelection(indicator.id));
        return card;
    }

    function renderIndicatorList() {
        if (!els.indicatorList) return;
        els.indicatorList.innerHTML = '';

        if (!state.indicators.length) {
            if (els.indicatorEmpty) els.indicatorEmpty.classList.remove('hidden');
            if (els.indicatorCount) {
                els.indicatorCount.textContent = formatLabel(labels.matchCount, { count: 0 });
            }
            return;
        }

        if (els.indicatorEmpty) els.indicatorEmpty.classList.add('hidden');
        state.indicators.forEach((indicator) => {
            els.indicatorList.appendChild(renderIndicatorCard(indicator));
        });
        updateSelectionSummary();
    }

    function updateSelectionSummary() {
        if (els.indicatorCount) {
            const selected = state.selectedIds.size;
            const visible = state.indicators.length;
            els.indicatorCount.textContent = `${formatLabel(labels.selectedCount, { count: selected })} · ${formatLabel(labels.matchCount, { count: visible })}`;
        }
    }

    function toggleIndicatorSelection(indicatorId) {
        const id = Number(indicatorId);
        if (state.selectedIds.has(id)) {
            state.selectedIds.delete(id);
        } else {
            state.selectedIds.add(id);
        }
        renderIndicatorList();
    }

    async function fetchIndicators() {
        if (state.isLoading) return;
        state.isLoading = true;
        setStatus('');
        if (els.indicatorLoading) els.indicatorLoading.classList.remove('hidden');
        if (els.indicatorList) els.indicatorList.innerHTML = '';

        try {
            const { filters, search } = buildFiltersPayload();
            const response = await fetch(config.urls.indicatorCount, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Accept: 'application/json',
                    'X-CSRFToken': getCsrfToken(config),
                },
                credentials: 'same-origin',
                body: JSON.stringify({
                    filters,
                    search,
                    include_indicators: true,
                }),
            });

            if (!response.ok) {
                throw new Error('Failed to load indicators');
            }

            const payload = await response.json();
            state.indicators = payload.indicators || [];
            renderIndicatorList();
        } catch (error) {
            setStatus(labels.createFailed, true);
            if (els.indicatorEmpty) {
                els.indicatorEmpty.classList.remove('hidden');
                els.indicatorEmpty.textContent = labels.createFailed;
            }
        } finally {
            state.isLoading = false;
            if (els.indicatorLoading) els.indicatorLoading.classList.add('hidden');
            updateStepUi();
        }
    }

    function getSelectedIndicators() {
        const lookup = new Map(state.indicators.map((indicator) => [indicator.id, indicator]));
        const selected = [];

        state.selectedIds.forEach((id) => {
            const indicator = lookup.get(id);
            if (indicator) {
                selected.push(indicator);
            }
        });

        return selected;
    }

    function compareSectionsForDisplay(a, b) {
        const orderA = a.sortOrder ?? Number.MAX_SAFE_INTEGER;
        const orderB = b.sortOrder ?? Number.MAX_SAFE_INTEGER;
        if (orderA !== orderB) {
            return orderA - orderB;
        }
        if (state.groupBy === 'area') {
            return (a.areaCode || '').localeCompare(b.areaCode || '', undefined, { sensitivity: 'base' });
        }
        return (a.name || '').localeCompare(b.name || '', undefined, { sensitivity: 'base' });
    }

    function resolveGroupMeta(indicator, groupBy) {
        if (groupBy === 'sector') {
            const sectorId = indicator.sector?.primary;
            const name = sectorId ? sectorNameById(sectorId) : labels.unassignedSector;
            return {
                key: sectorId ? `sector:${sectorId}` : 'sector:__unassigned__',
                name,
                sortOrder: sectorSortOrderById(sectorId),
            };
        }
        if (groupBy === 'area') {
            return resolveAreaGroupMeta(indicator);
        }
        if (groupBy === 'program') {
            const programs = normalizePrograms(indicator.related_programs);
            if (!programs.length) {
                return {
                    key: 'program:__unassigned__',
                    name: labels.unassignedProgram,
                    sortOrder: Number.MAX_SAFE_INTEGER,
                };
            }
            if (programs.length === 1) {
                return {
                    key: `program:${programs[0]}`,
                    name: programs[0],
                    sortOrder: Number.MAX_SAFE_INTEGER - 1,
                };
            }
            return {
                key: 'program:__shared__',
                name: labels.sharedPrograms,
                sortOrder: Number.MAX_SAFE_INTEGER,
            };
        }
        return {
            key: 'section:general',
            name: labels.generalSection,
            sortOrder: 0,
        };
    }

    function buildSections() {
        const selectedIndicators = getSelectedIndicators();
        const buckets = new Map();

        selectedIndicators.forEach((indicator) => {
            const group = resolveGroupMeta(indicator, state.groupBy);
            if (!buckets.has(group.key)) {
                buckets.set(group.key, {
                    name: group.name,
                    sortOrder: group.sortOrder,
                    areaCode: group.areaCode || null,
                    spefId: group.spefId || null,
                    indicators: [],
                });
            }
            buckets.get(group.key).indicators.push(indicator);
        });

        const sections = Array.from(buckets.values()).map((bucket) => ({
            name: bucket.name,
            sortOrder: bucket.sortOrder,
            areaCode: bucket.areaCode || null,
            spefId: bucket.spefId || null,
            indicator_ids: bucket.indicators.map((indicator) => indicator.id),
            indicators: bucket.indicators,
        }));

        if (state.groupBy === 'area' || state.groupBy === 'sector' || state.groupBy === 'program') {
            sections.sort(compareSectionsForDisplay);
        }

        state.sections = sections;
    }

    function refreshSectionGrouping() {
        buildSections();
        renderSectionBuckets();
        updateGroupByNote();
        stabilizeScrollAfterLayoutChange(els.groupByOptions || root.querySelector('[data-wizard-step="3"]'));
    }

    function refreshDisaggregationUi() {
        updateDisaggregationPanel();
        stabilizeScrollAfterLayoutChange(getStepScrollAnchor(4));
    }

    function renderSectionBuckets() {
        if (!els.sectionBuckets) return;
        els.sectionBuckets.innerHTML = '';

        if (!state.sections.length) {
            const empty = document.createElement('p');
            empty.className = 'nt-indicator-empty';
            empty.textContent = labels.selectAtLeastOne;
            els.sectionBuckets.appendChild(empty);
            return;
        }

        state.sections.forEach((section, index) => {
            const bucket = document.createElement('div');
            bucket.className = 'nt-section-bucket';
            bucket.innerHTML = `
                <div class="nt-section-bucket__header">
                    <input type="text" class="nt-section-bucket__name-input" value="" maxlength="100" aria-label="Section name">
                    <span class="nt-section-bucket__count"></span>
                </div>
                <div class="nt-section-bucket__items"></div>
            `;

            const nameInput = bucket.querySelector('.nt-section-bucket__name-input');
            nameInput.value = section.name;
            nameInput.addEventListener('input', () => {
                state.sections[index].name = nameInput.value;
            });

            bucket.querySelector('.nt-section-bucket__count').textContent = formatLabel(labels.matchCount, {
                count: section.indicator_ids.length,
            });

            const itemsEl = bucket.querySelector('.nt-section-bucket__items');
            section.indicators.forEach((indicator) => {
                const chip = document.createElement('span');
                chip.className = 'nt-section-chip';
                chip.title = indicator.name || '';
                chip.innerHTML = '<span class="nt-section-chip__label"></span>';
                chip.querySelector('.nt-section-chip__label').textContent = indicator.name;

                const programs = normalizePrograms(indicator.related_programs);
                if (state.groupBy === 'program' && programs.length > 1) {
                    const programNote = document.createElement('span');
                    programNote.className = 'nt-indicator-badge nt-indicator-badge--program';
                    programNote.textContent = programs.join(', ');
                    chip.appendChild(programNote);
                }

                itemsEl.appendChild(chip);
            });

            els.sectionBuckets.appendChild(bucket);
        });
    }

    function validateCurrentStep() {
        if (state.currentStep === 2) {
            if (!state.selectedIds.size) {
                setStatus(labels.selectAtLeastOne, true);
                return false;
            }
        }
        if (state.currentStep === 4) {
            const name = (els.templateName?.value || '').trim();
            if (!name) {
                setStatus(labels.templateNameRequired, true);
                return false;
            }
            const preset = getCurrentDisaggregationPreset();
            if (preset === 'custom') {
                const customOptions = getSelectedDisaggregationOptions();
                if (!customOptions.length) {
                    setStatus(labels.selectDisaggregation || 'Select at least one disaggregation option.', true);
                    return false;
                }
            }
        }
        return true;
    }

    function getSharedWithValues() {
        if (!els.templateSharedFields) return [];
        return Array.from(els.templateSharedFields.querySelectorAll('input[type="hidden"]'))
            .map((input) => input.value)
            .filter(Boolean);
    }

    function updateAccessSummary() {
        if (!els.templateAccessSummary || !els.templateOwnerField) return;
        const currentOwner = String(els.templateOwnerField.value || '').trim();
        const shared = getSharedWithValues().filter((value) => value !== currentOwner);
        const parts = [];

        if (currentOwner && Array.isArray(config.ownerChoices)) {
            const ownerChoice = config.ownerChoices.find((choice) => String(choice[0]) === currentOwner);
            if (ownerChoice) {
                parts.push(`Owner: ${ownerChoice[1]}`);
            }
        }
        if (shared.length) {
            parts.push(`${shared.length} shared`);
        }
        els.templateAccessSummary.textContent = parts.length
            ? parts.join(', ')
            : (config.labels?.manageAccess || 'Manage template access…');
    }

    async function submitWizard() {
        if (state.isSubmitting || !validateCurrentStep()) return;

        const name = (els.templateName?.value || '').trim();
        try {
            await loadFilterOptions();
        } catch (error) {
            setStatus(labels.createFailed, true);
            return;
        }
        buildSections();

        const sections = state.sections
            .map((section) => ({
                name: (section.name || '').trim() || labels.generalSection,
                indicator_ids: section.indicator_ids || [],
                area_code: section.areaCode || null,
                spef_id: section.spefId || null,
            }))
            .filter((section) => section.indicator_ids.length);

        if (!sections.length) {
            setStatus(labels.selectAtLeastOne, true);
            return;
        }

        state.isSubmitting = true;
        setStatus(labels.creating, false);
        updateStepUi();

        try {
            const payload = await window.apiFetch(config.urls.createTemplate, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Accept: 'application/json',
                    'X-CSRFToken': getCsrfToken(config),
                },
                credentials: 'same-origin',
                body: JSON.stringify({
                    name,
                    description: (els.templateDescription?.value || '').trim(),
                    add_to_self_report: Boolean(els.templateSelfReport?.checked),
                    owned_by: els.templateOwnerField?.value || config.currentUserId,
                    shared_with: getSharedWithValues(),
                    group_by: state.groupBy,
                    sections,
                    disaggregation: {
                        allowed_options: getSelectedDisaggregationOptions(),
                        age_groups_config: (els.ageGroupsConfig?.value || '').trim() || null,
                    },
                }),
            });
            if (payload.success === false) {
                throw new Error(payload.message || payload.error || labels.createFailed);
            }

            if (payload.redirect_url) {
                window.location.href = payload.redirect_url;
                return;
            }
            setStatus(payload.message || 'Template created.', false);
        } catch (error) {
            setStatus(error.message || labels.createFailed, true);
        } finally {
            state.isSubmitting = false;
            updateStepUi();
        }
    }

    function selectAllVisible() {
        state.indicators.forEach((indicator) => state.selectedIds.add(indicator.id));
        renderIndicatorList();
    }

    function clearSelection() {
        state.selectedIds.clear();
        renderIndicatorList();
    }

    async function prepareWizard() {
        try {
            await loadFilterOptions();
        } catch (error) {
            setStatus(labels.createFailed, true);
        }
    }

    if (els.filterSearch) {
        els.filterSearch.addEventListener('input', updateActiveFilterPills);
    }

    if (els.filterEmergency) {
        els.filterEmergency.addEventListener('change', updateActiveFilterPills);
    }

    if (els.clearFiltersBtn) {
        els.clearFiltersBtn.addEventListener('click', clearAllFilters);
    }

    if (els.prevBtn) {
        els.prevBtn.addEventListener('click', () => {
            void goToStep(state.currentStep - 1);
        });
    }

    if (els.nextBtn) {
        els.nextBtn.addEventListener('click', async () => {
            if (state.currentStep >= 4) return;
            if (!validateCurrentStep()) return;
            if (state.currentStep === 1) {
                state.indicators = [];
                await fetchIndicators();
            }
            await goToStep(state.currentStep + 1);
        });
    }

    if (els.submitBtn) {
        els.submitBtn.addEventListener('click', submitWizard);
    }

    if (els.selectAllBtn) {
        els.selectAllBtn.addEventListener('click', selectAllVisible);
    }

    if (els.clearSelectionBtn) {
        els.clearSelectionBtn.addEventListener('click', clearSelection);
    }

    preventFocusScrollOnCards('.nt-group-option-card');
    preventFocusScrollOnCards('.nt-disagg-preset');

    els.groupByRadios.forEach((radio) => {
        radio.addEventListener('change', async () => {
            if (!radio.checked) return;
            state.groupBy = radio.value;
            if (state.currentStep === 3) {
                try {
                    await loadFilterOptions();
                } catch (error) {
                    setStatus(labels.createFailed, true);
                    return;
                }
            }
            refreshSectionGrouping();
        });
    });

    els.disaggPresetRadios.forEach((radio) => {
        radio.addEventListener('change', onDisaggregationPresetChange);
    });

    if (els.templateAccessBtn && window.showTemplateAccessModal) {
        updateAccessSummary();
        els.templateAccessBtn.addEventListener('click', () => {
            window.showTemplateAccessModal({
                title: 'Template Access Management',
                ownerFieldName: 'owned_by',
                sharedFieldName: 'shared_with_admins',
                ownerChoices: config.ownerChoices || [],
                sharedChoices: config.sharedChoices || [],
                currentOwner: els.templateOwnerField?.value || String(config.currentUserId),
                currentShared: getSharedWithValues(),
                currentUserId: config.currentUserId,
                templateOwnerId: null,
                onSave: (data) => {
                    if (els.templateOwnerField) {
                        els.templateOwnerField.value = data.owner;
                    }
                    if (els.templateSharedFields) {
                        els.templateSharedFields.innerHTML = '';
                        (data.shared || []).forEach((value) => {
                            const input = document.createElement('input');
                            input.type = 'hidden';
                            input.name = data.sharedFieldName;
                            input.value = value;
                            els.templateSharedFields.appendChild(input);
                        });
                    }
                    updateAccessSummary();
                },
            });
        });
    }

    const methodCard = document.getElementById(config.methodCardId || 'indicator-bank-btn');
    if (methodCard) {
        methodCard.addEventListener('click', () => {
            prepareWizard();
            goToStep(1);
        });
    }

    updateStepUi();

    return {
        prepareWizard,
        goToStep,
        fetchIndicators,
        getState: () => state,
    };
}
