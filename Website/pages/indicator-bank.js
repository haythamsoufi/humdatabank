import Head from 'next/head';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/router';
import { motion } from 'framer-motion';
import { getIndicatorBank, getSectorsSubsectors, getCommonWords } from '../lib/apiService';
import Link from 'next/link';
import { useTranslation } from '../lib/useTranslation';
import { TranslationSafe } from '../components/ClientOnly';
import { processIndicatorName, initializeTooltips, addCommonWordsStyles } from '../lib/commonWordsUtils';

// Force SSR to avoid build-time prerender errors when APIs are unavailable
export async function getServerSideProps() {
  return { props: {} };
}

// Fallback icons for sectors without logos
const getSectorIcon = (sectorName) => {
  const name = sectorName.toLowerCase();
  if (name.includes('health')) return '🏥';
  if (name.includes('shelter')) return '🏠';
  if (name.includes('water') || name.includes('sanitation')) return '💧';
  if (name.includes('food') || name.includes('nutrition')) return '🍽️';
  if (name.includes('education')) return '📚';
  if (name.includes('protection')) return '🛡️';
  if (name.includes('livelihood')) return '💼';
  if (name.includes('coordination')) return '🤝';
  if (name.includes('emergency')) return '🚨';
  if (name.includes('disaster')) return '⚠️';
  if (name.includes('environment')) return '🌱';
  if (name.includes('migration')) return '🚶';
  if (name.includes('community')) return '👥';
  return '📊';
};

// Component will fetch data client-side to work with static export

