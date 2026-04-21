/**
 * Data Exploration - Disaggregation Analysis with ApexCharts
 * Modern charts using ApexCharts library for better visualization and interactivity.
 * Replaces Chart.js version with more modern, animated, and responsive charts.
 */
(function(global) {
    'use strict';

    /**
     * Escape HTML special characters to prevent XSS attacks.
     * @param {string} str - The string to escape
     * @returns {string} - The escaped string safe for HTML insertion
     */
    function escapeHtml(str) {
        if (str === null || str === undefined) return '';
        var div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    const UNKNOWN = 'Unknown';
    const UNKNOWN_INDICATOR = 'Unknown indicator';
    const GOVERNING_BOARD_INDICATOR_ID = 722;
    const VOLUNTEERS_INDICATOR_ID = 724;
    const STAFF_INDICATOR_ID = 727;
    const VOLUNTEERING_PATTERNS = ['volunteers', 'volunteer', 'voluntary', 'community workers', 'active volunteers', 'trained volunteers', 'registered volunteers'].map(p => p.toLowerCase());
    const STAFF_PATTERNS = ['staff', 'employees', 'personnel', 'workers', 'paid staff', 'professional staff', 'trained staff', 'registered staff'].map(p => p.toLowerCase());

    // Modern color palette
    const CHART_COLORS = {
        primary: '#2563eb',
        secondary: '#7c3aed',
        success: '#10b981',
        danger: '#ef4444',
        warning: '#f59e0b',
        info: '#06b6d4',
        dark: '#1f2937',
        muted: '#6b7280',
        palette: ['#2563eb', '#7c3aed', '#10b981', '#f59e0b', '#ef4444', '#06b6d4', '#ec4899', '#8b5cf6', '#14b8a6', '#f97316'],
        gradientPrimary: ['#3b82f6', '#1d4ed8'],
        gradientSecondary: ['#a855f7', '#7c3aed'],
        gradientSuccess: ['#34d399', '#059669'],
        female: '#ec4899',
        male: '#3b82f6'
    };

    // Common chart theme configuration
    const chartTheme = {
        mode: 'light',
        palette: 'palette1',
        monochrome: {
            enabled: false
        }
    };

    // Common chart options for consistent styling
    const commonOptions = {
        chart: {
            fontFamily: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
            toolbar: {
                show: true,
                tools: {
                    download: true,
                    selection: false,
                    zoom: false,
                    zoomin: false,
                    zoomout: false,
                    pan: false,
                    reset: false
                }
            },
            animations: {
                enabled: true,
                easing: 'easeinout',
                speed: 800,
                animateGradually: {
                    enabled: true,
                    delay: 150
                },
                dynamicAnimation: {
                    enabled: true,
                    speed: 350
                }
            },
            dropShadow: {
                enabled: false
            }
        },
        theme: chartTheme,
        grid: {
            borderColor: '#e5e7eb',
            strokeDashArray: 4,
            padding: {
                top: 0,
                right: 0,
                bottom: 0,
                left: 0
            }
        },
        tooltip: {
            theme: 'light',
            style: {
                fontSize: '12px'
            },
            y: {
                formatter: function(val) {
                    if (val === null || val === undefined) return '';
                    return typeof val === 'number' ? val.toLocaleString() : val;
                }
            }
        },
        dataLabels: {
            enabled: false
        },
        legend: {
            position: 'bottom',
            horizontalAlign: 'center',
            fontSize: '12px',
            markers: {
                radius: 4
            }
        },
        responsive: [{
            breakpoint: 640,
            options: {
                chart: {
                    height: 300
                },
                legend: {
                    position: 'bottom'
                }
            }
        }]
    };

    function formatSexCategory(sex) {
        const map = { 'male': 'Male', 'female': 'Female', 'men': 'Male', 'women': 'Female', 'boys': 'Male', 'girls': 'Female', 'other': 'Other', 'unknown': UNKNOWN };
        return map[(sex || '').toLowerCase()] || (String(sex).charAt(0).toUpperCase() + String(sex).slice(1));
    }

    function formatAgeGroup(age) {
        const ageMap = {
            'child': '0-17 years', 'children': '0-17 years', 'infant': '0-2 years', 'adult': '18-64 years', 'adults': '18-64 years',
            'elderly': '65+ years', 'elder': '65+ years', 'senior': '65+ years', 'under_5': '0-4 years', 'under_18': '0-17 years',
            'over_65': '65+ years', '0_4': '0-4 years', '5_17': '5-17 years', '18_59': '18-59 years', '60_plus': '60+ years', 'unknown': UNKNOWN
        };
        const clean = String(age).toLowerCase().replace(/[^a-z0-9_]/g, '');
        if (ageMap[clean]) return ageMap[clean];
        if (clean.indexOf('_') !== -1) {
            const parts = clean.split('_');
            if (parts.length === 2 && (parts[1] === 'plus' || parts[1] === 'over')) return parts[0] + '+ years';
            if (parts.length === 2) return parts[0] + '-' + parts[1] + ' years';
        }
        return String(age).charAt(0).toUpperCase() + String(age).slice(1).replace(/_/g, ' ');
    }

    function extractYearFromPeriod(periodName) {
        if (!periodName) return 0;
        const m = String(periodName).match(/\b(20\d{2})\b/);
        return m ? parseInt(m[1], 10) : 0;
    }

    function sortAgeGroups(a, b) {
        function order(ag) {
            if (ag.indexOf('0-2') !== -1 || ag.indexOf('0-4') !== -1) return 1;
            if (ag.indexOf('5-17') !== -1) return 2;
            if (ag.indexOf('18-59') !== -1 || ag.indexOf('18-64') !== -1) return 3;
            if (ag.indexOf('60+') !== -1 || ag.indexOf('65+') !== -1) return 4;
            if (ag.toLowerCase().indexOf('unknown') !== -1) return 5;
            return 99;
        }
        return order(a) - order(b);
    }

    // Processing function - same as original
    function processDisaggregationData(data, formItems, countries) {
        if (!data || !Array.isArray(data)) {
            return getEmptyProcessed();
        }
        const formItemsMap = new Map();
        const formItemsNameMap = new Map();
        const indicatorIdToNameMap = new Map();

        for (let i = 0; i < (formItems || []).length; i++) {
            const fi = formItems[i];
            const bid = (fi.bank_details && fi.bank_details.id) || fi.indicator_bank_id;
            const bname = (fi.bank_details && fi.bank_details.name) || fi.indicator_bank_name || fi.label;
            if (bid && fi.id) {
                formItemsMap.set(fi.id, parseInt(bid, 10));
                formItemsNameMap.set(fi.id, bname || UNKNOWN_INDICATOR);
                indicatorIdToNameMap.set(parseInt(bid, 10), bname || UNKNOWN_INDICATOR);
            }
        }

        const countriesMap = new Map();
        const countryNameToRegion = {};
        (countries || []).forEach(c => {
            if (c.id) countriesMap.set(c.id, { name: c.name || UNKNOWN, region: c.region || 'Other' });
            if (c.name) countryNameToRegion[c.name] = c.region || 'Other';
        });

        const filteredData = [];
        const validUnits = ['people', 'person', 'volunteers', 'volunteer', 'staff', 'employees', 'employee', 'personnel'];

        for (let i = 0; i < data.length; i++) {
            const item = data[i];
            const hasDisagg = item.disaggregation_data && item.disaggregation_data.values && Object.keys(item.disaggregation_data.values).length > 0;
            if (hasDisagg) {
                filteredData.push(item);
                continue;
            }
            const unit = (item.form_item_info && item.form_item_info.bank_details && item.form_item_info.bank_details.unit) ||
                (item.form_item_info && item.form_item_info.unit) || item.unit || (item.bank_details && item.bank_details.unit);
            if (unit && validUnits.indexOf(String(unit).toLowerCase().trim()) !== -1) filteredData.push(item);
            else if (item.value != null || item.answer_value != null) filteredData.push(item);
        }

        const result = {
            totalReached: 0,
            byCountry: {},
            bySex: {},
            byAge: {},
            bySexAge: {},
            trends: {},
            byIndicator: {},
            countryDisaggregation: {},
            // Coverage breakdown by year for filtering in "Country Disaggregation Coverage"
            // Shape: { [year:number]: { [countryName:string]: { totalItems:number, onlyTotal:number } } }
            countryDisaggregationByYear: {},
            womenInLeadership: { leadership: {}, volunteering: {}, staff: {}, trends: {} }
        };

        for (let i = 0; i < filteredData.length; i++) {
            const item = filteredData[i];
            const countryInfo = item.country_info;
            const formItemInfo = item.form_item_info;
            const bankDetails = formItemInfo && formItemInfo.bank_details;
            const country = (countryInfo && countryInfo.name) || (item.country_id && countriesMap.has(item.country_id) ? countriesMap.get(item.country_id).name : null) || UNKNOWN;
            const period = item.period_name || UNKNOWN;
            const year = extractYearFromPeriod(period);
            let indicatorId = (bankDetails && bankDetails.id) || (formItemInfo && formItemInfo.indicator_bank_id) || item.indicator_bank_id || item.indicator_id;
            if (!indicatorId && item.form_item_id && formItemsMap.has(item.form_item_id)) indicatorId = formItemsMap.get(item.form_item_id);
            let indicator = (bankDetails && bankDetails.name) || (formItemInfo && formItemInfo.indicator_bank_name) || item.indicator_bank_name || formItemInfo && formItemInfo.label;
            if (!indicator || indicator === UNKNOWN_INDICATOR) {
                if (item.form_item_id && formItemsNameMap.has(item.form_item_id)) indicator = formItemsNameMap.get(item.form_item_id);
                else if (indicatorId && indicatorIdToNameMap.has(indicatorId)) indicator = indicatorIdToNameMap.get(indicatorId);
                else indicator = UNKNOWN_INDICATOR;
            }
            const disaggregationData = item.disaggregation_data;
            const hasDisaggregation = disaggregationData && disaggregationData.values;
            const mode = disaggregationData && disaggregationData.mode;
            const isGoverningBoard = indicatorId === GOVERNING_BOARD_INDICATOR_ID || indicatorId == GOVERNING_BOARD_INDICATOR_ID;
            const indLower = (indicator || '').toLowerCase();
            const isVolunteering = (indicatorId === VOLUNTEERS_INDICATOR_ID || indicatorId == VOLUNTEERS_INDICATOR_ID) || VOLUNTEERING_PATTERNS.some(p => indLower.indexOf(p) !== -1);
            const isStaff = (indicatorId === STAFF_INDICATOR_ID || indicatorId == STAFF_INDICATOR_ID) || STAFF_PATTERNS.some(p => indLower.indexOf(p) !== -1);
            const canProcessGender = hasDisaggregation && (mode === 'sex' || mode === 'sex_age');

            if (!result.byCountry[country]) result.byCountry[country] = { total: 0, count: 0 };
            if (!result.trends[period]) result.trends[period] = { total: 0, count: 0, totalItems: 0, sexDisaggregated: 0, ageDisaggregated: 0, sexAgeDisaggregated: 0, onlyTotal: 0 };
            if (!result.byIndicator[indicator]) result.byIndicator[indicator] = { total: 0, count: 0, id: indicatorId, bySex: {}, byAge: {}, bySexAge: {} };
            if (!result.countryDisaggregation[country]) result.countryDisaggregation[country] = { totalItems: 0, sexDisaggregated: 0, ageDisaggregated: 0, sexAgeDisaggregated: 0, onlyTotal: 0, totalValue: 0 };
            if (isGoverningBoard && !result.womenInLeadership.leadership[country]) result.womenInLeadership.leadership[country] = { female: 0, male: 0, total: 0 };
            if (isVolunteering && !result.womenInLeadership.volunteering[country]) result.womenInLeadership.volunteering[country] = { female: 0, male: 0, total: 0 };
            if (isStaff && !result.womenInLeadership.staff[country]) result.womenInLeadership.staff[country] = { female: 0, male: 0, total: 0 };
            if (!result.womenInLeadership.trends[period]) result.womenInLeadership.trends[period] = { leadershipFemale: 0, leadershipTotal: 0, volunteeringFemale: 0, volunteeringTotal: 0, staffFemale: 0, staffTotal: 0 };

            result.countryDisaggregation[country].totalItems += 1;
            result.trends[period].totalItems += 1;

            // Track by-year totals for coverage filtering
            if (year > 0) {
                if (!result.countryDisaggregationByYear[year]) result.countryDisaggregationByYear[year] = {};
                if (!result.countryDisaggregationByYear[year][country]) result.countryDisaggregationByYear[year][country] = { totalItems: 0, onlyTotal: 0 };
                result.countryDisaggregationByYear[year][country].totalItems += 1;
            }

            if (!hasDisaggregation || !disaggregationData.values) {
                result.countryDisaggregation[country].onlyTotal += 1;
                result.trends[period].onlyTotal += 1;
                const totalVal = parseFloat(item.answer_value || item.value) || 0;
                result.countryDisaggregation[country].totalValue += totalVal;
                result.byCountry[country].total += totalVal;
                result.byCountry[country].count += 1;
                result.trends[period].total += totalVal;
                result.trends[period].count += 1;
                result.byIndicator[indicator].total += totalVal;
                result.byIndicator[indicator].count += 1;
                result.totalReached += totalVal;

                if (year > 0 && result.countryDisaggregationByYear[year] && result.countryDisaggregationByYear[year][country]) {
                    result.countryDisaggregationByYear[year][country].onlyTotal += 1;
                }
                continue;
            }

            const values = disaggregationData.values;
            const actualValues = values.direct || values;
            let itemTotal = 0;
            for (const k in actualValues) { if (Object.prototype.hasOwnProperty.call(actualValues, k)) itemTotal += parseFloat(actualValues[k]) || 0; }
            result.countryDisaggregation[country].totalValue += itemTotal;
            if (mode === 'sex') { result.countryDisaggregation[country].sexDisaggregated += 1; result.trends[period].sexDisaggregated += 1; }
            else if (mode === 'age') { result.countryDisaggregation[country].ageDisaggregated += 1; result.trends[period].ageDisaggregated += 1; }
            else if (mode === 'sex_age') {
                result.countryDisaggregation[country].sexAgeDisaggregated += 1;
                result.countryDisaggregation[country].ageDisaggregated += 1;
                result.trends[period].sexAgeDisaggregated += 1;
                result.trends[period].ageDisaggregated += 1;
            }

            function addToResult(sexKey, ageKey, sexAgeKey, val) {
                const v = parseFloat(val) || 0;
                if (sexKey) { result.bySex[sexKey] = (result.bySex[sexKey] || 0) + v; result.byIndicator[indicator].bySex[sexKey] = (result.byIndicator[indicator].bySex[sexKey] || 0) + v; }
                if (ageKey) { result.byAge[ageKey] = (result.byAge[ageKey] || 0) + v; result.byIndicator[indicator].byAge[ageKey] = (result.byIndicator[indicator].byAge[ageKey] || 0) + v; }
                if (sexAgeKey) { result.bySexAge[sexAgeKey] = (result.bySexAge[sexAgeKey] || 0) + v; result.byIndicator[indicator].bySexAge[sexAgeKey] = (result.byIndicator[indicator].bySexAge[sexAgeKey] || 0) + v; }
                result.byCountry[country].total += v;
                result.byCountry[country].count += 1;
                result.trends[period].total += v;
                result.trends[period].count += 1;
                result.byIndicator[indicator].total += v;
                result.byIndicator[indicator].count += 1;
                result.totalReached += v;
            }

            if (mode === 'sex') {
                for (const k in actualValues) {
                    if (!Object.prototype.hasOwnProperty.call(actualValues, k)) continue;
                    const sexFormatted = formatSexCategory(k);
                    const val = actualValues[k];
                    addToResult(sexFormatted, null, null, val);
                    if (isGoverningBoard) {
                        if (sexFormatted === 'Female') { result.womenInLeadership.leadership[country].female += parseFloat(val) || 0; result.womenInLeadership.trends[period].leadershipFemale += parseFloat(val) || 0; }
                        else if (sexFormatted === 'Male') result.womenInLeadership.leadership[country].male += parseFloat(val) || 0;
                        result.womenInLeadership.leadership[country].total += parseFloat(val) || 0;
                        result.womenInLeadership.trends[period].leadershipTotal += parseFloat(val) || 0;
                    }
                    if (isVolunteering && canProcessGender) {
                        if (sexFormatted === 'Female') { result.womenInLeadership.volunteering[country].female += parseFloat(val) || 0; result.womenInLeadership.trends[period].volunteeringFemale += parseFloat(val) || 0; }
                        else if (sexFormatted === 'Male') result.womenInLeadership.volunteering[country].male += parseFloat(val) || 0;
                        result.womenInLeadership.volunteering[country].total += parseFloat(val) || 0;
                        result.womenInLeadership.trends[period].volunteeringTotal += parseFloat(val) || 0;
                    }
                    if (isStaff && canProcessGender) {
                        if (sexFormatted === 'Female') { result.womenInLeadership.staff[country].female += parseFloat(val) || 0; result.womenInLeadership.trends[period].staffFemale += parseFloat(val) || 0; }
                        else if (sexFormatted === 'Male') result.womenInLeadership.staff[country].male += parseFloat(val) || 0;
                        result.womenInLeadership.staff[country].total += parseFloat(val) || 0;
                        result.womenInLeadership.trends[period].staffTotal += parseFloat(val) || 0;
                    }
                }
            } else if (mode === 'age') {
                for (const k in actualValues) {
                    if (!Object.prototype.hasOwnProperty.call(actualValues, k)) continue;
                    addToResult(null, formatAgeGroup(k), null, actualValues[k]);
                }
            } else if (mode === 'sex_age') {
                for (const k in actualValues) {
                    if (!Object.prototype.hasOwnProperty.call(actualValues, k)) continue;
                    const parts = k.split('_');
                    const sexPart = formatSexCategory(parts[0]);
                    const agePart = formatAgeGroup(parts.slice(1).join('_'));
                    const sexAgePart = sexPart + ' - ' + agePart;
                    const v = parseFloat(actualValues[k]) || 0;
                    addToResult(sexPart, agePart, sexAgePart, actualValues[k]);
                    if (isGoverningBoard) {
                        if (sexPart === 'Female') { result.womenInLeadership.leadership[country].female += v; result.womenInLeadership.trends[period].leadershipFemale += v; }
                        else if (sexPart === 'Male') result.womenInLeadership.leadership[country].male += v;
                        result.womenInLeadership.leadership[country].total += v;
                        result.womenInLeadership.trends[period].leadershipTotal += v;
                    }
                    if (isVolunteering && canProcessGender) {
                        if (sexPart === 'Female') { result.womenInLeadership.volunteering[country].female += v; result.womenInLeadership.trends[period].volunteeringFemale += v; }
                        else if (sexPart === 'Male') result.womenInLeadership.volunteering[country].male += v;
                        result.womenInLeadership.volunteering[country].total += v;
                        result.womenInLeadership.trends[period].volunteeringTotal += v;
                    }
                    if (isStaff && canProcessGender) {
                        if (sexPart === 'Female') { result.womenInLeadership.staff[country].female += v; result.womenInLeadership.trends[period].staffFemale += v; }
                        else if (sexPart === 'Male') result.womenInLeadership.staff[country].male += v;
                        result.womenInLeadership.staff[country].total += v;
                        result.womenInLeadership.trends[period].staffTotal += v;
                    }
                }
            }
        }

        const yearSet = new Set();
        filteredData.forEach(it => { const y = extractYearFromPeriod(it.period_name); if (y > 0) yearSet.add(y); });
        const availableYears = Array.from(yearSet).sort((a, b) => b - a);

        const byCountryArr = Object.entries(result.byCountry).map(([label, d]) => ({
            label, value: d.count > 0 ? Math.round(d.total / d.count) : 0, total: d.total, count: d.count
        })).sort((a, b) => b.value - a.value).slice(0, 15);

        const bySexArr = Object.entries(result.bySex).map(([label, val]) => ({ label, value: Math.round(val) })).sort((a, b) => b.value - a.value);
        const byAgeArr = Object.entries(result.byAge).map(([label, val]) => ({ label, value: Math.round(val) })).sort((a, b) => sortAgeGroups(a.label, b.label));
        const bySexAgeArr = Object.entries(result.bySexAge).map(([label, val]) => ({ label, value: Math.round(val) })).sort((a, b) => b.value - a.value).slice(0, 20);

        const trendsArr = Object.entries(result.trends).map(([label, d]) => {
            const itemsWithDisagg = d.totalItems - d.onlyTotal;
            return {
                label,
                value: d.count > 0 ? Math.round(d.total / d.count) : 0,
                total: d.total,
                count: d.count,
                ageDisaggregationPercentage: d.totalItems > 0 ? Math.round((d.ageDisaggregated / d.totalItems) * 100) : 0,
                overallDisaggregationPercentage: d.totalItems > 0 ? Math.round((itemsWithDisagg / d.totalItems) * 100) : 0
            };
        }).sort((a, b) => a.label.localeCompare(b.label));

        const byIndicatorArr = Object.entries(result.byIndicator).map(([label, d]) => ({
            label,
            value: Math.round(d.total),
            average: d.count > 0 ? Math.round(d.total / d.count) : 0,
            count: d.count,
            id: d.id,
            bySex: Object.entries(d.bySex).map(([l, v]) => ({ label: l, value: Math.round(v) })),
            byAge: Object.entries(d.byAge).map(([l, v]) => ({ label: l, value: Math.round(v) })),
            bySexAge: Object.entries(d.bySexAge).map(([l, v]) => ({ label: l, value: Math.round(v) }))
        })).filter(ind => {
            const hasSex = ind.bySex.length > 0 && ind.bySex.some(item => item.value > 0);
            const hasAge = ind.byAge.length > 0 && ind.byAge.some(item => item.value > 0);
            return hasSex || hasAge;
        }).sort((a, b) => b.value - a.value);

        const countryDisaggArr = Object.entries(result.countryDisaggregation).map(([label, d]) => {
            const itemsWithAny = d.totalItems - d.onlyTotal;
            return {
                label,
                region: countryNameToRegion[label] || 'Other',
                totalItems: d.totalItems,
                onlyTotal: d.onlyTotal,
                totalValue: Math.round(d.totalValue),
                overallDisaggregation: d.totalItems > 0 ? Math.round((itemsWithAny / d.totalItems) * 100) : 0
            };
        }).sort((a, b) => b.overallDisaggregation - a.overallDisaggregation);

        const leadershipArr = Object.entries(result.womenInLeadership.leadership).map(([label, d]) => ({
            label, female: d.female, male: d.male, total: d.total, femalePercentage: d.total > 0 ? Math.round((d.female / d.total) * 100) : 0
        })).sort((a, b) => b.femalePercentage - a.femalePercentage);

        const volunteeringArr = Object.entries(result.womenInLeadership.volunteering).map(([label, d]) => ({
            label, female: d.female, male: d.male, total: d.total, femalePercentage: d.total > 0 ? Math.round((d.female / d.total) * 100) : 0
        })).sort((a, b) => b.femalePercentage - a.femalePercentage);

        const staffArr = Object.entries(result.womenInLeadership.staff).map(([label, d]) => ({
            label, female: d.female, male: d.male, total: d.total, femalePercentage: d.total > 0 ? Math.round((d.female / d.total) * 100) : 0
        })).sort((a, b) => b.femalePercentage - a.femalePercentage);

        // Women in Leadership was not collected before 2017; use chart-specific year range
        const WOMEN_LEADERSHIP_MIN_YEAR = '2017';
        const trendsWomenArr = Object.entries(result.womenInLeadership.trends)
            .filter(([label, d]) => (label >= WOMEN_LEADERSHIP_MIN_YEAR) && (d.leadershipTotal > 0 || d.volunteeringTotal > 0 || d.staffTotal > 0))
            .map(([label, d]) => ({
                label,
                leadershipPercentage: d.leadershipTotal > 0 ? Math.round((d.leadershipFemale / d.leadershipTotal) * 100) : 0,
                volunteeringPercentage: d.volunteeringTotal > 0 ? Math.round((d.volunteeringFemale / d.volunteeringTotal) * 100) : 0,
                staffPercentage: d.staffTotal > 0 ? Math.round((d.staffFemale / d.staffTotal) * 100) : 0
            }))
            .sort((a, b) => a.label.localeCompare(b.label));

        const comparison = [
            { label: 'Leadership Roles', value: Object.values(result.womenInLeadership.leadership).reduce((s, d) => s + d.female, 0), total: Object.values(result.womenInLeadership.leadership).reduce((s, d) => s + d.total, 0) },
            { label: 'Volunteering', value: Object.values(result.womenInLeadership.volunteering).reduce((s, d) => s + d.female, 0), total: Object.values(result.womenInLeadership.volunteering).reduce((s, d) => s + d.total, 0) },
            { label: 'Staff', value: Object.values(result.womenInLeadership.staff).reduce((s, d) => s + d.female, 0), total: Object.values(result.womenInLeadership.staff).reduce((s, d) => s + d.total, 0) }
        ].map(item => ({ label: item.label, value: item.value, total: item.total, percentage: item.total > 0 ? Math.round((item.value / item.total) * 100) : 0 }));

        return {
            totalReached: result.totalReached,
            availableYears,
            byCountry: byCountryArr,
            bySex: bySexArr,
            byAge: byAgeArr,
            bySexAge: bySexAgeArr,
            trends: trendsArr,
            byIndicator: byIndicatorArr,
            countryDisaggregation: countryDisaggArr,
            countryDisaggregationByYear: result.countryDisaggregationByYear,
            womenInLeadership: {
                leadership: leadershipArr,
                volunteering: volunteeringArr,
                staff: staffArr,
                trends: trendsWomenArr,
                comparison
            }
        };
    }

    function getEmptyProcessed() {
        return {
            totalReached: 0,
            availableYears: [],
            byCountry: [],
            bySex: [],
            byAge: [],
            bySexAge: [],
            trends: [],
            byIndicator: [],
            countryDisaggregation: [],
            countryDisaggregationByYear: {},
            womenInLeadership: { leadership: [], volunteering: [], staff: [], trends: [], comparison: [] }
        };
    }

    // Store chart instances for cleanup
    const chartInstances = {};

    function destroyCharts(keys) {
        keys = keys || Object.keys(chartInstances);
        keys.forEach(key => {
            if (chartInstances[key]) {
                chartInstances[key].destroy();
                chartInstances[key] = null;
            }
        });
    }

    function getApexCharts() {
        return (typeof globalThis !== 'undefined' && globalThis.ApexCharts) ||
               (typeof window !== 'undefined' && window.ApexCharts);
    }

    // Modern bar chart with gradient
    function createBarChart(containerId, data, options = {}) {
        const container = document.getElementById(containerId);
        if (!container) return null;

        const ApexCharts = getApexCharts();
        if (!ApexCharts) {
            console.warn('ApexCharts not loaded');
            return null;
        }

        if (chartInstances[containerId]) {
            chartInstances[containerId].destroy();
            chartInstances[containerId] = null;
        }

        container.innerHTML = '';

        const labels = data.map(d => d.label);
        const values = data.map(d => d.value);
        const isHorizontal = options.horizontal !== false;

        // Calculate max label length for dynamic left margin
        const maxLabelLength = Math.max(...labels.map(l => l.length));
        const leftMargin = isHorizontal ? Math.min(Math.max(maxLabelLength * 6, 100), 180) : 10;

        // Calculate max value for determining label placement
        const maxValue = Math.max(...values);

        const chartOptions = {
            ...commonOptions,
            chart: {
                ...commonOptions.chart,
                type: 'bar',
                height: options.height || 350
            },
            grid: {
                ...commonOptions.grid,
                padding: {
                    left: isHorizontal ? leftMargin : 10,
                    right: isHorizontal ? 80 : 20, // Extra right padding for outside labels
                    top: 0,
                    bottom: 0
                }
            },
            plotOptions: {
                bar: {
                    horizontal: isHorizontal,
                    borderRadius: 4,
                    borderRadiusApplication: 'end',
                    dataLabels: {
                        position: 'top' // Position at end of bar
                    },
                    columnWidth: '60%',
                    barHeight: '65%'
                }
            },
            colors: options.colors || [CHART_COLORS.primary],
            fill: {
                type: 'gradient',
                gradient: {
                    shade: 'light',
                    type: isHorizontal ? 'horizontal' : 'vertical',
                    shadeIntensity: 0.25,
                    gradientToColors: options.gradientTo || [CHART_COLORS.secondary],
                    inverseColors: false,
                    opacityFrom: 1,
                    opacityTo: 0.85,
                    stops: [0, 100]
                }
            },
            series: [{
                name: options.seriesName || 'Value',
                data: values
            }],
            xaxis: {
                categories: labels,
                labels: {
                    style: {
                        fontSize: '11px',
                        fontWeight: 500
                    },
                    trim: true,
                    maxHeight: 80,
                    formatter: val => typeof val === 'number' ? val.toLocaleString() : val
                }
            },
            yaxis: {
                labels: {
                    show: true,
                    minWidth: isHorizontal ? leftMargin : 0,
                    maxWidth: isHorizontal ? leftMargin : 160,
                    style: {
                        fontSize: '11px'
                    },
                    formatter: val => typeof val === 'number' ? val.toLocaleString() : val,
                    offsetX: 0
                }
            },
            dataLabels: {
                enabled: options.showDataLabels !== false,
                formatter: val => typeof val === 'number' ? val.toLocaleString() : val,
                textAnchor: isHorizontal ? 'start' : 'middle',
                style: {
                    fontSize: '11px',
                    fontWeight: 600,
                    colors: ['#374151'] // Dark gray - always readable
                },
                offsetX: isHorizontal ? 5 : 0, // Push labels outside the bar for horizontal
                offsetY: isHorizontal ? 0 : -5, // Push labels above the bar for vertical
                dropShadow: {
                    enabled: false
                },
                background: {
                    enabled: false
                }
            }
        };

        const chart = new ApexCharts(container, chartOptions);
        chart.render();
        chartInstances[containerId] = chart;
        return chart;
    }

    // Modern donut/pie chart
    function createDonutChart(containerId, data, options = {}) {
        const container = document.getElementById(containerId);
        if (!container) return null;

        const ApexCharts = getApexCharts();
        if (!ApexCharts) {
            console.warn('ApexCharts not loaded');
            return null;
        }

        if (chartInstances[containerId]) {
            chartInstances[containerId].destroy();
            chartInstances[containerId] = null;
        }

        container.innerHTML = '';

        const labels = data.map(d => d.label);
        const values = data.map(d => d.value);

        // Assign colors based on sex categories if applicable
        let colors = options.colors || CHART_COLORS.palette.slice(0, labels.length);
        if (labels.includes('Female') || labels.includes('Male')) {
            colors = labels.map(label => {
                if (label === 'Female') return CHART_COLORS.female;
                if (label === 'Male') return CHART_COLORS.male;
                return CHART_COLORS.muted;
            });
        }

        const chartOptions = {
            ...commonOptions,
            chart: {
                ...commonOptions.chart,
                type: options.type || 'donut',
                height: options.height || 380
            },
            series: values,
            labels: labels,
            colors: colors,
            plotOptions: {
                pie: {
                    donut: {
                        size: options.donutSize || '65%',
                        labels: {
                            show: true,
                            name: {
                                show: true,
                                fontSize: '14px',
                                fontWeight: 600,
                                color: '#374151',
                                offsetY: -10
                            },
                            value: {
                                show: true,
                                fontSize: '24px',
                                fontWeight: 700,
                                color: '#111827',
                                offsetY: 5,
                                formatter: val => typeof val === 'number' ? val.toLocaleString() : val
                            },
                            total: {
                                show: options.showTotal !== false,
                                showAlways: true,
                                label: 'Total',
                                fontSize: '12px',
                                fontWeight: 500,
                                color: '#6b7280',
                                formatter: w => w.globals.seriesTotals.reduce((a, b) => a + b, 0).toLocaleString()
                            }
                        }
                    },
                    expandOnClick: true
                }
            },
            stroke: {
                width: 3,
                colors: ['#fff']
            },
            legend: {
                show: true,
                position: 'right',
                fontSize: '13px',
                fontWeight: 600,
                width: 200,
                offsetY: 0,
                markers: {
                    width: 12,
                    height: 12,
                    radius: 3,
                    offsetX: 0,
                    offsetY: 1
                },
                itemMargin: {
                    horizontal: 0,
                    vertical: 6
                },
                formatter: function(seriesName, opts) {
                    const value = opts.w.globals.series[opts.seriesIndex];
                    const total = opts.w.globals.seriesTotals.reduce((a, b) => a + b, 0);
                    const pct = total > 0 ? Math.round((value / total) * 100) : 0;
                    // Name on same line as marker, value below
                    return seriesName + ' <span style="font-weight: 400; color: #6b7280;">(' + pct + '%)</span><br/>' +
                           '<span style="font-size: 11px; font-weight: 400; color: #9ca3af; margin-left: 0;">' + value.toLocaleString() + '</span>';
                }
            },
            dataLabels: {
                enabled: false // Clean donut without on-slice labels
            },
            responsive: [{
                breakpoint: 640,
                options: {
                    chart: {
                        height: 350
                    },
                    legend: {
                        position: 'bottom',
                        width: '100%'
                    }
                }
            }]
        };

        const chart = new ApexCharts(container, chartOptions);
        chart.render();
        chartInstances[containerId] = chart;
        return chart;
    }

    // Modern line/area chart
    function createLineChart(containerId, data, options = {}) {
        const container = document.getElementById(containerId);
        if (!container) return null;

        const ApexCharts = getApexCharts();
        if (!ApexCharts) {
            console.warn('ApexCharts not loaded');
            return null;
        }

        if (chartInstances[containerId]) {
            chartInstances[containerId].destroy();
            chartInstances[containerId] = null;
        }

        container.innerHTML = '';

        const labels = data.map(d => d.label);
        const values = data.map(d => d.value);

        const chartOptions = {
            ...commonOptions,
            chart: {
                ...commonOptions.chart,
                type: options.area ? 'area' : 'line',
                height: options.height || 350
            },
            series: [{
                name: options.seriesName || 'Value',
                data: values
            }],
            colors: options.colors || [CHART_COLORS.primary],
            stroke: {
                curve: 'smooth',
                width: 3
            },
            fill: options.area ? {
                type: 'gradient',
                gradient: {
                    shadeIntensity: 1,
                    opacityFrom: 0.5,
                    opacityTo: 0.1,
                    stops: [0, 90, 100]
                }
            } : undefined,
            markers: {
                size: 5,
                colors: [CHART_COLORS.primary],
                strokeColors: '#fff',
                strokeWidth: 2,
                hover: {
                    size: 7
                }
            },
            xaxis: {
                categories: labels,
                labels: {
                    style: {
                        fontSize: '11px'
                    }
                }
            },
            yaxis: {
                labels: {
                    formatter: val => typeof val === 'number' ? val.toLocaleString() : val
                }
            }
        };

        const chart = new ApexCharts(container, chartOptions);
        chart.render();
        chartInstances[containerId] = chart;
        return chart;
    }

    // Multi-series line chart for trends
    function createMultiLineChart(containerId, series, categories, options = {}) {
        const container = document.getElementById(containerId);
        if (!container) return null;

        const ApexCharts = getApexCharts();
        if (!ApexCharts) {
            console.warn('ApexCharts not loaded');
            return null;
        }

        if (chartInstances[containerId]) {
            chartInstances[containerId].destroy();
            chartInstances[containerId] = null;
        }

        container.innerHTML = '';

        const chartOptions = {
            ...commonOptions,
            chart: {
                ...commonOptions.chart,
                type: 'line',
                height: options.height || 350
            },
            series: series,
            colors: options.colors || [CHART_COLORS.primary, CHART_COLORS.secondary, CHART_COLORS.success],
            stroke: {
                curve: 'smooth',
                width: 3
            },
            markers: {
                size: 4,
                strokeWidth: 2,
                hover: {
                    size: 6
                }
            },
            xaxis: {
                categories: categories,
                labels: {
                    style: {
                        fontSize: '11px'
                    }
                }
            },
            yaxis: {
                min: 0,
                max: 100,
                labels: {
                    formatter: val => val + '%'
                }
            },
            legend: {
                show: true,
                position: 'top'
            }
        };

        const chart = new ApexCharts(container, chartOptions);
        chart.render();
        chartInstances[containerId] = chart;
        return chart;
    }

    // Radial bar chart for percentages - with always visible labels
    function createRadialChart(containerId, data, options = {}) {
        const container = document.getElementById(containerId);
        if (!container) return null;

        const ApexCharts = getApexCharts();
        if (!ApexCharts) {
            console.warn('ApexCharts not loaded');
            return null;
        }

        if (chartInstances[containerId]) {
            chartInstances[containerId].destroy();
            chartInstances[containerId] = null;
        }

        container.innerHTML = '';

        const labels = data.map(d => d.label);
        const values = data.map(d => d.percentage || d.value);

        const chartOptions = {
            ...commonOptions,
            chart: {
                ...commonOptions.chart,
                type: 'radialBar',
                height: options.height || 380
            },
            series: values,
            labels: labels,
            colors: options.colors || [CHART_COLORS.female, CHART_COLORS.success, CHART_COLORS.info],
            plotOptions: {
                radialBar: {
                    offsetY: 0,
                    startAngle: -90,
                    endAngle: 90,
                    hollow: {
                        margin: 0,
                        size: '45%',
                        background: 'transparent'
                    },
                    track: {
                        background: '#e5e7eb',
                        strokeWidth: '100%',
                        margin: 6
                    },
                    dataLabels: {
                        show: true,
                        name: {
                            show: false
                        },
                        value: {
                            show: true,
                            fontSize: '24px',
                            fontWeight: 700,
                            color: '#111827',
                            offsetY: -5,
                            formatter: val => Math.round(val) + '%'
                        },
                        total: {
                            show: true,
                            showAlways: true,
                            label: 'Avg',
                            fontSize: '11px',
                            fontWeight: 500,
                            color: '#6b7280',
                            formatter: w => {
                                const avg = Math.round(w.globals.seriesTotals.reduce((a, b) => a + b, 0) / w.globals.seriesTotals.length);
                                return avg + '%';
                            }
                        }
                    }
                }
            },
            stroke: {
                lineCap: 'round'
            },
            legend: {
                show: true,
                floating: false,
                fontSize: '13px',
                fontWeight: 500,
                position: 'bottom',
                horizontalAlign: 'center',
                offsetY: 0,
                markers: {
                    width: 12,
                    height: 12,
                    radius: 6
                },
                itemMargin: {
                    horizontal: 12,
                    vertical: 4
                },
                formatter: function(seriesName, opts) {
                    return seriesName + ': ' + opts.w.globals.series[opts.seriesIndex] + '%';
                }
            }
        };

        const chart = new ApexCharts(container, chartOptions);
        chart.render();
        chartInstances[containerId] = chart;
        return chart;
    }

    // Grouped bar chart for comparisons
    function createGroupedBarChart(containerId, data, options = {}) {
        const container = document.getElementById(containerId);
        if (!container) return null;

        const ApexCharts = getApexCharts();
        if (!ApexCharts) {
            console.warn('ApexCharts not loaded');
            return null;
        }

        if (chartInstances[containerId]) {
            chartInstances[containerId].destroy();
            chartInstances[containerId] = null;
        }

        container.innerHTML = '';

        // Extract categories (countries) and prepare series
        const categories = data.map(d => d.label);
        const femaleData = data.map(d => d.female || 0);
        const maleData = data.map(d => d.male || 0);

        const chartOptions = {
            ...commonOptions,
            chart: {
                ...commonOptions.chart,
                type: 'bar',
                height: options.height || 400,
                stacked: false
            },
            plotOptions: {
                bar: {
                    horizontal: true,
                    borderRadius: 4,
                    barHeight: '70%',
                    dataLabels: {
                        position: 'top'
                    }
                }
            },
            series: [
                { name: 'Female', data: femaleData },
                { name: 'Male', data: maleData }
            ],
            colors: [CHART_COLORS.female, CHART_COLORS.male],
            xaxis: {
                categories: categories,
                labels: {
                    style: {
                        fontSize: '11px'
                    }
                }
            },
            yaxis: {
                labels: {
                    style: {
                        fontSize: '11px'
                    }
                }
            },
            legend: {
                position: 'top'
            },
            dataLabels: {
                enabled: false
            }
        };

        const chart = new ApexCharts(container, chartOptions);
        chart.render();
        chartInstances[containerId] = chart;
        return chart;
    }

    function updateDisaggregationUI() {
        const p = window.disaggProcessedData;
        if (!p) return;

        // Initialize/update the year multiselect for "Country Disaggregation Coverage"
        try {
            initOrUpdateCoverageYearFilter(p);
        } catch (e) {
            // non-fatal
        }

        const statAvgDisagg = document.getElementById('stat-avg-disagg');
        const statAvgAge = document.getElementById('stat-avg-age');
        const statWomenLead = document.getElementById('stat-women-leadership');
        const statWomenVol = document.getElementById('stat-women-volunteering');
        const statWomenStaff = document.getElementById('stat-women-staff');

        let avgDisagg = 0;
        let avgAge = 0;
        if (p.countryDisaggregation && p.countryDisaggregation.length > 0) {
            avgDisagg = Math.round(p.countryDisaggregation.reduce((s, c) => s + c.overallDisaggregation, 0) / p.countryDisaggregation.length);
            avgAge = p.trends && p.trends.length > 0 ? Math.round(p.trends.reduce((s, t) => s + (t.ageDisaggregationPercentage || 0), 0) / p.trends.length) : 0;
        }

        let leadPct = 0, volPct = 0, staffPct = 0;
        if (p.womenInLeadership && p.womenInLeadership.comparison && p.womenInLeadership.comparison.length > 0) {
            const comp = p.womenInLeadership.comparison;
            leadPct = (comp[0] && comp[0].percentage) || 0;
            volPct = (comp[1] && comp[1].percentage) || 0;
            staffPct = (comp[2] && comp[2].percentage) || 0;
        }

        if (statAvgDisagg) statAvgDisagg.textContent = avgDisagg + '%';
        if (statAvgAge) statAvgAge.textContent = avgAge + '%';
        if (statWomenLead) statWomenLead.textContent = leadPct + '%';
        if (statWomenVol) statWomenVol.textContent = volPct + '%';
        if (statWomenStaff) statWomenStaff.textContent = staffPct + '%';

        if (window.currentDisaggSubtab && window.renderDisaggSubtabCharts) {
            window.renderDisaggSubtabCharts(window.currentDisaggSubtab);
        }
    }

    function _getCoverageYearsFromSelect(el) {
        if (!el) return [];
        try {
            const vals = (window.jQuery && window.jQuery(el).val) ? window.jQuery(el).val() : Array.from(el.selectedOptions || []).map(o => o.value);
            const out = (vals || []).map(v => parseInt(v, 10)).filter(v => Number.isFinite(v) && v > 0);
            // De-dupe
            return Array.from(new Set(out));
        } catch (e) {
            return [];
        }
    }

    function initOrUpdateCoverageYearFilter(p) {
        const el = document.getElementById('country-coverage-year-filter');
        if (!el) return;
        const years = (p && Array.isArray(p.availableYears)) ? p.availableYears.slice() : [];
        if (years.length === 0) {
            el.innerHTML = '';
            return;
        }

        // If current selection is empty/invalid, default to latest year
        const latest = years[0];
        const prev = Array.isArray(window.selectedCoverageYears) ? window.selectedCoverageYears.slice() : [];
        const validPrev = prev.filter(y => years.indexOf(y) !== -1);
        if (!validPrev.length) {
            window.selectedCoverageYears = [latest];
        } else {
            window.selectedCoverageYears = validPrev;
        }

        // Rebuild options (preserve selection)
        const selectedSet = new Set(window.selectedCoverageYears);
        el.innerHTML = years.map(y => { const n = parseInt(y, 10) || 0; return `<option value="${n}"${selectedSet.has(y) ? ' selected' : ''}>${n}</option>`; }).join('');

        // Attach change handler once
        if (!el.dataset.boundChange) {
            el.addEventListener('change', function() {
                window.selectedCoverageYears = _getCoverageYearsFromSelect(el);
                if (!window.selectedCoverageYears.length && years.length) window.selectedCoverageYears = [years[0]];
                // Re-render the current subtab only
                if (window.currentDisaggSubtab === 'country-coverage' && window.renderDisaggSubtabCharts) {
                    window.renderDisaggSubtabCharts('country-coverage');
                }
            });
            el.dataset.boundChange = '1';
        }

        // Enhance with Select2 (if available). Select2 is loaded with defer, so retry briefly if needed.
        const tryInitSelect2 = () => {
            if (!window.jQuery || !window.jQuery.fn || !window.jQuery.fn.select2) return false;
            const $el = window.jQuery(el);
            if ($el.hasClass('select2-hidden-accessible')) {
                // Keep it but refresh options/selection
                $el.trigger('change.select2');
                return true;
            }
            $el.select2({
                width: 'style',
                placeholder: el.dataset && el.dataset.placeholder ? el.dataset.placeholder : 'Select year(s)',
                closeOnSelect: false,
                allowClear: false
            });
            // Ensure correct selection is reflected
            $el.val((window.selectedCoverageYears || []).map(String)).trigger('change.select2');
            return true;
        };

        if (!tryInitSelect2()) {
            // Defer timing race: Select2 script loads after layout; retry a few times.
            let attempts = 0;
            const t = setInterval(() => {
                attempts += 1;
                if (tryInitSelect2() || attempts >= 10) clearInterval(t);
            }, 150);
        }
    }

    function getCountryCoverageListForSelectedYears(p) {
        const selectedYears = Array.isArray(window.selectedCoverageYears) ? window.selectedCoverageYears : [];
        if (!selectedYears.length || !p || !p.countryDisaggregationByYear) return (p && p.countryDisaggregation) ? p.countryDisaggregation : [];

        // Build region lookup from overall (all-years) data
        const regionByCountry = {};
        (p.countryDisaggregation || []).forEach(c => {
            if (c && c.label) regionByCountry[c.label] = c.region || 'Other';
        });

        const agg = {};
        selectedYears.forEach(y => {
            const yr = p.countryDisaggregationByYear[y] || p.countryDisaggregationByYear[String(y)];
            if (!yr) return;
            Object.keys(yr).forEach(country => {
                const d = yr[country] || {};
                if (!agg[country]) agg[country] = { totalItems: 0, onlyTotal: 0 };
                agg[country].totalItems += (d.totalItems || 0);
                agg[country].onlyTotal += (d.onlyTotal || 0);
            });
        });

        return Object.keys(agg).map(country => {
            const d = agg[country];
            const itemsWithAny = (d.totalItems || 0) - (d.onlyTotal || 0);
            return {
                label: country,
                region: regionByCountry[country] || 'Other',
                totalItems: d.totalItems || 0,
                onlyTotal: d.onlyTotal || 0,
                totalValue: 0,
                overallDisaggregation: (d.totalItems || 0) > 0 ? Math.round((itemsWithAny / d.totalItems) * 100) : 0
            };
        }).sort((a, b) => b.overallDisaggregation - a.overallDisaggregation);
    }

    function renderDisaggSubtabCharts(subtab) {
        const p = window.disaggProcessedData;
        if (!p) return;

        if (subtab === 'overview') {
            destroyCharts(['chart-overview-countries', 'chart-overview-sex']);

            // Countries bar chart - horizontal with gradient
            createBarChart('chart-overview-countries', (p.byCountry || []).slice(0, 10), {
                height: 350,
                horizontal: true,
                seriesName: 'Average Value',
                showDataLabels: true,
                colors: [CHART_COLORS.primary],
                gradientTo: ['#60a5fa']
            });

            // Sex donut chart with custom colors
            createDonutChart('chart-overview-sex', (p.bySex || []).slice(0, 10), {
                height: 350,
                type: 'donut',
                donutSize: '60%',
                showTotal: true
            });

            const noData = document.getElementById('overview-no-data');
            if (noData) {
                noData.classList.toggle('hidden', (p.byCountry && p.byCountry.length > 0) || (p.bySex && p.bySex.length > 0));
            }

        } else if (subtab === 'by-indicator') {
            destroyCharts(['chart-by-indicator']);

            const indData = (p.byIndicator || []).slice(0, 12).map(i => ({
                label: i.label.length > 35 ? i.label.substring(0, 32) + '...' : i.label,
                value: i.value
            }));

            createBarChart('chart-by-indicator', indData, {
                height: 450,
                horizontal: true,
                seriesName: 'Total Value',
                showDataLabels: true,
                colors: [CHART_COLORS.secondary],
                gradientTo: ['#c084fc']
            });

            const noData = document.getElementById('by-indicator-no-data');
            if (noData) noData.classList.toggle('hidden', indData.length > 0);

        } else if (subtab === 'women-leadership') {
            destroyCharts(['chart-women-comparison', 'chart-women-by-country', 'chart-women-trends', 'chart-trends-governing', 'chart-trends-staff', 'chart-trends-volunteers']);

            const comp = p.womenInLeadership && p.womenInLeadership.comparison ? p.womenInLeadership.comparison : [];

            // Radial chart for comparison - larger to fill the area
            createRadialChart('chart-women-comparison', comp, {
                height: 380,
                colors: [CHART_COLORS.female, CHART_COLORS.success, CHART_COLORS.info]
            });

            // Grouped bar chart for countries showing female vs male
            const lead = (p.womenInLeadership && p.womenInLeadership.leadership) ? p.womenInLeadership.leadership.slice(0, 12) : [];
            createGroupedBarChart('chart-women-by-country', lead, {
                height: 400
            });

            // Multi-line trends chart (Trends Over Time - kept as the single combined view)
            const trends = (p.womenInLeadership && p.womenInLeadership.trends) ? p.womenInLeadership.trends : [];
            if (trends.length > 0) {
                createMultiLineChart('chart-women-trends', [
                    { name: 'Leadership', data: trends.map(t => t.leadershipPercentage) },
                    { name: 'Volunteering', data: trends.map(t => t.volunteeringPercentage) },
                    { name: 'Staff', data: trends.map(t => t.staffPercentage || 0) }
                ], trends.map(t => t.label), {
                    height: 350,
                    colors: [CHART_COLORS.female, CHART_COLORS.success, CHART_COLORS.info]
                });
                // Individual trend lines (moved from Trends tab; Combined Trends removed as duplicate)
                createLineChart('chart-trends-governing', trends.map(t => ({ label: t.label, value: t.leadershipPercentage })), {
                    height: 280,
                    area: true,
                    seriesName: 'Women in Leadership %',
                    colors: [CHART_COLORS.female]
                });
                createLineChart('chart-trends-staff', trends.map(t => ({ label: t.label, value: t.staffPercentage || 0 })), {
                    height: 280,
                    area: true,
                    seriesName: 'Women in Staff %',
                    colors: [CHART_COLORS.info]
                });
                createLineChart('chart-trends-volunteers', trends.map(t => ({ label: t.label, value: t.volunteeringPercentage })), {
                    height: 280,
                    area: true,
                    seriesName: 'Women in Volunteering %',
                    colors: [CHART_COLORS.success]
                });
            }

            const noData = document.getElementById('women-leadership-no-data');
            if (noData) noData.classList.toggle('hidden', comp.length > 0 || lead.length > 0 || trends.length > 0);

        } else if (subtab === 'sex-age') {
            destroyCharts(['chart-by-sex', 'chart-by-age', 'chart-by-sex-age']);

            // Donut for sex distribution
            createDonutChart('chart-by-sex', (p.bySex || []).slice(0, 10), {
                height: 320,
                type: 'donut',
                showTotal: true
            });

            // Horizontal bar for age groups
            createBarChart('chart-by-age', (p.byAge || []).slice(0, 10), {
                height: 320,
                horizontal: true,
                seriesName: 'Count',
                colors: [CHART_COLORS.success],
                gradientTo: ['#6ee7b7']
            });

            // Vertical bar for sex-age combinations
            createBarChart('chart-by-sex-age', (p.bySexAge || []).slice(0, 12), {
                height: 350,
                horizontal: false,
                seriesName: 'Count',
                colors: [CHART_COLORS.secondary],
                gradientTo: ['#c084fc']
            });

            const noData = document.getElementById('sex-age-no-data');
            if (noData) noData.classList.toggle('hidden', (p.bySex && p.bySex.length > 0) || (p.byAge && p.byAge.length > 0));

        } else if (subtab === 'by-country') {
            destroyCharts(['chart-by-country']);

            createBarChart('chart-by-country', (p.byCountry || []).slice(0, 20), {
                height: 500,
                horizontal: true,
                seriesName: 'Average Value',
                showDataLabels: true,
                colors: [CHART_COLORS.info],
                gradientTo: ['#67e8f9']
            });

            const noData = document.getElementById('by-country-no-data');
            if (noData) noData.classList.toggle('hidden', (p.byCountry && p.byCountry.length > 0));

        } else if (subtab === 'country-coverage') {
            const regionalDiv = document.getElementById('coverage-regional-summary');
            const tableDiv = document.getElementById('coverage-countries-table');
            const noData = document.getElementById('country-coverage-no-data');

            if (regionalDiv) regionalDiv.innerHTML = '';
            if (tableDiv) tableDiv.innerHTML = '';

            if (!p.countryDisaggregation || p.countryDisaggregation.length === 0) {
                if (noData) noData.classList.remove('hidden');
                return;
            }
            if (noData) noData.classList.add('hidden');

            const list = getCountryCoverageListForSelectedYears(p);
            const byRegion = {};
            list.forEach(c => {
                const region = c.region || 'Other';
                if (!byRegion[region]) byRegion[region] = [];
                byRegion[region].push(c);
            });

            // Track selected region for filtering
            // Reset selection if the previously selected region no longer exists in the data
            const regionList = Object.keys(byRegion);
            if (window.selectedCoverageRegion && regionList.indexOf(window.selectedCoverageRegion) === -1) {
                window.selectedCoverageRegion = null;
            }

            // Function to filter regions in the table
            function filterCoverageByRegion(selectedRegion) {
                window.selectedCoverageRegion = selectedRegion;

                // Update card styles to show selection
                const cards = document.querySelectorAll('.region-filter-card');
                cards.forEach(card => {
                    const cardRegion = card.getAttribute('data-region');
                    if (selectedRegion && cardRegion === selectedRegion) {
                        card.classList.add('ring-2', 'ring-blue-500', 'ring-offset-2');
                        card.style.transform = 'scale(1.02)';
                    } else {
                        card.classList.remove('ring-2', 'ring-blue-500', 'ring-offset-2');
                        card.style.transform = 'scale(1)';
                    }
                });

                // Show/hide region sections in the table
                const regionSections = document.querySelectorAll('.region-table-section');
                regionSections.forEach(section => {
                    const sectionRegion = section.getAttribute('data-region');
                    if (!selectedRegion || sectionRegion === selectedRegion) {
                        section.style.display = 'block';
                        // Auto-expand selected region
                        if (selectedRegion && sectionRegion === selectedRegion) {
                            const countriesDiv = section.querySelector('.region-countries');
                            if (countriesDiv) countriesDiv.classList.remove('hidden');
                            const chevron = section.querySelector('.chevron-icon');
                            if (chevron) chevron.classList.add('rotate-180');
                        }
                    } else {
                        section.style.display = 'none';
                    }
                });

                // Update the "Show All" button visibility
                const showAllBtn = document.getElementById('coverage-show-all-btn');
                if (showAllBtn) {
                    showAllBtn.style.display = selectedRegion ? 'inline-flex' : 'none';
                }
            }

            // Expose filter function globally
            window.filterCoverageByRegion = filterCoverageByRegion;

            // Modern cards for regional summary - using inline styles for color compatibility
            // Use 5 columns on large screens to fit all regions on one line
            let cardsHtml = '<div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3 mb-4">';
            Object.keys(byRegion).sort().forEach(region => {
                const countries = byRegion[region];
                const avg = Math.round(countries.reduce((s, c) => s + c.overallDisaggregation, 0) / countries.length);
                // Use inline gradient styles for color compatibility
                const headerGradient = avg >= 75 ? 'linear-gradient(90deg, #22c55e 0%, #16a34a 100%)' :
                                       avg >= 50 ? 'linear-gradient(90deg, #eab308 0%, #ca8a04 100%)' :
                                                   'linear-gradient(90deg, #ef4444 0%, #dc2626 100%)';
                const barColor = avg >= 75 ? '#22c55e' : avg >= 50 ? '#eab308' : '#ef4444';
                const isSelected = window.selectedCoverageRegion === region;
                const selectedClasses = isSelected ? 'ring-2 ring-blue-500 ring-offset-2' : '';
                const selectedStyle = isSelected ? 'transform: scale(1.02);' : '';
                cardsHtml += `
                    <div class="region-filter-card bg-white rounded-lg shadow-sm border border-gray-100 overflow-hidden hover:shadow-md transition-all cursor-pointer ${selectedClasses}"
                         data-region="${escapeHtml(region)}"
                         style="${selectedStyle}">
                        <div class="px-3 py-2" style="background: ${headerGradient};">
                            <h4 class="font-bold text-sm truncate" style="color: #ffffff;" title="${escapeHtml(region)}">${escapeHtml(region)}</h4>
                            <p class="text-xs" style="color: rgba(255,255,255,0.8);">${countries.length} countries</p>
                        </div>
                        <div class="p-3">
                            <div class="flex items-center justify-between mb-1">
                                <span class="text-xl font-bold text-gray-900">${avg}%</span>
                                <span class="text-xs text-gray-500">Avg</span>
                            </div>
                            <div class="w-full bg-gray-100 rounded-full h-1.5">
                                <div class="h-1.5 rounded-full transition-all duration-500" style="width: ${avg}%; background-color: ${barColor};"></div>
                            </div>
                        </div>
                    </div>
                `;
            });
            cardsHtml += '</div>';

            // Add "Show All" button (hidden by default)
            const showAllDisplay = window.selectedCoverageRegion ? 'inline-flex' : 'none';
            cardsHtml += `
                <div class="mb-4">
                    <button type="button"
                            id="coverage-show-all-btn"
                            class="inline-flex items-center px-3 py-1.5 text-sm font-medium text-blue-600 bg-blue-50 border border-blue-200 rounded-lg hover:bg-blue-100 transition-colors"
                            style="display: ${showAllDisplay};">
                        <i class="fas fa-times mr-2"></i>
                        Clear filter - Show all regions
                    </button>
                </div>
            `;

            if (regionalDiv) regionalDiv.innerHTML = cardsHtml;

            // Attach event listeners for regional filter cards (CSP-compliant)
            regionalDiv.querySelectorAll('.region-filter-card').forEach(function(card) {
                card.addEventListener('click', function() {
                    var cardRegion = this.getAttribute('data-region');
                    filterCoverageByRegion(window.selectedCoverageRegion === cardRegion ? null : cardRegion);
                });
            });

            // Attach event listener for "Show All" button
            var showAllBtn = document.getElementById('coverage-show-all-btn');
            if (showAllBtn) {
                showAllBtn.addEventListener('click', function() {
                    filterCoverageByRegion(null);
                });
            }

            // Group countries by region and create collapsible tables
            let tableHtml = '<div class="space-y-4">';

            Object.keys(byRegion).sort().forEach(region => {
                const regionCountries = byRegion[region].sort((a, b) => b.overallDisaggregation - a.overallDisaggregation);
                const regionAvg = Math.round(regionCountries.reduce((s, c) => s + c.overallDisaggregation, 0) / regionCountries.length);
                const headerGradient = regionAvg >= 75 ? 'linear-gradient(90deg, #22c55e 0%, #16a34a 100%)' :
                                       regionAvg >= 50 ? 'linear-gradient(90deg, #eab308 0%, #ca8a04 100%)' :
                                                         'linear-gradient(90deg, #ef4444 0%, #dc2626 100%)';
                const regionId = region.replace(/\s+/g, '-').toLowerCase();
                const isSelected = window.selectedCoverageRegion === region;
                const sectionDisplay = (!window.selectedCoverageRegion || isSelected) ? 'block' : 'none';
                // All tables expanded by default
                const countriesHidden = '';
                const chevronRotated = 'rotate-180';

                tableHtml += `
                    <div class="region-table-section bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden" data-region="${escapeHtml(region)}" style="display: ${sectionDisplay};">
                        <button type="button"
                                class="region-table-header w-full px-4 py-3 flex items-center justify-between cursor-pointer transition-all duration-200"
                                style="background: ${headerGradient};"
                                title="Click to expand/collapse">
                            <div class="flex items-center gap-3">
                                <i class="fas fa-layer-group text-xs" style="color: rgba(255,255,255,0.7);"></i>
                                <span class="font-semibold text-sm" style="color: #ffffff;">${escapeHtml(region)}</span>
                                <span class="text-xs px-2 py-0.5 rounded-full" style="background-color: rgba(255,255,255,0.2); color: #ffffff;">
                                    ${regionCountries.length} countries
                                </span>
                            </div>
                            <div class="flex items-center gap-3">
                                <span class="text-sm font-bold" style="color: #ffffff;">${regionAvg}% avg</span>
                                <i class="fas fa-chevron-down chevron-icon transition-transform duration-200 ${chevronRotated}" style="color: #ffffff;"></i>
                            </div>
                        </button>
                        <div class="region-countries ${countriesHidden}">
                            <table class="min-w-full">
                                <thead class="bg-gray-50 border-b border-gray-200">
                                    <tr>
                                        <th class="px-6 py-2 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Country</th>
                                        <th class="px-6 py-2 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Coverage</th>
                                        <th class="px-6 py-2 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider w-40">Progress</th>
                                    </tr>
                                </thead>
                                <tbody class="divide-y divide-gray-100">
                `;

                regionCountries.forEach((c, idx) => {
                    const badgeBg = c.overallDisaggregation >= 75 ? '#dcfce7' : c.overallDisaggregation >= 50 ? '#fef9c3' : '#fee2e2';
                    const badgeText = c.overallDisaggregation >= 75 ? '#166534' : c.overallDisaggregation >= 50 ? '#854d0e' : '#991b1b';
                    const barColor = c.overallDisaggregation >= 75 ? '#22c55e' : c.overallDisaggregation >= 50 ? '#eab308' : '#ef4444';
                    const rowBg = idx % 2 === 0 ? '#ffffff' : '#f9fafb';
                    const pct = Math.round(Number(c.overallDisaggregation) || 0);
                    tableHtml += `
                        <tr style="background-color: ${rowBg};">
                            <td class="px-6 py-3 whitespace-nowrap text-sm font-medium text-gray-900">${escapeHtml(c.label)}</td>
                            <td class="px-6 py-3 whitespace-nowrap">
                                <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold" style="background-color: ${badgeBg}; color: ${badgeText};">
                                    ${pct}%
                                </span>
                            </td>
                            <td class="px-6 py-3 whitespace-nowrap">
                                <div class="w-32 bg-gray-200 rounded-full h-2">
                                    <div class="h-2 rounded-full transition-all duration-500" style="width: ${pct}%; background-color: ${barColor};"></div>
                                </div>
                            </td>
                        </tr>
                    `;
                });

                tableHtml += `
                                </tbody>
                            </table>
                        </div>
                    </div>
                `;
            });

            tableHtml += '</div>';
            if (tableDiv) tableDiv.innerHTML = tableHtml;

            // Attach event listeners for table headers (CSP-compliant)
            tableDiv.querySelectorAll('.region-table-header').forEach(function(header) {
                // Click to expand/collapse
                header.addEventListener('click', function() {
                    var content = this.nextElementSibling;
                    var chevron = this.querySelector('.chevron-icon');
                    if (content) content.classList.toggle('hidden');
                    if (chevron) chevron.classList.toggle('rotate-180');
                });

                // Hover effects
                header.addEventListener('mouseenter', function() {
                    this.style.filter = 'brightness(1.1)';
                    this.style.transform = 'translateY(-1px)';
                });
                header.addEventListener('mouseleave', function() {
                    this.style.filter = 'brightness(1)';
                    this.style.transform = 'translateY(0)';
                });
            });

        }
    }

    // Expose functions globally
    global.processDisaggregationData = processDisaggregationData;
    global.updateDisaggregationUI = updateDisaggregationUI;
    global.renderDisaggSubtabCharts = renderDisaggSubtabCharts;

})(typeof window !== 'undefined' ? window : this);
