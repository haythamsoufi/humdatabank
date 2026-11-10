import 'package:intl/intl.dart';

/// Public UPR bilateral support geometry (`GET /upr/support-flow/data`).
class SupportFlowData {
  final List<SupportFlowNode> nodes;
  final List<SupportFlowEdge> edges;
  final List<SupportFundingLink> funding;
  final List<SupportFlowFigure> figures;
  final List<SupportCoveragePoint> coverage;
  final List<SupportFlowArea> areas;
  final List<int> years;
  final bool hasData;

  const SupportFlowData({
    required this.nodes,
    required this.edges,
    required this.funding,
    required this.figures,
    required this.coverage,
    required this.areas,
    required this.years,
    required this.hasData,
  });

  factory SupportFlowData.fromResponse(Map<String, dynamic> json) {
    final flows = json['flows'];
    if (flows is Map) {
      return SupportFlowData.fromJson(Map<String, dynamic>.from(flows));
    }
    return SupportFlowData.fromJson(json);
  }

  factory SupportFlowData.fromJson(Map<String, dynamic> json) {
    final nodes = <SupportFlowNode>[];
    for (final raw in _mapList(json['nodes'])) {
      final node = SupportFlowNode.tryParse(raw);
      if (node != null) nodes.add(node);
    }
    final edges = _mapList(json['edges'])
        .map(SupportFlowEdge.tryParse)
        .whereType<SupportFlowEdge>()
        .toList(growable: false);
    return SupportFlowData(
      nodes: nodes,
      edges: edges,
      funding: _mapList(json['funding'])
          .map(SupportFundingLink.fromJson)
          .toList(growable: false),
      figures: _mapList(json['figures'])
          .map(SupportFlowFigure.fromJson)
          .toList(growable: false),
      coverage: _mapList(json['coverage'])
          .map(SupportCoveragePoint.fromJson)
          .toList(growable: false),
      areas: _mapList(json['areas'])
          .map(SupportFlowArea.fromJson)
          .where((area) => area.code.isNotEmpty)
          .toList(growable: false),
      years: _yearList(json['years']),
      hasData: json['has_data'] == true || edges.isNotEmpty,
    );
  }

  SupportFlowNode? nodeByIso(String? iso3) {
    final code = iso3?.trim().toUpperCase() ?? '';
    if (code.isEmpty) return null;
    for (final node in nodes) {
      if (node.iso3 == code) return node;
    }
    return null;
  }
}

class SupportFlowNode {
  final String iso3;
  final String name;
  final double lat;
  final double lng;
  final double outWeight;
  final double inWeight;
  final String role;

  const SupportFlowNode({
    required this.iso3,
    required this.name,
    required this.lat,
    required this.lng,
    this.outWeight = 0,
    this.inWeight = 0,
    this.role = 'host',
  });

  double get totalWeight => outWeight + inWeight;

  SupportFlowNode copyWithWeights({
    required double outWeight,
    required double inWeight,
  }) {
    final role = outWeight > 0 && inWeight > 0
        ? 'both'
        : (outWeight > 0 ? 'donor' : 'host');
    return SupportFlowNode(
      iso3: iso3,
      name: name,
      lat: lat,
      lng: lng,
      outWeight: outWeight,
      inWeight: inWeight,
      role: role,
    );
  }

  static SupportFlowNode? tryParse(Map<String, dynamic> json) {
    final iso3 = json['iso3']?.toString().trim().toUpperCase() ?? '';
    final lat = (json['lat'] as num?)?.toDouble();
    final lng = (json['lng'] as num?)?.toDouble();
    if (iso3.length != 3 || lat == null || lng == null) return null;
    return SupportFlowNode(
      iso3: iso3,
      name: (json['name']?.toString().trim().isNotEmpty ?? false)
          ? json['name'].toString().trim()
          : iso3,
      lat: lat,
      lng: lng,
      outWeight: (json['out_weight'] as num?)?.toDouble() ?? 0,
      inWeight: (json['in_weight'] as num?)?.toDouble() ?? 0,
      role: json['role']?.toString() ?? 'host',
    );
  }
}

class SupportFlowEdge {
  final String from;
  final String to;
  final double weight;
  final List<int> years;

  const SupportFlowEdge({
    required this.from,
    required this.to,
    this.weight = 1,
    this.years = const [],
  });

