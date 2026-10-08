/**
 * Keep these cases aligned with tests/unit/test_utils/test_matrix_calculation.py.
 */
import { describe, it, expect } from 'vitest';
import {
  columnCountsTowardRowTotal,
  compileCalculation,
  evaluateMatrixRow,
  formatFormulaNumber,
  formatFormulaNumberForDisplay,
} from '../../../app/static/js/forms/modules/matrix/calculation.js';

function cols() {
  return [
    { name: 'income', type: 'number_whole' },
    { name: 'grant', type: 'number_whole' },
    { name: 'expenditure', type: 'number_whole' },
    { name: 'done', type: 'tick' },
    { name: 'part', type: 'number_whole' },
    { name: 'whole', type: 'number_whole' },
  ];
}

function calc(name, operation, extra = {}) {
  return { name, type: 'calculated', calculation: { operation, ...extra } };
}

describe('matrix calculated columns', () => {
  it('sums blanks as zero and skips them inside SUM', () => {
    const columns = cols().concat([calc('total', 'sum', { sources: ['income', 'grant', 'expenditure'] })]);
    const filled = evaluateMatrixRow(columns, { income: 1, grant: '', expenditure: 3 }).total;
    const empty = evaluateMatrixRow(columns, {}).total;
    expect(filled).toEqual({ value: 4, error: null });
    expect(empty).toEqual({ value: 0, error: null });
  });

  it('leaves AVERAGE MIN and MAX blank when every input is blank', () => {
    const columns = cols().concat([
      calc('avg', 'average', { sources: ['income', 'expenditure'] }),
      calc('low', 'min', { sources: ['income', 'expenditure'] }),
      calc('high', 'max', { sources: ['income', 'expenditure'] }),
    ]);
    const row = evaluateMatrixRow(columns, { income: 2, expenditure: '' });
    expect(row.avg.value).toBe(2);
    expect(row.low.value).toBe(2);
    expect(row.high.value).toBe(2);
    const blank = evaluateMatrixRow(columns, {});
    expect(blank.avg).toEqual({ value: null, error: null });
    expect(blank.low.value).toBeNull();
    expect(blank.high.value).toBeNull();
  });

  it('counts numbers and filled cells, and treats ticks as 0 or 1', () => {
    const columns = cols().concat([
      calc('numbers', 'count', { sources: ['income', 'grant'] }),
      calc('filled', 'count_filled', { sources: ['income', 'grant'] }),
      calc('ticks', 'sum', { sources: ['done'] }),
    ]);
    const row = evaluateMatrixRow(columns, { income: 0, grant: '' });
    expect(row.numbers.value).toBe(1);
    expect(row.filled.value).toBe(1);
    expect(evaluateMatrixRow(columns, {}).ticks.value).toBe(0);
    expect(evaluateMatrixRow(columns, { done: '1' }).ticks.value).toBe(1);
  });

  it('compiles difference, percentage, and product', () => {
    const columns = cols().concat([
      calc('balance', 'difference', { sources: ['income', 'grant'], subtrahends: ['expenditure'] }),
      calc('share', 'percentage', { sources: ['part'], denominators: ['whole'] }),
      calc('area', 'product', { sources: ['income', 'grant'] }),
    ]);
    const row = evaluateMatrixRow(columns, {
      income: 10, grant: 5, expenditure: 3, part: 1, whole: 4,
    });
    expect(row.balance.value).toBe(12);
    expect(row.share.value).toBe(25);
    expect(row.area.value).toBe(50);
    const zeroDen = evaluateMatrixRow(columns, { part: 1, whole: 0 });
    expect(zeroDen.share).toEqual({ value: null, error: null });
    expect(compileCalculation({
      operation: 'difference', sources: ['income'], subtrahends: ['expenditure'],
    })).toBe('SUM(income) - SUM(expenditure)');
    const bare = evaluateMatrixRow([
      { name: 'income', type: 'number_whole' },
      { name: 'grant', type: 'number_whole' },
      { name: 'total', type: 'calculated', calculation: { operation: 'formula', formula: 'income + grant' } },
    ], { income: 2, grant: 3 });
    expect(bare.total.value).toBe(5);
  });

  it('evaluates IF, ROUND, and blank-as-zero', () => {
    const columns = cols().concat([
      {
        name: 'net',
        type: 'calculated',
        calculation: {
          operation: 'formula',
          formula: 'IF({whole} > 0, ROUND({part} / {whole} * 100, 1), 0)',
          blank_as_zero: true,
        },
      },
      {
        name: 'strict',
        type: 'calculated',
        calculation: { operation: 'formula', formula: '{income} + {grant}', blank_as_zero: false },
      },
    ]);
    const row = evaluateMatrixRow(columns, { part: 1, whole: 4, income: 2 });
    expect(row.net.value).toBe(25);
    expect(row.strict).toEqual({ value: null, error: null });
    expect(evaluateMatrixRow(columns, { part: 1, whole: 8 }).net.value).toBe(12.5);
    expect(formatFormulaNumber(1.25, 1)).toBe('1.3');
    expect(formatFormulaNumberForDisplay(1234567, 0)).toBe(
      new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(1234567),
    );
  });

  it('short-circuits IF and reports cycles, unknown columns, and division by zero', () => {
    const safe = evaluateMatrixRow([
      { name: 'whole', type: 'number_whole' },
      { name: 'safe', type: 'calculated', calculation: { operation: 'formula', formula: 'IF({whole} = 0, 5, 1 / {whole})' } },
    ], { whole: 0 });
    expect(safe.safe.value).toBe(5);

    const row = evaluateMatrixRow([
      { name: 'a', type: 'calculated', calculation: { operation: 'formula', formula: '{missing}' } },
      { name: 'b', type: 'calculated', calculation: { operation: 'formula', formula: '1 / 0' } },
      { name: 'c', type: 'calculated', calculation: { operation: 'formula', formula: '{d} + 1' } },
      { name: 'd', type: 'calculated', calculation: { operation: 'formula', formula: '{c} + 1' } },
    ], {});
    expect(row.a.error).toBe('Unknown column {missing}');
    expect(row.b.error).toBe('Division by zero');
    expect(row.c.error).toBe('Circular reference');
    expect(row.d.error).toBe('Circular reference');
  });

  it('lets calculated columns reference each other, including names with spaces', () => {
    const chained = evaluateMatrixRow([
      { name: 'income', type: 'number_whole' },
      calc('base', 'sum', { sources: ['income'] }),
      { name: 'doubled', type: 'calculated', calculation: { operation: 'formula', formula: '{base} * 2' } },
      { name: 'again', type: 'calculated', calculation: { operation: 'formula', formula: '{doubled} + 1' } },
    ], { income: 4 });
    expect(chained.base.value).toBe(4);
    expect(chained.doubled.value).toBe(8);
    expect(chained.again.value).toBe(9);

    const spaced = evaluateMatrixRow([
      { name: 'other income', type: 'number_whole' },
      { name: 'total', type: 'calculated', calculation: { operation: 'formula', formula: 'SUM({other income})' } },
    ], { 'other income': '1,250' });
    expect(spaced.total.value).toBe(1250);
  });

  it('keeps calculated columns out of the row total unless opted in', () => {
    expect(columnCountsTowardRowTotal({ name: 'a', type: 'number_whole' })).toBe(true);
    expect(columnCountsTowardRowTotal({ name: 'a', type: 'number_whole', include_in_row_total: false })).toBe(false);
    expect(columnCountsTowardRowTotal({ name: 'a', type: 'calculated' })).toBe(false);
    expect(columnCountsTowardRowTotal({ name: 'a', type: 'calculated', include_in_row_total: true })).toBe(true);
  });
});
