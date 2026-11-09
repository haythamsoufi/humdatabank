import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { DlpPolicyMixin } from '../../../app/static/js/chatbot/dlp-policy.js';

const CONFIRM_PAYLOAD = {
    error: 'Sensitive information detected (password). Remove it and send your message again.',
    error_type: 'dlp_requires_confirmation',
    dlp: { sensitive: true, findings: [{ kind: 'password', count: 1 }], recommendation: 'remove_or_confirm' },
};
const BLOCKED_PAYLOAD = {
    error: CONFIRM_PAYLOAD.error,
    error_type: 'dlp_blocked',
    dlp: { sensitive: true, findings: [{ kind: 'password', count: 1 }] },
};
const PREVIOUS_HISTORY = [
    { isUser: true, message: 'Earlier question' },
    { isUser: false, message: 'Earlier answer' },
];
const REJECTED_TEXT = 'my password: hunter2';

function makeHost() {
    document.body.innerHTML = `
        <div id="messages">
            <div class="chat-message-wrapper is-user" data-message-index="0"></div>
        </div>
        <textarea id="input"></textarea>
    `;
    const host = Object.create(DlpPolicyMixin);
    Object.assign(host, {
        elements: {
            messages: document.getElementById('messages'),
            input: document.getElementById('input'),
        },
        conversationHistory: [...PREVIOUS_HISTORY, { isUser: true, message: REJECTED_TEXT }],
        _uiString: () => '',
        loadConversation: vi.fn((history) => {
            host.conversationHistory = history.slice();
        }),
        saveConversationHistory: vi.fn(),
        _dispatchImmersiveUpdate: vi.fn(),
        _resizeChatInput: vi.fn(),
        handleSendMessage: vi.fn(),
        enterEditModeInBubble: vi.fn((wrapper) => {
            wrapper.innerHTML = '<textarea class="chat-message-edit-textarea"></textarea>';
        }),
    });
    return host;
}

const overlay = () => document.querySelector('.humdb-dlp-modal-overlay');
const buttons = () => [...document.querySelectorAll('.humdb-dlp-modal-actions button')];
const pressEscape = () => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
const unsent = (extra = {}) => ({ history: PREVIOUS_HISTORY, text: REJECTED_TEXT, ...extra });

describe('DLP challenge dialog', () => {
    let host;

    beforeEach(() => {
        host = makeHost();
    });

    afterEach(() => {
        pressEscape();
        document.body.innerHTML = '';
        vi.useRealTimers();
    });

    it('offers Cancel and Mask & send when confirmation is required', () => {
        host._handleDlpChallenge(REJECTED_TEXT, { dlpUnsent: unsent() }, CONFIRM_PAYLOAD);

        expect(buttons().map((b) => b.textContent)).toEqual(['Cancel', 'Mask & send']);
        expect([...document.querySelectorAll('.humdb-dlp-modal-body li')].map((li) => li.textContent)).toEqual([
            'Password',
        ]);
    });

    it('Mask & send resends with allow_sensitive and the original send options', () => {
        const sendOptions = { client_message_id: 'msg-1', dlpUnsent: unsent() };
        host._handleDlpChallenge(REJECTED_TEXT, sendOptions, CONFIRM_PAYLOAD);

        buttons()[1].click();

        expect(host.handleSendMessage).toHaveBeenCalledWith(REJECTED_TEXT, { ...sendOptions, allow_sensitive: true });
        expect(host.loadConversation).not.toHaveBeenCalled();
        expect(overlay()).toBeNull();
    });

    it('Cancel restores the conversation from before the send and returns the text to the input', () => {
        host._handleDlpChallenge(REJECTED_TEXT, { dlpUnsent: unsent() }, CONFIRM_PAYLOAD);

        buttons()[0].click();

        expect(host.conversationHistory).toEqual(PREVIOUS_HISTORY);
        expect(host.saveConversationHistory).toHaveBeenCalled();
        expect(host.elements.input.value).toBe(REJECTED_TEXT);
        expect(host.handleSendMessage).not.toHaveBeenCalled();
        expect(overlay()).toBeNull();
    });

    it.each([
        ['Escape', pressEscape],
        ['a backdrop click', () => overlay().click()],
    ])('%s counts as Cancel', (_name, dismiss) => {
        host._handleDlpChallenge(REJECTED_TEXT, { dlpUnsent: unsent() }, CONFIRM_PAYLOAD);

        dismiss();

        expect(host.conversationHistory).toEqual(PREVIOUS_HISTORY);
        expect(host.elements.input.value).toBe(REJECTED_TEXT);
        expect(overlay()).toBeNull();
    });

    it('only offers to edit the message when it is blocked', () => {
        host._handleDlpChallenge(REJECTED_TEXT, { dlpUnsent: unsent() }, BLOCKED_PAYLOAD);

        expect(buttons().map((b) => b.textContent)).toEqual(['Edit message']);
        buttons()[0].click();

        expect(host.conversationHistory).toEqual(PREVIOUS_HISTORY);
        expect(host.elements.input.value).toBe(REJECTED_TEXT);
        expect(host.handleSendMessage).not.toHaveBeenCalled();
    });

    it('reopens the edit box with the rejected text when an edit is cancelled', () => {
        vi.useFakeTimers();
        const wrapper = document.querySelector('[data-message-index="0"]');
        wrapper.scrollIntoView = vi.fn();
        host._handleDlpChallenge(REJECTED_TEXT, { dlpUnsent: unsent({ editIndex: 0 }) }, CONFIRM_PAYLOAD);

        buttons()[0].click();
        vi.runAllTimers();

        expect(host.enterEditModeInBubble).toHaveBeenCalledWith(wrapper, 0);
        expect(wrapper.querySelector('.chat-message-edit-textarea').value).toBe(REJECTED_TEXT);
        expect(wrapper.scrollIntoView).toHaveBeenCalledWith({ block: 'nearest' });
        expect(host.elements.input.value).toBe('');
    });

    it('leaves the input alone when a retry is cancelled', () => {
        host.elements.input.value = 'a draft typed meanwhile';
        host._handleDlpChallenge(REJECTED_TEXT, { dlpUnsent: unsent({ text: '' }) }, CONFIRM_PAYLOAD);

        buttons()[0].click();

        expect(host.conversationHistory).toEqual(PREVIOUS_HISTORY);
        expect(host.elements.input.value).toBe('a draft typed meanwhile');
    });

    it('does not overwrite a draft typed while the dialog was open', () => {
        host._handleDlpChallenge(REJECTED_TEXT, { dlpUnsent: unsent() }, CONFIRM_PAYLOAD);
        host.elements.input.value = 'a draft typed meanwhile';

        buttons()[0].click();

        expect(host.elements.input.value).toBe('a draft typed meanwhile');
    });

    it('just closes when there is nothing to restore', () => {
        host._handleDlpChallenge(REJECTED_TEXT, {}, CONFIRM_PAYLOAD);

        buttons()[0].click();

        expect(host.loadConversation).not.toHaveBeenCalled();
        expect(overlay()).toBeNull();
    });

    it('replaces an open dialog instead of stacking a second one', () => {
        host._handleDlpChallenge(REJECTED_TEXT, { dlpUnsent: unsent() }, CONFIRM_PAYLOAD);
        host._handleDlpChallenge(REJECTED_TEXT, { dlpUnsent: unsent() }, CONFIRM_PAYLOAD);

        expect(document.querySelectorAll('.humdb-dlp-modal-overlay')).toHaveLength(1);
        pressEscape();
        expect(host.loadConversation).toHaveBeenCalledTimes(1);
    });
});
