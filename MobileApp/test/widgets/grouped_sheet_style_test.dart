import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/theme/grouped_dashboard_palette.dart';
import 'package:hum_databank_app/theme/grouped_sheet_style.dart';
import 'package:hum_databank_app/utils/ios_constants.dart';
import 'package:hum_databank_app/utils/theme.dart';

Future<void> _pump(WidgetTester tester, ThemeData theme, Widget child) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: theme,
      home: Scaffold(body: child),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  test('light and dark canvases match the grouped dashboard', () {
    expect(
      GroupedSheetStyle.canvasFor(isDark: false),
      IOSColors.groupedTableViewBackground,
    );
    expect(
      GroupedSheetStyle.canvasFor(isDark: true),
      IOSColors.groupedTableViewBackgroundDark,
    );
    expect(
      GroupedSheetStyle.cardFor(
        isDark: false,
        scheme: AppTheme.lightTheme().colorScheme,
      ),
      GroupedDashboardPalette.card,
    );
    expect(
      GroupedSheetStyle.hairlineFor(
        isDark: false,
        scheme: AppTheme.lightTheme().colorScheme,
      ),
      GroupedDashboardPalette.hairline,
    );
  });

  testWidgets('light filter chip uses the dashboard card and hairline', (
    tester,
  ) async {
    await _pump(
      tester,
      AppTheme.lightTheme(),
      GroupedFilterChip(label: 'Period', onTap: () {}),
    );

    final material = tester.widget<Material>(find.byType(Material).last);
    expect(material.color, GroupedDashboardPalette.card);
    final shape = material.shape! as RoundedRectangleBorder;
    expect(shape.side.color, GroupedDashboardPalette.hairline);
  });

  testWidgets('dark selected option uses the info wash', (tester) async {
    await _pump(
      tester,
      AppTheme.darkTheme(),
      GroupedSheetOption(label: 'Approved', selected: true, onTap: () {}),
    );

    final material = tester.widget<Material>(find.byType(Material).last);
    expect(
      material.color,
      GroupedDashboardPalette.info.accent.withValues(alpha: 0.22),
    );
    final shape = material.shape! as RoundedRectangleBorder;
    expect(
      shape.side.color,
      GroupedDashboardPalette.info.accent.withValues(alpha: 0.55),
    );
    expect(find.byIcon(Icons.check_rounded), findsOneWidget);
  });

  testWidgets('light selected option uses the info background', (tester) async {
    await _pump(
      tester,
      AppTheme.lightTheme(),
      GroupedSheetOption(label: 'Submitted', selected: true, onTap: () {}),
    );

    final material = tester.widget<Material>(find.byType(Material).last);
    expect(material.color, GroupedDashboardPalette.info.background);
    expect(find.text('Submitted'), findsOneWidget);
  });
}
