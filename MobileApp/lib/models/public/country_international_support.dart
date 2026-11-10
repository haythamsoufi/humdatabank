/// International bilateral support for one country
/// (`GET /api/mobile/v1/data/country-profile/{iso3}/international`).
class CountryInternationalSupport {
  final String iso3;
  final bool isPns;
  final String role;
  final bool hasSupport;
  final List<int> years;
  final CountryInternationalSummary summary;
  final List<CountryInternationalPartner> partners;
  final Map<String, String> embeds;

  const CountryInternationalSupport({
    required this.iso3,
    required this.isPns,
    required this.role,
    required this.hasSupport,
    required this.years,
    required this.summary,
    required this.partners,
    required this.embeds,
  });

  factory CountryInternationalSupport.fromJson(Map<String, dynamic> json) {
    final embedsRaw = json['embeds'];
    final embeds = <String, String>{};
    if (embedsRaw is Map) {
      for (final entry in embedsRaw.entries) {
        final value = entry.value?.toString().trim() ?? '';
        if (value.isEmpty) continue;
        embeds[entry.key.toString()] = value;
      }
    }
    return CountryInternationalSupport(
      iso3: json['iso3']?.toString() ?? '',
      isPns: json['is_pns'] == true,
      role: json['role']?.toString() ?? '',
      hasSupport: json['has_support'] == true,
      years: _intList(json['years']),
      summary: CountryInternationalSummary.fromJson(
        Map<String, dynamic>.from(json['summary'] as Map? ?? const {}),
      ),
      partners: _mapList(json['partners'])
          .map(CountryInternationalPartner.fromJson)
          .toList(growable: false),
      embeds: embeds,
    );
  }

  /// Relative path for the primary UPR embed (overview for PNS, flow for hosts).
  String? get primaryEmbedPath {
    final primary = embeds['primary']?.trim();
    if (primary != null && primary.isNotEmpty) return primary;
    final flow = embeds['flow']?.trim();
    if (flow != null && flow.isNotEmpty) return flow;
    return null;
  }
}

class CountryInternationalSummary {
  final int? year;
  final int? countriesSupported;
  final int? supportingPartners;
  final double funding;
  final double requirement;
  final double expenditure;

  const CountryInternationalSummary({
    this.year,
    this.countriesSupported,
    this.supportingPartners,
    this.funding = 0,
    this.requirement = 0,
    this.expenditure = 0,
  });

  factory CountryInternationalSummary.fromJson(Map<String, dynamic> json) {
    return CountryInternationalSummary(
      year: (json['year'] as num?)?.toInt(),
      countriesSupported: (json['countries_supported'] as num?)?.toInt(),
      supportingPartners: (json['supporting_partners'] as num?)?.toInt(),
      funding: (json['funding'] as num?)?.toDouble() ?? 0,
      requirement: (json['requirement'] as num?)?.toDouble() ?? 0,
      expenditure: (json['expenditure'] as num?)?.toDouble() ?? 0,
    );
  }
}

class CountryInternationalPartner {
  final String? iso3;
  final String name;
  final double? funding;

  const CountryInternationalPartner({
    required this.name,
    this.iso3,
    this.funding,
  });

  factory CountryInternationalPartner.fromJson(Map<String, dynamic> json) {
    return CountryInternationalPartner(
      iso3: json['iso3']?.toString(),
      name: json['name']?.toString() ?? '',
      funding: (json['funding'] as num?)?.toDouble(),
    );
  }
}

List<int> _intList(Object? raw) {
  if (raw is! List) return const [];
  return raw
      .map((e) => (e as num?)?.toInt())
      .whereType<int>()
      .toList(growable: false);
}

List<Map<String, dynamic>> _mapList(Object? raw) => raw is List
    ? raw
        .whereType<Map>()
        .map((e) => Map<String, dynamic>.from(e))
        .toList(growable: false)
    : const [];
