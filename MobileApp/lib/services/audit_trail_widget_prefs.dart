import 'dart:convert';

import '../config/app_config.dart';
import 'storage_service.dart';

/// Persisted on this device. Empty set = widget shows all activity types.
class AuditTrailWidgetPrefs {
  AuditTrailWidgetPrefs._();

  /// Canonical filter slugs: create, update, delete, login, logout.
  static Future<Set<String>> getActivityTypeFilter() async {
    final raw =
        await StorageService().getString(AppConfig.auditTrailWidgetActivityFiltersKey);
    if (raw == null || raw.isEmpty) return {};
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! List) return {};
      return decoded
          .map((e) => e.toString().toLowerCase().trim())
          .where((s) => s.isNotEmpty)
          .toSet();
    } catch (_) {
      return {};
    }
  }

  static Future<void> setActivityTypeFilter(Set<String> types) async {
    final normalized = types
        .map((s) => s.toLowerCase().trim())
        .where((s) => s.isNotEmpty)
        .toList()
      ..sort();
    if (normalized.isEmpty) {
      await StorageService()
          .remove(AppConfig.auditTrailWidgetActivityFiltersKey);
    } else {
      await StorageService().setString(
          AppConfig.auditTrailWidgetActivityFiltersKey, jsonEncode(normalized));
    }
  }
}
