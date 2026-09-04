/**
 * Platform + client JavaScript error reporting for the Backoffice.
 *
 * Platform errors (WAF 403, 502, 503, 504) → POST /api/v1/platform-error
 * Client JS runtime errors → POST /api/v1/client-error (SecurityEvent, no admin email)
 *
 * When a WAF or reverse-proxy intercepts an AJAX request the beacon script
 * embedded in the Azure custom error page never executes (the browser receives
 * an opaque response body, not a navigated page).  This module bridges that gap
 * by intercepting both transport layers used by the Backoffice:
 *
 *   1. window.fetch  — wrapped so every fetch()-based call (including csrfFetch,
 *      apiFetch, bare fetch) triggers reportPlatformError() on WAF responses.
 *
 *   2. jQuery AJAX   — a global ajaxComplete handler catches $.ajax / $.post /
 *      $.get responses the same way.
 *
 *   3. window.onerror + unhandledrejection — report ReferenceError and similar
 *      bugs to /api/v1/client-error (disabled when __humdbClientErrorReportingEnabled
 *      is false, e.g. Flask DEBUG).
 *
 * WAF vs Flask detection: Flask sets X-App-Origin: 1 on every response via
 * security_headers middleware.  Responses without that header are treated as
 * WAF/proxy errors.
 *
 * Deduplication: each report key is sent at most once per tab session
 * (sessionStorage).
 *
 * Loaded from core/layout.html (and chat_immersive.html) so coverage is
 * automatic for all pages.
 */
