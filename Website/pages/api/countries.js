// pages/api/countries.js
// API route for client-side access to countries from server-side data store

import { getCountriesFromStore } from '../../lib/dataStore';

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const locale = req.query.locale || null;
    const countries = await getCountriesFromStore();

    // Map frontend locale codes to backend language keys
    const backendLocaleMap = {
      en: 'english',
      fr: 'french',
      es: 'spanish',
      ar: 'arabic',
      zh: 'chinese',
      ru: 'russian',
      hi: 'hindi',
    };

    const backendLocaleKey = locale ? backendLocaleMap[String(locale).toLowerCase()] : null;

    // Transform to match expected format with localization
    const transformed = countries.map(country => {
      // Resolve localized country name
      let resolvedCountryName = country.name;
      if (country.multilingual_names && backendLocaleKey && country.multilingual_names[backendLocaleKey]) {
        resolvedCountryName = country.multilingual_names[backendLocaleKey] || resolvedCountryName;
      }

      // Resolve localized National Society name
      let resolvedNsName = country.national_society_name || country.name;
      if (country.multilingual_national_society_names && backendLocaleKey && country.multilingual_national_society_names[backendLocaleKey]) {
        resolvedNsName = country.multilingual_national_society_names[backendLocaleKey] || resolvedNsName;
      }

      // Resolve localized region name
      let resolvedRegion = country.region || 'Other';
      if (country.region_multilingual_names && backendLocaleKey && country.region_multilingual_names[backendLocaleKey]) {
        resolvedRegion = country.region_multilingual_names[backendLocaleKey] || resolvedRegion;
      }

      return {
        id: country.id,
        code: country.iso2,
        name: resolvedCountryName,
        region: resolvedRegion,
        region_localized: resolvedRegion,
        iso3: country.iso3,
        iso2: country.iso2,
        national_society_name: resolvedNsName,
      };
    });

    res.status(200).json(transformed);
  } catch (error) {
    console.error('Error fetching countries:', error);
    res.status(500).json({ error: error.message });
  }
}
