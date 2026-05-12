import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import '../config/app_config.dart';
import '../models/indicator_bank/indicator.dart';
import '../models/indicator_bank/sector.dart';
import '../utils/debug_logger.dart';

/// Serializable payload for cold-start / offline Indicator Bank restore.
class IndicatorBankSnapshotPayload {
  IndicatorBankSnapshotPayload({
    required this.version,
    required this.locale,
    required this.savedAt,
    required this.sectors,
    required this.indicators,
  });

  final int version;
  final String locale;
  final DateTime savedAt;
  final List<Sector> sectors;
  final List<Indicator> indicators;

  Map<String, dynamic> toJson() => {
        'version': version,
        'locale': locale,
        'saved_at': savedAt.toIso8601String(),
        'sectors': sectors.map((s) => s.toJson()).toList(),
        'indicators': indicators.map((i) => i.toJson()).toList(),
      };

  static IndicatorBankSnapshotPayload? tryParse(String raw) {
    try {
      final map = jsonDecode(raw) as Map<String, dynamic>;
      if ((map['version'] as num?)?.toInt() != 1) return null;
      final locale = map['locale'] as String?;
      final savedAt = DateTime.tryParse(map['saved_at'] as String? ?? '');
      if (locale == null || locale.isEmpty || savedAt == null) return null;
      final sectorsRaw = map['sectors'] as List<dynamic>?;
      final indicatorsRaw = map['indicators'] as List<dynamic>?;
      if (sectorsRaw == null || indicatorsRaw == null) return null;
      final sectors = sectorsRaw.map((e) {
        final m = Map<String, dynamic>.from(e as Map);
        return Sector.fromJson(m);
      }).toList();
      final indicators = indicatorsRaw.map((e) {
        final m = Map<String, dynamic>.from(e as Map);
        return Indicator.fromJson(m);
      }).toList();
      return IndicatorBankSnapshotPayload(
        version: 1,
        locale: locale,
        savedAt: savedAt,
        sectors: sectors,
        indicators: indicators,
      );
    } catch (e, st) {
      DebugLogger.logWarn(
          'INDICATOR_BANK_SNAPSHOT', 'parse failed: $e\n$st');
      return null;
    }
  }
}

/// Large JSON snapshot on disk (avoids SharedPreferences size limits).
class IndicatorBankSnapshotStore {
  static Future<File> _file() async {
    final dir = await getApplicationSupportDirectory();
    return File(p.join(dir.path, AppConfig.indicatorBankSnapshotFilename));
  }

  static Future<void> save(IndicatorBankSnapshotPayload payload) async {
    try {
      final f = await _file();
      await f.parent.create(recursive: true);
      await f.writeAsString(jsonEncode(payload.toJson()), flush: true);
    } catch (e, st) {
      DebugLogger.logWarn('INDICATOR_BANK_SNAPSHOT', 'save failed: $e\n$st');
    }
  }

  /// Loads the last saved snapshot for [locale].
  ///
  /// When [maxAge] is null, the file is accepted regardless of age (offline /
  /// last-resort hydrate, same idea as [UnifiedPlanningDocumentsCache]).
  static Future<IndicatorBankSnapshotPayload?> loadIfValid({
    required String locale,
    Duration? maxAge,
  }) async {
    try {
      final f = await _file();
      if (!await f.exists()) return null;
      final raw = await f.readAsString();
      final payload = IndicatorBankSnapshotPayload.tryParse(raw);
      if (payload == null) return null;
      if (payload.locale != locale) return null;
      if (maxAge != null &&
          DateTime.now().difference(payload.savedAt) > maxAge) {
        return null;
      }
      return payload;
    } catch (e, st) {
      DebugLogger.logWarn('INDICATOR_BANK_SNAPSHOT', 'load failed: $e\n$st');
      return null;
    }
  }
}
