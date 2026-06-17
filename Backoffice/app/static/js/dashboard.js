function getSecureConfirmMessage(key, fallback = 'Are you sure?') {
    try {
        if (typeof confirmMessages === 'object' && confirmMessages !== null) {
            const message = confirmMessages[key];
            if (typeof message === 'string') {
                // Basic XSS prevention for confirm messages
                return message.replace(/[<>"']/g, function(match) {
                    const htmlEntities = {
                        '<': '&lt;',
                        '>': '&gt;',
                        '"': '&quot;',
                        "'": '&#39;'
                    };
                    return htmlEntities[match];
                });
            }
        }
        console.warn(`Confirm message not found for key: ${key}`);
        return fallback;
    } catch (error) {
        console.error('Error accessing confirm message:', error);
        return fallback;
    }
}

// SECURITY: Sanitize text content before DOM manipulation
function sanitizeTextContent(text) {
    if (typeof text !== 'string') return '';
    // Remove HTML tags and encode dangerous characters
    return text.replace(/<[^>]*>/g, '') // Strip HTML tags
               .replace(/[<>"'&]/g, function(match) {
                   const htmlEntities = {
                       '<': '&lt;',
                       '>': '&gt;',
                       '"': '&quot;',
                       "'": '&#39;',
                       '&': '&amp;'
                   };
                   return htmlEntities[match];
               });
}

const DASHBOARD_CARD_ACTIONS_OVERFLOW_BTN_WIDTH = 40;

function closeDashboardCardActionsOverflowMenus(exceptMenu) {
    document.querySelectorAll('.dashboard-card-actions-overflow-menu').forEach((menu) => {
        if (menu === exceptMenu) {
            return;
        }
        menu.classList.add('hidden');
        const toggle = menu.closest('.dashboard-card-actions-overflow')
            ?.querySelector('.dashboard-card-actions-overflow-btn');
        if (toggle) {
            toggle.setAttribute('aria-expanded', 'false');
        }
    });
}

function markDashboardCardActionsLayoutReady(container) {
    container.setAttribute('data-actions-layout-ready', '');
}

function layoutDashboardCardActions(container) {
    const bar = container.querySelector('.dashboard-card-actions-bar');
    const inline = container.querySelector('.dashboard-card-actions-inline');
    const overflowWrap = container.querySelector('.dashboard-card-actions-overflow');
    const overflowMenu = container.querySelector('.dashboard-card-actions-overflow-menu');

    if (!bar || !inline || !overflowWrap || !overflowMenu) {
        markDashboardCardActionsLayoutReady(container);
        return;
    }

    while (overflowMenu.firstElementChild) {
        inline.appendChild(overflowMenu.firstElementChild);
    }
    overflowWrap.classList.add('hidden');
    overflowMenu.classList.add('hidden');
    const overflowBtn = overflowWrap.querySelector('.dashboard-card-actions-overflow-btn');
    if (overflowBtn) {
        overflowBtn.setAttribute('aria-expanded', 'false');
    }

    if (inline.children.length) {
        const needsOverflow = () => {
            const reserved = overflowWrap.classList.contains('hidden')
                ? 0
                : DASHBOARD_CARD_ACTIONS_OVERFLOW_BTN_WIDTH;
            return inline.scrollWidth > bar.clientWidth - reserved;
        };

        while (needsOverflow() && inline.lastElementChild) {
            overflowMenu.insertBefore(inline.lastElementChild, overflowMenu.firstElementChild);
            overflowWrap.classList.remove('hidden');
        }
    }

    markDashboardCardActionsLayoutReady(container);
}

let dashboardCardActionsOverflowListenersBound = false;

function initializeDashboardCardActionsOverflow() {
    const containers = document.querySelectorAll('[data-dashboard-card-actions]');
    if (!containers.length) {
        return;
    }

    const relayoutAll = () => {
        containers.forEach((container) => layoutDashboardCardActions(container));
    };

    relayoutAll();

    if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(relayoutAll).catch(() => {});
    }

    if (typeof ResizeObserver !== 'undefined') {
        const observer = new ResizeObserver(relayoutAll);
        containers.forEach((container) => observer.observe(container));
    } else {
        window.addEventListener('resize', relayoutAll);
    }

    if (dashboardCardActionsOverflowListenersBound) {
        return;
    }
    dashboardCardActionsOverflowListenersBound = true;

    document.addEventListener('click', (event) => {
        const toggle = event.target.closest('.dashboard-card-actions-overflow-btn');
        if (toggle) {
            event.stopPropagation();
            const wrap = toggle.closest('.dashboard-card-actions-overflow');
            const menu = wrap?.querySelector('.dashboard-card-actions-overflow-menu');
            if (!menu) {
                return;
            }
            const isOpen = !menu.classList.contains('hidden');
            closeDashboardCardActionsOverflowMenus(isOpen ? null : menu);
            if (isOpen) {
                menu.classList.add('hidden');
                toggle.setAttribute('aria-expanded', 'false');
            } else {
                menu.classList.remove('hidden');
                toggle.setAttribute('aria-expanded', 'true');
            }
            return;
        }

        if (!event.target.closest('.dashboard-card-actions-overflow')) {
            closeDashboardCardActionsOverflowMenus();
        }
    });
}

function bootDashboardCardActionsOverflow() {
    initializeDashboardCardActionsOverflow();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootDashboardCardActionsOverflow);
} else {
    bootDashboardCardActionsOverflow();
}

// Set background colors for profile avatars from data attributes
document.addEventListener('DOMContentLoaded', function() {
    const avatars = document.querySelectorAll('[data-bg-color]');
    avatars.forEach(avatar => {
        const bgColor = avatar.dataset.bgColor;
        if (bgColor) {
            avatar.style.backgroundColor = bgColor;
        }
    });
});

