import 'dart:convert';

/// JavaScript shared by the online recorder and the offline replay so that both
/// sides derive the same cache key for a request.
///
/// Keys look like `GET /path?a=1&b=2`; unsafe methods append a hash of the string
/// body (`POST /path #<hash>:<length>`). Requests without a derivable key
/// (FormData bodies, Request objects with bodies) are neither recorded nor replayed.
const String kOfflineApiKeyJs = r'''
  var IFRC_VOLATILE_PARAMS = { _: 1, _t: 1, ts: 1, t: 1, timestamp: 1, cb: 1, nocache: 1 };
  function ifrcApiParts(input, init) {
    var method = (init && init.method) || (input && typeof input === 'object' && input.method) || 'GET';
    var url = (typeof input === 'string') ? input
      : (input && typeof input === 'object' && input.url) ? input.url : String(input);
    var body = init && init.body;
    return { method: String(method).toUpperCase(), url: url, body: body };
  }
  function ifrcApiKey(method, url, body) {
    try {
      var u = new URL(String(url), location.href);
      var params = [];
      u.searchParams.forEach(function (v, k) {
        if (!IFRC_VOLATILE_PARAMS[k]) params.push([k, v]);
      });
      params.sort(function (a, b) {
        if (a[0] !== b[0]) return a[0] < b[0] ? -1 : 1;
        return a[1] < b[1] ? -1 : (a[1] > b[1] ? 1 : 0);
      });
      var qs = params.map(function (p) {
        return encodeURIComponent(p[0]) + '=' + encodeURIComponent(p[1]);
      }).join('&');
      var key = method + ' ' + u.pathname + (qs ? '?' + qs : '');
      if (method !== 'GET' && method !== 'HEAD') {
        if (typeof body !== 'string') return null;
        var h = 5381;
        for (var i = 0; i < body.length; i++) {
          h = ((h * 33) ^ body.charCodeAt(i)) >>> 0;
        }
        key += ' #' + h.toString(36) + ':' + body.length;
      }
      return key;
    } catch (e) {
      return null;
    }
  }
''';

/// Name of the Flutter handler that receives recorded API responses.
const String kOfflineApiRecordHandler = 'ifrcOfflineApiRecord';

/// Injected at document start in the online entry-form WebView (and in the
/// headless download-time load). Captures the JSON the form fetches for its own
/// data — lookup lists, plugin data such as emergency operations, entry bootstrap,
/// resolved variables — so the saved copy can serve them offline.
final String kOfflineApiRecorderJs = '''
(function () {
  if (window.__ifrcApiRecorderInstalled) return;
  window.__ifrcApiRecorderInstalled = true;
  var nativeFetch = window.fetch;
  if (typeof nativeFetch !== 'function') return;
$kOfflineApiKeyJs
  var ALLOW_GET = /^\\/(api\\/(forms|v1|plugins)\\/|admin\\/plugins\\/|admin\\/api\\/plugins\\/|forms\\/matrix\\/)/;
  var ALLOW_POST = /^\\/(api\\/v1\\/variables\\/resolve|api\\/v1\\/matrix\\/auto-load-entities\\/batch|forms\\/matrix\\/search-rows|api\\/forms\\/dynamic-indicators\\/render-pending)/;
  var DENY = /\\/(presence|session-keepalive|keepalive|csrf|discussion|validation[_-]summary|export|upload|notifications|chat|ai-opinions)/i;
  var MAX_BODY = 4 * 1024 * 1024;
  var pending = [];
  var timer = null;

  function aesId() {
    var m = location.pathname.match(/\\/assignment\\/(\\d+)/);
    return m ? parseInt(m[1], 10) : null;
  }
  function flush() {
    timer = null;
    if (!pending.length) return;
    var id = aesId();
    var batch = pending.splice(0, pending.length);
    if (id === null) return;
    try {
      if (window.flutter_inappwebview && window.flutter_inappwebview.callHandler) {
        window.flutter_inappwebview.callHandler('$kOfflineApiRecordHandler', JSON.stringify({ aesId: id, entries: batch }));
      }
    } catch (e) {}
  }
  window.__ifrcApiRecorderFlush = flush;
  function schedule() {
    if (timer === null) timer = setTimeout(flush, 1000);
  }
  function eligible(parts, key) {
    if (!key) return false;
    var path = key.split(' ')[1].split('?')[0];
    if (DENY.test(path)) return false;
    if (parts.method === 'GET') return ALLOW_GET.test(path);
    if (parts.method === 'POST') return ALLOW_POST.test(path);
    return false;
  }
  window.fetch = function (input, init) {
    var parts, key;
    try {
      parts = ifrcApiParts(input, init);
      key = ifrcApiKey(parts.method, parts.url, parts.body);
    } catch (e) { key = null; }
    var result = nativeFetch.apply(this, arguments);
    try {
      if (key && eligible(parts, key)) {
        result.then(function (resp) {
          if (!resp || !resp.ok) return;
          var ct = resp.headers.get('Content-Type') || '';
          if (ct.indexOf('json') === -1) return;
          resp.clone().text().then(function (text) {
            if (!text || text.length > MAX_BODY) return;
            pending.push({ k: key, s: resp.status, t: ct, b: text });
            schedule();
          }).catch(function () {});
        }).catch(function () {});
      }
    } catch (e) {}
    return result;
  };
  window.addEventListener('pagehide', flush);
})();
''';

