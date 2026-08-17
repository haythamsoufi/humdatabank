/**
 * Pure helpers for matrix row-total keys, validation, and effective values.
 * Does not cover tooltip DOM, SVG indicators, or calculateMatrixTotals.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
  debugLog: vi.fn(),
  debugWarn: vi.fn(),
  debugError: vi.fn(),
}));

import {
  __isRowTotalCellKey,
  __rowTotalCellKey,
  __rowTotalManualEnabled,
  __rowTotalValidation,
  __parseRowTotalManualValue,
  __rowTotalConflictType,
  __rowTotalConflictMessage,
  __storedRowTotalManualScalar,
  __computedRowTotalFromData,
  __effectiveRowTotalValue,
} from '../../../app/static/js/forms/modules/matrix/totals.js';

describe('matrix row-total helpers', () => {
  beforeEach(() => {
    delete window.__numericUnformat;
  });

  afterEach(() => {
    delete window.__numericUnformat;
  });

  describe('__isRowTotalCellKey', () => {
    it('is true only for strings ending with _Total', () => {
      expect(__isRowTotalCellKey('row1_Total')).toBe(true);
      expect(__isRowTotalCellKey('_Total')).toBe(true);
      expect(__isRowTotalCellKey('row1_Amount')).toBe(false);
      expect(__isRowTotalCellKey('Total')).toBe(false);
      expect(__isRowTotalCellKey('row1_total')).toBe(false);
    });

    it('is false for empty or non-string keys', () => {
      expect(__isRowTotalCellKey('')).toBe(false);
      expect(__isRowTotalCellKey(null)).toBe(false);
      expect(__isRowTotalCellKey(undefined)).toBe(false);
      expect(__isRowTotalCellKey(123)).toBe(false);
      expect(__isRowTotalCellKey({ key: 'row1_Total' })).toBe(false);
    });
  });

  describe('__rowTotalCellKey', () => {
    it('joins rowId with the Total column name', () => {
      expect(__rowTotalCellKey('row1')).toBe('row1_Total');
      expect(__rowTotalCellKey('abc-42')).toBe('abc-42_Total');
    });
  });

  describe('__rowTotalManualEnabled', () => {
    it('is true for true / "true" / 1 / "1"', () => {
      expect(__rowTotalManualEnabled({ row_total_manual_enabled: true })).toBe(true);
      expect(__rowTotalManualEnabled({ row_total_manual_enabled: 'true' })).toBe(true);
      expect(__rowTotalManualEnabled({ row_total_manual_enabled: 1 })).toBe(true);
      expect(__rowTotalManualEnabled({ row_total_manual_enabled: '1' })).toBe(true);
    });

    it('is false when missing or disabled', () => {
      expect(__rowTotalManualEnabled(undefined)).toBe(false);
      expect(__rowTotalManualEnabled({})).toBe(false);
      expect(__rowTotalManualEnabled({ row_total_manual_enabled: false })).toBe(false);
      expect(__rowTotalManualEnabled({ row_total_manual_enabled: 'false' })).toBe(false);
      expect(__rowTotalManualEnabled({ row_total_manual_enabled: 0 })).toBe(false);
    });
  });

  describe('__rowTotalValidation', () => {
    it('returns strict or partial when set, otherwise none', () => {
      expect(__rowTotalValidation({ row_total_validation: 'strict' })).toBe('strict');
      expect(__rowTotalValidation({ row_total_validation: 'partial' })).toBe('partial');
      expect(__rowTotalValidation({ row_total_validation: 'none' })).toBe('none');
      expect(__rowTotalValidation({ row_total_validation: 'other' })).toBe('none');
      expect(__rowTotalValidation({})).toBe('none');
      expect(__rowTotalValidation(undefined)).toBe('none');
    });
  });

  describe('__parseRowTotalManualValue', () => {
    it('returns null for null, undefined, empty, or non-finite values', () => {
      expect(__parseRowTotalManualValue(null)).toBeNull();
      expect(__parseRowTotalManualValue(undefined)).toBeNull();
      expect(__parseRowTotalManualValue('')).toBeNull();
      expect(__parseRowTotalManualValue('abc')).toBeNull();
      expect(__parseRowTotalManualValue(Infinity)).toBeNull();
    });

    it('parses plain numbers without __numericUnformat', () => {
      expect(__parseRowTotalManualValue(0)).toBe(0);
      expect(__parseRowTotalManualValue('42')).toBe(42);
      expect(__parseRowTotalManualValue(12.5)).toBe(12.5);
      expect(__parseRowTotalManualValue('1,234')).toBeNull();
    });

    it('uses window.__numericUnformat when present (e.g. 1,234)', () => {
      window.__numericUnformat = (s) => String(s).replace(/,/g, '');
      expect(__parseRowTotalManualValue('1,234')).toBe(1234);
      expect(__parseRowTotalManualValue('12')).toBe(12);
    });
  });

  describe('__rowTotalConflictType', () => {
    it('returns null when the manual value is missing', () => {
      expect(__rowTotalConflictType(10, null, 'strict')).toBeNull();
      expect(__rowTotalConflictType(10, '', 'partial')).toBeNull();
    });

    it('strict: mismatch is error, match is null', () => {
      expect(__rowTotalConflictType(10, 7, 'strict')).toBe('error');
      expect(__rowTotalConflictType(10, 10, 'strict')).toBeNull();
    });

    it('partial: manual < auto is error; manual > auto is warning; equal is null', () => {
      expect(__rowTotalConflictType(10, 7, 'partial')).toBe('error');
      expect(__rowTotalConflictType(10, 15, 'partial')).toBe('warning');
      expect(__rowTotalConflictType(10, 10, 'partial')).toBeNull();
    });

    it('none or undefined validation: mismatch is warning', () => {
      expect(__rowTotalConflictType(10, 7, 'none')).toBe('warning');
      expect(__rowTotalConflictType(10, 7, undefined)).toBe('warning');
      expect(__rowTotalConflictType(10, 10, 'none')).toBeNull();
    });
  });

  describe('__rowTotalConflictMessage', () => {
    it('describes the manual vs breakdown difference', () => {
      const msg = __rowTotalConflictMessage(15, 10);
      expect(msg).toContain('Manual total');
      expect(msg).toContain('differs from breakdown sum');
    });
  });

  describe('__storedRowTotalManualScalar', () => {
    it('parses a modified object and ignores objects without a modification', () => {
      expect(__storedRowTotalManualScalar({ isModified: true, modified: 50 })).toBe(50);
      expect(__storedRowTotalManualScalar({ isModified: true, modified: '8' })).toBe(8);
      expect(__storedRowTotalManualScalar({ isModified: true, modified: '' })).toBeNull();
      expect(__storedRowTotalManualScalar({ isModified: false, modified: 50 })).toBeNull();
      expect(__storedRowTotalManualScalar({ original: 10 })).toBeNull();
    });

    it('parses scalars and returns null for empty stored values', () => {
      expect(__storedRowTotalManualScalar(42)).toBe(42);
      expect(__storedRowTotalManualScalar('99')).toBe(99);
      expect(__storedRowTotalManualScalar(null)).toBeNull();
      expect(__storedRowTotalManualScalar(undefined)).toBeNull();
      expect(__storedRowTotalManualScalar('')).toBeNull();
    });
  });

  describe('__computedRowTotalFromData', () => {
    it('sums data-column cells and skips Total when it is not in columns', () => {
      const data = {
        row1_A: 3,
        row1_B: '4',
        row1_C: '',
        row1_Total: 999,
      };
      expect(__computedRowTotalFromData(data, 'row1', ['A', 'B', 'C'])).toBe(7);
    });

    it('uses object column .name and __cellValueToNumber for objects/strings/empty', () => {
      const data = {
        row1_A: { original: 10, isModified: true, modified: 15 },
        row1_B: '5',
        row1_C: null,
      };
      const columns = [{ name: 'A' }, { name: 'B' }, { name: 'C' }];
      expect(__computedRowTotalFromData(data, 'row1', columns)).toBe(20);
    });

    it('returns 0 for missing columns or empty data keys', () => {
      expect(__computedRowTotalFromData({}, 'row1', ['A', 'B'])).toBe(0);
      expect(__computedRowTotalFromData({ row1_A: 2 }, 'row1', null)).toBe(0);
      expect(__computedRowTotalFromData({ row1_A: 2 }, 'row1', [])).toBe(0);
    });
  });

  describe('__effectiveRowTotalValue', () => {
    const columns = ['A', 'B'];
    const data = {
      row1_A: 3,
      row1_B: 4,
      row1_Total: { isModified: true, modified: 20 },
    };

    it('returns the computed sum when manual totals are disabled', () => {
      expect(__effectiveRowTotalValue(data, 'row1', columns, false)).toBe(7);
    });

    it('uses the manual scalar when an isModified object is present', () => {
      expect(__effectiveRowTotalValue(data, 'row1', columns, true)).toBe(20);
    });

    it('falls back to computed when no usable manual scalar is stored', () => {
      const noManual = { row1_A: 3, row1_B: 4 };
      expect(__effectiveRowTotalValue(noManual, 'row1', columns, true)).toBe(7);

      const unmodified = {
        row1_A: 3,
        row1_B: 4,
        row1_Total: { isModified: false, modified: 20 },
      };
      expect(__effectiveRowTotalValue(unmodified, 'row1', columns, true)).toBe(7);
    });

    it('uses a stored scalar total of 0 when manual mode is on', () => {
      const zeroManual = {
        row1_A: 3,
        row1_B: 4,
        row1_Total: { isModified: true, modified: 0 },
      };
      expect(__effectiveRowTotalValue(zeroManual, 'row1', columns, true)).toBe(0);
    });
  });
});
