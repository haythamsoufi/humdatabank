// pages/api/backoffice/[[...path]].js
// Generic same-origin proxy to Backoffice /api/v1/* (avoids CORS for form-items, indicator-bank, etc.).

const BACKOFFICE_URL = (process.env.NEXT_PUBLIC_API_URL || process.env.INTERNAL_API_URL || 'http://localhost:5000').replace(/\/$/, '');
const API_KEY = (process.env.NEXT_PUBLIC_API_KEY || 'databank2026').replace(/^Bearer\s+/i, '').trim();

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const pathParts = req.query.path;
    const pathSegment = Array.isArray(pathParts) ? pathParts.join('/') : (pathParts || '');
    const { path: _p, ...rest } = req.query;
    const query = new URLSearchParams(rest).toString();
    const url = `${BACKOFFICE_URL}/api/v1/${pathSegment}${query ? `?${query}` : ''}`;
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        Accept: 'application/json',
        ...(API_KEY ? { Authorization: `Bearer ${API_KEY}` } : {}),
      },
      signal: AbortSignal.timeout(60000),
    });
    const data = await response.json().catch(() => ({}));
    res.status(response.status).json(data);
  } catch (error) {
    console.warn('[api/backoffice] Proxy failed:', error?.message);
    res.status(502).json({ error: error?.message || 'Backoffice proxy failed' });
  }
}
