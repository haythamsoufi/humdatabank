// Phase 1.5 — extended /api/v1 read coverage
//
// Round-robin GETs across the non-rate-limited /api/v1 endpoints from
// Backoffice/app/routes/admin/api_management.py (auth: 'api_key_or_session',
// rate_limited: False):
//
//   /api/v1/countrymap
//   /api/v1/templates
//   /api/v1/form-items
//   /api/v1/assigned-forms
//   /api/v1/data/tables
//   /api/v1/submissions
//
// Each request is tagged so the stdout summary and any export split metrics
// per endpoint. Conservative VUs because some of these hit DB joins.
//
// Run:
//   k6 run k6-load-tests/scenarios/api-v1-reads-extended.js \
//     -e BASE_URL=https://your-staging-host \
//     -e K6_BACKOFFICE_API_KEY=your_staging_key

import http from 'k6/http';
import { sleep, fail } from 'k6';

import {
  url,
  headers,
  backofficeApiKey,
  defaultThresholds,
  profileValues,
  logProfile,
} from '../lib/config.js';
import { checkJsonOk } from '../lib/checks.js';

const PATHS = [
  { path: '/api/v1/countrymap', name: 'v1-countrymap' },
  { path: '/api/v1/templates', name: 'v1-templates' },
  { path: '/api/v1/form-items', name: 'v1-form-items' },
  { path: '/api/v1/assigned-forms', name: 'v1-assigned-forms' },
  { path: '/api/v1/data/tables', name: 'v1-data-tables' },
  { path: '/api/v1/submissions', name: 'v1-submissions' },
];

export const options = {
  vus: 5,
  duration: '1m',
  thresholds: {
    ...defaultThresholds(),
    'http_req_duration{name:v1-data-tables}': [
      `p(95)<${profileValues().heavyP95}`,
    ],
  },
};

export function setup() {
  logProfile();
  if (!backofficeApiKey()) {
    fail(
      'K6_BACKOFFICE_API_KEY is not set. ' +
        'Provide a Backoffice Bearer API key (read-only, staging) and re-run.',
    );
  }
  const reqHeaders = headers({ auth: 'apiKey' });
  for (const { path } of PATHS) {
    http.get(url(path), { headers: reqHeaders, tags: { warmup: 'true' } });
  }
  return {};
}

export default function apiV1ReadsExtended() {
  const reqHeaders = headers({ auth: 'apiKey' });

  // Round-robin across endpoints, one request per iteration to keep load even.
  const idx = (__ITER % PATHS.length + PATHS.length) % PATHS.length;
  const { path, name } = PATHS[idx];

  const res = http.get(url(path), {
    headers: reqHeaders,
    tags: { name },
  });
  checkJsonOk(res, name);

  sleep(1);
}
