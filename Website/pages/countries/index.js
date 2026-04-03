// pages/countries/index.js
import Head from 'next/head';
import Link from 'next/link';
import { useState, useEffect } from 'react';
import { useTranslation } from '../../lib/useTranslation';
import { getCountriesList } from '../../lib/apiService';

export async function getStaticProps() {
  try {
    const countries = await getCountriesList();
    return {
      props: {
        countries: countries || [],
        error: null
      },
      revalidate: 3600 // Revalidate every hour
    };
  } catch (error) {
    console.error('Failed to fetch countries:', error);
    return {
      props: {
        countries: [],
        error: 'Failed to load countries list'
      },
      revalidate: 3600
    };
  }
}

export default function CountriesListPage({ countries: initialCountries, error: initialError }) {
  const { t } = useTranslation();
  const [countries, setCountries] = useState(initialCountries || []);
  const [loading, setLoading] = useState(!initialCountries);
  const [error, setError] = useState(initialError);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedRegion, setSelectedRegion] = useState('all');

  // Get unique regions
  const regions = ['all', ...new Set(countries.map(c => c.region).filter(Boolean))];

  // Filter countries based on search and region
  const filteredCountries = countries.filter(country => {
    const matchesSearch = !searchTerm ||
      country.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      country.national_society_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      country.iso3?.toLowerCase().includes(searchTerm.toLowerCase());

    const matchesRegion = selectedRegion === 'all' || country.region === selectedRegion;

    return matchesSearch && matchesRegion;
  });

  // Sort countries alphabetically by name
  const sortedCountries = [...filteredCountries].sort((a, b) => {
    const nameA = a.name || '';
    const nameB = b.name || '';
    return nameA.localeCompare(nameB);
  });

  // Load countries on client side if not available from static props
  useEffect(() => {
    if (!initialCountries && !loading) {
      setLoading(true);
      getCountriesList()
        .then(data => {
          setCountries(data || []);
          setError(null);
        })
        .catch(err => {
          console.error('Failed to fetch countries:', err);
          setError(t('errors.failedToLoadCountriesList'));
        })
        .finally(() => {
          setLoading(false);
        });
    }
  }, [initialCountries, loading]);

  return (
    <>
      <Head>
        <title>{`${t('navigation.countries')} - NGO Databank`}</title>
        <meta name="description" content="Browse all countries in the NGO Databank. Explore country profiles, indicators, and data." />
      </Head>

      <div className="min-h-screen bg-gradient-to-br from-ngodb-gray-50 to-ngodb-gray-100">
        <div className="w-full px-6 sm:px-8 lg:px-12 py-12">
          {/* Header */}
          <div className="text-center mb-12">
            <h1 className="text-4xl sm:text-5xl font-extrabold text-ngodb-navy mb-4">
              {t('navigation.countries')}
            </h1>
            <p className="text-lg text-ngodb-gray-600 max-w-2xl mx-auto">
              {t('countriesList.description', { default: 'Explore country profiles, indicators, and data from National Societies around the world.' })}
            </p>
          </div>

          {/* Filters */}
          <div className="bg-white rounded-xl shadow-lg p-6 mb-8">
            <div className="flex flex-col sm:flex-row gap-4">
              {/* Search */}
              <div className="flex-1 relative">
                <input
                  type="text"
                  placeholder={t('countriesList.searchPlaceholder', { default: 'Search countries...' })}
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full pl-10 pr-4 py-2 border border-ngodb-gray-300 rounded-lg focus:ring-2 focus:ring-ngodb-red focus:border-transparent"
                />
                <svg
                  className="absolute left-3 top-2.5 w-5 h-5 text-ngodb-gray-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </div>

              {/* Region Filter */}
              <div className="sm:w-64">
                <select
                  value={selectedRegion}
                  onChange={(e) => setSelectedRegion(e.target.value)}
                  className="w-full px-4 py-2 border border-ngodb-gray-300 rounded-lg focus:ring-2 focus:ring-ngodb-red focus:border-transparent"
                >
                  <option value="all">{t('countriesList.allRegions', { default: 'All Regions' })}</option>
                  {regions.filter(r => r !== 'all').map(region => (
                    <option key={region} value={region}>{region}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* Results count */}
            <div className="mt-4 text-sm text-ngodb-gray-600">
              {t('countriesList.showing', {
                default: 'Showing {count} of {total} countries',
                count: sortedCountries.length,
                total: countries.length
              })}
            </div>
          </div>

          {/* Loading State */}
          {loading && (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-ngodb-red"></div>
              <span className="ml-3 text-ngodb-gray-600">{t('countriesList.loading', { default: 'Loading countries...' })}</span>
            </div>
          )}

          {/* Error State */}
          {error && !loading && (
            <div className="bg-yellow-50 border-l-4 border-yellow-400 p-4 rounded-lg mb-8">
              <div className="flex">
                <div className="flex-shrink-0">
                  <svg className="h-5 w-5 text-yellow-400" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                  </svg>
                </div>
                <div className="ml-3">
                  <p className="text-sm text-yellow-700">{error}</p>
                </div>
              </div>
            </div>
          )}

          {/* Countries Grid */}
          {!loading && !error && (
            <>
              {sortedCountries.length > 0 ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
                  {sortedCountries.map((country) => (
                    <Link
                      key={country.id || country.iso3}
                      href={`/countries/${country.iso3?.toUpperCase() || country.iso3}`}
                      className="bg-white rounded-xl shadow-md hover:shadow-xl transition-all duration-300 overflow-hidden border border-ngodb-gray-200 hover:border-ngodb-red group"
                    >
                      {/* Flag */}
                      <div className="h-32 bg-gradient-to-br from-ngodb-navy to-ngodb-red flex items-center justify-center relative overflow-hidden">
                        {country.iso2 ? (
                          <img
                            src={`/flags/${country.iso2.toLowerCase()}.svg`}
                            alt={`${country.name} flag`}
                            className="w-20 h-20 object-contain"
                            onError={(e) => {
                              e.target.style.display = 'none';
                            }}
                          />
                        ) : (
                          <div className="w-20 h-20 bg-white bg-opacity-20 rounded-full flex items-center justify-center">
                            <svg className="w-12 h-12 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                          </div>
                        )}
                        <div className="absolute inset-0 bg-black bg-opacity-0 group-hover:bg-opacity-10 transition-opacity duration-300"></div>
                      </div>

                      {/* Content */}
                      <div className="p-4">
                        <h3 className="text-lg font-bold text-ngodb-navy mb-1 group-hover:text-ngodb-red transition-colors line-clamp-2">
                          {country.name}
                        </h3>
                        {country.national_society_name && (
                          <p className="text-sm text-ngodb-gray-600 mb-2 line-clamp-2">
                            {country.national_society_name}
                          </p>
                        )}
                        {country.region && (
                          <p className="text-xs text-ngodb-gray-500">
                            {country.region}
                          </p>
                        )}
                      </div>

                      {/* Hover Arrow */}
                      <div className="px-4 pb-4">
                        <div className="flex items-center text-ngodb-red opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                          <span className="text-sm font-medium mr-2">
                            {t('countriesList.viewProfile', { default: 'View Profile' })}
                          </span>
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                          </svg>
                        </div>
                      </div>
                    </Link>
                  ))}
                </div>
              ) : (
                <div className="text-center py-12 bg-white rounded-xl shadow-lg">
                  <svg className="w-16 h-16 text-ngodb-gray-400 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <p className="text-lg text-ngodb-gray-600 mb-2">
                    {t('countriesList.noCountriesFound', { default: 'No countries found' })}
                  </p>
                  <p className="text-sm text-ngodb-gray-500">
                    {t('countriesList.tryDifferentSearch', { default: 'Try adjusting your search or filter criteria' })}
                  </p>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}
