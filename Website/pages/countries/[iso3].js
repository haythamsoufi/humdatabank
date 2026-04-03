// pages/countries/[iso3].js
import Head from 'next/head';
import { useRouter } from 'next/router';
import Link from 'next/link';
import { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { useTranslation } from '../../lib/useTranslation';
import {
  getCountryProfileOptimizedWithCountries,
  getCountriesList,
  getSubmittedDocuments,
  getAvailablePeriods,
  getIndicatorBank,
  getKeyFigures,
  getCountryIndicatorTimeseries,
  FDRS_TEMPLATE_ID
} from '../../lib/apiService';
import MultiChart from '../../components/MultiChart';

// Enhanced loading skeleton with modern animations
const CountryProfileSkeleton = () => (
  <div className="bg-gradient-to-br from-ngodb-gray-50 to-ngodb-gray-100 min-h-screen">
    {/* Hero Section Skeleton */}
    <div className="relative h-96 bg-gradient-to-r from-ngodb-navy to-ngodb-red animate-pulse">
      <div className="absolute inset-0 bg-black bg-opacity-30"></div>
      <div className="relative z-10 flex items-center justify-center h-full px-6 sm:px-8 lg:px-12">
        <div className="text-center">
          <div className="h-16 bg-white bg-opacity-20 rounded-lg mb-6 mx-auto w-80"></div>
          <div className="h-8 bg-white bg-opacity-20 rounded-lg mx-auto w-96"></div>
        </div>
      </div>
    </div>

    <div className="w-full px-6 sm:px-8 lg:px-12 py-12">
      {/* Top Indicators Skeleton */}
      <section className="mb-16">
        <div className="h-10 bg-ngodb-gray-200 rounded mb-8 w-64"></div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-white p-8 rounded-xl shadow-lg border-l-4 border-ngodb-red animate-pulse">
              <div className="h-6 bg-ngodb-gray-200 rounded mb-4 w-48"></div>
              <div className="h-12 bg-ngodb-gray-200 rounded mb-4 w-32"></div>
              <div className="h-4 bg-ngodb-gray-200 rounded w-24"></div>
            </div>
          ))}
        </div>
      </section>

      {/* All Indicators Skeleton */}
      <section className="mb-16">
        <div className="h-10 bg-ngodb-gray-200 rounded mb-8 w-56"></div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="bg-white p-6 rounded-lg shadow-md animate-pulse">
              <div className="h-5 bg-ngodb-gray-200 rounded mb-3 w-40"></div>
              <div className="h-8 bg-ngodb-gray-200 rounded w-24"></div>
            </div>
          ))}
        </div>
      </section>

      {/* Documents Skeleton */}
      <section className="mb-16">
        <div className="h-10 bg-ngodb-gray-200 rounded mb-8 w-48"></div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="bg-white p-6 rounded-lg shadow-md animate-pulse">
              <div className="h-6 bg-ngodb-gray-200 rounded mb-4 w-full"></div>
              <div className="h-4 bg-ngodb-gray-200 rounded mb-2 w-3/4"></div>
              <div className="h-4 bg-ngodb-gray-200 rounded w-1/2"></div>
            </div>
          ))}
        </div>
      </section>
    </div>
  </div>
);

