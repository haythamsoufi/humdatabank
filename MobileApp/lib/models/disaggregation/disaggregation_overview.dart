/// Aggregated disaggregation overview returned by the mobile API.
class DisaggregationOverview {
  DisaggregationOverview({
    this.periodName,
    required this.indicatorBankId,
    this.countryId,
    required this.total,
    required this.recordCount,
    required this.disaggregatedCount,
    required this.disaggregationRate,
    required this.bySex,
    required this.byAge,
    required this.byCountry,
    required this.byRegion,
    required this.trends,
    required this.countryDetailsAvailable,
  });

  final String? periodName;
  final int indicatorBankId;
  final int? countryId;
  final double total;
  final int recordCount;
  final int disaggregatedCount;
  final double disaggregationRate;
  final List<DisaggregationBreakdownItem> bySex;
  final List<DisaggregationBreakdownItem> byAge;
  final List<DisaggregationCountryItem> byCountry;
  final List<DisaggregationRegionItem> byRegion;
  final List<DisaggregationTrendItem> trends;
  final bool countryDetailsAvailable;

  factory DisaggregationOverview.fromJson(Map<String, dynamic> json) {
    return DisaggregationOverview(
      periodName: json['period_name'] as String?,
      indicatorBankId: (json['indicator_bank_id'] as num?)?.toInt() ?? 729,
      countryId: (json['country_id'] as num?)?.toInt(),
      total: _toDouble(json['total']),
      recordCount: (json['record_count'] as num?)?.toInt() ?? 0,
      disaggregatedCount: (json['disaggregated_count'] as num?)?.toInt() ?? 0,
      disaggregationRate: _toDouble(json['disaggregation_rate']),
      bySex: _parseBreakdown(json['by_sex']),
      byAge: _parseBreakdown(json['by_age']),
      byCountry: _parseCountries(json['by_country']),
      byRegion: _parseRegions(json['by_region']),
      trends: _parseTrends(json['trends']),
      countryDetailsAvailable: json['country_details_available'] == true,
    );
  }

  static double _toDouble(dynamic value) {
    if (value is num) return value.toDouble();
    return double.tryParse(value?.toString() ?? '') ?? 0;
  }

  static List<DisaggregationBreakdownItem> _parseBreakdown(dynamic raw) {
    if (raw is! List<dynamic>) return const [];
    return raw
        .whereType<Map<String, dynamic>>()
        .map(DisaggregationBreakdownItem.fromJson)
        .toList();
  }

  static List<DisaggregationCountryItem> _parseCountries(dynamic raw) {
    if (raw is! List<dynamic>) return const [];
    return raw
        .whereType<Map<String, dynamic>>()
        .map(DisaggregationCountryItem.fromJson)
        .toList();
  }

  static List<DisaggregationRegionItem> _parseRegions(dynamic raw) {
    if (raw is! List<dynamic>) return const [];
    return raw
        .whereType<Map<String, dynamic>>()
        .map(DisaggregationRegionItem.fromJson)
        .toList();
  }

  static List<DisaggregationTrendItem> _parseTrends(dynamic raw) {
    if (raw is! List<dynamic>) return const [];
    return raw
        .whereType<Map<String, dynamic>>()
        .map(DisaggregationTrendItem.fromJson)
        .toList();
  }
}

class DisaggregationBreakdownItem {
  const DisaggregationBreakdownItem({
    required this.category,
    required this.value,
  });

  final String category;
  final double value;

  factory DisaggregationBreakdownItem.fromJson(Map<String, dynamic> json) {
    return DisaggregationBreakdownItem(
      category: json['category']?.toString() ?? '',
      value: DisaggregationOverview._toDouble(json['value']),
    );
  }
}

class DisaggregationCountryItem {
  const DisaggregationCountryItem({
    required this.countryId,
    required this.name,
    required this.value,
    required this.recordCount,
    required this.disaggregatedCount,
    required this.disaggregationRate,
  });

  final int countryId;
  final String name;
  final double value;
  final int recordCount;
  final int disaggregatedCount;
  final double disaggregationRate;

