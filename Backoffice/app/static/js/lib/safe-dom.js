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

  const DANGEROUS_TAGS = new Set([
    'script', 'iframe', 'object', 'embed', 'form', 'input', 'button',
    'textarea', 'link', 'style', 'base', 'meta',
  ]);

  const DANGEROUS_HREF_PROTOCOLS = /^(javascript|vbscript|data):/i;

  /**
   * DOMParser-based HTML sanitizer — strips dangerous elements, event
   * handlers, style attributes, and unsafe href protocols.
   *
   * Use for defense-in-depth whenever server-rendered HTML partials or
   * JSON-supplied HTML fragments are assigned to innerHTML / outerHTML /
   * insertAdjacentHTML.  Not intended for Markdown→HTML (chatbot has its
   * own richer pipeline); this is the general-purpose safety net.
   */
  function sanitizeHtml(html) {
    if (!html) return '';
    var doc;
    try {
      doc = new DOMParser().parseFromString(String(html), 'text/html');
    } catch (_) {
      return '';
    }
    var body = doc.body;
    if (!body) return '';

    // 1. Remove dangerous elements entirely
    DANGEROUS_TAGS.forEach(function (tag) {
      var els = body.querySelectorAll(tag);
      for (var i = els.length - 1; i >= 0; i--) els[i].remove();
    });

    // 2. Walk all surviving elements
    var all = body.querySelectorAll('*');
    for (var i = all.length - 1; i >= 0; i--) {
      var el = all[i];
      for (var j = el.attributes.length - 1; j >= 0; j--) {
        var attr = el.attributes[j];
        var name = attr.name.toLowerCase();

        // Remove event handlers (onclick, onerror, …)
        if (name.startsWith('on')) {
          el.removeAttribute(attr.name);
          continue;
        }

        // Remove style attributes (CSS-based exfil / expression())
        if (name === 'style') {
          el.removeAttribute(attr.name);
          continue;
        }

        // Sanitize href / src / action protocols
        if (name === 'href' || name === 'src' || name === 'action') {
          var val = (attr.value || '').replace(/[\s\x00-\x1f]/g, '');
          if (DANGEROUS_HREF_PROTOCOLS.test(val)) {
            el.removeAttribute(attr.name);
          }
        }
      }
    }

    return body.innerHTML;
  }

  window.SafeDom = {
    escapeHtml,
    escapeHtmlAttr,
    sanitizeHtml,
    safeUrl,
    navigate,
    setText,
    setAttr,
  };

  // Global aliases so templates don't need to repeat local definitions
  if (!window.escapeHtml) window.escapeHtml = escapeHtml;
  if (!window.escapeHtmlAttr) window.escapeHtmlAttr = escapeHtmlAttr;
  if (!window.sanitizeHtml) window.sanitizeHtml = sanitizeHtml;
})();