// Timeout Error Notification Component
const TimeoutErrorNotification = ({ errors, onDismiss }) => {
  const { t } = useTranslation();

  if (!errors || errors.length === 0) return null;

  return (
    <div className="fixed top-4 right-4 z-50 max-w-md">
      <div className="bg-yellow-50 border-l-4 border-yellow-400 p-4 rounded-lg shadow-lg">
        <div className="flex">
          <div className="flex-shrink-0">
            <svg className="h-5 w-5 text-yellow-400" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
            </svg>
          </div>
          <div className="ml-3">
            <h3 className="text-sm font-medium text-yellow-800">
              {t('countryProfile.timeoutWarning.title')}
            </h3>
            <div className="mt-2 text-sm text-yellow-700">
              <p>{t('countryProfile.timeoutWarning.message')}</p>
              <ul className="mt-2 list-disc list-inside">
                {errors.map((error, index) => (
                  <li key={index}>{error}</li>
                ))}
              </ul>
            </div>
            <div className="mt-4">
              <button
                onClick={onDismiss}
                className="bg-yellow-50 px-2 py-1.5 rounded-md text-sm font-medium text-yellow-800 hover:bg-yellow-100 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-yellow-500"
              >
                {t('countryProfile.timeoutWarning.dismiss')}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

// Floating Navigation Component
const FloatingNav = ({ sections, activeSection, onSectionClick }) => {
  const { t } = useTranslation();
  const [isVisible, setIsVisible] = useState(true);
  const [showCloseButton, setShowCloseButton] = useState(false);

  // Load visibility state from localStorage on mount
  useEffect(() => {
    const savedVisibility = localStorage.getItem('floatingNavVisible');
    if (savedVisibility !== null) {
      setIsVisible(JSON.parse(savedVisibility));
    }
  }, []);

  // Save visibility state to localStorage
  const toggleVisibility = () => {
    const newVisibility = !isVisible;
    setIsVisible(newVisibility);
    localStorage.setItem('floatingNavVisible', JSON.stringify(newVisibility));
  };

        const navItems = [
          {
            id: 'overview',
            labelKey: 'countryProfile.nav.overview',
            icon: (
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            )
          },
          {
            id: 'indicators',
            labelKey: 'countryProfile.nav.indicators',
            icon: (
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
            )
          },
          {
            id: 'documents',
            labelKey: 'countryProfile.nav.documents',
            icon: (
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            )
          }
        ];

  if (!isVisible) {
    return (
      <div className="fixed left-4 top-1/2 transform -translate-y-1/2 translate-y-8 z-50 hidden lg:block">
        <button
          onClick={toggleVisibility}
          className="bg-gray-800/90 backdrop-blur-sm rounded-full shadow-lg border border-gray-700 p-3 text-white hover:bg-gray-700 transition-all duration-200 w-12 h-12 flex items-center justify-center"
          title={t('navigation.showNavigation')}
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>
      </div>
    );
  }

  return (
    <div className="fixed left-4 top-1/2 transform -translate-y-1/2 translate-y-8 z-50 hidden lg:block group">
      <div
        className="bg-gray-800/90 backdrop-blur-sm rounded-full shadow-2xl border border-gray-700 p-2 transition-all duration-300 relative overflow-visible"
        onMouseEnter={() => setShowCloseButton(true)}
        onMouseLeave={() => setShowCloseButton(false)}
      >
        {/* Close button - positioned absolutely so items don't shift */}
        <div className={`absolute -top-6 left-1/2 transform -translate-x-1/2 transition-opacity duration-200 ${showCloseButton ? 'opacity-100' : 'opacity-0'}`}>
          {/* Invisible hover area covering the gap between pane and X button */}
          <div
            className="absolute -top-4 left-1/2 transform -translate-x-1/2 w-8 h-4"
            onMouseEnter={() => setShowCloseButton(true)}
          ></div>
          <button
            onClick={toggleVisibility}
            className="text-gray-400 hover:text-white transition-colors duration-200 p-1 rounded-full w-6 h-6 flex items-center justify-center shadow-[0_0_8px_rgba(255,255,255,0.3)] hover:shadow-[0_0_12px_rgba(255,255,255,0.5)]"
            title={t('navigation.hideNavigation')}
            onMouseEnter={() => setShowCloseButton(true)}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex flex-col space-y-1">
          <nav className="flex flex-col space-y-1">
            {navItems.map((item) => (
              <button
                key={item.id}
                onClick={() => onSectionClick(item.id)}
                className={`flex items-center justify-center w-10 h-10 rounded-full text-sm font-medium transition-all duration-200 relative group/item ${
                  activeSection === item.id
                    ? 'bg-ngodb-red text-white shadow-md'
                    : 'text-white hover:bg-gray-700 hover:text-ngodb-red'
                }`}
                title={t(item.labelKey)}
              >
                <span className="flex-shrink-0">{item.icon}</span>

                {/* Tooltip */}
                <div className="absolute left-12 bg-gray-900 text-white text-sm px-2 py-1 rounded-md opacity-0 invisible group-hover/item:opacity-100 group-hover/item:visible transition-all duration-200 whitespace-nowrap z-10 pointer-events-none">
                  {t(item.labelKey)}
                  <div className="absolute left-0 top-1/2 transform -translate-y-1/2 -translate-x-1 w-2 h-2 bg-gray-900 rotate-45"></div>
                </div>
              </button>
            ))}
          </nav>
        </div>
      </div>
    </div>
  );
};

// Hero Section Component
const HeroSection = ({ country, nationalSociety, coverImages = [], keyFigures, isLoadingKeyFigures }) => {
  const { t } = useTranslation();

  console.log('HeroSection received coverImages:', coverImages);

  // Use cover images from submitted documents, fallback to null for gradient
  const heroImages = coverImages.length > 0
    ? coverImages.map(img => img.display_url || img.download_url).filter(Boolean)
    : [];

  console.log('Hero images URLs:', heroImages);

  const [currentImageIndex, setCurrentImageIndex] = useState(0);

  useEffect(() => {
    // Only run carousel if there are images
    if (heroImages.length > 1) {
      const interval = setInterval(() => {
        setCurrentImageIndex((prev) => (prev + 1) % heroImages.length);
      }, 5000);
      return () => clearInterval(interval);
    }
  }, [heroImages.length]);

  return (
    <>
      {/* Hero Cover Section */}
      <div className="relative h-64 md:h-80 overflow-hidden -mt-20 md:-mt-[136px] xl:-mt-20 pt-20 md:pt-[136px] xl:pt-20">
        {/* Background Images with Carousel or Gradient Fallback */}
        <div className="absolute inset-0">
          {heroImages.length > 0 ? (
            // Show carousel of cover images
            heroImages.map((image, index) => (
              <div
                key={index}
                className={`absolute inset-0 bg-cover bg-center transition-opacity duration-1000 ${
                  index === currentImageIndex ? 'opacity-100' : 'opacity-0'
                }`}
                style={{
                  backgroundImage: `url(${image}), linear-gradient(135deg, rgba(0,0,0,0.5), rgba(0,0,0,0.4))`
                }}
              />
            ))
          ) : (
            // Show gradient fallback when no cover images
            <div className="absolute inset-0 bg-gradient-to-br from-ngodb-navy via-ngodb-navy to-ngodb-red" />
          )}
        </div>

        {/* Overlay */}
        <div className="absolute inset-0 bg-gradient-to-r from-black/50 to-black/40"></div>

        {/* Content */}
        <div className="relative z-10 flex items-center justify-center h-full px-6 sm:px-8 lg:px-12">
          {/* Key Figures - Left Side (Desktop) */}
          <div className="hidden lg:block text-white absolute left-6 sm:left-8 lg:left-12">
            <div className="bg-black/30 backdrop-blur-sm rounded-xl pt-6 pb-2 px-6 border border-white/20">
              {isLoadingKeyFigures ? (
                <div className="grid grid-cols-2 gap-6">
                  {[1, 2, 3, 4].map((i) => (
                    <div key={i} className="animate-pulse text-center">
                      <div className="h-3 bg-white/20 rounded w-16 mx-auto mb-2"></div>
                      <div className="h-6 bg-white/20 rounded w-12 mx-auto mb-1"></div>
                      <div className="h-3 bg-white/20 rounded w-8 mx-auto"></div>
                    </div>
                  ))}
                </div>
              ) : (
                <div>
                  <div className="grid grid-cols-2 gap-6">
                    {['volunteers', 'staff', 'branches', 'localUnits'].map((key) => {
                      const figure = keyFigures[key] || {
                        name: key === 'localUnits' ? 'Local Units' : key.charAt(0).toUpperCase() + key.slice(1),
                        value: null,
                        year: null
                      };
                      return (
                        <div key={key} className="text-center">
                          <span className="text-sm text-ngodb-gray-200 block capitalize">
                            {figure.name}
                          </span>
                          <span className="text-2xl font-bold text-ngodb-red block">
                            {figure.value ? figure.value.toLocaleString() : 'N/A'}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                  {/* Show year once at the bottom if any figure has a year */}
                  {(() => {
                    const years = ['volunteers', 'staff', 'branches', 'localUnits']
                      .map(key => keyFigures[key]?.year)
                      .filter(Boolean);
                    const uniqueYears = [...new Set(years)];
                    return uniqueYears.length > 0 && (
                      <div className="text-center mt-1">
                        <span className="text-xs text-ngodb-gray-300">
                          ({uniqueYears.join(', ')})
                        </span>
                      </div>
                    );
                  })()}
                </div>
              )}
            </div>
          </div>

          {/* Country Title - Center */}
          <div className="text-center text-white w-full max-w-4xl">
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold mb-4 drop-shadow-lg">
              {country.name}
            </h1>
            {nationalSociety && (
              <p className="text-xl sm:text-2xl lg:text-3xl text-ngodb-gray-200 mb-6 drop-shadow-md">
                {nationalSociety}
              </p>
            )}
          </div>
        </div>

        {/* Scroll indicator */}
        <div className="absolute bottom-8 left-1/2 transform -translate-x-1/2 text-white animate-bounce">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
          </svg>
        </div>
      </div>

      {/* Key Figures Bar - Mobile (Below cover) */}
      <div className="lg:hidden bg-ngodb-navy border-b border-ngodb-navy shadow-sm text-white">
        <div className="px-4 py-4">
          {isLoadingKeyFigures ? (
            <div className="grid grid-cols-4 gap-2">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="animate-pulse text-center">
                  <div className="h-3 bg-ngodb-gray-200 rounded w-12 mx-auto mb-1"></div>
                  <div className="h-4 bg-ngodb-gray-200 rounded w-8 mx-auto mb-1"></div>
                  <div className="h-2 bg-ngodb-gray-200 rounded w-6 mx-auto"></div>
                </div>
              ))}
            </div>
          ) : (
            <div>
              <div className="grid grid-cols-4 gap-2">
                {['volunteers', 'staff', 'branches', 'localUnits'].map((key) => {
                  const figure = keyFigures[key] || {
                    name: key === 'localUnits' ? 'Local Units' : key.charAt(0).toUpperCase() + key.slice(1),
                    value: null,
                    year: null
                  };
                  return (
                    <div key={key} className="text-center">
                      <span className="text-xs text-white/80 block capitalize leading-tight">
                        {figure.name}
                      </span>
                      <span className="text-sm font-bold text-ngodb-red block leading-tight">
                        {figure.value ? figure.value.toLocaleString() : 'N/A'}
                      </span>
                    </div>
                  );
                })}
              </div>
              {/* Show year once at the bottom if any figure has a year */}
              {(() => {
                const years = ['volunteers', 'staff', 'branches', 'localUnits']
                  .map(key => keyFigures[key]?.year)
                  .filter(Boolean);
                const uniqueYears = [...new Set(years)];
                return uniqueYears.length > 0 && (
                  <div className="hidden md:block text-center mt-2">
                    <span className="text-xs text-white/70">
                      ({uniqueYears.join(', ')})
                    </span>
                  </div>
                );
              })()}
            </div>
          )}
        </div>
      </div>
    </>
  );
};

// Top Sectors Component (replaces National Society Strengths)
const TopSectorsSection = ({ sectors, t, isLoading }) => {
  if (isLoading) {
    return (
      <section className="mb-16">
        <div className="text-center mb-12">
          <h2 className="text-3xl font-bold text-ngodb-navy mb-4">
            {t('countryProfile.topSectors')}
          </h2>
          <p className="text-lg text-ngodb-gray-600 max-w-2xl mx-auto">
            {t('countryProfile.topSectorsDescription')}
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-white p-8 rounded-xl shadow-lg border-l-4 border-ngodb-red animate-pulse">
              <div className="h-6 bg-ngodb-gray-200 rounded mb-4 w-48"></div>
              <div className="h-12 bg-ngodb-gray-200 rounded mb-4 w-32"></div>
              <div className="h-4 bg-ngodb-gray-200 rounded w-24"></div>
            </div>
          ))}
        </div>
      </section>
    );
  }

  if (!sectors || sectors.length === 0) {
    return (
      <section className="mb-16">
        <div className="text-center mb-12">
          <h2 className="text-3xl font-bold text-ngodb-navy mb-4">
            {t('countryProfile.topSectors')}
          </h2>
          <p className="text-lg text-ngodb-gray-600 max-w-2xl mx-auto">
            {t('countryProfile.topSectorsDescription')}
          </p>
        </div>
        <div className="text-center text-ngodb-gray-600 py-12">
          <p>{t('countryProfile.noTopSectors')}</p>
        </div>
      </section>
    );
  }

  return (
    <section className="mb-16">
      <div className="text-center mb-12">
        <h2 className="text-3xl font-bold text-ngodb-navy mb-4">
          {t('countryProfile.topSectors')}
        </h2>
        <p className="text-lg text-ngodb-gray-600 max-w-2xl mx-auto">
          {t('countryProfile.topSectorsDescription')}
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
        {sectors.slice(0, 3).map((sector, index) => (
          <div
            key={sector.name}
            className="group bg-white p-8 rounded-xl shadow-lg hover:shadow-xl transition-all duration-300 border-l-4 border-ngodb-red hover:scale-105"
          >
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center space-x-3">
                <div className="w-12 h-12 bg-ngodb-red text-white rounded-full flex items-center justify-center text-xl font-bold">
                  {index + 1}
                </div>
                <h3 className="text-xl font-bold text-ngodb-navy group-hover:text-ngodb-red transition-colors">
                  {sector.name}
                </h3>
              </div>
            </div>

            <div className="text-3xl font-bold text-ngodb-red mb-2">
              {sector.maxValue?.toLocaleString() || 'N/A'}
            </div>

            <div className="text-sm text-ngodb-gray-500 mb-4">
              {t('countryProfile.maxValue')}
            </div>

            <div className="mt-4 pt-4 border-t border-ngodb-gray-200">
              <div className="flex items-center justify-between text-sm">
                <span className="text-ngodb-gray-500">
                  {t('countryProfile.indicatorsCount')}: {sector.count}
                </span>
                <span className="text-ngodb-red font-medium">
                  {t('countryProfile.topSector')}
                </span>
              </div>

              {/* Show top indicators in this sector */}
              {sector.indicators && sector.indicators.length > 0 && (
                <div className="mt-3">
                  <p className="text-xs text-ngodb-gray-500 mb-2">
                    {t('countryProfile.topIndicatorsInSector')}:
                  </p>
                  <div className="space-y-1">
                    {sector.indicators.slice(0, 2).map((indicator, idx) => (
                      <div key={idx} className="text-xs text-ngodb-gray-600 truncate">
                        • {indicator.indicator_label}: {indicator.value?.toLocaleString() || 'N/A'}
                      </div>
                    ))}
                    {sector.indicators.length > 2 && (
                      <div className="text-xs text-ngodb-gray-500">
                        +{sector.indicators.length - 2} {t('countryProfile.more')}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
};

// All Indicators Component
const AllIndicatorsSection = ({ allIndicators, t }) => {
  const [selectedPeriod, setSelectedPeriod] = useState('all');
  const [searchTerm, setSearchTerm] = useState('');

  // Get unique periods from indicators
  const periods = [...new Set(allIndicators.map(ind => ind.period).filter(Boolean))];

  // Filter indicators based on period and search
  const filteredIndicators = allIndicators.filter(indicator => {
    const matchesPeriod = selectedPeriod === 'all' || indicator.period === selectedPeriod;
    const matchesSearch = indicator.indicator_label?.toLowerCase().includes(searchTerm.toLowerCase());
    return matchesPeriod && matchesSearch;
  });

  if (!allIndicators || allIndicators.length === 0) {
    return (
      <section className="mb-16">
        <h2 className="text-3xl font-bold text-ngodb-navy mb-8 text-center">
          {t('countryProfile.allIndicators')}
        </h2>
        <div className="text-center text-ngodb-gray-600 py-12">
          <p>{t('countryProfile.noIndicators')}</p>
        </div>
      </section>
    );
  }

  return (
    <section className="mb-16">
      <div className="text-center mb-12">
        <h2 className="text-3xl font-bold text-ngodb-navy mb-4">
          {t('countryProfile.allIndicators')}
        </h2>
        <p className="text-lg text-ngodb-gray-600 max-w-2xl mx-auto">
          {t('countryProfile.allIndicatorsDescription')}
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4 mb-8 justify-between items-center">
        <div className="flex flex-col sm:flex-row gap-4">
          <div className="relative">
            <input
              type="text"
              placeholder={t('countryProfile.searchIndicators')}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-10 pr-4 py-2 border border-ngodb-gray-300 rounded-lg focus:ring-2 focus:ring-ngodb-red focus:border-transparent"
            />
            <svg className="absolute left-3 top-2.5 w-4 h-4 text-ngodb-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </div>

          {periods.length > 0 && (
            <select
              value={selectedPeriod}
              onChange={(e) => setSelectedPeriod(e.target.value)}
              className="px-4 py-2 border border-ngodb-gray-300 rounded-lg focus:ring-2 focus:ring-ngodb-red focus:border-transparent"
            >
              <option value="all">{t('countryProfile.allPeriods')}</option>
              {periods.map(period => (
                <option key={period} value={period}>{period}</option>
              ))}
            </select>
          )}
        </div>

        <div className="text-sm text-ngodb-gray-600">
          {t('countryProfile.showing')} {filteredIndicators.length} {t('countryProfile.of')} {allIndicators.length} {t('countryProfile.indicatorsLabel')}
        </div>
      </div>

      {/* Indicators Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {(() => {
          const maxValue = Math.max(...allIndicators.map(i => i.value || 0), 1);
          return filteredIndicators.map((indicator, index) => (
          <div
            key={`${indicator.indicator_label}-${index}`}
            className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition-shadow duration-200 border border-ngodb-gray-200"
          >
            <h3 className="text-lg font-semibold text-ngodb-navy mb-2 line-clamp-2">
              {indicator.indicator_label}
            </h3>

            <div className="text-2xl font-bold text-ngodb-red mb-2">
              {indicator.value?.toLocaleString() || 'N/A'}
              {indicator.unit && (
                <span className="text-sm text-ngodb-gray-500 ml-1">
                  {indicator.unit}
                </span>
              )}
            </div>

            {indicator.period && (
              <p className="text-xs text-ngodb-gray-500 mb-3">
                {t('countryProfile.period')}: {indicator.period}
              </p>
            )}

            {/* Progress bar for visual appeal */}
            <div className="w-full bg-ngodb-gray-200 rounded-full h-2 mb-2">
              <div
                className="bg-gradient-to-r from-ngodb-red to-ngodb-navy h-2 rounded-full transition-all duration-500"
                style={{
                  width: `${Math.min(100, (indicator.value || 0) / maxValue * 100)}%`
                }}
              ></div>
            </div>
          </div>
          ));
        })()}
      </div>

      {filteredIndicators.length === 0 && (
        <div className="text-center py-12">
          <p className="text-ngodb-gray-600">{t('countryProfile.noIndicatorsFound')}</p>
        </div>
      )}
    </section>
  );
};

// Documents Section Component
const DocumentsSection = ({ documents, t }) => {
  const [selectedType, setSelectedType] = useState('all');
  const [selectedPeriod, setSelectedPeriod] = useState('all');

  // Get unique document types
  const documentTypes = [...new Set(documents.map(doc => doc.document_type).filter(Boolean))];

  // Get unique periods (years) from documents
  const periods = [...new Set(documents.map(doc => doc.year).filter(Boolean))].sort((a, b) => b - a);

  // Filter documents based on type and period
  const filteredDocuments = documents.filter(doc => {
    const matchesType = selectedType === 'all' || doc.document_type === selectedType;
    const matchesPeriod = selectedPeriod === 'all' || doc.year === parseInt(selectedPeriod);
    return matchesType && matchesPeriod;
  });

  if (!documents || documents.length === 0) {
    return (
      <section className="mb-16">
        <h2 className="text-3xl font-bold text-ngodb-navy mb-8 text-center">
          {t('countryProfile.documents')}
        </h2>
        <div className="text-center text-ngodb-gray-600 py-12">
          <p>{t('countryProfile.noDocuments')}</p>
        </div>
      </section>
    );
  }

  return (
    <section className="mb-16">
      <div className="text-center mb-12">
        <h2 className="text-3xl font-bold text-ngodb-navy mb-4">
          {t('countryProfile.documents')}
        </h2>
        <p className="text-lg text-ngodb-gray-600 max-w-2xl mx-auto">
          {t('countryProfile.documentsDescription')}
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4 mb-8 justify-center items-center">
      {/* Document Type Filter */}
      {documentTypes.length > 0 && (
          <div className="flex flex-wrap justify-center gap-2">
          <button
            onClick={() => setSelectedType('all')}
            className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
              selectedType === 'all'
                ? 'bg-ngodb-red text-white'
                : 'bg-ngodb-gray-200 text-ngodb-gray-700 hover:bg-ngodb-gray-300'
            }`}
          >
            {t('countryProfile.allDocuments')}
          </button>
          {documentTypes.map(type => (
            <button
              key={type}
              onClick={() => setSelectedType(type)}
              className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
                selectedType === type
                  ? 'bg-ngodb-red text-white'
                  : 'bg-ngodb-gray-200 text-ngodb-gray-700 hover:bg-ngodb-gray-300'
              }`}
            >
              {type.charAt(0).toUpperCase() + type.slice(1)}
            </button>
          ))}
        </div>
      )}

        {/* Period Filter */}
        {periods.length > 0 && (
          <div className="flex items-center gap-2">
            <label className="text-sm font-medium text-ngodb-gray-700">
              {t('countryProfile.period')}:
            </label>
            <div className="relative">
              <select
                value={selectedPeriod}
                onChange={(e) => setSelectedPeriod(e.target.value)}
                className="px-3 py-2 pr-8 border border-ngodb-gray-300 rounded-lg focus:ring-2 focus:ring-ngodb-red focus:border-transparent text-sm appearance-none bg-white w-full"
              >
                <option value="all">{t('countryProfile.allPeriods')}</option>
                {periods.map(period => (
                  <option key={period} value={period}>{period}</option>
                ))}
              </select>
              <div className="absolute inset-y-0 right-0 flex items-center pr-2 pointer-events-none">
                <svg className="w-4 h-4 text-ngodb-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Results count */}
      <div className="text-center mb-6">
        <p className="text-sm text-ngodb-gray-600">
          {t('countryProfile.showing')} {filteredDocuments.length} {t('countryProfile.of')} {documents.length} {t('countryProfile.documents')}
        </p>
      </div>

      {/* Documents Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {filteredDocuments.map((document) => (
          <div
            key={document.id}
            className="relative h-80 rounded-lg shadow-md hover:shadow-xl transition-all duration-300 group overflow-hidden cursor-pointer"
            style={{
              backgroundImage: document.thumbnail_url
                ? `url(${document.thumbnail_url}), linear-gradient(135deg, rgba(0,50,98,0.3), rgba(220,38,38,0.2))`
                : document.display_url
                ? `url(${document.display_url}), linear-gradient(135deg, rgba(0,50,98,0.6), rgba(220,38,38,0.5))`
                : document.download_url
                ? `url(${document.download_url}), linear-gradient(135deg, rgba(0,50,98,0.8), rgba(220,38,38,0.7))`
                : 'linear-gradient(135deg, rgba(0,50,98,0.9), rgba(220,38,38,0.8))',
              backgroundSize: 'cover',
              backgroundPosition: 'center',
              backgroundBlendMode: 'overlay'
            }}
          >
            {/* Overlay gradient for better text readability */}
            <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent"></div>

            {/* Document Type Badge */}
            <div className="absolute top-4 left-4 right-4 z-10">
              <span className="px-3 py-1 bg-ngodb-red text-white text-xs font-medium rounded-full backdrop-blur-sm bg-opacity-90">
                {document.document_type?.charAt(0).toUpperCase() + document.document_type?.slice(1) || 'Document'}
              </span>
            </div>

            {/* Content positioned at bottom */}
            <div className="absolute bottom-0 left-0 right-0 p-6 z-10">
              {/* Document Title - Clickable for Download */}
              {document.download_url ? (
                <a
                  href={document.download_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block group/title"
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="flex items-start justify-between gap-3 mb-2">
                    <h3 className="text-lg font-bold text-white line-clamp-2 group-hover:text-ngodb-red transition-colors drop-shadow-lg flex-1">
                      {document.filename}
                    </h3>
                    <div className="w-8 h-8 bg-white/20 backdrop-blur-sm rounded-full flex items-center justify-center flex-shrink-0 group-hover/title:bg-ngodb-red transition-colors">
                      <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                    </div>
                  </div>
                </a>
              ) : (
                <div className="flex items-start justify-between gap-3 mb-2">
                  <h3 className="text-lg font-bold text-white line-clamp-2 drop-shadow-lg flex-1">
                    {document.filename}
                  </h3>
                  <div className="w-8 h-8 bg-white/20 backdrop-blur-sm rounded-full flex items-center justify-center flex-shrink-0 opacity-50">
                    <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  </div>
                </div>
              )}

              {/* Document Language and Year */}
              {(document.language || document.year) && (
                <p className="text-white/70 text-xs mb-3 drop-shadow-sm">
                  {document.language && document.year
                    ? `${document.language.toUpperCase()} • ${document.year}`
                    : document.language
                    ? document.language.toUpperCase()
                    : document.year
                  }
                </p>
              )}

              {/* Upload Date */}
              {document.uploaded_at && (
                <p className="text-white/70 text-xs drop-shadow-sm">
                  {new Date(document.uploaded_at).toLocaleDateString()}
                </p>
              )}
            </div>

            {/* Hover overlay effect */}
            <div className="absolute inset-0 bg-ngodb-red/20 opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
          </div>
        ))}
      </div>

      {filteredDocuments.length === 0 && (
        <div className="text-center py-12">
          <p className="text-ngodb-gray-600">{t('countryProfile.noDocumentsFound')}</p>
        </div>
      )}
    </section>
  );
};

