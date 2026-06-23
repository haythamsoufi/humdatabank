/**
 * Pure data processing for Explore Data disaggregation analysis.
 *
 * This file intentionally has no DOM or chart dependencies so it can be tested
 * with Node and reused by the ApexCharts renderer.
 */
(function(root, factory) {
    if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        const api = factory();
        root.ExploreDataAnalysisCore = api;
        root.processDisaggregationData = api.processDisaggregationData;
    }
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
    'use strict';

    const UNKNOWN = 'Unknown';
    const UNKNOWN_INDICATOR = 'Unknown indicator';
    const WOMEN_LEADERSHIP_MIN_YEAR = 2017;
    const PEOPLE_UNITS = new Set([
        'people', 'person', 'persons', 'individuals', 'beneficiaries',
        'volunteers', 'volunteer', 'staff', 'employees', 'employee', 'personnel'
    ]);
    const STANDARD_DISAGG_MODES = new Set(['sex', 'age', 'sex_age']);
    const WOMEN_INDICATORS = {
        leadership: {
            id: 722,
            label: 'Leadership Roles',
            fallbackPatterns: [/\bgoverning\s+board\b/i, /\bleadership\b/i]
        },
        volunteering: {
            id: 724,
            label: 'Volunteering',
            fallbackPatterns: [/\bvolunteers?\b/i, /\bvoluntary\b/i, /\bcommunity\s+workers?\b/i]
        },
        staff: {
            id: 727,
            label: 'Staff',
            fallbackPatterns: [/\bstaff\b/i, /\bemployees?\b/i, /\bpersonnel\b/i, /\bpaid\s+staff\b/i]
        }
    };

    function toNumber(value) {
        if (value === null || value === undefined) return 0;
        if (typeof value === 'number') return Number.isFinite(value) ? value : 0;
        if (typeof value === 'string') {
            const cleaned = value.replace(/,/g, '').trim();
            if (!cleaned || cleaned.toLowerCase() === 'null') return 0;
            const n = Number(cleaned);
            return Number.isFinite(n) ? n : 0;
        }
        return 0;
    }

    function asId(value) {
        const n = parseInt(value, 10);
        return Number.isFinite(n) ? n : null;
    }

    function percentage(numerator, denominator) {
        return denominator > 0 ? Math.round((numerator / denominator) * 100) : 0;
    }

    function formatSexCategory(sex) {
        const map = {
            male: 'Male',
            female: 'Female',
            men: 'Male',
            women: 'Female',
            boys: 'Male',
            girls: 'Female',
            other: 'Other',
            unknown: UNKNOWN
        };
        const clean = String(sex || '').toLowerCase().trim();
        return map[clean] || (String(sex || UNKNOWN).charAt(0).toUpperCase() + String(sex || UNKNOWN).slice(1));
    }

    function formatAgeGroup(age) {
        const ageMap = {
            child: '0-17 years',
            children: '0-17 years',
            infant: '0-2 years',
            adult: '18-64 years',
            adults: '18-64 years',
            elderly: '65+ years',
            elder: '65+ years',
            senior: '65+ years',
            under_5: '0-4 years',
            under_18: '0-17 years',
            over_65: '65+ years',
            '0_4': '0-4 years',
            '5_17': '5-17 years',
            '18_59': '18-59 years',
            '60_plus': '60+ years',
            unknown: UNKNOWN
        };
        const clean = String(age || '').toLowerCase().replace(/[^a-z0-9_]/g, '');
        if (ageMap[clean]) return ageMap[clean];
        if (clean.indexOf('_') !== -1) {
            const parts = clean.split('_');
            if (parts.length === 2 && (parts[1] === 'plus' || parts[1] === 'over')) return parts[0] + '+ years';
            if (parts.length === 2) return parts[0] + '-' + parts[1] + ' years';
        }
        return String(age || UNKNOWN).charAt(0).toUpperCase() + String(age || UNKNOWN).slice(1).replace(/_/g, ' ');
    }

    function extractYearFromPeriod(periodName) {
        if (!periodName) return 0;
        const match = String(periodName).match(/\b(20\d{2})\b/);
        return match ? parseInt(match[1], 10) : 0;
    }

    function sortAgeGroups(a, b) {
        function order(ageGroup) {
            const ag = String(ageGroup || '');
            if (ag.indexOf('0-2') !== -1 || ag.indexOf('0-4') !== -1) return 1;
            if (ag.indexOf('5-17') !== -1) return 2;
            if (ag.indexOf('18-59') !== -1 || ag.indexOf('18-64') !== -1) return 3;
            if (ag.indexOf('60+') !== -1 || ag.indexOf('65+') !== -1) return 4;
            if (ag.toLowerCase().indexOf('unknown') !== -1) return 5;
            return 99;
        }
        return order(a) - order(b);
    }

    function extractDisabilityMeta(payload) {
        if (!payload || typeof payload !== 'object') return null;
        const rawValues = payload.values && typeof payload.values === 'object' ? payload.values : null;
        if (!rawValues) return null;
        const values = rawValues.direct && typeof rawValues.direct === 'object' ? rawValues.direct : rawValues;
        const disability = values.disability;
        if (!disability || typeof disability !== 'object') return null;
        if (!Object.prototype.hasOwnProperty.call(disability, 'disaggregated_by_disability')) return null;
        return {
            answered: true,
            disaggregated: disability.disaggregated_by_disability === true,
            washingtonGroupCompliant: disability.washington_group_compliant === true
        };
    }

    function normalizeDisaggregationPayload(payload) {
        if (!payload || typeof payload !== 'object') return null;
        const mode = String(payload.mode || '').toLowerCase();
        const rawValues = payload.values && typeof payload.values === 'object' ? payload.values : null;
        if (!rawValues || Object.keys(rawValues).length === 0) return null;
        const values = rawValues.direct && typeof rawValues.direct === 'object' ? rawValues.direct : rawValues;
        const normalizedValues = {};
        Object.keys(values).forEach(key => {
            if (key === 'disability') return;
            const numeric = toNumber(values[key]);
            if (numeric !== 0) normalizedValues[key] = numeric;
        });
        if (Object.keys(normalizedValues).length === 0) return null;
        return { mode, values: normalizedValues };
    }

    function isDisabilityApplicableRow(row, formItemInfo, bankDetails) {
        if (formItemInfo && formItemInfo.allow_disability_questions) return true;
        if (extractDisabilityMeta(row.disaggregation_data)) return true;
        return PEOPLE_UNITS.has(getUnit(row, formItemInfo, bankDetails));
    }

    function rowCountsAsDisaggregated(hasDisagg, disabilityMeta) {
        return !!hasDisagg || !!disabilityMeta;
    }

    function getFormItemInfo(row, formItemsMap) {
        if (row.form_item_info) return row.form_item_info;
        if (!row.form_item_id) return null;
        return formItemsMap.get(row.form_item_id) || formItemsMap.get(asId(row.form_item_id)) || null;
    }

    function getBankDetails(row, formItemInfo) {
        return (formItemInfo && formItemInfo.bank_details) || row.bank_details || null;
    }

    function getUnit(row, formItemInfo, bankDetails) {
        return String(
            (bankDetails && bankDetails.unit) ||
            (formItemInfo && formItemInfo.unit) ||
            row.unit ||
            ''
        ).toLowerCase().trim();
    }

    function getAllowedDisaggregationOptions(formItemInfo) {
        const options = formItemInfo && formItemInfo.allowed_disaggregation_options;
        if (Array.isArray(options)) return options;
        if (options && typeof options === 'object') return Object.keys(options).filter(key => options[key]);
        if (typeof options === 'string' && options.trim()) return [options.trim()];
        return [];
    }

    function isIndicatorRow(row, formItemInfo, bankDetails) {
        if (bankDetails && bankDetails.id) return true;
        if (row.indicator_bank_id || row.indicator_id) return true;
        return !!(formItemInfo && (formItemInfo.bank_details || formItemInfo.indicator_bank_id || formItemInfo.is_indicator));
    }

    function isAnalysisEligibleRow(row, formItemsMap) {
        const formItemInfo = getFormItemInfo(row, formItemsMap || new Map());
        const bankDetails = getBankDetails(row, formItemInfo);
        const disagg = normalizeDisaggregationPayload(row.disaggregation_data);
        if (!isIndicatorRow(row, formItemInfo, bankDetails)) return false;
        if (extractDisabilityMeta(row.disaggregation_data)) return true;
        if (disagg && (STANDARD_DISAGG_MODES.has(disagg.mode) || disagg.mode === 'matrix')) return true;
        if (PEOPLE_UNITS.has(getUnit(row, formItemInfo, bankDetails))) return true;
        return getAllowedDisaggregationOptions(formItemInfo).length > 0;
    }

    function getEffectiveNumericValue(row) {
        if (row.num_value !== null && row.num_value !== undefined) return toNumber(row.num_value);
        return toNumber(row.answer_value !== undefined ? row.answer_value : row.value);
    }

    function getIndicatorMeta(row, formItemsMap, formItemsNameMap, indicatorIdToNameMap) {
        const formItemInfo = getFormItemInfo(row, formItemsMap);
        const bankDetails = getBankDetails(row, formItemInfo);
        let indicatorId = asId(
            (bankDetails && bankDetails.id) ||
            (formItemInfo && formItemInfo.indicator_bank_id) ||
            row.indicator_bank_id ||
            row.indicator_id
        );
        const formItemKey = row.form_item_id ? (formItemsMap.has(row.form_item_id) ? row.form_item_id : asId(row.form_item_id)) : null;
        if (!indicatorId && formItemKey && formItemsMap.has(formItemKey)) {
            const mapped = formItemsMap.get(formItemKey);
            indicatorId = asId(mapped && mapped.indicator_bank_id);
        }
        let indicator = (
            (bankDetails && bankDetails.name) ||
            (formItemInfo && formItemInfo.indicator_bank_name) ||
            row.indicator_bank_name ||
            (formItemInfo && formItemInfo.label)
        );
        if (!indicator || indicator === UNKNOWN_INDICATOR) {
            if (formItemKey && formItemsNameMap.has(formItemKey)) indicator = formItemsNameMap.get(formItemKey);
            else if (indicatorId && indicatorIdToNameMap.has(indicatorId)) indicator = indicatorIdToNameMap.get(indicatorId);
            else indicator = UNKNOWN_INDICATOR;
        }
        return { id: indicatorId, label: indicator };
    }

    function getWomenCategory(indicatorId, indicatorLabel) {
        const label = String(indicatorLabel || '');
        for (const category of Object.keys(WOMEN_INDICATORS)) {
            const config = WOMEN_INDICATORS[category];
            if (indicatorId === config.id) return category;
            if (!indicatorId && config.fallbackPatterns.some(pattern => pattern.test(label))) return category;
        }
        return null;
    }

    function increment(map, key, amount) {
        map[key] = (map[key] || 0) + amount;
    }

    function ensureCoverageBucket(collection, key, region) {
        if (!collection[key]) {
            collection[key] = {
                totalItems: 0,
                disaggregatedItems: 0,
                totalOnly: 0,
                missingItems: 0,
                sexDisaggregated: 0,
                ageDisaggregated: 0,
                sexAgeDisaggregated: 0,
                matrixDisaggregated: 0,
                totalValue: 0,
                region: region || 'Other'
            };
        }
        return collection[key];
    }

    function ensureWomenBucket(collection, key) {
        if (!collection[key]) collection[key] = { female: 0, male: 0, total: 0 };
        return collection[key];
    }

    function applyWomenValue(result, category, country, period, sex, value) {
        if (!category) return;
        const countryBucket = ensureWomenBucket(result.womenInLeadership[category], country);
        if (!result.womenInLeadership.trends[period]) {
            result.womenInLeadership.trends[period] = {
                leadershipFemale: 0, leadershipMale: 0, leadershipTotal: 0,
                volunteeringFemale: 0, volunteeringMale: 0, volunteeringTotal: 0,
                staffFemale: 0, staffMale: 0, staffTotal: 0
            };
        }
        const trendBucket = result.womenInLeadership.trends[period];
        if (trendBucket.leadershipMale === undefined) trendBucket.leadershipMale = 0;
        if (trendBucket.volunteeringMale === undefined) trendBucket.volunteeringMale = 0;
        if (trendBucket.staffMale === undefined) trendBucket.staffMale = 0;

        if (sex === 'Female') {
            countryBucket.female += value;
            trendBucket[category + 'Female'] += value;
        } else if (sex === 'Male') {
            countryBucket.male += value;
            trendBucket[category + 'Male'] += value;
        }
        countryBucket.total += value;
        trendBucket[category + 'Total'] += value;
    }

    function toCoverageArray(entries, regionLookup) {
        return Object.entries(entries).map(([label, data]) => {
            const disaggregatedItems = data.disaggregatedItems || 0;
            return {
                label,
                region: data.region || (regionLookup && regionLookup[label]) || 'Other',
                value: percentage(disaggregatedItems, data.totalItems),
                totalItems: data.totalItems,
                disaggregatedItems,
                totalOnly: data.totalOnly || 0,
                onlyTotal: data.totalOnly || 0,
                missingItems: data.missingItems || 0,
                totalValue: Math.round(data.totalValue || 0),
                sexDisaggregation: percentage(data.sexDisaggregated || 0, data.totalItems),
                ageDisaggregation: percentage(data.ageDisaggregated || 0, data.totalItems),
                sexAgeDisaggregation: percentage(data.sexAgeDisaggregated || 0, data.totalItems),
                matrixDisaggregation: percentage(data.matrixDisaggregated || 0, data.totalItems),
                overallDisaggregation: percentage(disaggregatedItems, data.totalItems)
            };
        }).sort((a, b) => b.overallDisaggregation - a.overallDisaggregation || b.totalItems - a.totalItems);
    }

    function getEmptyProcessed() {
        return {
            coverageSummary: {
                eligibleRows: 0,
                disaggregatedRows: 0,
                totalOnlyRows: 0,
                missingRows: 0,
                sexDisaggregatedRows: 0,
                ageDisaggregatedRows: 0,
                sexAgeDisaggregatedRows: 0,
                matrixDisaggregatedRows: 0,
                overallDisaggregationPercentage: 0,
                sexCoveragePercentage: 0,
                ageCoveragePercentage: 0,
                sexAgeCoveragePercentage: 0
            },
            availableYears: [],
            coverageStatus: [],
            byCountry: [],
            bySex: [],
            byAge: [],
            bySexAge: [],
            trends: [],
            byIndicator: [],
            countryDisaggregation: [],
            countryDisaggregationByYear: {},
            countryUniverse: [],
            womenInLeadership: { leadership: [], volunteering: [], staff: [], trends: [], comparison: [] }
        };
    }

    function processDisaggregationData(data, formItems, countries) {
        if (!Array.isArray(data) || data.length === 0) return getEmptyProcessed();

        const formItemsMap = new Map();
        const formItemsNameMap = new Map();
        const indicatorIdToNameMap = new Map();
        (formItems || []).forEach(item => {
            if (!item || !item.id) return;
            formItemsMap.set(item.id, item);
            const bankId = (item.bank_details && item.bank_details.id) || item.indicator_bank_id;
            const bankName = (item.bank_details && item.bank_details.name) || item.indicator_bank_name || item.label;
            if (bankId) {
                const parsedBankId = asId(bankId);
                formItemsNameMap.set(item.id, bankName || UNKNOWN_INDICATOR);
                if (parsedBankId) indicatorIdToNameMap.set(parsedBankId, bankName || UNKNOWN_INDICATOR);
            }
        });

        const countriesMap = new Map();
        const countryNameToRegion = {};
        (countries || []).forEach(country => {
            if (!country) return;
            if (country.id) countriesMap.set(country.id, { name: country.name || UNKNOWN, region: country.region || 'Other' });
            if (country.name) countryNameToRegion[country.name] = country.region || 'Other';
        });
        const countryUniverse = (countries || [])
            .filter(country => country && country.name)
            .map(country => ({
                label: country.name || UNKNOWN,
                region: country.region || 'Other'
            }))
            .sort((a, b) => a.region.localeCompare(b.region) || a.label.localeCompare(b.label));

        const result = {
            coverageSummary: getEmptyProcessed().coverageSummary,
            byCountry: {},
            byIndicator: {},
            bySex: {},
            byAge: {},
            bySexAge: {},
            trends: {},
            countryDisaggregationByYear: {},
            womenInLeadership: { leadership: {}, volunteering: {}, staff: {}, trends: {} }
        };
        const yearSet = new Set();

        data.forEach(row => {
            if (!row || !isAnalysisEligibleRow(row, formItemsMap)) return;

            const formItemInfo = getFormItemInfo(row, formItemsMap);
            const countryInfo = row.country_info || (row.country_id && countriesMap.get(row.country_id)) || null;
            const country = (countryInfo && countryInfo.name) || UNKNOWN;
            const region = (countryInfo && countryInfo.region) || countryNameToRegion[country] || 'Other';
            const period = row.period_name || UNKNOWN;
            const year = extractYearFromPeriod(period);
            const indicator = getIndicatorMeta(row, formItemsMap, formItemsNameMap, indicatorIdToNameMap);
            const disagg = normalizeDisaggregationPayload(row.disaggregation_data);
            const disabilityMeta = extractDisabilityMeta(row.disaggregation_data);
            const isMissing = row.is_missing === true || row.data_status === 'missing';
            const hasDisagg = !!disagg;
            const isDisaggregated = rowCountsAsDisaggregated(hasDisagg, disabilityMeta);

            if (year > 0) yearSet.add(year);
            const countryBucket = ensureCoverageBucket(result.byCountry, country, region);
            const indicatorBucket = ensureCoverageBucket(result.byIndicator, indicator.label, null);
            indicatorBucket.id = indicator.id;
            const trendBucket = ensureCoverageBucket(result.trends, period, null);
            const yearBucket = year > 0 ? ensureCoverageBucket(result.countryDisaggregationByYear[year] || (result.countryDisaggregationByYear[year] = {}), country, region) : null;
            const buckets = [countryBucket, indicatorBucket, trendBucket].concat(yearBucket ? [yearBucket] : []);

            result.coverageSummary.eligibleRows += 1;
            buckets.forEach(bucket => { bucket.totalItems += 1; });

            if (isMissing) {
                result.coverageSummary.missingRows += 1;
                buckets.forEach(bucket => { bucket.missingItems += 1; });
                return;
            }

            if (!isDisaggregated) {
                const numeric = getEffectiveNumericValue(row);
                result.coverageSummary.totalOnlyRows += 1;
                buckets.forEach(bucket => {
                    bucket.totalOnly += 1;
                    bucket.totalValue += numeric;
                });
                return;
            }

            result.coverageSummary.disaggregatedRows += 1;
            buckets.forEach(bucket => { bucket.disaggregatedItems += 1; });

            if (!hasDisagg) {
                return;
            }

            const values = disagg.values;
            const itemTotal = Object.keys(values).reduce((sum, key) => sum + toNumber(values[key]), 0);
            buckets.forEach(bucket => { bucket.totalValue += itemTotal; });

            if (disagg.mode === 'sex') {
                result.coverageSummary.sexDisaggregatedRows += 1;
                buckets.forEach(bucket => { bucket.sexDisaggregated += 1; });
            } else if (disagg.mode === 'age') {
                result.coverageSummary.ageDisaggregatedRows += 1;
                buckets.forEach(bucket => { bucket.ageDisaggregated += 1; });
            } else if (disagg.mode === 'sex_age') {
                result.coverageSummary.sexDisaggregatedRows += 1;
                result.coverageSummary.ageDisaggregatedRows += 1;
                result.coverageSummary.sexAgeDisaggregatedRows += 1;
                buckets.forEach(bucket => {
                    bucket.sexDisaggregated += 1;
                    bucket.ageDisaggregated += 1;
                    bucket.sexAgeDisaggregated += 1;
                });
            } else if (disagg.mode === 'matrix') {
                result.coverageSummary.matrixDisaggregatedRows += 1;
                buckets.forEach(bucket => { bucket.matrixDisaggregated += 1; });
            }

            const womenCategory = getWomenCategory(indicator.id, indicator.label);
            Object.keys(values).forEach(key => {
                const value = toNumber(values[key]);
                if (value === 0) return;
                if (disagg.mode === 'sex') {
                    const sex = formatSexCategory(key);
                    increment(result.bySex, sex, value);
                    applyWomenValue(result, womenCategory, country, period, sex, value);
                } else if (disagg.mode === 'age') {
                    increment(result.byAge, formatAgeGroup(key), value);
                } else if (disagg.mode === 'sex_age') {
                    const parts = String(key).split('_');
                    const sex = formatSexCategory(parts[0]);
                    const age = formatAgeGroup(parts.slice(1).join('_'));
                    increment(result.bySex, sex, value);
                    increment(result.byAge, age, value);
                    increment(result.bySexAge, sex + ' - ' + age, value);
                    applyWomenValue(result, womenCategory, country, period, sex, value);
                }
            });
        });

        const summary = result.coverageSummary;
        summary.overallDisaggregationPercentage = percentage(summary.disaggregatedRows, summary.eligibleRows);
        summary.sexCoveragePercentage = percentage(summary.sexDisaggregatedRows, summary.eligibleRows);
        summary.ageCoveragePercentage = percentage(summary.ageDisaggregatedRows, summary.eligibleRows);
        summary.sexAgeCoveragePercentage = percentage(summary.sexAgeDisaggregatedRows, summary.eligibleRows);

        const coverageStatus = [
            { label: 'Reported with disaggregation', value: summary.disaggregatedRows },
            { label: 'Reported total only', value: summary.totalOnlyRows },
            { label: 'Missing', value: summary.missingRows }
        ].filter(item => item.value > 0);

        const bySex = Object.entries(result.bySex).map(([label, value]) => ({ label, value: Math.round(value) })).sort((a, b) => b.value - a.value);
        const byAge = Object.entries(result.byAge).map(([label, value]) => ({ label, value: Math.round(value) })).sort((a, b) => sortAgeGroups(a.label, b.label));
        const bySexAge = Object.entries(result.bySexAge).map(([label, value]) => ({ label, value: Math.round(value) })).sort((a, b) => b.value - a.value).slice(0, 20);
        const countryDisaggregation = toCoverageArray(result.byCountry, countryNameToRegion);
        const byIndicator = toCoverageArray(result.byIndicator, {}).map(item => ({
            ...item,
            id: result.byIndicator[item.label] && result.byIndicator[item.label].id
        }));
        const trends = toCoverageArray(result.trends, {}).sort((a, b) => extractYearFromPeriod(a.label) - extractYearFromPeriod(b.label) || a.label.localeCompare(b.label));

        const leadership = Object.entries(result.womenInLeadership.leadership).map(([label, d]) => ({
            label, female: d.female, male: d.male, total: d.total, femalePercentage: percentage(d.female, d.female + d.male)
        })).sort((a, b) => b.femalePercentage - a.femalePercentage || b.total - a.total);
        const volunteering = Object.entries(result.womenInLeadership.volunteering).map(([label, d]) => ({
            label, female: d.female, male: d.male, total: d.total, femalePercentage: percentage(d.female, d.female + d.male)
        })).sort((a, b) => b.femalePercentage - a.femalePercentage || b.total - a.total);
        const staff = Object.entries(result.womenInLeadership.staff).map(([label, d]) => ({
            label, female: d.female, male: d.male, total: d.total, femalePercentage: percentage(d.female, d.female + d.male)
        })).sort((a, b) => b.femalePercentage - a.femalePercentage || b.total - a.total);
        const womenTrends = Object.entries(result.womenInLeadership.trends)
            .filter(([period, d]) => extractYearFromPeriod(period) >= WOMEN_LEADERSHIP_MIN_YEAR && (d.leadershipTotal > 0 || d.volunteeringTotal > 0 || d.staffTotal > 0))
            .map(([label, d]) => ({
                label,
                leadershipPercentage: percentage(d.leadershipFemale, d.leadershipFemale + d.leadershipMale),
                volunteeringPercentage: percentage(d.volunteeringFemale, d.volunteeringFemale + d.volunteeringMale),
                staffPercentage: percentage(d.staffFemale, d.staffFemale + d.staffMale)
            }))
            .sort((a, b) => extractYearFromPeriod(a.label) - extractYearFromPeriod(b.label) || a.label.localeCompare(b.label));
        const comparison = Object.keys(WOMEN_INDICATORS).map(category => {
            const values = Object.values(result.womenInLeadership[category]);
            const female = values.reduce((sum, item) => sum + item.female, 0);
            const male = values.reduce((sum, item) => sum + item.male, 0);
            const total = values.reduce((sum, item) => sum + item.total, 0);
            const knownTotal = female + male;
            return {
                label: WOMEN_INDICATORS[category].label,
                value: female,
                knownTotal,
                total,
                percentage: percentage(female, knownTotal)
            };
        }).filter(item => item.total > 0);

        return {
            coverageSummary: summary,
            availableYears: Array.from(yearSet).sort((a, b) => b - a),
            coverageStatus,
            byCountry: countryDisaggregation,
            bySex,
            byAge,
            bySexAge,
            trends,
            byIndicator,
            countryDisaggregation,
            countryDisaggregationByYear: result.countryDisaggregationByYear,
            countryUniverse,
            womenInLeadership: { leadership, volunteering, staff, trends: womenTrends, comparison }
        };
    }

    return {
        PEOPLE_UNITS,
        WOMEN_INDICATORS,
        extractYearFromPeriod,
        extractDisabilityMeta,
        formatAgeGroup,
        formatSexCategory,
        getEmptyProcessed,
        isAnalysisEligibleRow,
        isDisabilityApplicableRow,
        normalizeDisaggregationPayload,
        processDisaggregationData,
        rowCountsAsDisaggregated
    };
});
