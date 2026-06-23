/**
 * Re-export HumDatabankChatbot for tests and legacy imports.
 * @module chatbot/export
 */
export { HumDatabankChatbot } from './core.js';
export default HumDatabankChatbot;

if (typeof module !== 'undefined' && module.exports) {
    module.exports = HumDatabankChatbot;
}
