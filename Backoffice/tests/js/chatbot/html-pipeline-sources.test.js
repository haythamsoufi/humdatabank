import { describe, it, expect } from 'vitest';
import { HtmlPipelineMixin } from '../../../app/static/js/chatbot/html-pipeline.js';

function makeHost() {
    const host = Object.create(HtmlPipelineMixin);
    host._uiString = (key) => (key === 'responseSources' ? 'Sources' : '');
    host._tableDebugLog = () => {};
    return host;
}

const STRUCTURED_SOURCES_HTML = [
    '<p>No emergency documents matched.</p>',
    '<details class="chat-response-sources mt-2 border border-gray-200 rounded p-2 bg-gray-50">',
    '<summary class="cursor-pointer font-medium text-gray-700">Sources</summary>',
    '<div class="chat-response-sources-body mt-2 text-sm text-gray-600">',
    '<ul class="chat-response-sources-list">',
    '<li data-source-title="Syria Unified Plan 2024" data-source-kind="document" data-source-page="14" data-source-url="/api/ai/documents/12/download" data-source-detail="Contingency section" onclick="alert(1)">Syria Unified Plan 2024 — page 14</li>',
    '</ul>',
    '</div></details>',
].join('');

describe('chat response sources formatting', () => {
    it('keeps structured source attributes through sanitize and renders the chip', () => {
        const host = makeHost();
        const container = document.createElement('div');
        container.innerHTML = host.sanitizeHtml(STRUCTURED_SOURCES_HTML);

        const row = container.querySelector('[data-source-title]');
        expect(row).not.toBeNull();
        expect(row.getAttribute('data-source-title')).toBe('Syria Unified Plan 2024');
        expect(row.getAttribute('data-source-page')).toBe('14');
        expect(row.getAttribute('data-source-url')).toBe('/api/ai/documents/12/download');
        expect(row.hasAttribute('onclick')).toBe(false);

        host._formatChatResponseSources(container);

        expect(container.querySelector('details')).toBeNull();
        expect(container.querySelector('.chat-response-sources-chip')).not.toBeNull();
        expect(container.querySelector('.chat-response-sources-chip-count').textContent).toBe('1');
    });

    it('turns a prose Sources disclosure into the chip and drops the disclosure', () => {
        const host = makeHost();
        const container = document.createElement('div');
        container.innerHTML = [
            '<p>Result: 0 documents found.</p>',
            '<details class="chat-response-sources">',
            '<summary>Sources</summary>',
            '<div class="chat-response-sources-body">',
            'Uploaded document titles for Syria contained no emergency match.',
            '</div></details>',
        ].join('');

        host._formatChatResponseSources(container);

        expect(container.querySelector('details')).toBeNull();
        expect(container.querySelector('summary')).toBeNull();
        const chip = container.querySelector('.chat-response-sources-chip');
        expect(chip).not.toBeNull();
        expect(chip.getAttribute('data-sources-copy')).toContain('Uploaded document titles for Syria');
    });

    it('packages a markdown Sources sentence as structured rows before the chip', () => {
        const host = makeHost();
        const container = document.createElement('div');
        container.innerHTML = host.sanitizeHtml(
            'No matches.\n\n## Sources\n\nUploaded document titles for Syria contained no emergency match.\n'
        );
        const row = container.querySelector('[data-source-title]');
        expect(row).not.toBeNull();
        expect(row.getAttribute('data-source-title')).toContain('Uploaded document titles for Syria');

        host._formatChatResponseSources(container);

        expect(container.querySelector('details, summary')).toBeNull();
        expect(container.querySelector('.chat-response-sources-chip')).not.toBeNull();
    });

    it('places the chip on the action row after the icons, with a divider between', () => {
        const host = makeHost();
        const wrapper = document.createElement('div');
        wrapper.className = 'chat-message-wrapper is-bot';
        wrapper.innerHTML = [
            '<div class="chat-message-content">',
            '<p>No matches.</p>',
            '<div class="chat-response-sources chat-response-sources--chip" data-sources-formatted="1">',
            '<button type="button" class="chat-response-sources-chip"><i class="fas fa-book-open chat-response-sources-chip-icon"></i><span>Sources</span></button>',
            '</div></div>',
            '<div class="chat-message-actions">',
            '<button type="button" class="chat-message-action chat-message-action-copy"></button>',
            '<button type="button" class="chat-message-action chat-message-action-like"></button>',
            '</div>',
        ].join('');

        host._relocateSourcesChipIfNeeded(wrapper);

        const bar = wrapper.querySelector('.chat-message-actions');
        const kids = [...bar.children];
        expect(kids.map((el) => el.className)).toEqual([
            'chat-message-action chat-message-action-copy',
            'chat-message-action chat-message-action-like',
            'chat-message-actions-sep',
            'chat-response-sources-chip',
        ]);
        expect(wrapper.querySelector('.chat-message-content .chat-response-sources')).toBeNull();
        expect(wrapper.querySelector('.chat-response-sources-chip-icon')).not.toBeNull();
    });
});
