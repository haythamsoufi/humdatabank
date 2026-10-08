import { describe, it, expect } from 'vitest';
import { __nextVariableCellValue } from '../../../app/static/js/forms/modules/matrix/formatting.js';

const cleared = { original: 200000, modified: '', isModified: true };
const reported = { original: 616508, modified: 439311, isModified: true };

describe('variable cell save', () => {
  it('keeps a cleared structured cell when the blank input was not edited', () => {
    expect(__nextVariableCellValue({
      existing: cleared, rawValue: '', maxDecimals: 0, userEdited: false,
    })).toEqual({ action: 'keep' });
  });

  it('keeps a reported structured cell instead of flattening it', () => {
    expect(__nextVariableCellValue({
      existing: reported, rawValue: '439311', maxDecimals: 0, userEdited: false,
    })).toEqual({ action: 'keep' });
  });

  it('does not invent a blank for an empty untouched cell', () => {
    expect(__nextVariableCellValue({
      existing: undefined, rawValue: '', maxDecimals: 0, userEdited: false,
    })).toEqual({ action: 'keep' });
  });

  it('keeps a stored number when its input is empty and was not edited', () => {
    expect(__nextVariableCellValue({
      existing: '452281', rawValue: '', maxDecimals: 0, userEdited: false,
    })).toEqual({ action: 'keep' });
  });

  it('stores a plain scalar for a figure the user typed', () => {
    expect(__nextVariableCellValue({
      existing: cleared, rawValue: '50', maxDecimals: 0, userEdited: true,
    })).toEqual({ action: 'set', value: '50' });
  });

  it('stores a blank when the user clears the cell', () => {
    expect(__nextVariableCellValue({
      existing: '452281', rawValue: '', maxDecimals: 0, userEdited: true,
    })).toEqual({ action: 'set', value: '' });
  });
});
