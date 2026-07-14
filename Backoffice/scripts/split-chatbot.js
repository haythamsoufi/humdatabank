/**
 * One-time splitter: extracts HumDatabankChatbot methods into mixin modules.
 * Run from Backoffice/: node scripts/split-chatbot.js
 */
const fs = require('fs');
const path = require('path');

const SRC = path.join(__dirname, '../app/static/js/chatbot.js'); // monolith removed after modular split; script is for one-time regeneration only

if (!fs.existsSync(SRC)) {
    console.error('split-chatbot.js requires the legacy monolith at app/static/js/chatbot.js (removed).');
    console.error('Edit modules under app/static/js/chatbot/ directly.');
    process.exit(1);
}
const OUT_DIR = path.join(__dirname, '../app/static/js/chatbot');

const MODULE_METHODS = {
    'state.js': [
        '_stopInflightPoll', '_getImmersiveDraftKey', '_getActiveConversationKey',
        '_setServerInflightIndex', 'isConversationRunning', '_rekeyInflight',
        '_detachConversationStreamByKey', '_detachActiveConversationStream',
        'saveConversationHistory', 'loadConversationHistory', 'setExpanded',
        'saveExpandedState', 'loadExpandedState',
    ],
    'chat-sources.js': [
        '_chatSourcesAllowed', '_chatSourcesDefault', '_normalizeChatSources',
        '_loadChatSourcesFromStorage', '_saveChatSourcesToStorage', '_getChatSourcesFromUi',
        '_applyChatSourcesToUi', '_getChatSourcesFromUiOrStorage', '_setupChatSourcesControl',
    ],
    'dlp-policy.js': [
        '_makeDlpError', '_formatDlpFindings', '_showDlpModal', '_handleDlpChallenge',
        '_hasAcknowledgedAiPolicy', '_setAcknowledgedAiPolicy', '_showAiPolicyModal',
        '_hideAiPolicyModal', '_updateAiNoticeVisibility', '_triggerPolicyNoticeAttention',
        '_updateImmersiveChatControls', '_triggerImmersivePolicyNoticeAttention',
        '_updateFloatingChatControls',
    ],
    'html-pipeline.js': [
        'escapeHtml', '_safeSameOriginUrl', 'decodeHtmlEntities', '_linkifyCellContent',
        'markdownTablesToHtml', 'markdownSourcesToHtml', 'sanitizeHtml', '_tableToMatrix',
        '_downloadTableAsExcel', '_addTableCopyButtons', '_collapseLongTables',
        '_normalizeSourcesSection', '_formatChatResponseSources', '_enhanceIndicatorActionLinks',
        '_augmentOnboardingActions', '_inferWorkflowTourHref',
    ],
    'spotlight-tours.js': [
        '_registerChatbotTours', '_getSpotlightTooltipPosition', '_setSpotlightTooltipPosition',
        'runSpotlightFromHash', 'spotlightById', '_spotlightSelector', '_spotlightElement',
        'startTour', '_showTourStep', '_advanceTourStep', '_endTour', '_clearSpotlight',
    ],
    'form-builder-ai.js': [
        '_loadFormBuilderAiConfig', '_ensureFormBuilderAiIntegration', '_syncFormBuilderAiPanelFab',
        '_openFormBuilderChat', '_clearFormBuilderWelcomeBubble', 'updateFormBuilderVersionId',
        '_fbAiLabels', '_parseTemplateEditLink', '_findTemplateEditLink',
        '_handleFormBuilderResult',
        '_stripFormBuilderEditAnswerHtml', '_appendFormBuilderApplyActions',
        '_fbAiRestoreStructureUrl', '_syncFormBuilderAiUndoRedoButtons',
        '_formBuilderAiRestoreSnapshot', '_formBuilderAiUndo', '_formBuilderAiRedo',
        '_appendFormBuilderStatusBubble', '_snapshotFormBuilderIds',
        '_highlightFormBuilderAiChanges', '_reloadFormBuilderAjax',
    ],
    'widget-ui.js': [
        '_initFloatingDrag', '_initFabDrag', '_initFabOverlapAvoidance',
        'toggleChat', 'isOpen', 'scrollToBottom', '_resizeChatInput',
        'showTypingIndicator', 'addStepToProgress', '_isSuppressedStepDetail',
        'appendStepDetail', '_updateStepDetail', 'updateTypingIndicator',
        'hideTypingIndicator', '_setSendButtonStop', 'stopCurrentRequest',
        '_updateImmersiveQuickPromptsVisibility', '_syncFloatingMobileBodyLock',
    ],
    'transport.js': [
        '_generateClientMessageId', '_buildUnifiedChatPayload',
        '_coerceStructuredPayload', '_setPendingStructuredPayload',
        '_consumePendingStructuredPayload', '_dispatchStructuredPayload',
        '_cleanTextForCopyFromElement', '_formatStructuredPayloadForCopy',
        '_buildCopyTextForBotMessage',
        'handleSendMessage', '_scheduleStreamingFlush', '_scheduleStreamingFlushBatched',
        'processStreamingMessage', 'streamResponseWithWebSocket', 'streamResponseWithSSE',
        'createStreamingMessageElement', 'getStreamingSafeHtml', 'getAIResponse',
        '_isServiceUnavailableResponse', 'callBackendAPI',
        'getPageContext', 'getLocalPageExplanation', 'getLocalResponse',
    ],
    'conversations.js': [
        '_getImmersiveActiveId', '_setImmersiveActiveId', '_getImmersiveChatPath',
        '_updateImmersiveUrl', '_handleImmersivePopstate', '_getFloatingConversationId',
        '_setFloatingConversationId', '_updateImmersiveLinkHref', '_toggleFloatingSidebar',
        '_escapeAttr', '_renderFloatingConversationList', '_apiFetch',
        '_renderInflightProgress', '_maybeRestoreInflightFromConversationResponse',
        '_startInflightPoll', '_setupVisibilityChangeHandler', '_checkAndResumeInflightPoll',
        '_loadImmersiveConversation', '_dispatchImmersiveUpdate',
        '_refreshConversationSidebarTitles', '_resetFloatingHeaderTitleToDefault',
        '_applyFloatingHeaderTitleText', '_buildLocalConversationTitle',
        '_applyInstantChatTitles', '_syncFloatingHeaderTitleFromConversationList',
        '_refreshFloatingHeaderTitleFromServer', '_cancelConversationTitleBurst',
        '_queueConversationTitleBurst', '_scheduleConversationTitleRefresh',
        'loadConversation', '_mapApiMessages', 'startNewChat', 'switchChat',
        'deleteChat', 'deleteAllChats', 'getActiveConversationId', 'getImmersiveData',
        'rewindToMessageIndex', 'enterEditModeInBubble', 'submitEditedMessage',
        '_retryFromUserMessage', '_createMessageActionBar',
    ],
};

