// pages/api/periods.js
// Same-origin proxy for periods: calls Backoffice with API key so the browser avoids CORS.

import { getDataFromStore } from '../../lib/dataStore';
import { FDRS_TEMPLATE_ID } from '../../lib/constants';

const BACKOFFICE_URL = process.env.NEXT_PUBLIC_API_URL || process.env.INTERNAL_API_URL || 'http://localhost:5000';
const API_KEY = (process.env.NEXT_PUBLIC_API_KEY || 'databank2026').replace(/^Bearer\s+/i, '').trim();

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const templateId = req.query.template_id ? parseInt(req.query.template_id) : FDRS_TEMPLATE_ID;

  // 1) Try Backoffice first (server-side call, no CORS)
  try {
    const url = `${BACKOFFICE_URL}/api/v1/periods${templateId != null && !isNaN(templateId) ? `?template_id=${templateId}` : ''}`;
    const response = await fetch(url, {
      headers: API_KEY ? { Authorization: `Bearer ${API_KEY}` } : {}
    });
    if (response.ok) {
      const periods = await response.json();
      if (Array.isArray(periods)) {
        return res.status(200).json(periods);
      }
    }
  } catch (proxyError) {
    console.warn('[api/periods] Backoffice proxy failed, using fallback:', proxyError?.message || proxyError);
  }

  // 2) Fallback: local data store
  try {
    const data = await getDataFromStore({ template_id: templateId });
    const periods = [...new Set(data.map(item => item.period_name).filter(Boolean))].sort().reverse();
    return res.status(200).json(periods);
  } catch (error) {
    console.error('Error fetching periods:', error);
    return res.status(500).json({ error: error.message });
  }
}
