/**
 * Translation preview for entry-form text and textarea answers.
 *
 * Focal points type free text in their own language. When someone else opens
 * the form with a different display language selected, a small icon appears
 * inside the field. Activating it shows a translation in the display language.
 *
 * The field value is never written. The panel is not a form control.
 *
 * Language detection here mirrors
 * app/services/forms/field_text_language.py — keep the two in step.
 */

const PREVIEW_CONFIDENCE = 0.55;
const INPUT_REFRESH_MS = 250;

const LATIN_STOPWORDS = {
    en: new Set([
        'the', 'and', 'of', 'to', 'in', 'for', 'with', 'from', 'that', 'this',
        'was', 'were', 'are', 'is', 'been', 'have', 'has', 'had', 'not', 'but',
        'or', 'as', 'by', 'on', 'at', 'an', 'their', 'they', 'which', 'when',
        'where', 'what', 'who', 'into', 'over', 'after', 'before', 'because',
        'during', 'between', 'about', 'than', 'then', 'also', 'only', 'its',
        'be', 'will', 'would', 'can', 'could', 'should', 'our', 'your',
    ]),
    fr: new Set([
        'les', 'des', 'une', 'dans', 'pour', 'avec', 'sur', 'est', 'sont',
        'été', 'était', 'que', 'qui', 'dont', 'cette', 'ces', 'aux', 'par',
        'pas', 'plus', 'nous', 'vous', 'ils', 'elles', 'leur', 'comme', 'mais',
        'où', 'donc', 'car', 'ainsi', 'entre', 'après', 'avant', 'chez', 'sous',
        'vers', 'depuis', 'très', 'aussi', 'ont', 'elle', 'votre', 'notre',
        'merci', 'bonjour', 'la', 'le', 'de', 'un', 'et', 'du', 'au', 'en', 'à',
    ]),
    es: new Set([
        'los', 'las', 'una', 'del', 'con', 'para', 'por', 'son', 'está', 'que',
        'como', 'más', 'pero', 'porque', 'cuando', 'donde', 'también', 'entre',
        'sobre', 'desde', 'hasta', 'muy', 'este', 'esta', 'estos', 'estas',
        'hay', 'fue', 'fueron', 'han', 'tiene', 'sus', 'el', 'la', 'de', 'en',
        'un', 'y', 'se', 'su', 'al',
    ]),
    pt: new Set([
        'não', 'uma', 'para', 'com', 'por', 'como', 'mais', 'mas', 'também',
        'está', 'são', 'foi', 'foram', 'tem', 'dos', 'das', 'nos', 'nas',
        'pelo', 'pela', 'entre', 'sobre', 'desde', 'muito', 'este', 'esta',
        'isso', 'quando', 'onde', 'porque', 'na', 'no', 'em', 'os', 'as', 'do',
        'da', 'ao', 'ou', 'se',
    ]),
    de: new Set([
        'und', 'der', 'die', 'das', 'den', 'dem', 'des', 'ein', 'eine', 'nicht',
        'mit', 'von', 'für', 'auf', 'ist', 'sind', 'war', 'waren', 'auch',
        'nach', 'bei', 'aus', 'zum', 'zur', 'oder', 'aber', 'wenn', 'wie',
        'sich', 'dass', 'hat', 'haben', 'wurde', 'wurden', 'über', 'zwischen',
        'im', 'am', 'vom',
    ]),
    it: new Set([
        'che', 'non', 'una', 'per', 'con', 'sono', 'come', 'più', 'anche',
        'questo', 'questa', 'degli', 'delle', 'dalla', 'nella', 'perché',
        'quando', 'dove', 'dopo', 'prima', 'molto', 'stato', 'stata', 'hanno',
        'della', 'nel', 'sul', 'sullo', 'gli', 'uno', 'del', 'dei',
        'il', 'lo', 'la', 'di', 'un', 'e', 'in', 'da', 'su',
    ]),
};

const DISTINCTIVE = {
    es: new Set(['ñ', '¿', '¡']),
    pt: new Set(['ã', 'õ']),
    fr: new Set(['œ', 'æ']),
    de: new Set(['ä', 'ö', 'ü', 'ß']),
};

const URDU_CHARS = new Set(['ٹ', 'ڈ', 'ڑ', 'ں']);
const PERSIAN_CHARS = new Set(['پ', 'چ', 'ژ', 'گ']);
const UKRAINIAN_CHARS = new Set(['і', 'ї', 'є', 'ґ']);

