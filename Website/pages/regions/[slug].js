import { useRouter } from 'next/router';
import { useState, useEffect } from 'react';
import { useTranslation } from '../../lib/useTranslation';
import { getCountriesList } from '../../lib/apiService';

// Add static generation to prevent build-time errors
export async function getStaticPaths() {
  try {
    const countries = await getCountriesList();

    // Get unique regions from countries data
    const regions = [...new Set(countries.map(country => country.region_localized || country.region))];

    // Create slugs for each region
    const regionSlugMap = {
      'Africa': 'africa',
      'Americas': 'americas',
      'Asia Pacific': 'asia-pacific',
      'Europe and Central Asia': 'europe-and-central-asia',
      'MENA': 'mena',
      'Middle East and North Africa': 'middle-east-and-north-africa'
    };

    const paths = regions
      .filter(region => regionSlugMap[region]) // Only include mapped regions
      .map(region => ({
        params: { slug: regionSlugMap[region] }
      }));

    return {
      paths,
      fallback: 'blocking'
    };
  } catch (error) {
    console.error('Failed to generate static paths for regions:', error);
    return {
      paths: [],
      fallback: 'blocking'
    };
  }
}

export async function getStaticProps({ params }) {
  try {
    const countries = await getCountriesList();

    // Map URL slugs to region names
    const regionSlugMap = {
      'africa': 'Africa',
      'americas': 'Americas',
      'asia-pacific': 'Asia Pacific',
      'europe-and-central-asia': 'Europe and Central Asia',
      'mena': 'MENA',
      'middle-east-and-north-africa': 'Middle East and North Africa'
    };

    const region = regionSlugMap[params.slug];
    if (!region) {
      return {
        notFound: true
      };
    }

    // Filter countries by region
    const regionCountries = countries.filter(country => {
      const countryRegion = country.region_localized || country.region;
      return countryRegion === region;
    });

    return {
      props: {
        regionName: region,
        initialCountries: regionCountries,
        error: null
      },
      revalidate: 3600 // Revalidate every hour
    };
  } catch (error) {
    console.error('Failed to fetch region data:', error);
    return {
      props: {
        regionName: null,
        initialCountries: [],
        error: 'Failed to load region data'
      },
      revalidate: 3600
    };
  }
}

