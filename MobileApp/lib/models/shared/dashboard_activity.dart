/// One row of the dashboard recent-activities feed.
///
/// The server sends the same facts the back office dashboard renders: who
/// made the change, which assignment it belongs to, a localized summary, and
/// the individual field lines for a multi-field save.
class DashboardActivity {
  const DashboardActivity({
    required this.id,
    this.timestamp,
    this.user,
    this.assignmentId,
    this.assignmentTitle,
    this.templatePeriod,
    this.summaryKey,
    this.changeType,
    this.changeCount,
    this.summary = '',
    this.changes = const [],
  });

  final String id;
  final DateTime? timestamp;
  final DashboardActivityUser? user;
  final int? assignmentId;
  final String? assignmentTitle;
  final String? templatePeriod;
  final String? summaryKey;
  final String? changeType;
  final int? changeCount;
  final String summary;
  final List<DashboardActivityChange> changes;

  /// Stable id for the user filter. Empty when the activity has no user.
  String get filterUserId => user == null ? '' : '${user!.id}';

  String get filterTemplatePeriod {
    final period = templatePeriod?.trim();
    if (period != null && period.isNotEmpty) return period;
    return assignmentTitle?.trim() ?? '';
  }

  factory DashboardActivity.fromJson(Map<String, dynamic> json) {
    final userJson = json['user'];
    return DashboardActivity(
      id: json['id']?.toString() ?? '',
      timestamp: DateTime.tryParse(json['timestamp']?.toString() ?? ''),
      user: userJson is Map
          ? DashboardActivityUser.fromJson(Map<String, dynamic>.from(userJson))
          : null,
      assignmentId: _asInt(json['assignment_id']),
      assignmentTitle: _text(json['assignment_title']),
      templatePeriod: _text(json['template_period']),
      summaryKey: _text(json['summary_key']),
      changeType: _text(json['change_type']),
      changeCount: _asInt(json['change_count']),
      summary: json['summary']?.toString() ?? '',
      changes: [
        for (final item in (json['changes'] as List? ?? const []))
          if (item is Map)
            DashboardActivityChange.fromJson(Map<String, dynamic>.from(item)),
      ],
    );
  }

  Map<String, dynamic> toJson() => {
    'id': id,
    'timestamp': timestamp?.toUtc().toIso8601String(),
    'user': user?.toJson(),
    'assignment_id': assignmentId,
    'assignment_title': assignmentTitle,
    'template_period': templatePeriod,
    'summary_key': summaryKey,
    'change_type': changeType,
    'change_count': changeCount,
    'summary': summary,
    'changes': [for (final change in changes) change.toJson()],
  };
}

class DashboardActivityUser {
  const DashboardActivityUser({
    required this.id,
    this.name,
    this.email = '',
    this.title,
  });

  final int id;
  final String? name;
  final String email;
  final String? title;

  String get displayName {
    final trimmed = name?.trim();
    if (trimmed != null && trimmed.isNotEmpty) return trimmed;
    if (email.contains('@')) return email.split('@').first;
    if (email.isNotEmpty) return email;
    return '';
  }

  String get initials {
    final source = displayName.trim();
    if (source.isEmpty) return '?';
    final parts = source.split(RegExp(r'\s+'));
    if (parts.length >= 2 && parts.first.isNotEmpty && parts.last.isNotEmpty) {
      return '${parts.first[0]}${parts.last[0]}'.toUpperCase();
    }
    return source.substring(0, 1).toUpperCase();
  }

  factory DashboardActivityUser.fromJson(Map<String, dynamic> json) {
    return DashboardActivityUser(
      id: _asInt(json['id']) ?? 0,
      name: _text(json['name']),
      email: json['email']?.toString() ?? '',
      title: _text(json['title']),
    );
  }

  Map<String, dynamic> toJson() => {
    'id': id,
    'name': name,
    'email': email,
    'title': title,
  };
}

class DashboardActivityChange {
  const DashboardActivityChange({required this.changeType, required this.text});

  final String changeType;
  final String text;

  factory DashboardActivityChange.fromJson(Map<String, dynamic> json) {
    return DashboardActivityChange(
      changeType: json['change_type']?.toString() ?? 'updated',
      text: json['text']?.toString() ?? '',
    );
  }

  Map<String, dynamic> toJson() => {'change_type': changeType, 'text': text};
}

/// One page of the activities feed, from the dashboard or from "load more".
class DashboardActivityPage {
  const DashboardActivityPage({
    required this.activities,
    required this.hasMore,
  });

  final List<DashboardActivity> activities;
  final bool hasMore;

  factory DashboardActivityPage.fromJson(Map<String, dynamic> json) {
    return DashboardActivityPage(
      activities: [
        for (final item in (json['recent_activities'] as List? ?? const []))
          if (item is Map)
            DashboardActivity.fromJson(Map<String, dynamic>.from(item)),
      ],
      hasMore:
          json['recent_activities_has_more'] == true ||
          json['has_more'] == true,
    );
  }
}

int? _asInt(dynamic value) {
  if (value is int) return value;
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '');
}

String? _text(dynamic value) {
  final text = value?.toString().trim() ?? '';
  return text.isEmpty ? null : text;
}