const WORD_RE = /[A-Za-zÀ-ÖØ-öø-ÿ]+/g;

const chrome = new WeakMap();
const inputTimers = new WeakMap();
let installed = false;
let scanTimer = 0;
let panelSeq = 0;
let openField = null;

function stripUrlsAndEmails(text) {
    return String(text || '').split(/\s+/).filter((token) => {
        const lowered = token.toLowerCase();
        if (lowered.startsWith('http://') || lowered.startsWith('https://') || lowered.startsWith('www.')) {
            return false;
        }
        const at = token.indexOf('@');
        if (at > 0 && token.indexOf('@', at + 1) === -1) {
            const domain = token.slice(at + 1);
            const dot = domain.lastIndexOf('.');
            if (dot > 0 && dot < domain.length - 1) return false;
        }
        return true;
    }).join(' ');
}

export function normalizeLanguageCode(lang, fallback = 'en') {
    const base = String(lang || '').trim().toLowerCase().replace(/-/g, '_').split('_')[0];
    return /^[a-z]{2,3}$/.test(base) ? base : fallback;
}

export function displayLanguage() {
    const fromBody = document.body && document.body.dataset ? document.body.dataset.language : '';
    const fromHtml = document.documentElement ? document.documentElement.lang : '';
    return normalizeLanguageCode(fromBody || fromHtml || 'en');
}

function countScript(text) {
    const counts = {
        ur: 0, fa: 0, ar: 0, hi: 0, bn: 0, th: 0, ko: 0, ja: 0, zh: 0,
        uk: 0, ru: 0, el: 0, he: 0, latin: 0,
    };
    for (const ch of text) {
        if (!/\p{L}/u.test(ch)) continue;
        const o = ch.codePointAt(0);
        if (UKRAINIAN_CHARS.has(ch)) {
            counts.uk += 1;
            counts.ru += 1;
        } else if (URDU_CHARS.has(ch)) {
            counts.ur += 1;
            counts.ar += 1;
        } else if (PERSIAN_CHARS.has(ch)) {
            counts.fa += 1;
            counts.ar += 1;
        } else if (
            (o >= 0x0600 && o <= 0x06FF)
            || (o >= 0x0750 && o <= 0x077F)
            || (o >= 0x08A0 && o <= 0x08FF)
            || (o >= 0xFB50 && o <= 0xFDFF)
            || (o >= 0xFE70 && o <= 0xFEFF)
        ) {
            counts.ar += 1;
        } else if (o >= 0x0900 && o <= 0x097F) counts.hi += 1;
        else if (o >= 0x0980 && o <= 0x09FF) counts.bn += 1;
        else if (o >= 0x0E00 && o <= 0x0E7F) counts.th += 1;
        else if ((o >= 0xAC00 && o <= 0xD7AF) || (o >= 0x1100 && o <= 0x11FF)) counts.ko += 1;
        else if (o >= 0x3040 && o <= 0x30FF) counts.ja += 1;
        else if (o >= 0x4E00 && o <= 0x9FFF) counts.zh += 1;
        else if (o >= 0x0400 && o <= 0x04FF) counts.ru += 1;
        else if (o >= 0x0370 && o <= 0x03FF) counts.el += 1;
        else if (o >= 0x0590 && o <= 0x05FF) counts.he += 1;
        else if (/[A-Za-zÀ-ÿ]/.test(ch)) counts.latin += 1;
    }
    if (counts.ja) counts.zh = 0;
    if (counts.uk) counts.ru = 0;
    return counts;
}

function acceptScript(counts, lang, count) {
    if (count < 2) return null;
    if (counts.latin && count < counts.latin && count < 4) return null;
    return lang;
}

function scriptLanguage(text) {
    const counts = countScript(text);
    if (counts.ur >= 2) return acceptScript(counts, 'ur', counts.ar);
    if (counts.fa >= 2) return acceptScript(counts, 'fa', counts.ar);
    if (counts.ja >= 2) return acceptScript(counts, 'ja', counts.ja + counts.zh);
    if (counts.uk >= 2) return acceptScript(counts, 'uk', counts.ru);

    const generic = [
        ['ar', counts.ar],
        ['hi', counts.hi],
        ['bn', counts.bn],
        ['th', counts.th],
        ['ko', counts.ko],
        ['zh', counts.zh],
        ['ru', counts.ru],
        ['el', counts.el],
        ['he', counts.he],
    ];
    let best = null;
    let bestCount = 0;
    for (const [lang, count] of generic) {
        if (count > bestCount) {
            best = lang;
            bestCount = count;
        }
    }
    if (!best) return null;
    return acceptScript(counts, best, bestCount);
}

