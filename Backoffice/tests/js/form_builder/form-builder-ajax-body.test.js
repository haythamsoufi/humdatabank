/**
 * Form-builder saves must use the chunked WAF envelope.
 * A funding-matrix config is tens of KB; one base64 argument is what
 * production Application Gateway blocks with 403.
 */
import { describe, it, expect, afterEach } from 'vitest';
import { WAF_JSON_MAX_CHUNK } from '../../../app/static/js/lib/waf-json-body.js';
import { encodeFormBuilderAjaxBody } from '../../../app/static/js/form_builder/modules/form-submit-ui.js';
import { fetchMatrixColumnMigrationPreview } from '../../../app/static/js/form_builder/modules/modal/matrix-column-migration.js';

function decodeEnvelope(raw) {
    const envelope = JSON.parse(raw);
    let b64 = envelope.payload || '';
    for (let i = 1; envelope['payload__c' + i]; i += 1) {
        b64 += envelope['payload__c' + i];
    }
    return JSON.parse(decodeURIComponent(escape(atob(b64))));
}

function assertChunked(raw) {
    const envelope = JSON.parse(raw);
    expect(envelope.payload).toBeTruthy();
    Object.entries(envelope).forEach(([key, value]) => {
        expect(key === 'payload' || /^payload__c\d+$/.test(key)).toBe(true);
        expect(value.length).toBeLessThanOrEqual(WAF_JSON_MAX_CHUNK);
    });
    return envelope;
}

describe('encodeFormBuilderAjaxBody', () => {
    it('keeps a small save as a single payload argument', () => {
        const inner = { item_type: 'question', label: 'Name' };
        const raw = encodeFormBuilderAjaxBody(inner);
        const envelope = assertChunked(raw);
        expect(envelope.payload__c1).toBeUndefined();
        expect(decodeEnvelope(raw)).toEqual(inner);
    });

    it('returns null when there is nothing to send', () => {
        expect(encodeFormBuilderAjaxBody(null)).toBeNull();
        expect(encodeFormBuilderAjaxBody(undefined)).toBeNull();
    });

    it('splits a funding-matrix save and hides formulas from the WAF', () => {
        const columns = Array.from({ length: 40 }, (_, i) => ({
            name: `sp${i}`,
            label: `Strategic priority ${i}`,
            type: i % 5 === 0 ? 'calculated' : 'number',
            ...(i % 5 === 0
                ? { calculation: { operation: 'formula', formula: `SUM(sp${i}_a, sp${i}_b)` } }
                : {}),
            name_translations: { fr: 'Priorité', ar: 'أولوية', es: 'Prioridad' },
        }));
        const inner = {
            item_type: 'matrix',
            label: 'Financial Overview',
            matrix_config: JSON.stringify({
                type: 'matrix',
                columns,
                column_groups: [{
                    label: 'Funding <2026>',
                    header_color: '#1e3a5f',
                    header_text_color: '#ffffff',
                    columns: ['sp0'],
                }],
                rows: [],
            }),
        };

        const raw = encodeFormBuilderAjaxBody(inner);
        expect(raw.length).toBeGreaterThan(5000);
        expect(raw).not.toContain('SUM(');
        expect(raw).not.toContain('<2026>');
        expect(raw).not.toContain('أولوية');
        const envelope = assertChunked(raw);
        expect(envelope.payload__c1).toBeTruthy();
        expect(decodeEnvelope(raw)).toEqual(inner);
    });
});

describe('fetchMatrixColumnMigrationPreview', () => {
    afterEach(() => {
        delete window.getFetch;
    });

    it('sends column codes in the same chunked envelope', async () => {
        const bodies = [];
        window.getFetch = () => async (_url, opts) => {
            bodies.push(opts.body);
            return {
                ok: true,
                json: async () => ({ success: true, preview: { rows_affected: 1, variables: [] } }),
            };
        };
        const renames = Array.from({ length: 80 }, (_, i) => ({
            from: `SP${i}`,
            to: `SP${i}_[assignment_year]`,
        }));

        const preview = await fetchMatrixColumnMigrationPreview(1433, renames, 22);

        expect(preview.rows_affected).toBe(1);
        const raw = bodies[0];
        expect(raw).not.toContain('[assignment_year]');
        const envelope = assertChunked(raw);
        expect(envelope.payload__c1).toBeTruthy();
        expect(decodeEnvelope(raw)).toEqual({ renames, version_id: 22 });
    });
});
