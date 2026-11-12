import 'dart:convert';

/// Longest value of any single envelope key. Matches `WAF_JSON_MAX_CHUNK` in the
/// Backoffice web client so no single argument trips the gateway's length rules.
const int wafJsonMaxChunk = 350;

/// Wraps a JSON object in the base64 envelope the Backoffice AI endpoints unwrap
/// (`unwrap_waf_json_envelope` in `app/utils/http/request_utils.py`).
///
/// The gateway's WAF inspects POST bodies and answers 403 (with no JSON error body)
/// when chat history contains HTML/markdown/SQL-like text, which happens as soon as a
/// conversation has a previous assistant reply. The envelope hides that text the same way
/// the web chat does (`stringifyWafJsonBody` in `waf-json-body.js`):
/// `{"payload": "<first 350 chars>", "payload__c1": "...", ...}`.
Map<String, dynamic> wrapWafJsonBody(Map<String, dynamic> inner) {
  final wire = base64.encode(utf8.encode(jsonEncode(inner)));
  if (wire.length <= wafJsonMaxChunk) {
    return {'payload': wire};
  }
  final out = <String, dynamic>{'payload': wire.substring(0, wafJsonMaxChunk)};
  var index = 1;
  for (var i = wafJsonMaxChunk; i < wire.length; i += wafJsonMaxChunk) {
    final end = i + wafJsonMaxChunk < wire.length ? i + wafJsonMaxChunk : wire.length;
    out['payload__c$index'] = wire.substring(i, end);
    index++;
  }
  return out;
}
