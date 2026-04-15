import 'dart:async';
import 'package:app_links/app_links.dart';
import 'package:provider/provider.dart';
import '../config/routes.dart';
import '../config/app_navigation.dart';
import '../providers/shared/auth_provider.dart';
import '../utils/debug_logger.dart';

class DeepLinkService {
  static final DeepLinkService _instance = DeepLinkService._internal();
  factory DeepLinkService() => _instance;
  DeepLinkService._internal();

  // Broadcast stream for Azure OAuth mobile deep-link callbacks.
  // AzureLoginScreen subscribes to this to receive JWT tokens after the
  // Chrome Custom Tabs OAuth flow completes.
  static final StreamController<Map<String, String>> _oauthTokenController =
      StreamController<Map<String, String>>.broadcast();

  static Stream<Map<String, String>> get oauthTokenStream =>
      _oauthTokenController.stream;

  // Buffer for the OAuth token payload that arrives via getInitialLink() when
  // the app is cold-started by the deep-link callback (e.g. the app was killed
  // while the browser was open). Broadcast streams do not replay events, so
  // the token would be lost before AzureLoginScreen subscribes. Callers (e.g.
  // AzureLoginScreen.initState) should call consumePendingOAuthTokens() once
  // after subscribing to the stream to pick up any already-fired initial link.
  static Map<String, String>? _pendingInitialOAuthTokens;
  static DateTime? _pendingTokensTimestamp;

  /// Max age for pending cold-start tokens. Tokens older than this are
  /// considered stale (the user likely navigated away and came back later).
  static const Duration _maxPendingTokenAge = Duration(minutes: 2);

  /// Returns and clears the OAuth token payload from a cold-start deep link,
  /// or null if there was none (or if the tokens are stale).
  /// Call once from AzureLoginScreen.initState after setting up the
  /// oauthTokenStream subscription.
  static Map<String, String>? consumePendingOAuthTokens() {
    final tokens = _pendingInitialOAuthTokens;
    final ts = _pendingTokensTimestamp;
    _pendingInitialOAuthTokens = null;
    _pendingTokensTimestamp = null;

    if (tokens == null) {
      DebugLogger.logInfo('DEEPLINK', 'No pending cold-start OAuth tokens');
      return null;
    }

    final age = ts != null ? DateTime.now().difference(ts) : null;
    if (age != null && age > _maxPendingTokenAge) {
      DebugLogger.logWarn('DEEPLINK',
          'Discarding stale cold-start OAuth tokens (age: ${age.inSeconds}s, '
          'max: ${_maxPendingTokenAge.inSeconds}s)');
      return null;
    }

    DebugLogger.logInfo('DEEPLINK',
        'Returning pending cold-start OAuth tokens '
        '(age: ${age?.inSeconds ?? "?"}s)');
    return tokens;
  }

  late final AppLinks _appLinks;
  StreamSubscription<Uri>? _linkSubscription;
  bool _initialized = false;

  Future<void> initialize() async {
    if (_initialized) return;
    _appLinks = AppLinks();
    _initialized = true;

    // Handle initial link (app opened via deep link while not running).
    // For OAuth callbacks, we buffer the payload in _pendingInitialOAuthTokens
    // as well as broadcasting it — broadcast streams do not replay, so a late
    // subscriber (AzureLoginScreen) would miss the event otherwise.
    try {
      final initialUri = await _appLinks.getInitialLink();
      if (initialUri != null) {
        DebugLogger.logInfo('DEEPLINK', 'Initial deep link: $initialUri');
        _handleDeepLink(initialUri, isInitialLink: true);
      }
    } catch (e) {
      DebugLogger.logError('Failed to get initial deep link: $e');
    }

    // Listen for incoming links while the app is already running.
    // These are never cold-start links, so no buffering is needed.
    _linkSubscription = _appLinks.uriLinkStream.listen(
      (uri) {
        DebugLogger.logInfo('DEEPLINK', 'Received deep link: $uri');
        _handleDeepLink(uri);
      },
      onError: (e) {
        DebugLogger.logError('Deep link stream error: $e');
      },
    );
  }

