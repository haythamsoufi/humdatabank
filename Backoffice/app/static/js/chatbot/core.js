/**
 * HumDatabankChatbot core class
 * @module chatbot/core
 */

import { StateMixin } from './state.js';
import { ChatSourcesMixin } from './chat-sources.js';
import { DlpPolicyMixin } from './dlp-policy.js';
import { HtmlPipelineMixin } from './html-pipeline.js';
import { SpotlightToursMixin } from './spotlight-tours.js';
import { FormBuilderAiMixin } from './form-builder-ai.js';
import { WidgetUiMixin } from './widget-ui.js';
import { TransportMixin } from './transport.js';
import { ConversationsMixin } from './conversations.js';

export class HumDatabankChatbot {
    constructor() {
        this.apiEndpoint = '/api/ai/v2/chat';
        this.isInitialized = false;
        this.conversationHistory = [];
        this.isTyping = false;
        this.isExpanded = true; /* Chat is always maximized; no minimize/expand */
        this.storageKey = 'humdb_chatbot_conversation';
        this.immersiveStorageKey = 'humdb_chatbot_immersive_data';
        this.immersiveActiveIdKey = 'humdb_chatbot_immersive_active_id';
        this.sourcesStorageKey = 'humdb_chatbot_sources';
        this.floatingConversationIdKey = 'humdb_chatbot_floating_conversation_id';
        this.expandStorageKey = 'humdb_chatbot_expanded';
        this.aiPolicyAckStorageKey = 'humdb_chatbot_ai_policy_acknowledged';
        this.activeConversationId = null;
        this.preferredLanguage = this._normalizeLanguage(localStorage.getItem('chatbot_language'));
        this._currentAbort = null;
        // In immersive mode we allow multiple conversations to run in parallel.
        // We only "render live" for the currently active conversation; background
        // runs are tracked via conversation.meta.inflight (server-side) + list polling.
        this._inflightByConversationKey = new Map(); // key: conversation_id or draft key -> { detached, detachRef, ... }
        this._detachedInflightStepsByKey = new Map(); // key: conversation_id -> { steps, request_id } when user switched away mid-stream
        this._serverInflightByConversationId = new Map(); // conversation_id -> inflight summary (from /conversations)
        this._serverInflightIgnoreUntilByConversationId = new Map(); // id -> timestamp; do not re-add from /conversations until after this (stale list fix)
        this._immersiveDraftKey = null; // stable key for a "new chat" tab before conversation_id exists
        this._chatSourcesControlInitialized = false;
        this._inflightPollTimer = null;
        this._inflightPollConversationId = null;
        this._inflightPollRequestId = null;
        this._inflightLastRendered = null;
        this._pendingStructuredPayload = null;
        /** Non-stream HTTP responses may include map + table; dispatch each in addMessageToDOM. */
        this._pendingStructuredRawPieces = null;
        this._lastPreparingQueryDetail = null; // refined query for "Preparing query…" step

        // Debug mode - managed by centralized debug.js
        this.apiAvailable = true; // Track API availability status

        // Load messages from external file (fallback to inline if not available)
        this.messages = window.ChatbotMessages || this._getDefaultMessages();

        // Debug utilities from centralized debug.js (available after page load)
        this.debug = null; // Will be set to window.debug once available

        this.init();

        // Register chatbot tours with InteractiveTour system
        this._registerChatbotTours();
    }


    _getDefaultMessages() {
        // Fallback messages if chatbot/messages.js is not loaded
        return {
            greetings: {
                get en() {
                    const orgName = window.ORG_NAME || 'Humanitarian Databank';
                    const chatbotName = window.CHATBOT_NAME;
                    if (chatbotName && String(chatbotName).trim()) {
                        return `Hello! I'm ${String(chatbotName).trim()}, your ${orgName} assistant. How can I help you today?`;
                    }
                    return `Hello! I'm your ${orgName} assistant. How can I help you today?`;
                }
            },
            errors: {
                connectionError: {
                    en: "I'm sorry, but I'm having trouble connecting right now. Please try again."
                }
            },
            knowledgeBase: {},
            pageExplanations: {},
            thankYouResponses: { en: "You're welcome!" },
            defaultResponse: { en: "How can I help you?" }
        };
    }


    _normalizeLanguage(language) {
        const configured = Array.isArray(window.SUPPORTED_LANGUAGES) ? window.SUPPORTED_LANGUAGES : ['en'];
        const supported = new Set(
            configured
                .filter(l => typeof l === 'string' && l.trim())
                .map(l => l.trim().toLowerCase().split('_')[0].split('-', 1)[0])
        );
        if (!language || typeof language !== 'string') return 'en';
        const lang = language.trim().toLowerCase().split('_')[0].split('-', 1)[0];
        return supported.has(lang) ? lang : 'en';
    }


    _setPreferredLanguage(language) {
        this.preferredLanguage = this._normalizeLanguage(language);
        localStorage.setItem('chatbot_language', this.preferredLanguage);
    }


    // Private mode removed: all requests may use external providers unless blocked by DLP.

    /** Log only when window.CHATBOT_DEBUG is true (set by debug.enableChatbot()) */

    _log(...args) {
        if (!window.CHATBOT_DEBUG) return;
        console.log('[Chatbot]', ...args);
    }


    /** Log when sidebar "Running" debug is enabled (debug why side menu keeps showing Running after response). */

