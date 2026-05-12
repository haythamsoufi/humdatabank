// pages/api/data.js
// Same-origin proxy for form data: uses local store first, then Backoffice /api/v1/data when store is empty.

import { getDataFromStore, getFormItemsFromStore, getCountriesFromStore } from '../../lib/dataStore';
import { FDRS_TEMPLATE_ID } from '../../lib/constants';

const BACKOFFICE_URL = process.env.NEXT_PUBLIC_API_URL || process.env.INTERNAL_API_URL || 'http://localhost:5000';
const API_KEY = (process.env.NEXT_PUBLIC_API_KEY || 'databank2026').replace(/^Bearer\s+/i, '').trim();

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const filters = {
      country_iso3: req.query.country_iso3,
      country_iso2: req.query.country_iso2,
      period_name: req.query.period_name,
      indicator_bank_id: req.query.indicator_bank_id ? parseInt(req.query.indicator_bank_id) : undefined,
      template_id: req.query.template_id ? parseInt(req.query.template_id) : undefined,
      submission_type: req.query.submission_type,
    };
    Object.keys(filters).forEach(key => filters[key] === undefined && delete filters[key]);

    const returnFullResponse = req.query.returnFullResponse === 'true' || req.query.related === 'all';
    const perPage = Math.min(parseInt(req.query.per_page || req.query.perPage, 10) || 100000, 100000);
    const storeOnly = req.query.storeOnly === 'true' || req.query.storeOnly === '1';

    let data = [];
    try {
      data = await getDataFromStore(filters);
    } catch (storeError) {
      console.warn('[api/data] Store error, will try Backoffice:', storeError?.message);
    }

    // If store returned empty and we have filters, try Backoffice (same as getIndicatorData needs)
    if (data.length === 0 && BACKOFFICE_URL && API_KEY && !storeOnly) {
      try {
        const params = new URLSearchParams();
        params.set('template_id', String(filters.template_id || FDRS_TEMPLATE_ID));
        params.set('disagg', 'true');
        params.set('per_page', String(perPage));
        if (filters.period_name) params.set('period_name', filters.period_name);
        if (filters.indicator_bank_id) params.set('indicator_bank_id', String(filters.indicator_bank_id));
        if (filters.country_iso2) params.set('country_iso2', filters.country_iso2);
        if (filters.country_iso3) params.set('country_iso3', filters.country_iso3);
        const url = `${BACKOFFICE_URL}/api/v1/data?${params.toString()}`;
        const response = await fetch(url, {
          headers: { Accept: 'application/json', Authorization: `Bearer ${API_KEY}` },
          signal: AbortSignal.timeout(60000),
        });
        if (response.ok) {
          const json = await response.json();
          data = Array.isArray(json) ? json : (json.data || []);
          console.log(`[api/data] Backoffice returned ${data.length} items`);
        }
      } catch (proxyError) {
        console.warn('[api/data] Backoffice proxy failed:', proxyError?.message);
      }
    }

    if (returnFullResponse) {
      let formItems = [];
      let countries = [];
      try {
        formItems = await getFormItemsFromStore(filters);
        countries = await getCountriesFromStore();
      } catch (_) {}
      return res.status(200).json({
        data,
        form_items: formItems,
        countries,
        total_items: data.length,
        total_pages: 1,
        current_page: 1,
        per_page: data.length,
      });
    }
    res.status(200).json({ data, count: data.length });
  } catch (error) {
    console.error('Error in /api/data:', error);
    res.status(500).json({ error: error.message });
  }
}
