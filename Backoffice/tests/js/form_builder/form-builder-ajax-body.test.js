/**
 * Form-builder saves must use the chunked WAF envelope.
 * A funding-matrix config is tens of KB; one base64 argument is what
 * production Application Gateway blocks with 403. Chunking does not shrink
 * the combined size, so large saves switch to gzip+hex (`gz:`).
 */
import { describe, it, expect, afterEach } from 'vitest';
import { WAF_JSON_MAX_CHUNK } from '../../../app/static/js/lib/waf-json-body.js';
import { encodeFormBuilderAjaxBody } from '../../../app/static/js/form_builder/modules/form-submit-ui.js';
import { fetchMatrixColumnMigrationPreview } from '../../../app/static/js/form_builder/modules/modal/matrix-column-migration.js';

async function decodeEnvelope(raw) {
    const envelope = JSON.parse(raw);
    let wire = envelope.payload || '';
    for (let i = 1; envelope['payload__c' + i]; i += 1) {
        wire += envelope['payload__c' + i];
    }
    if (wire.startsWith('gz:')) {
        const hex = wire.slice(3);
        const bytes = new Uint8Array(hex.length / 2);
        for (let i = 0; i < bytes.length; i += 1) {
            bytes[i] = parseInt(hex.substr(i * 2, 2), 16);
        }
        const source = new ReadableStream({
            start(controller) {
                controller.enqueue(bytes);
                controller.close();
            },
        });
        const reader = source.pipeThrough(new DecompressionStream('gzip')).getReader();
        const chunks = [];
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            chunks.push(value);
        }
        const text = new TextDecoder().decode(
            chunks.length === 1 ? chunks[0] : concatBytes(chunks)
        );
        return JSON.parse(text);
    }
    return JSON.parse(decodeURIComponent(escape(atob(wire))));
}

function concatBytes(chunks) {
    const total = chunks.reduce((n, c) => n + c.length, 0);
    const out = new Uint8Array(total);
    let offset = 0;
    chunks.forEach((chunk) => {
        out.set(chunk, offset);
        offset += chunk.length;
    });
    return out;
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
    it('keeps a small save as a single payload argument', async () => {
        const inner = { item_type: 'question', label: 'Name' };
        const raw = await encodeFormBuilderAjaxBody(inner);
        const envelope = assertChunked(raw);
        expect(envelope.payload__c1).toBeUndefined();
        expect(envelope.payload.startsWith('gz:')).toBe(false);
        expect(await decodeEnvelope(raw)).toEqual(inner);
    });

    it('returns null when there is nothing to send', async () => {
        expect(await encodeFormBuilderAjaxBody(null)).toBeNull();
        expect(await encodeFormBuilderAjaxBody(undefined)).toBeNull();
    });

    it('gzips a funding-matrix save so the combined arguments stay small', async () => {
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

        const raw = await encodeFormBuilderAjaxBody(inner);
        expect(raw).not.toContain('SUM(');
        expect(raw).not.toContain('<2026>');
        expect(raw).not.toContain('أولوية');
        expect(raw).not.toMatch(/[+/=]/);
        const envelope = assertChunked(raw);
        expect(envelope.payload.startsWith('gz:')).toBe(true);
        expect(envelope.payload__c1).toBeTruthy();
        const combined = Object.values(envelope).reduce((n, value) => n + value.length, 0);
        // The blocked production save was 24500 bytes of base64 arguments.
        expect(combined).toBeLessThan(8000);
        expect(await decodeEnvelope(raw)).toEqual(inner);
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
        expect(await decodeEnvelope(raw)).toEqual({ renames, version_id: 22 });
    });
});