// Use static generation with incremental static regeneration for better performance
export async function getStaticProps({ params }) {
  try {
    // Get countries list once and pass it to the optimized function
    const countries = await getCountriesList();
    const country = countries.find(
      (c) => (c.iso3 && c.iso3.toUpperCase() === params.iso3.toUpperCase())
    );

    if (!country) {
      throw new Error(`Country not found for ISO3: ${params.iso3.toUpperCase()}`);
    }

    let profileData;
    try {
      profileData = await getCountryProfileOptimizedWithCountries(params.iso3.toUpperCase(), countries);
    } catch (profileError) {
      console.error(`Error fetching profile data for ${params.iso3.toUpperCase()}:`, profileError);
      // Create a minimal profile with just country info if data fetch fails
      profileData = {
        country_info: {
          id: country.id || null,
          name: country.name,
          iso3: country.iso3,
          iso2: country.iso2,
          national_society_name: country.national_society_name,
          flag_url: country.iso2 ? `/flags/${country.iso2.toLowerCase()}.svg` : null
        },
        summary_stats: {
          people_assisted_last_year: null,
          active_programs: 0,
          key_focus_areas: []
        },
        narrative: null,
        indicator_data: [],
        related_publications_api_url: null,
        map_data: null
      };
    }

    if (!profileData || !profileData.country_info) {
      throw new Error(`No profile data found for ${params.iso3.toUpperCase()}`);
    }

    // Fetch submitted documents for this country with timeout handling
    let documents = [];
    let coverImages = [];
    try {
      // Use Promise.allSettled to handle both document fetches independently
      const [documentsResult, coverImagesResult] = await Promise.allSettled([
        getSubmittedDocuments(country.id, '', 'en', true, 'approved', 1, 100),
        getSubmittedDocuments(country.id, 'Cover Image', 'en', true, 'approved', 1, 10)
      ]);

      // Handle documents result
      if (documentsResult.status === 'fulfilled') {
        documents = documentsResult.value.documents || [];
        console.log('Documents fetched successfully:', documents.length);
      } else {
        console.error('Failed to fetch documents:', documentsResult.reason);
        documents = [];
      }

      // Handle cover images result
      if (coverImagesResult.status === 'fulfilled') {
        coverImages = coverImagesResult.value.documents || [];
        console.log('Cover images fetched successfully:', coverImages.length);
      } else {
        console.error('Failed to fetch cover images:', coverImagesResult.reason);
        coverImages = [];
      }

    } catch (error) {
      console.error('Failed to fetch submitted documents:', error);
      console.error('Error details:', error.message);
      console.error('Error stack:', error.stack);

      // Ensure we have empty arrays as fallback
      documents = [];
      coverImages = [];
    }

    return {
      props: {
        profileData,
        documents,
        coverImages,
        error: null
      },
      // Revalidate every 6 hours for fresh data
      revalidate: 21600
    };
  } catch (error) {
    console.error(`Failed to fetch country profile for ${params.iso3}:`, error);
    return {
      props: {
        profileData: null,
        documents: [],
        coverImages: [],
        error: `Could not load profile data for ${params.iso3.toUpperCase()}. It might not be available yet.`,
      },
      revalidate: 21600
    };
  }
}

