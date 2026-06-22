/**
 * Form Builder AI Assistant panel.
 *
 * Lightweight chat client for the form-builder AI tools. Streams answers from
 * /api/ai/v2/chat/stream (SSE) with page_context.formBuilder set, so the agent
 * exposes the create/edit form template tools. All AI changes go to a draft
 * version; after a successful edit the panel refreshes the builder in-place via
 * AJAX (or offers to open a newly created template from the list page).
 *
 * Markup + config live in components/form_builder_ai_panel.html.
 */

'use strict';

const CONFIG_EL_ID = 'fb-ai-assistant-config';
const MAX_HISTORY_SENT = 5;
const MAX_HISTORY_STORED = 40;
const FB_AI_STORAGE_PREFIX = 'humdb_fb_ai_';
const FB_AI_NEW_TEMPLATE_KEY = `${FB_AI_STORAGE_PREFIX}new`;
const FB_AI_MIGRATE_MARKER_KEY = 'humdb_fb_ai_migrate_to';

function fbAiStorageKey(templateId) {
    return `${FB_AI_STORAGE_PREFIX}${templateId || 'new'}`;
}

function readFbAiStoredState(storageKey) {
    try {
        return JSON.parse(sessionStorage.getItem(storageKey) || 'null');
    } catch (e) {
        return null;
    }
}

function writeFbAiStoredState(storageKey, state) {
    try {
        sessionStorage.setItem(storageKey, JSON.stringify(state));
    } catch (e) { /* storage unavailable */ }
}

function readConfig() {
    const el = document.getElementById(CONFIG_EL_ID);
    if (!el) return null;
    try {
        return JSON.parse(el.textContent);
    } catch (e) {
        console.error('[fb-ai] invalid config JSON', e);
        return null;
    }
}

function csrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
}

