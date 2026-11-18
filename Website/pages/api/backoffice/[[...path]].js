// pages/api/backoffice/[[...path]].js
// Same-origin proxy to selected Backoffice /api/v1/* read endpoints (avoids CORS for form-items,
// indicator-bank, etc.).
//
// This route is reachable by anyone who can reach the Website, and it adds the server's API key.
// Only the read-only paths below are forwarded; everything else is refused, so the key's other
// permissions (submissions, users, suggestions, ...) are never reachable through the proxy.

const BACKOFFICE_URL = (process.env.NEXT_PUBLIC_API_URL || process.env.INTERNAL_API_URL || 'http://localhost:5000').replace(/\/$/, '');
// Prefer a server-only variable; NEXT_PUBLIC_* values are compiled into browser bundles.
const API_KEY = (
  process.env.BACKOFFICE_API_KEY ||
  process.env.API_KEY ||
  process.env.NEXT_PUBLIC_API_KEY ||
  'databank2026'
).replace(/^Bearer\s+/i, '').trim();

// First path segment -> may be followed by an id / sub-path.
const ALLOWED_PREFIXES = new Set([
  'data', // includes data/tables
  'public', // public/submissions/coverage
  'form-items',
  'indicator-bank',
  'templates',
  'periods',
  'countrymap',
  'nationalsocietymap',
  'sectors',
  'subsectors',
  'sectors-subsectors',
  'common-words',
  'resources',
  'embed-content',
  'submitted-documents',
  'fdrs',
]);

function isSafeSegments(parts) {
  return parts.every((part) => part && part !== '.' && part !== '..' && !/[\\\x00-\x1f]/.test(part));
}

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const pathParts = Array.isArray(req.query.path) ? req.query.path : (req.query.path ? [req.query.path] : []);
    if (!pathParts.length || !isSafeSegments(pathParts) || !ALLOWED_PREFIXES.has(pathParts[0])) {
      return res.status(404).json({ error: 'Not found' });
    }
    // `fdrs` is only proxied for the published (public) feed.
    if (pathParts[0] === 'fdrs' && pathParts[1] !== 'published-data') {
      return res.status(404).json({ error: 'Not found' });
    }
    // Templates: the per-template data export is not a public Website feature.
    if (pathParts[0] === 'templates' && pathParts.includes('data')) {
      return res.status(404).json({ error: 'Not found' });
    }

    const { path: _p, ...rest } = req.query;
    const params = new URLSearchParams();
    for (const [name, value] of Object.entries(rest)) {
      if (['api_key', 'apikey', 'apiKey', 'access_token', 'token', 'key'].includes(name)) continue;
      (Array.isArray(value) ? value : [value]).forEach((v) => params.append(name, v));
    }
    if (pathParts[0] === 'submitted-documents') {
      // Only published documents, whatever the key could otherwise list.
      params.set('is_public', 'true');
      params.set('status', 'approved');
    }
    const query = params.toString();
    const url = `${BACKOFFICE_URL}/api/v1/${pathParts.map(encodeURIComponent).join('/')}${query ? `?${query}` : ''}`;
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
    res.status(502).json({ error: 'Backoffice proxy failed' });
  }
}
