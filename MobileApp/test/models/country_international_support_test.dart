import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/models/public/country_international_support.dart';
import 'package:hum_databank_app/models/public/country_profile.dart';

void main() {
  group('CountryInfo.isPns', () {
    test('defaults to false and reads is_pns', () {
      final plain = CountryInfo.fromJson({
        'id': 1,
        'name': 'Syria',
        'iso3': 'SYR',
      });
      expect(plain.isPns, isFalse);

      final pns = CountryInfo.fromJson({
        'id': 2,
        'name': 'Norway',
        'iso3': 'NOR',
        'is_pns': true,
      });
      expect(pns.isPns, isTrue);
    });
  });

  group('CountryInternationalSupport', () {
    test('parses host payload', () {
      final support = CountryInternationalSupport.fromJson({
        'iso3': 'SYR',
        'is_pns': false,
        'role': 'host',
        'has_support': true,
        'years': [2026, 2025],
        'summary': {
          'year': 2026,
          'supporting_partners': 2,
          'funding': 1500000,
          'requirement': 2000000,
          'expenditure': 900000,
        },
        'partners': [
          {'iso3': 'NOR', 'name': 'Norwegian Red Cross', 'funding': 1000000},
          {'iso3': 'DNK', 'name': 'Danish Red Cross', 'funding': 500000},
        ],
        'embeds': {
          'primary': '/upr/support-flow?recipient=SYR',
          'flow': '/upr/support-flow?recipient=SYR',
        },
      });

      expect(support.isPns, isFalse);
      expect(support.summary.supportingPartners, 2);
      expect(support.partners, hasLength(2));
      expect(support.primaryEmbedPath, '/upr/support-flow?recipient=SYR');
    });

    test('parses pns payload and prefers primary embed', () {
      final support = CountryInternationalSupport.fromJson({
        'iso3': 'NOR',
        'is_pns': true,
        'role': 'pns',
        'has_support': true,
        'years': [2026],
        'summary': {
          'year': 2026,
          'countries_supported': 3,
          'funding': 4000000,
        },
        'partners': [
          {'iso3': 'SYR', 'name': 'Syria', 'funding': 1500000},
        ],
        'embeds': {
          'primary': '/upr/support-overview?pns=NOR',
          'flow': '/upr/support-flow?pns=NOR',
          'funding': '/upr/support-funding',
          'coverage': '/upr/support-coverage',
        },
      });

      expect(support.isPns, isTrue);
      expect(support.summary.countriesSupported, 3);
      expect(support.primaryEmbedPath, '/upr/support-overview?pns=NOR');
    });
  });
}
