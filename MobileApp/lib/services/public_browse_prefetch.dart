import 'dart:convert';

import '../config/app_config.dart';
import '../config/fdrs_constants.dart';
import '../di/service_locator.dart';
import '../utils/debug_logger.dart';
import '../utils/network_availability.dart';
import 'api_service.dart';
import 'offline_cache_service.dart';
import 'storage_service.dart';

/// One cached API body, keyed the same way [ApiService.get] will look it up.
typedef BrowseCacheRow = ({String key, String data});

String browseEnvelope(Object? data) =>
    jsonEncode(<String, Object?>{'success': true, 'data': data});

BrowseCacheRow _row(
  String endpoint,
  Object? data, [
  Map<String, String>? query,
]) {
  return (
    key: OfflineCacheService.generateCacheKey(
      endpoint,
      query,
      scope: 'public',
    ),
    data: browseEnvelope(data),
  );
}

/// Cache rows for `/data/periods`, reach chips, and every indicator/period.
List<BrowseCacheRow> homeBrowseEntries({
  required Map<String, dynamic> pack,
  required String locale,
}) {
  final templateId = '${FdrsConstants.templateId}';
  final rows = <BrowseCacheRow>[
    _row(
      AppConfig.mobileFdrsPeriodsEndpoint,
      <String, Object?>{
        'periods': pack['periods'] is List ? pack['periods'] : const <Object>[],
      },
      <String, String>{'template_id': templateId},
    ),
    _row(
      AppConfig.mobileFdrsReachIndicatorsEndpoint,
      <String, Object?>{
        'sectors': pack['reach_sectors'] is List
            ? pack['reach_sectors']
            : const <Object>[],
      },
      <String, String>{'locale': locale, 'template_id': templateId},
    ),
  ];

  final overviews = pack['overviews'];
  if (overviews is! List) return rows;
  for (final raw in overviews) {
    if (raw is! Map) continue;
    final overview = Map<String, dynamic>.from(raw);
    final period = overview['period_name']?.toString() ?? '';
    final kpi = overview['kpi_code']?.toString();
    final bank = overview['indicator_bank_id'];
    final query = <String, String>{
      'locale': locale,
      'template_id': templateId,
    };
    if (period.isNotEmpty) query['period_name'] = period;
    if (kpi != null && kpi.isNotEmpty && kpi != 'null') {
      query['kpi_code'] = kpi;
    } else if (bank != null) {
      query['indicator_bank_id'] = '$bank';
    } else {
      continue;
    }
    overview.remove('indicator_bank_id');
    overview.remove('kpi_code');
    rows.add(_row(AppConfig.mobileFdrsOverviewEndpoint, overview, query));
  }
  return rows;
}

/// Cache rows for the country list, every profile, and every operations payload.
List<BrowseCacheRow> countryBrowseEntries({
  required Map<String, dynamic> pack,
  required String locale,
}) {
  final rows = <BrowseCacheRow>[
    _row(
      AppConfig.mobileCountryMapEndpoint,
      <String, Object?>{
        'countries':
            pack['countries'] is List ? pack['countries'] : const <Object>[],
      },
      <String, String>{'locale': locale},
    ),
  ];

  void addByIso(Object? source, String suffix, {bool withLocale = false}) {
    if (source is! Map) return;
    source.forEach((iso, payload) {
      final code = iso.toString().trim().toUpperCase();
      if (code.length != 3 || payload is! Map) return;
      final path = '${AppConfig.mobileCountryProfileEndpoint}/$code$suffix';
      rows.add(
        _row(
          path,
          payload,
          withLocale ? <String, String>{'locale': locale} : null,
        ),
      );
    });
  }

  addByIso(pack['profiles'], '', withLocale: true);
  addByIso(pack['operations'], '/operations');
  return rows;
}

List<String> iso3sFromCountryPack(Map<String, dynamic> pack) {
  final countries = pack['countries'];
  if (countries is! List) return const [];
  final codes = <String>[];
  for (final row in countries) {
    if (row is! Map) continue;
    final code = row['iso3']?.toString().trim().toUpperCase() ?? '';
    if (code.length == 3) codes.add(code);
  }
  return codes;
}

/// One country's rows from the single cached GO document list, or null.
Future<Map<String, dynamic>?> cachedGoDocumentsFor(String iso3) async {
  final code = iso3.trim().toUpperCase();
  if (code.length != 3) return null;
  final cached = await OfflineCacheService().getCachedResponse(
    OfflineCacheService.generateCacheKey(
      AppConfig.mobileGoDocumentsEndpoint,
      null,
      scope: 'public',
    ),
    allowExpired: true,
  );
  if (cached == null) return null;
  try {
    final decoded = jsonDecode(cached.data);
    final data = decoded is Map ? decoded['data'] : null;
    final byCountry = data is Map ? data['by_country'] : null;
    if (byCountry is! Map) return null;
    final payload = byCountry[code];
    if (payload is Map<String, dynamic>) return payload;
    if (payload is Map) return Map<String, dynamic>.from(payload);
  } catch (_) {}
  return null;
}

