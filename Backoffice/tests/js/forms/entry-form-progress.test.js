/**
 * Unit tests for entry-form-progress.js (completion rate, section icons, gap highlights).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
  debugLog: vi.fn(),
  debugWarn: vi.fn(),
  debugError: vi.fn(),
}));

let loadedTeardown = null;

async function loadProgress() {
  loadedTeardown?.();
  loadedTeardown = null;
  vi.resetModules();
  const mod = await import('../../../app/static/js/forms/modules/entry-form-progress.js');
  loadedTeardown = mod.teardownCompletionRateRefresh;
  return mod;
}

function jsonResponse(body, { ok = true, status = 200, contentType = 'application/json' } = {}) {
  return {
    ok,
    status,
    headers: {
      get: (name) => (String(name).toLowerCase() === 'content-type' ? contentType : null),
    },
    json: async () => body,
  };
}

function setupProgressDom({
  rateDisplay = true,
  gapButton = true,
  aesId = '42',
  completionRate = '',
  sections = [
    { id: '10', size: 'w-4' },
    { id: '20', size: 'w-3' },
  ],
  items = [{ id: '101' }, { id: '102' }],
} = {}) {
  const displayHtml = rateDisplay ? '<span id="completion-rate-display"></span>' : '';
  const rateAttr = completionRate === '' ? '' : ` data-completion-rate="${completionRate}"`;
  const btnHtml = gapButton
    ? `<button type="button" id="completion-gap-btn" data-aes-id="${aesId}"${rateAttr}>
         <span class="completion-gap-btn-label">Show me what I missed</span>
       </button>`
    : '';
  const sectionHtml = sections.map((s) => {
    const sizeClass = s.size === 'w-3' ? 'w-3 h-3' : 'w-4 h-4';
    return `<a class="section-link" data-section-id="section-container-${s.id}">
      <i class="section-status-icon ${sizeClass}"></i>
    </a>`;
  }).join('');
  const itemHtml = items.map((item) => {
    const hidden = item.hidden ? ' relevance-hidden' : '';
    const typeAttr = item.type ? ` data-item-type="${item.type}"` : '';
    return `<div class="form-item-block${hidden}" data-item-id="${item.id}"${typeAttr}>Item ${item.id}</div>`;
  }).join('');

  document.body.innerHTML = `
    ${displayHtml}
    ${btnHtml}
    <nav>${sectionHtml}</nav>
    <form>${itemHtml}</form>
  `;
}

function displayEl() {
  return document.getElementById('completion-rate-display');
}

function gapBtn() {
  return document.getElementById('completion-gap-btn');
}

function iconFor(sectionId) {
  return document.querySelector(
    `a.section-link[data-section-id="section-container-${sectionId}"] .section-status-icon`,
  );
}

describe('entry-form-progress', () => {
  beforeEach(() => {
    window.t = (k) => k;
    window.showFlashMessage = vi.fn();
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    delete window.t;
    delete window.showFlashMessage;
    delete window.getCsrfAwareFetch;
    delete window.getApiFetch;
    delete window.responseAsResult;
    delete window.collectHiddenFieldsForSubmission;
    loadedTeardown?.();
    loadedTeardown = null;
    delete document.body.dataset.completionRateRefreshInit;
    delete document.body.dataset.completionRateFromSave;
    document.body.innerHTML = '';
  });

  describe('applyCompletionRate', () => {
    it('returns false when the completion display is missing', async () => {
      setupProgressDom({ rateDisplay: false });
      const { applyCompletionRate } = await loadProgress();
      expect(applyCompletionRate(50)).toBe(false);
    });

    it('returns false when the rate is not numeric', async () => {
      setupProgressDom();
      const { applyCompletionRate } = await loadProgress();
      expect(applyCompletionRate('x')).toBe(false);
      expect(applyCompletionRate(null)).toBe(false);
      expect(applyCompletionRate(undefined)).toBe(false);
      expect(applyCompletionRate({})).toBe(false);
      expect(displayEl().textContent).toBe('');
    });

    it('accepts numeric strings', async () => {
      setupProgressDom();
      const { applyCompletionRate } = await loadProgress();
      expect(applyCompletionRate('50')).toBe(true);
      expect(displayEl().textContent).toBe('50.0%');
    });

    it('formats 0% in red and keeps the gap button enabled', async () => {
      setupProgressDom();
      displayEl().classList.add('text-green-700', 'text-gray-400');
      const { applyCompletionRate } = await loadProgress();

      expect(applyCompletionRate(0)).toBe(true);
      expect(displayEl().textContent).toBe('0.0%');
      expect(displayEl().classList.contains('text-red-600')).toBe(true);
      expect(displayEl().classList.contains('font-semibold')).toBe(true);
      expect(displayEl().classList.contains('text-green-700')).toBe(false);
      expect(displayEl().classList.contains('text-gray-400')).toBe(false);
      expect(gapBtn().dataset.completionRate).toBe('0');
      expect(gapBtn().disabled).toBe(false);
      expect(gapBtn().querySelector('.completion-gap-btn-label').textContent).toBe('Show me what I missed');
    });

    it('formats 50% in amber and stores the rate on the gap button', async () => {
      setupProgressDom();
      const { applyCompletionRate } = await loadProgress();

      expect(applyCompletionRate(50)).toBe(true);
      expect(displayEl().textContent).toBe('50.0%');
      expect(displayEl().classList.contains('text-amber-600')).toBe(true);
      expect(displayEl().classList.contains('text-red-600')).toBe(false);
      expect(displayEl().classList.contains('text-green-700')).toBe(false);
      expect(gapBtn().dataset.completionRate).toBe('50');
      expect(gapBtn().disabled).toBe(false);
    });

    it('formats 100% in green and disables the gap button', async () => {
      setupProgressDom();
      const { applyCompletionRate } = await loadProgress();

      expect(applyCompletionRate(100)).toBe(true);
      expect(displayEl().textContent).toBe('100.0%');
      expect(displayEl().classList.contains('text-green-700')).toBe(true);
      expect(displayEl().classList.contains('text-amber-600')).toBe(false);
      expect(gapBtn().dataset.completionRate).toBe('100');
      expect(gapBtn().disabled).toBe(true);
      expect(gapBtn().getAttribute('aria-label')).toBe('All countable items are complete');
    });
  });

  describe('updateSectionStatusIcons', () => {
    it('maps each STATUS_ICON_CLASSES key onto the matching section link', async () => {
      setupProgressDom({
        sections: [
          { id: '10', size: 'w-4' },
          { id: '20', size: 'w-4' },
          { id: '30', size: 'w-4' },
          { id: '40', size: 'w-4' },
        ],
      });
      const { updateSectionStatusIcons } = await loadProgress();

      updateSectionStatusIcons({
        10: 'Completed',
        20: 'in_progress',
        30: 'Not Started',
        40: 'N/A',
      });

      expect(iconFor('10').className).toContain('fa-check-circle');
      expect(iconFor('10').className).toContain('text-green-500');
      expect(iconFor('20').className).toContain('fa-pen');
      expect(iconFor('20').className).toContain('text-blue-500');
      expect(iconFor('30').className).toContain('fa-circle');
      expect(iconFor('30').className).toContain('text-gray-400');
      expect(iconFor('40').className).toContain('fa-minus-circle');
      expect(iconFor('40').className).toContain('text-gray-500');
    });

    it('falls back to Not Started for unknown statuses and ignores invalid payloads', async () => {
      setupProgressDom({ sections: [{ id: '10', size: 'w-4' }] });
      const icon = iconFor('10');
      icon.className = 'section-status-icon original';
      const { updateSectionStatusIcons } = await loadProgress();

      updateSectionStatusIcons(null);
      updateSectionStatusIcons('Completed');
      expect(icon.className).toBe('section-status-icon original');

      updateSectionStatusIcons({ 10: 'unknown-status' });
      expect(icon.classList.contains('fa-circle')).toBe(true);
      expect(icon.classList.contains('text-gray-400')).toBe(true);
      expect(icon.classList.contains('section-status-icon')).toBe(true);
    });

    it('preserves the compact w-3 icon size', async () => {
      setupProgressDom({ sections: [{ id: '20', size: 'w-3' }] });
      const { updateSectionStatusIcons } = await loadProgress();

      updateSectionStatusIcons({ 20: 'Completed' });
      expect(iconFor('20').classList.contains('w-3')).toBe(true);
      expect(iconFor('20').classList.contains('h-3')).toBe(true);
      expect(iconFor('20').classList.contains('w-4')).toBe(false);
    });
  });

  describe('applyEntryFormProgress', () => {
    it('applies completion_rate and section_statuses from a bootstrap payload', async () => {
      setupProgressDom({ sections: [{ id: '10', size: 'w-4' }] });
      const { applyEntryFormProgress } = await loadProgress();

      applyEntryFormProgress({
        completion_rate: 80,
        section_statuses: { 10: 'Completed' },
      });

      expect(displayEl().textContent).toBe('80.0%');
      expect(displayEl().classList.contains('text-green-700')).toBe(true);
      expect(iconFor('10').className).toContain('fa-check-circle');
    });

    it('is a no-op for invalid payloads or a non-numeric completion_rate', async () => {
      setupProgressDom();
      const { applyEntryFormProgress } = await loadProgress();

      applyEntryFormProgress(null);
      applyEntryFormProgress('x');
      applyEntryFormProgress({ completion_rate: 'nope' });
      expect(displayEl().textContent).toBe('');
    });

    it('applies a numeric-string completion_rate from the save payload', async () => {
      setupProgressDom();
      const { applyEntryFormProgress } = await loadProgress();

      applyEntryFormProgress({ completion_rate: '55.5' });
      expect(displayEl().textContent).toBe('55.5%');
      expect(document.body.dataset.completionRateFromSave).toBe('1');
    });

    it('clears active gap highlights when a new progress payload arrives', async () => {
      setupProgressDom({
        items: [{ id: '101' }, { id: '102' }],
        sections: [{ id: '10', size: 'w-4' }],
      });
      fetch.mockResolvedValue(jsonResponse({
        missing_items: [{ form_item_id: 101 }],
        section_ids: ['10'],
        missing_count: 1,
        completion_rate: 40,
      }));

      const { applyEntryFormProgress, initCompletionGapHighlight } = await loadProgress();
      initCompletionGapHighlight();
      gapBtn().click();
      await vi.waitFor(() => {
        expect(document.querySelector('[data-item-id="101"]').classList.contains('completion-gap-highlight')).toBe(true);
      });

      applyEntryFormProgress({ completion_rate: 70 });

      expect(document.querySelector('[data-item-id="101"]').classList.contains('completion-gap-highlight')).toBe(false);
      expect(document.querySelector('a.section-link').classList.contains('completion-gap-section')).toBe(false);
      expect(gapBtn().classList.contains('completion-gap-active')).toBe(false);
      expect(displayEl().textContent).toBe('70.0%');
    });
  });

  describe('initCompletionGapHighlight', () => {
    it('is a no-op without a gap button or aes id', async () => {
      setupProgressDom({ gapButton: false });
      const { initCompletionGapHighlight } = await loadProgress();
      expect(() => initCompletionGapHighlight()).not.toThrow();

      document.body.innerHTML = '<button type="button" id="completion-gap-btn"><span class="completion-gap-btn-label"></span></button>';
      initCompletionGapHighlight();
      expect(gapBtn().dataset.gapHighlightInit).toBeUndefined();
    });

    it('toggles highlights on incomplete form-item-blocks and skips hidden ones', async () => {
      setupProgressDom({
        items: [
          { id: '101' },
          { id: '102' },
          { id: '103', hidden: true },
        ],
        sections: [{ id: '10', size: 'w-4' }],
      });
      fetch.mockResolvedValue(jsonResponse({
        missing_items: [{ form_item_id: 101 }, { form_item_id: 103 }],
        section_ids: ['10'],
        missing_count: 2,
      }));

      const { initCompletionGapHighlight } = await loadProgress();
      initCompletionGapHighlight();
      initCompletionGapHighlight();

      gapBtn().click();
      await vi.waitFor(() => {
        expect(document.querySelector('[data-item-id="101"]').classList.contains('completion-gap-highlight')).toBe(true);
      });

      expect(document.querySelector('[data-item-id="102"]').classList.contains('completion-gap-highlight')).toBe(false);
      expect(document.querySelector('[data-item-id="103"]').classList.contains('completion-gap-highlight')).toBe(false);
      expect(document.querySelector('a.section-link').classList.contains('completion-gap-section')).toBe(true);
      expect(gapBtn().classList.contains('completion-gap-active')).toBe(true);
      expect(gapBtn().getAttribute('aria-pressed')).toBe('true');
      expect(gapBtn().querySelector('.completion-gap-btn-label').textContent).toBe('Clear highlights');
      expect(fetch).toHaveBeenCalledTimes(1);
      expect(fetch.mock.calls[0][0]).toBe('/api/forms/assignment/42/completion-gaps');
      expect(window.showFlashMessage).toHaveBeenCalledWith('Highlighted 1 missing item(s).', 'info');

      gapBtn().click();
      expect(document.querySelector('[data-item-id="101"]').classList.contains('completion-gap-highlight')).toBe(false);
      expect(gapBtn().classList.contains('completion-gap-active')).toBe(false);
      expect(gapBtn().getAttribute('aria-pressed')).toBe('false');
      expect(gapBtn().querySelector('.completion-gap-btn-label').textContent).toBe('Show me what I missed');
      expect(window.showFlashMessage).toHaveBeenCalledWith('Highlights cleared.', 'info');
    });
  });

  describe('refreshVisibleCompletionRate', () => {
    it('fetches the completion-rate endpoint and applies a numeric rate', async () => {
      setupProgressDom();
      fetch.mockResolvedValue(jsonResponse({ completion_rate: 75.5 }));
      const { refreshVisibleCompletionRate } = await loadProgress();

      const data = await refreshVisibleCompletionRate(7);
      expect(data).toEqual({ completion_rate: 75.5 });
      expect(displayEl().textContent).toBe('75.5%');
      expect(fetch).toHaveBeenCalledWith(
        '/api/forms/assignment/7/completion-rate',
        expect.objectContaining({
          credentials: 'same-origin',
          cache: 'no-store',
          headers: expect.objectContaining({ Accept: 'application/json' }),
        }),
      );
    });

    it('uses getCsrfAwareFetch when available instead of window.fetch', async () => {
      setupProgressDom();
      const csrfFetch = vi.fn().mockResolvedValue(jsonResponse({ completion_rate: 33 }));
      window.getCsrfAwareFetch = () => csrfFetch;
      const { refreshVisibleCompletionRate } = await loadProgress();

      await refreshVisibleCompletionRate(9);
      expect(csrfFetch).toHaveBeenCalledWith(
        '/api/forms/assignment/9/completion-rate',
        expect.any(Object),
      );
      expect(fetch).not.toHaveBeenCalled();
      expect(displayEl().textContent).toBe('33.0%');
    });

    it('throws when the completion-rate response is not ok', async () => {
      setupProgressDom();
      fetch.mockResolvedValue(jsonResponse({ error: 'fail' }, { ok: false, status: 500 }));
      const { refreshVisibleCompletionRate } = await loadProgress();

      await expect(refreshVisibleCompletionRate(1)).rejects.toThrow('HTTP 500');
      expect(displayEl().textContent).toBe('');
    });
  });

  describe('initCompletionRateRefresh', () => {
    it('is a no-op without aesId', async () => {
      setupProgressDom();
      const { initCompletionRateRefresh } = await loadProgress();

      initCompletionRateRefresh('');
      initCompletionRateRefresh(null);
      expect(document.body.dataset.completionRateRefreshInit).toBeUndefined();
    });

    it('debounces refresh on ifrc:relevance-settled and only initializes once', async () => {
      vi.useFakeTimers();
      setupProgressDom();
      fetch.mockResolvedValue(jsonResponse({ completion_rate: 40 }));
      const { initCompletionRateRefresh } = await loadProgress();

      initCompletionRateRefresh(5);
      expect(document.body.dataset.completionRateRefreshInit).toBe('1');
      initCompletionRateRefresh(99);

      document.dispatchEvent(new CustomEvent('ifrc:relevance-settled'));
      document.dispatchEvent(new CustomEvent('ifrc:relevance-settled'));
      expect(fetch).not.toHaveBeenCalled();

      await vi.advanceTimersByTimeAsync(300);
      expect(fetch).toHaveBeenCalledTimes(1);
      expect(fetch.mock.calls[0][0]).toBe('/api/forms/assignment/5/completion-rate');
      expect(displayEl().textContent).toBe('40.0%');
    });

    it('does not refetch after a save-applied rate while relevance is settling', async () => {
      vi.useFakeTimers();
      setupProgressDom();
      fetch.mockResolvedValue(jsonResponse({ completion_rate: 40 }));
      const { initCompletionRateRefresh, applyEntryFormProgress } = await loadProgress();

      initCompletionRateRefresh(5);
      applyEntryFormProgress({ completion_rate: 80 });
      expect(displayEl().textContent).toBe('80.0%');
      expect(document.body.dataset.completionRateFromSave).toBe('1');

      document.dispatchEvent(new CustomEvent('ifrc:relevance-settled'));
      await vi.advanceTimersByTimeAsync(300);

      expect(fetch).not.toHaveBeenCalled();
      expect(displayEl().textContent).toBe('80.0%');

      await vi.advanceTimersByTimeAsync(1000);
      document.dispatchEvent(new CustomEvent('ifrc:relevance-settled'));
      await vi.advanceTimersByTimeAsync(300);
      expect(fetch).toHaveBeenCalledTimes(1);
      expect(displayEl().textContent).toBe('40.0%');
    });
  });
});
