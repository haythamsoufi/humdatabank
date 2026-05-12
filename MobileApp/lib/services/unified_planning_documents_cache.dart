import 'dart:convert';

import '../config/app_config.dart';
import '../models/shared/unified_planning_document.dart';
import '../utils/debug_logger.dart';
import 'storage_service.dart';

/// Persisted snapshot of the IFRC unified planning grid (documents + UI flags).
///
/// Used when [shouldDeferRemoteFetch] is true or when a live refresh fails, so
/// the list and [pdfThumbnailEnabled] still match the last successful online load.
class UnifiedPlanningDocumentsCache {
  UnifiedPlanningDocumentsCache(this._storage);

  final StorageService _storage;

  static const int _formatVersion = 1;

  Future<void> save({
    required List<UnifiedPlanningDocument> documents,
    required bool pdfThumbnailEnabled,
  }) async {
    try {
      final payload = jsonEncode({
        'v': _formatVersion,
        'timestamp': DateTime.now().toUtc().toIso8601String(),
        'pdf_thumbnail_enabled': pdfThumbnailEnabled,
        'documents': documents.map((d) => d.toJson()).toList(),
      });
      await _storage.setString(AppConfig.cachedUnifiedPlanningSnapshotKey, payload);
    } catch (e, st) {
      DebugLogger.logErrorWithTag(
        'UNIFIED_PLANNING_CACHE',
        'Save failed: $e\n$st',
      );
    }
  }

  /// Returns null if missing, corrupt, or wrong version.
  Future<UnifiedPlanningSnapshot?> load() async {
    try {
      final raw = await _storage.getString(AppConfig.cachedUnifiedPlanningSnapshotKey);
      if (raw == null || raw.isEmpty) return null;
      final decoded = jsonDecode(raw);
      if (decoded is! Map<String, dynamic>) return null;
      if ((decoded['v'] as num?)?.toInt() != _formatVersion) return null;
      final thumb = decoded['pdf_thumbnail_enabled'];
      final pdfThumb = thumb is bool ? thumb : true;
      final list = decoded['documents'];
      if (list is! List<dynamic>) return null;
      final docs = <UnifiedPlanningDocument>[];
      for (final e in list) {
        if (e is! Map<String, dynamic>) continue;
        final url = (e['url'] as String?)?.trim() ?? '';
        if (url.isEmpty) continue;
        docs.add(UnifiedPlanningDocument.fromJson(e));
      }
      DateTime? at;
      final ts = decoded['timestamp'];
      if (ts is String && ts.isNotEmpty) {
        at = DateTime.tryParse(ts);
      }
      return UnifiedPlanningSnapshot(
        documents: docs,
        pdfThumbnailEnabled: pdfThumb,
        cachedAt: at,
      );
    } catch (e, st) {
      DebugLogger.logWarn('UNIFIED_PLANNING_CACHE', 'Load failed: $e\n$st');
      return null;
    }
  }
}

class UnifiedPlanningSnapshot {
  final List<UnifiedPlanningDocument> documents;
  final bool pdfThumbnailEnabled;
  final DateTime? cachedAt;

  const UnifiedPlanningSnapshot({
    required this.documents,
    required this.pdfThumbnailEnabled,
    this.cachedAt,
  });
}