/// Downloads every home-map indicator and every country profile while online.
///
/// Screens keep loading the one figure the user is looking at. This fills the
/// rest of the cache so the other indicators and countries open offline.
class PublicBrowsePrefetch {
  PublicBrowsePrefetch({
    ApiService? api,
    OfflineCacheService? cache,
    StorageService? storage,
  })  : _api = api ?? sl<ApiService>(),
        _cache = cache ?? OfflineCacheService(),
        _storage = storage ?? sl<StorageService>();

  final ApiService _api;
  final OfflineCacheService _cache;
  final StorageService _storage;

  static const _freshFor = Duration(hours: 12);
  static const _packTimeout = Duration(seconds: 120);

  Future<void>? _packFlight;

  Future<void> warm({required String locale, bool force = false}) async {
    if (shouldDeferRemoteFetch) return;
    final language = locale.trim().isEmpty ? 'en' : locale.trim();
    if (!force && await _isFresh(language)) {
      await _cacheGoDocumentList(force: false);
      return;
    }
    final inFlight = _packFlight;
    if (inFlight != null) {
      await inFlight;
      return;
    }
    final flight = _download(language, force: force);
    _packFlight = flight;
    try {
      await flight;
    } finally {
      if (identical(_packFlight, flight)) _packFlight = null;
    }
  }

  Future<void> _download(String locale, {required bool force}) async {
    final packs = await Future.wait<Map<String, dynamic>?>([
      _getPack(
        AppConfig.mobileOfflineHomeEndpoint,
        <String, String>{
          'locale': locale,
          'template_id': '${FdrsConstants.templateId}',
          'indicator_bank_ids': FdrsConstants.homeMapBankIds.join(','),
        },
      ),
      _getPack(
        AppConfig.mobileOfflineCountriesEndpoint,
        <String, String>{
          'locale': locale,
          'template_id': '${FdrsConstants.templateId}',
        },
      ),
    ]);
    final home = packs[0];
    final countries = packs[1];
    if (home != null) {
      await _cache.cacheResponses(
        homeBrowseEntries(pack: home, locale: locale),
        ttl: OfflineCacheService.publicBrowseTtl,
      );
    }
    if (countries != null) {
      await _cache.cacheResponses(
        countryBrowseEntries(pack: countries, locale: locale),
        ttl: OfflineCacheService.publicBrowseTtl,
      );
    }
    if (home != null && countries != null) {
      await _storage.setString(
        _freshKey(locale),
        DateTime.now().toUtc().toIso8601String(),
      );
    }
    await _cacheGoDocumentList(force: force);
  }

  Future<Map<String, dynamic>?> _getPack(
    String endpoint,
    Map<String, String> query,
  ) async {
    try {
      final response = await _api.get(
        endpoint,
        queryParams: query,
        includeAuth: false,
        useCache: false,
        timeout: _packTimeout,
      );
      if (response.statusCode != 200) return null;
      final decoded = jsonDecode(response.body);
      final data = decoded is Map ? decoded['data'] : null;
      if (data is Map<String, dynamic>) return data;
      if (data is Map) return Map<String, dynamic>.from(data);
    } catch (e, stackTrace) {
      DebugLogger.logWarn(
        'PUBLIC_BROWSE',
        'Pack $endpoint failed: $e\n$stackTrace',
      );
    }
    return null;
  }

  Future<bool> _isFresh(String locale) async {
    final raw = await _storage.getString(_freshKey(locale));
    final saved = raw == null ? null : DateTime.tryParse(raw);
    if (saved == null) return false;
    return DateTime.now().difference(saved.toLocal()) < _freshFor;
  }

  String _freshKey(String locale) => 'public_browse_prefetch_$locale';

  /// One request, one cache row: every country's GO document list.
  Future<void> _cacheGoDocumentList({required bool force}) async {
    if (shouldDeferRemoteFetch) return;
    final key = OfflineCacheService.generateCacheKey(
      AppConfig.mobileGoDocumentsEndpoint,
      null,
      scope: 'public',
    );
    if (!force) {
      final existing = await _cache.getCachedResponse(key);
      if (existing != null) return;
    }
    try {
      await _api.get(
        AppConfig.mobileGoDocumentsEndpoint,
        includeAuth: false,
        useCache: true,
        cacheTtl: OfflineCacheService.publicBrowseTtl,
        timeout: const Duration(seconds: 180),
      );
    } catch (e, stackTrace) {
      DebugLogger.logWarn(
        'PUBLIC_BROWSE',
        'GO document list failed: $e\n$stackTrace',
      );
    }
  }
}
