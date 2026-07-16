/**
 * Chatbot FormBuilderAi module
 * @module chatbot/form-builder-ai
 */

const FB_AI_IMAGE_MIME_RE = /^image\/(png|jpe?g|webp|gif)$/i;
const FB_AI_IMAGE_EXT_RE = /\.(png|jpe?g|webp|gif)$/i;

function fbAiIsImageFile(file) {
    if (!file) return false;
    const type = String(file.type || '').toLowerCase();
    if (FB_AI_IMAGE_MIME_RE.test(type)) return true;
    return FB_AI_IMAGE_EXT_RE.test(String(file.name || '').toLowerCase());
}

function fbAiNormalizeImageFilename(file) {
    if (file.name && String(file.name).trim()) return file;
    const ext = (file.type || 'image/png').split('/')[1] || 'png';
    return new File([file], `pasted-image.${ext}`, { type: file.type || 'image/png' });
}

function fbAiCsrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
}

function fbAiUniqueFilename(name, existingNames) {
    const baseName = String(name || 'attachment').trim() || 'attachment';
    if (!existingNames.has(baseName)) return baseName;
    const extMatch = baseName.match(/^(.+?)(\.[^.]+)?$/);
    const stem = extMatch?.[1] || baseName;
    const ext = extMatch?.[2] || '';
    let i = 2;
    while (existingNames.has(`${stem}-${i}${ext}`)) i += 1;
    return `${stem}-${i}${ext}`;
}

/** One screenshot paste often exposes the same bitmap as png + bmp/jpeg — keep one. */
function fbAiPickClipboardImages(files) {
    if (!files || files.length <= 1) return files || [];
    const preferredTypes = ['image/png', 'image/jpeg', 'image/webp', 'image/gif'];
    for (const mime of preferredTypes) {
        const matches = files.filter((f) => String(f.type || '').toLowerCase() === mime);
        if (matches.length) {
            return [matches.sort((a, b) => (b.size || 0) - (a.size || 0))[0]];
        }
    }
    return [files.sort((a, b) => (b.size || 0) - (a.size || 0))[0]];
}

function fbAiCollectClipboardImageFiles(clipboardData) {
    const items = clipboardData?.items;
    if (!items) return [];
    const imageFiles = [];
    for (const item of items) {
        if (item.type && item.type.startsWith('image/')) {
            const file = item.getAsFile();
            if (file) imageFiles.push(fbAiNormalizeImageFilename(file));
        }
    }
    return fbAiPickClipboardImages(imageFiles);
}

const FB_AI_MAX_IMAGE_ATTACHMENTS = 12;

