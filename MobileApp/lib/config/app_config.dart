import 'package:flutter/foundation.dart'
    show kIsWeb, kDebugMode, defaultTargetPlatform, TargetPlatform;
import 'package:flutter_dotenv/flutter_dotenv.dart';
import '../services/organization_config_service.dart';

class AppConfig {
  static bool _envFlag(String key, {bool defaultValue = false}) {
    final envValue = dotenv.env[key];
    if (envValue != null) {
      return envValue.toLowerCase() == 'true';
    }
    return bool.fromEnvironment(key, defaultValue: defaultValue);
  }

  // Environment Configuration (see productionBackendUrl / productionFrontendUrl below).
  // PRODUCTION=true → Backoffice: IFRC (databank.ifrc.org); public website: Fly.io.
  // STAGING=true → Backoffice: databank-stage.ifrc.org (IFRC staging); public website: Fly.io when flags set.
  // DEMO=true → Humanitarian Databank Fly preview (*.fly.dev backoffice); not IFRC staging.
  // DEVELOPMENT=true → localhost / emulator hosts. Omit all four for ad-hoc defaults in _backendUrlRaw.
  static final bool isProduction =
      _envFlag('PRODUCTION', defaultValue: false);
  static final bool isStaging =
      _envFlag('STAGING', defaultValue: false);
  static final bool isDemo =
      _envFlag('DEMO', defaultValue: false);
  static final bool isDevelopment =
      _envFlag('DEVELOPMENT', defaultValue: false);

  /// True when the resolved backoffice URL is loopback or the Android emulator host.
  static bool get isLocalBackendHost {
    try {
      final uri = Uri.parse(backendUrl);
      final host = uri.host.toLowerCase();
      return host == 'localhost' ||
          host == '127.0.0.1' ||
          host == '10.0.2.2' ||
          host == '[::1]' ||
          host == '::1';
    } catch (_) {
      return false;
    }
  }

  /// Test quick-login buttons: debug builds only, with a local backoffice (excludes release/CI).
  static bool get isQuickLoginEnabled => kDebugMode && isLocalBackendHost;

  /// IFRC-hosted backoffice (e.g. databank.ifrc.org, databank-stage.ifrc.org).
  static bool get isIfrcBackendHost {
    try {
      final host = Uri.parse(backendUrl).host.toLowerCase();
      return host == 'ifrc.org' || host.endsWith('.ifrc.org');
    } catch (_) {
      return false;
    }
  }

  /// Fly.io app host (*.fly.dev).
  static bool get isFlyDevBackend {
    try {
      return Uri.parse(backendUrl).host.toLowerCase().contains('fly.dev');
    } catch (_) {
      return false;
    }
  }

  /// Email/password login in the app: Fly preview or local backoffice only (not IFRC-hosted).
  static bool get isManualCredentialLoginEnabled =>
      isFlyDevBackend || isLocalBackendHost;

  // Production — backoffice is IFRC-hosted (not *.fly.dev). Public website is on Fly.io.
  static const String productionBackendUrl = 'https://databank.ifrc.org';
  static const String productionFrontendUrl =
      'https://website-databank.fly.dev';

  // Staging — IFRC-hosted backoffice only (website URL still resolved via flags / .env)
  static const String stagingBackendUrl = 'https://databank-stage.ifrc.org';

  /// Fly.io Humanitarian Databank preview backoffice (CI `demo` profile when BACKEND_URL is unset).
  static const String demoBackendUrl = 'https://backoffice-databank.fly.dev';

  // Development URLs (localhost)
  static const String devBackendUrlWeb = 'http://localhost:5000';
  static const String devBackendUrlAndroid = 'http://10.0.2.2:5000';
  static const String devBackendUrlOther = 'http://localhost:5000';
  static const String devFrontendUrlWeb = 'http://localhost:3000';
  static const String devFrontendUrlAndroid = 'http://10.0.2.2:3000';
  static const String devFrontendUrlOther = 'http://localhost:3000';

