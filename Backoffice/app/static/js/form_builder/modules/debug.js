/**
 * Form Builder debug utilities
 *
 * Intentionally separate from `/static/js/forms/modules/debug.js` (entry-form only).
 * Exposes `window.formBuilderDebug` with per-module toggles + levels + persistence.
 */

const DEBUG_CONFIG = {
  global: true, // Master switch for all form builder debugging
  modules: {
    // Loader/resource timing
    'form-builder-loader': true,

    // Common areas (default off; enable as needed)
    'csrf-handler': false,
    'data-manager': false,
    'item-modal': false,
    'calculated-lists': false,
    'conditions': false,
    'dynamic-sections': false,
    'form-submit-ui': false,
    'translation': false,
    'ui': false
  },
  levels: {
    info: true,
    warn: true,
    error: true
  }
};

const STORAGE_PREFIX = 'ifrc:form_builder:debug:module:';

function getModuleStorageKey(module) {
  return `${STORAGE_PREFIX}${module}`;
}

function applyPersistedModuleFlags() {
  try {
    // Apply persisted flags for known modules
    Object.keys(DEBUG_CONFIG.modules).forEach((module) => {
      const raw = localStorage.getItem(getModuleStorageKey(module));
      if (raw === '1') DEBUG_CONFIG.modules[module] = true;
      if (raw === '0') DEBUG_CONFIG.modules[module] = false;
    });
  } catch (_e) {
    // no-op
  }
}

// Apply persisted module flags immediately on module load
applyPersistedModuleFlags();

export function initFormBuilderDebug(config = {}) {
  // Back-compat: allow { enabled: false } as master global disable.
  if (config.enabled === false) {
    DEBUG_CONFIG.global = false;
    return;
  }

  if (config.global !== undefined) {
    DEBUG_CONFIG.global = !!config.global;
  }

  if (config.modules && typeof config.modules === 'object') {
    Object.assign(DEBUG_CONFIG.modules, config.modules);
  }

  if (config.levels && typeof config.levels === 'object') {
    Object.assign(DEBUG_CONFIG.levels, config.levels);
  }
}

function shouldLog(module, level = 'info') {
  return !!(
    DEBUG_CONFIG.global &&
    DEBUG_CONFIG.levels[level] &&
    DEBUG_CONFIG.modules[module]
  );
}

function timestamp() {
  try {
    return new Date().toISOString().split('T')[1];
  } catch (_e) {
    return '';
  }
}

export function debugLog(module, ...args) {
  if (shouldLog(module, 'info')) {
    // eslint-disable-next-line no-console
    console.log(`[FB-DEBUG ${timestamp()}] [${module}]`, ...args);
  }
}

export function debugWarn(module, ...args) {
  if (shouldLog(module, 'warn')) {
    // eslint-disable-next-line no-console
    console.warn(`[FB-WARN ${timestamp()}] [${module}]`, ...args);
  }
}

export function debugError(module, ...args) {
  if (shouldLog(module, 'error')) {
    // eslint-disable-next-line no-console
    console.error(`[FB-ERROR ${timestamp()}] [${module}]`, ...args);
  }
}

export function isDebugEnabled(module, level = 'info') {
  return shouldLog(module, level);
}

export function setModuleDebug(module, enabled) {
  // Allow "any module": if unknown, create it.
  if (!Object.prototype.hasOwnProperty.call(DEBUG_CONFIG.modules, module)) {
    DEBUG_CONFIG.modules[module] = false;
  }
  DEBUG_CONFIG.modules[module] = !!enabled;
  try {
    localStorage.setItem(getModuleStorageKey(module), enabled ? '1' : '0');
  } catch (_e) {
    // ignore
  }
}

export function setDebugLevel(level, enabled) {
  if (Object.prototype.hasOwnProperty.call(DEBUG_CONFIG.levels, level)) {
    DEBUG_CONFIG.levels[level] = !!enabled;
  }
}

export function setGlobalDebug(enabled) {
  DEBUG_CONFIG.global = !!enabled;
}

export function getConfig() {
  return DEBUG_CONFIG;
}

function safeNow() {
  try {
    return (performance && typeof performance.now === 'function') ? performance.now() : Date.now();
  } catch (_e) {
    return Date.now();
  }
}

function sourceHintFromTiming(entry) {
  // transferSize === 0 often indicates cache (memory/disk),
  // but can also be 0 for other cases (e.g., opaque responses).
  if (typeof entry.transferSize === 'number') {
    if (entry.transferSize === 0) return 'cache/0';
    if (entry.transferSize > 0) return 'network';
  }
  return 'unknown';
}

function collectJsResourceRows() {
  if (!performance || !performance.getEntriesByType) return [];
  const entries = performance.getEntriesByType('resource') || [];

  return entries
    .filter(e => typeof e.name === 'string')
    .filter(e =>
      e.name.includes('/static/js/form_builder/') ||
      e.name.includes('/static/js/components/')
    )
    .map(e => ({
      name: e.name.split('?')[0],
      initiatorType: e.initiatorType,
      source: sourceHintFromTiming(e),
      transferKB: (typeof e.transferSize === 'number') ? Math.round(e.transferSize / 1024) : undefined,
      decodedKB: (typeof e.decodedBodySize === 'number') ? Math.round(e.decodedBodySize / 1024) : undefined,
      durationMs: (typeof e.duration === 'number') ? Math.round(e.duration) : undefined
    }));
}

export function logResourceTimingTable() {
  if (!shouldLog('form-builder-loader', 'info')) return;

  const start = safeNow();
  setTimeout(() => {
    try {
      const rows = collectJsResourceRows();
      const elapsed = Math.round(safeNow() - start);
      // eslint-disable-next-line no-console
      console.groupCollapsed(`[form-builder-loader] JS resources (${rows.length}) after ~${elapsed}ms`);
      // eslint-disable-next-line no-console
      console.table(rows);
      // eslint-disable-next-line no-console
      console.groupEnd();
    } catch (e) {
      // eslint-disable-next-line no-console
      console.debug('[form-builder-loader] failed to read resource timing', e);
    }
  }, 0);
}

// Expose a dedicated global debug controller for the form builder.
// (Do NOT overwrite `window.debug` which is used by entry forms.)
try {
  window.formBuilderDebug = {
    setModule: setModuleDebug,
    setLevel: setDebugLevel,
    setGlobal: setGlobalDebug,
    getConfig,
    isEnabled: isDebugEnabled,
    logResources: logResourceTimingTable,
    log: debugLog,
    warn: debugWarn,
    error: debugError
  };
} catch (_e) {
  // no-op
}
