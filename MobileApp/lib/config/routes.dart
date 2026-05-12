class AppRoutes {
  static const String splash = '/';
  static const String login = '/login';
  static const String azureLogin = '/azure-login';
  static const String dashboard = '/dashboard';
  static const String settings = '/settings';
  static const String notifications = '/notifications';
  static const String webview = '/webview';

  // Admin Screens
  static const String admin = '/admin';
  static const String adminDashboard = '/admin/dashboard';
  static const String templates = '/admin/templates';
  static const String assignments = '/admin/assignments';

  /// Native assignment summary (pass `AdminAssignment` as route `arguments`).
  static String assignmentDetail(int assignmentId) =>
      '/admin/assignments/$assignmentId';
  static const String users = '/admin/users';
  /// Native user edit/detail (not in [routes] map — pushed from [ManageUsersScreen]).
  static const String adminUserDetail = '/admin/user-detail';
  static const String accessRequests = '/admin/access-requests';
  static const String documentManagement = '/admin/documents';

  /// Native document summary (pass [Document] as route `arguments`).
  static String documentDetail(int documentId) => '/admin/documents/$documentId';
  static const String translationManagement = '/admin/translations/manage';
  static const String translationEntryDetail = '/admin/translations/entry';
  static const String pluginManagement = '/admin/plugins';
  static const String systemConfiguration = '/admin/settings';
  static const String resourcesManagement = '/admin/resources';

  /// Native resource summary (pass [Resource] as route `arguments`).
  static String resourceDetail(int resourceId) => '/admin/resources/$resourceId';
  static const String organizationalStructure = '/admin/organization';
  static String editEntity(int id, [String? entityType]) => entityType != null
      ? '/admin/organization/edit/$entityType/$id'
      : '/admin/organization/edit/$id';
  static const String indicatorBankAdmin = '/admin/indicator_bank';
  static String editIndicator(int id) => '/admin/indicator_bank/edit/$id';
  static const String userAnalytics = '/admin/analytics/dashboard';
  static const String auditTrail = '/admin/analytics/audit-trail';
  static const String loginLogs = '/admin/login-logs';
  static const String sessionLogs = '/admin/session-logs';
  static const String apiManagement = '/api-management';
  static const String pushNotifications = '/admin/push-notifications';

  // Public Screens
  static const String indicatorBank = '/indicator-bank';
  static const String proposeIndicator = '/indicator-bank/propose';
  static String indicatorDetail(int id) => '/indicator-bank/$id';
  static const String resources = '/resources';
  static const String unifiedPlanningDocuments = '/unified-planning-documents';
  static const String unifiedPlanningAnalytics = '/unified-planning-analytics';
  static const String pdfViewer = '/pdf-viewer';
  static const String disaggregationAnalysis = '/disaggregation-analysis';
  static const String countries = '/countries';
  static const String nsStructure = '/ns-structure';
  static String nsStructureForCountry(int countryId) => '/ns-structure/$countryId';
  static const String quizGame = '/quiz-game';
  static const String leaderboard = '/leaderboard';
  static const String aiChat = '/ai-chat';

  // WebView Routes (for other admin pages)
  /// Backoffice form templates (list / builder lives under `/admin/templates/...`).
  static const String formBuilder = '/admin/templates';
  static const String userManagement = '/admin/users';
  static const String analytics = '/admin/analytics';

  static String formEntry(int assignmentId) =>
      '/forms/assignment/$assignmentId';

  /// True when [rawPath] is implemented as a Flutter screen (see [MaterialApp.routes]
  /// and [onGenerateRoute] in `main.dart`). Other `/admin/...` paths are web-only
  /// and should open in a WebView (e.g. `/admin/access-requests`).
  static bool isNativeAdminPath(String rawPath) {
    final path = rawPath.split('?').first.split('#').first;
    if (!path.startsWith('/admin')) return false;

    const exact = <String>{
      '/admin',
      '/admin/dashboard',
      '/admin/templates',
      '/admin/assignments',
      '/admin/users',
      '/admin/access-requests',
      '/admin/documents',
      '/admin/translations/manage',
      '/admin/translations/entry',
      '/admin/resources',
      '/admin/organization',
      '/admin/indicator_bank',
      '/admin/analytics/dashboard',
      '/admin/analytics/audit-trail',
      '/admin/login-logs',
      '/admin/session-logs',
    };
    if (exact.contains(path)) return true;

    if (path.startsWith('/admin/indicator_bank/edit/')) {
      final id = int.tryParse(path.split('/').last);
      return id != null;
    }

    if (path.startsWith('/admin/assignments/')) {
      final parts = path.split('/');
      if (parts.length == 4) {
        return int.tryParse(parts[3]) != null;
      }
    }

    if (path.startsWith('/admin/organization/edit/')) {
      final parts = path.split('/');
      if (parts.length == 6) {
        return int.tryParse(parts[5]) != null;
      }
      if (parts.length == 5) {
        return int.tryParse(parts[4]) != null;
      }
    }

    // Document detail: /admin/documents/{id} (not edit/serve/download/…)
    if (path.startsWith('/admin/documents/')) {
      final parts = path.split('/').where((s) => s.isNotEmpty).toList();
      if (parts.length == 3 && parts[0] == 'admin' && parts[1] == 'documents') {
        return int.tryParse(parts[2]) != null;
      }
    }

    // Resource detail: /admin/resources/{id} (not new/edit/…)
    if (path.startsWith('/admin/resources/')) {
      final parts = path.split('/').where((s) => s.isNotEmpty).toList();
      if (parts.length == 3 && parts[0] == 'admin' && parts[1] == 'resources') {
        return int.tryParse(parts[2]) != null;
      }
    }
    return false;
  }
}
