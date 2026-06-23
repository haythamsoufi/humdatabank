/**
 * Chatbot entry point — initializes HumDatabankChatbot and global helpers.
 * @module chatbot/main
 */

import { HumDatabankChatbot } from './core.js';
import { registerStructuredPayloadListener } from './structured-payloads.js';

const chatbot = new HumDatabankChatbot();

try {
    if (window.debug && window.debug.getConfig && window.debug.getConfig().modules.chatbot) {
        console.log('[Chatbot tables] chatbot/main.js loaded; HumDatabankChatbot initialized');
    }
} catch (e) { /* debug not loaded */ }

window.humdatabankChatbot = chatbot;

window.setChatbotLanguage = function (language) {
    if (window.humdatabankChatbot) {
        window.humdatabankChatbot.setLanguagePreference(language);
        return `Language preference set to: ${language}`;
    }
    return 'Chatbot not initialized';
};

window.getChatbotLanguage = function () {
    if (window.humdatabankChatbot) {
        return window.humdatabankChatbot.preferredLanguage;
    }
    return 'Chatbot not initialized';
};

window.resetChatbotLaptopPreference = function () {
    if (window.humdatabankChatbot) {
        window.humdatabankChatbot.resetLaptopPreference();
        return 'Laptop auto-expansion preference reset.';
    }
    return 'Chatbot not initialized';
};

window.enableChatbotDebug = function () {
    if (window.debug && window.debug.enableChatbot) {
        window.debug.enableChatbot();
        window.CHATBOT_DEBUG = true;
        console.log('✅ Chatbot debug enabled via centralized debug.js');
        console.log('Tip: Use window.debug.enableChatbot() directly in the future');
        return true;
    }
    console.warn('Centralized debug system not loaded yet. Debug.js should be loaded before chatbot/main.js');
    return false;
};

window.disableChatbotDebug = function () {
    if (window.debug && window.debug.disableChatbot) {
        window.debug.disableChatbot();
        window.CHATBOT_DEBUG = false;
        return true;
    }
    console.warn('Centralized debug system not loaded yet');
    return false;
};

window.getChatbotAPIStatus = function () {
    if (window.humdatabankChatbot) {
        const status = window.humdatabankChatbot.getAPIStatus();
        console.table(status);
        return status;
    }
    console.warn('Chatbot not initialized');
    return null;
};

window.getChatbotMessages = function () {
    if (window.humdatabankChatbot) {
        console.log('Loaded Messages:', window.humdatabankChatbot.messages);
        return window.humdatabankChatbot.messages;
    }
    console.warn('Chatbot not initialized');
    return null;
};

registerStructuredPayloadListener();

export { HumDatabankChatbot, chatbot };
export default chatbot;
