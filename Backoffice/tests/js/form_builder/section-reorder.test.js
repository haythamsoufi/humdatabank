import { describe, it, expect } from 'vitest';
import { ordersForSequence } from '../../../app/static/js/form_builder/modules/section-reorder.js';

describe('ordersForSequence', () => {
    it('writes the same numbers back in visual order', () => {
        expect(ordersForSequence([3, 1, 2])).toEqual([1, 2, 3]);
    });

    it('leaves sections that have no number untouched', () => {
        expect(ordersForSequence([4, null, 2])).toEqual([2, null, 4]);
    });

    it('replaces duplicate numbers so two sections do not share one', () => {
        expect(ordersForSequence([1, 1, 2])).toEqual([1, 2, 3]);
    });
});
