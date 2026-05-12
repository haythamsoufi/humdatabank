// Shared response checks for k6 scenarios.
//
// Keep checks small and tolerant — load-testing infrastructure should not be
// brittle to harmless schema additions in the Backoffice.

import { check } from 'k6';

export function checkOk(res, name) {
  return check(res, {
    [`${name} status is 200`]: (r) => r.status === 200,
  });
}

// Accept either 200 or 503; AI health legitimately returns 503 when env is missing.
export function checkAiHealth(res) {
  return check(res, {
    'ai-health status is 200 or 503': (r) => r.status === 200 || r.status === 503,
    'ai-health body has checks object': (r) => {
      try {
        const j = r.json();
        return j && typeof j === 'object' && 'checks' in j;
      } catch (_) {
        return false;
      }
    },
  });
}

export function checkPublicHealth(res) {
  return check(res, {
    'health status is 200': (r) => r.status === 200,
    'health body has status field': (r) => {
      try {
        const j = r.json();
        return j && j.status === 'healthy';
      } catch (_) {
        return false;
      }
    },
  });
}

// Generic JSON-shape check: 200 + parseable JSON body. Tolerant of varied schemas.
export function checkJsonOk(res, name) {
  return check(res, {
    [`${name} status is 200`]: (r) => r.status === 200,
    [`${name} body is JSON`]: (r) => {
      try {
        const j = r.json();
        return j !== null && j !== undefined;
      } catch (_) {
        return false;
      }
    },
  });
}

// For document/binary downloads: 200 + non-empty body.
export function checkBinaryOk(res, name) {
  return check(res, {
    [`${name} status is 200`]: (r) => r.status === 200,
    [`${name} body is non-empty`]: (r) => {
      const b = r.body;
      if (!b) return false;
      if (typeof b === 'string') return b.length > 0;
      // ArrayBuffer / Uint8Array
      try {
        return b.byteLength > 0;
      } catch (_) {
        return false;
      }
    },
  });
}
