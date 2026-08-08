/**
 * Entry form bootstrap — gateway HTML must not crash; user sees warning.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

const noop = () => {};

vi.mock('../../../app/static/js/forms/modules/form-optimization.js', () => ({ initFormOptimization: noop }));
vi.mock('../../../app/static/js/forms/modules/mobile-nav.js', () => ({ initMobileNav: noop }));
vi.mock('../../../app/static/js/forms/modules/field-management.js', () => ({ initFieldManagement: noop }));
vi.mock('../../../app/static/js/forms/modules/conditions.js', () => ({ initConditions: noop }));
vi.mock('../../../app/static/js/forms/modules/formatting.js', () => ({ initFormatting: noop }));
vi.mock('../../../app/static/js/forms/modules/layout.js', () => ({ initLayout: noop }));
vi.mock('../../../app/static/js/forms/modules/multi-select.js', () => ({ initMultiSelect: noop }));
vi.mock('../../../app/static/js/forms/modules/question-other-option.js', () => ({ initQuestionOtherOption: noop }));
vi.mock('../../../app/static/js/forms/modules/checkbox-handlers.js', () => ({
  initCheckboxHandlers: noop,
  handleYesNoCheckbox: noop,
}));
vi.mock('../../../app/static/js/forms/modules/data-availability.js', () => ({ initDataAvailability: noop }));
vi.mock('../../../app/static/js/forms/modules/disability-questions.js', () => ({ initDisabilityQuestions: noop }));
vi.mock('../../../app/static/js/forms/modules/unique-section-options.js', () => ({ initUniqueSectionOptions: noop }));
vi.mock('../../../app/static/js/forms/modules/disaggregation-calculator.js', () => ({ initDisaggregationCalculator: noop }));
vi.mock('../../../app/static/js/forms/modules/form-validation.js', () => ({ initializeFormValidation: noop }));
vi.mock('../../../app/static/js/forms/modules/ajax-save.js', () => ({
  initAjaxSave: noop,
  triggerSave: noop,
  isSavingForm: () => false,
}));
vi.mock('../../../app/static/js/forms/modules/session-keepalive.js', () => ({ initSessionKeepalive: noop }));
vi.mock('../../../app/static/js/forms/modules/public-drafts.js', () => ({ initPublicDrafts: noop }));
vi.mock('../../../app/static/js/forms/modules/auth-drafts.js', () => ({
  initAuthDrafts: noop,
  prepareAuthDraftsStore: noop,
}));
vi.mock('../../../app/static/js/forms/modules/tooltips.js', () => ({ initTooltips: noop }));
vi.mock('../../../app/static/js/forms/modules/form-events.js', () => ({ initFormEvents: noop }));
vi.mock('../../../app/static/js/forms/modules/form-item-utils.js', () => ({
  cleanupInputValues: noop,
  setupNumericInputJsonSupport: noop,
}));
vi.mock('../../../app/static/js/forms/modules/ai-opinions.js', () => ({ initAiOpinions: noop }));
vi.mock('../../../app/static/js/forms/modules/entry-form-progress.js', () => ({
  initCompletionGapHighlight: noop,
  initCompletionRateRefresh: noop,
  refreshVisibleCompletionRate: vi.fn().mockResolvedValue(undefined),
  applyCompletionRate: noop,
}));

describe('main.js entry-bootstrap', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <button id="completion-gap-btn" data-aes-id="99"></button>
      <span id="completion-rate-display">…</span>
    `;
    window.__formFeatures = {
      matrix: false,
      repeat: false,
      dynamicIndicators: false,
      documents: false,
      calculatedLists: false,
      pdfExport: false,
      excelExport: false,
      discussion: false,
    };
    window.showAlert = vi.fn();
    window.apiFetch = vi.fn().mockRejectedValue(
      Object.assign(new Error('HTTP 502: Bad Gateway'), { status: 502 }),
    );
    delete window.__entryBootstrapPromise;
    delete window.__entryBootstrap;
  });

  afterEach(() => {
    delete window.showAlert;
    delete window.apiFetch;
    delete window.__entryBootstrapPromise;
    delete window.__entryBootstrap;
    document.body.innerHTML = '';
    vi.resetModules();
  });

  it('shows warning and nulls bootstrap on gateway failure', async () => {
    vi.resetModules();
    await import('../../../app/static/js/forms/main.js');
    const data = await window.__entryBootstrapPromise;
    expect(data).toBeNull();
    expect(window.__entryBootstrap).toBeNull();
    expect(window.showAlert).toHaveBeenCalledWith(
      expect.stringMatching(/Could not load form data/i),
      'warning',
    );
  });
});
