import 'dart:convert';

import '../config/app_config.dart';
import '../config/fdrs_constants.dart';
import '../di/service_locator.dart';
import '../models/disaggregation/disaggregation_overview.dart';
import 'api_service.dart';
import 'jwt_token_service.dart';
import 'session_service.dart';

class DisaggregationLoadException implements Exception {
  DisaggregationLoadException(this.message);
  final String message;

  @override
  String toString() => message;
}

class DisaggregationDataService {
  DisaggregationDataService({ApiService? api}) : _api = api ?? sl<ApiService>();

  final ApiService _api;

  /// Public endpoint that returns richer country data when auth is present.
  /// Do not set [includeAuth] when tokens are expired — that triggers the global
  /// session guard and blocks anonymous regional/global loads.
  Future<bool> _includeAuthIfAvailable() async {
    final jwt = sl<JwtTokenService>();
    final accessToken = await jwt.getAccessToken();
    if (accessToken != null && accessToken.isNotEmpty) {
      if (!await jwt.isAccessTokenExpired()) return true;
      if (await jwt.hasRefreshToken()) return true;
    }
    return sl<SessionService>().isSessionValid();
  }

  Future<List<String>> listPeriods() async {
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

  Future<List<DisaggregationCountryOption>> listCountries({
    required String locale,
  }) async {
    final resp = await _api.get(
      AppConfig.mobileCountryMapEndpoint,
      queryParams: {'locale': locale},
      includeAuth: false,
      useCache: true,
    );
    if (resp.statusCode != 200) return [];
    final body = jsonDecode(resp.body);
    if (body is! Map<String, dynamic>) return [];
    final data = body['data'];
    if (data is! Map<String, dynamic>) return [];
    final countries = data['countries'];
    if (countries is! List<dynamic>) return [];
    return countries
        .whereType<Map<String, dynamic>>()
        .map(DisaggregationCountryOption.fromJson)
        .where((c) => c.id > 0 && c.name.isNotEmpty)
        .toList()
      ..sort((a, b) => a.name.compareTo(b.name));
  }

  Future<DisaggregationOverview> loadOverview({
    required String locale,
    required DisaggregationFilters filters,
  }) async {
    final qp = <String, String>{
      'indicator_bank_id': '${filters.indicatorBankId}',
      'template_id': '${FdrsConstants.templateId}',
      'locale': locale,
    };
    if (filters.periodName != null && filters.periodName!.isNotEmpty) {
      qp['period_name'] = filters.periodName!;
    }
    if (filters.countryId != null) {
      qp['country_id'] = '${filters.countryId}';
    }

    final resp = await _api.get(
      AppConfig.mobileDisaggregationOverviewEndpoint,
      queryParams: qp,
      includeAuth: await _includeAuthIfAvailable(),
      timeout: const Duration(seconds: 45),
      useCache: false,
    );

    if (resp.statusCode != 200) {
      throw DisaggregationLoadException(
        'HTTP ${resp.statusCode} loading disaggregation overview',
      );
    }

    final body = jsonDecode(resp.body);
    if (body is! Map<String, dynamic>) {
      throw DisaggregationLoadException('Unexpected response shape');
    }
    final data = body['data'];
    if (data is! Map<String, dynamic>) {
      throw DisaggregationLoadException('Missing data envelope');
    }
    return DisaggregationOverview.fromJson(data);
  }
}
