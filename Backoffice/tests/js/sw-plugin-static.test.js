/**
 * Service worker routing for plugin-served static files.
 *
 * Plugins mount /<name>/static/<path> themselves (upr, fdrs, ifrc, decisions,
 * pb-progress, ...). The worker must treat their JS/CSS like core /static/ files
 * without knowing any plugin by name, so a new plugin is covered automatically.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const SW_SOURCE = fs.readFileSync(path.join(ROOT, 'app/static/js/sw.js'), 'utf8');
const ORIGIN = 'https://databank.example';
const OLD_BODY = '/* old plugin script */';
const NEW_BODY = '/* new plugin script */';

function loadServiceWorker(fetchImpl) {
  const stores = new Map();
  const keyOf = (request) => (typeof request === 'string' ? request : request.url);
  const bucket = (name) => {
    if (!stores.has(name)) stores.set(name, new Map());
    const store = stores.get(name);
    return {
      async match(request) {
        return store.get(keyOf(request));
      },
      async put(request, response) {
        store.set(keyOf(request), response);
      },
      async delete(request) {
        return store.delete(keyOf(request));
      },
      async keys() {
        return [...store.keys()].map((url) => new Request(url));
      },
    };
  };
  const caches = {
    stores,
    async open(name) {
      return bucket(name);
    },
    async keys() {
      return [...stores.keys()];
    },
    async delete(name) {
      return stores.delete(name);
    },
  };

  const listeners = {};
  const self = {
    location: { origin: ORIGIN },
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
  return { listeners, caches };
}

async function dispatchFetch(listeners, url) {
  let pending;
  const event = {
    request: new Request(url, { method: 'GET', mode: 'cors' }),
    respondWith(value) {
      pending = Promise.resolve(value);
    },
  };
  for (const handler of listeners.fetch || []) handler(event);
  if (!pending) return { intercepted: false, response: null };
  return { intercepted: true, response: await pending };
}

describe('service worker: plugin static files', () => {
  let fetchImpl;
  let fetched;

  beforeEach(() => {
    fetched = [];
    fetchImpl = async (request) => {
      fetched.push(typeof request === 'string' ? request : request.url);
      return new Response(NEW_BODY, {
        status: 200,
        headers: { 'Content-Type': 'application/javascript' },
      });
    };
  });

  it.each([
    '/upr/static/js/upr-emergency-coverage.js',
    '/fdrs/static/css/fdrs-currency.css',
    '/ifrc/static/js/ppp-dashboard.js',
    '/decisions/static/js/decisions.js',
    '/pb-progress/static/js/pb-progress.js',
    '/some-future-plugin/static/js/anything.mjs',
    '/a/nested/prefix/static/css/x.css',
  ])('fetches %s from the network, never from a stale cached copy', async (pathname) => {
    const { listeners, caches } = loadServiceWorker(fetchImpl);
    const cache = await caches.open('ifrc-forms-ASSET_VERSION_PLACEHOLDER');
    await cache.put(new Request(`${ORIGIN}${pathname}`), new Response(OLD_BODY, { status: 200 }));

    const { intercepted, response } = await dispatchFetch(listeners, `${ORIGIN}${pathname}`);

    expect(intercepted).toBe(true);
    expect(await response.text()).toBe(NEW_BODY);
    expect(fetched).toEqual([`${ORIGIN}${pathname}`]);
  });

  it('keeps ?v= in the cache key so a new version is a new entry', async () => {
    const { listeners, caches } = loadServiceWorker(fetchImpl);
    const cache = await caches.open('ifrc-forms-ASSET_VERSION_PLACEHOLDER');
    await cache.put(
      new Request(`${ORIGIN}/upr/static/js/a.js?v=d1.old`),
      new Response(OLD_BODY, { status: 200 }),
    );

    const { response } = await dispatchFetch(listeners, `${ORIGIN}/upr/static/js/a.js?v=d1.new`);

    expect(await response.text()).toBe(NEW_BODY);
    expect(await (await cache.match(`${ORIGIN}/upr/static/js/a.js?v=d1.new`)).text()).toBe(NEW_BODY);
  });

  it('serves the cached plugin script when the network is down', async () => {
    const offline = async () => {
      throw new TypeError('offline');
    };
    const { listeners, caches } = loadServiceWorker(offline);
    const cache = await caches.open('ifrc-forms-ASSET_VERSION_PLACEHOLDER');
    await cache.put(
      new Request(`${ORIGIN}/upr/static/js/a.js`),
      new Response(OLD_BODY, { status: 200 }),
    );

    const { response } = await dispatchFetch(listeners, `${ORIGIN}/upr/static/js/a.js`);
    expect(await response.text()).toBe(OLD_BODY);
  });

  it.each([
    // Downloads and Excel templates under a plugin static route stay with the browser.
    '/upr/static/templates/unified_country_plan.xlsx',
    '/upr/static/icons/eo-emergency.png',
    // A "static" word that is not a path segment is not a static route.
    '/upr/staticfiles/js/a.js',
    '/upr/static',
    // Not a code asset.
    '/upr/static/js/a.js.map',
    // Plugin API / page routes are never intercepted.
    '/upr/assignment/12/visuals/progress',
  ])('does not intercept %s', async (pathname) => {
    const { listeners } = loadServiceWorker(fetchImpl);
    const { intercepted } = await dispatchFetch(listeners, `${ORIGIN}${pathname}`);
    expect(intercepted).toBe(false);
    expect(fetched).toEqual([]);
  });

  it('does not intercept cross-origin plugin-shaped URLs', async () => {
    const { listeners } = loadServiceWorker(fetchImpl);
    const { intercepted } = await dispatchFetch(listeners, 'https://cdn.example/upr/static/js/a.js');
    expect(intercepted).toBe(false);
  });

  it('does not name any plugin', () => {
    const handler = SW_SOURCE.match(/function isPluginStaticCode[\s\S]*?\n}\n/)[0];
    expect(handler).not.toMatch(/upr|fdrs|ifrc|decisions|pb-progress/);
  });
});
