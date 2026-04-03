/**
 * Entry form bootstrap
 *
 * Goal: reduce top-level <script type="module"> tags in the template and ensure
 * the full dependency graph is fetched/validated together. If any import fails,
 * the entry module fails and our retry loader in the template can retry.
 *
 * Note: many modules self-initialize on DOMContentLoaded; importing them here is enough.
 */

// Enable verbose module/resource logging by:
// - URL: ?debugModules=1
// - Console (persisted): window.debug.setModule('forms-loader', true); then reload
const DEBUG_MODULES = (() => {
  try {
    const url = new URL(window.location.href);
    // Back-compat: ifrc:debugModules=1
    const legacy = localStorage.getItem('ifrc:debugModules') === '1';
    const persisted = localStorage.getItem('ifrc:debug:module:forms-loader') === '1';
    // If debug.js already loaded, prefer its config (but keep localStorage for early boot clarity)
    const cfg = (window.debug && typeof window.debug.getConfig === 'function')
      ? !!(window.debug.getConfig().modules && window.debug.getConfig().modules['forms-loader'])
      : false;
    return url.searchParams.get('debugModules') === '1' || legacy || persisted || cfg;
  } catch (e) {
    return false;
  }
})();

// Formatting should be available as early as possible (runs immediately + observers)
import './modules/numeric-formatting.js';

// Sidebar UX / navigation
import './modules/sidebar-collapse.js';
import './modules/section-nav-scroll.js';
import './modules/pagination.js';

// Presence + collapsible are used by the entry form UI
import './modules/presence.js';
import './modules/collapsible.js';

// Plugin fields are rendered client-side on entry forms
import './plugin-field-loader.js';

// Local drafts for authenticated forms
import './modules/auth-drafts.js';

// Main form initialization (sets document.body.dataset.formInitialized = 'true' when done)
import './main.js';

// Replace plugin label variables ([EO1], [EO2], [EO3]) in section/item labels after plugin fields set data-eo1 etc.
import { initPluginLabelVariableReplacement } from './modules/plugin-label-variables.js';
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initPluginLabelVariableReplacement);
} else {
  initPluginLabelVariableReplacement();
}

// After imports resolve and the module evaluates, we can report what was fetched.
if (DEBUG_MODULES) {
  // eslint-disable-next-line no-console
  console.debug('[forms-loader] entry-form.js evaluated; collecting resource timing…');

  // Give the browser a moment to populate performance entries for module graph requests.
  setTimeout(() => {
    try {
      if (!performance || !performance.getEntriesByType) return;
      const entries = performance.getEntriesByType('resource') || [];

      const rows = entries
        .filter(e => typeof e.name === 'string' && e.name.includes('/static/js/forms/'))
        .map(e => ({
          name: e.name.split('?')[0],
          initiatorType: e.initiatorType,
          // transferSize==0 often indicates cache (memory/disk) but can be 0 for other reasons; still useful as a hint.
          source: (typeof e.transferSize === 'number')
            ? (e.transferSize === 0 ? 'cache' : 'network')
            : 'unknown',
          transferKB: (typeof e.transferSize === 'number') ? Math.round(e.transferSize / 1024) : undefined,
          decodedKB: (typeof e.decodedBodySize === 'number') ? Math.round(e.decodedBodySize / 1024) : undefined,
          durationMs: (typeof e.duration === 'number') ? Math.round(e.duration) : undefined
        }));

      // eslint-disable-next-line no-console
      console.groupCollapsed(`[forms-loader] /static/js/forms/* resources (${rows.length})`);
      // eslint-disable-next-line no-console
      console.table(rows);
      // eslint-disable-next-line no-console
      console.groupEnd();
    } catch (e) {
      // eslint-disable-next-line no-console
      console.debug('[forms-loader] failed to read resource timing', e);
    }
  }, 0);
}
