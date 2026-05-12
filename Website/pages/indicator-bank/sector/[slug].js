import Head from 'next/head';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/router';
import { getIndicatorBank } from '../../../lib/apiService';
import Link from 'next/link';
import { useTranslation } from '../../../lib/useTranslation';
import { TranslationSafe } from '../../../components/ClientOnly';

export default function SectorIndicatorsPage() {
  const router = useRouter();
  const { slug } = router.query;
  const { t, isLoaded } = useTranslation();

  // State
  const [indicators, setIndicators] = useState([]);
  const [filterType, setFilterType] = useState('');
  const [filterValue, setFilterValue] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');

  // Fetch data when component mounts or slug changes
  useEffect(() => {
    if (!router.isReady || !slug) return;

    const fetchData = async () => {
      setLoading(true);
      setError(null);

      try {
        const [type, value] = slug.split('-');
        const searchQuery = router.query.search || '';

        setFilterType(type);
        setFilterValue(value);
        setSearchTerm(searchQuery);

        let data;
        if (type === 'sector') {
          data = await getIndicatorBank('', '', value, '', '', null);
        } else if (type === 'subsector') {
          data = await getIndicatorBank('', '', '', value, '', null);
        } else {
          throw new Error(t('sectorIndicators.error.invalidFilter'));
        }

        setIndicators(data.indicators || []);
      } catch (err) {
        console.error("Failed to fetch indicators:", err);
        setError(t('sectorIndicators.error.loadFailed'));
        setIndicators([]);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [router.isReady, slug, router.query.search]);

  // Function to handle search
  const handleSearch = (e) => {
    e.preventDefault();
    const queryParams = new URLSearchParams();
    if (searchTerm) queryParams.set('search', searchTerm);

    router.push(`/indicator-bank/sector/${router.query.slug}?${queryParams.toString()}`);
  };

  // Filter indicators by search term if provided
  const filteredIndicators = searchTerm ?
    indicators.filter(indicator =>
      indicator.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      indicator.definition?.toLowerCase().includes(searchTerm.toLowerCase())
    ) : indicators;

  // Prevent rendering until translations are loaded to avoid hydration mismatches
  if (!isLoaded) {
    return (
      <div className="w-full px-6 sm:px-8 lg:px-12 py-8">
        <Head>
          <title>{`${t('sectorIndicators.loading.title')} - Humanitarian Databank`}</title>
        </Head>
        <div className="text-center py-20">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-humdb-red mb-4"></div>
          <h1 className="text-3xl font-bold text-humdb-navy mb-2">
            <TranslationSafe fallback="Loading Sector Indicators">
              {t('sectorIndicators.loading.title')}
            </TranslationSafe>
          </h1>
          <p className="text-humdb-gray-600">
            <TranslationSafe fallback="Please wait while we fetch the sector data...">
              {t('sectorIndicators.loading.description')}
            </TranslationSafe>
          </p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="w-full px-6 sm:px-8 lg:px-12 py-8 text-center">
        <Head>
          <title>{`${t('sectorIndicators.error.title')} - Humanitarian Databank`}</title>
        </Head>
        <h1 className="text-3xl font-bold text-humdb-red mb-6">{t('sectorIndicators.error.title')}</h1>
        <p className="text-red-600 bg-red-100 p-4 rounded-md">{error}</p>
        <Link href="/indicator-bank" className="mt-4 inline-block text-humdb-red hover:underline">
          &larr; {t('sectorIndicators.backToBank')}
        </Link>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="w-full px-6 sm:px-8 lg:px-12 py-8">
        <Head>
          <title>{`${t('sectorIndicators.loading.title')} - Humanitarian Databank`}</title>
        </Head>
        <div className="text-center py-20">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-humdb-red mb-4"></div>
          <h1 className="text-3xl font-bold text-humdb-navy mb-2">{t('sectorIndicators.loading.title')}</h1>
          <p className="text-humdb-gray-600">{t('sectorIndicators.loading.description')}</p>
        </div>
      </div>
    );
  }

  const displayValue = filterValue.replace(/-/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

  return (
    <>
      <Head>
        <title>{`${t('sectorIndicators.hero.title', { displayValue })} - Humanitarian Databank`}</title>
        <meta name="description" content={`Browse ${displayValue} indicators from the indicator bank.`} />
      </Head>

      <div className="bg-humdb-gray-100 min-h-screen">
        <div className="w-full px-6 sm:px-8 lg:px-12 py-10">
          {/* Breadcrumb */}
          <nav className="mb-8">
            <div className="flex items-center space-x-2 text-sm text-humdb-gray-600">
              <Link href="/indicator-bank" className="hover:text-humdb-red">
                {t('sectorIndicators.breadcrumb.indicatorBank')}
              </Link>
              <span>&gt;</span>
              <span className="capitalize">{t(`sectorIndicators.breadcrumb.${filterType}`)}</span>
              <span>&gt;</span>
              <span className="text-humdb-navy font-medium">{displayValue}</span>
            </div>
          </nav>

          <div className="text-center mb-12">
            <h1 className="text-4xl sm:text-5xl font-extrabold text-humdb-navy mb-4">
              {t('sectorIndicators.hero.title', { displayValue })}
            </h1>
            <p className="text-lg text-humdb-gray-600 max-w-2xl mx-auto">
              {t('sectorIndicators.hero.description', { displayValue, filterType })}
            </p>
          </div>

          {/* Search Section */}
          <form onSubmit={handleSearch} className="mb-10 bg-white p-6 rounded-lg shadow-sm">
            <div className="flex gap-4">
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder={t('sectorIndicators.search.placeholder')}
                className="flex-1 px-4 py-3 border border-humdb-gray-300 rounded-md focus:ring-2 focus:ring-humdb-red focus:border-humdb-red"
              />
              <button
                type="submit"
                className="bg-humdb-red hover:bg-humdb-red-dark text-white font-semibold px-6 py-2 rounded-md transition-colors duration-150"
              >
                {t('sectorIndicators.search.button')}
              </button>
              {searchTerm && (
                <button
                  type="button"
                  onClick={() => {
                    setSearchTerm('');
                    router.push(`/indicator-bank/sector/${router.query.slug}`);
                  }}
                  className="bg-humdb-gray-300 hover:bg-humdb-gray-400 text-humdb-gray-700 font-semibold px-6 py-2 rounded-md transition-colors duration-150"
                >
                  {t('sectorIndicators.search.clear')}
                </button>
              )}
            </div>
          </form>

          {/* Results Count */}
          <div className="mb-6">
            <p className="text-humdb-gray-600">
              {filteredIndicators.length === 1
                ? t('sectorIndicators.results.showing', { count: filteredIndicators.length })
                : t('sectorIndicators.results.showingPlural', { count: filteredIndicators.length })
              }
              {searchTerm && t('sectorIndicators.results.matching', { searchTerm })}
            </p>
          </div>

          {/* Indicators List */}
          {filteredIndicators.length === 0 ? (
            <p className="text-center text-humdb-gray-600 text-lg py-10">
              {searchTerm ?
                t('sectorIndicators.results.noResults') :
                t('sectorIndicators.results.noIndicators', { displayValue, filterType })
              }
            </p>
          ) : (
            <div className="grid gap-6">
              {filteredIndicators.map((indicator) => (
                <Link key={indicator.id} href={`/indicator-bank/${indicator.id}`}>
                  <div className="bg-white p-6 rounded-lg shadow-sm border border-humdb-gray-200 hover:shadow-lg hover:border-humdb-red transition-all duration-150 cursor-pointer">
                    <div className="flex justify-between items-start mb-4">
                      <h3 className="text-xl font-semibold text-humdb-navy mb-2">
                        {String(indicator.name || '')}
                      </h3>
                      {indicator.archived && (
                        <span className="bg-yellow-100 text-yellow-800 text-xs font-medium px-2.5 py-0.5 rounded">
                          {t('sectorIndicators.indicator.archived')}
                        </span>
                      )}
                    </div>

                    {indicator.definition && (
                      <p className="text-humdb-gray-600 mb-4">
                        {String(indicator.definition)}
                      </p>
                    )}

                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                      {indicator.type && (
                        <div>
                          <span className="font-medium text-humdb-gray-700">{t('sectorIndicators.indicator.type')}:</span>
                          <p className="text-humdb-gray-600">{String(indicator.type)}</p>
                        </div>
                      )}
                      {indicator.unit && (
                        <div>
                          <span className="font-medium text-humdb-gray-700">{t('sectorIndicators.indicator.unit')}:</span>
                          <p className="text-humdb-gray-600">{String(indicator.unit)}</p>
                        </div>
                      )}
                      {indicator.sector && (
                        <div>
                          <span className="font-medium text-humdb-gray-700">{t('sectorIndicators.indicator.sector')}:</span>
                          <p className="text-humdb-gray-600">
                            {typeof indicator.sector === 'object' && indicator.sector !== null
                              ? String(indicator.sector.primary || indicator.sector.name || indicator.sector)
                              : String(indicator.sector)}
                          </p>
                        </div>
                      )}
                      {indicator.emergency !== null && indicator.emergency !== undefined && (
                        <div>
                          <span className="font-medium text-humdb-gray-700">{t('sectorIndicators.indicator.emergency')}:</span>
                          <p className="text-humdb-gray-600">{indicator.emergency ? t('common.yes') : t('common.no')}</p>
                        </div>
                      )}
                    </div>

                    {indicator.related_programs && Array.isArray(indicator.related_programs) && indicator.related_programs.length > 0 && (
                      <div className="mt-4">
                        <span className="font-medium text-humdb-gray-700 text-sm">{t('sectorIndicators.indicator.relatedPrograms')}:</span>
                        <div className="flex flex-wrap gap-2 mt-1">
                          {indicator.related_programs.map((program, index) => (
                            <span key={index} className="bg-humdb-gray-100 text-humdb-gray-700 text-xs px-2 py-1 rounded">
                              {typeof program === 'string' ? program :
                               typeof program === 'object' && program !== null ?
                                 (String(program.primary || program.name || t('fallbacks.unknownProgram'))) :
                                 String(program || t('fallbacks.unknownProgram'))}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