export function detectFieldTextLanguage(text) {
    const raw = String(text || '').trim();
    if (raw.length < 2) return { language: null, confidence: 0 };

    const script = scriptLanguage(raw);
    if (script) return { language: script, confidence: 0.92 };

    const cleaned = stripUrlsAndEmails(raw);
    const words = (cleaned.match(WORD_RE) || []).map((word) => word.toLowerCase());
    if (words.length < 3) return { language: null, confidence: 0 };

    const hits = {};
    const scores = {};
    for (const lang of Object.keys(LATIN_STOPWORDS)) {
        hits[lang] = 0;
        scores[lang] = 0;
    }
    for (const word of words) {
        for (const [lang, vocab] of Object.entries(LATIN_STOPWORDS)) {
            if (vocab.has(word)) hits[lang] += 1;
        }
    }
    const lower = cleaned.toLowerCase();
    const distinctiveHits = {};
    for (const lang of Object.keys(LATIN_STOPWORDS)) {
        scores[lang] = hits[lang] / words.length;
    }
    for (const [lang, chars] of Object.entries(DISTINCTIVE)) {
        let n = 0;
        for (const ch of lower) if (chars.has(ch)) n += 1;
        distinctiveHits[lang] = n;
        scores[lang] = (scores[lang] || 0) + Math.min(0.24, n * 0.08);
    }

    let best = null;
    let bestScore = -1;
    for (const [lang, score] of Object.entries(scores)) {
        if (score > bestScore) {
            best = lang;
            bestScore = score;
        }
    }
    const ordered = Object.values(scores).sort((a, b) => b - a);
    const second = ordered.length > 1 ? ordered[1] : 0;
    if ((hits[best] || 0) < 2 && !(distinctiveHits[best])) return { language: null, confidence: 0 };
    if (bestScore < 0.18) return { language: null, confidence: 0 };
    if ((bestScore - second) < 0.08 && (hits[best] || 0) < 4) return { language: null, confidence: 0 };
    return { language: best, confidence: Math.min(0.9, 0.45 + bestScore) };
}

export function shouldOfferTranslationPreview(text, displayLang) {
    const display = normalizeLanguageCode(displayLang);
    const detected = detectFieldTextLanguage(text);
    const offer = Boolean(
        detected.language
        && detected.language !== display
        && detected.confidence >= PREVIEW_CONFIDENCE
    );
    return { offer, ...detected, display };
}

export function isFreeTextField(el) {
    if (!el || (el.tagName !== 'TEXTAREA' && el.tagName !== 'INPUT')) return false;
    if (el.tagName === 'INPUT' && el.type !== 'text') return false;
    if (el.type === 'hidden' || el.closest('template')) return false;
    if (el.classList.contains('validation-answer-input')) return false;
    if (el.id && el.id.indexOf('discussion-comment') === 0) return false;
    if (el.closest(
        '.matrix-table, .discussion-panel, #validation-questions-panel, .matrix-add-row-interface, .field-translation-preview-panel'
    )) return false;
    if (el.classList.contains('other-text-input')) return true;

    const block = el.closest('.form-item-block');
    if (!block) return false;
    const questionType = (block.getAttribute('data-question-type') || '').toLowerCase();
    if (questionType === 'text' && el.tagName === 'INPUT') return true;
    if (questionType === 'textarea' && el.tagName === 'TEXTAREA') return true;
    const itemType = (block.getAttribute('data-item-type') || '').toLowerCase();
    if (itemType === 'indicator' || itemType === 'dynamic') {
        return el.tagName === 'TEXTAREA' || el.tagName === 'INPUT';
    }
    return false;
}

function i18n(name, fallback) {
    const root = document.getElementById('entry-form-root');
    const value = root ? root.getAttribute(`data-i18n-${name}`) : '';
    return value || fallback;
}

function formatLanguage(template, language) {
    return String(template || '').replace('%(language)s', language || '');
}

function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.getAttribute('content')) return meta.getAttribute('content');
    const input = document.querySelector('input[name="csrf_token"]');
    return input ? input.value : '';
}

function previewContext() {
    const root = document.getElementById('entry-form-root');
    const submissionId = root ? root.getAttribute('data-public-submission-id') : '';
    if (submissionId) return { public_submission_id: Number(submissionId) };
    const aes = document.querySelector('input[name="assignment_entity_status_id"]');
    if (aes && aes.value) return { assignment_entity_status_id: Number(aes.value) };
    return {};
}

