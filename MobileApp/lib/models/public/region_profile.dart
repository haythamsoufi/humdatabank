import 'country_profile.dart';

/// Regional analysis from `GET /api/mobile/v1/data/region-profile/{slug}`.
class RegionProfile {
  final String name;
  final int countryCount;
  final List<String> periods;
  final List<RegionIndicator> indicators;

  const RegionProfile({
    required this.name,
    required this.countryCount,
    required this.periods,
    required this.indicators,
  });

  factory RegionProfile.fromJson(Map<String, dynamic> json) {
    final region = Map<String, dynamic>.from(json['region'] as Map? ?? const {});
    return RegionProfile(
      name: region['name']?.toString() ?? '',
      countryCount: (region['country_count'] as num?)?.toInt() ?? 0,
      periods: json['periods'] is List
          ? (json['periods'] as List).map((e) => e.toString()).toList()
          : const [],
      indicators: json['indicators'] is List
          ? (json['indicators'] as List)
              .whereType<Map>()
              .map((e) => RegionIndicator.fromJson(Map<String, dynamic>.from(e)))
              .toList()
          : const [],
    );
  }

  RegionIndicator? indicatorByKey(String key) {
    for (final indicator in indicators) {
      if (indicator.key == key) return indicator;
    }
    return null;
  }
}

class RegionIndicator implements KeyIndicatorInfo {
  final int id;
  @override
  final String key;
  @override
  final String name;
  final String? unit;
  @override
  final String? sector;
  @override
  final String? group;
  @override
  final int? groupOrder;
  final String latestPeriod;

  /// Sum across the countries that reported in [latestPeriod].
  final double latestValue;
  final int reportingCountries;

  /// Regional totals, oldest first.
  final List<CountryIndicatorPoint> series;
  final List<RegionCountryValue> topCountries;

  const RegionIndicator({
    required this.id,
    required this.key,
    required this.name,
    required this.latestPeriod,
    required this.latestValue,
    required this.reportingCountries,
    required this.series,
    required this.topCountries,
    this.unit,
    this.sector,
    this.group,
    this.groupOrder,
  });

  factory RegionIndicator.fromJson(Map<String, dynamic> json) {
    List<Map<String, dynamic>> maps(Object? raw) => raw is List
        ? raw.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList()
        : const [];
    return RegionIndicator(
      id: (json['id'] as num?)?.toInt() ?? 0,
      key: json['key']?.toString() ?? '',
      name: json['name']?.toString() ?? '',
      unit: json['unit']?.toString(),
      sector: json['sector']?.toString(),
      group: json['group']?.toString(),
      groupOrder: (json['group_order'] as num?)?.toInt(),
      latestPeriod: json['latest_period']?.toString() ?? '',
      latestValue: (json['latest_value'] as num?)?.toDouble() ?? 0,
      reportingCountries: (json['reporting_countries'] as num?)?.toInt() ?? 0,
      series: maps(json['series']).map(CountryIndicatorPoint.fromJson).toList(),
      topCountries:
          maps(json['top_countries']).map(RegionCountryValue.fromJson).toList(),
    );
  }
}

class RegionCountryValue {
  final String iso3;
  final String name;
  final double value;

  const RegionCountryValue({
    required this.iso3,
    required this.name,
    required this.value,
  });

  factory RegionCountryValue.fromJson(Map<String, dynamic> json) {
    return RegionCountryValue(
      iso3: json['iso3']?.toString() ?? '',
      name: json['name']?.toString() ?? '',
      value: (json['value'] as num?)?.toDouble() ?? 0,
    );
  }
}