  // Backoffice Configuration
  // Priority: BACKEND_URL (--dart-define, highest) > .env BACKEND_URL >
  // Staging > Production > Development
  //
  // Local dev without touching .env:
  //   Android emulator → host machine: --dart-define=BACKEND_URL=http://10.0.2.2:5000
  //   Physical device + adb reverse tcp:5000 tcp:5000:
  //     --dart-define=BACKEND_URL=http://localhost:5000
  //
  // Or set BACKEND_URL in .env:
  //   BACKEND_URL=http://localhost:5000                 (local Flask)
  //   BACKEND_URL=https://databank.ifrc.org             (IFRC production backoffice)
  //   BACKEND_URL=https://databank-stage.ifrc.org       (IFRC staging)
  //   BACKEND_URL=https://backoffice-databank.fly.dev   (Fly Humanitarian Databank demo preview — not IFRC staging)
  //
  // If BACKEND_URL is not set, flag-based defaults apply:
  //   STAGING=true → databank-stage.ifrc.org
  //   DEMO=true → backoffice-databank.fly.dev
  //   PRODUCTION=true → databank.ifrc.org (IFRC)
  //   DEVELOPMENT=true → localhost (10.0.2.2 for Android emulator)
  //   no flags → same default as PRODUCTION (databank.ifrc.org); see _backendUrlRaw
  static String get backendUrl => _normalizeLoopbackToLocalhost(_backendUrlRaw);

  /// Prefer `localhost` over `127.0.0.1` in URLs (same loopback; matches typical Flask copy).
  static String _normalizeLoopbackToLocalhost(String url) {
    try {
      final u = Uri.parse(url);
      if (u.host == '127.0.0.1') {
        return u.replace(host: 'localhost').toString();
      }
    } catch (_) {}
    return url;
  }

  static String get _backendUrlRaw {
    const fromDefine = String.fromEnvironment('BACKEND_URL', defaultValue: '');
    final trimmedDefine = fromDefine.trim();
    if (trimmedDefine.isNotEmpty) {
      return trimmedDefine.endsWith('/')
          ? trimmedDefine.substring(0, trimmedDefine.length - 1)
          : trimmedDefine;
    }

    final customBackendUrl = dotenv.env['BACKEND_URL']?.trim();
    if (customBackendUrl != null && customBackendUrl.isNotEmpty) {
      return customBackendUrl.endsWith('/')
          ? customBackendUrl.substring(0, customBackendUrl.length - 1)
          : customBackendUrl;
    }

    // Fall back to flag-based selection
    if (isStaging) {
      return stagingBackendUrl;
    }
    if (isDemo) {
      return demoBackendUrl;
    }
    if (isProduction) {
      return productionBackendUrl;
    }
    if (isDevelopment) {
      if (kIsWeb) {
        return devBackendUrlWeb;
      }
      if (defaultTargetPlatform == TargetPlatform.android) {
        return devBackendUrlAndroid;
      }
      return devBackendUrlOther;
    }

    // Default to production when no flags are set
    return productionBackendUrl;
  }

  /// True when no `BACKEND_URL` (`--dart-define` or `.env`) and no `STAGING` /
  /// `DEMO` / `PRODUCTION` / `DEVELOPMENT` flag — [backendUrl] uses
  /// [productionBackendUrl]. Used to warn in debug when that default is easy to mistake for a local build.
  static bool get isImplicitProductionBackendDefault {
    const fromDefine = String.fromEnvironment('BACKEND_URL', defaultValue: '');
    if (fromDefine.trim().isNotEmpty) return false;
    final envUrl = dotenv.env['BACKEND_URL']?.trim();
    if (envUrl != null && envUrl.isNotEmpty) return false;
    if (isStaging || isDemo || isProduction || isDevelopment) return false;
    return true;
  }

  static String get baseApiUrl => backendUrl;

  // Website Configuration
  // Priority: FRONTEND_URL (--dart-define, same as CI) > .env FRONTEND_URL >
  // Staging/Production/Demo flags > Development > localhost fallbacks
  //
  // Cloud simulators (e.g. Appetize) cannot reach your machine: use a public
  // https://… FRONTEND_URL, not http://localhost:3000.
  //
  // To override the frontend URL, set FRONTEND_URL in your .env file:
  //   FRONTEND_URL=http://localhost:3000               (local Website)
  //   FRONTEND_URL=https://website-databank.fly.dev    (public site; Fly.io — not the backoffice host)
  //
  // If FRONTEND_URL is not set:
  //   STAGING=true or PRODUCTION=true or DEMO=true → website-databank.fly.dev
  //   DEVELOPMENT=true → localhost (10.0.2.2:3000 on Android emulator)
  //   no flags → dev localhost defaults (see frontendUrl)
  static String get frontendUrl => _normalizeFrontendUrlTrailingSlash(_frontendUrlRaw);

  /// Public “Mobile apps” download page (iOS/Android links). Resolved from [frontendUrl].
  static String get mobileAppsDownloadUrl => '$frontendUrl/download-apps/';

