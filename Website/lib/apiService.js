// lib/apiService.js

import { FDRS_TEMPLATE_ID } from './constants';
export { FDRS_TEMPLATE_ID } from './constants';

// Ensure this URL matches where your Flask backend is running.
// For development, it's likely http://localhost:5000
// For production, it will be your deployed Flask backend URL.
const isDevelopment = process.env.NODE_ENV === 'development';
const isBuildTime = process.env.BUILD_TIME === 'true';
const isServer = typeof window === 'undefined';

// Set API URL based on environment
const PUBLIC_API_URL = process.env.NEXT_PUBLIC_API_URL;
const INTERNAL_API_URL = process.env.NEXT_INTERNAL_API_URL || process.env.INTERNAL_API_URL;

let API_BASE_URL;
if (isServer) {
  // When running server-side (SSR/build): inside Docker use backoffice:5000; locally use localhost.
  // Prefer INTERNAL_API_URL (e.g. in Docker) or PUBLIC_API_URL; otherwise dev = localhost so SSR works without Docker.
  API_BASE_URL = INTERNAL_API_URL
    || PUBLIC_API_URL
    || (isDevelopment ? 'http://localhost:5000' : 'https://backoffice-databank.fly.dev');
} else {
  // Client-side in browser: use public URL, or localhost in dev if none set
  if (isDevelopment && !PUBLIC_API_URL) {
    API_BASE_URL = 'http://localhost:5000';
  } else {
    API_BASE_URL = PUBLIC_API_URL || 'https://backoffice-databank.fly.dev';
  }
}

const API_KEY = process.env.NEXT_PUBLIC_API_KEY || 'databank2026';

/** Build Authorization header value for /api/v1 (Backoffice expects "Bearer <key>"). */
function getBearerAuthHeader() {
  if (!API_KEY || typeof API_KEY !== 'string') return null;
  const key = API_KEY.replace(/^Bearer\s+/i, '').trim();
  return key ? `Bearer ${key}` : null;
}

/**
 * Single entry point for all Backoffice /api/v1/* URLs.
 * In the browser returns same-origin proxy URL (avoids CORS); on server returns direct Backoffice URL.
 * All Backoffice endpoints (periods, indicator-bank, form-items, data/tables, etc.) should use this.
 * @param {string} path - Path after /api/v1/ (e.g. 'periods', 'indicator-bank', 'data/tables', 'form-items').
 * @param {Object} [params] - Query params as object (e.g. { template_id: 21, per_page: 1000 }).
 * @returns {string} URL to fetch (proxy in browser, direct on server).
 */
export function getBackofficeApiUrl(path, params = {}) {
  const pathClean = (path || '').replace(/^\/+/, '').replace(/\/+$/, '');
  const query = Object.keys(params).length
    ? new URLSearchParams(params).toString()
    : '';
  const suffix = query ? `?${query}` : '';
  if (!isServer && typeof window !== 'undefined' && window.location) {
    return `${window.location.origin}/api/backoffice/${pathClean}${suffix}`;
  }
  const base = (API_BASE_URL || '').replace(/\/$/, '');
  return `${base}/api/v1/${pathClean}${suffix}`;
}

// Lightweight in-flight deduper + TTL cache for GET JSON endpoints
const __inflightRequests = new Map(); // key -> Promise
const __responseCache = new Map(); // key -> { ts, data }

function __normalizeUrlKey(url) {
  try { return new URL(url).toString(); } catch (_e) { return String(url); }
}

function __resolveUrl(url) {
  // If it's already an absolute URL, return it
  try {
    const urlObj = new URL(url);
    return urlObj.toString();
  } catch (_e) {
    // If it's a relative URL, make it absolute using API_BASE_URL
    if (!API_BASE_URL) {
      console.error('API_BASE_URL is not defined. Cannot resolve URL:', url);
      throw new Error('API_BASE_URL is not configured');
    }

    // Ensure API_BASE_URL doesn't end with a slash
    const baseUrl = API_BASE_URL.endsWith('/') ? API_BASE_URL.slice(0, -1) : API_BASE_URL;

    // If it's a relative URL, make it absolute using API_BASE_URL
    if (url.startsWith('/')) {
      return `${baseUrl}${url}`;
    }
    // If it doesn't start with /, assume it's relative to API_BASE_URL
    return `${baseUrl}/${url}`;
  }
}

async function fetchJsonWithCache(url, { ttlMs = 5 * 60 * 1000, init = {} } = {}) {
  if (!url) {
    throw new Error('URL is required for fetchJsonWithCache');
  }

  const key = __normalizeUrlKey(url);
  let resolvedUrl;

  try {
    resolvedUrl = __resolveUrl(url);
    // Validate that resolvedUrl is a valid URL
    new URL(resolvedUrl);
  } catch (error) {
    console.error('Invalid URL resolution:', {
      originalUrl: url,
      resolvedUrl: resolvedUrl,
      API_BASE_URL: API_BASE_URL,
      error: error.message,
      isServer: isServer
    });
    throw new Error(`Invalid URL: ${url}. ${error.message}`);
  }

  // Memory cache hit
  const cached = __responseCache.get(key);
  if (cached && (Date.now() - cached.ts) < ttlMs) {
    return cached.data;
  }

  // Deduplicate concurrent identical requests
  if (__inflightRequests.has(key)) {
    return __inflightRequests.get(key);
  }

  const p = (async () => {
    try {
      // Validate URL before attempting fetch
      let finalUrl;
      try {
        finalUrl = new URL(resolvedUrl);
      } catch (urlError) {
        throw new Error(`Invalid URL format: ${resolvedUrl}. Original URL: ${url}. Error: ${urlError.message}`);
      }

      // Only attempt fetch if we have a valid HTTP/HTTPS URL
      if (!finalUrl.protocol.startsWith('http')) {
        throw new Error(`Invalid protocol for fetch: ${finalUrl.protocol}. URL: ${resolvedUrl}`);
      }

      // In browser, rewrite Backoffice /api/v1/* to same-origin proxy (avoids CORS for form-items, data/tables, etc.)
      let fetchUrl = resolvedUrl;
      if (!isServer && typeof window !== 'undefined' && window.location && resolvedUrl.includes('/api/v1/')) {
        try {
          const u = new URL(resolvedUrl);
          const pathAfterV1 = u.pathname.replace(/^\/api\/v1\/?/, '') || '';
          fetchUrl = `${window.location.origin}/api/backoffice/${pathAfterV1}${u.search}`;
        } catch (_) {}
      }

      // Check if fetch is available (should be available in both browser and Node 18+)
      if (typeof fetch === 'undefined') {
        throw new Error('Fetch API is not available in this environment');
      }

      // Create abort controller for timeout if needed (server-side)
      let abortController = null;
      let timeoutId = null;
      if (isServer && typeof AbortController !== 'undefined' && !init.signal) {
        abortController = new AbortController();
        timeoutId = setTimeout(() => abortController.abort(), 30000); // 30 second timeout
      }

      const initHeaders = (init && init.headers) ? init.headers : {};
      const bearer = getBearerAuthHeader();
      const mergedHeaders = {
        ...initHeaders,
        // /api/v1 endpoints require Authorization: Bearer <key> (proxy URL does not)
        ...(fetchUrl.includes('/api/v1/') && bearer
          ? { 'Authorization': bearer }
          : {}),
      };

      const resp = await fetch(fetchUrl, {
        ...init,
        headers: mergedHeaders,
        signal: abortController ? abortController.signal : init.signal
      }).catch((fetchError) => {
        // Clear timeout if it was set
        if (timeoutId) {
          clearTimeout(timeoutId);
        }
        // Detailed log for terminal/console (Failed to fetch / CORS / connection refused)
        const detail = {
          message: fetchError.message,
          name: fetchError.name,
          url: fetchUrl,
          originalUrl: url,
          API_BASE_URL,
          sentAuth: !!mergedHeaders.Authorization,
          authPrefix: mergedHeaders.Authorization ? (mergedHeaders.Authorization.startsWith('Bearer ') ? 'Bearer' : 'other') : 'none',
          isServer,
          stack: fetchError.stack
        };
        console.error('[apiService] FETCH FAILED (network/CORS/connection):', JSON.stringify(detail, null, 2));
        if (fetchError.name === 'TypeError' && fetchError.message === 'Failed to fetch') {
          throw new Error(
            `Network error: Failed to fetch from ${resolvedUrl}. ` +
            `This could be due to: 1) Backoffice not running at ${API_BASE_URL}, ` +
            `2) CORS issues, 3) Network connectivity problems, or 4) Invalid URL. ` +
            `Original URL: ${url}`
          );
        }
        throw fetchError;
      });

      // Clear timeout on successful response
      if (timeoutId) {
        clearTimeout(timeoutId);
      }

      if (!resp.ok) {
        const txt = await resp.text().catch(() => '');
        console.error('[apiService] HTTP error:', resp.status, resp.statusText, 'URL:', resolvedUrl, 'Body:', txt?.slice(0, 500));
        throw new Error(`HTTP ${resp.status} ${resp.statusText} ${txt}`.trim());
      }
      const data = await resp.json();
      __responseCache.set(key, { ts: Date.now(), data });
      return data;
    } catch (error) {
      // Detailed log for terminal/console
      const detail = {
        originalUrl: url,
        resolvedUrl: resolvedUrl,
        key: key,
        errorMessage: error.message,
        errorName: error.name,
        errorStack: error.stack,
        isServer,
        API_BASE_URL,
        hasWindow: typeof window !== 'undefined',
        hasFetch: typeof fetch !== 'undefined'
      };
      console.error('[apiService] Fetch error (full detail):', JSON.stringify(detail, null, 2));
      throw error;
    } finally {
      __inflightRequests.delete(key);
    }
  })();

  __inflightRequests.set(key, p);
  return p;
}

// Utility function to validate API configuration
function validateApiConfig() {
  console.log('=== API Configuration ===');
  console.log('Environment:', process.env.NODE_ENV);
  console.log('API_BASE_URL:', API_BASE_URL);
  console.log('API_KEY set:', !!API_KEY);
  console.log('Current protocol:', window?.location?.protocol || 'unknown');
  console.log('Mixed content risk:', window?.location?.protocol === 'https:' && API_BASE_URL.startsWith('http:'));

  if (window?.location?.protocol === 'https:' && API_BASE_URL.startsWith('http:')) {
    console.warn('⚠️  MIXED CONTENT WARNING: HTTPS page trying to load HTTP resources');
    console.warn('This will cause security warnings and may block API calls');
  }

  console.log('========================');
}

// Log configuration on module load
if (typeof window !== 'undefined') {
  validateApiConfig();
}

/**
 * Retry utility function for API calls
 * @param {Function} fn - Function to retry
 * @param {number} maxRetries - Maximum number of retries
 * @param {number} delay - Delay between retries in milliseconds
 * @returns {Promise} - Promise that resolves with the function result
 */
async function retryApiCall(fn, maxRetries = 3, delay = 1000) {
  let lastError;

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;
      console.warn(`API call attempt ${attempt} failed:`, error.message);

      // Don't retry on certain error types
      if (error.name === 'AbortError' || error.message.includes('404')) {
        throw error;
      }

      // If this is the last attempt, throw the error
      if (attempt === maxRetries) {
        throw error;
      }

      // Wait before retrying
      await new Promise(resolve => setTimeout(resolve, delay * attempt));
    }
  }

  throw lastError;
}

/**
 * Test API connectivity to help debug connection issues
 * @returns {Promise<Object>} Test result with status and details
 */
export async function testApiConnectivity() {
  console.log('🧪 Testing API connectivity...');

  const testResult = {
    success: false,
    apiUrl: API_BASE_URL,
    environment: process.env.NODE_ENV,
    timestamp: new Date().toISOString(),
    details: {}
  };

  try {
    // Test 1: Basic connectivity to the API base
    console.log('Testing basic connectivity to:', API_BASE_URL);
    // Use /data/tables endpoint for connectivity test
    const testUrl = buildDataTablesApiUrl({
      templateId: FDRS_TEMPLATE_ID,
      perPage: 1,
      related: 'page'
    });
    const baseResponse = await fetch(testUrl, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      },
      signal: AbortSignal.timeout(10000), // 10 second timeout for test
    });

    testResult.details.baseConnectivity = {
      status: baseResponse.status,
      statusText: baseResponse.statusText,
      ok: baseResponse.ok
    };

    if (baseResponse.ok) {
      const data = await baseResponse.json();
      testResult.details.dataReceived = {
        hasData: !!data.data,
        dataLength: data.data ? data.data.length : 0,
        totalRecords: data.total_items || data.total_records || 'unknown'
      };
      testResult.success = true;
      console.log('✅ API connectivity test passed!');
    } else {
      console.log('❌ API connectivity test failed with status:', baseResponse.status);
    }

  } catch (error) {
    console.error('❌ API connectivity test failed with error:', error);
    testResult.details.error = {
      name: error.name,
      message: error.message,
      type: error.constructor.name
    };

    // Provide specific guidance based on error type
    if (error.name === 'TypeError' && error.message.includes('Failed to fetch')) {
      console.error('🔍 Network error detected. Possible causes:');
      console.error('1. Backoffice server not running at', API_BASE_URL);
      console.error('2. CORS issues - backend needs to allow frontend origin');
      console.error('3. Network connectivity problems');
      console.error('4. Firewall blocking the connection');
    } else if (error.name === 'AbortError') {
      console.error('⏰ Request timed out. Backoffice might be slow or unresponsive.');
    }
  }

  console.log('📊 API connectivity test result:', testResult);
  return testResult;
}

/**
 * @deprecated Use buildDataTablesApiUrl() instead. This function builds /data URLs which will be deprecated.
 * The /data endpoint will be removed in favor of /data/tables which includes related form_items and countries.
 *
 * Migration: Replace buildDataApiUrl() calls with buildDataTablesApiUrl()
 * Note: /data/tables uses country_id instead of country_iso3/iso2 directly
 */
function buildDataApiUrl({ perPage = null, periodName = null, indicatorBankId = null, countryIso2 = null, countryIso3 = null } = {}) {
  if (process.env.NODE_ENV !== 'production') {
    console.warn('⚠️ buildDataApiUrl() is deprecated. Use buildDataTablesApiUrl() instead.');
  }
  let url = `${API_BASE_URL}/api/v1/data?template_id=${FDRS_TEMPLATE_ID}&disagg=true`;
  if (perPage != null) {
    url += `&per_page=${perPage}`;
  }
  if (periodName) {
    url += `&period_name=${encodeURIComponent(periodName)}`;
  }
  if (indicatorBankId) {
    url += `&indicator_bank_id=${encodeURIComponent(indicatorBankId)}`;
  }
  // Backoffice supports country filters; prefer iso3 when available
  if (countryIso3) {
    url += `&country_iso3=${encodeURIComponent(countryIso3)}`;
  } else if (countryIso2) {
    url += `&country_iso2=${encodeURIComponent(countryIso2)}`;
  }
  return url;
}

/**
 * Fetches a list of resources from the backend API.
 * @param {number} page - The page number for pagination.
 * @param {number} perPage - The number of items per page.
 * @param {string} searchQuery - Optional search query for filtering by title.
 * @param {string} resourceType - Optional resource type filter ('publication', 'other').
 * @param {string} language - Optional language code for translations (default: 'en').
 * @returns {Promise<Object>} A promise that resolves to the API response (resources, pagination info).
 * @throws {Error} If the network response is not ok.
 */
export async function getResources(page = 1, perPage = 9, searchQuery = '', resourceType = '', language = 'en') {
  // Try to use local data store first (via API route)
  const USE_LOCAL_STORE = process.env.NEXT_PUBLIC_USE_LOCAL_STORE !== 'false';
  const FORCE_API = process.env.NEXT_PUBLIC_FORCE_API === 'true';

  if (USE_LOCAL_STORE && !FORCE_API) {
    try {
      // Use API route (which uses stored data or returns empty gracefully)
      const params = new URLSearchParams();
      params.append('page', page.toString());
      params.append('per_page', perPage.toString());
      if (searchQuery) params.append('search', searchQuery);
      if (resourceType) params.append('resource_type', resourceType);
      if (language) params.append('language', language);

      const response = await fetch(`/api/resources?${params.toString()}`);
      if (response.ok) {
        const data = await response.json();
        // Return empty state gracefully if no resources available
        return data;
      }
    } catch (error) {
      console.warn('Failed to get resources from API route, falling back to direct API:', error);
    }
  }

  // Fallback to direct API call
  let url = `${API_BASE_URL}/api/v1/resources?page=${page}&per_page=${perPage}`;
  if (searchQuery) {
    url += `&search=${encodeURIComponent(searchQuery)}`;
  }
  if (resourceType) {
    url += `&resource_type=${encodeURIComponent(resourceType)}`;
  }
  if (language) {
    url += `&language=${encodeURIComponent(language)}`;
  }
  console.log(`Fetching resources from: ${url}`); // For debugging

  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      },
      signal: AbortSignal.timeout(30000), // 30 second timeout
    });

    if (!response.ok) {
      console.error('API Error (getResources):', response.status, response.statusText);
      const errorText = await response.text();
      console.error('Error response body:', errorText);
      throw new Error(`Failed to fetch resources: ${response.status} ${response.statusText}`);
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Error in getResources:', error);

    // Check if it's a network/connection error - return empty state instead of throwing
    if (error.name === 'TypeError' && error.message.includes('Failed to fetch')) {
      console.warn('Network error detected in getResources. Returning empty state.');
      // Return empty state instead of throwing error
      return {
        resources: [],
        total: 0,
        page: page,
        per_page: perPage,
        total_pages: 0,
        current_page: page
      };
    }

    throw error; // Re-throw other errors for the calling component to handle
  }
}

/**
 * Fetches people reached data with optional filtering for disaggregation analysis.
 * @param {Object} filterParams - Filter parameters object.
 * @param {Array} filterParams.countries - Array of country names/IDs to filter by.
 * @param {string} filterParams.period - Period name to filter by.
 * @param {string} filterParams.indicator - Indicator to filter by.
 * @returns {Promise<Object>} A promise that resolves to the people reached data.
 * @throws {Error} If the network response is not ok.
 */
/**
 * Builds URL for /data/tables endpoint
 * Note: /data/tables endpoint supports country_id but not country_iso2/iso3
 * Country filtering by name is handled on the frontend after fetching data
 * Using related=page instead of related=all to avoid transaction issues with large datasets
 */
/**
 * Builds URL for /data/tables endpoint with comprehensive filter support
 * Note: /data/tables endpoint uses country_id, not country_iso3/iso2 directly
 * @param {Object} options - Filter options
 * @param {number} options.templateId - Template ID (default: FDRS_TEMPLATE_ID)
 * @param {number} options.perPage - Items per page
 * @param {string} options.periodName - Period name filter
 * @param {number} options.indicatorBankId - Indicator bank ID filter
 * @param {number} options.countryId - Country ID filter (preferred over ISO codes)
 * @param {string} options.countryIso3 - Country ISO3 code filter (note: backend may not support this in /data/tables)
 * @param {string} options.countryIso2 - Country ISO2 code filter (note: backend may not support this in /data/tables)
 * @param {string} options.submissionType - Submission type filter
 * @param {boolean} options.disagg - Include disaggregation (default: true)
 * @param {string} options.related - Related tables scope: 'page' or 'all' (default: 'all')
 * @param {boolean} options.includeFullInfo - Include full info (default: false)
 * @returns {string} Complete API URL
 */
function buildDataTablesApiUrl({
  templateId = FDRS_TEMPLATE_ID,
  perPage = null,
  periodName = null,
  indicatorBankId = null,
  countryId = null,
  countryIso3 = null,
  countryIso2 = null,
  submissionType = null,
  disagg = true,
  related = 'all',
  includeFullInfo = false
} = {}) {
  const params = { template_id: String(templateId) };
  if (disagg) params.disagg = 'true';
  if (related) params.related = related;
  if (perPage != null) params.per_page = String(perPage);
  if (periodName) params.period_name = periodName;
  if (indicatorBankId) params.indicator_bank_id = String(indicatorBankId);
  if (countryId) params.country_id = String(countryId);
  if (countryIso3 && !countryId) params.country_iso3 = countryIso3;
  if (countryIso2 && !countryId) params.country_iso2 = countryIso2;
  if (submissionType) params.submission_type = submissionType;
  if (includeFullInfo) params.include_full_info = 'true';
  return getBackofficeApiUrl('data/tables', params);
}

