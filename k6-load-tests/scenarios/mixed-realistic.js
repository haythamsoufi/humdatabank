// Phase 1.5 — mixed realistic profile
//
// Combines several Phase 1 / Phase 1.5 scenarios into a single k6 run using the
// `scenarios:` block, to surface DB pool / connection saturation that
// single-endpoint scripts miss.
//
// Composition:
//   - background:    /health every few seconds
//   - main reads:    round-robin GETs across non-rate-limited /api/v1 endpoints
//   - documents:     optional public document downloads (if K6_DOC_IDS provided)
//
// AI chat and writes are deliberately NOT included here — they have their own
// opt-in scripts with cost / safety guards.
//
// Run:
//   k6 run k6-load-tests/scenarios/mixed-realistic.js \
//     -e BASE_URL=https://your-staging-host \
//     -e K6_BACKOFFICE_API_KEY=your_staging_key

import http from 'k6/http';
import { sleep, fail } from 'k6';

import {
  url,
  headers,
  backofficeApiKey,
  csvEnv,
  defaultThresholds,
  profileValues,
  logProfile,
} from '../lib/config.js';
import {
  checkPublicHealth,
  checkJsonOk,
  checkBinaryOk,
} from '../lib/checks.js';

const READ_PATHS = [
  { path: '/api/v1/countrymap', name: 'v1-countrymap' },
  { path: '/api/v1/templates', name: 'v1-templates' },
  { path: '/api/v1/form-items', name: 'v1-form-items' },
  { path: '/api/v1/assigned-forms', name: 'v1-assigned-forms' },
  { path: '/api/v1/data/tables', name: 'v1-data-tables' },
];

const DOC_IDS = csvEnv('K6_DOC_IDS');
const HAS_DOCS = DOC_IDS.length > 0;

export const options = {
  scenarios: {
    health_background: {
      executor: 'constant-vus',
      vus: 1,
      duration: '2m',
      exec: 'healthBackground',
      tags: { scenario: 'health-background' },
    },
    api_v1_reads: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 5 },
        { duration: '1m', target: 5 },
        { duration: '30s', target: 0 },
      ],
      exec: 'apiV1Reads',
      tags: { scenario: 'api-v1-reads' },
    },
    documents: {
      executor: 'constant-vus',
      vus: HAS_DOCS ? 1 : 0,
      duration: '2m',
      exec: 'documentReads',
      tags: { scenario: 'documents' },
    },
  },
  thresholds: {
    ...defaultThresholds(),
    'http_req_duration{name:health}': [`p(95)<${profileValues().healthP95}`],
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
  // Warmup all endpoints once so cold-start doesn't poison thresholds.
  http.get(url('/health'), { headers: headers(), tags: { warmup: 'true' } });
  const apiHeaders = headers({ auth: 'apiKey' });
  for (const { path } of READ_PATHS) {
    http.get(url(path), { headers: apiHeaders, tags: { warmup: 'true' } });
  }
  if (HAS_DOCS) {
    http.get(url(`/documents/thumbnail/${DOC_IDS[0]}`), {
      headers: headers(),
      tags: { warmup: 'true' },
    });
  }
  return {};
}

export function healthBackground() {
  const res = http.get(url('/health'), {
    headers: headers(),
    tags: { name: 'health' },
  });
  checkPublicHealth(res);
  sleep(3);
}

export function apiV1Reads() {
  const reqHeaders = headers({ auth: 'apiKey' });
  const idx = (__ITER % READ_PATHS.length + READ_PATHS.length) % READ_PATHS.length;
  const { path, name } = READ_PATHS[idx];

  const res = http.get(url(path), {
    headers: reqHeaders,
    tags: { name },
  });
  checkJsonOk(res, name);
  sleep(1);
}

export function documentReads() {
  if (!HAS_DOCS) return;
  const reqHeaders = headers();
  const docId = DOC_IDS[__ITER % DOC_IDS.length];

  const res = http.get(url(`/documents/thumbnail/${docId}`), {
    headers: reqHeaders,
    tags: { name: 'document-thumbnail' },
  });
  checkBinaryOk(res, 'document-thumbnail');
  sleep(2);
}
