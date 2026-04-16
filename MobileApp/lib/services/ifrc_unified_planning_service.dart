import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import '../models/shared/unified_planning_document.dart';
import '../utils/debug_logger.dart';

/// Fetches unified planning documents from IFRC GO using config from the backoffice.
class IfrcUnifiedPlanningService {
  IfrcUnifiedPlanningService._();
  static final IfrcUnifiedPlanningService instance = IfrcUnifiedPlanningService._();

  static final _yearRe = RegExp(r'\b(20\d{2})\b');
  static final _iso2SuffixRe = RegExp(r'\s*\([A-Z]{2}\)\s*$');

  /// GET [AppConfig.mobileUnifiedPlanningConfigEndpoint] — public mobile API.
  Future<Map<String, dynamic>?> fetchConfig() async {
    final uri = Uri.parse(
      '${AppConfig.baseApiUrl}${AppConfig.mobileUnifiedPlanningConfigEndpoint}',
    );
    final headers = <String, String>{
      'Accept': 'application/json',
      'User-Agent': 'hum-databank-mobile/1.0',
    };
    final key = AppConfig.apiKey.trim();
    if (key.isNotEmpty) {
      headers['Authorization'] = 'Bearer $key';
    }
    try {
      final res = await http.get(uri, headers: headers).timeout(const Duration(seconds: 25));
      if (res.statusCode != 200) {
        DebugLogger.logErrorWithTag(
          'IFRC_UNIFIED_PLANNING',
          'Config HTTP ${res.statusCode}',
        );
        return null;
      }
      final body = jsonDecode(res.body);
      if (body is! Map<String, dynamic>) return null;
      if (body['success'] != true) return null;
      final data = body['data'];
      if (data is! Map<String, dynamic>) return null;
      return data;
    } catch (e, st) {
      DebugLogger.logErrorWithTag('IFRC_UNIFIED_PLANNING', 'Config error: $e\n$st');
      return null;
    }
  }

  /// Build type id → label map from config `document_types` list.
  static Map<int, String> parseTypeLabels(Map<String, dynamic> config) {
    final out = <int, String>{};
    final raw = config['document_types'];
    if (raw is! List) return out;
    for (final e in raw) {
      if (e is! Map) continue;
      final id = e['id'];
      final label = e['label']?.toString();
      if (id is int && label != null && label.isNotEmpty) {
        out[id] = label;
      } else if (id is num && label != null && label.isNotEmpty) {
        out[id.toInt()] = label;
      }
    }
    return out;
  }

  static String _normalizeHttpsUrl(String raw) {
    final u = raw.trim();
    if (u.isEmpty) return '';
    try {
      final parsed = Uri.parse(u);
      final scheme = (parsed.scheme.isEmpty ? 'https' : parsed.scheme).toLowerCase();
      var host = parsed.host.toLowerCase();
      if (host.isEmpty) return u;
      var port = parsed.hasPort ? parsed.port : null;
      if (scheme == 'https' && port == 443) port = null;
      if (scheme == 'http' && port == 80) port = null;
      var path = parsed.path;
      if (path.isEmpty) path = '/';
      path = path.replaceAll(RegExp(r'/+'), '/');
      if (!path.startsWith('/')) path = '/$path';
      return Uri(
        scheme: scheme,
        host: host,
        port: port,
        path: path,
        query: parsed.query,
      ).toString();
    } catch (_) {
      return u;
    }
  }

  static String? _stripCountrySuffix(String? name) {
    if (name == null) return null;
    final s = name.trim();
    if (s.isEmpty) return null;
    return s.replaceAll(_iso2SuffixRe, '').trim();
  }

  /// GET IFRC appeals list with HTTP Basic auth (credentials from app env / dart-define).
  Future<List<UnifiedPlanningDocument>> fetchDocuments({
    required String ifrcListUrl,
    required Map<int, String> typeLabels,
  }) async {
    final user = AppConfig.ifrcApiUser;
    final password = AppConfig.ifrcApiPassword;
    if (user.isEmpty || password.isEmpty) {
      throw StateError('missing_credentials');
    }

    final uri = Uri.parse(ifrcListUrl);
    final token = base64Encode(utf8.encode('$user:$password'));
    final headers = <String, String>{
      'Accept': 'application/json',
      'User-Agent': 'hum-databank-mobile/1.0',
      'Authorization': 'Basic $token',
    };

    final res = await http.get(uri, headers: headers).timeout(const Duration(seconds: 45));
    if (res.statusCode == 401) {
      throw StateError('ifrc_auth_failed');
    }
    if (res.statusCode != 200) {
      throw StateError('ifrc_http_${res.statusCode}');
    }

    final decoded = jsonDecode(res.body);
    if (decoded is! List) {
      throw StateError('ifrc_invalid_json');
    }

    final out = <UnifiedPlanningDocument>[];
    for (final item in decoded) {
      if (item is! Map<String, dynamic>) continue;
      if (item['Hidden'] == true) continue;

      final baseDir = (item['BaseDirectory'] as String?) ?? '';
      final baseFile = (item['BaseFileName'] as String?) ?? '';
      if (baseDir.isEmpty || baseFile.isEmpty) continue;

      final url = _normalizeHttpsUrl(baseDir + baseFile);
      if (!url.toLowerCase().startsWith('https://')) continue;

      final appealsTypeId = item['AppealsTypeId'];
      int? tid;
      if (appealsTypeId is int) {
        tid = appealsTypeId;
      } else if (appealsTypeId is num) {
        tid = appealsTypeId.toInt();
      }

      final orig = (item['AppealOrigType'] as String?) ?? '';
      final name = (item['AppealsName'] as String?) ?? '';
      final ym = _yearRe.firstMatch('$orig $name');
      final year = ym != null ? int.tryParse(ym.group(1)!) : null;

      final locCode = (item['LocationCountryCode'] as String?)?.trim().toUpperCase();
      final locName = _stripCountrySuffix(item['LocationCountryName'] as String?);

      final title = name.trim().isNotEmpty ? name.trim() : (orig.trim().isNotEmpty ? orig.trim() : 'Document');

      out.add(
        UnifiedPlanningDocument(
          url: url,
          title: title,
          countryCode: locCode?.isEmpty ?? true ? null : locCode,
          countryName: locName?.isEmpty ?? true ? null : locName,
          appealsTypeId: tid,
          documentTypeLabel: tid != null ? typeLabels[tid] : null,
          year: year,
        ),
      );
    }

    out.sort((a, b) {
      final yb = b.year ?? -1;
      final ya = a.year ?? -1;
      if (yb != ya) return yb.compareTo(ya);
      return a.title.toLowerCase().compareTo(b.title.toLowerCase());
    });
    return out;
  }
}
