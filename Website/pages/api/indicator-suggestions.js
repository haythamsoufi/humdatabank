// Same-origin proxy for POST /api/v1/indicator-suggestions (avoids CORS in the browser).

const BACKOFFICE_URL = (process.env.NEXT_PUBLIC_API_URL || process.env.INTERNAL_API_URL || 'http://localhost:5000').replace(/\/$/, '');
const API_KEY = (process.env.NEXT_PUBLIC_API_KEY || 'databank2026').replace(/^Bearer\s+/i, '').trim();

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const url = `${BACKOFFICE_URL}/api/v1/indicator-suggestions`;
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        ...(API_KEY ? { Authorization: `Bearer ${API_KEY}` } : {}),
      },
      body: JSON.stringify(req.body || {}),
      signal: AbortSignal.timeout(30000),
    });

    const data = await response.json().catch(() => ({}));
    res.status(response.status).json(data);
  } catch (error) {
    console.warn('[api/indicator-suggestions] Proxy failed:', error?.message);
    res.status(502).json({ error: error?.message || 'Backoffice proxy failed' });
  }
}