function escapeHtml(text) {
    return String(text ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

const IMAGE_MIME_RE = /^image\/(png|jpe?g|webp|gif)$/i;
const IMAGE_EXT_RE = /\.(png|jpe?g|webp|gif)$/i;

function isImageFile(file) {
    if (!file) return false;
    const type = String(file.type || '').toLowerCase();
    if (IMAGE_MIME_RE.test(type)) return true;
    return IMAGE_EXT_RE.test(String(file.name || '').toLowerCase());
}

function normalizeImageFilename(file) {
    if (file.name && String(file.name).trim()) return file;
    const ext = (file.type || 'image/png').split('/')[1] || 'png';
    return new File([file], `pasted-image.${ext}`, { type: file.type || 'image/png' });
}

class FormBuilderAIAssistant {
    constructor(config) {
        this.config = config;
        this.templateId = config.templateId || null;
        this.versionId = config.versionId || null;
        this.labels = config.labels || {};
        this._isCreateMode = !this.templateId;
        this.storageKey = fbAiStorageKey(this.templateId);

        this.conversationId = null;
        this.messages = []; // {message, isUser, isError?}
        this.attachment = null; // {kind: 'document'|'image', filename, text, sections?, previewUrl?}
        this.busy = false;
        this.abortController = null;

        this.els = {
            panel: document.getElementById('fb-ai-panel'),
            messages: document.getElementById('fb-ai-messages'),
            status: document.getElementById('fb-ai-status'),
            statusText: document.getElementById('fb-ai-status-text'),
            actionBar: document.getElementById('fb-ai-action-bar'),
            actionBtn: document.getElementById('fb-ai-action-btn'),
            input: document.getElementById('fb-ai-input'),
            send: document.getElementById('fb-ai-send'),
            close: document.getElementById('fb-ai-close'),
            clear: document.getElementById('fb-ai-clear'),
            attach: document.getElementById('fb-ai-attach'),
            file: document.getElementById('fb-ai-file'),
            attachment: document.getElementById('fb-ai-attachment'),
            attachmentPreview: document.getElementById('fb-ai-attachment-preview'),
            attachmentIcon: document.getElementById('fb-ai-attachment-icon'),
            attachmentName: document.getElementById('fb-ai-attachment-name'),
            attachmentRemove: document.getElementById('fb-ai-attachment-remove'),
            trigger: document.getElementById('ai-assistant-btn'),
            lightbox: document.getElementById('fb-ai-image-lightbox'),
            lightboxImg: document.getElementById('fb-ai-lightbox-img'),
            lightboxClose: document.getElementById('fb-ai-lightbox-close'),
        };
        this._onLightboxKeydown = (e) => {
            if (e.key === 'Escape') this.closeImageLightbox();
        };
    }

    init() {
        if (!this.els.panel) return;
        this.els.trigger?.addEventListener('click', () => this.toggle());
        this.els.close?.addEventListener('click', () => this.hide());
        this.els.clear?.addEventListener('click', () => this.reset());
        this.els.send?.addEventListener('click', () => this.handleSend());
        this.els.input?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.handleSend();
            }
        });
        this.els.input?.addEventListener('paste', (e) => this.handlePaste(e));
        this.els.panel?.addEventListener('paste', (e) => this.handlePaste(e));
        this.els.attach?.addEventListener('click', () => this.els.file?.click());
        this.els.file?.addEventListener('change', () => {
            const f = this.els.file.files && this.els.file.files[0];
            if (f) this.uploadAttachment(f);
            this.els.file.value = '';
        });
        this.els.attachmentRemove?.addEventListener('click', () => this.clearAttachment());

        // Drag & drop questionnaire files onto the panel
        this.els.panel.addEventListener('dragover', (e) => {
            e.preventDefault();
            this.els.panel.classList.add('fb-ai-drag-over');
        });
        this.els.panel.addEventListener('dragleave', () => {
            this.els.panel.classList.remove('fb-ai-drag-over');
        });
        this.els.panel.addEventListener('drop', (e) => {
            e.preventDefault();
            this.els.panel.classList.remove('fb-ai-drag-over');
            const f = e.dataTransfer?.files && e.dataTransfer.files[0];
            if (f) this.uploadAttachment(f);
        });

        this.updateSendEnabled();
        this.els.input?.addEventListener('input', () => this.updateSendEnabled());

        this.initImageLightbox();
        this.els.messages?.addEventListener('click', (e) => this.handleTemplateLinkClick(e));
        this.restoreState();
    }

    handleTemplateLinkClick(e) {
        if (this.templateId) return;
        const anchor = e.target.closest('a[href]');
        if (!anchor) return;
        const link = this.parseTemplateEditLink(anchor.getAttribute('href') || '');
        if (!link) return;
        this.migrateStateToTemplate(link.templateId);
        this.markPanelReopenOnLoad();
    }

    initImageLightbox() {
        if (!this.els.lightbox) return;
        this.els.lightboxClose?.addEventListener('click', (e) => {
            e.stopPropagation();
            this.closeImageLightbox();
        });
        this.els.lightbox.addEventListener('click', () => this.closeImageLightbox());
        this.els.lightboxImg?.addEventListener('click', (e) => e.stopPropagation());
    }

    openImageLightbox(src, alt = 'Image preview') {
        if (!this.els.lightbox || !this.els.lightboxImg || !src) return;
        this.els.lightboxImg.src = src;
        this.els.lightboxImg.alt = alt || 'Image preview';
        this.els.lightbox.hidden = false;
        document.body.classList.add('fb-ai-lightbox-open');
        document.addEventListener('keydown', this._onLightboxKeydown);
        this.els.lightboxClose?.focus();
    }

    closeImageLightbox() {
        if (!this.els.lightbox) return;
        this.els.lightbox.hidden = true;
        if (this.els.lightboxImg) {
            this.els.lightboxImg.removeAttribute('src');
            this.els.lightboxImg.alt = '';
        }
        document.body.classList.remove('fb-ai-lightbox-open');
        document.removeEventListener('keydown', this._onLightboxKeydown);
    }

    wireExpandableImage(img, src, alt = 'Pasted image') {
        if (!img || !src) return;
        img.src = src;
        img.alt = alt;
        img.classList.add('fb-ai-expandable-image');
        if (img.dataset.fbExpandableWired === '1') return;
        img.dataset.fbExpandableWired = '1';
        img.tabIndex = 0;
        img.setAttribute('role', 'button');
        img.setAttribute('aria-label', this.labels.viewImage || 'View full size image');
        const open = () => this.openImageLightbox(src, alt);
        img.addEventListener('click', open);
        img.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                open();
            }
        });
    }

    // ------------------------------------------------------------------
    // Panel visibility + persisted state
    // ------------------------------------------------------------------

    toggle() {
        if (this.els.panel.hidden) this.show();
        else this.hide();
    }

    _syncGlobalChrome(isOpen) {
        try {
            document.body.classList.toggle('fb-ai-panel-open', isOpen);
        } catch (e) { /* ignore */ }
        try {
            window.dispatchEvent(new CustomEvent('fb-ai-panel-visibility', {
                detail: { open: isOpen },
            }));
        } catch (e) { /* ignore */ }
    }

    show() {
        this.els.panel.hidden = false;
        this._syncGlobalChrome(true);
        this.els.input?.focus();
    }

    hide() {
        this.els.panel.hidden = true;
        this._syncGlobalChrome(false);
    }

    reset() {
        if (this.busy) this.abortController?.abort();
        this.conversationId = null;
        this.messages = [];
        this.clearAttachment();
        this.hideAction();
        try {
            sessionStorage.removeItem(this.storageKey);
            if (this._isCreateMode) {
                sessionStorage.removeItem(FB_AI_NEW_TEMPLATE_KEY);
                sessionStorage.removeItem(FB_AI_MIGRATE_MARKER_KEY);
                this.storageKey = FB_AI_NEW_TEMPLATE_KEY;
                this.templateId = null;
            }
        } catch (e) { /* storage unavailable */ }
        // Remove rendered messages but keep the welcome block (first child)
        const children = Array.from(this.els.messages.children);
        children.forEach((c, i) => { if (i > 0) c.remove(); });
        const welcome = this.els.messages.querySelector('.fb-ai-welcome');
        if (welcome) welcome.hidden = false;
    }

    saveState() {
        writeFbAiStoredState(this.storageKey, {
            conversationId: this.conversationId,
            messages: this.messages.slice(-MAX_HISTORY_STORED),
        });
    }

    markPanelReopenOnLoad() {
        try {
            sessionStorage.setItem(`${this.storageKey}_reopen`, '1');
        } catch (e) { /* storage unavailable */ }
    }

    migrateStateToTemplate(templateId) {
        const numericId = parseInt(templateId, 10);
        if (!numericId) return;

        const targetKey = fbAiStorageKey(numericId);
        if (targetKey === this.storageKey && this.messages.length) {
            this.saveState();
        } else {
            const state = this.messages.length
                ? {
                    conversationId: this.conversationId,
                    messages: this.messages.slice(-MAX_HISTORY_STORED),
                }
                : readFbAiStoredState(this.storageKey)
                    || readFbAiStoredState(FB_AI_NEW_TEMPLATE_KEY);
            if (state && Array.isArray(state.messages) && state.messages.length) {
                writeFbAiStoredState(targetKey, state);
            }
        }

        try {
            sessionStorage.setItem(FB_AI_MIGRATE_MARKER_KEY, String(numericId));
            if (this._isCreateMode) {
                sessionStorage.removeItem(FB_AI_NEW_TEMPLATE_KEY);
            }
            if (this.storageKey !== targetKey) {
                sessionStorage.removeItem(this.storageKey);
            }
        } catch (e) { /* storage unavailable */ }

        this.storageKey = targetKey;
        this.templateId = numericId;
    }

    inheritCreateModeStateIfNeeded() {
        if (!this.templateId) return null;

        let state = readFbAiStoredState(this.storageKey);
        if (state && Array.isArray(state.messages) && state.messages.length) {
            return state;
        }

        let migrateTo = null;
        try {
            migrateTo = sessionStorage.getItem(FB_AI_MIGRATE_MARKER_KEY);
        } catch (e) { /* ignore */ }
        if (!migrateTo || parseInt(migrateTo, 10) !== this.templateId) {
            return null;
        }

        const createState = readFbAiStoredState(FB_AI_NEW_TEMPLATE_KEY);
        if (!createState || !Array.isArray(createState.messages) || !createState.messages.length) {
            return null;
        }

        writeFbAiStoredState(this.storageKey, createState);
        try {
            sessionStorage.removeItem(FB_AI_NEW_TEMPLATE_KEY);
            sessionStorage.removeItem(FB_AI_MIGRATE_MARKER_KEY);
        } catch (e) { /* ignore */ }
        return createState;
    }

    restoreState() {
        let state = this.inheritCreateModeStateIfNeeded();
        if (!state) {
            state = readFbAiStoredState(this.storageKey);
        }
        if (!state || !Array.isArray(state.messages) || !state.messages.length) return;
        this.conversationId = state.conversationId || null;
        this.messages = state.messages;
        this.messages.forEach((m) => this.renderMessage(m.message, m.isUser, !!m.isError));
        // The panel stays closed on restore; reopen if a reload was pending.
        let pendingReload = null;
        try {
            pendingReload = sessionStorage.getItem(`${this.storageKey}_reopen`);
            sessionStorage.removeItem(`${this.storageKey}_reopen`);
        } catch (e) { /* ignore */ }
        if (pendingReload) this.show();
    }

    // ------------------------------------------------------------------
    // Attachments (questionnaire import + pasted images)
    // ------------------------------------------------------------------

    handlePaste(e) {
        const items = e.clipboardData?.items;
        if (!items || this.busy) return;
        for (const item of items) {
            if (item.type && item.type.startsWith('image/')) {
                e.preventDefault();
                const file = normalizeImageFilename(item.getAsFile());
                if (file) this.attachImageFile(file);
                return;
            }
        }
    }

    async uploadAttachment(file) {
        if (this.busy || !file) return;
        if (isImageFile(file)) {
            this.attachImageFile(normalizeImageFilename(file));
        } else {
            await this.uploadDocumentAttachment(file);
        }
    }

    attachImageFile(file) {
        const normalized = normalizeImageFilename(file);
        this.setAttachment({
            kind: 'image',
            filename: normalized.name,
            file: normalized,
            previewUrl: URL.createObjectURL(normalized),
            text: null,
            sections: [],
        });
    }

    async uploadDocumentAttachment(file) {
        this.setStatus(this.labels.extracting || 'Extracting…', true);
        try {
            const form = new FormData();
            form.append('file', file);
            const resp = await ((window.getFetch && window.getFetch()) || fetch)(this.config.extractUrl, {
                method: 'POST',
                credentials: 'same-origin',
                body: form,
            });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok || !data || data.success === false || !data.text) {
                throw new Error(data?.error || data?.message || 'extract failed');
            }
            this.setAttachment({
                kind: 'document',
                filename: data.filename || file.name,
                text: String(data.text),
                sections: Array.isArray(data.sections) ? data.sections : [],
                truncated: Boolean(data.truncated),
            });
        } catch (e) {
            console.warn('[fb-ai] document extraction failed', e);
            this.renderMessage(this.labels.extractFailed || 'Could not extract text.', false, true);
        } finally {
            this.setStatus('', false);
        }
    }

    async extractImageFile(file) {
        const form = new FormData();
        form.append('file', file);
        const extractUrl = this.config.extractImageUrl || this.config.extractUrl;
        const resp = await ((window.getFetch && window.getFetch()) || fetch)(extractUrl, {
            method: 'POST',
            credentials: 'same-origin',
            body: form,
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok || !data || data.success === false || !data.text) {
            throw new Error(data?.error || data?.message || 'image extract failed');
        }
        return {
            filename: data.filename || file.name,
            text: String(data.text),
            sections: Array.isArray(data.sections) ? data.sections : [],
            truncated: Boolean(data.truncated),
        };
    }

    setAttachment(attachment) {
        this.clearAttachment();
        this.attachment = attachment;
        const isImage = attachment.kind === 'image';
        const label = isImage
            ? (this.labels.attachedImage || 'Attached image:')
            : (this.labels.attached || 'Attached:');
        if (this.els.attachmentName) {
            this.els.attachmentName.textContent = `${label} ${attachment.filename}`;
        }
        if (this.els.attachmentPreview) {
            if (isImage && attachment.previewUrl) {
                this.els.attachmentPreview.hidden = false;
                this.wireExpandableImage(
                    this.els.attachmentPreview,
                    attachment.previewUrl,
                    attachment.filename || 'Attached image'
                );
            } else {
                this.els.attachmentPreview.hidden = true;
                this.els.attachmentPreview.removeAttribute('src');
                this.els.attachmentPreview.classList.remove('fb-ai-expandable-image');
                delete this.els.attachmentPreview.dataset.fbExpandableWired;
            }
        }
        if (this.els.attachmentIcon) {
            this.els.attachmentIcon.className = isImage ? 'fas fa-image' : 'fas fa-paperclip';
        }
        if (this.els.attachment) this.els.attachment.hidden = false;
        this.updateSendEnabled();
        this.els.input?.focus();
    }

    clearAttachment() {
        if (this.attachment?.previewUrl) {
            try {
                URL.revokeObjectURL(this.attachment.previewUrl);
            } catch (e) { /* ignore */ }
        }
        this.attachment = null;
        if (this.els.attachment) this.els.attachment.hidden = true;
        if (this.els.attachmentPreview) {
            this.els.attachmentPreview.hidden = true;
            this.els.attachmentPreview.removeAttribute('src');
        }
        if (this.els.attachmentIcon) {
            this.els.attachmentIcon.className = 'fas fa-paperclip';
        }
        this.updateSendEnabled();
    }

    updateSendEnabled() {
        if (!this.els.send || this.busy) return;
        const hasText = Boolean((this.els.input?.value || '').trim());
        this.els.send.disabled = !(hasText || this.attachment);
    }

    // ------------------------------------------------------------------
    // Chat
    // ------------------------------------------------------------------

    buildMessageText(userText, attachment = this.attachment) {
        if (!attachment || !attachment.text) return userText;
        const maxChars = Number(this.config.maxMessageChars || 4000);
        const sections = (attachment.sections || [])
            .map((s) => (s && s.title ? String(s.title).trim() : ''))
            .filter(Boolean);
        let outline = '';
        if (sections.length) {
            outline = `\nDetected section headings:\n${sections.map((t) => `- ${t}`).join('\n')}\n`;
        }
        const sourceLabel = attachment.kind === 'image'
            ? `Pasted form image "${attachment.filename}"`
            : `Imported questionnaire text from "${attachment.filename}"`;
        const header = `\n\n--- ${sourceLabel} ---${outline}\n`;
        const budget = Math.max(200, maxChars - userText.length - header.length - 50);
        let text = attachment.text;
        if (text.length > budget) {
            text = `${text.slice(0, budget)}\n[…document truncated…]`;
        }
        if (attachment.truncated) {
            text += '\n[Note: the extracted document was truncated server-side.]';
        }
        return `${userText}${header}${text}`;
    }

    buildPayload(messageText, options = {}) {
        const formBuilder = { enabled: true };
        if (this.templateId) formBuilder.template_id = this.templateId;
        if (this.versionId) formBuilder.version_id = this.versionId;
        const payload = {
            message: messageText,
            client: 'backoffice',
            keep_running_on_disconnect: true,
            // Form-builder panel never uses chatbot databank/document sources.
            sources: {
                historical: false,
                system_documents: false,
                upr_documents: false,
            },
            page_context: {
                currentPage: window.location.pathname,
                pageTitle: document.title,
                formBuilder: formBuilder,
            },
            conversationHistory: this.messages
                .filter((m) => !m.isError)
                .slice(-MAX_HISTORY_SENT)
                .map((m) => ({ message: m.message, isUser: m.isUser })),
        };
        if (this.conversationId) payload.conversation_id = this.conversationId;
        if (options.allowSensitive) payload.allow_sensitive = true;
        return payload;
    }

    formatDlpFindings(dlpPayload) {
        const findings = dlpPayload?.dlp?.findings || dlpPayload?.findings || [];
        if (!Array.isArray(findings) || !findings.length) return [];
        const labelMap = {
            email: 'Email address',
            phone: 'Phone number',
            jwt: 'Token (JWT)',
            bearer_token: 'Bearer token',
            private_key: 'Private key',
            password: 'Password',
            api_key_or_secret: 'API key / secret',
            iban: 'IBAN / bank account',
            payment_card: 'Payment card number',
        };
        return findings.map((f) => {
            const kind = String(f?.kind || '').trim() || 'sensitive_data';
            const count = Number(f?.count || 1) || 1;
            const label = labelMap[kind] || kind;
            return `${label}${count > 1 ? ` (x${count})` : ''}`;
        });
    }

    showDlpModal({ title, bodyText, bodyLines, actions }) {
        document.querySelector('.humdb-dlp-modal-overlay')?.remove();
        const overlay = document.createElement('div');
        overlay.className = 'humdb-dlp-modal-overlay';
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');

        const modal = document.createElement('div');
        modal.className = 'humdb-dlp-modal';

        const header = document.createElement('div');
        header.className = 'humdb-dlp-modal-header';
        header.textContent = title;

        const body = document.createElement('div');
        body.className = 'humdb-dlp-modal-body';
        const p = document.createElement('p');
        p.textContent = bodyText;
        body.appendChild(p);
        if (bodyLines?.length) {
            const ul = document.createElement('ul');
            bodyLines.forEach((line) => {
                const li = document.createElement('li');
                li.textContent = line;
                ul.appendChild(li);
            });
            body.appendChild(ul);
        }

        const actionsEl = document.createElement('div');
        actionsEl.className = 'humdb-dlp-modal-actions';
        const close = () => overlay.remove();
        actions.forEach((a) => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = `humdb-dlp-btn${a.variant === 'danger' ? ' humdb-dlp-btn-danger' : ''}`;
            btn.textContent = a.label;
            btn.addEventListener('click', () => {
                close();
                a.onClick?.();
            });
            actionsEl.appendChild(btn);
        });

        modal.append(header, body, actionsEl);
        overlay.appendChild(modal);
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) close();
        });
        document.body.appendChild(overlay);
    }

    handleDlpChallenge(messageText, streamOptions, dlpPayload) {
        const findings = this.formatDlpFindings(dlpPayload);
        this.showDlpModal({
            title: this.labels.dlpTitle || 'Sensitive information detected',
            bodyText: this.labels.dlpBody || 'Your message appears to include sensitive information.',
            bodyLines: findings,
            actions: [
                {
                    label: this.labels.dlpCancel || 'Cancel',
                    onClick: () => {},
                },
                {
                    label: this.labels.dlpSendAnyway || 'Send anyway',
                    variant: 'danger',
                    onClick: () => {
                        this.streamChat(messageText, { ...streamOptions, allowSensitive: true });
                    },
                },
            ],
        });
    }

    async handleSend() {
        const raw = (this.els.input.value || '').trim();
        if ((!raw && !this.attachment) || this.busy) return;

        let attachmentSnapshot = this.attachment;
        const needsImageExtract = Boolean(
            attachmentSnapshot?.kind === 'image'
            && attachmentSnapshot.file
            && !attachmentSnapshot.text
        );

        if (needsImageExtract) {
            this.setBusy(true);
            this.setStatus(this.labels.extractingImage || 'Reading image…', true);
            try {
                const extracted = await this.extractImageFile(attachmentSnapshot.file);
                attachmentSnapshot = { ...attachmentSnapshot, ...extracted };
            } catch (e) {
                console.warn('[fb-ai] image extraction failed', e);
                this.pushMessage(this.labels.extractImageFailed || 'Could not read image.', false, true);
                this.setBusy(false);
                this.setStatus('', false);
                return;
            } finally {
                this.setStatus('', false);
                this.setBusy(false);
            }
        }

        const outgoingPreviewUrl = attachmentSnapshot?.previewUrl || null;
        if (outgoingPreviewUrl && this.attachment) {
            // Keep the blob URL alive for the outgoing chat bubble.
            this.attachment.previewUrl = null;
        }
        const defaultPrompt = attachmentSnapshot?.kind === 'image'
            ? 'Build a form template from this pasted image.'
            : 'Build a form template from this attached questionnaire.';
        const messageText = this.buildMessageText(raw || defaultPrompt, attachmentSnapshot);
        this.els.input.value = '';
        const displayed = this.buildDisplayedUserMessage(raw, attachmentSnapshot);
        this.clearAttachment();
        this.hideAction();

        this.pushMessage(displayed, true, false, {
            previewUrl: outgoingPreviewUrl,
        });
        await this.streamChat(messageText, {});
    }

    buildDisplayedUserMessage(raw, attachment) {
        const parts = [];
        if (raw) parts.push(raw);
        if (attachment) {
            const icon = attachment.kind === 'image' ? '🖼' : '📎';
            parts.push(`${icon} ${attachment.filename}`);
        }
        return parts.join('\n');
    }

    pushMessage(message, isUser, isError = false, options = {}) {
        this.messages.push({ message, isUser, isError });
        if (this.messages.length > MAX_HISTORY_STORED) {
            this.messages = this.messages.slice(-MAX_HISTORY_STORED);
        }
        this.renderMessage(message, isUser, isError, options);
        this.saveState();
    }

    renderMessage(message, isUser, isError = false, options = {}) {
        const welcome = this.els.messages.querySelector('.fb-ai-welcome');
        if (welcome) welcome.hidden = true;
        const div = document.createElement('div');
        div.className = isError
            ? 'fb-ai-msg fb-ai-msg-error'
            : `fb-ai-msg ${isUser ? 'fb-ai-msg-user' : 'fb-ai-msg-assistant'}`;
        if (isUser && options.previewUrl) {
            if (message) {
                const textEl = document.createElement('div');
                textEl.textContent = message;
                div.appendChild(textEl);
            }
            const img = document.createElement('img');
            img.className = 'fb-ai-msg-image-preview';
            this.wireExpandableImage(img, options.previewUrl, 'Pasted image');
            div.appendChild(img);
        } else if (isUser || isError) {
            div.textContent = message;
        } else {
            div.innerHTML = message; // server-rendered HTML answer
        }
        this.els.messages.appendChild(div);
        this.scrollToBottom();
        return div;
    }

    scrollToBottom() {
        this.els.messages.scrollTop = this.els.messages.scrollHeight;
    }

    setStatus(text, visible) {
        if (!this.els.status) return;
        this.els.status.hidden = !visible;
        if (this.els.statusText) this.els.statusText.textContent = text || '';
    }

    setBusy(busy) {
        this.busy = busy;
        if (this.els.input) this.els.input.disabled = busy;
        this.updateSendEnabled();
    }

    async streamChat(messageText, streamOptions = {}) {
        this.setBusy(true);
        this.setStatus(this.labels.thinking || 'Working…', true);
        this.abortController = new AbortController();

        const bubble = this.renderMessage('', false);
        let buffer = '';
        let doneReceived = false;
        let formBuilderResult = null;

        try {
            const resp = await ((window.getFetch && window.getFetch()) || fetch)(this.config.chatStreamUrl, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'text/event-stream',
                },
                body: JSON.stringify(this.buildPayload(messageText, streamOptions)),
                signal: this.abortController.signal,
            });
            if (!resp.ok || !resp.body) {
                throw new Error(`HTTP ${resp.status}`);
            }

            const reader = resp.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let sseBuffer = '';

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                sseBuffer += decoder.decode(value, { stream: true });
                const parts = sseBuffer.split('\n\n');
                sseBuffer = parts.pop() || '';
                for (const part of parts) {
                    const dataLines = part
                        .split('\n')
                        .filter((l) => l.startsWith('data:'))
                        .map((l) => l.slice(5).trim());
                    if (!dataLines.length) continue;
                    let msg;
                    try {
                        msg = JSON.parse(dataLines.join('\n'));
                    } catch (e) {
                        continue;
                    }
                    if (msg.type === 'meta') {
                        if (msg.conversation_id) this.conversationId = msg.conversation_id;
                    } else if (msg.type === 'step') {
                        this.setStatus(msg.message || this.labels.thinking || '', true);
                    } else if (msg.type === 'delta') {
                        buffer += msg.text || '';
                        bubble.innerHTML = buffer;
                        this.scrollToBottom();
                    } else if (msg.type === 'done') {
                        doneReceived = true;
                        buffer = msg.response || buffer;
                        if (msg.conversation_id) this.conversationId = msg.conversation_id;
                        if (msg.form_builder_result) formBuilderResult = msg.form_builder_result;
                    } else if (msg.type === 'error') {
                        const errType = String(msg.error_type || '');
                        if (errType === 'dlp_requires_confirmation') {
                            const dlpErr = new Error(msg.error || msg.message || 'Sensitive information detected');
                            dlpErr.name = 'DlpConfirmationRequired';
                            dlpErr.dlp = msg;
                            throw dlpErr;
                        }
                        if (errType === 'dlp_blocked') {
                            const dlpErr = new Error(msg.error || msg.message || 'Request blocked');
                            dlpErr.name = 'DlpBlocked';
                            dlpErr.dlp = msg;
                            throw dlpErr;
                        }
                        throw new Error(msg.message || msg.error || 'stream error');
                    }
                }
            }

            if (!buffer) {
                throw new Error('empty response');
            }
            buffer = this.stripSourcesFromAnswer(
                this.stripEditModeBoilerplate(
                    this.ensureEditLinkInAnswer(buffer, formBuilderResult)
                )
            );
            bubble.innerHTML = buffer;
            this.messages.push({ message: buffer, isUser: false });
            this.saveState();
            this.handleAnswerActions(buffer, formBuilderResult);
        } catch (e) {
            bubble.remove();
            if (e?.name === 'DlpConfirmationRequired') {
                this.handleDlpChallenge(messageText, streamOptions, e.dlp);
            } else if (e?.name === 'DlpBlocked') {
                this.pushMessage(e.message || this.labels.dlpBlocked || 'Request blocked.', false, true);
            } else if (e?.name !== 'AbortError') {
                console.error('[fb-ai] chat failed', e);
                this.pushMessage(this.labels.error || 'Something went wrong.', false, true);
            }
        } finally {
            this.setBusy(false);
            this.setStatus('', false);
            this.abortController = null;
            this.scrollToBottom();
            if (!doneReceived) this.saveState();
        }
    }

    // ------------------------------------------------------------------
    // Post-answer actions: reload builder / open created template
    // ------------------------------------------------------------------

    stripSourcesFromAnswer(answerHtml) {
        let html = answerHtml || '';
        if (!html) return html;
        try {
            const doc = new DOMParser().parseFromString(html, 'text/html');
            doc.querySelectorAll('.chat-response-sources').forEach((el) => el.remove());
            html = doc.body.innerHTML;
        } catch (_e) {}
        return html;
    }

    stripEditModeBoilerplate(answerHtml) {
        if (!this.templateId) return answerHtml || '';
        let html = answerHtml || '';
        if (!html) return html;
        const boilerplateRe = /warnings?\s*:\s*none|no warnings were produced|all changes (?:are|were) (?:in|applied to) the draft|please review(?: the draft)? and deploy|review the draft and deploy/i;
        try {
            const doc = new DOMParser().parseFromString(html, 'text/html');
            doc.querySelectorAll('a[href*="/admin/templates/edit/"]').forEach((a) => {
                const label = (a.textContent || '').toLowerCase();
                if (label.includes('open the draft') || label.includes('open the template')) {
                    const block = a.closest('p, li');
                    if (block) block.remove();
                    else a.remove();
                }
            });
            doc.querySelectorAll('p, li').forEach((el) => {
                if (boilerplateRe.test(el.textContent || '')) el.remove();
            });
            html = doc.body.innerHTML;
        } catch (_e) {}
        return html;
    }

    ensureEditLinkInAnswer(answerHtml, formBuilderResult) {
        let html = answerHtml || '';
        // On the form builder page the user is already editing — link only on templates list.
        if (this.templateId) return html;
        const link = this.findTemplateEditLink(html);
        const editUrl = formBuilderResult?.edit_url || link?.url;
        if (!editUrl || link) return html;
        const label = this.labels.openTemplate || 'Open the template in the form builder';
        return `${html}<p><a href="${editUrl}">${escapeHtml(label)}</a></p>`;
    }

    handleAnswerActions(answerHtml, formBuilderResult = null) {
        let link = this.findTemplateEditLink(answerHtml);
        if (!link && formBuilderResult?.edit_url) {
            const href = String(formBuilderResult.edit_url);
            const m = href.match(/^\/admin\/templates\/edit\/(\d+)(?:\?([^#]*))?/);
            if (m) {
                let versionId = null;
                if (m[2]) {
                    const vm = m[2].match(/(?:^|&)version_id=(\d+)/);
                    if (vm) versionId = parseInt(vm[1], 10);
                }
                link = {
                    url: href,
                    templateId: parseInt(m[1], 10),
                    versionId,
                };
            }
        }
        if (!link) return;

        if (
            formBuilderResult?.action === 'create_form_template'
            && formBuilderResult.template_id
        ) {
            window.dispatchEvent(new CustomEvent('humdb:template-created', {
                detail: { ...formBuilderResult, edit_url: link.url },
            }));
        }

        if (this.templateId && link.templateId === this.templateId) {
            // Existing template edited: refresh the builder in-place (no full page reload).
            const target = link.url;
            const effectiveVersionId = (
                formBuilderResult?.version_id != null
                    ? formBuilderResult.version_id
                    : link.versionId
            );
            this.setStatus(this.labels.reloading || 'Draft updated — refreshing the builder…', true);
            this.saveState();
            setTimeout(
                () => this.reloadBuilderAjax(target, effectiveVersionId, formBuilderResult),
                400
            );
        } else if (!this.templateId) {
            // Created from the templates list: persist chat under the new template id.
            this.migrateStateToTemplate(link.templateId);
            this.showAction(this.labels.openTemplate || 'Open the template', () => {
                this.markPanelReopenOnLoad();
                window.location.href = link.url;
            });
        }
    }

    // ------------------------------------------------------------------
    // In-place AJAX reload of the form builder after AI changes
    // ------------------------------------------------------------------

    async reloadBuilderAjax(url, newVersionId = null, formBuilderResult = null) {
        // Only works when the form builder AJAX layer is present (i.e. on the edit template page).
        const refreshFn = window.FormBuilderAjax && window.FormBuilderAjax.refreshFromHtml;
        if (typeof refreshFn !== 'function') {
            // No AJAX support (e.g. on the templates list page) — fall back to full navigation.
            try { sessionStorage.setItem(`${this.storageKey}_reopen`, '1'); } catch (_e) {}
            window.location.href = url;
            return;
        }

        this.setBusy(true);
        this.setStatus(this.labels.refreshing || this.labels.reloading || 'Refreshing…', true);
        this.hideAction();

        // Snapshot current section/item IDs so we can detect which ones are new after the swap.
        const prevSectionIds = this._snapshotIds('.section-item[data-section-id]', 'data-section-id');
        const prevItemIds = this._snapshotIds('tr[data-item-id]', 'data-item-id');

        try {
            const resp = await ((window.getFetch && window.getFetch()) || fetch)(url, {
                method: 'GET',
                credentials: 'same-origin',
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const html = await resp.text();

            // Swap out builder sections, data blobs, and the version status banner.
            refreshFn(html);

            // Also refresh the version button in the page header (cosmetic sync).
            try {
                const doc = new DOMParser().parseFromString(html, 'text/html');
                const newVersionBtn = doc.getElementById('versions-modal-btn');
                const curVersionBtn = document.getElementById('versions-modal-btn');
                if (newVersionBtn && curVersionBtn) {
                    curVersionBtn.innerHTML = newVersionBtn.innerHTML;
                }
            } catch (_e) {}

            // Highlight newly added / modified elements.
            this.highlightAiChanges(formBuilderResult, prevSectionIds, prevItemIds);

            // Keep browser URL in sync (pushState for a new version, replaceState otherwise).
            try {
                const applyUrl = (resp.url && resp.url !== url) ? resp.url : url;
                if (newVersionId && this.versionId && newVersionId !== this.versionId) {
                    window.history.pushState({}, document.title, applyUrl);
                } else {
                    window.history.replaceState({}, document.title, applyUrl);
                }
            } catch (_e) {}

            // Update our own versionId so subsequent messages target the new version.
            if (newVersionId) this.versionId = newVersionId;

            this.setStatus('', false);
        } catch (e) {
            console.error('[fb-ai] AJAX reload failed, falling back to full reload', e);
            // Fall back gracefully: the panel state is already saved above.
            try { sessionStorage.setItem(`${this.storageKey}_reopen`, '1'); } catch (_e) {}
            window.location.href = url;
        } finally {
            this.setBusy(false);
        }
    }

    // ------------------------------------------------------------------
    // DOM snapshot helper + AI-change highlight animations
    // ------------------------------------------------------------------

    _snapshotIds(selector, attr) {
        const ids = new Set();
        try {
            document.querySelectorAll(selector).forEach((el) => {
                const v = el.getAttribute(attr);
                if (v) ids.add(v);
            });
        } catch (_e) {}
        return ids;
    }

    highlightAiChanges(formBuilderResult, prevSectionIds, prevItemIds) {
        // One rAF to let the refreshed DOM paint before we measure / animate.
        requestAnimationFrame(() => {
            const newSectionEls = [];
            const modifiedSectionEls = [];
            const newItemEls = [];
            const modifiedItemEls = [];

            // Classify sections: new vs pre-existing
            document.querySelectorAll('.section-item[data-section-id]').forEach((el) => {
                if (!prevSectionIds.has(el.getAttribute('data-section-id'))) {
                    newSectionEls.push(el);
                }
            });

            // Classify item rows: new vs pre-existing
            document.querySelectorAll('tr[data-item-id]').forEach((el) => {
                if (!prevItemIds.has(el.getAttribute('data-item-id'))) {
                    newItemEls.push(el);
                }
            });

            // From AI result refs: bucket modified (existing) sections and items
            const refs = (formBuilderResult && formBuilderResult.refs) ? formBuilderResult.refs : {};
            const newSectionIdSet = new Set(newSectionEls.map((el) => el.getAttribute('data-section-id')));
            const newItemIdSet    = new Set(newItemEls.map((el) => el.getAttribute('data-item-id')));

            for (const ref of Object.values(refs)) {
                if (!ref || !ref.id) continue;
                const id = String(ref.id);
                if (ref.type === 'section' && !newSectionIdSet.has(id)) {
                    const el = document.querySelector(`.section-item[data-section-id="${id}"]`);
                    if (el) modifiedSectionEls.push(el);
                } else if (ref.type === 'item' && !newItemIdSet.has(id)) {
                    const el = document.querySelector(`tr[data-item-id="${id}"]`);
                    if (el) modifiedItemEls.push(el);
                }
            }

            // ── Apply animations ──────────────────────────────────────

            // How long before we start fading out the accent border / badge.
            const FADE_MS  = 4000;
            const CLEAN_MS = FADE_MS + 1800;

            const scheduleClean = (el, classes) => {
                setTimeout(() => el.classList.add('fb-ai-done'), FADE_MS);
                setTimeout(() => el.classList.remove(...classes, 'fb-ai-done'), CLEAN_MS);
            };

            // New sections
            newSectionEls.forEach((el) => {
                el.classList.add('fb-ai-new-section');

                // Inject sparkle badge beside the h3 section title
                const h3 = el.querySelector('.section-header-banner h3');
                if (h3 && !el.querySelector('.fb-ai-badge')) {
                    const badge = document.createElement('span');
                    badge.className = 'fb-ai-badge';
                    badge.innerHTML = '<i class="fas fa-wand-magic-sparkles" style="font-size:0.55rem"></i>&nbsp;AI';
                    h3.insertAdjacentElement('afterend', badge);
                    setTimeout(() => badge.classList.add('fb-ai-done'), FADE_MS);
                    setTimeout(() => badge.remove(), CLEAN_MS);
                }

                scheduleClean(el, ['fb-ai-new-section']);
            });

            // New item rows
            newItemEls.forEach((el) => {
                el.classList.add('fb-ai-new-row');
                scheduleClean(el, ['fb-ai-new-row']);
            });

            // Modified sections
            modifiedSectionEls.forEach((el) => {
                el.classList.add('fb-ai-modified-section');
                scheduleClean(el, ['fb-ai-modified-section']);
            });

            // Modified item rows
            modifiedItemEls.forEach((el) => {
                el.classList.add('fb-ai-modified-row');
                scheduleClean(el, ['fb-ai-modified-row']);
            });

            // Scroll to the first changed element (with a slight delay for animation to start)
            const first = newSectionEls[0] || newItemEls[0] || modifiedSectionEls[0] || modifiedItemEls[0];
            if (first) {
                setTimeout(() => first.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 200);
            }
        });
    }

    parseTemplateEditLink(href) {
        const m = String(href || '').match(/^\/admin\/templates\/edit\/(\d+)(?:\?([^#]*))?/);
        if (!m) return null;
        let versionId = null;
        if (m[2]) {
            const vm = m[2].match(/(?:^|&)version_id=(\d+)/);
            if (vm) versionId = parseInt(vm[1], 10);
        }
        return { url: href, templateId: parseInt(m[1], 10), versionId };
    }

    findTemplateEditLink(html) {
        try {
            const doc = new DOMParser().parseFromString(html, 'text/html');
            const anchors = Array.from(doc.querySelectorAll('a[href]'));
            for (const a of anchors) {
                const link = this.parseTemplateEditLink(a.getAttribute('href') || '');
                if (link) return link;
            }
        } catch (e) { /* ignore parse errors */ }
        return null;
    }

    showAction(label, onClick) {
        if (!this.els.actionBar || !this.els.actionBtn) return;
        this.els.actionBtn.textContent = label;
        this.els.actionBtn.onclick = onClick;
        this.els.actionBar.hidden = false;
    }

    hideAction() {
        if (this.els.actionBar) this.els.actionBar.hidden = true;
    }
}

function initFormBuilderAIAssistant() {
    const config = readConfig();
    if (!config) return;
    const assistant = new FormBuilderAIAssistant(config);
    assistant.init();
    window.formBuilderAIAssistant = assistant;
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initFormBuilderAIAssistant);
} else {
    initFormBuilderAIAssistant();
}

export { initFormBuilderAIAssistant };
