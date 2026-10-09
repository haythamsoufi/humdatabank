import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/l10n/app_localizations.dart';
import 'package:hum_databank_app/providers/shared/tab_customization_provider.dart';
import 'package:hum_databank_app/utils/theme.dart';
import 'package:hum_databank_app/widgets/bottom_navigation_bar.dart';

const _tabs = <TabDefinition>[
  TabDefinition(
    id: TabIds.home,
    icon: Icons.home_outlined,
    activeIcon: Icons.home_rounded,
    getLabel: _homeLabel,
    isRequired: true,
  ),
  TabDefinition(
    id: TabIds.dashboard,
    icon: Icons.grid_view_outlined,
    activeIcon: Icons.grid_view,
    getLabel: _dashboardLabel,
  ),
];

String _homeLabel(AppLocalizations l) => l.home;
String _dashboardLabel(AppLocalizations l) => l.dashboard;

/// Pumps a page under the floating bar the way the tab shell and the pushed
/// chat route do: [Scaffold.extendBody] with no body resize for the keyboard.
Future<MediaQueryData> _pumpExtendedBody(
  WidgetTester tester, {
  double keyboard = 0,
}) async {
  tester.view.physicalSize = const Size(390, 844);
  tester.view.devicePixelRatio = 1;
  tester.view.padding = const FakeViewPadding(bottom: 34);
  tester.view.viewPadding = const FakeViewPadding(bottom: 34);
  tester.view.viewInsets = FakeViewPadding(bottom: keyboard);
  addTearDown(tester.view.reset);

  late MediaQueryData bodyMedia;
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.lightTheme(),
      localizationsDelegates: const [AppLocalizations.delegate],
      supportedLocales: const [Locale('en')],
      home: Scaffold(
        primary: false,
        resizeToAvoidBottomInset: false,
        extendBody: true,
        body: Builder(
          builder: (context) {
            bodyMedia = MediaQuery.of(context);
            return const SizedBox.expand();
          },
        ),
        bottomNavigationBar: const AppBottomNavigationBar(
          currentIndex: 0,
          visibleTabs: _tabs,
        ),
      ),
    ),
  );
  await tester.pump();
  return bodyMedia;
}

void main() {
  // The chat composer and every tab page size their trailing space from this
  // value, so it has to equal the capsule's real height.
  testWidgets('page padding.bottom equals the floating bar height', (
    tester,
  ) async {
    final media = await _pumpExtendedBody(tester);
    final barHeight = tester.getSize(find.byType(AppBottomNavigationBar)).height;

    expect(media.padding.bottom, closeTo(barHeight, 0.5));
    expect(barHeight, greaterThan(AppBottomNavigationBar.floatingPillHeight));
  });

  testWidgets('page padding.bottom stays the bar height under the keyboard', (
    tester,
  ) async {
    final media = await _pumpExtendedBody(tester, keyboard: 300);
    final barHeight = tester.getSize(find.byType(AppBottomNavigationBar)).height;

    expect(media.viewInsets.bottom, 300);
    expect(media.padding.bottom, closeTo(barHeight, 0.5));
  });
}
