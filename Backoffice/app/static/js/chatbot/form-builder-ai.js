/**
 * Chatbot FormBuilderAi module
 * @module chatbot/form-builder-ai
 */

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
        });
    },

    _syncFormBuilderAiPanelFab(forceHidden) {
        if (!this.elements.fab || this._isImmersive()) return;
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

    _appendFormBuilderOpenTemplateButton(label, url) {
        if (!this.elements.messages || !url) return;
        const existing = this.elements.messages.querySelector('.fb-ai-open-template-action');
        if (existing) existing.remove();
        const wrap = document.createElement('div');
        wrap.className = 'fb-ai-open-template-action chat-message bot';
        const inner = document.createElement('div');
        inner.className = 'flex items-start gap-2';
        const content = document.createElement('div');
        content.className = 'chat-message-content';
        const btn = document.createElement('a');
        btn.href = url;
        btn.className = 'btn btn-primary btn-sm inline-flex items-center mt-2';
        btn.textContent = label || 'Open the template in the form builder';
        content.appendChild(btn);
        inner.appendChild(content);
        wrap.appendChild(inner);
        this.elements.messages.appendChild(wrap);
        this.scrollToBottom();
    },

    _handleFormBuilderResult(formBuilderResult, answerHtml = '', contentElement = null) {
        if (!this._fbAiConfig || !formBuilderResult) return;

        const labels = this._fbAiLabels();
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
            this._appendFormBuilderOpenTemplateButton(
                labels.openTemplate || 'Open the template in the form builder',
                link.url
            );
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
    }

};
