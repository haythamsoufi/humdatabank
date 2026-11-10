import { annotateDuplicateRows, summarizeDuplicateRows } from '../../../app/static/js/admin/ai-documents/duplicates.js';
import { renderMarkdown, sanitizeHtml } from '../../../app/static/js/admin/ai-documents/markdown.js';

describe('ai document duplicate grouping', () => {
    test('keeps the linked copy and does not mix a hashed file with a URL-only copy', () => {
        const rows = annotateDuplicateRows([
            { id: 1, content_hash: 'abc', source_url: 'https://example.org/a.pdf', processing_status: 'completed', total_chunks: 2 },
            { id: 2, content_hash: 'abc', source_url: 'https://example.org/a.pdf', processing_status: 'failed', total_chunks: 9, submitted_document_id: 9 },
            { id: 3, content_hash: '', source_url: 'https://example.org/a.pdf', processing_status: 'completed', total_chunks: 4 },
        ]);
        const byId = Object.fromEntries(rows.map((row) => [row.id, row]));
        expect(byId[2].is_duplicate_keeper).toBe(true);
        expect(byId[1].duplicate_keeper_id).toBe(2);
        expect(byId[3].is_duplicate).toBe(false);
        expect(summarizeDuplicateRows(rows)).toMatchObject({ groups: 1, extras: 1 });
    });
});

describe('ai documents page entry', () => {
    test('loads the module graph', async () => {
        window.aiDocumentsConfig = window.aiDocumentsConfig || { t: {}, urls: {} };
        vi.stubGlobal('fetch', vi.fn(async () => ({
            ok: false,
            json: async () => ({ success: false, error: 'offline' }),
        })));
        await import('../../../app/static/js/admin/ai-documents.js');
    });
});

describe('ai answer markdown', () => {
    test('keeps nested lists when the list is flushed', () => {
        const html = renderMarkdown('- outer\n  - inner\n');
        expect(html).toContain('<li>outer<ul><li>inner</li></ul></li>');
    });

    test('strips event handlers from answer html', () => {
        const clean = sanitizeHtml('<p onclick="alert(1)">ok</p><a href="javascript:alert(1)">x</a>');
        expect(clean).not.toContain('onclick');
        expect(clean).not.toContain('javascript:');
        expect(clean).toContain('ok');
    });
});
