import 'package:flutter/foundation.dart'
    show kIsWeb, defaultTargetPlatform, TargetPlatform;
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

  // Environment Configuration
  // Set to true for production builds (fly.dev)
  // Set to true for staging builds (databank-stage.ifrc.org)
  // Set to false for local development
  static final bool isProduction =
      _envFlag('PRODUCTION', defaultValue: false);
  static final bool isStaging =
      _envFlag('STAGING', defaultValue: false);
  static final bool isDevelopment =
      _envFlag('DEVELOPMENT', defaultValue: false);

  // Production URLs (fly.dev)
  static const String productionBackendUrl = 'https://backoffice-databank.fly.dev';
  static const String productionFrontendUrl =
      'https://website-databank.fly.dev';

  // Staging URLs (backend only)
  static const String stagingBackendUrl = 'https://databank-stage.ifrc.org';

  // Development URLs (localhost)
  static const String devBackendUrlWeb = 'http://localhost:5000';
  static const String devBackendUrlAndroid = 'http://10.0.2.2:5000';
  static const String devBackendUrlOther = 'http://localhost:5000';
  static const String devFrontendUrlWeb = 'http://localhost:3000';
  static const String devFrontendUrlAndroid = 'http://10.0.2.2:3000';
  static const String devFrontendUrlOther = 'http://localhost:3000';

  // Backoffice Configuration
  // Priority: BACKEND_URL (from .env) > Staging > Production > Development
  //
  // To override the backend URL, set BACKEND_URL in your .env file:
  //   BACKEND_URL=http://localhost:5000          (for local development)
  //   BACKEND_URL=https://backoffice-databank.fly.dev  (for production)
  //   BACKEND_URL=https://databank-stage.ifrc.org      (for staging)
  //
  // If BACKEND_URL is not set, the app uses:
  //   - Staging: databank-stage.ifrc.org (if STAGING=true)
  //   - Production: fly.dev URL (if PRODUCTION=true)
  //   - Development: localhost (10.0.2.2 for Android emulator)
  static String get backendUrl {
    // First, check if BACKEND_URL is explicitly set in .env file
    final customBackendUrl = dotenv.env['BACKEND_URL']?.trim();
    if (customBackendUrl != null && customBackendUrl.isNotEmpty) {
      // Remove trailing slash if present
      return customBackendUrl.endsWith('/')
          ? customBackendUrl.substring(0, customBackendUrl.length - 1)
          : customBackendUrl;
    }

    // Fall back to flag-based selection
    if (isStaging) {
      return stagingBackendUrl;
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

    // Default to development URLs if no flags are set
    if (kIsWeb) {
      return devBackendUrlWeb;
    }
    // Check if running on Android
    if (defaultTargetPlatform == TargetPlatform.android) {
      return devBackendUrlAndroid;
    }
    return devBackendUrlOther;
  }

  static String get baseApiUrl => backendUrl;

  // Website Configuration
  // Priority: FRONTEND_URL (from .env) > Staging/Production > Development
  //
  // To override the frontend URL, set FRONTEND_URL in your .env file:
  //   FRONTEND_URL=http://localhost:3000          (for local development)
  //   FRONTEND_URL=https://website-databank.fly.dev  (for production)
  //
  // If FRONTEND_URL is not set, the app uses:
  //   - Staging/Production: fly.dev URL (if STAGING=true or PRODUCTION=true)
  //   - Development: localhost (10.0.2.2:3000 for Android emulator)
  static String get frontendUrl {
    // First, check if FRONTEND_URL is explicitly set in .env file
    final customFrontendUrl = dotenv.env['FRONTEND_URL']?.trim();
    if (customFrontendUrl != null && customFrontendUrl.isNotEmpty) {
      // Remove trailing slash if present
      return customFrontendUrl.endsWith('/')
          ? customFrontendUrl.substring(0, customFrontendUrl.length - 1)
          : customFrontendUrl;
    }

    // Fall back to flag-based selection
    if (isStaging || isProduction) {
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
    return 'ngodatabank'; // Default fallback
  }

  // API Endpoints
  static const String loginEndpoint = '/login';
  static const String azureLoginEndpoint = '/login/azure';
  static const String azureCallbackEndpoint = '/auth/azure/callback';
  static const String logoutEndpoint = '/logout';
  static const String dashboardEndpoint = '/';
  static const String accountSettingsEndpoint = '/account-settings';
  static const String changePasswordEndpoint = '/auth/change-password';

  // User Profile API Endpoint (preferred method)
  // This endpoint should return JSON with user profile data
  // Format: { "id": int, "email": string, "name": string?, "title": string?,
  //           "role": string, "chatbot_enabled": bool, "profile_color": string?,
  //           "country_ids": int[] }
  static const String userProfileApiEndpoint = '/api/v1/user/profile';

  // User Profile Update API Endpoint (PUT/PATCH)
  // This endpoint accepts JSON with updatable fields:
  // Format: { "name": string?, "title": string?, "chatbot_enabled": bool?, "profile_color": string? }
  static const String userProfileUpdateApiEndpoint = '/api/v1/user/profile';

  // Dashboard API Endpoint (preferred method - JSON API)
  // This endpoint should return JSON with dashboard data
  // Format: { "current_assignments": [...], "past_assignments": [...],
  //           "entities": [...], "selected_entity": {...} | null }
  static const String dashboardApiEndpoint = '/api/v1/dashboard';
  static const String notificationsEndpoint = '/notifications/api';
  static const String notificationsCountEndpoint = '/notifications/api/count';
  static const String markNotificationsReadEndpoint =
      '/notifications/mark-read';
  static const String markNotificationsUnreadEndpoint =
      '/notifications/mark-unread';
  static const String notificationPreferencesEndpoint =
      '/notifications/api/preferences';
  static const String deviceRegisterEndpoint =
      '/notifications/api/devices/register';
  static const String deviceUnregisterEndpoint =
      '/notifications/api/devices/unregister';

  // Storage Keys
  static const String sessionCookieKey = 'session_cookie';
  static const String userEmailKey = 'user_email';
  static const String rememberMeKey = 'remember_me';
  static const String selectedEntityTypeKey = 'selected_entity_type';
  static const String selectedEntityIdKey = 'selected_entity_id';

  // Cache Keys
  static const String cachedDashboardKey = 'cached_dashboard';
  static const String cachedUserProfileKey = 'cached_user_profile';
  static const String cachedEntitiesKey = 'cached_entities';

  // App Configuration (dynamic, loaded from organization config)
  static String get appName {
    try {
      if (OrganizationConfigService().isInitialized) {
        return OrganizationConfigService().config.app.name;
      }
    } catch (e) {
      // Fallback if config not loaded
    }
    return 'NGO Databank'; // Default fallback
  }
  static const Duration cacheExpiration = Duration(hours: 1);
  static const Duration sessionTimeout = Duration(hours: 8);

  // Feature Flags
  static const bool loginEnabled = true;

  // Sentry Configuration (Error Tracking)
  // Set via environment variable or compile-time constant
  // Leave empty to disable Sentry
  static const String sentryDsn =
      String.fromEnvironment('SENTRY_DSN', defaultValue: '');

  // API Key for public endpoints
  // Priority: .env/.env.mobile -> compile-time define -> empty string
  static String get apiKey {
    final envValue = dotenv.env['API_KEY'];
    if (envValue != null && envValue.isNotEmpty) {
      return envValue;
    }

    const defineValue = String.fromEnvironment('API_KEY', defaultValue: '');
    if (defineValue.isNotEmpty) {
      return defineValue;
    }

    return '';
  }

  // Shared secret used by native clients to authenticate notification API calls
  static String get mobileNotificationApiKey =>
      dotenv.env['MOBILE_NOTIFICATION_API_KEY'] ??
      const String.fromEnvironment(
        'MOBILE_NOTIFICATION_API_KEY',
        defaultValue: '',
      );

  // Security Note: Authentication bypass removed for security.
  // If needed for development, use environment variables with kDebugMode checks
  // and ensure it can NEVER be enabled in release builds.

  // WebView Security - Allowed URL patterns
  // Only URLs matching these patterns will be allowed to load in WebView
  static List<String> getAllowedUrlPatterns() {
    return [
      backendUrl,
      frontendUrl,
      // Allow staging URLs
      if (isStaging) ...[
        'https://databank-stage.ifrc.org',
        'https://*.databank-stage.ifrc.org',
      ],
      // Allow subdomains of production URLs
      if (isProduction) ...[
        'https://*.fly.dev',
        'https://*.databank.fly.dev',
      ],
      // Allow localhost for development
      if (!isProduction && !isStaging) ...[
        'http://localhost:*',
        'http://127.0.0.1:*',
        'http://10.0.2.2:*', // Android emulator
      ],
    ];
  }

  // Content Security Policy for WebView
  static String get contentSecurityPolicy {
    // Default-src: allow same-origin and backend API
    // script-src: allow same-origin and inline scripts (required for some pages)
    // style-src: allow same-origin, inline styles, and Google Fonts (for Tajawal)
    // font-src: allow same-origin and Google Fonts
    // img-src: allow data URLs and same-origin
    // connect-src: allow same-origin and backend API
    return "default-src 'self' ${backendUrl} ${frontendUrl}; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: blob: ${backendUrl} ${frontendUrl}; "
        "connect-src 'self' ${backendUrl} ${frontendUrl}; "
        "frame-src 'self' ${backendUrl} ${frontendUrl}; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self' ${backendUrl} ${frontendUrl};";
  }
}
