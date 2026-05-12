// Phase 1.5 — write smoke (OPT-IN, THROWAWAY STAGING DB ONLY)
//
// Performs ONE create per iteration against a low-impact /api/v1 write endpoint
// to surface obvious write-path regressions. Default endpoint is
// /api/v1/indicator-suggestions (configurable via K6_WRITE_PATH).
//
// SAFETY:
//   - NO-OP unless K6_WRITE_ENABLED=true.
//   - Only run against a throwaway staging database. The script does NOT clean up.
//   - 1 VU, 5 iterations by default. Do NOT raise without ops sign-off.
//
// Auth: Authorization: Bearer <K6_BACKOFFICE_API_KEY> (Backoffice external API).
//
// Run (only when you really mean it):
//   k6 run k6-load-tests/scenarios/write-smoke.js \
//     -e BASE_URL=https://your-staging-host \
//     -e K6_BACKOFFICE_API_KEY=your_staging_key \
//     -e K6_WRITE_ENABLED=true

import http from 'k6/http';
import { check, sleep } from 'k6';

import {
  url,
  headers,
  backofficeApiKey,
  envFlag,
  defaultThresholds,
  logProfile,
} from '../lib/config.js';

const ENABLED = envFlag('K6_WRITE_ENABLED', false);
const WRITE_PATH = (__ENV.K6_WRITE_PATH || '/api/v1/indicator-suggestions').trim();

export const options = {
  vus: 1,
  iterations: 5,
  thresholds: defaultThresholds(),
};

export function setup() {
  logProfile();
  if (!ENABLED) {
    console.warn(
      'write-smoke: K6_WRITE_ENABLED is not "true". Script is a NO-OP (safety guard).',
    );
    return { skip: true };
  }
  if (!backofficeApiKey()) {
    console.warn(
      'write-smoke: K6_BACKOFFICE_API_KEY is not set. NO-OP.',
    );
    return { skip: true };
  }
  console.warn(
    `write-smoke: ENABLED. Writing to ${WRITE_PATH}. THROWAWAY STAGING DB ONLY.`,
  );
  return { skip: false };
}

export default function writeSmoke(data) {
  if (data && data.skip) {
    return;
  }

  // Minimal, schema-light payload. The /api/v1/indicator-suggestions endpoint
  // accepts at least a free-text suggestion; tune fields here if you change
  // K6_WRITE_PATH to point elsewhere.
  const payload = JSON.stringify({
    suggestion: `k6 write-smoke ${Date.now()}`,
    source: 'k6-load-test',
  });

  const res = http.post(url(WRITE_PATH), payload, {
    headers: headers({ auth: 'apiKey', contentType: 'application/json' }),
    tags: { name: 'v1-write' },
  });

  check(res, {
    'write status is 2xx or 4xx (not 5xx)': (r) => r.status >= 200 && r.status < 500,
  });

  sleep(2);
}
