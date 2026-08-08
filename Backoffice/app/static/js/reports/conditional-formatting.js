/** Threshold-based conditional formatting for KPI/table widgets. */

export function applyConditionalFormatting(element, value, chartOptions) {
    const thresholds = chartOptions?.thresholds || [];
    if (!thresholds.length || value == null || !Number.isFinite(Number(value))) return;
    const num = Number(value);
    for (const rule of thresholds) {
        const target = Number(rule.value);
        const ok = (
            (rule.operator === 'lt' && num < target) ||
            (rule.operator === 'lte' && num <= target) ||
            (rule.operator === 'gt' && num > target) ||
            (rule.operator === 'gte' && num >= target) ||
            (rule.operator === 'eq' && num === target) ||
            (rule.operator === 'neq' && num !== target)
        );
        if (ok && rule.color) {
            element.style.color = rule.color;
            return;
        }
    }
}

export function rowCellStyle(value, chartOptions) {
    const thresholds = chartOptions?.thresholds || [];
    if (!thresholds.length || value == null || !Number.isFinite(Number(value))) return '';
    const num = Number(value);
    for (const rule of thresholds) {
        const target = Number(rule.value);
        const ok = (
            (rule.operator === 'lt' && num < target) ||
            (rule.operator === 'lte' && num <= target) ||
            (rule.operator === 'gt' && num > target) ||
            (rule.operator === 'gte' && num >= target) ||
            (rule.operator === 'eq' && num === target) ||
            (rule.operator === 'neq' && num !== target)
        );
        if (ok && rule.color) return 'color:' + rule.color;
    }
    return '';
}