export const FormBuilderAiMixin = {
    _loadFormBuilderAiConfig() {
        try {
            const el = document.getElementById('fb-ai-assistant-config');
            if (!el) {
                this._fbAiConfig = null;
                return null;
            }
            this._fbAiConfig = JSON.parse(el.textContent || 'null');
            return this._fbAiConfig;
        } catch (_) {
            this._fbAiConfig = null;
            return null;
        }
    },

    _ensureFormBuilderAiIntegration() {
        if (this._fbAiClickBound) return;
        this._fbAiClickBound = true;
        this._loadFormBuilderAiConfig();
        document.addEventListener('click', (e) => {
            const btn = e.target.closest('#ai-assistant-btn');
            if (!btn) return;
            if (!this._loadFormBuilderAiConfig()) return;
            e.preventDefault();
            e.stopImmediatePropagation();
            this._openFormBuilderChat();
        }, true);
        document.addEventListener('formBuilder:initialized', () => {
            this._loadFormBuilderAiConfig();
            this._syncFormBuilderChatInput();
        });
    },

    _syncFormBuilderAiPanelFab(forceHidden) {
        if (!this.elements.fab || this._isImmersive()) return;
        // User dismissed the FAB for this page load (dragged to hide zone) — keep it gone.
        if (this._fabSessionHidden) {
            const fab = this.elements.fab;
            fab.classList.add('fab-session-hidden');
            fab.hidden = true;
            fab.style.setProperty('display', 'none', 'important');
            try { fab.setAttribute('aria-hidden', 'true'); } catch (_) { /* ignore */ }
            return;
        }
        const hidden = typeof forceHidden === 'boolean'
            ? forceHidden
            : !!(document.body && document.body.classList.contains('fb-ai-panel-open'));
        this.elements.fab.hidden = hidden;
        try {
            this.elements.fab.setAttribute('aria-hidden', hidden ? 'true' : 'false');
        } catch (_) { /* ignore */ }
    },

    _openFormBuilderChat() {
        if (!this._loadFormBuilderAiConfig()) return;
        if (!this.elements || !this.elements.widget || !this.elements.messages) {
            console.warn('[chatbot] Form builder AI requires the chat widget (chatbot must be enabled for this user).');
            return;
        }
        const currentId = this._getFloatingConversationId && this._getFloatingConversationId();
        if (this._fbAiConversationId && currentId === this._fbAiConversationId) {
            this.toggleChat(true);
            return;
        }
        this._setFloatingConversationId(null);
        this._fbAiConversationId = null;
        this.loadConversation([]);
        this._syncFormBuilderChatInput();
        this._setupFormBuilderAttachmentHandlers();
        this.toggleChat(true);
    },

    _clearFormBuilderWelcomeBubble() {
        try {
            this.elements.messages?.querySelectorAll('.fb-ai-welcome-bubble').forEach((el) => el.remove());
        } catch (_) { /* ignore */ }
    },

    updateFormBuilderVersionId(id) {
        if (this._fbAiConfig && id) {
            this._fbAiConfig.versionId = id;
        }
    },

    _fbAiLabels() {
        return (this._fbAiConfig && this._fbAiConfig.labels) || {};
    },

    _parseTemplateEditLink(href) {
        const m = String(href || '').match(/^\/admin\/templates\/edit\/(\d+)(?:\?([^#]*))?/);
        if (!m) return null;
        let versionId = null;
        if (m[2]) {
            const vm = m[2].match(/(?:^|&)version_id=(\d+)/);
            if (vm) versionId = parseInt(vm[1], 10);
        }
        return { url: href, templateId: parseInt(m[1], 10), versionId };
    },

    _findTemplateEditLink(html) {
        try {
            const doc = new DOMParser().parseFromString(html || '', 'text/html');
            const anchors = Array.from(doc.querySelectorAll('a[href]'));
            for (const a of anchors) {
                const link = this._parseTemplateEditLink(a.getAttribute('href') || '');
                if (link) return link;
            }
        } catch (_) { /* ignore parse errors */ }
        return null;
    },

    _handleFormBuilderResult(formBuilderResult, answerHtml = '', contentElement = null) {
        if (!this._fbAiConfig || !formBuilderResult) return;

        let link = this._findTemplateEditLink(answerHtml);
        if (!link && formBuilderResult.edit_url) {
            const href = String(formBuilderResult.edit_url);
            const m = href.match(/^\/admin\/templates\/edit\/(\d+)(?:\?([^#]*))?/);
            if (m) {
                let versionId = null;
                if (m[2]) {
                    const vm = m[2].match(/(?:^|&)version_id=(\d+)/);
                    if (vm) versionId = parseInt(vm[1], 10);
                }
                link = { url: href, templateId: parseInt(m[1], 10), versionId };
            }
        }
        if (!link && formBuilderResult.template_id != null) {
            const templateId = Number(formBuilderResult.template_id);
            const versionId = formBuilderResult.version_id != null
                ? Number(formBuilderResult.version_id)
                : null;
            const url = `/admin/templates/edit/${templateId}`
                + (versionId ? `?version_id=${versionId}` : '');
            link = { url, templateId, versionId };
        }
        if (!link) return;

        if (formBuilderResult.version_id != null) {
            this.updateFormBuilderVersionId(formBuilderResult.version_id);
        }

        const writeActions = new Set(['edit_form_template', 'create_form_template', 'translate_form_template']);
        const didWrite = writeActions.has(String(formBuilderResult.action || ''));
        if (didWrite && contentElement) {
            this._fbAiPendingApplyActions = { contentElement, formBuilderResult };
        }

        if (
            formBuilderResult.action === 'create_form_template'
            && formBuilderResult.template_id
        ) {
            window.dispatchEvent(new CustomEvent('humdb:template-created', {
                detail: { ...formBuilderResult, edit_url: link.url },
            }));
        }

        const configTemplateId = this._fbAiConfig.templateId != null
            ? Number(this._fbAiConfig.templateId)
            : null;
        if (configTemplateId && Number(link.templateId) === configTemplateId) {
            const effectiveVersionId = (
                formBuilderResult.version_id != null
                    ? Number(formBuilderResult.version_id)
                    : link.versionId
            );
            setTimeout(
                () => this._reloadFormBuilderAjax(link.url, effectiveVersionId, formBuilderResult),
                400
            );
            return;
        }

        if (!configTemplateId) {
            this._fbAiConfig.templateId = link.templateId;
        }
    },

    _stripFormBuilderEditAnswerHtml(answerHtml) {
        if (!this._fbAiConfig?.templateId) return answerHtml || '';
        let html = answerHtml || '';
        if (!html) return html;
        const boilerplateRe = /warnings?\s*:\s*none|no warnings were produced|all changes (?:are|were) (?:in|applied to) the draft|please review(?: the draft)? and deploy|review the draft and deploy|i can apply|open the draft to review|which would you like me to prepare/i;
        try {
            const doc = new DOMParser().parseFromString(html, 'text/html');
            doc.querySelectorAll('a[href*="/admin/templates/edit/"], a[href*="chatbot-tour="]').forEach((a) => {
                const label = (a.textContent || '').toLowerCase();
                if (label.includes('open the draft') || label.includes('open the template') || a.getAttribute('href')?.includes('chatbot-tour=')) {
                    const block = a.closest('p, li');
                    if (block) block.remove();
                    else a.remove();
                }
            });
            doc.querySelectorAll('.chatbot-tour-trigger, .chatbot-show-me, .chatbot-show-me-wrapper').forEach((el) => el.remove());
            doc.querySelectorAll('p, li').forEach((el) => {
                if (boilerplateRe.test(el.textContent || '')) el.remove();
            });
            html = doc.body.innerHTML;
        } catch (_) { /* ignore */ }
        return html;
    },

    _appendFormBuilderApplyActions(contentElement, formBuilderResult) {
        if (!contentElement || !formBuilderResult) return;
        contentElement.querySelectorAll('.fb-ai-apply-actions').forEach((el) => el.remove());

        const changes = Array.isArray(formBuilderResult.changes) ? formBuilderResult.changes.filter(Boolean) : [];
        const labels = this._fbAiLabels();
        const wrap = document.createElement('div');
        wrap.className = 'fb-ai-apply-actions';

        if (changes.length) {
            const summary = document.createElement('div');
            summary.className = 'fb-ai-changes-summary';
            const title = document.createElement('p');
            title.className = 'fb-ai-changes-summary-title';
            title.innerHTML = `<strong>${this.escapeHtml(labels.changesApplied || 'Changes applied')}</strong>`;
            summary.appendChild(title);
            const list = document.createElement('ul');
            list.className = 'fb-ai-changes-list';
            changes.forEach((change) => {
                const li = document.createElement('li');
                li.textContent = String(change);
                list.appendChild(li);
            });
            summary.appendChild(list);
            wrap.appendChild(summary);
        }

        const btnRow = document.createElement('div');
        btnRow.className = 'fb-ai-apply-actions-buttons';

        const undoBtn = document.createElement('button');
        undoBtn.type = 'button';
        undoBtn.className = 'btn btn-secondary btn-sm fb-ai-undo-btn';
        undoBtn.innerHTML = `<i class="fas fa-undo mr-1"></i>${this.escapeHtml(labels.undo || 'Undo')}`;
        undoBtn.disabled = !this._fbAiLastEditUndoRedo?.before;
        undoBtn.addEventListener('click', () => this._formBuilderAiUndo(undoBtn, redoBtn));

        const redoBtn = document.createElement('button');
        redoBtn.type = 'button';
        redoBtn.className = 'btn btn-secondary btn-sm fb-ai-redo-btn';
        redoBtn.innerHTML = `<i class="fas fa-redo mr-1"></i>${this.escapeHtml(labels.redo || 'Redo')}`;
        redoBtn.disabled = true;
        redoBtn.addEventListener('click', () => this._formBuilderAiRedo(undoBtn, redoBtn));

        btnRow.appendChild(undoBtn);
        btnRow.appendChild(redoBtn);
        wrap.appendChild(btnRow);
        contentElement.appendChild(wrap);
    },

    _fbAiRestoreStructureUrl(templateId) {
        const tpl = (this._fbAiConfig && this._fbAiConfig.restoreStructureUrl)
            || '/admin/templates/0/ai-restore-structure';
        return String(tpl).replace('/templates/0/', `/templates/${encodeURIComponent(templateId)}/`);
    },

    _syncFormBuilderAiUndoRedoButtons(undoBtn, redoBtn) {
        const state = this._fbAiLastEditUndoRedo;
        if (!undoBtn || !redoBtn || !state) return;
        if (state.active === 'before') {
            undoBtn.disabled = true;
            redoBtn.disabled = !state.after;
        } else {
            undoBtn.disabled = !state.before;
            redoBtn.disabled = true;
        }
    },

    async _formBuilderAiRestoreSnapshot(snapshot, undoBtn, redoBtn, targetActive) {
        const templateId = this._fbAiConfig && this._fbAiConfig.templateId;
        if (!templateId || !snapshot) return;
        const labels = this._fbAiLabels();
        if (undoBtn) undoBtn.disabled = true;
        if (redoBtn) redoBtn.disabled = true;
        try {
            const resp = await ((window.getFetch && window.getFetch()) || fetch)(
                this._fbAiRestoreStructureUrl(templateId),
                {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '',
                        'X-Requested-With': 'XMLHttpRequest',
                    },
                    body: JSON.stringify({ structure: snapshot }),
                }
            );
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok || data.success === false) {
                throw new Error(data.message || data.error || `HTTP ${resp.status}`);
            }
            const versionId = data.version_id != null ? Number(data.version_id) : Number(snapshot.version_id);
            const url = data.edit_url
                || `/admin/templates/edit/${encodeURIComponent(templateId)}`
                + (versionId ? `?version_id=${versionId}` : '');
            await this._reloadFormBuilderAjax(url, versionId || null, null);
            if (this._fbAiLastEditUndoRedo) {
                this._fbAiLastEditUndoRedo.active = targetActive;
            }
            this._syncFormBuilderAiUndoRedoButtons(undoBtn, redoBtn);
        } catch (e) {
            console.error('[chatbot] form builder restore failed', e);
            this._appendFormBuilderStatusBubble(
                targetActive === 'before'
                    ? (labels.undoFailed || 'Could not undo changes.')
                    : (labels.redoFailed || 'Could not redo changes.'),
                true
            );
            this._syncFormBuilderAiUndoRedoButtons(undoBtn, redoBtn);
        }
    },

    _formBuilderAiUndo(undoBtn, redoBtn) {
        const state = this._fbAiLastEditUndoRedo;
        if (!state?.before || state.active === 'before') return;
        void this._formBuilderAiRestoreSnapshot(state.before, undoBtn, redoBtn, 'before');
    },

    _formBuilderAiRedo(undoBtn, redoBtn) {
        const state = this._fbAiLastEditUndoRedo;
        if (!state?.after || state.active === 'after') return;
        void this._formBuilderAiRestoreSnapshot(state.after, undoBtn, redoBtn, 'after');
    },

    _appendFormBuilderStatusBubble(text, isError = false) {
        if (!this.elements?.messages || !text) return;
        const msgEl = document.createElement('div');
        msgEl.className = `chat-message bot fb-ai-status-bubble${isError ? ' fb-ai-status-error' : ''}`;
        const inner = document.createElement('div');
        inner.className = 'chat-message-content';
        inner.textContent = String(text);
        msgEl.appendChild(inner);
        this.elements.messages.appendChild(msgEl);
        this.scrollToBottom();
    },

    _snapshotFormBuilderIds(selector, attr) {
        const ids = new Set();
        try {
            document.querySelectorAll(selector).forEach((el) => {
                const v = el.getAttribute(attr);
                if (v) ids.add(v);
            });
        } catch (_) { /* ignore */ }
        return ids;
    },

    _highlightFormBuilderAiChanges(formBuilderResult, prevSectionIds, prevItemIds) {
        requestAnimationFrame(() => {
            const newSectionEls = [];
            const modifiedSectionEls = [];
            const newItemEls = [];
            const modifiedItemEls = [];

            document.querySelectorAll('.section-item[data-section-id]').forEach((el) => {
                if (!prevSectionIds.has(el.getAttribute('data-section-id'))) {
                    newSectionEls.push(el);
                }
            });

            document.querySelectorAll('tr[data-item-id]').forEach((el) => {
                if (!prevItemIds.has(el.getAttribute('data-item-id'))) {
                    newItemEls.push(el);
                }
            });

            const refs = (formBuilderResult && formBuilderResult.refs) ? formBuilderResult.refs : {};
            const newSectionIdSet = new Set(newSectionEls.map((el) => el.getAttribute('data-section-id')));
            const newItemIdSet = new Set(newItemEls.map((el) => el.getAttribute('data-item-id')));

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

            const FADE_MS = 4000;
            const CLEAN_MS = FADE_MS + 1800;

            const scheduleClean = (el, classes) => {
                setTimeout(() => el.classList.add('fb-ai-done'), FADE_MS);
                setTimeout(() => el.classList.remove(...classes, 'fb-ai-done'), CLEAN_MS);
            };

            newSectionEls.forEach((el) => {
                el.classList.add('fb-ai-new-section');
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

            newItemEls.forEach((el) => {
                el.classList.add('fb-ai-new-row');
                scheduleClean(el, ['fb-ai-new-row']);
            });

            modifiedSectionEls.forEach((el) => {
                el.classList.add('fb-ai-modified-section');
                scheduleClean(el, ['fb-ai-modified-section']);
            });

            modifiedItemEls.forEach((el) => {
                el.classList.add('fb-ai-modified-row');
                scheduleClean(el, ['fb-ai-modified-row']);
            });

            const first = newSectionEls[0] || newItemEls[0] || modifiedSectionEls[0] || modifiedItemEls[0];
            if (first) {
                setTimeout(() => first.scrollIntoView({ behavior: 'smooth', block: 'nearest' }), 200);
            }
        });
    },

    async _reloadFormBuilderAjax(url, newVersionId = null, formBuilderResult = null) {
        const refreshFn = window.FormBuilderAjax && window.FormBuilderAjax.refreshFromHtml;
        if (typeof refreshFn !== 'function') {
            window.location.href = url;
            return;
        }

        const prevSectionIds = this._snapshotFormBuilderIds('.section-item[data-section-id]', 'data-section-id');
        const prevItemIds = this._snapshotFormBuilderIds('tr[data-item-id]', 'data-item-id');
        const isAiApplyReload = !!(formBuilderResult && formBuilderResult.undo_structure && formBuilderResult.redo_structure);

        try {
            const resp = await ((window.getFetch && window.getFetch()) || fetch)(url, {
                method: 'GET',
                credentials: 'same-origin',
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const html = await resp.text();
            refreshFn(html);

            if (isAiApplyReload) {
                this._fbAiLastEditUndoRedo = {
                    before: formBuilderResult.undo_structure,
                    after: formBuilderResult.redo_structure,
                    active: 'after',
                };
            }

            try {
                const doc = new DOMParser().parseFromString(html, 'text/html');
                const newVersionBtn = doc.getElementById('versions-modal-btn');
                const curVersionBtn = document.getElementById('versions-modal-btn');
                if (newVersionBtn && curVersionBtn) {
                    curVersionBtn.innerHTML = newVersionBtn.innerHTML;
                }
            } catch (_) { /* ignore */ }

            this._highlightFormBuilderAiChanges(formBuilderResult, prevSectionIds, prevItemIds);

            try {
                const applyUrl = (resp.url && resp.url !== url) ? resp.url : url;
                const prevVersionId = this._fbAiConfig && this._fbAiConfig.versionId;
                if (newVersionId && prevVersionId && newVersionId !== prevVersionId) {
                    window.history.pushState({}, document.title, applyUrl);
                } else {
                    window.history.replaceState({}, document.title, applyUrl);
                }
            } catch (_) { /* ignore */ }

            if (newVersionId) {
                this.updateFormBuilderVersionId(newVersionId);
            }

            if (this._fbAiPendingApplyActions) {
                const pending = this._fbAiPendingApplyActions;
                this._fbAiPendingApplyActions = null;
                this._appendFormBuilderApplyActions(pending.contentElement, pending.formBuilderResult);
                this.scrollToBottom();
            }
        } catch (e) {
            console.error('[chatbot] form builder AJAX reload failed, falling back to full reload', e);
            window.location.href = url;
        }
    },

    _syncFormBuilderAttachButton() {
        const attachBtn = this.elements?.widget?.querySelector('.chat-input-attach');
        if (!attachBtn) return;
        const fbMode = !!this._loadFormBuilderAiConfig();
        attachBtn.hidden = !fbMode;
        attachBtn.style.display = fbMode ? 'flex' : 'none';
        if (fbMode) {
            attachBtn.title = 'Attach questionnaire files or images (PDF, Word, PNG — paste multiple screenshots)';
        }
    },

    _syncFormBuilderChatInput() {
        if (!this._loadFormBuilderAiConfig() || !this.elements?.input) return;
        const isCreate = !this._fbAiConfig.templateId;
        this.elements.input.placeholder = isCreate
            ? 'Describe what you want, or paste screenshots of a form…'
            : 'Describe the changes you want, or paste screenshots…';
        this._syncFormBuilderAttachButton();
    },

    _hasFormBuilderAttachments() {
        return Array.isArray(this._fbAiAttachments) && this._fbAiAttachments.length > 0;
    },

    _nextFormBuilderAttachmentId() {
        this._fbAiAttachmentSeq = (this._fbAiAttachmentSeq || 0) + 1;
        return `fb-att-${Date.now()}-${this._fbAiAttachmentSeq}`;
    },

    _formBuilderAttachmentNames() {
        return new Set((this._fbAiAttachments || []).map((a) => a.filename));
    },

    _ensureFormBuilderAttachmentUi() {
        if (this._fbAiAttachmentUiReady) return;
        const container = this.elements?.widget?.querySelector('.chat-input-container');
        if (!container) return;

        let panel = document.getElementById('fb-ai-chat-attachments');
        if (!panel) {
            panel = document.createElement('div');
            panel.id = 'fb-ai-chat-attachments';
            panel.className = 'fb-ai-chat-attachments';
            panel.hidden = true;

            const header = document.createElement('div');
            header.className = 'fb-ai-chat-attachments-header';

            const label = document.createElement('span');
            label.className = 'fb-ai-chat-attachments-label';
            label.textContent = 'Attachments';

            const clearBtn = document.createElement('button');
            clearBtn.type = 'button';
            clearBtn.id = 'fb-ai-chat-attachments-clear';
            clearBtn.className = 'fb-ai-chat-attachments-clear';
            clearBtn.textContent = 'Clear all';

            header.append(label, clearBtn);

            const grid = document.createElement('div');
            grid.id = 'fb-ai-chat-attachment-grid';
            grid.className = 'fb-ai-chat-attachment-grid';

            panel.append(header, grid);
            container.insertBefore(panel, container.firstChild);

            // Remove legacy single-attachment bar if present from an older build.
            document.getElementById('fb-ai-chat-attachment')?.remove();
        }

        if (!document.getElementById('fb-ai-chat-file')) {
            const fileInput = document.createElement('input');
            fileInput.type = 'file';
            fileInput.id = 'fb-ai-chat-file';
            fileInput.hidden = true;
            fileInput.multiple = true;
            fileInput.accept = '.pdf,.docx,.doc,.txt,.md,.png,.jpg,.jpeg,.webp,.gif,image/*';
            container.appendChild(fileInput);
        }

        if (!document.getElementById('fb-ai-image-lightbox')) {
            const lightbox = document.createElement('div');
            lightbox.id = 'fb-ai-image-lightbox';
            lightbox.className = 'fb-ai-image-lightbox';
            lightbox.hidden = true;
            lightbox.setAttribute('aria-modal', 'true');
            lightbox.setAttribute('role', 'dialog');
            lightbox.setAttribute('aria-label', 'Image preview');

            const closeBtn = document.createElement('button');
            closeBtn.type = 'button';
            closeBtn.id = 'fb-ai-lightbox-close';
            closeBtn.className = 'fb-ai-lightbox-close';
            closeBtn.title = 'Close';
            closeBtn.setAttribute('aria-label', 'Close');
            closeBtn.innerHTML = '<i class="fas fa-times" aria-hidden="true"></i>';

            const lightboxImg = document.createElement('img');
            lightboxImg.id = 'fb-ai-lightbox-img';
            lightboxImg.className = 'fb-ai-lightbox-img';
            lightboxImg.alt = '';

            lightbox.append(closeBtn, lightboxImg);
            document.body.appendChild(lightbox);
        }

        this._fbAiAttachmentEls = {
            panel: document.getElementById('fb-ai-chat-attachments'),
            grid: document.getElementById('fb-ai-chat-attachment-grid'),
            clear: document.getElementById('fb-ai-chat-attachments-clear'),
            file: document.getElementById('fb-ai-chat-file'),
            lightbox: document.getElementById('fb-ai-image-lightbox'),
            lightboxImg: document.getElementById('fb-ai-lightbox-img'),
            lightboxClose: document.getElementById('fb-ai-lightbox-close'),
        };
        this._fbAiAttachmentUiReady = true;
        this._initFormBuilderImageLightbox();
    },

    _initFormBuilderImageLightbox() {
        const els = this._fbAiAttachmentEls;
        if (!els?.lightbox || els.lightbox.dataset.fbAiWired === '1') return;
        els.lightbox.dataset.fbAiWired = '1';
        els.lightboxClose?.addEventListener('click', (e) => {
            e.preventDefault();
            this._closeFormBuilderImageLightbox();
        });
        els.lightbox.addEventListener('click', () => this._closeFormBuilderImageLightbox());
        els.lightboxImg?.addEventListener('click', (e) => e.stopPropagation());
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') this._closeFormBuilderImageLightbox();
        });
    },

    _openFormBuilderImageLightbox(src, alt = 'Image preview') {
        const els = this._fbAiAttachmentEls;
        if (!els?.lightbox || !els.lightboxImg || !src) return;
        els.lightboxImg.src = src;
        els.lightboxImg.alt = alt || 'Image preview';
        els.lightbox.hidden = false;
        document.body.classList.add('fb-ai-lightbox-open');
    },

    _closeFormBuilderImageLightbox() {
        const els = this._fbAiAttachmentEls;
        if (!els?.lightbox) return;
        els.lightbox.hidden = true;
        if (els.lightboxImg) els.lightboxImg.removeAttribute('src');
        document.body.classList.remove('fb-ai-lightbox-open');
    },

    _wireFormBuilderExpandableImage(img, src, alt = 'Pasted image') {
        if (!img || !src) return;
        img.src = src;
        img.classList.add('fb-ai-expandable-image');
        if (img.dataset.fbExpandableWired === '1') return;
        img.dataset.fbExpandableWired = '1';
        const labels = this._fbAiLabels();
        img.setAttribute('aria-label', labels.viewImage || 'View full size image');
        const open = () => this._openFormBuilderImageLightbox(src, alt);
        img.addEventListener('click', open);
        img.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                open();
            }
        });
        img.tabIndex = 0;
        img.role = 'button';
    },

    _setupFormBuilderAttachmentHandlers() {
        if (!this._loadFormBuilderAiConfig()) return;
        this._ensureFormBuilderAttachmentUi();
        if (!this._fbAiAttachmentUiReady) return;
        this._syncFormBuilderChatInput();

        if (this._fbAiAttachmentHandlersBound) return;
        this._fbAiAttachmentHandlersBound = true;

        const els = this._fbAiAttachmentEls;
        const attachBtn = this.elements?.widget?.querySelector('.chat-input-attach');
        const widget = this.elements?.widget;

        attachBtn?.addEventListener('click', (e) => {
            if (!this._fbAiConfig || this._fbAiAttachmentBusy) return;
            e.preventDefault();
            els.file?.click();
        });

        els.file?.addEventListener('change', () => {
            const files = Array.from(els.file?.files || []);
            files.forEach((f) => { void this._uploadFormBuilderAttachment(f); });
            els.file.value = '';
        });

        els.clear?.addEventListener('click', () => this._clearFormBuilderAttachment());

        const onPaste = (e) => this._handleFormBuilderPaste(e);
        // Single capture listener on the widget — avoid duplicate handlers on input + widget
        // (bubbling would attach the same screenshot twice).
        widget?.addEventListener('paste', onPaste, true);

        if (widget) {
            widget.addEventListener('dragover', (e) => {
                if (!this._fbAiConfig || this._fbAiAttachmentBusy) return;
                e.preventDefault();
                widget.classList.add('fb-ai-chat-drag-over');
            });
            widget.addEventListener('dragleave', (e) => {
                if (!widget.contains(e.relatedTarget)) {
                    widget.classList.remove('fb-ai-chat-drag-over');
                }
            });
            widget.addEventListener('drop', (e) => {
                widget.classList.remove('fb-ai-chat-drag-over');
                if (!this._fbAiConfig || this._fbAiAttachmentBusy) return;
                e.preventDefault();
                const files = Array.from(e.dataTransfer?.files || []);
                files.forEach((f) => { void this._uploadFormBuilderAttachment(f); });
            });
        }
    },

    _handleFormBuilderPaste(e) {
        if (!this._fbAiConfig || this._fbAiAttachmentBusy) return;
        const imageFiles = fbAiCollectClipboardImageFiles(e.clipboardData);
        if (!imageFiles.length) return;
        e.preventDefault();
        e.stopPropagation();
        const remaining = FB_AI_MAX_IMAGE_ATTACHMENTS - this._countFormBuilderImageAttachments();
        const toAdd = imageFiles.slice(0, Math.max(0, remaining));
        if (toAdd.length < imageFiles.length) {
            this._appendFormBuilderStatusBubble(
                `Only ${FB_AI_MAX_IMAGE_ATTACHMENTS} images can be attached at once.`,
                true
            );
        }
        toAdd.forEach((file) => this._addFormBuilderImageFile(file, { skipLimitCheck: true }));
    },

    _countFormBuilderImageAttachments() {
        return (this._fbAiAttachments || []).filter((a) => a.kind === 'image').length;
    },

    async _uploadFormBuilderAttachment(file) {
        if (this._fbAiAttachmentBusy || !file || !this._fbAiConfig) return;
        if (fbAiIsImageFile(file)) {
            this._addFormBuilderImageFile(fbAiNormalizeImageFilename(file));
        } else {
            await this._uploadFormBuilderDocumentAttachment(file);
        }
    },

    _addFormBuilderImageFile(file, opts = {}) {
        const normalized = fbAiNormalizeImageFilename(file);
        if (!opts.skipLimitCheck && this._countFormBuilderImageAttachments() >= FB_AI_MAX_IMAGE_ATTACHMENTS) {
            this._appendFormBuilderStatusBubble(
                `You can attach up to ${FB_AI_MAX_IMAGE_ATTACHMENTS} images at a time.`,
                true
            );
            return;
        }

        const names = this._formBuilderAttachmentNames();
        const filename = fbAiUniqueFilename(normalized.name, names);
        const attachment = {
            id: this._nextFormBuilderAttachmentId(),
            kind: 'image',
            filename,
            file: filename !== normalized.name
                ? new File([normalized], filename, { type: normalized.type || 'image/png' })
                : normalized,
            previewUrl: URL.createObjectURL(normalized),
            text: null,
            status: 'ready',
        };
        this._fbAiAttachments = [...(this._fbAiAttachments || []), attachment];
        this._renderFormBuilderAttachmentGrid();
        this.elements?.input?.focus();
    },

    async _uploadFormBuilderDocumentAttachment(file) {
        const labels = this._fbAiLabels();
        this._removeFormBuilderAttachmentsWhere((a) => a.kind === 'document');
        const pendingId = this._nextFormBuilderAttachmentId();
        this._fbAiAttachments = [
            ...(this._fbAiAttachments || []),
            {
                id: pendingId,
                kind: 'document',
                filename: file.name,
                text: null,
                status: 'extracting',
            },
        ];
        this._renderFormBuilderAttachmentGrid();
        this._fbAiAttachmentBusy = true;

        try {
            const form = new FormData();
            form.append('file', file);
            const resp = await ((window.getFetch && window.getFetch()) || fetch)(this._fbAiConfig.extractUrl, {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'X-CSRFToken': fbAiCsrfToken() },
                body: form,
            });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok || data.success === false) {
                throw new Error(data?.error || data?.message || 'extract failed');
            }
            const idx = (this._fbAiAttachments || []).findIndex((a) => a.id === pendingId);
            const readyDoc = {
                id: pendingId,
                kind: 'document',
                filename: data.filename || file.name,
                text: String(data.text),
                sections: Array.isArray(data.sections) ? data.sections : [],
                truncated: Boolean(data.truncated),
                status: 'ready',
            };
            if (idx >= 0) {
                const next = [...this._fbAiAttachments];
                next[idx] = readyDoc;
                this._fbAiAttachments = next;
            } else {
                this._fbAiAttachments = [...(this._fbAiAttachments || []), readyDoc];
            }
            this._renderFormBuilderAttachmentGrid();
        } catch (e) {
            console.warn('[chatbot] form builder document extraction failed', e);
            this._appendFormBuilderStatusBubble(
                labels.extractFailed || 'Could not extract text from the document.',
                true
            );
            this._removeFormBuilderAttachment(pendingId);
        } finally {
            this._fbAiAttachmentBusy = false;
        }
    },

    async _extractFormBuilderImageFile(file) {
        const form = new FormData();
        form.append('file', file);
        const extractUrl = this._fbAiConfig.extractImageUrl || this._fbAiConfig.extractUrl;
        const resp = await ((window.getFetch && window.getFetch()) || fetch)(extractUrl, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'X-CSRFToken': fbAiCsrfToken() },
            body: form,
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok || data.success === false) {
            throw new Error(data?.error || data?.message || 'image extract failed');
        }
        return {
            filename: data.filename || file.name,
            text: String(data.text),
            sections: Array.isArray(data.sections) ? data.sections : [],
            truncated: Boolean(data.truncated),
        };
    },

    _removeFormBuilderAttachment(id) {
        const target = (this._fbAiAttachments || []).find((a) => a.id === id);
        if (target?.previewUrl) {
            try { URL.revokeObjectURL(target.previewUrl); } catch (_) { /* ignore */ }
        }
        this._fbAiAttachments = (this._fbAiAttachments || []).filter((a) => a.id !== id);
        this._renderFormBuilderAttachmentGrid();
    },

    _removeFormBuilderAttachmentsWhere(predicate) {
        const kept = [];
        for (const attachment of this._fbAiAttachments || []) {
            if (predicate(attachment)) {
                if (attachment.previewUrl) {
                    try { URL.revokeObjectURL(attachment.previewUrl); } catch (_) { /* ignore */ }
                }
            } else {
                kept.push(attachment);
            }
        }
        this._fbAiAttachments = kept;
    },

    _renderFormBuilderAttachmentGrid() {
        const els = this._fbAiAttachmentEls;
        const attachments = this._fbAiAttachments || [];
        if (!els?.grid || !els.panel) return;

        els.grid.replaceChildren();
        attachments.forEach((attachment) => {
            els.grid.appendChild(this._createFormBuilderAttachmentCard(attachment));
        });

        const count = attachments.length;
        els.panel.hidden = count === 0;
        const label = els.panel.querySelector('.fb-ai-chat-attachments-label');
        if (label) {
            label.textContent = count === 1 ? '1 attachment' : `${count} attachments`;
        }
        if (els.clear) els.clear.hidden = count === 0;
    },

    _createFormBuilderAttachmentCard(attachment) {
        const labels = this._fbAiLabels();
        const card = document.createElement('div');
        card.className = 'fb-ai-attach-card';
        card.dataset.id = attachment.id;
        if (attachment.status === 'extracting') card.classList.add('fb-ai-attach-card-loading');

        const thumb = document.createElement('div');
        thumb.className = 'fb-ai-attach-card-thumb';

        if (attachment.kind === 'image' && attachment.previewUrl) {
            const img = document.createElement('img');
            img.className = 'fb-ai-attach-card-img fb-ai-expandable-image';
            img.alt = attachment.filename || 'Attached image';
            this._wireFormBuilderExpandableImage(img, attachment.previewUrl, attachment.filename);
            thumb.appendChild(img);
        } else {
            const icon = document.createElement('i');
            icon.className = attachment.kind === 'document'
                ? 'fas fa-file-lines fb-ai-attach-card-doc-icon'
                : 'fas fa-image fb-ai-attach-card-doc-icon';
            icon.setAttribute('aria-hidden', 'true');
            thumb.appendChild(icon);
        }

        const meta = document.createElement('div');
        meta.className = 'fb-ai-attach-card-meta';

        const name = document.createElement('span');
        name.className = 'fb-ai-attach-card-name';
        name.textContent = attachment.filename || 'Attachment';
        name.title = attachment.filename || '';

        const kind = document.createElement('span');
        kind.className = 'fb-ai-attach-card-kind';
        kind.textContent = attachment.kind === 'image'
            ? (labels.attachedImage || 'Image').replace(/:$/, '')
            : (labels.attached || 'Document').replace(/:$/, '');

        meta.append(name, kind);

        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'fb-ai-attach-card-remove';
        removeBtn.title = 'Remove';
        removeBtn.setAttribute('aria-label', 'Remove attachment');
        removeBtn.innerHTML = '<i class="fas fa-times" aria-hidden="true"></i>';
        removeBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            this._removeFormBuilderAttachment(attachment.id);
        });

        if (attachment.status === 'extracting') {
            const loading = document.createElement('div');
            loading.className = 'fb-ai-attach-card-overlay';
            loading.innerHTML = '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i>';
            card.append(thumb, meta, removeBtn, loading);
        } else {
            card.append(thumb, meta, removeBtn);
        }

        return card;
    },

    _clearFormBuilderAttachment(opts = {}) {
        (this._fbAiAttachments || []).forEach((attachment) => {
            if (attachment.previewUrl) {
                try { URL.revokeObjectURL(attachment.previewUrl); } catch (_) { /* ignore */ }
            }
        });
        this._fbAiAttachments = [];
        if (!opts.keepPanel) {
            this._renderFormBuilderAttachmentGrid();
        } else if (this._fbAiAttachmentEls?.grid) {
            this._fbAiAttachmentEls.grid.replaceChildren();
            if (this._fbAiAttachmentEls.panel) this._fbAiAttachmentEls.panel.hidden = true;
        }
    },

    _appendAttachmentBlockToMessage(messageText, attachment, budget) {
        if (!attachment?.text) return messageText;
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
        const remaining = Math.max(200, budget - messageText.length - header.length - 50);
        let text = attachment.text;
        if (text.length > remaining) {
            text = `${text.slice(0, remaining)}\n[…document truncated…]`;
        }
        if (attachment.truncated) {
            text += '\n[Note: the extracted document was truncated server-side.]';
        }
        return `${messageText}${header}${text}`;
    },

    _buildFormBuilderMessageText(userText, attachments) {
        const list = Array.isArray(attachments) ? attachments : (attachments ? [attachments] : []);
        if (!list.length) return userText;
        const maxChars = Number(this._fbAiConfig?.maxMessageChars || 16000);
        let result = userText || '';
        for (const attachment of list) {
            result = this._appendAttachmentBlockToMessage(result, attachment, maxChars);
        }
        if (result.length > maxChars) {
            result = `${result.slice(0, maxChars)}\n[…message truncated…]`;
        }
        return result;
    },

    _buildFormBuilderDisplayedUserMessage(raw, attachments) {
        const parts = [];
        if (raw) parts.push(raw);
        const list = Array.isArray(attachments) ? attachments : (attachments ? [attachments] : []);
        list.forEach((attachment) => {
            const icon = attachment.kind === 'image' ? '🖼' : '📎';
            parts.push(`${icon} ${attachment.filename}`);
        });
        return parts.join('\n');
    },

    _buildFormBuilderPreviewItems(attachments, detachUrls = true) {
        return (attachments || []).map((attachment) => {
            const item = {
                kind: attachment.kind,
                filename: attachment.filename,
                url: attachment.previewUrl || null,
                alt: attachment.filename || 'Attached image',
            };
            if (detachUrls && attachment.previewUrl) {
                attachment.previewUrl = null;
            }
            return item;
        }).filter((item) => item.kind === 'image' ? !!item.url : true);
    },

    _renderFormBuilderUserAttachmentGrid(container, previewItems) {
        if (!container || !previewItems?.length) return;
        const grid = document.createElement('div');
        grid.className = 'fb-ai-msg-attachment-grid';
        previewItems.forEach((item) => {
            const card = document.createElement('div');
            card.className = 'fb-ai-msg-attach-card';
            if (item.kind === 'image' && item.url) {
                const img = document.createElement('img');
                img.className = 'fb-ai-msg-attach-card-img fb-ai-expandable-image';
                img.alt = item.alt || item.filename || 'Attached image';
                this._wireFormBuilderExpandableImage(img, item.url, item.alt || item.filename);
                card.appendChild(img);
                if (item.filename) {
                    const cap = document.createElement('span');
                    cap.className = 'fb-ai-msg-attach-card-caption';
                    cap.textContent = item.filename;
                    card.appendChild(cap);
                }
            } else {
                card.classList.add('fb-ai-msg-attach-card-doc');
                const icon = document.createElement('i');
                icon.className = 'fas fa-file-lines';
                icon.setAttribute('aria-hidden', 'true');
                const cap = document.createElement('span');
                cap.className = 'fb-ai-msg-attach-card-caption';
                cap.textContent = item.filename || 'Document';
                card.append(icon, cap);
            }
            grid.appendChild(card);
        });
        container.appendChild(grid);
    },

    async _prepareFormBuilderOutgoingMessage(rawInput) {
        if (!this._hasFormBuilderAttachments()) {
            return { ok: true, messageText: rawInput, displayed: rawInput, previewItems: [] };
        }

        const labels = this._fbAiLabels();
        const attachments = (this._fbAiAttachments || []).map((a) => ({ ...a }));
        const imagesNeedingExtract = attachments.filter(
            (a) => a.kind === 'image' && a.file && !a.text
        );

        if (imagesNeedingExtract.length) {
            this._fbAiAttachmentBusy = true;
            try {
                for (let i = 0; i < imagesNeedingExtract.length; i += 1) {
                    const attachment = imagesNeedingExtract[i];
                    const idx = attachments.findIndex((a) => a.id === attachment.id);
                    if (idx >= 0) {
                        attachments[idx] = { ...attachments[idx], status: 'extracting' };
                        this._fbAiAttachments = attachments.map((a) => ({ ...a }));
                        this._renderFormBuilderAttachmentGrid();
                    }
                    try {
                        const extracted = await this._extractFormBuilderImageFile(attachment.file);
                        if (idx >= 0) {
                            attachments[idx] = {
                                ...attachments[idx],
                                ...extracted,
                                status: 'ready',
                            };
                            this._fbAiAttachments = attachments.map((a) => ({ ...a }));
                            this._renderFormBuilderAttachmentGrid();
                        }
                    } catch (e) {
                        console.warn('[chatbot] form builder image extraction failed', e);
                        this._appendFormBuilderStatusBubble(
                            labels.extractImageFailed || 'Could not read one of the pasted images.',
                            true
                        );
                        return { ok: false };
                    }
                }
            } finally {
                this._fbAiAttachmentBusy = false;
            }
        }

        const imageCount = attachments.filter((a) => a.kind === 'image').length;
        const hasDocument = attachments.some((a) => a.kind === 'document');
        let defaultPrompt = 'Build a form template from the attached materials.';
        if (hasDocument && imageCount > 1) {
            defaultPrompt = `Build a form template from the attached questionnaire and ${imageCount} pasted images.`;
        } else if (hasDocument && imageCount === 1) {
            defaultPrompt = 'Build a form template from the attached questionnaire and pasted image.';
        } else if (hasDocument) {
            defaultPrompt = 'Build a form template from this attached questionnaire.';
        } else if (imageCount === 1) {
            defaultPrompt = 'Build a form template from this pasted image.';
        } else if (imageCount > 1) {
            defaultPrompt = `Build a form template from these ${imageCount} pasted form images.`;
        }

        const messageText = this._buildFormBuilderMessageText(rawInput || defaultPrompt, attachments);
        const displayed = this._buildFormBuilderDisplayedUserMessage(rawInput, attachments);
        const previewItems = this._buildFormBuilderPreviewItems(attachments, true);
        return { ok: true, messageText, displayed, previewItems };
    },

};
