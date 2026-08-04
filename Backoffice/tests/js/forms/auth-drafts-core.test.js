/**
 * Unit tests for auth-drafts-core.js (collect, diff, legacy migration, restore).
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import {
  storeSuffixFromName,
  numericUnformat,
  escapeFieldName,
  shouldSkipDraftElement,
  collectFormData,
  diffAgainstBaseline,
  draftValuesEqual,
  legacySnapshotToSafeDiff,
  resolveDraftPayloadForRestore,
  draftHasContent,
  restoreFormData,
  canRestoreAuthDraft,
  mergeDraftRecords,
  parseDraftRestoreContext,
  readStoredSectionId,
  getPersistedSectionContext,
  getActiveSectionContext,
  isEmptyDraftValue,
} from '../../../app/static/js/forms/modules/auth-drafts-core.js';

function buildForm(html) {
  document.body.innerHTML = html;
  return document.querySelector('form');
}

describe('auth-drafts-core helpers', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    sessionStorage.clear();
    delete window.__ifrcConditionsIsClearing;
    delete window.__numericUnformat;
    window.location.hash = '';
  });

  it('storeSuffixFromName strips auth_drafts_ prefix', () => {
    expect(storeSuffixFromName('auth_drafts_v42')).toBe('v42');
    expect(storeSuffixFromName('')).toBe('v1');
  });

  it('numericUnformat uses window.__numericUnformat when present', () => {
    window.__numericUnformat = (v) => String(v).replace(/,/g, '');
    expect(numericUnformat('1,234')).toBe('1234');
  });

  it('escapeFieldName falls back when CSS.escape is unavailable', () => {
    const prev = globalThis.CSS;
    // eslint-disable-next-line no-global-assign
    globalThis.CSS = undefined;
    expect(escapeFieldName('field"name')).toBe('field\\"name');
    globalThis.CSS = prev;
  });

  it('draftValuesEqual ignores array element order', () => {
    expect(draftValuesEqual(['b', 'a'], ['a', 'b'])).toBe(true);
    expect(draftValuesEqual(['a'], ['a', 'b'])).toBe(false);
  });

  it('isEmptyDraftValue treats false and empty arrays as empty', () => {
    expect(isEmptyDraftValue('')).toBe(true);
    expect(isEmptyDraftValue(false)).toBe(true);
    expect(isEmptyDraftValue([])).toBe(true);
    expect(isEmptyDraftValue('x')).toBe(false);
  });
});

describe('shouldSkipDraftElement', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    delete window.__ifrcConditionsIsClearing;
  });

  it('skips csrf, file inputs, disabled, and relevance-hidden fields', () => {
    document.body.innerHTML = `
      <form id="f">
        <input name="csrf_token" value="tok">
        <input type="file" name="doc">
        <input name="visible" value="yes">
        <div class="form-item-block relevance-hidden" data-item-id="1">
          <input name="hidden_field" value="cleared">
        </div>
      </form>`;
    const form = document.getElementById('f');
    expect(shouldSkipDraftElement(form.elements.namedItem('csrf_token'))).toBe(true);
    expect(shouldSkipDraftElement(form.querySelector('[type=file]'))).toBe(true);
    expect(shouldSkipDraftElement(form.elements.namedItem('visible'))).toBe(false);
    expect(shouldSkipDraftElement(form.elements.namedItem('hidden_field'))).toBe(true);
  });

  it('skips all elements while conditions bulk-clear runs', () => {
    document.body.innerHTML = `<form><input name="a" value="1"></form>`;
    window.__ifrcConditionsIsClearing = true;
    expect(shouldSkipDraftElement(document.querySelector('input'))).toBe(true);
  });
});

describe('collectFormData and diffAgainstBaseline', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    delete window.__ifrcConditionsIsClearing;
  });

  it('collects text, checkbox, radio, and select values', () => {
    const form = buildForm(`
      <form id="focalDataEntryForm">
        <input name="title" value="Hello">
        <input type="checkbox" name="agree" checked>
        <input type="radio" name="mode" value="a" checked>
        <input type="radio" name="mode" value="b">
        <select name="country"><option value="ch" selected>CH</option></select>
      </form>`);
    const data = collectFormData(form);
    expect(data.title).toBe('Hello');
    expect(data.agree).toBe(true);
    expect(data.mode).toBe('a');
    expect(data.country).toBe('ch');
  });

  it('stores unformatted numeric values', () => {
    window.__numericUnformat = (v) => String(v).replace(/,/g, '');
    const form = buildForm(`
      <form><input name="amount" data-numeric="true" value="1,234"></form>`);
    expect(collectFormData(form).amount).toBe('1234');
  });

  it('diffAgainstBaseline returns only changed fields', () => {
    const baseline = { a: '1', b: '2' };
    const current = { a: '1', b: '3', c: 'new' };
    expect(diffAgainstBaseline(current, baseline)).toEqual({ b: '3', c: 'new' });
  });

  it('does not record relevance-hidden clears in diff', () => {
    const form = buildForm(`
      <form id="focalDataEntryForm">
        <input name="kept" value="server">
        <div class="form-item-block relevance-hidden" data-item-id="9">
          <input name="cleared_by_relevance" value="">
        </div>
      </form>`);
    const baseline = { kept: 'server', cleared_by_relevance: 'was populated' };
    const current = collectFormData(form);
    expect(diffAgainstBaseline(current, baseline)).toEqual({});
  });
});

describe('legacySnapshotToSafeDiff', () => {
  it('drops empty legacy values that would wipe baseline content', () => {
    const baseline = { a: 'db', b: '' };
    const legacy = { a: '', b: '', c: 'user-edit' };
    expect(legacySnapshotToSafeDiff(legacy, baseline)).toEqual({ c: 'user-edit' });
  });

  it('identical empty legacy and baseline produces nothing to restore', () => {
    const baseline = { a: '' };
    const legacy = { a: '' };
    expect(legacySnapshotToSafeDiff(legacy, baseline)).toEqual({});
  });
});

describe('resolveDraftPayloadForRestore', () => {
  it('passes diff-based records through unchanged', () => {
    const record = { diffBased: true, data: { x: '1' } };
    expect(resolveDraftPayloadForRestore(record, { x: '0' })).toEqual({
      data: { x: '1' },
      diffBased: true,
    });
  });

  it('converts legacy snapshots to safe diffs', () => {
    const record = { diffBased: false, data: { a: 'new', b: '' } };
    const baseline = { a: 'old', b: 'db' };
    expect(resolveDraftPayloadForRestore(record, baseline)).toEqual({
      data: { a: 'new' },
      diffBased: true,
    });
  });
});

describe('restoreFormData', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    delete window.__numericUnformat;
  });

  it('restores text, checkbox, and radio values', () => {
    const form = buildForm(`
      <form id="f">
        <input name="title" value="">
        <input type="checkbox" name="flag">
        <input type="radio" name="mode" value="yes">
        <input type="radio" name="mode" value="no">
      </form>`);
    restoreFormData(form, { title: 'Restored', flag: true, mode: 'yes' });
    expect(form.elements.namedItem('title').value).toBe('Restored');
    expect(form.elements.namedItem('flag').checked).toBe(true);
    expect(form.querySelector('[value=yes]').checked).toBe(true);
  });

  it('restores unformatted numerics to inputs', () => {
    window.__numericUnformat = (v) => String(v).replace(/,/g, '');
    const form = buildForm(`<form><input name="n" data-numeric="true" value=""></form>`);
    restoreFormData(form, { n: '5,000' });
    expect(form.elements.namedItem('n').value).toBe('5000');
  });

  it('ignores csrf_token in draft payload', () => {
    const form = buildForm(`
      <form>
        <input name="csrf_token" value="original">
        <input name="title" value="">
      </form>`);
    restoreFormData(form, { csrf_token: 'evil', title: 'ok' });
    expect(form.elements.namedItem('csrf_token').value).toBe('original');
    expect(form.elements.namedItem('title').value).toBe('ok');
  });
});

describe('canRestoreAuthDraft', () => {
  it('allows pending and in_progress when review is disabled', () => {
    expect(canRestoreAuthDraft({
      assignmentStatus: 'pending',
      reviewEnabled: false,
      isDelegationUser: false,
    })).toBe(true);
    expect(canRestoreAuthDraft({
      assignmentStatus: 'in_progress',
      reviewEnabled: false,
      isDelegationUser: false,
    })).toBe(true);
  });

  it('blocks submitted and other terminal statuses when review is disabled', () => {
    expect(canRestoreAuthDraft({
      assignmentStatus: 'submitted',
      reviewEnabled: false,
      isDelegationUser: false,
    })).toBe(false);
    expect(canRestoreAuthDraft({
      assignmentStatus: 'sent_for_review',
      reviewEnabled: false,
      isDelegationUser: false,
    })).toBe(false);
  });

  it('blocks NS focals when send-for-review workflow is enabled', () => {
    expect(canRestoreAuthDraft({
      assignmentStatus: 'pending',
      reviewEnabled: true,
      isDelegationUser: false,
    })).toBe(false);
    expect(canRestoreAuthDraft({
      assignmentStatus: 'in_progress',
      reviewEnabled: true,
      isDelegationUser: false,
    })).toBe(false);
    expect(canRestoreAuthDraft({
      assignmentStatus: 'requires_revision',
      reviewEnabled: true,
      isDelegationUser: false,
    })).toBe(false);
  });

  it('allows ORG delegation users only while sent_for_review', () => {
    expect(canRestoreAuthDraft({
      assignmentStatus: 'sent_for_review',
      reviewEnabled: true,
      isDelegationUser: true,
    })).toBe(true);
    expect(canRestoreAuthDraft({
      assignmentStatus: 'in_progress',
      reviewEnabled: true,
      isDelegationUser: true,
    })).toBe(false);
    expect(canRestoreAuthDraft({
      assignmentStatus: 'submitted',
      reviewEnabled: true,
      isDelegationUser: true,
    })).toBe(false);
  });

  it('allows restore when assignment context is absent', () => {
    expect(canRestoreAuthDraft(null)).toBe(true);
    expect(canRestoreAuthDraft({ assignmentStatus: '', reviewEnabled: false, isDelegationUser: false })).toBe(true);
  });
});

describe('parseDraftRestoreContext', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('reads workflow flags from form data attributes', () => {
    document.body.innerHTML = `
      <form id="focalDataEntryForm"
            data-assignment-status="sent_for_review"
            data-review-enabled="true"
            data-is-delegation-user="true"></form>`;
    expect(parseDraftRestoreContext(document.getElementById('focalDataEntryForm'))).toEqual({
      assignmentStatus: 'sent_for_review',
      reviewEnabled: true,
      isDelegationUser: true,
    });
  });
});

describe('mergeDraftRecords', () => {
  it('prefers newer host record over older idb record', () => {
    const idbRec = { data: { a: 'idb' }, updatedAt: 100 };
    const hostRec = { data: { a: 'host' }, updatedAt: 200 };
    const { rec, source } = mergeDraftRecords(idbRec, hostRec);
    expect(source).toBe('host');
    expect(rec.data.a).toBe('host');
  });

  it('ignores tombstoned deleted records', () => {
    const idbRec = { deleted: true, data: { a: '1' } };
    const hostRec = null;
    expect(mergeDraftRecords(idbRec, hostRec)).toEqual({ rec: null, source: 'none' });
  });

  it('draftHasContent requires at least one key', () => {
    expect(draftHasContent({ data: {} })).toBe(false);
    expect(draftHasContent({ data: { x: '1' } })).toBe(true);
  });
});

describe('section context helpers', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <form id="focalDataEntryForm" action="/entry/1"></form>
      <div id="section-container-99" data-page-number="3"></div>
      <a class="section-link is-active" data-section-id="section-container-5" data-page-number="2" href="#section-container-5"></a>`;
  });

  afterEach(() => {
    document.body.innerHTML = '';
    sessionStorage.clear();
    window.location.hash = '';
  });

  it('readStoredSectionId reads location hash', () => {
    window.location.hash = '#section-container-99';
    expect(readStoredSectionId()).toBe('section-container-99');
  });

  it('getActiveSectionContext prefers sidebar active link', () => {
    expect(getActiveSectionContext()).toEqual({
      sectionId: 'section-container-5',
      pageNumber: '2',
    });
  });

  it('getPersistedSectionContext falls back to sessionStorage', () => {
    const form = document.getElementById('focalDataEntryForm');
    const storageKey = `form_page_${btoa(form.action).replace(/[^a-zA-Z0-9]/g, '')}`;
    sessionStorage.setItem(`${storageKey}_section`, 'section-container-99');
    expect(getPersistedSectionContext()).toEqual({
      sectionId: 'section-container-99',
      pageNumber: '3',
    });
  });
});
