import '../config/app_config.dart';
import '../services/api_service.dart';
import '../services/analytics_service.dart';
import '../services/jwt_token_service.dart';
import '../utils/debug_logger.dart' show DebugLogger, LogLevel;
import '../utils/network_availability.dart';

/// Tracks mobile screen views on both Firebase Analytics and the Backoffice
/// audit trail via `POST /api/mobile/v1/analytics/screen-view`.
///
/// Includes a short client-side dedup window so rapid back/forward taps
/// or tab re-selections don't produce duplicate entries.
class ScreenViewTracker {
  static final ScreenViewTracker _instance = ScreenViewTracker._internal();
  factory ScreenViewTracker() => _instance;
  ScreenViewTracker._internal();

  final ApiService _api = ApiService();
  final AnalyticsService _analytics = AnalyticsService();
  final JwtTokenService _jwtService = JwtTokenService();

  String? _lastScreenName;
  DateTime? _lastTrackedAt;
  static const _dedupWindow = Duration(seconds: 2);

  /// After transport failures, skip Backoffice POST briefly (Wi‑Fi can stay
  /// "connected" while the dev server or tunnel is down).
  DateTime? _suppressServerScreenViewUntil;
  static const _suppressAfterFailure = Duration(seconds: 45);

  /// Human-readable screen name for a route path (Navigator-pushed routes).
  static String screenNameFromRoute(String routePath) {
    return _routeNameMap[routePath] ?? _humanize(routePath);
  }

  /// Human-readable screen name for a tab ID (bottom-nav tabs).
  static String screenNameFromTabId(String tabId) {
    return _tabNameMap[tabId] ?? _humanize(tabId);
  }

  static const _tabNameMap = <String, String>{
    'notifications': 'Notifications',
    'dashboard': 'Dashboard',
    'home': 'Home',
    'ai_chat': 'AI Chat',
    'admin': 'Admin Panel',
    'analysis': 'Disaggregation Analysis',
    'settings': 'Settings',
    'resources': 'Resources',
    'indicators': 'Indicator Bank',
    'unified_planning': 'Unified Planning Documents',
  };

  static const _routeNameMap = <String, String>{
    '/': 'Splash',
    '/login': 'Login',
    '/azure-login': 'Azure Login',
    '/dashboard': 'Home',
    '/settings': 'Settings',
    '/notifications': 'Notifications',
    '/notification-preferences': 'Notification Preferences',
    '/webview': 'WebView',
    '/admin': 'Admin Panel',
    '/admin/dashboard': 'Admin Dashboard',
    '/admin/templates': 'Templates',
    '/admin/assignments': 'Assignments',
    '/admin/users': 'Manage Users',
    '/admin/user-detail': 'User Detail',
    '/admin/access-requests': 'Access Requests',
    '/admin/documents': 'Document Management',
    '/admin/translations/manage': 'Translation Management',
    '/admin/translations/entry': 'Translation Entry Detail',
    '/admin/resources': 'Resources Management',
    '/admin/organization': 'Organizational Structure',
    '/admin/indicator_bank': 'Indicator Bank Admin',
    '/admin/analytics/dashboard': 'User Analytics',
    '/admin/analytics/audit-trail': 'Audit Trail',
    '/admin/login-logs': 'Login Logs',
    '/admin/session-logs': 'Session Logs',
    '/indicator-bank': 'Indicator Bank',
    '/indicator-bank/propose': 'Propose Indicator',
    '/resources': 'Resources',
    '/unified-planning-documents': 'Unified Planning Documents',
    '/unified-planning-analytics': 'Unified Planning Analytics',
    '/disaggregation-analysis': 'Disaggregation Analysis',
    '/countries': 'Countries',
    '/ns-structure': 'NS Structure',
    '/quiz-game': 'Quiz Game',
    '/leaderboard': 'Leaderboard',
    '/ai-chat': 'AI Chat',
    '/world-map-fullscreen': 'World Map',
  };

  static String _humanize(String raw) {
    // Handle parameterized routes with known prefixes
    if (raw == '/indicator-bank/propose') return 'Propose Indicator';
    if (raw.startsWith('/indicator-bank/')) return 'Indicator Detail';
    if (raw.startsWith('/ns-structure/')) return 'NS Structure';
    if (raw.startsWith('/admin/indicator_bank/edit/')) return 'Edit Indicator';
    if (raw.startsWith('/admin/organization/edit/')) return 'Edit Entity';

    final segment = raw.split('/').where((s) => s.isNotEmpty).lastOrNull ?? raw;
    return segment
        .replaceAll('_', ' ')
        .replaceAll('-', ' ')
        .split(' ')
        .map((w) => w.isEmpty ? '' : '${w[0].toUpperCase()}${w.substring(1)}')
        .join(' ');
  }

  /// Track a screen view. Fire-and-forget — errors are swallowed.
  /// [routePath] Navigator route string (e.g. `/admin/analytics`) for Backoffice path keys.
  void trackScreenView(String screenName, {String? screenClass, String? routePath}) {
    if (screenName.isEmpty) return;

    // Client-side dedup
    final now = DateTime.now();
    if (_lastScreenName == screenName &&
        _lastTrackedAt != null &&
        now.difference(_lastTrackedAt!) < _dedupWindow) {
      return;
    }
    _lastScreenName = screenName;
    _lastTrackedAt = now;

    // Firebase Analytics (always, even when unauthenticated)
    _analytics.logScreenView(
      screenName: screenName,
      screenClass: screenClass,
    );

    // Backoffice audit trail (fire-and-forget)
    _postScreenView(screenName, screenClass, routePath);
  }

  Future<void> _postScreenView(
    String screenName,
    String? screenClass,
    String? routePath,
  ) async {
    try {
      final now = DateTime.now();
      if (_suppressServerScreenViewUntil != null &&
          now.isBefore(_suppressServerScreenViewUntil!)) {
        return;
      }

      // Skip the Backoffice POST when the user has no stored tokens — this
      // happens at app startup before auth is established and would always
      // produce an auth error, generating noisy [ERROR] log lines.
      final hasTokens = await _jwtService.hasTokens();
      if (!hasTokens) return;

      // Includes recent primary-backend transport failures (Wi‑Fi can stay "on").
      if (shouldDeferRemoteFetch) return;

      final body = <String, dynamic>{
        'screen_name': screenName,
        if (screenClass != null && screenClass.isNotEmpty) 'screen_class': screenClass,
        if (routePath != null && routePath.isNotEmpty) 'route_path': routePath,
      };
      await _api.post(
        AppConfig.mobileScreenViewEndpoint,
        body: body,
        queueOnOffline: false,
      );
    } catch (e) {
      if (isTransientBackendFailure(e)) {
        _suppressServerScreenViewUntil =
            DateTime.now().add(_suppressAfterFailure);
        DebugLogger.log(
          'SCREEN_VIEW',
          'screen_view skipped (transient): $e',
          level: LogLevel.debug,
        );
      } else {
        DebugLogger.logWarn('SCREEN_VIEW', 'screen_view tracking failed: $e');
      }
    }
  }
}
