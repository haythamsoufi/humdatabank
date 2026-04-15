import { useRouter } from 'next/router';
import Link from 'next/link';

const LanguageSwitcher = () => {
  const router = useRouter();
  const { locale, pathname, asPath, query } = router;

  const languages = [
    { code: 'en', name: 'English', display: 'EN', flagCode: 'gb' },
    { code: 'es', name: 'Español', display: 'ES', flagCode: 'es' },
    { code: 'fr', name: 'Français', display: 'FR', flagCode: 'fr' },
    { code: 'ar', name: 'العربية', display: 'AR', flagCode: 'sa' },
    { code: 'hi', name: 'हिन्दी', display: 'HI', flagCode: 'in' },
    { code: 'ru', name: 'Русский', display: 'RU', flagCode: 'ru' },
    { code: 'zh', name: '中文', display: 'ZH', flagCode: 'cn' },
  ];

  const currentLanguage = languages.find(lang => lang.code === locale) || languages[0];

  // Create a stable href that works both on server and client
  // Use pathname and query for dynamic routes to avoid hydration mismatches
  // This prevents the warning: "Prop `href` did not match. Server: "/countries/[iso3]/" Client: "/countries/SYR/""
  const getLocalizedHref = () => {
    // Handle 404 pages - use pathname consistently to avoid hydration mismatch
    if (pathname === '/404' || pathname === '/_error') {
      return pathname;
    }

    // For dynamic routes, use pathname and query object
    // This ensures the href is the same on both server and client
    if (pathname.includes('[') && pathname.includes(']')) {
      return {
        pathname: pathname,
        query: query
      };
    }
    // For static routes, use pathname for consistency (asPath can differ on 404s)
    // Fallback to '/' if pathname is not available
    return pathname || '/';
  };

  // Function to render language flag
  const renderLanguageFlag = (language) => {
    if (!language) {
      return (
        <span
          className="flag-icon flag-icon-gb"
          role="img"
          aria-label="English language"
        ></span>
      );
    }

    return (
      <span
        className={`flag-icon flag-icon-${language.flagCode}`}
        role="img"
        aria-label={`${language.name} language`}
        title={language.name}
      ></span>
    );
  };

  return (
    <div className="relative group">
      <button className="flex items-center space-x-1 px-3 py-2 text-sm font-medium text-humdb-white hover:text-humdb-blue-200 transition-colors duration-200">
        {renderLanguageFlag(currentLanguage)}
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      <div className="absolute right-0 mt-2 w-48 bg-white rounded-md shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 z-50">
        <div className="py-1">
          {languages.map((language) => (
            <Link
              key={language.code}
              href={getLocalizedHref()}
              locale={language.code}
              className={`flex items-center space-x-3 px-4 py-2 text-sm hover:bg-humdb-gray-100 transition-colors duration-200 ${
                locale === language.code ? 'bg-humdb-blue-50 text-humdb-blue-600' : 'text-humdb-gray-700'
              }`}
            >
              <span className={`flag-icon flag-icon-${language.flagCode}`} title={language.name}></span>
              <span>{language.name}</span>
              {locale === language.code && (
                <svg className="w-4 h-4 ml-auto" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                </svg>
              )}
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
};

export default LanguageSwitcher;
