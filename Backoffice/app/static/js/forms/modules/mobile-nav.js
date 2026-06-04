/**
 * Legacy entry point — mobile nav is handled by sidebar-collapse.js.
 * Kept so existing imports from main.js remain valid.
 */
export { closeEntryFormMobileNav as closeMobileNav } from './sidebar-collapse.js';

export function initMobileNav() {
  // sidebar-collapse.js auto-initializes on DOMContentLoaded.
}
