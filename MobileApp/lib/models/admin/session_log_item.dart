/// One row from [GET /admin/api/analytics/session-logs].
class SessionLogItem {
  const SessionLogItem({
    required this.sessionId,
    this.sessionStartIso,
    this.sessionEndIso,
    this.lastActivityIso,
    this.durationMinutes,
    this.activeDurationMinutes,
    required this.pageViews,
    this.distinctPageViewPaths = 0,
    this.pageViewPathCounts = const {},
    required this.activityCount,
    required this.isActive,
    this.deviceType,
    this.browser,
    this.operatingSystem,
    this.ipAddress,
    this.userAgent,
    this.userName,
    this.userEmail,
  });

  final String sessionId;
  final String? sessionStartIso;
  final String? sessionEndIso;
  final String? lastActivityIso;
  final int? durationMinutes;
  /// Minutes from session start to last activity (excludes idle after last activity).
  final int? activeDurationMinutes;
  final int pageViews;
  /// Number of distinct canonical path keys in [pageViewPathCounts] (from API).
  final int distinctPageViewPaths;
  /// Histogram path key -> hit count (same source as web session logs).
  final Map<String, int> pageViewPathCounts;
  final int activityCount;
  final bool isActive;
  final String? deviceType;
  final String? browser;
  final String? operatingSystem;
  final String? ipAddress;
  final String? userAgent;
  final String? userName;
  final String? userEmail;

  factory SessionLogItem.fromJson(Map<String, dynamic> json) {
    final user = json['user'];
    String? uname;
    String? uemail;
    if (user is Map<String, dynamic>) {
      uname = user['name']?.toString();
      uemail = user['email']?.toString();
    }
    final dm = json['duration_minutes'];
    final am = json['active_duration_minutes'];
    return SessionLogItem(
      sessionId: json['session_id']?.toString() ?? '',
      sessionStartIso: json['session_start']?.toString(),
      sessionEndIso: json['session_end']?.toString(),
      lastActivityIso: json['last_activity']?.toString(),
      durationMinutes: dm == null
          ? null
          : (dm is int ? dm : int.tryParse('$dm')),
      activeDurationMinutes: am == null
          ? null
          : (am is int ? am : int.tryParse('$am')),
      pageViews: json['page_views'] is int
          ? json['page_views'] as int
          : int.tryParse('${json['page_views'] ?? 0}') ?? 0,
      distinctPageViewPaths: json['distinct_page_view_paths'] is int
          ? json['distinct_page_view_paths'] as int
          : int.tryParse('${json['distinct_page_view_paths'] ?? 0}') ?? 0,
      pageViewPathCounts: _parsePageViewPathCounts(json['page_view_path_counts']),
      activityCount: json['activity_count'] is int
          ? json['activity_count'] as int
          : int.tryParse('${json['activity_count'] ?? 0}') ?? 0,
      isActive: json['is_active'] == true,
      deviceType: json['device_type']?.toString(),
      browser: json['browser']?.toString(),
      operatingSystem: json['operating_system']?.toString(),
      ipAddress: json['ip_address']?.toString(),
      userAgent: json['user_agent']?.toString(),
      userName: uname,
      userEmail: uemail,
    );
  }

  static Map<String, int> _parsePageViewPathCounts(dynamic raw) {
    if (raw is! Map) return const {};
    final out = <String, int>{};
    raw.forEach((dynamic k, dynamic v) {
      final key = k?.toString() ?? '';
      final n = v is int ? v : int.tryParse('$v') ?? 0;
      out[key] = n;
    });
    return Map<String, int>.unmodifiable(out);
  }

  /// Entries sorted by count descending, then path key ascending.
  List<MapEntry<String, int>> get sortedPathEntries {
    final list = pageViewPathCounts.entries.toList();
    list.sort((a, b) {
      final c = b.value.compareTo(a.value);
      if (c != 0) return c;
      return a.key.compareTo(b.key);
    });
    return list;
  }
}
