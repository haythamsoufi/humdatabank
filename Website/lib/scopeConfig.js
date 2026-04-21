// lib/scopeConfig.js
// Centralized configuration for deployment/demo scope selection.

export const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === 'true';

// Activity views (Domestic / International)
// - Domestic: current indicator-based maps (world map, NS country map)
// - International: cross-border support maps (future: flow lines, support relationships)
export const ENABLE_DOMESTIC = process.env.NEXT_PUBLIC_ENABLE_DOMESTIC !== 'false';
export const ENABLE_INTERNATIONAL = process.env.NEXT_PUBLIC_ENABLE_INTERNATIONAL === 'true';
export const DEFAULT_ACTIVITY_VIEW = String(process.env.NEXT_PUBLIC_DEFAULT_ACTIVITY_VIEW || 'domestic').trim().toLowerCase();

// Deployment scope is used when DEMO_MODE is false.
// Supported values:
// - "global" (default)
// - ISO2 country code, e.g. "SY"
export const ENV_DEPLOYMENT_SCOPE = String(process.env.NEXT_PUBLIC_DEPLOYMENT_SCOPE || 'global')
  .trim();

export function normalizeScopeValue(value) {
  const v = String(value || '').trim();
  if (!v) return { type: 'global', countryIso2: null };

  if (v.toLowerCase() === 'global') return { type: 'global', countryIso2: null };

  // Treat any 2-letter code as ISO2.
  if (/^[a-zA-Z]{2}$/.test(v)) return { type: 'country', countryIso2: v.toUpperCase() };

  return { type: 'global', countryIso2: null };
}

export function getAllowedScopeTypes() {
  // In demo mode, allow switching between global and country.
  if (DEMO_MODE) return ['global', 'country'];
  return [normalizeScopeValue(ENV_DEPLOYMENT_SCOPE).type];
}

export function getEffectiveScope(preferred) {
  // preferred can be:
  // - "global"
  // - ISO2 string like "SY"
  // - { type, countryIso2 }
  const preferredValue =
    preferred && typeof preferred === 'object'
      ? (preferred.type === 'country' ? preferred.countryIso2 : 'global')
      : preferred;

  if (DEMO_MODE) return normalizeScopeValue(preferredValue || ENV_DEPLOYMENT_SCOPE);
  return normalizeScopeValue(ENV_DEPLOYMENT_SCOPE);
}

export function getScopeLabel(scope, countryName = null, nationalSocietyName = null) {
  if (!scope || scope.type === 'global') return 'Global';
  return nationalSocietyName || countryName || scope.countryIso2 || 'Selected country';
}