/// Head patch for a saved form: replays recorded API responses, stubs the service
/// worker and static URL helper, and keeps server-only actions from running while
/// the form is opened from disk. Saving stays available (drafts are kept on the
/// device); submitting is only possible online, where the server validates it.
String buildOfflineHeadPatch({required String submitBlockedMessage}) {
  final message = jsonEncode(submitBlockedMessage);
  return '''
<script src="offline_api_cache.js"></script>
<style>
.approve-assignment-form, .reopen-assignment-form,
a[href*="/export_pdf"], a[href*="/export_excel"], a[href*="/validation_summary"],
[data-requires-online] { display: none !important; }
</style>
<script>
(function () {
  window.__IFRC_OFFLINE_BUNDLE = true;
  try {
    if (navigator.serviceWorker && navigator.serviceWorker.register) {
      navigator.serviceWorker.register = function () { return Promise.resolve({}); };
    }
  } catch (e) {}
  try {
    window.getStaticUrl = function (filename) {
      filename = String(filename || '').replace(/^\\/+/, '').replace(/^static\\/+/, '');
      return 'static/' + filename;
    };
  } catch (e) {}
$kOfflineApiKeyJs
  var nativeFetch = window.fetch;
  window.fetch = function (input, init) {
    try {
      var parts = ifrcApiParts(input, init);
      var key = ifrcApiKey(parts.method, parts.url, parts.body);
      var store = window.__IFRC_OFFLINE_API__ || {};
      var hit = key ? store[key] : null;
      if (hit) {
        return Promise.resolve(new Response(hit.b, {
          status: hit.s || 200,
          headers: { 'Content-Type': hit.t || 'application/json' }
        }));
      }
    } catch (e) {}
    if (typeof nativeFetch === 'function') return nativeFetch.apply(this, arguments);
    return Promise.reject(new TypeError('Failed to fetch'));
  };

  var SUBMIT_MESSAGE = $message;
  var ONLINE_ONLY_ACTIONS = { submit: 1, send_for_review: 1 };
  function notifyOnlineOnly() {
    try {
      var drafts = window.__ifrcAuthDrafts;
      if (drafts && typeof drafts.saveNow === 'function') {
        if (typeof drafts.setOffline === 'function') drafts.setOffline(true);
        drafts.saveNow();
      }
    } catch (e) {}
    try {
      if (typeof window.showAlert === 'function') window.showAlert(SUBMIT_MESSAGE, 'warning');
      else alert(SUBMIT_MESSAGE);
    } catch (e) {}
  }
  function isOnlineOnlyControl(el) {
    if (!el || !el.closest) return false;
    var btn = el.closest('button, input[type="submit"]');
    if (!btn) return false;
    if (btn.name === 'action' && ONLINE_ONLY_ACTIONS[btn.value]) return true;
    return !!btn.closest('.approve-assignment-form, .reopen-assignment-form');
  }
  function block(e) {
    e.preventDefault();
    e.stopImmediatePropagation();
    notifyOnlineOnly();
  }
  document.addEventListener('click', function (e) {
    if (isOnlineOnlyControl(e.target)) block(e);
  }, true);
  document.addEventListener('submit', function (e) {
    if (isOnlineOnlyControl(e.submitter)) block(e);
  }, true);
})();
</script>
''';
}

/// Runs while the page is still being parsed (before deferred/module scripts),
/// pointing plugin module and stylesheet paths at the saved files. The form's
/// plugin loader imports `es_module_path` dynamically, and a root-absolute
/// `/plugins/static/…` does not exist under `file://`.
const String kOfflinePluginPathsScript = r'''
<script>
(function () {
  try {
    var base = location.href.replace(/[?#].*$/, '').replace(/[^\/]*$/, '');
    var P = '/plugins/static/';
    var abs = base + 'plugins/static/';
    var els = document.querySelectorAll('[data-entry-form-config]');
    for (var i = 0; i < els.length; i++) {
      var v = els[i].getAttribute('data-entry-form-config');
      if (v && v.indexOf(P) !== -1) {
        els[i].setAttribute('data-entry-form-config', v.split(P).join(abs));
      }
    }
  } catch (e) {}
})();
</script>
''';
