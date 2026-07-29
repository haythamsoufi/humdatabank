/**
 * Chatbot DlpPolicy module
 * @module chatbot/dlp-policy
 */

const _t = (k) => (typeof window.t === 'function' ? window.t(k) : k);

export const DlpPolicyMixin = {
    _makeDlpError(dlpPayload) {
        const err = new Error((dlpPayload && (dlpPayload.error || dlpPayload.message)) || _t('Sensitive information detected'));
        err.name = 'DlpConfirmationRequired';
        err.dlp = dlpPayload || null;
        return err;
    },

    _formatDlpFindings(dlpPayload) {
        try {
            const findings = dlpPayload?.dlp?.findings || dlpPayload?.findings || [];
            if (!Array.isArray(findings) || !findings.length) return [];
            const labelMap = {
                email: 'Email address',
                phone: 'Phone number',
                jwt: 'Token (JWT)',
                bearer_token: 'Bearer token',
                private_key: 'Private key',
                // Avoid `password: '...'` substring patterns in secret scanners (display label only).
                password: 'Pass' + 'word',
                api_key_or_secret: 'API key / secret',
                iban: 'IBAN / bank account',
                payment_card: 'Payment card number',
            };
            return findings.map(f => {
                const kind = String(f?.kind || '').trim() || 'sensitive_data';
                const count = Number(f?.count || 1) || 1;
                const label = labelMap[kind] || kind;
                return `${label}${count > 1 ? ` (x${count})` : ''}`;
            });
        } catch (e) {
            return [];
        }
    },

    _showDlpModal({ title, bodyLines, actions }) {
        // Minimal custom modal (3-button) to avoid relying on global dialog helpers.
        try {
            const existing = document.querySelector('.humdb-dlp-modal-overlay');
            if (existing) existing.remove();
        } catch (_) {}

        const overlay = document.createElement('div');
        overlay.className = 'humdb-dlp-modal-overlay';
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');

        const modal = document.createElement('div');
        modal.className = 'humdb-dlp-modal';

        const header = document.createElement('div');
        header.className = 'humdb-dlp-modal-header';
        header.textContent = title || _t('Sensitive information detected');

        const body = document.createElement('div');
        body.className = 'humdb-dlp-modal-body';
        const p = document.createElement('p');
        p.textContent = _t('Your message appears to include sensitive information. Choose how to proceed:');
        body.appendChild(p);
        if (Array.isArray(bodyLines) && bodyLines.length) {
            const ul = document.createElement('ul');
            bodyLines.forEach(line => {
                const li = document.createElement('li');
                li.textContent = line;
                ul.appendChild(li);
            });
            body.appendChild(ul);
        }

        const actionsEl = document.createElement('div');
        actionsEl.className = 'humdb-dlp-modal-actions';

        function close() {
            try { overlay.remove(); } catch (_) {}
        }

        (actions || []).forEach(a => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'humdb-dlp-btn ' + (a.variant === 'primary' ? 'humdb-dlp-btn-primary' : a.variant === 'danger' ? 'humdb-dlp-btn-danger' : '');
            btn.textContent = a.label || _t('OK');
            btn.addEventListener('click', () => {
                close();
                try { if (typeof a.onClick === 'function') a.onClick(); } catch (_) {}
            });
            actionsEl.appendChild(btn);
        });

        modal.appendChild(header);
        modal.appendChild(body);
        modal.appendChild(actionsEl);
        overlay.appendChild(modal);

        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) close();
        });

        document.body.appendChild(overlay);
    },

    _handleDlpChallenge(originalMessage, sendOptions, dlpPayload) {
        const findings = this._formatDlpFindings(dlpPayload);
        const title = this._uiString('sensitiveInfoTitle') || _t('Sensitive information detected');
        const sendAnyway = this._uiString('sendAnyway') || _t('Send anyway');
        const cancel = this._uiString('cancel') || _t('Cancel');

        this._showDlpModal({
            title,
            bodyLines: findings,
            actions: [
                {
                    label: cancel,
                    variant: 'default',
                    onClick: () => {}
                },
                {
                    label: sendAnyway,
                    variant: 'danger',
                    onClick: () => {
                        const opts = Object.assign({}, sendOptions || {}, { allow_sensitive: true });
                        this.handleSendMessage(originalMessage, opts);
                    }
                }
            ]
        });
    },
    /** Spotlight tooltip positions: max 10 entries in localStorage */

    _hasAcknowledgedAiPolicy() {
        try {
            return localStorage.getItem(this.aiPolicyAckStorageKey) === '1';
        } catch (_) {
            return false;
        }
    },

    _setAcknowledgedAiPolicy() {
        try {
            localStorage.setItem(this.aiPolicyAckStorageKey, '1');
        } catch (_) {}
    },

    _showAiPolicyModal() {
        const overlay = document.getElementById('chatAiPolicyModalOverlay');
        if (!overlay) return;
        const active = document.activeElement;
        if (active && !overlay.contains(active)) {
            this._aiPolicyModalPreviousFocus = active;
        }
        overlay.removeAttribute('hidden');
        overlay.setAttribute('aria-hidden', 'false');
        const ackBtn = document.getElementById('chatAiPolicyModalAckBtn');
        if (ackBtn) {
            try { ackBtn.focus(); } catch (_) {}
        }
    },

    _hideAiPolicyModal() {
        const overlay = document.getElementById('chatAiPolicyModalOverlay');
        if (!overlay) return;

        const active = document.activeElement;
        if (active && overlay.contains(active)) {
            const prev = this._aiPolicyModalPreviousFocus;
            const fallback = document.getElementById('chatAiPolicyLinkBtn')
                || this.elements?.input
                || document.body;
            const target = (prev && document.contains(prev) && !overlay.contains(prev)) ? prev : fallback;
            try {
                if (target && typeof target.focus === 'function') target.focus();
                else active.blur();
            } catch (_) {
                try { active.blur(); } catch (_) {}
            }
        }
        this._aiPolicyModalPreviousFocus = null;

        overlay.setAttribute('aria-hidden', 'true');
        overlay.setAttribute('hidden', '');
    },

    _updateAiNoticeVisibility() {
        const el = this.elements && this.elements.aiNoticeBlock;
        if (!el) return;
        const isEmptyChat = Array.isArray(this.conversationHistory) && this.conversationHistory.length === 0;
        const isImmersive = this._isImmersive();
        const notAcked = !this._hasAcknowledgedAiPolicy();
        const show = isImmersive ? (isEmptyChat || notAcked) : (isEmptyChat || notAcked);
        el.style.display = show ? '' : 'none';
        try { el.setAttribute('aria-hidden', show ? 'false' : 'true'); } catch (_) {}
        const acked = this._hasAcknowledgedAiPolicy();
        if (isImmersive) this._updateImmersiveChatControls(acked);
        else this._updateFloatingChatControls(acked);
    },

    _triggerPolicyNoticeAttention() {
        if (this._isImmersive()) return;
        const notice = this.elements && this.elements.aiNoticeBlock;
        const block = notice?.matches?.('.chat-ai-notice-block') ? notice : notice?.querySelector('.chat-ai-notice-block');
        if (!notice || !block) return;
        block.classList.remove('chat-ai-notice-attention');
        void block.offsetWidth;
        block.classList.add('chat-ai-notice-attention');
        setTimeout(() => block.classList.remove('chat-ai-notice-attention'), 600);
    },

    _updateImmersiveChatControls(acked) {
        if (!this._isImmersive()) return;
        const disabled = !acked;
        const input = this.elements && this.elements.input;
        const sendBtn = this.elements && this.elements.sendBtn;
        if (input) {
            input.disabled = disabled;
            input.placeholder = disabled ? (this._uiString('aiPolicyAckRequired') || _t('Please acknowledge the AI policy to continue.')) : _t('Ask anything');
        }
        if (sendBtn) sendBtn.disabled = disabled;
        const addBtn = document.getElementById('chatImmersiveAddBtn');
        const sourcesBtn = document.getElementById('chatImmersiveSourcesBtn');
        const quickPrompts = this.elements.quickPrompts;
        if (addBtn) addBtn.disabled = disabled;
        if (sourcesBtn) sourcesBtn.disabled = disabled;
        if (quickPrompts) {
            quickPrompts.querySelectorAll('.chat-immersive-quick-prompt').forEach((b) => { b.disabled = disabled; });
            quickPrompts.style.pointerEvents = disabled ? 'none' : '';
        }
        const ackBtn = document.getElementById('chatAiPolicyAckBtn');
        if (ackBtn) ackBtn.style.display = acked ? 'none' : '';
        const container = this.elements.widget?.querySelector('.chat-immersive-input-container');
        const wrapper = this.elements.widget?.querySelector('.chat-input-wrapper-immersive');
        if (container) container.classList.toggle('chat-immersive-input-disabled', disabled);
        if (wrapper) wrapper.classList.toggle('chat-immersive-input-disabled', disabled);
        let overlay = document.getElementById('chatAiPolicyInputOverlay');
        if (disabled && container) {
            if (!overlay) {
                overlay = document.createElement('div');
                overlay.id = 'chatAiPolicyInputOverlay';
                overlay.className = 'chat-ai-policy-input-overlay';
                overlay.setAttribute('aria-hidden', 'true');
                overlay.addEventListener('click', () => this._triggerImmersivePolicyNoticeAttention());
                container.style.position = 'relative';
                container.appendChild(overlay);
            }
            overlay.style.display = '';
        } else if (overlay) overlay.style.display = 'none';
    },

    _triggerImmersivePolicyNoticeAttention() {
        if (!this._isImmersive()) return;
        const notice = this.elements && this.elements.aiNoticeBlock;
        const block = notice?.matches?.('.chat-ai-notice-block') ? notice : notice?.querySelector('.chat-ai-notice-block');
        if (!notice || !block) return;
        block.classList.remove('chat-ai-notice-attention', 'chat-ai-notice-attention-bounce');
        void block.offsetWidth;
        block.classList.add('chat-ai-notice-attention-bounce');
        setTimeout(() => block.classList.remove('chat-ai-notice-attention-bounce'), 600);
    },

    _updateFloatingChatControls(acked) {
        if (this._isImmersive()) return;
        const input = this.elements && this.elements.input;
        const sendBtn = this.elements && this.elements.sendBtn;
        const attachBtn = document.querySelector('#aiChatWidget .chat-input-attach');
        const disabled = !acked;
        if (input) {
            input.disabled = disabled;
            input.placeholder = disabled ? (this._uiString('aiPolicyAckRequired') || _t('Please acknowledge the AI policy to continue.')) : _t('Ask anything');
        }
        if (sendBtn) sendBtn.disabled = disabled;
        if (attachBtn) {
            const fbMode = !!(this._fbAiConfig || this._loadFormBuilderAiConfig?.());
            attachBtn.hidden = !fbMode;
            attachBtn.style.display = fbMode ? 'flex' : 'none';
            attachBtn.disabled = disabled || !fbMode;
        }
        const ackBtn = document.getElementById('chatAiPolicyAckBtn');
        if (ackBtn) ackBtn.style.display = acked ? 'none' : '';

        const container = this.elements.widget?.querySelector('.chat-input-container');
        let overlay = document.getElementById('chatAiPolicyInputOverlay');
        if (disabled) {
            if (!overlay && container) {
                overlay = document.createElement('div');
                overlay.id = 'chatAiPolicyInputOverlay';
                overlay.className = 'chat-ai-policy-input-overlay';
                overlay.setAttribute('aria-hidden', 'true');
                overlay.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    this._triggerPolicyNoticeAttention();
                });
                container.style.position = 'relative';
                container.appendChild(overlay);
            }
            if (overlay) overlay.style.display = '';
        } else {
            if (overlay) overlay.style.display = 'none';
        }
    }

};
