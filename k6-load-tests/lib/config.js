// Shared configuration helpers for the k6 suite.
//
// All scripts import from this file for:
//   - resolving BASE_URL
//   - selecting a threshold *profile* (local vs staging)
//   - building default request headers (Bearer auth optional)
//   - exposing safe default thresholds (starting points, NOT SLOs)
//
// Backoffice-only. Do not point at the Website or mobile-app binary.

const DEFAULT_BASE_URL = 'http://127.0.0.1:5000';

// ---------------------------------------------------------------------------
// BASE_URL
// ---------------------------------------------------------------------------

export function baseUrl() {
  const raw = (__ENV.BASE_URL || DEFAULT_BASE_URL).trim();
  return raw.replace(/\/+$/, '');
}

export function url(path) {
  const p = String(path || '');
  return `${baseUrl()}${p.startsWith('/') ? '' : '/'}${p}`;
}

// ---------------------------------------------------------------------------
// Auth helpers
// ---------------------------------------------------------------------------

export function backofficeApiKey() {
  return (__ENV.K6_BACKOFFICE_API_KEY || '').trim();
}

export function aiToken() {
  return (__ENV.K6_AI_TOKEN || '').trim();
}

export function envFlag(name, defaultValue = false) {
  const raw = (__ENV[name] || '').toString().trim().toLowerCase();
  if (raw === '') return defaultValue;
  return raw === 'true' || raw === '1' || raw === 'yes';
}

export function csvEnv(name) {
  const raw = (__ENV[name] || '').trim();
  if (!raw) return [];
  return raw
    .split(',')
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

// Build standard headers for a request. Pass { auth: 'apiKey' | 'aiToken' | null }
// to attach an Authorization header.
export function headers(opts = {}) {
  const h = {
    Accept: 'application/json',
  };
  if (opts.contentType) {
    h['Content-Type'] = opts.contentType;
  }
  if (opts.auth === 'apiKey') {
    const key = backofficeApiKey();
    if (key) h.Authorization = `Bearer ${key}`;
  } else if (opts.auth === 'aiToken') {
    const tok = aiToken();
    if (tok) h.Authorization = `Bearer ${tok}`;
  }
  if (opts.extra) {
    Object.assign(h, opts.extra);
  }
  return h;
}

// ---------------------------------------------------------------------------
// Threshold profiles
// ---------------------------------------------------------------------------
//
// Two profiles:
//
//   - "staging"  : strict thresholds suitable for a warmed-up server behind
//                  gunicorn (or equivalent). Use against staging / production-
//                  like deployments.
//   - "local"    : relaxed thresholds that tolerate the Flask development
//                  server's single-threaded Werkzeug behavior, lazy imports,
//                  and the first-request cold start.
//
// Selection order:
//   1. If K6_PROFILE env var is set ("local" or "staging"), use it.
//   2. Otherwise auto-detect from BASE_URL host:
//        - 127.0.0.1 / localhost / [::1] / 0.0.0.0 / *.local  -> "local"
//        - anything else                                       -> "staging"
//
// Numbers are *starting points* — tune per environment, do not treat as SLOs.

const PROFILES = {
  staging: {
    failedRate: 0.01,
    healthP95: 300,
    healthP99: 800,
    aiHealthP95: 2000,
    aiHealthP99: 5000,
    defaultP95: 1500,
    defaultP99: 3000,
    heavyP95: 3000,
    aiChatP95: 30000,
    documentP95: 3000,
    documentP99: 8000,
  },
  local: {
    failedRate: 0.05,
    healthP95: 2000,
    healthP99: 5000,
    aiHealthP95: 5000,
    aiHealthP99: 10000,
    defaultP95: 5000,
    defaultP99: 10000,
    heavyP95: 8000,
    aiChatP95: 60000,
    documentP95: 8000,
    documentP99: 20000,
  },
};

function _isLocalHost(host) {
  if (!host) return false;
  const h = host.toLowerCase();
  return (
    h === 'localhost' ||
    h === '127.0.0.1' ||
    h === '0.0.0.0' ||
    h === '[::1]' ||
    h === '::1' ||
    h.endsWith('.local')
  );
}

function _hostFromBaseUrl() {
  const raw = baseUrl();
  // Cheap parse — enough for host extraction without URL polyfill.
  const m = raw.match(/^[a-z]+:\/\/([^/:]+)/i);
  return m ? m[1] : '';
}

export function profile() {
  const explicit = (__ENV.K6_PROFILE || '').toLowerCase().trim();
  if (explicit === 'staging' || explicit === 'local') {
    return explicit;
  }
  return _isLocalHost(_hostFromBaseUrl()) ? 'local' : 'staging';
}

export function profileValues() {
  return PROFILES[profile()];
}

// Default thresholds applied to most scenarios.
export function defaultThresholds() {
  const p = profileValues();
  return {
    http_req_failed: [`rate<${p.failedRate}`],
    http_req_duration: [`p(95)<${p.defaultP95}`, `p(99)<${p.defaultP99}`],
  };
}

// Strict thresholds for the lightweight /health endpoint.
export function healthThresholds() {
  const p = profileValues();
  return {
    http_req_failed: [`rate<${p.failedRate}`],
    'http_req_duration{name:health}': [
      `p(95)<${p.healthP95}`,
      `p(99)<${p.healthP99}`,
    ],
  };
}

// Thresholds for the AI health endpoint (slower than /health due to lazy init).
export function aiHealthThresholds() {
  const p = profileValues();
  return {
    'http_req_duration{name:ai-health}': [
      `p(95)<${p.aiHealthP95}`,
      `p(99)<${p.aiHealthP99}`,
    ],
  };
}

// Print the resolved profile once at script start so output is self-explanatory.
export function logProfile() {
  console.log(
    `[k6] profile=${profile()} base_url=${baseUrl()}`,
  );
}
