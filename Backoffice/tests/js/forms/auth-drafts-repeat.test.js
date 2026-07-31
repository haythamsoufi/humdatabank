/**
 * Tests for ensureRepeatEntriesFromDraftData (repeat row creation before draft restore).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

describe('ensureRepeatEntriesFromDraftData', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div id="section-container-7" data-section-type="repeat">
        <div id="repeat-entries-7">
          <div class="repeat-entry" data-repeat-instance="1" id="repeat-entry-7-1">
            <div class="form-item-block" data-item-id="field-1">
              <input name="repeat_7_1_field_0" value="">
            </div>
          </div>
        </div>
      </div>`;
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('creates missing repeat entries inferred from draft field names', async () => {
    const { ensureRepeatEntriesFromDraftData } = await import(
      '../../../app/static/js/forms/modules/repeat-sections.js'
    );

    ensureRepeatEntriesFromDraftData({
      repeat_7_1_field_0: 'a',
      repeat_7_3_field_0: 'c',
    });

    const entries = document.querySelectorAll('#repeat-entries-7 .repeat-entry');
    expect(entries.length).toBeGreaterThanOrEqual(3);
    expect(document.querySelector('.repeat-entry[data-repeat-instance="3"]')).toBeTruthy();
  });

  it('no-ops when draft has no repeat keys', async () => {
    const { ensureRepeatEntriesFromDraftData } = await import(
      '../../../app/static/js/forms/modules/repeat-sections.js'
    );
    ensureRepeatEntriesFromDraftData({ indicator_1: 'x' });
    expect(document.querySelectorAll('#repeat-entries-7 .repeat-entry').length).toBe(1);
  });
});
