// Phase 1.5 — AI chat smoke (OPT-IN, COST-GUARDED)
//
// Sends a tiny number of POST requests to /api/ai/v2/chat to verify the chat
// pipeline responds under minimal load. This costs LLM tokens — keep it tiny.
//
// COST GUARD: the script is a NO-OP unless K6_AI_CHAT_ENABLED=true.
//
// Auth: a preissued AI Bearer JWT (K6_AI_TOKEN) obtained via:
//   GET /api/ai/v2/token   (while logged in to the Backoffice)
// We never log in inside the script — that would hit auth rate limits and skew
// results.
//
// Defaults: 1 VU, 5 iterations total. Do NOT raise these without ops sign-off.
//
// Run (only when you really mean it):
//   k6 run k6-load-tests/scenarios/ai-chat-smoke.js \
//     -e BASE_URL=https://your-staging-host \
//     -e K6_AI_TOKEN=eyJ... \
//     -e K6_AI_CHAT_ENABLED=true

import http from 'k6/http';
import { check, sleep } from 'k6';

import {
  url,
  headers,
  aiToken,
  envFlag,
  defaultThresholds,
  profileValues,
  logProfile,
} from '../lib/config.js';

const ENABLED = envFlag('K6_AI_CHAT_ENABLED', false);

export const options = {
  vus: 1,
  iterations: 5,
  thresholds: {
    ...defaultThresholds(),
    'http_req_duration{name:ai-chat}': [`p(95)<${profileValues().aiChatP95}`],
  },
};

export function setup() {
  logProfile();
  if (!ENABLED) {
    console.warn(
      'ai-chat-smoke: K6_AI_CHAT_ENABLED is not "true". Script is a NO-OP (cost guard).',
    );
    return { skip: true };
  }
  if (!aiToken()) {
    console.warn(
      'ai-chat-smoke: K6_AI_TOKEN is not set. Cannot authenticate. NO-OP.',
    );
    return { skip: true };
  }
  return { skip: false };
}

export default function aiChatSmoke(data) {
  if (data && data.skip) {
    return;
  }

  const payload = JSON.stringify({
    message: 'health probe — please reply with a single word: ok',
  });

  const res = http.post(url('/api/ai/v2/chat'), payload, {
    headers: headers({ auth: 'aiToken', contentType: 'application/json' }),
    tags: { name: 'ai-chat' },
    timeout: '60s',
  });

  check(res, {
    'ai-chat status is 200 or 429': (r) => r.status === 200 || r.status === 429,
  });

  sleep(2);
}