// Don't pre-generate any country pages - generate them on-demand
export async function getStaticPaths() {
  return {
    paths: [], // No pre-generated paths
    fallback: true // Generate pages on-demand and render fallback immediately
  };
}

export default function CountryProfilePage({ profileData, documents, coverImages, error }) {
  const router = useRouter();
  const { t } = useTranslation();
  const [clientCoverImages, setClientCoverImages] = useState([]);
  const [isLoadingCoverImages, setIsLoadingCoverImages] = useState(false);
  const [activeSection, setActiveSection] = useState('overview');
  const sectionRefs = useRef({});

  // Indicator selection state
  const [selectedIndicator, setSelectedIndicator] = useState('volunteers');
  const [activeIndicator, setActiveIndicator] = useState('volunteers');

  // Timeseries data state
  const [timeseriesData, setTimeseriesData] = useState([]);
  const [isLoadingTimeseries, setIsLoadingTimeseries] = useState(false);
  const [availableYears, setAvailableYears] = useState([]);
  const [chartSummaryStats, setChartSummaryStats] = useState(null);

  // Indicator bank data state
  const [indicatorBankData, setIndicatorBankData] = useState([]);
  const [isLoadingIndicatorBank, setIsLoadingIndicatorBank] = useState(false);

  // Error states
  const [timeoutErrors, setTimeoutErrors] = useState([]);
  const [hasTimeoutError, setHasTimeoutError] = useState(false);

  // Key figures state
  const [keyFigures, setKeyFigures] = useState({
    volunteers: { value: null, year: null, name: 'Volunteers', unit: 'Volunteers' },
    staff: { value: null, year: null, name: 'Staff', unit: 'Staff' },
    branches: { value: null, year: null, name: 'Branches', unit: 'Branches' },
    localUnits: { value: null, year: null, name: 'Local Units', unit: 'Units' }
  });
  const [isLoadingKeyFigures, setIsLoadingKeyFigures] = useState(false);

  // Key indicators mapping to indicator bank IDs
  const keyIndicatorsMapping = {
    'volunteers': {
      id: 724,
      name: t('globalOverview.indicators.volunteers'),
      unit: 'Volunteers'
    },
    'staff': {
      id: 727,
      name: t('globalOverview.indicators.staff'),
      unit: 'Staff'
    },
    'branches': {
      id: 1117,
      name: t('globalOverview.indicators.branches'),
      unit: 'Branches'
    },
    'local-units': {
      id: 723,
      name: t('globalOverview.indicators.localUnits'),
      unit: 'Units'
    },
    'blood-donors': {
      id: 626,
      name: t('globalOverview.indicators.bloodDonors'),
      unit: 'People'
    },
    'first-aid': {
      id: 625,
      name: t('globalOverview.indicators.firstAid'),
      unit: 'People'
    },
    'people-reached': {
      id: 729,
      name: t('globalOverview.indicators.peopleReached'),
      unit: 'People'
    },
    'income': {
      id: 733,
      name: t('globalOverview.indicators.income'),
      unit: 'USD'
    },
    'expenditure': {
      id: 734,
      name: t('globalOverview.indicators.expenditure'),
      unit: 'USD'
    }
  };

  // Fetch available years/periods
  const fetchAvailableYears = async () => {
    try {
      const periods = await getAvailablePeriods(FDRS_TEMPLATE_ID);
      console.log('Available periods from API:', periods);
      setAvailableYears(periods);
    } catch (error) {
      console.error('Error fetching available years:', error);

      // Check if it's a timeout error
      if (error.name === 'TimeoutError' || error.message.includes('timeout')) {
        console.error('Timeout error detected in available years fetch');
        setTimeoutErrors(prev => [...prev, t('errors.failedToLoadAvailableYears')]);
        setHasTimeoutError(true);
      }

      setAvailableYears(['2023', '2022', '2021', '2020', '2019']);
    }
  };

  // Fetch indicator bank data
  const fetchIndicatorBankData = async () => {
    setIsLoadingIndicatorBank(true);
    try {
      const indicatorBankResponse = await getIndicatorBank('', '', '', '', '', null, 'en');
      console.log('Indicator bank data:', indicatorBankResponse);
      setIndicatorBankData(indicatorBankResponse.indicators || []);
    } catch (error) {
      console.error('Error fetching indicator bank data:', error);

      // Check if it's a timeout error
      if (error.name === 'TimeoutError' || error.message.includes('timeout')) {
        console.error('Timeout error detected in indicator bank data fetch');
        setTimeoutErrors(prev => [...prev, t('errors.failedToLoadIndicatorBankData')]);
        setHasTimeoutError(true);
      }

      setIndicatorBankData([]);
    } finally {
      setIsLoadingIndicatorBank(false);
    }
  };

  // Fetch key figures data
  const fetchKeyFigures = async () => {
    if (!profileData?.country_info?.id || !profileData?.country_info?.iso2) {
      return;
    }

    setIsLoadingKeyFigures(true);
    try {
      const keyFiguresData = await getKeyFigures(
        profileData.country_info.id,
        profileData.country_info.iso2
      );
      console.log('Key figures data:', keyFiguresData);
      setKeyFigures(keyFiguresData);
    } catch (error) {
      console.error('Error fetching key figures:', error);

      // Check if it's a timeout error
      if (error.name === 'TimeoutError' || error.message.includes('timeout')) {
        console.error('Timeout error detected in key figures fetch');
        setTimeoutErrors(prev => [...prev, t('errors.failedToLoadKeyFigures')]);
        setHasTimeoutError(true);
      }

      // Keep default state on error
    } finally {
      setIsLoadingKeyFigures(false);
    }
  };

  // Get sector information for an indicator by its ID
  const getSectorForIndicator = (indicatorId) => {
    const indicator = indicatorBankData.find(ind => ind.id === indicatorId);
    if (indicator && indicator.sector && indicator.sector.primary) {
      return indicator.sector.primary;
    }
    return null;
  };

  // Get top sectors from indicator data
  const getTopSectors = (indicators) => {
    if (!indicators || !indicatorBankData.length) return [];

    // Group indicators by sector and calculate totals
    const sectorTotals = {};

    indicators.forEach(indicator => {
      // The indicator data from the country profile API has this structure:
      // { indicator_label: "...", value: ..., unit: "...", period: "..." }
      // We need to match by indicator_label to find the corresponding indicator bank entry
      const indicatorBankEntry = indicatorBankData.find(ind =>
        ind.name === indicator.indicator_label ||
        ind.localized_name === indicator.indicator_label
      );

      if (indicatorBankEntry) {
        const sector = getSectorForIndicator(indicatorBankEntry.id);

        if (sector && indicator.value) {
          if (!sectorTotals[sector]) {
            sectorTotals[sector] = {
              name: sector,
              maxValue: 0,
              indicators: [],
              count: 0
            };
          }
          sectorTotals[sector].maxValue = Math.max(sectorTotals[sector].maxValue, indicator.value || 0);
          sectorTotals[sector].indicators.push(indicator);
          sectorTotals[sector].count += 1;
        }
      }
    });

    // Convert to array and sort by max value
    const sortedSectors = Object.values(sectorTotals)
      .sort((a, b) => b.maxValue - a.maxValue)
      .slice(0, 3);

    return sortedSectors;
  };

  // Fetch timeseries data for selected indicator
  const fetchTimeseriesData = async (indicatorKey) => {
    if (!profileData?.country_info?.id) return;
    setIsLoadingTimeseries(true);
    try {
      const indicator = keyIndicatorsMapping[indicatorKey];
      if (!indicator) {
        setTimeseriesData([]);
        return;
      }
      const iso2 = profileData.country_info.iso2;
      const iso3 = profileData.country_info.iso3;
      const series = await getCountryIndicatorTimeseries(iso2, iso3, indicator.id);
      setTimeseriesData(series);
    } catch (error) {
      console.error('Error fetching timeseries data:', error);
      setTimeseriesData([]);
    } finally {
      setIsLoadingTimeseries(false);
    }
  };

  // Fetch cover images on the client side if not available from static generation
  useEffect(() => {
    const fetchCoverImages = async () => {
      console.log('Client-side fetchCoverImages called');
      console.log('coverImages from props:', coverImages);
      console.log('profileData?.country_info?.id:', profileData?.country_info?.id);

      if (coverImages && coverImages.length > 0) {
        console.log('Using cover images from props');
        setClientCoverImages(coverImages);
        return;
      }

      if (!profileData?.country_info?.id) {
        console.log('No country ID available, skipping cover image fetch');
        return;
      }

      console.log('Fetching cover images on client side for country ID:', profileData.country_info.id);
      setIsLoadingCoverImages(true);
      try {
        const { getSubmittedDocuments } = await import('../../lib/apiService');
        const coverImagesResponse = await getSubmittedDocuments(
          profileData.country_info.id,
          'Cover Image',
          'en',
          true,
          'approved',
          1,
          10
        );
        console.log('Client-side cover images response:', coverImagesResponse);
        setClientCoverImages(coverImagesResponse.documents || []);
      } catch (error) {
        console.error('Failed to fetch cover images on client side:', error);

        // Check if it's a timeout error
        if (error.name === 'TimeoutError' || error.message.includes('timeout')) {
          console.error('Timeout error detected in client-side cover image fetch');
        }

        // Set empty array as fallback
        setClientCoverImages([]);
      } finally {
        setIsLoadingCoverImages(false);
      }
    };

    fetchCoverImages();
  }, [coverImages, profileData?.country_info?.id]);

  // Initialize available years and indicator bank data on component mount
  useEffect(() => {
    fetchAvailableYears();
    fetchIndicatorBankData();
  }, []);

  // Fetch key figures when profile data is available
  useEffect(() => {
    if (profileData?.country_info?.id && profileData?.country_info?.iso2) {
      fetchKeyFigures();
    }
  }, [profileData?.country_info?.id, profileData?.country_info?.iso2]);

  // Fetch timeseries data when indicator changes
  useEffect(() => {
    if (availableYears.length > 0 && activeIndicator) {
      fetchTimeseriesData(activeIndicator);
    }
  }, [activeIndicator, availableYears, profileData?.country_info?.id]);

  // Helper function to get current indicator name for display
  const getCurrentIndicatorName = () => {
    return keyIndicatorsMapping[activeIndicator]?.name || t('fallbacks.unknownIndicator');
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

  // Handle section navigation
  const handleSectionClick = (sectionId) => {
    const element = document.getElementById(sectionId);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  // Handle timeout error notification dismiss
  const handleDismissTimeoutError = () => {
    setTimeoutErrors([]);
    setHasTimeoutError(false);
  };

  // Track active section based on scroll position
  useEffect(() => {
    const handleScroll = () => {
      const sections = ['overview', 'indicators', 'documents'];
      const scrollPosition = window.scrollY + 100;

      for (const sectionId of sections) {
        const element = document.getElementById(sectionId);
        if (element) {
          const { offsetTop, offsetHeight } = element;
          if (scrollPosition >= offsetTop && scrollPosition < offsetTop + offsetHeight) {
            setActiveSection(sectionId);
            break;
          }
        }
      }
    };

    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  // Handle fallback state during static generation - show loading skeleton
  if (router.isFallback) {
    return <CountryProfileSkeleton />;
  }

  // Display error message if fetching failed or no data was returned
  // Also check if profileData has at least country_info
  if (error || !profileData || !profileData.country_info) {
    console.error('[CountryProfilePage] Error state:', { error, hasProfileData: !!profileData, hasCountryInfo: !!profileData?.country_info });
    return (
      <div className="min-h-screen bg-gradient-to-br from-ngodb-gray-50 to-ngodb-gray-100 flex items-center justify-center">
        <div className="text-center px-6">
        <Head>
          <title>{`${t('countryProfile.error.title')} - NGO Databank`}</title>
        </Head>
          <div className="mb-8">
            <svg className="w-24 h-24 text-ngodb-red mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
          </div>
        <h1 className="text-3xl font-bold text-ngodb-red mb-6">{t('countryProfile.error.title')}</h1>
          <p className="text-ngodb-gray-700 mb-8 text-lg">{error || t('countryProfile.error.loadFailed')}</p>
        <div className="space-x-4">
            <Link
              href="/countries"
              className="inline-flex items-center px-6 py-3 bg-ngodb-red text-white font-medium rounded-lg hover:bg-ngodb-red-dark transition-colors"
            >
              <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
              {t('countryProfile.actions.backToList')}
          </Link>
          </div>
        </div>
      </div>
    );
  }

  // Destructure data only if profileData is available
  const { country_info, summary_stats, indicator_data } = profileData;

  console.log('profileData:', profileData);
  console.log('country_info:', country_info);
  console.log('country_info.id:', country_info?.id);

  // Get top sectors from indicator data
  const topSectors = getTopSectors(indicator_data);
  const allIndicators = indicator_data;

  return (
    <>
      <Head>
        <title>{`${country_info.name} - ${t('countryProfile.title')} - NGO Databank`}</title>
        <meta name="description" content={`Humanitarian data, visualizations, and impact in ${country_info.name}. Explore indicators and country context.`} />
        <meta name="keywords" content={`${country_info.name}, humanitarian data, indicators, ${country_info.national_society_name || ''}`} />
      </Head>

      {/* Timeout Error Notification */}
      <TimeoutErrorNotification
        errors={timeoutErrors}
        onDismiss={handleDismissTimeoutError}
      />

      {/* Floating Navigation */}
      <FloatingNav
        activeSection={activeSection}
        onSectionClick={handleSectionClick}
      />

      <div className="bg-gradient-to-br from-ngodb-gray-50 to-ngodb-gray-100 min-h-screen">
        {/* Hero Section */}
        <HeroSection
          country={country_info}
          nationalSociety={country_info.national_society_name}
          coverImages={clientCoverImages}
          keyFigures={keyFigures}
          isLoadingKeyFigures={isLoadingKeyFigures}
        />

        <div className="w-full px-6 sm:px-8 lg:px-12 py-12">
          {/* Overview - Combined At a Glance and National Society Strengths */}
          <section id="overview" className="mb-16">
              <div className="bg-white rounded-xl shadow-lg p-8">
              <h2 className="text-3xl font-bold text-ngodb-navy mb-8 text-center">
                {t('countryProfile.sections.overview')}
                </h2>


              {/* Top Sectors */}
              <TopSectorsSection
                sectors={topSectors}
                t={t}
                isLoading={isLoadingIndicatorBank}
              />
              </div>
            </section>

          {/* Key Indicators Bar and Timeseries Chart */}
          <section id="indicators" className="mb-16">
            <div className="text-center mb-12">
              <h2 className="text-3xl font-bold text-ngodb-navy mb-4">
                {t('countryProfile.keyIndicators')}
              </h2>
              <p className="text-lg text-ngodb-gray-600 max-w-2xl mx-auto">
                {t('countryProfile.keyIndicatorsDescription')}
              </p>
            </div>

            {/* Key Indicators Selector */}
            <div className="bg-ngodb-white shadow-lg border border-ngodb-gray-100 overflow-hidden">
              <div className="flex h-16 overflow-x-auto md:overflow-visible space-x-2 md:space-x-0 px-2 md:px-0">
                {Object.entries(keyIndicatorsMapping).map(([key, indicator]) => (
                  <button
                    key={key}
                    onClick={() => {
                      setSelectedIndicator(key);
                      setActiveIndicator(key);
                    }}
                    className={`group relative md:flex-1 flex-shrink-0 px-3 font-semibold transition-all duration-300 md:border-r md:last:border-r-0 ${
                      selectedIndicator === key
                        ? 'bg-ngodb-red text-white'
                        : 'bg-ngodb-white text-ngodb-gray-700 hover:bg-ngodb-gray-50'
                    }`}
                  >
                    <span className="text-sm">{indicator.name}</span>
                    {selectedIndicator === key && (
                      <motion.div
                        className="absolute bottom-0 left-0 right-0 h-1 bg-ngodb-red"
                        initial={{ scaleX: 0 }}
                        animate={{ scaleX: 1 }}
                        transition={{ type: "spring", stiffness: 500, damping: 30 }}
                      />
                    )}
                  </button>
                ))}
              </div>
            </div>

            {/* Timeseries Chart */}
            <div className="bg-white rounded-xl shadow-lg p-8">

              {isLoadingTimeseries ? (
                <div className="flex items-center justify-center py-12">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-ngodb-red"></div>
                  <span className="ml-3 text-ngodb-gray-600">{t('common.loading')}</span>
                </div>
              ) : timeseriesData.length > 0 ? (
                <div>
                  <MultiChart
                    data={timeseriesData.map(item => ({
                      label: item.year,
                      value: item.value
                    }))}
                    type="line"
                    title={`${getCurrentIndicatorName()} - ${profileData.country_info.name}`}
                    height={400}
                    onSummaryStats={setChartSummaryStats}
                  />

                  {/* Chart Summary Stats */}
                  {chartSummaryStats && (
                    <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-4">
                      <div className="text-center p-4 bg-ngodb-gray-50 rounded-lg">
                        <div className="text-2xl font-bold text-ngodb-red">
                          {chartSummaryStats.currentTotal}
                        </div>
                        <div className="text-sm text-ngodb-gray-600">
                          {t('countryProfile.currentValue')}
                        </div>
                      </div>
                      <div className="text-center p-4 bg-ngodb-gray-50 rounded-lg">
                        <div className="text-2xl font-bold text-ngodb-navy">
                          {chartSummaryStats.totalGrowth}%
                        </div>
                        <div className="text-sm text-ngodb-gray-600">
                          {t('countryProfile.totalGrowth')}
                        </div>
                      </div>
                      <div className="text-center p-4 bg-ngodb-gray-50 rounded-lg">
                        <div className="text-2xl font-bold text-ngodb-navy">
                          {chartSummaryStats.avgAnnualGrowth}%
                        </div>
                        <div className="text-sm text-ngodb-gray-600">
                          {t('countryProfile.avgAnnualGrowth')}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-center py-12">
                  <div className="text-ngodb-gray-500 mb-4">
                    <svg className="w-16 h-16 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                    </svg>
                  </div>
                  <p className="text-ngodb-gray-600 text-lg mb-2">
                    {t('countryProfile.noTimeseriesData')}
                  </p>
                  <p className="text-ngodb-gray-500 text-sm">
                    {t('countryProfile.noTimeseriesDataDescription')}
                  </p>
                </div>
              )}
            </div>

            {/* Additional Indicators Grid */}
            {allIndicators && allIndicators.length > 0 && (
              <div className="mt-12">
                <div className="text-center mb-8">
                  <h3 className="text-2xl font-bold text-ngodb-navy mb-4">
                    {t('countryProfile.allIndicators')}
                  </h3>
                  <p className="text-lg text-ngodb-gray-600 max-w-2xl mx-auto">
                    {t('countryProfile.allIndicatorsDescription')}
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {allIndicators.slice(3).map((indicator, index) => (
                    <div
                      key={`${indicator.indicator_label}-${index}`}
                      className="bg-white p-6 rounded-lg shadow-md hover:shadow-lg transition-shadow duration-200 border border-ngodb-gray-200"
                    >
                      <h4 className="text-lg font-semibold text-ngodb-navy mb-2 line-clamp-2">
                        {indicator.indicator_label}
                      </h4>

                      <div className="text-2xl font-bold text-ngodb-red mb-2">
                        {indicator.value?.toLocaleString() || 'N/A'}
                        {indicator.unit && (
                          <span className="text-sm text-ngodb-gray-500 ml-1">
                            {indicator.unit}
                          </span>
                        )}
                      </div>

                      {indicator.period && (
                        <p className="text-xs text-ngodb-gray-500 mb-3">
                          {t('countryProfile.period')}: {indicator.period}
                        </p>
                      )}

                      {/* Progress bar for visual appeal */}
                      <div className="w-full bg-ngodb-gray-200 rounded-full h-2 mb-2">
                        <div
                          className="bg-gradient-to-r from-ngodb-red to-ngodb-navy h-2 rounded-full transition-all duration-500"
                          style={{
                            width: `${Math.min(100, (indicator.value || 0) / Math.max(...allIndicators.map(i => i.value || 0)) * 100)}%`
                          }}
                        ></div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>

          {/* Documents Section - Filter out cover images */}
          <section id="documents">
          <DocumentsSection documents={documents.filter(doc => doc.document_type !== 'Cover Image')} t={t} />
          </section>

          {/* Back to Countries Link */}
          <div className="text-center mt-16">
            <Link
              href="/countries"
              className="inline-flex items-center px-8 py-4 bg-ngodb-navy text-white font-medium rounded-lg hover:bg-ngodb-navy-dark transition-colors shadow-lg hover:shadow-xl"
            >
              <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
              {t('countryProfile.actions.backToList')}
                </Link>
              </div>
        </div>
      </div>
    </>
  );
}
