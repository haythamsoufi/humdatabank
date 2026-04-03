// Utility functions for region handling

// Normalize region names coming from different data sources into a canonical set.
// This ensures consistent routing (/regions/[slug]) while allowing UI labels to be localized.
export function normalizeRegionName(regionName) {
  if (!regionName) return '';

  const trimmed = String(regionName).trim();

  const canonicalMap = {
    // Africa
    'Africa': 'Africa',

    // Americas
    'Americas': 'Americas',

    // Asia Pacific
    'Asia Pacific': 'Asia Pacific',
    'Asia-Pacific': 'Asia Pacific',

    // Europe & Central Asia (various abbreviations)
    'Europe and Central Asia': 'Europe and Central Asia',
    'Europe & Central Asia': 'Europe and Central Asia',
    'Europe & CA': 'Europe and Central Asia',
    'Europe & C. Asia': 'Europe and Central Asia',

    // MENA
    'MENA': 'MENA',
    'Middle East and North Africa': 'MENA',
    'Middle East & North Africa': 'MENA',
  };

  return canonicalMap[trimmed] || trimmed;
}

// Map canonical/known region names to an i18n key.
// Keys live under `globalOverview.regions.*` in `public/locales/*/common.json`.
export function regionNameToTranslationKey(regionName) {
  const canonical = normalizeRegionName(regionName);

  const keyMap = {
    'Africa': 'globalOverview.regions.africa',
    'Americas': 'globalOverview.regions.americas',
    'Asia Pacific': 'globalOverview.regions.asiaPacific',
    'Europe and Central Asia': 'globalOverview.regions.europeCentralAsia',
    'MENA': 'globalOverview.regions.mena',
  };

  return keyMap[canonical] || null;
}

// Convert region name to URL slug
export function regionToSlug(regionName) {
  if (!regionName) return '';

  const raw = String(regionName).trim();

  // Preserve legacy explicit slugs when callers pass the full label.
  // (Some parts of the app/router may still rely on this variant.)
  if (raw === 'Middle East and North Africa' || raw === 'Middle East & North Africa') {
    return 'middle-east-and-north-africa';
  }

  const normalized = normalizeRegionName(raw);

  const slugMap = {
    'Africa': 'africa',
    'Americas': 'americas',
    'Asia Pacific': 'asia-pacific',
    'Europe and Central Asia': 'europe-and-central-asia',
    'MENA': 'mena',
    // Legacy / alternative labels
    'Europe & Central Asia': 'europe-and-central-asia',
    'Europe & CA': 'europe-and-central-asia',
    'Middle East and North Africa': 'middle-east-and-north-africa',
    'Middle East & North Africa': 'middle-east-and-north-africa'
  };

  return slugMap[normalized] || normalized.toLowerCase().replace(/\s+/g, '-');
}

// Convert URL slug back to region name
export function slugToRegion(slug) {
  if (!slug) return '';

  const regionMap = {
    'africa': 'Africa',
    'americas': 'Americas',
    'asia-pacific': 'Asia Pacific',
    'europe-and-central-asia': 'Europe and Central Asia',
    'mena': 'MENA',
    'middle-east-and-north-africa': 'Middle East and North Africa'
  };

  return regionMap[slug] || slug;
}

// Get all available regions
export function getAvailableRegions() {
  return [
    'Africa',
    'Americas',
    'Asia Pacific',
    'Europe and Central Asia',
    'MENA',
    'Middle East and North Africa'
  ];
}
