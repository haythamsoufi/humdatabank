// scripts/sync-sectors.js
// Sync ONLY sectors/subsectors data from backend API to local data store

const fs = require('fs').promises;
const path = require('path');

// Load environment variables from .env.local or .env (best effort)
try {
  const dotenv = require('dotenv');
  const fsSync = require('fs');
  const envPath = fsSync.existsSync('.env.local') ? '.env.local' : '.env';
  dotenv.config({ path: envPath });
} catch (e) {
  // noop: dotenv is optional
}

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.API_BASE_URL ||
  'https://backoffice-databank.fly.dev';

const API_KEY = process.env.NEXT_PUBLIC_API_KEY || process.env.API_KEY || 'databank2026';
const CLEAN_API_KEY = (API_KEY || '').replace(/^Bearer\s+/i, '').trim();

const DATA_DIR = path.join(__dirname, '..', 'data');
const OUT_TMP = path.join(DATA_DIR, 'sectors_subsectors.json.tmp');
const OUT_FINAL = path.join(DATA_DIR, 'sectors_subsectors.json');

async function syncSectors() {
  console.log('🔄 Starting sectors/subsectors sync...');
  console.log(`📡 API: ${API_BASE_URL}`);

  await fs.mkdir(DATA_DIR, { recursive: true });

  const url = `${API_BASE_URL}/api/v1/sectors-subsectors`;
  console.log(`📥 Fetching sectors/subsectors from: ${url}`);

  let resp = await fetch(url, {
    headers: CLEAN_API_KEY ? { Authorization: `Bearer ${CLEAN_API_KEY}` } : {}
  });
  if (!resp.ok && resp.status === 401 && CLEAN_API_KEY) {
    const queryUrl = `${url}?api_key=${encodeURIComponent(CLEAN_API_KEY)}`;
    resp = await fetch(queryUrl);
  }
  if (!resp.ok) {
    throw new Error(`API error: ${resp.status} ${resp.statusText}`);
  }

  const payload = await resp.json();
  const sectors = payload?.sectors || [];

  // Persist only what we need (keep the full payload shape: { sectors: [...] })
  const json = JSON.stringify({ sectors }, null, 2);
  JSON.parse(json);

  await fs.writeFile(OUT_TMP, json);
  await fs.rename(OUT_TMP, OUT_FINAL);

  console.log(`✅ Synced ${sectors.length} sectors`);
  console.log(`📁 Wrote: ${OUT_FINAL}`);
}

syncSectors().catch(async (err) => {
  console.error('❌ Sectors sync failed:', err);
  try {
    await fs.unlink(OUT_TMP);
  } catch (e) {
    // ignore
  }
  process.exit(1);
});
