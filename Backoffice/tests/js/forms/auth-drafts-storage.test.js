/**
 * IndexedDB persistence tests for auth-drafts.js (save / load / delete / host merge).
 */
import 'fake-indexeddb/auto';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  clearAuthDraftsDatabase,
  loadAuthDraftsModule,
  prepareAuthDraftsTestEnv,
} from './auth-drafts-test-helpers.js';

const DRAFT_KEY = 'auth:42:100';

vi.mock('../../../app/static/js/forms/modules/repeat-sections.js', () => ({
  ensureRepeatEntriesFromDraftData: vi.fn(),
}));

describe('auth-drafts IndexedDB storage', () => {
  beforeEach(async () => {
    await clearAuthDraftsDatabase();
    localStorage.clear();
    window.ASSET_VERSION = 'test-vitest';
    delete window.flutter_inappwebview;
  });

  afterEach(() => {
    delete window.ASSET_VERSION;
    delete window.flutter_inappwebview;
  });

  it('saveDraft and loadDraft round-trip diff-based records', async () => {
    const mod = await prepareAuthDraftsTestEnv();
    await mod.saveDraft(DRAFT_KEY, { field_a: 'changed' }, true);
    const loaded = await mod.loadDraft(DRAFT_KEY);
    expect(loaded.data).toEqual({ field_a: 'changed' });
    expect(loaded.diffBased).toBe(true);
    expect(loaded.key).toBe(DRAFT_KEY);
  });

  it('deleteDraft removes stored record', async () => {
    const mod = await prepareAuthDraftsTestEnv();
    await mod.saveDraft(DRAFT_KEY, { x: '1' }, true);
    await mod.deleteDraft(DRAFT_KEY);
    expect(await mod.loadDraft(DRAFT_KEY)).toBeNull();
  });

  it('loadDraft prefers newer host record and backfills IndexedDB', async () => {
    const mod = await prepareAuthDraftsTestEnv();
    await mod.saveDraft(DRAFT_KEY, { stale: 'idb' }, true);

    window.flutter_inappwebview = {
      callHandler: vi.fn(async (name) => {
        if (name === 'authDraftPullFromHost') {
          return JSON.stringify({
            key: DRAFT_KEY,
            data: { fresh: 'host' },
            updatedAt: Date.now() + 1000,
            diffBased: true,
          });
        }
        return null;
      }),
    };

    const loaded = await mod.loadDraft(DRAFT_KEY);
    expect(loaded.data).toEqual({ fresh: 'host' });

    delete window.flutter_inappwebview;
    const idbOnly = await mod.loadDraft(DRAFT_KEY);
    expect(idbOnly.data).toEqual({ fresh: 'host' });
  });

  it('pushDraftToHost is called on save when mobile bridge exists', async () => {
    const mod = await prepareAuthDraftsTestEnv();
    const callHandler = vi.fn(async () => null);
    window.flutter_inappwebview = { callHandler };

    await mod.saveDraft(DRAFT_KEY, { mobile: '1' }, true);
    expect(callHandler).toHaveBeenCalledWith(
      'authDraftPushToHost',
      expect.stringContaining('"mobile":"1"'),
    );
  });

  it('loadDraft reads localStorage spill and backfills IndexedDB', async () => {
    const mod = await prepareAuthDraftsTestEnv();
    mod.spillDraftSync(DRAFT_KEY, { spilled: 'yes' }, Date.now(), true);
    const loaded = await mod.loadDraft(DRAFT_KEY);
    expect(loaded.data).toEqual({ spilled: 'yes' });
    expect(mod.readSpilledDraft(DRAFT_KEY)).toBeNull();
    const again = await mod.loadDraft(DRAFT_KEY);
    expect(again.data).toEqual({ spilled: 'yes' });
  });

  it('migrates records from legacy auth_drafts_* store on version bump', async () => {
    const OLD_STORE = 'auth_drafts_v-old';
    await new Promise((resolve, reject) => {
      const req = indexedDB.open('ifrc_forms', 2);
      req.onupgradeneeded = (e) => {
        const db = e.target.result;
        if (!db.objectStoreNames.contains(OLD_STORE)) {
          db.createObjectStore(OLD_STORE, { keyPath: 'key' });
        }
      };
      req.onsuccess = () => {
        const db = req.result;
        const tx = db.transaction(OLD_STORE, 'readwrite');
        tx.objectStore(OLD_STORE).put({
          key: DRAFT_KEY,
          data: { migrated: 'yes' },
          updatedAt: 100,
          diffBased: true,
        });
        tx.oncomplete = () => { db.close(); resolve(); };
        tx.onerror = () => reject(tx.error);
      };
      req.onerror = () => reject(req.error);
    });

    localStorage.setItem('ifrc_auth_drafts_version', 'v-old');
    localStorage.setItem('ifrc_auth_drafts_idb_schema_v2', '2');
    window.ASSET_VERSION = 'v-new';

    const mod = await loadAuthDraftsModule();
    await mod.prepareAuthDraftsStore();
    mod.invalidateDbCache();

    const loaded = await mod.loadDraft(DRAFT_KEY);
    expect(loaded?.data).toEqual({ migrated: 'yes' });
  });
});