export default function RegionOverview({ regionName: initialRegionName, initialCountries, error: initialError }) {
  const router = useRouter();
  const { slug } = router.query;
  const { t, locale } = useTranslation();
  const [countries, setCountries] = useState(initialCountries || []);
  const [loading, setLoading] = useState(!initialCountries);
  const [regionName, setRegionName] = useState(initialRegionName || '');
  const [error, setError] = useState(initialError);

  // Map URL slugs to region names
  const regionSlugMap = {
    'africa': 'Africa',
    'americas': 'Americas',
    'asia-pacific': 'Asia Pacific',
    'europe-and-central-asia': 'Europe and Central Asia',
    'mena': 'MENA',
    'middle-east-and-north-africa': 'Middle East and North Africa'
  };

  useEffect(() => {
    // If we already have data from getStaticProps, don't refetch
    if (initialCountries && initialRegionName) {
      return;
    }

    if (slug) {
      const region = regionSlugMap[slug] || slug;
      setRegionName(region);

      const fetchCountries = async () => {
        try {
          setLoading(true);
          const countriesData = await getCountriesList(locale || 'en');

          // Filter countries by region
          const regionCountries = countriesData.filter(country => {
            const countryRegion = country.region_localized || country.region;
            return countryRegion === region;
          });

          setCountries(regionCountries);
        } catch (error) {
          console.error('Failed to fetch countries:', error);
          setError(t('errors.failedToLoadRegionData'));
        } finally {
          setLoading(false);
        }
      };

      fetchCountries();
    }
  }, [slug, locale, initialCountries, initialRegionName]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 py-8">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-ngodb-red"></div>
            <span className="ml-2 text-gray-600">{t('common.loading')}</span>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 py-8">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center">
            <h1 className="text-2xl font-bold text-gray-900">{t('regions.error')}</h1>
            <p className="mt-2 text-gray-600">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  if (!regionName) {
    return (
      <div className="min-h-screen bg-gray-50 py-8">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center">
            <h1 className="text-2xl font-bold text-gray-900">{t('regions.notFound')}</h1>
            <p className="mt-2 text-gray-600">{t('regions.regionNotFound')}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-8">
          <nav className="flex" aria-label="Breadcrumb">
            <ol className="flex items-center space-x-4">
              <li>
                <div>
                  <a href="/" className="text-gray-400 hover:text-gray-500">
                    {t('navigation.home')}
                  </a>
                </div>
              </li>
              <li>
                <div className="flex items-center">
                  <svg className="flex-shrink-0 h-5 w-5 text-gray-300" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clipRule="evenodd" />
                  </svg>
                  <a href="/countries" className="ml-4 text-sm font-medium text-gray-500 hover:text-gray-700">
                    {t('navigation.countries')}
                  </a>
                </div>
              </li>
              <li>
                <div className="flex items-center">
                  <svg className="flex-shrink-0 h-5 w-5 text-gray-300" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clipRule="evenodd" />
                  </svg>
                  <span className="ml-4 text-sm font-medium text-gray-900">{regionName}</span>
                </div>
              </li>
            </ol>
          </nav>

          <div className="mt-6">
            <h1 className="text-3xl font-bold text-gray-900">{regionName}</h1>
            <p className="mt-2 text-lg text-gray-600">
              {t('regions.overview', { region: regionName, count: countries.length })}
            </p>
          </div>
        </div>

        {/* Region Stats */}
        <div className="bg-white overflow-hidden shadow rounded-lg mb-8">
          <div className="px-4 py-5 sm:p-6">
            <dl className="grid grid-cols-1 gap-5 sm:grid-cols-3">
              <div className="px-4 py-5 bg-gray-50 rounded-lg overflow-hidden sm:p-6">
                <dt className="text-sm font-medium text-gray-500 truncate">
                  {t('regions.totalCountries')}
                </dt>
                <dd className="mt-1 text-3xl font-semibold text-gray-900">
                  {countries.length}
                </dd>
              </div>
              <div className="px-4 py-5 bg-gray-50 rounded-lg overflow-hidden sm:p-6">
                <dt className="text-sm font-medium text-gray-500 truncate">
                  {t('regions.nationalSocieties')}
                </dt>
                <dd className="mt-1 text-3xl font-semibold text-gray-900">
                  {countries.filter(c => c.national_society_name).length}
                </dd>
              </div>
              <div className="px-4 py-5 bg-gray-50 rounded-lg overflow-hidden sm:p-6">
                <dt className="text-sm font-medium text-gray-500 truncate">
                  {t('regions.region')}
                </dt>
                <dd className="mt-1 text-3xl font-semibold text-gray-900">
                  {regionName}
                </dd>
              </div>
            </dl>
          </div>
        </div>

        {/* Countries Grid */}
        <div className="bg-white shadow overflow-hidden sm:rounded-md">
          <div className="px-4 py-5 sm:px-6 border-b border-gray-200">
            <h3 className="text-lg leading-6 font-medium text-gray-900">
              {t('regions.countriesInRegion', { region: regionName })}
            </h3>
          </div>
          <ul className="divide-y divide-gray-200">
            {countries.map((country, index) => (
              <li key={country.iso3 || index}>
                <a
                  href={`/countries/${country.iso3?.toLowerCase()}`}
                  className="block hover:bg-gray-50 transition-colors duration-150 ease-in-out"
                >
                  <div className="px-4 py-4 sm:px-6">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center">
                        <div className="flex-shrink-0">
                          <div className="h-10 w-10 rounded-full bg-ngodb-red flex items-center justify-center">
                            <span className="text-white font-semibold text-sm">
                              {country.iso3 || country.name?.charAt(0)}
                            </span>
                          </div>
                        </div>
                        <div className="ml-4">
                          <div className="text-sm font-medium text-gray-900">
                            {country.name}
                          </div>
                          {country.national_society_name && (
                            <div className="text-sm text-gray-500">
                              {country.national_society_name}
                            </div>
                          )}
                        </div>
                      </div>
                      <div className="flex-shrink-0">
                        <svg className="h-5 w-5 text-gray-400" fill="currentColor" viewBox="0 0 20 20">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
                        </svg>
                      </div>
                    </div>
                  </div>
                </a>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
