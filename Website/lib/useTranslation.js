import { useRouter } from 'next/router';
import { useEffect, useState } from 'react';

function loadServerTranslations(locale) {
  try {
    const fs = require('fs');
    const path = require('path');
    const resolved = locale || 'en';
    const filePath = path.join(process.cwd(), 'public', 'locales', resolved, 'common.json');
    if (fs.existsSync(filePath)) {
      return JSON.parse(fs.readFileSync(filePath, 'utf8'));
    }
  } catch (_) {}
  return {};
}

function loadEmbeddedTranslations() {
  if (typeof window === 'undefined') return null;
  try {
    const el = document.getElementById('__i18n');
    const raw = el?.textContent || '';
    if (!raw.trim()) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch (_) {
    return null;
  }
}

export function useTranslation() {
  const router = useRouter();
  const { locale } = router;

  // Ensure consistent initial state between server and client:
  // - Server renders real translations synchronously
  // - Client bootstraps from `__i18n` embedded JSON (rendered by Layout)
  const [translations, setTranslations] = useState(() => {
    if (typeof window === 'undefined') {
      // Server-side: load translations synchronously
      return loadServerTranslations(locale);
    }
    // Client-side: use embedded translations (prevents hydration mismatch)
    return loadEmbeddedTranslations() || {};
  });

  const [fallbackTranslations, setFallbackTranslations] = useState(() => {
    if (typeof window === 'undefined') {
      // Server-side: load fallback translations synchronously
      return loadServerTranslations('en');
    }
    // Client-side: will be fetched; keep empty unless we decide to hydrate this too
    return {};
  });

  // Track if translations have been loaded to prevent hydration issues
  const [isLoaded, setIsLoaded] = useState(() => {
    // Server-side: always start as loaded
    if (typeof window === 'undefined') {
      return true;
    }
    // Client-side: loaded if we have embedded translations
    return !!loadEmbeddedTranslations();
  });

  // Track if we're in a hydration-safe state
  const [isHydrationSafe, setIsHydrationSafe] = useState(() => {
    // Server-side: always safe
    if (typeof window === 'undefined') {
      return true;
    }
    // Client-side: safe if we have embedded translations
    return !!loadEmbeddedTranslations();
  });

  useEffect(() => {
    const loadTranslations = async () => {
      try {
        const [currentRes, fallbackRes] = await Promise.all([
          fetch(`/locales/${locale}/common.json`),
          fetch('/locales/en/common.json'),
        ]);

        if (fallbackRes.ok) {
          const fallbackData = await fallbackRes.json();
          setFallbackTranslations(fallbackData);
        }

        if (currentRes.ok) {
          const data = await currentRes.json();
          setTranslations(data);
        } else if (fallbackRes.ok) {
          // If current locale missing entirely, use English
          const fallbackData = await fallbackRes.json();
          setTranslations(fallbackData);
        }

        setIsLoaded(true);

        // Mark as hydration-safe after a small delay to ensure DOM is ready
        setTimeout(() => {
          setIsHydrationSafe(true);
        }, 0);
      } catch (error) {
        console.error('Error loading translations:', error);
        // Best-effort English fallback
        try {
          const fallbackResponse = await fetch('/locales/en/common.json');
          if (fallbackResponse.ok) {
            const fallbackData = await fallbackResponse.json();
            setFallbackTranslations(fallbackData);
            setTranslations(fallbackData);
          }
        } catch (fallbackError) {
          console.error('Error loading fallback translations:', fallbackError);
        }
        setIsLoaded(true);
        setTimeout(() => {
          setIsHydrationSafe(true);
        }, 0);
      }
    };

    if (locale && typeof window !== 'undefined') {
      loadTranslations();
    }
  }, [locale]);

  const t = (key, params = {}) => {
    // If translations aren't loaded yet on client, return a loading state
    if (!isLoaded && typeof window !== 'undefined') {
      // Return a simple loading text to prevent hydration mismatch
      if (key.includes('loading')) {
        return 'Loading...';
      }
      // For other keys, return a placeholder that won't cause hydration issues
      return '';
    }

    const keys = key.split('.');

    const resolveValue = (source) => {
      let current = source;
      for (const k of keys) {
        if (current && typeof current === 'object' && k in current) {
          current = current[k];
        } else {
          return undefined;
        }
      }
      return typeof current === 'string' ? current : undefined;
    };

    // Prefer current locale
    let value = resolveValue(translations);
    // Fallback to English when missing
    if (value === undefined) {
      value = resolveValue(fallbackTranslations);
    }
    // Fallback to provided defaultValue param
    if (value === undefined && typeof params.defaultValue === 'string') {
      value = params.defaultValue;
    }

    if (typeof value === 'string') {
      // Interpolate params like {{param}}
      let result = value;
      Object.keys(params).forEach((paramKey) => {
        if (paramKey === 'defaultValue') return;
        const regex = new RegExp(`{{${paramKey}}}`, 'g');
        result = result.replace(regex, String(params[paramKey]));
      });
      return result;
    }

    // Final fallback: return the key path
    return key;
  };

  // Safe translation function that prevents hydration mismatches
  const tSafe = (key, params = {}) => {
    // If we're not in a hydration-safe state, return empty string to prevent mismatch
    if (!isHydrationSafe && typeof window !== 'undefined') {
      return '';
    }

    return t(key, params);
  };

  // For components that need to show content immediately but can handle hydration
  const tHydrationSafe = (key, params = {}) => {
    // Server-side: always return the translation
    if (typeof window === 'undefined') {
      return t(key, params);
    }

    // Client-side: if translations aren't loaded, return empty string
    if (!isLoaded) {
      return '';
    }

    return t(key, params);
  };

  return {
    t,
    tSafe,
    tHydrationSafe,
    locale,
    isLoaded,
    isHydrationSafe
  };
}
