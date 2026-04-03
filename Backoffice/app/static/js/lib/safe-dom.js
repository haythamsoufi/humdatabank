// safe-dom.js
// Small, dependency-free helpers for CSP-safe DOM updates and safe navigation.
// Exposes: window.SafeDom

(function () {
  'use strict';

  const DISALLOWED_PROTOCOLS = new Set(['javascript:', 'data:', 'vbscript:']);

  function toString(value) {
    if (value === null || value === undefined) return '';
    return String(value);
  }

  function escapeHtml(value) {
    // Only use when you must build HTML strings. Prefer textContent.
    const s = toString(value);
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
  }

  function safeUrl(value, options) {
    // Returns a normalized same-origin URL string, or '' if unsafe.
    // options: { allowRelativeOnly?: boolean, allowSameOrigin?: boolean, allowPaths?: string[] }
    const opts = options || {};
    const raw = toString(value).trim();
    if (!raw || raw === 'None') return '';

    // Quick reject obvious schemes
    const lower = raw.toLowerCase();
    for (const proto of DISALLOWED_PROTOCOLS) {
      if (lower.startsWith(proto)) return '';
    }

    let url;
    try {
      url = new URL(raw, window.location.origin);
    } catch (_) {
      return '';
    }

    const allowSameOrigin = opts.allowSameOrigin !== false; // default true
    if (allowSameOrigin && url.origin !== window.location.origin) return '';

    const allowRelativeOnly = opts.allowRelativeOnly === true;
    if (allowRelativeOnly) {
      // Ensure the original didn't include a scheme/host
      if (/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(raw)) return '';
      if (raw.startsWith('//')) return '';
    }

    const allowPaths = Array.isArray(opts.allowPaths) ? opts.allowPaths : null;
    if (allowPaths && allowPaths.length > 0) {
      const ok = allowPaths.some((p) => url.pathname.startsWith(p));
      if (!ok) return '';
    }

    // Preserve the user's original relative string if it was relative and safe
    if (!/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(raw) && !raw.startsWith('//')) {
      return raw;
    }
    return url.toString();
  }

  function navigate(urlValue, options) {
    const u = safeUrl(urlValue, options);
    if (!u) return false;
    window.location.href = u;
    return true;
  }

  function setText(el, value) {
    if (!el) return;
    el.textContent = toString(value);
  }

  function setAttr(el, name, value) {
    if (!el) return;
    const v = toString(value);
    if (!v) {
      el.removeAttribute(name);
    } else {
      el.setAttribute(name, v);
    }
  }

  function escapeHtmlAttr(value) {
    return toString(value)
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  window.SafeDom = {
    escapeHtml,
    escapeHtmlAttr,
    safeUrl,
    navigate,
    setText,
    setAttr,
  };

  // Global aliases so templates don't need to repeat local definitions
  if (!window.escapeHtml) window.escapeHtml = escapeHtml;
  if (!window.escapeHtmlAttr) window.escapeHtmlAttr = escapeHtmlAttr;
})();