function encodeText(text) {
    return btoa(unescape(encodeURIComponent(text)));
}

function buildIcon() {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('aria-hidden', 'true');
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('stroke', 'currentColor');
    path.setAttribute('stroke-width', '1.5');
    path.setAttribute('stroke-linecap', 'round');
    path.setAttribute('stroke-linejoin', 'round');
    path.setAttribute(
        'd',
        'M10.5 21l5.25-11.25L21 21m-9-3h7.5M3 5.621a48.474 48.474 0 016-.371m0 0c1.12 0 2.233.038 3.334.114M9 5.25V3m3.334 2.364C11.176 10.658 7.69 15.08 3 17.502m9.334-12.138c.896.061 1.785.147 2.666.257m-4.589 8.495a18.023 18.023 0 01-3.827-5.802'
    );
    svg.appendChild(path);
    return svg;
}

function buildButton(field) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'field-translation-preview-btn';
    button.classList.add(field.tagName === 'TEXTAREA' ? 'is-textarea' : 'is-input');
    button.hidden = true;
    button.setAttribute('aria-expanded', 'false');
    button.setAttribute('aria-label', i18n('show-translation', 'Show translation preview'));
    button.appendChild(buildIcon());
    return button;
}

function buildPanel() {
    panelSeq += 1;
    const panel = document.createElement('div');
    panel.className = 'field-translation-preview-panel';
    panel.id = `field-translation-preview-${panelSeq}`;
    panel.hidden = true;
    panel.setAttribute('role', 'note');

    const title = document.createElement('p');
    title.className = 'field-translation-preview-title';
    const body = document.createElement('p');
    body.className = 'field-translation-preview-body';
    const note = document.createElement('p');
    note.className = 'field-translation-preview-note';
    note.textContent = i18n('preview-note', 'Preview only. This does not change the saved text.');
    panel.append(title, body, note);
    return panel;
}

function ensureChrome(field) {
    const existing = chrome.get(field);
    if (existing) return existing;

    let slot = field.parentElement && field.parentElement.classList.contains('field-translation-slot')
        ? field.parentElement
        : null;
    if (!slot) {
        slot = document.createElement('span');
        slot.className = 'field-translation-slot';
        field.parentNode.insertBefore(slot, field);
        slot.appendChild(field);
    }
    slot.querySelectorAll(':scope > .field-translation-preview-btn, :scope > .field-translation-preview-panel')
        .forEach((node) => node.remove());

    const button = buildButton(field);
    slot.appendChild(button);
    field.classList.add('field-translation-host');
    const state = { slot, button, panel: null, requestId: 0, cache: new Map(), text: field.value };
    chrome.set(field, state);
    return state;
}

function setIconVisible(field, state, visible) {
    state.button.hidden = !visible;
    field.classList.toggle('has-translation-icon', visible);
    if (!visible) closePanel(field, state);
}

function closePanel(field, state) {
    if (!state || !state.panel) return;
    state.panel.hidden = true;
    state.button.setAttribute('aria-expanded', 'false');
    state.button.setAttribute('aria-label', i18n('show-translation', 'Show translation preview'));
    if (openField === field) openField = null;
}

function closeOpenPanel() {
    if (!openField) return;
    const state = chrome.get(openField);
    closePanel(openField, state);
}

function panelParts(panel) {
    return {
        title: panel.querySelector('.field-translation-preview-title'),
        body: panel.querySelector('.field-translation-preview-body'),
        note: panel.querySelector('.field-translation-preview-note'),
    };
}

function showPanel(field, state, { title, body, truncated }) {
    if (!state.panel) {
        state.panel = buildPanel();
        state.button.setAttribute('aria-controls', state.panel.id);
        state.slot.appendChild(state.panel);
    }
    const parts = panelParts(state.panel);
    parts.title.textContent = title || '';
    parts.body.textContent = body || '';
    const note = i18n('preview-note', 'Preview only. This does not change the saved text.');
    const extra = truncated ? ` ${i18n('truncated', 'Preview shows the beginning of this text.')}` : '';
    parts.note.textContent = `${note}${extra}`;
    state.panel.hidden = false;
    state.button.hidden = false;
    state.button.setAttribute('aria-expanded', 'true');
    state.button.setAttribute('aria-label', i18n('hide-translation', 'Hide translation preview'));
    field.classList.add('has-translation-icon');
    openField = field;
}

