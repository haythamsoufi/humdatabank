// scripts/sync-indicators.js
// Sync ONLY indicator bank data from backend API to local data store

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
const INDICATORS_TMP = path.join(DATA_DIR, 'indicators.json.tmp');
const INDICATORS_FINAL = path.join(DATA_DIR, 'indicators.json');

async function syncIndicators() {
  console.log('🔄 Starting indicator-only sync...');
  console.log(`📡 API: ${API_BASE_URL}`);

  await fs.mkdir(DATA_DIR, { recursive: true });

  const indicatorsUrl = `${API_BASE_URL}/api/v1/indicator-bank`;
  console.log(`📥 Fetching indicators from: ${indicatorsUrl}`);

  let resp = await fetch(indicatorsUrl, {
    headers: CLEAN_API_KEY ? { Authorization: `Bearer ${CLEAN_API_KEY}` } : {}
  });
  if (!resp.ok && resp.status === 401 && CLEAN_API_KEY) {
    const queryUrl = `${indicatorsUrl}?api_key=${encodeURIComponent(CLEAN_API_KEY)}`;
    resp = await fetch(queryUrl);
  }
  if (!resp.ok) {
    throw new Error(`API error: ${resp.status} ${resp.statusText}`);
  }

  const payload = await resp.json();
  const indicators = payload?.indicators || [];

  // Validate JSON serialization before overwriting
  const json = JSON.stringify(indicators, null, 2);
  JSON.parse(json);

  await fs.writeFile(INDICATORS_TMP, json);
  await fs.rename(INDICATORS_TMP, INDICATORS_FINAL);

  console.log(`✅ Synced ${indicators.length} indicators`);
  console.log(`📁 Wrote: ${INDICATORS_FINAL}`);
}

syncIndicators().catch(async (err) => {
  console.error('❌ Indicator sync failed:', err);
  try {
    await fs.unlink(INDICATORS_TMP);
  } catch (e) {
    // ignore
  }
  process.exit(1);
});
