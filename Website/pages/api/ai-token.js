// pages/api/ai-token.js
// Same-origin proxy for AI token so the browser avoids CORS when calling Backoffice.

const BACKOFFICE_URL = process.env.NEXT_PUBLIC_API_URL || process.env.INTERNAL_API_URL || 'http://localhost:5000';

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const url = `${BACKOFFICE_URL}/api/ai/v2/token`;
    const headers = {
      'Content-Type': 'application/json',
      'Accept': 'application/json'
    };
    // Forward cookie so Backoffice can recognize session if user has one
    if (req.headers.cookie) {
      headers['Cookie'] = req.headers.cookie;
    }
    const response = await fetch(url, {
      method: 'GET',
      headers,
      signal: AbortSignal.timeout(10000)
    });
    const data = await response.json().catch(() => ({}));
    res.status(response.status).json(data);
  } catch (error) {
    console.warn('[api/ai-token] Proxy failed:', error?.message || error);
    res.status(502).json({ error: error?.message || 'Token proxy failed' });
  }
}
