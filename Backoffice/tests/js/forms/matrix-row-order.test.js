import { describe, expect, it } from 'vitest';

import { compareMatrixRowLabels, matrixRowPeriodKey } from '../../../app/static/js/forms/modules/matrix/row-order.js';

describe('matrix row header order', () => {
  it('orders period labels by calendar start, not alphabetically', () => {
    const labels = ['Jan-Jun 2026', '2025', 'Jul-Dec 2025', 'Q1 2026', '2026'];
    labels.sort(compareMatrixRowLabels);
    expect(labels).toEqual(['2025', 'Jul-Dec 2025', '2026', 'Jan-Jun 2026', 'Q1 2026']);
  });

  it('keeps period rows together and names alphabetical', () => {
    const labels = ['Zambia', '2026', 'Botswana', '2025'];
    labels.sort(compareMatrixRowLabels);
    expect(labels).toEqual(['2025', '2026', 'Botswana', 'Zambia']);
  });

  it('keeps country names alphabetical and numeric labels in number order', () => {
    const labels = ['Zambia', 'Botswana', 'Row 10', 'Row 2'];
    labels.sort(compareMatrixRowLabels);
    expect(labels).toEqual(['Botswana', 'Row 2', 'Row 10', 'Zambia']);
    expect(matrixRowPeriodKey('Botswana')).toBeNull();
  });
});
