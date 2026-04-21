// Debug configuration and utilities
const DEBUG_CONFIG = {
    global: true,  // Master switch for all debugging
    modules: {
        'forms-loader': false,
        'data-availability': false,
        'conditions': false,
        'field-management': false,
        'dynamic-indicators': false,
        'layout': false,
        'multi-select': false,
        'repeat-sections': false,
        'form-optimization': false,
        'form-events': false,
        'ajax-save': false,
        'form_validation': false,
        'pdf-export': false,
        'excel-export': false,
        'calculated-lists-runtime': false,
        'disaggregation-calculator': false,
        'matrix-handler': false,
        'numeric-formatting': false,
        'plugin-field-loader': false,
        'plugins': false,
        'pagination': false,  // Pagination module debugging
        'section-nav-scroll': false,  // Section nav scroll (non-paginated) debugging
        'chatbot': false,  // AI Chatbot debugging
        'chatbot-api': false,  // Chatbot API requests/responses
        'chatbot-context': false  // Chatbot page context collection
    },
    levels: {
        info: true,
        warn: true,
        error: true
    }
};

const STORAGE_PREFIX = 'ifrc:debug:module:';

function getModuleStorageKey(module) {
    return `${STORAGE_PREFIX}${module}`;
}

function applyPersistedModuleFlags() {
    try {
        // Read persisted flags for known modules only
        Object.keys(DEBUG_CONFIG.modules).forEach((module) => {
            const raw = localStorage.getItem(getModuleStorageKey(module));
            if (raw === '1') DEBUG_CONFIG.modules[module] = true;
            if (raw === '0') DEBUG_CONFIG.modules[module] = false;
        });
    } catch (e) {
        // no-op
    }
}

// Apply persisted module flags immediately on module load
applyPersistedModuleFlags();

export function initDebug(config = {}) {
    // Can be configured based on environment or other factors
    if (config.global !== undefined) {
        DEBUG_CONFIG.global = config.global;
    }

    // Update module configs
    if (config.modules) {
        Object.assign(DEBUG_CONFIG.modules, config.modules);
    }

    // Update level configs
    if (config.levels) {
        Object.assign(DEBUG_CONFIG.levels, config.levels);
    }

    console.log('Debug configuration:', DEBUG_CONFIG);
}

function shouldLog(module, level = 'info') {
    return DEBUG_CONFIG.global &&
           DEBUG_CONFIG.modules[module] &&
           DEBUG_CONFIG.levels[level];
}

/** Max length for stringified objects in one log line; beyond this we truncate. */
const MAX_STRINGIFY_LENGTH = 8000;

/**
 * Format a single argument for copy-friendly console output (no expandable objects).
 * Objects/arrays are JSON.stringified so the full content is visible and copyable.
 */
function formatArgForLog(arg) {
    if (arg === null) return 'null';
    if (arg === undefined) return 'undefined';
    const t = typeof arg;
    if (t === 'string') return arg;
    if (t === 'number' || t === 'boolean') return String(arg);
    if (t === 'function') return `[Function: ${arg.name || 'anonymous'}]`;
    if (t === 'object') {
        try {
            const seen = new WeakSet();
            const json = JSON.stringify(arg, (key, value) => {
                if (typeof value === 'object' && value !== null) {
                    if (seen.has(value)) return '[Circular]';
                    seen.add(value);
                }
                return value;
            }, 2);
            if (json.length > MAX_STRINGIFY_LENGTH) {
                return json.slice(0, MAX_STRINGIFY_LENGTH) + '\n...[truncated]';
            }
            return json;
        } catch (e) {
            return `[Object: ${String(e.message)}]`;
        }
    }
    return String(arg);
}

/**
 * Build one copy-friendly log string from (module, ...args).
 * Each arg is serialized so copying the log gives full data without expanding.
 */
function buildCopyFriendlyMessage(module, args) {
    const parts = args.map((a) => formatArgForLog(a));
    const timestamp = new Date().toISOString();
    const prefix = `[${timestamp}] [${module}]`;
    const body = parts.length === 1
        ? parts[0]
        : parts.join('\n');
    return `${prefix} ${body}`;
}

