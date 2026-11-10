import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/models/public/country_international_support.dart';
import 'package:hum_databank_app/models/public/country_profile.dart';
import 'package:hum_databank_app/models/public/support_flow.dart';
import 'package:hum_databank_app/widgets/public/support_flow_geometry.dart';

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
        'staff_presence': {
          'year': 2026,
          'count': 1,
          'entries': [
            {'iso3': 'NOR', 'name': 'Norwegian Red Cross', 'staff': 4},
          ],
        },
        'embeds': {
          'primary': '/upr/support-flow?recipient=SYR',
          'flow': '/upr/support-flow?recipient=SYR',
        },
      });

      expect(support.isPns, isFalse);
      expect(support.summary.supportingPartners, 2);
      expect(support.partners, hasLength(2));
      expect(support.staffPresence.count, 1);
      expect(support.staffPresence.staffTotal, 4);
      expect(support.staffPresence.entries.first.iso3, 'NOR');
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
          'staff_presence': 2,
        },
        'partners': [
          {'iso3': 'SYR', 'name': 'Syria', 'funding': 1500000},
        ],
        'staff_presence': {
          'year': 2026,
          'count': 2,
          'entries': [
            {'iso3': 'SYR', 'name': 'Syria', 'staff': 4},
            {'iso3': 'UKR', 'name': 'Ukraine', 'staff': 2},
          ],
        },
        'embeds': {
          'primary': '/upr/support-overview?pns=NOR',
          'flow': '/upr/support-flow?pns=NOR',
          'funding': '/upr/support-funding',
          'coverage': '/upr/support-coverage',
        },
      });

      expect(support.isPns, isTrue);
      expect(support.summary.countriesSupported, 3);
      expect(support.summary.staffPresence, 2);
      expect(support.staffPresence.staffTotal, 6);
      expect(support.staffPresence.entries, hasLength(2));
      expect(support.primaryEmbedPath, '/upr/support-overview?pns=NOR');
    });

    test('sums staff when staff_total is omitted and prefers an explicit total', () {
      final summed = CountryInternationalStaffPresence.fromJson({
        'entries': [
          {'name': 'Syria', 'staff': 4},
          {'name': 'Ukraine', 'staff': 1.5},
        ],
      });
      expect(summed.staffTotal, 5.5);

      final explicit = CountryInternationalStaffPresence.fromJson({
        'staff_total': 11,
        'entries': [
          {'name': 'Syria', 'staff': 4},
        ],
      });
      expect(explicit.staffTotal, 11);
    });
  });

  group('mergeInternationalFundingBars', () {
    test('joins funding and staff on one row and keeps staff-only partners', () {
      final rows = mergeInternationalFundingBars(
        partners: const [
          CountryInternationalPartner(
            iso3: 'NOR',
            name: 'Norwegian Red Cross',
            funding: 1000000,
          ),
          CountryInternationalPartner(iso3: 'DNK', name: 'Danish Red Cross', funding: 200000),
        ],
        staff: const [
          CountryInternationalStaffEntry(iso3: 'NOR', name: 'Norwegian Red Cross', staff: 4),
          CountryInternationalStaffEntry(iso3: 'SWE', name: 'Swedish Red Cross', staff: 2),
        ],
      );

      expect(rows.map((row) => row.iso3).toList(), ['NOR', 'DNK', 'SWE']);
      expect(rows.first.funding, 1000000);
      expect(rows.first.staff, 4);
      expect(rows[1].staff, 0);
      expect(rows.last.funding, 0);
      expect(rows.last.staff, 2);
    });
  });

  group('support flow geometry', () {
    const nodes = [
      SupportFlowNode(iso3: 'NOR', name: 'Norway', lat: 60, lng: 10, role: 'donor'),
      SupportFlowNode(iso3: 'SYR', name: 'Syria', lat: 35, lng: 38, role: 'host'),
      SupportFlowNode(iso3: 'LBN', name: 'Lebanon', lat: 34, lng: 36, role: 'host'),
    ];
    const edges = [
      SupportFlowEdge(from: 'NOR', to: 'SYR', years: [2026]),
      SupportFlowEdge(from: 'NOR', to: 'LBN', years: [2026]),
      SupportFlowEdge(from: 'NOR', to: 'SYR', years: [2025]),
    ];

    test('keeps one line per pair for the selected year and bundles it', () {
      final yearEdges = supportEdgesForYear(edges, 2026);
      expect(yearEdges, hasLength(2));
      final visible = supportNodesForEdges(nodes, yearEdges);
      expect(visible, hasLength(3));
      final donor = visible.firstWhere((node) => node.iso3 == 'NOR');
      expect(donor.outWeight, 2);
      expect(donor.role, 'donor');

      final segments = buildSupportFlowSegments(nodes: visible, edges: yearEdges);
      expect(segments.where((segment) => segment.leaf), hasLength(2));
      expect(segments.where((segment) => !segment.leaf), isNotEmpty);
      expect(
        segments.every((segment) => segment.parts.every((part) => part.length > 1)),
        isTrue,
      );
    });

    test('narrows each party list by the other filter', () {
      const data = SupportFlowData(
        nodes: nodes,
        edges: edges,
        funding: const [],
        figures: const [],
        coverage: const [],
        areas: const [],
        years: const [2026, 2025],
        hasData: true,
      );
      final resolved = resolveSupportFlowFilter(
        data: data,
        year: 2026,
        pns: 'NOR',
        recipient: null,
      );
      expect(resolved.pns, 'NOR');
      expect(resolved.recipientOptions.map((option) => option.iso3), ['LBN', 'SYR']);
      expect(resolved.edges, hasLength(2));
    });

    test('splits a path that crosses the date line', () {
      final parts = splitFlowAtAntimeridian(const [
        FlowPoint(0, 170),
        FlowPoint(0, 190),
      ]);
      expect(parts, hasLength(2));
      expect(parts.first.last.lng, 180);
      expect(parts.last.first.lng, -180);
    });
  });
}
