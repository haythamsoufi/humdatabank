import React from 'react';
import Head from 'next/head';
import Link from 'next/link';
import { useRouter } from 'next/router';
import { useState, useEffect } from 'react';
import { getIndicatorBank, getSectorsSubsectors, getCommonWords } from '../../lib/apiService';
import { useTranslation } from '../../lib/useTranslation';
import { processIndicatorName, initializeTooltips, addCommonWordsStyles } from '../../lib/commonWordsUtils';
import { TranslationSafe } from '../../components/ClientOnly';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:5000';
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || '';

// Enable SSR to avoid build-time failures when API is unavailable
export async function getServerSideProps() {
  return { props: {} };
}

export default function IndicatorDetailPage() {
  const router = useRouter();
  const { id } = router.query;
  const { t, tWithFallback, isLoaded } = useTranslation();
  const isRTL = router.locale === 'ar';

  // State
  const [indicator, setIndicator] = useState(null);
  const [allIndicators, setAllIndicators] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [expandedSectors, setExpandedSectors] = useState({});
  const [expandedSubSectors, setExpandedSubSectors] = useState({});
  const [initialScrollDone, setInitialScrollDone] = useState(false);
  const [commonWords, setCommonWords] = useState([]);

  // Suggest Updates Modal State
  const [showSuggestModal, setShowSuggestModal] = useState(false);
  const [suggestForm, setSuggestForm] = useState({
    name: '',
    email: '',
    suggestion_type: 'correction',
    // Indicator fields
    indicator_name: '',
    definition: '',
    type: '',
    unit: '',
    sector: {
      primary: '',
      secondary: '',
      tertiary: ''
    },
    sub_sector: {
      primary: '',
      secondary: '',
      tertiary: ''
    },
    emergency: false,
    related_programs: '',
    // Additional fields
    reason: '',
    additional_notes: ''
  });

  // Sector and Subsector data
  const [sectors, setSectors] = useState([]);
  const [subsectors, setSubsectors] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [submitSuccess, setSubmitSuccess] = useState(false);

  const currentId = id ? parseInt(id) : null;

  // Fetch data on mount and when ID changes
  useEffect(() => {
    if (!router.isReady || !id) return;

    const fetchData = async () => {
      setLoading(true);
      setError(null);

      try {
        // Fetch all indicators for sidebar navigation with locale (this includes the specific indicator)
        const allIndicatorsData = await getIndicatorBank('', '', '', '', '', false, router.locale);

        // Find the specific indicator from the processed data
        const specificIndicator = allIndicatorsData.indicators?.find(ind => ind.id === parseInt(id));

        if (!specificIndicator) {
          setError(t('errors.indicatorNotFound'));
          return;
        }

        // Fetch sectors and subsectors with locale
        const sectorsResponse = await getSectorsSubsectors(router.locale);

        // Fetch common words for tooltips
        const commonWordsResponse = await getCommonWords(router.locale);

        setIndicator(specificIndicator);
        setAllIndicators(allIndicatorsData.indicators || []);
        setSectors(sectorsResponse.sectors || []);
        setSubsectors(sectorsResponse.sectors?.flatMap(sector => sector.subsectors || []) || []);
        setCommonWords(commonWordsResponse.common_words || []);
      } catch (err) {
        console.error("Failed to fetch indicator:", err);
        setError(t('errors.failedToLoadIndicatorDetails'));
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [router.isReady, id, router.locale]);

  // Initialize tooltips and styles when common words are loaded
  useEffect(() => {
    if (commonWords.length > 0) {
      addCommonWordsStyles();
      initializeTooltips();
    }
  }, [commonWords]);

  // Group indicators by sector and subsector
  const groupedIndicators = allIndicators.reduce((acc, ind) => {
    // Handle sector - could be string or object
    let sector = 'Other';
    if (ind.sector) {
      if (typeof ind.sector === 'string') {
        sector = ind.sector;
      } else if (typeof ind.sector === 'object' && ind.sector !== null) {
        sector = String(ind.sector.localized_name || ind.sector.primary || ind.sector.name || 'Other');
      }
    }

    // Handle sub_sector - could be string or object
    let subSector = 'General';
    if (ind.sub_sector) {
      if (typeof ind.sub_sector === 'string') {
        subSector = ind.sub_sector;
      } else if (typeof ind.sub_sector === 'object' && ind.sub_sector !== null) {
        subSector = String(ind.sub_sector.localized_name || ind.sub_sector.primary || ind.sub_sector.name || 'General');
      }
    }

    if (!acc[sector]) {
      acc[sector] = {};
    }
    if (!acc[sector][subSector]) {
      acc[sector][subSector] = [];
    }
    acc[sector][subSector].push(ind);
    return acc;
  }, {});

  // Filter indicators based on search term
  const filteredIndicators = allIndicators.filter(ind =>
    (ind.localized_name || ind.name) && (ind.localized_name || ind.name).toLowerCase().includes(searchTerm.toLowerCase())
  );

  // Group filtered indicators by sector and subsector
  const filteredGroupedIndicators = filteredIndicators.reduce((acc, ind) => {
    // Handle sector - could be string or object
    let sector = 'Other';
    if (ind.sector) {
      if (typeof ind.sector === 'string') {
        sector = ind.sector;
      } else if (typeof ind.sector === 'object' && ind.sector !== null) {
        sector = String(ind.sector.localized_name || ind.sector.primary || ind.sector.name || 'Other');
      }
    }

    // Handle sub_sector - could be string or object
    let subSector = 'General';
    if (ind.sub_sector) {
      if (typeof ind.sub_sector === 'string') {
        subSector = ind.sub_sector;
      } else if (typeof ind.sub_sector === 'object' && ind.sub_sector !== null) {
        subSector = String(ind.sub_sector.localized_name || ind.sub_sector.primary || ind.sub_sector.name || 'General');
      }
    }

    if (!acc[sector]) {
      acc[sector] = {};
    }
    if (!acc[sector][subSector]) {
      acc[sector][subSector] = [];
    }
    acc[sector][subSector].push(ind);
    return acc;
  }, {});

  // Sort sectors and subsectors alphabetically, but put "Other" last
  const sortedSectors = Object.keys(filteredGroupedIndicators).sort((a, b) => {
    if (a === 'Other') return 1;
    if (b === 'Other') return -1;
    return a.localeCompare(b);
  });

  // Initialize expanded states - expand all sectors and subsectors by default
  React.useEffect(() => {
    const allSectors = {};
    const allSubSectors = {};

    Object.keys(filteredGroupedIndicators).forEach(sector => {
      allSectors[sector] = true;
      Object.keys(filteredGroupedIndicators[sector]).forEach(subSector => {
        allSubSectors[`${sector}-${subSector}`] = true;
      });
    });

    setExpandedSectors(allSectors);
    setExpandedSubSectors(allSubSectors);
  }, [JSON.stringify(Object.keys(filteredGroupedIndicators))]);

  // Auto-scroll to current indicator within sidebar only
  React.useEffect(() => {
    if (!initialScrollDone && currentId) {
      const timer = setTimeout(() => {
        const currentElement = document.querySelector(`[data-indicator-id="${currentId}"]`);
        const sidebarContainer = document.querySelector('[data-sidebar-scroll]');

        if (currentElement && sidebarContainer) {
          const containerRect = sidebarContainer.getBoundingClientRect();
          const elementRect = currentElement.getBoundingClientRect();

          // Calculate the scroll position to center the element in the sidebar
          const scrollTop = sidebarContainer.scrollTop +
            (elementRect.top - containerRect.top) -
            (containerRect.height / 2) +
            (elementRect.height / 2);

          sidebarContainer.scrollTo({
            top: scrollTop,
            behavior: 'smooth'
          });

          setInitialScrollDone(true);
        }
      }, 500); // Small delay to ensure DOM is rendered

      return () => clearTimeout(timer);
    }
  }, [currentId, initialScrollDone, expandedSectors, expandedSubSectors]);

  // Toggle functions for expand/collapse
  const toggleSector = (sector) => {
    setExpandedSectors(prev => ({
      ...prev,
      [sector]: !prev[sector]
    }));
  };

  const toggleSubSector = (sector, subSector) => {
    const key = `${sector}-${subSector}`;
    setExpandedSubSectors(prev => ({
      ...prev,
      [key]: !prev[key]
    }));
  };

  // Suggest Updates Modal Functions
  const openSuggestModal = () => {
    setShowSuggestModal(true);

    // Process sector data
    let sectorData = { primary: '', secondary: '', tertiary: '' };
    if (indicator?.sector) {
      if (typeof indicator.sector === 'object' && indicator.sector !== null) {
        sectorData = {
          primary: indicator.sector.primary || '',
          secondary: indicator.sector.secondary || '',
          tertiary: indicator.sector.tertiary || ''
        };
      } else {
        sectorData = { primary: String(indicator.sector), secondary: '', tertiary: '' };
      }
    }

    // Process subsector data
    let subsectorData = { primary: '', secondary: '', tertiary: '' };
    if (indicator?.sub_sector) {
      if (typeof indicator.sub_sector === 'object' && indicator.sub_sector !== null) {
        subsectorData = {
          primary: indicator.sub_sector.primary || '',
          secondary: indicator.sub_sector.secondary || '',
          tertiary: indicator.sub_sector.tertiary || ''
        };
      } else {
        subsectorData = { primary: String(indicator.sub_sector), secondary: '', tertiary: '' };
      }
    }

    setSuggestForm({
      name: '',
      email: '',
      suggestion_type: 'correction',
      // Indicator fields - prefilled with current data
      indicator_name: String(indicator?.localized_name || indicator?.name || ''),
      definition: String(indicator?.localized_definition || indicator?.definition || ''),
      type: String(indicator?.type || ''),
      unit: String(indicator?.unit || ''),
      sector: sectorData,
      sub_sector: subsectorData,
      emergency: indicator?.emergency || false,
      related_programs: Array.isArray(indicator?.related_programs)
        ? indicator.related_programs.map(p =>
            typeof p === 'string' ? p :
            typeof p === 'object' && p !== null ?
              String(p.primary || p.name || t('fallbacks.unknownProgram')) :
              String(p || t('fallbacks.unknownProgram'))
          ).join(', ')
        : '',
      // Additional fields
      reason: '',
      additional_notes: ''
    });
    setSubmitSuccess(false);
  };

  const closeSuggestModal = () => {
    setShowSuggestModal(false);
    setSubmitting(false);
  };

  const handleSuggestFormChange = (e) => {
    const { name, value, type, checked } = e.target;
    const newValue = type === 'checkbox' ? checked : value;

    // Handle nested sector and subsector fields
    if (name.startsWith('sector.') || name.startsWith('sub_sector.')) {
      const [field, level] = name.split('.');
      setSuggestForm(prev => ({
        ...prev,
        [field]: {
          ...prev[field],
          [level]: newValue
        }
      }));
      return;
    }

    setSuggestForm(prev => ({
      ...prev,
      [name]: newValue
    }));

    // If suggestion type changes to "new indicator", clear all indicator fields
    if (name === 'suggestion_type' && value === 'new_indicator') {
      setSuggestForm(prev => ({
        ...prev,
        indicator_name: '',
        definition: '',
        type: '',
        unit: '',
        sector: { primary: '', secondary: '', tertiary: '' },
        sub_sector: { primary: '', secondary: '', tertiary: '' },
        emergency: false,
        related_programs: ''
      }));
    }

    // If suggestion type changes back to other types, refill with current data
    if (name === 'suggestion_type' && value !== 'new_indicator') {
      // Process sector data
      let sectorData = { primary: '', secondary: '', tertiary: '' };
      if (indicator?.sector) {
        if (typeof indicator.sector === 'object' && indicator.sector !== null) {
          sectorData = {
            primary: indicator.sector.primary || '',
            secondary: indicator.sector.secondary || '',
            tertiary: indicator.sector.tertiary || ''
          };
        } else {
          sectorData = { primary: String(indicator.sector), secondary: '', tertiary: '' };
        }
      }

      // Process subsector data
      let subsectorData = { primary: '', secondary: '', tertiary: '' };
      if (indicator?.sub_sector) {
        if (typeof indicator.sub_sector === 'object' && indicator.sub_sector !== null) {
          subsectorData = {
            primary: indicator.sub_sector.primary || '',
            secondary: indicator.sub_sector.secondary || '',
            tertiary: indicator.sub_sector.tertiary || ''
          };
        } else {
          subsectorData = { primary: String(indicator.sub_sector), secondary: '', tertiary: '' };
        }
      }

      setSuggestForm(prev => ({
        ...prev,
        indicator_name: String(indicator?.localized_name || indicator?.name || ''),
        definition: String(indicator?.localized_definition || indicator?.definition || ''),
        type: String(indicator?.type || ''),
        unit: String(indicator?.unit || ''),
        sector: sectorData,
        sub_sector: subsectorData,
        emergency: indicator?.emergency || false,
        related_programs: Array.isArray(indicator?.related_programs)
          ? indicator.related_programs.map(p =>
              typeof p === 'string' ? p :
              typeof p === 'object' && p !== null ?
                String(p.primary || p.name || 'Unknown Program') :
                String(p || 'Unknown Program')
            ).join(', ')
          : ''
      }));
    }
  };

  // Helper function to validate sector input
  const validateSectorSelection = () => {
    const { sector } = suggestForm;
    // Only primary sector is mandatory
    return sector.primary?.trim();
  };

  // Helper function to validate subsector input
  const validateSubsectorSelection = () => {
    const { sub_sector } = suggestForm;
    // Only primary subsector is mandatory
    return sub_sector.primary?.trim();
  };

  // Helper function to clear sector and subsector selections
  const clearSectorSelections = () => {
    setSuggestForm(prev => ({
      ...prev,
      sector: { primary: '', secondary: '', tertiary: '' },
      sub_sector: { primary: '', secondary: '', tertiary: '' }
    }));
  };

  // Helper function to clear all form fields
  const clearAllFormFields = () => {
    setSuggestForm({
      name: '',
      email: '',
      suggestion_type: 'correction',
      indicator_name: '',
      definition: '',
      type: '',
      unit: '',
      sector: { primary: '', secondary: '', tertiary: '' },
      sub_sector: { primary: '', secondary: '', tertiary: '' },
      emergency: false,
      related_programs: '',
      reason: '',
      additional_notes: ''
    });
  };

  const handleSuggestSubmit = async (e) => {
    e.preventDefault();

    // Validate sector and subsector selections
    if (!validateSectorSelection()) {
      alert(t('alerts.selectSectorLevel'));
      return;
    }

    if (!validateSubsectorSelection()) {
      alert(t('alerts.selectSubsectorLevel'));
      return;
    }

    setSubmitting(true);

    try {
      // Prepare the data for submission
      const submissionData = {
        submitter_name: suggestForm.name,
        submitter_email: suggestForm.email,
        suggestion_type: suggestForm.suggestion_type,
        indicator_id: suggestForm.suggestion_type === 'new_indicator' ? null : indicator.id,
        indicator_name: suggestForm.indicator_name,
        definition: suggestForm.definition,
        type: suggestForm.type,
        unit: suggestForm.unit,
        sector: suggestForm.sector,
        sub_sector: suggestForm.sub_sector,
        emergency: suggestForm.emergency,
        related_programs: suggestForm.related_programs,
        reason: suggestForm.reason,
        additional_notes: suggestForm.additional_notes
      };

      // Submit to backend API
      const response = await fetch(`${API_BASE_URL}/api/v1/indicator-suggestions?api_key=${API_KEY}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(submissionData)
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || t('alerts.failedToSubmit', { type: 'suggestion', message: '' }));
      }

      const result = await response.json();
      console.log('Suggestion submitted successfully:', result);

      setSubmitSuccess(true);

    } catch (error) {
      console.error('Error submitting suggestion:', error);
      alert(`Failed to submit suggestion: ${error.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  // Process indicator names with common word highlights
  const processIndicatorNameWithHighlights = (indicatorName) => {
    if (!indicatorName || !commonWords.length) {
      return indicatorName;
    }

    const processedName = processIndicatorName(indicatorName, commonWords, router.locale);
    return <span dangerouslySetInnerHTML={{ __html: processedName }} />;
  };

  if (error) {
    return (
      <div className="container mx-auto px-4 py-8 text-center">
        <Head>
          <title>{`Indicator Error - Humanitarian Databank`}</title>
        </Head>
        <h1 className="text-3xl font-bold text-humdb-red mb-6">Indicator Details</h1>
        <p className="text-red-600 bg-red-100 p-4 rounded-md">{error}</p>
        <Link href="/indicator-bank" className="mt-4 inline-block text-humdb-red hover:underline">
          &larr; Back to Indicator Bank
        </Link>
      </div>
    );
  }

  if (loading || !indicator) {
    return (
      <div className="w-full px-6 sm:px-8 lg:px-12 py-8">
        <Head>
          <title>{`${t('indicatorDetail.loading.title')} - Humanitarian Databank`}</title>
        </Head>
        <div className="text-center py-20">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-humdb-red mb-4"></div>
          <h1 className="text-3xl font-bold text-humdb-navy mb-2">
            <TranslationSafe fallback="Loading Indicator">
              {t('indicatorDetail.loading.title')}
            </TranslationSafe>
          </h1>
          <p className="text-humdb-gray-600">
            <TranslationSafe fallback="Please wait while we fetch the indicator details...">
              {t('indicatorDetail.loading.message')}
            </TranslationSafe>
          </p>
        </div>
      </div>
    );
  }

  // Prevent rendering until translations are loaded to avoid hydration mismatches
  if (!isLoaded || loading || !indicator) {
    return (
      <div className="w-full px-6 sm:px-8 lg:px-12 py-8">
        <Head>
          <title>{`${t('indicatorDetail.loading.title')} - Humanitarian Databank`}</title>
        </Head>
        <div className="text-center py-20">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-humdb-red mb-4"></div>
          <h1 className="text-3xl font-bold text-humdb-navy mb-2">
            <TranslationSafe fallback="Loading Indicator">
              {t('indicatorDetail.loading.title')}
            </TranslationSafe>
          </h1>
          <p className="text-humdb-gray-600">
            <TranslationSafe fallback="Please wait while we fetch the indicator details...">
              {t('indicatorDetail.loading.message')}
            </TranslationSafe>
          </p>
        </div>
      </div>
    );
  }

  return (
    <>
              <Head>
          <title>{`${String(indicator.localized_name || indicator.name || 'Indicator')} - Humanitarian Databank`}</title>
          <meta name="description" content={`Details for ${indicator.localized_name || indicator.name} from the indicator bank.`} />
        </Head>

      <div className={`bg-humdb-gray-100 min-h-screen ${isRTL ? 'rtl font-tajawal' : ''}`}>
        <div className={`w-full max-w-none px-6 py-10 ${isRTL ? 'rtl' : ''}`}>

          {/* Breadcrumb Navigation */}
          <nav className={`mb-8 ${isRTL ? 'rtl' : ''}`} aria-label="Breadcrumb">
            <ol className={`flex items-center text-sm text-humdb-gray-600 ${isRTL ? 'flex-row-reverse space-x-reverse' : 'space-x-2'}`}>
              <li>
                <Link href="/" className="hover:text-humdb-red">
                  {t('common.home')}
                </Link>
              </li>
              <li>
                <span className={isRTL ? 'mx-2' : 'mx-2'}>/</span>
              </li>
              <li>
                <Link href="/indicator-bank" className="hover:text-humdb-red">
                  {t('navigation.indicatorBank')}
                </Link>
              </li>
              <li>
                <span className={isRTL ? 'mx-2' : 'mx-2'}>/</span>
              </li>
              <li className="text-humdb-gray-800 font-medium">
                {String(indicator.localized_name || indicator.name || t('indicatorDetail.title'))}
              </li>
            </ol>
          </nav>

          {/* Main Layout with Sidebar */}
          <div className={`flex gap-6 ${isRTL ? 'flex-row-reverse' : ''}`}>

            {/* Sidebar - Indicator Navigation */}
            <div className="w-96 flex-shrink-0">
              <div className="bg-white rounded-lg shadow-sm border border-humdb-gray-200 overflow-hidden sticky top-24 md:top-[144px] xl:top-24 h-screen">

                {/* Header */}
                <div className="px-4 py-3 border-b border-humdb-gray-200 bg-humdb-gray-50">
                  <h3 className={`text-lg font-semibold text-humdb-navy ${isRTL ? 'text-right' : 'text-left'}`}>{t('indicatorDetail.sidebar.title')}</h3>
                  <p className={`text-sm text-humdb-gray-600 ${isRTL ? 'text-right' : 'text-left'}`}>
                    {searchTerm ? `${filteredIndicators.length} ${t('indicatorDetail.sidebar.of')} ${allIndicators.length}` : `${allIndicators.length}`} {allIndicators.length === 1 ? t('indicatorBank.indicator') : t('indicatorBank.indicators')}
                  </p>
                </div>

                {/* Search Bar */}
                <div className="px-4 py-3 border-b border-humdb-gray-200">
                  <div className="relative">
                    <input
                      type="text"
                      placeholder={t('indicatorDetail.sidebar.searchPlaceholder')}
                      value={searchTerm}
                      onChange={(e) => setSearchTerm(e.target.value)}
                      className={`w-full px-3 py-2 ${isRTL ? 'pr-10' : 'pl-10'} text-sm border border-humdb-gray-300 rounded-md focus:ring-2 focus:ring-humdb-red focus:border-humdb-red ${isRTL ? 'text-right' : 'text-left'}`}
                    />
                    <svg
                      className={`absolute ${isRTL ? 'right-3' : 'left-3'} top-2.5 h-4 w-4 text-humdb-gray-400`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                    </svg>
                  </div>
                </div>

                {/* Indicator Tree */}
                <div className={`flex-1 overflow-y-auto ${isRTL ? 'rtl' : ''}`} style={{ height: 'calc(100vh - 200px)' }} data-sidebar-scroll>
                  {sortedSectors.map((sector) => (
                    <div key={sector} className="border-b border-humdb-gray-100 last:border-b-0">

                      {/* Sector Header - Collapsible */}
                      <button
                        onClick={() => toggleSector(sector)}
                        className={`w-full px-4 py-3 bg-humdb-navy text-white hover:bg-humdb-navy/90 transition-colors duration-150 flex items-center justify-between border-b border-humdb-navy/10 ${isRTL ? 'flex-row-reverse' : ''}`}
                      >
                        <h4 className={`text-sm font-bold uppercase tracking-wider ${isRTL ? 'text-right' : 'text-left'}`}>
                          {sector}
                        </h4>
                        <svg
                          className={`h-5 w-5 text-white transition-transform duration-200 ${
                            expandedSectors[sector] ? 'rotate-90' : ''
                          }`}
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                        </svg>
                      </button>

                      {/* Subsectors within this sector - Collapsible */}
                      {expandedSectors[sector] && Object.keys(filteredGroupedIndicators[sector])
                        .sort((a, b) => a.localeCompare(b))
                        .map((subSector) => {
                          const subSectorKey = `${sector}-${subSector}`;
                          const hasMultipleSubSectors = Object.keys(filteredGroupedIndicators[sector]).length > 1;

                          return (
                            <div key={subSector}>

                              {/* Subsector Header - Always collapsible */}
                              <button
                                onClick={() => toggleSubSector(sector, subSector)}
                                className={`w-full px-6 py-2.5 bg-slate-100 hover:bg-slate-200 transition-colors duration-150 flex items-center justify-between ${isRTL ? 'border-r-4 border-slate-300 flex-row-reverse' : 'border-l-4 border-slate-300'}`}
                              >
                                <h5 className={`text-sm font-semibold text-slate-700 ${isRTL ? 'text-right' : 'text-left'}`}>
                                  {subSector}
                                </h5>
                                <svg
                                  className={`h-4 w-4 text-slate-600 transition-transform duration-200 ${
                                    expandedSubSectors[subSectorKey] ? 'rotate-90' : ''
                                  }`}
                                  fill="none"
                                  stroke="currentColor"
                                  viewBox="0 0 24 24"
                                >
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                                </svg>
                              </button>

                              {/* Indicators in this subsector */}
                              {expandedSubSectors[subSectorKey] &&
                                filteredGroupedIndicators[sector][subSector].map((ind) => (
                                  <Link key={ind.id} href={`/indicator-bank/${ind.id}`}>
                                    <div
                                      data-indicator-id={ind.id}
                                      className={`px-8 py-3 hover:bg-blue-50 transition-colors duration-150 cursor-pointer ${isRTL ? 'border-r border-humdb-gray-200' : 'border-l border-humdb-gray-200'} ${
                                        ind.id === currentId ? `bg-blue-100 ${isRTL ? 'border-r-4 border-r-blue-500' : 'border-l-4 border-l-blue-500'} shadow-sm` : ''
                                      }`}
                                    >
                                      <p className={`text-sm leading-relaxed ${isRTL ? 'text-right' : 'text-left'} ${
                                        ind.id === currentId ? 'text-blue-700 font-medium' : 'text-humdb-gray-800'
                                      }`} style={{ wordWrap: 'break-word', whiteSpace: 'normal' }}>
                                        {commonWords.length > 0 ? (
                                          <span dangerouslySetInnerHTML={{
                                            __html: processIndicatorName(
                                              String(ind.localized_name || ind.name || 'Unnamed Indicator'),
                                              commonWords,
                                              router.locale
                                            )
                                          }} />
                                        ) : (
                                          String(ind.localized_name || ind.name || 'Unnamed Indicator')
                                        )}
                                      </p>
                                    </div>
                                  </Link>
                                ))
                              }
                            </div>
                          );
                        })}
                    </div>
                  ))}

                  {/* No results message */}
                  {searchTerm && filteredIndicators.length === 0 && (
                    <div className="px-4 py-8 text-center">
                      <p className="text-sm text-humdb-gray-500">{t('indicatorDetail.sidebar.noResults', { searchTerm })}</p>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Main Content */}
            <div className="flex-1">
              <div className={`bg-white rounded-lg shadow-sm border border-humdb-gray-200 overflow-hidden ${isRTL ? 'rtl' : ''}`}>

            {/* Header */}
            <div className="px-8 py-6 border-b border-humdb-gray-200">
              <div className={`flex justify-between items-start ${isRTL ? 'flex-row-reverse' : ''}`}>
                <div className="flex-1">
                  <h1 className={`text-3xl font-bold text-humdb-navy mb-2 ${isRTL ? 'text-right' : 'text-left'}`}>
                    {commonWords.length > 0 ? (
                      processIndicatorNameWithHighlights(String(indicator.localized_name || indicator.name || ''))
                    ) : (
                      String(indicator.localized_name || indicator.name || '')
                    )}
                  </h1>
                  {indicator.id && (
                    <p className={`text-humdb-gray-500 text-sm ${isRTL ? 'text-right' : 'text-left'}`}>
                      {t('indicatorDetail.header.id')}: {indicator.id}
                    </p>
                  )}
                </div>
                <div className={`flex items-center gap-3 ${isRTL ? 'flex-row-reverse' : ''}`}>
                  <button
                    onClick={openSuggestModal}
                    className="bg-humdb-red hover:bg-humdb-red-dark text-white font-medium px-4 py-2 rounded-md transition-colors duration-150 flex items-center gap-2"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                    </svg>
                    {t('indicatorDetail.header.suggestUpdates')}
                  </button>
                  {indicator.archived && (
                    <span className="bg-yellow-100 text-yellow-800 text-sm font-medium px-3 py-1 rounded-full">
                      {t('indicatorDetail.header.archived')}
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Content */}
            <div className={`px-8 py-6 ${isRTL ? 'rtl' : ''}`}>

              {/* Definition */}
              {(indicator.localized_definition || indicator.definition) && (
                <div className="mb-8">
                  <h2 className={`text-xl font-semibold text-humdb-navy mb-3 ${isRTL ? 'text-right' : 'text-left'}`}>{t('indicatorDetail.content.definition')}</h2>
                  <p className={`text-humdb-gray-700 leading-relaxed ${isRTL ? 'text-right' : 'text-left'}`}>
                    {String(indicator.localized_definition || indicator.definition)}
                  </p>
                </div>
              )}

              {/* Key Properties Grid */}
              <div className="mb-8">
                <h2 className={`text-xl font-semibold text-humdb-navy mb-4 ${isRTL ? 'text-right' : 'text-left'}`}>{t('indicatorDetail.content.keyProperties')}</h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">

                  {indicator.localized_type || indicator.type ? (
                    <div className="bg-humdb-gray-50 p-4 rounded-lg">
                      <h3 className={`font-medium text-humdb-gray-700 mb-2 ${isRTL ? 'text-right' : 'text-left'}`}>{t('indicatorDetail.content.type')}</h3>
                      <p className={`text-humdb-gray-900 ${isRTL ? 'text-right' : 'text-left'}`}>{String(indicator.localized_type || indicator.type)}</p>
                    </div>
                  ) : null}

                  {indicator.localized_unit || indicator.unit ? (
                    <div className="bg-humdb-gray-50 p-4 rounded-lg">
                      <h3 className={`font-medium text-humdb-gray-700 mb-2 ${isRTL ? 'text-right' : 'text-left'}`}>{t('indicatorDetail.content.unit')}</h3>
                      <p className={`text-humdb-gray-900 ${isRTL ? 'text-right' : 'text-left'}`}>{String(indicator.localized_unit || indicator.unit)}</p>
                    </div>
                  ) : null}

                  {indicator.sector && (
                    <div className="bg-humdb-gray-50 p-4 rounded-lg">
                      <h3 className={`font-medium text-humdb-gray-700 mb-2 ${isRTL ? 'text-right' : 'text-left'}`}>{t('indicatorDetail.content.sector')}</h3>
                      <p className={`text-humdb-gray-900 ${isRTL ? 'text-right' : 'text-left'}`}>
                        {typeof indicator.sector === 'object' && indicator.sector !== null
                          ? String(indicator.sector.localized_name || indicator.sector.primary || indicator.sector.name || indicator.sector)
                          : String(indicator.sector)}
                      </p>
                    </div>
                  )}

                  {indicator.sub_sector && (
                    <div className="bg-humdb-gray-50 p-4 rounded-lg">
                      <h3 className={`font-medium text-humdb-gray-700 mb-2 ${isRTL ? 'text-right' : 'text-left'}`}>{t('indicatorDetail.content.subSector')}</h3>
                      <p className={`text-humdb-gray-900 ${isRTL ? 'text-right' : 'text-left'}`}>
                        {typeof indicator.sub_sector === 'object' && indicator.sub_sector !== null
                          ? String(indicator.sub_sector.localized_name || indicator.sub_sector.primary || indicator.sub_sector.name || indicator.sub_sector)
                          : String(indicator.sub_sector)}
                      </p>
                    </div>
                  )}

                  {indicator.emergency !== null && indicator.emergency !== undefined && (
                    <div className="bg-humdb-gray-50 p-4 rounded-lg">
                      <h3 className={`font-medium text-humdb-gray-700 mb-2 ${isRTL ? 'text-right' : 'text-left'}`}>{t('indicatorDetail.content.emergencyContext')}</h3>
                      <p className={`text-humdb-gray-900 ${isRTL ? 'text-right' : 'text-left'}`}>
                        {typeof indicator.emergency === 'boolean' ?
                          (indicator.emergency ? t('common.yes') : t('common.no')) :
                          String(indicator.emergency)
                        }
                      </p>
                    </div>
                  )}

                  <div className="bg-humdb-gray-50 p-4 rounded-lg">
                    <h3 className={`font-medium text-humdb-gray-700 mb-2 ${isRTL ? 'text-right' : 'text-left'}`}>{t('indicatorDetail.content.status')}</h3>
                    <p className={`text-humdb-gray-900 ${isRTL ? 'text-right' : 'text-left'}`}>
                      {indicator.archived ? t('indicatorDetail.content.archived') : t('indicatorDetail.content.active')}
                    </p>
                  </div>

                </div>
              </div>

              {/* Related Programs */}
              {indicator.related_programs && Array.isArray(indicator.related_programs) && indicator.related_programs.length > 0 && (
                <div className="mb-8">
                  <h2 className={`text-xl font-semibold text-humdb-navy mb-4 ${isRTL ? 'text-right' : 'text-left'}`}>{t('indicatorDetail.content.relatedPrograms')}</h2>
                  <div className={`flex flex-wrap gap-3 ${isRTL ? 'flex-row-reverse' : ''}`}>
                    {indicator.related_programs.map((program, index) => (
                      <span key={index} className={`bg-humdb-red-light text-humdb-red px-4 py-2 rounded-full text-sm font-medium ${isRTL ? 'text-right' : 'text-left'}`}>
                        {typeof program === 'string' ? program :
                         typeof program === 'object' && program !== null ?
                           String(program.primary || program.name || t('indicatorDetail.content.unknownProgram')) :
                           String(program || t('indicatorDetail.content.unknownProgram'))}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Metadata */}
              <div className="border-t border-humdb-gray-200 pt-6">
                <h2 className={`text-xl font-semibold text-humdb-navy mb-4 ${isRTL ? 'text-right' : 'text-left'}`}>{t('indicatorDetail.content.metadata')}</h2>
                <div className={`grid grid-cols-1 md:grid-cols-2 gap-6 text-sm ${isRTL ? 'rtl' : ''}`}>

                  {indicator.created_at && (
                    <div className={isRTL ? 'text-right' : 'text-left'}>
                      <span className="font-medium text-humdb-gray-700">{t('indicatorDetail.content.created')}:</span>
                      <p className="text-humdb-gray-600 mt-1">
                        {new Date(indicator.created_at).toLocaleDateString(router.locale || 'en-US', {
                          year: 'numeric',
                          month: 'long',
                          day: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit'
                        })}
                      </p>
                    </div>
                  )}

                  {indicator.updated_at && (
                    <div className={isRTL ? 'text-right' : 'text-left'}>
                      <span className="font-medium text-humdb-gray-700">{t('indicatorDetail.content.lastUpdated')}:</span>
                      <p className="text-humdb-gray-600 mt-1">
                        {new Date(indicator.updated_at).toLocaleDateString(router.locale || 'en-US', {
                          year: 'numeric',
                          month: 'long',
                          day: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit'
                        })}
                      </p>
                    </div>
                  )}

                </div>
              </div>

            </div>

            {/* Footer Actions */}
            <div className={`px-8 py-4 bg-humdb-gray-50 border-t border-humdb-gray-200 ${isRTL ? 'rtl' : ''}`}>
              <div className={`flex ${isRTL ? 'flex-row-reverse' : ''} justify-between items-center`}>
                <Link
                  href="/indicator-bank"
                  className="inline-flex items-center text-humdb-red hover:text-humdb-red-dark transition-colors duration-150"
                >
                  <svg className={`w-4 h-4 ${isRTL ? 'ml-2' : 'mr-2'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                  </svg>
                  {t('indicatorDetail.footer.backToBank')}
                </Link>

                <button
                  onClick={() => router.back()}
                  className="bg-humdb-gray-300 hover:bg-humdb-gray-400 text-humdb-gray-700 font-medium px-4 py-2 rounded-md transition-colors duration-150"
                >
                  {t('indicatorDetail.footer.goBack')}
                </button>
              </div>
              </div>
            </div>

          </div>
        </div>
        </div>
      </div>

      {/* Suggest Updates Modal */}
      {showSuggestModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-[99999] p-4">
          <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-humdb-gray-200">
              <div className="flex justify-between items-center">
                <h2 className="text-xl font-semibold text-humdb-navy">Suggest Updates</h2>
                <button
                  onClick={closeSuggestModal}
                  className="text-humdb-gray-400 hover:text-humdb-gray-600 transition-colors duration-150"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              <p className="text-humdb-gray-600 mt-1">
                Help us improve this indicator by suggesting corrections or improvements.
              </p>
            </div>

            {/* Modal Content */}
            <div className="px-6 py-4">
              {submitSuccess ? (
                <div className="text-center py-8">
                  <div className="text-green-500 mb-4">
                    <svg className="w-16 h-16 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                  <h3 className="text-lg font-semibold text-humdb-navy mb-2">Thank You!</h3>
                  <p className="text-humdb-gray-600 mb-6">
                    Your suggestion has been submitted successfully. We'll review it and get back to you if needed.
                  </p>
                  <div className="bg-blue-50 border border-blue-200 rounded-md p-4 mb-6">
                    <div className="flex items-start">
                      <svg className="w-5 h-5 text-blue-500 mt-0.5 mr-3 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 4.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                      </svg>
                      <div>
                        <p className="text-blue-800 font-medium">Confirmation Email Sent</p>
                        <p className="text-blue-700 text-sm mt-1">
                          A confirmation email has been sent to <strong>{suggestForm.email}</strong>.
                          Please check your inbox (and spam folder) for details about your submission.
                        </p>
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={closeSuggestModal}
                    className="bg-humdb-red hover:bg-humdb-red-dark text-white font-medium px-6 py-2 rounded-md transition-colors duration-150"
                  >
                    Close
                  </button>
                </div>
              ) : (
                <form onSubmit={handleSuggestSubmit} className="space-y-6">
                  {/* Contact Information */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label htmlFor="name" className="block text-sm font-medium text-humdb-gray-700 mb-1">
                        Your Name *
                      </label>
                      <input
                        type="text"
                        id="name"
                        name="name"
                        value={suggestForm.name}
                        onChange={handleSuggestFormChange}
                        required
                        className="w-full px-3 py-2 border border-humdb-gray-300 rounded-md focus:ring-2 focus:ring-humdb-red focus:border-humdb-red"
                      />
                    </div>
                    <div>
                      <label htmlFor="email" className="block text-sm font-medium text-humdb-gray-700 mb-1">
                        Email Address *
                      </label>
                      <input
                        type="email"
                        id="email"
                        name="email"
                        value={suggestForm.email}
                        onChange={handleSuggestFormChange}
                        required
                        className="w-full px-3 py-2 border border-humdb-gray-300 rounded-md focus:ring-2 focus:ring-humdb-red focus:border-humdb-red"
                      />
                    </div>
                  </div>

                  {/* Suggestion Type */}
                  <div>
                    <label htmlFor="suggestion_type" className="block text-sm font-medium text-humdb-gray-700 mb-1">
                      Type of Suggestion *
                    </label>
                    <select
                      id="suggestion_type"
                      name="suggestion_type"
                      value={suggestForm.suggestion_type}
                      onChange={handleSuggestFormChange}
                      required
                      className="w-full px-3 py-2 border border-humdb-gray-300 rounded-md focus:ring-2 focus:ring-humdb-red focus:border-humdb-red"
                    >
                      <option value="correction">{t('indicatorDetail.suggestModal.suggestionTypes.correction')}</option>
                      <option value="improvement">{t('indicatorDetail.suggestModal.suggestionTypes.improvement')}</option>
                      <option value="new_indicator">{t('indicatorDetail.suggestModal.suggestionTypes.newIndicator')}</option>
                      <option value="other">{t('indicatorDetail.suggestModal.suggestionTypes.other')}</option>
                    </select>
                  </div>

                  {/* Indicator Fields */}
                  <div className="border-t border-humdb-gray-200 pt-6">
                    <h3 className="text-lg font-semibold text-humdb-navy mb-4">Indicator Information</h3>

                    {/* Indicator Name */}
                    <div className="mb-4">
                      <label htmlFor="indicator_name" className="block text-sm font-medium text-humdb-gray-700 mb-1">
                        Indicator Name *
                      </label>
                      <input
                        type="text"
                        id="indicator_name"
                        name="indicator_name"
                        value={suggestForm.indicator_name}
                        onChange={handleSuggestFormChange}
                        required
                        className="w-full px-3 py-2 border border-humdb-gray-300 rounded-md focus:ring-2 focus:ring-humdb-red focus:border-humdb-red"
                      />
                    </div>

                    {/* Definition */}
                    <div className="mb-4">
                      <label htmlFor="definition" className="block text-sm font-medium text-humdb-gray-700 mb-1">
                        Definition *
                      </label>
                      <textarea
                        id="definition"
                        name="definition"
                        value={suggestForm.definition}
                        onChange={handleSuggestFormChange}
                        required
                        rows={4}
                        className="w-full px-3 py-2 border border-humdb-gray-300 rounded-md focus:ring-2 focus:ring-humdb-red focus:border-humdb-red"
                      />
                    </div>

                    {/* Type and Unit */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                      <div>
                        <label htmlFor="type" className="block text-sm font-medium text-humdb-gray-700 mb-1">
                          Type
                        </label>
                        <input
                          type="text"
                          id="type"
                          name="type"
                          value={suggestForm.type}
                          onChange={handleSuggestFormChange}
                          className="w-full px-3 py-2 border border-humdb-gray-300 rounded-md focus:ring-2 focus:ring-humdb-red focus:border-humdb-red"
                        />
                      </div>
                      <div>
                        <label htmlFor="unit" className="block text-sm font-medium text-humdb-gray-700 mb-1">
                          Unit of Measurement
                        </label>
                        <input
                          type="text"
                          id="unit"
                          name="unit"
                          value={suggestForm.unit}
                          onChange={handleSuggestFormChange}
                          className="w-full px-3 py-2 border border-humdb-gray-300 rounded-md focus:ring-2 focus:ring-humdb-red focus:border-humdb-red"
                        />
                      </div>
                    </div>

                    {/* Sector and Sub-sector */}
                    <div className="mb-4">
                      <h4 className="text-md text-humdb-navy mb-3">Sector</h4>

                      {/* Sector */}
                      <div className="mb-6">
                        <label className="block text-sm font-medium text-humdb-gray-700 mb-3">
                          Sector
                        </label>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                          <div>
                            <label className="block text-xs font-medium text-humdb-gray-600 mb-2">
                              Primary Sector *
                            </label>
                            <input
                              type="text"
                              name="sector.primary"
                              value={suggestForm.sector.primary}
                              onChange={handleSuggestFormChange}
                              placeholder={t('forms.placeholders.sectorPrimary')}
                              className="w-full px-3 py-2 border border-humdb-gray-300 rounded-md focus:ring-2 focus:ring-humdb-red focus:border-humdb-red text-sm"
                            />
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-humdb-gray-600 mb-2">
                              Secondary Sector
                            </label>
                            <input
                              type="text"
                              name="sector.secondary"
                              value={suggestForm.sector.secondary}
                              onChange={handleSuggestFormChange}
                              placeholder={t('forms.placeholders.sectorSecondary')}
                              className="w-full px-3 py-2 border border-humdb-gray-300 rounded-md focus:ring-2 focus:ring-humdb-red focus:border-humdb-red text-sm"
                            />
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-humdb-gray-600 mb-2">
                              Tertiary Sector
                            </label>
                            <input
                              type="text"
                              name="sector.tertiary"
                              value={suggestForm.sector.tertiary}
                              onChange={handleSuggestFormChange}
                              placeholder={t('forms.placeholders.sectorTertiary')}
                              className="w-full px-3 py-2 border border-humdb-gray-300 rounded-md focus:ring-2 focus:ring-humdb-red focus:border-humdb-red text-sm"
                            />
                          </div>
                        </div>
                        {!validateSectorSelection() && (
                          <p className="text-xs text-red-600 mt-2">
                            {t('forms.validation.primarySectorRequired')}
                          </p>
                        )}
                      </div>

                      {/* Sub-sector */}
                      <div className="mb-4">
                        <label className="block text-sm font-medium text-humdb-gray-700 mb-3">
                          Sub-Sector
                        </label>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                          <div>
                            <label className="block text-xs font-medium text-humdb-gray-600 mb-2">
                              Primary Sub-Sector *
                            </label>
                            <input
                              type="text"
                              name="sub_sector.primary"
                              value={suggestForm.sub_sector.primary}
                              onChange={handleSuggestFormChange}
                              placeholder={t('forms.placeholders.subsectorPrimary')}
                              className="w-full px-3 py-2 border border-humdb-gray-300 rounded-md focus:ring-2 focus:ring-humdb-red focus:border-humdb-red text-sm"
                            />
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-humdb-gray-600 mb-2">
                              Secondary Sub-Sector
                            </label>
                            <input
                              type="text"
                              name="sub_sector.secondary"
                              value={suggestForm.sub_sector.secondary}
                              onChange={handleSuggestFormChange}
                              placeholder={t('forms.placeholders.subsectorSecondary')}
                              className="w-full px-3 py-2 border border-humdb-gray-300 rounded-md focus:ring-2 focus:ring-humdb-red focus:border-humdb-red text-sm"
                            />
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-humdb-gray-600 mb-2">
                              Tertiary Sub-Sector
                            </label>
                            <input
                              type="text"
                              name="sub_sector.tertiary"
                              value={suggestForm.sub_sector.tertiary}
                              onChange={handleSuggestFormChange}
                              placeholder={t('forms.placeholders.subsectorTertiary')}
                              className="w-full px-3 py-2 border border-humdb-gray-300 rounded-md focus:ring-2 focus:ring-humdb-red focus:border-humdb-red text-sm"
                            />
                          </div>
                        </div>
                        {!validateSubsectorSelection() && (
                          <p className="text-xs text-red-600 mt-2">
                            {t('forms.validation.primarySubsectorRequired')}
                          </p>
                        )}
                      </div>

                    </div>

                    {/* Emergency Context */}
                    <div className="mb-4">
                      <label className="flex items-center">
                        <input
                          type="checkbox"
                          name="emergency"
                          checked={suggestForm.emergency}
                          onChange={handleSuggestFormChange}
                          className="h-4 w-4 text-humdb-red focus:ring-humdb-red border-humdb-gray-300 rounded"
                        />
                        <span className="ml-2 text-sm font-medium text-humdb-gray-700">
                          Emergency Context
                        </span>
                      </label>
                    </div>

                    {/* Related Programs */}
                    <div className="mb-4">
                      <label htmlFor="related_programs" className="block text-sm font-medium text-humdb-gray-700 mb-1">
                        Related Programs
                      </label>
                      <input
                        type="text"
                        id="related_programs"
                        name="related_programs"
                        value={suggestForm.related_programs}
                        onChange={handleSuggestFormChange}
                        placeholder={t('forms.placeholders.programs')}
                        className="w-full px-3 py-2 border border-humdb-gray-300 rounded-md focus:ring-2 focus:ring-humdb-red focus:border-humdb-red"
                      />
                    </div>
                  </div>

                  {/* Reason and Additional Notes */}
                  <div className="border-t border-humdb-gray-200 pt-6">
                    <div className="mb-4">
                      <label htmlFor="reason" className="block text-sm font-medium text-humdb-gray-700 mb-1">
                        Reason for Change *
                      </label>
                      <textarea
                        id="reason"
                        name="reason"
                        value={suggestForm.reason}
                        onChange={handleSuggestFormChange}
                        required
                        rows={3}
                        placeholder={t('forms.placeholders.reasonForChange')}
                        className="w-full px-3 py-2 border border-humdb-gray-300 rounded-md focus:ring-2 focus:ring-humdb-red focus:border-humdb-red"
                      />
                    </div>

                    <div className="mb-4">
                      <label htmlFor="additional_notes" className="block text-sm font-medium text-humdb-gray-700 mb-1">
                        Additional Notes
                      </label>
                      <textarea
                        id="additional_notes"
                        name="additional_notes"
                        value={suggestForm.additional_notes}
                        onChange={handleSuggestFormChange}
                        rows={3}
                        placeholder={t('forms.placeholders.additionalNotes')}
                        className="w-full px-3 py-2 border border-humdb-gray-300 rounded-md focus:ring-2 focus:ring-humdb-red focus:border-humdb-red"
                      />
                    </div>
                  </div>

                  {/* Form Actions */}
                  <div className="flex justify-between items-center pt-4 border-t border-humdb-gray-200">
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={clearAllFormFields}
                        className="px-3 py-2 text-humdb-gray-600 bg-humdb-gray-100 hover:bg-humdb-gray-200 rounded-md transition-colors duration-150 text-sm"
                      >
                        Clear All
                      </button>
                    </div>
                    <div className="flex gap-3">
                      <button
                        type="button"
                        onClick={closeSuggestModal}
                        className="px-4 py-2 text-humdb-gray-700 bg-humdb-gray-200 hover:bg-humdb-gray-300 rounded-md transition-colors duration-150"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        disabled={submitting || !validateSectorSelection() || !validateSubsectorSelection()}
                        className="px-6 py-2 bg-humdb-red hover:bg-humdb-red-dark text-white font-medium rounded-md transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                      >
                        {submitting ? (
                          <>
                            <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                            Submitting...
                          </>
                        ) : (
                          'Submit Suggestion'
                        )}
                      </button>
                    </div>
                  </div>
                </form>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
