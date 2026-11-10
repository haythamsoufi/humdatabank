import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/models/shared/assignment.dart';
import 'package:hum_databank_app/models/shared/project_dashboard_group.dart';

Assignment _cycle({
  required int id,
  required String period,
  DateTime? due,
  String status = 'in_progress',
  bool closed = false,
}) {
  return Assignment(
    id: id,
    name: '$period - Quarterly',
    status: status,
    completionRate: 10,
    templateName: 'Quarterly',
    periodName: period,
    dueDate: due,
    projectId: 7,
    projectTitle: 'Health systems',
    projectReference: 'NSD-7',
    projectStatus: closed ? 'Closed' : 'Open',
    projectClosed: closed,
  );
}

void main() {
  final today = DateTime(2026, 6, 15);

  test('groups one project into a single card and keeps other assignments', () {
    final country = Assignment(
      id: 1,
      name: 'Annual',
      status: 'pending',
      completionRate: 0,
      templateName: 'Annual',
      periodName: '2026',
    );
    final cards = groupProjectDashboardCards([
      _cycle(id: 3, period: 'Y1Q2', due: DateTime(2026, 8, 1)),
      country,
      _cycle(id: 2, period: 'Y1Q1', due: DateTime(2026, 3, 1)),
    ], today: today);

    expect(cards, hasLength(2));
    expect(cards.first.project, isNotNull);
    expect(cards.first.project!.displayTitle, 'Health systems');
    expect(cards.first.project!.showReference, isTrue);
    expect(cards.first.project!.reference, 'NSD-7');
    expect(cards.first.project!.cycles.map((c) => c.periodName), [
      'Y1Q1',
      'Y1Q2',
    ]);
    // Next due date on or after today.
    expect(cards.first.project!.activeCycleIndex, 1);
    expect(cards.last.assignment, same(country));
  });

  test('active cycle is the latest dated round when every cycle is past due', () {
    final cycles = [
      _cycle(id: 1, period: 'Y1Q1', due: DateTime(2026, 1, 1)),
      _cycle(id: 2, period: 'Y1Q2', due: DateTime(2026, 4, 1)),
    ];
    expect(pickProjectDashboardCycleIndex(cycles..sort((a, b) => a.id.compareTo(b.id)), today), 1);
    final cards = groupProjectDashboardCards(cycles, today: today);
    expect(cards.single.project!.activeCycleIndex, 1);
  });

  test('cycle tags match the web menu', () {
    final past = _cycle(id: 1, period: 'Y1Q1', due: DateTime(2026, 3, 1), status: 'approved');
    final current = _cycle(id: 2, period: 'Y1Q2', due: DateTime(2026, 8, 1));
    final upcoming = _cycle(id: 3, period: 'Y1Q3', due: DateTime(2026, 11, 1));
    expect(
      projectCycleTag(index: 0, activeIndex: 1, cycle: past, today: today),
      'past',
    );
    expect(
      projectCycleTag(index: 1, activeIndex: 1, cycle: current, today: today),
      'current',
    );
    expect(
      projectCycleTag(index: 2, activeIndex: 1, cycle: upcoming, today: today),
      'upcoming',
    );

    final late = _cycle(id: 4, period: 'Y1Q1', due: DateTime(2026, 1, 1));
    expect(
      projectCycleTag(index: 0, activeIndex: 1, cycle: late, today: today),
      'overdue',
    );
  });

  test('project fields round-trip through JSON', () {
    final original = _cycle(
      id: 9,
      period: 'Y2Q1',
      due: DateTime.utc(2026, 9, 1),
      closed: true,
    );
    final again = Assignment.fromJson(original.toJson());
    expect(again.projectId, 7);
    expect(again.projectTitle, 'Health systems');
    expect(again.projectReference, 'NSD-7');
    expect(again.projectClosed, isTrue);
    expect(again.isRoundClosed, isFalse);
  });
}
