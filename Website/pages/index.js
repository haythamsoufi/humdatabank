// pages/index.js (Global Overview - Animated with Integrated Chat)
import Head from 'next/head';
import Link from 'next/link';
import { useEffect, useMemo, useState, useRef } from 'react';
import { useRouter } from 'next/router';
import { motion, AnimatePresence } from 'framer-motion'; // Import Framer Motion
import { useTranslation } from '../lib/useTranslation';
import { getIndicatorData, getAvailablePeriods, getCountriesList, FDRS_TEMPLATE_ID } from '../lib/apiService';
import { KEY_INDICATOR_BANK_IDS, KEY_INDICATOR_UNITS } from '../lib/constants';
import { downloadCSV, downloadPNG, generateFilename } from '../lib/downloadUtils';
import { fetchAiToken, getCachedAiToken } from '../lib/aiAuth';
import InteractiveWorldMap from '../components/InteractiveWorldMap';
import MultiChart from '../components/MultiChart';
import ClientOnly, { HydrationSafe } from '../components/ClientOnly';
import { useScope } from '../components/scope/ScopeContext';
import { ENABLE_DOMESTIC, ENABLE_INTERNATIONAL, DEFAULT_ACTIVITY_VIEW } from '../lib/scopeConfig';
import { getPublicOrganizationName } from '../lib/publicOrgName';

