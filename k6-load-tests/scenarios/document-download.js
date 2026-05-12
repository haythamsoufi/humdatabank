// Phase 1.5 — public document/thumbnail downloads
//
// Exercises the storage I/O path (Azure Blob or filesystem per UPLOAD_STORAGE_PROVIDER)
// via the public download endpoints in Backoffice/app/routes/public.py:
//
//   GET /documents/thumbnail/<doc_id>           (image only)
//   GET /resources/download/<resource_id>/<lang>
//   GET /resources/thumbnail/<resource_id>/<lang>
//
// IDs are caller-supplied (no hardcoded staging data) via env vars:
//   K6_DOC_IDS=12,34,56
//   K6_RESOURCE_IDS=7:en,9:fr
//
// If neither is set, the script logs and exits with no requests.
//
// Run:
//   k6 run k6-load-tests/scenarios/document-download.js \
//     -e BASE_URL=https://your-staging-host \
//     -e K6_DOC_IDS=12,34,56 \
//     -e K6_RESOURCE_IDS=7:en,9:fr

import http from 'k6/http';
import { sleep } from 'k6';

import {
  url,
  headers,
  csvEnv,
  defaultThresholds,
  profileValues,
  logProfile,
} from '../lib/config.js';
import { checkBinaryOk } from '../lib/checks.js';

const DOC_IDS = csvEnv('K6_DOC_IDS');
const RESOURCE_PAIRS = csvEnv('K6_RESOURCE_IDS')
  .map((entry) => {
    const [id, lang] = entry.split(':').map((s) => (s || '').trim());
    if (!id || !lang) return null;
    return { id, lang };
  })
  .filter(Boolean);

const HAS_TARGETS = DOC_IDS.length > 0 || RESOURCE_PAIRS.length > 0;

export const options = {
  vus: 2,
  duration: '30s',
  thresholds: {
    ...defaultThresholds(),
    'http_req_duration{name:resource-download}': [
      `p(95)<${profileValues().documentP95}`,
      `p(99)<${profileValues().documentP99}`,
    ],
  },
};

export function setup() {
  logProfile();
  if (!HAS_TARGETS) {
    console.warn(
      'document-download: no K6_DOC_IDS or K6_RESOURCE_IDS provided. ' +
        'No requests will be sent. Set at least one to exercise the download path.',
    );
    return {};
  }
  const reqHeaders = headers();
  if (DOC_IDS.length > 0) {
    http.get(url(`/documents/thumbnail/${DOC_IDS[0]}`), {
      headers: reqHeaders,
      tags: { warmup: 'true' },
    });
  }
  if (RESOURCE_PAIRS.length > 0) {
    const { id, lang } = RESOURCE_PAIRS[0];
    http.get(url(`/resources/download/${id}/${lang}`), {
      headers: reqHeaders,
      tags: { warmup: 'true' },
    });
  }
  return {};
}

export default function documentDownload() {
  if (!HAS_TARGETS) {
    return;
  }

  const reqHeaders = headers();

  if (DOC_IDS.length > 0) {
    const docId = DOC_IDS[__ITER % DOC_IDS.length];
    const res = http.get(url(`/documents/thumbnail/${docId}`), {
      headers: reqHeaders,
      tags: { name: 'document-thumbnail' },
    });
    checkBinaryOk(res, 'document-thumbnail');
  }

  if (RESOURCE_PAIRS.length > 0) {
    const { id, lang } = RESOURCE_PAIRS[__ITER % RESOURCE_PAIRS.length];

    const dl = http.get(url(`/resources/download/${id}/${lang}`), {
      headers: reqHeaders,
      tags: { name: 'resource-download' },
    });
    checkBinaryOk(dl, 'resource-download');

    const thumb = http.get(url(`/resources/thumbnail/${id}/${lang}`), {
      headers: reqHeaders,
      tags: { name: 'resource-thumbnail' },
    });
    checkBinaryOk(thumb, 'resource-thumbnail');
  }

  sleep(1);
}
