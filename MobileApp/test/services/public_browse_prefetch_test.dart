import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/config/app_config.dart';
import 'package:hum_databank_app/config/fdrs_constants.dart';
import 'package:hum_databank_app/services/offline_cache_service.dart';
import 'package:hum_databank_app/services/public_browse_prefetch.dart';

void main() {
  test('home pack caches every indicator and period', () {
    final rows = homeBrowseEntries(
      locale: 'en',
      pack: {
        'periods': ['Annual 2024', 'Annual 2023'],
        'reach_sectors': [
          {
            'id': '1',
            'indicators': [
              {'kpi_code': 'KPI_ReachH'},
            ],
          },
        ],
        'overviews': [
          {
            'indicator_bank_id': FdrsConstants.indicatorVolunteers,
            'kpi_code': null,
            'period_name': 'Annual 2024',
            'by_country': {'1': 5},
            'country_names': {'1': 'A'},
            'country_iso2': {'1': 'AA'},
            'global_rolling_mean': null,
          },
          {
            'indicator_bank_id': null,
            'kpi_code': 'KPI_ReachH',
            'period_name': 'Annual 2023',
            'by_country': <String, Object>{},
            'country_names': <String, Object>{},
            'country_iso2': <String, Object>{},
            'global_rolling_mean': null,
          },
        ],
      },
    );

    String overviewKey(Map<String, String> query) {
      return OfflineCacheService.generateCacheKey(
        AppConfig.mobileFdrsOverviewEndpoint,
        query,
        scope: 'public',
      );
    }

    final volunteers = overviewKey({
      'indicator_bank_id': '${FdrsConstants.indicatorVolunteers}',
      'locale': 'en',
      'period_name': 'Annual 2024',
      'template_id': '${FdrsConstants.templateId}',
    });
    final reach = overviewKey({
      'kpi_code': 'KPI_ReachH',
      'locale': 'en',
      'period_name': 'Annual 2023',
      'template_id': '${FdrsConstants.templateId}',
    });
    final keys = rows.map((row) => row.key).toList();
    expect(keys, contains(volunteers));
    expect(keys, contains(reach));
    expect(
      keys,
      contains(
        OfflineCacheService.generateCacheKey(
          AppConfig.mobileFdrsPeriodsEndpoint,
          {'template_id': '${FdrsConstants.templateId}'},
          scope: 'public',
        ),
      ),
    );

    final body = jsonDecode(
      rows.firstWhere((row) => row.key == volunteers).data,
    ) as Map<String, dynamic>;
    final data = body['data'] as Map<String, dynamic>;
    expect(data.containsKey('indicator_bank_id'), isFalse);
    expect(data['by_country'], {'1': 5});
  });

  test('country pack caches the list and every profile', () {
    final rows = countryBrowseEntries(
      locale: 'fr',
      pack: {
        'countries': [
          {'iso3': 'bgd', 'name': 'Bangladesh'},
        ],
        'profiles': {
          'bgd': {
            'country': {'iso3': 'BGD'},
          },
        },
        'operations': {
          'BGD': {'operations': <Object>[]},
        },
      },
    );
    final keys = rows.map((row) => row.key).toSet();
    expect(
      keys,
      contains(
        OfflineCacheService.generateCacheKey(
          AppConfig.mobileCountryMapEndpoint,
          {'locale': 'fr'},
          scope: 'public',
        ),
      ),
    );
    expect(
      keys,
      contains(
        OfflineCacheService.generateCacheKey(
          '${AppConfig.mobileCountryProfileEndpoint}/BGD',
          {'locale': 'fr'},
          scope: 'public',
        ),
      ),
    );
    expect(
      keys,
      contains(
        OfflineCacheService.generateCacheKey(
          '${AppConfig.mobileCountryProfileEndpoint}/BGD/operations',
          null,
          scope: 'public',
        ),
      ),
    );
    expect(iso3sFromCountryPack({
      'countries': [
        {'iso3': 'bgd'},
        {'iso3': 'AF'},
      ],
    }), ['BGD']);
  });
}