const MIXIN_NAMES = {
    'state.js': 'StateMixin',
    'chat-sources.js': 'ChatSourcesMixin',
    'dlp-policy.js': 'DlpPolicyMixin',
    'html-pipeline.js': 'HtmlPipelineMixin',
    'spotlight-tours.js': 'SpotlightToursMixin',
    'form-builder-ai.js': 'FormBuilderAiMixin',
    'widget-ui.js': 'WidgetUiMixin',
    'transport.js': 'TransportMixin',
    'conversations.js': 'ConversationsMixin',
};

const src = fs.readFileSync(SRC, 'utf8');
const lines = src.split('\n');

// Find class boundaries
const classStart = lines.findIndex((l) => l.startsWith('class HumDatabankChatbot'));
const classEnd = lines.findIndex((l, i) => i > classStart && l.trim() === '}' && !l.startsWith(' ') && !l.startsWith('\t'));
if (classStart < 0 || classEnd < 0) {
    console.error('Could not find class boundaries');
    process.exit(1);
}

const classLines = lines.slice(classStart + 1, classEnd);

// Parse methods: class-level methods only (must open with `{` on same line or soon after)
const methodStartRe = /^    (async )?([a-zA-Z_][a-zA-Z0-9_]*)\s*\(/;
const methods = [];
let current = null;

function lineOpensMethodBody(startIdx) {
    for (let j = startIdx; j < Math.min(startIdx + 3, classLines.length); j++) {
        const ln = classLines[j];
        if (/\)\s*\{/.test(ln)) return true;
        if (/\)\s*$/.test(ln) && j + 1 < classLines.length && /^\s*\{/.test(classLines[j + 1])) return true;
    }
    return false;
}

for (let i = 0; i < classLines.length; i++) {
    const line = classLines[i];
    const m = line.match(methodStartRe);
    if (m && lineOpensMethodBody(i)) {
        if (current) {
            current.endLine = i - 1;
            current.body = classLines.slice(current.startLine, i).join('\n');
            methods.push(current);
        }
        current = {
            name: m[2],
            async: !!m[1],
            startLine: i,
            endLine: null,
            body: null,
        };
    }
}
if (current) {
    current.endLine = classLines.length - 1;
    current.body = classLines.slice(current.startLine).join('\n');
    methods.push(current);
}

console.log(`Parsed ${methods.length} methods`);

// Build reverse map: method -> module
const methodToModule = {};
for (const [mod, names] of Object.entries(MODULE_METHODS)) {
    for (const name of names) {
        methodToModule[name] = mod;
    }
}

const byModule = {};
const coreMethods = [];

for (const method of methods) {
    const mod = Object.prototype.hasOwnProperty.call(methodToModule, method.name)
        ? methodToModule[method.name]
        : undefined;
    if (mod) {
        if (!byModule[mod]) byModule[mod] = [];
        byModule[mod].push(method);
    } else {
        coreMethods.push(method);
    }
}

fs.mkdirSync(OUT_DIR, { recursive: true });

function writeMixin(moduleFile, mixinName, methodList) {
    const header = `/**\n * Chatbot ${mixinName.replace('Mixin', '')} module\n * @module chatbot/${moduleFile.replace('.js', '')}\n */\n\nexport const ${mixinName} = {\n`;
    const body = methodList.map((m) => m.body).join(',\n\n');
    const footer = '\n};\n';
    fs.writeFileSync(path.join(OUT_DIR, moduleFile), header + body + footer, 'utf8');
    console.log(`Wrote ${moduleFile}: ${methodList.length} methods`);
}

for (const [mod, methodList] of Object.entries(byModule)) {
    const mixinName = MIXIN_NAMES[mod];
    if (!mixinName) {
        console.error('Missing MIXIN_NAMES for', mod);
        process.exit(1);
    }
    writeMixin(mod, mixinName, methodList);
}

// Write core.js with constructor + remaining methods
const coreHeader = `/**\n * HumDatabankChatbot core class\n * @module chatbot/core\n */\n\nimport { StateMixin } from './state.js';\nimport { ChatSourcesMixin } from './chat-sources.js';\nimport { DlpPolicyMixin } from './dlp-policy.js';\nimport { HtmlPipelineMixin } from './html-pipeline.js';\nimport { SpotlightToursMixin } from './spotlight-tours.js';\nimport { FormBuilderAiMixin } from './form-builder-ai.js';\nimport { WidgetUiMixin } from './widget-ui.js';\nimport { TransportMixin } from './transport.js';\nimport { ConversationsMixin } from './conversations.js';\n\nexport class HumDatabankChatbot {\n`;
const coreBody = coreMethods.map((m) => m.body).join('\n\n');
const coreFooter = `\n}\n\nObject.assign(HumDatabankChatbot.prototype,\n    StateMixin,\n    ChatSourcesMixin,\n    DlpPolicyMixin,\n    HtmlPipelineMixin,\n    SpotlightToursMixin,\n    FormBuilderAiMixin,\n    WidgetUiMixin,\n    TransportMixin,\n    ConversationsMixin,\n);\n`;

fs.writeFileSync(path.join(OUT_DIR, 'core.js'), coreHeader + coreBody + coreFooter, 'utf8');
console.log(`Wrote core.js: ${coreMethods.length} methods`);

// Extract structured payloads IIFE
const iifeMarker = '// Floating chatbot structured-payload renderer';
const iifeStart = src.indexOf(iifeMarker);
const iifeEnd = src.lastIndexOf('})();');
if (iifeStart >= 0 && iifeEnd >= 0) {
    let iifeInner = src.slice(iifeStart, iifeEnd);
    // Strip the IIFE wrapper opening
    iifeInner = iifeInner.replace(/^[\s\S]*?\(function \(\) \{\s*'use strict';\s*/m, '');
    const structuredPayloads = `/**
 * Floating chatbot structured-payload renderer
 * @module chatbot/structured-payloads
 */

export function registerStructuredPayloadListener() {
${iifeInner}
}
`;
    fs.writeFileSync(path.join(OUT_DIR, 'structured-payloads.js'), structuredPayloads, 'utf8');
    console.log('Wrote structured-payloads.js');
}

// Report unmapped methods in modules that weren't found
for (const [mod, names] of Object.entries(MODULE_METHODS)) {
    const found = new Set((byModule[mod] || []).map((m) => m.name));
    for (const name of names) {
        if (!found.has(name)) {
            console.warn(`WARN: ${mod} expected method not found: ${name}`);
        }
    }
}

console.log('\nCore methods:', coreMethods.map((m) => m.name).join(', '));