export function debugLog(module, ...args) {
    if (shouldLog(module, 'info')) {
        console.log(buildCopyFriendlyMessage(module, args));
    }
}

export function debugError(module, ...args) {
    if (shouldLog(module, 'error')) {
        console.error(buildCopyFriendlyMessage(module, args));
    }
}

export function debugWarn(module, ...args) {
    if (shouldLog(module, 'warn')) {
        console.warn(buildCopyFriendlyMessage(module, args));
    }
}

export function isDebugEnabled(module) {
    return shouldLog(module);
}

// Utility to enable/disable debugging for specific modules at runtime
export function setModuleDebug(module, enabled) {
    if (DEBUG_CONFIG.modules.hasOwnProperty(module)) {
        DEBUG_CONFIG.modules[module] = enabled;
        // Persist per-module flags so early loaders (non-module scripts) can read them too.
        try {
            localStorage.setItem(getModuleStorageKey(module), enabled ? '1' : '0');
        } catch (e) {
            // ignore
        }
        console.log(`Debug ${enabled ? 'enabled' : 'disabled'} for module: ${module}`);
    } else {
        console.warn(`Unknown module: ${module}`);
    }
}

// Utility to enable/disable specific debug levels at runtime
export function setDebugLevel(level, enabled) {
    if (DEBUG_CONFIG.levels.hasOwnProperty(level)) {
        DEBUG_CONFIG.levels[level] = enabled;
        console.log(`Debug level ${level} ${enabled ? 'enabled' : 'disabled'}`);
    } else {
        console.warn(`Unknown debug level: ${level}`);
    }
}

// Utility to enable/disable all debugging
export function setGlobalDebug(enabled) {
    DEBUG_CONFIG.global = enabled;
    console.log(`Global debugging ${enabled ? 'enabled' : 'disabled'}`);
}

// Debug function to scan all calculated total fields
export function debugCalculatedTotalFields() {
    // Only log if explicitly enabled via the global debug object
    if (!window.debug || !window.debug.isEnabled) {
        return;
    }

    console.log('=== DEBUG: Scanning all calculated total fields ===');

    const calculatedTotalFields = document.querySelectorAll('input[id*="total-calculated"]');
    console.log(`Found ${calculatedTotalFields.length} calculated total fields:`);

    calculatedTotalFields.forEach((field, index) => {
        const isVisible = field.offsetParent !== null && field.style.display !== 'none';
        const parentDiv = field.closest('div');
        const parentVisibility = parentDiv ? (parentDiv.offsetParent !== null && parentDiv.style.display !== 'none') : 'unknown';

        console.log(`  ${index + 1}. ID: ${field.id}, Visible: ${isVisible}, Parent Visible: ${parentVisibility}, Value: "${field.value}"`);

        // Find field ID from the calculated total field ID
        const fieldIdMatch = field.id.match(/total-calculated-(\d+)$/);
        if (fieldIdMatch) {
            const fieldId = fieldIdMatch[1];
            console.log(`    Field ID: ${fieldId}`);

            // Check if there are indirect reach fields for this field
            const indirectReachField = document.querySelector(`input[name*="${fieldId}_indirect_reach"]`);
            if (indirectReachField) {
                console.log(`    Has indirect reach field: ${indirectReachField.name}, Value: "${indirectReachField.value}"`);
            } else {
                console.log(`    No indirect reach field found`);
            }
        }
    });

    console.log('=== End calculated total fields scan ===');
}

// Plugin-specific debug utilities
export function debugPluginLog(pluginName, ...args) {
    if (shouldLog('plugins', 'info')) {
        const timestamp = new Date().toISOString().split('T')[1];
        console.log(`[PLUGIN ${timestamp}] [${pluginName}]`, ...args);
    }
}

export function debugPluginError(pluginName, ...args) {
    if (shouldLog('plugins', 'error')) {
        const timestamp = new Date().toISOString().split('T')[1];
        console.error(`[PLUGIN ERROR ${timestamp}] [${pluginName}]`, ...args);
    }
}

export function debugPluginWarn(pluginName, ...args) {
    if (shouldLog('plugins', 'warn')) {
        const timestamp = new Date().toISOString().split('T')[1];
        console.warn(`[PLUGIN WARN ${timestamp}] [${pluginName}]`, ...args);
    }
}

