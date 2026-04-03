// components/layout/Navbar.js
import Link from 'next/link';
import { useRouter } from 'next/router';
import { useState, useEffect, useMemo, useRef } from 'react'; // Import useState for mobile menu
import LanguageSwitcher from '../LanguageSwitcher';
import { useTranslation } from '../../lib/useTranslation';
import { getCountriesList } from '../../lib/apiService';
import CountriesDropdown from './CountriesDropdown';
import NSStructureDropdown from './NSStructureDropdown';
import { TranslationSafe } from '../ClientOnly';
import DemoBanner from '../DemoBanner';
import { useScope } from '../scope/ScopeContext';
import NSLogo from '../NSLogo';
import { getPublicOrganizationName } from '../../lib/publicOrgName';

export default function Navbar() {
  const router = useRouter();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false); // State for mobile menu
  const [analysisDropdownOpen, setAnalysisDropdownOpen] = useState(false); // State for analysis dropdown
  const [countriesDropdownOpen, setCountriesDropdownOpen] = useState(false); // State for countries dropdown
  const [countries, setCountries] = useState([]);
  const [loadingCountries, setLoadingCountries] = useState(false);
  const [currentCountryName, setCurrentCountryName] = useState(null); // State for current country name
  const [isOverWhiteBackground, setIsOverWhiteBackground] = useState(true); // Track if secondary bar is over white background (default to navy)
  const { t, locale, isLoaded } = useTranslation();
  const { scope, countryIso2, nationalSocietyName, isDemoMode } = useScope();
  const isNationalScope = scope?.type === 'country' && !!countryIso2;

  // Global title: NEXT_PUBLIC_ORGANIZATION_NAME or i18n (align with Backoffice branding)
  const i18nSiteTitle = t('navigation.siteTitle');
  const globalSiteTitle = getPublicOrganizationName(i18nSiteTitle);
  // In Arabic demo NS mode, place "Databank" before NS name
  const siteTitle = (isDemoMode && isNationalScope && nationalSocietyName)
    ? (locale === 'ar'
        ? `${t('navigation.databank')} ${nationalSocietyName}`
        : `${nationalSocietyName} ${t('navigation.databank')}`)
    : globalSiteTitle;
  const countriesDropdownRef = useRef(null);
  const nsStructureDropdownRef = useRef(null);
  const countriesButtonRef = useRef(null);
  const countriesButtonSecondaryRef = useRef(null);
  const countriesButtonMobileRef = useRef(null);
  const analysisButtonRef = useRef(null);
  const analysisButtonSecondaryRef = useRef(null);
  const secondaryBarRef = useRef(null);

  // Get country ID from countries list when we have a country scope
  const currentCountryId = useMemo(() => {
    if (!isNationalScope || !countryIso2 || !countries.length) return null;
    const country = countries.find(c => String(c?.iso2 || '').toUpperCase() === String(countryIso2).toUpperCase());
    return country?.id || null;
  }, [isNationalScope, countryIso2, countries]);

  // Determine if we should show NS Structure instead of Countries
  const showNSStructure = isDemoMode && isNationalScope && currentCountryId;

  // Handle click outside to close dropdowns
  useEffect(() => {
    function handleClickOutside(event) {
      // Check if click is outside the dropdown, button, and not on mobile menu items
      const isClickOnDesktopButton = countriesButtonRef.current && countriesButtonRef.current.contains(event.target);
      const isClickOnSecondaryButton = countriesButtonSecondaryRef.current && countriesButtonSecondaryRef.current.contains(event.target);
      const isClickOnMobileButton = countriesButtonMobileRef.current && countriesButtonMobileRef.current.contains(event.target);
      const isClickOnButton = isClickOnDesktopButton || isClickOnSecondaryButton || isClickOnMobileButton;
      const isClickInDropdown = countriesDropdownRef.current && countriesDropdownRef.current.contains(event.target);
      const isClickInNSStructureDropdown = nsStructureDropdownRef.current && nsStructureDropdownRef.current.contains(event.target);
      const isClickInMobileMenu = event.target.closest('#mobile-menu');
      const isClickInDataAttribute = event.target.closest('[data-countries-dropdown]') || event.target.closest('[data-ns-structure-dropdown]');

      if (countriesDropdownOpen &&
          !isClickOnButton &&
          !isClickInDropdown &&
          !isClickInNSStructureDropdown &&
          !isClickInMobileMenu &&
          !isClickInDataAttribute) {
        setCountriesDropdownOpen(false);
      }
    }

    if (countriesDropdownOpen) {
      // Use click instead of mousedown so it fires after button's onClick
      document.addEventListener('click', handleClickOutside);
    }

    return () => {
      document.removeEventListener('click', handleClickOutside);
    };
  }, [countriesDropdownOpen]);

  // Handle click outside to close analysis dropdown
  useEffect(() => {
    function handleClickOutside(event) {
      // Check if click is outside the analysis dropdown and button
      const analysisDropdown = document.querySelector('[data-analysis-dropdown]');
      const isClickOnPrimaryButton = analysisButtonRef.current && analysisButtonRef.current.contains(event.target);
      const isClickOnSecondaryButton = analysisButtonSecondaryRef.current && analysisButtonSecondaryRef.current.contains(event.target);
      const isClickOnButton = isClickOnPrimaryButton || isClickOnSecondaryButton;
      const isClickInDropdown = analysisDropdown && analysisDropdown.contains(event.target);

      if (analysisDropdownOpen && !isClickOnButton && !isClickInDropdown) {
        setAnalysisDropdownOpen(false);
      }
    }

    if (analysisDropdownOpen) {
      // Use click instead of mousedown so it fires after button's onClick
      document.addEventListener('click', handleClickOutside);
    }

    return () => {
      document.removeEventListener('click', handleClickOutside);
    };
  }, [analysisDropdownOpen]);

  const navItems = [
    { href: '/', label: 'navigation.home' },
    { href: '/indicator-bank', label: 'navigation.indicatorBank' },
    { href: '/resources', label: 'navigation.publications' },
  ];

  const analysisItems = [
    { href: '/dataviz', label: 'navigation.dataVisualization' },
    { href: '/disaggregation-analysis', label: 'navigation.disaggregationAnalysis' },
    { href: '/global-initiative', label: 'navigation.globalInitiative' },
    { href: '/unified-planning-reporting', label: 'navigation.unifiedPlanningReporting' },
  ];

  // Use NEXT_PUBLIC_API_URL when set (Fly/production), fallback to localhost in dev
  const backendBaseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5000';
  const backendLoginUrl = `${backendBaseUrl.replace(/\/$/, '')}/login`;

  // Check if any analysis item is active
  const isAnalysisActive = analysisItems.some(item =>
    router.pathname === item.href || (item.href !== '/' && router.pathname.startsWith(item.href))
  );

  // Check if countries dropdown should be active
  const isCountriesActive = router.pathname === '/countries' || router.pathname.startsWith('/countries');

  // Fetch countries data when component mounts or when dropdown opens
  useEffect(() => {
    if (countries.length === 0 && !loadingCountries) {
      const fetchCountries = async () => {
        try {
          setLoadingCountries(true);
          const countriesData = await getCountriesList(locale || 'en');
          setCountries(countriesData);
        } catch (error) {
          console.error('Failed to fetch countries:', error);
        } finally {
          setLoadingCountries(false);
        }
      };
      fetchCountries();
    }
  }, [countries.length, loadingCountries, locale]);

  // Detect current country and set country name when on a country page
  useEffect(() => {
    const isCountryPage = router.pathname.startsWith('/countries/') && router.query.iso3;

    if (isCountryPage && countries.length > 0) {
      const iso3 = router.query.iso3.toUpperCase();
      const country = countries.find(c => c.iso3 && c.iso3.toUpperCase() === iso3);
      if (country) {
        setCurrentCountryName(country.name);
      } else {
        setCurrentCountryName(null);
      }
    } else {
      setCurrentCountryName(null);
    }
  }, [router.pathname, router.query.iso3, countries]);

  // Detect if secondary bar is over white/light background and adjust styling
  useEffect(() => {
    if (typeof window === 'undefined') return;

    const checkBackgroundColor = () => {
      // Only check on md-xl screens where secondary bar is visible
      if (window.innerWidth < 768 || window.innerWidth >= 1280) {
        setIsOverWhiteBackground(false);
        return;
      }

      // Get the actual path - use asPath for the actual URL, fallback to pathname
      const actualPath = (router.asPath || router.pathname || '').split('?')[0];

      // Explicit list of pages with hero sections that extend behind navbar (transparent style)
      const heroSectionPages = [
        '/',
        '/disaggregation-analysis',
        '/api-builder',
        '/indicator-bank',
        '/global-initiative',
        '/unified-planning-reporting'
      ];

      // Check if current path is a country detail page (has dynamic route like /countries/[iso3])
      // But NOT the index page /countries or /countries/index
      const isCountryDetailPage = actualPath.startsWith('/countries/') &&
                                   actualPath !== '/countries' &&
                                   actualPath !== '/countries/index' &&
                                   actualPath.split('/').length > 2; // Must have something after /countries/

      const hasHeroSection = heroSectionPages.includes(actualPath) || isCountryDetailPage;

      // Default to navy unless we're explicitly on a hero section page
      // This ensures /countries (index) always gets navy
      const shouldBeNavy = !hasHeroSection;
      setIsOverWhiteBackground(shouldBeNavy);
    };

    // Check on mount and route change
    checkBackgroundColor();

    // Check on resize and scroll
    const handleResize = () => {
      checkBackgroundColor();
    };
    const handleScroll = () => {
      checkBackgroundColor();
    };

    window.addEventListener('resize', handleResize);
    window.addEventListener('scroll', handleScroll, { passive: true });

    return () => {
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('scroll', handleScroll);
    };
  }, [router.pathname]);

  // Helper component to render navigation items
  const renderNavigationItems = (isSecondaryBar = false) => {
    // Determine text colors based on whether secondary bar is over white background
    const textColorClass = isSecondaryBar && isOverWhiteBackground
      ? 'text-ngodb-white' // White text when over white background (navy bar)
      : 'text-ngodb-gray-300'; // Light gray text when over hero section (transparent bar)

    const hoverBgClass = isSecondaryBar && isOverWhiteBackground
      ? 'hover:bg-ngodb-navy-dark'
      : 'hover:bg-ngodb-gray-700';

    const hoverTextClass = isSecondaryBar && isOverWhiteBackground
      ? 'hover:text-ngodb-white'
      : 'hover:text-ngodb-white';

    return (
    <>
      {/* Home */}
      {router.pathname === '/' ? (
        <span className="px-2 sm:px-3 py-2 rounded-md text-xs sm:text-sm font-medium bg-ngodb-red text-white cursor-default">
          <TranslationSafe fallback="Global Overview">
            {t('navigation.home')}
          </TranslationSafe>
        </span>
      ) : (
        <Link
          href="/"
          className={`px-2 sm:px-3 py-2 rounded-md text-xs sm:text-sm font-medium transition-colors duration-150 ease-in-out ${textColorClass} ${hoverBgClass} ${hoverTextClass}`}
        >
          <TranslationSafe fallback="Global Overview">
            {t('navigation.home')}
          </TranslationSafe>
        </Link>
      )}

      {/* Countries Dropdown or NS Structure Dropdown */}
      <div className="relative" ref={isSecondaryBar ? countriesButtonSecondaryRef : countriesButtonRef}>
        <button
          onClick={(e) => {
            e.stopPropagation();
            // Close analysis dropdown if open
            if (analysisDropdownOpen) {
              setAnalysisDropdownOpen(false);
            }
            // Toggle countries/NS structure dropdown
            setCountriesDropdownOpen(!countriesDropdownOpen);
          }}
          className={`px-2 sm:px-3 py-2 rounded-md text-xs sm:text-sm font-medium transition-colors duration-150 ease-in-out flex items-center space-x-1
            ${
              isCountriesActive
                ? 'bg-ngodb-red text-white' // Active link style
                : `${textColorClass} ${hoverBgClass} ${hoverTextClass}`
            }`}
        >
          <span>
            {showNSStructure ? (
              <TranslationSafe fallback="Organizational Structure">
                {t('navigation.organizationalStructure')}
              </TranslationSafe>
            ) : (
              <TranslationSafe fallback={currentCountryName || "Countries"}>
                {currentCountryName || t('navigation.countries')}
              </TranslationSafe>
            )}
          </span>
          {loadingCountries ? (
            <div className="animate-spin rounded-full h-3 w-3 sm:h-4 sm:w-4 border-b-2 border-current"></div>
          ) : (
            <svg
              className={`w-3 h-3 sm:w-4 sm:h-4 transition-transform duration-200 ${countriesDropdownOpen ? 'rotate-180' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          )}
        </button>

        {/* Countries Dropdown Menu or NS Structure Dropdown */}
        {countriesDropdownOpen && !isSecondaryBar && (
          showNSStructure ? (
            <NSStructureDropdown
              countryId={currentCountryId}
              onClose={() => setCountriesDropdownOpen(false)}
              ref={nsStructureDropdownRef}
            />
          ) : (
            <CountriesDropdown
              countries={countries}
              loading={loadingCountries}
              onClose={() => setCountriesDropdownOpen(false)}
              ref={countriesDropdownRef}
            />
          )
        )}
        {countriesDropdownOpen && isSecondaryBar && (
          showNSStructure ? (
            <NSStructureDropdown
              countryId={currentCountryId}
              onClose={() => setCountriesDropdownOpen(false)}
              ref={nsStructureDropdownRef}
            />
          ) : (
            <CountriesDropdown
              countries={countries}
              loading={loadingCountries}
              onClose={() => setCountriesDropdownOpen(false)}
              ref={countriesDropdownRef}
            />
          )
        )}
      </div>

      {/* Analysis Dropdown */}
      <div className="relative" ref={isSecondaryBar ? analysisButtonSecondaryRef : analysisButtonRef}>
        <button
          onClick={(e) => {
            e.stopPropagation();
            // Close countries dropdown if open
            if (countriesDropdownOpen) {
              setCountriesDropdownOpen(false);
            }
            // Toggle analysis dropdown
            setAnalysisDropdownOpen(!analysisDropdownOpen);
          }}
          className={`px-2 sm:px-3 py-2 rounded-md text-xs sm:text-sm font-medium transition-colors duration-150 ease-in-out flex items-center space-x-1
            ${
              isAnalysisActive
                ? 'bg-ngodb-red text-white' // Active link style
                : `${textColorClass} ${hoverBgClass} ${hoverTextClass}`
            }`}
        >
          <span>
            <TranslationSafe fallback="Analysis">
              {t('navigation.analysis')}
            </TranslationSafe>
          </span>
          <svg
            className={`w-3 h-3 sm:w-4 sm:h-4 transition-transform duration-200 ${analysisDropdownOpen ? 'rotate-180' : ''}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {/* Dropdown Menu */}
        {analysisDropdownOpen && (
          <div className="absolute top-full left-0 mt-1 w-48 bg-ngodb-navy border border-ngodb-gray-700 rounded-md shadow-lg z-50" data-analysis-dropdown>
            <div className="py-1">
              {analysisItems.map((item) => {
                const isItemActive = router.pathname === item.href || (item.href !== '/' && router.pathname.startsWith(item.href));
                return isItemActive ? (
                  <span
                    key={item.label}
                    className="block px-4 py-2 text-sm bg-ngodb-red text-white cursor-default"
                  >
                    <TranslationSafe fallback={item.label.replace('navigation.', '').replace(/([A-Z])/g, ' $1').trim()}>
                      {t(item.label)}
                    </TranslationSafe>
                  </span>
                ) : (
                  <Link
                    key={item.label}
                    href={item.href}
                    className="block px-4 py-2 text-sm transition-colors duration-150 ease-in-out text-ngodb-gray-300 hover:bg-ngodb-gray-700 hover:text-ngodb-white"
                    onClick={() => setAnalysisDropdownOpen(false)}
                  >
                    <TranslationSafe fallback={item.label.replace('navigation.', '').replace(/([A-Z])/g, ' $1').trim()}>
                      {t(item.label)}
                    </TranslationSafe>
                  </Link>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Indicator Bank */}
      {router.pathname === '/indicator-bank' || router.pathname.startsWith('/indicator-bank') ? (
        <span className="px-2 sm:px-3 py-2 rounded-md text-xs sm:text-sm font-medium bg-ngodb-red text-white cursor-default">
          <TranslationSafe fallback="Indicator Bank">
            {t('navigation.indicatorBank')}
          </TranslationSafe>
        </span>
      ) : (
        <Link
          href="/indicator-bank"
          className={`px-2 sm:px-3 py-2 rounded-md text-xs sm:text-sm font-medium transition-colors duration-150 ease-in-out ${textColorClass} ${hoverBgClass} ${hoverTextClass}`}
        >
          <TranslationSafe fallback="Indicator Bank">
            {t('navigation.indicatorBank')}
          </TranslationSafe>
        </Link>
      )}

      {/* Resources */}
      {router.pathname === '/resources' || router.pathname.startsWith('/resources') ? (
        <span className="px-2 sm:px-3 py-2 rounded-md text-xs sm:text-sm font-medium bg-ngodb-red text-white cursor-default">
          <TranslationSafe fallback="Resources">
            {t('navigation.publications')}
          </TranslationSafe>
        </span>
      ) : (
        <Link
          href="/resources"
          className={`px-2 sm:px-3 py-2 rounded-md text-xs sm:text-sm font-medium transition-colors duration-150 ease-in-out ${textColorClass} ${hoverBgClass} ${hoverTextClass}`}
        >
          <TranslationSafe fallback="Resources">
            {t('navigation.publications')}
          </TranslationSafe>
        </Link>
      )}

      {/* Desktop Login Button - Only show in primary bar */}
      {!isSecondaryBar && (
        <a
          href={backendLoginUrl}
          className="px-3 sm:px-4 py-2 rounded-md text-xs sm:text-sm font-medium bg-ngodb-gray-600 text-ngodb-white hover:bg-ngodb-gray-500 transition-colors duration-150 ease-in-out border border-ngodb-gray-500 hover:border-ngodb-gray-400"
        >
          <TranslationSafe fallback="Login">
            {t('navigation.login')}
          </TranslationSafe>
        </a>
      )}
    </>
    );
  };

  return (
    <header className="text-ngodb-white shadow-lg sticky top-0 z-[9999]"> {/* Default text color for header is white */}
      <DemoBanner />
      <div className="w-full"> {/* Reduced padding on small screens */}
        {/* Primary Bar - Logo, Title, Language Switcher, Login, Mobile Menu */}
        <div className="flex items-center justify-between h-20 bg-ngodb-navy px-4 sm:px-6 lg:px-8">
          {/* Logo and Site Title - Allow wrapping and reduce gap */}
          <div className="flex-shrink-0 min-w-0 flex-1"> {/* Allow flex-1 to take available space */}
            <Link href="/" className="flex items-center space-x-2 rtl:space-x-reverse"> {/* Reduced space-x from 3 to 2 */}
              {/* Hide logo only on md screens (trying to fit in primary bar), show again when secondary bar appears (lg+) */}
              <NSLogo
                className="block md:hidden lg:block"
                size="default"
              />
              <span className="self-center text-sm sm:text-lg lg:text-xl font-semibold text-ngodb-white break-words"> {/* Allow text wrapping and responsive sizing */}
                <TranslationSafe fallback="NGO Databank">
                  {siteTitle}
                </TranslationSafe>
              </span>
            </Link>
          </div>

          {/* Right side content - Ensure it doesn't push menu button off screen */}
          <div className="flex items-center space-x-2 sm:space-x-4 flex-shrink-0"> {/* Reduced spacing and ensure no shrinking */}
            {/* Navigation Links - Desktop - Show on xl+ screens only in primary bar */}
            <nav className="hidden xl:flex items-center space-x-3 lg:space-x-6 xl:space-x-8"> {/* Reduced spacing */}
              {renderNavigationItems(false)}
            </nav>

            {/* Language Switcher - Always visible */}
            <LanguageSwitcher />

            {/* Mobile Menu Button - Only visible on mobile screens */}
            <div className="flex items-center flex-shrink-0 md:hidden">
              <button
                type="button"
                className="text-ngodb-gray-300 hover:text-ngodb-white focus:outline-none focus:ring-2 focus:ring-inset focus:ring-ngodb-white p-1"
                aria-controls="mobile-menu"
                aria-expanded={mobileMenuOpen}
                onClick={() => setMobileMenuOpen(!mobileMenuOpen)} // Toggle state
              >
                <span className="sr-only">
                  <TranslationSafe fallback="Open main menu">
                    {t('navigation.openMainMenu')}
                  </TranslationSafe>
                </span>
                <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16m-7 6h7" />
                </svg>
              </button>
            </div>
          </div>
        </div>

        {/* Secondary Bar - Navigation items on large screens (only show if hiding logo isn't enough) */}
        <nav
          ref={secondaryBarRef}
          className={`hidden lg:flex xl:hidden items-center justify-center space-x-3 lg:space-x-6 py-3 px-4 sm:px-6 lg:px-8 border-t relative z-50 transition-all duration-300 backdrop-blur-xl ${
            isOverWhiteBackground
              ? 'border-ngodb-gray-300'
              : 'border-white/10'
          }`}
          style={{
            backgroundColor: isOverWhiteBackground
              ? 'rgba(1, 30, 65, 0.98)' // Nearly solid navy with slight transparency for glassmorphism
              : 'rgba(0, 0, 0, 0.15)' // Transparent dark when over hero section
          }}
        >
          {renderNavigationItems(true)}
        </nav>
      </div>

      {/* Mobile Menu */}
      <div className={`${mobileMenuOpen ? 'block' : 'hidden'} md:hidden absolute top-full left-0 w-full bg-ngodb-navy shadow-lg`} id="mobile-menu">
        <div className="px-2 pt-2 pb-3 sm:px-3 flex flex-wrap gap-2">
          {/* Home */}
          {router.pathname === '/' ? (
            <span className="inline-flex items-center px-3 py-2 rounded-md text-sm font-medium bg-ngodb-red text-white cursor-default">
              <TranslationSafe fallback="Global Overview">
                {t('navigation.home')}
              </TranslationSafe>
            </span>
          ) : (
            <Link
              href="/"
              onClick={() => setMobileMenuOpen(false)} // Close menu on click
              className="inline-flex items-center px-3 py-2 rounded-md text-sm font-medium text-ngodb-gray-300 hover:bg-ngodb-gray-700 hover:text-ngodb-white"
            >
              <TranslationSafe fallback="Global Overview">
                {t('navigation.home')}
              </TranslationSafe>
            </Link>
          )}

          {/* Countries or NS Structure - Mobile with Dropdown */}
          <div className="relative" ref={countriesButtonMobileRef}>
            <button
              onClick={(e) => {
                e.stopPropagation();
                // Close analysis dropdown if open
                if (analysisDropdownOpen) {
                  setAnalysisDropdownOpen(false);
                }
                // Toggle countries/NS structure dropdown
                setCountriesDropdownOpen(!countriesDropdownOpen);
              }}
              className={`inline-flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium w-full justify-between
                ${
                  isCountriesActive
                    ? 'bg-ngodb-red text-white'
                    : 'text-ngodb-gray-300 hover:bg-ngodb-gray-700 hover:text-ngodb-white'
                }`}
            >
              <span>
                {showNSStructure ? (
                  <TranslationSafe fallback="Organizational Structure">
                    {t('navigation.organizationalStructure')}
                  </TranslationSafe>
                ) : (
                  <TranslationSafe fallback={currentCountryName || "Countries"}>
                    {currentCountryName || t('navigation.countries')}
                  </TranslationSafe>
                )}
              </span>
              {loadingCountries ? (
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-current"></div>
              ) : (
                <svg
                  className={`w-4 h-4 transition-transform duration-200 ${countriesDropdownOpen ? 'rotate-180' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              )}
            </button>

            {/* Mobile Countries Dropdown or NS Structure Dropdown */}
            {countriesDropdownOpen && (
              <div className="mt-2 w-full">
                {showNSStructure ? (
                  <NSStructureDropdown
                    countryId={currentCountryId}
                    onClose={() => {
                      setCountriesDropdownOpen(false);
                      setMobileMenuOpen(false);
                    }}
                    ref={nsStructureDropdownRef}
                  />
                ) : (
                  <CountriesDropdown
                    countries={countries}
                    loading={loadingCountries}
                    onClose={() => {
                      setCountriesDropdownOpen(false);
                      setMobileMenuOpen(false);
                    }}
                    ref={countriesDropdownRef}
                  />
                )}
              </div>
            )}
          </div>

          {/* Analysis Section in Mobile Menu */}
          <div className="border-t border-ngodb-gray-700 pt-2 mt-2 flex flex-wrap gap-2 items-start">
            <div className="basis-full px-1 py-1 text-xs font-medium text-ngodb-gray-400">
              <TranslationSafe fallback="Analysis">
                {t('navigation.analysis')}
              </TranslationSafe>
            </div>
            {analysisItems.map((item) => {
              const isItemActive = router.pathname === item.href || (item.href !== '/' && router.pathname.startsWith(item.href));
              return isItemActive ? (
                <span
                  key={item.label}
                  className="inline-flex items-center px-3 py-2 rounded-md text-sm font-medium bg-ngodb-red text-white cursor-default"
                >
                  <TranslationSafe fallback={item.label.replace('navigation.', '').replace(/([A-Z])/g, ' $1').trim()}>
                    {t(item.label)}
                  </TranslationSafe>
                </span>
              ) : (
                <Link
                  key={item.label}
                  href={item.href}
                  onClick={() => setMobileMenuOpen(false)} // Close menu on click
                  className="inline-flex items-center px-3 py-2 rounded-md text-sm font-medium text-ngodb-gray-300 hover:bg-ngodb-gray-700 hover:text-ngodb-white"
                >
                  <TranslationSafe fallback={item.label.replace('navigation.', '').replace(/([A-Z])/g, ' $1').trim()}>
                    {t(item.label)}
                  </TranslationSafe>
                </Link>
              );
            })}
          </div>

          {/* Indicator Bank */}
          {router.pathname === '/indicator-bank' || router.pathname.startsWith('/indicator-bank') ? (
            <span className="inline-flex items-center px-3 py-2 rounded-md text-sm font-medium bg-ngodb-red text-white cursor-default">
              <TranslationSafe fallback="Indicator Bank">
                {t('navigation.indicatorBank')}
              </TranslationSafe>
            </span>
          ) : (
            <Link
              href="/indicator-bank"
              onClick={() => setMobileMenuOpen(false)} // Close menu on click
              className="inline-flex items-center px-3 py-2 rounded-md text-sm font-medium text-ngodb-gray-300 hover:bg-ngodb-gray-700 hover:text-ngodb-white"
            >
              <TranslationSafe fallback="Indicator Bank">
                {t('navigation.indicatorBank')}
              </TranslationSafe>
            </Link>
          )}

          {/* Resources */}
          {router.pathname === '/resources' || router.pathname.startsWith('/resources') ? (
            <span className="inline-flex items-center px-3 py-2 rounded-md text-sm font-medium bg-ngodb-red text-white cursor-default">
              <TranslationSafe fallback="Resources">
                {t('navigation.publications')}
              </TranslationSafe>
            </span>
          ) : (
            <Link
              href="/resources"
              onClick={() => setMobileMenuOpen(false)} // Close menu on click
              className="inline-flex items-center px-3 py-2 rounded-md text-sm font-medium text-ngodb-gray-300 hover:bg-ngodb-gray-700 hover:text-ngodb-white"
            >
              <TranslationSafe fallback="Resources">
                {t('navigation.publications')}
              </TranslationSafe>
            </Link>
          )}

          {/* Mobile Login Button - Opens in the same tab */}
          <a
            href={backendLoginUrl}
            onClick={() => setMobileMenuOpen(false)} // Close menu on click
            className="inline-flex items-center px-3 py-2 rounded-md text-sm font-medium bg-ngodb-gray-600 text-ngodb-white hover:bg-ngodb-gray-500 border border-ngodb-gray-500 hover:border-ngodb-gray-400 transition-colors duration-150 ease-in-out" // Updated styling to match desktop
          >
            <TranslationSafe fallback="Login">
              {t('navigation.login')}
            </TranslationSafe>
          </a>
        </div>
      </div>
    </header>
  );
}
