/**
 * Replace plugin label variables (e.g. [EO1], [EO2], [EO3]) in section/item labels
 * with values from plugin fields' data attributes (data-eo1, data-eo2, data-eo3).
 * Plugin fields set these attributes when they load (e.g. Emergency Operations plugin).
 * Runs after DOM ready and on plugin update events so labels update when plugin data arrives.
 * Stores original text per node (WeakMap) so we can re-apply when plugin loads and updates values.
 */

const originalTextByNode = new WeakMap();

// Cache latest values from plugin events so we don't depend on DOM order.
let lastValues = null;

const PLACEHOLDER_RE = /\[(EO1|EO2|EO3)\]/;

function getValuesFromElement(el) {
  if (!el || typeof el.getAttribute !== 'function') return null;
  return {
    EO1: el.getAttribute('data-eo1') || '',
    EO2: el.getAttribute('data-eo2') || '',
    EO3: el.getAttribute('data-eo3') || ''
  };
}

function pickBestSourceElement() {
  const candidates = Array.from(document.querySelectorAll('[data-eo1], [data-eo2], [data-eo3]'));
  if (!candidates.length) return null;

  const withEO1 = candidates.find((el) => String(el.getAttribute('data-eo1') || '').trim() !== '');
  if (withEO1) return withEO1;

  const withCount = candidates.find((el) => {
    const c = parseFloat(el.getAttribute('data-operations-count') || '');
    return !Number.isNaN(c) && c > 0;
  });
  return withCount || candidates[0];
}

function getPluginVariableValues(evt) {
  // If called from a plugin event, prefer its target (most accurate).
  try {
    if (evt && evt.target && typeof evt.target.getAttribute === 'function') {
      const v = getValuesFromElement(evt.target);
      if (v) {
        lastValues = v;
        return v;
      }
    }
  } catch (_e) {
    // ignore
  }

  // Otherwise use cache or best DOM candidate.
  if (lastValues) return lastValues;
  const el = pickBestSourceElement();
  if (!el) return null;
  lastValues = getValuesFromElement(el);
  return lastValues;
}

function shouldConsiderTextNode(node) {
  if (!node) return false;
  const t = node.textContent;
  if (!t || t.indexOf('[EO') === -1) return false;
  if (!PLACEHOLDER_RE.test(t)) return false;

  const p = node.parentElement;
  if (!p) return false;
  const tag = p.tagName;
  if (tag === 'SCRIPT' || tag === 'STYLE') return false;
  if (tag === 'TEXTAREA') return false;
  if (tag === 'INPUT') return false;
  return true;
}

function replaceInElement(el, values) {
  if (!el || !values) return;
  // Fast pre-check to avoid TreeWalker setup when there are no placeholders at all.
  try {
    const tc = el.textContent || '';
    if (tc.indexOf('[EO') === -1) return;
  } catch (_e) {
    return;
  }

  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, {
    acceptNode: function (node) {
      return shouldConsiderTextNode(node) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
    }
  });

  while (walker.nextNode()) {
    const node = walker.currentNode;
    let t = originalTextByNode.get(node);
    if (t === undefined) {
      t = node.textContent || '';
      originalTextByNode.set(node, t);
    }

    // Only replace when we have a non-empty value; otherwise leave [EO1] etc. in place
    // so that when the plugin loads later we can replace with "Name (CODE)".
    const result = t
      .replace(/\[EO1\]/g, values.EO1 != null && String(values.EO1).trim() !== '' ? values.EO1 : '[EO1]')
      .replace(/\[EO2\]/g, values.EO2 != null && String(values.EO2).trim() !== '' ? values.EO2 : '[EO2]')
      .replace(/\[EO3\]/g, values.EO3 != null && String(values.EO3).trim() !== '' ? values.EO3 : '[EO3]');

    if (node.textContent !== result) node.textContent = result;
  }
}

function getCandidateRoots() {
  // Restrict work to likely label areas (sidebar nav, section headings, and field labels).
  // Avoid scanning the entire document body: large entry forms can have thousands of text nodes.
  const selectors = [
    '#section-navigation-sidebar .section-link span',
    '#entry-form-ui h1, #entry-form-ui h2, #entry-form-ui h3, #entry-form-ui h4',
    '#entry-form-ui label',
    '#entry-form-ui .form-item-block p'
  ];
  try {
    return Array.from(document.querySelectorAll(selectors.join(', ')));
  } catch (_e) {
    return [];
  }
}

function replacePluginLabelVariablesInPage(evt) {
  const values = getPluginVariableValues(evt);
  if (!values) return;

  // Publish variables to the generic registry (window.__ifrcPluginVariables) so other systems
  // (e.g. conditions.js relevance evaluation) can read plugin-provided variables.
  //
  // GUARD: only publish when the source plugin has been marked data-ready.
  // If we publish placeholder empty values (EO1='', EO2='', EO3='') before real data arrives,
  // conditions.js isDepsReadyNow() treats '' as "defined" (not null) and unlocks evaluation
  // prematurely — causing sections to be evaluated with stale empty variable values.
  //
  // NOTE: emergency_operations_field.js now also publishes synchronously inside
  // updateOperationsVariables(), which is the primary fix. This guard is a defensive layer
  // for any other code path that might call this function before the plugin is ready.
  try {
    const sourceEl = pickBestSourceElement();
    const isSourceReady = sourceEl
      ? String(sourceEl.getAttribute('data-plugin-data-ready') || '').toLowerCase() === 'true'
      : false;

    if (isSourceReady) {
      window.__ifrcPluginVariables = window.__ifrcPluginVariables || {};
      const prev = window.__ifrcPluginVariables;
      window.__ifrcPluginVariables = { ...prev, ...values };
      document.dispatchEvent(new CustomEvent('pluginVariablesUpdated', {
        detail: { variables: Object.keys(values || {}) },
        bubbles: false
      }));
    }
    // When not ready: skip publishing to __ifrcPluginVariables so conditions wait for real data.
    // The text replacement below still runs so labels that are already visible update correctly.
  } catch (_e) {
    // ignore
  }

  const roots = getCandidateRoots();
  for (const el of roots) {
    replaceInElement(el, values);
  }
}

function initPluginLabelVariableReplacement() {
  // Debounce so bursty plugin updates don't trigger repeated work.
  let scheduled = false;
  const schedule = (evt) => {
    if (scheduled) return;
    scheduled = true;
    setTimeout(() => {
      scheduled = false;
      replacePluginLabelVariablesInPage(evt);
    }, 0);
  };

  schedule();
  document.addEventListener('operationsCountUpdated', (e) => schedule(e));

  // Watch for EO attribute updates (some plugins may set attributes without emitting an event).
  try {
    const observer = new MutationObserver((mutations) => {
      for (const m of mutations) {
        if (m.type === 'attributes' && m.target) {
          const attr = m.attributeName || '';
          if (attr === 'data-eo1' || attr === 'data-eo2' || attr === 'data-eo3' || attr === 'data-operations-count') {
            schedule({ target: m.target });
            break;
          }
        }
      }
    });
    observer.observe(document.body, {
      subtree: true,
      attributes: true,
      attributeFilter: ['data-eo1', 'data-eo2', 'data-eo3', 'data-operations-count']
    });
  } catch (_e) {
    // ignore
  }

  // One short delayed run to catch late DOM insertions during initial hydration.
  setTimeout(() => schedule(), 1200);
}

export { replacePluginLabelVariablesInPage, getPluginVariableValues, initPluginLabelVariableReplacement };
