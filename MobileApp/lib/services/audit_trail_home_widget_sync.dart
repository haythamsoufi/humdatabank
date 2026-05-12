import 'dart:convert';
import 'dart:io' show Platform;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:home_widget/home_widget.dart';

import 'audit_trail_widget_prefs.dart';

/// iOS: must match [ios/Runner/Runner.entitlements] and the widget extension.
/// Create the group in Apple Developer → Identifiers → App Groups if it does not exist.
/// Android: [HomeWidget.setAppGroupId] is a no-op; data is stored in app SharedPreferences.
const String auditTrailHomeWidgetAppGroupId = 'group.com.hum.databank';

const String _auditTrailWidgetDataKey = 'audit_trail_json';
const String _auditTrailWidgetIOSKind = 'AuditTrailWidget';

/// Short class name; full class is `com.hum.databank.AuditTrailWidgetProvider`.
const String _auditTrailAndroidProviderClass = 'AuditTrailWidgetProvider';

/// Pushes the latest audit rows into the home screen widget (iOS + Android, best-effort).
Future<void> syncAuditTrailToHomeWidget(List<Map<String, dynamic>> logs) async {
  if (kIsWeb) return;
  if (!Platform.isIOS && !Platform.isAndroid) return;
  try {
    final filter = await AuditTrailWidgetPrefs.getActivityTypeFilter();
    final filtered =
        filter.isEmpty ? logs : logs.where((e) => _matchesWidgetFilter(e, filter)).toList();
    final forWidget = filtered
        .take(12)
        .map(_normalizeAuditRowForWidget)
        .toList(growable: false);
    final jsonStr = jsonEncode(forWidget);
    await HomeWidget.saveWidgetData<String>(_auditTrailWidgetDataKey, jsonStr);
    if (Platform.isIOS) {
      await HomeWidget.updateWidget(iOSName: _auditTrailWidgetIOSKind);
    }
    if (Platform.isAndroid) {
      await HomeWidget.updateWidget(androidName: _auditTrailAndroidProviderClass);
    }
  } catch (_) {
    // Never break audit UI if widget sync fails.
  }
}

bool _matchesWidgetFilter(Map<String, dynamic> e, Set<String> filter) {
  final activity =
      (e['activity_type'] ?? e['action'] ?? '').toString().toLowerCase();
  if (activity.isEmpty) return false;
  for (final f in filter) {
    if (activity.contains(f)) return true;
  }
  return false;
}

Map<String, dynamic> _normalizeAuditRowForWidget(Map<String, dynamic> e) {
  final desc =
      (e['consistent_description'] ?? e['description'] ?? '').toString().trim();
  final activity =
      (e['activity_type'] ?? e['action'] ?? '').toString().trim();
  final user = (e['user_name'] ?? e['user_email'] ?? e['user'] ?? '')
      .toString()
      .trim();
  final ts = (e['timestamp'] ?? '').toString().trim();
  final clipped = desc.length > 220 ? '${desc.substring(0, 217)}…' : desc;
  return {
    'description': clipped,
    if (activity.isNotEmpty) 'activity_type': activity,
    'user': user,
    'timestamp': ts,
  };
}