  static SupportFlowEdge? tryParse(Map<String, dynamic> json) {
    final from = json['from']?.toString().trim().toUpperCase() ?? '';
    final to = json['to']?.toString().trim().toUpperCase() ?? '';
    if (from.length != 3 || to.length != 3) return null;
    return SupportFlowEdge(
      from: from,
      to: to,
      weight: (json['weight'] as num?)?.toDouble() ?? 1,
      years: _yearList(json['years']),
    );
  }
}

class SupportFundingLink {
  final int year;
  final String from;
  final String fromName;
  final String to;
  final String toName;
  final double value;

  const SupportFundingLink({
    required this.year,
    required this.from,
    required this.fromName,
    required this.to,
    required this.toName,
    required this.value,
  });

  factory SupportFundingLink.fromJson(Map<String, dynamic> json) {
    final from = json['from']?.toString().trim().toUpperCase() ?? '';
    final to = json['to']?.toString().trim().toUpperCase() ?? '';
    return SupportFundingLink(
      year: (json['year'] as num?)?.toInt() ?? 0,
      from: from,
      fromName: json['from_name']?.toString().trim().isNotEmpty == true
          ? json['from_name'].toString().trim()
          : from,
      to: to,
      toName: json['to_name']?.toString().trim().isNotEmpty == true
          ? json['to_name'].toString().trim()
          : to,
      value: (json['value'] as num?)?.toDouble() ?? 0,
    );
  }
}

class SupportFlowFigure {
  final int year;
  final String from;
  final String to;
  final String area;
  final double requirement;
  final double funding;
  final double expenditure;

  const SupportFlowFigure({
    required this.year,
    required this.from,
    required this.to,
    required this.area,
    required this.requirement,
    required this.funding,
    required this.expenditure,
  });

  factory SupportFlowFigure.fromJson(Map<String, dynamic> json) {
    return SupportFlowFigure(
      year: (json['year'] as num?)?.toInt() ?? 0,
      from: json['from']?.toString().trim().toUpperCase() ?? '',
      to: json['to']?.toString().trim().toUpperCase() ?? '',
      area: json['area']?.toString().trim() ?? '',
      requirement: (json['requirement'] as num?)?.toDouble() ?? 0,
      funding: (json['funding'] as num?)?.toDouble() ?? 0,
      expenditure: (json['expenditure'] as num?)?.toDouble() ?? 0,
    );
  }

  double metric(String key) {
    switch (key) {
      case 'requirement':
        return requirement;
      case 'funding':
        return funding;
      case 'expenditure':
        return expenditure;
      default:
        return 0;
    }
  }
}

class SupportCoveragePoint {
  final int year;
  final String iso3;
  final String name;
  final double requirement;
  final double funding;
  final double met;
  final String informClass;

  const SupportCoveragePoint({
    required this.year,
    required this.iso3,
    required this.name,
    required this.requirement,
    required this.funding,
    required this.met,
    required this.informClass,
  });

  factory SupportCoveragePoint.fromJson(Map<String, dynamic> json) {
    final iso3 = json['iso3']?.toString().trim().toUpperCase() ?? '';
    return SupportCoveragePoint(
      year: (json['year'] as num?)?.toInt() ?? 0,
      iso3: iso3,
      name: json['name']?.toString().trim().isNotEmpty == true
          ? json['name'].toString().trim()
          : iso3,
      requirement: (json['requirement'] as num?)?.toDouble() ?? 0,
      funding: (json['funding'] as num?)?.toDouble() ?? 0,
      met: (json['met'] as num?)?.toDouble() ?? 0,
      informClass: json['inform_class']?.toString().trim() ?? '',
    );
  }
}

class SupportFlowArea {
  final String code;
  final String label;

  const SupportFlowArea({required this.code, required this.label});

  factory SupportFlowArea.fromJson(Map<String, dynamic> json) {
    final code = json['code']?.toString().trim() ?? '';
    final label = json['label']?.toString().trim() ?? '';
    return SupportFlowArea(code: code, label: label.isEmpty ? code : label);
  }
}

class SupportPartyOption {
  final String iso3;
  final String name;

  const SupportPartyOption({required this.iso3, required this.name});
}

/// Edges that include [year]. Each pair is one line for that year.
List<SupportFlowEdge> supportEdgesForYear(List<SupportFlowEdge> edges, int year) {
  return [
    for (final edge in edges)
      if (edge.years.contains(year))
        SupportFlowEdge(from: edge.from, to: edge.to, weight: 1, years: [year]),
  ];
}

