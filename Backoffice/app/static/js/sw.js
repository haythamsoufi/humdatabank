// Cache version - automatically set from ASSET_VERSION via server-side injection
// IMPORTANT: This is replaced server-side with the actual ASSET_VERSION value
// The server route (/sw.js) injects the version when serving this file
// This ensures users get fresh files after deployment. The old cache will be cleaned up automatically.
const CACHE_VERSION = 'ASSET_VERSION_PLACEHOLDER'; // Replaced server-side with actual ASSET_VERSION
const CACHE_NAME = `ifrc-forms-${CACHE_VERSION}`;

// Core assets to cache on service worker installation (keep this SMALL).
// Note: These paths don't need version query parameters because the cache name (CACHE_VERSION)
// changes when files are updated, which invalidates the entire cache automatically.
const CORE_ASSETS = [
  '/static/favicon.svg',
  '/static/IFRC_logo_horizontal.svg',
  '/static/IFRC_logo_square.svg',
  '/static/css/output.css',
  '/static/css/executive-header.css',
  '/static/css/components.css',
  '/static/css/chatbot.css',
  '/static/css/responsive.css',
  '/static/css/rtl.css',
  '/static/css/layout.css',
  '/static/libs/fontawesome-6.5.0.min.css',
  '/static/libs/select2.min.css',
  '/static/libs/jquery-3.7.1.min.js',
  '/static/libs/select2.min.js',
  '/static/js/lib/safe-dom.js',
  '/static/js/lib/action-router.js',
  '/static/js/layout.js',
  '/static/js/page-header-pin.js',
  '/static/js/confirm-dialogs.js',
  '/static/js/components.js',
  '/static/js/flash-messages.js',
  '/static/js/robot-personality.js',
  '/static/js/chatbot-messages.js',
  '/static/js/csrf.js',
  '/static/js/chatbot.js'
];

// Forms assets are relatively heavy; cache them ONLY when the user actually visits forms.
const FORMS_ASSETS = [
  '/static/css/forms.css',
  '/static/js/forms/entry-form.js',
  '/static/js/forms/main.js',
  '/static/js/forms/modules/pagination.js',
  '/static/js/forms/modules/matrix-handler.js',
  '/static/js/forms/modules/calculated-lists-runtime.js',
  '/static/js/forms/modules/conditions.js',
  '/static/js/forms/modules/debug.js',
  '/static/js/forms/modules/form-item-utils.js',
  '/static/js/forms/modules/ajax-save.js',
  '/static/js/forms/modules/form-validation.js',
  '/static/js/forms/modules/layout.js',
  '/static/js/forms/modules/field-management.js',
  '/static/js/forms/modules/section-renderer.js',
  '/static/js/forms/modules/dynamic-indicators.js',
  '/static/js/forms/modules/formatting.js',
  '/static/js/forms/modules/public-drafts.js',
  '/static/js/forms/modules/auth-drafts.js',
  '/static/js/forms/modules/presence.js',
  '/static/js/forms/modules/data-availability.js',
  '/static/js/forms/modules/checkbox-handlers.js',
  '/static/js/forms/modules/form-optimization.js',
  '/static/js/forms/modules/disaggregation-calculator.js',
  '/static/js/forms/modules/pdf-export.js',
  '/static/js/forms/modules/repeat-sections.js',
  '/static/js/forms/modules/document-upload.js',
  '/static/js/forms/modules/tooltips.js',
  '/static/js/forms/modules/form-events.js',
  '/static/js/forms/modules/excel-export.js',
  '/static/js/forms/modules/multi-select.js',
  '/static/js/forms/modules/mobile-nav.js',
  '/static/js/forms/plugin-field-loader.js'
];

const PUBLIC_URL_PREFIXES = [
  '/public/',
  '/resources/download/',
  '/resources/thumbnail/',
  '/public_submission_success/',
  '/public_documents/download/',
  '/landing',
  '/forms/public-submission/'
];

function toAbsoluteUrl(pathOrUrl) {
  try {
    return new URL(pathOrUrl, self.location.origin);
  } catch (e) {
    return null;
  }
}

function cacheKeyForUrl(u) {
  // Normalize cache keys by stripping query/hash.
  // This prevents storing duplicates for /static/foo.css and /static/foo.css?v=123.
  return new Request(`${u.origin}${u.pathname}`);
}

