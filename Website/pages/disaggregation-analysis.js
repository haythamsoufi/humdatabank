import Head from 'next/head';
import { useEffect, useState, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useTranslation } from '../lib/useTranslation';
import { getDataWithRelated, getFilterOptions, processDisaggregatedData, getCountriesList, FDRS_TEMPLATE_ID } from '../lib/apiService';
import { downloadCSV, downloadPNG, generateFilename } from '../lib/downloadUtils';
import MultiChart from '../components/MultiChart';
import Image from 'next/image';

// Info Icon SVG Component
const InfoIcon = ({ className = "w-4 h-4" }) => (
  <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" className={className}>
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);

// Tooltip Component
const TrendTooltip = ({ data, isVisible, position, t }) => {
  if (!isVisible || !data) return null;

  const hasPlaceholderData = data.length === 1 && data[0]?.isPlaceholder;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.8 }}
      className="fixed z-50 bg-white border border-gray-200 rounded-lg shadow-xl p-4 max-w-[320px]"
      style={{
        left: position.x,
        top: position.y,
        transform: 'translate(0, 0)', // No transform needed - position is already calculated
        pointerEvents: 'none' // Prevent tooltip from interfering with mouse events
      }}
    >
      <div className="text-sm font-semibold text-ngodb-navy mb-2">
        {hasPlaceholderData ? t('disaggregationAnalysis.tooltip.trendData') : t('disaggregationAnalysis.tooltip.fiveYearTrends')}
      </div>
      <div className="text-xs text-ngodb-gray-500 mb-3">
        {hasPlaceholderData
          ? t('disaggregationAnalysis.tooltip.historicalTrendNotAvailable')
          : t('disaggregationAnalysis.tooltip.historicalTrendsDescription')
        }
      </div>

      {hasPlaceholderData ? (
        <div className="text-center py-4">
          <div className="text-ngodb-gray-400 text-sm">
            <svg className="w-8 h-8 mx-auto mb-2 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            <div>{t('disaggregationAnalysis.tooltip.noHistoricalData')}</div>
            <div className="text-xs mt-1">{t('disaggregationAnalysis.tooltip.onlyCurrentPeriod')}</div>
          </div>
        </div>
      ) : (
        <>
          <div className="space-y-2">
            {data.map((item, index) => (
              <div key={index} className="flex justify-between items-center">
                <span className="text-xs text-ngodb-gray-600 font-medium">{item.year}</span>
                <span className="text-xs font-bold text-ngodb-navy">{item.value}%</span>
                <div className="w-16 bg-ngodb-gray-200 rounded-full h-1.5">
                  <div
                    className="h-1.5 rounded-full transition-all duration-300"
                    style={{
                      width: `${Math.max(item.value, 2)}%`, // Minimum 2% width for visibility
                      backgroundColor: item.value >= 50 ? '#10B981' : item.value >= 30 ? '#F59E0B' : '#EF4444'
                    }}
                  ></div>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-3 pt-2 border-t border-gray-200">
            <div className="flex justify-between text-xs">
              <span className="text-ngodb-gray-600">{t('disaggregationAnalysis.tooltip.average')}</span>
              <span className="font-medium text-ngodb-navy">
                {Math.round(data.reduce((sum, item) => sum + item.value, 0) / data.length)}%
              </span>
            </div>
          </div>
        </>
      )}
    </motion.div>
  );
};

export default function DisaggregationAnalysisPage() {
  const { t } = useTranslation();

  // State management
  const [rawData, setRawData] = useState([]);
  const [processedData, setProcessedData] = useState({
    totalReached: 0,
    availableYears: [],
    byCountry: [],
    bySex: [],
    byAge: [],
    bySexAge: [],
    trends: [],
    byIndicator: [],
    countryDisaggregation: [],
    womenInLeadership: {
      leadership: [],
      volunteering: [],
      staff: [],
      trends: [],
      comparison: []
    }
  });
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [countryRegions, setCountryRegions] = useState({});
  const [countriesMap, setCountriesMap] = useState(new Map());

  // Download state
  const [isDownloadingCSV, setIsDownloadingCSV] = useState(false);
  const [isDownloadingPNG, setIsDownloadingPNG] = useState(false);

  // Filter state
  const [filters, setFilters] = useState({
    countries: [],
    selectedCountries: [],
    periods: [],
    selectedPeriod: '',
    indicators: [],
    selectedIndicator: ''
  });

  // UI state
  const [activeTab, setActiveTab] = useState('overview');
  const [chartType, setChartType] = useState('bar');
  const [expandedFilters, setExpandedFilters] = useState(false);
  const [selectedYear, setSelectedYear] = useState(null);

  // Tooltip state
  const [tooltipState, setTooltipState] = useState({
    isVisible: false,
    data: null,
    position: { x: 0, y: 0 }
  });

  // Throttling for mouse move events
  const tooltipThrottleRef = useRef(null);

  // Load filter options and country regions on component mount - optimized with concurrent loading
  useEffect(() => {
    const loadInitialData = async () => {
      try {
        // Load filter options and country data concurrently
        const [options, countries] = await Promise.all([
          getFilterOptions(),
          getCountriesList()
        ]);

        // Set filters
        setFilters(prev => ({
          ...prev,
          countries: options.countries,
          periods: options.periods,
          indicators: options.indicators
        }));

        // Set country regions
        const regionMap = {};
        const countryIdMap = new Map();
        countries.forEach(country => {
          regionMap[country.name] = country.region;
          if (country.id) {
            countryIdMap.set(country.id, {
              name: country.name || t('fallbacks.unknown'),
              iso2: country.iso2 || country.code || '',
              iso3: country.iso3 || '',
              region: country.region || 'Other'
            });
          }
        });
        console.log(`📊 Loaded ${countries.length} countries, ${countryIdMap.size} in countriesMap`);
        setCountryRegions(regionMap);
        setCountriesMap(countryIdMap);

      } catch (error) {
        console.error('Error loading initial data:', error);
      }
    };

    loadInitialData();
  }, []);

  // Enhanced data processing function
  const processEnhancedDisaggregatedData = async (data, yearFilter = selectedYear, countryMap = countriesMap) => {
    // Validate input data
    if (!data || !Array.isArray(data)) {
      console.error('processEnhancedDisaggregatedData: Invalid data input', data);
      // Return default structure if data is invalid
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
        womenInLeadership: {
          leadership: [],
          volunteering: [],
          staff: [],
          trends: [],
          comparison: []
        }
      };
    }

    try {
      // Use the countriesMap passed in (loaded at component level)
      // Fallback to empty Map if not provided (will result in "Unknown" countries)
      const countriesMapToUse = (countryMap && countryMap.size > 0) ? countryMap : (countriesMap.size > 0 ? countriesMap : new Map());

      // Load form_items to resolve form_item_id to indicator_bank_id and indicator name
      let formItemsMap = new Map(); // form_item_id -> indicator_bank_id
      let formItemsNameMap = new Map(); // form_item_id -> indicator_name
      let indicatorIdToNameMap = new Map(); // indicator_bank_id -> indicator_name
      try {
        // Try to get form_items from the data store or API
        if (typeof window === 'undefined') {
          // Server-side: use dataStore directly
          const { getFormItemsFromStore } = await import('../lib/dataStore');
          const formItems = await getFormItemsFromStore({ template_id: FDRS_TEMPLATE_ID });
          formItems.forEach(fi => {
            const indicatorId = fi.bank_details?.id || fi.indicator_bank_id;
            const indicatorName = fi.bank_details?.name ||
                                 fi.indicator_bank_name ||
                                 fi.label ||
                                 t('fallbacks.unknownIndicator');

            if (indicatorId && fi.id) {
              formItemsMap.set(fi.id, parseInt(indicatorId));
              formItemsNameMap.set(fi.id, indicatorName);
              indicatorIdToNameMap.set(parseInt(indicatorId), indicatorName);
            }
          });
        } else {
          // Client-side: use API route
          try {
            const response = await fetch('/api/data?related=all&returnFullResponse=true');
            if (response.ok) {
              const result = await response.json();
              const formItems = result.form_items || [];
              formItems.forEach(fi => {
                const indicatorId = fi.bank_details?.id || fi.indicator_bank_id;
                const indicatorName = fi.bank_details?.name ||
                                     fi.indicator_bank_name ||
                                     fi.label ||
                                     t('fallbacks.unknownIndicator');

                if (indicatorId && fi.id) {
                  formItemsMap.set(fi.id, parseInt(indicatorId));
                  formItemsNameMap.set(fi.id, indicatorName);
                  indicatorIdToNameMap.set(parseInt(indicatorId), indicatorName);
                }
              });
            }
          } catch (error) {
            console.warn('Failed to load form_items for indicator resolution:', error);
          }
        }
        console.log(`Loaded ${formItemsMap.size} form_items for indicator resolution (${indicatorIdToNameMap.size} unique indicators)`);
      } catch (error) {
        console.warn('Failed to load form_items for indicator resolution:', error);
      }

      // Processing data - optimized for performance with large datasets

      // Filter to only include indicators with unit "People" (case-insensitive)
      // Use for loop instead of filter() for better performance with large arrays
      const filteredData = [];
      const dataLength = data.length;

    for (let i = 0; i < dataLength; i++) {
      const item = data[i];

      // Check if item has disaggregation data
      const hasDisaggregation = item.disaggregation_data &&
                                 item.disaggregation_data.values &&
                                 Object.keys(item.disaggregation_data.values).length > 0;

      // Include ALL items (both disaggregated and non-disaggregated) for complete totals
      // This ensures:
      // 1. Complete totals (including non-disaggregated data)
      // 2. Accurate disaggregation percentages (disaggregated vs total)
      // 3. Proper "onlyTotal" counts

      if (hasDisaggregation) {
        // Item has disaggregation data - include it
        filteredData.push(item);
        continue;
      }

      // Item doesn't have disaggregation - still include it for totals
      // But apply unit filter to focus on people-related indicators
      const unit = item.form_item_info?.bank_details?.unit ||
                   item.form_item_info?.unit ||
                   item.unit ||
                   item.bank_details?.unit;

      if (unit) {
        // Fast lowercase comparison - cache the result
        const unitStr = String(unit);
        const unitLower = unitStr.toLowerCase();
        const unitTrimmed = unitLower.trim();

        // Include items with unit "People", "Person", "Volunteers", "Staff", "Employees" etc.
        const validUnits = ['people', 'person', 'volunteers', 'volunteer', 'staff', 'employees', 'employee', 'personnel'];
        if (validUnits.includes(unitTrimmed)) {
          filteredData.push(item);
        }
      } else {
        // If no unit info, still include if it has a value (might be missing unit metadata)
        // This ensures we don't lose data due to missing metadata
        const hasValue = item.value != null || item.num_value != null || item.answer_value != null;
        if (hasValue) {
          filteredData.push(item);
        }
      }
    }

    // Debug: Track units found
    const unitCounts = {};
    for (let i = 0; i < dataLength; i++) {
      const item = data[i];
      const unit = item.form_item_info?.bank_details?.unit ||
                   item.form_item_info?.unit ||
                   item.unit;
      if (unit) {
        const unitKey = String(unit).toLowerCase().trim();
        unitCounts[unitKey] = (unitCounts[unitKey] || 0) + 1;
      }
    }

    console.log('📊 Unit Filter Debug:', {
      totalItems: data.length,
      filteredItems: filteredData.length,
      unitCounts: Object.entries(unitCounts).sort((a, b) => b[1] - a[1]).slice(0, 10),
      validUnits: ['people', 'person', 'volunteers', 'volunteer', 'staff', 'employees', 'employee', 'personnel']
    });

    const result = {
      totalReached: 0,
      byCountry: {},
      bySex: {},
      byAge: {},
      bySexAge: {},
      trends: {},
      byIndicator: {},
      countryDisaggregation: {},
      womenInLeadership: {
        leadership: {},
        volunteering: {},
        staff: {},
        trends: {},
        comparison: {}
      }
    };

    // CRITICAL: Only use the specific "Number of people on the National Society Governing Board" indicator (bank ID 722)
    const GOVERNING_BOARD_INDICATOR_ID = 722;
    const VOLUNTEERS_INDICATOR_ID = 724;
    const STAFF_INDICATOR_ID = 727;

    // Volunteering indicator patterns (broader search for volunteers) - pre-lowercased for performance
    const volunteeringIndicators = [
      'volunteers', 'volunteer', 'voluntary', 'community workers', 'volunteers active', 'active volunteers',
      'volunteer staff', 'community volunteer', 'trained volunteers', 'registered volunteers'
    ].map(p => p.toLowerCase());

    // Staff indicator patterns - pre-lowercased for performance
    const staffIndicators = [
      'staff', 'employees', 'personnel', 'workers', 'employees active', 'active staff',
      'paid staff', 'professional staff', 'trained staff', 'registered staff'
    ].map(p => p.toLowerCase());

    // Debug: Log what we're looking for
    console.log('🔍 Starting indicator processing:', {
      GOVERNING_BOARD_INDICATOR_ID,
      VOLUNTEERS_INDICATOR_ID,
      STAFF_INDICATOR_ID,
      volunteeringPatterns: volunteeringIndicators,
      staffPatterns: staffIndicators,
      totalItemsToProcess: filteredData.length
    });

    // Debug counters for tracking indicator matching
    const debugCounters = {
      totalItems: 0,
      itemsWithDisaggregation: 0,
      governingBoardMatches: 0,
      volunteerIdMatches: 0,
      volunteerNameMatches: 0,
      staffIdMatches: 0,
      staffNameMatches: 0,
      volunteerDataProcessed: 0,
      staffDataProcessed: 0
    };

    // Debug: Track unique indicator IDs and names we encounter
    const encounteredIndicators = new Map(); // Map<indicatorId, {name, count}>
    const sampleIndicatorData = [];

    // Process each data item (using filtered data) - use for loop for better performance
    const filteredLength = filteredData.length;
    for (let idx = 0; idx < filteredLength; idx++) {
      const item = filteredData[idx];

      // Cache frequently accessed properties to avoid repeated property lookups
      const countryInfo = item.country_info;
      const formItemInfo = item.form_item_info;
      const bankDetails = formItemInfo?.bank_details;

      // Resolve country name from country_id if country_info is not available
      let country = t('fallbacks.unknown');
      if (countryInfo?.name) {
        country = countryInfo.name;
      } else if (item.country_id && countriesMapToUse.has(item.country_id)) {
        country = countriesMapToUse.get(item.country_id).name;
      } else if (item.country_id) {
        // Try to find by ID in countries list
        const countryData = Array.from(countriesMap.values()).find(c => c.id === item.country_id);
        if (countryData) {
          country = countryData.name;
        }
      }

      const period = item.period_name || t('fallbacks.unknown');

      // Resolve indicator_bank_id from form_item_id if not directly available
      let indicatorId = bankDetails?.id ||
                         formItemInfo?.indicator_bank_id ||
                         item.indicator_bank_id ||
                         item.indicator_id ||
                         item.bank_id;

      // If indicatorId not found, try to resolve from form_item_id using formItemsMap
      if (!indicatorId && item.form_item_id && formItemsMap.has(item.form_item_id)) {
        indicatorId = formItemsMap.get(item.form_item_id);
      }

      // Extract indicator name from the correct nested path - use formItemsNameMap for local store data
      let indicator = bankDetails?.name ||
                       formItemInfo?.indicator_bank_name ||
                       item.indicator_bank_name ||
                       item.indicator_name ||
                       formItemInfo?.label;

      // If indicator name not found, try to resolve from form_item_id or indicator_id
      if (!indicator || indicator === t('fallbacks.unknownIndicator')) {
        if (item.form_item_id && formItemsNameMap.has(item.form_item_id)) {
          indicator = formItemsNameMap.get(item.form_item_id);
        } else if (indicatorId && indicatorIdToNameMap.has(indicatorId)) {
          indicator = indicatorIdToNameMap.get(indicatorId);
        } else {
          indicator = t('fallbacks.unknownIndicator');
        }
      }

      // Cache disaggregation data early to avoid repeated property access throughout loop
      const disaggregationData = item.disaggregation_data;
      const hasDisaggregation = !!disaggregationData?.values;
      const mode = disaggregationData?.mode;

      // Debug: Track encountered indicators (sample first 100 unique indicators)
      if (encounteredIndicators.size < 100 && indicatorId) {
        const key = String(indicatorId);
        if (!encounteredIndicators.has(key)) {
          encounteredIndicators.set(key, {
            id: indicatorId,
            name: indicator,
            type: typeof indicatorId,
            hasDisaggregation: hasDisaggregation,
            mode: mode,
            rawIndicatorId: indicatorId,
            rawBankDetails: bankDetails ? { id: bankDetails.id, name: bankDetails.name } : null
          });

          // Also check if indicator name contains volunteer/staff keywords (case insensitive)
          const indicatorLower = (indicator || '').toLowerCase();
          if (indicatorLower.includes('volunteer') || indicatorLower.includes('staff') ||
              indicatorLower.includes('personnel') || indicatorLower.includes('employee')) {
            sampleIndicatorData.push({
              indicatorId,
              indicator,
              indicatorLower,
              bankDetails: bankDetails ? {
                id: bankDetails.id,
                name: bankDetails.name,
                type: typeof bankDetails.id
              } : null,
              formItemInfo: formItemInfo ? {
                indicator_bank_id: formItemInfo.indicator_bank_id,
                indicator_bank_name: formItemInfo.indicator_bank_name,
                label: formItemInfo.label
              } : null,
              itemKeys: Object.keys(item).filter(k => k.includes('indicator') || k.includes('bank')),
              itemSample: {
                indicator_bank_id: item.indicator_bank_id,
                indicator_bank_name: item.indicator_bank_name,
                indicator_id: item.indicator_id,
                indicator_name: item.indicator_name,
                bank_id: item.bank_id
              },
              hasDisaggregation,
              mode
            });
          }
        }
      }

      // Check if this is the governing board indicator
      const isGoverningBoardIndicator = indicatorId === GOVERNING_BOARD_INDICATOR_ID ||
                                       indicatorId == GOVERNING_BOARD_INDICATOR_ID; // Loose comparison for string/number

      // Debug: Count items
      debugCounters.totalItems++;
      if (hasDisaggregation) {
        debugCounters.itemsWithDisaggregation++;
      }
      if (isGoverningBoardIndicator) {
        debugCounters.governingBoardMatches++;
      }

      // Check indicator ID first (more reliable than name matching)
      // Use String conversion to handle both string and number IDs
      const indicatorIdStr = String(indicatorId || '');
      const volunteerIdStr = String(VOLUNTEERS_INDICATOR_ID);
      const staffIdStr = String(STAFF_INDICATOR_ID);

      const isVolunteeringIndicatorById = indicatorId === VOLUNTEERS_INDICATOR_ID ||
                                         indicatorId == VOLUNTEERS_INDICATOR_ID ||
                                         indicatorIdStr === volunteerIdStr;
      const isStaffIndicatorById = indicatorId === STAFF_INDICATOR_ID ||
                                   indicatorId == STAFF_INDICATOR_ID ||
                                   indicatorIdStr === staffIdStr;

      // Check indicator name patterns (fallback for indicators not using the standard IDs)
      // IMPORTANT: Check ALL items, not just those with disaggregation, to find indicators
      let indicatorLower = (indicator || '').toLowerCase().trim();
      let isVolunteeringIndicatorByName = false;
      let isStaffIndicatorByName = false;

      // Check name patterns for all items
      if (indicatorLower) {
        isVolunteeringIndicatorByName = volunteeringIndicators.some(pattern => indicatorLower.includes(pattern));
        isStaffIndicatorByName = staffIndicators.some(pattern => indicatorLower.includes(pattern));

        // Also check for exact matches or close matches
        if (!isVolunteeringIndicatorByName && indicatorLower) {
          // Check if indicator name starts with or contains volunteer keywords more precisely
          isVolunteeringIndicatorByName = indicatorLower.includes('volunteer') &&
                                         !indicatorLower.includes('staff') && // Exclude "volunteer staff"
                                         indicatorLower.length < 100; // Sanity check
        }

        if (!isStaffIndicatorByName && indicatorLower) {
          // Check if indicator name contains staff keywords but not volunteer
          isStaffIndicatorByName = (indicatorLower.includes('staff') ||
                                   indicatorLower.includes('employee') ||
                                   indicatorLower.includes('personnel')) &&
                                  !indicatorLower.includes('volunteer') &&
                                  indicatorLower.length < 100;
        }
      }

      // Combine ID and name matches
      const isVolunteeringIndicator = isVolunteeringIndicatorById || isVolunteeringIndicatorByName;
      const isStaffIndicator = isStaffIndicatorById || isStaffIndicatorByName;

      // IMPORTANT: Only process if we have disaggregation data with sex information
      // This ensures we only count indicators that can provide gender breakdown
      const canProcessGenderData = hasDisaggregation && (mode === 'sex' || mode === 'sex_age');

      // Debug: Track matches
      if (isVolunteeringIndicatorById) {
        debugCounters.volunteerIdMatches++;
      }
      if (isVolunteeringIndicatorByName) {
        debugCounters.volunteerNameMatches++;
        // Debug: Log first few name matches
        if (debugCounters.volunteerNameMatches <= 3) {
          console.log('✅ Volunteer indicator matched by NAME:', {
            indicatorId,
            indicator,
            indicatorLower,
            hasDisaggregation,
            mode
          });
        }
      }
      if (isStaffIndicatorById) {
        debugCounters.staffIdMatches++;
      }
      if (isStaffIndicatorByName) {
        debugCounters.staffNameMatches++;
        // Debug: Log first few name matches
        if (debugCounters.staffNameMatches <= 3) {
          console.log('✅ Staff indicator matched by NAME:', {
            indicatorId,
            indicator,
            indicatorLower,
            hasDisaggregation,
            mode
          });
        }
      }

      // Debug: Log first few matches for troubleshooting
      if ((isVolunteeringIndicator || isStaffIndicator) && debugCounters.volunteerDataProcessed + debugCounters.staffDataProcessed < 5) {
        console.log('🔍 Indicator Match Debug:', {
          indicator,
          indicatorId,
          indicatorLower,
          isVolunteeringIndicator,
          isVolunteeringIndicatorById,
          isVolunteeringIndicatorByName,
          isStaffIndicator,
          isStaffIndicatorById,
          isStaffIndicatorByName,
          hasDisaggregation,
          mode,
          country,
          canProcessGenderData
        });
      }

      // Initialize structures
      if (!result.byCountry[country]) {
        result.byCountry[country] = { total: 0, count: 0 };
      }
      if (!result.trends[period]) {
        result.trends[period] = {
          total: 0,
          count: 0,
          totalItems: 0,
          sexDisaggregated: 0,
          ageDisaggregated: 0,
          sexAgeDisaggregated: 0,
          onlyTotal: 0
        };
      }
      if (!result.byIndicator[indicator]) {
        result.byIndicator[indicator] = {
          total: 0,
          count: 0,
          id: indicatorId,
          bySex: {},
          byAge: {},
          bySexAge: {}
        };
      }
      if (!result.countryDisaggregation[country]) {
        result.countryDisaggregation[country] = {
          totalItems: 0,
          sexDisaggregated: 0,
          ageDisaggregated: 0,
          sexAgeDisaggregated: 0,
          onlyTotal: 0,
          totalValue: 0
        };
      }

      // Count ALL items for proper disaggregation calculation
      result.countryDisaggregation[country].totalItems += 1;
      result.trends[period].totalItems += 1;

      // Check if item has disaggregation data
      if (!disaggregationData || !disaggregationData.values) {
        // This item only has total value (no disaggregation)
        result.countryDisaggregation[country].onlyTotal += 1;
        result.trends[period].onlyTotal += 1;

        // Use the answer_value for items without disaggregation, fallback to value
        const totalValue = parseFloat(item.answer_value || item.value) || 0;
        result.countryDisaggregation[country].totalValue += totalValue;
        result.byCountry[country].total += totalValue;
        result.byCountry[country].count += 1;
        result.trends[period].total += totalValue;
        result.trends[period].count += 1;
        result.byIndicator[indicator].total += totalValue;
        result.byIndicator[indicator].count += 1;
        result.totalReached += totalValue;
        continue; // Continue to next item instead of returning from function
      }

      const values = disaggregationData.values;
      const disaggregationMode = disaggregationData.mode;

      // Initialize women in leadership structures
      if (isGoverningBoardIndicator && !result.womenInLeadership.leadership[country]) {
        result.womenInLeadership.leadership[country] = { female: 0, male: 0, total: 0 };
      }
      if (isVolunteeringIndicator && !result.womenInLeadership.volunteering[country]) {
        result.womenInLeadership.volunteering[country] = { female: 0, male: 0, total: 0 };
      }
      if (isStaffIndicator && !result.womenInLeadership.staff[country]) {
        result.womenInLeadership.staff[country] = { female: 0, male: 0, total: 0 };
      }
      if (!result.womenInLeadership.trends[period]) {
        result.womenInLeadership.trends[period] = {
          leadershipFemale: 0, leadershipTotal: 0,
          volunteeringFemale: 0, volunteeringTotal: 0,
          staffFemale: 0, staffTotal: 0
        };
      }

      // Calculate total value for this item - optimized to avoid Object.values() overhead
      let itemTotal = 0;
      if (values.direct && typeof values.direct === 'object') {
        for (const key in values.direct) {
          if (values.direct.hasOwnProperty(key)) {
            itemTotal += parseFloat(values.direct[key]) || 0;
          }
        }
      } else if (typeof values === 'object') {
        for (const key in values) {
          if (values.hasOwnProperty(key) && key !== 'direct' && key !== 'indirect') {
            const val = values[key];
            if (typeof val === 'object' && val !== null) {
              // Handle nested structure
              for (const subKey in val) {
                if (val.hasOwnProperty(subKey)) {
                  itemTotal += parseFloat(val[subKey]) || 0;
                }
              }
            } else {
              itemTotal += parseFloat(val) || 0;
            }
          }
        }
      }

      // Update country disaggregation stats
      result.countryDisaggregation[country].totalValue += itemTotal;

      if (disaggregationMode === 'sex') {
        result.countryDisaggregation[country].sexDisaggregated += 1;
        result.trends[period].sexDisaggregated += 1;
      } else if (disaggregationMode === 'age') {
        result.countryDisaggregation[country].ageDisaggregated += 1;
        result.trends[period].ageDisaggregated += 1;
      } else if (disaggregationMode === 'sex_age') {
        result.countryDisaggregation[country].sexAgeDisaggregated += 1;
        result.countryDisaggregation[country].ageDisaggregated += 1; // sex_age also contains age disaggregation
        result.trends[period].sexAgeDisaggregated += 1;
        result.trends[period].ageDisaggregated += 1; // sex_age also contains age disaggregation
      }

      // Process based on disaggregation mode
      if (disaggregationMode === 'sex') {
        // Handle nested structure: values might be { "direct": { "female": 10, "male": 5 }, "indirect": null }
        const actualValues = values.direct || values;

        // Use for...in loop instead of Object.keys().forEach() for better performance
        for (const sex in actualValues) {
          if (!actualValues.hasOwnProperty(sex)) continue;
          const value = parseFloat(actualValues[sex]) || 0;
          const formattedSex = formatSexCategory(sex);

          result.bySex[formattedSex] = (result.bySex[formattedSex] || 0) + value;
          result.byIndicator[indicator].bySex[formattedSex] = (result.byIndicator[indicator].bySex[formattedSex] || 0) + value;

          // Process women in leadership data - ONLY for governing board indicator
          if (isGoverningBoardIndicator) {
            if (formattedSex === 'Female') {
              result.womenInLeadership.leadership[country].female += value;
              result.womenInLeadership.trends[period].leadershipFemale += value;
            } else if (formattedSex === 'Male') {
              result.womenInLeadership.leadership[country].male += value;
            }
            result.womenInLeadership.leadership[country].total += value;
            result.womenInLeadership.trends[period].leadershipTotal += value;
          }

          // Process volunteering data - only if indicator matches and we have gender disaggregation
          if (isVolunteeringIndicator && canProcessGenderData) {
            if (formattedSex === 'Female') {
              result.womenInLeadership.volunteering[country].female += value;
              result.womenInLeadership.trends[period].volunteeringFemale += value;
            } else if (formattedSex === 'Male') {
              result.womenInLeadership.volunteering[country].male += value;
            }
            result.womenInLeadership.volunteering[country].total += value;
            result.womenInLeadership.trends[period].volunteeringTotal += value;
            debugCounters.volunteerDataProcessed++;
          }

          // Process staff data - only if indicator matches and we have gender disaggregation
          if (isStaffIndicator && canProcessGenderData) {
            if (formattedSex === 'Female') {
              result.womenInLeadership.staff[country].female += value;
              result.womenInLeadership.trends[period].staffFemale += value;
            } else if (formattedSex === 'Male') {
              result.womenInLeadership.staff[country].male += value;
            }
            result.womenInLeadership.staff[country].total += value;
            result.womenInLeadership.trends[period].staffTotal += value;
            debugCounters.staffDataProcessed++;
          }

          result.byCountry[country].total += value;
          result.byCountry[country].count += 1;
          result.trends[period].total += value;
          result.trends[period].count += 1;
          result.byIndicator[indicator].total += value;
          result.byIndicator[indicator].count += 1;
          result.totalReached += value;
        }
      } else if (disaggregationMode === 'age') {
        // Handle nested structure: values might be { "direct": { "0-17": 10, "18-64": 5 }, "indirect": null }
        const actualValues = values.direct || values;

        // Use for...in loop instead of Object.keys().forEach() for better performance
        for (const age in actualValues) {
          if (!actualValues.hasOwnProperty(age)) continue;
          const value = parseFloat(actualValues[age]) || 0;
          const formattedAge = formatAgeGroup(age);

          result.byAge[formattedAge] = (result.byAge[formattedAge] || 0) + value;
          result.byIndicator[indicator].byAge[formattedAge] = (result.byIndicator[indicator].byAge[formattedAge] || 0) + value;

          result.byCountry[country].total += value;
          result.byCountry[country].count += 1;
          result.trends[period].total += value;
          result.trends[period].count += 1;
          result.byIndicator[indicator].total += value;
          result.byIndicator[indicator].count += 1;
          result.totalReached += value;
        }
      } else if (disaggregationMode === 'sex_age') {
        // Handle nested structure: values might be { "direct": { "female_18-49": 21, "male_18-49": 498 }, "indirect": null }
        const actualValues = values.direct || values;

        // Use for...in loop instead of Object.keys().forEach() for better performance
        for (const key in actualValues) {
          if (!actualValues.hasOwnProperty(key)) continue;
          const value = parseFloat(actualValues[key]) || 0;
          const parts = key.split('_');
          const sex = parts[0];
          const age = parts.slice(1).join('_'); // Handle age groups that might have underscores
          const formattedSex = formatSexCategory(sex);
          const formattedAge = formatAgeGroup(age);
          const formattedSexAge = `${formattedSex} - ${formattedAge}`;

          // Process sex data
          result.bySex[formattedSex] = (result.bySex[formattedSex] || 0) + value;
          result.byIndicator[indicator].bySex[formattedSex] = (result.byIndicator[indicator].bySex[formattedSex] || 0) + value;

          // Process age data
          result.byAge[formattedAge] = (result.byAge[formattedAge] || 0) + value;
          result.byIndicator[indicator].byAge[formattedAge] = (result.byIndicator[indicator].byAge[formattedAge] || 0) + value;

          // Process sex-age combination
          result.bySexAge[formattedSexAge] = (result.bySexAge[formattedSexAge] || 0) + value;
          result.byIndicator[indicator].bySexAge[formattedSexAge] = (result.byIndicator[indicator].bySexAge[formattedSexAge] || 0) + value;

          // Process women in leadership data for sex-age - ONLY for governing board indicator
          if (isGoverningBoardIndicator) {
            if (formattedSex === 'Female') {
              result.womenInLeadership.leadership[country].female += value;
              result.womenInLeadership.trends[period].leadershipFemale += value;
            } else if (formattedSex === 'Male') {
              result.womenInLeadership.leadership[country].male += value;
            }
            result.womenInLeadership.leadership[country].total += value;
            result.womenInLeadership.trends[period].leadershipTotal += value;
          }

          // Process volunteering data for sex-age - only if indicator matches
          if (isVolunteeringIndicator && canProcessGenderData) {
            // Initialize if not already done
            if (!result.womenInLeadership.volunteering[country]) {
              result.womenInLeadership.volunteering[country] = { female: 0, male: 0, total: 0 };
            }
            if (formattedSex === 'Female') {
              result.womenInLeadership.volunteering[country].female += value;
              result.womenInLeadership.trends[period].volunteeringFemale += value;
            } else if (formattedSex === 'Male') {
              result.womenInLeadership.volunteering[country].male += value;
            }
            result.womenInLeadership.volunteering[country].total += value;
            result.womenInLeadership.trends[period].volunteeringTotal += value;
            debugCounters.volunteerDataProcessed++;
          }

          // Process staff data for sex-age - only if indicator matches
          if (isStaffIndicator && canProcessGenderData) {
            // Initialize if not already done
            if (!result.womenInLeadership.staff[country]) {
              result.womenInLeadership.staff[country] = { female: 0, male: 0, total: 0 };
            }
            if (formattedSex === 'Female') {
              result.womenInLeadership.staff[country].female += value;
              result.womenInLeadership.trends[period].staffFemale += value;
            } else if (formattedSex === 'Male') {
              result.womenInLeadership.staff[country].male += value;
            }
            result.womenInLeadership.staff[country].total += value;
            result.womenInLeadership.trends[period].staffTotal += value;
            debugCounters.staffDataProcessed++;
          }

          result.byCountry[country].total += value;
          result.byCountry[country].count += 1;
          result.trends[period].total += value;
          result.trends[period].count += 1;
          result.byIndicator[indicator].total += value;
          result.byIndicator[indicator].count += 1;
          result.totalReached += value;
        }
      }
    }

    // Debug logging for indicator matching and processing
    console.log('🔍 Indicator Matching Debug:', {
      totalItems: debugCounters.totalItems,
      itemsWithDisaggregation: debugCounters.itemsWithDisaggregation,
      governingBoardMatches: debugCounters.governingBoardMatches,
      volunteerIdMatches: debugCounters.volunteerIdMatches,
      volunteerNameMatches: debugCounters.volunteerNameMatches,
      staffIdMatches: debugCounters.staffIdMatches,
      staffNameMatches: debugCounters.staffNameMatches,
      volunteerDataProcessed: debugCounters.volunteerDataProcessed,
      staffDataProcessed: debugCounters.staffDataProcessed,
      uniqueIndicatorsEncountered: encounteredIndicators.size,
      lookingForIds: {
        volunteers: VOLUNTEERS_INDICATOR_ID,
        staff: STAFF_INDICATOR_ID,
        governingBoard: GOVERNING_BOARD_INDICATOR_ID
      }
    });

    // Debug: Log sample indicators with volunteer/staff keywords
    if (sampleIndicatorData.length > 0) {
      console.log('📋 Sample Indicators with Volunteer/Staff Keywords:', sampleIndicatorData.slice(0, 10));
    }

    // Debug: Check if we found the target IDs
    const foundVolunteerId = Array.from(encounteredIndicators.values()).some(ind =>
      String(ind.id) === String(VOLUNTEERS_INDICATOR_ID) ||
      ind.id === VOLUNTEERS_INDICATOR_ID
    );
    const foundStaffId = Array.from(encounteredIndicators.values()).some(ind =>
      String(ind.id) === String(STAFF_INDICATOR_ID) ||
      ind.id === STAFF_INDICATOR_ID
    );

    // Get ALL indicator IDs and names for debugging
    const allIndicators = Array.from(encounteredIndicators.values()).map(ind => ({
      id: ind.id,
      idType: typeof ind.id,
      name: ind.name,
      hasDisaggregation: ind.hasDisaggregation,
      mode: ind.mode
    }));

    // Find indicators with volunteer/staff keywords
    const volunteerCandidates = allIndicators.filter(ind => {
      const nameLower = (ind.name || '').toLowerCase();
      return nameLower.includes('volunteer') && !nameLower.includes('staff');
    });

    const staffCandidates = allIndicators.filter(ind => {
      const nameLower = (ind.name || '').toLowerCase();
      return (nameLower.includes('staff') || nameLower.includes('employee') || nameLower.includes('personnel')) &&
             !nameLower.includes('volunteer');
    });

    if (!foundVolunteerId || !foundStaffId) {
      console.warn('⚠️ Target Indicator IDs NOT found in data:', {
        lookingForVolunteerId: VOLUNTEERS_INDICATOR_ID,
        foundVolunteerId,
        lookingForStaffId: STAFF_INDICATOR_ID,
        foundStaffId,
        totalUniqueIndicators: allIndicators.length,
        allIndicatorIds: allIndicators.map(ind => ind.id),
        volunteerCandidates: volunteerCandidates.map(ind => ({ id: ind.id, name: ind.name })),
        staffCandidates: staffCandidates.map(ind => ({ id: ind.id, name: ind.name })),
        sampleIndicators: allIndicators.slice(0, 20)
      });
    }

    // Also log sample indicator data if we found volunteer/staff keywords
    if (sampleIndicatorData.length > 0) {
      console.log('📋 Sample Indicators with Volunteer/Staff Keywords:', sampleIndicatorData.slice(0, 10));
    }

    // Debug: Log volunteering and staff data summary
    const volunteerCountries = Object.keys(result.womenInLeadership.volunteering);
    const staffCountries = Object.keys(result.womenInLeadership.staff || {});
    console.log('👩‍💼 Women in Leadership Debug:', {
      volunteerCountries: volunteerCountries.length,
      staffCountries: staffCountries.length,
      volunteeringData: volunteerCountries.length > 0 ? Object.entries(result.womenInLeadership.volunteering).slice(0, 3).map(([country, data]) => ({
        country,
        female: data.female,
        male: data.male,
        total: data.total,
        percentage: data.total > 0 ? Math.round((data.female / data.total) * 100) : 0
      })) : t('data.noData'),
      staffData: staffCountries.length > 0 ? Object.entries(result.womenInLeadership.staff || {}).slice(0, 3).map(([country, data]) => ({
        country,
        female: data.female,
        male: data.male,
        total: data.total,
        percentage: data.total > 0 ? Math.round((data.female / data.total) * 100) : 0
      })) : t('data.noData'),
      trends: Object.keys(result.womenInLeadership.trends).length > 0 ? Object.entries(result.womenInLeadership.trends).slice(-3).map(([period, data]) => ({
        period,
        volunteeringPercentage: data.volunteeringTotal > 0 ? Math.round((data.volunteeringFemale / data.volunteeringTotal) * 100) : 0,
        staffPercentage: data.staffTotal > 0 ? Math.round((data.staffFemale / data.staffTotal) * 100) : 0,
        volunteeringTotal: data.volunteeringTotal,
        staffTotal: data.staffTotal
      })) : t('data.noTrendData')
    });

    // Summary logging removed for performance - uncomment if debugging needed
    // const totalTrendItems = Object.values(result.trends).reduce((sum, period) => sum + period.totalItems, 0);
    // ... more calculations and logging ...

    // Extract available years and build countryYearData in a single pass
    const yearSet = new Set();
    const countryYearData = {};

    // Only build countryYearData if we need year filtering
    const needsYearData = !!yearFilter;

    // Use for loop instead of forEach for better performance
    for (let i = 0; i < filteredLength; i++) {
      const item = filteredData[i];
      const year = extractYearFromPeriod(item.period_name);
      if (year > 0) {
        yearSet.add(year);

        // Only process countryYearData if year filtering is needed
        if (needsYearData) {
          // Resolve country name from country_id if country_info is not available
          let country = t('fallbacks.unknown');
          if (item.country_info?.name) {
            country = item.country_info.name;
      } else if (item.country_id && countriesMapToUse.has(item.country_id)) {
        country = countriesMapToUse.get(item.country_id).name;
          }
          // Resolve indicator name from form_item_id if needed
          let indicator = item.form_item_info?.bank_details?.name ||
                           item.form_item_info?.indicator_bank_name ||
                           item.indicator_bank_name ||
                           item.indicator_name ||
                           item.form_item_info?.label;

          if (!indicator || indicator === t('fallbacks.unknownIndicator')) {
            if (item.form_item_id && formItemsNameMap.has(item.form_item_id)) {
              indicator = formItemsNameMap.get(item.form_item_id);
            } else {
              // Try to get indicator_id first
              const itemIndicatorId = item.form_item_info?.bank_details?.id ||
                                     item.form_item_info?.indicator_bank_id ||
                                     item.indicator_bank_id;
              if (itemIndicatorId && indicatorIdToNameMap.has(itemIndicatorId)) {
                indicator = indicatorIdToNameMap.get(itemIndicatorId);
              } else {
                indicator = t('fallbacks.unknownIndicator');
              }
            }
          }

          if (!countryYearData[country]) {
            countryYearData[country] = {};
          }
          if (!countryYearData[country][year]) {
            countryYearData[country][year] = {};
          }
          if (!countryYearData[country][year][indicator]) {
            countryYearData[country][year][indicator] = { total: 0, count: 0 };
          }

          // Calculate value for this item - optimized to avoid Object.values()
          let itemValue = 0;
          if (item.disaggregation_data && item.disaggregation_data.values) {
            const values = item.disaggregation_data.values;
            const actualValues = values.direct || values;
            // Use for...in loop instead of Object.values().reduce()
            for (const key in actualValues) {
              if (actualValues.hasOwnProperty(key)) {
                itemValue += parseFloat(actualValues[key]) || 0;
              }
            }
          } else {
            itemValue = parseFloat(item.answer_value || item.value) || 0;
          }

          countryYearData[country][year][indicator].total += itemValue;
          countryYearData[country][year][indicator].count += 1;
        }
      }
    }

    const availableYears = Array.from(yearSet).sort((a, b) => b - a); // Sort descending (latest first)

    // Convert to arrays and calculate top indicator per country per year
    const byCountryResult = yearFilter ?
      // If year is selected, show top indicator per country for that year
      Object.entries(countryYearData)
        .map(([country, years]) => {
          const yearData = years[yearFilter];
          if (!yearData || Object.keys(yearData).length === 0) {
            return null;
          }

          // Find top indicator (highest average value) for this country and year
          let topIndicator = null;
          let topValue = 0;

          Object.entries(yearData).forEach(([indicator, data]) => {
            const avgValue = data.count > 0 ? data.total / data.count : 0;
            if (avgValue > topValue) {
              topValue = avgValue;
              topIndicator = indicator;
            }
          });

          return topIndicator ? {
            label: country,
            value: Math.round(topValue),
            indicator: topIndicator,
            year: yearFilter
          } : null;
        })
        .filter(item => item !== null)
        .sort((a, b) => b.value - a.value)
        .slice(0, 15)
      :
      // If no year selected, use original average calculation
      Object.entries(result.byCountry)
        .map(([label, data]) => ({
          label,
          value: data.count > 0 ? Math.round(data.total / data.count) : 0,
          total: data.total,
          count: data.count
        }))
        .sort((a, b) => b.value - a.value)
        .slice(0, 15);

    // Year filter logging removed for performance - uncomment if debugging needed
    // if (yearFilter) { ... }

    const processedResult = {
      totalReached: result.totalReached,
      availableYears: availableYears,
      byCountry: byCountryResult,
      bySex: Object.entries(result.bySex)
        .map(([label, value]) => ({ label, value: Math.round(value) }))
        .sort((a, b) => b.value - a.value),
      byAge: Object.entries(result.byAge)
        .map(([label, value]) => ({ label, value: Math.round(value) }))
        .sort((a, b) => sortAgeGroups(a.label, b.label)),
      bySexAge: Object.entries(result.bySexAge)
        .map(([label, value]) => ({ label, value: Math.round(value) }))
        .sort((a, b) => b.value - a.value)
        .slice(0, 20), // Top 20 combinations
      trends: Object.entries(result.trends)
        .map(([label, data]) => {
          /*
           * TRENDS DISAGGREGATION CALCULATION DOCUMENTATION
           * ==============================================
           *
           * For time-based trends, we need to calculate what percentage of ALL items
           * in each time period have different types of disaggregation.
           *
           * BREAKDOWN PERCENTAGES (should add up to 100%):
           * 1. Non-disaggregated: (onlyTotal / totalItems) * 100
           * 2. Sex disaggregation: (sexDisaggregated / totalItems) * 100
           * 3. Age disaggregation: (ageDisaggregated / totalItems) * 100
           * 4. Sex+Age disaggregation: (sexAgeDisaggregated / totalItems) * 100
           *
           * Note: sex_age items count for BOTH sex and age, so totals may overlap
           *
           * FORMULAS:
           * - Age disaggregation % = (age disaggregated items / total items) * 100
           * - Overall disaggregation % = (items with ANY disaggregation / total items) * 100
           */

          const itemsWithDisaggregation = data.totalItems - data.onlyTotal;

          // FIXED: Age disaggregation as percentage of ALL items (not just disaggregated ones)
          const ageDisaggregationPercentage = data.totalItems > 0 ?
            Math.round((data.ageDisaggregated / data.totalItems) * 100) : 0;

          // Calculate breakdown percentages for debugging
          const notDisaggregatedPercentage = data.totalItems > 0 ?
            Math.round((data.onlyTotal / data.totalItems) * 100) : 0;
          const sexDisaggregationPercentage = data.totalItems > 0 ?
            Math.round((data.sexDisaggregated / data.totalItems) * 100) : 0;
          const sexAgeDisaggregationPercentage = data.totalItems > 0 ?
            Math.round((data.sexAgeDisaggregated / data.totalItems) * 100) : 0;

          // Overall disaggregation percentage - items with ANY disaggregation
          const overallDisaggregationPercentage = data.totalItems > 0 ?
            Math.round((itemsWithDisaggregation / data.totalItems) * 100) : 0;

          // Debug logging removed for performance - uncomment if debugging needed
          // console.log(`📊 Trend calculation for ${label}:`, {...});

          return {
            label,
            value: data.count > 0 ? Math.round(data.total / data.count) : 0,
            total: data.total,
            count: data.count,
            ageDisaggregationPercentage,
            overallDisaggregationPercentage,
            // Breakdown percentages for detailed analysis
            notDisaggregatedPercentage,
            sexDisaggregationPercentage,
            sexAgeDisaggregationPercentage
          };
        })
        .sort((a, b) => a.label.localeCompare(b.label)),
      byIndicator: Object.entries(result.byIndicator)
        .map(([label, data]) => ({
          label,
          value: Math.round(data.total),
          average: data.count > 0 ? Math.round(data.total / data.count) : 0,
          count: data.count,
          id: data.id,
          bySex: Object.entries(data.bySex).map(([sex, val]) => ({ label: sex, value: Math.round(val) })),
          byAge: Object.entries(data.byAge).map(([age, val]) => ({ label: age, value: Math.round(val) })),
          bySexAge: Object.entries(data.bySexAge).map(([sexAge, val]) => ({ label: sexAge, value: Math.round(val) }))
        }))
        .filter(indicator => {
          // Only keep indicators that have age/sex disaggregation data
          const hasSexData = indicator.bySex.length > 0 && indicator.bySex.some(item => item.value > 0);
          const hasAgeData = indicator.byAge.length > 0 && indicator.byAge.some(item => item.value > 0);
          return hasSexData || hasAgeData;
        })
        .sort((a, b) => b.value - a.value),
      countryDisaggregation: Object.entries(result.countryDisaggregation)
        .map(([label, data]) => {
          /*
           * DISAGGREGATION PERCENTAGE CALCULATION DOCUMENTATION
           * ===================================================
           *
           * The goal is to calculate what percentage of data items have disaggregation.
           * However, we need to avoid double-counting items that have multiple types
           * of disaggregation (e.g., both sex AND age data).
           *
           * PROBLEM: Previous calculation was:
           * (sexDisaggregated + ageDisaggregated + sexAgeDisaggregated) / totalItems * 100
           *
           * This causes double/triple counting:
           * - Items with sex+age disaggregation get counted 3 times!
           * - This can result in percentages > 100%
           *
           * SOLUTION: Count unique items that have ANY disaggregation
           * Formula: (totalItems - onlyTotal) / totalItems * 100
           * Where:
           * - totalItems = all data items for this country
           * - onlyTotal = items that ONLY have total values (no disaggregation)
           * - (totalItems - onlyTotal) = items with ANY disaggregation
           */

          const itemsWithAnyDisaggregation = data.totalItems - data.onlyTotal;

          return {
            label,
            totalItems: data.totalItems,
            sexDisaggregated: data.sexDisaggregated,
            ageDisaggregated: data.ageDisaggregated,
            sexAgeDisaggregated: data.sexAgeDisaggregated,
            onlyTotal: data.onlyTotal,
            totalValue: Math.round(data.totalValue),

            // Individual disaggregation type percentages (these can overlap, so their sum may exceed 100%)
            sexPercentage: data.totalItems > 0 ? Math.round((data.sexDisaggregated / data.totalItems) * 100) : 0,
            agePercentage: data.totalItems > 0 ? Math.round((data.ageDisaggregated / data.totalItems) * 100) : 0,
            sexAgePercentage: data.totalItems > 0 ? Math.round((data.sexAgeDisaggregated / data.totalItems) * 100) : 0,

            // FIXED: Overall disaggregation percentage - no double counting
            // This represents: "What percentage of items have ANY disaggregation?"
            overallDisaggregation: data.totalItems > 0 ?
              Math.round((itemsWithAnyDisaggregation / data.totalItems) * 100) : 0
          };
        })
        .sort((a, b) => b.overallDisaggregation - a.overallDisaggregation),
      womenInLeadership: {
        leadership: Object.entries(result.womenInLeadership.leadership)
          .map(([country, data]) => ({
            label: country,
            female: data.female,
            male: data.male,
            total: data.total,
            femalePercentage: data.total > 0 ? Math.round((data.female / data.total) * 100) : 0
          }))
          .sort((a, b) => b.femalePercentage - a.femalePercentage),
        volunteering: Object.entries(result.womenInLeadership.volunteering)
          .map(([country, data]) => ({
            label: country,
            female: data.female,
            male: data.male,
            total: data.total,
            femalePercentage: data.total > 0 ? Math.round((data.female / data.total) * 100) : 0
          }))
          .sort((a, b) => b.femalePercentage - a.femalePercentage),
        staff: Object.entries(result.womenInLeadership.staff || {})
          .map(([country, data]) => ({
            label: country,
            female: data.female,
            male: data.male,
            total: data.total,
            femalePercentage: data.total > 0 ? Math.round((data.female / data.total) * 100) : 0
          }))
          .sort((a, b) => b.femalePercentage - a.femalePercentage),
        trends: Object.entries(result.womenInLeadership.trends)
          .map(([period, data]) => {
            /*
             * WOMEN IN LEADERSHIP TRENDS CALCULATION DOCUMENTATION
             * ==================================================
             *
             * These calculations represent gender representation percentages
             * across different organizational levels over time.
             *
             * FORMULAS:
             * - Leadership % = (female leadership count / total leadership count) * 100
             * - Volunteering % = (female volunteer count / total volunteer count) * 100
             * - Staff % = (female staff count / total staff count) * 100
             *
             * NOTE: These percentages should never exceed 100% as they represent
             * proportional representation within each category.
             */

            return {
              label: period,
              leadershipPercentage: data.leadershipTotal > 0 ? Math.round((data.leadershipFemale / data.leadershipTotal) * 100) : 0,
              volunteeringPercentage: data.volunteeringTotal > 0 ? Math.round((data.volunteeringFemale / data.volunteeringTotal) * 100) : 0,
              staffPercentage: data.staffTotal > 0 ? Math.round((data.staffFemale / data.staffTotal) * 100) : 0,
              leadershipTotal: data.leadershipTotal,
              volunteeringTotal: data.volunteeringTotal,
              staffTotal: data.staffTotal,
              // Debug info for validation
              _debug: {
                leadershipFormula: `${data.leadershipFemale} / ${data.leadershipTotal} * 100`,
                volunteeringFormula: `${data.volunteeringFemale} / ${data.volunteeringTotal} * 100`,
                staffFormula: `${data.staffFemale} / ${data.staffTotal} * 100`
              }
            };
          })
          .sort((a, b) => a.label.localeCompare(b.label)),
        comparison: [
          {
            label: 'Leadership Roles',
            value: Object.values(result.womenInLeadership.leadership).reduce((sum, data) => sum + data.female, 0),
            total: Object.values(result.womenInLeadership.leadership).reduce((sum, data) => sum + data.total, 0)
          },
          {
            label: 'Volunteering',
            value: Object.values(result.womenInLeadership.volunteering).reduce((sum, data) => sum + data.female, 0),
            total: Object.values(result.womenInLeadership.volunteering).reduce((sum, data) => sum + data.total, 0)
          },
          {
            label: 'Staff',
            value: Object.values(result.womenInLeadership.staff || {}).reduce((sum, data) => sum + data.female, 0),
            total: Object.values(result.womenInLeadership.staff || {}).reduce((sum, data) => sum + data.total, 0)
          }
        ].map(item => ({
          ...item,
          percentage: item.total > 0 ? Math.round((item.value / item.total) * 100) : 0
        }))
      }
    };

    return processedResult;
    } catch (error) {
      console.error('Error in processEnhancedDisaggregatedData:', error);
      // Return default structure on error
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
        womenInLeadership: {
          leadership: [],
          volunteering: [],
          staff: [],
          trends: [],
          comparison: []
        }
      };
    }
  };

  // Helper function to extract year from period name
  const extractYearFromPeriod = (periodName) => {
    if (!periodName) return 0;

    // Try to extract year from various formats (e.g., "2023", "FY2023", "Q1 2024")
    const yearMatch = periodName.match(/\b(20\d{2})\b/);
    if (yearMatch) {
      return parseInt(yearMatch[1]);
    }

    // If no year found, try to parse as number
    const numMatch = periodName.match(/\b(\d{4})\b/);
    if (numMatch) {
      return parseInt(numMatch[1]);
    }

    return 0;
  };

  // Helper function to format sex categories
  const formatSexCategory = (sex) => {
    const sexMap = {
      'male': 'Male',
      'female': 'Female',
      'men': 'Male',
      'women': 'Female',
      'boys': 'Male',
      'girls': 'Female',
      'other': 'Other',
      'unknown': t('fallbacks.unknown')
    };
    return sexMap[sex.toLowerCase()] || sex.charAt(0).toUpperCase() + sex.slice(1);
  };

  // Helper function to format and standardize age groups
  const formatAgeGroup = (age) => {
    const ageMap = {
      'child': '0-17 years',
      'children': '0-17 years',
      'infant': '0-2 years',
      'infants': '0-2 years',
      'toddler': '2-5 years',
      'toddlers': '2-5 years',
      'preschool': '3-5 years',
      'school': '6-12 years',
      'adolescent': '13-17 years',
      'adolescents': '13-17 years',
      'teen': '13-17 years',
      'teenager': '13-17 years',
      'adult': '18-64 years',
      'adults': '18-64 years',
      'elderly': '65+ years',
      'elder': '65+ years',
      'senior': '65+ years',
      'seniors': '65+ years',
      'young_adult': '18-30 years',
      'middle_aged': '31-64 years',
      'under_5': '0-4 years',
      'under_18': '0-17 years',
      'over_65': '65+ years',
      '0_4': '0-4 years',
      '5_17': '5-17 years',
      '18_59': '18-59 years',
      '60_plus': '60+ years',
      'unknown': t('fallbacks.unknown')
    };

    // Clean the age string
    let cleanAge = age.toLowerCase().replace(/[^a-z0-9_]/g, '');

    // Check for direct mapping
    if (ageMap[cleanAge]) {
      return ageMap[cleanAge];
    }

    // Check for numeric ranges
    if (cleanAge.includes('_')) {
      const parts = cleanAge.split('_');
      if (parts.length === 2) {
        const start = parts[0];
        const end = parts[1];
        if (end === 'plus' || end === 'over') {
          return `${start}+ years`;
        } else {
          return `${start}-${end} years`;
        }
      }
    }

    // Return formatted version
    return age.charAt(0).toUpperCase() + age.slice(1).replace(/_/g, ' ');
  };

  // Helper function to sort age groups logically
  const sortAgeGroups = (a, b) => {
    const getAgeOrder = (ageGroup) => {
      if (ageGroup.includes('0-2') || ageGroup.includes('0-4')) return 1;
      if (ageGroup.includes('2-5') || ageGroup.includes('3-5') || ageGroup.includes('5-17')) return 2;
      if (ageGroup.includes('6-12')) return 3;
      if (ageGroup.includes('13-17')) return 4;
      if (ageGroup.includes('0-17')) return 5;
      if (ageGroup.includes('18-30')) return 6;
      if (ageGroup.includes('18-59') || ageGroup.includes('18-64')) return 7;
      if (ageGroup.includes('31-64')) return 8;
      if (ageGroup.includes('60+') || ageGroup.includes('65+')) return 9;
      if (ageGroup.toLowerCase().includes('unknown')) return 10;
      return 99;
    };

    return getAgeOrder(a) - getAgeOrder(b);
  };

  // Helper function to group countries by region
  const groupCountriesByRegion = (countryData) => {
    const regionGroups = {};

    countryData.forEach(country => {
      const region = countryRegions[country.label] || 'Other';
      if (!regionGroups[region]) {
        regionGroups[region] = [];
      }
      regionGroups[region].push(country);
    });

    return regionGroups;
  };

  // Helper function to get region color
  const getRegionColor = (region) => {
    const colors = {
      'Africa': '#E53E3E',
      'Americas': '#3182CE',
      'Asia': '#38A169',
      'Europe': '#805AD5',
      'Middle East': '#D69E2E',
      'Other': '#718096'
    };
    return colors[region] || '#718096';
  };

  // Fetch data from API
  const fetchData = async () => {
    setIsLoading(true);
    setError(null);

    const startTime = performance.now();

    try {
      // Build filters for getDataWithRelated
      const apiFilters = {
        template_id: FDRS_TEMPLATE_ID,
        period_name: filters.selectedPeriod || undefined,
        indicator_bank_id: filters.selectedIndicator ? parseInt(filters.selectedIndicator) : undefined,
        disagg: true,
        related: 'all',
        returnFullResponse: false // Get just the data array for backward compatibility
      };

      // Remove undefined filters
      Object.keys(apiFilters).forEach(key =>
        apiFilters[key] === undefined && delete apiFilters[key]
      );

      const data = await getDataWithRelated(apiFilters);

      const fetchTime = performance.now() - startTime;

      // getDataWithRelated returns array directly (backward compatible mode)
      const actualData = Array.isArray(data) ? data : (data?.data || []);

      // Filter by countries on frontend if needed (since backend /data/tables uses country_id, not country names)
      let filteredData = actualData;
      if (filters.selectedCountries && filters.selectedCountries.length > 0) {
        filteredData = actualData.filter(item => {
          // Resolve country name from country_id if country_info is not available
          let countryName = item?.country_info?.name;
          if (!countryName && item.country_id && countriesMap.has(item.country_id)) {
            countryName = countriesMap.get(item.country_id).name;
          }
          return countryName && filters.selectedCountries.includes(countryName);
        });
      }

      // Console logging removed for performance
      // console.log(`📊 Received ${actualData.length} total records from API`);

      setRawData(filteredData);

      // Process the data with enhanced logic - measure performance
      const processingStart = performance.now();

      isProcessingRef.current = true;
      const processed = await processEnhancedDisaggregatedData(filteredData, selectedYear, countriesMap);

      const processingTime = performance.now() - processingStart;

      // Only log processing time if it's significant (> 500ms)
      if (processingTime > 500) {
        console.log(`📊 Processing completed in ${processingTime.toFixed(2)}ms`);
      }

      // Only set processed data if processing was successful
      if (processed && typeof processed === 'object') {
        setProcessedData(processed);

        // Update refs to track what we've processed
        lastProcessedYearRef.current = selectedYear;
        lastRawDataLengthRef.current = filteredData.length;

        // Set default year to latest if not already set
        if (processed.availableYears && Array.isArray(processed.availableYears) && processed.availableYears.length > 0 && !selectedYear) {
          setSelectedYear(processed.availableYears[0]);
        }
      } else {
        console.error('Processing failed: processEnhancedDisaggregatedData returned invalid result', processed);
        setError(t('errors.failedToProcessData'));
      }

      isProcessingRef.current = false;

    } catch (err) {
      console.error('Error fetching data:', err);
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  // Download handlers
  const handleDownloadCSV = async () => {
    setIsDownloadingCSV(true);
    try {
      if (!processedData || !processedData.countryDisaggregation || !Array.isArray(processedData.countryDisaggregation)) {
        console.error('Cannot download CSV: processedData is not available');
        return;
      }

      const regionGroups = groupCountriesByRegion(processedData.countryDisaggregation);
      const csvData = {};

      // Convert region groups to flat structure for CSV
      Object.entries(regionGroups).forEach(([region, countries]) => {
        countries.forEach(country => {
          csvData[country.label] = {
            name: country.label,
            value: country.overallDisaggregation,
            region: region,
            totalItems: country.totalItems,
            sexPercentage: country.sexPercentage,
            agePercentage: country.agePercentage,
            sexAgePercentage: country.sexAgePercentage
          };
        });
      });

      const filename = generateFilename(
        'Disaggregation Coverage by Country',
        filters.selectedPeriod || t('data.allPeriods'),
        t('data.allRegions'),
        'csv'
      );

      downloadCSV(csvData, filename, 'Disaggregation Coverage by Country', filters.selectedPeriod || t('data.allPeriods'), t('data.allRegions'));
    } catch (error) {
      console.error('Error downloading CSV:', error);
    } finally {
      setIsDownloadingCSV(false);
    }
  };



  const handleDownloadPNG = async (elementId, title) => {
    setIsDownloadingPNG(true);
    try {
      const filename = generateFilename(
        title,
        filters.selectedPeriod || t('data.allPeriods'),
        title === t('data.regionalSummary') ? t('data.allRegions') : title,
        'png'
      );

      await downloadPNG(filename, elementId);
    } catch (error) {
      console.error('Error downloading PNG:', error);
    } finally {
      setIsDownloadingPNG(false);
    }
  };

  // Track if we're currently processing to avoid duplicate processing
  const isProcessingRef = useRef(false);
  const lastProcessedYearRef = useRef(null);
  const lastRawDataLengthRef = useRef(0);

  // Load data when filters change - debounced to prevent excessive API calls
  useEffect(() => {
    if (filters.countries.length > 0) { // Only fetch when filter options are loaded
      // Add small delay to prevent rapid successive calls
      const timeoutId = setTimeout(() => {
        fetchData();
      }, 300);

      return () => clearTimeout(timeoutId);
    }
  }, [filters.selectedCountries, filters.selectedPeriod, filters.selectedIndicator, filters.countries]);

  // Recalculate byCountry when selectedYear changes (no need to refetch data)
  // Only reprocess if year actually changed and we have data
  useEffect(() => {
    if (rawData.length > 0 && !isProcessingRef.current) {
      // Only reprocess if year changed or raw data changed
      const yearChanged = lastProcessedYearRef.current !== selectedYear;
      const dataChanged = lastRawDataLengthRef.current !== rawData.length;

      if (yearChanged || dataChanged) {
        isProcessingRef.current = true;

        // Process immediately - don't use requestIdleCallback as it causes delays
        // Use setTimeout(0) to yield to the browser but process quickly
        const timeoutId = setTimeout(async () => {
          // Reprocess only the byCountry calculation, not everything
          const processed = await processEnhancedDisaggregatedData(rawData, selectedYear, countriesMap);

          // Check if processed is valid before accessing properties
          if (processed && typeof processed === 'object') {
            setProcessedData(prev => ({
              ...prev,
              byCountry: processed.byCountry || [],
              availableYears: processed.availableYears || []
            }));

            lastProcessedYearRef.current = selectedYear;
            lastRawDataLengthRef.current = rawData.length;
          } else {
            console.error('Failed to process data: processEnhancedDisaggregatedData returned invalid result', processed);
          }

          isProcessingRef.current = false;
        }, 0);

        return () => clearTimeout(timeoutId);
      }
    }
  }, [selectedYear, rawData]);

  // Cleanup tooltip throttle timeout on unmount
  useEffect(() => {
    return () => {
      if (tooltipThrottleRef.current) {
        clearTimeout(tooltipThrottleRef.current);
      }
    };
  }, []);

  // Format numbers
  const formatNumber = (num) => {
    // Handle undefined, null, or NaN values
    if (num === undefined || num === null || isNaN(num)) {
      return '0';
    }

    if (num >= 1000000000) {
      return (num / 1000000000).toFixed(1) + 'B';
    } else if (num >= 1000000) {
      return (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
      return (num / 1000).toFixed(1) + 'K';
    }
    return Math.round(num).toLocaleString();
  };

  // Helper function to generate 5-year trend data
  const generateTrendData = (trends, type) => {
    if (!trends || trends.length === 0) {
      // Return a clear message instead of mock data
      return [{
        year: t('data.noData'),
        value: 0,
        isPlaceholder: true
      }];
    }

    // Get actual trend data and sort by year
    const sortedTrends = trends.sort((a, b) => {
      // Try to parse as numbers first (for years like "2023")
      const yearA = parseInt(a.label) || a.label;
      const yearB = parseInt(b.label) || b.label;

      if (typeof yearA === 'number' && typeof yearB === 'number') {
        return yearA - yearB;
      }
      // Fallback to string comparison
      return a.label.localeCompare(b.label);
    });

    // Get the last 5 years of data or all available data if less than 5 years
    const availableYears = Math.min(5, sortedTrends.length);
    const recentTrends = sortedTrends.slice(-availableYears);

    return recentTrends.map(trend => ({
      year: trend.label,
      value: Math.round(type === 'leadership' ? trend.leadershipPercentage :
             type === 'volunteering' ? trend.volunteeringPercentage :
             type === 'staff' ? (trend.staffPercentage || 0) :
             type === 'age' ? (trend.ageDisaggregationPercentage || 0) :
             type === 'disaggregation' ? (trend.overallDisaggregationPercentage || 0) : 0),
      isPlaceholder: false
    }));
  };

  // Helper function to handle tooltip events with throttling
  const handleTooltip = (event, data, type) => {
    // Throttle mouse move events for better performance
    if (tooltipThrottleRef.current) {
      clearTimeout(tooltipThrottleRef.current);
    }

    tooltipThrottleRef.current = setTimeout(() => {
    // Return early if processedData is not available
    if (!processedData || typeof processedData !== 'object') {
      return;
    }

    // Determine which trends array to use based on tooltip type
    const trendsSource = (type === 'age' || type === 'disaggregation')
      ? (processedData.trends || [])
      : (processedData.womenInLeadership?.trends || []);

    const trendData = generateTrendData(trendsSource, type);

    // Use mouse position for better cursor tracking
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const tooltipWidth = 320; // Account for padding and content
    const tooltipHeight = 200; // Estimated tooltip height
    const offset = 15; // Distance from cursor

    // Get cursor position
    let x = event.clientX;
    let y = event.clientY;

    // Smart positioning: place tooltip to avoid going off screen
    // Default: top-right of cursor
    let tooltipX = x + offset;
    let tooltipY = y - tooltipHeight - offset;

    // If tooltip would go off right edge, place it to the left of cursor
    if (tooltipX + tooltipWidth > viewportWidth) {
      tooltipX = x - tooltipWidth - offset;
    }

    // If tooltip would go off top edge, place it below cursor
    if (tooltipY < 0) {
      tooltipY = y + offset;
    }

    // Final boundary checks to ensure tooltip stays on screen
    tooltipX = Math.max(10, Math.min(tooltipX, viewportWidth - tooltipWidth - 10));
    tooltipY = Math.max(10, Math.min(tooltipY, viewportHeight - tooltipHeight - 10));

    setTooltipState({
      isVisible: true,
      data: trendData,
      position: { x: tooltipX, y: tooltipY }
    });
    }, 16); // ~60fps throttling
  };

  const hideTooltip = () => {
    // Clear any pending tooltip updates
    if (tooltipThrottleRef.current) {
      clearTimeout(tooltipThrottleRef.current);
      tooltipThrottleRef.current = null;
    }

    setTooltipState({
      isVisible: false,
      data: null,
      position: { x: 0, y: 0 }
    });
  };

  // Calculate summary statistics
  const getSummaryStats = () => {
    // Return default stats if processedData is not initialized
    if (!processedData || typeof processedData !== 'object') {
      return {
        totalCountries: 0,
        totalSexCategories: 0,
        totalAgeGroups: 0,
        totalIndicators: 0,
        totalDataPoints: 0,
        disaggregatedDataPoints: 0,
        avgDisaggregation: 0,
        avgAgeDisaggregation: 0,
        avgWomenLeadership: 0,
        avgWomenVolunteering: 0,
        avgWomenStaff: 0
      };
    }

    // Get the most recent year's data
    const getMostRecentYearData = (dataArray, yearField = 'period_name') => {
      if (!dataArray || dataArray.length === 0) return [];

      // Get unique years and sort them
      const years = [...new Set(dataArray.map(item => item[yearField] || item.label))].sort();
      const mostRecentYear = years[years.length - 1];

      // Filter data for the most recent year
      return dataArray.filter(item => (item[yearField] || item.label) === mostRecentYear);
    };

    // Get most recent year data from raw data
    const recentRawData = getMostRecentYearData(rawData);

    // Calculate disaggregation for recent data only - with null check
    const countryDisaggregation = processedData.countryDisaggregation || [];
    const recentCountryDisaggregation = Array.isArray(countryDisaggregation)
      ? countryDisaggregation
          .map(country => {
            // For each country, calculate stats based on recent data only
            // Resolve country name from country_id if needed
            const countryRecentData = recentRawData.filter(item => {
              let itemCountryName = item.country_info?.name;
              if (!itemCountryName && item.country_id && countriesMap.has(item.country_id)) {
                itemCountryName = countriesMap.get(item.country_id).name;
              }
              if (!itemCountryName) {
                itemCountryName = item.country;
              }
              return itemCountryName === country.label;
            });

            if (countryRecentData.length === 0) return null;

            const disaggregatedCount = countryRecentData.filter(item =>
              item.disaggregation_data && item.disaggregation_data.values
            ).length;

            const recentDisaggregationPercentage = countryRecentData.length > 0
              ? Math.round((disaggregatedCount / countryRecentData.length) * 100)
              : 0;

            return {
              ...country,
              recentDisaggregationPercentage
            };
          })
          .filter(country => country !== null)
      : [];

    // Get most recent trends data - with null checks
    const womenInLeadership = processedData.womenInLeadership || {};
    const leadershipTrends = womenInLeadership.trends || [];
    const recentTrends = Array.isArray(leadershipTrends) && leadershipTrends.length > 0
      ? leadershipTrends[leadershipTrends.length - 1]
      : null;

    // Get most recent overall trends data (includes age and overall disaggregation percentages)
    const trends = processedData.trends || [];
    const recentOverallTrends = Array.isArray(trends) && trends.length > 0
      ? trends[trends.length - 1]
      : null;

    // Safe array access with defaults
    const byCountry = processedData.byCountry || [];
    const bySex = processedData.bySex || [];
    const byAge = processedData.byAge || [];
    const byIndicator = processedData.byIndicator || [];
    const leadership = womenInLeadership.leadership || [];
    const volunteering = womenInLeadership.volunteering || [];
    const staff = womenInLeadership.staff || [];

    const stats = {
      totalCountries: Array.isArray(byCountry) ? byCountry.length : 0,
      totalSexCategories: Array.isArray(bySex) ? bySex.length : 0,
      totalAgeGroups: Array.isArray(byAge) ? byAge.length : 0,
      totalIndicators: Array.isArray(byIndicator) ? byIndicator.length : 0,
      totalDataPoints: Array.isArray(rawData) ? rawData.length : 0,
      disaggregatedDataPoints: (() => {
        if (!Array.isArray(rawData)) return 0;
        // Count disaggregated items using for loop for better performance
        let count = 0;
        for (let i = 0; i < rawData.length; i++) {
          if (rawData[i]?.disaggregation_data?.values) {
            count++;
          }
        }
        return count;
      })(),

      // FIXED: Use most recent overall trends data for consistency with tooltips
      avgDisaggregation: recentOverallTrends ? recentOverallTrends.overallDisaggregationPercentage :
        (recentCountryDisaggregation.length > 0
          ? Math.round(recentCountryDisaggregation.reduce((sum, country) => sum + country.recentDisaggregationPercentage, 0) / recentCountryDisaggregation.length)
          : 0),

      // FIXED: Use most recent overall trends data for consistency with tooltips
      avgAgeDisaggregation: recentOverallTrends ? recentOverallTrends.ageDisaggregationPercentage : 0,

      // Use most recent trends data if available
      avgWomenLeadership: recentTrends ? recentTrends.leadershipPercentage :
        (Array.isArray(leadership) && leadership.length > 0
          ? Math.round(leadership.reduce((sum, country) => sum + country.femalePercentage, 0) / leadership.length)
          : 0),

      avgWomenVolunteering: (() => {
        const fromTrends = recentTrends ? recentTrends.volunteeringPercentage : null;
        const fromArray = Array.isArray(volunteering) && volunteering.length > 0
          ? Math.round(volunteering.reduce((sum, country) => sum + country.femalePercentage, 0) / volunteering.length)
          : null;
        const result = fromTrends !== null && fromTrends !== undefined ? fromTrends : (fromArray !== null ? fromArray : 0);

        // Debug logging
        if (result === 0 && volunteering.length > 0) {
          console.warn('⚠️ avgWomenVolunteering is 0 but volunteering data exists:', {
            recentTrends,
            volunteeringLength: volunteering.length,
            volunteeringData: volunteering.slice(0, 3),
            fromTrends,
            fromArray,
            result
          });
        }
        return result;
      })(),

      avgWomenStaff: (() => {
        const fromTrends = recentTrends ? (recentTrends.staffPercentage || 0) : null;
        const fromArray = Array.isArray(staff) && staff.length > 0
          ? Math.round(staff.reduce((sum, country) => sum + country.femalePercentage, 0) / staff.length)
          : null;
        const result = fromTrends !== null && fromTrends !== undefined ? fromTrends : (fromArray !== null ? fromArray : 0);

        // Debug logging
        if (result === 0 && staff.length > 0) {
          console.warn('⚠️ avgWomenStaff is 0 but staff data exists:', {
            recentTrends,
            staffLength: staff.length,
            staffData: staff.slice(0, 3),
            fromTrends,
            fromArray,
            result
          });
        }
        return result;
      })()
    };
    return stats;
  };

  const stats = getSummaryStats();

  const fadeIn = {
    hidden: { opacity: 0 },
    visible: { opacity: 1, transition: { duration: 0.6 } },
  };

  const slideUp = {
    hidden: { opacity: 0, y: 20 },
    visible: { opacity: 1, y: 0, transition: { duration: 0.6 } },
  };

  const staggerContainer = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1,
        delayChildren: 0.2,
      },
    },
  };

  if (error) {
    return (
      <div className="w-full px-6 sm:px-8 lg:px-12 py-8 text-center">
        <Head>
          <title>{t('disaggregationAnalysis.error.title')} - {t('disaggregationAnalysis.title')} - NGO Databank</title>
        </Head>
        <h1 className="text-3xl font-bold text-ngodb-red mb-6">{t('disaggregationAnalysis.error.title')}</h1>
        <p className="text-ngodb-gray-700 mb-6">{error}</p>
        <button
          onClick={fetchData}
          className="bg-ngodb-red text-white px-6 py-2 rounded-lg hover:bg-ngodb-red-dark transition-colors"
        >
          {t('disaggregationAnalysis.error.retry')}
        </button>
      </div>
    );
  }

  return (
    <>
      <Head>
        <title>{t('disaggregationAnalysis.title')} - NGO Databank</title>
        <meta name="description" content={t('disaggregationAnalysis.meta.description')} />
      </Head>

      {/* Tooltip Component */}
      <AnimatePresence>
        <TrendTooltip
          data={tooltipState.data}
          isVisible={tooltipState.isVisible}
          position={tooltipState.position}
          t={t}
        />
      </AnimatePresence>

      {/* Hero Section */}
      <section className="bg-gradient-to-br from-ngodb-navy via-ngodb-navy to-ngodb-red text-white py-16 -mt-20 md:-mt-[136px] xl:-mt-20 pt-36 md:pt-[156px] xl:pt-36">
        <motion.div
          className="w-full px-6 sm:px-8 lg:px-12 text-center"
          variants={staggerContainer}
          initial="hidden"
          animate="visible"
        >
          <motion.h1 className="text-4xl sm:text-5xl font-extrabold mb-6" variants={slideUp}>
            {t('disaggregationAnalysis.hero.title')}
          </motion.h1>
          <motion.p className="text-lg sm:text-xl max-w-4xl mx-auto mb-8" variants={slideUp}>
            {t('disaggregationAnalysis.hero.description')}
          </motion.p>

          {!isLoading && processedData.totalReached > 0 && (
            <motion.div
              className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4 max-w-6xl mx-auto"
              variants={staggerContainer}
            >
              <motion.div
                className="bg-white bg-opacity-10 backdrop-blur-sm rounded-lg p-4 min-w-[120px] relative cursor-pointer hover:bg-opacity-20 transition-all duration-200"
                variants={slideUp}
                onMouseMove={(e) => handleTooltip(e, stats.avgDisaggregation, 'disaggregation')}
                onMouseLeave={hideTooltip}
              >
                <div className="text-2xl font-bold text-white">
                  {stats.avgDisaggregation}%
                </div>
                <div className="text-sm text-ngodb-gray-200">{t('disaggregationAnalysis.stats.avgDisaggregation')}</div>
                <div className="absolute top-2 right-2 text-ngodb-gray-200 opacity-60">
                  <InfoIcon className="w-4 h-4" />
                </div>
              </motion.div>
              <motion.div
                className="bg-white bg-opacity-10 backdrop-blur-sm rounded-lg p-4 min-w-[120px] relative cursor-pointer hover:bg-opacity-20 transition-all duration-200"
                variants={slideUp}
                onMouseMove={(e) => handleTooltip(e, stats.avgAgeDisaggregation, 'age')}
                onMouseLeave={hideTooltip}
              >
                <div className="text-2xl font-bold text-white">
                  {stats.avgAgeDisaggregation}%
                </div>
                <div className="text-sm text-ngodb-gray-200">{t('disaggregationAnalysis.stats.ageDisaggregation')}</div>
                <div className="absolute top-2 right-2 text-ngodb-gray-200 opacity-60">
                  <InfoIcon className="w-4 h-4" />
                </div>
              </motion.div>
              <motion.div
                className="bg-white bg-opacity-10 backdrop-blur-sm rounded-lg p-4 min-w-[120px] relative cursor-pointer hover:bg-opacity-20 transition-all duration-200"
                variants={slideUp}
                onMouseMove={(e) => handleTooltip(e, stats.avgWomenLeadership, 'leadership')}
                onMouseLeave={hideTooltip}
              >
                <div className="text-2xl font-bold text-white">
                  {stats.avgWomenLeadership}%
                </div>
                <div className="text-sm text-ngodb-gray-200">{t('disaggregationAnalysis.stats.womenLeadership')}</div>
                <div className="absolute top-2 right-2 text-ngodb-gray-200 opacity-60">
                  <InfoIcon className="w-4 h-4" />
                </div>
              </motion.div>
              <motion.div
                className="bg-white bg-opacity-10 backdrop-blur-sm rounded-lg p-4 min-w-[120px] relative cursor-pointer hover:bg-opacity-20 transition-all duration-200"
                variants={slideUp}
                onMouseMove={(e) => handleTooltip(e, stats.avgWomenVolunteering, 'volunteering')}
                onMouseLeave={hideTooltip}
              >
                <div className="text-2xl font-bold text-white">
                  {stats.avgWomenVolunteering}%
                </div>
                <div className="text-sm text-ngodb-gray-200">{t('disaggregationAnalysis.stats.womenVolunteering')}</div>
                <div className="absolute top-2 right-2 text-ngodb-gray-200 opacity-60">
                  <InfoIcon className="w-4 h-4" />
                </div>
              </motion.div>
              <motion.div
                className="bg-white bg-opacity-10 backdrop-blur-sm rounded-lg p-4 min-w-[120px] relative cursor-pointer hover:bg-opacity-20 transition-all duration-200"
                variants={slideUp}
                onMouseMove={(e) => handleTooltip(e, stats.avgWomenStaff, 'staff')}
                onMouseLeave={hideTooltip}
              >
                <div className="text-2xl font-bold text-white">
                  {stats.avgWomenStaff}%
                </div>
                <div className="text-sm text-ngodb-gray-200">{t('disaggregationAnalysis.stats.womenStaff')}</div>
                <div className="absolute top-2 right-2 text-ngodb-gray-200 opacity-60">
                  <InfoIcon className="w-4 h-4" />
                </div>
              </motion.div>
            </motion.div>
          )}
        </motion.div>
      </section>

      {/* Filters Section */}
      <section className="bg-ngodb-gray-50 py-8">
        <div className="w-full px-6 sm:px-8 lg:px-12">
          <motion.div
            className="bg-white rounded-xl shadow-lg overflow-hidden"
            variants={slideUp}
            initial="hidden"
            animate="visible"
          >
            <div className="px-6 py-4 border-b border-ngodb-gray-200">
              <button
                onClick={() => setExpandedFilters(!expandedFilters)}
                className="flex items-center justify-between w-full text-left"
              >
                <div className="flex items-center space-x-3">
                  <Image src="/icons/funnel.svg" alt="Filters" width={24} height={24} className="text-ngodb-red" />
                  <h2 className="text-xl font-bold text-ngodb-navy">{t('disaggregationAnalysis.filters.title')}</h2>
                </div>
                <motion.div
                  animate={{ rotate: expandedFilters ? 180 : 0 }}
                  transition={{ duration: 0.2 }}
                >
                  <svg className="w-5 h-5 text-ngodb-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </motion.div>
              </button>
            </div>

            <AnimatePresence>
              {expandedFilters && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.3 }}
                  className="overflow-hidden"
                >
                  <div className="p-6">
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                      {/* Country Filter */}
                      <div>
                        <label className="block text-sm font-semibold text-ngodb-gray-700 mb-3">
                          {t('disaggregationAnalysis.filters.countries')}
                        </label>
                        <select
                          multiple
                          size="4"
                          className="w-full p-3 border border-ngodb-gray-300 rounded-lg focus:ring-2 focus:ring-ngodb-red focus:border-transparent"
                          value={filters.selectedCountries}
                          onChange={(e) => {
                            const values = Array.from(e.target.selectedOptions, option => option.value);
                            setFilters(prev => ({ ...prev, selectedCountries: values }));
                          }}
                        >
                          {filters.countries.map(country => (
                            <option key={country} value={country}>{country}</option>
                          ))}
                        </select>
                        <p className="text-xs text-ngodb-gray-500 mt-1">{t('disaggregationAnalysis.filters.selectMultiple')}</p>
                      </div>

                      {/* Period Filter */}
                      <div>
                        <label className="block text-sm font-semibold text-ngodb-gray-700 mb-3">
                          {t('disaggregationAnalysis.filters.period')}
                        </label>
                        <select
                          className="w-full p-3 border border-ngodb-gray-300 rounded-lg focus:ring-2 focus:ring-ngodb-red focus:border-transparent"
                          value={filters.selectedPeriod}
                          onChange={(e) => setFilters(prev => ({ ...prev, selectedPeriod: e.target.value }))}
                        >
                          <option value="">{t('disaggregationAnalysis.filters.allPeriods')}</option>
                          {filters.periods.map(period => (
                            <option key={period} value={period}>{period}</option>
                          ))}
                        </select>
                      </div>

                      {/* Indicator Filter */}
                      <div>
                        <label className="block text-sm font-semibold text-ngodb-gray-700 mb-3">
                          {t('disaggregationAnalysis.filters.indicator')}
                        </label>
                        <select
                          className="w-full p-3 border border-ngodb-gray-300 rounded-lg focus:ring-2 focus:ring-ngodb-red focus:border-transparent"
                          value={filters.selectedIndicator}
                          onChange={(e) => setFilters(prev => ({ ...prev, selectedIndicator: e.target.value }))}
                        >
                          <option value="">{t('disaggregationAnalysis.filters.allIndicators')}</option>
                          {filters.indicators.map(indicator => (
                            <option key={indicator.id} value={indicator.id}>{indicator.name}</option>
                          ))}
                        </select>
                      </div>

                      {/* Chart Type */}
                      <div>
                        <label className="block text-sm font-semibold text-ngodb-gray-700 mb-3">
                          {t('disaggregationAnalysis.filters.chartType')}
                        </label>
                        <select
                          className="w-full p-3 border border-ngodb-gray-300 rounded-lg focus:ring-2 focus:ring-ngodb-red focus:border-transparent"
                          value={chartType}
                          onChange={(e) => setChartType(e.target.value)}
                        >
                          <option value="bar">{t('disaggregationAnalysis.filters.barChart')}</option>
                          <option value="pie">{t('disaggregationAnalysis.filters.pieChart')}</option>
                          <option value="line">{t('disaggregationAnalysis.filters.lineChart')}</option>
                        </select>
                      </div>
                    </div>

                    <div className="mt-6 flex flex-wrap gap-3">
                      <button
                        onClick={() => setFilters(prev => ({
                          ...prev,
                          selectedCountries: [],
                          selectedPeriod: '',
                          selectedIndicator: ''
                        }))}
                        className="px-4 py-2 bg-ngodb-gray-200 text-ngodb-gray-700 rounded-lg hover:bg-ngodb-gray-300 transition-colors font-medium"
                      >
                        {t('disaggregationAnalysis.filters.clearFilters')}
                      </button>
                      <button
                        onClick={fetchData}
                        className="px-4 py-2 bg-ngodb-red text-white rounded-lg hover:bg-ngodb-red-dark transition-colors font-medium"
                        disabled={isLoading}
                      >
                        {isLoading ? t('disaggregationAnalysis.filters.loading') : t('disaggregationAnalysis.filters.refreshData')}
                      </button>
                      <div className="flex-1"></div>
                      <div className="text-sm text-ngodb-gray-600 flex items-center">
                        <span className="inline-block w-2 h-2 bg-green-400 rounded-full mr-2"></span>
                        {t('disaggregationAnalysis.filters.disaggregatedRecords', {
                          count: rawData.filter(item => item.disaggregation_data && item.disaggregation_data.values).length,
                          total: rawData.length
                        })}
                      </div>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        </div>
      </section>

      {/* Tab Navigation */}
      <section className="bg-white border-b border-ngodb-gray-200 sticky top-20 md:top-[136px] xl:top-20 z-40">
        <div className="w-full px-6 sm:px-8 lg:px-12">
          <div className="flex space-x-1 overflow-x-auto">
            {[
              { id: 'overview', label: t('disaggregationAnalysis.tabs.overview'), icon: '/icons/analytics.svg' },
              { id: 'by-indicator', label: t('disaggregationAnalysis.tabs.byIndicator'), icon: '/icons/chart.svg' },
              { id: 'women-leadership', label: t('disaggregationAnalysis.tabs.womenLeadership'), icon: '/icons/woman-leader.svg' },
              { id: 'by-sex', label: t('disaggregationAnalysis.tabs.bySex'), icon: '/icons/users-group.svg' },
              { id: 'by-age', label: t('disaggregationAnalysis.tabs.byAge'), icon: '/icons/age-groups.svg' },
              { id: 'by-sex-age', label: t('disaggregationAnalysis.tabs.bySexAge'), icon: '/icons/trending-up.svg' },
              { id: 'by-country', label: t('disaggregationAnalysis.tabs.byCountry'), icon: '/icons/globe.svg' },
              { id: 'country-disaggregation', label: t('disaggregationAnalysis.tabs.countryDisaggregation'), icon: '/icons/coverage.svg' },
              { id: 'trends', label: t('disaggregationAnalysis.tabs.trends'), icon: '/icons/calendar.svg' }
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`py-4 px-4 font-semibold border-b-2 transition-all duration-200 whitespace-nowrap flex items-center space-x-2 ${
                  activeTab === tab.id
                    ? 'text-ngodb-red border-ngodb-red bg-ngodb-red bg-opacity-5'
                    : 'text-ngodb-gray-600 border-transparent hover:text-ngodb-red hover:border-ngodb-red hover:border-opacity-50'
                }`}
              >
                <Image src={tab.icon} alt={tab.label} width={20} height={20} />
                <span>{tab.label}</span>
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* Content Section */}
      <section className="py-16 bg-ngodb-gray-50 min-h-screen">
        <div className="w-full px-6 sm:px-8 lg:px-12">
          {isLoading ? (
            <div className="text-center py-20">
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
                className="w-16 h-16 border-4 border-ngodb-red border-t-transparent rounded-full mx-auto mb-4"
              ></motion.div>
              <p className="text-ngodb-gray-600 text-lg">{t('disaggregationAnalysis.loading.message')}</p>
            </div>
          ) : (
            <AnimatePresence mode="wait">
              <motion.div
                key={activeTab}
                variants={slideUp}
                initial="hidden"
                animate="visible"
                exit="hidden"
                className="space-y-8"
              >
                {/* Overview Tab */}
                {activeTab === 'overview' && (
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                    <div className="bg-white rounded-xl shadow-lg p-6">
                      <div className="flex items-center justify-between mb-6">
                        <h3 className="text-xl font-bold text-ngodb-navy flex items-center">
                          <Image src="/icons/globe.svg" alt="Countries" width={24} height={24} className="mr-2" />
                          {t('disaggregationAnalysis.overview.topCountries')}
                        </h3>
                        {processedData.availableYears && processedData.availableYears.length > 0 && (
                          <select
                            className="px-3 py-2 border border-ngodb-gray-300 rounded-lg focus:ring-2 focus:ring-ngodb-red focus:border-transparent text-sm"
                            value={selectedYear || ''}
                            onChange={(e) => setSelectedYear(e.target.value ? parseInt(e.target.value) : null)}
                          >
                            <option value="">All Years</option>
                            {processedData.availableYears.map(year => (
                              <option key={year} value={year}>{year}</option>
                            ))}
                          </select>
                        )}
                      </div>
                      {processedData.byCountry.length > 0 ? (
                        <>
                          <MultiChart
                            data={processedData.byCountry.slice(0, 8)}
                            type={chartType}
                            title=""
                            height={350}
                          />
                          {selectedYear && (
                            <p className="text-xs text-ngodb-gray-500 mt-2 text-center">
                              Showing top indicator per country for {selectedYear}
                            </p>
                          )}
                        </>
                      ) : (
                        <div className="text-center py-12">
                          <Image src="/icons/analytics.svg" alt={t('data.noData')} width={64} height={64} className="mx-auto mb-4 opacity-50" />
                          <p className="text-ngodb-gray-500">{t('disaggregationAnalysis.overview.noData')}</p>
                        </div>
                      )}
                    </div>

                    <div className="bg-white rounded-xl shadow-lg p-6">
                      <h3 className="text-xl font-bold text-ngodb-navy mb-6 flex items-center">
                        <Image src="/icons/users-group.svg" alt="Sex Distribution" width={24} height={24} className="mr-2" />
                        {t('disaggregationAnalysis.overview.overallDistribution')}
                      </h3>
                      {processedData.bySex.length > 0 ? (
                        <MultiChart
                          data={processedData.bySex}
                          type="pie"
                          title=""
                          height={350}
                        />
                      ) : (
                        <div className="text-center py-12">
                          <Image src="/icons/users-group.svg" alt={t('data.noData')} width={64} height={64} className="mx-auto mb-4 opacity-50" />
                          <p className="text-ngodb-gray-500">{t('disaggregationAnalysis.overview.noData')}</p>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* By Indicator Tab */}
                {activeTab === 'by-indicator' && (
                  <div className="bg-white rounded-xl shadow-lg p-8">
                    <h3 className="text-2xl font-bold text-ngodb-navy mb-8 flex items-center">
                      <Image src="/icons/chart.svg" alt="Indicators" width={28} height={28} className="mr-3" />
                      {t('disaggregationAnalysis.byIndicator.title')}
                    </h3>
                    {processedData.byIndicator.length > 0 ? (
                      <MultiChart
                        data={processedData.byIndicator}
                        type="bar"
                        stackedMode={true}
                        title={t('disaggregationAnalysis.byIndicator.description')}
                        height={600}
                      />
                    ) : (
                      <div className="text-center py-16">
                        <Image src="/icons/chart.svg" alt={t('data.noData')} width={80} height={80} className="mx-auto mb-6 opacity-50" />
                        <p className="text-ngodb-gray-500 text-lg">{t('disaggregationAnalysis.byIndicator.noData')}</p>
                        <p className="text-ngodb-gray-400 text-sm mt-2">{t('disaggregationAnalysis.byIndicator.noDataDescription')}</p>
                      </div>
                    )}
                  </div>
                )}

                {/* Women in Leadership Tab */}
                {activeTab === 'women-leadership' && (
                  <div className="space-y-8">
                    {/* Leadership vs Staff vs Volunteering Comparison */}
                    <div className="bg-white rounded-xl shadow-lg p-8">
                      <h3 className="text-2xl font-bold text-ngodb-navy mb-8 flex items-center">
                        <Image src="/icons/woman-leader.svg" alt="Women in Leadership" width={28} height={28} className="mr-3" />
                        {t('disaggregationAnalysis.womenLeadership.comparison')}
                      </h3>
                      {processedData.womenInLeadership.comparison.length > 0 ? (
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                          <MultiChart
                            data={processedData.womenInLeadership.comparison.map(item => ({
                              label: item.label,
                              value: item.percentage
                            }))}
                            type="bar"
                            title={t('disaggregationAnalysis.womenLeadership.representationPercentage')}
                            height={300}
                          />
                          <div className="space-y-4">
                            {processedData.womenInLeadership.comparison.map((item, index) => (
                              <div key={index} className="bg-ngodb-gray-50 rounded-lg p-4">
                                <div className="flex justify-between items-center mb-2">
                                  <h4 className="font-semibold text-ngodb-navy">{item.label}</h4>
                                  <span className={`px-2 py-1 rounded text-sm font-bold ${
                                    item.percentage >= 50 ? 'bg-green-100 text-green-800' :
                                    item.percentage >= 30 ? 'bg-yellow-100 text-yellow-800' :
                                    'bg-red-100 text-red-800'
                                  }`}>
                                    {item.percentage}%
                                  </span>
                                </div>
                                <div className="text-sm text-ngodb-gray-600">
                                  {t('disaggregationAnalysis.womenLeadership.womenOutOf', {
                                    value: formatNumber(item.value),
                                    total: formatNumber(item.total)
                                  })}
                                </div>
                                <div className="w-full bg-ngodb-gray-200 rounded-full h-2 mt-2">
                                  <div
                                    className="bg-ngodb-red h-2 rounded-full transition-all duration-500"
                                    style={{ width: `${item.percentage}%` }}
                                  ></div>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      ) : (
                        <div className="text-center py-16">
                          <Image src="/icons/woman-leader.svg" alt={t('data.noData')} width={80} height={80} className="mx-auto mb-6 opacity-50" />
                          <p className="text-ngodb-gray-500 text-lg">{t('disaggregationAnalysis.womenLeadership.noData')}</p>
                        </div>
                      )}
                    </div>

                    {/* Country Leadership Analysis */}
                    {processedData.womenInLeadership.leadership.length > 0 && (
                      <div className="bg-white rounded-xl shadow-lg p-8">
                        <h3 className="text-xl font-bold text-ngodb-navy mb-6 flex items-center">
                          <Image src="/icons/globe.svg" alt="Countries" width={24} height={24} className="mr-2" />
                          {t('disaggregationAnalysis.womenLeadership.byCountry')}
                        </h3>
                        <MultiChart
                          data={processedData.womenInLeadership.leadership.slice(0, 15).map(item => ({
                            label: item.label,
                            value: item.femalePercentage
                          }))}
                          type="bar"
                          title={t('disaggregationAnalysis.womenLeadership.percentageTitle')}
                          height={400}
                        />
                      </div>
                    )}

                    {/* Trends Over Time */}
                    {processedData.womenInLeadership.trends.length > 0 && (
                      <div className="bg-white rounded-xl shadow-lg p-8">
                        <h3 className="text-xl font-bold text-ngodb-navy mb-6 flex items-center">
                          <Image src="/icons/trending-up.svg" alt="Trends" width={24} height={24} className="mr-2" />
                          Women's Participation Trends
                        </h3>
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                          <MultiChart
                            data={processedData.womenInLeadership.trends.map(item => ({
                              label: item.label,
                              value: item.leadershipPercentage
                            }))}
                            type="line"
                            title={t('disaggregationAnalysis.womenLeadership.leadershipOverTime')}
                            height={300}
                          />
                          <MultiChart
                            data={processedData.womenInLeadership.trends.map(item => ({
                              label: item.label,
                              value: item.volunteeringPercentage
                            }))}
                            type="line"
                            title={t('disaggregationAnalysis.womenLeadership.volunteeringOverTime')}
                            height={300}
                          />
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* By Sex Tab */}
                {activeTab === 'by-sex' && (
                  <div className="bg-white rounded-xl shadow-lg p-8">
                    <h3 className="text-2xl font-bold text-ngodb-navy mb-8 flex items-center">
                      <Image src="/icons/users-group.svg" alt="Sex Analysis" width={28} height={28} className="mr-3" />
                      {t('disaggregationAnalysis.bySex.title')}
                    </h3>
                    {processedData.bySex.length > 0 ? (
                      <MultiChart
                        data={processedData.bySex}
                        type={chartType}
                        title={t('disaggregationAnalysis.bySex.description')}
                        height={450}
                      />
                    ) : (
                      <div className="text-center py-16">
                        <Image src="/icons/users-group.svg" alt={t('data.noData')} width={80} height={80} className="mx-auto mb-6 opacity-50" />
                        <p className="text-ngodb-gray-500 text-lg">{t('disaggregationAnalysis.bySex.noData')}</p>
                      </div>
                    )}
                  </div>
                )}

                {/* By Age Tab */}
                {activeTab === 'by-age' && (
                  <div className="bg-white rounded-xl shadow-lg p-8">
                    <h3 className="text-2xl font-bold text-ngodb-navy mb-8 flex items-center">
                      <Image src="/icons/age-groups.svg" alt="Age Groups" width={28} height={28} className="mr-3" />
                      {t('disaggregationAnalysis.byAge.title')}
                    </h3>
                    {processedData.byAge.length > 0 ? (
                      <MultiChart
                        data={processedData.byAge}
                        type={chartType}
                        title={t('disaggregationAnalysis.byAge.description')}
                        height={450}
                      />
                    ) : (
                      <div className="text-center py-16">
                        <Image src="/icons/age-groups.svg" alt={t('data.noData')} width={80} height={80} className="mx-auto mb-6 opacity-50" />
                        <p className="text-ngodb-gray-500 text-lg">{t('disaggregationAnalysis.byAge.noData')}</p>
                      </div>
                    )}
                  </div>
                )}

                {/* By Sex & Age Tab */}
                {activeTab === 'by-sex-age' && (
                  <div className="bg-white rounded-xl shadow-lg p-8">
                    <h3 className="text-2xl font-bold text-ngodb-navy mb-8 flex items-center">
                      <Image src="/icons/trending-up.svg" alt="Sex and Age" width={28} height={28} className="mr-3" />
                      {t('disaggregationAnalysis.bySexAge.title')}
                    </h3>
                    {processedData.bySexAge.length > 0 ? (
                      <MultiChart
                        data={processedData.bySexAge}
                        type={chartType}
                        title={t('disaggregationAnalysis.bySexAge.description')}
                        height={450}
                      />
                    ) : (
                      <div className="text-center py-16">
                        <Image src="/icons/trending-up.svg" alt={t('data.noData')} width={80} height={80} className="mx-auto mb-6 opacity-50" />
                        <p className="text-ngodb-gray-500 text-lg">{t('disaggregationAnalysis.bySexAge.noData')}</p>
                      </div>
                    )}
                  </div>
                )}

                {/* By Country Tab */}
                {activeTab === 'by-country' && (
                  <div className="bg-white rounded-xl shadow-lg p-8">
                    <h3 className="text-2xl font-bold text-ngodb-navy mb-8 flex items-center">
                      <Image src="/icons/globe.svg" alt="Countries" width={28} height={28} className="mr-3" />
                      {t('disaggregationAnalysis.byCountry.title')}
                    </h3>
                    {processedData.byCountry.length > 0 ? (
                      <MultiChart
                        data={processedData.byCountry}
                        type={chartType}
                        title={t('disaggregationAnalysis.byCountry.description')}
                        height={450}
                      />
                    ) : (
                      <div className="text-center py-16">
                        <Image src="/icons/globe.svg" alt={t('data.noData')} width={80} height={80} className="mx-auto mb-6 opacity-50" />
                        <p className="text-ngodb-gray-500 text-lg">{t('disaggregationAnalysis.byCountry.noData')}</p>
                      </div>
                    )}
                  </div>
                )}

                {/* Country Disaggregation Coverage Tab */}
                {activeTab === 'country-disaggregation' && (
                  <div className="bg-white rounded-xl shadow-lg p-8">
                    <div className="flex items-center justify-between mb-8">
                      <h3 className="text-2xl font-bold text-ngodb-navy flex items-center">
                        <Image src="/icons/coverage.svg" alt="Coverage" width={28} height={28} className="mr-3" />
                        {t('disaggregationAnalysis.coverage.title')}
                      </h3>

                      {/* Download Buttons */}
                      <div className="flex items-center space-x-2">
                        <button
                          onClick={handleDownloadCSV}
                          disabled={isDownloadingCSV || isLoading || processedData.countryDisaggregation.length === 0}
                          className="p-2 rounded-lg text-white transition-all duration-200 shadow-md border-2"
                          title={t('disaggregationAnalysis.coverage.downloadCSV')}
                          style={{
                            minWidth: '32px',
                            minHeight: '32px',
                            backgroundColor: isDownloadingCSV || isLoading || processedData.countryDisaggregation.length === 0 ? '#9CA3AF' : '#28A745',
                            borderColor: isDownloadingCSV || isLoading || processedData.countryDisaggregation.length === 0 ? '#9CA3AF' : '#28A745'
                          }}
                        >
                          {isDownloadingCSV ? (
                            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                          ) : (
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                            </svg>
                          )}
                        </button>


                      </div>
                    </div>
                    {processedData.countryDisaggregation.length > 0 ? (
                      <div className="space-y-8" id="coverage-container">
                        {/* Regional Summary */}
                        <div className="bg-ngodb-gray-50 rounded-lg p-6" id="regional-summary">
                          <div className="flex items-center justify-between mb-4">
                            <h5 className="text-md font-semibold text-ngodb-navy">Regional Summary</h5>
                            <button
                              onClick={() => handleDownloadPNG('regional-summary', t('data.regionalSummary'))}
                              disabled={isDownloadingPNG || isLoading}
                              className="px-3 py-1 rounded-lg text-white transition-all duration-200 shadow-md border-2 text-sm"
                              title={t('disaggregationAnalysis.coverage.downloadRegionalSummary')}
                              style={{
                                backgroundColor: isDownloadingPNG || isLoading ? '#9CA3AF' : '#3B82F6',
                                borderColor: isDownloadingPNG || isLoading ? '#9CA3AF' : '#3B82F6'
                              }}
                            >
                              {isDownloadingPNG ? (
                                <div className="animate-spin rounded-full h-3 w-3 border-b-2 border-white"></div>
                              ) : (
                                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                                </svg>
                              )}
                            </button>
                          </div>
                          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                            {(() => {
                              const regionGroups = groupCountriesByRegion(processedData.countryDisaggregation);
                              const sortedRegions = Object.keys(regionGroups).sort();

                              return sortedRegions.map(region => {
                                const countries = regionGroups[region];
                                const avgDisaggregation = Math.round(
                                  countries.reduce((sum, country) => sum + country.overallDisaggregation, 0) / countries.length
                                );
                                const totalCountries = countries.length;

                                return (
                                  <div key={region} className="bg-white rounded-lg p-4 border-l-4" style={{ borderLeftColor: getRegionColor(region) }}>
                                    <div className="flex items-center justify-between mb-2">
                                      <h6 className="font-semibold text-ngodb-navy">{region}</h6>
                                      <span className={`px-2 py-1 text-xs font-bold rounded-full ${
                                        avgDisaggregation >= 75 ? 'bg-green-100 text-green-800' :
                                        avgDisaggregation >= 50 ? 'bg-yellow-100 text-yellow-800' :
                                        'bg-red-100 text-red-800'
                                      }`}>
                                        {avgDisaggregation}%
                                      </span>
                                    </div>
                                    <div className="text-sm text-ngodb-gray-600">
                                      {totalCountries} countries
                                    </div>
                                    <div className="w-full bg-ngodb-gray-200 rounded-full h-2 mt-2">
                                      <div
                                        className="h-2 rounded-full transition-all duration-500"
                                        style={{
                                          width: `${avgDisaggregation}%`,
                                          backgroundColor: getRegionColor(region)
                                        }}
                                      ></div>
                                    </div>
                                  </div>
                                );
                              });
                            })()}
                          </div>
                        </div>

                        {/* Regional Breakdown */}
                        <div>
                          <h4 className="text-lg font-semibold text-ngodb-navy mb-6">Detailed Breakdown by Region</h4>
                          {(() => {
                            const regionGroups = groupCountriesByRegion(processedData.countryDisaggregation);
                            const sortedRegions = Object.keys(regionGroups).sort();

                            return (
                              <div className="space-y-6">
                                {sortedRegions.map(region => {
                                  const countries = regionGroups[region];
                                  const avgDisaggregation = Math.round(
                                    countries.reduce((sum, country) => sum + country.overallDisaggregation, 0) / countries.length
                                  );

                                  return (
                                    <div key={region} className="border border-ngodb-gray-200 rounded-lg overflow-hidden" id={`region-${region.toLowerCase().replace(/\s+/g, '-')}`}>
                                      {/* Region Header */}
                                      <div
                                        className="px-6 py-4 font-bold text-white flex items-center justify-between"
                                        style={{ backgroundColor: getRegionColor(region) }}
                                      >
                                        <div className="flex items-center">
                                          <div className="w-3 h-3 rounded-full mr-3" style={{ backgroundColor: 'white' }}></div>
                                          {region} ({countries.length} countries)
                                        </div>
                                        <div className="flex items-center space-x-3">
                                          <div className="text-right">
                                            <div className="text-sm opacity-90">Average</div>
                                            <div className="text-xl">{avgDisaggregation}%</div>
                                          </div>
                                          <button
                                            onClick={() => handleDownloadPNG(`region-${region.toLowerCase().replace(/\s+/g, '-')}`, region)}
                                            disabled={isDownloadingPNG || isLoading}
                                            className="px-2 py-1 rounded text-white transition-all duration-200 shadow-md border border-white text-xs"
                                            title={t('disaggregationAnalysis.coverage.downloadRegion', { region })}
                                            style={{
                                              backgroundColor: 'rgba(255, 255, 255, 0.2)',
                                              borderColor: 'rgba(255, 255, 255, 0.3)'
                                            }}
                                          >
                                            {isDownloadingPNG ? (
                                              <div className="animate-spin rounded-full h-3 w-3 border-b-2 border-white"></div>
                                            ) : (
                                              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                                              </svg>
                                            )}
                                          </button>
                                        </div>
                                      </div>

                                      {/* Countries Table */}
                                      <div className="overflow-x-auto">
                                        <table className="min-w-full bg-white">
                                          <thead className="bg-ngodb-gray-50">
                                            <tr>
                                              <th className="px-4 py-3 text-left text-xs font-medium text-ngodb-gray-500 uppercase tracking-wider">Country</th>
                                              <th className="px-4 py-3 text-left text-xs font-medium text-ngodb-gray-500 uppercase tracking-wider">Total Records</th>
                                              <th className="px-4 py-3 text-left text-xs font-medium text-ngodb-gray-500 uppercase tracking-wider">Sex %</th>
                                              <th className="px-4 py-3 text-left text-xs font-medium text-ngodb-gray-500 uppercase tracking-wider">Age %</th>
                                              <th className="px-4 py-3 text-left text-xs font-medium text-ngodb-gray-500 uppercase tracking-wider">Sex+Age %</th>
                                              <th className="px-4 py-3 text-left text-xs font-medium text-ngodb-gray-500 uppercase tracking-wider">Overall %</th>
                                              <th className="px-4 py-3 text-left text-xs font-medium text-ngodb-gray-500 uppercase tracking-wider">Bar Chart</th>
                                            </tr>
                                          </thead>
                                          <tbody className="bg-white divide-y divide-ngodb-gray-200">
                                            {countries.map((item, index) => (
                                              <tr key={index} className="hover:bg-ngodb-gray-50">
                                                <td className="px-4 py-4 whitespace-nowrap text-sm font-medium text-ngodb-gray-900">{item.label}</td>
                                                <td className="px-4 py-4 whitespace-nowrap text-sm text-ngodb-gray-500">{item.totalItems}</td>
                                                <td className="px-4 py-4 whitespace-nowrap text-sm text-ngodb-gray-500">{item.sexPercentage}%</td>
                                                <td className="px-4 py-4 whitespace-nowrap text-sm text-ngodb-gray-500">{item.agePercentage}%</td>
                                                <td className="px-4 py-4 whitespace-nowrap text-sm text-ngodb-gray-500">{item.sexAgePercentage}%</td>
                                                <td className="px-4 py-4 whitespace-nowrap">
                                                  <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                                                    item.overallDisaggregation >= 75 ? 'bg-green-100 text-green-800' :
                                                    item.overallDisaggregation >= 50 ? 'bg-yellow-100 text-yellow-800' :
                                                    'bg-red-100 text-red-800'
                                                  }`}>
                                                    {item.overallDisaggregation}%
                                                  </span>
                                                </td>
                                                <td className="px-4 py-4 whitespace-nowrap">
                                                  <div className="flex items-center space-x-2">
                                                    <div className="w-24 bg-ngodb-gray-200 rounded-full h-3">
                                                      <div
                                                        className="h-3 rounded-full transition-all duration-300"
                                                        style={{
                                                          width: `${item.overallDisaggregation}%`,
                                                          backgroundColor: getRegionColor(region)
                                                        }}
                                                      ></div>
                                                    </div>
                                                    <span className="text-xs text-ngodb-gray-500 w-8 text-right">
                                                      {item.overallDisaggregation}%
                                                    </span>
                                                  </div>
                                                </td>
                                              </tr>
                                            ))}
                                          </tbody>
                                        </table>
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            );
                          })()}
                        </div>
                      </div>
                    ) : (
                      <div className="text-center py-16">
                        <Image src="/icons/coverage.svg" alt={t('data.noData')} width={80} height={80} className="mx-auto mb-6 opacity-50" />
                        <p className="text-ngodb-gray-500 text-lg">{t('disaggregationAnalysis.trends.noDisaggregationData')}</p>
                      </div>
                    )}
                  </div>
                )}

                {/* Trends Tab */}
                {activeTab === 'trends' && (
                  <div className="space-y-8">
                    {/* Women in Governing Board Trends */}
                    <div className="bg-white rounded-xl shadow-lg p-8">
                      <h3 className="text-2xl font-bold text-ngodb-navy mb-8 flex items-center">
                        <Image src="/icons/woman-leader.svg" alt="Women in Leadership" width={28} height={28} className="mr-3" />
                        Women in Governing Board - Trends Over Time
                      </h3>
                      {processedData.womenInLeadership.trends.length > 0 ? (
                        <MultiChart
                          data={processedData.womenInLeadership.trends.map(item => ({
                            label: item.label,
                            value: item.leadershipPercentage
                          }))}
                          type="line"
                          title={t('disaggregationAnalysis.trends.governingBoardTitle')}
                          height={400}
                        />
                      ) : (
                        <div className="text-center py-16">
                          <Image src="/icons/woman-leader.svg" alt={t('data.noData')} width={80} height={80} className="mx-auto mb-6 opacity-50" />
                          <p className="text-ngodb-gray-500 text-lg">{t('disaggregationAnalysis.trends.noGoverningBoardData')}</p>
                        </div>
                      )}
                    </div>

                    {/* Women in Staff Trends */}
                    <div className="bg-white rounded-xl shadow-lg p-8">
                      <h3 className="text-2xl font-bold text-ngodb-navy mb-8 flex items-center">
                        <Image src="/icons/users-group.svg" alt="Staff" width={28} height={28} className="mr-3" />
                        {t('disaggregationAnalysis.trends.staff')}
                      </h3>
                      {processedData.womenInLeadership.trends.length > 0 ? (
                        <MultiChart
                          data={processedData.womenInLeadership.trends.map(item => ({
                            label: item.label,
                            value: item.staffPercentage || 0
                          }))}
                          type="line"
                          title={t('disaggregationAnalysis.trends.staffTitle')}
                          height={400}
                        />
                      ) : (
                        <div className="text-center py-16">
                          <Image src="/icons/users-group.svg" alt={t('data.noData')} width={80} height={80} className="mx-auto mb-6 opacity-50" />
                          <p className="text-ngodb-gray-500 text-lg">{t('disaggregationAnalysis.trends.noStaffData')}</p>
                        </div>
                      )}
                    </div>

                    {/* Women in Volunteers Trends */}
                    <div className="bg-white rounded-xl shadow-lg p-8">
                      <h3 className="text-2xl font-bold text-ngodb-navy mb-8 flex items-center">
                        <Image src="/icons/trending-up.svg" alt="Volunteers" width={28} height={28} className="mr-3" />
                        {t('disaggregationAnalysis.trends.volunteers')}
                      </h3>
                      {processedData.womenInLeadership.trends.length > 0 ? (
                        <MultiChart
                          data={processedData.womenInLeadership.trends.map(item => ({
                            label: item.label,
                            value: item.volunteeringPercentage
                          }))}
                          type="line"
                          title={t('disaggregationAnalysis.trends.volunteersTitle')}
                          height={400}
                        />
                      ) : (
                        <div className="text-center py-16">
                          <Image src="/icons/trending-up.svg" alt={t('data.noData')} width={80} height={80} className="mx-auto mb-6 opacity-50" />
                          <p className="text-ngodb-gray-500 text-lg">{t('disaggregationAnalysis.trends.noVolunteersData')}</p>
                        </div>
                      )}
                    </div>

                    {/* Combined Trends Comparison */}
                    <div className="bg-white rounded-xl shadow-lg p-8">
                      <h3 className="text-2xl font-bold text-ngodb-navy mb-8 flex items-center">
                        <Image src="/icons/chart.svg" alt="Comparison" width={28} height={28} className="mr-3" />
                        Women's Participation Comparison - All Categories
                      </h3>
                      {processedData.womenInLeadership.trends.length > 0 ? (
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                          <div>
                            <h4 className="text-lg font-semibold text-ngodb-navy mb-4">Governing Board vs Staff vs Volunteers</h4>
                            <MultiChart
                              data={processedData.womenInLeadership.trends.map(item => ({
                                label: item.label,
                                governingBoard: item.leadershipPercentage,
                                staff: item.staffPercentage || 0,
                                volunteers: item.volunteeringPercentage
                              }))}
                              type="line"
                              title={t('disaggregationAnalysis.trends.comparisonDescription')}
                              height={350}
                            />
                          </div>
                          <div className="space-y-4">
                            <h4 className="text-lg font-semibold text-ngodb-navy mb-4">Latest Period Summary</h4>
                            {(() => {
                              const latestTrend = processedData.womenInLeadership.trends[processedData.womenInLeadership.trends.length - 1];
                              if (latestTrend) {
                                return (
                                  <div className="space-y-4">
                                    <div className="bg-ngodb-gray-50 rounded-lg p-4">
                                      <div className="flex justify-between items-center mb-2">
                                        <h5 className="font-semibold text-ngodb-navy">Governing Board</h5>
                                        <span className={`px-2 py-1 rounded text-sm font-bold ${
                                          latestTrend.leadershipPercentage >= 50 ? 'bg-green-100 text-green-800' :
                                          latestTrend.leadershipPercentage >= 30 ? 'bg-yellow-100 text-yellow-800' :
                                          'bg-red-100 text-red-800'
                                        }`}>
                                          {latestTrend.leadershipPercentage}%
                                        </span>
                                      </div>
                                      <div className="w-full bg-ngodb-gray-200 rounded-full h-2">
                                        <div
                                          className="bg-ngodb-red h-2 rounded-full transition-all duration-500"
                                          style={{ width: `${latestTrend.leadershipPercentage}%` }}
                                        ></div>
                                      </div>
                                    </div>

                                    <div className="bg-ngodb-gray-50 rounded-lg p-4">
                                      <div className="flex justify-between items-center mb-2">
                                        <h5 className="font-semibold text-ngodb-navy">Staff</h5>
                                        <span className={`px-2 py-1 rounded text-sm font-bold ${
                                          (latestTrend.staffPercentage || 0) >= 50 ? 'bg-green-100 text-green-800' :
                                          (latestTrend.staffPercentage || 0) >= 30 ? 'bg-yellow-100 text-yellow-800' :
                                          'bg-red-100 text-red-800'
                                        }`}>
                                          {latestTrend.staffPercentage || 0}%
                                        </span>
                                      </div>
                                      <div className="w-full bg-ngodb-gray-200 rounded-full h-2">
                                        <div
                                          className="bg-ngodb-blue h-2 rounded-full transition-all duration-500"
                                          style={{ width: `${latestTrend.staffPercentage || 0}%` }}
                                        ></div>
                                      </div>
                                    </div>

                                    <div className="bg-ngodb-gray-50 rounded-lg p-4">
                                      <div className="flex justify-between items-center mb-2">
                                        <h5 className="font-semibold text-ngodb-navy">Volunteers</h5>
                                        <span className={`px-2 py-1 rounded text-sm font-bold ${
                                          latestTrend.volunteeringPercentage >= 50 ? 'bg-green-100 text-green-800' :
                                          latestTrend.volunteeringPercentage >= 30 ? 'bg-yellow-100 text-yellow-800' :
                                          'bg-red-100 text-red-800'
                                        }`}>
                                          {latestTrend.volunteeringPercentage}%
                                        </span>
                                      </div>
                                      <div className="w-full bg-ngodb-gray-200 rounded-full h-2">
                                        <div
                                          className="bg-ngodb-green h-2 rounded-full transition-all duration-500"
                                          style={{ width: `${latestTrend.volunteeringPercentage}%` }}
                                        ></div>
                                      </div>
                                    </div>
                                  </div>
                                );
                              }
                              return <p className="text-ngodb-gray-500">No trend data available</p>;
                            })()}
                          </div>
                        </div>
                      ) : (
                        <div className="text-center py-16">
                          <Image src="/icons/chart.svg" alt={t('data.noData')} width={80} height={80} className="mx-auto mb-6 opacity-50" />
                          <p className="text-ngodb-gray-500 text-lg">{t('disaggregationAnalysis.trends.noComparisonData')}</p>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </motion.div>
            </AnimatePresence>
          )}
        </div>
      </section>


    </>
  );
}
