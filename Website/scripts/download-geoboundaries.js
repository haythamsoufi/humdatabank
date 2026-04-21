#!/usr/bin/env node
/**
 * Script to download geoBoundaries GeoJSON files and save them to public/geoboundaries/
 *
 * Usage:
 *   node scripts/download-geoboundaries.js [ISO3] [ADM]...
 *
 * Examples:
 *   node scripts/download-geoboundaries.js AFG ADM0 ADM1        # Download ADM0 and ADM1 for Afghanistan
 *   node scripts/download-geoboundaries.js SYR ADM0 ADM1 ADM2   # Download ADM0, ADM1, ADM2 for Syria
 *   node scripts/download-geoboundaries.js SYR ADM0 ADM1 ADM2 ADM3  # Download all levels for Syria
 *   node scripts/download-geoboundaries.js ALL ADM0 ADM1        # Download ADM0 and ADM1 for all countries
 */

const fs = require('fs');
const path = require('path');

const PUBLIC_DIR = path.join(__dirname, '..', 'public');
const GEOBOUNDARIES_DIR = path.join(PUBLIC_DIR, 'geoboundaries');
const COUNTRIES_FILE = path.join(__dirname, '..', 'data', 'countries.json');

async function fetchJson(url) {
  const resp = await fetch(url, { redirect: 'follow' });
  if (!resp.ok) {
    const text = await resp.text().catch(() => '');
    throw new Error(`HTTP ${resp.status} for ${url}: ${text.slice(0, 200)}`);
  }
  return await resp.json();
}

async function downloadGeoBoundary(iso3, adm) {
  try {
    console.log(`Fetching metadata for ${iso3}/${adm}...`);
    const metaUrl = `https://www.geoboundaries.org/api/current/gbOpen/${iso3}/${adm}`;
    const meta = await fetchJson(metaUrl);

    const gjUrlRaw =
      meta?.gjDownloadURL ||
      meta?.geoJSONUrl ||
      meta?.downloadURL ||
      null;

    if (!gjUrlRaw) {
      console.warn(`  ⚠ No GeoJSON URL found for ${iso3}/${adm}`);
      return false;
    }

    console.log(`  Downloading GeoJSON from ${gjUrlRaw}...`);
    const geojson = await fetchJson(gjUrlRaw);

    // Ensure directory exists
    const countryDir = path.join(GEOBOUNDARIES_DIR, iso3);
    if (!fs.existsSync(countryDir)) {
      fs.mkdirSync(countryDir, { recursive: true });
    }

    // Save file
    const filePath = path.join(countryDir, `${adm}.geojson`);
    fs.writeFileSync(filePath, JSON.stringify(geojson, null, 2));

    const fileSizeKB = Math.round(fs.statSync(filePath).size / 1024);
    console.log(`  ✓ Saved ${filePath} (${fileSizeKB} KB)`);
    return true;
  } catch (error) {
    console.error(`  ✗ Failed to download ${iso3}/${adm}: ${error.message}`);
    return false;
  }
}

async function main() {
  const args = process.argv.slice(2);

  if (args.length < 2) {
    console.error('Usage: node scripts/download-geoboundaries.js [ISO3|ALL] [ADM]...');
    console.error('Example: node scripts/download-geoboundaries.js AFG ADM0 ADM1');
    console.error('Example: node scripts/download-geoboundaries.js ALL ADM0 ADM1');
    process.exit(1);
  }

  const iso3Arg = args[0].toUpperCase();
  const adms = args.slice(1).map(a => a.toUpperCase()).filter(a => /^ADM[0-5]$/.test(a));

  if (adms.length === 0) {
    console.error('Error: Please specify at least one admin level (ADM0, ADM1, ADM2, ADM3, etc.)');
    process.exit(1);
  }

  // Ensure public/geoboundaries directory exists
  if (!fs.existsSync(GEOBOUNDARIES_DIR)) {
    fs.mkdirSync(GEOBOUNDARIES_DIR, { recursive: true });
  }

  let countries = [];

  if (iso3Arg === 'ALL') {
    // Load all countries from countries.json
    if (!fs.existsSync(COUNTRIES_FILE)) {
      console.error(`Error: Countries file not found at ${COUNTRIES_FILE}`);
      process.exit(1);
    }
    const countriesData = JSON.parse(fs.readFileSync(COUNTRIES_FILE, 'utf8'));
    countries = countriesData.map(c => c.iso3).filter(Boolean);
    console.log(`Downloading ${adms.join(', ')} for ${countries.length} countries...\n`);
  } else {
    if (!/^[A-Z]{3}$/.test(iso3Arg)) {
      console.error(`Error: Invalid ISO3 code: ${iso3Arg}`);
      process.exit(1);
    }
    countries = [iso3Arg];
  }

  let successCount = 0;
  let failCount = 0;

  for (const iso3 of countries) {
    console.log(`\n${iso3}:`);
    for (const adm of adms) {
      const success = await downloadGeoBoundary(iso3, adm);
      if (success) {
        successCount++;
      } else {
        failCount++;
      }
      // Small delay to avoid rate limiting
      await new Promise(resolve => setTimeout(resolve, 200));
    }
  }

  console.log(`\n✓ Completed: ${successCount} successful, ${failCount} failed`);
}

main().catch(error => {
  console.error('Fatal error:', error);
  process.exit(1);
});
