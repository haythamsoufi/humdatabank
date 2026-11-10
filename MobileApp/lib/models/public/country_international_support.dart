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
  final CountryInternationalStaffPresence staffPresence;
  final Map<String, String> embeds;

  const CountryInternationalSupport({
    required this.iso3,
    required this.isPns,
    required this.role,
    required this.hasSupport,
    required this.years,
    required this.summary,
    required this.partners,
    required this.staffPresence,
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
      staffPresence: CountryInternationalStaffPresence.fromJson(
        Map<String, dynamic>.from(json['staff_presence'] as Map? ?? const {}),
      ),
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
  final int staffPresence;
  final double funding;
  final double requirement;
  final double expenditure;

  const CountryInternationalSummary({
    this.year,
    this.countriesSupported,
    this.supportingPartners,
    this.staffPresence = 0,
    this.funding = 0,
    this.requirement = 0,
    this.expenditure = 0,
  });

  factory CountryInternationalSummary.fromJson(Map<String, dynamic> json) {
    return CountryInternationalSummary(
      year: (json['year'] as num?)?.toInt(),
      countriesSupported: (json['countries_supported'] as num?)?.toInt(),
      supportingPartners: (json['supporting_partners'] as num?)?.toInt(),
      staffPresence: (json['staff_presence'] as num?)?.toInt() ?? 0,
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

class CountryInternationalStaffPresence {
  final int? year;
  final int count;

  /// Headcount summed across every society, including rows past any old cap.
  final double staffTotal;
  final List<CountryInternationalStaffEntry> entries;

  const CountryInternationalStaffPresence({
    this.year,
    this.count = 0,
    this.staffTotal = 0,
    this.entries = const [],
  });

  factory CountryInternationalStaffPresence.fromJson(Map<String, dynamic> json) {
    final entries = _mapList(json['entries'])
        .map(CountryInternationalStaffEntry.fromJson)
        .toList(growable: false);
    final summed = entries.fold<double>(0, (sum, entry) => sum + entry.staff);
    return CountryInternationalStaffPresence(
      year: (json['year'] as num?)?.toInt(),
      count: (json['count'] as num?)?.toInt() ?? entries.length,
      staffTotal: (json['staff_total'] as num?)?.toDouble() ?? summed,
      entries: entries,
    );
  }
}

/// One society or country on the consolidated funding list.
class InternationalFundingBar {
  final String? iso3;
  final String name;
  final double funding;
  final double staff;

  const InternationalFundingBar({
    required this.name,
    this.iso3,
    this.funding = 0,
    this.staff = 0,
  });
}

String _fundingBarKey(String? iso3, String name) {
  final code = iso3?.trim().toUpperCase() ?? '';
  if (code.length == 3 && RegExp(r'^[A-Z]{3}$').hasMatch(code)) return code;
  return name.trim().toLowerCase();
}

/// Partners with funding, plus staff presence on the same row when it exists.
List<InternationalFundingBar> mergeInternationalFundingBars({
  required List<CountryInternationalPartner> partners,
  required List<CountryInternationalStaffEntry> staff,
}) {
  final merged = <String, InternationalFundingBar>{};
  for (final partner in partners) {
    final name = partner.name.trim();
    if (name.isEmpty && (partner.iso3 ?? '').trim().isEmpty) continue;
    final key = _fundingBarKey(partner.iso3, name);
    merged[key] = InternationalFundingBar(
      iso3: partner.iso3,
      name: name.isEmpty ? (partner.iso3 ?? key) : name,
      funding: partner.funding ?? 0,
      staff: 0,
    );
  }
  for (final entry in staff) {
    final name = entry.name.trim();
    if (name.isEmpty && (entry.iso3 ?? '').trim().isEmpty) continue;
    final key = _fundingBarKey(entry.iso3, name);
    final existing = merged[key];
    if (existing == null) {
      merged[key] = InternationalFundingBar(
        iso3: entry.iso3,
        name: name.isEmpty ? (entry.iso3 ?? key) : name,
        funding: 0,
        staff: entry.staff,
      );
      continue;
    }
    merged[key] = InternationalFundingBar(
      iso3: existing.iso3 ?? entry.iso3,
      name: existing.name,
      funding: existing.funding,
      staff: existing.staff + entry.staff,
    );
  }
  final rows = merged.values
      .where((row) => row.funding > 0 || row.staff > 0)
      .toList(growable: true);
  rows.sort((a, b) {
    final byFunding = b.funding.compareTo(a.funding);
    if (byFunding != 0) return byFunding;
    final byStaff = b.staff.compareTo(a.staff);
    if (byStaff != 0) return byStaff;
    return a.name.toLowerCase().compareTo(b.name.toLowerCase());
  });
  return rows;
}

class CountryInternationalStaffEntry {
  final String? iso3;
  final String name;
  final double staff;

  const CountryInternationalStaffEntry({
    required this.name,
    this.iso3,
    this.staff = 0,
  });

  factory CountryInternationalStaffEntry.fromJson(Map<String, dynamic> json) {
    return CountryInternationalStaffEntry(
      iso3: json['iso3']?.toString(),
      name: json['name']?.toString() ?? '',
      staff: (json['staff'] as num?)?.toDouble() ?? 0,
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
