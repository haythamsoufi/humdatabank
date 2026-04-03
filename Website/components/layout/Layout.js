// components/layout/Layout.js
import Navbar from './Navbar';
import Footer from './Footer';
import Head from 'next/head';
import Script from 'next/script';
import { useRouter } from 'next/router';
import { useState, useEffect } from 'react';
import { HydrationSafe } from '../ClientOnly';
import { ScopeProvider } from '../scope/ScopeContext';
import { getPublicOrganizationName } from '../../lib/publicOrgName';

export default function Layout({ children }) {
  const router = useRouter();
  const isRTL = router.locale === 'ar';
  const [isMobileApp, setIsMobileApp] = useState(false);

  // Server: read locale file. Client: parse SSR-embedded JSON so title/OG match locale + env org name.
  const initialTranslations = typeof window === 'undefined'
    ? (() => {
        try {
          const fs = require('fs');
          const path = require('path');
          const resolved = router?.locale || 'en';
          const filePath = path.join(process.cwd(), 'public', 'locales', resolved, 'common.json');
          if (fs.existsSync(filePath)) {
            return JSON.parse(fs.readFileSync(filePath, 'utf8'));
          }
        } catch (_) {}
        return {};
      })()
    : (() => {
        try {
          const el = typeof document !== 'undefined' && document.getElementById('__i18n');
          if (el && el.textContent) {
            return JSON.parse(el.textContent);
          }
        } catch (_) {}
        return {};
      })();

  const i18nSiteTitle = initialTranslations?.navigation?.siteTitle || 'NGO Databank';
  const defaultSiteTitle = getPublicOrganizationName(i18nSiteTitle);

  // Ensure consistent JSON stringification with proper escaping
  const i18nJson = (() => {
    try {
      // IMPORTANT: Keep this as valid JSON so the client can JSON.parse it.
      // Escaping `<` is sufficient to prevent `</script>`-style injection in a script tag.
      return JSON.stringify(initialTranslations).replace(/</g, '\\u003c');
    } catch (_) {
      return '{}';
    }
  })();

  // Detect if running in Flutter mobile app
  useEffect(() => {
    // Check for Flutter app indicators
    const checkMobileApp = () => {
      if (typeof window !== 'undefined') {
        // Check for window.isMobileApp flag set by Flutter app
        const isMobile = window.isMobileApp === true ||
                        window.NGODatabankMobileApp === true ||
                        window.IFRCMobileApp === true ||
                        document.documentElement.getAttribute('data-mobile-app') === 'true' ||
                        (typeof navigator !== 'undefined' &&
                         navigator.userAgent &&
                         (navigator.userAgent.includes('NGO-Databank-Flutter') ||
                          navigator.userAgent.includes('IFRC-Databank-Flutter')));

        setIsMobileApp(isMobile);

        // Add CSS class to body for additional styling if needed
        if (isMobile) {
          document.body.classList.add('mobile-app-view');
          document.documentElement.classList.add('mobile-app-view');
        } else {
          document.body.classList.remove('mobile-app-view');
          document.documentElement.classList.remove('mobile-app-view');
        }
      }
    };

    // Check immediately
    checkMobileApp();

    // Also check after a short delay to catch late injections
    const timeoutId = setTimeout(checkMobileApp, 100);

    // Watch for attribute changes (in case Flutter injects it later)
    const observer = new MutationObserver(checkMobileApp);
    if (typeof document !== 'undefined' && document.documentElement) {
      observer.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ['data-mobile-app']
      });
    }

    return () => {
      clearTimeout(timeoutId);
      observer.disconnect();
    };
  }, []);

  return (
    <>
      <Head>
        {/* Default Head tags, can be overridden by individual pages */}
        <title>{defaultSiteTitle}</title>
        <link rel="icon" href="/favicon.ico" /> {/* Make sure to add a favicon.ico to your /public folder */}
        <meta property="og:title" content={defaultSiteTitle} />
        <meta property="og:description" content={`Explore data, visualizations, and insights from ${defaultSiteTitle}.`} />
        {/* Add more OG tags, twitter cards etc. as needed */}
      </Head>
      {/* Use suppressHydrationWarning to prevent hydration mismatch for dynamic content */}
      <script
        id="__i18n"
        type="application/json"
        dangerouslySetInnerHTML={{ __html: i18nJson }}
        suppressHydrationWarning={true}
      />
      <Script src="/clear-cache.js" strategy="beforeInteractive" />
      <ScopeProvider>
        <div className={`flex flex-col min-h-screen ${isRTL ? 'rtl' : 'ltr'}`} dir={isRTL ? 'rtl' : 'ltr'}>
          {!isMobileApp && <Navbar />}
          <main className="flex-grow bg-ngodb-white"> {/* Set a default background */}
            <HydrationSafe fallback={<div />}>
              {children}
            </HydrationSafe>
          </main>
          {!isMobileApp && <Footer />}
        </div>
      </ScopeProvider>
    </>
  );
}
