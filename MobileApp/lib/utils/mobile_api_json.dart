import 'dart:convert';

/// Helpers for `/api/mobile/v1` JSON and legacy Flask `json_ok` shapes.
///
/// Mobile success envelope: `{ "success": true, "data": ... }`
/// See Backoffice `app/utils/mobile_responses.py`.

Map<String, dynamic> decodeJsonObject(String body) {
  final decoded = jsonDecode(body);
  if (decoded is! Map<String, dynamic>) {
    throw const FormatException('Expected JSON object');
  }
  return decoded;
}

bool mobileResponseIsSuccess(Map<String, dynamic> root) {
  return root['status'] == 'success' || root['success'] == true;
}

/// Strict [mobile_ok]: returns [root['data']] when the response is successful
/// and `data` is a [Map]. Otherwise returns `null`.
Map<String, dynamic>? unwrapMobileDataMap(Map<String, dynamic> root) {
  if (!mobileResponseIsSuccess(root)) return null;
  final data = root['data'];
  return data is Map<String, dynamic> ? data : null;
}

/// Public/read-only endpoints that always store the payload under `data` as a map.
Map<String, dynamic> mobileDataMapLoose(Map<String, dynamic> root) {
  final data = root['data'];
  if (data is Map<String, dynamic>) return data;
  return {};
}

/// List payload under `data` (e.g. paginated indicator bank).
List<dynamic> mobileDataListLoose(Map<String, dynamic> root) {
  final data = root['data'];
  if (data is List<dynamic>) return data;
  if (data is List) return List<dynamic>.from(data);
  return [];
}

/// Single-indicator detail: prefer `data.indicator`, then `data`, then the root map.
Map<String, dynamic> resolveIndicatorDetailPayload(Map<String, dynamic> root) {
  final rawData = root['data'];
  if (rawData is Map<String, dynamic>) {
    final inner = rawData['indicator'];
    if (inner is Map<String, dynamic>) {
      return inner;
    }
    return rawData;
  }
  return root;
}

/// Access-requests style: `data` map when present, else top-level map.
Map<String, dynamic> mobileNestedDataOrRootMap(Map<String, dynamic> decoded) {
  final data = decoded['data'];
  if (data is Map<String, dynamic>) return data;
  return decoded;
}

/// Admin dashboard stats / activity: payload may live under `data` or merged at top level
/// (Flask `json_ok` vs `mobile_ok`).
Map<String, dynamic> mergeMobileOrJsonOkPayload(Map<String, dynamic> decoded) {
  if (!mobileResponseIsSuccess(decoded)) {
    return {};
  }
  final nested = decoded['data'];
  final map = Map<String, dynamic>.from(
    nested is Map ? nested as Map<String, dynamic> : decoded,
  );
  if (nested is! Map) {
    map.remove('success');
    map.remove('status');
    map.remove('message');
  }
  return map;
}
