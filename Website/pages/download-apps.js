// pages/download-apps.js
import Head from 'next/head';
import { useTranslation } from '../lib/useTranslation';
import { TranslationSafe } from '../components/ClientOnly';

function isAllowedEmbedUrl(url) {
  if (!url || typeof url !== 'string') return false;
  try {
    const u = new URL(url.trim());
    return u.protocol === 'https:' || u.protocol === 'http:';
  } catch {
    return false;
  }
}

/**
 * Appetize browser embeds require a plan that includes embedding; disabled until upgraded.
 * Set to true to show Android/iOS iframe demos again.
 */
const ENABLE_APPETIZE_BROWSER_DEMOS = false;

/** Default Appetize.io embeds (override with ANDROID_DEMO_EMBED_URL / IOS_DEMO_EMBED_URL or NEXT_PUBLIC_*). */
const DEFAULT_APPETIZE_ANDROID_EMBED =
  'https://appetize.io/embed/b_erwrjl54m4twliwpe2hdn7glim';
const DEFAULT_APPETIZE_IOS_EMBED =
  'https://appetize.io/embed/b_oe7tcyhr5pjr7jzwjlikugbkty';

export default function DownloadAppsPage({ androidDemoEmbedUrl = '', iosDemoEmbedUrl = '' }) {
  const { t, isLoaded } = useTranslation();

  const handleDownload = (platform, filename) => {
    // Use API route to ensure proper download headers with Content-Disposition: attachment
    // This forces the browser/webview to download the file instead of displaying it
    const downloadUrl = `/api/download-app?filename=${encodeURIComponent(filename)}`;

    // Use window.location.href for maximum compatibility with webviews
    // The API route sets proper headers to force download
    window.location.href = downloadUrl;
  };

  // Prevent rendering until translations are loaded to avoid hydration mismatches
  if (!isLoaded) {
    return (
      <div className="w-full px-6 sm:px-8 lg:px-12 py-8">
        <Head>
          <title>Download Mobile Apps - Humanitarian Databank</title>
        </Head>
        <div className="text-center py-20">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-humdb-red mb-4"></div>
          <h1 className="text-3xl font-bold text-humdb-navy mb-2">Loading...</h1>
        </div>
      </div>
    );
  }

  return (
    <>
      <Head>
        <title>{`${t('downloadApps.title')} - Humanitarian Databank`}</title>
        <meta name="description" content={t('downloadApps.meta.description')} />
      </Head>

      <div className="bg-humdb-gray-100 min-h-screen">
        <div className="w-full h-full px-4 sm:px-6 lg:px-12 py-6 sm:py-8 lg:py-10">
          {/* Hero Section */}
          <div className="text-center mb-8 sm:mb-12">
            <h1 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-humdb-navy mb-3 sm:mb-4">
              <TranslationSafe fallback="Download Mobile Apps">
                {t('downloadApps.hero.title')}
              </TranslationSafe>
            </h1>
            <p className="text-base sm:text-lg text-humdb-gray-600 max-w-2xl mx-auto px-4">
              <TranslationSafe fallback="Get the Humanitarian Databank mobile app for Android and iOS devices.">
                {t('downloadApps.hero.description')}
              </TranslationSafe>
            </p>
          </div>

          {ENABLE_APPETIZE_BROWSER_DEMOS ? (
            <div className="max-w-4xl mx-auto mb-8 sm:mb-12">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 sm:gap-8">
                <div className="bg-white rounded-xl shadow-lg border-2 border-humdb-gray-200 p-6 sm:p-8">
                  <h2 className="text-2xl font-bold text-humdb-navy mb-2 text-center">
                    <TranslationSafe fallback="Try the Android app in your browser">
                      {t('downloadApps.demo.title')}
                    </TranslationSafe>
                  </h2>
                  <p className="text-sm sm:text-base text-humdb-gray-600 text-center mb-6 max-w-2xl mx-auto">
                    <TranslationSafe fallback="Interactive demo on a cloud Android device. No install required.">
                      {t('downloadApps.demo.description')}
                    </TranslationSafe>
                  </p>
                  {isAllowedEmbedUrl(androidDemoEmbedUrl) ? (
                    <div className="relative w-full max-w-[400px] mx-auto rounded-xl overflow-hidden border border-humdb-gray-200 bg-humdb-gray-900 shadow-inner aspect-[9/16] max-h-[min(85vh,820px)]">
                      <iframe
                        title="Humanitarian Databank Android demo"
                        src={androidDemoEmbedUrl}
                        className="absolute inset-0 w-full h-full border-0"
                        loading="lazy"
                        referrerPolicy="no-referrer-when-downgrade"
                        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                      />
                    </div>
                  ) : (
                    <p className="text-sm text-humdb-gray-600 text-center max-w-xl mx-auto py-4 px-4 bg-humdb-gray-50 rounded-lg border border-dashed border-humdb-gray-300">
                      <TranslationSafe fallback="Browser demo is not configured yet. Set ANDROID_DEMO_EMBED_URL (or NEXT_PUBLIC_ANDROID_DEMO_EMBED_URL) to your hosted emulator embed link, or download the APK above.">
                        {t('downloadApps.demo.unavailable')}
                      </TranslationSafe>
                    </p>
                  )}
                </div>

                <div className="bg-white rounded-xl shadow-lg border-2 border-humdb-gray-200 p-6 sm:p-8">
                  <h2 className="text-2xl font-bold text-humdb-navy mb-2 text-center">
                    <TranslationSafe fallback="Try the iOS app in your browser">
                      {t('downloadApps.demo.iosTitle')}
                    </TranslationSafe>
                  </h2>
                  <p className="text-sm sm:text-base text-humdb-gray-600 text-center mb-6 max-w-2xl mx-auto">
                    <TranslationSafe fallback="Interactive demo on a cloud iOS device. No install required.">
                      {t('downloadApps.demo.iosDescription')}
                    </TranslationSafe>
                  </p>
                  {isAllowedEmbedUrl(iosDemoEmbedUrl) ? (
                    <div className="relative w-full max-w-[400px] mx-auto rounded-xl overflow-hidden border border-humdb-gray-200 bg-humdb-gray-900 shadow-inner aspect-[9/16] max-h-[min(85vh,820px)]">
                      <iframe
                        title="Humanitarian Databank iOS demo"
                        src={iosDemoEmbedUrl}
                        className="absolute inset-0 w-full h-full border-0"
                        loading="lazy"
                        referrerPolicy="no-referrer-when-downgrade"
                        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                      />
                    </div>
                  ) : (
                    <p className="text-sm text-humdb-gray-600 text-center max-w-xl mx-auto py-4 px-4 bg-humdb-gray-50 rounded-lg border border-dashed border-humdb-gray-300">
                      <TranslationSafe fallback="iOS browser demo is not configured yet. Set IOS_DEMO_EMBED_URL (or NEXT_PUBLIC_IOS_DEMO_EMBED_URL) to your Appetize embed link, or download the IPA above.">
                        {t('downloadApps.demo.iosUnavailable')}
                      </TranslationSafe>
                    </p>
                  )}
                </div>
              </div>
            </div>
          ) : null}

          {/* Download Cards */}
          <div className="max-w-4xl mx-auto grid grid-cols-1 md:grid-cols-2 gap-6 sm:gap-8">
            {/* Android APK Card */}
            <div className="bg-white rounded-xl shadow-lg border-2 border-humdb-gray-200 p-6 sm:p-8 hover:shadow-xl transition-shadow duration-300">
              <div className="text-center">
                <div className="mb-6 flex justify-center">
                  <div className="bg-humdb-green/10 rounded-full p-6">
                    <svg className="w-16 h-16 text-humdb-green" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <path d="M23.35 12.653l2.496-4.323c0.044-0.074 0.070-0.164 0.070-0.26 0-0.287-0.232-0.519-0.519-0.519-0.191 0-0.358 0.103-0.448 0.257l-0.001 0.002-2.527 4.377c-1.887-0.867-4.094-1.373-6.419-1.373s-4.532 0.506-6.517 1.413l0.098-0.040-2.527-4.378c-0.091-0.156-0.259-0.26-0.45-0.26-0.287 0-0.519 0.232-0.519 0.519 0 0.096 0.026 0.185 0.071 0.262l-0.001-0.002 2.496 4.323c-4.286 2.367-7.236 6.697-7.643 11.744l-0.003 0.052h29.991c-0.41-5.099-3.36-9.429-7.57-11.758l-0.076-0.038zM9.098 20.176c-0 0-0 0-0 0-0.69 0-1.249-0.559-1.249-1.249s0.559-1.249 1.249-1.249c0.69 0 1.249 0.559 1.249 1.249v0c-0.001 0.689-0.559 1.248-1.249 1.249h-0zM22.902 20.176c-0 0-0 0-0 0-0.69 0-1.249-0.559-1.249-1.249s0.559-1.249 1.249-1.249c0.69 0 1.249 0.559 1.249 1.249v0c-0.001 0.689-0.559 1.248-1.249 1.249h-0z" fill="currentColor"/>
                    </svg>
                  </div>
                </div>
                <h2 className="text-2xl font-bold text-humdb-navy mb-3">
                  <TranslationSafe fallback="Android App">
                    {t('downloadApps.android.title')}
                  </TranslationSafe>
                </h2>
                <p className="text-humdb-gray-600 mb-6 text-sm sm:text-base">
                  <TranslationSafe fallback="Download the APK file for Android devices">
                    {t('downloadApps.android.description')}
                  </TranslationSafe>
                </p>
                <button
                  onClick={() => handleDownload('android', 'databank.apk')}
                  className="w-full bg-humdb-green hover:bg-humdb-green-dark text-white font-semibold py-3 px-6 rounded-lg transition-colors duration-200 flex items-center justify-center"
                >
                  <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  <TranslationSafe fallback="Download APK">
                    {t('downloadApps.android.downloadButton')}
                  </TranslationSafe>
                </button>
                <p className="text-xs text-humdb-gray-500 mt-4">
                  <TranslationSafe fallback="Version 1.0.0">
                    {t('downloadApps.android.version')}
                  </TranslationSafe>
                </p>
              </div>
            </div>

            {/* iOS IPA Card */}
            <div className="bg-white rounded-xl shadow-lg border-2 border-humdb-gray-200 p-6 sm:p-8 hover:shadow-xl transition-shadow duration-300">
              <div className="text-center">
                <div className="mb-6 flex justify-center">
                  <div className="bg-humdb-blue-100 rounded-full p-6 flex items-center justify-center">
                    <img
                      src="/icons/apple.svg"
                      alt="Apple"
                      className="w-16 h-16"
                      style={{
                        filter: 'brightness(0) saturate(100%) invert(27%) sepia(100%) saturate(5000%) hue-rotate(210deg) brightness(0.95) contrast(1.1)',
                        display: 'block'
                      }}
                    />
                  </div>
                </div>
                <h2 className="text-2xl font-bold text-humdb-navy mb-3">
                  <TranslationSafe fallback="iOS App">
                    {t('downloadApps.ios.title')}
                  </TranslationSafe>
                </h2>
                <p className="text-humdb-gray-600 mb-6 text-sm sm:text-base">
                  <TranslationSafe fallback="Download the IPA file for iOS devices">
                    {t('downloadApps.ios.description')}
                  </TranslationSafe>
                </p>
                <button
                  onClick={() => handleDownload('ios', 'databank.ipa')}
                  className="w-full bg-humdb-blue-600 hover:bg-humdb-blue-700 text-white font-semibold py-3 px-6 rounded-lg transition-colors duration-200 flex items-center justify-center"
                >
                  <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  <TranslationSafe fallback="Download IPA">
                    {t('downloadApps.ios.downloadButton')}
                  </TranslationSafe>
                </button>
                <p className="text-xs text-humdb-gray-500 mt-4">
                  <TranslationSafe fallback="Version 1.0.0">
                    {t('downloadApps.ios.version')}
                  </TranslationSafe>
                </p>
              </div>
            </div>
          </div>

          {/* Instructions Section */}
          <div className="max-w-4xl mx-auto mt-8 sm:mt-12">
            <div className="bg-white rounded-xl shadow-lg border-2 border-humdb-gray-200 p-6 sm:p-8">
              <h2 className="text-2xl font-bold text-humdb-navy mb-4">
                <TranslationSafe fallback="Installation Instructions">
                  {t('downloadApps.instructions.title')}
                </TranslationSafe>
              </h2>

              <div className="space-y-6">
                {/* Android Instructions */}
                <div>
                  <h3 className="text-lg font-semibold text-humdb-navy mb-3 flex items-center">
                    <svg className="w-5 h-5 mr-2 text-humdb-green" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <path d="M23.35 12.653l2.496-4.323c0.044-0.074 0.070-0.164 0.070-0.26 0-0.287-0.232-0.519-0.519-0.519-0.191 0-0.358 0.103-0.448 0.257l-0.001 0.002-2.527 4.377c-1.887-0.867-4.094-1.373-6.419-1.373s-4.532 0.506-6.517 1.413l0.098-0.040-2.527-4.378c-0.091-0.156-0.259-0.26-0.45-0.26-0.287 0-0.519 0.232-0.519 0.519 0 0.096 0.026 0.185 0.071 0.262l-0.001-0.002 2.496 4.323c-4.286 2.367-7.236 6.697-7.643 11.744l-0.003 0.052h29.991c-0.41-5.099-3.36-9.429-7.57-11.758l-0.076-0.038zM9.098 20.176c-0 0-0 0-0 0-0.69 0-1.249-0.559-1.249-1.249s0.559-1.249 1.249-1.249c0.69 0 1.249 0.559 1.249 1.249v0c-0.001 0.689-0.559 1.248-1.249 1.249h-0zM22.902 20.176c-0 0-0 0-0 0-0.69 0-1.249-0.559-1.249-1.249s0.559-1.249 1.249-1.249c0.69 0 1.249 0.559 1.249 1.249v0c-0.001 0.689-0.559 1.248-1.249 1.249h-0z" fill="currentColor"/>
                    </svg>
                    <TranslationSafe fallback="Android">
                      {t('downloadApps.instructions.android.title')}
                    </TranslationSafe>
                  </h3>
                  <ol className="list-decimal list-inside space-y-2 text-humdb-gray-700 text-sm sm:text-base">
                    <li>
                      <TranslationSafe fallback="Download the APK file using the button above">
                        {t('downloadApps.instructions.android.step1')}
                      </TranslationSafe>
                    </li>
                    <li>
                      <TranslationSafe fallback="Enable 'Install from Unknown Sources' in your device settings">
                        {t('downloadApps.instructions.android.step2')}
                      </TranslationSafe>
                    </li>
                    <li>
                      <TranslationSafe fallback="Open the downloaded APK file and follow the installation prompts">
                        {t('downloadApps.instructions.android.step3')}
                      </TranslationSafe>
                    </li>
                  </ol>
                </div>

                {/* iOS Instructions */}
                <div>
                  <h3 className="text-lg font-semibold text-humdb-navy mb-3 flex items-center">
                    <img
                      src="/icons/apple.svg"
                      alt="Apple"
                      className="w-5 h-5 mr-2"
                      style={{
                        filter: 'brightness(0) saturate(100%) invert(27%) sepia(100%) saturate(5000%) hue-rotate(210deg) brightness(0.95) contrast(1.1)',
                        display: 'block'
                      }}
                    />
                    <TranslationSafe fallback="iOS">
                      {t('downloadApps.instructions.ios.title')}
                    </TranslationSafe>
                  </h3>
                  <ol className="list-decimal list-inside space-y-2 text-humdb-gray-700 text-sm sm:text-base">
                    <li>
                      <TranslationSafe fallback="Download the IPA file using the button above">
                        {t('downloadApps.instructions.ios.step1')}
                      </TranslationSafe>
                    </li>
                    <li>
                      <TranslationSafe fallback="Connect your iOS device to your computer">
                        {t('downloadApps.instructions.ios.step2')}
                      </TranslationSafe>
                    </li>
                    <li>
                      <TranslationSafe fallback="Use iTunes or Finder to install the IPA file on your device">
                        {t('downloadApps.instructions.ios.step3')}
                      </TranslationSafe>
                    </li>
                    <li>
                      <TranslationSafe fallback="Trust the developer certificate in Settings > General > Device Management">
                        {t('downloadApps.instructions.ios.step4')}
                      </TranslationSafe>
                    </li>
                  </ol>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

// Ensure SSR to avoid build-time prerender errors.
// When ENABLE_APPETIZE_BROWSER_DEMOS is true: ANDROID_DEMO_EMBED_URL / IOS_DEMO_EMBED_URL (server)
// or NEXT_PUBLIC_* (build); defaults use committed Appetize embed URLs when env is unset.
export async function getServerSideProps() {
  if (!ENABLE_APPETIZE_BROWSER_DEMOS) {
    return { props: {} };
  }
  const androidDemoEmbedUrl =
    process.env.ANDROID_DEMO_EMBED_URL ||
    process.env.NEXT_PUBLIC_ANDROID_DEMO_EMBED_URL ||
    DEFAULT_APPETIZE_ANDROID_EMBED;
  const iosDemoEmbedUrl =
    process.env.IOS_DEMO_EMBED_URL ||
    process.env.NEXT_PUBLIC_IOS_DEMO_EMBED_URL ||
    DEFAULT_APPETIZE_IOS_EMBED;
  return { props: { androidDemoEmbedUrl, iosDemoEmbedUrl } };
}
