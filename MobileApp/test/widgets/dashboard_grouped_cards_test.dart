import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:hum_databank_app/l10n/app_localizations.dart';
import 'package:hum_databank_app/models/shared/assignment.dart';
import 'package:hum_databank_app/models/shared/focal_point_contact.dart';
import 'package:hum_databank_app/theme/grouped_dashboard_palette.dart';
import 'package:hum_databank_app/widgets/dashboard_focal_points_section.dart';
import 'package:hum_databank_app/widgets/dashboard_grouped_assignment_card.dart';

Assignment _assignment(String status) {
  return Assignment(
    id: 1,
    name: 'Unified Country Plan',
    status: status,
    completionRate: 73,
    templateName: 'Unified Country Plan',
    periodName: '2027',
  );
}

Future<void> _pump(WidgetTester tester, Widget child) async {
  await tester.pumpWidget(
    MaterialApp(
      localizationsDelegates: const [AppLocalizations.delegate],
      supportedLocales: const [Locale('en')],
      home: Scaffold(body: SingleChildScrollView(child: child)),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('approved assignment card uses a blue wash, not grey', (
    tester,
  ) async {
    await _pump(
      tester,
      DashboardGroupedAssignmentCard(assignment: _assignment('approved')),
    );

    final colors = tester
        .widgetList<Material>(find.byType(Material))
        .map((material) => material.color);
    expect(colors, contains(GroupedDashboardPalette.approvedCard));
    expect(colors, isNot(contains(GroupedDashboardPalette.mutedWash)));
    expect(find.text('Approved'), findsOneWidget);
  });

  testWidgets('submitted assignment card uses a green wash', (tester) async {
    await _pump(
      tester,
      DashboardGroupedAssignmentCard(assignment: _assignment('submitted')),
    );

    final colors = tester
        .widgetList<Material>(find.byType(Material))
        .map((material) => material.color);
    expect(colors, contains(GroupedDashboardPalette.submittedCard));
  });

  testWidgets('focal points use envelope and Teams action marks', (
    tester,
  ) async {
    await _pump(
      tester,
      const DashboardFocalPointsSection(
        entityLabel: 'Bangladesh',
        nsFocalPoints: [
          FocalPointContact(
            id: 1,
            name: 'Ada Lovelace',
            title: 'Reporting lead',
            email: 'ada@example.org',
          ),
        ],
        orgFocalPoints: [],
      ),
    );

    expect(find.byIcon(FontAwesomeIcons.solidEnvelope), findsOneWidget);
    expect(find.byType(CustomPaint), findsWidgets);
    final paints = tester.widgetList<CustomPaint>(find.byType(CustomPaint));
    expect(
      paints.where((paint) => paint.painter != null).length,
      greaterThan(0),
    );
  });
}