    _sidebarRunningLog(...args) {
        if (!window.CHATBOT_DEBUG && !window.CHAT_SIDEBAR_RUNNING_DEBUG) return;
        console.log('[Chatbot sidebar running]', ...args);
    }


    /** Table payload diagnostics: logs when table/structured payload code runs. Gated by debug.js module 'chatbot'. */

    _tableDebugLog(...args) {
        try {
            if (window.debug && window.debug.getConfig && window.debug.getConfig().modules.chatbot) {
                console.log('[Chatbot tables]', ...args);
            }
        } catch (e) { /* debug not loaded or getConfig failed */ }
    }


    _warn(...args) {
        if (!window.CHATBOT_DEBUG) return;
        console.warn('[Chatbot]', ...args);
    }


    /** Resolve UI string: prefer server-side translations (CHAT_UI_STRINGS), then messages.ui */

    _uiString(key) {
        // Server-side translations injected by the template (best: uses Flask-Babel _())
        const serverStrings = window.CHAT_UI_STRINGS;
        if (serverStrings && serverStrings[key] != null) return serverStrings[key];
        // Fallback to ChatbotMessages.ui (language-aware, then English)
        const ui = this.messages.ui;
        if (!ui) return null;
        const lang = this.preferredLanguage || 'en';
        return (ui[lang] && ui[lang][key]) || (ui.en && ui.en[key]) || null;
    }


