/**
 * Why the WAF ajax-save.js fix stayed stuck in returning browsers after deploy.
 *
 * These tests encode the force-reload contract: a visitor who already has
 * ajax-save.js cached must receive the new module after a deploy, without
 * clearing site data. They load the real service worker and replay the
 * cache/deploy strategies the last ship actually used.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const SW_PATH = path.join(ROOT, 'app/static/js/sw.js');
const UPLOAD_SCRIPT = fs.readFileSync(
  path.join(ROOT, 'azure/upload-static-assets.sh'),
  'utf8',
);
const LAYOUT_HTML = fs.readFileSync(
  path.join(ROOT, 'app/templates/core/layout.html'),
  'utf8',
);
const ENTRY_FORM_HTML = fs.readFileSync(
  path.join(ROOT, 'app/templates/forms/entry_form/entry_form.html'),
  'utf8',
);
const SW_SOURCE = fs.readFileSync(SW_PATH, 'utf8');

const AJAX_SAVE_PATH = '/static/js/forms/modules/ajax-save.js';
const APP_ORIGIN = 'https://databank.example';
const CDN_ORIGIN = 'https://cdn.example';
const OLD_MODULE = 'export function initAjaxSave(){ /* pre-WAF */ }';
const NEW_MODULE = 'export function initAjaxSave(){ /* WAF b64 wrap */ }';

class ImmutableHttpCache {
  /**
   * Browser HTTP cache that honors Cache-Control: immutable (RFC 8246).
   * A later origin header change is invisible until the stored response
   * is no longer fresh — the client does not revalidate while max-age holds.
   */
  constructor({ now = 0 } = {}) {
    this.now = now;
    this.entries = new Map();
  }

  store(url, { body, cacheControl, storedAt } = {}) {
    this.entries.set(url, {
      body,
      cacheControl,
      storedAt: storedAt ?? this.now,
      maxAge: parseMaxAge(cacheControl),
      immutable: /\bimmutable\b/.test(cacheControl),
    });
  }

  lookup(url) {
    const entry = this.entries.get(url);
    if (!entry) return null;
    const age = this.now - entry.storedAt;
    if (age >= entry.maxAge) return null;
    return entry;
  }

  fetch(url, originResponse) {
    const cached = this.lookup(url);
    if (cached) {
      return { body: cached.body, via: 'cache', cacheControl: cached.cacheControl };
    }
    this.store(url, originResponse);
    return { body: originResponse.body, via: 'network', cacheControl: originResponse.cacheControl };
  }
}

function parseMaxAge(cacheControl) {
  const match = /max-age=(\d+)/.exec(cacheControl || '');
  return match ? Number(match[1]) : 0;
}

function createCacheStorage() {
  const buckets = new Map();

  function requestUrl(request) {
    if (typeof request === 'string') return request;
    return request.url;
  }

  function openSync(name) {
    if (!buckets.has(name)) buckets.set(name, new Map());
    const store = buckets.get(name);
    return {
      async match(request) {
        return store.get(requestUrl(request));
      },
      async put(request, response) {
        store.set(requestUrl(request), response);
      },
      async delete(request) {
        return store.delete(requestUrl(request));
      },
      async keys() {
        return [...store.keys()].map((url) => new Request(url));
      },
    };
  }

  return {
    buckets,
    async open(name) {
      return openSync(name);
    },
    async match(request, options = {}) {
      const url = new URL(requestUrl(request));
      for (const store of buckets.values()) {
        for (const [cachedUrl, response] of store.entries()) {
          const cached = new URL(cachedUrl);
          const pathMatch = cached.origin === url.origin && cached.pathname === url.pathname;
          if (!pathMatch) continue;
          if (options.ignoreSearch || cached.search === url.search) {
            return response;
          }
        }
      }
      return undefined;
    },
    async keys() {
      return [...buckets.keys()];
    },
    async delete(name) {
      return buckets.delete(name);
    },
  };
}

function loadServiceWorker({ origin = APP_ORIGIN, fetchImpl, caches } = {}) {
  const listeners = {};
  const self = {
    location: { origin },
    addEventListener(type, handler) {
      (listeners[type] ||= []).push(handler);
    },
    skipWaiting: () => {},
    clients: { claim: () => {} },
  };

  const context = {
    self,
    caches,
    fetch: fetchImpl,
    URL,
    Request,
    Response,
    console,
    location: self.location,
  };
  vm.runInNewContext(SW_SOURCE, context, { filename: 'sw.js' });
  return { self, listeners, context };
}

async function dispatchFetch(listeners, request) {
  let pending;
  const event = {
    request,
    respondWith(value) {
      pending = Promise.resolve(value);
    },
  };
  for (const handler of listeners.fetch || []) {
    handler(event);
  }
  if (!pending) return { intercepted: false, response: null };
  return { intercepted: true, response: await pending };
}

