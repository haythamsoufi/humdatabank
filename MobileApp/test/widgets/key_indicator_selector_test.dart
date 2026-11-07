import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/l10n/app_localizations.dart';
import 'package:hum_databank_app/widgets/public/indicator_trend.dart';

const _choices = [
  ReachChoice(key: 'KPI_ReachH', label: 'Health services', section: 'Health', order: 0),
  ReachChoice(key: 'KPI_ReachHI', label: 'Immunization', section: 'Health', order: 1),
  ReachChoice(key: 'KPI_ReachS', label: 'Shelter', section: 'Housing', order: 2),
];

Widget _host(String selectedKey, ValueChanged<String> onSelected) {
  return MaterialApp(
    locale: const Locale('en'),
    localizationsDelegates: const [
      AppLocalizations.delegate,
      GlobalMaterialLocalizations.delegate,
      GlobalWidgetsLocalizations.delegate,
    ],
    supportedLocales: const [Locale('en')],
    home: Scaffold(
      body: KeyIndicatorSelector(
        singleKeys: const {'volunteers'},
        reachChoices: _choices,
        selectedKey: selectedKey,
        onSelected: onSelected,
      ),
    ),
  );
}

void main() {
  testWidgets('headline selection shows only the first chip row', (tester) async {
    await tester.pumpWidget(_host('volunteers', (_) {}));
    await tester.pumpAndSettle();

    expect(find.text('Volunteers'), findsOneWidget);
    expect(find.text('Health'), findsNothing);
    expect(find.text('Immunization'), findsNothing);
  });

  testWidgets('people reached shows sector row then indicator row', (tester) async {
    String? picked;
    await tester.pumpWidget(_host('KPI_ReachH', (k) => picked = k));
    await tester.pumpAndSettle();

    expect(find.text('Health'), findsOneWidget);
    expect(find.text('Housing'), findsOneWidget);
    expect(find.text('Health services'), findsOneWidget);
    expect(find.text('Immunization'), findsOneWidget);
    expect(find.text('Shelter'), findsNothing);

    await tester.tap(find.text('Housing'));
    expect(picked, 'KPI_ReachS');
  });
}
