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
  test('iPhone home-indicator inset leaves the indicator under the pill', () {
    // 34pt inset → 21pt under the capsule (indicator graphic is ~13pt).
    expect(AppBottomNavigationBar.iosBottomPaddingForInset(34), 21);
    expect(AppBottomNavigationBar.iosBottomPaddingForInset(0), 12);
    expect(AppBottomNavigationBar.iosBottomPaddingForInset(21), 21);
    expect(AppBottomNavigationBar.iosBottomPaddingForInset(48), 48);
  });

  testWidgets('iPhone bar floats a capsule above the home indicator', (
    tester,
  ) async {
    await _pumpBar(tester, platform: TargetPlatform.iOS, bottomInset: 34);

    final barRect = tester.getRect(find.byType(AppBottomNavigationBar));
    final pillRect = tester.getRect(
      find.byKey(AppBottomNavigationBar.floatingPillKey),
    );
    final icon = tester.renderObject<RenderBox>(find.byIcon(Icons.grid_view));
    final gap =
        barRect.bottom - icon.localToGlobal(Offset(0, icon.size.height)).dy;

    expect(
      barRect.height,
      closeTo(
        AppBottomNavigationBar.floatingTopGap +
            AppBottomNavigationBar.floatingPillHeight +
            21,
        0.5,
      ),
    );
    expect(pillRect.height, AppBottomNavigationBar.floatingPillHeight);
    expect(pillRect.left - barRect.left, greaterThan(10));
    expect(barRect.right - pillRect.right, greaterThan(10));
    expect(barRect.bottom - pillRect.bottom, closeTo(21, 0.5));
    // Glyph stays clear of the ~13pt home-indicator graphic.
    expect(gap, greaterThan(13));
  });

  testWidgets('iPhone without a home indicator still floats off the edge', (
    tester,
  ) async {
    await _pumpBar(tester, platform: TargetPlatform.iOS, bottomInset: 0);

    final barRect = tester.getRect(find.byType(AppBottomNavigationBar));
    final pillRect = tester.getRect(
      find.byKey(AppBottomNavigationBar.floatingPillKey),
    );
    expect(
      barRect.height,
      closeTo(
        AppBottomNavigationBar.floatingTopGap +
            AppBottomNavigationBar.floatingPillHeight +
            12,
        0.5,
      ),
    );
    expect(barRect.bottom - pillRect.bottom, closeTo(12, 0.5));
  });

  testWidgets('Android floats the capsule above the system inset', (
    tester,
  ) async {
    await _pumpBar(tester, platform: TargetPlatform.android, bottomInset: 48);

    final barRect = tester.getRect(find.byType(AppBottomNavigationBar));
    final pillRect = tester.getRect(
      find.byKey(AppBottomNavigationBar.floatingPillKey),
    );
    expect(
      barRect.height,
      closeTo(
        AppBottomNavigationBar.floatingTopGap +
            AppBottomNavigationBar.floatingPillHeight +
            48,
        0.5,
      ),
    );
    expect(barRect.bottom - pillRect.bottom, closeTo(48, 0.5));
    expect(pillRect.left, greaterThan(10));
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
    final pillRect = tester.getRect(
      find.byKey(AppBottomNavigationBar.floatingPillKey),
    );
    expect(icon.localToGlobal(Offset.zero).dx, greaterThan(47));
    expect(pillRect.left, greaterThan(47));
  });
}
