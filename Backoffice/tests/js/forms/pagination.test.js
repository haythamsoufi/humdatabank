/**
 * Visibility tests for entry-form pagination (applyVisibilityForPage).
 *
 * pagination.js auto-calls initPagination() on import. Fixture HTML must be
 * in the document before import(); vi.resetModules() re-runs init each test.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
  debugLog: vi.fn(),
  debugWarn: vi.fn(),
  isDebugEnabled: () => false,
}));

vi.mock('../../../app/static/js/core/scroll-container.js', () => ({
  getScrollableContainer: () => document.documentElement,
  scrollElementIntoViewIfNeeded: vi.fn(),
}));

vi.mock('../../../app/static/js/forms/modules/form-page-state.js', () => ({
  buildFormPageStorageKey: () => 'test-form-page',
  getStableFormStorageBaseUrl: () => '/forms/entry/1',
  isPageReload: () => false,
}));

const PAGINATION_LABELS = {
  previous: 'Previous Page',
  next: 'Next Page',
  of: 'of',
};

const PAGINATED_FIXTURE = `
<div id="sections-container" data-is-paginated="true">
  <div id="section-container-1" data-page-number="1" data-page-name="One" data-section-type="standard">
    <p>Page 1</p>
  </div>
  <div id="section-container-2" data-page-number="2" data-page-name="Two" data-section-type="standard">
    <p>Page 2</p>
  </div>
  <div id="section-container-3" data-page-number="2" data-page-name="Two" data-section-type="standard"
       class="relevance-hidden">
    <p>Hidden by relevance</p>
  </div>
</div>
`;

function section(id) {
  return document.getElementById(id);
}

function isPaginationHidden(el) {
  return el.style.getPropertyValue('display') === 'none'
    && el.style.getPropertyPriority('display') === 'important';
}

function isPaginationShown(el) {
  return el.style.getPropertyValue('display') === '';
}

async function loadPagination(html = PAGINATED_FIXTURE) {
  vi.resetModules();
  delete window.__ifrcPagination;
  document.body.innerHTML = html;
  document.body.dataset.formInitialized = 'true';
  await import('../../../app/static/js/forms/modules/pagination.js');
  return window.__ifrcPagination;
}

describe('entry-form pagination visibility', () => {
  beforeEach(() => {
    window.scrollTo = vi.fn();
    window.PAGINATION_LABELS = PAGINATION_LABELS;
    globalThis.PAGINATION_LABELS = PAGINATION_LABELS;
    vi.stubGlobal('PAGINATION_LABELS', PAGINATION_LABELS);
    sessionStorage.clear();
    window.history.replaceState({}, '', '/');
    document.body.innerHTML = '';
    delete document.body.dataset.formInitialized;
    delete window.__ifrcPagination;
  });

  afterEach(() => {
    delete window.__ifrcPagination;
    delete window.PAGINATION_LABELS;
    delete globalThis.PAGINATION_LABELS;
    vi.unstubAllGlobals();
    sessionStorage.clear();
    window.history.replaceState({}, '', '/');
    document.body.innerHTML = '';
    delete document.body.dataset.formInitialized;
  });

  it('shows page 1 and hides page 2 after import', async () => {
    await loadPagination();

    expect(isPaginationShown(section('section-container-1'))).toBe(true);
    expect(isPaginationHidden(section('section-container-2'))).toBe(true);
    expect(isPaginationHidden(section('section-container-3'))).toBe(true);
  });

  it('showPageByNumber(2) shows the page-2 section and hides page 1', async () => {
    const api = await loadPagination();

    expect(api.showPageByNumber(2)).toBe(true);

    expect(isPaginationHidden(section('section-container-1'))).toBe(true);
    expect(isPaginationShown(section('section-container-2'))).toBe(true);
  });

  it('keeps relevance-hidden on page 2 display:none after showPageByNumber(2) and refresh()', async () => {
    const api = await loadPagination();
    const hidden = section('section-container-3');

    api.showPageByNumber(2);
    expect(isPaginationHidden(hidden)).toBe(true);
    expect(hidden.classList.contains('relevance-hidden')).toBe(true);

    expect(api.refresh()).toBe(true);
    expect(isPaginationHidden(hidden)).toBe(true);
    expect(isPaginationShown(section('section-container-2'))).toBe(true);
  });

  it('showPageByNumber(99) returns false and leaves the current page unchanged', async () => {
    const api = await loadPagination();
    const before = api.getCurrentPageNumber();

    expect(api.showPageByNumber(99)).toBe(false);
    expect(api.getCurrentPageNumber()).toBe(before);
    expect(isPaginationShown(section('section-container-1'))).toBe(true);
    expect(isPaginationHidden(section('section-container-2'))).toBe(true);
  });

  it('getCurrentPageNumber tracks the active page', async () => {
    const api = await loadPagination();

    expect(api.getCurrentPageNumber()).toBe(1);
    api.showPageByNumber(2);
    expect(api.getCurrentPageNumber()).toBe(2);
    api.showPageByNumber(1);
    expect(api.getCurrentPageNumber()).toBe(1);
  });

  it('getCurrentPageIndex tracks the active page index', async () => {
    const api = await loadPagination();

    expect(api.getCurrentPageIndex()).toBe(0);
    api.showPageByNumber(2);
    expect(api.getCurrentPageIndex()).toBe(1);
  });

  it('dispatches ifrc:pagination:pageChanged with pageNumber 2', async () => {
    const api = await loadPagination();
    const handler = vi.fn();
    document.addEventListener('ifrc:pagination:pageChanged', handler);

    api.showPageByNumber(2);

    expect(handler).toHaveBeenCalledTimes(1);
    const event = handler.mock.calls[0][0];
    expect(event).toBeInstanceOf(CustomEvent);
    expect(event.detail.pageNumber).toBe(2);
  });

  it('showPageByNumber(1) after page 2 restores page-1 visibility', async () => {
    const api = await loadPagination();

    api.showPageByNumber(2);
    api.showPageByNumber(1);

    expect(isPaginationShown(section('section-container-1'))).toBe(true);
    expect(isPaginationHidden(section('section-container-2'))).toBe(true);
    expect(isPaginationHidden(section('section-container-3'))).toBe(true);
  });

  it('refresh() re-applies visibility for the current page', async () => {
    const api = await loadPagination();

    expect(api.refresh()).toBe(true);
    expect(isPaginationShown(section('section-container-1'))).toBe(true);
    expect(isPaginationHidden(section('section-container-2'))).toBe(true);
  });

  it('shows all sections when data-is-paginated is false', async () => {
    const html = PAGINATED_FIXTURE.replace(
      'data-is-paginated="true"',
      'data-is-paginated="false"',
    );
    await loadPagination(html);

    expect(isPaginationShown(section('section-container-1'))).toBe(true);
    expect(isPaginationShown(section('section-container-2'))).toBe(true);
    expect(isPaginationShown(section('section-container-3'))).toBe(true);
  });

  it('shows all sections when data-is-paginated is absent', async () => {
    const html = PAGINATED_FIXTURE.replace(' data-is-paginated="true"', '');
    await loadPagination(html);

    expect(isPaginationShown(section('section-container-1'))).toBe(true);
    expect(isPaginationShown(section('section-container-2'))).toBe(true);
    expect(isPaginationShown(section('section-container-3'))).toBe(true);
  });

  it('showPageByNumber works without a leaked PAGINATION_LABELS global', async () => {
    const api = await loadPagination();
    delete window.PAGINATION_LABELS;
    delete globalThis.PAGINATION_LABELS;
    vi.unstubAllGlobals();
    window.scrollTo = vi.fn();

    expect(() => api.showPageByNumber(2)).not.toThrow();
    expect(api.getCurrentPageNumber()).toBe(2);
    expect(isPaginationShown(section('section-container-2'))).toBe(true);
  });

  it('does not throw when #sections-container is missing', async () => {
    await expect(loadPagination('<p>no sections</p>')).resolves.toBeUndefined();
    expect(window.__ifrcPagination).toBeUndefined();
  });
});
