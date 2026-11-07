import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:latlong2/latlong.dart';

import '../config/app_config.dart';
import '../config/fdrs_constants.dart';
import 'api_service.dart';
import '../di/service_locator.dart';

/// Which indicator the home map shows: a headline indicator bank row, or a
/// people-reached indicator identified by FDRS KPI code (stable across
/// environments, unlike bank ids) within a sector.
class FdrsIndicatorSelection {
  const FdrsIndicatorSelection.bank(int this.bankId)
      : kpiCode = null,
        sectorKey = null,
        label = null;

  const FdrsIndicatorSelection.reach({
    required String this.kpiCode,
    required String this.sectorKey,
    required String this.label,
  }) : bankId = null;

  final int? bankId;
  final String? kpiCode;
  final String? sectorKey;
  final String? label;

  bool get isReach => kpiCode != null;

  Map<String, String> get queryParams => isReach
      ? {'kpi_code': kpiCode!}
      : {'indicator_bank_id': '$bankId'};

  @override
  bool operator ==(Object other) =>
      other is FdrsIndicatorSelection &&
      other.bankId == bankId &&
      other.kpiCode == kpiCode;

  @override
  int get hashCode => Object.hash(bankId, kpiCode);
}

class ReachIndicator {
  const ReachIndicator({required this.kpiCode, required this.name});

  final String kpiCode;
  final String name;
}

/// A main sector with the people-reached indicators reported under it.
class ReachSector {
  const ReachSector({
    required this.key,
    required this.name,
    required this.indicators,
  });

  /// Sector id from the server, or `other` for indicators without a sector.
  final String key;

  /// Null when the indicators carry no sector; the UI supplies a fallback label.
  final String? name;
  final List<ReachIndicator> indicators;
}

/// Aggregated FDRS indicator values per country for the native home map/chart.
class GlobalOverviewDataset {
  GlobalOverviewDataset({
    required this.periodName,
    required this.byCountryId,
    required this.countryNames,
    required this.countryIso2,
  });

  final String? periodName;
  final Map<int, double> byCountryId;
  final Map<int, String> countryNames;
  final Map<int, String> countryIso2;

  double get globalTotal =>
      byCountryId.values.fold<double>(0, (a, b) => a + b);

  List<MapEntry<int, double>> topByValue(int n) {
    final list = byCountryId.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    return list.take(n).toList();
  }

  /// Points for markers where we have both a value and a centroid.
  List<({LatLng point, double value, int countryId, String iso2})> geoPoints(
    LatLng? Function(String? iso2) centroid,
  ) {
    final out = <({LatLng point, double value, int countryId, String iso2})>[];
    for (final e in byCountryId.entries) {
      final iso = countryIso2[e.key];
      if (iso == null || iso.isEmpty) continue;
      final ll = centroid(iso);
      if (ll == null || e.value <= 0) continue;
      out.add((
        point: ll,
        value: e.value,
        countryId: e.key,
        iso2: iso.toUpperCase(),
      ));
    }
    return out;
  }
}

class GlobalOverviewDataService {
  GlobalOverviewDataService({ApiService? api}) : _api = api ?? sl<ApiService>();

  final ApiService _api;

  /// Distinct FDRS period names, newest first.
  ///
  /// Public endpoint — no authentication required.
  Future<List<String>> listFdrsPeriods() async {
    final resp = await _api.get(
      AppConfig.mobileFdrsPeriodsEndpoint,
      queryParams: {'template_id': '${FdrsConstants.templateId}'},
      includeAuth: false,
      useCache: false,
    );
    if (resp.statusCode != 200) return [];
    final body = jsonDecode(resp.body);
    if (body is! Map<String, dynamic>) return [];
    final data = body['data'];
    if (data is! Map<String, dynamic>) return [];
    final periods = data['periods'];
    if (periods is! List<dynamic>) return [];
    return periods
        .map((e) => e?.toString() ?? '')
        .where((s) => s.isNotEmpty)
        .toList();
  }

  /// People-reached indicators grouped by sector (public endpoint). Empty when
  /// the request fails so the home chips simply hide the People reached group.
  Future<List<ReachSector>> listReachSectors({required String locale}) async {
    try {
      final resp = await _api.get(
        AppConfig.mobileFdrsReachIndicatorsEndpoint,
        queryParams: {
          'template_id': '${FdrsConstants.templateId}',
          'locale': locale,
        },
        includeAuth: false,
        useCache: false,
      );
      if (resp.statusCode != 200) return [];
      return parseReachSectors(jsonDecode(resp.body));
    } catch (_) {
      return [];
    }
  }