export default function GlobalOverviewPage() {
  const { t, locale, isLoaded } = useTranslation();
  const router = useRouter();
  const { scope, countryIso2, countryIso3, label, nationalSocietyName, countryName: scopeCountryName, isDemoMode } = useScope();
  const isNationalScope = scope?.type === 'country' && !!countryIso2;

  // Domestic / International activity views (feature-flagged by env)
  const enabledActivityViews = useMemo(() => [
    ...(ENABLE_DOMESTIC ? ['domestic'] : []),
    ...(ENABLE_INTERNATIONAL ? ['international'] : []),
  ], []);
  const hasActivityTabs = enabledActivityViews.length > 1;

  // Get default activity view (without URL consideration)
  const getDefaultActivityView = () => {
    if (hasActivityTabs) {
      if (DEFAULT_ACTIVITY_VIEW === 'international' && ENABLE_INTERNATIONAL) return 'international';
      if (DEFAULT_ACTIVITY_VIEW === 'domestic' && ENABLE_DOMESTIC) return 'domestic';
      return ENABLE_DOMESTIC ? 'domestic' : 'international';
    }
    return enabledActivityViews[0] || 'domestic';
  };

  const defaultActivityView = getDefaultActivityView();
  const [activityView, setActivityView] = useState(defaultActivityView);

  // Sync URL parameter with activity view on mount and when URL changes
  useEffect(() => {
    if (!router.isReady) return;

    const urlView = router.query.view;
    if (urlView === 'domestic' || urlView === 'international') {
      // Check if the view is enabled and different from current
      const isEnabled = (urlView === 'domestic' && ENABLE_DOMESTIC) ||
                        (urlView === 'international' && ENABLE_INTERNATIONAL);
      if (isEnabled && urlView !== activityView) {
        setActivityView(urlView);
      }
    } else if (!urlView && activityView !== defaultActivityView) {
      // If no URL param and current view is not default, reset to default
      // (This handles the case where user navigates away and back)
      setActivityView(defaultActivityView);
    }
  }, [router.isReady, router.query.view, activityView, defaultActivityView]);

  // Update URL when activity view changes
  const handleActivityViewChange = (view) => {
    if (!enabledActivityViews.includes(view)) return;

    setActivityView(view);

    // Update URL without page reload
    const newQuery = { ...router.query };
    if (view === defaultActivityView) {
      // Remove parameter if it's the default view
      delete newQuery.view;
    } else {
      newQuery.view = view;
    }

    router.push(
      {
        pathname: router.pathname,
        query: newQuery,
      },
      undefined,
      { shallow: true }
    );
  };

  const i18nSiteTitle = t('navigation.siteTitle');
  const globalSiteTitle = getPublicOrganizationName(i18nSiteTitle);
  // In Arabic demo NS mode, place "Databank" before NS name
  const siteTitle = (isDemoMode && isNationalScope && nationalSocietyName)
    ? (locale === 'ar'
        ? `${t('navigation.databank')} ${nationalSocietyName}`
        : `${nationalSocietyName} ${t('navigation.databank')}`)
    : globalSiteTitle;

  const organizationName = (isDemoMode && isNationalScope && nationalSocietyName)
    ? nationalSocietyName
    : siteTitle;

  // Chat state
  const [currentResponse, setCurrentResponse] = useState('');
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isInputFocused, setIsInputFocused] = useState(false);
  const [submittedMessage, setSubmittedMessage] = useState('');
  const [chartData, setChartData] = useState(null);
  const chatInputRef = useRef(null);

  // Conversation persistence state
  const [conversationId, setConversationId] = useState(null);
  const [conversationHistory, setConversationHistory] = useState([]);

  // AI auth token state
  const [aiToken, setAiToken] = useState(null);

  // Conversation list state (for logged-in users)
  const [conversations, setConversations] = useState([]);
  const [isLoadingConversations, setIsLoadingConversations] = useState(false);
  const [showConversationList, setShowConversationList] = useState(false);

  // Indicator selection state
  const [selectedIndicator, setSelectedIndicator] = useState('volunteers');

  // Active indicator state (the one that actually filters the map)
  const [activeIndicator, setActiveIndicator] = useState('volunteers');

  // International indicator selection state
  const [selectedInternationalIndicator, setSelectedInternationalIndicator] = useState('total-funding');

  // Region selection state
  const [selectedRegion, setSelectedRegion] = useState('global');

  // Lock region selection for national-scope deployments/demos
  useEffect(() => {
    if (isNationalScope && selectedRegion !== 'global') {
      setSelectedRegion('global');
    }
  }, [isNationalScope, selectedRegion]);

  // API data state
  const [countryData, setCountryData] = useState({});
  const [globalTotal, setGlobalTotal] = useState(0);
  const [isLoadingData, setIsLoadingData] = useState(false);
  const [indicatorMapping, setIndicatorMapping] = useState({});

  // Cache for API responses
  const [apiCache, setApiCache] = useState({});
  const [isUsingCache, setIsUsingCache] = useState(false);
  const CACHE_DURATION = 5 * 60 * 1000; // 5 minutes in milliseconds

  // Hover state for dynamic total display
  const [hoveredCountry, setHoveredCountry] = useState(null);
  const [hoveredValue, setHoveredValue] = useState(0);

  // Visualization type state
  const [visualizationType, setVisualizationType] = useState('choropleth'); // 'choropleth', 'bubble', 'barchart'

  // Selected sub-indicator state for People Reached
  const [selectedSubIndicator, setSelectedSubIndicator] = useState(null);

  // Dropdown state for People Reached sub-categories
  const [openDropdown, setOpenDropdown] = useState(null);

  // State to track if People Reached sub-categories are expanded
  const [isPeopleReachedExpanded, setIsPeopleReachedExpanded] = useState(false);
  const [isMobile, setIsMobile] = useState(false);

  // Year filter state
  const [selectedYear, setSelectedYear] = useState(null);
  const [availableYears, setAvailableYears] = useState([]);
  const [isLoadingYears, setIsLoadingYears] = useState(false);

  // Download state
  const [isDownloadingCSV, setIsDownloadingCSV] = useState(false);
  const [isDownloadingPNG, setIsDownloadingPNG] = useState(false);

  // Country regions mapping from API
  const [countryRegions, setCountryRegions] = useState({});

  // Region definitions
  const regions = {
    'global': {
      name: t('globalOverview.regions.global'),
      description: t('globalOverview.regions.globalDesc'),
      countries: []
    },
    'africa': {
      name: t('globalOverview.regions.africa'),
      description: t('globalOverview.regions.africaDesc'),
      countries: []
    },
    'americas': {
      name: t('globalOverview.regions.americas'),
      description: t('globalOverview.regions.americasDesc'),
      countries: []
    },
    'asia-pacific': {
      name: t('globalOverview.regions.asiaPacific'),
      description: t('globalOverview.regions.asiaPacificDesc'),
      countries: []
    },
    'europe-and-central-asia': {
      name: t('globalOverview.regions.europeCentralAsia'),
      description: t('globalOverview.regions.europeCentralAsiaDesc'),
      countries: []
    },
    'mena': {
      name: t('globalOverview.regions.mena'),
      description: t('globalOverview.regions.menaDesc'),
      countries: []
    }
  };

  // Secondary indicators for "People Reached"
  const peopleReachedSubIndicators = {
    'cross-cutting': {
      id: 735,
      name: t('globalOverview.peopleReached.crossCutting'),
      description: t('globalOverview.peopleReached.crossCuttingDesc'),
      unit: 'People',
      indicators: [
        { id: 754, name: t('globalOverview.peopleReached.subIndicators.longTermServices'), unit: 'People' },
        { id: 619, name: t('globalOverview.peopleReached.subIndicators.emergencyResponse'), unit: 'People' }
      ]
    },
    'climate-environmental': {
      id: 736,
      name: t('globalOverview.peopleReached.climateEnvironmental'),
      description: t('globalOverview.peopleReached.climateEnvironmentalDesc'),
      unit: 'People',
      indicators: [
        { id: 744, name: t('globalOverview.peopleReached.subIndicators.climateAdaptation'), unit: 'People' },
        { id: 745, name: t('globalOverview.peopleReached.subIndicators.environmentalProtection'), unit: 'People' },
        { id: 746, name: t('globalOverview.peopleReached.subIndicators.disasterRiskReduction'), unit: 'People' },
        { id: 747, name: t('globalOverview.peopleReached.subIndicators.sustainableDevelopment'), unit: 'People' }
      ]
    },
    'evolving-crises': {
      id: 737,
      name: t('globalOverview.peopleReached.evolvingCrises'),
      description: t('globalOverview.peopleReached.evolvingCrisesDesc'),
      unit: 'People',
      indicators: [
        { id: 748, name: t('globalOverview.peopleReached.subIndicators.emergencyResponseRecovery'), unit: 'People' },
        { id: 749, name: t('globalOverview.peopleReached.subIndicators.recoveryRehabilitation'), unit: 'People' },
        { id: 750, name: t('globalOverview.peopleReached.subIndicators.earlyWarningSystems'), unit: 'People' },
        { id: 751, name: t('globalOverview.peopleReached.subIndicators.crisisPreparedness'), unit: 'People' }
      ]
    },
    'health-wellbeing': {
      id: 738,
      name: t('globalOverview.peopleReached.healthWellbeing'),
      description: t('globalOverview.peopleReached.healthWellbeingDesc'),
      unit: 'People',
      indicators: [
        { id: 752, name: t('globalOverview.peopleReached.subIndicators.primaryHealthcare'), unit: 'People' },
        { id: 753, name: t('globalOverview.peopleReached.subIndicators.mentalHealthSupport'), unit: 'People' },
        { id: 754, name: t('globalOverview.peopleReached.subIndicators.nutritionPrograms'), unit: 'People' },
        { id: 755, name: t('globalOverview.peopleReached.subIndicators.healthEducation'), unit: 'People' }
      ]
    },
    'migration-identity': {
      id: 739,
      name: t('globalOverview.peopleReached.migrationIdentity'),
      description: t('globalOverview.peopleReached.migrationIdentityDesc'),
      unit: 'People',
      indicators: [
        { id: 756, name: t('globalOverview.peopleReached.subIndicators.migrantAssistance'), unit: 'People' },
        { id: 757, name: t('globalOverview.peopleReached.subIndicators.refugeeSupport'), unit: 'People' },
        { id: 758, name: t('globalOverview.peopleReached.subIndicators.communityIntegration'), unit: 'People' },
        { id: 759, name: t('globalOverview.peopleReached.subIndicators.identityProtection'), unit: 'People' }
      ]
    },
    'values-power-inclusion': {
      id: 740,
      name: t('globalOverview.peopleReached.valuesPowerInclusion'),
      description: t('globalOverview.peopleReached.valuesPowerInclusionDesc'),
      unit: 'People',
      indicators: [
        { id: 760, name: t('globalOverview.peopleReached.subIndicators.genderEquality'), unit: 'People' },
        { id: 761, name: t('globalOverview.peopleReached.subIndicators.youthEmpowerment'), unit: 'People' },
        { id: 762, name: t('globalOverview.peopleReached.subIndicators.socialInclusion'), unit: 'People' },
        { id: 763, name: t('globalOverview.peopleReached.subIndicators.humanitarianValues'), unit: 'People' }
      ]
    }
  };

  // Key indicators: IDs and units from constants; names from translations.
  const keyIndicatorsMapping = {
    'volunteers': { id: KEY_INDICATOR_BANK_IDS.volunteers, name: t('globalOverview.indicators.volunteers'), unit: KEY_INDICATOR_UNITS.volunteers },
    'staff': { id: KEY_INDICATOR_BANK_IDS.staff, name: t('globalOverview.indicators.staff'), unit: KEY_INDICATOR_UNITS.staff },
    'branches': { id: KEY_INDICATOR_BANK_IDS.branches, name: t('globalOverview.indicators.branches'), unit: KEY_INDICATOR_UNITS.branches },
    'local-units': { id: KEY_INDICATOR_BANK_IDS['local-units'], name: t('globalOverview.indicators.localUnits'), unit: KEY_INDICATOR_UNITS['local-units'] },
    'blood-donors': { id: KEY_INDICATOR_BANK_IDS['blood-donors'], name: t('globalOverview.indicators.bloodDonors'), unit: KEY_INDICATOR_UNITS['blood-donors'] },
    'first-aid': { id: KEY_INDICATOR_BANK_IDS['first-aid'], name: t('globalOverview.indicators.firstAid'), unit: KEY_INDICATOR_UNITS['first-aid'] },
    'people-reached': { id: KEY_INDICATOR_BANK_IDS['people-reached'], name: t('globalOverview.indicators.peopleReached'), unit: KEY_INDICATOR_UNITS['people-reached'] },
    'income': { id: KEY_INDICATOR_BANK_IDS.income, name: t('globalOverview.indicators.income'), unit: KEY_INDICATOR_UNITS.income },
    'expenditure': { id: KEY_INDICATOR_BANK_IDS.expenditure, name: t('globalOverview.indicators.expenditure'), unit: KEY_INDICATOR_UNITS.expenditure }
  };

  // Cache utility functions
  const getCacheKey = (indicatorId) => `indicator_${indicatorId}`;

  const isCacheValid = (cacheEntry) => {
    if (!cacheEntry || !cacheEntry.timestamp) return false;
    return Date.now() - cacheEntry.timestamp < CACHE_DURATION;
  };

  const getCachedData = (cacheKey) => {
    const cacheEntry = apiCache[cacheKey];
    if (isCacheValid(cacheEntry)) {
      setIsUsingCache(true);
      return cacheEntry.data;
    }
    setIsUsingCache(false);
    return null;
  };

  const setCachedData = (cacheKey, data) => {
    setApiCache(prev => ({
      ...prev,
      [cacheKey]: {
        data,
        timestamp: Date.now()
      }
    }));
  };

  const clearCache = () => {
    setApiCache({});
    setIsUsingCache(false);
  };

  const getCacheInfo = () => {
    const cacheEntries = Object.keys(apiCache).length;
    const cacheSize = Object.values(apiCache).reduce((total, entry) => {
      return total + JSON.stringify(entry.data).length;
    }, 0);
    return { entries: cacheEntries, size: cacheSize };
  };

  const getCacheTimeRemaining = (cacheKey) => {
    const cacheEntry = apiCache[cacheKey];
    if (!cacheEntry || !cacheEntry.timestamp) return 0;

    const timeElapsed = Date.now() - cacheEntry.timestamp;
    const timeRemaining = CACHE_DURATION - timeElapsed;
    return Math.max(0, timeRemaining);
  };

  // Hover callback functions
  const handleCountryHover = (countryName, value, countryCode) => {
    setHoveredCountry(countryName);
    setHoveredValue(value);
  };

  const handleCountryLeave = () => {
    setHoveredCountry(null);
    setHoveredValue(0);
  };

  // Load country regions from API
  const loadCountryRegions = async () => {
    try {
      const countries = await getCountriesList();
      const regionMap = {};
      countries.forEach(country => {
        // Map API region names to our region keys
        let normalizedRegion;
        switch (country.region) {
          case 'Europe & CA':
          case 'Europe':
            normalizedRegion = 'europe-and-central-asia';
            break;
          case 'Asia Pacific':
          case 'Asia':
            normalizedRegion = 'asia-pacific';
            break;
          case 'MENA':
          case 'Middle East':
            normalizedRegion = 'mena';
            break;
          case 'Africa':
            normalizedRegion = 'africa';
            break;
          case 'Americas':
            normalizedRegion = 'americas';
            break;
          default:
            normalizedRegion = 'other';
        }
        regionMap[country.code] = normalizedRegion;
      });
      setCountryRegions(regionMap);
    } catch (error) {
      console.error('Error loading country regions:', error);
    }
  };

  // Fetch available years/periods
  const fetchAvailableYears = async () => {
    setIsLoadingYears(true);
    try {
      const periods = await getAvailablePeriods(FDRS_TEMPLATE_ID);
      setAvailableYears(periods);
      // Set the most recent year as default if none selected
      if (!selectedYear && periods.length > 0) {
        setSelectedYear(periods[0]);
      }
    } catch (error) {
      console.error('Error fetching available years:', error);
      setAvailableYears(['2023', '2022', '2021', '2020', '2019']);
      if (!selectedYear) {
        setSelectedYear('2023');
      }
    } finally {
      setIsLoadingYears(false);
    }
  };

  // Fetch data from API using centralized service
  const fetchIndicatorData = async (indicatorKey) => {
    setIsLoadingData(true);

    try {
      let indicator;

      // Handle people-reached sub-indicators
      if (indicatorKey.startsWith('people-reached-')) {
        const subIndicatorId = indicatorKey.replace('people-reached-', '');
        // Find the sub-indicator in the peopleReachedSubIndicators
        for (const category of Object.values(peopleReachedSubIndicators)) {
          const subIndicator = category.indicators.find(sub => sub.id.toString() === subIndicatorId);
          if (subIndicator) {
            indicator = subIndicator;
            break;
          }
        }
      } else {
        indicator = keyIndicatorsMapping[indicatorKey];
      }

      if (!indicator) {
        console.warn(`No indicator mapping found for: ${indicatorKey}`);
        setCountryData({});
        setGlobalTotal(0);
        setIndicatorMapping({});
        return;
      }

      // Check if we have a known indicator ID
      if (!indicator.id) {
        console.warn(`No indicator ID configured for: ${indicator.name}`);
        setCountryData({});
        setGlobalTotal(0);
        setIndicatorMapping(indicator);
        return;
      }

      // Create cache key that includes the year filter
      const cacheKey = selectedYear ? `${indicator.id}_${selectedYear}` : indicator.id;
      const cachedData = getCachedData(cacheKey);
      if (cachedData) {
        setCountryData(cachedData.processedData);
        setGlobalTotal(cachedData.globalTotal);
        setIndicatorMapping(indicator);
        setIsLoadingData(false);
        return;
      }

      // Use centralized API service
      const { processedData, globalTotal } = await getIndicatorData(indicator.id, selectedYear);

      // Map the raw values to the correct indicator fields
      const mappedData = {};

      // Create a mapping from indicator keys to field names
      const fieldMapping = {
        'volunteers': 'volunteers',
        'staff': 'staff',
        'branches': 'branches',
        'local-units': 'localUnits',
        'blood-donors': 'bloodDonors',
        'first-aid': 'firstAid',
        'people-reached': 'peopleReached',
        'income': 'income',
        'expenditure': 'expenditure'
      };

      Object.keys(processedData).forEach(countryCode => {
        const country = processedData[countryCode];

        // Handle people-reached sub-indicators differently
        if (indicatorKey.startsWith('people-reached-')) {
          // For sub-indicators, keep the rawValue as is
          mappedData[countryCode] = {
            ...country,
            rawValue: country.rawValue || 0
          };
        } else {
          // For regular indicators, map to specific fields
          const fieldName = fieldMapping[indicatorKey];

          mappedData[countryCode] = {
            ...country,
            [fieldName]: country.rawValue || 0
          };
          // Remove the rawValue field as it's no longer needed
          delete mappedData[countryCode].rawValue;
        }
      });

      // Cache the processed data with year-specific key
      setCachedData(cacheKey, {
        processedData: mappedData,
        globalTotal,
        indicator: {
          ...indicator,
          unit: indicator.unit
        }
      });

      setCountryData(mappedData);
      setGlobalTotal(globalTotal);

      setIndicatorMapping({
        ...indicator,
        unit: indicator.unit
      });

    } catch (error) {
      console.error('Error fetching indicator data:', error);
      // No fallback to sample data - just set empty data
      setCountryData({});
      setGlobalTotal(0);
      setIndicatorMapping({});
    } finally {
      setIsLoadingData(false);
    }
  };

  // Fetch available years and country regions on component mount
  useEffect(() => {
    const initializeData = async () => {
      await fetchAvailableYears();
      await loadCountryRegions();

      // If we have a selected year after fetching years, immediately fetch indicator data
      if (selectedYear && activeIndicator !== 'people-reached') {
        fetchIndicatorData(activeIndicator);
      }
    };

    initializeData();
  }, []);

  // Fetch data when indicator or year changes
  useEffect(() => {
    const controller = new AbortController();

    if (!isLoadingData && selectedYear && activeIndicator !== 'people-reached') {
      fetchIndicatorData(activeIndicator);
    }

    return () => {
      controller.abort();
    };
  }, [activeIndicator, selectedYear]);


  // Reset sub-indicator when region or year changes
  useEffect(() => {
    if (selectedSubIndicator) {
      setSelectedSubIndicator(null);
    }
    // Reset active indicator to a valid indicator if it's currently set to a people-reached sub-indicator
    if (activeIndicator.startsWith('people-reached-')) {
      setActiveIndicator('volunteers');
      setSelectedIndicator('volunteers');
    }
    // Close any open dropdowns
    setOpenDropdown(null);
    // Collapse People Reached section
    setIsPeopleReachedExpanded(false);
  }, [selectedRegion, selectedYear]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (openDropdown && !event.target.closest('.dropdown-container')) {
        setOpenDropdown(null);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [openDropdown]);

  // Detect mobile viewport to adjust dropdown rendering
  useEffect(() => {
    const checkIsMobile = () => setIsMobile(typeof window !== 'undefined' && window.innerWidth < 768);
    checkIsMobile();
    window.addEventListener('resize', checkIsMobile);
    return () => window.removeEventListener('resize', checkIsMobile);
  }, []);

  // --- REPLACE THESE WITH YOUR ACTUAL IMAGE URLS ---
  // For local images: Place them in the 'public' folder (e.g., public/images/operation1.jpg)
  // and use the path starting with '/' (e.g., "/images/1.jpg").
  // For external images: Use the full URL (e.g., "https://cdn.example.org/your-image.jpg").
  const slideshowImages = [
    "/images/1.jpg", // Example: Türkiye Earthquake Response
    "/images/2.jpg", // Example: Volunteer Activities
    "/images/3.jpg", // Example: Health Worker in Action
    // Add more image URLs here if needed
  ];
  // --- END OF IMAGE REPLACEMENT SECTION ---

  const [currentImageIndex, setCurrentImageIndex] = useState(0);

  useEffect(() => {
    if (slideshowImages.length <= 1) return; // Don't start timer if only one or no images

    const timer = setInterval(() => {
      setCurrentImageIndex((prevIndex) => (prevIndex + 1) % slideshowImages.length);
    }, 5000); // Change image every 5 seconds
    return () => clearInterval(timer); // Cleanup timer on component unmount
  }, [slideshowImages.length]);





  // Fetch AI token on mount (if user is logged in)
  useEffect(() => {
    if (typeof window !== 'undefined') {
      // Try to get cached token first
      const cached = getCachedAiToken();
      if (cached) {
        setAiToken(cached);
        loadConversations(cached);
      } else {
        // Try to fetch token (will return null if not authenticated)
        fetchAiToken().then(token => {
          if (token) {
            setAiToken(token);
            loadConversations(token);
          }
        }).catch(() => {
          // Silent fail - user is likely anonymous
        });
      }
    }
  }, []);

  // Load conversations list (for logged-in users)
  const loadConversations = async (token) => {
    if (!token) return;

    setIsLoadingConversations(true);
    try {
      const resp = await fetch('/api/ai-conversations?limit=20', {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });
      const data = await resp.json();
      if (data.conversations) {
        setConversations(data.conversations);
      }
    } catch (err) {
      console.warn('Failed to load conversations:', err);
    } finally {
      setIsLoadingConversations(false);
    }
  };

  // Load a specific conversation
  const loadConversation = async (conversationId) => {
    if (!aiToken || !conversationId) return;

    setIsLoading(true);
    try {
      const resp = await fetch(`/api/ai-conversations?conversation_id=${conversationId}`, {
        headers: {
          'Authorization': `Bearer ${aiToken}`,
        },
      });
      const data = await resp.json();
      if (data.conversation && data.messages) {
        setConversationId(conversationId);
        setConversationHistory(data.messages.map(msg => ({
          role: msg.role,
          content: msg.content,
        })));
        // Show the last message as current response
        const lastMsg = data.messages[data.messages.length - 1];
        if (lastMsg && lastMsg.role === 'assistant') {
          setCurrentResponse(lastMsg.content);
        }
        setShowConversationList(false);
      }
    } catch (err) {
      console.error('Failed to load conversation:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    const userMessage = inputValue.trim();
    if (!userMessage) return;

    setSubmittedMessage(userMessage);
    // Keep the text in the input field instead of clearing it
    // setInputValue('');
    setIsLoading(true);

    try {
      const pageContext = {
        currentPage: typeof window !== 'undefined' ? window.location.pathname : '/',
        currentUrl: typeof window !== 'undefined' ? window.location.href : '',
        pageTitle: typeof document !== 'undefined' ? document.title : siteTitle,
        pageData: {
          pageType: 'public_global_overview',
          selectedIndicator: activeIndicator,
          selectedRegion,
          selectedYear,
        },
      };

      // Build conversation history array from previous messages
      const historyArray = conversationHistory.map(msg => ({
        role: msg.role,
        content: msg.content,
      }));

      // Prepare headers with Authorization if we have a token
      const headers = { 'Content-Type': 'application/json' };
      const currentToken = aiToken || getCachedAiToken();
      if (currentToken) {
        headers['Authorization'] = `Bearer ${currentToken}`;
      }

      // Retry logic for network failures
      let resp = null;
      let data = null;
      let lastError = null;
      const maxRetries = 2;

      for (let attempt = 0; attempt <= maxRetries; attempt++) {
        try {
          resp = await fetch('/api/chatbot', {
            method: 'POST',
            headers,
            body: JSON.stringify({
              message: userMessage,
              conversation_id: conversationId,
              page_context: pageContext,
              preferred_language: 'english',
              conversationHistory: historyArray,
            }),
            signal: AbortSignal.timeout(65000), // Slightly above proxy timeout (60s)
          });

          data = await resp.json().catch(() => ({}));
          if (!resp.ok) {
            const errMsg = data?.error || `Chat request failed: ${resp.status}`;
            // Don't retry on 4xx errors (client errors)
            if (resp.status >= 400 && resp.status < 500) {
              throw new Error(errMsg);
            }
            // Retry on 5xx/502 (Backoffice unreachable or server error)
            if ((resp.status >= 500 || resp.status === 502) && attempt < maxRetries) {
              await new Promise(resolve => setTimeout(resolve, 1000 * (attempt + 1))); // Exponential backoff
              continue;
            }
            throw new Error(errMsg);
          }
          // Success - break retry loop
          break;
        } catch (error) {
          lastError = error;
          // Retry on network errors (but not on timeout/abort)
          if (attempt < maxRetries && (error.name === 'TypeError' || error.name === 'NetworkError')) {
            await new Promise(resolve => setTimeout(resolve, 1000 * (attempt + 1))); // Exponential backoff
            continue;
          }
          // Don't retry on timeout/abort
          throw error;
        }
      }

      if (!resp || !resp.ok) {
        throw lastError || new Error(data?.error || 'Chat request failed');
      }

      const reply = data.reply || '';
      const newConversationId = data.conversation_id || null;

      // Update conversation state
      if (newConversationId && newConversationId !== conversationId) {
        setConversationId(newConversationId);
      }

      // Add user message and assistant reply to history
      const updatedHistory = [
        ...conversationHistory,
        { role: 'user', content: userMessage },
        { role: 'assistant', content: reply },
      ];
      setConversationHistory(updatedHistory);

      setCurrentResponse(reply);
      setChartData(null); // Phase 1: backend returns text only
    } catch (err) {
      console.error('Chatbot error:', err);
      let friendlyMessage = err?.message || t('chat.placeholder.response', { message: userMessage });
      if (friendlyMessage.includes('aborted') || friendlyMessage.includes('timeout')) {
        friendlyMessage = 'Request timed out. The AI service may be slow or unreachable. Ensure Backoffice is running (e.g. `cd Backoffice && python run.py`) and try again.';
      }
      setCurrentResponse(friendlyMessage);
      setChartData(null);
    } finally {
      setIsLoading(false);
    }
  };

  const generateChartData = (message) => {
    // Placeholder fake chart data for Afghanistan volunteers across years
    const currentYear = selectedYear || '2023';
    return {
      type: 'line',
      title: t('globalOverview.chartTitles.afghanistanVolunteers', { year: currentYear }),
      data: [
        { label: '2019', value: 12500 },
        { label: '2020', value: 14200 },
        { label: '2021', value: 16800 },
        { label: '2022', value: 18900 },
        { label: '2023', value: 21500 },
        { label: currentYear, value: 23000 }
      ]
    };
  };

  const generateVolunteersChartData = () => {
    // Chart data showing Afghan Red Crescent Society volunteers over the past 5 years
    return {
      type: 'line',
      title: t('globalOverview.chartTitles.arcsVolunteers'),
      data: [
        { label: '2019', value: 23440 },
        { label: '2020', value: 28500 },
        { label: '2021', value: 32000 },
        { label: '2022', value: 393077 },
        { label: '2023', value: 425000 }
      ]
    };
  };

  const generateDisasterResponseChartData = () => {
    // Chart data showing disaster response operations over the past 5 years
    return {
      type: 'bar',
      title: t('globalOverview.chartTitles.disasterResponse'),
      data: [
        { label: '2019', value: 850 },
        { label: '2020', value: 920 },
        { label: '2021', value: 980 },
        { label: '2022', value: 1050 },
        { label: '2023', value: 1100 }
      ]
    };
  };

  const generateIndicatorsChartData = () => {
    // Chart data showing key humanitarian indicators
    return {
      type: 'bar',
      title: t('globalOverview.chartTitles.humanitarianIndicators'),
      data: [
        { label: t('globalOverview.indicators.volunteers'), value: 15000000 },
        { label: t('globalOverview.indicators.staff'), value: 450000 },
        { label: t('globalOverview.indicators.localUnits'), value: 125000 },
        { label: t('globalOverview.indicators.bloodDonors'), value: 8500000 },
        { label: t('globalOverview.indicators.firstAid'), value: 3200000 },
        { label: t('globalOverview.indicators.peopleReached'), value: 160000000 }
      ]
    };
  };

  const generateRegionalComparisonChartData = () => {
    // Chart data showing volunteer numbers by region
    return {
      type: 'bar',
      title: t('globalOverview.chartTitles.regionalComparison'),
      data: [
        { label: t('globalOverview.regions.africa'), value: 5200000 },
        { label: t('globalOverview.regions.asia'), value: 4800000 },
        { label: t('globalOverview.regions.americas'), value: 2800000 },
        { label: t('globalOverview.regions.europe'), value: 1800000 },
        { label: t('globalOverview.regions.middleEast'), value: 400000 }
      ]
    };
  };





  // Helper function to format numbers
  const formatNumber = (num) => {
    if (num >= 1000000000) {
      return (num / 1000000000).toFixed(1) + 'B';
    } else if (num >= 1000000) {
      return (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
      return (num / 1000).toFixed(1) + 'K';
    }
    return num.toString();
  };

  // Helper function to get indicator value
  const getIndicatorValue = (countryCode, indicator) => {
    const country = countryData[countryCode];
    if (!country) return 0;

    // Handle people-reached sub-indicators
    if (indicator.startsWith('people-reached-')) {
      // For sub-indicators, we use the rawValue that comes from the API
      return country.rawValue || 0;
    }

    const indicatorMap = {
      'volunteers': country.volunteers,
      'staff': country.staff,
      'branches': country.branches,
      'local-units': country.localUnits,
      'blood-donors': country.bloodDonors,
      'first-aid': country.firstAid,
      'people-reached': country.peopleReached,
      'income': country.income,
      'expenditure': country.expenditure
    };

    const value = indicatorMap[indicator] || 0;

    return value;
  };

  // Helper function to filter data by region
  const getFilteredCountryData = () => {
    if (selectedRegion === 'global') {
      return countryData;
    }

    const filteredData = {};

    Object.keys(countryData).forEach(countryCode => {
      const countryRegion = countryRegions[countryCode];
      if (countryRegion === selectedRegion) {
        filteredData[countryCode] = countryData[countryCode];
      }
    });

    return filteredData;
  };

  // Helper function to calculate regional total
  const getRegionalTotal = () => {
    const filteredData = getFilteredCountryData();
    return Object.entries(filteredData).reduce((total, [countryCode, country]) => {
      const value = getIndicatorValue(countryCode, activeIndicator);
      return total + value;
    }, 0);
  };

  // Helper function to get country name
  const getCountryName = (countryCode) => {
    const country = countryData[countryCode];
    return country ? country.name : t('fallbacks.unknownCountry');
  };

  // --- International view helpers (support flows, support relationships) ---
  // NOTE: These should eventually be fetched from Backoffice.
  // For now we fetch from a Website API route which serves demo dummy data.
  // The API endpoint serves data from Website/data/international_dummy.json
  const [internationalData, setInternationalData] = useState(() => {
    // Keep a stable initial shape for SSR/hydration.
    // Start with empty data, will be populated by API fetch
    return { supportMap: {}, flows: {}, indicators: {} };
  });

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      try {
        const resp = await fetch('/api/international-support');
        // 204 means "no demo data in this environment"
        if (!resp.ok) return;
        const data = await resp.json();
        if (!mounted) return;
        if (data && typeof data === 'object') {
          setInternationalData(data);
        }
      } catch (_e) {
        // Keep current (dummy/empty) data
      }
    };
    load();
    return () => {
      mounted = false;
    };
  }, []);

  const internationalSupportMap = useMemo(() => {
    const parsed = internationalData?.supportMap;
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};

    const normalized = {};
    for (const [k, v] of Object.entries(parsed)) {
      const from = String(k || '').toUpperCase();
      if (!from || from.length !== 2) continue;
      const arr = Array.isArray(v) ? v : [];
      normalized[from] = arr
        .map((c) => String(c || '').toUpperCase())
        .filter((c) => c && c.length === 2 && c !== from);
    }
    return normalized;
  }, [internationalData]);

  const internationalFlows = useMemo(() => {
    // Support both old format (array) and new format (object with years)
    let flowsArray = [];
    if (Array.isArray(internationalData?.flows)) {
      // Old format: direct array
      flowsArray = internationalData.flows;
    } else if (internationalData?.flows && typeof internationalData.flows === 'object' && !Array.isArray(internationalData.flows)) {
      // New format: object with years
      // Get available years (filter out non-year keys like supportMap if it exists)
      const availableYears = Object.keys(internationalData.flows)
        .filter(k => /^\d{4}$/.test(String(k)))
        .sort()
        .reverse();

      // Use selectedYear if it exists in the data, otherwise use most recent year
      let year = null;
      if (selectedYear && availableYears.includes(String(selectedYear))) {
        year = String(selectedYear);
      } else if (availableYears.length > 0) {
        year = availableYears[0];
      }

      flowsArray = year ? (internationalData.flows[year] || []) : [];
    }

    const baseFlows = flowsArray
      .map((f) => {
        const rawValue = Number(f?.value ?? 1);
        return {
          from: f?.from ? String(f.from).toUpperCase() : null,
          to: f?.to ? String(f.to).toUpperCase() : null,
          rawValue: Number.isFinite(rawValue) && rawValue > 0 ? rawValue : 1,
        };
      })
      .filter((f) => f.from && f.to && f.from.length === 2 && f.to.length === 2);

    if (!baseFlows.length) {
      return [];
    }

    const sortedValues = baseFlows
      .map((f) => f.rawValue)
      .filter((v) => Number.isFinite(v) && v > 0)
      .sort((a, b) => a - b);

    const getPercentile = (arr, percentile) => {
      if (!arr.length) return 1;
      if (arr.length === 1) return arr[0];
      const clampedPercentile = Math.max(0, Math.min(1, Number(percentile) || 0));
      const position = clampedPercentile * (arr.length - 1);
      const lowerIndex = Math.floor(position);
      const upperIndex = Math.ceil(position);
      if (lowerIndex === upperIndex) return arr[lowerIndex];
      const weight = position - lowerIndex;
      return arr[lowerIndex] + (arr[upperIndex] - arr[lowerIndex]) * weight;
    };

    // Robust range avoids one extreme flow making every other line look identical.
    const p10 = getPercentile(sortedValues, 0.1);
    const p90 = getPercentile(sortedValues, 0.9);
    const hasSpread = Number.isFinite(p10) && Number.isFinite(p90) && p90 > p10;

    return baseFlows.map((flow) => {
      const clampedValue = hasSpread
        ? Math.max(p10, Math.min(p90, flow.rawValue))
        : flow.rawValue;
      const normalized = hasSpread ? (clampedValue - p10) / (p90 - p10) : 0.5;
      const visualWeight = 8 + (normalized * 92); // 8..100, tuned for map line/arrow scaling

      let styleTier = 'medium';
      if (normalized >= 0.8) styleTier = 'strong';
      else if (normalized <= 0.2) styleTier = 'subtle';

      return {
        from: flow.from,
        to: flow.to,
        value: flow.rawValue,
        visualWeight,
        styleTier,
      };
    });
  }, [internationalData, selectedYear]);

  // International indicator definitions
  const internationalIndicators = {
    'total-funding': {
      name: 'Total Funding',
      unit: 'USD',
    },
    'people-reached': {
      name: 'People Reached',
      unit: 'People',
    },
    'services': {
      name: 'Services',
      unit: 'Services',
    },
  };

  const internationalMapModel = useMemo(() => {
    const activeIso2 = countryIso2 ? String(countryIso2).toUpperCase() : null;
    const indicatorKey = selectedInternationalIndicator || 'total-funding';
    // Get indicator definition from data first, fallback to hardcoded
    const dataIndicator = internationalData?.indicators?.[indicatorKey];
    const indicatorDef = {
      name: dataIndicator?.name || internationalIndicators[indicatorKey]?.name || internationalIndicators['total-funding'].name,
      unit: dataIndicator?.unit || internationalIndicators[indicatorKey]?.unit || internationalIndicators['total-funding'].unit,
    };

    // Support both old format (direct data) and new format (data with years)
    let indicatorDataRaw = {};
    const indicatorDataStructure = internationalData?.indicators?.[indicatorKey]?.data;
    if (indicatorDataStructure) {
      if (indicatorDataStructure[selectedYear]) {
        // New format: data organized by year
        indicatorDataRaw = indicatorDataStructure[selectedYear] || {};
      } else if (!Object.keys(indicatorDataStructure).some(k => /^\d{4}$/.test(k))) {
        // Old format: direct country data (no year keys)
        indicatorDataRaw = indicatorDataStructure;
      } else {
        // New format but selectedYear not found, use most recent year
        const availableYears = Object.keys(indicatorDataStructure).filter(k => /^\d{4}$/.test(k)).sort().reverse();
        indicatorDataRaw = indicatorDataStructure[availableYears[0]] || {};
      }
    }

    // Country scope: highlight active country + supported countries
    if (isNationalScope && activeIso2) {
      const supported = internationalSupportMap[activeIso2] || [];
      const activeSet = Array.from(new Set([activeIso2, ...supported]));
      const flowsForCountry = internationalFlows.filter(
        (f) => f.from === activeIso2 && activeSet.includes(f.to)
      );
      const derivedFlows =
        flowsForCountry.length > 0
          ? flowsForCountry
          : supported.map((to) => ({
              from: activeIso2,
              to,
              value: 1,
              visualWeight: 25,
              styleTier: 'subtle',
            }));

      // Build indicator data from dummy data, fallback to 1 if not found
      const indicatorData = Object.fromEntries(
        activeSet.map((iso2) => {
          const data = indicatorDataRaw[iso2];
          return [
            iso2,
            {
              value: data?.value ?? 1,
              name: data?.name || getCountryName(iso2),
            },
          ];
        })
      );

      const total = Object.values(indicatorData).reduce((sum, d) => sum + (Number(d.value) || 0), 0);

      return {
        title: 'International',
        description:
          supported.length > 0
            ? `Showing ${activeIso2} and the countries it supports internationally (with flow lines).`
            : `Showing ${activeIso2}. (No supported-countries list configured.)`,
        indicatorName: indicatorDef.name,
        indicatorData,
        flows: derivedFlows,
        globalTotal: total,
      };
    }

    // Global scope: use indicator data from dummy data, fallback to flow involvement
    if (Object.keys(indicatorDataRaw).length > 0) {
      const indicatorData = Object.fromEntries(
        Object.entries(indicatorDataRaw).map(([iso2, data]) => [
          iso2,
          {
            value: Number(data?.value ?? 0),
            name: data?.name || getCountryName(iso2),
          },
        ])
      );
      const total = Object.values(indicatorData).reduce((sum, d) => sum + (Number(d.value) || 0), 0);

      return {
        title: 'International',
        description: `Showing ${indicatorDef.name.toLowerCase()} across countries involved in international support flows.`,
        indicatorName: indicatorDef.name,
        indicatorUnit: indicatorDef.unit,
        indicatorData,
        flows: internationalFlows,
        globalTotal: total,
      };
    }

    // Fallback: use flow involvement if no indicator data
    if (internationalFlows.length > 0) {
      const totals = {};
      for (const f of internationalFlows) {
        const w = Number.isFinite(f.rawValue) ? f.rawValue : (Number.isFinite(f.value) ? f.value : 1);
        totals[f.from] = (totals[f.from] || 0) + w;
        totals[f.to] = (totals[f.to] || 0) + w;
      }
      const indicatorData = Object.fromEntries(
        Object.entries(totals).map(([iso2, v]) => [
          iso2,
          { value: v, name: getCountryName(iso2) },
        ])
      );
      return {
        title: 'International',
        description: 'Showing international support flows between countries.',
        indicatorName: 'Flow involvement',
        indicatorUnit: indicatorDef.unit,
        indicatorData,
        flows: internationalFlows,
        globalTotal: Object.values(totals).reduce((a, b) => a + (Number(b) || 0), 0),
      };
    }

    return {
      title: 'International',
      description: 'International support flows are not configured yet.',
      indicatorName: indicatorDef.name,
      indicatorUnit: indicatorDef.unit,
      indicatorData: {},
      flows: [],
      globalTotal: 0,
    };
  }, [countryIso2, getCountryName, internationalFlows, internationalSupportMap, isNationalScope, selectedInternationalIndicator, internationalData, selectedYear]);

  // Helper function to get current indicator name for display
  const getCurrentIndicatorName = () => {
    if (activeIndicator.startsWith('people-reached-')) {
      const subIndicatorId = activeIndicator.replace('people-reached-', '');
      // Find the sub-indicator name
      for (const category of Object.values(peopleReachedSubIndicators)) {
        const subIndicator = category.indicators.find(sub => sub.id.toString() === subIndicatorId);
        if (subIndicator) {
          return subIndicator.name;
        }
      }
      return 'People Reached';
    }
    return keyIndicatorsMapping[activeIndicator]?.name || t('fallbacks.unknownIndicator');
  };

  // Handle country click
  const handleCountryClick = (countryCode, countryName) => {
    const country = countryData[countryCode];
    if (!country) return;

    // You could open a modal, navigate to a country page, etc.
    // For example: router.push(`/countries/${countryCode}`);
  };

  // Download handlers
  const handleDownloadCSV = async () => {
    setIsDownloadingCSV(true);
    try {
      const filteredData = getFilteredCountryData();
      const mapData = Object.fromEntries(
        Object.entries(filteredData).map(([code, country]) => [
          code,
          {
            value: getIndicatorValue(code, activeIndicator),
            name: getCountryName(code)
          }
        ])
      );

      const filename = generateFilename(
        getCurrentIndicatorName(),
        selectedYear,
        selectedRegion === 'global' ? null : regions[selectedRegion]?.name,
        'csv'
      );

      downloadCSV(
        mapData,
        filename,
        getCurrentIndicatorName(),
        selectedYear,
        selectedRegion === 'global' ? 'Global' : regions[selectedRegion]?.name
      );
    } catch (error) {
      console.error('Error downloading CSV:', error);
    } finally {
      setIsDownloadingCSV(false);
    }
  };

  const handleDownloadPNG = async () => {
    setIsDownloadingPNG(true);
    try {
      const filename = generateFilename(
        getCurrentIndicatorName(),
        selectedYear,
        selectedRegion === 'global' ? null : regions[selectedRegion]?.name,
        'png'
      );

      await downloadPNG(filename, 'map-container');
    } catch (error) {
      console.error('Error downloading PNG:', error);
    } finally {
      setIsDownloadingPNG(false);
    }
  };



  // Animation Variants
  const fadeIn = {
    hidden: { opacity: 0 },
    visible: { opacity: 1, transition: { duration: 0.8 } },
  };

  const fadeInUp = {
    hidden: { opacity: 0, y: 20 },
    visible: { opacity: 1, y: 0, transition: { duration: 0.6, ease: "easeOut" } },
  };

  const staggerContainer = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.15, // Stagger animation of children
        delayChildren: 0.2,
      },
    },
  };

  const cardHover = {
    scale: 1.03,
    boxShadow: "0px 10px 30px -5px rgba(0, 0, 0, 0.15)",
    transition: { type: "spring", stiffness: 300, damping: 20 }
  };

  const buttonHover = {
    scale: 1.05,
    transition: { type: "spring", stiffness: 400, damping: 15 }
  };



  // Show loading state until translations are loaded
  if (!isLoaded) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-humdb-white">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-humdb-red mx-auto mb-4"></div>
          <p className="text-humdb-gray-600">{t('common.loading')}</p>
        </div>
      </div>
    );
  }

  // Global Overview Mode View
  return (
    <div suppressHydrationWarning={true}>
      <Head>
        <title>{`${t('globalOverview.title')} - ${siteTitle}`}</title>
        <meta name="description" content={t('globalOverview.meta.description')} />
      </Head>

      {/* Hero Section with Dynamic Background Image & Crossfade */}
      <section
        className="relative bg-humdb-gray-900 text-humdb-white py-16 md:py-20 overflow-hidden -mt-20 md:-mt-[136px] xl:-mt-20 pt-36 md:pt-[156px] xl:pt-36" // Added overflow-hidden, extends behind navbar
        role="banner"
        aria-label="Global overview slideshow"
      >
        {/* Background Image Slideshow with Crossfade */}
        <AnimatePresence initial={false}>
          <motion.div
            key={currentImageIndex}
            className="absolute inset-0 bg-cover bg-center z-0"
            style={{ backgroundImage: slideshowImages.length > 0 ? `url('${slideshowImages[currentImageIndex]}')` : 'url("https://placehold.co/1920x800/011E41/FFFFFF?text=Humanitarian+Databank")' }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 1.0, ease: 'easeInOut' }} // Slow crossfade
          />
        </AnimatePresence>

        {/* Overlay */}
        <div className="absolute inset-0 bg-humdb-black bg-opacity-60 z-10"></div>

        {/* Content */}
        <motion.div
          className="w-full px-6 sm:px-8 lg:px-12 text-center relative z-20"
          variants={staggerContainer}
          initial="hidden"
          animate="visible"
        >
          <motion.h1
            className="text-4xl sm:text-5xl md:text-6xl font-extrabold mb-6"
            variants={fadeInUp}
          >
            {siteTitle}
          </motion.h1>
          <motion.p
            className="text-lg sm:text-xl max-w-3xl mx-auto mb-10"
            variants={fadeInUp}
          >
            {t('globalOverview.hero.description')}
          </motion.p>

          {/* Chat Input Section Integrated in Hero */}
          <motion.div
            className="max-w-full mx-auto mb-10 px-4"
            variants={fadeInUp}
          >
            <div className="w-full max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-[auto,minmax(0,1fr)] items-center md:items-stretch gap-4 bg-white bg-opacity-10 backdrop-blur-sm rounded-xl py-3 px-4 border border-white border-opacity-20 transition-all duration-500 ease-out">
              <motion.div
                className="flex-shrink-0 text-center sm:text-left"
                animate={{
                  opacity: (isInputFocused || inputValue.trim()) ? 0 : 1,
                  width: (isInputFocused || inputValue.trim()) ? 0 : 'auto',
                  marginRight: (isInputFocused || inputValue.trim()) ? 0 : 16,
                  height: (isInputFocused || inputValue.trim()) ? 0 : 'auto'
                }}
                transition={{
                  duration: 0.5,
                  ease: "easeOut"
                }}
                style={{ overflow: 'hidden' }}
              >
                <h3 className="text-lg font-semibold text-humdb-white mb-1">
                  {t('chat.hero.title')}
                </h3>
                <p className="text-sm text-humdb-gray-200">
                  {t('chat.hero.description')}
                </p>
            </motion.div>
              <HydrationSafe
                fallback={
                  <div style={{ height: 0 }} />
                }
              >
                <div className="relative w-full md:max-w-[640px] lg:max-w-[720px] xl:max-w-[840px] mx-auto md:justify-self-center transition-all duration-500 ease-out">
                  {/* Conversation History Button (for logged-in users) */}
                  {aiToken && (
                    <div className="relative mb-2">
                      <button
                        type="button"
                        onClick={() => {
                          setShowConversationList(!showConversationList);
                          if (!showConversationList && conversations.length === 0) {
                            loadConversations(aiToken);
                          }
                        }}
                        className="flex items-center gap-2 px-3 py-1.5 text-sm text-humdb-white bg-white bg-opacity-20 hover:bg-opacity-30 rounded-lg transition-all"
                        title="View conversation history"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                        </svg>
                        <span>History</span>
                        {isLoadingConversations && (
                          <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"></path>
                          </svg>
                        )}
                      </button>

                      {/* Conversation List Dropdown */}
                      {showConversationList && (
                        <div className="absolute top-full left-0 mt-2 w-80 max-h-96 overflow-y-auto bg-white rounded-lg shadow-xl border border-humdb-gray-200 z-50">
                          <div className="p-3 border-b border-humdb-gray-200 flex items-center justify-between">
                            <h4 className="font-semibold text-humdb-gray-800">Conversations</h4>
                            <button
                              onClick={() => setShowConversationList(false)}
                              className="text-humdb-gray-500 hover:text-humdb-gray-700"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                              </svg>
                            </button>
                          </div>
                          {conversations.length === 0 ? (
                            <div className="p-4 text-center text-humdb-gray-500 text-sm">
                              {isLoadingConversations ? t('common.loading') : t('chat.conversations.none')}
                            </div>
                          ) : (
                            <div className="divide-y divide-humdb-gray-100">
                              {conversations.map((conv) => (
                                <button
                                  key={conv.id}
                                  onClick={() => loadConversation(conv.id)}
                                  className="w-full text-left p-3 hover:bg-humdb-gray-50 transition-colors"
                                >
                                  <div className="font-medium text-humdb-gray-800 text-sm truncate">
                                    {conv.title || t('chat.conversations.untitled')}
                                  </div>
                                  {conv.last_message_at && (
                                    <div className="text-xs text-humdb-gray-500 mt-1">
                                      {new Date(conv.last_message_at).toLocaleDateString()}
                                    </div>
                                  )}
                                </button>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                <form
                  onSubmit={handleSendMessage}
                  className="relative w-full"
                >
                  <input
                    ref={chatInputRef}
                    type="text"
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                    onFocus={() => setIsInputFocused(true)}
                    onBlur={() => setIsInputFocused(false)}
                    placeholder={t('chat.messages.placeholder')}
                    className="w-full px-4 py-3 pr-16 border border-humdb-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-humdb-red focus:border-transparent text-base bg-white bg-opacity-95 backdrop-blur-sm text-humdb-gray-800 placeholder-humdb-gray-500"
                    disabled={isLoading}
                  />
                  <button
                    type="submit"
                    className={`absolute right-2 top-1/2 transform -translate-y-1/2 flex items-center justify-center w-10 h-10 rounded-full text-white transition-colors duration-150 ${
                      isLoading ? 'bg-humdb-gray-400 cursor-not-allowed' : 'bg-humdb-red hover:bg-humdb-red-dark'
                    }`}
                    disabled={isLoading}
                    aria-label={isLoading ? t('chat.messages.thinking') : t('chat.actions.send')}
                  >
                    {isLoading ? (
                      <svg
                        className="w-5 h-5 animate-spin"
                        fill="none"
                        viewBox="0 0 24 24"
                      >
                        <circle
                          className="opacity-25"
                          cx="12"
                          cy="12"
                          r="10"
                          stroke="currentColor"
                          strokeWidth="4"
                        />
                        <path
                          className="opacity-75"
                          fill="currentColor"
                          d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
                        />
                      </svg>
                    ) : (
                      <svg
                        className="w-5 h-5"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M5 12h14M12 5l7 7-7 7"
                        />
                      </svg>
                    )}
                  </button>
                </form>
                </div>
              </HydrationSafe>
            </div>

            {/* Quick Prompts */}
            <HydrationSafe
              fallback={<div style={{ height: 0 }} />}
            >
              <motion.div
                className="mt-6 flex flex-wrap justify-center gap-3"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3, duration: 0.5 }}
              >
                {[
                  t('globalOverview.quickPrompts.afghanVolunteers'),
                  t('globalOverview.quickPrompts.disasterResponse'),
                  t('globalOverview.quickPrompts.humanitarianIndicators')
                ].map((prompt, index) => (
                  <motion.button
                    key={index}
                    onClick={() => {
                      setInputValue(prompt);
                      // Auto-submit the prompt
                      setTimeout(() => {
                        const form = document.querySelector('form');
                        if (form) {
                          form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
                        }
                      }, 100);
                    }}
                    className="px-4 py-2 bg-white bg-opacity-20 backdrop-blur-sm border border-white border-opacity-30 rounded-lg text-sm text-humdb-white hover:bg-white hover:bg-opacity-30 transition-all duration-200 font-medium"
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                  >
                    {prompt}
                  </motion.button>
                ))}
              </motion.div>
            </HydrationSafe>
          </motion.div>


        </motion.div>
      </section>

      {/* Chat Response Section */}
      <HydrationSafe
        fallback={
          <section className="py-8 bg-humdb-white" style={{ minHeight: '80px' }}>
            <div className="w-full px-6 sm:px-8 lg:px-12">
              <div style={{ opacity: 0 }}>
                <div className="bg-humdb-gray-100 text-humdb-gray-800 px-4 py-3 rounded-xl shadow">
                  {t('common.loading')}
                </div>
              </div>
            </div>
          </section>
        }
      >
        {(currentResponse || isLoading) && (
          <section className="py-8 bg-humdb-white">
            <div className="w-full px-6 sm:px-8 lg:px-12">
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5 }}
              >
                  {/* Loading indicator */}
                  {isLoading && (
                    <div className="flex justify-start mb-4">
                      <div className="bg-humdb-gray-100 text-humdb-gray-800 px-4 py-3 rounded-xl shadow animate-pulse">
                        {t('chat.messages.thinking')}
                      </div>
                    </div>
                  )}

                  {/* Response display */}
                  {currentResponse && !isLoading && (
                  <>
                    <div className="bg-humdb-gray-50 rounded-xl shadow-lg border border-humdb-gray-200 p-6 w-full">
                      <div className="flex flex-col lg:flex-row gap-6">
                                              {/* Text response */}
                      <div className="lg:w-1/2 relative">
                        {/* Copy Button */}
                        <button
                          onClick={() => {
                            // Create a temporary element to get text with source links
                            const tempDiv = document.createElement('div');
                            tempDiv.innerHTML = currentResponse;

                            // Extract text and convert links to readable format
                            const links = tempDiv.querySelectorAll('a');
                            let textWithSources = tempDiv.textContent || tempDiv.innerText || '';

                            // Add source links at the end
                            if (links.length > 0) {
                              textWithSources += `\n\n${t('chat.conversations.sources')}\n`;
                              links.forEach((link, index) => {
                                const linkText = link.textContent || link.innerText || 'source';
                                const linkUrl = link.href;
                                textWithSources += `${index + 1}. ${linkText}: ${linkUrl}\n`;
                              });
                            }

                            navigator.clipboard.writeText(textWithSources).then(() => {
                              // Show a brief success message
                              const button = document.querySelector('.copy-text-btn');
                              if (button) {
                                const originalText = button.innerHTML;
                                button.innerHTML = t('globalOverview.copyButton.copied');
                                button.className = 'absolute top-2 right-2 px-3 py-1 bg-green-500 text-white rounded-md text-xs font-medium transition-all duration-200 z-30';
                                setTimeout(() => {
                                  button.innerHTML = originalText;
                                  button.className = 'absolute top-2 right-2 px-3 py-1 bg-humdb-red text-white rounded-md text-xs font-medium transition-all duration-200 z-30 hover:bg-humdb-red-dark copy-text-btn';
                                }, 2000);
                              }
                            });
                          }}
                          className="absolute top-2 right-2 px-3 py-1 bg-humdb-red text-white rounded-md text-xs font-medium transition-all duration-200 z-30 hover:bg-humdb-red-dark copy-text-btn"
                          title={t('globalOverview.copyButton.copy')}
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                          </svg>
                        </button>
                        <div
                          className="prose prose-sm max-w-none text-humdb-gray-800 pt-8"
                          dangerouslySetInnerHTML={{ __html: currentResponse }}
                          suppressHydrationWarning={true}
                        />
                      </div>

                        {/* Chart display */}
                        {chartData && (
                          <div className="lg:w-1/2 flex-shrink-0">
                            <MultiChart
                              data={chartData.data}
                              type={chartData.type}
                              title={chartData.title}
                              height={400}
                            />
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="mt-8 border-b border-humdb-gray-200"></div>
                  </>
                )}
              </motion.div>
          </div>
        </section>
        )}
      </HydrationSafe>

      {/* Global Map Section */}
      <section className="py-16 bg-humdb-gray-50">
        <div className="w-full px-6 sm:px-8 lg:px-12">
          <div className="max-w-7xl mx-auto">
            {hasActivityTabs && (
              <div className="flex justify-center mb-8">
                <div className="inline-flex bg-white border border-humdb-gray-200 rounded-lg shadow-sm overflow-hidden">
                  {ENABLE_DOMESTIC && (
                    <button
                      type="button"
                      onClick={() => handleActivityViewChange('domestic')}
                      className={`px-5 py-2.5 text-sm font-semibold transition-colors ${
                        activityView === 'domestic'
                          ? 'bg-humdb-red text-white'
                          : 'bg-white text-humdb-gray-700 hover:bg-humdb-gray-50'
                      }`}
                      aria-pressed={activityView === 'domestic'}
                    >
                      Domestic
                    </button>
                  )}
                  {ENABLE_INTERNATIONAL && (
                    <button
                      type="button"
                      onClick={() => handleActivityViewChange('international')}
                      className={`px-5 py-2.5 text-sm font-semibold transition-colors ${
                        activityView === 'international'
                          ? 'bg-humdb-red text-white'
                          : 'bg-white text-humdb-gray-700 hover:bg-humdb-gray-50'
                      }`}
                      aria-pressed={activityView === 'international'}
                    >
                      International
                    </button>
                  )}
                </div>
              </div>
            )}

            {activityView === 'international' ? (
              <div className="bg-white rounded-xl shadow-lg border border-humdb-gray-100 overflow-hidden">
                <div className="p-6 border-b border-humdb-gray-100">
                  {!hasActivityTabs && (
                    <div className="text-sm font-semibold text-humdb-gray-600 uppercase tracking-wide mb-2">
                      International
                    </div>
                  )}
                  {!hasActivityTabs && (
                    <h2 className="text-3xl font-bold text-humdb-navy mb-3">
                      {internationalMapModel.title}
                      {selectedYear && (
                        <span className="text-xl font-normal text-humdb-gray-600 ml-2">
                          ({selectedYear})
                        </span>
                      )}
                      <span className="text-xl font-normal text-humdb-gray-600 ml-2">
                        - {internationalMapModel.indicatorName}
                      </span>
                    </h2>
                  )}
                  {!hasActivityTabs && (
                    <p className="text-lg text-humdb-gray-600 max-w-3xl mx-auto">
                      {internationalMapModel.description}
                    </p>
                  )}
                </div>

                {/* International Indicator Selector */}
                <div className="bg-humdb-white border-b border-humdb-gray-100 overflow-hidden">
                  <div className="flex h-16 overflow-x-auto md:overflow-visible space-x-2 md:space-x-0 px-2 md:px-0">
                    <button
                      onClick={() => setSelectedInternationalIndicator('total-funding')}
                      className={`group relative md:flex-1 flex-shrink-0 px-3 font-semibold transition-all duration-300 md:border-r md:last:border-r-0 ${
                        selectedInternationalIndicator === 'total-funding'
                          ? 'bg-humdb-red text-white'
                          : 'bg-humdb-white text-humdb-gray-700 hover:bg-humdb-gray-50'
                      }`}
                    >
                      <span className="text-sm">Total Funding</span>
                      {selectedInternationalIndicator === 'total-funding' && (
                        <motion.div
                          className="absolute bottom-0 left-0 right-0 h-1 bg-humdb-red"
                          initial={{ scaleX: 0 }}
                          animate={{ scaleX: 1 }}
                          transition={{ type: "spring", stiffness: 500, damping: 30 }}
                        />
                      )}
                    </button>
                    <button
                      onClick={() => setSelectedInternationalIndicator('people-reached')}
                      className={`group relative md:flex-1 flex-shrink-0 px-3 font-semibold transition-all duration-300 md:border-r md:last:border-r-0 ${
                        selectedInternationalIndicator === 'people-reached'
                          ? 'bg-humdb-red text-white'
                          : 'bg-humdb-white text-humdb-gray-700 hover:bg-humdb-gray-50'
                      }`}
                    >
                      <span className="text-sm">People Reached</span>
                      {selectedInternationalIndicator === 'people-reached' && (
                        <motion.div
                          className="absolute bottom-0 left-0 right-0 h-1 bg-humdb-red"
                          initial={{ scaleX: 0 }}
                          animate={{ scaleX: 1 }}
                          transition={{ type: "spring", stiffness: 500, damping: 30 }}
                        />
                      )}
                    </button>
                    <button
                      onClick={() => setSelectedInternationalIndicator('services')}
                      className={`group relative md:flex-1 flex-shrink-0 px-3 font-semibold transition-all duration-300 md:border-r md:last:border-r-0 ${
                        selectedInternationalIndicator === 'services'
                          ? 'bg-humdb-red text-white'
                          : 'bg-humdb-white text-humdb-gray-700 hover:bg-humdb-gray-50'
                      }`}
                    >
                      <span className="text-sm">Services</span>
                      {selectedInternationalIndicator === 'services' && (
                        <motion.div
                          className="absolute bottom-0 left-0 right-0 h-1 bg-humdb-red"
                          initial={{ scaleX: 0 }}
                          animate={{ scaleX: 1 }}
                          transition={{ type: "spring", stiffness: 500, damping: 30 }}
                        />
                      )}
                    </button>
                  </div>
                </div>

                <div id="map-container" className="rounded-b-xl overflow-hidden">
                  <InteractiveWorldMap
                    selectedIndicator="international"
                    indicatorName={internationalMapModel.indicatorName}
                    indicatorData={internationalMapModel.indicatorData}
                    flowLines={internationalMapModel.flows}
                    internationalIndicatorType={selectedInternationalIndicator}
                    internationalIndicatorUnit={internationalMapModel.indicatorUnit}
                    visualizationType={visualizationType}
                    onCountryClick={handleCountryClick}
                    globalTotal={internationalMapModel.globalTotal}
                    isLoadingData={false}
                    onCountryHover={handleCountryHover}
                    onCountryLeave={handleCountryLeave}
                    hoveredCountry={hoveredCountry}
                    hoveredValue={hoveredValue}
                    onVisualizationTypeChange={setVisualizationType}
                    regionName={isNationalScope ? label : siteTitle}
                    selectedRegion="global"
                    availableYears={availableYears}
                    selectedYear={selectedYear}
                    onYearChange={setSelectedYear}
                    scopeType="global"
                    // For International view we still render the world (Leaflet), but when a demo country
                    // is selected (e.g. Qatar) we pass its ISO codes so the map can auto-zoom to active flows.
                    scopeCountryIso2={isNationalScope ? countryIso2 : null}
                    scopeCountryIso3={isNationalScope ? countryIso3 : null}
                    yearTimeline={(() => {
                      if (isLoadingYears) {
                        return (
                          <div className="flex items-center justify-center">
                            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-humdb-red"></div>
                          </div>
                        );
                      }

                      if (availableYears.length === 0) {
                        return null;
                      }

                      return (
                        <div className="flex flex-col space-y-3">
                          {availableYears.map((year, index) => (
                            <motion.button
                              key={year}
                              onClick={() => setSelectedYear(year)}
                              className="relative flex items-center space-x-3 group"
                              whileHover={{ scale: 1.05 }}
                              whileTap={{ scale: 0.95 }}
                            >
                              {/* Timeline dot */}
                              <div className={`relative w-4 h-4 rounded-full border-2 transition-all duration-200 ${
                                selectedYear === year
                                  ? 'bg-humdb-red border-humdb-red shadow-lg'
                                  : 'bg-white border-humdb-gray-300 group-hover:border-humdb-red group-hover:bg-humdb-red'
                              }`}>
                                {/* Timeline line (except for last item) */}
                                {index < availableYears.length - 1 && (
                                  <div className="absolute left-1/2 top-4 w-0.5 h-8 bg-humdb-gray-300 transition-all duration-200" style={{ transform: 'translateX(-50%)' }}></div>
                                )}
                              </div>

                              {/* Year label */}
                              <span className={`text-xs font-medium transition-all duration-200 ${
                                selectedYear === year
                                  ? 'text-humdb-red font-bold'
                                  : 'text-humdb-gray-600 group-hover:text-humdb-red'
                              }`}>
                                {year}
                              </span>
                            </motion.button>
                          ))}
                        </div>
                      );
                    })()}
                  />
                </div>
              </div>
            ) : (
              <>
            <motion.div
              className="text-center mb-12"
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.6 }}
            >
              {!hasActivityTabs && (
                <div className="text-sm font-semibold text-humdb-gray-600 uppercase tracking-wide mb-2">
                  Domestic
                </div>
              )}
              <h2 className="text-3xl font-bold text-humdb-navy mb-4">
                {(() => {
                  // Use NS name in demo mode with country scope, otherwise use region name
                  const regionName = (isDemoMode && isNationalScope && nationalSocietyName)
                    ? nationalSocietyName
                    : (selectedRegion === 'global' ? t('globalOverview.regions.global') : regions[selectedRegion]?.name);
                  return t('globalOverview.map.title', { region: regionName });
                })()}
                {selectedYear && (
                  <span className="text-xl font-normal text-humdb-gray-600 ml-2">
                    ({selectedYear})
                  </span>
                )}
                {activeIndicator !== 'people-reached' && (
                  <span className="text-xl font-normal text-humdb-gray-600 ml-2">
                    - {getCurrentIndicatorName()}
                  </span>
                )}
              </h2>
              <p className="text-lg text-humdb-gray-600 max-w-3xl mx-auto">
                {(() => {
                  // Determine location text - use country name when NS is selected, otherwise use region
                  let locationText;
                  // Get country name - prefer scopeCountryName, then label, fallback to getCountryName
                  let countryNameForLocation = null;
                  if (isNationalScope) {
                    if (scopeCountryName) {
                      countryNameForLocation = scopeCountryName;
                    } else if (label && !label.includes('(')) {
                      // Use label if it doesn't contain parentheses (which would indicate NS name format)
                      countryNameForLocation = label;
                    } else if (countryIso2) {
                      countryNameForLocation = getCountryName(String(countryIso2).toUpperCase());
                    } else if (countryIso3) {
                      countryNameForLocation = getCountryName(String(countryIso3).toUpperCase());
                    }
                  }

                  if (isDemoMode && isNationalScope && countryNameForLocation) {
                    locationText = t('globalOverview.map.nationalLocation', { country: countryNameForLocation });
                  } else {
                    locationText = selectedRegion === 'global'
                      ? t('globalOverview.map.globalLocation')
                      : t('globalOverview.map.regionalLocation', { region: regions[selectedRegion]?.name });
                  }

                  return t('globalOverview.map.description', {
                    organization: organizationName,
                    location: locationText,
                    year: selectedYear ? t('globalOverview.map.yearFilter', { year: selectedYear }) : '',
                    indicatorInstruction: activeIndicator === 'people-reached' ? t('globalOverview.map.peopleReachedInstruction') : t('globalOverview.map.indicatorInstruction')
                  });
                })()}
              </p>
            </motion.div>

            {/* Enhanced Indicator Selector */}
            <div className={`bg-humdb-white shadow-lg border border-humdb-gray-100 overflow-hidden ${selectedIndicator === 'people-reached' ? 'mb-0' : 'mb-8'}`}>
              <div className="flex h-16 overflow-x-auto md:overflow-visible space-x-2 md:space-x-0 px-2 md:px-0">
                <button
                  onClick={() => {
                    setSelectedIndicator('volunteers');
                    setActiveIndicator('volunteers');
                    setSelectedSubIndicator(null);
                    setOpenDropdown(null);
                    setIsPeopleReachedExpanded(false);
                  }}
                  className={`group relative md:flex-1 flex-shrink-0 px-3 font-semibold transition-all duration-300 md:border-r md:last:border-r-0 ${
                    selectedIndicator === 'volunteers'
                      ? 'bg-humdb-red text-white'
                      : 'bg-humdb-white text-humdb-gray-700 hover:bg-humdb-gray-50'
                  }`}
                >
                  <span className="text-sm">{t('globalOverview.indicators.volunteers')}</span>
                  {selectedIndicator === 'volunteers' && (
                    <motion.div
                      className="absolute bottom-0 left-0 right-0 h-1 bg-humdb-red"
                      initial={{ scaleX: 0 }}
                      animate={{ scaleX: 1 }}
                      transition={{ type: "spring", stiffness: 500, damping: 30 }}
                    />
                  )}
                </button>
                <button
                  onClick={() => {
                    setSelectedIndicator('staff');
                    setActiveIndicator('staff');
                    setSelectedSubIndicator(null);
                    setOpenDropdown(null);
                    setIsPeopleReachedExpanded(false);
                  }}
                  className={`group relative md:flex-1 flex-shrink-0 px-3 font-semibold transition-all duration-300 md:border-r md:last:border-r-0 ${
                    selectedIndicator === 'staff'
                      ? 'bg-humdb-red text-white'
                      : 'bg-humdb-white text-humdb-gray-700 hover:bg-humdb-gray-50'
                  }`}
                >
                  <span className="text-sm">{t('globalOverview.indicators.staff')}</span>
                  {selectedIndicator === 'staff' && (
                    <motion.div
                      className="absolute bottom-0 left-0 right-0 h-1 bg-humdb-red"
                      initial={{ scaleX: 0 }}
                      animate={{ scaleX: 1 }}
                      transition={{ type: "spring", stiffness: 500, damping: 30 }}
                    />
                  )}
                </button>
                <button
                  onClick={() => {
                    setSelectedIndicator('branches');
                    setActiveIndicator('branches');
                    setSelectedSubIndicator(null);
                    setOpenDropdown(null);
                    setIsPeopleReachedExpanded(false);
                  }}
                  className={`group relative md:flex-1 flex-shrink-0 px-3 font-semibold transition-all duration-300 md:border-r md:last:border-r-0 ${
                    selectedIndicator === 'branches'
                      ? 'bg-humdb-red text-white'
                      : 'bg-humdb-white text-humdb-gray-700 hover:bg-humdb-gray-50'
                  }`}
                >
                  <span className="text-sm">{t('globalOverview.indicators.branches')}</span>
                  {selectedIndicator === 'branches' && (
                    <motion.div
                      className="absolute bottom-0 left-0 right-0 h-1 bg-humdb-red"
                      initial={{ scaleX: 0 }}
                      animate={{ scaleX: 1 }}
                      transition={{ type: "spring", stiffness: 500, damping: 30 }}
                    />
                  )}
                </button>
                <button
                  onClick={() => {
                    setSelectedIndicator('local-units');
                    setActiveIndicator('local-units');
                    setSelectedSubIndicator(null);
                    setOpenDropdown(null);
                    setIsPeopleReachedExpanded(false);
                  }}
                  className={`group relative md:flex-1 flex-shrink-0 px-3 font-semibold transition-all duration-300 md:border-r md:last:border-r-0 ${
                    selectedIndicator === 'local-units'
                      ? 'bg-humdb-red text-white'
                      : 'bg-humdb-white text-humdb-gray-700 hover:bg-humdb-gray-50'
                  }`}
                >
                  <span className="text-sm">{t('globalOverview.indicators.localUnits')}</span>
                  {selectedIndicator === 'local-units' && (
                    <motion.div
                      className="absolute bottom-0 left-0 right-0 h-1 bg-humdb-red"
                      initial={{ scaleX: 0 }}
                      animate={{ scaleX: 1 }}
                      transition={{ type: "spring", stiffness: 500, damping: 30 }}
                    />
                  )}
                </button>
                <button
                  onClick={() => {
                    setSelectedIndicator('blood-donors');
                    setActiveIndicator('blood-donors');
                    setSelectedSubIndicator(null);
                    setOpenDropdown(null);
                    setIsPeopleReachedExpanded(false);
                  }}
                  className={`group relative md:flex-1 flex-shrink-0 px-3 font-semibold transition-all duration-300 md:border-r md:last:border-r-0 ${
                    selectedIndicator === 'blood-donors'
                      ? 'bg-humdb-red text-white'
                      : 'bg-humdb-white text-humdb-gray-700 hover:bg-humdb-gray-50'
                  }`}
                >
                  <span className="text-sm">{t('globalOverview.indicators.bloodDonors')}</span>
                  {selectedIndicator === 'blood-donors' && (
                    <motion.div
                      className="absolute bottom-0 left-0 right-0 h-1 bg-humdb-red"
                      initial={{ scaleX: 0 }}
                      animate={{ scaleX: 1 }}
                      transition={{ type: "spring", stiffness: 500, damping: 30 }}
                    />
                  )}
                </button>
                <button
                  onClick={() => {
                    setSelectedIndicator('first-aid');
                    setActiveIndicator('first-aid');
                    setSelectedSubIndicator(null);
                    setOpenDropdown(null);
                    setIsPeopleReachedExpanded(false);
                  }}
                  className={`group relative md:flex-1 flex-shrink-0 px-3 font-semibold transition-all duration-300 md:border-r md:last:border-r-0 ${
                    selectedIndicator === 'first-aid'
                      ? 'bg-humdb-red text-white'
                      : 'bg-humdb-white text-humdb-gray-700 hover:bg-humdb-gray-50'
                  }`}
                >
                  <span className="text-sm">{t('globalOverview.indicators.firstAid')}</span>
                  {selectedIndicator === 'first-aid' && (
                    <motion.div
                      className="absolute bottom-0 left-0 right-0 h-1 bg-humdb-red"
                      initial={{ scaleX: 0 }}
                      animate={{ scaleX: 1 }}
                      transition={{ type: "spring", stiffness: 500, damping: 30 }}
                    />
                  )}
                </button>
                <button
                  onClick={() => {
                    setSelectedIndicator('people-reached');
                    // Toggle the expanded state
                    setIsPeopleReachedExpanded(!isPeopleReachedExpanded);
                    // Don't change activeIndicator - keep the current one for map filtering
                    // Don't clear selectedSubIndicator - keep it for visual feedback
                    setOpenDropdown(null);
                  }}
                  className={`group relative md:flex-1 flex-shrink-0 px-3 font-semibold transition-all duration-300 md:border-r md:last:border-r-0 ${
                    selectedIndicator === 'people-reached'
                      ? 'bg-humdb-red text-white'
                      : 'bg-humdb-white text-humdb-gray-700 hover:bg-humdb-gray-50'
                  }`}
                >
                  <div className="flex items-center justify-center">
                    <span className="text-sm">{t('globalOverview.indicators.peopleReached')}</span>
                    <svg
                      className={`ml-2 w-4 h-4 transition-transform duration-200 ${isPeopleReachedExpanded ? 'rotate-180' : ''}`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </div>
                  {selectedIndicator === 'people-reached' && (
                    <motion.div
                      className="absolute bottom-0 left-0 right-0 h-1 bg-humdb-red"
                      initial={{ scaleX: 0 }}
                      animate={{ scaleX: 1 }}
                      transition={{ type: "spring", stiffness: 500, damping: 30 }}
                    />
                  )}
                </button>
                <button
                  onClick={() => {
                    setSelectedIndicator('income');
                    setActiveIndicator('income');
                    setSelectedSubIndicator(null);
                    setOpenDropdown(null);
                    setIsPeopleReachedExpanded(false);
                  }}
                  className={`group relative md:flex-1 flex-shrink-0 px-3 font-semibold transition-all duration-300 md:border-r md:last:border-r-0 ${
                    selectedIndicator === 'income'
                      ? 'bg-humdb-red text-white'
                      : 'bg-humdb-white text-humdb-gray-700 hover:bg-humdb-gray-50'
                  }`}
                >
                  <span className="text-sm">{t('globalOverview.indicators.income')}</span>
                  {selectedIndicator === 'income' && (
                    <motion.div
                      className="absolute bottom-0 left-0 right-0 h-1 bg-humdb-red"
                      initial={{ scaleX: 0 }}
                      animate={{ scaleX: 1 }}
                      transition={{ type: "spring", stiffness: 500, damping: 30 }}
                    />
                  )}
                </button>
                <button
                  onClick={() => {
                    setSelectedIndicator('expenditure');
                    setActiveIndicator('expenditure');
                    setSelectedSubIndicator(null);
                    setOpenDropdown(null);
                    setIsPeopleReachedExpanded(false);
                  }}
                  className={`group relative md:flex-1 flex-shrink-0 px-3 font-semibold transition-all duration-300 md:border-r md:last:border-r-0 ${
                    selectedIndicator === 'expenditure'
                      ? 'bg-humdb-red text-white'
                      : 'bg-humdb-white text-humdb-gray-700 hover:bg-humdb-gray-50'
                  }`}
                >
                  <span className="text-sm">{t('globalOverview.indicators.expenditure')}</span>
                  {selectedIndicator === 'expenditure' && (
                    <motion.div
                      className="absolute bottom-0 left-0 right-0 h-1 bg-humdb-red"
                      initial={{ scaleX: 0 }}
                      animate={{ scaleX: 1 }}
                      transition={{ type: "spring", stiffness: 500, damping: 30 }}
                    />
                  )}
                </button>
              </div>
            </div>





            {/* Secondary Indicator Bar for People Reached */}
            {isPeopleReachedExpanded && (
              <motion.div
                className="bg-humdb-white shadow-lg mb-8 border border-humdb-gray-100"
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.3, ease: "easeOut" }}
              >
                <div className="flex relative overflow-x-auto overflow-y-visible md:overflow-visible min-h-[4rem] md:h-16">
                  {Object.entries(peopleReachedSubIndicators).map(([key, indicator], index) => (
                    <div
                      key={key}
                      className={`dropdown-container group relative flex-shrink-0 w-52 md:w-auto md:flex-1 font-semibold transition-all duration-300 border-r border-humdb-gray-200 last:border-r-0 hover:bg-humdb-gray-50 hover:border-humdb-red cursor-pointer ${
                        selectedSubIndicator && indicator.indicators.some(sub => sub.id === selectedSubIndicator.id)
                          ? 'bg-humdb-red bg-opacity-10 border-humdb-red'
                          : ''
                      }`}
                    >
                      <div
                        className="flex items-center justify-start h-full px-4"
                        onClick={() => setOpenDropdown(openDropdown === key ? null : key)}
                      >
                        <span className="text-sm">{indicator.name}</span>
                        <svg
                          className={`ml-auto w-4 h-4 transition-transform duration-200 ${openDropdown === key ? 'rotate-180' : ''}`}
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                        </svg>
                      </div>

                      {/* Dropdown List */}
                      {isMobile ? (
                        openDropdown === key && (
                          <div className="fixed inset-0 z-[10000]">
                            <div
                              className="absolute inset-0 bg-black bg-opacity-40"
                              onClick={() => setOpenDropdown(null)}
                            />
                            <div className="absolute left-0 right-0 bottom-0 bg-white border-t border-humdb-gray-200 rounded-t-xl shadow-2xl max-h-[60vh] overflow-y-auto">
                              {indicator.indicators.map((subIndicator) => (
                                <button
                                  key={subIndicator.id}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setSelectedSubIndicator(subIndicator);
                                    setActiveIndicator(`people-reached-${subIndicator.id}`);
                                    const updatedMapping = {
                                      ...keyIndicatorsMapping,
                                      [`people-reached-${subIndicator.id}`]: {
                                        id: subIndicator.id,
                                        name: subIndicator.name,
                                        unit: subIndicator.unit
                                      }
                                    };
                                    fetchIndicatorData(`people-reached-${subIndicator.id}`);
                                    setOpenDropdown(null);
                                  }}
                                  className="w-full text-left px-4 py-3 text-sm text-humdb-gray-700 hover:bg-humdb-red hover:text-white transition-colors duration-150 border-b border-humdb-gray-100 last:border-b-0 whitespace-normal"
                                >
                                  {subIndicator.name}
                                </button>
                              ))}
                            </div>
                          </div>
                        )
                      ) : (
                        <div className={`absolute top-full left-0 transition-all duration-200 pointer-events-auto z-[9999] mt-1 ${
                          openDropdown === key ? 'opacity-100 visible' : 'opacity-0 invisible'
                        }`}>
                          <div className="bg-white border border-humdb-gray-200 shadow-xl rounded-md overflow-hidden min-w-[300px] max-w-[500px] max-h-72 overflow-y-auto">
                            {indicator.indicators.map((subIndicator) => (
                              <button
                                key={subIndicator.id}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setSelectedSubIndicator(subIndicator);
                                  // Set the active indicator to trigger map filtering
                                  setActiveIndicator(`people-reached-${subIndicator.id}`);
                                  // Update the indicator mapping to use the sub-indicator
                                  const updatedMapping = {
                                    ...keyIndicatorsMapping,
                                    [`people-reached-${subIndicator.id}`]: {
                                      id: subIndicator.id,
                                      name: subIndicator.name,
                                      unit: subIndicator.unit
                                    }
                                  };
                                  // Trigger data fetch with new indicator
                                  fetchIndicatorData(`people-reached-${subIndicator.id}`);
                                  // Close the dropdown
                                  setOpenDropdown(null);
                                }}
                                className="w-full text-left px-4 py-3 text-sm text-humdb-gray-700 hover:bg-humdb-red hover:text-white transition-colors duration-150 border-b border-humdb-gray-100 last:border-b-0 whitespace-normal"
                              >
                                {subIndicator.name}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </motion.div>
            )}





            {/* Interactive World Map */}
            <motion.div
              id="map-container"
              className="bg-white rounded-xl shadow-lg overflow-hidden relative"
              initial={{ opacity: 0, scale: 0.95 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true }}
              transition={{ duration: 0.8, delay: 0.2 }}
            >
              {(() => {
                const filteredData = getFilteredCountryData();
                const regionalTotal = getRegionalTotal();

                // Apply national-scope filtering (e.g., Syria only for SARC)
                let scopedData = filteredData;
                if (isNationalScope && countryIso2) {
                  const targetCodes = [countryIso2].filter(Boolean);
                  const picked = {};

                  for (const code of targetCodes) {
                    if (filteredData && filteredData[code]) {
                      picked[code] = filteredData[code];
                    }
                  }

                  if (Object.keys(picked).length === 0 && filteredData) {
                    const keys = Object.keys(filteredData);
                    for (const code of targetCodes) {
                      const match = keys.find(k => String(k).toUpperCase() === String(code).toUpperCase());
                      if (match) picked[match] = filteredData[match];
                    }
                  }

                  scopedData = picked;
                }

                const mapData = Object.fromEntries(
                  Object.entries(scopedData).map(([code]) => [
                    code,
                    {
                      value: getIndicatorValue(code, activeIndicator),
                      name: getCountryName(code)
                    }
                  ])
                );

                const scopedTotal = isNationalScope
                  ? Object.entries(mapData).reduce((sum, [code]) => sum + getIndicatorValue(code, activeIndicator), 0)
                  : (selectedRegion === 'global' ? globalTotal : regionalTotal);

                return (
                  <InteractiveWorldMap
                    selectedIndicator={activeIndicator}
                    indicatorName={getCurrentIndicatorName()}
                    indicatorData={mapData}
                    visualizationType={visualizationType}
                    onCountryClick={handleCountryClick}
                    globalTotal={scopedTotal}
                    isLoadingData={isLoadingData}
                    onCountryHover={handleCountryHover}
                    onCountryLeave={handleCountryLeave}
                    hoveredCountry={hoveredCountry}
                    hoveredValue={hoveredValue}
                    onVisualizationTypeChange={setVisualizationType}
                    regionName={isNationalScope ? label : (selectedRegion === 'global' ? null : regions[selectedRegion]?.name)}
                    selectedRegion={isNationalScope ? 'global' : selectedRegion}
                    availableYears={availableYears}
                    selectedYear={selectedYear}
                    onYearChange={setSelectedYear}
                    scopeType={scope?.type || 'global'}
                    scopeCountryIso2={countryIso2}
                    scopeCountryIso3={countryIso3}
                    yearTimeline={(() => {
                      if (isLoadingYears) {
                        return (
                          <div className="flex items-center justify-center">
                            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-humdb-red"></div>
                          </div>
                        );
                      }

                                              return (
                          <div className="flex flex-col space-y-3">
                            {availableYears.map((year, index) => (
                                            <motion.button
                key={year}
                onClick={() => setSelectedYear(year)}
                className="relative flex items-center space-x-3 group"
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
              >
                {/* Timeline dot */}
                <div className={`relative w-4 h-4 rounded-full border-2 transition-all duration-200 ${
                  selectedYear === year
                    ? 'bg-humdb-red border-humdb-red shadow-lg'
                    : 'bg-white border-humdb-gray-300 group-hover:border-humdb-red group-hover:bg-humdb-red'
                }`}>
                  {/* Timeline line (except for last item) */}
                  {index < availableYears.length - 1 && (
                    <div className="absolute left-1/2 top-4 w-0.5 h-8 bg-humdb-gray-300 transition-all duration-200" style={{ transform: 'translateX(-50%)' }}></div>
                  )}
                </div>

                {/* Year label */}
                <span className={`text-xs font-medium transition-all duration-200 ${
                  selectedYear === year
                    ? 'text-humdb-red font-bold'
                    : 'text-humdb-gray-600 group-hover:text-humdb-red'
                }`}>
                  {year}
                </span>
              </motion.button>
            ))}
          </div>
        );
      })()}
    />
  );
})()}
            </motion.div>



            {/* Region Selector - Below Map (global scope only) */}
            {!isNationalScope && (
            <motion.div
              className="mt-6 bg-humdb-white shadow-lg border border-humdb-gray-100 rounded-lg"
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: 0.1 }}
            >
              <div className="flex flex-wrap items-center justify-between gap-4 px-6 py-4">
                <div className="flex flex-wrap items-center gap-4">
                  <div className="flex items-center space-x-2">
                    <svg className="w-5 h-5 text-humdb-red" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <label className="text-sm font-semibold text-humdb-gray-700">
                      {t('globalOverview.map.regionSelector')}
                    </label>
                  </div>
                  <div className="relative">
                    <select
                      value={selectedRegion}
                      onChange={(e) => setSelectedRegion(e.target.value)}
                      className="appearance-none bg-white border border-humdb-gray-300 rounded-lg px-4 py-2 pr-8 text-sm font-medium text-humdb-gray-700 focus:outline-none focus:ring-2 focus:ring-humdb-red focus:border-transparent cursor-pointer hover:border-humdb-gray-400 transition-colors"
                    >
                      {Object.entries(regions).map(([key, region]) => (
                        <option key={key} value={key}>
                          {region.name}
                        </option>
                      ))}
                    </select>
                    <div className="absolute inset-y-0 right-0 flex items-center pr-2 pointer-events-none">
                      <svg className="w-4 h-4 text-humdb-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                      </svg>
                    </div>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  {selectedRegion !== 'global' && (
                    <div className="flex items-center space-x-2">
                      <div className="w-2 h-2 bg-humdb-red rounded-full"></div>
                      <span className="text-sm text-humdb-gray-600">
                        {t('globalOverview.map.countriesInRegion', {
                          count: regions[selectedRegion]?.countries?.length || 0,
                          region: regions[selectedRegion]?.name
                        })}
                      </span>
                    </div>
                  )}
                  {selectedRegion === 'global' && (
                    <div className="flex items-center space-x-2">
                      <div className="w-2 h-2 bg-humdb-gray-400 rounded-full"></div>
                      <span className="text-sm text-humdb-gray-600">
                        {t('globalOverview.map.allRegions')}
                      </span>
                    </div>
                  )}
                  {!isLoadingData && (
                    <div className="flex items-center space-x-2">
                      <span className="text-sm font-medium text-humdb-gray-800">
                        {t('globalOverview.map.total', { value: formatNumber(selectedRegion === 'global' ? globalTotal : getRegionalTotal()) })}
                      </span>
                    </div>
                  )}

                  {/* Download Buttons */}
                  <div className="flex items-center space-x-2">
                    <button
                      onClick={handleDownloadCSV}
                      disabled={isDownloadingCSV || isLoadingData || Object.keys(getFilteredCountryData()).length === 0}
                      className="p-2 rounded-lg text-white transition-all duration-200 shadow-md border-2"
                      title={t('globalOverview.map.downloadCSV')}
                      style={{
                        minWidth: '32px',
                        minHeight: '32px',
                        backgroundColor: isDownloadingCSV || isLoadingData || Object.keys(getFilteredCountryData()).length === 0 ? '#9CA3AF' : '#28A745',
                        borderColor: isDownloadingCSV || isLoadingData || Object.keys(getFilteredCountryData()).length === 0 ? '#9CA3AF' : '#28A745'
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

                    <button
                      onClick={handleDownloadPNG}
                      disabled={isDownloadingPNG || isLoadingData}
                      className="p-2 rounded-lg text-white transition-all duration-200 shadow-md border-2"
                      title={t('globalOverview.map.downloadPNG')}
                      style={{
                        minWidth: '32px',
                        minHeight: '32px',
                        backgroundColor: isDownloadingPNG || isLoadingData ? '#9CA3AF' : '#3B82F6',
                        borderColor: isDownloadingPNG || isLoadingData ? '#9CA3AF' : '#3B82F6'
                      }}
                    >
                      {isDownloadingPNG ? (
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                      ) : (
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                        </svg>
                      )}
                    </button>
                  </div>
                </div>
              </div>
            </motion.div>
            )}
              </>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