// Function to toggle additional changes visibility
function toggleAdditionalChanges(button, activityIndex) {
    const container = document.querySelector(`.additional-changes-${activityIndex}`);
    const showMoreText = button.querySelector('.show-more-text');
    const showLessText = button.querySelector('.show-less-text');
    const isExpanded = button.getAttribute('aria-expanded') === 'true';

    // Toggle visibility
    container.classList.toggle('hidden');
    showMoreText.classList.toggle('hidden');
    showLessText.classList.toggle('hidden');

    // Update aria-expanded state
    button.setAttribute('aria-expanded', !isExpanded);

    // Smooth scroll to show newly revealed content if expanding
    if (!isExpanded) {
        container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

// Function to render the Completion Rate Line Chart
function renderCompletionRateChart() {
    const ctx = document.getElementById('completionRateChart');

    if (!ctx) {
        console.error("Completion Rate Chart canvas element not found!");
        return;
    }

    // Fake data for demonstration
    const data = {
        labels: ['Period 1', 'Period 2', 'Period 3', 'Period 4', 'Period 5'], // Example periods
        datasets: [{
            label: 'Completion Rate (%)',
            data: [65, 72, 78, 85, 90], // Example completion rates
            borderColor: 'rgb(59, 130, 246)', // Blue color
            tension: 0.1,
            fill: false
        }]
    };

    new Chart(ctx, {
        type: 'line',
        data: data,
        options: {
            responsive: true,
            maintainAspectRatio: false, // Allow height to be controlled by container
            plugins: {
                title: {
                    display: true,
                    text: getSecureConfirmMessage('completionRateOverTime', 'Completion Rate Over Time')
                },
                legend: {
                    display: false // Hide legend if only one dataset
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    title: {
                        display: true,
                        text: 'Completion (%)'
                    }
                }
            }
        }
    });
}

// Function to render the Data Quality Bar Chart
function renderDataQualityChart() {
    const ctx = document.getElementById('dataQualityChart');

     if (!ctx) {
        console.error("Data Quality Chart canvas element not found!");
        return;
    }

    // Fake data for demonstration
    const data = {
        labels: ['Period 1', 'Period 2', 'Period 3', 'Period 4', 'Period 5'], // Example periods
        datasets: [{
            label: getSecureConfirmMessage('dataQualityIndex', 'Data Quality Index'),
            data: [7.5, 8.0, 8.5, 8.8, 9.1], // Example quality scores (out of 10)
            backgroundColor: 'rgb(168, 85, 247)', // Purple color
            borderColor: 'rgb(147, 51, 234)', // Darker purple
            borderWidth: 1
        }]
    };

    new Chart(ctx, {
        type: 'bar',
        data: data,
         options: {
            responsive: true,
            maintainAspectRatio: false, // Allow height to be controlled by container
            plugins: {
                title: {
                    display: true,
                    text: getSecureConfirmMessage('dataQualityIndexTrend', 'Data Quality Index Trend')
                },
                 legend: {
                    display: false // Hide legend if only one dataset
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 10, // Assuming index is out of 10
                     title: {
                        display: true,
                        text: getSecureConfirmMessage('qualityIndex', 'Quality Index')
                    }
                }
            }
        }
    });
}

function scoreColorClass(pct) {
    if (pct >= 80) return 'text-green-700';
    if (pct >= 50) return 'text-amber-600';
    return 'text-red-600';
}

function scoreHexColor(pct) {
    if (pct >= 80) return '#15803d';
    if (pct >= 50) return '#d97706';
    return '#dc2626';
}

function scoreRingColor(pct) {
    if (pct >= 80) return '#16a34a';
    if (pct >= 50) return '#d97706';
    return '#dc2626';
}

function formatDataQualityOverallPct(pct) {
    return Math.round(Math.max(0, Math.min(100, Number(pct) || 0)));
}

function renderDataQualityScoreRing(pct) {
    const displayPct = formatDataQualityOverallPct(pct);
    const color = scoreRingColor(displayPct);
    const radius = 40;
    const stroke = 7;
    const normalizedRadius = radius - stroke / 2;
    const circumference = normalizedRadius * 2 * Math.PI;
    const offset = circumference - (displayPct / 100) * circumference;
    const label = `${getSecureConfirmMessage('overallScore', 'Overall score')}: ${displayPct}%`;

    return `
        <svg class="shrink-0" width="96" height="96" viewBox="0 0 96 96" role="img" aria-label="${label}">
            <circle cx="48" cy="48" r="${normalizedRadius}" fill="none" stroke="#e5e7eb" stroke-width="${stroke}"></circle>
            <circle cx="48" cy="48" r="${normalizedRadius}" fill="none" stroke="${color}" stroke-width="${stroke}"
                    stroke-dasharray="${circumference.toFixed(2)}"
                    stroke-dashoffset="${offset.toFixed(2)}"
                    stroke-linecap="round"
                    transform="rotate(-90 48 48)"></circle>
            <text x="48" y="48" text-anchor="middle" dominant-baseline="middle"
                  font-size="22" font-weight="700" fill="${color}">${displayPct}%</text>
        </svg>
    `;
}

const DATA_QUALITY_DETAILS_STORAGE_KEY = 'dataQualityPillarDetailsExpanded';
const DATA_QUALITY_TREND_MODE_STORAGE_KEY = 'dataQualityTrendMode';
const DATA_QUALITY_COMPONENT_STORAGE_PREFIX = 'dataQualityComponentExpanded:';

function isDataQualityPillarDetailsExpanded() {
    try {
        return sessionStorage.getItem(DATA_QUALITY_DETAILS_STORAGE_KEY) === 'true';
    } catch (e) {
        return false;
    }
}

function setDataQualityPillarDetailsExpanded(expanded) {
    try {
        sessionStorage.setItem(DATA_QUALITY_DETAILS_STORAGE_KEY, expanded ? 'true' : 'false');
    } catch (e) {
        /* sessionStorage unavailable */
    }
}

function updateDataQualityDetailsToggleButton(expanded) {
    const btn = document.getElementById('data-quality-pillar-details-toggle');
    if (!btn) return;
    btn.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    btn.classList.toggle('is-expanded', expanded);
    const actionLabel = expanded
        ? getSecureConfirmMessage('pillarBreakdownCollapse', 'Hide score breakdown')
        : getSecureConfirmMessage('pillarBreakdownExpand', 'Show score breakdown');
    btn.setAttribute('aria-label', actionLabel);
}

function getDataQualityTrendMode() {
    try {
        const mode = sessionStorage.getItem(DATA_QUALITY_TREND_MODE_STORAGE_KEY);
        return mode === 'pillars' ? 'pillars' : 'overall';
    } catch (e) {
        return 'overall';
    }
}

function setDataQualityTrendMode(mode) {
    try {
        sessionStorage.setItem(
            DATA_QUALITY_TREND_MODE_STORAGE_KEY,
            mode === 'pillars' ? 'pillars' : 'overall'
        );
    } catch (e) {
        /* sessionStorage unavailable */
    }
}

function setDataQualityTrendToggleUi(mode) {
    const toggle = document.getElementById('data-quality-trend-toggle');
    if (!toggle) return;
    toggle.querySelectorAll('[data-trend-mode]').forEach((btn) => {
        const btnMode = btn.getAttribute('data-trend-mode');
        const active = btnMode === mode;
        btn.classList.toggle('is-active', active);
        btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
}

function applyDataQualityTrendMode(mode) {
    if (!dataQualityTrendData.length) return;
    const resolvedMode = mode || getDataQualityTrendMode();
    renderDataQualityTrendChart(dataQualityTrendData, resolvedMode);
    setDataQualityTrendToggleUi(resolvedMode);
}

function applyDataQualityPillarDetailsVisibility(expanded) {
    document.querySelectorAll('.data-quality-sub-pillars').forEach((el) => {
        el.classList.toggle('is-collapsed', !expanded);
    });
    updateDataQualityDetailsToggleButton(expanded);
}

function dataQualityComponentStorageKey(pillarKey, subPillarKey) {
    return `${DATA_QUALITY_COMPONENT_STORAGE_PREFIX}${pillarKey}:${subPillarKey}`;
}

function isDataQualityComponentExpanded(pillarKey, subPillarKey) {
    try {
        return sessionStorage.getItem(dataQualityComponentStorageKey(pillarKey, subPillarKey)) === 'true';
    } catch (e) {
        return false;
    }
}

function setDataQualityComponentExpanded(pillarKey, subPillarKey, expanded) {
    try {
        sessionStorage.setItem(
            dataQualityComponentStorageKey(pillarKey, subPillarKey),
            expanded ? 'true' : 'false'
        );
    } catch (e) {
        /* sessionStorage unavailable */
    }
}

function subPillarHasComponents(pillarKey, subPillarKey, pillarComponentDetails) {
    const meta = getDataQualityComponentMeta()[pillarKey];
    if (!meta || !meta[subPillarKey]) {
        return false;
    }
    const detail = pillarComponentDetails && pillarComponentDetails[subPillarKey];
    return Boolean(detail && typeof detail === 'object' && Object.keys(detail).length);
}

function dataQualityComponentListId(pillarKey, subPillarKey) {
    return `dq-components-${pillarKey}-${subPillarKey}`;
}

function updateDataQualitySubPillarToggleLabel(btn, expanded) {
    const label = expanded
        ? getSecureConfirmMessage('subPillarComponentsCollapse', 'Hide score components')
        : getSecureConfirmMessage('subPillarComponentsExpand', 'Show score components');
    btn.setAttribute('aria-label', label);
}

function syncDataQualityPillarDetailsToggle() {
    const toggleWrap = document.getElementById('data-quality-details-toggle-wrap');
    const hasSubPillars = document.querySelector('.data-quality-sub-pillars');
    if (!hasSubPillars) {
        if (toggleWrap) toggleWrap.classList.add('is-unavailable');
        return;
    }
    if (toggleWrap) toggleWrap.classList.remove('is-unavailable');
    applyDataQualityPillarDetailsVisibility(isDataQualityPillarDetailsExpanded());
}

function syncDataQualityTrendToggle() {
    applyDataQualityTrendMode(getDataQualityTrendMode());
}

function bindDataQualityPillarDetailsToggle() {
    const btn = document.getElementById('data-quality-pillar-details-toggle');
    if (!btn || btn.dataset.bound === 'true') return;
    btn.dataset.bound = 'true';
    btn.addEventListener('click', () => {
        const nextExpanded = btn.getAttribute('aria-expanded') !== 'true';
        setDataQualityPillarDetailsExpanded(nextExpanded);
        applyDataQualityPillarDetailsVisibility(nextExpanded);
    });
}

function bindDataQualitySubPillarComponentToggles() {
    document.querySelectorAll('.data-quality-sub-pillar__toggle').forEach((btn) => {
        if (btn.dataset.bound === 'true') {
            return;
        }
        btn.dataset.bound = 'true';

        const pillarKey = btn.dataset.pillarKey;
        const subPillarKey = btn.dataset.subPillarKey;
        const listId = btn.getAttribute('aria-controls');
        const list = listId ? document.getElementById(listId) : null;
        const expanded = isDataQualityComponentExpanded(pillarKey, subPillarKey);

        btn.setAttribute('aria-expanded', expanded ? 'true' : 'false');
        btn.classList.toggle('is-expanded', expanded);
        updateDataQualitySubPillarToggleLabel(btn, expanded);
        if (list) {
            list.classList.toggle('is-collapsed', !expanded);
        }

        btn.addEventListener('click', () => {
            const nextExpanded = btn.getAttribute('aria-expanded') !== 'true';
            setDataQualityComponentExpanded(pillarKey, subPillarKey, nextExpanded);
            btn.setAttribute('aria-expanded', nextExpanded ? 'true' : 'false');
            btn.classList.toggle('is-expanded', nextExpanded);
            updateDataQualitySubPillarToggleLabel(btn, nextExpanded);
            if (list) {
                list.classList.toggle('is-collapsed', !nextExpanded);
            }
        });
    });
}

function getDataQualitySubPillarMeta() {
    return {
        documents: [
            { key: 'annual_report', label: getSecureConfirmMessage('subAnnualReport', 'Annual Report'), format: 'binary' },
            { key: 'audited_financial_statement', label: getSecureConfirmMessage('subAuditedFinancial', 'Audited Financial Statement'), format: 'binary' }
        ],
        reporting: [
            { key: 'governance_structure', label: getSecureConfirmMessage('subGovernance', 'Governance & structure'), format: 'fraction' },
            { key: 'finance_partnership', label: getSecureConfirmMessage('subFinance', 'Finance & partnership'), format: 'fraction' },
            { key: 'people_reached', label: getSecureConfirmMessage('subPeopleReached', 'People reached'), format: 'fraction' }
        ],
        disaggregation: [
            { key: 'sex', label: getSecureConfirmMessage('subSex', 'Sex disaggregation'), format: 'fraction' },
            { key: 'age', label: getSecureConfirmMessage('subAge', 'Age disaggregation'), format: 'fraction' },
            { key: 'disability', label: getSecureConfirmMessage('subDisability', 'Disability'), format: 'fraction' }
        ]
    };
}

function getDataQualityComponentMeta() {
    return {
        reporting: {
            finance_partnership: [
                { key: 'reported_income', label: getSecureConfirmMessage('subReportedIncome', 'Reported income'), weight: 35, format: 'binary' },
                { key: 'reported_expenditure', label: getSecureConfirmMessage('subReportedExpenditure', 'Reported expenditure'), weight: 35, format: 'binary' },
                { key: 'income_sources', label: getSecureConfirmMessage('subIncomeSources', 'Income sources'), weight: 30, format: 'fraction' }
            ]
        },
        disaggregation: {
            disability: [
                { key: 'disaggregated_disability', label: getSecureConfirmMessage('subDisaggregatedDisability', 'Disaggregated disability'), weight: 80, format: 'fraction' },
                { key: 'washington_group_questions', label: getSecureConfirmMessage('subWashingtonGroup', 'Washington Group questions'), weight: 20, format: 'fraction' }
            ]
        }
    };
}

function formatSubPillarPct(value, format) {
    if (value == null || value === '') {
        return null;
    }
    const n = Number(value);
    if (Number.isNaN(n)) {
        return null;
    }
    if (format === 'binary') {
        return n >= 1 ? 100 : 0;
    }
    return Math.round(n * 1000) / 10;
}

function renderDataQualityComponentRows(pillarKey, subPillarKey, componentDetail) {
    const spec = getDataQualityComponentMeta()[pillarKey];
    const items = spec && spec[subPillarKey];
    if (!items || !componentDetail || typeof componentDetail !== 'object') {
        return '';
    }

    const listId = dataQualityComponentListId(pillarKey, subPillarKey);
    const expanded = isDataQualityComponentExpanded(pillarKey, subPillarKey);
    const collapsedClass = expanded ? '' : ' is-collapsed';
    const weightLabel = getSecureConfirmMessage('weightLabel', 'Weight');
    const rows = items.map((item) => {
        if (componentDetail[item.key] == null) {
            return null;
        }
        const label = sanitizeTextContent(item.label);
        const weightHtml = item.weight != null
            ? `<span class="data-quality-component-row__weight">${weightLabel}: ${item.weight}%</span>`
            : '';

        if (item.format === 'binary') {
            const isPresent = Number(componentDetail[item.key]) >= 1;
            const statusLabel = isPresent
                ? getSecureConfirmMessage('subPillarPresent', 'Present')
                : getSecureConfirmMessage('subPillarMissing', 'Missing');
            return `
                <li class="data-quality-component-row">
                    <div class="data-quality-component-row__label-wrap">
                        <span class="data-quality-component-row__label" title="${label}">${label}</span>
                        ${weightHtml}
                    </div>
                    <span class="data-quality-component-row__status ${isPresent ? 'is-present' : 'is-missing'}"
                          aria-label="${label}: ${statusLabel}">
                        <i class="fas ${isPresent ? 'fa-check-circle' : 'fa-times-circle'}" aria-hidden="true"></i>
                    </span>
                </li>
            `;
        }

        const pct = formatSubPillarPct(componentDetail[item.key], item.format);
        if (pct == null) {
            return null;
        }
        const barWidth = Math.max(0, Math.min(100, pct));
        const scoreColor = scoreHexColor(pct);
        const barColor = scoreHexColor(pct);
        return `
            <li class="data-quality-component-row">
                <div class="data-quality-component-row__label-wrap">
                    <span class="data-quality-component-row__label" title="${label}">${label}</span>
                    ${weightHtml}
                </div>
                <span class="data-quality-component-row__score" style="color: ${scoreColor}">${pct}%</span>
                <div class="data-quality-component-row__bar-track" role="progressbar"
                     aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"
                     aria-label="${label}">
                    <div class="data-quality-component-row__bar-fill"
                         style="width: ${barWidth}%; background-color: ${barColor};"></div>
                </div>
            </li>
        `;
    }).filter(Boolean);

    if (!rows.length) {
        return '';
    }

    return `<ul id="${listId}" class="data-quality-component-list${collapsedClass}" aria-label="${getSecureConfirmMessage('componentBreakdownLabel', 'Score components')}">${rows.join('')}</ul>`;
}

function renderDataQualitySubPillarLabel(item, pillarKey, hasComponents) {
    if (!hasComponents) {
        return `<span class="data-quality-sub-pillar__label">${item.label}</span>`;
    }

    const listId = dataQualityComponentListId(pillarKey, item.key);
    const expanded = isDataQualityComponentExpanded(pillarKey, item.key);
    const actionLabel = expanded
        ? getSecureConfirmMessage('subPillarComponentsCollapse', 'Hide score components')
        : getSecureConfirmMessage('subPillarComponentsExpand', 'Show score components');

    return `
        <button type="button"
                class="data-quality-sub-pillar__toggle${expanded ? ' is-expanded' : ''}"
                data-pillar-key="${pillarKey}"
                data-sub-pillar-key="${item.key}"
                aria-expanded="${expanded ? 'true' : 'false'}"
                aria-controls="${listId}"
                aria-label="${actionLabel}">
            <span class="data-quality-sub-pillar__label">${item.label}</span>
            <i class="fas fa-chevron-right data-quality-sub-pillar__chevron" aria-hidden="true"></i>
        </button>
    `;
}

function renderDataQualitySubPillars(pillarKey, subDetail, pillarComponentDetails) {
    const spec = getDataQualitySubPillarMeta()[pillarKey];
    if (!spec || !subDetail || typeof subDetail !== 'object') {
        return '';
    }

    const rows = spec
        .map((item) => {
            if (subDetail[item.key] == null) {
                return null;
            }
            const hasComponents = subPillarHasComponents(
                pillarKey,
                item.key,
                pillarComponentDetails
            );
            const componentRowsHtml = hasComponents
                ? renderDataQualityComponentRows(
                    pillarKey,
                    item.key,
                    pillarComponentDetails[item.key]
                )
                : '';
            const labelHtml = renderDataQualitySubPillarLabel(item, pillarKey, hasComponents);
            const expandableClass = hasComponents ? ' data-quality-sub-pillar--expandable' : '';

            if (item.format === 'binary') {
                const isPresent = Number(subDetail[item.key]) >= 1;
                const statusLabel = isPresent
                    ? getSecureConfirmMessage('subPillarPresent', 'Present')
                    : getSecureConfirmMessage('subPillarMissing', 'Missing');
                return `
                    <li class="data-quality-sub-pillar data-quality-sub-pillar--binary${expandableClass}">
                        ${labelHtml}
                        <span class="data-quality-sub-pillar__status ${isPresent ? 'is-present' : 'is-missing'}"
                              aria-label="${item.label}: ${statusLabel}">
                            <i class="fas ${isPresent ? 'fa-check-circle' : 'fa-times-circle'}" aria-hidden="true"></i>
                        </span>
                        ${componentRowsHtml}
                    </li>
                `;
            }

            const pct = formatSubPillarPct(subDetail[item.key], item.format);
            if (pct == null) {
                return null;
            }
            const barWidth = Math.max(0, Math.min(100, pct));
            const scoreColor = scoreHexColor(pct);
            const barColor = scoreHexColor(pct);
            return `
                <li class="data-quality-sub-pillar${expandableClass}">
                    ${labelHtml}
                    <span class="data-quality-sub-pillar__score" style="color: ${scoreColor}">${pct}%</span>
                    <div class="data-quality-sub-pillar__bar-track" role="progressbar"
                         aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"
                         aria-label="${item.label}">
                        <div class="data-quality-sub-pillar__bar-fill"
                             style="width: ${barWidth}%; background-color: ${barColor};"></div>
                    </div>
                    ${componentRowsHtml}
                </li>
            `;
        })
        .filter(Boolean);

    if (!rows.length) {
        return '';
    }

    const expanded = isDataQualityPillarDetailsExpanded();
    const collapsedClass = expanded ? '' : ' is-collapsed';

    return `<ul class="data-quality-sub-pillars${collapsedClass}" aria-label="${getSecureConfirmMessage('subPillarsLabel', 'Components')}">
        ${rows.join('')}
    </ul>`;
}

function renderDataQualityPillarCard(key, meta, pillars, weightLabel, subDetail, pillarComponentDetails) {
    const pct = pillars[key];
    const hasScore = pct != null;
    const score = hasScore ? Number(pct) : null;
    const barWidth = hasScore ? Math.max(0, Math.min(100, score)) : 0;
    const scoreColor = hasScore ? scoreHexColor(score) : '#9ca3af';
    const barColor = hasScore ? scoreHexColor(score) : '#d1d5db';
    const iconColor = meta.color || '#6d28d9';
    const iconBg = meta.bg || '#f5f3ff';
    const subPillarsHtml = renderDataQualitySubPillars(key, subDetail, pillarComponentDetails);

    return `
        <div class="data-quality-pillar-card">
            <div class="data-quality-pillar-card__header">
                <div class="data-quality-pillar-card__title-row">
                    <span class="data-quality-pillar-card__icon" style="background-color: ${iconBg}; color: ${iconColor};">
                        <i class="fas ${meta.icon}" aria-hidden="true"></i>
                    </span>
                    <div>
                        <p class="data-quality-pillar-card__label">${meta.label}</p>
                        <p class="data-quality-pillar-card__weight">${weightLabel}: ${meta.weight}%</p>
                    </div>
                </div>
                <p class="data-quality-pillar-card__score" style="color: ${scoreColor}">
                    ${hasScore ? `${score}%` : '—'}
                </p>
            </div>
            <div class="data-quality-pillar-card__bar-track" role="progressbar"
                 aria-valuemin="0" aria-valuemax="100" aria-valuenow="${hasScore ? barWidth : 0}"
                 aria-label="${meta.label}">
                <div class="data-quality-pillar-card__bar-fill"
                     style="width: ${barWidth}%; background-color: ${barColor};"></div>
            </div>
            <p class="data-quality-pillar-card__desc">${meta.description}</p>
            ${subPillarsHtml}
        </div>
    `;
}

function getDataQualityPillarColors() {
    return {
        documents: { color: '#6366f1', bg: '#eef2ff' },
        reporting: { color: '#0891b2', bg: '#ecfeff' },
        disaggregation: { color: '#059669', bg: '#ecfdf5' },
        timeliness: { color: '#d97706', bg: '#fffbeb' },
        validation_questions: { color: '#db2777', bg: '#fdf2f8' }
    };
}

function getDataQualityPillarMeta() {
    const colors = getDataQualityPillarColors();
    return {
        documents: {
            label: getSecureConfirmMessage('pillarDocuments', 'Documents'),
            weight: 20,
            icon: 'fa-file-alt',
            color: colors.documents.color,
            bg: colors.documents.bg,
            description: getSecureConfirmMessage('pillarDocumentsDesc', 'Annual Report and Audited Financial Statement uploads')
        },
        reporting: {
            label: getSecureConfirmMessage('pillarReporting', 'Reporting'),
            weight: 30,
            icon: 'fa-chart-bar',
            color: colors.reporting.color,
            bg: colors.reporting.bg,
            description: getSecureConfirmMessage('pillarReportingDesc', 'Governance, finance, and people-reached indicators')
        },
        disaggregation: {
            label: getSecureConfirmMessage('pillarDisaggregation', 'Disaggregation'),
            weight: 30,
            icon: 'fa-users',
            color: colors.disaggregation.color,
            bg: colors.disaggregation.bg,
            description: getSecureConfirmMessage('pillarDisaggregationDesc', 'Sex, age, and disability breakdowns where applicable')
        },
        timeliness: {
            label: getSecureConfirmMessage('pillarTimeliness', 'Timeliness'),
            weight: 10,
            icon: 'fa-clock',
            color: colors.timeliness.color,
            bg: colors.timeliness.bg,
            description: getSecureConfirmMessage('pillarTimelinessDesc', 'Whether sections were submitted before the cutoff')
        },
        validation_questions: {
            label: getSecureConfirmMessage('pillarValidationQuestions', 'Validation questions'),
            weight: 10,
            icon: 'fa-check-circle',
            color: colors.validation_questions.color,
            bg: colors.validation_questions.bg,
            description: getSecureConfirmMessage('pillarValidationDesc', 'Responses to automatic data checks')
        }
    };
}

function buildDataQualityTrendDatasets(trend, mode, pillarMeta) {
    if (mode === 'pillars') {
        return Object.keys(pillarMeta).map((key) => {
            const lineColor = pillarMeta[key].color || '#6d28d9';
            return {
                label: pillarMeta[key].label,
                data: trend.map((entry) => {
                    const pillars = entry.pillars || {};
                    return pillars[key] != null ? Number(pillars[key]) : null;
                }),
                borderColor: lineColor,
                backgroundColor: lineColor,
                pointBackgroundColor: lineColor,
                pointRadius: 3,
                pointHoverRadius: 4,
                tension: 0.25,
                fill: false,
                clip: false
            };
        });
    }

    return [{
        label: getSecureConfirmMessage('dataQualityIndex', 'Data Quality Index'),
        data: trend.map((entry) => formatDataQualityOverallPct(entry.overall_pct)),
        borderColor: 'rgb(124, 58, 237)',
        backgroundColor: 'rgba(124, 58, 237, 0.08)',
        pointBackgroundColor: 'rgb(124, 58, 237)',
        pointRadius: 4,
        pointHoverRadius: 5,
        tension: 0.25,
        fill: true,
        clip: false
    }];
}

let dataQualityTrendChartInstance = null;
let dataQualityTrendData = [];

function destroyDataQualityTrendChart() {
    if (dataQualityTrendChartInstance) {
        dataQualityTrendChartInstance.destroy();
        dataQualityTrendChartInstance = null;
    }
}

function renderDataQualityTrendChart(trend, mode) {
    const ctx = document.getElementById('dataQualityTrendChart');
    if (!ctx || typeof Chart === 'undefined' || !trend.length) {
        return;
    }

    destroyDataQualityTrendChart();
    const pillarMeta = getDataQualityPillarMeta();
    const datasets = buildDataQualityTrendDatasets(trend, mode, pillarMeta);
    const showLegend = mode === 'pillars';
    const chartWrap = ctx.closest('.data-quality-trend-chart-wrap');
    if (chartWrap) {
        chartWrap.classList.toggle('data-quality-trend-chart-wrap--pillars', showLegend);
    }

    dataQualityTrendChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: trend.map((entry) => entry.period),
            datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: {
                padding: { top: 12, right: 8, left: 4, bottom: 0 }
            },
            plugins: {
                legend: {
                    display: showLegend,
                    position: 'bottom',
                    labels: {
                        boxWidth: 10,
                        boxHeight: 10,
                        padding: 12,
                        font: { size: 11 }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    min: 0,
                    max: 100,
                    grace: '4%',
                    ticks: { callback: (value) => `${value}%` }
                }
            }
        }
    });
}

function bindDataQualityTrendToggle() {
    const panelContent = document.getElementById('data-quality-panel-content');
    if (!panelContent || panelContent.dataset.trendToggleBound === 'true') return;
    panelContent.dataset.trendToggleBound = 'true';

    panelContent.addEventListener('click', (event) => {
        const button = event.target.closest('[data-trend-mode]');
        const toggle = document.getElementById('data-quality-trend-toggle');
        if (!button || !toggle || !toggle.contains(button) || button.classList.contains('is-active')) {
            return;
        }
        const mode = button.getAttribute('data-trend-mode');
        if (!mode) return;
        setDataQualityTrendMode(mode);
        applyDataQualityTrendMode(mode);
    });
}

function renderDataQualityTrendSection(trend) {
    if (!trend.length) {
        return `<div class="rounded-lg border border-dashed border-gray-200 bg-gray-50/40 px-4 py-6 text-center text-sm text-gray-500">
            ${getSecureConfirmMessage('noTrendData', 'Not enough history to show a trend yet.')}
        </div>`;
    }

    const trendMode = getDataQualityTrendMode();
    const overallActive = trendMode === 'overall';
    const pillarsActive = trendMode === 'pillars';

    return `<div class="rounded-lg border border-gray-200 bg-gray-50/60 p-4" id="data-quality-trend-section">
        <div class="data-quality-trend-header">
            <h4 class="data-quality-trend-header__title">${getSecureConfirmMessage('scoreTrend', 'Score trend')}</h4>
            <div class="data-quality-trend-toggle" id="data-quality-trend-toggle" role="group" aria-label="${getSecureConfirmMessage('scoreTrend', 'Score trend')}">
                <button type="button"
                        class="data-quality-trend-toggle__btn${overallActive ? ' is-active' : ''}"
                        data-trend-mode="overall"
                        aria-pressed="${overallActive ? 'true' : 'false'}">
                    ${getSecureConfirmMessage('trendOverall', 'Overall')}
                </button>
                <button type="button"
                        class="data-quality-trend-toggle__btn${pillarsActive ? ' is-active' : ''}"
                        data-trend-mode="pillars"
                        aria-pressed="${pillarsActive ? 'true' : 'false'}">
                    ${getSecureConfirmMessage('trendByPillar', 'By pillar')}
                </button>
            </div>
        </div>
        <div class="data-quality-trend-chart-wrap"><canvas id="dataQualityTrendChart" aria-label="${getSecureConfirmMessage('dataQualityIndexTrend', 'Data Quality Index Trend')}"></canvas></div>
    </div>`;
}

function renderDataQualityLoadingSkeleton() {
    return `
        <div class="space-y-4" id="data-quality-loading">
            <div class="data-quality-pillars-grid">
                ${Array.from({ length: 5 }).map(() => `
                    <div class="data-quality-skeleton data-quality-pillar-card" style="min-height: 7.5rem;"></div>
                `).join('')}
            </div>
        </div>
    `;
}

function renderDataQualityPanel(data) {
    const panelContent = document.getElementById('data-quality-panel-content');
    const ringSlot = document.getElementById('data-quality-ring-slot');
    const validationSlot = document.getElementById('data-quality-validation-slot');
    const periodSelect = document.getElementById('data-quality-period-select');
    if (!panelContent || !data) return;

    const pillars = data.pillars || {};
    const subPillars = data.sub_pillars || {};
    const componentDetails = data.component_details || {};
    const val = data.validation_summary || {};
    const pillarMeta = getDataQualityPillarMeta();
    const overallPct = Number(data.overall_pct) || 0;
    const weightLabel = getSecureConfirmMessage('weightLabel', 'Weight');

    if (ringSlot) {
        ringSlot.innerHTML = renderDataQualityScoreRing(overallPct);
    }

    if (periodSelect && data.period_name) {
        periodSelect.value = data.period_name;
    }

    if (validationSlot) {
        validationSlot.innerHTML = val.asked
            ? `<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
                (val.answered || 0) >= val.asked ? 'bg-green-100 text-green-800' : 'bg-amber-100 text-amber-800'
            }">
                <i class="fas fa-clipboard-check" aria-hidden="true"></i>
                ${val.answered || 0}/${val.asked} ${getSecureConfirmMessage('validationAnswered', 'validation questions answered')}
            </span>`
            : '';
    }

    const warningsHtml = (data.warnings || []).length
        ? `<div class="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
            ${data.warnings.map((w) => `<p>${sanitizeTextContent(w)}</p>`).join('')}
        </div>`
        : '';

    const pillarCards = Object.keys(pillarMeta).map((key) =>
        renderDataQualityPillarCard(key, pillarMeta[key], pillars, weightLabel, subPillars[key], componentDetails[key])
    ).join('');

    const trend = data.trend || [];
    dataQualityTrendData = trend;
    const trendSection = renderDataQualityTrendSection(trend);

    destroyDataQualityTrendChart();

    panelContent.innerHTML = `
        <div class="mb-5">
            <div class="data-quality-pillars-toolbar" id="data-quality-pillars-toolbar">
                <h4 class="data-quality-pillars-toolbar__title">${getSecureConfirmMessage('scorePillars', 'Score pillars')}</h4>
            </div>
            <div class="data-quality-pillars-grid">
                ${pillarCards}
            </div>
        </div>

        ${trendSection}
        ${warningsHtml}
    `;

    syncDataQualityPillarDetailsToggle();
    syncDataQualityTrendToggle();
    bindDataQualitySubPillarComponentToggles();
}

async function loadDataQualityScore(templateId, period, entityType, entityId) {
    const panelContent = document.getElementById('data-quality-panel-content');
    const ringSlot = document.getElementById('data-quality-ring-slot');
    const toggleWrap = document.getElementById('data-quality-details-toggle-wrap');
    if (toggleWrap) toggleWrap.classList.add('is-unavailable');
    dataQualityTrendData = [];
    if (panelContent) {
        panelContent.innerHTML = renderDataQualityLoadingSkeleton();
    }
    destroyDataQualityTrendChart();
    if (ringSlot) {
        ringSlot.innerHTML = '<div class="data-quality-skeleton w-24 h-24 rounded-full bg-violet-100"></div>';
    }

    if (!templateId || !period || !entityType || entityId == null || entityId === '') {
        if (panelContent) {
            panelContent.innerHTML = '<p class="text-gray-500 text-sm py-6 text-center">No reporting period available for this template.</p>';
        }
        return;
    }

    const params = new URLSearchParams({
        entity_type: entityType,
        entity_id: entityId,
        template_id: templateId,
        period: period
    });

    try {
        const resp = await fetch(`/api/v1/dashboard/data-quality?${params.toString()}`, {
            headers: { 'Accept': 'application/json' },
            credentials: 'same-origin'
        });
        const contentType = resp.headers.get('content-type') || '';
        let data = null;
        if (contentType.includes('application/json')) {
            data = await resp.json();
        } else {
            const text = await resp.text();
            console.error('Data quality API returned non-JSON response', resp.status, text.slice(0, 200));
            if (panelContent) {
                panelContent.innerHTML = '<p class="text-red-600 text-sm">Failed to load data quality score. Please refresh or contact support.</p>';
            }
            return;
        }
        if (!resp.ok) {
            if (panelContent) panelContent.innerHTML = `<p class="text-red-600 text-sm">${sanitizeTextContent(data.error || 'Failed to load score')}</p>`;
            return;
        }
        renderDataQualityPanel(data);
    } catch (err) {
        console.error('Data quality fetch failed', err);
        if (panelContent) {
            panelContent.innerHTML = '<p class="text-red-600 text-sm">Failed to load data quality score. Please refresh or contact support.</p>';
        }
    }
}

function initDataQualityDashboard() {
    const root = document.getElementById('data-quality-dashboard');
    if (!root) return;

    bindDataQualityPillarDetailsToggle();
    bindDataQualityTrendToggle();

    const entityType = root.dataset.entityType;
    const entityId = root.dataset.entityId;
    const periodSelect = document.getElementById('data-quality-period-select');
    const periodWrap = document.getElementById('data-quality-period-wrap');
    let templates = [];
    try {
        templates = JSON.parse(root.dataset.templates || '[]');
    } catch (e) {
        templates = [];
    }

    const templatesById = {};
    templates.forEach((t) => {
        if (t && t.template_id != null) {
            templatesById[String(t.template_id)] = t;
        }
    });

    function populatePeriodSelect(templateId, preferredPeriod) {
        if (!periodSelect) return;
        const tmpl = templatesById[String(templateId)];
        const periods = (tmpl && Array.isArray(tmpl.periods)) ? tmpl.periods : [];
        const previous = preferredPeriod || periodSelect.value;
        periodSelect.innerHTML = '';
        periods.forEach((period) => {
            const option = document.createElement('option');
            option.value = period;
            option.textContent = period;
            periodSelect.appendChild(option);
        });
        if (previous && periods.includes(previous)) {
            periodSelect.value = previous;
        }
        periodSelect.disabled = periods.length <= 1;
        if (periodWrap) {
            periodWrap.classList.toggle('is-interactive', periods.length > 1);
        }
    }

    function loadActiveScore() {
        const activeTab = root.querySelector('.data-quality-tab[aria-selected="true"]');
        if (!activeTab) return;
        const templateId = activeTab.dataset.templateId;
        const period = periodSelect ? periodSelect.value : '';
        if (templateId && period) {
            loadDataQualityScore(templateId, period, entityType, entityId);
        }
    }

    const tabs = root.querySelectorAll('.data-quality-tab');
    const activate = (tab) => {
        tabs.forEach((t) => {
            const active = t === tab;
            t.setAttribute('aria-selected', active ? 'true' : 'false');
            if (window.AdminUnderlineTabs) {
                window.AdminUnderlineTabs.setStripButtonActive(t, active);
            }
        });
        populatePeriodSelect(tab.dataset.templateId);
        loadActiveScore();
    };

    if (periodSelect) {
        periodSelect.addEventListener('change', loadActiveScore);
    }
    tabs.forEach((tab) => tab.addEventListener('click', () => activate(tab)));
    if (tabs.length) activate(tabs[0]);
}

// Render charts and set up event listeners when the DOM is fully loaded
document.addEventListener('DOMContentLoaded', function() {
    if (document.getElementById('data-quality-dashboard')) {
        initDataQualityDashboard();
    } else {
        renderCompletionRateChart();
        renderDataQualityChart();
    }

    // Initialize filtering and pagination for Past Assignments
    initializeFilteringAndPagination();

    // NEW: JavaScript for the Self-Report Templates button and dropdown
    const selfReportButton = document.getElementById('self-report-templates-button');
    const selfReportDropdown = document.getElementById('self-report-templates-dropdown');

    if (selfReportButton && selfReportDropdown) {
        selfReportButton.addEventListener('click', function() {
            const isExpanded = selfReportButton.getAttribute('aria-expanded') === 'true';
            selfReportButton.setAttribute('aria-expanded', !isExpanded);
            selfReportDropdown.classList.toggle('hidden');
        });

        // Close the dropdown if the user clicks outside of it
        document.addEventListener('click', function(event) {
            if (!selfReportButton.contains(event.target) && !selfReportDropdown.contains(event.target)) {
                selfReportDropdown.classList.add('hidden');
                selfReportButton.setAttribute('aria-expanded', 'false');
            }
        });
    }

    // NEW: JavaScript for the Past Assignments section toggle
    const approvedAssignmentsHeader = document.getElementById('approved-assignments-header');
    const approvedAssignmentsContent = document.getElementById('approved-assignments-content');
    const toggleApprovedAssignmentsButton = document.getElementById('toggle-approved-assignments');
    const approvedAssignmentsHint = document.getElementById('approved-assignments-hint');
    const approvedAssignmentsToggleText = document.getElementById('approved-assignments-toggle-text');

    if (approvedAssignmentsHeader && approvedAssignmentsContent && toggleApprovedAssignmentsButton) {
        function setExpandedState(isExpanded) {
            // aria-expanded on both header (role=button) and the actual button
            approvedAssignmentsHeader.setAttribute('aria-expanded', String(isExpanded));
            toggleApprovedAssignmentsButton.setAttribute('aria-expanded', String(isExpanded));

            // Rotate only the arrow icon (not the Show/Hide text)
            const chevron = document.getElementById('approved-assignments-chevron');
            if (chevron) {
                if (isExpanded) {
                    chevron.classList.remove('rotate-0');
                    chevron.classList.add('rotate-180'); // Rotate up when expanded
                } else {
                    chevron.classList.remove('rotate-180');
                    chevron.classList.add('rotate-0'); // Rotate down when collapsed
                }
            }

            // Update microcopy (optional elements)
            if (approvedAssignmentsHint) {
                approvedAssignmentsHint.textContent = isExpanded ? 'Click to collapse' : 'Click to expand';
            }
            if (approvedAssignmentsToggleText) {
                approvedAssignmentsToggleText.textContent = isExpanded ? 'Hide' : 'Show';
            }
            toggleApprovedAssignmentsButton.title = isExpanded ? 'Hide past assignments' : 'Show past assignments';
        }

        function toggleApprovedAssignments() {
            const isHidden = approvedAssignmentsContent.classList.contains('hidden');
            // if it was hidden, we're expanding; if it was visible, we're collapsing
            approvedAssignmentsContent.classList.toggle('hidden');
            setExpandedState(isHidden);
        }

        // Click anywhere on the header row toggles
        approvedAssignmentsHeader.addEventListener('click', function() {
            toggleApprovedAssignments();
        });

        // Keyboard support for the header "button"
        approvedAssignmentsHeader.addEventListener('keydown', function(event) {
            if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                toggleApprovedAssignments();
            }
        });

        // Also make the chevron/button itself clickable (without double-triggering)
        toggleApprovedAssignmentsButton.addEventListener('click', function(event) {
            event.stopPropagation();
            toggleApprovedAssignments();
        });

        // Ensure initial state is consistent
        setExpandedState(!approvedAssignmentsContent.classList.contains('hidden'));
    }

    // NEW: JavaScript for filtering and pagination of Past Assignments
    function initializeFilteringAndPagination() {
        const periodSlicer = document.getElementById('period-slicer');
        const templateSlicer = document.getElementById('template-slicer');
        const statusSlicer = document.getElementById('status-slicer');
        const approvedAssignmentsList = document.getElementById('approved-assignments-list'); // Get the table

        // Pagination variables
        let currentPage = 1;
        const recordsPerPage = 10;

        if (periodSlicer && templateSlicer && statusSlicer && approvedAssignmentsList) {



            // Function to get all visible rows after filtering
            function getVisibleRows() {
                const allRows = approvedAssignmentsList.querySelectorAll('tbody tr.approved-assignment-item');
                const visibleRows = [];

                allRows.forEach((row, index) => {
                    const itemPeriod = row.getAttribute('data-period') || '';
                    const itemTemplate = row.getAttribute('data-template') || '';
                    const itemStatus = row.getAttribute('data-status') || '';
                    const selectedPeriod = periodSlicer.value;
                    const selectedTemplate = templateSlicer.value;
                    const selectedStatus = statusSlicer.value;

                    // Check if the item matches the selected filters
                    const periodMatch = (selectedPeriod === '' || itemPeriod === selectedPeriod);
                    const templateMatch = (selectedTemplate === '' || itemTemplate === selectedTemplate);
                    const statusMatch = (selectedStatus === '' || itemStatus === selectedStatus);

                    if (periodMatch && templateMatch && statusMatch) {
                        visibleRows.push(row);
                    }
                });

                return visibleRows;
            }

            // Function to show/hide rows based on current page
            function showPage(page) {
                const visibleRows = getVisibleRows();
                const totalPages = Math.ceil(visibleRows.length / recordsPerPage);

                // Ensure page is within valid range
                if (page < 1) page = 1;
                if (page > totalPages) page = totalPages;

                currentPage = page;

                // First, hide all rows
                const allRows = approvedAssignmentsList.querySelectorAll('tbody tr.approved-assignment-item');
                allRows.forEach(row => {
                    row.style.display = 'none';
                });

                // Then show only the filtered rows for current page
                const startIndex = (currentPage - 1) * recordsPerPage;
                const endIndex = startIndex + recordsPerPage;

                for (let i = startIndex; i < endIndex && i < visibleRows.length; i++) {
                    visibleRows[i].style.display = '';
                }

                // Update pagination controls
                updatePaginationControls(visibleRows.length, totalPages);
            }

            // Function to update pagination controls
            function updatePaginationControls(totalRecords, totalPages) {
                const startRecord = totalRecords > 0 ? (currentPage - 1) * recordsPerPage + 1 : 0;
                const endRecord = Math.min(currentPage * recordsPerPage, totalRecords);

                // Update record count display
                document.getElementById('start-record').textContent = startRecord;
                document.getElementById('end-record').textContent = endRecord;
                document.getElementById('total-records').textContent = totalRecords;

                // Update previous/next buttons
                const prevButtons = document.querySelectorAll('#prev-page, #prev-page-mobile');
                const nextButtons = document.querySelectorAll('#next-page, #next-page-mobile');

                prevButtons.forEach(btn => {
                    btn.disabled = currentPage <= 1;
                });

                nextButtons.forEach(btn => {
                    btn.disabled = currentPage >= totalPages;
                });

                // Generate page numbers
                const pageNumbersContainer = document.getElementById('page-numbers');
                pageNumbersContainer.replaceChildren();

                const maxVisiblePages = 5;
                let startPage = Math.max(1, currentPage - Math.floor(maxVisiblePages / 2));
                let endPage = Math.min(totalPages, startPage + maxVisiblePages - 1);

                if (endPage - startPage + 1 < maxVisiblePages) {
                    startPage = Math.max(1, endPage - maxVisiblePages + 1);
                }

                for (let i = startPage; i <= endPage; i++) {
                    const pageButton = document.createElement('button');
                    pageButton.className = `relative inline-flex items-center px-4 py-2 border text-sm font-medium ${
                        i === currentPage
                            ? 'z-10 bg-blue-50 border-blue-500 text-blue-600'
                            : 'bg-white border-gray-300 text-gray-500 hover:bg-gray-50'
                    }`;
                    pageButton.textContent = i;
                    pageButton.addEventListener('click', () => showPage(i));
                    pageNumbersContainer.appendChild(pageButton);
                }
            }

            // Function to apply filters and reset pagination
            function applyFilters() {
                currentPage = 1; // Reset to first page when filters change
                showPage(currentPage);
            }

            // Add event listeners to the slicers
            try {
                periodSlicer.addEventListener('change', function(e) {
                    applyFilters();
                });
                templateSlicer.addEventListener('change', function(e) {
                    applyFilters();
                });
                statusSlicer.addEventListener('change', function(e) {
                    applyFilters();
                });
            } catch (error) {
                console.error('Error attaching event listeners:', error);
            }

            // Add event listeners to pagination buttons
            try {
                document.getElementById('prev-page').addEventListener('click', () => {
                    if (currentPage > 1) showPage(currentPage - 1);
                });

                document.getElementById('next-page').addEventListener('click', () => {
                    const visibleRows = getVisibleRows();
                    const totalPages = Math.ceil(visibleRows.length / recordsPerPage);
                    if (currentPage < totalPages) showPage(currentPage + 1);
                });

                document.getElementById('prev-page-mobile').addEventListener('click', () => {
                    if (currentPage > 1) showPage(currentPage - 1);
                });

                document.getElementById('next-page-mobile').addEventListener('click', () => {
                    const visibleRows = getVisibleRows();
                    const totalPages = Math.ceil(visibleRows.length / recordsPerPage);
                    if (currentPage < totalPages) showPage(currentPage + 1);
                });
            } catch (error) {
                console.error('Error attaching pagination event listeners:', error);
            }

            // Initialize pagination on page load
            showPage(1);
        }
    }

    // Initialize Enhanced Search Dropdown for Countries (only if elements exist)
    if (typeof EnhancedSearchDropdown !== 'undefined') {
        const searchInput = document.getElementById('search_input');
        const searchDropdown = document.getElementById('search_dropdown');
        if (searchInput && searchDropdown) {
            new EnhancedSearchDropdown({
                searchInputId: 'search_input',
                dropdownId: 'search_dropdown',
                listId: 'search_list',
                noResultsId: 'no_results',
                formId: 'search_form',
                selectId: 'search_select',
                clearSearchId: 'clear_search'
            });
        }
    }

    // Handle form confirmations
    function resetSubmitGuardState(form) {
        if (window.FormSubmitGuard && typeof window.FormSubmitGuard.reset === 'function') {
            window.FormSubmitGuard.reset(form);
        }
    }

    document.addEventListener('submit', function(event) {
        const form = event.target;

        if (form.classList.contains('delete-self-report-form')) {
            if (form.dataset.confirmed === 'true') { delete form.dataset.confirmed; return; }
            event.preventDefault();
            resetSubmitGuardState(form);
            const _dsrBtn = form.querySelector('[type="submit"]');
            if (_dsrBtn && _dsrBtn.disabled) return;
            if (_dsrBtn) _dsrBtn.disabled = true;
            const msg = getSecureConfirmMessage('deleteSelfReport', 'Are you sure you want to delete this self-report?');
            const _dsrRestore = () => { if (_dsrBtn) _dsrBtn.disabled = false; };
            if (window.showDangerConfirmation) {
                window.showDangerConfirmation(msg, () => { form.dataset.confirmed = 'true'; form.requestSubmit ? form.requestSubmit() : form.submit(); }, _dsrRestore, 'Delete', 'Cancel', 'Confirm Delete');
            } else if (window.showConfirmation) {
                window.showConfirmation(msg, () => { form.dataset.confirmed = 'true'; form.requestSubmit ? form.requestSubmit() : form.submit(); }, _dsrRestore, 'Delete', 'Cancel', 'Confirm Delete');
            } else {
                _dsrRestore();
                console.warn('Confirmation dialog not available:', msg);
                return false;
            }
            return false;
        }

        if (form.classList.contains('approve-assignment-form')) {
            if (form.dataset.confirmed === 'true') { delete form.dataset.confirmed; return; }
            event.preventDefault();
            resetSubmitGuardState(form);
            const _aaBtn = form.querySelector('[type="submit"]');
            if (_aaBtn && _aaBtn.disabled) return;
            if (_aaBtn) _aaBtn.disabled = true;
            const msg = getSecureConfirmMessage('approveAssignment', 'Are you sure you want to approve this assignment?');
            const _aaRestore = () => { if (_aaBtn) _aaBtn.disabled = false; };
            if (window.showConfirmation) {
                window.showConfirmation(msg, () => { form.dataset.confirmed = 'true'; form.requestSubmit ? form.requestSubmit() : form.submit(); }, _aaRestore, 'Approve', 'Cancel', 'Approve Assignment?');
            } else {
                _aaRestore();
                console.warn('Confirmation dialog not available:', msg);
                return false;
            }
            return false;
        }

        if (form.classList.contains('reopen-assignment-form')) {
            if (form.dataset.confirmed === 'true') { delete form.dataset.confirmed; return; }
            event.preventDefault();
            resetSubmitGuardState(form);
            const _raBtn = form.querySelector('[type="submit"]');
            if (_raBtn && _raBtn.disabled) return;
            if (_raBtn) _raBtn.disabled = true;
            const msg = getSecureConfirmMessage('reopenAssignment', 'Are you sure you want to reopen this assignment?');
            const _raRestore = () => { if (_raBtn) _raBtn.disabled = false; };
            if (window.showConfirmation) {
                window.showConfirmation(msg, () => { form.dataset.confirmed = 'true'; form.requestSubmit ? form.requestSubmit() : form.submit(); }, _raRestore, 'Reopen', 'Cancel', 'Reopen Assignment?');
            } else {
                _raRestore();
                console.warn('Confirmation dialog not available:', msg);
                return false;
            }
            return false;
        }
    });

    // Handle submission dropdown menus
    document.addEventListener('click', function(event) {
        if (!event.target.closest('.dashboard-card-actions-overflow')) {
            closeDashboardCardActionsOverflowMenus();
        }

        // Close all dropdowns when clicking outside
        if (!event.target.closest('.relative.inline-block.text-left')) {
            document.querySelectorAll('[id^="submission-dropdown-menu-"]').forEach(menu => {
                menu.classList.add('hidden');
            });
            document.querySelectorAll('[id^="submission-dropdown-"]').forEach(button => {
                button.setAttribute('aria-expanded', 'false');
            });
        }
    });

    // Handle dropdown button clicks
    document.querySelectorAll('[id^="submission-dropdown-"]').forEach(button => {
        button.addEventListener('click', function(event) {
            event.stopPropagation();
            const menuId = this.id.replace('submission-dropdown-', 'submission-dropdown-menu-');
            const menu = document.getElementById(menuId);
            const isOpen = !menu.classList.contains('hidden');

            // Close all other dropdowns
            document.querySelectorAll('[id^="submission-dropdown-menu-"]').forEach(otherMenu => {
                if (otherMenu.id !== menuId) {
                    otherMenu.classList.add('hidden');
                }
            });
            document.querySelectorAll('[id^="submission-dropdown-"]').forEach(otherButton => {
                if (otherButton.id !== this.id) {
                    otherButton.setAttribute('aria-expanded', 'false');
                }
            });

            // Toggle current dropdown
            if (isOpen) {
                menu.classList.add('hidden');
                this.setAttribute('aria-expanded', 'false');
            } else {
                menu.classList.remove('hidden');
                this.setAttribute('aria-expanded', 'true');
            }
        });
    });

    // Handle toggle additional changes buttons (replaced inline onclick handlers for CSP compliance)
    document.querySelectorAll('.toggle-additional-changes').forEach(button => {
        button.addEventListener('click', function(event) {
            const activityIndex = this.getAttribute('data-activity-index');
            toggleAdditionalChanges(this, activityIndex);
        });
    });

});
