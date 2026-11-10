/// One active project on a country profile
/// (`GET /api/mobile/v1/data/country-profile/{iso3}/projects`).
class CountryProject {
  final String reference;
  final String? title;
  final String? portfolio;
  final String? fund;
  final String status;
  final String? organizationName;
  final String? fundingModality;
  final String? categories;
  final String? startDate;
  final String? endDate;
  final double? amountGranted;
  final String? plannedOverview;

  const CountryProject({
    required this.reference,
    required this.status,
    this.title,
    this.portfolio,
    this.fund,
    this.organizationName,
    this.fundingModality,
    this.categories,
    this.startDate,
    this.endDate,
    this.amountGranted,
    this.plannedOverview,
  });

  factory CountryProject.fromJson(Map<String, dynamic> json) {
    return CountryProject(
      reference: json['reference']?.toString().trim() ?? '',
      title: _text(json['title']),
      portfolio: _text(json['portfolio']),
      fund: _text(json['fund']),
      status: _text(json['status']) ?? 'Open',
      organizationName: _text(json['organization_name']),
      fundingModality: _text(json['funding_modality']),
      categories: _text(json['categories']),
      startDate: _text(json['start_date']),
      endDate: _text(json['end_date']),
      amountGranted: (json['amount_granted'] as num?)?.toDouble(),
      plannedOverview: _text(json['planned_overview']),
    );
  }

  /// Title when the registry has one, otherwise the reference code.
  String get heading {
    final name = title;
    if (name != null && name.isNotEmpty) return name;
    return reference;
  }

  bool get showsReference =>
      title != null && title!.isNotEmpty && reference.isNotEmpty;
}

String? _text(Object? raw) {
  final value = raw?.toString().trim();
  if (value == null || value.isEmpty) return null;
  return value;
}

List<CountryProject> countryProjectsFromPayload(Map<String, dynamic> json) {
  final raw = json['projects'];
  if (raw is! List) return const [];
  return raw
      .whereType<Map>()
      .map((row) => CountryProject.fromJson(Map<String, dynamic>.from(row)))
      .where((project) => project.reference.isNotEmpty || (project.title ?? '').isNotEmpty)
      .toList(growable: false);
}