describe('returning visitor after ajax-save.js deploy', () => {
  describe('Azure Cache-Control flip (the 5dc91450 self-heal)', () => {
    it('does not claim a strategy the HTTP cache cannot perform', () => {
      expect(UPLOAD_SCRIPT).toMatch(/self-heals on the next request/);
      expect(UPLOAD_SCRIPT).toMatch(/CACHE_CONTROL_REVALIDATE/);
    });

    it('must fetch the WAF-fixed ajax-save.js after origin switches immutable → must-revalidate on the same URL', () => {
      const url = `${CDN_ORIGIN}${AJAX_SAVE_PATH}`;
      const cache = new ImmutableHttpCache({ now: 0 });
      cache.store(url, {
        body: OLD_MODULE,
        cacheControl: 'max-age=31536000, public, immutable',
      });

      // One hour later the blob now has the WAF fix and the new revalidate
      // header. The user reloads the form without clearing site data.
      cache.now = 3600;
      const result = cache.fetch(url, {
        body: NEW_MODULE,
        cacheControl: 'max-age=0, public, must-revalidate',
      });

      expect(result.body, [
        'Returning browsers that already stored unversioned ajax-save.js as',
        '`Cache-Control: immutable` (Azure\'s previous year-long header) will',
        'not revalidate for up to a year. Changing the blob to',
        '`must-revalidate` only affects *new* fetches — it cannot evict the',
        'cached pre-WAF module. That is why the deploy did not force-reload it.',
      ].join(' ')).toBe(NEW_MODULE);
      expect(result.via).toBe('network');
    });

    it('does fetch the new module when the URL itself changes (?v= bump)', () => {
      const cache = new ImmutableHttpCache({ now: 0 });
      cache.store(`${CDN_ORIGIN}${AJAX_SAVE_PATH}?v=oldsha`, {
        body: OLD_MODULE,
        cacheControl: 'max-age=31536000, public, immutable',
      });
      cache.now = 3600;
      const result = cache.fetch(`${CDN_ORIGIN}${AJAX_SAVE_PATH}?v=newsha`, {
        body: NEW_MODULE,
        cacheControl: 'max-age=0, public, must-revalidate',
      });
      expect(result.body).toBe(NEW_MODULE);
      expect(result.via).toBe('network');
    });
  });

  describe('service worker cache-first + stripped query string', () => {
    let caches;
    let networkBody;
    let fetchImpl;

    beforeEach(() => {
      caches = createCacheStorage();
      networkBody = NEW_MODULE;
      fetchImpl = async (input) => {
        const url = typeof input === 'string' ? input : input.url;
        return new Response(networkBody, {
          status: 200,
          headers: { 'Content-Type': 'application/javascript' },
        });
      };
    });

    it('must not serve a previously cached ajax-save.js when the page asks for a new ?v=', async () => {
      const { listeners } = loadServiceWorker({ caches, fetchImpl });
      const cacheName = `ifrc-forms-ASSET_VERSION_PLACEHOLDER`;
      const cache = await caches.open(cacheName);
      await cache.put(
        new Request(`${APP_ORIGIN}${AJAX_SAVE_PATH}`),
        new Response(OLD_MODULE, { status: 200 }),
      );

      const { intercepted, response } = await dispatchFetch(
        listeners,
        new Request(`${APP_ORIGIN}${AJAX_SAVE_PATH}?v=new-deploy-sha`, {
          method: 'GET',
          mode: 'cors',
        }),
      );

      expect(intercepted).toBe(true);
      const body = await response.text();
      expect(body, [
        'sw.js cacheKeyForUrl() strips ?v= and the /static/ handler is',
        'cache-first. A deploy that only changes ASSET_VERSION on the script',
        'URL still hits the old Cache API entry, so ajax-save.js never',
        'reloads until the SW cache *name* changes and the old bucket is',
        'deleted — and even then only if the SW actually reinstalled.',
      ].join(' ')).toBe(NEW_MODULE);
    });

    it('does not intercept CDN ajax-save.js, so a SW cache-version bump cannot refresh production modules', async () => {
      const { listeners } = loadServiceWorker({ caches, fetchImpl });
      const { intercepted } = await dispatchFetch(
        listeners,
        new Request(`${CDN_ORIGIN}${AJAX_SAVE_PATH}?v=new-deploy-sha`, {
          method: 'GET',
          mode: 'cors',
        }),
      );

      expect(intercepted, [
        'Production loads ajax-save.js from STATIC_CDN_URL (cross-origin).',
        'sw.js returns early for other origins, so injecting ASSET_VERSION',
        'into CACHE_NAME cannot evict the CDN/browser copy. Combined with',
        'the immutable header, a SW-only deploy does nothing for form save.',
      ].join(' ')).toBe(true);
    });
  });

  describe('import map still has to win before any module script', () => {
    it('keeps the entry-form import map as the first thing in {% block head %}', () => {
      const headBlock = ENTRY_FORM_HTML.split('{% block head %}')[1]?.split('{% endblock %}')[0] || '';
      const importMapAt = headBlock.indexOf('type="importmap"');
      const moduleAt = headBlock.search(/type=["']module["']/);
      expect(importMapAt).toBeGreaterThanOrEqual(0);
      expect(moduleAt === -1 || importMapAt < moduleAt).toBe(true);
    });

    it('does not load a type=module script in layout.html before {% block head %}', () => {
      const beforeHead = LAYOUT_HTML.split('{% block head %}')[0];
      expect(beforeHead).not.toMatch(/<script\b[^>]*\btype=["']module["']/);
    });
  });

  describe('upload script only rewrites Cache-Control for content-changed blobs', () => {
    it('must update ajax-save.js metadata even when AzCopy dry-run is empty (header-only policy change)', () => {
      const incrementalReturnsEarly = /no static files differ from blob storage; skipping sync and Cache-Control pass/.test(
        UPLOAD_SCRIPT,
      );
      const forceUploadOnlyFullRewrite = /STATIC_FORCE_UPLOAD=1/.test(UPLOAD_SCRIPT)
        && /if \[\[ "\$\{STATIC_FORCE_UPLOAD:-}" == "1" \]\]/.test(UPLOAD_SCRIPT);

      expect(
        incrementalReturnsEarly && forceUploadOnlyFullRewrite,
        [
          'Expected the incremental uploader to still rewrite JS Cache-Control',
          'when file bytes are unchanged. Today a dry-run miss skips the',
          'Cache-Control pass entirely, so existing ajax-save.js blobs keep',
          '`max-age=31536000, immutable` — the header that froze the old module.',
        ].join(' '),
      ).toBe(false);
    });
  });
});
