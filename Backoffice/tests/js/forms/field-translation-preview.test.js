/**
 * Translation preview icon for entry-form text and textarea fields.
 * The preview is shown beside the value. The value itself is left alone.
 */
import { describe, it, expect, beforeAll, afterEach, vi } from 'vitest';
import {
    installFieldTranslationPreview,
    refreshFieldTranslationPreviews,
    openFieldTranslationPreview,
    isFreeTextField,
    shouldOfferTranslationPreview,
} from '../../../app/static/js/forms/modules/field-translation-preview.js';

const ARABIC = 'تم تأجيل التوزيع بسبب الفيضانات في المنطقة';
const ENGLISH = 'The distribution was delayed because of flooding in the area.';

function mount(html) {
    const parsed = new DOMParser().parseFromString(
        `<div id="entry-form-root" data-field-translation-url="/forms/api/field-text-translation-preview" data-i18n-show-translation="Show translation preview" data-i18n-hide-translation="Hide translation preview" data-i18n-translating="Translating…" data-i18n-preview-note="Preview only. This does not change the saved text." data-i18n-unavailable="Translation is unavailable right now." data-i18n-preview-title="Preview in %(language)s" data-i18n-truncated="Preview shows the beginning of this text.">${html}</div>`,
        'text/html'
    );
    document.body.dataset.language = 'en';
    document.body.appendChild(parsed.getElementById('entry-form-root'));
    return document.getElementById('entry-form-root');
}

describe('field translation preview', () => {
    beforeAll(() => {
        installFieldTranslationPreview();
    });

    afterEach(() => {
        document.body.replaceChildren();
        delete document.body.dataset.language;
    });

    it('offers a preview only when the text language differs from the display language', () => {
        expect(shouldOfferTranslationPreview(ARABIC, 'en').offer).toBe(true);
        expect(shouldOfferTranslationPreview(ARABIC, 'ar').offer).toBe(false);
        expect(shouldOfferTranslationPreview(ENGLISH, 'en').offer).toBe(false);
        expect(shouldOfferTranslationPreview(ENGLISH, 'fr').offer).toBe(true);
        expect(shouldOfferTranslationPreview('Amman clinic', 'fr').offer).toBe(false);
    });

    it('badges text and textarea answers and ignores other controls', () => {
        const root = mount(`
            <form id="focalDataEntryForm">
                <div class="form-item-block" data-item-type="question" data-question-type="text">
                    <input type="text" name="field_value[1]" value="${ARABIC}">
                </div>
                <div class="form-item-block" data-item-type="question" data-question-type="textarea">
                    <textarea name="field_value[2]">${ENGLISH}</textarea>
                </div>
                <div class="form-item-block" data-item-type="indicator">
                    <textarea name="field_value[3]">${ARABIC}</textarea>
                </div>
                <div class="form-item-block" data-item-type="indicator">
                    <input type="number" name="field_value[4]" value="12">
                </div>
                <div class="form-item-block" data-item-type="matrix">
                    <input type="text" id="matrix-row-search-9" value="search">
                </div>
                <textarea id="discussion-comment-input">comment</textarea>
            </form>
        `);
        refreshFieldTranslationPreviews(root);

        const question = root.querySelector('[name="field_value[1]"]');
        const english = root.querySelector('[name="field_value[2]"]');
        const indicator = root.querySelector('[name="field_value[3]"]');
        const number = root.querySelector('[name="field_value[4]"]');
        const search = root.querySelector('#matrix-row-search-9');
        const comment = root.querySelector('#discussion-comment-input');

        expect(isFreeTextField(question)).toBe(true);
        expect(isFreeTextField(number)).toBe(false);
        expect(isFreeTextField(search)).toBe(false);
        expect(isFreeTextField(comment)).toBe(false);

        expect(question.parentElement.querySelector('.field-translation-preview-btn').hidden).toBe(false);
        expect(question.parentElement.querySelector('.field-translation-preview-btn').type).toBe('button');
        expect(english.parentElement.querySelector('.field-translation-preview-btn').hidden).toBe(true);
        expect(indicator.parentElement.querySelector('.field-translation-preview-btn').hidden).toBe(false);
        expect(number.parentElement.classList.contains('field-translation-slot')).toBe(false);
        expect(question.value).toBe(ARABIC);
    });

    it('shows the translation in a preview and does not replace the field value', async () => {
        const root = mount(`
            <form id="focalDataEntryForm">
                <input type="hidden" name="assignment_entity_status_id" value="15">
                <div class="form-item-block" data-item-type="question" data-question-type="textarea">
                    <textarea name="field_value[2]">${ARABIC}</textarea>
                </div>
            </form>
        `);
        refreshFieldTranslationPreviews(root);
        const field = root.querySelector('textarea');
        const original = field.value;

        const fetchImpl = vi.fn(async () => ({
            ok: true,
            json: async () => ({
                success: true,
                preview_only: true,
                show_preview: true,
                translation: 'The distribution was delayed',
                target_language_name: 'English',
            }),
        }));

        await openFieldTranslationPreview(field, fetchImpl);

        expect(field.value).toBe(original);
        const button = field.parentElement.querySelector('.field-translation-preview-btn');
        expect(button.getAttribute('aria-expanded')).toBe('true');
        expect(button.getAttribute('aria-label')).toBe('Hide translation preview');
        refreshFieldTranslationPreviews(root);
        expect(field.value).toBe(original);
        expect(button.getAttribute('aria-label')).toBe('Hide translation preview');
        expect(root.querySelector('.field-translation-preview-body').textContent)
            .toBe('The distribution was delayed');
        expect(root.querySelector('.field-translation-preview-title').textContent)
            .toBe('Preview in English');
        expect(root.querySelector('.field-translation-preview-note').textContent)
            .toContain('does not change the saved text');
        expect(root.querySelector('.field-translation-preview-panel input, .field-translation-preview-panel textarea'))
            .toBeNull();

        const request = JSON.parse(fetchImpl.mock.calls[0][1].body);
        expect(request.assignment_entity_status_id).toBe(15);
        expect(request.text).toBeUndefined();
        expect(request.text_b64).toBeTruthy();
        expect(field.value).toBe(original);
    });
});
