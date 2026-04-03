/**
 * Data Exploration - Disaggregation Analysis
 * Port of Website processEnhancedDisaggregatedData + Chart.js rendering for Backoffice.
 * Expects: processDisaggregationData(data, formItems, countries) to be called from explore_data.html
 * and updateDisaggregationUI(), renderDisaggSubtabCharts(subtab) to be called when tab/subtab is shown.
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
    const VOLUNTEERING_PATTERNS = ['volunteers', 'volunteer', 'voluntary', 'community workers', 'active volunteers', 'trained volunteers', 'registered volunteers'].map(function(p) { return p.toLowerCase(); });
    const STAFF_PATTERNS = ['staff', 'employees', 'personnel', 'workers', 'paid staff', 'professional staff', 'trained staff', 'registered staff'].map(function(p) { return p.toLowerCase(); });

    const CHART_COLORS = ['#2563eb', '#dc2626', '#16a34a', '#ca8a04', '#9333ea', '#0891b2', '#ea580c', '#4b5563'];

    function getChartConstructor() {
        var C = (typeof globalThis !== 'undefined' && globalThis.Chart) || (typeof window !== 'undefined' && window.Chart);
        if (typeof C === 'function') return C;
        if (C && typeof C.default === 'function') return C.default;
        return null;
    }

    function formatSexCategory(sex) {
        var map = { 'male': 'Male', 'female': 'Female', 'men': 'Male', 'women': 'Female', 'boys': 'Male', 'girls': 'Female', 'other': 'Other', 'unknown': UNKNOWN };
        return map[(sex || '').toLowerCase()] || (String(sex).charAt(0).toUpperCase() + String(sex).slice(1));
    }

    function formatAgeGroup(age) {
        var ageMap = {
            'child': '0-17 years', 'children': '0-17 years', 'infant': '0-2 years', 'adult': '18-64 years', 'adults': '18-64 years',
            'elderly': '65+ years', 'elder': '65+ years', 'senior': '65+ years', 'under_5': '0-4 years', 'under_18': '0-17 years',
            'over_65': '65+ years', '0_4': '0-4 years', '5_17': '5-17 years', '18_59': '18-59 years', '60_plus': '60+ years', 'unknown': UNKNOWN
        };
        var clean = String(age).toLowerCase().replace(/[^a-z0-9_]/g, '');
        if (ageMap[clean]) return ageMap[clean];
        if (clean.indexOf('_') !== -1) {
            var parts = clean.split('_');
            if (parts.length === 2 && (parts[1] === 'plus' || parts[1] === 'over')) return parts[0] + '+ years';
            if (parts.length === 2) return parts[0] + '-' + parts[1] + ' years';
        }
        return String(age).charAt(0).toUpperCase() + String(age).slice(1).replace(/_/g, ' ');
    }

    function extractYearFromPeriod(periodName) {
        if (!periodName) return 0;
        var m = String(periodName).match(/\b(20\d{2})\b/);
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

    function processDisaggregationData(data, formItems, countries) {
        if (!data || !Array.isArray(data)) {
            return getEmptyProcessed();
        }
        var formItemsMap = new Map();
        var formItemsNameMap = new Map();
        var indicatorIdToNameMap = new Map();
        var i, fi, bid, bname;
        for (i = 0; i < (formItems || []).length; i++) {
            fi = formItems[i];
            bid = (fi.bank_details && fi.bank_details.id) || fi.indicator_bank_id;
            bname = (fi.bank_details && fi.bank_details.name) || fi.indicator_bank_name || fi.label;
            if (bid && fi.id) {
                formItemsMap.set(fi.id, parseInt(bid, 10));
                formItemsNameMap.set(fi.id, bname || UNKNOWN_INDICATOR);
                indicatorIdToNameMap.set(parseInt(bid, 10), bname || UNKNOWN_INDICATOR);
            }
        }
        var countriesMap = new Map();
        var countryNameToRegion = {};
        (countries || []).forEach(function(c) {
            if (c.id) countriesMap.set(c.id, { name: c.name || UNKNOWN, region: c.region || 'Other' });
            if (c.name) countryNameToRegion[c.name] = c.region || 'Other';
        });

        var filteredData = [];
        var validUnits = ['people', 'person', 'volunteers', 'volunteer', 'staff', 'employees', 'employee', 'personnel'];
        for (i = 0; i < data.length; i++) {
            var item = data[i];
            var hasDisagg = item.disaggregation_data && item.disaggregation_data.values && Object.keys(item.disaggregation_data.values).length > 0;
            if (hasDisagg) {
                filteredData.push(item);
                continue;
            }
            var unit = (item.form_item_info && item.form_item_info.bank_details && item.form_item_info.bank_details.unit) ||
                (item.form_item_info && item.form_item_info.unit) || item.unit || (item.bank_details && item.bank_details.unit);
            if (unit && validUnits.indexOf(String(unit).toLowerCase().trim()) !== -1) filteredData.push(item);
            else if (item.value != null || item.answer_value != null) filteredData.push(item);
        }

        var result = {
            totalReached: 0,
            byCountry: {},
            bySex: {},
            byAge: {},
            bySexAge: {},
            trends: {},
            byIndicator: {},
            countryDisaggregation: {},
            womenInLeadership: { leadership: {}, volunteering: {}, staff: {}, trends: {} }
        };

        for (i = 0; i < filteredData.length; i++) {
            item = filteredData[i];
            var countryInfo = item.country_info;
            var formItemInfo = item.form_item_info;
            var bankDetails = formItemInfo && formItemInfo.bank_details;
            var country = (countryInfo && countryInfo.name) || (item.country_id && countriesMap.has(item.country_id) ? countriesMap.get(item.country_id).name : null) || UNKNOWN;
            var period = item.period_name || UNKNOWN;
            var indicatorId = (bankDetails && bankDetails.id) || (formItemInfo && formItemInfo.indicator_bank_id) || item.indicator_bank_id || item.indicator_id;
            if (!indicatorId && item.form_item_id && formItemsMap.has(item.form_item_id)) indicatorId = formItemsMap.get(item.form_item_id);
            var indicator = (bankDetails && bankDetails.name) || (formItemInfo && formItemInfo.indicator_bank_name) || item.indicator_bank_name || formItemInfo && formItemInfo.label;
            if (!indicator || indicator === UNKNOWN_INDICATOR) {
                if (item.form_item_id && formItemsNameMap.has(item.form_item_id)) indicator = formItemsNameMap.get(item.form_item_id);
                else if (indicatorId && indicatorIdToNameMap.has(indicatorId)) indicator = indicatorIdToNameMap.get(indicatorId);
                else indicator = UNKNOWN_INDICATOR;
            }
            var disaggregationData = item.disaggregation_data;
            var hasDisaggregation = disaggregationData && disaggregationData.values;
            var mode = disaggregationData && disaggregationData.mode;
            var isGoverningBoard = indicatorId === GOVERNING_BOARD_INDICATOR_ID || indicatorId == GOVERNING_BOARD_INDICATOR_ID;
            var indLower = (indicator || '').toLowerCase();
            var isVolunteering = (indicatorId === VOLUNTEERS_INDICATOR_ID || indicatorId == VOLUNTEERS_INDICATOR_ID) || VOLUNTEERING_PATTERNS.some(function(p) { return indLower.indexOf(p) !== -1; });
            var isStaff = (indicatorId === STAFF_INDICATOR_ID || indicatorId == STAFF_INDICATOR_ID) || STAFF_PATTERNS.some(function(p) { return indLower.indexOf(p) !== -1; });
            var canProcessGender = hasDisaggregation && (mode === 'sex' || mode === 'sex_age');

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

            if (!hasDisaggregation || !disaggregationData.values) {
                result.countryDisaggregation[country].onlyTotal += 1;
                result.trends[period].onlyTotal += 1;
                var totalVal = parseFloat(item.answer_value || item.value) || 0;
                result.countryDisaggregation[country].totalValue += totalVal;
                result.byCountry[country].total += totalVal;
                result.byCountry[country].count += 1;
                result.trends[period].total += totalVal;
                result.trends[period].count += 1;
                result.byIndicator[indicator].total += totalVal;
                result.byIndicator[indicator].count += 1;
                result.totalReached += totalVal;
                continue;
            }

            var values = disaggregationData.values;
            var actualValues = values.direct || values;
            var itemTotal = 0;
            for (var k in actualValues) { if (Object.prototype.hasOwnProperty.call(actualValues, k)) itemTotal += parseFloat(actualValues[k]) || 0; }
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
                var v = parseFloat(val) || 0;
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
                for (k in actualValues) {
                    if (!Object.prototype.hasOwnProperty.call(actualValues, k)) continue;
                    var sexFormatted = formatSexCategory(k);
                    var val = actualValues[k];
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
                for (k in actualValues) {
                    if (!Object.prototype.hasOwnProperty.call(actualValues, k)) continue;
                    addToResult(null, formatAgeGroup(k), null, actualValues[k]);
                }
            } else if (mode === 'sex_age') {
                for (k in actualValues) {
                    if (!Object.prototype.hasOwnProperty.call(actualValues, k)) continue;
                    var parts = k.split('_');
                    var sexPart = formatSexCategory(parts[0]);
                    var agePart = formatAgeGroup(parts.slice(1).join('_'));
                    var sexAgePart = sexPart + ' - ' + agePart;
                    var v = parseFloat(actualValues[k]) || 0;
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

        var yearSet = new Set();
        filteredData.forEach(function(it) { var y = extractYearFromPeriod(it.period_name); if (y > 0) yearSet.add(y); });
        var availableYears = Array.from(yearSet).sort(function(a, b) { return b - a; });

        var byCountryArr = Object.entries(result.byCountry).map(function(entry) {
            var label = entry[0], d = entry[1];
            return { label: label, value: d.count > 0 ? Math.round(d.total / d.count) : 0, total: d.total, count: d.count };
        }).sort(function(a, b) { return b.value - a.value; }).slice(0, 15);

        var bySexArr = Object.entries(result.bySex).map(function(entry) { return { label: entry[0], value: Math.round(entry[1]) }; }).sort(function(a, b) { return b.value - a.value; });
        var byAgeArr = Object.entries(result.byAge).map(function(entry) { return { label: entry[0], value: Math.round(entry[1]) }; }).sort(function(a, b) { return sortAgeGroups(a.label, b.label); });
        var bySexAgeArr = Object.entries(result.bySexAge).map(function(entry) { return { label: entry[0], value: Math.round(entry[1]) }; }).sort(function(a, b) { return b.value - a.value; }).slice(0, 20);

        var trendsArr = Object.entries(result.trends).map(function(entry) {
            var label = entry[0], d = entry[1];
            var itemsWithDisagg = d.totalItems - d.onlyTotal;
            return {
                label: label,
                value: d.count > 0 ? Math.round(d.total / d.count) : 0,
                total: d.total,
                count: d.count,
                ageDisaggregationPercentage: d.totalItems > 0 ? Math.round((d.ageDisaggregated / d.totalItems) * 100) : 0,
                overallDisaggregationPercentage: d.totalItems > 0 ? Math.round((itemsWithDisagg / d.totalItems) * 100) : 0
            };
        }).sort(function(a, b) { return a.label.localeCompare(b.label); });

        var byIndicatorArr = Object.entries(result.byIndicator).map(function(entry) {
            var label = entry[0], d = entry[1];
            return {
                label: label,
                value: Math.round(d.total),
                average: d.count > 0 ? Math.round(d.total / d.count) : 0,
                count: d.count,
                id: d.id,
                bySex: Object.entries(d.bySex).map(function(e) { return { label: e[0], value: Math.round(e[1]) }; }),
                byAge: Object.entries(d.byAge).map(function(e) { return { label: e[0], value: Math.round(e[1]) }; }),
                bySexAge: Object.entries(d.bySexAge).map(function(e) { return { label: e[0], value: Math.round(e[1]) }; })
            };
        }).filter(function(ind) {
            var hasSex = ind.bySex.length > 0 && ind.bySex.some(function(item) { return item.value > 0; });
            var hasAge = ind.byAge.length > 0 && ind.byAge.some(function(item) { return item.value > 0; });
            return hasSex || hasAge;
        }).sort(function(a, b) { return b.value - a.value; });

        var countryDisaggArr = Object.entries(result.countryDisaggregation).map(function(entry) {
            var label = entry[0], d = entry[1];
            var itemsWithAny = d.totalItems - d.onlyTotal;
            return {
                label: label,
                region: countryNameToRegion[label] || 'Other',
                totalItems: d.totalItems,
                onlyTotal: d.onlyTotal,
                totalValue: Math.round(d.totalValue),
                overallDisaggregation: d.totalItems > 0 ? Math.round((itemsWithAny / d.totalItems) * 100) : 0
            };
        }).sort(function(a, b) { return b.overallDisaggregation - a.overallDisaggregation; });

        var leadershipArr = Object.entries(result.womenInLeadership.leadership).map(function(entry) {
            var d = entry[1];
            return { label: entry[0], female: d.female, male: d.male, total: d.total, femalePercentage: d.total > 0 ? Math.round((d.female / d.total) * 100) : 0 };
        }).sort(function(a, b) { return b.femalePercentage - a.femalePercentage; });
        var volunteeringArr = Object.entries(result.womenInLeadership.volunteering).map(function(entry) {
            var d = entry[1];
            return { label: entry[0], female: d.female, male: d.male, total: d.total, femalePercentage: d.total > 0 ? Math.round((d.female / d.total) * 100) : 0 };
        }).sort(function(a, b) { return b.femalePercentage - a.femalePercentage; });
        var staffArr = Object.entries(result.womenInLeadership.staff).map(function(entry) {
            var d = entry[1];
            return { label: entry[0], female: d.female, male: d.male, total: d.total, femalePercentage: d.total > 0 ? Math.round((d.female / d.total) * 100) : 0 };
        }).sort(function(a, b) { return b.femalePercentage - a.femalePercentage; });

        // Women in Leadership was not collected before 2017; use chart-specific year range
        var WOMEN_LEADERSHIP_MIN_YEAR = '2017';
        var trendsWomenArr = Object.entries(result.womenInLeadership.trends)
            .filter(function(entry) { var label = entry[0], d = entry[1]; return label >= WOMEN_LEADERSHIP_MIN_YEAR && (d.leadershipTotal > 0 || d.volunteeringTotal > 0 || d.staffTotal > 0); })
            .map(function(entry) {
                var label = entry[0], d = entry[1];
                return {
                    label: label,
                    leadershipPercentage: d.leadershipTotal > 0 ? Math.round((d.leadershipFemale / d.leadershipTotal) * 100) : 0,
                    volunteeringPercentage: d.volunteeringTotal > 0 ? Math.round((d.volunteeringFemale / d.volunteeringTotal) * 100) : 0,
                    staffPercentage: d.staffTotal > 0 ? Math.round((d.staffFemale / d.staffTotal) * 100) : 0
                };
            })
            .sort(function(a, b) { return a.label.localeCompare(b.label); });

        var comparison = [
            { label: 'Leadership Roles', value: Object.values(result.womenInLeadership.leadership).reduce(function(s, d) { return s + d.female; }, 0), total: Object.values(result.womenInLeadership.leadership).reduce(function(s, d) { return s + d.total; }, 0) },
            { label: 'Volunteering', value: Object.values(result.womenInLeadership.volunteering).reduce(function(s, d) { return s + d.female; }, 0), total: Object.values(result.womenInLeadership.volunteering).reduce(function(s, d) { return s + d.total; }, 0) },
            { label: 'Staff', value: Object.values(result.womenInLeadership.staff).reduce(function(s, d) { return s + d.female; }, 0), total: Object.values(result.womenInLeadership.staff).reduce(function(s, d) { return s + d.total; }, 0) }
        ].map(function(item) { return { label: item.label, value: item.value, total: item.total, percentage: item.total > 0 ? Math.round((item.value / item.total) * 100) : 0 }; });

        return {
            totalReached: result.totalReached,
            availableYears: availableYears,
            byCountry: byCountryArr,
            bySex: bySexArr,
            byAge: byAgeArr,
            bySexAge: bySexAgeArr,
            trends: trendsArr,
            byIndicator: byIndicatorArr,
            countryDisaggregation: countryDisaggArr,
            womenInLeadership: {
                leadership: leadershipArr,
                volunteering: volunteeringArr,
                staff: staffArr,
                trends: trendsWomenArr,
                comparison: comparison
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
            womenInLeadership: { leadership: [], volunteering: [], staff: [], trends: [], comparison: [] }
        };
    }

    var chartInstances = {};

    function destroyCharts(keys) {
        keys = keys || Object.keys(chartInstances);
        keys.forEach(function(key) {
            if (chartInstances[key]) {
                chartInstances[key].destroy();
                chartInstances[key] = null;
            }
        });
    }

    function makeChart(canvasId, type, dataArr, options) {
        var canvas = document.getElementById(canvasId);
        if (!canvas) return;
        if (chartInstances[canvasId]) { chartInstances[canvasId].destroy(); chartInstances[canvasId] = null; }
        var labels = dataArr.map(function(d) { return d.label; });
        var values = dataArr.map(function(d) { return d.value; });
        var cfg = {
            type: type,
            data: {
                labels: labels,
                datasets: [{
                    label: options && options.label ? options.label : 'Value',
                    data: values,
                    backgroundColor: type === 'pie' ? CHART_COLORS.slice(0, labels.length) : CHART_COLORS[0],
                    borderColor: CHART_COLORS[0],
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: type === 'pie' } },
                scales: (type !== 'pie' && type !== 'doughnut') ? { y: { beginAtZero: true } } : undefined
            }
        };
        if (type === 'line' && options && options.tension !== undefined) cfg.data.datasets[0].tension = options.tension;
        var ChartCtor = getChartConstructor();
        if (!ChartCtor) {
            console.warn('Chart.js not loaded; charts will not render.');
            return;
        }
        chartInstances[canvasId] = new ChartCtor(canvas, cfg);
    }

    function updateDisaggregationUI() {
        var p = window.disaggProcessedData;
        if (!p) return;
        var statAvgDisagg = document.getElementById('stat-avg-disagg');
        var statAvgAge = document.getElementById('stat-avg-age');
        var statWomenLead = document.getElementById('stat-women-leadership');
        var statWomenVol = document.getElementById('stat-women-volunteering');
        var statWomenStaff = document.getElementById('stat-women-staff');
        var avgDisagg = 0;
        var avgAge = 0;
        if (p.countryDisaggregation && p.countryDisaggregation.length > 0) {
            avgDisagg = Math.round(p.countryDisaggregation.reduce(function(s, c) { return s + c.overallDisaggregation; }, 0) / p.countryDisaggregation.length);
            avgAge = p.trends && p.trends.length > 0 ? Math.round(p.trends.reduce(function(s, t) { return s + (t.ageDisaggregationPercentage || 0); }, 0) / p.trends.length) : 0;
        }
        var leadPct = 0, volPct = 0, staffPct = 0;
        if (p.womenInLeadership && p.womenInLeadership.comparison && p.womenInLeadership.comparison.length > 0) {
            var comp = p.womenInLeadership.comparison;
            leadPct = (comp[0] && comp[0].percentage) || 0;
            volPct = (comp[1] && comp[1].percentage) || 0;
            staffPct = (comp[2] && comp[2].percentage) || 0;
        }
        if (statAvgDisagg) statAvgDisagg.textContent = avgDisagg + '%';
        if (statAvgAge) statAvgAge.textContent = avgAge + '%';
        if (statWomenLead) statWomenLead.textContent = leadPct + '%';
        if (statWomenVol) statWomenVol.textContent = volPct + '%';
        if (statWomenStaff) statWomenStaff.textContent = staffPct + '%';
        if (window.currentDisaggSubtab && window.renderDisaggSubtabCharts) window.renderDisaggSubtabCharts(window.currentDisaggSubtab);
    }

    function renderDisaggSubtabCharts(subtab) {
        var p = window.disaggProcessedData;
        if (!p) return;
        var chartType = (document.getElementById('disagg-chart-type') && document.getElementById('disagg-chart-type').value) || 'bar';
        var type = chartType === 'pie' ? 'pie' : chartType === 'line' ? 'line' : 'bar';

        if (subtab === 'overview') {
            destroyCharts(['chart-overview-countries', 'chart-overview-sex']);
            makeChart('chart-overview-countries', 'bar', (p.byCountry || []).slice(0, 8), {});
            makeChart('chart-overview-sex', 'pie', (p.bySex || []).slice(0, 10), {});
            document.getElementById('overview-no-data').classList.toggle('hidden', (p.byCountry && p.byCountry.length > 0) || (p.bySex && p.bySex.length > 0));
        } else if (subtab === 'by-indicator') {
            destroyCharts(['chart-by-indicator']);
            var indData = (p.byIndicator || []).slice(0, 15).map(function(i) { return { label: i.label.length > 30 ? i.label.substring(0, 27) + '...' : i.label, value: i.value }; });
            makeChart('chart-by-indicator', 'bar', indData, {});
            document.getElementById('by-indicator-no-data').classList.toggle('hidden', indData.length > 0);
        } else if (subtab === 'women-leadership') {
            destroyCharts(['chart-women-comparison', 'chart-women-by-country', 'chart-women-trends', 'chart-trends-governing', 'chart-trends-staff', 'chart-trends-volunteers']);
            var comp = p.womenInLeadership && p.womenInLeadership.comparison ? p.womenInLeadership.comparison : [];
            makeChart('chart-women-comparison', 'bar', comp.map(function(c) { return { label: c.label, value: c.percentage }; }), {});
            var lead = (p.womenInLeadership && p.womenInLeadership.leadership) ? p.womenInLeadership.leadership.slice(0, 15) : [];
            makeChart('chart-women-by-country', 'bar', lead.map(function(c) { return { label: c.label, value: c.femalePercentage }; }), {});
            var trends = (p.womenInLeadership && p.womenInLeadership.trends) ? p.womenInLeadership.trends : [];
            makeChart('chart-women-trends', 'line', trends.map(function(t) { return { label: t.label, value: t.volunteeringPercentage }; }), { tension: 0.3 });
            if (trends.length > 0) {
                makeChart('chart-trends-governing', 'line', trends.map(function(t) { return { label: t.label, value: t.leadershipPercentage }; }), { tension: 0.3 });
                makeChart('chart-trends-staff', 'line', trends.map(function(t) { return { label: t.label, value: t.staffPercentage || 0 }; }), { tension: 0.3 });
                makeChart('chart-trends-volunteers', 'line', trends.map(function(t) { return { label: t.label, value: t.volunteeringPercentage }; }), { tension: 0.3 });
            }
            document.getElementById('women-leadership-no-data').classList.toggle('hidden', comp.length > 0 || lead.length > 0 || trends.length > 0);
        } else if (subtab === 'sex-age') {
            destroyCharts(['chart-by-sex', 'chart-by-age', 'chart-by-sex-age']);
            makeChart('chart-by-sex', type, (p.bySex || []).slice(0, 10), {});
            makeChart('chart-by-age', type, (p.byAge || []).slice(0, 12), {});
            makeChart('chart-by-sex-age', type, (p.bySexAge || []).slice(0, 15), {});
            document.getElementById('sex-age-no-data').classList.toggle('hidden', (p.bySex && p.bySex.length > 0) || (p.byAge && p.byAge.length > 0));
        } else if (subtab === 'by-country') {
            destroyCharts(['chart-by-country']);
            makeChart('chart-by-country', type, (p.byCountry || []).slice(0, 20), {});
            document.getElementById('by-country-no-data').classList.toggle('hidden', (p.byCountry && p.byCountry.length > 0));
        } else if (subtab === 'country-coverage') {
            var regionalDiv = document.getElementById('coverage-regional-summary');
            var tableDiv = document.getElementById('coverage-countries-table');
            var noData = document.getElementById('country-coverage-no-data');
            if (regionalDiv) regionalDiv.innerHTML = '';
            if (tableDiv) tableDiv.innerHTML = '';
            if (!p.countryDisaggregation || p.countryDisaggregation.length === 0) {
                if (noData) noData.classList.remove('hidden');
                return;
            }
            if (noData) noData.classList.add('hidden');
            var list = p.countryDisaggregation;
            var byRegion = {};
            list.forEach(function(c) {
                var region = c.region || 'Other';
                if (!byRegion[region]) byRegion[region] = [];
                byRegion[region].push(c);
            });
            Object.keys(byRegion).sort().forEach(function(region) {
                var countries = byRegion[region];
                var avg = Math.round(countries.reduce(function(s, c) { return s + c.overallDisaggregation; }, 0) / countries.length);
                var card = document.createElement('div');
                card.className = 'bg-gray-50 rounded-lg p-4 border-l-4 border-blue-500 mb-4';
                card.innerHTML = '<div class="font-semibold text-gray-900">' + escapeHtml(region) + '</div><div class="text-sm text-gray-600">' + escapeHtml(String(countries.length)) + ' countries</div><div class="mt-2 text-lg font-bold">' + escapeHtml(String(avg)) + '%</div><div class="w-full bg-gray-200 rounded-full h-2 mt-2"><div class="bg-blue-500 h-2 rounded-full" style="width:' + avg + '%"></div></div>';
                regionalDiv.appendChild(card);
            });
            var table = '<table class="min-w-full divide-y divide-gray-200"><thead><tr><th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Country</th><th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Coverage %</th><th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Bar</th></tr></thead><tbody>';
            list.forEach(function(c) {
                var badgeClass = c.overallDisaggregation >= 75 ? 'bg-green-100 text-green-800' : c.overallDisaggregation >= 50 ? 'bg-yellow-100 text-yellow-800' : 'bg-red-100 text-red-800';
                table += '<tr class="border-t"><td class="px-4 py-2">' + escapeHtml(c.label) + '</td><td class="px-4 py-2"><span class="px-2 py-1 text-xs font-bold rounded ' + badgeClass + '">' + escapeHtml(String(c.overallDisaggregation)) + '%</span></td><td class="px-4 py-2"><div class="w-24 bg-gray-200 rounded h-2"><div class="bg-blue-500 h-2 rounded" style="width:' + c.overallDisaggregation + '%"></div></div></td></tr>';
            });
            table += '</tbody></table>';
            tableDiv.innerHTML = table;
        }
    }

    global.processDisaggregationData = processDisaggregationData;
    global.updateDisaggregationUI = updateDisaggregationUI;
    global.renderDisaggSubtabCharts = renderDisaggSubtabCharts;

})(typeof window !== 'undefined' ? window : this);
