/**
 * WAF-safe JSON POST body: wrap the real object as base64 and split it
 * across sibling keys so signature rules (941/942) never see HTML/SQL-like
 * tokens, and no single argument exceeds CRS 920370 example length.
 *
 * Wire format (same envelope as manage-settings / get_request_data):
 *   { "payload": "<first ≤350 chars of b64>", "payload__c1": "...", ... }
 *
 * Server: unwrap_waf_json_envelope() in app/utils/request_utils.py.
 *
 * @module lib/waf-json-body
 */

export const WAF_JSON_MAX_CHUNK = 350;

export function encodeUtf8ToB64(text) {
  return btoa(unescape(encodeURIComponent(String(text))));
}

export function wrapWafJsonBody(innerObj) {
  const b64 = encodeUtf8ToB64(JSON.stringify(innerObj));
  if (b64.length <= WAF_JSON_MAX_CHUNK) {
    return { payload: b64 };
  }
  const out = { payload: b64.slice(0, WAF_JSON_MAX_CHUNK) };
  let index = 1;
  for (let i = WAF_JSON_MAX_CHUNK; i < b64.length; i += WAF_JSON_MAX_CHUNK) {
    out['payload__c' + index] = b64.slice(i, i + WAF_JSON_MAX_CHUNK);
    index += 1;
  }
  return out;
}

export function stringifyWafJsonBody(innerObj) {
  try {
    return JSON.stringify(wrapWafJsonBody(innerObj));
  } catch (_) {
    return JSON.stringify(innerObj);
  }
}
