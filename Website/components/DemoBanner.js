// components/DemoBanner.js
import React, { useEffect, useMemo, useState } from 'react';
import { useScope } from './scope/ScopeContext';
import { HydrationSafe } from './ClientOnly';
import { getCountriesList } from '../lib/apiService';
import { useTranslation } from '../lib/useTranslation';

export default function DemoBanner() {
  const {
    isDemoMode,
    scope,
    setScope,
    countryIso2,
    setCountryName,
    setNationalSocietyName,
    setCountryIso3,
  } = useScope();

  const { locale, t } = useTranslation();

  const [countries, setCountries] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    if (!isDemoMode) return;
    let mounted = true;
    const load = async () => {
      try {
        setLoading(true);
        const list = await getCountriesList(locale || 'en');
        if (!mounted) return;
        setCountries(Array.isArray(list) ? list : []);
      } catch (_e) {
        if (!mounted) return;
        setCountries([]);
      } finally {
        if (!mounted) return;
        setLoading(false);
      }
    };
    load();
    return () => {
      mounted = false;
    };
  }, [isDemoMode, locale]);

  const options = useMemo(() => {
    const items = (countries || [])
      .filter((c) => c && c.iso2)
      .map((c) => ({
        iso2: String(c.iso2).toUpperCase(),
        iso3: c.iso3 ? String(c.iso3).toUpperCase() : null,
        countryName: c.name || String(c.iso2).toUpperCase(),
        nationalSocietyName: c.national_society_name || null,
      }))
      .sort((a, b) => {
        const aName = a.nationalSocietyName || a.countryName;
        const bName = b.nationalSocietyName || b.countryName;
        return aName.localeCompare(bName);
      });

    return items;
  }, [countries]);

  const filteredOptions = useMemo(() => {
    if (!searchQuery.trim()) {
      return options;
    }
    const query = searchQuery.toLowerCase();
    return options.filter((o) => {
      const displayName = o.nationalSocietyName || o.countryName;
      return displayName.toLowerCase().includes(query) || o.countryName.toLowerCase().includes(query);
    });
  }, [options, searchQuery]);

  useEffect(() => {
    if (!isDemoMode) return;
    if (scope?.type !== 'country' || !countryIso2) return;
    const match = options.find((o) => o.iso2 === String(countryIso2).toUpperCase());
    if (match) {
      setCountryName(match.countryName);
      setNationalSocietyName(match.nationalSocietyName);
      setCountryIso3(match.iso3);
    }
  }, [isDemoMode, scope?.type, countryIso2, options, setCountryName, setNationalSocietyName, setCountryIso3]);

  // Close dropdown when clicking outside
  useEffect(() => {
    if (!isOpen) return;
    const handleClickOutside = (event) => {
      if (event.target.closest('.demo-banner-dropdown')) return;
      setIsOpen(false);
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  if (!isDemoMode) return null;

  // Single select: "global" or ISO2.
  const selectedValue = scope?.type === 'country' && countryIso2 ? countryIso2 : 'global';

  return (
    <div className="w-full bg-amber-50 border-b border-amber-200 text-amber-900">
      <div className="w-full px-4 sm:px-6 lg:px-8 py-2 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-200 text-amber-900">
            {t('demoBanner.badge')}
          </span>
          <span className="text-sm font-medium">{t('demoBanner.description')}</span>
        </div>

        <HydrationSafe
          fallback={
            <div className="flex items-center gap-2">
              <label className="text-xs font-semibold uppercase tracking-wide text-amber-900">
                {t('demoBanner.scope')}
              </label>
              <div className="h-8 w-56 bg-amber-100 border border-amber-200 rounded-md" />
            </div>
          }
        >
          <div className="flex items-center gap-2">
            <label className="text-xs font-semibold uppercase tracking-wide text-amber-900">
              {t('demoBanner.scope')}
            </label>
            <div className="relative demo-banner-dropdown">
              <button
                type="button"
                onClick={() => {
                  setIsOpen(!isOpen);
                  setSearchQuery('');
                }}
                className="bg-white border border-amber-300 rounded-md px-3 py-1 text-sm text-amber-900 focus:outline-none focus:ring-2 focus:ring-amber-400 min-w-[220px] text-left flex items-center justify-between"
              >
                <span>
                  {selectedValue === 'global'
                    ? t('demoBanner.global')
                    : (() => {
                        const match = options.find((o) => o.iso2 === selectedValue);
                        return match
                          ? match.nationalSocietyName
                            ? `${match.nationalSocietyName} (${match.countryName})`
                            : match.countryName
                          : t('demoBanner.select');
                      })()}
                </span>
                <svg
                  className={`w-4 h-4 transition-transform ${isOpen ? 'rotate-180' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              {isOpen && (
                <div className="absolute top-full left-0 mt-1 bg-white border border-amber-300 rounded-md shadow-lg z-50 min-w-[220px] max-w-[400px] max-h-[300px] flex flex-col">
                  <div className="p-2 border-b border-amber-200">
                    <input
                      type="text"
                      placeholder={t('demoBanner.searchPlaceholder')}
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      onClick={(e) => e.stopPropagation()}
                      className="w-full px-2 py-1.5 text-sm text-amber-900 border border-amber-300 rounded focus:outline-none focus:ring-2 focus:ring-amber-400"
                      autoFocus
                    />
                  </div>
                  <div className="overflow-y-auto max-h-[240px]">
                    <button
                      type="button"
                      onClick={() => {
                        setCountryName(null);
                        setNationalSocietyName(null);
                        setCountryIso3(null);
                        setScope('global');
                        setIsOpen(false);
                        setSearchQuery('');
                      }}
                      className={`w-full text-left px-3 py-2 text-sm transition-colors ${
                        selectedValue === 'global'
                          ? 'bg-amber-200 text-amber-900 font-semibold'
                          : 'text-amber-900 hover:bg-amber-50'
                      }`}
                    >
                      {t('demoBanner.global')}
                    </button>
                    {loading ? (
                      <div className="px-3 py-2 text-sm text-amber-700">{t('common.loading')}</div>
                    ) : filteredOptions.length > 0 ? (
                      filteredOptions.map((o) => (
                        <button
                          key={o.iso2}
                          type="button"
                          onClick={() => {
                            setCountryName(o.countryName);
                            setNationalSocietyName(o.nationalSocietyName);
                            setCountryIso3(o.iso3);
                            setScope(o.iso2);
                            setIsOpen(false);
                            setSearchQuery('');
                          }}
                          className={`w-full text-left px-3 py-2 text-sm transition-colors ${
                            selectedValue === o.iso2
                              ? 'bg-amber-200 text-amber-900 font-semibold'
                              : 'text-amber-900 hover:bg-amber-50'
                          }`}
                        >
                          {o.nationalSocietyName ? `${o.nationalSocietyName} (${o.countryName})` : o.countryName}
                        </button>
                      ))
                    ) : (
                      <div className="px-3 py-2 text-sm text-amber-600">{t('demoBanner.noCountriesFound')}</div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </HydrationSafe>
      </div>
    </div>
  );
}
