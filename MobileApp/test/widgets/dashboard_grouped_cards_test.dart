import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/l10n/app_localizations.dart';
import 'package:hum_databank_app/models/shared/assignment.dart';
import 'package:hum_databank_app/models/shared/project_dashboard_group.dart';
import 'package:hum_databank_app/models/shared/focal_point_contact.dart';
import 'package:hum_databank_app/theme/grouped_dashboard_palette.dart';
import 'package:hum_databank_app/widgets/dashboard_focal_points_section.dart';
import 'package:hum_databank_app/widgets/dashboard_grouped_assignment_card.dart';
import 'package:intl/date_symbol_data_local.dart';

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
  setUpAll(() => initializeDateFormatting('en'));

  testWidgets('approved assignment card uses the Backoffice green wash', (
    tester,
  ) async {
    await _pump(
      tester,
      DashboardGroupedAssignmentCard(assignment: _assignment('approved')),
    );

    final colors = tester
        .widgetList<Material>(find.byType(Material))
        .map((material) => material.color);
    expect(colors, contains(GroupedDashboardPalette.success.background));
    expect(colors, isNot(contains(GroupedDashboardPalette.neutral.background)));
    expect(find.text('Approved'), findsOneWidget);
  });

  testWidgets('submitted assignment card uses the Backoffice blue wash', (
    tester,
  ) async {
    await _pump(
      tester,
      DashboardGroupedAssignmentCard(assignment: _assignment('submitted')),
    );

    final colors = tester
        .widgetList<Material>(find.byType(Material))
        .map((material) => material.color);
    expect(colors, contains(GroupedDashboardPalette.info.background));
  });

  testWidgets('sent for review and requires revision use Backoffice tones', (
    tester,
  ) async {
    await _pump(
      tester,
      Column(
        children: [
          DashboardGroupedAssignmentCard(
            assignment: _assignment('sent_for_review'),
          ),
          DashboardGroupedAssignmentCard(
            assignment: _assignment('requires_revision'),
          ),
        ],
      ),
    );

    final colors = tester
        .widgetList<Material>(find.byType(Material))
        .map((material) => material.color);
    expect(colors, contains(GroupedDashboardPalette.review.background));
    expect(colors, contains(GroupedDashboardPalette.warning.background));
    expect(find.text('Sent For Review'), findsOneWidget);
  });

  testWidgets('overdue assignment card uses the danger wash', (tester) async {
    final overdue = Assignment(
      id: 2,
      name: 'Late form',
      status: 'in_progress',
      completionRate: 10,
      dueDate: DateTime(2020, 1, 1),
    );
    await _pump(tester, DashboardGroupedAssignmentCard(assignment: overdue));

    final colors = tester
        .widgetList<Material>(find.byType(Material))
        .map((material) => material.color);
    expect(colors, contains(GroupedDashboardPalette.danger.background));
    expect(find.text('Overdue'), findsOneWidget);
    expect(find.text('In Progress'), findsOneWidget);

    final dueDate = tester.getRect(find.textContaining('Due Date'));
    final overdueBadge = tester.getRect(find.text('Overdue'));
    final statusBadge = tester.getRect(find.text('In Progress'));
    // Overdue sits on the due-date line, not stacked under the status chip.
    expect((dueDate.center.dy - overdueBadge.center.dy).abs(), lessThan(8));
    expect(overdueBadge.left, greaterThan(dueDate.right));
    expect(statusBadge.bottom, lessThan(overdueBadge.top));
  });

  testWidgets('completion rate sits above a bar filled to that rate', (
    tester,
  ) async {
    await _pump(
      tester,
      DashboardGroupedAssignmentCard(assignment: _assignment('approved')),
    );

    expect(find.text('73% completed'), findsOneWidget);
    final bar = tester.widget<LinearProgressIndicator>(
      find.byType(LinearProgressIndicator),
    );
    expect(bar.value, closeTo(0.73, 0.001));
    expect(bar.color, GroupedDashboardPalette.pending.accent);
    final barWidth = tester.getSize(find.byType(LinearProgressIndicator)).width;
    final cardWidth = tester
        .getSize(find.byType(DashboardGroupedAssignmentCard))
        .width;
    // Accent stripe (6) plus the card's horizontal padding (14 + 12).
    expect(barWidth, closeTo((cardWidth - 32) / 3, 1));

    final label = tester.widget<Text>(find.text('73% completed'));
    expect(label.style?.color, GroupedDashboardPalette.pending.accent);
  });

  testWidgets('low completion uses the danger colour and a short fill', (
    tester,
  ) async {
    final low = Assignment(
      id: 3,
      name: 'Just started',
      status: 'pending',
      completionRate: 10,
    );
    await _pump(tester, DashboardGroupedAssignmentCard(assignment: low));

    expect(find.text('10% completed'), findsOneWidget);
    final bar = tester.widget<LinearProgressIndicator>(
      find.byType(LinearProgressIndicator),
    );
    expect(bar.value, closeTo(0.10, 0.001));
    expect(bar.color, GroupedDashboardPalette.danger.accent);
  });

  testWidgets('completion bar sits on the last line beside download and enter data', (
    tester,
  ) async {
    await _pump(
      tester,
      DashboardGroupedAssignmentCard(
        assignment: _assignment('pending'),
        showEnterDataButton: true,
        onEnterData: () {},
        onDownloadForOffline: () {},
      ),
    );

    final bar = tester.getRect(find.byType(LinearProgressIndicator));
    final download = tester.getRect(find.byIcon(Icons.download_rounded));
    final enter = tester.getRect(find.text('Enter Data'));
    final label = tester.getRect(find.text('73% completed'));

    expect(label.bottom, lessThanOrEqualTo(bar.top));
    expect(bar.right, lessThan(download.left));
    expect(enter.left - download.right, lessThan(24));
    expect((bar.center.dy - enter.center.dy).abs(), lessThan(24));
  });

  testWidgets('downloaded assignment shows only the saved cloud icon', (
    tester,
  ) async {
    await _pump(
      tester,
      DashboardGroupedAssignmentCard(
        assignment: _assignment('pending'),
        onDownloadForOffline: () {},
        onOfflineBundleDetails: () {},
        hasOfflineFormSnapshot: true,
      ),
    );

    expect(find.byIcon(Icons.download_rounded), findsNothing);
    expect(find.byIcon(Icons.cloud_done_rounded), findsOneWidget);
  });

  testWidgets('not yet downloaded assignment shows only the download icon', (
    tester,
  ) async {
    await _pump(
      tester,
      DashboardGroupedAssignmentCard(
        assignment: _assignment('pending'),
        onDownloadForOffline: () {},
      ),
    );

    expect(find.byIcon(Icons.download_rounded), findsOneWidget);
    expect(find.byIcon(Icons.cloud_done_rounded), findsNothing);
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

    expect(find.byIcon(Icons.mail_rounded), findsOneWidget);
    final paints = tester.widgetList<CustomPaint>(find.byType(CustomPaint));
    expect(
      paints.where((paint) => paint.painter != null).length,
      greaterThan(0),
    );
  });

  ProjectDashboardGroup projectGroup({
    required bool closed,
    required List<Assignment> cycles,
    int active = 0,
  }) {
    return ProjectDashboardGroup(
      projectId: 7,
      reference: 'NSD-7',
      title: 'Health systems',
      projectStatus: closed ? 'Closed' : 'Open',
      projectClosed: closed,
      activeCycleIndex: active,
      cycles: cycles,
    );
  }

  Assignment cycle(int id, String period, DateTime due) {
    return Assignment(
      id: id,
      name: '$period - Quarterly',
      status: 'in_progress',
      completionRate: 40,
      templateName: 'Quarterly',
      periodName: period,
      dueDate: due,
      projectId: 7,
      projectTitle: 'Health systems',
      projectReference: 'NSD-7',
    );
  }

  testWidgets('project card shows the project and the active cycle', (
    tester,
  ) async {
    await _pump(
      tester,
      DashboardProjectGroupCard(
        group: projectGroup(
          closed: false,
          active: 1,
          cycles: [
            cycle(1, 'Y1Q1', DateTime(2026, 3, 1)),
            cycle(2, 'Y1Q2', DateTime(2026, 8, 1)),
          ],
        ),
      ),
    );

    expect(find.text('Health systems'), findsOneWidget);
    expect(find.text('NSD-7'), findsOneWidget);
    expect(find.text('Reporting cycle: Y1Q2'), findsOneWidget);
    expect(find.text('Quarterly — Y1Q2'), findsNothing);
    expect(find.text('Cycles'), findsOneWidget);
    expect(find.text('2'), findsOneWidget);
  });

  testWidgets('a closed project is not marked overdue', (tester) async {
    await _pump(
      tester,
      DashboardProjectGroupCard(
        group: projectGroup(
          closed: true,
          cycles: [cycle(1, 'Y1Q1', DateTime(2020, 1, 1))],
        ),
      ),
    );

    expect(find.text('Overdue'), findsNothing);
    expect(find.text('In Progress'), findsOneWidget);

    final colors = tester
        .widgetList<Material>(find.byType(Material))
        .map((material) => material.color);
    expect(colors, isNot(contains(GroupedDashboardPalette.danger.background)));
  });

  testWidgets('choosing another cycle updates the reporting line', (
    tester,
  ) async {
    await _pump(
      tester,
      DashboardProjectGroupCard(
        group: projectGroup(
          closed: false,
          active: 0,
          cycles: [
            cycle(1, 'Y1Q1', DateTime(2026, 3, 1)),
            cycle(2, 'Y1Q2', DateTime(2026, 8, 1)),
          ],
        ),
      ),
    );

    await tester.tap(find.text('Cycles'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Y1Q2'));
    await tester.pumpAndSettle();

    expect(find.text('Reporting cycle: Y1Q2'), findsOneWidget);
  });
}
