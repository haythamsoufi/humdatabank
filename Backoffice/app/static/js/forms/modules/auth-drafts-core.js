// Pure draft collect/restore/diff helpers (unit-testable, no IndexedDB).

import { getFormPageStorageKey } from './form-page-state.js';

export const DRAFT_EXCLUDED_FIELDS = new Set(['csrf_token']);
export const DRAFT_EXCLUDED_TYPES = new Set(['file', 'submit', 'button', 'reset', 'image', 'password']);

/** Escape a form field name for use in CSS attribute selectors (CSS.escape with fallback). */
export function escapeFieldName(name) {
  if (typeof CSS !== 'undefined' && typeof CSS.escape === 'function') return CSS.escape(name);
  return String(name).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
}

export function storeSuffixFromName(name) {
  if (!name || typeof name !== 'string') return 'v1';
  return name.startsWith('auth_drafts_') ? name.slice('auth_drafts_'.length) : name;
}

export function numericUnformat(value) {
  const fn = (typeof window !== 'undefined' && window.__numericUnformat)
    || ((v) => String(v || '').replace(/[\s,\u00A0\u202F]/g, ''));
  return fn(String(value ?? ''));
}

export function isNumericDraftElement(el) {
  return !!(el && (el.type === 'number' || el.dataset?.numeric === 'true'));
}

/** Skip relevance-hidden fields and programmatic condition clears from draft diffs. */
export function shouldSkipDraftElement(el) {
  if (!el || !el.name) return true;
  if (el.disabled) return true;
  if (DRAFT_EXCLUDED_FIELDS.has(el.name)) return true;
  if (DRAFT_EXCLUDED_TYPES.has(el.type)) return true;
  if (typeof window !== 'undefined' && window.__ifrcConditionsIsClearing === true) return true;

  const fieldBlock = el.closest('.form-item-block[data-item-id]');
  if (fieldBlock?.classList.contains('relevance-hidden')) return true;

  const section = el.closest('div[id^="section-container-"]');
  if (section?.classList.contains('relevance-hidden')) return true;

  return false;
}

export function normalizeDraftFieldValue(el, value) {
  if (isNumericDraftElement(el)) return numericUnformat(value);
  return value;
}

export function collectFormData(form) {
  const data = {};
  const processedCheckboxNames = new Set();
  Array.from(form.elements).forEach((el) => {
    if (shouldSkipDraftElement(el)) return;

    if (el.type === 'checkbox') {
      if (processedCheckboxNames.has(el.name)) return;
      processedCheckboxNames.add(el.name);
      const same = form.querySelectorAll(`input[type="checkbox"][name="${escapeFieldName(el.name)}"]`);
      if (same.length > 1) {
        data[el.name] = Array.from(same).filter((n) => n.checked).map((n) => n.value);
      } else {
        data[el.name] = !!el.checked;
      }
      return;
    }

    if (el.type === 'radio') {
      if (el.checked) {
        data[el.name] = el.value;
      } else if (!(el.name in data)) {
        data[el.name] = '';
      }
      return;
    }

    if (el.type === 'select-multiple') {
      data[el.name] = Array.from(el.selectedOptions).map((o) => o.value);
      return;
    }

    if (typeof el.value === 'undefined') return;
    data[el.name] = normalizeDraftFieldValue(el, el.value);
  });
  return data;
}

function sortedArrayKey(arr) {
  return JSON.stringify([...arr].map(String).sort());
}

export function draftValuesEqual(a, b) {
  if (Array.isArray(a) && Array.isArray(b)) {
    if (a.length !== b.length) return false;
    return sortedArrayKey(a) === sortedArrayKey(b);
  }
  return a === b;
}

export function diffAgainstBaseline(current, baseline) {
  const diff = {};
  Object.keys(current).forEach((name) => {
    if (!(name in baseline) || !draftValuesEqual(current[name], baseline[name])) {
      diff[name] = current[name];
    }
  });
  return diff;
}

export function isEmptyDraftValue(value) {
  if (value == null || value === '' || value === false) return true;
  if (Array.isArray(value)) return value.length === 0;
  return false;
}

/** Convert a legacy full-form snapshot into a safe diff vs the current baseline. */
export function legacySnapshotToSafeDiff(snapshot, baseline) {
  const diff = diffAgainstBaseline(snapshot, baseline);
  const safe = {};
  Object.keys(diff).forEach((name) => {
    const value = diff[name];
    const baseValue = baseline[name];
    if (!isEmptyDraftValue(value)) {
      safe[name] = value;
      return;
    }
    if (!(name in baseline)) safe[name] = value;
    else if (isEmptyDraftValue(baseValue)) safe[name] = value;
  });
  return safe;
}

export function resolveDraftPayloadForRestore(record, baseline) {
  if (!record?.data) return { data: null, diffBased: true };
  if (record.diffBased) return { data: record.data, diffBased: true };
  if (!baseline) return { data: null, diffBased: true };
  return { data: legacySnapshotToSafeDiff(record.data, baseline), diffBased: true };
}

export function draftHasContent(rec) {
  return !!(rec && rec.data && typeof rec.data === 'object' && Object.keys(rec.data).length > 0);
}

