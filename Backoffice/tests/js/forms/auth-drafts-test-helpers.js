/**
 * Shared Vitest helpers for auth-drafts integration tests.
 */
import { vi } from 'vitest';

export async function clearAuthDraftsDatabase() {
  if (typeof indexedDB === 'undefined') return;
  await new Promise((resolve, reject) => {
    const req = indexedDB.deleteDatabase('ifrc_forms');
    req.onsuccess = () => resolve();
    req.onerror = () => reject(req.error);
    req.onblocked = () => resolve();
  });
}

export async function loadAuthDraftsModule() {
  vi.resetModules();
  return import('../../../app/static/js/forms/modules/auth-drafts.js');
}

export function setupEntryFormDom({
  userId = '42',
  aesId = '100',
  withField = true,
  withCsrf = false,
  assignmentStatus = 'in_progress',
  reviewEnabled = false,
  isDelegationUser = false,
  withAssignmentContext = true,
} = {}) {
  const assignmentAttrs = withAssignmentContext && assignmentStatus
    ? `data-assignment-status="${assignmentStatus}" data-review-enabled="${reviewEnabled ? 'true' : 'false'}" data-is-delegation-user="${isDelegationUser ? 'true' : 'false'}"`
    : '';
  document.body.innerHTML = `
    <div id="presence-bar" data-aes-id="${aesId}" data-current-user-id="${userId}"></div>
    <form id="focalDataEntryForm" action="/forms/entry/${aesId}" ${assignmentAttrs}>
      ${withCsrf ? '<input name="csrf_token" value="tok">' : ''}
      ${withField ? '<input name="indicator_1" value="server-value">' : ''}
      <button type="submit" name="action" value="save">Save</button>
      <button type="submit" name="action" value="submit">Submit</button>
    </form>`;
  document.body.dataset.formInitialized = 'true';
}

export async function prepareAuthDraftsTestEnv() {
  localStorage.clear();
  await clearAuthDraftsDatabase();
  window.ASSET_VERSION = 'test-vitest';
  const mod = await loadAuthDraftsModule();
  await mod.prepareAuthDraftsStore();
  return mod;
}

export async function initAuthDraftsForTest(mod, { preSaveDraft = null } = {}) {
  if (preSaveDraft) {
    await mod.saveDraft('auth:42:100', preSaveDraft.data, preSaveDraft.diffBased !== false);
  }
  mod.initAuthDrafts();
}
