/**
 * @jest-environment jsdom
 */
import {
    normalizeChartPayload,
    normalizeBarChartPayload,
    normalizePieChartPayload
} from '../../../app/static/js/reports/chart-payload-normalize.js';

describe('ReportChartNormalize', () => {
    test('normalizeChartPayload accepts line series', () => {
        const out = normalizeChartPayload({
            type: 'line',
            metric: 'Volunteers',
            series: [{ x: 2024, y: 10 }, { x: 2025, y: 20 }]
        });
        expect(out).not.toBeNull();
        expect(out.type).toBe('line');
        expect(out.series).toHaveLength(2);
    });

    test('normalizeBarChartPayload accepts categories', () => {
        const out = normalizeBarChartPayload({
            type: 'bar',
            categories: [{ label: 'A', value: 1 }, { label: 'B', value: 2 }]
        });
        expect(out).not.toBeNull();
        expect(out.categories).toHaveLength(2);
    });

    test('normalizePieChartPayload accepts slices', () => {
        const out = normalizePieChartPayload({
            type: 'pie',
            slices: [{ label: 'Yes', value: 3 }, { label: 'No', value: 7 }]
        });
        expect(out).not.toBeNull();
        expect(out.slices).toHaveLength(2);
    });
});
