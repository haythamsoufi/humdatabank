// Phase 1 — minimal /api/v1 reads
//
// Hits a small, stable subset of Backoffice external API GETs that are flagged
// `api_key_or_session` and `rate_limited: False` in
// Backoffice/app/routes/admin/api_management.py:
//
//   GET /api/v1/countrymap   (Countries & Geography, not rate-limited)
//   GET /api/v1/templates    (Templates & Form Items, not rate-limited)
//
// Auth is via Authorization: Bearer <key>. Query-string keys are rejected by
// Backoffice/app/utils/auth.py:_extract_api_key().
//
// If K6_BACKOFFICE_API_KEY is unset, the script aborts in setup().
//
// Run:
//   k6 run k6-load-tests/scenarios/api-v1-reads.js \
//     -e BASE_URL=https://your-staging-host \
//     -e K6_BACKOFFICE_API_KEY=your_staging_key

import http from 'k6/http';
import { sleep, fail } from 'k6';

import {
  url,
  headers,
  backofficeApiKey,
  defaultThresholds,
  logProfile,
} from '../lib/config.js';
import { checkJsonOk } from '../lib/checks.js';

const PATHS = [
  { path: '/api/v1/countrymap', name: 'v1-countrymap' },
  { path: '/api/v1/templates', name: 'v1-templates' },
];

export const options = {
  vus: 2,
  duration: '30s',
  thresholds: defaultThresholds(),
};

export function setup() {
  logProfile();
  if (!backofficeApiKey()) {
    fail(
      'K6_BACKOFFICE_API_KEY is not set. ' +
        'Provide a Backoffice Bearer API key (read-only, staging) and re-run.',
    );
  }
  // Warmup each endpoint once.
  const reqHeaders = headers({ auth: 'apiKey' });
  for (const { path } of PATHS) {
    http.get(url(path), { headers: reqHeaders, tags: { warmup: 'true' } });
  }
  return {};
}

export default function apiV1Reads() {
  const reqHeaders = headers({ auth: 'apiKey' });

  for (const { path, name } of PATHS) {
    const res = http.get(url(path), {
      headers: reqHeaders,
      tags: { name },
    });
    checkJsonOk(res, name);
  }

  sleep(1);
}