export function restoreFormData(form, data) {
  if (!data) return;
  Object.entries(data).forEach(([name, value]) => {
    if (DRAFT_EXCLUDED_FIELDS.has(name)) return;
    if (typeof value === 'undefined') return;
    const el = form.elements.namedItem(name);
    if (!el) return;

    if (el instanceof RadioNodeList) {
      const nodes = Array.from(el);
      nodes.forEach((n) => {
        if (n.type === 'checkbox') {
          n.checked = Array.isArray(value) && value.includes(n.value);
        } else if (n.type === 'radio') {
          n.checked = value === n.value;
        }
      });
      return;
    }

    if (el.type === 'checkbox') {
      el.checked = !!value;
      return;
    }

    if (el.type === 'radio') {
      el.checked = value === el.value;
      return;
    }

    if (el.type === 'select-multiple') {
      if (!Array.isArray(value)) return;
      Array.from(el.options).forEach((o) => { o.selected = value.includes(o.value); });
      return;
    }

    if (typeof value !== 'string' && typeof value !== 'number') return;
    el.value = isNumericDraftElement(el) ? numericUnformat(value) : String(value);
  });
}

export function readStoredSectionId() {
  const hash = (window.location.hash || '').replace(/^#/, '');
  if (hash.startsWith('section-container-')) return hash;

  try {
    const storageKey = getFormPageStorageKey();
    const stored = sessionStorage.getItem(`${storageKey}_section`);
    if (stored && stored.startsWith('section-container-')) return stored;
  } catch (_) { /* no-op */ }

  return null;
}

export function sectionContextFromId(sectionId) {
  if (!sectionId) return null;
  const el = document.getElementById(sectionId);
  return { sectionId, pageNumber: el?.dataset?.pageNumber };
}

export function getPersistedSectionContext() {
  return sectionContextFromId(readStoredSectionId());
}

export function getActiveSectionContext() {
  const activeLink = document.querySelector('a.section-link.is-active');
  if (activeLink) {
    const sectionId = activeLink.dataset.sectionId
      || (activeLink.getAttribute('href') || '').replace(/^#/, '');
    if (sectionId) {
      return { sectionId, pageNumber: activeLink.dataset.pageNumber };
    }
  }
  return sectionContextFromId(readStoredSectionId());
}

/** Statuses where draft restore is allowed when delegation review is not enabled. */
export const DRAFT_RESTORE_EDITABLE_STATUSES = new Set(['pending', 'in_progress']);

/** Statuses where ORG/delegation users may restore while review workflow is enabled. */
export const DRAFT_RESTORE_DELEGATION_STATUSES = new Set(['sent_for_review']);

export function normalizeAssignmentStatus(status) {
  if (status == null || status === '') return '';
  return String(status).trim().toLowerCase();
}

/**
 * Read assignment workflow context from the entry form data attributes.
 * @param {HTMLFormElement|null|undefined} form
 * @returns {{ assignmentStatus: string, reviewEnabled: boolean, isDelegationUser: boolean }|null}
 */
export function parseDraftRestoreContext(form) {
  if (!form) return null;
  const assignmentStatus = normalizeAssignmentStatus(
    form.dataset.assignmentStatus || form.getAttribute('data-assignment-status') || '',
  );
  const reviewEnabled = (form.dataset.reviewEnabled || form.getAttribute('data-review-enabled') || '') === 'true';
  const isDelegationUser = (form.dataset.isDelegationUser || form.getAttribute('data-is-delegation-user') || '') === 'true';
  return { assignmentStatus, reviewEnabled, isDelegationUser };
}

/**
 * Whether a local draft may be offered for restore on this assignment.
 * - Without delegation review: pending or in_progress only (not yet submitted).
 * - With delegation review: NS focals never; ORG/delegation users only while sent_for_review.
 */
export function canRestoreAuthDraft(context) {
  if (!context) return true;
  const { assignmentStatus, reviewEnabled, isDelegationUser } = context;
  if (!assignmentStatus) return true;

  if (reviewEnabled) {
    if (isDelegationUser) {
      return DRAFT_RESTORE_DELEGATION_STATUSES.has(assignmentStatus);
    }
    return false;
  }

  return DRAFT_RESTORE_EDITABLE_STATUSES.has(assignmentStatus);
}

export function mergeDraftRecords(idbRec, hostRec) {
  let rec = null;
  let source = 'none';
  if (idbRec && idbRec.deleted) idbRec = null;
  if (hostRec && hostRec.deleted) hostRec = null;
  if (idbRec && idbRec.data && hostRec && hostRec.data) {
    const idbT = idbRec.updatedAt || 0;
    const hostT = hostRec.updatedAt || 0;
    rec = idbT >= hostT ? idbRec : hostRec;
    source = idbT >= hostT ? 'idb' : 'host';
  } else if (idbRec && idbRec.data) {
    rec = idbRec;
    source = 'idb';
  } else if (hostRec && hostRec.data) {
    rec = hostRec;
    source = 'host';
  }
  if (!draftHasContent(rec)) {
    return { rec: null, source: 'none' };
  }
  return { rec, source };
}
