import { useState, useMemo, forwardRef } from 'react';
import Link from 'next/link';
import { useTranslation } from '../../lib/useTranslation';
import { normalizeRegionName, regionNameToTranslationKey, regionToSlug } from '../../lib/regionUtils';
import { TranslationSafe } from '../ClientOnly';

const CountriesDropdown = forwardRef(({ countries, loading, onClose }, ref) => {
  const { t, isLoaded } = useTranslation();

  const [selectedRegion, setSelectedRegion] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');

  const getRegionLabel = (regionName) => {
    const key = regionNameToTranslationKey(regionName);
    if (!key) return regionName;
    return t(key, { defaultValue: regionName });
  };

  // Group countries by region
  const regionsWithCountries = useMemo(() => {
    if (!countries || countries.length === 0) return [];

    const groups = countries.reduce((acc, country) => {
      // Use a canonical region for grouping/routing; UI label is localized separately.
      const region = normalizeRegionName(country.region || 'Other');
      if (!acc[region]) acc[region] = [];
      acc[region].push(country);
      return acc;
    }, {});

    // Sort regions and countries alphabetically
    return Object.entries(groups)
      .map(([region, items]) => [region, items.sort((a, b) => (a.name || '').localeCompare(b.name || ''))])
      .sort((a, b) => a[0].localeCompare(b[0]));
  }, [countries]);

  // Set first region as selected by default
  useMemo(() => {
    if (regionsWithCountries.length > 0 && !selectedRegion) {
      setSelectedRegion(regionsWithCountries[0][0]);
    }
  }, [regionsWithCountries, selectedRegion]);

  // Get countries for selected region
  const selectedRegionCountries = useMemo(() => {
    if (!selectedRegion) return [];
    const regionEntry = regionsWithCountries.find(([region]) => region === selectedRegion);
    return regionEntry ? regionEntry[1] : [];
  }, [regionsWithCountries, selectedRegion]);

  // Filter countries based on search query
  const filteredCountries = useMemo(() => {
    if (!searchQuery.trim()) {
      // No search query - show countries from selected region only
      return selectedRegionCountries;
    }

    // Search query exists - search across all countries
    const query = searchQuery.toLowerCase();
    return countries.filter(country =>
      country.name?.toLowerCase().includes(query) ||
      country.national_society_name?.toLowerCase().includes(query)
    );
  }, [selectedRegionCountries, searchQuery, countries]);

  if (loading) {
    return (
      <div
        ref={ref}
        className="absolute top-full -left-32 mt-1 w-[50rem] bg-white border border-gray-300 rounded-md shadow-lg z-50"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-4">
          <div className="flex items-center justify-center">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-humdb-red"></div>
            <span className="ml-2 text-gray-600">
              <TranslationSafe fallback="Loading countries...">
                {t('countries.loading.title')}
              </TranslationSafe>
            </span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={ref}
      className="absolute top-full left-0 sm:-left-32 mt-1 bg-white border border-gray-300 rounded-md shadow-lg z-50 sm:w-[50rem] sm:ml-0 mobile-full-width"
      style={{
        width: window.innerWidth <= 640 ? 'calc(100vw - 2rem)' : undefined,
        left: window.innerWidth <= 640 ? '1rem' : undefined,
        right: window.innerWidth <= 640 ? '1rem' : undefined,
        maxWidth: window.innerWidth <= 640 ? 'calc(100vw - 2rem)' : undefined
      }}
      onClick={(e) => e.stopPropagation()}
      data-countries-dropdown
    >
      <div className="flex flex-col sm:flex-row h-auto sm:h-96 max-h-96" onClick={(e) => e.stopPropagation()}>
        {/* Regions List - Left Side */}
        <div className="w-full sm:w-1/4 border-b sm:border-b-0 sm:border-r border-gray-300 overflow-y-auto max-h-48 sm:max-h-none" onClick={(e) => e.stopPropagation()}>
          <div className="p-3 border-b border-gray-300">
            <h3 className="text-sm font-semibold text-gray-800">
              <TranslationSafe fallback="Regions">
                {t('countries.regions')}
              </TranslationSafe>
            </h3>
          </div>
          {/* Mobile: Horizontal layout */}
          <div className="py-1 sm:hidden">
            <div className="flex flex-wrap gap-1 px-4">
              {regionsWithCountries.map(([region, countriesInRegion]) => (
                <button
                  key={region}
                  onClick={() => setSelectedRegion(region)}
                  className={`px-2 py-1 text-xs font-medium rounded transition-colors duration-150 ease-in-out
                    ${
                      selectedRegion === region
                        ? 'bg-humdb-red text-white'
                        : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                    }`}
                >
                  {getRegionLabel(region)}
                </button>
              ))}
            </div>
          </div>
          {/* Desktop: Vertical layout */}
          <div className="py-1 hidden sm:block">
            {regionsWithCountries.map(([region, countriesInRegion]) => (
              <button
                key={region}
                onClick={() => setSelectedRegion(region)}
                className={`w-full text-left px-3 py-2 text-sm transition-colors duration-150 ease-in-out
                  ${
                    selectedRegion === region
                      ? 'bg-humdb-red text-white'
                      : 'text-gray-700 hover:bg-gray-100'
                  }`}
              >
                <div className="font-medium">{getRegionLabel(region)}</div>
                <div className="text-xs opacity-75">{countriesInRegion.length}
                  <TranslationSafe fallback=" countries">
                    {' '}{t('countries.countries')}
                  </TranslationSafe>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Countries List - Right Side */}
        <div className="w-full sm:w-3/4 flex flex-col max-h-64 sm:max-h-none" onClick={(e) => e.stopPropagation()}>
          {/* Header with region info and search */}
          <div className="p-3 border-b border-gray-300">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-semibold text-gray-800">
                {selectedRegion ? (
                  <Link
                    href={`/regions/${regionToSlug(selectedRegion)}`}
                    onClick={onClose}
                    className="text-humdb-red hover:text-humdb-red-dark transition-colors duration-150 ease-in-out cursor-pointer underline hover:no-underline"
                    title={t('regions.clickToViewOverview', { region: getRegionLabel(selectedRegion), defaultValue: 'Click to view overview' })}
                  >
                    <TranslationSafe fallback={`See ${getRegionLabel(selectedRegion)} Region Overview`}>
                      {t('regions.seeRegionOverview', { region: getRegionLabel(selectedRegion) })}
                    </TranslationSafe>
                  </Link>
                ) : (
                  <TranslationSafe fallback="Select a region">
                    {t('countries.selectRegion')}
                  </TranslationSafe>
                )}
              </h3>
            </div>
            <input
              type="text"
              placeholder={t('countries.search.placeholder', { defaultValue: 'Search countries...' })}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full px-3 py-2 text-sm text-gray-900 border border-gray-300 rounded-md focus:ring-2 focus:ring-humdb-red focus:border-humdb-red"
            />
          </div>

          {/* Countries List */}
          <div className="flex-1 overflow-y-auto p-2 px-4 sm:px-2">
            {filteredCountries.length > 0 ? (
              <div className="grid grid-cols-2 sm:grid-cols-2 gap-2 divide-x divide-gray-200">
                {filteredCountries.map((country) => (
                  <Link
                    key={country.iso3}
                    href={`/countries/${country.iso3}`}
                    onClick={onClose}
                    className="block px-2 py-1.5 text-sm text-gray-700 hover:bg-gray-100 rounded transition-colors duration-150 ease-in-out"
                    title={`View profile for ${country.name}`}
                    prefetch={true}
                  >
                    <div className="font-medium">{country.name}</div>
                    {country.national_society_name && (
                      <div className="text-xs text-gray-500 truncate hidden sm:block">
                        {country.national_society_name}
                      </div>
                    )}
                  </Link>
                ))}
              </div>
            ) : (
              <div className="text-center py-8">
                <p className="text-gray-500 text-sm">
                  {searchQuery.trim() ?
                    <TranslationSafe fallback="No countries found">
                      {t('countries.search.noResults')}
                    </TranslationSafe> :
                    <TranslationSafe fallback="No countries available">
                      {t('countries.noCountries')}
                    </TranslationSafe>
                  }
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
});

export default CountriesDropdown;
