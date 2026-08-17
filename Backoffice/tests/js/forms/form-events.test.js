/**
 * Unit tests for form-events.js (presave-on-submit, confirm dialogs, public CSRF).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/ajax-save.js', () => ({
  triggerSave: vi.fn(),
  saveFormBeforeSubmit: vi.fn(async () => true),
}));

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
  debugLog: vi.fn(),
}));

import { initFormEvents } from '../../../app/static/js/forms/modules/form-events.js';
import { saveFormBeforeSubmit, triggerSave } from '../../../app/static/js/forms/modules/ajax-save.js';

function flushPromises() {
  return Promise.resolve().then(() => Promise.resolve());
}

function mountForm({
  publicSubmission = false,
  confirmMessage = null,
  extraButtons = '',
} = {}) {
  const confirmAttrs = confirmMessage
    ? ` data-confirm-message="${confirmMessage}" data-confirm-title="Submit Form?" data-confirm-label="Submit"`
    : '';
  const formHtml = `
    <form id="focalDataEntryForm" action="/forms/entry/1">
      <input name="csrf_token" value="tok">
      <button type="submit" name="action" value="save">Save</button>
      <button type="submit" name="action" value="submit"${confirmAttrs}>Submit</button>
      ${extraButtons}
    </form>`;
  document.body.innerHTML = publicSubmission
    ? `<div data-is-public-submission="true">${formHtml}</div>`
    : formHtml;

  const form = document.getElementById('focalDataEntryForm');
  form.requestSubmit = vi.fn();
  form.submit = vi.fn();
  return form;
}

function dispatchFormSubmit(form, submitter, { forcePresave = false } = {}) {
  if (forcePresave) {
    form.dataset.ifrcForcePresave = '1';
  }
  const event = new SubmitEvent('submit', {
    bubbles: true,
    cancelable: true,
    submitter,
  });
  if (submitter && event.submitter !== submitter) {
    Object.defineProperty(event, 'submitter', { value: submitter, configurable: true });
  }
  form.dispatchEvent(event);
  return event;
}

describe('initFormEvents', () => {
  beforeEach(() => {
    window.t = (k) => k;
    window.showFlashMessage = vi.fn();
    saveFormBeforeSubmit.mockClear();
    saveFormBeforeSubmit.mockResolvedValue(true);
    triggerSave.mockClear();
    vi.spyOn(HTMLFormElement.prototype, 'requestSubmit').mockImplementation(() => {});
    vi.spyOn(HTMLFormElement.prototype, 'submit').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    document.body.innerHTML = '';
    delete window.t;
    delete window.showFlashMessage;
    delete window.showConfirmation;
    delete window.showSubmitConfirmation;
    delete window.getConfirmDialogOptions;
    delete window.refreshCsrfFromCurrentPage;
    delete window.collectHiddenFieldsForSubmission;
    delete window.FormSubmitGuard;
    delete window.__clientLog;
    delete window.__clientWarn;
  });

  it('is a no-op without #focalDataEntryForm', () => {
    document.body.innerHTML = '<form id="otherForm"></form>';
    expect(() => initFormEvents()).not.toThrow();
    expect(saveFormBeforeSubmit).not.toHaveBeenCalled();
  });

  it('save-before-submit: action=submit with ifrcForcePresave calls saveFormBeforeSubmit and preventDefault', async () => {
    const form = mountForm();
    const collectHidden = vi.fn();
    window.collectHiddenFieldsForSubmission = collectHidden;
    window.FormSubmitGuard = { reset: vi.fn() };
    initFormEvents();

    const submitBtn = form.querySelector('button[value="submit"]');
    const event = dispatchFormSubmit(form, submitBtn, { forcePresave: true });

    expect(event.defaultPrevented).toBe(true);
    expect(saveFormBeforeSubmit).toHaveBeenCalledWith({ toast: false });
    expect(collectHidden).toHaveBeenCalled();
    expect(window.showFlashMessage).toHaveBeenCalledWith('Saving your latest changes…', 'info');

    await flushPromises();

    expect(window.showFlashMessage).toHaveBeenCalledWith('Changes saved.', 'info');
    expect(form.querySelector('input[name="action"][type="hidden"]').value).toBe('submit');
    expect(form.dataset.ifrcInternalSubmit).toBe('1');
    expect(form.requestSubmit).toHaveBeenCalledWith(submitBtn);
    expect(window.FormSubmitGuard.reset).toHaveBeenCalledWith(form);
    expect(form.dataset.ifrcPresaveInProgress).toBeUndefined();
    expect(form.dataset.ifrcForcePresave).toBeUndefined();
  });

  it('save action does not take the save-before-submit path', () => {
    const form = mountForm();
    initFormEvents();

    const saveBtn = form.querySelector('button[value="save"]');
    const event = dispatchFormSubmit(form, saveBtn, { forcePresave: true });

    expect(saveFormBeforeSubmit).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
    expect(form.querySelector('input[name="action"][type="hidden"]').value).toBe('save');
  });

  it('skips presave when ifrcInternalSubmit marks a programmatic follow-up submit', () => {
    const form = mountForm();
    initFormEvents();
    form.dataset.ifrcInternalSubmit = '1';

    const submitBtn = form.querySelector('button[value="submit"]');
    const event = dispatchFormSubmit(form, submitBtn, { forcePresave: true });

    expect(saveFormBeforeSubmit).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
    expect(form.dataset.ifrcInternalSubmit).toBeUndefined();
  });

  it('prevents a duplicate presave while ifrcPresaveInProgress is set', () => {
    const form = mountForm();
    initFormEvents();
    form.dataset.ifrcPresaveInProgress = '1';

    const submitBtn = form.querySelector('button[value="submit"]');
    const event = dispatchFormSubmit(form, submitBtn, { forcePresave: true });

    expect(event.defaultPrevented).toBe(true);
    expect(saveFormBeforeSubmit).not.toHaveBeenCalled();
  });

  it('shows showSubmitConfirmation when the submit button has data-confirm-message', () => {
    const form = mountForm({ confirmMessage: 'Really submit this form?' });
    window.showSubmitConfirmation = vi.fn();
    window.showConfirmation = vi.fn();
    initFormEvents();

    const submitBtn = form.querySelector('button[value="submit"]');
    const click = new MouseEvent('click', { bubbles: true, cancelable: true });
    submitBtn.dispatchEvent(click);

    expect(click.defaultPrevented).toBe(true);
    expect(window.showSubmitConfirmation).toHaveBeenCalledWith(
      'Really submit this form?',
      expect.any(Function),
      expect.any(Function),
      'Submit',
      'Cancel',
      'Submit Form?',
    );
    expect(window.showConfirmation).not.toHaveBeenCalled();
    expect(form.requestSubmit).not.toHaveBeenCalled();
  });

  it('falls back to showConfirmation and setHiddenAction on confirm', () => {
    const form = mountForm({ confirmMessage: 'Confirm submit?' });
    window.showConfirmation = vi.fn();
    initFormEvents();

    const submitBtn = form.querySelector('button[value="submit"]');
    submitBtn.click();

    expect(window.showConfirmation).toHaveBeenCalledWith(
      'Confirm submit?',
      expect.any(Function),
      expect.any(Function),
      'Submit',
      'Cancel',
      'Submit Form?',
    );

    const onConfirm = window.showConfirmation.mock.calls[0][1];
    onConfirm();

    expect(form.dataset.ifrcForcePresave).toBe('1');
    expect(form.querySelector('input[name="action"][type="hidden"]').value).toBe('submit');
    expect(form.requestSubmit).toHaveBeenCalledWith(submitBtn);
    expect(submitBtn.dataset.confirmInProgress).toBe('false');
  });

  it('refreshes CSRF on init when the form is a public submission', () => {
    window.refreshCsrfFromCurrentPage = vi.fn();
    mountForm({ publicSubmission: true });
    initFormEvents();
    expect(window.refreshCsrfFromCurrentPage).toHaveBeenCalledTimes(1);
  });

  it('intercepts public submit to refresh CSRF then requestSubmit', async () => {
    const form = mountForm({ publicSubmission: true });
    initFormEvents();

    window.refreshCsrfFromCurrentPage = vi.fn(async () => {});
    const submitBtn = form.querySelector('button[value="submit"]');
    // Untrusted + no ifrcForcePresave: capture presave handler returns early.
    const event = dispatchFormSubmit(form, submitBtn);

    expect(event.defaultPrevented).toBe(true);
    expect(saveFormBeforeSubmit).not.toHaveBeenCalled();
    expect(window.refreshCsrfFromCurrentPage).toHaveBeenCalledTimes(1);

    await flushPromises();

    expect(form.dataset.csrfRefreshed).toBe('true');
    expect(form.dataset.ifrcInternalSubmit).toBe('1');
    expect(form.querySelector('input[name="action"][type="hidden"]').value).toBe('submit');
    expect(form.requestSubmit).toHaveBeenCalledWith(submitBtn);
  });

  it('wires the FAB save button to the main save submitter', () => {
    document.body.innerHTML = `
      <form id="focalDataEntryForm">
        <button type="submit" name="action" value="save" id="main-save">Save</button>
      </form>
      <button type="button" id="fab-save-btn">FAB Save</button>`;
    const form = document.getElementById('focalDataEntryForm');
    form.requestSubmit = vi.fn();
    const saveBtn = form.querySelector('#main-save');
    const saveClick = vi.fn();
    saveBtn.addEventListener('click', saveClick);

    initFormEvents();
    document.getElementById('fab-save-btn').click();

    expect(saveClick).toHaveBeenCalled();
    expect(triggerSave).not.toHaveBeenCalled();
  });
});
