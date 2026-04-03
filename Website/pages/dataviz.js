// pages/dataviz.js - Explore Data
import Head from 'next/head';
import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { useTranslation } from '../lib/useTranslation';
import MultiChart from '../components/MultiChart';
import MultiSelectDropdown from '../components/MultiSelectDropdown';
import { getSectorsSubsectors, getAvailableIndicatorsWithData, getCountriesList, getAvailablePeriods, FDRS_TEMPLATE_ID } from '../lib/apiService';

// Cache keys for localStorage
const CACHE_KEYS = {
  SELECTED_SECTOR: 'dataviz_selected_sector',
  SELECTED_INDICATOR: 'dataviz_selected_indicator',
  SELECTED_COUNTRIES: 'dataviz_selected_countries',
  SELECTED_CHART_TYPE: 'dataviz_selected_chart_type',
  SELECTED_YEARS: 'dataviz_selected_years',
  CHART_DATA: 'dataviz_chart_data',
  SUMMARY_STATS: 'dataviz_summary_stats',
  VIEW_MODE: 'dataviz_view_mode',
  PERIOD_SELECTION_MODE: 'dataviz_period_selection_mode',
  SELECTED_SINGLE_YEAR: 'dataviz_selected_single_year',
  SELECTED_FROM_YEAR: 'dataviz_selected_from_year',
  SELECTED_TO_YEAR: 'dataviz_selected_to_year'
};

// Placeholder for dynamic indicators data
let indicators = [];
let sectors = [];

// Cache utility functions
const saveToCache = (key, data) => {
  try {
    // Check if we're in a browser environment
    if (typeof window === 'undefined') {
      return;
    }
    localStorage.setItem(key, JSON.stringify(data));
  } catch (error) {
    console.warn('Failed to save to cache:', error);
  }
};

const loadFromCache = (key, defaultValue = null) => {
  try {
    // Check if we're in a browser environment
    if (typeof window === 'undefined') {
      return defaultValue;
    }
    const cached = localStorage.getItem(key);
    return cached ? JSON.parse(cached) : defaultValue;
  } catch (error) {
    console.warn('Failed to load from cache:', error);
    return defaultValue;
  }
};

const clearCache = () => {
  try {
    // Check if we're in a browser environment
    if (typeof window === 'undefined') {
      return;
    }
    Object.values(CACHE_KEYS).forEach(key => localStorage.removeItem(key));
  } catch (error) {
    console.warn('Failed to clear cache:', error);
  }
};

// Countries will be loaded from API
let countries = [];

// Chart types - will be translated in component
const chartTypes = [
  { id: 'line', description: 'Shows trends over time' },
  { id: 'bar', description: 'Compares values across categories' },
  { id: 'pie', description: 'Shows proportions of a whole' }
];