/**
 * @deprecated Use getDataWithRelated() instead. This function uses the /data endpoint which will be removed.
 * This function is kept for backward compatibility but will be removed in a future version.
 *
 * Migration: Replace getPeopleReachedData() calls with getDataWithRelated()
 *
 * Example:
 * // Before:
 * const result = await getPeopleReachedData({ period: '2023', indicator: '123' });
 * const data = result.data || [];
 *
 * // After:
 * const data = await getDataWithRelated({
 *   template_id: FDRS_TEMPLATE_ID,
 *   period_name: '2023',
 *   indicator_bank_id: 123,
 *   disagg: true,
 *   related: 'all'
 * });
 */
export async function getPeopleReachedData(filterParams = {}) {
  if (process.env.NODE_ENV !== 'production') {
    console.warn('⚠️ getPeopleReachedData() is deprecated. Use getDataWithRelated() instead.');
  }
  let url = buildDataApiUrl();

  // Add per_page parameter - use a large number to get all data in one request
  // For disaggregation analysis, we need comprehensive data
  url += `&per_page=50000`;

  // Add filter parameters if provided
  if (filterParams.countries && filterParams.countries.length > 0) {
    // For now, we'll handle country filtering on the frontend since the API uses country_id
    // In the future, the backend could be enhanced to support country name filtering
  }
  if (filterParams.period) {
    url = buildDataApiUrl({ periodName: filterParams.period });
  }
  if (filterParams.indicator) {
    url = buildDataApiUrl({ periodName: filterParams.period || null, indicatorBankId: filterParams.indicator });
  }

  // Console logging removed for performance in production
  // console.log(`Fetching people reached data from: ${url}`);

  let firstPageData = null;
  let allData = [];

  try {
    // First, fetch the first page to check pagination
    const firstPageUrl = url + `&page=1`;
    const response = await fetch(firstPageUrl, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      },
      signal: AbortSignal.timeout(90000), // 90 second timeout for large data fetches
    });

    if (!response.ok) {
      console.error('API Error (getPeopleReachedData):', response.status, response.statusText);
      const errorText = await response.text();
      console.error('Error response body:', errorText);
      throw new Error(`Failed to fetch people reached data: ${response.status} ${response.statusText}`);
    }

    firstPageData = await response.json();
    allData = firstPageData.data || [];
    const totalItems = firstPageData.total_items || 0;
    const totalPages = firstPageData.total_pages || 1;
    const perPage = firstPageData.per_page || 50000;

    // Console logging removed for performance - uncomment if debugging needed
    // console.log(`📊 Data pagination: ${totalItems} total items, ${totalPages} pages, ${perPage} per page`);

    // If there are more pages, fetch them in batches to avoid overwhelming the server
    if (totalPages > 1) {
      // console.log(`📊 Fetching additional pages (2-${totalPages}) in batches...`);
      const BATCH_SIZE = 5; // Fetch 5 pages at a time
      const failedPages = [];

      // Helper function to fetch a single page with retry
      const fetchPageWithRetry = async (pageNum, retries = 2) => {
        for (let attempt = 0; attempt <= retries; attempt++) {
          try {
            const pageUrl = url + `&page=${pageNum}`;
            const res = await fetch(pageUrl, {
              method: 'GET',
              headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
              },
              signal: AbortSignal.timeout(90000), // 90 second timeout per page
            });

            if (!res.ok) {
              throw new Error(`HTTP ${res.status}: ${res.statusText}`);
            }

            const pageData = await res.json();
            return { success: true, page: pageNum, data: pageData };
          } catch (error) {
            if (attempt === retries) {
              console.warn(`⚠️ Failed to fetch page ${pageNum} after ${retries + 1} attempts:`, error.message);
              return { success: false, page: pageNum, error: error.message };
            }
            // Wait before retrying (exponential backoff)
            await new Promise(resolve => setTimeout(resolve, 1000 * (attempt + 1)));
          }
        }
      };

      // Fetch pages in batches
      for (let batchStart = 2; batchStart <= totalPages; batchStart += BATCH_SIZE) {
        const batchEnd = Math.min(batchStart + BATCH_SIZE - 1, totalPages);
        // console.log(`📊 Fetching pages ${batchStart}-${batchEnd}...`);

        const batchPromises = [];
        for (let page = batchStart; page <= batchEnd; page++) {
          batchPromises.push(fetchPageWithRetry(page));
        }

        const batchResults = await Promise.allSettled(batchPromises);

        batchResults.forEach((result, index) => {
          if (result.status === 'fulfilled' && result.value.success) {
            const pageData = result.value.data;
            if (pageData.data && Array.isArray(pageData.data)) {
              allData = allData.concat(pageData.data);
            }
          } else {
            const pageNum = batchStart + index;
            failedPages.push(pageNum);
            if (result.status === 'fulfilled' && result.value) {
              console.warn(`⚠️ Page ${pageNum} failed:`, result.value.error);
            } else {
              console.warn(`⚠️ Page ${pageNum} failed:`, result.reason?.message || 'Unknown error');
            }
          }
        });

        // Small delay between batches to avoid overwhelming the server
        if (batchEnd < totalPages) {
          await new Promise(resolve => setTimeout(resolve, 200));
        }
      }

      if (failedPages.length > 0) {
        console.warn(`⚠️ Failed to fetch ${failedPages.length} pages: ${failedPages.join(', ')}`);
        console.warn(`📊 Continuing with ${allData.length} records from ${totalPages - failedPages.length} successful pages`);
      } else {
        // console.log(`📊 Successfully fetched ${allData.length} total records across ${totalPages} pages`);
      }
    }

    const data = {
      ...firstPageData,
      data: allData
    };

    // Hydrate missing legacy fields for downstream consumers - optimized
    // Backoffice API already includes country_info, so we only need to check and set answer_value alias
    if (Array.isArray(data.data) && data.data.length > 0) {
      // Fast path: just set answer_value alias if missing - use for loop for better performance
      for (let i = 0; i < data.data.length; i++) {
        const item = data.data[i];
        // Provide backward-compatibility alias - only set if missing
        if (item?.answer_value == null && item?.value != null) {
          item.answer_value = item.value;
        }
      }

      // Only hydrate country_info if really needed (should rarely be the case since API includes it)
      // Skip this expensive operation if not needed
      let needsCountryHydration = false;
      const sampleSize = Math.min(5, data.data.length);
      for (let i = 0; i < sampleSize; i++) {
        if (!data.data[i]?.country_info && (data.data[i]?.iso2 || data.data[i]?.iso3)) {
          needsCountryHydration = true;
          break;
        }
      }

      if (needsCountryHydration) {
        try {
          const countries = await getCountriesList();
          const byIso2 = new Map(countries.map(c => [String(c.iso2 || '').toUpperCase(), c]));
          const byIso3 = new Map(countries.map(c => [String(c.iso3 || '').toUpperCase(), c]));

          // Batch hydrate only items that need it
          for (let i = 0; i < data.data.length; i++) {
            const item = data.data[i];
            if (!item?.country_info) {
              const iso2 = String(item?.iso2 || '').toUpperCase();
              const iso3 = String(item?.iso3 || '').toUpperCase();
              const country = byIso2.get(iso2) || byIso3.get(iso3) || null;
              if (country) {
                item.country_info = country;
              }
            }
          }
        } catch (_e) {
          // Non-fatal hydration failure - API already provides country_info anyway
        }
      }
    }

    // Filter by countries on the frontend if needed
    if (filterParams.countries && filterParams.countries.length > 0 && data.data) {
      data.data = data.data.filter(item => {
        // Try by hydrated country_info name, else try mapping from iso codes
        if (item?.country_info?.name) {
          return filterParams.countries.includes(item.country_info.name);
        }
        return false;
      });
    }

    return data;
  } catch (error) {
    console.error('Error in getPeopleReachedData:', error);

    // Check if it's a timeout error
    if (error.name === 'TimeoutError' || error.message.includes('timeout')) {
      console.error('Timeout error detected in getPeopleReachedData. This could be due to:');
      console.error('1. Large dataset taking longer than expected');
      console.error('2. Slow backend server response');
      console.error('3. Network connectivity issues');
      console.error('4. Consider applying filters to reduce data size');
      console.error('Current API_BASE_URL:', API_BASE_URL);
      console.error('Current environment:', process.env.NODE_ENV);

      // If we have partial data, return it instead of throwing
      if (firstPageData && allData && allData.length > 0) {
        console.warn('⚠️ Returning partial data due to timeout');
        return {
          ...firstPageData,
          data: allData,
          _partial: true,
          _error: 'Timeout occurred, but partial data is available'
        };
      }
    }

    // Check if it's a network/connection error
    if (error.name === 'TypeError' && error.message.includes('Failed to fetch')) {
      console.error('Network error detected in getPeopleReachedData. This could be due to:');
      console.error('1. Backoffice server not running');
      console.error('2. Incorrect API URL');
      console.error('3. CORS issues');
      console.error('4. Network connectivity problems');
      console.error('Current API_BASE_URL:', API_BASE_URL);
      console.error('Current environment:', process.env.NODE_ENV);
    }

    throw error; // Re-throw the error for the calling component to handle
  }
}

/**
 * Internal function that actually calls /data/tables endpoint
 */
async function getPeopleReachedDataFromTablesInternal(filterParams = {}) {
  let url = buildDataTablesApiUrl();

  // Add per_page parameter - use a large number to get all data in one request
  // For disaggregation analysis, we need comprehensive data
  url += `&per_page=50000`;

  // Add filter parameters if provided
  if (filterParams.period) {
    url = buildDataTablesApiUrl({ periodName: filterParams.period });
  }
  if (filterParams.indicator) {
    url = buildDataTablesApiUrl({ periodName: filterParams.period || null, indicatorBankId: filterParams.indicator });
  }

  let firstPageData = null;
  let allData = [];
  let allFormItems = [];
  let allCountries = [];

  try {
    // First, fetch the first page to check pagination
    const firstPageUrl = url + `&page=1`;
    const response = await fetch(firstPageUrl, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      },
      signal: AbortSignal.timeout(90000), // 90 second timeout for large data fetches
    });

    if (!response.ok) {
      console.error('API Error (getPeopleReachedDataFromTables):', response.status, response.statusText);
      const errorText = await response.text();
      console.error('Error response body:', errorText);
      throw new Error(`Failed to fetch people reached data: ${response.status} ${response.statusText}`);
    }

    firstPageData = await response.json();
    allData = firstPageData.data || [];
    allFormItems = firstPageData.form_items || [];
    allCountries = firstPageData.countries || [];
    const totalItems = firstPageData.total_items || 0;
    const totalPages = firstPageData.total_pages || 1;
    const perPage = firstPageData.per_page || 50000;

    // If there are more pages, fetch them in batches
    if (totalPages > 1) {
      const BATCH_SIZE = 5; // Fetch 5 pages at a time
      const failedPages = [];

      // Helper function to fetch a single page with retry
      const fetchPageWithRetry = async (pageNum, retries = 2) => {
        for (let attempt = 0; attempt <= retries; attempt++) {
          try {
            const pageUrl = url + `&page=${pageNum}`;
            const res = await fetch(pageUrl, {
              method: 'GET',
              headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
              },
              signal: AbortSignal.timeout(90000), // 90 second timeout per page
            });

            if (!res.ok) {
              throw new Error(`HTTP ${res.status}: ${res.statusText}`);
            }

            const pageData = await res.json();
            return { success: true, page: pageNum, data: pageData };
          } catch (error) {
            if (attempt === retries) {
              console.warn(`⚠️ Failed to fetch page ${pageNum} after ${retries + 1} attempts:`, error.message);
              return { success: false, page: pageNum, error: error.message };
            }
            // Wait before retrying (exponential backoff)
            await new Promise(resolve => setTimeout(resolve, 1000 * (attempt + 1)));
          }
        }
      };

      // Fetch pages in batches
      for (let batchStart = 2; batchStart <= totalPages; batchStart += BATCH_SIZE) {
        const batchEnd = Math.min(batchStart + BATCH_SIZE - 1, totalPages);

        const batchPromises = [];
        for (let page = batchStart; page <= batchEnd; page++) {
          batchPromises.push(fetchPageWithRetry(page));
        }

        const batchResults = await Promise.allSettled(batchPromises);

        batchResults.forEach((result, index) => {
          if (result.status === 'fulfilled' && result.value.success) {
            const pageData = result.value.data;
            if (pageData.data && Array.isArray(pageData.data)) {
              allData = allData.concat(pageData.data);
            }
            // Merge form_items and countries (avoid duplicates)
            if (pageData.form_items && Array.isArray(pageData.form_items)) {
              const existingFormItemIds = new Set(allFormItems.map(fi => fi.item_id || fi.id));
              pageData.form_items.forEach(fi => {
                const fiId = fi.item_id || fi.id;
                if (fiId && !existingFormItemIds.has(fiId)) {
                  allFormItems.push(fi);
                  existingFormItemIds.add(fiId);
                }
              });
            }
            if (pageData.countries && Array.isArray(pageData.countries)) {
              const existingCountryIds = new Set(allCountries.map(c => c.id || c.country_id));
              pageData.countries.forEach(c => {
                const cId = c.id || c.country_id;
                if (cId && !existingCountryIds.has(cId)) {
                  allCountries.push(c);
                  existingCountryIds.add(cId);
                }
              });
            }
          } else {
            const pageNum = batchStart + index;
            failedPages.push(pageNum);
            if (result.status === 'fulfilled' && result.value) {
              console.warn(`⚠️ Page ${pageNum} failed:`, result.value.error);
            } else {
              console.warn(`⚠️ Page ${pageNum} failed:`, result.reason?.message || 'Unknown error');
            }
          }
        });

        // Small delay between batches to avoid overwhelming the server
        if (batchEnd < totalPages) {
          await new Promise(resolve => setTimeout(resolve, 200));
        }
      }

      if (failedPages.length > 0) {
        console.warn(`⚠️ Failed to fetch ${failedPages.length} pages: ${failedPages.join(', ')}`);
        console.warn(`📊 Continuing with ${allData.length} records from ${totalPages - failedPages.length} successful pages`);
      }
    }

    // Create lookup maps for efficient hydration
    const formItemMap = new Map();
    allFormItems.forEach(fi => {
      const fiId = fi.item_id || fi.id;
      if (fiId) {
        formItemMap.set(fiId, fi);
      }
    });

    const countryMap = new Map();
    allCountries.forEach(c => {
      const cId = c.id || c.country_id;
      if (cId) {
        countryMap.set(cId, c);
      }
    });

    // Hydrate data items with form_item_info and country_info
    for (let i = 0; i < allData.length; i++) {
      const item = allData[i];

      // Hydrate form_item_info
      if (item.form_item_id && !item.form_item_info) {
        const formItem = formItemMap.get(item.form_item_id);
        if (formItem) {
          item.form_item_info = formItem;
        }
      }

      // Hydrate country_info
      if (item.country_id && !item.country_info) {
        const country = countryMap.get(item.country_id);
        if (country) {
          item.country_info = country;
        }
      }

      // Provide backward-compatibility alias
      if (item?.answer_value == null && item?.value != null) {
        item.answer_value = item.value;
      }
    }

    // Filter by countries on the frontend if needed
    if (filterParams.countries && filterParams.countries.length > 0 && allData) {
      allData = allData.filter(item => {
        // Try by hydrated country_info name
        if (item?.country_info?.name) {
          return filterParams.countries.includes(item.country_info.name);
        }
        return false;
      });
    }

    const data = {
      ...firstPageData,
      data: allData
    };

    return data;
  } catch (error) {
    console.error('Error in getPeopleReachedDataFromTablesInternal:', error);

    // Check if it's a timeout error
    if (error.name === 'TimeoutError' || error.message.includes('timeout')) {
      console.error('Timeout error detected in getPeopleReachedDataFromTablesInternal. This could be due to:');
      console.error('1. Large dataset taking longer than expected');
      console.error('2. Slow backend server response');
      console.error('3. Network connectivity issues');
      console.error('4. Consider applying filters to reduce data size');
      console.error('Current API_BASE_URL:', API_BASE_URL);
      console.error('Current environment:', process.env.NODE_ENV);

      // If we have partial data, return it instead of throwing
      if (firstPageData && allData && allData.length > 0) {
        console.warn('⚠️ Returning partial data due to timeout');
        return {
          ...firstPageData,
          data: allData,
          _partial: true,
          _error: 'Timeout occurred, but partial data is available'
        };
      }
    }

    // Check if it's a network/connection error
    if (error.name === 'TypeError' && error.message.includes('Failed to fetch')) {
      console.error('Network error detected in getPeopleReachedDataFromTablesInternal. This could be due to:');
      console.error('1. Backoffice server not running');
      console.error('2. Incorrect API URL');
      console.error('3. CORS issues');
      console.error('4. Network connectivity problems');
      console.error('Current API_BASE_URL:', API_BASE_URL);
      console.error('Current environment:', process.env.NODE_ENV);
    }

    throw error; // Re-throw the error for the calling component to handle
  }
}

/**
 * @deprecated Use getDataWithRelated() instead. This function will be removed in a future version.
 *
 * Migration: Replace getPeopleReachedDataFromTables() calls with getDataWithRelated()
 *
 * Example:
 * // Before:
 * const result = await getPeopleReachedDataFromTables({ period: '2023', indicator: '123' });
 * const data = result.data || [];
 *
 * // After:
 * const data = await getDataWithRelated({
 *   template_id: FDRS_TEMPLATE_ID,
 *   period_name: '2023',
 *   indicator_bank_id: 123,
 *   disagg: true,
 *   related: 'all'
 * });
 *
 * Fetches people reached data using the /data/tables endpoint which includes
 * related form_items and countries tables for better performance.
 * Falls back to /data endpoint if /data/tables fails.
 * @param {Object} filterParams - Filter parameters (countries, period, indicator)
 * @returns {Promise<Object>} A promise that resolves to the data with hydrated country_info and form_item_info
 */
export async function getPeopleReachedDataFromTables(filterParams = {}) {
  if (process.env.NODE_ENV !== 'production') {
    console.warn('⚠️ getPeopleReachedDataFromTables() is deprecated. Use getDataWithRelated() instead.');
  }
  // Try /data/tables first, fall back to /data if it fails
  try {
    return await getPeopleReachedDataFromTablesInternal(filterParams);
  } catch (error) {
    // If /data/tables fails (e.g., transaction errors), fall back to original endpoint
    if (error.message && (error.message.includes('500') || error.message.includes('transaction'))) {
      console.warn('⚠️ /data/tables endpoint failed, falling back to /data endpoint:', error.message);
      return await getPeopleReachedData(filterParams);
    }
    throw error;
  }
}

/**
 * Unified data fetching function that uses local data store when available,
 * falls back to direct API calls when store is unavailable or disabled.
 * This function standardizes on the /data/tables endpoint and returns
 * data along with related form_items and countries tables.
 *
 * @param {Object} filters - Filter parameters
 * @param {string} filters.country_iso3 - Country ISO3 code
 * @param {string} filters.country_iso2 - Country ISO2 code
 * @param {string} filters.period_name - Period name
 * @param {number} filters.indicator_bank_id - Indicator bank ID
 * @param {number} filters.template_id - Template ID (defaults to FDRS_TEMPLATE_ID)
 * @param {string} filters.submission_type - Submission type
 * @param {boolean} filters.include_full_info - Include full info (default: false)
 * @param {string} filters.related - Related data level: 'page', 'all', or undefined (default: 'all')
 * @param {number} filters.per_page - Items per page (default: 100000 for comprehensive datasets)
 * @param {boolean} filters.disagg - Include disaggregation data (default: true)
 * @param {boolean} filters.returnFullResponse - If true, returns full response object with form_items and countries (default: false for backward compatibility)
 * @returns {Promise<Array|Object>}
 *   - If returnFullResponse=false: Returns array of data records (backward compatible)
 *   - If returnFullResponse=true: Returns { data: [], form_items: [], countries: [], total_items, ... }
 */
