import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:provider/provider.dart';
import 'config/routes.dart';
import 'config/app_config.dart';
import 'config/app_navigation.dart';
import 'l10n/app_localizations.dart';
import 'utils/debug_logger.dart';
// Shared providers
import 'providers/shared/auth_provider.dart';
import 'services/auth_service.dart';
import 'providers/shared/dashboard_provider.dart';
import 'providers/shared/notification_provider.dart';
import 'providers/shared/language_provider.dart';
import 'providers/shared/theme_provider.dart';
import 'providers/shared/offline_provider.dart';
import 'providers/shared/offline_banner_dismissal_provider.dart';
import 'providers/shared/backend_reachability_notifier.dart';
// Admin providers
import 'providers/admin/templates_provider.dart';
import 'providers/admin/assignments_provider.dart';
import 'providers/admin/admin_dashboard_provider.dart';
import 'providers/admin/document_management_provider.dart';
import 'providers/admin/translation_management_provider.dart';
import 'providers/admin/resources_management_provider.dart';
import 'providers/admin/organizational_structure_provider.dart';
import 'providers/admin/indicator_bank_admin_provider.dart';
import 'providers/admin/user_analytics_provider.dart';
import 'providers/admin/audit_trail_provider.dart';
import 'providers/admin/manage_users_provider.dart';
import 'providers/admin/login_logs_provider.dart';
import 'providers/admin/session_logs_provider.dart';
import 'providers/admin/access_requests_provider.dart';
import 'providers/public/indicator_bank_provider.dart';
import 'providers/public/public_resources_provider.dart';
import 'providers/public/quiz_game_provider.dart';
import 'providers/public/leaderboard_provider.dart';
import 'providers/shared/ai_chat_provider.dart';
import 'providers/shared/tab_customization_provider.dart';
import 'config/app_router.dart';
import 'services/storage_service.dart';
import 'services/prefs_migration.dart';
import 'services/push_notification_service.dart';
import 'services/auth_error_handler.dart';
import 'services/connectivity_service.dart';
import 'services/performance_service.dart';
import 'services/api_service.dart';
import 'services/organization_config_service.dart';
import 'utils/theme.dart';
import 'utils/layout_scale.dart';
import 'widgets/session_expiration_warning.dart';
import 'dart:io' show Platform;
import 'package:flutter/foundation.dart' show kDebugMode, kIsWeb;
import 'package:firebase_core/firebase_core.dart';
import 'package:home_widget/home_widget.dart';
import 'services/audit_trail_home_widget_sync.dart';
import 'services/launcher_shortcuts_service.dart';
import 'services/deep_link_service.dart';
import 'services/app_build_metadata.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
// Sentry import - use prefix to avoid conflicts
import 'package:sentry_flutter/sentry_flutter.dart' as sentry;
import 'di/service_locator.dart';
import 'services/analytics_service.dart';
import 'utils/analytics_navigator_observer.dart';

