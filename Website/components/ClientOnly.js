import { useEffect, useState } from 'react';
import { useTranslation } from '../lib/useTranslation';

// Enhanced ClientOnly component for safe translation rendering
// WARNING: This component can cause hydration errors if fallback is null
// and children render different DOM structure. Use HydrationSafe instead.
export default function ClientOnly({ children, fallback = null, translationKey = null }) {
  const [hasMounted, setHasMounted] = useState(false);

  useEffect(() => {
    setHasMounted(true);
  }, []);

  if (!hasMounted) {
    return fallback;
  }

  return children;
}

// Specialized component for translation-safe rendering
export function TranslationSafe({ children, fallback = null }) {
  const [hasMounted, setHasMounted] = useState(false);

  useEffect(() => {
    // Small delay to ensure translations are loaded
    const timer = setTimeout(() => {
      setHasMounted(true);
    }, 50);

    return () => clearTimeout(timer);
  }, []);

  if (!hasMounted) {
    return fallback;
  }

  return children;
}

// Component for rendering translations safely
export function SafeTranslation({ translationKey, fallback = '', children }) {
  const [hasMounted, setHasMounted] = useState(false);

  useEffect(() => {
    setHasMounted(true);
  }, []);

  if (!hasMounted) {
    return fallback;
  }

  return children;
}

/**
 * HydrationSafe Component - The Ultimate Hydration Error Prevention
 *
 * This component ensures identical server/client rendering by:
 * 1. Rendering identical fallback content on both server and initial client render
 * 2. Only switching to dynamic content after hydration is complete
 * 3. Maintaining the same DOM structure throughout the process
 *
 * @param {ReactNode} children - The content to render after hydration
 * @param {ReactNode} fallback - The content to render during SSR and initial hydration (must be identical on server/client)
 * @param {string} className - Optional CSS classes to apply to the wrapper
 * @param {object} style - Optional inline styles
 * @param {number} delay - Optional delay in milliseconds before switching to children (default: 100)
 */
export function HydrationSafe({
  children,
  fallback = null,
  className = '',
  style = {},
  delay = 100,
  suppressHydrationWarning = true
}) {
  const [isHydrated, setIsHydrated] = useState(false);

  useEffect(() => {
    // Use a small delay to ensure all hydration is complete
    const timer = setTimeout(() => {
      setIsHydrated(true);
    }, delay);

    return () => clearTimeout(timer);
  }, [delay]);

  // Always render the same wrapper structure to prevent DOM mismatch
  return (
    <div
      className={className}
      style={style}
      suppressHydrationWarning={suppressHydrationWarning}
    >
      {isHydrated ? children : fallback}
    </div>
  );
}

/**
 * MapSafe Component - Specialized for interactive maps and complex widgets
 *
 * This component is designed specifically for components that need to:
 * 1. Avoid SSR completely (like Leaflet maps)
 * 2. Show consistent loading states
 * 3. Prevent any hydration mismatches
 */
export function MapSafe({
  children,
  loadingComponent = null,
  className = '',
  style = {},
  height = 'auto',
  minHeight = '400px'
}) {
  const { t } = useTranslation();
  const [isClient, setIsClient] = useState(false);

  useEffect(() => {
    // Ensure this only runs on the client
    setIsClient(true);
  }, []);

  // Default loading component
  const defaultLoading = (
    <div
      className={`flex items-center justify-center bg-gradient-to-br from-gray-50 to-gray-100 rounded-xl ${className}`}
      style={{ height, minHeight, ...style }}
    >
      <div className="text-center">
        <div className="animate-spin rounded-full h-16 w-16 border-4 border-humdb-red border-t-transparent mx-auto mb-6"></div>
        <p className="text-humdb-gray-600 text-lg font-medium">{t('common.loading')}</p>
      </div>
    </div>
  );

  // Always render the same structure, but with different content
  if (!isClient) {
    return loadingComponent || defaultLoading;
  }

  return (
    <div className={className} style={style}>
      {children}
    </div>
  );
}
