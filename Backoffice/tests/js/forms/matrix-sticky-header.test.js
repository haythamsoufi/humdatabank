/**
 * When a matrix column header stays pinned while the page scrolls.
 */
import { describe, it, expect } from 'vitest';

import { shouldPinMatrixHeader } from '../../../app/static/js/forms/modules/matrix/sticky-header.js';

const header = (top, bottom) => ({ top, bottom });
const table = (bottom) => ({ bottom });

describe('shouldPinMatrixHeader', () => {
  it('pins once the header has scrolled above the nav and the table is still on screen', () => {
    expect(shouldPinMatrixHeader(header(-80, -10), table(900), 56)).toBe(true);
  });

  it('does not pin while the header is still visible', () => {
    expect(shouldPinMatrixHeader(header(80, 160), table(900), 56)).toBe(false);
    expect(shouldPinMatrixHeader(header(20, 90), table(900), 56)).toBe(false);
  });

  it('lets go once the table has scrolled past the pinned header', () => {
    expect(shouldPinMatrixHeader(header(-400, -330), table(80), 56)).toBe(false);
  });

  it('ignores a header with no height', () => {
    expect(shouldPinMatrixHeader(header(0, 0), table(900), 56)).toBe(false);
  });
});
