import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/config/fdrs_constants.dart';
import 'package:hum_databank_app/l10n/app_localizations.dart';
import 'package:hum_databank_app/services/global_overview_data_service.dart';
import 'package:hum_databank_app/widgets/home_landing/fdrs_world_map.dart';

const _sectors = [
  ReachSector(
    key: '1',
    name: 'Health',
    indicators: [
      ReachIndicator(kpiCode: 'KPI_ReachH', name: 'People reached with health'),
      ReachIndicator(kpiCode: 'KPI_ReachM', name: 'People reached with MHPSS'),
    ],
  ),
  ReachSector(
    key: '2',
    name: 'Housing',
    indicators: [
      ReachIndicator(kpiCode: 'KPI_ReachS', name: 'People reached with shelter'),
    ],
  ),
];

Widget _host({
  required FdrsIndicatorSelection selection,
  required List<ReachSector> sectors,
  required ValueChanged<FdrsIndicatorSelection> onSelect,
}) {
  final l10n = AppLocalizations(const Locale('en'));
  return MaterialApp(
    home: Scaffold(
      body: FdrsIndicatorPicker(
        l10n: l10n,
        selection: selection,
        reachSectors: sectors,
        onSelect: onSelect,
      ),
    ),
  );
}

void main() {
  const volunteers = FdrsIndicatorSelection.bank(
    FdrsConstants.indicatorVolunteers,
  );

  testWidgets('people reached selects the first sector indicator', (
    tester,
  ) async {
    FdrsIndicatorSelection? picked;
    await tester.pumpWidget(
      _host(
        selection: volunteers,
        sectors: _sectors,
        onSelect: (s) => picked = s,
      ),
    );

    expect(find.text('Health'), findsNothing);
    await tester.ensureVisible(find.text('People reached'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('People reached'));

    expect(picked?.isReach, isTrue);
    expect(picked?.kpiCode, 'KPI_ReachH');
    expect(picked?.sectorKey, '1');
  });

  testWidgets('reach selection shows sector chips then sector indicators', (
    tester,
  ) async {
    FdrsIndicatorSelection? picked;
    await tester.pumpWidget(
      _host(
        selection: const FdrsIndicatorSelection.reach(
          kpiCode: 'KPI_ReachH',
          sectorKey: '1',
          label: 'Health services',
        ),
        sectors: _sectors,
        onSelect: (s) => picked = s,
      ),
    );

    expect(find.text('Health'), findsOneWidget);
    expect(find.text('Housing'), findsOneWidget);
    expect(find.text('Health services'), findsOneWidget);
    expect(find.text('Migrants & displaced people'), findsOneWidget);
    expect(find.text('Shelter'), findsNothing);

    await tester.tap(find.text('Housing'));
    expect(picked?.sectorKey, '2');
    expect(picked?.kpiCode, 'KPI_ReachS');
  });

  testWidgets('people reached chip is hidden without sectors', (tester) async {
    await tester.pumpWidget(
      _host(selection: volunteers, sectors: const [], onSelect: (_) {}),
    );

    expect(find.text('Volunteers'), findsOneWidget);
    expect(find.text('People reached'), findsNothing);
  });

  testWidgets('global total card shows the summed value', (tester) async {
    final l10n = AppLocalizations(const Locale('en'));
    final data = GlobalOverviewDataset(
      periodName: '2024',
      byCountryId: {1: 1200000, 2: 300000},
      countryNames: {1: 'A', 2: 'B'},
      countryIso2: {1: 'AA', 2: 'BB'},
    );
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: FdrsGlobalTotalCard(
            l10n: l10n,
            locale: 'en',
            indicatorLabel: 'Volunteers',
            data: data,
          ),
        ),
      ),
    );

    expect(find.text('Global total'), findsOneWidget);
    expect(find.text('1.5M'), findsOneWidget);
    expect(find.text('1,500,000'), findsOneWidget);
    expect(find.text('2 countries reporting · 2024'), findsOneWidget);
  });
}
