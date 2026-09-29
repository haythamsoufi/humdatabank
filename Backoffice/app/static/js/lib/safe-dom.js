// safe-dom.js
// Small, dependency-free helpers for CSP-safe DOM updates and safe navigation.
// Exposes: window.SafeDom
//
// Contract (see docs/DEVELOPER-HANDBOOK.md, "Safe primitives"):
//   * text        -> el.textContent / SafeDom.setText
//   * URLs        -> SafeDom.safeUrl / setHref / setSrc / safeHrefAttr / navigate / openWindow
//   * HTML strings-> SafeDom.html`...` (escapes every ${} value) then SafeDom.setHtml(el, ...)
//                    or SafeDom.setHtml(el, untrustedString) (sanitised via sanitizeHtml)
// Callers must never fall back to identity when SafeDom is missing; use escapeHtml / deny.

(function () {
  'use strict';

  const DEFAULT_URL_SCHEMES = ['http:', 'https:'];
  const CONTROL_CHARS = /[\u0000-\u001f\u007f-\u009f\u2028\u2029]/;
  const SCHEME_PREFIX = /^[a-zA-Z][a-zA-Z0-9+.-]*:/;

  function toString(value) {
    if (value === null || value === undefined) return '';
    return String(value);
  }

  function escapeHtml(value) {
    // Escapes & < > " ' so the result is safe in text nodes AND quoted attribute values.
    // Prefer textContent when you do not need an HTML string.
    return toString(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function safeUrl(value, options) {
    // Returns a normalised URL string, or '' if unsafe.
    // options: {
    //   allowRelativeOnly?: boolean,  // reject anything carrying a scheme or host
    //   allowSameOrigin?: boolean,    // default true: absolute URLs must match this origin;
    //                                 // false permits any host but still only allowed schemes
    //   allowSchemes?: string[],      // extra schemes such as ['mailto:', 'tel:'] (default http/https)
    //   allowPaths?: string[]
    // }
    const opts = options || {};
    const raw = toString(value).trim();
    if (!raw || raw === 'None') return '';

    // Control characters / tabs / newlines are stripped by URL parsers ("java\tscript:"),
    // and backslashes are treated as slashes by browsers ("/\\evil.com"): reject both.
    if (CONTROL_CHARS.test(raw) || raw.indexOf('\\') !== -1) return '';

    // Entity-obfuscated schemes ("jav&#x61;script:") become live once embedded in an HTML string.
    if (raw.indexOf('&') !== -1) {
      const decoded = decodeHtmlEntities(raw);
      if (decoded !== raw && !safeUrl(decoded, options)) return '';
    }

    const hasScheme = SCHEME_PREFIX.test(raw);
    const protocolRelative = raw.startsWith('//');

    let url;
    try {
      url = new URL(raw, window.location.origin);
    } catch (_) {
      return '';
    }

    const allowedSchemes = DEFAULT_URL_SCHEMES.concat(
      Array.isArray(opts.allowSchemes)
        ? opts.allowSchemes.map((x) => toString(x).toLowerCase())
        : []
    );
    if (allowedSchemes.indexOf(url.protocol.toLowerCase()) === -1) return '';

    const isWebScheme = url.protocol === 'http:' || url.protocol === 'https:';
    const allowSameOrigin = opts.allowSameOrigin !== false; // default true
    if (isWebScheme && allowSameOrigin && url.origin !== window.location.origin) return '';

    if (opts.allowRelativeOnly === true && (hasScheme || protocolRelative)) return '';

    const allowPaths = Array.isArray(opts.allowPaths) ? opts.allowPaths : null;
    if (allowPaths && allowPaths.length > 0) {
      const ok = allowPaths.some((p) => url.pathname.startsWith(p));
      if (!ok) return '';
    }

    // Preserve the caller's original relative string if it was relative and safe
    if (!hasScheme && !protocolRelative) return raw;
    return url.toString();
  }

  function safeHrefAttr(value, options) {
    // Attribute-ready string: safe URL (or '#') with all HTML metacharacters escaped.
    return escapeHtml(safeUrl(value, options) || '#');
  }

  function setHref(el, value, options) {
    if (!el) return false;
    const u = safeUrl(value, options);
    if (!u) {
      el.removeAttribute('href');
      return false;
    }
    el.setAttribute('href', u);
    return true;
  }

  function setSrc(el, value, options) {
    if (!el) return false;
    const u = safeUrl(value, options);
    if (!u) {
      el.removeAttribute('src');
      return false;
    }
    el.setAttribute('src', u);
    return true;
  }

  function openWindow(value, options) {
    const u = safeUrl(value, options);
    if (!u) return null;
    return window.open(u, '_blank', 'noopener,noreferrer');
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

  const URL_ATTRS = new Set(['href', 'src', 'action', 'formaction', 'xlink:href', 'poster', 'background']);

  function setAttr(el, name, value) {
    if (!el) return;
    const attrName = toString(name).toLowerCase();
    if (attrName.startsWith('on') || attrName === 'srcdoc') return;
    const v = URL_ATTRS.has(attrName) ? safeUrl(value) : toString(value);
    if (!v) {
      el.removeAttribute(name);
    } else {
      el.setAttribute(name, v);
    }
  }

  function escapeHtmlAttr(value) {
    return toString(value)
      .replace(/&/g, '&amp;')
      .replace(/\\/g, '\\\\')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  /** Escape a value for use inside a CSS attribute selector ([name="…"]). */
  function escapeCssSelector(value) {
    try {
      if (window.CSS && typeof window.CSS.escape === 'function') {
        return window.CSS.escape(toString(value));
      }
    } catch (_) { /* ignore */ }
    return toString(value)
      .replace(/\\/g, '\\\\')
      .replace(/"/g, '\\"');
  }

  /** Decode HTML entities without assigning untrusted HTML via innerHTML. */
  function decodeHtmlEntities(value) {
    const raw = toString(value);
    if (!raw) return '';
    try {
      const doc = new DOMParser().parseFromString(raw, 'text/html');
      return doc.documentElement.textContent || '';
    } catch (_) {
      return raw;
    }
  }

  const DANGEROUS_TAGS = new Set([
    'script', 'iframe', 'frame', 'frameset', 'object', 'embed', 'applet', 'portal',
    'form', 'link', 'style', 'base', 'meta', 'math', 'template',
  ]);
  const CONTROL_TAGS = ['input', 'button', 'textarea', 'select', 'option'];

  const DANGEROUS_ATTRS = new Set(['style', 'srcdoc', 'formaction', 'ping', 'is']);
  const SANITIZER_URL_ATTRS = new Set(['href', 'src', 'action', 'xlink:href', 'poster', 'background', 'cite']);
  const SANITIZER_URL_SCHEMES = ['http:', 'https:', 'mailto:', 'tel:'];

  function isSafeSanitizerUrl(value) {
    // Strip everything the URL parser ignores before looking at the scheme.
    const compact = toString(value).replace(/[\s\u0000-\u001f\u007f-\u009f\u2028\u2029]/g, '');
    if (!compact) return true;
    if (/^\/?\\/.test(compact)) return false;
    const m = SCHEME_PREFIX.exec(compact);
    if (!m) return true;
    return SANITIZER_URL_SCHEMES.indexOf(m[0].toLowerCase()) !== -1;
  }

  /**
   * DOMParser-based HTML sanitizer — strips dangerous elements, event
   * handlers, style attributes, and any URL attribute whose scheme is not
   * http(s)/mailto/tel (relative URLs are kept).
   *
   * Use for defense-in-depth whenever server-rendered HTML partials or
   * JSON-supplied HTML fragments are assigned to innerHTML / outerHTML /
   * insertAdjacentHTML.  Not intended for Markdown→HTML (chatbot has its
   * own richer pipeline); this is the general-purpose safety net.
   *
   * options.allowControls keeps input/button/textarea/select/option (needed for
   * plugin configuration fragments); <form> is always removed.
   */
  function sanitizeHtml(html, options) {
    var allowControls = !!(options && options.allowControls);
    if (!html) return '';
    var doc;
    try {
      doc = new DOMParser().parseFromString(String(html), 'text/html');
    } catch (_) {
      return '';
    }
    var body = doc.body;
    if (!body) return '';

    var removeTags = allowControls ? Array.from(DANGEROUS_TAGS) : Array.from(DANGEROUS_TAGS).concat(CONTROL_TAGS);
    removeTags.forEach(function (tag) {
      var els = body.querySelectorAll(tag);
      for (var i = els.length - 1; i >= 0; i--) els[i].remove();
    });

    var all = body.querySelectorAll('*');
    for (var i = all.length - 1; i >= 0; i--) {
      var el = all[i];
      for (var j = el.attributes.length - 1; j >= 0; j--) {
        var attr = el.attributes[j];
        var name = attr.name.toLowerCase();

        if (name.startsWith('on') || DANGEROUS_ATTRS.has(name)) {
          el.removeAttribute(attr.name);
          continue;
        }

        if (SANITIZER_URL_ATTRS.has(name) && !isSafeSanitizerUrl(attr.value)) {
          el.removeAttribute(attr.name);
        }
      }
      if (el.tagName === 'A' && (el.getAttribute('target') || '').toLowerCase() === '_blank') {
        el.setAttribute('rel', 'noopener noreferrer');
      }
    }

    return body.innerHTML;
  }

  function SafeHtml(value) {
    this.value = value;
  }
  SafeHtml.prototype.toString = function () { return this.value; };

  function isSafeHtml(value) {
    return value instanceof SafeHtml;
  }

  /** Mark a string as already-safe HTML. Only for literals or output of html`` / sanitizeHtml. */
  function raw(value) {
    return new SafeHtml(toString(value));
  }

  /**
   * Tagged template that escapes every interpolated value (text and attribute
   * safe). Nested html`` results and raw() values are inserted verbatim; arrays
   * are joined after per-item handling. URL attributes must still use
   * safeHrefAttr(): html`<a href="${SafeDom.safeHrefAttr(u)}">`.
   */
  function html(strings) {
    var out = strings[0];
    for (var i = 1; i < arguments.length; i++) {
      var v = arguments[i];
      var part;
      if (isSafeHtml(v)) {
        part = v.value;
      } else if (Array.isArray(v)) {
        part = v.map(function (item) { return isSafeHtml(item) ? item.value : escapeHtml(item); }).join('');
      } else {
        part = escapeHtml(v);
      }
      out += part + strings[i];
    }
    return new SafeHtml(out);
  }

  /**
   * Assign markup to an element. SafeHtml (from html``/raw) is assigned as is;
   * plain strings are treated as untrusted and sanitised first.
   */
  function setHtml(el, value, options) {
    if (!el) return;
    el.innerHTML = isSafeHtml(value) ? value.value : sanitizeHtml(value, options);
  }

  window.SafeDom = {
    escapeHtml,
    escapeHtmlAttr,
    escapeCssSelector,
    decodeHtmlEntities,
    sanitizeHtml,
    safeUrl,
    safeHrefAttr,
    setHref,
    setSrc,
    openWindow,
    html,
    raw,
    isSafeHtml,
    setHtml,
    navigate,
    setText,
    setAttr,
  };

  // Global aliases so templates don't need to repeat local definitions
  if (!window.escapeHtml) window.escapeHtml = escapeHtml;
  if (!window.escapeHtmlAttr) window.escapeHtmlAttr = escapeHtmlAttr;
  if (!window.escapeCssSelector) window.escapeCssSelector = escapeCssSelector;
  if (!window.decodeHtmlEntities) window.decodeHtmlEntities = decodeHtmlEntities;
  if (!window.sanitizeHtml) window.sanitizeHtml = sanitizeHtml;
})();