(function () {
  'use strict';

  var REPORTABLE_CODES = [403, 502, 503, 504];
  var PLATFORM_ENDPOINT = '/api/v1/platform-error';
  var CLIENT_ERROR_ENDPOINT = '/api/v1/client-error';
  var WRAP_FLAG = '__humdbPlatformErrorFetchWrapped';
  var JQ_FLAG   = '__humdbPlatformErrorJqBound';
  var WINDOW_ERROR_FLAG = '__humdbWindowErrorBound';

  var IGNORED_CLIENT_ERROR_FRAGMENTS = [
    'AbortError',
    'message channel closed before a response was received',
    'ResizeObserver loop limit exceeded',
    'ResizeObserver loop completed with undelivered notifications',
    'Non-Error promise rejection captured'
  ];

  var IGNORED_CLIENT_ERROR_SOURCE_PREFIXES = [
    'chrome-extension://',
    'moz-extension://',
    'safari-extension://',
    'safari-web-extension://'
  ];

  var nativeFetch =
    typeof window !== 'undefined' && typeof window.fetch === 'function'
      ? window.fetch.bind(window)
      : null;

  function shouldReport(statusCode) {
    return REPORTABLE_CODES.indexOf(statusCode) !== -1;
  }

  function pathnameForDedupe(urlStr) {
    if (!urlStr) return '';
    try {
      return new URL(urlStr, window.location.origin).pathname || '';
    } catch (_) {
      return String(urlStr).slice(0, 200);
    }
  }

  function dedupeKey(statusCode, failedRequestUrl) {
    var pagePath = (window.location && window.location.pathname) || '';
    var apiPath = pathnameForDedupe(failedRequestUrl);
    return 'platform_err_' + statusCode + '_' + pagePath + '_' + apiPath;
  }

  function alreadyReported(statusCode, failedRequestUrl) {
    try {
      return !!sessionStorage.getItem(dedupeKey(statusCode, failedRequestUrl));
    } catch (_) {
      return false;
    }
  }

  function markReported(statusCode, failedRequestUrl) {
    try {
      sessionStorage.setItem(dedupeKey(statusCode, failedRequestUrl), '1');
    } catch (_) {}
  }

  /**
   * Detect whether a response originated from a WAF / reverse-proxy rather
   * than from the Flask application.
   *
   * Primary signal: Flask sets X-App-Origin: 1 on every response via the
   * security_headers middleware.  WAF/proxy responses never carry that header.
   *
   * Accepts either a fetch Response or a thin adapter object with
   * { status: number, headers: { get(name): string|null } }.
   *
   * @param {Response|object} response
   * @returns {boolean}
   */
  function looksLikeWafResponse(response) {
    if (!response || typeof response.status !== 'number') return false;
    if (!shouldReport(response.status)) return false;

    try {
      if (response.headers.get('X-App-Origin') === '1') return false;
    } catch (_) {}

    return true;
  }

  /**
   * Field names that ajax-save.js is supposed to b64-wrap (or chunk) before
   * POST. An unwrapped value here on a later 403 is the smoking gun for a
   * stale cached module that predates the WAF wrap.
   */
  function isWrapCandidateFieldName(key) {
    if (!key) return false;
    return (
      key.indexOf('field_value[') === 0 ||
      key.indexOf('field_other_text[') === 0 ||
      key.indexOf('_emergency_metadata') !== -1
    );
  }

  function versionQueryFromUrl(urlStr) {
    try {
      var parsed = new URL(urlStr, (window.location && window.location.origin) || 'http://localhost');
      var v = parsed.searchParams.get('v');
      return v ? String(v).slice(0, 128) : null;
    } catch (_) {
      var match = String(urlStr || '').match(/[?&]v=([^&]+)/);
      if (!match) return null;
      try {
        return decodeURIComponent(match[1]).slice(0, 128);
      } catch (__) {
        return match[1].slice(0, 128);
      }
    }
  }

  function ajaxSaveUrlFromImportMap() {
    try {
      var maps = document.querySelectorAll('script[type="importmap"]');
      for (var i = 0; i < maps.length; i++) {
        var parsed = JSON.parse(maps[i].textContent || '{}');
        var scopes = parsed.scopes || {};
        var scopeKeys = Object.keys(scopes);
        for (var s = 0; s < scopeKeys.length; s++) {
          var specifiers = scopes[scopeKeys[s]] || {};
          var specKeys = Object.keys(specifiers);
          for (var k = 0; k < specKeys.length; k++) {
            var mapped = specifiers[specKeys[k]];
            if (mapped && String(mapped).indexOf('ajax-save.js') !== -1) {
              return String(mapped);
            }
          }
        }
        var imports = parsed.imports || {};
        var importKeys = Object.keys(imports);
        for (var n = 0; n < importKeys.length; n++) {
          var href = imports[importKeys[n]];
          if (
            String(importKeys[n]).indexOf('ajax-save.js') !== -1 ||
            (href && String(href).indexOf('ajax-save.js') !== -1)
          ) {
            return String(href);
          }
        }
      }
    } catch (_) { /* best-effort only */ }
    return null;
  }

  /**
   * Which ajax-save.js the tab actually loaded: Performance resource URL
   * (includes ?v=<deploy>.<content-hash>) plus cache-vs-network hint.
   * Falls back to the import-map target when no resource timing exists.
   */
  function resolveAjaxSaveScriptInfo() {
    var info = { url: null, version: null, delivery: null, transfer_size: null };
    try {
      if (typeof performance !== 'undefined' && typeof performance.getEntriesByType === 'function') {
        var entries = performance.getEntriesByType('resource') || [];
        for (var i = 0; i < entries.length; i++) {
          var entry = entries[i];
          if (!entry || !entry.name || String(entry.name).indexOf('ajax-save.js') === -1) {
            continue;
          }
          info.url = String(entry.name);
          if (typeof entry.transferSize === 'number') {
            info.transfer_size = entry.transferSize;
            if (entry.transferSize === 0 && typeof entry.encodedBodySize === 'number' && entry.encodedBodySize > 0) {
              info.delivery = 'disk_cache';
            } else if (entry.transferSize > 0) {
              info.delivery = 'network';
            }
          }
          break;
        }
      }
    } catch (_) { /* best-effort only */ }
    if (!info.url) {
      info.url = ajaxSaveUrlFromImportMap();
    }
    if (info.url) {
      info.version = versionQueryFromUrl(info.url);
    }
    return (info.url || info.version) ? info : null;
  }

  function collectClientVersionContext() {
    var ctx = {};
    try {
      if (window.ASSET_VERSION) {
        ctx.asset_version = String(window.ASSET_VERSION).slice(0, 128);
      }
    } catch (_) { /* best-effort only */ }
    try {
      if (window.location && window.location.href) {
        ctx.page_url = String(window.location.href).slice(0, 2000);
      }
    } catch (_) { /* best-effort only */ }
    try {
      var scriptInfo = resolveAjaxSaveScriptInfo();
      if (scriptInfo) {
        if (scriptInfo.url) ctx.ajax_save_script_url = String(scriptInfo.url).slice(0, 2000);
        if (scriptInfo.version) ctx.ajax_save_script_version = String(scriptInfo.version).slice(0, 128);
        if (scriptInfo.delivery) ctx.ajax_save_script_delivery = String(scriptInfo.delivery).slice(0, 40);
        if (typeof scriptInfo.transfer_size === 'number') {
          ctx.ajax_save_script_transfer_size = scriptInfo.transfer_size;
        }
      }
    } catch (_) { /* best-effort only */ }
    return ctx;
  }

  /**
   * Best-effort summary of a fetch/XHR request body, attached to platform
   * error reports so a future WAF 403 investigation doesn't hit the same
   * dead end this one did: the WAF blocks the request before it reaches
   * Flask, so the *only* place that ever saw the actual payload shape is the
   * browser that sent it. Capturing field count / approximate byte size /
   * b64-wrap coverage here lets SecOps/engineering tell "stale ajax-save.js"
   * from "large form" vs. "large single field" without WAF log access.
   *
   * @param {*} body - the `init.body` passed to fetch()
   * @returns {object|null}
   */
  function summarizeRequestBody(body) {
    try {
      if (typeof FormData !== 'undefined' && body instanceof FormData) {
        var fieldCount = 0;
        var approxBytes = 0;
        var b64FieldCount = 0;
        var unwrappedFieldCount = 0;
        var longestFieldBytes = 0;
        var longestFieldName = null;
        var unwrappedFieldNames = [];
        var entries = (typeof body.entries === 'function') ? body.entries() : null;
        if (!entries) return null;
        var next = entries.next();
        while (!next.done) {
          var pair = next.value;
          var key = String(pair[0] || '');
          var value = pair[1];
          var valueBytes = 0;
          var valueIsFile = value && typeof value === 'object' && typeof value.size === 'number';
          fieldCount += 1;
          if (valueIsFile) {
            valueBytes = value.size;
            approxBytes += key.length + valueBytes;
          } else {
            var valueStr = String(value == null ? '' : value);
            valueBytes = valueStr.length;
            approxBytes += key.length + valueBytes;
            if (valueStr.indexOf('b64:') === 0) {
              b64FieldCount += 1;
            } else if (isWrapCandidateFieldName(key) && valueStr.length > 0) {
              unwrappedFieldCount += 1;
              if (unwrappedFieldNames.length < 15) {
                unwrappedFieldNames.push(key.slice(0, 200));
              }
            }
          }
          if (valueBytes > longestFieldBytes) {
            longestFieldBytes = valueBytes;
            longestFieldName = key.slice(0, 200);
          }
          next = entries.next();
        }
        var summary = {
          request_field_count: fieldCount,
          request_approx_bytes: approxBytes,
          request_b64_field_count: b64FieldCount,
          request_unwrapped_field_count: unwrappedFieldCount,
          request_longest_field_bytes: longestFieldBytes
        };
        if (longestFieldName) {
          summary.request_longest_field_name = longestFieldName;
        }
        if (unwrappedFieldNames.length) {
          summary.request_unwrapped_field_names = unwrappedFieldNames;
        }
        return summary;
      }
      if (typeof body === 'string') {
        var stringSummary = { request_field_count: null, request_approx_bytes: body.length };
        if (body.indexOf('b64:') === 0) {
          stringSummary.request_b64_field_count = 1;
        }
        return stringSummary;
      }
    } catch (_) { /* best-effort only */ }
    return null;
  }

  function requestUrlFromFetchInput(input) {
    try {
      if (typeof input === 'string') return input;
      if (input && typeof input.url === 'string') return input.url;
    } catch (_) {}
    return window.location.href;
  }

  function isPlatformErrorRequestUrl(urlStr) {
    try {
      var p = pathnameForDedupe(urlStr);
      return p.indexOf('/api/v1/platform-error') !== -1;
    } catch (_) {
      return false;
    }
  }

  function isClientErrorRequestUrl(urlStr) {
    try {
      var p = pathnameForDedupe(urlStr);
      return p.indexOf('/api/v1/client-error') !== -1;
    } catch (_) {
      return false;
    }
  }

  function clientErrorReportingEnabled() {
    return window.__humdbClientErrorReportingEnabled !== false;
  }

  function sendJsonBeacon(endpoint, payload) {
    try {
      var body = JSON.stringify(payload);
      if (navigator.sendBeacon) {
        navigator.sendBeacon(
          endpoint,
          new Blob([body], { type: 'application/json' })
        );
      } else if (nativeFetch) {
        nativeFetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: body,
          keepalive: true
        }).catch(function () {});
      }
    } catch (_) {}
  }

  function shouldIgnoreClientErrorMessage(message, source) {
    var msg = String(message || '').trim();
    if (!msg) return true;
    if (msg === 'Script error.' && !source) return true;
    for (var i = 0; i < IGNORED_CLIENT_ERROR_FRAGMENTS.length; i++) {
      if (msg.indexOf(IGNORED_CLIENT_ERROR_FRAGMENTS[i]) !== -1) return true;
    }
    if (source) {
      var srcLower = String(source).toLowerCase();
      for (var j = 0; j < IGNORED_CLIENT_ERROR_SOURCE_PREFIXES.length; j++) {
        if (srcLower.indexOf(IGNORED_CLIENT_ERROR_SOURCE_PREFIXES[j]) === 0) return true;
      }
    }
    return false;
  }

  function clientErrorDedupeKey(kind, message, source, line, column) {
    var day = new Date().toISOString().slice(0, 10);
    var pagePath = (window.location && window.location.pathname) || '';
    return 'client_err_' + day + '_' + kind + '_' + pagePath + '_' + String(source || '') + '_' +
      String(line || '') + '_' + String(column || '') + '_' + String(message || '').slice(0, 200);
  }

  function alreadyReportedClientError(kind, message, source, line, column) {
    try {
      return !!sessionStorage.getItem(clientErrorDedupeKey(kind, message, source, line, column));
    } catch (_) {
      return false;
    }
  }

  function markClientErrorReported(kind, message, source, line, column) {
    try {
      sessionStorage.setItem(
        clientErrorDedupeKey(kind, message, source, line, column),
        '1'
      );
    } catch (_) {}
  }

  /**
   * Report a client-side JavaScript error to the backend.
   *
   * @param {object} details
   * @param {string} details.kind - "error" | "unhandledrejection"
   * @param {string} details.message
   * @param {string} [details.source]
   * @param {number} [details.line]
   * @param {number} [details.column]
   * @param {string} [details.stack]
   */
  function reportClientError(details) {
    if (!clientErrorReportingEnabled()) return;
    var d = details || {};
    var kind = d.kind === 'unhandledrejection' ? 'unhandledrejection' : 'error';
    var message = String(d.message || '').trim();
    var source = d.source ? String(d.source) : '';
    var line = typeof d.line === 'number' ? d.line : null;
    var column = typeof d.column === 'number' ? d.column : null;
    var stack = d.stack ? String(d.stack).slice(0, 4000) : '';

    if (shouldIgnoreClientErrorMessage(message, source)) return;
    if (alreadyReportedClientError(kind, message, source, line, column)) return;

    markClientErrorReported(kind, message, source, line, column);

    sendJsonBeacon(CLIENT_ERROR_ENDPOINT, {
      kind: kind,
      message: message.slice(0, 1000),
      source: source.slice(0, 500) || null,
      line: line,
      column: column,
      stack: stack || null,
      url: window.location.href,
      referrer: document.referrer || null,
      user_agent: navigator.userAgent || null,
      timestamp: new Date().toISOString()
    });
  }

  /**
   * Report a platform-level error to the backend.
   *
   * Safe to call speculatively — it no-ops when the status code is not
   * reportable, the response looks like a normal Flask response, or the
   * same error was already reported this session.
   *
   * @param {Response|object} response - fetch Response or adapter with .status / .headers.get
   * @param {object}   [opts]
   * @param {string}   [opts.url]      - URL of the failed request (default: current page)
   * @param {string}   [opts.referrer] - Override referrer
   */
  function reportPlatformError(response, opts) {
    if (!response || typeof response.status !== 'number') return;
    var code = response.status;
    if (!shouldReport(code)) return;
    if (!looksLikeWafResponse(response)) return;

    var o = opts || {};
    var failedUrl = o.url || window.location.href;
    if (alreadyReported(code, failedUrl)) return;

    markReported(code, failedUrl);

    var payload = {
      error_code: code,
      url: failedUrl,
      referrer: o.referrer || document.referrer || null,
      user_agent: navigator.userAgent || null,
      timestamp: new Date().toISOString()
    };

    // Deploy + ajax-save.js version (best-effort). If a returning visitor
    // still has the pre-WAF-wrap module cached, the page's ASSET_VERSION and
    // the script ?v= / wrap counts will disagree.
    var versionCtx = collectClientVersionContext();
    var versionKeys = [
      'asset_version',
      'page_url',
      'ajax_save_script_url',
      'ajax_save_script_version',
      'ajax_save_script_delivery'
    ];
    for (var vk = 0; vk < versionKeys.length; vk++) {
      if (versionCtx[versionKeys[vk]]) {
        payload[versionKeys[vk]] = versionCtx[versionKeys[vk]];
      }
    }
    if (typeof versionCtx.ajax_save_script_transfer_size === 'number') {
      payload.ajax_save_script_transfer_size = versionCtx.ajax_save_script_transfer_size;
    }

    try {
      var serverHdr = response.headers && response.headers.get('server');
      if (serverHdr) {
        payload.response_server = String(serverHdr).slice(0, 200);
      }
    } catch (_) { /* best-effort only */ }

    // Request-body telemetry (best-effort; see summarizeRequestBody doc comment).
    var bodySummary = o.requestBodySummary || (o.requestBody !== undefined ? summarizeRequestBody(o.requestBody) : null);
    if (bodySummary) {
      var bodyKeys = [
        'request_field_count',
        'request_approx_bytes',
        'request_b64_field_count',
        'request_unwrapped_field_count',
        'request_longest_field_bytes'
      ];
      for (var bk = 0; bk < bodyKeys.length; bk++) {
        if (typeof bodySummary[bodyKeys[bk]] === 'number') {
          payload[bodyKeys[bk]] = bodySummary[bodyKeys[bk]];
        }
      }
      if (bodySummary.request_longest_field_name) {
        payload.request_longest_field_name = bodySummary.request_longest_field_name;
      }
      if (bodySummary.request_unwrapped_field_names && bodySummary.request_unwrapped_field_names.length) {
        payload.request_unwrapped_field_names = bodySummary.request_unwrapped_field_names;
      }
    }

    try {
      sendJsonBeacon(PLATFORM_ENDPOINT, payload);
    } catch (_) {}

    // For 504 specifically: schedule lightweight recovery probes at T+5s and
    // T+15s.  These arrive when a worker IS healthy and complete the incident
    // timeline by showing "worker available again" state in the server log.
    if (code === 504) {
      scheduleWorkerProbes(failedUrl);
    }
  }

  /**
   * Send a recovery-confirmation beacon after a 504, at T+5s and T+15s.
   *
   * The backend receives these as [WORKER_RECOVERY] log entries (no security
   * event created).  probe_delay_s tells the backend how long after the
   * original 504 this probe was sent, so it can compute the incident duration.
   *
   * Uses nativeFetch (not the wrapped window.fetch) to avoid recursive error
   * detection. Falls back to sendBeacon so it survives page navigation.
   *
   * @param {string} failedUrl - The URL that returned 504
   */
  function scheduleWorkerProbes(failedUrl) {
    var delays = [5000, 15000];
    for (var i = 0; i < delays.length; i++) {
      (function (delayMs) {
        setTimeout(function () {
          var probePayload = {
            error_code: 504,
            url: failedUrl,
            user_agent: navigator.userAgent || null,
            timestamp: new Date().toISOString(),
            probe_delay_s: delayMs / 1000
          };
          try {
            sendJsonBeacon(PLATFORM_ENDPOINT, probePayload);
          } catch (_) {}
        }, delayMs);
      })(delays[i]);
    }
  }

  /* ── window.fetch wrapper ──────────────────────────────────────────────── */

  function installFetchWrapper() {
    if (!nativeFetch || window[WRAP_FLAG]) return;
    window[WRAP_FLAG] = true;
    window.fetch = function (input, init) {
      var reqUrl = requestUrlFromFetchInput(input);
      // Summarize the outgoing body *before* awaiting the response — a
      // FormData's file entries could theoretically be mutated/GC'd by the
      // time the response resolves, and this is cheap either way.
      var bodySummary = (init && init.body !== undefined) ? summarizeRequestBody(init.body) : null;
      return nativeFetch(input, init).then(function (response) {
        if (
          response &&
          !response.ok &&
          !isPlatformErrorRequestUrl(reqUrl) &&
          typeof reportPlatformError === 'function'
        ) {
          reportPlatformError(response, { url: reqUrl, requestBodySummary: bodySummary });
        }
        return response;
      });
    };
  }

  /* ── jQuery AJAX handler ───────────────────────────────────────────────── */

  function installJQueryHandler() {
    var jq = (typeof jQuery !== 'undefined') ? jQuery
           : (typeof $ !== 'undefined' && $.fn && $.fn.jquery) ? $
           : null;
    if (!jq || window[JQ_FLAG]) return;
    window[JQ_FLAG] = true;

    jq(document).ajaxComplete(function (_event, jqXHR, settings) {
      if (!jqXHR || !shouldReport(jqXHR.status)) return;
      var reqUrl = (settings && settings.url) || window.location.href;
      if (isPlatformErrorRequestUrl(reqUrl)) return;

      var adapter = {
        status: jqXHR.status,
        headers: {
          get: function (name) {
            try { return jqXHR.getResponseHeader(name); } catch (_) { return null; }
          }
        }
      };
      reportPlatformError(adapter, { url: reqUrl });
    });
  }

  /* ── Global unhandled-rejection handler ───────────────────────────────── */

  var UNHANDLED_FLAG = '__humdbUnhandledRejectionBound';

  function installUnhandledRejectionHandler() {
    if (typeof window === 'undefined' || window[UNHANDLED_FLAG]) return;
    window[UNHANDLED_FLAG] = true;
    window.addEventListener('unhandledrejection', function (event) {
      var reason = (event && event.reason) || {};
      var msg = String(reason && reason.message ? reason.message : reason);
      // Suppress noise from aborted fetches and cancelled operations.
      if (msg === 'AbortError' || msg.indexOf('AbortError') !== -1) return;
      // Suppress browser-extension message-channel noise.  Third-party extensions
      // register async chrome.runtime.onMessage listeners (returning `true`) but
      // close the channel before the response arrives, surfacing as an unhandled
      // rejection in the host page's context.  This is entirely outside page code.
      if (msg.indexOf('message channel closed before a response was received') !== -1) {
        event.preventDefault();
        return;
      }
      console.warn('[humdb] Unhandled promise rejection:', reason);
      reportClientError({
        kind: 'unhandledrejection',
        message: msg,
        stack: reason && reason.stack ? String(reason.stack) : null
      });
    });
  }

  function installWindowErrorHandler() {
    if (typeof window === 'undefined' || window[WINDOW_ERROR_FLAG]) return;
    window[WINDOW_ERROR_FLAG] = true;
    window.addEventListener('error', function (event) {
      if (!event) return;
      // Ignore resource load failures (images, stylesheets, etc.).
      var target = event.target;
      if (target && target !== window && target !== document) {
        var tag = target.tagName ? String(target.tagName).toUpperCase() : '';
        if (tag && tag !== 'SCRIPT') return;
      }

      var message = event.message || (event.error && event.error.message) || 'Unknown error';
      var source = event.filename || (event.error && event.error.fileName) || '';
      var line = typeof event.lineno === 'number' ? event.lineno : null;
      var column = typeof event.colno === 'number' ? event.colno : null;
      var stack = event.error && event.error.stack ? String(event.error.stack) : null;

      reportClientError({
        kind: 'error',
        message: message,
        source: source,
        line: line,
        column: column,
        stack: stack
      });
    });
  }

  /* ── Navigation status check (full-page 504/502/503) ─────────────────── */

  function installNavigationStatusCheck() {
    try {
      var entries = performance.getEntriesByType('navigation');
      if (!entries || !entries.length) return;
      var status = entries[0].responseStatus;
      if (!status || !shouldReport(status)) return;

      var url = window.location.href;
      if (alreadyReported(status, url)) return;

      markReported(status, url);

      var payload = {
        error_code: status,
        url: url,
        referrer: document.referrer || null,
        user_agent: navigator.userAgent || null,
        timestamp: new Date().toISOString()
      };
      var navVersion = collectClientVersionContext();
      if (navVersion.asset_version) payload.asset_version = navVersion.asset_version;
      if (navVersion.page_url) payload.page_url = navVersion.page_url;
      if (navVersion.ajax_save_script_url) payload.ajax_save_script_url = navVersion.ajax_save_script_url;
      if (navVersion.ajax_save_script_version) payload.ajax_save_script_version = navVersion.ajax_save_script_version;

      if (navigator.sendBeacon) {
        sendJsonBeacon(PLATFORM_ENDPOINT, payload);
      } else if (nativeFetch) {
        sendJsonBeacon(PLATFORM_ENDPOINT, payload);
      }
    } catch (_) {}
  }

  /* ── Bootstrap ─────────────────────────────────────────────────────────── */

  if (typeof window !== 'undefined') {
    window.reportPlatformError = reportPlatformError;
    window.reportClientError = reportClientError;
    window.looksLikeWafResponse = looksLikeWafResponse;
    installFetchWrapper();
    installJQueryHandler();
    installWindowErrorHandler();
    installUnhandledRejectionHandler();
    installNavigationStatusCheck();
  }
})();
