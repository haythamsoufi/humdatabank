import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/l10n/app_localizations.dart';
import 'package:hum_databank_app/models/shared/dashboard_activity.dart';
import 'package:hum_databank_app/widgets/dashboard_recent_activities_section.dart';
import 'package:intl/date_symbol_data_local.dart';

DashboardActivity _activity({
  String id = '1',
  String name = 'Ada Lovelace',
  String summary = 'People reached: 1 → 4',
  String? changeType = 'updated',
  String title = 'Plan – 2026',
}) {
  return DashboardActivity(
    id: id,
    timestamp: DateTime.utc(2026, 3, 1, 12),
    user: DashboardActivityUser(
      id: int.parse(id),
      name: name,
      email: 'ada@example.org',
    ),
    assignmentId: 9,
    assignmentTitle: title,
    templatePeriod: title,
    changeType: changeType,
    summary: summary,
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

  testWidgets('shows the activity the way the back office feed does', (
    tester,
  ) async {
    await _pump(
      tester,
      DashboardRecentActivitiesSection(
        entityLabel: 'Syria',
        activities: [_activity()],
        hasMore: false,
        isLoading: false,
        isLoadingMore: false,
        onOpenAssignment: (_) {},
        onLoadMore: null,
      ),
    );

    expect(find.text('RECENT ACTIVITIES'), findsOneWidget);
    expect(find.text('Last month'), findsOneWidget);
    expect(find.text('Ada Lovelace'), findsOneWidget);
    expect(find.text('Plan – 2026'), findsOneWidget);
    expect(find.text('Updated'), findsOneWidget);
    expect(find.text('People reached: 1 → 4'), findsOneWidget);
  });

  testWidgets('empty feed explains that focal-point activity will appear', (
    tester,
  ) async {
    await _pump(
      tester,
      DashboardRecentActivitiesSection(
        entityLabel: 'Syria',
        activities: const [],
        hasMore: false,
        isLoading: false,
        isLoadingMore: false,
        onOpenAssignment: (_) {},
        onLoadMore: null,
      ),
    );

    expect(find.text('No recent activities'), findsOneWidget);
    expect(
      find.textContaining('Activities from other focal points in Syria'),
      findsOneWidget,
    );
  });

  testWidgets('offers a user filter when more than one person appears', (
    tester,
  ) async {
    await _pump(
      tester,
      DashboardRecentActivitiesSection(
        entityLabel: 'Syria',
        activities: [
          _activity(),
          _activity(id: '2', name: 'Grace Hopper', summary: 'Submitted'),
        ],
        hasMore: false,
        isLoading: false,
        isLoadingMore: false,
        onOpenAssignment: (_) {},
        onLoadMore: null,
      ),
    );

    expect(find.text('Filter by User'), findsOneWidget);
  });

  test('parses a dashboard activity payload', () {
    final activity = DashboardActivity.fromJson({
      'id': 12,
      'timestamp': '2026-03-01T12:00:00Z',
      'user': {'id': 3, 'name': 'Ada', 'email': 'ada@example.org'},
      'assignment_id': 9,
      'assignment_title': 'Plan – 2026',
      'summary': 'Assignment submitted: Plan – 2026',
      'changes': [
        {'change_type': 'added', 'text': 'Notes: hello'},
      ],
    });

    expect(activity.id, '12');
    expect(activity.assignmentId, 9);
    expect(activity.user!.displayName, 'Ada');
    expect(activity.changes.single.changeType, 'added');
    expect(activity.timestamp!.toUtc(), DateTime.utc(2026, 3, 1, 12));
  });
}