  static String _normalizeFrontendUrlTrailingSlash(String url) {
    if (url.endsWith('/')) {
      return url.substring(0, url.length - 1);
    }
    return url;
  }

  static String get _frontendUrlRaw {
    const fromDefine = String.fromEnvironment('FRONTEND_URL', defaultValue: '');
    final trimmedDefine = fromDefine.trim();
    if (trimmedDefine.isNotEmpty) {
      return trimmedDefine;
    }

    final customFrontendUrl = dotenv.env['FRONTEND_URL']?.trim();
    if (customFrontendUrl != null && customFrontendUrl.isNotEmpty) {
      return customFrontendUrl;
    }

    // Fall back to flag-based selection
    if (isStaging || isProduction || isDemo) {
      return productionFrontendUrl;
    }
    if (isDevelopment) {
      if (kIsWeb) {
        return devFrontendUrlWeb;
      }
      if (defaultTargetPlatform == TargetPlatform.android) {
        return devFrontendUrlAndroid;
      }
      return devFrontendUrlOther;
    }

    // Default to development URLs if no flags are set
    if (kIsWeb) {
      return devFrontendUrlWeb;
    }
    // Check if running on Android
    if (defaultTargetPlatform == TargetPlatform.android) {
      return devFrontendUrlAndroid;
    }
    return devFrontendUrlOther;
  }

  // Azure AD B2C Configuration (dynamic, loaded from organization config)
  static String get azureB2CTenant {
    try {
      if (OrganizationConfigService().isInitialized) {
        final tenant = OrganizationConfigService().config.azure.b2cTenant;
        if (tenant.isNotEmpty) return tenant;
      }
    } catch (e) {
      // Fallback if config not loaded
    }
    return ''; // Default: empty (Azure B2C disabled)
  }

  static String get azureB2CPolicy {
    try {
      if (OrganizationConfigService().isInitialized) {
        final policy = OrganizationConfigService().config.azure.b2cPolicy;
        if (policy.isNotEmpty) return policy;
      }
    } catch (e) {
      // Fallback if config not loaded
    }
    return ''; // Default: empty (Azure B2C disabled)
  }

  static String get azureB2CRedirectScheme {
    try {
      if (OrganizationConfigService().isInitialized) {
        return OrganizationConfigService().config.azure.redirectScheme;
      }
    } catch (e) {
      // Fallback if config not loaded
    }
    return 'humdatabank'; // Default fallback
  }

  // API Endpoints
  static const String loginEndpoint = '/login';
  static const String azureLoginEndpoint = '/login/azure';
  static const String azureCallbackEndpoint = '/auth/azure/callback';
  static const String dashboardEndpoint = '/';
  static const String accountSettingsEndpoint = '/account-settings';

  // Mobile API surface -- all mobile routes use JWT Bearer auth
  static const String mobileApiPrefix = '/api/mobile/v1';

  // Auth
  static const String mobileTokenEndpoint = '$mobileApiPrefix/auth/token';
  static const String mobileRefreshEndpoint = '$mobileApiPrefix/auth/refresh';
  static const String mobileSessionCheckEndpoint = '$mobileApiPrefix/auth/session';
  static const String mobileExchangeSessionEndpoint = '$mobileApiPrefix/auth/exchange-session';
  static const String logoutEndpoint = '$mobileApiPrefix/auth/logout';
  static const String changePasswordEndpoint = '$mobileApiPrefix/auth/change-password';
  static const String profileEndpoint = '$mobileApiPrefix/auth/profile';

  // Notifications
  static const String notificationsEndpoint = '$mobileApiPrefix/notifications';
  static const String notificationsCountEndpoint = '$mobileApiPrefix/notifications/count';
  static const String markNotificationsReadEndpoint = '$mobileApiPrefix/notifications/mark-read';
  static const String markNotificationsUnreadEndpoint = '$mobileApiPrefix/notifications/mark-unread';
  static const String notificationPreferencesEndpoint = '$mobileApiPrefix/notifications/preferences';

  // Devices
  static const String deviceRegisterEndpoint = '$mobileApiPrefix/devices/register';
  static const String deviceUnregisterEndpoint = '$mobileApiPrefix/devices/unregister';
  static const String deviceHeartbeatEndpoint = '$mobileApiPrefix/devices/heartbeat';