async function precacheUrls(cache, urls) {
  const results = await Promise.allSettled(
    urls.map(async (url) => {
      const abs = toAbsoluteUrl(url);
      if (!abs) throw new Error(`precache failed: invalid url ${url}`);
      const key = cacheKeyForUrl(abs);

      // Skip if already cached (e.g., first page load already fetched it)
      const existing = await cache.match(key);
      if (existing) return;

      // cache: 'reload' bypasses HTTP cache for this fetch, ensuring we store a fresh copy
      // when the SW is (re)installed after a deployment.
      const req = new Request(abs.href, { cache: 'reload' });
      const res = await fetch(req);
      if (!res || !res.ok) {
        throw new Error(`precache failed: ${url} (${res ? res.status : 'no response'})`);
      }
      await cache.put(key, res);
    })
  );

  const failed = results.filter((r) => r.status === 'rejected');
  if (failed.length) {
    // Do not fail SW install if some assets are missing or the network is flaky.
    // This is critical for users on unstable connections.
    console.warn(`SW: precache completed with ${failed.length} failures`);
    for (const f of failed.slice(0, 10)) {
      // Avoid spamming logs if many assets fail.
      console.warn('SW: precache failure:', f.reason);
    }
  }
}

function isPublicUrl(url) {
  return PUBLIC_URL_PREFIXES.some(prefix => url.startsWith(self.location.origin + prefix));
}

function isPublicFormUrl(url) {
  // Cache public form URLs (with UUID tokens) and public submission URLs
  // BUT exclude pages that might contain CSRF tokens (like form pages)
  return (url.includes('/forms/public/') && url.match(/\/forms\/public\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i)) ||
         (url.includes('/forms/public-submission/') && url.match(/\/forms\/public-submission\/\d+\/(edit|view|success)$/));
}

function shouldCachePage(url) {
  // Don't cache pages that contain CSRF tokens or form submission pages
  const noCachePatterns = [
    /\/forms\/public\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i, // Public form pages with CSRF tokens
    /\/forms\/public-submission\/\d+\/edit$/i, // Public submission edit pages
    /\/admin\//i, // Admin pages
    /\/api\//i, // API endpoints
  ];

  return !noCachePatterns.some(pattern => pattern.test(url));
}

function isAssignmentFormNavigation(url, request) {
  try {
    if (!request || request.mode !== 'navigate') return false;
    return url.origin === self.location.origin && /^\/forms\/assignment\/\d+/.test(url.pathname);
  } catch (e) {
    return false;
  }
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      try {
        const cache = await caches.open(CACHE_NAME);

        // Cache core assets (resilient: does not fail install if one file 404s)
        await precacheUrls(cache, CORE_ASSETS);

        self.skipWaiting();
      } catch (error) {
        console.error('SW: Installation failed:', error);
        // Still allow the SW to install even if caching fails; users may be on unstable connections.
        try { self.skipWaiting(); } catch (e) {}
      }
    })()
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => {
        return caches.delete(k);
      }));
    }).then(() => {
      // Clear any cached pages that might contain expired CSRF tokens
      return caches.open(CACHE_NAME).then((cache) => {
        return cache.keys().then((requests) => {
          const deletePromises = requests
            .filter(request => {
              const url = new URL(request.url);
              return !shouldCachePage(url.href);
            })
            .map(request => cache.delete(request));
          return Promise.all(deletePromises);
        });
      });
    }).then(() => {
      self.clients.claim();
    })
  );
});

// Allow pages to ask the SW to activate immediately.
self.addEventListener('message', (event) => {
  try {
    if (event.data && event.data.type === 'SKIP_WAITING') {
      self.skipWaiting();
    }
    if (event.data && event.data.type === 'PRECACHE_FORMS') {
      event.waitUntil(
        (async () => {
          try {
            const cache = await caches.open(CACHE_NAME);
            await precacheUrls(cache, FORMS_ASSETS);
          } catch (e) {
            console.warn('SW: PRECACHE_FORMS failed', e);
          }
        })()
      );
    }
  } catch (e) {
    // no-op
  }
});

