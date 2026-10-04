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
  TabDefinition(
    id: TabIds.admin,
    icon: Icons.shield_outlined,
    activeIcon: Icons.shield,
    getLabel: _adminLabel,
  ),
];

String _homeLabel(AppLocalizations l) => l.home;
String _dashboardLabel(AppLocalizations l) => l.dashboard;
String _adminLabel(AppLocalizations l) => l.admin;

Future<void> _pumpBar(
  WidgetTester tester, {
  required TargetPlatform platform,
  required double bottomInset,
  double leftInset = 0,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: AppTheme.lightTheme().copyWith(platform: platform),
      localizationsDelegates: const [AppLocalizations.delegate],
      supportedLocales: const [Locale('en')],
      builder: (context, child) {
        final mq = MediaQuery.of(context);
        return MediaQuery(
          data: mq.copyWith(
            padding: EdgeInsets.only(left: leftInset, bottom: bottomInset),
            viewPadding: EdgeInsets.only(left: leftInset, bottom: bottomInset),
          ),
          child: child!,
        );
      },
      home: const Scaffold(
        body: ColoredBox(color: Color(0xFFF2F2F7)),
        bottomNavigationBar: AppBottomNavigationBar(
          currentIndex: 1,
          visibleTabs: _tabs,
        ),
      ),
    ),
  );
  await tester.pump();
}

void main() {
  test('iPhone home-indicator inset keeps a short clearance', () {
    // 34pt inset → 18pt under the glyphs (indicator graphic is ~13pt).
    expect(AppBottomNavigationBar.iosBottomPaddingForInset(34), 18);
    expect(AppBottomNavigationBar.iosBottomPaddingForInset(0), 8);
    expect(AppBottomNavigationBar.iosBottomPaddingForInset(21), 16);
    expect(AppBottomNavigationBar.iosBottomPaddingForInset(48), 48);
  });

  testWidgets('iPhone bar does not stack the full safe inset under the icons', (
    tester,
  ) async {
    await _pumpBar(tester, platform: TargetPlatform.iOS, bottomInset: 34);

    final bar = tester.renderObject<RenderBox>(
      find.byType(AppBottomNavigationBar),
    );
    final icon = tester.renderObject<RenderBox>(find.byIcon(Icons.grid_view));
    final gap =
        bar.localToGlobal(Offset(0, bar.size.height)).dy -
        icon.localToGlobal(Offset(0, icon.size.height)).dy;

    expect(bar.size.height, closeTo(35 + 18, 0.5));
    // Old shell was 52 + 34, with the glyph centered, ~48pt under the icon.
    expect(gap, closeTo(18, 0.5));
    expect(gap, greaterThan(13));
  });

  testWidgets('iPhone without a home indicator uses a short bottom pad', (
    tester,
  ) async {
    await _pumpBar(tester, platform: TargetPlatform.iOS, bottomInset: 0);

    final bar = tester.renderObject<RenderBox>(
      find.byType(AppBottomNavigationBar),
    );
    expect(bar.size.height, closeTo(35 + 8, 0.5));
  });

  testWidgets('Android keeps the full system inset under the icon slot', (
    tester,
  ) async {
    await _pumpBar(tester, platform: TargetPlatform.android, bottomInset: 48);

    final bar = tester.renderObject<RenderBox>(
      find.byType(AppBottomNavigationBar),
    );
    expect(bar.size.height, closeTo(52 + 48, 0.5));
  });

  testWidgets('iPhone landscape keeps the side safe inset', (tester) async {
    await _pumpBar(
      tester,
      platform: TargetPlatform.iOS,
      bottomInset: 21,
      leftInset: 47,
    );

    final icon = tester.renderObject<RenderBox>(
      find.byIcon(Icons.home_outlined),
    );
    expect(icon.localToGlobal(Offset.zero).dx, greaterThan(47));
  });
}
