// pages/api/sectors-subsectors.js
// API route for client-side access to sectors/subsectors from local store

import { getLocalizedSectorName, getLocalizedSubsectorName } from '../../lib/apiService';
import { getSectorsSubsectorsFromStore } from '../../lib/dataStore';

// Helper function for sector description (simplified)
function getLocalizedSectorDescription(sector, locale) {
  return sector.description || '';
}

// Helper function for subsector description (simplified)
function getLocalizedSubsectorDescription(subsector, locale) {
  return subsector.description || '';
}

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const locale = req.query.locale || 'en';

    const payload = await getSectorsSubsectorsFromStore();
    const sectors = (payload?.sectors || []).map(sector => ({
      ...sector,
      localized_name: getLocalizedSectorName(sector, locale),
      localized_description: getLocalizedSectorDescription(sector, locale),
      subsectors: (sector.subsectors || []).map(subsector => ({
        ...subsector,
        localized_name: getLocalizedSubsectorName(subsector, locale),
        localized_description: getLocalizedSubsectorDescription(subsector, locale)
      }))
    }));

    res.status(200).json({ sectors });
  } catch (error) {
    console.error('Error fetching sectors/subsectors:', error);
    res.status(500).json({ error: error.message });
  }
}