  // Admin -- Users
  static const String mobileAdminUsersEndpoint = '$mobileApiPrefix/admin/users';
  static const String mobileRbacRolesEndpoint = '$mobileApiPrefix/admin/users/rbac-roles';

  // Admin -- Access Requests
  static const String mobileAccessRequestsEndpoint = '$mobileApiPrefix/admin/access-requests';

  // Admin -- Analytics
  static const String mobileDashboardStatsEndpoint = '$mobileApiPrefix/admin/analytics/dashboard-stats';

  /// Focal-point home: assignments + entities (same payload as legacy GET /api/v1/dashboard).
  static const String mobileUserDashboardEndpoint = '$mobileApiPrefix/user/dashboard';
  static const String mobileDashboardActivityEndpoint = '$mobileApiPrefix/admin/analytics/dashboard-activity';
  static const String mobileLoginLogsEndpoint = '$mobileApiPrefix/admin/analytics/login-logs';
  static const String mobileSessionLogsEndpoint = '$mobileApiPrefix/admin/analytics/session-logs';
  static const String mobileEndSessionEndpoint = '$mobileApiPrefix/admin/analytics/sessions';
  static const String mobileAuditTrailEndpoint = '$mobileApiPrefix/admin/analytics/audit-trail';

  // Admin -- Content
  static const String mobileTemplatesEndpoint = '$mobileApiPrefix/admin/content/templates';
  static const String mobileAssignmentsEndpoint = '$mobileApiPrefix/admin/content/assignments';

  static String mobileAssignmentDetailEndpoint(int assignmentId) =>
      '$mobileApiPrefix/admin/content/assignments/$assignmentId';
  static const String mobileDocumentsEndpoint = '$mobileApiPrefix/admin/content/documents';
  static const String mobileResourcesEndpoint = '$mobileApiPrefix/admin/content/resources';
  static const String mobileIndicatorBankEndpoint = '$mobileApiPrefix/admin/content/indicator-bank';
  static const String mobileTranslationsEndpoint = '$mobileApiPrefix/admin/content/translations';
  static const String mobileTranslationSourcesEndpoint =
      '$mobileApiPrefix/admin/content/translations/sources';

  // Admin -- Notifications (send)
  static const String mobileAdminSendNotificationEndpoint = '$mobileApiPrefix/admin/notifications/send';

  // Admin -- Organization
  static const String mobileOrgBranchesEndpoint = '$mobileApiPrefix/admin/org/branches';
  static const String mobileOrgSubbranchesEndpoint = '$mobileApiPrefix/admin/org/subbranches';
  static const String mobileOrgStructureEndpoint = '$mobileApiPrefix/admin/org/structure';

  // Public data (via mobile API)
  static const String mobileCountryMapEndpoint = '$mobileApiPrefix/data/countrymap';
  static const String mobileSectorsSubsectorsEndpoint = '$mobileApiPrefix/data/sectors-subsectors';
  static const String mobilePublicIndicatorBankEndpoint = '$mobileApiPrefix/data/indicator-bank';
  static const String mobilePublicResourcesEndpoint = '$mobileApiPrefix/data/resources';
  static const String mobileUnifiedPlanningConfigEndpoint =
      '$mobileApiPrefix/data/unified-planning-config';
  static const String mobileUnifiedPlanningThumbnailEndpoint =
      '$mobileApiPrefix/data/unified-planning-thumbnail';

  /// IFRC GO API credentials for client-side PublicSiteAppeals fetch (unified planning).
  /// Set via `.env` or `--dart-define=IFRC_API_USER=...` / `IFRC_API_PASSWORD=...`.
  static String get ifrcApiUser {
    final v = dotenv.env['IFRC_API_USER'] ?? dotenv.env['IFRC_API_USERNAME'];
    if (v != null && v.trim().isNotEmpty) return v.trim();
    const d = String.fromEnvironment('IFRC_API_USER', defaultValue: '');
    return d.trim();
  }

  static String get ifrcApiPassword {
    final v = dotenv.env['IFRC_API_PASSWORD'];
    if (v != null && v.trim().isNotEmpty) return v.trim();
    const d = String.fromEnvironment('IFRC_API_PASSWORD', defaultValue: '');
    return d.trim();
  }

