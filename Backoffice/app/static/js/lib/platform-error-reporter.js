/**
 * Reports platform-level errors (WAF 403, 502, 503) to /api/v1/platform-error.
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
 * WAF vs Flask detection: Flask sets X-App-Origin: 1 on every response via
 * security_headers middleware.  Responses without that header are treated as
 * WAF/proxy errors.
 *
 * Deduplication: each (status, page-path, request-path) is reported at most
 * once per tab session (sessionStorage).
 *
 * Loaded from core/layout.html (and chat_immersive.html) so coverage is
 * automatic for all pages.
 */
(function () {
  'use strict';

  var REPORTABLE_CODES = [403, 502, 503];
  var ENDPOINT = '/api/v1/platform-error';
  var WRAP_FLAG = '__humdbPlatformErrorFetchWrapped';
  var JQ_FLAG   = '__humdbPlatformErrorJqBound';

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

    try {
      if (navigator.sendBeacon) {
        navigator.sendBeacon(
          ENDPOINT,
          new Blob([JSON.stringify(payload)], { type: 'application/json' })
        );
      } else if (nativeFetch) {
        nativeFetch(ENDPOINT, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
          keepalive: true
        }).catch(function () {});
      }
    } catch (_) {}
  }

  /* ── window.fetch wrapper ──────────────────────────────────────────────── */

  function installFetchWrapper() {
    if (!nativeFetch || window[WRAP_FLAG]) return;
    window[WRAP_FLAG] = true;
    window.fetch = function (input, init) {
      var reqUrl = requestUrlFromFetchInput(input);
      return nativeFetch(input, init).then(function (response) {
        if (
          response &&
          !response.ok &&
          !isPlatformErrorRequestUrl(reqUrl) &&
          typeof reportPlatformError === 'function'
        ) {
          reportPlatformError(response, { url: reqUrl });
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

  /* ── Bootstrap ─────────────────────────────────────────────────────────── */

  if (typeof window !== 'undefined') {
    window.reportPlatformError = reportPlatformError;
    window.looksLikeWafResponse = looksLikeWafResponse;
    installFetchWrapper();
    installJQueryHandler();
  }
})();