    init() {
        // Wait for DOM to be ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this._initialize());
        } else {
            this._initialize();
        }
    }


    _initialize() {
        // Connect to centralized debug system
        if (window.debug) {
            this.debug = window.debug;
        }

        this._fbAiConfig = null;
        this._fbAiConversationId = null;
        this._fbAiLastEditUndoRedo = null;
        this._fbAiPendingApplyActions = null;
        this._fbAiAttachments = [];
        this._fbAiAttachmentBusy = false;
        this._ensureFormBuilderAiIntegration();

        this.initializeElements();
        // Add class-based fallbacks so the UI works even where :has() is unsupported.
        try {
            document.querySelectorAll('.chat-input-container').forEach((el) => {
                if (!el.querySelector('.chat-input-pill')) {
                    el.classList.add('chat-input-container-no-pill');
                }
            });
        } catch (_) { /* ignore */ }
        // Run any pending "spotlight" navigation from URL hash, e.g. /admin/users#chatbot-spotlight=add-new-user
        this.runSpotlightFromHash();
    }


    _isImmersive() {
        return document.body && document.body.classList.contains('chat-immersive');
    }


    _isMobileFloatingLayout() {
        if (this._isImmersive()) return false;
        try {
            return typeof window.matchMedia === 'function' && window.matchMedia('(max-width: 768px)').matches;
        } catch (_) {
            return false;
        }
    }


    initializeElements() {
        this.elements = {
            fab: document.getElementById('aiChatbotFAB'),
            widget: document.getElementById('aiChatWidget'),
            closeBtn: document.getElementById('chatCloseBtn'),
            expandBtn: document.getElementById('chatExpandBtn'),
            clearBtn: document.getElementById('chatClearBtn'),
            newChatBtn: document.getElementById('chatNewChatBtn'),
            immersiveBtn: document.getElementById('chatImmersiveBtn'),
            sidebar: document.getElementById('chatFloatingSidebar'),
            sidebarToggle: document.getElementById('chatSidebarToggleBtn'),
            floatingChatList: document.getElementById('chatFloatingChatList'),
            floatingNewChat: document.getElementById('chatFloatingNewChat'),
            chatTitle: document.getElementById('chatTitle'),
            chatFloatingTitleLabel: document.getElementById('chatFloatingTitleLabel'),
            messages: document.getElementById('chatMessages'),
            input: document.getElementById('chatInput'),
            sendBtn: document.getElementById('chatSendBtn'),
            quickPrompts: document.getElementById('chatImmersiveQuickPrompts'),
            welcomeCenter: document.getElementById('chatImmersiveWelcomeCenter'),
            aiNoticeBlock: document.getElementById('chatAiNoticeBlock'),
            chatSourcesBtn: document.getElementById('chatImmersiveSourcesBtn'),
            chatSourcesMenu: document.getElementById('chatImmersiveSourcesMenu'),
            chatSrcHistorical: document.getElementById('chat-ai-src-historical'),
            chatSrcSystem: document.getElementById('chat-ai-src-system'),
            chatSrcUpr: document.getElementById('chat-ai-src-upr'),
        };

        this._floatingDefaultTitleText = '';
        try {
            if (this.elements.chatFloatingTitleLabel) {
                this._floatingDefaultTitleText = String(this.elements.chatFloatingTitleLabel.textContent || '').trim();
            } else if (typeof window !== 'undefined' && window.CHATBOT_NAME) {
                this._floatingDefaultTitleText = String(window.CHATBOT_NAME || '').trim();
            }
        } catch (_) { /* ignore */ }
        if (!this._floatingDefaultTitleText) {
            this._floatingDefaultTitleText = 'Assistant';
        }

        const canInit = this.elements.widget && (this.elements.fab || this._isImmersive());
        if (canInit) {
            this._initFloatingDrag();
            this._initFabDrag();
            this._initFabOverlapAvoidance();
            this.setupEventListeners();
            this.loadConversationHistory();
            this.loadExpandedState();
            this._updateAiNoticeVisibility();
            if (this._isImmersive() && !this._hasAcknowledgedAiPolicy()) {
                this._showAiPolicyModal();
            }
            this._setupChatSourcesControl();
            if (this._isImmersive()) {
                this.elements.widget.classList.add('chat-open');
                this.setExpanded(true);
                if (this.conversationHistory.length === 0) {
                    this.showWelcomeMessage();
                }
                this.elements.input.focus();
                window.addEventListener('popstate', this._handleImmersivePopstate.bind(this));
                this._setupVisibilityChangeHandler();
            } else {
                this._updateImmersiveLinkHref();
                if (this._getFloatingConversationId()) {
                    void this._refreshFloatingHeaderTitleFromServer();
                }
            }
            this.isInitialized = true;
        }
    }


    setupEventListeners() {
        if (!this.elements.input || !this.elements.sendBtn || !this.elements.messages) {
            return;
        }
        const isImmersive = this._isImmersive();

        // Toggle chat widget (floating FAB only)
        if (this.elements.fab) {
            this.elements.fab.addEventListener('click', () => this.toggleChat());
            this._syncFormBuilderAiPanelFab();
            window.addEventListener('fb-ai-panel-visibility', (e) => {
                this._syncFormBuilderAiPanelFab(!!(e.detail && e.detail.open));
            });
        }

        // Close / Back: in widget close; in immersive closeBtn is a link, no handler
        if (this.elements.closeBtn && !isImmersive) {
            this.elements.closeBtn.addEventListener('click', () => this.toggleChat(false));
        }

        // Immersive view: open full-page chat in a new tab (same conversation if one is active)
        if (this.elements.immersiveBtn && !isImmersive) {
            this.elements.immersiveBtn.addEventListener('click', (e) => {
                let url = this.elements.widget.getAttribute('data-immersive-url') || '/chat';
                const conversationId = this._getFloatingConversationId();
                if (conversationId) {
                    url = url.replace(/\/+$/, '') + '/' + encodeURIComponent(conversationId);
                }
                e.preventDefault();
                window.open(url, '_blank', 'noopener,noreferrer');
            });
        }

        // Conversations sidebar toggle (floating only)
        if (this.elements.sidebarToggle && !isImmersive) {
            this.elements.sidebarToggle.addEventListener('click', () => this._toggleFloatingSidebar());
        }

        // New chat (floating only – starts a fresh conversation)
        if (this.elements.floatingNewChat && !isImmersive) {
            this.elements.floatingNewChat.addEventListener('click', () => this.startNewChat());
        }
        if (this.elements.newChatBtn && !isImmersive) {
            this.elements.newChatBtn.addEventListener('click', () => this.startNewChat());
        }

        // AI policy: immersive = modal, floating = inline I understand
        const modalAckBtn = document.getElementById('chatAiPolicyModalAckBtn');
        if (modalAckBtn) {
            modalAckBtn.addEventListener('click', () => {
                this._setAcknowledgedAiPolicy();
                this._hideAiPolicyModal();
                this._updateAiNoticeVisibility();
            });
        }
        const policyLinkBtn = document.getElementById('chatAiPolicyLinkBtn');
        if (policyLinkBtn) {
            policyLinkBtn.addEventListener('click', (e) => {
                e.preventDefault();
                this._showAiPolicyModal();
            });
        }
        const policyOverlay = document.getElementById('chatAiPolicyModalOverlay');
        if (policyOverlay) {
            policyOverlay.addEventListener('click', (e) => {
                if (e.target === policyOverlay) this._hideAiPolicyModal();
            });
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape' && policyOverlay.getAttribute('aria-hidden') === 'false') {
                    this._hideAiPolicyModal();
                }
            });
        }
        const inlineAckBtn = document.getElementById('chatAiPolicyAckBtn');
        if (inlineAckBtn) {
            inlineAckBtn.addEventListener('click', () => {
                this._setAcknowledgedAiPolicy();
                this._updateAiNoticeVisibility();
            });
        }

        // Floating: when user clicks/ taps anywhere in chat before acking, animate the policy notice
        if (!isImmersive) {
            const mainArea = this.elements.widget?.querySelector('.chat-floating-main');
            if (mainArea) {
                const onPointer = (e) => {
                    if (!this._hasAcknowledgedAiPolicy()) {
                        const isAckAction = e.target.closest('#chatAiPolicyAckBtn, #chatAiPolicyLinkBtn');
                        if (!isAckAction) this._triggerPolicyNoticeAttention();
                    }
                };
                mainArea.addEventListener('pointerdown', onPointer, true);
                mainArea.addEventListener('click', onPointer, true);
            }
        }

        // Immersive: when user clicks anywhere in chat before acking, bounce the policy notice
        if (isImmersive) {
            const inner = this.elements.widget?.querySelector('.chat-immersive-widget-inner');
            if (inner) {
                const onPointer = (e) => {
                    if (!this._hasAcknowledgedAiPolicy()) {
                        const isAckAction = e.target.closest('#chatAiPolicyAckBtn, #chatAiPolicyLinkBtn');
                        if (!isAckAction) this._triggerImmersivePolicyNoticeAttention();
                    }
                };
                inner.addEventListener('pointerdown', onPointer, true);
                inner.addEventListener('click', onPointer, true);
            }
        }

        // Immersive quick prompts: click to send
        if (isImmersive && this.elements.quickPrompts) {
            this.elements.quickPrompts.addEventListener('click', (e) => {
                const btn = e.target.closest('.chat-immersive-quick-prompt');
                if (btn) {
                    const text = (btn.getAttribute('data-prompt') || btn.textContent || '').trim();
                    if (text) {
                        this.elements.input.value = text;
                        this.handleSendMessage();
                    }
                }
            });
        }

        // Clear conversation
        if (this.elements.clearBtn) {
            this.elements.clearBtn.addEventListener('click', () => this.handleClearConversation());
        }

        // Send message handlers (click = send when idle, stop when loading; button must stay enabled so Stop is clickable)
        this.elements.sendBtn.addEventListener('click', () => {
            if (this.isTyping) {
                this._log('Send button clicked while loading -> stop');
                this.stopCurrentRequest();
            } else {
                this.handleSendMessage();
            }
        });
        this.elements.input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.handleSendMessage();
            }
        });

        // Auto-resize textarea as user types (grow up to max-height, then scroll)
        if (this.elements.input && this.elements.input.nodeName === 'TEXTAREA') {
            this.elements.input.addEventListener('input', () => this._resizeChatInput());
            this._resizeChatInput();
        }

        // Re-sync body scroll lock when crossing the mobile/desktop breakpoint with chat open
        if (!isImmersive && typeof window.matchMedia === 'function') {
            const mq = window.matchMedia('(max-width: 768px)');
            const onViewportChange = () => this._syncFloatingMobileBodyLock(this.isOpen());
            if (typeof mq.addEventListener === 'function') {
                mq.addEventListener('change', onViewportChange);
            } else if (typeof mq.addListener === 'function') {
                mq.addListener(onViewportChange);
            }
        }

        // Close chat when clicking outside (floating only)
        if (!isImmersive && this.elements.fab) {
            document.addEventListener('click', (e) => {
                if (e.target.closest('#ai-assistant-btn')) return;
                if (this.isOpen() &&
                    !this.elements.widget.contains(e.target) &&
                    this.elements.fab && !this.elements.fab.contains(e.target)) {
                // Don't close if clicking on a modal/confirmation dialog
                // Check if click target is within a modal (high z-index element)
                let isWithinModal = false;
                let element = e.target;
                while (element && element !== document.body) {
                    const style = window.getComputedStyle(element);
                    const zIndex = parseInt(style.zIndex, 10);
                    // Modals typically have z-index >= 1000
                    if (zIndex >= 1000 || element.getAttribute('role') === 'dialog') {
                        isWithinModal = true;
                        break;
                    }
                    element = element.parentElement;
                }

                if (!isWithinModal) {
                    this.toggleChat(false);
                }
            }
            });
        }

        // Prevent chat from closing when clicking inside
        this.elements.widget.addEventListener('click', (e) => {
            e.stopPropagation();
        });

        // When sidebar is open, clicking the chat area (messages or input) closes the sidebar
        if (!isImmersive && this.elements.widget) {
            const main = this.elements.widget.querySelector('.chat-floating-main');
            if (main) {
                main.addEventListener('click', (e) => {
                    if (!this.elements.widget.classList.contains('chat-sidebar-open')) return;
                    const inMessages = this.elements.messages && this.elements.messages.contains(e.target);
                    const inInput = this.elements.widget.querySelector('.chat-input-container')?.contains(e.target);
                    if (inMessages || inInput) {
                        this._toggleFloatingSidebar();
                    }
                });
            }
        }

        // Handle interactive elements inside chatbot messages (event delegation)
        this.elements.messages.addEventListener('click', (e) => {
            const tourButton = e.target.closest('.chatbot-tour-trigger');
            if (tourButton) {
                e.preventDefault();
                e.stopPropagation();

                // Check for workflow-based tour (new dynamic system)
                const workflowId = tourButton.getAttribute('data-workflow');
                const href = tourButton.getAttribute('href') || '';

                if (workflowId || href.includes('chatbot-tour=')) {
                    // Handle workflow-based tour trigger
                    const targetPage = href.split('#')[0] || window.location.pathname;

                    // Close chatbot before starting tour
                    this.toggleChat(false);

                    // Use WorkflowTourParser if available for dynamic registration
                    if (window.WorkflowTourParser && workflowId) {
                        setTimeout(() => {
                            window.WorkflowTourParser.handleTourTrigger(workflowId, targetPage);
                        }, 300);
                    } else if (href) {
                        // Fallback: navigate directly with tour hash
                        setTimeout(() => {
                            window.location.href = href;
                        }, 300);
                    }
                    return;
                }

                // Legacy: entry form tour with step number
                const stepNumber = parseInt(tourButton.getAttribute('data-step'), 10);
                if (!isNaN(stepNumber) && typeof window.startEntryFormTour === 'function') {
                    // Close chatbot before starting tour
                    this.toggleChat(false);
                    // Start tour at specific step
                    setTimeout(() => {
                        window.startEntryFormTour(stepNumber);
                    }, 300);
                }
                return;
            }

            // "Show me" onboarding links — indicator view/edit open in a new tab (target=_blank)
            const showMeLink = e.target.closest('a.chatbot-show-me');
            if (showMeLink) {
                const href = (showMeLink.getAttribute('href') || '').split('#')[0];
                if (/^\/admin\/indicator_bank\/(?:view|edit)\/\d+/.test(href)) {
                    return;
                }
                if (!href) return;
                e.preventDefault();
                const tourMatch = href.match(/chatbot-tour=([a-zA-Z0-9-]+)/);
                if (tourMatch && window.WorkflowTourParser && typeof window.WorkflowTourParser.handleTourTrigger === 'function') {
                    // handleTourTrigger closes the chat, fetches/registers the tour, then either
                    // starts it in-place (same page) or navigates with the hash (different page).
                    const workflowId = tourMatch[1];
                    const targetPage = href.split('#')[0] || window.location.pathname;
                    window.WorkflowTourParser.handleTourTrigger(workflowId, targetPage);
                } else {
                    this.toggleChat(false);
                    window.location.href = href;
                }
            }
        });

        if (this._loadFormBuilderAiConfig()) {
            this._setupFormBuilderAttachmentHandlers();
        }

    }


    addMessage(message, isUser = false, opts = {}) {
        // Add to conversation history first so index is correct
        const entry = {
            message: message,
            isUser: isUser,
            timestamp: new Date().toISOString()
        };
        if (!isUser && opts.structuredPayload) entry.structuredPayload = opts.structuredPayload;
        this.conversationHistory.push(entry);

        // Limit conversation history to prevent memory issues (immersive: keep full history for DB-backed convos)
        const maxHistory = this._isImmersive() ? 500 : 20;
        if (this.conversationHistory.length > maxHistory) {
            this.conversationHistory = this.conversationHistory.slice(-maxHistory);
        }

        // Add to DOM with index for edit/rewind
        this.addMessageToDOM(message, isUser, this.conversationHistory.length - 1, opts);

        // Save conversation to localStorage
        this.saveConversationHistory();
    }


    addErrorMessage(errorMessage, retryMessage) {
        this.conversationHistory.push({
            message: errorMessage,
            isUser: false,
            timestamp: new Date().toISOString(),
            isError: true,
            retryMessage: retryMessage || ''
        });
        const maxHistory = this._isImmersive() ? 500 : 20;
        if (this.conversationHistory.length > maxHistory) {
            this.conversationHistory = this.conversationHistory.slice(-maxHistory);
        }
        this.addMessageToDOM(errorMessage, false, this.conversationHistory.length - 1, { isError: true, retryMessage: retryMessage || '' });
        this.saveConversationHistory();
        if (this._isImmersive()) {
            const cid = this.getActiveConversationId && this.getActiveConversationId();
            if (cid) {
                this._apiFetch(`/api/ai/v2/conversations/${encodeURIComponent(cid)}/messages`, {
                    method: 'POST',
                    body: JSON.stringify({
                        role: 'assistant',
                        content: errorMessage,
                        meta: { is_error: true, retry_message: retryMessage || '' }
                    })
                }).then(() => { if (this._dispatchImmersiveUpdate) this._dispatchImmersiveUpdate(); }).catch(() => {});
            }
        }
    }


    addMessageToDOM(message, isUser = false, messageIndex = undefined, opts = {}) {
        const isError = opts.isError === true;
        const retryMessage = opts.retryMessage || '';
        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-message ${isUser ? 'user' : 'bot'}${isError ? ' chat-message-error' : ''}`;

        // Auto-detect text direction so LTR text reads correctly on RTL pages and vice-versa
        messageDiv.setAttribute('dir', 'auto');

        if (isUser) {
            const inner = document.createElement('div');
            inner.className = 'chat-message-user-inner';
            const text = String(message ?? '');
            if (text) {
                const textEl = document.createElement('div');
                textEl.className = 'chat-message-user-text';
                textEl.textContent = text;
                inner.appendChild(textEl);
            }
            if (opts.previewUrl) {
                this._renderFormBuilderUserAttachmentGrid?.(inner, [{
                    kind: 'image',
                    url: opts.previewUrl,
                    alt: opts.previewAlt || 'Attached image',
                    filename: opts.previewAlt || '',
                }]);
            } else if (opts.attachmentPreviews?.length) {
                this._renderFormBuilderUserAttachmentGrid?.(inner, opts.attachmentPreviews);
            }
            if (!inner.childNodes.length) {
                inner.textContent = text;
            }
            messageDiv.appendChild(inner);
        } else {
            // Bot/AI messages are sanitized to allow safe HTML formatting
            let sanitizedMessage = this.sanitizeHtml(message);

            // Auto-convert tour step references to interactive buttons
            // Universal patterns that work in any language
            if (typeof window.getEntryFormTourSteps === 'function') {
                // Pattern: Detect action phrase followed by parentheses with step keyword and number
                // Works for: "Show me (Step 3)", "Montrez-moi (Étape 3)", "Ver (Paso 3)", etc.
                sanitizedMessage = sanitizedMessage.replace(
                    /([^.!?\n]*?)\b(show\s+me|montrez-moi|ver|voir|zeig|mostra|toon|pokaż|見せ|显示|muestra|voir|ver\s+paso|show)\s*\(([^)]*?)(\d+)([^)]*?)\)/gi,
                    (match, beforeText, actionPhrase, beforeNum, stepNum, afterNum) => {
                        // Verify it contains step keywords
                        const lowerMatch = match.toLowerCase();
                        const tourKeywords = ['step', 'étape', 'paso', 'schritt', 'passo', 'stap', 'krok', 'ステップ', '步骤'];
                        const hasTourKeyword = tourKeywords.some(keyword => lowerMatch.includes(keyword));

                        if (hasTourKeyword) {
                            // Extract and capitalize the action phrase properly
                            let buttonText = actionPhrase.trim();
                            // Capitalize first letter
                            buttonText = buttonText.charAt(0).toUpperCase() + buttonText.slice(1);

                            // Return just the button, removing the original text
                            const safeBefore = this.escapeHtml((beforeText || '').trim());
                            const safeLabel = this.escapeHtml(buttonText);
                            const safeStep = String(stepNum).replace(/[^0-9]/g, '');
                            return `${safeBefore}<br><button class="chatbot-tour-trigger" data-step="${safeStep}"><i class="fas fa-compass"></i>${safeLabel}</button>`;
                        }
                        return match; // Return unchanged if not a tour reference
                    }
                );
            }

            const wrap = document.createElement('div');
            wrap.className = 'flex items-start gap-2';
            const content = document.createElement('div');
            content.className = 'chat-message-content';
            try {
                const doc = new DOMParser().parseFromString(String(sanitizedMessage || ''), 'text/html');
                const root = doc.body;
                if (root) {
                    // Inject lightweight onboarding affordances (e.g. add "Show me" next to key admin links)
                    const showMeLink = this._augmentOnboardingActions(root);

                    const fragment = document.createDocumentFragment();
                    while (root.firstChild) fragment.appendChild(root.firstChild);
                    content.appendChild(fragment);

                    // If we created a "Show me" link, append it to the content wrapper with proper spacing
                    if (showMeLink) {
                        // Add a wrapper div for the button to ensure it's positioned correctly
                        const buttonWrapper = document.createElement('div');
                        buttonWrapper.className = 'chatbot-show-me-wrapper';
                        buttonWrapper.appendChild(showMeLink);
                        content.appendChild(buttonWrapper);
                    }
                } else {
                    // Parsed but empty body: still render sanitized HTML so <strong>, <br> etc. display correctly
                    content.innerHTML = String(sanitizedMessage || '');
                }
            } catch (_) {
                // Fallback: message was already sanitized, so safe to render as HTML (avoids showing raw tags)
                content.innerHTML = String(sanitizedMessage || '');
            }
            wrap.appendChild(content);

            // Confidence badge (shown when agent returns a grounding/confidence score)
            const confidence = opts.confidence || null;
            const groundingScore = opts.grounding_score != null ? opts.grounding_score : null;
            let userPromptForConfidence = opts._confidenceUserPrompt;
            if (userPromptForConfidence === undefined && !isUser && typeof messageIndex === 'number' && messageIndex > 0) {
                const prev = this.conversationHistory[messageIndex - 1];
                if (prev && prev.isUser) userPromptForConfidence = prev.message;
            }
            if (confidence || groundingScore != null) {
                if (!this._shouldSuppressConfidenceBadgeForUserPrompt(userPromptForConfidence)) {
                    const badge = this._buildConfidenceBadge(confidence, groundingScore);
                    if (badge) content.appendChild(badge);
                }
            }

            messageDiv.appendChild(wrap);

            // Process message for workflow tour triggers
            if (window.WorkflowTourParser && typeof window.WorkflowTourParser.processMessage === 'function') {
                try {
                    window.WorkflowTourParser.processMessage(content);
                } catch (e) {
                    console.debug('WorkflowTourParser error:', e);
                }
            }
            this._formatChatResponseSources(content);
            this._enhanceIndicatorActionLinks(content);
            this._addTableCopyButtons(content);
            this._collapseLongTables(content);
            this._tableDebugLog('Rendered assistant message tables:', {
                tables_in_dom: content.querySelectorAll('table').length,
                ai_tables_in_dom: content.querySelectorAll('.chat-ai-table').length
            });
        }

        const wrapper = document.createElement('div');
        wrapper.className = 'chat-message-wrapper';
        if (isError) wrapper.classList.add('chat-message-wrapper-error');
        wrapper.classList.add(isUser ? 'is-user' : 'is-bot');
        if (typeof messageIndex === 'number') wrapper.setAttribute('data-message-index', String(messageIndex));
        if (!isUser && opts.traceId != null) wrapper.setAttribute('data-trace-id', String(opts.traceId));
        wrapper.appendChild(messageDiv);

        const getTextFn = isUser
            ? () => messageDiv.querySelector('div')?.textContent ?? ''
            : () => this._buildCopyTextForBotMessage(wrapper, messageDiv);
        const actionBar = this._createMessageActionBar(messageDiv, isUser, getTextFn, messageIndex);

        if (isError && retryMessage) {
            const errorRetryLabel = this._uiString('retry') || 'Retry';
            const retryBtn = document.createElement('button');
            retryBtn.type = 'button';
            retryBtn.className = 'chat-message-action chat-message-action-retry';
            retryBtn.setAttribute('aria-label', errorRetryLabel);
            retryBtn.title = errorRetryLabel;
            retryBtn.innerHTML = '<i class="fas fa-rotate-right" aria-hidden="true"></i>';
            retryBtn.addEventListener('click', () => {
                if (this.isTyping) return;
                wrapper.remove();
                if (this.conversationHistory.length && this.conversationHistory[this.conversationHistory.length - 1].isError) {
                    this.conversationHistory.pop();
                    this.saveConversationHistory();
                }
                this.handleSendMessage(retryMessage, { allowServerInflightBypass: true });
            });
            actionBar.appendChild(retryBtn);
        }

        wrapper.appendChild(actionBar);

        this.elements.messages.appendChild(wrapper);
        if (!isUser && !isError) {
            const pieces = this._pendingStructuredRawPieces;
            if (pieces && pieces.length) {
                this._pendingStructuredRawPieces = null;
                this._tableDebugLog('addMessageToDOM', {
                    messageIndex,
                    hasStructuredPayload: true,
                    payloadType: 'multi',
                    fromOpts: !!opts.structuredPayload,
                    wrapperInDOM: !!(wrapper && wrapper.parentElement),
                    messageDivInDOM: !!(messageDiv && messageDiv.parentElement),
                    totalWrappers: this.elements.messages ? this.elements.messages.querySelectorAll('.chat-message-wrapper').length : 0
                });
                for (const p of pieces) {
                    this._dispatchStructuredPayload(p, messageDiv, wrapper);
                }
            } else {
                const structuredPayload = opts.structuredPayload || this._consumePendingStructuredPayload();
                this._tableDebugLog('addMessageToDOM', {
                    messageIndex,
                    hasStructuredPayload: !!structuredPayload,
                    payloadType: structuredPayload && (structuredPayload.type || (structuredPayload.table_payload && 'table_payload') || 'unknown'),
                    fromOpts: !!opts.structuredPayload,
                    wrapperInDOM: !!(wrapper && wrapper.parentElement),
                    messageDivInDOM: !!(messageDiv && messageDiv.parentElement),
                    totalWrappers: this.elements.messages ? this.elements.messages.querySelectorAll('.chat-message-wrapper').length : 0
                });
                this._dispatchStructuredPayload(structuredPayload, messageDiv, wrapper);
            }
        }
        this.scrollToBottom();
    }


    /**
     * Whether to hide grounding/confidence for the user turn (e.g. "hi", "thanks") — not meaningful for RAG.
     * @param {string} [userPrompt]
     * @returns {boolean}
     */

    _shouldSuppressConfidenceBadgeForUserPrompt(userPrompt) {
        const raw = String(userPrompt || '').trim();
        if (!raw || raw.length > 56) return false;
        const compact = raw
            .toLowerCase()
            .replace(/[\u2018\u2019`']/g, "'")
            .replace(/[!?.…,:;'"()]+/g, ' ')
            .replace(/[^a-z0-9\u00c0-\u024f\s'-]/gi, ' ')
            .replace(/\s+/g, ' ')
            .trim();
        if (!compact) return false;

        if (/^(?:\b(?:hi|hello|hey|heya|hiya|howdy|yo|greetings)\b\s*)+$/i.test(compact)) return true;
        if (/^(?:hi|hey|hello|heya|hiya)\s+(there|everyone|all)\s*$/i.test(compact)) return true;
        if (/^(?:good\s+(?:morning|afternoon|evening|day))\.?\s*$/i.test(compact)) return true;
        if (/^(?:thanks?|thank\s+you|thx|ty|merci|danke|gracias)\s*!?\s*$/i.test(compact)) return true;
        if (/^(?:ok+|okay|kk)\s*!?\s*$/i.test(compact)) return true;
        if (/^(?:bye|goodbye|ciao|cheers)\s*!?\s*$/i.test(compact)) return true;
        if (/^how\s+are\s+you\??$/i.test(compact)) return true;
        if (/^what'?s\s+up\??$/i.test(compact)) return true;

        return false;
    }


    /**
     * Build a small confidence/grounding badge element to append to an AI message.
     * @param {string|null} confidence - 'high', 'medium', or 'low'
     * @param {number|null} groundingScore - 0.0–1.0
     * @returns {HTMLElement|null}
     */

    _buildConfidenceBadge(confidence, groundingScore) {
        const level = confidence || (
            groundingScore != null
                ? (groundingScore >= 0.7 ? 'high' : groundingScore >= 0.4 ? 'medium' : 'low')
                : null
        );
        if (!level) return null;

        const colorMap = {
            high:   { bg: '#dcfce7', color: '#166534', icon: '●', label: 'High confidence' },
            medium: { bg: '#fef9c3', color: '#854d0e', icon: '●', label: 'Medium confidence' },
            low:    { bg: '#fee2e2', color: '#991b1b', icon: '●', label: 'Low confidence' },
        };
        const cfg = colorMap[level] || colorMap.medium;

        const badge = document.createElement('div');
        badge.className = 'chat-confidence-badge';
        badge.style.cssText = [
            'display:inline-flex',
            'align-items:center',
            'gap:4px',
            'margin-top:8px',
            'padding:2px 8px',
            'border-radius:9999px',
            `background:${cfg.bg}`,
            `color:${cfg.color}`,
            'font-size:0.7rem',
            'font-weight:500',
            'opacity:0.85',
            'cursor:default',
        ].join(';');

        const scoreText = groundingScore != null ? ` (${Math.round(groundingScore * 100)}%)` : '';
        badge.title = `Source grounding score${groundingScore != null ? `: ${Math.round(groundingScore * 100)}%` : ''}`;
        badge.innerHTML = `<span aria-hidden="true" style="font-size:0.55rem">${cfg.icon}</span> ${cfg.label}${scoreText}`;
        return badge;
    }


    showWelcomeMessage() {
        this._updateImmersiveQuickPromptsVisibility();

        if (!this._fbAiConfig || !this.elements || !this.elements.messages) return;

        if (this.elements.messages.querySelector('.fb-ai-welcome-bubble')) return;

        const isCreateMode = !this._fbAiConfig.templateId;
        const msgEl = document.createElement('div');
        msgEl.className = 'chat-message bot fb-ai-welcome-bubble';
        msgEl.setAttribute('dir', 'auto');
        const inner = document.createElement('div');
        inner.className = 'flex items-start gap-2';
        const content = document.createElement('div');
        content.className = 'chat-message-content';
        content.innerHTML = isCreateMode
            ? `<p><strong>Describe the form template you want to create.</strong></p>
               <ul>
                 <li>"Create a health programme reporting form with sections for staffing, services and budget"</li>
                 <li>"Build a template from this questionnaire:" (paste text, drop files, or paste multiple screenshots)</li>
               </ul>
               <p class="text-sm text-gray-500">All changes go to a draft version — you review and deploy them in the form builder.</p>`
            : `<p><strong>Describe the changes you want for this template.</strong></p>
               <ul>
                 <li>"Add a WASH section with 3 number questions"</li>
                 <li>"Make the budget field required"</li>
                 <li>"Show Q5 only if Q4 is Yes"</li>
               </ul>
               <p class="text-sm text-gray-500">All changes go to a draft version — you review and deploy them.</p>`;
        inner.appendChild(content);
        msgEl.appendChild(inner);
        this.elements.messages.appendChild(msgEl);
        this.scrollToBottom();
    }


    // Get API status

    getAPIStatus() {
        const debugModules = this.debug && this.debug.getConfig ? this.debug.getConfig().modules : {};
        const chatbotDebugEnabled = debugModules['chatbot'] || debugModules['chatbot-api'] || debugModules['chatbot-context'];

        return {
            available: this.apiAvailable,
            status: this.apiAvailable ? '🟢 Available' : '🔴 Unavailable',
            endpoint: this.apiEndpoint,
            debugMode: chatbotDebugEnabled,
            language: this.preferredLanguage,
            conversationLength: this.conversationHistory.length,
            debugSystem: 'Managed by centralized debug.js - Use window.debug.enableChatbot() to enable'
        };
    }


    clearConversation() {
        try {
            localStorage.removeItem(this.storageKey);
            if (!this._isImmersive()) this._setFloatingConversationId(null);
            this.conversationHistory = [];

            // Clear all messages
            this.elements.messages.replaceChildren();

            // Show welcome message
            this.showWelcomeMessage();
            this._updateAiNoticeVisibility();
        } catch (error) {
            console.warn('Failed to clear conversation:', error);
        }
    }


    handleClearConversation() {
        if (this._isImmersive()) {
            this.startNewChat();
            return;
        }
        // Show confirmation dialog
        const msg = this._uiString('clearConversationConfirm') || 'Are you sure you want to clear the entire conversation? This action cannot be undone.';
        const clearLabel = this._uiString('clear') || 'Clear';
        const cancelLabel = this._uiString('cancel') || 'Cancel';
        const clearTitle = this._uiString('clearConversationTitle') || 'Clear Conversation?';
        const doClear = () => {
            // Clear conversation history and localStorage (and floating conversation id so next send starts a new DB thread)
            try {
                localStorage.removeItem(this.storageKey);
                this._setFloatingConversationId(null);
                this.conversationHistory = [];

                // Clear all messages completely
                this.elements.messages.replaceChildren();

                // Add a fresh welcome message
                this.showWelcomeMessage();
                this._updateAiNoticeVisibility();
            } catch (error) {
                console.warn('Failed to clear conversation:', error);
            }
        };

        if (window.showDangerConfirmation) {
            window.showDangerConfirmation(msg, doClear, null, clearLabel, cancelLabel, clearTitle);
            return;
        }
        if (window.showConfirmation) {
            window.showConfirmation(msg, doClear, null, clearLabel, cancelLabel, clearTitle);
            return;
        }
        console.warn('Custom confirmation dialog not available:', msg);
    }


    async callAIService(message, context = {}) {
        try {
            // Backward-compatible wrapper: route through the unified v2 request path so
            // transport behavior, DLP, sources, and conversation management can't drift.
            // `context` is intentionally ignored here to preserve the /api/ai/v2 contract.
            return await this.callBackendAPI(String(message ?? ''), {}, null);
        } catch (error) {
            console.error('AI service error:', error);
            throw error;
        }
    }


    showGreeting() {
        const greetings = this.messages.greetings || {};
        const greetingMessage = greetings[this.preferredLanguage] || greetings.en || "Hello! How can I help you?";
        this.addMessage(greetingMessage);
    }


    // Method to manually set language preference

    setLanguagePreference(language) {
        const validLanguages = ['en', 'es', 'fr', 'ar', 'ru', 'zh', 'hi'];
        const normalized = this._normalizeLanguage(language);
        if (validLanguages.includes(normalized)) {
            this._setPreferredLanguage(normalized);

            // Update greeting message
            this.clearConversation();
            //console.log(`Language preference set to: ${language}`);
        } else {
            console.warn(`Invalid language: ${language}. Valid options: ${validLanguages.join(', ')}`);
        }
    }


    resetLaptopPreference() {
        /* No-op: chat is always maximized */
    }
}

Object.assign(HumDatabankChatbot.prototype,
    StateMixin,
    ChatSourcesMixin,
    DlpPolicyMixin,
    HtmlPipelineMixin,
    SpotlightToursMixin,
    FormBuilderAiMixin,
    WidgetUiMixin,
    TransportMixin,
    ConversationsMixin,
);