  void _handleDeepLink(Uri uri, {bool isInitialLink = false}) {
    // Handle Azure OAuth mobile callback — delivers JWT tokens to the waiting
    // AzureLoginScreen without going through the Navigator.
    if (uri.scheme == 'humdatabank' && uri.host == 'oauth-success') {
      final params = Map<String, String>.from(uri.queryParameters);
      final hasAccess = params.containsKey('access_token') &&
          (params['access_token']?.isNotEmpty ?? false);
      final hasRefresh = params.containsKey('refresh_token') &&
          (params['refresh_token']?.isNotEmpty ?? false);
      DebugLogger.logInfo('DEEPLINK',
          'Azure OAuth callback received — '
          'isInitialLink: $isInitialLink, '
          'has_access_token: $hasAccess, '
          'has_refresh_token: $hasRefresh, '
          'expires_in: ${params['expires_in'] ?? "absent"}');
      if (isInitialLink) {
        // Buffer for AzureLoginScreen to consume after subscribing (cold-start
        // race: the broadcast fires before any subscriber exists).
        _pendingInitialOAuthTokens = params;
        _pendingTokensTimestamp = DateTime.now();
        DebugLogger.logInfo('DEEPLINK',
            'Buffered cold-start OAuth tokens for AzureLoginScreen');
      }
      _oauthTokenController.add(params);
      return;
    }

    final path = uri.path;
    final navigatorState = appNavigatorKey.currentState;
    if (navigatorState == null) {
      DebugLogger.logWarn('DEEPLINK', 'Navigator not available for deep link: $uri');
      return;
    }

    // Map deep link paths to app routes
    if (path == '/' || path.isEmpty) {
      navigatorState.pushNamedAndRemoveUntil(AppRoutes.dashboard, (route) => false);
    } else if (path == '/indicator-bank' || path == '/indicators') {
      navigatorState.pushNamed(AppRoutes.indicatorBank);
    } else if (path == AppRoutes.proposeIndicator) {
      navigatorState.pushNamed(AppRoutes.proposeIndicator);
    } else if (path.startsWith('/indicator-bank/')) {
      final idStr = path.split('/').last;
      final id = int.tryParse(idStr);
      if (id != null) {
        navigatorState.pushNamed(AppRoutes.indicatorDetail(id));
      }
    } else if (path == '/resources') {
      navigatorState.pushNamed(AppRoutes.resources);
    } else if (path == '/countries') {
      navigatorState.pushNamed(AppRoutes.countries);
    } else if (path.startsWith('/ns-structure/')) {
      final idStr = path.split('/').last;
      final countryId = int.tryParse(idStr);
      if (countryId != null) {
        navigatorState.pushNamed(AppRoutes.nsStructureForCountry(countryId));
      }
    } else if (path == '/quiz-game') {
      navigatorState.pushNamed(AppRoutes.quizGame);
    } else if (path == '/leaderboard') {
      final ctx = appNavigatorKey.currentContext;
      final authed = ctx != null &&
          Provider.of<AuthProvider>(ctx, listen: false).isAuthenticated;
      if (authed) {
        navigatorState.pushNamed(AppRoutes.leaderboard);
      } else {
        DebugLogger.logWarn(
          'DEEPLINK',
          'Ignoring /leaderboard — login required',
        );
      }
    } else if (path == '/ai-chat') {
      navigatorState.pushNamed(AppRoutes.aiChat);
    } else if (path == '/disaggregation-analysis') {
      navigatorState.pushNamed(AppRoutes.disaggregationAnalysis);
    } else if (path == '/settings') {
      navigatorState.pushNamed(AppRoutes.settings);
    } else if (AppRoutes.isNativeAdminPath(path)) {
      navigatorState.pushNamed(path);
    } else {
      DebugLogger.logWarn('DEEPLINK', 'Unhandled deep link path: $path');
    }
  }

  void dispose() {
    _linkSubscription?.cancel();
    _linkSubscription = null;
  }
}
