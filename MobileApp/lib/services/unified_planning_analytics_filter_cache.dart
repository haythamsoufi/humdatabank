import 'dart:convert';

import '../config/app_config.dart';
import '../models/shared/unified_planning_document.dart';
import 'storage_service.dart';

/// Persisted inclusion filters for the unified planning analytics screen.
class UnifiedPlanningAnalyticsFilterCriteria {
  const UnifiedPlanningAnalyticsFilterCriteria({
    required this.allYears,
    required this.years,
    required this.includeUnknownYear,
    required this.allTypes,
    required this.typeKeys,
  });

  /// No year restriction (show every calendar year present in data).
  final bool allYears;

  /// When [allYears] is false, only these calendar years are kept.
  final Set<int> years;

  /// When [allYears] is false, whether documents with no parsed year are kept.
  final bool includeUnknownYear;

  /// No document-type restriction.
  final bool allTypes;

  /// When [allTypes] is false, only these [UnifiedPlanningDocument.typeKey] values are kept.
  final Set<String> typeKeys;

  static const UnifiedPlanningAnalyticsFilterCriteria inclusive =
      UnifiedPlanningAnalyticsFilterCriteria(
    allYears: true,
    years: {},
    includeUnknownYear: true,
    allTypes: true,
    typeKeys: {},
  );

  bool get isRestricted => !allYears || !allTypes;

  bool matches(UnifiedPlanningDocument d) {
    if (!allYears) {
      final y = d.year;
      if (y == null) {
        if (!includeUnknownYear) return false;
      } else if (!years.contains(y)) {
        return false;
      }
    }
    if (!allTypes) {
      if (!typeKeys.contains(UnifiedPlanningDocument.typeKey(d))) {
        return false;
      }
    }
    return true;
  }

  UnifiedPlanningAnalyticsFilterCriteria copyWith({
    bool? allYears,
    Set<int>? years,
    bool? includeUnknownYear,
    bool? allTypes,
    Set<String>? typeKeys,
  }) {
    return UnifiedPlanningAnalyticsFilterCriteria(
      allYears: allYears ?? this.allYears,
      years: years ?? this.years,
      includeUnknownYear: includeUnknownYear ?? this.includeUnknownYear,
      allTypes: allTypes ?? this.allTypes,
      typeKeys: typeKeys ?? this.typeKeys,
    );
  }

  Map<String, dynamic> toJson() {
    final y = years.toList()..sort();
    final t = typeKeys.toList()..sort();
    return {
      'allYears': allYears,
      'years': y,
      'includeUnknownYear': includeUnknownYear,
      'allTypes': allTypes,
      'types': t,
    };
  }

  factory UnifiedPlanningAnalyticsFilterCriteria.fromJson(
    Map<String, dynamic> json,
  ) {
    return UnifiedPlanningAnalyticsFilterCriteria(
      allYears: json['allYears'] as bool? ?? true,
      years: (json['years'] as List<dynamic>? ?? [])
          .map((e) => e as int)
          .toSet(),
      includeUnknownYear: json['includeUnknownYear'] as bool? ?? true,
      allTypes: json['allTypes'] as bool? ?? true,
      typeKeys: (json['types'] as List<dynamic>? ?? [])
          .map((e) => e as String)
          .toSet(),
    );
  }

  /// Drop type keys that no longer appear in [documents] (stale cache).
  UnifiedPlanningAnalyticsFilterCriteria reconcileWithDocuments(
    List<UnifiedPlanningDocument> documents,
  ) {
    if (allTypes) return this;
    final available = documents.map(UnifiedPlanningDocument.typeKey).toSet();
    final t = typeKeys.intersection(available);
    if (t.isEmpty) {
      return copyWith(allTypes: true, typeKeys: {});
    }
    return copyWith(typeKeys: t);
  }
}

class UnifiedPlanningAnalyticsFilterCache {
  UnifiedPlanningAnalyticsFilterCache(this._storage);

  final StorageService _storage;

  Future<UnifiedPlanningAnalyticsFilterCriteria> load() async {
    final raw = await _storage.getString(AppConfig.unifiedPlanningAnalyticsFiltersKey);
    if (raw == null || raw.trim().isEmpty) {
      return UnifiedPlanningAnalyticsFilterCriteria.inclusive;
    }
    try {
      final map = jsonDecode(raw) as Map<String, dynamic>;
      return UnifiedPlanningAnalyticsFilterCriteria.fromJson(map);
    } catch (_) {
      return UnifiedPlanningAnalyticsFilterCriteria.inclusive;
    }
  }

  Future<void> save(UnifiedPlanningAnalyticsFilterCriteria criteria) async {
    await _storage.setString(
      AppConfig.unifiedPlanningAnalyticsFiltersKey,
      jsonEncode(criteria.toJson()),
    );
  }
}