  /// `per_page` for public indicator bank list requests. Must stay within the
  /// Backoffice `public_indicator_bank` route `max_per_page` (currently 2000).
  static const int mobilePublicIndicatorBankPerPage = 2000;
  static const String mobileIndicatorSuggestionsEndpoint = '$mobileApiPrefix/data/indicator-suggestions';
  static const String mobileQuizLeaderboardEndpoint = '$mobileApiPrefix/data/quiz/leaderboard';
  static const String mobileQuizSubmitScoreEndpoint = '$mobileApiPrefix/data/quiz/submit-score';
  static const String mobileFdrsPeriodsEndpoint = '$mobileApiPrefix/data/periods';
  static const String mobileFdrsOverviewEndpoint = '$mobileApiPrefix/data/fdrs-overview';
  static const String mobileScreenViewEndpoint = '$mobileApiPrefix/analytics/screen-view';

  /// Main app dashboard (assignments / entities). Not the admin analytics stats endpoint.
  static const String dashboardApiEndpoint = mobileUserDashboardEndpoint;

  // Storage Keys — prefixed by build environment so prod and staging installs on
  // the same device write to separate Keychain / SharedPreferences namespaces.
  // Changing these from const → get is intentional: the value depends on runtime
  // environment flags (isStaging / isDemo / isDevelopment) resolved from .env / dart-define.
  static String get _storagePrefix {
    if (isStaging) return 'staging_';
    if (isDemo) return 'demo_';
    if (isDevelopment) return 'dev_';
    return '';
  }

  static String get sessionCookieKey         => '${_storagePrefix}session_cookie';
  static String get userEmailKey              => '${_storagePrefix}user_email';
  static String get rememberMeKey             => '${_storagePrefix}remember_me';
  static String get selectedEntityTypeKey     => '${_storagePrefix}selected_entity_type';
  static String get selectedEntityIdKey       => '${_storagePrefix}selected_entity_id';
  /// Survives logout — AuthService.logout() preserves this key across
  /// clearSecure() so the same physical device keeps the same token.
  static String get persistentDeviceInstallIdKey =>
      '${_storagePrefix}persistent_device_install_id';

  // Cache Keys
  static String get cachedDashboardKey   => '${_storagePrefix}cached_dashboard';
  static String get cachedUserProfileKey => '${_storagePrefix}cached_user_profile';
  static String get cachedEntitiesKey    => '${_storagePrefix}cached_entities';

  /// SharedPreferences JSON for unified planning analytics year/type filters.
  static String get unifiedPlanningAnalyticsFiltersKey =>
      '${_storagePrefix}unified_planning_analytics_filters';

  /// Last successful unified planning IFRC document list + thumbnail flag (offline).
  static String get cachedUnifiedPlanningSnapshotKey =>
      '${_storagePrefix}cached_unified_planning_snapshot';

  // ── Durable prefs (SharedPreferences) — env-prefixed for staging/dev isolation ──

  static String get themeModeKey => '${_storagePrefix}theme_mode';
  static String get selectedLanguageKey => '${_storagePrefix}selected_language';
  static String get arabicTextFontKey => '${_storagePrefix}arabic_text_font';

  static String get chatbotAiPolicyAcknowledgedKey =>
      '${_storagePrefix}humdb_chatbot_ai_policy_acknowledged';
  static String get chatbotSourcesKey =>
      '${_storagePrefix}humdb_chatbot_sources';
  static String get chatbotPinnedConversationIdsKey =>
      '${_storagePrefix}humdb_chatbot_pinned_conversation_ids';

  static String get lastSyncedTimestampKey =>
      '${_storagePrefix}last_synced_timestamp';

  static String get auditTrailWidgetActivityFiltersKey =>
      '${_storagePrefix}audit_trail_widget_activity_filters_v1';

  /// Keys are `$tabCustomizationKeyPrefix$roleKey` (admin|focal|auth|guest).
  static String get tabCustomizationKeyPrefix =>
      '${_storagePrefix}tab_customization_';

  /// On-disk JSON snapshot for Indicator Bank (large payload; not in SharedPreferences).
  static String get indicatorBankSnapshotFilename =>
      '${_storagePrefix}indicator_bank_snapshot_v1.json';

  // App Configuration (dynamic, loaded from organization config)
  static String get appName {
    try {
      if (OrganizationConfigService().isInitialized) {
        return OrganizationConfigService().config.app.name;
      }
    } catch (e) {
      // Fallback if config not loaded
    }
    return 'Humanitarian Databank'; // Default fallback
  }
  static const Duration cacheExpiration = Duration(hours: 1);
  // Must match the server's PERMANENT_SESSION_LIFETIME (7 days).
  // With SESSION_REFRESH_EACH_REQUEST=True on the server, each authenticated
  // request rolls this window forward — so staying logged in across weeks works
  // as long as the app is opened at least once per week.
  static const Duration sessionTimeout = Duration(days: 7);

