// Phase 1 — Backoffice smoke
//
// Hits two unauthenticated health endpoints exposed by the Flask Backoffice:
//   GET /health             (Backoffice/app/routes/public.py)
//   GET /api/ai/v2/health   (Backoffice/app/routes/ai.py)
//
// Notes:
//   - /api/ai/v2/health may return 503 on environments where OPENAI_API_KEY (or
//     related AI config) is missing. That is treated as an environment signal,
//     NOT a k6 failure. The check accepts 200 OR 503.
//   - We deliberately do NOT pass ?probe=embedding to avoid LLM/embed cost.
//   - setup() warms both endpoints once so the cold-start outlier is not
//     counted in measured metrics.
//   - Thresholds adapt to the profile (local vs staging) selected by
//     K6_PROFILE or auto-detected from BASE_URL.
//
// Run:
//   k6 run k6-load-tests/scenarios/smoke-backoffice.js -e BASE_URL=http://127.0.0.1:5000
//   k6 run k6-load-tests/scenarios/smoke-backoffice.js -e BASE_URL=https://your-staging-host

import http from 'k6/http';
import { sleep } from 'k6';

import {
  url,
  headers,
  healthThresholds,
  aiHealthThresholds,
  logProfile,
} from '../lib/config.js';
import { checkPublicHealth, checkAiHealth } from '../lib/checks.js';

export const options = {
  vus: 1,
  duration: '30s',
  thresholds: {
    ...healthThresholds(),
    ...aiHealthThresholds(),
  },
};

export function setup() {
  logProfile();
  // Warmup: one request to each endpoint to discount cold-start latency
  // (lazy imports, AI integration init, DB pool open).
  http.get(url('/health'), { headers: headers(), tags: { warmup: 'true' } });
  http.get(url('/api/ai/v2/health'), {
    headers: headers(),
    tags: { warmup: 'true' },
  });
  return {};
}

export default function smokeBackoffice() {
  const reqHeaders = headers();

  const healthRes = http.get(url('/health'), {
    headers: reqHeaders,
    tags: { name: 'health' },
  });
  checkPublicHealth(healthRes);

  const aiHealthRes = http.get(url('/api/ai/v2/health'), {
    headers: reqHeaders,
    tags: { name: 'ai-health' },
  });
  checkAiHealth(aiHealthRes);

  sleep(1);
}
