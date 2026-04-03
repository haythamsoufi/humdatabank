// pages/api/geoboundaries.js
// Server-side proxy for geoBoundaries to avoid browser CORS issues when fetching GitHub raw URLs.

const cache = new Map(); // key -> { ts, data }
const TTL_MS = 6 * 60 * 60 * 1000; // 6 hours

function isValidIso3(v) {
  return typeof v === 'string' && /^[A-Z]{3}$/.test(v);
}

function isValidAdm(v) {
  return typeof v === 'string' && /^ADM[0-5]$/.test(v);
}

function rewriteGitHubRaw(url) {
  // geoBoundaries returns URLs like:
  // https://github.com/wmgeolab/geoBoundaries/raw/<hash>/releaseData/gbOpen/SYR/ADM1/geoBoundaries-SYR-ADM1.geojson
  // Convert to raw.githubusercontent.com to avoid redirects/CORS weirdness:
  // https://raw.githubusercontent.com/wmgeolab/geoBoundaries/<hash>/releaseData/...
  try {
    const u = new URL(url);
    if (u.hostname !== 'github.com') return url;
    const parts = u.pathname.split('/').filter(Boolean); // [org, repo, 'raw', hash, ...rest]
    if (parts.length >= 5 && parts[2] === 'raw') {
      const [org, repo, _raw, hash, ...rest] = parts;
      return `https://raw.githubusercontent.com/${org}/${repo}/${hash}/${rest.join('/')}`;
    }
  } catch (_e) {}
  return url;
}

async function fetchJson(url, options = {}) {
  // Add timeout for large file downloads (60 seconds for ADM3 files)
  const timeoutMs = options.timeout || 60000;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const resp = await fetch(url, {
      redirect: 'follow',
      signal: controller.signal,
      ...options
    });
    clearTimeout(timeoutId);

    if (!resp.ok) {
      const text = await resp.text().catch(() => '');
      const err = new Error(`HTTP ${resp.status} for ${url}: ${text.slice(0, 200)}`);
      err.statusCode = resp.status;
      throw err;
    }
    return await resp.json();
  } catch (error) {
    clearTimeout(timeoutId);
    if (error.name === 'AbortError') {
      const timeoutErr = new Error(`Request timeout after ${timeoutMs}ms`);
      timeoutErr.statusCode = 504;
      throw timeoutErr;
    }
    throw error;
  }
}

export default async function handler(req, res) {
  try {
    const iso3 = String(req.query.iso3 || '').toUpperCase();
    const adm = String(req.query.adm || '').toUpperCase();
    const checkOnly = String(req.query.check || '').toLowerCase() === '1' || String(req.query.check || '').toLowerCase() === 'true';

    if (!isValidIso3(iso3) || !isValidAdm(adm)) {
      return res.status(400).json({ error: 'Invalid parameters. Expected iso3=AAA and adm=ADM0..ADM5.' });
    }

    const key = `${iso3}:${adm}`;
    const cached = cache.get(key);
    // For "check only" requests, consider cached data as available without re-fetching.
    if (checkOnly) {
      if (cached && (Date.now() - cached.ts) < TTL_MS) {
        res.setHeader('Cache-Control', 'public, max-age=3600');
        if (req.method === 'HEAD') return res.status(200).end();
        return res.status(200).json({ ok: true, cached: true });
      }
    }

    if (!checkOnly && cached && (Date.now() - cached.ts) < TTL_MS) {
      res.setHeader('Cache-Control', 'public, max-age=3600');
      return res.status(200).json(cached.data);
    }

    const metaUrl = `https://www.geoboundaries.org/api/current/gbOpen/${iso3}/${adm}`;
    let meta;
    try {
      meta = await fetchJson(metaUrl, { timeout: 10000 }); // 10s timeout for metadata
    } catch (e) {
      // If metadata fetch fails, return 404 (data not available) rather than 500/502
      res.setHeader('Cache-Control', 'public, max-age=300');
      if (req.method === 'HEAD') return res.status(404).end();
      return res.status(404).json({ error: `Admin level ${adm} not available for ${iso3}` });
    }

    const gjUrlRaw =
      meta?.gjDownloadURL ||
      meta?.geoJSONUrl ||
      meta?.downloadURL ||
      null;
    if (!gjUrlRaw) {
      res.setHeader('Cache-Control', 'public, max-age=300');
      if (req.method === 'HEAD') return res.status(404).end();
      return res.status(404).json({ error: `Admin level ${adm} not available for ${iso3}: No GeoJSON download URL found.` });
    }

    // Lightweight availability check: don't download huge GeoJSON, just confirm that metadata exists.
    if (checkOnly || req.method === 'HEAD') {
      res.setHeader('Cache-Control', 'public, max-age=3600');
      if (req.method === 'HEAD') return res.status(200).end();
      return res.status(200).json({ ok: true, iso3, adm });
    }

    // IMPORTANT: Do NOT rewrite to raw.githubusercontent.com here.
    // geoBoundaries GitHub raw links may be backed by Git LFS; raw.githubusercontent.com can return LFS pointer files.
    // The github.com/.../raw/... URL (and/or media.githubusercontent.com) returns the actual GeoJSON.
    const gjUrl = String(gjUrlRaw);
    let geojson;
    try {
      // Use longer timeout for ADM3 files which can be very large (120s)
      const timeout = adm === 'ADM3' ? 120000 : 60000;
      geojson = await fetchJson(gjUrl, { timeout });
    } catch (e) {
      // If GeoJSON fetch fails (timeout, network error, etc.), return 404
      // This allows the client to gracefully handle missing data
      if (e.statusCode === 504) {
        res.setHeader('Cache-Control', 'public, max-age=300');
        return res.status(404).json({ error: `Admin level ${adm} for ${iso3} timed out - data may be too large or unavailable` });
      }
      res.setHeader('Cache-Control', 'public, max-age=300');
      return res.status(404).json({ error: `Admin level ${adm} not available for ${iso3}: ${e.message}` });
    }

    cache.set(key, { ts: Date.now(), data: geojson });
    res.setHeader('Cache-Control', 'public, max-age=3600');
    return res.status(200).json(geojson);
  } catch (e) {
    // Fallback for any unexpected errors - return 404 to allow graceful handling
    console.error('geoboundaries API error:', e);
    const status = e?.statusCode && Number.isFinite(e.statusCode) && e.statusCode < 500 ? e.statusCode : 404;
    return res.status(status).json({ error: e?.message || 'Data not available' });
  }
}
