/**
 * Unit tests for section-lock.js (page lock, banner sync, admin bypass, buzz).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

async function loadSectionLock() {
  vi.resetModules();
  return import('../../../app/static/js/forms/modules/section-lock.js');
}

function mountLockedPage({ bypass = false } = {}) {
  document.body.innerHTML = `
    <form id="focalDataEntryForm"${bypass ? ' data-bypass-page-lock="true"' : ''}>
      <div class="page-locked-banner hidden" data-page-id="7" data-page-number="1">
        <span>This page is locked and cannot be edited.</span>
      </div>
      <div id="section-container-10"
           data-page-id="7"
           data-page-workflow="submitted"
           data-page-locked="true"
           class="section-container--locked">
        <div data-collapsible-content>
          <div class="form-item-block">
            <input type="text" name="field_value[1]" value="x">
            <button type="button" class="collapse-toggle">Toggle</button>
          </div>
        </div>
      </div>
    </form>
  `;
}

describe('section-lock', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  afterEach(() => {
    document.body.innerHTML = '';
    vi.useRealTimers();
  });

  it('disables fields and reveals the sticky banner when locked', async () => {
    mountLockedPage();
    const { initSectionLocks } = await loadSectionLock();
    initSectionLocks();

    const input = document.querySelector('input[name="field_value[1]"]');
    const banner = document.querySelector('.page-locked-banner');
    expect(input.disabled).toBe(true);
    expect(banner.classList.contains('hidden')).toBe(false);
  });

  it('bypasses lock for admins/system managers', async () => {
    mountLockedPage({ bypass: true });
    const { initSectionLocks } = await loadSectionLock();
    initSectionLocks();

    const container = document.getElementById('section-container-10');
    const input = document.querySelector('input[name="field_value[1]"]');
    const banner = document.querySelector('.page-locked-banner');
    expect(container.dataset.pageLocked).toBe('false');
    expect(input.disabled).toBe(false);
    expect(banner.classList.contains('hidden')).toBe(true);
  });

  it('buzzes the banner when interacting with a locked form item', async () => {
    vi.useFakeTimers();
    mountLockedPage();
    const { initSectionLocks, buzzPageLockedBanner } = await loadSectionLock();
    initSectionLocks();

    const banner = document.querySelector('.page-locked-banner');
    banner.scrollIntoView = vi.fn();

    const input = document.querySelector('input[name="field_value[1]"]');
    input.dispatchEvent(new Event('pointerdown', { bubbles: true }));

    expect(banner.classList.contains('page-locked-banner--buzz')).toBe(true);
    expect(buzzPageLockedBanner('7')).toBe(true);

    vi.advanceTimersByTime(500);
    expect(banner.classList.contains('page-locked-banner--buzz')).toBe(false);
  });

  it('does not buzz chrome controls like collapse toggles', async () => {
    mountLockedPage();
    const { initSectionLocks } = await loadSectionLock();
    initSectionLocks();

    const banner = document.querySelector('.page-locked-banner');
    banner.scrollIntoView = vi.fn();
    banner.classList.remove('page-locked-banner--buzz');

    document.querySelector('.collapse-toggle')
      .dispatchEvent(new Event('pointerdown', { bubbles: true }));

    expect(banner.classList.contains('page-locked-banner--buzz')).toBe(false);
  });

  it('hides the banner when unlocking a page', async () => {
    mountLockedPage();
    const { initSectionLocks, applySectionLock } = await loadSectionLock();
    initSectionLocks();

    const container = document.getElementById('section-container-10');
    applySectionLock(container, false);

    const banner = document.querySelector('.page-locked-banner');
    expect(banner.classList.contains('hidden')).toBe(true);
    expect(container.dataset.pageLocked).toBe('false');
  });
});