export default function ExploreDataPage() {
  const { t } = useTranslation();

  // State management
  const [selectedSector, setSelectedSector] = useState('');
  const [selectedIndicator, setSelectedIndicator] = useState('');
  const [selectedCountries, setSelectedCountries] = useState([]);
  const [selectedChartType, setSelectedChartType] = useState('line');
  const [selectedYears, setSelectedYears] = useState([]);
  const [chartData, setChartData] = useState(null);
  const [summaryStats, setSummaryStats] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingData, setIsLoadingData] = useState(true);
  const [isRestoringCache, setIsRestoringCache] = useState(false);
  const [indicators, setIndicators] = useState([]);
  const [sectors, setSectors] = useState([]);
  const [filteredIndicators, setFilteredIndicators] = useState([]);
  const [availablePeriods, setAvailablePeriods] = useState([]);
  const [viewMode, setViewMode] = useState('chart'); // 'chart' or 'table'
  const [downloadData, setDownloadData] = useState(null);
  const [periodSelectionMode, setPeriodSelectionMode] = useState('range'); // 'single' or 'range'
  const [selectedSingleYear, setSelectedSingleYear] = useState(null);
  const [selectedFromYear, setSelectedFromYear] = useState(null);
  const [selectedToYear, setSelectedToYear] = useState(null);


  // Load cached data on component mount (client-side only)
  useEffect(() => {
    setSelectedSector(loadFromCache(CACHE_KEYS.SELECTED_SECTOR, ''));
    setSelectedIndicator(loadFromCache(CACHE_KEYS.SELECTED_INDICATOR, ''));
    setSelectedCountries(loadFromCache(CACHE_KEYS.SELECTED_COUNTRIES, []));
    setSelectedChartType(loadFromCache(CACHE_KEYS.SELECTED_CHART_TYPE, 'line'));
    // Don't load cached years here - let the periods loading effect handle it
    setChartData(loadFromCache(CACHE_KEYS.CHART_DATA, null));
    setSummaryStats(loadFromCache(CACHE_KEYS.SUMMARY_STATS, null));
    setViewMode(loadFromCache(CACHE_KEYS.VIEW_MODE, 'chart'));
    setDownloadData(loadFromCache(CACHE_KEYS.CHART_DATA, null)); // Initialize downloadData with chartData
    setPeriodSelectionMode(loadFromCache(CACHE_KEYS.PERIOD_SELECTION_MODE, 'range'));
    setSelectedSingleYear(loadFromCache(CACHE_KEYS.SELECTED_SINGLE_YEAR, null));
    setSelectedFromYear(loadFromCache(CACHE_KEYS.SELECTED_FROM_YEAR, null));
    setSelectedToYear(loadFromCache(CACHE_KEYS.SELECTED_TO_YEAR, null));
  }, []);

  // Save configuration to cache whenever it changes
  useEffect(() => {
    saveToCache(CACHE_KEYS.SELECTED_SECTOR, selectedSector);
  }, [selectedSector]);

  useEffect(() => {
    saveToCache(CACHE_KEYS.SELECTED_INDICATOR, selectedIndicator);
  }, [selectedIndicator]);

  useEffect(() => {
    saveToCache(CACHE_KEYS.SELECTED_COUNTRIES, selectedCountries);
  }, [selectedCountries]);

  useEffect(() => {
    saveToCache(CACHE_KEYS.SELECTED_CHART_TYPE, selectedChartType);
  }, [selectedChartType]);

  useEffect(() => {
    saveToCache(CACHE_KEYS.SELECTED_YEARS, selectedYears);
  }, [selectedYears]);

  useEffect(() => {
    saveToCache(CACHE_KEYS.CHART_DATA, chartData);
  }, [chartData]);

  useEffect(() => {
    saveToCache(CACHE_KEYS.SUMMARY_STATS, summaryStats);
  }, [summaryStats]);

  useEffect(() => {
    saveToCache(CACHE_KEYS.VIEW_MODE, viewMode);
  }, [viewMode]);

  useEffect(() => {
    saveToCache(CACHE_KEYS.CHART_DATA, downloadData); // Save downloadData to cache
  }, [downloadData]);

  useEffect(() => {
    saveToCache(CACHE_KEYS.PERIOD_SELECTION_MODE, periodSelectionMode);
  }, [periodSelectionMode]);

  useEffect(() => {
    saveToCache(CACHE_KEYS.SELECTED_SINGLE_YEAR, selectedSingleYear);
  }, [selectedSingleYear]);

  useEffect(() => {
    saveToCache(CACHE_KEYS.SELECTED_FROM_YEAR, selectedFromYear);
  }, [selectedFromYear]);

  useEffect(() => {
    saveToCache(CACHE_KEYS.SELECTED_TO_YEAR, selectedToYear);
  }, [selectedToYear]);

  // Load sectors and indicators on component mount
  useEffect(() => {
    const loadData = async () => {
      try {
        setIsLoadingData(true);

        // Load sectors, indicators, countries, and periods in parallel
        const [sectorsResponse, indicatorsResponse, countriesResponse, periodsResponse] = await Promise.all([
          getSectorsSubsectors('en'),
          getAvailableIndicatorsWithData('en'),
          getCountriesList(),
          getAvailablePeriods(FDRS_TEMPLATE_ID)
        ]);

        const sectorsData = sectorsResponse.sectors || [];
        const indicatorsData = indicatorsResponse || [];
        const countriesData = countriesResponse || [];
        const periodsData = periodsResponse || [];

        setSectors(sectorsData);
        setIndicators(indicatorsData);
        setFilteredIndicators(indicatorsData);
        setAvailablePeriods(periodsData);
        // Update the global countries variable
        countries = countriesData;
      } catch (error) {
        console.error('Error loading data:', error);
        // Fallback to sample data if API fails
        const fallbackSectors = [
          { name: 'Health', localized_name: 'Health' },
          { name: 'WASH', localized_name: 'WASH' },
          { name: 'Shelter', localized_name: 'Shelter' },
          { name: 'Food Security', localized_name: 'Food Security' },
          { name: 'Livelihoods', localized_name: 'Livelihoods' }
        ];

        const fallbackIndicators = [
          { id: 'volunteers', name: 'Volunteers', unit: 'People', sector: { name: 'Health' }, localized_name: 'Volunteers', localized_unit: 'People' },
          { id: 'staff', name: 'Staff', unit: 'People', sector: { name: 'Health' }, localized_name: 'Staff', localized_unit: 'People' },
          { id: 'local-units', name: 'Local Units', unit: 'Units', sector: { name: 'Shelter' }, localized_name: 'Local Units', localized_unit: 'Units' },
          { id: 'blood-donors', name: 'Blood Donors', unit: 'People', sector: { name: 'Health' }, localized_name: 'Blood Donors', localized_unit: 'People' },
          { id: 'first-aid', name: 'First Aid Training', unit: 'People', sector: { name: 'Health' }, localized_name: 'First Aid Training', localized_unit: 'People' },
          { id: 'people-reached', name: 'People Reached', unit: 'People', sector: { name: 'WASH' }, localized_name: 'People Reached', localized_unit: 'People' },
          { id: 'income', name: 'Income', unit: 'USD', sector: { name: 'Livelihoods' }, localized_name: 'Income', localized_unit: 'USD' },
          { id: 'expenditure', name: 'Expenditure', unit: 'USD', sector: { name: 'Livelihoods' }, localized_name: 'Expenditure', localized_unit: 'USD' }
        ];

        const fallbackPeriods = ['2019', '2020', '2021', '2022', '2023'];

        setSectors(fallbackSectors);
        setIndicators(fallbackIndicators);
        setFilteredIndicators(fallbackIndicators);
        setAvailablePeriods(fallbackPeriods);

        // Fallback countries data
        const fallbackCountries = [
          { code: 'AF', name: 'Afghanistan', region: 'Asia' },
          { code: 'PK', name: 'Pakistan', region: 'Asia' },
          { code: 'BD', name: 'Bangladesh', region: 'Asia' },
          { code: 'IN', name: 'India', region: 'Asia' },
          { code: 'NP', name: 'Nepal', region: 'Asia' }
        ];
        countries = fallbackCountries;
      } finally {
        setIsLoadingData(false);
      }
    };

    loadData();
  }, []);

  // Initialize selectedYears when availablePeriods are loaded
  useEffect(() => {
    if (availablePeriods.length > 0) {
      const availableYears = availablePeriods.map(period => {
        const yearMatch = period.match(/\d{4}/);
        return yearMatch ? parseInt(yearMatch[0]) : parseInt(period);
      }).sort((a, b) => b - a); // Sort descending (newest first)

      // Initialize single year selection if not set
      if (selectedSingleYear === null && availableYears.length > 0) {
        setSelectedSingleYear(availableYears[0]);
      }

      // Initialize range selection if not set
      if (selectedFromYear === null && availableYears.length > 0) {
        setSelectedFromYear(availableYears[availableYears.length - 1]); // Oldest
      }
      if (selectedToYear === null && availableYears.length > 0) {
        setSelectedToYear(availableYears[0]); // Newest
      }

      // Update selectedYears based on current mode
      updateSelectedYearsFromMode();
    }
  }, [availablePeriods, periodSelectionMode, selectedSingleYear, selectedFromYear, selectedToYear]);

  // Helper function to update selectedYears based on current selection mode
  const updateSelectedYearsFromMode = () => {
    if (periodSelectionMode === 'single' && selectedSingleYear) {
      setSelectedYears([selectedSingleYear]);
    } else if (periodSelectionMode === 'range' && selectedFromYear && selectedToYear) {
      const availableYears = availablePeriods.map(period => {
        const yearMatch = period.match(/\d{4}/);
        return yearMatch ? parseInt(yearMatch[0]) : parseInt(period);
      }).sort((a, b) => a - b); // Sort ascending for range

      const fromYear = Math.min(selectedFromYear, selectedToYear);
      const toYear = Math.max(selectedFromYear, selectedToYear);

      const rangeYears = availableYears.filter(year => year >= fromYear && year <= toYear);
      setSelectedYears(rangeYears);
    }
  };

  // Filter indicators when sector changes
  useEffect(() => {
    if (selectedSector) {
      const filtered = indicators.filter(indicator => {
        const indicatorSector = indicator.sector?.name || indicator.sector?.primary || indicator.sector;
        return indicatorSector === selectedSector;
      });
      setFilteredIndicators(filtered);
      // Only reset indicator if it's not valid in the current filtered list
      if (selectedIndicator && !filtered.find(ind => ind.id == selectedIndicator)) {
        setSelectedIndicator('');
      }
    } else {
      setFilteredIndicators(indicators);
    }
  }, [selectedSector, indicators, selectedIndicator]);

  // Validate cached indicator when indicators load
  useEffect(() => {
    if (indicators.length > 0 && selectedIndicator) {
      const isValidIndicator = indicators.find(ind => ind.id == selectedIndicator);
      if (!isValidIndicator) {
        setSelectedIndicator('');
        setChartData(null);
        setSummaryStats(null);
      }
    }
  }, [indicators, selectedIndicator]);

  // Validate cached countries after countries are loaded
  useEffect(() => {
    if (selectedCountries.length > 0 && countries.length > 0) {
      const validCountries = selectedCountries.filter(country =>
        countries.find(c => c.code === country.code)
      );
      if (validCountries.length !== selectedCountries.length) {
        setSelectedCountries(validCountries);
        // If countries changed, clear chart data
        if (validCountries.length === 0) {
          setChartData(null);
          setSummaryStats(null);
        }
      }
    }
  }, [selectedCountries, countries]);

  // Restore cached chart data after indicators are loaded and cache is restored
  useEffect(() => {
    if (indicators.length > 0 && !isLoadingData && selectedIndicator && selectedCountries.length > 0 && !chartData) {
      const cachedChartData = loadFromCache(CACHE_KEYS.CHART_DATA, null);
      if (cachedChartData) {
        setIsRestoringCache(true);
        setTimeout(() => {
          setChartData(cachedChartData);
          setSummaryStats(loadFromCache(CACHE_KEYS.SUMMARY_STATS, null));
          setIsRestoringCache(false);
        }, 500); // Small delay to show restoration
      }
    }
  }, [indicators.length, isLoadingData, selectedIndicator, selectedCountries, chartData]);



  // Generate sample data based on selections
  const extractYearFromPeriod = (periodName) => {
    if (!periodName || typeof periodName !== 'string') return 0;
    const yearMatch = periodName.match(/\b(20\d{2})\b/);
    if (yearMatch) return parseInt(yearMatch[1], 10);
    const numMatch = periodName.match(/\b(\d{4})\b/);
    return numMatch ? parseInt(numMatch[1], 10) : 0;
  };

  const extractNumericValue = (entry) => {
    const raw = entry?.answer_value != null ? entry.answer_value : (entry?.value != null ? entry.value : entry?.num_value);
    if (raw == null) return 0;
    if (typeof raw === 'number') return Number.isFinite(raw) ? raw : 0;
    if (typeof raw === 'string') {
      const parsed = parseFloat(raw);
      return Number.isFinite(parsed) ? parsed : 0;
    }
    if (typeof raw === 'object') {
      if (raw.values && raw.values.total != null) {
        const parsed = parseFloat(raw.values.total);
        return Number.isFinite(parsed) ? parsed : 0;
      }
      if (raw.total != null) {
        const parsed = parseFloat(raw.total);
        return Number.isFinite(parsed) ? parsed : 0;
      }
    }
    return 0;
  };

  const fetchAllIndicatorDataEntries = async (indicatorBankId) => {
    const perPage = 5000;
    const allRows = [];

    const fetchPage = async (page) => {
      const params = new URLSearchParams({
        template_id: String(FDRS_TEMPLATE_ID),
        indicator_bank_id: String(indicatorBankId),
        disagg: 'true',
        related: 'none',
        per_page: String(perPage),
        page: String(page)
      });
      const response = await fetch(`/api/backoffice/data/tables?${params.toString()}`);
      if (!response.ok) {
        throw new Error(`Failed to load data/tables page ${page}: ${response.status}`);
      }
      return await response.json();
    };

    const firstPage = await fetchPage(1);
    if (Array.isArray(firstPage?.data)) {
      allRows.push(...firstPage.data);
    }

    const totalPages = Number(firstPage?.total_pages || 1);
    for (let page = 2; page <= totalPages; page++) {
      const pageData = await fetchPage(page);
      if (Array.isArray(pageData?.data)) {
        allRows.push(...pageData.data);
      }
    }

    return allRows;
  };

  const generateChartData = async () => {
    if (!selectedIndicator || selectedCountries.length === 0) return null;

    const indicator = filteredIndicators.find(ind => ind.id == selectedIndicator); // Use == for type coercion
    if (!indicator) return null;

    const indicatorBankId = Number(selectedIndicator);
    if (!Number.isFinite(indicatorBankId)) return null;

    const selectedCountryRows = selectedCountries.map((country) => {
      const countryId = Number(country.id);
      if (Number.isFinite(countryId)) {
        return { id: countryId, name: country.name, code: country.code };
      }
      const fallback = (countries || []).find((c) => c.code === country.code);
      const fallbackId = Number(fallback?.id);
      return Number.isFinite(fallbackId)
        ? { id: fallbackId, name: country.name || fallback?.name, code: country.code || fallback?.code }
        : null;
    }).filter(Boolean);

    if (selectedCountryRows.length === 0) return null;
    if (!selectedYears || selectedYears.length === 0) return null;

    const selectedCountryIdSet = new Set(selectedCountryRows.map((c) => c.id));
    const selectedYearSet = new Set(selectedYears.map((year) => Number(year)).filter(Number.isFinite));
    const allEntries = await fetchAllIndicatorDataEntries(indicatorBankId);

    const valueByCountryYear = new Map();
    for (const entry of allEntries) {
      const countryId = Number(entry?.country_id);
      if (!Number.isFinite(countryId) || !selectedCountryIdSet.has(countryId)) continue;

      const year = extractYearFromPeriod(entry?.period_name || '');
      if (!Number.isFinite(year) || !selectedYearSet.has(year)) continue;

      const numericValue = extractNumericValue(entry);
      const key = `${countryId}|${year}`;
      valueByCountryYear.set(key, (valueByCountryYear.get(key) || 0) + numericValue);
    }

    const tableRows = [];
    for (const country of selectedCountryRows) {
      for (const year of selectedYears) {
        const normalizedYear = Number(year);
        const key = `${country.id}|${normalizedYear}`;
        tableRows.push({
          country: country.name,
          year: String(normalizedYear),
          value: Math.round(valueByCountryYear.get(key) || 0)
        });
      }
    }

    const smartDisplay = getSmartCountryDisplay(selectedCountries, countries || []);

    const lineData = selectedYears.map((year) => {
      const y = String(year);
      const total = tableRows
        .filter((row) => row.year === y)
        .reduce((sum, row) => sum + row.value, 0);
      return { label: y, value: total };
    });

    const barData = tableRows.map((row) => ({
      label: `${row.year} - ${row.country}`,
      value: row.value
    }));

    const pieMap = new Map();
    for (const row of tableRows) {
      pieMap.set(row.country, (pieMap.get(row.country) || 0) + row.value);
    }
    const pieData = Array.from(pieMap.entries()).map(([country, value]) => ({ label: country, value }));

    return {
      type: selectedChartType,
      title: `${indicator.localized_name || indicator.name} - ${smartDisplay.displayText}`,
      tableRows,
      data: selectedChartType === 'line'
        ? lineData
        : selectedChartType === 'bar'
        ? barData
        : pieData
    };
  };

  // Handle country selection
  const toggleCountry = (country) => {
    setSelectedCountries(prev =>
      prev.find(c => c.code === country.code)
        ? prev.filter(c => c.code !== country.code)
        : [...prev, country]
    );
  };

  // Smart display function for selected countries
  const getSmartCountryDisplay = (selectedCountries, allCountries) => {
    if (!selectedCountries || selectedCountries.length === 0) {
      return { displayText: 'No countries selected', type: 'none' };
    }

    // Check if allCountries is available
    if (!allCountries || !Array.isArray(allCountries) || allCountries.length === 0) {
      return {
        displayText: selectedCountries.length === 1 && selectedCountries[0]?.name ? selectedCountries[0].name : `${selectedCountries.length} countries selected`,
        type: 'count',
        completeRegions: [],
        partialCountries: selectedCountries
      };
    }

    // Check if all countries are selected
    if (selectedCountries.length === allCountries.length) {
      return { displayText: 'All countries', type: 'all' };
    }

    // Group countries by region
    const regionGroups = {};
    const regionCounts = {};

    // Count total countries per region
    allCountries.forEach(country => {
      const region = country.region || 'Other';
      regionCounts[region] = (regionCounts[region] || 0) + 1;
    });

    // Group selected countries by region
    selectedCountries.forEach(country => {
      const region = country.region || 'Other';
      if (!regionGroups[region]) {
        regionGroups[region] = [];
      }
      regionGroups[region].push(country);
    });

    const completeRegions = [];
    const partialRegions = [];

    // Identify complete and partial regions
    Object.entries(regionGroups).forEach(([region, countries]) => {
      if (countries.length === regionCounts[region]) {
        completeRegions.push(region);
      } else {
        partialRegions.push({ region, countries });
      }
    });

    // Build display text
    const displayParts = [];

    // Add complete regions
    if (completeRegions.length > 0) {
      displayParts.push(...completeRegions);
    }

    // Add individual countries from partial regions
    partialRegions.forEach(({ countries }) => {
      displayParts.push(...countries.map(c => c.name));
    });

    // Determine display strategy
    if (displayParts.length <= 3) {
      return {
        displayText: displayParts.join(', '),
        type: 'short',
        completeRegions,
        partialCountries: partialRegions.flatMap(p => p.countries)
      };
    } else if (completeRegions.length > 0 && partialRegions.length === 0) {
      return {
        displayText: completeRegions.join(', '),
        type: 'regions',
        completeRegions,
        partialCountries: []
      };
    } else {
      return {
        displayText: `${selectedCountries.length} countries selected`,
        type: 'count',
        completeRegions,
        partialCountries: partialRegions.flatMap(p => p.countries)
      };
    }
  };



  // Generate visualization
  const handleGenerateVisualization = async () => {
    setIsLoading(true);
    try {
      const data = await generateChartData();
      setChartData(data);
      setDownloadData(data); // Set download data
      setSummaryStats(null); // Reset summary stats
    } catch (error) {
      console.error('Failed to generate visualization from real data:', error);
      setChartData(null);
      setDownloadData(null);
      setSummaryStats(null);
    } finally {
      setIsLoading(false);
    }
  };

  // Download chart as PNG
  const downloadChart = () => {
    if (!chartData) return;

    // Create a canvas element
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    canvas.width = 1200;
    canvas.height = 800;

    // Fill background
    ctx.fillStyle = '#FFFFFF';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Add title
    ctx.fillStyle = '#011E41';
    ctx.font = 'bold 24px Inter';
    ctx.textAlign = 'center';
    ctx.fillText(chartData.title, canvas.width / 2, 40);

    // Footer label on exported chart
    ctx.fillStyle = '#ED1C24';
    ctx.font = '16px Inter';
    ctx.fillText('NGO Databank', canvas.width / 2, canvas.height - 20);

    // Convert to blob and download
    canvas.toBlob((blob) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${chartData.title.replace(/[^a-z0-9]/gi, '_').toLowerCase()}.png`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    });
  };

  // Download data as CSV
  const downloadDataAsCSV = () => {
    if (!chartData || !chartData.data) return;

    // Parse data based on chart type (same logic as table view)
    const parseCSVData = () => {
      const tableRows = Array.isArray(chartData.tableRows) ? chartData.tableRows : [];
      if (selectedChartType === 'line') {
        // For line charts, if multiple countries, create separate rows for each country
        if (selectedCountries.length > 1 && tableRows.length > 0) {
          return tableRows;
        } else {
          // Single country - no country column needed
          return chartData.data.map((item) => ({
            value: item.value,
            year: item.label
          }));
        }
      } else if (selectedChartType === 'bar') {
        // For bar charts, label contains "year - country"
        return chartData.data.map((item, index) => {
          const parts = item.label.split(' - ');
          return {
            value: item.value,
            year: parts[0] || '-',
            country: parts[1] || '-'
          };
        });
      } else if (selectedChartType === 'pie') {
        // For pie charts, label contains country, no year info
        return chartData.data.map((item, index) => ({
          value: item.value,
          year: 'All Years',
          country: item.label
        }));
      }
      return chartData.data;
    };

    const csvData = parseCSVData();
    const showCountryColumn = selectedCountries.length > 1 || selectedChartType === 'bar' || selectedChartType === 'pie';

    // Create CSV content
    const headers = showCountryColumn ? ['Value', 'Year', 'Country'] : ['Value', 'Year'];
    const csvContent = [
      headers.join(','),
      ...csvData.map(item => {
        const row = [
          item.value,
          `"${item.year}"`
        ];
        if (showCountryColumn) {
          row.push(`"${item.country}"`);
        }
        return row.join(',');
      })
    ].join('\n');

    // Create and download file
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${chartData.title.replace(/[^a-z0-9]/gi, '_').toLowerCase()}_data.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Render table view
  const renderTableView = () => {
    if (!chartData || !chartData.data) return null;

    // Parse data based on chart type
    const parseTableData = () => {
      const tableRows = Array.isArray(chartData.tableRows) ? chartData.tableRows : [];
      if (selectedChartType === 'line') {
        // For line charts, if multiple countries, create separate rows for each country
        if (selectedCountries.length > 1 && tableRows.length > 0) {
          return tableRows;
        } else {
          // Single country - no country column needed
          return chartData.data.map((item) => ({
            value: item.value,
            year: item.label
          }));
        }
      } else if (selectedChartType === 'bar') {
        // For bar charts, label contains "year - country"
        return chartData.data.map((item, index) => {
          const parts = item.label.split(' - ');
          return {
            value: item.value,
            year: parts[0] || '-',
            country: parts[1] || '-'
          };
        });
      } else if (selectedChartType === 'pie') {
        // For pie charts, label contains country, no year info
        return chartData.data.map((item, index) => ({
          value: item.value,
          year: 'All Years',
          country: item.label
        }));
      }
      return chartData.data;
    };

    const tableData = parseTableData();
    const showCountryColumn = selectedCountries.length > 1 || selectedChartType === 'bar' || selectedChartType === 'pie';

    return (
      <div className="overflow-x-auto">
        <table className="w-full border-collapse border border-ngodb-gray-200">
          <thead>
            <tr className="bg-ngodb-navy text-white">
              <th className="border border-ngodb-gray-200 px-4 py-3 text-left">{t('exploreData.chart.tableHeaders.value')}</th>
              <th className="border border-ngodb-gray-200 px-4 py-3 text-left">{t('exploreData.chart.tableHeaders.year')}</th>
              {showCountryColumn && (
                <th className="border border-ngodb-gray-200 px-4 py-3 text-left">{t('exploreData.chart.tableHeaders.country')}</th>
              )}
            </tr>
          </thead>
          <tbody>
            {tableData.map((item, index) => (
              <tr key={index} className={index % 2 === 0 ? 'bg-white' : 'bg-ngodb-gray-50'}>
                <td className="border border-ngodb-gray-200 px-4 py-3 font-medium text-ngodb-red">
                  {item.value.toLocaleString()}
                </td>
                <td className="border border-ngodb-gray-200 px-4 py-3">{item.year}</td>
                {showCountryColumn && (
                  <td className="border border-ngodb-gray-200 px-4 py-3">{item.country}</td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  // Placeholder component for when no chart is generated
  const ChartPlaceholder = () => (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6 }}
      className="bg-white rounded-xl shadow-lg border border-ngodb-gray-100 overflow-hidden"
    >
      <div className="bg-gradient-to-r from-ngodb-navy to-ngodb-navy-dark px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-xl font-bold text-white mb-1">{t('exploreData.placeholder.title')}</h3>
            <p className="text-ngodb-gray-200 text-sm">{t('exploreData.placeholder.subtitle')}</p>
          </div>
        </div>
      </div>

      <div className="p-12 text-center">
        <div className="max-w-md mx-auto">
          <div className="mb-6">
            <svg className="w-24 h-24 mx-auto text-ngodb-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
          </div>
          <h4 className="text-xl font-semibold text-ngodb-navy mb-3">{t('exploreData.placeholder.noChartGenerated')}</h4>
          <p className="text-ngodb-gray-600 mb-6">
            {t('exploreData.placeholder.description')}
          </p>
          <div className="space-y-3 text-sm text-ngodb-gray-500">
            <div className="flex items-center justify-center space-x-2">
              <div className="w-2 h-2 bg-ngodb-red rounded-full"></div>
              <span>{t('exploreData.placeholder.feature1')}</span>
            </div>
            <div className="flex items-center justify-center space-x-2">
              <div className="w-2 h-2 bg-ngodb-red rounded-full"></div>
              <span>{t('exploreData.placeholder.feature2')}</span>
            </div>
            <div className="flex items-center justify-center space-x-2">
              <div className="w-2 h-2 bg-ngodb-red rounded-full"></div>
              <span>{t('exploreData.placeholder.feature3')}</span>
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );

  const handleClearCache = () => {
    if (confirm(t('exploreData.confirmClearCache'))) {
      clearCache();
      // Reset all state to defaults
      setSelectedSector('');
      setSelectedIndicator('');
      setSelectedCountries([]);
      setSelectedChartType('line');
      // Reset years to empty array - the periods effect will handle initialization
      setSelectedYears([]);
      setChartData(null);
      setSummaryStats(null);
      setViewMode('chart');
      setDownloadData(null);
      setPeriodSelectionMode('range');
      setSelectedSingleYear(null);
      setSelectedFromYear(null);
      setSelectedToYear(null);
    }
  };

  return (
    <>
      <Head>
        <title>{t('exploreData.title')} - NGO Databank</title>
        <meta name="description" content={t('exploreData.meta.description')} />
      </Head>

      <div className="w-full px-4 sm:px-6 lg:px-8 py-10 pb-32">
        {/* Header */}
        <div className="text-center mb-12">
          <motion.h1
            className="text-4xl sm:text-5xl font-extrabold text-ngodb-navy mb-4"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            {t('exploreData.hero.title')}
          </motion.h1>
          <motion.p
            className="text-lg text-ngodb-gray-600 max-w-3xl mx-auto"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.2 }}
          >
            {t('exploreData.hero.description')}
          </motion.p>

        </div>

        <div className="w-full">
          {/* Main Layout - Left Pane for Controls, Right Pane for Chart */}
          <div className="grid lg:grid-cols-4 gap-8">
            {/* Left Pane - Controls */}
            <div className="lg:col-span-1">
              <motion.div
                className="bg-white rounded-xl shadow-lg p-6 sticky top-24 md:top-[144px] xl:top-24"
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.6, delay: 0.2 }}
              >
                <h2 className="text-2xl font-bold text-ngodb-navy mb-6">{t('exploreData.configure.title')}</h2>

                {/* Step 1: Indicator Selection */}
                <div className="mb-8">
                  <h3 className="text-lg font-semibold text-ngodb-navy mb-4 flex items-center">
                    <span className="w-6 h-6 bg-ngodb-red text-white rounded-full flex items-center justify-center text-sm font-bold mr-3">1</span>
                    {t('exploreData.configure.step1')}
                  </h3>

                  <div className="space-y-4">
                    {/* Sector Selection */}
                    <div>
                      <label className="block text-sm font-semibold text-ngodb-gray-700 mb-2">
                        {t('exploreData.configure.filterBySector')}
                      </label>
                      <select
                        value={selectedSector}
                        onChange={(e) => setSelectedSector(e.target.value)}
                        disabled={isLoadingData}
                        className="w-full px-3 py-2 border border-ngodb-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-ngodb-red focus:border-transparent disabled:bg-ngodb-gray-100"
                      >
                        <option value="">{t('exploreData.configure.allSectors')}</option>
                        {sectors.map(sector => (
                          <option key={sector.name} value={sector.name}>
                            {sector.localized_name || sector.name}
                          </option>
                        ))}
                      </select>
                    </div>

                    {/* Indicator Selection */}
                    <div>
                      <label className="block text-sm font-semibold text-ngodb-gray-700 mb-2">
                        {t('exploreData.configure.selectIndicator')}
                      </label>
                      <select
                        value={selectedIndicator}
                        onChange={(e) => setSelectedIndicator(e.target.value)}
                        disabled={isLoadingData || filteredIndicators.length === 0}
                        className="w-full px-3 py-2 border border-ngodb-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-ngodb-red focus:border-transparent disabled:bg-ngodb-gray-100"
                      >
                        <option value="">
                          {isLoadingData ? t('exploreData.configure.loading') : filteredIndicators.length === 0 ? t('exploreData.configure.noIndicatorsAvailable') : t('exploreData.configure.chooseIndicator')}
                        </option>
                        {filteredIndicators.map(indicator => (
                          <option key={indicator.id} value={indicator.id}>
                            {indicator.localized_name || indicator.name} ({indicator.localized_unit || indicator.unit})
                          </option>
                        ))}
                      </select>
                    </div>


                  </div>
                </div>

                {/* Step 2: Country Selection */}
                <div className="mb-8">
                  <h3 className="text-lg font-semibold text-ngodb-navy mb-4 flex items-center">
                    <span className="w-6 h-6 bg-ngodb-red text-white rounded-full flex items-center justify-center text-sm font-bold mr-3">2</span>
                    {t('exploreData.configure.step2')}
                  </h3>

                  <div>
                    <label className="block text-sm font-semibold text-ngodb-gray-700 mb-2">
                      {t('exploreData.configure.selectCountries')}
                    </label>
                    <MultiSelectDropdown
                      options={countries}
                      selectedOptions={selectedCountries}
                      onSelectionChange={setSelectedCountries}
                      placeholder={t('exploreData.configure.chooseCountries')}
                      groupBy="region"
                      searchable={true}
                      maxHeight="200px"
                    />

                    {/* Selected Countries Display */}
                    {selectedCountries.length > 0 && (
                      <div className="mt-3">
                        {(() => {
                          const smartDisplay = getSmartCountryDisplay(selectedCountries, countries || []);
                          return (
                            <>
                              <p className="text-xs text-ngodb-gray-600 mb-2">
                                {smartDisplay.type === 'all' ? t('exploreData.configure.allCountriesSelected') :
                                 smartDisplay.type === 'regions' ? t('exploreData.configure.regionsSelected', { count: smartDisplay.completeRegions.length }) :
                                 smartDisplay.type === 'short' ? t('exploreData.configure.selected') :
                                 t('exploreData.configure.countriesSelected', { count: selectedCountries.length })}
                              </p>

                              {smartDisplay.type === 'short' && (
                                <div className="text-xs text-ngodb-navy font-medium mb-2">
                                  {smartDisplay.displayText}
                                </div>
                              )}

                              {smartDisplay.type === 'regions' && (
                                <div className="text-xs text-ngodb-navy font-medium mb-2">
                                  {smartDisplay.completeRegions.join(', ')}
                                </div>
                              )}

                              {(smartDisplay.type === 'count' || selectedCountries.length <= 10) && (
                                <div className="flex flex-wrap gap-1">
                                  {selectedCountries.slice(0, 10).map(country => (
                                    <span
                                      key={country.code}
                                      className="inline-flex items-center px-2 py-1 rounded-full text-xs bg-ngodb-red text-white"
                                    >
                                      {country.name}
                                      <button
                                        onClick={() => toggleCountry(country)}
                                        className="ml-1 hover:bg-ngodb-red-dark rounded-full w-3 h-3 flex items-center justify-center"
                                      >
                                        ×
                                      </button>
                                    </span>
                                  ))}
                                  {selectedCountries.length > 10 && (
                                    <span className="inline-flex items-center px-2 py-1 rounded-full text-xs bg-ngodb-gray-400 text-white">
                                      +{selectedCountries.length - 10} more
                                    </span>
                                  )}
                                </div>
                              )}
                            </>
                          );
                        })()}
                      </div>
                    )}
                  </div>
                </div>

                {/* Step 3: Period & Chart Type */}
                <div className="mb-8">
                  <h3 className="text-lg font-semibold text-ngodb-navy mb-4 flex items-center">
                    <span className="w-6 h-6 bg-ngodb-red text-white rounded-full flex items-center justify-center text-sm font-bold mr-3">3</span>
                    {t('exploreData.configure.step3')}
                  </h3>

                  <div className="space-y-4">
                    {/* Chart Type Selection */}
                    <div>
                      <label className="block text-sm font-semibold text-ngodb-gray-700 mb-2">
                        {t('exploreData.configure.chartType')}
                      </label>
                      <select
                        value={selectedChartType}
                        onChange={(e) => setSelectedChartType(e.target.value)}
                        className="w-full px-3 py-2 border border-ngodb-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-ngodb-red focus:border-transparent"
                      >
                        {chartTypes.map(type => (
                          <option key={type.id} value={type.id}>
                            {t(`exploreData.chartTypes.${type.id}.name`)}
                          </option>
                        ))}
                      </select>
                    </div>

                    {/* Time Period Selection */}
                    <div>
                      <label className="block text-sm font-semibold text-ngodb-gray-700 mb-2">
                        {t('exploreData.configure.timePeriod')}
                      </label>

                      {/* Selection Mode Toggle */}
                      <div className="mb-3">
                        <div className="flex bg-ngodb-gray-100 rounded-lg p-1">
                          <button
                            type="button"
                            onClick={() => setPeriodSelectionMode('single')}
                            className={`flex-1 px-3 py-2 text-sm font-medium rounded-md transition-colors duration-150 ${
                              periodSelectionMode === 'single'
                                ? 'bg-white text-ngodb-red shadow-sm'
                                : 'text-ngodb-gray-600 hover:text-ngodb-gray-800'
                            }`}
                          >
                            {t('exploreData.configure.singleYear')}
                          </button>
                          <button
                            type="button"
                            onClick={() => setPeriodSelectionMode('range')}
                            className={`flex-1 px-3 py-2 text-sm font-medium rounded-md transition-colors duration-150 ${
                              periodSelectionMode === 'range'
                                ? 'bg-white text-ngodb-red shadow-sm'
                                : 'text-ngodb-gray-600 hover:text-ngodb-gray-800'
                            }`}
                          >
                            {t('exploreData.configure.range')}
                          </button>
                        </div>
                      </div>

                      {/* Single Year Selection */}
                      {periodSelectionMode === 'single' && (
                        <select
                          value={selectedSingleYear || ''}
                          onChange={(e) => setSelectedSingleYear(parseInt(e.target.value))}
                          disabled={isLoadingData || availablePeriods.length === 0}
                          className="w-full px-3 py-2 border border-ngodb-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-ngodb-red focus:border-transparent disabled:bg-ngodb-gray-100"
                        >
                          <option value="">
                            {isLoadingData ? t('exploreData.configure.loadingPeriods') : t('exploreData.configure.selectYear')}
                          </option>
                          {availablePeriods.map(period => {
                            const yearMatch = period.match(/\d{4}/);
                            const year = yearMatch ? parseInt(yearMatch[0]) : parseInt(period);
                            return (
                              <option key={year} value={year}>
                                {year}
                              </option>
                            );
                          })}
                        </select>
                      )}

                      {/* Range Selection */}
                      {periodSelectionMode === 'range' && (
                        <div className="space-y-3">
                          <div className="grid grid-cols-2 gap-3">
                            <div>
                              <label className="block text-xs font-medium text-ngodb-gray-600 mb-1">
                                {t('exploreData.configure.fromYear')}
                              </label>
                              <select
                                value={selectedFromYear || ''}
                                onChange={(e) => setSelectedFromYear(parseInt(e.target.value))}
                                disabled={isLoadingData || availablePeriods.length === 0}
                                className="w-full px-3 py-2 border border-ngodb-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-ngodb-red focus:border-transparent disabled:bg-ngodb-gray-100 text-sm"
                              >
                                <option value="">
                                  {isLoadingData ? t('exploreData.configure.loading') : t('exploreData.configure.from')}
                                </option>
                                {availablePeriods.map(period => {
                                  const yearMatch = period.match(/\d{4}/);
                                  const year = yearMatch ? parseInt(yearMatch[0]) : parseInt(period);
                                  return (
                                    <option key={year} value={year}>
                                      {year}
                                    </option>
                                  );
                                })}
                              </select>
                            </div>
                            <div>
                              <label className="block text-xs font-medium text-ngodb-gray-600 mb-1">
                                {t('exploreData.configure.toYear')}
                              </label>
                              <select
                                value={selectedToYear || ''}
                                onChange={(e) => setSelectedToYear(parseInt(e.target.value))}
                                disabled={isLoadingData || availablePeriods.length === 0}
                                className="w-full px-3 py-2 border border-ngodb-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-ngodb-red focus:border-transparent disabled:bg-ngodb-gray-100 text-sm"
                              >
                                <option value="">
                                  {isLoadingData ? t('exploreData.configure.loading') : t('exploreData.configure.to')}
                                </option>
                                {availablePeriods.map(period => {
                                  const yearMatch = period.match(/\d{4}/);
                                  const year = yearMatch ? parseInt(yearMatch[0]) : parseInt(period);
                                  return (
                                    <option key={year} value={year}>
                                      {year}
                                    </option>
                                  );
                                })}
                              </select>
                            </div>
                          </div>

                          {/* Range Preview */}
                          {selectedFromYear && selectedToYear && (
                            <div className="text-xs text-ngodb-gray-600 bg-ngodb-gray-50 px-3 py-2 rounded-lg">
                              {t('exploreData.configure.selectedRange', {
                                from: Math.min(selectedFromYear, selectedToYear),
                                to: Math.max(selectedFromYear, selectedToYear)
                              })}
                              {selectedYears.length > 0 && (
                                <span className="ml-2 text-ngodb-red font-medium">
                                  ({t('exploreData.configure.years', { count: selectedYears.length })})
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* Action Buttons */}
                <div className="space-y-3">
                  <button
                    onClick={handleGenerateVisualization}
                    disabled={
                      !selectedIndicator ||
                      selectedCountries.length === 0 ||
                      isLoading ||
                      (periodSelectionMode === 'single' && !selectedSingleYear) ||
                      (periodSelectionMode === 'range' && (!selectedFromYear || !selectedToYear))
                    }
                    className={`w-full px-6 py-3 rounded-lg font-semibold text-white transition-colors duration-150 ${
                      !selectedIndicator ||
                      selectedCountries.length === 0 ||
                      isLoading ||
                      (periodSelectionMode === 'single' && !selectedSingleYear) ||
                      (periodSelectionMode === 'range' && (!selectedFromYear || !selectedToYear))
                        ? 'bg-ngodb-gray-400 cursor-not-allowed'
                        : 'bg-ngodb-red hover:bg-ngodb-red-dark'
                    }`}
                  >
                    {isLoading ? t('exploreData.configure.generating') : t('exploreData.configure.generateChart')}
                  </button>

                  <button
                    onClick={handleClearCache}
                    className="w-full px-6 py-2 rounded-lg font-medium text-ngodb-gray-600 border border-ngodb-gray-300 hover:bg-ngodb-gray-50 transition-colors duration-150"
                  >
                    {t('exploreData.configure.clearSavedConfiguration')}
                  </button>
                </div>

                {/* Summary */}
                {(selectedIndicator || selectedCountries.length > 0) && (
                  <div className="mt-6 p-4 bg-ngodb-gray-50 rounded-lg border border-ngodb-gray-200">
                    <h4 className="font-semibold text-ngodb-navy mb-3 text-sm">{t('exploreData.configure.summary')}</h4>
                    <div className="space-y-2 text-xs">
                      <div className="flex justify-between">
                        <span className="text-ngodb-gray-600">{t('exploreData.configure.indicator')}</span>
                        <span className="font-medium">{filteredIndicators.find(ind => ind.id === selectedIndicator)?.localized_name || filteredIndicators.find(ind => ind.id === selectedIndicator)?.name || t('exploreData.configure.notSelected')}</span>
                      </div>
                            <div className="flex justify-between">
                              <span className="text-ngodb-gray-600">{t('exploreData.configure.countries')}</span>
                              <span className="font-medium">
                                {(() => {
                                  const smartDisplay = getSmartCountryDisplay(selectedCountries, countries || []);
                                  return smartDisplay.type === 'all' ? t('exploreData.configure.allCountriesSelected') :
                                         smartDisplay.type === 'regions' ? t('exploreData.configure.regionsSelected', { count: smartDisplay.completeRegions.length }) :
                                         t('exploreData.configure.countriesSelected', { count: selectedCountries.length });
                                })()}
                              </span>
                            </div>
                      <div className="flex justify-between">
                        <span className="text-ngodb-gray-600">{t('exploreData.configure.period')}</span>
                        <span className="font-medium">
                          {periodSelectionMode === 'single' && selectedSingleYear ?
                            selectedSingleYear :
                            selectedYears.length > 0 ?
                              `${selectedYears[0]} - ${selectedYears[selectedYears.length - 1]}` :
                              t('exploreData.configure.notSelected')
                          }
                        </span>
                      </div>
                    </div>
                  </div>
                )}
              </motion.div>
            </div>

            {/* Right Pane - Chart Display */}
            <div className="lg:col-span-3">
              {/* Chart Display */}
              {chartData ? (
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.6 }}
                  className="bg-white rounded-xl shadow-lg border border-ngodb-gray-100 mb-12 overflow-hidden"
                >
                  {/* Chart Header */}
                  <div className="bg-gradient-to-r from-ngodb-navy to-ngodb-navy-dark px-6 py-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <h3 className="text-xl font-bold text-white mb-1">{t('exploreData.chart.title')}</h3>
                        <p className="text-ngodb-gray-200 text-sm">{chartData.title}</p>
                      </div>
                      <div className="flex items-center space-x-3">
                        {/* View Toggle */}
                        <div className="flex items-center bg-ngodb-navy-dark rounded-lg p-1">
                          <button
                            onClick={() => setViewMode('chart')}
                            className={`px-3 py-1 rounded-md text-sm font-medium transition-colors duration-150 ${
                              viewMode === 'chart'
                                ? 'bg-ngodb-red text-white'
                                : 'text-ngodb-gray-200 hover:text-white'
                            }`}
                          >
                            <svg className="w-4 h-4 inline mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                            </svg>
                            {t('exploreData.chart.chart')}
                          </button>
                          <button
                            onClick={() => setViewMode('table')}
                            className={`px-3 py-1 rounded-md text-sm font-medium transition-colors duration-150 ${
                              viewMode === 'table'
                                ? 'bg-ngodb-red text-white'
                                : 'text-ngodb-gray-200 hover:text-white'
                            }`}
                          >
                            <svg className="w-4 h-4 inline mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 10h18M3 14h18m-9-4v8m-7 0h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                            </svg>
                            {t('exploreData.chart.table')}
                          </button>
                        </div>

                        <div className="text-right text-white">
                          <div className="text-xs text-ngodb-gray-200">{t('exploreData.chart.generatedOn')}</div>
                          <div className="text-sm font-medium">{new Date().toLocaleDateString()}</div>
                        </div>

                        {/* Download Buttons */}
                        <div className="flex items-center space-x-2">
                          <button
                            onClick={downloadDataAsCSV}
                            className="px-3 py-2 bg-ngodb-gray-600 text-white rounded-lg hover:bg-ngodb-gray-700 transition-colors duration-150 flex items-center space-x-2 shadow-lg"
                            title={t('exploreData.chart.downloadData')}
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                            </svg>
                            <span className="hidden sm:inline">{t('exploreData.chart.data')}</span>
                          </button>
                          <button
                            onClick={downloadChart}
                            className="px-4 py-2 bg-ngodb-red text-white rounded-lg hover:bg-ngodb-red-dark transition-colors duration-150 flex items-center space-x-2 shadow-lg"
                            title={t('exploreData.chart.downloadChart')}
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                            </svg>
                            <span>{t('exploreData.chart.chart')}</span>
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Chart Content */}
                  <div className="p-6">
                    <div className="grid lg:grid-cols-4 gap-6">
                      {/* Main Chart/Table */}
                      <div className="lg:col-span-3">
                        <div className="overflow-hidden">
                          {viewMode === 'chart' ? (
                            chartData.data && chartData.data.length > 0 ? (
                              <MultiChart
                                data={chartData.data}
                                type={chartData.type}
                                title=""
                                height={400}
                                onSummaryStats={setSummaryStats}
                              />
                            ) : (
                              <div className="flex items-center justify-center h-96 bg-ngodb-gray-50 rounded-lg">
                                <div className="text-center">
                                  <p className="text-ngodb-gray-600 mb-2">{t('exploreData.chart.noChartData')}</p>
                                  <p className="text-sm text-ngodb-gray-500">{t('exploreData.chart.checkConsole')}</p>
                                </div>
                              </div>
                            )
                          ) : (
                            renderTableView()
                          )}
                        </div>
                      </div>

                      {/* Chart Info Panel */}
                      <div className="space-y-6">
                        {/* Configuration Summary */}
                        <div className="bg-ngodb-gray-50 rounded-lg p-4 border border-ngodb-gray-200">
                          <h4 className="font-semibold text-ngodb-navy mb-3 flex items-center">
                            <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5H7a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                            </svg>
                            {t('exploreData.chart.configuration')}
                          </h4>
                          <div className="space-y-2 text-sm">
                            <div className="flex justify-between">
                              <span className="text-ngodb-gray-600">{t('exploreData.chart.sector')}</span>
                              <span className="font-medium text-ngodb-navy">
                                {selectedSector || t('exploreData.configure.allSectors')}
                              </span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-ngodb-gray-600">{t('exploreData.configure.indicator')}</span>
                              <span className="font-medium text-ngodb-navy">
                                {filteredIndicators.find(ind => ind.id === selectedIndicator)?.localized_name || filteredIndicators.find(ind => ind.id === selectedIndicator)?.name}
                              </span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-ngodb-gray-600">{t('exploreData.chart.chartType')}</span>
                              <span className="font-medium text-ngodb-navy">
                                {t(`exploreData.chartTypes.${selectedChartType}.name`)}
                              </span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-ngodb-gray-600">{t('exploreData.configure.countries')}</span>
                              <span className="font-medium text-ngodb-navy">
                                {(() => {
                                  const smartDisplay = getSmartCountryDisplay(selectedCountries, countries || []);
                                  return smartDisplay.type === 'all' ? t('exploreData.configure.allCountriesSelected') :
                                         smartDisplay.type === 'regions' ? t('exploreData.configure.regionsSelected', { count: smartDisplay.completeRegions.length }) :
                                         selectedCountries.length.toString();
                                })()}
                              </span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-ngodb-gray-600">{t('exploreData.chart.years')}</span>
                              <span className="font-medium text-ngodb-navy">
                                {periodSelectionMode === 'single' && selectedSingleYear ?
                                  selectedSingleYear :
                                  selectedYears.length > 0 ?
                                    `${selectedYears[0]} - ${selectedYears[selectedYears.length - 1]}` :
                                    t('exploreData.configure.notSelected')
                                }
                              </span>
                            </div>
                          </div>
                        </div>

                        {/* Data Summary */}
                        <div className="bg-ngodb-gray-50 rounded-lg p-4 border border-ngodb-gray-200">
                          <h4 className="font-semibold text-ngodb-navy mb-3 flex items-center">
                            <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                            </svg>
                            {t('exploreData.chart.dataSummary')}
                          </h4>
                          <div className="space-y-2 text-sm">
                            <div className="flex justify-between">
                              <span className="text-ngodb-gray-600">{t('exploreData.chart.totalDataPoints')}</span>
                              <span className="font-medium text-ngodb-navy">{chartData.data.length}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-ngodb-gray-600">{t('exploreData.chart.maxValue')}</span>
                              <span className="font-medium text-ngodb-red">
                                {Math.max(...chartData.data.map(d => d.value)).toLocaleString()}
                              </span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-ngodb-gray-600">{t('exploreData.chart.minValue')}</span>
                              <span className="font-medium text-ngodb-red">
                                {Math.min(...chartData.data.map(d => d.value)).toLocaleString()}
                              </span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-ngodb-gray-600">{t('exploreData.chart.average')}</span>
                              <span className="font-medium text-ngodb-red">
                                {Math.round(chartData.data.reduce((sum, d) => sum + d.value, 0) / chartData.data.length).toLocaleString()}
                              </span>
                            </div>
                          </div>
                        </div>

                        {/* Selected Countries */}
                        <div className="bg-ngodb-gray-50 rounded-lg p-4 border border-ngodb-gray-200">
                          <h4 className="font-semibold text-ngodb-navy mb-3 flex items-center">
                            <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                            {(() => {
                              const smartDisplay = getSmartCountryDisplay(selectedCountries, countries || []);
                              return smartDisplay.type === 'all' ? t('exploreData.chart.allCountries') :
                                     smartDisplay.type === 'regions' ? t('exploreData.chart.regions', { count: smartDisplay.completeRegions.length }) :
                                     t('exploreData.chart.countries', { count: selectedCountries.length });
                            })()}
                          </h4>
                          <div className="space-y-2 max-h-32 overflow-y-auto">
                            {(() => {
                              const smartDisplay = getSmartCountryDisplay(selectedCountries, countries || []);

                              if (smartDisplay.type === 'all') {
                                return (
                                  <div className="text-sm text-ngodb-navy font-medium">
                                    {t('exploreData.chart.allCountriesSelected')}
                                  </div>
                                );
                              }

                              if (smartDisplay.type === 'regions' && smartDisplay.completeRegions.length > 0) {
                                return (
                                  <div className="space-y-1">
                                    {smartDisplay.completeRegions.map(region => (
                                      <div key={region} className="text-sm">
                                        <span className="text-ngodb-navy font-medium">{region}</span>
                                        <span className="text-ngodb-gray-500 text-xs ml-2">{t('exploreData.chart.entireRegion')}</span>
                                      </div>
                                    ))}
                                  </div>
                                );
                              }

                              return (
                                <div className="space-y-1">
                                  {smartDisplay.completeRegions.length > 0 && (
                                    <>
                                      {smartDisplay.completeRegions.map(region => (
                                        <div key={region} className="text-sm">
                                          <span className="text-ngodb-navy font-medium">{region}</span>
                                          <span className="text-ngodb-gray-500 text-xs ml-2">{t('exploreData.chart.entireRegion')}</span>
                                        </div>
                                      ))}
                                      {smartDisplay.partialCountries.length > 0 && (
                                        <div className="border-t border-ngodb-gray-200 pt-2 mt-2"></div>
                                      )}
                                    </>
                                  )}
                                  {smartDisplay.partialCountries.slice(0, 8).map(country => (
                                    <div key={country.code} className="flex items-center justify-between text-sm">
                                      <span className="text-ngodb-gray-700">{country.name}</span>
                                      <span className="text-ngodb-gray-500 text-xs">{country.region}</span>
                                    </div>
                                  ))}
                                  {smartDisplay.partialCountries.length > 8 && (
                                    <div className="text-xs text-ngodb-gray-500 italic">
                                      {t('exploreData.chart.moreCountries', { count: smartDisplay.partialCountries.length - 8 })}
                                    </div>
                                  )}
                                </div>
                              );
                            })()}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Summary Stats - Outside Chart Container */}
                  {summaryStats && (
                    <motion.div
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.6, delay: 0.2 }}
                      className="mt-6 p-4 bg-ngodb-gray-50 rounded-lg border border-ngodb-gray-200"
                    >
                      <h4 className="font-semibold text-ngodb-navy mb-4 flex items-center">
                        <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                        </svg>
                        {t('exploreData.chart.keyStatistics')}
                      </h4>
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div className="text-center p-3 bg-white rounded-lg border border-ngodb-gray-200">
                          <div className="text-sm text-ngodb-gray-600 mb-1">{t('exploreData.chart.totalGrowth')}</div>
                          <div className="text-2xl font-bold text-ngodb-navy">{summaryStats.totalGrowth}%</div>
                        </div>
                        <div className="text-center p-3 bg-white rounded-lg border border-ngodb-gray-200">
                          <div className="text-sm text-ngodb-gray-600 mb-1">{t('exploreData.chart.currentTotal')}</div>
                          <div className="text-2xl font-bold text-ngodb-red">{summaryStats.currentTotal}</div>
                        </div>
                        <div className="text-center p-3 bg-white rounded-lg border border-ngodb-gray-200">
                          <div className="text-sm text-ngodb-gray-600 mb-1">{t('exploreData.chart.averageAnnualGrowth')}</div>
                          <div className="text-2xl font-bold text-ngodb-navy">{summaryStats.avgAnnualGrowth}%</div>
                        </div>
                      </div>
                    </motion.div>
                  )}
                </motion.div>
              ) : (
                <ChartPlaceholder />
              )}

              {/* Loading State */}
              {isLoading && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="bg-white rounded-xl shadow-lg p-6 text-center"
                >
                  <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-ngodb-red mx-auto mb-4"></div>
                  <p className="text-ngodb-gray-600">{t('exploreData.loading.generating')}</p>
                </motion.div>
              )}

              {/* Initial Data Loading State */}
              {isLoadingData && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="bg-white rounded-xl shadow-lg p-6 text-center"
                >
                  <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-ngodb-red mx-auto mb-4"></div>
                  <p className="text-ngodb-gray-600">{t('exploreData.loading.loadingData')}</p>
                </motion.div>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