  // Feature Flags
  static const bool loginEnabled = true;

  // Sentry Configuration (Error Tracking)
  // Set via environment variable or compile-time constant
  // Leave empty to disable Sentry
  static const String sentryDsn =
      String.fromEnvironment('SENTRY_DSN', defaultValue: '');

  // API Key for public endpoints (DB-managed key, sent as Authorization: Bearer)
  // Priority: MOBILE_APP_API_KEY (new) -> API_KEY (legacy alias) -> compile-time define -> empty string
  static String get apiKey {
    final envValue = dotenv.env['MOBILE_APP_API_KEY'] ?? dotenv.env['API_KEY'];
    if (envValue != null && envValue.isNotEmpty) {
      return envValue.trim();
    }

    const defineValue = String.fromEnvironment('MOBILE_APP_API_KEY', defaultValue: '');
    if (defineValue.isNotEmpty) {
      return defineValue.trim();
    }

    // Legacy compile-time alias
    const legacyDefine = String.fromEnvironment('API_KEY', defaultValue: '');
    if (legacyDefine.isNotEmpty) {
      return legacyDefine.trim();
    }

    return '';
  }

  /// Public Mapbox token for raster tiles (same style family as the website).
  /// Set `MAPBOX_ACCESS_TOKEN` in `.env` or `--dart-define=MAPBOX_ACCESS_TOKEN=pk.…`.
  /// When empty, the app falls back to Carto basemaps in `fdrs_world_map.dart`.
  static String get mapboxAccessToken {
    final env = dotenv.env['MAPBOX_ACCESS_TOKEN']?.trim();
    if (env != null && env.isNotEmpty) return env;
    const define = String.fromEnvironment('MAPBOX_ACCESS_TOKEN', defaultValue: '');
    return define.trim();
  }

  // Security Note: Authentication bypass removed for security.
  // If needed for development, use environment variables with kDebugMode checks
  // and ensure it can NEVER be enabled in release builds.

  // WebView Security - Allowed URL patterns
  // Only URLs matching these patterns will be allowed to load in WebView
  static List<String> getAllowedUrlPatterns() {
    // Hosts the Backoffice CSP permits for scripts/styles/fonts/embeds (see
    // Backoffice/app/middleware/security_headers.py). Without these, release
    // builds can block iframes or navigations that the server already allows,
    // which looks like missing CSS/JS in the embedded WebView.
    const cdnAndEmbedHosts = <String>[
      'https://cdnjs.cloudflare.com',
      'https://cdn.jsdelivr.net',
      'https://unpkg.com',
      'https://code.jquery.com',
      'https://www.gstatic.com',
      'https://fonts.googleapis.com',
      'https://fonts.gstatic.com',
      'https://nominatim.openstreetmap.org',
      // AI chat embedded map (Leaflet): Mapbox raster tiles when MAPBOX_ACCESS_TOKEN is set;
      // otherwise OSM tiles (must be allowlisted for release WebView subresource loads).
      'https://api.mapbox.com',
      'https://*.tile.openstreetmap.org',
      'https://a.tile.openstreetmap.org',
      'https://b.tile.openstreetmap.org',
      'https://c.tile.openstreetmap.org',
      'https://ipapi.co',
      'https://app.powerbi.com',
      'https://app.powerbigov.us',
      'https://msit.powerbi.com',
      'https://public.tableau.com',
    ];
    return [
      backendUrl,
      frontendUrl,
      ...cdnAndEmbedHosts,
      // Allow staging URLs
      if (isStaging) ...[
        'https://databank-stage.ifrc.org',
        'https://*.databank-stage.ifrc.org',
      ],
      // Production WebView: IFRC backoffice is in `backendUrl`; allow Fly.io for public website embeds/previews.
      if (isProduction) ...[
        'https://*.fly.dev',
        'https://*.databank.fly.dev',
      ],
      // Demo: Fly preview backoffice + public site (Humanitarian Databank, not IFRC staging).
      if (isDemo) ...[
        'https://*.fly.dev',
        'https://*.databank.fly.dev',
      ],
      // Allow localhost for development
      if (!isProduction && !isStaging && !isDemo) ...[
        'http://localhost:*',
        'http://127.0.0.1:*',
        'http://10.0.2.2:*', // Android emulator
      ],
    ];
  }
}
