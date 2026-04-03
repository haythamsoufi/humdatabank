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
  static const String users = '/admin/users';
  static const String documentManagement = '/admin/documents';
  static const String translationManagement = '/admin/translations/manage';
  static const String pluginManagement = '/admin/plugins';
  static const String systemConfiguration = '/admin/settings';
  static const String resourcesManagement = '/admin/resources';
  static const String organizationalStructure = '/admin/organization';
  static String editEntity(int id, [String? entityType]) => entityType != null
      ? '/admin/organization/edit/$entityType/$id'
      : '/admin/organization/edit/$id';
  static const String indicatorBankAdmin = '/admin/indicator_bank';
  static String editIndicator(int id) => '/admin/indicator_bank/edit/$id';
  static const String userAnalytics = '/admin/analytics/dashboard';
  static const String auditTrail = '/admin/analytics/audit-trail';
  static const String apiManagement = '/api-management';
  static const String pushNotifications = '/admin/push-notifications';

  // Public Screens
  static const String indicatorBank = '/indicator-bank';
  static String indicatorDetail(int id) => '/indicator-bank/$id';
  static const String resources = '/resources';
  static const String disaggregationAnalysis = '/disaggregation-analysis';
  static const String countries = '/countries';
  static const String nsStructure = '/ns-structure';
  static String nsStructureForCountry(int countryId) => '/ns-structure/$countryId';
  static const String quizGame = '/quiz-game';
  static const String leaderboard = '/leaderboard';
  static const String aiChat = '/ai-chat';
  static const String aiConversations = '/ai-conversations';

  // WebView Routes (for other admin pages)
  static const String formBuilder = '/admin/form-builder';
  static const String userManagement = '/admin/users';
  static const String analytics = '/admin/analytics';

  static String formEntry(int assignmentId) =>
      '/forms/assignment/$assignmentId';
}