export async function getDataWithRelated(filters = {}) {
  const USE_LOCAL_STORE = process.env.NEXT_PUBLIC_USE_LOCAL_STORE !== 'false';
  const FORCE_API = process.env.NEXT_PUBLIC_FORCE_API === 'true';
  const returnFullResponse = filters.returnFullResponse === true;

  // Use local store if enabled and not forcing API
  if (USE_LOCAL_STORE && !FORCE_API) {
    // Server-side: use data store directly
    if (isServer) {
      try {
        // Dynamic import to avoid issues if dataStore is not available
        const { getDataFromStore, getFormItemsFromStore, getCountriesFromStore } = await import('./dataStore');
        const data = await getDataFromStore(filters);

        // If full response requested, include related tables
        if (returnFullResponse) {
          const formItems = await getFormItemsFromStore(filters);
          const countries = await getCountriesFromStore();
          return {
            data,
            form_items: formItems,
            countries,
            total_items: data.length,
            total_pages: 1,
            current_page: 1,
            per_page: data.length
          };
        }

        return data;
      } catch (error) {
        // If local store fails, fall back to API
        console.warn('Local store error, falling back to API:', error.message);
      }
    } else {
      // Client-side: use API route (which reads from server-side store)
      try {
        const params = new URLSearchParams();
        Object.entries(filters).forEach(([key, value]) => {
          if (value !== undefined && value !== null && key !== 'returnFullResponse') {
            params.append(key, value);
          }
        });

        const response = await fetch(`/api/data?${params.toString()}`);
        if (response.ok) {
          const result = await response.json();

          // If full response requested, we need to fetch form_items and countries separately
          // (API route currently only returns data array)
          if (returnFullResponse) {
            // For now, return data with empty related tables
            // TODO: Enhance API route to return full response
            return {
              data: result.data || [],
              form_items: [],
              countries: [],
              total_items: result.count || 0,
              total_pages: 1,
              current_page: 1,
              per_page: result.count || 0
            };
          }

          return result.data || [];
        } else {
          throw new Error(`API route error: ${response.status}`);
        }
      } catch (error) {
        console.warn('API route error, falling back to direct API:', error.message);
      }
    }
  }

  // Fallback to direct API call using /data/tables endpoint
  return await getDataWithRelatedFromAPI(filters);
}

/**
 * Internal function that fetches data from API using /data/tables endpoint
 * Returns full response with data, form_items, and countries tables
 * @private
 */
