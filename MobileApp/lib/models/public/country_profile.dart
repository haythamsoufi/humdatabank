/// Public country profile from `GET /api/mobile/v1/data/country-profile/{iso3}`.
class CountryProfile {
  final CountryInfo country;
  final List<String> periods;
  final List<CountryIndicator> indicators;
  final List<String> coverImages;
  final List<CountryDocument> documents;

  const CountryProfile({
    required this.country,
    required this.periods,
    required this.indicators,
    required this.coverImages,
    required this.documents,
  });

  factory CountryProfile.fromJson(Map<String, dynamic> json) {
    return CountryProfile(
      country: CountryInfo.fromJson(
        Map<String, dynamic>.from(json['country'] as Map? ?? const {}),
      ),
      periods: _stringList(json['periods']),
      indicators: _mapList(json['indicators'])
          .map(CountryIndicator.fromJson)
          .toList(growable: false),
      coverImages: _stringList(json['cover_images']),
      documents: _mapList(json['documents'])
          .map(CountryDocument.fromJson)
          .toList(growable: false),
    );
  }

  /// Featured indicator with the given server key (e.g. `volunteers`), if reported.
  CountryIndicator? indicatorByKey(String key) {
    for (final indicator in indicators) {
      if (indicator.key == key) return indicator;
    }
    return null;
  }
}

class CountryInfo {
  final int id;
  final String name;
  final String? iso2;
  final String iso3;
  final String? region;
  final String? nationalSocietyName;
  final String? logoUrl;

  /// True when the country is assigned UPR PNS plan/report templates (22/23).
  final bool isPns;

  const CountryInfo({
    required this.id,
    required this.name,
    required this.iso3,
    this.iso2,
    this.region,
    this.nationalSocietyName,
    this.logoUrl,
    this.isPns = false,
  });

  factory CountryInfo.fromJson(Map<String, dynamic> json) {
    return CountryInfo(
      id: (json['id'] as num?)?.toInt() ?? 0,
      name: json['name']?.toString() ?? '',
      iso2: json['iso2']?.toString(),
      iso3: json['iso3']?.toString() ?? '',
      region: json['region']?.toString(),
      nationalSocietyName: json['national_society_name']?.toString(),
      logoUrl: json['logo_url']?.toString(),
      isPns: json['is_pns'] == true,
    );
  }
}

class CountryIndicatorPoint {
  final String period;
  final double value;

  const CountryIndicatorPoint({required this.period, required this.value});

  factory CountryIndicatorPoint.fromJson(Map<String, dynamic> json) {
    return CountryIndicatorPoint(
      period: json['period']?.toString() ?? '',
      value: (json['value'] as num?)?.toDouble() ?? 0,
    );
  }
}

/// Fields shared by country and region indicators that drive the key-indicator selector.
abstract interface class KeyIndicatorInfo {
  /// Headline key (`volunteers`, ...) or the FDRS KPI code for people-reached indicators.
  String? get key;
  String get name;
  String? get sector;

  /// `people_reached` for the indicators grouped under the People reached chip.
  String? get group;
  int? get groupOrder;
}

class CountryIndicator implements KeyIndicatorInfo {
  final int id;

  /// Set only for the featured indicators (volunteers, staff, income, ...).
  @override
  final String? key;
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
  final double latestValue;

  /// Oldest first.
  final List<CountryIndicatorPoint> series;

  const CountryIndicator({
    required this.id,
    required this.name,
    required this.latestPeriod,
    required this.latestValue,
    required this.series,
    this.key,
    this.unit,
    this.sector,
    this.group,
    this.groupOrder,
  });

  factory CountryIndicator.fromJson(Map<String, dynamic> json) {
    return CountryIndicator(
      id: (json['id'] as num?)?.toInt() ?? 0,
      key: json['key']?.toString(),
      name: json['name']?.toString() ?? '',
      unit: json['unit']?.toString(),
      sector: json['sector']?.toString(),
      group: json['group']?.toString(),
      groupOrder: (json['group_order'] as num?)?.toInt(),
      latestPeriod: json['latest_period']?.toString() ?? '',
      latestValue: (json['latest_value'] as num?)?.toDouble() ?? 0,
      series: _mapList(json['series'])
          .map(CountryIndicatorPoint.fromJson)
          .toList(growable: false),
    );
  }
}

class CountryDocument {
  final String title;
  final String? filename;
  final String url;
  final String? thumbnail;
  final int? year;
  final String? documentType;

  /// Display name (e.g. "English"); falls back to the ISO code when the server sends only that.
  final String? language;
  final String? languageCode;

  /// Appeal or event name. Emergency documents are grouped by this.
  final String? emergency;

  /// Stable emergency id (appeal code, or ``event:<id>`` for situation reports).
  final String? emergencyCode;

  const CountryDocument({
    required this.title,
    required this.url,
    this.filename,
    this.thumbnail,
    this.year,
    this.documentType,
    this.language,
    this.languageCode,
    this.emergency,
    this.emergencyCode,
  });

  factory CountryDocument.fromJson(Map<String, dynamic> json) {
    final filename = json['filename']?.toString();
    final languageCode = json['language_code']?.toString();
    final rawLanguage = json['language']?.toString();
    return CountryDocument(
      title: json['title']?.toString() ?? filename ?? '',
      filename: filename,
      url: json['url']?.toString() ?? '',
      thumbnail: json['thumbnail']?.toString(),
      year: (json['year'] as num?)?.toInt(),
      documentType: json['document_type']?.toString(),
      language: _languageDisplayName(rawLanguage),
      languageCode: languageCode ?? rawLanguage,
      emergency: _nonEmpty(json['emergency']),
      emergencyCode: _nonEmpty(json['emergency_code']),
    );
  }

  bool get isPdf {
    final name = (filename ?? url).toLowerCase();
    return name.endsWith('.pdf') || name.contains('/downloadfile/');
  }

  bool get isImage {
    final name = (filename ?? url).toLowerCase();
    return name.endsWith('.png') ||
        name.endsWith('.jpg') ||
        name.endsWith('.jpeg') ||
        name.endsWith('.webp') ||
        name.endsWith('.gif');
  }
}

const _languageNames = {
  'en': 'English',
  'fr': 'French',
  'es': 'Spanish',
  'ar': 'Arabic',
  'ru': 'Russian',
  'zh': 'Chinese',
  'hi': 'Hindi',
  'pt': 'Portuguese',
  'de': 'German',
};

String? _nonEmpty(Object? raw) {
  final value = raw?.toString().trim();
  if (value == null || value.isEmpty) return null;
  return value;
}

String? _languageDisplayName(String? raw) {
  final value = raw?.trim();
  if (value == null || value.isEmpty) return null;
  return _languageNames[value.toLowerCase()] ?? value;
}

List<String> _stringList(Object? raw) =>
    raw is List ? raw.map((e) => e.toString()).toList(growable: false) : const [];

List<Map<String, dynamic>> _mapList(Object? raw) => raw is List
    ? raw
        .whereType<Map>()
        .map((e) => Map<String, dynamic>.from(e))
        .toList(growable: false)
    : const [];