void main() async {
  // Set up dependency injection (lazy — no instances created yet)
  setupServiceLocator();

  // Initialize performance monitoring first
  final performanceService = sl<PerformanceService>();
  performanceService.recordAppStart();
  performanceService.recordMainStart();

  WidgetsFlutterBinding.ensureInitialized();

  // Verbose DEBUG logs (API/NAV/…) are off unless VERBOSE_LOGS is set (see DebugLogger.applyStartupLogPolicy).

  if (!kIsWeb && (Platform.isIOS || Platform.isAndroid)) {
    await HomeWidget.setAppGroupId(auditTrailHomeWidgetAppGroupId);
  }

  // Load environment variables (e.g., MOBILE_APP_API_KEY, BACKEND_URL)
  await dotenv.load(fileName: '.env', isOptional: true);

  await AppBuildMetadata.ensureInitialized();

  if (kDebugMode && AppConfig.isImplicitProductionBackendDefault) {
    DebugLogger.logWarn(
        'CONFIG',
        'Using default production backoffice URL (${AppConfig.backendUrl}). '
        'For local or staging, set BACKEND_URL in .env or --dart-define, or use '
        '--dart-define=DEVELOPMENT=true, STAGING=true, or DEMO=true. '
        'See MobileApp/run_mobile_with_urls.bat and MobileApp/README.md.');
  }

  DebugLogger.applyStartupLogPolicy(
    envVerboseLogs: dotenv.env['VERBOSE_LOGS']?.toLowerCase() == 'true',
  );

  // Initialize organization configuration (default: IFRC profile)
  // Override with --dart-define=ORGANIZATION_CONFIG=otherorg; use empty define for generic Humanitarian Databank config
  const organizationConfig = String.fromEnvironment('ORGANIZATION_CONFIG', defaultValue: 'ifrc');
  await sl<OrganizationConfigService>().loadConfig(
    organization: organizationConfig.isNotEmpty ? organizationConfig : null,
  );
  DebugLogger.logInfo('INIT',
      'Organization config loaded: ${sl<OrganizationConfigService>().config.organization.name}');

  // Initialize performance service
  await performanceService.initialize();
  performanceService.startInit('binding_initialized');
  performanceService.endInit('binding_initialized');

  // Optimize startup: Initialize critical services in parallel
  // Firebase can be initialized in background (non-blocking for app startup)
  performanceService.startInit('critical_services');

  // Initialize storage and connectivity services in parallel (critical for app)
  final initFutures = <Future>[];

  // Storage service - critical for app state persistence
  initFutures.add(performanceService.trackOperation('storage_init', () async {
    try {
      await sl<StorageService>().init();
      DebugLogger.logInfo('INIT', 'Storage service initialized successfully');
    } catch (e, stackTrace) {
      DebugLogger.logError('Failed to initialize storage service: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
    }
  }));

  // Connectivity service - critical for offline detection
  initFutures
      .add(performanceService.trackOperation('connectivity_init', () async {
    try {
      await sl<ConnectivityService>().initialize();
      DebugLogger.logInfo(
          'INIT', 'Connectivity service initialized successfully');
    } catch (e, stackTrace) {
      DebugLogger.logError('Failed to initialize connectivity service: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
    }
  }));

  // Wait for critical services to initialize
  await Future.wait(initFutures);
  await migrateLegacySharedPreferencesKeys(sl<StorageService>());
  final initialThemeMode =
      await ThemeProvider.loadInitialModeFromStorage(sl<StorageService>());
  performanceService.endInit('critical_services');

  await LauncherShortcutsService.install();

  // Initialize deep linking (handles initial link + stream)
  sl<DeepLinkService>().initialize();

  // Set up API service language header interceptor once at app startup
  // This ensures all API requests include the Accept-Language header
  // Must be done before runApp() to ensure it's ready for any early API calls
  final apiService = sl<ApiService>();
  apiService.addRequestInterceptor(_languageHeaderInterceptor);
  DebugLogger.logInfo('INIT', 'Language header interceptor added to API service');

  // Initialize Firebase in background (non-blocking for app startup)
  // Push notifications will work once Firebase finishes initializing
  performanceService.startInit('firebase_init');
  // Don't await - let it initialize in background
  performanceService.trackOperation('firebase_init', () async {
    try {
      await Firebase.initializeApp();
      DebugLogger.logInfo('INIT', 'Firebase initialized successfully');
      // Analytics must be initialized after Firebase.initializeApp() completes
      await sl<AnalyticsService>().initialize();
    } catch (e, stackTrace) {
      // Firebase initialization failed - push notifications and analytics won't work
      // Log the error but don't crash the app
      DebugLogger.logError('Failed to initialize Firebase: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
    } finally {
      performanceService.endInit('firebase_init');
    }
  }).catchError((e) {
    DebugLogger.logError('Firebase initialization error: $e');
    performanceService.endInit('firebase_init');
  });

  // Note: Push notifications will be initialized after user login
  // (Device registration requires authentication)

  // Initialize Sentry if DSN is configured
  if (AppConfig.sentryDsn.isNotEmpty) {
    try {
      await sentry.SentryFlutter.init(
        (options) {
          options.dsn = AppConfig.sentryDsn;
          // Set release version
          options.release = '${AppConfig.appName}@1.0.0+1';
          // Enable automatic breadcrumbs
          options.enableAutoPerformanceTracing = true;
          // Set environment
          options.environment = AppConfig.isStaging
              ? 'staging'
              : AppConfig.isDemo
                  ? 'demo'
                  : (AppConfig.isProduction ? 'production' : 'development');
        },
        appRunner: () {
          runApp(MyApp(initialThemeMode: initialThemeMode));
        },
      );
    } catch (e) {
      // Sentry initialization failed - run app without it
      DebugLogger.logError('Failed to initialize Sentry: $e');
      DebugLogger.logInfo('INIT', 'Running app without Sentry');
      runApp(MyApp(initialThemeMode: initialThemeMode));
    }
  } else {
    // Run app without Sentry if DSN is not configured
    DebugLogger.logInfo('INIT', 'Sentry disabled (DSN not configured)');
    runApp(MyApp(initialThemeMode: initialThemeMode));
  }
}

// Language header interceptor for API requests
// This ensures all API requests include the Accept-Language header
// Reads language from storage dynamically on each request
Future<Map<String, String>> _languageHeaderInterceptor(
    Map<String, String> headers, String endpoint) async {
  try {
    final storage = StorageService();
    final languageCode =
        await storage.getString(AppConfig.selectedLanguageKey) ?? 'en';
    headers['Accept-Language'] = languageCode;
  } catch (e) {
    // If we can't get the language, default to English
    headers['Accept-Language'] = 'en';
  }
  return headers;
}

class MyApp extends StatefulWidget {
  const MyApp({super.key, required this.initialThemeMode});

  /// From [ThemeProvider.loadInitialModeFromStorage] before [runApp] so the
  /// first [MaterialApp] frame matches the saved light/dark/system choice.
  final String initialThemeMode;

  @override
  State<MyApp> createState() => _MyAppState();
}

class _MyAppState extends State<MyApp> with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    // Listen to app lifecycle changes
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    // Remove lifecycle observer
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    super.didChangeAppLifecycleState(state);

    // IMPROVED: Refresh session when app resumes from background
    // This ensures users don't return to expired sessions
    if (state == AppLifecycleState.resumed) {
      DebugLogger.logAuth('App resumed - refreshing session...');
      // Refresh session in background
      // Get auth provider from context if available, otherwise use service directly
      final authService = AuthService();
      // forceRefresh: bypass 5-minute rate limit so a cold return from
      // background (especially on iOS) always attempts a token refresh before
      // other work hits the API with an expired access token.
      authService.refreshSession(forceRefresh: true).then((success) {
        if (success) {
          DebugLogger.logAuth('Session refreshed successfully on app resume');
        } else {
          DebugLogger.logWarn('AUTH', 'Session refresh failed on app resume');
        }
      }).catchError((e) {
        DebugLogger.logWarn('AUTH', 'Error refreshing session on app resume: $e');
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    // Track first frame rendering
    WidgetsBinding.instance.addPostFrameCallback((_) {
      PerformanceService().recordFirstFrame();

      // Log performance summary after first frame
      Future.delayed(const Duration(seconds: 1), () async {
        final summary = await PerformanceService().getSummary();
        summary.logSummary();
      });
    });

    return MultiProvider(
      providers: [
        // Core providers - Always needed at app startup
        // These providers manage essential app state and are lightweight
        ChangeNotifierProvider(create: (_) {
          final authProvider = AuthProvider();
          // Set auth provider reference in error handler
          AuthErrorHandler().authProvider = authProvider;
          return authProvider;
        }),
        ChangeNotifierProvider(create: (_) => DashboardProvider()),
        ChangeNotifierProvider(create: (_) => NotificationProvider()),
        ChangeNotifierProvider(create: (_) => LanguageProvider()),
        ChangeNotifierProvider(
            create: (_) => ThemeProvider(initialMode: widget.initialThemeMode)),
        ChangeNotifierProvider(create: (_) {
          final offlineProvider = OfflineProvider();
          // Initialize offline provider asynchronously (non-blocking)
          final performanceService = PerformanceService();
          performanceService.startInit('offline_provider');
          offlineProvider.initialize().then((_) {
            performanceService.endInit('offline_provider');
          }).catchError((e) {
            DebugLogger.logError('Offline provider initialization error: $e');
            performanceService.endInit('offline_provider');
          });
          return offlineProvider;
        }),
        ChangeNotifierProvider(create: (_) {
          final notifier = BackendReachabilityNotifier();
          notifier.start();
          return notifier;
        }),
        ChangeNotifierProvider(create: (_) => OfflineBannerDismissalProvider()),
        ChangeNotifierProvider(create: (_) => IndicatorBankProvider()),
        ChangeNotifierProvider(create: (_) => PublicResourcesProvider()),
        ChangeNotifierProvider(create: (_) => LeaderboardProvider()),
        ChangeNotifierProvider(create: (_) => AiChatProvider()),
        ChangeNotifierProvider(create: (_) => TabCustomizationProvider()),
        ChangeNotifierProxyProvider<IndicatorBankProvider, QuizGameProvider>(
          create: (context) {
            final indicatorProvider =
                Provider.of<IndicatorBankProvider>(context, listen: false);
            final languageProvider =
                Provider.of<LanguageProvider>(context, listen: false);
            final quizProvider = QuizGameProvider(indicatorProvider);
            quizProvider.updateLanguageProvider(languageProvider);
            return quizProvider;
          },
          update: (context, indicatorProvider, previous) {
            final languageProvider =
                Provider.of<LanguageProvider>(context, listen: false);
            if (previous == null) {
              final quizProvider = QuizGameProvider(indicatorProvider);
              quizProvider.updateLanguageProvider(languageProvider);
              return quizProvider;
            }
            previous.updateIndicatorBankProvider(indicatorProvider);
            previous.updateLanguageProvider(languageProvider);
            return previous;
          },
        ),

        // Admin providers - Only actively used when admin screens are accessed
        // These providers are lightweight at creation (data loaded on-demand via load* methods)
        // Using ChangeNotifierProvider ensures automatic disposal when app is removed from tree
        // Note: Providers persist for app lifetime but don't consume resources until first use
        ChangeNotifierProvider(create: (_) => TemplatesProvider()),
        ChangeNotifierProvider(create: (_) => AssignmentsProvider()),
        ChangeNotifierProvider(create: (_) => AdminDashboardProvider()),
        ChangeNotifierProvider(create: (_) => DocumentManagementProvider()),
        ChangeNotifierProvider(create: (_) => TranslationManagementProvider()),
        ChangeNotifierProvider(create: (_) => ResourcesManagementProvider()),
        ChangeNotifierProvider(
            create: (_) => OrganizationalStructureProvider()),
        ChangeNotifierProvider(create: (_) => IndicatorBankAdminProvider()),
        ChangeNotifierProvider(create: (_) => UserAnalyticsProvider()),
        ChangeNotifierProvider(create: (_) => AuditTrailProvider()),
        ChangeNotifierProvider(create: (_) => ManageUsersProvider()),
        ChangeNotifierProvider(create: (_) => LoginLogsProvider()),
        ChangeNotifierProvider(create: (_) => SessionLogsProvider()),
        ChangeNotifierProvider(create: (_) => AccessRequestsProvider()),
      ],
      child: Consumer2<LanguageProvider, ThemeProvider>(
        builder: (context, languageProvider, themeProvider, child) {
          // Convert language code to Locale
          final locale = Locale(languageProvider.currentLanguage);


          // Set navigator key for push notification service
          PushNotificationService().navigatorKey = appNavigatorKey;

          return SessionExpirationWarning(
            child: MaterialApp(
            navigatorKey: appNavigatorKey,
            navigatorObservers: [AnalyticsNavigatorObserver()],
            title: AppConfig.appName,
            debugShowCheckedModeBanner: false,
            theme: AppTheme.lightTheme(
              locale: locale,
              arabicTextFont: languageProvider.arabicTextFontPreference,
            ),
            darkTheme: AppTheme.darkTheme(
              locale: locale,
              arabicTextFont: languageProvider.arabicTextFontPreference,
            ),
            themeMode: themeProvider.themeMode,
            builder: (context, child) {
              // Apply a small, global typography scale based on screen width.
              // This helps keep text proportions comfortable across phones
              // while still respecting the OS accessibility text size setting.
              final theme = Theme.of(context);
              final factor =
                  LayoutScale.screenScaleFactor(context);

              final scaled = theme.copyWith(
                textTheme: theme.textTheme.apply(fontSizeFactor: factor),
                primaryTextTheme:
                    theme.primaryTextTheme.apply(fontSizeFactor: factor),
              );

              return Theme(
                data: scaled,
                child: child ?? const SizedBox.shrink(),
              );
            },
            locale: locale,
            supportedLocales: LanguageProvider.availableLanguages
                .map((lang) => Locale(lang['code']!))
                .toList(),
            localizationsDelegates: const [
              GlobalMaterialLocalizations.delegate,
              GlobalWidgetsLocalizations.delegate,
              GlobalCupertinoLocalizations.delegate,
              AppLocalizations.delegate,
            ],
            initialRoute: AppRoutes.splash,
            routes: AppRouter.routes,
            onGenerateRoute: AppRouter.onGenerateRoute,
          ),
          )
        ;
        },
      ),
    );
  }
}