/// Nodes touched by [edges], with in/out weights recomputed for this filter.
List<SupportFlowNode> supportNodesForEdges(
  List<SupportFlowNode> all,
  List<SupportFlowEdge> edges,
) {
  final weights = <String, List<double>>{};
  for (final edge in edges) {
    weights.putIfAbsent(edge.from, () => [0, 0]);
    weights.putIfAbsent(edge.to, () => [0, 0]);
    weights[edge.from]![0] += edge.weight;
    weights[edge.to]![1] += edge.weight;
  }
  return [
    for (final node in all)
      if (weights[node.iso3] != null)
        node.copyWithWeights(
          outWeight: weights[node.iso3]![0],
          inWeight: weights[node.iso3]![1],
        ),
  ];
}

/// Year pool, then each dropdown narrowed by the other party.
({
  List<SupportFlowEdge> pool,
  String? pns,
  String? recipient,
  List<SupportPartyOption> pnsOptions,
  List<SupportPartyOption> recipientOptions,
  List<SupportFlowEdge> edges,
}) resolveSupportFlowFilter({
  required SupportFlowData data,
  required int? year,
  required String? pns,
  required String? recipient,
}) {
  final pool = year == null
      ? const <SupportFlowEdge>[]
      : supportEdgesForYear(data.edges, year);
  final pnsPref = pool.any((edge) => edge.from == pns) ? pns : null;
  final recipientPref = pool.any((edge) => edge.to == recipient) ? recipient : null;
  final donorEdges = recipientPref == null
      ? pool
      : pool.where((edge) => edge.to == recipientPref).toList(growable: false);
  final hostEdges = pnsPref == null
      ? pool
      : pool.where((edge) => edge.from == pnsPref).toList(growable: false);
  final effectivePns =
      donorEdges.any((edge) => edge.from == pnsPref) ? pnsPref : null;
  final effectiveRecipient =
      hostEdges.any((edge) => edge.to == recipientPref) ? recipientPref : null;
  final edges = pool.where((edge) {
    if (effectivePns != null && edge.from != effectivePns) return false;
    if (effectiveRecipient != null && edge.to != effectiveRecipient) return false;
    return true;
  }).toList(growable: false);
  return (
    pool: pool,
    pns: effectivePns,
    recipient: effectiveRecipient,
    pnsOptions: _partyOptions(data, donorEdges, from: true),
    recipientOptions: _partyOptions(data, hostEdges, from: false),
    edges: edges,
  );
}

List<SupportPartyOption> _partyOptions(
  SupportFlowData data,
  List<SupportFlowEdge> edges, {
  required bool from,
}) {
  final seen = <String>{};
  final rows = <SupportPartyOption>[];
  for (final edge in edges) {
    final iso = from ? edge.from : edge.to;
    if (!seen.add(iso)) continue;
    rows.add(SupportPartyOption(
      iso3: iso,
      name: data.nodeByIso(iso)?.name ?? iso,
    ));
  }
  rows.sort((a, b) => a.name.toLowerCase().compareTo(b.name.toLowerCase()));
  return rows;
}

double sumSupportMetric(List<SupportFlowFigure> rows, String key) {
  final totals = rows.where((row) => row.area.isEmpty);
  final fromTotals = totals.fold<double>(0, (sum, row) => sum + row.metric(key));
  if (fromTotals != 0) return fromTotals;
  return rows
      .where((row) => row.area.isNotEmpty)
      .fold<double>(0, (sum, row) => sum + row.metric(key));
}

String formatSupportAmount(double value) {
  if (value <= 0) return '—';
  return NumberFormat.compactCurrency(symbol: '', decimalDigits: 1)
      .format(value)
      .trim();
}

String formatStaffCount(double value) {
  if (value <= 0) return '0';
  if (value == value.roundToDouble()) return value.round().toString();
  return NumberFormat.compact().format(value).trim();
}

List<int> _yearList(Object? raw) {
  if (raw is! List) return const [];
  final years = <int>[
    for (final item in raw)
      if (item is num) item.toInt(),
  ];
  years.sort((a, b) => b.compareTo(a));
  return years;
}

List<Map<String, dynamic>> _mapList(Object? raw) => raw is List
    ? raw
        .whereType<Map>()
        .map((entry) => Map<String, dynamic>.from(entry))
        .toList(growable: false)
    : const [];
