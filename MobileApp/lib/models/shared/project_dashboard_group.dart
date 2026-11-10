import 'assignment.dart';

/// One project card: the reporting cycles that are still on the current list.
///
/// Mirrors Backoffice `group_dashboard_project_assignments`: cycles are ordered
/// by due date, the active cycle is the next one due today or later, and a
/// closed project does not show as overdue.
class ProjectDashboardGroup {
  const ProjectDashboardGroup({
    required this.projectId,
    required this.reference,
    required this.title,
    required this.projectStatus,
    required this.projectClosed,
    required this.activeCycleIndex,
    required this.cycles,
  });

  final int projectId;
  final String reference;
  final String title;
  final String projectStatus;
  final bool projectClosed;
  final int activeCycleIndex;
  final List<Assignment> cycles;

  String get displayTitle {
    final trimmed = title.trim();
    if (trimmed.isNotEmpty) return trimmed;
    final ref = reference.trim();
    return ref.isNotEmpty ? ref : '#$projectId';
  }

  bool get showReference =>
      title.trim().isNotEmpty && reference.trim().isNotEmpty;

  Assignment cycleAt(int index) {
    if (cycles.isEmpty) {
      throw StateError('Project $projectId has no cycles');
    }
    final safe = index.clamp(0, cycles.length - 1);
    return cycles[safe];
  }
}

/// A current-dashboard row: either one ordinary assignment or one project card.
class DashboardCardItem {
  const DashboardCardItem.assignment(this.assignment) : project = null;

  const DashboardCardItem.project(this.project) : assignment = null;

  final Assignment? assignment;
  final ProjectDashboardGroup? project;

  bool get isProject => project != null;
}

/// Collapses project-entity assignments that share a [Assignment.projectId].
///
/// Card order follows the first cycle of each project in [items] (the API
/// already orders by due date). Other assignments stay as their own cards.
List<DashboardCardItem> groupProjectDashboardCards(
  List<Assignment> items, {
  DateTime? today,
}) {
  final now = today ?? DateTime.now();
  final byProject = <int, List<Assignment>>{};
  for (final item in items) {
    final projectId = item.projectId;
    if (projectId == null) continue;
    byProject.putIfAbsent(projectId, () => []).add(item);
  }

  final groups = <int, ProjectDashboardGroup>{};
  for (final entry in byProject.entries) {
    final cycles = List<Assignment>.of(entry.value)..sort(_compareCycles);
    final sample = cycles.first;
    groups[entry.key] = ProjectDashboardGroup(
      projectId: entry.key,
      reference: (sample.projectReference ?? '').trim(),
      title: (sample.projectTitle ?? '').trim(),
      projectStatus: (sample.projectStatus ?? '').trim(),
      projectClosed: cycles.any((cycle) => cycle.projectClosed),
      activeCycleIndex: pickProjectDashboardCycleIndex(cycles, now),
      cycles: cycles,
    );
  }

  final seen = <int>{};
  final cards = <DashboardCardItem>[];
  for (final item in items) {
    final projectId = item.projectId;
    if (projectId == null) {
      cards.add(DashboardCardItem.assignment(item));
      continue;
    }
    if (seen.add(projectId)) {
      cards.add(DashboardCardItem.project(groups[projectId]!));
    }
  }
  return cards;
}

/// Active round = the cycle with the next due date on or after [today].
///
/// Cycles must already be in [_compareCycles] order. If every dated cycle is
/// past due, the latest one is active.
int pickProjectDashboardCycleIndex(List<Assignment> cycles, DateTime today) {
  if (cycles.isEmpty) return 0;
  final todayDate = DateTime(today.year, today.month, today.day);
  for (var i = 0; i < cycles.length; i++) {
    final due = _dateOnly(cycles[i].dueDate);
    if (due != null && !due.isBefore(todayDate)) return i;
  }
  for (var i = cycles.length - 1; i >= 0; i--) {
    if (cycles[i].dueDate != null) return i;
  }
  return cycles.length - 1;
}

/// Current / Overdue / Upcoming / Past, using the same rules as the web menu.
///
/// The active cycle is always "current", even when its due date has passed.
/// The card chrome, not this label, shows that it is overdue.
String projectCycleTag({
  required int index,
  required int activeIndex,
  required Assignment cycle,
  required DateTime today,
}) {
  if (index == activeIndex) return 'current';
  if (_isLate(cycle, today)) return 'overdue';
  if (index > activeIndex) return 'upcoming';
  return 'past';
}

bool projectCycleIsLate(Assignment cycle, DateTime today) =>
    _isLate(cycle, today);

int _compareCycles(Assignment a, Assignment b) {
  final aDue = _dateOnly(a.dueDate);
  final bDue = _dateOnly(b.dueDate);
  if (aDue == null && bDue != null) return 1;
  if (aDue != null && bDue == null) return -1;
  if (aDue != null && bDue != null) {
    final byDue = aDue.compareTo(bDue);
    if (byDue != 0) return byDue;
  }
  final byPeriod = _comparePeriod(a.periodName, b.periodName);
  if (byPeriod != 0) return byPeriod;
  return a.id.compareTo(b.id);
}

DateTime? _dateOnly(DateTime? value) {
  if (value == null) return null;
  final local = value.toLocal();
  return DateTime(local.year, local.month, local.day);
}

bool _isDoneStatus(String status) {
  switch (status.toLowerCase().trim()) {
    case 'submitted':
    case 'approved':
    case 'requires_revision':
    case 'requires revision':
    case 'sent_for_review':
    case 'sent for review':
    case 'cancelled':
    case 'canceled':
      return true;
    default:
      return false;
  }
}

bool _isLate(Assignment cycle, DateTime today) {
  final due = _dateOnly(cycle.dueDate);
  if (due == null || _isDoneStatus(cycle.status)) return false;
  final todayDate = DateTime(today.year, today.month, today.day);
  return due.isBefore(todayDate);
}

int _comparePeriod(String? a, String? b) {
  final ak = _periodSortKey(a);
  final bk = _periodSortKey(b);
  final byTier = ak.$1.compareTo(bk.$1);
  if (byTier != 0) return byTier;
  final byYear = ak.$2.compareTo(bk.$2);
  if (byYear != 0) return byYear;
  final byQuarter = ak.$3.compareTo(bk.$3);
  if (byQuarter != 0) return byQuarter;
  return ak.$4.compareTo(bk.$4);
}

/// `(tier, year, quarter, label)` so Y1Q2 sorts before Y2Q1 and before Final.
(int, int, int, String) _periodSortKey(String? period) {
  final value = (period ?? '').trim();
  final match = RegExp(r'^Y(\d+)Q(\d+)$', caseSensitive: false).firstMatch(value);
  if (match != null) {
    return (
      0,
      int.parse(match.group(1)!),
      int.parse(match.group(2)!),
      '',
    );
  }
  if (value.toLowerCase() == 'final') return (1, 0, 0, value);
  return (2, 0, 0, value);
}
