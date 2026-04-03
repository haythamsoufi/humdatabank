// lib/aiAuth.js
// Simple utility to fetch and manage AI authentication token for logged-in users

const AI_TOKEN_KEY = 'ai_token';
const TOKEN_CACHE_TTL = 30 * 60 * 1000; // 30 minutes

let cachedToken = null;
let tokenExpiry = null;

/**
 * Resolve Backoffice base URL (same logic as chatbot proxy)
 */
function resolveBackofficeBaseUrl() {
  const isDev = process.env.NODE_ENV === 'development';
  const publicUrl = process.env.NEXT_PUBLIC_API_URL;
  const internalUrl = process.env.NEXT_INTERNAL_API_URL || process.env.INTERNAL_API_URL;

  if (internalUrl) return internalUrl.replace(/\/$/, '');
  if (publicUrl) return publicUrl.replace(/\/$/, '');
  return isDev ? 'http://localhost:5000' : 'https://backoffice-databank.fly.dev';
}

/**
 * Fetch AI token from Backoffice with retry logic.
 * This will only work if the user has an active session cookie with Backoffice.
 * Returns null if not authenticated or if request fails.
 */
export async function fetchAiToken(maxRetries = 2) {
  // Check cache first
  if (cachedToken && tokenExpiry && Date.now() < tokenExpiry) {
    return cachedToken;
  }

  let lastError = null;

  const isBrowser = typeof window !== 'undefined';
  // In browser, use same-origin proxy to avoid CORS
  const url = isBrowser ? '/api/ai-token' : `${resolveBackofficeBaseUrl()}/api/ai/v2/token`;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      const resp = await fetch(url, {
        method: 'GET',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        signal: AbortSignal.timeout(10000),
      });

      if (!resp.ok) {
        // 401/403 means not authenticated - this is fine, user is anonymous
        if (resp.status === 401 || resp.status === 403) {
          cachedToken = null;
          tokenExpiry = null;
          return null;
        }
        // Retry on 5xx errors
        if (resp.status >= 500 && attempt < maxRetries) {
          await new Promise(resolve => setTimeout(resolve, 1000 * (attempt + 1))); // Exponential backoff
          continue;
        }
        throw new Error(`Token fetch failed: ${resp.status}`);
      }

      const data = await resp.json();
      const token = data?.token;

      if (token && typeof token === 'string' && token.length > 0) {
        cachedToken = token;
        tokenExpiry = Date.now() + TOKEN_CACHE_TTL;
        return token;
      }

      return null;
    } catch (error) {
      lastError = error;
      // Retry on network errors (but not on timeout/abort)
      if (attempt < maxRetries && (error.name === 'TypeError' || error.name === 'NetworkError')) {
        await new Promise(resolve => setTimeout(resolve, 1000 * (attempt + 1))); // Exponential backoff
        continue;
      }
      // Don't retry on timeout/abort or auth errors
      break;
    }
  }

  if (lastError?.message && !lastError.message.includes('timeout') && !lastError.message.includes('aborted')) {
    console.warn('Failed to fetch AI token (user may be anonymous):', lastError.message);
  }
  cachedToken = null;
  tokenExpiry = null;
  return null;
}

/**
 * Get cached AI token (doesn't make network request)
 */
export function getCachedAiToken() {
  if (cachedToken && tokenExpiry && Date.now() < tokenExpiry) {
    return cachedToken;
  }
  return null;
}

/**
 * Clear cached token (useful on logout)
 */
export function clearAiToken() {
  cachedToken = null;
  tokenExpiry = null;
}

/**
 * Check if user is likely authenticated (has a valid cached token)
 * Note: This is a best-effort check. The actual auth check happens server-side.
 */
export function isLikelyAuthenticated() {
  return getCachedAiToken() !== null;
}