export default function IndicatorBankPage() {
  const router = useRouter();
  const { t, isLoaded } = useTranslation();
  const isRTL = router.locale === 'ar';

  // State for data
  const [allIndicators, setAllIndicators] = useState([]);
  const [filteredIndicators, setFilteredIndicators] = useState([]);
  const [sectorsData, setSectorsData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [commonWords, setCommonWords] = useState([]);

  // State for filters - initialize from router query
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedType, setSelectedType] = useState('');
  const [selectedSector, setSelectedSector] = useState('');
  const [selectedSubSector, setSelectedSubSector] = useState('');
  const [selectedEmergency, setSelectedEmergency] = useState('');
  const [selectedArchived, setSelectedArchived] = useState('');
  const [viewMode, setViewMode] = useState('grid'); // 'grid', 'table'
  const [showFilters, setShowFilters] = useState(false); // For collapsible filter panel
  const [expandedSector, setExpandedSector] = useState(null); // Track which sector's subsectors are shown

  // Propose New Indicator Modal State
  const [showProposeModal, setShowProposeModal] = useState(false);
  const [proposeForm, setProposeForm] = useState({
    name: '',
    email: '',
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
    reason: '',
    additional_notes: ''
  });
  const [submitting, setSubmitting] = useState(false);
  const [submitSuccess, setSubmitSuccess] = useState(false);

  // Initialize filter state from URL query parameters
  useEffect(() => {
    if (router.isReady) {
      setSearchTerm(router.query.search || '');
      setSelectedType(router.query.type || '');
      setSelectedSubSector(router.query.sub_sector || '');
      setSelectedEmergency(router.query.emergency || '');
      setSelectedArchived(router.query.archived || '');
    }
  }, [router.isReady, router.query]);

  // Fetch data on mount and when filters change
  useEffect(() => {
    const fetchData = async () => {
      if (!router.isReady) return;

      setLoading(true);
      setError(null);

      try {
        // Fetch sectors and subsectors data
        const sectorsResponse = await getSectorsSubsectors(router.locale);
        // Normalize sector data to ensure all names are strings
        const normalizedSectors = (sectorsResponse.sectors || []).map(sector => {
          const sectorName = typeof sector.name === 'string'
            ? sector.name
            : (typeof sector.name === 'object' && sector.name !== null
                ? (sector.name.primary || sector.name.name || String(sector.name))
                : String(sector.name || t('fallbacks.unknown')));

          const localizedName = typeof sector.localized_name === 'string'
            ? sector.localized_name
            : (typeof sector.localized_name === 'object' && sector.localized_name !== null
                ? String(sector.localized_name.primary || sector.localized_name.name || sector.localized_name)
                : (sector.localized_name ? String(sector.localized_name) : ''));

          return {
            ...sector,
            name: sectorName,
            localized_name: localizedName || sectorName,
            subsectors: (sector.subsectors || []).map(subsector => {
              const subsectorName = typeof subsector.name === 'string'
                ? subsector.name
                : (typeof subsector.name === 'object' && subsector.name !== null
                    ? (subsector.name.primary || subsector.name.name || String(subsector.name))
                    : String(subsector.name || t('fallbacks.unknown')));

              const subsectorLocalizedName = typeof subsector.localized_name === 'string'
                ? subsector.localized_name
                : (typeof subsector.localized_name === 'object' && subsector.localized_name !== null
                    ? String(subsector.localized_name.primary || subsector.localized_name.name || subsector.localized_name)
                    : (subsector.localized_name ? String(subsector.localized_name) : ''));

              return {
                ...subsector,
                name: subsectorName,
                localized_name: subsectorLocalizedName || subsectorName
              };
            })
          };
        });
        setSectorsData(normalizedSectors);

        // Always fetch all indicators for grid view calculations (only active ones)
        const allData = await getIndicatorBank('', '', '', '', '', false, router.locale);

        // Fetch filtered data for table view if any filters are applied
        const searchQuery = router.query.search || '';
        const type = router.query.type || '';
        const sector = router.query.sector || '';
        const subSector = router.query.sub_sector || '';
        const emergency = router.query.emergency || '';
        const archived = router.query.archived || false; // Default to false (active only)

        const hasFilters = searchQuery || type || sector || subSector || emergency || archived !== false;
        const filteredData = hasFilters ?
          await getIndicatorBank(searchQuery, type, sector, subSector, emergency, archived, router.locale) :
          allData;

        // Fetch common words for tooltips
        const commonWordsResponse = await getCommonWords(router.locale);

        // Debug log to see the structure
        if (allData.indicators && allData.indicators.length > 0) {
          console.log("Sample indicator data:", JSON.stringify(allData.indicators[0], null, 2));
        }

        setAllIndicators(allData.indicators || []);
        setFilteredIndicators(filteredData.indicators || []);
        setCommonWords(commonWordsResponse.common_words || []);

      } catch (err) {
        console.error("Failed to fetch data:", err);
        setError(t('errors.failedToLoadIndicatorData'));
        setAllIndicators([]);
        setFilteredIndicators([]);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [router.isReady, router.locale, router.query]);

  // Initialize tooltips and styles when common words are loaded
  useEffect(() => {
    if (commonWords.length > 0) {
      addCommonWordsStyles();
      initializeTooltips();
    }
  }, [commonWords]);

  // Prevent rendering until translations are loaded to avoid hydration mismatches
  if (!isLoaded || loading) {
    return (
      <div className="w-full px-6 sm:px-8 lg:px-12 py-8">
        <Head>
          <title>Indicator Bank - NGO Databank</title>
        </Head>
        <div className="text-center py-20">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-ngodb-red mb-4"></div>
          <h1 className="text-3xl font-bold text-ngodb-navy mb-2">
            <TranslationSafe fallback="Loading Indicator Bank">
              {t('indicatorBank.loading.title')}
            </TranslationSafe>
          </h1>
          <p className="text-ngodb-gray-600">
            <TranslationSafe fallback="Please wait while we fetch the indicator data...">
              {t('indicatorBank.loading.description')}
            </TranslationSafe>
          </p>
        </div>
      </div>
    );
  }

  // Get unique values for filter dropdowns
  const types = [...new Set(allIndicators.map(ind => ind.type).filter(val => val && typeof val === 'string'))];

  // Helper function to get localized type name
  const getLocalizedTypeName = (type) => {
    if (!type) return '';
    // The backend already returns `localized_type` when we pass `locale=`.
    // For filters we keep the raw stable key to avoid hardcoding language lists here.
    return type;
  };

  // Calculate indicator counts for sectors and subsectors
  const sectorCounts = new Map();
  const subsectorCounts = new Map();

  allIndicators.forEach(indicator => {
    let sectorName = '';
    let subsectorName = '';

    // Process sector
    if (indicator.sector) {
      if (typeof indicator.sector === 'object' && indicator.sector !== null) {
        sectorName = indicator.sector.primary || indicator.sector.name || String(indicator.sector);
      } else {
        sectorName = String(indicator.sector);
      }

      if (sectorName && typeof sectorName === 'string' && sectorName.trim() && sectorName !== 'undefined' && sectorName !== 'null') {
        sectorCounts.set(sectorName, (sectorCounts.get(sectorName) || 0) + 1);
      }
    }

    // Process subsector
    if (indicator.sub_sector) {
      if (typeof indicator.sub_sector === 'object' && indicator.sub_sector !== null) {
        subsectorName = indicator.sub_sector.primary || indicator.sub_sector.name || String(indicator.sub_sector);
      } else {
        subsectorName = String(indicator.sub_sector);
      }

      if (subsectorName && typeof subsectorName === 'string' && subsectorName.trim() && subsectorName !== 'undefined' && subsectorName !== 'null') {
        subsectorCounts.set(subsectorName, (subsectorCounts.get(subsectorName) || 0) + 1);
      }
    }
  });

  // Prepare sectors data with counts and subsectors
  const sectors = sectorsData.map(sector => {
    // Ensure sector name is a string, not an object
    const sectorName = typeof sector.name === 'string'
      ? sector.name
      : (typeof sector.name === 'object' && sector.name !== null
          ? (sector.name.primary || sector.name.name || String(sector.name))
          : String(sector.name || 'Unknown'));

    return {
      ...sector,
      name: sectorName, // Normalize to string
      count: sectorCounts.get(sectorName) || 0,
      subsectors: sector.subsectors.map(subsector => {
        // Ensure subsector name is a string
        const subsectorName = typeof subsector.name === 'string'
          ? subsector.name
          : (typeof subsector.name === 'object' && subsector.name !== null
              ? (subsector.name.primary || subsector.name.name || String(subsector.name))
              : String(subsector.name || 'Unknown'));

        return {
          ...subsector,
          name: subsectorName, // Normalize to string
          count: subsectorCounts.get(subsectorName) || 0
        };
      })
    };
  }).sort((a, b) => a.display_order - b.display_order || (a.localized_name || a.name).localeCompare(b.localized_name || b.name));

  // Prepare subsectors for filter dropdowns
  const subsectors = sectors.flatMap(sector =>
    sector.subsectors.map(subsector => ({
      ...subsector,
      sectorName: sector.name
    }))
  ).sort((a, b) => (a.localized_name || a.name).localeCompare(b.localized_name || b.name));

  // Function to handle search and filter submission
  const handleFilter = (e) => {
    e.preventDefault();
    const queryParams = new URLSearchParams();

    if (searchTerm) queryParams.set('search', searchTerm);
    if (selectedType) queryParams.set('type', selectedType);
    if (selectedSector) queryParams.set('sector', selectedSector);
    if (selectedSubSector) queryParams.set('sub_sector', selectedSubSector);
    if (selectedEmergency) queryParams.set('emergency', selectedEmergency);
    if (selectedArchived) queryParams.set('archived', selectedArchived);

    router.push(`/indicator-bank?${queryParams.toString()}`);
  };

  // Function to handle sector card click
  const handleSectorClick = (sectorName) => {
    setSelectedSector(sectorName);
    setSelectedSubSector(''); // Clear subsector when sector changes
    setViewMode('table');

    const queryParams = new URLSearchParams();
    if (searchTerm) queryParams.set('search', searchTerm);
    if (selectedType) queryParams.set('type', selectedType);
    queryParams.set('sector', sectorName);
    if (selectedEmergency) queryParams.set('emergency', selectedEmergency);
    if (selectedArchived) queryParams.set('archived', selectedArchived);

    router.push(`/indicator-bank?${queryParams.toString()}`);
  };

  // Function to handle subsector card click
  const handleSubsectorClick = (subsectorName, sectorName) => {
    setSelectedSector(sectorName);
    setSelectedSubSector(subsectorName);
    setViewMode('table');

    const queryParams = new URLSearchParams();
    if (searchTerm) queryParams.set('search', searchTerm);
    if (selectedType) queryParams.set('type', selectedType);
    queryParams.set('sector', sectorName);
    queryParams.set('sub_sector', subsectorName);
    if (selectedEmergency) queryParams.set('emergency', selectedEmergency);
    if (selectedArchived) queryParams.set('archived', selectedArchived);

    router.push(`/indicator-bank?${queryParams.toString()}`);
  };

  // Function to toggle subsectors visibility for a sector
  const toggleSubsectors = (sectorName) => {
    setExpandedSector(expandedSector === sectorName ? null : sectorName);
  };

  // Function to clear all filters
  const clearFilters = () => {
    setSearchTerm('');
    setSelectedType('');
    setSelectedSector('');
    setSelectedSubSector('');
    setSelectedEmergency('');
    setSelectedArchived('');
    router.push('/indicator-bank');
  };

  // Propose New Indicator Modal Functions
  const openProposeModal = () => {
    setShowProposeModal(true);
    setProposeForm({
      name: '',
      email: '',
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
    setSubmitSuccess(false);
  };

  const closeProposeModal = () => {
    setShowProposeModal(false);
    setSubmitting(false);
  };

  const handleProposeFormChange = (e) => {
    const { name, value, type, checked } = e.target;
    const newValue = type === 'checkbox' ? checked : value;

    // Handle nested sector and subsector fields
    if (name.startsWith('sector.') || name.startsWith('sub_sector.')) {
      const [field, level] = name.split('.');
      setProposeForm(prev => ({
        ...prev,
        [field]: {
          ...prev[field],
          [level]: newValue
        }
      }));
      return;
    }

    setProposeForm(prev => ({
      ...prev,
      [name]: newValue
    }));
  };

  // Helper function to validate sector input
  const validateSectorSelection = () => {
    const { sector } = proposeForm;
    // Only primary sector is mandatory
    return sector.primary?.trim();
  };

  // Helper function to validate subsector input
  const validateSubsectorSelection = () => {
    const { sub_sector } = proposeForm;
    // Only primary subsector is mandatory
    return sub_sector.primary?.trim();
  };

  // Helper function to clear all form fields
  const clearAllFormFields = () => {
    setProposeForm({
      name: '',
      email: '',
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

  const handleProposeSubmit = async (e) => {
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
        submitter_name: proposeForm.name,
        submitter_email: proposeForm.email,
        suggestion_type: 'new_indicator',
        indicator_id: null,
        indicator_name: proposeForm.indicator_name,
        definition: proposeForm.definition,
        type: proposeForm.type,
        unit: proposeForm.unit,
        sector: proposeForm.sector,
        sub_sector: proposeForm.sub_sector,
        emergency: proposeForm.emergency,
        related_programs: proposeForm.related_programs,
        reason: proposeForm.reason,
        additional_notes: proposeForm.additional_notes
      };

      // Submit to backend API
      const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:5000';
      const API_KEY = process.env.NEXT_PUBLIC_API_KEY || '';

      const response = await fetch(`${API_BASE_URL}/api/v1/indicator-suggestions?api_key=${API_KEY}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(submissionData)
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || t('alerts.failedToSubmit', { type: 'proposal', message: '' }));
      }

      const result = await response.json();
      console.log('Proposal submitted successfully:', result);

      setSubmitSuccess(true);

    } catch (error) {
      console.error('Error submitting proposal:', error);
      alert(t('indicatorBank.proposeModal.failedToSubmit', { message: error.message }));
    } finally {
      setSubmitting(false);
    }
  };

  if (error) {
    return (
      <div className="w-full px-6 sm:px-8 lg:px-12 py-8 text-center">
        <Head>
          <title>{`${t('indicatorBank.error.title')} - NGO Databank`}</title>
        </Head>
        <h1 className="text-3xl font-bold text-ngodb-red mb-6">{t('indicatorBank.title')}</h1>
        <p className="text-red-600 bg-red-100 p-4 rounded-md">{error}</p>
        <Link href="/indicator-bank" className="mt-4 inline-block text-ngodb-red hover:underline">
          &larr; {t('common.tryAgain')}
        </Link>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="w-full px-6 sm:px-8 lg:px-12 py-8">
        <Head>
          <title>{`Indicator Bank - NGO Databank`}</title>
        </Head>
        <div className="text-center py-20">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-ngodb-red mb-4"></div>
          <h1 className="text-3xl font-bold text-ngodb-navy mb-2">
            <TranslationSafe fallback="Loading Indicator Bank">
              {t('indicatorBank.loading.title')}
            </TranslationSafe>
          </h1>
          <p className="text-ngodb-gray-600">
            <TranslationSafe fallback="Please wait while we fetch the indicator data...">
              {t('indicatorBank.loading.description')}
            </TranslationSafe>
          </p>
        </div>
      </div>
    );
  }

  return (
    <>
      <Head>
        <title>{`${t('indicatorBank.title')} - NGO Databank`}</title>
        <meta name="description" content={t('indicatorBank.meta.description')} />
      </Head>

      <div className={`bg-ngodb-gray-100 min-h-screen ${isRTL ? 'rtl font-tajawal' : ''}`}>
        {/* Hero Section */}
        <section className="bg-gradient-to-br from-ngodb-navy via-ngodb-navy to-ngodb-red text-white py-16 -mt-20 md:-mt-[136px] xl:-mt-20 pt-36 md:pt-[156px] xl:pt-36">
          <motion.div
            className="w-full px-6 sm:px-8 lg:px-12 text-center"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            <motion.h1
              className="text-4xl sm:text-5xl font-extrabold mb-6"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.1 }}
            >
              {t('indicatorBank.hero.title')}
            </motion.h1>
            <motion.p
              className="text-lg sm:text-xl max-w-4xl mx-auto mb-8"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.2 }}
            >
              {t('indicatorBank.hero.description')}
            </motion.p>
          </motion.div>
        </section>

        <div className="w-full px-6 sm:px-8 lg:px-12 py-10">

          {/* Grid View */}
          {viewMode === 'grid' && (
            <>
              {/* Search Bar and Controls for Grid View */}
              <div className={`mb-8 flex justify-between items-center gap-4 ${isRTL ? 'flex-row-reverse' : ''}`}>
                {/* Search Bar */}
                <div className="flex-1">
                  <input
                    type="text"
                    value={searchTerm}
                    onChange={(e) => {
                      const value = e.target.value;
                      setSearchTerm(value);
                      if (value.trim() && viewMode === 'grid') {
                        setViewMode('table');
                        setShowFilters(true);
                      }
                    }}
                    placeholder={t('indicatorBank.search.placeholder')}
                    className={`w-full px-4 py-2 border border-ngodb-gray-300 rounded-md focus:ring-2 focus:ring-ngodb-red focus:border-ngodb-red ${isRTL ? 'text-right' : 'text-left'}`}
                  />
                </div>

                {/* Controls */}
                <div className={`flex items-center gap-2 ${isRTL ? 'flex-row-reverse' : ''}`}>
                  {/* Propose New Indicator Button */}
                  <button
                    onClick={openProposeModal}
                    className="bg-white hover:bg-ngodb-gray-50 text-ngodb-navy border border-ngodb-gray-300 hover:border-ngodb-gray-400 font-medium px-4 py-2 rounded-md transition-all duration-150 flex items-center gap-2 shadow-sm hover:shadow-md"
                  >
                    <svg className="w-4 h-4 text-ngodb-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                    </svg>
                    {t('indicatorBank.proposeNewIndicator')}
                  </button>

                  {/* View Mode Toggle */}
                  <div className="bg-white rounded-lg p-1 shadow-sm border border-ngodb-gray-200">
                    <button
                      onClick={() => setViewMode('grid')}
                      className={`p-2 rounded-md transition-colors duration-150 ${
                        viewMode === 'grid'
                          ? 'bg-ngodb-red text-white'
                          : 'text-ngodb-gray-600 hover:text-ngodb-red'
                      }`}
                      title={t('indicatorBank.viewMode.grid')}
                    >
                      📊
                    </button>
                    <button
                      onClick={() => {
                        setViewMode('table');
                        // Show filters if there are active filters
                        if (searchTerm || selectedType || selectedSector || selectedSubSector || selectedArchived) {
                          setShowFilters(true);
                        }
                      }}
                      className={`p-2 rounded-md transition-colors duration-150 ${
                        viewMode === 'table'
                          ? 'bg-ngodb-red text-white'
                          : 'text-ngodb-gray-600 hover:text-ngodb-red'
                      }`}
                      title={t('indicatorBank.viewMode.table')}
                    >
                      📋
                    </button>
                  </div>
                </div>
              </div>

              {/* Sectors Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                {sectors.filter(sector => sector.count > 0).map((sector) => {
                  const isExpanded = expandedSector === sector.name;

                  return (
                    <div key={sector.id} className="relative">
                      <div className="bg-white rounded-lg shadow-sm border border-ngodb-gray-200 hover:shadow-lg hover:border-ngodb-red transition-all duration-150 overflow-hidden h-full flex flex-col">
                        {/* Main clickable area for sector */}
                        <div
                          onClick={() => handleSectorClick(sector.name)}
                          className="p-6 text-center cursor-pointer flex-1 flex flex-col justify-center"
                        >
                          <div className="mb-4">
                            {sector.logo_url ? (
                              <img
                                src={sector.logo_url}
                                alt={`${sector.name} logo`}
                                className="w-16 h-16 mx-auto object-contain"
                                onError={(e) => {
                                  // Fallback to icon if image fails to load
                                  e.target.style.display = 'none';
                                  e.target.nextSibling.style.display = 'block';
                                }}
                              />
                            ) : null}
                            <div
                              className={`text-4xl ${sector.logo_url ? 'hidden' : ''}`}
                              style={{ display: sector.logo_url ? 'none' : 'block' }}
                            >
                              {getSectorIcon(sector.name)}
                            </div>
                          </div>
                          <h3 className="text-lg font-semibold text-ngodb-navy mb-2">
                            {(() => {
                              // Safely extract string from localized_name or name
                              const localizedName = typeof sector.localized_name === 'string'
                                ? sector.localized_name
                                : (typeof sector.localized_name === 'object' && sector.localized_name !== null
                                    ? String(sector.localized_name.primary || sector.localized_name.name || sector.localized_name)
                                    : '');
                              const sectorName = typeof sector.name === 'string'
                                ? sector.name
                                : String(sector.name || '');
                              return localizedName || sectorName;
                            })()}
                          </h3>
                          {sector.localized_description && (
                            <p className="text-sm text-ngodb-gray-600 line-clamp-2">
                              {sector.localized_description}
                            </p>
                          )}
                        </div>

                        {/* Indicator count and action area */}
                        <div
                          onClick={(e) => {
                            e.stopPropagation();
                            if (sector.subsectors.length > 0) {
                              toggleSubsectors(sector.name);
                            } else {
                              handleSectorClick(sector.name);
                            }
                          }}
                          className="border-t border-ngodb-gray-100 bg-gradient-to-r from-ngodb-gray-50 to-ngodb-gray-100 px-6 py-3 cursor-pointer hover:from-ngodb-gray-100 hover:to-ngodb-gray-200 transition-all duration-150 group flex-shrink-0"
                        >
                          <div className="flex items-center justify-center gap-2">
                            <span className="text-sm text-ngodb-gray-600 group-hover:text-ngodb-gray-700 transition-colors duration-150">
                              {sector.count} {sector.count === 1 ? t('indicatorBank.indicator') : t('indicatorBank.indicators')}
                            </span>
                            {sector.subsectors.length > 0 && (
                              <span className={`text-ngodb-gray-300 group-hover:text-ngodb-gray-400 transition-all duration-150 ${
                                isExpanded ? 'rotate-180' : ''
                              }`}>
                                ▼
                              </span>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Subsectors Dropdown */}
                      {isExpanded && sector.subsectors.length > 0 && (
                        <div className={`absolute top-full z-10 mt-2 bg-white rounded-lg shadow-lg border border-ngodb-gray-200 max-h-60 overflow-y-auto ${isRTL ? 'right-0 left-0' : 'left-0 right-0'}`}>
                          <div className="p-3">
                            <h4 className={`text-sm font-medium text-ngodb-gray-700 mb-2 ${isRTL ? 'text-right' : 'text-left'}`}>{t('indicatorBank.filters.subsector.label')}</h4>
                            <div className="space-y-2">
                              {sector.subsectors.map((subsector) => (
                                <div
                                  key={subsector.id}
                                  onClick={() => handleSubsectorClick(subsector.name, sector.name)}
                                  className={`flex items-center justify-between p-2 rounded hover:bg-ngodb-gray-50 cursor-pointer transition-colors duration-150 ${isRTL ? 'flex-row-reverse' : ''}`}
                                >
                                  <div className={`flex items-center gap-2 ${isRTL ? 'flex-row-reverse' : ''}`}>
                                    {subsector.logo_url && (
                                      <img
                                        src={subsector.logo_url}
                                        alt={`${subsector.name} logo`}
                                        className="w-4 h-4 object-contain"
                                      />
                                    )}
                                    <span className="text-sm text-ngodb-navy">{subsector.localized_name || subsector.name}</span>
                                  </div>
                                  <span className="text-xs text-ngodb-gray-500">
                                    {subsector.count} {subsector.count === 1 ? t('indicatorBank.indicator') : t('indicatorBank.indicators')}
                                  </span>
                                </div>
                              ))}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </>
          )}

          {/* Table View */}
          {viewMode === 'table' && (
            <>
              {/* Search Bar and Controls for Table View */}
              <div className={`mb-8 flex justify-between items-center gap-4 ${isRTL ? 'flex-row-reverse' : ''}`}>
                {/* Search Bar */}
                <div className="flex-1">
                  <input
                    type="text"
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    placeholder={t('indicatorBank.filter.placeholder')}
                    className={`w-full px-4 py-2 border border-ngodb-gray-300 rounded-md focus:ring-2 focus:ring-ngodb-red focus:border-ngodb-red ${isRTL ? 'text-right' : 'text-left'}`}
                  />
                </div>

                {/* Controls */}
                <div className={`flex items-center gap-2 ${isRTL ? 'flex-row-reverse' : ''}`}>
                  {/* Propose New Indicator Button */}
                  <button
                    onClick={openProposeModal}
                    className="bg-white hover:bg-ngodb-gray-50 text-ngodb-navy border border-ngodb-gray-300 hover:border-ngodb-gray-400 font-medium px-4 py-2 rounded-md transition-all duration-150 flex items-center gap-2 shadow-sm hover:shadow-md"
                  >
                    <svg className="w-4 h-4 text-ngodb-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                    </svg>
                    {t('indicatorBank.proposeNewIndicator')}
                  </button>

                  {/* Filter Toggle Button */}
                  <button
                    onClick={() => setShowFilters(!showFilters)}
                    className="bg-white hover:bg-ngodb-gray-50 text-ngodb-navy font-medium px-4 py-2 rounded-lg shadow-sm border border-ngodb-gray-200 transition-colors duration-150 flex items-center gap-2"
                  >
                    <span>🔍</span>
                    <span>{t('indicatorBank.filters.title')}</span>
                    <span className={`transform transition-transform duration-200 ${showFilters ? 'rotate-180' : ''}`}>
                      ▼
                    </span>
                    {(searchTerm || selectedType || selectedSector || selectedSubSector || selectedArchived) && (
                      <span className="bg-ngodb-red text-white text-xs px-2 py-1 rounded-full ml-2">
                        {t('indicatorBank.filters.active')}
                      </span>
                    )}
                  </button>

                  {/* View Mode Toggle */}
                  <div className="bg-white rounded-lg p-1 shadow-sm border border-ngodb-gray-200">
                  <button
                    onClick={() => setViewMode('grid')}
                    className={`p-2 rounded-md transition-colors duration-150 ${
                      viewMode === 'grid'
                        ? 'bg-ngodb-red text-white'
                        : 'text-ngodb-gray-600 hover:text-ngodb-red'
                    }`}
                    title={t('indicatorBank.viewMode.grid')}
                  >
                    📊
                  </button>
                  <button
                    onClick={() => {
                      setViewMode('table');
                      // Show filters if there are active filters
                        if (searchTerm || selectedType || selectedSector || selectedSubSector || selectedArchived) {
                        setShowFilters(true);
                      }
                    }}
                    className={`p-2 rounded-md transition-colors duration-150 ${
                      viewMode === 'table'
                        ? 'bg-ngodb-red text-white'
                        : 'text-ngodb-gray-600 hover:text-ngodb-red'
                    }`}
                    title={t('indicatorBank.viewMode.table')}
                  >
                    📋
                  </button>
                  </div>
                </div>
              </div>

              {/* Filter Toggle Button */}
              {showFilters && (
                <form onSubmit={handleFilter} className="mb-10 bg-white p-6 rounded-lg shadow-sm border border-ngodb-gray-200">
                  {/* Search Bar */}
                  <div className="mb-6">
                    <label htmlFor="indicator-search" className="block text-sm font-medium text-ngodb-gray-700 mb-2">
                      {t('indicatorBank.filters.search.title')}
                    </label>
                    <input
                      id="indicator-search"
                      type="text"
                      value={searchTerm}
                      onChange={(e) => setSearchTerm(e.target.value)}
                      placeholder={t('indicatorBank.filters.search.placeholder')}
                      className={`w-full px-4 py-3 border border-ngodb-gray-300 rounded-md focus:ring-2 focus:ring-ngodb-red focus:border-ngodb-red ${isRTL ? 'text-right' : 'text-left'}`}
                    />
                  </div>

                  {/* Filter Dropdowns */}
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
                    <div>
                      <label htmlFor="type-filter" className="block text-sm font-medium text-ngodb-gray-700 mb-1">
                        {t('indicatorBank.filters.type.label')}
                      </label>
                      <select
                        id="type-filter"
                        value={selectedType}
                        onChange={(e) => setSelectedType(e.target.value)}
                        className={`w-full px-3 py-2 border border-ngodb-gray-300 rounded-md focus:ring-2 focus:ring-ngodb-red focus:border-ngodb-red ${isRTL ? 'text-right' : 'text-left'}`}
                      >
                        <option value="">{t('indicatorBank.filters.type.all')}</option>
                        {types.map(type => (
                          <option key={type} value={type}>{getLocalizedTypeName(type)}</option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label htmlFor="sector-filter" className="block text-sm font-medium text-ngodb-gray-700 mb-1">
                        {t('indicatorBank.filters.sector.label')}
                      </label>
                      <select
                        id="sector-filter"
                        value={selectedSector}
                        onChange={(e) => {
                          setSelectedSector(e.target.value);
                          if (e.target.value !== selectedSector) setSelectedSubSector(''); // Clear subsector when sector changes
                        }}
                        className={`w-full px-3 py-2 border border-ngodb-gray-300 rounded-md focus:ring-2 focus:ring-ngodb-red focus:border-ngodb-red ${isRTL ? 'text-right' : 'text-left'}`}
                      >
                        <option value="">{t('indicatorBank.filters.sector.all')}</option>
                        {sectors.map(sector => (
                          <option key={sector.id} value={sector.name}>{sector.localized_name || sector.name}</option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label htmlFor="subsector-filter" className="block text-sm font-medium text-ngodb-gray-700 mb-1">
                        {t('indicatorBank.filters.subsector.label')}
                      </label>
                      <select
                        id="subsector-filter"
                        value={selectedSubSector}
                        onChange={(e) => setSelectedSubSector(e.target.value)}
                        className={`w-full px-3 py-2 border border-ngodb-gray-300 rounded-md focus:ring-2 focus:ring-ngodb-red focus:border-ngodb-red ${isRTL ? 'text-right' : 'text-left'}`}
                      >
                        <option value="">{t('indicatorBank.filters.subsector.all')}</option>
                        {subsectors
                          .filter(sub => !selectedSector || sub.sectorName === selectedSector)
                          .map(sub => (
                            <option key={sub.id} value={sub.name}>{sub.localized_name || sub.name}</option>
                          ))}
                      </select>
                    </div>

                    <div>
                      <label htmlFor="archived-filter" className="block text-sm font-medium text-ngodb-gray-700 mb-1">
                        {t('indicatorBank.filters.status.label')}
                      </label>
                      <select
                        id="archived-filter"
                        value={selectedArchived || 'false'}
                        onChange={(e) => setSelectedArchived(e.target.value === 'false' ? null : e.target.value)}
                        className={`w-full px-3 py-2 border border-ngodb-gray-300 rounded-md focus:ring-2 focus:ring-ngodb-red focus:border-ngodb-red ${isRTL ? 'text-right' : 'text-left'}`}
                      >
                        <option value="false">{t('indicatorBank.filters.status.activeOnly')}</option>
                        <option value="">{t('indicatorBank.filters.status.all')}</option>
                        <option value="true">{t('indicatorBank.filters.status.archivedOnly')}</option>
                      </select>
                    </div>
                  </div>

                  {/* Action Buttons */}
                  <div className="flex gap-4">
                    <button
                      type="submit"
                      className="bg-ngodb-red hover:bg-ngodb-red-dark text-white font-semibold px-6 py-2 rounded-md transition-colors duration-150"
                    >
                      {t('indicatorBank.filters.apply')}
                    </button>
                    <button
                      type="button"
                      onClick={clearFilters}
                      className="bg-ngodb-gray-300 hover:bg-ngodb-gray-400 text-ngodb-gray-700 font-semibold px-6 py-2 rounded-md transition-colors duration-150"
                    >
                      {t('indicatorBank.filters.clearAll')}
                    </button>
                  </div>
                </form>
              )}

              {/* Results Count */}
              <div className="mb-6">
                {(() => {
                  const filteredCount = filteredIndicators.filter(indicator =>
                    !searchTerm ||
                    String(indicator.localized_name || indicator.name || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
                    String(indicator.localized_definition || indicator.definition || '').toLowerCase().includes(searchTerm.toLowerCase())
                  ).length;

                  return (
                <p className="text-ngodb-gray-600">
                      {t('indicatorBank.results.showing')} {filteredCount} {filteredCount === 1 ? t('indicatorBank.indicator') : t('indicatorBank.indicators')}
                      {searchTerm && t('indicatorBank.results.matching', { term: searchTerm })}
                </p>
                  );
                })()}
              </div>

              {/* Table View */}
              {filteredIndicators.length === 0 ? (
                <p className="text-center text-ngodb-gray-600 text-lg py-10">
                  {searchTerm || selectedType || selectedSector || selectedEmergency ?
                    t('indicatorBank.results.noResults') :
                    t('indicatorBank.results.noIndicators')
                  }
                </p>
              ) : (
                <div className={`bg-white rounded-lg shadow-sm overflow-hidden ${isRTL ? 'rtl' : ''}`} dir={isRTL ? 'rtl' : 'ltr'}>
                  <div className="overflow-x-auto" dir={isRTL ? 'rtl' : 'ltr'}>
                    <table className={`min-w-full divide-y divide-ngodb-gray-200 ${isRTL ? 'rtl' : ''}`} dir={isRTL ? 'rtl' : 'ltr'}>
                      <thead className="bg-ngodb-gray-50" dir={isRTL ? 'rtl' : 'ltr'}>
                        <tr dir={isRTL ? 'rtl' : 'ltr'}>
                          <th className={`px-6 py-3 text-xs font-medium text-ngodb-gray-500 uppercase tracking-wider ${isRTL ? 'text-right' : 'text-left'}`}>
                            {t('indicatorBank.table.name')}
                          </th>
                          <th className={`px-6 py-3 text-xs font-medium text-ngodb-gray-500 uppercase tracking-wider ${isRTL ? 'text-right' : 'text-left'}`}>
                            {t('indicatorBank.table.type')}
                          </th>
                          <th className={`px-6 py-3 text-xs font-medium text-ngodb-gray-500 uppercase tracking-wider ${isRTL ? 'text-right' : 'text-left'}`}>
                            {t('indicatorBank.table.sector')}
                          </th>
                          <th className={`px-6 py-3 text-xs font-medium text-ngodb-gray-500 uppercase tracking-wider ${isRTL ? 'text-right' : 'text-left'}`}>
                            {t('indicatorBank.table.subsector')}
                          </th>
                          <th className={`px-6 py-3 text-xs font-medium text-ngodb-gray-500 uppercase tracking-wider ${isRTL ? 'text-right' : 'text-left'}`}>
                            {t('indicatorBank.table.unit')}
                          </th>
                        </tr>
                      </thead>
                      <tbody className="bg-white divide-y divide-ngodb-gray-200" dir={isRTL ? 'rtl' : 'ltr'}>
                        {filteredIndicators
                          .filter(indicator =>
                            !searchTerm ||
                            String(indicator.localized_name || indicator.name || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
                            String(indicator.localized_definition || indicator.definition || '').toLowerCase().includes(searchTerm.toLowerCase())
                          )
                          .map((indicator) => (
                          <tr key={indicator.id} className="hover:bg-ngodb-gray-50" dir={isRTL ? 'rtl' : 'ltr'}>
                            <td className={`px-6 py-4 ${isRTL ? 'text-right' : 'text-left'}`} dir={isRTL ? 'rtl' : 'ltr'}>
                              <Link href={`/indicator-bank/${indicator.id}`} className="text-ngodb-navy hover:text-ngodb-red font-medium" dir={isRTL ? 'rtl' : 'ltr'}>
                                {commonWords.length > 0 ? (
                                  <span dangerouslySetInnerHTML={{
                                    __html: processIndicatorName(
                                      String(indicator.localized_name || indicator.name || ''),
                                      commonWords,
                                      router.locale
                                    )
                                  }} />
                                ) : (
                                  String(indicator.localized_name || indicator.name || '')
                                )}
                              </Link>
                            </td>
                            <td className={`px-6 py-4 text-sm text-ngodb-gray-600 ${isRTL ? 'text-right' : 'text-left'}`} dir={isRTL ? 'rtl' : 'ltr'}>
                              {String(indicator.localized_type || indicator.type || '')}
                            </td>
                            <td className={`px-6 py-4 text-sm text-ngodb-gray-600 ${isRTL ? 'text-right' : 'text-left'}`} dir={isRTL ? 'rtl' : 'ltr'}>
                              {typeof indicator.sector === 'object' && indicator.sector !== null
                                ? String(indicator.sector.localized_name || indicator.sector.primary || indicator.sector.name || indicator.sector)
                                : String(indicator.sector || '')}
                            </td>
                            <td className={`px-6 py-4 text-sm text-ngodb-gray-600 ${isRTL ? 'text-right' : 'text-left'}`} dir={isRTL ? 'rtl' : 'ltr'}>
                              {typeof indicator.sub_sector === 'object' && indicator.sub_sector !== null
                                ? String(indicator.sub_sector.localized_name || indicator.sub_sector.primary || indicator.sub_sector.name || indicator.sub_sector)
                                : String(indicator.sub_sector || '')}
                            </td>
                            <td className={`px-6 py-4 text-sm text-ngodb-gray-600 ${isRTL ? 'text-right' : 'text-left'}`} dir={isRTL ? 'rtl' : 'ltr'}>
                              {String(indicator.localized_unit || indicator.unit || '')}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}

          {/* Guide to Indicator Selection */}
          <div className={`mt-20 ${isRTL ? 'rtl' : ''}`}>
            <h2 className={`text-3xl font-bold text-ngodb-navy mb-12 text-center ${isRTL ? 'text-right' : 'text-left'}`}>{t('indicatorBank.guide.title')}</h2>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
              {/* Step 1 */}
              <div className="group bg-gradient-to-br from-blue-50 to-indigo-100 rounded-xl shadow-lg border border-blue-200 p-8 hover:shadow-xl hover:scale-105 transition-all duration-300 transform hover:-translate-y-2">
                <div className="flex items-center justify-center w-16 h-16 bg-ngodb-red text-white rounded-full text-2xl font-bold mb-6 mx-auto group-hover:scale-110 transition-transform duration-300">
                  1
                </div>
                <h3 className={`text-xl font-bold text-ngodb-navy mb-4 text-center ${isRTL ? 'text-right' : 'text-left'}`}>{t('indicatorBank.guide.step1.title')}</h3>
                <p className={`text-ngodb-gray-700 leading-relaxed text-center ${isRTL ? 'text-right' : 'text-left'}`}>
                  {t('indicatorBank.guide.step1.description')}
                </p>
                <div className="mt-6 flex justify-center">
                  <div className="w-8 h-8 bg-ngodb-red rounded-full opacity-20 group-hover:opacity-40 transition-opacity duration-300"></div>
                </div>
              </div>

              {/* Step 2 */}
              <div className="group bg-gradient-to-br from-green-50 to-emerald-100 rounded-xl shadow-lg border border-green-200 p-8 hover:shadow-xl hover:scale-105 transition-all duration-300 transform hover:-translate-y-2">
                <div className="flex items-center justify-center w-16 h-16 bg-ngodb-red text-white rounded-full text-2xl font-bold mb-6 mx-auto group-hover:scale-110 transition-transform duration-300">
                  2
                </div>
                <h3 className={`text-xl font-bold text-ngodb-navy mb-4 text-center ${isRTL ? 'text-right' : 'text-left'}`}>{t('indicatorBank.guide.step2.title')}</h3>
                <p className={`text-ngodb-gray-700 leading-relaxed text-center ${isRTL ? 'text-right' : 'text-left'}`}>
                  {t('indicatorBank.guide.step2.description')}
                </p>
                <div className="mt-6 flex justify-center">
                  <div className="w-8 h-8 bg-ngodb-red rounded-full opacity-20 group-hover:opacity-40 transition-opacity duration-300"></div>
                </div>
              </div>

              {/* Step 3 */}
              <div className="group bg-gradient-to-br from-purple-50 to-violet-100 rounded-xl shadow-lg border border-purple-200 p-8 hover:shadow-xl hover:scale-105 transition-all duration-300 transform hover:-translate-y-2">
                <div className="flex items-center justify-center w-16 h-16 bg-ngodb-red text-white rounded-full text-2xl font-bold mb-6 mx-auto group-hover:scale-110 transition-transform duration-300">
                  3
                </div>
                <h3 className={`text-xl font-bold text-ngodb-navy mb-4 text-center ${isRTL ? 'text-right' : 'text-left'}`}>{t('indicatorBank.guide.step3.title')}</h3>
                <p className={`text-ngodb-gray-700 leading-relaxed text-center ${isRTL ? 'text-right' : 'text-left'}`}>
                  {t('indicatorBank.guide.step3.description')}
                </p>
                <div className="mt-6 flex justify-center">
                  <div className="w-8 h-8 bg-ngodb-red rounded-full opacity-20 group-hover:opacity-40 transition-opacity duration-300"></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Propose New Indicator Modal */}
      {showProposeModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-[99999] p-4">
          <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-ngodb-gray-200">
              <div className="flex justify-between items-center">
                <h2 className="text-xl font-semibold text-ngodb-navy">Propose New Indicator</h2>
                <button
                  onClick={closeProposeModal}
                  className="text-ngodb-gray-400 hover:text-ngodb-gray-600 transition-colors duration-150"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
              <p className="text-ngodb-gray-600 mt-1">
                Help us expand our indicator bank by proposing a new indicator for humanitarian response.
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
                  <h3 className="text-lg font-semibold text-ngodb-navy mb-2">{t('indicatorBank.proposeModal.thankYou')}</h3>
                  <p className="text-ngodb-gray-600 mb-6">
                    {t('indicatorBank.proposeModal.successMessage')}
                  </p>
                  <div className="bg-blue-50 border border-blue-200 rounded-md p-4 mb-6">
                    <div className="flex items-start">
                      <svg className="w-5 h-5 text-blue-500 mt-0.5 mr-3 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 4.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                      </svg>
                      <div>
                        <p className="text-blue-800 font-medium">{t('indicatorBank.proposeModal.confirmationEmailSent')}</p>
                        <p className="text-blue-700 text-sm mt-1">
                          {t('indicatorBank.proposeModal.confirmationEmailMessage', { email: proposeForm.email })}
                        </p>
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={closeProposeModal}
                    className="bg-ngodb-red hover:bg-ngodb-red-dark text-white font-medium px-6 py-2 rounded-md transition-colors duration-150"
                  >
                    {t('indicatorBank.proposeModal.close')}
                  </button>
                </div>
              ) : (
                <form onSubmit={handleProposeSubmit} className="space-y-6">
                  {/* Contact Information */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label htmlFor="name" className="block text-sm font-medium text-ngodb-gray-700 mb-1">
                        Your Name *
                      </label>
                      <input
                        type="text"
                        id="name"
                        name="name"
                        value={proposeForm.name}
                        onChange={handleProposeFormChange}
                        required
                        className="w-full px-3 py-2 border border-ngodb-gray-300 rounded-md focus:ring-2 focus:ring-ngodb-red focus:border-ngodb-red"
                      />
                    </div>
                    <div>
                      <label htmlFor="email" className="block text-sm font-medium text-ngodb-gray-700 mb-1">
                        Email Address *
                      </label>
                      <input
                        type="email"
                        id="email"
                        name="email"
                        value={proposeForm.email}
                        onChange={handleProposeFormChange}
                        required
                        className="w-full px-3 py-2 border border-ngodb-gray-300 rounded-md focus:ring-2 focus:ring-ngodb-red focus:border-ngodb-red"
                      />
                    </div>
                  </div>

                  {/* Indicator Information */}
                  <div className="border-t border-ngodb-gray-200 pt-6">
                    <h3 className="text-lg font-semibold text-ngodb-navy mb-4">Indicator Information</h3>

                    {/* Indicator Name */}
                    <div className="mb-4">
                      <label htmlFor="indicator_name" className="block text-sm font-medium text-ngodb-gray-700 mb-1">
                        Indicator Name *
                      </label>
                      <input
                        type="text"
                        id="indicator_name"
                        name="indicator_name"
                        value={proposeForm.indicator_name}
                        onChange={handleProposeFormChange}
                        required
                        className="w-full px-3 py-2 border border-ngodb-gray-300 rounded-md focus:ring-2 focus:ring-ngodb-red focus:border-ngodb-red"
                      />
                    </div>

                    {/* Definition */}
                    <div className="mb-4">
                      <label htmlFor="definition" className="block text-sm font-medium text-ngodb-gray-700 mb-1">
                        Definition *
                      </label>
                      <textarea
                        id="definition"
                        name="definition"
                        value={proposeForm.definition}
                        onChange={handleProposeFormChange}
                        required
                        rows={4}
                        className="w-full px-3 py-2 border border-ngodb-gray-300 rounded-md focus:ring-2 focus:ring-ngodb-red focus:border-ngodb-red"
                      />
                    </div>

                    {/* Type and Unit */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                      <div>
                        <label htmlFor="type" className="block text-sm font-medium text-ngodb-gray-700 mb-1">
                          Type
                        </label>
                        <input
                          type="text"
                          id="type"
                          name="type"
                          value={proposeForm.type}
                          onChange={handleProposeFormChange}
                          className="w-full px-3 py-2 border border-ngodb-gray-300 rounded-md focus:ring-2 focus:ring-ngodb-red focus:border-ngodb-red"
                        />
                      </div>
                      <div>
                        <label htmlFor="unit" className="block text-sm font-medium text-ngodb-gray-700 mb-1">
                          Unit of Measurement
                        </label>
                        <input
                          type="text"
                          id="unit"
                          name="unit"
                          value={proposeForm.unit}
                          onChange={handleProposeFormChange}
                          className="w-full px-3 py-2 border border-ngodb-gray-300 rounded-md focus:ring-2 focus:ring-ngodb-red focus:border-ngodb-red"
                        />
                      </div>
                    </div>

                    {/* Sector and Sub-sector */}
                    <div className="mb-4">
                      <h4 className="text-md text-ngodb-navy mb-3">Sector</h4>

                      {/* Sector */}
                      <div className="mb-6">
                        <label className="block text-sm font-medium text-ngodb-gray-700 mb-3">
                          Sector
                        </label>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                          <div>
                            <label className="block text-xs font-medium text-ngodb-gray-600 mb-2">
                              Primary Sector *
                            </label>
                            <input
                              type="text"
                              name="sector.primary"
                              value={proposeForm.sector.primary}
                              onChange={handleProposeFormChange}
                              placeholder={t('forms.placeholders.sectorPrimary')}
                              className="w-full px-3 py-2 border border-ngodb-gray-300 rounded-md focus:ring-2 focus:ring-ngodb-red focus:border-ngodb-red text-sm"
                            />
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-ngodb-gray-600 mb-2">
                              Secondary Sector
                            </label>
                            <input
                              type="text"
                              name="sector.secondary"
                              value={proposeForm.sector.secondary}
                              onChange={handleProposeFormChange}
                              placeholder={t('forms.placeholders.sectorSecondary')}
                              className="w-full px-3 py-2 border border-ngodb-gray-300 rounded-md focus:ring-2 focus:ring-ngodb-red focus:border-ngodb-red text-sm"
                            />
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-ngodb-gray-600 mb-2">
                              Tertiary Sector
                            </label>
                            <input
                              type="text"
                              name="sector.tertiary"
                              value={proposeForm.sector.tertiary}
                              onChange={handleProposeFormChange}
                              placeholder={t('forms.placeholders.sectorTertiary')}
                              className="w-full px-3 py-2 border border-ngodb-gray-300 rounded-md focus:ring-2 focus:ring-ngodb-red focus:border-ngodb-red text-sm"
                            />
                          </div>
                        </div>
                        {!validateSectorSelection() && (
                          <p className="text-xs text-red-600 mt-2">
                            ⚠️ Please enter primary sector
                          </p>
                        )}
                      </div>

                      {/* Sub-sector */}
                      <div className="mb-4">
                        <label className="block text-sm font-medium text-ngodb-gray-700 mb-3">
                          Sub-Sector
                        </label>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                          <div>
                            <label className="block text-xs font-medium text-ngodb-gray-600 mb-2">
                              Primary Sub-Sector *
                            </label>
                            <input
                              type="text"
                              name="sub_sector.primary"
                              value={proposeForm.sub_sector.primary}
                              onChange={handleProposeFormChange}
                              placeholder={t('forms.placeholders.sectorSecondary')}
                              className="w-full px-3 py-2 border border-ngodb-gray-300 rounded-md focus:ring-2 focus:ring-ngodb-red focus:border-ngodb-red text-sm"
                            />
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-ngodb-gray-600 mb-2">
                              Secondary Sub-Sector
                            </label>
                            <input
                              type="text"
                              name="sub_sector.secondary"
                              value={proposeForm.sub_sector.secondary}
                              onChange={handleProposeFormChange}
                              placeholder={t('forms.placeholders.sectorTertiary')}
                              className="w-full px-3 py-2 border border-ngodb-gray-300 rounded-md focus:ring-2 focus:ring-ngodb-red focus:border-ngodb-red text-sm"
                            />
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-ngodb-gray-600 mb-2">
                              Tertiary Sub-Sector
                            </label>
                            <input
                              type="text"
                              name="sub_sector.tertiary"
                              value={proposeForm.sub_sector.tertiary}
                              onChange={handleProposeFormChange}
                              placeholder={t('forms.placeholders.subsectorTertiary')}
                              className="w-full px-3 py-2 border border-ngodb-gray-300 rounded-md focus:ring-2 focus:ring-ngodb-red focus:border-ngodb-red text-sm"
                            />
                          </div>
                        </div>
                        {!validateSubsectorSelection() && (
                          <p className="text-xs text-red-600 mt-2">
                            ⚠️ Please enter primary subsector
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
                          checked={proposeForm.emergency}
                          onChange={handleProposeFormChange}
                          className="h-4 w-4 text-ngodb-red focus:ring-ngodb-red border-ngodb-gray-300 rounded"
                        />
                        <span className="ml-2 text-sm font-medium text-ngodb-gray-700">
                          Emergency Context
                        </span>
                      </label>
                    </div>

                    {/* Related Programs */}
                    <div className="mb-4">
                      <label htmlFor="related_programs" className="block text-sm font-medium text-ngodb-gray-700 mb-1">
                        Related Programs
                      </label>
                      <input
                        type="text"
                        id="related_programs"
                        name="related_programs"
                        value={proposeForm.related_programs}
                        onChange={handleProposeFormChange}
                        placeholder={t('forms.placeholders.programs')}
                        className="w-full px-3 py-2 border border-ngodb-gray-300 rounded-md focus:ring-2 focus:ring-ngodb-red focus:border-ngodb-red"
                      />
                    </div>
                  </div>

                  {/* Reason and Additional Notes */}
                  <div className="border-t border-ngodb-gray-200 pt-6">
                    <div className="mb-4">
                      <label htmlFor="reason" className="block text-sm font-medium text-ngodb-gray-700 mb-1">
                        Reason for Proposal *
                      </label>
                      <textarea
                        id="reason"
                        name="reason"
                        value={proposeForm.reason}
                        onChange={handleProposeFormChange}
                        required
                        rows={3}
                        placeholder={t('forms.placeholders.indicatorNeeded')}
                        className="w-full px-3 py-2 border border-ngodb-gray-300 rounded-md focus:ring-2 focus:ring-ngodb-red focus:border-ngodb-red"
                      />
                    </div>

                    <div className="mb-4">
                      <label htmlFor="additional_notes" className="block text-sm font-medium text-ngodb-gray-700 mb-1">
                        Additional Notes
                      </label>
                      <textarea
                        id="additional_notes"
                        name="additional_notes"
                        value={proposeForm.additional_notes}
                        onChange={handleProposeFormChange}
                        rows={3}
                        placeholder={t('forms.placeholders.additionalNotes')}
                        className="w-full px-3 py-2 border border-ngodb-gray-300 rounded-md focus:ring-2 focus:ring-ngodb-red focus:border-ngodb-red"
                      />
                    </div>
                  </div>

                  {/* Form Actions */}
                  <div className="flex justify-between items-center pt-4 border-t border-ngodb-gray-200">
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={clearAllFormFields}
                        className="px-3 py-2 text-ngodb-gray-600 bg-ngodb-gray-100 hover:bg-ngodb-gray-200 rounded-md transition-colors duration-150 text-sm"
                      >
                        {t('indicatorBank.proposeModal.clearAll')}
                      </button>
                    </div>
                    <div className="flex gap-3">
                      <button
                        type="button"
                        onClick={closeProposeModal}
                        className="px-4 py-2 text-ngodb-gray-700 bg-ngodb-gray-200 hover:bg-ngodb-gray-300 rounded-md transition-colors duration-150"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        disabled={submitting || !validateSectorSelection() || !validateSubsectorSelection()}
                        className="px-6 py-2 bg-ngodb-red hover:bg-ngodb-red-dark text-white font-medium rounded-md transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                      >
                        {submitting ? (
                          <>
                            <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                            {t('indicatorBank.proposeModal.submitting')}
                          </>
                        ) : (
                          t('indicatorBank.proposeModal.submitProposal')
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