export function refreshField(field) {
    if (!isFreeTextField(field)) return;
    const state = ensureChrome(field);
    const text = field.value || '';
    if (text !== state.text) {
        closePanel(field, state);
        state.text = text;
    }
    const decision = shouldOfferTranslationPreview(text, displayLanguage());
    setIconVisible(field, state, decision.offer);
}

export function refreshFieldTranslationPreviews(root) {
    const scope = root || document.getElementById('entry-form-root') || document;
    scope.querySelectorAll('textarea, input[type="text"]').forEach((el) => {
        if (isFreeTextField(el)) refreshField(el);
    });
}

async function requestPreview(text, fetchImpl) {
    const root = document.getElementById('entry-form-root');
    const url = root ? root.getAttribute('data-field-translation-url') : '';
    if (!url) throw new Error('missing translation url');
    const fetcher = fetchImpl || window.fetch.bind(window);
    const response = await fetcher(url, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken(),
            'X-Requested-With': 'XMLHttpRequest',
        },
        body: JSON.stringify({
            text_b64: encodeText(text),
            ...previewContext(),
        }),
    });
    if (!response.ok) throw new Error(`preview failed (${response.status})`);
    return response.json();
}

export async function openFieldTranslationPreview(field, fetchImpl) {
    if (!isFreeTextField(field)) return null;
    const state = ensureChrome(field);
    const text = field.value || '';
    if (openField === field && state.panel && !state.panel.hidden) {
        closePanel(field, state);
        return null;
    }
    closeOpenPanel();
    const cached = state.cache.get(text);
    if (cached) {
        showPanel(field, state, cached);
        return cached;
    }
    showPanel(field, state, {
        title: i18n('translating', 'Translating…'),
        body: '',
    });
    state.requestId += 1;
    const requestId = state.requestId;
    try {
        const data = await requestPreview(text, fetchImpl);
        if (state.requestId !== requestId || (field.value || '') !== text) return null;
        if (!data || data.show_preview === false || !data.translation) {
            if (data && data.show_preview === false) setIconVisible(field, state, false);
            else {
                showPanel(field, state, {
                    title: i18n('unavailable', 'Translation is unavailable right now.'),
                    body: '',
                });
            }
            return data;
        }
        const view = {
            title: formatLanguage(
                i18n('preview-title', 'Preview in %(language)s'),
                data.target_language_name || ''
            ),
            body: data.translation,
            truncated: Boolean(data.truncated),
        };
        state.cache.set(text, view);
        showPanel(field, state, view);
        return data;
    } catch (err) {
        if (state.requestId !== requestId) return null;
        showPanel(field, state, {
            title: i18n('unavailable', 'Translation is unavailable right now.'),
            body: '',
        });
        return null;
    }
}

function fieldFromButton(button) {
    const slot = button.closest('.field-translation-slot');
    if (!slot) return null;
    return slot.querySelector('textarea, input[type="text"]');
}

function onClick(event) {
    const button = event.target.closest && event.target.closest('.field-translation-preview-btn');
    if (button) {
        event.preventDefault();
        event.stopPropagation();
        const field = fieldFromButton(button);
        if (field) openFieldTranslationPreview(field);
        return;
    }
    if (event.target.closest && event.target.closest('.field-translation-preview-panel')) return;
    closeOpenPanel();
}

function onKeyDown(event) {
    if (event.key === 'Escape') closeOpenPanel();
}

function onInput(event) {
    const field = event.target;
    if (!isFreeTextField(field)) return;
    const pending = inputTimers.get(field);
    if (pending) window.clearTimeout(pending);
    inputTimers.set(field, window.setTimeout(() => refreshField(field), INPUT_REFRESH_MS));
}

function scheduleScan() {
    window.clearTimeout(scanTimer);
    scanTimer = window.setTimeout(() => refreshFieldTranslationPreviews(), 50);
}

export function installFieldTranslationPreview() {
    if (installed) return;
    installed = true;
    document.addEventListener('click', onClick);
    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('input', onInput);
    const root = document.getElementById('entry-form-root') || document.body;
    if (typeof MutationObserver === 'function' && root) {
        const observer = new MutationObserver(scheduleScan);
        observer.observe(root, { childList: true, subtree: true });
    }
}

function boot() {
    const root = document.getElementById('entry-form-root');
    if (!root || !root.getAttribute('data-field-translation-url')) return;
    installFieldTranslationPreview();
    refreshFieldTranslationPreviews(root);
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
} else {
    boot();
}