  /// Loads totals per country for one indicator and [periodName].
  ///
  /// When [periodName] is null or empty, uses the first period from
  /// [listFdrsPeriods] (latest reporting period).
  ///
  /// This single call replaces the previous pattern of separately fetching
  /// /countrymap + paginated /data/tables and aggregating on the client.
  /// Loads totals per country for one indicator and [periodName].
  ///
  /// Both the period lookup and the overview fetch use public endpoints —
  /// no authentication required.
  Future<GlobalOverviewDataset> loadOverview({
    required FdrsIndicatorSelection indicator,
    required String locale,
    String? periodName,
  }) async {
    var period = periodName;
    if (period == null || period.isEmpty) {
      final list = await listFdrsPeriods();
      if (list.isEmpty) {
        return GlobalOverviewDataset(
          periodName: null,
          byCountryId: {},
          countryNames: {},
          countryIso2: {},
        );
      }
      period = list.first;
    }

    final resolvedPeriod = period;

    final qp = <String, String>{
      ...indicator.queryParams,
      'template_id': '${FdrsConstants.templateId}',
      'locale': locale,
    };
    if (resolvedPeriod.isNotEmpty) {
      qp['period_name'] = resolvedPeriod;
    }

    final http.Response resp = await _api.get(
      AppConfig.mobileFdrsOverviewEndpoint,
      queryParams: qp,
      includeAuth: false,
      timeout: const Duration(seconds: 30),
      useCache: false,
    );

    if (resp.statusCode != 200) {
      throw OverviewLoadException('HTTP ${resp.statusCode} loading fdrs-overview');
    }

    final body = jsonDecode(resp.body);
    if (body is! Map<String, dynamic>) {
      throw OverviewLoadException('Unexpected response shape from fdrs-overview');
    }
    final data = (body['data'] as Map<String, dynamic>?) ?? {};

    final byCountryRaw = (data['by_country'] as Map<String, dynamic>?) ?? {};
    final countryNamesRaw = (data['country_names'] as Map<String, dynamic>?) ?? {};
    final countryIso2Raw = (data['country_iso2'] as Map<String, dynamic>?) ?? {};
    final returnedPeriod = data['period_name'] as String? ?? resolvedPeriod;

    final byCountry = <int, double>{};
    byCountryRaw.forEach((k, v) {
      final id = int.tryParse(k);
      if (id == null) return;
      final n = v is num ? v.toDouble() : double.tryParse(v?.toString() ?? '');
      if (n != null && n > 0) byCountry[id] = n;
    });

    final countryNames = <int, String>{};
    countryNamesRaw.forEach((k, v) {
      final id = int.tryParse(k);
      if (id != null && v != null) countryNames[id] = v.toString();
    });

    final countryIso2 = <int, String>{};
    countryIso2Raw.forEach((k, v) {
      final id = int.tryParse(k);
      if (id != null && v != null) countryIso2[id] = v.toString().toUpperCase();
    });

    return GlobalOverviewDataset(
      periodName: returnedPeriod,
      byCountryId: byCountry,
      countryNames: countryNames,
      countryIso2: countryIso2,
    );
  }

  /// Loads [indicator] for [countryId] across each period in [periods]
  /// (parallel requests). [periods] should be ordered oldest → newest for charts.
  Future<List<({String period, double? value})>> loadCountryIndicatorSeries({
    required FdrsIndicatorSelection indicator,
    required String locale,
    required int countryId,
    required List<String> periods,
  }) async {
    if (periods.isEmpty) return [];
    final futures = periods.map(
      (p) => loadOverview(
        indicator: indicator,
        locale: locale,
        periodName: p,
      ),
    );
    final datasets = await Future.wait(futures);
    return List.generate(periods.length, (i) {
      final v = datasets[i].byCountryId[countryId];
      return (period: periods[i], value: v);
    });
  }
}

/// Parses the `fdrs-reach-indicators` response body into sectors that have indicators.
List<ReachSector> parseReachSectors(Object? body) {
  if (body is! Map<String, dynamic>) return [];
  final data = body['data'];
  if (data is! Map<String, dynamic>) return [];
  final raw = data['sectors'];
  if (raw is! List<dynamic>) return [];
  final sectors = <ReachSector>[];
  for (final entry in raw) {
    if (entry is! Map<String, dynamic>) continue;
    final indicators = <ReachIndicator>[];
    final rawIndicators = entry['indicators'];
    if (rawIndicators is List<dynamic>) {
      for (final item in rawIndicators) {
        if (item is! Map<String, dynamic>) continue;
        final code = item['kpi_code']?.toString() ?? '';
        if (code.isEmpty) continue;
        indicators.add(
          ReachIndicator(kpiCode: code, name: item['name']?.toString() ?? code),
        );
      }
    }
    if (indicators.isEmpty) continue;
    final name = entry['name']?.toString();
    sectors.add(
      ReachSector(
        key: entry['id']?.toString() ?? 'other',
        name: name == null || name.isEmpty ? null : name,
        indicators: indicators,
      ),
    );
  }
  return sectors;
}

class OverviewLoadException implements Exception {
  OverviewLoadException(this.message);
  final String message;

  @override
  String toString() => message;
}
