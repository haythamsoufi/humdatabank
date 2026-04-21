// pages/api/embed-content.js
// Caching proxy for embed content from the backoffice API.
// Keeps the last successful response so the website still works when
// the backoffice is unreachable. Also falls back to the local data store
// synced by dataStore.syncDataFromBackend.

const BACKOFFICE_URL = (
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.INTERNAL_API_URL ||
  'http://localhost:5000'
).replace(/\/$/, '');
const API_KEY = (process.env.NEXT_PUBLIC_API_KEY || 'databank2026')
  .replace(/^Bearer\s+/i, '')
  .trim();

let cachedData = null;
let cacheTimestamp = 0;
const CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const category = req.query.category || '';
  const now = Date.now();

  // Serve from in-memory cache if fresh
  if (cachedData && now - cacheTimestamp < CACHE_TTL_MS) {
    const filtered = category
      ? cachedData.filter((e) => e.category === category)
      : cachedData;
    return res.status(200).json({ embeds: filtered, total: filtered.length, cached: true });
  }

  // Try live backoffice fetch
  try {
    const params = new URLSearchParams();
    if (category) params.append('category', category);
    const qs = params.toString();
    const url = `${BACKOFFICE_URL}/api/v1/embed-content${qs ? `?${qs}` : ''}`;

    const response = await fetch(url, {
      method: 'GET',
      headers: {
        Accept: 'application/json',
        ...(API_KEY ? { Authorization: `Bearer ${API_KEY}` } : {}),
      },
      signal: AbortSignal.timeout(15000),
    });

    if (!response.ok) {
      throw new Error(`Backoffice returned ${response.status}`);
    }

    const data = await response.json();
    const embeds = data?.embeds || [];

    // Update in-memory cache (full set when no filter applied)
    if (!category) {
      cachedData = embeds;
      cacheTimestamp = now;
    }

    return res.status(200).json({ embeds, total: embeds.length, cached: false });
  } catch (error) {
    console.warn('[api/embed-content] Backoffice unreachable, trying fallbacks:', error?.message);

    // Fallback 1: stale in-memory cache
    if (cachedData) {
      const filtered = category
        ? cachedData.filter((e) => e.category === category)
        : cachedData;
      return res.status(200).json({ embeds: filtered, total: filtered.length, cached: true, stale: true });
    }

    // Fallback 2: local data store (disk-persisted from last sync)
    try {
      const { getEmbedContentFromStore } = await import('../../lib/dataStore');
      const storeEmbeds = await getEmbedContentFromStore(category);
      if (storeEmbeds && storeEmbeds.length > 0) {
        return res.status(200).json({ embeds: storeEmbeds, total: storeEmbeds.length, cached: true, stale: true });
      }
    } catch (_storeErr) {
      // Data store not available
    }

    return res.status(200).json({ embeds: [], total: 0, cached: false, error: 'No data available' });
  }
}