// Utility to enable/disable plugin debugging for specific plugins
export function setPluginDebug(pluginName, enabled) {
    if (enabled) {
        // Enable plugins module if not already enabled
        if (!DEBUG_CONFIG.modules.plugins) {
            DEBUG_CONFIG.modules.plugins = true;
        }
        console.log(`Plugin debugging enabled for: ${pluginName}`);
    } else {
        console.log(`Plugin debugging disabled for: ${pluginName}`);
    }
}

// Utility to enable all plugin debugging
export function enableAllPluginDebug() {
    DEBUG_CONFIG.modules.plugins = true;
    console.log('All plugin debugging enabled');
}

// Utility to disable all plugin debugging
export function disableAllPluginDebug() {
    DEBUG_CONFIG.modules.plugins = false;
    console.log('All plugin debugging disabled');
}

// Chatbot-specific debug utilities
export function debugChatbot(message, data = null) {
    if (shouldLog('chatbot', 'info')) {
        const timestamp = new Date().toISOString().split('T')[1];
        console.log(`[CHATBOT ${timestamp}]`, message, data || '');
    }
}

export function debugChatbotAPI(type, message, data = null) {
    if (shouldLog('chatbot-api', 'info')) {
        const timestamp = new Date().toISOString();
        const emoji = {
            'request': '🔵',
            'response': '✅',
            'error': '⚠️',
            'success': '🟢',
            'failure': '🔴',
            'fallback': '🟡'
        }[type] || 'ℹ️';

        console.group(`${emoji} [CHATBOT-API ${timestamp}] ${message}`);
        if (data) {
            if (typeof data === 'object') {
                Object.entries(data).forEach(([key, value]) => {
                    console.log(`${key}:`, value);
                });
            } else {
                console.log(data);
            }
        }
        console.groupEnd();
    }
}

export function debugChatbotContext(context) {
    if (shouldLog('chatbot-context', 'info')) {
        const timestamp = new Date().toISOString().split('T')[1];
        console.group(`📦 [CHATBOT-CONTEXT ${timestamp}] Page Context Collected`);
        console.log('Page Type:', context.pageData?.pageType || 'unknown');
        console.log('Current Page:', context.currentPage);
        console.log('Page Title:', context.pageTitle);
        console.log('UI Elements:', context.uiElements);
        console.log('Full Context:', context);
        console.groupEnd();
    }
}

export function enableChatbotDebug() {
    DEBUG_CONFIG.modules.chatbot = true;
    DEBUG_CONFIG.modules['chatbot-api'] = true;
    DEBUG_CONFIG.modules['chatbot-context'] = true;
    console.log('🐛 Chatbot Debug Mode: ENABLED (default)');
    console.log('Debug logs will show:');
    console.log('  • API request/response payloads');
    console.log('  • Page context collection');
    console.log('  • API availability status');
    console.log('  • Fallback usage');
    console.log('  • Performance metrics');
    console.log('\nNote: Chatbot debug is ON by default. To disable: window.debug.disableChatbot()');
}

export function disableChatbotDebug() {
    DEBUG_CONFIG.modules.chatbot = false;
    DEBUG_CONFIG.modules['chatbot-api'] = false;
    DEBUG_CONFIG.modules['chatbot-context'] = false;
    console.log('Chatbot Debug Mode: DISABLED');
}

// Example usage in console:
window.debug = {
    setModule: setModuleDebug,
    setLevel: setDebugLevel,
    setGlobal: setGlobalDebug,
    getConfig: () => DEBUG_CONFIG,
    scanCalculatedTotals: debugCalculatedTotalFields,
    isEnabled: false,  // Default to disabled
    enableScan: () => { window.debug.isEnabled = true; },
    disableScan: () => { window.debug.isEnabled = false; },
    // Plugin-specific utilities
    setPlugin: setPluginDebug,
    enableAllPlugins: enableAllPluginDebug,
    disableAllPlugins: disableAllPluginDebug,
    // Chatbot-specific utilities
    enableChatbot: enableChatbotDebug,
    disableChatbot: disableChatbotDebug,
    chatbot: debugChatbot,
    chatbotAPI: debugChatbotAPI,
    chatbotContext: debugChatbotContext
};
