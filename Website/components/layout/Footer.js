// components/layout/Footer.js
import { useTranslation } from '../../lib/useTranslation';
import Link from 'next/link';
import { TranslationSafe } from '../ClientOnly';
import { useScope } from '../scope/ScopeContext';
import NSLogo from '../NSLogo';
import { getPublicOrganizationName } from '../../lib/publicOrgName';

export default function Footer() {
  const currentYear = new Date().getFullYear();
  const { t, isLoaded, locale } = useTranslation();
  const { scope, countryIso2, nationalSocietyName, isDemoMode } = useScope();
  const isNationalScope = scope?.type === 'country' && !!countryIso2;
  const isRTL = locale === 'ar';

  const i18nSiteTitle = t('navigation.siteTitle');
  const globalSiteTitle = getPublicOrganizationName(i18nSiteTitle);
  const siteTitle = (isDemoMode && isNationalScope && nationalSocietyName)
    ? `${nationalSocietyName} ${t('navigation.databank')}`
    : globalSiteTitle;

  const organizationName = (isDemoMode && isNationalScope && nationalSocietyName)
    ? nationalSocietyName
    : globalSiteTitle;

  return (
    <footer className="bg-ngodb-navy text-ngodb-gray-300 py-8" dir={isRTL ? 'rtl' : 'ltr'}>
      <div className="w-full px-6 sm:px-8 lg:px-12">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 lg:gap-8 mb-8">
          {/* Main Footer Content */}
          <div
            className={isRTL ? 'lg:col-span-4' : 'text-center sm:text-left lg:col-span-4'}
            style={isRTL ? { textAlign: 'right' } : undefined}
          >
            <div className="mb-4">
              <div className={isRTL ? 'flex justify-start w-full' : ''}>
                <NSLogo
                  className={`${isRTL ? '' : 'mx-auto sm:ml-0'} mb-2`}
                  size="medium"
                />
              </div>
              <p className="text-sm">
                <TranslationSafe fallback={globalSiteTitle}>
                  {organizationName}
                </TranslationSafe>
              </p>
            </div>
            <div className="text-xs mb-2">
              <a href="#" className="hover:text-ngodb-red mx-2 transition-colors">
                <TranslationSafe fallback="Privacy">
                  {t('footer.privacy')}
                </TranslationSafe>
              </a> |
              <a href="#" className="hover:text-ngodb-red mx-2 transition-colors">
                <TranslationSafe fallback="Terms">
                  {t('footer.terms')}
                </TranslationSafe>
              </a> |
              <a href="#" className="hover:text-ngodb-red mx-2 transition-colors">
                <TranslationSafe fallback="Contact">
                  {t('footer.contact')}
                </TranslationSafe>
              </a>
            </div>
            <p className="text-xs">
              <TranslationSafe fallback={`© ${currentYear} ${siteTitle}. All rights reserved.`}>
                {(() => {
                  let c = t('footer.copyright').replace(/\b2024\b/g, String(currentYear));
                  if (c.includes('{orgName}')) {
                    return c.replace(/\{orgName\}/g, siteTitle);
                  }
                  return c.replace(/NGO Databank/g, siteTitle);
                })()}
              </TranslationSafe>
            </p>
            <p className="text-xs mt-2">
              <TranslationSafe fallback="Built by Haytham Alsoufi, volunteer of Syrian Arab Red Crescent">
                {t('footer.developedBy')}
              </TranslationSafe>
            </p>
          </div>

          {/* Mobile Apps Section */}
          <div className="text-center lg:col-span-3">
            <div className="bg-gradient-to-r from-ngodb-green/20 to-ngodb-blue-600/20 backdrop-blur-sm border border-ngodb-green/30 rounded-xl p-4 shadow-lg h-full">
              <div className="flex items-center justify-center mb-3">
                <div className={`bg-ngodb-green/20 rounded-full p-2 ${isRTL ? 'ml-3' : 'mr-3'}`}>
                  <svg className="w-6 h-6 text-ngodb-green" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" />
                  </svg>
                </div>
                <h3 className="text-ngodb-white font-semibold text-lg">
                  <TranslationSafe fallback="Mobile Apps">
                    {t('footer.mobileApps.title')}
                  </TranslationSafe>
                </h3>
              </div>
              <p className="text-sm mb-4 text-ngodb-gray-300 leading-relaxed">
                <TranslationSafe fallback="Download our mobile app for Android and iOS devices">
                  {t('footer.mobileApps.description')}
                </TranslationSafe>
              </p>
              <div className="flex items-center justify-center gap-4">
                <Link
                  href="/download-apps"
                  className="inline-flex items-center justify-center w-10 h-10 bg-ngodb-green/20 hover:bg-ngodb-green/30 rounded-full transition-all duration-200 group"
                  title={t('footer.mobileApps.downloadAndroid')}
                  aria-label={t('footer.mobileApps.downloadAndroid')}
                >
                  <svg className="w-6 h-6 text-ngodb-green group-hover:scale-110 transition-transform" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M23.35 12.653l2.496-4.323c0.044-0.074 0.070-0.164 0.070-0.26 0-0.287-0.232-0.519-0.519-0.519-0.191 0-0.358 0.103-0.448 0.257l-0.001 0.002-2.527 4.377c-1.887-0.867-4.094-1.373-6.419-1.373s-4.532 0.506-6.517 1.413l0.098-0.040-2.527-4.378c-0.091-0.156-0.259-0.26-0.45-0.26-0.287 0-0.519 0.232-0.519 0.519 0 0.096 0.026 0.185 0.071 0.262l-0.001-0.002 2.496 4.323c-4.286 2.367-7.236 6.697-7.643 11.744l-0.003 0.052h29.991c-0.41-5.099-3.36-9.429-7.57-11.758l-0.076-0.038zM9.098 20.176c-0 0-0 0-0 0-0.69 0-1.249-0.559-1.249-1.249s0.559-1.249 1.249-1.249c0.69 0 1.249 0.559 1.249 1.249v0c-0.001 0.689-0.559 1.248-1.249 1.249h-0zM22.902 20.176c-0 0-0 0-0 0-0.69 0-1.249-0.559-1.249-1.249s0.559-1.249 1.249-1.249c0.69 0 1.249 0.559 1.249 1.249v0c-0.001 0.689-0.559 1.248-1.249 1.249h-0z" fill="currentColor"/>
                  </svg>
                </Link>
                <Link
                  href="/download-apps"
                  className="inline-flex items-center justify-center w-10 h-10 bg-ngodb-blue-600/20 hover:bg-ngodb-blue-600/30 rounded-full transition-all duration-200 group"
                  title={t('footer.mobileApps.downloadIOS')}
                  aria-label={t('footer.mobileApps.downloadIOS')}
                >
                  <img
                    src="/icons/apple.svg"
                    alt="Apple"
                    className="w-6 h-6 group-hover:scale-110 transition-transform"
                    style={{
                      filter: 'brightness(0) saturate(100%) invert(27%) sepia(100%) saturate(5000%) hue-rotate(210deg) brightness(0.95) contrast(1.1)',
                      display: 'block',
                      margin: '0 auto'
                    }}
                  />
                </Link>
              </div>
            </div>
          </div>

          {/* API Builder Special Section */}
          <div className={`text-center lg:${isRTL ? 'text-left' : 'text-right'} lg:col-span-5`}>
            <div className="bg-gradient-to-r from-ngodb-red/20 to-ngodb-red/10 backdrop-blur-sm border border-ngodb-red/30 rounded-xl p-6 shadow-lg h-full">
              <div className={`flex items-center justify-center lg:${isRTL ? 'justify-start' : 'justify-end'} mb-3`}>
                <div className={`bg-ngodb-red/20 rounded-full p-2 ${isRTL ? 'ml-3' : 'mr-3'}`}>
                  <svg className="w-5 h-5 text-ngodb-red" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                  </svg>
                </div>
                <h3 className="text-ngodb-white font-semibold text-lg">
                  <TranslationSafe fallback="Developer Tools">
                    {t('footer.developerTools.title')}
                  </TranslationSafe>
                </h3>
              </div>
              <p className="text-sm mb-4 text-ngodb-gray-300 leading-relaxed">
                <TranslationSafe fallback="Build and test API queries with our interactive builder. Access comprehensive documentation and examples.">
                  {t('footer.developerTools.description')} {t('footer.developerTools.moreInfo')}
                </TranslationSafe>
              </p>
              <div className={`flex items-center justify-center lg:${isRTL ? 'justify-start' : 'justify-end'} gap-4`}>
                <Link
                  href="/api-builder#docs"
                  className="inline-flex items-center justify-center w-10 h-10 bg-ngodb-red/20 hover:bg-ngodb-red/30 border border-ngodb-red/30 rounded-full transition-all duration-200 group"
                  title="Read API Documentation"
                  aria-label="Read API Documentation"
                >
                  <svg className="w-5 h-5 text-ngodb-red group-hover:scale-110 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 20h9" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16.5 3.5A2.5 2.5 0 0119 6v9a2 2 0 01-2 2H7a2 2 0 01-2-2V6a2.5 2.5 0 012.5-2.5H16.5z" />
                  </svg>
                </Link>
                <Link
                  href="/api-builder/#builder"
                  className="inline-flex items-center justify-center w-10 h-10 bg-ngodb-red/20 hover:bg-ngodb-red/30 border border-ngodb-red/30 rounded-full transition-all duration-200 group"
                  title={t('navigation.apiBuilder')}
                  aria-label={t('navigation.apiBuilder')}
                >
                  <svg className="w-5 h-5 text-ngodb-red group-hover:scale-110 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                  </svg>
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
