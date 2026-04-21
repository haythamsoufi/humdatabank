// pages/api/indicators.js
// API route for client-side access to indicators (data store first, then Backoffice)

import { getIndicatorsFromStore } from '../../lib/dataStore';

const BACKOFFICE_URL = (process.env.NEXT_PUBLIC_API_URL || process.env.INTERNAL_API_URL || 'http://localhost:5000').replace(/\/$/, '');
const API_KEY = (process.env.NEXT_PUBLIC_API_KEY || process.env.API_KEY || 'databank2026').replace(/^Bearer\s+/i, '').trim();

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const searchQuery = req.query.search || '';
    const type = req.query.type || '';
    const sector = req.query.sector || '';
    const subSector = req.query.sub_sector || '';
    const archived = req.query.archived !== undefined ? req.query.archived === 'true' : null;

    let indicators = [];
    try {
      indicators = await getIndicatorsFromStore({
        searchQuery,
        type,
        sector,
        subSector,
        archived
      });
    } catch (storeError) {
      // Store not available or disabled
    }

    // If store is empty, fetch from Backoffice
    if (!indicators || indicators.length === 0) {
      const params = new URLSearchParams();
      if (searchQuery) params.set('search', searchQuery);
      if (type) params.set('type', type);
      if (sector) params.set('sector', sector);
      if (subSector) params.set('sub_sector', subSector);
      if (archived !== null) params.set('archived', String(archived));
      const url = `${BACKOFFICE_URL}/api/v1/indicator-bank${params.toString() ? `?${params.toString()}` : ''}`;
      const response = await fetch(url, {
        headers: API_KEY ? { Authorization: `Bearer ${API_KEY}` } : {},
        signal: AbortSignal.timeout(60000),
      });
      if (response.ok) {
        const data = await response.json();
        indicators = data.indicators || [];
      }
    }

    res.status(200).json({ indicators });
  } catch (error) {
    console.error('Error fetching indicators:', error);
    res.status(500).json({ error: error.message });
  }
}
