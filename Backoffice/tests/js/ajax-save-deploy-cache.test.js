/**
 * Assignment /1593 returning-visitor contract.
 *
 * A user who already opened the form before the WAF ajax-save fix still
 * posts to /assignment/1593?ajax=1. They must receive the new ajax-save.js
 * (and every other changed static file) without clearing site data.
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
    });
  }

  lookup(url) {
    const entry = this.entries.get(url);
    if (!entry) return null;
    if (this.now - entry.storedAt >= entry.maxAge) return null;
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

describe('assignment /1593 returning visitor after ajax-save.js deploy', () => {
  describe('HTTP cache: a new ?v= is the only way off an immutable copy', () => {
    it('does not claim that flipping Cache-Control self-heals the same URL', () => {
      expect(UPLOAD_SCRIPT).not.toMatch(/self-heals on the next request/);
    });

    it('fetches the WAF-fixed module when the import map / static_url query changes', () => {
      const cache = new ImmutableHttpCache({ now: 0 });
      cache.store(`${CDN_ORIGIN}${AJAX_SAVE_PATH}`, {
        body: OLD_MODULE,
        cacheControl: 'max-age=31536000, public, immutable',
      });
      cache.now = 3600;
      const result = cache.fetch(`${CDN_ORIGIN}${AJAX_SAVE_PATH}?v=pinned.newhash`, {
        body: NEW_MODULE,
        cacheControl: 'max-age=31536000, public, immutable',
      });
      expect(result.body).toBe(NEW_MODULE);
      expect(result.via).toBe('network');
    });
  });

  describe('service worker', () => {
    let caches;
    let networkBody;
    let fetchImpl;

    beforeEach(() => {
      caches = createCacheStorage();
      networkBody = NEW_MODULE;
      fetchImpl = async () => new Response(networkBody, {
        status: 200,
        headers: { 'Content-Type': 'application/javascript' },
      });
    });

    it('does not serve a previously cached ajax-save.js when the page asks for a new ?v=', async () => {
      const { listeners } = loadServiceWorker({ caches, fetchImpl });
      const cacheName = 'ifrc-forms-ASSET_VERSION_PLACEHOLDER';
      const cache = await caches.open(cacheName);
      await cache.put(
        new Request(`${APP_ORIGIN}${AJAX_SAVE_PATH}`),
        new Response(OLD_MODULE, { status: 200 }),
      );

      const { intercepted, response } = await dispatchFetch(
        listeners,
        new Request(`${APP_ORIGIN}${AJAX_SAVE_PATH}?v=new-deploy-sha.contenthash`, {
          method: 'GET',
          mode: 'cors',
        }),
      );

      expect(intercepted).toBe(true);
      expect(await response.text()).toBe(NEW_MODULE);
    });

    it('revalidates same-origin JS even when the request URL has no new query', async () => {
      const { listeners } = loadServiceWorker({ caches, fetchImpl });
      const cache = await caches.open('ifrc-forms-ASSET_VERSION_PLACEHOLDER');
      await cache.put(
        new Request(`${APP_ORIGIN}${AJAX_SAVE_PATH}`),
        new Response(OLD_MODULE, { status: 200 }),
      );

      const { response } = await dispatchFetch(
        listeners,
        new Request(`${APP_ORIGIN}${AJAX_SAVE_PATH}`, { method: 'GET', mode: 'cors' }),
      );
      expect(await response.text()).toBe(NEW_MODULE);
    });

    it('does not intercept CDN ajax-save.js (versioned URLs are the CDN bust)', async () => {
      const { listeners } = loadServiceWorker({ caches, fetchImpl });
      const { intercepted } = await dispatchFetch(
        listeners,
        new Request(`${CDN_ORIGIN}${AJAX_SAVE_PATH}?v=new-deploy-sha.contenthash`, {
          method: 'GET',
          mode: 'cors',
        }),
      );
      expect(intercepted).toBe(false);
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

  describe('upload script rewrites JS/CSS headers every deploy', () => {
    it('lists local js/css for Cache-Control even when AzCopy dry-run is empty', () => {
      expect(UPLOAD_SCRIPT).toMatch(/_list_local_js_css/);
      expect(UPLOAD_SCRIPT).toMatch(/Always rewrite JS\/CSS Cache-Control/);
      expect(UPLOAD_SCRIPT).not.toMatch(/skipping sync and Cache-Control pass/);
    });
  });
});
