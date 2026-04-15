import Head from 'next/head';
import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useTranslation } from '../lib/useTranslation';
import { getDataWithRelated, getFilterOptions, processDisaggregatedData, FDRS_TEMPLATE_ID } from '../lib/apiService';
import MultiChart from '../components/MultiChart';

export default function PeopleReachedAnalysisPage() {
  const { t } = useTranslation();

  // State management
  const [rawData, setRawData] = useState([]);
  const [processedData, setProcessedData] = useState({
    totalReached: 0,
    byCountry: [],
    bySex: [],
    byAge: [],
    bySexAge: [],
    trends: []
  });
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

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

  // Load filter options on component mount
  useEffect(() => {
    const loadFilterOptions = async () => {
      try {
        const options = await getFilterOptions();
        setFilters(prev => ({
          ...prev,
          countries: options.countries,
          periods: options.periods,
          indicators: options.indicators
        }));
      } catch (error) {
        console.error('Error loading filter options:', error);
      }
    };

    loadFilterOptions();
  }, []);

  // Fetch data from API
  const fetchData = async () => {
    setIsLoading(true);
    setError(null);
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

      console.log('Fetching with filters:', apiFilters);
      const data = await getDataWithRelated(apiFilters);
      console.log('Received data:', data);

      // getDataWithRelated returns array directly (backward compatible mode)
      let dataArray = Array.isArray(data) ? data : (data?.data || []);

      // Filter by countries on frontend if needed (since backend /data/tables uses country_id, not country names)
      if (filters.selectedCountries && filters.selectedCountries.length > 0) {
        dataArray = dataArray.filter(item => {
          const countryName = item?.country_info?.name;
          return countryName && filters.selectedCountries.includes(countryName);
        });
      }

      setRawData(dataArray);

      // Process the data
      const processed = processDisaggregatedData(dataArray);
      setProcessedData(processed);

    } catch (err) {
      console.error('Error fetching data:', err);
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  // Load data when filters change
  useEffect(() => {
    if (filters.countries.length > 0) { // Only fetch when filter options are loaded
      fetchData();
    }
  }, [filters.selectedCountries, filters.selectedPeriod, filters.selectedIndicator, filters.countries]);

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

  // Calculate summary statistics
  const getSummaryStats = () => {
    const stats = {
      totalCountries: processedData.byCountry.length,
      totalSexCategories: processedData.bySex.length,
      totalAgeGroups: processedData.byAge.length,
      totalDataPoints: rawData.filter(item => item.disaggregation_data).length,
      avgPerCountry: processedData.byCountry.length > 0
        ? Math.round(processedData.totalReached / processedData.byCountry.length)
        : 0
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
          <title>Error - People Reached Analysis - Humanitarian Databank</title>
        </Head>
        <h1 className="text-3xl font-bold text-humdb-red mb-6">Error Loading Data</h1>
        <p className="text-humdb-gray-700 mb-6">{error}</p>
        <button
          onClick={fetchData}
          className="bg-humdb-red text-white px-6 py-2 rounded-lg hover:bg-humdb-red-dark transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <>
      <Head>
        <title>People Reached Analysis - Humanitarian Databank</title>
        <meta name="description" content="Analyze people reached data by sex and age groups across humanitarian operations" />
      </Head>

      {/* Hero Section */}
      <section className="bg-gradient-to-br from-humdb-navy via-humdb-navy to-humdb-red text-white py-16">
        <motion.div
          className="w-full px-6 sm:px-8 lg:px-12 text-center"
          variants={staggerContainer}
          initial="hidden"
          animate="visible"
        >
          <motion.h1 className="text-4xl sm:text-5xl font-extrabold mb-6" variants={slideUp}>
            People Reached Analysis
          </motion.h1>
          <motion.p className="text-lg sm:text-xl max-w-4xl mx-auto mb-8" variants={slideUp}>
            Explore and analyze disaggregated data on people reached by sex and age groups across humanitarian operations worldwide
          </motion.p>

          {!isLoading && processedData.totalReached > 0 && (
            <motion.div
              className="grid grid-cols-2 md:grid-cols-5 gap-4 max-w-4xl mx-auto"
              variants={staggerContainer}
            >
              <motion.div className="bg-white bg-opacity-10 backdrop-blur-sm rounded-lg p-4 min-w-[120px]" variants={slideUp}>
                <div className="text-2xl font-bold text-white">
                  {formatNumber(processedData.totalReached)}
                </div>
                <div className="text-sm text-humdb-gray-200">Total People Reached</div>
              </motion.div>
              <motion.div className="bg-white bg-opacity-10 backdrop-blur-sm rounded-lg p-4 min-w-[120px]" variants={slideUp}>
                <div className="text-2xl font-bold text-white">
                  {stats.totalCountries}
                </div>
                <div className="text-sm text-humdb-gray-200">Countries</div>
              </motion.div>
              <motion.div className="bg-white bg-opacity-10 backdrop-blur-sm rounded-lg p-4 min-w-[120px]" variants={slideUp}>
                <div className="text-2xl font-bold text-white">
                  {stats.totalDataPoints}
                </div>
                <div className="text-sm text-humdb-gray-200">Data Points</div>
              </motion.div>
              <motion.div className="bg-white bg-opacity-10 backdrop-blur-sm rounded-lg p-4 min-w-[120px]" variants={slideUp}>
                <div className="text-2xl font-bold text-white">
                  {stats.totalSexCategories}
                </div>
                <div className="text-sm text-humdb-gray-200">Sex Categories</div>
              </motion.div>
              <motion.div className="bg-white bg-opacity-10 backdrop-blur-sm rounded-lg p-4 min-w-[120px]" variants={slideUp}>
                <div className="text-2xl font-bold text-white">
                  {stats.totalAgeGroups}
                </div>
                <div className="text-sm text-humdb-gray-200">Age Groups</div>
              </motion.div>
            </motion.div>
          )}
        </motion.div>
      </section>

      {/* Filters Section */}
      <section className="bg-humdb-gray-50 py-8">
        <div className="w-full px-6 sm:px-8 lg:px-12">
          <motion.div
            className="bg-white rounded-xl shadow-lg overflow-hidden"
            variants={slideUp}
            initial="hidden"
            animate="visible"
          >
            <div className="px-6 py-4 border-b border-humdb-gray-200">
              <button
                onClick={() => setExpandedFilters(!expandedFilters)}
                className="flex items-center justify-between w-full text-left"
              >
                <h2 className="text-xl font-bold text-humdb-navy">Filters & Analysis Options</h2>
                <motion.div
                  animate={{ rotate: expandedFilters ? 180 : 0 }}
                  transition={{ duration: 0.2 }}
                >
                  <svg className="w-5 h-5 text-humdb-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
                        <label className="block text-sm font-semibold text-humdb-gray-700 mb-3">
                          Countries
                        </label>
                        <select
                          multiple
                          size="4"
                          className="w-full p-3 border border-humdb-gray-300 rounded-lg focus:ring-2 focus:ring-humdb-red focus:border-transparent"
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
                        <p className="text-xs text-humdb-gray-500 mt-1">Hold Ctrl/Cmd to select multiple</p>
                      </div>

                      {/* Period Filter */}
                      <div>
                        <label className="block text-sm font-semibold text-humdb-gray-700 mb-3">
                          Period
                        </label>
                        <select
                          className="w-full p-3 border border-humdb-gray-300 rounded-lg focus:ring-2 focus:ring-humdb-red focus:border-transparent"
                          value={filters.selectedPeriod}
                          onChange={(e) => setFilters(prev => ({ ...prev, selectedPeriod: e.target.value }))}
                        >
                          <option value="">All Periods</option>
                          {filters.periods.map(period => (
                            <option key={period} value={period}>{period}</option>
                          ))}
                        </select>
                      </div>

                      {/* Indicator Filter */}
                      <div>
                        <label className="block text-sm font-semibold text-humdb-gray-700 mb-3">
                          Indicator
                        </label>
                        <select
                          className="w-full p-3 border border-humdb-gray-300 rounded-lg focus:ring-2 focus:ring-humdb-red focus:border-transparent"
                          value={filters.selectedIndicator}
                          onChange={(e) => setFilters(prev => ({ ...prev, selectedIndicator: e.target.value }))}
                        >
                          <option value="">All Indicators</option>
                          {filters.indicators.map(indicator => (
                            <option key={indicator.id} value={indicator.id}>{indicator.name}</option>
                          ))}
                        </select>
                      </div>

                      {/* Chart Type */}
                      <div>
                        <label className="block text-sm font-semibold text-humdb-gray-700 mb-3">
                          Chart Type
                        </label>
                        <select
                          className="w-full p-3 border border-humdb-gray-300 rounded-lg focus:ring-2 focus:ring-humdb-red focus:border-transparent"
                          value={chartType}
                          onChange={(e) => setChartType(e.target.value)}
                        >
                          <option value="bar">Bar Chart</option>
                          <option value="pie">Pie Chart</option>
                          <option value="line">Line Chart</option>
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
                        className="px-4 py-2 bg-humdb-gray-200 text-humdb-gray-700 rounded-lg hover:bg-humdb-gray-300 transition-colors font-medium"
                      >
                        Clear Filters
                      </button>
                      <button
                        onClick={fetchData}
                        className="px-4 py-2 bg-humdb-red text-white rounded-lg hover:bg-humdb-red-dark transition-colors font-medium"
                        disabled={isLoading}
                      >
                        {isLoading ? 'Loading...' : 'Refresh Data'}
                      </button>
                      <div className="flex-1"></div>
                      <div className="text-sm text-humdb-gray-600 flex items-center">
                        <span className="inline-block w-2 h-2 bg-green-400 rounded-full mr-2"></span>
                        {rawData.filter(item => item.disaggregation_data).length} disaggregated records found
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
      <section className="bg-white border-b border-humdb-gray-200 sticky top-20 z-40">
        <div className="w-full px-6 sm:px-8 lg:px-12">
          <div className="flex space-x-1 overflow-x-auto">
            {[
              { id: 'overview', label: 'Overview', icon: '📊' },
              { id: 'by-sex', label: 'By Sex', icon: '👥' },
              { id: 'by-age', label: 'By Age', icon: '👶👴' },
              { id: 'by-sex-age', label: 'Sex & Age', icon: '📈' },
              { id: 'by-country', label: 'Countries', icon: '🌍' },
              { id: 'trends', label: 'Trends', icon: '📅' }
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`py-4 px-4 font-semibold border-b-2 transition-all duration-200 whitespace-nowrap flex items-center space-x-2 ${
                  activeTab === tab.id
                    ? 'text-humdb-red border-humdb-red bg-humdb-red bg-opacity-5'
                    : 'text-humdb-gray-600 border-transparent hover:text-humdb-red hover:border-humdb-red hover:border-opacity-50'
                }`}
              >
                <span>{tab.icon}</span>
                <span>{tab.label}</span>
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* Content Section */}
      <section className="py-16 bg-humdb-gray-50 min-h-screen">
        <div className="w-full px-6 sm:px-8 lg:px-12">
          {isLoading ? (
            <div className="text-center py-20">
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
                className="w-16 h-16 border-4 border-humdb-red border-t-transparent rounded-full mx-auto mb-4"
              ></motion.div>
              <p className="text-humdb-gray-600 text-lg">Loading disaggregated data...</p>
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
                      <h3 className="text-xl font-bold text-humdb-navy mb-6 flex items-center">
                        <span className="mr-2">🏆</span>
                        Top Countries by People Reached
                      </h3>
                      {processedData.byCountry.length > 0 ? (
                        <MultiChart
                          data={processedData.byCountry.slice(0, 8)}
                          type={chartType}
                          title=""
                          height={350}
                        />
                      ) : (
                        <div className="text-center py-12">
                          <div className="text-6xl mb-4">📊</div>
                          <p className="text-humdb-gray-500">No data available</p>
                        </div>
                      )}
                    </div>

                    <div className="bg-white rounded-xl shadow-lg p-6">
                      <h3 className="text-xl font-bold text-humdb-navy mb-6 flex items-center">
                        <span className="mr-2">⚖️</span>
                        Distribution by Sex
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
                          <div className="text-6xl mb-4">📊</div>
                          <p className="text-humdb-gray-500">No data available</p>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* By Sex Tab */}
                {activeTab === 'by-sex' && (
                  <div className="bg-white rounded-xl shadow-lg p-8">
                    <h3 className="text-2xl font-bold text-humdb-navy mb-8 flex items-center">
                      <span className="mr-3">👥</span>
                      People Reached by Sex
                    </h3>
                    {processedData.bySex.length > 0 ? (
                      <MultiChart
                        data={processedData.bySex}
                        type={chartType}
                        title="Distribution by Sex"
                        height={450}
                      />
                    ) : (
                      <div className="text-center py-16">
                        <div className="text-8xl mb-6">👥</div>
                        <p className="text-humdb-gray-500 text-lg">No sex-disaggregated data available</p>
                      </div>
                    )}
                  </div>
                )}

                {/* By Age Tab */}
                {activeTab === 'by-age' && (
                  <div className="bg-white rounded-xl shadow-lg p-8">
                    <h3 className="text-2xl font-bold text-humdb-navy mb-8 flex items-center">
                      <span className="mr-3">👶👴</span>
                      People Reached by Age Group
                    </h3>
                    {processedData.byAge.length > 0 ? (
                      <MultiChart
                        data={processedData.byAge}
                        type={chartType}
                        title="Distribution by Age Group"
                        height={450}
                      />
                    ) : (
                      <div className="text-center py-16">
                        <div className="text-8xl mb-6">👶👴</div>
                        <p className="text-humdb-gray-500 text-lg">No age-disaggregated data available</p>
                      </div>
                    )}
                  </div>
                )}

                {/* By Sex & Age Tab */}
                {activeTab === 'by-sex-age' && (
                  <div className="bg-white rounded-xl shadow-lg p-8">
                    <h3 className="text-2xl font-bold text-humdb-navy mb-8 flex items-center">
                      <span className="mr-3">📈</span>
                      People Reached by Sex and Age
                    </h3>
                    {processedData.bySexAge.length > 0 ? (
                      <MultiChart
                        data={processedData.bySexAge}
                        type={chartType}
                        title="Distribution by Sex and Age Groups"
                        height={450}
                      />
                    ) : (
                      <div className="text-center py-16">
                        <div className="text-8xl mb-6">📈</div>
                        <p className="text-humdb-gray-500 text-lg">No sex-age disaggregated data available</p>
                      </div>
                    )}
                  </div>
                )}

                {/* By Country Tab */}
                {activeTab === 'by-country' && (
                  <div className="bg-white rounded-xl shadow-lg p-8">
                    <h3 className="text-2xl font-bold text-humdb-navy mb-8 flex items-center">
                      <span className="mr-3">🌍</span>
                      People Reached by Country
                    </h3>
                    {processedData.byCountry.length > 0 ? (
                      <MultiChart
                        data={processedData.byCountry}
                        type={chartType}
                        title="Distribution by Country"
                        height={450}
                      />
                    ) : (
                      <div className="text-center py-16">
                        <div className="text-8xl mb-6">🌍</div>
                        <p className="text-humdb-gray-500 text-lg">No country data available</p>
                      </div>
                    )}
                  </div>
                )}

                {/* Trends Tab */}
                {activeTab === 'trends' && (
                  <div className="bg-white rounded-xl shadow-lg p-8">
                    <h3 className="text-2xl font-bold text-humdb-navy mb-8 flex items-center">
                      <span className="mr-3">📅</span>
                      Trends Over Time
                    </h3>
                    {processedData.trends.length > 0 ? (
                      <MultiChart
                        data={processedData.trends}
                        type="line"
                        title="People Reached Over Time"
                        height={450}
                      />
                    ) : (
                      <div className="text-center py-16">
                        <div className="text-8xl mb-6">📅</div>
                        <p className="text-humdb-gray-500 text-lg">No trend data available</p>
                      </div>
                    )}
                  </div>
                )}
              </motion.div>
            </AnimatePresence>
          )}
        </div>
      </section>

      {/* Data Summary Section */}
      <section className="bg-white py-16 border-t border-humdb-gray-200">
        <div className="w-full px-6 sm:px-8 lg:px-12">
          <div className="text-center mb-12">
            <h2 className="text-3xl font-bold text-humdb-navy mb-4">Data Summary</h2>
            <p className="text-humdb-gray-600 max-w-2xl mx-auto">
              Comprehensive overview of people reached across all disaggregated categories and regions
            </p>
          </div>
          <motion.div
            className="grid grid-cols-2 md:grid-cols-5 gap-6"
            variants={staggerContainer}
            initial="hidden"
            animate="visible"
          >
            <motion.div className="bg-gradient-to-br from-humdb-red to-humdb-red-dark rounded-xl p-6 text-white text-center" variants={slideUp}>
              <div className="text-3xl font-bold mb-2">
                {formatNumber(processedData.totalReached)}
              </div>
              <div className="text-sm opacity-90">Total People Reached</div>
            </motion.div>
            <motion.div className="bg-gradient-to-br from-blue-500 to-blue-600 rounded-xl p-6 text-white text-center" variants={slideUp}>
              <div className="text-3xl font-bold mb-2">
                {stats.totalCountries}
              </div>
              <div className="text-sm opacity-90">Countries</div>
            </motion.div>
            <motion.div className="bg-gradient-to-br from-green-500 to-green-600 rounded-xl p-6 text-white text-center" variants={slideUp}>
              <div className="text-3xl font-bold mb-2">
                {stats.totalSexCategories}
              </div>
              <div className="text-sm opacity-90">Sex Categories</div>
            </motion.div>
            <motion.div className="bg-gradient-to-br from-purple-500 to-purple-600 rounded-xl p-6 text-white text-center" variants={slideUp}>
              <div className="text-3xl font-bold mb-2">
                {stats.totalAgeGroups}
              </div>
              <div className="text-sm opacity-90">Age Groups</div>
            </motion.div>
            <motion.div className="bg-gradient-to-br from-orange-500 to-orange-600 rounded-xl p-6 text-white text-center" variants={slideUp}>
              <div className="text-3xl font-bold mb-2">
                {formatNumber(stats.avgPerCountry)}
              </div>
              <div className="text-sm opacity-90">Average per Country</div>
            </motion.div>
          </motion.div>
        </div>
      </section>
    </>
  );
}