// Simplified service worker for public forms
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);


  // IMPORTANT:
  // Do not intercept cross-origin requests. If we call fetch() from the Service Worker,
  // the request becomes subject to the document's CSP `connect-src`, which can block
  // otherwise-valid <script>/<link> loads (e.g., CDN scripts or Google Fonts).
  // By not calling respondWith(), the browser handles the request normally.
  if (url.origin !== self.location.origin) {
    return;
  }

  // Skip API routes and language switching completely
  // These should always go directly to the network without service worker interference
  // Note: We allow static assets to be cached even on admin pages (handled below)
  if (url.pathname.startsWith('/api/') ||
      url.pathname.startsWith('/language/')) {
    // Don't call respondWith() - let the browser handle these requests normally
    return;
  }

  // Skip admin page navigations (HTML requests), but allow static assets
  // Static assets under /static/ will be handled by the static asset handler below
  if (url.pathname.startsWith('/admin/') && request.mode === 'navigate') {
    // Don't intercept admin page navigations - let browser handle normally
    return;
  }

  // Skip non-GET requests (after API/admin checks)
  if (request.method !== 'GET') {
    // Don't intercept - let browser handle POST/PUT/DELETE/etc normally
    return;
  }

  // Authenticated assignment form navigations: network-first, cache for offline reopen.
  if (isAssignmentFormNavigation(url, request)) {
    event.respondWith(
      fetch(request, { mode: 'same-origin' })
        .then((response) => {
          if (response && response.ok) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(async () => {
          const cached = await caches.match(request, { ignoreSearch: false });
          if (cached) return cached;
          // Minimal offline fallback shell
          return new Response(
            `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
            <title>Offline</title>
            <style>body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:0;padding:24px;background:#f9fafb;color:#111827}
            .card{max-width:720px;margin:40px auto;background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:20px}
            .muted{color:#6b7280}</style></head>
            <body><div class="card">
              <h2>You are offline</h2>
              <p class="muted">This form page isn't available offline yet. Reconnect and open it once to cache it. If the form is already open, you can keep working and use “Save Draft” to save locally.</p>
            </div></body></html>`,
            { headers: { 'Content-Type': 'text/html; charset=utf-8' }, status: 200 }
          );
        })
    );
    return;
  }

  // (same-origin only from here on)

  // Favicon requests can happen very early and should never break the SW pipeline.
  // If offline and not cached, return an empty icon response instead of throwing.
  if (url.pathname === '/favicon.ico') {
    event.respondWith(
      caches.match(request, { ignoreSearch: true })
        // IMPORTANT: 204 responses must not include a body (even an empty string).
        .then((cached) => cached || new Response(null, { status: 204, headers: { 'Content-Type': 'image/x-icon' } }))
    );
    return;
  }

  // For public form pages, check if we should cache them
  if (isPublicFormUrl(url.href)) {
    // Don't cache pages with CSRF tokens - always fetch fresh
    if (!shouldCachePage(url.href)) {
      event.respondWith(
        fetch(request, {
          mode: 'same-origin',
          cache: 'no-cache',
          headers: {
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
          }
        })
          .then((response) => {
            if (response.ok) {
              console.log('SW: Fetched fresh page (no cache):', url.href);
            }
            return response;
          })
          .catch((error) => {
            console.warn('SW: Network error fetching form page:', url.href, error);
            throw error;
          })
      );
      return;
    }

    // For other public form URLs, use cache-first strategy
    event.respondWith(
      caches.match(request, { ignoreSearch: false })
        .then((cached) => {
          if (cached) {
            return cached;
          }
          // If not in cache, fetch and cache it
          return fetch(request, { mode: 'same-origin' })
            .then((response) => {
              if (response.ok) {
                const copy = response.clone();
                caches.open(CACHE_NAME).then((cache) => {
                  cache.put(request, copy);
                });
              }
              return response;
            })
            .catch((error) => {
              console.warn('SW: Network error fetching form page:', url.href, error);
              throw error;
            });
        })
    );
    return;
  }

  // Static assets: cache-first and ignore querystring (supports ?v=... URLs)
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      (async () => {
        const cache = await caches.open(CACHE_NAME);
        const key = cacheKeyForUrl(url);
        const cached = await cache.match(key);
        if (cached) return cached;
        const response = await fetch(request, { mode: 'same-origin' });
        if (response && response.ok) {
          cache.put(key, response.clone());
        }
        return response;
      })()
    );
    return;
  }

  // Plugin static assets are served under /plugins/static/<plugin>/...
  // Cache them the same way as /static/ assets (cache-first, ignore querystring).
  if (url.pathname.startsWith('/plugins/') && url.pathname.includes('/static/')) {
    event.respondWith(
      (async () => {
        const cache = await caches.open(CACHE_NAME);
        const key = cacheKeyForUrl(url);
        const cached = await cache.match(key);
        if (cached) return cached;
        const response = await fetch(request, { mode: 'same-origin' });
        if (response && response.ok) {
          cache.put(key, response.clone());
        }
        return response;
      })()
    );
    return;
  }

  // All other requests: do not intercept.
  // We intentionally avoid caching HTML/dynamic responses globally (auth pages, CSRF-bearing pages, etc).
  // Static assets are handled above via the /static/ cache-first handler.
  return;
});