  factory DisaggregationCountryItem.fromJson(Map<String, dynamic> json) {
    return DisaggregationCountryItem(
      countryId: (json['country_id'] as num?)?.toInt() ?? 0,
      name: json['name']?.toString() ?? '',
      value: DisaggregationOverview._toDouble(json['value']),
      recordCount: (json['record_count'] as num?)?.toInt() ?? 0,
      disaggregatedCount: (json['disaggregated_count'] as num?)?.toInt() ?? 0,
      disaggregationRate: DisaggregationOverview._toDouble(
        json['disaggregation_rate'],
      ),
    );
  }
}

class DisaggregationRegionItem {
  const DisaggregationRegionItem({
    required this.region,
    required this.value,
    required this.recordCount,
    required this.disaggregatedCount,
    required this.disaggregationRate,
    required this.countryCount,
  });

  final String region;
  final double value;
  final int recordCount;
  final int disaggregatedCount;
  final double disaggregationRate;
  final int countryCount;

  factory DisaggregationRegionItem.fromJson(Map<String, dynamic> json) {
    return DisaggregationRegionItem(
      region: json['region']?.toString() ?? '',
      value: DisaggregationOverview._toDouble(json['value']),
      recordCount: (json['record_count'] as num?)?.toInt() ?? 0,
      disaggregatedCount: (json['disaggregated_count'] as num?)?.toInt() ?? 0,
      disaggregationRate: DisaggregationOverview._toDouble(
        json['disaggregation_rate'],
      ),
      countryCount: (json['country_count'] as num?)?.toInt() ?? 0,
    );
  }
}

class DisaggregationTrendItem {
  const DisaggregationTrendItem({
    required this.period,
    required this.total,
    required this.recordCount,
    required this.disaggregatedCount,
    required this.disaggregationRate,
  });

  final String period;
  final double total;
  final int recordCount;
  final int disaggregatedCount;
  final double disaggregationRate;

  factory DisaggregationTrendItem.fromJson(Map<String, dynamic> json) {
    return DisaggregationTrendItem(
      period: json['period']?.toString() ?? '',
      total: DisaggregationOverview._toDouble(json['total']),
      recordCount: (json['record_count'] as num?)?.toInt() ?? 0,
      disaggregatedCount: (json['disaggregated_count'] as num?)?.toInt() ?? 0,
      disaggregationRate: DisaggregationOverview._toDouble(
        json['disaggregation_rate'],
      ),
    );
  }
}

/// Lightweight country option for filter pickers.
class DisaggregationCountryOption {
  const DisaggregationCountryOption({
    required this.id,
    required this.name,
    this.iso2,
    this.region,
  });

  final int id;
  final String name;
  final String? iso2;
  final String? region;

  factory DisaggregationCountryOption.fromJson(Map<String, dynamic> json) {
    return DisaggregationCountryOption(
      id: (json['id'] as num?)?.toInt() ?? 0,
      name: json['name']?.toString() ?? '',
      iso2: json['iso2']?.toString(),
      region: json['region']?.toString(),
    );
  }
}

/// Active filter state for the disaggregation screen.
class DisaggregationFilters {
  const DisaggregationFilters({
    this.periodName,
    this.countryId,
    this.indicatorBankId = 729,
  });

  final String? periodName;
  final int? countryId;
  final int indicatorBankId;

  DisaggregationFilters copyWith({
    String? periodName,
    bool clearPeriod = false,
    int? countryId,
    bool clearCountry = false,
    int? indicatorBankId,
  }) {
    return DisaggregationFilters(
      periodName: clearPeriod ? null : (periodName ?? this.periodName),
      countryId: clearCountry ? null : (countryId ?? this.countryId),
      indicatorBankId: indicatorBankId ?? this.indicatorBankId,
    );
  }

  bool get hasActiveFilters =>
      periodName != null ||
      countryId != null ||
      indicatorBankId != 729;

  bool hasActiveFiltersFor({required bool countryDetailsAvailable}) {
    if (!countryDetailsAvailable && countryId != null) {
      return periodName != null || indicatorBankId != 729;
    }
    return hasActiveFilters;
  }
}

enum DisaggregationChartTab { bySex, byAge, byCountry, byRegion, trends }