async function getDataWithRelatedFromAPI(filters = {}) {
  const returnFullResponse = filters.returnFullResponse === true;

  // Build URL using the enhanced helper function
  const backofficeUrl = buildDataTablesApiUrl({
    templateId: filters.template_id || FDRS_TEMPLATE_ID,
    perPage: filters.per_page || 100000,
    periodName: filters.period_name,
    indicatorBankId: filters.indicator_bank_id,
    countryIso3: filters.country_iso3,
    countryIso2: filters.country_iso2,
    submissionType: filters.submission_type,
    disagg: filters.disagg !== false,
    related: filters.related || 'all',
    includeFullInfo: filters.include_full_info || false
  });

  // In browser, use same-origin proxy to avoid CORS (dataviz, disaggregation, etc.)
  const isClient = typeof window !== 'undefined';
  const url = isClient && typeof window !== 'undefined' && window.location
    ? `${window.location.origin}/api/data-tables?${new URL(backofficeUrl).searchParams.toString()}`
    : backofficeUrl;

  try {
    const bearer = getBearerAuthHeader();
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        ...(bearer ? { Authorization: bearer } : {}),
      },
      signal: AbortSignal.timeout(90000), // 90 second timeout
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status} ${response.statusText}`);
    }

    const result = await response.json();

    // Return full response object if requested, otherwise just data array for backward compatibility
    if (returnFullResponse) {
      return {
        data: result.data || [],
        form_items: result.form_items || [],
        countries: result.countries || [],
        total_items: result.total_items || 0,
        total_pages: result.total_pages || 1,
        current_page: result.current_page || 1,
        per_page: result.per_page || (result.data?.length || 0)
      };
    }

    // Backward compatibility: return just the data array
    return result.data || [];
  } catch (error) {
    console.error('Error fetching data from API:', error);
    throw error;
  }
}

/**
 * Fetches available filter options for the disaggregation analysis.
 * @returns {Promise<Object>} A promise that resolves to the filter options.
 * @throws {Error} If the network response is not ok.
 */
export async function getFilterOptions() {
  try {
    // Fetch countries, periods, and indicators in parallel to reduce latency
    const [countriesData, periodsData, indicatorData] = await Promise.allSettled([
      getCountriesList(),
      getAvailablePeriods(FDRS_TEMPLATE_ID),
      getIndicatorBank()
    ]);

    // Handle countries
    const countries = countriesData.status === 'fulfilled' && Array.isArray(countriesData.value)
      ? countriesData.value.map(country => ({
          name: country.name,
          iso2: country.iso2,
          iso3: country.iso3
        }))
      : [];

    // Handle periods
    const periods = periodsData.status === 'fulfilled' && Array.isArray(periodsData.value)
      ? periodsData.value.map(period => ({
          name: period,
          label: period
        }))
      : [];

    // Handle indicators
    const indicators = indicatorData.status === 'fulfilled' && indicatorData.value?.indicators
      ? indicatorData.value.indicators.map(indicator => ({
          id: indicator.id,
          name: indicator.localized_name || indicator.name,
          definition: indicator.localized_definition || indicator.definition
        }))
      : [];

    return {
      countries,
      periods,
      indicators
    };
  } catch (error) {
    console.error('Error fetching filter options:', error);
    // Return empty arrays instead of throwing - allows app to continue working
    return {
      countries: [],
      periods: [],
      indicators: []
    };
  }
}

/**
 * Processes disaggregated data for analysis and visualization.
 * @param {Array} data - Raw data array from the API.
 * @returns {Object} Processed data object with various analysis breakdowns.
 */
export function processDisaggregatedData(data) {
  if (!data || !Array.isArray(data)) {
    console.warn('processDisaggregatedData received invalid data:', data);
    return {
      totalReached: 0,
      byCountry: [],
      bySex: [],
      byAge: [],
      bySexAge: [],
      trends: [],
      byIndicator: [],
      countryDisaggregation: []
    };
  }

  console.log('Processing disaggregated data:', data.length, 'items');

  const result = {
    totalReached: 0,
    byCountry: {},
    bySex: {},
    byAge: {},
    bySexAge: {},
    trends: {},
    byIndicator: {},
    countryDisaggregation: {}
  };

  let totalReached = 0;

  // Process each data item
  data.forEach(item => {
    if (!item) return;

    // Extract answer value (support legacy answer_value and new value field)
    const av = item?.answer_value != null ? item.answer_value : item?.value;
    let numericValue = 0;
    if (av && typeof av === 'object' && av.values && av.values.total != null) {
      numericValue = parseFloat(av.values.total) || 0;
    } else if (av && typeof av === 'object' && av.total != null) {
      numericValue = parseFloat(av.total) || 0;
    } else {
      numericValue = parseFloat(av) || 0;
    }

    totalReached += numericValue;

    // Process by country
    if (item?.country_info?.name) {
      const countryName = item.country_info.name;
      if (!result.byCountry[countryName]) {
        result.byCountry[countryName] = {
          name: countryName,
          total: 0,
          items: 0
        };
      }
      result.byCountry[countryName].total += numericValue;
      result.byCountry[countryName].items += 1;
    }

    // Process disaggregation data if available
    if (item.disaggregation_data) {
      const disaggData = typeof item.disaggregation_data === 'string'
        ? JSON.parse(item.disaggregation_data)
        : item.disaggregation_data;

      // Process sex disaggregation
      if (disaggData.sex) {
        Object.entries(disaggData.sex).forEach(([sexKey, sexValue]) => {
          if (!result.bySex[sexKey]) {
            result.bySex[sexKey] = 0;
          }
          result.bySex[sexKey] += parseFloat(sexValue) || 0;
        });
      }

      // Process age disaggregation
      if (disaggData.age) {
        Object.entries(disaggData.age).forEach(([ageKey, ageValue]) => {
          if (!result.byAge[ageKey]) {
            result.byAge[ageKey] = 0;
          }
          result.byAge[ageKey] += parseFloat(ageValue) || 0;
        });
      }
    }

    // Process by indicator
    if (item.form_item_info && item.form_item_info.bank_details) {
      const indicatorId = item.form_item_info.bank_details.id;
      const indicatorName = item.form_item_info.bank_details.name;

      if (!result.byIndicator[indicatorId]) {
        result.byIndicator[indicatorId] = {
          id: indicatorId,
          name: indicatorName,
          total: 0,
          items: 0
        };
      }
      result.byIndicator[indicatorId].total += numericValue;
      result.byIndicator[indicatorId].items += 1;
    }

    // Process trends by period
    if (item.period_name) {
      if (!result.trends[item.period_name]) {
        result.trends[item.period_name] = {
          period: item.period_name,
          total: 0,
          items: 0
        };
      }
      result.trends[item.period_name].total += numericValue;
      result.trends[item.period_name].items += 1;
    }
  });

  // Convert objects to arrays for easier frontend consumption
  const processedResult = {
    totalReached,
    byCountry: Object.values(result.byCountry).sort((a, b) => b.total - a.total),
    bySex: Object.entries(result.bySex).map(([key, value]) => ({ category: key, value })),
    byAge: Object.entries(result.byAge).map(([key, value]) => ({ category: key, value })),
    bySexAge: [], // This would need more complex processing
    trends: Object.values(result.trends).sort((a, b) => a.period.localeCompare(b.period)),
    byIndicator: Object.values(result.byIndicator).sort((a, b) => b.total - a.total),
    countryDisaggregation: Object.values(result.byCountry).map(country => ({
      label: country.name,
      value: country.total,
      totalItems: country.items,
      // Add placeholder disaggregation percentages - these would need more sophisticated calculation
      sexPercentage: Math.random() * 100, // Placeholder
      agePercentage: Math.random() * 100, // Placeholder
      sexAgePercentage: Math.random() * 100, // Placeholder
      overallDisaggregation: Math.random() * 100 // Placeholder
    }))
  };

  console.log('Processed data result:', processedResult);
  return processedResult;
}

/**
 * Fetches global overview data.
 * (Placeholder - implement actual API endpoint in Flask backend)
 * @returns {Promise<Object>} A promise that resolves to the global overview data.
 */
export async function getGlobalOverviewData() {
  // const response = await fetch(`${API_BASE_URL}/api/v1/global-overview`);
  // if (!response.ok) {
  //   console.error('API Error (getGlobalOverviewData):', response.status, await response.text());
  //   throw new Error('Failed to fetch global overview data');
  // }
  // return response.json();
  console.warn("getGlobalOverviewData is using placeholder data.");
  return Promise.resolve({
    total_people_assisted: 12500000,
    active_countries_count: 75,
    total_volunteers: 200000,
    key_global_indicators: [
      { name: "Shelter Provided (Households)", value: 50000 },
      { name: "Access to Safe Water (People)", value: 2000000 }
    ],
    regional_highlights: [
      { region: "africa", people_assisted: 3000000, active_emergencies: 5 },
      { region: "americas", people_assisted: 2500000, active_emergencies: 3 },
      { region: "asia-pacific", people_assisted: 4000000, active_emergencies: 7 },
      { region: "europe-and-central-asia", people_assisted: 1500000, active_emergencies: 2 },
      { region: "mena", people_assisted: 1500000, active_emergencies: 4 },
    ]
  });
}

/**
 * Fetches a list of templates from the API or data store.
 * @returns {Promise<Array>} A promise that resolves to an array of template objects.
 */
export async function getTemplates() {
  // Try to use local data store first
  const USE_LOCAL_STORE = process.env.NEXT_PUBLIC_USE_LOCAL_STORE !== 'false';
  const FORCE_API = process.env.NEXT_PUBLIC_FORCE_API === 'true';

  if (USE_LOCAL_STORE && !FORCE_API) {
    try {
      // Server-side: use data store directly
      if (typeof window === 'undefined') {
        const { getTemplatesFromStore } = await import('./dataStore');
        const templates = await getTemplatesFromStore();
        if (Array.isArray(templates) && templates.length > 0) {
          return templates;
        }
      } else {
        // Client-side: use API route (which reads from server-side store)
        try {
          const response = await fetch('/api/templates');
          if (response.ok) {
            const data = await response.json();
            if (data.templates && Array.isArray(data.templates) && data.templates.length > 0) {
              return data.templates;
            }
          }
        } catch (error) {
          console.warn('Failed to get templates from API route, falling back to direct API:', error);
        }
      }
    } catch (error) {
      console.warn('Local store error for templates, falling back to API:', error.message);
    }
  }

  // Fallback to direct API call
  try {
    const url = `${API_BASE_URL}/api/v1/templates?per_page=1000`;
    const response = await fetch(url);
    if (response.ok) {
      const data = await response.json();
      return data.templates || [];
    }
    return [];
  } catch (error) {
    console.error('Error fetching templates:', error);
    return []; // Return empty array instead of throwing
  }
}

/**
 * Fetches NS organizational structure (branches, sub-branches, local units) for a country.
 * @param {number|string} countryId - The country ID
 * @param {number|string} [branchId] - Optional branch ID to fetch sub-branches
 * @returns {Promise<Object>} A promise that resolves to an object with branches, subbranches, and localunits arrays.
 */
export async function getNSStructure(countryId, branchId = null) {
  try {
    const params = new URLSearchParams({ country_id: String(countryId) });
    if (branchId) {
      params.set('branch_id', String(branchId));
    }

    const response = await fetch(`/api/ns-structure?${params.toString()}`);

    if (!response.ok) {
      console.warn('Failed to fetch NS structure:', response.status);
      return {
        branches: [],
        subbranches: [],
        localunits: [],
      };
    }

    const data = await response.json();
    return {
      branches: Array.isArray(data.branches) ? data.branches : [],
      subbranches: Array.isArray(data.subbranches) ? data.subbranches : [],
      localunits: Array.isArray(data.localunits) ? data.localunits : [],
    };
  } catch (error) {
    console.error('Error fetching NS structure:', error);
    return {
      branches: [],
      subbranches: [],
      localunits: [],
    };
  }
}

/**
 * Fetches a list of countries from the API.
 * @returns {Promise<Array>} A promise that resolves to an array of country objects.
 */
export async function getCountriesList(locale = null) {
  // Try to use local data store first
  const USE_LOCAL_STORE = process.env.NEXT_PUBLIC_USE_LOCAL_STORE !== 'false';
  const FORCE_API = process.env.NEXT_PUBLIC_FORCE_API === 'true';

  if (USE_LOCAL_STORE && !FORCE_API) {
    try {
      // Server-side: use data store directly
      if (typeof window === 'undefined') {
        const { getCountriesFromStore } = await import('./dataStore');
        const countries = await getCountriesFromStore();

        // Map frontend locale codes to backend language keys
        const backendLocaleMap = {
          en: 'english',
          fr: 'french',
          es: 'spanish',
          ar: 'arabic',
          zh: 'chinese',
          ru: 'russian',
          hi: 'hindi',
        };

        const backendLocaleKey = locale ? backendLocaleMap[String(locale).toLowerCase()] : null;

        // Transform to match expected format with localization
        return countries.map(country => {
          // Resolve localized country name
          let resolvedCountryName = country.name;
          if (country.multilingual_names && backendLocaleKey && country.multilingual_names[backendLocaleKey]) {
            resolvedCountryName = country.multilingual_names[backendLocaleKey] || resolvedCountryName;
          }

          // Resolve localized National Society name
          let resolvedNsName = country.national_society_name || country.name;
          if (country.multilingual_national_society_names && backendLocaleKey && country.multilingual_national_society_names[backendLocaleKey]) {
            resolvedNsName = country.multilingual_national_society_names[backendLocaleKey] || resolvedNsName;
          }

          // Resolve localized region name
          let resolvedRegion = country.region || 'Other';
          if (country.region_multilingual_names && backendLocaleKey && country.region_multilingual_names[backendLocaleKey]) {
            resolvedRegion = country.region_multilingual_names[backendLocaleKey] || resolvedRegion;
          }

          return {
            id: country.id,
            code: country.iso2,
            name: resolvedCountryName,
            region: resolvedRegion,
            region_localized: resolvedRegion,
            iso3: country.iso3,
            iso2: country.iso2,
            national_society_name: resolvedNsName,
          };
        });
      } else {
        // Client-side: use API route (which reads from server-side store)
        try {
          const url = new URL('/api/countries', window.location.origin);
          if (locale) {
            url.searchParams.set('locale', locale);
          }
          const response = await fetch(url.toString());
          if (response.ok) {
            const countries = await response.json();
            if (Array.isArray(countries) && countries.length > 0) {
              return countries;
            }
          }
        } catch (error) {
          console.warn('Failed to get countries from API route, falling back to direct API:', error);
        }
      }
    } catch (error) {
      console.warn('Local store error for countries, falling back to API:', error.message);
    }
  }

  // Fallback to direct API call (API key sent in Authorization header by fetchJsonWithCache)
  try {
    const url = new URL(`${API_BASE_URL}/api/v1/countrymap`);
    if (locale) {
      url.searchParams.set('locale', locale);
    }

    const data = await fetchJsonWithCache(url.toString(), { ttlMs: 24 * 60 * 60 * 1000 });

    // Transform the API response to match the expected format
    const backendLocaleMap = {
      en: 'english',
      fr: 'french',
      es: 'spanish',
      ar: 'arabic',
      zh: 'chinese',
      ru: 'russian',
      hi: 'hindi',
    };

    const transformedData = data.map(country => {
      const backendLocaleKey = locale ? backendLocaleMap[String(locale).toLowerCase()] : null;

      // Resolve localized country name
      let resolvedCountryName = country.localized_name || country.name;
      if (!country.localized_name && country.multilingual_names && backendLocaleKey && country.multilingual_names[backendLocaleKey]) {
        resolvedCountryName = country.multilingual_names[backendLocaleKey] || resolvedCountryName;
      }

      // Resolve localized National Society name
      let resolvedNsName = country.localized_national_society_name || country.national_society_name;
      if (!country.localized_national_society_name && country.multilingual_national_society_names && backendLocaleKey && country.multilingual_national_society_names[backendLocaleKey]) {
        resolvedNsName = country.multilingual_national_society_names[backendLocaleKey] || resolvedNsName;
      }

      // Resolve localized region name. If API gives a custom region (e.g., "Europe & CA"), preserve it.
      let resolvedRegion = country.region_localized || country.region || 'Other';
      if (!country.region_localized && country.region_multilingual_names && backendLocaleKey) {
        // region_multilingual_names uses human language keys (english/french/...) on backend; map them here
        const langKeyMap = {
          english: 'en', french: 'fr', spanish: 'es', arabic: 'ar', chinese: 'zh', russian: 'ru', hindi: 'hi'
        };
        const desiredBackendNameKey = Object.keys(langKeyMap).find(k => langKeyMap[k] === String(locale || 'en').toLowerCase());
        if (desiredBackendNameKey && country.region_multilingual_names[desiredBackendNameKey]) {
          resolvedRegion = country.region_multilingual_names[desiredBackendNameKey] || resolvedRegion;
        }
      }

      return {
        id: country.id,
        code: country.iso2,
        name: resolvedCountryName,
        region: resolvedRegion,
        region_localized: country.region_localized || resolvedRegion,
        iso3: country.iso3,
        iso2: country.iso2,
        national_society_name: resolvedNsName,
      };
    });

    return transformedData;
  } catch (error) {
    console.error('Error fetching countries:', error);
    // Return empty array instead of throwing - allows app to continue working
    // Components should handle empty countries list gracefully
    return [];
  }
}

// Lightweight caches for related-entity hydration
const formItemDetailsCache = new Map(); // form_item_id -> details
const indicatorDetailsCache = new Map(); // indicator_bank_id -> details
const formItemsMapCache = new Map(); // template_id -> Map(form_item_id -> indicator_bank_id)

/**
 * Fetch form item details by ID with caching.
 */
async function getFormItemDetailsById(itemId) {
  const key = Number(itemId);
  if (!key) return null;
  const cached = formItemDetailsCache.get(key);
  if (cached) return cached;
  const url = `${API_BASE_URL}/api/v1/form-items/${key}`;
  try {
    const details = await fetchJsonWithCache(url, { ttlMs: 6 * 60 * 60 * 1000 });
    formItemDetailsCache.set(key, details);
    return details;
  } catch (_e) {
    return null;
  }
}

/**
 * Fetch indicator bank details by ID with caching.
 */
async function getIndicatorDetailsById(indicatorId) {
  const key = Number(indicatorId);
  if (!key) return null;
  const cached = indicatorDetailsCache.get(key);
  if (cached) return cached;
  const url = `${API_BASE_URL}/api/v1/indicator-bank/${key}`;
  try {
    const details = await fetchJsonWithCache(url, { ttlMs: 6 * 60 * 60 * 1000 });
    indicatorDetailsCache.set(key, details);
    return details;
  } catch (_e) {
    return null;
  }
}

/**
 * Fetch a full map of form_item_id -> indicator_bank_id for a template in as few calls as possible.
 */
async function fetchFormItemsMapForTemplate(templateId) {
  const tid = Number(templateId);
  if (!tid) return new Map();
  const cacheHit = formItemsMapCache.get(tid);
  if (cacheHit) return cacheHit;

  const perPage = 1000;
  const firstUrl = `${API_BASE_URL}/api/v1/form-items?template_id=${tid}&per_page=${perPage}&page=1`;
  const first = await fetchJsonWithCache(firstUrl, { ttlMs: 6 * 60 * 60 * 1000 });
  const items = Array.isArray(first?.form_items) ? first.form_items.slice() : [];
  const totalPages = Number(first?.total_pages || 1);
  if (totalPages > 1) {
    const pages = [];
    for (let p = 2; p <= totalPages; p++) {
      const url = `${API_BASE_URL}/api/v1/form-items?template_id=${tid}&per_page=${perPage}&page=${p}`;
      pages.push(fetchJsonWithCache(url, { ttlMs: 6 * 60 * 60 * 1000 }));
    }
    const results = await Promise.all(pages);
    for (const res of results) {
      if (Array.isArray(res?.form_items)) items.push(...res.form_items);
    }
  }

  const map = new Map();
  for (const it of items) {
    if (!it) continue;
    const itemId = it.id;
    const itemType = it.type ?? it.item_type;
    const isIndicator = (itemType === 'indicator');
    const bankId = it.indicator_bank_id;
    if (itemId != null && isIndicator && bankId != null) {
      const fid = Number(itemId);
      const bid = Number(bankId);
      map.set(fid, bid);
      if (String(itemId) !== String(fid)) map.set(itemId, bid);
    }
  }
  formItemsMapCache.set(tid, map);
  return map;
}

/**
 * Hydrate legacy fields expected by older consumers:
 * - country_info (derived from iso2/iso3)
 * - answer_value alias for new value field
 */
async function ensureLegacyFields(items, locale = null) {
  if (!Array.isArray(items)) return [];
  const countries = await getCountriesList(locale);
  const byIso2 = new Map(countries.map(c => [String(c.iso2 || '').toUpperCase(), c]));
  const byIso3 = new Map(countries.map(c => [String(c.iso3 || '').toUpperCase(), c]));
  return items.map(item => {
    const iso2 = String(item?.iso2 || '').toUpperCase();
    const iso3 = String(item?.iso3 || '').toUpperCase();
    const country = item?.country_info || byIso2.get(iso2) || byIso3.get(iso3) || null;
    return {
      ...item,
      country_info: country || item.country_info || null,
      answer_value: item?.answer_value != null ? item.answer_value : item?.value
    };
  });
}

// Simple in-memory cache for country profiles
const countryProfileCache = new Map();
// Longer cache TTL for build-time performance (1 hour)
const CACHE_TTL = 60 * 60 * 1000; // 1 hour in milliseconds

/**
 * Get cached country profile or return null if expired/not found
 */
function getCachedCountryProfile(iso3) {
  const cached = countryProfileCache.get(iso3);
  if (!cached) return null;

  const now = Date.now();
  if (now - cached.timestamp > CACHE_TTL) {
    countryProfileCache.delete(iso3);
    return null;
  }

  return cached.data;
}

/**
 * Cache a country profile with timestamp
 */
function cacheCountryProfile(iso3, data) {
  countryProfileCache.set(iso3, {
    data,
    timestamp: Date.now()
  });
}

/**
 * Optimized version of getCountryProfile that uses more targeted API calls
 * and better caching strategies for improved performance
 */
export async function getCountryProfileOptimized(iso3) {
  try {
    const upperIso3 = (iso3 || '').toUpperCase();

    // Check cache first
    const cached = getCachedCountryProfile(upperIso3);
    if (cached) {
      console.log(`Using cached profile for ${upperIso3}`);
      return cached;
    }

    // 1) Get basic country info
    const countries = await getCountriesList();
    const country = countries.find(
      (c) => (c.iso3 && c.iso3.toUpperCase() === upperIso3)
    );

    if (!country) {
      throw new Error(`Country not found for ISO3: ${upperIso3}`);
    }

    return await getCountryProfileOptimizedWithCountries(upperIso3, countries);
  } catch (error) {
    console.error('Failed to assemble optimized country profile:', error);
    throw error;
  }
}

/**
 * Optimized version that accepts countries list to avoid redundant API calls
 * This is especially useful during build time when countries list is already available
 */
export async function getCountryProfileOptimizedWithCountries(iso3, countries) {
  try {
    const upperIso3 = (iso3 || '').toUpperCase();

    // Check cache first
    const cached = getCachedCountryProfile(upperIso3);
    if (cached) {
      return cached;
    }

    // Find country from the provided list
    const country = countries.find(
      (c) => (c.iso3 && c.iso3.toUpperCase() === upperIso3)
    );

    if (!country) {
      throw new Error(`Country not found for ISO3: ${upperIso3}`);
    }

    // Try to use stored data first via getDataWithRelated (which uses local data store)
    let countryEntries = [];

    try {
      console.log(`[getCountryProfileOptimizedWithCountries] Fetching data for ${upperIso3} (country ID: ${country.id})`);
      // Use getDataWithRelated which checks local store first, falls back to API
      // This provides better performance by using stored data when available
      // Use country_iso3 since dataStore filters by ISO codes
      const filterParams = {
        template_id: FDRS_TEMPLATE_ID,
        country_iso3: upperIso3,
        country_iso2: country.iso2 || undefined,
        disagg: true,
        related: 'all'
      };
      console.log(`[getCountryProfileOptimizedWithCountries] Filter params:`, filterParams);

      const countryData = await getDataWithRelated(filterParams);

      console.log(`[getCountryProfileOptimizedWithCountries] Received data:`, {
        isArray: Array.isArray(countryData),
        length: Array.isArray(countryData) ? countryData.length : 'not an array',
        type: typeof countryData
      });

      countryEntries = Array.isArray(countryData) ? countryData : [];
      console.log(`[getCountryProfileOptimizedWithCountries] Filtered to ${countryEntries.length} entries for ${upperIso3}`);
    } catch (fallbackError) {
      console.error('[getCountryProfileOptimizedWithCountries] Failed to get country data from store/API:', fallbackError);
      console.error('[getCountryProfileOptimizedWithCountries] Error details:', {
        message: fallbackError.message,
        stack: fallbackError.stack,
        countryIso3: upperIso3,
        countryId: country.id
      });
      console.warn('Failed to get country data from store/API, trying direct API call:', fallbackError.message);
      // Fallback: Direct API call if getDataWithRelated fails
      try {
        const perPageLimit = isBuildTime ? 200 : 500;
        const countryId = country.id;

        const countryDataUrl = buildDataTablesApiUrl({
          templateId: FDRS_TEMPLATE_ID,
          perPage: perPageLimit,
          countryId: countryId,
          disagg: true,
          related: 'all'
        });

        const countryDataResp = await fetch(countryDataUrl, {
          method: 'GET',
          headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
          },
          signal: AbortSignal.timeout(45000), // 45 second timeout for country data
        });

        if (countryDataResp.ok) {
          const countryDataResult = await countryDataResp.json();
          countryEntries = Array.isArray(countryDataResult?.data) ? countryDataResult.data : [];
        } else {
          // Final fallback: Fetch all data and filter
          const perPageLimit = isBuildTime ? 500 : 1000;
          const dataUrl = buildDataTablesApiUrl({
            templateId: FDRS_TEMPLATE_ID,
            perPage: perPageLimit,
            related: 'all'
          });
          const dataResp = await fetch(dataUrl, {
            method: 'GET',
            headers: {
              'Accept': 'application/json',
              'Content-Type': 'application/json',
            },
            signal: AbortSignal.timeout(60000), // 60 second timeout for general data fetch
          });
          if (!dataResp.ok) {
            console.error('API Error (getCountryProfileOptimized:data):', dataResp.status, await dataResp.text());
            throw new Error('Failed to fetch country data');
          }
          const allDataResult = await dataResp.json();
          const allEntries = Array.isArray(allDataResult?.data) ? allDataResult.data : [];

          // Filter to country-specific entries
          countryEntries = allEntries.filter((item) => {
            const info = item?.country_info || {};
            const itemIso3 = (info.iso3 || '').toUpperCase();
            const itemIso2 = (info.iso2 || '').toUpperCase();
            const itemName = (info.name || '').toLowerCase();
            return (
              itemIso3 === upperIso3 ||
              (country.iso2 && itemIso2 === (country.iso2 || '').toUpperCase()) ||
              (country.name && itemName === (country.name || '').toLowerCase())
            );
          });
        }
      } catch (finalError) {
        console.error('[getCountryProfileOptimizedWithCountries] All data fetch methods failed:', finalError);
        console.error('[getCountryProfileOptimizedWithCountries] Error details:', {
          message: finalError.message,
          stack: finalError.stack,
          countryIso3: upperIso3,
          countryId: country.id
        });
        // Don't throw - return empty profile instead to allow page to render
        // The page can still show country info even without indicator data
        countryEntries = [];
      }
    }

    // Early return if no country-specific data found
    if (countryEntries.length === 0) {
      console.warn(`[getCountryProfileOptimizedWithCountries] No data entries found for ${upperIso3} (country ID: ${country.id})`);
      console.warn(`[getCountryProfileOptimizedWithCountries] This might indicate:`);
      console.warn(`  - No data exists in the store for this country`);
      console.warn(`  - Country filtering is not working correctly`);
      console.warn(`  - Data needs to be synced`);

      const emptyProfile = {
        country_info: {
          id: country.id || null,
          name: country.name,
          iso3: country.iso3,
          iso2: country.iso2,
          national_society_name: country.national_society_name,
          flag_url: country.iso2 ? `/flags/${country.iso2.toLowerCase()}.svg` : null
        },
        summary_stats: {
          people_assisted_last_year: null,
          active_programs: 0,
          key_focus_areas: []
        },
        narrative: null,
        indicator_data: [],
        related_publications_api_url: null,
        map_data: null
      };

      // Cache empty profile too
      cacheCountryProfile(upperIso3, emptyProfile);
      return emptyProfile;
    }

    // Helper: extract numeric value from answer_value
    const extractNumeric = (answerValue) => {
      if (answerValue == null) return 0;
      if (typeof answerValue === 'object') {
        if (answerValue.values && answerValue.values.total != null) {
          return parseFloat(answerValue.values.total) || 0;
        }
        if (answerValue.total != null) {
          return parseFloat(answerValue.total) || 0;
        }
      }
      return parseFloat(answerValue) || 0;
    };

    // Determine latest period for this country's entries
    const periods = new Set();
    for (const e of countryEntries) {
      if (e?.period_name) periods.add(e.period_name);
    }
    const sortedPeriods = Array.from(periods).sort((a, b) => extractYearFromPeriod(b) - extractYearFromPeriod(a));
    const latestPeriod = sortedPeriods[0] || null;

    // Build indicator summaries for latest period (top 6 by value)
    const latestEntries = latestPeriod
      ? countryEntries.filter((e) => e.period_name === latestPeriod)
      : countryEntries;

    // Enrich latest entries with indicator bank details via a bulk form-items map
    const formItemsMap = await fetchFormItemsMapForTemplate(FDRS_TEMPLATE_ID);
    const indicatorIdSet = new Set();
    for (const it of latestEntries) {
      const fid = it?.form_item_id;
      const bankId = fid ? formItemsMap.get(fid) : null;
      if (bankId) indicatorIdSet.add(bankId);
    }
    const indicatorIds = [...indicatorIdSet];
    const indicatorDetailsList = await Promise.all(indicatorIds.map(id => getIndicatorDetailsById(id)));
    const indicatorMap = new Map();
    for (let i = 0; i < indicatorIds.length; i++) {
      if (indicatorDetailsList[i]) indicatorMap.set(indicatorIds[i], indicatorDetailsList[i]);
    }

    // More efficient indicator processing with early termination
    const indicatorTotals = new Map();
    let processedCount = 0;
    const maxIndicators = isBuildTime ? 6 : 10; // Even smaller limit during build time

    for (const item of latestEntries) {
      if (processedCount >= maxIndicators) break; // Early termination

      const fid = item?.form_item_id;
      const bankId = fid ? formItemsMap.get(fid) : null;
      const bank = bankId ? indicatorMap.get(bankId) : null;
      if (!bank || !bank.id) continue;

      const key = bank.id;
      const prev = indicatorTotals.get(key) || { total: 0, label: bank.name || `Indicator ${key}`, unit: bank.unit || '', period: latestPeriod };
      const av = item?.answer_value != null ? item.answer_value : item?.value;
      prev.total += extractNumeric(av);
      indicatorTotals.set(key, prev);
      processedCount++;
    }

    const indicator_data = Array.from(indicatorTotals.values())
      .sort((a, b) => (b.total || 0) - (a.total || 0))
      .slice(0, isBuildTime ? 4 : 6) // Fewer indicators during build time
      .map((x) => ({ indicator_label: x.label, value: x.total, unit: x.unit, period: x.period }));

    // Summary stats - optimized single pass
    const unitMatchesPeople = (unit) => {
      if (!unit) return false;
      const u = String(unit).toLowerCase();
      return (
        u === 'people' || u === 'persons' || u === 'beneficiaries' || u === 'person' || u === 'recipients'
      );
    };

    let peopleAssistedLastYear = 0;
    let activePrograms = 0;
    const sectorCount = new Map();
    const processedIndicators = new Set();

    // Single optimized pass through latest entries
    for (const item of latestEntries) {
      const fid = item?.form_item_id;
      const bankId = fid ? formItemsMap.get(fid) : null;
      const bank = bankId ? indicatorMap.get(bankId) : null;
      if (!bank) continue;

      const unit = bank.unit;
      const av = item?.answer_value != null ? item.answer_value : item?.value;
      const val = extractNumeric(av);

      if (unitMatchesPeople(unit)) {
        peopleAssistedLastYear += val;
      }

      const sectorPrimary = bank?.sector?.primary || bank?.sector?.name || bank?.sector;
      if (sectorPrimary) {
        sectorCount.set(sectorPrimary, (sectorCount.get(sectorPrimary) || 0) + 1);
      }

      // Track unique indicators for active programs count
      if (bank.id) {
        processedIndicators.add(bank.id);
      }
    }

    activePrograms = processedIndicators.size;

    const key_focus_areas = Array.from(sectorCount.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(([name]) => name)
      .filter(Boolean);

    const country_info = {
      id: country.id || null,
      name: country.name,
      iso3: country.iso3,
      iso2: country.iso2,
      national_society_name: country.national_society_name,
      flag_url: country.iso2 ? `/flags/${country.iso2.toLowerCase()}.svg` : null
    };

    const summary_stats = {
      people_assisted_last_year: peopleAssistedLastYear || null,
      active_programs: activePrograms || null,
      key_focus_areas
    };

    const profileData = {
      country_info,
      summary_stats,
      narrative: null,
      indicator_data,
      related_publications_api_url: null,
      map_data: null
    };

    // Cache the result
    cacheCountryProfile(upperIso3, profileData);

    console.log(`[getCountryProfileOptimizedWithCountries] Successfully built profile for ${upperIso3} with ${indicator_data.length} indicators`);
    return profileData;
  } catch (error) {
    console.error(`[getCountryProfileOptimizedWithCountries] Failed to assemble optimized country profile for ${iso3}:`, error);
    console.error('Error details:', {
      message: error.message,
      stack: error.stack,
      iso3: iso3
    });
    throw error;
  }
}

/**
 * Fetches indicators from the indicator bank.
 * @param {string} searchQuery - Optional search query for filtering by name or definition.
 * @param {string} type - Optional filter by indicator type.
 * @param {string} sector - Optional filter by sector.
 * @param {string} subSector - Optional filter by sub-sector.
 * @param {string} emergency - Optional filter by emergency type.
 * @param {string} archived - Optional filter by archived status ('true', 'false', or omit for all).
 * @param {string} locale - Optional locale for multilingual support.
 * @returns {Promise<Object>} A promise that resolves to the indicator bank data.
 * @throws {Error} If the network response is not ok.
 */
export async function getIndicatorBank(searchQuery = '', type = '', sector = '', subSector = '', emergency = '', archived = null, locale = 'en') {
  // Try to use local data store first
  const USE_LOCAL_STORE = process.env.NEXT_PUBLIC_USE_LOCAL_STORE !== 'false';
  const FORCE_API = process.env.NEXT_PUBLIC_FORCE_API === 'true';

  if (USE_LOCAL_STORE && !FORCE_API) {
    try {
      if (typeof window === 'undefined') {
        // Server-side: read from data store
        const { getIndicatorsFromStore } = await import('./dataStore');
        const indicators = await getIndicatorsFromStore({
          searchQuery,
          type,
          sector,
          subSector,
          archived
        });

        if (indicators.length > 0) {
          console.log(`Using ${indicators.length} indicators from local data store`);
          return { indicators };
        }
      } else {
        // Client-side: use API route (data store); fall back to Backoffice if store is empty
        try {
          const params = new URLSearchParams();
          if (searchQuery) params.append('search', searchQuery);
          if (type) params.append('type', type);
          if (sector) params.append('sector', sector);
          if (subSector) params.append('sub_sector', subSector);
          if (archived !== null) params.append('archived', archived);

          const response = await fetch(`/api/indicators?${params.toString()}`);
          if (response.ok) {
            const data = await response.json();
            const list = data.indicators || [];
            if (list.length > 0) {
              console.log(`Using ${list.length} indicators from API route`);
              return { indicators: list };
            }
            // Store empty: fall through to Backoffice indicator-bank
          }
        } catch (error) {
          console.warn('Failed to get indicators from API route, falling back to direct API:', error);
        }
      }
    } catch (error) {
      console.warn('Local store error for indicators, falling back to API:', error.message);
    }
  }

  // Fallback to Backoffice (or when data store is empty)
  const params = {};
  if (searchQuery) params.search = searchQuery;
  if (type) params.type = type;
  if (sector) params.sector = sector;
  if (subSector) params.sub_sector = subSector;
  if (emergency) params.emergency = emergency;
  if (archived !== null) params.archived = String(archived);
  const url = getBackofficeApiUrl('indicator-bank', params);

  console.log(`Fetching indicators from: ${url}`); // For debugging
  const data = await fetchJsonWithCache(url, { ttlMs: 6 * 60 * 60 * 1000 });

  // Fetch sectors and subsectors data to create lookup tables for translations
  let sectorsData = [];
  let subsectorsData = [];
  try {
    const sectorsResponse = await getSectorsSubsectors(locale);
    sectorsData = sectorsResponse.sectors || [];
    subsectorsData = sectorsData.flatMap(sector => sector.subsectors || []);
  } catch (error) {
    console.warn('Failed to fetch sectors data for translations:', error);
  }

  // Create lookup tables for sector and subsector translations
  const sectorLookup = {};
  const subsectorLookup = {};

  sectorsData.forEach(sector => {
    sectorLookup[sector.name] = sector.localized_name || sector.name;
  });

  subsectorsData.forEach(subsector => {
    subsectorLookup[subsector.name] = subsector.localized_name || subsector.name;
  });

  // Process indicators to use localized names
  if (data.indicators) {
    data.indicators = data.indicators.map(indicator => {
      return {
          ...indicator,
          localized_name: getLocalizedIndicatorName(indicator, locale),
          localized_definition: getLocalizedIndicatorDefinition(indicator, locale),
          // Process type localization
          localized_type: indicator.localized_type || indicator.type,
          // Process unit localization
          localized_unit: indicator.localized_unit || indicator.unit,
          // Process sector localization - handle the different data structure
          sector: indicator.sector ? (typeof indicator.sector === 'object' ? {
            ...indicator.sector,
            // For the indicator API, sector objects have primary/secondary/tertiary structure
            // We need to get the localized name for the primary sector
            localized_name: indicator.sector.primary ? (sectorLookup[indicator.sector.primary] || indicator.sector.primary) : indicator.sector.primary,
            name: indicator.sector.primary || indicator.sector.name || indicator.sector
          } : indicator.sector) : indicator.sector,
          // Process subsector localization - handle the different data structure
          sub_sector: indicator.sub_sector ? (typeof indicator.sub_sector === 'object' ? {
            ...indicator.sub_sector,
            // For the indicator API, subsector objects have primary/secondary/tertiary structure
            // We need to get the localized name for the primary subsector
            localized_name: indicator.sub_sector.primary ? (subsectorLookup[indicator.sub_sector.primary] || indicator.sub_sector.primary) : indicator.sub_sector.primary,
            name: indicator.sub_sector.primary || indicator.sub_sector.name || indicator.sub_sector
          } : indicator.sub_sector) : indicator.sub_sector
        };
    });
  }

  return data;
}

/**
 * Gets the localized name for an indicator based on the current locale.
 * @param {Object} indicator - The indicator object from the API.
 * @param {string} locale - The current locale.
 * @returns {string} The localized name.
 */
export function getLocalizedIndicatorName(indicator, locale) {
  const lc = (locale || 'en').toLowerCase().split('_', 1)[0].split('-', 1)[0];
  const translations = indicator?.name_translations && typeof indicator.name_translations === 'object'
    ? indicator.name_translations
    : null;
  if (translations && typeof translations[lc] === 'string' && translations[lc].trim()) {
    return translations[lc].trim();
  }
  if (translations && typeof translations.en === 'string' && translations.en.trim()) {
    return translations.en.trim();
  }
  return indicator?.name || '';
}

/**
 * Gets the localized definition for an indicator based on the current locale.
 * @param {Object} indicator - The indicator object from the API.
 * @param {string} locale - The current locale.
 * @returns {string} The localized definition.
 */
export function getLocalizedIndicatorDefinition(indicator, locale) {
  const lc = (locale || 'en').toLowerCase().split('_', 1)[0].split('-', 1)[0];
  const translations = indicator?.definition_translations && typeof indicator.definition_translations === 'object'
    ? indicator.definition_translations
    : null;
  if (translations && typeof translations[lc] === 'string' && translations[lc].trim()) {
    return translations[lc].trim();
  }
  if (translations && typeof translations.en === 'string' && translations.en.trim()) {
    return translations.en.trim();
  }
  return indicator?.definition || '';
}

/**
 * Fetches sectors and subsectors with their logos and hierarchical structure.
 * @param {string} locale - Optional locale for multilingual support.
 * @returns {Promise<Object>} A promise that resolves to the sectors and subsectors data.
 * @throws {Error} If the network response is not ok.
 */
export async function getSectorsSubsectors(locale = 'en') {
  // Try to use local data store first
  const USE_LOCAL_STORE = process.env.NEXT_PUBLIC_USE_LOCAL_STORE !== 'false';
  const FORCE_API = process.env.NEXT_PUBLIC_FORCE_API === 'true';

  if (USE_LOCAL_STORE && !FORCE_API) {
    try {
      // Prefer a dedicated local file (includes multilingual_names)
      if (typeof window === 'undefined') {
        // Server-side: use dataStore directly
        const { getSectorsSubsectorsFromStore } = await import('./dataStore');
        const payload = await getSectorsSubsectorsFromStore();
        if (payload?.sectors?.length) {
          payload.sectors = payload.sectors.map(sector => ({
            ...sector,
            localized_name: getLocalizedSectorName(sector, locale),
            localized_description: getLocalizedSectorDescription(sector, locale),
            subsectors: (sector.subsectors || []).map(subsector => ({
              ...subsector,
              localized_name: getLocalizedSubsectorName(subsector, locale),
              localized_description: getLocalizedSubsectorDescription(subsector, locale)
            }))
          }));
          return payload;
        }
      } else {
        // Client-side: use API route
        try {
          const response = await fetch(`/api/sectors-subsectors?locale=${encodeURIComponent(locale || 'en')}`);
          if (response.ok) {
            const data = await response.json();
            if (data.sectors && data.sectors.length > 0) {
              console.log(`Using ${data.sectors.length} sectors from API route (client-side)`);
              return data;
            }
          }
        } catch (error) {
          console.warn('Failed to get sectors from API route, falling back to direct API:', error);
        }
      }
    } catch (error) {
      console.warn('Local store error for sectors, falling back to API:', error.message);
    }
  }

  // Fallback to direct API call
  try {
    const url = `${API_BASE_URL}/api/v1/sectors-subsectors`;

    console.log(`Fetching sectors and subsectors from: ${url}`); // For debugging
    const data = await fetchJsonWithCache(url, { ttlMs: 24 * 60 * 60 * 1000 });

    // Process sectors and subsectors to use localized names
    if (data.sectors) {
      data.sectors = data.sectors.map(sector => ({
        ...sector,
        localized_name: getLocalizedSectorName(sector, locale),
        localized_description: getLocalizedSectorDescription(sector, locale),
        subsectors: sector.subsectors.map(subsector => ({
          ...subsector,
          localized_name: getLocalizedSubsectorName(subsector, locale),
          localized_description: getLocalizedSubsectorDescription(subsector, locale)
        }))
      }));
    }

    return data;
  } catch (error) {
    console.error('Error fetching sectors and subsectors:', error);
    // Return empty structure to allow app to continue working
    return { sectors: [] };
  }
}

/**
 * Fetches available indicators that have data in the data API.
 * @param {string} locale - The current locale.
 * @returns {Promise<Array>} A promise that resolves to an array of indicators with data.
 */
export async function getAvailableIndicatorsWithData(locale = 'en') {

  try {
    // First, get all indicators from the indicator bank
    const indicatorBankResponse = await getIndicatorBank('', '', '', '', '', null, locale);
    const allIndicators = indicatorBankResponse.indicators || [];



    // Then, fetch all data/tables pages to determine which indicators actually have data.
    const perPage = 1000;
    const baseDataUrl = buildDataTablesApiUrl({
      templateId: FDRS_TEMPLATE_ID,
      perPage,
      disagg: true,
      related: 'none' // We only need data, not related tables
    });

    const firstPageUrl = `${baseDataUrl}&page=1`;
    const firstPageResult = await fetchJsonWithCache(firstPageUrl, { ttlMs: 3 * 60 * 60 * 1000 });
    // /data/tables returns { data: [...] } structure
    const dataEntries = Array.isArray(firstPageResult?.data) ? firstPageResult.data.slice() : [];
    const totalPages = Number(firstPageResult?.total_pages || 1);
    if (totalPages > 1) {
      const pagePromises = [];
      for (let page = 2; page <= totalPages; page++) {
        pagePromises.push(fetchJsonWithCache(`${baseDataUrl}&page=${page}`, { ttlMs: 3 * 60 * 60 * 1000 }));
      }
      const pageResults = await Promise.all(pagePromises);
      for (const pageResult of pageResults) {
        if (Array.isArray(pageResult?.data)) dataEntries.push(...pageResult.data);
      }
    }

    // Resolve indicator IDs via a single bulk form-items map for FDRS template
    const formItemsMap = await fetchFormItemsMapForTemplate(FDRS_TEMPLATE_ID);
    // Canonical set of indicator-bank IDs (integers only) that have data
    const availableIndicatorIds = new Set();
    for (const entry of dataEntries) {
      const fid = entry?.form_item_id;
      const bankId = fid != null
        ? (formItemsMap.get(Number(fid)) ?? formItemsMap.get(String(fid)) ?? formItemsMap.get(fid))
        : null;
      if (bankId != null) {
        const n = parseInt(Number(bankId), 10);
        if (!Number.isNaN(n)) availableIndicatorIds.add(n);
      }
      if (entry?.indicator_id != null) {
        const n = parseInt(Number(entry.indicator_id), 10);
        if (!Number.isNaN(n)) availableIndicatorIds.add(n);
      }
      if (entry?.indicator_bank_id != null) {
        const n = parseInt(Number(entry.indicator_bank_id), 10);
        if (!Number.isNaN(n)) availableIndicatorIds.add(n);
      }
    }

    // Normalize indicator id to integer.
    // Prefer explicit bank ids over generic id when available because local stores
    // may carry a different id namespace than data-table indicator references.
    const toCanonicalId = (ind) => {
      let raw =
        ind?.indicator_bank_id ??
        ind?.bank_details?.id ??
        ind?.IndicatorBankId ??
        ind?.id ??
        ind?.Id;
      if (raw == null || raw === '') {
        if (ind && typeof ind === 'object') {
          const idKey = Object.keys(ind).find((k) =>
            k.toLowerCase() === 'indicator_bank_id' ||
            k.toLowerCase() === 'indicatorbankid' ||
            k.toLowerCase() === 'id'
          );
          raw = idKey != null ? ind[idKey] : undefined;
        }
      }
      if (raw == null || raw === '') return NaN;
      const n = parseInt(Number(raw), 10);
      return Number.isNaN(n) ? NaN : n;
    };
    let availableIndicators = allIndicators.filter((ind) => {
      const canonical = toCanonicalId(ind);
      return !Number.isNaN(canonical) && availableIndicatorIds.has(canonical);
    });

    // If local indicator-store IDs are stale/out-of-sync, retry with live Backoffice
    // indicator-bank payload before giving up.
    if (availableIndicatorIds.size > 0 && availableIndicators.length === 0) {
      try {
        const liveIndicatorBankUrl = getBackofficeApiUrl('indicator-bank');
        const liveResponse = await fetchJsonWithCache(liveIndicatorBankUrl, { ttlMs: 30 * 60 * 1000 });
        const liveIndicators = liveResponse?.indicators || [];
        if (liveIndicators.length > 0) {
          availableIndicators = liveIndicators.filter((ind) => {
            const canonical = toCanonicalId(ind);
            return !Number.isNaN(canonical) && availableIndicatorIds.has(canonical);
          }).map((indicator) => ({
            ...indicator,
            localized_name: getLocalizedIndicatorName(indicator, locale),
            localized_definition: getLocalizedIndicatorDefinition(indicator, locale),
            localized_type: indicator.localized_type || indicator.type,
            localized_unit: indicator.localized_unit || indicator.unit
          }));
        }
      } catch (retryError) {
        console.warn('[getAvailableIndicatorsWithData] Live indicator-bank retry failed:', retryError);
      }
    }

    if (process.env.NODE_ENV === 'development' && typeof console !== 'undefined' && console.debug) {
      const idsWithData = [...availableIndicatorIds].sort((a, b) => a - b);
      const bankCanonicalIds = [...new Set(allIndicators.map(toCanonicalId).filter(n => !Number.isNaN(n)))].sort((a, b) => a - b).slice(0, 10);
      const bankIdsInSet = bankCanonicalIds.filter(id => availableIndicatorIds.has(id));
      const firstIndKeys = allIndicators.length > 0 ? Object.keys(allIndicators[0]) : [];
      const firstIndIdRaw = allIndicators.length > 0 ? allIndicators[0].id : undefined;
      console.debug(
        '[getAvailableIndicatorsWithData]',
        'allIndicators:', allIndicators.length,
        'dataEntries:', dataEntries.length,
        'formItemsMapSize:', formItemsMap.size,
        'indicatorIdsWithData:', availableIndicatorIds.size,
        'availableIndicators:', availableIndicators.length,
        availableIndicatorIds.size > 0 && availableIndicators.length === 0
          ? {
              idsWithDataSample: idsWithData.slice(0, 10),
              bankCanonicalIdsSample: bankCanonicalIds,
              bankIdsInSetCount: bankIdsInSet.length,
              firstIndicatorKeys: firstIndKeys,
              firstIndicatorIdRaw: firstIndIdRaw,
              firstIndicatorIdType: typeof firstIndIdRaw
            }
          : {}
      );
    }

    return availableIndicators;
  } catch (error) {
    console.error('Error fetching available indicators with data:', error);
    // Fallback to returning all indicators if data API fails
    const indicatorBankResponse = await getIndicatorBank('', '', '', '', '', null, locale);
    return indicatorBankResponse.indicators || [];
  }
}

/**
 * Gets the localized name for a sector based on the current locale.
 * @param {Object} sector - The sector object from the API.
 * @param {string} locale - The current locale.
 * @returns {string} The localized name.
 */
export function getLocalizedSectorName(sector, locale) {
  // Handle null/undefined sector
  if (!sector) {
    console.warn('getLocalizedSectorName called with null/undefined sector');
    return 'Other';
  }

  // Handle string sector (fallback)
  if (typeof sector === 'string') {
    return sector;
  }

  // Handle object sector
  if (typeof sector === 'object') {
    const lc = (locale || 'en').toLowerCase().split('_', 1)[0].split('-', 1)[0];
    if (sector.multilingual_names && sector.multilingual_names[lc]) {
      return sector.multilingual_names[lc];
    }
    return sector.name || sector.primary || 'Other';
  }

  // Fallback for any other case
  console.warn('getLocalizedSectorName: unexpected sector type:', typeof sector, sector);
  return 'Other';
}

/**
 * Gets the localized description for a sector based on the current locale.
 * @param {Object} sector - The sector object from the API.
 * @param {string} locale - The current locale.
 * @returns {string} The localized description.
 */
function getLocalizedSectorDescription(sector, locale) {
  // For now, descriptions are only in English
  return sector.description;
}

/**
 * Gets the localized name for a subsector based on the current locale.
 * @param {Object} subsector - The subsector object from the API.
 * @param {string} locale - The current locale.
 * @returns {string} The localized name.
 */
export function getLocalizedSubsectorName(subsector, locale) {
  // Handle null/undefined subsector
  if (!subsector) {
    console.warn('getLocalizedSubsectorName called with null/undefined subsector');
    return 'General';
  }

  // Handle string subsector (fallback)
  if (typeof subsector === 'string') {
    return subsector;
  }

  // Handle object subsector
  if (typeof subsector === 'object') {
    const lc = (locale || 'en').toLowerCase().split('_', 1)[0].split('-', 1)[0];
    if (subsector.multilingual_names && subsector.multilingual_names[lc]) {
      return subsector.multilingual_names[lc];
    }
    return subsector.name || subsector.primary || 'General';
  }

  // Fallback for any other case
  console.warn('getLocalizedSubsectorName: unexpected subsector type:', typeof subsector, subsector);
  return 'General';
}

/**
 * Gets the localized description for a subsector based on the current locale.
 * @param {Object} subsector - The subsector object from the API.
 * @param {string} locale - The current locale.
 * @returns {string} The localized description.
 */
function getLocalizedSubsectorDescription(subsector, locale) {
  // For now, descriptions are only in English
  return subsector.description;
}

/**
 * Gets the localized type name for an indicator.
 * @param {string} type - The indicator type.
 * @param {string} locale - The current locale.
 * @returns {string} The localized type name.
 */
function getLocalizedTypeName(type, locale) {
  // No hardcoded language maps here. The backend already returns `localized_type`
  // when you pass `locale=` to the API. This helper is a conservative fallback.
  return type || '';
}

/**
 * Gets the localized unit name for an indicator.
 * @param {string} unit - The indicator unit.
 * @param {string} locale - The current locale.
 * @returns {string} The localized unit name.
 */
function getLocalizedUnitName(unit, locale) {
  // No hardcoded language maps here. The backend already returns `localized_unit`
  // when you pass `locale=` to the API. This helper is a conservative fallback.
  return unit || '';
}

/* LEGACY_UNIT_TRANSLATIONS_REMOVED_START
      'en': 'Days',
      'fr': 'Jours',
      'es': 'Días',
      'ar': 'أيام',
      'zh': '天',
      'ru': 'Дни',
      'hi': 'दिन'
    },
    'weeks': {
      'en': 'Weeks',
      'fr': 'Semaines',
      'es': 'Semanas',
      'ar': 'أسابيع',
      'zh': '周',
      'ru': 'Недели',
      'hi': 'सप्ताह'
    },
    'months': {
      'en': 'Months',
      'fr': 'Mois',
      'es': 'Meses',
      'ar': 'أشهر',
      'zh': '月',
      'ru': 'Месяцы',
      'hi': 'महीने'
    },
    'years': {
      'en': 'Years',
      'fr': 'Années',
      'es': 'Años',
      'ar': 'سنوات',
      'zh': '年',
      'ru': 'Годы',
      'hi': 'साल'
    },
    'hours': {
      'en': 'Hours',
      'fr': 'Heures',
      'es': 'Horas',
      'ar': 'ساعات',
      'zh': '小时',
      'ru': 'Часы',
      'hi': 'घंटे'
    },
    'minutes': {
      'en': 'Minutes',
      'fr': 'Minutes',
      'es': 'Minutos',
      'ar': 'دقائق',
      'zh': '分钟',
      'ru': 'Минуты',
      'hi': 'मिनट'
    },
    'meters': {
      'en': 'Meters',
      'fr': 'Mètres',
      'es': 'Metros',
      'ar': 'أمتار',
      'zh': '米',
      'ru': 'Метры',
      'hi': 'मीटर'
    },
    'kilometers': {
      'en': 'Kilometers',
      'fr': 'Kilomètres',
      'es': 'Kilómetros',
      'ar': 'كيلومترات',
      'zh': '公里',
      'ru': 'Километры',
      'hi': 'किलोमीटर'
    },
    'grams': {
      'en': 'Grams',
      'fr': 'Grammes',
      'es': 'Gramos',
      'ar': 'جرامات',
      'zh': '克',
      'ru': 'Граммы',
      'hi': 'ग्राम'
    },
    'tons': {
      'en': 'Tons',
      'fr': 'Tonnes',
      'es': 'Toneladas',
      'ar': 'أطنان',
      'zh': '吨',
      'ru': 'Тонны',
      'hi': 'टन'
    },
    'dollars': {
      'en': 'Dollars',
      'fr': 'Dollars',
      'es': 'Dólares',
      'ar': 'دولارات',
      'zh': '美元',
      'ru': 'Доллары',
      'hi': 'डॉलर'
    },
    'euros': {
      'en': 'Euros',
      'fr': 'Euros',
      'es': 'Euros',
      'ar': 'يورو',
      'zh': '欧元',
      'ru': 'Евро',
      'hi': 'यूरो'
    },
    'ratio': {
      'en': 'Ratio',
      'fr': 'Ratio',
      'es': 'Ratio',
      'ar': 'نسبة',
      'zh': '比率',
      'ru': 'Соотношение',
      'hi': 'अनुपात'
    },
    'rate': {
      'en': 'Rate',
      'fr': 'Taux',
      'es': 'Tasa',
      'ar': 'معدل',
      'zh': '比率',
      'ru': 'Ставка',
      'hi': 'दर'
    },
    'count': {
      'en': 'Count',
      'fr': 'Compte',
      'es': 'Conteo',
      'ar': 'عدد',
      'zh': '计数',
      'ru': 'Количество',
      'hi': 'गणना'
    },
    'number': {
      'en': 'Number',
      'fr': 'Nombre',
      'es': 'Número',
      'ar': 'رقم',
      'zh': '数字',
      'ru': 'Число',
      'hi': 'संख्या'
    },
    'amount': {
      'en': 'Amount',
      'fr': 'Montant',
      'es': 'Cantidad',
      'ar': 'مبلغ',
      'zh': '金额',
      'ru': 'Сумма',
      'hi': 'राशि'
    },
    'quantity': {
      'en': 'Quantity',
      'fr': 'Quantité',
      'es': 'Cantidad',
      'ar': 'كمية',
      'zh': '数量',
      'ru': 'Количество',
      'hi': 'मात्रा'
    },
    'total': {
      'en': 'Total',
      'fr': 'Total',
      'es': 'Total',
      'ar': 'إجمالي',
      'zh': '总计',
      'ru': 'Всего',
      'hi': 'कुल'
    },
    'average': {
      'en': 'Average',
      'fr': 'Moyenne',
      'es': 'Promedio',
      'ar': 'متوسط',
      'zh': '平均',
      'ru': 'Среднее',
      'hi': 'औसत'
    },
    'per': {
      'en': 'Per',
      'fr': 'Par',
      'es': 'Por',
      'ar': 'لكل',
      'zh': '每',
      'ru': 'На',
      'hi': 'प्रति'
    },
    'per capita': {
      'en': 'Per Capita',
      'fr': 'Par Habitant',
      'es': 'Per Cápita',
      'ar': 'للشخص الواحد',
      'zh': '人均',
      'ru': 'На Душу Населения',
      'hi': 'प्रति व्यक्ति'
    },
    'per household': {
      'en': 'Per Household',
      'fr': 'Par Ménage',
      'es': 'Por Hogar',
      'ar': 'لكل أسرة',
      'zh': '每户',
      'ru': 'На Домохозяйство',
      'hi': 'प्रति परिवार'
    },
    'per day': {
      'en': 'Per Day',
      'fr': 'Par Jour',
      'es': 'Por Día',
      'ar': 'في اليوم',
      'zh': '每天',
      'ru': 'В День',
      'hi': 'प्रति दिन'
    },
    'per week': {
      'en': 'Per Week',
      'fr': 'Par Semaine',
      'es': 'Por Semana',
      'ar': 'في الأسبوع',
      'zh': '每周',
      'ru': 'В Неделю',
      'hi': 'प्रति सप्ताह'
    },
    'per month': {
      'en': 'Per Month',
      'fr': 'Par Mois',
      'es': 'Por Mes',
      'ar': 'في الشهر',
      'zh': '每月',
      'ru': 'В Месяц',
      'hi': 'प्रति महीना'
    },
    'per year': {
      'en': 'Per Year',
      'fr': 'Par An',
      'es': 'Por Año',
      'ar': 'في السنة',
      'zh': '每年',
      'ru': 'В Год',
      'hi': 'प्रति वर्ष'
    },
    'nation': {
      'en': 'Nation',
      'fr': 'Nation',
      'es': 'Nación',
      'ar': 'أمة',
      'zh': '国家',
      'ru': 'Нация',
      'hi': 'राष्ट्र'
    },
    'nations': {
      'en': 'Nations',
      'fr': 'Nations',
      'es': 'Naciones',
      'ar': 'أمم',
      'zh': '国家',
      'ru': 'Нации',
      'hi': 'राष्ट्र'
    },
    'country': {
      'en': 'Country',
      'fr': 'Pays',
      'es': 'País',
      'ar': 'بلد',
      'zh': '国家',
      'ru': 'Страна',
      'hi': 'देश'
    },
    'countries': {
      'en': 'Countries',
      'fr': 'Pays',
      'es': 'Países',
      'ar': 'بلدان',
      'zh': '国家',
      'ru': 'Страны',
      'hi': 'देश'
    },
    'funds': {
      'en': 'Funds',
      'fr': 'Fonds',
      'es': 'Fondos',
      'ar': 'أموال',
      'zh': '资金',
      'ru': 'Фонды',
      'hi': 'धन'
    },
    'fund': {
      'en': 'Fund',
      'fr': 'Fonds',
      'es': 'Fondo',
      'ar': 'صندوق',
      'zh': '基金',
      'ru': 'Фонд',
      'hi': 'कोष'
    },
    'metrics': {
      'en': 'Metrics',
      'fr': 'Métriques',
      'es': 'Métricas',
      'ar': 'مقاييس',
      'zh': '指标',
      'ru': 'Метрики',
      'hi': 'मैट्रिक्स'
    },
    'metric': {
      'en': 'Metric',
      'fr': 'Métrique',
      'es': 'Métrica',
      'ar': 'مقياس',
      'zh': '指标',
      'ru': 'Метрика',
      'hi': 'मैट्रिक'
    },
    'indicators': {
      'en': 'Indicators',
      'fr': 'Indicateurs',
      'es': 'Indicadores',
      'ar': 'مؤشرات',
      'zh': '指标',
      'ru': 'Индикаторы',
      'hi': 'संकेतक'
    },
    'indicator': {
      'en': 'Indicator',
      'fr': 'Indicateur',
      'es': 'Indicador',
      'ar': 'مؤشر',
      'zh': '指标',
      'ru': 'Индикатор',
      'hi': 'संकेतक'
    },
    'organizations': {
      'en': 'Organizations',
      'fr': 'Organisations',
      'es': 'Organizaciones',
      'ar': 'منظمات',
      'zh': '组织',
      'ru': 'Организации',
      'hi': 'संगठन'
    },
    'organization': {
      'en': 'Organization',
      'fr': 'Organisation',
      'es': 'Organización',
      'ar': 'منظمة',
      'zh': '组织',
      'ru': 'Организация',
      'hi': 'संगठन'
    },
    'agencies': {
      'en': 'Agencies',
      'fr': 'Agences',
      'es': 'Agencias',
      'ar': 'وكالات',
      'zh': '机构',
      'ru': 'Агентства',
      'hi': 'एजेंसियां'
    },
    'agency': {
      'en': 'Agency',
      'fr': 'Agence',
      'es': 'Agencia',
      'ar': 'وكالة',
      'zh': '机构',
      'ru': 'Агентство',
      'hi': 'एजेंसी'
    },
    'projects': {
      'en': 'Projects',
      'fr': 'Projets',
      'es': 'Proyectos',
      'ar': 'مشاريع',
      'zh': '项目',
      'ru': 'Проекты',
      'hi': 'परियोजनाएं'
    },
    'project': {
      'en': 'Project',
      'fr': 'Projet',
      'es': 'Proyecto',
      'ar': 'مشروع',
      'zh': '项目',
      'ru': 'Проект',
      'hi': 'परियोजना'
    },
    'programs': {
      'en': 'Programs',
      'fr': 'Programmes',
      'es': 'Programas',
      'ar': 'برامج',
      'zh': '计划',
      'ru': 'Программы',
      'hi': 'कार्यक्रम'
    },
    'program': {
      'en': 'Program',
      'fr': 'Programme',
      'es': 'Programa',
      'ar': 'برنامج',
      'zh': '计划',
      'ru': 'Программа',
      'hi': 'कार्यक्रम'
    },
    'activities': {
      'en': 'Activities',
      'fr': 'Activités',
      'es': 'Actividades',
      'ar': 'أنشطة',
      'zh': '活动',
      'ru': 'Деятельность',
      'hi': 'गतिविधियां'
    },
    'activity': {
      'en': 'Activity',
      'fr': 'Activité',
      'es': 'Actividad',
      'ar': 'نشاط',
      'zh': '活动',
      'ru': 'Деятельность',
      'hi': 'गतिविधि'
    },
    'events': {
      'en': 'Events',
      'fr': 'Événements',
      'es': 'Eventos',
      'ar': 'أحداث',
      'zh': '事件',
      'ru': 'События',
      'hi': 'घटनाएं'
    },
    'event': {
      'en': 'Event',
      'fr': 'Événement',
      'es': 'Evento',
      'ar': 'حدث',
      'zh': '事件',
      'ru': 'Событие',
      'hi': 'घटना'
    },
    'sessions': {
      'en': 'Sessions',
      'fr': 'Sessions',
      'es': 'Sesiones',
      'ar': 'جلسات',
      'zh': '会议',
      'ru': 'Сессии',
      'hi': 'सत्र'
    },
    'session': {
      'en': 'Session',
      'fr': 'Session',
      'es': 'Sesión',
      'ar': 'جلسة',
      'zh': '会议',
      'ru': 'Сессия',
      'hi': 'सत्र'
    },
    'meetings': {
      'en': 'Meetings',
      'fr': 'Réunions',
      'es': 'Reuniones',
      'ar': 'اجتماعات',
      'zh': '会议',
      'ru': 'Встречи',
      'hi': 'बैठकें'
    },
    'meeting': {
      'en': 'Meeting',
      'fr': 'Réunion',
      'es': 'Reunión',
      'ar': 'اجتماع',
      'zh': '会议',
      'ru': 'Встреча',
      'hi': 'बैठक'
    },
    'reports': {
      'en': 'Reports',
      'fr': 'Rapports',
      'es': 'Informes',
      'ar': 'تقارير',
      'zh': '报告',
      'ru': 'Отчеты',
      'hi': 'रिपोर्ट'
    },
    'report': {
      'en': 'Report',
      'fr': 'Rapport',
      'es': 'Informe',
      'ar': 'تقرير',
      'zh': '报告',
      'ru': 'Отчет',
      'hi': 'रिपोर्ट'
    },
    'documents': {
      'en': 'Documents',
      'fr': 'Documents',
      'es': 'Documentos',
      'ar': 'وثائق',
      'zh': '文件',
      'ru': 'Документы',
      'hi': 'दस्तावेज'
    },
    'document': {
      'en': 'Document',
      'fr': 'Document',
      'es': 'Documento',
      'ar': 'وثيقة',
      'zh': '文件',
      'ru': 'Документ',
      'hi': 'दस्तावेज'
    },
    'cases': {
      'en': 'Cases',
      'fr': 'Cas',
      'es': 'Casos',
      'ar': 'حالات',
      'zh': '案例',
      'ru': 'Случаи',
      'hi': 'मामले'
    },
    'case': {
      'en': 'Case',
      'fr': 'Cas',
      'es': 'Caso',
      'ar': 'حالة',
      'zh': '案例',
      'ru': 'Случай',
      'hi': 'मामला'
    },
    'instances': {
      'en': 'Instances',
      'fr': 'Instances',
      'es': 'Instancias',
      'ar': 'حالات',
      'zh': '实例',
      'ru': 'Экземпляры',
      'hi': 'उदाहरण'
    },
    'instance': {
      'en': 'Instance',
      'fr': 'Instance',
      'es': 'Instancia',
      'ar': 'حالة',
      'zh': '实例',
      'ru': 'Экземпляр',
      'hi': 'उदाहरण'
    },
    'items': {
      'en': 'Items',
      'fr': 'Articles',
      'es': 'Artículos',
      'ar': 'عناصر',
      'zh': '项目',
      'ru': 'Элементы',
      'hi': 'वस्तुएं'
    },
    'item': {
      'en': 'Item',
      'fr': 'Article',
      'es': 'Artículo',
      'ar': 'عنصر',
      'zh': '项目',
      'ru': 'Элемент',
      'hi': 'वस्तु'
    },
    'records': {
      'en': 'Records',
      'fr': 'Enregistrements',
      'es': 'Registros',
      'ar': 'سجلات',
      'zh': '记录',
      'ru': 'Записи',
      'hi': 'रिकॉर्ड'
    },
    'record': {
      'en': 'Record',
      'fr': 'Enregistrement',
      'es': 'Registro',
      'ar': 'سجل',
      'zh': '记录',
      'ru': 'Запись',
      'hi': 'रिकॉर्ड'
    },
    'entries': {
      'en': 'Entries',
      'fr': 'Entrées',
      'es': 'Entradas',
      'ar': 'إدخالات',
      'zh': '条目',
      'ru': 'Записи',
      'hi': 'प्रविष्टियां'
    },
    'entry': {
      'en': 'Entry',
      'fr': 'Entrée',
      'es': 'Entrada',
      'ar': 'إدخال',
      'zh': '条目',
      'ru': 'Запись',
      'hi': 'प्रविष्टि'
    },
    'samples': {
      'en': 'Samples',
      'fr': 'Échantillons',
      'es': 'Muestras',
      'ar': 'عينات',
      'zh': '样本',
      'ru': 'Образцы',
      'hi': 'नमूने'
    },
    'sample': {
      'en': 'Sample',
      'fr': 'Échantillon',
      'es': 'Muestra',
      'ar': 'عينة',
      'zh': '样本',
      'ru': 'Образец',
      'hi': 'नमूना'
    },
    'categories': {
      'en': 'Categories',
      'fr': 'Catégories',
      'es': 'Categorías',
      'ar': 'فئات',
      'zh': '类别',
      'ru': 'Категории',
      'hi': 'श्रेणियां'
    },
    'category': {
      'en': 'Category',
      'fr': 'Catégorie',
      'es': 'Categoría',
      'ar': 'فئة',
      'zh': '类别',
      'ru': 'Категория',
      'hi': 'श्रेणी'
    },
    'types': {
      'en': 'Types',
      'fr': 'Types',
      'es': 'Tipos',
      'ar': 'أنواع',
      'zh': '类型',
      'ru': 'Типы',
      'hi': 'प्रकार'
    },
    'type': {
      'en': 'Type',
      'fr': 'Type',
      'es': 'Tipo',
      'ar': 'نوع',
      'zh': '类型',
      'ru': 'Тип',
      'hi': 'प्रकार'
    },
    'groups': {
      'en': 'Groups',
      'fr': 'Groupes',
      'es': 'Grupos',
      'ar': 'مجموعات',
      'zh': '组',
      'ru': 'Группы',
      'hi': 'समूह'
    },
    'group': {
      'en': 'Group',
      'fr': 'Groupe',
      'es': 'Grupo',
      'ar': 'مجموعة',
      'zh': '组',
      'ru': 'Группа',
      'hi': 'समूह'
    },
    'teams': {
      'en': 'Teams',
      'fr': 'Équipes',
      'es': 'Equipos',
      'ar': 'فرق',
      'zh': '团队',
      'ru': 'Команды',
      'hi': 'टीमें'
    },
    'team': {
      'en': 'Team',
      'fr': 'Équipe',
      'es': 'Equipo',
      'ar': 'فريق',
      'zh': '团队',
      'ru': 'Команда',
      'hi': 'टीम'
    },
    'centers': {
      'en': 'Centers',
      'fr': 'Centres',
      'es': 'Centros',
      'ar': 'مراكز',
      'zh': '中心',
      'ru': 'Центры',
      'hi': 'केंद्र'
    },
    'center': {
      'en': 'Center',
      'fr': 'Centre',
      'es': 'Centro',
      'ar': 'مركز',
      'zh': '中心',
      'ru': 'Центр',
      'hi': 'केंद्र'
    },
    'facilities': {
      'en': 'Facilities',
      'fr': 'Installations',
      'es': 'Instalaciones',
      'ar': 'مرافق',
      'zh': '设施',
      'ru': 'Объекты',
      'hi': 'सुविधाएं'
    },
    'facility': {
      'en': 'Facility',
      'fr': 'Installation',
      'es': 'Instalación',
      'ar': 'مرفق',
      'zh': '设施',
      'ru': 'Объект',
      'hi': 'सुविधा'
    },
    'sites': {
      'en': 'Sites',
      'fr': 'Sites',
      'es': 'Sitios',
      'ar': 'مواقع',
      'zh': '站点',
      'ru': 'Сайты',
      'hi': 'साइटें'
    },
    'site': {
      'en': 'Site',
      'fr': 'Site',
      'es': 'Sitio',
      'ar': 'موقع',
      'zh': '站点',
      'ru': 'Сайт',
      'hi': 'साइट'
    },
    'locations': {
      'en': 'Locations',
      'fr': 'Emplacements',
      'es': 'Ubicaciones',
      'ar': 'مواقع',
      'zh': '位置',
      'ru': 'Местоположения',
      'hi': 'स्थान'
    },
    'location': {
      'en': 'Location',
      'fr': 'Emplacement',
      'es': 'Ubicación',
      'ar': 'موقع',
      'zh': '位置',
      'ru': 'Местоположение',
      'hi': 'स्थान'
    },
    'areas': {
      'en': 'Areas',
      'fr': 'Zones',
      'es': 'Áreas',
      'ar': 'مناطق',
      'zh': '区域',
      'ru': 'Районы',
      'hi': 'क्षेत्र'
    },
    'area': {
      'en': 'Area',
      'fr': 'Zone',
      'es': 'Área',
      'ar': 'منطقة',
      'zh': '区域',
      'ru': 'Район',
      'hi': 'क्षेत्र'
    },
    'regions': {
      'en': 'Regions',
      'fr': 'Régions',
      'es': 'Regiones',
      'ar': 'مناطق',
      'zh': '地区',
      'ru': 'Регионы',
      'hi': 'क्षेत्र'
    },
    'region': {
      'en': 'Region',
      'fr': 'Région',
      'es': 'Región',
      'ar': 'منطقة',
      'zh': '地区',
      'ru': 'Регион',
      'hi': 'क्षेत्र'
    },
    'districts': {
      'en': 'Districts',
      'fr': 'Districts',
      'es': 'Distritos',
      'ar': 'أحياء',
      'zh': '区',
      'ru': 'Районы',
      'hi': 'जिले'
    },
    'district': {
      'en': 'District',
      'fr': 'District',
      'es': 'Distrito',
      'ar': 'حي',
      'zh': '区',
      'ru': 'Район',
      'hi': 'जिला'
    },
    'villages': {
      'en': 'Villages',
      'fr': 'Villages',
      'es': 'Pueblos',
      'ar': 'قرى',
      'zh': '村庄',
      'ru': 'Деревни',
      'hi': 'गांव'
    },
    'village': {
      'en': 'Village',
      'fr': 'Village',
      'es': 'Pueblo',
      'ar': 'قرية',
      'zh': '村庄',
      'ru': 'Деревня',
      'hi': 'गांव'
    },
    'cities': {
      'en': 'Cities',
      'fr': 'Villes',
      'es': 'Ciudades',
      'ar': 'مدن',
      'zh': '城市',
      'ru': 'Города',
      'hi': 'शहर'
    },
    'city': {
      'en': 'City',
      'fr': 'Ville',
      'es': 'Ciudad',
      'ar': 'مدينة',
      'zh': '城市',
      'ru': 'Город',
      'hi': 'शहर'
    },
    'towns': {
      'en': 'Towns',
      'fr': 'Villes',
      'es': 'Pueblos',
      'ar': 'بلدات',
      'zh': '城镇',
      'ru': 'Города',
      'hi': 'कस्बे'
    },
    'town': {
      'en': 'Town',
      'fr': 'Ville',
      'es': 'Pueblo',
      'ar': 'بلدة',
      'zh': '城镇',
      'ru': 'Город',
      'hi': 'कस्बा'
    },
    'national society': {
      'en': 'National Society',
      'fr': 'Société Nationale',
      'es': 'Sociedad Nacional',
      'ar': 'الجمعية الوطنية',
      'zh': '国家红会',
      'ru': 'Национальное Общество',
      'hi': 'राष्ट्रीय सोसायटी'
    },
    'national societies': {
      'en': 'National Societies',
      'fr': 'Sociétés Nationales',
      'es': 'Sociedades Nacionales',
      'ar': 'الجمعيات الوطنية',
      'zh': '国家红会',
      'ru': 'Национальные Общества',
      'hi': 'राष्ट्रीय सोसायटी'
    },
    'society': {
      'en': 'Society',
      'fr': 'Société',
      'es': 'Sociedad',
      'ar': 'جمعية',
      'zh': '红会',
      'ru': 'Общество',
      'hi': 'सोसायटी'
    },
    'societies': {
      'en': 'Societies',
      'fr': 'Sociétés',
      'es': 'Sociedades',
      'ar': 'جمعيات',
      'zh': '红会',
      'ru': 'Общества',
      'hi': 'सोसायटी'
    },
    'red cross': {
      'en': 'Red Cross',
      'fr': 'Croix-Rouge',
      'es': 'Cruz Roja',
      'ar': 'الصليب الأحمر',
      'zh': '红十字会',
      'ru': 'Красный Крест',
      'hi': 'रेड क्रॉस'
    },
    'red crescent': {
      'en': 'Red Crescent',
      'fr': 'Croissant-Rouge',
      'es': 'Media Luna Roja',
      'ar': 'الهلال الأحمر',
      'zh': '红新月会',
      'ru': 'Красный Полумесяц',
      'hi': 'रेड क्रिसेंट'
    },
    'red crystal': {
      'en': 'Red Crystal',
      'fr': 'Cristal Rouge',
      'es': 'Cristal Rojo',
      'ar': 'البلورة الحمراء',
      'zh': '红水晶',
      'ru': 'Красный Кристалл',
      'hi': 'रेड क्रिस्टल'
    },
    'staff': {
      'en': 'Staff',
      'fr': 'Personnel',
      'es': 'Personal',
      'ar': 'موظفين',
      'zh': '工作人员',
      'ru': 'Персонал',
      'hi': 'कर्मचारी'
    },
    'staff members': {
      'en': 'Staff Members',
      'fr': 'Membres du Personnel',
      'es': 'Miembros del Personal',
      'ar': 'أعضاء الموظفين',
      'zh': '工作人员',
      'ru': 'Члены Персонала',
      'hi': 'कर्मचारी सदस्य'
    },
    'personnel': {
      'en': 'Personnel',
      'fr': 'Personnel',
      'es': 'Personal',
      'ar': 'موظفين',
      'zh': '人员',
      'ru': 'Персонал',
      'hi': 'कर्मचारी'
    },
    'employees': {
      'en': 'Employees',
      'fr': 'Employés',
      'es': 'Empleados',
      'ar': 'موظفين',
      'zh': '员工',
      'ru': 'Сотрудники',
      'hi': 'कर्मचारी'
    },
    'employee': {
      'en': 'Employee',
      'fr': 'Employé',
      'es': 'Empleado',
      'ar': 'موظف',
      'zh': '员工',
      'ru': 'Сотрудник',
      'hi': 'कर्मचारी'
    },
    'workers': {
      'en': 'Workers',
      'fr': 'Travailleurs',
      'es': 'Trabajadores',
      'ar': 'عمال',
      'zh': '工人',
      'ru': 'Работники',
      'hi': 'कार्यकर्ता'
    },
    'worker': {
      'en': 'Worker',
      'fr': 'Travailleur',
      'es': 'Trabajador',
      'ar': 'عامل',
      'zh': '工人',
      'ru': 'Работник',
      'hi': 'कार्यकर्ता'
    },
    'volunteers': {
      'en': 'Volunteers',
      'fr': 'Bénévoles',
      'es': 'Voluntarios',
      'ar': 'متطوعين',
      'zh': '志愿者',
      'ru': 'Волонтеры',
      'hi': 'स्वयंसेवक'
    },
    'volunteer': {
      'en': 'Volunteer',
      'fr': 'Bénévole',
      'es': 'Voluntario',
      'ar': 'متطوع',
      'zh': '志愿者',
      'ru': 'Волонтер',
      'hi': 'स्वयंसेवक'
    },
    'members': {
      'en': 'Members',
      'fr': 'Membres',
      'es': 'Miembros',
      'ar': 'أعضاء',
      'zh': '成员',
      'ru': 'Члены',
      'hi': 'सदस्य'
    },
    'member': {
      'en': 'Member',
      'fr': 'Membre',
      'es': 'Miembro',
      'ar': 'عضو',
      'zh': '成员',
      'ru': 'Член',
      'hi': 'सदस्य'
    },
    'participants': {
      'en': 'Participants',
      'fr': 'Participants',
      'es': 'Participantes',
      'ar': 'مشاركين',
      'zh': '参与者',
      'ru': 'Участники',
      'hi': 'प्रतिभागी'
    },
    'participant': {
      'en': 'Participant',
      'fr': 'Participant',
      'es': 'Participante',
      'ar': 'مشارك',
      'zh': '参与者',
      'ru': 'Участник',
      'hi': 'प्रतिभागी'
    },
    'beneficiaries': {
      'en': 'Beneficiaries',
      'fr': 'Bénéficiaires',
      'es': 'Beneficiarios',
      'ar': 'مستفيدين',
      'zh': '受益人',
      'ru': 'Бенефициары',
      'hi': 'लाभार्थी'
    },
    'beneficiary': {
      'en': 'Beneficiary',
      'fr': 'Bénéficiaire',
      'es': 'Beneficiario',
      'ar': 'مستفيد',
      'zh': '受益人',
      'ru': 'Бенефициар',
      'hi': 'लाभार्थी'
    },
    'recipients': {
      'en': 'Recipients',
      'fr': 'Destinataires',
      'es': 'Destinatarios',
      'ar': 'مستلمين',
      'zh': '接收者',
      'ru': 'Получатели',
      'hi': 'प्राप्तकर्ता'
    },
    'recipient': {
      'en': 'Recipient',
      'fr': 'Destinataire',
      'es': 'Destinatario',
      'ar': 'مستلم',
      'zh': '接收者',
      'ru': 'Получатель',
      'hi': 'प्राप्तकर्ता'
    },
    'trainees': {
      'en': 'Trainees',
      'fr': 'Stagiaires',
      'es': 'Practicantes',
      'ar': 'متدربين',
      'zh': '学员',
      'ru': 'Стажеры',
      'hi': 'प्रशिक्षु'
    },
    'trainee': {
      'en': 'Trainee',
      'fr': 'Stagiaire',
      'es': 'Practicante',
      'ar': 'متدرب',
      'zh': '学员',
      'ru': 'Стажер',
      'hi': 'प्रशिक्षु'
    },
    'students': {
      'en': 'Students',
      'fr': 'Étudiants',
      'es': 'Estudiantes',
      'ar': 'طلاب',
      'zh': '学生',
      'ru': 'Студенты',
      'hi': 'छात्र'
    },
    'student': {
      'en': 'Student',
      'fr': 'Étudiant',
      'es': 'Estudiante',
      'ar': 'طالب',
      'zh': '学生',
      'ru': 'Студент',
      'hi': 'छात्र'
    },
    'professionals': {
      'en': 'Professionals',
      'fr': 'Professionnels',
      'es': 'Profesionales',
      'ar': 'مهنيين',
      'zh': '专业人员',
      'ru': 'Профессионалы',
      'hi': 'पेशेवर'
    },
    'professional': {
      'en': 'Professional',
      'fr': 'Professionnel',
      'es': 'Profesional',
      'ar': 'مهني',
      'zh': '专业人员',
      'ru': 'Профессионал',
      'hi': 'पेशेवर'
    },
    'specialists': {
      'en': 'Specialists',
      'fr': 'Spécialistes',
      'es': 'Especialistas',
      'ar': 'متخصصين',
      'zh': '专家',
      'ru': 'Специалисты',
      'hi': 'विशेषज्ञ'
    },
    'specialist': {
      'en': 'Specialist',
      'fr': 'Spécialiste',
      'es': 'Especialista',
      'ar': 'متخصص',
      'zh': '专家',
      'ru': 'Специалист',
      'hi': 'विशेषज्ञ'
    },
    'experts': {
      'en': 'Experts',
      'fr': 'Experts',
      'es': 'Expertos',
      'ar': 'خبراء',
      'zh': '专家',
      'ru': 'Эксперты',
      'hi': 'विशेषज्ञ'
    },
    'expert': {
      'en': 'Expert',
      'fr': 'Expert',
      'es': 'Experto',
      'ar': 'خبير',
      'zh': '专家',
      'ru': 'Эксперт',
      'hi': 'विशेषज्ञ'
    },
    'instructors': {
      'en': 'Instructors',
      'fr': 'Instructeurs',
      'es': 'Instructores',
      'ar': 'مدربين',
      'zh': '指导员',
      'ru': 'Инструкторы',
      'hi': 'प्रशिक्षक'
    },
    'instructor': {
      'en': 'Instructor',
      'fr': 'Instructeur',
      'es': 'Instructor',
      'ar': 'مدرب',
      'zh': '指导员',
      'ru': 'Инструктор',
      'hi': 'प्रशिक्षक'
    },
    'trainers': {
      'en': 'Trainers',
      'fr': 'Formateurs',
      'es': 'Entrenadores',
      'ar': 'مدربين',
      'zh': '培训师',
      'ru': 'Тренеры',
      'hi': 'प्रशिक्षक'
    },
    'trainer': {
      'en': 'Trainer',
      'fr': 'Formateur',
      'es': 'Entrenador',
      'ar': 'مدرب',
      'zh': '培训师',
      'ru': 'Тренер',
      'hi': 'प्रशिक्षक'
    },
    'coordinators': {
      'en': 'Coordinators',
      'fr': 'Coordinateurs',
      'es': 'Coordinadores',
      'ar': 'منسقين',
      'zh': '协调员',
      'ru': 'Координаторы',
      'hi': 'समन्वयक'
    },
    'coordinator': {
      'en': 'Coordinator',
      'fr': 'Coordinateur',
      'es': 'Coordinador',
      'ar': 'منسق',
      'zh': '协调员',
      'ru': 'Координатор',
      'hi': 'समन्वयक'
    },
    'managers': {
      'en': 'Managers',
      'fr': 'Gestionnaires',
      'es': 'Gerentes',
      'ar': 'مديرين',
      'zh': '经理',
      'ru': 'Менеджеры',
      'hi': 'प्रबंधक'
    },
    'manager': {
      'en': 'Manager',
      'fr': 'Gestionnaire',
      'es': 'Gerente',
      'ar': 'مدير',
      'zh': '经理',
      'ru': 'Менеджер',
      'hi': 'प्रबंधक'
    },
    'leaders': {
      'en': 'Leaders',
      'fr': 'Dirigeants',
      'es': 'Líderes',
      'ar': 'قادة',
      'zh': '领导',
      'ru': 'Лидеры',
      'hi': 'नेता'
    },
    'leader': {
      'en': 'Leader',
      'fr': 'Dirigeant',
      'es': 'Líder',
      'ar': 'قائد',
      'zh': '领导',
      'ru': 'Лидер',
      'hi': 'नेता'
    }
  };

  const unitKey = unit.toLowerCase().trim();

  // Try exact match first
  if (unitTranslations[unitKey] && unitTranslations[unitKey][locale]) {
    return unitTranslations[unitKey][locale];
  }

  // Try common variations and abbreviations
  const variations = {
    'person': 'people',
    'individual': 'people',
    'individuals': 'people',
    'family': 'families',
    'household': 'households',
    'child': 'children',
    'kid': 'children',
    'kids': 'children',
    'woman': 'women',
    'man': 'men',
    'day': 'days',
    'week': 'weeks',
    'month': 'months',
    'year': 'years',
    'hour': 'hours',
    'minute': 'minutes',
    'min': 'minutes',
    'meter': 'meters',
    'm': 'meters',
    'kilometer': 'kilometers',
    'km': 'kilometers',
    'gram': 'grams',
    'g': 'grams',
    'ton': 'tons',
    'dollar': 'dollars',
    'usd': 'dollars',
    '$': 'dollars',
    'euro': 'euros',
    'eur': 'euros',
    '€': 'euros',
    'unit': 'units',
    'litre': 'liters',
    'l': 'liters',
    'pound': 'kg',
    'lb': 'kg',
    'lbs': 'kg',
    'pc': 'percent',
    'pct': 'percent',
    'pcnt': 'percent',
    'nation': 'nations',
    'country': 'countries',
    'fund': 'funds',
    'metric': 'metrics',
    'indicator': 'indicators',
    'organization': 'organizations',
    'org': 'organizations',
    'agency': 'agencies',
    'project': 'projects',
    'program': 'programs',
    'prog': 'programs',
    'activity': 'activities',
    'event': 'events',
    'session': 'sessions',
    'meeting': 'meetings',
    'report': 'reports',
    'document': 'documents',
    'doc': 'documents',
    'case': 'cases',
    'instance': 'instances',
    'item': 'items',
    'record': 'records',
    'entry': 'entries',
    'sample': 'samples',
    'category': 'categories',
    'cat': 'categories',
    'type': 'types',
    'group': 'groups',
    'team': 'teams',
    'center': 'centers',
    'centre': 'centers',
    'facility': 'facilities',
    'site': 'sites',
    'location': 'locations',
    'loc': 'locations',
    'area': 'areas',
    'region': 'regions',
    'district': 'districts',
    'village': 'villages',
    'city': 'cities',
    'town': 'towns',
    'ns': 'national societies',
    'national society': 'national societies',
    'staff member': 'staff members',
    'personnel': 'staff',
    'employee': 'employees',
    'worker': 'workers',
    'volunteer': 'volunteers',
    'member': 'members',
    'participant': 'participants',
    'beneficiary': 'beneficiaries',
    'recipient': 'recipients',
    'trainee': 'trainees',
    'student': 'students',
    'professional': 'professionals',
    'specialist': 'specialists',
    'expert': 'experts',
    'instructor': 'instructors',
    'trainer': 'trainers',
    'coordinator': 'coordinators',
    'manager': 'managers',
    'leader': 'leaders'
  };

  if (variations[unitKey] && unitTranslations[variations[unitKey]] && unitTranslations[variations[unitKey]][locale]) {
    return unitTranslations[variations[unitKey]][locale];
  }

LEGACY_UNIT_TRANSLATIONS_REMOVED_END */

/**
 * Fetches indicator data for the global overview map.
 * @param {number} indicatorId - The indicator bank ID to filter by.
 * @param {string} periodName - Optional period name filter (e.g., "2023", "FY2023", "Q1 2024").
 * @returns {Promise<Object>} A promise that resolves to the processed indicator data.
 * @throws {Error} If the network response is not ok.
 */
export async function getIndicatorData(indicatorId, periodName = null, options = {}) {

  // Build URL with optional period filter and server-side indicator filter
  // Use /data/tables endpoint for better performance (includes related tables)
  const { countryIso2 = null, countryIso3 = null, perPage = 20000 } = options || {};

  // Resolve ISO codes to country_id if needed (since /data/tables uses country_id, not ISO codes)
  let countryId = null;
  if (countryIso3 || countryIso2) {
    try {
      const countries = await getCountriesList();
      const country = countries.find(c => {
        if (countryIso3) {
          return c.iso3 && c.iso3.toUpperCase() === countryIso3.toUpperCase();
        }
        if (countryIso2) {
          return c.iso2 && c.iso2.toUpperCase() === countryIso2.toUpperCase();
        }
        return false;
      });
      if (country) {
        countryId = country.id;
      }
    } catch (error) {
      console.warn('Failed to resolve ISO code to country_id:', error);
    }
  }

  // Use getDataWithRelated() to leverage local data store and unified endpoint
  const filters = {
    template_id: FDRS_TEMPLATE_ID,
    perPage,
    period_name: periodName || undefined,
    indicator_bank_id: indicatorId,
    country_id: countryId || undefined,
    country_iso2: countryIso2 || undefined,
    country_iso3: countryIso3 || undefined,
    disagg: true,
    related: 'all',
    returnFullResponse: false // Get just the data array
  };

  // Remove undefined filters
  Object.keys(filters).forEach(key =>
    filters[key] === undefined && delete filters[key]
  );

  console.log(`Fetching indicator data using getDataWithRelated with filters:`, filters);

  try {
    // Use getDataWithRelated which will use local store if available
    const dataArray = await getDataWithRelated(filters);

    console.log(`getDataWithRelated returned:`, {
      isArray: Array.isArray(dataArray),
      length: Array.isArray(dataArray) ? dataArray.length : (dataArray?.data?.length || 0),
      type: typeof dataArray,
      keys: Array.isArray(dataArray) ? 'array' : Object.keys(dataArray || {}),
      sample: Array.isArray(dataArray) ? dataArray[0] : (dataArray?.data?.[0] || null)
    });

    // Handle both array and object responses
    const dataResult = Array.isArray(dataArray)
      ? { data: dataArray }
      : (dataArray?.data ? dataArray : { data: [] });

    if (!dataResult || !dataResult.data || dataResult.data.length === 0) {
      console.warn('No data found in database. Filters:', filters);
      console.warn('Data result:', dataResult);
      return { processedData: {}, globalTotal: 0 };
    }

    console.log(`Total data items received: ${dataResult.data.length}`);

    // Data already filtered server-side by indicator_bank_id when supported
    const filteredData = Array.isArray(dataResult.data) ? dataResult.data : [];

  console.log(`Filtered data for indicator ${indicatorId}:`, filteredData);
  console.log(`Number of matching items: ${filteredData.length}`);

  if (filteredData.length === 0) {
    console.warn(`No data found for indicator bank ID: ${indicatorId}`);
    return { processedData: {}, globalTotal: 0 };
  }

  // Load countries table to resolve country_id to ISO codes
  let countriesMap = null;
  try {
    const countries = await getCountriesList();
    if (countries && Array.isArray(countries)) {
      countriesMap = new Map();
      countries.forEach(c => {
        if (c.id && c.iso2) {
          countriesMap.set(c.id, { iso2: c.iso2.toUpperCase(), iso3: c.iso3?.toUpperCase(), name: c.name });
        }
      });
      console.log(`Loaded ${countriesMap.size} countries for country_id resolution`);
    }
  } catch (error) {
    console.warn('Failed to load countries for country_id resolution:', error);
  }

  // Process the filtered data
  const processedData = {};
  let globalTotal = 0;

  console.log(`Processing ${filteredData.length} items for indicator ${indicatorId}`);

  filteredData.forEach(item => {
    // Try multiple ways to get country code
    // First, try country_id lookup in countries map
    let countryCode = null;
    let countryName = null;

    if (item.country_id && countriesMap) {
      const country = countriesMap.get(item.country_id);
      if (country) {
        countryCode = country.iso2;
        countryName = country.name;
      }
    }

    // Fallback to direct ISO codes (for API responses that might have hydrated data)
    if (!countryCode) {
      const iso2 = (item?.country_info?.iso2 || item?.iso2 || item?.country_iso2 || '').toUpperCase();
      const iso3 = (item?.country_info?.iso3 || item?.iso3 || item?.country_iso3 || '').toUpperCase();

      if (item?.country_info?.iso2) {
        countryCode = item.country_info.iso2.toUpperCase();
        countryName = item.country_info.name;
      } else if (iso2 && iso2.length === 2) {
        countryCode = iso2;
      } else if (item?.country_info?.iso3) {
        countryCode = item.country_info.iso3.toUpperCase();
        countryName = item.country_info.name;
      } else if (iso3 && iso3.length === 3) {
        countryCode = iso3.toUpperCase();
      }
    }

    const av = item?.answer_value != null ? item.answer_value : (item?.value || item?.num_value);

    if (countryCode && av != null) {
        // Handle different answer_value formats
        let numericValue = 0;

        if (av && typeof av === 'object' && av.values) {
          // Format: { mode: "total", values: { total: 123889 } }
          numericValue = parseFloat(av.values.total) || 0;
        } else if (av && typeof av === 'object' && av.total) {
          // Format: { total: 123889 }
          numericValue = parseFloat(av.total) || 0;
        } else {
          // Format: simple number or string
          numericValue = parseFloat(av) || 0;
        }

        // Initialize country data if it doesn't exist
        if (!processedData[countryCode]) {
          processedData[countryCode] = {
            name: countryName || item?.country_info?.name || item?.country_name || countryCode,
            value: numericValue, // Add value field for map component
            volunteers: 0,
            staff: 0,
            branches: 0,
            localUnits: 0,
            bloodDonors: 0,
            firstAid: 0,
            peopleReached: 0,
            income: 0,
            expenditure: 0
          };
        } else {
          // Aggregate values if country already exists (multiple records per country)
          processedData[countryCode].value += numericValue;
        }

        // Set the rawValue (for backward compatibility)
        processedData[countryCode].rawValue = processedData[countryCode].value;
        globalTotal += numericValue;
      }
  });

  console.log(`Processed data for ${Object.keys(processedData).length} countries, globalTotal: ${globalTotal}`);
  if (Object.keys(processedData).length > 0) {
    console.log(`Sample processed data:`, Object.entries(processedData).slice(0, 3));
  } else {
    console.warn('No countries processed! Sample item structure:', filteredData[0]);
  }

  return { processedData, globalTotal };
  } catch (error) {
    console.error('Error in getIndicatorData:', error);
    throw error;
  }
}

/**
 * Fetch a country's indicator timeseries in one call by iterating periods client-side,
 * using server-side indicator filtering and country filter to minimize payload.
 * Results are cached per (iso3, indicatorId) for 15 minutes.
 */
export async function getCountryIndicatorTimeseries(iso2, iso3, indicatorId) {
  if (!iso2 && !iso3) return [];

  const cacheKey = `timeseries:${(iso3 || iso2 || '').toUpperCase()}:${indicatorId}`;
  const cache = getCountryIndicatorTimeseries._cache || (getCountryIndicatorTimeseries._cache = new Map());
  const cached = cache.get(cacheKey);
  if (cached && (Date.now() - cached.ts) < 15 * 60 * 1000) {
    return cached.value;
  }

  // Resolve ISO codes to country_id if needed
  let countryId = null;
  if (iso3 || iso2) {
    try {
      const countries = await getCountriesList();
      const country = countries.find(c => {
        if (iso3) return c.iso3 && c.iso3.toUpperCase() === iso3.toUpperCase();
        if (iso2) return c.iso2 && c.iso2.toUpperCase() === iso2.toUpperCase();
        return false;
      });
      if (country) countryId = country.id;
    } catch (error) {
      console.warn('Failed to resolve ISO code to country_id:', error);
    }
  }

  const periods = await getAvailablePeriods(FDRS_TEMPLATE_ID);
  const sorted = periods
    .slice()
    .sort((a, b) => {
      const ya = extractYearFromPeriod(a);
      const yb = extractYearFromPeriod(b);
      if (ya !== yb) return ya - yb;
      // Tie-break lexically to keep stable order when years are equal or missing
      return String(a).localeCompare(String(b));
    });
  const results = [];

  // Batch requests in small parallel groups to reduce total time while avoiding overload
  const batchSize = 4;
  for (let i = 0; i < sorted.length; i += batchSize) {
    const batch = sorted.slice(i, i + batchSize);
    const batchPromises = batch.map(async (year) => {
        try {
          // Try to use stored data first via getDataWithRelated (which uses local data store)
          let data = [];
          try {
            // Use ISO codes since dataStore filters by ISO codes, not country_id
            const filters = {
              template_id: FDRS_TEMPLATE_ID,
              period_name: year,
              indicator_bank_id: indicatorId,
              disagg: true,
              related: 'none' // We only need data for timeseries
            };

            // Add ISO filters if available (dataStore uses these)
            if (iso3) filters.country_iso3 = iso3;
            else if (iso2) filters.country_iso2 = iso2;

            data = await getDataWithRelated(filters);
            data = Array.isArray(data) ? data : [];
        } catch (storeError) {
          // Fallback to direct API call if getDataWithRelated fails
          console.warn(`Failed to get data from store for ${year}, using API:`, storeError.message);
          const url = buildDataTablesApiUrl({
            templateId: FDRS_TEMPLATE_ID,
            perPage: 2000,
            periodName: year,
            indicatorBankId: indicatorId,
            countryId: countryId,
            countryIso3: iso3 || null,
            countryIso2: iso2 || null,
            disagg: true,
            related: 'none'
          });
          const resp = await fetch(url);
          if (!resp.ok) return { year, value: 0 };
          const json = await resp.json();
          data = Array.isArray(json.data) ? json.data : [];
        }

        if (!data.length) return { year, value: 0 };
        // Aggregate all entries for the year to produce a single value
        let sum = 0;
        for (const item of data) {
          const av = (item && (item.answer_value != null ? item.answer_value : item.value));
          if (av && typeof av === 'object') {
            if (av.values && av.values.total != null) sum += parseFloat(av.values.total) || 0;
            else if (av.total != null) sum += parseFloat(av.total) || 0;
          } else {
            sum += parseFloat(av) || 0;
          }
        }
        return { year, value: sum };
      } catch (_e) {
        return { year, value: 0 };
      }
    });
    const batchResults = await Promise.all(batchPromises);
    results.push(...batchResults);
  }

  const filtered = results.filter(r => r.value > 0).sort((a, b) => parseInt(a.year) - parseInt(b.year));
  cache.set(cacheKey, { value: filtered, ts: Date.now() });
  return filtered;
}

/**
 * Fetches available periods/years from the data API.
 * @returns {Promise<Array>} A promise that resolves to an array of available periods.
 * @throws {Error} If the network response is not ok.
 */
export async function getAvailablePeriods(templateId = null) {
  // Try to use local data store first
  const USE_LOCAL_STORE = process.env.NEXT_PUBLIC_USE_LOCAL_STORE !== 'false';
  const FORCE_API = process.env.NEXT_PUBLIC_FORCE_API === 'true';

  if (USE_LOCAL_STORE && !FORCE_API) {
    try {
      // Extract periods from stored data
      if (typeof window === 'undefined') {
        // Server-side: read from data store
        const { getDataFromStore } = await import('./dataStore');
        const data = await getDataFromStore({ template_id: templateId || FDRS_TEMPLATE_ID });

        // Extract unique period names
        const periods = [...new Set(data.map(item => item.period_name).filter(Boolean))].sort().reverse();
        if (periods.length > 0) {
          return periods;
        }
      } else {
        // Client-side: use API route
        try {
          const params = new URLSearchParams();
          if (templateId) params.append('template_id', templateId);
          const response = await fetch(`/api/periods?${params.toString()}`);
          if (response.ok) {
            const periods = await response.json();
            if (Array.isArray(periods) && periods.length > 0) {
              return periods;
            }
          }
        } catch (error) {
          console.warn('Failed to get periods from API route, falling back to direct API:', error);
        }
      }
    } catch (error) {
      console.warn('Local store error for periods, falling back to API:', error.message);
    }
  }

  // Fallback to direct API call
  try {
    // Create cache key that includes template_id for proper caching
    const cacheKey = templateId ? `periods_${templateId}` : 'periods_all';

    // In-memory cache
    if (getAvailablePeriods._cache && getAvailablePeriods._cache[cacheKey] && Array.isArray(getAvailablePeriods._cache[cacheKey].value) && (Date.now() - getAvailablePeriods._cache[cacheKey].ts) < 24 * 60 * 60 * 1000) {
      return getAvailablePeriods._cache[cacheKey].value;
    }

    // localStorage cache (per backend base URL and template)
    const storageKey = `periods:${API_BASE_URL}:${templateId || 'all'}`;
    if (typeof window !== 'undefined') {
      try {
        const raw = window.localStorage.getItem(storageKey);
        if (raw) {
          const parsed = JSON.parse(raw);
          if (parsed && Array.isArray(parsed.value) && (Date.now() - parsed.ts) < 24 * 60 * 60 * 1000) {
            if (!getAvailablePeriods._cache) getAvailablePeriods._cache = {};
            getAvailablePeriods._cache[cacheKey] = { value: parsed.value, ts: parsed.ts };
            return parsed.value;
          }
        }
      } catch (_e) {}
    }

  // Single proxy for all Backoffice endpoints (browser → /api/backoffice/*, server → direct)
  const periodsParams = templateId != null ? { template_id: String(templateId) } : {};
  const periodsUrl = getBackofficeApiUrl('periods', periodsParams);

  const periods = await fetchJsonWithCache(periodsUrl, { ttlMs: 24 * 60 * 60 * 1000, init: { signal: AbortSignal.timeout(15000) } });

    if (!Array.isArray(periods)) {
      console.warn('Invalid periods response, using fallback');
      // Fall through to fallback logic below
      throw new Error('Invalid periods response');
    }

    // Cache in-memory and in localStorage
    if (!getAvailablePeriods._cache) getAvailablePeriods._cache = {};
    getAvailablePeriods._cache[cacheKey] = { value: periods, ts: Date.now() };
    if (typeof window !== 'undefined') {
      try { window.localStorage.setItem(storageKey, JSON.stringify(getAvailablePeriods._cache[cacheKey])); } catch (_e) {}
    }
    return periods;
  } catch (error) {
    const periodsDetail = {
      message: error.message,
      name: error.name,
      stack: error.stack,
      templateId,
      url: `${API_BASE_URL}/api/v1/periods${templateId != null ? `?template_id=${templateId}` : ''}`,
      API_BASE_URL,
      isServer: typeof window === 'undefined'
    };
    console.error('[apiService] getAvailablePeriods error (full detail):', JSON.stringify(periodsDetail, null, 2));

    // Fallback: last known storage cache
    const storageKey = `periods:${API_BASE_URL}:${templateId || 'all'}`;
    if (typeof window !== 'undefined') {
      try {
        const raw = window.localStorage.getItem(storageKey);
        if (raw) {
          const parsed = JSON.parse(raw);
          if (parsed && Array.isArray(parsed.value)) {
            return parsed.value;
          }
        }
      } catch (_e) {}
    }

    // Try to extract from local store as last resort
    if (USE_LOCAL_STORE && !FORCE_API) {
      try {
        if (typeof window === 'undefined') {
          const { getDataFromStore } = await import('./dataStore');
          const data = await getDataFromStore({ template_id: templateId || FDRS_TEMPLATE_ID });
          const periods = [...new Set(data.map(item => item.period_name).filter(Boolean))].sort().reverse();
          if (periods.length > 0) {
            console.log('Using periods extracted from local data store (fallback)');
            return periods;
          }
        } else {
          // Try API route as fallback
          try {
            const params = new URLSearchParams();
            if (templateId) params.append('template_id', templateId);
            const response = await fetch(`/api/periods?${params.toString()}`);
            if (response.ok) {
              const periods = await response.json();
              if (Array.isArray(periods) && periods.length > 0) {
                console.log('Using periods from API route (fallback)');
                return periods;
              }
            }
          } catch (_e) {}
        }
      } catch (storeError) {
        console.warn('Failed to extract periods from local store:', storeError);
      }
    }

    // Final fallback: return default years
    console.warn('Using default fallback periods');
    return ['2024', '2023', '2022', '2021', '2020'];
  }
}

/**
 * Extracts year from period name.
 * @param {string} periodName - The period name (e.g., "2023", "FY2023", "Q1 2024").
 * @returns {number} The extracted year.
 */
function extractYearFromPeriod(periodName) {
  if (!periodName) return 0;

  // Try to extract year from various formats
  const yearMatch = periodName.match(/\b(20\d{2})\b/);
  if (yearMatch) {
    return parseInt(yearMatch[1]);
  }

  // If no year found, try to parse as number
  const numMatch = periodName.match(/\b(\d{4})\b/);
  if (numMatch) {
    return parseInt(numMatch[1]);
  }

  return 0;
}

/**
 * Fetch submitted documents by country
 * @param {number} countryId - Country ID to filter by
 * @param {string} documentType - Document type to filter by (optional)
 * @param {string} language - Language code for filtering (optional)
 * @param {boolean} isPublic - Filter by public status (default: true)
 * @param {string} status - Filter by approval status (default: 'approved')
 * @param {number} page - Page number (default: 1)
 * @param {number} perPage - Items per page (default: 20)
 * @returns {Promise<Object>} - Submitted documents data
 */
export async function getSubmittedDocuments(countryId, documentType = '', language = 'en', isPublic = true, status = 'approved', page = 1, perPage = 20) {
  // Try to use local data store first
  const USE_LOCAL_STORE = process.env.NEXT_PUBLIC_USE_LOCAL_STORE !== 'false';
  const FORCE_API = process.env.NEXT_PUBLIC_FORCE_API === 'true';

  if (USE_LOCAL_STORE && !FORCE_API) {
    try {
      if (typeof window === 'undefined') {
        // Server-side: try to get from local store
        const { getSubmittedDocumentsFromStore } = await import('./dataStore');
        const storeResult = await getSubmittedDocumentsFromStore({
          country_id: countryId,
          document_type: documentType,
          language: language && language.trim() !== '' && documentType !== 'Cover Image' ? language : undefined,
          is_public: isPublic,
          status: status,
          page: page,
          per_page: perPage
        });

        console.log(`[getSubmittedDocuments] Local store returned ${storeResult?.documents?.length || 0} documents`);

        // If store file doesn't exist (_storeUnavailable flag), fall back to API
        // Otherwise, return result even if empty (empty means no documents exist, not an error)
        if (storeResult && !storeResult._storeUnavailable) {
          return storeResult;
        }

        if (storeResult?._storeUnavailable) {
          console.log('[getSubmittedDocuments] Store file not available, falling back to API');
        } else {
          console.log('[getSubmittedDocuments] Local store returned null/undefined, falling back to API');
        }
      } else {
        // Client-side: use API route (which uses stored data server-side)
        try {
          const params = new URLSearchParams();
          params.append('page', page.toString());
          params.append('per_page', perPage.toString());
          if (countryId) params.append('country_id', countryId.toString());
          if (documentType) params.append('document_type', documentType);
          if (language && language.trim() !== '' && documentType !== 'Cover Image') {
            params.append('language', language);
          }
          params.append('is_public', isPublic.toString());
          params.append('status', status);

          console.log('[getSubmittedDocuments] Trying API route:', `/api/submitted-documents?${params.toString()}`);
          const response = await fetch(`/api/submitted-documents?${params.toString()}`);
          if (response.ok) {
            const result = await response.json();
            console.log(`[getSubmittedDocuments] API route returned ${result.documents?.length || 0} documents`);
            // Return result even if empty (store might be empty, which is valid)
            return result;
          } else {
            console.warn(`[getSubmittedDocuments] API route returned ${response.status}, falling back to direct API`);
          }
        } catch (apiRouteError) {
          console.warn('[getSubmittedDocuments] API route error, falling back to direct API:', apiRouteError.message);
        }
      }
    } catch (storeError) {
      console.warn('[getSubmittedDocuments] Local store error, falling back to API:', storeError.message);
    }
  }

  try {
    // Use configured API base and key (works in dev, build, and production)
    // Reduce noisy logging in production
    if (process.env.NODE_ENV === 'development') {
      console.log('getSubmittedDocuments called with:', { countryId, documentType, language, isPublic, status, page, perPage });
      console.log('API_BASE_URL:', API_BASE_URL);
      console.log('API_KEY set:', !!API_KEY);
    }

    const params = new URLSearchParams({
      page: page.toString(),
      per_page: perPage.toString(),
      is_public: isPublic.toString(),
      status: status
    });

    if (countryId) params.append('country_id', countryId.toString());
    if (documentType) params.append('document_type', documentType);
    // Only add language filter if it's not empty and not for cover images (which often have null language)
    if (language && language.trim() !== '' && documentType !== 'Cover Image') {
      params.append('language', language);
    }

    const url = `${API_BASE_URL}/api/v1/submitted-documents?${params}`;
    if (process.env.NODE_ENV === 'development') {
      console.log('Fetching URL:', url);
    }

    // Use retry logic for the API call (backend requires Authorization: Bearer <key>; no query param)
    const bearer = getBearerAuthHeader();
    const data = await retryApiCall(async () => {
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
          ...(bearer ? { 'Authorization': bearer } : {}),
        },
        signal: AbortSignal.timeout(30000), // 30 second timeout
      });

      if (!response.ok) {
        const body = await response.text().catch(() => '');
        console.error('[apiService] submitted-documents HTTP error:', response.status, response.statusText, 'URL:', url, 'Body:', body?.slice(0, 500));
        throw new Error(`HTTP error! status: ${response.status} ${response.statusText} ${body?.slice(0, 200)}`);
      }

      return await response.json();
    }, 2, 2000); // 2 retries with 2 second delay

    if (process.env.NODE_ENV === 'development') {
      console.log('API response:', data);
    }
    return data;
  } catch (error) {
    const detail = {
      message: error.message,
      name: error.name,
      stack: error.stack,
      url: `${API_BASE_URL}/api/v1/submitted-documents?...`,
      API_BASE_URL,
      sentAuth: !!getBearerAuthHeader(),
      isTimeout: error.name === 'TimeoutError' || error.message?.includes('timeout')
    };
    console.error('[apiService] getSubmittedDocuments error (full detail):', JSON.stringify(detail, null, 2));

    return {
      documents: [],
      total_items: 0,
      total_pages: 0,
      current_page: 1,
      per_page: perPage
    };
  }
}

/**
 * Fetch common words for tooltips
 * @param {string} language - Language code (e.g., 'en', 'fr', 'es', 'ar', 'zh', 'ru', 'hi')
 * @returns {Promise<Object>} - Common words data
 */
export async function getCommonWords(language = 'en') {
  // Try to use local data store first
  const USE_LOCAL_STORE = process.env.NEXT_PUBLIC_USE_LOCAL_STORE !== 'false';
  const FORCE_API = process.env.NEXT_PUBLIC_FORCE_API === 'true';

  if (USE_LOCAL_STORE && !FORCE_API) {
    try {
      if (typeof window === 'undefined') {
        // Server-side: use dataStore directly
        const { getCommonWordsFromStore } = await import('./dataStore');
        const data = await getCommonWordsFromStore(language);
        // Return data even if empty (allows app to continue without API)
        if (data && data.common_words) {
          if (data.common_words.length > 0) {
            console.log(`Using ${data.common_words.length} common words from local store (server-side)`);
          } else {
            console.log('No common words in local store, returning empty structure');
          }
          return data;
        }
        // If data is null/undefined, return empty structure
        return { success: false, common_words: [], total: 0 };
      } else {
        // Client-side: use API route
        try {
          const response = await fetch(`/api/common-words?language=${language}`);
          if (response.ok) {
            const data = await response.json();
            // Return data even if empty (allows app to continue)
            if (data && data.common_words) {
              if (data.common_words.length > 0) {
                console.log(`Using ${data.common_words.length} common words from API route (client-side)`);
              } else {
                console.log('No common words in local store, returning empty structure');
              }
              return data;
            }
          }
          // If response not ok or no data, return empty structure
          return { success: false, common_words: [], total: 0 };
        } catch (error) {
          console.warn('Failed to get common words from API route:', error);
          // Return empty structure instead of falling back to API
          return { success: false, common_words: [], total: 0 };
        }
      }
    } catch (error) {
      console.warn('Local store error for common words:', error.message);
      // Return empty structure instead of falling back to API
      return { success: false, common_words: [], total: 0 };
    }
  }

  // Fallback to direct API call only if local store is disabled
  try {
    const url = `${API_BASE_URL}/api/v1/common-words?language=${language}`;
    const data = await fetchJsonWithCache(url, { ttlMs: 12 * 60 * 60 * 1000 });
    return data;
  } catch (error) {
    console.error('Error fetching common words:', error);
    return { success: false, common_words: [], total: 0 };
  }
}

/**
 * Fetch latest available key figures for a country
 * @param {number} countryId - Country ID to filter by
 * @param {string} iso2 - Country ISO2 code for data lookup
 * @returns {Promise<Object>} - Key figures data with latest available values
 */
export async function getKeyFigures(countryId, iso2) {
  try {
    console.log('Fetching key figures for country:', { countryId, iso2 });

    // Key indicators mapping with their IDs
    const keyIndicators = {
      volunteers: { id: 724, name: 'Volunteers', unit: 'Volunteers' },
      staff: { id: 727, name: 'Staff', unit: 'Staff' },
      branches: { id: 1117, name: 'Branches', unit: 'Branches' },
      localUnits: { id: 723, name: 'Local Units', unit: 'Units' }
    };

    // Fetch timeseries for each indicator in parallel and take the latest non-zero
    const entries = Object.entries(keyIndicators);
    const seriesList = await Promise.all(entries.map(([_, indicator]) => getCountryIndicatorTimeseries(iso2, null, indicator.id)));

    const keyFigures = {};
    seriesList.forEach((series, idx) => {
      const [key, indicator] = entries[idx];
    const latest = (series || [])
      .slice()
      .sort((a, b) => {
        const ya = extractYearFromPeriod(a.year);
        const yb = extractYearFromPeriod(b.year);
        if (ya !== yb) return yb - ya;
        return String(b.year).localeCompare(String(a.year));
      })
      .find(p => p.value > 0) || { value: null, year: null };
      keyFigures[key] = {
        value: latest.value,
        year: latest.year,
        name: indicator.name,
        unit: indicator.unit
      };
    });

    console.log('Key figures result:', keyFigures);
    return keyFigures;

  } catch (error) {
    console.error('Error fetching key figures:', error);
    return {
      volunteers: { value: null, year: null, name: 'Volunteers', unit: 'Volunteers' },
      staff: { value: null, year: null, name: 'Staff', unit: 'Staff' },
      branches: { value: null, year: null, name: 'Branches', unit: 'Branches' },
      localUnits: { value: null, year: null, name: 'Local Units', unit: 'Units' }
    };
  }
}
